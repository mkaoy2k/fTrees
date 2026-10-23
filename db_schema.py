"""Create and migrate the family-tree schema.

Importing this module does not create a database. Call `init_db()` from
application startup (`context_utils.init_session_state` / `fTrees.main`)
or from `genesis.py`.
"""
import re

from db_connection import db_tables, get_db_connection, quote_ident

_COLUMN_TYPE = re.compile(r"^[A-Za-z0-9_ ]+$")


def init_db() -> None:
    """Create any missing tables and migrate older databases in place."""
    migrate_referential_integrity()
    with get_db_connection() as conn:
        _create_schema(conn)
        migrate_plaintext_reset_tokens(conn)
        conn.commit()


def migrate_plaintext_reset_tokens(conn) -> int:
    """Hash leftover plaintext password-reset tokens in place.

    Existing email links still work: validation hashes the presented token
    and compares it to the stored digest. Expiry and the used flag are kept.
    Rows that already store a SHA-256 hex digest are skipped.
    """
    import auth_utils as au

    cursor = conn.cursor()
    if not _table_exists(conn, "password_reset_tokens"):
        return 0
    cursor.execute("SELECT id, token FROM password_reset_tokens")
    updated = 0
    for row in cursor.fetchall():
        token = row["token"]
        if token and not au.is_stored_reset_token(token):
            cursor.execute(
                "UPDATE password_reset_tokens SET token = ? WHERE id = ?",
                (au.hash_reset_token(token), row["id"]),
            )
            updated += 1
    return updated


def migrate_referential_integrity(conn=None) -> None:
    """Add parent and relation foreign keys without deleting rows.

    Databases created before these keys have no `FOREIGN KEY` clauses.
    SQLite cannot add them with ALTER TABLE, so members and relations are
    rebuilt. References that do not point at a real row (including the
    historical 0 sentinel) become NULL. Extra columns added later are copied.
    Orphan password-reset tokens, which cannot belong to a user, are removed.
    """
    own = conn is None
    if own:
        conn = get_db_connection()
    previous_isolation = conn.isolation_level
    try:
        conn.commit()
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys = OFF")
        started = False
        try:
            members = db_tables["members"]
            relations = db_tables["relations"]
            if not _table_exists(conn, members):
                return
            if _has_foreign_key(conn, members, "dad_id") and _has_foreign_key(conn, relations, "member_id"):
                return
            conn.execute("BEGIN")
            started = True
            _null_missing_member_refs(conn)
            _null_missing_relation_refs(conn)
            _drop_orphan_reset_tokens(conn)
            if not _has_foreign_key(conn, members, "dad_id"):
                _rebuild_members(conn)
            if _table_exists(conn, relations) and not _has_foreign_key(conn, relations, "member_id"):
                _rebuild_relations(conn)
            problems = conn.execute("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise RuntimeError(f"Foreign key check failed after migration: {problems[:5]}")
            conn.execute("COMMIT")
            started = False
        except Exception:
            if started:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = previous_isolation
        if own:
            conn.close()


def _create_schema(conn) -> None:
    users = quote_ident(db_tables["users"])
    members = quote_ident(db_tables["members"])
    relations = quote_ident(db_tables["relations"])
    families = quote_ident(db_tables["families"])
    mirrors = quote_ident(db_tables["mirrors"])
    cursor = conn.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {users} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT -1,
            l10n TEXT DEFAULT 'US',
            token TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            family_id INTEGER DEFAULT 0,
            member_id INTEGER DEFAULT 0,
            password_hash TEXT DEFAULT '',
            salt TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {families} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            background TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {members} (
            {_members_column_sql()}
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {relations} (
            {_relations_column_sql()}
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {mirrors} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Name TEXT NOT NULL,
            Aka TEXT,
            Sex INTEGER,
            Born DATE DEFAULT '0000-01-01',
            Died DATE DEFAULT '0000-01-01',
            Dad TEXT,
            Mom TEXT,
            Relation INTEGER DEFAULT 0,
            Spouse TEXT,
            Married DATE DEFAULT '0000-01-01',
            {quote_ident("Order")} INTEGER DEFAULT 0,
            Href TEXT,
            Status INTEGER DEFAULT 0
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            FOREIGN KEY (email) REFERENCES {users}(email) ON DELETE CASCADE
        )
    """)

    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_members_name ON {members}(name)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_members_family ON {members}(family_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_members_email ON {members}(email)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_relations_member ON {relations}(member_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_relations_partner ON {relations}(partner_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_relations_original ON {relations}(original_family_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_families_name ON {families}(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens(token)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_email ON password_reset_tokens(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_expires ON password_reset_tokens(expires_at)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_mirrors_name ON {mirrors}(Name)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_mirrors_order ON {mirrors}({quote_ident('Order')})")

    _timestamp_trigger(cursor, "update_users_timestamp", users)
    _timestamp_trigger(cursor, "update_members_timestamp", members)
    _timestamp_trigger(cursor, "update_relations_timestamp", relations)
    _timestamp_trigger(cursor, "update_families_timestamp", families)


def _members_column_sql() -> str:
    members = quote_ident(db_tables["members"])
    families = quote_ident(db_tables["families"])
    return ", ".join([
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "name TEXT",
        f"family_id INTEGER REFERENCES {families}(id) ON DELETE SET NULL",
        "alias TEXT",
        "email TEXT",
        "url TEXT",
        "born DATE DEFAULT '0000-00-00'",
        "died DATE DEFAULT '0000-00-00'",
        "sex TEXT",
        "gen_order INTEGER",
        f"dad_id INTEGER REFERENCES {members}(id) ON DELETE SET NULL",
        f"mom_id INTEGER REFERENCES {members}(id) ON DELETE SET NULL",
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ])


def _relations_column_sql() -> str:
    members = quote_ident(db_tables["members"])
    families = quote_ident(db_tables["families"])
    return ", ".join([
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        f"original_family_id INTEGER REFERENCES {families}(id) ON DELETE SET NULL",
        "original_name TEXT",
        f"partner_id INTEGER REFERENCES {members}(id) ON DELETE RESTRICT",
        f"member_id INTEGER REFERENCES {members}(id) ON DELETE RESTRICT",
        "relation TEXT",
        "dad_name TEXT",
        "mom_name TEXT",
        "join_date DATE DEFAULT '0000-00-00'",
        "end_date DATE DEFAULT '0000-00-00'",
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ])


def _timestamp_trigger(cursor, name, table) -> None:
    cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {name}
        AFTER UPDATE ON {table}
        FOR EACH ROW
        BEGIN
            UPDATE {table} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
    """)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _has_foreign_key(conn, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    rows = conn.execute(f"PRAGMA foreign_key_list({quote_ident(table)})").fetchall()
    return any(row[3] == column for row in rows)


def _table_columns(conn, table: str):
    return conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()


def _null_missing_member_refs(conn) -> None:
    members = quote_ident(db_tables["members"])
    families = quote_ident(db_tables["families"])
    columns = {row[1] for row in _table_columns(conn, db_tables["members"])}
    if "dad_id" in columns:
        conn.execute(f"""
            UPDATE {members} SET dad_id = NULL
            WHERE dad_id IS NOT NULL AND dad_id NOT IN (SELECT id FROM {members})
        """)
    if "mom_id" in columns:
        conn.execute(f"""
            UPDATE {members} SET mom_id = NULL
            WHERE mom_id IS NOT NULL AND mom_id NOT IN (SELECT id FROM {members})
        """)
    if "family_id" in columns and _table_exists(conn, db_tables["families"]):
        conn.execute(f"""
            UPDATE {members} SET family_id = NULL
            WHERE family_id IS NOT NULL AND family_id NOT IN (SELECT id FROM {families})
        """)


def _null_missing_relation_refs(conn) -> None:
    relations_name = db_tables["relations"]
    if not _table_exists(conn, relations_name):
        return
    relations = quote_ident(relations_name)
    members = quote_ident(db_tables["members"])
    families = quote_ident(db_tables["families"])
    columns = {row[1] for row in _table_columns(conn, relations_name)}
    if "member_id" in columns:
        conn.execute(f"""
            UPDATE {relations} SET member_id = NULL
            WHERE member_id IS NOT NULL AND member_id NOT IN (SELECT id FROM {members})
        """)
    if "partner_id" in columns:
        conn.execute(f"""
            UPDATE {relations} SET partner_id = NULL
            WHERE partner_id IS NOT NULL AND partner_id NOT IN (SELECT id FROM {members})
        """)
    if "original_family_id" in columns and _table_exists(conn, db_tables["families"]):
        conn.execute(f"""
            UPDATE {relations} SET original_family_id = NULL
            WHERE original_family_id IS NOT NULL
              AND original_family_id NOT IN (SELECT id FROM {families})
        """)


def _drop_orphan_reset_tokens(conn) -> None:
    if db_tables["users"] != "users" or not _table_exists(conn, "password_reset_tokens"):
        return
    if not _table_exists(conn, "users"):
        return
    conn.execute("""
        DELETE FROM password_reset_tokens
        WHERE email NOT IN (SELECT email FROM users)
    """)


def _rebuild_members(conn) -> None:
    _rebuild_table(conn, db_tables["members"], _members_column_sql(), [
        "id", "name", "family_id", "alias", "email", "url", "born", "died",
        "sex", "gen_order", "dad_id", "mom_id", "created_at", "updated_at",
    ])


def _rebuild_relations(conn) -> None:
    _rebuild_table(conn, db_tables["relations"], _relations_column_sql(), [
        "id", "original_family_id", "original_name", "partner_id", "member_id",
        "relation", "dad_name", "mom_name", "join_date", "end_date",
        "created_at", "updated_at",
    ])


def _rebuild_table(conn, table: str, column_sql: str, canonical: list) -> None:
    info = _table_columns(conn, table)
    old_names = [row[1] for row in info]
    known = set(canonical)
    extras = []
    extra_names = []
    for row in info:
        if row[1] in known:
            continue
        col_type = row[2] if row[2] and _COLUMN_TYPE.fullmatch(row[2]) else "TEXT"
        extras.append(f"{quote_ident(row[1])} {col_type}")
        extra_names.append(row[1])
    staging = quote_ident(f"{table}__rebuild")
    conn.execute(f"DROP TABLE IF EXISTS {staging}")
    definitions = column_sql
    if extras:
        definitions = column_sql + ", " + ", ".join(extras)
    conn.execute(f"CREATE TABLE {staging} ({definitions})")
    copy_names = [name for name in canonical if name in old_names] + extra_names
    if copy_names:
        columns = ", ".join(quote_ident(name) for name in copy_names)
        conn.execute(
            f"INSERT INTO {staging} ({columns}) SELECT {columns} FROM {quote_ident(table)}"
        )
    conn.execute(f"DROP TABLE {quote_ident(table)}")
    conn.execute(f"ALTER TABLE {staging} RENAME TO {quote_ident(table)}")
