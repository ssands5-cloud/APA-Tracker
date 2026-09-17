import pytest

from scripts.check_release_candidate import main, validate_release_version


def test_source_release_gate_checker_passes_on_release_line():
    assert main() == 0


@pytest.mark.parametrize("version", ["1.0.0-rc1", "1.0.0"])
def test_release_version_gate_accepts_rc_and_final(version):
    validate_release_version(version)


@pytest.mark.parametrize("version", ["1.0.0-rc2", "1.0.1", "2.0.0", ""])
def test_release_version_gate_rejects_unapproved_versions(version):
    with pytest.raises(SystemExit, match="unexpected APA Tracker 1.0 release version"):
        validate_release_version(version)
