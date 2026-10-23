"""Regression tests for case forms, the read-only 3-generation view, and settings."""
import importlib.util
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

import case_helpers
import db_utils as dbm
import ops_dbMgmt


def _load(module_name, relative):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaseHelperTests(unittest.TestCase):
    def test_project_env_file_is_app_root(self):
        env = case_helpers.project_env_file(ROOT / "pages" / "8_caseMgmt.py")
        self.assertEqual(env, ROOT / ".env")

    def test_member_user_fields_use_family_member_role(self):
        fields = case_helpers.member_user_fields(7, 11)
        self.assertEqual(fields["is_admin"], dbm.User_State["f_member"])
        self.assertEqual(fields["is_active"], dbm.Subscriber_State["active"])
        self.assertEqual(fields["family_id"], 7)
        self.assertEqual(fields["member_id"], 11)

    def test_chosen_parents_drops_missing(self):
        dad = {"id": 1, "name": "Dad"}
        self.assertEqual(case_helpers.chosen_parents(dad, None), [dad])
        self.assertEqual(case_helpers.chosen_parents(None, None), [])

    def test_case_page_does_not_import_venv_logger_or_pages_env(self):
        source = (ROOT / "pages" / "8_caseMgmt.py").read_text()
        self.assertNotIn("from venv import logger", source)
        self.assertNotIn("script_dir / '.env'", source)
        self.assertNotIn("User_State['f_member']", source)
        self.assertNotIn("partner_name", source)
        self.assertIn("lookup_members", source)
        self.assertIn("parent_relation", source)

    def test_lookup_members_and_parent_relation(self):
        with patch.object(case_helpers.dbm, "get_member", return_value={"id": 3, "name": "Ada"}) as get_member:
            self.assertEqual(case_helpers.lookup_members(member_id="3"), [{"id": 3, "name": "Ada"}])
            get_member.assert_called_once_with(3)
        with patch.object(case_helpers.dbm, "get_member") as get_member:
            self.assertEqual(case_helpers.lookup_members(member_id=0), [])
            self.assertEqual(case_helpers.lookup_members(member_id=-4), [])
            get_member.assert_not_called()
            with self.assertRaises(ValueError):
                case_helpers.lookup_members(member_id="nope")
        with patch.object(case_helpers.dbm, "search_members", return_value=[{"id": 4}]) as search:
            self.assertEqual(case_helpers.lookup_members(name="  Ada "), [{"id": 4}])
            search.assert_called_once_with(name="ada")
        self.assertEqual(case_helpers.lookup_members(), [])
        row = case_helpers.parent_relation(1, 2, "2000-01-01")
        self.assertEqual(row, {
            "member_id": 1,
            "partner_id": 2,
            "relation": "parent",
            "join_date": "2000-01-01",
        })
        ended = case_helpers.parent_relation(1, 2, "2000-01-01", "adopt", end_date="0000-00-00")
        self.assertEqual(ended["relation"], "adopt")
        self.assertEqual(ended["end_date"], "0000-00-00")


class ThreeGenerationTests(unittest.TestCase):
    def test_view_reads_relatives_without_writing_relations(self):
        page = _load("show_3g_page", "pages/6_show_3G.py")
        center = {"id": 1, "name": "Center", "born": "2000-01-01"}
        parent = {"id": 2, "name": "Parent", "born": "1970-01-01"}
        grand = {"id": 3, "name": "Grand", "born": "1940-01-01"}
        child = {"id": 4, "name": "Child", "born": "2020-01-01"}
        grandchild = {"id": 5, "name": "Grandchild", "born": "2040-01-01"}
        members = {1: center, 2: parent, 3: grand, 4: child, 5: grandchild}

        def parents(member_id):
            return {1: [parent], 2: [grand]}.get(member_id, [])

        def children(member_id):
            return {1: [child], 4: [grandchild]}.get(member_id, [])

        with patch.object(page.dbm, "get_member", side_effect=lambda mid: members.get(mid)), \
             patch.object(page.dbm, "get_parents", side_effect=parents), \
             patch.object(page.dbm, "get_children", side_effect=children), \
             patch.object(page.dbm, "add_or_update_relation") as write:
            result = page.get_family_members(1)

        write.assert_not_called()
        self.assertEqual(result["center"]["id"], 1)
        self.assertEqual([m["id"] for m in result["parents"]], [2])
        self.assertEqual([m["id"] for m in result["grandparents"]], [3])
        self.assertEqual([m["id"] for m in result["children"]], [4])
        self.assertEqual([m["id"] for m in result["grandchildren"]], [5])


class SettingsTests(unittest.TestCase):
    def test_format_timestamps_uses_requested_timezone(self):
        pandas = __import__("pandas")
        page = _load("usr_mgmt_page", "pages/1_usrMgmt.py")
        frame = pandas.DataFrame({
            "created_at": ["2024-01-15 20:00:00"],
            "updated_at": ["2024-01-15 20:00:00"],
        })
        pacific = page.format_timestamps(frame.copy(), "America/Los_Angeles")
        taipei = page.format_timestamps(frame.copy(), "Asia/Taipei")
        self.assertEqual(pacific.loc[0, "created_at"], "2024-01-15 12:00:00")
        self.assertEqual(taipei.loc[0, "created_at"], "2024-01-16 04:00:00")

    def test_default_timezone_is_pacific(self):
        import context_utils as cu
        pandas = __import__("pandas")
        page = _load("usr_mgmt_page_default_tz", "pages/1_usrMgmt.py")
        self.assertEqual(cu.DEFAULT_TIMEZONE, "America/Los_Angeles")
        frame = pandas.DataFrame({"created_at": ["2024-01-15 20:00:00"]})
        shown = page.format_timestamps(frame)
        self.assertEqual(shown.loc[0, "created_at"], "2024-01-15 12:00:00")

    def test_unknown_timezone_falls_back_to_utc(self):
        pandas = __import__("pandas")
        page = _load("usr_mgmt_page_tz", "pages/1_usrMgmt.py")
        frame = pandas.DataFrame({"created_at": ["2024-01-15 20:00:00"]})
        shown = page.format_timestamps(frame, "Not/AZone")
        self.assertEqual(shown.loc[0, "created_at"], "2024-01-15 20:00:00")

    def test_family_update_message_uses_update_data(self):
        source = (ROOT / "pages" / "2_famMgmt.py").read_text()
        self.assertNotIn("updated_data", source)
        self.assertIn("update_data", source)

    def test_remove_column_is_imported_and_drops_the_column(self):
        source = (ROOT / "fTrees.py").read_text()
        self.assertIn("remove_column_if_exists,", source)

        tmp = tempfile.mkdtemp(prefix="ftpe-col-")
        previous = dbm.database_name
        dbm.database_name = os.path.join(tmp, "family.db")
        try:
            with sqlite3.connect(dbm.database_name) as conn:
                conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, extra TEXT)")
                conn.execute("INSERT INTO widgets (extra) VALUES ('keep')")
                conn.commit()
            self.assertTrue(ops_dbMgmt.remove_column_if_exists("widgets", "extra"))
            with sqlite3.connect(dbm.database_name) as conn:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(widgets)")]
                count = conn.execute("SELECT COUNT(*) FROM widgets").fetchone()[0]
            self.assertEqual(columns, ["id"])
            self.assertEqual(count, 1)
            self.assertFalse(ops_dbMgmt.remove_column_if_exists("widgets", "missing"))
        finally:
            dbm.database_name = previous
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
