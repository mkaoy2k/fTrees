
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
            # Get members born in the selected month
            members = dbm.get_members_when_born_in(month_number)
            
            if not members:
                message = f"⚠️ {fu.get_function_name()}: {UI_TEXTS['members']} {UI_TEXTS['not_found']}"
                st.warning(message)
                return
            
            # Create a list to hold all member data
            member_data = []
            
            # Process each member and collect their data
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
        
            # Create DataFrame from the collected data
            df = pd.DataFrame(member_data)
            
            # Ensure all date columns are strings
            date_columns = ['Birthday']
            for col in date_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
        
            # save to csv, created in the dir_path, specified in the context fss
            csv_file = f"{st.session_state.app_context['fss']['dir_path']}/birthday_list_{selected_month.lower()}_{datetime.now().year}.csv"
            # Display the results first
            st.dataframe(
                df,
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
            
            # Save to CSV
            try:
                df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                message = f"✅ {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['saved']}: {csv_file}"
                st.info(message)
            except Exception as e:
                message = f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['error']}"
                log.error(message, exc_info=e)
                st.error(message)
           
            # Create a row with two columns for the buttons
            if not df.empty:
                st.write("")
                
                # Define callback functions
                def on_publish():
                    # Create email publisher object
                    publisher = eu.EmailPublisher(eu.Config.MAIL_USERNAME, eu.Config.MAIL_PASSWORD)
                    
                    # Filter out None or empty email addresses
                    recipients = [m.get('email') for m in members if m.get('email')]
                    
                    if not recipients:
                        st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['email']} {UI_TEXTS['not_found']}")
                        return
                    
                    # Rest of the email sending code...
                    text_content = """Wishing you a wonderful birthday celebration!
                    May this special day bring you joy and happiness!

                    Best regards,
                    Your Family Team"""
                                            
                    # Check if the attached b'day card file exists
                    card_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bday.html")
                    if not os.path.exists(card_file):
                        st.error(f"❌ {fu.get_function_name()} {card_file} {UI_TEXTS['not_found']}")
                        return
                    # Create HTML content with animated birthday card
                    html_content = open(card_file, 'r').read()
                    # Display the HTML content properly
                    st.components.v1.html(html_content, height=500)
                    
                    # Send email with the animated birthday card
                    publisher.publish_email(
                        subject=f"🎉 Happy Birthday Celebrations - {selected_month} {datetime.now().year}",
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
                            file_name=f"birthday_list_{selected_month.lower()}_{datetime.now().year}.csv",
                            mime="text/csv",
                            key="download_csv"
                        )
                        st.success(f"✅ {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['downloaded']}")
                    except Exception as e:
                        fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['download_error']}", e)
                
                # Create buttons with callbacks
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"📧 {UI_TEXTS['publish']} {UI_TEXTS['birthday']} {UI_TEXTS['list']}", 
                               use_container_width=True, 
                               type="primary",
                               on_click=on_publish):
                        pass  # Callback handles the action
                
                with col2:
                    if st.button(f"💾 {UI_TEXTS['download']} {UI_TEXTS['birthday']} {UI_TEXTS['list']}", 
                               use_container_width=True, 
                               type="secondary",
                               on_click=on_download):
                        pass  # Callback handles the action
        except Exception as e:
            message = f"❌ {fu.get_function_name()} {UI_TEXTS['birthday']} {UI_TEXTS['list']} {UI_TEXTS['download_error']}"
            log.error(message, exc_info=e)
            st.session_state.birthday_message = message
            st.error(message)

def sidebar() -> None:
    """Sidebar application entry point."""
    global UI_TEXTS
    # Sidebar --- from here
    with st.sidebar:
        if st.session_state.user_state == dbm.User_State['p_admin']:
            # Show default navigation for padmin users
            if 'user_email' in st.session_state and st.session_state.user_email:
                st.markdown(
                    f"<div style='background-color: #2e7d32; padding: 0.5rem; border-radius: 0.5rem; margin: 1rem 0;'>"
                    f"<p style='color: white; margin: 0; font-weight: bold; text-align: center;'>{st.session_state.user_email}</p>"
                    "</div>",
                    unsafe_allow_html=True)
                cu.update_context({
                    'email_user': st.session_state.user_email
                })
                
                # Add logout button at the bottom for admin
                if st.button(f"{UI_TEXTS['logout']}", type="primary", use_container_width=True, key="fam_mgmt_admin_logout"):
                    # Log logout activity
                    if 'user_email' in st.session_state and st.session_state.user_email:
                        fu.log_activity(st.session_state.user_email, 'logout')

                    st.session_state.authenticated = False
                    st.session_state.user_email = None
                    st.rerun()
        else:
            # For non-admin users
            # Hide the default navigation for non-padmin users
            st.markdown("""
            <style>
                [data-testid="stSidebarNav"] {
                    display: none !important;
                }
            </style>""", unsafe_allow_html=True)
            
            if 'user_email' in st.session_state and st.session_state.user_email:
                st.markdown(
                    f"<div style='background-color: #2e7d32; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 1rem;'>"
                    f"<p style='color: white; margin: 0; font-weight: bold; text-align: center;'>{st.session_state.user_email}</p>"
                    "</div>",
                    unsafe_allow_html=True)
                cu.update_context({
                    'email_user': st.session_state.user_email
                })
            
            st.subheader(f"{UI_TEXTS['navigation']}")
            st.page_link("fTrees.py", label="Home", icon="🏠")
            # st.page_link("pages/5_ftpe.py", label="FamilyTreePE", icon="📊")
            if st.session_state.user_state == dbm.User_State['f_admin']:
                st.page_link("pages/2_famMgmt.py", label="Family Management", icon="🌲")
                st.page_link("pages/8_caseMgmt.py", label="Case Management", icon="📋")
            st.page_link("pages/6_show_3G.py", label="Show 3 Generations", icon="👥")
            st.page_link("pages/7_show_related.py", label="Show Related", icon="👨‍👩‍👧‍👦")
            st.page_link("pages/3_csv_editor.py", label="CSV Editor", icon="🔧")
            st.page_link("pages/4_json_editor.py", label="JSON Editor", icon="🪛")
             
            # Add logout button at the bottom for non-admin users
            if st.button(f"{UI_TEXTS['logout']}", type="primary", use_container_width=True, key="fam_mgmt_user_logout"):
                # Log logout activity
                if 'user_email' in st.session_state and st.session_state.user_email:
                    fu.log_activity(st.session_state.user_email, 'logout')
                st.session_state.authenticated = False
                st.session_state.user_email = None
                st.rerun()
    
def main():
    """Main application entry point."""
    global UI_TEXTS
    
    st.header(f"🎂 {UI_TEXTS['birthday_of_the_month']}")
    
    # Main Page --- frome here
    birthday_of_the_month_page()
        
if 'app_context' not in st.session_state:
    st.session_state.app_context = cu.init_context()
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
    sidebar()
    main()