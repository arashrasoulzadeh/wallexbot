# D9: UI Language

## Context
UI language and localization.

## Decision
**English + Persian (fa) with RTL layout**. Persian digits optional. Jalali date display option.

## Rationale
- Primary users: Iran-based traders
- RTL support essential for Persian
- Persian digits (۰-۹) preferred by some users
- Jalali (Solar Hijri) calendar for local date display
- UTC stored everywhere, conversion at display edge only

## Consequences
- All UI text in message catalogs (`en.json`, `fa.json`)
- Language switch persists in cookie
- `dir="rtl"` on `<html>` for Persian
- Number formatting: Decimal-safe, no float
- Date formatting: Gregorian + Jalali toggle

## Alternatives Considered
- English only → Excludes primary user base
- Auto-detect from browser → Unreliable, no user control