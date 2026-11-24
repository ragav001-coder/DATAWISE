# Resume and Portfolio Text

## Resume entry

**DATAWISE - Data Cleaning and Validation Engine** | DIT Internship, Task 7 (Individual Project)

*A Python web application that profiles, cleans, validates and scores raw datasets and exports cleaned data and quality reports.*

**Technologies:** Python, Streamlit, Pandas, NumPy, Plotly, OpenPyXL, Regex, pytest, Git, GitHub, Streamlit Community Cloud

- Built a modular data-quality application (separate logic, UI and component layers) that reads CSV, Excel and JSON files and handles empty, corrupted and unsupported uploads.
- Implemented a cleaning engine for missing values, duplicates, text and column-name normalization, safe type conversion and IQR / Z-score outlier review, with undo and a session cleaning history.
- Designed a rule-based validation engine (email, phone, numeric, date, range, length, allowed values, regex) with row-level issue reports and Excel export.
- Created a transparent 0-100 data quality score (completeness, validity, uniqueness, consistency) and a rule-based Smart Clean recommender that proposes steps for the user to review.
- Wrote an automated pytest suite for the core logic and produced HTML and Excel reports with before/after comparison.

*(Add numbers such as the number of tests only after you have run them yourself.)*

## Short GitHub description (repository "About" box)

Streamlit app that profiles, cleans, validates and scores messy datasets (CSV/Excel/JSON) and exports cleaned data and quality reports. Pandas, Plotly, pytest.

**Suggested topics:** `python` `streamlit` `pandas` `data-cleaning` `data-validation` `data-quality` `plotly`

## One-paragraph project summary (for forms and LinkedIn)

DATAWISE is an individual internship project at DefineInfoTech. It is a Python and Streamlit web application that helps users turn raw,
inconsistent datasets into clean, validated, analysis-ready data. It combines profiling, guided cleaning with undo, rule-based
Smart Clean recommendations, configurable validation, a transparent data quality score and downloadable reports, and is
covered by automated tests.
