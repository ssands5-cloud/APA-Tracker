"""Offline, row-scoped historical identity repair for Ultimate Coach.

This repairs already-ingested historical staging data without querying APA.
Unlike the older current-roster repair, it resolves each player-match scope
against exact historical team + session roster provenance and never applies a
global alias-player rewrite across unrelated matches.

Dry run is the default. Apply mode must be explicit.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Match, Player, PlayerHeadToHead, PlayerMatch
from database.queries import resolve_roster_identity


@dataclass
class HistoricalIdentityRepairReport:
    scopes_examined: int = 0
    scopes_resolved_unique: int = 0
    scopes_already_canonical: int = 0
    scopes_rewrite_planned: int = 0
    scopes_unresolved: int = 0
    scopes_blocked_collision: int = 0
    duplicate_alias_match_scopes: int = 0
    player_match_rows_rewritten: int = 0
    h2h_rows_examined: int = 0
    h2h_id_fields_rewrite_planned: int = 0
    h2h_id_fields_rewritten: int = 0
    h2h_rows_blocked_self_pairing: int = 0
    unresolved_scopes: list[dict[str, Any]] = field(default_factory=list)
    blocked_scopes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def resolution_rate(self) -> float | None:
        if not self.scopes_examined:
            return None
        return round(self.scopes_resolved_unique / self.scopes_examined, 4)

    def to_dict(self, *, applied: bool) -> dict[str, Any]:
        data = asdict(self)
        data["resolution_rate"] = self.resolution_rate
        data["applied"] = bool(applied)
        data["schema"] = "ultimate-coach-historical-identity-repair-v1"
        data["identity_scope_rule"] = "EXACT_TEAM_SESSION_MATCH_SCOPE"
        data["network_used"] = False
        data["probability_publication"] = "FORBIDDEN"
        return data


def _player_match_scope_rows(
    db: Session,
) -> list[tuple[PlayerMatch, Match, Player]]:
    return (
        db.query(PlayerMatch, Match, Player)
        .join(Match, Match.id == PlayerMatch.match_id)
        .join(Player, Player.id == PlayerMatch.player_id)
        .filter(
            PlayerMatch.match_id.isnot(None),
            PlayerMatch.team_id.isnot(None),
            PlayerMatch.team_id != "",
        )
        .order_by(PlayerMatch.match_id, PlayerMatch.player_id, PlayerMatch.id)
        .all()
    )


def _scope_detail(
    player_match: PlayerMatch,
    match: Match,
    player: Player,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "player_match_id": player_match.id,
        "match_id": match.id,
        "match_external_id": match.external_id,
        "alias_player_id": player.id,
        "alias_external_id": player.external_id,
        "display_name": player.name,
        "team_id": player_match.team_id,
        "session_name": match.session_name,
        "reason": reason,
    }
    row.update(extra)
    return row


def repair_historical_identities(
    db: Session,
    *,
    apply: bool = False,
) -> HistoricalIdentityRepairReport:
    """Resolve and optionally rewrite historical identity rows safely.

    Resolution uses current_only=False because historical roster memberships
    are deliberately not marked current. Every rewrite is scoped by both the
    alias Player.id and Match.id. A source scope is blocked if a canonical
    PlayerMatch already exists for the target match or if multiple alias
    scopes would collapse onto the same canonical player-match target.
    """
    report = HistoricalIdentityRepairReport()
    raw_rows = _player_match_scope_rows(db)

    groups: dict[tuple[int, int], list[tuple[PlayerMatch, Match, Player]]] = {}
    for player_match, match, player in raw_rows:
        groups.setdefault((player.id, match.id), []).append((player_match, match, player))

    report.scopes_examined = len(groups)

    scope_resolution: dict[tuple[int, int], int] = {}
    scope_row: dict[tuple[int, int], tuple[PlayerMatch, Match, Player]] = {}
    proposed_rewrites: dict[tuple[int, int], int] = {}

    for key in sorted(groups):
        rows = groups[key]
        player_match, match, player = rows[0]
        scope_row[key] = (player_match, match, player)

        if len(rows) != 1:
            report.duplicate_alias_match_scopes += 1
            report.scopes_blocked_collision += 1
            report.blocked_scopes.append(
                _scope_detail(
                    player_match,
                    match,
                    player,
                    "DUPLICATE_ALIAS_MATCH_SCOPE",
                    row_count=len(rows),
                )
            )
            continue

        session_name = str(match.session_name or "").strip()
        if not session_name:
            report.scopes_unresolved += 1
            report.unresolved_scopes.append(
                _scope_detail(player_match, match, player, "MISSING_SESSION_SCOPE")
            )
            continue

        resolved = resolve_roster_identity(
            db,
            player_match.team_id,
            session_name,
            player.name,
            current_only=False,
        )
        if resolved is None:
            report.scopes_unresolved += 1
            report.unresolved_scopes.append(
                _scope_detail(
                    player_match,
                    match,
                    player,
                    "NO_UNIQUE_HISTORICAL_ROSTER_IDENTITY",
                )
            )
            continue

        report.scopes_resolved_unique += 1
        scope_resolution[key] = resolved.id
        if resolved.id == player.id:
            report.scopes_already_canonical += 1
            continue

        existing_target = (
            db.query(PlayerMatch)
            .filter(
                PlayerMatch.match_id == match.id,
                PlayerMatch.player_id == resolved.id,
                PlayerMatch.id != player_match.id,
            )
            .count()
        )
        if existing_target:
            report.scopes_blocked_collision += 1
            report.blocked_scopes.append(
                _scope_detail(
                    player_match,
                    match,
                    player,
                    "CANONICAL_PLAYER_MATCH_ALREADY_EXISTS",
                    resolved_player_id=resolved.id,
                    existing_target_rows=existing_target,
                )
            )
            scope_resolution.pop(key, None)
            continue

        proposed_rewrites[key] = resolved.id

    target_to_sources: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for source_key, resolved_id in proposed_rewrites.items():
        _, match_id = source_key
        target_to_sources.setdefault((resolved_id, match_id), []).append(source_key)

    blocked_multi_sources: set[tuple[int, int]] = set()
    for target_key, source_keys in target_to_sources.items():
        if len(source_keys) <= 1:
            continue
        for source_key in source_keys:
            blocked_multi_sources.add(source_key)
            scope_resolution.pop(source_key, None)
            proposed_rewrites.pop(source_key, None)
            player_match, match, player = scope_row[source_key]
            report.scopes_blocked_collision += 1
            report.blocked_scopes.append(
                _scope_detail(
                    player_match,
                    match,
                    player,
                    "MULTIPLE_ALIAS_SCOPES_TO_SAME_CANONICAL_MATCH",
                    resolved_player_id=target_key[0],
                    source_scope_count=len(source_keys),
                )
            )

    h2h_rows = db.query(PlayerHeadToHead).order_by(PlayerHeadToHead.id).all()
    report.h2h_rows_examined = len(h2h_rows)

    # First pass: if any proposed identity rewrite would collapse a real H2H
    # row into player==opponent, block the ENTIRE source player/match scope.
    # Blocking only the H2H row while still rewriting PlayerMatch would leave
    # the database internally inconsistent.
    self_pair_blocked_scopes: set[tuple[int, int]] = set()
    for row in h2h_rows:
        player_scope = (row.player_id, row.match_id)
        opponent_scope = (row.opponent_id, row.match_id)
        player_target = scope_resolution.get(player_scope, row.player_id)
        opponent_target = scope_resolution.get(opponent_scope, row.opponent_id)
        player_changed = player_target != row.player_id
        opponent_changed = opponent_target != row.opponent_id
        if not player_changed and not opponent_changed:
            continue
        if player_target != opponent_target:
            continue

        report.h2h_rows_blocked_self_pairing += 1
        if player_changed and player_scope in proposed_rewrites:
            self_pair_blocked_scopes.add(player_scope)
        if opponent_changed and opponent_scope in proposed_rewrites:
            self_pair_blocked_scopes.add(opponent_scope)

    for source_key in sorted(self_pair_blocked_scopes):
        resolved_id = proposed_rewrites.pop(source_key, None)
        scope_resolution.pop(source_key, None)
        if resolved_id is None:
            continue
        player_match, match, player = scope_row[source_key]
        report.scopes_blocked_collision += 1
        report.blocked_scopes.append(
            _scope_detail(
                player_match,
                match,
                player,
                "H2H_SELF_PAIRING_AFTER_RESOLUTION",
                resolved_player_id=resolved_id,
            )
        )

    report.scopes_rewrite_planned = len(proposed_rewrites)

    # Second pass: build the actual H2H rewrite plan from only still-approved
    # scope mappings.
    h2h_plan: list[tuple[PlayerHeadToHead, int, int]] = []
    for row in h2h_rows:
        player_target = scope_resolution.get((row.player_id, row.match_id), row.player_id)
        opponent_target = scope_resolution.get((row.opponent_id, row.match_id), row.opponent_id)
        player_changed = player_target != row.player_id
        opponent_changed = opponent_target != row.opponent_id
        if not player_changed and not opponent_changed:
            continue
        if player_target == opponent_target:
            # Defensive only: all changed scopes capable of this should have
            # been removed in the first pass.
            continue
        report.h2h_id_fields_rewrite_planned += int(player_changed) + int(opponent_changed)
        h2h_plan.append((row, player_target, opponent_target))

    if not apply:
        return report

    for row, player_target, opponent_target in h2h_plan:
        if row.player_id != player_target:
            row.player_id = player_target
            report.h2h_id_fields_rewritten += 1
        if row.opponent_id != opponent_target:
            row.opponent_id = opponent_target
            report.h2h_id_fields_rewritten += 1

    for source_key, resolved_id in sorted(proposed_rewrites.items()):
        player_match, _, _ = scope_row[source_key]
        if player_match.player_id != resolved_id:
            player_match.player_id = resolved_id
            report.player_match_rows_rewritten += 1

    db.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to Ultimate Coach SQLite staging database")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply row-scoped rewrites. Without this flag the command is dry-run only.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path.",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"No database at {db_path}")
        return 1

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as db:
        report = repair_historical_identities(db, apply=args.apply)
    engine.dispose()

    payload = report.to_dict(applied=args.apply)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(
        f"{mode}: scopes={report.scopes_examined}, "
        f"resolved={report.scopes_resolved_unique}, "
        f"rewrite_planned={report.scopes_rewrite_planned}, "
        f"unresolved={report.scopes_unresolved}, "
        f"blocked={report.scopes_blocked_collision}, "
        f"h2h_fields_planned={report.h2h_id_fields_rewrite_planned}"
    )
    if not args.apply:
        print("Dry run only. Review the report before using --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
