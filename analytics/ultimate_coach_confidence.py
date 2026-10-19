"""Captain confidence level for one pairing: how much to trust sending our player against theirs.

A plain, stated rule over recorded evidence only -- the framework in docs/captain_confidence_framework.md,
checked by a chronological replay (scripts/replay_confidence_levels.py): its levels order real next-game
outcomes Strong > Solid > Thin > Unknown > Caution in both 8-Ball and 9-Ball. It is a trust label with its
reason, never a probability or a prediction, and it does not change any ranking order.

Inputs: the direct record and its meeting count, whether skill levels changed since the pair last met,
both players' league-scoped lifetime records in the format, and shared-opponent results. Recency is not an
input: the replay found almost no difference between recent and old direct records.

ui/ultimate_coach_war_room.js mirrors this module exactly; browser tests cross-check the two.
"""

from __future__ import annotations

from typing import Any

LEVELS = ("Strong", "Solid", "Thin", "Unknown", "Conflicted", "Caution")
# Integer points used by the Match Night Engine; integers keep Python and JavaScript plans identical.
LEVEL_POINTS = {"Strong": 4, "Solid": 2, "Thin": 1, "Unknown": 0, "Conflicted": 0, "Caution": -2}

FORM_MIN_GAMES = 20     # an overall record counts once both players have this many games
FORM_SHRINK = 5         # pulled toward .500 by 5 wins and 5 losses so a new player is not extreme
# Thresholds (exact, in integer arithmetic below): overall form edge .05, strong form edge .15,
# shared-opponent edge .10.
SHARED_SOLID_COUNT = 3  # common opponents needed for a Solid shared-opponent edge
DEEP_MEETINGS = 5
DEEP_RATE = 0.7


def _wl(w: int, g: int) -> str:
    return f"{w}-{g - w}"


def _meetings(g: int) -> str:
    return f"{g} meeting{'' if g == 1 else 's'}"


def overall_record(player: dict[str, Any] | None, fmt: str) -> tuple[int, int]:
    """League-scoped lifetime (wins, games) in the format, from complete scopes only."""
    w = g = 0
    for row in (player or {}).get("career_stats") or []:
        if row.get("format") != fmt:
            continue
        won, played = row.get("matches_won"), row.get("matches_played")
        if isinstance(won, bool) or isinstance(played, bool) or not isinstance(won, int) or not isinstance(played, int):
            continue
        if 0 <= won <= played:
            w += won
            g += played
    return w, g


def _form_compare(own: tuple[int, int], opp: tuple[int, int], edge_twentieths: int) -> int:
    """Sign of (own form - opp form) - edge, in exact integers so Python and JavaScript always agree.

    Form is (w + 5) / (g + 10); edge_twentieths is the threshold in twentieths (1 = .05, 3 = .15).
    """
    (ow, og), (xw, xg) = own, opp
    num = (ow + FORM_SHRINK) * (xg + 2 * FORM_SHRINK) - (xw + FORM_SHRINK) * (og + 2 * FORM_SHRINK)
    den = (og + 2 * FORM_SHRINK) * (xg + 2 * FORM_SHRINK)
    diff = 20 * num - edge_twentieths * den
    return (diff > 0) - (diff < 0)


def pair_confidence(direct: tuple[int, int] | None, *, own_overall: tuple[int, int], opp_overall: tuple[int, int],
                    shared: tuple[int, int, int, int, int] | None = None,
                    sl_changed: bool = False) -> dict[str, Any]:
    """Level and reason for sending our player against theirs.

    direct: (wins, meetings) or None. shared: (our wins, our games, their wins, their games, common opponents)
    or None. sl_changed: True only when both skill levels are captured and differ from the latest meeting.
    """
    known_form = own_overall[1] >= FORM_MIN_GAMES and opp_overall[1] >= FORM_MIN_GAMES
    form_for = known_form and _form_compare(own_overall, opp_overall, 1) >= 0
    form_against = known_form and _form_compare(opp_overall, own_overall, 1) >= 0
    form_strong = known_form and _form_compare(own_overall, opp_overall, 3) >= 0
    overall = f"overall {_wl(*own_overall)} vs {_wl(*opp_overall)}"

    def out(level: str, why: str) -> dict[str, Any]:
        return {"level": level, "points": LEVEL_POINTS[level], "why": why, "text": f"{level} — {why}"}

    if direct and direct[1] > 0:
        w, g = direct
        rec = f"{_wl(w, g)} in {_meetings(g)}"
        fav, unf = w > g - w, w < g - w
        if fav and form_against:
            return out("Conflicted", f"{rec}, but a weaker {overall}")
        if unf and form_for:
            return out("Conflicted", f"{rec}, but a stronger {overall}")
        if unf:
            return out("Caution", f"{rec} direct")
        if not fav:
            level, why = "Thin", f"even direct record, {rec}"
        elif g >= DEEP_MEETINGS and w / g >= DEEP_RATE or g >= 3 and form_for:
            level, why = "Strong", rec + (f" and a stronger {overall}" if form_for else "")
        elif g >= 3 or form_for:
            level, why = "Solid", rec + (f" and a stronger {overall}" if form_for else "")
        else:
            level, why = "Thin", f"only {rec}"
        if sl_changed and level in ("Strong", "Solid"):
            level = "Solid" if level == "Strong" else "Thin"
            why += "; skill levels changed since they last met"
        return out(level, why)

    if form_strong:
        return out("Strong", f"no direct history; much stronger {overall}")
    if form_for:
        return out("Solid", f"no direct history; stronger {overall}")
    if form_against:
        return out("Caution", f"no direct history; weaker {overall}")
    if shared and shared[1] > 0 and shared[3] > 0:
        ow, og, tw, tg, n = shared
        cross = 10 * (ow * tg - tw * og)     # shared edge vs .10, in exact integers
        common = f"{n} shared opponent{'' if n == 1 else 's'}: ours {_wl(ow, og)}, theirs {_wl(tw, tg)}"
        if cross >= og * tg:
            return out("Solid" if n >= SHARED_SOLID_COUNT else "Thin", common)
        if cross <= -og * tg:
            return out("Caution", common)
    return out("Unknown", "no direct history and no clear overall or shared-opponent edge")


def sl_changed_since_last_meeting(games: list[dict[str, Any]], own_sl: Any, opp_sl: Any) -> bool:
    """True only when the newest dated meeting and both current skill levels are captured and differ."""
    def known(x: Any) -> bool:
        return type(x) in (int, float) and x > 0
    dated = [g for g in games if g.get("sort")]
    if not dated or not known(own_sl) or not known(opp_sl):
        return False
    last = max(dated, key=lambda g: g["sort"])
    if not known(last.get("own_sl")) or not known(last.get("opp_sl")):
        return False
    return (last["own_sl"], last["opp_sl"]) != (own_sl, opp_sl)
