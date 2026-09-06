"""Lineup Optimizer tab: one legal opponent assignment per team card.

This tab renders ``exports/lineups.json`` rather than querying the database or
recomputing scores.  The JSON is the builder's versioned artifact, so a page a
captain opens always agrees with the file that was produced by the pipeline.
It is self-contained HTML and has no network dependency.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional, Sequence

NO_DATA = "No data"

# Header order is part of the captain-facing contract.
COLUMNS = (
    ("player_name", "Player", False),
    ("opponent_name", "Opponent", False),
    ("matchup_score_raw", "Matchup Score", True),
    ("win_probability", "Win Probability", True),
    ("confidence", "Confidence", True),
    ("risk_factor", "Risk", True),
    ("final_score", "Final Score", True),
    ("lineup_rank", "Rank", True),
    ("rationale", "Rationale", False),
)


def load_rows(
    document: dict[str, Any],
    *,
    team_id: Optional[str] = None,
    opponent_team_id: Optional[str] = None,
    format_: Optional[str] = None,
    session_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Flatten assignment rows while retaining their lineup context."""

    rows: list[dict[str, Any]] = []
    for lineup in document.get("lineups") or []:
        if team_id is not None and str(lineup.get("team_id")) != str(team_id):
            continue
        if (opponent_team_id is not None
                and str(lineup.get("opponent_team_id")) != str(opponent_team_id)):
            continue
        if format_ is not None and lineup.get("format") != format_:
            continue
        if session_name is not None and lineup.get("session_name") != session_name:
            continue
        for assignment in lineup.get("assignments") or []:
            row = dict(assignment)
            row["team_name"] = lineup.get("team_name") or ""
            row["opponent_team_name"] = lineup.get("opponent_team_name") or ""
            row["format"] = lineup.get("format") or ""
            row["session_name"] = lineup.get("session_name") or ""
            row["source_pairing"] = bool(row.get("source_pairing"))
            rows.append(row)
    rows.sort(key=lambda row: (
        row.get("team_name") or "",
        row.get("opponent_team_name") or "",
        row.get("format") or "",
        row.get("session_name") or "",
        row.get("lineup_rank") is None,
        row.get("lineup_rank") or 0,
        (row.get("player_name") or "").casefold(),
    ))
    return rows


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return NO_DATA
    if key == "win_probability":
        return f"{float(value) * 100:.0f}%"
    if key in ("confidence", "risk_factor", "final_score"):
        return f"{float(value):.3f}"
    if key == "matchup_score_raw":
        return escape(str(value))
    return escape(str(value))


def _table(rows: Sequence[dict[str, Any]], title: str) -> str:
    header = "".join(
        f'<th class="{"num" if numeric else ""}">{escape(label)}</th>'
        for _, label, numeric in COLUMNS
    )
    body = "".join(
        '<tr class="{cls}">{cells}</tr>'.format(
            cls="unobserved" if not row.get("source_pairing") else "",
            cells="".join(
                f'<td class="{"num" if numeric else ""}">{_cell(row, key)}</td>'
                for key, _, numeric in COLUMNS
            ),
        )
        for row in rows
    )
    return f"""<h3>{escape(title)}</h3>
<table class="lineup-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"""


def render(document: dict[str, Any], title: str = "Lineup Optimizer") -> str:
    """Render one table per solved team/opponent/format/session group."""

    lineups = document.get("lineups") or []
    if not lineups:
        warnings = document.get("resolution_warnings") or []
        note = "No resolved lineup yet. Run the pipeline after Head-to-Head and Player Trend data are available."
        if warnings:
            note += f" {len(warnings)} data-quality warning(s) are recorded in lineups.json."
        return (
            f'<section class="lineup-tab"><h2>{escape(title)}</h2>'
            f'<p class="lineup-empty">{escape(note)}</p></section>'
        )

    sections: list[str] = []
    for lineup in lineups:
        rows = load_rows(
            {"lineups": [lineup]},
            team_id=str(lineup.get("team_id")),
        )
        heading = (
            f"{lineup.get('team_name') or lineup.get('team_id') or 'Team'} vs "
            f"{lineup.get('opponent_team_name') or lineup.get('opponent_team_id') or 'Opponent'}"
        )
        context = " · ".join(
            value for value in (lineup.get("format"), lineup.get("session_name")) if value
        )
        if context:
            heading += f" · {context}"
        assigned = len(rows)
        total_players = lineup.get("players_considered")
        total_opponents = lineup.get("opponents_considered")
        note = (
            f"{assigned} assignment(s)"
            + (f" from {total_players} player(s)" if total_players is not None else "")
            + (f" and {total_opponents} opponent(s)" if total_opponents is not None else "")
            + ". Scores are computed by the exact one-to-one optimizer."
        )
        if lineup.get("roster_resolution") == "player_name":
            note += " Roster identity used an unambiguous player-name fallback."
        sections.append(
            '<div class="lineup-group">'
            f"{_table(rows, heading)}"
            f'<p class="lineup-note">{escape(note)}</p>'
            "</div>"
        )

    return f"""<section class="lineup-tab">
<h2>{escape(title)}</h2>
<p class="lineup-note">{len(lineups)} solved lineup group(s). Raw matchup scores are shown as stored; No data means the source did not provide a value. Neutral defaults are used only inside the optimizer.
Click a column to sort.</p>
<style>
.lineup-tab table {{ border-collapse: collapse; width: 100%; min-width: 980px; font-size: 13.5px; }}
.lineup-tab th, .lineup-tab td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; vertical-align: top; }}
.lineup-tab th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; white-space: nowrap; }}
.lineup-tab td.num, .lineup-tab th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.lineup-tab td:last-child {{ min-width: 260px; color: #666e7a; font-size: 12.5px; }}
.lineup-tab tr.unobserved {{ background: #fdf3e3; }}
.lineup-tab h3 {{ margin: 14px 0 3px; font-size: 15px; }}
.lineup-note, .lineup-empty {{ color: #666e7a; padding: 4px 0 10px; }}
.lineup-group + .lineup-group {{ border-top: 1px solid #e2e5ea; margin-top: 12px; padding-top: 2px; }}
</style>
{''.join(sections)}
<script>
(function () {{
  document.currentScript.parentElement.querySelectorAll(".lineup-table").forEach(function (table) {{
    var ascending = false;
    table.querySelectorAll("th").forEach(function (th, index) {{
      th.addEventListener("click", function () {{
        var rows = Array.from(table.tBodies[0].rows);
        ascending = !ascending;
        rows.sort(function (a, b) {{
          var x = a.cells[index].textContent.trim();
          var y = b.cells[index].textContent.trim();
          if (x === "{NO_DATA}") return 1;
          if (y === "{NO_DATA}") return -1;
          var nx = parseFloat(x.replace(/[%,+]/g, ""));
          var ny = parseFloat(y.replace(/[%,+]/g, ""));
          if (!isNaN(nx) && !isNaN(ny)) return ascending ? nx - ny : ny - nx;
          return ascending ? x.localeCompare(y) : y.localeCompare(x);
        }});
        rows.forEach(function (row) {{ table.tBodies[0].appendChild(row); }});
      }});
    }});
  }});
}})();
</script>
</section>"""


def build(document: dict[str, Any], title: str = "Lineup Optimizer") -> str:
    """Render a lineup JSON document into one self-contained section."""

    return render(document, title)
