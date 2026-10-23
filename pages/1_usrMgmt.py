"""
# Add parent directory to path to allow absolute imports
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))


User Management Page

This page provides user management functionality including:
- Managing users
"""
import streamlit as st
import pandas as pd
import db_utils as dbm
from fTrees import show_padmin_sidebar, show_front_end
import context_utils as cu
import funcUtils as fu
import auth_utils as au

def format_timestamps(df, timezone="UTC"):
    """Format UTC timestamps in an IANA timezone.

    Naive database values are treated as UTC. Unknown timezone names fall
    back to UTC so a bad setting does not blank the user table.
    """
    zone = timezone or "UTC"
    for col in ['created_at', 'updated_at']:
        if col in df.columns:
            converted = pd.to_datetime(df[col], utc=True, errors="coerce")
            try:
                converted = converted.dt.tz_convert(zone)
            except Exception:
                converted = converted.dt.tz_convert("UTC")
            df[col] = converted.dt.strftime('%Y-%m-%d %H:%M:%S')
    return df


def display_timezone():
    """Timezone chosen in Settings, defaulting to UTC."""
    context = st.session_state.get("app_context") or {}
    return context.get("timezone") or "UTC"

def show_page():
    # Get UI texts from session state
    global UI_TEXTS
    from fTrees import UI_TEXTS  # 確保從 fTrees 導入 UI_TEXTS
    
    # Initialize logging
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    try:
        logger.debug("Initializing show_page")
        
        # Get context from session state
        logger.debug(f"Context: {st.session_state.app_context}")
        
        if st.session_state.user_state == dbm.User_State['p_admin']:
            # Show admin sidebar
            show_padmin_sidebar()
        else:
            st.error(f"❌ {fu.get_function_name()}: {UI_TEXTS['permission_error']}")
            return
        
    except Exception as e:
        logger.error(f"❌ {fu.get_function_name()}: {UI_TEXTS['admin_init_error']}: {str(e)}", exc_info=True)
        fu.show_user_error(f"❌ {fu.get_function_name()}: {UI_TEXTS['admin_init_error']}", e)
        return
    
    try:
        st.header(f"{UI_TEXTS['user']} {UI_TEXTS['management']}")
        show_front_end()
        df = pd.DataFrame()
        
        # Subscriber Management
        with st.container(border=True):
            st.subheader(f"{UI_TEXTS['subscriber']} {UI_TEXTS['management']}")
            btn11, btn12, btn13, btn14 = st.columns([5,5,5,5])
            info1, info2, info3 = st.columns([18,1,1])
            with btn11:
                if st.button(f"{UI_TEXTS['active']}", type="secondary", key="active_subscriber_btn"):
                    users = dbm.get_subscribers(state="active")
                    if users:
                        df = pd.DataFrame(users, columns=users[0].keys())
                        df = format_timestamps(df, display_timezone())
                        with info1:
                            st.info(f"{UI_TEXTS['active']} {UI_TEXTS['subscriber']} {UI_TEXTS['count']}: {len(users)}")
                            st.dataframe(df)
                    else:
                        with info1:
                            st.info(f"{UI_TEXTS['active']} {UI_TEXTS['subscriber']} {UI_TEXTS['not_found']}")    
            with btn12:
                if st.button(f"{UI_TEXTS['inactive']}", type="secondary", key="inactive_subscriber_btn"):
                    users = dbm.get_subscribers(state="inactive")
                    if users:
                        df = pd.DataFrame(users, columns=users[0].keys())
                        df = format_timestamps(df, display_timezone())
                        with info1:
                            st.info(f"{UI_TEXTS['inactive']} {UI_TEXTS['subscriber']} {UI_TEXTS['count']}: {len(users)}")
                            st.dataframe(df)
                    else:
                        with info1:
                            st.info(f"{UI_TEXTS['inactive']} {UI_TEXTS['subscriber']} {UI_TEXTS['not_found']}")
            with btn13:
                if st.button(f"{UI_TEXTS['pending']}", type="secondary", key="pending_subscriber_btn"):
                    users = dbm.get_subscribers(state="pending")
                    if users:
                        df = pd.DataFrame(users, columns=users[0].keys())
                        df = format_timestamps(df, display_timezone())
                        with info1:
                            st.info(f"{UI_TEXTS['pending']} {UI_TEXTS['subscriber']} {UI_TEXTS['count']}: {len(users)}")
                            st.dataframe(df)
                    else:
                        with info1:
                            st.info(f"{UI_TEXTS['pending']} {UI_TEXTS['subscriber']} {UI_TEXTS['not_found']}") 
                            
            with btn14:
                if st.button(f"{UI_TEXTS['all']}", type="secondary", key="all_subscriber_btn"):
                    users = dbm.get_subscribers('all')
                    if users:
                        df = pd.DataFrame(users, columns=users[0].keys())
                        df = format_timestamps(df, display_timezone())
                        with info1:
                            st.info(f"{UI_TEXTS['subscriber']} {UI_TEXTS['count']}: {len(users)}")
                            st.dataframe(df)
                    else:
                        with info1:
                            st.info(f"{UI_TEXTS['subscriber']} {UI_TEXTS['not_found']}")

            # Create 2 columns for better layout
            col21, col22 = st.columns([2,1])
            with col21:
                email_value = st.session_state.get('user_email', '')
                logger.debug(f"Setting email input with value: {email_value}")
                email = st.text_input(
                    f":blue[{UI_TEXTS['email']}]:", 
                    value=email_value, 
                    key="subscriber_email"
                )
                email = email.strip()
                
            with col22:
                lang_list = st.session_state.app_context.get('languages', ['US'])
                current_lang = st.session_state.app_context.get('language', 'US')
                logger.debug(f"Languages: {lang_list}, Current: {current_lang}")
                
                # Ensure the current language is in the list to avoid ValueError
                default_index = 0
                if current_lang in lang_list:
                    default_index = lang_list.index(current_lang)
                l10n = st.selectbox(
                    f':blue[{UI_TEXTS["language"]}]:', 
                    lang_list,
                    index=default_index,
                    key="subscriber_language"
                )
            # Create the info31 column outside the query block to ensure it's always visible
            info31, info32 = st.columns([18,1])
            
            # Initialize user as None
            user = None
            
            col1, col2 = st.columns(2)
            with col2:
                if st.button(f"{UI_TEXTS['refresh']}", type="secondary", key="refresh_subscriber_btn", use_container_width=True):
                    st.rerun()
            with col1:
                if st.button(f"{UI_TEXTS['query']} {UI_TEXTS['subscriber']}", type="primary", key="query_subscriber_btn", use_container_width=True):
                    user = dbm.get_subscriber(email)
                
            # Always show the subscriber details section, 
            # but only show content if user exists
            with info31:
                st.write(f':blue[{UI_TEXTS["subscriber"]} {UI_TEXTS["details"]}]:')
                
                if user is not None:
                    # Create three columns for better layout
                    col41, col42, col43 = st.columns([5,5,5])
                    
                    # Display user data in a vertical format
                    for i, (key, value) in enumerate(user.items()):
                        # Convert timestamp to local time if needed
                        if key in ['created_at', 'updated_at'] and value is not None:
                            value = pd.to_datetime(value, utc=True).tz_convert('America/Los_Angeles').strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Alternate between columns for better space usage
                        if i % 3 == 0:
                            col41.write(f"**{key.replace('_', ' ').title()}:** {value}")
                        elif i % 3 == 1:
                            col42.write(f"**{key.replace('_', ' ').title()}:** {value}")
                        else:
                            col43.write(f"**{key.replace('_', ' ').title()}:** {value}")
                
                btn41, btn42, btn43 = st.columns([1,1,1])
                with btn41:
                    if st.button("Subscribe", type="secondary", key="subscribe_btn"):
                        success, message = dbm.add_subscriber(email, "By Platform Admin", lang=l10n)
                        if success:
                            cu.update_context({'language': l10n})
                            st.success(f"✅ {UI_TEXTS['successful']} {UI_TEXTS['subscription']}: {email}")
                        else:
                            st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['add']} {UI_TEXTS['subscriber']} {email} {UI_TEXTS['failed']}: {message}")
                with btn42:
                    if st.button("Unsubscribe", type="secondary", key="unsubscribe_btn"):
                        if dbm.remove_subscriber(email):
                            st.success(f"✅ {UI_TEXTS['unsubscribed']} {email} {UI_TEXTS['successfully']}")
                        else:
                            st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['unsubscribe']} {email} {UI_TEXTS['failed']}")
                with btn43:
                    with st.expander("Danger Zone", expanded=False):
                        st.warning(f"⚠️ {UI_TEXTS['cannot_be_undone']}!")
                        if st.button("Delete Subscriber by Email", type="secondary", key="delete_subscriber_btn"):
                            if dbm.delete_subscriber(email):
                                st.success(f"✅ {UI_TEXTS['delete']} {UI_TEXTS['subscriber']} {email} {UI_TEXTS['successfully']}")
                            else:
                                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['delete']} {UI_TEXTS['subscriber']} {email} {UI_TEXTS['failed']}")
    
        # Create Family Admin/Members
        with st.form("create_member_form"):
            st.subheader(f"{UI_TEXTS['create']} {UI_TEXTS['family']} {UI_TEXTS['admin']} {UI_TEXTS['or']} {UI_TEXTS['member']}")

            col1, col2, col3 = st.columns(3)
            with col1:
                role = st.radio(
                    f':blue[{UI_TEXTS["role"]}]:', 
                    ["Family Admin", "Family Member"],
                    index=0,
                    horizontal=True,
                    key="new_member_role")
                new_email = st.text_input(
                    f':blue[{UI_TEXTS["email"]}]:',
                    help=f"{UI_TEXTS['enter']} {UI_TEXTS['email']}",
                    key="new_member_email")
            
            with col2:
                new_password = st.text_input(
                    f':blue[{UI_TEXTS["password"]}]:', 
                    type="password", 
                    help=f"{UI_TEXTS['enter']} {UI_TEXTS['password']} ({UI_TEXTS['at_least_eight_characters']})",
                    key="new_member_password")
                confirm_password = st.text_input(
                    f':blue[{UI_TEXTS["password_confirmed"]}]:', 
                    type="password", 
                    help=f"{UI_TEXTS['confirm']} {UI_TEXTS['password']}",
                    key="new_member_confirm_password")
            
            with col3:
                family_id = st.number_input(
                    f':blue[{UI_TEXTS["family"]} {UI_TEXTS["id"]}]:', 
                    min_value=0,
                    step=1,
                    key="new_member_family_id")
                member_id = st.number_input(
                    f':blue[{UI_TEXTS["member"]} {UI_TEXTS["id"]}]:', 
                    min_value=0,
                    step=1,
                    key="new_member_member_id")
                # Ensure the current language is in the list to avoid ValueError
                default_index = 0
                if current_lang in lang_list:
                    default_index = lang_list.index(current_lang)
                l10n = st.selectbox(
                    f':blue[{UI_TEXTS["language"]}]:', 
                    lang_list,
                    index=default_index,
                    key="subscriber_language_2"
                )
            if new_password != confirm_password:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['password_error']}")
            submitted = st.form_submit_button(f"{UI_TEXTS['submit']}", type="primary")
            
            if submitted:
                if not new_email or not new_password or not confirm_password:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}")
                elif new_password != confirm_password:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['password_error']}")
                elif len(new_password) < 8:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['password']} {UI_TEXTS['at_least_eight_characters']}")
                else:
                    if role == "Family Admin":
                        role = dbm.User_State['f_admin']
                    else:
                        # Default to Family Member
                        role = dbm.User_State['f_member']
                    user_id = au.create_user(new_email, 
                                        new_password, 
                                        role=role,
                                        l10n=l10n,
                                        is_active=dbm.Subscriber_State['active'],
                                        family_id=family_id,
                                        member_id=member_id)
                    if user_id:
                        st.success(f"✅ {UI_TEXTS['create']} {UI_TEXTS['family']} {UI_TEXTS['admin']} {UI_TEXTS['or']} {UI_TEXTS['member']}: {user_id} {UI_TEXTS['successfully']}")
                        # The form will automatically clear on the next run
                    else:
                        st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['create']} {UI_TEXTS['family']} {UI_TEXTS['admin']} {UI_TEXTS['or']} {UI_TEXTS['member']} {UI_TEXTS['failed']}")
        
        with st.expander(f"{UI_TEXTS['danger_zone']}", expanded=False):
            st.warning(f"⚠️ {UI_TEXTS['cannot_be_undone']}")
            user_id = st.number_input(f"{UI_TEXTS['user']} {UI_TEXTS['id']}",
                                  min_value=1,
                                  max_value=100000,
                                  value=1)
            if st.button(f"{UI_TEXTS['delete']} {UI_TEXTS['user']}", type="primary"):
                if dbm.delete_user(user_id):
                    st.success(f"✅ {UI_TEXTS['delete']} {UI_TEXTS['user']}: {user_id} {UI_TEXTS['successfully']}")
                else:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['delete']} {UI_TEXTS['user']}: {user_id} {UI_TEXTS['failed']}")
    except Exception as err:
        fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['user_error']}", err)
    
# Streamlit runs this file as __main__. Tests can import format_timestamps.
if __name__ == "__main__":
    if 'app_context' not in st.session_state:
        cu.init_session_state()
    cu.apply_ui_preferences()

    if not st.session_state.get('authenticated', False):
        st.switch_page("fTrees.py")
    else:
        show_page()
