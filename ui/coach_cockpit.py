"""One-stop Coach Cockpit composition layer.

This module deliberately does not copy Match Night, matchup, lineup, or Data
Coverage logic. It composes the already-audited ``ui.dashboard`` page with the
already-existing ``ui.tabs.data_coverage`` reporter so a captain can see both
from one generated artifact.

The composition seam is intentionally narrow and fail-closed: the base
Dashboard must contain exactly one ``</body>`` marker. If that contract ever
changes, rendering raises instead of silently dropping, duplicating, or
misplacing Data Coverage.
"""

from __future__ import annotations

from html import escape
from typing import Optional, Sequence

from analytics.data_coverage import DataCoverageReport
from analytics.opponent_risk_profile import OpponentRiskEntry
from analytics.player_matchup_engine import PlayerMatchupReport
from analytics.team_matchup_engine import TeamMatchupReport
from ui.dashboard import render as render_dashboard
from ui.tabs.data_coverage import render as render_data_coverage

_BODY_END = "</body>"


def _scope_key_from_team(report: TeamMatchupReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def _scope_key_from_coverage(report: DataCoverageReport) -> str:
    return f"{report.opponent_team_external_id}|{report.format}|{report.session_name}"


def _coverage_sections(
    reports: Sequence[DataCoverageReport],
    team_reports: Sequence[TeamMatchupReport],
    our_team_name: str,
) -> str:
    team_by_scope = {_scope_key_from_team(report): report for report in team_reports}
    sections: list[str] = []
    for report in reports:
        key = _scope_key_from_coverage(report)
        team_report = team_by_scope.get(key)
        opponent_name = (
            team_report.opponent_team_name
            if team_report is not None
            else report.opponent_team_external_id
        )
        label = f"{opponent_name} — {report.format} / {report.session_name}"
        body = render_data_coverage(
            report,
            our_team_name,
            opponent_name,
            title="Data Coverage",
        )
        sections.append(
            '<details class="dc-embedded">'
            f'<summary>{escape(label)}</summary>{body}</details>'
        )
    return "".join(sections)


def render(
    player_reports: Sequence[PlayerMatchupReport],
    team_reports: Sequence[TeamMatchupReport],
    opponent_risk_entries: Sequence[OpponentRiskEntry],
    our_team_name: str,
    built_at: Optional[str] = None,
    data_coverage_reports: Sequence[DataCoverageReport] = (),
) -> str:
    """Render one Coach Cockpit from existing trusted reporter outputs.

    ``data_coverage_reports`` defaults to empty for backwards-compatible
    callers. Missing coverage is shown explicitly rather than inferred from
    another timestamp or silently omitted.
    """
    base = render_dashboard(
        player_reports,
        team_reports,
        opponent_risk_entries,
        our_team_name,
        built_at=built_at,
    )
    if base.count(_BODY_END) != 1:
        raise ValueError("Coach Dashboard must contain exactly one </body> marker")

    sections = _coverage_sections(data_coverage_reports, team_reports, our_team_name)
    coverage_html = f"""
<section id="data-coverage-freshness" class="dc-cockpit-section">
<style>
.dc-cockpit-section {{ margin-top: 32px; }}
.dc-embedded {{ margin: 10px 0; overflow-x: auto; }}
.dc-embedded > summary {{ cursor: pointer; font-weight: 700; padding: 10px 0; }}
.dc-embedded .dc-tab {{ min-width: 0; }}
</style>
<h2>Data Coverage &amp; Freshness</h2>
<p class="cd-note">Real evidence coverage, missing posted skill levels, sample sizes, and
refresh timestamps already captured by the Data Coverage reporter. No age threshold or
"fresh/stale" verdict is invented here. Read the real timestamps and gaps before relying
on a matchup decision.</p>
{sections if sections else '<p class="cd-none">No Data Coverage report is available for this bundle.</p>'}
</section>
"""
    return base.replace(_BODY_END, coverage_html + _BODY_END)
