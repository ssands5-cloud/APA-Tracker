"""
Command-line entry point for exporting APA league analytics to Excel.

Usage:
    python scripts/export_analytics.py --output-file league_stats.xlsx
    python scripts/export_analytics.py --output-file out.xlsx --db-path /path/to/apa.db
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.spreadsheet_builder import build_from_db
from database.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export APA league analytics to an Excel workbook."
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Path of the .xlsx file to create (default: APA_League_Analytics_<date>.xlsx)",
    )
    parser.add_argument(
        "--db-path",
        default="apa_tracker.db",
        help="Path to the SQLite database file (default: apa_tracker.db)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    db_url = f"sqlite:///{args.db_path}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)  # safe no-op if tables already exist
    Session = sessionmaker(bind=engine)

    with Session() as session:
        from database.models import Player, PlayerMatch, Team

        player_count = session.query(Player).count()
        team_count = session.query(Team).count()
        match_count = session.query(PlayerMatch).count()

        logger.info(
            "Database: %d players, %d teams, %d player-match records",
            player_count,
            team_count,
            match_count,
        )

        out_path = build_from_db(session, args.output_file)

    logger.info(
        "Exported %d players, %d teams, %d match records to %s",
        player_count,
        team_count,
        match_count,
        out_path,
    )


if __name__ == "__main__":
    main()
