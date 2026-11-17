"""
FamilyTrees Operations Server

This module provides admin services for a specific family, 
identified by the family's unique identifier, on the FamilyTrees Platform. 
The services include:
- Main page
- Frequently Asked Questions (FAQ)
- About page
- Feedback page

Main Features:
- Publish periodical journal about family news, strories, and events
- Solicitate family members to contribute to the journal
- Support Family member subscription
  - Allow users to subscribe and unsubscribe from family updates
  - Applicant will be validated by email and must be a family member
  - Only family members can subscribe
  - To subscibe if not a family member yet, the user needs to contact 
  the corresponding family Admin to register their email address and 
  personal information in the family database first.
- All the pages are supported with multi-language support (L10N)

Production (default) — waitress, Flask debug off:
    python ops_svr.py --family_id <family_id>

Development — Flask's built-in server, debugger, and reloader:
    python ops_svr.py --dev --family_id <family_id>
    OPS_DEV=1 python ops_svr.py --family_id <family_id>

`--family_id` overrides the FAMILY_ID environment variable. If both are
missing or blank, the process exits at import and does not serve. That
covers `python ops_svr.py` and the `ops_svr:app` callable used by
waitress-serve and gunicorn. Those WSGI servers do not parse
`--family_id`; set FAMILY_ID for them.

A member record is the `users` row for that email. Membership means the row's
family_id equals the family id this process was started with. Email
comparison in the subscribe, confirm, and feedback flow is case-insensitive.
Article pages and feedback writes use that same family id.

The module-level Flask callable for an external WSGI server is `app`
(for example `ops_svr:app`). Do not use `flask run` in production;
that command is Flask's development server.

The active language, menu, and page strings are request-local (`flask.g`,
set by `bind_request_locale`). Shared catalogs stay module-level and are
swapped as a whole. `OPS_SVR_THREADS` may be raised above 1 without mixing
languages across overlapping requests. The default remains 1.
"""

from flask import Flask, request, redirect, render_template, flash, url_for, session, jsonify, g
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from flask_mail import Mail
import argparse
import os
import sys
import threading
import email_utils as eu
import auth_utils as au
import db_utils as dbm
from funcUtils import load_menu, load_ops_L10N, load_page_cat
import logging
from dotenv import load_dotenv

# Shared catalogs and process config. These are not the active request
# language. A request copies one language onto flask.g in bind_request_locale.
g_L10N = {}
g_L10N_options = []
g_MENU = {}
g_PAGE = {}
g_PAGE_CAT = {}
g_default_loc_key = None
backend = None
ft_svr = None
git_ftpe = None
git_subs = None

# Held only while publishing a new catalog snapshot, not during database reads.
_catalog_lock = threading.Lock()

# Language choice for the browser. This is not the Secure session cookie:
# SESSION_COOKIE_SECURE is on, so browsers drop that cookie on the default
# http://127.0.0.1 listener. A language code is not a credential.
LANG_COOKIE = "current_lang"
LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Load environment variables
load_dotenv(".env")

# Configure logging
log = logging.getLogger(__name__)
log_level = os.getenv('LOGGING', 'WARNING').upper()
log.setLevel(getattr(logging, log_level, logging.WARNING))

# Remove existing handlers to avoid duplication
log.handlers = []

# Configure console handler format
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
formatter = logging.Formatter('%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add handler to logger
log.addHandler(console_handler)

# Prevent propagation to root logger
log.propagate = False

# Add after Flask app initialization
app = Flask(__name__, template_folder='templates')
# Configure Flask app
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour CSRF token expiration
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookies over HTTPS
app.config['REMEMBER_COOKIE_SECURE'] = True  # Only send remember cookies over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent client-side JS access to cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection for same-site requests

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Make CSRF token available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

# Configure Flask-Mail with SSL on port 465
app.config.update(
    # Keep existing mail configuration unchanged
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=465,
    MAIL_USE_TLS=False,
    MAIL_USE_SSL=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', 'mkaoy2k@gmail.com'),
    MAIL_DEBUG=0,
    MAIL_SUPPRESS_SEND=False
)

# Initialize Flask-Mail
g_fmail = Mail(app)

# Test email configuration
log.info(f"Email server configured: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
log.info(f"Using TLS: {app.config['MAIL_USE_TLS']}, Using SSL: {app.config['MAIL_USE_SSL']}")

def _load_page_content(page_cat, options, article_window):
    """Build per-language page content for this server's family only."""
    family_id = active_family_id()
    pages = {}
    for idx, loc in enumerate(options):
        l_page = {}

        l_home = {}
        for cat in page_cat['home']:
            articles = dbm.get_articles_byDays(cat, byDays=article_window, family_id=family_id)
            if articles:
                log.debug(f"Found {len(articles)} articles in category '{cat}' from last {article_window} days")
                l_home[cat] = []
                for article in articles:
                    if article['l10n'] == loc:
                        l_home[cat].append(article)
            else:
                log.debug(f"No articles found in category '{cat}' from last {article_window} days")
        l_page['home'] = l_home

        l_faq = {}
        for cat in page_cat['faq']:
            articles = dbm.get_articles(cat, family_id=family_id)
            if articles:
                log.debug(f"Found {len(articles)} articles in category '{cat}'")
                l_faq[cat] = []
                for article in articles:
                    if article['l10n'] == loc:
                        l_faq[cat].append(article)
            else:
                log.debug(f"No articles found in category '{cat}'")
        l_page['faq'] = l_faq

        l_about = {}
        for cat in page_cat['about']:
            articles = dbm.get_articles(cat, family_id=family_id)
            if articles:
                log.debug(f"Found {len(articles)} articles in category '{cat}'")
                l_about[cat] = []
                for article in articles:
                    if article['l10n'] == loc:
                        l_about[cat].append(article)
            else:
                log.debug(f"No articles found in category '{cat}'")
        l_page['about'] = l_about

        pages[idx] = l_page
    return pages


def init_globals():
    """
    Reload shared catalogs and process config.

    Builds the new catalogs first, then swaps them in under a lock so a
    request never observes a half-updated language table. Does not select
    the active request language; that lives on flask.g.
    """
    global g_L10N, g_L10N_options, g_MENU, g_PAGE, g_PAGE_CAT, g_default_loc_key
    global backend, ft_svr, git_ftpe, git_subs

    dbm.init_db()

    new_backend = os.getenv("DB_SVR", "sqlite3")
    log.debug(f"DB_SVR import: {new_backend}")

    new_ft_svr = os.getenv("FT_SVR", "https://crappie-on-kingfish.ngrok-free.app")
    log.debug(f"FamilyTreesPE Server: {new_ft_svr}")
    new_git_ftpe = os.getenv("GIT_FTPE", "https://github.com/mkaoy2k/ftpe.git")
    log.debug(f"ftpe GitHub Server: {new_git_ftpe}")
    new_git_subs = os.getenv("GIT_SUBS", "https://github.com/mkaoy2k/subs.git")
    log.debug(f"subs GitHub Server: {new_git_subs}")

    new_l10n = load_ops_L10N()
    new_options = list(new_l10n.keys())

    new_default = os.getenv("L10N") or "US"
    if new_default not in new_l10n:
        log.warning(
            "L10N=%r is not in the operations catalogs %s; using US",
            new_default,
            new_options,
        )
        new_default = "US" if "US" in new_l10n else new_options[0]
    log.debug(f"Default L10N='{new_default}'...")

    article_window = int(os.getenv("ARTICLE_WINDOW", "7"))
    log.debug(f"ARTICLE_WINDOW: {article_window}")

    f_menu = os.getenv("OPS_MENU_FILE", "ops_menu.json")
    new_menu = load_menu(f_menu)
    if new_default not in new_menu:
        raise KeyError(f"L10N={new_default!r} is missing from menu file {f_menu}")

    f_page_cat = os.getenv("OPS_PAGE_CAT", "page_category.json")
    new_page_cat = load_page_cat(f_page_cat)
    log.debug(f"Page categories: {new_page_cat}")

    new_page = _load_page_content(new_page_cat, new_options, article_window)

    with _catalog_lock:
        backend = new_backend
        ft_svr = new_ft_svr
        git_ftpe = new_git_ftpe
        git_subs = new_git_subs
        g_L10N = new_l10n
        g_L10N_options = new_options
        g_default_loc_key = new_default
        g_MENU = new_menu
        g_PAGE_CAT = new_page_cat
        g_PAGE = new_page


def catalog_snapshot():
    """Return the current shared catalogs as one consistent set of references."""
    with _catalog_lock:
        return g_default_loc_key, g_L10N, g_L10N_options, g_MENU, g_PAGE


def bind_request_locale(lang):
    """
    Copy one language's strings onto flask.g for this request only.

    Each request has its own g, so overlapping requests cannot observe
    each other's language, menu, or page strings.
    """
    default_key, l10n, options, menu_all, pages = catalog_snapshot()
    if lang not in options:
        lang = default_key
    g.loc_key = lang
    g.loc = l10n[lang]
    g.menu = menu_all[lang]
    g.options = options
    page = pages[options.index(lang)]
    g.home = page['home']
    g.faq = page['faq']
    g.about = page['about']


def remember_request_lang(lang):
    """Keep lang on this request's session and on the response cookie."""
    session['current_lang'] = lang
    g.lang_cookie = lang


def get_template_context():
    """Return template context for all view functions"""
    return {
        'menu': g.menu,
        'options': g.options,
        'release': os.getenv("RELEASE", ""),
        'settings': g.loc['SETTINGS'],
        'admin': g.loc['HOME_HTML_T4_TEAM'],
        'admin_email': os.getenv("DB_ADMIN", ""),
        'office_days': os.getenv("OFFICE_DAYS", "Monday - Friday"),
        'office_hours': os.getenv("OFFICE_HOURS", "9:00 AM - 5:00 PM (PST)"),
        'mailing_address': os.getenv("MAILING_ADDRESS", ""),
        'mailing_city': os.getenv("MAILING_CITY", ""),
        'mailing_country': os.getenv("MAILING_COUNTRY", ""),
        'your_language': g.loc['YOUR_LANGUAGE'],
        'subscribe': g.loc['SUBSCRIBE'],
        'unsubscribe': g.loc['UNSUBSCRIBE'],
        'email_subscription': g.loc['EMAIL_SUBSCRIPTION'],
        'motto_btn': g.loc['HOME_HTML_H2'],
        'motto': g.loc['HOME_HTML_MOTTO'],
        'ops_svr': os.getenv("OPS_SVR", "http://localhost:5566"),
        'current_lang': g.loc_key
    }

@app.before_request
def before_request():
    """Bind this request's language from the cookie or session onto flask.g."""
    default_key, _l10n, options, _menu_all, _pages = catalog_snapshot()
    # The cookie is what a browser on plain HTTP actually sends back.
    lang = request.cookies.get(LANG_COOKIE) or session.get('current_lang')
    if lang not in options:
        lang = default_key
    try:
        bind_request_locale(lang)
    except Exception as e:
        log.error(f"Language switch error: {str(e)}")
        bind_request_locale(default_key)
    if session.get('current_lang') != g.loc_key or request.cookies.get(LANG_COOKIE) != g.loc_key:
        remember_request_lang(g.loc_key)


@app.after_request
def persist_language_cookie(response):
    """Send the language cookie when this request selected or corrected it."""
    lang = getattr(g, 'lang_cookie', None)
    if not lang:
        return response
    response.set_cookie(
        LANG_COOKIE,
        lang,
        max_age=LANG_COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=False,
        path='/',
    )
    return response
 
@app.route("/")
def home():
    """Home page"""
    context = get_template_context()
    t1 = g.loc['HOME_HTML_T1']
    t2 = g.loc['HOME_HTML_T2']
    t3 = g.loc['HOME_HTML_T3']
    
    # Check if Story has content, if not use default values
    story_data = {
        't2_title': g.loc['HOME_HTML_NO_STORY_TITLE'],
        't2_content': g.loc['HOME_HTML_NO_STORY_CONTENT'],
        't2_image': '',
        't2_image_alt': '',
        't2_author': '',
        't2_src_url': '',
        't2_source': ''
    }
    
    try:
        if g.home["Story"] and len(g.home["Story"]) > 0:
            story_data = {
                't2_title': g.home["Story"][0].get('title', g.loc['HOME_HTML_NO_STORY_TITLE']),
                't2_content': g.home["Story"][0].get('content', g.loc['HOME_HTML_NO_STORY_CONTENT']),
                't2_image': g.home["Story"][0].get('image_url', ''),
                't2_image_alt': g.home["Story"][0].get('image_alt', ''),
                't2_author': g.home["Story"][0].get('author', ''),
                't2_src_url': g.home["Story"][0].get('src_url', ''),
                't2_source': g.home["Story"][0].get('source', '')
            }
    
    except Exception as e:
        log.warning(f"Skip processing story: {str(e)}")
    
    context.update({
        'release': os.getenv("RELEASE", ""),
        'header': g.loc['HOME_HTML_H1'],
        't1': t1,
        't1_articles': g.home.get("News") or [
            {
                'title': g.loc.get('HOME_HTML_NO_NEWS_TITLE', 'No News Available'),
                'content': g.loc.get('HOME_HTML_NO_NEWS_CONTENT', 'Check back later for updates.')
            }
        ],
        'author_label': g.loc['HTML_AUTHOR_LABEL'],
        'source_label': g.loc['HTML_SOURCE_LABEL'],
        't2': t2,
        't2_title': story_data['t2_title'],
        't2_content': story_data['t2_content'],
        't2_image': story_data['t2_image'],
        't2_image_alt': story_data['t2_image_alt'],
        't2_author': story_data['t2_author'],
        't2_src_url': story_data['t2_src_url'],
        't2_source': story_data['t2_source'],
        't3': t3,
        't3_article': g.home.get("Events") or [
            {
                'title': g.loc.get('HOME_HTML_NO_EVENT_TITLE', 'No Events Available'),
                'content': g.loc.get('HOME_HTML_NO_EVENT_CONTENT', 'Check back later for updates.')
            }
        ],
        't4_greeting': g.loc['HOME_HTML_T4_GREETING'],
        't4_team': g.loc['HOME_HTML_T4_TEAM'],
        'ft_url': ft_svr,
        'title': 'home'
    })
    return render_template('home.html', **context)

@app.route("/faq")
def faq():
    """FAQ page"""
    
    context = get_template_context()
    
    # Get the articles for the current language's FAQ category
    faq_articles = g.faq['FAQ']
    
    context.update({
        'release': os.getenv("RELEASE", ""),
        'header': g.loc['FAQ_HTML_H1'],
        'questions': [article['title'] for article in faq_articles],
        'answers': [article['content'] for article in faq_articles],
        'authors': [article['author'] for article in faq_articles],
        'images': [article['src_url'] for article in faq_articles],
        'ft_url': ft_svr,
        'title': 'faq'
    })
    return render_template('faq.html', **context)

@app.route("/about")
def about():
    """About page"""
    
    context = get_template_context()
    body = [None, None]
    log.debug(f"Processing about page content. Found {len(g.about['About'])} articles")
    
    # Log all article titles for debugging
    for article in g.about['About']:
        log.debug(f"Article title: '{article['title']}' (length: {len(article['content'])} chars)")
    
    # Match articles to expected sections
    for article in g.about['About']:
        if article['title'] == g.loc['ABOUT_INTRODUCTION_H2']:
            body[0] = article['content']
            log.debug(f"Found introduction article. Content length: {len(body[0])} chars")
        elif article['title'] == g.loc['ABOUT_REPOSITORY_H2']:
            body[1] = article['content']
            log.debug(f"Found repository article. Content length: {len(body[1])} chars")
    context.update({
        'release': os.getenv("RELEASE", ""),
        'header': g.loc['ABOUT_HTML_H1'],
        'introduction': g.loc['ABOUT_INTRODUCTION_H2'],
        'repository': g.loc['ABOUT_REPOSITORY_H2'],
        'body': body,
        'git_ftpe': git_ftpe,
        'git_subs': git_subs,
        'title': 'about'
    })
    return render_template('about.html', **context)

@app.route("/privacy")
def privacy():
    """Privacy Policy page"""
    
    context = get_template_context()
    context.update({
        'release': os.getenv("RELEASE", ""),
        'header': g.loc.get('PRIVACY_HEADER', 'Privacy Policy'),
        'title': 'privacy',
        'admin': context['admin'],
        'admin_email': context['admin_email'],
        'last_updated': '2024-06-26'
    })
    return render_template('privacy.html', **context)

@app.route("/terms")
def terms():
    """Terms of Service page"""
    
    context = get_template_context()
    context.update({
        'release': os.getenv("RELEASE", ""),
        'header': g.loc.get('TERMS_HEADER', 'Terms of Service'),
        'title': 'terms',
        'admin': context['admin'],
        'admin_email': context['admin_email'],
        'last_updated': '2024-06-26'
    })
    return render_template('terms.html', **context)

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    from forms import ContactForm
    
    """Contact Us page"""
    
    context = get_template_context()
    message_sent = False
    form = ContactForm()
    
    if form.validate_on_submit():
        # Get form data
        form_data = {
            'name': form.name.data.strip(),
            'email': form.email.data.strip(),
            'subject': form.subject.data.strip(),
            'message': form.message.data.strip()
        }
        
        # Check if user exists, if not create a new user
        user = dbm.get_subscriber(form_data['email'])
        if not user:
            user_id = dbm.create_user(form_data['email'], dbm.Subscriber_State['in_contact'], lang=context['current_lang'])
            if not user_id:
                flash(g.loc.get('ADD_CONTACT_ERROR', 'Contact not created/updated. Please try again later.'), 'danger')
                return redirect(url_for('contact'))
        else:
            user_id = user['id']
        # Save the form data to database
        article_data = {
            'title': form_data['subject'],
            'content': form_data['message'],
            'category': dbm.Article_Categories['contact'],
            'author': form_data['name'],
            'source': form_data['email'],
            'src_url': '',
            'image_url': '',
            'l10n': context['current_lang'],
            'user_id': user_id,
            'family_id': active_family_id(),
        }
        article_id = dbm.add_or_update_article(article_data, 
                                        update=True)
            
        if article_id:
            log.info(f"Created contact form article successfully withID: {article_id}")
            # Send email to admin
            to_emails = [context.get('admin_email')]
            subject = f"New Contact Article: {article_id}"
            html = f"""
            <p>Subject: {form_data['subject']}</p>
            <p>Content: {form_data['message']}</p>
            <p>Author: {form_data['name']}</p>
            <p>Source: {form_data['email']}</p>
            """
            if eu.send_email(g_fmail, to_emails, subject, html):
                log.info(f"Successfully sent contact email to {to_emails}")
            else:
                log.error(f"Failed to send contact email to {to_emails}")
            message_sent = True
            flash(g.loc.get('CONTACT_SUCCESS', 'Your contact request has been sent. We will get back to you soon!'), 'success')
            return redirect(url_for('contact'))
        else:
            log.error("Failed to create contact form article")
            flash(g.loc.get('CONTACT_ERROR', 'Failed to send contact request. Please try again later.'), 'danger')
    
    # Initialize form_data with empty values if not set
    if 'form_data' not in locals():
        form_data = {
            'name': '',
            'email': '',
            'subject': '',
            'message': ''
        }
    
    # Add form data to context
    context.update({
        'form': form,
        'release': os.getenv("RELEASE", ""),
        'header': g.loc.get('CONTACT_HEADER', 'Contact Us'),
        'title': 'contact',
        'admin': context['admin'],
        'admin_email': context['admin_email'],
        'office_days': context['office_days'],
        'office_hours': context['office_hours'],
        'mailing_address': context['mailing_address'],
        'mailing_city': context['mailing_city'],
        'mailing_country': context['mailing_country'],
        'message_sent': message_sent,
        'form_labels': {
            'name': g.loc.get('CONTACT_NAME', 'Your Name'),
            'email': g.loc.get('CONTACT_EMAIL', 'Email Address'),
            'subject': g.loc.get('CONTACT_SUBJECT', 'Subject'),
            'message': g.loc.get('CONTACT_MESSAGE', 'Your Message'),
            'submit': g.loc.get('CONTACT_SUBMIT', 'Send Message')
        }
    })
    return render_template('contact.html', **context)

@app.route("/feedback", methods=['GET', 'POST'])
def feedback():
    """
    Feedback page for article submission
    """
    from forms import ArticleForm
    from werkzeug.datastructures import MultiDict
    
    context = get_template_context()
    lang = session.get('current_lang', 'US')
    
    # Initialize form based on request method
    if request.method == 'POST':
        log.debug(f"Form data received: {request.form}")
        submitted = MultiDict(request.form)
        normalized_email = dbm.normalize_subscriber_email(submitted.get("email"))
        if normalized_email:
            submitted["email"] = normalized_email

        # Create form with data from request using formdata
        form = ArticleForm(formdata=submitted, meta={'csrf': True}, lang=lang)
        
        # Manually populate the form data
        for field in form:
            if field.name in submitted:
                field.data = submitted[field.name]
        
        # Log form data before validation
        log.debug(f"Form data before validation: {form.data}")
        log.debug(f"Request form data: {dict(request.form)}")
        
        # Process the form data if validation passes
        if form.validate():
            log.debug("Form validation passed")
            log.debug(f"Form data after validation: {form.data}")
            
            # Process the form data
            title = form.title.data
            content = form.content.data
            l10n = form.l10n.data
            author = form.author.data
            source = form.source.data
            src_url = form.source_url.data or None
            image_url = form.image_url.data or None
            email = dbm.normalize_subscriber_email(form.email.data)
            
            # Validate email format. Membership uses the same lowered address.
            if not email or not eu.validate_email(email):
                log.warning(f"Invalid email address: {form.email.data}")
                flash(f'{g.loc.get("EMAIL_INVALID", "Invalid email address")}', 'danger')
            elif not dbm.is_family_member(email, active_family_id()):
                # Same page message as subscribe. No user row is created.
                log.info(
                    "Feedback request is not a member of this family; "
                    "sending registration instructions"
                )
                admin_email = os.getenv("DB_ADMIN", "")
                if eu.send_membership_instruction_email(
                    g_fmail, email, admin_email=admin_email
                ):
                    _flash_subscription_next_step(email)
                else:
                    _flash_subscription_send_failed()
            else:
                subscriber = dbm.get_subscriber(email)
                if not subscriber or subscriber.get('is_active') != dbm.Subscriber_State['active']:
                    # A member who is not an active subscriber sees the same
                    # page message as a non-member. The letter is the
                    # verification mail, and no article is stored.
                    log.info("Family member must confirm subscription before submitting feedback")
                    _start_subscription(email)
                else:
                    # Only proceed with article creation if all validations pass
                    try:
                        # Create the article in the database
                        article_data = {
                            'title': title,
                            'content': content,
                            'category': dbm.Article_Categories['feedback'],
                            'author': author,
                            'source': source,
                            'src_url': src_url,
                            'image_url': image_url,
                            'user_id': subscriber['id'],
                            'l10n': l10n,
                            'family_id': active_family_id(),
                        }
                        
                        article_id = dbm.add_or_update_article(article_data, 
                                        update=True)
                        
                        if article_id:
                            log.debug(f"Successfully created article with ID: {article_id}")
                            
                            # Send email to admin
                            to_emails = [context.get('admin_email')]
                            subject = f"New Feedback Article: {article_id}"
                            html = f"""
                            <p>Subject: {title}</p>
                            <p>Content: {content}</p>
                            <p>Author: {author}</p>
                            <p>Source: {source}</p>
                            <p>Source URL: {src_url}</p>
                            <p>Image URL: {image_url}</p>
                            """
                            if eu.send_email(g_fmail, 
                                to_emails, 
                                subject, html):
                                log.info(f"Successfully sent feedback email to {to_emails}")
                            else:
                                log.error(f"Failed to send feedback email to {to_emails}")
                            
                            flash(f'Ticket:{article_id}, {g.loc.get("FEEDBACK_SUCCESS", "Submitted successfully")}', 'success')
                            # Redirect to home page after successful submission
                            return redirect(url_for('home'))
                        else:
                            log.error("Failed to create article in database")
                            flash(f'{g.loc.get("FEEDBACK_RETRY", "Article not created. Please try again later.")}', 'danger')
                    except Exception as e:
                        log.error(f"Error creating article: {str(e)}")
                        flash(f'{g.loc.get("FEEDBACK_ERROR", "An error occurred. Please try again.")}', 'danger')
        else:
            log.warning(f"Form validation failed: {form.errors}")
            # Log each field's error for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    log.warning(f"Field '{field}': {error}")
    else:
        # Initialize empty form for GET request
        form = ArticleForm(meta={'csrf': True}, lang=lang)
    
    # Update context with form data
    context.update({
        'header': g.loc.get('FEEDBACK_HTML_H1', 'Submit Feedback'),
        'title': 'feedback',
        'form': form,
    })
    
    # Log form state before rendering
    log.debug(f"Form data before render: {form.data}")
    log.debug(f"Form errors before render: {form.errors}")
    log.debug(f"Form is bound: {form.is_submitted()}")
    log.debug(f"Form validate on submit: {form.validate_on_submit()}")
    log.debug(f"CSRF Token: {form.csrf_token.current_token if hasattr(form, 'csrf_token') else 'No CSRF token'}")
    
    # Debug: Log all form fields and their data
    log.debug("=== Form Field Values ===")
    for field_name, field in form._fields.items():
        log.debug(f"Field: {field_name}, Type: {type(field).__name__}, Data: {field.data}, Raw Data: {field.raw_data}, Errors: {field.errors}")
    log.debug("=======================")
    
    return render_template('feedback.html', **context)

@app.route("/setL10N")
def set_l10n():
    """
    Set up language localization (L10N) routing
    """
    # Get language and page from URL parameters
    lang = request.args.get('lang')
    page = request.args.get('page', 'home')

    if lang in g_L10N_options:
        try:
            # Refresh shared catalogs, then remember the choice on this session.
            # The next request binds it onto flask.g. Nothing here is process-wide.
            init_globals()
            if lang not in g_L10N_options:
                raise KeyError(lang)
            bind_request_locale(lang)
            remember_request_lang(g.loc_key)
        except Exception as e:
            log.error(f"Language switch error: {str(e)}")
    
    # Redirect to target page
    if page == "feedback":
        return redirect(url_for('feedback'))
    elif page == "about":
        return redirect(url_for('about'))
    elif page == "faq":
        return redirect(url_for('faq'))
    return redirect(url_for('home'))

@app.route('/subscribe', methods=['POST'])
# 前端表單中必須包含: <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
def subscribe():
    """
    Handle email subscription/unsubscription request
    
    Returns:
        Response: Redirect back to previous page and display operation result
    """
    
    # CSRF protection is automatically handled by Flask-WTF
    
    raw_email = request.form.get('email')
    email = dbm.normalize_subscriber_email(raw_email)
    action = request.form.get('action')
    
    if not email or not eu.validate_email(email):
        shown = email or raw_email
        flash(f'{shown} is not a valid email address', 'danger')
        return redirect(request.referrer or url_for('home'))
    
    try:
        if action == 'subscribe':
            family_id = active_family_id()
            # Unknown addresses and members of another family take the same
            # branch and the same page message. Only the letter differs.
            if not dbm.is_family_member(email, family_id):
                log.info(
                    "Subscription request is not a member of this family; "
                    "sending registration instructions"
                )
                admin_email = os.getenv("DB_ADMIN", "")
                if eu.send_membership_instruction_email(
                    g_fmail, email, admin_email=admin_email
                ):
                    _flash_subscription_next_step(email)
                else:
                    _flash_subscription_send_failed()
            else:
                _start_subscription(email)
        else:
            # For unsubscribing, we can send a verification email or unsubscribe directly
            # For security, we send a verification email here
            token = eu.generate_verification_token()
            if eu.send_verification_email(g_fmail, email, token, is_subscribe=False):
                flash(f'Please check {email} to confirm unsubscription.', 'info')
            else:
                flash('Failed to send verification email. Please try again later.', 'danger')
                
    except Exception as e:
        log.error(f"Error processing subscription: {str(e)}")
        flash('An error occurred. Please try again later.', 'danger')
    
    return redirect(request.referrer or url_for('home'))

@app.route('/verify-email')
def verify_email():
    """
    Verify email subscription/unsubscription
    """
    
    email = dbm.normalize_subscriber_email(request.args.get('email'))
    token = request.args.get('token')
    action = request.args.get('action')
    
    if not all([email, token, action]):
        log.debug(f"Invalid verification link: {email}, {token}, {action}")
        flash('Invalid verification link', 'danger')
        return redirect(url_for('home'))
    
    # Verify token
    if not dbm.verify_subscription_token(email, token):
        log.debug(f"Invalid or expired verification link: {email}, {token}, {action}")
        flash('Invalid or expired verification link', 'danger')
        return redirect(url_for('home'))
    
    # Handle subscription/unsubscription
    if action == 'subscribe':
        family_id = active_family_id()
        if not family_id or not dbm.is_family_member(email, family_id):
            # The link already proved they can read the mailbox. Do not
            # activate, and do not clear the token, so an admin can register
            # the address and the same link can be used again.
            log.info("Verification refused because the address is not a member of this family")
            flash(
                g.loc.get(
                    "SUB_VERIFY_BLOCKED",
                    "This subscription could not be completed. Please contact the family Admin to register, then try again.",
                ),
                "danger",
            )
            return redirect(url_for('home'))
        user_data = {
            'email': email,
            'is_active': dbm.Subscriber_State['active'],
            'token': token,
            'l10n': g.loc_key
        }
        if dbm.add_or_update_subscriber(user_data):
            log.debug(f"Subscribed {email} with lang={g.loc_key}")
            flash(f'{email} has been successfully subscribed to our newsletter!', 'success')
        else:
            flash(f'Failed to subscribe {email}. Please try again later.', 'danger')
    else:
        dbm.remove_subscriber(email)
        flash(f'{email} has been unsubscribed from our newsletter.', 'info')
    
    return redirect(url_for('home'))

# ---- Admin tools below ----

@app.route('/pub')
def pub_newsletter():
    """
    retrieve active subscribers' emails from db and send newsletter
    """
    lang = request.args.get('lang', g.loc_key)
    email = request.args.get('email')
    password = request.args.get('password')

    if lang not in g_L10N_options:
        log.debug(f"Language not found: {lang}")
        flash(f'{g.loc.get("PUB_HTML_FAILS", "Language not found")}', 'warning')
        return redirect(url_for('home'))

    # Check admin credentials. There is no separate login route on this server.
    if not au.verify_admin(email, password):
        log.debug("Login failed")
        flash(f'{g.loc.get("LOGIN", "login")} {g.loc.get("FAILED", "failed")}', 'warning')
        return redirect(url_for('home'))

    # Refresh shared catalogs, then bind this request (and this session)
    # to the newsletter language. Other requests keep their own flask.g.
    init_globals()
    if lang not in g_L10N_options:
        log.debug(f"Language not found after refresh: {lang}")
        flash(f'{g.loc.get("PUB_HTML_FAILS", "Language not found")}', 'warning')
        return redirect(url_for('home'))
    bind_request_locale(lang)
    remember_request_lang(g.loc_key)
    family_id = active_family_id()
    users = [
        user for user in (dbm.get_subscribers(state='active', lang=lang) or [])
        if dbm.is_family_member(user.get('email'), family_id)
    ]
    if not users:  # Handles both None and empty list
        log.debug(f"No active subscribers found for language: {lang}")
        flash(f'{g.loc.get("NO_ACTIVE_SUBSCRIBERS", "No active subscribers found")}', 'warning')
        return redirect(url_for('home'))
        
    emails = [user['email'] for user in users if user and 'email' in user]
    if not emails:  
        # In case all users in the list are invalid or missing email
        log.debug(f"No valid emails found for language: {lang}")
        flash(f'{g.loc.get("NO_EMAILS_FOUND", "No valid emails found")}', 'danger')
        return redirect(url_for('home'))

    context = get_template_context()
    t1 = g.loc['HOME_HTML_T1']
    t2 = g.loc['HOME_HTML_T2']
    t3 = g.loc['HOME_HTML_T3']
    
    # Prepare story data with safe defaults
    story_data = {
        't2_title': g.loc.get('HOME_HTML_NO_STORY_TITLE', 'Featured Story'),
        't2_content': g.loc.get('HOME_HTML_NO_STORY_CONTENT', 'No story content available'),
        't2_image': '',
        't2_image_alt': '',
        't2_author': '',
        't2_source': '',
        't2_src_url': ''
    }
    
    # Update story data if available
    if 'Story' in g.home and isinstance(g.home['Story'], list) and len(g.home['Story']) > 0:
        story = g.home['Story'][0]
        story_data.update({
            't2_title': story.get('title', story_data['t2_title']),
            't2_content': story.get('content', story_data['t2_content']),
            't2_image': story.get('image_url', ''),
            't2_image_alt': story.get('image_alt', ''),
            't2_author': story.get('author', ''),
            't2_source': story.get('source', ''),
            't2_src_url': story.get('src_url', '')
        })
    
    # Prepare context with safe dictionary access
    context.update({
        'header': g.loc.get('HOME_HTML_H1', 'Newsletter'),
        'author_label': g.loc.get('HTML_AUTHOR_LABEL', 'Author'),
        'source_label': g.loc.get('HTML_SOURCE_LABEL', 'Source'),
        't1': t1,
        't1_articles': g.home.get('News', []),  # Default to empty list if 'News' key doesn't exist
        't2': t2,
        't2_title': story_data['t2_title'],
        't2_content': story_data['t2_content'],
        't2_image': story_data['t2_image'],
        't2_image_alt': story_data['t2_image_alt'],
        't2_author': story_data['t2_author'],
        't2_source': story_data['t2_source'],
        't2_src_url': story_data['t2_src_url'],
        't3': t3,
        't3_articles': g.home.get('Events', []),  # Default to empty list if 'Events' key doesn't exist
        't4_greeting': g.loc.get('HOME_HTML_T4_GREETING', 'Thank you for subscribing!'),
        't4_team': g.loc.get('HOME_HTML_T4_TEAM', 'The Team'),
        'ft_url': ft_svr,
        'ops_svr': os.getenv("OPS_SVR", "http://localhost:5566"),
        'title': g.loc.get('HOME_HTML_H1', 'Newsletter')
    })
    
    try:
        log.info(f"Attempting to send newsletter to {len(emails)} recipients in language: {lang}")
        log.debug(f"Context keys: {list(context.keys())}")
        
        # Log important context data for debugging
        if 't1_articles' in context:
            log.debug(f"Found {len(context['t1_articles'])} news articles")
        if 't3_articles' in context:
            log.debug(f"Found {len(context['t3_articles'])} event articles")
            
        # Send the newsletter
        if eu.send_newsletter(g_fmail, emails, context):
            success_msg = f"Newsletter sent successfully to {len(emails)} recipients in language: {lang}"
            log.info(success_msg)
            flash(g.loc.get("PUB_HTML_SUCCESS", "Newsletter sent successfully."), 'success')
        else:
            error_msg = f"Failed to send newsletter for language: {lang}. Check logs for details."
            log.error(error_msg)
            flash(g.loc.get("PUB_HTML_FAIL", "Failed to send newsletter. Please try again later."), 'danger')
            
    except Exception as e:
        error_msg = f"Unexpected error while sending newsletter for language {lang}: {str(e)}"
        log.error(error_msg, exc_info=True)
        flash(g.loc.get("PUB_HTML_FAIL", "An unexpected error occurred. Please contact support."), 'danger')
        
    return redirect(url_for('home'))    

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Handle password reset requests and form submission"""
    if request.method == 'GET':
        # Show the reset password form
        token = request.args.get('token')
        email = request.args.get('email')
        
        if not token or not email:
            flash('Invalid password reset link', 'error')
            return redirect(url_for('home'))
            
        # Verify the token against the password_reset_tokens table.
        if not _reset_token_matches(email, token):
            flash('The password reset link is invalid or has expired.', 'error')
            return redirect(url_for('home'))
            
        return render_template('reset_password.html', 
                             email=email, 
                             token=token,
                             **get_template_context())
    
    elif request.method == 'POST':
        # Process the password reset form
        email = request.form.get('email')
        token = request.form.get('token')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if not all([email, token, password, confirm_password]):
            flash('All fields are required', 'error')
            return redirect(request.url)
            
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(request.url)
            
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(request.url)
        
        # Verify the token again before allowing password reset
        if not _reset_token_matches(email, token):
            flash('The password reset link is invalid or has expired.', 'error')
            return redirect(url_for('home'))
        
        # Update the password through the family-tree account helper.
        if au.reset_password(email, password):
            flash('Your password has been reset successfully. Please log in with your new password.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Failed to reset password. Please try again.', 'error')
            return redirect(request.url)

# Handle CSRF errors
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({
        'error': 'Invalid CSRF token',
        'message': 'The form has expired. Please refresh the page and try again.'
    }), 400

def _env_truthy(name):
    """True when an environment flag is 1/true/yes/on."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


FAMILY_ID_REQUIRED = (
    "FamilyTreesOps requires a family id and will not start without one. "
    "Pass --family_id <family_id>, or set FAMILY_ID in the environment (.env). "
    "waitress-serve and gunicorn load ops_svr:app and do not read --family_id; "
    "set FAMILY_ID for those processes."
)


def active_family_id():
    """The family id this process was started with, or None if it is unset."""
    family_id = app.config.get("FAMILY_ID")
    if family_id is None:
        return None
    text = str(family_id).strip()
    return text or None


def cli_family_id(argv=None):
    """
    Read --family_id from argv.

    Used at import so `python ops_svr.py --family_id <id>` can satisfy the
    startup check before main() parses arguments. waitress-serve and gunicorn
    do not pass this flag through to the app.
    """
    if argv is None:
        argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--family_id" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--family_id="):
            return arg.split("=", 1)[1]
    return None


def configure_family_id(cli_value=None):
    """
    Choose the family this process serves.

    A non-blank --family_id wins. Otherwise FAMILY_ID from the environment
    (including .env) is used. When both are blank, raise SystemExit. The
    process does not serve with open subscription.
    """
    if cli_value is not None and str(cli_value).strip():
        chosen = str(cli_value).strip()
    else:
        chosen = os.getenv("FAMILY_ID", "").strip() or None
    app.config["FAMILY_ID"] = chosen
    if not chosen:
        log.error(FAMILY_ID_REQUIRED)
        raise SystemExit(FAMILY_ID_REQUIRED)
    log.info(f"Family subscription gate enabled for family_id={chosen}")
    return chosen


def build_parser():
    """Command-line parser for `python ops_svr.py`."""
    parser = argparse.ArgumentParser(description="FamilyTreesOps server")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run Flask's development server with the debugger and reloader. Not for production.",
    )
    parser.add_argument(
        "--family_id",
        default=None,
        help=(
            "Family this server serves. Required unless FAMILY_ID is set. "
            "Only user rows whose family_id equals this value may subscribe "
            "or submit feedback. Overrides FAMILY_ID."
        ),
    )
    return parser


def _reset_token_matches(email, token):
    """True when the reset token is live and belongs to this address."""
    ok, owner = au.validate_password_reset_token(token)
    if not ok or not owner or not email:
        return False
    return dbm.normalize_subscriber_email(owner) == dbm.normalize_subscriber_email(email)


def _flash_subscription_next_step(email):
    """One message for members and non-members, so the page does not reveal which."""
    template = g.loc.get(
        "SUB_CHECK_EMAIL",
        "Please check {email} for the next step.",
    )
    flash(template.replace("{email}", email), "info")


def _flash_subscription_send_failed():
    flash(
        g.loc.get(
            "SUB_EMAIL_SEND_FAILED",
            "Failed to send email. Please try again later.",
        ),
        "danger",
    )


def _start_subscription(email):
    """
    Send the existing verification mail and store the pending token.

    The address is the normalized form.     The update does not change
    users.family_id. The page message matches the non-member message.
    """
    token = eu.generate_verification_token()
    if not eu.send_verification_email(g_fmail, email, token, is_subscribe=True):
        _flash_subscription_send_failed()
        return

    user_data = {
        'email': email,
        'is_active': dbm.Subscriber_State['pending'],
        'token': token,
        'l10n': g.loc_key
    }
    if not dbm.add_or_update_subscriber(user_data):
        _flash_subscription_send_failed()
        return

    log.debug(f"Subscribed {email} with lang={g.loc_key}")
    _flash_subscription_next_step(email)


def server_settings():
    """
    Host, port, and waitress thread count.

    Defaults match the previous `app.run` behavior: localhost, port 5566,
    and one waitress thread. Active language is request-local, so
    OPS_SVR_THREADS may be raised (4 is a reasonable small-site setting)
    without mixing languages. The default stays 1 until the variable is set.
    """
    host = os.getenv("OPS_SVR_HOST", "127.0.0.1").strip() or "127.0.0.1"

    raw_port = os.getenv("OPS_SVR_PORT", "5566")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        log.warning(f"Invalid OPS_SVR_PORT={raw_port!r}; using 5566")
        port = 5566
    if port < 1 or port > 65535:
        log.warning(f"OPS_SVR_PORT {port} is out of range; using 5566")
        port = 5566

    raw_threads = os.getenv("OPS_SVR_THREADS", "1")
    try:
        threads = int(raw_threads)
    except (TypeError, ValueError):
        log.warning(f"Invalid OPS_SVR_THREADS={raw_threads!r}; using 1")
        threads = 1
    if threads < 1:
        log.warning(f"OPS_SVR_THREADS {threads} is below 1; using 1")
        threads = 1

    return host, port, threads


def main(argv=None):
    """
    Start FamilyTreesOps.

    The default path serves `app` with waitress (a production WSGI server)
    and does not enable Flask's debugger. Pass --dev, or set OPS_DEV, to
    run Flask's development server instead.
    """
    args = build_parser().parse_args(argv)
    configure_family_id(args.family_id)
    dev = args.dev or _env_truthy("OPS_DEV")
    host, port, threads = server_settings()

    if dev:
        log.warning(
            "Starting FamilyTreesOps development server "
            f"(Flask debugger) on http://{host}:{port}. Not for production."
        )
        # debug=True turns on the reloader and Werkzeug's development server.
        app.run(host=host, port=port, debug=True)
        return

    log.info(
        f"Starting FamilyTreesOps server (waitress) on http://{host}:{port} "
        f"(threads={threads})"
    )
    try:
        from waitress import serve
    except ImportError:
        log.error(
            "waitress is not installed. Install project dependencies and retry."
        )
        raise
    serve(app, host=host, port=port, threads=threads)

# Fail at import when neither --family_id nor FAMILY_ID is set, including
# waitress-serve and gunicorn, which load ops_svr:app and never call main().
# main() applies the parsed flag again. Request language is bound later.
configure_family_id(cli_family_id())
init_globals()

if __name__ == "__main__":
    main()
