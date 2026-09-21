# Ultimate Coach temporal integrity boundary

This stacked slice hardens the prequential backtest foundation. It still does **not** train, calibrate, score, or publish a matchup probability.

## Why this exists

Chronological backtesting is only meaningful when every target has an unambiguous identity and a globally comparable timestamp. Guessing a timezone, accepting duplicate provenance keys, or tolerating an impossible winner/loser relationship can turn a clean-looking backtest into leakage or double counting.

## Fail-closed rules

A same-format All Games row is excluded when any of these are true:

- `game_key` is blank
- `game_key` is duplicated within that format, in which case every copy is quarantined
- `mirror_status` is not `VERIFIED_UNIQUE`
- timestamp is missing, invalid, or timezone-naive
- the two participants are the same identity
- winner or loser is outside the two participants
- winner and loser are the same identity

No timezone is inferred. No duplicate is arbitrarily selected. No identity or outcome is repaired.

Equivalent instants expressed with different UTC offsets compare correctly as the same instant. Therefore neither may enter the other's prior-history window.

Duplicate-key detection is format-scoped so an EIGHT game and a NINE game do not contaminate one another merely because an upstream key happens to be textually identical.

## Publication lock

`probability_publication` remains `FORBIDDEN`. This is evidence hygiene for a future chronological backtest, not evidence that any model is calibrated.

## Claude audit challenge

Audit the exact frozen SHA after CI passes and try to falsify:

1. a timezone-naive timestamp can never be silently interpreted as local time or UTC
2. two strings representing the same instant cannot leak into each other
3. every copy of a duplicate same-format game key is quarantined
4. a blank provenance key cannot reach a feature row
5. self-pairings and impossible outcomes cannot reach history or targets
6. EIGHT/NINE remain isolated, including duplicate-key checks
7. no excluded row is silently repaired or neutral-filled
8. no probability publication path was introduced
