"""Newsletter for platform admins and family admins.

Family members do not get this page. A platform admin chooses any
family_id. A family admin stays on the family_id from login. Publication
previews the operations-server home page for that family and language,
then sends that snapshot only to the family's active subscribers.
"""
import html

import streamlit as st

import context_utils as cu
import db_utils as dbm
import funcUtils as fu
import newsletter_publish as nl
from nav import render_sidebar, require_role


def _language_choices(family_id):
    """Catalog languages that this family actually publishes, else every catalog."""
    try:
        catalogs = list(fu.load_ops_L10N() or {})
    except Exception:
        catalogs = []
    stored = set(dbm.get_article_languages(family_id=family_id) or [])
    choices = [lang for lang in catalogs if lang in stored]
    if choices:
        return choices
    return catalogs or ["US"]


def _status_label(value, texts):
    labels = {
        dbm.Subscriber_State["active"]: texts.get("active", "Active"),
        dbm.Subscriber_State["pending"]: texts.get("pending", "Pending"),
        dbm.Subscriber_State["inactive"]: texts.get("inactive", "Inactive"),
    }
    return labels.get(value, texts.get("unknown", "Unknown"))


def _subscriber_panel(family_id, lang, texts):
    """Table of this family's users, plus add and unsubscribe."""
    with st.form("newsletter_add_subscriber"):
        email = st.text_input(texts.get("email", "Email"))
        submitted = st.form_submit_button(
            f"{texts.get('add', 'Add')} {texts.get('subscriber', 'Subscriber')}"
        )
    if submitted:
        outcome = nl.add_family_subscriber(email, family_id, lang)
        if outcome["ok"]:
            st.success(
                f"{texts.get('subscriber', 'Subscriber')} {texts.get('added', 'Added')}: {outcome['email']}"
            )
        elif outcome["reason"] == "not_member":
            st.error(texts.get("newsletter_not_member", nl.NOT_MEMBER_MESSAGE))
        elif outcome["reason"] == "invalid_email":
            st.error(texts.get("newsletter_invalid_email", nl.INVALID_EMAIL_MESSAGE))
        else:
            st.error(texts.get("failed", "Failed"))

    rows = dbm.list_family_subscribers(family_id)
    if not rows:
        st.info(texts.get("newsletter_no_subscribers", "No active subscribers for this family."))
        return
    frame_rows = [
        {
            texts.get("email", "Email"): row.get("email") or "",
            texts.get("subscription", "Subscription"): _status_label(row.get("is_active"), texts),
            texts.get("language", "Language"): row.get("l10n") or "",
            "family_id": row.get("family_id"),
        }
        for row in rows
    ]
    try:
        import pandas as pd
        st.dataframe(pd.DataFrame(frame_rows), hide_index=True, width="stretch")
    except Exception:
        st.table(frame_rows)

    emails = [row.get("email") for row in rows if row.get("email")]
    choice = st.selectbox(
        texts.get("subscriber", "Subscriber"),
        emails,
        key="newsletter_unsubscribe_choice",
    )

    def _unsubscribe(address, family):
        nl.unsubscribe_family_subscriber(address, family)

    st.button(
        texts.get("unsubscribe", "Unsubscribe"),
        key="newsletter_unsubscribe",
        on_click=_unsubscribe,
        args=(choice, family_id),
    )


def _show_delivery(result, texts):
    count = len(result.get("recipients") or [])
    reason = result.get("reason")
    if reason == "blocked":
        st.warning(texts.get(
            "newsletter_send_blocked",
            "Sending is turned off in this environment. No email was sent.",
        ))
    elif reason == "no_recipients":
        st.info(texts.get("newsletter_no_subscribers", "No active subscribers for this family."))
    elif result.get("sent"):
        st.success(f"{texts.get('published', 'Published')} ({count})")
    else:
        st.error(texts.get("failed", "Failed"))


def main():
    """Choose a family and language, manage subscribers, preview, then send."""
    texts = UI_TEXTS
    role = st.session_state.get("user_state")
    own_family_id = cu.current_family_id()
    is_platform = role == dbm.User_State["p_admin"]

    st.header(f"{texts.get('newsletter', 'Newsletter')} {texts.get('publication', 'Publication')}")

    if is_platform:
        requested = st.number_input(
            "family_id",
            min_value=0,
            value=int(own_family_id or 0),
            step=1,
            key="newsletter_family_id",
        )
    else:
        requested = own_family_id
        st.text_input(
            "family_id",
            value="" if own_family_id is None else str(own_family_id),
            disabled=True,
            key="newsletter_family_id_locked",
        )
    try:
        family_id = nl.selected_family_id(role, own_family_id, requested)
    except PermissionError:
        st.error(texts.get("permission_error", "Need permission to access this page."))
        st.stop()
    except ValueError:
        st.error(texts.get("failed", "Failed"))
        st.stop()
    if family_id is None:
        st.error(texts.get("newsletter_no_subscribers", "No active subscribers for this family."))
        st.stop()

    choices = _language_choices(family_id)
    current = (st.session_state.get("app_context") or {}).get("language")
    index = choices.index(current) if current in choices else 0
    lang = st.selectbox(
        f"{texts.get('select', 'Select')} {texts.get('language', 'Language')}",
        choices,
        index=index,
        key="newsletter_language",
    )

    base = nl.default_base_url()
    safe_base = html.escape(base, quote=True)
    st.markdown(
        f'<a href="{safe_base}/" target="_blank">FamilyTreesOps</a>',
        unsafe_allow_html=True,
    )
    st.caption(texts.get(
        "newsletter_snapshot_help",
        "Preview is the current operations-server home page for this family and language. "
        "Mail is sent only after preview, and only to this family's active subscribers.",
    ))

    if "newsletter_manage" not in st.session_state:
        st.session_state.newsletter_manage = False
    if st.button(
        f"{texts.get('subscriber', 'Subscriber')} {texts.get('management', 'Management')}",
        key="newsletter_manage_button",
    ):
        st.session_state.newsletter_manage = True
    if st.session_state.newsletter_manage:
        _subscriber_panel(family_id, lang, texts)

    st.subheader(f"{texts.get('newsletter', 'Newsletter')} {texts.get('publication', 'Publication')}")
    if st.button(texts.get("preview", "Preview"), key="newsletter_preview_button"):
        try:
            st.session_state.newsletter_preview = nl.build_snapshot(family_id, lang)
        except SystemExit as exc:
            st.session_state.newsletter_preview = None
            st.error(str(exc) or texts.get("failed", "Failed"))
        except Exception as exc:
            st.session_state.newsletter_preview = None
            st.error(f"{texts.get('failed', 'Failed')}: {exc}")

    preview = st.session_state.get("newsletter_preview") or {}
    matches = (
        preview.get("family_id") == family_id
        and preview.get("lang") == lang
        and preview.get("html")
    )
    if not matches:
        return
    recipients = preview.get("recipients") or []
    st.markdown(f"**{texts.get('recipients', 'Recipients')}** ({len(recipients)})")
    if recipients:
        st.write(", ".join(recipients))
    else:
        st.info(texts.get("newsletter_no_subscribers", "No active subscribers for this family."))
    st.html(preview["html"])
    if st.button(texts.get("send", "Send"), type="primary", key="newsletter_send_button"):
        _show_delivery(nl.deliver_newsletter(preview, send=True), texts)


cu.init_session_state()
cu.apply_ui_preferences()
UI_TEXTS = fu.session_texts()

require_role(dbm.User_State["p_admin"], dbm.User_State["f_admin"])
render_sidebar()
main()
