/**
 * canvas.js — Cytoscape graph renderer v3 (full redesign)
 * Exposes window.CortexGraph = { render, addNode, highlightSearch, clearSearch,
 *                                  filterEdgesByLabel, focusNode, screenshot }
 */
(function () {
  'use strict';

  // ── Type palette: dark-mode graph chips ──────────────────────────────────
  // fg = icon & text, bg = node fill, bdr = border
  const TYPE_PAL = {
    Service:        { fg: '#818cf8', bg: 'rgba(99,102,241,0.09)',  bdr: 'rgba(99,102,241,0.55)'  },
    Database:       { fg: '#34d399', bg: 'rgba(52,211,153,0.09)',  bdr: 'rgba(52,211,153,0.55)'  },
    Infrastructure: { fg: '#fbbf24', bg: 'rgba(251,191,36,0.09)',  bdr: 'rgba(251,191,36,0.55)'  },
    File:           { fg: '#38bdf8', bg: 'rgba(56,189,248,0.09)',   bdr: 'rgba(56,189,248,0.55)'  },
    SystemDesign:   { fg: '#c084fc', bg: 'rgba(192,132,252,0.09)', bdr: 'rgba(192,132,252,0.55)' },
  };

  const DIFF_PAL = {
    added:    { bg: 'rgba(34,197,94,0.12)',  bdr: '#22c55e' },
    deleted:  { bg: 'rgba(239,68,68,0.12)',  bdr: '#ef4444' },
    modified: { bg: 'rgba(251,191,36,0.12)', bdr: '#fbbf24' },
  };

  // ── SVG icon factory ─────────────────────────────────────────────────────
  // 16×16 viewport, 1.4px stroke, designed for 14px rendered size.
  function _svg(color, body) {
    return `data:image/svg+xml,${encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="${color}" ` +
      `stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`
    )}`;
  }

  const ICONS = {
    // WiFi broadcast — service sends/receives data
    Service: (c) => _svg(c,
      `<circle cx="8" cy="11.5" r="1.5" fill="${c}" stroke="none"/>` +
      `<path d="M5.34 8.34a3.75 3.75 0 0 1 5.32 0"/>` +
      `<path d="M2.93 5.93a7.5 7.5 0 0 1 10.14 0"/>`
    ),
    // Stacked cylinders — database
    Database: (c) => _svg(c,
      `<ellipse cx="8" cy="4.5" rx="5" ry="2"/>` +
      `<path d="M3 4.5v7c0 1.1 2.24 2 5 2s5-.9 5-2v-7"/>` +
      `<path d="M3 7.5c0 1.1 2.24 2 5 2s5-.9 5-2"/>`
    ),
    // Server rack with LED dots — infrastructure
    Infrastructure: (c) => _svg(c,
      `<rect x="2" y="2.5" width="12" height="4" rx="1"/>` +
      `<rect x="2" y="9.5" width="12" height="4" rx="1"/>` +
      `<circle cx="11.5" cy="4.5" r="1" fill="${c}" stroke="none"/>` +
      `<circle cx="11.5" cy="11.5" r="1" fill="${c}" stroke="none"/>` +
      `<line x1="4" y1="4.5" x2="8.5" y2="4.5"/>` +
      `<line x1="4" y1="11.5" x2="8.5" y2="11.5"/>`
    ),
    // Document with fold corner — file
    File: (c) => _svg(c,
      `<path d="M10 2H4.5A1.5 1.5 0 0 0 3 3.5v9A1.5 1.5 0 0 0 4.5 14h7A1.5 1.5 0 0 0 13 12.5V6L10 2z"/>` +
      `<polyline points="10 2 10 6 13 6"/>` +
      `<line x1="5.5" y1="9" x2="10.5" y2="9"/>` +
      `<line x1="5.5" y1="11.5" x2="9" y2="11.5"/>`
    ),
    // Hexagon with center node — design pattern / decision
    SystemDesign: (c) => _svg(c,
      `<polygon points="8,2 13.5,5 13.5,11 8,14 2.5,11 2.5,5"/>` +
      `<circle cx="8" cy="8" r="2.5" fill="${c}" stroke="none" opacity="0.55"/>`
    ),
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let _cy             = null;
  let _hiddenEdgeLabels = new Set();
  let _clusterData    = [];
  let _nodeCluster    = {};

  // ── Stylesheet ────────────────────────────────────────────────────────────
  function buildStyle() {
    // Per-type styled chips
    const typeStyles = Object.entries(TYPE_PAL).map(([label, p]) => ({
      selector: `node.${label}`,
      style: {
        'background-color':      p.bg,
        'border-color':          p.bdr,
        'color':                 p.fg,
        ...(ICONS[label] ? {
          'background-image':      ICONS[label](p.fg),
          'background-width':      '14px',
          'background-height':     '14px',
          'background-position-x': '9px',
          'background-position-y': '50%',
          'background-clip':       'none',
        } : {}),
      },
    }));

    const MONO = 'Consolas, monospace';

    return [
      // ── Base node chip ─────────────────────────────────────────
      {
        selector: 'node',
        style: {
          'label':             'data(displayName)',
          'font-size':         '10.5px',
          'font-family':       MONO,
          'font-weight':       500,
          'color':             '#71717a',         // zinc-500
          'text-valign':       'center',
          'text-halign':       'center',
          'text-margin-x':     7,
          'width':             'label',
          'height':            '26px',
          'padding':           '5px 10px 5px 28px',
          'shape':             'roundrectangle',
          'border-width':      1,
          'border-color':      '#27272a',
          'background-color':  '#131318',
          'text-wrap':         'none',
          'min-width':         '52px',
        },
      },

      // ── Type chips ─────────────────────────────────────────────
      ...typeStyles,

      // ── Group container (compound parent) ──────────────────────
      {
        selector: 'node:parent',
        style: {
          'label':             'data(displayName)',
          'text-valign':       'top',
          'text-halign':       'left',
          'font-size':         '8.5px',
          'font-weight':       700,
          'font-family':       MONO,
          'color':             '#3f3f46',          // zinc-700
          'text-margin-x':     10,
          'text-margin-y':     8,
          'background-color':  '#0f0f14',
          'border-color':      '#2a2a36',
          'border-width':      1,
          'border-style':      'dashed',
          'padding':           '30px 12px 12px',
          'background-image':  'none',
        },
      },

      // ── Selection highlight ─────────────────────────────────────
      {
        selector: 'node:selected',
        style: {
          'border-color':    '#6366f1',
          'border-width':    2,
        },
      },
      {
        selector: 'node:parent:selected',
        style: {
          'border-color': '#6366f1',
          'border-width': 1.5,
        },
      },

      // ── Search fade ────────────────────────────────────────────
      { selector: 'node.faded', style: { 'opacity': 0.10 } },

      // ── Diff overlays ──────────────────────────────────────────
      { selector: 'node.diff-added',    style: { 'background-color': DIFF_PAL.added.bg,    'border-color': DIFF_PAL.added.bdr,    'border-width': 2 } },
      { selector: 'node.diff-deleted',  style: { 'background-color': DIFF_PAL.deleted.bg,  'border-color': DIFF_PAL.deleted.bdr,  'border-width': 2 } },
      { selector: 'node.diff-modified', style: { 'background-color': DIFF_PAL.modified.bg, 'border-color': DIFF_PAL.modified.bdr, 'border-width': 2 } },

      // ── Edges ──────────────────────────────────────────────────
      {
        selector: 'edge',
        style: {
          'width':                    1,
          'line-color':               '#27272a',
          'target-arrow-color':       '#27272a',
          'target-arrow-shape':       'triangle',
          'arrow-scale':              0.65,
          'curve-style':              'bezier',
          'label':                    'data(rel)',
          'font-size':                '7.5px',
          'font-family':              MONO,
          'color':                    '#3f3f46',
          'text-background-color':    '#09090b',
          'text-background-opacity':  0.88,
          'text-background-padding':  '2px',
          'text-border-opacity':      0,
        },
      },
      {
        selector: 'edge:selected',
        style: {
          'width':              2,
          'line-color':         '#6366f1',
          'target-arrow-color': '#6366f1',
          'color':              '#818cf8',
        },
      },
      { selector: 'edge.hidden',       style: { 'display': 'none' } },
      { selector: 'edge.diff-added',   style: { 'line-color': '#22c55e', 'target-arrow-color': '#22c55e', 'width': 2 } },
      { selector: 'edge.diff-deleted', style: { 'line-color': '#ef4444', 'target-arrow-color': '#ef4444', 'line-style': 'dashed' } },
    ];
  }

  // ── Element conversion ────────────────────────────────────────────────────
  function toElements(nodes, edges, diffData) {
    const parentMap      = {};
    const nonMemberEdges = [];

    for (const e of edges) {
      if (e.rel === 'MEMBER_OF') parentMap[e.src] = e.dst;
      else nonMemberEdges.push(e);
    }

    const elements = [];

    for (const n of nodes) {
      const name        = n.name || n.id || '';
      const displayName = name.length > 26 ? name.slice(0, 26) + '…' : name;
      const data        = { id: n.id, displayName, label: n.label, ...n };
      if (parentMap[n.id]) data.parent = parentMap[n.id];

      const classes = [n.label || 'Unknown'];
      if (diffData) {
        if ((diffData.added_nodes   || []).includes(n.id)) classes.push('diff-added');
        else if ((diffData.deleted_nodes  || []).includes(n.id)) classes.push('diff-deleted');
        else if ((diffData.modified_nodes || []).includes(n.id)) classes.push('diff-modified');
      }
      elements.push({ data, classes: classes.join(' ') });
    }

    for (let i = 0; i < nonMemberEdges.length; i++) {
      const e     = nonMemberEdges[i];
      const eData = { id: `${e.src}|${e.rel}|${e.dst}_${i}`, source: e.src, target: e.dst, rel: e.rel };
      const cls   = [];
      if (diffData) {
        const addK = (diffData.added_edges   || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        const delK = (diffData.deleted_edges || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        const key  = `${e.src}|${e.rel}|${e.dst}`;
        if (addK.includes(key)) cls.push('diff-added');
        else if (delK.includes(key)) cls.push('diff-deleted');
      }
      elements.push({ data: eData, classes: cls.join(' ') });
    }

    return elements;
  }

  // ── Cluster ring coloring ─────────────────────────────────────────────────
  function applyClusterColors() {
    if (!_cy || !_clusterData.length) return;
    for (const cluster of _clusterData) {
      for (const id of cluster.members) {
        const node = _cy.getElementById(id);
        if (node.length) node.style({ 'border-color': cluster.color, 'border-width': 2 });
      }
    }
  }

  // ── Minimap ───────────────────────────────────────────────────────────────
  function buildMinimap() {
    const mm = document.createElement('div');
    mm.id = 'cortex-minimap';
    Object.assign(mm.style, {
      position: 'absolute', bottom: '50px', right: '12px',
      width: '168px', height: '120px',
      background: 'rgba(9,9,11,0.92)',
      border: '1px solid #27272a',
      borderRadius: '8px',
      overflow: 'hidden', zIndex: '10',
      boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      pointerEvents: 'none',
    });

    const lbl = document.createElement('div');
    lbl.textContent = 'OVERVIEW';
    Object.assign(lbl.style, {
      position: 'absolute', top: '5px', left: '8px',
      fontSize: '7.5px', color: '#3f3f46',
      fontFamily: "'Geist Mono','Cascadia Code',monospace",
      letterSpacing: '0.12em', fontWeight: '700', zIndex: '1',
    });

    const img = document.createElement('img');
    img.id = 'cortex-minimap-img';
    Object.assign(img.style, {
      position: 'absolute', top: '18px', left: '0',
      width: '100%', height: 'calc(100% - 18px)',
      objectFit: 'contain',
    });

    mm.appendChild(lbl);
    mm.appendChild(img);
    return mm;
  }

  function refreshMinimap() {
    if (!_cy) return;
    const img = document.getElementById('cortex-minimap-img');
    if (!img) return;
    requestAnimationFrame(() => {
      try {
        img.src = _cy.png({ output: 'base64uri', bg: '#09090b', full: true, scale: 0.20 });
      } catch (_) {}
    });
  }

  // ── Layout ────────────────────────────────────────────────────────────────
  function pickLayout() {
    if (typeof cytoscapeDagre !== 'undefined') {
      return {
        name:   'dagre',
        rankDir: 'LR',
        nodeSep: 22,
        rankSep: 64,
        padding: 40,
        animate: true,
        animationDuration: 420,
        nodeDimensionsIncludeLabels: true,
        ranker: 'network-simplex',
        align:  'UL',
      };
    }
    if (typeof cytoscapeCoseBilkent !== 'undefined') {
      return {
        name:   'cose-bilkent',
        animate: true,
        animationDuration: 500,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 100,
        nodeRepulsion: 8000,
        gravity: 0.25,
        numIter: 2500,
        randomize: false,
      };
    }
    return { name: 'cose', animate: true, animationDuration: 500 };
  }

  // ── Zoom toolbar ──────────────────────────────────────────────────────────
  function buildToolbar() {
    const bar = document.createElement('div');
    Object.assign(bar.style, {
      position: 'absolute', bottom: '50px', left: '12px',
      display: 'flex', flexDirection: 'column', gap: '3px', zIndex: '10',
    });

    const s = `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"`;

    function btn(title, svg, onClick) {
      const b = document.createElement('button');
      b.title   = title;
      b.innerHTML = svg;
      Object.assign(b.style, {
        width: '30px', height: '30px', borderRadius: '7px',
        background: 'rgba(9,9,11,0.88)', border: '1px solid #27272a',
        color: '#52525b', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'color 0.15s, border-color 0.15s',
      });
      b.addEventListener('mouseenter', () => { b.style.color = '#a1a1aa'; b.style.borderColor = '#3f3f46'; });
      b.addEventListener('mouseleave', () => { b.style.color = '#52525b'; b.style.borderColor = '#27272a'; });
      b.addEventListener('click', onClick);
      return b;
    }

    bar.appendChild(btn('Fit view',
      `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" ${s}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,
      () => _cy && _cy.fit(undefined, 40)
    ));
    bar.appendChild(btn('Zoom in',
      `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
      () => _cy && _cy.zoom({ level: _cy.zoom() * 1.25, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })
    ));
    bar.appendChild(btn('Zoom out',
      `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
      () => _cy && _cy.zoom({ level: _cy.zoom() / 1.25, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })
    ));

    return bar;
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  function bootstrap() {
    const container = document.getElementById('graph-canvas');
    if (!container) return;

    if (typeof cytoscapeCoseBilkent !== 'undefined') cytoscape.use(cytoscapeCoseBilkent);
    if (typeof cytoscapeDagre       !== 'undefined') cytoscape.use(cytoscapeDagre);

    _cy = cytoscape({
      container,
      elements:            [],
      style:               buildStyle(),
      layout:              { name: 'grid' },
      autoungrabify:       true,
      boxSelectionEnabled: true,
      minZoom:             0.05,
      maxZoom:             4,
    });

    _cy.on('tap', 'node', function (evt) {
      const node = evt.target;
      if (node.isParent()) return;
      if (window.CortexUI && window.CortexUI.onNodeClick) window.CortexUI.onNodeClick(node.id());
    });

    _cy.on('dbltap', 'node', function (evt) {
      _cy.animate({
        fit: { eles: evt.target.neighborhood().add(evt.target), padding: 60 },
        duration: 350,
      });
    });

    fetch('/api/clusters')
      .then(r => r.json())
      .then(clusters => {
        _clusterData = clusters;
        _nodeCluster = {};
        for (const c of clusters) for (const m of c.members) _nodeCluster[m] = c.id;
        window._clusterDataGlobal = clusters;
        applyClusterColors();
      })
      .catch(() => {});
  }

  // ── Public render API ─────────────────────────────────────────────────────
  function render(nodes, edges, diffData) {
    if (!_cy) return;
    _cy.elements().remove();
    _cy.add(toElements(nodes, edges, diffData));

    const layout = _cy.layout(pickLayout());
    layout.one('layoutstop', () => {
      applyClusterColors();
      refreshMinimap();
    });
    layout.run();

    if (window._cortexSearchQuery) highlightSearch(window._cortexSearchQuery);
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
  }

  function addNode(node, edges) {
    if (!_cy) return;
    _cy.add(toElements([node], edges, null));
    const el = _cy.getElementById(node.id);
    if (el.length) {
      el.layout({ name: 'concentric', animate: true }).run();
      el.select();
      setTimeout(() => el.unselect(), 2000);
    }
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
    applyClusterColors();
    refreshMinimap();
  }

  function highlightSearch(query) {
    window._cortexSearchQuery = query;
    if (!_cy) return;
    const q = query.toLowerCase();
    _cy.nodes().forEach(n => {
      const d = n.data();
      const match = (d.name || '').toLowerCase().includes(q) || (d.id || '').toLowerCase().includes(q);
      if (match) n.removeClass('faded');
      else       n.addClass('faded');
    });
  }

  function clearSearch() {
    window._cortexSearchQuery = '';
    if (_cy) _cy.nodes().removeClass('faded');
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
      _cy.animate({ center: { eles: node }, zoom: 1.8, duration: 350 });
      node.select();
    }
  }

  function screenshot() {
    if (!_cy) return null;
    return _cy.png({ output: 'base64uri', bg: '#09090b', full: false });
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function onReady() {
    bootstrap();

    const wrapper = document.getElementById('canvas-wrapper');
    if (wrapper) {
      wrapper.appendChild(buildToolbar());
      wrapper.appendChild(buildMinimap());
    }

    window.CortexGraph = { render, addNode, highlightSearch, clearSearch, filterEdgesByLabel, focusNode, screenshot };

    if (window._pendingGraph) {
      const { nodes, edges, diffData } = window._pendingGraph;
      render(nodes, edges, diffData);
      delete window._pendingGraph;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady);
  else onReady();
})();
