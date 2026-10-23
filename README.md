# FamilyTrees (`fts`)

## Introduction

The 'FamilyTrees' (`fts` in short) is a web application, wrritten in Python that allows you to record your family tree and connect to other family trees on Internet. It is an extension to the FamilyTrees Personal Edition (`ftpe`) project that is available for free.

## How It Works

The `fts` facilitates you to build your whole family tree as you grow your family and to be able to trace back your family root as you like. With this simple `fts` App, you can add, update, share and pass along your family tree among your family members. Who knows, it might become one of your family heritage some day.

The `fts` also provides various query functions to discover your root, by entertaining you with graphic representation of your related family members.

The `fts` not only helps you to build your family heritage, but also provides you with the following benefits:

1. _Sharing_:

   To join online over Internet, you can help  build the same family tree of yours. Or better yet, with divide-and-conquer approach, several family members can work together to build different parts of the family tree simultaneously. While merging them together seamlessly, resluting in the whole picture of your family history, the footprint of your family history might eventually become the treasure of your family heritage to pass along.

2. _Multi-Language Support_:

   Currently, there are 10 supported languages: English, Traditional Chinese, Simplified Chinese, Japanese, Korean, Danish, German, French, Lithuanian, and Polish. You are welcome if you would like to localize any language of yours. Don't hesitate to let [Creator: Michael Kao](mailto:mkaoy2k@gmail.com) know.

### System Requirements

- Python 3.8 or newer
- SQLite 3 (built-in)
- Email service (e.g., Gmail)

### Installation Steps

1. **Clone the Repository**

   ```bash
   git clone https://github.com/mkaoy2k/ftpe.git
   cd fts
   ```

2. **Create Virtual Environment (Recommended)**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or
   .\.venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies**

   Install the required dependencies by running the following command if using Conda environment:

   ```bash
   conda env create -f environment.yaml
   ```

   Or under uv environment, run:

   ```bash
   uv run python -m pip install -r requirements.txt
   ```

   Or under pip environment, run:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables** defined in the `.env` file

   ```bash
   cp template.env.txt .env
   ```

   Edit the `.env` file to tailor your environment:
   - Set server paths
   - Set your language, release, and version etc.
   - Configure email service
   - Set application name, DB admin name, DB admin password
   - Set DB name, DB host, DB port
   - Configure server URL

   Edit `L10N.json` if your language is newly added. The default languages are Traditional Chinese (繁中) and English (US).

   Edit `L10N_<your language>.json` if your language is newly added. The current localization files include:

   ```bash
   "繁中"  : "L10N_TW.json",
   "简中"  : "L10N_CN.json",
   "日本語" : "L10N_JP.json",
   "한국어" : "L10N_KR.json",
   "DANISH" : "L10N_DK.json",
   "GERMAN" : "L10N_DE.json",
   "FRENCH" : "L10N_FR.json",
   "LITHUANIAN" : "L10N_LT.json",
   "POLISH" : "L10N_PL.json",
   "US"   : "L10N_US.json"
   ```

   To set your preferred language, you can specify your preferred language in the `.env` file, e.g.:

   ```bash
   L10N_FILE="L10N.json"
   L10N="繁中"
   # L10N="US"
   ```

   At the run time, from `Settings` sidebar, you can also select your preferred language from the 'User Language' drop-down list.

5. **Initialize Data Directory**

   ```bash
   mkdir -p data
   ```

6. **Initialize Admin User Database**

   ```bash
   python genesis.py
   ```

## Directory Structure

fts/
├── auth_utils.py         # Authentication utilities
├── context_utils.py      # Context management
├── db_utils.py           # Database utilities
├── email_utils.py        # Email functionality
├── fTrees.py             # Main interface
├── ftpe.py               # Personal edition (`streamlit run ftpe.py`)
├── funcUtils.py          # Utility functions
├── genesis.py            # Initialization script
├── glogTime.py           # Logging utilities
├── ops_dbMgmt.py         # Database management
configuration script
├── bday.html             # Birthday template
├── requirements.txt      # Python dependencies
├── template.env.txt      # Environment template
│
├── data/                 # Data directory
│   ├── family.db         # Local database (not in git)
│   ├── me.csv            # Local personal tree (not in git)
│   ├── me.sample.csv     # Fictional sample tree
│   └── template.csv      # CSV template
│
└── pages/                # Application pages
    ├── 1_usrMgmt.py      # User management page
    ├── 2_famMgmt.py      # Family management page
    ├── 3_csv_editor.py   # CSV editor page
    ├── 4_json_editor.py  # JSON editor page
    ├── 6_show_3G.py      # show 3G page
    ├── 7_show_related.py # show relatives page
    ├── 8_caseMgmt.py     # case management page
    └── 9_birthday.py     # birthday page

## How to Use

There are two running environments that are supported to run `fts` App.

1. To run `fts` App as a Docker Image in a Docker Container:

   - After pulling mkaoy2k/fts image from the [Docker Hub](https://hub.docker.com), execute the following command to launch `fts` container, for example:

   ```bash
   docker run --name fts -d -p 8501:8501 --env-file .env mkaoy2k/fts:2.6
   ```

   Pass configuration and secrets with `--env-file` or `-e`. The image does not contain `.env`, database files, or `data/me.csv`.

   - At your default web browser, displaying the login page by entering:

   ```bash
   http://localhost:8501
   ```

2. To run `fts` App in Python environment, do:

   - Ensure that you have installed the required dependencies in the `.env` file.

   - Run the `fTrees.py` file using the Streamlit CLI. Execute the following command to launch `fts` server:

   ```bash
   streamlit run fTrees.py
   ```

   - When the `fts` server is running, your default web browser, displaying a login page, will be launched automatically. Or at will, you may launch your default web browser, displaying the login page by entering:

   ```bash
   http://localhost:8501
   ```

   Created with ❤️ by:
   [Michael Kao](https://github.com/mkaoy2k/fts)
