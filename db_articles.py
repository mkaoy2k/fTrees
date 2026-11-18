"""Article records scoped to one family.

Reads return only rows whose ``family_id`` matches the requested family.
Writes store that family id. A missing family id matches nothing and
refuses the write, so a caller cannot fall through to every family or to
the column default.
"""
import sqlite3
from datetime import datetime, timedelta

from db_connection import (
    Article_Categories,
    Article_State,
    coerce_family_id,
    db_tables,
    get_db_connection,
    log,
    parse_family_id,
    quote_ident,
)


def _article_table():
    return quote_ident(db_tables["articles"])


def _family_clause(family_id, all_families=False):
    """SQL predicate and params.

    ``all_families`` matches every row (platform admin). A blank or
    non-numeric family id matches nothing, so a caller cannot leak rows
    by forgetting the id.
    """
    if all_families:
        return "1 = 1", []
    try:
        number = parse_family_id(family_id)
    except ValueError:
        return "1 = 0", []
    if number is None:
        return "1 = 0", []
    return "family_id = ?", [number]


def article_access_scope(role, own_family_id, *, platform_admin, filter_all=False, filter_family_id=None):
    """Query scope for the article page.

    A platform admin sees every family unless they set a family filter.
    A family admin is always limited to their own family id.
    """
    if role == platform_admin:
        if filter_all:
            return {"family_id": None, "all_families": True}
        try:
            number = parse_family_id(filter_family_id)
        except ValueError:
            number = None
        return {"family_id": number, "all_families": False}
    try:
        number = parse_family_id(own_family_id)
    except ValueError:
        number = None
    return {"family_id": number, "all_families": False}


def get_articles(category, limit=None, family_id=None, all_families=False):
    """Approved articles in one category for one family, newest id first.

    ``category`` may be ``all``. Returns None when the category is unknown
    or nothing matches. ``limit`` 0 returns an empty list.
    """
    if not category or category not in Article_Categories.values():
        log.warning(
            "Invalid category %r for get_articles. Expected one of: %s",
            category,
            ", ".join(Article_Categories.values()),
        )
        return None
    if limit == 0:
        return []

    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    query = f"""
        SELECT * FROM {_article_table()}
        WHERE is_censored = ?
        AND {family_sql}
    """
    params = [Article_State["approved"], *family_params]
    if category.lower() != "all":
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY id DESC"
    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(int(limit))

    try:
        with get_db_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        articles = [dict(row) for row in rows]
        return articles or None
    except sqlite3.Error as exc:
        log.error("Database error while retrieving articles: %s", exc)
        return None


def get_articles_byDays(category, byDays=7, family_id=None, all_families=False):
    """Approved articles in one category updated within the last ``byDays`` days."""
    if not category or category not in Article_Categories.values():
        log.warning(
            "Invalid category %r for get_articles_byDays. Expected one of: %s",
            category,
            ", ".join(Article_Categories.values()),
        )
        return None
    days_ago = datetime.now() - timedelta(days=int(byDays))
    date_str = days_ago.strftime("%Y-%m-%d %H:%M:%S")
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {_article_table()}
                WHERE is_censored = ?
                AND category = ?
                AND updated_at >= ?
                AND {family_sql}
                ORDER BY updated_at DESC
                """,
                (Article_State["approved"], category, date_str, *family_params),
            ).fetchall()
        if not rows:
            return None
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        log.error("Database error while retrieving recent articles: %s", exc)
        return None


def get_article_languages(family_id=None, all_families=False):
    """Distinct article language codes for one family."""
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT l10n FROM {_article_table()}
                WHERE l10n IS NOT NULL AND {family_sql}
                ORDER BY l10n ASC
                """,
                tuple(family_params),
            ).fetchall()
        return [row[0] for row in rows if row[0]]
    except sqlite3.Error as exc:
        log.error("Error retrieving article languages: %s", exc)
        return []


def get_article_categories(family_id=None, all_families=False):
    """Distinct article categories stored for one family."""
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT category FROM {_article_table()}
                WHERE {family_sql}
                ORDER BY category ASC
                """,
                tuple(family_params),
            ).fetchall()
        return [row[0] for row in rows]
    except sqlite3.Error as exc:
        log.error("Error fetching article categories: %s", exc)
        return []


def get_article_byId(article_id, family_id=None, all_families=False):
    """One article, only when it belongs to ``family_id``."""
    if not isinstance(article_id, int) or article_id <= 0:
        log.warning("Invalid article ID provided: %s", article_id)
        return None
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM {_article_table()}
                WHERE id = ? AND {family_sql}
                """,
                (article_id, *family_params),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as exc:
        log.error("Error fetching article %s: %s", article_id, exc)
        return None


def get_next_article(article_id, category, is_censored=Article_State["pending"], family_id=None, all_families=False):
    """Next article at or after ``article_id`` in this family, category, and state.

    Returns ``(id, article)`` or None.
    """
    if not isinstance(article_id, int) or article_id <= 0:
        return None
    if not isinstance(category, str) or category not in get_article_categories(family_id, all_families=all_families):
        return None
    if not isinstance(is_censored, int) or is_censored not in Article_State.values():
        return None
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM {_article_table()}
                WHERE is_censored = ?
                AND id >= ?
                AND category = ?
                AND {family_sql}
                ORDER BY id ASC
                LIMIT 1
                """,
                (is_censored, article_id, category, *family_params),
            ).fetchone()
        if not row:
            return None
        article = dict(row)
        return article["id"], article
    except sqlite3.Error as exc:
        log.error("Error fetching next article: %s", exc)
        return None


def review_article(article_id, is_censored, category=None, family_id=None, all_families=False):
    """Set the review state of one article in this family. Optionally reclassify it."""
    if not isinstance(article_id, int) or article_id <= 0:
        return False
    if is_censored not in Article_State.values():
        return False
    if get_article_byId(article_id, family_id, all_families=all_families) is None:
        return False
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            if category is None:
                cursor = conn.execute(
                    f"""
                    UPDATE {_article_table()}
                    SET is_censored = ?
                    WHERE id = ? AND {family_sql}
                    """,
                    (is_censored, article_id, *family_params),
                )
            else:
                cursor = conn.execute(
                    f"""
                    UPDATE {_article_table()}
                    SET is_censored = ?, category = ?
                    WHERE id = ? AND {family_sql}
                    """,
                    (is_censored, category, article_id, *family_params),
                )
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        log.error("Error reviewing article %s: %s", article_id, exc)
        return False


def add_or_update_article(article_data, update=False, family_id=None):
    """Insert an article, or update the same title inside this family.

    ``family_id`` wins over any family id inside ``article_data``. The stored
    value is always this family's id. Returns the article id, or None.
    """
    if not article_data or "title" not in article_data:
        log.error("Missing required article data or title")
        return None
    scoped = family_id if family_id is not None else article_data.get("family_id")
    try:
        stored_family = coerce_family_id(scoped)
    except ValueError:
        log.error("Refusing article write with non-numeric family_id %r", scoped)
        return None
    if stored_family is None:
        log.error("Refusing article write without a family_id")
        return None

    family_sql, family_params = _family_clause(stored_family)
    payload = dict(article_data)
    payload["family_id"] = stored_family

    try:
        with get_db_connection() as conn:
            columns = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({_article_table()})").fetchall()
            }
            columns.discard("id")
            columns.discard("created_at")
            existing = conn.execute(
                f"""
                SELECT id FROM {_article_table()}
                WHERE title = ? AND {family_sql}
                """,
                (payload["title"], *family_params),
            ).fetchone()
            if existing:
                if not update:
                    log.error("Article with title %r already exists in this family", payload["title"])
                    return None
                article_id = existing["id"]
                fields = []
                params = []
                for field, value in payload.items():
                    if field in columns:
                        fields.append(f"{quote_ident(field)} = ?")
                        params.append(value)
                if "is_censored" not in payload and "is_censored" in columns:
                    fields.append(f"{quote_ident('is_censored')} = ?")
                    params.append(Article_State["pending"])
                if not fields:
                    return None
                params.extend([article_id, *family_params])
                conn.execute(
                    f"""
                    UPDATE {_article_table()}
                    SET {", ".join(fields)}
                    WHERE id = ? AND {family_sql}
                    """,
                    tuple(params),
                )
                return article_id

            required = ("title", "content", "category", "author", "source")
            missing = [field for field in required if field not in payload]
            if missing:
                log.error("Missing required article fields: %s", ", ".join(missing))
                return None
            if "is_censored" not in payload:
                payload["is_censored"] = Article_State["pending"]
            fields = []
            values = []
            for field, value in payload.items():
                if field in columns:
                    fields.append(quote_ident(field))
                    values.append(value)
            conn.execute(
                f"""
                INSERT INTO {_article_table()} ({", ".join(fields)})
                VALUES ({", ".join("?" for _ in fields)})
                """,
                tuple(values),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.Error as exc:
        log.error("Database error in add_or_update_article: %s", exc)
        return None


def delete_article(article_id, family_id=None, all_families=False):
    """Delete one article when it belongs to ``family_id``."""
    if not isinstance(article_id, int) or article_id <= 0:
        return False
    family_sql, family_params = _family_clause(family_id, all_families=all_families)
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                f"""
                DELETE FROM {_article_table()}
                WHERE id = ? AND {family_sql}
                """,
                (article_id, *family_params),
            )
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        log.error("Error deleting article %s: %s", article_id, exc)
        return False
