/*
 * AI Orbit — Ecosystem Explorer (static build)
 * ==============================================
 * A pure client-side port of the Gradio app (app/app.py). Loads
 * data/entities.json and data/relationships.json via fetch(), then
 * replicates: stat cards, Browse & Search, Relationship Explorer
 * (sorted-by-connectivity picker + helpful empty state), and Dataset
 * Stats (Chart.js bar charts).
 *
 * No server, no build step, no API calls at runtime — everything here
 * runs entirely in the visitor's browser against the two static JSON
 * files shipped alongside this page.
 */

let ENTITIES = [];
let RELATIONSHIPS = [];
let ENTITY_BY_ID = {};
let CONNECTION_COUNTS = {};
let ENTITY_CHOICES = [];   // [{label, id}], sorted by connection count desc
let LABEL_TO_ID = {};
let TOP_CONNECTED = [];
let ALL_CATEGORIES = [];
let ALL_TYPES = [];

// ---------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------

async function main() {
    const [entitiesRes, relationshipsRes] = await Promise.all([
        fetch('data/entities.json'),
        fetch('data/relationships.json'),
    ]);
    ENTITIES = await entitiesRes.json();
    RELATIONSHIPS = await relationshipsRes.json();

    ENTITY_BY_ID = Object.fromEntries(ENTITIES.map(e => [e.id, e]));

    ALL_CATEGORIES = [...new Set(ENTITIES.flatMap(e => e.categories))].sort();
    ALL_TYPES = [...new Set(ENTITIES.map(e => e.entity_type))].sort();

    CONNECTION_COUNTS = {};
    for (const r of RELATIONSHIPS) {
        CONNECTION_COUNTS[r.source_id] = (CONNECTION_COUNTS[r.source_id] || 0) + 1;
        CONNECTION_COUNTS[r.target_id] = (CONNECTION_COUNTS[r.target_id] || 0) + 1;
    }

    ENTITY_CHOICES = ENTITIES
        .map(e => ({ label: entityLabel(e), id: e.id, count: CONNECTION_COUNTS[e.id] || 0 }))
        .sort((a, b) => b.count - a.count);
    LABEL_TO_ID = Object.fromEntries(ENTITY_CHOICES.map(c => [c.label, c.id]));

    TOP_CONNECTED = Object.entries(CONNECTION_COUNTS)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([id]) => ENTITY_BY_ID[id])
        .filter(Boolean);

    renderStatCards();
    setupTabs();
    setupBrowseTab();
    setupRelationshipTab();
    setupStatsTab(); // already internally defensive — see function body
}

function entityLabel(e) {
    const count = CONNECTION_COUNTS[e.id] || 0;
    const suffix = count ? ` — ${count} link${count !== 1 ? 's' : ''}` : ' — no links yet';
    return `${e.name} (${e.entity_type})${suffix}`;
}

// ---------------------------------------------------------------------
// Stat cards
// ---------------------------------------------------------------------

function renderStatCards() {
    const connected = Object.keys(CONNECTION_COUNTS).length;
    const cards = [
        ['Total entities', ENTITIES.length.toLocaleString()],
        ['Relationships', RELATIONSHIPS.length.toLocaleString()],
        ['Entity types', String(ALL_TYPES.length)],
        ['Categories', String(ALL_CATEGORIES.length)],
        ['Connected entities', connected.toLocaleString()],
    ];
    document.getElementById('stat-cards').innerHTML = cards.map(([label, value]) => `
        <div class="orbit-stat-card">
            <div class="orbit-stat-label">${escapeHtml(label)}</div>
            <div class="orbit-stat-value">${escapeHtml(value)}</div>
        </div>
    `).join('');
}

// ---------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------

function setupTabs() {
    document.querySelectorAll('.orbit-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.orbit-tab').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.orbit-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
        });
    });
}

// ---------------------------------------------------------------------
// Browse & Search tab
// ---------------------------------------------------------------------

function setupBrowseTab() {
    const categorySelect = document.getElementById('category-select');
    const typeSelect = document.getElementById('type-select');

    categorySelect.innerHTML = ['All', ...ALL_CATEGORIES]
        .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    typeSelect.innerHTML = ['All', ...ALL_TYPES]
        .map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');

    const searchInput = document.getElementById('search-input');
    const rerun = () => searchEntities(searchInput.value, categorySelect.value, typeSelect.value);

    searchInput.addEventListener('input', rerun);
    categorySelect.addEventListener('change', rerun);
    typeSelect.addEventListener('change', rerun);

    rerun(); // initial render
}

function searchEntities(query, category, entityType) {
    let results = ENTITIES;
    if (category && category !== 'All') {
        results = results.filter(e => e.categories.includes(category));
    }
    if (entityType && entityType !== 'All') {
        results = results.filter(e => e.entity_type === entityType);
    }
    if (query) {
        const q = query.toLowerCase();
        results = results.filter(e =>
            e.name.toLowerCase().includes(q) || (e.description || '').toLowerCase().includes(q)
        );
    }
    renderResultsTable(results);
    document.getElementById('result-count').textContent = `${results.length} entities match your filters.`;
}

function renderResultsTable(results) {
    const tbody = document.getElementById('results-tbody');
    tbody.innerHTML = results.map(e => `
        <tr data-id="${escapeAttr(e.id)}">
            <td>${escapeHtml(e.name)}</td>
            <td>${escapeHtml(e.entity_type)}</td>
            <td>${escapeHtml(e.categories.join(', '))}</td>
            <td>${CONNECTION_COUNTS[e.id] || 0}</td>
            <td>${escapeHtml(e.source.name)}</td>
            <td><a href="${escapeAttr(e.url)}" target="_blank" rel="noopener">${escapeHtml(truncate(e.url, 60))}</a></td>
        </tr>
    `).join('');

    tbody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', () => showEntityDetail(row.dataset.id));
    });
}

function showEntityDetail(entityId) {
    const e = ENTITY_BY_ID[entityId];
    const panel = document.getElementById('detail-panel');
    if (!e) {
        panel.innerHTML = '<p class="orbit-dim">Entity not found.</p>';
        return;
    }

    const links = CONNECTION_COUNTS[entityId] || 0;
    let html = `
        <h3>${escapeHtml(e.name)}
            <span class="orbit-badge">${links} link${links !== 1 ? 's' : ''}</span>
        </h3>
        <p><b>Type:</b> ${escapeHtml(e.entity_type)} &nbsp;|&nbsp; <b>Categories:</b> ${escapeHtml(e.categories.join(', '))}</p>
        <p>${escapeHtml(e.description) || '<i>No description available.</i>'}</p>
        <p><b>Source:</b> <a href="${escapeAttr(e.source.url)}" target="_blank" rel="noopener">${escapeHtml(e.source.name)}</a></p>
        <p><b>URL:</b> <a href="${escapeAttr(e.url)}" target="_blank" rel="noopener">${escapeHtml(e.url)}</a></p>
    `;

    const metaSections = [
        ['model_metadata', 'Model details'],
        ['repository_metadata', 'Repository details'],
        ['mcp_metadata', 'MCP details'],
        ['company_metadata', 'Company details'],
        ['video_metadata', 'Video details'],
        ['news_metadata', 'News details'],
    ];

    for (const [key, title] of metaSections) {
        const meta = e[key];
        if (!meta) continue;
        const populated = Object.entries(meta).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && v.length === 0));
        if (populated.length === 0) continue;
        html += `<p><b>${escapeHtml(title)}:</b></p><ul>`;
        for (const [k, v] of populated) {
            const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const value = Array.isArray(v) ? v.join(', ') : v;
            html += `<li>${escapeHtml(label)}: ${escapeHtml(String(value))}</li>`;
        }
        html += '</ul>';
    }

    panel.innerHTML = html;
}

// ---------------------------------------------------------------------
// Relationship Explorer tab
// ---------------------------------------------------------------------

function setupRelationshipTab() {
    const input = document.getElementById('entity-combobox');
    const list = document.getElementById('entity-combobox-list');

    function renderSuggestions(filterText) {
        const q = filterText.trim().toLowerCase();
        const matches = (q
            ? ENTITY_CHOICES.filter(c => c.label.toLowerCase().includes(q))
            : ENTITY_CHOICES
        ).slice(0, 50);

        if (matches.length === 0) {
            list.innerHTML = '<li class="orbit-dim">No matches</li>';
        } else {
            list.innerHTML = matches.map(c =>
                `<li data-id="${escapeAttr(c.id)}" data-label="${escapeAttr(c.label)}">${escapeHtml(c.label)}</li>`
            ).join('');
        }
        list.classList.add('open');
    }

    input.addEventListener('focus', () => renderSuggestions(input.value));
    input.addEventListener('input', () => renderSuggestions(input.value));
    document.addEventListener('click', (evt) => {
        if (!evt.target.closest('.orbit-combobox')) list.classList.remove('open');
    });
    list.addEventListener('click', (evt) => {
        const li = evt.target.closest('li[data-id]');
        if (!li) return;
        input.value = li.dataset.label;
        list.classList.remove('open');
        exploreRelationships(li.dataset.id);
    });

    // Default selection: the most-connected entity, mirroring the Python app.
    if (ENTITY_CHOICES.length > 0) {
        input.value = ENTITY_CHOICES[0].label;
        exploreRelationships(ENTITY_CHOICES[0].id);
    }
}

// Exposed globally so the empty-state "try this instead" list can call it.
window.selectEntityById = function (entityId) {
    const choice = ENTITY_CHOICES.find(c => c.id === entityId);
    if (!choice) return;
    document.getElementById('entity-combobox').value = choice.label;
    document.getElementById('entity-combobox-list').classList.remove('open');
    exploreRelationships(entityId);
};

function exploreRelationships(entityId) {
    const entity = ENTITY_BY_ID[entityId];
    if (!entity) return;

    const outgoing = RELATIONSHIPS.filter(r => r.source_id === entityId);
    const incoming = RELATIONSHIPS.filter(r => r.target_id === entityId);

    const rows = [];
    for (const r of outgoing) {
        const target = ENTITY_BY_ID[r.target_id];
        if (target) rows.push({ direction: '→ outgoing', predicate: r.predicate, other: target.name, otherType: target.entity_type, confidence: r.confidence, evidence: r.evidence });
    }
    for (const r of incoming) {
        const source = ENTITY_BY_ID[r.source_id];
        if (source) rows.push({ direction: '← incoming', predicate: r.predicate, other: source.name, otherType: source.entity_type, confidence: r.confidence, evidence: r.evidence });
    }
    rows.sort((a, b) => b.confidence - a.confidence);

    document.getElementById('rel-summary').innerHTML =
        `<h3>${escapeHtml(entity.name)}</h3><p class="orbit-dim">${rows.length} relationship(s) found.</p>`;

    const tbody = document.getElementById('rel-tbody');
    const emptyState = document.getElementById('rel-empty-state');

    if (rows.length === 0) {
        tbody.innerHTML = '';
        const suggestions = TOP_CONNECTED.slice(0, 5).map(e => `
            <li onclick="selectEntityById('${escapeAttr(e.id)}')">
                ${escapeHtml(e.name)}
                <span class="orbit-dim">(${escapeHtml(e.entity_type)}, ${CONNECTION_COUNTS[e.id] || 0} links)</span>
            </li>
        `).join('');
        emptyState.innerHTML = `
            <div class="orbit-empty-state">
                <b>No detected relationships for this entity.</b><br>
                Most entities in a real-world ecosystem graph like this sit on the edges —
                relationships are inferred from text mentions and structural signals, so only
                entities that reference each other by name get linked. Try one of the
                well-connected hubs instead:
                <ul>${suggestions}</ul>
            </div>`;
    } else {
        emptyState.innerHTML = '';
        tbody.innerHTML = rows.map(r => `
            <tr>
                <td>${escapeHtml(r.direction)}</td>
                <td>${escapeHtml(r.predicate)}</td>
                <td>${escapeHtml(r.other)}</td>
                <td>${escapeHtml(r.otherType)}</td>
                <td>${r.confidence}</td>
                <td>${escapeHtml(r.evidence)}</td>
            </tr>
        `).join('');
    }
}

// ---------------------------------------------------------------------
// Dataset Stats tab
// ---------------------------------------------------------------------

const CHART_PALETTE = ['#4FD1C5', '#F5A623', '#7C9EF2', '#E8608E', '#8ED17F', '#C084F5', '#F2A65A', '#5AC8E8', '#F27878', '#A0E85A'];

function countBy(items, keyFn) {
    const counts = {};
    for (const item of items) {
        const key = keyFn(item);
        counts[key] = (counts[key] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}

function renderBarChart(canvasId, entries) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: entries.map(([k]) => k),
            datasets: [{
                data: entries.map(([, v]) => v),
                backgroundColor: entries.map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#8B92A8' }, grid: { color: '#262E42' } },
                y: { ticks: { color: '#8B92A8', precision: 0 }, grid: { color: '#262E42' }, beginAtZero: true },
            },
        },
    });
}

function setupStatsTab() {
    if (typeof Chart === 'undefined') {
        // Chart.js failed to load for some reason (blocked script, offline
        // vendor file, etc.) — degrade gracefully instead of taking down
        // the rest of the app, which only depends on entities/relationships
        // JSON, not on this library.
        console.error('Chart.js is not available; Dataset Stats charts will not render.');
        document.querySelectorAll('.orbit-chart-wrap').forEach(el => {
            el.innerHTML = '<p class="orbit-dim">Charts unavailable (chart library failed to load).</p>';
        });
        return;
    }
    try {
        renderBarChart('chart-by-type', countBy(ENTITIES, e => e.entity_type));
        renderBarChart('chart-by-source', countBy(ENTITIES, e => e.source.name));
        renderBarChart('chart-by-predicate', countBy(RELATIONSHIPS, r => r.predicate));
    } catch (err) {
        console.error('Failed to render dataset stats charts:', err);
    }
}

// ---------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
function escapeAttr(str) { return escapeHtml(str); }
function truncate(str, n) { return str && str.length > n ? str.slice(0, n) + '…' : str; }

main().catch(err => {
    document.body.innerHTML = `<div style="padding:40px;color:#E8608E;font-family:sans-serif">
        <h2>Failed to load dataset</h2>
        <p>${escapeHtml(err.message)}</p>
        <p>Make sure <code>data/entities.json</code> and <code>data/relationships.json</code>
        are present alongside this page, and that you're viewing it via a local server
        (not a bare <code>file://</code> URL — browsers block fetch() for local files).</p>
    </div>`;
    console.error(err);
});
