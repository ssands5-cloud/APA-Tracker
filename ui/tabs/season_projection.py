"""Season Projection tab: docs/season_projection.md's HTML layout.

Renders a real, already-computed ``analytics.season_projection`` result --
a REPORTER, the same posture as every other tab in this project. Nothing
here recomputes a probability, a rate, or an expected value.
"""

from __future__ import annotations

from html import escape
from typing import Optional, Sequence

from analytics.season_projection import RemainingMatchProjection, SeasonProjection, StandingsPoint


def _pct(value: Optional[float]) -> str:
    return "No data" if value is None else f"{value * 100:.1f}%"


def _num(value) -> str:
    return "No data" if value is None else str(value)


def render(
    projection: SeasonProjection,
    standings_points: Sequence[StandingsPoint],
    team_name: str,
    session_name: str,
    actual_wins: Optional[int],
    actual_losses: Optional[int],
    capture_time: Optional[str],
    title: str = "Season Projection",
) -> str:
    actual_record = (
        f"{actual_wins}-{actual_losses}" if actual_wins is not None and actual_losses is not None
        else "No data"
    )
    projected_final_wins = (
        round(actual_wins + projection.expected_wins, 2)
        if actual_wins is not None else None
    )
    projected_final_losses = (
        round(actual_losses + projection.expected_losses, 2)
        if actual_losses is not None else None
    )

    rows = "".join(
        "<tr>"
        f"<td>{_num(m.week)}</td><td>{escape(m.match_id)}</td>"
        f"<td>{escape(m.opponent_team_name or 'Unresolved')}</td>"
        f"<td>{_pct(m.win_probability)}</td>"
        f"<td>{escape(m.probability_source.value)}</td>"
        f"<td>{_pct(m.upset_likelihood)}</td>"
        "</tr>"
        for m in projection.matches
    )

    curve_points = "".join(
        f"<li>{escape(p.captured_at)}: {p.wins}-{p.losses} ({_pct(p.win_rate)})</li>"
        for p in standings_points
    ) or "<li>No real standings history captured yet.</li>"

    return f"""<section class="sp-tab">
<h2>{escape(title)}</h2>
<p class="sp-sub">{escape(team_name)} -- {escape(session_name)}.
Capture time: {escape(capture_time or "No data")}. Projects only the real
remaining schedule from real season-to-date records -- no future lineup is
simulated (docs/season_projection.md).</p>

<table class="sp-summary"><tbody>
<tr><th>Actual record</th><td>{actual_record}</td></tr>
<tr><th>Remaining matches</th><td>{len(projection.matches)}</td></tr>
<tr><th>Coverage (matches with a real probability)</th><td>{_pct(projection.coverage)}</td></tr>
<tr><th>Expected remaining W-L</th><td>{projection.expected_wins:.2f} - {projection.expected_losses:.2f}</td></tr>
<tr><th>Projected final record</th><td>{_num(projected_final_wins)} - {_num(projected_final_losses)}</td></tr>
</tbody></table>

<h3>Standings history (deduplicated to real record changes)</h3>
<ul>{curve_points}</ul>

<h3>Remaining match projections</h3>
<table class="sp-matches">
<thead><tr><th>Week</th><th>Match</th><th>Opponent</th><th>Win Probability</th>
<th>Probability Source</th><th>Upset Likelihood</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<p class="sp-assumptions">Log5 (Bill James) win probability from real season
win rates only -- stationary over the remaining schedule, no lineup/home-away/
travel/forfeit/availability effects. A one-side fallback (see Probability
Source column) is a disclosed real behavior, not an imputed opponent rate.
No playoff band, confidence interval, or categorical season outcome is
invented.</p>

<style>
.sp-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
.sp-tab th, .sp-tab td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.sp-tab .sp-summary th {{ width: 260px; }}
.sp-assumptions {{ color: #666e7a; font-size: 12.5px; }}
</style>
</section>"""
