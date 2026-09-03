from __future__ import annotations

import pytest

from parser.html_parser import TableNotFoundError, TableShapeError, parse_table

COLUMNS = ["rank", "team_name", "wins", "losses", "points"]

WELL_FORMED = """<table class="standings"><tbody>
<tr><td>1</td><td>Cue Crew</td><td>10</td><td>2</td><td>88</td></tr>
<tr><td>2</td><td>Rack Attack</td><td>8</td><td>4</td><td>71</td></tr>
</tbody></table>"""

EXTRA_LEADING_CELL = """<table class="standings"><tbody>
<tr><td><img/></td><td>1</td><td>Cue Crew</td><td>10</td><td>2</td><td>88</td></tr>
</tbody></table>"""

SHORT_ROW = """<table class="standings"><tbody>
<tr><td>1</td><td>Cue Crew</td><td>10</td></tr>
</tbody></table>"""

HEADER_INSIDE_BODY = """<table class="standings"><tbody>
<tr><th>Rank</th><th>Team</th><th>W</th><th>L</th><th>Pts</th></tr>
<tr><td>1</td><td>Cue Crew</td><td>10</td><td>2</td><td>88</td></tr>
</tbody></table>"""


class TestWellFormedTables:
    def test_parses_rows_into_declared_columns(self):
        rows = parse_table(WELL_FORMED, "table.standings", "tbody tr", COLUMNS)
        assert rows == [
            {"rank": "1", "team_name": "Cue Crew", "wins": "10", "losses": "2", "points": "88"},
            {"rank": "2", "team_name": "Rack Attack", "wins": "8", "losses": "4", "points": "71"},
        ]


class TestShapeMismatchRaises:
    def test_extra_leading_cell_raises_instead_of_shifting(self):
        with pytest.raises(TableShapeError) as excinfo:
            parse_table(EXTRA_LEADING_CELL, "table.standings", "tbody tr", COLUMNS)
        error = excinfo.value
        assert error.row_index == 0
        assert len(error.cells) == 6
        assert error.columns == COLUMNS

    def test_error_message_shows_what_actually_arrived(self):
        with pytest.raises(TableShapeError) as excinfo:
            parse_table(EXTRA_LEADING_CELL, "table.standings", "tbody tr", COLUMNS)
        message = str(excinfo.value)
        assert "6 cell(s)" in message and "5 column(s)" in message
        assert "Cue Crew" in message

    def test_short_row_also_raises(self):
        with pytest.raises(TableShapeError):
            parse_table(SHORT_ROW, "table.standings", "tbody tr", COLUMNS)

    def test_pre_fix_behaviour_is_gone(self):
        try:
            parse_table(EXTRA_LEADING_CELL, "table.standings", "tbody tr", COLUMNS)
        except TableShapeError:
            return
        pytest.fail("shape mismatch was accepted and produced rows")


class TestNonStrictMode:
    def test_skips_the_bad_row_and_keeps_going(self):
        html = WELL_FORMED.replace("<tr><td>2</td>", "<tr><td><img/></td><td>2</td>")
        rows = parse_table(html, "table.standings", "tbody tr", COLUMNS, strict=False)
        assert len(rows) == 1
        assert rows[0]["team_name"] == "Cue Crew"


class TestHeaderRows:
    def test_header_row_inside_tbody_is_not_a_data_row(self):
        rows = parse_table(HEADER_INSIDE_BODY, "table.standings", "tbody tr", COLUMNS)
        assert len(rows) == 1
        assert rows[0]["rank"] == "1"
        assert "Rank" not in [row["rank"] for row in rows]


class TestMissingTable:
    def test_absent_table_raises_rather_than_reporting_zero_rows(self):
        with pytest.raises(TableNotFoundError):
            parse_table("<html><body>Please log in</body></html>", "table.standings", "tbody tr", COLUMNS)

    def test_non_strict_returns_empty(self):
        assert parse_table("<html></html>", "table.standings", "tbody tr", COLUMNS, strict=False) == []
