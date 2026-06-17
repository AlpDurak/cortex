/**
 * canvas.js — D3.js v7 force-simulation graph renderer
 * Hub nodes (Service/Database/etc) = large filled pills
 * Leaf nodes (File/etc)            = small white-bordered chips
 * Groups                           = live bounding-box containers
 * Nodes are draggable; layout is organic force-directed.
 */
(function () {
  "use strict";

  // ── Visual tiers ──────────────────────────────────────────────────────────
  const HUB_TYPES = new Set([
    "Service",
    "Database",
    "Infrastructure",
    "SystemDesign",
  ]);

  // Hub: vivid fill, white text.  Leaf: tinted fill, dark text.
  const TYPE_PAL = {
    Service: {
      fill: "#6366f1",
      text: "#fff",
      stroke: "#4f46e5",
      lFill: "#eef2ff",
      lText: "#3730a3",
      lStroke: "#818cf8",
    },
    Database: {
      fill: "#10b981",
      text: "#fff",
      stroke: "#059669",
      lFill: "#d1fae5",
      lText: "#065f46",
      lStroke: "#34d399",
    },
    Infrastructure: {
      fill: "#f59e0b",
      text: "#fff",
      stroke: "#d97706",
      lFill: "#fef3c7",
      lText: "#92400e",
      lStroke: "#fbbf24",
    },
    File: {
      fill: "#3b82f6",
      text: "#fff",
      stroke: "#2563eb",
      lFill: "#eff6ff",
      lText: "#1e40af",
      lStroke: "#93c5fd",
    },
    SystemDesign: {
      fill: "#8b5cf6",
      text: "#fff",
      stroke: "#7c3aed",
      lFill: "#f5f3ff",
      lText: "#5b21b6",
      lStroke: "#a78bfa",
    },
  };
  const PAL_DEF = {
    fill: "#6b7280",
    text: "#fff",
    stroke: "#4b5563",
    lFill: "#f9fafb",
    lText: "#374151",
    lStroke: "#d1d5db",
  };

  function pal(d) {
    return TYPE_PAL[d.label] || PAL_DEF;
  }
  function isHub(d) {
    return HUB_TYPES.has(d.label);
  }

  // ── Icons (14×14 SVG content, stroked) ────────────────────────────────────
  const ICONS = {
    Service: (c) =>
      `<path fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"
       d="M1 7.5C1 4.5 3.7 2 7 2s6 2.5 6 5.5M3.5 8.8C3.5 7 5.1 5.6 7 5.6s3.5 1.4 3.5 3.2"/>
       <circle cx="7" cy="11.5" r="1.5" fill="${c}" stroke="none"/>`,
    Database: (c) =>
      `<ellipse cx="7" cy="3.5" rx="5" ry="1.7" fill="none" stroke="${c}" stroke-width="1.5"/>
       <path fill="none" stroke="${c}" stroke-width="1.5"
       d="M2 3.5v7.2c0 .9 2.2 1.7 5 1.7s5-.8 5-1.7V3.5M2 7.1c0 .9 2.2 1.7 5 1.7s5-.8 5-1.7"/>`,
    Infrastructure: (c) =>
      `<rect x="1" y="2" width="12" height="3.5" rx="1" fill="none" stroke="${c}" stroke-width="1.5"/>
       <rect x="1" y="8.5" width="12" height="3.5" rx="1" fill="none" stroke="${c}" stroke-width="1.5"/>
       <circle cx="11" cy="3.75" r=".85" fill="${c}"/>
       <circle cx="11" cy="10.25" r=".85" fill="${c}"/>
       <line x1="2.5" y1="3.75" x2="8" y2="3.75" stroke="${c}" stroke-width="1.2" stroke-linecap="round"/>
       <line x1="2.5" y1="10.25" x2="8" y2="10.25" stroke="${c}" stroke-width="1.2" stroke-linecap="round"/>`,
    File: (c) =>
      `<path fill="none" stroke="${c}" stroke-width="1.5" stroke-linejoin="round"
       d="M3 1.5H9l3.5 3.5V13a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5v-11A.5.5 0 0 1 3 1.5z"/>
       <path fill="none" stroke="${c}" stroke-width="1.5" d="M9 1.5V5h3.5"/>`,
    SystemDesign: (c) =>
      `<polygon points="7,1.5 12.2,4.5 12.2,10.5 7,13.5 1.8,10.5 1.8,4.5"
       fill="none" stroke="${c}" stroke-width="1.5" stroke-linejoin="round"/>`,
  };

  // ── Text measurement ──────────────────────────────────────────────────────
  let _ctx = null;
  function textW(str, font) {
    if (!_ctx) _ctx = document.createElement("canvas").getContext("2d");
    _ctx.font = font;
    return _ctx.measureText(str || "").width;
  }

  const HUB_FONT = "600 13px Consolas,monospace";
  const LEAF_FONT = "500 11px Consolas,monospace";
  const ICON_W = 14,
    ICON_GAP = 5;

  function nodeMetrics(d) {
    const raw = d.name || d.id || "";
    const label = raw.length > 30 ? raw.slice(0, 30) + "…" : raw;
    const hub = isHub(d);
    const font = hub ? HUB_FONT : LEAF_FONT;
    const lpad = hub ? 14 : 10;
    const rpad = hub ? 12 : 8;
    const tw = Math.ceil(textW(label, font));
    const w = Math.max(tw + lpad + ICON_W + ICON_GAP + rpad, hub ? 90 : 60);
    const h = hub ? 36 : 26;
    const rx = hub ? 18 : 6;
    const ix = -w / 2 + lpad; // icon group translate-x
    const tx = ix + ICON_W + ICON_GAP; // text start-x
    return { label, w, h, rx, ix, tx, hub };
  }

  function collideR(d) {
    const m = d._m;
    return m ? Math.sqrt(m.w * m.w + m.h * m.h) / 2 + 6 : 40;
  }

  // ── Edge rect-boundary intersection ───────────────────────────────────────
  function borderPt(fromX, fromY, toX, toY, tw, th) {
    const dx = toX - fromX,
      dy = toY - fromY;
    if (!dx && !dy) return { x: toX, y: toY };
    const hw = tw / 2,
      hh = th / 2;
    const sx = hw / Math.abs(dx || 1e-9),
      sy = hh / Math.abs(dy || 1e-9);
    const s = Math.min(sx, sy);
    return { x: toX - dx * s, y: toY - dy * s };
  }

  // ── State ─────────────────────────────────────────────────────────────────
  let _svg = null,
    _zoomG = null,
    _zoom = null,
    _sim = null;
  let _nodesData = [],
    _edgesData = [];
  let _parentMap = {},
    _groupIds = new Set(),
    _byId = {};
  let _searchActive = false;
  let _mmTimer = null;

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  function bootstrap() {
    const container = document.getElementById("graph-canvas");
    if (!container) return;

    _svg = d3
      .select(container)
      .append("svg")
      .attr("width", "100%")
      .attr("height", "100%")
      .style("display", "block");

    const defs = _svg.append("defs");
    [
      ["arr", "#757679"],
      ["arr-add", "#22c55e"],
      ["arr-del", "#ef4444"],
    ].forEach(([id, col]) =>
      defs
        .append("marker")
        .attr("id", id)
        .attr("viewBox", "0 -4 8 8")
        .attr("refX", 7)
        .attr("refY", 0)
        .attr("markerWidth", 5)
        .attr("markerHeight", 5)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L8,0L0,4Z")
        .attr("fill", col),
    );

    _zoomG = _svg.append("g").attr("class", "zoom-root");
    ["groups", "links", "nodes"].forEach((cls) =>
      _zoomG.append("g").attr("class", `layer-${cls}`),
    );

    _zoom = d3
      .zoom()
      .scaleExtent([0.04, 4])
      .on("zoom", (evt) => {
        _zoomG.attr("transform", evt.transform);
        schedMinimap();
      });
    _svg.call(_zoom);

    _svg.on("click", (evt) => {
      if (evt.target === _svg.node()) _clearSearch(true);
    });

    const wrap = document.getElementById("canvas-wrapper");
    if (wrap) {
      wrap.appendChild(_buildToolbar());
      wrap.appendChild(_buildMinimap());
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  function render(nodes, edges, diffData) {
    if (!_svg) return;
    if (_sim) _sim.stop();

    _nodesData = nodes;
    _edgesData = edges;
    _parentMap = {};
    _groupIds = new Set();
    edges.forEach((e) => {
      if (e.rel === "MEMBER_OF") {
        _parentMap[e.src] = e.dst;
        _groupIds.add(e.dst);
      }
    });
    _byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

    const diffAdd = new Set(diffData?.added_nodes || []);
    const diffDel = new Set(diffData?.deleted_nodes || []);
    const diffMod = new Set(diffData?.modified_nodes || []);
    const eAdd = new Set(
      (diffData?.added_edges || []).map((e) => `${e.src}|${e.dst}`),
    );
    const eDel = new Set(
      (diffData?.deleted_edges || []).map((e) => `${e.src}|${e.dst}`),
    );

    const renderNodes = nodes.filter((n) => !_groupIds.has(n.id));
    const groupNodes = nodes.filter((n) => _groupIds.has(n.id));

    const W = document.getElementById("graph-canvas")?.clientWidth || 900;
    const H = document.getElementById("graph-canvas")?.clientHeight || 650;

    renderNodes.forEach((n) => {
      n._m = nodeMetrics(n);
      if (n.x == null) {
        n.x = W / 2 + (Math.random() - 0.5) * 400;
      }
      if (n.y == null) {
        n.y = H / 2 + (Math.random() - 0.5) * 300;
      }
    });

    const links = edges
      .filter(
        (e) =>
          e.rel !== "MEMBER_OF" &&
          _byId[e.src] &&
          _byId[e.dst] &&
          !_groupIds.has(e.src) &&
          !_groupIds.has(e.dst),
      )
      .map((e) => ({ ...e, source: e.src, target: e.dst }));

    // ── Groups ───────────────────────────────────────────────────────────────
    const gLayer = _zoomG.select(".layer-groups");
    gLayer.selectAll("*").remove();
    const gEls = {};
    groupNodes.forEach((gn) => {
      const g = gLayer.append("g");
      g.append("rect")
        .attr("class", "grp-rect")
        .attr("rx", 12)
        .attr("fill", "rgba(148,163,184,0.09)")
        .attr("stroke", "#cbd5e1")
        .attr("stroke-width", 1.5)
        .attr("stroke-dasharray", "6,4");
      g.append("text")
        .attr("class", "grp-label")
        .attr("text-anchor", "middle")
        .attr("fill", "#b0b5c0")
        .attr("font-size", "8.5px")
        .attr("font-family", "Consolas,monospace")
        .attr("font-weight", "700")
        .attr("letter-spacing", "0.06em")
        .text((gn.name || gn.id || "").toUpperCase());
      gEls[gn.id] = g;
    });

    // ── Links ────────────────────────────────────────────────────────────────
    const lLayer = _zoomG.select(".layer-links");
    lLayer.selectAll("*").remove();

    const linkEls = lLayer
      .selectAll("g.lnk")
      .data(links, (d) => `${d.src}|${d.dst}|${d.rel}`)
      .join("g")
      .attr("class", "lnk");

    linkEls
      .append("path")
      .attr("fill", "none")
      .attr("stroke", (d) =>
        eAdd.has(`${d.src}|${d.dst}`)
          ? "#22c55e"
          : eDel.has(`${d.src}|${d.dst}`)
            ? "#ef4444"
            : "#5e5e5e7a",
      )
      .attr("stroke-width", 1)
      .attr("marker-end", (d) =>
        eAdd.has(`${d.src}|${d.dst}`)
          ? "url(#arr-add)"
          : eDel.has(`${d.src}|${d.dst}`)
            ? "url(#arr-del)"
            : "url(#arr)",
      );

    linkEls
      .append("text")
      .attr("text-anchor", "middle")
      .attr("fill", "#c0c3cc")
      .attr("font-size", "8px")
      .attr("font-family", "Consolas,monospace")
      .attr("pointer-events", "none")
      .text((d) => d.rel || "");

    // ── Nodes ────────────────────────────────────────────────────────────────
    const nLayer = _zoomG.select(".layer-nodes");
    nLayer.selectAll("*").remove();

    // const drag = d3
    //   .drag()
    //   .on("start", (ev, d) => {
    //     if (!ev.active) _sim.alphaTarget(0.3).restart();
    //     d.fx = d.x;
    //     d.fy = d.y;
    //   })
    //   .on("drag", (ev, d) => {
    //     d.fx = ev.x;
    //     d.fy = ev.y;
    //   })
    //   .on("end", (ev, d) => {
    //     if (!ev.active) _sim.alphaTarget(0);
    //     d.fx = null;
    //     d.fy = null;
    //   });

    const nodeEls = nLayer
      .selectAll("g.nd")
      .data(renderNodes, (d) => d.id)
      .join("g")
      .attr("class", (d) => `nd ${d.label || ""}`)
      .attr("data-id", (d) => d.id)
      .style("cursor", "pointer");
    // .call(drag);

    nodeEls.each(function (d) {
      const sel = d3.select(this);
      const m = d._m;
      const p = pal(d);

      let fill = m.hub ? p.fill : p.lFill;
      let stk = m.hub ? p.stroke : p.lStroke;
      let ttxt = m.hub ? p.text : p.lText;
      let sw = m.hub ? 2 : 1.5;
      let ic = m.hub ? "rgba(255, 255, 255, 0.9)" : p.lStroke;
      if (diffAdd.has(d.id)) {
        fill = "#dcfce7";
        stk = "#22c55e";
        ttxt = "#003d14";
        ic = "#003d14";
      }
      if (diffDel.has(d.id)) {
        fill = "#fee2e2";
        stk = "#ef4444";
        ttxt = "#3d0000";
        ic = "#3d0000";
      }
      if (diffMod.has(d.id)) {
        fill = "#fef9c3";
        stk = "#f59e0b";
        ttxt = "#636401";
        ic = "#636401";
      }

      sel
        .append("rect")
        .attr("class", "nd-rect")
        .attr("x", -m.w / 2)
        .attr("y", -m.h / 2)
        .attr("width", m.w)
        .attr("height", m.h)
        .attr("rx", m.rx)
        .attr("fill", fill)
        .attr("stroke", stk)
        .attr("stroke-width", sw);

      const iconFn = ICONS[d.label];
      if (iconFn) {
        sel
          .append("g")
          .attr("transform", `translate(${m.ix},${-ICON_W / 2})`)
          .attr("pointer-events", "none")
          .html(iconFn(ic));
      }

      sel
        .append("text")
        .attr("x", iconFn ? m.tx : 0)
        .attr("y", 0)
        .attr("dy", "0.35em")
        .attr("text-anchor", iconFn ? "start" : "middle")
        .attr("fill", ttxt)
        .attr("font-size", m.hub ? "13px" : "11px")
        .attr("font-family", "Consolas,monospace")
        .attr("font-weight", m.hub ? "600" : "500")
        .attr("pointer-events", "none")
        .text(m.label);
    });

    nodeEls.on("click", (ev, d) => {
      ev.stopPropagation();
      _clearSearch(true);
      nLayer.selectAll(".nd-rect").each(function (n) {
        const m = n._m,
          p = pal(n);
        d3.select(this)
          .attr("stroke", m.hub ? p.stroke : p.lStroke)
          .attr("stroke-width", m.hub ? 2 : 1.5);
      });
      d3.select(ev.currentTarget)
        .select(".nd-rect")
        .attr("stroke", "#6366f1")
        .attr("stroke-width", d._m.hub ? 3 : 2.5);
      if (window.CortexUI?.onNodeClick) window.CortexUI.onNodeClick(d.id);
    });

    nodeEls
      .on("mouseenter", function () {
        d3.select(this).select(".nd-rect").attr("filter", "brightness(0.94)");
      })
      .on("mouseleave", function () {
        d3.select(this).select(".nd-rect").attr("filter", null);
      });

    // ── Simulation ────────────────────────────────────────────────────────────
    _sim = d3
      .forceSimulation(renderNodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance((d) => {
            const s = _byId[d.source?.id ?? d.source];
            const t = _byId[d.target?.id ?? d.target];
            return (s && isHub(s)) || (t && isHub(t)) ? 130 : 85;
          })
          .strength(0.6),
      )
      .force(
        "charge",
        d3.forceManyBody().strength((d) => (isHub(d) ? -700 : -220)),
      )
      .force("center", d3.forceCenter(W / 2, H / 2).strength(0.04))
      .force("collision", d3.forceCollide().radius(collideR).strength(0.9))
      .force("cohesion", _cohesionForce(renderNodes))
      .alphaDecay(0.025);

    // ── Tick ─────────────────────────────────────────────────────────────────
    _sim.on("tick", () => {
      nodeEls.attr(
        "transform",
        (d) => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`,
      );

      linkEls.each(function (d) {
        const s = d.source,
          t = d.target;
        const sm = s._m || { w: 80, h: 28 };
        const tm = t._m || { w: 80, h: 28 };
        const sp = borderPt(t.x, t.y, s.x, s.y, sm.w, sm.h);
        const tp = borderPt(s.x, s.y, t.x, t.y, tm.w + 4, tm.h + 4);
        const lk = d3.select(this);
        lk.select("path").attr(
          "d",
          `M${sp.x.toFixed(1)},${sp.y.toFixed(1)}L${tp.x.toFixed(1)},${tp.y.toFixed(1)}`,
        );
        lk.select("text")
          .attr("x", ((s.x + t.x) / 2).toFixed(1))
          .attr("y", ((s.y + t.y) / 2 - 4).toFixed(1));
      });

      Object.keys(gEls).forEach((gid) => {
        const ms = renderNodes.filter((n) => _parentMap[n.id] === gid);
        if (!ms.length) return;
        const pad = { t: 44, r: 20, b: 20, l: 20 };
        const x0 = d3.min(ms, (n) => n.x - n._m.w / 2) - pad.l;
        const y0 = d3.min(ms, (n) => n.y - n._m.h / 2) - pad.t;
        const x1 = d3.max(ms, (n) => n.x + n._m.w / 2) + pad.r;
        const y1 = d3.max(ms, (n) => n.y + n._m.h / 2) + pad.b;
        const g = gEls[gid];
        g.select(".grp-rect")
          .attr("x", x0)
          .attr("y", y0)
          .attr("width", x1 - x0)
          .attr("height", y1 - y0);
        g.select(".grp-label")
          .attr("x", (x0 + x1) / 2)
          .attr("y", y0 + 16);
      });
    });

    _sim.on("end", () => {
      fitView();
      schedMinimap();
    });
  }

  // ── Group cohesion force ──────────────────────────────────────────────────
  function _cohesionForce(nodes) {
    return function (alpha) {
      const gs = {};
      nodes.forEach((n) => {
        const g = _parentMap[n.id];
        if (g) (gs[g] = gs[g] || []).push(n);
      });
      Object.values(gs).forEach((ms) => {
        if (ms.length < 2) return;
        const cx = d3.mean(ms, (n) => n.x),
          cy = d3.mean(ms, (n) => n.y);
        ms.forEach((n) => {
          n.vx -= (n.x - cx) * alpha * 0.07;
          n.vy -= (n.y - cy) * alpha * 0.07;
        });
      });
    };
  }

  // ── Fit view ──────────────────────────────────────────────────────────────
  function fitView() {
    if (!_svg || !_zoom) return;
    const el = document.getElementById("graph-canvas");
    if (!el) return;
    const W = el.clientWidth,
      H = el.clientHeight;
    try {
      const bb = _zoomG.node().getBBox();
      if (!bb.width || !bb.height) return;
      const pad = 48;
      const k = Math.min(
        (W - pad * 2) / bb.width,
        (H - pad * 2) / bb.height,
        1.5,
      );
      _svg
        .transition()
        .duration(500)
        .call(
          _zoom.transform,
          d3.zoomIdentity
            .translate(
              (W - bb.width * k) / 2 - bb.x * k,
              (H - bb.height * k) / 2 - bb.y * k,
            )
            .scale(k),
        );
    } catch (_) {}
  }

  // ── Focus node ────────────────────────────────────────────────────────────
  function focusNode(nodeId) {
    const n = _byId[nodeId];
    if (!n || n.x == null || !_svg) return;
    const el = document.getElementById("graph-canvas");
    if (!el) return;
    const W = el.clientWidth,
      H = el.clientHeight,
      k = 2;
    _svg
      .transition()
      .duration(400)
      .call(
        _zoom.transform,
        d3.zoomIdentity.translate(W / 2 - n.x * k, H / 2 - n.y * k).scale(k),
      );
    _zoomG.selectAll(".nd-rect").each(function (d) {
      const m = d._m,
        p = pal(d);
      d3.select(this)
        .attr("stroke", m.hub ? p.stroke : p.lStroke)
        .attr("stroke-width", m.hub ? 2 : 1.5);
    });
    _zoomG
      .selectAll("g.nd")
      .filter(function () {
        return this.dataset.id === nodeId;
      })
      .select(".nd-rect")
      .attr("stroke", "#6366f1")
      .attr("stroke-width", 3);
  }

  // ── Search ────────────────────────────────────────────────────────────────
  function highlightSearch(query) {
    const q = (query || "").toLowerCase().trim();
    if (!q) {
      clearSearch();
      return;
    }
    _searchActive = true;
    _zoomG.selectAll("g.nd").style("opacity", function () {
      const id = this.dataset.id;
      const n = _byId[id];
      return n &&
        ((n.name || "").toLowerCase().includes(q) ||
          id.toLowerCase().includes(q))
        ? 1
        : 0.28;
    });
  }

  function clearSearch() {
    _searchActive = false;
    if (_zoomG) _zoomG.selectAll("g.nd").style("opacity", null);
  }

  function _clearSearch(andUI) {
    clearSearch();
    if (andUI && window.CortexUI?.clearSearch) window.CortexUI.clearSearch();
  }

  // ── Live add node ─────────────────────────────────────────────────────────
  function addNode(node, edges) {
    _nodesData.push(node);
    (edges || []).forEach((e) => _edgesData.push(e));
    render(_nodesData, _edgesData, null);
  }

  // ── Minimap ───────────────────────────────────────────────────────────────
  function _buildMinimap() {
    const mm = document.createElement("div");
    mm.id = "cortex-minimap";
    Object.assign(mm.style, {
      position: "absolute",
      bottom: "14px",
      right: "14px",
      width: "160px",
      height: "110px",
      background: "rgba(255,255,255,0.92)",
      border: "1px solid #e5e7eb",
      borderRadius: "12px",
      overflow: "hidden",
      zIndex: "10",
      boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
      pointerEvents: "none",
    });
    const lbl = document.createElement("div");
    lbl.textContent = "OVERVIEW";
    Object.assign(lbl.style, {
      position: "absolute",
      top: "5px",
      left: "8px",
      fontSize: "7px",
      color: "#9ca3af",
      fontFamily: "Consolas,monospace",
      letterSpacing: "0.1em",
      fontWeight: "700",
      zIndex: "1",
    });
    const img = document.createElement("img");
    img.id = "cortex-minimap-img";
    Object.assign(img.style, {
      position: "absolute",
      top: "18px",
      left: "0",
      width: "100%",
      height: "calc(100% - 18px)",
      objectFit: "contain",
    });
    mm.appendChild(lbl);
    mm.appendChild(img);
    return mm;
  }

  function schedMinimap() {
    clearTimeout(_mmTimer);
    _mmTimer = setTimeout(() => {
      const img = document.getElementById("cortex-minimap-img");
      if (!img || !_svg || !_zoomG) return;
      try {
        const clone = _svg.node().cloneNode(true);
        clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        const zr = clone.querySelector(".zoom-root");
        if (zr) zr.removeAttribute("transform");
        const bb = _zoomG.node().getBBox();
        if (bb.width > 0) {
          clone.setAttribute(
            "viewBox",
            `${bb.x - 20} ${bb.y - 20} ${bb.width + 40} ${bb.height + 40}`,
          );
          const bg = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "rect",
          );
          bg.setAttribute("x", bb.x - 20);
          bg.setAttribute("y", bb.y - 20);
          bg.setAttribute("width", bb.width + 40);
          bg.setAttribute("height", bb.height + 40);
          bg.setAttribute("fill", "#f4f4f8");
          clone.insertBefore(bg, clone.firstChild);
        }
        img.src =
          "data:image/svg+xml;charset=utf-8," +
          encodeURIComponent(new XMLSerializer().serializeToString(clone));
      } catch (_) {}
    }, 600);
  }

  // ── Toolbar ───────────────────────────────────────────────────────────────
  function _buildToolbar() {
    const bar = document.createElement("div");
    Object.assign(bar.style, {
      position: "absolute",
      bottom: "14px",
      left: "14px",
      display: "flex",
      flexDirection: "column",
      gap: "4px",
      zIndex: "10",
    });
    const s =
      'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
    function btn(title, ico, fn) {
      const b = document.createElement("button");
      b.title = title;
      b.innerHTML = ico;
      Object.assign(b.style, {
        width: "32px",
        height: "32px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.92)",
        border: "1px solid #e5e7eb",
        color: "#6b7280",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
        transition: "all 0.12s",
      });
      b.onmouseenter = () => {
        b.style.color = "#111";
        b.style.borderColor = "#d1d5db";
      };
      b.onmouseleave = () => {
        b.style.color = "#6b7280";
        b.style.borderColor = "#e5e7eb";
      };
      b.onclick = fn;
      return b;
    }
    bar.appendChild(
      btn(
        "Fit view",
        `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,
        fitView,
      ),
    );
    bar.appendChild(
      btn(
        "Zoom in",
        `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
        () => _svg?.transition().duration(200).call(_zoom?.scaleBy, 1.4),
      ),
    );
    bar.appendChild(
      btn(
        "Zoom out",
        `<svg viewBox="0 0 24 24" width="15" height="15" ${s}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
        () => _svg?.transition().duration(200).call(_zoom?.scaleBy, 0.7),
      ),
    );
    return bar;
  }

  // ── Screenshot ────────────────────────────────────────────────────────────
  function screenshot() {
    if (!_svg) return null;
    try {
      const clone = _svg.node().cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      bg.setAttribute("width", "100%");
      bg.setAttribute("height", "100%");
      bg.setAttribute("fill", "#f4f4f8");
      clone.insertBefore(bg, clone.firstChild);
      return (
        "data:image/svg+xml;charset=utf-8," +
        encodeURIComponent(new XMLSerializer().serializeToString(clone))
      );
    } catch (_) {
      return null;
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    bootstrap();
    window.CortexGraph = {
      render,
      addNode,
      highlightSearch,
      clearSearch,
      filterEdgesByLabel: () => {},
      focusNode,
      screenshot,
    };
    if (window._pendingGraph) {
      const { nodes, edges, diffData } = window._pendingGraph;
      render(nodes, edges, diffData);
      delete window._pendingGraph;
    }
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
})();
