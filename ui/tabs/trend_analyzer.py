"""Trend Analyzer tab: docs/trend_analyzer.md's dedicated presentation
contract, layered over the existing ui/tabs/trends.py table (unchanged).

Renders a real, already-computed ``analytics.trend_analyzer.TrendAnalyzerReport``
-- a REPORTER. Nothing here recalculates slope, changes the 20-reading
volatility window, or converts an unavailable indicator to NEUTRAL.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from analytics.trend_analyzer import TrendAnalyzerReport

NO_DATA = "No data"


def _num(value, fmt: str = "{:.4f}") -> str:
    return NO_DATA if value is None else fmt.format(value)


def _pct(value: Optional[float]) -> str:
    return NO_DATA if value is None else f"{value * 100:.1f}%"


def render(report: TrendAnalyzerReport, title: str = "Trend Analyzer") -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(r.player_name)}</td><td>{escape(r.format or NO_DATA)}</td>"
        f"<td>{escape(r.session_name or NO_DATA)}</td><td>{r.sample_size}</td>"
        f"<td>{r.current_skill_level if r.current_skill_level is not None else NO_DATA}</td>"
        f"<td>{_num(r.regression_slope, '{:+.4f}')}</td><td>{_num(r.volatility)}</td>"
        f"<td>{_num(r.sl_stability)}</td><td>{_num(r.trend_score)}</td>"
        f"<td>{escape(r.hot_cold_indicator or NO_DATA)}</td>"
        f"<td>{_pct(r.projected_sl_change_probability)}</td>"
        "</tr>"
        for r in report.rows
    ) or '<tr><td colspan="11">No measured player trends in this scope.</td></tr>'

    return f"""<section id="trend-analyzer" class="ta-tab">
<h2>{escape(title)}</h2>
<p class="ta-sub">{escape(report.team_name)} -- {escape(report.session_name)}
{'-- ' + escape(report.format) if report.format else ''}. Descriptive skill-level
history only -- not a claim about effort, health, future match outcome, or an
APA re-rating decision (docs/trend_analyzer.md). Formula version:
{escape(report.formula_version)}.</p>

<p class="ta-counts">{len(report.rows)} row(s) &middot; {report.hot_count} HOT &middot;
{report.cold_count} COLD &middot; {report.neutral_count} NEUTRAL &middot;
{report.no_data_count} No data.</p>

<figure id="trend-score-bars">
<figcaption>Trend score (signed; positive = climbing, negative = declining; zero
center; missing values are omitted, not zero)</figcaption>
<ul>{"".join(f"<li>{escape(r.player_name)}: {_num(r.trend_score)}</li>" for r in report.rows) or "<li>No data.</li>"}</ul>
</figure>

<table id="trend-analyzer-table">
<thead><tr><th>Player</th><th>Format</th><th>Session</th><th>Sample</th>
<th>Current SL</th><th>Slope (SL/match)</th><th>Volatility (last 20)</th>
<th>Stability</th><th>Trend Score</th><th>Trend Indicator</th>
<th>Upward-SL Heuristic</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<p class="ta-assumptions">Slope spans all usable observations in the session;
volatility spans only the most recent 20. Trend score and the HOT/COLD/NEUTRAL
indicator describe direction and steadiness of captured skill-level history
only -- they cannot alter lineup selection, produce Avoid/Target advice, or be
combined with Player-vs-Player probability into a hidden category. The Upward-
SL Heuristic is a transparent heuristic, not a learned probability or a
match-win forecast.</p>

<style>
.ta-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
.ta-tab th, .ta-tab td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.ta-assumptions {{ color: #666e7a; font-size: 12.5px; }}
</style>
</section>"""
