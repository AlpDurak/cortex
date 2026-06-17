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
