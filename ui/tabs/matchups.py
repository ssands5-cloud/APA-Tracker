"""Head-to-Head tab: every opponent, sortable, with recommendations marked.

Renders from ``player_h2h_advantage`` -- the Head-to-Head Advantage Engine's
output. Like every other view in this project it is a REPORTER: it displays
what ``analytics.head_to_head`` computed and never recalculates a score, so
the tab, the workbook and the database cannot disagree.

Output is a self-contained HTML fragment with no external resources, so it
embeds in the demo or opens on its own from a file:// URL.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from database.models import Player, PlayerH2HAdvantage

# A pairing is "recommended" when the engine both scores it well AND is
# reasonably sure. Score alone would promote a 1-0 fluke; probability alone
# would promote a skill-level mismatch the player has actually been losing.
RECOMMEND_SCORE = 60
RECOMMEND_PROBABILITY = 0.60
# Below this the pairing is flagged as one to avoid, on the same two-sided
# reasoning.
AVOID_SCORE = 40
AVOID_PROBABILITY = 0.40

COLUMNS = (
    ("opponent_name", "Opponent", False),
    ("total_matches", "Games", True),
    ("record", "W-L", False),
    ("sl_delta", "SL Δ", True),
    ("trend_modifier", "Trend", True),
    ("matchup_score", "Score", True),
    ("win_probability", "Win %", True),
    ("expected_points", "Exp Pts", True),
    ("expected_balls", "Exp Balls", True),
    ("format", "Format", False),
)


def classify(row: dict[str, Any]) -> str:
    """"recommended" / "avoid" / "neutral" for one pairing.

    Needs both signals to agree. A pairing with no probability at all (no
    games, no skill levels) is neutral -- absence of evidence is not a
    recommendation either way.
    """
    score = row.get("matchup_score")
    probability = row.get("win_probability")
    if score is None or probability is None:
        return "neutral"
    if score >= RECOMMEND_SCORE and probability >= RECOMMEND_PROBABILITY:
        return "recommended"
    if score <= AVOID_SCORE and probability <= AVOID_PROBABILITY:
        return "avoid"
    return "neutral"


def load_rows(db: Session, player_external_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Pairings as plain dicts, opponent names resolved, best score first."""
    opponent = db.query(Player).subquery()
    query = (
        db.query(PlayerH2HAdvantage, Player)
        .join(Player, Player.id == PlayerH2HAdvantage.opponent_id)
    )
    rows = []
    for advantage, opp in query.all():
        player = advantage.player
        if player_external_id and (player is None or player.external_id != player_external_id):
            continue
        rows.append({
            "player_name": player.name if player else "",
            "player_id": player.external_id if player else "",
            "opponent_name": opp.name,
            "opponent_id": opp.external_id,
            "total_matches": advantage.total_matches,
            "wins": advantage.wins,
            "losses": advantage.losses,
            "record": f"{advantage.wins or 0}-{advantage.losses or 0}",
            "sl_delta": advantage.sl_delta,
            "trend_modifier": advantage.trend_modifier,
            "matchup_score": advantage.matchup_score,
            "win_probability": advantage.win_probability,
            "expected_points": advantage.expected_points,
            "expected_balls": advantage.expected_balls,
            "format": advantage.format,
            "session_name": advantage.session_name,
        })
    rows.sort(key=lambda r: (r["matchup_score"] is None, -(r["matchup_score"] or 0)))
    for row in rows:
        row["classification"] = classify(row)
    return rows


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        # An em dash, never 0: "no data" and "zero" are different facts, and
        # a 0.0 win probability would read as a prediction.
        return "—"
    if key == "win_probability":
        return f"{value * 100:.0f}%"
    if key == "trend_modifier":
        return f"{value:+d}" if value else "0"
    if key in ("sl_delta", "expected_points", "expected_balls"):
        return f"{value:+.2f}" if key == "sl_delta" else f"{value:.2f}"
    return escape(str(value))


def render(rows: Sequence[dict[str, Any]], title: str = "Head-to-Head") -> str:
    """A self-contained, sortable HTML fragment. No external resources."""
    if not rows:
        return (
            f'<section class="h2h-tab"><h2>{escape(title)}</h2>'
            '<p class="h2h-empty">No head-to-head pairings yet. '
            "Run the pipeline, then scripts/build_head_to_head.py.</p></section>"
        )

    header = "".join(
        f'<th data-key="{key}" class="{"num" if numeric else ""}">{escape(label)}</th>'
        for key, label, numeric in COLUMNS
    )
    body = "".join(
        '<tr class="{cls}">{cells}</tr>'.format(
            cls=row["classification"],
            cells="".join(
                f'<td class="{"num" if numeric else ""}">{_cell(row, key)}</td>'
                for key, _, numeric in COLUMNS
            ),
        )
        for row in rows
    )

    recommended = sum(1 for r in rows if r["classification"] == "recommended")
    avoid = sum(1 for r in rows if r["classification"] == "avoid")

    return f"""<section class="h2h-tab">
<h2>{escape(title)}</h2>
<p class="h2h-note">{len(rows)} pairing(s) · {recommended} recommended · {avoid} to avoid.
Click any column to sort. Scores come from the Head-to-Head Advantage Engine, not from this page.</p>
<style>
.h2h-tab table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
.h2h-tab th, .h2h-tab td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; white-space: nowrap; }}
.h2h-tab th {{ cursor: pointer; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; }}
.h2h-tab td.num, .h2h-tab th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.h2h-tab tr.recommended {{ background: #e6f6ec; }}
.h2h-tab tr.avoid {{ background: #fdecec; }}
.h2h-empty {{ color: #666e7a; padding: 18px 0; }}
</style>
<table class="h2h-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>
<script>
(function () {{
  var table = document.currentScript.previousElementSibling;
  var ascending = false;
  table.querySelectorAll("th").forEach(function (th, index) {{
    th.addEventListener("click", function () {{
      var rows = Array.from(table.tBodies[0].rows);
      ascending = !ascending;
      rows.sort(function (a, b) {{
        var x = a.cells[index].textContent.trim();
        var y = b.cells[index].textContent.trim();
        // "—" is missing data and always sorts last, never as zero.
        if (x === "\\u2014") return 1;
        if (y === "\\u2014") return -1;
        var nx = parseFloat(x.replace(/[%+]/g, ""));
        var ny = parseFloat(y.replace(/[%+]/g, ""));
        if (!isNaN(nx) && !isNaN(ny)) return ascending ? nx - ny : ny - nx;
        return ascending ? x.localeCompare(y) : y.localeCompare(x);
      }});
      rows.forEach(function (row) {{ table.tBodies[0].appendChild(row); }});
    }});
  }});
}})();
</script>
</section>"""


def build(db: Session, player_external_id: Optional[str] = None,
          title: str = "Head-to-Head") -> str:
    """Query and render in one call."""
    return render(load_rows(db, player_external_id), title)
