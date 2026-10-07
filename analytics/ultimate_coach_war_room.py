"""Captain's War Room: everything for ONE fixture, built around one question --
who do I put up next? -- from recorded, identity-verified facts only.

Builds on analytics.ultimate_coach_matchup_evidence (the reviewed ranking
rule: direct meetings first, then shared-opponent results, ties shown) and
adds, for one directed team pairing (our roster vs theirs, one format):

* an evidence CATEGORY for every pairing of our player vs their player,
* best-supported sends per opponent player,
* concerning pairings, and opponents with winning records vs our roster,
* an opponent scouting card per opponent player,
* every recorded direct meeting between the two rosters.

Evidence category rule -- no tuned thresholds or weights; only the sign of a
recorded direct record, and whether any evidence exists at all:

    G  Favorable direct record   more direct wins than losses
    R  Concerning direct record  more direct losses than wins
    E  Even direct record        as many direct wins as losses
    I  Indirect evidence only    no direct meetings; shared opponents exist
    X  Insufficient evidence     neither

Shown as green / red / yellow / yellow / gray, always next to the sample
size. A category is not a probability, a prediction or a guarantee: a 1-0
record is "favorable" and visibly based on one meeting.

"Best-supported sends" keep the reviewed ranking order and only drop
pairings whose evidence is concerning (R) or missing (X) -- so favorable
direct records come first, then even direct records, then indirect-only
evidence. Nothing is re-scored or blended.

No meetings with our roster is never read as a weak opponent; it is listed
as unknown. Availability / used marks are the captain's inputs and are
applied by the artifacts, never written into evidence.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from analytics.ultimate_coach_match_day import EIGHT_NINE_CATEGORIES, excel_date_serial, localize_match_date
from analytics.ultimate_coach_matchup_evidence import (
    format_label,
    matchup_evidence,
    member_order_key,
    player_ref,
    plural,
    record_text,
)

CATEGORY_LABELS = {
    "G": "Favorable direct record",
    "R": "Concerning direct record",
    "E": "Even direct record",
    "I": "Indirect evidence only",
    "X": "Insufficient evidence",
}
CATEGORY_COLOR = {"G": "green", "R": "red", "E": "yellow", "I": "yellow", "X": "gray"}
SENDABLE = ("G", "E", "I")

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def date_label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{_WEEKDAYS[d.weekday()][:3]} {_MONTHS[d.month - 1]} {d.day}, {d.year}"


# ---- pairing evidence ----

def category(row: dict[str, Any]) -> str:
    direct = row.get("direct")
    if direct:
        wins, games = direct
        losses = games - wins
        return "G" if wins > losses else "R" if wins < losses else "E"
    return "I" if row.get("shared_count") else "X"


def cell_text(row: dict[str, Any]) -> str:
    """Short matrix-cell text; the category color and legend carry the rest."""
    direct = row.get("direct")
    if direct:
        return f"{record_text(*direct)} ({direct[1]})"
    if row.get("shared_count"):
        (ow, og), (tw, tg) = row["ours"], row["theirs"]
        return f"≈ {record_text(ow, og)} vs {record_text(tw, tg)} ({row['shared_count']} shared)"
    return "No evidence"


def explanation(row: dict[str, Any]) -> str:
    """Which records support the pairing, how many observations, direct or indirect."""
    direct = row.get("direct")
    parts = [f"Direct: {record_text(*direct)} in {plural(direct[1], 'meeting')}" if direct else "No direct meetings"]
    if row.get("shared_count"):
        (ow, og), (tw, tg) = row["ours"], row["theirs"]
        parts.append(f"Indirect: {plural(row['shared_count'], 'shared opponent')} — ours {record_text(ow, og)} "
                     f"({plural(og, 'game')}), theirs {record_text(tw, tg)} ({plural(tg, 'game')})")
    else:
        parts.append("no shared opponents")
    return " · ".join(parts)


# ---- evidence indexes beyond the Player vs Player pairs ----

def sl_bucket_index(evidence: Iterable[dict[str, Any]], player_ids: set[Any]) -> dict[tuple[Any, str], dict[Any, list[int]]]:
    """(player, format) -> {opponent SL: [wins, games]} for the given players."""
    index: dict[tuple[Any, str], dict[Any, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for row in evidence:
        pid = row.get("player_id")
        if pid not in player_ids:
            continue
        sl = row.get("opponent_skill_level")
        bucket = index[(pid, row.get("format") or "")][sl if isinstance(sl, (int, float)) and sl > 0 else None]
        bucket[1] += 1
        if row.get("result") == "W":
            bucket[0] += 1
    return index


def meetings_index(evidence: Iterable[dict[str, Any]], player_ids: set[Any],
                   display_timezone: str) -> dict[tuple[Any, Any, str], list[dict[str, Any]]]:
    """(player, opponent, format) -> recorded games, newest first, between current-roster players."""
    index: dict[tuple[Any, Any, str], list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        pid, opp = row.get("player_id"), row.get("opponent_id")
        if pid not in player_ids or opp not in player_ids:
            continue
        local = localize_match_date(row.get("match_date"), display_timezone)
        index[(pid, opp, row.get("format") or "")].append({
            "sort": local["local_sort"] or "",
            "date": date_label(local["local_date"]) if local["local_date"] else "No data",
            "session": row.get("session_name") or "No data",
            "result": row.get("result") or "No data",
            "own_sl": row.get("own_skill_level"),
            "opp_sl": row.get("opponent_skill_level"),
            "points": row.get("points_earned"),
        })
    for games in index.values():
        games.sort(key=lambda g: g["sort"], reverse=True)
    return index


def _sl_text(sl: Any) -> str:
    return "No data" if sl is None else str(sl)


def _bucket_summary(buckets: dict[Any, list[int]]) -> tuple[str, str, str]:
    known = sorted((sl, rec) for sl, rec in buckets.items() if sl is not None)
    if not known:
        return "No opponent skill levels recorded", "—", "—"
    by_sl = " · ".join(f"vs SL{int(sl)} {record_text(w, g)}" for sl, (w, g) in known)
    winning = [f"SL{int(sl)} ({record_text(w, g)})" for sl, (w, g) in known if w > g - w]
    losing = [f"SL{int(sl)} ({record_text(w, g)})" for sl, (w, g) in known if w < g - w]
    return by_sl, ", ".join(winning) or "None recorded", ", ".join(losing) or "None recorded"


def _complete_count(row: dict[str, Any]) -> tuple[int, int] | None:
    """(wins, played) only when BOTH are recorded and consistent; never zero-fill a missing count."""
    won, played = row.get("matches_won"), row.get("matches_played")
    if isinstance(won, bool) or isinstance(played, bool) or not isinstance(won, int) or not isinstance(played, int):
        return None
    return (won, played) if 0 <= won <= played else None


def _career_text(player: dict[str, Any] | None, fmt: str) -> str:
    """League-scoped lifetime record from complete scopes only (GPT audit #84): a scope with
    missing wins or games is disclosed and left out -- unknown wins never become losses."""
    rows = [r for r in (player or {}).get("career_stats") or [] if r.get("format") == fmt]
    if not rows:
        return "No career stats captured"
    complete = [c for c in (_complete_count(r) for r in rows) if c is not None]
    incomplete = len(rows) - len(complete)
    won, played = sum(c[0] for c in complete), sum(c[1] for c in complete)
    gap = f"{plural(incomplete, 'league scope')} with missing wins or games not counted" if incomplete else ""
    if not played:
        return f"No complete career record captured ({gap})" if incomplete else "No career games recorded"
    return f"{record_text(won, played)} (league-scoped lifetime {format_label(fmt)}" + (f"; {gap})" if gap else ")")


# ---- the War Room for one directed pairing ----

def war_room_pair(
    our_members: list[dict[str, Any]],
    opp_members: list[dict[str, Any]],
    pair_index: Any,
    fmt: str,
    *,
    sl_index: dict[tuple[Any, str], dict[Any, list[int]]] | None = None,
    meetings: dict[tuple[Any, Any, str], list[dict[str, Any]]] | None = None,
    players_by_id: dict[Any, dict[str, Any]] | None = None,
    session_name: str = "",
) -> dict[str, Any]:
    sl_index = sl_index or {}
    meetings = meetings or {}
    players_by_id = players_by_id or {}
    evidence = matchup_evidence(our_members, opp_members, pair_index, fmt)
    ours = sorted(our_members, key=member_order_key)
    theirs = sorted(opp_members, key=member_order_key)

    # Annotate every ranked row with its category and texts.
    for block in evidence["opponents"]:
        for position, row in enumerate(block["rows"], start=1):
            row["category"] = category(row)
            row["cell"] = cell_text(row)
            row["explanation"] = explanation(row)
            row["position"] = position

    matrix = []
    for member in ours:
        cells = []
        for block in evidence["opponents"]:
            row = next(r for r in block["rows"] if r["member"]["id"] == member["id"])
            cells.append(row)
        matrix.append({"member": member, "cells": cells})

    best_sends = []
    for block in evidence["opponents"]:
        best_sends.append([r for r in block["rows"] if r["category"] in SENDABLE])

    concerning = []
    for j, block in enumerate(evidence["opponents"]):
        for row in block["rows"]:
            if row["category"] == "R":
                wins, games = row["direct"]
                concerning.append({"our": row["member"], "opp": block["opponent"], "direct": row["direct"],
                                   "text": f"{row['player']} vs {block['opponent_label']}: {record_text(wins, games)} "
                                           f"direct ({plural(games, 'meeting')})",
                                   "_key": (-(games - 2 * wins), -games, member_order_key(row["member"]), j)})
    concerning.sort(key=lambda c: c["_key"])

    cards = []
    for block in evidence["opponents"]:
        opp = block["opponent"]
        # Roster order (not ranking order): the card describes the opponent, it doesn't rank our players.
        met = sorted((r for r in block["rows"] if r["direct"]), key=lambda r: member_order_key(r["member"]))
        their_wins = sum(r["direct"][1] - r["direct"][0] for r in met)
        their_games = sum(r["direct"][1] for r in met)
        if their_games:
            vs_ours = (f"{record_text(their_wins, their_games)} in {plural(their_games, 'meeting')} with "
                       f"{len(met)} of our {len(ours)} players")
            met_list = " · ".join(f"vs {r['player']}: {record_text(r['direct'][1] - r['direct'][0], r['direct'][1])}"
                                  for r in met)
        else:
            vs_ours = "No recorded meetings with our roster — unknown, not a sign of weakness"
            met_list = "—"
        shared_players = [r for r in block["rows"] if r["shared_count"]]
        shared_summary = (f"Shared opponents with {len(shared_players)} of our {len(ours)} players"
                          if shared_players else "No shared opponents with our roster")
        by_sl, winning, losing = _bucket_summary(sl_index.get((opp["id"], fmt), {}))
        missing = []
        if opp.get("skill_level") is None:
            missing.append("No captured SL on this team's roster")
        if block["opponent_games"] == 0:
            missing.append(f"No recorded {format_label(fmt)} games in the verified evidence")
        if not their_games:
            missing.append("No meetings with our roster")
        team_record = ("No data" if opp.get("matches_won") is None or opp.get("matches_played") is None
                       else f"{record_text(opp['matches_won'], opp['matches_played'])} (this team"
                            + (f", {session_name})" if session_name else ")"))
        cards.append({
            "opponent": opp, "label": block["opponent_label"], "sl": _sl_text(opp.get("skill_level")),
            "team_record": team_record, "lifetime": _career_text(players_by_id.get(opp["id"]), fmt),
            "sample": block["opponent_sample"], "vs_ours": vs_ours, "met_list": met_list,
            "their_wins": their_wins, "their_games": their_games, "players_met": len(met),
            "shared_summary": shared_summary, "by_sl": by_sl, "winning_sl": winning, "losing_sl": losing,
            "missing": "; ".join(missing) or "None noted",
        })

    threats = [c for c in cards if c["their_games"] and c["their_wins"] > c["their_games"] - c["their_wins"]]
    threats.sort(key=lambda c: (-(2 * c["their_wins"] - c["their_games"]), -c["their_wins"], -c["their_games"],
                                member_order_key(c["opponent"])))
    for c in threats:
        c["threat_text"] = (f"{c['label']} · SL {c['sl']} · {record_text(c['their_wins'], c['their_games'])} vs our "
                            f"roster ({plural(c['their_games'], 'meeting')}, {c['players_met']} of our players)")

    meeting_rows = []
    for member in ours:
        for opp in theirs:
            for game in meetings.get((member["id"], opp["id"], fmt), []):
                meeting_rows.append({**game, "our": member, "opp": opp})
    meeting_rows.sort(key=lambda g: (g["sort"], member_order_key(g["our"])), reverse=True)

    return {
        "format": fmt, "ours": ours, "theirs": theirs, "comparison": evidence["comparison"],
        "blocks": evidence["opponents"], "matrix": matrix, "best_sends": best_sends,
        "concerning": concerning, "cards": cards, "threats": threats, "meetings": meeting_rows,
    }


# ---- schedule helpers shared by the artifacts ----

def filter_codes(fixture: dict[str, Any]) -> list[str]:
    """Match Day format-filter codes a fixture belongs to: "89" (every 8-Ball
    and 9-Ball variant), "ALL", and "F:<raw recorded format>"."""
    codes = ["89"] if fixture.get("format") in EIGHT_NINE_CATEGORIES else []
    codes.append("ALL")
    raw = str(fixture.get("format_raw") or "")
    if raw:
        codes.append(f"F:{raw}")
    return codes


def build_local_date(built_at: str, display_timezone: str) -> str | None:
    """The calendar date (in the display timezone) a "YYYY-MM-DD HH:MM UTC" build stamp falls on."""
    try:
        stamp = datetime.strptime(built_at.replace(" UTC", ""), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        return None
    return stamp.astimezone(ZoneInfo(display_timezone)).date().isoformat()


def scope_dates(match_day: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    """(scope, filter code) -> the distinct scheduled local dates (ISO), ascending."""
    fixtures = match_day.get("fixtures") or []
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    for scope, sides in (match_day.get("schedule") or {}).items():
        for side in sides:
            fixture = fixtures[side["fixture_index"]]
            if not fixture.get("local_date"):
                continue
            for code in filter_codes(fixture):
                out[(scope, code)].add(fixture["local_date"])
    return {key: sorted(values) for key, values in out.items()}


def suggested_date(dates: list[str], build_local: str | None) -> str | None:
    """Earliest scheduled date on or after the build date, if any."""
    if not build_local:
        return None
    return next((d for d in dates if d >= build_local), None)


def default_matchup(match_day: dict[str, Any], viewer_scopes: list[str], build_local: str | None,
                    label_by_scope: dict[str, str]) -> dict[str, Any] | None:
    """The viewer's next fixture on or after the build date (8-Ball & 9-Ball
    filter): earliest date, then earliest kickoff, then team label."""
    fixtures = match_day.get("fixtures") or []
    best = None
    for scope in viewer_scopes:
        for side in (match_day.get("schedule") or {}).get(scope, []):
            fixture = fixtures[side["fixture_index"]]
            if fixture.get("format") not in EIGHT_NINE_CATEGORIES or not fixture.get("local_date"):
                continue
            if build_local and fixture["local_date"] < build_local:
                continue
            key = (fixture["local_date"], fixture.get("local_sort") or "", label_by_scope.get(scope, scope))
            if best is None or key < best[0]:
                best = (key, scope, side)
    if best is None:
        return None
    _, scope, side = best
    return {"scope": scope, "date": best[0][0], "side": side,
            "opponent_scope": side["opponent"].get("scope_key")}


def freshness(match_day: dict[str, Any], build_local: str | None) -> dict[str, Any]:
    fixtures = match_day.get("fixtures") or []
    results = [f["local_date"] for f in fixtures if f.get("local_date") and f.get("is_scored")]
    latest = max(results) if results else None
    stale = sum(1 for f in fixtures if f.get("local_date") and build_local and f["local_date"] < build_local
                and str(f.get("status") or "").upper() == "UNPLAYED")
    return {
        "latest_result": date_label(latest) if latest else "No results recorded",
        "unplayed_before_build": stale,
        "build_date": date_label(build_local) if build_local else "unknown",
        "excel_serial_build": excel_date_serial(build_local) if build_local else None,
    }
