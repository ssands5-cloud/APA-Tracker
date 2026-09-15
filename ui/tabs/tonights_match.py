"""Tonight's Match: the captain-first evidence matrix.

Stage 2 of docs/captain_first_edge_experience.md. Renders one or more
``analytics.pairing_evidence.PairingEvidenceMatrix`` objects (Stage 1's own
output -- this module recomputes nothing) as one self-contained HTML
application: real team/session/format/opponent selectors switch between
precomputed real matrices, and per-player availability checkboxes narrow
the DISPLAYED rows live, in the browser, with no server and no Python after
the file is opened.

Every matrix embedded here was built by
``analytics.pairing_evidence.build_pairing_evidence_matrix`` against a real
scheduled match between the configured team and a real opponent -- there is
no client-side re-classification, so the page can never show an evidence
label the Python classifier did not compute. Availability filtering only
hides/shows already-classified rows and re-tallies the VISIBLE counts; it
never changes a pairing's DIRECT/INDIRECT/UNKNOWN label, matching
docs/captain_first_edge_experience.md's rule that availability narrows the
feasible set for display, not the evidence itself.

UNKNOWN rows are never hidden by default (§7): the "Show all pairings"
checkbox controls only whether pairings the captain has marked unavailable
stay visible for reference, not whether UNKNOWN rows appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Optional, Sequence

from analytics.lineup_lab import LineupLabResult
from analytics.opponent_risk_profile import build_profile as build_risk_profile
from analytics.pairing_evidence import PairingEvidenceMatrix

COLUMNS = (
    ("player_name", "Our Player", False),
    ("player_skill_level", "Our SL", True),
    ("opponent_name", "Opponent", False),
    ("opponent_skill_level", "Opp SL", True),
    ("evidence_label", "Evidence", False),
    ("observed_win_rate", "Observed Win Rate", True),
    ("direct_evidence_count", "Direct Matches", True),
    ("modeled_win_probability", "Modeled Win Prob.", True),
    ("model_source", "Model Source", False),
)


@dataclass(frozen=True)
class MatchScope:
    """One real, selectable (session, opponent, format) combination.

    ``matrix`` is the real computed result, when the canonical rosters on
    both sides allowed one to be built. ``unavailable_reason`` is set
    instead, never both -- a combination this page could not evaluate is
    named honestly, not silently dropped from the selector.

    ``lineup_result``/``lineup_error`` are independent of the matrix split
    above and only meaningful when ``matrix`` is set: Stage 3's Lineup Lab
    (analytics.lineup_lab.solve) can fail on a real matrix that classified
    fine (an oversized roster exceeding the bounded exact search, for
    example) without that failure invalidating the matrix itself. The real
    builder (scripts/build_captain_first_edge.py) always sets exactly one
    of the two whenever it has a matrix; leaving both unset here (the
    default) only ever happens in a test that isn't exercising Stage 3.
    """

    session_name: str
    opponent_team_external_id: str
    opponent_team_name: str
    format: str
    matrix: Optional[PairingEvidenceMatrix]
    unavailable_reason: Optional[str] = None
    lineup_result: Optional[LineupLabResult] = None
    lineup_error: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.matrix is None) == (self.unavailable_reason is None):
            raise ValueError(
                "A match scope must carry exactly one of matrix or unavailable_reason"
            )
        if self.matrix is None and (self.lineup_result is not None or self.lineup_error is not None):
            raise ValueError(
                "A match scope with no matrix cannot carry a lineup result or error"
            )
        if self.lineup_result is not None and self.lineup_error is not None:
            raise ValueError(
                "A match scope cannot carry both a lineup result and a lineup error"
            )


def _scope_key(session_name: str, opponent_team_external_id: str, format: str) -> str:
    return json.dumps([session_name, opponent_team_external_id, format])


def _script_json(value: object) -> str:
    """Serialize JSON without allowing database text to end the script tag.

    The payload is embedded in a classic ``<script>`` element. JSON string
    escaping does not escape ``<`` by default, so a captured player/team name
    containing ``</script>`` could otherwise break out of the data block.
    These replacements preserve the decoded values while making the HTML
    parser treat all database text as script data.
    """
    return (
        json.dumps(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _matrix_payload(matrix: PairingEvidenceMatrix) -> dict:
    """The real, already-classified rows and counts, as plain JSON --
    the only thing the page's JavaScript reads. No recomputation happens
    client-side; this is a serialization of Stage 1's own output."""
    return {
        "our_team_external_id": matrix.our_team_external_id,
        "opponent_team_external_id": matrix.opponent_team_external_id,
        "format": matrix.format,
        "session_name": matrix.session_name,
        "our_roster_available": matrix.our_roster_available,
        "opponent_roster_available": matrix.opponent_roster_available,
        "counts": matrix.counts,
        "pairings": [
            {
                "player_id": p.player_id,
                "player_external_id": p.player_external_id,
                "player_name": p.player_name,
                "player_skill_level": p.player_skill_level,
                "opponent_id": p.opponent_id,
                "opponent_external_id": p.opponent_external_id,
                "opponent_name": p.opponent_name,
                "opponent_skill_level": p.opponent_skill_level,
                "evidence_label": p.evidence_label.value,
                "observed_win_rate": p.observed_win_rate,
                "direct_evidence_count": p.direct_evidence_count,
                "modeled_win_probability": p.modeled_win_probability,
                "model_source": p.model_source,
            }
            for p in matrix.pairings
        ],
    }


def _lineup_payload(scope: MatchScope) -> Optional[dict]:
    """The real Stage 3 result for one scope, as plain JSON -- or an honest
    error, or ``None`` when this scope never attempted one (a test scope,
    or a scope whose matrix itself is unavailable). Computed once at build
    time for the full current roster on both sides; it is NOT recomputed
    when the captain toggles availability above (see the "Approved Best
    Lineup" note rendered with it) -- analytics.lineup_lab.solve's
    assignment depends on exactly who is available, so silently re-filtering
    an already-solved lineup client-side could show an assignment that was
    never actually approved for that narrower roster. Regenerating this
    file with a real availability selection (see docs/captain_first_edge_experience.md
    §16) is the honest way to get an availability-aware recommendation
    today."""
    if scope.lineup_error is not None:
        return {"error": scope.lineup_error}
    if scope.lineup_result is None:
        return None
    result = scope.lineup_result
    return {
        "assignments": [
            {
                "player_id": slot.player_id,
                "player_name": slot.player_name,
                "player_skill_level": slot.player_skill_level,
                "opponent_id": slot.opponent_id,
                "opponent_name": slot.opponent_name,
                "opponent_skill_level": slot.opponent_skill_level,
                "evidence_label": slot.evidence_label.value,
                "observed_win_rate": slot.observed_win_rate,
                "direct_evidence_count": slot.direct_evidence_count,
                "modeled_win_probability": slot.modeled_win_probability,
                "model_source": slot.model_source,
                "lineup_score": slot.lineup_score,
                "lineup_score_source": slot.lineup_score_source,
            }
            for slot in result.assignments
        ],
        "unassigned_players": [
            {"player_id": u.player_id, "player_name": u.player_name}
            for u in result.unassigned_players
        ],
        "unassigned_opponents": [
            {"opponent_id": u.opponent_id, "opponent_name": u.opponent_name}
            for u in result.unassigned_opponents
        ],
        "total_score": result.total_score,
        "skill_total": result.skill_total,
        "is_legal": result.is_legal,
        "blocked_reason": result.blocked_reason,
    }


def _pct_or_no_data(value: Optional[float]) -> str:
    return "No data" if value is None else f"{value * 100:.0f}%"


def _risk_profile_section(scopes: Sequence[MatchScope]) -> str:
    """Captain's Edge Opponent Risk Profile: a purely descriptive,
    whole-schedule ranking across every real opponent this build could
    evaluate -- see analytics/opponent_risk_profile.py. Computed once,
    across every real opponent scope, independent of which single scope
    the Session/Opponent/Format dropdowns above currently show.

    No categorical danger/favorable flag, no threshold on
    modeled_win_probability -- ranked only by the reliability-weighted
    skill-only probability, DIRECT win rate, and real sample size.
    """
    matrices = [
        (scope.opponent_team_external_id, scope.opponent_team_name, scope.matrix)
        for scope in scopes
        if scope.matrix is not None
    ]
    if not matrices:
        return (
            '<section class="tm-risk-profile"><h2>Opponent Risk Profile</h2>'
            "<p>No real opponent scope could be evaluated yet.</p></section>"
        )

    profile = build_risk_profile(matrices)
    rows = "".join(
        "<tr>"
        f"<td>{escape(entry.opponent_team_name)}</td>"
        f"<td class='num'>{entry.total_pairings}</td>"
        f"<td class='num'>{entry.direct_pairing_count}</td>"
        f"<td class='num'>{_pct_or_no_data(entry.direct_win_rate)}</td>"
        f"<td class='num'>{entry.sample_size}</td>"
        f"<td class='num'>{_pct_or_no_data(entry.reliability_weighted_skill_probability)}</td>"
        "</tr>"
        for entry in profile
    )
    return f"""<section class="tm-risk-profile">
<h2>Opponent Risk Profile</h2>
<p class="tm-sub">A purely descriptive ranking, real opponents only -- sorted by
reliability-weighted skill-only probability, toughest first. No categorical
danger/favorable flag and no threshold on modeled_win_probability are used;
<b>Recommended Avoid</b> and <b>Recommended Target</b> are Not available -- threshold
not validated (see docs/player_vs_player_html_structure.md).</p>
<table class="tm-risk-table">
<thead><tr><th>Opponent</th><th class="num">Feasible Pairings</th>
<th class="num">DIRECT Pairings</th><th class="num">DIRECT Win Rate</th>
<th class="num">Sample Size</th><th class="num">Reliability-Weighted Skill Prob.</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</section>"""


def render(
    scopes: Sequence[MatchScope],
    our_team_name: str,
    title: str = "Tonight's Match",
    *,
    our_team_external_id: Optional[str] = None,
    page_unavailable_reason: Optional[str] = None,
) -> str:
    """A self-contained HTML page. No external resources, no server.

    ``scopes`` is every real (session, opponent, format) combination this
    build could attempt -- one real scheduled match between the configured
    team and a real opponent is the only thing that puts a combination in
    this list. An empty list renders an honest empty state, never a guess.
    """
    if page_unavailable_reason is not None:
        return (
            f"<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{escape(title)}</title></head><body>"
            f'<section class="tm-unavailable"><h1>{escape(title)}</h1>'
            f"<p>This build could not read the configured database: "
            f"{escape(page_unavailable_reason)}</p>"
            "<p>Regenerate the database from the APA API, then rebuild this file.</p>"
            "</section></body></html>"
        )
    if not scopes:
        return (
            f"<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{escape(title)}</title></head><body>"
            f'<section class="tm-empty"><h1>{escape(title)}</h1>'
            "<p>No real scheduled match was found for the configured team. "
            "Run the pipeline, then scripts/build_captain_first_edge.py.</p>"
            "</section></body></html>"
        )

    sessions = sorted({s.session_name for s in scopes})
    payload: dict[str, dict] = {}
    options: list[dict] = []
    for scope in scopes:
        key = _scope_key(scope.session_name, scope.opponent_team_external_id, scope.format)
        options.append({
            "key": key,
            "session_name": scope.session_name,
            "opponent_team_external_id": scope.opponent_team_external_id,
            "opponent_team_name": scope.opponent_team_name,
            "format": scope.format,
            "available": scope.matrix is not None,
            "unavailable_reason": scope.unavailable_reason,
        })
        if scope.matrix is not None:
            payload[key] = _matrix_payload(scope.matrix)
            payload[key]["lineup"] = _lineup_payload(scope)

    session_options = "".join(
        f'<option value="{escape(s)}">{escape(s)}</option>' for s in sessions
    )
    team_value = our_team_external_id or our_team_name
    risk_profile_html = _risk_profile_section(scopes)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1c1f24; }}
.tm-risk-profile {{ margin: 22px 0; padding: 14px; background: #f4f6f8; border-radius: 8px; }}
.tm-risk-table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
.tm-risk-table th, .tm-risk-table td {{ padding: 6px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; }}
.tm-risk-table td.num, .tm-risk-table th.num {{ text-align: right; }}
h1 {{ margin-bottom: 4px; }}
.tm-sub {{ color: #666e7a; margin-top: 0; }}
.tm-controls {{ display: flex; gap: 18px; flex-wrap: wrap; align-items: flex-end;
  margin: 18px 0; padding: 14px; background: #f4f6f8; border-radius: 8px; }}
.tm-controls label {{ display: block; font-size: 11.5px; text-transform: uppercase;
  letter-spacing: .04em; color: #666e7a; margin-bottom: 4px; }}
.tm-controls select {{ font-size: 14px; padding: 5px 8px; }}
.tm-counts {{ margin: 10px 0; font-size: 14px; }}
.tm-counts b {{ font-variant-numeric: tabular-nums; }}
.tm-unavailable {{ color: #9a3b3b; padding: 14px; background: #fdecec; border-radius: 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; margin-top: 10px; }}
th, td {{ padding: 7px 9px; border-bottom: 1px solid #e2e5ea; text-align: left; white-space: nowrap; }}
th {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: #666e7a; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr.evidence-DIRECT {{ background: #e6f6ec; }}
tr.evidence-INDIRECT {{ background: #fff8e1; }}
tr.evidence-UNKNOWN {{ background: #ffffff; }}
tr.tm-hidden {{ display: none; }}
.tm-avail {{ margin: 14px 0; }}
.tm-avail summary {{ cursor: pointer; font-size: 13px; color: #444b54; }}
.tm-avail label {{ display: inline-block; margin: 4px 10px 4px 0; font-size: 13px; }}
.tm-showall label {{ font-size: 13px; margin-left: 6px; }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
<p class="tm-sub">{escape(our_team_name)} -- every real pairing evidence label comes from
analytics.pairing_evidence; nothing on this page is recomputed in the browser.</p>

<div class="tm-controls">
  <div>
    <label>Team</label>
    <select id="tm-team" aria-label="Configured team">
      <option value="{escape(team_value)}">{escape(our_team_name)}</option>
    </select>
  </div>
  <div>
    <label>Session</label>
    <select id="tm-session"><option value="">Select session&hellip;</option>{session_options}</select>
  </div>
  <div>
    <label>Opponent</label>
    <select id="tm-opponent"><option value="">Select opponent&hellip;</option></select>
  </div>
  <div>
    <label>Format</label>
    <select id="tm-format"><option value="">Select format&hellip;</option></select>
  </div>
  <div class="tm-showall">
    <input type="checkbox" id="tm-showall">
    <label for="tm-showall">Show pairings marked unavailable</label>
  </div>
</div>

{risk_profile_html}

<div id="tm-body"><p>Select an opponent and format to see tonight's evidence matrix.</p></div>

<script>
var TM_OPTIONS = {_script_json(options)};
var TM_PAYLOAD = {_script_json(payload)};
var TM_COLUMNS = {_script_json([[k, l, n] for k, l, n in COLUMNS])};
var tmUnavailable = {{our: {{}}, opp: {{}}}};

function tmEsc(value) {{
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}}

function tmFmt(row, key) {{
  var value = row[key];
  if (value === null || value === undefined) return "No data";
  if (key === "observed_win_rate" || key === "modeled_win_probability") {{
    return Math.round(value * 100) + "%";
  }}
  return String(value);
}}

function tmPopulate(select, values, current) {{
  select.innerHTML = "";
  values.forEach(function (v) {{
    var opt = document.createElement("option");
    opt.value = v.value;
    opt.textContent = v.label;
    if (v.value === current) opt.selected = true;
    select.appendChild(opt);
  }});
}}

function tmRefreshOpponents() {{
  var session = document.getElementById("tm-session").value;
  var seen = {{}};
  var values = [{{value: "", label: "Select opponent\\u2026"}}];
  TM_OPTIONS.filter(function (o) {{ return o.session_name === session; }})
    .forEach(function (o) {{
      if (seen[o.opponent_team_external_id]) return;
      seen[o.opponent_team_external_id] = true;
      values.push({{value: o.opponent_team_external_id, label: o.opponent_team_name}});
    }});
  tmPopulate(document.getElementById("tm-opponent"), values, "");
  tmRefreshFormats();
}}

function tmRefreshFormats() {{
  var session = document.getElementById("tm-session").value;
  var opponent = document.getElementById("tm-opponent").value;
  var values = [{{value: "", label: "Select format\\u2026"}}];
  TM_OPTIONS.filter(function (o) {{
    return o.session_name === session && o.opponent_team_external_id === opponent;
  }}).forEach(function (o) {{ values.push({{value: o.format, label: o.format}}); }});
  tmPopulate(document.getElementById("tm-format"), values, "");
  tmRender();
}}

function tmCurrentOption() {{
  var session = document.getElementById("tm-session").value;
  var opponent = document.getElementById("tm-opponent").value;
  var format = document.getElementById("tm-format").value;
  if (!opponent || !format) return null;
  return TM_OPTIONS.filter(function (o) {{
    return o.session_name === session && o.opponent_team_external_id === opponent && o.format === format;
  }})[0] || null;
}}

function tmAvailabilityControls(rows) {{
  var ours = {{}}, theirs = {{}};
  rows.forEach(function (r) {{
    ours[r.player_id] = r.player_name;
    theirs[r.opponent_id] = r.opponent_name;
  }});
  function block(label, ids, side) {{
    if (Object.keys(ids).length === 0) return "";
    var html = '<details class="tm-avail" open><summary>' + label + ' availability</summary>';
    Object.keys(ids).forEach(function (id) {{
      var checked = tmUnavailable[side][id] ? "" : "checked";
      html += '<label><input type="checkbox" data-side="' + tmEsc(side) + '" data-id="' + tmEsc(id) +
        '" ' + checked + ' onchange="tmToggleAvailable(this)"> ' + tmEsc(ids[id]) + '</label>';
    }});
    return html + '</details>';
  }}
  return block("Our", ours, "our") + block("Opponent", theirs, "opp");
}}

function tmToggleAvailable(el) {{
  var side = el.getAttribute("data-side");
  var id = el.getAttribute("data-id");
  tmUnavailable[side][id] = !el.checked;
  tmApplyFilters();
}}

function tmApplyFilters() {{
  var showAll = document.getElementById("tm-showall").checked;
  var rows = document.querySelectorAll("#tm-table tbody tr");
  var counts = {{DIRECT: 0, INDIRECT: 0, UNKNOWN: 0}};
  rows.forEach(function (tr) {{
    var pid = tr.getAttribute("data-player-id");
    var oid = tr.getAttribute("data-opponent-id");
    var hidden = (!!tmUnavailable.our[pid] || !!tmUnavailable.opp[oid]) && !showAll;
    tr.classList.toggle("tm-hidden", hidden);
    if (!hidden) counts[tr.getAttribute("data-label")]++;
  }});
  var total = counts.DIRECT + counts.INDIRECT + counts.UNKNOWN;
  var countTarget = document.getElementById("tm-shown-counts");
  if (countTarget) {{
    countTarget.textContent =
      "Shown: " + total + " pairing(s) -- " + counts.DIRECT + " DIRECT, " +
      counts.INDIRECT + " INDIRECT, " + counts.UNKNOWN + " UNKNOWN.";
  }}
}}

function tmRosterWarnings(data) {{
  var warnings = [];
  if (!data.our_roster_available) {{
    warnings.push("Our canonical current roster is unavailable for this team and session.");
  }}
  if (!data.opponent_roster_available) {{
    warnings.push("The opponent canonical current roster is unavailable for this team and session.");
  }}
  if (!warnings.length) return "";
  return '<div class="tm-unavailable">' + warnings.map(function (message) {{
    return '<p>' + tmEsc(message) + '</p>';
  }}).join("") + '</div>';
}}

function tmLineupSlotRow(slot) {{
  return '<tr class="evidence-' + tmEsc(slot.evidence_label) + '">' +
    '<td>' + tmEsc(slot.player_name) + '</td>' +
    '<td class="num">' + tmEsc(slot.player_skill_level === null ? "No data" : slot.player_skill_level) + '</td>' +
    '<td>' + tmEsc(slot.opponent_name) + '</td>' +
    '<td class="num">' + tmEsc(slot.opponent_skill_level === null ? "No data" : slot.opponent_skill_level) + '</td>' +
    '<td>' + tmEsc(slot.evidence_label) + '</td>' +
    '<td class="num">' + tmEsc(Math.round(slot.lineup_score * 100) + "%") + '</td>' +
    '<td class="num">' + tmEsc(slot.observed_win_rate === null ? "No data" : Math.round(slot.observed_win_rate * 100) + "%") + '</td>' +
    '</tr>';
}}

function tmRenderLineup(lineup) {{
  var note = '<p class="tm-sub">Approved Best Lineup -- computed once at build time for the ' +
    'full current roster on both sides. It does NOT update when you toggle availability above; ' +
    'regenerate this file with scripts/build_captain_first_edge.py after setting tonight\\'s real ' +
    'availability to get a recommendation for that narrower roster.</p>';
  if (!lineup) {{
    return '<h2>Approved Best Lineup</h2>' + note + '<p>Not computed for this scope.</p>';
  }}
  if (lineup.error) {{
    return '<h2>Approved Best Lineup</h2>' + note +
      '<p class="tm-unavailable">This lineup could not be computed: ' + tmEsc(lineup.error) + '</p>';
  }}
  var header = ['Our Player', 'Our SL', 'Opponent', 'Opp SL', 'Evidence', 'Lineup Score', 'Observed Win Rate']
    .map(function (label) {{ return '<th>' + tmEsc(label) + '</th>'; }}).join("");
  var rows = lineup.assignments.map(tmLineupSlotRow).join("");
  var legality = lineup.is_legal === true ? "Legal (23-Rule)" :
    lineup.is_legal === false ? "ILLEGAL (23-Rule)" : "Not evaluated";
  var summary = '<p class="tm-counts">' +
    (lineup.total_score !== null ? '<b>' + lineup.assignments.length + '</b> of 5 positions filled, total lineup score <b>' +
      lineup.total_score.toFixed(2) + '</b>, skill total <b>' +
      (lineup.skill_total === null ? "n/a" : lineup.skill_total) + '</b> -- <b>' + legality + '</b>.'
      : 'No scoreable pairing exists for this matchup.') +
    '</p>';
  var blocked = lineup.blocked_reason
    ? '<p class="tm-unavailable">' + tmEsc(lineup.blocked_reason) + '</p>' : '';
  var unassigned = '';
  if (lineup.unassigned_players.length) {{
    unassigned += '<p><b>Unassigned players:</b> ' +
      lineup.unassigned_players.map(function (u) {{ return tmEsc(u.player_name); }}).join(", ") + '</p>';
  }}
  if (lineup.unassigned_opponents.length) {{
    unassigned += '<p><b>Unassigned opponents:</b> ' +
      lineup.unassigned_opponents.map(function (u) {{ return tmEsc(u.opponent_name); }}).join(", ") + '</p>';
  }}
  var table = rows
    ? '<table><thead><tr>' + header + '</tr></thead><tbody>' + rows + '</tbody></table>'
    : '';
  return '<h2>Approved Best Lineup</h2>' + note + summary + blocked + table + unassigned;
}}

function tmRender() {{
  var body = document.getElementById("tm-body");
  var option = tmCurrentOption();
  if (!option) {{
    body.innerHTML = "<p>Select an opponent and format to see tonight's evidence matrix.</p>";
    return;
  }}
  if (!option.available) {{
    body.innerHTML = '<p class="tm-unavailable">This matchup could not be evaluated: ' +
      tmEsc(option.unavailable_reason) + '</p>';
    return;
  }}
  var data = TM_PAYLOAD[option.key];
  tmUnavailable = {{our: {{}}, opp: {{}}}};
  var header = TM_COLUMNS.map(function (c) {{
    return '<th class="' + (c[2] ? "num" : "") + '">' + tmEsc(c[1]) + '</th>';
  }}).join("");
  var body_rows = data.pairings.map(function (r) {{
    var cells = TM_COLUMNS.map(function (c) {{
      return '<td class="' + (c[2] ? "num" : "") + '">' + tmEsc(tmFmt(r, c[0])) + '</td>';
    }}).join("");
    return '<tr class="evidence-' + tmEsc(r.evidence_label) + '" data-player-id="' + tmEsc(r.player_id) +
      '" data-opponent-id="' + tmEsc(r.opponent_id) + '" data-label="' + tmEsc(r.evidence_label) + '">' +
      cells + '</tr>';
  }}).join("");
  var c = data.counts;
  body.innerHTML =
    tmRosterWarnings(data) +
    '<p class="tm-counts">Full matrix: <b>' + c.total_feasible_pairings + '</b> feasible pairing(s) -- ' +
    '<b>' + c.DIRECT + '</b> DIRECT, <b>' + c.INDIRECT + '</b> INDIRECT, <b>' + c.UNKNOWN + '</b> UNKNOWN.</p>' +
    '<p id="tm-shown-counts" class="tm-counts"></p>' +
    tmAvailabilityControls(data.pairings) +
    '<table id="tm-table"><thead><tr>' + header + '</tr></thead><tbody>' + body_rows + '</tbody></table>' +
    tmRenderLineup(data.lineup);
  tmApplyFilters();
}}

document.getElementById("tm-session").addEventListener("change", tmRefreshOpponents);
document.getElementById("tm-opponent").addEventListener("change", tmRefreshFormats);
document.getElementById("tm-format").addEventListener("change", tmRender);
document.getElementById("tm-showall").addEventListener("change", tmApplyFilters);
tmRefreshOpponents();
</script>
</body>
</html>"""
