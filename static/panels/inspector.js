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
