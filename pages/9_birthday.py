
"""
Birthday of the Month Page
"""
import os
import context_utils as cu
import streamlit as st
import db_utils as dbm
import pandas as pd
from datetime import datetime
import funcUtils as fu
import email_utils as eu
import logging
from nav import render_sidebar, require_role

log = logging.getLogger("ftpe")

def birthday_of_the_month_page():
    """Display members born in a specific month."""
    global UI_TEXTS
    st.header(f"🎂 {UI_TEXTS['birthday']} {UI_TEXTS['calendar']}")
    
    # Get current month as default
    current_month = datetime.now().month
    
    # Create two columns for month selection and display
    col1, col2 = st.columns([1, 3])
    
    with col1:
        # Month selection dropdown
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        selected_month = st.selectbox(
            f"{UI_TEXTS['select']} {UI_TEXTS['month']}", 
            options=months, 
            index=current_month-1,
            format_func=lambda x: f"{x}"
        )
        month_number = months.index(selected_month) + 1
    
    with col2:
        st.write("")
    
    if st.button(f"{UI_TEXTS['query']}", type="primary"):
        try:
            st.session_state.birthday_query = {
                "month": month_number,
                "label": selected_month,
                "members": dbm.get_members_when_born_in(month_number),
                "page": 0,
            }
        except Exception as e:
            message = f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['download_error']}"
            log.error(message, exc_info=e)
            st.session_state.birthday_message = message
            st.error(message)
            return

    query = st.session_state.get("birthday_query")
    if not query:
        return
    members = query.get("members") or []
    selected_label = query.get("label") or selected_month
    if not members:
        message = f"⚠️ {fu.get_function_name()}: {UI_TEXTS['members']} {UI_TEXTS['not_found']}"
        st.warning(message)
        return

    member_data = []
    for m in members:
        if m.get('sex') == 'M':
            gender = 'Male'
        elif m.get('sex') == 'F':
            gender = 'Female'
        else:
            gender = 'Unknown'
        member_data.append({
            'ID': m.get('id', ''),
            'Name': m.get('name', ''),
            'Gender': gender,
            'Birthday': fu.format_timestamp(m.get('born')),
            'Email': m.get('email', '')
        })

    df = pd.DataFrame(member_data)
    if 'Birthday' in df.columns:
        df['Birthday'] = df['Birthday'].astype(str)

    page_size = int(st.session_state.app_context.get("items_per_page") or cu.ITEMS_PER_PAGE)
    page = int(query.get("page") or 0)
    start = page * page_size
    view = df.iloc[start:start + page_size]
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            'ID': st.column_config.NumberColumn('ID'),
            'Name': st.column_config.TextColumn('Name'),
            'Gender': st.column_config.TextColumn('Gender'),
            'Birthday': st.column_config.TextColumn('Birthday'),
            'Email': st.column_config.TextColumn('Email')
        }
    )
    st.markdown(f"### {UI_TEXTS['page']} {page + 1} — {UI_TEXTS['count']}: {len(view)}")
    prev_col, next_col = st.columns(2)
    if page > 0 and prev_col.button(UI_TEXTS['back'], key="birthday_prev"):
        query["page"] = page - 1
        st.rerun()
    if start + page_size < len(df) and next_col.button("Next", key="birthday_next"):
        query["page"] = page + 1
        st.rerun()

    csv_file = f"{st.session_state.app_context['fss']['dir_path']}/birthday_list_{selected_label.lower()}_{datetime.now().year}.csv"
    try:
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        message = f"✅ {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['saved']}: {csv_file}"
        st.info(message)
    except Exception as e:
        message = f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['error']}"
        log.error(message, exc_info=e)
        st.error(message)

    if not df.empty:
        st.write("")

        def on_publish():
            stored = st.session_state.get("birthday_query") or {}
            everyone = stored.get("members") or []
            label = stored.get("label") or selected_label
            publisher = eu.EmailPublisher(eu.Config.MAIL_USERNAME, eu.Config.MAIL_PASSWORD)
            recipients = [m.get('email') for m in everyone if m.get('email')]
            if not recipients:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['email']} {UI_TEXTS['not_found']}")
                return
            text_content = """Wishing you a wonderful birthday celebration!
            May this special day bring you joy and happiness!

            Best regards,
            Your Family Team"""
            card_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bday.html")
            if not os.path.exists(card_file):
                st.error(f"❌ {fu.get_function_name()} {card_file} {UI_TEXTS['not_found']}")
                return
            html_content = open(card_file, 'r').read()
            st.components.v1.html(html_content, height=500)
            publisher.publish_email(
                subject=f"🎉 Happy Birthday Celebrations - {label} {datetime.now().year}",
                text=text_content,
                html=html_content,
                attached_file=card_file,
                recipients=recipients
            )
            st.success(f"✅ {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['published']}  {UI_TEXTS['count']}: {len(recipients)}")

        def on_download():
            try:
                csv_data = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"⬇️ {UI_TEXTS['download']} CSV",
                    data=csv_data,
                    file_name=f"birthday_list_{selected_label.lower()}_{datetime.now().year}.csv",
                    mime="text/csv",
                    key="download_csv"
                )
                st.success(f"✅ {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['downloaded']}")
            except Exception as e:
                fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['download_error']}", e)

        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"📧 {UI_TEXTS['publish']} {UI_TEXTS['birthday']} {UI_TEXTS['list']}",
                       use_container_width=True,
                       type="primary",
                       on_click=on_publish):
                pass
        with col2:
            if st.button(f"💾 {UI_TEXTS['download']} {UI_TEXTS['birthday']} {UI_TEXTS['list']}",
                       use_container_width=True,
                       type="secondary",
                       on_click=on_download):
                pass

def sidebar() -> None:
    """Sidebar application entry point."""
    render_sidebar()
    
def main():
    """Main application entry point."""
    global UI_TEXTS
    
    st.header(f"🎂 {UI_TEXTS['birthday_of_the_month']}")
    
    # Main Page --- frome here
    birthday_of_the_month_page()
        
if 'app_context' not in st.session_state:
    st.session_state.app_context = cu.init_context()
dbm.init_db()
cu.apply_ui_preferences()
    
# Get UI_TEXTS with a fallback to English if needed
try:
    UI_TEXTS = st.session_state.ui_context[st.session_state.app_context.get('language', 'US')]
except (KeyError, AttributeError):
    # Fallback to English if there's any issue
    UI_TEXTS = st.session_state.ui_context['US']

# Check authentication
if not st.session_state.get('authenticated', False):
    st.switch_page("fTrees.py")
else:
    require_role(dbm.User_State['p_admin'], dbm.User_State['f_admin'])
    sidebar()
    main()