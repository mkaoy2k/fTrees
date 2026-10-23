"""CSV and JSON editors stay inside the data directory."""
import tempfile
import unittest
from pathlib import Path

import editor_paths

ROOT = Path(__file__).resolve().parents[1]


class EditorPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ftpe-editor-")
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "me.csv").write_text("name\nAda\n", encoding="utf-8")
        (self.data / "notes.json").write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_names_stay_in_data_and_gain_a_suffix(self):
        csv_path = editor_paths.new_data_file(self.root, "me", ".csv")
        json_path = editor_paths.new_data_file(self.root, "notes.json", ".json")
        self.assertEqual(csv_path, (self.data / "me.csv").resolve())
        self.assertEqual(json_path, (self.data / "notes.json").resolve())
        self.assertEqual(editor_paths.sanitized_filename("家族", ".csv"), "家族.csv")

    def test_traversal_and_odd_names_are_rejected(self):
        rejected = [
            "../secret.csv",
            "/etc/passwd.csv",
            "foo/bar.csv",
            "..\\secret.csv",
            "..",
            "",
            "   ",
            "me.csv/../../../etc/passwd",
            ".hidden.csv",
            "con\x00.csv",
            12,
            ".csv",
        ]
        for raw in rejected:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    editor_paths.sanitized_filename(raw, ".csv")
                if isinstance(raw, str):
                    with self.assertRaises(ValueError):
                        editor_paths.new_data_file(self.root, raw, ".csv")

    def test_symlink_that_leaves_data_is_not_listed_or_opened(self):
        outside = self.root / "secret.csv"
        outside.write_text("secret\n", encoding="utf-8")
        link = self.data / "escape.csv"
        link.symlink_to(outside)
        self.assertFalse(editor_paths.path_inside(self.data, link))
        self.assertIsNone(editor_paths.contained_file(self.root, link))
        names = editor_paths.list_data_files(self.root, ".csv")
        self.assertEqual(names, ["me.csv"])
        self.assertNotIn("escape.csv", names)

    def test_data_directory_link_is_rejected(self):
        linked = tempfile.TemporaryDirectory(prefix="ftpe-linked-")
        try:
            root = Path(linked.name)
            target = root / "elsewhere"
            target.mkdir()
            (root / "data").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                editor_paths.data_directory(root)
        finally:
            linked.cleanup()

    def test_editors_do_not_offer_the_project_root(self):
        for name in ("pages/3_csv_editor.py", "pages/4_json_editor.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("Project Root", source)
            self.assertIn("editor_paths", source)
            self.assertIn("contained_file", source)
            self.assertIn("new_data_file", source)
