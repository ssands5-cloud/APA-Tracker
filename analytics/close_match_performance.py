"""Close-Match Win Rate -- docs/planned_analytics_design.md.

Replaces what earlier drafts called "Clutch Rating". Renamed on purpose:
this measures a real, narrow thing -- win rate specifically in team
matches that were close -- not poise or pressure performance in general,
and must never be labeled more strongly than what it actually is.

What's real and what isn't, checked against database/models.py and every
captured API query before this was written: APA's data has no field for
which individual game within a team match was the deciding one, or the
score at the time a given game was played (PlayerHeadToHead.match's own
matchPositionNumber-derived pairing is a fixed roster-position assignment,
not temporal sequence). What IS real: the team match's own final margin
(Match.home_score/away_score) and which individual games a specific
player won or lost within that match (PlayerHeadToHead). This module uses
only those two real, already-ingested sources -- no new upstream export,
no new pipeline stage.

Both the close-match subset and the "overall" baseline it shrinks toward
are derived from the SAME real PlayerHeadToHead population passed in, so
they can never disagree about which games happened -- the same discipline
analytics.head_to_head and analytics.matchups already apply by sharing one
source of raw rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from analytics.matchups import reliability_weight
from database.models import Match, PlayerHeadToHead

CLOSE_MATCH_MARGIN = 4
"""Not a fitted value -- checked against this project's own real data, not
picked blind. The 14 decided team matches in the database when this was
written had margins [2, 2, 2, 4, 5, 6, 6, 8, 9, 10, 14, 14, 21, 28]
(median 8); 4 is the real bottom quartile of matches actually played, not
an arbitrary round number. Genuinely provisional: 14 matches is a small
sample, and 8-ball/9-ball divisions may play to different point totals,
which could argue for a per-format threshold once there's enough data in
each to check that separately. See docs/planned_analytics_design.md."""

CLOSE_MATCH_MIN_SAMPLE = 3
"""Fewer DISTINCT close matches (by match_id, not PlayerHeadToHead rows --
see CloseMatchPerformance's own docstring for why those can differ) than
this and there is no real signal yet -- None, not a guess, same as
volatility/regression_slope elsewhere."""


def _is_win(result) -> Optional[bool]:
    """True/False for a recognised W/L result, None otherwise. Same rule
    as analytics.matchups._is_win, restated locally rather than importing
    a function whose leading underscore marks it module-private."""
    normalized = str(result or "").strip().upper()
    if normalized == "W":
        return True
    if normalized == "L":
        return False
    return None


def is_close_match(match: Optional[Match]) -> bool:
    """True only for a real, decided, CONFIRMED, close result.

    Excludes, in order: a missing Match row; a bye (no real opponent to be
    close against); a match that isn't scored, or is scored but not yet
    `is_finalized` (per Match's own docstring, "is_finalized marks a
    result the league has confirmed; is_scored alone can still change" --
    an unconfirmed score is not decided evidence yet); a missing score on
    either side; and a tie (not a decided result either way, the same
    guard analytics.team_stats.team_match_record already applies to what
    counts as decided for Team_Stats -- now applied here too, so the two
    can never disagree about which matches are real, decided results).
    """
    if match is None:
        return False
    if match.is_bye:
        return False
    if not match.is_scored or not match.is_finalized:
        return False
    if match.home_score is None or match.away_score is None:
        return False
    if match.home_score == match.away_score:
        return False
    return abs(match.home_score - match.away_score) <= CLOSE_MATCH_MARGIN


@dataclass
class CloseMatchPerformance:
    """One player's real close-match record, and the shrunk estimate
    derived from it.

    `close_matches_played` counts DISTINCT real team matches (by
    match_id), not PlayerHeadToHead rows -- a player can legitimately play
    more than one individual game within a single team match (confirmed
    against a real scoresheet: match 51007724, where Rob Stegall played
    two different opponents in the same match; see PlayerHeadToHead's own
    docstring in database/models.py). Counting rows would let one close
    team match masquerade as several independent pieces of evidence.
    `close_games_played` is the row count, kept separately since
    `close_win_rate` is genuinely a per-game rate (each game is a real,
    independent result) -- only the SAMPLE-SIZE gate (is there enough
    evidence to trust this at all) needs distinct matches.

    `overall_matches_played` counts recognised-result games (rows), the
    same convention every other win-rate figure in this project uses --
    the overall baseline was never the thing under dispute here.
    """

    close_matches_played: int
    close_games_played: int
    close_win_rate: Optional[float]
    overall_matches_played: int
    overall_win_rate: Optional[float]
    shrunk_win_rate: Optional[float]


def close_match_performance(rows: Sequence[PlayerHeadToHead]) -> CloseMatchPerformance:
    """`rows` is one player's REAL PlayerHeadToHead rows -- every game, not
    pre-filtered to close ones; the close-match subset and the overall
    baseline both come from this same list.

    `shrunk_win_rate` is None whenever either input it needs is missing:
    fewer than CLOSE_MATCH_MIN_SAMPLE DISTINCT close matches, or no
    overall win rate to shrink toward at all (no recognised results of any
    kind).
    """
    recognized = [r for r in rows if _is_win(r.result) is not None]
    overall_n = len(recognized)
    overall_wins = sum(1 for r in recognized if _is_win(r.result))
    overall_win_rate = round(overall_wins / overall_n, 3) if overall_n else None

    close = [r for r in recognized if is_close_match(r.match)]
    close_games = len(close)
    close_matches = len({r.match_id for r in close})
    close_wins = sum(1 for r in close if _is_win(r.result))
    close_win_rate = round(close_wins / close_games, 3) if close_games else None

    shrunk_win_rate = None
    if close_matches >= CLOSE_MATCH_MIN_SAMPLE and overall_win_rate is not None:
        weight = reliability_weight(close_matches)
        shrunk_win_rate = round(weight * close_win_rate + (1 - weight) * overall_win_rate, 3)

    return CloseMatchPerformance(
        close_matches_played=close_matches,
        close_games_played=close_games,
        close_win_rate=close_win_rate,
        overall_matches_played=overall_n,
        overall_win_rate=overall_win_rate,
        shrunk_win_rate=shrunk_win_rate,
    )


CLOSE_MATCH_BAND_MARGIN = 0.10
"""A heuristic, not a fitted value: how far the shrunk close-match rate has
to sit from the player's own overall rate (in percentage points) before
labelling it "Strong" or "Struggles" rather than "Even". Self-relative on
purpose -- a player is compared to their own normal level, not to a
league-wide bar, since close-match performance is about a player's own
close-match tendency, not their overall skill."""


def close_match_band(shrunk_win_rate: Optional[float], overall_win_rate: Optional[float]) -> str:
    """"Strong" / "Even" / "Struggles" / "Unknown" -- Unknown whenever
    either rate is missing (fewer than CLOSE_MATCH_MIN_SAMPLE close
    matches, or no overall record at all), never a guessed band. Shared by
    both export surfaces (ui.export_excel, ui.export_json) so the workbook
    and the JSON document can never label the same player differently.
    """
    if shrunk_win_rate is None or overall_win_rate is None:
        return "Unknown"
    diff = shrunk_win_rate - overall_win_rate
    if diff >= CLOSE_MATCH_BAND_MARGIN:
        return "Strong"
    if diff <= -CLOSE_MATCH_BAND_MARGIN:
        return "Struggles"
    return "Even"
