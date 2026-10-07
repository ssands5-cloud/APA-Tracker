"""Match Night evidence: a team comparison and an evidence-backed ranking of
our players against each opponent player.

REPORTER, not a predictor: every number shown is a recorded fact from the
identity-verified evidence (analytics.ultimate_coach_excel_payload's
Player vs Player pairs), and the ordering rule is fixed and disclosed:

1. players with DIRECT meetings against that opponent first, ordered by
   their observed direct record, then by more meetings;
2. then players with only SHARED-OPPONENT results (opponents both players
   have faced), ordered by our player's record against those shared
   opponents, then by more shared opponents, then by more games;
3. players with neither are listed last and NOT ranked.

Identical evidence is a tie ("2=") and is explained, never broken silently.
The ranking is not a win probability (none is calibrated or published) and
not a guaranteed or optimal lineup. The standalone HTML mirrors these rules
and texts in JavaScript (ui/ultimate_coach.py); a browser test checks both
produce the same ranking for the same rosters.

Players are always named alongside their APA record ID; every lookup keys
on the verified player id and roster scope, never on a name.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from typing import Any, Iterable

FORMAT_LABELS = {"EIGHT": "8-Ball", "NINE": "9-Ball", "MASTERS": "Masters", "MASTERS ALT": "Masters Alt"}

TIER_DIRECT = 3
TIER_SHARED = 2
TIER_NONE = 1

PairIndex = dict[tuple[Any, str], dict[Any, tuple[int, int]]]


def format_label(fmt: str) -> str:
    return FORMAT_LABELS.get(fmt, fmt or "this format")


def build_pair_index(pairs: Iterable[dict[str, Any]]) -> PairIndex:
    """(player_id, format) -> {opponent_id: (wins, games)} from the same
    Player vs Player aggregation the workbook's own sheet is written from."""
    index: PairIndex = defaultdict(dict)
    for row in pairs:
        index[(row["player_id"], row["format"])][row["opponent_id"]] = (int(row["wins"]), int(row["games"]))
    return index


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def record_text(wins: int, games: int) -> str:
    return f"{wins}-{games - wins}"


def player_ref(member: dict[str, Any]) -> str:
    external_id = member.get("external_id")
    shown = "not captured" if external_id in (None, "") else str(external_id)
    return f"{member['name']} (APA record ID {shown})"


def member_order_key(member: dict[str, Any]) -> tuple[Any, ...]:
    """Roster display order shared with the HTML: captured SL high to low
    (missing SL last), then name, then record ID."""
    sl = member.get("skill_level")
    return (sl is None, -(sl or 0), str(member["name"]).lower(), str(member.get("external_id") or ""))


def _rank_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (candidate["tier"], candidate["rate"], candidate["n"], candidate["extra"])


def rank_vs_opponent(
    our_members: list[dict[str, Any]], opponent: dict[str, Any], index: PairIndex, fmt: str
) -> dict[str, Any]:
    opp_games = index.get((opponent["id"], fmt), {})
    opp_total = sum(g for _, g in opp_games.values())
    candidates = []
    for member in our_members:
        mine = index.get((member["id"], fmt), {})
        direct = mine.get(opponent["id"])
        shared = sorted(set(mine) & set(opp_games), key=str)
        ow = sum(mine[s][0] for s in shared)
        og = sum(mine[s][1] for s in shared)
        tw = sum(opp_games[s][0] for s in shared)
        tg = sum(opp_games[s][1] for s in shared)
        if direct and direct[1] > 0:
            tier, rate, n, extra = TIER_DIRECT, Fraction(direct[0], direct[1]), direct[1], 0
        elif shared and og > 0:
            tier, rate, n, extra = TIER_SHARED, Fraction(ow, og), len(shared), og
        else:
            tier, rate, n, extra = TIER_NONE, Fraction(0), 0, 0
        candidates.append({
            "member": member, "tier": tier, "rate": rate, "n": n, "extra": extra,
            "direct": direct if direct and direct[1] > 0 else None,
            "shared_count": len(shared), "ours": (ow, og), "theirs": (tw, tg),
        })
    candidates.sort(key=lambda c: (-c["tier"], -c["rate"], -c["n"], -c["extra"], member_order_key(c["member"])))

    rows = []
    position = 0
    i = 0
    while i < len(candidates):
        j = i
        while j + 1 < len(candidates) and _rank_key(candidates[j + 1]) == _rank_key(candidates[i]):
            j += 1
        group = candidates[i:j + 1]
        for c in group:
            position += 1
        start_rank = position - len(group) + 1
        for c in group:
            ranked = c["tier"] != TIER_NONE
            tied = ranked and len(group) > 1
            if c["direct"]:
                direct_text = f"{record_text(*c['direct'])} ({plural(c['direct'][1], 'meeting')})"
            else:
                direct_text = "No direct meetings"
            if c["shared_count"]:
                ow, og = c["ours"]
                tw, tg = c["theirs"]
                shared_text = (f"{plural(c['shared_count'], 'shared opponent')} · ours {record_text(ow, og)} "
                               f"({plural(og, 'game')}) · theirs {record_text(tw, tg)} ({plural(tg, 'game')})")
            else:
                shared_text = "No shared opponents"
            if c["tier"] == TIER_DIRECT:
                basis = "Direct record"
            elif c["tier"] == TIER_SHARED:
                basis = "Shared-opponent results only (no direct meetings)"
            else:
                basis = "No direct or shared-opponent evidence"
            if tied:
                others = [player_ref(o["member"]) for o in group if o is not c]
                basis += " · Tied with " + ", ".join(others) + " — same evidence; the ranking can't separate them"
            rows.append({
                "rank": (f"{start_rank}=" if tied else str(start_rank)) if ranked else "—",
                "member": c["member"], "player": player_ref(c["member"]), "tier": c["tier"],
                "direct_text": direct_text, "shared_text": shared_text, "basis": basis,
                "direct": c["direct"], "shared_count": c["shared_count"], "ours": c["ours"], "theirs": c["theirs"],
            })
        i = j + 1

    with_evidence = sum(1 for r in rows if r["tier"] != TIER_NONE)
    if not our_members:
        note = "Our roster has no current players captured — nothing to rank."
    elif opp_total == 0:
        note = (f"No recorded {format_label(fmt)} games for this opponent in the verified evidence — "
                "nothing to rank on.")
    else:
        note = (f"{with_evidence} of {len(our_members)} of our players have direct or shared-opponent "
                "evidence against this opponent.")
    return {
        "opponent": opponent, "opponent_label": player_ref(opponent),
        "opponent_sample": f"{plural(opp_total, 'recorded game')} in {format_label(fmt)}",
        "opponent_games": opp_total, "note": note, "rows": rows, "with_evidence": with_evidence,
    }


def team_comparison(
    our_members: list[dict[str, Any]], opp_members: list[dict[str, Any]], index: PairIndex, fmt: str
) -> dict[str, Any]:
    def side(members: list[dict[str, Any]]) -> dict[str, Any]:
        known = [m for m in members if m.get("skill_level") is not None]
        games = [sum(g for _, g in index.get((m["id"], fmt), {}).values()) for m in members]
        total = sum(m["skill_level"] for m in known)
        return {
            "rostered": str(len(members)),
            "captured_sl": f"{len(known)} of {len(members)}",
            "sl_total": str(total) if len(known) == len(members) else f"{total} (from {len(known)} of {len(members)})",
            "games": str(sum(games)),
            "no_games": str(sum(1 for g in games if g == 0)),
        }

    dw = dg = 0
    met: set[Any] = set()
    direct_pairs = shared_pairs = none_pairs = 0
    for member in our_members:
        mine = index.get((member["id"], fmt), {})
        for opp in opp_members:
            rec = mine.get(opp["id"])
            if rec and rec[1] > 0:
                dw += rec[0]
                dg += rec[1]
                met.add(opp["id"])
                direct_pairs += 1
            elif set(mine) & set(index.get((opp["id"], fmt), {})):
                shared_pairs += 1
            else:
                none_pairs += 1
    total_pairs = len(our_members) * len(opp_members)
    return {
        "format": format_label(fmt),
        "ours": side(our_members),
        "theirs": side(opp_members),
        "direct_meetings": (f"{plural(dg, 'game')} · our players {record_text(dw, dg)}" if dg
                            else "No direct meetings between these rosters"),
        "opponents_met": f"{len(met)} of {len(opp_members)}",
        "pairings": (f"{direct_pairs} direct · {shared_pairs} shared-opponent only · {none_pairs} no evidence "
                     f"({total_pairs} total)"),
    }


def matchup_evidence(
    our_members: list[dict[str, Any]], opp_members: list[dict[str, Any]], index: PairIndex, fmt: str
) -> dict[str, Any]:
    ours = sorted(our_members, key=member_order_key)
    theirs = sorted(opp_members, key=member_order_key)
    return {
        "format": fmt,
        "comparison": team_comparison(ours, theirs, index, fmt),
        "opponents": [rank_vs_opponent(ours, opp, index, fmt) for opp in theirs],
    }


def fixture_scope_pairs(match_day: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Every directed (our scope, opponent scope, format category) pairing
    that has at least one scheduled fixture with a resolved opponent roster."""
    fixtures = match_day.get("fixtures") or []
    seen: set[tuple[str, str, str]] = set()
    for scope_key, sides in (match_day.get("schedule") or {}).items():
        for side in sides:
            opponent = side.get("opponent") or {}
            if opponent.get("status") != "resolved":
                continue
            fmt = str(fixtures[side["fixture_index"]].get("format") or "")
            seen.add((scope_key, opponent["scope_key"], fmt))
    return sorted(seen)


def members_by_scope(rosters: list[dict[str, Any]], players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Roster members per scope from analytics.ultimate_coach_excel_payload.build_team_rosters()
    rows -- the same live-SL-else-division-SL rule the HTML's TEAM_INDEX uses."""
    external_ids = {p["id"]: p.get("external_id") for p in players}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rosters:
        out[row["team_scope_key"]].append({
            "id": row["player_id"], "external_id": external_ids.get(row["player_id"]), "name": row["player_name"],
            "skill_level": row["skill_level"],
            "matches_won": row.get("matches_won"), "matches_played": row.get("matches_played"),
        })
    return out
