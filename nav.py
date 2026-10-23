"""Role-aware navigation and the server-side page gate.

Pages call ``require_role`` before they read family data. The sidebar
draws the same links for a role on every page, using the strings already
in the language files.
"""
import html

import streamlit as st

import context_utils as cu
import db_utils as dbm
import funcUtils as fu

_ALL = (
    dbm.User_State["p_admin"],
    dbm.User_State["f_admin"],
    dbm.User_State["f_member"],
)
_ADMINS = (
    dbm.User_State["p_admin"],
    dbm.User_State["f_admin"],
)
_PLATFORM = (dbm.User_State["p_admin"],)

# page, L10N keys, fallback label, icon, roles that may see the link.
# CSV and JSON stay proper nouns. Keys that a language file does not have
# yet fall back to the English label.
_LINKS = (
    ("fTrees.py", ("home",), "Home", "🏠", _ALL),
    ("pages/1_usrMgmt.py", ("user", "management"), "User Management", "👤", _PLATFORM),
    ("pages/2_famMgmt.py", ("family", "management"), "Family Management", "🌲", _ADMINS),
    ("pages/8_caseMgmt.py", ("case_mgmt",), "Case Management", "📋", _ADMINS),
    ("pages/9_birthday.py", ("birthday",), "Birthday", "🎂", _ADMINS),
    ("pages/6_show_3G.py", ("MENU_QUERY_TBL_BY_3GEN",), "Show 3 Generations", "👥", _ALL),
    ("pages/7_show_related.py", ("relation",), "Relation", "👨‍👩‍👧‍👦", _ALL),
    ("pages/3_csv_editor.py", (), "CSV", "🔧", _ALL),
    ("pages/4_json_editor.py", (), "JSON", "🪛", _ALL),
)

_HIDE_DEFAULT_NAV = """
<style>
[data-testid="stSidebarNav"] {
    display: none !important;
}
</style>
"""


def role_is_allowed(authenticated, role, allowed):
    """Return ``login``, ``denied``, or ``ok`` without touching Streamlit."""
    if not authenticated:
        return "login"
    if role not in tuple(allowed):
        return "denied"
    return "ok"


def _label(texts, keys, fallback):
    if not keys or not texts:
        return fallback
    parts = []
    for key in keys:
        value = texts.get(key) if hasattr(texts, "get") else None
        if not value:
            return fallback
        parts.append(str(value))
    return " ".join(parts)


def navigation_links(role, texts=None):
    """Links this role may open. ``texts`` is one language dictionary."""
    links = []
    for page, keys, fallback, icon, roles in _LINKS:
        if role not in roles:
            continue
        links.append({
            "page": page,
            "label": _label(texts, keys, fallback),
            "icon": icon,
        })
    return links


def _ui_texts():
    try:
        language = st.session_state.app_context.get("language", "US")
        return st.session_state.ui_context[language]
    except (AttributeError, KeyError, TypeError):
        try:
            return st.session_state.ui_context["US"]
        except (AttributeError, KeyError, TypeError):
            return {}


def _sidebar_title(role, texts):
    if role == dbm.User_State["p_admin"]:
        parts = ("platform", "admin", "sidebar")
        fallback = "Platform Admin Sidebar"
    elif role == dbm.User_State["f_admin"]:
        parts = ("family", "admin", "sidebar")
        fallback = "Family Admin Sidebar"
    else:
        parts = ("family", "member", "sidebar")
        fallback = "Family Member Sidebar"
    return _label(texts, parts, fallback)


def _email_banner():
    email = st.session_state.get("user_email")
    if not email:
        return
    safe = html.escape(str(email), quote=True)
    st.markdown(
        "<div style='background-color: #2e7d32; padding: 0.5rem; "
        "border-radius: 0.5rem; margin-bottom: 1rem;'>"
        "<p style='color: white; margin: 0; font-weight: bold; text-align: center;'>"
        f"{safe}</p></div>",
        unsafe_allow_html=True,
    )
    cu.update_context({"email_user": email})


def render_sidebar():
    """Draw the shared sidebar: hidden default nav, role links, logout."""
    st.markdown(_HIDE_DEFAULT_NAV, unsafe_allow_html=True)
    texts = _ui_texts()
    role = st.session_state.get("user_state")
    with st.sidebar:
        st.title(_sidebar_title(role, texts))
        _email_banner()
        st.subheader(texts.get("navigation", "Navigation"))
        for link in navigation_links(role, texts):
            st.page_link(link["page"], label=link["label"], icon=link["icon"])
        if st.button(
            texts.get("logout", "Logout"),
            type="primary",
            use_container_width=True,
            key="nav_logout",
        ):
            email = st.session_state.get("user_email")
            if email:
                fu.log_activity(email, "logout")
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()


def require_role(*allowed):
    """Stop the page unless the signed-in user has one of ``allowed`` roles.

    An anonymous visitor is sent back to the login page. A signed-in user
    with the wrong role sees the permission error and the page does not
    read its data.
    """
    decision = role_is_allowed(
        bool(st.session_state.get("authenticated", False)),
        st.session_state.get("user_state"),
        allowed,
    )
    if decision == "login":
        st.switch_page("fTrees.py")
        st.stop()
    if decision == "denied":
        st.error(_ui_texts().get("permission_error", "Need permission to access this page."))
        st.stop()
