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
        lambda _db, _config: calls.append(("workbook", None))
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
        lambda _db, out_dir=None: calls.append(("analysis tabs", None))
        or ((out_dir or exports.EXPORTS_DIR) / "analysis_tabs.html"),
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

    def build(_db_path, out_dir, weights=None):
        calls.append(("lineups", Path(out_dir)))
        return Path(out_dir) / "lineups.json"

    module.build = build
    # Real signature is (config) -> LineupWeights; this stub never inspects
    # its result (build() above ignores `weights` too), only that
    # pipeline.exports.run() calls it at all -- see
    # test_pipeline_exports_lineup_weights.py for the real, config-driven
    # value.
    module.load_weights_from_config = lambda config: None
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

    assert calls[:2] == [("workbook", None), ("demo json", None)]
    assert calls[-1] == ("analysis tabs", None)
    assert [label for label, _ in written] == [
        "workbook", "demo json", "captains html", "captains xlsx",
        "lineups json", "analysis tabs",
    ]
    lineup_output = next(path for label, path in written if label == "lineups json")
    assert Path(lineup_output).parent == exports.EXPORTS_DIR
    assert calls[2] == ("captains", exports.EXPORTS_DIR)
    assert calls[3] == ("lineups", exports.EXPORTS_DIR)


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

    assert [label for label, _ in written] == ["workbook", "demo json"]
    assert calls == [("workbook", None), ("demo json", None)]


def test_lineup_output_outside_repository_exports_is_rejected(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)

    module = types.ModuleType("scripts.build_lineups")
    module.NoDatabaseError = type("LineupNoDatabaseError", (RuntimeError,), {})
    module.build = lambda _db_path, _out_dir, weights=None: Path("C:/outside.json")
    module.load_weights_from_config = lambda config: None
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)

    with pytest.raises(ValueError, match="must be under"):
        exports.run({"database": {"path": "unused.db"}}, engine)


def test_run_computes_lineup_weights_from_config_and_passes_them_to_the_builder(
    monkeypatch, engine, stub_exporters
):
    """Not just that build_lineups.build() gets called -- that pipeline.exports.run()
    actually threads its own real `config` through load_weights_from_config()
    and hands the RESULT to build(), rather than silently dropping it."""
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)

    module = types.ModuleType("scripts.build_lineups")
    seen: dict[str, object] = {}

    def load_weights_from_config(config):
        seen["config"] = config
        return "sentinel-weights"

    def build(_db_path, out_dir, weights=None):
        seen["weights"] = weights
        return Path(out_dir) / "lineups.json"

    module.load_weights_from_config = load_weights_from_config
    module.build = build
    module.NoDatabaseError = type("LineupNoDatabaseError", (RuntimeError,), {})
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)

    config = {"database": {"path": "unused.db"}, "lineup_optimizer": {"weight_matchup_score": 0.9}}
    exports.run(config, engine, captains=True)

    assert seen["config"] is config
    assert seen["weights"] == "sentinel-weights"


class TestConfiguredExportsDir:
    def test_defaults_to_the_module_constant(self):
        assert exports.configured_exports_dir({}) == exports.EXPORTS_DIR
        assert exports.configured_exports_dir({"export": {}}) == exports.EXPORTS_DIR

    def test_a_relative_override_resolves_under_project_root(self):
        assert (
            exports.configured_exports_dir({"export": {"exports_dir": "scratch/out"}})
            == exports.PROJECT_ROOT / "scratch" / "out"
        )

    def test_an_absolute_override_is_used_as_is(self, tmp_path):
        assert exports.configured_exports_dir({"export": {"exports_dir": str(tmp_path)}}) == tmp_path


def test_export_dir_override_redirects_every_builder_not_just_the_workbook(
    monkeypatch, engine, stub_exporters, tmp_path
):
    """The gap this closes: export_to_excel/export_to_json already honoured
    config["export"]["*_output_path"], but Captain's Edge, the Lineup
    Optimizer and the analysis tabs page always wrote to the real project's
    exports/ regardless of config -- so a caller (a CI run, a build
    verification script) could not fully redirect output without
    monkeypatching pipeline.exports' module globals directly."""
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)
    _lineup_builder(monkeypatch, calls)

    scratch = tmp_path / "scratch-exports"
    config = {"database": {"path": "unused.db"}, "export": {"exports_dir": str(scratch)}}
    written = exports.run(config, engine, captains=True)

    assert calls[2] == ("captains", scratch)
    assert calls[3] == ("lineups", scratch)
    lineup_output = next(path for label, path in written if label == "lineups json")
    assert Path(lineup_output).parent == scratch


def test_missing_lineup_database_skips_only_lineup_artifact(
    monkeypatch, engine, stub_exporters
):
    calls = stub_exporters
    _captains_builder(monkeypatch, calls)

    module = types.ModuleType("scripts.build_lineups")
    no_database_error = type("LineupNoDatabaseError", (RuntimeError,), {})
    module.NoDatabaseError = no_database_error

    def fail(_db_path, _out_dir, weights=None):
        raise no_database_error("database unavailable")

    module.build = fail
    module.load_weights_from_config = lambda config: None
    monkeypatch.setitem(sys.modules, "scripts.build_lineups", module)

    written = exports.run({"database": {"path": "unused.db"}}, engine)

    assert [label for label, _ in written] == [
        "workbook", "demo json", "captains html", "captains xlsx", "analysis tabs",
    ]
    assert calls[-1] == ("analysis tabs", None)
