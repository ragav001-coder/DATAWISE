# DATAWISE - Viva Preparation (44 questions)

Answers are written in simple English so you can learn them and say them in your own words. Every answer describes only
what DATAWISE really does.

## A. The project

**1. What is DATAWISE?**
DATAWISE is a web application I built with Python and Streamlit. It takes a raw dataset (CSV, Excel or JSON), finds quality
problems, helps me clean it, validates it with rules, gives a quality score from 0 to 100, and lets me download the cleaned
data and a report.

**2. Why did you choose this project?**
Real data is almost always messy, and analysts spend a lot of time cleaning it. I wanted a tool that makes this safe,
visible and repeatable, and that also let me practise Python, Pandas, testing and deployment.

**3. What problem does it solve?**
It finds and fixes missing values, duplicate rows, extra spaces, wrong capitalisation, mixed date formats, numbers stored as
text and invalid emails or phones, and it shows evidence (before/after) that the data got better.

**4. Who is the user?**
A student, analyst or small business person who has a spreadsheet-style file and wants it clean before analysis.

**5. What is the existing system and what is your proposed system?**
Existing: people clean data by hand in Excel, or write one-off scripts. This is slow, hard to repeat and easy to get wrong.
Proposed: one app with profiling, guided cleaning, validation, scoring and reports, with a history of every change.

## B. Concepts

**6. What is data cleaning?**
Fixing or removing wrong, incomplete, duplicate or badly formatted data so it can be trusted.

**7. What is data validation?**
Checking data against rules, for example "email must look like name@domain.com". Validation reports problems; it does not change data.

**8. What is the difference between cleaning and validation?**
Cleaning changes the data. Validation only checks it and lists what fails. In DATAWISE validation never modifies the dataset.

**9. What is data preprocessing?**
All the preparation done before analysis or machine learning: cleaning, converting types, standardising and scaling.

**10. What is a missing value?**
A cell with no value (NaN/None). DATAWISE also counts empty or space-only text as missing, and you can switch that off in Settings.

**11. What is a duplicate record?**
A row that is identical to an earlier row. DATAWISE keeps the first copy and can remove the rest. You can also decide duplicates by selected columns only.

**12. What is an outlier?**
A value that is very different from the others, for example an age of 250. It may be an error or a real extreme, so a person must review it.

**13. What is IQR?**
The Interquartile Range: Q3 (75th percentile) minus Q1 (25th percentile). A value below Q1 - 1.5 x IQR or above Q3 + 1.5 x IQR is treated as an outlier.

**14. What is a Z-score?**
How many standard deviations a value is from the mean: (value - mean) / standard deviation. Values with |z| above 3 are flagged. It works best with many values and a bell-shaped distribution.

**15. Why do you show outliers before removing them?**
Because an outlier can be a genuine value. DATAWISE never removes or caps outliers automatically; you must review them, tick a confirmation and choose "cap" or "remove".

**16. What is a DataFrame?**
Pandas' table object: rows and named columns, like an Excel sheet inside Python.

**17. What is standardization?**
Making the same kind of value look the same: one date format, one spelling for a category, numbers as real numbers.

**18. What is normalization (scaling) in your project?**
An optional tool that adds NEW columns with min-max (0 to 1) or z-score scaled numbers. The original columns stay.

## C. Technology

**19. Why Pandas?**
It is the standard Python library for tables: fast, well tested and it has the operations I need (missing values, duplicates, grouping, type conversion).

**20. Why Streamlit?**
It lets me build an interactive web app in pure Python, with no HTML/JavaScript project, and it deploys free on Streamlit Community Cloud.

**21. Why Plotly?**
It makes interactive charts (hover, zoom) and works well inside Streamlit.

**22. What is OpenPyXL used for?**
Reading and writing Excel .xlsx files.

**23. What is session state?**
Streamlit re-runs the script after each click. Session state is a dictionary that remembers my data, history and settings between runs for one browser session.

**24. Why is the code split into pages, core and components?**
`pages` draws screens, `core` processes data without any Streamlit code, `components` has reusable UI. This keeps the code understandable and lets me test the logic on its own.

## D. How it works

**25. How does file upload work?**
The uploaded file is read from memory into a DataFrame by `core/file_handler.py`. It checks the file type, empty files, size and corruption, tries several text encodings for CSV and gives a clear error message if reading fails. The file is never executed or saved.

**26. How do you protect the original data?**
There are two copies: the original upload (never changed) and a working copy. Every cleaning function returns a new DataFrame. I can undo the last step or reset to the original.

**27. How does email validation work?**
A regular expression checks the shape: allowed characters, one @, a domain, and a top-level domain of at least two letters. Double dots are rejected. It checks format only, not whether the mailbox exists.

**28. How does phone validation work and what is its limit?**
It allows digits, spaces and + - ( ) . and checks the digit count (default 7 to 15). Phone formats differ by country, so I made the digit range configurable and I explain that it cannot prove a number is real.

**29. How does date validation work?**
Values are parsed as real calendar dates, so 31/04/2024 fails. Because 05/06/2024 is ambiguous, the user chooses day-first or month-first, or gives an exact format.

**30. How does the data quality score work?**
Four categories from 0 to 100: Completeness (share of non-missing cells), Uniqueness (share of non-duplicate rows), Validity (share of passed checks) and Consistency (formatting problems such as extra spaces, mixed case and mixed date formats). The overall score is a weighted average: 30%, 20%, 30%, 20%.

**31. What if a category cannot be measured?**
It is shown as "not applicable" and its weight is shared among the others, so the score is not unfairly lowered. An empty dataset gets no score at all.

**32. How does Smart Clean work?**
It runs fixed detectors in order (spaces, blanks, spelling variants, text numbers/dates, duplicates, column names), simulates each step on a copy to measure its effect, and shows the list. I tick the steps I accept and press Apply.

**33. Is this real AI?**
No. Smart Clean is rule-based automation using Python, Pandas and statistics. There is no machine learning model and no external AI service. The app says so on screen.

**34. How is automation implemented?**
The workflow upload -> analyze -> recommend -> review -> apply -> validate -> score -> compare -> report -> download is connected by functions in `core` and buttons in the pages. Every step is logged.

**35. What does Smart Clean NOT do automatically?**
It does not fill missing values, remove outliers or fix invalid emails. These need human judgement, so they appear as advice only.

**36. How do you convert data types safely?**
If any value cannot be converted, the operation stops, changes nothing and lists the problem values. The user may choose to set failing values to missing instead. Phone numbers and codes with leading zeros are not converted automatically.

**37. How is the cleaning history kept?**
Each applied or blocked step is recorded with time, columns, parameters, rows before and after, cells changed and missing values before and after. It lives in session state and is session-only.

**38. How are reports made?**
`core/report_generator.py` builds a self-contained HTML report (with the logo, scores, history, validation and before/after tables) and Excel reports with Pandas and OpenPyXL. All data values are escaped in the HTML.

## E. Testing, GitHub, deployment

**39. How did you test the project?**
I wrote 122 pytest tests for the core logic (reading files, missing values, duplicates, text, column names, types, validation, outliers, score, Smart Clean and exports). I run them with `python -m pytest`. I also found and fixed bugs this way. Please run them yourself and quote your own result.

**40. What is GitHub and why use it?**
GitHub stores my code online with version history. Streamlit Cloud reads the code from it when deploying.

**41. What is deployment?**
Putting the app on a server so anyone can open it with a link instead of running it on my computer.

**42. How does Streamlit Community Cloud work?**
It connects to my GitHub repository, installs `requirements.txt`, runs `app.py` and gives a public URL. When I push new code it redeploys.

## F. Reflection

**43. What are the limitations?**
Session-only memory; free hosting limits (sleep, memory); phone and date formats cannot cover every country; email check is format-only; Smart Clean is heuristic; undo keeps only 8 versions.

**44. What are the future enhancements?**
Saved cleaning recipes, fuzzy duplicate detection, more file formats, multi-sheet Excel, a built-in PDF export and saved projects with login.

---

### Bonus questions you may be asked

- *Show me where the DIT logo is loaded.* `components/styling.py`, using a path relative to the file; it falls back to text if the file is missing.
- *What happens if the logo file is deleted?* The app shows the text "DefineInfoTech" and keeps running.
- *Why a white card behind the logo?* The logo has dark lettering; the card keeps it readable on the dark sidebar without changing the logo.
- *What did you build yourself?* All modules in this repository: the engines, the tests, the interface and the documentation.
