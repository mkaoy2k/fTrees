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


def lookup_members(member_id=None, name=None):
    """Members matching an id, or a name search.

    An id returns that member, or an empty list when the id is missing or
    not positive. A non-integer id raises ValueError. A name is stripped
    and lowercased before the same search the case forms used to call.
    When both are passed, the id is used.
    """
    if member_id is not None and member_id != "":
        return _lookup_by_id(member_id)
    if name and str(name).strip():
        found = dbm.search_members(name=str(name).strip().lower())
        return list(found or [])
    return []


def _lookup_by_id(member_id):
    if isinstance(member_id, bool):
        raise ValueError("member id must be an integer")
    try:
        member_id = int(member_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("member id must be an integer") from exc
    if member_id <= 0:
        return []
    member = dbm.get_member(member_id)
    return [member] if member else []


def parent_relation(member_id, partner_id, join_date, relation="parent", end_date=None):
    """Relation row shared by the birth, adoption, and partnership forms."""
    row = {
        "member_id": member_id,
        "partner_id": partner_id,
        "relation": relation,
        "join_date": join_date,
    }
    if end_date is not None:
        row["end_date"] = end_date
    return row
