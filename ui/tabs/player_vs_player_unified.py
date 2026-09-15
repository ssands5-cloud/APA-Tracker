"""Unified Player vs Player tab: one top-level tab, two subviews.

Follows the shape docs/player_vs_player_html_structure.md specifies (posted
by the concurrent documentation lane), scoped down to what is realistically
buildable and testable as one static, self-contained HTML fragment in this
pass -- see the module docstring's "Known simplifications" for exactly what
is deferred (full history/back-forward routing, run-id/hash provenance,
gated Recommended Avoid/Target machinery beyond the always-shown "not
validated" text).

- **Pair View** -- one explicit player/opponent comparison, rendered by
  reusing ``ui/tabs/player_vs_player.py::render`` directly (no second
  implementation of that fragment).
- **Matrix View** -- every feasible pairing in the scope, the same summary
  table ``ui/export_html_player_vs_player.py`` already renders, reused here
  rather than duplicated.

Both subviews read from the SAME embedded, escaped JSON document (the
`<script type="application/json" id="pvp-data">` element the design doc
calls for) -- nothing is fetched, queried, or recomputed in the browser.
Clicking a matrix row's "Details" link switches to Pair View and shows
that row's already-rendered detail section; there is no live recomputation
of any evidence label, rate, or probability.

Known simplifications versus docs/player_vs_player_html_structure.md's
full target (disclosed, not silently dropped):

- No persistent URL/fragment routing or back-forward history restoration
  -- subview + selection state lives in page JS only, reset on reload.
  A static, no-server export has nothing to persist that state IN.
- No run ID / capture-time / source-hash provenance banner -- this
  project has no run-manifest concept yet to source one from honestly.
- No keyboard-arrow roving tabindex; the two subview buttons are ordinary,
  independently focusable buttons with `aria-selected`, not a full ARIA
  tablist widget.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from analytics.player_vs_player_matrix import PlayerVsPlayerExportRow
from ui.export_html_player_vs_player import SUMMARY_COLUMNS, _fmt, _row_id
from ui.tabs.player_vs_player import render as render_pair
from ui.tabs.tonights_match import _script_json

RISK_PROFILE_NOTE = (
    "Recommended Avoid / Recommended Target: Not available -- threshold not "
    "validated. Neither flag is inferred from modeled_win_probability, "
    "volatility, or an arbitrary cutoff (docs/player_vs_player_html_structure.md)."
)


def render_unified_tab(
    rows: Sequence[PlayerVsPlayerExportRow],
    our_team_name: str,
    title: str = "Player vs Player",
) -> str:
    """One self-contained ``<section>`` fragment: a Player vs Player tab
    with Pair View / Matrix View subviews. An empty ``rows`` renders an
    honest empty state, never a guess."""
    if not rows:
        return (
            f'<section class="pvp-unified"><h2>{escape(title)}</h2>'
            "<p>No feasible pairings in this scope.</p></section>"
        )

    scope = rows[0]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.evidence_label.value] = counts.get(row.evidence_label.value, 0) + 1

    header = "".join(f"<th>{escape(label)}</th>" for _, label in SUMMARY_COLUMNS)
    matrix_rows_html = "".join(
        f'<tr class="evidence-{escape(row.evidence_label.value)}" data-pair="{_row_id(row)}">'
        + "".join(f"<td>{escape(_fmt(row, key))}</td>" for key, _ in SUMMARY_COLUMNS)
        + f'<td><button type="button" class="pvp-details-btn" data-target="{_row_id(row)}">Details</button></td>'
        "</tr>"
        for row in rows
    )

    pair_sections = "".join(
        f'<div id="{_row_id(row)}" class="pvp-pair-panel" hidden>'
        + render_pair(row.summary, row.player_name, row.opponent_name,
                      title=f"{row.player_name} vs {row.opponent_name}")
        + f'<section class="pvp-risk-profile"><h3>Opponent Risk Profile</h3>'
        + f'<p>{escape(RISK_PROFILE_NOTE)}</p></section>'
        + "</div>"
        for row in rows
    )

    first_pair_id = _row_id(rows[0])
    payload = _script_json({
        "our_team_external_id": scope.our_team_external_id,
        "opponent_team_external_id": scope.opponent_team_external_id,
        "format": scope.format,
        "session_name": scope.session_name,
        "counts": counts,
        "row_ids": [_row_id(row) for row in rows],
    })

    return f"""<section class="pvp-unified" id="player-vs-player-tab">
<h2>{escape(title)}</h2>
<p class="pvp-unified-sub">{escape(our_team_name)} -- {escape(scope.session_name)} /
{escape(scope.format)} -- {len(rows)} feasible pairing(s): {counts.get("DIRECT", 0)} DIRECT,
{counts.get("INDIRECT", 0)} INDIRECT, {counts.get("UNKNOWN", 0)} UNKNOWN.</p>

<div role="tablist" aria-label="Player vs Player subviews" class="pvp-subviews">
  <button type="button" role="tab" id="pvp-matrix-tab" aria-selected="true" aria-controls="pvp-matrix-view">Matrix View</button>
  <button type="button" role="tab" id="pvp-pair-tab" aria-selected="false" aria-controls="pvp-pair-view">Pair View</button>
</div>

<section id="pvp-matrix-view" role="tabpanel" aria-labelledby="pvp-matrix-tab">
<table id="pvp-matrix-table"><thead><tr>{header}<th>&nbsp;</th></tr></thead>
<tbody>{matrix_rows_html}</tbody></table>
</section>

<section id="pvp-pair-view" role="tabpanel" aria-labelledby="pvp-pair-tab" hidden>
{pair_sections}
</section>

<script type="application/json" id="pvp-data">{payload}</script>
<style>
.pvp-unified table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 10px 0; }}
.pvp-unified th, .pvp-unified td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; white-space: nowrap; }}
.pvp-unified tr.evidence-DIRECT {{ background: #e6f6ec; }}
.pvp-unified tr.evidence-INDIRECT {{ background: #fff8e1; }}
.pvp-unified tr.evidence-UNKNOWN {{ background: #ffffff; }}
.pvp-subviews {{ margin: 12px 0; }}
.pvp-subviews button {{ padding: 7px 14px; margin-right: 6px; cursor: pointer; border: 1px solid #d8dce1; background: #f4f6f8; border-radius: 6px; }}
.pvp-subviews button[aria-selected="true"] {{ background: #1F3864; color: #fff; border-color: #1F3864; }}
.pvp-risk-profile {{ margin-top: 14px; padding: 10px; background: #f4f6f8; border-radius: 6px; color: #444b54; font-size: 13px; }}
</style>
<script>
(function () {{
  var matrixTab = document.getElementById("pvp-matrix-tab");
  var pairTab = document.getElementById("pvp-pair-tab");
  var matrixView = document.getElementById("pvp-matrix-view");
  var pairView = document.getElementById("pvp-pair-view");
  var currentPanel = null;

  function showPair(id) {{
    if (currentPanel) currentPanel.hidden = true;
    var panel = document.getElementById(id);
    if (panel) {{ panel.hidden = false; currentPanel = panel; }}
  }}

  function selectSubview(name) {{
    var showMatrix = name === "matrix";
    matrixView.hidden = !showMatrix;
    pairView.hidden = showMatrix;
    matrixTab.setAttribute("aria-selected", String(showMatrix));
    pairTab.setAttribute("aria-selected", String(!showMatrix));
  }}

  matrixTab.addEventListener("click", function () {{ selectSubview("matrix"); }});
  pairTab.addEventListener("click", function () {{ selectSubview("pair"); }});

  document.querySelectorAll(".pvp-details-btn").forEach(function (button) {{
    button.addEventListener("click", function () {{
      showPair(button.getAttribute("data-target"));
      selectSubview("pair");
    }});
  }});

  showPair("{first_pair_id}");
}})();
</script>
</section>"""
