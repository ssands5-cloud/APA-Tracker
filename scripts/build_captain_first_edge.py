"""Build Tonight's Match: the captain-first evidence-matrix application.

Writes one self-contained artifact from the existing SQLite database:

    exports/captain_first_edge.html   opens with no server, no Python

This is Stage 2 of docs/captain_first_edge_experience.md. It is a REPORTER
over Stage 1's own classifier (analytics.pairing_evidence): every real
scheduled match between the configured team and a real opponent becomes one
selectable (session, opponent, format) scope, and
analytics.pairing_evidence.build_pairing_evidence_matrix computes each
scope's real evidence matrix. Nothing here recomputes a label, a rate, or a
probability -- see ui/tabs/tonights_match.py for the rendering, which is
equally a pure reporter.

The database is opened read-only (mode=ro), the same connection factory
scripts/build_captains_edge.py already uses -- this script cannot write to,
migrate, or create the real data file, and does NOT use
database.engine.create_db_engine() (which calls Base.metadata.create_all(),
a write). A database written before PlayerTeamHistory.team_external_id
existed is reported as unavailable using SQLite's underlying reason, without
exposing the failed SQL statement or pretending that no match was scheduled.
This script does not paper over that with a migration;
docs/captain_first_edge_experience.md and database/engine.py already say the
real fix is to regenerate the database from the API.

A scope this script could not evaluate (an ambiguous canonical roster or a
database query failure, for example) is still listed in the opponent/format
selectors, with its real reason shown instead of a matrix -- never silently
dropped. A genuinely absent roster is represented by Stage 1's side-specific
availability flags and named explicitly in the page.

Usage:
    python scripts/build_captain_first_edge.py
    python scripts/build_captain_first_edge.py --db path/to/apa.db
    python scripts/build_captain_first_edge.py --our-team-id 13082948
    python scripts/build_captain_first_edge.py --out-dir exports
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# ``python scripts/build_captain_first_edge.py`` is a documented operator
# command. In that direct-file mode Python puts only ``scripts/`` on
# sys.path, so the sibling ``analytics``/``database``/``ui`` packages would
# otherwise be unimportable. Module mode already has the project root
# present; this mirrors scripts/build_lineups.py's own shim so both entry
# points work identically.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.pairing_evidence import PairingEvidenceError, build_pairing_evidence_matrix
from database.models import Match, Team
from database.queries import CanonicalRosterError
from scripts.build_captains_edge import NoDatabaseError, connect_read_only, resolve_db_path
from ui.tabs.tonights_match import MatchScope, render

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
HTML_NAME = "captain_first_edge.html"


def _configured_our_team_id() -> Optional[str]:
    """team.team_id from apa_config.yaml, the same real field every other
    entry point in this project already treats as "ours". Advisory, like
    scripts/build_captains_edge.py's own config read -- a malformed or
    absent config is not fatal given --our-team-id."""
    config_path = PROJECT_ROOT / "apa_config.yaml"
    if not config_path.is_file():
        return None
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        logger.debug("Could not read %s for team_id", config_path)
        return None
    team_id = (config.get("team") or {}).get("team_id")
    return str(team_id) if team_id else None


def _team_name(db: Session, team_external_id: str) -> str:
    """The real display name for a team id, when this project has ever
    scraped one. Named honestly as unresolved rather than guessed when it
    hasn't -- a captain planning against an opponent whose roster was never
    scraped still deserves to see that opponent's real id."""
    team = db.query(Team).filter_by(external_id=team_external_id).one_or_none()
    if team is not None:
        return team.name
    return f"Unresolved team (id: {team_external_id})"


def _database_error(exc: SQLAlchemyError) -> str:
    """Expose the underlying database reason without leaking SQL/parameters."""
    underlying = getattr(exc, "orig", None)
    return f"{type(underlying or exc).__name__}: {underlying or exc}"


def real_match_scopes(db: Session, our_team_external_id: str) -> list[tuple[str, str, str]]:
    """Every real, distinct (session_name, opponent_team_external_id, format)
    combination from a real scheduled Match involving the configured team.

    Excludes byes (no real opponent) and rows missing format/session -- a
    combination this page cannot even name is not offered. Included
    regardless of is_scored/is_finalized: a captain planning for an
    upcoming, not-yet-played match is exactly who Tonight's Match is for;
    build_pairing_evidence_matrix's own DIRECT gate (which DOES require a
    scored/finalized match) governs the evidence inside each scope, not
    which scopes exist.
    """
    rows = (
        db.query(Match)
        .filter(
            Match.is_bye.is_(False),
            Match.format.isnot(None),
            Match.session_name.isnot(None),
        )
        .filter(
            (Match.home_team_id == our_team_external_id)
            | (Match.away_team_id == our_team_external_id)
        )
        .all()
    )
    scopes: set[tuple[str, str, str]] = set()
    for match in rows:
        opponent = (
            match.away_team_id
            if match.home_team_id == our_team_external_id
            else match.home_team_id
        )
        if not opponent:
            continue
        session_name = str(match.session_name or "").strip()
        format_name = str(match.format or "").strip()
        if not session_name or not format_name:
            continue
        scopes.add((session_name, opponent, format_name))
    return sorted(scopes)


def build_match_scopes(db: Session, our_team_external_id: str) -> list[MatchScope]:
    """Classify every real scope this database can name. A scope whose
    matrix could not be built (an ambiguous or absent canonical roster) is
    still returned, with its real reason -- see PairingEvidenceError /
    CanonicalRosterError."""
    scopes = []
    for session_name, opponent_team_external_id, format in real_match_scopes(
        db, our_team_external_id
    ):
        opponent_team_name = _team_name(db, opponent_team_external_id)
        try:
            matrix = build_pairing_evidence_matrix(
                db,
                our_team_external_id=our_team_external_id,
                opponent_team_external_id=opponent_team_external_id,
                format=format,
                session_name=session_name,
            )
            scopes.append(
                MatchScope(
                    session_name=session_name,
                    opponent_team_external_id=opponent_team_external_id,
                    opponent_team_name=opponent_team_name,
                    format=format,
                    matrix=matrix,
                )
            )
        except (PairingEvidenceError, CanonicalRosterError, ValueError, SQLAlchemyError) as exc:
            reason = _database_error(exc) if isinstance(exc, SQLAlchemyError) else str(exc)
            scopes.append(
                MatchScope(
                    session_name=session_name,
                    opponent_team_external_id=opponent_team_external_id,
                    opponent_team_name=opponent_team_name,
                    format=format,
                    matrix=None,
                    unavailable_reason=reason,
                )
            )
    return scopes


def build(db: Session, our_team_external_id: str, out_dir: Path) -> Path:
    try:
        our_team_name = _team_name(db, our_team_external_id)
        scopes = build_match_scopes(db, our_team_external_id)
        html = render(
            scopes,
            our_team_name,
            our_team_external_id=our_team_external_id,
        )
    except SQLAlchemyError as exc:
        html = render(
            [],
            f"Configured team (id: {our_team_external_id})",
            our_team_external_id=our_team_external_id,
            page_unavailable_reason=_database_error(exc),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / HTML_NAME
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to the SQLite database (default: configured/fallback path)")
    parser.add_argument("--our-team-id", help="Override apa_config.yaml's team.team_id")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory to write into")
    args = parser.parse_args(argv)

    try:
        db_path = resolve_db_path(args.db)
    except NoDatabaseError as exc:
        logger.error(str(exc))
        return 1

    our_team_external_id = args.our_team_id or _configured_our_team_id()
    if not our_team_external_id:
        logger.error(
            "No team id given. Set apa_config.yaml's team.team_id, or pass --our-team-id."
        )
        return 1

    logger.info("Reading %s", db_path)
    engine = create_engine("sqlite://", creator=lambda: connect_read_only(db_path))
    db = Session(bind=engine)
    try:
        try:
            out_path = build(db, our_team_external_id, Path(args.out_dir))
        except OSError as exc:
            logger.error("Could not write Captain's Edge HTML: %s", exc)
            return 1
    finally:
        db.close()
        engine.dispose()

    logger.info("Wrote %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
