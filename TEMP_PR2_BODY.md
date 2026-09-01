# PR 2: Parser Defects

## Title
Parser defects: fail on shape mismatch, identify match tables by header

## Base
main

## Compare
claude/parser-defect-fixes

## Body

This PR contains three commits fixing parser defects identified in the state audit:

### Commit 1: Raise on table shape mismatch
parse_table mapped cells to columns positionally via dict(zip(...)). A row of the wrong width therefore shifted every field after the discrepancy and returned without complaint. From the state audit, one extra leading cell:

```
expected  {'rank': '1', 'team_name': 'Cue Crew', 'wins': '10',       ...}
actual    {'rank': '',  'team_name': '1',        'wins': 'Cue Crew', ...}
```

parse_table now validates each row's width against the declared columns and raises TableShapeError naming the selector, the row index, the declared columns and the cells actually received. strict=False keeps the old skip-and-continue behaviour for exploratory work.

Two related cases handled:
- Header rows inside <tbody> (every cell a <th>) are skipped rather than returned as a data row
- A table selector matching nothing now raises TableNotFoundError in strict mode

### Commit 2: Remove dead selector keys and fix docstring
TEAM_PAGE["roster_table_selector" / "roster_row_selector" / "roster_columns"] and PLAYER_PAGE["stats_columns" / "stats_table_selector"] were read by nothing. Roster parsing uses MATCH_PAGE selectors; player parsing used no map at all.

They were a trap: PLAYER_PAGE["stats_columns"] declared a column order contradicting the one _parse_match_row actually uses, so wiring the map back up would have silently misfiled skill level as the match result.

The module docstring now states verification status per map and records what was removed and why so the keys are not reinstated casually.

### Commit 3: Identify match tables by headers, not cell count
_extract_match_history walked every table and treated any row of three or more cells as a match. A navigation bar, a lifetime summary widget and a header row all clear that bar. Against the audit fixture it returned five matches, four fabricated.

A table now qualifies only if its headers name both a date column and an opponent column. When tables exist but none qualify, that is logged at WARNING so "found nothing" cannot be read as "played nothing".

All 28 tests pass. The audit fixtures are now regression tests.
