# Player vs Player HTML structure

The HTML export is a self-contained report generated from the versioned export
envelope. The existing `ui/tabs/player_vs_player.py` renders one
`PlayerVsPlayerSummary`; the planned `exports/html_builder.py` wraps those
fragments in a scope/pair index. It performs presentation-only filtering and
does not fetch data, call analytics, or recompute probabilities in the browser.

## Document outline

```text
main#player-vs-player
├── header#pvp-header
│   ├── title and selected match scope
│   ├── capture timestamp / manifest ID
│   └── validation-status banner
├── nav#pvp-navigation
│   ├── Tonight's Match
│   ├── Player vs Player (current)
│   ├── Lineup Lab
│   └── Data Coverage
├── section#pvp-controls
│   ├── player filter
│   ├── opponent filter
│   ├── evidence-label filter
│   └── Show all / reset
├── section#pvp-summary
│   ├── feasible-pair count
│   ├── DIRECT / INDIRECT / UNKNOWN counts
│   └── source and missing-field disclosure
├── section#pvp-table
│   └── table#pvp-pairings
│       └── one row per canonical feasible pair
├── section#pvp-detail
│   ├── selected pair identity and scope
│   ├── recognized-game record and timeline
│   ├── probabilities kept separate
│   ├── break/run unavailability disclosure
│   ├── player-level form context
│   └── next-match projection / unavailable reason
└── footer#pvp-provenance
```

## Table columns

The compact index shows Player, Current Player SL, Opponent, Current Opponent
SL, Format, Session, Evidence, Distinct Direct Matches, Recognized Games,
History Reliability, Last Recorded Skill Probability, Experimental Modeled
Probability, Pair Trend, Recent Pair Trend, and Forward Pair Projection.

The selected-pair fragment reuses the existing stats table, inline-SVG timeline,
and chronological games table. Innings, per-opponent defense, break/run rate,
and numeric volatility remain visible as named unavailable fields in the shell
disclosure rather than receiving fabricated columns in the analytics summary.

## Interaction rules

- Tonight's Match can link to a pair via stable external IDs and scope values.
  The router selects that existing row; it never accepts names as identity.
- Filters hide rows only at the user's request. Reset restores the canonical
  full order, including every UNKNOWN row.
- Selecting a row opens its detail panel without changing any metric.
- Game-history entries preserve the chronological order returned by
  `head_to_head_history`, with match ID as the deterministic tie-break already
  applied by the query. Their result and real posted skill readings are visible.
- Evidence labels use text and accessible descriptions; color is supplemental.

## No-data and safety rules

Null displays as “No data,” followed by a concise reason in the detail panel.
Zero remains numeric zero. For UNKNOWN, the adapter passes an empty row list to
`summarize`, yielding an honest 0-0 record, zero reliability, null
probabilities/projection, `no data` trends, and no timeline markers. UNKNOWN
rows retain the same identity and navigation affordances as DIRECT/INDIRECT.

All captured text is escaped. Embedded JSON escapes HTML parser delimiters.
There are no external scripts, fonts, images, or network requests. Controls are
labelled and keyboard-operable; the table has scoped headers and a descriptive
caption. At narrow widths the table scrolls horizontally while the summary and
detail sections remain readable.
