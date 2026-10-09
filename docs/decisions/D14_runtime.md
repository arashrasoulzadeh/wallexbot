# D14: Runtime

## Context
Where and how does the bot run?

## Decision
**This Mac, on demand** — no 24/7 uptime, no launchd, no keep-awake.

## Rationale
- Development machine, not a server
- User starts bot when wanted
- Crash recovery (Phase 9) still required
- No need for daemonization

## Consequences
- No systemd/launchd service files
- No keep-alive scripts
- User runs `wallexbot paper` or `wallexbot ui` manually
- Web UI binds to 127.0.0.1 only

## Alternatives Considered
- Systemd service → Not needed for on-demand use
- Docker with restart policy → Overkill
- Cron job → Too rigid