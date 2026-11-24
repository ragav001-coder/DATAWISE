# GitHub and Streamlit Community Cloud - Step by Step

This guide is written for Windows, PowerShell and VS Code. **Nothing here has been done for you yet**: the app has not been
pushed to GitHub or deployed. Do the steps below, and only say it is deployed after you open the live link and see it work.

## Part A - Run it locally first

```powershell
cd $HOME\Documents\DATAWISE          # the folder that contains app.py
python -m venv venv                  # creates a private package folder
.\venv\Scripts\Activate.ps1          # you should now see (venv) in the prompt
pip install -r requirements.txt      # installs Streamlit, Pandas, Plotly ...
python -m pytest                     # runs the automatic tests - they should all pass
streamlit run app.py                 # starts the app; open http://localhost:8501
```

Local check list: the DIT logo is visible at the top of the sidebar; **Data Upload > Load customers sample** works; the
Dashboard shows numbers; **Data Cleaning > Smart Clean > Analyze dataset > Apply selected steps** works; the **Reports** page
downloads open correctly.

## Part B - GitHub

**1. Create the repository.** On github.com press **New repository**. Name: `datawise`. Choose **Public** (Streamlit's free
plan deploys from GitHub). Do **not** tick "Add a README", ".gitignore" or "licence". Press **Create repository**.

**2. Tell Git who you are** (once per computer). Git writes this name and email into every saved change:

```powershell
git config --global user.name "Ragav K P"
git config --global user.email "the-email-used-on-your-github-account@example.com"
```

**3. Turn the folder into a Git repository and save the first version:**

```powershell
cd $HOME\Documents\DATAWISE
git init                               # starts tracking this folder
git add .                              # marks every allowed file to be saved (.gitignore skips venv etc.)
git status                             # CHECK: assets/dit_logo.png and sample_data/*.csv are listed; venv/ is NOT
git commit -m "DATAWISE v1.0.0"        # saves a snapshot with a message
git branch -M main                     # names the main branch "main"
```

**4. Connect to GitHub and upload:**

```powershell
git remote add origin https://github.com/<your-username>/datawise.git   # the address of your empty repository
git push -u origin main                                                 # uploads; a browser window may ask you to sign in
```

**5. Verify on GitHub.** Open the repository page and confirm you can see `app.py`, `requirements.txt`, the `core`, `pages`,
`components`, `sample_data`, `tests` folders and **`assets/dit_logo.png`**. If the logo is missing there, run
`git add -f assets/dit_logo.png`, `git commit -m "Add logo"`, `git push`.

Common problems:

| Message | Fix |
|---|---|
| `git is not recognized` | Install Git from git-scm.com and reopen PowerShell. |
| `Author identity unknown` | Run the two `git config` commands in step 2. |
| `remote origin already exists` | `git remote set-url origin https://github.com/<your-username>/datawise.git` |
| `Authentication failed` | Sign in through the browser window, or use a Personal Access Token as the password. |
| `rejected ... fetch first` | You created the repo with a README. Run `git pull origin main --rebase`, then push again. |

## Part C - Deploy on Streamlit Community Cloud (free)

1. Go to **https://share.streamlit.io** and **Continue with GitHub**. Allow access.
2. Press **Create app** and choose **Deploy a public app from GitHub**.
3. Repository: `<your-username>/datawise`. Branch: `main`. **Main file path: `app.py`**.
4. (Optional) choose a short app URL, for example `datawise-ragav`.
5. Press **Deploy**. The first build installs `requirements.txt` and takes a few minutes. Watch the log on the right.
6. When it finishes the app opens at `https://<name>.streamlit.app`. Test it exactly like Part A.

Troubleshooting:

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` in the log | The package is missing from `requirements.txt`. Add it, commit, push. |
| `No such file ... app.py` | Main file path must be `app.py` (the file is in the repository root). |
| Logo shows the text "DefineInfoTech" | `assets/dit_logo.png` was not pushed. See Part B step 5. |
| App is slow or restarts on big files | Free hosting has limited memory. Try a smaller file. |
| "This app has gone to sleep" | Free apps sleep when idle. Press **Yes, get this app back up!**. |
| Python version | In the app's **Settings > Advanced settings** choose Python 3.13 if offered, then reboot. |

## Part D - Update the live app

```powershell
git add .
git commit -m "Describe what you changed"
git push
```

Streamlit Cloud notices the push and redeploys in about a minute. Use **Manage app > Reboot app** if it does not.

## Limits of free hosting (explain these in your viva)

- **Sleeping:** apps with no visitors for a while are put to sleep and wake on the next visit.
- **Resources:** limited memory and CPU; DATAWISE caps uploads at 50 MB.
- **Temporary storage:** files written to disk are not kept. DATAWISE writes nothing to disk.
- **Session persistence:** all work is kept in the visitor's session only and is lost on refresh or timeout.
- **Public access:** anyone with the link can open the app, so never upload confidential data.
