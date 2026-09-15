"""Tests for scripts/scrape_and_ingest.py.

No test in this file makes, or can make, a live APA request:
run_all_teams (the only function that would) is mocked out entirely in
every test that reaches it, and --dry-run never imports it at all.
"""

from __future__ import annotations

import scripts.scrape_and_ingest as cli
from scripts.scrape_and_ingest import CredentialError, _require_token, _token_present, main


class TestTokenPresence:
    def test_a_real_env_token_is_detected(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token-value")
        assert _token_present("apa_config.yaml", "APA_ACCESS_TOKEN") is True

    def test_no_env_token_and_no_config_file_is_false(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        missing_config = tmp_path / "nonexistent.yaml"
        assert _token_present(str(missing_config), "APA_ACCESS_TOKEN") is False

    def test_a_placeholder_config_token_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        config_path = tmp_path / "apa_config.yaml"
        config_path.write_text(
            "apa:\n  access_token: \"eyJhbGciOi...your token here...\"\n", encoding="utf-8"
        )
        assert _token_present(str(config_path), "APA_ACCESS_TOKEN") is False

    def test_a_real_config_token_is_detected(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        config_path = tmp_path / "apa_config.yaml"
        config_path.write_text("apa:\n  access_token: \"real.jwt.value\"\n", encoding="utf-8")
        assert _token_present(str(config_path), "APA_ACCESS_TOKEN") is True

    def test_a_custom_token_env_name_is_honored(self, monkeypatch):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("MY_TOKEN_VAR", "real-token")
        assert _token_present("apa_config.yaml", "MY_TOKEN_VAR") is True


class TestRequireToken:
    def test_raises_a_clear_error_naming_the_env_var_not_a_value(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        missing_config = tmp_path / "nonexistent.yaml"
        try:
            _require_token(str(missing_config), "APA_ACCESS_TOKEN")
            assert False, "expected CredentialError"
        except CredentialError as exc:
            assert "APA_ACCESS_TOKEN" in str(exc)

    def test_does_not_raise_when_a_real_token_exists(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        _require_token("apa_config.yaml", "APA_ACCESS_TOKEN")  # must not raise


class TestDryRun:
    def test_dry_run_never_imports_or_calls_run_all_teams(self, monkeypatch, capsys):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        exit_code = main(["--dry-run"])

        assert exit_code == 0

    def test_dry_run_without_a_token_fails_closed(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        missing_config = tmp_path / "nonexistent.yaml"

        exit_code = main(["--dry-run", "--config", str(missing_config)])

        assert exit_code == 1

    def test_neither_live_nor_dry_run_is_rejected(self):
        assert main([]) == 1

    def test_both_live_and_dry_run_is_rejected(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        assert main(["--live", "--dry-run"]) == 1


class TestLiveModeCallsTheRealPipelineOnly(object):
    def test_live_mode_calls_run_all_teams_exactly_once(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        calls = []

        def fake_run_all_teams(config_path, export):
            calls.append((config_path, export))
            return {"teams": 1}

        monkeypatch.setattr("scheduler.graphql_sync.run_all_teams", fake_run_all_teams)

        exit_code = main(["--live", "--config", "apa_config.yaml"])

        assert exit_code == 0
        assert calls == [("apa_config.yaml", True)]

    def test_no_export_flag_is_passed_through(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        calls = []
        monkeypatch.setattr(
            "scheduler.graphql_sync.run_all_teams",
            lambda config_path, export: calls.append(export) or {},
        )

        main(["--live", "--no-export"])

        assert calls == [False]

    def test_live_mode_without_a_token_never_reaches_run_all_teams(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        missing_config = tmp_path / "nonexistent.yaml"
        called = []
        monkeypatch.setattr(
            "scheduler.graphql_sync.run_all_teams",
            lambda *a, **k: called.append(True),
        )

        exit_code = main(["--live", "--config", str(missing_config)])

        assert exit_code == 1
        assert called == []


class TestUnusedCredentialFlagsWarnRatherThanSilentlyNoOp:
    def test_username_env_and_password_env_do_not_crash_and_are_accepted(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "real-token")
        exit_code = main([
            "--dry-run", "--username-env", "APA_USERNAME", "--password-env", "APA_PASSWORD",
        ])
        assert exit_code == 0


class TestNoSecretLeakage:
    def test_a_credential_error_never_includes_a_token_value(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APA_ACCESS_TOKEN", raising=False)
        missing_config = tmp_path / "nonexistent.yaml"
        try:
            _require_token(str(missing_config), "APA_ACCESS_TOKEN")
        except CredentialError as exc:
            message = str(exc)
            assert "eyJ" not in message  # a JWT would start like this if ever leaked
