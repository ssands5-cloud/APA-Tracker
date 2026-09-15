# Demo dashboard layout

The presentation uses a captain-first hierarchy: tonight's decision and its
evidence are primary; broad historical exports are supporting material.

## Screen layout

```text
┌──────────────────────────────────────────────────────────────┐
│ APA Tracker · Tonight's Match · capture time · data status   │
├──────────────────────────────────────────────────────────────┤
│ Team │ Opponent │ Format │ Session │ Available players       │
├──────────────────────────────────────────────────────────────┤
│ Evidence: DIRECT ## (##%) · INDIRECT ## (##%) · UNKNOWN ##  │
├───────────────────────────────┬──────────────────────────────┤
│ Pairing matrix                 │ Data Coverage                │
│ ours × opponent               │ skill gaps, samples, times  │
├───────────────────────────────┴──────────────────────────────┤
│ Lineup Lab: approved / unassigned / legality or blocked      │
├──────────────────────────────────────────────────────────────┤
│ Links: analysis tabs · JSON · workbook · run manifest        │
└──────────────────────────────────────────────────────────────┘
```

## Information hierarchy

1. **Context** — real selected match scope and capture freshness.
2. **Coverage** — whether the captain has direct evidence, skill-only
   evidence, or no defensible input.
3. **Matrix** — every feasible pairing, including UNKNOWN rows.
4. **Lineup Lab** — the approved maximum scoreable matching, unassigned sides,
   and the real legality verdict.
5. **Exports** — links to detailed historical and machine-readable views.

The primary page should not lead with the excluded modeled stack, lineup-risk
badge, or season projection. Those modules can remain available in their
existing supporting artifacts with their documented limitations.

## Workbook layout

The workbook remains an audit and handoff surface rather than the opening
screen. Existing sheets (Standings, Player Stats, Career Stats, Team History,
Skill Level History, Matchups, Head-to-Head, and optional analysis sheets)
retain their source labels. Stage 3's captain-first evidence and Data Coverage
are demonstrated in HTML first; a workbook extension should be a separate,
explicitly scoped change after the HTML contract is stable.

