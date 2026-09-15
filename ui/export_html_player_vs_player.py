"""Player vs Player HTML export: a standalone, self-contained page listing
every feasible pairing in one scope, with a drill-down detail section per
pairing.

Reuses ``ui/tabs/player_vs_player.py``'s existing single-pair renderer for
each row's detail section rather than a second HTML implementation --
consistent with this project's "renderers do not recompute" rule
(docs/player_vs_player_exports.md), the whole-page shell and the per-pair
fragment can never disagree about one pairing's own numbers.

No external resources. Real values only -- a missing number renders as the
literal text "No data", and UNKNOWN pairings are listed in the summary
table exactly like DIRECT/INDIRECT ones, never hidden or sorted out.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from analytics.player_vs_player_matrix import PlayerVsPlayerExportRow
from ui.tabs.player_vs_player import render as render_pair
from ui.tabs.tonights_match import _script_json

SUMMARY_COLUMNS = (
    ("session_name", "Session"),
    ("format", "Format"),
    ("player_name", "Player"),
    ("player_skill_level", "Player SL"),
    ("opponent_name", "Opponent"),
    ("opponent_skill_level", "Opp SL"),
    ("evidence_label", "Evidence"),
    ("direct_matches", "Direct Matches"),
    ("observed_win_rate", "Observed Win Rate"),
    ("modeled_win_probability", "Modeled Win Prob. (experimental)"),
)


def _pct(value) -> str:
    return "No data" if value is None else f"{value * 100:.0f}%"


def _fmt(row: PlayerVsPlayerExportRow, key: str) -> str:
    if key == "evidence_label":
        return row.evidence_label.value
    if key == "observed_win_rate":
        return _pct(row.observed_win_rate)
    if key == "modeled_win_probability":
        return _pct(row.summary.modeled_win_probability)
    value = getattr(row, key)
    return "No data" if value is None else str(value)


def _row_id(row: PlayerVsPlayerExportRow) -> str:
    return f"pvp-{row.player_id}-{row.opponent_id}"


def render_export(rows: Sequence[PlayerVsPlayerExportRow], title: str = "Player vs Player") -> str:
    """A self-contained HTML page for one scope's whole Player vs Player
    export. An empty ``rows`` renders an honest empty state, never a
    guess."""
    if not rows:
        return (
            f'<!doctype html><html><head><meta charset="utf-8">'
            f"<title>{escape(title)}</title></head><body>"
            f'<section class="pvp-export-empty"><h1>{escape(title)}</h1>'
            "<p>No feasible pairings in this scope.</p></section>"
            "</body></html>"
        )

    scope = rows[0]
    header = "".join(f"<th>{escape(label)}</th>" for _, label in SUMMARY_COLUMNS)
    body_rows = "".join(
        f'<tr class="evidence-{escape(row.evidence_label.value)}">'
        + "".join(f"<td>{escape(_fmt(row, key))}</td>" for key, _ in SUMMARY_COLUMNS)
        + f'<td><a href="#{_row_id(row)}">Details</a></td></tr>'
        for row in rows
    )
    detail_sections = "".join(
        f'<div id="{_row_id(row)}">'
        + render_pair(row.summary, row.player_name, row.opponent_name,
                      title=f"{row.player_name} vs {row.opponent_name}")
        + "</div>"
        for row in rows
    )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row.evidence_label.value] = counts.get(row.evidence_label.value, 0) + 1

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 10px 0; }}
th, td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; white-space: nowrap; }}
th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; }}
tr.evidence-DIRECT {{ background: #e6f6ec; }}
tr.evidence-INDIRECT {{ background: #fff8e1; }}
tr.evidence-UNKNOWN {{ background: #ffffff; }}
.pvp-export-counts {{ color: #444b54; margin: 8px 0 18px; }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
<p class="pvp-export-counts">{escape(scope.session_name)} / {escape(scope.format)} -- {len(rows)}
feasible pairing(s): {counts.get("DIRECT", 0)} DIRECT, {counts.get("INDIRECT", 0)} INDIRECT,
{counts.get("UNKNOWN", 0)} UNKNOWN. Click any column to sort; click "Details" to jump to a pairing's
full comparison below.</p>
<table id="pvp-export-summary"><thead><tr>{header}<th>&nbsp;</th></tr></thead>
<tbody>{body_rows}</tbody></table>
<h2>Pairing details</h2>
{detail_sections}
<script>
var PVP_TABLE = document.getElementById("pvp-export-summary");
var pvpAscending = false;
Array.from(PVP_TABLE.tHead.rows[0].cells).forEach(function (th, index) {{
  th.addEventListener("click", function () {{
    var rows = Array.from(PVP_TABLE.tBodies[0].rows);
    pvpAscending = !pvpAscending;
    rows.sort(function (a, b) {{
      var x = a.cells[index] ? a.cells[index].textContent.trim() : "";
      var y = b.cells[index] ? b.cells[index].textContent.trim() : "";
      if (x === "No data") return 1;
      if (y === "No data") return -1;
      var nx = parseFloat(x.replace(/%/g, "")), ny = parseFloat(y.replace(/%/g, ""));
      if (!isNaN(nx) && !isNaN(ny)) return pvpAscending ? nx - ny : ny - nx;
      return pvpAscending ? x.localeCompare(y) : y.localeCompare(x);
    }});
    rows.forEach(function (row) {{ PVP_TABLE.tBodies[0].appendChild(row); }});
  }});
}});
</script>
</body>
</html>"""
