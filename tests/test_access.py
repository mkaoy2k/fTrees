"""Role gates, query limits, and login attempt limits."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auth_utils as au
import db_utils as dbm
import graph_text
import nav


class RoleGateTests(unittest.TestCase):
    def test_role_decision(self):
        everyone = (
            dbm.User_State["p_admin"],
            dbm.User_State["f_admin"],
            dbm.User_State["f_member"],
        )
        admins = (dbm.User_State["p_admin"], dbm.User_State["f_admin"])
        self.assertEqual(nav.role_is_allowed(False, dbm.User_State["f_member"], everyone), "login")
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["f_member"], admins), "denied")
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["f_admin"], admins), "ok")
        self.assertEqual(nav.role_is_allowed(True, dbm.User_State["f_member"], everyone), "ok")

    def test_links_follow_the_role_and_the_language_file(self):
        texts = {
            "home": "Inicio",
            "user": "Usuario",
            "management": "Gestion",
            "family": "Familia",
            "case_mgmt": "Casos",
            "birthday": "Cumple",
            "relation": "Relacion",
            "MENU_QUERY_TBL_BY_3GEN": "Tres generaciones",
        }
        member_pages = [item["page"] for item in nav.navigation_links(dbm.User_State["f_member"], texts)]
        self.assertIn("fTrees.py", member_pages)
        self.assertIn("pages/6_show_3G.py", member_pages)
        self.assertIn("pages/7_show_related.py", member_pages)
        self.assertIn("pages/3_csv_editor.py", member_pages)
        self.assertNotIn("pages/2_famMgmt.py", member_pages)
        self.assertNotIn("pages/8_caseMgmt.py", member_pages)
        self.assertNotIn("pages/9_birthday.py", member_pages)
        self.assertNotIn("pages/1_usrMgmt.py", member_pages)

        admin = nav.navigation_links(dbm.User_State["f_admin"], texts)
        admin_pages = [item["page"] for item in admin]
        self.assertIn("pages/2_famMgmt.py", admin_pages)
        self.assertIn("pages/8_caseMgmt.py", admin_pages)
        self.assertIn("pages/9_birthday.py", admin_pages)
        family = next(item["label"] for item in admin if item["page"] == "pages/2_famMgmt.py")
        self.assertEqual(family, "Familia Gestion")
        three = next(item["label"] for item in admin if item["page"] == "pages/6_show_3G.py")
        self.assertEqual(three, "Tres generaciones")

        sparse = nav.navigation_links(dbm.User_State["f_member"], {"home": "Home"})
        fallback = next(item["label"] for item in sparse if item["page"] == "pages/6_show_3G.py")
        csv_label = next(item["label"] for item in sparse if item["page"] == "pages/3_csv_editor.py")
        self.assertEqual(fallback, "Show 3 Generations")
        self.assertEqual(csv_label, "CSV")

    def test_pages_gate_before_they_read_data(self):
        for name in (
            "pages/2_famMgmt.py",
            "pages/3_csv_editor.py",
            "pages/4_json_editor.py",
            "pages/6_show_3G.py",
            "pages/7_show_related.py",
            "pages/8_caseMgmt.py",
            "pages/9_birthday.py",
        ):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("require_role", source, name)
            self.assertIn("render_sidebar", source, name)
        self.assertFalse((ROOT / "pages" / "5_ftpe.py").exists())
        self.assertFalse((ROOT / "ftpe.py").exists())

    def test_reset_page_uses_one_sentence(self):
        source = (ROOT / "fTrees.py").read_text(encoding="utf-8")
        self.assertIn("RESET_REQUEST_MESSAGE", source)
        self.assertIn("login_allowed", source)
        self.assertIn("record_auth_attempt", source)
        self.assertNotIn("If your email exists", source)
        self.assertNotIn("has been sent to", source)

    def test_graph_popups_escape_names(self):
        popup = graph_text.member_popup(7, "<img src=x>")
        self.assertEqual(popup, "ID: 7<br>Name: &lt;img src=x&gt;")
        self.assertIn("<br>", popup)
        self.assertNotIn("<img", popup)
        self.assertIn("&quot;", graph_text.related_popup('Ann "A"', "parent"))
        page6 = (ROOT / "pages/6_show_3G.py").read_text(encoding="utf-8")
        page7 = (ROOT / "pages/7_show_related.py").read_text(encoding="utf-8")
        self.assertIn("member_popup", page6)
        self.assertIn("related_popup", page7)
        self.assertIn("center_popup", page7)
        self.assertIn('"direction": "UD"', page6)
        self.assertIn('"enabled": false', page6)
        self.assertNotIn("graphviz", page6.lower())
        self.assertNotIn("neato", page6)

    def test_three_generation_rows_follow_generation(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("show_3g", ROOT / "pages" / "6_show_3G.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        family = {
            "center": {"id": 2, "name": "Ada <b>", "sex": "f", "gen_order": 2, "born": "1950-01-01"},
            "parents": [
                {"id": 1, "name": "Bob", "sex": "m", "gen_order": 1},
                {"id": 4, "name": "Dee", "sex": "f"},
            ],
            "children": [
                {"id": 3, "name": 'Cy "C"', "sex": "m", "gen_order": "3"},
                {"id": 5, "name": "Eve", "sex": "f", "gen_order": 0},
            ],
            "grandparents": [],
            "grandchildren": [],
        }
        graph = module.create_family_graph(family, height=8, width=10)
        levels = {node["id"]: node["level"] for node in graph.nodes}
        self.assertEqual(levels, {"2": 2, "1": 1, "4": 1, "3": 3, "5": 3})
        titles = {node["id"]: node["title"] for node in graph.nodes}
        self.assertEqual(titles["2"], "ID: 2<br>Name: Ada &lt;b&gt;")
        self.assertNotIn("<b>", titles["2"])
        html = graph.generate_html()
        self.assertIn('"direction": "UD"', html)
        self.assertIn('"enabled": false', html)
        self.assertNotIn("use_DOT", html)


class QueryAndAttemptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftpe-access-")
        self.db_path = os.path.join(self.tmp, "family.db")
        self._previous_db = dbm.database_name
        dbm.database_name = self.db_path
        dbm.init_db()

    def tearDown(self):
        dbm.database_name = self._previous_db
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _insert(self, name, born, died, gen_order):
        with dbm.get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO members (name, born, died, sex, gen_order)
                VALUES (?, ?, ?, 'M', ?)
                """,
                (name, born, died, gen_order),
            )

    def test_born_index_and_attempt_table_exist(self):
        with dbm.get_db_connection() as conn:
            indexes = {row[1] for row in conn.execute("PRAGMA index_list('members')")}
            self.assertIn("idx_members_born", indexes)
            conn.execute("SELECT email, action, attempted_at FROM login_attempts")

    def test_nested_connections_are_the_same_object(self):
        with dbm.get_db_connection() as outer:
            with dbm.get_db_connection() as inner:
                self.assertIs(outer, inner)
                inner.execute("CREATE TABLE ping (id INTEGER)")
            outer.execute("INSERT INTO ping (id) VALUES (1)")
            self.assertEqual(outer.execute("SELECT id FROM ping").fetchone()[0], 1)
        scope = dbm.get_db_connection()
        scope.isolation_level = None
        self.assertIsNone(scope.isolation_level)
        scope.close()

    def test_alive_filter_matches_member_is_alive(self):
        samples = [
            ("Empty", "1990-05-02", ""),
            ("Placeholder", "1990-05-03", "0000-00-00"),
            ("UnknownDay", "1990-05-04", "0000-01-01"),
            ("Zero", "1990-05-05", "0"),
            ("Token", "1990-05-06", "YYYY-MM-DD"),
            ("Year", "1990-05-07", "1999"),
            ("Month", "1990-05-08", "1999-05"),
            ("Full", "1990-05-09", "1999-05-01"),
            ("Text", "1990-05-10", "not-a-date"),
            ("June", "1990-06-01", None),
        ]
        for name, born, died in samples:
            self._insert(name, born, died, 1)
        with dbm.get_db_connection() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM members")]
        expected = {row["id"] for row in rows if dbm.member_is_alive(row)}
        actual = {row["id"] for row in dbm.get_members_when_alive()}
        self.assertEqual(actual, expected)

        may = {member["name"] for member in dbm.get_members_when_born_in(5)}
        self.assertIn("Empty", may)
        self.assertIn("Placeholder", may)
        self.assertIn("Text", may)
        self.assertNotIn("Full", may)
        self.assertNotIn("Year", may)
        self.assertNotIn("June", may)
        alive_names = {member["name"] for member in dbm.search_members(alive=True)}
        self.assertIn("Placeholder", alive_names)
        self.assertNotIn("Full", alive_names)

    def test_search_limit_and_offset(self):
        for index, name in enumerate(("A", "B", "C", "D", "E"), start=1):
            self._insert(name, "1980-01-01", None, index)
        first = [member["name"] for member in dbm.search_members(limit=2, offset=0)]
        last = [member["name"] for member in dbm.search_members(limit=2, offset=4)]
        everything = dbm.search_members()
        self.assertEqual(first, ["A", "B"])
        self.assertEqual(last, ["E"])
        self.assertEqual(len(everything), 5)
        with self.assertRaises(ValueError):
            dbm.search_members(limit=-1)

    def test_login_and_reset_share_the_attempt_limit(self):
        for _ in range(au.cu.MAX_LOGIN_ATTEMPTS):
            au.record_auth_attempt("User@Example.com", "login")
        self.assertTrue(au.auth_is_limited("user@example.com", "login"))
        self.assertFalse(au.login_allowed("user@example.com"))
        au.record_auth_attempt("user@example.com", "login")
        self.assertEqual(au.auth_attempt_count("user@example.com", "login"), au.cu.MAX_LOGIN_ATTEMPTS)
        self.assertTrue(au.reset_may_send("user@example.com"))
        au.clear_auth_attempts("USER@example.com", "login")
        self.assertFalse(au.auth_is_limited("user@example.com", "login"))

        for _ in range(au.cu.MAX_LOGIN_ATTEMPTS):
            au.record_auth_attempt("missing@example.com", "reset")
        self.assertFalse(au.reset_may_send("missing@example.com"))
        self.assertTrue(au.login_allowed("missing@example.com"))

        with dbm.get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO login_attempts (email, action, attempted_at)
                VALUES ('old@example.com', 'login', datetime('now', '-2 hours'))
                """
            )
        self.assertFalse(au.auth_is_limited("old@example.com", "login"))


if __name__ == "__main__":
    unittest.main()
