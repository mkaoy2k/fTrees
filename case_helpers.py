"""Helpers shared by case-management forms.

Kept out of the Streamlit page so tests can import them without starting
the page script.
"""
from pathlib import Path

import db_utils as dbm


def project_env_file(page_file) -> Path:
    """`.env` next to the app, for a page that lives in `pages/`."""
    return Path(page_file).resolve().parent.parent / ".env"


def member_user_fields(family_id, member_id):
    """Login row for a family member created from a case form."""
    return {
        "is_admin": dbm.User_State["f_member"],
        "is_active": dbm.Subscriber_State["active"],
        "family_id": family_id,
        "member_id": member_id,
    }


def chosen_parents(father, mother):
    """Parent records that were actually selected on a case form."""
    return [parent for parent in (father, mother) if parent]
