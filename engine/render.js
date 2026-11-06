(function (global) {
  "use strict";

  const VERSION = "0.1.1";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DEFAULTS = Object.freeze({ width: 1080, padding: 28, gap: 16, columns: 12 });
  const SIZE = Object.freeze({ sfx: 80, label: 30, text: 31, box: 31 });
  const TAIL = Object.freeze({ w: 40, h: 34, stroke: 4 });
  const THOUGHT_DOTS = Object.freeze([{ size: 30, offset: 10 }, { size: 18, offset: 46 }]);
  const TAIL_ROTATION = Object.freeze({ down: 0, up: 180, left: 90, right: -90 });
  const COVER = Object.freeze({ w: 480, h: 800, border: 6, titleSize: 110, subSize: 34 });

  function el(tag, cls, parent) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (parent) parent.appendChild(e);
    return e;
  }

  function rich(s) {
    return String(s).replace(/\n/g, "<br>");
  }

  function resolve(src, base) {
    if (!src || !base || /^([a-z]+:|\/|#)/i.test(src)) return src;
    return base + src;
  }

  function place(node, side, at, size, offset) {
    const along = side === "down" || side === "up" ? "left" : "top";
    node.style[along] = `calc(${at}% - ${size / 2}px)`;
    const edge = { down: "bottom", up: "top", left: "left", right: "right" }[side];
    node.style[edge] = -offset + "px";
  }

  function tail(bubble, side, at, kind) {
    if (!side || side === "none") return;
    if (kind === "thought") {
      THOUGHT_DOTS.forEach((d) => {
        const dot = el("div", "dot", bubble);
        dot.style.width = dot.style.height = d.size + "px";
        place(dot, side, at, d.size, d.offset + d.size);
      });
      return;
    }
    const sv = document.createElementNS(SVG_NS, "svg");
    sv.setAttribute("width", TAIL.w);
    sv.setAttribute("height", TAIL.h);
    sv.setAttribute("class", "tail");
    sv.innerHTML = `<polygon points="0,0 ${TAIL.w},0 ${TAIL.w / 2},${TAIL.h}" fill="#fff"/><polyline points="0,0 ${TAIL.w / 2},${TAIL.h} ${TAIL.w},0" fill="none" stroke="#000" stroke-width="${TAIL.stroke}"/>`;
    sv.style.transform = `rotate(${TAIL_ROTATION[side]}deg)`;
    const vertical = side === "down" || side === "up";
    place(sv, side, at, vertical ? TAIL.w : TAIL.h, vertical ? TAIL.h - 2 : TAIL.h + 1);
    bubble.appendChild(sv);
  }

  function bubbleNode(parent, q, fs) {
    const type = q.type || "speech";
    const b = el("div", "b " + type + (q.shape ? " " + q.shape : "") + (q.dark ? " dark" : ""), parent);
    b.style.left = q.x + "%";
    b.style.top = q.y + "%";
    if (q.w) b.style.width = q.w * fs + "px";
    const base = q.size || (type === "sfx" ? SIZE.sfx : type === "label" ? SIZE.label : SIZE.text);
    b.style.fontSize = base * fs + "px";
    if (q.rot) b.style.transform = `rotate(${q.rot}deg)`;
    el("div", "tx", b).innerHTML = rich(q.text);
    if (type === "speech" || type === "thought") tail(b, q.tail, q.tailAt ?? 50, type);
  }

  function panelNode(grid, p, i, o) {
    const er = (o.panel && p.ereader) || {};
    const d = el("div", "pan" + (p.bw !== false ? " bw" : "") + (p.box ? " boxed" : p.tone !== false ? " tone" : ""), grid);
    const art = p.box ? el("div", "art" + (p.tone !== false ? " tone" : ""), d) : d;
    d.style.gridColumn = `${p.col[0]} / span ${p.col[1]}`;
    d.style.gridRow = `${p.row[0]} / span ${p.row[1] || 1}`;
    if (p.border) d.style.borderWidth = p.border + "px";
    if (p.img) {
      const im = el("img", "", art);
      im.src = resolve(p.img, o.base);
      im.alt = "";
      if (p.focus) im.style.objectPosition = p.focus;
      if (p.scale && p.scale !== 1) {
        im.style.transform = `scale(${p.scale})`;
        im.style.transformOrigin = p.focus || "center";
      }
    }
    if (p.number !== false) el("div", "num", d).textContent = p.number || i + 1;
    const fs = o.panel ? o.fs * (er.fs || 1) : 1;
    (p.bubbles || []).forEach((q0, bi) => {
      const q = o.panel ? Object.assign({}, q0, (er.bubbles || {})[bi]) : q0;
      bubbleNode(art, q, fs);
    });
    if (p.box) {
      const x = el("div", "ibox", d);
      x.innerHTML = p.box;
      const size = p.boxSize || SIZE.box;
      x.style.fontSize = size + "px";
      x.dataset.fs = size * (o.panel ? o.fs * (er.boxFs || er.fs || 1) : 1);
    }
    return d;
  }

  function render(P, root, opts) {
    const o = Object.assign({ panel: 0, fs: 1, base: "" }, opts || {});
    const C = Object.assign({}, DEFAULTS, P);
    root.innerHTML = "";
    root.classList.add("page");
    root.style.width = C.width + "px";
    root.style.padding = C.padding + "px";
    if (C.title) {
      const h = el("div", "head", root);
      h.style.marginBottom = C.gap + "px";
      el("h1", "", h).innerHTML = rich(C.title.text);
      if (C.title.sub) el("div", "sub", h).innerHTML = rich(C.title.sub);
    }
    const grid = el("div", "grid", root);
    grid.style.gridTemplateColumns = `repeat(${C.columns},1fr)`;
    grid.style.gridTemplateRows = C.rows.map((r) => r + "px").join(" ");
    grid.style.gap = C.gap + "px";
    const panels = C.panels.map((p, i) => panelNode(grid, p, i, o));
    if (C.footer) el("div", "foot", root).innerHTML = rich(C.footer);
    return { root, grid, panels };
  }

  function isolatePanel(view, index) {
    const pan = view.panels[index - 1];
    const r = pan.getBoundingClientRect();
    const art = pan.querySelector(".art");
    const bx = pan.querySelector(".ibox");
    const ah = art ? art.getBoundingClientRect().height : 0;
    document.body.appendChild(pan);
    view.root.style.display = "none";
    Object.assign(pan.style, { position: "fixed", left: "0", top: "0", width: r.width + "px", height: r.height + "px" });
    if (art && bx) {
      art.style.flex = "none";
      art.style.height = ah + "px";
      bx.style.fontSize = bx.dataset.fs + "px";
      pan.style.height = "auto";
    }
  }

  function renderCover(P, root, w, h, base) {
    const C = P.cover || {};
    const first = (P.panels.find((p) => p.img) || {}).img;
    root.style.display = "none";
    const c = el("div", "cover", document.body);
    Object.assign(c.style, { position: "fixed", left: 0, top: 0, width: w + "px", height: h + "px", border: COVER.border + "px solid #000", display: "flex", flexDirection: "column", background: "#fff" });
    const hd = el("div", "head", c);
    hd.style.justifyContent = "center";
    hd.style.border = "0";
    const h1 = el("h1", "", hd);
    h1.innerHTML = rich(P.title.text);
    h1.style.fontSize = (C.titleSize || COVER.titleSize) + "px";
    const pn = el("div", "pan bw tone", c);
    Object.assign(pn.style, { flex: "1", border: "0", borderTop: COVER.border + "px solid #000" });
    const im = el("img", "", pn);
    im.src = resolve(C.img || first, base);
    im.alt = "";
    if (C.focus) im.style.objectPosition = C.focus;
    const sub = C.sub || P.title.sub;
    if (sub) {
      const s = el("div", "foot", c);
      s.innerHTML = rich(sub);
      Object.assign(s.style, { textAlign: "center", padding: "8px", borderTop: COVER.border + "px solid #000", fontSize: (C.subSize || COVER.subSize) + "px", margin: 0 });
    }
  }

  function boot() {
    const q = Object.fromEntries(location.hash.slice(1).split("&").filter(Boolean).map((k) => k.split("=")));
    const P = global.PAGE;
    const root = document.getElementById("page");
    const panel = q.panel ? +q.panel : 0;
    const view = render(P, root, { panel, fs: q.fs ? +q.fs : 1 });
    document.body.style.width = root.style.width;
    if (panel) isolatePanel(view, panel);
    if (q.cover) renderCover(P, root, +q.w || COVER.w, +q.h || COVER.h, "");
    const done = () => {
      document.documentElement.dataset.width = Math.ceil(root.getBoundingClientRect().width);
      document.documentElement.dataset.height = Math.ceil(root.getBoundingClientRect().height);
      document.documentElement.dataset.panels = view.panels.map((p) => Math.ceil(p.getBoundingClientRect().height)).join(",");
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(done);
    else done();
  }

  global.MangaEngine = { VERSION, render, boot };
})(window);
