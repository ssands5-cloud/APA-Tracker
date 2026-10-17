"""Captain's War Room: everything for ONE fixture, built around one question --
who do I put up next? -- from recorded, identity-verified facts only.

Builds on analytics.ultimate_coach_matchup_evidence (the reviewed ranking
rule: direct meetings first, then shared-opponent results, ties shown) and
adds, for one directed team pairing (our roster vs theirs, one format):

* an evidence CATEGORY for every pairing of our player vs their player,
* first by recorded direct results per opponent player,
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
from math import isfinite
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from analytics.ultimate_coach_match_day import EIGHT_NINE_CATEGORIES, excel_date_serial, localize_match_date
from analytics.ultimate_coach_matchup_evidence import (
    NO_VERIFIED_DIRECT,
    NO_VERIFIED_EVIDENCE,
    display_name,
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

# Excluded evidence is NOT directionally conservative, and saying so would be
# wrong: category() reads the sign of a verified subtotal, so a pairing whose
# verified rows are 1-0 shows as Favorable while the same pairing with two
# excluded losses (1-2) is Concerning. Missing rows can move a label or a send
# order either way without a single stored value being fabricated.
EVIDENCE_LIMITS_NOTE = (
    "Categories describe the evidence verified in this snapshot, not a complete "
    "record. Where identities are unresolved or excluded, a pairing's history can "
    "be incomplete, and the missing results can move a category or a send order "
    "in either direction — a pairing shown as favorable can prove concerning "
    "once its excluded results resolve. See Data trust & freshness for how many "
    "identities this build excluded."
)
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
    return NO_VERIFIED_EVIDENCE


def explanation(row: dict[str, Any]) -> str:
    """Which records support the pairing, how many observations, direct or indirect."""
    direct = row.get("direct")
    parts = [
        f"Direct: {record_text(*direct)} in {plural(direct[1], 'meeting')}"
        if direct
        else NO_VERIFIED_DIRECT
    ]
    if row.get("shared_count"):
        (ow, og), (tw, tg) = row["ours"], row["theirs"]
        parts.append(f"Indirect: {plural(row['shared_count'], 'shared opponent')} — ours {record_text(ow, og)} "
                     f"({plural(og, 'game')}), theirs {record_text(tw, tg)} ({plural(tg, 'game')})")
    else:
        parts.append("no shared opponents")
    return " · ".join(parts)


_CATEGORY_WORD = {"G": "favorable", "R": "concerning", "E": "even"}
CAPTAIN_ICON = {"G": "🟢", "E": "🟡", "I": "🟡", "X": "⚪", "R": "🔴"}


def captain_cell(row: dict[str, Any]) -> str:
    """Captain View matrix cell: the category icon plus our direct record (≈ for shared-opponent only)."""
    cat = category(row)
    direct = row.get("direct")
    return CAPTAIN_ICON[cat] + (f" {record_text(*direct)}" if direct else " ≈" if cat == "I" else "")


def reason(row: dict[str, Any]) -> str:
    """Why a player appears as a send, in plain words: the recorded evidence and its sample size only."""
    direct = row.get("direct")
    if direct:
        wins, games = direct
        return f"{record_text(wins, games)} direct record ({plural(games, 'meeting')}) — {_CATEGORY_WORD[category(row)]}" + (" · small sample" if games < 3 else "")
    if row.get("shared_count"):
        (ow, og), (tw, tg) = row["ours"], row["theirs"]
        return (f"shared-opponent results only: ours {record_text(ow, og)} vs theirs {record_text(tw, tg)} across "
                f"{plural(row['shared_count'], 'shared opponent')} (no verified direct meetings in this snapshot)")
    return "no recorded evidence"


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



def meeting_date_context(games) -> str:
    """Latest captured calendar date, not a recency score or claim about undated meetings."""
    dated = [g for g in games if g.get("sort") and g.get("date") not in (None, "No data")]
    if not dated:
        return "Meeting dates not captured"
    latest = max(dated, key=lambda g: g["sort"])
    return "Latest dated meeting: " + latest["date"] + (
        "; some meeting dates not captured" if len(dated) != len(games) else "")

def meeting_sl_context(games, roster_sl) -> str:
    """Factual meeting-versus-roster scope; never re-score the recorded result."""
    if not games:
        return ""
    def captured_level(value):
        # Disclosure follows the numeric-positive SL bucket scope; never guess from text.
        if type(value) not in (int, float) or value <= 0:
            return None
        if isinstance(value, float):
            if not isfinite(value):
                return None
            return int(value) if value.is_integer() else value
        return value

    captured = [captured_level(g.get("opp_sl")) for g in games]
    roster_sl = captured_level(roster_sl)
    levels = sorted({sl for sl in captured if sl is not None})
    if not levels:
        return "Meeting opponent SL not captured"
    missing = any(sl is None for sl in captured)
    if roster_sl is not None and all(sl == roster_sl for sl in levels) and not missing:
        return ""
    note = "Meeting opponent SL " + ", ".join(str(sl) for sl in levels)
    note += "; roster capture SL " + (str(roster_sl) if roster_sl is not None else "not captured")
    return note + ("; some meeting SLs not captured" if missing else "")


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
            row["sl_context"] = (meeting_sl_context(meetings.get((row["member"]["id"], block["opponent"]["id"], fmt), []), block["opponent"].get("skill_level"))
                                 if row["direct"] else "")
            row["date_context"] = (meeting_date_context(meetings.get((row["member"]["id"], block["opponent"]["id"], fmt), []))
                                   if row["direct"] else "")
            row["reason"] = reason(row) + (" · " + row["sl_context"] if row["sl_context"] else "") + (" \u00b7 " + row["date_context"] if row["date_context"] else "")
            row["captain"] = captain_cell(row)
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

    for card, block in zip(cards, evidence["opponents"]):
        card["quick_read"] = quick_read(card, block)

    threats = [c for c in cards if c["their_games"] and c["their_wins"] > c["their_games"] - c["their_wins"]]
    threats.sort(key=lambda c: (-(2 * c["their_wins"] - c["their_games"]), -c["their_wins"], -c["their_games"],
                                member_order_key(c["opponent"])))
    for c in threats:
        c["threat_text"] = (f"{c['label']} · SL {c['sl']} · {record_text(c['their_wins'], c['their_games'])} vs our "
                            f"roster ({plural(c['their_games'], 'meeting')}, {c['players_met']} of our players)"
                            + (" · small sample" if c["their_games"] < 3 else ""))

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


def quick_read_badges(card: dict[str, Any], block: dict[str, Any], *, has_note: bool = False) -> list[str]:
    """Short, glanceable badges for the TOP of a scouting card, above the dense facts below.

    Paul's own spec (an icon and a few words a captain can read without stopping), not another
    restatement of quick_read's one-line sentence. Reuses exactly card["their_games"] -- the same
    total quick_read's own "Threat:/Even:/Vs our roster:" line already shows -- as the evidence
    signal, as a yes/no read on evidence volume and on whether this opponent has been scouted,
    rather than the facts themselves.

    GPT audit correction (d3203ee): the first version filtered rows to categories G/E only, so an
    opponent with nothing but CONCERNING (R) direct records -- real games we lost -- showed "No
    evidence on our roster", which is false; R is evidence, not its absence. It also said "Strong
    direct evidence" at exactly 3 meetings, implying a confidence a 3-game sample does not
    support. Both are fixed: evidence presence now follows card["their_games"] (every direct row,
    whatever its result), and the badge states the actual count rather than a bare adjective.

    has_note is passed in rather than looked up here: coach notes live client-side only (this
    browser's localStorage), never in the server payload, the same boundary every other coach-note
    surface in this file respects.
    """
    tg = card["their_games"]
    badges: list[str] = []
    if tg:
        badges.append(f"Direct meetings vs roster: {plural(tg, 'meeting')}" if tg >= 3
                      else f"⚠ Direct meetings vs roster: {plural(tg, 'meeting')} (small sample)")
    else:
        shared = [r for r in block["rows"] if r["category"] == "I"]
        if shared:
            total = sum(r["shared_count"] for r in shared)
            strong = len(shared) >= 3 or total >= 6
            badges.append(f"✅ Shared-opponent evidence: {plural(len(shared), 'player')}, "
                          f"{plural(total, 'opponent link')}" if strong else
                          f"⚠ Shared-opponent evidence: {plural(len(shared), 'player')}, "
                          f"{plural(total, 'opponent link')} (thin)")
        else:
            badges.append("⚠ No evidence on our roster")
    if card["losing_sl"] not in ("—", "None recorded"):
        badges.append(f"⚠ Recorded losses vs {card['losing_sl']}")
    if not has_note:
        badges.append("❓ No coach observations")
    return badges


def quick_read(card: dict[str, Any], block: dict[str, Any]) -> str:
    """One-line, facts-only summary for the top of a scouting card (full roster, no planning marks):
    the opponent's record vs our roster, our best answer on record, who to avoid, and SL directions."""
    tw, tg = card["their_wins"], card["their_games"]
    if not tg:
        parts = ["Unknown vs our roster — no meetings (not weak)"]
    else:
        word = "Threat" if tw > tg - tw else "Even" if 2 * tw == tg else "Vs our roster"
        parts = [f"{word}: {record_text(tw, tg)} vs our roster ({plural(tg, 'meeting')}{', small sample' if tg < 3 else ''})"]
    rows = block["rows"]
    roster = [r["member"] for r in rows]
    def names(group):
        return ", ".join(display_name(r["member"], roster) for r in group)
    for cat, label in (("G", "Historical top record"), ("E", "Even option on record")):
        group = [r for r in rows if r["category"] == cat]
        if group:
            top = [r for r in group if r["rank"].rstrip("=") == group[0]["rank"].rstrip("=")]
            rec = record_text(*top[0]["direct"])
            parts.append(f"{label}: {names(top)} ({rec}{', small sample' if top[0]['direct'][1] < 3 else ''}{', tied' if len(top) > 1 else ''})")
            contexts = sorted({r.get("sl_context", "") for r in top if r.get("sl_context")})
            if contexts:
                parts.append(contexts[0] if len(top) == 1 else "Meeting SLs differ or are missing; check each pairing's detail")
            break
    else:
        shared = [r for r in rows if r["category"] == "I"]
        parts.append(f"No direct answer — {plural(len(shared), 'shared-opponent candidate')} (≈, not ordered)"
                     if shared else "No evidence-backed answer on our roster")
    avoid = [r for r in rows if r["category"] == "R"]
    if avoid:
        parts.append("Avoid: " + ", ".join(f"{display_name(r['member'], roster)} ({record_text(*r['direct'])}{', small sample' if r['direct'][1] < 3 else ''})" for r in reversed(avoid)))
    if card["winning_sl"] not in ("—", "None recorded"):
        parts.append(f"Winning records vs {card['winning_sl']}")
    if card["losing_sl"] not in ("—", "None recorded"):
        parts.append(f"Losing records vs {card['losing_sl']}")
    return " · ".join(parts)


# ---- Send lists outside Tonight (War Room, Lineup Lab, Command Center, packet) ----

def _group_key(row: dict[str, Any]) -> str:
    return str(row["rank"]).rstrip("=")


def send_labels(rows: list[dict[str, Any]]) -> list[str]:
    """Labels for our remaining sendable candidates vs one opponent, in ranking order. Direct records are
    numbered by evidence group ("1." or, when several remaining players share the evidence, "1="); shared-
    opponent-only candidates are "≈" -- one unordered group, never numbered (GPT audit #84)."""
    order: dict[str, int] = {}
    count: dict[str, int] = {}
    for r in rows:
        if r["category"] in ("G", "E"):
            key = _group_key(r)
            order.setdefault(key, len(order) + 1)
            count[key] = count.get(key, 0) + 1
    return [f"{order[_group_key(r)]}{'=' if count[_group_key(r)] > 1 else '.'}" if r["category"] in ("G", "E") else "≈"
            for r in rows]


def send_list_text(rows: list[dict[str, Any]], limit: int = 3) -> str:
    labels = send_labels(rows)
    return " · ".join(f"{labels[i]} {r['player']} — {r['cell']}" for i, r in enumerate(rows[:limit]))


def best_send_text(rows: list[dict[str, Any]]) -> str:
    """The single best remaining send and its reason -- saying when it is tied or not ordered at all."""
    if not rows:
        return ""
    first = rows[0]
    if first["category"] == "I":
        n = sum(1 for r in rows if r["category"] == "I")
        tag = f"shared-opponent candidate, not ordered ({'the only one' if n == 1 else f'one of {n}'}): "
    else:
        tied = sum(1 for r in rows if r["category"] in ("G", "E") and _group_key(r) == _group_key(first))
        tag = ("first by recorded direct results: " if tied == 1 else
               f"first by recorded direct results (tied with {tied - 1} other{'s' if tied > 2 else ''}, same evidence): ")
    return f"{tag}{first['player']} — reason: {first['reason']}"


# ---- Next Send: "they put up this player -- who do I send?" ----

DIRECT_ORDER_NOTE = 'Order uses recorded win percentage before meeting count, not confidence. A 1-0 record can appear before 8-2; compare sample sizes.'

MEDALS = ("🥇", "🥈", "🥉")


def save_record_text(row: dict[str, Any]) -> str:
    """Recorded scope beside a save warning, never a strategic strength estimate."""
    if not row["direct"]:
        return ""
    w, games = row["direct"]
    return f"{record_text(w, games)} in {games} meeting{'s' if games != 1 else ''}" + (", small sample" if games < 3 else "")


def next_send(war_room: dict[str, Any], j: int, *, remaining: set[Any] | None = None,
              unplayed: list[bool] | None = None) -> dict[str, Any]:
    """Responses to opponent j among our remaining players, from the War Room ranking only.

    Every ranked direct candidate (favorable, then even direct records) gets its own numbered
    line, in ranking order; players with the same evidence share a rank number and are named as
    tied. Nothing is hidden behind a "+N more" collapse (SEND-LAYOUT-01) -- the first three ranks
    also carry a medal for a quick visual read, and ranks beyond that still get a plain number.
    Shared-opponent-only candidates are one unordered group ("≈"), never ranked. Concerning direct
    records are listed to avoid; players with no evidence are unknown (not weak). Names shown here
    omit the APA record ID (NAME-DISPLAY-01) -- every lookup still keys on member['id']. A ranked
    player who is our only remaining favorable direct option vs another unplayed opponent is
    flagged "consider saving". Nothing is re-scored, weighted or blended."""
    blocks = war_room["blocks"]
    roster = war_room["ours"]
    remaining = {m["id"] for m in roster} if remaining is None else remaining
    unplayed = [True] * len(blocks) if unplayed is None else unplayed
    block = blocks[j]
    if not unplayed[j]:          # a used target gets no active response at all (GPT audit #84 P2)
        return {"opponent": block["opponent"], "label": block["opponent_label"],
                "headline": f"{block['opponent']['name']} has already played.",
                "ranked": [], "unordered": [], "avoid": [], "unknown": []}
    rows = [r for r in block["rows"] if r["member"]["id"] in remaining]
    only_green: dict[Any, list[str]] = {}
    for k, other in enumerate(blocks):
        if k == j or not unplayed[k]:
            continue
        greens = [r for r in other["rows"] if r["category"] == "G" and r["member"]["id"] in remaining]
        if len(greens) == 1:
            only_green.setdefault(greens[0]["member"]["id"], []).append(f"{display_name(other['opponent'], war_room['theirs'])} ({save_record_text(greens[0])})")

    groups: list[list[dict[str, Any]]] = []
    for r in rows:
        if r["category"] in ("G", "E"):
            if groups and groups[-1][0]["rank"].rstrip("=") == r["rank"].rstrip("="):
                groups[-1].append(r)
            else:
                groups.append([r])
    ranked: list[dict[str, Any]] = []
    for g, group in enumerate(groups):
        medal = MEDALS[g] if g < len(MEDALS) else ""
        for r in group:
            tied = [display_name(o["member"], roster) for o in group if o is not r]
            save = only_green.get(r["member"]["id"])
            ranked.append({
                "rank": r["rank"], "choice_number": g + 1, "medal": medal, "member": r["member"],
                "display": display_name(r["member"], roster), "category": r["category"],
                "reason": r["reason"], "tied_with": tied,
                "save": f"consider saving — our only favorable direct option vs {', '.join(save)}" if save else "",
            })
    # The save warning belongs here too, not only on ranked candidates. With no direct record to
    # order, every candidate shows as "≈ not ordered" -- and picking one off that list is exactly
    # when a captain can unknowingly spend his only favorable option against an opponent still to
    # come.
    def _save_for(member_id: Any) -> str:
        names = only_green.get(member_id)
        return f"consider saving — our only favorable direct option vs {', '.join(names)}" if names else ""

    unordered = [{"member": r["member"], "display": display_name(r["member"], roster), "reason": r["reason"],
                  "save": _save_for(r["member"]["id"])}
                 for r in rows if r["category"] == "I"]
    # Worst recorded direct record first: the reverse of the ranking order.
    avoid = [{"member": r["member"], "display": display_name(r["member"], roster), "reason": r["reason"]}
             for r in reversed(rows) if r["category"] == "R"]
    unknown = [display_name(r["member"], roster) for r in rows if r["category"] == "X"]
    if ranked:
        headline = f"First by recorded direct results: {ranked[0]['display']}" + (
            f" or {', '.join(ranked[0]['tied_with'])} (tied)" if ranked[0]["tied_with"] else "")
    elif unordered:
        headline = "No favorable/even direct option — shared-opponent candidates only (≈, not ordered)"
    else:
        headline = "No evidence-backed option left among our remaining players"
    return {"opponent": block["opponent"], "label": block["opponent_label"], "headline": headline,
            "ranked": ranked, "unordered": unordered, "avoid": avoid, "unknown": unknown}


def lineup_budget(war_room: dict[str, Any], *, cap: int | None, slots: int,
                  played: dict[Any, int] | None = None, remaining: set[Any] | None = None,
                  sending: Any = None) -> dict[str, Any]:
    """Reference skill arithmetic for a supplied cap and slot count, not match legality.

    Required sends, format and other match constraints are not verified here. Legacy boolean
    field names describe only the captured-SL comparison under the caller's supplied count.
    No cap is assumed; missing captured skill levels keep the comparison incomplete.
    """
    played = played or {}
    ours = war_room["ours"]
    remaining = {m["id"] for m in ours} if remaining is None else remaining
    used = sum(int(v) for v in played.values())
    slots_left = max(0, slots - len(played))
    pool = [m for m in ours if m["id"] in remaining and m["id"] not in played]
    known = sorted(int(m["skill_level"]) for m in pool if isinstance(m.get("skill_level"), (int, float)))
    unknown = sum(1 for m in pool if not isinstance(m.get("skill_level"), (int, float)))
    out = {"cap": cap, "used": used, "left": None if cap is None else cap - used,
           "slots_left": slots_left, "unknown_sl": unknown, "complete": unknown == 0,
           "feasible": None, "cheapest": None, "sending_keeps_legal": None, "note": ""}
    if cap is None:
        return out
    left = cap - used

    def cheapest(pool_sl: list[int], n: int) -> int | None:
        return sum(pool_sl[:n]) if len(pool_sl) >= n else None

    need = cheapest(known, slots_left)
    out["cheapest"] = need
    out["feasible"] = None if need is None else need <= left
    if sending is not None:
        send_m = next((m for m in ours if m["id"] == sending), None)
        sl = send_m.get("skill_level") if send_m else None
        if isinstance(sl, (int, float)):
            rest = sorted(int(m["skill_level"]) for m in pool
                          if m["id"] != sending and isinstance(m.get("skill_level"), (int, float)))
            after = cheapest(rest, max(0, slots_left - 1))
            out["sending_keeps_legal"] = (None if after is None
                                          else int(sl) + after + used <= cap)
    bits = [f"Reference: {slots_left} supplied slots; required sends/format not verified — not a match-legality check"]
    if unknown:
        bits.append(f"{unknown} player(s) without a captured skill level — this check is incomplete; no lineup cleared")
    elif out["feasible"] is False:
        bits.append(f"captured-SL comparison exceeds entered budget: the cheapest {slots_left} left total {need}, "
                    f"{need - left} over your remaining {left}")
    elif need is None and slots_left:
        bits.append(f"not enough players with a captured skill level to check {slots_left} more slots")
    elif out["feasible"]:
        bits.append(f"{left} left for {slots_left} more")
    out["note"] = " · ".join(bits)
    return out


def blind_send(war_room: dict[str, Any], *, remaining: set[Any] | None = None,
               unplayed: list[bool] | None = None) -> dict[str, Any]:
    """Who to put up when WE lead and have not seen their player yet.

    Every other recommendation here answers "they put up X, who answers?". In APA the lead
    alternates, so a captain regularly chooses first, and for that decision the product had no
    answer at all. This fills it WITHOUT predicting their lineup: it ranks our remaining players
    by what is already recorded against the opponents still unplayed.

    The order is fewest concerning direct records, then most favorable, then most even direct,
    then roster order. That is a stated preference rather than a derived truth: it assumes a
    captain leading blind would rather dodge a known bad matchup than chase a known good one.
    The third key was changed from total meetings to even-record count so the workbook can
    compute the same ranking from its category grid; those two are DIFFERENT preferences that
    happen to agree on our fixtures, not equivalent rules (GPT, BLIND-01).

    Two things it refuses to do, both from that audit. It will not name anybody when nothing is
    recorded for or against any candidate, because naming the first player in roster order
    implies an edge that does not exist and contradicts the response panel below it. And it
    never says "no concerning record" without saying how much of the remaining field we actually
    hold a direct record against: silence about an opponent is missing evidence, not a clean
    sheet.
    """
    blocks = war_room["blocks"]
    remaining = {m["id"] for m in war_room["ours"]} if remaining is None else remaining
    unplayed = [True] * len(blocks) if unplayed is None else unplayed
    live = [b for b, open_ in zip(blocks, unplayed) if open_]
    empty = {"member": None, "why": "", "concerning": 0, "favorable": 0, "even": 0,
             "direct_coverage": 0, "no_record": len(live), "unranked": True,
             "weak": True, "ranked": [], "ties": [], "opponents_left": len(live)}
    if not live or not remaining:
        return empty

    by_member: dict[Any, dict[str, Any]] = {}
    for order, m in enumerate(war_room["ours"]):
        if m["id"] in remaining:
            by_member[m["id"]] = {"member": m, "order": order, "concerning": 0,
                                  "favorable": 0, "even": 0}
    for block in live:
        for r in block["rows"]:
            stat = by_member.get(r["member"]["id"])
            if stat is None:
                continue
            if r["category"] == "R":
                stat["concerning"] += 1
            elif r["category"] == "G":
                stat["favorable"] += 1
            elif r["category"] == "E":
                stat["even"] += 1
    if not by_member:
        return empty
    for stat in by_member.values():
        stat["direct_coverage"] = stat["concerning"] + stat["favorable"] + stat["even"]
        stat["no_record"] = len(live) - stat["direct_coverage"]

    ranked = sorted(by_member.values(),
                    key=lambda s: (s["concerning"], -s["favorable"], -s["even"], s["order"]))
    n = len(live)

    # If the leading candidate holds no direct record at all, we are not recommending him -- he
    # simply sorted above players who have a LOSING record. Unknown is not evidence of a safer
    # lead, so it is never dressed up as one ("even vs 0 of 2" was the shape of that bug). Name
    # nobody, and say what the alternatives actually look like so the tradeoff is visible.
    # Kept short on purpose: this sits above the fold on a phone.
    top = ranked[0]
    if not top["direct_coverage"]:
        bad = sum(1 for x in ranked if x["concerning"])
        known = sum(1 for x in ranked if x["direct_coverage"])
        out = dict(empty)
        if not known:
            why = f"nothing recorded either way vs any of {n} — your read decides"
        else:
            why = (f"no record either way for our best-placed option — unknown, not safer"
                   + (f" · {bad} of your remaining have a concerning record" if bad else "")
                   + " · unranked, your read decides")
        out.update(ranked=ranked, opponents_left=n, no_record=n, why=why)
        return out

    gap = f" · no direct record vs {top['no_record']}" if top["no_record"] else ""
    if top["concerning"]:
        why = (f"{top['concerning']} concerning of {n} — best available, not good{gap}"
               if top["favorable"] == 0 else
               f"{top['favorable']} favorable, {top['concerning']} concerning of {n}{gap}")
    elif top["favorable"]:
        why = f"favorable vs {top['favorable']} of {n}{gap}"
    else:
        why = f"even vs {top['even']} of {n}{gap}"
    # Count ties are not equal records: the existing final fallback is roster order.
    ties = [s["member"] for s in ranked
            if all(s[key] == top[key] for key in ("concerning", "favorable", "even"))]
    return {"member": top["member"], "why": why, "ties": ties, "concerning": top["concerning"],
            "favorable": top["favorable"], "even": top["even"],
            "direct_coverage": top["direct_coverage"], "no_record": top["no_record"],
            "unranked": False, "weak": top["favorable"] == 0 and top["even"] == 0,
            "ranked": ranked, "opponents_left": n}

def live_threats(war_room: dict[str, Any], *, remaining: set[Any] | None = None) -> list[dict[str, Any]]:
    """Dangerous opponents, evaluated against our roster AS IT STANDS TONIGHT.

    The existing threat flag sums a win/loss record against our WHOLE roster's history with
    that opponent, including players who are Unavailable or have already Played. A captain
    reading "dangerous" needs to know whether that danger is still live for the sends still
    ahead -- a record built entirely on a player no longer in tonight's lineup proves nothing
    about the players actually left to send.

    Returns opponents who are either a LIVE threat (their winning record holds among players
    still in play) or UNKNOWN (the old roster-wide flag would have fired, but every game behind
    it was against a player no longer available, so there is no evidence at all against the
    remaining roster). GPT audit correction: missing evidence is uncertainty, not safety -- the
    first version of this said "no longer a live risk", which reads as a clearance the data does
    not support. If ANY live evidence exists and simply is not winning, that is real evidence of
    no danger, not an unresolved case, so it is not flagged here at all; UNKNOWN only ever means
    zero games against players still in play, which is also what makes "only against player(s)
    not in tonight's remaining lineup" a true statement rather than an overclaim.
    """
    ours_ids = {m["id"] for m in war_room["ours"]}
    remaining = ours_ids if remaining is None else remaining
    if not remaining:
        return []
    remaining_count = len(ours_ids & remaining)
    out: list[dict[str, Any]] = []
    for block in war_room["blocks"]:
        opp = block["opponent"]
        live = [r for r in block["rows"] if r["direct"] and r["member"]["id"] in remaining]
        gone = [r for r in block["rows"] if r["direct"] and r["member"]["id"] not in remaining]
        live_wins = sum(r["direct"][1] - r["direct"][0] for r in live)
        live_games = sum(r["direct"][1] for r in live)
        gone_wins = sum(r["direct"][1] - r["direct"][0] for r in gone)
        gone_games = sum(r["direct"][1] for r in gone)
        dangerous_live = bool(live_games) and live_wins > live_games - live_wins
        # Only reachable when live_games is zero, so "only against departed players" is literally
        # true here, and the record is silent about the players actually still in play, not safe.
        dangerous_on_departed_evidence_only = (not live_games and gone_games
                                               and gone_wins > gone_games - gone_wins)
        if dangerous_live:
            out.append({
                "opponent": opp, "label": block["opponent_label"], "live": True, "unknown": False,
                "wins": live_wins, "games": live_games, "players_met": len(live),
                "text": f"{block['opponent_label']} · SL {_sl_text(opp.get('skill_level'))} · "
                        f"{record_text(live_wins, live_games)} vs our roster still in play "
                        f"({plural(live_games, 'meeting')}, {len(live)} of {plural(remaining_count, 'remaining player')})"
                        + (f" · no direct record vs {plural(remaining_count - len(live), 'remaining player')}"
                           if remaining_count > len(live) else "")
                        + (" · small sample" if live_games < 3 else ""),
                "short": (f"{display_name(opp, war_room['theirs'])} — {record_text(live_wins, live_games)} ({plural(live_games, 'meeting')}, small sample)"
                          if live_games < 3 else f"{display_name(opp, war_room['theirs'])} — {record_text(live_wins, live_games)} vs our roster still in play"),
            })
        elif dangerous_on_departed_evidence_only:
            out.append({
                "opponent": opp, "label": block["opponent_label"], "live": False, "unknown": True,
                "wins": gone_wins, "games": gone_games, "players_met": len(gone),
                "text": f"{block['opponent_label']} · SL {_sl_text(opp.get('skill_level'))} · "
                        f"historically {record_text(gone_wins, gone_games)} vs our roster, but that "
                        "record is only against player(s) not in tonight's remaining lineup — "
                        "unknown vs who is left, not cleared" + (" · small historical sample" if gone_games < 3 else ""),
                "short": f"{display_name(opp, war_room['theirs'])} — unknown vs our remaining roster (historically "
                        f"{record_text(gone_wins, gone_games)}{', small sample' if gone_games < 3 else ''})",
            })
    out.sort(key=lambda c: (c["unknown"], -(2 * c["wins"] - c["games"]) if c["games"] else 0,
                            member_order_key(c["opponent"])))
    return out


def send_cost(war_room: dict[str, Any], j: int, member_id: Any, *,
              remaining: set[Any] | None = None,
              unplayed: list[bool] | None = None) -> dict[str, Any]:
    """What spending this player on opponent j costs for the rest of the night.

    Next Send answers one pairing at a time, so a captain choosing between two candidates could
    not see what the choice leaves him for the opponents still to come. The existing "consider
    saving" flag only fires in the extreme case -- when a player is our SOLE favorable option
    against someone else -- and between that and silence there was nothing.

    This counts, exactly: of the other unplayed opponents, how many have a favorable direct
    option among our remaining players now, and how many still would once this player is gone.
    No model and no prediction of their lineup; it is arithmetic over records already shown.
    """
    blocks = war_room["blocks"]
    remaining = {m["id"] for m in war_room["ours"]} if remaining is None else remaining
    unplayed = [True] * len(blocks) if unplayed is None else unplayed
    after = remaining - {member_id}
    others = [b for k, b in enumerate(blocks) if k != j and unplayed[k]]

    def covered(pool: set[Any]) -> list[dict[str, Any]]:
        return [b["opponent"] for b in others
                if any(r["category"] == "G" and r["member"]["id"] in pool for r in b["rows"])]

    before, still = covered(remaining), covered(after)
    still_ids = {opponent["id"] for opponent in still}
    lost = [display_name(opponent, war_room["theirs"]) for opponent in before
            if opponent["id"] not in still_ids]
    return {"others": len(others), "covered_before": len(before), "covered_after": len(still),
            "lost": lost}


def next_send_lines(ns: dict[str, Any]) -> list[str]:
    """Plain-text Next Send lines shared by the HTML (cross-checked) and Excel/packet texts.

    Every ranked candidate gets its own numbered line (SEND-LAYOUT-01); tied candidates
    retain equal numbers, and nothing below the top three is hidden."""
    lines = [ns["headline"]]
    if ns["ranked"]:
        lines.append(DIRECT_ORDER_NOTE)
    for m in ns["ranked"]:
        prefix = f"{m['choice_number']}."
        lines.append(f"{prefix} {m['display']} — {m['reason']}"
                     + (f" · tied with {', '.join(m['tied_with'])}" if m["tied_with"] else "")
                     + (f" · {m['save']}" if m["save"] else ""))
    for u in ns["unordered"]:
        lines.append(f"≈ {u['display']} — {u['reason']}"
                     + (f" · {u['save']}" if u.get("save") else ""))
    for a in ns["avoid"]:
        lines.append(f"⚠ Avoid {a['display']} — {a['reason']}")
    if ns["unknown"]:
        lines.extend("❓ Unknown (no verified evidence, not weak): " + name for name in ns["unknown"])
    return lines


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


def stale_warning(fresh: dict[str, Any]) -> str:
    """One shared, prominent sentence for a snapshot whose earlier fixtures have no result ("" when none).

    Real case (2026-10-08): a workbook built Oct 8 held no result after Sep 20, so a Monday that APA already
    showed was missing; the only hint was muted text (hidden entirely on the phone Match Night page)."""
    n = int(fresh.get("unplayed_before_build") or 0)
    if not n:
        return ""
    return (f"⚠ {n} fixture{'s' if n != 1 else ''} dated before this build {'have' if n != 1 else 'has'} no result in "
            f"this snapshot (latest recorded result {fresh.get('latest_result')}). Records, medals and risks leave "
            "those matches out — refresh the data and rebuild before relying on them.")


def stale_by_scope(match_day: dict[str, Any], build_local: str | None) -> dict[str, int]:
    """Per team scope: fixtures dated before the build that still show UNPLAYED (the captain's own missing
    results, not just a league-wide count). Scopes with none are omitted."""
    fixtures = match_day.get("fixtures") or []
    out: dict[str, int] = {}
    if not build_local:
        return out
    for scope, sides in (match_day.get("schedule") or {}).items():
        n = sum(1 for side in sides for f in [fixtures[side["fixture_index"]]]
                if f.get("local_date") and f["local_date"] < build_local
                and str(f.get("status") or "").upper() == "UNPLAYED" and not f.get("is_bye"))
        if n:
            out[scope] = n
    return out


def team_stale_note(team_label: str, count: int) -> str:
    """The same per-team lead-in Excel's uc_TeamStaleText formula renders ("" when the team has no gap), for a
    renderer (e.g. the Match Night slim package) where the one relevant team is already fixed at build time."""
    if not count:
        return ""
    return (f"⚠ {team_label}: {count} earlier fixture{'s' if count != 1 else ''} "
            f"{'has' if count == 1 else 'have'} no result in this snapshot. ")


def freshness(match_day: dict[str, Any], build_local: str | None) -> dict[str, Any]:
    fixtures = match_day.get("fixtures") or []
    # GPT audit 7a4f8b5 follow-up (2026-10-09 06:12 UTC): scripts/refresh_ultimate_coach_current_session.py's
    # diff() was fixed to require real score evidence, but this is the SEPARATE function the actual HTML/Excel
    # freshness banner reads -- it still selected the latest date by is_scored alone, so a rebuild from the
    # already-fixed refresh engine still advertised the same wrong date here. APA can flag a fixture
    # is_scored=True/COMPLETED with null home/away scores (a scheduling-system artifact, not a real result);
    # only a fixture with actual non-null scores counts as real evidence of a result.
    results = [f["local_date"] for f in fixtures
               if f.get("local_date") and f.get("is_scored") and f.get("home_score") is not None and f.get("away_score") is not None]
    latest = max(results) if results else None
    stale = sum(1 for f in fixtures if f.get("local_date") and build_local and f["local_date"] < build_local
                and str(f.get("status") or "").upper() == "UNPLAYED")
    return {
        "latest_result": date_label(latest) if latest else "No results recorded",
        "unplayed_before_build": stale,
        "build_date": date_label(build_local) if build_local else "unknown",
        "excel_serial_build": excel_date_serial(build_local) if build_local else None,
    }


# ---- onboarding shared by the Excel START HERE tab and the HTML "Start here" card ----

ONBOARDING_WHAT = [
    "• Prepare for tonight's match from one setup point",
    "• Compare both rosters side by side",
    "• Review direct head-to-head history",
    "• Review shared-opponent evidence",
    "• Plan your lineup as the night goes",
    "• Scout every opponent",
    "• Print a match-night packet",
]
ONBOARDING_LIMITS = [
    "• Historical records are not predictions. A favorable record is not a promise.",
    "• Evidence can be missing: unscored matches, uncaptured skill levels, players with few games.",
    "• This file is a snapshot and never refreshes itself: results after its latest recorded result are missing "
    "until the data is refreshed and the file rebuilt. A ⚠ warning appears when earlier fixtures have no result.",
    "• No validated win-probability model exists: no predicted or calibrated odds are shown (NOT CALIBRATED). Historical win rates that appear (e.g. Player vs Player) describe past results only, always with their sample size.",
    "• Recommendations only rank the available evidence; small samples are labelled with their counts.",
    "• Rosters are current captured rosters, not who played on a past date.",
    "• Unknown availability is not Unavailable, and neither is a prediction. No lineup-legality or skill cap is assumed.",
    "• Planning marks belong to one fixture: clear old marks before planning another night.",
    "• Coach Notes are your opinions, never APA facts.",
]
# Player vs Player status line (GPT audit #84): the page DOES show historical win-rate percentages, so the
# banner must separate those descriptive figures from a prediction, which is never shown.
PVP_STATUS = (
    "Win probability: NOT CALIBRATED — no predicted odds are shown.",
    "Percentages on this page are historical win rates from recorded games, each with its sample size: "
    "they describe past results, not a prediction. A predicted percentage would need a model that first "
    "passes chronological backtesting.",
)
PAGES_URL = "https://ssands5-cloud.github.io/APA-Tracker/"
MATCH_NIGHT_GUIDE = [
    f"• Open on your phone: {PAGES_URL} — a private Match Night package for ONE fixture, encrypted; enter the passphrase once.",
    "• Add to Home Screen — iPhone (Safari): Share → Add to Home Screen. Android (Chrome): ⋮ menu → Add to Home screen / Install app.",
    "• Before league night: the publisher re-publishes the package (tools/publish_match_night.ps1); open the app once while online so the phone downloads it. The lock screen shows 'Package built <date>'.",
    "• Offline: after one unlock it opens without signal, but the data is frozen at its build date — results recorded after it are not included.",
    "• During the match: under 'Who should I send next?' tap the player they put up. Medals = ordered direct records (same evidence, same medal); ≈ = not ordered; ⚠ = avoid; ❓ = unknown, not weak. Tap ✓ Sent to mark the pairing played.",
    "• Planning marks and coach notes you make on the phone stay on that phone; nothing is sent anywhere.",
    "• Freshness: check the Built date, the latest recorded result and the count of earlier fixtures still UNPLAYED in the snapshot.",
]
COACH_TAGS = ["Slow shooter", "Fast shooter", "Strong safety player", "Good under pressure", "Struggles under pressure",
              "Consistent breaker", "Aggressive style", "Defensive style", "Runs out often", "Misses long shots"]


def build_version() -> str:
    """The code revision an artifact was built from (short git SHA), or "unversioned" outside a checkout."""
    import subprocess
    from pathlib import Path
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10,
                             cwd=Path(__file__).resolve().parent).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    return f"PR #83 · {sha}" if sha else "unversioned"


def worked_example(match_day: dict[str, Any], default: dict[str, Any] | None, viewer_label: str | None,
                   label_by_scope: dict[str, str]) -> list[str] | None:
    """What Match Day picks for this build's configured viewer (default_matchup): selections only, never
    results, so the example is always true to the data it ships with."""
    from analytics.ultimate_coach_match_day import FORMAT_FILTER_EIGHT_NINE_LABEL
    if not default or not viewer_label:
        return None
    fixtures = match_day.get("fixtures") or []
    side = default["side"]
    opponent = side.get("opponent") or {}
    if opponent.get("status") == "bye":
        opp_text = "Bye (no opponent)"
    else:
        opp_text = (("Home" if side.get("side") == "home" else "Away") + " vs "
                    + (label_by_scope.get(opponent.get("scope_key") or "") or opponent.get("team_name")
                       or "an opponent without a captured roster"))
    same_day = [s for s in (match_day.get("schedule") or {}).get(default["scope"], [])
                if fixtures[s["fixture_index"]].get("local_date") == default["date"]
                and fixtures[s["fixture_index"]].get("format") in EIGHT_NINE_CATEGORIES]
    return [
        f"1 · Player: {viewer_label}",
        f"2 · Team: {label_by_scope.get(default['scope'], default['scope'])}",
        f"3 · Format: {FORMAT_FILTER_EIGHT_NINE_LABEL} (the default)",
        f"4 · Scheduled date: {date_label(default['date'])} — the earliest scheduled date on or after the build date",
        "5 · Fixture: " + opp_text + (" (the only fixture that day, so it is used automatically)" if len(same_day) == 1
                                      else f" ({len(same_day)} fixtures that day — you choose one)"),
        "Then the Command Center, Lineup Lab, War Room and Captain Packet all show this fixture.",
    ]
