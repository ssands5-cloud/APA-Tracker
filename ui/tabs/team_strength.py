"""Team Strength tab: docs/team_strength.md's HTML layout.

Renders a real, already-computed ``analytics.team_strength.TeamStrengthReport``
-- a REPORTER, the same posture as every other tab in this project. Nothing
here recomputes a component, renormalizes a missing composite, or invents a
strength tier/color/gauge threshold.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from analytics.team_strength import TeamStrengthReport


def _num(value) -> str:
    return "No data" if value is None else str(value)


def _score(value: Optional[float]) -> str:
    return "No data" if value is None else f"{value:.1f}"


def render(report: TeamStrengthReport, title: str = "Team Strength") -> str:
    unavailable = (
        "".join(f"<li>{escape(reason)}</li>" for reason in report.unavailable_reasons)
        or "<li>All components available.</li>"
    )

    player_rows = "".join(
        "<tr>"
        f"<td>{escape(p.player_name)}</td><td>{escape(p.player_external_id)}</td>"
        f"<td>{_num(p.skill_level)}</td><td>{p.matches_won}</td><td>{p.matches_played}</td>"
        f"<td>{_score(p.observed_rate * 100 if p.observed_rate is not None else None)}</td>"
        f"<td>{_num(p.depth_order)}</td>"
        "</tr>"
        for p in sorted(
            report.player_rows,
            key=lambda r: (r.observed_rate is None, -(r.observed_rate or 0), r.player_external_id),
        )
    ) or "<tr><td colspan=\"7\">No canonical roster player found.</td></tr>"

    match_rows = "".join(
        "<tr>"
        f"<td>{_num(m.week)}</td><td>{escape(m.match_date or 'No data')}</td>"
        f"<td>{escape(m.opponent_team_name or 'Unresolved')}</td>"
        f"<td>{'Home' if m.is_home else 'Away'}</td>"
        f"<td>{m.points_for:g}</td><td>{m.points_against:g}</td>"
        "</tr>"
        for m in report.match_rows
    ) or "<tr><td colspan=\"6\">No eligible finalized match found.</td></tr>"

    standings = (
        f"{escape(report.standings_record)} (rank {report.current_rank})"
        if report.standings_record is not None and report.current_rank is not None
        else (escape(report.standings_record) if report.standings_record is not None else "No data")
    )

    return f"""<section id="team-strength" class="ts-tab">
<h2>{escape(title)}</h2>
<p class="ts-sub">{escape(report.team_name)} -- {escape(report.session_name)}.
Descriptive comparison only -- not a validated predictive signal, a lineup
selector, or a strength tier (docs/team_strength.md). Formula version:
{escape(report.formula_version)}.</p>

<table class="ts-summary"><tbody>
<tr><th>Team Strength Index</th><td>{_score(report.team_strength_index)}</td></tr>
<tr><th>Offense (Roster result rate)</th><td>{_score(report.offense_index)}
  ({report.offense_wins}/{report.offense_played} across {report.offense_player_count} players)</td></tr>
<tr><th>Defense (team-score containment proxy)</th><td>{_score(report.defense_index)}
  (PF {report.points_for:g} / PA {report.points_against:g} across {report.defense_match_count} matches)</td></tr>
<tr><th>Depth (fifth-position floor)</th><td>{_score(report.depth_index)}
  ({report.scoreable_player_count} scoreable of {report.roster_count} roster; fifth = {_num(report.depth_player_id)})</td></tr>
<tr><th>Standings (not an index input)</th><td>{standings}</td></tr>
</tbody></table>

<figure id="team-strength-components">
<figcaption>Component scores (0-100 axis; a missing component shows "No data" and is
never included in the composite)</figcaption>
<ul>
<li>Offense: {_score(report.offense_index)}</li>
<li>Defense (proxy): {_score(report.defense_index)}</li>
<li>Depth: {_score(report.depth_index)}</li>
</ul>
</figure>

<h3>Roster Evidence</h3>
<table id="team-strength-roster">
<thead><tr><th>Player</th><th>External ID</th><th>Skill</th><th>Won</th><th>Played</th>
<th>Observed Rate</th><th>Depth Order</th></tr></thead>
<tbody>{player_rows}</tbody>
</table>

<h3>Match Evidence</h3>
<table id="team-strength-matches">
<thead><tr><th>Week</th><th>Date</th><th>Opponent</th><th>Home/Away</th>
<th>Points For</th><th>Points Against</th></tr></thead>
<tbody>{match_rows}</tbody>
</table>

<h3>Unavailable components</h3>
<ul class="ts-unavailable">{unavailable}</ul>

<p class="ts-assumptions">Equal weighting of offense/defense/depth is a design
assumption, not a learned coefficient, and the composite is never renormalized
over a partial subset. Defense is a team-score containment proxy, not a real
defensive-shot rate. These values never alter Player-vs-Player or Lineup Lab
selection (docs/team_strength.md).</p>

<style>
.ts-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
.ts-tab th, .ts-tab td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.ts-tab .ts-summary th {{ width: 300px; }}
.ts-assumptions {{ color: #666e7a; font-size: 12.5px; }}
</style>
</section>"""
