"""Newsletter role gate, member-only subscribe, and home-page snapshot.

Run from the repo root:

    python -m unittest tests.test_newsletter -v

Snapshots are rendered through ops_svr or a stand-in fetcher. These tests
never open an SMTP connection.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("FAMILY_ID", "1")
os.environ.setdefault("FLASK_SECRET_KEY", "newsletter-test")
os.environ.setdefault("LOGGING", "ERROR")
os.environ.setdefault("L10N", "US")

import auth_utils as au
import db_utils as dbm
import nav
import newsletter_publish as nl
import ops_svr

BASE = "https://localhost"
NOT_MEMBER = "This email is not a registered member of this family."
NOT_MEMBER_ZH = "此電子郵件不是本家族的已登記成員。"


def _insert_user(email, family_id, is_active=0, token="", l10n="US", is_admin=0):
    with dbm.get_db_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO {dbm.db_tables['users']}
                (email, is_active, l10n, token, family_id, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, is_active, l10n, token, family_id, is_admin),
        )
        conn.commit()


def _insert_admin(email, role, family_id, password="secret"):
    stored, salt = au.hash_password(password, iterations=1000)
    with dbm.get_db_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO {dbm.db_tables['users']}
                (email, password_hash, salt, is_admin, is_active, l10n, family_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email, stored, salt, role, dbm.Subscriber_State["inactive"], "US", family_id),
        )
        conn.commit()


def _article(title, family_id, category="News", l10n="US", approved=True, content=None, **extra):
    payload = {
        "title": title,
        "content": content or f"Body of {title}",
        "category": category,
        "author": "Ada",
        "source": "Letter",
        "l10n": l10n,
        "is_censored": dbm.Article_State["approved"] if approved else dbm.Article_State["pending"],
    }
    payload.update(extra)
    return dbm.add_or_update_article(payload, family_id=family_id)


class NewsletterAccessTests(unittest.TestCase):
    def test_sidebar_and_direct_page_follow_admin_roles(self):
        allowed = (dbm.User_State["p_admin"], dbm.User_State["f_admin"])
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["p_admin"], allowed), "ok")
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["f_admin"], allowed), "ok")
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["f_member"], allowed), "denied")
        self.assertEqual(nav.role_is_allowed(False, dbm.User_State["f_admin"], allowed), "login")

        member_pages = [item["page"] for item in nav.navigation_links(dbm.User_State["f_member"])]
        admin_pages = [item["page"] for item in nav.navigation_links(dbm.User_State["f_admin"])]
        platform_pages = [item["page"] for item in nav.navigation_links(dbm.User_State["p_admin"])]
        self.assertNotIn("pages/10_newsletter.py", member_pages)
        self.assertIn("pages/10_newsletter.py", admin_pages)
        self.assertIn("pages/10_newsletter.py", platform_pages)

        source = (ROOT / "pages" / "10_newsletter.py").read_text(encoding="utf-8")
        self.assertIn("require_role", source)
        self.assertIn("render_sidebar", source)
        self.assertIn('User_State["p_admin"]', source)
        self.assertIn('User_State["f_admin"]', source)
        self.assertNotIn('User_State["f_member"]', source)
        self.assertNotIn("show_padmin_sidebar", source)
        self.assertNotIn("/pub?", source)
        self.assertNotIn("1_usrMgmt.py", source)
        self.assertLess(source.index('key="newsletter_family_id"'), source.index('key="newsletter_language"'))
        self.assertLess(
            source.index('key="newsletter_family_id_locked"'),
            source.index('key="newsletter_language"'),
        )
        self.assertIn("disabled=True", source)
        self.assertIn("selected_family_id", source)
        self.assertIn("list_family_subscribers", source)
        self.assertIn("add_family_subscriber", source)
        self.assertIn("build_snapshot", source)

    def test_family_admin_cannot_pick_another_family(self):
        platform = dbm.User_State["p_admin"]
        family = dbm.User_State["f_admin"]
        self.assertEqual(nl.selected_family_id(platform, 1, "04"), 4)
        self.assertEqual(nl.selected_family_id(platform, 1, 2), 2)
        self.assertEqual(nl.selected_family_id(family, 3, 9), 3)
        self.assertEqual(nl.selected_family_id(family, " 03 ", 9), 3)
        self.assertIsNone(nl.selected_family_id(family, None, 9))
        with self.assertRaises(PermissionError):
            nl.selected_family_id(dbm.User_State["f_member"], 3, 3)
        with self.assertRaises(ValueError):
            nl.selected_family_id(platform, 1, "fam-1")

    def test_not_member_copy_is_bilingual(self):
        self.assertIn(NOT_MEMBER, nl.NOT_MEMBER_MESSAGE)
        self.assertIn(NOT_MEMBER_ZH, nl.NOT_MEMBER_MESSAGE)
        for name in ("L10N_US.json", "L10N_TW.json"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(NOT_MEMBER, text)
            self.assertIn(NOT_MEMBER_ZH, text)


class NewsletterFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftrees-newsletter-")
        self.db_path = os.path.join(self.tmp, "family.db")
        self._previous_db = dbm.database_name
        self._family = ops_svr.app.config.get("FAMILY_ID")
        self._csrf = ops_svr.app.config.get("WTF_CSRF_ENABLED", True)
        self._window = os.environ.get("ARTICLE_WINDOW")
        dbm.database_name = self.db_path
        dbm.init_db()
        ops_svr.app.config["FAMILY_ID"] = 1
        ops_svr.app.config["WTF_CSRF_ENABLED"] = False
        os.environ["ARTICLE_WINDOW"] = "7"
        with dbm.get_db_connection() as conn:
            conn.execute(f"DELETE FROM {dbm.db_tables['users']}")
            conn.execute(f"DELETE FROM {dbm.db_tables['articles']}")
            conn.commit()

    def tearDown(self):
        dbm.database_name = self._previous_db
        ops_svr.app.config["FAMILY_ID"] = self._family
        ops_svr.app.config["WTF_CSRF_ENABLED"] = self._csrf
        if self._window is None:
            os.environ.pop("ARTICLE_WINDOW", None)
        else:
            os.environ["ARTICLE_WINDOW"] = self._window

    def _seed_people(self):
        _insert_user("Member@Example.com", 1, is_active=dbm.Subscriber_State["pending"], token="keep")
        _insert_user("quiet@example.com", 1, is_active=dbm.Subscriber_State["inactive"])
        _insert_user("active.one@example.com", 1, is_active=dbm.Subscriber_State["active"], l10n="US")
        _insert_user("active.two@example.com", 2, is_active=dbm.Subscriber_State["active"], l10n="US")
        _insert_user("waiting@example.com", 1, is_active=dbm.Subscriber_State["pending"])

    def test_add_accepts_only_a_member_of_the_selected_family(self):
        self._seed_people()
        before = self._count_users()
        added = nl.add_family_subscriber("  MEMBER@example.com ", 1, "US")
        self.assertTrue(added["ok"])
        self.assertEqual(added["email"], "member@example.com")
        row = dbm.get_subscriber("member@example.com")
        self.assertEqual(row["is_active"], dbm.Subscriber_State["active"])
        self.assertEqual(row["family_id"], 1)
        self.assertEqual(row["is_admin"], 0)
        self.assertEqual(row["token"], "")
        self.assertEqual(self._count_users(), before)

        other = nl.add_family_subscriber("active.two@example.com", 1, "US")
        self.assertFalse(other["ok"])
        self.assertEqual(other["reason"], "not_member")
        self.assertIn(NOT_MEMBER, nl.NOT_MEMBER_MESSAGE)
        untouched = dbm.get_subscriber("active.two@example.com")
        self.assertEqual(untouched["family_id"], 2)
        self.assertEqual(untouched["is_active"], dbm.Subscriber_State["active"])

        stranger = nl.add_family_subscriber("stranger@example.com", 1, "US")
        self.assertFalse(stranger["ok"])
        self.assertEqual(stranger["reason"], "not_member")
        self.assertIsNone(dbm.get_subscriber("stranger@example.com"))
        self.assertEqual(self._count_users(), before)

        invalid = nl.add_family_subscriber("not-an-email", 1, "US")
        self.assertEqual(invalid["reason"], "invalid_email")
        self.assertEqual(self._count_users(), before)

    def test_unsubscribe_and_listing_stay_inside_the_family(self):
        self._seed_people()
        listed = [row["email"] for row in dbm.list_family_subscribers(1)]
        self.assertEqual(
            listed,
            ["active.one@example.com", "Member@Example.com", "quiet@example.com", "waiting@example.com"],
        )
        self.assertNotIn("active.two@example.com", listed)
        self.assertEqual(
            [row["email"] for row in dbm.list_family_subscribers(1, state="active")],
            ["active.one@example.com"],
        )
        self.assertTrue(nl.unsubscribe_family_subscriber(" ACTIVE.ONE@example.com ", 1))
        self.assertEqual(
            dbm.get_subscriber("active.one@example.com")["is_active"],
            dbm.Subscriber_State["inactive"],
        )
        self.assertFalse(nl.unsubscribe_family_subscriber("active.two@example.com", 1))
        self.assertEqual(
            dbm.get_subscriber("active.two@example.com")["is_active"],
            dbm.Subscriber_State["active"],
        )
        self.assertEqual(nl.active_recipient_emails(1), [])
        self.assertEqual(nl.active_recipient_emails(2), ["active.two@example.com"])

    def test_snapshot_uses_a_mocked_ops_svr_and_absolutizes_urls(self):
        self._seed_people()
        calls = []

        def fake_ops(family_id, lang, base_url):
            calls.append((family_id, lang, base_url))
            return (
                "<html><head>"
                "<link rel=\"stylesheet\" type=\"text/css\" href=\"/static/main.css\">"
                "</head><body>"
                f"<p>family {family_id} {lang}</p>"
                "<img src=\"/static/a.png\">"
                "<img src=\"pics/b.jpg\">"
                "<a href=\"/privacy\">privacy</a>"
                "<script>document.write('hide-me')</script>"
                "</body></html>"
            )

        snapshot = nl.build_snapshot(2, "繁中", fetcher=fake_ops, base_url="http://127.0.0.1:5566")
        self.assertEqual(calls, [(2, "繁中", "http://127.0.0.1:5566")])
        html = snapshot["html"]
        self.assertIn("family 2 繁中", html)
        self.assertIn("http://127.0.0.1:5566/static/a.png", html)
        self.assertIn("http://127.0.0.1:5566/pics/b.jpg", html)
        self.assertIn("http://127.0.0.1:5566/privacy", html)
        self.assertNotIn("main.css", html)
        self.assertIn("background: #fafafa", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn('src="/static/a.png"', html)
        self.assertEqual(snapshot["recipients"], ["active.two@example.com"])
        self.assertNotIn("active.one@example.com", snapshot["recipients"])

        def explode(*_args, **_kwargs):
            raise AssertionError("mailer was called")

        dry = nl.deliver_newsletter(snapshot, send=False, mailer=explode)
        self.assertFalse(dry["sent"])
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["reason"], "dry_run")

    def test_delivery_does_not_send_in_ci_and_stays_with_one_family(self):
        snapshot = {
            "html": "<p>Family One Market</p>",
            "subject": "Journal",
            "recipients": ["active.one@example.com"],
            "family_id": 1,
            "lang": "US",
        }
        called = []

        def fake_mailer(recipients, subject, html):
            called.append((list(recipients), subject, html))
            return True

        blocked_env = {"CI": "true", "GITHUB_ACTIONS": "", "NEWSLETTER_DISABLE_SEND": ""}
        with patch.dict(os.environ, blocked_env, clear=False):
            blocked = nl.deliver_newsletter(snapshot, send=True, mailer=fake_mailer)
        self.assertEqual(called, [])
        self.assertEqual(blocked["reason"], "blocked")
        self.assertFalse(blocked["sent"])

        open_env = {"CI": "", "GITHUB_ACTIONS": "", "NEWSLETTER_DISABLE_SEND": ""}
        with patch.dict(os.environ, open_env, clear=False):
            sent = nl.deliver_newsletter(snapshot, send=True, mailer=fake_mailer)
        self.assertTrue(sent["sent"])
        self.assertEqual(called[0][0], ["active.one@example.com"])
        self.assertIn("Family One Market", called[0][2])

        with patch.dict(os.environ, {"NEWSLETTER_DISABLE_SEND": "1", "CI": "", "GITHUB_ACTIONS": ""}, clear=False):
            again = nl.deliver_newsletter(snapshot, send=True, mailer=fake_mailer)
        self.assertEqual(again["reason"], "blocked")
        self.assertEqual(len(called), 1)

    def test_rendered_snapshot_matches_the_family_home_page(self):
        self._seed_people()
        _article(
            "Family One Market",
            1,
            content='Market day. <img src="pics/note.jpg" alt="note">',
        )
        _article("Family One Picnic", 1, category="Events")
        _article(
            "Family One Story",
            1,
            category="Story",
            image_url="/static/cover.png",
        )
        _article("Family One Lantern", 1, l10n="繁中")
        _article("Family Two Market", 2)
        _article("Family One Draft", 1, approved=False)
        _article("Family One Archive", 1, updated_at="2000-01-01 00:00:00")

        html = ops_svr.render_main_snapshot(1, "US", "http://127.0.0.1:5566")
        self.assertIn("Family One Market", html)
        self.assertIn("Family One Picnic", html)
        self.assertIn("Family One Story", html)
        self.assertIn("http://127.0.0.1:5566/static/cover.png", html)
        self.assertIn("http://127.0.0.1:5566/pics/note.jpg", html)
        self.assertIn("http://127.0.0.1:5566/privacy", html)
        self.assertNotIn("Family Two Market", html)
        self.assertNotIn("Family One Draft", html)
        self.assertNotIn("Family One Archive", html)
        self.assertNotIn("Family One Lantern", html)
        self.assertNotIn("main.css", html)
        self.assertIn("background: #fafafa", html)
        self.assertNotIn("<script", html.lower())
        self.assertRegex(html, r"\d{4}-\d{2}-\d{2}")

        traditional = ops_svr.render_main_snapshot(1, "繁中", "http://127.0.0.1:5566")
        self.assertIn("Family One Lantern", traditional)
        self.assertNotIn("Family One Market", traditional)

        with patch.object(ops_svr.eu, "send_email") as send:
            snapshot = nl.build_snapshot(1, "US", base_url="http://127.0.0.1:5566")
        send.assert_not_called()
        self.assertEqual(snapshot["recipients"], ["active.one@example.com"])
        self.assertIn("Family One Market", snapshot["html"])
        self.assertNotIn("Family Two Market", snapshot["html"])

    def test_pub_dry_run_is_family_scoped_and_does_not_send(self):
        self._seed_people()
        _article("Family One Market", 1)
        _article("Family Two Market", 2)
        _insert_admin("platform@example.com", dbm.User_State["p_admin"], 1)
        _insert_admin("family.admin@example.com", dbm.User_State["f_admin"], 1)
        client = ops_svr.app.test_client()

        with patch.object(ops_svr.eu, "send_email") as send:
            preview = client.get(
                "/pub",
                query_string={
                    "lang": "US",
                    "family_id": "2",
                    "email": "platform@example.com",
                    "password": "secret",
                    "dry_run": "1",
                },
                base_url=BASE,
            )
            locked = client.get(
                "/pub",
                query_string={
                    "lang": "US",
                    "family_id": "2",
                    "email": "family.admin@example.com",
                    "password": "secret",
                    "dry_run": "1",
                },
                base_url=BASE,
            )
        send.assert_not_called()
        self.assertEqual(preview.status_code, 200)
        preview_body = preview.get_data(as_text=True)
        self.assertIn("Family Two Market", preview_body)
        self.assertNotIn("Family One Market", preview_body)
        locked_body = locked.get_data(as_text=True)
        self.assertIn("Family One Market", locked_body)
        self.assertNotIn("Family Two Market", locked_body)

        open_env = {"CI": "", "GITHUB_ACTIONS": "", "NEWSLETTER_DISABLE_SEND": ""}
        with patch.dict(os.environ, open_env, clear=False):
            with patch.object(ops_svr.eu, "send_email", return_value=True) as send:
                sent = client.get(
                    "/pub",
                    query_string={
                        "lang": "US",
                        "family_id": "2",
                        "email": "platform@example.com",
                        "password": "secret",
                    },
                    base_url=BASE,
                    follow_redirects=True,
                )
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], ["active.two@example.com"])
        mailed = send.call_args.args[3]
        self.assertIn("Family Two Market", mailed)
        self.assertNotIn("Family One Market", mailed)
        self.assertNotIn("active.one@example.com", mailed)
        self.assertIn('role="alert"', sent.get_data(as_text=True))
        self.assertIn("alert-success", sent.get_data(as_text=True))

        blocked_env = {"CI": "true", "GITHUB_ACTIONS": "", "NEWSLETTER_DISABLE_SEND": ""}
        with patch.dict(os.environ, blocked_env, clear=False):
            with patch.object(ops_svr.eu, "send_email", return_value=True) as send:
                client.get(
                    "/pub",
                    query_string={
                        "lang": "US",
                        "family_id": "2",
                        "email": "platform@example.com",
                        "password": "secret",
                    },
                    base_url=BASE,
                    follow_redirects=True,
                )
        send.assert_not_called()

    def test_base_url_prefers_ops_svr_and_falls_back_to_the_listener(self):
        with patch.dict(os.environ, {"OPS_SVR": "http://localhost:5566/"}, clear=False):
            self.assertEqual(nl.default_base_url(), "http://localhost:5566")
        with patch.dict(
            os.environ,
            {"OPS_SVR": "", "OPS_SVR_HOST": "0.0.0.0", "OPS_SVR_PORT": "5566"},
            clear=False,
        ):
            self.assertEqual(nl.default_base_url(), "http://127.0.0.1:5566")

    def _count_users(self):
        with dbm.get_db_connection() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {dbm.db_tables['users']}").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
