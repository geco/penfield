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

VERSION = "0.1.0"
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
            os.execv(cand, [cand, me] + sys.argv[1:])
    sys.stderr.write(
        "penfield: mempalace package not importable (tried system python, "
        "MEMPALACE_PYTHON and the pipx/uv venvs). Install mempalace first.\n"
    )
    sys.exit(2)


INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>penfield</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em;color:#222}
h1{font-size:1.4em}.wing{margin:.4em 0}.room{color:#666;font-size:.9em}
a{color:#06c;text-decoration:none}
</style></head><body>
<h1>&#x25c8; penfield <small id="v"></small></h1>
<p>Local-first MemPalace browser. Read-only, always.</p>
<div id="wings">loading&hellip;</div>
<script>
fetch("api/taxonomy").then(r=>r.json()).then(t=>{
  document.getElementById("v").textContent = "v" + t.version;
  const el = document.getElementById("wings");
  el.innerHTML = t.wings.map(w =>
    `<div class="wing"><b>${w.name}</b> — ${w.drawers} drawers` +
    w.rooms.map(r => `<div class="room">&nbsp;&nbsp;${r.name}: ${r.drawers}</div>`).join("") +
    `</div>`).join("");
}).catch(e => { document.getElementById("wings").textContent = "error: " + e; });
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
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
                self._json(taxonomy(self.server.palace_path))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001 — JSON error, never a traceback
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def log_message(self, *args: object) -> None:
        pass  # quiet: stdout stays clean for supervisors


def open_collection(palace_path: str):
    """Read-only collection handle. create=False: never creates, never locks."""
    from mempalace.palace import PalaceRef, get_backend_for_palace

    ref = PalaceRef(id=palace_path, local_path=palace_path)
    backend = get_backend_for_palace(palace_path)
    return backend.get_collection(palace=ref, collection_name="mempalace_drawers", create=False)


def taxonomy(palace_path: str) -> dict:
    from collections import Counter

    col = open_collection(palace_path)
    total = col.count()
    # Paginated metadata scan: no embeddings cross the wire, ever.
    wings: Counter = Counter()
    rooms: Counter = Counter()
    offset = 0
    step = 20000
    while True:
        res = col.get(limit=step, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        if not metas:
            break
        for m in metas:
            w = m.get("wing") or "?"
            wings[w] += 1
            rooms[(w, m.get("room") or "?")] += 1
        offset += len(metas)
        if len(metas) < step:
            break
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


def resolve_palace(explicit: str | None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("MEMPALACE_PALACE_PATH", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/.mempalace/palace"))


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
    print(f"penfield v{VERSION} on http://{ns.host}:{ns.port} (read-only, palace {palace})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
