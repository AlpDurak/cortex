# Cortex v2 — Phase 3: Canvas Rewrite + UI Panels

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vis-network graph library with Cytoscape.js + cose-bilkent layout. Render Groups as compound parent containers. Apply Signal Cluster border rings. Add four sidebar panels: Vitals, Inspector, Timeline, Search.

**Architecture:** `static/canvas.js` is a complete rewrite — swap vis.DataSet/vis.Network for `cytoscape({...})`. The existing `window.CortexGraph` API surface (`render`, `addNode`, `highlightSearch`, `clearSearch`, `filterEdgesByLabel`) is preserved so `index.html` JavaScript needs only small updates. `MEMBER_OF` edges are converted to `parent` properties on member nodes before being passed to Cytoscape — they are not drawn as arrows. New panels live in `static/panels/` as independent JS modules that expose a single `init(state)` function.

**Tech Stack:** Cytoscape.js 3.29 (CDN), cytoscape-cose-bilkent 4.1 (CDN), vanilla JS, CSS. No build step.

**Prerequisites:** Phase 1 and Phase 2 complete. `/api/clusters`, `/api/keystones`, `/api/latent-bridges` endpoints must exist.

---

## Task 1: Swap vis-network for Cytoscape.js in index.html

**Files:**
- Modify: `static/index.html` — replace vis-network `<script>` with Cytoscape CDN scripts; add panel `<script>` tags; add Vitals dock button; remove minimap `<canvas>`; add panels container

- [ ] **Step 1: Replace the CDN script tags in index.html**

Remove line 9:
```html
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
```

Replace with:
```html
<script src="https://unpkg.com/cytoscape@3.29.2/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/cytoscape-cose-bilkent@4.1.0/cytoscape-cose-bilkent.js"></script>
```

- [ ] **Step 2: Add a Vitals dock button in the icon dock**

After the existing `#btn-filter` button, add:
```html
<button class="dock-btn" id="btn-vitals" title="Vitals" onclick="setActivePanel('vitals')">
  <svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
</button>
```

- [ ] **Step 3: Add a Vitals panel div in the secondary sidebar**

After the `#filter-panel` div, add:
```html
<!-- VITALS PANEL -->
<div id="vitals-panel" style="display:none; flex-direction:column; flex: 1; overflow-y:auto">
  <div class="panel-header">Vitals</div>
  <div id="vitals-content" style="padding:8px 14px 16px"></div>
</div>
```

- [ ] **Step 4: Add panel script tags at the bottom (before canvas.js)**

Replace:
```html
<!-- Phase 5: Vis-Network canvas (loaded after main UI script) -->
<script src="/static/canvas.js"></script>
```

With:
```html
<script src="/static/panels/vitals.js"></script>
<script src="/static/panels/inspector.js"></script>
<script src="/static/canvas.js"></script>
```

- [ ] **Step 5: Update panel switching in index.html JavaScript**

In the `setActivePanel` function, add `vitals` to the `panels` map:
```javascript
const panels = {
  timeline: 'timeline-panel',
  search: 'search-panel',
  filter: 'filter-panel',
  vitals: 'vitals-panel',
};
```

And add `btn-vitals` to the button mapping that already handles `btn-timeline`, `btn-search`, `btn-filter` — the `setActivePanel` function finds buttons by `id = 'btn-' + panel`, so this is automatic.

- [ ] **Step 6: Remove minimap canvas element**

Remove the `<canvas id="minimap-canvas" ...>` element from the HTML. Cytoscape has no built-in minimap equivalent and the canvas API differs — the minimap is dropped in this rewrite.

- [ ] **Step 7: Remove minimap canvas CSS**

Remove from `<style>`:
```css
/* nothing to remove specifically — minimap was inline-styled */
```
The inline style on the `<canvas>` element is removed in Step 6, so no separate CSS cleanup needed.

- [ ] **Step 8: Update the search panel click handler in onSearchInput**

In `index.html` JavaScript, update `onSearchInput` — remove the vis-network-specific focus call and replace with Cytoscape:

```javascript
function onSearchInput(q) {
  if (window.CortexGraph) {
    if (q) window.CortexGraph.highlightSearch(q);
    else   window.CortexGraph.clearSearch();
  }

  const ul = document.getElementById('search-results');
  ul.innerHTML = '';
  if (!q) return;
  const matches = _nodes.filter(n =>
    (n.name || '').toLowerCase().includes(q.toLowerCase()) ||
    (n.id   || '').toLowerCase().includes(q.toLowerCase())
  ).slice(0, 20);

  matches.forEach(n => {
    const li = document.createElement('li');
    li.textContent = (n.name || n.id);
    li.title = n.id;
    li.addEventListener('click', () => {
      if (window.CortexGraph) window.CortexGraph.focusNode(n.id);
      onNodeClick(n.id);
    });
    ul.appendChild(li);
  });
}
```

- [ ] **Step 9: Update onNodeClick in index.html to use Decision Arc status colors**

In the `statusColor` map, update from old status names to Decision Arc:
```javascript
const statusColor = {
  'shipped':  '#059669',
  'building': '#ea580c',
  'proposed': '#6b7280',
};
```

- [ ] **Step 10: Commit HTML changes**

```bash
git add static/index.html
git commit -m "feat(ui): swap vis-network for Cytoscape.js CDN, add Vitals dock button"
```

---

## Task 2: Rewrite canvas.js for Cytoscape.js

**Files:**
- Rewrite: `static/canvas.js`

The existing `canvas.js` is a vis-network implementation. The new version keeps the same `window.CortexGraph` API but uses Cytoscape.js internally.

Key mappings:
- `new vis.Network(container, data, opts)` → `cytoscape({container, elements, style, layout})`
- `_visNodes.add(...)` / `_visEdges.add(...)` → `cy.add([...])`
- `_network.on('click', ...)` → `cy.on('tap', 'node', ...)`
- `MEMBER_OF` edges → set `parent: groupId` on member nodes, skip edge rendering
- Signal Cluster ring → `border-color` and `border-width` on nodes

- [ ] **Step 1: Overwrite static/canvas.js with the Cytoscape.js implementation**

```javascript
/**
 * canvas.js — Cytoscape.js graph canvas for Cortex.
 * Exposes window.CortexGraph = { render, addNode, highlightSearch, clearSearch,
 *                                  filterEdgesByLabel, focusNode }
 */
(function () {
  'use strict';

  // Node type colour palette
  const TYPE_COLORS = {
    File:           { bg: '#dbeafe', border: '#3b82f6' },
    SystemDesign:   { bg: '#ede9fe', border: '#7c3aed' },
    Service:        { bg: '#ffedd5', border: '#ea580c' },
    Database:       { bg: '#d1fae5', border: '#059669' },
    Infrastructure: { bg: '#e5e7eb', border: '#6b7280' },
    Group:          { bg: 'rgba(124,58,237,0.06)', border: '#7c3aed' },
  };
  const COLOR_DEFAULT = { bg: '#f3f4f6', border: '#9ca3af' };

  const DIFF_COLORS = {
    added:    { bg: '#d4edda', border: '#28a745' },
    deleted:  { bg: '#f8d7da', border: '#dc3545' },
    modified: { bg: '#fff3cd', border: '#ffc107' },
  };

  let _cy = null;
  let _hiddenEdgeLabels = new Set();
  let _clusterData = [];   // loaded from /api/clusters
  let _nodeCluster = {};   // nodeId → cluster id

  // ---------------------------------------------------------------------------
  // Build Cytoscape stylesheet
  // ---------------------------------------------------------------------------
  function buildStyle() {
    const typeStyles = Object.entries(TYPE_COLORS).map(([label, c]) => ({
      selector: `node.${label}`,
      style: {
        'background-color': c.bg,
        'border-color': c.border,
        'border-width': 2,
      },
    }));

    return [
      {
        selector: 'node',
        style: {
          'label': 'data(displayName)',
          'font-size': '11px',
          'font-family': 'Cascadia Code, Fira Code, Consolas, monospace',
          'color': '#1f2937',
          'text-valign': 'center',
          'text-halign': 'center',
          'width': 'label',
          'height': '28px',
          'padding': '8px',
          'shape': 'roundrectangle',
          'border-width': 2,
          'background-color': '#f3f4f6',
          'border-color': '#9ca3af',
          'text-wrap': 'none',
          'min-width': '80px',
        },
      },
      ...typeStyles,
      {
        selector: 'node:parent',  // compound Group nodes
        style: {
          'background-color': 'rgba(124,58,237,0.05)',
          'border-color': '#7c3aed',
          'border-width': 1.5,
          'border-style': 'dashed',
          'label': 'data(displayName)',
          'text-valign': 'top',
          'text-halign': 'center',
          'font-size': '10px',
          'font-weight': 700,
          'color': 'rgba(167,139,250,0.9)',
          'padding': '18px',
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-width': 3, 'border-color': '#0e639c' },
      },
      {
        selector: 'node.diff-added',
        style: { 'background-color': DIFF_COLORS.added.bg, 'border-color': DIFF_COLORS.added.border },
      },
      {
        selector: 'node.diff-deleted',
        style: { 'background-color': DIFF_COLORS.deleted.bg, 'border-color': DIFF_COLORS.deleted.border },
      },
      {
        selector: 'node.diff-modified',
        style: { 'background-color': DIFF_COLORS.modified.bg, 'border-color': DIFF_COLORS.modified.border },
      },
      {
        selector: 'node.faded',
        style: { 'opacity': 0.12 },
      },
      {
        selector: 'edge',
        style: {
          'width': 1.5,
          'line-color': '#94a3b8',
          'target-arrow-color': '#94a3b8',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(rel)',
          'font-size': '9px',
          'color': '#6b7280',
          'text-background-color': '#1e1e1e',
          'text-background-opacity': 0.7,
          'text-background-padding': '2px',
        },
      },
      {
        selector: 'edge:selected',
        style: { 'width': 3 },
      },
      {
        selector: 'edge.hidden',
        style: { 'display': 'none' },
      },
      {
        selector: 'edge.diff-added',
        style: { 'line-color': '#28a745', 'target-arrow-color': '#28a745', 'width': 2.5 },
      },
      {
        selector: 'edge.diff-deleted',
        style: {
          'line-color': '#dc3545',
          'target-arrow-color': '#dc3545',
          'line-style': 'dashed',
          'width': 2,
        },
      },
    ];
  }

  // ---------------------------------------------------------------------------
  // Convert raw API nodes/edges to Cytoscape elements
  // Resolves MEMBER_OF into parent/child compound structure.
  // ---------------------------------------------------------------------------
  function toElements(nodes, edges, diffData) {
    // Build parent map from MEMBER_OF edges
    const parentMap = {};   // memberId → groupId
    const nonMemberEdges = [];
    for (const e of edges) {
      if (e.rel === 'MEMBER_OF') {
        parentMap[e.src] = e.dst;
      } else {
        nonMemberEdges.push(e);
      }
    }

    const elements = [];

    // Add nodes
    for (const n of nodes) {
      const colors = TYPE_COLORS[n.label] || COLOR_DEFAULT;
      const name = n.name || n.id || '';
      const displayName = name.length > 26 ? name.slice(0, 26) + '…' : name;
      const clusterColor = _nodeCluster[n.id] !== undefined
        ? (_clusterData.find(c => c.id === _nodeCluster[n.id]) || {}).color
        : null;

      const data = {
        id: n.id,
        displayName,
        label: n.label,
        ...n,
      };

      if (parentMap[n.id]) {
        data.parent = parentMap[n.id];
      }

      const classes = [n.label || 'Unknown'];
      if (clusterColor) classes.push('has-cluster');
      if (diffData) {
        if (diffData.added_nodes && diffData.added_nodes.includes(n.id)) classes.push('diff-added');
        else if (diffData.deleted_nodes && diffData.deleted_nodes.includes(n.id)) classes.push('diff-deleted');
        else if (diffData.modified_nodes && diffData.modified_nodes.includes(n.id)) classes.push('diff-modified');
      }

      elements.push({ data, classes: classes.join(' ') });
    }

    // Add non-MEMBER_OF edges
    for (let i = 0; i < nonMemberEdges.length; i++) {
      const e = nonMemberEdges[i];
      const edgeKey = `${e.src}|${e.rel}|${e.dst}`;
      const eData = { id: edgeKey + '_' + i, source: e.src, target: e.dst, rel: e.rel };
      const classes = [];
      if (diffData) {
        const addedKeys = (diffData.added_edges || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        const deletedKeys = (diffData.deleted_edges || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        if (addedKeys.includes(edgeKey)) classes.push('diff-added');
        else if (deletedKeys.includes(edgeKey)) classes.push('diff-deleted');
      }
      elements.push({ data: eData, classes: classes.join(' ') });
    }

    return elements;
  }

  // ---------------------------------------------------------------------------
  // Apply cluster border rings
  // ---------------------------------------------------------------------------
  function applyClusterColors() {
    if (!_cy || !_clusterData.length) return;
    for (const cluster of _clusterData) {
      for (const memberId of cluster.members) {
        const node = _cy.getElementById(memberId);
        if (node.length) {
          node.style({
            'border-color': cluster.color,
            'border-width': 3,
          });
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // ---------------------------------------------------------------------------
  function bootstrap() {
    const container = document.getElementById('graph-canvas');
    if (!container) return;

    // Register cose-bilkent layout (loaded from CDN)
    if (typeof cytoscapeCoseBilkent !== 'undefined') {
      cytoscape.use(cytoscapeCoseBilkent);
    }

    _cy = cytoscape({
      container,
      elements: [],
      style: buildStyle(),
      layout: { name: 'grid' },
    });

    // Node click → inspector
    _cy.on('tap', 'node', function (evt) {
      const node = evt.target;
      if (node.isParent()) return;  // ignore compound group nodes
      if (window.CortexUI && window.CortexUI.onNodeClick) {
        window.CortexUI.onNodeClick(node.id());
      }
    });

    // Double-click → focus
    _cy.on('dbltap', 'node', function (evt) {
      _cy.animate({ fit: { eles: evt.target.neighborhood().add(evt.target), padding: 40 }, duration: 400 });
    });

    // Load cluster data
    fetch('/api/clusters')
      .then(r => r.json())
      .then(clusters => {
        _clusterData = clusters;
        _nodeCluster = {};
        for (const c of clusters) {
          for (const m of c.members) _nodeCluster[m] = c.id;
        }
        applyClusterColors();
      })
      .catch(() => {});
  }

  // ---------------------------------------------------------------------------
  // Public API — window.CortexGraph
  // ---------------------------------------------------------------------------

  function render(nodes, edges, diffData) {
    if (!_cy) return;

    _cy.elements().remove();
    const elements = toElements(nodes, edges, diffData);
    _cy.add(elements);

    const layout = _cy.layout({
      name: typeof cytoscapeCoseBilkent !== 'undefined' ? 'cose-bilkent' : 'cose',
      animate: true,
      animationDuration: 600,
      nodeDimensionsIncludeLabels: true,
      idealEdgeLength: 120,
      nodeRepulsion: 8000,
      gravity: 0.25,
    });
    layout.run();

    // Re-apply search if active
    const activeSearch = window._cortexSearchQuery;
    if (activeSearch) highlightSearch(activeSearch);

    // Re-apply edge filters
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);

    applyClusterColors();
  }

  function addNode(node, edges) {
    if (!_cy) return;
    const elements = toElements([node], edges, null);
    _cy.add(elements);

    const newNode = _cy.getElementById(node.id);
    if (newNode.length) {
      newNode.layout({ name: 'concentric', animate: true }).run();
      newNode.select();
      setTimeout(() => newNode.unselect(), 2000);
    }

    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
    applyClusterColors();
  }

  function highlightSearch(query) {
    window._cortexSearchQuery = query;
    if (!_cy) return;
    const q = query.toLowerCase();
    _cy.nodes().forEach(n => {
      const raw = n.data();
      const match = (raw.name || '').toLowerCase().includes(q)
                 || (raw.id  || '').toLowerCase().includes(q);
      if (match) n.removeClass('faded');
      else       n.addClass('faded');
    });
  }

  function clearSearch() {
    window._cortexSearchQuery = '';
    if (!_cy) return;
    _cy.nodes().removeClass('faded');
  }

  function filterEdgesByLabel(hiddenLabels) {
    _hiddenEdgeLabels = hiddenLabels;
    if (!_cy) return;
    _cy.edges().forEach(e => {
      if (_hiddenEdgeLabels.has(e.data('rel'))) e.addClass('hidden');
      else e.removeClass('hidden');
    });
  }

  function focusNode(nodeId) {
    if (!_cy) return;
    const node = _cy.getElementById(nodeId);
    if (node.length) {
      _cy.animate({ center: { eles: node }, zoom: 1.4, duration: 400 });
      node.select();
    }
  }

  // ---------------------------------------------------------------------------
  // Fit-view button
  // ---------------------------------------------------------------------------
  function buildFitBtn() {
    const btn = document.createElement('button');
    btn.title = 'Fit all nodes in view';
    btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`;
    btn.style.cssText = `
      position:absolute;bottom:44px;left:12px;width:32px;height:32px;
      border-radius:6px;background:rgba(30,30,30,0.88);border:1px solid #3c3c3c;
      color:#ccc;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:10;
    `;
    btn.addEventListener('click', () => _cy && _cy.fit(undefined, 40));
    return btn;
  }

  // ---------------------------------------------------------------------------
  // Init on DOM ready
  // ---------------------------------------------------------------------------
  function onReady() {
    bootstrap();

    const wrapper = document.getElementById('canvas-wrapper');
    if (wrapper) wrapper.appendChild(buildFitBtn());

    window.CortexGraph = { render, addNode, highlightSearch, clearSearch, filterEdgesByLabel, focusNode };

    if (window._pendingGraph) {
      const { nodes, edges, diffData } = window._pendingGraph;
      render(nodes, edges, diffData);
      delete window._pendingGraph;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
```

- [ ] **Step 2: Run a live smoke test**

```bash
cortex init --root .
cortex run &
```
Open `http://localhost:7842` in a browser. Verify:
- Graph canvas renders (even if empty)
- No console errors about `vis` being undefined
- Status bar shows "0 nodes 0 edges"
- Dock buttons work (Timeline, Search, Filter, Vitals)
- `kill %1` to stop server

- [ ] **Step 3: Commit**

```bash
git add static/canvas.js
git commit -m "feat(canvas): replace vis-network with Cytoscape.js, Groups as compound nodes"
```

---

## Task 3: Vitals Panel

**Files:**
- Create: `static/panels/vitals.js`
- Create: `static/panels/` directory (mkdir)

The Vitals panel shows: Depth Score (% of SystemDesign nodes with rationale), Decision Arc badge counts, Blind Spots list (empty description), Keystones (top 5), Latent Bridges (top 5).

- [ ] **Step 1: Create static/panels/ directory**

```bash
mkdir static/panels
```

- [ ] **Step 2: Create static/panels/vitals.js**

```javascript
/**
 * vitals.js — Vitals panel for Cortex.
 * Called by index.html after DOM ready when the user opens the Vitals panel.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  async function renderVitals(nodes) {
    const container = document.getElementById('vitals-content');
    if (!container) return;

    // Depth Score
    const designNodes = nodes.filter(n => n.label === 'SystemDesign');
    const withRationale = designNodes.filter(n => n.rationale && n.rationale.trim());
    const depthPct = designNodes.length
      ? Math.round((withRationale.length / designNodes.length) * 100)
      : 0;

    // Decision Arc counts
    const arcCounts = { proposed: 0, building: 0, shipped: 0 };
    for (const n of designNodes) {
      if (n.status in arcCounts) arcCounts[n.status]++;
    }

    // Blind Spots
    const blindSpots = nodes.filter(n => !n.description || !n.description.trim()).slice(0, 10);

    // Keystones from API
    let keystones = [];
    try {
      const r = await fetch('/api/keystones?top_n=5');
      keystones = await r.json();
    } catch (_) {}

    // Latent Bridges from API
    let bridges = [];
    try {
      const r = await fetch('/api/latent-bridges?top_n=5');
      bridges = await r.json();
    } catch (_) {}

    container.innerHTML = `
      <div style="margin-bottom:14px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:6px">Depth Score</div>
        <div style="display:flex;align-items:center;gap:8px">
          <div style="font-size:28px;font-weight:700;color:${depthPct >= 70 ? '#4ade80' : depthPct >= 40 ? '#fb923c' : '#f87171'}">${depthPct}%</div>
          <div style="font-size:11px;color:var(--text-muted)">${withRationale.length}/${designNodes.length} design nodes<br>with rationale</div>
        </div>
      </div>

      <div style="margin-bottom:14px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:6px">Decision Arc</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span style="background:#1e3a2a;border:1px solid #2d6a4a;border-radius:10px;padding:2px 8px;font-size:11px;color:#4ade80">proposed ${arcCounts.proposed}</span>
          <span style="background:#3a2a1e;border:1px solid #6a4a2d;border-radius:10px;padding:2px 8px;font-size:11px;color:#fb923c">building ${arcCounts.building}</span>
          <span style="background:#1e2a3a;border:1px solid #2d4a6a;border-radius:10px;padding:2px 8px;font-size:11px;color:#60a5fa">shipped ${arcCounts.shipped}</span>
        </div>
      </div>

      ${keystones.length ? `
      <div style="margin-bottom:14px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:6px">Keystones</div>
        ${keystones.map(k => `
          <div style="display:flex;justify-content:space-between;padding:3px 0;font-size:11px;border-bottom:1px solid var(--border)">
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px">${esc(k.name || k.id)}</span>
            <span style="color:var(--text-muted);flex-shrink:0">${k.degree}↔</span>
          </div>
        `).join('')}
      </div>` : ''}

      ${bridges.length ? `
      <div style="margin-bottom:14px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:6px">Latent Bridges</div>
        ${bridges.map(b => `
          <div style="font-size:10px;color:var(--text-muted);padding:2px 0;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            C${b.src_cluster}↔C${b.dst_cluster} [${esc(b.rel)}]
          </div>
        `).join('')}
      </div>` : ''}

      ${blindSpots.length ? `
      <div style="margin-bottom:14px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);margin-bottom:6px">Blind Spots (no description)</div>
        ${blindSpots.map(n => `
          <div style="font-size:10px;color:#f87171;padding:2px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(n.name || n.id)}</div>
        `).join('')}
      </div>` : ''}
    `;
  }

  // Hook into panel switching — render when Vitals panel opens
  const origSetActivePanel = window.setActivePanel;
  window.setActivePanel = function (panel) {
    if (typeof origSetActivePanel === 'function') origSetActivePanel(panel);
    if (panel === 'vitals' && window._nodes) {
      renderVitals(window._nodes);
    }
  };

  // Also expose for external call after graph loads
  window.CortexVitals = { render: renderVitals };
})();
```

- [ ] **Step 3: Expose _nodes on window in index.html**

In the `handleWSMessage` function (in `index.html`), after `_nodes = msg.nodes || [];`, add:

```javascript
window._nodes = _nodes;
```

Do the same in `loadGraph`:
```javascript
_nodes = data.nodes || [];
window._nodes = _nodes;
```

- [ ] **Step 4: Smoke-test vitals panel**

```bash
cortex run &
```
Open `http://localhost:7842`, click the Vitals dock button. Verify:
- Panel renders with "Depth Score 0%" and "Decision Arc" badges
- No console errors
- `kill %1`

- [ ] **Step 5: Commit**

```bash
git add static/panels/vitals.js static/index.html
git commit -m "feat(ui): Vitals panel — Depth Score, Decision Arc badges, Keystones, Latent Bridges, Blind Spots"
```

---

## Task 4: Inspector Panel Module

**Files:**
- Create: `static/panels/inspector.js`

Extract the `onNodeClick` logic from `index.html` into a standalone module that adds Source Pins and Signal Cluster display to the inspector.

- [ ] **Step 1: Create static/panels/inspector.js**

```javascript
/**
 * inspector.js — Node Inspector panel for Cortex.
 * Enhances the onNodeClick handler in index.html with Source Pins
 * and Signal Cluster display.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function statusBadge(status) {
    const colors = {
      proposed: { bg: '#6b7280', text: '#fff' },
      building: { bg: '#ea580c', text: '#fff' },
      shipped:  { bg: '#059669', text: '#fff' },
    };
    const c = colors[status] || { bg: '#6b7280', text: '#fff' };
    return `<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;background:${c.bg};color:${c.text}">${esc(status)}</span>`;
  }

  function renderInspector(nodeId, nodes, edges, clusterData) {
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;

    const connectedEdges = edges.filter(e => e.src === nodeId || e.dst === nodeId);
    const isDesign = node.label === 'SystemDesign';

    // Find cluster for this node
    const cluster = (clusterData || []).find(c => c.members && c.members.includes(nodeId));

    const container = document.getElementById('inspector-content');
    container.innerHTML = `
      <div class="inspector-field">
        <div class="inspector-label">Type</div>
        <div class="inspector-value"><span class="inspector-badge">${esc(node.label || '?')}</span></div>
      </div>
      ${cluster ? `
      <div class="inspector-field">
        <div class="inspector-label">Signal Cluster</div>
        <div class="inspector-value" style="display:flex;align-items:center;gap:6px">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${esc(cluster.color)}"></span>
          <span style="font-size:11px;color:${esc(cluster.color)}">${esc(cluster.label)}</span>
        </div>
      </div>` : ''}
      ${isDesign && node.section ? `
      <div class="inspector-field">
        <div class="inspector-label">Section</div>
        <div class="inspector-value" style="color:#a78bfa;font-weight:600">${esc(node.section)}</div>
      </div>` : ''}
      <div class="inspector-field">
        <div class="inspector-label">Name</div>
        <div class="inspector-value">${esc(node.name) || '—'}</div>
      </div>
      ${node.status ? `
      <div class="inspector-field">
        <div class="inspector-label">Status</div>
        <div class="inspector-value">${statusBadge(node.status)}</div>
      </div>` : ''}
      <div class="inspector-field">
        <div class="inspector-label">Description</div>
        <div class="inspector-value">${esc(node.description) || '<span style="color:var(--text-muted);font-style:italic">No description — add one to improve Depth Score</span>'}</div>
      </div>
      ${isDesign && node.rationale ? `
      <div class="inspector-field">
        <div class="inspector-label">Rationale</div>
        <div class="inspector-value" style="font-style:italic;font-size:11px">${esc(node.rationale)}</div>
      </div>` : ''}
      ${node.source_file ? `
      <div class="inspector-field">
        <div class="inspector-label">Source Pin</div>
        <div class="inspector-value" style="font-family:monospace;font-size:10px">${esc(node.source_file)}${node.source_line ? `:${node.source_line}` : ''}</div>
      </div>` : ''}
      ${node.file_path ? `
      <div class="inspector-field">
        <div class="inspector-label">File Path</div>
        <div class="inspector-value" style="font-family:monospace;font-size:10px">${esc(node.file_path)}</div>
      </div>` : ''}
      <div class="inspector-field">
        <div class="inspector-label">ID</div>
        <div class="inspector-value" style="font-family:monospace;font-size:10px;color:var(--text-muted)">${esc(node.id)}</div>
      </div>
      <div class="inspector-field">
        <div class="inspector-label">Connections (${connectedEdges.length})</div>
        <ul class="inspector-connections">
          ${connectedEdges.map(e =>
            `<li>${e.src === nodeId ? '&rarr;' : '&larr;'} [${esc(e.rel)}] ${esc(e.src === nodeId ? e.dst : e.src)}</li>`
          ).join('') || '<li style="color:var(--text-muted)">No connections</li>'}
        </ul>
      </div>
    `;
  }

  // Override the global onNodeClick defined in index.html
  const _orig = window.onNodeClick;
  window.onNodeClick = function (nodeId) {
    if (typeof _orig === 'function') _orig(nodeId);
    // Enhance with cluster data
    const clusterData = window._clusterDataGlobal || [];
    if (window._nodes && window._edges) {
      renderInspector(nodeId, window._nodes, window._edges, clusterData);
    }
  };

  window.CortexInspector = { render: renderInspector };
})();
```

- [ ] **Step 2: Expose _edges and _clusterDataGlobal on window in canvas.js**

In `canvas.js`, after loading cluster data, add:
```javascript
.then(clusters => {
    _clusterData = clusters;
    _nodeCluster = {};
    for (const c of clusters) {
      for (const m of c.members) _nodeCluster[m] = c.id;
    }
    window._clusterDataGlobal = clusters;   // ← add this line
    applyClusterColors();
})
```

In `index.html`'s `loadGraph` function, after setting `_edges`, add:
```javascript
window._edges = _edges;
```

- [ ] **Step 3: Smoke-test inspector**

```bash
cortex run &
```
Open `http://localhost:7842`. Add a test node via MCP tool or direct DB insert, then click it. Verify:
- Inspector shows Source Pin row if `source_file` is set
- Status uses Decision Arc colours (proposed=grey, building=orange, shipped=green)
- `kill %1`

- [ ] **Step 4: Commit**

```bash
git add static/panels/inspector.js static/canvas.js static/index.html
git commit -m "feat(ui): Inspector panel with Source Pins + Signal Cluster display"
```

---

Phase 3 complete. Delivers: Cytoscape.js canvas, Groups as compound nodes, Signal Cluster rings, Vitals panel, enhanced Inspector panel.
