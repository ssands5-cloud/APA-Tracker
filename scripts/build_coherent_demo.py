"""Build ONE internally coherent rehearsal-fixture database.

Writes: data/demo_coherent.db

This exists because scripts/build_demo.py's own fixtures are explicitly
"several honest, separately-sourced illustrations glued into one workbook,
not a single fabricated season" (its own docstring) -- each fixture file
was written independently for one row-mapper's own unit test, so no two
players/teams/matches share a consistent identity space. That is fine for
testing an ingest function in isolation; it fails every cross-referencing
analytics module (Team Strength, Trend Analyzer, Opponent Volatility,
Player-vs-Player, Lineup Lab, Captain's Edge) because they all key off a
canonical current roster that these disjoint fixtures never populate for
the same players who also have match/skill history.

This script builds the opposite: ONE team, ONE opponent, ONE session,
ONE format, with a full canonical current roster (5 players per side),
real match history between them (6 finalized/scored matches, enough
observations to clear analytics.player_trends' own five-reading evidence
gate), real head-to-head evidence for every roster pairing, real
standings for the whole division, and one real remaining (unscored)
scheduled match -- all using the SAME player/team identities throughout,
so every builder that reads this database sees a coherent,
cross-referenceable scope.

Every identity here is clearly fictional ("Fixture Sharks" / "Fixture
Renegades" / "2026 Rehearsal Session", external ids in the 90300s) --
rehearsal data, never presented as live APA production evidence. It
reuses the exact same ingestion functions the live sync and
scripts/build_demo.py already call (database.ingest.*,
analytics.matchup_builder.build_matchups); nothing here fabricates an
ANALYTICAL RESULT -- only the real, labeled-as-fictional INPUT rows an
analytics module then computes over honestly, exactly like every other
fixture in this project.

Usage:
    python scripts/build_coherent_demo.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sqlalchemy.orm import Session

from analytics.matchup_builder import build_matchups
from database.engine import create_db_engine
from database.ingest import (
    ingest_h2h_advantage,
    ingest_head_to_head,
    ingest_match,
    ingest_match_scores,
    ingest_player_team_history,
    ingest_standings,
    upsert_player,
)
from scripts.build_head_to_head import build_rows as build_h2h_advantage_rows
from scripts.build_player_trends import build_rows as build_trend_rows
from scripts.build_player_trends import grouped_history
from database.ingest import ingest_player_trends, prune_player_trends_not_in

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEMO_DB_PATH = "data/demo_coherent.db"
DEMO_CONFIG = {"database": {"path": DEMO_DB_PATH}}

DIVISION_ID = "90300"
SESSION_NAME = "2026 Rehearsal Session"
FORMAT_NAME = "8-Ball Open"

OUR_TEAM_ID = "90301"
OUR_TEAM_NAME = "Fixture Sharks"
OPP_TEAM_ID = "90302"
OPP_TEAM_NAME = "Fixture Renegades"

# (external_id, name, current_skill) -- position order matters: position i
# on our side plays position i on the opponent side in every match below.
#
# The skill here is the player's CURRENT level: it is what the canonical
# roster row carries and therefore what the 23-Rule is checked against, and
# it equals the last entry of that player's SKILL_SCHEDULE when they have
# one (asserted by tests, so a schedule can never drift from the roster).
#
# Our five current levels total 23 exactly -- the real
# TEAM_SKILL_LEVEL_LIMIT_5 -- so Lineup Lab's best five-player assignment is
# LEGAL and the demo's primary path is a success rather than a block. The
# illegal path is kept as a real, separately-tested scenario rather than
# being the only thing the fixture can show.
OUR_ROSTER = [
    ("F001", "Ann Fixture", 6),
    ("F002", "Ben Fixture", 5),
    ("F003", "Cal Fixture", 4),
    ("F004", "Dee Fixture", 5),
    ("F005", "Eli Fixture", 3),
]
OPP_ROSTER = [
    ("F101", "Uma Sample", 5),
    ("F102", "Vik Sample", 5),
    ("F103", "Wes Sample", 4),
    ("F104", "Xia Sample", 7),
    ("F105", "Yaz Sample", 3),
]

# Six real, finalized, scored matches, home team alternating. Each entry:
# (match_id, week, home_is_us, [our_result_per_position...]).
#
# Per-position points follow one fixed rule (WIN_POINTS/LOSS_POINTS below)
# and each match's team score is the SUM of its own position points, so the
# scoresheet and the team score can never disagree -- the same internal
# consistency a real scoresheet has, rather than two independently chosen
# numbers. Results are deliberately mixed (4-2 for us, 2-4 for them): an
# undefeated fixture drives Log5 to a degenerate 100% projection, which
# would read as a modelling bug rather than a rehearsal.
WIN, LOSS = "W", "L"
WIN_POINTS, LOSS_POINTS = 3, 1
MATCHES = [
    ("90401", 1, True, [WIN, LOSS, WIN, WIN, LOSS]),    # 3 of 5 -> we win
    ("90402", 2, False, [LOSS, WIN, LOSS, WIN, LOSS]),  # 2 of 5 -> we lose
    ("90403", 3, True, [WIN, WIN, LOSS, WIN, WIN]),     # 4 of 5 -> we win
    ("90404", 4, False, [LOSS, LOSS, WIN, LOSS, WIN]),  # 2 of 5 -> we lose
    ("90405", 5, True, [WIN, WIN, WIN, LOSS, WIN]),     # 4 of 5 -> we win
    ("90406", 6, False, [WIN, LOSS, WIN, WIN, LOSS]),   # 3 of 5 -> we win
]

# Real per-week skill levels where a player's level actually moved. Six
# observations clears analytics.player_trends' own five-observation
# evidence gate, so trend_score and the HOT/COLD/NEUTRAL indicator resolve
# from real readings instead of sitting at No data. Anyone absent here
# holds their base skill every week -- a real flat history, which is a
# measured zero slope, not missing evidence.
SKILL_SCHEDULE = {
    "F001": [5, 5, 6, 6, 6, 6],   # Ann Fixture: a real, steady rise
    "F102": [6, 6, 6, 5, 5, 5],   # Vik Sample: a real, steady decline
    "F105": [3, 3, 4, 4, 3, 3],   # Yaz Sample: real movement, no net trend
}

# The remaining, real, unscored, non-bye scheduled match.
REMAINING_MATCH_ID = "90407"
REMAINING_WEEK = 7

# The rest of the division, for a real, complete standings table.
OTHER_STANDINGS = [
    {"team_name": "Corner Pocket Crew", "rank": 3, "wins": 6, "losses": 5, "points": 121.0},
    {"team_name": "Break and Run Club", "rank": 4, "wins": 5, "losses": 6, "points": 112.0},
    {"team_name": "Rail Riders", "rank": 5, "wins": 4, "losses": 7, "points": 98.0},
]


def _skill_for_match(base_skill: int, match_index: int, external_id: str) -> int:
    schedule = SKILL_SCHEDULE.get(external_id)
    return schedule[match_index] if schedule else base_skill


def build(db_path: str = DEMO_DB_PATH) -> Path:
    db_file = Path(db_path).resolve()
    if db_file.exists():
        db_file.unlink()
        logger.info("Removed previous coherent-fixture database at %s", db_file)

    engine = create_db_engine({"database": {"path": db_path}})
    with Session(engine) as db:
        our_wins = {external_id: 0 for external_id, _, _ in OUR_ROSTER}
        our_played = {external_id: 0 for external_id, _, _ in OUR_ROSTER}
        opp_wins = {external_id: 0 for external_id, _, _ in OPP_ROSTER}
        opp_played = {external_id: 0 for external_id, _, _ in OPP_ROSTER}

        our_match_wins = 0
        for match_index, (match_id, week, home_is_us, our_results) in enumerate(MATCHES):
            our_score = sum(WIN_POINTS if r == WIN else LOSS_POINTS for r in our_results)
            opp_score = sum(LOSS_POINTS if r == WIN else WIN_POINTS for r in our_results)
            if our_score > opp_score:
                our_match_wins += 1
            home_score = our_score if home_is_us else opp_score
            away_score = opp_score if home_is_us else our_score
            home_team_id = OUR_TEAM_ID if home_is_us else OPP_TEAM_ID
            away_team_id = OPP_TEAM_ID if home_is_us else OUR_TEAM_ID
            ingest_match(
                db, match_id=match_id, home_team_id=home_team_id, away_team_id=away_team_id,
                home_team_name=OUR_TEAM_NAME if home_is_us else OPP_TEAM_NAME,
                away_team_name=OPP_TEAM_NAME if home_is_us else OUR_TEAM_NAME,
                match_date=f"2026-{week:02d}-15", status="COMPLETED",
                home_score=home_score, away_score=away_score, week=week,
                is_bye=False, is_scored=True, is_finalized=True,
                format=FORMAT_NAME, session_name=SESSION_NAME,
            )

            scores = []
            h2h_rows = []
            for i, (our_ext, our_name, our_base) in enumerate(OUR_ROSTER):
                opp_ext, opp_name, opp_base = OPP_ROSTER[i]
                our_result = our_results[i]
                opp_result = LOSS if our_result == WIN else WIN
                our_points = WIN_POINTS if our_result == WIN else LOSS_POINTS
                opp_points = WIN_POINTS if opp_result == WIN else LOSS_POINTS
                our_skill = _skill_for_match(our_base, match_index, our_ext)
                opp_skill = _skill_for_match(opp_base, match_index, opp_ext)

                scores.append({
                    "player_id": our_ext, "player_name": our_name, "team_id": OUR_TEAM_ID,
                    "team_name": OUR_TEAM_NAME, "skill_level": our_skill,
                    "result": our_result, "points_earned": our_points,
                })
                scores.append({
                    "player_id": opp_ext, "player_name": opp_name, "team_id": OPP_TEAM_ID,
                    "team_name": OPP_TEAM_NAME, "skill_level": opp_skill,
                    "result": opp_result, "points_earned": opp_points,
                })
                h2h_rows.append({
                    "player_id": our_ext, "player_name": our_name,
                    "opponent_id": opp_ext, "opponent_name": opp_name,
                    "own_skill_level": our_skill, "opponent_skill_level": opp_skill,
                    "result": our_result, "points_earned": our_points,
                })
                h2h_rows.append({
                    "player_id": opp_ext, "player_name": opp_name,
                    "opponent_id": our_ext, "opponent_name": our_name,
                    "own_skill_level": opp_skill, "opponent_skill_level": our_skill,
                    "result": opp_result, "points_earned": opp_points,
                })

                our_played[our_ext] += 1
                opp_played[opp_ext] += 1
                if our_result == WIN:
                    our_wins[our_ext] += 1
                if opp_result == WIN:
                    opp_wins[opp_ext] += 1

            created, updated = ingest_match_scores(db, match_id, scores)
            h2h_count = ingest_head_to_head(db, match_id, h2h_rows)
            logger.info(
                "Match %s (week %d): %d score row(s) (%d new, %d updated), %d head-to-head row(s)",
                match_id, week, len(scores), created, updated, h2h_count,
            )

        # The real remaining schedule: one unscored, non-bye match, week 4.
        ingest_match(
            db, match_id=REMAINING_MATCH_ID, home_team_id=OUR_TEAM_ID, away_team_id=OPP_TEAM_ID,
            home_team_name=OUR_TEAM_NAME, away_team_name=OPP_TEAM_NAME,
            match_date="2026-07-15", status="SCHEDULED", week=REMAINING_WEEK,
            is_bye=False, is_scored=False, is_finalized=False,
            format=FORMAT_NAME, session_name=SESSION_NAME,
        )
        logger.info("Ingested remaining scheduled match %s (week %d)", REMAINING_MATCH_ID, REMAINING_WEEK)

        # Canonical current rosters -- the SAME external ids used above.
        for our_ext, our_name, our_base in OUR_ROSTER:
            player = upsert_player(db, our_ext, our_name)
            ingest_player_team_history(db, player, [{
                "team_id": OUR_TEAM_ID, "team_name": OUR_TEAM_NAME, "division_id": DIVISION_ID,
                "session_name": SESSION_NAME, "is_current": True, "skill_level": our_base,
                "matches_won": our_wins[our_ext], "matches_played": our_played[our_ext],
            }])
        for opp_ext, opp_name, opp_base in OPP_ROSTER:
            player = upsert_player(db, opp_ext, opp_name)
            ingest_player_team_history(db, player, [{
                "team_id": OPP_TEAM_ID, "team_name": OPP_TEAM_NAME, "division_id": DIVISION_ID,
                "session_name": SESSION_NAME, "is_current": True, "skill_level": opp_base,
                "matches_won": opp_wins[opp_ext], "matches_played": opp_played[opp_ext],
            }])
        logger.info("Ingested canonical current rosters: %d + %d player(s)", len(OUR_ROSTER), len(OPP_ROSTER))

        # Real, complete division standings (with real wins/losses this
        # time -- the earlier disjoint-fixture run's StandingsSnapshot had
        # only points/rank, which is why Season Projection showed no
        # actual record for either team).
        our_total_wins = our_match_wins
        our_total_losses = len(MATCHES) - our_total_wins
        opp_total_wins = our_total_losses
        opp_total_losses = our_total_wins
        standings_rows = [
            {"team_name": OUR_TEAM_NAME, "rank": 1, "wins": our_total_wins, "losses": our_total_losses, "points": 142.0},
            {"team_name": OPP_TEAM_NAME, "rank": 2, "wins": opp_total_wins, "losses": opp_total_losses, "points": 138.0},
            *OTHER_STANDINGS,
        ]
        ingest_standings(db, standings_rows)
        logger.info("Ingested %d standings row(s) for division %s", len(standings_rows), DIVISION_ID)

        matchup_rows = build_matchups(db)
        logger.info("build_matchups: %d matchup(s) computed", len(matchup_rows))

        h2h_advantage_rows = build_h2h_advantage_rows(db)
        h2h_advantage_written = ingest_h2h_advantage(db, h2h_advantage_rows) if h2h_advantage_rows else 0
        logger.info("player_h2h_advantage: %d row(s) written", h2h_advantage_written)

        trend_rows = build_trend_rows(db)
        trend_written = ingest_player_trends(db, trend_rows) if trend_rows else 0
        valid = set(grouped_history(db))
        pruned = prune_player_trends_not_in(db, valid)
        logger.info("player_trends: %d row(s) written, %d pruned", trend_written, pruned)

    print(f"\nCoherent rehearsal-fixture database written to {db_file}")
    print(f"Scope: team {OUR_TEAM_ID} ({OUR_TEAM_NAME}) vs {OPP_TEAM_ID} ({OPP_TEAM_NAME}), "
          f"format {FORMAT_NAME!r}, session {SESSION_NAME!r}\n")
    return db_file


if __name__ == "__main__":
    build()
