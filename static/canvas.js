/**
 * canvas.js — Cytoscape graph renderer v4 (light mode, iOS-style, fixed labels/icons)
 */
(function () {
  'use strict';

  // ── Light-mode chip palettes ──────────────────────────────────────────────
  // bg  = node fill (soft tint)
  // txt = dark readable text
  // bdr = border stroke
  const TYPE_PAL = {
    Service:        { bg: '#eef2ff', txt: '#4338ca', bdr: '#a5b4fc' },
    Database:       { bg: '#ecfdf5', txt: '#065f46', bdr: '#6ee7b7' },
    Infrastructure: { bg: '#fffbeb', txt: '#92400e', bdr: '#fcd34d' },
    File:           { bg: '#e0f2fe', txt: '#0c4a6e', bdr: '#7dd3fc' },
    SystemDesign:   { bg: '#faf5ff', txt: '#6b21a8', bdr: '#d8b4fe' },
  };

  const DIFF_PAL = {
    added:    { bg: '#f0fdf4', bdr: '#22c55e' },
    deleted:  { bg: '#fef2f2', bdr: '#ef4444' },
    modified: { bg: '#fffbeb', bdr: '#f59e0b' },
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let _cy              = null;
  let _hiddenEdgeLabels = new Set();
  let _clusterData     = [];

  // ── Stylesheet ────────────────────────────────────────────────────────────
  function buildStyle() {
    const typeStyles = Object.entries(TYPE_PAL).map(([label, p]) => ({
      selector: `node.${label}`,
      style: {
        'background-color': p.bg,
        'border-color':     p.bdr,
        'color':            p.txt,
      },
    }));

    return [
      // ── Base node chip ────────────────────────────────────────────
      {
        selector: 'node',
        style: {
          'label':            'data(displayName)',
          'font-size':        '11px',
          'font-family':      'Consolas, monospace',
          'font-weight':      600,
          'color':            '#374151',
          'text-valign':      'center',
          'text-halign':      'center',
          'width':            'label',
          'height':           '28px',
          'padding':          '6px 14px',
          'shape':            'roundrectangle',
          'border-width':     1.5,
          'border-color':     '#e5e7eb',
          'background-color': '#ffffff',
          'text-wrap':        'none',
          'min-width':        '60px',
        },
      },

      // ── Type chips ────────────────────────────────────────────────
      ...typeStyles,

      // ── Group container ───────────────────────────────────────────
      {
        selector: 'node:parent',
        style: {
          'label':            'data(displayName)',
          'font-size':        '9px',
          'font-family':      'Consolas, monospace',
          'font-weight':      700,
          'color':            '#9ca3af',
          'text-valign':      'top',
          'text-halign':      'center',   // centered = INSIDE the box, not left edge
          'text-margin-y':    10,         // push down 10px inside the top border
          'background-color': '#fafafa',
          'background-image': 'none',
          'border-color':     '#e5e7eb',
          'border-width':     1.5,
          'border-style':     'dashed',
          'padding':          '28px 12px 12px',
        },
      },

      // ── Selected ──────────────────────────────────────────────────
      {
        selector: 'node:selected',
        style: {
          'border-color': '#6366f1',
          'border-width':  2.5,
        },
      },
      {
        selector: 'node:parent:selected',
        style: {
          'border-color': '#6366f1',
          'border-width':  2,
        },
      },

      // ── Search fade ───────────────────────────────────────────────
      { selector: 'node.faded', style: { 'opacity': 0.12 } },

      // ── Diff overlays ─────────────────────────────────────────────
      { selector: 'node.diff-added',    style: { 'background-color': DIFF_PAL.added.bg,    'border-color': DIFF_PAL.added.bdr,    'border-width': 2 } },
      { selector: 'node.diff-deleted',  style: { 'background-color': DIFF_PAL.deleted.bg,  'border-color': DIFF_PAL.deleted.bdr,  'border-width': 2 } },
      { selector: 'node.diff-modified', style: { 'background-color': DIFF_PAL.modified.bg, 'border-color': DIFF_PAL.modified.bdr, 'border-width': 2 } },

      // ── Edges ─────────────────────────────────────────────────────
      {
        selector: 'edge',
        style: {
          'width':                   1,
          'line-color':              '#d1d5db',
          'target-arrow-color':      '#d1d5db',
          'target-arrow-shape':      'triangle',
          'arrow-scale':             0.65,
          'curve-style':             'bezier',
          'label':                   'data(rel)',
          'font-size':               '8px',
          'font-family':             'Consolas, monospace',
          'color':                   '#9ca3af',
          'text-background-color':   '#f8f9fb',
          'text-background-opacity': 0.9,
          'text-background-padding': '2px',
          'text-border-opacity':     0,
        },
      },
      {
        selector: 'edge:selected',
        style: {
          'width':              2,
          'line-color':         '#6366f1',
          'target-arrow-color': '#6366f1',
          'color':              '#4f46e5',
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
      const displayName = name.length > 28 ? name.slice(0, 28) + '…' : name;
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
      const eData = { id: `e_${i}`, source: e.src, target: e.dst, rel: e.rel };
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

  // ── Minimap ───────────────────────────────────────────────────────────────
  function buildMinimap() {
    const mm = document.createElement('div');
    mm.id = 'cortex-minimap';
    Object.assign(mm.style, {
      position: 'absolute', bottom: '14px', right: '14px',
      width: '160px', height: '110px',
      background: 'rgba(255,255,255,0.92)',
      border: '1px solid #e5e7eb',
      borderRadius: '12px',
      overflow: 'hidden', zIndex: '10',
      boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
      pointerEvents: 'none',
    });

    const lbl = document.createElement('div');
    lbl.textContent = 'OVERVIEW';
    Object.assign(lbl.style, {
      position: 'absolute', top: '5px', left: '8px',
      fontSize: '7px', color: '#9ca3af',
      fontFamily: 'Consolas, monospace',
      letterSpacing: '0.1em', fontWeight: '700', zIndex: '1',
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
        img.src = _cy.png({ output: 'base64uri', bg: '#f8f9fb', full: true, scale: 0.18 });
      } catch (_) {}
    });
  }

  // ── Layout ────────────────────────────────────────────────────────────────
  function pickLayout() {
    if (typeof cytoscapeDagre !== 'undefined') {
      return {
        name:    'dagre',
        rankDir: 'LR',
        nodeSep: 24,
        rankSep: 70,
        padding: 44,
        animate: true,
        animationDuration: 400,
        nodeDimensionsIncludeLabels: true,
        ranker: 'network-simplex',
      };
    }
    if (typeof cytoscapeCoseBilkent !== 'undefined') {
      return { name: 'cose-bilkent', animate: true, animationDuration: 500, nodeDimensionsIncludeLabels: true, idealEdgeLength: 110, nodeRepulsion: 8000, gravity: 0.25, numIter: 2500, randomize: false };
    }
    return { name: 'cose', animate: true };
  }

  // ── Zoom toolbar ──────────────────────────────────────────────────────────
  function buildToolbar() {
    const bar = document.createElement('div');
    Object.assign(bar.style, {
      position: 'absolute', bottom: '14px', left: '14px',
      display: 'flex', flexDirection: 'column', gap: '4px', zIndex: '10',
    });

    const s = `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;

    function btn(title, svg, onClick) {
      const b = document.createElement('button');
      b.title   = title;
      b.innerHTML = svg;
      Object.assign(b.style, {
        width: '32px', height: '32px', borderRadius: '10px',
        background: 'rgba(255,255,255,0.92)', border: '1px solid #e5e7eb',
        color: '#6b7280', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
        transition: 'color 0.12s, border-color 0.12s, background 0.12s',
      });
      b.addEventListener('mouseenter', () => { b.style.color = '#111827'; b.style.borderColor = '#d1d5db'; });
      b.addEventListener('mouseleave', () => { b.style.color = '#6b7280'; b.style.borderColor = '#e5e7eb'; });
      b.addEventListener('click', onClick);
      return b;
    }

    bar.appendChild(btn('Fit view',
      `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,
      () => _cy && _cy.fit(undefined, 44)
    ));
    bar.appendChild(btn('Zoom in',
      `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
      () => _cy && _cy.zoom({ level: _cy.zoom() * 1.3, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })
    ));
    bar.appendChild(btn('Zoom out',
      `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
      () => _cy && _cy.zoom({ level: _cy.zoom() / 1.3, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })
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
      minZoom:             0.04,
      maxZoom:             4,
    });

    _cy.on('tap', 'node', function (evt) {
      const node = evt.target;
      if (node.isParent()) return;
      if (window.CortexUI && window.CortexUI.onNodeClick) window.CortexUI.onNodeClick(node.id());
    });

    _cy.on('dbltap', 'node', function (evt) {
      _cy.animate({ fit: { eles: evt.target.neighborhood().add(evt.target), padding: 60 }, duration: 350 });
    });
  }

  // ── Public API ────────────────────────────────────────────────────────────
  function render(nodes, edges, diffData) {
    if (!_cy) return;
    _cy.elements().remove();
    _cy.add(toElements(nodes, edges, diffData));

    const layout = _cy.layout(pickLayout());
    layout.one('layoutstop', () => refreshMinimap());
    layout.run();

    if (window._cortexSearchQuery) highlightSearch(window._cortexSearchQuery);
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
  }

  function addNode(node, edges) {
    if (!_cy) return;
    _cy.add(toElements([node], edges, null));
    const el = _cy.getElementById(node.id);
    if (el.length) { el.layout({ name: 'concentric', animate: true }).run(); el.select(); setTimeout(() => el.unselect(), 2000); }
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
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
    if (node.length) { _cy.animate({ center: { eles: node }, zoom: 2, duration: 350 }); node.select(); }
  }

  function screenshot() {
    if (!_cy) return null;
    return _cy.png({ output: 'base64uri', bg: '#f8f9fb', full: false });
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
