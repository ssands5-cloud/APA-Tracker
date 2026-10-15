---
name: captain-decision-review
description: Use when building, changing or auditing any Ultimate Coach recommendation or screen (Next Send, Blind Send, Threat Panel, Scouting Cards, Coach Notes, Captain Matrix, War Room, Captain Packet), or when a feature passes its tests but a captain might not trust or understand it.
---

# Captain Decision Review

## Overview

Ultimate Coach is a captain's decision-support system, not an APA data project. A feature is judged by the decision it supports during a live league night or tournament, not by whether the code is correct. Code can be right and the recommendation still misleading.

**This is not a planning step or an approval gate.** Do not block or delay implementation on it. Its job is to catch "technically correct but captain-misleading" features and to improve trust, clarity and decision quality. Apply it while building or auditing, fix what it finds, and keep going.

**Core principle:** decision first, then reason, then evidence. Unknown is never shown as weak or as safe. No odds, no probability models.

## When to Use

- Any new or changed recommendation, ranking, label, color, badge or warning
- Any audit of a feature that "works" but feels untrustworthy
- Before calling a captain-facing feature complete

Not for: pure data-pipeline, scraper or identity work with no captain-visible output.

## The Eight Questions

1. What decision is the captain trying to make?
2. Does this feature answer that decision?
3. Is the answer obvious?
4. Would a captain trust the recommendation?
5. Is there contradictory information elsewhere?
6. Is evidence strength represented honestly?
7. Does the feature surface the decision before the evidence?
8. Would this help during a live league night or tournament?

Decisions to test against: Who should I send next? Who should I put up first? Who should I avoid? Who is dangerous? Who should I save? What risks remain? What don't I know?

## The Four Tests

**CAPTAIN TEST** — If I were standing in a tournament right now, would this help me make a better decision?

**TRUST TEST** — Would another experienced captain trust this recommendation? Check sample size, recency, opponent skill level at the time, and whether excluded or missing results could flip it.

**CONSISTENCY TEST** — Does this screen contradict another screen for the same evidence? Compare the same pairing across Next Send, Blind Send, Threat Panel, Scouting Cards, Captain Matrix, War Room, the workbook and the Captain Packet. Compare labels, ranks, colors, thresholds and wording.

Example of a failure: a Scouting Card calls 1-2 meetings a "small sample" while Next Send shows the same 1-0 as #1 "Best-supported response".

**MATCH-NIGHT TEST** — Can I understand this recommendation in under 5 seconds? If not, name why: too much text, answer buried, jargon, a label that overclaims, a warning hidden in small print.

## Red Flags

- A recommendation whose label claims more than its sample supports
- Different screens using different definitions of "better", "favorable" or "small sample"
- Unknown availability or unknown evidence ranked or colored like a known result
- A top pick that is illegal or impractical (skill cap, availability) with no warning at the point of the pick
- A caveat that lives only on a trust or data page, not at the decision
- Ties that hide a real difference (recency, opponent skill level)
- Tests that prove the code matches itself but never exercise the captain-visible surface

## Output Format

For audits, give exactly:

- **Captain decision being supported**
- **Trust concerns** (sample size, evidence quality, wording that overclaims)
- **Missing information** (what the captain still can't tell)
- **Contradictions** (screen A vs screen B, with the shared evidence)
- **Recommendation** (smallest change that fixes the trust problem; do not redesign ranking)

Mark each finding as read in code, verified by running, or inferred. Do not pad with process or history.

## Where to Apply

Run it as part of normal review for: Next Send Engine, Blind Send, Threat Panel, Scouting Cards, Coach Notes, Captain Matrix, War Room, Captain Packet. Highest value: any change touching ranking order, labels, colors or sample-size wording, and any change that must stay consistent across HTML, workbook and packet.
