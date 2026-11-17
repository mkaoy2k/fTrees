"""Article management.

A family admin sees and writes only their own family_id. A platform admin
sees every family, can filter by family_id, and chooses the family_id when
creating an article. family_id is shown on each row.
"""
import importlib.util
import logging
import os
import subprocess
import sys

import pandas as pd
import streamlit as st

import context_utils as cu
import db_utils as dbm
import email_utils as eu
import funcUtils as fu
from nav import render_sidebar, require_role

log = logging.getLogger(__name__)


def _ops_texts():
    """Operations-server strings for the signed-in language, else US."""
    catalogs = fu.load_ops_L10N()
    language = (st.session_state.get("app_context") or {}).get("language") or "US"
    if language not in catalogs:
        language = "US" if "US" in catalogs else next(iter(catalogs), None)
    if not language:
        return {}
    return catalogs.get(language) or {}


def format_timestamps(df):
    """Show created_at and updated_at in the owner's timezone."""
    for col in ("created_at", "updated_at"):
        if col not in df.columns:
            continue
        try:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            df[col] = df[col].apply(
                lambda value: value.tz_convert("America/Los_Angeles").strftime("%Y-%m-%d %H:%M:%S")
                if pd.notna(value) else None
            )
        except Exception as exc:
            st.warning(f"Could not format {col}: {exc}")
    return df


def display_article(article, info):
    """Show one article's fields in two columns."""
    items = list(article.items())
    half = (len(items) + 1) // 2
    with info:
        col1, col2 = st.columns([5, 5])
        for key, value in items[:half]:
            if key in ("created_at", "updated_at") and value is not None:
                value = pd.to_datetime(value, utc=True).tz_convert("America/Los_Angeles").strftime("%Y-%m-%d %H:%M:%S")
            with col1:
                st.write(f"**{key.replace('_', ' ').title()}:** {value}")
        for key, value in items[half:]:
            if key in ("created_at", "updated_at") and value is not None:
                value = pd.to_datetime(value, utc=True).tz_convert("America/Los_Angeles").strftime("%Y-%m-%d %H:%M:%S")
            with col2:
                st.write(f"**{key.replace('_', ' ').title()}:** {value}")


def _notify(publisher, subject, html, article, review_id, success_text, failure_text):
    """Email the article's user, or the admin address when the user has none."""
    user_email = None
    if article.get("user_id"):
        user_email = dbm.get_user_email(article["user_id"])
    if not user_email:
        msg = (
            f"{fu.get_function_name()}: {UI_TEXTS['USER']} {UI_TEXTS['EMAIL']} "
            f"{UI_TEXTS['NOT_FOUND']}. {UI_TEXTS['TICKET']} {UI_TEXTS['ID']}: {review_id}"
        )
        log.error(msg)
        st.error(msg)
        return
    admin_email = st.session_state.get("admin_email") or os.getenv("DB_ADMIN", "")
    to_emails = [user_email] if user_email else [admin_email]
    if publisher.publish_email(subject, f"ref: {UI_TEXTS['TICKET']} {UI_TEXTS['ID']}: {review_id}", html, to_emails):
        log.info(success_text)
        st.success(success_text)
    else:
        log.error(failure_text)
        st.error(failure_text)


def _query_kwargs(scope):
    return {"family_id": scope["family_id"], "all_families": scope["all_families"]}


def launch_article_editor(family_id):
    """Start the optional PyQt editor scoped to one integer family id."""
    if importlib.util.find_spec("PyQt5") is None:
        st.error("The article editor needs PyQt5. Install it with: pip install 'PyQt5>=5.15.11'")
        return False
    try:
        number = dbm.parse_family_id(family_id)
    except ValueError:
        number = None
    if number is None:
        st.error("Choose a numeric family_id before opening the editor.")
        return False
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ops_artBatch.py")
    subprocess.Popen(
        [sys.executable, script, "--db", dbm.db_path, "--table", dbm.db_tables["article"], "--family-id", str(number)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def main():
    """Query, create, review, and delete articles for the signed-in role."""
    global UI_TEXTS
    own_family_id = cu.current_family_id()
    is_platform = st.session_state.get("user_state") == dbm.User_State["p_admin"]
    ops_svr = os.getenv("OPS_SVR", "http://localhost:5566")
    st.header(f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['TABLE']} {UI_TEXTS['MANAGEMENT']}")
    st.markdown(f"### Current family_id: {own_family_id}")

    filter_all = False
    filter_family = own_family_id
    if is_platform:
        st.caption("Platform admin: every family's articles are listed unless you filter.")
        filter_col, id_col = st.columns([2, 2])
        with filter_col:
            filter_all = st.checkbox("All families", value=True)
        with id_col:
            filter_family = st.number_input(
                "Filter family_id",
                min_value=0,
                value=int(own_family_id or 0),
                step=1,
                disabled=filter_all,
            )
    scope = dbm.article_access_scope(
        st.session_state.get("user_state"),
        own_family_id,
        platform_admin=dbm.User_State["p_admin"],
        filter_all=filter_all,
        filter_family_id=filter_family,
    )
    query = _query_kwargs(scope)

    if "article_id" not in st.session_state:
        st.session_state.article_id = 1
    if "publisher" not in st.session_state:
        context = st.session_state.get("app_context") or {}
        st.session_state.publisher = eu.EmailPublisher(
            context.get("email_user"),
            context.get("email_pass"),
        )

    with st.container():
        try:
            st.subheader(f"{UI_TEXTS['QUERY']} {UI_TEXTS['ARTICLES']}")
            cats = list(dbm.Article_Categories.keys())
            news_index = cats.index("news") if "news" in cats else 0
            cat_key = st.selectbox(f"{UI_TEXTS['CATEGORY']}:", options=cats, index=news_index)
            col1, col2 = st.columns([5, 5])
            with col1:
                limit = st.number_input(
                    f"{UI_TEXTS['NUMBER_OF_APPROVED_ARTICLES']}",
                    min_value=1,
                    max_value=10,
                    value=10,
                    step=1,
                    format="%d",
                )
            with col2:
                by_days = st.number_input(
                    f"{UI_TEXTS['NUMBER_OF_DAYS']}",
                    min_value=1,
                    max_value=365,
                    value=7,
                    step=1,
                    format="%d",
                )

            articles = []
            btn11, btn12 = st.columns([5, 5])
            with btn11:
                if st.button(f"{UI_TEXTS['QUERY']} {UI_TEXTS['BY_LIMIT']}"):
                    articles = dbm.get_articles(
                        dbm.Article_Categories[cat_key],
                        limit=limit,
                        **query,
                    )
            with btn12:
                if st.button(f"{UI_TEXTS['QUERY']} {UI_TEXTS['BY_DAYS']}"):
                    articles = dbm.get_articles_byDays(
                        dbm.Article_Categories[cat_key],
                        byDays=by_days,
                        **query,
                    )

            info1, _info2 = st.columns([15, 1])
            if articles:
                frame = format_timestamps(pd.DataFrame(articles))
                with info1:
                    st.caption("Each row includes family_id.")
                    st.dataframe(frame)
                    st.success(f"{UI_TEXTS['RETRIEVED']} {len(articles)} {UI_TEXTS['ARTICLES']}")

            st.subheader(f"{UI_TEXTS.get('ADD', 'Add')} {UI_TEXTS['ARTICLE']}")
            with st.form("create_article"):
                title = st.text_input(UI_TEXTS["TITLE"])
                content = st.text_area(UI_TEXTS["CONTENT"])
                author = st.text_input(UI_TEXTS["AUTHOR"])
                source = st.text_input(UI_TEXTS["SOURCE"])
                if is_platform:
                    create_family = st.number_input(
                        "family_id",
                        min_value=0,
                        value=int(filter_family or 0),
                        step=1,
                        key="create_article_family_id",
                    )
                else:
                    create_family = own_family_id
                    st.write(f"family_id: {create_family}")
                create_clicked = st.form_submit_button(f"{UI_TEXTS.get('ADD', 'Add')} {UI_TEXTS['ARTICLE']}")
            if create_clicked:
                created = dbm.add_or_update_article(
                    {
                        "title": title,
                        "content": content,
                        "category": dbm.Article_Categories[cat_key],
                        "author": author,
                        "source": source,
                        "l10n": (st.session_state.get("app_context") or {}).get("language") or "US",
                    },
                    family_id=create_family,
                )
                if created:
                    st.success(f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: {created} family_id: {create_family}")
                else:
                    st.error(f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['FAILED']}")

            editor_family = create_family if is_platform else own_family_id
            if st.button(f"{UI_TEXTS.get('OPEN', 'Open')} {UI_TEXTS['ARTICLE']} {UI_TEXTS.get('EDITOR', 'Editor')}"):
                if launch_article_editor(editor_family):
                    st.success(f"Article editor launched for family_id {editor_family}")

            col1, col2 = st.columns([5, 5])
            with col1:
                cursor_id = st.number_input(
                    f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}:",
                    min_value=1,
                    value=int(st.session_state.article_id),
                    step=1,
                    format="%d",
                )
            with col2:
                article_state_options = list(dbm.Article_State.keys())
                article_state = st.selectbox(
                    f"{UI_TEXTS['ARTICLE_STATE']}:",
                    options=article_state_options,
                    index=len(article_state_options) - 1,
                )

            btn21, btn22 = st.columns([5, 5])
            with btn21:
                if st.button(f"{UI_TEXTS['QUERY']} {UI_TEXTS['BY_ID']}"):
                    article = dbm.get_article_byId(int(cursor_id), **query)
                    if article:
                        display_article(article, info1)
                        st.session_state.article_id = article["id"]
                        st.success(f"{UI_TEXTS['RETRIEVED']} {UI_TEXTS['ARTICLE']}: {article['id']}")
                    else:
                        st.error(
                            f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: {cursor_id} {UI_TEXTS['NOT_FOUND']}"
                        )
            with btn22:
                if st.button(f"{UI_TEXTS['QUERY']} {UI_TEXTS['NEXT']} {UI_TEXTS['FEEDBACK']} {UI_TEXTS['BY_STATE']}"):
                    result = dbm.get_next_article(
                        int(cursor_id),
                        dbm.Article_Categories[cat_key],
                        is_censored=dbm.Article_State[article_state],
                        **query,
                    )
                    if result is not None:
                        article_id, article = result
                        display_article(article, info1)
                        st.session_state.article_id = article_id
                        st.success(
                            f"{UI_TEXTS['RETRIEVED']} '{cat_key}':'{article_state}' "
                            f"{UI_TEXTS['NEXT']} {UI_TEXTS['ARTICLE']}"
                        )
                    else:
                        st.error(f"'{cat_key}':'{article_state}' {UI_TEXTS['ARTICLE']} {UI_TEXTS['NOT_FOUND']}")

            with st.expander(f"{UI_TEXTS['DANGER_ZONE']}", expanded=False):
                st.warning(UI_TEXTS["CANNOT_BE_UNDONE"])
                if st.button(f"{UI_TEXTS['DELETE']} {UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: {int(cursor_id)}"):
                    if dbm.delete_article(int(cursor_id), **query):
                        st.success(f"{UI_TEXTS['DELETE']} {UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: {int(cursor_id)}")
                    else:
                        st.error(
                            f"{UI_TEXTS['DELETE']} {UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: "
                            f"{int(cursor_id)} {UI_TEXTS['FAILED']}"
                        )

            st.subheader(f"{UI_TEXTS['REVIEW']} {UI_TEXTS['FEEDBACK']}")
            info3, _info4 = st.columns([15, 1])
            result = dbm.get_next_article(
                1,
                dbm.Article_Categories["feedback"],
                is_censored=dbm.Article_State["pending"],
                **query,
            )
            if result is None:
                st.info(f"{UI_TEXTS['NO_MORE']} {UI_TEXTS['PENDING']} {UI_TEXTS['FEEDBACKS']}")
            else:
                review_id, article = result
                article["category"] = dbm.Article_Categories[cat_key]
                display_article(article, info3)
                btn31, btn32 = st.columns([5, 5])
                with btn31:
                    label = (
                        f"{UI_TEXTS['APPROVE']} {UI_TEXTS['ID']}: {review_id} "
                        f"{UI_TEXTS['CATEGORY']}: {dbm.Article_Categories[cat_key]}"
                    )
                    if st.button(label):
                        if dbm.review_article(
                            review_id,
                            dbm.Article_State["approved"],
                            category=dbm.Article_Categories[cat_key],
                            **query,
                        ):
                            subject = f"{UI_TEXTS['TICKET']}: {review_id} {UI_TEXTS['APPROVED']}"
                            html = (
                                f"<p>{UI_TEXTS['ARTICLE']} {UI_TEXTS['APPROVED']}:</p>"
                                f"<p><strong>{UI_TEXTS['TITLE']}:</strong> {article.get('title', '')}</p>"
                                f"<p><strong>{UI_TEXTS['CATEGORY']}:</strong> {dbm.Article_Categories[cat_key]}</p>"
                                f"<p><strong>{UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}:</strong> {review_id}</p>"
                                f"<p>{UI_TEXTS['THANK_YOU']}!</p>"
                                f"<p>Visit us at: <a href=\"{ops_svr}\">FamilyTreesOps</a></p>"
                            )
                            _notify(
                                st.session_state.publisher,
                                subject,
                                html,
                                article,
                                review_id,
                                f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['ID']}: {review_id} "
                                f"{UI_TEXTS['CATEGORY']}: {dbm.Article_Categories[cat_key]}",
                                f"{UI_TEXTS['EMAIL_SENT_FAILED']}. {UI_TEXTS['TICKET']} {UI_TEXTS['ID']}: {review_id}",
                            )
                        else:
                            st.error(f"{UI_TEXTS['APPROVE']} {UI_TEXTS['FEEDBACK']} {UI_TEXTS['FAILED']}")
                with btn32:
                    if st.button(f"{UI_TEXTS['REJECT']} {UI_TEXTS['FEEDBACK']} {UI_TEXTS['ID']}: {review_id}"):
                        if dbm.review_article(
                            review_id,
                            dbm.Article_State["rejected"],
                            category=dbm.Article_Categories[cat_key],
                            **query,
                        ):
                            st.success(
                                f"{UI_TEXTS['REJECT']} {UI_TEXTS['FEEDBACK']} {UI_TEXTS['ID']}: {review_id}"
                            )
                        else:
                            st.error(f"{UI_TEXTS['REJECT']} {UI_TEXTS['FEEDBACK']} {UI_TEXTS['FAILED']}")

            st.subheader(f"{UI_TEXTS['REVIEW']} {UI_TEXTS['CONTACT']}")
            info5, _info6 = st.columns([15, 1])
            result = dbm.get_next_article(
                1,
                dbm.Article_Categories["contact"],
                is_censored=dbm.Article_State["pending"],
                **query,
            )
            if result is None:
                st.info(f"{UI_TEXTS['NO_MORE']} {UI_TEXTS['PENDING']} {UI_TEXTS['CONTACTS']}")
                st.stop()
            review_id, article = result
            display_article(article, info5)
            btn41, btn42 = st.columns([5, 5])
            with btn41:
                if st.button(f"Completed ID: {review_id}"):
                    if dbm.review_article(
                        review_id,
                        dbm.Article_State["action_taken"],
                        **query,
                    ):
                        subject = f"{UI_TEXTS['TICKET']} {review_id} {UI_TEXTS['COMPLETED']}"
                        html = (
                            f"<p>{UI_TEXTS['CONTACT_REQUEST_COMPLETED']}</p>"
                            f"<p><strong>{UI_TEXTS['TITLE']}:</strong> {article.get('title', '')}</p>"
                            f"<p><strong>{UI_TEXTS['CONTENT']}:</strong> {article.get('content', '')}</p>"
                            f"<p><strong>{UI_TEXTS['TICKET']} {UI_TEXTS['ID']}:</strong> {review_id}</p>"
                            f"<p>{UI_TEXTS['THANK_YOU']}!</p>"
                            f"<p>Visit us at: <a href=\"{ops_svr}\">FamilyTreesOps</a></p>"
                        )
                        _notify(
                            st.session_state.publisher,
                            subject,
                            html,
                            article,
                            review_id,
                            f"{UI_TEXTS['CONTACT']} {UI_TEXTS['ID']}: {review_id} {UI_TEXTS['COMPLETED']}",
                            f"{UI_TEXTS['CONTACT']} {UI_TEXTS['ID']}: {review_id} {UI_TEXTS['FAILED']}",
                        )
                    else:
                        st.error(f"{UI_TEXTS['CONTACT']} {UI_TEXTS['ID']}: {review_id} {UI_TEXTS['FAILED']}")
            with btn42:
                if st.button(f"{UI_TEXTS['IGNORE']} ID: {review_id}"):
                    if dbm.review_article(
                        review_id,
                        dbm.Article_State["ignored"],
                        **query,
                    ):
                        st.success(f"{UI_TEXTS['CONTACT']} {UI_TEXTS['ID']}: {review_id} {UI_TEXTS['IGNORED']}")
                    else:
                        st.error(f"{UI_TEXTS['IGNORE']} {UI_TEXTS['CONTACT']} {UI_TEXTS['ID']}: {review_id} {UI_TEXTS['FAILED']}")
        except Exception as exc:
            st.error(f"{UI_TEXTS['ARTICLE']} {UI_TEXTS['MANAGEMENT']} {UI_TEXTS['FAILED']}: {exc}")
            st.exception(exc)


cu.init_session_state()
cu.apply_ui_preferences()
UI_TEXTS = _ops_texts()

require_role(dbm.User_State["p_admin"], dbm.User_State["f_admin"])
render_sidebar()
main()
