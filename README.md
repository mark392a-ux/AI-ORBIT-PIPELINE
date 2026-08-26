# AI Orbit — Data Ingestion Pipeline

A modular, API-first pipeline that aggregates, cleans, normalizes, deduplicates,
classifies, and cross-links real data from across the AI ecosystem into a single
structured dataset — plus a Gradio app to browse it.

**Current output:** 271 entities · 79 relationships · 6 sources · 14 categories.
(Numbers vary between runs since GitHub's live search results — and how many
records survive deduplication — change run to run; typically lands in the
250–300 range spec'd above with the default settings.)

```
data/entities.json         # every entity, common schema + specialized metadata
data/relationships.json    # typed, directed, evidence-backed edges between entities
data/quality_report.json   # coverage breakdown by type / category / source
```

**Further reading:**
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — deep dive into design
  decisions behind every stage, the data model, and what a production
  version would add.
- [`docs/CHALLENGES_AND_DECISIONS.md`](docs/CHALLENGES_AND_DECISIONS.md) —
  the actual problems hit during development (network restrictions, sparse
  relationship graphs, rate limiting, entity-resolution edge cases) and how
  each was diagnosed and fixed.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — step-by-step instructions
  for pushing this to GitHub and deploying the demo app to Hugging Face
  Spaces.

---

## 1. Quick start

```bash
git clone <this-repo>
cd ai-orbit-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and add whichever API keys you have — see section 4

python run.py                       # full pipeline, all sources
python run.py --sources github      # just one source
python run.py --max-per-query 10    # smaller/faster run

python app/app.py                   # launch the browsing UI locally
```

No API key is strictly required to get a first result: GitHub search works
unauthenticated (rate-limited), and every other source falls back to real,
previously-fetched data cached under `data/raw/` if its live API is
unavailable (see section 5 — this is a deliberate resilience feature, not a
workaround).

---

## 2. Architecture

```
Discovery → Extraction → Cleaning → Normalization → Entity Resolution
→ Classification → Relationship Mapping → Validation → Output
```

```
src/
├── schemas/            Entity & Relationship pydantic models (the contract
│                        every other stage reads/writes)
├── discovery/           Declarative seed lists — what to query each source
│                        for. Adding coverage = editing a list, not code.
├── extractors/           One module per source (github, huggingface, youtube,
│                        rss, sites, tasks). Each returns raw dicts + a
│                        raw_X_to_entity_dict() mapper to the common shape.
├── cleaning/            HTML/markdown/whitespace sanitization for text
│                        pulled from APIs, RSS, and web pages.
├── normalization/        URL normalization + entity_builder.py, which turns
│                        a raw pre-entity dict into a validated Entity.
├── entity_resolution/   Canonicalization + 3-pass deduplication (see §3).
├── classification/       Rule-based category tagging.
├── relationships/        Heuristic relationship inference engine (see §3).
├── validation/           Final integrity checks + the quality report.
└── utils/                Config loading, logging, retry/backoff.
```

Each stage only depends on the pydantic models in `schemas/` and the output
of the previous stage — no stage reaches back into another's internals. That
means, for example, adding a seventh data source only requires a new file in
`extractors/` and a few lines in `run.py`; nothing else changes.

### Why this stage order

Extraction is deliberately kept "dumb" (get raw records, tag with a category
hint) so that all the judgment calls — what counts as a duplicate, which
category something really belongs to, whether two things are related — live
in their own auditable stages, each independently testable and independently
tunable.

---

## 3. How entity resolution and relationship mapping work

### Entity resolution (`src/entity_resolution/resolver.py`)

Three passes, cheapest/highest-confidence first:

1. **Exact URL match** (after normalization — see `url_normalizer.py`, which
   strips tracking params, forces `https`, drops trailing slashes/fragments).
   Two records with the same normalized URL are the same entity, full stop.
2. **Exact canonical-name match**, within the same `entity_type`.
   `canonicalize_name()` lowercases, turns `-`/`_` into spaces, and strips
   common corporate suffixes (`inc`, `llc`, `labs`, `ai`, …) — so `"OpenAI"`,
   `"open-ai"`, and `"OpenAI, Inc."` all collapse to the same key.
3. **Fuzzy name match** (`rapidfuzz.fuzz.token_sort_ratio`, threshold 92),
   still scoped to the same `entity_type`, to catch near-misses that survive
   passes 1–2 without false-merging genuinely distinct entities.

When two records are judged the same, `_merge()` combines them: the
higher-authority source (official site > GitHub/HF APIs > YouTube > RSS)
wins on scalar fields, but categories and specialized metadata are **unioned**
so information from the lower-authority source isn't thrown away.

### Relationship mapping (`src/relationships/relationship_mapper.py`)

Sources rarely state relationships in structured form, so this stage infers
them from signals available after resolution:

| Rule | Signal used |
|---|---|
| Company → provides → Model | Model's `provider` field matches a company's canonical name |
| Company → develops → Repository/MCP | GitHub `owner/repo` prefix matches (exact or substring) a company name |
| Repository → implements → Model | Repo name/description text mentions a known model's short name |
| MCP → integrates_with → Tool | MCP server text mentions a known tool's name |
| Device/Robot → runs → Model | Device/robot text mentions a known model's name |
| News → mentions → Company / Model | News text mentions a known company or model name |
| Video → demonstrates → Tool | Video title/description mentions a known tool name |
| Tool/Repo → solves → Task | Text mentions a canonical task name (e.g. "text-to-image") |
| Model → solves → Task | Model's pipeline-tag/modality matches a task name exactly |

Every relationship carries a `confidence` (0–1) and an `evidence` string
explaining *why* the edge exists — visible in the app's Relationship
Explorer tab — because an inferred graph without provenance isn't
trustworthy. Relationships are deduplicated by a deterministic ID
(`UUID5(source_id, predicate, target_id)`), so re-running the pipeline never
produces duplicate edges, and if the same pair is inferred by two rules, the
higher-confidence one wins.

This is intentionally rule-based rather than ML-based: it's deterministic,
fast, free, and every inference is explainable — appropriate for a pipeline
whose output has to be auditable.

---

## 4. Sources & how each one is queried

| Source | Method | Auth needed? |
|---|---|---|
| GitHub | REST Search API (`/search/repositories`, topic + star-count queries) | Optional (`GITHUB_TOKEN`) — the search endpoint is capped at 10 req/min unauthenticated, 30 req/min with a token |
| Hugging Face | Hub REST API (`/api/models` for Models, `/api/spaces` for Tools/Collections) | Optional (`HUGGINGFACE_TOKEN`) |
| YouTube | Data API v3 (`search.list`) | Required (`YOUTUBE_API_KEY`) |
| News | Publisher RSS feeds (`feedparser`) | None |
| Official sites | Single `<meta description>` fetch per curated company site | None |
| Tasks | Hugging Face's published task taxonomy (curated, versioned list — see below) | None |

All of these are genuinely API-first: nothing is scraped by parsing rendered
HTML search-results pages, and the "official sites" extractor deliberately
reads one `<meta>` tag rather than crawling.

**A note on the Task source:** Hugging Face doesn't expose a "list all
tasks" REST endpoint — its task taxonomy is a documentation surface, not an
API. `src/extractors/task_extractor.py` therefore ships a curated,
versioned list (`data/raw/tasks_taxonomy.json`) of HF's own canonical task
names, each linking to its real `huggingface.co/tasks/...` page. This is the
one place the pipeline uses a static list instead of a live call, and it's
called out explicitly rather than disguised as something else.

---

## 5. Resilience & graceful degradation

Every extractor is wrapped so that a single source failing doesn't take down
the run:

- **Retries with exponential backoff + jitter** on transient HTTP failures
  (`src/utils/retry.py`), with a hard cap so a persistently-broken API
  fails loudly (logged) rather than hanging forever.
- **Per-source isolation** in `run.py` — each source's extraction is in its
  own `try/except`; one failing source just means fewer records from it,
  not a crashed pipeline.
- **Cache fallback**: `huggingface_extractor.py`, `youtube_extractor.py`,
  `rss_extractor.py`, and `sites_extractor.py` all fall back to a local
  `data/raw/*_cache.json` file — populated with real, previously-fetched
  API/page data, never invented — if the live call fails. This matters
  concretely in network-restricted environments (e.g. this pipeline was
  partly developed in a sandbox that could reach `api.github.com` but not
  `huggingface.co` directly) and means the pipeline is reproducible even
  without every API key or open network egress.
- **Field-level, not record-level, failure**: `entity_builder.py` drops and
  logs individual malformed records (e.g. missing name/URL) rather than
  failing the whole batch.

All logs go to both stdout and `logs/pipeline.log`.

---

## 6. Data schema

Every entity follows the common schema from the spec:

```json
{
  "id": "stable UUID5, deterministic across runs",
  "entity_type": "Tool | Task | Company | News | Video | Robot | Device | Model | Repository | MCP | Collection | Personal | Creative",
  "name": "string",
  "description": "string (sanitized, ≤600 chars)",
  "url": "string (normalized)",
  "categories": ["string", "..."],
  "source": { "name": "string", "url": "string" }
}
```

IDs are `uuid5(NAMESPACE, f"{entity_type}::{normalized_url}")` — running the
pipeline twice on unchanged input produces byte-identical entity IDs, which
is what makes the merge/dedup/relationship logic idempotent.

Specialized metadata is attached as typed sub-objects (only populated where
relevant): `model_metadata`, `repository_metadata`, `mcp_metadata`,
`company_metadata`, `video_metadata`, `news_metadata` — see
`src/schemas/entity.py` for exact fields.

---

## 7. The demo app

`app/app.py` is a single-file Gradio app with a "mission control" visual
identity (dark space palette, teal accent, monospace stat readouts) and
three tabs:

- **Browse & Search** — free-text search + category/type filters over a live
  table (now showing each entity's relationship count); click a row for full
  entity detail including specialized metadata.
- **Relationship Explorer** — pick any entity, see every incoming and
  outgoing relationship with its confidence score and evidence string.
  The entity picker is sorted by connection count (most-connected first)
  and defaults to a well-connected hub, because relationship graphs built
  from real text-mention evidence are inherently sparse — most entities
  have few or no detected links, and picking one at random used to make
  the tab look broken. If you do land on an unconnected entity, the app
  now shows a clear explanation and points you at well-connected
  alternatives instead of a blank table.
- **Dataset Stats** — real bar charts (not just tables) for entities by
  type, by source, and relationships by predicate, plus stat cards up top.

It reads only the static `data/entities.json` / `data/relationships.json` —
no external API calls at request time, no login, and it's fast even on
Spaces' free CPU tier.

### Why the Relationship Explorer looked empty, and what changed

Two real issues surfaced after a live run with a full `YOUTUBE_API_KEY` and
open network access (thank you for the bug report):

1. **Hugging Face Spaces were only ever coming from the offline cache.**
   The live Hub API call only ever hit `/api/models`, so a successful live
   run produced zero `Tool`/`Collection` entities — those types only
   existed in the `data/raw/huggingface_cache.json` fixture used for
   fallback. `huggingface_extractor.py` now also calls the real
   `/api/spaces` endpoint live, so Tool/Collection coverage is populated
   from real data on every run, not just the offline fallback.
2. **Relationship rules were tuned against a small, hand-curated sample**
   and used plain substring matching. Against a large, diverse live
   dataset (371 real entities), the rules were too narrow: only ~45/261
   entities had any detected relationship at all. `relationship_mapper.py`
   now uses word-boundary matching throughout (more precise **and** more
   consistent), adds Video→Company, Video→Model, Video→Repository/MCP, and
   broader Repository/MCP→Company text-mention rules, and matches Tasks
   against GitHub topics directly (a much cleaner signal than free-text
   mentions). This roughly doubled relationship coverage in testing.

Relationship graphs inferred purely from text co-occurrence will always be
sparse — that's inherent to the method, not a bug — so the app itself was
also changed to make that sparsity legible instead of confusing (see above).

---

## 8. Deploying to GitHub & Hugging Face Spaces

Full step-by-step instructions (including a Space README template, a
troubleshooting section, and how to refresh the live dataset later) live in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Short version: push this
project to a GitHub repo as-is; for the Hugging Face Space, create a
separate Space repo with the Gradio SDK, copy `app/app.py` to its root
(adjusting one `DATA_DIR` path), copy `data/entities.json` and
`data/relationships.json` alongside it, copy `requirements.txt`, and push.

---

## 9. Regenerating the dataset

```bash
python run.py --sources github huggingface youtube rss sites tasks --max-per-query 13
```

`--max-per-query` controls how many records are pulled per query/topic/feed;
13 (the default) was tuned to land the total in the 250–300 record range the
spec asks for. Lower it for a faster smoke-test run, raise it for a larger
dataset.

---

## 10. Known limitations

- Relationship inference is text/keyword-based, not semantic — it will miss
  relationships that aren't stated in the entities' own name/description
  text, and confidence scores reflect that (nothing above 0.95).
- `founding_year`, `headquarters`, and `employee_range` on Company entities
  are left `null` rather than filled with unverified guesses — the "never
  hallucinate" rule takes priority over schema completeness.
- YouTube extraction requires an API key; without one it falls back to the
  cached sample in `data/raw/youtube_cache.json`.
