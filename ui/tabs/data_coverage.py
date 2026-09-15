"""Data Coverage tab: docs/captain_first_edge_experience.md §11.

Renders ``analytics.data_coverage.DataCoverageReport`` -- a REPORTER, the
same posture as every other tab in this project: displays what that module
computed, recomputes nothing, and cannot disagree with the matrix it was
built from.

Self-contained HTML fragment, no external resources.
"""

from __future__ import annotations

from html import escape

from analytics.data_coverage import DataCoverageReport


def _pct(value) -> str:
    return "No data" if value is None else f"{value * 100:.1f}%"


def render(
    report: DataCoverageReport,
    our_team_name: str,
    opponent_team_name: str,
    title: str = "Data Coverage",
) -> str:
    coverage = report.evidence_coverage

    missing = "".join(
        f"<li>{escape(m.side.capitalize())}: {escape(m.player_name)} "
        f"({escape(m.player_external_id)})</li>"
        for m in report.missing_skill_levels
    ) or "<li>None -- every player in this matrix has a real posted skill level.</li>"

    sample_rows = "".join(
        "<tr>"
        f"<td>{escape(s.player_name)}</td><td>{escape(s.opponent_name)}</td>"
        f"<td>{escape(s.evidence_label.value)}</td>"
        f"<td>{s.direct_matches if s.direct_matches is not None else 'No data'}</td>"
        f"<td>{s.player_skill_level if s.player_skill_level is not None else 'No data'}</td>"
        f"<td>{s.opponent_skill_level if s.opponent_skill_level is not None else 'No data'}</td>"
        f"<td>{escape(s.model_source or 'No data')}</td>"
        "</tr>"
        for s in report.sample_sizes
    )

    career_rows = "".join(
        f"<li>{escape(player_id)}: {escape(ts or 'No data')}</li>"
        for player_id, ts in sorted(report.career_stats_refreshed_at.items())
    ) or "<li>No real PlayerCareerStats.updated_at rows available.</li>"

    unavailable = "".join(f"<li>{escape(field)}</li>" for field in report.unavailable_fields)

    return f"""<section class="dc-tab">
<h2>{escape(title)}</h2>
<p class="dc-sub">{escape(our_team_name)} vs {escape(opponent_team_name)} --
{escape(report.format)} / {escape(report.session_name)}. How much of this
matchup's evidence can actually be trusted right now.</p>

<h3>Evidence coverage</h3>
<table class="dc-coverage"><tbody>
<tr><th>DIRECT</th><td>{coverage.direct_count}</td><td>{_pct(coverage.direct_pct)}</td></tr>
<tr><th>INDIRECT</th><td>{coverage.indirect_count}</td><td>{_pct(coverage.indirect_pct)}</td></tr>
<tr><th>UNKNOWN</th><td>{coverage.unknown_count}</td><td>{_pct(coverage.unknown_pct)}</td></tr>
<tr><th>Total feasible pairings</th><td>{coverage.total}</td><td>100%</td></tr>
</tbody></table>

<h3>Missing skill levels</h3>
<ul>{missing}</ul>

<h3>Sample sizes</h3>
<table class="dc-samples">
<thead><tr><th>Player</th><th>Opponent</th><th>Evidence</th><th>Direct Matches</th>
<th>Player SL</th><th>Opponent SL</th><th>Model Source</th></tr></thead>
<tbody>{sample_rows}</tbody>
</table>

<h3>Refresh dates</h3>
<p>Standings last captured: <b>{escape(report.standings_refreshed_at or "No data")}</b></p>
<p>Player career stats last updated:</p>
<ul>{career_rows}</ul>

<h3>Unavailable fields</h3>
<ul class="dc-unavailable">{unavailable}</ul>

<style>
.dc-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
.dc-tab th, .dc-tab td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.dc-tab .dc-coverage th {{ width: 220px; }}
.dc-unavailable {{ color: #666e7a; }}
.dc-sub {{ color: #444b54; }}
</style>
</section>"""
