# V2 candidate HTML vs the companion Excel workbook

Checked read-only on Sat Nov 21 2026 against the Sunday companion workbook
`tmp\ultimate-coach-release\broadcast-v7-ui-6d74dc8\Ultimate_Coach_Archive_Evidence.xlsx`
(sha256 `8c795c72e096e2635744acba95fab3413ae3c9d89290b5574066130bbe554acb`, built from workbook source revision 02fa311,
reused unchanged by the v7 build per `workbook-reuse-provenance.json`). Probe: `excel_probe.py` (local).

**Bottom line: the workbook runs M3 only. There is no V2 in Excel, so V2 and Excel recommendations can differ by design.
No V2 parity is claimed.**

| Function | V2 candidate HTML (683d5f5) | Companion Excel (02fa311) | Same? |
|---|---|---|---|
| Recommendation engine | V2 executed policy (estimated win chances; captain-control rule); M3 available via "Compare with M3" | M3 only (six evidence levels, 6/3/1/0/0/-3); start-of-night plan printed from the M3 engine (`wr_Plan*` names) | **No** |
| Answer to their put-up | V2 answer + role (competitive / strategic / concession / best available) | M3 answer from the printed plan (paper cannot re-plan) | **No** |
| Level words | Favored / Edge / Toss-up / Underdog / Long shot | Strong / Solid / Thin / Unknown / Conflicted / Caution | **No** |
| Decision trace, M3-vs-V2 table, engine badge | yes | none | No |
| Skill cap default | 23 for 8/9-Ball, override, clear = off | 23 for 8/9-Ball (`Lineup Lab!C7` formula), override, clear = off | Yes |
| Availability default | Everyone Here unless marked Out | **Blank availability = Unknown**; choices Available/Unavailable/Unknown | **No** (workbook predates the c3e2bbf fix) |
| Out shared by the night | yes (Here/Out applies to every match that night) | marks belong to one fixture | **No** |
| START HERE limitations | current text (cap 23 default, Here unless Out, V2 estimate line) | old text: "no skill cap is assumed", "Unknown availability is not Unavailable", "marks belong to one fixture", "no win-probability model" | **No** (workbook predates a111f46) |
| Recorded records (direct, shared, Player vs Player, scouting) | same recorded data (embedded data identical to the Sunday HTML) | same recorded data (Codex v7 verification: 0 differences) | Yes |
| Five check, Risk briefing, Swap what-if, Player Form | yes (Team Status) | not in the workbook | No |

## What it would take to align them (not done; needs owner approval)
1. Regenerate the workbook from current code (picks up c3e2bbf availability/limits fixes; still M3).
2. A V2 workbook would need the V2 policy in spreadsheet formulas or a precomputed V2 plan table; neither exists.
Until then the workbook must be presented as the M3 companion, not as a V2 deliverable.
