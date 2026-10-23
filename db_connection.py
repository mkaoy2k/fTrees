"""SQLite connection policy and shared database constants.

`database_name` is stored on `config` so `db_utils.database_name = ...` and
new connections stay in agreement. Relative names are resolved from the
application root (this file's directory), not from the process working
directory.
"""
import logging
import os
import re
import sqlite3
import threading
from pathlib import Path

import funcUtils as fu
from dotenv import load_dotenv

load_dotenv(".env")

APP_ROOT = Path(__file__).resolve().parent

log = logging.getLogger("db_utils")
if not log.handlers:
    log_level = os.getenv("LOGGING", "WARNING").upper()
    log.setLevel(getattr(logging, log_level, logging.WARNING))
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    ))
    log.addHandler(console_handler)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabaseConfig:
    def __init__(self):
        self.database_name = os.getenv("DB_NAME", "data/family.db")

    def resolve_path(self):
        """Absolute database path. `:memory:` is returned unchanged."""
        name = self.database_name
        if name == ":memory:":
            return ":memory:"
        path = Path(name)
        if not path.is_absolute():
            path = APP_ROOT / path
        return path


config = DatabaseConfig()

db_tables = {
    "users": os.getenv("TBL_USERS", "users"),
    "members": os.getenv("TBL_MEMBERS", "members"),
    "relations": os.getenv("TBL_RELATIONS", "relations"),
    "families": os.getenv("TBL_FAMILIES", "families"),
    "mirrors": os.getenv("TBL_MIRRORS", "mirrors"),
}

Subscriber_State = {
    "active": 1,
    "pending": 0,
    "inactive": -1,
}

User_State = {
    "p_admin": 2,
    "f_admin": 1,
    "f_member": 0,
}

Member_Status = {
    "single": 0,
    "married": 1,
    "together": 2,
}

Member_Relation = {
    "bio": 0,
    "adopt": 1,
    "step": 2,
}

Member_Sex = {
    "male": 0,
    "female": 1,
    "inlaw-male": 2,
    "inlaw-female": 3,
}

Relation_Type = {
    "child": "child",
    "child ai": "child adopted within the family",
    "child ao": "child adopted from another family",
    "child step": "child step",
    "parent": "parent",
    "parent ai": "parent adopted within the family",
    "parent ao": "parent adopted from another family",
    "parent step": "parent step",
    "sibling": "sibling",
    "spouse": "spouse",
    "spouse cu": "spouse civil union",
    "spouse divorced": "spouse divorced",
    "spouse dp": "spouse domestic partnership",
    "spouse separated": "spouse separated",
    "other": "other",
}

USER_COLUMNS = frozenset({
    "is_admin", "family_id", "member_id", "l10n", "is_active",
})
MEMBER_COLUMNS = frozenset({
    "name", "family_id", "alias", "email", "url", "born", "died",
    "sex", "gen_order", "dad_id", "mom_id",
})
MEMBER_FK_COLUMNS = frozenset({"family_id", "dad_id", "mom_id"})
RELATION_COLUMNS = frozenset({
    "original_family_id", "original_name", "partner_id", "member_id",
    "relation", "dad_name", "mom_name", "join_date", "end_date",
})
RELATION_FK_COLUMNS = frozenset({"original_family_id", "partner_id", "member_id"})
FAMILY_COLUMNS = frozenset({"name", "background", "url"})


def quote_ident(name: str) -> str:
    """Quote a SQL identifier. Rejects anything that is not a plain name."""
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return '"' + name + '"'


def nullable_fk(value):
    """Coerce the historical 0 / blank sentinel to NULL for a foreign key."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.lstrip("-").isdigit():
            value = int(stripped)
        else:
            return value
    if isinstance(value, int):
        return value if value > 0 else None
    return value


def required_member_id(value, label):
    """Return a positive member id or raise. 0 and blanks are not members."""
    member_id = nullable_fk(value)
    if not isinstance(member_id, int):
        raise ValueError(f"{label} must be a positive member id")
    return member_id


def column_assignments(values, allowed, fk_fields=(), ignore=()):
    """Build an allowlisted `col = ?` clause.

    Keys in `ignore` are skipped (for example a password that is stored in
    other columns, or an id used only to find the row). Any other key that
    is not a real column raises ValueError.
    """
    unknown = [str(key) for key in values if key not in allowed and key not in ignore]
    if unknown:
        raise ValueError("Unknown column(s): " + ", ".join(sorted(unknown)))
    fields = []
    params = []
    fk_fields = set(fk_fields)
    for key, value in values.items():
        if key not in allowed or value is None:
            continue
        if key in fk_fields:
            value = nullable_fk(value)
        fields.append(f"{quote_ident(key)} = ?")
        params.append(value)
    return fields, params


_connections = threading.local()


def _connection_stack():
    stack = getattr(_connections, "stack", None)
    if stack is None:
        stack = []
        _connections.stack = stack
    return stack


class _ConnectionScope:
    """Context manager around one SQLite connection.

    Nested ``with get_db_connection()`` calls reuse the connection already
    open on this thread. Callers that assign ``conn = get_db_connection()``
    and then ``commit()`` / ``close()`` still receive an object with those
    methods. ``__enter__`` yields the raw connection so both scopes are the
    same object.
    """

    def __init__(self, conn, owned):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_owned", owned)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        if name in ("_conn", "_owned"):
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def __enter__(self):
        conn = object.__getattribute__(self, "_conn")
        if object.__getattribute__(self, "_owned"):
            _connection_stack().append(conn)
        return conn

    def __exit__(self, exc_type, exc, tb):
        if not object.__getattribute__(self, "_owned"):
            return False
        conn = object.__getattribute__(self, "_conn")
        stack = _connection_stack()
        if stack and stack[-1] is conn:
            stack.pop()
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        except sqlite3.Error:
            if exc_type is None:
                raise
        finally:
            if not stack:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        return False


def _open_connection():
    """Open the configured database with foreign keys enforced."""
    name = config.database_name
    if name == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        path = config.resolve_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if name != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def get_db_connection():
    """Return a connection scope for the configured database.

    A nested call reuses the connection opened by the outer ``with`` block.
    """
    stack = _connection_stack()
    if stack:
        return _ConnectionScope(stack[-1], owned=False)
    return _ConnectionScope(_open_connection(), owned=True)


def get_table_columns(table: str):
    """Return column names for a table. The table name must be an identifier."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({quote_ident(table)})")
            return [column[1] for column in cursor.fetchall()]
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching table columns: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()}: to fetch table columns: {str(e)}")


def get_total_records(table: str) -> int:
    """Return the number of rows in a table. The table name must be an identifier."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}")
            result = cursor.fetchone()
            return result[0] if result else 0
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching total records: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()}: to fetch total records: {str(e)}")
