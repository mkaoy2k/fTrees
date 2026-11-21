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


class OpsSimplifiedChineseTests(unittest.TestCase):
    """简中 is Simplified Chinese (zh-CN), labelled CN. Same key as L10N.json."""

    def test_ops_catalogs_share_keys_and_cn_is_simplified(self):
        index = json.loads((ROOT / "ops_L10N.json").read_text(encoding="utf-8"))
        self.assertEqual(index["简中"], "ops_L10N_CN.json")
        self.assertEqual(index["繁中"], "ops_L10N_TW.json")
        self.assertEqual(index["US"], "ops_L10N_US.json")
        menu = json.loads((ROOT / "ops_menu.json").read_text(encoding="utf-8"))
        self.assertEqual(menu["简中"][0], ["home", "首页"])
        us = json.loads((ROOT / "ops_L10N_US.json").read_text(encoding="utf-8"))
        tw = json.loads((ROOT / "ops_L10N_TW.json").read_text(encoding="utf-8"))
        cn = json.loads((ROOT / "ops_L10N_CN.json").read_text(encoding="utf-8"))
        self.assertEqual(set(us), set(tw))
        self.assertEqual(set(us), set(cn))
        self.assertEqual(cn["YOUR_LANGUAGE"], "您的语言")
        self.assertEqual(tw["YOUR_LANGUAGE"], "您的語言")
        self.assertEqual(cn["SETTINGS"], "设置")
        self.assertEqual(cn["SUBSCRIBE"], "订阅")
        self.assertEqual(cn["HOME_HTML_T2"], "故事")
        self.assertEqual(cn["HOME_HTML_T3"], "活动")
        self.assertNotIn("訂閱", json.dumps(cn, ensure_ascii=False))
        self.assertNotIn("設定", json.dumps(cn, ensure_ascii=False))
        self.assertEqual(us["PRIVACY_SECTIONS"][0]["heading"], "1. Information We Collect")
        self.assertEqual(
            us["SUB_SUCCESS"],
            "{email} has been successfully subscribed to our newsletter!",
        )
        self.assertIn("个人资料", cn["SUB_NONMEMBER_ACTION"])
        self.assertIn("個人資料", tw["SUB_NONMEMBER_ACTION"])

    def test_cn_alias_selects_simplified_chinese(self):
        options = ["繁中", "简中", "US"]
        self.assertEqual(fu.normalize_ops_lang("CN", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("zh-CN", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("zh-Hans", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("简中", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("us", options), "US")
        self.assertEqual(fu.normalize_ops_lang("繁中", options), "繁中")
        self.assertIsNone(fu.normalize_ops_lang("CN", ["US", "繁中"]))
        self.assertEqual(fu.ops_lang_label("简中"), "CN")
        self.assertEqual(fu.ops_lang_label("繁中"), "繁中")
        self.assertEqual(fu.ops_lang_label("US"), "US")
