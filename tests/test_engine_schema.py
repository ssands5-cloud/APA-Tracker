"""Stale-database detection.

`Base.metadata.create_all` creates missing tables but never ALTERS existing
ones. A database written before columns like matches.week or players.ppm
existed keeps its old shape, and the first insert dies with a bare
"sqlite3.OperationalError: no such column". These tests build a genuinely
old-shaped database and assert the failure is caught up front, with the fix
spelled out.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from database.engine import StaleSchemaError, check_schema, create_db_engine
from database.models import Base


def _make_stale_db(path):
    """A database with the right tables but an older, narrower `matches`."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        # The Match model as it was before scores and flags were added.
        conn.execute(text("""
            CREATE TABLE matches (
                id INTEGER NOT NULL PRIMARY KEY,
                external_id VARCHAR NOT NULL UNIQUE,
                home_team_id VARCHAR,
                away_team_id VARCHAR,
                home_team_name VARCHAR,
                away_team_name VARCHAR,
                location VARCHAR,
                match_date VARCHAR,
                status VARCHAR
            )
        """))
    engine.dispose()


class TestCheckSchema:
    def test_a_current_database_reports_nothing_missing(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
        Base.metadata.create_all(engine)
        assert check_schema(engine) == []

    def test_missing_columns_are_named(self, tmp_path):
        path = tmp_path / "stale.db"
        _make_stale_db(path)
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)  # adds the other tables, leaves matches alone

        missing = check_schema(engine)
        assert "matches.week" in missing
        assert "matches.home_score" in missing
        assert "matches.is_bye" in missing
        # Tables it created fresh are complete.
        assert not any(m.startswith("players.") for m in missing)

    def test_an_absent_table_is_not_reported_as_missing_columns(self, tmp_path):
        """create_all will make it; that is not a stale-schema problem."""
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        assert check_schema(engine) == []


class TestCreateDbEngineRefusesStaleFiles:
    def test_raises_with_the_columns_and_the_fix(self, tmp_path):
        path = tmp_path / "old.db"
        _make_stale_db(path)

        with pytest.raises(StaleSchemaError) as excinfo:
            create_db_engine({"database": {"path": str(path)}})

        message = str(excinfo.value)
        assert "matches.week" in message, "must name what is actually missing"
        assert "delete the file" in message, "must say how to fix it"

    def test_a_fresh_path_is_fine(self, tmp_path):
        engine = create_db_engine({"database": {"path": str(tmp_path / "sub" / "new.db")}})
        assert check_schema(engine) == []

    def test_running_twice_on_the_same_file_is_fine(self, tmp_path):
        config = {"database": {"path": str(tmp_path / "twice.db")}}
        create_db_engine(config)
        create_db_engine(config)  # must not trip its own check
