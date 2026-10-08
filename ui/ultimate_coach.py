"""Render the standalone offline Ultimate Coach Scout & Compare cockpit."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from analytics.ultimate_coach_match_day import (
    DEFAULT_MATCH_DAY_TIMEZONE,
    FORMAT_FILTER_ALL,
    FORMAT_FILTER_ALL_LABEL,
    FORMAT_FILTER_EIGHT_NINE,
    FORMAT_FILTER_EIGHT_NINE_LABEL,
    build_match_day_section,
    viewer_current_teams,
    viewer_player,
)
from analytics.ultimate_coach_excel_payload import build_team_rosters
from analytics.ultimate_coach_matchup_evidence import player_ref
from analytics.ultimate_coach_war_room import (
    COACH_TAGS,
    MATCH_NIGHT_GUIDE,
    ONBOARDING_LIMITS,
    ONBOARDING_WHAT,
    build_local_date,
    build_version,
    default_matchup,
    freshness,
    worked_example,
)

# The Captain's War Room script (matrix, best sends, risks, Lineup Lab, scouting
# cards, meetings) lives in its own file so it is plain JavaScript, not an
# f-string; it is embedded inside the page's single script at render time.
_WAR_ROOM_JS = Path(__file__).with_name("ultimate_coach_war_room.js").read_text(encoding="utf-8")
_WAR_ROOM_CSS = """
.cat-G { background:#CFE8D4; } .cat-R { background:#F4CCCC; } .cat-E,.cat-I { background:#FFF0B3; } .cat-X { background:#E3E3E3; color:#555; }
.cat-dot { display:inline-block; width:11px; height:11px; border-radius:50%; margin:0 5px 0 8px; vertical-align:-1px; border:1px solid rgba(0,0,0,.25); }
.legend { font-size:12.5px; color:var(--muted); line-height:1.9; }
.matrix th,.matrix td { padding:3px; text-align:center; vertical-align:middle; }
.matrix tbody th { text-align:left; min-width:140px; }
.matrix thead th { min-width:96px; font-size:11px; text-transform:none; letter-spacing:0; }
.matrix th a { color:var(--felt-deep); }
.mcell { width:100%; min-height:44px; border:1px solid rgba(0,0,0,.12); border-radius:6px; font-size:12.5px; font-weight:700; color:#1d2b22; padding:6px 4px; }
.mcell:hover,.mcell:focus-visible { outline:3px solid #2b5d8f; background-image:none; }
.mcell.cat-G:hover,.mcell.cat-G:focus-visible { background:#CFE8D4; } .mcell.cat-R:hover { background:#F4CCCC; } .mcell.cat-E:hover,.mcell.cat-I:hover { background:#FFF0B3; } .mcell.cat-X:hover { background:#E3E3E3; }
.mcell.on { outline:3px solid var(--ink); }
tr.out td,tr.out th,.mcell.out,th.out,.scout.out { opacity:.5; }
.send { display:inline-block; margin:2px 0; }
.send-table td:first-child { white-space:nowrap; font-weight:600; }
.risk-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
.risk-grid h3 { margin:0 0 2px; }
.wr-list { margin:6px 0 0; padding-left:18px; font-size:13.5px; }
.pair { margin-top:14px; border:1px solid var(--line); border-left:6px solid #999; border-radius:10px; padding:12px 14px; }
.cat-border-G { border-left-color:#5aa86b; } .cat-border-R { border-left-color:#c0504d; } .cat-border-E,.cat-border-I { border-left-color:#d9b44a; }
.pair h4 { margin:10px 0 4px; font-size:13px; color:var(--felt-deep); }
select.plan { width:auto; margin:0; padding:5px 8px; font-size:13.5px; background:#FFF4CC; }
textarea.plan { width:100%; font:inherit; font-size:13px; padding:6px; border:1px solid var(--line-strong); border-radius:6px; background:#FFF4CC; }
input#ll-cap { width:160px; display:block; margin-top:6px; padding:8px; font-size:14px; border:1px solid var(--line-strong); border-radius:8px; background:#FFF4CC; }
label.inline { text-transform:none; font-weight:600; letter-spacing:0; display:inline; }
.cap-label { margin-top:10px; }
button.secondary { background:#fff; color:var(--felt-deep); border-color:#bcd5c4; }
button.secondary:hover { background:var(--felt-soft); }
.print-only { display:none; }
.scout-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
.scout { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.scout-head { background:var(--rail); color:#fff; font-weight:800; padding:8px 12px; }
.scout dl { display:grid; grid-template-columns:max-content minmax(0,1fr); gap:3px 10px; margin:0; padding:10px 12px; font-size:13px; }
.scout dt { color:var(--muted); } .scout dd { margin:0; overflow-wrap:anywhere; }
.scout dd select, .scout dd textarea { max-width:100%; box-sizing:border-box; }
@media (max-width:480px) { .scout dl { grid-template-columns:minmax(0,1fr); gap:0 10px; } .scout dt { font-size:11px; text-transform:uppercase; letter-spacing:.3px; margin-top:5px; } }
.md-date-list { margin-top:10px; }
.matrix th .id-line { display:block; text-transform:none; letter-spacing:0; font-weight:400; }
.tonight { border-top:5px solid var(--brass); }
.tonight:empty { display:none; }
.tonight h2 { margin:0 0 4px; font-size:19px; }
.tonight .when { font-weight:800; font-size:16px; }
.tonight .vs { font-size:15px; margin:2px 0 8px; }
.tonight-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
.tonight-grid > div { background:#f7f5ef; border:1px solid #ece6d8; border-radius:9px; padding:8px 10px; font-size:13px; }
.tonight-grid b { display:block; font-size:11px; text-transform:uppercase; letter-spacing:.4px; color:var(--muted); margin-bottom:3px; }
.tonight-links { display:flex; gap:12px; flex-wrap:wrap; margin-top:8px; font-weight:700; font-size:13.5px; }
.tonight-links a { color:var(--felt-deep); }
@media print { #tonight,#start-here { display:none !important; } }
.demo-flag { background:#fff3cd; color:#7a1f1f; border:2px dashed #b45309; font-weight:800; text-align:center;
  padding:6px 10px; margin:8px 0; border-radius:8px; font-size:14px; }
@media print { .demo-flag { display:block !important; -webkit-print-color-adjust:exact; print-color-adjust:exact; } }
.mn-banner { background:#b8862b; color:#1b1406; font-weight:700; font-size:12.5px; padding:6px 14px; text-align:center; }
body.match-night header.hero { padding:10px 14px 8px; }
body.match-night header.hero p,body.match-night header.hero .ball { display:none; }
body.match-night header h1 { font-size:17px; }
body.match-night .freshness { margin-top:6px; font-size:11px; }
body.match-night .freshness span:nth-child(n+3) { display:none; }
@media (max-width:600px) {
  /* Phone match night: the banner and the date line already say "tonight" -- spend the first screen on decisions. */
  body.match-night main { padding-top:8px; }
  body.match-night #tonight { padding:10px 12px; }
  body.match-night #tonight > h2 { display:none; }
  body.match-night .demo-flag { padding:3px 8px; margin:0 0 6px; font-size:13px; }
  body.match-night .freshness span { padding:2px 8px; }
  body.match-night nav.sections { margin-top:6px; }
}
.tonight-grid.decide { margin-bottom:10px; }
.next-send { background:#fffdf6; border:2px solid #c9a24a; border-radius:10px; padding:6px 10px; margin:4px 0 8px; }
.next-send h3 { margin:0 0 2px; font-size:16px; text-transform:uppercase; letter-spacing:.4px; color:#5d4413; }
.ns-ask { align-self:center; font-size:12px; color:var(--muted); }
@media (max-width:600px) { .tonight-grid.decide { gap:6px; } .tonight-grid.decide > div { padding:6px 9px; }
  /* Phones: Next Send already answers the open opponent, so threats and risks come before the per-opponent overview. */
  .decide-threats { order:1; } .decide-risks { order:2; } .decide-sends { order:3; } }
.ns-chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:4px; align-items:center; }
.ns-chip { min-height:40px; padding:6px 10px; border-radius:20px; border:1px solid #c9b88f; background:#fff; color:#3b2f17; font-size:13px; }
.ns-chip.on { background:#5d4413; color:#fff; border-color:#5d4413; font-weight:700; }
.ns-head { margin:2px 0; font-size:15px; }
.ns-list { list-style:none; margin:0; padding:0; font-size:13px; }
.ns-list li { padding:3px 6px; border-left:4px solid transparent; margin:2px 0; }
.ns-m { font-size:16px; }
.ns-list li.ns-medal { display:flex; align-items:center; gap:6px; } .ns-why { flex:1; }
.ns-save { color:#7a4b00; font-weight:700; }
.ns-more summary { cursor:pointer; font-size:13px; padding:3px 6px; background:#fdecec; border-left:4px solid #b42318; border-radius:4px; }
.ns-avoid { background:#fdecec; border-left-color:#b42318 !important; }
.ns-unordered { background:#fff8db; }
.ns-unknown { color:var(--muted); }
.ns-send { margin-left:4px; min-height:28px; padding:2px 8px; font-size:12px; line-height:1.2; vertical-align:baseline; }
.ns-coach { margin:6px 0 0; font-size:13px; background:#eef4ff; padding:4px 6px; border-radius:6px; }
.quick-read { margin:6px 8px; padding:5px 7px; background:#fff8e8; border-left:4px solid #c9a24a; font-size:13px; }
.quick-read b { text-transform:uppercase; font-size:11px; letter-spacing:.4px; color:#5d4413; margin-right:4px; }
.mv-toggle { display:inline-flex; border:1px solid #c9b88f; border-radius:999px; overflow:hidden; }
.mv-toggle .mv { border:0; border-radius:0; background:#fff; color:#3b2f17; min-height:36px; padding:4px 12px; font-size:13px; }
.mv-toggle .mv.on { background:#5d4413; color:#fff; font-weight:700; }
.coach-op { display:block; font-style:normal; font-size:12px; color:#2f4a7a; }
.ns-foot { margin:-4px 0 8px; font-size:11px; }
@media print { .ns-chips, .ns-send, .mv-toggle { display:none; } }
.tonight-grid.decide > div { background:#fff8e8; border-color:#e7d4a7; }
.tonight-grid.decide b { color:#5d4413; }
.tonight-grid.detail > div { font-size:12px; }
.start-here summary { cursor:pointer; font-size:15px; color:var(--felt-deep); }
.start-here[open] summary { margin-bottom:10px; }
.sh-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
.start-here ul,.start-here ol { margin:4px 0 0; padding-left:20px; font-size:13.5px; }
.start-here h3 { margin:6px 0 2px; }
.coach-summary { font-weight:600; color:#5d4413; margin-top:4px; }
.coach-summary:empty { display:none; }
.tonight-grid span { display:block; }
@media (max-width:760px) {
  header.hero p { display:none; }
  header.hero .ball { width:32px; height:32px; }
  nav.sections { flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; margin-top:8px; }
  nav.sections a { white-space:nowrap; padding:5px 10px; font-size:12px; }
  .freshness { gap:4px; margin-top:8px; font-size:11px; }
  .freshness span { padding:2px 7px; }
}
@media print {
  select.plan,textarea.plan,input#ll-cap,label.inline input,#ll-clear { display:none !important; }
  .print-only { display:inline; }
  .cat-G,.cat-R,.cat-E,.cat-I,.cat-X,.cat-dot,.scout-head { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  body.print-matchup #wr-matrix { break-before:page; }
  body.print-matchup .mcell { min-height:0; padding:2px; font-size:9px; }
  body.print-matchup .matrix thead th { font-size:8.5px; min-width:0; }
  body.print-matchup .matrix tbody th { font-size:9px; min-width:0; }
  body.print-matchup .send-table,body.print-matchup .wr-list,body.print-matchup .legend { font-size:10px; }
  body.print-matchup .risk-grid { grid-template-columns:1fr 1fr 1fr; gap:8px; }
  body.print-matchup .risk-grid h3 { font-size:11px; }
  body.print-matchup .scout-grid { grid-template-columns:1fr 1fr; gap:6px; }
  body.print-matchup .scout { break-inside:avoid; }
  body.print-matchup .scout dl { font-size:9.5px; padding:4px 8px; }
  body.print-matchup .scout-head { padding:3px 8px; font-size:11px; }
  /* Page 1 density: explanations live in the notes page; keep the decision content. */
  body.print-matchup #matchup-head > p.muted,body.print-matchup .roster-scope,body.print-matchup #wr-opportunities > p.muted,
  body.print-matchup #wr-risks p.muted { display:none; }
  body.print-matchup #team-rosters th:nth-child(6),body.print-matchup #team-rosters td:nth-child(6) { display:none; }
  body.print-matchup #team-rosters td,body.print-matchup #team-rosters th { padding:1px 4px; font-size:9.5px; }
  body.print-matchup .send-table td,body.print-matchup .send-table th { padding:1px 4px; font-size:9px; }
  body.print-matchup .send-table td:first-child { white-space:nowrap; width:42%; }
  body.print-matchup .send-table td:last-child,body.print-matchup .wr-list li,body.print-matchup .scout dd,body.print-matchup .matrix th { white-space:normal; }
  body.print-matchup .wr-list { font-size:9px; margin:0; padding-left:14px; }
  body.print-matchup #wr-opportunities h2,body.print-matchup #wr-risks h2 { font-size:12px; margin:0 0 2px; }
  body.print-matchup .matchup-teams { gap:4px; }
  body.print-matchup .matchup-facts { margin-top:2px; }
  body.print-matchup .matchup-side b { display:inline; margin:0 6px; font-size:12px; }
  body.print-matchup .matchup-teams { grid-template-columns:1fr auto 1fr; }
  body.print-matchup #matchup-print > .card,body.print-matchup #team-rosters > .card { padding:4px 8px; margin-bottom:4px; }
  body.print-matchup #team-rosters h2 { font-size:12px; }
  body.print-matchup .roster-summary { font-size:9.5px; }
  body.print-matchup .send { margin:0; }
  body.print-matchup #team-rosters,body.print-matchup #wr-opportunities,body.print-matchup #wr-risks { line-height:1.25; }
}
"""


def _script_json(value: Any) -> str:
    """Serialize for embedding inside <script type="application/json">.

    json.dumps(..., ensure_ascii=True) (the default) already backslash-
    escapes every non-ASCII character -- including U+2028/U+2029 LINE/
    PARAGRAPH SEPARATOR -- as \\uXXXX, so those never reach the page as raw
    bytes. What it does NOT do is touch plain ASCII '<', '>', '&', which is
    exactly what a source string containing a literal "</script>" or
    "<script>" needs to break out of this element. JSON syntax itself never
    uses '<', '>', or '&' outside a quoted string value, so replacing them
    globally in the dumped text only ever rewrites string CONTENT, never
    JSON structure -- and \\uXXXX is valid inside a JSON string, so
    JSON.parse() on the browser side reconstructs the original character
    exactly. This closes the '<script>'/'&entity;' cases the previous
    "</"-only replacement did not cover, without weakening JSON.parse
    compatibility at all.
    """
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_BROWSER_EVIDENCE_FIELDS = (
    "opponent_id",
    "match_date",
    "session_name",
    "result",
    "own_skill_level",
    "opponent_skill_level",
    "points_earned",
)

# EIGHT/NINE are always offered even with zero matching evidence -- they are
# the two primary APA team formats. Any other raw format recorded in the
# source data (e.g. "MASTERS", "MASTERS ALT" -- both are real APA formats,
# see scraper.graphql_scraper._VALID_FORMATS) is appended rather than
# dropped, so a real recorded meeting can never be unreachable from the
# Format selectors just because it happened outside 8-Ball/9-Ball. Mirrors
# the equivalent fix in ui/export_excel_ultimate_coach.py.
BASE_FORMAT_ORDER = ["EIGHT", "NINE"]
FORMAT_LABELS = {"EIGHT": "8-Ball", "NINE": "9-Ball", "MASTERS": "Masters", "MASTERS ALT": "Masters Alt"}


def _format_label(fmt: str) -> str:
    return FORMAT_LABELS.get(fmt, fmt)


def _raw_format_option_label(raw: str) -> str:
    return f"{FORMAT_LABELS[raw]} (recorded as {raw})" if raw in FORMAT_LABELS else raw


def _format_options(formats_present: list[str]) -> list[str]:
    extra = sorted(set(formats_present) - set(BASE_FORMAT_ORDER))
    return BASE_FORMAT_ORDER + extra


def _browser_payload(
    payload: dict[str, Any], *, consume_evidence: bool = False
) -> dict[str, Any]:
    """Compact and pre-index evidence for fast standalone-browser use.

    Production builders may drain the large raw evidence list while it is
    compacted so the dict-heavy source rows and compact browser index do not
    remain resident in memory at the same time.
    """
    compact = {key: value for key, value in payload.items() if key != "evidence"}
    index: dict[str, list[list[Any]]] = {}
    formats_present: set[str] = set()
    evidence = payload.get("evidence") or []
    if consume_evidence and isinstance(evidence, list):
        while evidence:
            row = evidence.pop()
            fmt = row.get("format") or ""
            if fmt:
                formats_present.add(fmt)
            key = f"{row.get('player_id')}|{fmt}"
            index.setdefault(key, []).append(
                [row.get(field) for field in _BROWSER_EVIDENCE_FIELDS]
            )
    else:
        for row in evidence:
            fmt = row.get("format") or ""
            if fmt:
                formats_present.add(fmt)
            key = f"{row.get('player_id')}|{fmt}"
            index.setdefault(key, []).append(
                [row.get(field) for field in _BROWSER_EVIDENCE_FIELDS]
            )
    compact["browser_payload_schema"] = "ultimate-coach-browser-compact-v1"
    compact["evidence_row_fields"] = list(_BROWSER_EVIDENCE_FIELDS)
    compact["evidence_index"] = index
    compact["formats_present"] = sorted(formats_present)
    compact["format_labels"] = FORMAT_LABELS
    return compact


def _trust_card(payload: dict[str, Any]) -> str:
    """Server-rendered Data Trust/Coverage summary.

    Static per payload -- no client-side JS needed for this card, and it
    degrades gracefully (all zero counts, no crash) if rendered against an
    older payload shape that never carried a "trust" section at all.
    """
    trust = payload.get("trust") or {}

    def n(key: str) -> int:
        return int(trust.get(key) or 0)

    return f"""<div class="card">
  <h2>Data Trust &amp; Coverage</h2>
  <div class="metric-grid">
    <div class="metric"><b>{n('verified_identity_count')}</b><span>Verified selectable identities</span></div>
    <div class="metric"><b>{n('identity_exclusion_count')}</b><span>Identities excluded (unresolved/ambiguous)</span></div>
    <div class="metric"><b>{n('identity_verified_game_count')}</b><span>Identity-verified games usable as evidence</span></div>
    <div class="metric"><b>{n('quarantined_game_count')}</b><span>Games quarantined (not used as evidence)</span></div>
    <div class="metric"><b>{n('suspect_participant_count')}</b><span>Suspect participant rows</span></div>
    <div class="metric"><b>{n('indeterminate_participant_count')}</b><span>Indeterminate participant rows</span></div>
    <div class="metric"><b>{n('source_coverage_issue_count')}</b><span>Source coverage issues (contract-level)</span></div>
  </div>
  <p class="muted">Only players with roster-backed, uniquely-verified identity provenance are selectable below. Only games that are both mirror-verified and identity-verified feed direct/shared-opponent evidence. Quarantined or unresolved evidence is counted above, never silently dropped or blended in.</p>
</div>"""


def render(
    payload: dict[str, Any],
    *,
    built_at: str = "",
    consume_evidence: bool = False,
    viewer_member_external_id: str | None = None,
    viewer_card_number: str | None = None,
    match_night: dict[str, Any] | None = None,
) -> str:
    compact_payload = _browser_payload(payload, consume_evidence=consume_evidence)
    compact_payload["match_night"] = match_night
    format_options = _format_options(compact_payload.get("formats_present") or [])
    format_options_markup = "".join(
        f'<option value="{escape(fmt)}">{escape(_format_label(fmt))}</option>'
        for fmt in format_options
    )
    players = payload.get("players") or []
    match_day = payload.get("match_day") or build_match_day_section([], players)
    compact_payload["match_day"] = match_day
    # Match Day filters FIXTURES by their raw recorded label ("8-Ball
    # Doubles", "9-Ball Open", ...): the default keeps every 8-Ball and
    # 9-Ball variant, and every other recorded format stays selectable.
    raw_formats = sorted({str(f.get("format_raw") or "") for f in match_day.get("fixtures") or []} - {""})
    md_format_options_markup = (
        f'<option value="{FORMAT_FILTER_EIGHT_NINE}">{escape(FORMAT_FILTER_EIGHT_NINE_LABEL)}</option>'
        f'<option value="{FORMAT_FILTER_ALL}">{escape(FORMAT_FILTER_ALL_LABEL)}</option>'
        + "".join(f'<option value="{escape(fmt)}">{escape(_raw_format_option_label(fmt))}</option>' for fmt in raw_formats)
    )
    resolved_viewer = viewer_player(players, viewer_member_external_id)
    compact_payload["viewer"] = {
        "configured": bool(viewer_member_external_id),
        "external_id": viewer_member_external_id,
        "card_number": viewer_card_number if resolved_viewer else None,
        "resolved": resolved_viewer is not None,
        "player_id": resolved_viewer.get("id") if resolved_viewer else None,
        "player_name": resolved_viewer.get("name") if resolved_viewer else None,
        "teams": viewer_current_teams(players, viewer_member_external_id),
    }
    tz_name = str(match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE)
    build_local = build_local_date(built_at, tz_name) if built_at else None
    fresh = freshness(match_day, build_local)
    if payload.get("snapshot_freshness"):      # Match Night package: freshness of the whole snapshot, not one fixture
        fresh = {**fresh, **payload["snapshot_freshness"]}
    compact_payload["build"] = {"built_at": built_at, "build_local": build_local, **{k: fresh[k] for k in (
        "build_date", "latest_result", "unplayed_before_build")}}
    # Start here: the same onboarding text, worked example and version as the Excel START HERE tab.
    rosters = build_team_rosters(payload)
    label_by_scope = {r["team_scope_key"]: r["team_label"] for r in rosters}
    example = None
    if resolved_viewer:
        viewer_scopes = sorted({r["team_scope_key"] for r in rosters if r["player_id"] == resolved_viewer["id"]})
        example = worked_example(match_day, default_matchup(match_day, viewer_scopes, build_local, label_by_scope),
                                 player_ref(resolved_viewer), label_by_scope)
    version = build_version()
    compact_payload["coach_tags"] = COACH_TAGS
    li = lambda items: "".join(f"<li>{escape(x.lstrip('• '))}</li>" for x in items)
    steps = [
        ('#match-day-card', "Match Day", "pick yourself, team, format and date (and the fixture if two share a day)."),
        ('#tonight', "Tonight", "opponent, availability, evidence counts and best sends at a glance."),
        ('#lineup-lab', "Lineup Lab", "mark who's here and who has played — marks belong to that one fixture."),
        ('#team-section', "War Room", "best sends, risks and the colour matrix — tap a cell for the evidence."),
        ('#scouting-cards', "Scouting cards", "every opponent, plus your own coach notes."),
    ]
    start_here = (
        '<details class="card start-here" id="start-here" open><summary><b>Start here</b> — what Ultimate Coach does '
        'and how to use it in three minutes</summary><div class="sh-grid">'
        f'<div><h3>What Ultimate Coach does</h3><ul>{li(ONBOARDING_WHAT)}</ul></div>'
        '<div><h3>Quick start</h3><ol>'
        + "".join(f'<li><a href="{href}">{escape(name)}</a>: {escape(text)}</li>' for href, name, text in steps)
        + '<li>Print the Captain Packet (button at the top of the War Room).</li></ol></div>'
        '<div><h3>Worked example from this build</h3><ul>'
        + (li(example) if example else "<li>No viewer is configured for this build: pick yourself on Match Day and it "
           "fills in team, date and fixture the same way.</li>")
        + f'</ul></div></div><h3>Important limitations</h3><ul>{li(ONBOARDING_LIMITS)}</ul>'
        f'<h3>Mobile match night</h3><ul>{li(MATCH_NIGHT_GUIDE)}</ul>'
        f'<p class="muted">Version: {escape(version)} · Build date: {escape(fresh["build_date"])} · data current to the '
        f'latest recorded result {escape(fresh["latest_result"])}'
        + (f' · {fresh["unplayed_before_build"]} earlier fixtures still show UNPLAYED in this snapshot'
           if fresh["unplayed_before_build"] else "")
        + ' · this page never refreshes itself.</p></details>'
    )
    data = _script_json(compact_payload)
    built_label_js = _script_json(f"Ultimate Coach · built {built_at}" if built_at else "Ultimate Coach · offline build")
    player_count = int((payload.get("counts") or {}).get("players") or 0)
    evidence_count = int((payload.get("counts") or {}).get("head_to_head_rows") or 0)
    trust_card = _trust_card(payload)
    coverage = match_day.get("coverage") or {}
    display_tz = escape(str(match_day.get("display_timezone") or DEFAULT_MATCH_DAY_TIMEZONE))
    schedule_note = (
        f"Schedule coverage: {int(coverage.get('embedded_fixture_count') or 0):,} of "
        f"{int(coverage.get('stored_fixture_count') or 0):,} stored fixtures are included — every fixture "
        f"involving a team with a current captured roster ({escape(', '.join(coverage.get('current_sessions') or []) or 'no current session')}). "
        f"The other {int(coverage.get('excluded_fixture_count') or 0):,} belong to past-session teams with no current "
        "roster, so My Team can't reach them; their individual game results are still fully used as scouting evidence."
    )
    location_note = (
        f"Venue is blank in the source for {int(coverage.get('location_missing_count') or 0):,} of these fixtures and shows as “No data”."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ultimate Coach — Captain's War Room</title>
<style>
:root {{
  color-scheme: light;
  --felt:#14532d; --felt-deep:#0c3a1f; --felt-soft:#e7f1ea; --rail:#5a3a1f;
  --brass:#b8862b; --brass-soft:#f6ecd6; --paper:#f4f1ea; --card:#ffffff;
  --ink:#17221c; --muted:#5b6a61; --line:#e2dccf; --line-strong:#cfc6b4;
  --warn-bg:#fff6df; --warn-line:#b78300; --info-bg:#eaf2fb; --info-line:#2b5d8f;
  --radius:12px;
}}
* {{ box-sizing:border-box; }}
body {{ font-family:"Segoe UI",system-ui,-apple-system,Roboto,sans-serif; margin:0; background:var(--paper); color:var(--ink); font-size:15px; line-height:1.45; }}
header.hero {{ background:radial-gradient(120% 140% at 0% 0%,#1f6f43 0%,var(--felt) 45%,var(--felt-deep) 100%); color:#fff; padding:22px 24px 18px; border-bottom:6px solid var(--rail); }}
.hero-inner {{ max-width:1400px; margin:auto; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
.ball {{ width:44px; height:44px; border-radius:50%; background:radial-gradient(circle at 35% 30%,#555 0%,#111 60%); display:flex; align-items:center; justify-content:center; flex:none; box-shadow:0 2px 6px rgba(0,0,0,.35); }}
.ball span {{ background:#fff; color:#111; width:22px; height:22px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:13px; }}
header h1 {{ margin:0; font-size:26px; letter-spacing:.2px; }}
header p {{ margin:4px 0 0; opacity:.88; font-size:14px; }}
nav.sections {{ max-width:1400px; margin:12px auto 0; display:flex; gap:8px; flex-wrap:wrap; }}
nav.sections a {{ color:#fff; text-decoration:none; font-size:13px; font-weight:600; padding:6px 12px; border-radius:999px; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.22); }}
nav.sections a:hover,nav.sections a:focus-visible {{ background:rgba(255,255,255,.24); }}
.freshness {{ max-width:1400px; margin:14px auto 0; padding:0 18px; display:flex; gap:8px; flex-wrap:wrap; font-size:12.5px; color:var(--muted); }}
.freshness span {{ background:var(--card); border:1px solid var(--line); border-radius:999px; padding:4px 10px; }}
.freshness .badge-uncal {{ background:var(--warn-bg); border-color:#e8cf8a; color:#6b4d00; font-weight:700; }}
main {{ max-width:1400px; margin:auto; padding:16px 18px 40px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:18px; margin-bottom:16px; box-shadow:0 1px 2px rgba(30,25,10,.05); }}
.card:empty {{ display:none; }}
.card-feature {{ border-top:5px solid var(--felt); }}
.section-title {{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin:26px 0 10px; }}
.section-title h2 {{ margin:0; font-size:21px; color:var(--felt-deep); }}
.section-title p {{ margin:0; color:var(--muted); font-size:13px; }}
.card-head {{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:12px; }}
.card-head h2 {{ margin:0; }}
.pill {{ display:inline-block; padding:4px 10px; border-radius:999px; background:var(--felt-soft); color:var(--felt-deep); font-size:12px; font-weight:700; border:1px solid #c9dfd0; }}
.controls {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
label {{ font-size:12px; font-weight:700; color:#46564d; display:block; letter-spacing:.2px; text-transform:uppercase; }}
select,input[type="search"],input[type="date"] {{ width:100%; margin-top:6px; padding:10px 11px; font-size:15px; border:1px solid var(--line-strong); border-radius:8px; background:#fff; color:var(--ink); font-family:inherit; text-transform:none; letter-spacing:0; }}
select:focus,input:focus {{ outline:3px solid #9cc7ab; outline-offset:1px; border-color:var(--felt); }}
select:disabled,input:disabled {{ background:#f1efe9; color:#8a948e; }}
input[type="search"] {{ margin-bottom:4px; }}
label .muted {{ text-transform:none; letter-spacing:0; font-weight:400; display:block; margin-top:3px; }}
button {{ font:inherit; font-weight:700; font-size:14px; padding:9px 14px; border-radius:8px; border:1px solid var(--felt); background:var(--felt); color:#fff; cursor:pointer; }}
button:hover,button:focus-visible {{ background:var(--felt-deep); }}
button.chip {{ background:#fff; color:var(--felt-deep); border-color:#bcd5c4; padding:5px 10px; font-size:12.5px; font-weight:600; border-radius:999px; }}
button.chip:hover,button.chip[aria-pressed="true"] {{ background:var(--felt-soft); }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }}
.chips:empty {{ display:none; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.grid > * {{ min-width:0; }}
.metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px; }}
.metric {{ background:#f7f5ef; border:1px solid #ece6d8; border-radius:9px; padding:10px 12px; }}
.metric b {{ display:block; font-size:18px; color:var(--felt-deep); }}
.metric span {{ font-size:11.5px; color:var(--muted); }}
.tag {{ display:inline-block; padding:3px 8px; border-radius:999px; background:var(--felt-soft); color:var(--felt-deep); margin:2px; font-size:12px; }}
.warn {{ background:var(--warn-bg); border-left:5px solid var(--warn-line); padding:10px 12px; }}
.good {{ background:#edf8f0; border-left:5px solid #27813b; padding:10px 12px; }}
.table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th,td {{ padding:8px 9px; border-bottom:1px solid #ece7dc; text-align:left; vertical-align:top; }}
th {{ color:#4f5f56; font-size:11px; text-transform:uppercase; letter-spacing:.4px; background:#f7f5ef; }}
tbody tr:nth-child(even) td {{ background:#fbfaf6; }}
.muted {{ color:var(--muted); font-size:12.5px; }}
h2,h3 {{ margin-top:0; color:var(--felt-deep); }}
h3 {{ font-size:15px; margin-top:14px; }}
.status-line {{ margin:12px 0 4px; font-weight:600; }}
.viewer-box {{ background:var(--brass-soft); border:1px solid #e7d4a7; border-radius:10px; padding:12px 14px; margin-bottom:14px; }}
.viewer-box label {{ color:#5d4413; }}
.fixture {{ border:1px solid var(--line); border-left:6px solid var(--felt); border-radius:10px; padding:14px 16px; margin-top:12px; background:#fff; }}
.fixture.bye {{ border-left-color:var(--brass); background:#fffcf4; }}
.fixture-when {{ font-size:18px; font-weight:800; color:var(--ink); }}
.fixture-vs {{ font-size:16px; margin:4px 0 8px; }}
.fixture-vs b {{ color:var(--felt-deep); }}
.badges {{ display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px; }}
.badge {{ font-size:12px; font-weight:700; padding:3px 9px; border-radius:999px; background:#f1eee6; color:#3f4a44; border:1px solid #e1dbcd; }}
.badge.side {{ background:var(--felt); color:#fff; border-color:var(--felt); }}
.fixture dl {{ display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; margin:0 0 10px; font-size:13.5px; }}
.fixture dt {{ color:var(--muted); }}
.fixture dd {{ margin:0; overflow-wrap:anywhere; }}
.note {{ font-size:13px; padding:8px 10px; border-radius:8px; background:var(--info-bg); border-left:4px solid var(--info-line); margin:8px 0; }}
.note.warn-note {{ background:var(--warn-bg); border-left-color:var(--warn-line); }}
details.disclosure {{ margin-top:14px; border-top:1px solid var(--line); padding-top:10px; }}
details.disclosure summary {{ cursor:pointer; font-weight:700; color:var(--felt-deep); font-size:13.5px; }}
details.disclosure ul {{ margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:13px; }}
footer.page-foot {{ color:var(--muted); font-size:12.5px; border-top:1px solid var(--line); padding-top:12px; }}
.id-line {{ margin:-6px 0 10px; color:var(--muted); font-size:13px; font-weight:600; }}
td .id-line {{ display:block; margin:2px 0 0; font-size:12px; font-weight:400; }}
.roster-head {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.role {{ display:inline-block; font-size:11px; font-weight:800; letter-spacing:.6px; text-transform:uppercase; color:#fff; background:var(--felt); padding:3px 8px; border-radius:6px; }}
.role.opp,#team-rosters > .card:nth-child(2) .role {{ background:var(--rail); }}
.badge.side.opp,#team-rosters > .card:nth-child(2) .badge.side {{ background:var(--rail); border-color:var(--rail); }}
.roster-scope {{ margin:4px 0; font-weight:600; }}
.roster-summary {{ margin:4px 0; font-size:13px; }}
.matchup-head .matchup-when {{ font-size:18px; font-weight:800; margin:2px 0 10px; }}
.matchup-teams {{ display:grid; grid-template-columns:1fr auto 1fr; gap:12px; align-items:center; }}
.matchup-side b {{ display:block; font-size:16px; margin:4px 0; }}
.matchup-vs {{ font-weight:800; color:var(--muted); }}
.matchup-facts {{ display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; font-size:13.5px; margin:12px 0 0; }}
.matchup-facts dt {{ color:var(--muted); }}
.matchup-facts dd {{ margin:0; overflow-wrap:anywhere; }}
.matchup-notes ul {{ margin:6px 0 8px; padding-left:18px; color:var(--muted); font-size:13px; }}
.compare-table td:first-child {{ font-weight:600; color:#3f4a44; }}
.rank-block {{ margin-top:16px; }}
.rank-block h3 {{ margin-bottom:2px; }}
.rank-table td:first-child {{ font-weight:800; white-space:nowrap; }}
.rank-table tr.tier-1 td {{ color:var(--muted); }}
@media(max-width:760px) {{
  .matchup-teams {{ grid-template-columns:1fr; }}
  .matchup-vs {{ display:none; }}
  header.hero {{ padding:16px 16px 14px; }}
  header h1 {{ font-size:21px; }}
  .freshness {{ padding:0 12px; }}
  main {{ padding:12px 12px 32px; }}
  .card {{ padding:14px; }}
  .grid {{ grid-template-columns:1fr; }}
  .fixture-when {{ font-size:16px; }}
  .fixture dl {{ grid-template-columns:1fr; gap:0; }}
  .fixture dt {{ margin-top:6px; }}
}}
@media print {{
  @page {{ size:landscape; margin:10mm; }}
  header.hero,.freshness,#player-section,#trust-section,button,.viewer-box,details.disclosure {{ display:none !important; }}
  body {{ background:#fff; }}
  .card {{ box-shadow:none; break-inside:avoid; }}
  .role,.badge.side {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  /* "Print this matchup": only the fixture header, both labeled rosters and the data notes. */
  body.print-matchup main > :not(#matchup-print) {{ display:none !important; }}
  body.print-matchup main {{ padding:0; max-width:none; }}
  body.print-matchup #team-rosters {{ grid-template-columns:1fr 1fr !important; gap:8px; margin:0; }}
  body.print-matchup .card {{ border:1px solid #bbb; border-radius:6px; padding:7px 10px; margin-bottom:6px; break-inside:auto; }}
  body.print-matchup h2 {{ font-size:15px; margin:0 0 3px; }}
  body.print-matchup .card-head {{ margin-bottom:2px; }}
  body.print-matchup .matchup-when {{ font-size:14px; margin:0 0 4px; }}
  body.print-matchup .matchup-side b {{ font-size:13px; margin:2px 0; }}
  body.print-matchup .matchup-facts {{ grid-template-columns:repeat(3,max-content 1fr); gap:1px 10px; font-size:11px; margin-top:4px; }}
  body.print-matchup .roster-fineprint {{ display:none; }}
  body.print-matchup .roster-scope,body.print-matchup .roster-summary,body.print-matchup .muted {{ font-size:10.5px; margin:1px 0; }}
  body.print-matchup table {{ font-size:10.5px; }}
  body.print-matchup th,body.print-matchup td {{ padding:2px 5px; }}
  body.print-matchup td {{ white-space:nowrap; }}
  body.print-matchup .table-wrap {{ overflow:visible; }}
  body.print-matchup .matchup-notes h3 {{ font-size:12px; margin:0 0 2px; }}
  body.print-matchup .matchup-notes ul {{ font-size:10px; margin:2px 0; columns:2; column-gap:18px; }}
  /* The evidence ranking starts on its own page; each opponent's table stays together. */
  body.print-matchup .rank-blocks {{ columns:2; column-gap:14px; }}
  body.print-matchup .rank-block {{ break-inside:avoid; margin:0 0 8px; }}
  body.print-matchup .rank-block h3 {{ font-size:11px; margin:0; }}
  body.print-matchup .rank-block .muted {{ font-size:9.5px; }}
  body.print-matchup .rank-table {{ font-size:9px; }}
  body.print-matchup .rank-table th,body.print-matchup .rank-table td {{ padding:1px 3px; white-space:normal; }}
  body.print-matchup .rank-table th:nth-child(3),body.print-matchup .rank-table td:nth-child(3) {{ display:none; }}
  body.print-matchup .note {{ font-size:10.5px; padding:4px 8px; margin:4px 0; }}
}}
{_WAR_ROOM_CSS}</style></head>
<body class="{'match-night' if match_night else ''}">
<header class="hero"><div class="hero-inner"><div class="ball" aria-hidden="true"><span>8</span></div>
<div><h1>Ultimate Coach — Captain's War Room</h1>
<p>{player_count} verified players · {evidence_count} identity-verified evidence rows · offline scouting cockpit</p></div></div>
<nav class="sections" aria-label="Sections"><a href="#match-day-card">Match Day</a><a href="#team-section">War Room</a><a href="#wr-matrix">Matrix</a><a href="#lineup-lab">Lineup Lab</a><a href="#scouting-cards">Scouting</a><a href="#player-section">Player vs Player</a><a href="#trust-section">Data trust</a></nav></header>
{f'<div class="mn-banner" title="{escape(match_night["fixture_label"])} · {escape(match_night["fixture_display"])}">{"DEMO (synthetic players) · " if match_night.get("demo") else ""}Match Night package · data frozen at build — re-publish before league night</div>' if match_night else ''}<div class="freshness"><span>Built {escape(fresh["build_date"]) + " (" + escape(built_at) + ")" if build_local else (escape(built_at) if built_at else "from the selected SQLite snapshot")}</span><span>Offline snapshot: latest recorded result {escape(fresh["latest_result"])}</span>{f'<span>{fresh["unplayed_before_build"]} earlier fixtures still show UNPLAYED — results after the snapshot are not included</span>' if fresh["unplayed_before_build"] else ""}<span>Never refreshes itself — rebuild for new results</span><span>Match Day times: {display_tz}</span><span class="badge-uncal">Win probability: NOT CALIBRATED — none shown</span></div>
<main>
{f'<div class="demo-flag">DEMO — synthetic players, not real data</div>' if (match_night or {}).get("demo") else ''}<section id="tonight" class="card tonight" aria-label="Tonight at a glance"></section>
{start_here}
<section class="card card-feature" id="match-day-card">
  <div class="card-head"><h2>Match Day</h2><span class="pill" id="md-tz">All dates &amp; times in {display_tz}</span></div>
  <div class="viewer-box">
    <label>I am (verified player)<input id="md-viewer-search" type="search" placeholder="Search your name or APA record ID" autocomplete="off"><select id="md-viewer"></select></label>
    <p id="md-viewer-status" class="muted"></p>
  </div>
  <div class="controls">
    <label>1 · Date<input id="md-date" type="date"></label>
    <label>2 · My Team<select id="md-team"></select></label>
    <label>3 · Format<select id="md-format">{md_format_options_markup}</select></label>
  </div>
  <label class="md-date-list">Scheduled dates for this team &amp; format<select id="md-date-list"></select></label>
  <div id="md-team-dates" class="chips" aria-label="Dates this team plays"></div>
  <p id="md-status" class="status-line"></p>
  <div id="md-fixtures"></div>
  <details class="disclosure"><summary>About Match Day data</summary><ul>
    <li>Dates, weekdays and kickoff times are converted to {display_tz} (MST/MDT as applicable). Each fixture also shows its original source timestamp.</li>
    <li>Rosters shown below are each team's CURRENT roster, not a reconstruction of who actually played on the chosen date — this data source doesn't capture historical lineups, so no date-specific lineup accuracy is promised.</li>
    <li id="md-coverage">{schedule_note}</li>
    <li>{location_note}</li>
    <li>“APA record ID” is APA's internal member record number. It is not the league card number printed on a member card (card numbers differ per league and are not stored in this data).</li>
  </ul></details>
</section>

<div class="section-title" id="team-section"><h2>Captain's War Room</h2><p>Who do I put up next? Follows Match Day; pick other teams here to explore.</p></div>
<div class="card">
  <div class="controls">
    <label>Our Team<input id="search-team-a" type="search" placeholder="Search our team"><select id="team-a"></select><span id="search-status-team-a" class="muted"></span></label>
    <label>Opponent Team<input id="search-team-b" type="search" placeholder="Search opponent team"><select id="team-b"></select><span id="search-status-team-b" class="muted"></span></label>
    <label>Format<select id="team-format">{format_options_markup}</select></label>
  </div>
  <p class="muted">Rosters are each team's current captured roster, not who played on any particular past date.</p>
</div>
<section id="matchup-print" aria-label="Printable matchup">{f'<div class="demo-flag">DEMO — synthetic players, not real data</div>' if (match_night or {}).get("demo") else ''}
<div id="matchup-head" class="card matchup-head"></div>
<div id="team-rosters" class="grid"></div>
<div id="wr-opportunities" class="card"></div>
<div id="wr-risks" class="card"></div>
<div id="wr-matrix" class="card"></div>
<div id="lineup-lab" class="card"></div>
<div id="team-comparison" class="card"></div>
<div id="team-matchups" class="card"></div>
<div id="scouting-cards" class="card"></div>
<div id="wr-meetings" class="card"></div>
<div id="matchup-notes" class="card matchup-notes"></div>
</section>

<div id="player-section">
<div class="section-title"><h2>Player vs Player</h2><p>Direct and shared-opponent history between any two verified players.</p></div>
<div class="card">
  <div class="controls">
    <label>Player A<input id="search-a" type="search" placeholder="Search player A"><select id="player-a"></select><span id="search-status-a" class="muted"></span></label>
    <label>Player B<select id="player-b-scope" aria-label="Player B pool"><option value="played">Played opponents</option><option value="all">All players</option></select><input id="search-b" type="search" placeholder="Search player B"><select id="player-b"></select><span id="search-status-b" class="muted"></span></label>
    <label>Format<select id="format">{format_options_markup}</select></label>
  </div>
</div>
<div id="status" class="card warn"></div>
<div class="grid">
  <div id="profile-a" class="card"></div>
  <div id="profile-b" class="card"></div>
</div>
<div id="summary" class="card"></div>
<div id="direct" class="card"></div>
<div id="shared" class="card"></div>
<div id="meetings" class="card"></div>
</div>

<div id="trust-section">
<div class="section-title"><h2>Data trust &amp; freshness</h2><p>What is verified, what is excluded, and why.</p></div>
{trust_card}
</div>
<footer class="page-foot">Built {escape(built_at) if built_at else "from the selected SQLite snapshot"}. This page shows recorded APA facts and derived comparisons only. No matchup probability is displayed until a separately back-tested calibration gate passes.</footer>
</main>
<script id="uc-data" type="application/json">{data}</script>
<script>
(function() {{
  var DATA=JSON.parse(document.getElementById("uc-data").textContent);
  var BUILT_LABEL={built_label_js};
  var PLAYERS={{}}; DATA.players.forEach(function(p){{PLAYERS[String(p.id)]=p;}});
  var EVIDENCE_INDEX=DATA.evidence_index||{{}};
  var EVIDENCE_FIELDS=DATA.evidence_row_fields||[];
  var EC={{}}; EVIDENCE_FIELDS.forEach(function(name,i){{EC[name]=i;}});
  var A=document.getElementById("player-a"), B=document.getElementById("player-b"), F=document.getElementById("format");
  var BSCOPE=document.getElementById("player-b-scope");
  var SA=document.getElementById("search-a"), SB=document.getElementById("search-b");
  var SSA=document.getElementById("search-status-a"), SSB=document.getElementById("search-status-b");
  var MAX_OPTIONS=75;
  var SEARCH_DEBOUNCE_MS=300;
  function esc(v){{return String(v===null||v===undefined?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}}
  function pct(w,g){{return g?((w/g)*100).toFixed(1)+"%":"No data";}}
  function val(row,name){{return row[EC[name]];}}
  // Names are shown next to the APA record ID everywhere a player is picked
  // or listed; every lookup still keys on the player's id, never the name.
  function recordIdText(p){{var x=p&&p.external_id;return x===null||x===undefined||x===""?"not captured":String(x);}}
  function playerLabel(p){{return p.name+" · APA record ID "+recordIdText(p);}}
  function playerRef(p){{return p.name+" (APA record ID "+recordIdText(p)+")";}}
  var SORTED=DATA.players.slice().sort(function(x,y){{return x.name.localeCompare(y.name);}});
  var SEARCH_NAMES={{}}; SORTED.forEach(function(p){{SEARCH_NAMES[String(p.id)]=(p.name+" "+recordIdText(p)).toLowerCase();}});

  var FORMAT_LABELS=DATA.format_labels||{{}};
  function formatName(fmt){{return FORMAT_LABELS[fmt]||fmt;}}
  function matchingPlayers(filter,candidates) {{
    var q=String(filter||"").trim().toLowerCase();
    var matches=(candidates||SORTED).filter(function(p){{return !q||SEARCH_NAMES[String(p.id)].indexOf(q)!==-1;}});
    return {{rows:matches.slice(0,MAX_OPTIONS),total:matches.length}};
  }}
  function selectMarkup(found,previous,labeler) {{
    var keep=previous&&found.rows.some(function(p){{return String(p.id)===String(previous);}});
    var placeholder='<option value="">Select a player...</option>';
    var rows=found.rows.map(function(p){{return '<option value="'+p.id+'">'+esc(labeler?labeler(p):playerLabel(p))+'</option>';}}).join("");
    return {{html:placeholder+rows,value:keep?String(previous):""}};
  }}
  function applyPlayerASearch() {{
    var previous=A.value, found=matchingPlayers(SA.value,SORTED);
    var rendered=selectMarkup(found,previous,null);
    A.innerHTML=rendered.html;
    A.value=rendered.value;
    SSA.textContent=found.total>MAX_OPTIONS
      ? "Showing first "+MAX_OPTIONS+" of "+found.total+" matches. Keep typing, then choose a player."
      : found.total+" matching player"+(found.total===1?"":"s")+". Choose a player to load opponents.";
  }}
  function rowsFor(pid,fmt){{return EVIDENCE_INDEX[String(pid)+"|"+fmt]||[];}}
  function playerBPool() {{
    var playerA=String(A.value||"");
    if(!playerA) return {{players:[],counts:{{}}}};
    if(BSCOPE.value==="all") {{
      return {{players:SORTED.filter(function(p){{return String(p.id)!==playerA;}}),counts:{{}}}};
    }}
    var counts={{}};
    rowsFor(playerA,F.value).forEach(function(r){{
      var id=String(val(r,"opponent_id"));
      if(id!==playerA&&PLAYERS[id]) counts[id]=(counts[id]||0)+1;
    }});
    return {{
      players:SORTED.filter(function(p){{return !!counts[String(p.id)];}}),
      counts:counts
    }};
  }}
  function refreshPlayerB(preserveSelection) {{
    var previous=preserveSelection?B.value:"";
    var pool=playerBPool(), found=matchingPlayers(SB.value,pool.players);
    var rendered=selectMarkup(found,previous,function(p){{
      var count=pool.counts[String(p.id)]||0;
      var suffix=BSCOPE.value==="played"&&count
        ? " · "+count+" meeting"+(count===1?"":"s")
        : "";
      return playerLabel(p)+suffix;
    }});
    B.innerHTML=rendered.html;
    B.value=rendered.value;
    var pa=PLAYERS[A.value], fmt=formatName(F.value);
    if(BSCOPE.value==="played") {{
      if(!pool.players.length) {{
        SSB.textContent="No recorded opponents for "+(pa?pa.name:"Player A")+" in "+fmt+".";
      }} else if(String(SB.value||"").trim()) {{
        SSB.textContent=found.total+" matching of "+pool.players.length+" recorded opponent"+(pool.players.length===1?"":"s")+".";
      }} else {{
        SSB.textContent=pool.players.length+" recorded opponent"+(pool.players.length===1?"":"s")+" for "+(pa?pa.name:"Player A")+" in "+fmt+".";
      }}
    }} else {{
      SSB.textContent=found.total>MAX_OPTIONS
        ? "Showing first "+MAX_OPTIONS+" of "+found.total+" players. Keep typing to narrow."
        : found.total+" matching player"+(found.total===1?"":"s")+" (all-player scouting).";
    }}
  }}
  applyPlayerASearch();
  refreshPlayerB(false);
  function record(rows){{var w=rows.filter(function(r){{return val(r,"result")==="W";}}).length;return {{w:w,l:rows.length-w,g:rows.length}};}}
  function career(p,fmt){{return (p.career_stats||[]).filter(function(r){{return r.format===fmt;}});}}
  // A scope counts only when BOTH wins and games are recorded and consistent -- a missing
  // count is never zero-filled (an unknown win must not become a loss).
  function careerCount(r){{var w=r.matches_won,g=r.matches_played;return Number.isInteger(w)&&Number.isInteger(g)&&w>=0&&w<=g?[w,g]:null;}}
  function careerComplete(rows){{var w=0,g=0,bad=0;rows.forEach(function(r){{var c=careerCount(r);if(c){{w+=c[0];g+=c[1];}}else bad++;}});return {{w:w,g:g,incomplete:bad}};}}
  function profile(p,fmt) {{
    var c=career(p,fmt), cc=careerComplete(c), totalW=cc.w, totalG=cc.g;
    var seenTeamTags={{}};
    var teams=(p.team_history||[]).slice().reverse().filter(function(t){{
      var tag=[t.session_name||"",t.team_name||"",t.skill_level===null?"":t.skill_level].join("|");
      if(seenTeamTags[tag]) return false;
      seenTeamTags[tag]=true;
      return true;
    }}).slice(0,12);
    return '<h2>'+esc(p.name)+'</h2><p class="id-line">APA record ID '+esc(recordIdText(p))+'</p>'
      +'<div class="metric-grid"><div class="metric"><b>'+(p.current_skill_level===null?'—':p.current_skill_level)+'</b><span>Current captured SL</span></div>'
      +'<div class="metric"><b>'+(totalG?(totalW+'-'+(totalG-totalW)):(c.length?'No data':'Pending'))+'</b><span>League-scoped lifetime '+esc(formatName(fmt))+' W-L'+(cc.incomplete?' ('+cc.incomplete+' scope'+(cc.incomplete===1?'':'s')+' with missing wins or games not counted)':'')+'</span></div>'
      +'<div class="metric"><b>'+(totalG?pct(totalW,totalG):'—')+'</b><span>Lifetime win rate</span></div></div>'
      +'<h3>League stats</h3>'+(c.length?'<div class="table-wrap"><table><thead><tr><th>League</th><th>W-L</th><th>Last played</th><th>B&R</th><th>Mini slams</th></tr></thead><tbody>'
        +c.map(function(r){{var cnt=careerCount(r);return '<tr><td>'+esc(r.league_slug||r.league_id)+'</td><td>'+(cnt?cnt[0]+'-'+(cnt[1]-cnt[0]):'No data')+'</td><td>'+esc(r.last_played?isoDateLabel(String(r.last_played).slice(0,10)):'—')+'</td><td>'+esc(r.break_and_runs===null?'—':r.break_and_runs)+'</td><td>'+esc(r.mini_slams===null?'—':r.mini_slams)+'</td></tr>';}}).join('')+'</tbody></table></div>':'<p class="muted">Career-stat enrichment is still in progress for this build. Historical match evidence below is already usable.</p>')
      +'<h3>Recent team/session history</h3>'+(teams.length?teams.map(function(t){{return '<span class="tag">'+esc(t.session_name||'Unknown session')+' · '+esc(t.team_name||'Unknown team')+(t.skill_level!==null?' · SL '+t.skill_level:'')+'</span>';}}).join(''):'<p class="muted">No team history captured.</p>');
  }}

  function compare() {{
    var pa=PLAYERS[A.value], pb=PLAYERS[B.value], fmt=F.value;
    if(!pa) return;
    document.getElementById("profile-a").innerHTML=profile(pa,fmt);
    if(!pb) {{
      document.getElementById("profile-b").innerHTML='<h2>No opponent selected</h2><p class="muted">'+(BSCOPE.value==="played"?'No recorded opponent is available for '+esc(pa.name)+' in '+esc(formatName(fmt))+'.':'Search or choose a Player B to compare.')+'</p>';
      document.getElementById("summary").innerHTML='<h2>What we know</h2><p><strong>'+(BSCOPE.value==="played"?'No recorded opponents for '+esc(pa.name)+' in '+esc(formatName(fmt))+'. Switch Player B to “All players” for broader scouting.':'Choose Player B to compare with '+esc(pa.name)+'.')+'</strong></p>';
      document.getElementById("direct").innerHTML='';
      document.getElementById("shared").innerHTML='';
      document.getElementById("meetings").innerHTML='';
      document.getElementById("status").innerHTML='<strong>Probability status: NOT CALIBRATED.</strong> Scout & Compare is showing real source evidence only. The future odds model must pass chronological backtesting before a percentage appears here.';
      return;
    }}
    document.getElementById("profile-b").innerHTML=profile(pb,fmt);
    if(String(pa.id)===String(pb.id)) {{
      document.getElementById("summary").innerHTML='<h2>What we know</h2><p>Choose two different players to compare.</p>';
      document.getElementById("direct").innerHTML='';
      document.getElementById("shared").innerHTML='';
      document.getElementById("meetings").innerHTML='';
      return;
    }}

    var ar=rowsFor(pa.id,fmt), br=rowsFor(pb.id,fmt);
    var direct=ar.filter(function(r){{return String(val(r,"opponent_id"))===String(pb.id);}});
    var dr=record(direct);
    var ag={{}},bg={{}};
    ar.forEach(function(r){{var id=String(val(r,"opponent_id"));(ag[id]||(ag[id]=[])).push(r);}});
    br.forEach(function(r){{var id=String(val(r,"opponent_id"));(bg[id]||(bg[id]=[])).push(r);}});
    var ids=Object.keys(ag).filter(function(id){{return bg[id]&&id!==String(pa.id)&&id!==String(pb.id);}});
    ids.sort(function(x,y){{return (ag[y].length+bg[y].length)-(ag[x].length+bg[x].length);}});

    var summaryText=dr.g
      ? esc(pa.name)+' and '+esc(pb.name)+' have '+dr.g+' recorded direct meeting'+(dr.g===1?'':'s')+' in '+esc(formatName(fmt))+'.'
      : 'No recorded direct meeting between '+esc(pa.name)+' and '+esc(pb.name)+' in '+esc(formatName(fmt))+'.';
    summaryText+=' '+(ids.length
      ? 'They share '+ids.length+' recorded opponent'+(ids.length===1?'':'s')+', so you still have indirect history to compare.'
      : 'No shared-opponent evidence is recorded for this format.');
    document.getElementById("summary").innerHTML='<h2>What we know</h2><p><strong>'+summaryText+'</strong></p>'
      +'<div class="metric-grid"><div class="metric"><b>'+ar.length+'</b><span>'+esc(pa.name)+' evidence rows in '+esc(formatName(fmt))+'</span></div>'
      +'<div class="metric"><b>'+br.length+'</b><span>'+esc(pb.name)+' evidence rows in '+esc(formatName(fmt))+'</span></div>'
      +'<div class="metric"><b>'+dr.g+'</b><span>Direct meetings</span></div>'
      +'<div class="metric"><b>'+ids.length+'</b><span>Shared opponents</span></div></div>';

    document.getElementById("direct").innerHTML='<h2>Direct history</h2><div class="metric-grid"><div class="metric"><b>'+(dr.g?(dr.w+'-'+dr.l):'No recorded evidence')+'</b><span>'+esc(pa.name)+' record vs '+esc(pb.name)+'</span></div><div class="metric"><b>'+(dr.g?pct(dr.w,dr.g):'—')+'</b><span>Observed direct win rate</span></div><div class="metric"><b>'+dr.g+'</b><span>Recorded meetings</span></div></div>';

    var visibleIds=ids.slice(0,100);
    var sharedRows=visibleIds.map(function(id){{var p=PLAYERS[id],ra=record(ag[id]),rb=record(bg[id]);return '<tr><td>'+esc(p?playerLabel(p):id)+'</td><td>'+ra.w+'-'+ra.l+' ('+pct(ra.w,ra.g)+')</td><td>'+rb.w+'-'+rb.l+' ('+pct(rb.w,rb.g)+')</td><td>'+ra.g+' / '+rb.g+'</td></tr>';}}).join('');
    var limitNote=ids.length>visibleIds.length?'<p class="muted">Showing the 100 shared opponents with the largest combined samples.</p>':'';
    document.getElementById("shared").innerHTML='<h2>Shared-opponent evidence</h2>'+(ids.length?'<p class="muted">'+ids.length+' opponent(s) both players have actually faced in '+esc(formatName(fmt))+'.</p>'+limitNote+'<div class="table-wrap"><table><thead><tr><th>Shared opponent</th><th>'+esc(pa.name)+'</th><th>'+esc(pb.name)+'</th><th>Samples A/B</th></tr></thead><tbody>'+sharedRows+'</tbody></table></div>':'<p class="muted">No recorded shared opponents in this format.</p>');

    var meetings=direct.slice().sort(function(x,y){{return String(val(y,"match_date")).localeCompare(String(val(x,"match_date")));}});
    document.getElementById("meetings").innerHTML='<h2>Recorded meetings</h2>'+(meetings.length?'<div class="table-wrap"><table><thead><tr><th>Date</th><th>Session</th><th>Result</th><th>SL</th><th>Opponent SL</th><th>Points</th></tr></thead><tbody>'+meetings.map(function(r){{return '<tr><td>'+esc(val(r,"match_date")?wrDayLabel(wrInstant(val(r,"match_date"))):'—')+'</td><td>'+esc(val(r,"session_name")||'—')+'</td><td>'+esc(val(r,"result"))+'</td><td>'+esc(val(r,"own_skill_level")===null?'—':val(r,"own_skill_level"))+'</td><td>'+esc(val(r,"opponent_skill_level")===null?'—':val(r,"opponent_skill_level"))+'</td><td>'+esc(val(r,"points_earned")===null?'—':val(r,"points_earned"))+'</td></tr>';}}).join('')+'</tbody></table></div>':'<p class="muted">These players have no recorded direct meeting in this format.</p>');

    document.getElementById("status").innerHTML='<strong>Probability status: NOT CALIBRATED.</strong> Scout & Compare is showing real source evidence only. The future odds model must pass chronological backtesting before a percentage appears here.';
  }}

  A.addEventListener("change",function(){{SB.value="";refreshPlayerB(false);compare();}});
  B.addEventListener("change",compare);
  F.addEventListener("change",function(){{
    // "All players" mode's candidate pool (SORTED minus Player A) does not
    // depend on format at all -- only "played opponents" mode does. So a
    // format switch while scouting "all" must keep the selected Player B
    // and search text, and simply recompute the comparison against the new
    // format's evidence. Only "played" mode's selection and search get
    // cleared, since that pool genuinely can change under a new format.
    var preserve=BSCOPE.value==="all";
    if(!preserve) SB.value="";
    refreshPlayerB(preserve);
    compare();
  }});
  BSCOPE.addEventListener("change",function(){{SB.value="";refreshPlayerB(false);compare();}});
  var searchTimers={{a:null,b:null}};
  SA.addEventListener("input",function(){{
    clearTimeout(searchTimers.a);
    searchTimers.a=setTimeout(function(){{
      applyPlayerASearch();
    }},SEARCH_DEBOUNCE_MS);
  }});
  SB.addEventListener("input",function(){{
    clearTimeout(searchTimers.b);
    searchTimers.b=setTimeout(function(){{
      refreshPlayerB(true);
    }},SEARCH_DEBOUNCE_MS);
  }});
  compare();

  // ---- Team vs Team ----
  // Rosters are derived entirely from data already embedded above
  // (p.team_history) -- no additional server payload, so this carries no
  // extra memory cost for the standalone build. Built once at load, not
  // per keystroke: same responsive-search contract as Player A/B (debounced
  // input, capped rendered options, no expensive work while typing).
  function teamScopeKey(t){{
    return [String(t.team_external_id||t.team_name||""),String(t.division_id||""),String(t.session_name||"")].join("|");
  }}
  function teamDisplay(team){{
    var parts=[team.name];
    if(team.session_name) parts.push(team.session_name);
    if(team.format) parts.push(formatName(team.format));
    if(team.division_id) parts.push("Div "+team.division_id);
    return parts.join(" · ");
  }}
  var TEAM_INDEX=(function(){{
    var idx={{}};
    DATA.players.forEach(function(p){{
      (p.team_history||[]).forEach(function(t){{
        if(!t.is_current||!t.team_name) return;
        var key=teamScopeKey(t);
        if(!idx[key]) idx[key]={{
          key:key,
          name:t.team_name,
          team_external_id:t.team_external_id||"",
          division_id:t.division_id||"",
          session_name:t.session_name||"",
          format:t.format||"",
          seen:{{}},
          players:[]
        }};
        // Team display names are not identities. Same-named teams in
        // different divisions/sessions remain separate roster scopes.
        // Within one exact scope, dedupe repeated history rows by player id.
        if(idx[key].seen[p.id]) return;
        idx[key].seen[p.id]=true;
        var sl=typeof t.skill_level==="number"&&t.skill_level>0?t.skill_level:null;
        idx[key].players.push({{id:p.id,external_id:p.external_id,name:p.name,skill_level:sl,matches_won:t.matches_won,matches_played:t.matches_played}});
      }});
    }});
    return idx;
  }})();
  var TEAM_KEYS=Object.keys(TEAM_INDEX).sort(function(x,y){{return teamDisplay(TEAM_INDEX[x]).localeCompare(teamDisplay(TEAM_INDEX[y]));}});
  var TEAM_SEARCH_NAMES={{}}; TEAM_KEYS.forEach(function(k){{TEAM_SEARCH_NAMES[k]=teamDisplay(TEAM_INDEX[k]).toLowerCase();}});
  var TA=document.getElementById("team-a"),TB=document.getElementById("team-b"),TF=document.getElementById("team-format");
  var STA=document.getElementById("search-team-a"),STB=document.getElementById("search-team-b");
  var SSTA=document.getElementById("search-status-team-a"),SSTB=document.getElementById("search-status-team-b");
  var STANDARD_SKILL_CAP=23;

  function matchingTeams(filter) {{
    var q=String(filter||"").trim().toLowerCase();
    var matches=TEAM_KEYS.filter(function(k){{
      var team=TEAM_INDEX[k];
      var formatMatches=!team.format||team.format===TF.value;
      return formatMatches&&(!q||TEAM_SEARCH_NAMES[k].indexOf(q)!==-1);
    }});
    return {{rows:matches.slice(0,MAX_OPTIONS),total:matches.length}};
  }}
  function teamSelectMarkup(found,previous) {{
    var keep=previous&&found.rows.indexOf(previous)!==-1;
    var placeholder='<option value="">Select a team...</option>';
    var rows=found.rows.map(function(k){{var team=TEAM_INDEX[k];return '<option value="'+esc(k)+'">'+esc(teamDisplay(team))+' · '+team.players.length+' rostered</option>';}}).join("");
    return {{html:placeholder+rows,value:keep?previous:""}};
  }}
  function applyTeamSearch(input,select,status) {{
    var previous=select.value,found=matchingTeams(input.value);
    var rendered=teamSelectMarkup(found,previous);
    select.innerHTML=rendered.html;
    select.value=rendered.value;
    if(found.total>MAX_OPTIONS) {{
      status.textContent="Showing first "+MAX_OPTIONS+" of "+found.total+" matches. Keep typing, then choose a team.";
    }} else if(found.total===0 && matchingTeams("").total===0) {{
      // Zero results even with an empty search term means no CURRENTLY
      // ROSTERED team has this format at all -- not a search-text miss, and
      // not necessarily a bug: a format can have real recorded evidence
      // (reachable from Player A/B scouting) while no team actively plays
      // it right now. Say so plainly instead of leaving an opaque "0
      // matching teams." that reads like a broken selector.
      status.textContent="No currently-rostered team plays "+esc(formatName(TF.value))+" right now.";
    }} else {{
      status.textContent=found.total+" matching team"+(found.total===1?"":"s")+".";
    }}
  }}
  applyTeamSearch(STA,TA,SSTA);
  applyTeamSearch(STB,TB,SSTB);

  function rosterTable(role,team,fmt,side) {{
    var head='<h2 class="roster-head"><span class="role">'+esc(role)+'</span>'+(team?'<span>'+esc(team.name)+'</span>':'')+(side?'<span class="badge side">'+esc(side)+'</span>':'')+'</h2>';
    if(!team) return head+'<p class="muted">Choose a team to load its current roster.</p>';
    var known=team.players.filter(function(m){{return m.skill_level!==null&&m.skill_level!==undefined;}});
    var totalSkill=known.reduce(function(sum,m){{return sum+m.skill_level;}},0);
    var totalNote=known.length===team.players.length
      ? 'full-roster skill total '+totalSkill
      : 'full-roster skill total '+totalSkill+' from '+known.length+' of '+team.players.length+' players with a captured skill level (missing players excluded, not counted as 0)';
    var rows=team.players.slice().sort(function(x,y){{return (y.skill_level||0)-(x.skill_level||0);}}).map(function(m,i){{
      var evid=rowsFor(m.id,fmt).length;
      var slLabel=m.skill_level===null||m.skill_level===undefined?'—':String(m.skill_level);
      var wl=m.matches_won===null||m.matches_won===undefined||m.matches_played===null||m.matches_played===undefined?'—':m.matches_won+'-'+Math.max(0,m.matches_played-m.matches_won);
      return '<tr><td>'+(i+1)+'</td><td>'+esc(m.name)+'</td><td>'+esc(recordIdText(m))+'</td><td>'+slLabel+'</td><td>'+wl+'</td><td>'+evid+'</td></tr>';
    }}).join("");
    // The team-specific summary (including any "from k of n players" missing-SL disclosure) always stays with
    // the roster; the generic cap/asterisk fine print is repeated in the matchup notes, so the focused print
    // hides only this copy of it.
    return head+'<p class="roster-scope">'+esc(teamDisplay(team))+'</p><p class="roster-summary">'+team.players.length+' rostered · '+totalNote+'</p>'+
      '<p class="muted roster-fineprint">Not a 5-player lineup total. This data does not capture your division\\'s skill cap; enter one in Lineup Lab if you want a reference shown.'+
      '</p>'+
      '<div class="table-wrap"><table><thead><tr><th>#</th><th>Player</th><th>APA record ID</th><th>SL (this format)</th><th>Team W-L</th><th>Evidence rows ('+esc(formatName(fmt))+')</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
  }}

  // ---- Match Night evidence: team comparison + ranking ----
  // Mirrors analytics/ultimate_coach_matchup_evidence.py exactly -- same
  // ordering rule, tie handling and texts (a browser test cross-checks the
  // two). Recorded facts only: not win odds, not a guaranteed lineup.
  var OPP_MAP_CACHE={{}};
  function oppMap(pid,fmt){{
    var key=String(pid)+"|"+fmt;
    if(OPP_MAP_CACHE[key]) return OPP_MAP_CACHE[key];
    var m={{}};
    rowsFor(pid,fmt).forEach(function(r){{var id=String(val(r,"opponent_id"));var e=m[id]||(m[id]={{w:0,g:0}});e.g+=1;if(val(r,"result")==="W") e.w+=1;}});
    OPP_MAP_CACHE[key]=m;
    return m;
  }}
  function plural(n,word){{return n+" "+word+(n===1?"":"s");}}
  function wlText(w,g){{return w+"-"+(g-w);}}
  function fmtLabel(fmt){{return FORMAT_LABELS[fmt]||fmt||"this format";}}
  function slText(m){{return m.skill_level===null||m.skill_level===undefined?"—":String(m.skill_level);}}
  function memberOrder(x,y){{
    var xs=x.skill_level,ys=y.skill_level,xn=xs===null||xs===undefined,yn=ys===null||ys===undefined;
    if(xn!==yn) return xn?1:-1;
    if(!xn&&xs!==ys) return ys-xs;
    var a=String(x.name).toLowerCase(),b=String(y.name).toLowerCase();
    if(a!==b) return a<b?-1:1;
    var ea=String(x.external_id===null||x.external_id===undefined?"":x.external_id),eb=String(y.external_id===null||y.external_id===undefined?"":y.external_id);
    return ea<eb?-1:(ea>eb?1:0);
  }}
  function rankKeyCmp(a,b){{
    if(a.tier!==b.tier) return b.tier-a.tier;
    var f=b.rw*a.rg-a.rw*b.rg;
    if(f!==0) return f;
    if(a.n!==b.n) return b.n-a.n;
    if(a.extra!==b.extra) return b.extra-a.extra;
    return 0;
  }}
  function rankVsOpponent(ours,opp,fmt){{
    var om=oppMap(opp.id,fmt),oppTotal=0;
    Object.keys(om).forEach(function(k){{oppTotal+=om[k].g;}});
    var cands=ours.map(function(m){{
      var mm=oppMap(m.id,fmt),d=mm[String(opp.id)];
      var shared=Object.keys(mm).filter(function(k){{return !!om[k];}});
      var ow=0,og=0,tw=0,tg=0;
      shared.forEach(function(k){{ow+=mm[k].w;og+=mm[k].g;tw+=om[k].w;tg+=om[k].g;}});
      var c={{member:m,direct:(d&&d.g>0)?d:null,shared:shared.length,ow:ow,og:og,tw:tw,tg:tg}};
      if(c.direct) {{c.tier=3;c.rw=d.w;c.rg=d.g;c.n=d.g;c.extra=0;}}
      else if(shared.length&&og>0) {{c.tier=2;c.rw=0;c.rg=1;c.n=0;c.extra=0;}}
      else {{c.tier=1;c.rw=0;c.rg=1;c.n=0;c.extra=0;}}
      return c;
    }});
    cands.sort(function(a,b){{var k=rankKeyCmp(a,b);return k!==0?k:memberOrder(a.member,b.member);}});
    var rows=[],i=0,position=0;
    while(i<cands.length){{
      var j=i;
      while(j+1<cands.length&&rankKeyCmp(cands[j+1],cands[i])===0) j++;
      var group=cands.slice(i,j+1);
      position+=group.length;
      var start=position-group.length+1;
      group.forEach(function(c){{
        var ranked=c.tier===3,tied=ranked&&group.length>1;
        var basis=c.tier===3?"Direct record":(c.tier===2?"Shared-opponent results only (no direct meetings) — not ordered against other indirect candidates; compare ours vs theirs":"No direct or shared-opponent evidence");
        if(tied) basis+=" · Tied with "+group.filter(function(o){{return o!==c;}}).map(function(o){{return playerRef(o.member);}}).join(", ")+" — same evidence; the ranking can't separate them";
        rows.push({{
          rank:ranked?(tied?start+"=":String(start)):(c.tier===2?"≈":"—"),
          member:c.member,player:playerRef(c.member),tier:c.tier,c:c,
          direct_text:c.direct?wlText(c.direct.w,c.direct.g)+" ("+plural(c.direct.g,"meeting")+")":"No direct meetings",
          shared_text:c.shared?plural(c.shared,"shared opponent")+" · ours "+wlText(c.ow,c.og)+" ("+plural(c.og,"game")+") · theirs "+wlText(c.tw,c.tg)+" ("+plural(c.tg,"game")+")":"No shared opponents",
          basis:basis
        }});
      }});
      i=j+1;
    }}
    var withEvidence=rows.filter(function(r){{return r.tier!==1;}}).length;
    var note=!ours.length?"Our roster has no current players captured — nothing to rank."
      :(oppTotal===0?"No recorded "+fmtLabel(fmt)+" games for this opponent in the verified evidence — nothing to rank on."
      :withEvidence+" of "+ours.length+" of our players have direct or shared-opponent evidence against this opponent.");
    return {{opponent:opp,opponent_label:playerRef(opp),opponent_sample:plural(oppTotal,"recorded game")+" in "+fmtLabel(fmt),opponent_games:oppTotal,note:note,rows:rows,with_evidence:withEvidence}};
  }}
  function teamComparison(ours,theirs,fmt){{
    function side(members){{
      var known=members.filter(function(m){{return m.skill_level!==null&&m.skill_level!==undefined;}});
      var total=known.reduce(function(sum,m){{return sum+m.skill_level;}},0);
      var games=members.map(function(m){{var om=oppMap(m.id,fmt),g=0;Object.keys(om).forEach(function(k){{g+=om[k].g;}});return g;}});
      return {{rostered:String(members.length),captured_sl:known.length+" of "+members.length,
        sl_total:known.length===members.length?String(total):total+" (from "+known.length+" of "+members.length+")",
        games:String(games.reduce(function(sum,g){{return sum+g;}},0)),
        no_games:String(games.filter(function(g){{return g===0;}}).length)}};
    }}
    var dw=0,dg=0,met={{}},direct=0,sharedOnly=0,none=0;
    ours.forEach(function(m){{
      var mm=oppMap(m.id,fmt);
      theirs.forEach(function(q){{
        var rec=mm[String(q.id)];
        if(rec&&rec.g>0) {{dw+=rec.w;dg+=rec.g;met[String(q.id)]=true;direct++;}}
        else {{var qm=oppMap(q.id,fmt); if(Object.keys(mm).some(function(k){{return !!qm[k];}})) sharedOnly++; else none++;}}
      }});
    }});
    return {{format:fmtLabel(fmt),ours:side(ours),theirs:side(theirs),
      direct_meetings:dg?plural(dg,"game")+" · our players "+wlText(dw,dg):"No direct meetings between these rosters",
      opponents_met:Object.keys(met).length+" of "+theirs.length,
      pairings:direct+" direct · "+sharedOnly+" shared-opponent only · "+none+" no evidence ("+(ours.length*theirs.length)+" total)"}};
  }}
  function evidenceLeader(b){{
    var opp=b.opponent,rows=b.rows;
    if(!rows.length||rows[0].tier===1) return 'No direct or shared-opponent evidence for any of our roster against '+playerRef(opp)+' in this format yet.';
    var top=rows.filter(function(r){{return r.rank===rows[0].rank;}}),c=rows[0].c;
    if(rows[0].tier===3&&top.length>1) return 'Insufficient evidence to distinguish '+top.map(function(r){{return r.player;}}).join(' / ')+' against '+playerRef(opp)+' — '
      +(c.tier===3?'identical direct records ('+wlText(c.rw,c.rg)+', '+plural(c.rg,'meeting')+' each)':'identical shared-opponent evidence ('+plural(c.n,'shared opponent')+', ours '+wlText(c.ow,c.og)+')')+'.';
    if(c.tier===3) return rows[0].player+' — ranks first on direct evidence: '+wlText(c.rw,c.rg)+' direct ('+plural(c.rg,'meeting')+') vs '+playerRef(opp)+'.';
    var ind=rows.filter(function(r){{return r.tier===2;}}).length;
    return 'None of our roster has met '+playerRef(opp)+' directly. '+plural(ind,'player')+(ind===1?' has':' have')+' shared-opponent evidence only — not ranked against each other; compare ours vs theirs in the matrix.';
  }}

{_WAR_ROOM_JS}
  // ---- Matchup header + focused print ----
  // MATCHUP_CONTEXT is set only by Match Day's Compare button and is kept
  // only while both team selectors still hold exactly those roster scopes.
  var MATCHUP_CONTEXT=null;
  function sideLabel(s){{return s==="home"?"Home":(s==="away"?"Away":"");}}
  function fixtureResultText(f){{
    var scored=f.is_scored&&f.home_score!==null&&f.home_score!==undefined&&f.away_score!==null&&f.away_score!==undefined;
    return scored?(f.home_team_name||"Home")+' '+f.home_score+' – '+f.away_score+' '+(f.away_team_name||"Away"):'Not recorded';
  }}
  function renderMatchupHead(ta,tb,fmt) {{
    var head=document.getElementById("matchup-head"),notes=document.getElementById("matchup-notes");
    if(!ta&&!tb) {{ head.innerHTML=""; notes.innerHTML=""; return null; }}
    var ctx=(MATCHUP_CONTEXT&&ta&&tb&&MATCHUP_CONTEXT.ourKey===ta.key&&MATCHUP_CONTEXT.oppKey===tb.key)?MATCHUP_CONTEXT:null;
    if(!ctx) MATCHUP_CONTEXT=null;
    var f=ctx?ctx.fixture:null, tz=(DATA.match_day&&DATA.match_day.display_timezone)||"";
    var oppSide=ctx?(ctx.ourSide==="home"?"away":"home"):"";
    head.innerHTML='<div class="card-head"><h2>Matchup</h2>'+(ta&&tb?'<button type="button" id="print-matchup">Print Captain Packet</button>':'')+'</div>'
      +(ctx?'<p class="matchup-when">'+(f.date_status==="ok"?esc(f.local_display)+' <span class="muted">('+esc(tz)+')</span>':'Undated fixture')+'</p>'
          :'<p class="muted">Teams chosen manually — not tied to a scheduled fixture. Use Match Day → Compare to load a specific fixture with its date and time.</p>')
      +'<div class="matchup-teams">'
      +'<div class="matchup-side"><span class="role">Our team</span><b>'+(ta?esc(teamDisplay(ta)):'Not chosen')+'</b>'+(ctx?'<span class="badge side">'+sideLabel(ctx.ourSide)+'</span>':'')+'</div>'
      +'<div class="matchup-vs">vs</div>'
      +'<div class="matchup-side"><span class="role opp">Opponent</span><b>'+(tb?esc(teamDisplay(tb)):'Not chosen')+'</b>'+(ctx?'<span class="badge side opp">'+sideLabel(oppSide)+'</span>':'')+'</div>'
      +'</div>'
      +(ctx?'<dl class="matchup-facts"><dt>Format</dt><dd>'+esc(f.format_display||f.format_raw||formatName(f.format)||"No data")+'</dd>'
          +'<dt>Session</dt><dd>'+esc(f.session_name||"No data")+'</dd>'
          +'<dt>Venue</dt><dd>'+esc(f.location||"No data")+'</dd>'
          +'<dt>Status</dt><dd>'+esc(f.status||"No data")+'</dd>'
          +'<dt>Result</dt><dd>'+esc(fixtureResultText(f))+'</dd>'
          +'<dt>Source timestamp</dt><dd>'+esc(f.match_date||"No data")+'</dd></dl>':'')
      +'<p class="muted">Evidence counts in the rosters use '+esc(formatName(fmt))+'.</p>';
    notes.innerHTML='<h3>About these rosters</h3><ul>'
      +'<li>— = not captured in the source data.</li>'
      +'<li>SL = the skill level this team scope records for its format (8-Ball and 9-Ball levels differ).</li>'
      +'<li>Skill totals count only players with a captured skill level — missing players are excluded, never counted as 0. Totals are informational, not a lineup-legality check; a cap appears only if you enter one in Lineup Lab.</li>'
      +'<li>Rosters are each team\\'s CURRENT captured roster, not a reconstruction of who actually played on any particular date.</li>'
      +'<li>Players are identified by APA record ID — not by name, and not by the league card number printed on a member card.</li>'
      +'<li>The evidence ranking orders our players by recorded direct and shared-opponent results only; ties and missing evidence are labeled. It is not win odds and not a guaranteed or optimal lineup.</li>'
      +'<li>No win probability is shown: NOT CALIBRATED.</li></ul>'
      +'<p class="muted">'+esc(BUILT_LABEL)+'</p>';
    var btn=document.getElementById("print-matchup");
    if(btn) btn.addEventListener("click",function(){{document.body.classList.add("print-matchup");window.print();}});
    return ctx;
  }}
  window.addEventListener("afterprint",function(){{document.body.classList.remove("print-matchup");}});

  function renderTeamMatchups() {{
    renderTeamMatchupsCore();
    renderWarRoom(TEAM_INDEX[TA.value]||null,TEAM_INDEX[TB.value]||null,TF.value);
  }}
  function renderTeamMatchupsCore() {{
    var ta=TEAM_INDEX[TA.value],tb=TEAM_INDEX[TB.value],fmt=TF.value;
    var ctx=renderMatchupHead(ta,tb,fmt);
    document.getElementById("team-rosters").innerHTML=
      '<div class="card">'+rosterTable("Our team",ta,fmt,ctx?sideLabel(ctx.ourSide):"")+'</div>'+
      '<div class="card">'+rosterTable("Opponent",tb,fmt,ctx?sideLabel(ctx.ourSide==="home"?"away":"home"):"")+'</div>';
    var cmpEl=document.getElementById("team-comparison"),out=document.getElementById("team-matchups");
    if(!ta||!tb) {{
      cmpEl.innerHTML="";
      out.innerHTML='<h2>Evidence ranking vs each opponent</h2><p class="muted">Choose both teams to see the evidence ranking of our players against each opponent player.</p>';
      return;
    }}
    var ours=ta.players.slice().sort(memberOrder),theirs=tb.players.slice().sort(memberOrder);
    var cmp=teamComparison(ours,theirs,fmt);
    cmpEl.innerHTML='<h2>Team comparison</h2><p class="muted">Format: '+esc(cmp.format)+' · recorded facts from identity-verified games — not a prediction.</p>'
      +'<div class="table-wrap"><table class="compare-table"><thead><tr><th></th><th>Our team: '+esc(teamDisplay(ta))+'</th><th>Opponent: '+esc(teamDisplay(tb))+'</th></tr></thead><tbody>'
      +[["Players rostered","rostered"],["Players with a captured SL","captured_sl"],["Skill total (captured SLs only)","sl_total"],
        ["Recorded "+cmp.format+" games (all opponents)","games"],["Players with no recorded "+cmp.format+" games","no_games"]].map(function(r){{
        return '<tr><td>'+esc(r[0])+'</td><td>'+esc(cmp.ours[r[1]])+'</td><td>'+esc(cmp.theirs[r[1]])+'</td></tr>';
      }}).join("")
      +'</tbody></table></div><h3>Between the two rosters</h3><dl class="matchup-facts">'
      +'<dt>Direct meetings between the rosters</dt><dd>'+esc(cmp.direct_meetings)+'</dd>'
      +'<dt>Opponent players our roster has met directly</dt><dd>'+esc(cmp.opponents_met)+'</dd>'
      +'<dt>Player pairings by evidence</dt><dd>'+esc(cmp.pairings)+'</dd></dl>';
    if(!ta.players.length||!tb.players.length) {{
      out.innerHTML='<h2>Evidence ranking vs each opponent</h2><p class="muted">One of these rosters has no current players captured — insufficient roster data to rank.</p>';
      return;
    }}
    var blocks=theirs.map(function(opp){{return rankVsOpponent(ours,opp,fmt);}});
    var glance=blocks.map(function(b){{
      return '<tr><td>'+esc(b.opponent.name)+(b.opponent.skill_level===null||b.opponent.skill_level===undefined?'':' (SL '+b.opponent.skill_level+')')+'<span class="id-line">APA record ID '+esc(recordIdText(b.opponent))+'</span></td><td>'+esc(evidenceLeader(b))+'</td></tr>';
    }}).join("");
    var detail=blocks.map(function(b,bi){{
      return '<div class="rank-block" id="rank-block-'+bi+'"><h3>vs '+esc(b.opponent_label)+' · SL '+esc(slText(b.opponent))+' · '+esc(b.opponent_sample)+'</h3><p class="muted">'+esc(b.note)+'</p>'
        +'<div class="table-wrap"><table class="rank-table"><thead><tr><th>Rank</th><th>Our player (APA record ID)</th><th>SL</th><th>Direct record (meetings)</th><th>Shared-opponent evidence (samples)</th><th>Basis · ties · missing evidence</th></tr></thead><tbody>'
        +b.rows.map(function(r){{return '<tr class="tier-'+r.tier+'"><td>'+esc(r.rank)+'</td><td>'+esc(r.player)+'</td><td>'+esc(slText(r.member))+'</td><td>'+esc(r.direct_text)+'</td><td>'+esc(r.shared_text)+'</td><td>'+esc(r.basis)+'</td></tr>';}}).join("")
        +'</tbody></table></div></div>';
    }}).join("");
    out.innerHTML='<h2>Evidence ranking vs each opponent</h2>'
      +'<p class="note warn-note">Captain assistance only — this orders our players by recorded evidence. It is not a win probability (none is calibrated or published; probability_publication stays FORBIDDEN) and not a guaranteed or optimal lineup. Small samples are noisy. A direct record ranks ahead of shared-opponent results even when it is small or a loss — read the records and sample sizes, not just the rank.</p>'
      +'<p class="muted">Order: direct meetings first (by observed direct record, then more meetings); then shared-opponent results (by our player\\'s record against opponents both players have faced, then more shared opponents, then more games); players with no evidence are listed last and not ranked (—). “2=” marks a tie the evidence can\\'t separate — the Basis column names who is tied.</p>'
      +'<h3>At a glance</h3><div class="table-wrap"><table><thead><tr><th>Opponent player</th><th>First in the evidence ranking (and why)</th></tr></thead><tbody>'+glance+'</tbody></table></div>'
      +'<div class="rank-blocks">'+detail+'</div>';
  }}
  renderTeamMatchups();

  TA.addEventListener("change",renderTeamMatchups);
  TB.addEventListener("change",renderTeamMatchups);
  TF.addEventListener("change",function(){{
    applyTeamSearch(STA,TA,SSTA);
    applyTeamSearch(STB,TB,SSTB);
    renderTeamMatchups();
  }});
  var teamSearchTimers={{a:null,b:null}};
  STA.addEventListener("input",function(){{
    clearTimeout(teamSearchTimers.a);
    teamSearchTimers.a=setTimeout(function(){{applyTeamSearch(STA,TA,SSTA);}},SEARCH_DEBOUNCE_MS);
  }});
  STB.addEventListener("input",function(){{
    clearTimeout(teamSearchTimers.b);
    teamSearchTimers.b=setTimeout(function(){{applyTeamSearch(STB,TB,SSTB);}},SEARCH_DEBOUNCE_MS);
  }});

  // ---- Match Day ----
  // Every date/time below was derived ONCE in Python, in the disclosed
  // display timezone (analytics.ultimate_coach_match_day) -- this script
  // never converts timestamps itself, so it can't drift into the viewer's
  // browser timezone or disagree with the Excel companion. "Me" is an
  // explicit choice of a verified player (APA record ID), defaulting to the
  // build's configured identity -- never inferred from a name.
  var MD=DATA.match_day||{{fixtures:[],schedule:{{}},coverage:{{}}}};
  var FIXTURES=MD.fixtures||[], SCHEDULE=MD.schedule||{{}};
  var VIEWER=DATA.viewer||{{configured:false,resolved:false,teams:[]}};
  var MD_DATE=document.getElementById("md-date"),MD_TEAM=document.getElementById("md-team"),MD_FORMAT=document.getElementById("md-format");
  var MD_STATUS=document.getElementById("md-status"),MD_FIXTURES_EL=document.getElementById("md-fixtures");
  var MD_DATES_EL=document.getElementById("md-team-dates");
  var MDV=document.getElementById("md-viewer"),MDVS=document.getElementById("md-viewer-search"),MDVST=document.getElementById("md-viewer-status");
  var ALL_MY_TEAMS="__all__";
  var VIEWER_STORE_KEY="ultimate-coach:match-day-viewer";
  var WEEKDAYS=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  var MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function storeGet(){{try{{return window.localStorage.getItem(VIEWER_STORE_KEY);}}catch(e){{return null;}}}}
  function storeSet(v){{try{{if(v) window.localStorage.setItem(VIEWER_STORE_KEY,v); else window.localStorage.removeItem(VIEWER_STORE_KEY);}}catch(e){{}}}}
  function shortDateLabel(iso){{var full=isoDateLabel(iso);return /^[A-Z][a-z]+ /.test(full)?full.slice(0,3)+full.slice(full.indexOf(" ")):full;}}
  function isoDateLabel(iso){{
    var m=/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/.exec(String(iso||""));
    if(!m) return String(iso||"");
    var day=new Date(Date.UTC(+m[1],+m[2]-1,+m[3])).getUTCDay();
    return WEEKDAYS[day]+" "+MONTHS[+m[2]-1]+" "+(+m[3])+", "+m[1];
  }}
  var NAME_COUNTS={{}};
  DATA.players.forEach(function(p){{var k=String(p.name||"").toLowerCase();NAME_COUNTS[k]=(NAME_COUNTS[k]||0)+1;}});
  function currentScopes(p){{
    var seen={{}},out=[];
    (p&&p.team_history||[]).forEach(function(t){{
      if(!t.is_current||!t.team_external_id) return;
      var key=teamScopeKey(t);
      if(seen[key]) return;
      seen[key]=true;
      out.push({{key:key,team_external_id:String(t.team_external_id),session_name:String(t.session_name||""),team_name:t.team_name||"",
        display:teamDisplay({{name:t.team_name,session_name:t.session_name,format:t.format,division_id:t.division_id}})}});
    }});
    out.sort(function(x,y){{return x.display.localeCompare(y.display);}});
    return out;
  }}
  function viewerOptionLabel(p){{
    var names={{}};
    currentScopes(p).forEach(function(s){{names[s.team_name]=true;}});
    var teamNames=Object.keys(names);
    var dupes=NAME_COUNTS[String(p.name||"").toLowerCase()]||1;
    return p.name+" · APA record ID "+p.external_id+" · "+(teamNames.length?teamNames.join(", "):"no current team")+(dupes>1?" · "+dupes+" players share this name":"");
  }}
  var VIEWER_SEARCH={{}};
  SORTED.forEach(function(p){{VIEWER_SEARCH[String(p.id)]=(p.name+" "+p.external_id).toLowerCase();}});
  var mdViewerId=(function(){{
    var stored=storeGet();
    if(stored&&PLAYERS[stored]) return {{id:stored,source:"saved"}};
    if(VIEWER.resolved&&VIEWER.player_id!==null&&PLAYERS[String(VIEWER.player_id)]) return {{id:String(VIEWER.player_id),source:"config"}};
    return {{id:"",source:""}};
  }})();
  function renderViewerOptions(){{
    var q=String(MDVS.value||"").trim().toLowerCase();
    var matches=SORTED.filter(function(p){{return !q||VIEWER_SEARCH[String(p.id)].indexOf(q)!==-1;}});
    var rows=matches.slice(0,MAX_OPTIONS);
    var current=mdViewerId.id&&PLAYERS[mdViewerId.id];
    if(current&&rows.indexOf(current)===-1) rows=[current].concat(rows);
    MDV.innerHTML='<option value="">Choose yourself...</option>'+rows.map(function(p){{return '<option value="'+esc(p.id)+'">'+esc(viewerOptionLabel(p))+'</option>';}}).join("");
    MDV.value=mdViewerId.id||"";
    return matches.length;
  }}
  function viewerScopes(){{return mdViewerId.id?currentScopes(PLAYERS[mdViewerId.id]):[];}}
  function renderViewerStatus(totalMatches){{
    var p=mdViewerId.id&&PLAYERS[mdViewerId.id];
    var searchNote=String(MDVS.value||"").trim()?(" "+totalMatches+" matching player"+(totalMatches===1?"":"s")+(totalMatches>MAX_OPTIONS?" (showing first "+MAX_OPTIONS+")":"")+"."):"";
    if(!p) {{
      if(VIEWER.configured&&!VIEWER.resolved) {{
        MDVST.textContent="The configured viewer identity (APA record ID "+(VIEWER.external_id||"")+") was not found among this build's verified players. Search for yourself above."+searchNote;
      }} else {{
        MDVST.textContent="No viewer identity configured. Search your name or APA record ID above and choose yourself — same-name players are told apart by record ID and current teams. Nothing is guessed."+searchNote;
      }}
      return;
    }}
    var scopes=viewerScopes();
    var src=mdViewerId.source==="config"?"default from this build's configuration":(mdViewerId.source==="saved"?"your saved choice on this device":"your choice");
    var card=(String(p.external_id)===String(VIEWER.external_id||"")&&VIEWER.card_number)?" League card #"+VIEWER.card_number+" was verified to this record when the build was configured (card numbers are per league and are not used as identity).":"";
    MDVST.innerHTML='Match Day for <strong>'+esc(p.name)+'</strong> · APA record ID '+esc(p.external_id)+' ('+esc(src)+').'+esc(card)+' '
      +(scopes.length?scopes.length+' current team scope'+(scopes.length===1?'':'s')+': '+scopes.map(function(s){{return '<span class="tag">'+esc(s.display)+'</span>';}}).join(''):'No current team captured for this player.')
      +esc(searchNote);
  }}
  function renderTeamOptions(){{
    var scopes=viewerScopes(), previous=MD_TEAM.value;
    if(!mdViewerId.id||!scopes.length) {{
      MD_TEAM.innerHTML="";
      MD_TEAM.disabled=true;
      return;
    }}
    MD_TEAM.disabled=false;
    MD_TEAM.innerHTML=(scopes.length>1?'<option value="'+ALL_MY_TEAMS+'">All my current teams ('+scopes.length+')</option>':'')
      +scopes.map(function(s){{return '<option value="'+esc(s.key)+'">'+esc(s.display)+'</option>';}}).join("");
    var keep=previous&&(previous===ALL_MY_TEAMS&&scopes.length>1||scopes.some(function(s){{return s.key===previous;}}));
    MD_TEAM.value=keep?previous:defaultTeamKey(scopes);
  }}
  // Same rule as analytics.ultimate_coach_war_room.default_matchup (the Excel default): the team
  // of the viewer's next 8-Ball/9-Ball fixture on or after the build date -- earliest date, then
  // kickoff, then team label. Otherwise one team, or all teams to browse.
  function defaultTeamKey(scopes){{
    var best=null,b=(DATA.build||{{}}).build_local||"";
    scopes.forEach(function(s){{
      (SCHEDULE[s.key]||[]).forEach(function(side){{
        var f=FIXTURES[side.fixture_index];
        if(!f||(f.format!=="EIGHT"&&f.format!=="NINE")||!f.local_date||(b&&f.local_date<b)) return;
        var k=[f.local_date,f.local_sort||"",s.display];
        if(!best||k[0]<best.k[0]||(k[0]===best.k[0]&&(k[1]<best.k[1]||(k[1]===best.k[1]&&k[2]<best.k[2])))) best={{k:k,key:s.key}};
      }});
    }});
    return best?best.key:(scopes.length>1?ALL_MY_TEAMS:scopes[0].key);
  }}
  function selectedScopes(){{
    var scopes=viewerScopes();
    if(MD_TEAM.value===ALL_MY_TEAMS) return scopes;
    return scopes.filter(function(s){{return s.key===MD_TEAM.value;}});
  }}
  function formatFilterMatches(f){{
    var v=MD_FORMAT.value;
    if(v==="*") return true;
    if(v==="") return f.format==="EIGHT"||f.format==="NINE";
    return String(f.format_raw||"")===v;
  }}
  function formatFilterLabel(){{var o=MD_FORMAT.options[MD_FORMAT.selectedIndex];return o?o.text:"";}}
  function sidesFor(scopes){{
    var out=[];
    scopes.forEach(function(s){{
      (SCHEDULE[s.key]||[]).forEach(function(side){{
        var f=FIXTURES[side.fixture_index];
        if(f&&formatFilterMatches(f)) out.push({{scope:s,side:side,fixture:f}});
      }});
    }});
    out.sort(function(x,y){{return String(x.fixture.local_sort||"~").localeCompare(String(y.fixture.local_sort||"~"));}});
    return out;
  }}
  function opponentText(side){{
    var o=side.opponent||{{}};
    if(o.status==="bye") return "Bye — no opponent";
    return o.team_name||"No data";
  }}
  function rosterStatusNote(side){{
    var o=side.opponent||{{}};
    if(o.status==="resolved") return "";
    if(o.status==="bye") return '<p class="muted">Bye week — a real schedule slot with no opponent, not missing data. There is no opponent roster to compare.</p>';
    if(o.status==="ambiguous") return '<p class="note warn-note">Opponent roster is ambiguous: '+o.candidate_scope_keys.length+' current roster scopes share this team ID and session ('+o.candidate_scope_keys.map(function(k){{return esc(TEAM_INDEX[k]?teamDisplay(TEAM_INDEX[k]):k);}}).join(" / ")+'). None is picked automatically — compare manually in Team vs Team below.</p>';
    if(o.status==="missing") return '<p class="note warn-note">The source records no opponent team for this fixture, so there is no roster to compare.</p>';
    return '<p class="note warn-note">No current roster is captured for '+esc(o.team_name||"this opponent")+' in this build, so a roster comparison is not available for this matchup.</p>';
  }}
  function mdFixtureCard(item,i,showTeam){{
    var f=item.fixture, side=item.side, isBye=(side.opponent||{{}}).status==="bye";
    var when=f.date_status==="ok"?esc(f.local_display)
      :(f.date_status==="unparseable"?'Unparseable date: '+esc(f.match_date||""):'No date recorded');
    var scored=f.is_scored&&f.home_score!==null&&f.home_score!==undefined&&f.away_score!==null&&f.away_score!==undefined;
    var result=scored?(esc(f.home_team_name||"Home")+' '+f.home_score+' – '+f.away_score+' '+esc(f.away_team_name||"Away")):'Not recorded';
    var badges='<span class="badge side">'+(side.side==="home"?"Home":"Away")+'</span>'
      +'<span class="badge">'+esc(f.format_display||f.format_raw||formatName(f.format)||"Format: No data")+'</span>'
      +'<span class="badge">'+esc(f.session_name||"Session: No data")+'</span>'
      +'<span class="badge">'+esc(f.status||"Status: No data")+'</span>'
      +(f.week!==null&&f.week!==undefined?'<span class="badge">Week '+esc(f.week)+'</span>':'');
    var body='<div class="fixture-when">'+when+'</div>'
      +'<div class="fixture-vs">'+(showTeam?'<b>'+esc(item.scope.display)+'</b> ':'<b>'+esc(item.scope.team_name)+'</b> ')
      +(isBye?'— <b>Bye — no opponent</b>':(side.side==="home"?'(home) vs ':'(away) at ')+'<b>'+esc(opponentText(side))+'</b>')+'</div>'
      +'<div class="badges">'+badges+'</div>'
      +'<dl><dt>Kickoff</dt><dd>'+(f.date_status==="ok"?esc(f.local_time)+' '+esc(f.local_tz_abbrev)+' ('+esc(MD.display_timezone||"")+', UTC'+esc(f.local_utc_offset)+')':'No data')+'</dd>'
      +'<dt>Source timestamp</dt><dd>'+esc(f.match_date||"No data")+'</dd>'
      +'<dt>Venue</dt><dd>'+esc(f.location||"No data")+'</dd>'
      +'<dt>Result</dt><dd>'+result+'</dd>'
      +'<dt>Opponent roster</dt><dd>'+(isBye?'Not applicable (bye)':((side.opponent||{{}}).status==="resolved"?'Current roster captured':'Not available — see note'))+'</dd></dl>'
      +(side.own_scope_ambiguous?'<p class="note warn-note">This team ID and session are rostered in more than one division and the fixture names no division, so this fixture is listed under each of them.</p>':'')
      +rosterStatusNote(side)
      +(!isBye&&(side.opponent||{{}}).status==="resolved"?'<button type="button" id="md-compare-'+i+'">Compare rosters &amp; evidence for this matchup</button>':'');
    return '<div class="fixture'+(isBye?' bye':'')+'">'+body+'</div>';
  }}
  function forceSelectTeam(select,key) {{
    var team=TEAM_INDEX[key];
    if(!team) return false;
    select.innerHTML='<option value="'+esc(key)+'">'+esc(teamDisplay(team))+' · '+team.players.length+' rostered</option>';
    select.value=key;
    return true;
  }}
  // Match Day's selection has no single fixture with an opponent roster: drop the followed matchup
  // entirely (teams, fixture context, print/planning context) and say why in the Tonight panel, so an
  // earlier fixture can never stay on screen as if it were tonight's (GPT audit #84, Paul's HTML UAT).
  function mdNoFixture(when,text) {{
    MATCHUP_CONTEXT=null;
    WR_TONIGHT_NOTE={{when:when||"",text:text}};
    STA.value=""; STB.value="";
    applyTeamSearch(STA,TA,SSTA); TA.value="";
    applyTeamSearch(STB,TB,SSTB); TB.value="";
    renderTeamMatchups();
  }}
  function mdApplyFixture(item,auto) {{
    WR_TONIGHT_NOTE=null;
    STA.value="";
    STB.value="";
    forceSelectTeam(TA,item.scope.key);
    var fmt=item.fixture.format||"";
    if(fmt&&!Array.prototype.some.call(TF.options,function(o){{return o.value===fmt;}})) {{
      var opt=document.createElement("option"); opt.value=fmt; opt.textContent=formatName(fmt); TF.appendChild(opt);
    }}
    if(fmt) TF.value=fmt;
    forceSelectTeam(TB,item.side.opponent.scope_key);
    MATCHUP_CONTEXT={{fixture:item.fixture,ourKey:item.scope.key,oppKey:item.side.opponent.scope_key,ourSide:item.side.side}};
    var fromMatchDay="Loaded from Match Day ("+(item.fixture.local_display||"undated fixture")+"). Search to pick a different team.";
    SSTA.textContent=fromMatchDay;
    SSTB.textContent=fromMatchDay;
    renderTeamMatchups();
    if(!auto) document.getElementById("matchup-print").scrollIntoView({{behavior:"smooth"}});
  }}
  var MD_DATE_LIST=document.getElementById("md-date-list");
  var BUILD=DATA.build||{{}};
  function scheduledDates(scopes){{
    var dates={{}};
    sidesFor(scopes).forEach(function(it){{if(it.fixture.local_date) dates[it.fixture.local_date]=true;}});
    return Object.keys(dates).sort();
  }}
  function suggestedDate(list){{
    if(!BUILD.build_local) return "";
    for(var i=0;i<list.length;i++) if(list[i]>=BUILD.build_local) return list[i];
    return "";
  }}
  function renderDateList(scopes){{
    var list=scheduledDates(scopes),sugg=suggestedDate(list);
    MD_DATE_LIST.innerHTML='<option value="">'+(list.length?'Choose a scheduled date…':'No scheduled dates captured')+'</option>'
      +list.map(function(d){{return '<option value="'+d+'">'+esc(isoDateLabel(d))+(d===sugg?' · suggested (next on or after the build date)':(BUILD.build_local&&d<BUILD.build_local?' · before the build date':''))+'</option>';}}).join("");
    MD_DATE_LIST.disabled=!list.length;
    MD_DATE_LIST.value=list.indexOf(MD_DATE.value)!==-1?MD_DATE.value:"";
    return {{list:list,sugg:sugg}};
  }}
  function renderDateChips(scopes){{
    var list=scheduledDates(scopes);
    if(!list.length) {{ MD_DATES_EL.innerHTML=""; return; }}
    MD_DATES_EL.innerHTML='<span class="muted" style="align-self:center;">Scheduled dates ('+list.length+'):</span>'+list.map(function(d){{
      return '<button type="button" class="chip" data-date="'+d+'" aria-pressed="'+(d===MD_DATE.value?'true':'false')+'">'+esc(isoDateLabel(d).replace(/^(\\w{{3}})\\w*/,"$1"))+'</button>';
    }}).join("");
  }}
  function renderMatchDay() {{
    var totalMatches=renderViewerOptions();
    renderViewerStatus(totalMatches);
    renderTeamOptions();
    var scopes=selectedScopes();
    if(!mdViewerId.id) {{
      MD_STATUS.textContent=VIEWER.configured&&!VIEWER.resolved
        ? "The configured viewer identity was not found among this build's verified players. Choose yourself in “I am” above."
        : "No viewer identity configured. Choose yourself in “I am” above to see your teams' schedule.";
      MD_FIXTURES_EL.innerHTML=""; MD_DATES_EL.innerHTML="";
      mdNoFixture("",MD_STATUS.textContent);
      return;
    }}
    if(!scopes.length) {{
      MD_STATUS.textContent=viewerScopes().length?"Choose one of your teams.":"No current team found for "+PLAYERS[mdViewerId.id].name+".";
      MD_FIXTURES_EL.innerHTML=""; MD_DATES_EL.innerHTML="";
      mdNoFixture("",MD_STATUS.textContent);
      return;
    }}
    var dl=renderDateList(scopes);
    var dateNote="";
    if(MD_DATE.value&&dl.list.indexOf(MD_DATE.value)===-1&&dl.list.length&&MD_AUTO_DATE) {{
      dateNote=isoDateLabel(MD_DATE.value)+" has no fixture for this team and format — ";
      MD_DATE.value="";
    }}
    if(!MD_DATE.value&&dl.sugg&&MD_AUTO_DATE) {{
      MD_DATE.value=dl.sugg;
      dateNote+="Suggested: the earliest scheduled date on or after the build date. ";
    }} else if(dateNote) {{ dateNote+="choose a date. "; }}
    MD_DATE_LIST.value=dl.list.indexOf(MD_DATE.value)!==-1?MD_DATE.value:"";
    renderDateChips(scopes);
    var teamText=scopes.length>1?"all "+scopes.length+" of your current teams":scopes[0].display;
    var undated=sidesFor(scopes).filter(function(it){{return it.fixture.date_status!=="ok";}});
    var undatedNote=undated.length?" "+undated.length+" fixture"+(undated.length===1?" has":"s have")+" a missing or unparseable date and can't be placed on a calendar day.":"";
    var localDate=MD_DATE.value;
    if(!localDate) {{
      MD_STATUS.textContent="Choose a date to see "+teamText+"'s scheduled matches"+(MD_DATES_EL.innerHTML?", or tap a scheduled date below the pickers.":".")+undatedNote;
      MD_FIXTURES_EL.innerHTML="";
      mdNoFixture("","Choose a date on Match Day.");
      return;
    }}
    var found=sidesFor(scopes).filter(function(it){{return it.fixture.local_date===localDate;}});
    if(!found.length) {{
      MD_STATUS.textContent="No scheduled match found for "+teamText+" on "+isoDateLabel(localDate)+" ("+formatFilterLabel()+")."+undatedNote;
      MD_FIXTURES_EL.innerHTML="";
      mdNoFixture(shortDateLabel(localDate),"No scheduled match for "+teamText+" on this date ("+formatFilterLabel()+").");
      return;
    }}
    MD_STATUS.textContent=dateNote+found.length+" scheduled match"+(found.length===1?"":"es")+" found for "+teamText+" on "+isoDateLabel(localDate)+" ("+formatFilterLabel()+"). "+(found.length>1?"All are listed — none is applied automatically; choose which one to compare.":"Choose Compare to load both rosters.");
    MD_FIXTURES_EL.innerHTML=found.map(function(it,i){{return mdFixtureCard(it,i,scopes.length>1);}}).join("");
    found.forEach(function(it,i){{
      var btn=document.getElementById("md-compare-"+i);
      if(btn) btn.addEventListener("click",function(){{mdApplyFixture(it);}});
    }});
    // Exactly one fixture with a rostered opponent: the War Room follows it automatically
    // (several fixtures are never chosen for you).
    if(found.length===1&&(found[0].side.opponent||{{}}).status==="resolved") {{
      mdApplyFixture(found[0],true);
      MD_STATUS.textContent+=" The War Room below now follows this fixture.";
    }} else if(found.length>1) {{
      mdNoFixture(shortDateLabel(localDate),found.length+" fixtures on this date — choose one on Match Day (none is chosen for you).");
    }} else {{
      var f1=found[0].fixture,o1=found[0].side.opponent||{{}};
      var when1=f1.date_status==="ok"?f1.local_display:shortDateLabel(localDate);
      mdNoFixture(when1,o1.status==="bye"?"Bye — no opponent this week. Nothing to plan for this date."
        :"vs "+(o1.team_name||"an opponent the source does not name")+" — no current opponent roster is captured, so there is nothing to compare or plan.");
    }}
  }}
  MD_DATES_EL.addEventListener("click",function(e){{
    var t=e.target&&e.target.closest?e.target.closest("button[data-date]"):null;
    if(!t) return;
    MD_DATE.value=t.getAttribute("data-date");
    renderMatchDay();
  }});
  MDV.addEventListener("change",function(){{
    mdViewerId={{id:MDV.value||"",source:MDV.value?"chosen":""}};
    storeSet(MDV.value||"");
    MD_TEAM.value="";
    renderMatchDay();
  }});
  var viewerSearchTimer=null;
  MDVS.addEventListener("input",function(){{
    clearTimeout(viewerSearchTimer);
    viewerSearchTimer=setTimeout(function(){{renderViewerStatus(renderViewerOptions());}},SEARCH_DEBOUNCE_MS);
  }});
  var MD_AUTO_DATE=true;
  MD_DATE.addEventListener("change",function(){{MD_AUTO_DATE=false;renderMatchDay();MD_AUTO_DATE=true;}});
  MD_DATE.addEventListener("input",function(){{MD_AUTO_DATE=false;renderMatchDay();MD_AUTO_DATE=true;}});
  MD_DATE_LIST.addEventListener("change",function(){{if(MD_DATE_LIST.value){{MD_DATE.value=MD_DATE_LIST.value;MD_AUTO_DATE=false;renderMatchDay();MD_AUTO_DATE=true;}}}});
  MD_TEAM.addEventListener("change",renderMatchDay);
  MD_FORMAT.addEventListener("change",renderMatchDay);
  renderMatchDay();
}})();
</script></body></html>"""
