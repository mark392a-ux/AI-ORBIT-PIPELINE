# Deployment Guide

Two deployments, done separately: a **GitHub repository** (the source of
record — code, docs, and the dataset) and a **Hugging Face Space** (the
live, public demo app). This guide assumes you've already run the pipeline
locally per the main README and have a working `data/entities.json` /
`data/relationships.json`.

---

## Part A: Deploy to GitHub

### A1. Create the repository on GitHub

1. Go to [github.com/new](https://github.com/new).
2. Repository name: `ai-orbit-pipeline` (or whatever you prefer).
3. Leave "Initialize with README" **unchecked** — you already have one.
4. Visibility: your choice (Public is typical for a portfolio/submission
   piece).
5. Click **Create repository**. GitHub will show you a page with a remote
   URL like `https://github.com/<your-username>/ai-orbit-pipeline.git` —
   keep that page open.

### A2. Push your local project

From inside your `ai-orbit-pipeline` folder:

```bash
git init
git add .
git commit -m "Initial commit: AI Orbit data ingestion pipeline"
git branch -M main
git remote add origin https://github.com/<your-username>/ai-orbit-pipeline.git
git push -u origin main
```

If you already ran `git init` earlier in development, skip straight to
`git add .` — `git init` is safe to skip if `.git/` already exists.

### A3. Double-check what got committed

Your `.gitignore` already excludes `.env`, `logs/`, and `__pycache__/`, but
it's worth a sanity check before or right after pushing:

```bash
git status               # confirm .env is NOT listed as tracked
cat .gitignore            # confirm it includes .env
```

If you ever accidentally commit a real API key, rotate it immediately
(regenerate the token on GitHub/Hugging Face/Google Cloud) — removing it
from a later commit does not remove it from git history.

### A4. (Optional) Add repository metadata on GitHub

On your repo's GitHub page:
- Click the gear icon next to "About" and add a short description +
  topics (e.g. `data-engineering`, `nlp`, `knowledge-graph`, `gradio`).
- If you want the README to render nicely with the badge-free style it's
  written in, no extra action needed — GitHub renders `README.md`
  automatically on the repo homepage.

Your repository is now live at
`https://github.com/<your-username>/ai-orbit-pipeline`.

---

## Part B: Deploy the demo app to Hugging Face Spaces

Spaces are their own git repositories, separate from your GitHub repo. You
will push a *subset* of your project (the app + the data it reads) to a
Space-specific repo.

### B1. Create the Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   (create a free Hugging Face account first if you don't have one).
2. **Owner:** your username or an organization you belong to.
3. **Space name:** e.g. `ai-orbit-explorer`.
4. **License:** your choice (MIT is a reasonable default).
5. **Select the Space SDK:** choose **Gradio**.
6. **Space hardware:** CPU basic (free) — this app does no heavy
   computation, it just filters JSON in memory.
7. **Visibility:** Public (so it's viewable with no login, per the
   project's requirement).
8. Click **Create Space**.

Hugging Face will show you a git URL like
`https://huggingface.co/spaces/<your-username>/ai-orbit-explorer` and
git-clone instructions.

### B2. Prepare the Space's file layout

Hugging Face Spaces expect `app.py` and `requirements.txt` at the **repo
root** — not nested in an `app/` folder like in the main project. Clone the
new Space repo separately from your main project and copy files across:

```bash
git clone https://huggingface.co/spaces/<your-username>/ai-orbit-explorer
cd ai-orbit-explorer

# Copy the app to the Space's root
cp /path/to/ai-orbit-pipeline/app/app.py ./app.py

# Copy the dataset
mkdir -p data
cp /path/to/ai-orbit-pipeline/data/entities.json ./data/
cp /path/to/ai-orbit-pipeline/data/relationships.json ./data/

# Copy dependencies
cp /path/to/ai-orbit-pipeline/requirements.txt ./requirements.txt
```

### B3. Fix the one path that changes

`app/app.py` locates its data relative to its own file location, assuming
it lives one directory below the project root (`app/app.py` → `../data/`).
Once copied to the Space root, `app.py` and `data/` are siblings, so this
one line needs to change:

```python
# In app.py, find this line near the top:
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Change it to (app.py is now at the Space's repo root):
DATA_DIR = Path(__file__).resolve().parent / "data"
```

Everything else in `app.py` works unmodified — it only ever reads from
`DATA_DIR`, never anything under `src/`.

### B4. Add a Space README header (required by Hugging Face)

Hugging Face Spaces need a small YAML header at the top of their
`README.md` to configure the Space correctly. A ready-to-copy template is
provided at [`docs/space_README_template.md`](space_README_template.md) —
copy it to the Space repo root as `README.md` and replace
`<your-username>` with your actual GitHub username:

```bash
cp /path/to/ai-orbit-pipeline/docs/space_README_template.md ./README.md
# then edit README.md to replace <your-username>
```

Match `sdk_version` in that file to whatever `gradio` version is pinned in
your `requirements.txt` (currently `>=5.0,<6`; `5.31.0` is a safe concrete
choice and is what the template uses).

### B5. Push to the Space

```bash
git add .
git commit -m "Deploy AI Orbit Ecosystem Explorer"
git push
```

Hugging Face automatically builds the Space on push. Watch the build logs
at `https://huggingface.co/spaces/<your-username>/ai-orbit-explorer` — the
**"Logs"** tab shows `pip install` output and any startup errors.

### B6. Verify it's live

Once the build finishes (usually under a minute for a Gradio app this
size), the Space URL becomes interactive with no login required:

```
https://huggingface.co/spaces/<your-username>/ai-orbit-explorer
```

Check all three tabs (Browse & Search, Relationship Explorer, Dataset
Stats) load and the stat cards at the top show non-zero numbers — that
confirms `data/entities.json` and `data/relationships.json` were found
correctly.

### B7. Refreshing the dataset later

Whenever you re-run the pipeline locally and want the Space to reflect
new data:

```bash
cd ai-orbit-pipeline
python run.py                          # regenerate data/entities.json etc.

cd ../ai-orbit-explorer                # your Space repo clone
cp ../ai-orbit-pipeline/data/entities.json ./data/
cp ../ai-orbit-pipeline/data/relationships.json ./data/
git add data/
git commit -m "Refresh dataset"
git push
```

The Space rebuilds automatically on push.

---

## Troubleshooting

**Space build fails with `ModuleNotFoundError`**
Check `requirements.txt` was actually copied to the Space root (not left
nested under a subfolder) and that its contents match what `app.py`
imports (`gradio`, `pandas`).

**Space loads but shows "0 entities" or crashes on load**
Almost always the `DATA_DIR` path from step B3 wasn't updated, or
`data/entities.json` / `data/relationships.json` weren't copied into the
Space repo. Check the Space's **Files** tab to confirm both JSON files are
actually present at `data/entities.json` relative to the repo root.

**GitHub push rejected with "failed to push some refs"**
Usually means the remote has commits your local repo doesn't (e.g. you
initialized with a README on GitHub despite the instructions above). Run
`git pull origin main --allow-unrelated-histories` and resolve any
conflicts, then push again.

**Hugging Face push asks for a password and rejects it**
GitHub and Hugging Face both require a personal access token instead of
your account password for git operations over HTTPS. For Hugging Face,
generate one at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
(Write access) and use it as the password when prompted. For GitHub,
generate one at
[github.com/settings/tokens](https://github.com/settings/tokens).
