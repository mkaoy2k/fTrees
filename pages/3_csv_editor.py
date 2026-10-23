"""
CSV Editor for Streamlit

This module provides a user interface for viewing and editing CSV files within a Streamlit application.
It includes features for:
- Browsing and selecting CSV files from the data directory
- Creating new CSV files
- Editing CSV content in a data grid
- Saving changes back to files
- Reloading files to see external changes
- Downloading CSV files
- Viewing formatted data in a table
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import context_utils as cu
import funcUtils as fu
import db_utils as dbm
import time
from nav import render_sidebar, require_role
import editor_paths

APP_ROOT = Path(__file__).resolve().parent.parent


def _texts():
    return fu.session_texts()


def _contained(file_path):
    return editor_paths.contained_file(APP_ROOT, file_path)


def load_csv(file_path):
    """
    Load CSV data from a file in the data directory.

    Args:
        file_path (str or Path): Path to the CSV file to load

    Returns:
        DataFrame: Loaded data as a pandas DataFrame, or empty DataFrame if file doesn't exist
    """
    target = _contained(file_path)
    try:
        if target is not None and target.exists():
            return pd.read_csv(target)
        return pd.DataFrame()
    except Exception as e:
        fu.show_user_error("❌ Error loading CSV file", e)
        return pd.DataFrame()

def save_csv(file_path, df):
    """
    Save DataFrame to a CSV file in the data directory.

    Args:
        file_path (str or Path): Path where the CSV file will be saved
        df (DataFrame): Data to be saved as CSV

    Returns:
        bool: True if save was successful, False otherwise
    """
    target = _contained(file_path)
    if target is None:
        return False
    try:
        df.to_csv(target, index=False)
        return True
    except Exception as e:
        fu.show_user_error("❌ Error saving file", e)
        return False

def load_file_content(file_path=None):
    """
    Load file content into a DataFrame.

    Args:
        file_path (Path, optional): Path to the file to load. Defaults to None.

    Returns:
        DataFrame: Loaded data as a pandas DataFrame,
            or an empty DataFrame if the file is empty or does not exist.
    """
    target = _contained(file_path)
    try:
        if target is not None and target.exists():
            try:
                df = pd.read_csv(target)
                if df.empty:
                    st.warning("⚠️ The file is empty. Starting with an empty table.")
                    return pd.DataFrame(columns=['Column 1'])
                return df
            except pd.errors.EmptyDataError:
                st.warning("⚠️ The file is empty. Starting with an empty table.")
                return pd.DataFrame(columns=['Column 1'])
            except Exception as e:
                fu.show_user_error("❌ Error reading file", e)
                return pd.DataFrame(columns=['Column 1'])
        else:
            return pd.DataFrame(columns=['Column 1'])
    except Exception as e:
        fu.show_user_error("❌ Unexpected error", e)
        return pd.DataFrame(columns=['Column 1'])

def main():
    texts = _texts()
    st.header(texts.get("csv_editor", "CSV Editor"))
    render_sidebar()
    with st.sidebar:
        create_label = texts.get("create_new", "Create New...")
        csv_files = editor_paths.list_data_files(APP_ROOT, ".csv")
        selected_file = st.sidebar.selectbox(
            texts.get("select_file", "Select a file"),
            [create_label] + csv_files,
            index=0
        )

        file_path = None
        if selected_file == create_label:
            new_file = st.sidebar.text_input(texts.get("new_filename", "New file name"))
            if new_file:
                try:
                    file_path = editor_paths.new_data_file(APP_ROOT, new_file, ".csv")
                except ValueError:
                    st.sidebar.error(texts.get(
                        "invalid_filename",
                        "That file name is not allowed. Use a simple file name in the data folder.",
                    ))
        else:
            file_path = _contained(editor_paths.data_directory(APP_ROOT) / selected_file)

        force_reload = st.session_state.get('force_reload', False)
        reload_path = _contained(st.session_state.get('reload_file_path'))
        file_changed = 'current_file' not in st.session_state or st.session_state.current_file != str(file_path)
        reload_needed = 'reload_file' in st.session_state and st.session_state.reload_file

        if 'file_content' not in st.session_state or file_changed or reload_needed or (force_reload and reload_path is not None and str(reload_path) == str(file_path)):
            try:
                if force_reload and reload_path is not None and reload_path.exists():
                    st.session_state.file_content = pd.read_csv(reload_path)
                    st.session_state.current_file = str(reload_path)
                    del st.session_state.force_reload
                    del st.session_state.reload_file
                else:
                    st.session_state.file_content = load_file_content(file_path)
                    st.session_state.current_file = str(file_path) if file_path else None

                if 'reload_file' in st.session_state:
                    del st.session_state.reload_file
            except Exception as e:
                fu.show_user_error("❌ Error loading file", e)
                st.session_state.file_content = pd.DataFrame(columns=['Column 1'])

        if file_path:
            st.sidebar.write(f"{texts.get('editing', 'Editing')}: `{file_path.name}`")

        if not isinstance(st.session_state.file_content, pd.DataFrame):
            st.session_state.file_content = pd.DataFrame(columns=['Column 1'])

    st.subheader(texts.get("editing_area", "Editing Area"))
    if 'editor_key' not in st.session_state:
        current_file = st.session_state.get('current_file', '')
        file_name = Path(current_file).name if current_file else 'new'
        st.session_state.editor_key = f"editor_{file_name}_{time.time()}"

    current_content = st.session_state.file_content

    edited_df = st.data_editor(
        current_content,
        num_rows="dynamic",
        use_container_width=True,
        key=st.session_state.editor_key
    )

    if not current_content.equals(edited_df):
        st.session_state.file_content = edited_df

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(texts.get("save_changes", "Save Changes"), type="primary") and file_path:
            try:
                if _contained(file_path) is None:
                    st.error(texts.get(
                        "invalid_filename",
                        "That file name is not allowed. Use a simple file name in the data folder.",
                    ))
                elif save_csv(file_path, edited_df):
                    st.success(f"{texts.get('save_changes', 'Save Changes')}: {file_path.name}")
            except Exception as e:
                fu.show_user_error("❌ Error saving file", e)

    with col2:
        if st.button(texts.get("reload", "Reload")):
            target = _contained(file_path)
            if target is not None and target.exists():
                try:
                    new_content = pd.read_csv(target)
                    st.session_state.editor_key = f"editor_{target.name}_{time.time()}"
                    st.session_state.file_content = new_content
                    st.session_state.current_file = str(target)
                    st.rerun()
                except Exception as e:
                    fu.show_user_error("❌ Error reloading file", e)
            else:
                st.warning("⚠️ No valid file selected or file doesn't exist")

    with col3:
        if st.button(texts.get("download", "Download")):
            csv = edited_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"{texts.get('download', 'Download')} CSV",
                data=csv,
                file_name=file_path.name if file_path else "data.csv",
                mime="text/csv"
            )
    st.write(f"Number of rows: {len(edited_df)}")
    with st.expander("View Formatted Table"):
        if not edited_df.empty:
            st.dataframe(edited_df, use_container_width=True)
        else:
            st.info("No data to display")

# Initialize session state
cu.init_session_state()
cu.apply_ui_preferences()

# Check authentication
if not st.session_state.get('authenticated', False):
    st.switch_page("fTrees.py")
else:
    require_role(
        dbm.User_State['p_admin'],
        dbm.User_State['f_admin'],
        dbm.User_State['f_member'],
    )
    if 'file_content' not in st.session_state:
        st.session_state.file_content = pd.DataFrame()
    if 'current_file' not in st.session_state:
        st.session_state.current_file = None
    if 'force_reload' not in st.session_state:
        st.session_state.force_reload = False
    if 'reload_file_path' not in st.session_state:
        st.session_state.reload_file_path = None
    if 'reload_file' not in st.session_state:
        st.session_state.reload_file = False
    main()
