# penfield

Local-first visual browser for your [MemPalace](https://github.com/MemPalace/mempalace) memory. Read-only, always.

MemPalace is a powerful backend, but it is opaque: wings, rooms, drawers, diary entries and knowledge-graph facts are only reachable through CLI or MCP calls. Penfield is the human view of the same data — browse it, follow it over time, see how facts connect.

- One command: `penfield`, open `http://localhost:8766`
- **Views**: timeline (drawer filings, diary entries, KG fact lifecycles), knowledge-graph canvas (current vs expired, click a node for its facts), wings/rooms drill-down, stats (filings per day, drawers per wing)
- **Stdlib only** — no build step, no JavaScript dependencies, no telemetry, no CDN calls. The page is one hand-written HTML file.
- **Never takes the palace writer lock** — SQLite opened read-only, collections opened with `create=False`. Safe to run while mines write.
- **Headless VPS**: bind stays on `127.0.0.1`; reach it with `ssh -L 8766:localhost:8766 <vps>`.

## Install

Requires MemPalace installed (`pipx install mempalace` or `uv tool install mempalace`):

```bash
pipx install penfield
penfield --palace ~/opencode-memory
```

## Endpoints

All JSON, all read-only: `/api/health`, `/api/taxonomy`, `/api/timeline?wing=&limit=`,
`/api/kg?limit=`, `/api/stats?days=`.

## Status

v0.1.5: dark theme, inspector + similar, live KG, top entities, diary feed.

v0.1.2: timeline, KG graph, wings, stats. Next: drawer inspector with semantic-similar lookup.
