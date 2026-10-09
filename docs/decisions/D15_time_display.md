# D15: Time Display

## Context
How to display time to users.

## Decision
**Asia/Tehran, Gregorian dates**. UTC stored everywhere. Jalali is UI toggle.

## Rationale
- User is in Iran (Asia/Tehran)
- Gregorian dates for international consistency
- Jalali (Solar Hijri) as optional display toggle
- UTC in database, conversion at UI edge only

## Consequences
- All timestamps stored as UTC Unix milliseconds
- Display: `Asia/Tehran` timezone
- Date format: YYYY-MM-DD (Gregorian)
- Optional: Jalali date alongside Gregorian
- Time format: HH:MM:SS (24-hour)

## Alternatives Considered
- UTC everywhere → Confusing for local users
- Jalali only → Inconsistent with international data