# penfield

Local-first regulator for your [MemPalace](https://github.com/MemPalace/mempalace) memory: see it, navigate it, curate it — and invent new memories on purpose.

MemPalace is a powerful backend, but it is opaque: wings, rooms, drawers, diary entries and knowledge-graph facts are only reachable through CLI or MCP calls. Penfield is the human hand on the same data — browse it, follow it over time, see how facts connect, fix what is wrong, delete what is junk, file what never happened.

- One command: `penfield`, open `http://localhost:8766`
- **Views**: timeline (drawer filings, diary entries, KG fact lifecycles), knowledge-graph canvas (current vs expired, click a node for its facts), wings/rooms drill-down, stats (filings per day, top entities, latest diary), inspector (full text, metadata, conversation thread, similar drawers)
- **Curation**: correct text, move wing/room, delete (two-click confirm), invent memories from scratch — same tool functions the MCP server calls, lock held seconds, never a lifetime lease
- **Stdlib only** — no build step, no JavaScript dependencies, no telemetry, no CDN calls. The page is one hand-written HTML file.
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

v0.3.0: English UI, sidebar layout, heal duplicates, paged timeline, local filter, zoomable graph.

v0.1.5: dark theme, inspector + similar, live KG, top entities, diary feed.

v0.1.2: timeline, KG graph, wings, stats. Next: drawer inspector with semantic-similar lookup.
