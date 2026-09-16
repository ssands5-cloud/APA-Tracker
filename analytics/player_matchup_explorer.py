"""Player Matchup Explorer: any two distinct players in the captured scope.

The existing Player-vs-Player surfaces answer "our roster against this one
opponent roster". This one answers "these two specific people", for ANY two
distinct players the database has captured -- including two opponents who
are both on other teams, which no existing view can currently show.

Two things are kept rigidly apart, because conflating them is exactly how a
tool starts inventing history:

    CAPTURED MEETINGS   real recorded PlayerHeadToHead games only. Meeting
                        count, wins/losses, dates, both skill levels as
                        they were on the night, and each individual
                        outcome. A pair with nothing captured reports
                        NO_DIRECT_MEETINGS -- never a zero that reads like
                        a measured result, and never a meeting inferred
                        from a shared match, a shared team, or anything
                        else.

    MODELED COMPARISON  analytics.head_to_head.skill_only_win_probability
                        over the two current skill levels. It is available
                        for a pair who have never met -- that is the point
                        of it -- so it is carried in its own field, labeled
                        as modeled, and never folded into the captured
                        record or presented as evidence that they played.

Purely computational, like every other analytics module here: takes
already-fetched real rows and computes. Queries nothing, imports no UI
renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from analytics.head_to_head import skill_only_win_probability

FORMULA_VERSION = "player-matchup-explorer-v1"

NO_DIRECT_MEETINGS = "No direct meetings captured"
MODELED_LABEL = "Modeled from current skill levels only -- not a record of play"


@dataclass(frozen=True)
class ExplorerPlayer:
    """One selectable player in the captured scope."""

    player_id: int
    player_external_id: str
    player_name: str
    team_external_id: str
    team_name: str
    skill_level: Optional[int]


@dataclass(frozen=True)
class ExplorerGame:
    """One real captured game between the two selected players."""

    match_id: Optional[str]
    match_date: Optional[str]
    week: Optional[int]
    own_skill_level: Optional[int]
    opponent_skill_level: Optional[int]
    result: Optional[str]
    points_earned: Optional[float]


@dataclass(frozen=True)
class ExplorerPair:
    """One ordered pair, from the first player's point of view."""

    player_id: int
    opponent_id: int
    meetings: int
    wins: int
    losses: int
    undecided: int
    games: tuple[ExplorerGame, ...]
    modeled_skill_only_probability: Optional[float]
    unavailable_reason: Optional[str]

    @property
    def has_direct_history(self) -> bool:
        return self.meetings > 0


@dataclass(frozen=True)
class PlayerMatchupExplorerDocument:
    session_name: str
    division_id: Optional[str]
    format: Optional[str]
    captured_at: Optional[str]
    formula_version: str
    players: tuple[ExplorerPlayer, ...]
    pairs: tuple[ExplorerPair, ...]
    captured_pair_count: int


def _game(row: Mapping) -> ExplorerGame:
    return ExplorerGame(
        match_id=row.get("match_id"),
        match_date=row.get("match_date"),
        week=row.get("week"),
        own_skill_level=row.get("own_skill_level"),
        opponent_skill_level=row.get("opponent_skill_level"),
        result=row.get("result"),
        points_earned=row.get("points_earned"),
    )


def build_pair(
    player: ExplorerPlayer,
    opponent: ExplorerPlayer,
    history: Sequence[Mapping],
) -> ExplorerPair:
    """One ordered pair from ``player``'s side.

    ``history`` is that pair's real captured games, already scoped and
    ordered by the caller. An empty history is a real answer -- the pair has
    no captured meetings -- not a reason to guess one.
    """
    games = tuple(_game(row) for row in history)
    wins = sum(1 for g in games if (g.result or "").upper().startswith("W"))
    losses = sum(1 for g in games if (g.result or "").upper().startswith("L"))

    return ExplorerPair(
        player_id=player.player_id,
        opponent_id=opponent.player_id,
        meetings=len(games),
        wins=wins,
        losses=losses,
        undecided=len(games) - wins - losses,
        games=games,
        # Deliberately computed for every pair, met or not: it is a current
        # skill comparison, never a claim about games played.
        modeled_skill_only_probability=skill_only_win_probability(
            player.skill_level, opponent.skill_level
        ) if player.skill_level is not None and opponent.skill_level is not None else None,
        unavailable_reason=None if games else NO_DIRECT_MEETINGS,
    )


def build_document(
    players: Sequence[Mapping],
    pair_histories: Mapping[tuple[int, int], Sequence[Mapping]],
    *,
    session_name: str,
    division_id: Optional[str] = None,
    format: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> PlayerMatchupExplorerDocument:
    """Every selectable player, and every ordered pair among them.

    ``players`` -- one dict per selectable player:
    ``player_id``/``player_external_id``/``player_name``/
    ``team_external_id``/``team_name``/``skill_level``.
    ``pair_histories`` -- ``(player_id, opponent_id)`` to that pair's real
    captured games. A pair absent from this mapping has no captured
    meetings; it is still present in the output, reported as such.
    """
    roster = tuple(
        ExplorerPlayer(
            player_id=p["player_id"],
            player_external_id=p["player_external_id"],
            player_name=p["player_name"],
            team_external_id=p.get("team_external_id", ""),
            team_name=p.get("team_name", ""),
            skill_level=p.get("skill_level"),
        )
        for p in players
    )
    ordered = sorted(roster, key=lambda p: (p.team_name, p.player_name, p.player_external_id))

    pairs: list[ExplorerPair] = []
    for player in ordered:
        for opponent in ordered:
            if player.player_id == opponent.player_id:
                continue  # a player is never their own opponent
            history = pair_histories.get((player.player_id, opponent.player_id), ())
            pairs.append(build_pair(player, opponent, history))

    return PlayerMatchupExplorerDocument(
        session_name=session_name,
        division_id=division_id,
        format=format,
        captured_at=captured_at,
        formula_version=FORMULA_VERSION,
        players=ordered,
        pairs=tuple(pairs),
        captured_pair_count=sum(1 for pair in pairs if pair.has_direct_history),
    )
