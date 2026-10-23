"""
Family Management Page

This module provides a Streamlit interface for managing 
family members including:
searching, adding, updating, and deleting member information.
"""
import os
import context_utils as cu
import auth_utils as au
import streamlit as st
import db_utils as dbm
from fTrees import UI_TEXTS, search_members_page
import pandas as pd
from datetime import date
import funcUtils as fu
from pathlib import Path
from dotenv import load_dotenv
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# --- Initialize system environment --- from here
script_path = Path(__file__).resolve()
script_dir = script_path.parent
env_path = script_dir / '.env'

# 載入 .env 文件
load_dotenv(env_path, override=True)

# --- Set Server logging levels ---
g_logging = os.getenv("LOGGING", "INFO").strip('\"\'').upper()  # 預設為 INFO，並移除可能的引號

# 創建日誌器
logger = logging.getLogger(__name__)

# 設置日誌格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

# 設置控制台處理器
console_handler = logging.StreamHandler()

# 根據環境變數設置日誌級別
if g_logging == "DEBUG":
    logger.setLevel(logging.DEBUG)
    console_handler.setLevel(logging.DEBUG)
    logger.debug("Debug logging is enabled")
else:
    logger.setLevel(logging.INFO)
    console_handler.setLevel(logging.INFO)

console_handler.setFormatter(formatter)

# 移除所有現有的處理器，避免重複日誌
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 添加處理器到日誌器
logger.addHandler(console_handler)

# 確保根日誌器不會干擾
logging.basicConfig(level=logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

def search_families_page() -> None:
    """
    Display the family search page with filters and results.
    """
    global UI_TEXTS
    
    st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
    
    # Initialize session state for search results
    if 'family_search_results' not in st.session_state:
        st.session_state.family_search_results = []
    
    # Search form
    with st.form("family_search_form"):
        st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['criteria']}")
        
        # Create two rows of search fields
        row1_col1, row1_col2 = st.columns(2)
        row2_col1, row2_col2 = st.columns(2)
        
        with row1_col2:
            name = st.text_input(
                f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['name']}",
                key="search_family_name"
            )
        
        with row1_col1:
            family_id = st.number_input(
                f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
                min_value=0,
                value=0,
                step=1,
                key="search_family_id"
            )
            
        with row2_col2:
            background = st.text_area(
                f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['background']}")
            
        with row2_col1:
            url = st.text_input(
                f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['url']}",
                key="search_url")
        
        # add a search button
        submitted = st.form_submit_button(f"{UI_TEXTS['search']}", type="primary")
    
        # process search when form is submitted
        if submitted:
            # Validate required fields
            name = name.strip()
            background = background.strip()
            
            with st.spinner(
                f"{UI_TEXTS['search']} {UI_TEXTS['in_progress']} ..."):
                if family_id > 0:
                    # Get family by ID
                    family = dbm.get_family(family_id)
                    if family:
                        st.session_state.family_search_results = [family]
                    else:
                        st.session_state.family_search_results = []
                elif name:
                    # Get families by name-like
                    results = dbm.get_families_by_name(name)
                    if results:
                        st.session_state.family_search_results = results
                    else:
                        st.session_state.family_search_results = []
                elif background:
                    # Get families by background
                    results = dbm.get_families_by_background(background)
                    if results:
                        st.session_state.family_search_results = results
                    else:
                        st.session_state.family_search_results = []
                elif url:
                    # Get families by url-like
                    results = dbm.get_families_by_url(url)
                    if results:
                        st.session_state.family_search_results = results
                    else:
                        st.session_state.family_search_results = []
                else:
                    # Get all families
                    st.session_state.family_search_results = dbm.get_families()
            
            # display search results if available
            if st.session_state.family_search_results:
                st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['results']}")
        
                # convert results to dataframe for better display
                df = pd.DataFrame(st.session_state.family_search_results)
        
                # rename columns for better display
                if not df.empty:
                    # select and reorder columns
                    all_fields = ['id', 'name', 'background', 'url', 'created_at', 'updated_at']
            
                    # Filter out columns that don't exist in the results
                    existing_fields = [col for col in all_fields if col in df.columns]
                    df = df[existing_fields]
            
                    # Display the data in a table
                    st.dataframe(
                        df,
                        column_config={
                            'id': 'ID',
                            'name': 'Family Name',
                            'background': 'Background',
                            'url': 'Website',
                            'created_at': 'Created At',
                            'updated_at': 'Updated At'
                        },
                        hide_index=True,
                        use_container_width=True,
                        column_order=all_fields
                    )
            
                    # Show result count with bigger and bolder text
                    st.markdown(f"### {UI_TEXTS['search']} {UI_TEXTS['count']}: {len(df)}")
                else:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['search']} {UI_TEXTS['not_found']}")
    
            # No results message
            elif submitted:
                st.info(f"❌ {fu.get_function_name()} {UI_TEXTS['search']} {UI_TEXTS['not_found']}")

def add_family_page() -> None:
    """Display the form to add a new family."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['add']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
    
    with st.form("add_family_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input(
                f"{UI_TEXTS['family']} {UI_TEXTS['name']}", "", key="family_name_2")
            url = st.text_input(
                f"{UI_TEXTS['family']} {UI_TEXTS['url']}",
                "",
                placeholder="https://example.com",
                key="family_url_2"
            )
        
        with col2:
            background = st.text_area(
                f"{UI_TEXTS['family']} {UI_TEXTS['background']}",
                "",
                height=100,
                help="Enter any relevant family history or background information",
                key="family_background_2"
            )
        
        # Form submission button
        submitted = st.form_submit_button(f"{UI_TEXTS['add']} {UI_TEXTS['family']}", type="primary")
        
        if submitted:
            # Validate required fields
            if not name:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}")
                return
                
            try:
                # Prepare family data
                family_data = {
                    'name': name.strip(),
                    'background': background.strip() if background else None,
                    'url': url.strip() if url else None
                }
                
                # Add family to database
                family_id = dbm.add_or_update_family(
                    family_data, 
                    update=False)
                
                if family_id:
                    st.success(f"✅ {UI_TEXTS['family']} {UI_TEXTS['added']}: {name} (ID: {family_id})")
                    
                else:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['family']} {UI_TEXTS['not_found']}")
                
            except ValueError as ve:
                fu.show_user_error(f"❌ {fu.get_function_name()}", ve)
            except Exception as e:
                fu.show_user_error(f"❌ {fu.get_function_name()}", e)

def update_family_page() -> None:
    """Display the form to update an existing family."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
    
    if st.session_state.user_state == dbm.User_State['p_admin']:
        # Get family ID to update
        family_id = st.number_input(
            f"{UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
            min_value=1,
            step=1,
        key="update_family_id_2"
    )
    
    elif st.session_state.user_state == dbm.User_State['f_admin']:
        family_id = st.session_state.app_context.get('family_id', 0)
        if family_id == 0:
            st.error(f"❌ {UI_TEXTS['unauthorized']} {UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
            st.stop()
        st.write(f"**{UI_TEXTS['family']} {UI_TEXTS['id']}:** {family_id}")
    else:
        st.error(f"❌ {UI_TEXTS['unauthorized']} {UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
        st.stop()
    
    if 'update_message' in st.session_state:
        st.info(st.session_state.update_message)
        del st.session_state.update_message
    
    if family_id:
        # Get family data
        family = dbm.get_family(family_id)
        
        if not family:
            message = f"⚠️ {fu.get_function_name()} {UI_TEXTS['family']} {UI_TEXTS['not_found']}"
            st.session_state.update_message = message
            st.rerun()
    
    with st.form(f"update_family_form_{family_id}"):
        st.subheader(
            f"{UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['form']}: {family_id}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input(
                f"{UI_TEXTS['update']} {UI_TEXTS['family']} {UI_TEXTS['name']}",
                family.get('name', ''),
                key=f"update_name_{family_id}"
            )
            
            # Display creation/update timestamps as read-only
            created_at = family.get('created_at', 'N/A')
            updated_at = family.get('updated_at', 'N/A')
            
            st.caption(f"Created: {created_at}")
            st.caption(f"Last Updated: {updated_at}")
            
        with col2:
            url = st.text_input(
                f"{UI_TEXTS['update']} {UI_TEXTS['url']}",
                family.get('url', ''),
                placeholder="https://example.com",
                key=f"update_url_{family_id}"
            )
        
        background = st.text_area(
            f"{UI_TEXTS['update']} {UI_TEXTS['background']}",
            family.get('background', ''),
            height=150,
            help="Enter any relevant family history or background information",
            key=f"update_background_{family_id}"
        )
        
        submitted = st.form_submit_button(f"{UI_TEXTS['update']}", type="primary")
        
        if submitted:
                # Validate required fields
                if not name.strip():
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['name']} {UI_TEXTS['required']}"
                    st.session_state.update_message = message
                    st.rerun()
                    
                try:
                    # Prepare update data with only changed fields
                    update_data = {}
                    
                    update_data['name'] = name.strip()
                    if background != family.get('background'):
                        update_data['background'] = background.strip() if background else None
                    if url != family.get('url'):
                        update_data['url'] = url.strip() if url else None
                    
                    if update_data:
                        # Add the update flag to indicate this is an update
                        update_data['id'] = family_id
                        
                        # Update family in database
                        updated_id = dbm.add_or_update_family(
                            update_data, 
                            update=True)
                        
                        if updated_id:
                            message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['family']} {UI_TEXTS['update']} {name} (ID: {family_id})"
                            st.session_state.update_message = message
                            st.rerun()
                        else:
                            message = f"❌ {fu.get_function_name()} {UI_TEXTS['update_error']}: {updated_id}"
                            st.session_state.update_message = message
                            st.rerun()
                    else:
                        message = f"❌ {fu.get_function_name()} {UI_TEXTS['update_error']}: {update_data}"
                        st.session_state.update_message = message
                        st.rerun()
                        
                except ValueError as ve:
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['update_error']}"
                    logger.error(message, exc_info=ve)
                    st.session_state.update_message = message
                    st.rerun()
                except Exception as e:
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['update_error']}"
                    logger.error(message, exc_info=e)
                    st.session_state.update_message = message
                    st.rerun()

def search_relations_page() -> None:
    """
    Display the relation search page with filters and results.
    """
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['relation']} {UI_TEXTS['page']}")
    
    # Initialize session state for search results
    if 'relation_search_results' not in st.session_state:
        st.session_state.relation_search_results = []
    
    # Search form
    with st.form("relation_search_form"):
        st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['criteria']}")
        
        # Create two rows of search fields
        row1_col1, row1_col2 = st.columns(2)
        row2_col1, row2_col2 = st.columns(2)
        
        with row1_col1:
            some_id = st.number_input(
                "ID of either member or partner",
                min_value=0,
                step=1,
                value=0,
                key="search_some_id_2"
            )
        
        with row2_col1:
            relation_type = st.text_input(
                "Relation Type that Member relates to Partner",
                value="",
                placeholder="e.g. spouse, parent, child, sibling",
                key="relation_type_2"
            )
            
        with row1_col2:
            join_date_from = st.text_input(
                "Join Date From (YYYY-MM-DD)",
                value="",
                help="Enter the join date in the format YYYY-MM-DD",
                key="join_date_from_2"
            )
        
        with row2_col2:
            join_date_to = st.text_input(
                "Join Date To (YYYY-MM-DD)",
                value="",
                help="Enter the join date in the format YYYY-MM-DD",
                key="join_date_to_2"
            )
        
        # Add a search button
        submitted = st.form_submit_button(f"{UI_TEXTS['search']}", type="primary")
    
        # Process search when form is submitted
        if submitted:
            with st.spinner(f"{UI_TEXTS['search']} {UI_TEXTS['in_progress']}"):
                try:
                    if some_id > 0:
                        relations = dbm.get_relations_by_id(some_id)
                        
                    elif relation_type:
                        relations = dbm.get_relations_by_relation(relation_type)
                        
                    elif join_date_from and join_date_to:
                        relations = dbm.get_relations_by_join_between(join_date_from, join_date_to)
                        
                    else:
                        relations = dbm.get_relations()
                
                    if relations:
                        # Store results in session state
                        st.session_state.relation_search_results = relations
                    else:
                        st.session_state.relation_search_results = []
                        st.info("No matching relations found")
                
                except Exception as e:
                    st.session_state.relation_search_results = []
                    fu.show_user_error("❌ Error searching relations", e)
    
            # Display search results if available
            if st.session_state.relation_search_results:
                st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['results']}")
        
                # Convert results to DataFrame for better display
                df = pd.DataFrame(st.session_state.relation_search_results)
        
                # Rename columns for better display
                if not df.empty:
                    # Ensure date fields are properly formatted as strings
                    date_columns = ['join_date', 'end_date', 'created_at', 'updated_at']
                    for col in date_columns:
                        if col in df.columns:
                            df[col] = df[col].astype(str)
                    
                    # Select and reorder columns
                    all_fields = [
                        'id', 'member_id', 'partner_id', 'relation', 
                        'original_family_id', 'original_name', 'join_date', 'end_date',
                        'created_at', 'updated_at'
                    ]
            
                    # Filter out columns that don't exist in the results
                    existing_fields = [col for col in all_fields if col in df.columns]
                    df = df[existing_fields]
            
                    # Display the data in a table
                    st.dataframe(
                        df,
                        column_config={
                            'id': 'ID',
                            'member_id': 'Member ID',
                            'partner_id': 'Related Member ID',
                            'relation': 'Relation Type',
                            'original_family_id': 'Original Family ID',
                            'original_name': 'Original Name',
                            'join_date': 'Start Date',
                            'end_date': 'End Date',
                            'created_at': 'Created At',
                            'updated_at': 'Updated At'
                        },
                        hide_index=True,
                        use_container_width=True,
                        column_order=all_fields
                    )
            
                    # Show result count with bigger and bolder text
                    st.markdown(f"### {UI_TEXTS['search']} {UI_TEXTS['count']}: {len(df)}")
                else:
                    st.info(f"❌ {fu.get_function_name()} {UI_TEXTS['search']} {UI_TEXTS['not_found']}")
    
            # No results message
            elif submitted:
                st.info(f"❌ {fu.get_function_name()} {UI_TEXTS['search']} {UI_TEXTS['not_found']}")

def add_relation_page() -> None:
    """
    Display the form to add a new relation between members.
    """
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['add']} {UI_TEXTS['relation']} {UI_TEXTS['page']}")
    
    with st.form("add_relation_form"):

        col1, col2 = st.columns(2)
        
        with col1:
            member_id = st.number_input(
                f"{UI_TEXTS['member']} {UI_TEXTS['id']}*",
                min_value=1,
                step=1,
                help="ID of the first member in the relationship",
                key="add_relation_member_id_2"
            )
            rel_list = dbm.Relation_Type.keys()
            relation_type = st.selectbox(
                f"{UI_TEXTS['relation_type']}*",
                rel_list,
                help="Type of relationship between the members",
                key="add_relation_type_2"
            )
            
            join_date = st.text_input(
                f"{UI_TEXTS['relation_join_date']}*",
                value=date.today().strftime("%Y-%m-%d"),
                help="When this relationship began",
                key="add_relation_join_date_2"
            )
            
        with col2:
            partner_id = st.number_input(
                f"{UI_TEXTS['partner']} {UI_TEXTS['id']}*",
                min_value=1,
                step=1,
                value=1,
                help="ID of the second member in the relationship",
                key="add_relation_partner_id_2"
            )
            
            original_family_id = st.number_input(
                f"{UI_TEXTS['original']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
                min_value=0,
                step=1,
                value=0,
                help="Original family ID if applicable",
                key="add_relation_original_family_id_2"
            )
            
            end_date = st.text_input(
                f"{UI_TEXTS['relation_end_date']})",
                value=None,
                help="If this relationship has ended, when it ended",
                key="add_end_date_2"
            )
            
            # Validate date range if end date is provided
            if end_date and end_date < join_date:
                st.error("❌ End date cannot be before start date")
                st.stop()
        
        # Additional fields
        original_name = st.text_input("Original Name (if different)", "", key="add_original_name_2")
        dad_name = st.text_input("Father's Name (if applicable)", "", key="add_dad_name_2")
        mom_name = st.text_input("Mother's Name (if applicable)", "", key="add_mom_name_2")
        
        submitted = st.form_submit_button(f"{UI_TEXTS['add']} {UI_TEXTS['relation']}", type="primary")
        
        if submitted:
            # Validate required fields
            if not member_id or not partner_id or not relation_type:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}")
                return
                
            try:
                # Prepare relation data
                relation_data = {
                    'member_id': member_id,
                    'partner_id': partner_id,
                    'relation': relation_type,
                    'join_date': join_date,
                    'original_family_id': original_family_id if original_family_id > 0 else None,
                    'original_name': original_name if original_name else None,
                    'dad_name': dad_name if dad_name else None,
                    'mom_name': mom_name if mom_name else None
                }
                
                # Add end date if provided
                if end_date:
                    relation_data['end_date'] = end_date
                
                # Add relation to database
                relation_id = dbm.add_or_update_relation(
                    relation_data, update=False)
                
                if relation_id:
                    st.success(f"✅ {UI_TEXTS['add']} {UI_TEXTS['relation']} {UI_TEXTS['id']}: {relation_id}")
                else:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['add']} {UI_TEXTS['relation_error']} {UI_TEXTS['id']}: {relation_id}")
                
            except ValueError as ve:
                fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['add']} {UI_TEXTS['relation_error']}", ve)
            except Exception as e:
                fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['add']} {UI_TEXTS['relation_error']}", e)

def update_relation_page() -> None:
    """
    Display the form to update an existing relation.
    """
    global UI_TEXTS
    # 初始化 session state 變數
    if 'update_relation' not in st.session_state:
        st.session_state.update_relation = None
    if 'relation_fetched' not in st.session_state:
        st.session_state.relation_fetched = False
    if 'submitted' not in st.session_state:
        st.session_state.submitted = False
        
    st.subheader(f"{UI_TEXTS['update']} {UI_TEXTS['relation']} {UI_TEXTS['page']}")
    
    # Get relation ID to update
    relation_id = st.number_input(
        f"{UI_TEXTS['relation']} {UI_TEXTS['id']}",
        min_value=1,
        step=1,
        key="update_relation_id_2"
    )
    
    if relation_id is not None and st.button(f"{UI_TEXTS['search']} {UI_TEXTS['relation']}", type="primary"):
        # Get relation data
        relation = dbm.get_relation(relation_id)
        
        if not relation:
            st.warning(f"⚠️ {UI_TEXTS['relation']} {UI_TEXTS['id']} {UI_TEXTS['not_found']}: {relation_id}")
       
        else:
            st.session_state.update_relation = relation
            st.session_state.relation_fetched = True
            st.rerun()
            
    if st.session_state.relation_fetched:
        relation = st.session_state.update_relation
        relation_id = relation.get('id')
        with st.form("update_relation_form"):
            st.subheader(f"Relation Details: {relation_id}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                member_id = st.number_input(
                        f"{UI_TEXTS['member']} {UI_TEXTS['id']}",
                        min_value=1,
                        step=1,
                        value=relation.get('member_id', 1),
                        help="ID of the first member in the relationship",
                        key="update_relation_member_id_2"
                    )
                rel_list = list(dbm.Relation_Type.values())  # Convert dict_keys to list
                current_relation = relation.get('relation', 'spouse')
                try:
                    default_index = rel_list.index(current_relation)
                except ValueError:
                    default_index = 0  # Default to first item if relation not found
                    
                relation_type = st.selectbox(
                        f"{UI_TEXTS['relation_type']}",
                        rel_list,
                        index=default_index,
                        help="Type of relationship between the members",
                        key="update_relation_type_2"
                    )
                    
                # Additional fields
                original_name = st.text_input(
                        f"{UI_TEXTS['original']} {UI_TEXTS['name']}",
                        relation.get('original_name', ''),
                        key=f"update_original_name_{relation_id}"
                    )
                
                dad_name = st.text_input(
                        f"{UI_TEXTS['dad']} {UI_TEXTS['name']}",
                        relation.get('dad_name', ''),
                        key=f"update_dad_name_{relation_id}"
                    )
                
                mom_name = st.text_input(
                        f"{UI_TEXTS['mom']} {UI_TEXTS['name']}",
                        relation.get('mom_name', ''),
                        key=f"update_mom_name_{relation_id}"
                    )
                
            with col2:
                partner_id = st.number_input(
                        f"{UI_TEXTS['partner']} {UI_TEXTS['id']}",
                        min_value=1,
                        step=1,
                        value=relation.get('partner_id', 1),
                        help="ID of the second member in the relationship",
                        key="update_relation_partner_id_2"
                    )
                    
                original_family_id = st.number_input(
                        f"{UI_TEXTS['original']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
                        min_value=0,
                        step=1,
                        value=relation.get('original_family_id', 0),
                        help="Original family ID if applicable",
                        key="update_relation_original_family_id_2"
                    )

                join_date = st.text_input(
                        f"{UI_TEXTS['relation_join_date']}*",
                        value=relation.get('join_date', date.today()),
                        help="When this relationship began",
                        key=f"update_join_date_{relation_id}"
                    )
                
                end_date = st.text_input(
                        f"{UI_TEXTS['relation_end_date']}",
                        value=relation.get('end_date', None),
                        help="If this relationship has ended, when it ended",
                        key=f"update_end_date_{relation_id}"
                        )
                    
                # Display timestamps
                created_at = relation.get('created_at', 'N/A')
                st.caption(f"Created: {created_at}")

                # Validate required fields for relation update
                if not member_id or not partner_id or not relation_type:
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}"
                    st.error(message)
            submitted = st.form_submit_button(f"{UI_TEXTS['update']} {UI_TEXTS['relation']}", type="primary")    
            if submitted:
                # Prepare update data with only changed fields
                update_data = {}
                        
                update_data['member_id'] = int(member_id)
                update_data['partner_id'] = int(partner_id)
                update_data['relation'] = relation_type
                logger.debug(f"Relation: {update_data['relation']}")
                    
                # Handle optional fields
                optional_fields = {
                        'original_family_id': int(original_family_id) if int(original_family_id) > 0 else 0,
                        'original_name': original_name if original_name else None,
                        'dad_name': dad_name if dad_name else None,
                        'mom_name': mom_name if mom_name else None,
                        'join_date': join_date if join_date else '0000-01-01',
                        'end_date': end_date if end_date else '0000-01-01'
                        }
                    
                for field, value in optional_fields.items():
                    if value != relation.get(field):
                        update_data[field] = value
                    
                if update_data:
                    st.session_state.update_relation = update_data
                    st.session_state.relation_fetched = False
                    st.session_state.submitted = True
                    st.rerun()
    
    if st.session_state.update_relation and st.session_state.submitted:
        # Update relation in database
        updated_id = dbm.add_or_update_relation(
            st.session_state.update_relation, update=True)
        
        if updated_id:
            message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['update']} {UI_TEXTS['relation']} {UI_TEXTS['id']}: {relation_id}"
            st.success(message)
        else:
            message = f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['update']} {UI_TEXTS['relation']} {UI_TEXTS['id']}: {relation_id}"
            st.error(message)
        
        # Clear session state
        del st.session_state.update_relation
        del st.session_state.relation_fetched
        del st.session_state.submitted

def add_member_page() -> None:
    """Display the form to add a new member."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['add']} {UI_TEXTS['member']} {UI_TEXTS['page']}")
   
    # save message to session state
    if 'add_message' in st.session_state and st.session_state.add_message:
        st.info(st.session_state.add_message)
        del st.session_state.add_message
 
    with st.form("add_member_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['name']}*",
                "",
                key="add_member_name_2"
            )
            sex = st.selectbox(
                f"{UI_TEXTS['add']} {UI_TEXTS['sex']}*",
                [UI_TEXTS['sex_male'], UI_TEXTS['sex_female'], UI_TEXTS['sex_other']],
                index=0,
                key="add_member_sex_2"
            )
            born = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['born']}*",
                value=date.today().strftime("%Y-%m-%d"),
                help=UI_TEXTS["date_placeholder"],
                key="add_born_date_2"
            )
            family_id = st.number_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
                min_value=0,
                step=1,
                value=0,
                key="add_member_family_id_2"
            )
            gen_order = st.number_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['gen_order']}",
                min_value=0,
                step=1,
                value=None,
                key="add_member_gen_order_2"
            )
        with col2:
            alias = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['alias']}", 
                "", 
                key="add_alias_2")
            
            email = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['email']}", 
                "", 
                key="add_email_2")
            password = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['password']}", 
                "", 
                type="password", 
                key="add_password_2")
            confirm_password = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['password_confirmed']}", 
                "", 
                type="password", 
                key="confirm_password_2")
            if password != confirm_password:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['password_error']}") 
                return
            url = st.text_input(
                f"{UI_TEXTS['add']} {UI_TEXTS['url']}", 
                "", 
                key="add_url_2")
        
        submitted = st.form_submit_button(UI_TEXTS["submit"], type="primary")
        
        if submitted:
            # Validate required fields
            if not name or not gen_order or not born:
                st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}")
                return
                
            try:
                member_data = {
                    'name': name,
                    'sex': sex[0].upper() if sex else None,
                    'born': born,
                    'family_id': int(family_id) if int(family_id) >= 0 else 0,
                    'alias': alias if alias else None,
                    'email': email if email else None,
                    'url': url if url else 'https://',
                    'gen_order': int(gen_order) if int(gen_order) > 0 else 0,
                }
                
                # Add new or update existing family member
                member_id = dbm.add_or_update_member(
                    member_data, 
                    update=False)
                if member_id:
                    if email and password:
                        # Create user in users table
                        user_id = au.create_user(email, password,
                                role=dbm.User_State['f_member'],
                                member_id=member_id)
                        if user_id:
                            message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['user']} {UI_TEXTS['created']}:  {email}" 
                        else:
                            message = f"❌ {fu.get_function_name()} {UI_TEXTS['user']['created']} {UI_TEXTS['failed']}: {email} "
                    else:
                        message = f"❌ {fu.get_function_name()} {UI_TEXTS['failed']}: {UI_TEXTS['field']} {UI_TEXTS['required']} "
                else:
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['member_error']} {UI_TEXTS['members']} {UI_TEXTS['not_found']}: {member_id}"
                
            except Exception as e:
                message = f"❌ {fu.get_function_name()} {UI_TEXTS['member_error']} {UI_TEXTS['failed']}: {member_id}"
                logger.error(message, exc_info=e)
            st.session_state.add_message = message
            st.rerun()

def update_member_page() -> None:
    """Display the form to update an existing member."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['update']} {UI_TEXTS['member']} {UI_TEXTS['page']}")
    
    # Get member ID to update
    member_id = st.number_input(
        f"{UI_TEXTS['update']} {UI_TEXTS['member']} {UI_TEXTS['id']}",
        min_value=1,
        step=1,
        key="update_member_id_2"
    )
    
    # save message to session state
    if 'update_message' in st.session_state and st.session_state.update_message:
        st.info(st.session_state.update_message)
        del st.session_state.update_message
    
    # Initialize member in session state if not exists
    if 'current_member' not in st.session_state:
        st.session_state.current_member = None
    
    # Handle Get Member button click
    if st.button(f"{UI_TEXTS['search']} {UI_TEXTS['member']}", type="primary"):
        if member_id:
            # Get member data and store in session state
            st.session_state.current_member = dbm.get_member(member_id)
            if not st.session_state.current_member:
                st.session_state.update_message = f"⚠️ {fu.get_function_name()} {UI_TEXTS['member']} {UI_TEXTS['id']} {UI_TEXTS['not_found']}: {member_id}"
                st.rerun()
        else:
            st.session_state.update_message = f"⚠️ {fu.get_function_name()} {UI_TEXTS['member']} {UI_TEXTS['id']} {UI_TEXTS['not_found']}: {member_id}"
            st.rerun()
    
    # Display the form if we have member data
    if st.session_state.current_member:
        member = st.session_state.current_member
        with st.form(f"update_form_{member_id}"):
            st.subheader(f"{UI_TEXTS['update']} {UI_TEXTS['member']} {UI_TEXTS['form']}")
            
            # Three-column layout for better organization
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Basic Information
                st.subheader(f"{UI_TEXTS['basic_info']}")
                name = st.text_input(
                    f"{UI_TEXTS['name']}*",
                    member.get('name', ''),
                    key=f"update_name_{member_id}_2"
                )
                
                alias = st.text_input(
                    f"{UI_TEXTS['alias']}",
                    member.get('alias', ''),
                    key=f"update_alias_{member_id}_2"
                )
                
                # Gender selection with proper value mapping
                gender_options = [UI_TEXTS['sex_male'], UI_TEXTS['sex_female'], UI_TEXTS['sex_other']]                
                gender_values = ['M', 'F', 'O']
                # Get current gender, default to 'M' if invalid
                current_sex = str(member.get('sex', '')).strip().upper()
                if current_sex not in gender_values:
                    current_sex = 'M'
                
                # Get the index of current gender for the selectbox
                current_index = gender_values.index(current_sex)
                
                # Display the selectbox and get the selected index
                sex = st.selectbox(
                    f"{UI_TEXTS['sex']}*",
                    gender_options,
                    index=current_index
                )
                
                # Get the corresponding value from our values list
                sex={UI_TEXTS['sex_male']: "M", UI_TEXTS['sex_female']: "F", UI_TEXTS['sex_other']: "O"}.get(sex, "") if sex else ""
                
            with col2:
                # Dates and Family
                st.subheader(f"{UI_TEXTS['dates']} & {UI_TEXTS['family']}")
                # Convert empty string to '0000-00-00' for date input
                born_value = str(member.get('born'))
                logger.debug(f"Born value: {born_value}")
                if born_value == '' or born_value is None:
                    born_value = '0000-00-00'
                
                born = st.text_input(
                    f"{UI_TEXTS['born']}* (YYYY-MM-DD)",
                    value=born_value,
                    help="Enter the birth date in the format YYYY-MM-DD",
                    key=f"update_born_{member_id}"
                )
                
                # Convert empty string to '0000-00-00' for date input
                died_value = str(member.get('died'))
                logger.debug(f"Died value: {died_value}")
                if died_value == '' or died_value is None:
                    died_value = '0000-00-00'
                        
                died = st.text_input(
                    f"{UI_TEXTS['died']} (YYYY-MM-DD)",
                    value=died_value,
                    help="Enter the death date in the format YYYY-MM-DD",
                    key=f"update_died_{member_id}"
                )
                
                family_id = st.number_input(
                    f"{UI_TEXTS['family']} {UI_TEXTS['id']}",
                    min_value=0,
                    step=1,
                    value=member.get('family_id', 0),
                    key="update_member_family_id_2"
                )
                
                # Ensure gen_order is an integer
                try:
                    gen_order_value = int(member.get('gen_order', 0))
                except (ValueError, TypeError):
                    gen_order_value = 0
                    
                gen_order = st.number_input(
                    f"{UI_TEXTS['gen_order']}*",
                    min_value=0,
                    step=1,
                    value=gen_order_value,
                    key="update_member_gen_order"
                )
                
            with col3:
                # Contact and Relations
                st.subheader(f"{UI_TEXTS['contact']} & {UI_TEXTS['relation']}")
                email = st.text_input(
                    "Email",
                    member.get('email', '')
                )
                
                url = st.text_input(
                    "Personal Website",
                    member.get('url', 'https://')
                )
                
                dad_id = st.number_input(
                    "Father ID",
                    min_value=0,
                    step=1,
                    value=int(member.get('dad_id') or 0),
                    key="update_member_dad_id"
                )
                
                mom_id = st.number_input(
                    "Mother ID",
                    min_value=0,
                    step=1,
                    value=int(member.get('mom_id') or 0),
                    key="update_member_mom_id"
                )
            
            submitted = st.form_submit_button(UI_TEXTS["submit"])
            
            if submitted:
                # Validate required fields
                if not name or not gen_order or not born:
                    message = f"❌ {fu.get_function_name()} {UI_TEXTS['field']} {UI_TEXTS['required']}"
                    st.session_state.update_message = message
                    return
                
                update_data = {
                    'name': name,
                    'sex': sex if sex else None,
                    'born': born,
                    'died': died if died else '0000-00-00',
                    'family_id': int(family_id) if int(family_id) >= 0 else 0,
                    'alias': alias if alias else None,
                    'email': email if email else None,
                    'url': url if url else None,
                    'gen_order': gen_order if gen_order > 0 else 0,
                    'dad_id': int(dad_id) if int(dad_id) >= 0 else 0,
                    'mom_id': int(mom_id) if int(mom_id) >= 0 else 0
                }
                
                # Remove unchanged fields
                for key in list(update_data.keys()):
                    if key in member and update_data[key] == member[key]:
                        del update_data[key]
                
                if update_data:
                    logger.debug(f"Update data: {update_data}")
                    try:
                        success = dbm.update_member(member_id, update_data)
                        if success:
                            st.session_state.update_message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['update']}"
                            # Refresh member data after successful update
                            st.session_state.current_member = dbm.get_member(member_id)
                        else:
                            st.session_state.update_message = f"⚠️ {UI_TEXTS['update']} {UI_TEXTS['not_changed']}"
                        st.rerun()
                    except Exception as e:
                        st.session_state.update_message = f"❌ {UI_TEXTS['update_error']}"
                        logging.getLogger('ftpe').error(f"❌ {UI_TEXTS['update_error']}", exc_info=e)
                        st.rerun()
                else:
                    st.session_state.update_message = f"⚠️ {UI_TEXTS['update']} {UI_TEXTS['not_changed']}"
                    st.rerun()

def delete_member_page() -> None:
    """Display the interface for deleting a member."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['member']} {UI_TEXTS['page']}")
    
    # Initialize session state for delete confirmation
    if 'delete_message' not in st.session_state:
        st.session_state.delete_message = None
    if 'delete_member_id' not in st.session_state:
        st.session_state.delete_member_id = None
    if 'delete_member_confirmation' not in st.session_state:
        st.session_state.delete_member_confirmation = False
    
    # Get member ID to delete
    member_id = st.number_input(
        f"{UI_TEXTS['delete']} {UI_TEXTS['member']} {UI_TEXTS['id']}",
        min_value=1,
        step=1,
        value=st.session_state.get('delete_member_id', 1)
    )

    # Display any existing messages
    if st.session_state.get('delete_message'):
        st.info(st.session_state.delete_message)
        st.session_state.delete_message = None
    
    # First button to show confirmation
    if not st.session_state.delete_member_confirmation:
        if st.button("Show Member Details", type="primary"):
            st.session_state.delete_member_id = member_id
            st.session_state.delete_member_confirmation = True
            st.rerun()
    
    # Show confirmation UI if requested
    if st.session_state.delete_member_confirmation:
        try:
            member_id = int(st.session_state.delete_member_id)
            # Get member data for confirmation
            member = dbm.get_member(member_id)
        
            if not member:
                error_msg = f"{fu.get_function_name()} {UI_TEXTS['members']} {UI_TEXTS['not_found']}: {member_id}"
                logger.error(error_msg)
                st.session_state.delete_message = f"❌ {error_msg}"
                st.session_state.delete_member_confirmation = False
                st.rerun()
            
            # Display member data for confirmation
            st.warning(f"⚠️ {UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
            st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
            
            # Format member information for display
            st.write(f"**{UI_TEXTS['member']} {UI_TEXTS['id']}:** {member['id']}")
            st.write(f"**{UI_TEXTS['name']}:** {member.get('name', 'Unknown')}")
            st.write(f"**{UI_TEXTS['sex']}:** {member.get('gender', 'N/A')}")
            st.write(f"**{UI_TEXTS['born']}:** {member.get('born', 'N/A')}")
            st.write(f"**{UI_TEXTS['email']}:** {member.get('email', 'N/A')}")
            
            # Get family information if available
            if member.get('family_id'):
                family = dbm.get_family(member['family_id'])
                family_name = family.get('name', 'Unknown') if family else 'Unknown'
                st.write(f"**{UI_TEXTS['family']}:** {family_name} ({UI_TEXTS['id']}: {member['family_id']})")
            
            # Get relations information
            relations = dbm.get_member_relations(member_id)
            if relations:
                relation_list = []
                for rel in relations:
                    other_member_id = rel['partner_id'] if rel['member_id'] == member_id else rel['member_id']
                    other_member = dbm.get_member(other_member_id)
                    other_name = other_member.get('name', 'Unknown') if other_member else 'Unknown'
                    relation_list.append(f"{other_name} (ID: {other_member_id}) - {rel.get('relation', 'N/A')}")
                
                st.warning(f"⚠️ {UI_TEXTS['member']} {UI_TEXTS['relation']} {UI_TEXTS['count']}: {len(relations)}")
                for rel in relation_list:
                    st.write(f"- {rel}")
            
            # Confirm deletion with a form to avoid button nesting
            with st.form("confirm_delete_member_form"):
                confirm = st.checkbox(
                    f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}"
                )
                logger.debug(f"Checkbox state: {confirm}")
                
                col1, col2 = st.columns(2)
                with col1:
                    cancel_button = st.form_submit_button("Cancel")
                
                with col2:
                    delete_button = st.form_submit_button("Delete", type="primary")
                    
                if cancel_button:
                    st.session_state.delete_member_confirmation = False
                    st.rerun()
                    
                if confirm and delete_button:
                    try:
                        logger.debug(f"Delete form submitted for member ID: {member_id}")
                        logger.debug(f"Attempting to delete member with ID: {member_id}")
                        success = dbm.delete_member(int(member_id))
                        logger.debug(f"Delete operation result: {success}")
                        if success:
                            message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['delete']} {UI_TEXTS['member']} {UI_TEXTS['id']}: {member_id}"
                            logger.info(message)
                            st.session_state.delete_message = message
                            st.session_state.delete_member_confirmation = False
                            st.session_state.delete_member_id = None
                            st.rerun()
                        else:
                            message = f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['delete']} {UI_TEXTS['member']} {UI_TEXTS['id']}: {member_id}"
                            logger.error(message)
                            st.session_state.delete_message = message
                            st.rerun()
                    except Exception:
                        error_msg = f"❌ {fu.get_function_name()} {UI_TEXTS['delete_error']}"
                        logger.error(error_msg, exc_info=True)
                        st.session_state.delete_message = f"❌ {error_msg}"
                        st.rerun()
        except Exception:
            error_msg = f"❌ {fu.get_function_name()} {UI_TEXTS['delete_error']}"
            logger.error(error_msg, exc_info=True)
            st.session_state.delete_message = f"❌ {error_msg}"
            st.rerun()

def delete_family_page() -> None:
    """Display the interface for deleting a family."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
    
    # Initialize session state for delete confirmation
    if 'delete_message' not in st.session_state:
        st.session_state.delete_message = None
    if 'delete_family_id' not in st.session_state:
        st.session_state.delete_family_id = None
    if 'delete_family_confirmation' not in st.session_state:
        st.session_state.delete_family_confirmation = False

    if st.session_state.user_state == dbm.User_State['p_admin']:
        # Get family ID to delete
        family_id = st.number_input(
            f"{UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['id']}",
            min_value=1,
            step=1,
            value=st.session_state.get('delete_family_id', 1)
        )
    elif st.session_state.user_state == dbm.User_State['f_admin']:
        family_id = st.session_state.app_context.get('family_id', 0)
        if family_id == 0:
            st.error(f"❌ {UI_TEXTS['unauthorized']} {UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
            st.stop()
        st.write(f"Family ID: {family_id}")
    else:
        st.error(f"❌ {UI_TEXTS['unauthorized']} {UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['page']}")
        st.stop()
    
    # Store the family ID in session state
    st.session_state.delete_family_id = family_id
    # Check for error message first
    if st.session_state.get('delete_message'):
        st.error(f"❌ {st.session_state.delete_message}")
        st.session_state.delete_message = None
    
    # First button to show confirmation
    if not st.session_state.delete_family_confirmation:
        if st.button("Show Family Details", type="primary"):
            st.session_state.delete_family_confirmation = True
            st.rerun()
    
    # Show confirmation UI if requested
    if st.session_state.delete_family_confirmation:
        try:
            family_id = int(st.session_state.delete_family_id)
            # Check if family exists before showing confirmation
            family = dbm.get_family(family_id)
            if not family:
                error_msg = f"{UI_TEXTS['family']} {UI_TEXTS['id']}: {family_id} {UI_TEXTS['not_found']}"
                logger.error(error_msg)
                st.session_state.delete_message = f"❌ {error_msg}"
                st.session_state.delete_family_confirmation = False
                st.rerun()
            
            # Get member count and list of members in this family
            members = dbm.search_members(family_id=family_id)
            member_count = len(members)
            
            # Display family data for confirmation
            st.warning(f"⚠️ {UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
            st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
            
            # Format family detail info for display
            st.write(f"**{UI_TEXTS['family']} {UI_TEXTS['id']}:** {family['id']}")
            st.write(f"**{UI_TEXTS['family']} {UI_TEXTS['name']}:** {family.get('name', 'Unknown')}")
            st.write(f"**{UI_TEXTS['background']}:** {family.get('background', 'N/A')}")
            st.write(f"**{UI_TEXTS['url']}:** {family.get('url', 'N/A')}")
            st.write(f"**{UI_TEXTS['email']}:** {family.get('email', 'N/A')}")
            
            # Show member information if any
            if member_count > 0:
                st.warning(f"⚠️ {UI_TEXTS['family']} {UI_TEXTS['count']}: {member_count}")
                member_names = [f"{m.get('name', 'Unknown')} (ID: {m['id']})" for m in members]
                st.write(f"**{UI_TEXTS['family']} {UI_TEXTS['member']}**", ", ".join(member_names) if member_names else "None")
            
            # Confirm deletion with a form to avoid button nesting
            with st.form("confirm_delete_family_form"):
                confirm = st.checkbox(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
                logger.debug(f"Checkbox state: {confirm}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Cancel"):
                        st.session_state.delete_family_confirmation = False
                        st.rerun()
                
                with col2:
                    submit_button = st.form_submit_button(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}", type="primary")
                    logger.debug(f"Submit button state - Confirm: {confirm}, Button Clicked: {submit_button}")
                    
                if confirm and submit_button:
                    try:
                        logger.debug(f"Delete form submitted for family ID: {family_id}")
                        logger.debug(f"Attempting to delete family with ID: {family_id}")
                        success = dbm.delete_family(int(family_id))
                        logger.debug(f"Delete operation result: {success}")
                        if success:
                            message = f"✅ {UI_TEXTS['successful']} {UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['id']}: {family_id}"
                            logger.info(message)
                            st.session_state.delete_message = message
                            st.session_state.delete_family_confirmation = False
                            st.session_state.delete_family_id = None
                            st.rerun()
                        else:
                            message = f"❌ {fu.get_function_name()} {UI_TEXTS['failed']} {UI_TEXTS['delete']} {UI_TEXTS['family']} {UI_TEXTS['id']}: {family_id}"
                            logger.error(message)
                            st.session_state.delete_message = message
                            st.rerun()
                    except Exception:
                        error_msg = f"{fu.get_function_name()} {UI_TEXTS['delete_error']}"
                        logger.error(error_msg, exc_info=True)
                        st.session_state.delete_message = f"❌ {error_msg}"
                        st.rerun()
        except Exception as e:
            error_msg = f"{fu.get_function_name()} {UI_TEXTS['delete_error']}"
            logging.getLogger('ftpe').error(f"{fu.get_function_name()} {UI_TEXTS['delete_error']}", exc_info=e)
            message = f"❌ {error_msg}"
            st.session_state.delete_message = message
            st.session_state.delete_family_confirmation = False
            logger.error(error_msg, exc_info=True)
            st.rerun()

def delete_relation_page() -> None:
    """Display the interface for deleting a relation."""
    global UI_TEXTS
    st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['relation']} {UI_TEXTS['page']}")
    
    # Initialize session state for delete confirmation
    if 'delete_message' not in st.session_state:
        st.session_state.delete_message = None
    if 'delete_relation_id' not in st.session_state:
        st.session_state.delete_relation_id = None
    if 'delete_relation_confirmation' not in st.session_state:
        st.session_state.delete_relation_confirmation = False
    
    # Get relation ID to delete
    relation_id = st.number_input(
        f"{UI_TEXTS['enter']} {UI_TEXTS['relation']} {UI_TEXTS['id']}",
        min_value=1,
        step=1,
        value=st.session_state.get('delete_relation_id', 1)
    )
    
    # Store the relation ID in session state
    st.session_state.delete_relation_id = relation_id
    
    # Display any existing messages
    if st.session_state.get('delete_message'):
        st.info(st.session_state.delete_message)
        st.session_state.delete_message = None
    
    # First button to show confirmation
    if not st.session_state.delete_relation_confirmation:
        if st.button(f"{UI_TEXTS['delete']} {UI_TEXTS['relation']} {UI_TEXTS['confirm']}", type="primary"):
            st.session_state.delete_relation_confirmation = True
            st.rerun()
    
    # Show confirmation UI if requested
    if st.session_state.delete_relation_confirmation:
        try:
            # Get relation data for confirmation
            relation = dbm.get_relation(relation_id)
                
            if not relation:
                error_msg = f"{fu.get_function_name()} {UI_TEXTS['relation']} {UI_TEXTS['id']}: {relation_id} {UI_TEXTS['not_found']}"
                logger.error(error_msg)
                st.session_state.delete_relation_confirmation = False
                st.session_state.delete_relation_id = None
                st.session_state.delete_message = f"❌ {error_msg}"
                st.error(error_msg)
                
            # Get member names for display
            member1 = dbm.get_member(relation['member_id'])
            member2 = dbm.get_member(relation['partner_id'])
            
            # Display relation data for confirmation
            st.warning(f"⚠️ {UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
            st.subheader(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
                
            # Format relation information for display   
            st.write(f"**{UI_TEXTS['relation']} {UI_TEXTS['id']}:** {relation['id']}")
            st.write(f"**{UI_TEXTS['member']} 1 (ID: {relation['member_id']}):** {member1.get('name', 'Unknown') if member1 else 'Unknown'}")
            st.write(f"**{UI_TEXTS['member']} 2 (ID: {relation['partner_id']}):** {member2.get('name', 'Unknown') if member2 else 'Unknown'}")
            st.write(f"**{UI_TEXTS['relation']} {UI_TEXTS['type']}:** {relation.get('relation', 'N/A')}")
            st.write(f"**{UI_TEXTS['relation_join_date']}:** {relation.get('join_date', 'N/A')}")
            st.write(f"**{UI_TEXTS['relation_end_date']}:** {relation.get('end_date', 'N/A')}")
                
            # Confirm deletion with a form to avoid button nesting
            with st.form("confirm_delete_form"):
                confirm = st.checkbox(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}")
                logger.debug(f"Checkbox state: {confirm}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Cancel"):
                        st.session_state.delete_relation_confirmation = False
                        st.rerun()
                
                with col2:
                    submit_button = st.form_submit_button(f"{UI_TEXTS['delete']} {UI_TEXTS['confirm']}", type="primary")
                    logger.debug(f"Submit button state - Confirm: {confirm}, Button Clicked: {submit_button}")
                    
                if confirm and submit_button:
                    try:
                        logger.debug(f"Delete form submitted for relation ID: {relation_id}")
                        logger.debug(f"Attempting to delete relation with ID: {relation_id}")
                        result = dbm.delete_relation(int(relation_id))
                        logger.debug(f"Delete operation result: {result}")
                        if result:
                            message = f"✅ {UI_TEXTS['relation']} {UI_TEXTS['id']}: {relation_id} {UI_TEXTS['deleted']}"
                            logger.debug(message)
                            st.session_state.delete_message = message
                            st.session_state.delete_relation_confirmation = False
                            st.session_state.delete_relation_id = None
                            st.success(message)
                        else:
                            message = f"❌ Failed to delete relation with ID {relation_id}"
                            logger.error(message)
                            st.session_state.delete_message = message
                            st.error(message)
                    except Exception:
                        error_msg = "❌ Error deleting relation"
                        logger.error(error_msg, exc_info=True)
                        st.session_state.delete_message = f"❌ {error_msg}"
                        st.error(error_msg)
                
        except Exception:
            error_msg = f"{fu.get_function_name()} {UI_TEXTS['relation']} {UI_TEXTS['delete_error']}"
            logger.error(error_msg, exc_info=True)
            st.session_state.delete_message = f"❌ {error_msg}"
            st.session_state.delete_relation_confirmation = False
            st.error(error_msg)

def main() -> None:
    """Main application entry point."""
    global UI_TEXTS
    
    st.header(f"🌲 {UI_TEXTS['family_tree']} {UI_TEXTS['management']}")

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
                st.page_link("pages/8_caseMgmt.py", label="Case Management", icon="📋")
                st.page_link("pages/9_birthday.py", label="Birthday", icon="🎂")
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
    
    # Main Page --- frome here
    
    # Main tab groups
    tab1, tab2, tab3 = st.tabs([
        f"👥 {UI_TEXTS['member']} {UI_TEXTS['management']}", 
        f"🏠 {UI_TEXTS['family']} {UI_TEXTS['management']}", 
        f"🔗 {UI_TEXTS['relation']} {UI_TEXTS['management']}"])
    
    with tab1:  # Member Management
        st.header(f"{UI_TEXTS['member']} {UI_TEXTS['management']}")
        
        # Define the tab labels explicitly to ensure we have the correct number
        member_tab_labels = [
            f"🔍 {UI_TEXTS['search']} {UI_TEXTS['member']}",
            f"➕ {UI_TEXTS['add']} {UI_TEXTS['member']}",
            f"✏️ {UI_TEXTS['update']} {UI_TEXTS['member']}",
            f"🗑️ {UI_TEXTS['delete']} {UI_TEXTS['member']}"
        ]
        
        # Create tabs with explicit labels
        member_tabs = st.tabs(member_tab_labels)
        
        # Map each tab to its corresponding function
        with member_tabs[0]:  # Search Members
            search_members_page()
            
        with member_tabs[1]:  # Add Member
            add_member_page()
            
        with member_tabs[2]:  # Update Member
            update_member_page()
            
        with member_tabs[3]:  # Delete Member
            delete_member_page()
        
    with tab2:  # Family Management
        st.header(f"🏠 {UI_TEXTS['family']} {UI_TEXTS['management']}")
        family_tabs = st.tabs([
            f"🔍 {UI_TEXTS['search']} {UI_TEXTS['family']}", 
            f"➕ {UI_TEXTS['add']} {UI_TEXTS['family']}", 
            f"✏️ {UI_TEXTS['update']} {UI_TEXTS['family']}",
            f"🗑️ {UI_TEXTS['delete']} {UI_TEXTS['family']}"])
        
        with family_tabs[0]:  # Search Families
            search_families_page()
            
        with family_tabs[1]:  # Add Family
            add_family_page()
            
        with family_tabs[2]:  # Update Family
            update_family_page()
        
        with family_tabs[3]:  # Delete Family
            delete_family_page()
    
    with tab3:  # Relations Management
        st.header(f"🔗 {UI_TEXTS['relation']} {UI_TEXTS['management']}")
        relation_tabs = st.tabs([
            f"🔍 {UI_TEXTS['search']} {UI_TEXTS['relation']}", 
            f"➕ {UI_TEXTS['add']} {UI_TEXTS['relation']}", 
            f"✏️ {UI_TEXTS['update']} {UI_TEXTS['relation']}",
            f"🗑️ {UI_TEXTS['delete']} {UI_TEXTS['relation']}"])
        
        with relation_tabs[0]:  # Search Relations
            search_relations_page()
            
        with relation_tabs[1]:  # Add Relation
            add_relation_page()
            
        with relation_tabs[2]:  # Update Relation
            update_relation_page()
        
        with relation_tabs[3]:  # Delete Relation
            delete_relation_page()

# Initialize session state and UI_TEXTS
if 'app_context' not in st.session_state:
    cu.init_session_state()
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
    main()