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


def _value_shape(value):
    if isinstance(value, dict):
        return {key: _value_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_value_shape(item) for item in value]
    return type(value).__name__


class OpsJapaneseKoreanTests(unittest.TestCase):
    """日本語 and 한국어 match L10N.json. The switcher labels them JP and KR."""

    def test_ops_catalogs_share_keys_with_japanese_and_korean(self):
        index = json.loads((ROOT / "ops_L10N.json").read_text(encoding="utf-8"))
        streamlit = json.loads((ROOT / "L10N.json").read_text(encoding="utf-8"))
        self.assertEqual(index["日本語"], "ops_L10N_JP.json")
        self.assertEqual(index["한국어"], "ops_L10N_KR.json")
        self.assertEqual(streamlit["日本語"], "L10N_JP.json")
        self.assertEqual(streamlit["한국어"], "L10N_KR.json")
        menu = json.loads((ROOT / "ops_menu.json").read_text(encoding="utf-8"))
        self.assertEqual(menu["日本語"][0], ["home", "ホーム"])
        self.assertEqual(menu["한국어"][0], ["home", "홈"])
        self.assertEqual(menu["简中"][0], ["home", "首页"])
        us = json.loads((ROOT / "ops_L10N_US.json").read_text(encoding="utf-8"))
        jp = json.loads((ROOT / "ops_L10N_JP.json").read_text(encoding="utf-8"))
        kr = json.loads((ROOT / "ops_L10N_KR.json").read_text(encoding="utf-8"))
        self.assertEqual(_value_shape(us), _value_shape(jp))
        self.assertEqual(_value_shape(us), _value_shape(kr))
        self.assertEqual(jp["YOUR_LANGUAGE"], "表示言語")
        self.assertEqual(kr["YOUR_LANGUAGE"], "표시 언어")
        self.assertEqual(jp["SUBSCRIBE"], "購読")
        self.assertEqual(kr["SUBSCRIBE"], "구독")
        self.assertEqual(jp["PRIVACY_SECTIONS"][0]["heading"], "1. 収集する情報")
        self.assertEqual(kr["PRIVACY_SECTIONS"][0]["heading"], "1. 수집하는 정보")
        self.assertIn("{email}", jp["SUB_SUCCESS"])
        self.assertIn("{app}", kr["VERIFY_SUB_SUBJECT"])
        self.assertNotEqual(jp["HOME_HTML_H1"], us["HOME_HTML_H1"])
        self.assertNotEqual(kr["HOME_HTML_H1"], us["HOME_HTML_H1"])
        self.assertNotIn("訂閱", json.dumps(jp, ensure_ascii=False))
        self.assertNotIn("订阅", json.dumps(kr, ensure_ascii=False))

    def test_jp_and_kr_aliases_select_the_stored_keys(self):
        options = ["繁中", "简中", "日本語", "한국어", "US"]
        self.assertEqual(fu.normalize_ops_lang("JP", options), "日本語")
        self.assertEqual(fu.normalize_ops_lang("ja", options), "日本語")
        self.assertEqual(fu.normalize_ops_lang("ja-JP", options), "日本語")
        self.assertEqual(fu.normalize_ops_lang("日本語", options), "日本語")
        self.assertEqual(fu.normalize_ops_lang("KR", options), "한국어")
        self.assertEqual(fu.normalize_ops_lang("ko", options), "한국어")
        self.assertEqual(fu.normalize_ops_lang("ko-KR", options), "한국어")
        self.assertEqual(fu.normalize_ops_lang("한국어", options), "한국어")
        self.assertEqual(fu.normalize_ops_lang("CN", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("繁中", options), "繁中")
        self.assertEqual(fu.normalize_ops_lang("us", options), "US")
        self.assertIsNone(fu.normalize_ops_lang("ja", ["US", "繁中", "简中"]))
        self.assertIsNone(fu.normalize_ops_lang("ko", ["US", "繁中"]))
        self.assertEqual(fu.ops_lang_label("日本語"), "JP")
        self.assertEqual(fu.ops_lang_label("한국어"), "KR")
        self.assertEqual(fu.ops_lang_label("简中"), "CN")
        self.assertEqual(fu.ops_html_lang("日本語"), "ja")
        self.assertEqual(fu.ops_html_lang("한국어"), "ko")
        self.assertEqual(fu.ops_html_lang("简中"), "zh-CN")
        self.assertEqual(fu.ops_html_lang("繁中"), "zh-Hant")

    def test_accept_language_maps_japanese_and_korean(self):
        options = ["繁中", "简中", "日本語", "한국어", "US"]
        self.assertEqual(fu.match_accept_language("ja-JP,ja;q=0.9,en;q=0.8", options), "日本語")
        self.assertEqual(fu.match_accept_language("ko-KR,ko;q=0.8,en;q=0.5", options), "한국어")
        self.assertEqual(fu.match_accept_language("fr,ja;q=0.5", options), "日本語")
        self.assertEqual(fu.match_accept_language("ja;q=0, en;q=0.8", options), "US")
        self.assertEqual(fu.match_accept_language("zh-TW,zh;q=0.9,en;q=0.8", options), "繁中")
        self.assertEqual(fu.match_accept_language("zh-CN,zh;q=0.9", options), "简中")
        self.assertIsNone(fu.match_accept_language("fr,de;q=0.5", options))
        self.assertIsNone(fu.match_accept_language("*", options))
        self.assertIsNone(fu.match_accept_language("", options))
        self.assertEqual(
            fu.match_accept_language([("ko", 0.2), ("ja", 0.9)], options),
            "日本語",
        )


# Stored keys are the Streamlit names. The switcher shows the short labels.
_EUROPEAN = (
    ("Danish", "ops_L10N_DK.json", "L10N_DK.json", "DK", "da", "Dit sprog", "Abonnér", "1. Oplysninger vi indsamler"),
    ("German", "ops_L10N_DE.json", "L10N_DE.json", "DE", "de", "Ihre Sprache", "Abonnieren", "1. Welche Daten wir erheben"),
    ("French", "ops_L10N_FR.json", "L10N_FR.json", "FR", "fr", "Votre langue", "S'abonner", "1. Informations que nous collectons"),
    ("Lithuanian", "ops_L10N_LT.json", "L10N_LT.json", "LT", "lt", "Jūsų kalba", "Prenumeruoti", "1. Kokią informaciją renkame"),
    ("Polish", "ops_L10N_PL.json", "L10N_PL.json", "PL", "pl", "Twój język", "Subskrybuj", "1. Jakie informacje zbieramy"),
    ("Spanish", "ops_L10N_ES.json", "L10N_ES.json", "ES", "es", "Su idioma", "Suscribirse", "1. Información que recopilamos"),
)


class OpsEuropeanLanguageTests(unittest.TestCase):
    """Danish through Spanish match L10N.json. The switcher shows DK–ES."""

    def test_catalogs_share_keys_with_the_streamlit_names(self):
        index = json.loads((ROOT / "ops_L10N.json").read_text(encoding="utf-8"))
        streamlit = json.loads((ROOT / "L10N.json").read_text(encoding="utf-8"))
        menu = json.loads((ROOT / "ops_menu.json").read_text(encoding="utf-8"))
        us = json.loads((ROOT / "ops_L10N_US.json").read_text(encoding="utf-8"))
        self.assertEqual(
            list(index),
            ["繁中", "简中", "日本語", "한국어", "Danish", "German", "French", "Lithuanian", "Polish", "Spanish", "US"],
        )
        for key, ops_file, streamlit_file, label, html_lang, your_language, subscribe, privacy in _EUROPEAN:
            self.assertEqual(index[key], ops_file)
            self.assertEqual(streamlit[key], streamlit_file)
            self.assertEqual(menu[key][0][0], "home")
            self.assertEqual(len(menu[key]), 4)
            data = json.loads((ROOT / ops_file).read_text(encoding="utf-8"))
            self.assertEqual(_value_shape(us), _value_shape(data))
            self.assertEqual(data["YOUR_LANGUAGE"], your_language)
            self.assertEqual(data["SUBSCRIBE"], subscribe)
            self.assertEqual(data["PRIVACY_SECTIONS"][0]["heading"], privacy)
            self.assertIn("family id", data["FAMILY_ID_HELP"])
            self.assertIn("{email}", data["SUB_SUCCESS"])
            self.assertIn("{app}", data["VERIFY_SUB_SUBJECT"])
            self.assertIn("{email}", data["VERIFY_SUB_BODY"])
            self.assertNotEqual(data["HOME_HTML_H1"], us["HOME_HTML_H1"])
            self.assertNotIn("訂閱", json.dumps(data, ensure_ascii=False))
            self.assertNotIn("订阅", json.dumps(data, ensure_ascii=False))
            self.assertEqual(fu.ops_lang_label(key), label)
            self.assertEqual(fu.ops_html_lang(key), html_lang)
        self.assertEqual(menu["简中"][0], ["home", "首页"])
        self.assertEqual(fu.ops_lang_label("日本語"), "JP")
        self.assertEqual(fu.ops_lang_label("简中"), "CN")

    def test_aliases_select_the_stored_keys(self):
        options = [
            "繁中", "简中", "日本語", "한국어",
            "Danish", "German", "French", "Lithuanian", "Polish", "Spanish", "US",
        ]
        self.assertEqual(fu.normalize_ops_lang("DK", options), "Danish")
        self.assertEqual(fu.normalize_ops_lang("da", options), "Danish")
        self.assertEqual(fu.normalize_ops_lang("da-DK", options), "Danish")
        self.assertEqual(fu.normalize_ops_lang("Danish", options), "Danish")
        self.assertEqual(fu.normalize_ops_lang("dansk", options), "Danish")
        self.assertEqual(fu.normalize_ops_lang("DE", options), "German")
        self.assertEqual(fu.normalize_ops_lang("de", options), "German")
        self.assertEqual(fu.normalize_ops_lang("de-DE", options), "German")
        self.assertEqual(fu.normalize_ops_lang("de-AT", options), "German")
        self.assertEqual(fu.normalize_ops_lang("de-CH", options), "German")
        self.assertEqual(fu.normalize_ops_lang("deutsch", options), "German")
        self.assertEqual(fu.normalize_ops_lang("german", options), "German")
        self.assertEqual(fu.normalize_ops_lang("FR", options), "French")
        self.assertEqual(fu.normalize_ops_lang("fr", options), "French")
        self.assertEqual(fu.normalize_ops_lang("fr-FR", options), "French")
        self.assertEqual(fu.normalize_ops_lang("fr-CA", options), "French")
        self.assertEqual(fu.normalize_ops_lang("français", options), "French")
        self.assertEqual(fu.normalize_ops_lang("LT", options), "Lithuanian")
        self.assertEqual(fu.normalize_ops_lang("lt", options), "Lithuanian")
        self.assertEqual(fu.normalize_ops_lang("lt-LT", options), "Lithuanian")
        self.assertEqual(fu.normalize_ops_lang("PL", options), "Polish")
        self.assertEqual(fu.normalize_ops_lang("pl", options), "Polish")
        self.assertEqual(fu.normalize_ops_lang("pl-PL", options), "Polish")
        self.assertEqual(fu.normalize_ops_lang("ES", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("es", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("es-ES", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("es-MX", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("es-419", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("español", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("spanish", options), "Spanish")
        self.assertEqual(fu.normalize_ops_lang("CN", options), "简中")
        self.assertEqual(fu.normalize_ops_lang("ja-JP", options), "日本語")
        self.assertEqual(fu.normalize_ops_lang("ko", options), "한국어")
        self.assertEqual(fu.normalize_ops_lang("us", options), "US")
        self.assertIsNone(fu.normalize_ops_lang("da", ["US", "繁中", "简中"]))
        self.assertIsNone(fu.normalize_ops_lang("de-AT", ["US", "日本語"]))
        self.assertIsNone(fu.normalize_ops_lang("pt-BR", options))
        self.assertIsNone(fu.normalize_ops_lang("ca", options))

    def test_accept_language_maps_the_new_codes(self):
        options = [
            "繁中", "简中", "日本語", "한국어",
            "Danish", "German", "French", "Lithuanian", "Polish", "Spanish", "US",
        ]
        self.assertEqual(fu.match_accept_language("da-DK,da;q=0.9,en;q=0.8", options), "Danish")
        self.assertEqual(fu.match_accept_language("de-AT,de;q=0.8,en;q=0.5", options), "German")
        self.assertEqual(fu.match_accept_language("fr-CA,fr;q=0.9,en;q=0.4", options), "French")
        self.assertEqual(fu.match_accept_language("lt-LT,lt;q=0.8,en;q=0.3", options), "Lithuanian")
        self.assertEqual(fu.match_accept_language("pl-PL,pl;q=0.8,en;q=0.2", options), "Polish")
        self.assertEqual(fu.match_accept_language("es-MX,es;q=0.9,en;q=0.5", options), "Spanish")
        self.assertEqual(fu.match_accept_language("es-419,es;q=0.8", options), "Spanish")
        self.assertEqual(fu.match_accept_language("fr,ja;q=0.5", options), "French")
        self.assertEqual(fu.match_accept_language("pt-BR,en;q=0.5", options), "US")
        self.assertEqual(fu.match_accept_language("da;q=0, en;q=0.8", options), "US")
        older = ["繁中", "简中", "日本語", "한국어", "US"]
        self.assertEqual(fu.match_accept_language("fr,ja;q=0.5", older), "日本語")
        self.assertIsNone(fu.match_accept_language("fr,de;q=0.5", older))
