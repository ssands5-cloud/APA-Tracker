"""Tests for the Player Trend Analyzer.

Covers every case the governing spec's test list names: regression (rising,
falling, flat, a known irregular slope, insufficient data), volatility (known
fixture, exactly 20, more than 20 with older excluded, insufficient data),
stability (0, 1, None), hot/cold (boundaries, neutral, insufficient
evidence), probability (positive, negative, zero, high volatility,
insufficient evidence), the builder (persistence, idempotency, stale
pruning), the UI (headers, sorting, formatting, "No data") and Excel
(headers, formatting, conditional formatting).

Numeric assertions are cross-checked against an independent computation --
``statistics.stdev``, or the formula written longhand -- rather than against
numbers this implementation happened to produce.
"""

from __future__ import annotations

import itertools
import math
import statistics

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.player_trends import (
    COLD,
    COLD_SLOPE_MAX,
    HOT,
    HOT_SLOPE_MIN,
    MIN_SAMPLE_SIZE_CLASSIFICATION,
    NEUTRAL,
    PROBABILITY_SAMPLE_CAP,
    STABLE_VOLATILITY_MAX,
    VOLATILITY_WINDOW,
    evaluate,
    hot_cold_flag,
    normalize_format,
    projected_sl_change_probability,
    regression_slope,
    sl_stability,
    volatility,
)
from database.ingest import ingest_player_trends, prune_player_trends_not_in
from database.models import Base, Match, Player, PlayerMatch, PlayerTrend
from scripts.build_player_trends import build_rows, grouped_history, run
from ui.tabs.trends import COLUMNS, NO_DATA, load_rows, render, row_class


# =============================================================================
# Regression slope
# =============================================================================

class TestRegressionSlope:
    def test_rising(self):
        assert regression_slope([4, 5, 6]) == pytest.approx(1.0)

    def test_falling(self):
        assert regression_slope([6, 5, 4]) == pytest.approx(-1.0)

    def test_flat(self):
        assert regression_slope([5, 5, 5, 5]) == 0.0

    def test_irregular_known_slope(self):
        """Cross-checked against least squares written longhand, not against
        this implementation's own output."""
        ys = [4, 4, 5, 5, 6, 6, 6]
        n = len(ys)
        xs = list(range(1, n + 1))
        expected = ((n * sum(x * y for x, y in zip(xs, ys)) - sum(xs) * sum(ys))
                    / (n * sum(x * x for x in xs) - sum(xs) ** 2))
        assert regression_slope(ys) == pytest.approx(expected, abs=1e-6)

    def test_insufficient_data(self):
        assert regression_slope([5]) is None
        assert regression_slope([]) is None

    def test_two_observations_are_enough(self):
        assert regression_slope([4, 5]) == pytest.approx(1.0)

    def test_missing_levels_are_excluded_not_zeroed(self):
        assert regression_slope([4, None, 6]) == pytest.approx(regression_slope([4, 6]))

    def test_it_is_not_capped_at_the_volatility_window(self):
        """The slope uses ALL observations; volatility uses the last 20.
        A long flat history then a jump must not read as the jump alone."""
        long_history = [3] * 30 + [7]
        assert regression_slope(long_history) != regression_slope(long_history[-20:])


# =============================================================================
# Volatility
# =============================================================================

class TestVolatility:
    def test_known_fixture(self):
        levels = [4, 4, 5, 5, 6]
        assert volatility(levels) == pytest.approx(statistics.stdev(levels), abs=1e-6)

    def test_it_is_sample_not_population(self):
        """ddof=1. The two differ materially at small n, and picking the
        wrong one would shift every stability and probability downstream."""
        levels = [4, 6]
        assert volatility(levels) == pytest.approx(statistics.stdev(levels), abs=1e-6)
        assert volatility(levels) != pytest.approx(statistics.pstdev(levels), abs=1e-6)

    def test_exactly_twenty_observations(self):
        levels = [4, 5] * 10
        assert len(levels) == VOLATILITY_WINDOW
        assert volatility(levels) == pytest.approx(statistics.stdev(levels), abs=1e-6)

    def test_more_than_twenty_excludes_the_older_ones(self):
        """A settled recent stretch must not be dragged by ancient history."""
        older_noise = [2, 7] * 10          # wildly volatile, 20 observations
        recent_calm = [5] * VOLATILITY_WINDOW
        assert volatility(older_noise + recent_calm) == 0.0

    def test_the_window_is_the_last_twenty_exactly(self):
        levels = list(range(1, 31))
        assert volatility(levels) == pytest.approx(
            statistics.stdev(levels[-VOLATILITY_WINDOW:]), abs=1e-6
        )

    def test_insufficient_data(self):
        assert volatility([5]) is None
        assert volatility([]) is None

    def test_an_unchanged_level_has_zero_spread(self):
        assert volatility([5, 5, 5]) == 0.0


# =============================================================================
# SL stability
# =============================================================================

class TestStability:
    def test_volatility_zero(self):
        assert sl_stability(0.0) == 1.0

    def test_volatility_one(self):
        assert sl_stability(1.0) == 0.5

    def test_volatility_none(self):
        assert sl_stability(None) is None

    def test_it_falls_as_volatility_rises(self):
        assert sl_stability(0.2) > sl_stability(0.9)

    def test_it_matches_the_formula(self):
        assert sl_stability(0.5477) == pytest.approx(1 / 1.5477, abs=1e-6)


# =============================================================================
# Hot / Cold / Neutral
# =============================================================================

class TestHotCold:
    def test_boundary_values_are_inclusive(self):
        assert hot_cold_flag(HOT_SLOPE_MIN, STABLE_VOLATILITY_MAX, 5) == HOT
        assert hot_cold_flag(COLD_SLOPE_MAX, STABLE_VOLATILITY_MAX, 5) == COLD

    def test_just_inside_the_boundary_is_neutral(self):
        assert hot_cold_flag(HOT_SLOPE_MIN - 0.001, 0.1, 10) == NEUTRAL
        assert hot_cold_flag(COLD_SLOPE_MAX + 0.001, 0.1, 10) == NEUTRAL

    def test_volatility_just_over_the_ceiling_is_neutral(self):
        """Both conditions are required: a steep slope through an erratic
        skill level is noise, not a trend."""
        assert hot_cold_flag(0.5, STABLE_VOLATILITY_MAX + 0.001, 10) == NEUTRAL

    def test_neutral(self):
        assert hot_cold_flag(0.0, 0.1, 10) == NEUTRAL

    def test_insufficient_sample_is_null_not_neutral(self):
        """NULL and NEUTRAL are different claims: unmeasured versus measured
        and unremarkable."""
        assert hot_cold_flag(0.5, 0.1, MIN_SAMPLE_SIZE_CLASSIFICATION - 1) is None

    def test_missing_volatility_is_null(self):
        assert hot_cold_flag(0.5, None, 10) is None

    def test_the_flag_values_are_uppercase(self):
        assert hot_cold_flag(0.5, 0.1, 10) == "HOT"
        assert hot_cold_flag(-0.5, 0.1, 10) == "COLD"
        assert hot_cold_flag(0.0, 0.1, 10) == "NEUTRAL"


# =============================================================================
# Projected SL-change probability
# =============================================================================

class TestProjectedProbability:
    def test_positive_slope(self):
        slope, sigma, n = 0.3, 0.2, 10
        expected = 0.5 * math.tanh(4 * slope) * (1 - sigma) * (n / 20)
        assert projected_sl_change_probability(slope, sigma, n) == pytest.approx(
            expected, abs=1e-6
        )

    def test_negative_slope_clamps_to_zero(self):
        """The heuristic describes UPWARD pressure only; direction lives in
        regression_slope, stored beside it."""
        assert projected_sl_change_probability(-0.5, 0.2, 10) == 0.0

    def test_slope_zero(self):
        assert projected_sl_change_probability(0.0, 0.2, 10) == 0.0

    def test_high_volatility_damps_it(self):
        calm = projected_sl_change_probability(0.3, 0.1, 10)
        erratic = projected_sl_change_probability(0.3, 0.6, 10)
        assert erratic < calm

    def test_volatility_above_one_clamps_to_zero_not_negative(self):
        assert projected_sl_change_probability(0.5, 1.8, 10) == 0.0

    def test_insufficient_evidence(self):
        assert projected_sl_change_probability(
            0.5, 0.1, MIN_SAMPLE_SIZE_CLASSIFICATION - 1
        ) is None
        assert projected_sl_change_probability(None, 0.1, 10) is None
        assert projected_sl_change_probability(0.5, None, 10) is None

    def test_the_sample_term_caps_at_twenty(self):
        at_cap = projected_sl_change_probability(0.3, 0.2, PROBABILITY_SAMPLE_CAP)
        beyond = projected_sl_change_probability(0.3, 0.2, PROBABILITY_SAMPLE_CAP * 5)
        assert at_cap == beyond

    def test_it_stays_within_zero_and_one(self):
        assert 0.0 <= projected_sl_change_probability(50.0, 0.0, 20) <= 1.0


# =============================================================================
# Format normalisation
# =============================================================================

class TestFormatNormalisation:
    def test_captured_names_map_to_the_spec_values(self):
        assert normalize_format("8-Ball Open") == "8-ball"
        assert normalize_format("9-Ball Open") == "9-ball"

    def test_an_unrecognised_format_is_left_alone(self):
        """Forcing it into a bucket would label a division as something it
        may not be."""
        assert normalize_format("Masters Doubles") == "Masters Doubles"
        assert normalize_format(None) is None


# =============================================================================
# evaluate()
# =============================================================================

class TestEvaluate:
    def test_it_reports_the_most_recent_skill_level(self):
        result = evaluate([4, 4, 5], player_id="P1", format_="8-Ball Open",
                          session_name="Fall 2026")
        assert result.current_skill_level == 5
        assert result.format == "8-ball"
        assert result.session_name == "Fall 2026"

    def test_a_single_observation_yields_only_what_it_supports(self):
        result = evaluate([5], player_id="P1")
        assert result.sample_size == 1
        assert result.current_skill_level == 5
        assert result.regression_slope is None
        assert result.volatility is None
        assert result.sl_stability is None
        assert result.hot_cold_flag is None
        assert result.projected_sl_change_probability is None

    def test_four_observations_give_a_slope_but_no_classification(self):
        """The exact shape of this project's real data."""
        result = evaluate([4, 4, 5, 5], player_id="P1")
        assert result.regression_slope is not None
        assert result.volatility is not None
        assert result.hot_cold_flag is None
        assert result.projected_sl_change_probability is None

    def test_five_observations_unlock_the_gated_metrics(self):
        result = evaluate([4, 4, 5, 5, 5], player_id="P1")
        assert result.hot_cold_flag is not None
        assert result.projected_sl_change_probability is not None

    def test_sample_size_counts_the_window_not_the_whole_history(self):
        result = evaluate([5] * 30, player_id="P1")
        assert result.sample_size == VOLATILITY_WINDOW


# =============================================================================
# Database + builder
# =============================================================================

@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'trends.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


_match_counter = itertools.count(1)


def _add_match(db, player, week, level, fmt="8-Ball Open", session="Fall 2026"):
    """Add one match and the player's row in it.

    external_id comes from a module-level counter: Match.external_id is
    UNIQUE, and deriving it from (format, session, week) collided the moment
    two players shared a week.
    """
    match = Match(external_id=f"M{next(_match_counter)}", week=week, format=fmt,
                  session_name=session, home_team_id="T1", away_team_id="T2")
    db.add(match)
    db.flush()
    db.add(PlayerMatch(player_id=player.id, match_id=match.id,
                       skill_level=level, points_earned=2.0, result="W"))
    return match


@pytest.fixture
def seeded(db):
    """One player, five 8-ball matches in one session, climbing skill level."""
    player = Player(external_id="P1", name="Alice", skill_level=5)
    db.add(player)
    db.flush()
    for week, level in enumerate([4, 4, 5, 5, 5], start=1):
        _add_match(db, player, week, level)
    db.commit()
    return db


class TestSchema:
    def test_the_table_has_exactly_the_specified_columns(self):
        columns = {c.name for c in PlayerTrend.__table__.columns}
        assert columns == {
            "id", "player_id", "format", "session_name", "sample_size",
            "current_skill_level", "regression_slope", "volatility",
            "sl_stability", "hot_cold_flag", "projected_sl_change_probability",
        }

    def test_the_unique_key_is_player_format_session(self):
        unique = [c for c in PlayerTrend.__table__.constraints
                  if c.__class__.__name__ == "UniqueConstraint"]
        assert len(unique) == 1
        assert {c.name for c in unique[0].columns} == {
            "player_id", "format", "session_name"
        }

    def test_there_is_an_index_on_format_and_session(self):
        indexes = {tuple(sorted(c.name for c in i.columns))
                   for i in PlayerTrend.__table__.indexes}
        assert ("format", "session_name") in indexes

    def test_the_required_columns_are_not_nullable(self):
        table = PlayerTrend.__table__
        for name in ("player_id", "format", "session_name", "sample_size",
                     "current_skill_level"):
            assert not table.c[name].nullable, name


class TestBuilderPersistence:
    def test_it_writes_a_row_per_player_format_session(self, seeded):
        rows = build_rows(seeded)
        assert len(rows) == 1
        row = rows[0]
        assert row["player_id"] == "P1"
        assert row["format"] == "8-ball"
        assert row["session_name"] == "Fall 2026"
        assert row["sample_size"] == 5
        assert row["current_skill_level"] == 5
        assert row["regression_slope"] == pytest.approx(0.3, abs=1e-6)

    def test_the_row_persists_to_the_table(self, seeded):
        ingest_player_trends(seeded, build_rows(seeded))
        stored = seeded.query(PlayerTrend).one()
        assert stored.format == "8-ball"
        assert stored.sample_size == 5
        assert stored.current_skill_level == 5

    def test_separate_sessions_produce_separate_rows(self, db):
        player = Player(external_id="P1", name="Alice")
        db.add(player)
        db.flush()
        for week, level in enumerate([4, 5], start=1):
            _add_match(db, player, week, level, session="Fall 2026")
        for week, level in enumerate([5, 6], start=1):
            _add_match(db, player, week, level, session="Summer 2026")
        db.commit()

        rows = build_rows(db)
        assert {r["session_name"] for r in rows} == {"Fall 2026", "Summer 2026"}

    def test_separate_formats_produce_separate_rows(self, db):
        player = Player(external_id="P1", name="Alice")
        db.add(player)
        db.flush()
        for week, level in enumerate([4, 5], start=1):
            _add_match(db, player, week, level, fmt="8-Ball Open")
        for week, level in enumerate([5, 6], start=1):
            _add_match(db, player, week, level, fmt="9-Ball Open")
        db.commit()

        assert {r["format"] for r in build_rows(db)} == {"8-ball", "9-ball"}

    def test_a_match_without_a_format_or_session_is_skipped(self, db):
        player = Player(external_id="P2", name="Bob")
        db.add(player)
        db.flush()
        match = Match(external_id="MX", week=1, home_team_id="T1", away_team_id="T2")
        db.add(match)
        db.flush()
        db.add(PlayerMatch(player_id=player.id, match_id=match.id, skill_level=5))
        db.commit()
        assert build_rows(db) == []

    def test_an_empty_database_builds_nothing(self, db):
        assert build_rows(db) == []


class TestBuilderIdempotency:
    def test_rebuilding_updates_rather_than_duplicating(self, seeded):
        rows = build_rows(seeded)
        ingest_player_trends(seeded, rows)
        ingest_player_trends(seeded, rows)
        assert seeded.query(PlayerTrend).count() == 1

    def test_values_are_identical_across_rebuilds(self, seeded):
        ingest_player_trends(seeded, build_rows(seeded))
        first = seeded.query(PlayerTrend).one()
        snapshot = (first.sample_size, first.regression_slope, first.volatility,
                    first.sl_stability, first.hot_cold_flag)
        ingest_player_trends(seeded, build_rows(seeded))
        second = seeded.query(PlayerTrend).one()
        assert (second.sample_size, second.regression_slope, second.volatility,
                second.sl_stability, second.hot_cold_flag) == snapshot

    def test_an_unknown_player_is_skipped_not_guessed(self, seeded):
        assert ingest_player_trends(seeded, [{
            "player_id": "GHOST", "format": "8-ball", "session_name": "Fall 2026",
            "sample_size": 5, "current_skill_level": 5,
        }]) == 0


class TestStalePruning:
    def test_an_aggregate_whose_matches_vanished_is_removed(self, seeded):
        """Without pruning an aggregate outlives its evidence and keeps being
        reported as current."""
        ingest_player_trends(seeded, build_rows(seeded))
        assert seeded.query(PlayerTrend).count() == 1

        seeded.query(PlayerMatch).delete()
        seeded.commit()

        removed = prune_player_trends_not_in(seeded, set(grouped_history(seeded)))
        assert removed == 1
        assert seeded.query(PlayerTrend).count() == 0

    def test_live_aggregates_survive_pruning(self, seeded):
        ingest_player_trends(seeded, build_rows(seeded))
        removed = prune_player_trends_not_in(seeded, set(grouped_history(seeded)))
        assert removed == 0
        assert seeded.query(PlayerTrend).count() == 1

    def test_only_the_stale_group_is_pruned(self, db):
        player = Player(external_id="P1", name="Alice")
        db.add(player)
        db.flush()
        for week, level in enumerate([4, 5], start=1):
            _add_match(db, player, week, level, fmt="8-Ball Open")
        nine = [_add_match(db, player, week, level, fmt="9-Ball Open")
                for week, level in enumerate([5, 6], start=1)]
        db.commit()
        ingest_player_trends(db, build_rows(db))
        assert db.query(PlayerTrend).count() == 2

        # Remove only the 9-ball history.
        for match in nine:
            db.query(PlayerMatch).filter_by(match_id=match.id).delete()
        db.commit()

        prune_player_trends_not_in(db, set(grouped_history(db)))
        remaining = db.query(PlayerTrend).all()
        assert len(remaining) == 1
        assert remaining[0].format == "8-ball"


class TestNullPersistence:
    def test_nulls_are_stored_as_nulls_not_zeros(self, db):
        player = Player(external_id="P9", name="Thin")
        db.add(player)
        db.flush()
        _add_match(db, player, 1, 5)
        db.commit()

        ingest_player_trends(db, build_rows(db))
        row = db.query(PlayerTrend).one()
        assert row.sample_size == 1
        assert row.current_skill_level == 5
        assert row.regression_slope is None
        assert row.volatility is None
        assert row.sl_stability is None
        assert row.hot_cold_flag is None
        assert row.projected_sl_change_probability is None


# =============================================================================
# UI
# =============================================================================

class TestTrendsTab:
    def test_the_headers_match_the_spec_order(self):
        assert [label for _, label, _ in COLUMNS] == [
            "Player", "Format", "Session", "Sample Size", "Current SL",
            "Regression Slope", "Volatility", "SL Stability", "Hot/Cold",
            "Projected SL Change Probability",
        ]

    def test_hot_and_cold_are_highlighted(self):
        assert row_class({"hot_cold_flag": "HOT"}) == "hot"
        assert row_class({"hot_cold_flag": "COLD"}) == "cold"

    def test_neutral_and_unmeasured_are_not_highlighted(self):
        assert row_class({"hot_cold_flag": "NEUTRAL"}) == ""
        assert row_class({"hot_cold_flag": None}) == ""

    def test_nulls_render_as_no_data(self, db):
        player = Player(external_id="P9", name="Thin")
        db.add(player)
        db.flush()
        _add_match(db, player, 1, 5)
        db.commit()
        ingest_player_trends(db, build_rows(db))
        assert NO_DATA in render(load_rows(db))

    def test_numeric_formatting(self, seeded):
        ingest_player_trends(seeded, build_rows(seeded))
        html = render(load_rows(seeded))
        assert "+0.3000" in html          # signed slope, 4dp
        assert "0.5477" in html           # volatility, 4dp

    def test_rows_sort_by_slope_descending(self, db):
        for external_id, name, levels in (
            ("P1", "Riser", [4, 5, 6]),
            ("P2", "Faller", [6, 5, 4]),
        ):
            player = Player(external_id=external_id, name=name)
            db.add(player)
            db.flush()
            for week, level in enumerate(levels, start=1):
                _add_match(db, player, week, level)
        db.commit()
        ingest_player_trends(db, build_rows(db))

        rows = load_rows(db)
        assert [r["player_name"] for r in rows] == ["Riser", "Faller"]

    def test_it_is_sortable_client_side(self, seeded):
        ingest_player_trends(seeded, build_rows(seeded))
        html = render(load_rows(seeded))
        assert "addEventListener" in html
        assert NO_DATA in html or "localeCompare" in html

    def test_it_carries_no_external_resources(self, seeded):
        """It has to open at a venue with no internet."""
        ingest_player_trends(seeded, build_rows(seeded))
        html = render(load_rows(seeded))
        assert "http://" not in html and "https://" not in html

    def test_an_empty_tab_explains_what_to_run(self):
        assert "build_player_trends" in render([])


# =============================================================================
# Excel
# =============================================================================

class TestExcelSheet:
    def _sheet(self, db, tmp_path):
        from ui.export_excel import export_to_excel

        path = export_to_excel(
            db, {"export": {"excel_output_path": str(tmp_path / "wb.xlsx")}}
        )
        return load_workbook(path)["Player Trends"]

    def test_headers_match_the_spec_order(self, seeded, tmp_path):
        ingest_player_trends(seeded, build_rows(seeded))
        sheet = self._sheet(seeded, tmp_path)
        assert [c.value for c in next(sheet.iter_rows(max_row=1))] == [
            "Player", "Format", "Session", "Sample Size", "Current SL",
            "Regression Slope", "Volatility", "SL Stability", "Hot/Cold",
            "Projected SL Change Probability",
        ]

    def test_the_header_is_frozen_and_filtered(self, seeded, tmp_path):
        ingest_player_trends(seeded, build_rows(seeded))
        sheet = self._sheet(seeded, tmp_path)
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref is not None

    def test_hot_and_cold_are_conditionally_formatted(self, seeded, tmp_path):
        ingest_player_trends(seeded, build_rows(seeded))
        sheet = self._sheet(seeded, tmp_path)
        formulas = [rule.formula[0]
                    for rules in sheet.conditional_formatting
                    for rule in rules.rules]
        assert '"HOT"' in formulas
        assert '"COLD"' in formulas

    def test_the_probability_column_is_a_percentage(self, seeded, tmp_path):
        ingest_player_trends(seeded, build_rows(seeded))
        sheet = self._sheet(seeded, tmp_path)
        header = [c.value for c in next(sheet.iter_rows(max_row=1))]
        column = header.index("Projected SL Change Probability") + 1
        cell = sheet.cell(row=2, column=column)
        assert isinstance(cell.value, (int, float))
        assert cell.number_format == "0.0%"

    def test_slope_and_volatility_stay_numeric(self, seeded, tmp_path):
        ingest_player_trends(seeded, build_rows(seeded))
        sheet = self._sheet(seeded, tmp_path)
        header = [c.value for c in next(sheet.iter_rows(max_row=1))]
        row = dict(zip(header, [c.value for c in list(sheet.iter_rows(min_row=2))[0]]))
        assert isinstance(row["Regression Slope"], (int, float))
        assert isinstance(row["Volatility"], (int, float))

    def test_nulls_render_as_no_data(self, db, tmp_path):
        player = Player(external_id="P9", name="Thin")
        db.add(player)
        db.flush()
        _add_match(db, player, 1, 5)
        db.commit()
        ingest_player_trends(db, build_rows(db))

        sheet = self._sheet(db, tmp_path)
        header = [c.value for c in next(sheet.iter_rows(max_row=1))]
        row = dict(zip(header, [c.value for c in list(sheet.iter_rows(min_row=2))[0]]))
        assert row["Volatility"] == NO_DATA
        assert row["Hot/Cold"] == NO_DATA

    def test_the_other_sheets_still_ship(self, seeded, tmp_path):
        from ui.export_excel import export_to_excel

        path = export_to_excel(
            seeded, {"export": {"excel_output_path": str(tmp_path / "wb.xlsx")}}
        )
        names = load_workbook(path).sheetnames
        assert "Matchups" in names and "Head-to-Head" in names
