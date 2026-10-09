# Offline Installation Fallback

## Issue
PyPI (files.pythonhosted.org) is not reachable from the development environment.

## Fallback Options

### Option 1: Vendored Wheels (Recommended)
Download wheels on a machine with internet access and copy them:
```bash
# On machine with internet
pip download -d ./wheels -r requirements.txt

# On offline machine
pip install --no-index --find-links ./wheels -r requirements.txt
```

### Option 2: Stdlib-only Shims
If dependencies cannot be installed, implement minimal shims:
- `pydantic` → Use `dataclasses` + manual validation
- `httpx` → Use `urllib.request` in a thread pool
- `websockets` → Use `asyncio` + `ssl` raw sockets (complex)
- `PyYAML` → Use `json` only configs (simpler)
- `pytest` → Use `unittest` (stdlib)
- `ruff`/`mypy` → Skip linting/type-checking locally, run in CI

### Option 3: Minimal Dependencies
Reduce to only essential packages with no dependencies:
- `pydantic` (has no deps)
- `PyYAML` (has no deps)
- `httpx` (has few deps: certifi, h11, httpcore, idna, sniffio)
- `websockets` (has few deps)

## Current Status
As of 2026-10-10: PyPI unreachable. Development continues with code written TDD-style; tests will run when network is available.