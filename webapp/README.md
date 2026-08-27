# AI Orbit — Static Web App

A pure client-side rebuild of the Gradio demo app (`app/app.py`), with
identical functionality, that requires no Python server and no paid
hosting tier. Runs entirely as static files.

## Why this exists

Hugging Face now requires a paid plan to *create* a Gradio or Docker
Space (the CPU Basic hardware itself is still free once created, but
creating one at all needs PRO). Static Spaces — plain HTML/CSS/JS with no
backend — remain free for everyone. Since this app's entire job is
filtering and displaying two pre-generated JSON files, it doesn't
actually need a Python backend at request time, so it was rebuilt as a
static site: same features, zero cost, and it also runs on GitHub Pages,
Netlify, Vercel, or literally any static file host (or none at all, if
you just open the file locally through a simple server).

## Files

```
webapp/
├── index.html            # page structure, all three tabs
├── style.css             # "mission control" visual identity
├── app.js                 # all logic — ports app.py 1:1 into vanilla JS
├── vendor/
│   ├── chart.umd.js        # Chart.js, vendored locally (no CDN dependency)
│   └── chart.js-LICENSE.md
└── data/
    ├── entities.json       # copy of ../data/entities.json
    └── relationships.json  # copy of ../data/relationships.json
```

## Feature parity with the Gradio app

| Feature | Gradio app | Static app |
|---|---|---|
| Stat cards (totals) | ✅ | ✅ |
| Search + category/type filters | ✅ | ✅ |
| Entity detail panel w/ specialized metadata | ✅ | ✅ |
| Relationship Explorer, sorted by connectivity | ✅ | ✅ |
| Empty-state with clickable suggestions | ✅ | ✅ (suggestions are clickable here too) |
| Dataset Stats bar charts | ✅ (Gradio BarPlot) | ✅ (Chart.js) |

Nothing was cut — this is a genuine 1:1 port, not a simplified version.

## Running it locally

Browsers block `fetch()` of local files under a bare `file://` URL (CORS),
so you need a tiny local server — no build step, no npm install required:

```bash
cd webapp
python3 -m http.server 8080
```

Then open `http://127.0.0.1:8080` in your browser.

## Updating the dataset

Whenever you re-run the main pipeline (`python run.py` from the project
root), copy the refreshed files in before redeploying:

```bash
cp ../data/entities.json ./data/entities.json
cp ../data/relationships.json ./data/relationships.json
```

## Deploying

See [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) for full step-by-step
instructions for both a Hugging Face **Static Space** (free) and **GitHub
Pages** (also free, and you likely already have the GitHub repo set up).

## Design notes

- No framework, no build step, no bundler — just three files plus a
  vendored chart library. This keeps the "static site" claim honest: there
  is nothing here that requires `npm install` or a compile step to deploy.
- Chart.js is vendored locally (`vendor/chart.umd.js`) rather than loaded
  from a CDN. This was a deliberate fix, not just a preference: an earlier
  CDN-based version would take down the *entire app* (not just the charts)
  if the CDN was slow, blocked by an ad-blocker, or unreachable — because
  the resulting `ReferenceError` propagated up through the app's
  initialization sequence. `setupStatsTab()` now also checks for Chart's
  existence and degrades gracefully (showing a plain message instead of a
  chart) if it's ever missing, so a charting failure can never break
  search, filtering, or the relationship explorer.
- All text inserted into the DOM goes through `escapeHtml()` /
  `escapeAttr()` — entity names, descriptions, and URLs are ultimately
  sourced from external APIs (GitHub, Hugging Face, RSS feeds), so they're
  treated as untrusted strings when building HTML, to avoid any
  script-injection risk from upstream data.
