"""Connection policy, foreign-key migration, and column allowlists."""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth_utils as au
import db_utils as dbm
import ops_dbMgmt


LEGACY_MEMBERS = """
CREATE TABLE families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    background TEXT,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    family_id INTEGER,
    alias TEXT,
    email TEXT,
    url TEXT,
    born DATE DEFAULT '0000-00-00',
    died DATE DEFAULT '0000-00-00',
    sex TEXT,
    gen_order INTEGER,
    dad_id INTEGER,
    mom_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_family_id INTEGER,
    original_name TEXT,
    partner_id INTEGER,
    member_id INTEGER,
    relation TEXT,
    dad_name TEXT,
    mom_name TEXT,
    join_date DATE DEFAULT '0000-00-00',
    end_date DATE DEFAULT '0000-00-00',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE users (
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
);
CREATE TABLE password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    token TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
);
"""


class DatabaseLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftpe-db-")
        self.db_path = os.path.join(self.tmp, "family.db")
        self._previous = dbm.database_name
        dbm.database_name = self.db_path

    def tearDown(self):
        dbm.database_name = self._previous
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_import_does_not_create_the_database(self):
        target = ROOT / "data" / "import-must-not-create.db"
        env = os.environ.copy()
        env["DB_NAME"] = "data/import-must-not-create.db"
        proc = subprocess.run(
            [sys.executable, "-c", "import db_utils"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(target.exists())

    def test_relative_path_is_resolved_from_the_app_root(self):
        previous = dbm.database_name
        dbm.database_name = "data/batch2-relative.db"
        other = tempfile.mkdtemp(prefix="ftpe-cwd-")
        cwd = os.getcwd()
        target = ROOT / "data" / "batch2-relative.db"
        try:
            os.chdir(other)
            conn = dbm.get_db_connection()
            conn.execute("CREATE TABLE IF NOT EXISTS ping (id INTEGER)")
            conn.commit()
            conn.close()
            self.assertTrue(target.exists())
            self.assertFalse((Path(other) / "data" / "batch2-relative.db").exists())
        finally:
            os.chdir(cwd)
            dbm.database_name = previous
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(target) + suffix)
                if path.exists():
                    path.unlink()
            os.rmdir(other)

    def test_connections_enforce_foreign_keys(self):
        dbm.init_db()
        with dbm.get_db_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            dad = conn.execute("PRAGMA foreign_key_list(members)").fetchall()
        columns = {row[3] for row in dad}
        self.assertIn("dad_id", columns)
        self.assertIn("mom_id", columns)
        self.assertIn("family_id", columns)

    def test_legacy_database_gains_keys_without_losing_rows(self):
        with self._connect() as conn:
            conn.executescript(LEGACY_MEMBERS)
            conn.execute("ALTER TABLE members ADD COLUMN note TEXT")
            conn.execute("INSERT INTO families (id, name) VALUES (1, 'House')")
            conn.execute("INSERT INTO members (id, name, dad_id) VALUES (4, 'Dad', NULL)")
            conn.execute(
                "INSERT INTO members (id, name, family_id, dad_id, mom_id, note) VALUES (1, 'Parent', 1, 4, 0, 'kept')"
            )
            conn.execute(
                "INSERT INTO members (id, name, family_id, dad_id, mom_id) VALUES (2, 'Child', 1, 1, 0)"
            )
            conn.execute(
                "INSERT INTO members (id, name, family_id, dad_id) VALUES (3, 'Orphan', 50, 99)"
            )
            conn.execute(
                "INSERT INTO relations (id, member_id, partner_id, relation, original_family_id) VALUES (1, 2, 1, 'parent', 1)"
            )
            conn.execute(
                "INSERT INTO relations (id, member_id, partner_id, relation, original_family_id) VALUES (2, 2, 77, 'parent', 9)"
            )
            conn.execute("INSERT INTO users (email, password_hash, salt) VALUES ('real@example.com', 'x', 'y')")
            stored = "ab" * 32
            conn.execute(
                "INSERT INTO password_reset_tokens (email, token, expires_at) VALUES ('ghost@example.com', ?, '2099-01-01')",
                (stored,),
            )
            conn.execute(
                "INSERT INTO password_reset_tokens (email, token, expires_at) VALUES ('real@example.com', ?, '2099-01-01')",
                (stored,),
            )
            conn.commit()

        dbm.init_db()
        with self._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM members").fetchone()[0], 4)
            parent = conn.execute("SELECT * FROM members WHERE id = 1").fetchone()
            child = conn.execute("SELECT * FROM members WHERE id = 2").fetchone()
            orphan = conn.execute("SELECT * FROM members WHERE id = 3").fetchone()
            self.assertEqual(parent["note"], "kept")
            self.assertEqual(parent["dad_id"], 4)
            self.assertIsNone(parent["mom_id"])
            self.assertEqual(parent["family_id"], 1)
            self.assertEqual(child["dad_id"], 1)
            self.assertIsNone(child["mom_id"])
            self.assertIsNone(orphan["dad_id"])
            self.assertIsNone(orphan["family_id"])
            good = conn.execute("SELECT * FROM relations WHERE id = 1").fetchone()
            bad = conn.execute("SELECT * FROM relations WHERE id = 2").fetchone()
            self.assertEqual(good["partner_id"], 1)
            self.assertEqual(good["original_family_id"], 1)
            self.assertIsNone(bad["partner_id"])
            self.assertIsNone(bad["original_family_id"])
            tokens = [row["email"] for row in conn.execute("SELECT email FROM password_reset_tokens")]
            self.assertEqual(tokens, ["real@example.com"])
            keys = {row[3] for row in conn.execute("PRAGMA foreign_key_list(members)")}
            self.assertIn("dad_id", keys)

        dbm.init_db()
        with dbm.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM members").fetchone()[0], 4)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO relations (member_id, partner_id, relation) VALUES (999, 1, 'parent')"
                )
            conn.execute("INSERT INTO members (name) VALUES ('Next')")
            new_id = conn.execute("SELECT id FROM members WHERE name = 'Next'").fetchone()["id"]
            self.assertEqual(new_id, 5)
            conn.execute("DELETE FROM members WHERE id = 4")
            dad = conn.execute("SELECT dad_id FROM members WHERE id = 1").fetchone()["dad_id"]
            self.assertIsNone(dad)

        with self.assertRaises(ValueError):
            dbm.delete_member(2)

    def test_update_member_rejects_unknown_columns(self):
        dbm.init_db()
        with self._connect() as conn:
            conn.execute("INSERT INTO members (id, name) VALUES (1, 'Kept')")
            conn.commit()
        with self.assertRaises(ValueError):
            dbm.update_member(1, {"name": "Changed", "password": "secret"})
        self.assertEqual(dbm.get_member(1)["name"], "Kept")
        self.assertTrue(dbm.update_member(1, {"name": "Changed", "dad_id": 0}))
        member = dbm.get_member(1)
        self.assertEqual(member["name"], "Changed")
        self.assertIsNone(member["dad_id"])

    def test_family_update_ignores_the_lookup_id(self):
        dbm.init_db()
        family_id = dbm.add_or_update_family({"name": "House", "background": "old"}, update=False)
        updated = dbm.add_or_update_family(
            {"id": family_id, "name": "House", "background": "new"},
            update=True,
        )
        self.assertEqual(updated, family_id)
        self.assertEqual(dbm.get_family(family_id)["background"], "new")

    def test_user_password_update_writes_the_hash(self):
        dbm.init_db()
        created, message = dbm.add_or_update_user(
            "person@example.com",
            "old-password-1",
            {"is_admin": 0, "is_active": 1, "l10n": "US"},
            update=False,
        )
        self.assertTrue(created, message)
        updated, message = dbm.add_or_update_user(
            "person@example.com",
            "old-password-1",
            {"password": "new-password-1", "l10n": "US"},
            update=True,
        )
        self.assertTrue(updated, message)
        with self._connect() as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE email = ?",
                ("person@example.com",),
            ).fetchone()
        self.assertNotIn("password", columns)
        self.assertTrue(au._password_ok("new-password-1", row["salt"], row["password_hash"]))

    def test_import_users_reports_a_row_error(self):
        dbm.init_db()
        result = dbm.import_users([{"email": "missing-fields@example.com"}])
        self.assertFalse(result["success"])
        self.assertTrue(result["errors"])

    def test_import_members_accepts_a_child_before_the_parent(self):
        dbm.init_db()
        result = dbm.import_members([
            {
                "id": "2", "name": "Child", "born": "2000-01-01", "gen_order": "2",
                "family_id": "", "sex": "F", "dad_id": "1", "mom_id": "",
            },
            {
                "id": "1", "name": "Parent", "born": "1970-01-01", "gen_order": "1",
                "family_id": "", "sex": "M", "dad_id": "", "mom_id": "",
            },
        ])
        self.assertTrue(result["success"], result)
        self.assertEqual(dbm.get_member(2)["dad_id"], 1)
        self.assertIsNone(dbm.get_member(2)["mom_id"])

    def test_identifiers_and_admin_drop_reject_injected_names(self):
        with self.assertRaises(ValueError):
            dbm.quote_ident("members; DROP TABLE members")
        dbm.init_db()
        self.assertFalse(ops_dbMgmt.drop_table("users; DROP TABLE users"))
        with self._connect() as conn:
            self.assertIsNotNone(
                conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
            )

    def test_executable_sys_path_hack_is_gone(self):
        for relative in ("funcUtils.py", "ftpe.py", "email_utils.py"):
            text = (ROOT / relative).read_text()
            self.assertNotIn("sys.path.append", text)
