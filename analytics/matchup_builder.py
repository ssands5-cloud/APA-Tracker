"""
Computes the Matchup Advantage Engine's player_matchups table from
already-ingested head-to-head history (PlayerHeadToHead).

Pulled out of scripts/build_matchups.py (a CLI entry point -- argparse,
its own logging setup, a network-adjacent config file) so this reusable
piece of business logic lives in a neutral module instead: importing a
function out of a script meant to be run standalone, the way
scripts/build_demo.py and scheduler/graphql_sync.py both need to, was the
CLI module doing double duty as a library. scripts/build_matchups.py now
just wraps this for the command line.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from analytics.matchups import (
    average_opponent_skill_level,
    average_points_earned,
    confidence_score,
    head_to_head_win_rate,
    matchup_score,
    recognized_results,
)
from analytics.skill_level_trends import skill_level_trend, skill_level_volatility
from database.ingest import ingest_matchups, prune_matchups_not_in
from database.queries import all_head_to_head, skill_level_history


def build_matchups(db: Session) -> list[dict]:
    """Group every raw head-to-head row by (player, opponent, format,
    session_name) -- P1-4: a player's 8-ball record against an opponent
    doesn't predict their 9-ball one, and a stale prior session's record
    isn't "current form" the way this session's is, so those two get their
    own matchup rows rather than being blended into one. Rows whose
    PlayerHeadToHead.format/session_name are both NULL (an older ingest,
    or a call that didn't have team context handy) still group together
    under that shared NULL/NULL bucket, same as any other real value.

    Scores each pair-in-context and upserts the result into
    player_matchups -- pruning any existing PlayerMatchup row whose exact
    (player, opponent, format, session) no longer has ANY head-to-head
    evidence first (P1-7: a match-level reconciliation in
    ingest_head_to_head() can zero out a group's history entirely, and
    this is what actually removes the now-stale aggregate rather than
    leaving it behind). Returns the rows written, for a caller's own
    summary/logging.
    """
    by_pair: dict[tuple[int, int, str, str], list] = defaultdict(list)
    for row in all_head_to_head(db):
        by_pair[(row.player_id, row.opponent_id, row.format, row.session_name)].append(row)

    prune_matchups_not_in(db, set(by_pair.keys()))

    # Trend/volatility are about the PLAYER *in this format/session*, not
    # blended across all of them -- P1-4: grouped the same way the matchup
    # itself is (player_id, format, session_name), not just player_id, or
    # an 8-ball trend would bleed into a 9-ball matchup's score. Sourced
    # via each PlayerMatch's own Match relationship, since
    # database.queries.skill_level_history() returns PlayerMatch rows,
    # not PlayerHeadToHead ones -- those don't carry format/session_name
    # directly, but every PlayerMatch that has one is match-linked.
    own_history_by_group: dict[tuple[int, str, str], list] = defaultdict(list)
    for reading in skill_level_history(db):
        match = reading.match
        key = (reading.player_id, match.format if match else None, match.session_name if match else None)
        own_history_by_group[key].append(reading)

    rows = []
    for (player_id, opponent_id, format_, session_name), h2h_rows in by_pair.items():
        player = h2h_rows[0].player
        opponent = h2h_rows[0].opponent
        own_history = own_history_by_group.get((player_id, format_, session_name), [])
        trend = skill_level_trend(own_history)
        volatility = skill_level_volatility(own_history)

        rows.append(
            {
                "player_id": player.external_id,
                "player_name": player.name,
                "opponent_id": opponent.external_id,
                "opponent_name": opponent.name,
                # P1-6: only RECOGNIZED-result games count as "played" here
                # -- an unrecognized result (see analytics.matchups) isn't
                # evidence of a game's outcome, so it shouldn't inflate
                # this count past what win_rate/matchup_score actually used.
                "matches_played": len(recognized_results(h2h_rows)),
                "win_rate": head_to_head_win_rate(h2h_rows),
                "avg_points_earned": average_points_earned(h2h_rows),
                "avg_opponent_skill_level": average_opponent_skill_level(h2h_rows),
                "trend": trend,
                "volatility": volatility,
                "matchup_score": matchup_score(h2h_rows, trend, volatility),
                "confidence_score": confidence_score(h2h_rows, trend, volatility),
                "format": format_,
                "session_name": session_name,
            }
        )

    ingest_matchups(db, rows)
    return rows
