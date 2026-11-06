import { APP_ID, APP_VERSION, STATS_KEY, EXAMPLE_DIR, EXAMPLE_URL, STAT, STATS, SWIPE_PX, FIT_MARGIN_PX } from "./config.js";
import { metaUpdate, metaDeclararProyecto } from "./meta.js";

const $ = (id) => document.getElementById(id);
const stage = $("stage");
const fit = $("fit");
const sheet = $("sheet");
const single = $("single");
const prev = $("prev");
const next = $("next");
const count = $("count");
const segButtons = [...document.querySelectorAll(".seg button")];

const state = { view: "page", index: 0, panels: [], sizes: [] };

function loadStats() {
  try {
    const s = JSON.parse(localStorage.getItem(STATS_KEY));
    if (s && typeof s === "object") return Object.assign({ [STAT.PANELS_VIEWED]: 0 }, s);
  } catch (e) {
    return { [STAT.PANELS_VIEWED]: 0 };
  }
  return { [STAT.PANELS_VIEWED]: 0 };
}

const stats = loadStats();

function saveStats() {
  try {
    localStorage.setItem(STATS_KEY, JSON.stringify(stats));
  } catch (e) {
    return;
  }
  metaUpdate(APP_ID, APP_VERSION, { stats }, { declare: STATS });
}

function place(box, w, h) {
  const r = stage.getBoundingClientRect();
  const s = Math.min((r.width - FIT_MARGIN_PX * 2) / w, (r.height - FIT_MARGIN_PX * 2) / h);
  box.style.width = w + "px";
  box.style.height = h + "px";
  box.style.transform = `translate(${(r.width - w * s) / 2}px, ${(r.height - h * s) / 2}px) scale(${s})`;
}

function layout() {
  if (state.view === "page") {
    place(fit, sheet.offsetWidth, sheet.offsetHeight);
    return;
  }
  const sz = state.sizes[state.index];
  if (sz) place(single, sz.w, sz.h);
}

function measure() {
  state.sizes = state.panels.map((p) => ({ w: p.offsetWidth, h: p.offsetHeight }));
}

function showPanel(i) {
  state.index = Math.max(0, Math.min(state.panels.length - 1, i));
  const src = state.panels[state.index];
  const sz = state.sizes[state.index];
  const clone = src.cloneNode(true);
  clone.style.gridColumn = clone.style.gridRow = "";
  clone.style.width = sz.w + "px";
  clone.style.height = sz.h + "px";
  single.replaceChildren(clone);
  count.textContent = `${state.index + 1} / ${state.panels.length}`;
  prev.disabled = state.index === 0;
  next.disabled = state.index === state.panels.length - 1;
  stats[STAT.PANELS_VIEWED] += 1;
  saveStats();
  layout();
}

function setView(view) {
  state.view = view;
  segButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  const panels = view === "panels";
  fit.hidden = panels;
  single.hidden = !panels;
  prev.hidden = next.hidden = count.hidden = !panels;
  if (panels) showPanel(state.index);
  else layout();
}

function step(d) {
  if (state.view === "panels") showPanel(state.index + d);
}

function bind() {
  segButtons.forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") step(-1);
    if (e.key === "ArrowRight") step(1);
  });
  let start = null;
  stage.addEventListener("pointerdown", (e) => { start = { x: e.clientX, y: e.clientY }; });
  stage.addEventListener("pointerup", (e) => {
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    start = null;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy)) {
      if (state.view === "page") setView("panels");
      else step(dx < 0 ? 1 : -1);
    }
  });
  new ResizeObserver(layout).observe(stage);
}

async function main() {
  document.body.classList.add("app");
  $("ver").textContent = APP_VERSION;
  metaDeclararProyecto(APP_ID, APP_VERSION);
  saveStats();
  bind();
  const res = await fetch(EXAMPLE_URL, { cache: "no-cache" });
  const config = await res.json();
  const view = window.MangaEngine.render(config, sheet, { base: EXAMPLE_DIR });
  state.panels = view.panels;
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  measure();
  layout();
}

main();
