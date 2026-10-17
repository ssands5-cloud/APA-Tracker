"""Every real Ultimate Coach build entrypoint must hand the HTML and Excel
exports the SAME Match Day settings (viewer record ID, display-only card
number, display timezone), read once from apa_config.yaml plus its
git-ignored apa_config.local.yaml override -- otherwise configuring the
viewer could silently leave one artifact's "My Team" default disabled."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.build_ultimate_coach_excel as excel_entry
import scripts.build_ultimate_coach_html as html_entry
import scripts.build_ultimate_coach_production as production_entry


def _configs(tmp_path: Path, *, timezone: str = "America/Phoenix") -> Path:
    config = tmp_path / "apa_config.yaml"
    config.write_text(
        "ultimate_coach:\n"
        '  viewer_member_external_id: "CHANGE_ME"\n'
        '  viewer_card_number: "CHANGE_ME"\n'
        f'  match_day_timezone: "{timezone}"\n',
        encoding="utf-8",
    )
    (tmp_path / "apa_config.local.yaml").write_text(
        'ultimate_coach:\n  viewer_member_external_id: "9000001"\n  viewer_card_number: "80000001"\n',
        encoding="utf-8",
    )
    return config


class _FakeEngine:
    def dispose(self):
        pass


class _FakeSession:
    def __init__(self, engine):
        pass

    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def _payload():
    return {"counts": {"players": 1, "head_to_head_rows": 1}, "players": [], "evidence": []}


def _patch_common(monkeypatch, module, seen):
    monkeypatch.setattr(module, "create_db_engine", lambda *a, **k: _FakeEngine())
    monkeypatch.setattr(module, "Session", _FakeSession)

    def fake_payload(db, *, match_day_timezone):
        seen["payload_timezone"] = match_day_timezone
        return _payload()

    monkeypatch.setattr(module, "build_verified_cockpit_payload", fake_payload)


def test_html_entrypoint_passes_configured_viewer_and_timezone(monkeypatch, tmp_path):
    seen = {}
    _patch_common(monkeypatch, html_entry, seen)

    def fake_render(payload, **kwargs):
        seen.update(kwargs)
        return "<html></html>"

    monkeypatch.setattr(html_entry, "render", fake_render)
    db = tmp_path / "staging.db"
    db.write_bytes(b"")
    assert html_entry.main(["--db", str(db), "--output", str(tmp_path / "uc.html"), "--config", str(_configs(tmp_path))]) == 0
    assert seen["payload_timezone"] == "America/Phoenix"
    assert seen["viewer_member_external_id"] == "9000001"
    assert seen["viewer_card_number"] == "80000001"


def test_excel_entrypoint_passes_the_same_viewer_and_timezone(monkeypatch, tmp_path):
    seen = {}
    _patch_common(monkeypatch, excel_entry, seen)

    def fake_write(payload, path, **kwargs):
        seen.update(kwargs)
        return Path(path)

    monkeypatch.setattr(excel_entry, "write_workbook", fake_write)
    db = tmp_path / "staging.db"
    db.write_bytes(b"")
    assert excel_entry.main(["--db", str(db), "--output", str(tmp_path / "uc.xlsx"), "--config", str(_configs(tmp_path))]) == 0
    assert seen["payload_timezone"] == "America/Phoenix"
    assert seen["viewer_member_external_id"] == "9000001"
    assert seen["viewer_card_number"] == "80000001"


def test_production_entrypoint_passes_the_same_settings(monkeypatch, tmp_path):
    seen = {}

    def fake_build_candidate(db, out_dir, *, settings):
        seen["settings"] = settings
        return out_dir

    monkeypatch.setattr(production_entry, "build_candidate", fake_build_candidate)
    assert production_entry.main(["--db", str(tmp_path / "x.db"), "--out", str(tmp_path / "out"),
                                  "--config", str(_configs(tmp_path))]) == 0
    settings = seen["settings"]
    assert settings.viewer_member_external_id == "9000001"
    assert settings.viewer_card_number == "80000001"
    assert settings.timezone == "America/Phoenix"
    assert settings.viewer_source == "apa_config.local.yaml"


def test_production_candidate_renders_with_settings_and_records_them_in_the_manifest(monkeypatch, tmp_path):
    import json
    import sqlite3

    from analytics.ultimate_coach_match_day import MatchDaySettings

    source = tmp_path / "ultimate.db"
    sqlite3.connect(source).close()
    seen = {}

    def fake_build_payload(snapshot, *, match_day_timezone):
        seen["payload_timezone"] = match_day_timezone
        payload = {
            "probability_publication": "FORBIDDEN", "matchup_probability": None, "predictive_confidence": None,
            "requires_live_apa_login": False, "database_mutated": False, "name_matching_used": False,
            "counts": {"players": 1, "head_to_head_rows": 1}, "trust": {},
            "match_day": {"coverage": {"stored_fixture_count": 5, "embedded_fixture_count": 2}},
        }
        return payload

    def fake_render(payload, **kwargs):
        seen.update(kwargs)
        return "<html></html>"

    monkeypatch.setattr(production_entry, "_build_payload", fake_build_payload)
    monkeypatch.setattr(production_entry, "render", fake_render)
    settings = MatchDaySettings("9000001", "80000001", "America/Denver", "apa_config.local.yaml")
    out = production_entry.build_candidate(source, tmp_path / "candidate", settings=settings)
    assert seen["payload_timezone"] == "America/Denver"
    assert seen["viewer_member_external_id"] == "9000001"
    assert seen["viewer_card_number"] == "80000001"
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["match_day"]["display_timezone"] == "America/Denver"
    assert manifest["match_day"]["viewer_configured"] is True
    assert manifest["match_day"]["coverage"]["embedded_fixture_count"] == 2
    # The identity itself is never written into the manifest.
    assert "9000001" not in json.dumps(manifest)


def test_invalid_configured_timezone_stops_the_build(monkeypatch, tmp_path):
    db = tmp_path / "staging.db"
    db.write_bytes(b"")
    with pytest.raises(ValueError, match="Not/AZone"):
        html_entry.main(["--db", str(db), "--output", str(tmp_path / "uc.html"),
                         "--config", str(_configs(tmp_path, timezone="Not/AZone"))])
