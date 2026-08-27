# Development Journey: Challenges & Decisions

A record of what actually happened building this — the problems that came
up, how they were diagnosed, and why each fix was made the way it was.
Written for whoever reviews this project (and for future-me re-reading it
in six months).

---

## Challenge 1: Network egress restrictions during development

**The problem:** the development sandbox could reach `api.github.com`
live, but not `huggingface.co`, YouTube's API, or RSS endpoints directly.
A pipeline that only works when every source is reachable isn't
production-grade, and silently faking data to work around it would violate
the project's core rule (never hallucinate).

**The decision:** write fully working, production-ready extractor code for
every source — the code a user with open network and API keys would run —
and *separately* populate `data/raw/*_cache.json` with real data fetched
through other available tooling (web search/fetch), used only as a
fallback when the live call fails. This became a legitimate resilience
feature rather than a workaround: every extractor now degrades gracefully
from "live API" → "cached real data" → "skip this source, log it, keep
going," which is exactly the behavior you'd want in production when an API
has an outage.

**What this means for you as the user:** with your own network and API
keys, every source hits its real live API. The cache files exist purely as
a fallback safety net — you will rarely, if ever, see them used once you
have `GITHUB_TOKEN` and `YOUTUBE_API_KEY` set.

---

## Challenge 2: Landing in the 250–300 record target range

GitHub's live search API returns different result counts run to run
(trending repos shift, and the endpoint occasionally rate-limits mid-run).
Early full runs produced anywhere from 246 to 315 records depending on
timing. Rather than hard-coding a record cap (which would silently drop
real, valid data) or padding with placeholder records (which would violate
the never-hallucinate rule), the fix was to tune `--max-per-query` — how
many records to request *per query/topic/feed*, not a global cap — so the
typical run lands in range while every record returned is still real. The
default (`13`) was chosen empirically after several live runs; it's a CLI
flag specifically so this can be adjusted without touching code.

---

## Challenge 3: The Relationship Explorer looked broken (user-reported)

This was the most instructive bug in the project, so it's worth recording
in detail.

**Symptom:** after a real deployment with a live `YOUTUBE_API_KEY` and open
network (371 real entities, 63 real YouTube videos), selecting almost any
entity in the Relationship Explorer showed "0 relationships found."

**Diagnosis, step by step:**

1. First check: was this a UI bug (wrong entity being looked up) or a data
   bug (the entity genuinely has no relationships)? Counting entities with
   at least one relationship in the shipped dataset showed only 45 of 261
   — meaning most entities genuinely had zero relationships. Not a UI bug;
   a data density problem.
2. Second observation: the user's stats page showed only **7 entity
   types**, when the schema supports 9 (including Tool and Collection).
   Tracing this down: `huggingface_extractor.py`'s live code path only
   ever called `/api/models`. The Tool/Collection entities that existed in
   my test dataset came from Hugging Face *Spaces*, which only appeared in
   the offline cache fixture — never from a live call. So a fully
   successful live run (exactly what the user had) would always produce
   zero Tool/Collection entities. **This was a real functional gap, not
   just a display issue** — the live extractor was incomplete relative to
   what the cache implied it could do.
3. Third observation: even accounting for that gap, the relationship rules
   themselves were tuned against a small, hand-picked sample of ~14 videos
   and ~23 models. Against a much larger, more linguistically diverse real
   dataset, the plain-substring text matching rules had low recall — a
   video titled "Build Your First AI Agent in 13 Minutes" simply doesn't
   contain the exact string of any of the (at the time) 2 known Tool
   entity names.

**The fix, in order of impact:**

- Added a real, live `/api/spaces` call to the Hugging Face extractor, so
  Tool/Collection coverage now comes from live data on every run.
- Added five new relationship rules (Video→Company, Video→Model,
  Video→Repository/MCP, broader Repository/MCP→Company text mentions) and
  a GitHub-topics-based Task-matching rule, which is a much cleaner signal
  than free-text mentions since topics are structured metadata, not prose.
- Switched every text-matching rule to word-boundary regex matching
  (`_mentions()` helper) for both precision and consistency — previously
  some rules used plain substring `in` checks, which is both less precise
  and inconsistent across rules.
- This roughly doubled relationship coverage in testing (45/261 → 81/271
  entities connected).

**The part that isn't "fixable" and had to be designed around instead:**
a relationship graph built from real-world text co-occurrence will always
be sparse — most entities in any real dataset like this simply never get
mentioned by name in another entity's text. That's not a bug, it's the
nature of the signal. So alongside the data-layer fixes, the app itself
changed: the entity picker in the Relationship Explorer is now sorted by
connection count (most-connected first) and defaults to a well-connected
entity, and picking an unconnected one now shows an explanation plus
suggested alternatives instead of a bare "0 found" table. **Both the data
fix and the UX fix were necessary — fixing only the data would still leave
most entities sparse (that's inherent), and fixing only the UX without the
data fix would have shipped a nicer wrapper around a real coverage gap
(the missing Tool/Collection types).**

---

## Challenge 4: Precision vs. recall in text-based classification

Early keyword-based classification used plain substring matching (`"chat"
in description.lower()`), which caused false positives — e.g. "ChatGPT"
contains "chat" as a substring, incorrectly tagging unrelated tools as
"Personal" category. Fixed by switching to word-boundary regex matching
(`\bchat\b`) throughout the classifier and, later, the relationship
mapper. This is a small fix but a good example of a general lesson: cheap
string-matching heuristics need boundary-awareness from the start, or they
silently over-trigger in ways that are easy to miss during small-scale
testing and only surface at real scale.

---

## Challenge 5: Entity resolution missing hyphenated organization names

GitHub organizations often use hyphenated slugs (`deepseek-ai`,
`black-forest-labs`) while the corresponding company's canonical name is
space-separated (`DeepSeek`, `Black Forest Labs`). The original
`canonicalize_name()` stripped punctuation but didn't convert hyphens to
spaces first, so `"deepseek-ai"` canonicalized to `"deepseekai"` — which
doesn't match `"deepseek"` and doesn't get caught by the corporate-suffix
stripper either (the suffix pattern expects a space-separated `" ai"`, not
a fused `"ai"`). Fixed by normalizing hyphens/underscores to spaces *before*
suffix-stripping, so `"deepseek-ai"` → `"deepseek ai"` → suffix-stripped to
`"deepseek"`, correctly matching the company. This directly improved the
Company→Model and Company→Repository relationship counts.

---

## Challenge 6: Rate limiting looked like a pipeline bug

During iterative testing, repeated pipeline runs in quick succession
started returning noticeably fewer GitHub records, which initially looked
like a regression. Checking GitHub's rate-limit endpoint
(`api.github.com/rate_limit`) revealed the real cause: the *search* API
specifically is capped at 10 requests/minute unauthenticated (separate
from and much tighter than the general API's 60/hour), and the pipeline
was making ~18 search calls per run with only a 1-second delay between
them. This wasn't documented anywhere obvious and easy to miss. Fixed by
increasing the inter-query delay and correcting the rate-limit
documentation in the README and `.env.example`, which previously
(incorrectly) stated the general API's 60/hour limit.

---

## Challenge 7: Hugging Face requiring a paid plan to create Gradio Spaces

The original plan (and the project spec) called for a Hugging Face Space
running the Gradio app. Partway through deployment, it turned out Hugging
Face now requires a **paid PRO plan** just to *create* a Gradio or Docker
Space — the CPU Basic hardware itself is still free once created, but
Space creation itself is gated to paid accounts. Only Static Spaces (plain
HTML/CSS/JS, no Python backend) remain free to create for everyone.

**The decision:** rather than asking for a paid upgrade or dropping the
public-demo requirement, the app was rebuilt as `webapp/` — a genuine 1:1
port of `app/app.py`'s functionality into vanilla HTML/CSS/JS. This was
viable specifically because the app's actual runtime logic is simple
(filter and display two pre-generated JSON files); nothing about it
required a Python backend — Gradio was just the framework used to build
the first version quickly. The static rebuild deploys free to both a
Hugging Face Static Space and GitHub Pages, and needed no changes to the
pipeline or the underlying dataset — only the presentation layer changed.

**A bug this surfaced along the way:** the first static build loaded
Chart.js from a CDN (`cdnjs.cloudflare.com`). During testing in a
network-restricted environment, that request was blocked — which exposed
a real bug, not just a testing inconvenience: the resulting
`ReferenceError` propagated up through the app's initialization sequence
and crashed the *entire* app, not just the Dataset Stats tab. Any visitor
with an ad-blocker or a restrictive corporate network would have hit the
same failure in production. Fixed two ways: Chart.js is now vendored
locally (`webapp/vendor/chart.umd.js`, no CDN dependency at all), and
`setupStatsTab()` independently checks for Chart's availability and
degrades to a plain text message if it's ever missing, so a charting
failure can no longer take down search, filtering, or the relationship
explorer. This was caught by an automated headless-browser test
(Playwright) run against the static build before shipping it — worth
noting as a case where testing the actual rendered page, not just checking
JS syntax, caught a defect that code review alone likely would have
missed.

**What actually got deployed:** rather than switching to the static
build, the Gradio app ended up deployed on **Render's** free tier instead
— Render runs Python web services on a free plan with no payment gate,
unlike Hugging Face's Gradio Spaces. This meant zero code changes beyond
wiring `demo.launch()` to Render's expected host (`0.0.0.0`) and dynamic
`PORT` environment variable. The static `webapp/` build still exists in
the repo as a free, zero-server alternative (and remains the right choice
if Render's cold-start delay on the free tier — 30–60 seconds after
inactivity — is undesirable), but wasn't the path actually used for the
live demo.

---

## Design decisions that turned out to matter more than expected

- **Deterministic UUIDs** (`uuid5` from entity_type + normalized URL) —
  seemed like a minor detail early on, but turned out to be what made
  every later stage idempotent for free: re-running dedup, classification,
  or relationship mapping never produces drift or duplicate edges, because
  the same input always produces the same IDs.
- **Confidence scores on every relationship** — added early somewhat
  defensively ("this seems like good practice"), but became essential once
  the relationship count grew: when two independent rules infer the same
  edge, confidence is what lets deduplication pick the better-evidenced
  one instead of arbitrarily keeping whichever ran last.
- **Keeping extraction "dumb"** — resisted the temptation to have
  extractors do a bit of cleaning/classification inline "since they're
  already touching the data." Every time a bug showed up, isolating it to
  one specific stage (usually relationship mapping or classification) was
  fast precisely because extractors never contained that kind of logic.