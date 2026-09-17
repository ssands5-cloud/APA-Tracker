from scripts.check_release_candidate import main


def test_source_release_gate_checker_passes_on_hardening_branch():
    assert main() == 0
