/**
 * canvas.js — Phase 5
 * Vis-Network graph canvas for Cortex.
 * Exposes window.CortexGraph = { render, addNode, highlight }
 */

(function () {
  'use strict';

  // -----------------------------------------------------------------------
  // Node type → default colour palette (visible on dark canvas)
  // -----------------------------------------------------------------------
  const TYPE_COLORS = {
    File:           { background: '#dbeafe', border: '#3b82f6', highlight: { background: '#bfdbfe', border: '#1d4ed8' } },
    SystemDesign:   { background: '#ede9fe', border: '#7c3aed', highlight: { background: '#ddd6fe', border: '#5b21b6' } },
    Service:        { background: '#ffedd5', border: '#ea580c', highlight: { background: '#fed7aa', border: '#c2410c' } },
    Database:       { background: '#d1fae5', border: '#059669', highlight: { background: '#a7f3d0', border: '#047857' } },
    Infrastructure: { background: '#e5e7eb', border: '#6b7280', highlight: { background: '#d1d5db', border: '#374151' } },
  };

  // Default fallback
  const COLOR_DEFAULT = { background: '#f3f4f6', border: '#9ca3af', highlight: { background: '#e5e7eb', border: '#6b7280' } };

  // Diff overlay colours (exactly from spec)
  const DIFF_ADDED    = { background: '#d4edda', border: '#28a745' };
  const DIFF_DELETED  = { background: '#f8d7da', border: '#dc3545' };
  const DIFF_MODIFIED = { background: '#fff3cd', border: '#ffc107' };

  // Edge colours by relationship type (default view)
  const REL_COLORS = {
    CONTAINS:    '#94a3b8',
    MODIFIES:    '#a78bfa',
    DEPENDS_ON:  '#60a5fa',
    QUERIES:     '#34d399',
    TALKS_TO:    '#fb923c',
    HOSTED_ON:   '#9ca3af',
    IMPLEMENTS:  '#c084fc',
    PART_OF:     '#818cf8',
    USES:        '#f97316',
    STORES_IN:   '#10b981',
    RUNS_ON:     '#6b7280',
  };

  const NODE_ICONS = {
    File: [
      'M13 2H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z',
      'M13 2v5h5',
    ],
    SystemDesign: [
      'M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5',
      'M14 2l4 4-7 7H7v-4z',
    ],
    Service: [
      'M2 3h18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z',
      'M8 21h6',
      'M12 17v4',
    ],
    Database: [
      'M12 2C7.03 2 3 3.79 3 6v2c0 2.21 4.03 4 9 4s9-1.79 9-4V6c0-2.21-4.03-4-9-4z',
      'M3 8v4c0 2.21 4.03 4 9 4s9-1.79 9-4V8',
      'M3 12v4c0 2.21 4.03 4 9 4s9-1.79 9-4v-4',
    ],
    Infrastructure: [
      'M2 2h18a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z',
      'M2 12h18a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2z',
      'M6 6h.01',
      'M6 16h.01',
    ],
  };

  function svgEsc(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function calcNodeWidth(name) {
    return Math.max(130, 44 + name.length * 7.5 + 18);
  }

  function buildNodeSVG(node, diffBorderColor) {
    const colors  = TYPE_COLORS[node.label] || COLOR_DEFAULT;
    const bg      = colors.background;
    const border  = colors.border;
    const name    = truncate(node.name || node.id || '', 28);
    const W       = calcNodeWidth(name);
    const H       = 38;
    const r       = 19;
    const cx      = 21;
    const cy      = 19;
    const cr      = 15;
    const scale   = 0.6;
    const ox      = cx - 24 * scale / 2;
    const oy      = cy - 24 * scale / 2;

    const iconPaths = (NODE_ICONS[node.label] || []).map(d =>
      `<path d="${svgEsc(d)}" transform="translate(${ox.toFixed(1)},${oy.toFixed(1)}) scale(${scale})"
        fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`
    ).join('');

    const diffRing = diffBorderColor
      ? `<rect x="0" y="0" width="${W}" height="${H}" rx="${r}" ry="${r}"
       fill="none" stroke="${svgEsc(diffBorderColor)}" stroke-width="3" opacity="0.9"/>`
      : '';

    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
  ${diffRing}
  <rect x="1" y="1" width="${W-2}" height="${H-2}" rx="${r}" ry="${r}"
    fill="${svgEsc(bg)}" stroke="${svgEsc(border)}" stroke-width="2"/>
  <circle cx="${cx}" cy="${cy}" r="${cr}" fill="${svgEsc(border)}"/>
  ${iconPaths}
  <text x="${cx + cr + 10}" y="${cy + 5}"
    font-family="Cascadia Code, Fira Code, Consolas, monospace"
    font-size="13" font-weight="600" fill="#1f2937">${svgEsc(name)}</text>
</svg>`;
  }

  function buildNodeImage(node, diffBorderColor) {
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(buildNodeSVG(node, diffBorderColor));
  }

  function nodeWidth(node) {
    const name = truncate(node.name || node.id || '', 28);
    return calcNodeWidth(name);
  }

  // -----------------------------------------------------------------------
  // Vis-Network options (from project spec)
  // -----------------------------------------------------------------------
  const VIS_OPTIONS = {
    nodes: {
      borderWidth: 2,
      shadow: { enabled: true, color: 'rgba(0,0,0,0.15)', size: 6, x: 2, y: 2 },
      chosen: {
        node: function (values) {
          values.borderWidth = 3;
          values.shadowSize = 10;
        },
      },
    },
    edges: {
      width: 1.5,
      arrows: { to: { enabled: true, scaleFactor: 0.7 } },
      font: { size: 11, face: 'Segoe UI, system-ui, sans-serif', color: '#6b7280', strokeWidth: 0 },
      smooth: { enabled: true, type: 'cubicBezier', roundness: 0.4 },
      color: { inherit: false },
      chosen: {
        edge: function (values, id, selected, hovering) {
          values.width = 2.5;
        },
      },
    },
    interaction: {
      dragNodes: false,        // locked — no overlapping layout disruption
      dragView: true,
      zoomView: true,
      hover: true,
      tooltipDelay: 200,
      navigationButtons: false,
      keyboard: { enabled: true, speed: { x: 20, y: 20, zoom: 0.05 } },
    },
    physics: {
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -4000,
        centralGravity: 0.15,
        springLength: 180,
        springConstant: 0.05,
        damping: 0.09,
        avoidOverlap: 0.3,
      },
      stabilization: { enabled: true, iterations: 1000, updateInterval: 50 },
    },
    layout: {
      improvedLayout: true,
    },
  };

  // -----------------------------------------------------------------------
  // Internal state
  // -----------------------------------------------------------------------
  let _network   = null;
  let _visNodes  = null;
  let _visEdges  = null;
  let _container = null;
  let _activeSearchQuery = '';
  let _hiddenEdgeLabels = new Set();

  // -----------------------------------------------------------------------
  // Draw background region boxes for SystemDesign section groups
  // -----------------------------------------------------------------------
  function drawSectionGroups(ctx) {
    if (!_visNodes || !_network) return;

    const groups = {};
    _visNodes.forEach(visNode => {
      const raw = visNode._raw;
      if (!raw || raw.label !== 'SystemDesign') return;
      const section = raw.section;
      if (!section) return;
      if (!groups[section]) groups[section] = [];
      groups[section].push(visNode.id);
    });

    if (Object.keys(groups).length === 0) return;

    const positions = _network.getPositions();

    Object.entries(groups).forEach(([section, nodeIds]) => {
      const pts = nodeIds.map(id => positions[id]).filter(Boolean);
      if (!pts.length) return;

      const pad = 40;
      const halfW = 80;  // node half-width (approx pill W/2)
      const halfH = 19;  // node half-height (38/2)
      const minX = Math.min(...pts.map(p => p.x)) - halfW - pad;
      const maxX = Math.max(...pts.map(p => p.x)) + halfW + pad;
      const minY = Math.min(...pts.map(p => p.y)) - halfH - pad;
      const maxY = Math.max(...pts.map(p => p.y)) + halfH + pad;
      const r = 12;

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(minX + r, minY);
      ctx.arcTo(maxX, minY, maxX, maxY, r);
      ctx.arcTo(maxX, maxY, minX, maxY, r);
      ctx.arcTo(minX, maxY, minX, minY, r);
      ctx.arcTo(minX, minY, maxX, minY, r);
      ctx.closePath();
      ctx.fillStyle = 'rgba(124,58,237,0.06)';
      ctx.fill();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = 'rgba(124,58,237,0.35)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.font = '700 10px "Segoe UI", system-ui, sans-serif';
      ctx.fillStyle = 'rgba(167,139,250,0.9)';
      ctx.fillText(section.toUpperCase(), minX + 10, minY + 14);
      ctx.restore();
    });
  }

  // -----------------------------------------------------------------------
  // Bootstrap — wait for DOM and vis-network to be ready
  // -----------------------------------------------------------------------
  function bootstrap() {
    _container = document.getElementById('graph-canvas');
    if (!_container) return;

    _visNodes = new vis.DataSet();
    _visEdges = new vis.DataSet();

    _network = new vis.Network(_container, { nodes: _visNodes, edges: _visEdges }, VIS_OPTIONS);

    _network.on('beforeDrawing', function(ctx) {
      drawSectionGroups(ctx);
    });

    _network.on('afterDrawing', renderMinimap);

    // Node click → inspector
    _network.on('click', function (params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        if (window.CortexUI && window.CortexUI.onNodeClick) {
          window.CortexUI.onNodeClick(nodeId);
        }
      }
    });

    // Double-click → fit view to that node's neighbourhood
    _network.on('doubleClick', function (params) {
      if (params.nodes.length > 0) {
        _network.focus(params.nodes[0], { scale: 1.2, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
      }
    });

  }

  // -----------------------------------------------------------------------
  // Transform raw API nodes/edges → Vis-Network format
  // -----------------------------------------------------------------------
  function toVisNode(node, diffData) {
    const isDashed = diffData && diffData.deleted_nodes && diffData.deleted_nodes.includes(node.id);
    const diffColor = diffData ? resolveDiffColor(node, diffData) : null;

    const visNode = {
      id: node.id,
      shape: 'image',
      image: buildNodeImage(node, diffColor ? diffColor.border : null),
      label: '',
      width: nodeWidth(node),
      height: 38,
      title: buildTooltip(node),
      shapeProperties: { useBorderWithImage: false, borderDashes: isDashed ? [5, 3] : false },
      _raw: node,
    };

    return visNode;
  }

  function resolveDiffColor(node, diffData) {
    if (!diffData) return null;
    if (diffData.added_nodes   && diffData.added_nodes.includes(node.id))    return DIFF_ADDED;
    if (diffData.deleted_nodes && diffData.deleted_nodes.includes(node.id))  return DIFF_DELETED;
    if (diffData.modified_nodes && diffData.modified_nodes.includes(node.id)) return DIFF_MODIFIED;
    return null;
  }

  function toVisEdge(edge, diffData, idx) {
    const edgeKey = edge.src + '|' + edge.rel + '|' + edge.dst;
    let color = REL_COLORS[edge.rel] || '#9ca3af';
    let dashes = false;
    let width = 1.5;

    if (diffData) {
      const addedKeys = (diffData.added_edges || []).map(e => e.src + '|' + e.rel + '|' + e.dst);
      const deletedKeys = (diffData.deleted_edges || []).map(e => e.src + '|' + e.rel + '|' + e.dst);

      if (addedKeys.includes(edgeKey)) {
        color = '#28a745';
        width = 2.5;
      } else if (deletedKeys.includes(edgeKey)) {
        color = '#dc3545';
        dashes = [6, 4];
        width = 2;
      }
    }

    return {
      id: edgeKey + '_' + idx,
      from: edge.src,
      to: edge.dst,
      label: edge.rel,
      color: { color, highlight: color, hover: color },
      dashes,
      width,
    };
  }

  function esc(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function buildTooltip(node) {
    // Vis-Network only renders HTML tooltips when title is a DOM element.
    // We use CSS classes injected by injectStyles() for a dark-theme look.
    const wrap = document.createElement('div');

    wrap.innerHTML = `
      <span class="tt-badge">${esc(node.label || 'Node')}</span>
      <strong>${esc(node.name || node.id)}</strong>
      <code>${esc(node.id)}</code>
      ${node.description ? `<div class="tt-row"><span class="tt-label">Desc</span><span class="tt-value">${esc(truncate(node.description, 90))}</span></div>` : ''}
      ${node.file_path   ? `<div class="tt-row"><span class="tt-label">Path</span><span class="tt-value" style="font-family:monospace;font-size:10px">${esc(node.file_path)}</span></div>` : ''}
      ${node.status      ? `<div class="tt-row"><span class="tt-label">Status</span><span class="tt-value">${esc(node.status)}</span></div>` : ''}
      ${node.section     ? `<div class="tt-row"><span class="tt-label">Section</span><span class="tt-value" style="color:#a78bfa">${esc(node.section)}</span></div>` : ''}
      ${node.rationale   ? `<div class="tt-row"><span class="tt-label">Why</span><span class="tt-value" style="font-style:italic">${esc(truncate(node.rationale, 80))}</span></div>` : ''}
      ${node.provider    ? `<div class="tt-row"><span class="tt-label">Provider</span><span class="tt-value">${esc(node.provider)}</span></div>` : ''}
      ${node.endpoint    ? `<div class="tt-row"><span class="tt-label">Endpoint</span><span class="tt-value" style="font-size:10px">${esc(node.endpoint)}</span></div>` : ''}
    `;
    return wrap;
  }

  function truncate(str, max) {
    return str.length > max ? str.slice(0, max) + '…' : str;
  }

  // -----------------------------------------------------------------------
  // Public API — window.CortexGraph
  // -----------------------------------------------------------------------

  /**
   * Full render: replace all nodes and edges on the canvas.
   * @param {Array} nodes  - raw node objects from /api/graph
   * @param {Array} edges  - raw edge objects from /api/graph
   * @param {Object|null} diffData - from /api/diff, or null for live view
   */
  function render(nodes, edges, diffData) {
    if (!_network) return;

    const visNodes = nodes.map(n => toVisNode(n, diffData));
    const visEdges = edges.map((e, i) => toVisEdge(e, diffData, i));

    _visNodes.clear();
    _visEdges.clear();
    _visNodes.add(visNodes);
    _visEdges.add(visEdges);

    // Re-apply search highlighting if a query was active before the reload
    if (_activeSearchQuery) highlightSearch(_activeSearchQuery);

    // Re-apply edge filter if any labels are hidden
    if (_hiddenEdgeLabels.size > 0) filterEdgesByLabel(_hiddenEdgeLabels);

    // Re-run stabilisation after data change
    _network.stabilize(300);
  }

  /**
   * Incremental add — called when write_system_design_node pushes via WebSocket.
   * @param {Object} node - single raw node
   * @param {Array}  edges - new edges involving this node
   */
  function addNode(node, edges) {
    if (!_network) return;

    // Animate the new node in
    const visNode = toVisNode(node, null);
    _visNodes.add(visNode);

    edges.forEach((e, i) => {
      // Only add edge if both endpoints already exist in the dataset
      if (_visNodes.get(e.src) || _visNodes.get(e.dst)) {
        try {
          _visEdges.add(toVisEdge(e, null, Date.now() + i));
        } catch (_) { /* duplicate */ }
      }
    });

    // Re-apply search highlighting if a query is active
    if (_activeSearchQuery) highlightSearch(_activeSearchQuery);
    // Re-apply edge filter if any labels are hidden
    if (_hiddenEdgeLabels.size > 0) filterEdgesByLabel(_hiddenEdgeLabels);

    // Briefly highlight the new node
    _network.selectNodes([node.id]);
    setTimeout(() => _network.unselectAll(), 2000);
  }

  /**
   * Fit the entire graph into view.
   */
  function fitAll() {
    if (_network) _network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
  }

  function highlightSearch(query) {
    _activeSearchQuery = query;
    if (!_visNodes || !_network) return;
    if (!query) { clearSearch(); return; }
    const q = query.toLowerCase();
    const updates = [];
    _visNodes.forEach(visNode => {
      const raw = visNode._raw || {};
      const match = (raw.name || '').toLowerCase().includes(q)
                 || (raw.id  || '').toLowerCase().includes(q);
      updates.push({ id: visNode.id, color: { opacity: match ? 1.0 : 0.12 } });
    });
    _visNodes.update(updates);
  }

  function clearSearch() {
    _activeSearchQuery = '';
    if (!_visNodes) return;
    const updates = [];
    _visNodes.forEach(v => updates.push({ id: v.id, color: { opacity: 1.0 } }));
    _visNodes.update(updates);
  }

  function filterEdgesByLabel(hiddenLabels) {
    _hiddenEdgeLabels = hiddenLabels;
    if (!_visEdges) return;
    const updates = [];
    _visEdges.forEach(e => {
      updates.push({ id: e.id, hidden: _hiddenEdgeLabels.has(e.label) });
    });
    _visEdges.update(updates);
  }

  // -----------------------------------------------------------------------
  // Legend overlay
  // -----------------------------------------------------------------------
  function buildLegend() {
    const legend = document.createElement('div');
    legend.id = 'canvas-legend';
    legend.style.cssText = `
      position: absolute; bottom: 36px; right: 150px;
      background: rgba(30,30,30,0.88); border: 1px solid #3c3c3c;
      border-radius: 6px; padding: 10px 14px; z-index: 10;
      font-size: 11px; color: #ccc; line-height: 1.8;
      pointer-events: none;
    `;

    const typeEntries = Object.entries(TYPE_COLORS).map(([label, c]) =>
      `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${c.border};margin-right:5px;vertical-align:middle"></span>${label}`
    );
    const diffEntries = [
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_ADDED.background};border:1.5px solid ${DIFF_ADDED.border};margin-right:5px;vertical-align:middle"></span>Added`,
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_DELETED.background};border:1.5px solid ${DIFF_DELETED.border};margin-right:5px;vertical-align:middle"></span>Deleted`,
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_MODIFIED.background};border:1.5px solid ${DIFF_MODIFIED.border};margin-right:5px;vertical-align:middle"></span>Modified`,
    ];

    legend.innerHTML = [
      ...typeEntries,
      '<hr style="border-color:#3c3c3c;margin:4px 0">',
      ...diffEntries,
    ].map(e => `<div>${e}</div>`).join('');
    return legend;
  }

  // -----------------------------------------------------------------------
  // Fit-view button
  // -----------------------------------------------------------------------
  function buildFitBtn() {
    const btn = document.createElement('button');
    btn.id = 'canvas-fit-btn';
    btn.title = 'Fit all nodes in view';
    btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`;
    btn.style.cssText = `
      position: absolute; bottom: 44px; left: 12px;
      width: 32px; height: 32px; border-radius: 6px;
      background: rgba(30,30,30,0.88); border: 1px solid #3c3c3c;
      color: #ccc; cursor: pointer; display: flex;
      align-items: center; justify-content: center; z-index: 10;
    `;
    btn.addEventListener('click', fitAll);
    return btn;
  }

  // -----------------------------------------------------------------------
  // Inject tooltip + scrollbar CSS for the dark theme
  // -----------------------------------------------------------------------
  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      /* Override Vis-Network default tooltip */
      .vis-tooltip {
        background: #1a1a2e !important;
        border: 1px solid #3c3c5a !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5) !important;
        color: #e2e8f0 !important;
        font-family: 'Segoe UI', system-ui, sans-serif !important;
        font-size: 12px !important;
        line-height: 1.6 !important;
        max-width: 280px !important;
        pointer-events: none;
      }
      /* Inner DOM elements we build inside buildTooltip */
      .vis-tooltip strong {
        display: block;
        font-size: 13px;
        color: #f1f5f9;
        margin-bottom: 2px;
        font-weight: 600;
      }
      .vis-tooltip code {
        display: block;
        font-size: 10px !important;
        color: #64748b !important;
        font-family: 'Cascadia Code', 'Fira Code', monospace !important;
        margin-bottom: 6px;
        word-break: break-all;
        border-bottom: 1px solid #2d2d4a;
        padding-bottom: 5px;
      }
      .vis-tooltip .tt-row {
        display: flex;
        gap: 6px;
        margin-top: 2px;
      }
      .vis-tooltip .tt-label {
        color: #64748b;
        flex-shrink: 0;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .vis-tooltip .tt-value {
        color: #cbd5e1;
        font-size: 12px;
      }
      .vis-tooltip .tt-badge {
        display: inline-block;
        padding: 1px 7px;
        border-radius: 10px;
        font-size: 10px;
        font-weight: 700;
        background: #1e40af;
        color: #bfdbfe;
        margin-bottom: 5px;
      }
    `;
    document.head.appendChild(style);
  }

  // -----------------------------------------------------------------------
  // Minimap overlay
  // -----------------------------------------------------------------------
  let _minimapCanvas = null;

  function initMinimap() {
    _minimapCanvas = document.getElementById('minimap-canvas');
    if (!_minimapCanvas) return;
    const dpr = window.devicePixelRatio || 1;
    _minimapCanvas.width  = 130 * dpr;
    _minimapCanvas.height = 90  * dpr;
    const mctx = _minimapCanvas.getContext('2d');
    mctx.scale(dpr, dpr);

    _minimapCanvas.addEventListener('click', function(e) {
      if (!_network) return;
      const rect = _minimapCanvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width;
      const my = (e.clientY - rect.top)  / rect.height;
      const { minX, maxX, minY, maxY } = minimapBounds();
      if (minX === undefined) return;
      const gx = minX + mx * (maxX - minX);
      const gy = minY + my * (maxY - minY);
      _network.moveTo({ position: { x: gx, y: gy }, animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    });
  }

  function minimapBounds() {
    const positions = _network ? _network.getPositions() : {};
    const pts = Object.values(positions);
    if (!pts.length) return {};
    const pad = 60;
    return {
      minX: Math.min(...pts.map(p => p.x)) - pad,
      maxX: Math.max(...pts.map(p => p.x)) + pad + 160,
      minY: Math.min(...pts.map(p => p.y)) - pad,
      maxY: Math.max(...pts.map(p => p.y)) + pad + 38,
    };
  }

  function renderMinimap() {
    if (!_minimapCanvas || !_network) return;
    const mW = 130, mH = 90;
    const mctx = _minimapCanvas.getContext('2d');
    mctx.clearRect(0, 0, mW, mH);

    const bounds = minimapBounds();
    if (bounds.minX === undefined) return;
    const { minX, maxX, minY, maxY } = bounds;
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const toMX = gx => ((gx - minX) / rangeX) * mW;
    const toMY = gy => ((gy - minY) / rangeY) * mH;

    if (_visNodes) {
      const positions = _network.getPositions();
      _visNodes.forEach(visNode => {
        const pos = positions[visNode.id];
        if (!pos) return;
        const raw = visNode._raw;
        const colors = TYPE_COLORS[(raw && raw.label)] || COLOR_DEFAULT;
        mctx.fillStyle = colors.border;
        mctx.beginPath();
        mctx.roundRect(toMX(pos.x), toMY(pos.y), 8, 5, 2);
        mctx.fill();
      });
    }

    const graphCanvas = _network.canvas.frame.canvas;
    const tl = _network.DOMtoCanvas({ x: 0, y: 0 });
    const br = _network.DOMtoCanvas({ x: graphCanvas.clientWidth, y: graphCanvas.clientHeight });
    mctx.strokeStyle = 'rgba(255,255,255,0.4)';
    mctx.lineWidth = 1;
    mctx.strokeRect(
      toMX(tl.x), toMY(tl.y),
      toMX(br.x) - toMX(tl.x),
      toMY(br.y) - toMY(tl.y)
    );
  }

  // -----------------------------------------------------------------------
  // Init on DOM ready
  // -----------------------------------------------------------------------
  function onReady() {
    injectStyles();
    bootstrap();
    initMinimap();

    // Attach legend + fit button to canvas wrapper
    const wrapper = document.getElementById('canvas-wrapper');
    if (wrapper) {
      wrapper.appendChild(buildLegend());
      wrapper.appendChild(buildFitBtn());
    }

    // Expose public API + raw network for debugging
    window.CortexGraph = { render, addNode, fitAll, highlightSearch, clearSearch, filterEdgesByLabel };
    window._cortexNetwork = _network;

    // If init data arrived before canvas was ready, render it now
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
