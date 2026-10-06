#!/usr/bin/env python3
"""penfield — local-first visual browser for your MemPalace memory.

Read-only by construction: opens collections with create=False, opens every
SQLite file with mode=ro, never takes the palace writer lock, never writes
anything anywhere. Safe to run while mines write.

Stdlib only. Needs the `mempalace` package importable: if this interpreter
cannot see it (pipx/uv keep it isolated), re-exec into the first venv python
that has it — same pattern as mp-write.py in opencode-mempalace-persistence.

Usage:
  penfield [--palace PATH] [--port N] [--host ADDR]

Then open http://localhost:8766 in a browser. On a headless VPS, forward it:
  ssh -L 8766:localhost:8766 <vps>
"""

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = "0.1.9"
DEFAULT_PORT = 8766


def ensure_mempalace() -> None:
    try:
        import mempalace  # noqa: F401
        return
    except ImportError:
        pass
    home = os.path.expanduser("~")
    candidates = []
    env_py = os.environ.get("MEMPALACE_PYTHON", "").strip()
    if env_py:
        candidates.append(env_py)
    candidates += [
        os.path.join(home, ".local/share/pipx/venvs/mempalace/bin/python"),
        os.path.join(home, ".local/share/uv/tools/mempalace/bin/python"),
    ]
    me = os.path.realpath(sys.argv[0])
    for cand in candidates:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            # The target interpreter does NOT have penfield installed (that is
            # why we are relocating at all): carry our own location across so
            # the re-exec finds this module. Without this, every pipx install
            # dies here with ModuleNotFoundError on first run.
            try:
                pkgdir = os.path.dirname(os.path.realpath(__file__))
            except NameError:
                pkgdir = ""
            if pkgdir:
                prev = os.environ.get("PYTHONPATH", "")
                os.environ["PYTHONPATH"] = pkgdir + (os.pathsep + prev if prev else "")
            os.execv(cand, [cand, me] + sys.argv[1:])
    sys.stderr.write(
        "penfield: mempalace package not importable (tried system python, "
        "MEMPALACE_PYTHON and the pipx/uv venvs). Install mempalace first.\n"
    )
    sys.exit(2)


INDEX_HTML = r"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>penfield</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--txt:#e6edf3;--mut:#8b949e;--acc:#58a6ff;--grn:#3fb950;--gry:#6e7681;--amb:#d29922}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--txt);max-width:900px;margin:0 auto;padding:1.2em 1em 3em}
header h1{font-size:1.5em;margin:.2em 0}header h1 small{color:var(--mut);font-weight:normal}
header p{color:var(--mut);margin:.2em 0 1em}
nav{display:flex;gap:.4em;flex-wrap:wrap;margin-bottom:1em}
nav button{background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:.45em 1em;cursor:pointer;font-size:.95em}
nav button.on{background:var(--acc);border-color:var(--acc);color:#04121f;font-weight:bold}
section{display:none;animation:fade .25s ease-out}
section.on{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
h2{font-size:1.15em;margin:1em 0 .5em}h3{font-size:1em;color:var(--mut);margin:1.2em 0 .4em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.7em}
.cards article{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.9em}
.cards h3{margin:.1em 0 .3em;color:var(--txt)}.cards p{color:var(--mut);font-size:.9em;margin:.2em 0 .7em}
button,.btn{background:var(--acc);border:none;border-radius:6px;color:#04121f;padding:.4em .9em;cursor:pointer;font-size:.9em}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--txt)}
select,input{background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:.35em .6em}
.ev{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.55em .8em;margin:.45em 0;font-size:.92em;cursor:pointer}
.ev:hover{border-color:var(--acc)}
.ev .meta{color:var(--mut);font-size:.85em}
.ev time{color:var(--mut)}
.tag{display:inline-block;font-size:.75em;border:1px solid var(--line);border-radius:4px;padding:0 .4em;margin-right:.3em;color:var(--mut)}
.tag.cur{color:var(--grn);border-color:var(--grn)}.tag.old{color:var(--gry)}
progress{width:100%;height:8px;margin:.4em 0;accent-color:var(--acc)}
.statusline{color:var(--mut);font-size:.88em;min-height:1.4em}
canvas#kg{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:10px;cursor:grab}
table.meta{border-collapse:collapse;font-size:.88em;width:100%}
table.meta td{border-bottom:1px solid var(--line);padding:.3em .5em;vertical-align:top}
table.meta td:first-child{color:var(--mut);white-space:nowrap;width:110px}
pre.full{white-space:pre-wrap;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.9em;font-size:.9em;line-height:1.5}
.bar{fill:var(--acc)}.lbl{font-size:10px;fill:var(--mut)}
footer{margin-top:2.5em;color:var(--mut);font-size:.82em;border-top:1px solid var(--line);padding-top:1em}
.count{display:inline-block;min-width:3ch}
@media (max-width:600px){body{padding:.8em}.cards{grid-template-columns:1fr}}
</style></head><body>
<header>
<h1>&#x25c8; penfield <small id="v"></small></h1>
<p>Local-first MemPalace browser. Read-only, always. <span id="health"></span></p>
</header>
<nav aria-label="Views">
<button data-s="welcome" class="on">Welcome</button><button data-s="timeline">Timeline</button><button data-s="graph">Graph</button><button data-s="wings">Wings</button><button data-s="stats">Stats</button><button data-s="inspector" id="nav-inspector" style="display:none">Inspector</button>
</nav>
<main>
<section id="s-welcome" class="on" aria-labelledby="h-welcome">
<h2 id="h-welcome">Welcome</h2>
<div class="cards">
<article><h3>&#x25a3; Timeline</h3><p>Drawer filings, diary entries and KG fact lifecycles, newest first. Click anything to inspect it.</p><button data-go="timeline">Open</button></article>
<article><h3>&#x21d2; Graph</h3><p>Knowledge-graph nodes and edges: current vs expired, live layout, click a node for its facts.</p><button data-go="graph">Open</button></article>
<article><h3>&#x25c8; Wings</h3><p>Palace taxonomy: wings, rooms, drawer counts.</p><button data-go="wings">Open</button></article>
<article><h3>&#x25a4; Stats</h3><p>Filings per day, top entities, biggest rooms, latest diary.</p><button data-go="stats">Open</button></article>
</div>
<p class="statusline">Nothing loads until you open a view — this page starts empty on purpose.</p>
</section>
<section id="s-timeline" aria-labelledby="h-timeline">
<h2 id="h-timeline">Timeline</h2>
<div><label>wing: <select id="wing"><option value="">all</option></select></label></div>
<progress id="pg-tl" max="100" value="0" hidden></progress>
<div id="st-tl" class="statusline" role="status"></div>
<div id="tl"></div>
</section>
<section id="s-graph" aria-labelledby="h-graph">
<h2 id="h-graph">Knowledge graph</h2>
<div><label><input type="checkbox" id="kgcur" checked> only current</label>
<button id="kgload">load graph</button></div>
<figure style="margin:.6em 0">
<canvas id="kg" width="680" height="420"></canvas>
<figcaption style="color:var(--mut);font-size:.85em">Live force layout, drag nodes. Blue: current facts, grey: expired.</figcaption>
</figure>
<div id="kgfacts" style="font-size:.9em"></div>
</section>
<section id="s-wings" aria-labelledby="h-wings">
<h2 id="h-wings">Wings</h2>
<progress id="pg-wings" max="100" value="0" hidden></progress>
<div id="st-wings" class="statusline" role="status"></div>
<div id="wings"></div>
</section>
<section id="s-stats" aria-labelledby="h-stats">
<h2 id="h-stats">Stats</h2>
<progress id="pg-stats" max="100" value="0" hidden></progress>
<div id="st-stats" class="statusline" role="status"></div>
<div id="charts"></div>
<h3>Top entities</h3><div id="entities"></div>
<h3>Latest diary</h3><div id="diary"></div>
</section>
<section id="s-inspector" aria-labelledby="h-inspector">
<h2 id="h-inspector">Inspector</h2>
<div id="insp"></div>
<h3>Similar drawers</h3>
<div id="sim"></div>
</section>
</main>
<footer><small>penfield is read-only: it never writes to your palace. Served from localhost.</small></footer>
<script>
const kindIcon = {drawer:"&#x25a3;", diary:"&#x270e;", fact:"&#x21d2;", "fact-ended":"&#x21d0;"};
let flightCtl = null;
function show(sec) {
  try { if (flightCtl) flightCtl.abort(); } catch (e) {}
  flightCtl = new AbortController();
  document.querySelectorAll("nav button[data-s]").forEach(x => x.classList.toggle("on", x.dataset.s === sec));
  document.querySelectorAll("main section").forEach(x => x.classList.toggle("on", x.id === "s-" + sec));
  const ni = document.getElementById("nav-inspector");
  ni.style.display = sec === "inspector" ? "" : "none";
  loadSection(sec);
}
document.querySelectorAll("nav button[data-s]").forEach(b => b.onclick = () => show(b.dataset.s));
document.querySelectorAll("button[data-go]").forEach(b => b.onclick = () => show(b.dataset.go));
const loadedSecs = {};
function loadSection(sec) {
  if (sec === "inspector" || loadedSecs[sec]) return;
  loadedSecs[sec] = true;
  if (sec === "timeline") loadTaxonomy("pg-tl", "st-tl", true);
  if (sec === "wings") loadTaxonomy("pg-wings", "st-wings", false);
  if (sec === "stats") loadStats();
}
function animateCount(el, to) {
  const t0 = performance.now(), dur = 600;
  function step(t) {
    const f = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - f, 3);
    el.textContent = Math.round(to * e).toLocaleString();
    if (f < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
// NDJSON stream reader: real progress (offset/total), never a spinner.
async function fetchStream(url, pg, st, label) {
  pg.hidden = false; pg.removeAttribute("value");
  const r = await fetch(url, {signal: flightCtl.signal});
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "", result = null;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      if (msg.error) throw new Error(msg.error);
      if (msg.done) { result = msg.result; continue; }
      if (typeof msg.step === "number" && typeof msg.steps === "number") {
        pg.value = Math.round((msg.step / msg.steps) * 100);
        if (st) st.textContent = label + ": " + (msg.phase || "") + ` (${msg.step}/${msg.steps})`;
      } else if (typeof msg.progress === "number") {
        pg.value = Math.round(msg.progress * 100);
        if (st) st.textContent = label + " " + Math.round(msg.progress * 100) + "%" +
          (msg.total ? " of " + msg.total.toLocaleString() + " drawers" : "");
      }
    }
  }
  pg.hidden = true;
  if (st) st.textContent = "";
  return result;
}
function evHtml(e) {
  const extra = e.kind === "fact" || e.kind === "fact-ended"
    ? ` data-s="${(e.s||"").replace(/"/g, "")}" data-o="${(e.o||"").replace(/"/g, "")}"` : "";
  return `<article class="ev" data-id="${e.id || ""}" data-kind="${e.kind}"${extra}><span title="${e.kind}">${kindIcon[e.kind]||"&#x25a3;"}</span> ` +
    `<time datetime="${e.t||""}">${(e.t||"").slice(0,16).replace("T"," ")}</time> ` +
    (e.wing ? `<span class="meta">${e.wing}${e.room ? "/" + e.room : ""}</span> ` : "") +
    `${(e.text||"").slice(0,140)}</article>`;
}
function factSearch(box, s, o) {
  box.innerHTML += `<div class="statusline">searching drawers about “${s}”…</div>`;
  fetch("api/search?q=" + encodeURIComponent(s + " " + o) + "&n=5").then(r=>r.json()).then(sr=>{
    if (!sr.ok || !sr.hits.length) { box.querySelector(".statusline").textContent = "no drawers mention it."; return; }
    const div = document.createElement("div");
    div.innerHTML = sr.hits.map(h =>
      `<article class="ev" data-id="${h.id}"><span class="meta">${h.wing||""}/${h.room||""}` +
      (h.distance != null ? ` · d=${h.distance}` : "") + `</span> ${(h.text||"").slice(0,140)}</article>`).join("");
    box.querySelector(".statusline").replaceWith(div);
    wireInspector(box);
  }).catch(err => { box.querySelector(".statusline").textContent = "error: " + err; });
}
function wireInspector(root) {
  root.querySelectorAll(".ev[data-id]").forEach(el => {
    if (el.dataset.id) el.onclick = () => inspectDrawer(el.dataset.id);
  });
  root.querySelectorAll('.ev[data-kind="fact"],.ev[data-kind="fact-ended"]').forEach(el => {
    if (!el.dataset.id && el.dataset.s) el.style.cursor = "pointer";
    if (!el.dataset.id && el.dataset.s) el.onclick = () => factSearch(root, el.dataset.s, el.dataset.o);
  });
}
function loadTimeline(wing) {
  const st = document.getElementById("st-tl"), pg = document.getElementById("pg-tl");
  fetchStream("api/timeline?limit=60&stream=1" + (wing ? "&wing=" + encodeURIComponent(wing) : ""), pg, st, "timeline").then(t=>{
    st.textContent = t.events ? t.events.length + " events" : "";
    const el = document.getElementById("tl");
    if (!t.events || !t.events.length) { el.textContent = "nothing here yet."; return; }
    el.innerHTML = t.events.map(evHtml).join("");
    wireInspector(el);
  }).catch(e => { st.textContent = "error: " + e; });
}
let taxCache = null;
function renderTaxonomy(t) {
  taxCache = t;
  document.getElementById("v").textContent = "v" + t.version;
  const sel = document.getElementById("wing");
  if (sel.options.length <= 1) t.wings.forEach(w => { const o = document.createElement("option"); o.value = o.textContent = w.name; sel.appendChild(o); });
  sel.onchange = () => { loadTimeline(sel.value); };
  const total = t.drawers;
  document.getElementById("wings").innerHTML =
    `<p><span class="count" id="wtotal">0</span> drawers across ${t.wings.length} wings</p>` +
    t.wings.map(w =>
    `<article class="wing"><b>${w.name}</b> — ${w.drawers.toLocaleString()} drawers` +
    w.rooms.map(r => `<div class="room">&nbsp;&nbsp;${r.name}: ${r.drawers.toLocaleString()}</div>`).join("") +
    `</article>`).join("");
  animateCount(document.getElementById("wtotal"), total);
}
function loadTaxonomy(pgId, stId, thenTimeline) {
  const pg = document.getElementById(pgId), st = document.getElementById(stId);
  fetchStream("api/taxonomy?stream=1", pg, st, "scanning").then(t => {
    renderTaxonomy(t);
    if (thenTimeline) loadTimeline(document.getElementById("wing").value || "");
  }).catch(e => {
    document.getElementById("wings").textContent = "error: " + e;
    document.getElementById("tl").textContent = "error: " + e;
  });
}
function inspectDrawer(id) {
  if (!id) return;
  show("inspector");
  const box = document.getElementById("insp"), sim = document.getElementById("sim");
  box.innerHTML = "loading…"; sim.innerHTML = "";
  fetch("api/drawer?id=" + encodeURIComponent(id)).then(r=>r.json()).then(d=>{
    if (!d.ok) { box.textContent = d.error || "not found"; return; }
    box.innerHTML =
      `<table class="meta">` +
      `<tr><td>wing / room</td><td>${d.wing||"?"} / ${d.room||"?"}</td></tr>` +
      `<tr><td>filed</td><td><time datetime="${d.filed_at||""}">${(d.filed_at||"").slice(0,16).replace("T"," ")}</time></td></tr>` +
      (d.source_file ? `<tr><td>source</td><td>${d.source_file.split("/").pop()}</td></tr>` : "") +
      (d.entities ? `<tr><td>entities</td><td>${d.entities}</td></tr>` : "") +
      `</table><pre class="full"></pre>`;
    box.querySelector("pre").textContent = d.text || "(empty)";
    const th = document.createElement("div");
    th.innerHTML = "<h3>Thread</h3><div>loading…</div>";
    box.appendChild(th);
    fetch("api/thread?id=" + encodeURIComponent(id) + "&window=3").then(r=>r.json()).then(t=>{
      if (!t.ok || !t.chunks.length) { th.lastElementChild.textContent = "no thread (single-chunk source)."; return; }
      th.lastElementChild.innerHTML = `<p class="meta">chunk ${t.pos + 1} of ${t.total} in ${t.source}</p>` + t.chunks.map(c =>
        `<article class="ev"${c.current ? ' style="border-color:var(--acc)"' : ""}>` +
        `<span class="meta">#${c.n} · ${c.room||""} · ${(c.t||"").slice(0,16).replace("T"," ")}</span><br>` +
        `${(c.text||"").slice(0,600)}</article>`).join("");
    }).catch(e => { th.lastElementChild.textContent = "error: " + e; });
    fetch("api/similar?id=" + encodeURIComponent(id) + "&n=5").then(r=>r.json()).then(s=>{
      if (!s.ok || !s.similar.length) { sim.textContent = "no similar drawers found."; return; }
      sim.innerHTML = s.similar.map(x =>
        `<article class="ev" data-id="${x.id}"><span class="meta">${x.wing}/${x.room}` +
        (x.distance != null ? ` · d=${x.distance}` : "") + `</span> ${(x.preview||"").slice(0,140)}</article>`).join("");
      wireInspector(sim);
    }).catch(e => { sim.textContent = "error: " + e; });
  }).catch(e => { box.textContent = "error: " + e; });
}
// --- live force-directed KG: rAF loop with cooling + drag, no deps ---
let kgAnim = null;
function drawKG(nodes, edges) {
  const cv = document.getElementById("kg"), ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height, N = nodes.length;
  nodes.forEach((n, i) => {
    const a = (i / Math.max(1, N)) * 2 * Math.PI;
    n.x = W / 2 + Math.cos(a) * W * 0.32; n.y = H / 2 + Math.sin(a) * H * 0.32;
    n.vx = 0; n.vy = 0; n.r = 4 + Math.sqrt(n.count) * 2;
  });
  const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  let sel = null, drag = null, heat = 1;
  function paint() {
    ctx.clearRect(0, 0, W, H);
    edges.forEach(e => {
      const a = nodes[idx[e.s]], b = nodes[idx[e.o]];
      if (!a || !b) return;
      const hot = sel && (e.s === sel || e.o === sel);
      ctx.strokeStyle = hot ? "#58a6ff" : (e.current ? "#1f6feb" : "#30363d");
      ctx.lineWidth = hot ? 2 : 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    nodes.forEach(n => {
      ctx.fillStyle = n.id === sel ? "#58a6ff" : (n.current ? "#3fb950" : "#6e7681");
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill();
      if (n.id === sel || n.count >= 3) {
        ctx.fillStyle = "#e6edf3"; ctx.font = "11px system-ui";
        ctx.fillText(n.id.slice(0, 24), n.x + n.r + 3, n.y + 4);
      }
    });
  }
  function tick() {
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 40;
      const f = 900 / d2 * heat, d = Math.sqrt(d2);
      dx /= d; dy /= d; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    edges.forEach(e => {
      const a = nodes[idx[e.s]], b = nodes[idx[e.o]];
      if (!a || !b || a === drag || b === drag) return;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
      const f = (d - 70) * 0.02;
      a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
    });
    nodes.forEach(n => {
      if (n === drag) return;
      n.vx *= 0.85; n.vy *= 0.85;
      n.x = Math.min(W - 10, Math.max(10, n.x + n.vx));
      n.y = Math.min(H - 10, Math.max(10, n.y + n.vy));
    });
    paint();
    heat *= 0.995;
    if (heat > 0.02) kgAnim = requestAnimationFrame(tick);
    else kgAnim = null;
  }
  function pos(ev) {
    const r = cv.getBoundingClientRect();
    return [(ev.clientX - r.left) * (W / r.width), (ev.clientY - r.top) * (H / r.height)];
  }
  function pick(mx, my) {
    let best = null, bd = 1e9;
    nodes.forEach(n => { const d = (n.x - mx) ** 2 + (n.y - my) ** 2; if (d < bd) { bd = d; best = n; } });
    return bd < 900 ? best : null;
  }
  cv.onmousedown = ev => { const [mx, my] = pos(ev); const n = pick(mx, my); if (n) { drag = n; heat = Math.max(heat, 0.4); } };
  window.onmouseup = () => { drag = null; };
  cv.onmousemove = ev => {
    if (!drag) return;
    const [mx, my] = pos(ev);
    drag.x = Math.min(W - 10, Math.max(10, mx)); drag.y = Math.min(H - 10, Math.max(10, my));
    drag.vx = 0; drag.vy = 0;
  };
  cv.onclick = ev => {
    if (drag) return;
    const [mx, my] = pos(ev);
    const best = pick(mx, my);
    sel = best ? best.id : null;
    paint();
    if (!best) { document.getElementById("kgfacts").textContent = ""; return; }
    const facts = edges.filter(e => e.s === best.id || e.o === best.id);
    document.getElementById("kgfacts").innerHTML =
      `<b>${best.id}</b> (${best.count} facts)<br>` + facts.map((e, i) =>
        `<div class="ev" data-drawer="${e.drawer || ""}" data-fi="${facts.indexOf(e)}" style="${e.drawer ? "cursor:pointer" : ""}">${e.s} &rarr; <b>${e.p}</b> &rarr; ${e.o}` + (e.current ? "" : ` <i>(ended${e.to ? " " + e.to.slice(0, 10) : ""})</i>`) +
        (e.drawer ? ` <span class="meta">open &#8594;</span>` : "") + `</div>`
      ).join("");
    const box = document.getElementById("kgfacts");
    box.querySelectorAll(".ev").forEach((el, i) => {
      const e = facts[i];
      el.style.cursor = "pointer";
      el.onclick = () => {
        if (e.drawer) { inspectDrawer(e.drawer); return; }
        box.innerHTML += `<div class="statusline" id="fsearch">searching drawers about “${e.s}”…</div>`;
        fetch("api/search?q=" + encodeURIComponent(e.s + " " + e.o) + "&n=5").then(r=>r.json()).then(sr=>{
          const div = document.getElementById("fsearch");
          if (!sr.ok || !sr.hits.length) { if (div) div.textContent = "no drawers mention it."; return; }
          if (div) div.outerHTML = sr.hits.map(h =>
            `<article class="ev" data-id="${h.id}"><span class="meta">${h.wing||""}/${h.room||""}` +
            (h.distance != null ? ` · d=${h.distance}` : "") + `</span> ${(h.text||"").slice(0,140)}</article>`).join("");
          wireInspector(box);
        }).catch(err => {
          const div = document.getElementById("fsearch");
          if (div) div.textContent = "error: " + err;
        });
      };
    });
  };
  if (kgAnim) cancelAnimationFrame(kgAnim);
  tick();
}
document.getElementById("kgload").onclick = () => {
  const cur = document.getElementById("kgcur").checked;
  document.getElementById("kgfacts").textContent = "loading…";
  fetch("api/kg?limit=500").then(r=>r.json()).then(g=>{
    let edges = g.edges || [];
    if (cur) edges = edges.filter(e => e.current);
    const keep = new Set();
    edges.forEach(e => { keep.add(e.s); keep.add(e.o); });
    drawKG(g.nodes.filter(n => keep.has(n.id)), edges);
    document.getElementById("kgfacts").textContent =
      g.missing ? "no knowledge graph here." : `${edges.length} facts, drag nodes, click one.`;
  }).catch(e => { document.getElementById("kgfacts").textContent = "error: " + e; });
};
function svgBars(rows, val, maxv, w, h, bh) {
  const bw = Math.max(2, Math.floor(w / Math.max(1, rows.length)) - 2);
  let s = `<svg width="${w}" height="${h}" role="img" style="max-width:100%">`;
  rows.forEach((r, i) => {
    const bhgt = maxv ? Math.round((r[val] / maxv) * bh) : 0;
    const x = i * (bw + 2), y = h - 20 - bhgt;
    s += `<rect class="bar" x="${x}" y="${y}" width="${bw}" height="${bhgt}"><title>${r.day}: ${r[val]}</title></rect>`;
    if (i % Math.ceil(rows.length / 8) === 0) s += `<text class="lbl" x="${x}" y="${h - 6}">${(r.day || "").slice(5)}</text>`;
  });
  return s + "</svg>";
}
function loadStats() {
  const pg = document.getElementById("pg-stats"), st = document.getElementById("st-stats");
  fetchStream("api/stats?days=30&stream=1", pg, st, "scanning").then(t => {
    renderStats(t);
    Promise.all([
      fetch("api/entities?limit=12").then(r=>r.json()),
      fetch("api/diary?limit=3").then(r=>r.json()),
    ]).then(([en, di]) => {
      document.getElementById("entities").innerHTML = (en.entities || []).map(x =>
        `<span class="tag${x.current ? " cur" : " old"}" title="${x.facts} facts">${x.entity} ×${x.facts}</span>`).join(" ") || "none";
      document.getElementById("diary").innerHTML = (di.entries || []).map(e =>
        `<article class="ev" data-id="${e.id}"><time datetime="${e.t||""}">${(e.t||"").slice(0,16).replace("T"," ")}</time> ` +
        `<span class="meta">${e.wing||""}</span> ${(e.text||"").slice(0,160)}</article>`).join("") || "none";
      wireInspector(document.getElementById("diary"));
    }).catch(e => { document.getElementById("entities").textContent = "error: " + e; });
  }).catch(e => { document.getElementById("charts").textContent = "error: " + e; });
}
function renderStats(st) {
  const days = st.by_day || [];
  const maxv = Math.max(1, ...days.map(d => d.drawers));
  const maxf = Math.max(1, ...days.map(d => d.facts));
  const wings = (taxCache ? taxCache.wings : []).slice().sort((a, b) => b.drawers - a.drawers).slice(0, 12);
  const maxw = Math.max(1, ...wings.map(w => w.drawers));
  const tot = days.reduce((a, d) => a + d.drawers, 0);
  let h = `<p><span class="count" id="stotal">0</span> filings in 30 days</p>`;
  h += "<h3>Filings per day</h3>" + svgBars(days, "drawers", maxv, 680, 150, 120);
  h += "<h3>KG facts per day</h3>" + svgBars(days, "facts", maxf, 680, 120, 90);
  h += "<h3>Drawers per wing</h3>";
  wings.forEach(w => {
    const pct = Math.round((w.drawers / maxw) * 100);
    h += `<div style="font-size:.9em">${w.name} <span class="bar" style="display:inline-block;height:10px;width:${Math.max(2, pct * 3)}px"></span> ${w.drawers.toLocaleString()}</div>`;
  });
  document.getElementById("charts").innerHTML = h;
  animateCount(document.getElementById("stotal"), tot);
}
// health only: fast, no scan — the welcome page stays empty otherwise.
fetch("api/health").then(r=>r.json()).then(h=>{
  document.getElementById("v").textContent = "v" + h.version;
  document.getElementById("health").textContent = h.palace;
}).catch(()=>{});
</script></body></html>


"""



class _ClientGone(Exception):
    """Browser went away mid-stream (tab switch, reload, close). Not an
    error: just stop writing. Without this, every navigation paints a
    triple traceback in the console for something the user did on purpose."""


def stream_ndjson(handler, gen) -> None:
    """Chunked newline-delimited JSON: each scan page emits a progress
    event, the last event carries the result. The browser updates a real
    <progress> bar — offset/total, never an animation pretending to know."""
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson")
    handler.send_header("Transfer-Encoding", "chunked")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()

    def emit(obj: object) -> None:
        raw = (json.dumps(obj) + "\n").encode("utf-8")
        try:
            handler.wfile.write(f"{len(raw):X}\r\n".encode() + raw + b"\r\n")
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise _ClientGone()

    try:
        for msg in gen:
            emit(msg)
    except _ClientGone:
        try:
            gen.close()
        except Exception:
            pass
        return
    except Exception as exc:  # noqa: BLE001
        try:
            emit({"error": f"{type(exc).__name__}: {exc}"})
        except _ClientGone:
            return
    try:
        handler.wfile.write(b"0\r\n\r\n")
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # required for chunked streaming above
    server_version = "penfield/" + VERSION

    def _json(self, obj: object, code: int = 200) -> None:
        try:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _html(self, body: str) -> None:
        try:
            raw = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._html(INDEX_HTML)
        elif parsed.path == "/api/health":
            self._json({"ok": True, "version": VERSION, "palace": self.server.palace_path})  # type: ignore[attr-defined]
        elif parsed.path == "/api/taxonomy":
            try:
                qs = parse_qs(parsed.query or "")
                if "stream" in qs:
                    stream_ndjson(self, taxonomy_scan(self.server.palace_path))  # type: ignore[arg-type]
                else:
                    self._json(taxonomy(self.server.palace_path))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001 — JSON error, never a traceback
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/timeline":
            try:
                qs = parse_qs(parsed.query or "")
                wing = (qs.get("wing") or [None])[0]
                lim = min(int((qs.get("limit") or [200])[0]), 1000)
                if "stream" in qs:
                    stream_ndjson(self, timeline_scan(self.server.palace_path, wing, lim))  # type: ignore[arg-type]
                else:
                    self._json(
                        timeline(
                            self.server.palace_path,  # type: ignore[attr-defined]
                            wing=wing,
                            limit=lim,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/kg":
            try:
                qs = parse_qs(parsed.query or "")
                self._json(
                    kg_graph(
                        self.server.palace_path,  # type: ignore[attr-defined]
                        limit=min(int((qs.get("limit") or [500])[0]), 2000),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/drawer":
            try:
                qs = parse_qs(parsed.query or "")
                did = (qs.get("id") or [""])[0]
                if not did:
                    self._json({"ok": False, "error": "usage: /api/drawer?id=DRAWER_ID"}, 400)
                else:
                    self._json(drawer_by_id(self.server.palace_path, did))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/similar":
            try:
                qs = parse_qs(parsed.query or "")
                did = (qs.get("id") or [""])[0]
                n = min(int((qs.get("n") or [5])[0]), 20)
                if not did:
                    self._json({"ok": False, "error": "usage: /api/similar?id=DRAWER_ID&n=5"}, 400)
                else:
                    self._json(similar_to(self.server.palace_path, did, n))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/thread":
            try:
                qs = parse_qs(parsed.query or "")
                did = (qs.get("id") or [""])[0]
                w = min(int((qs.get("window") or [3])[0]), 20)
                if not did:
                    self._json({"ok": False, "error": "usage: /api/thread?id=DRAWER_ID&window=3"}, 400)
                else:
                    self._json(thread_around(self.server.palace_path, did, w))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/diary":
            try:
                qs = parse_qs(parsed.query or "")
                n = min(int((qs.get("limit") or [5])[0]), 50)
                self._json(recent_diary(self.server.palace_path, n))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/search":
            try:
                import mempalace.searcher
                search_memories = mempalace.searcher.search_memories

                qs = parse_qs(parsed.query or "")
                q = (qs.get("q") or [""])[0]
                n = min(int((qs.get("n") or [8])[0]), 30)
                if not q.strip():
                    self._json({"ok": False, "error": "usage: /api/search?q=TEXT&n=8"}, 400)
                else:
                    res = search_memories(q, self.server.palace_path, n_results=n)  # type: ignore[attr-defined]
                    hits = res.get("results") or res.get("hits") or []
                    self._json({"ok": True, "query": q, "hits": [
                        {"id": h.get("drawer_id") or h.get("id"),
                         "wing": h.get("wing"), "room": h.get("room"),
                         "t": h.get("filed_at") or h.get("created_at"),
                         "text": (h.get("text") or h.get("document") or "")[:220],
                         "distance": h.get("distance")}
                        for h in hits if isinstance(h, dict)]})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/entities":
            try:
                qs = parse_qs(parsed.query or "")
                n = min(int((qs.get("limit") or [15])[0]), 100)
                self._json(top_entities(self.server.palace_path, n))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif parsed.path == "/api/stats":
            try:
                qs = parse_qs(parsed.query or "")
                days = min(int((qs.get("days") or [30])[0]), 365)
                if "stream" in qs:
                    stream_ndjson(self, activity_scan(self.server.palace_path, days))  # type: ignore[arg-type]
                else:
                    self._json(
                        activity(
                            self.server.palace_path,  # type: ignore[attr-defined]
                            days=days,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def log_message(self, fmt: str, *args: object) -> None:
        import datetime

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        sys.stderr.write(f"{ts} {self.address_string()} {fmt % args}\n")


def open_collection(palace_path: str):
    """Read-only collection handle. create=False: never creates, never locks."""
    from mempalace.palace import PalaceRef, get_backend_for_palace

    ref = PalaceRef(id=palace_path, local_path=palace_path)
    backend = get_backend_for_palace(palace_path)
    return backend.get_collection(palace=ref, collection_name="mempalace_drawers", create=False)


def scan_pages(palace_path: str, where=None, step: int = 2000):
    """Yields (kind, payload): ("total", n), ("page", (metas, done)), ("end", None).
    Metadata only — embeddings never cross the wire, ever."""
    col = open_collection(palace_path)
    total = col.count()
    yield ("total", total)
    offset = 0
    while True:
        res = col.get(where=where, limit=step, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        if not metas:
            break
        offset += len(metas)
        yield ("page", (metas, offset))
        if len(metas) < step:
            break
    yield ("end", None)


def taxonomy(palace_path: str) -> dict:
    from collections import Counter

    wings: Counter = Counter()
    rooms: Counter = Counter()
    total = 0
    for kind, payload in scan_pages(palace_path):
        if kind == "total":
            total = payload
        elif kind == "page":
            for m in payload[0]:
                w = m.get("wing") or "?"
                wings[w] += 1
                rooms[(w, m.get("room") or "?")] += 1
    by_wing: dict = {}
    for (w, r), n in sorted(rooms.items()):
        by_wing.setdefault(w, []).append({"name": r, "drawers": n})
    return {
        "version": VERSION,
        "palace": palace_path,
        "drawers": total,
        "wings": [
            {"name": w, "drawers": wings[w], "rooms": by_wing.get(w, [])}
            for w in sorted(wings)
        ],
    }


def taxonomy_scan(palace_path: str):
    """Same numbers as taxonomy(), but yields NDJSON progress events."""
    from collections import Counter

    wings: Counter = Counter()
    rooms: Counter = Counter()
    total = 0
    for kind, payload in scan_pages(palace_path):
        if kind == "total":
            total = payload
            yield {"phase": "counted", "total": total, "progress": 0}
        elif kind == "page":
            for m in payload[0]:
                w = m.get("wing") or "?"
                wings[w] += 1
                rooms[(w, m.get("room") or "?")] += 1
            offset = payload[1]
            yield {"phase": "scan", "offset": offset, "total": total,
                   "progress": round(offset / max(1, total), 3)}
    by_wing: dict = {}
    for (w, r), n in sorted(rooms.items()):
        by_wing.setdefault(w, []).append({"name": r, "drawers": n})
    yield {"done": True, "result": {
        "version": VERSION,
        "palace": palace_path,
        "drawers": total,
        "wings": [
            {"name": w, "drawers": wings[w], "rooms": by_wing.get(w, [])}
            for w in sorted(wings)
        ],
    }}



def _unwrap(res):
    """chroma returns dicts or objects depending on path — normalize once."""
    if isinstance(res, dict):
        return (res.get("ids") or [], res.get("metadatas") or [], res.get("documents") or [],
                res.get("embeddings"), res.get("distances"))
    get = lambda k: getattr(res, k, None)  # noqa: E731
    return (get("ids") or [], get("metadatas") or [], get("documents") or [],
            get("embeddings"), get("distances"))


def drawer_by_id(palace_path: str, drawer_id: str) -> dict:
    col = open_collection(palace_path)
    ids, metas, docs, _, _ = _unwrap(col.get(ids=[drawer_id], include=["metadatas", "documents"]))
    if not ids:
        return {"ok": False, "error": "drawer not found"}
    m = metas[0] or {}
    return {"ok": True, "id": ids[0], "wing": m.get("wing"), "room": m.get("room"),
            "filed_at": m.get("filed_at"), "authored_at": m.get("authored_at"),
            "source_file": m.get("source_file"), "entities": m.get("entities"),
            "text": docs[0] if docs else ""}


def similar_to(palace_path: str, drawer_id: str, n: int = 5) -> dict:
    col = open_collection(palace_path)
    ids, metas, docs, emb, _ = _unwrap(col.get(ids=[drawer_id], include=["metadatas", "documents", "embeddings"]))
    if not ids or emb is None:
        return {"ok": False, "error": "drawer not found or has no embedding"}
    vec = emb[0]
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    qids, qmetas, qdocs, _, dists = _unwrap(col.query(
        query_embeddings=[list(vec)], n_results=n + 1, include=["metadatas", "documents", "distances"]))
    out = []
    for i, m, d in zip(qids[0] if qids and isinstance(qids[0], list) else [], qmetas[0] if qmetas else [], qdocs[0] if qdocs else []):
        if i == drawer_id:
            continue
        m = m or {}
        dist = None
        try:
            dist = round(float((dists[0] if dists else [])[len(out)]), 3) if dists else None
        except Exception:
            pass
        out.append({"id": i, "wing": m.get("wing"), "room": m.get("room"),
                    "filed_at": m.get("filed_at"), "preview": (d or "")[:160], "distance": dist})
        if len(out) >= n:
            break
    return {"ok": True, "id": drawer_id, "similar": out}



def thread_around(palace_path: str, drawer_id: str, window: int = 3) -> dict:
    """The conversation around a drawer: same source_file ordered by
    chunk_index (one export window = consecutive exchanges), window chunks
    each side, current highlighted. Full texts — a window is small."""
    col = open_collection(palace_path)
    ids, metas, docs, _, _ = _unwrap(col.get(ids=[drawer_id], include=["metadatas"]))
    if not ids:
        return {"ok": False, "error": "drawer not found"}
    meta = metas[0] or {}
    src = meta.get("source_file") or ""
    idx = meta.get("chunk_index", 0)
    if not src:
        return {"ok": False, "error": "drawer has no source file"}
    ids2, metas2, docs2, _, _ = _unwrap(col.get(
        where={"source_file": src}, limit=5000, offset=0,
        include=["metadatas", "documents"]))
    rows = sorted(
        ((m.get("chunk_index", 0), i, m, d)
         for i, m, d in zip(ids2 or [], metas2 or [], docs2 or [])),
        key=lambda t: t[0] if isinstance(t[0], int) else 0)
    pos = next((k for k, (_, i, _, _) in enumerate(rows) if i == drawer_id), None)
    if pos is None:
        return {"ok": False, "error": "drawer not in its own source listing"}
    lo, hi = max(0, pos - window), pos + window + 1
    return {"ok": True, "id": drawer_id, "source": src.split("/")[-1],
            "total": len(rows), "pos": pos,
            "chunks": [{"id": i, "n": n, "room": (m or {}).get("room"),
                        "t": (m or {}).get("authored_at"),
                        "current": i == drawer_id, "text": d or ""}
                       for n, i, m, d in rows[lo:hi]]}


def recent_diary(palace_path: str, n: int = 5) -> dict:
    col = open_collection(palace_path)
    # get_recent() is oldest-first (see timeline): sort ourselves.
    ids, metas, docs, _, _ = _unwrap(col.get(
        where={"room": "diary"}, limit=10000, offset=0,
        include=["metadatas", "documents"]))
    rows = sorted(
        ((m.get("filed_at") or m.get("authored_at") or "", i, m, d)
         for i, m, d in zip(ids or [], metas or [], docs or [])),
        reverse=True)[:n]
    return {"ok": True, "entries": [
        {"id": i, "wing": (m or {}).get("wing"), "t": (m or {}).get("filed_at") or (m or {}).get("authored_at"),
         "topic": None, "text": (d or "")[:300]}
        for _, i, m, d in rows]}


def top_entities(palace_path: str, n: int = 15) -> dict:
    import sqlite3

    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute(
                "SELECT subject, COUNT(*), SUM(valid_to IS NULL) FROM triples "
                "GROUP BY subject ORDER BY COUNT(*) DESC LIMIT ?", (n,)).fetchall()
        finally:
            db.close()
    except Exception:
        return {"ok": True, "entities": [], "missing": True}
    return {"ok": True, "entities": [
        {"entity": s, "facts": c, "current": bool(cur)} for s, c, cur in rows]}


def kg_graph(palace_path: str, limit: int = 500) -> dict:
    """Knowledge-graph nodes + edges for the graph view. A fact is current
    while valid_to is NULL — same rule `kg_stats` reports. Read-only open;
    empty (not error) when the KG is missing."""
    import sqlite3

    nodes: dict = {}
    edges: list = []
    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute(
                "SELECT subject,predicate,object,valid_from,valid_to,source_drawer_id FROM triples LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            db.close()
    except Exception:
        return {"ok": True, "nodes": [], "edges": [], "missing": True}
    for s, p, o, vf, vt, sd in rows:
        current = vt is None
        for name in (s, o):
            n = nodes.setdefault(name, {"id": name, "count": 0, "current": False})
            n["count"] += 1
            n["current"] = n["current"] or current
        e = {"s": s, "p": p, "o": o, "from": vf, "to": vt, "current": current}
        if sd:
            e["drawer"] = sd
        edges.append(e)
    return {"ok": True, "nodes": sorted(nodes.values(), key=lambda n: -n["count"]), "edges": edges}


def activity(palace_path: str, days: int = 30) -> dict:
    """Filings per day: drawers (+diary split) from metadata filed_at, KG
    facts from extracted_at. One metadata scan + one small KG query; the
    spinner covers the seconds on big palaces."""
    import datetime
    import sqlite3
    from collections import Counter

    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days - 1)).isoformat()
    drawers: Counter = Counter()
    diary: Counter = Counter()
    for kind, payload in scan_pages(palace_path):
        if kind != "page":
            continue
        for m in payload[0]:
            day = (m.get("filed_at") or "")[:10]
            if day and day >= start:
                drawers[day] += 1
                if (m.get("room") or "") == "diary":
                    diary[day] += 1
    facts: Counter = Counter()
    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            for (ex,) in db.execute("SELECT extracted_at FROM triples LIMIT 20000"):
                if ex and ex[:10] >= start:
                    facts[ex[:10]] += 1
        finally:
            db.close()
    except Exception:
        pass
    by_day = []
    for i in range(days):
        day = (today - datetime.timedelta(days=days - 1 - i)).isoformat()
        by_day.append({"day": day, "drawers": drawers.get(day, 0),
                       "diary": diary.get(day, 0), "facts": facts.get(day, 0)})
    return {"ok": True, "days": days, "by_day": by_day}


def activity_scan(palace_path: str, days: int = 30):
    """Same numbers as activity(), but yields NDJSON progress events."""
    import datetime
    import sqlite3
    from collections import Counter

    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days - 1)).isoformat()
    drawers: Counter = Counter()
    diary: Counter = Counter()
    total = 0
    for kind, payload in scan_pages(palace_path):
        if kind == "total":
            total = payload
            yield {"phase": "counted", "total": total, "progress": 0}
        elif kind == "page":
            for m in payload[0]:
                day = (m.get("filed_at") or "")[:10]
                if day and day >= start:
                    drawers[day] += 1
                    if (m.get("room") or "") == "diary":
                        diary[day] += 1
            offset = payload[1]
            yield {"phase": "scan", "offset": offset, "total": total,
                   "progress": round(offset / max(1, total), 3)}
    facts: Counter = Counter()
    yield {"phase": "kg", "progress": 0.98}
    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            for (ex,) in db.execute("SELECT extracted_at FROM triples LIMIT 20000"):
                if ex and ex[:10] >= start:
                    facts[ex[:10]] += 1
        finally:
            db.close()
    except Exception:
        pass
    by_day = []
    for i in range(days):
        day = (today - datetime.timedelta(days=days - 1 - i)).isoformat()
        by_day.append({"day": day, "drawers": drawers.get(day, 0),
                       "diary": diary.get(day, 0), "facts": facts.get(day, 0)})
    yield {"done": True, "result": {"ok": True, "days": days, "by_day": by_day}}


def resolve_palace(explicit: str | None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("MEMPALACE_PALACE_PATH", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/.mempalace/palace"))


def kg_path(palace_path: str) -> str:
    """Same resolution mempalace itself uses: palace-local KG when the palace
    was opened with an explicit path, else the default location."""
    cand = os.path.join(palace_path, "knowledge_graph.sqlite3")
    if os.path.isfile(cand):
        return cand
    return os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3")


def timeline(palace_path: str, wing: str | None = None, limit: int = 200) -> dict:
    """Merged timeline: drawer filings + KG fact lifecycles, newest first.

    Drawers carry filed_at (fallback authored_at); KG triples carry
    extracted_at for birth and valid_to for end. Everything is read with
    read-only opens; the merge cap keeps slow VPS responses small.
    """
    import sqlite3

    events: list = []
    col = open_collection(palace_path)
    # get_recent() returns OLDEST-first despite the name (verified live:
    # Sep-16 backfill rows), so newest-first needs our own sort. One scan
    # carrying (t, id, meta, doc) tuples, sorted desc, page sliced.
    pairs = []
    ids, metas, docs, _, _ = _unwrap(col.get(
        where=({"wing": wing} if wing else None),
        limit=100000, offset=0, include=["metadatas", "documents"]))
    for i, m, d in zip(ids or [], metas or [], docs or []):
        m = m or {}
        t = m.get("filed_at") or m.get("authored_at")
        if t:
            pairs.append((t, i, m, d or ""))
    pairs.sort(key=lambda t: t[0], reverse=True)
    for t, i, m, d in pairs[:limit]:
        room = m.get("room") or "?"
        events.append(
            {
                "id": i,
                "t": t,
                "kind": "diary" if room == "diary" else "drawer",
                "wing": m.get("wing") or "?",
                "room": room,
                "text": (d or "")[:220],
                "source": (m.get("source_file") or "").split("/")[-1] or None,
            }
        )
    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute(
                "SELECT subject,predicate,object,valid_from,valid_to,extracted_at FROM triples LIMIT 5000"
            ).fetchall()
        finally:
            db.close()
        for s, p, o, vf, vt, ex in rows:
            if ex:
                events.append(
                    {"t": ex, "kind": "fact", "wing": None, "room": None,
                     "text": f"{s} → {p} → {o}", "source": None,
                     "s": s, "p": p, "o": o}
                )
            if vt:
                events.append(
                    {"t": vt, "kind": "fact-ended", "wing": None, "room": None,
                     "text": f"{s} → {p} → {o}", "source": None,
                     "s": s, "p": p, "o": o}
                )
    except Exception:
        pass  # KG unreadable: timeline degrades to drawers, never fails
    events.sort(key=lambda e: e["t"], reverse=True)
    return {"ok": True, "wing": wing, "count": len(events[:limit]), "events": events[:limit]}


def timeline_scan(palace_path: str, wing: str | None = None, limit: int = 200):
    """Same numbers as timeline(), in 3 phases the bar can honestly show:
    drawers loaded, KG merged, done. No invented percentages — N of 3 steps."""
    import sqlite3

    yield {"phase": "drawers", "step": 1, "steps": 3}
    events: list = []
    col = open_collection(palace_path)
    pairs = []
    ids, metas, docs, _, _ = _unwrap(col.get(
        where=({"wing": wing} if wing else None),
        limit=100000, offset=0, include=["metadatas", "documents"]))
    for i, m, d in zip(ids or [], metas or [], docs or []):
        m = m or {}
        t = m.get("filed_at") or m.get("authored_at")
        if t:
            pairs.append((t, i, m, d or ""))
    pairs.sort(key=lambda t: t[0], reverse=True)
    for t, i, m, d in pairs[:limit]:
        room = m.get("room") or "?"
        events.append(
            {
                "id": i,
                "t": t,
                "kind": "diary" if room == "diary" else "drawer",
                "wing": m.get("wing") or "?",
                "room": room,
                "text": (d or "")[:220],
                "source": (m.get("source_file") or "").split("/")[-1] or None,
            }
        )
    yield {"phase": "kg", "step": 2, "steps": 3}
    try:
        db = sqlite3.connect(f"file:{kg_path(palace_path)}?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute(
                "SELECT subject,predicate,object,valid_from,valid_to,extracted_at FROM triples LIMIT 5000"
            ).fetchall()
        finally:
            db.close()
        for st, pr, o, vf, vt, ex in rows:
            if ex:
                events.append(
                    {"t": ex, "kind": "fact", "wing": None, "room": None,
                     "text": f"{st} → {pr} → {o}", "source": None,
                     "s": st, "p": pr, "o": o}
                )
            if vt:
                events.append(
                    {"t": vt, "kind": "fact-ended", "wing": None, "room": None,
                     "text": f"{st} → {pr} → {o}", "source": None,
                     "s": st, "p": pr, "o": o}
                )
    except Exception:
        pass
    events.sort(key=lambda e: e["t"], reverse=True)
    yield {"done": True, "result": {"ok": True, "wing": wing,
           "count": len(events[:limit]), "events": events[:limit]}}


def main(argv: list | None = None) -> int:
    ensure_mempalace()
    ap = argparse.ArgumentParser(prog="penfield", description=__doc__.splitlines()[0])
    ap.add_argument("--palace", default=None, help="palace dir (default: MEMPALACE_PALACE_PATH or ~/.mempalace/palace)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1", help="bind address; keep 127.0.0.1 (use SSH forwarding remotely)")
    ns = ap.parse_args(argv)
    palace = resolve_palace(ns.palace)
    if not os.path.isdir(palace):
        sys.stderr.write(f"penfield: no palace at {palace} (pass --palace)\n")
        return 2
    server = HTTPServer((ns.host, ns.port), Handler)
    server.palace_path = palace  # type: ignore[attr-defined]
    # flush=True: stdout to a file is block-buffered, and a boot line you
    # only see after killing the server is no boot line at all.
    print(f"penfield v{VERSION} on http://{ns.host}:{ns.port} (read-only, palace {palace})", flush=True)
    print("endpoints: /api/health /api/taxonomy /api/timeline /api/kg /api/stats", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
