"""Family-gated subscription.

Run from the repo root:

    python -m unittest tests.test_family_subscribe_smoke -v

The file name starts with ``test_`` so ``unittest discover`` runs it in CI.

Membership is the users row's family_id. The process refuses to start
when no family id is configured. Email matching in this flow is
case-insensitive. Article reads and writes stay inside that family.
"""

import contextlib
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="subs-family-")
_DB = str(Path(_TMP) / "users.db")
os.environ["DB_NAME"] = _DB
os.environ["L10N"] = "繁中"
os.environ["FLASK_SECRET_KEY"] = "family-subscribe-smoke"
os.environ["LOGGING"] = "ERROR"
os.environ["FAMILY_ID"] = "1"
os.environ.pop("DB_ADMIN", None)

import db_utils  # noqa: E402
# Discover imports db_utils before this module, so the env var alone is too late.
db_utils.database_name = _DB
import email_utils  # noqa: E402
import nav  # noqa: E402
import ops_svr  # noqa: E402

BASE = "https://localhost"
FAMILY = 1
NEXT_STEP = "Please check {email} for the next step."
NEXT_STEP_ZH = "請查看 {email} 以完成下一步。"
SEND_FAILED = "Failed to send email. Please try again later."
def _alerts(body):
    """Flash text shown on the page after a redirect."""
    found = re.findall(r'role="alert">\s*(.*?)\s*<button', body, flags=re.S)
    return [re.sub(r"\s+", " ", item).strip() for item in found]


def _insert_user(email, family_id, is_active=0, token=None, l10n="US"):
    with db_utils.get_db_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO {db_utils.db_tables['users']}
                (email, is_active, l10n, token, family_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, is_active, l10n, token, family_id),
        )
        conn.commit()


def _user(email):
    return db_utils.get_subscriber(email)


def _count_users():
    with db_utils.get_db_connection() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM {db_utils.db_tables['users']}"
        ).fetchone()[0]


def _count_articles():
    with db_utils.get_db_connection() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM {db_utils.db_tables['articles']}"
        ).fetchone()[0]


class FamilySubscribeSmokeTest(unittest.TestCase):
    def setUp(self):
        self._csrf = ops_svr.app.config.get("WTF_CSRF_ENABLED", True)
        self._family_env = os.environ.get("FAMILY_ID")
        ops_svr.app.config["WTF_CSRF_ENABLED"] = False
        os.environ["FAMILY_ID"] = str(FAMILY)
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        with db_utils.get_db_connection() as conn:
            conn.execute(f"DELETE FROM {db_utils.db_tables['users']}")
            conn.execute(f"DELETE FROM {db_utils.db_tables['articles']}")
            conn.commit()

    def tearDown(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        ops_svr.app.config["WTF_CSRF_ENABLED"] = self._csrf
        if self._family_env is None:
            os.environ.pop("FAMILY_ID", None)
        else:
            os.environ["FAMILY_ID"] = self._family_env
        os.environ.pop("DB_ADMIN", None)

    def _post(self, email, action="subscribe", lang="US"):
        client = ops_svr.app.test_client()
        with client.session_transaction() as sess:
            sess["current_lang"] = lang
        return client.post(
            "/subscribe",
            data={"email": email, "action": action},
            base_url=BASE,
            follow_redirects=True,
        )

    def test_parser_reads_family_id_and_cli_overrides_env(self):
        parser = ops_svr.build_parser()
        specified = parser.parse_args(["--family_id", "12", "--dev"])
        self.assertEqual(specified.family_id, "12")
        self.assertTrue(specified.dev)
        omitted = parser.parse_args([])
        self.assertIsNone(omitted.family_id)
        self.assertFalse(omitted.dev)
        self.assertEqual(ops_svr.cli_family_id(["--dev", "--family_id", "12"]), "12")
        self.assertEqual(ops_svr.cli_family_id(["--family_id=12"]), "12")
        self.assertIsNone(ops_svr.cli_family_id(["--dev"]))

        os.environ["FAMILY_ID"] = "4"
        self.assertEqual(ops_svr.configure_family_id(None), 4)
        self.assertEqual(ops_svr.configure_family_id("  12  "), 12)
        self.assertEqual(ops_svr.app.config["FAMILY_ID"], 12)
        self.assertEqual(ops_svr.configure_family_id("   "), 4)
        with self.assertRaises(SystemExit) as bad:
            ops_svr.configure_family_id("kao")
        self.assertIn("numeric", str(bad.exception).lower())
        self.assertNotEqual(getattr(bad.exception, "code", 1), 0)
        self.assertIsNone(ops_svr.active_family_id())

    def test_blank_family_id_refuses_to_start(self):
        os.environ["FAMILY_ID"] = "   "
        with self.assertRaises(SystemExit) as blank_env:
            ops_svr.configure_family_id(None)
        self.assertIn("requires a family id", str(blank_env.exception))
        self.assertIsNone(ops_svr.active_family_id())

        os.environ.pop("FAMILY_ID", None)
        with patch.object(ops_svr.app, "run") as run:
            with self.assertRaises(SystemExit) as missing:
                ops_svr.main([])
            run.assert_not_called()
        self.assertIn("FAMILY_ID", str(missing.exception))
        self.assertIn("--family_id", str(missing.exception))

    def test_legacy_article_table_gains_family_id_without_rewriting_rows(self):
        legacy_dir = tempfile.mkdtemp(prefix="ftrees-legacy-article-")
        legacy = str(Path(legacy_dir) / "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.execute(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'News',
                is_censored INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO articles (title, content, category) VALUES ('Keep me', 'Body', 'News')"
        )
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 0
            )
            """
        )
        conn.execute("INSERT INTO users (email, is_active) VALUES ('old@example.com', 1)")
        conn.commit()
        conn.close()

        previous = db_utils.database_name
        db_utils.database_name = legacy
        try:
            db_utils.init_db()
            db_utils.init_db()
            with db_utils.get_db_connection() as conn:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(articles)")]
                article = conn.execute(
                    "SELECT title, content, family_id FROM articles WHERE title = 'Keep me'"
                ).fetchone()
                user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
                user = conn.execute(
                    "SELECT email, family_id FROM users WHERE email = 'old@example.com'"
                ).fetchone()
                members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            self.assertIn("family_id", columns)
            self.assertEqual(article["title"], "Keep me")
            self.assertEqual(article["content"], "Body")
            self.assertEqual(article["family_id"], 1)
            self.assertIn("family_id", user_columns)
            self.assertEqual(user["email"], "old@example.com")
            self.assertIsNone(user["family_id"])
            self.assertEqual(members, 0)
        finally:
            db_utils.database_name = previous

    def test_membership_is_family_id_on_the_user_row(self):
        _insert_user("member@example.com", 1)
        _insert_user("other@example.com", 2)
        _insert_user("blank@example.com", None)
        _insert_user("numbered@example.com", 12)
        self.assertTrue(db_utils.is_family_member("member@example.com", 1))
        self.assertTrue(db_utils.is_family_member("  MEMBER@example.com ", "1"))
        self.assertTrue(db_utils.is_family_member("member@example.com", " 1 "))
        self.assertFalse(db_utils.is_family_member("member@example.com", "Fam-1"))
        self.assertFalse(db_utils.is_family_member("other@example.com", 1))
        self.assertFalse(db_utils.is_family_member("blank@example.com", 1))
        self.assertFalse(db_utils.is_family_member("missing@example.com", 1))
        self.assertFalse(db_utils.is_family_member("member@example.com", None))
        self.assertFalse(db_utils.is_family_member("member@example.com", "  "))
        self.assertTrue(db_utils.is_family_member("numbered@example.com", "12"))
        self.assertTrue(db_utils.is_family_member("numbered@example.com", "012"))

        user = _user("blank@example.com")
        self.assertEqual(db_utils.update_user(user["id"], {"family_id": 1}), user["id"])
        self.assertTrue(db_utils.is_family_member("blank@example.com", 1))

    def test_gated_member_and_non_member_see_the_same_page(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        os.environ["DB_ADMIN"] = "admin@example.com"
        _insert_user("member@example.com", FAMILY, token="keep-me")
        _insert_user("other@example.com", 2, is_active=1, token="leave-me")

        with patch.object(ops_svr.eu, "send_verification_email", return_value=True) as verify, \
             patch.object(ops_svr.eu, "send_membership_instruction_email", return_value=True) as instruction:
            member = self._post("member@example.com")
            other = self._post("other@example.com")
            stranger = self._post("stranger@example.com")

        self.assertEqual(member.status_code, 200)
        self.assertEqual(other.status_code, 200)
        self.assertEqual(stranger.status_code, 200)
        member_alerts = _alerts(member.get_data(as_text=True))
        other_alerts = _alerts(other.get_data(as_text=True))
        stranger_alerts = _alerts(stranger.get_data(as_text=True))
        self.assertEqual(member_alerts, [NEXT_STEP.format(email="member@example.com")])
        self.assertEqual(
            [item.replace("member@example.com", "ADDR") for item in member_alerts],
            [item.replace("other@example.com", "ADDR") for item in other_alerts],
        )
        self.assertEqual(
            [item.replace("other@example.com", "ADDR") for item in other_alerts],
            [item.replace("stranger@example.com", "ADDR") for item in stranger_alerts],
        )
        for alerts in (member_alerts, other_alerts, stranger_alerts):
            text = " ".join(alerts)
            self.assertNotIn("confirm subscription", text)
            self.assertNotIn("not registered", text)
            self.assertNotIn("尚未登記", text)
            self.assertNotIn("personal information", text)

        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.args[1], "member@example.com")
        self.assertTrue(verify.call_args.kwargs["is_subscribe"])
        self.assertEqual(instruction.call_count, 2)
        instructed = {call.args[1] for call in instruction.call_args_list}
        self.assertEqual(instructed, {"other@example.com", "stranger@example.com"})
        for call in instruction.call_args_list:
            self.assertEqual(call.kwargs["admin_email"], "admin@example.com")

        member_row = _user("member@example.com")
        self.assertEqual(member_row["is_active"], db_utils.Subscriber_State["pending"])
        self.assertEqual(member_row["family_id"], FAMILY)
        self.assertNotEqual(member_row["token"], "keep-me")

        other_row = _user("other@example.com")
        self.assertEqual(other_row["is_active"], 1)
        self.assertEqual(other_row["token"], "leave-me")
        self.assertEqual(other_row["family_id"], 2)
        self.assertIsNone(_user("stranger@example.com"))

    def test_gated_failure_page_is_the_same_for_member_and_stranger(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        _insert_user("member@example.com", FAMILY)
        with patch.object(ops_svr.eu, "send_verification_email", return_value=False), \
             patch.object(ops_svr.eu, "send_membership_instruction_email", return_value=False):
            member = self._post("member@example.com")
            stranger = self._post("stranger@example.com")
        member_alerts = _alerts(member.get_data(as_text=True))
        stranger_alerts = _alerts(stranger.get_data(as_text=True))
        self.assertEqual(member_alerts, [SEND_FAILED])
        self.assertEqual(member_alerts, stranger_alerts)
        self.assertEqual(_user("member@example.com")["is_active"], 0)
        self.assertIsNone(_user("stranger@example.com"))

    def test_gated_page_follows_the_request_language(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        _insert_user("member@example.com", FAMILY)
        with patch.object(ops_svr.eu, "send_verification_email", return_value=True), \
             patch.object(ops_svr.eu, "send_membership_instruction_email", return_value=True):
            member = self._post("member@example.com", lang="繁中")
            stranger = self._post("stranger@example.com", lang="繁中")
        member_alerts = _alerts(member.get_data(as_text=True))
        stranger_alerts = _alerts(stranger.get_data(as_text=True))
        self.assertEqual(member_alerts, [NEXT_STEP_ZH.format(email="member@example.com")])
        self.assertEqual(
            [item.replace("member@example.com", "ADDR") for item in member_alerts],
            [item.replace("stranger@example.com", "ADDR") for item in stranger_alerts],
        )

    def test_subscribe_matches_email_case_insensitively(self):
        _insert_user("Member@Example.com", FAMILY, token="old-token")
        with patch.object(ops_svr.eu, "send_verification_email", return_value=True) as verify, \
             patch.object(ops_svr.eu, "send_membership_instruction_email", return_value=True) as instruction:
            response = self._post("  Member@Example.COM ")
        alerts = _alerts(response.get_data(as_text=True))
        self.assertEqual(alerts, [NEXT_STEP.format(email="member@example.com")])
        self.assertEqual(verify.call_args.args[1], "member@example.com")
        instruction.assert_not_called()
        row = _user("member@example.com")
        self.assertEqual(row["email"], "member@example.com")
        self.assertEqual(row["family_id"], FAMILY)
        self.assertEqual(row["is_active"], db_utils.Subscriber_State["pending"])
        self.assertEqual(_count_users(), 1)

        _insert_user("Other@Example.com", 2)
        found = _user("other@example.com")
        self.assertEqual(found["email"], "Other@Example.com")
        _insert_user("other@example.com", FAMILY)
        preferred = _user("OTHER@example.com")
        self.assertEqual(preferred["email"], "other@example.com")
        self.assertTrue(db_utils.is_family_member("OTHER@example.com", FAMILY))

    def test_invalid_email_does_not_send_or_lookup_membership(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        with patch.object(ops_svr.eu, "send_verification_email") as verify, \
             patch.object(ops_svr.eu, "send_membership_instruction_email") as instruction, \
             patch.object(db_utils, "is_family_member") as membership:
            response = self._post("not-an-email")
        self.assertIn("not-an-email is not a valid email address", response.get_data(as_text=True))
        verify.assert_not_called()
        instruction.assert_not_called()
        membership.assert_not_called()

    def test_unsubscribe_does_not_require_membership(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        with patch.object(ops_svr.eu, "send_verification_email", return_value=True) as verify, \
             patch.object(ops_svr.eu, "send_membership_instruction_email") as instruction:
            response = self._post(" Stranger@Example.com ", action="unsubscribe")
        self.assertIn(
            "Please check stranger@example.com to confirm unsubscription.",
            response.get_data(as_text=True),
        )
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.args[1], "stranger@example.com")
        self.assertFalse(verify.call_args.kwargs["is_subscribe"])
        instruction.assert_not_called()
        self.assertIsNone(_user("stranger@example.com"))

    def test_instruction_email_is_bilingual(self):
        captured = {}

        def fake_send(mail, msg, max_retries=3):
            captured["subject"] = str(msg.subject)
            captured["html"] = msg.html
            captured["to"] = list(msg.recipients)
            return True

        with patch.object(email_utils, "_send_mail", fake_send):
            with ops_svr.app.app_context():
                sent = email_utils.send_membership_instruction_email(
                    ops_svr.g_fmail,
                    "person@example.com",
                    admin_email="admin@example.com",
                )
        self.assertTrue(sent)
        self.assertEqual(captured["to"], ["person@example.com"])
        self.assertIn("請先向家族管理員登記後再訂閱", captured["subject"])
        self.assertIn("Register with your family Admin before subscribing", captured["subject"])
        html = captured["html"]
        self.assertIn('lang="zh-Hant"', html)
        self.assertIn('lang="en"', html)
        self.assertIn("個人資料", html)
        self.assertIn("personal information", html)
        self.assertIn("person@example.com", html)
        self.assertIn("admin@example.com", html)
        self.assertIn("mailto:admin@example.com", html)

    def test_verify_activates_a_member_and_blocks_anyone_else(self):
        ops_svr.app.config["FAMILY_ID"] = FAMILY
        _insert_user("member@example.com", FAMILY, token="good-token")
        _insert_user("other@example.com", 2, token="other-token", is_active=-1)

        client = ops_svr.app.test_client()
        with client.session_transaction() as sess:
            sess["current_lang"] = "US"
        ok = client.get(
            "/verify-email",
            query_string={"email": "member@example.com", "token": "good-token", "action": "subscribe"},
            base_url=BASE,
            follow_redirects=True,
        )
        self.assertIn("successfully subscribed", ok.get_data(as_text=True))
        self.assertEqual(_user("member@example.com")["is_active"], db_utils.Subscriber_State["active"])

        blocked = client.get(
            "/verify-email",
            query_string={"email": "other@example.com", "token": "other-token", "action": "subscribe"},
            base_url=BASE,
            follow_redirects=True,
        )
        blocked_body = blocked.get_data(as_text=True)
        self.assertIn("could not be completed", blocked_body)
        self.assertNotIn("successfully subscribed", blocked_body)
        other = _user("other@example.com")
        self.assertEqual(other["is_active"], -1)
        self.assertEqual(other["token"], "other-token")

    def test_verify_matches_case_and_missing_family_does_not_activate(self):
        _insert_user("Member@Example.com", FAMILY, token="good-token")
        client = ops_svr.app.test_client()
        ok = client.get(
            "/verify-email",
            query_string={"email": " member@example.com ", "token": "good-token", "action": "subscribe"},
            base_url=BASE,
            follow_redirects=True,
        )
        self.assertIn("successfully subscribed", ok.get_data(as_text=True))
        activated = _user("member@example.com")
        self.assertEqual(activated["is_active"], db_utils.Subscriber_State["active"])
        self.assertEqual(activated["email"], "member@example.com")

        ops_svr.app.config["FAMILY_ID"] = None
        _insert_user("legacy@example.com", None, token="legacy-token")
        blocked_client = ops_svr.app.test_client()
        with blocked_client.session_transaction() as sess:
            sess["current_lang"] = "US"
        blocked = blocked_client.get(
            "/verify-email",
            query_string={"email": "legacy@example.com", "token": "legacy-token", "action": "subscribe"},
            base_url=BASE,
            follow_redirects=True,
        )
        self.assertIn("could not be completed", blocked.get_data(as_text=True))
        legacy = _user("legacy@example.com")
        self.assertNotEqual(legacy["is_active"], db_utils.Subscriber_State["active"])
        self.assertEqual(legacy["token"], "legacy-token")

    def test_feedback_is_member_only_and_hides_membership(self):
        os.environ["DB_ADMIN"] = "admin@example.com"
        _insert_user("Member@Example.com", FAMILY, is_active=0, token="pending-token")
        _insert_user("other@example.com", 2, is_active=1, token="leave-me")
        before = _count_users()

        with patch.object(ops_svr.eu, "send_verification_email", return_value=True) as verify, \
             patch.object(ops_svr.eu, "send_membership_instruction_email", return_value=True) as instruction, \
             patch.object(ops_svr.eu, "send_email", return_value=True):
            pending = self._post_feedback(" member@example.com ")
            stranger = self._post_feedback("stranger@example.com")
            other = self._post_feedback("Other@Example.com")

        pending_alerts = _alerts(pending.get_data(as_text=True))
        stranger_alerts = _alerts(stranger.get_data(as_text=True))
        other_alerts = _alerts(other.get_data(as_text=True))
        self.assertEqual(pending_alerts, [NEXT_STEP.format(email="member@example.com")])
        self.assertEqual(
            [item.replace("member@example.com", "ADDR") for item in pending_alerts],
            [item.replace("stranger@example.com", "ADDR") for item in stranger_alerts],
        )
        self.assertEqual(
            [item.replace("stranger@example.com", "ADDR") for item in stranger_alerts],
            [item.replace("other@example.com", "ADDR") for item in other_alerts],
        )
        for alerts in (pending_alerts, stranger_alerts, other_alerts):
            text = " ".join(alerts)
            self.assertNotIn("Submitted successfully", text)
            self.assertNotIn("not registered", text)
            self.assertNotIn("尚未登記", text)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.args[1], "member@example.com")
        instructed = {call.args[1] for call in instruction.call_args_list}
        self.assertEqual(instructed, {"stranger@example.com", "other@example.com"})
        self.assertEqual(_count_users(), before)
        self.assertIsNone(_user("stranger@example.com"))
        other_row = _user("other@example.com")
        self.assertEqual(other_row["token"], "leave-me")
        self.assertEqual(other_row["family_id"], 2)
        self.assertEqual(_count_articles(), 0)

        _insert_user("writer@example.com", FAMILY, is_active=db_utils.Subscriber_State["active"])
        with patch.object(ops_svr.eu, "send_verification_email") as verify_again, \
             patch.object(ops_svr.eu, "send_membership_instruction_email") as instruction_again, \
             patch.object(ops_svr.eu, "send_email", return_value=True):
            accepted = self._post_feedback(" Writer@Example.com ")
        accepted_body = accepted.get_data(as_text=True)
        self.assertRegex(accepted_body, r"Ticket:\d+")
        with db_utils.get_db_connection() as conn:
            stored_family = conn.execute(
                f"SELECT family_id FROM {db_utils.db_tables['articles']}"
            ).fetchone()
        self.assertEqual(stored_family["family_id"], FAMILY)
        self.assertIn("submitted for review", accepted_body)
        verify_again.assert_not_called()
        instruction_again.assert_not_called()
        self.assertEqual(_count_articles(), 1)
        self.assertEqual(_user("writer@example.com")["email"], "writer@example.com")

    def _post_feedback(self, email, lang="US"):
        client = ops_svr.app.test_client()
        with client.session_transaction() as sess:
            sess["current_lang"] = lang
        page = client.get("/feedback", base_url=BASE)
        html = page.get_data(as_text=True)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        if token is None:
            token = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
        self.assertIsNotNone(token)
        return client.post(
            "/feedback",
            data={
                "title": "Family picnic notes",
                "content": "A note long enough to pass the feedback form.",
                "l10n": lang,
                "author": "Ada",
                "source": "Letter",
                "email": email,
                "csrf_token": token.group(1),
            },
            base_url=BASE,
            follow_redirects=True,
        )


    def test_article_reads_and_writes_stay_inside_one_family(self):
        ours = db_utils.add_or_update_article({
            "title": "Our family news",
            "content": "Visible to this family only.",
            "category": "News",
            "author": "Ada",
            "source": "Letter",
            "l10n": "US",
            "is_censored": db_utils.Article_State["approved"],
            "family_id": 1,
        })
        other = db_utils.add_or_update_article({
            "title": "Other family news",
            "content": "Must stay hidden.",
            "category": "News",
            "author": "Bea",
            "source": "Letter",
            "l10n": "US",
            "is_censored": db_utils.Article_State["approved"],
            "family_id": 2,
        })
        self.assertIsNotNone(ours)
        self.assertIsNotNone(other)
        found = db_utils.get_articles("News", family_id=1)
        self.assertEqual([row["title"] for row in found], ["Our family news"])
        self.assertIn("family_id", found[0])
        self.assertEqual(found[0]["family_id"], 1)
        everyone = db_utils.get_articles("News", all_families=True)
        self.assertEqual(
            sorted(row["title"] for row in everyone),
            ["Other family news", "Our family news"],
        )
        self.assertIsNone(db_utils.get_article_byId(other, family_id=1))
        self.assertFalse(db_utils.delete_article(ours, family_id=2))
        self.assertEqual(db_utils.get_article_byId(ours, family_id=1)["title"], "Our family news")

        ops_svr.app.config["FAMILY_ID"] = 1
        ops_svr.init_globals()
        client = ops_svr.app.test_client()
        with client.session_transaction() as sess:
            sess["current_lang"] = "US"
        home = client.get("/", base_url=BASE)
        body = home.get_data(as_text=True)
        self.assertIn("Our family news", body)
        self.assertNotIn("Other family news", body)

        self.assertTrue(db_utils.delete_article(ours, family_id=1))
        self.assertIsNone(db_utils.get_article_byId(ours, family_id=1))
        self.assertEqual(db_utils.get_article_byId(other, family_id=2)["title"], "Other family news")

    def test_article_page_is_open_to_platform_and_family_admins(self):
        allowed = (db_utils.User_State["p_admin"], db_utils.User_State["f_admin"])
        self.assertEqual(nav.role_is_allowed(True, db_utils.User_State["f_admin"], allowed), "ok")
        self.assertEqual(nav.role_is_allowed(True, db_utils.User_State["p_admin"], allowed), "ok")
        self.assertEqual(nav.role_is_allowed(True, db_utils.User_State["f_member"], allowed), "denied")
        self.assertEqual(nav.role_is_allowed(False, db_utils.User_State["f_admin"], allowed), "login")
        admin_pages = [item["page"] for item in nav.navigation_links(db_utils.User_State["f_admin"])]
        member_pages = [item["page"] for item in nav.navigation_links(db_utils.User_State["f_member"])]
        platform_pages = [item["page"] for item in nav.navigation_links(db_utils.User_State["p_admin"])]
        self.assertIn("pages/5_artMgmt.py", admin_pages)
        self.assertIn("pages/5_artMgmt.py", platform_pages)
        self.assertNotIn("pages/5_artMgmt.py", member_pages)
        source = (ROOT / "pages" / "5_artMgmt.py").read_text(encoding="utf-8")
        self.assertIn("require_role", source)
        self.assertIn("render_sidebar", source)
        self.assertIn("Current family_id", source)
        self.assertIn("All families", source)
        self.assertIn("create_article_family_id", source)
        self.assertIn('User_State["f_admin"]', source)
        self.assertIn('User_State["p_admin"]', source)
        self.assertNotIn('User_State["f_member"]', source)
        platform = db_utils.User_State["p_admin"]
        wide = db_utils.article_access_scope(platform, 0, platform_admin=platform, filter_all=True)
        self.assertEqual(wide, {"family_id": None, "all_families": True})
        picked = db_utils.article_access_scope(
            platform, 0, platform_admin=platform, filter_all=False, filter_family_id="4",
        )
        self.assertEqual(picked, {"family_id": 4, "all_families": False})
        family = db_utils.article_access_scope(
            db_utils.User_State["f_admin"], 3, platform_admin=platform, filter_all=True, filter_family_id=9,
        )
        self.assertEqual(family, {"family_id": 3, "all_families": False})
        self.assertEqual(cu_family(None), None)
        self.assertEqual(cu_family({"family_id": 7}), 7)

    def test_feedback_update_keeps_the_server_family(self):
        _insert_user("writer@example.com", FAMILY, is_active=db_utils.Subscriber_State["active"])
        created = db_utils.add_or_update_article({
            "title": "Family picnic notes",
            "content": "A note long enough to pass the feedback form.",
            "category": "News",
            "author": "Ada",
            "source": "Letter",
            "l10n": "US",
            "is_censored": db_utils.Article_State["approved"],
            "family_id": FAMILY,
        })
        updated = db_utils.add_or_update_article({
            "title": "Family picnic notes",
            "content": "Updated for this family.",
            "category": "Feedback",
            "author": "Ada",
            "source": "Letter",
            "family_id": "2",
        }, update=True, family_id=FAMILY)
        self.assertEqual(updated, created)
        row = db_utils.get_article_byId(created, family_id=FAMILY)
        self.assertEqual(row["content"], "Updated for this family.")
        self.assertEqual(row["family_id"], FAMILY)
        self.assertIsNone(db_utils.get_article_byId(created, family_id=2))


    def test_non_numeric_family_id_refuses_to_start(self):
        env = os.environ.copy()
        env["FAMILY_ID"] = "kao"
        env["LOGGING"] = "ERROR"
        proc = subprocess.run(
            [sys.executable, "ops_svr.py", "--family_id", "fam-1"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("numeric", (proc.stderr + proc.stdout).lower())

        env.pop("FAMILY_ID", None)
        blank = subprocess.run(
            [sys.executable, "ops_svr.py"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(blank.returncode, 0)
        self.assertIn("family id", (blank.stderr + blank.stdout).lower())

    def test_batch_editor_filter_is_one_integer_family(self):
        import ops_artBatch

        self.assertEqual(ops_artBatch.article_family_filter(2), "family_id = 2")
        self.assertEqual(ops_artBatch.article_family_filter(" 02 "), "family_id = 2")
        with self.assertRaises(ValueError):
            ops_artBatch.article_family_filter("fam-1")
        parser = ops_artBatch.build_parser()
        self.assertEqual(parser.parse_args(["--family-id", "7"]).family_id, "7")
        with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
            with self.assertRaises(SystemExit):
                parser.parse_args([])
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
        direct = project.split("[project.optional-dependencies]", 1)[0]
        self.assertNotIn("pyqt", direct)
        self.assertIn("pyqt5", project)
        self.assertNotIn("pyqt", (ROOT / "requirements.txt").read_text(encoding="utf-8").lower())


def cu_family(value):
    import context_utils
    return context_utils.current_family_id({} if value is None else value)


if __name__ == "__main__":
    unittest.main()
