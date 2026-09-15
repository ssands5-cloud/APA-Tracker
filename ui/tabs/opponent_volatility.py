"""Opponent Volatility tab: docs/opponent_volatility.md's HTML layout.

Renders a real, already-computed
``analytics.opponent_volatility.OpponentVolatilityProfile`` -- a REPORTER.
No danger color, traffic-light category, or "riskiest" default order.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from analytics.opponent_volatility import OpponentVolatilityProfile

NO_DATA = "No data"


def _num(value, fmt: str = "{:.2f}") -> str:
    return NO_DATA if value is None else fmt.format(value)


def _pct(value: Optional[float]) -> str:
    return NO_DATA if value is None else f"{value * 100:.1f}%"


def render(profile: OpponentVolatilityProfile, title: str = "Opponent Volatility") -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(r.player_name)}</td><td>{_num(r.sample_size, '{:d}') if r.sample_size is not None else NO_DATA}</td>"
        f"<td>{_num(r.sigma, '{:.4f}')}</td><td>{_num(r.sl_stability, '{:.4f}')}</td>"
        f"<td>{_num(r.volatility_index)}</td><td>{escape(r.descriptor)}</td>"
        f"<td>{_num(r.regression_slope, '{:+.4f}')}</td>"
        f"<td>{escape(r.format or NO_DATA)}</td><td>{escape(r.session_name or NO_DATA)}</td>"
        f"<td>{escape(r.source_status)}</td>"
        "</tr>"
        for r in profile.player_rows
    ) or '<tr><td colspan="10">No canonical opponent roster player found.</td></tr>'

    return f"""<section id="opponent-volatility" class="ov-tab">
<h2>{escape(title)}</h2>
<p class="ov-sub">{escape(profile.opponent_team_name)} -- {escape(profile.session_name)}
{'-- ' + escape(profile.format) if profile.format else ''}. Summarizes captured
skill-level variation only -- not shot variance, temperament, or match risk
(docs/opponent_volatility.md). Formula version: {escape(profile.formula_version)}.</p>

<table class="ov-summary"><tbody>
<tr><th>Team Volatility Index (median)</th><td>{_num(profile.team_volatility_index)}</td></tr>
<tr><th>Coverage</th><td>{_pct(profile.coverage)} ({profile.measured_count}/{profile.roster_count} measured)</td></tr>
</tbody></table>

<figure id="opponent-volatility-plot">
<figcaption>Volatility index per measured opponent (0-100 axis; missing values omitted, not zero)</figcaption>
<ul>{"".join(f"<li>{escape(r.player_name)}: {_num(r.volatility_index)}</li>" for r in profile.player_rows) or "<li>No data.</li>"}</ul>
</figure>

<table id="opponent-volatility-table">
<thead><tr><th>Player</th><th>Sample</th><th>Raw Volatility</th><th>Stability</th>
<th>Volatility Index</th><th>Consistency Descriptor</th><th>Trend Slope</th>
<th>Format</th><th>Session</th><th>Source Status</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<p class="ov-assumptions">The index is a monotonic display transform of the
existing last-20-reading skill-level standard deviation -- it has no
validated match-outcome interpretation, cannot be restyled as danger or
favorable, and does not alter Player-vs-Player evidence, the skill-only
heatmap, or Lineup Lab selection. There is no default "riskiest" order.</p>

<style>
.ov-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 18px; }}
.ov-tab th, .ov-tab td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.ov-tab .ov-summary th {{ width: 260px; }}
.ov-assumptions {{ color: #666e7a; font-size: 12.5px; }}
</style>
</section>"""
