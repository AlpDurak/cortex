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
      const name = n.name || n.id || '';
      const displayName = name.length > 26 ? name.slice(0, 26) + '…' : name;

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
        window._clusterDataGlobal = clusters;
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
