"""Focused contracts for the export pipeline's Captain-facing artifacts."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import pipeline.exports as exports


@pytest.fixture
def engine():
    database_engine = create_engine("sqlite:///:memory:")
    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture
def stub_exporters(monkeypatch):
    """Keep these tests about orchestration, not workbook/database shape."""

    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        exports,
        "export_to_excel",
        lambda _db, _config, **kwargs: calls.append(("workbook", kwargs))
        or str(exports.EXPORTS_DIR / "workbook.xlsx"),
    )
    monkeypatch.setattr(
        exports,
        "export_to_json",
        lambda _db, _config: calls.append(("demo json", None))
        or str(exports.EXPORTS_DIR / "demo.json"),
    )
    monkeypatch.setattr(
        exports,
        "write_tabs",
        lambda _db, _out_dir=None, **kwargs: calls.append(
            ("analysis tabs", {"out_dir": _out_dir, **kwargs})
        )
        or (exports.EXPORTS_DIR / "analysis_tabs.html"),
    )
    return calls


def _captains_builder(monkeypatch, calls):
    import scripts.build_captains_edge as captains_edge

    def build(_db_path, out_dir):
        calls.append(("captains", Path(out_dir)))
        return Path(out_dir) / "captains_edge.html", Path(out_dir) / "captains_edge.xlsx"

    monkeypatch.setattr(captains_edge, "build", build)


def _lineup_builder(monkeypatch, calls):
    module = types.ModuleType("scripts.build_lineups")

    def build(_db_path, out_dir):
        calls.append(("lineups", Path(out_dir)))
        return Path(out_dir) / "lineups.json"

    module.build = build
    module.NoDatabaseError = type("LineupNoDatabaseError", (RuntimeError,), {})
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)


def test_captains_path_builds_lineups_in_repository_exports(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)
    _lineup_builder(monkeypatch, calls)

    config = {"database": {"path": "unused.db"}}
    written = exports.run(config, engine, captains=True)

    assert calls[:4] == [
        ("captains", exports.EXPORTS_DIR),
        ("lineups", exports.EXPORTS_DIR),
        ("workbook", {
            "captains_edge_path": exports.EXPORTS_DIR / "captains_edge.json",
            "include_captains_edge": True,
        }),
        ("demo json", None),
    ]
    assert calls[-1] == ("analysis tabs", {
        "out_dir": exports.EXPORTS_DIR,
        "include_captains_edge": True,
        "include_lineup": True,
    })
    assert [label for label, _ in written] == [
        "workbook", "demo json", "captains html", "captains xlsx", "captains json",
        "lineups json", "analysis tabs",
    ]
    lineup_output = next(path for label, path in written if label == "lineups json")
    assert Path(lineup_output).parent == exports.EXPORTS_DIR


def test_no_captains_does_not_import_or_build_lineups(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    forbidden = types.ModuleType("scripts.build_lineups")

    def fail(*_args, **_kwargs):  # pragma: no cover - assertion is the test
        raise AssertionError("Lineup Optimizer must not run with --no-captains")

    forbidden.build = fail
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", forbidden)

    written = exports.run({}, engine, captains=False)

    assert [label for label, _ in written] == [
        "workbook", "demo json", "analysis tabs",
    ]
    assert calls == [
        ("workbook", {
            "captains_edge_path": exports.EXPORTS_DIR / "captains_edge.json",
            "include_captains_edge": False,
        }),
        ("demo json", None),
        ("analysis tabs", {
            "out_dir": exports.EXPORTS_DIR,
            "include_captains_edge": False,
            "include_lineup": False,
        }),
    ]


def test_lineup_output_outside_repository_exports_is_rejected(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)

    module = types.ModuleType("scripts.build_lineups")
    module.NoDatabaseError = type("LineupNoDatabaseError", (RuntimeError,), {})
    module.build = lambda _db_path, _out_dir: Path("C:/outside.json")
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)

    with pytest.raises(ValueError, match="must be under"):
        exports.run({"database": {"path": "unused.db"}}, engine)


def test_missing_lineup_database_skips_only_lineup_artifact(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)

    module = types.ModuleType("scripts.build_lineups")
    no_database_error = type("LineupNoDatabaseError", (RuntimeError,), {})
    module.NoDatabaseError = no_database_error

    def fail(_db_path, _out_dir):
        raise no_database_error("database unavailable")

    module.build = fail
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)

    written = exports.run({"database": {"path": "unused.db"}}, engine)

    assert [label for label, _ in written] == [
        "workbook", "demo json", "captains html", "captains xlsx", "captains json",
        "analysis tabs",
    ]
    assert calls[-1] == ("analysis tabs", {
        "out_dir": exports.EXPORTS_DIR,
        "include_captains_edge": True,
        "include_lineup": False,
    })
