"""Language catalogs and case-insensitive language lookup."""
import json
import unittest
from pathlib import Path

import funcUtils as fu

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = (
    "L10N_US.json",
    "L10N_CN.json",
    "L10N_TW.json",
    "L10N_JP.json",
    "L10N_KR.json",
    "L10N_DE.json",
    "L10N_DK.json",
    "L10N_FR.json",
    "L10N_LT.json",
    "L10N_PL.json",
    "L10N_ES.json",
)
JOIN = "To become a family admin, you must join this family as member first"


class LanguageLookupTests(unittest.TestCase):
    def test_names_match_without_case(self):
        catalogs = {"US": {"home": "Home"}, "Spanish": {"home": "Inicio"}, "繁中": {"home": "首頁"}}
        self.assertEqual(fu.resolve_language(catalogs, "Spanish"), "Spanish")
        self.assertEqual(fu.resolve_language(catalogs, "spanish"), "Spanish")
        self.assertEqual(fu.resolve_language(catalogs, "SPANISH"), "Spanish")
        self.assertEqual(fu.resolve_language(catalogs, "us"), "US")
        self.assertEqual(fu.resolve_language(catalogs, "繁中"), "繁中")
        self.assertEqual(fu.resolve_language(catalogs, "no-such"), "US")
        self.assertEqual(fu.resolve_language({}, "Spanish"), "US")
        self.assertEqual(fu.texts_for(catalogs, "spanish")["home"], "Inicio")
        self.assertEqual(fu.texts_for(None, "US"), {})
        self.assertEqual(fu.language_index(["US", "Spanish", "繁中"], "spanish"), 1)
        self.assertEqual(fu.language_index([], "spanish"), 0)


class CatalogTests(unittest.TestCase):
    def test_every_catalog_has_the_us_keys(self):
        us = json.loads((ROOT / "L10N_US.json").read_text(encoding="utf-8"))
        self.assertEqual(
            us["reset_request_message"],
            "If an account exists for that email, a reset link has been sent.",
        )
        self.assertIn(JOIN, us)
        self.assertEqual(us["month_10"], "October")
        for name in CATALOGS:
            data = json.loads((ROOT / name).read_text(encoding="utf-8"))
            missing = sorted(set(us) - set(data))
            self.assertEqual(missing, [], name)
        self.assertIn("MENU_QUERY_TBL_BY_3GEN", us)
        self.assertIn("DB", us)
        self.assertNotIn("personal_sign_in", us)
        self.assertNotIn("MAIN_TITLE", us)
        spanish = json.loads((ROOT / "L10N_ES.json").read_text(encoding="utf-8"))
        self.assertIn("Editor", spanish["csv_editor"])
        self.assertIn("MENU_QUERY_TBL_BY_3GEN", spanish)
