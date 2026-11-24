# DATAWISE - Data Cleaning and Validation Engine

**Transform Raw Data into Reliable Insights**

DATAWISE is a Python and Streamlit web application that turns raw, inconsistent and incomplete datasets into clean,
validated, analysis-ready data. Upload a file, see its quality problems, clean it with full control, validate it with your
own rules, compare before and after, and download the cleaned data together with a quality report.

Developer: **Ragav K P** &nbsp;|&nbsp; DIT internship Task 7 (individual project) &nbsp;|&nbsp; Version 1.0.0

> **Smart Clean is rule-based automation, not generative AI.** It uses fixed rules, Pandas and simple statistics. There is no
> external AI service, no API key and no randomness.

---

## Features

| Module | What it does |
|---|---|
| Dashboard | Rows, columns, missing values, duplicates, invalid values, quality score, latest activity, charts. Shows a welcome screen (no fake numbers) when no data is loaded. |
| Data Upload | CSV, XLSX and JSON. Handles empty, unsupported, corrupted and wrongly encoded files with clear messages. Preview, data types, replace or remove the dataset. |
| Data Profiling | Per-column type, missing %, unique values, min/max/mean/median, common values, empty strings, IQR outliers, charts. |
| Data Cleaning | Missing values, duplicates, text cleaning, column names, type conversion, outliers (IQR / Z-score with review), standardization, custom rules. |
| Smart Clean | Analyze, review the recommendations, apply the ones you tick, compare before/after, undo or reset. |
| Data Validation | Required value, email, phone, numeric, date, duplicates, min/max, text length, allowed values, regex, required columns. Row-level issues and exports. |
| Quality Analysis | Transparent 0-100 score (completeness, validity, uniqueness, consistency) with explanations, issues and suggestions. |
| Cleaning History | Every step is logged for the session; undo the last step or reset to the original data. |
| Sample Library | Three intentionally messy, fictional datasets (customers, sales, employees). |
| Reports and Downloads | Cleaned CSV and Excel, validation report, quality report, history (CSV/JSON), HTML report (print to PDF from the browser). |
| Settings | Preview size, blank handling, outlier defaults, date order, phone digit range, reset. |

## Technology stack

Python 3.13, Streamlit, Pandas, NumPy, Plotly, OpenPyXL, JSON, Regex, pytest, Git, GitHub, Streamlit Community Cloud.
No paid services, no API keys.

## Project structure

```
DATAWISE/
|-- app.py                  entry point: page setup, sidebar, navigation
|-- requirements.txt        Python packages
|-- packages.txt            system packages for Streamlit Cloud (none needed)
|-- pytest.ini              test settings
|-- .streamlit/config.toml  theme (light content, dark sidebar) and upload limit
|-- assets/dit_logo.png     official DIT (DefineInfoTech) logo - used as is
|-- pages/                  one file per screen (dashboard, upload, profiling, cleaning, validation, quality, reports, settings)
|-- core/                   the logic - no Streamlit code, fully unit tested
|   |-- file_handler.py         read CSV/XLSX/JSON, write CSV/Excel
|   |-- profiler.py             column and dataset profile
|   |-- cleaning_engine.py      every cleaning operation
|   |-- validation_engine.py    rule-based validation
|   |-- quality_score.py        the 0-100 score and its explanation
|   |-- recommendation_engine.py  rule-based Smart Clean
|   |-- report_generator.py     HTML / Excel / history exports
|   `-- data_utils.py           shared helpers and constants
|-- components/             reusable UI: styling + logo, sidebar, state, cards, charts, tables
|-- sample_data/            three messy fictional CSV files
|-- tests/                  pytest tests for the core logic
`-- docs/                   project report, presentation, viva questions, GitHub and deployment guide
```

**Why this layout?** `pages/` only draws screens, `core/` only processes data, `components/` only holds reusable UI. Because
`core/` has no Streamlit code, it can be tested without opening a browser.

## Install and run on Windows (PowerShell + VS Code)

```powershell
# 1. Open PowerShell in the project folder (the folder that contains app.py)
cd $HOME\Documents\DATAWISE

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1          # if blocked:  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 3. Install the packages
pip install -r requirements.txt

# 4. Start the app
streamlit run app.py
```

Streamlit prints a local address (normally http://localhost:8501) and opens it in your browser. Stop the app with `Ctrl + C`.

## Run the tests

```powershell
python -m pytest
```

The tests cover CSV/Excel/JSON reading, missing-value detection and handling, duplicates, text cleaning, column names, type
conversion, email/numeric/date validation, outliers, the quality score, Smart Clean, and the export functions.

## How to use the app

1. **Data Upload**: upload a file, check the preview, press *Load this dataset* (or load a sample).
2. **Data Profiling**: see the health of every column.
3. **Data Cleaning > Smart Clean**: press *Analyze dataset*, tick the steps you agree with, press *Apply selected steps*.
   Use the other tabs for manual control. *Undo last step* and *Reset to original data* are always at the top.
4. **Data Validation**: add rules (or press *Suggest rules*), run validation, inspect row-level issues.
5. **Quality Analysis**: read the score, the issues and how to improve it.
6. **Reports and Downloads**: download the cleaned data and the reports.

## The DIT logo

The official logo is stored at `assets/dit_logo.png` and is never edited. The app finds it with a path relative to the code
(`components/styling.py`), so it works locally and on Streamlit Cloud. It appears in the sidebar (above the DATAWISE name), in the
dashboard header or the welcome screen, and on the cover of the HTML report. It is shown on a white card with its original
aspect ratio. If the file is missing, the text "DefineInfoTech" is shown and the app keeps running.
**Make sure `assets/dit_logo.png` is committed to GitHub** (it is not listed in `.gitignore`).

## Security and privacy

- Uploaded files are read in memory as data only. Nothing is executed and nothing is saved to disk.
- File names are never used as paths. Excel exports keep cell text as text so uploaded values cannot become formulas.
  The HTML report escapes all values from your data.
- No secrets are needed. `.gitignore` excludes `.env` and `.streamlit/secrets.toml`.
- **Do not upload confidential or highly sensitive personal data to a public deployment.**

## Deployment (Streamlit Community Cloud)

1. Create a **public** GitHub repository (for example `datawise`) with no README, `.gitignore` or licence (they already exist here).
2. In the project folder:
   ```powershell
   git init
   git add .
   git commit -m "DATAWISE v1.0.0"
   git branch -M main
   git remote add origin https://github.com/<your-username>/datawise.git
   git push -u origin main
   ```
3. Check on GitHub that `assets/dit_logo.png`, `sample_data/` and `requirements.txt` are visible.
4. Go to https://share.streamlit.io, sign in with GitHub and choose **Create app**.
5. Select your repository, branch `main`, main file path `app.py`, then **Deploy**.
6. To update the live app, commit and push again (`git add .`, `git commit -m "message"`, `git push`); it redeploys automatically.

More detail and troubleshooting: [`docs/GITHUB_AND_DEPLOYMENT.md`](docs/GITHUB_AND_DEPLOYMENT.md).

## Screenshots

Add your own screenshots to a `docs/screenshots/` folder after running the app, then list them here:

```
![Dashboard](docs/screenshots/dashboard.png)
![Smart Clean](docs/screenshots/smart_clean.png)
![Quality Analysis](docs/screenshots/quality.png)
```

## Limitations

- Everything is **session-based**: data, history, rules and settings disappear when the page is refreshed or the session ends.
- Free hosting limits apply: the app may sleep when idle, memory is limited and very large files can fail. Upload limit is 50 MB.
- Phone and date validation cannot cover every country format; use the digit range, date order, exact format or regex options.
- Email validation checks the format only, not whether the mailbox exists.
- Smart Clean is heuristic. It never fills missing values or removes outliers on its own, and ambiguous choices (such as date order) are left for you to confirm.
- Undo keeps only the last 8 versions, and is skipped for very large tables to save memory.

## Future enhancements

Saving and re-using cleaning recipes, fuzzy duplicate detection, more file formats, multi-sheet Excel selection,
column-level data type rules, a PDF export built into the app, and optional user accounts with saved projects.

## Licence

Created as an academic internship project. Sample data is fictional.
