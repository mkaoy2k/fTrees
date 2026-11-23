import os
from dotenv import load_dotenv  # pip install python-dotenv
import json
import logging
import streamlit as st  # pip install streamlit
from datetime import datetime, timedelta
from pathlib import Path
import traceback

def show_user_error(message, exc=None, *, warn=False):
    """Show a generic message in the UI and keep exception details in the server log."""
    log = logging.getLogger("ftpe")
    if exc is not None:
        log.error("%s", message, exc_info=exc)
    else:
        log.error("%s", message)
    if warn:
        st.warning(message)
    else:
        st.error(message)

def log_activity(user_id, action):
    """
    記錄使用者活動到月誌檔案
    
    此函數會將使用者的登入/登出活動記錄到以月份命名的日誌檔案中。
    日誌檔案會自動清理一年前的舊記錄，並確保日誌目錄存在。
    
    Args:
        user_id (str): 使用者ID
        action (str): 活動類型，應為 'login' 或 'logout'
        
    Returns:
        None
        
    Raises:
        Exception: 當日誌寫入發生錯誤時拋出，但會被函數內部捕獲並記錄
        
    Example:
        >>> log_activity('user123', 'login')
        # 會在 data/01.log 中新增一筆記錄：2025-12-06 10:41:00,user123,login
        
    Note:
        - 日誌檔案會自動建立在 data/ 目錄下
        - 每個月會建立一個新的日誌檔案（如：01.log, 02.log）
        - 系統會自動清理一年前的舊記錄
    """
    try:
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
        
        # Get current month and year for log file name
        now = datetime.now()
        month_str = now.strftime("%m")  # 01-12
        
        # Log file path: data/01.log, data/02.log, etc.
        log_file = os.path.join('data', f"{month_str}.log")
        
        # Check if log file exists and clean up old entries if needed
        if os.path.exists(log_file):
            one_year_ago = now - timedelta(days=365)
            cleaned_lines = []
            
            # Read existing log file and filter out old entries
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        # Parse date from log entry (first part before comma)
                        log_date_str = line.split(',')[0].strip()
                        log_date = datetime.strptime(log_date_str, '%Y-%m-%d %H:%M:%S')
                        if log_date >= one_year_ago:
                            cleaned_lines.append(line)
                    except (IndexError, ValueError):
                        # Skip malformed lines
                        continue
            
            # Write cleaned entries back to the file
            with open(log_file, 'w', encoding='utf-8') as f:
                f.writelines(cleaned_lines)
        
        # Add new log entry
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp},{user_id},{action}\n")
            
    except Exception as e:
        # Log the error but don't crash the application
        print(f"Error logging activity: {e}")
        
def get_function_name():
    """取得目前函數名稱"""
    return traceback.extract_stack(None, 2)[0][2]

def get_languages():
    """
    取得支援的國際化(I18N)語言清單
    
    此函數會讀取 L10N.json 檔案，並返回所有支援的語言代碼清單。
    預設會讀取 .env 中設定的 L10N_FILE 環境變數指定的檔案，
    若未設定則預設讀取 L10N.json。
    
    Returns:
        list: 包含所有支援語言代碼的列表
        
    Example:
        >>> languages = get_languages()
        >>> print(languages)
        ['en', 'zh-TW', 'ja']
        
    Note:
        需要確保 L10N.json 檔案存在且格式正確
        
    See Also:
        load_L10N: 載入完整的本地化字典
    """
    load_dotenv(".env")
    f_l10n = os.getenv("L10N_FILE", "L10N.json")
    
    # Read L10N.json which contains all supported languages
    with open(f_l10n) as f:
        data = f.read()
    js = json.loads(data)
    
    return list(js.keys())

def resolve_language(catalogs, language, default="US"):
    """Return the catalog key for ``language``.

    Exact matches win. Otherwise the comparison is case-insensitive, so
    ``spanish`` and ``SPANISH`` both select ``Spanish``. An unknown name
    falls back to ``default`` when that catalog exists.
    """
    if not isinstance(catalogs, dict) or not catalogs:
        return default
    if language in catalogs:
        return language
    if isinstance(language, str):
        folded = language.casefold()
        for key in catalogs:
            if isinstance(key, str) and key.casefold() == folded:
                return key
    if default in catalogs:
        return default
    folded_default = str(default).casefold()
    for key in catalogs:
        if isinstance(key, str) and key.casefold() == folded_default:
            return key
    return next(iter(catalogs))


def texts_for(catalogs, language, default="US"):
    """One language dictionary, or an empty dictionary when none are loaded."""
    if not isinstance(catalogs, dict):
        return {}
    return catalogs.get(resolve_language(catalogs, language, default), {}) or {}


def language_index(languages, current, default="US"):
    """Index of ``current`` in a language list, matched without case."""
    names = list(languages or [])
    if not names:
        return 0
    chosen = resolve_language({name: {} for name in names}, current, default)
    try:
        return names.index(chosen)
    except ValueError:
        return 0


# Operations-server catalog keys. Streamlit's L10N.json uses the same
# codes, so a subscriber's l10n and an article's l10n stay one value.
# 繁中 is Traditional Chinese (zh-Hant). US is English.
# 简中 is Simplified Chinese (zh-CN). The public switcher labels it CN.
# 日本語 and 한국어 are the L10N.json keys. The switcher labels them JP and KR.
# Danish, German, French, Lithuanian, Polish, and Spanish are the
# L10N.json keys too. The switcher labels them DK, DE, FR, LT, PL, and ES.
OPS_SIMPLIFIED = "简中"
OPS_TRADITIONAL = "繁中"
OPS_JAPANESE = "日本語"
OPS_KOREAN = "한국어"
OPS_DANISH = "Danish"
OPS_GERMAN = "German"
OPS_FRENCH = "French"
OPS_LITHUANIAN = "Lithuanian"
OPS_POLISH = "Polish"
OPS_SPANISH = "Spanish"
OPS_ENGLISH = "US"
OPS_LANG_LABELS = {
    OPS_TRADITIONAL: OPS_TRADITIONAL,
    OPS_SIMPLIFIED: "CN",
    OPS_JAPANESE: "JP",
    OPS_KOREAN: "KR",
    OPS_DANISH: "DK",
    OPS_GERMAN: "DE",
    OPS_FRENCH: "FR",
    OPS_LITHUANIAN: "LT",
    OPS_POLISH: "PL",
    OPS_SPANISH: "ES",
    OPS_ENGLISH: OPS_ENGLISH,
}
OPS_HTML_LANG = {
    OPS_TRADITIONAL: "zh-Hant",
    OPS_SIMPLIFIED: "zh-CN",
    OPS_JAPANESE: "ja",
    OPS_KOREAN: "ko",
    OPS_DANISH: "da",
    OPS_GERMAN: "de",
    OPS_FRENCH: "fr",
    OPS_LITHUANIAN: "lt",
    OPS_POLISH: "pl",
    OPS_SPANISH: "es",
    OPS_ENGLISH: "en",
}
# Request names that select a catalog. The stored code is always the key.
# A bare ``zh`` selects 繁中, the original Chinese catalog. ``zh-CN`` and
# ``zh-Hans`` are listed in full so they still select 简中.
_OPS_LANG_ALIASES = {
    "cn": OPS_SIMPLIFIED,
    "zh-cn": OPS_SIMPLIFIED,
    "zh_cn": OPS_SIMPLIFIED,
    "zh-hans": OPS_SIMPLIFIED,
    "zh_hans": OPS_SIMPLIFIED,
    "zh-sg": OPS_SIMPLIFIED,
    "简体中文": OPS_SIMPLIFIED,
    "簡體中文": OPS_SIMPLIFIED,
    "简体": OPS_SIMPLIFIED,
    "簡體": OPS_SIMPLIFIED,
    "zh-tw": OPS_TRADITIONAL,
    "zh_tw": OPS_TRADITIONAL,
    "zh-hant": OPS_TRADITIONAL,
    "zh_hant": OPS_TRADITIONAL,
    "zh-hk": OPS_TRADITIONAL,
    "zh_hk": OPS_TRADITIONAL,
    "zh-mo": OPS_TRADITIONAL,
    "zh": OPS_TRADITIONAL,
    "繁體中文": OPS_TRADITIONAL,
    "繁体中文": OPS_TRADITIONAL,
    "繁體": OPS_TRADITIONAL,
    "jp": OPS_JAPANESE,
    "ja": OPS_JAPANESE,
    "ja-jp": OPS_JAPANESE,
    "ja_jp": OPS_JAPANESE,
    "japanese": OPS_JAPANESE,
    "日文": OPS_JAPANESE,
    "日語": OPS_JAPANESE,
    "日语": OPS_JAPANESE,
    "kr": OPS_KOREAN,
    "ko": OPS_KOREAN,
    "ko-kr": OPS_KOREAN,
    "ko_kr": OPS_KOREAN,
    "korean": OPS_KOREAN,
    "韓文": OPS_KOREAN,
    "韩文": OPS_KOREAN,
    "韓國語": OPS_KOREAN,
    "韩国语": OPS_KOREAN,
    "dk": OPS_DANISH,
    "da": OPS_DANISH,
    "da-dk": OPS_DANISH,
    "da_dk": OPS_DANISH,
    "dansk": OPS_DANISH,
    "de": OPS_GERMAN,
    "de-de": OPS_GERMAN,
    "de_de": OPS_GERMAN,
    "deutsch": OPS_GERMAN,
    "fr": OPS_FRENCH,
    "fr-fr": OPS_FRENCH,
    "fr_fr": OPS_FRENCH,
    "francais": OPS_FRENCH,
    "français": OPS_FRENCH,
    "lt": OPS_LITHUANIAN,
    "lt-lt": OPS_LITHUANIAN,
    "lt_lt": OPS_LITHUANIAN,
    "lietuviu": OPS_LITHUANIAN,
    "lietuvių": OPS_LITHUANIAN,
    "pl": OPS_POLISH,
    "pl-pl": OPS_POLISH,
    "pl_pl": OPS_POLISH,
    "polski": OPS_POLISH,
    "es": OPS_SPANISH,
    "es-es": OPS_SPANISH,
    "es_es": OPS_SPANISH,
    "espanol": OPS_SPANISH,
    "español": OPS_SPANISH,
    "en": OPS_ENGLISH,
    "en-us": OPS_ENGLISH,
    "en_us": OPS_ENGLISH,
    "en-gb": OPS_ENGLISH,
    "en_gb": OPS_ENGLISH,
    "english": OPS_ENGLISH,
}


def ops_lang_label(lang):
    """Visible name for an operations-server language code.

    简中 is CN, 日本語 is JP, and 한국어 is KR. Danish is DK, German is
    DE, French is FR, Lithuanian is LT, Polish is PL, and Spanish is ES.
    """
    return OPS_LANG_LABELS.get(lang, lang)


def ops_html_lang(lang):
    """BCP 47 tag for an operations-server catalog key."""
    return OPS_HTML_LANG.get(lang, "en")


def _ops_alias(token, names):
    """Catalog key for one language token, or None when it is not offered."""
    if token in names:
        return token
    folded = token.casefold()
    alias = _OPS_LANG_ALIASES.get(folded)
    if alias in names:
        return alias
    for key in names:
        if isinstance(key, str) and key.casefold() == folded:
            return key
    primary = folded.split("-", 1)[0].split("_", 1)[0]
    if primary and primary != folded:
        alias = _OPS_LANG_ALIASES.get(primary)
        if alias in names:
            return alias
    return None


def normalize_ops_lang(lang, options, default=None):
    """Catalog key for an operations-server language request.

    Exact keys win. ``CN``, ``zh-CN``, and ``zh-Hans`` select ``简中``
    when that catalog is present. ``JP``, ``ja``, and ``ja-JP`` select
    ``日本語``. ``KR``, ``ko``, and ``ko-KR`` select ``한국어``.
    ``DK``, ``da``, and ``da-DK`` select ``Danish``. ``DE``, ``de``,
    and ``de-DE`` select ``German``; other ``de-*`` regions do too.
    ``FR``, ``fr``, and ``fr-*`` select ``French``. ``LT``, ``lt``,
    and ``lt-LT`` select ``Lithuanian``. ``PL``, ``pl``, and ``pl-PL``
    select ``Polish``. ``ES``, ``es``, and ``es-*`` select ``Spanish``.
    Other names match without case (``us`` selects ``US``, ``german``
    selects ``German``). A regional tag such as ``en-AU`` or ``de-AT``
    uses its primary language when that alias is offered. Unknown names
    return ``default`` when that key is in ``options``, otherwise None.
    """
    names = list(options or [])
    if lang in names:
        return lang
    if isinstance(lang, str):
        token = lang.strip()
        if token:
            chosen = _ops_alias(token, names)
            if chosen:
                return chosen
    if default in names:
        return default
    return None


def _accept_language_tags(header):
    """Language tags from an Accept-Language value, highest quality first."""
    if header is None:
        return []
    if isinstance(header, str):
        ranges = []
        for index, part in enumerate(header.split(",")):
            piece = part.strip()
            if not piece:
                continue
            bits = [bit.strip() for bit in piece.split(";")]
            tag = bits[0]
            quality = 1.0
            for bit in bits[1:]:
                if bit.lower().startswith("q="):
                    try:
                        quality = float(bit.split("=", 1)[1])
                    except ValueError:
                        quality = 0.0
            ranges.append((quality, index, tag))
        ranges.sort(key=lambda item: (-item[0], item[1]))
        return [tag for quality, _index, tag in ranges if quality > 0 and tag]
    ranges = []
    for index, item in enumerate(header):
        if isinstance(item, str):
            if item.strip():
                ranges.append((1.0, index, item.strip()))
            continue
        if isinstance(item, (tuple, list)) and item and isinstance(item[0], str):
            quality = item[1] if len(item) > 1 else 1
            try:
                quality = float(quality)
            except (TypeError, ValueError):
                quality = 0.0
            if item[0].strip():
                ranges.append((quality, index, item[0].strip()))
    ranges.sort(key=lambda item: (-item[0], item[1]))
    return [tag for quality, _index, tag in ranges if quality > 0]


def match_accept_language(header, options):
    """Catalog key for the best Accept-Language match, or None.

    Tags are tried in quality order. ``ja`` and ``ja-JP`` select
    ``日本語`` when that catalog is present. ``ko`` and ``ko-KR`` select
    ``한국어``. ``da`` selects ``Danish``, ``de`` and ``de-*`` select
    ``German``, ``fr`` and ``fr-*`` select ``French``, ``lt`` selects
    ``Lithuanian``, ``pl`` selects ``Polish``, and ``es`` and ``es-*``
    select ``Spanish``, when that catalog is present. A tag that names
    no catalog is skipped. ``*`` is ignored.
    """
    names = list(options or [])
    for tag in _accept_language_tags(header):
        if tag == "*":
            continue
        chosen = normalize_ops_lang(tag, names)
        if chosen:
            return chosen
    return None


def session_texts(default="US"):
    """Texts for the language stored in the Streamlit session."""
    catalogs = st.session_state.get("ui_context")
    app = st.session_state.get("app_context") or {}
    language = app.get("language", default) if isinstance(app, dict) else default
    return texts_for(catalogs, language, default)

@st.cache_data(ttl=300)
def load_L10N(base=None):
    """
    Load supported localization dictionaries, which 
    are specified in L10N.json file. 
    
    Args:
        base (str, optional): Base directory
    
    Returns:
        dict: Dictionary containing all supported languages
    """
    load_dotenv(".env")
    f_l10n = os.getenv("L10N_FILE", "L10N.json")
    
    # Read L10N.json which contains all supported languages
    with open(f_l10n) as f:
        data = f.read()
    js = json.loads(data)
    
    dl10n = {}
    for key, fl in js.items():
        with open(fl) as f:
            data = f.read()
        d = json.loads(data)
        dl10n[key] = d
    
    return dl10n

# Helper function to format timestamps
def format_timestamp(ts) -> str:
    """
    格式化時間戳記為易讀字串
    
    Args:
        ts: 時間戳記 (可以是 datetime 對象或字串)
                        
    Returns:
        str: 格式化後的時間字串，若解析失敗則返回原始字串
    """
    if not ts:
        return "Never"
                        
    # 如果是 datetime 對象，直接格式化
    if isinstance(ts, datetime):
        return ts.strftime('%Y-%m-%d %H:%M:%S')
                        
    # 如果是字串，嘗試解析
    ts_str = str(ts)
    try:
        # 嘗試 ISO 8601 格式 (包含 'T' 分隔符)
        if 'T' in ts_str:
            date_time = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        # 嘗試空格分隔的格式
        else:
            # 嘗試帶有微秒的格式
            for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
                try:
                    date_time = datetime.strptime(ts_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return ts_str  # 所有格式都失敗，返回原始字串
            return date_time.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts_str  # 解析失敗，返回原始字串

def _app_path(path):
    """Resolve a config path from the application root."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parent / candidate
    return candidate


def load_menu(fn):
    """Load the operations-server menu JSON."""
    with open(_app_path(fn), encoding="utf-8") as handle:
        return json.load(handle)


def load_page_cat(json_file):
    """Load page-to-article-category mapping for the operations server."""
    with open(_app_path(json_file), encoding="utf-8") as handle:
        return json.load(handle)


def load_ops_L10N():
    """Load the operations-server catalogs (separate from the Streamlit L10N files)."""
    load_dotenv(".env")
    index_name = os.getenv("OPS_L10N_FILE", "ops_L10N.json")
    with open(_app_path(index_name), encoding="utf-8") as handle:
        listing = json.load(handle)
    catalogs = {}
    for key, filename in listing.items():
        with open(_app_path(filename), encoding="utf-8") as handle:
            catalogs[key] = json.load(handle)
    return catalogs


def test_func():
    print(f"Function name: {get_function_name()}")
                        
if __name__ == '__main__':
    """
    Function test code
    """
    test_func()