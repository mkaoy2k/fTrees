import os
from dotenv import load_dotenv  # pip install python-dotenv
import json
import logging
import streamlit as st  # pip install streamlit
from datetime import datetime, timedelta
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

@st.cache_data(ttl=300)
def get_1st_mbr_dict(df, mem, born, base=None):
    """
    Find the first record in the DataFrame that matches the given conditions
    
    Args:
        df (pd.DataFrame): DataFrame to search
        mem (str): Member name
        born (int): Birth year
        base (str, optional): Base directory
    
    Returns:
        tuple: (index, member_dict)
            index: Record index
            member_dict: Member data dictionary
    
    Raises:
        FileNotFoundError: If no record matches the given conditions
    """
    filter = "Name == @mem and Born == @born"
    try:
        rec = df.query(filter)
        if rec.empty:
            raise FileNotFoundError("No record matches the given conditions")
    except Exception:
        raise
    
    # Remove duplicate records, keep only the first one
    rec = rec[0:1]
    idx, member = rec.to_dict('index').popitem()
    return idx, member

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

def test_func():
    print(f"Function name: {get_function_name()}")
                        
if __name__ == '__main__':
    """
    Function test code
    """
    test_func()