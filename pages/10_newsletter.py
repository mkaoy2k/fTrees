"""
Newsletter Publication Page

This page provides functionality for publishing newsletters in
various languages.
"""
import streamlit as st
from fTrees import show_padmin_sidebar
import context_utils as cu
import funcUtils as fu
import db_articles as dbm
from db_connection import User_State

# Initialize session state
cu.init_session_state()
language = st.session_state.app_context.get('language') or "US"
UI_TEXTS = st.session_state.ui_context.get(language, st.session_state.ui_context.get("US", {}))

# Initialize newsletter_password if not present (for ops_svr authentication)
if 'newsletter_password' not in st.session_state:
    st.session_state.newsletter_password = ''

# Check authentication
if not st.session_state.get('authenticated', False):
    st.switch_page("fTrees.py")
    
# Show admin sidebar
show_padmin_sidebar()

# Main content
st.header(f"{UI_TEXTS['newsletter']} {UI_TEXTS['publication']}")

st.subheader(f"{UI_TEXTS['newsletter']}")

context = st.session_state.get('app_context', cu.init_context())
own_family_id = cu.current_family_id()
is_platform = st.session_state.get("user_state") == User_State["p_admin"]
# Platform admin sees all families' languages, family admin sees only their own
lang_list = dbm.get_article_languages(family_id=own_family_id, all_families=is_platform)
current_lang = context.get('language')
# Default to index 0 if current language is not in the list
try:
    index = lang_list.index(current_lang) if current_lang in lang_list else 0
except ValueError:
    index = 0
l10n = st.selectbox(f"{UI_TEXTS['select']} {UI_TEXTS['language']}",
                   lang_list,
                   index=index)
cu.update_context({'language': l10n})

# Password input for ops_svr authentication
password = st.text_input(f"{UI_TEXTS['password']}", type="password", key="newsletter_password")

if st.button(f"{UI_TEXTS['publish']} {UI_TEXTS['language']}:{l10n}", type="primary"):
    with st.spinner(f"{UI_TEXTS['publish']} {UI_TEXTS['in_progress']} ..."):
        try:
           # Define CSS styles
           css_style = """
           <style>
               @keyframes blinker {
                   50% { opacity: 0.5; }
               }
               .publish-message {
                   font-size: 24px;
                   font-weight: bold;
                   animation: blinker 1s linear infinite;
                   color: #1f77b4;
               }
           </style>
           """
           # Display publication message and link
           ops_svr = context.get('ops_svr')
           
           st.markdown(css_style, unsafe_allow_html=True)
           st.markdown(f'<div class="publish-message">{UI_TEXTS["confirm"]}: {UI_TEXTS["publish"]} {UI_TEXTS["language"]}:{l10n}, click the link below:</div>', 
                       unsafe_allow_html=True)
           st.markdown(f'<div class="publish-message" style="font-size: 50px;"><a href="{ops_svr}/pub?family_id={own_family_id}&lang={l10n}&email={st.session_state.user_email}&password={password}" target="_blank">FamilyTreesOps</a></div>', 
                       unsafe_allow_html=True)
        except Exception as e:
            st.error(f"️❌ {fu.get_function_name()}: {UI_TEXTS['publish']} {UI_TEXTS['language']}: {l10n}: {str(e)} {UI_TEXTS['failed']}")

st.markdown("---")
st.subheader(f"{UI_TEXTS['navigation']}")

col1, col2 = st.columns(2)
with col1:
    if st.button(f"← {UI_TEXTS['back']}"):
        st.switch_page("fTrees.py")
        
with col2:
    if st.button(f"{UI_TEXTS['subscriber']} {UI_TEXTS['management']}"):
        st.switch_page("pages/1_usrMgmt.py")
