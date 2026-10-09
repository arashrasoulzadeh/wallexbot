# D10: Extras

## Context
Which extra features to include?

## Decision
Include: **Telegram alerts**, **Docker packaging**, **Pluggable strategies**.

## Rationale
- Telegram: Popular in Iran, bot token is not a Wallex key (safe)
- Docker: Packaging only, not for dev (per ground rules)
- Pluggable strategies: Enables future DCA, trailing grid, etc.

## Consequences
- Telegram: Outbound only, token/env only, never logged
- Docker: Multi-stage build, non-root, health check
- Plugin API: Formalized `Strategy` protocol, registry, contract tests

## Alternatives Considered
- Discord/Slack → Less popular in Iran
- Kubernetes → Overkill for single bot
- Hardcoded strategies → Blocks future extensions