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

VERSION = "0.1.4"
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
<html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>penfield</title>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:2em auto;padding:0 1em;color:#222}
h1{font-size:1.4em}h2{font-size:1.1em;margin-top:1.2em}
nav{margin:1em 0}nav button{margin-right:.4em;padding:.35em .8em;cursor:pointer}
nav button.on{font-weight:bold}
section{display:none}section.on{display:block}
.wing{margin:.4em 0}.room{color:#666;font-size:.9em}
.ev{margin:.3em 0;font-size:.92em}.ev i{color:#666}
.bar{fill:#369}.bar.dim{fill:#999}.lbl{font-size:10px;fill:#666}
a{color:#06c;text-decoration:none}
progress{width:100%;margin:.4em 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.8em}
.cards article{border:1px solid #ccc;border-radius:6px;padding:.8em}
.cards h3{margin:.2em 0;font-size:1em}
footer{margin-top:2em;color:#666;font-size:.85em}
</style></head><body>
<header>
<h1>&#x25c8; penfield <small id="v"></small></h1>
<p>Local-first MemPalace browser. Read-only, always. <span id="health"></span></p>
</header>
<nav aria-label="Views">
<button data-s="welcome" class="on">Welcome</button><button data-s="timeline">Timeline</button><button data-s="graph">Graph</button><button data-s="wings">Wings</button><button data-s="stats">Stats</button>
</nav>
<main>
<section id="s-welcome" class="on" aria-labelledby="h-welcome">
<h2 id="h-welcome">Welcome</h2>
<div class="cards">
<article><h3>Timeline</h3><p>Drawer filings, diary entries and KG fact lifecycles, newest first.</p><button data-go="timeline">Open</button></article>
<article><h3>Graph</h3><p>Knowledge-graph nodes and edges: current vs expired, click a node for its facts.</p><button data-go="graph">Open</button></article>
<article><h3>Wings</h3><p>Palace taxonomy: wings, rooms, drawer counts.</p><button data-go="wings">Open</button></article>
<article><h3>Stats</h3><p>Filings per day and drawers per wing.</p><button data-go="stats">Open</button></article>
</div>
<p>Nothing loads until you open a view — this page starts empty on purpose.</p>
</section>
<section id="s-timeline" aria-labelledby="h-timeline">
<h2 id="h-timeline">Timeline</h2>
<div><label>wing: <select id="wing"><option value="">all</option></select></label></div>
<progress id="pg-tl" max="100" value="0" hidden></progress>
<div id="st-tl" role="status"></div>
<div id="tl"></div>
</section>
<section id="s-graph" aria-labelledby="h-graph">
<h2 id="h-graph">Knowledge graph</h2>
<div><label><input type="checkbox" id="kgcur" checked> only current</label>
<button id="kgload">load graph</button></div>
<progress id="pg-kg" max="100" value="0" hidden></progress>
<figure>
<canvas id="kg" width="680" height="420" style="border:1px solid #ccc;max-width:100%"></canvas>
<figcaption>Force-directed layout, computed locally. Blue: current facts, grey: expired.</figcaption>
</figure>
<div id="kgfacts" style="font-size:.9em"></div>
</section>
<section id="s-wings" aria-labelledby="h-wings">
<h2 id="h-wings">Wings</h2>
<progress id="pg-wings" max="100" value="0" hidden></progress>
<div id="st-wings" role="status"></div>
<div id="wings"></div>
</section>
<section id="s-stats" aria-labelledby="h-stats">
<h2 id="h-stats">Stats</h2>
<progress id="pg-stats" max="100" value="0" hidden></progress>
<div id="st-stats" role="status"></div>
<div id="charts"></div>
</section>
</main>
<footer><small>penfield is read-only: it never writes to your palace. Served from localhost.</small></footer>
<script>
const kindIcon = {drawer:"&#x25a3;", diary:"&#x270e;", fact:"&#x21d2;", "fact-ended":"&#x21d0;"};
function show(sec) {
  document.querySelectorAll("nav button").forEach(x => x.classList.toggle("on", x.dataset.s === sec));
  document.querySelectorAll("main section").forEach(x => x.classList.toggle("on", x.id === "s-" + sec));
  loadSection(sec);
}
document.querySelectorAll("nav button").forEach(b => b.onclick = () => show(b.dataset.s));
document.querySelectorAll("button[data-go]").forEach(b => b.onclick = () => show(b.dataset.go));
const loadedSecs = {};
function loadSection(sec) {
  if (loadedSecs[sec]) return;
  loadedSecs[sec] = true;
  if (sec === "timeline" || sec === "wings") loadTaxonomy();
  if (sec === "stats") loadStats();
}
// NDJSON stream reader: real progress (offset/total), never a spinner.
async function fetchStream(url, pg, st, label) {
  pg.hidden = false; pg.removeAttribute("value");
  const r = await fetch(url);
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
      if (typeof msg.progress === "number") {
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
function loadTimeline(wing) {
  const st = document.getElementById("st-tl");
  st.textContent = "loading…";
  fetch("api/timeline?limit=60" + (wing ? "&wing=" + encodeURIComponent(wing) : "")).then(r=>r.json()).then(t=>{
    st.textContent = "";
    const el = document.getElementById("tl");
    if (!t.events || !t.events.length) { el.textContent = "nothing here yet."; return; }
    el.innerHTML = t.events.map(e =>
      `<article class="ev"><span title="${e.kind}">${kindIcon[e.kind]||"&#x25a3;"}</span> ` +
      `<time datetime="${e.t||""}"><b>${(e.t||"").slice(0,16).replace("T"," ")}</b></time> ` +
      (e.wing ? `<i>${e.wing}${e.room ? "/" + e.room : ""}</i> ` : "") +
      `${(e.text||"").slice(0,140)}</article>`).join("");
  }).catch(e => { st.textContent = "error: " + e; });
}
let taxCache = null;
function renderTaxonomy(t) {
  taxCache = t;
  document.getElementById("v").textContent = "v" + t.version;
  const sel = document.getElementById("wing");
  if (sel.options.length <= 1) t.wings.forEach(w => { const o = document.createElement("option"); o.value = o.textContent = w.name; sel.appendChild(o); });
  sel.onchange = () => { loadTimeline(sel.value); };
  document.getElementById("wings").innerHTML = t.wings.map(w =>
    `<article class="wing"><b>${w.name}</b> — ${w.drawers} drawers` +
    w.rooms.map(r => `<div class="room">&nbsp;&nbsp;${r.name}: ${r.drawers}</div>`).join("") +
    `</article>`).join("");
}
function loadTaxonomy() {
  const pg = document.getElementById("pg-wings"), st = document.getElementById("st-wings");
  const pg2 = document.getElementById("pg-tl"), st2 = document.getElementById("st-tl");
  pg.hidden = false; pg2.hidden = false;
  fetchStream("api/taxonomy?stream=1", pg, st, "scanning").then(t => {
    renderTaxonomy(t);
    loadTimeline("");
  }).catch(e => {
    document.getElementById("wings").textContent = "error: " + e;
    document.getElementById("tl").textContent = "error: " + e;
  }).finally(() => { pg2.hidden = true; });
}// --- force-directed KG on canvas: fixed iterations, no dependencies ------
function drawKG(nodes, edges) {
  const cv = document.getElementById("kg"), ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height, N = nodes.length;
  nodes.forEach((n, i) => {
    const a = (i / Math.max(1, N)) * 2 * Math.PI;
    n.x = W / 2 + Math.cos(a) * W * 0.32; n.y = H / 2 + Math.sin(a) * H * 0.32;
    n.vx = 0; n.vy = 0; n.r = 4 + Math.sqrt(n.count) * 2;
  });
  const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  for (let it = 0; it < 160; it++) {
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 40;
      const f = 900 / d2, d = Math.sqrt(d2);
      dx /= d; dy /= d; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    edges.forEach(e => {
      const a = nodes[idx[e.s]], b = nodes[idx[e.o]];
      if (!a || !b) return;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
      const f = (d - 70) * 0.02;
      a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
    });
    nodes.forEach(n => {
      n.vx *= 0.85; n.vy *= 0.85;
      n.x = Math.min(W - 10, Math.max(10, n.x + n.vx));
      n.y = Math.min(H - 10, Math.max(10, n.y + n.vy));
    });
  }
  function paint(sel) {
    ctx.clearRect(0, 0, W, H);
    edges.forEach(e => {
      const a = nodes[idx[e.s]], b = nodes[idx[e.o]];
      if (!a || !b) return;
      const hot = sel && (e.s === sel || e.o === sel);
      ctx.strokeStyle = hot ? "#06c" : (e.current ? "#bbd" : "#ddd");
      ctx.lineWidth = hot ? 2 : 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    nodes.forEach(n => {
      ctx.fillStyle = n.id === sel ? "#06c" : (n.current ? "#369" : "#999");
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill();
      if (n.id === sel || n.count >= 3) {
        ctx.fillStyle = "#222"; ctx.font = "11px system-ui";
        ctx.fillText(n.id.slice(0, 24), n.x + n.r + 3, n.y + 4);
      }
    });
  }
  paint(null);
  cv.onclick = ev => {
    const r = cv.getBoundingClientRect();
    const mx = (ev.clientX - r.left) * (W / r.width), my = (ev.clientY - r.top) * (H / r.height);
    let best = null, bd = 1e9;
    nodes.forEach(n => { const d = (n.x - mx) ** 2 + (n.y - my) ** 2; if (d < bd) { bd = d; best = n; } });
    if (!best || bd > 900) return;
    paint(best.id);
    const facts = edges.filter(e => e.s === best.id || e.o === best.id);
    document.getElementById("kgfacts").innerHTML =
      `<b>${best.id}</b> (${best.count} facts)<br>` + facts.map(e =>
        `${e.s} &rarr; <b>${e.p}</b> &rarr; ${e.o}` + (e.current ? "" : ` <i>(ended${e.to ? " " + e.to.slice(0, 10) : ""})</i>`)
      ).join("<br>");
  };
}
document.getElementById("kgload").onclick = () => {
  const cur = document.getElementById("kgcur").checked;
  fetch("api/kg?limit=500").then(r=>r.json()).then(g=>{
    let edges = g.edges || [];
    if (cur) edges = edges.filter(e => e.current);
    const keep = new Set();
    edges.forEach(e => { keep.add(e.s); keep.add(e.o); });
    drawKG(g.nodes.filter(n => keep.has(n.id)), edges);
    document.getElementById("kgfacts").textContent =
      g.missing ? "no knowledge graph here." : `${edges.length} facts, click a node.`;
  }).catch(e => { document.getElementById("kgfacts").textContent = "error: " + e; });
};
function svgBars(rows, val, maxv, w, h, bh) {
  const bw = Math.max(2, Math.floor(w / Math.max(1, rows.length)) - 2);
  let s = `<svg width="${w}" height="${h}" role="img">`;
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
  fetchStream("api/stats?days=30&stream=1", pg, st, "scanning").then(renderStats).catch(e => {
    document.getElementById("charts").textContent = "error: " + e;
  });
}
function renderStats(st) {
  const days = st.by_day || [];
  const maxv = Math.max(1, ...days.map(d => d.drawers));
  const maxf = Math.max(1, ...days.map(d => d.facts));
  const wings = (taxCache ? taxCache.wings : []).slice().sort((a, b) => b.drawers - a.drawers).slice(0, 12);
  const maxw = Math.max(1, ...wings.map(w => w.drawers));
  let h = "<figure><figcaption>Filings per day (30d)</figcaption>" + svgBars(days, "drawers", maxv, 680, 150, 120) + "</figure>";
  h += "<figure><figcaption>KG facts per day</figcaption>" + svgBars(days, "facts", maxf, 680, 120, 90) + "</figure>";
  h += "<h3>Drawers per wing</h3>";
  wings.forEach(w => {
    const pct = Math.round((w.drawers / maxw) * 100);
    h += `<div style="font-size:.9em">${w.name} <span style="display:inline-block;background:#369;height:10px;width:${Math.max(1, pct * 3)}px"></span> ${w.drawers}</div>`;
  });
  document.getElementById("charts").innerHTML = h;
  if (!taxCache) fetch("api/taxonomy").then(r=>r.json()).then(t => {
    taxCache = t;
    document.getElementById("v").textContent = "v" + t.version;
    renderStats(st);
  });
}
// health only: fast, no scan — the welcome page stays empty otherwise.
fetch("api/health").then(r=>r.json()).then(h=>{
  document.getElementById("v").textContent = "v" + h.version;
  document.getElementById("health").textContent = h.palace;
}).catch(()=>{});
</script></body></html>
"""


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
        handler.wfile.write(f"{len(raw):X}\r\n".encode() + raw + b"\r\n")
        handler.wfile.flush()

    try:
        for msg in gen:
            emit(msg)
    except Exception as exc:  # noqa: BLE001
        emit({"error": f"{type(exc).__name__}: {exc}"})
    handler.wfile.write(b"0\r\n\r\n")
    handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # required for chunked streaming above
    server_version = "penfield/" + VERSION

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

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
                self._json(
                    timeline(
                        self.server.palace_path,  # type: ignore[attr-defined]
                        wing=(qs.get("wing") or [None])[0],
                        limit=min(int((qs.get("limit") or [200])[0]), 1000),
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
                "SELECT subject,predicate,object,valid_from,valid_to FROM triples LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            db.close()
    except Exception:
        return {"ok": True, "nodes": [], "edges": [], "missing": True}
    for s, p, o, vf, vt in rows:
        current = vt is None
        for name in (s, o):
            n = nodes.setdefault(name, {"id": name, "count": 0, "current": False})
            n["count"] += 1
            n["current"] = n["current"] or current
        edges.append({"s": s, "p": p, "o": o, "from": vf, "to": vt, "current": current})
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
    where = {"wing": wing} if wing else None
    got = 0
    offset = 0
    step = 5000
    while got < limit:
        res = col.get(where=where, limit=min(step, limit - got), offset=offset, include=["metadatas", "documents"])
        metas = res.get("metadatas") or []
        docs = res.get("documents") or []
        if not metas:
            break
        for m, d in zip(metas, docs):
            t = m.get("filed_at") or m.get("authored_at")
            if not t:
                continue
            room = m.get("room") or "?"
            events.append(
                {
                    "t": t,
                    "kind": "diary" if room == "diary" else "drawer",
                    "wing": m.get("wing") or "?",
                    "room": room,
                    "text": (d or "")[:220],
                    "source": (m.get("source_file") or "").split("/")[-1] or None,
                }
            )
            got += 1
        offset += len(metas)
        if len(metas) < step:
            break
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
                     "text": f"{s} → {p} → {o}", "source": None}
                )
            if vt:
                events.append(
                    {"t": vt, "kind": "fact-ended", "wing": None, "room": None,
                     "text": f"{s} → {p} → {o}", "source": None}
                )
    except Exception:
        pass  # KG unreadable: timeline degrades to drawers, never fails
    events.sort(key=lambda e: e["t"], reverse=True)
    return {"ok": True, "wing": wing, "count": len(events[:limit]), "events": events[:limit]}


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
