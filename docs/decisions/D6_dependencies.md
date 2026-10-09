# D6: Dependencies

## Context
Use `pydantic` + `httpx` + `websockets` vs stdlib-only?

## Decision
Use `pydantic` v2 + `httpx` + `websockets` + `PyYAML`. Stdlib fallbacks documented.

## Rationale
- `pydantic` v2: Best-in-class config validation, performance
- `httpx`: Async HTTP with retry/timeout/transport injection for tests
- `websockets`: Standard async WebSocket client
- `PyYAML`: Standard YAML parser
- All are pure Python or have binary wheels
- Fallback: if PyPI unreachable, document offline install or stdlib shims

## Consequences
- ~15MB additional install size
- Requires internet for initial install (or vendored wheels)
- Much faster development than stdlib-only

## Alternatives Considered
- Stdlib only (`dataclasses`, `urllib`, `asyncio`, `json`) → 3-5x more code, harder to maintain
- `attrs` + `aiohttp` → Similar but `pydantic` has better validation