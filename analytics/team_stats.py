"""
Team-level statistics: standings trend, head-to-head records, and the
Team_Stats export sheet's aggregates (team_match_record/average_skill_level/
opponent_strength_index below).

The Team_Stats additions are deliberately narrow: built only from Match
rows, Player.skill_level, and PlayerHeadToHead rows -- three sources that
already exist and disagree with nothing else in this project. No clutch
rating, no numeric trend score, no break/run rate, no defensive-shot rate:
none of those are real fields anywhere in this project (checked against
database/models.py and every captured API query), and inventing them would
be exactly what this project has consistently refused to do elsewhere --
see docs/head_to_head.md's "Unavailable APA Fields". If a real,
honestly-computed version of any of them gets built later, it earns its
own spec; this module does not grow speculative columns to make room for
it ahead of time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from database.models import Match, Player, PlayerHeadToHead, StandingsSnapshot


@dataclass
class StandingsTrend:
    team_name: str
    rank_change: int  # negative = moved up (better), positive = moved down
    points_change: float


def compute_trend(history: list[StandingsSnapshot]) -> Optional[StandingsTrend]:
    """Compare the two most recent snapshots for a team."""
    if len(history) < 2:
        return None
    previous, current = history[-2], history[-1]
    return StandingsTrend(
        team_name=current.team_name,
        rank_change=(current.rank or 0) - (previous.rank or 0),
        points_change=round((current.points or 0.0) - (previous.points or 0.0), 2),
    )


def head_to_head(matches, opponent_name: str) -> dict:
    """Given a flat list of PlayerMatch-like records, tally results against one opponent."""
    relevant = [m for m in matches if m.opponent == opponent_name]
    wins = sum(1 for m in relevant if (m.result or "").strip().upper() == "W")
    losses = sum(1 for m in relevant if (m.result or "").strip().upper() == "L")
    return {"opponent": opponent_name, "played": len(relevant), "wins": wins, "losses": losses}


# --- Team_Stats export sheet -------------------------------------------------

@dataclass
class TeamMatchRecord:
    """One team's real record, split by home/away. `matches_played` counts
    only DECIDED matches -- scored, not a bye, and not a tie -- the same
    guard scraper.graphql_scraper.standings_rows() already applies to its
    own (API-reported) win/loss numbers, so this independently-derived
    version can never disagree with it about what counts as a real result.
    """

    matches_played: int
    wins: int
    losses: int
    home_wins: int
    home_losses: int
    away_wins: int
    away_losses: int

    @property
    def win_percentage(self) -> Optional[float]:
        """None (not 0.0) when nothing is decided yet -- an 0-0 record and
        an unmeasured one are different facts."""
        if not self.matches_played:
            return None
        return round(self.wins / self.matches_played, 3)

    @property
    def home_record(self) -> str:
        return f"{self.home_wins}-{self.home_losses}"

    @property
    def away_record(self) -> str:
        return f"{self.away_wins}-{self.away_losses}"


def team_match_record(matches: Sequence[Match], team_external_id: str) -> TeamMatchRecord:
    """A team's real win/loss record, derived from Match rows alone --
    home_score/away_score and status, per the Team_Stats request. A second,
    independent derivation from the same raw matches
    scraper.graphql_scraper.standings_rows() reads for the Standings sheet
    (StandingsSnapshot), not a replacement for it.
    """
    wins = losses = home_wins = home_losses = away_wins = away_losses = 0
    for match in matches:
        if match.is_bye:
            continue
        if match.home_score is None or match.away_score is None:
            continue
        if match.home_score == match.away_score:
            continue  # a real tie is not a decided result either way

        is_home = match.home_team_id == team_external_id
        is_away = match.away_team_id == team_external_id
        if not is_home and not is_away:
            continue

        won = (match.home_score > match.away_score) if is_home else (match.away_score > match.home_score)
        if won:
            wins += 1
            home_wins += int(is_home)
            away_wins += int(is_away)
        else:
            losses += 1
            home_losses += int(is_home)
            away_losses += int(is_away)

    return TeamMatchRecord(
        matches_played=wins + losses,
        wins=wins, losses=losses,
        home_wins=home_wins, home_losses=home_losses,
        away_wins=away_wins, away_losses=away_losses,
    )


def average_skill_level(players: Sequence[Player]) -> Optional[float]:
    """Mean of real, non-null skill_level values. None (not 0) when no
    roster member has one recorded yet."""
    levels = [p.skill_level for p in players if p.skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None


def opponent_strength_index(rows: Sequence[PlayerHeadToHead]) -> Optional[float]:
    """Mean skill level of opponents this team's players have actually
    faced, from real PlayerHeadToHead rows -- not a guess, not a league
    average, and not the same thing as the roster's own average_skill_level.
    None when nothing has been faced yet."""
    levels = [r.opponent_skill_level for r in rows if r.opponent_skill_level is not None]
    return round(sum(levels) / len(levels), 2) if levels else None
