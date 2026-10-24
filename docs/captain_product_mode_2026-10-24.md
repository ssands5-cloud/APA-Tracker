# Captain Product Mode — decision visibility and subscription readiness

Date: October 24, 2026
Branch: `codex/captain-decision-first`
Review: draft PR #97, targeting `codex/web-platform-v1`
Status: isolated review work; no merge or production deployment.

## Product judgment

The product's strongest proposition is: **avoid spending the right player at the wrong time.**

A captain buys preparation, faster calls and fewer avoidable lineup mistakes. Historical results are supporting evidence. A dramatic header or larger statistics panel does not establish that value.

| Assessment | Score | Interpretation |
| --- | --- | --- |
| Previously audited experience: product value | 6.5/10 | Useful evidence; captain must assemble too much of the decision. |
| Previously audited experience: subscription readiness | 6/10 | Plausible pilot value; weekly dependence and willingness to pay unproven. |
| Current review draft: product value | 7.5/10 provisional | Next action and preservation cost are more visible. This is a product judgment, not a measured usability result. |
| Current review draft: subscription readiness | 6.5/10 provisional | Better explanation supports an invite-only value test, not a proven paid launch. |

These scores do not certify release readiness, security, production data currency, or customer demand. They should not be promoted to 9/10 simply because local tests pass.

## Changes prepared

### Home: four calls before supporting explanation

SEND (conditional on putting up first), PROTECT, THREAT and TRADEOFF now precede the full opening analysis. The fixture and historical-reference qualification remain visible. The summary uses supplied plan outputs only. Additional protected options remain available below it; the first displayed option is not presented as a new ranking.

The lead's reason, actual evidence level, recorded concern and protection targets remain available. No invented numerical confidence, safety rating or win probability is added.

### Match Night: response workflow first

The same compact decision summary remains at the top. Full opening strategy is a disclosure rather than a second expanded lead panel above the Response Explorer. The existing wide explorer and compact Blind Send remain intact. Opening and response recommendations stay conditional on who puts up.

### Shark Tank: prepare a counter

Each threat now leads with the supplied counter and the specific designated answers to preserve for that opponent. It explains why dangerous, the mistake to avoid, the reason for the counter and its future cost. A direct link opens that opponent in Response Explorer.

Missing counters stay missing. Small records remain qualified. Roster-level threat evidence is not extrapolated into an advantage against everyone. No extra threat score or counter ranking is calculated.

### Captain's Briefing: read it to the team

A short numbered briefing covers opening, protection, threat, opportunity cost and pre-start checks. Full rationale is a disclosure; detailed plan evidence remains below. The decorative briefing hero no longer delays the plan.

The briefing can exceed one minute if the supplied protection list is unusually large; no designated player is silently dropped to meet a marketing label.

## Biggest remaining weaknesses

1. **Historical plan versus tonight's reality.** Correct fixture, current rosters, attendance and actual rules must be established before a historical plan becomes operational advice. Presentation cannot solve missing current inputs.
2. **Weekly freshness and delivery.** A refresh completing locally is different from fresh protected data being available in the web app. A visible freshness contract and recovery path matter more than another chart.
3. **No confirmed match-night state in this reviewed surface.** Available, already-played and remaining-player information must be trustworthy before live replanning can be sold. Do not imply this draft implements it.
4. **Untested five-second comprehension.** Browser geometry proves fit, not that a captain understands or trusts the call.
5. **Unproven retention and price.** No new customer interviews, purchase commitments, weekly-return measurements or willingness-to-pay evidence were gathered in this work.
6. **Product language still needs real captain testing.** 'Protect' must mean preserve for a named matchup, not never send. 'Strong Evidence' must never become a promise to win.

## Strongest competitive advantages to test

- Named preservation targets connect today's send to the next decision.
- Opponent-specific counter preparation makes scouting usable at the table.
- Conditional answers and explicit opportunity cost support fast decisions without hiding uncertainty.
- One briefing can align the entire team before play.
- Historical support, unknowns and limitations can be inspected rather than replaced with unexplained scores.

These are product hypotheses. No competitor benchmarking or claim of a unique market capability is implied.

## Top ten features captains may pay for

Rank reflects expected captain value and weekly use. Value and subscription impact are hypotheses to validate; effort is relative and requires an engineering estimate. Existing capabilities should be completed and validated rather than duplicated.

| Rank | Outcome / enhancement | Captain value | Effort | Subscription impact | Payment test |
| --- | --- | --- | --- | --- | --- |
| 1 | Reliable Tonight's Plan: correct scheduled fixture, latest usable snapshot and clear changes since last week | Very high | Medium–high | Very high | Does the captain reopen it every league night? |
| 2 | Match-state-aware response planning using confirmed attendance and players already used | Very high | High | Very high | Does it replace the captain's manual remaining-lineup notes? |
| 3 | Named opportunity-cost warning before spending a designated answer | Very high | Medium | High | Can the captain identify a lineup mistake this prevented? |
| 4 | Actionable opponent dossiers with counter, preservation target and source evidence | High | Low–medium | High | Does the captain use them before seeing the opponent's put-up? |
| 5 | One-minute team briefing plus private, usable team handoff | High | Low–medium | Medium–high | Does the captain actually brief the team from it? |
| 6 | Fixture-based preparation: save and reopen plans for upcoming opponents and formats | High | Medium | High | Does preparation begin before arrival at the venue? |
| 7 | Captain Command Center showing what changed and which decision needs attention | High | Medium | High | Can the captain describe the next action within five seconds? |
| 8 | Player intelligence organized around opening role, protected target and evidence limits | High | Medium | Medium–high | Does it improve a real choice rather than decorate the roster? |
| 9 | Private captain observations, clearly separated from recorded facts | Medium–high | Medium | Medium–high | Does the captain maintain notes and return to use them? |
| 10 | Post-night decision review: what was planned, what was chosen and why | Medium–high | High | Medium–high | Does it improve next week's preparation without claiming causal win uplift? |

Items involving match state, persistence, access, sharing or computation are future work requiring separate authorization, security review and appropriate branches. They are not implemented by this presentation PR. Do not add standings bonuses, skill-level bonuses, recency weights or synthetic coverage scores for beta.

## Exact next sprint: prove the value before building more

**Sprint goal:** a captain can name a send, a preservation target, the threat and the opportunity cost quickly, then use the same plan at league night.

1. Day 1: review draft #97 against the current release candidate and overlapping PR #88. Resolve overlap, run candidate CI and verify protected routes on the actual candidate. No automatic merge or deployment.
2. Day 2: confirm an appropriate upcoming fixture and approved refreshed snapshot in the test environment. Clearly label historical assumptions. Freshness is a separate release gate owned with the platform/refresh work.
3. Day 3: observe five invited captains on their own phones/iPads. Ask 'What should you do next?' without explaining the screen. Record send, target to preserve, threat, cost and time to answer.
4. Day 4: repair only comprehension/navigation problems observed in those sessions. Do not add more statistics, visual effects or engine factors.
5. Day 5 plus next league night: run an invite-only pilot; ask what decision changed, what nearly caused a mistake and whether they would pay to keep using it. Observe return at the following league night before declaring retention.

Acceptance targets: at least four of five captains identify the four decisions in five seconds; all distinguish historical evidence from a live availability claim; no protected navigation/data regressions; no clipping at supported viewports. Seek at least three voluntary next-night returns and explicit paid-pilot interest before investing in the next capability. These are proposed gates, not achieved results or purchase guarantees.

If comprehension fails, simplify. If comprehension succeeds but captains do not return, investigate freshness and operational fit. Do not respond by making the product prettier.

## Engineering handoff and validation

All display content derives from the existing snapshot. Recommendation scoring, authentication, roles, authorization, database architecture and snapshot storage are unchanged.

Local validation:
- Typecheck passed.
- Web suite: 22 passing tests (18 before this increment).
- Production build passed after a Windows filesystem-permission retry.
- 32 Chromium/WebKit viewport cases passed for command, scouting and briefing panels, including standard phone/iPad/desktop and long command text.
- The command summary first-fold assertion includes protected navigation extracted from the actual route; no authentication module is imported by the renderer.
- Source, missing-data behavior, preservation-to-opponent mapping and response deep links are covered with invented fixtures.

Build warnings retained: local `UC_SNAPSHOT_KEY` is unset; middleware convention is deprecated under the installed Next version. This work does not fix, expose or provision secrets, or alter middleware. A successful build is not proof that production historical loading works.

Local viewport checks are not physical iPhone/iPad tests, a real captain comprehension study, or a complete authenticated end-to-end test. No main merge or production deployment was performed. Review candidate branch compatibility before integration.
