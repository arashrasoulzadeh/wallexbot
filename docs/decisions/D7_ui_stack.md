# D7: UI Stack

## Context
Choose web UI technology stack.

## Decision
**FastAPI + HTMX** (server-rendered Jinja2 templates, no Node build).

## Rationale
- FastAPI: Native async, OpenAPI, type-safe, fast
- HTMX: Progressive enhancement, no SPA complexity
- Jinja2: Standard Python templating, i18n support
- No Node.js/npm/build step: Simpler deployment, smaller attack surface
- Vendored chart library (lightweight-charts): No CDN dependency

## Consequences
- Server-rendered HTML with partial updates via HTMX
- WebSocket for live updates (SSE fallback)
- Bilingual (EN/FA) with RTL support
- Responsive, accessible

## Alternatives Considered
- React/Vue SPA → Build complexity, separate frontend/backend
- Streamlit/Dash → Less control, heavier
- Plain HTML + JS → More boilerplate