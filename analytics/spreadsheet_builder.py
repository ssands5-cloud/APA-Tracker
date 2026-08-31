"""
Main orchestrator: queries the database, generates all analytical sheets,
and exports to an Excel workbook using openpyxl.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy.orm import Session

from analytics.sheet_generators import (
    HeadToHeadSheet,
    PlayerLifetimeSheet,
    PlayerMatchResultsSheet,
    SeasonSummarySheet,
    StandingsHistorySheet,
    TeamRosterSheet,
    TeamStatsSheet,
)
from analytics.formatting import style_sheet

logger = logging.getLogger(__name__)


class SpreadsheetBuilder:
    """Coordinates data aggregation from a database session and exports to Excel."""

    SHEET_CONFIGS = [
        ("SEASON_SUMMARY", SeasonSummarySheet),
        ("PLAYER_LIFETIME", PlayerLifetimeSheet),
        ("PLAYER_MATCH_RESULTS", PlayerMatchResultsSheet),
        ("TEAM_STATS", TeamStatsSheet),
        ("TEAM_ROSTER", TeamRosterSheet),
        ("HEAD_TO_HEAD", HeadToHeadSheet),
        ("STANDINGS_HISTORY", StandingsHistorySheet),
    ]

    def __init__(self, db: Session) -> None:
        self._db = db
        self._workbook = openpyxl.Workbook()
        # Remove the default empty sheet
        default = self._workbook.active
        if default is not None:
            self._workbook.remove(default)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_all_sheets(self) -> None:
        """Generate every analytical sheet and populate the workbook."""
        for sheet_name, generator_cls in self.SHEET_CONFIGS:
            logger.info("Building sheet: %s", sheet_name)
            try:
                generator = generator_cls(self._db)
                rows = generator.rows()
                self._write_sheet(sheet_name, generator.headers, rows)
                logger.info("  → %d rows written to %s", len(rows), sheet_name)
            except Exception:
                logger.exception("Failed to build sheet %s", sheet_name)
                raise

    def export_to_excel(self, filepath: str | Path) -> Path:
        """Save the workbook to *filepath* and return the resolved Path."""
        out = Path(filepath)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._workbook.save(str(out))
        logger.info("Workbook saved to %s", out.resolve())
        return out.resolve()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_sheet(
        self, sheet_name: str, headers: list[str], rows: list[dict[str, Any]]
    ) -> None:
        ws = self._workbook.create_sheet(title=sheet_name)
        style_sheet(ws, headers)

        for row_data in rows:
            ws.append([row_data.get(h) for h in headers])


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def build_from_db(db: Session, output_path: str | Path | None = None) -> Path:
    """
    Build the full analytics workbook from *db* and write it to *output_path*.

    If *output_path* is None a timestamped filename is created in the current
    working directory.

    Returns the resolved path of the created file.
    """
    if output_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_path = Path(f"APA_League_Analytics_{stamp}.xlsx")

    builder = SpreadsheetBuilder(db)
    builder.build_all_sheets()
    return builder.export_to_excel(output_path)
