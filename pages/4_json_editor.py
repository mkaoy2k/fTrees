"""
JSON Editor for Streamlit

This module provides a user interface for viewing and editing JSON files within a Streamlit application.
It includes features for:
- Browsing and selecting JSON files from the data directory
- Creating new JSON files
- Editing JSON content with syntax highlighting
- Saving changes back to files
- Reloading files to see external changes
- Downloading JSON files
- Viewing formatted JSON output
"""

import streamlit as st
import json
from pathlib import Path
import context_utils as cu
import db_utils as dbm
from nav import render_sidebar, require_role
import funcUtils as fu
import editor_paths

APP_ROOT = Path(__file__).resolve().parent.parent


def _texts():
    return fu.session_texts()


def _contained(file_path):
    return editor_paths.contained_file(APP_ROOT, file_path)


def load_json(file_path):
    """
    Load JSON data from a file in the data directory.

    Args:
        file_path (str or Path): Path to the JSON file to load

    Returns:
        dict: Parsed JSON data as a dictionary, or empty dict if file doesn't exist or is invalid
    """
    target = _contained(file_path)
    try:
        if target is not None and target.exists():
            with open(target, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except json.JSONDecodeError:
        st.error("❌ Error: Invalid JSON file")
        return {}

def save_json(file_path, data):
    """
    Save data to a JSON file in the data directory.

    Args:
        file_path (str or Path): Path where the JSON file will be saved
        data (dict): Data to be saved as JSON

    Returns:
        bool: True if save was successful, False otherwise
    """
    target = _contained(file_path)
    if target is None:
        return False
    try:
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        fu.show_user_error("❌ Error saving file", e)
        return False

def main():
    texts = _texts()
    st.header(texts.get("json_editor", "JSON Editor"))
    render_sidebar()
    with st.sidebar:
        create_label = texts.get("create_new", "Create New...")
        json_files = editor_paths.list_data_files(APP_ROOT, ".json")
        selected_file = st.sidebar.selectbox(
            texts.get("select_file", "Select a file"),
            [create_label] + json_files,
            index=0
        )

        file_path = None
        if selected_file == create_label:
            new_file = st.sidebar.text_input(texts.get("new_filename", "New file name"))
            if new_file:
                try:
                    file_path = editor_paths.new_data_file(APP_ROOT, new_file, ".json")
                except ValueError:
                    st.sidebar.error(texts.get(
                        "invalid_filename",
                        "That file name is not allowed. Use a simple file name in the data folder.",
                    ))
        elif selected_file:
            file_path = _contained(editor_paths.data_directory(APP_ROOT) / selected_file)

        file_changed = (
            'current_file' not in st.session_state or
            str(file_path) != st.session_state.get('current_file')
        )
        target = _contained(file_path)

        if (file_changed or 'reload_file' in st.session_state) and target is not None and target.exists():
            try:
                with open(target, 'r', encoding='utf-8') as f:
                    st.session_state.file_content = f.read()
                st.session_state.current_file = str(target)
                if 'reload_file' in st.session_state:
                    del st.session_state.reload_file
            except Exception as e:
                fu.show_user_error("❌ Error loading file", e)
                st.session_state.file_content = "{\n    \"key\": \"value\"\n}"
        elif target is None or not target.exists():
            st.session_state.file_content = "{\n    \"key\": \"value\"\n}"

        if file_path:
            st.sidebar.write(f"{texts.get('editing', 'Editing')}: `{Path(file_path).name}`")

    st.subheader(texts.get("editing_area", "Editing Area"))
    if not isinstance(st.session_state.file_content, str):
        st.session_state.file_content = "{\n    \"key\": \"value\"\n}"

    edited_json = st.text_area(
        "Edit JSON content:",
        value=st.session_state.file_content,
        height=600,
        key="json_editor"
    )

    st.session_state.file_content = edited_json

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(texts.get("save_changes", "Save Changes"), type="primary") and file_path:
            try:
                if _contained(file_path) is None:
                    st.error(texts.get(
                        "invalid_filename",
                        "That file name is not allowed. Use a simple file name in the data folder.",
                    ))
                else:
                    parsed_json = json.loads(edited_json)
                    if save_json(file_path, parsed_json):
                        st.success(f"{texts.get('save_changes', 'Save Changes')}: {Path(file_path).name}")
            except json.JSONDecodeError as e:
                fu.show_user_error("❌ Invalid JSON", e)

    with col2:
        target = _contained(file_path)
        if st.button(texts.get("reload", "Reload"), type="secondary") and target is not None and target.exists():
            if 'file_content' in st.session_state:
                del st.session_state.file_content
            st.session_state.reload_file = True
            st.rerun()

    with col3:
        if st.button(texts.get("download", "Download"), type="secondary"):
            st.download_button(
                label=f"{texts.get('download', 'Download')} JSON",
                data=edited_json,
                file_name=Path(file_path).name if file_path else "data.json",
                mime="application/json"
            )

    with st.expander("View Formatted JSON"):
        try:
            parsed = json.loads(edited_json)
            st.json(parsed)
        except json.JSONDecodeError:
            st.error("❌ Invalid JSON")

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
        st.session_state.file_content = ""
    main()
