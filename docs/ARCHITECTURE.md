# Architecture

This document goes deeper than the README on *why* the pipeline is built the
way it is. If the README is the map, this is the terrain.

---

## 1. Design goals, in priority order

1. **Never hallucinate.** Every record must trace back to a real API
   response or a real fetched page. This constraint shaped almost every
   other decision below — it's why extraction is separated from judgment,
   why every entity carries a `source`, and why missing optional fields are
   left `null` instead of guessed.
2. **Modularity over cleverness.** Each pipeline stage should be
   independently understandable, testable, and replaceable without
   touching its neighbors.
3. **Determinism and idempotency.** Running the pipeline twice on the same
   input should produce the same entity IDs and the same relationships —
   important for any real system that re-ingests periodically.
4. **Auditability.** Every inferred relationship carries the evidence that
   produced it. A graph you can't explain isn't trustworthy.
5. **Graceful degradation over hard failure.** A rate-limited API, a dead
   RSS feed, or a malformed record should degrade the *quality* of one
   run, not crash the whole pipeline.

---

## 2. Stage-by-stage design

```
Discovery → Extraction → Cleaning → Normalization → Entity Resolution
→ Classification → Relationship Mapping → Validation → Output
```

### 2.1 Discovery (`src/discovery/seeds.py`)

Pure data — no logic. A list of GitHub topic queries, Hugging Face search
terms, YouTube search strings, RSS feed URLs, and official site URLs, each
tagged with a `category_hint`. The reasoning: *what* to look for changes
far more often than *how* to look for it. Keeping this declarative means
adding coverage (a new GitHub topic, a new RSS feed) never touches
extractor code, and a non-engineer could plausibly review or edit this
file.

### 2.2 Extraction (`src/extractors/`)

One module per source. Each module has exactly two public functions:

- `extract_X(...)` — calls the real API/feed, returns raw dicts as close
  to the source's native shape as possible (GitHub's repo JSON, HF's
  model JSON, etc.), each annotated with a `_category_hint`.
- `raw_X_to_entity_dict(raw)` — maps that native shape into the
  intermediate "pre-entity" dict shape that normalization expects
  (`entity_type`, `name`, `description_raw`, `url`, `categories`,
  `source_name`, `source_url`, plus source-specific extra keys).

Extraction is deliberately "dumb": it does not sanitize text, resolve
duplicates, or decide final categories. That keeps each extractor small and
means a bug in, say, entity resolution can never accidentally live inside
an extractor where it'd be harder to find.

**Resilience pattern used by every extractor:** live API call wrapped in
`retry_with_backoff` → on exhausted retries, log and either skip that
source (GitHub, YouTube, sites) or fall back to a cached JSON file under
`data/raw/` populated with real, previously-fetched data (Hugging Face,
YouTube, RSS, sites). This is not a workaround for missing data — it's a
deliberate reproducibility feature: a pipeline that only works when every
API is up and every key is present is not production-grade.

### 2.3 Cleaning (`src/cleaning/text_sanitizer.py`)

Three composable functions — `strip_html`, `clean_markdown_noise`,
`normalize_whitespace` — composed into `sanitize_description()`. Kept
separate from normalization because cleaning is about *text hygiene*
(removing HTML tags, badges, excess whitespace) while normalization is
about *identity* (what makes two records the same or comparable).

### 2.4 Normalization (`src/normalization/`)

Two responsibilities:

- `url_normalizer.py` — makes two URLs that point at the same resource
  compare equal: strips tracking params, forces `https` on hosts known to
  redirect, drops trailing slashes and fragments, sorts remaining query
  params.
- `entity_builder.py` — the single choke point where a raw pre-entity dict
  becomes a validated `Entity`. This is where deterministic IDs are
  generated, specialized metadata sub-objects are attached based on
  `entity_type`, and records missing a name or URL are dropped (logged,
  not silently discarded).

**Why IDs are `uuid5(NAMESPACE, f"{entity_type}::{normalized_url}")`:**
this makes ID generation a pure function of content. Re-run the pipeline
next week and an unchanged GitHub repo gets the *same* ID it got today —
which is what makes downstream deduplication and relationship mapping
idempotent instead of accumulating duplicate edges on every run.

### 2.5 Entity Resolution (`src/entity_resolution/resolver.py`)

See the README for the three-pass algorithm (URL → canonical name → fuzzy
name). The architectural point worth calling out here: **resolution scope
is always within the same `entity_type`.** A Company named "Anthropic" and
a Model with "anthropic" somewhere in its provider string are never
compared against each other for deduplication purposes — they're different
kinds of things, and conflating them would be a correctness bug, not a
feature. Cross-type connections are relationship mapping's job, not
resolution's.

### 2.6 Classification (`src/classification/classifier.py`)

Rule-based, not ML-based — a deliberate choice given the priority list
above. Every category assignment is one of: (a) the entity's base type
mapped directly ("Model" always gets "Models"), (b) a word-boundary keyword
match against name+description (e.g. "assistant" → "Personal"), or (c) a
recency flag from normalization. All three are inspectable in a few lines
of code, which matters more than marginal accuracy gains from a
classifier that would need training data we don't have and couldn't
explain its decisions.

### 2.7 Relationship Mapping (`src/relationships/relationship_mapper.py`)

The most heuristic-heavy stage, by necessity: none of our sources expose
relationships as structured data. See the README for the current rule
table. Two design choices worth flagging:

- **Every relationship has a confidence score**, deliberately capped below
  1.0 for anything text-inferred (0.55–0.95 depending on rule strength).
  Structural signals (a model's `provider` field naming a company exactly)
  get higher confidence than free-text mentions.
- **Deduplication by deterministic relationship ID**
  (`uuid5(source_id, predicate, target_id)`) means if two different rules
  both infer "Company X develops Repo Y", the higher-confidence one wins
  rather than creating two edges — the pipeline is idempotent here too.

### 2.8 Validation (`src/validation/validator.py`)

The last gate: drops entities with duplicate IDs (would indicate a
resolver bug) or missing required fields, drops relationships whose
`source_id`/`target_id` don't exist in the final entity set (orphan edges
from entities that got dropped upstream), and produces the quality report
consumed by both `run.py`'s stdout and the demo app's stat cards.

---

## 3. Data model

### 3.1 Why pydantic, not raw dicts

Every stage after extraction operates on `Entity`/`Relationship` pydantic
models, not dicts. This buys three things a dict pipeline doesn't get for
free: validation at construction time (a malformed record fails loudly at
the point it's created, not three stages later when something crashes on
a missing key), IDE/type-checker support across the whole codebase, and a
single source of truth for "what fields exist" that both the pipeline and
the demo app can rely on.

### 3.2 Specialized metadata as typed sub-objects

`model_metadata`, `repository_metadata`, `mcp_metadata`,
`company_metadata`, `video_metadata`, `news_metadata` are each their own
pydantic model, attached to `Entity` as optional fields. The alternative —
a single loose `metadata: dict` — was rejected because it pushes all
validation to consumers and makes "what fields does a Model entity have"
an exercise in reading extractor code rather than reading the schema.

---

## 4. The demo app's architecture

`app/app.py` is intentionally a single file with no server-side state
beyond what's loaded at import time from the two JSON files. This is a
deliberate constraint for Hugging Face Spaces deployment: no database, no
background jobs, no external API calls at request time — the entire app is
a read-only view over a static snapshot, which means it's fast, has no
moving parts to break in production, and costs nothing to run beyond the
free CPU tier.

The one piece of app-side computation that isn't just filtering — the
per-entity connection count (`_CONNECTION_COUNTS`) — is computed once at
import time from the relationships file, not recomputed per request.

---

## 5. What would change for a "real" production version

Worth naming honestly, since this was built as a scoped deliverable:

- **Scheduled re-ingestion.** Right now `run.py` is invoked manually. A
  production version would run on a schedule (cron/Airflow/similar),
  writing to a database instead of flat JSON files, with the demo app
  reading from that database instead of static files.
- **Relationship inference via embeddings.** Text-mention matching is
  precise but low-recall. A production version could add a semantic layer
  (embedding similarity between entity descriptions) as an additional,
  separately-confidence-scored signal — kept alongside the rule-based
  signals, not replacing them, since explainability still matters.
- **Incremental updates.** Currently every run re-extracts everything.
  Deterministic IDs already make this idempotent, but a production
  pipeline would want to track "last seen" per source and only pull deltas
  to respect API rate limits at scale.
- **A real task graph, not a static taxonomy snapshot.** The Task
  taxonomy is versioned but static; a production system might periodically
  re-fetch/re-diff it against Hugging Face's published task list.
