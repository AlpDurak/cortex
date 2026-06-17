/**
 * canvas.js — Cytoscape.js graph canvas for Cortex.
 * Exposes window.CortexGraph = { render, addNode, highlightSearch, clearSearch,
 *                                  filterEdgesByLabel, focusNode }
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Type palette
  // ---------------------------------------------------------------------------
  const TYPE_COLORS = {
    File:           { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
    SystemDesign:   { bg: '#ede9fe', border: '#7c3aed', text: '#4c1d95' },
    Service:        { bg: '#ffedd5', border: '#ea580c', text: '#7c2d12' },
    Database:       { bg: '#d1fae5', border: '#059669', text: '#064e3b' },
    Infrastructure: { bg: '#e5e7eb', border: '#6b7280', text: '#1f2937' },
  };
  const DIFF_COLORS = {
    added:    { bg: '#d4edda', border: '#28a745' },
    deleted:  { bg: '#f8d7da', border: '#dc3545' },
    modified: { bg: '#fff3cd', border: '#ffc107' },
  };

  // ---------------------------------------------------------------------------
  // SVG icon data URIs per node type
  // ---------------------------------------------------------------------------
  function _svgUri(svg) {
    return `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }

  const TYPE_ICONS = {
    File: _svgUri(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
      '<polyline points="14 2 14 8 20 8"/>' +
      '<line x1="16" y1="13" x2="8" y2="13"/>' +
      '<line x1="16" y1="17" x2="8" y2="17"/>' +
      '</svg>'
    ),
    SystemDesign: _svgUri(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="#7c3aed" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>' +
      '</svg>'
    ),
    Service: _svgUri(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="#ea580c" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="3"/>' +
      '<path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>' +
      '</svg>'
    ),
    Database: _svgUri(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="#059669" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<ellipse cx="12" cy="5" rx="9" ry="3"/>' +
      '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>' +
      '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>' +
      '</svg>'
    ),
    Infrastructure: _svgUri(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="#6b7280" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<rect x="2" y="2" width="20" height="8" rx="2"/>' +
      '<rect x="2" y="14" width="20" height="8" rx="2"/>' +
      '<line x1="6" y1="6" x2="6.01" y2="6"/>' +
      '<line x1="6" y1="18" x2="6.01" y2="18"/>' +
      '</svg>'
    ),
  };

  let _cy = null;
  let _hiddenEdgeLabels = new Set();
  let _clusterData = [];
  let _nodeCluster = {};

  // ---------------------------------------------------------------------------
  // Stylesheet
  // ---------------------------------------------------------------------------
  function buildStyle() {
    const iconStyle = {
      'background-width':      '14px',
      'background-height':     '14px',
      'background-position-x': '8px',
      'background-position-y': 'center',
      'background-clip':       'none',
    };

    const typeStyles = Object.entries(TYPE_COLORS).map(([label, c]) => ({
      selector: `node.${label}`,
      style: {
        'background-color': c.bg,
        'border-color':     c.border,
        'border-width':     2,
        'color':            c.text,
        ...(TYPE_ICONS[label] ? { 'background-image': TYPE_ICONS[label], ...iconStyle } : {}),
      },
    }));

    return [
      {
        selector: 'node',
        style: {
          'label':            'data(displayName)',
          'font-size':        '10px',
          'font-family':      'Cascadia Code, Fira Code, Consolas, monospace',
          'font-weight':      600,
          'color':            '#1f2937',
          'text-valign':      'center',
          'text-halign':      'center',
          'text-margin-x':    7,
          'width':            'label',
          'height':           '28px',
          'padding':          '6px 12px 6px 26px',
          'shape':            'roundrectangle',
          'border-width':     2,
          'background-color': '#f3f4f6',
          'border-color':     '#9ca3af',
          'text-wrap':        'none',
          'min-width':        '80px',
        },
      },
      ...typeStyles,
      {
        selector: 'node:parent',
        style: {
          'background-color': 'rgba(124,58,237,0.04)',
          'border-color':     '#7c3aed',
          'border-width':     1.5,
          'border-style':     'dashed',
          'label':            'data(displayName)',
          'text-valign':      'top',
          'text-halign':      'center',
          'text-margin-y':    -4,
          'font-size':        '9px',
          'font-weight':      700,
          'color':            '#7c3aed',
          'padding':          '28px',
          'background-image': 'none',
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
          'width':                   1.5,
          'line-color':              '#94a3b8',
          'target-arrow-color':      '#94a3b8',
          'target-arrow-shape':      'triangle',
          'curve-style':             'bezier',
          'label':                   'data(rel)',
          'font-size':               '8px',
          'font-family':             'Cascadia Code, Fira Code, Consolas, monospace',
          'color':                   '#6b7280',
          'text-background-color':   '#ffffff',
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
        },
      },
      {
        selector: 'edge:selected',
        style: { 'width': 3, 'line-color': '#0e639c' },
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
          'line-color':         '#dc3545',
          'target-arrow-color': '#dc3545',
          'line-style':         'dashed',
          'width':              2,
        },
      },
    ];
  }

  // ---------------------------------------------------------------------------
  // Convert raw API data → Cytoscape elements
  // Resolves MEMBER_OF into parent/child compound structure.
  // ---------------------------------------------------------------------------
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
        if ((diffData.added_nodes   || []).includes(n.id))  classes.push('diff-added');
        else if ((diffData.deleted_nodes || []).includes(n.id))  classes.push('diff-deleted');
        else if ((diffData.modified_nodes || []).includes(n.id)) classes.push('diff-modified');
      }

      elements.push({ data, classes: classes.join(' ') });
    }

    for (let i = 0; i < nonMemberEdges.length; i++) {
      const e     = nonMemberEdges[i];
      const key   = `${e.src}|${e.rel}|${e.dst}`;
      const eData = { id: key + '_' + i, source: e.src, target: e.dst, rel: e.rel };
      const classes = [];
      if (diffData) {
        const addK = (diffData.added_edges   || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        const delK = (diffData.deleted_edges || []).map(x => `${x.src}|${x.rel}|${x.dst}`);
        if (addK.includes(key))  classes.push('diff-added');
        else if (delK.includes(key)) classes.push('diff-deleted');
      }
      elements.push({ data: eData, classes: classes.join(' ') });
    }

    return elements;
  }

  // ---------------------------------------------------------------------------
  // Cluster border rings
  // ---------------------------------------------------------------------------
  function applyClusterColors() {
    if (!_cy || !_clusterData.length) return;
    for (const cluster of _clusterData) {
      for (const memberId of cluster.members) {
        const node = _cy.getElementById(memberId);
        if (node.length) node.style({ 'border-color': cluster.color, 'border-width': 3 });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Minimap overlay
  // ---------------------------------------------------------------------------
  function buildMinimap() {
    const mm = document.createElement('div');
    mm.id = 'cortex-minimap';
    mm.style.cssText = [
      'position:absolute', 'bottom:52px', 'right:12px',
      'width:168px', 'height:126px',
      'background:rgba(18,18,18,0.95)',
      'border:1px solid #3c3c3c', 'border-radius:6px',
      'overflow:hidden', 'z-index:10',
      'box-shadow:0 2px 8px rgba(0,0,0,0.6)',
      'pointer-events:none',
    ].join(';');

    const lbl = document.createElement('div');
    lbl.textContent = 'OVERVIEW';
    lbl.style.cssText = [
      'position:absolute', 'top:4px', 'left:8px',
      'font-size:8px', 'color:#555',
      'font-family:Cascadia Code,monospace',
      'letter-spacing:0.8px', 'z-index:1',
    ].join(';');

    const img = document.createElement('img');
    img.id = 'cortex-minimap-img';
    img.style.cssText = [
      'position:absolute', 'top:16px', 'left:0',
      'width:100%', 'height:calc(100% - 16px)',
      'object-fit:contain',
    ].join(';');

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
        img.src = _cy.png({ output: 'base64uri', bg: '#1e1e1e', full: true, scale: 0.22 });
      } catch (_) {}
    });
  }

  // ---------------------------------------------------------------------------
  // Layout selection
  // ---------------------------------------------------------------------------
  function pickLayout() {
    if (typeof cytoscapeDagre !== 'undefined') {
      return {
        name:    'dagre',
        rankDir: 'TB',
        nodeSep: 60,
        rankSep: 80,
        padding: 50,
        animate: true,
        animationDuration: 500,
        nodeDimensionsIncludeLabels: true,
        ranker:  'network-simplex',
      };
    }
    if (typeof cytoscapeCoseBilkent !== 'undefined') {
      return {
        name:  'cose-bilkent',
        animate: true,
        animationDuration: 600,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 110,
        nodeRepulsion:   10000,
        gravity:         0.3,
        numIter:         2500,
        randomize:       false,
      };
    }
    return { name: 'cose', animate: true, animationDuration: 600 };
  }

  // ---------------------------------------------------------------------------
  // Toolbar (zoom + fit)
  // ---------------------------------------------------------------------------
  function buildToolbar() {
    const bar = document.createElement('div');
    bar.style.cssText = [
      'position:absolute', 'bottom:52px', 'left:12px',
      'display:flex', 'flex-direction:column', 'gap:4px', 'z-index:10',
    ].join(';');

    function btn(title, svgStr, onClick) {
      const b = document.createElement('button');
      b.title     = title;
      b.innerHTML = svgStr;
      b.style.cssText = [
        'width:32px', 'height:32px', 'border-radius:6px',
        'background:rgba(30,30,30,0.9)', 'border:1px solid #3c3c3c',
        'color:#ccc', 'cursor:pointer',
        'display:flex', 'align-items:center', 'justify-content:center',
      ].join(';');
      b.addEventListener('click', onClick);
      return b;
    }

    const s = `stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
    bar.appendChild(btn('Fit view',  `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" ${s}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,  () => _cy && _cy.fit(undefined, 40)));
    bar.appendChild(btn('Zoom in',   `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`, () => _cy && _cy.zoom({ level: _cy.zoom() * 1.3, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })));
    bar.appendChild(btn('Zoom out',  `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,                                       () => _cy && _cy.zoom({ level: _cy.zoom() / 1.3, renderedPosition: { x: _cy.width() / 2, y: _cy.height() / 2 } })));
    return bar;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // ---------------------------------------------------------------------------
  function bootstrap() {
    const container = document.getElementById('graph-canvas');
    if (!container) return;

    if (typeof cytoscapeCoseBilkent !== 'undefined') cytoscape.use(cytoscapeCoseBilkent);
    if (typeof cytoscapeDagre       !== 'undefined') cytoscape.use(cytoscapeDagre);

    _cy = cytoscape({
      container,
      elements:           [],
      style:              buildStyle(),
      layout:             { name: 'grid' },
      autoungrabify:      true,     // nodes are not draggable
      boxSelectionEnabled: true,
    });

    _cy.on('tap', 'node', function (evt) {
      const node = evt.target;
      if (node.isParent()) return;
      if (window.CortexUI && window.CortexUI.onNodeClick) window.CortexUI.onNodeClick(node.id());
    });

    _cy.on('dbltap', 'node', function (evt) {
      _cy.animate({ fit: { eles: evt.target.neighborhood().add(evt.target), padding: 40 }, duration: 400 });
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

  // ---------------------------------------------------------------------------
  // Public API — window.CortexGraph
  // ---------------------------------------------------------------------------

  function screenshot() {
    if (!_cy) return null;
    return _cy.png({ output: 'base64uri', bg: '#1e1e1e', full: false });
  }

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

    const activeSearch = window._cortexSearchQuery;
    if (activeSearch) highlightSearch(activeSearch);
    if (_hiddenEdgeLabels.size) filterEdgesByLabel(_hiddenEdgeLabels);
  }

  function addNode(node, edges) {
    if (!_cy) return;
    _cy.add(toElements([node], edges, null));
    const newNode = _cy.getElementById(node.id);
    if (newNode.length) {
      newNode.layout({ name: 'concentric', animate: true }).run();
      newNode.select();
      setTimeout(() => newNode.unselect(), 2000);
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
      const d     = n.data();
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
      _cy.animate({ center: { eles: node }, zoom: 1.6, duration: 400 });
      node.select();
    }
  }

  // ---------------------------------------------------------------------------
  // Init on DOM ready
  // ---------------------------------------------------------------------------
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
