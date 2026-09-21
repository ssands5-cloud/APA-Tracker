# Ultimate Coach canonical data contract

## One source of truth

The Ultimate Coach architecture is:

```
APA GraphQL
    ↓
SQLite: data/ultimate_coach_staging.db
    ↓
analytics/ultimate_coach_data_contract.py
    ↓
┌────────────────────┬─────────────────────┐
│ offline HTML       │ Excel workbook      │
│ Scout & Compare    │ advisor / reports   │
└────────────────────┴─────────────────────┘
```

SQLite is authoritative. Excel and HTML are views. Neither is allowed to create
a second private factual dataset that can drift away from SQLite.

## Flat tables

`scripts/export_ultimate_coach_data.py` writes the following shared datasets.

### all_games.csv

One canonical row per recorded individual player-vs-player game.

This is the primary factual table that a human should be able to inspect when
asking, "Why does the Matchup Advisor say this?"

Important columns include:

- team match id / APA external id
- real match date
- session
- format
- week/location
- both canonical player ids/names
- both captured team ids/names when PlayerMatch establishes them
- both match-time skill levels
- observed W/L
- winner / loser
- points/9-ball balls where available from the canonical source direction
- `mirror_status`

`mirror_status` is evidence quality, not a cosmetic field:

- `VERIFIED_UNIQUE`: exactly one directional row each way and they reconcile
- `VERIFIED_COUNT_ONLY`: repeated same-player pairings exist and both source
  directions reconcile as multisets, but the persisted schema no longer
  carries the original source position number needed to pair participant-B
  detail one-by-one
- `MISSING_REVERSE`: canonical source direction exists without its stored
  mirror
- `MIRROR_MISMATCH`: both directions exist but do not reconcile
- `REVERSE_ONLY`: only the opposite stored direction exists

Rows are never invented to make the two directions agree.

### raw_h2h_evidence.csv

Every stored `PlayerHeadToHead` row, one perspective per row.

This is the forensic/audit layer beneath All Games. Excel should normally show
All Games to a captain and keep Raw H2H available for investigation.

### team_matches.csv

Every `Match` row, including scheduled/final/scored/bye state and team score.

### player_match_stats.csv

Every match-linked `PlayerMatch` row. This is where per-team-match source
fields such as break-and-run/on-break/on-snap counts live. They must not be
pretended to be per-individual-game fields when a player appeared twice in one
team match.

### players.csv

Canonical player/member identity and current captured snapshot.

### career_stats.csv

League-scoped lifetime stats with exact APA alias provenance.

### team_history.csv

Cross-session team membership and historical skill-level context.

### coverage_issues.csv

Explicit structural/source limitations discovered while projecting the data.
Nothing in this table is auto-repaired by the export.

## Excel ownership rules

The future Ultimate Coach workbook must expose the raw contract as Excel tables.

Required factual tabs:

1. `All Games`
2. `Raw H2H`
3. `Team Matches`
4. `Player Match Stats`
5. `Players`
6. `Career Stats`
7. `Team History`
8. `Data Coverage`

Intelligence tabs such as `Matchup Advisor`, `Player Scout`,
`Players I've Faced`, and the dashboard must reference those tables. They
must not embed separate hand-painted copies of matchup facts below or beside the
visible report.

A derived/model cell must be visibly distinguishable from a factual source
cell. The workbook should provide a trace/evidence section showing which
All Games rows support a direct record.

## Matchup Advisor contract

Until a calibrated model passes the held-out chronological gate:

- direct W/L may be calculated from All Games
- shared-opponent summaries may be calculated from All Games
- current/historical SL may be read from Players, Team History and All Games
- lifetime aggregate context may be read from Career Stats
- a calibrated win-probability cell must remain unavailable / not calibrated

The advisor may sort or summarize evidence. It may not replace missing evidence
with guessed matches or force historical totals to match APA lifetime totals.

## Reproducible export

```powershell
python scripts/export_ultimate_coach_data.py
```

Default source:

`data/ultimate_coach_staging.db`

Default destination:

`exports/ultimate_coach_data/`

The manifest records row counts and file ownership for audit.
