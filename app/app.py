"""
AI Orbit — Ecosystem Explorer
==============================
Gradio demo app for Hugging Face Spaces. Loads the pipeline's output
(data/entities.json, data/relationships.json) and provides:

  - Summary stat cards (total entities, relationships, sources, categories)
  - Category filter + free-text search
  - Entity detail view with source URL and specialized metadata
  - A relationship explorer: pick an entity, see everything connected to it,
    ranked so the well-connected "hub" entities are easy to find first
  - Dataset stats with real bar charts

No login required; runs entirely off the static JSON produced by run.py,
so the Space stays fast and has no external API dependency at request time.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import gradio as gr
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Visual identity
# ---------------------------------------------------------------------------
# "Mission control" palette: deep space background, signal-teal accent for
# data/links, amber reserved for "new/attention" badges. Deliberately not
# the default purple/indigo Gradio theme, and not a generic light UI —
# this is meant to feel like a console for exploring a live dataset.

ORBIT_CSS = """
:root {
    --orbit-bg: #0B0E17;
    --orbit-surface: #141926;
    --orbit-surface-2: #1B2233;
    --orbit-border: #262E42;
    --orbit-text: #E8EAF2;
    --orbit-text-dim: #8B92A8;
    --orbit-accent: #4FD1C5;
    --orbit-accent-dark: #0F3D38;
    --orbit-amber: #F5A623;
}

.gradio-container {
    background: var(--orbit-bg) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* --- Stat card grid --- */
.orbit-stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: 4px 0 20px 0;
}
.orbit-stat-card {
    background: var(--orbit-surface);
    border: 1px solid var(--orbit-border);
    border-radius: 10px;
    padding: 14px 18px;
}
.orbit-stat-label {
    font-size: 12px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--orbit-text-dim);
    margin-bottom: 6px;
}
.orbit-stat-value {
    font-family: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 26px;
    font-weight: 600;
    color: var(--orbit-accent);
    line-height: 1.1;
}

/* --- Header --- */
.orbit-header {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 2px;
}
.orbit-title {
    font-size: 26px;
    font-weight: 700;
    color: var(--orbit-text);
}
.orbit-tagline {
    color: var(--orbit-text-dim);
    font-size: 14px;
    margin-bottom: 18px;
}

/* --- Empty state / hint box --- */
.orbit-empty-state {
    background: var(--orbit-surface);
    border: 1px dashed var(--orbit-border);
    border-radius: 10px;
    padding: 18px 20px;
    color: var(--orbit-text-dim);
    font-size: 14px;
    line-height: 1.6;
}
.orbit-empty-state b { color: var(--orbit-text); }

/* --- Connection badge inline in markdown --- */
.orbit-badge {
    display: inline-block;
    background: var(--orbit-accent-dark);
    color: var(--orbit-accent);
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    margin-left: 8px;
}
"""

ORBIT_THEME = gr.themes.Base(
    primary_hue="teal",
    secondary_hue="amber",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(
    body_background_fill="#0B0E17",
    body_background_fill_dark="#0B0E17",
    block_background_fill="#141926",
    block_background_fill_dark="#141926",
    block_border_color="#262E42",
    block_border_color_dark="#262E42",
    border_color_primary="#262E42",
    border_color_primary_dark="#262E42",
    body_text_color="#E8EAF2",
    body_text_color_dark="#E8EAF2",
    body_text_color_subdued="#8B92A8",
    body_text_color_subdued_dark="#8B92A8",
    input_background_fill="#1B2233",
    input_background_fill_dark="#1B2233",
    button_primary_background_fill="#4FD1C5",
    button_primary_background_fill_hover="#3FBAAE",
    button_primary_text_color="#0B0E17",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data():
    with open(DATA_DIR / "entities.json", "r", encoding="utf-8") as f:
        entities = json.load(f)
    with open(DATA_DIR / "relationships.json", "r", encoding="utf-8") as f:
        relationships = json.load(f)
    return entities, relationships


ENTITIES, RELATIONSHIPS = load_data()
ENTITY_BY_ID = {e["id"]: e for e in ENTITIES}

ALL_CATEGORIES = sorted({c for e in ENTITIES for c in e["categories"]})
ALL_TYPES = sorted({e["entity_type"] for e in ENTITIES})

# Connection count per entity — the single fact that makes the Relationship
# Explorer usable. Without this, picking a random entity out of hundreds
# almost always lands on one with zero links (most real-world graphs are
# sparse — a handful of hubs carry most of the connections).
_CONNECTION_COUNTS: Counter = Counter()
for r in RELATIONSHIPS:
    _CONNECTION_COUNTS[r["source_id"]] += 1
    _CONNECTION_COUNTS[r["target_id"]] += 1


def _entity_label(e: dict) -> str:
    count = _CONNECTION_COUNTS.get(e["id"], 0)
    suffix = f" — {count} link{'s' if count != 1 else ''}" if count else " — no links yet"
    return f"{e['name']} ({e['entity_type']}){suffix}"


# Sorted so well-connected entities surface first in the dropdown — the
# entities most worth exploring are no longer buried among hundreds of
# isolated ones.
ENTITY_CHOICES = sorted(
    ((_entity_label(e), e["id"]) for e in ENTITIES),
    key=lambda pair: -_CONNECTION_COUNTS.get(pair[1], 0),
)
LABEL_TO_ID = dict(ENTITY_CHOICES)

TOP_CONNECTED = [
    ENTITY_BY_ID[eid] for eid, _ in _CONNECTION_COUNTS.most_common(8)
]
DEFAULT_ENTITY_LABEL = ENTITY_CHOICES[0][0] if ENTITY_CHOICES else None


# ---------------------------------------------------------------------------
# Stat cards (header)
# ---------------------------------------------------------------------------

def build_stat_cards_html() -> str:
    connected = len(_CONNECTION_COUNTS)
    cards = [
        ("Total entities", f"{len(ENTITIES):,}"),
        ("Relationships", f"{len(RELATIONSHIPS):,}"),
        ("Entity types", str(len(ALL_TYPES))),
        ("Categories", str(len(ALL_CATEGORIES))),
        ("Connected entities", f"{connected:,}"),
    ]
    cards_html = "".join(
        f'<div class="orbit-stat-card"><div class="orbit-stat-label">{label}</div>'
        f'<div class="orbit-stat-value">{value}</div></div>'
        for label, value in cards
    )
    return f'<div class="orbit-stats-row">{cards_html}</div>'


# ---------------------------------------------------------------------------
# Browse / search tab
# ---------------------------------------------------------------------------

def entities_to_dataframe(entities: list[dict]) -> pd.DataFrame:
    rows = []
    for e in entities:
        rows.append(
            {
                "Name": e["name"],
                "Type": e["entity_type"],
                "Categories": ", ".join(e["categories"]),
                "Links": _CONNECTION_COUNTS.get(e["id"], 0),
                "Source": e["source"]["name"],
                "URL": e["url"],
            }
        )
    return pd.DataFrame(rows)


def search_entities(query: str, category: str, entity_type: str):
    results = ENTITIES
    if category and category != "All":
        results = [e for e in results if category in e["categories"]]
    if entity_type and entity_type != "All":
        results = [e for e in results if e["entity_type"] == entity_type]
    if query:
        q = query.lower()
        results = [
            e for e in results
            if q in e["name"].lower() or q in e["description"].lower()
        ]
    df = entities_to_dataframe(results)
    return df, f"**{len(results)}** entities match your filters."


def format_entity_detail(entity_id: str) -> str:
    e = ENTITY_BY_ID.get(entity_id)
    if not e:
        return "Select an entity to see details."

    links = _CONNECTION_COUNTS.get(entity_id, 0)
    lines = [
        f"### {e['name']}",
        f"**Type:** {e['entity_type']}  |  **Categories:** {', '.join(e['categories'])}"
        f'<span class="orbit-badge">{links} link{"s" if links != 1 else ""}</span>',
        "",
        e["description"] or "_No description available._",
        "",
        f"**Source:** [{e['source']['name']}]({e['source']['url']})",
        f"**URL:** {e['url']}",
    ]

    for meta_key, title in [
        ("model_metadata", "Model details"),
        ("repository_metadata", "Repository details"),
        ("mcp_metadata", "MCP details"),
        ("company_metadata", "Company details"),
        ("video_metadata", "Video details"),
        ("news_metadata", "News details"),
    ]:
        meta = e.get(meta_key)
        if meta:
            populated = {k: v for k, v in meta.items() if v not in (None, [], "")}
            if populated:
                lines.append(f"\n**{title}:**")
                for k, v in populated.items():
                    lines.append(f"- {k.replace('_', ' ').title()}: {v}")

    return "\n".join(lines)


def on_row_select(evt: gr.SelectData, current_df: pd.DataFrame):
    if current_df is None or len(current_df) == 0:
        return "Select an entity to see details."
    row = current_df.iloc[evt.index[0]]
    name = row["Name"]
    matches = [e for e in ENTITIES if e["name"] == name]
    if not matches:
        return "Entity not found."
    return format_entity_detail(matches[0]["id"])


# ---------------------------------------------------------------------------
# Relationship explorer tab
# ---------------------------------------------------------------------------

def _empty_state_html() -> str:
    suggestions = "".join(
        f"<li>{e['name']} <span style='color:var(--orbit-text-dim)'>({e['entity_type']}, "
        f"{_CONNECTION_COUNTS.get(e['id'], 0)} links)</span></li>"
        for e in TOP_CONNECTED[:5]
    )
    return (
        '<div class="orbit-empty-state">'
        "<b>No detected relationships for this entity.</b><br>"
        "Most entities in a real-world ecosystem graph like this sit on the edges — "
        "relationships are inferred from text mentions and structural signals, so only "
        "entities that reference each other by name get linked. Try one of the "
        "well-connected hubs instead:"
        f"<ul style='margin:8px 0 0 18px'>{suggestions}</ul></div>"
    )


def explore_relationships(entity_label: str):
    if not entity_label or entity_label not in LABEL_TO_ID:
        return "Pick an entity above to explore its relationships.", pd.DataFrame(), ""

    entity_id = LABEL_TO_ID[entity_label]
    entity = ENTITY_BY_ID[entity_id]

    outgoing = [r for r in RELATIONSHIPS if r["source_id"] == entity_id]
    incoming = [r for r in RELATIONSHIPS if r["target_id"] == entity_id]

    rows = []
    for r in outgoing:
        target = ENTITY_BY_ID.get(r["target_id"])
        if target:
            rows.append({
                "Direction": "→ outgoing",
                "Relationship": r["predicate"],
                "Other Entity": target["name"],
                "Other Type": target["entity_type"],
                "Confidence": r["confidence"],
                "Evidence": r["evidence"],
            })
    for r in incoming:
        source = ENTITY_BY_ID.get(r["source_id"])
        if source:
            rows.append({
                "Direction": "← incoming",
                "Relationship": r["predicate"],
                "Other Entity": source["name"],
                "Other Type": source["entity_type"],
                "Confidence": r["confidence"],
                "Evidence": r["evidence"],
            })

    summary = f"### {entity['name']}\n{len(rows)} relationship(s) found."

    if not rows:
        return summary, pd.DataFrame(
            columns=["Direction", "Relationship", "Other Entity", "Other Type", "Confidence", "Evidence"]
        ), _empty_state_html()

    df = pd.DataFrame(rows).sort_values("Confidence", ascending=False)
    return summary, df, ""


# ---------------------------------------------------------------------------
# Stats tab
# ---------------------------------------------------------------------------

def entities_by_type_df() -> pd.DataFrame:
    counts = Counter(e["entity_type"] for e in ENTITIES)
    return pd.DataFrame({"Type": list(counts.keys()), "Count": list(counts.values())}).sort_values(
        "Count", ascending=False
    )


def entities_by_source_df() -> pd.DataFrame:
    counts = Counter(e["source"]["name"] for e in ENTITIES)
    return pd.DataFrame({"Source": list(counts.keys()), "Count": list(counts.values())}).sort_values(
        "Count", ascending=False
    )


def relationships_by_predicate_df() -> pd.DataFrame:
    counts = Counter(r["predicate"] for r in RELATIONSHIPS)
    return pd.DataFrame({"Predicate": list(counts.keys()), "Count": list(counts.values())}).sort_values(
        "Count", ascending=False
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="AI Orbit — Ecosystem Explorer", theme=ORBIT_THEME, css=ORBIT_CSS) as demo:
    gr.HTML(
        '<div class="orbit-header"><span style="font-size:26px">🛰️</span>'
        '<span class="orbit-title">AI Orbit — Ecosystem Explorer</span></div>'
        '<div class="orbit-tagline">A structured, cross-referenced map of the AI ecosystem — '
        "ingested from GitHub, Hugging Face, YouTube, RSS news, and official company sites.</div>"
    )
    gr.HTML(build_stat_cards_html())

    with gr.Tab("Browse & Search"):
        with gr.Row():
            search_box = gr.Textbox(label="Search", placeholder="Search by name or description…", scale=2)
            category_dd = gr.Dropdown(choices=["All"] + ALL_CATEGORIES, value="All", label="Category")
            type_dd = gr.Dropdown(choices=["All"] + ALL_TYPES, value="All", label="Entity type")

        result_count = gr.Markdown()
        results_table = gr.Dataframe(
            headers=["Name", "Type", "Categories", "Links", "Source", "URL"],
            interactive=False,
            wrap=True,
        )
        detail_panel = gr.Markdown(value="Select a row above to see full entity details.")

        for control in (search_box, category_dd, type_dd):
            control.change(search_entities, [search_box, category_dd, type_dd], [results_table, result_count])

        results_table.select(on_row_select, [results_table], [detail_panel])

        demo.load(search_entities, [search_box, category_dd, type_dd], [results_table, result_count])

    with gr.Tab("Relationship Explorer"):
        gr.Markdown(
            "Pick any entity to see everything it's connected to, with the evidence behind each link. "
            "Sorted so the most-connected entities appear first — those are the best starting points."
        )
        entity_picker = gr.Dropdown(
            choices=[label for label, _ in ENTITY_CHOICES],
            value=DEFAULT_ENTITY_LABEL,
            label="Choose an entity",
            filterable=True,
        )
        rel_summary = gr.Markdown()
        rel_table = gr.Dataframe(
            headers=["Direction", "Relationship", "Other Entity", "Other Type", "Confidence", "Evidence"],
            interactive=False,
            wrap=True,
        )
        rel_empty_state = gr.HTML()

        entity_picker.change(
            explore_relationships, [entity_picker], [rel_summary, rel_table, rel_empty_state]
        )
        demo.load(explore_relationships, [entity_picker], [rel_summary, rel_table, rel_empty_state])

    with gr.Tab("Dataset Stats"):
        gr.Markdown("### Entities by type")
        type_chart = gr.BarPlot(
            entities_by_type_df(), x="Type", y="Count", title=None, height=280, color="Type",
        )
        gr.Markdown("### Entities by source")
        source_chart = gr.BarPlot(
            entities_by_source_df(), x="Source", y="Count", title=None, height=280, color="Source",
        )
        gr.Markdown("### Relationships by predicate")
        predicate_chart = gr.BarPlot(
            relationships_by_predicate_df(), x="Predicate", y="Count", title=None, height=240, color="Predicate",
        )

if __name__ == "__main__":
    demo.launch()
