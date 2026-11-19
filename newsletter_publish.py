"""Build and send a family newsletter from the operations-server home page.

The public journal (``ops_svr``) keeps serving the family it was started
with. This module renders that same home page for a chosen family and
language, rewrites relative links so an email client can load them, and
sends only to that family's active subscribers whose ``l10n`` matches
the edition.

Nothing here sends mail unless ``send=True`` and the process is allowed
to deliver. ``CI``, ``GITHUB_ACTIONS``, and ``NEWSLETTER_DISABLE_SEND``
block delivery.
"""
import os
import re
from pathlib import Path
from urllib.parse import urljoin

import db_utils as dbm
import email_utils as eu

NOT_MEMBER_MESSAGE = (
    "This email is not a registered member of this family. "
    "此電子郵件不是本家族的已登記成員。"
)
INVALID_EMAIL_MESSAGE = (
    "That email address is not valid. "
    "這個電子郵件地址無效。"
)

_APP_ROOT = Path(__file__).resolve().parent
_CSS_LINK = re.compile(
    r"<link\b[^>]*\bhref\s*=\s*([\"'])([^\"']*main\.css)\1[^>]*>",
    re.IGNORECASE,
)
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_ATTR_URL = re.compile(
    r"""(?i)\b(href|src)\s*=\s*(["'])(.*?)\2"""
)
_CSS_URL = re.compile(
    r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""",
    re.IGNORECASE,
)


def default_base_url():
    """Public base used for links inside the newsletter.

    ``OPS_SVR`` wins when it is set, because that is the address readers
    should open. Otherwise the URL is the listener (``OPS_SVR_HOST`` and
    ``OPS_SVR_PORT``). A wildcard bind is written as ``127.0.0.1`` so the
    link is an address a client can open.
    """
    configured = os.getenv("OPS_SVR", "").strip()
    if configured:
        return configured.rstrip("/")
    host = os.getenv("OPS_SVR_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    raw_port = os.getenv("OPS_SVR_PORT", "5566")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 5566
    if port < 1 or port > 65535:
        port = 5566
    return f"http://{host}:{port}"


def selected_family_id(role, own_family_id, requested=None):
    """Family the signed-in role may publish for.

    A platform admin may pass any integer family id. A family admin is
    locked to the family id stored at login. Any other role is refused.
    """
    if role == dbm.User_State["p_admin"]:
        return dbm.parse_family_id(requested)
    if role == dbm.User_State["f_admin"]:
        return dbm.parse_family_id(own_family_id)
    raise PermissionError("newsletter is limited to family and platform admins")


def add_family_subscriber(email, family_id, lang):
    """Activate an existing member of ``family_id``.

    The address is stripped and compared without case. A missing user, a
    user from another family, and an invalid address all fail. No row is
    inserted, and ``family_id`` on the existing row is left alone. The
    resulting ``is_active`` value is the same one ``ops_svr`` stores after
    a subscription is confirmed.
    """
    normalized = dbm.normalize_subscriber_email(email)
    if not normalized or not eu.validate_email(normalized):
        return {"ok": False, "reason": "invalid_email", "email": normalized or ""}
    try:
        number = dbm.parse_family_id(family_id)
    except ValueError:
        number = None
    if number is None or not dbm.is_family_member(normalized, number):
        return {"ok": False, "reason": "not_member", "email": normalized}
    before = dbm.get_subscriber(normalized)
    if not before or not dbm.family_ids_equal(before.get("family_id"), number):
        return {"ok": False, "reason": "not_member", "email": normalized}
    try:
        saved = dbm.add_or_update_subscriber({
            "email": normalized,
            "is_active": dbm.Subscriber_State["active"],
            "token": "",
            "l10n": lang or before.get("l10n") or "US",
        })
    except (TypeError, ValueError):
        saved = False
    after = dbm.get_subscriber(normalized)
    if (
        not saved
        or not after
        or after.get("is_active") != dbm.Subscriber_State["active"]
        or not dbm.family_ids_equal(after.get("family_id"), number)
    ):
        return {"ok": False, "reason": "failed", "email": normalized}
    return {"ok": True, "reason": "added", "email": after.get("email") or normalized}


def unsubscribe_family_subscriber(email, family_id):
    """Mark one member of this family inactive, the same way ``ops_svr`` does.

    Addresses outside the family are left unchanged.
    """
    normalized = dbm.normalize_subscriber_email(email)
    if not normalized or not dbm.is_family_member(normalized, family_id):
        return False
    return bool(dbm.remove_subscriber(normalized))


def active_recipient_emails(family_id, lang):
    """Active subscribers of this family whose ``l10n`` equals ``lang``.

    The comparison is the same exact match ``ops_svr`` used when ``/pub``
    loaded subscribers with ``get_subscribers(..., lang=lang)``. A blank
    language matches nobody.
    """
    if not isinstance(lang, str) or not lang:
        return []
    emails = []
    for row in dbm.list_family_subscribers(family_id, state="active"):
        if row.get("l10n") != lang:
            continue
        email = dbm.normalize_subscriber_email(row.get("email"))
        if email and email not in emails:
            emails.append(email)
    return emails


def family_display_name(family_id):
    """Stored family name, or None when the row or the name is missing.

    A database error is treated as a missing name so the subject line can
    still be built.
    """
    try:
        number = dbm.parse_family_id(family_id)
    except ValueError:
        return None
    if number is None:
        return None
    try:
        family = dbm.get_family(number)
    except Exception:
        return None
    if not isinstance(family, dict):
        return None
    name = family.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _skip_url(url):
    lowered = url.lower()
    return (
        not url
        or lowered.startswith((
            "http://", "https://", "mailto:", "data:", "cid:", "javascript:", "#",
        ))
        or url.startswith("//")
    )


def _join(base_url, url):
    if _skip_url(url):
        return url
    return urljoin(base_url, url)


def prepare_email_html(html, base_url):
    """Inline local CSS, drop scripts, and make remaining URLs absolute.

    Email clients do not resolve ``/static/...`` or ``pics/photo.jpg``
    against the operations server, and they ignore a linked stylesheet.
    """
    if not html:
        return ""
    base = (base_url or default_base_url()).rstrip("/") + "/"
    css_path = _APP_ROOT / "static" / "main.css"
    css = ""
    if css_path.is_file():
        css = css_path.read_text(encoding="utf-8")

    def _inline_css(match):
        return f"<style>{css}</style>"

    prepared = _SCRIPT.sub("", html)
    prepared = _CSS_LINK.sub(_inline_css, prepared)

    def _attr(match):
        attr, quote, url = match.group(1), match.group(2), match.group(3).strip()
        absolute = _join(base, url)
        return f"{attr}={quote}{absolute}{quote}"

    def _css(match):
        quote, url = match.group(1) or "", match.group(2).strip()
        absolute = _join(base, url)
        return f"url({quote}{absolute}{quote})"

    prepared = _ATTR_URL.sub(_attr, prepared)
    return _CSS_URL.sub(_css, prepared)


def capture_ops_main_page(family_id, lang, *, fetcher=None, base_url=None):
    """HTML of the operations-server home page for this family and language.

    The default fetcher renders through ``ops_svr`` (the same template and
    article query as the public home page). Tests pass a fetcher that
    stands in for that server.
    """
    base = (base_url or default_base_url()).rstrip("/")
    if fetcher is None:
        from ops_svr import render_main_snapshot
        return render_main_snapshot(family_id, lang, base)
    raw = fetcher(family_id, lang, base)
    if not isinstance(raw, str):
        raise TypeError("ops_svr snapshot must be HTML text")
    return prepare_email_html(raw, base)


def _journal_title(lang):
    try:
        from funcUtils import load_ops_L10N
        catalogs = load_ops_L10N() or {}
    except Exception:
        catalogs = {}
    loc = catalogs.get(lang) or catalogs.get("US") or {}
    title = loc.get("HOME_HTML_H1")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "Newsletter"


def newsletter_subject(family_id, lang):
    """Journal heading plus the family name and family id.

    A missing family row, a blank name, or a lookup error still keeps the
    family id on the subject.
    """
    title = _journal_title(lang)
    try:
        number = dbm.parse_family_id(family_id)
    except ValueError:
        number = None
    name = family_display_name(family_id)
    if number is None:
        return title
    if name:
        return f"{title} — {name} ({number})"
    return f"{title} — {number}"


def build_snapshot(family_id, lang, *, fetcher=None, base_url=None):
    """Preview payload. This never sends mail."""
    number = dbm.parse_family_id(family_id)
    if number is None:
        raise ValueError("family_id is required")
    base = (base_url or default_base_url()).rstrip("/")
    html = capture_ops_main_page(number, lang, fetcher=fetcher, base_url=base)
    return {
        "html": html,
        "subject": newsletter_subject(number, lang),
        "recipients": active_recipient_emails(number, lang),
        "family_id": number,
        "lang": lang,
        "base_url": base,
    }


def sending_is_blocked(env=None):
    """True when this process must not open an SMTP connection."""
    values = os.environ if env is None else env
    if values.get("CI") or values.get("GITHUB_ACTIONS"):
        return True
    flag = (values.get("NEWSLETTER_DISABLE_SEND") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def default_mailer(recipients, subject, html):
    """Send one HTML message through the operations server's Flask-Mail."""
    import ops_svr
    with ops_svr.app.app_context():
        return bool(eu.send_email(ops_svr.g_fmail, list(recipients), subject, html))


def deliver_newsletter(snapshot, *, send=False, mailer=None):
    """Send ``snapshot`` only when ``send`` is true and delivery is allowed.

    ``send=False`` is the dry run: the HTML and recipient list are returned
    and the mailer is not called.
    """
    recipients = list(snapshot.get("recipients") or [])
    result = {
        "sent": False,
        "dry_run": True,
        "recipients": recipients,
        "html": snapshot.get("html") or "",
        "subject": snapshot.get("subject") or "",
        "family_id": snapshot.get("family_id"),
        "lang": snapshot.get("lang"),
        "reason": "dry_run",
    }
    if not send:
        return result
    if sending_is_blocked():
        result["reason"] = "blocked"
        return result
    if not recipients:
        result["reason"] = "no_recipients"
        return result
    sender = mailer or default_mailer
    try:
        ok = bool(sender(recipients, result["subject"], result["html"]))
    except Exception:
        ok = False
    result["sent"] = ok
    result["dry_run"] = False
    result["reason"] = "sent" if ok else "failed"
    return result
