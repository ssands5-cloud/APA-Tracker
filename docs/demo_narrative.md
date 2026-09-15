# Demo narrative

The story is told from a captain's point of view: “What do we know about this
real match, how much of it is direct evidence, and where does the system refuse
to guess?”

## Opening

Start on Tonight's Match. Select the real team, opponent, format, and session.
Point out that the controls come from the schedule and database, not free text
or a guessed “most recent” match. The capture/provenance line establishes when
the snapshot was actually collected.

## Evidence before advice

Read the evidence cards first. DIRECT means recognized results from distinct,
scored, finalized, non-bye matches for this exact player/opponent and scope.
INDIRECT means both current roster skill levels support the validated skill-only
probability. UNKNOWN means the evidence is insufficient. The total is visibly
reconciled to the feasible matrix, so the audience sees coverage before a
recommendation.

## Unified Player vs Player tab

Open Player vs Player and choose Matrix View. Show that every feasible pairing
remains visible, including UNKNOWN. Change one availability toggle and show the
visible candidate rows update for tonight's choice; explain that the matrix is produced by
`analytics/player_vs_player_matrix.py`, while the evidence labels themselves
still come from Stage 1 and are not recomputed from browser guesses.

## Pair View and Opponent Risk Profile

Before discussing the assignment, select one matrix row to switch the same tab
to Pair View, whose analytics are owned by `analytics/player_vs_player.py`. Show its
recognized game history, Stage 1 distinct-match evidence, history reliability,
last-recorded skill-only probability, and the full model/projection alias as
separate experimental context. Then point to the named unavailable innings,
defense, break/run, and numeric-volatility fields. The value of this view is as
much in what it refuses to infer as in the real history it displays.

Then show the same evidence in Captain's Edge's Opponent Risk Profile. Call out
that it is a build-time snapshot and availability-dependent. Recommended Avoid
and Recommended Target currently read **Not available — threshold not
validated**. This is intentional: no arbitrary modeled-probability or
volatility cutoff is presented as advice.

## Lineup Lab

Move to the approved lineup. Explain that Stage 3 uses one shared, validated
skill-only score for DIRECT and INDIRECT rows; a historical DIRECT record is
displayed but is not silently treated as calibrated selection evidence. The
solver chooses the largest exact scoreable matching, then shows unassigned
players and opponents. A complete five-player lineup carries the real 23-rule
legality verdict; a partial or blocked result is an honest answer.

## Data Coverage

Close by naming missing skill levels, direct sample sizes, refresh timestamps,
coverage percentages, and unavailable APA fields. The key product behavior is
that the tool makes uncertainty legible instead of converting it into a neat
but unsupported number.

## Supporting exports

Open the analysis tabs and workbook only after the primary story. They provide
historical detail and handoff formats. Explicitly distinguish the legacy
Captain's Edge/optimizer artifacts from the captain-first validated path, and
identify modules still excluded under Issue #14.
