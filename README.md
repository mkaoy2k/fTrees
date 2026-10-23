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

Back up `data/family.db` before the first start after an upgrade. The first start migrates that file in place. `init_db()` rebuilds the member and relation tables to add foreign keys, turns references that do not point at a real row into NULL, removes orphaned password-reset tokens, and hashes leftover plaintext reset tokens. It does not create a second database file. Copy the file aside first:

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
├── auth_utils.py         # Authentication utilities
├── case_helpers.py       # Case-form helpers
├── context_utils.py      # Context management
├── db_utils.py           # Database facade
├── Dockerfile            # Container image
├── editor_paths.py       # CSV/JSON editor path checks
├── email_utils.py        # Email functionality
├── environment.yaml      # Conda env (uses the lockfile)
├── archive/personal-edition/
│   ├── me.sample.csv     # Retired fictional sample tree
│   └── template.csv      # Retired CSV template
├── fTrees.py             # Main Streamlit app
├── funcUtils.py          # Utility functions
├── genesis.py            # Create the admin account
├── LICENSE               # MIT License
├── nav.py                # Shared sidebar and role gate
├── pyproject.toml        # Direct dependencies
├── requirements.txt      # Locked dependencies
├── uv.lock               # Lockfile
├── template.env.txt      # Environment template
├── bday.html             # Birthday template
├── data/                 # Local data (mostly untracked)
│   └── family.db         # Local database (not in git)
└── pages/                # Multipage screens for fTrees.py
    ├── 1_usrMgmt.py
    ├── 2_famMgmt.py
    ├── 3_csv_editor.py
    ├── 4_json_editor.py
    ├── 6_show_3G.py
    ├── 7_show_related.py
    ├── 8_caseMgmt.py
    └── 9_birthday.py
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

The three-generation page and the relationship page draw interactive HTML in the page (`streamlit.components.v1.html` around a pyvis graph). Names in the hover text are escaped. The three-generation graph and the relationship graph each place a generation on its own row, smaller generation numbers above larger ones. There is no PNG or SVG download. Relationship edges stay gray and are labeled with the relation type.

The retired personal-edition sample and CSV template are in `archive/personal-edition/`. A `data/me.csv` left on a machine is not read by this app and is not committed.

Created by [Michael Kao](https://github.com/mkaoy2k/fTrees).
