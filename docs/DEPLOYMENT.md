# Deployment Guide

Two deployments, done separately: a **GitHub repository** (the source of
record — code, docs, and the dataset) and a **live demo app**. This guide
assumes you've already run the pipeline locally per the main README and
have a working `data/entities.json` / `data/relationships.json`.

**Currently deployed:** the Gradio app (`app/app.py`) on **Render's free
tier**, at
[ai-orbit-pipeline-6482.onrender.com](https://ai-orbit-pipeline-6482.onrender.com).
Render was chosen specifically because it runs a Gradio app on a free
tier with no paid-plan gate — unlike Hugging Face, which now requires PRO
just to *create* a Gradio Space (see Part D below). This guide documents
all three real options (Render, a free Hugging Face Static Space, and the
paid Hugging Face Gradio Space route) so you can pick based on what you
have available.

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

## Deploying the demo app: your options

There are two versions of the demo app in this repo:

- **`app/app.py`** — the original Gradio build. This is what's currently
  live, deployed on **Render's free tier** (Part B below) — Render has no
  paid-plan gate for running a Python web service, unlike Hugging Face.
- **`webapp/`** — a static HTML/CSS/JS build with identical functionality,
  no Python backend at all. Free to deploy on a Hugging Face **Static
  Space** or GitHub Pages (Part C / C-alt below).

Hugging Face's Gradio/Docker Spaces require a **paid PRO plan ($9/month
for personal accounts)** just to *create* one — the CPU Basic hardware
itself is still free once created, but the creation step is gated. If you
have or don't mind getting PRO, that route is Part D below.

---

## Part B: Deploy the Gradio app to Render (free, currently live)

Render's free tier runs a Python web service directly from a GitHub repo,
with no payment gate — this is how the current live demo is deployed.

### B1. Add a start command Render can use

Render needs to know how to launch a Gradio app as a web service. Gradio's
`demo.launch()` needs to bind to the host/port Render assigns, so add this
near the bottom of `app/app.py`, replacing the existing `if __name__ ==
"__main__":` block:

```python
if __name__ == "__main__":
    import os
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
```

`server_name="0.0.0.0"` is required — Render's proxy can't reach a Gradio
app bound only to `127.0.0.1`. Reading `PORT` from the environment is
required too — Render assigns the port dynamically and passes it in via
that variable.

### B2. Push your repo to GitHub first

Render deploys directly from a connected GitHub repo, so complete Part A
above before starting this section.

### B3. Create the Render service

1. Go to [dashboard.render.com](https://dashboard.render.com) and sign up
   / log in (GitHub login is the fastest option, and connects your repos
   immediately).
2. Click **New → Web Service**.
3. Connect the GitHub repo you pushed in Part A.
4. Configure:
   - **Name:** e.g. `ai-orbit-pipeline` (this becomes part of your URL).
   - **Region:** whichever is closest to you.
   - **Branch:** `main`.
   - **Root Directory:** leave blank (repo root).
   - **Runtime:** Python 3.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app/app.py`
   - **Instance Type:** **Free**.
5. Click **Create Web Service**.

Render builds and deploys automatically. Watch the **Logs** tab for
`pip install` output and, once it's running, a line confirming Gradio is
listening on the assigned port.

### B4. Verify it's live

Render gives you a URL in the form
`https://<your-service-name>-<random-id>.onrender.com`. Open it — you
should see the same three-tab app (Browse & Search, Relationship
Explorer, Dataset Stats) as running it locally.

**Free tier behavior to know about:** Render's free web services spin
down after a period of inactivity and take 30–60 seconds to wake back up
on the next visit. This is expected — it's not a crash, just the free
tier's cold-start tradeoff. There's no way to avoid this without a paid
Render plan.

### B5. Refreshing the dataset later

Render redeploys automatically whenever you push to the connected branch:

```bash
python run.py                          # regenerate data/entities.json etc.
git add data/
git commit -m "Refresh dataset"
git push
```

Render picks up the push and redeploys within a minute or two — check the
**Events** tab on your service's dashboard to watch it happen.

---

## Part C: Deploy the static web app to Hugging Face (free, no PRO needed)

Static Spaces — plain HTML/CSS/JS, no Python backend — remain free to
create for everyone on Hugging Face.

### C1. Create the Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   (create a free Hugging Face account first if you don't have one).
2. **Owner:** your username or an organization you belong to.
3. **Space name:** e.g. `ai-orbit-explorer`.
4. **License:** your choice (MIT is a reasonable default).
5. **Select the Space SDK:** choose **Static**.
6. **Visibility:** Public (so it's viewable with no login).
7. Click **Create Space**.

Hugging Face will show you a git URL like
`https://huggingface.co/spaces/<your-username>/ai-orbit-explorer` and
clone instructions.

### C2. Copy the webapp files across

Static Spaces expect an `index.html` at the **repo root**. The `webapp/`
folder in this project is already laid out exactly that way — just copy
its entire contents:

```bash
git clone https://huggingface.co/spaces/<your-username>/ai-orbit-explorer
cd ai-orbit-explorer

cp -r /path/to/ai-orbit-pipeline/webapp/* .
```

That copies `index.html`, `style.css`, `app.js`, `vendor/` (the locally
vendored Chart.js), and `data/entities.json` + `data/relationships.json`
in one step. No path changes are needed — `webapp/` was built to work
standalone.

### C3. Add a Space README header (required by Hugging Face)

Static Spaces need the same YAML header as Gradio Spaces, just with
`sdk: static` instead. Create/overwrite `README.md` in the Space repo
root:

```markdown
---
title: AI Orbit Ecosystem Explorer
emoji: 🛰️
colorFrom: blue
colorTo: green
sdk: static
pinned: false
license: mit
---

# AI Orbit — Ecosystem Explorer

A structured, cross-referenced map of the AI ecosystem — entities and
relationships ingested from GitHub, Hugging Face, YouTube, RSS news, and
official company sites.

Full pipeline source code: https://github.com/<your-username>/ai-orbit-pipeline
```

### C4. Push

```bash
git add .
git commit -m "Deploy AI Orbit Ecosystem Explorer (static)"
git push
```

The Space builds (effectively just uploads — there's no build step for
static sites) in a few seconds. It's live at
`https://huggingface.co/spaces/<your-username>/ai-orbit-explorer`, public,
no login, no PRO plan required.

### C5. Refreshing the dataset later

```bash
cd ai-orbit-pipeline
python run.py

cd ../ai-orbit-explorer
cp ../ai-orbit-pipeline/data/entities.json ./data/
cp ../ai-orbit-pipeline/data/relationships.json ./data/
git add data/
git commit -m "Refresh dataset"
git push
```

---

## Part C-alt: Deploy the static web app to GitHub Pages (also free)

Since you already have a GitHub repo, GitHub Pages is a natural second (or
only) place to host the same static app, for free. A ready-to-use GitHub
Actions workflow already ships with this project at
`.github/workflows/deploy-pages.yml` — this avoids the "Pages can only
serve from root or /docs" limitation of the older, non-Actions Pages
setup, since `webapp/` isn't named `docs/`.

### Enable Pages

1. In your GitHub repo, go to **Settings → Pages**.
2. Under **Build and deployment → Source**, select **GitHub Actions**.
3. That's it — the workflow file is already in the repo (you pushed it in
   Part A). Go to your repo's **Actions** tab; it should already have run
   automatically on your initial push (it triggers on any push touching
   `webapp/**`), or trigger it manually with **Run workflow**.
4. Once it finishes, your app is live at
   `https://<your-username>.github.io/ai-orbit-pipeline/`.

This workflow re-deploys automatically every time you update
`webapp/data/*.json` and push, so refreshing the live dataset is just:

```bash
python run.py
cp data/entities.json data/relationships.json webapp/data/
git add webapp/data/
git commit -m "Refresh dataset"
git push
```

---

## Part D: Deploy the Gradio app to Hugging Face Spaces (requires PRO)

Only follow this if you have (or are getting) a Hugging Face PRO plan and
specifically want the Gradio version rather than the static one — they
are functionally identical.

### D1. Create the Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. **Owner:** your username or an organization you belong to.
3. **Space name:** e.g. `ai-orbit-explorer-gradio`.
4. **License:** your choice.
5. **Select the Space SDK:** choose **Gradio**.
6. **Space hardware:** CPU basic (no additional hourly cost beyond the
   PRO subscription itself).
7. **Visibility:** Public.
8. Click **Create Space**. If your account isn't on a paid plan, Hugging
   Face will prompt you to upgrade at this step.

### D2. Prepare the Space's file layout

Hugging Face Spaces expect `app.py` and `requirements.txt` at the **repo
root** — not nested in an `app/` folder like in the main project.

```bash
git clone https://huggingface.co/spaces/<your-username>/ai-orbit-explorer-gradio
cd ai-orbit-explorer-gradio

cp /path/to/ai-orbit-pipeline/app/app.py ./app.py

mkdir -p data
cp /path/to/ai-orbit-pipeline/data/entities.json ./data/
cp /path/to/ai-orbit-pipeline/data/relationships.json ./data/

cp /path/to/ai-orbit-pipeline/requirements.txt ./requirements.txt
```

### D3. Fix the one path that changes

```python
# In app.py, find this line near the top:
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Change it to (app.py is now at the Space's repo root):
DATA_DIR = Path(__file__).resolve().parent / "data"
```

### D4. Add a Space README header

A ready-to-copy template is provided at
[`docs/space_README_template.md`](space_README_template.md) — copy it to
the Space repo root as `README.md`, replace `<your-username>`, and confirm
`sdk_version` matches the `gradio` version pinned in `requirements.txt`.

### D5. Push

```bash
git add .
git commit -m "Deploy AI Orbit Ecosystem Explorer (Gradio)"
git push
```

Watch the **Logs** tab on the Space page for build output and errors.

---

## Troubleshooting

**Render deploy succeeds but the app never becomes reachable**
Almost always means `server_name="0.0.0.0"` and the `PORT` environment
variable weren't wired into `demo.launch()` per step B1 — Gradio defaults
to binding `127.0.0.1`, which Render's proxy can't reach from outside the
container. Check the **Logs** tab for a line showing what host/port Gradio
actually bound to.

**Render app is slow to load the first time**
Expected on the free tier — the service spins down after inactivity and
takes 30–60 seconds to cold-start on the next request. Not a bug; there's
no fix on the free tier short of upgrading to a paid Render plan that
stays warm.

**Static Space or GitHub Pages shows a blank page or "Failed to load dataset" error**
Open the browser console (F12). If you see a 404 for `data/entities.json`,
the data files weren't copied into the deployed folder — check the
**Files** tab (Space) or the repo tree (`webapp/data/`) to confirm both
JSON files are present. If you see a CORS error, you're likely opening
`index.html` directly via a `file://` URL instead of through the actual
deployed hosting — that only affects local testing (see `webapp/README.md`
for the local-server workaround), not the real deployment.

**Charts don't appear on the Dataset Stats tab**
Check the console for a Chart.js-related error. The static app vendors
Chart.js locally (`webapp/vendor/chart.umd.js`) specifically so this
doesn't depend on a CDN being reachable — if `vendor/chart.umd.js` wasn't
copied along with everything else, re-copy the full `webapp/` folder
contents rather than picking files individually.

**Gradio Space build fails with `ModuleNotFoundError`**
Check `requirements.txt` was actually copied to the Space root (not left
nested under a subfolder) and that its contents match what `app.py`
imports (`gradio`, `pandas`).

**Gradio Space loads but shows "0 entities" or crashes on load**
Almost always the `DATA_DIR` path from step D3 wasn't updated, or
`data/entities.json` / `data/relationships.json` weren't copied into the
Space repo. Check the Space's **Files** tab to confirm both JSON files are
actually present at `data/entities.json` relative to the repo root.

**GitHub Pages Action runs but the site 404s**
Confirm **Settings → Pages → Source** is set to **GitHub Actions** (not
"Deploy from a branch") — the workflow in Part C-alt only works with the
Actions source setting. Also confirm the workflow's `path:` under
`upload-pages-artifact` points at `webapp` (matching this project's folder
name).

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