"""Password hashing and reset-token tests.

Legacy hashes match the previous scheme: PBKDF2-HMAC-SHA256, 100000
iterations, salt encoded as UTF-8, digest stored as bare hex.
"""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth_utils as au
import db_utils as dbm


def legacy_digest(password, salt, iterations=au.LEGACY_PBKDF2_ITERATIONS):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftpe-auth-")
        self.db_path = os.path.join(self.tmp, "family.db")
        self._previous_db = dbm.database_name
        dbm.database_name = self.db_path
        dbm.init_db()
        self._context = patch("auth_utils.cu.update_context")
        self._context.start()

    def tearDown(self):
        self._context.stop()
        dbm.database_name = self._previous_db
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert_user(self, email, password_hash, salt, role):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (email, password_hash, salt, is_admin, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (email, password_hash, salt, role),
            )
            conn.commit()

    def _user_row(self, email):
        with self._connect() as conn:
            return conn.execute(
                "SELECT password_hash, salt FROM users WHERE email = ?",
                (email,),
            ).fetchone()

    def _insert_reset_token(self, email, stored_token, expires_sql, used=0):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO password_reset_tokens (email, token, expires_at, used)
                VALUES (?, ?, datetime('now', ?), ?)
                """,
                (email, stored_token, expires_sql, used),
            )
            conn.commit()

    def _stored_reset_token(self, email):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT token, used FROM password_reset_tokens WHERE email = ?",
                (email,),
            ).fetchone()
        return row

    def test_legacy_hash_login_and_rehash(self):
        email = "legacy@example.com"
        password = "legacy-secret"
        salt = "a" * 32
        stored = legacy_digest(password, salt)
        self._insert_user(email, stored, salt, dbm.User_State["f_member"])

        self.assertFalse(au.verify_padmin(email, password))
        self.assertFalse(au.verify_fadmin(email, password))
        self.assertTrue(au.verify_fmember(email, password))

        row = self._user_row(email)
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$600000$"))
        self.assertNotEqual(row["password_hash"], stored)
        self.assertNotEqual(row["salt"], salt)

        # A second login uses the upgraded hash and does not rewrite it again.
        upgraded_hash = row["password_hash"]
        upgraded_salt = row["salt"]
        self.assertTrue(au.verify_fmember(email, password))
        row = self._user_row(email)
        self.assertEqual(row["password_hash"], upgraded_hash)
        self.assertEqual(row["salt"], upgraded_salt)

    def test_prefixed_low_iteration_hash_is_rehashed(self):
        email = "old-prefix@example.com"
        password = "prefix-secret"
        salt = "b" * 32
        digest = legacy_digest(password, salt, 100000)
        stored = f"pbkdf2_sha256$100000${digest}"
        self._insert_user(email, stored, salt, dbm.User_State["f_admin"])

        self.assertTrue(au.verify_fadmin(email, password))
        row = self._user_row(email)
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(au.verify_fadmin(email, password))

    def test_new_hash_login(self):
        email = "new@example.com"
        password = "new-secret-value"
        user_id = au.create_user(
            email,
            password,
            role=dbm.User_State["f_member"],
        )
        self.assertIsNotNone(user_id)

        row = self._user_row(email)
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$600000$"))
        self.assertNotIn(password, row["password_hash"])

        self.assertTrue(au.verify_fmember(email, password))
        after = self._user_row(email)
        self.assertEqual(after["password_hash"], row["password_hash"])
        self.assertEqual(after["salt"], row["salt"])

    def test_wrong_password_does_not_rehash(self):
        email = "wrong@example.com"
        password = "correct-secret"
        salt = "c" * 32
        stored = legacy_digest(password, salt)
        self._insert_user(email, stored, salt, dbm.User_State["f_member"])

        self.assertFalse(au.verify_fmember(email, "not-the-password"))
        row = self._user_row(email)
        self.assertEqual(row["password_hash"], stored)
        self.assertEqual(row["salt"], salt)

        self.assertFalse(au.verify_fmember(email, ""))
        self.assertFalse(au.verify_padmin(email, password))

    def test_unknown_hash_format_is_rejected(self):
        email = "bad-hash@example.com"
        self._insert_user(email, "not-a-hash", "d" * 32, dbm.User_State["p_admin"])
        self.assertFalse(au.verify_padmin(email, "anything"))
        row = self._user_row(email)
        self.assertEqual(row["password_hash"], "not-a-hash")

    def test_reset_token_flow(self):
        email = "reset@example.com"
        old_password = "old-password"
        new_password = "new-password"
        au.create_user(email, old_password, role=dbm.User_State["f_member"])
        self.assertTrue(au.verify_fmember(email, old_password))

        token = au.create_password_reset_token(email, expires_hours=2)
        self.assertTrue(token)
        stored = self._stored_reset_token(email)
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored["token"], token)
        self.assertEqual(stored["token"], au.hash_reset_token(token))
        self.assertEqual(stored["used"], 0)

        valid, found = au.validate_password_reset_token(token)
        self.assertTrue(valid)
        self.assertEqual(found, email)
        # The stored digest is not itself a usable token.
        self.assertEqual(
            au.validate_password_reset_token(stored["token"]),
            (False, None),
        )

        self.assertTrue(au.reset_password(email, new_password))
        self.assertEqual(au.validate_password_reset_token(token), (False, None))
        self.assertFalse(au.verify_fmember(email, old_password))
        self.assertTrue(au.verify_fmember(email, new_password))
        upgraded = self._user_row(email)
        self.assertTrue(upgraded["password_hash"].startswith("pbkdf2_sha256$600000$"))

    def test_expired_and_used_tokens_are_rejected(self):
        email = "expired@example.com"
        raw = "raw-reset-token-value"
        self._insert_reset_token(email, au.hash_reset_token(raw), "-1 hours")
        self.assertEqual(au.validate_password_reset_token(raw), (False, None))

        used_email = "used@example.com"
        used_raw = "used-reset-token-value"
        self._insert_reset_token(
            used_email, au.hash_reset_token(used_raw), "+2 hours", used=1
        )
        self.assertEqual(au.validate_password_reset_token(used_raw), (False, None))

    def test_legacy_plaintext_token_still_works_and_is_hashed(self):
        email = "legacy-token@example.com"
        raw = "legacy-plaintext-token"
        self._insert_reset_token(email, raw, "+3 hours")

        valid, found = au.validate_password_reset_token(raw)
        self.assertTrue(valid)
        self.assertEqual(found, email)
        stored = self._stored_reset_token(email)
        self.assertEqual(stored["token"], au.hash_reset_token(raw))
        self.assertNotEqual(stored["token"], raw)

        # Still valid after the in-place upgrade, until it is used or expires.
        self.assertEqual(au.validate_password_reset_token(raw), (True, email))
        au.delete_password_reset_token(raw)
        self.assertIsNone(self._stored_reset_token(email))
        self.assertEqual(au.validate_password_reset_token(raw), (False, None))

    def test_migration_hashes_existing_plaintext_tokens(self):
        email = "migrate@example.com"
        raw = "token-already-emailed"
        self._insert_reset_token(email, raw, "+5 hours")
        expired_email = "migrate-expired@example.com"
        expired_raw = "expired-plaintext"
        self._insert_reset_token(expired_email, expired_raw, "-2 hours")

        with self._connect() as conn:
            updated = dbm.migrate_plaintext_reset_tokens(conn)
            conn.commit()
        self.assertEqual(updated, 2)

        self.assertEqual(
            self._stored_reset_token(email)["token"],
            au.hash_reset_token(raw),
        )
        self.assertEqual(au.validate_password_reset_token(raw), (True, email))
        self.assertEqual(
            au.validate_password_reset_token(expired_raw),
            (False, None),
        )

        with self._connect() as conn:
            again = dbm.migrate_plaintext_reset_tokens(conn)
            conn.commit()
        self.assertEqual(again, 0)
        # Presenting the stored digest still does not authenticate.
        stored = self._stored_reset_token(email)["token"]
        self.assertEqual(au.validate_password_reset_token(stored), (False, None))
        au.delete_password_reset_token(stored)
        self.assertIsNotNone(self._stored_reset_token(email))


if __name__ == "__main__":
    unittest.main()
