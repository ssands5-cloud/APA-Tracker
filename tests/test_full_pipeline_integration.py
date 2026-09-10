"""End-to-end integration: real fixtures -> real ingest -> every real
exporter, with nothing stubbed.

Every other pipeline test either (a) unit-tests one ingest/analytics/export
function in isolation with hand-built ORM rows, or (b) tests
``pipeline.exports.run``'s orchestration with the real exporters monkeypatched
out (see tests/test_pipeline_exports.py's ``stub_exporters`` fixture). Neither
proves the actual command a captain runs -- ``python -m pipeline`` -- works
front to back: fixtures on disk, through every ingest step, through Player
Trend Analyzer, Head-to-Head Advantage, Captain's Edge and the Lineup
Optimizer, out to a real workbook, real JSON, and real HTML.

This module builds a small but realistic two-team, one-match fixture tree in
exactly the scraper's documented layout (README-scraper.md) and runs the real
``pipeline.ingest.run`` / ``pipeline.refresh.finalize`` against it -- the same
committed-row boundary ``pipeline/__main__.py`` uses.

Output is redirected away from the real project ``exports/`` directory by
monkeypatching ``pipeline.exports.PROJECT_ROOT`` / ``EXPORTS_DIR`` for the
duration of each test (pytest's ``monkeypatch`` reverts this automatically,
so it can never leak into another test or the real project tree) -- verified
directly below by snapshotting the real directory before and after.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy.orm import Session

import pipeline.exports as exports_mod
from database.engine import create_db_engine
from pipeline.fixtures import FixtureStore
from pipeline.ingest import run as ingest_run
from pipeline.refresh import finalize

REAL_EXPORTS_DIR = exports_mod.PROJECT_ROOT / "exports"


def write_fixture(root: Path, entity: str, entity_id: str, operation: str, data: dict) -> None:
    folder = root / entity / entity_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{operation}.json").write_text(json.dumps({"data": data}), encoding="utf-8")


def build_two_team_one_match_fixture_tree(root: Path) -> None:
    """Brunch Ballers (Alice, SL 5) beat Pool Sharks (Bob, SL 4) 18-12 in one
    scored 8-ball match -- just enough real data to exercise every table in
    the chain: roster, standings, a Match, PlayerMatch scores,
    PlayerHeadToHead, matchups, Head-to-Head Advantage, and Player Trends.
    """
    home = {"id": "T1", "name": "Brunch Ballers"}
    away = {"id": "T2", "name": "Pool Sharks"}
    schedule_entry = {
        "id": "M1", "week": 1, "startTime": "2026-09-01T00:00:00Z",
        "status": "COMPLETED", "home": home, "away": away,
        "results": [
            {"homeAway": "HOME", "points": {"total": 18}},
            {"homeAway": "AWAY", "points": {"total": 12}},
        ],
        "isBye": False, "isScored": True, "isFinalized": True,
    }

    def team_page(identity):
        return {
            "team": {
                "id": identity["id"], "name": identity["name"],
                "division": {"id": "D1", "name": "Division 1", "format": "8-Ball Open"},
                "session": {"name": "Fall 2026"},
                "league": {"id": "L1"},
            }
        }

    write_fixture(root, "team", "T1", "teamPage", team_page(home))
    write_fixture(root, "team", "T1", "teamRoster", {"team": {"roster": [
        {"member": {"id": "P1"}, "displayName": "Alice", "skillLevel": 5,
         "matchesPlayed": 1, "matchesWon": 1, "ppm": 1.5, "pa": 0.2},
    ]}})
    write_fixture(root, "team", "T1", "teamSchedule", {"team": {
        "matches": [schedule_entry],
        "sessionPoints": 10, "sessionBonusPoints": 0, "sessionTotalPoints": 10,
    }})

    write_fixture(root, "team", "T2", "teamPage", team_page(away))
    write_fixture(root, "team", "T2", "teamRoster", {"team": {"roster": [
        {"member": {"id": "P2"}, "displayName": "Bob", "skillLevel": 4,
         "matchesPlayed": 1, "matchesWon": 0, "ppm": 1.1, "pa": 0.1},
    ]}})
    write_fixture(root, "team", "T2", "teamSchedule", {"team": {
        "matches": [schedule_entry],
        "sessionPoints": 8, "sessionBonusPoints": 0, "sessionTotalPoints": 8,
    }})

    write_fixture(root, "match", "M1", "MatchPage", {"match": {
        "id": "M1", "home": home, "away": away,
        "results": [
            {"homeAway": "HOME", "scores": [
                {"matchPositionNumber": 1, "player": {"id": "P1", "displayName": "Alice"},
                 "skillLevel": 5, "winLoss": "W", "eightBallMatchPointsEarned": 6,
                 "matchForfeited": False, "incompleteMatch": False},
            ]},
            {"homeAway": "AWAY", "scores": [
                {"matchPositionNumber": 1, "player": {"id": "P2", "displayName": "Bob"},
                 "skillLevel": 4, "winLoss": "L", "eightBallMatchPointsEarned": 3,
                 "matchForfeited": False, "incompleteMatch": False},
            ]},
        ],
    }})


def run_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "run") -> dict[str, Path]:
    """Build the fixture tree under ``tmp_path/name`` and run the real
    ingest + export chain against it, entirely inside ``tmp_path``. Returns
    {label: path} for every artifact the production refresh reports.
    """
    run_root = tmp_path / name
    fixtures_root = run_root / "fixtures"
    build_two_team_one_match_fixture_tree(fixtures_root)

    store = FixtureStore(fixtures_root).load()
    exports_dir = run_root / "exports"
    config = {
        "database": {"path": str(run_root / "test.db")},
        "export": {
            "excel_output_path": str(exports_dir / "apa_stats.xlsx"),
            "json_output_path": str(exports_dir / "apa_data.json"),
        },
    }
    engine = create_db_engine(config)
    with Session(engine) as db:
        counts = ingest_run(db, store, refresh_derived=False)

    # write_tabs() and the captains/lineups builders fall back to
    # PROJECT_ROOT/EXPORTS_DIR when not given an explicit directory --
    # monkeypatch (auto-reverted after the test) so NOTHING this test does
    # can land in the real project's exports/ folder.
    monkeypatch.setattr(exports_mod, "PROJECT_ROOT", run_root)
    monkeypatch.setattr(exports_mod, "EXPORTS_DIR", exports_dir)

    derived, written = finalize(config, engine, export=True, captains=True)
    counts.update(derived)
    result = {label: Path(path) for label, path in written}
    result["_counts"] = counts  # type: ignore[assignment]
    return result


class TestRealExportsDirectoryIsNeverTouched:
    def test_this_test_files_own_isolation_is_real(self, tmp_path, monkeypatch):
        """Not a test of production code -- a test of THIS test file's own
        safety net. If this ever fails, every other test in this module
        may have been silently writing into the real project's exports/
        directory instead of tmp_path."""
        before = {p: p.stat().st_mtime for p in REAL_EXPORTS_DIR.rglob("*") if p.is_file()}
        run_full_pipeline(tmp_path, monkeypatch)
        after = {p: p.stat().st_mtime for p in REAL_EXPORTS_DIR.rglob("*") if p.is_file()}
        assert before == after, (
            "A file under the real exports/ directory changed while running "
            "an isolated test -- the tmp_path redirect is broken."
        )


class TestFullPipelineIntegration:
    """One real run. Not just "no exception" -- real, specific content in
    every artifact, proving the chain actually carried Alice/Bob's real
    match through every layer rather than merely not crashing."""

    def test_ingest_populates_every_derived_table(self, tmp_path, monkeypatch):
        counts = run_full_pipeline(tmp_path, monkeypatch)["_counts"]
        assert counts["teams"] == 2
        assert counts["roster"] == 2
        assert counts["scores"] == 2
        assert counts["head_to_head"] == 2
        assert counts["matchups"] == 2
        assert counts["h2h_advantage"] == 2
        assert counts["player_trends"] == 2

    def test_every_declared_artifact_exists_and_is_non_empty(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        labels = {k for k in written if k != "_counts"}
        assert labels == {
            "workbook", "demo json", "captains html", "captains xlsx",
            "captains json", "lineups json", "analysis tabs", "refresh manifest",
        }
        for label, path in written.items():
            if label == "_counts":
                continue
            assert path.is_file(), f"{label} was reported but not written: {path}"
            assert path.stat().st_size > 0, f"{label} exists but is empty: {path}"

    def test_workbook_has_every_expected_sheet_with_real_rows(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        wb = load_workbook(written["workbook"])
        assert set(wb.sheetnames) >= {
            "Standings", "Player Stats", "Career Stats", "Matchups",
            "Head-to-Head", "Player Trends", "Captain's Edge", "Lineup Optimizer",
        }
        player_rows = list(wb["Player Stats"].iter_rows(min_row=2, values_only=True))
        assert len(player_rows) == 2
        names = {row[0] for row in player_rows}  # column 0 is "Player"
        assert names == {"Alice", "Bob"}

    def test_demo_json_carries_the_real_match(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        document = json.loads(written["demo json"].read_text(encoding="utf-8"))
        player_names = {row["player"] for row in document["player_stats"]}
        assert player_names == {"Alice", "Bob"}

    def test_lineups_json_solves_the_only_possible_assignment(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        document = json.loads(written["lineups json"].read_text(encoding="utf-8"))
        assert document["pairing_rows"] == 2
        # PlayerHeadToHead is bidirectional (Alice-vs-Bob AND Bob-vs-Alice),
        # so build_lineups groups one lineup per team's own perspective --
        # two lineups, not one, even for a single real match.
        assert len(document["lineups"]) == 2
        for lineup in document["lineups"]:
            [assignment] = lineup["assignments"]
            # Exactly one player per side exists, so the one-to-one
            # assignment problem has exactly one possible solution each way.
            assert {assignment["player_name"], assignment["opponent_name"]} == {"Alice", "Bob"}

    def test_captains_html_names_the_real_players(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        html = written["captains html"].read_text(encoding="utf-8")
        assert "Alice" in html
        assert "Bob" in html

    def test_analysis_tabs_include_every_section_this_data_supports(self, tmp_path, monkeypatch):
        written = run_full_pipeline(tmp_path, monkeypatch)
        html = written["analysis tabs"].read_text(encoding="utf-8")
        assert "<title>APA Analysis</title>" in html
        # Both captains_edge.json and lineups.json exist by the time
        # write_tabs() runs (the production refresh's ordering), so both
        # optional sections should be present, not silently omitted.
        assert "Lineup Optimizer" in html
        assert "Captain" in html

    def test_manifest_covers_every_artifact_from_the_completed_run(
        self, tmp_path, monkeypatch
    ):
        written = run_full_pipeline(tmp_path, monkeypatch)
        manifest = json.loads(written["refresh manifest"].read_text(encoding="utf-8"))
        assert manifest["run_id"]
        assert manifest["derived_counts"]["h2h_advantage"] == 2
        records = {row["label"]: row for row in manifest["artifacts"]}
        assert set(records) == {
            label for label in written if label not in {"_counts", "refresh manifest"}
        }
        assert all(row["exists"] for row in records.values())
        assert all(len(row["sha256"]) == 64 for row in records.values())


class TestFullPipelineDeterminism:
    """Ensure deterministic outputs: the SAME fixtures, run through the SAME
    chain twice into two independent directories, produce identical
    artifacts once the fields that are EXPECTED to vary (a wall-clock
    ingest timestamp, an absolute temp-directory path) are excluded. This
    is the real content of the roadmap's "ensure deterministic outputs" --
    checked, not just asserted in a docstring.
    """

    VOLATILE_JSON_KEYS = {"generated_at", "captured_at", "source_db"}
    VOLATILE_COLUMN_HEADERS = {"as of"}

    @classmethod
    def _strip_volatile_json(cls, obj):
        if isinstance(obj, dict):
            return {k: cls._strip_volatile_json(v) for k, v in obj.items()
                     if k not in cls.VOLATILE_JSON_KEYS}
        if isinstance(obj, list):
            return [cls._strip_volatile_json(v) for v in obj]
        return obj

    @classmethod
    def _sheet_values(cls, path: Path) -> dict[str, list[list]]:
        wb = load_workbook(path, data_only=True)
        out = {}
        for name in wb.sheetnames:
            rows = [[cell.value for cell in row] for row in wb[name].iter_rows()]
            if rows:
                header = [str(h or "").strip().lower() for h in rows[0]]
                volatile_idx = {i for i, h in enumerate(header) if h in cls.VOLATILE_COLUMN_HEADERS}
                for row in rows[1:]:
                    for i in volatile_idx:
                        row[i] = None
            out[name] = rows
        return out

    def test_two_runs_of_the_same_fixtures_produce_the_same_artifacts(self, tmp_path, monkeypatch):
        first = run_full_pipeline(tmp_path, monkeypatch, name="run1")
        second = run_full_pipeline(tmp_path, monkeypatch, name="run2")

        for label in ("demo json", "captains json", "lineups json"):
            left = self._strip_volatile_json(json.loads(first[label].read_text(encoding="utf-8")))
            right = self._strip_volatile_json(json.loads(second[label].read_text(encoding="utf-8")))
            assert left == right, f"{label} differs between two runs of identical input"

        for label in ("captains html", "analysis tabs"):
            assert first[label].read_text(encoding="utf-8") == second[label].read_text(encoding="utf-8"), (
                f"{label} differs between two runs of identical input"
            )

        for label in ("workbook", "captains xlsx"):
            left = self._sheet_values(first[label])
            right = self._sheet_values(second[label])
            assert left == right, f"{label} differs between two runs of identical input"
