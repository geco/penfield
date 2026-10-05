# penfield

Local-first visual browser for your MemPalace memory. Read-only, always.

- One command: `penfield`, open `http://localhost:8766`
- Stdlib only, no build step, no telemetry
- Never takes the palace writer lock — safe to run while mines write
- Headless VPS: `ssh -L 8766:localhost:8766 <vps>`, browse from home

## Install

Requires MemPalace installed (`pipx install mempalace` or `uv tool install mempalace`):

```bash
pipx install penfield
penfield --palace ~/opencode-memory
```

## Status

v0.1.0 scaffold: health + taxonomy endpoints, wing/room overview page.
Next: timeline, knowledge-graph view, drawer inspector, semantic search.
