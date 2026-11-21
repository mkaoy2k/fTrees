# FamilyTrees (`fTrees`)

## Introduction

FamilyTrees (`fTrees`) is a web application, written in Python, that lets you record your family tree and connect it with other family trees. The personal edition (`ftpe.py`) is retired. Its fictional sample tree and CSV template are kept in `archive/personal-edition/`.

## How It Works

`fTrees` stores members, relationships, and accounts in a local SQLite database. Family members can add and update records, then query them as tables or as an interactive graph. The three-generation graph is HTML embedded in the page. Each generation is one row, top to bottom, and the page does not export a PNG or SVG.

1. _Sharing_: several people can maintain parts of the same tree and keep one shared database.

2. _Languages_: the catalogs in `L10N.json` are 繁中, 简中, 日本語, 한국어, Danish, German, French, Lithuanian, Polish, Spanish, and US. To add another language, add a catalog file and a line in `L10N.json`. Questions can go to [Michael Kao](mailto:mkaoy2k@gmail.com).

The application is licensed under the MIT License. See `LICENSE`.

### System Requirements

- Python 3.12 or newer (CI runs 3.12; the container image is Python 3.13)
- SQLite 3 (included with Python)
- An SMTP account if you send password-reset or birthday mail

### Installation

1. **Clone this repository**

   ```bash
   git clone https://github.com/mkaoy2k/fTrees.git
   cd fTrees
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or
   .\.venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**

   Direct dependencies are declared in `pyproject.toml`. `requirements.txt` and `uv.lock` are the lockfile exported from that declaration. Pandas and Streamlit pull in numpy themselves. Graphs use `pyvis`.

   ```bash
   pip install -r requirements.txt
   ```

   With conda, the environment file installs Python 3.12 and the same lockfile:

   ```bash
   conda env create -f environment.yaml
   conda activate ftrees
   ```

   Refresh the lock after changing `pyproject.toml`:

   ```bash
   uv lock
   uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
   ```

4. **Configure environment variables**

   ```bash
   cp template.env.txt .env
   ```

   Edit `.env` for language, mail, and the admin account created by `genesis.py`. The database path defaults to `data/family.db`. Language names must match the keys in `L10N.json` (`Spanish`, `US`, `繁中`, and the others). Matching is case-insensitive.

5. **Create the data directory and the admin account**

   ```bash
   mkdir -p data
   python genesis.py
   ```

### Upgrading an existing database

Back up `data/family.db` before the first start after an upgrade. The first start migrates that file in place. `init_db()` rebuilds the member and relation tables to add foreign keys, turns references that do not point at a real row into NULL, removes orphaned password-reset tokens, and hashes leftover plaintext reset tokens. It also creates the `article` table when it is missing. If an older `article` table has no `family_id` column, the migration adds `family_id INTEGER DEFAULT 1` and backfills existing article rows with 1. Other tables and other columns are left as they are. It does not create a second database file. Copy the file aside first:

```bash
cp -a data/family.db data/family.db.bak
```

### Tests

```bash
pip install -r requirements.txt ruff
ruff check --select F,E
python -m unittest discover -s tests -t . -v
```

## Directory Structure

```text
fTrees/
├── .agents/              # Devin agent skills
├── .github/              # GitHub configuration
├── .streamlit/           # Streamlit configuration
│   └── config.toml       # Streamlit settings
├── archive/personal-edition/
│   ├── me.sample.csv     # Retired fictional sample tree
│   └── template.csv      # Retired CSV template
├── auth_utils.py         # Authentication utilities
├── bday.html             # Birthday email template
├── case_helpers.py       # Case-form helpers
├── context_utils.py      # Context management
├── data/                 # Local data (mostly untracked)
│   └── family.db         # Local database (not in git)
├── db_articles.py        # Article records, scoped by family_id
├── db_connection.py      # Database connection management
├── db_exchange.py        # Data import/export
├── db_families.py        # Family database operations
├── db_members.py         # Member database operations
├── db_relations.py      # Relationship database operations
├── db_schema.py          # Database schema definitions
├── db_users.py           # User database operations
├── db_utils.py           # Database facade
├── Dockerfile            # Container image
├── editor_paths.py       # CSV/JSON editor path checks
├── email_utils.py        # Email functionality
├── environment.yaml      # Conda env (uses the lockfile)
├── fTrees.py             # Main Streamlit app
├── funcUtils.py          # Utility functions
├── genesis.py            # Create the admin account
├── graph_text.py         # Graph text utilities
├── L10N.json             # Localization catalog index
├── L10N_CN.json          # Simplified Chinese catalog
├── L10N_DE.json          # German catalog
├── L10N_DK.json          # Danish catalog
├── L10N_ES.json          # Spanish catalog
├── L10N_FR.json          # French catalog
├── L10N_JP.json          # Japanese catalog
├── L10N_KR.json          # Korean catalog
├── L10N_LT.json          # Lithuanian catalog
├── L10N_PL.json          # Polish catalog
├── L10N_TW.json          # Traditional Chinese catalog
├── L10N_US.json          # US English catalog
├── LICENSE               # MIT License
├── nav.py                # Shared sidebar and role gate
├── newsletter_publish.py # Newsletter snapshot and subscriber updates
├── ops_artBatch.py       # Optional PyQt article editor (one family)
├── ops_svr.py            # Public journal server (waitress)
├── ops_dbMgmt.py         # Database management operations
├── ops_L10N.json         # Operations-server language index (繁中, 简中, US)
├── ops_L10N_CN.json      # Operations-server Simplified Chinese (简中, labelled CN)
├── ops_menu.json         # Operations-server menu
├── page_category.json    # Which article categories fill each public page
├── forms.py              # Feedback and contact forms
├── static/               # Operations-server CSS
├── templates/            # Operations-server pages and email bodies
├── pages/                # Multipage screens for fTrees.py
│   ├── 1_usrMgmt.py      # User management
│   ├── 2_famMgmt.py      # Family management
│   ├── 3_csv_editor.py   # CSV editor
│   ├── 4_json_editor.py  # JSON editor
│   ├── 5_artMgmt.py      # Article management (family and platform admin)
│   ├── 10_newsletter.py  # Newsletter (family and platform admin)
│   ├── 6_show_3G.py      # Three-generation graph
│   ├── 7_show_related.py # Relationship graph
│   ├── 8_caseMgmt.py     # Case management
│   └── 9_birthday.py     # Birthday notifications
├── pyproject.toml        # Direct dependencies
├── requirements.txt      # Locked dependencies
├── ruff.toml             # Ruff linting configuration
├── template.env.txt      # Environment template
├── tests/                # Unit tests
│   ├── __init__.py
│   ├── test_access.py    # Access control tests
│   ├── test_db_layer.py  # Database layer tests
│   ├── test_editor_paths.py # Editor path tests
│   ├── test_l10n.py      # Localization tests
│   ├── test_packaging.py # Packaging tests
│   ├── test_password_auth.py # Password authentication tests
│   ├── test_family_subscribe_smoke.py # Subscribe gate and article family scope
│   ├── test_newsletter.py # Newsletter role, subscribers, and snapshot
│   └── test_regressions.py # Regression tests
└── uv.lock               # Lockfile
```

## How to Use

### Docker

Build the image from this repository, then run it:

```bash
docker build -t ftrees .
mkdir -p data
cp -a data/family.db data/family.db.bak  # if a database is already there
chown -R 1000:1000 data
docker run --name ftrees -d -p 8501:8501 \
  --env-file .env \
  -v "$PWD/data:/fts/data" \
  ftrees
```

The process listens on port 8501 without opening a browser (`--server.headless=true`). A health check requests `http://127.0.0.1:8501/_stcore/health`.

The image declares `VOLUME /fts/data` and runs as uid 1000 (`appuser`). The mounted directory has to be writable by that user. `chown 1000:1000` on the host directory before `docker run`. A Docker-managed named volume is created root-owned, so the app cannot write `family.db` there until that volume is chowned to uid 1000. Pass secrets with `--env-file` or `-e`. The image build ignores `.env` and local database files.

Open `http://localhost:8501`.

### Python

```bash
streamlit run fTrees.py
```

Streamlit serves the login page at `http://localhost:8501`.

### Article management

There is no `pages/5_*.py` collision in this tree (the numbers jump from 4 to 6), so article management is `pages/5_artMgmt.py`. Family admins and platform admins see it. Family members do not.

A family admin (`users.is_admin` = family admin) is limited to the `family_id` stored on that user at login. A platform admin sees every family's articles, with `family_id` on each row, and can filter to one family. Creating an article as a platform admin asks for the `family_id`. A family admin's new article uses their own id.

The optional desktop editor edits one family at a time. PyQt5 is not required for Streamlit or `ops_svr`:

```bash
pip install "PyQt5>=5.15.11"
python ops_artBatch.py --family-id 1
```

`uv sync --extra qt` installs the same optional extra.

### Operations server

`ops_svr.py` is the public family journal (home, FAQ, about, feedback, subscribe). It is a Flask app served by waitress. Pass the family this process serves:

```bash
python ops_svr.py --family_id 1
```

`--family_id` overrides `FAMILY_ID` in `.env`. The value must be an integer. If both are blank, or the value is not an integer, the process exits with a non-zero status and does not serve. `waitress-serve` does not read the flag, so set `FAMILY_ID` for that process. Content pages load only articles with that integer `family_id`. Feedback inserts and updates write that same id. A subscriber is a row in the shared `users` table whose `family_id` equals the server's family id. The address match is case-insensitive. Password reset uses the existing `password_reset_tokens` table.

```bash
python ops_svr.py --dev --family_id 1   # Flask debugger, not for production
```

The default listen address is `127.0.0.1:5566` (`OPS_SVR_HOST`, `OPS_SVR_PORT`). Language is chosen per request from the switcher. The catalog key for Simplified Chinese is `简中` (zh-CN), shown as CN. `繁中` is Traditional Chinese and `US` is English. A request for `CN` or `zh-CN` selects `简中`. Copy the new keys from `template.env.txt` into `.env` before starting the server. Do not commit `.env`.

### Newsletter

`pages/10_newsletter.py` is for platform admins (`users.is_admin` = 2) and family admins (`users.is_admin` = 1). Family members do not see it in the sidebar, and opening the page directly stops before it reads subscriber or article data. The family_id field sits above the language field. A platform admin can type any family_id. A family admin sees their own family_id and cannot change it.

Subscribers are rows in the shared `users` table. The page lists the rows for the selected family_id. Unsubscribe sets `is_active` to inactive and clears the token, which is the same update `ops_svr` applies after an unsubscribe is confirmed. Adding an address succeeds only when that address, compared without case after stripping whitespace, is already a user whose `family_id` equals the selected family. The row is marked active immediately. No confirmation mail is sent. The page does not insert a user and does not change `family_id`. An address that is not a member of that family shows an error in English and Traditional Chinese.

Publication previews the operations-server home page (`templates/home.html`) for the selected family_id and language. The preview uses the same article query as the public main page: approved articles in the article window for that `family_id`. English (`US`) and Traditional Chinese (`繁中`) also require `article.l10n` to match. Simplified Chinese (`简中`, labelled CN) shows a `繁中` article in that category when no `简中` article exists, then a `US` article. The newsletter language list shows CN for `简中`. Relative image and link URLs are rewritten to `OPS_SVR`, and `static/main.css` is inlined, because an email client does not resolve `/static/...` against the server. Nothing is sent until you preview and then choose send. Recipients are that family's active subscribers whose `l10n` equals the edition language. The subject line is the journal heading plus the family name and the family id. If the family row or its name is missing, the subject still includes the family id. Mail is not sent when `CI` or `GITHUB_ACTIONS` is set, or when `NEWSLETTER_DISABLE_SEND` is `1`. The sample `OPS_SVR` in `template.env.txt` is `http://127.0.0.1:5566`, the same address the listener uses by default (`OPS_SVR_HOST` `127.0.0.1`, `OPS_SVR_PORT` `5566`). If `OPS_SVR` is unset, newsletter links use that listener address (a wildcard host is written as `127.0.0.1`).

`/pub` on the operations server uses that same snapshot. `dry_run=1` (or `preview=1`) returns the HTML and does not send. A family admin is locked to their own family_id. A platform admin may pass `family_id`.

The three-generation page and the relationship page draw interactive HTML in the page using `st.iframe` with pyvis graphs. Names in the hover text are escaped. The three-generation graph and the relationship graph each place a generation on its own row, smaller generation numbers above larger ones. There is no PNG or SVG download. Relationship edges stay gray and are labeled with the relation type.

The retired personal-edition sample and CSV template are in `archive/personal-edition/`. A `data/me.csv` left on a machine is not read by this app and is not committed.

Created by [Michael Kao](https://github.com/mkaoy2k/fTrees).
