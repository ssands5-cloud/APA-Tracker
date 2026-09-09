"""Contract tests for the pure Lineup Optimizer.

The optimizer is intentionally independent of the database and pipeline.  These
tests exercise the score formula and the complete assignment contract so that a
future builder can safely supply it with a score matrix.
"""

from __future__ import annotations

import pytest

from analytics.lineup_optimizer import (
    DEFAULT_WEIGHTS,
    MAX_ASSIGNMENT_PERMUTATIONS,
    NEUTRAL_DEFAULT,
    WEIGHT_CONFIDENCE,
    WEIGHT_MATCHUP_SCORE,
    WEIGHT_RISK_PENALTY,
    WEIGHT_WIN_PROBABILITY,
    LineupWeights,
    PairingCandidate,
    build_rationale,
    effective_confidence,
    effective_risk,
    pairing_score,
    risk_penalty,
    solve_lineup_assignment,
)


def candidate(
    player_id: str,
    opponent_id: str,
    *,
    matchup_score: float | None = 0.5,
    win_probability: float | None = 0.5,
    confidence: float | None = 0.5,
    risk_factor: float | None = 0.5,
    player_name: str | None = None,
    opponent_name: str | None = None,
    weights: LineupWeights = DEFAULT_WEIGHTS,
) -> PairingCandidate:
    """Create a matrix cell with readable defaults for the tests."""

    return PairingCandidate(
        player_id=player_id,
        player_name=player_name or player_id,
        opponent_id=opponent_id,
        opponent_name=opponent_name or opponent_id,
        matchup_score=matchup_score,
        win_probability=win_probability,
        confidence=confidence,
        risk_factor=risk_factor,
        weights=weights,
    )


def matrix(
    players: list[str],
    opponents: list[str],
    *,
    cells: dict[tuple[str, str], dict] | None = None,
) -> list[list[PairingCandidate]]:
    cells = cells or {}
    return [
        [candidate(player, opponent, **cells.get((player, opponent), {}))
         for opponent in opponents]
        for player in players
    ]


class TestPairingScore:
    def test_all_missing_inputs_use_neutral_defaults(self):
        assert pairing_score(None, None, None, None) == NEUTRAL_DEFAULT

    def test_defaults_are_applied_independently(self):
        # matchup_score is the only observed component; the other three are
        # filled independently rather than causing the whole cell to vanish.
        assert pairing_score(1.0, None, None, None) == pytest.approx(0.75)
        assert pairing_score(None, 1.0, None, None) == pytest.approx(0.65)

    def test_it_matches_the_weighted_formula_and_rounds_for_stable_output(self):
        expected = 0.50 * 0.8 + 0.30 * 0.7 + 0.15 * 0.6 + 0.05 * (1.0 - 0.2)
        assert pairing_score(0.8, 0.7, 0.6, 0.2) == round(expected, 6)

    def test_effective_risk_and_confidence_and_risk_penalty_default_to_neutral(self):
        assert effective_confidence(None) == NEUTRAL_DEFAULT
        assert effective_risk(None) == NEUTRAL_DEFAULT
        assert risk_penalty(None) == NEUTRAL_DEFAULT
        assert risk_penalty(0.2) == pytest.approx(0.8)


class TestSolveLineupAssignment:
    def test_finds_the_global_one_to_one_optimum(self):
        players = ["Alice", "Bob"]
        opponents = ["Xavier", "Yara"]
        # All non-matchup components are neutral, so the cells' scores are
        # .25 + .5 * matchup_score.  Independent best-pair selection would
        # give Xavier to both players; the optimizer must not do that.
        cells = {
            ("Alice", "Xavier"): {"matchup_score": 0.70},
            ("Alice", "Yara"): {"matchup_score": 0.60},
            ("Bob", "Xavier"): {"matchup_score": 0.68},
            ("Bob", "Yara"): {"matchup_score": 0.40},
        }
        solution = solve_lineup_assignment(matrix(players, opponents, cells=cells),
                                            players, opponents)

        pairs = {(entry.player_name, entry.opponent_name)
                 for entry in solution.assignments}
        assert pairs == {("Alice", "Yara"), ("Bob", "Xavier")}
        assert len(pairs) == len(solution.assignments) == 2
        assert solution.unassigned_players == []
        assert solution.unassigned_opponents == []
        assert solution.objective_total == pytest.approx(
            pairing_score(0.60, 0.5, 0.5, 0.5)
            + pairing_score(0.68, 0.5, 0.5, 0.5)
        )
        assert [entry.lineup_rank for entry in solution.assignments] == [1, 2]

    @pytest.mark.parametrize(
        ("players", "opponents", "expected_unassigned_players", "expected_unassigned_opponents"),
        [
            (["Alice", "Bob", "Cara"], ["Xavier", "Yara"], ["Cara"], []),
            (["Alice", "Bob"], ["Xavier", "Yara", "Zane"], [], ["Zane"]),
        ],
    )
    def test_unequal_rosters_assign_each_slot_at_most_once(
        self,
        players,
        opponents,
        expected_unassigned_players,
        expected_unassigned_opponents,
    ):
        solution = solve_lineup_assignment(matrix(players, opponents), players, opponents)

        assert len(solution.assignments) == min(len(players), len(opponents))
        assert len({entry.player_id for entry in solution.assignments}) == len(solution.assignments)
        assert len({entry.opponent_id for entry in solution.assignments}) == len(solution.assignments)
        assert solution.unassigned_players == expected_unassigned_players
        assert solution.unassigned_opponents == expected_unassigned_opponents

    def test_lower_total_risk_breaks_an_objective_tie_when_only_one_player_fits(self):
        players = ["High risk", "Low risk"]
        opponents = ["Opponent"]
        # The matchup component offsets the risk contribution so both cells
        # have the same objective.  The calmer player must win the tie-break.
        cells = {
            ("High risk", "Opponent"): {"matchup_score": 0.57, "risk_factor": 0.8},
            ("Low risk", "Opponent"): {"matchup_score": 0.50, "risk_factor": 0.1},
        }
        solution = solve_lineup_assignment(matrix(players, opponents, cells=cells),
                                            players, opponents)

        assert [entry.player_name for entry in solution.assignments] == ["Low risk"]
        assert solution.total_risk == pytest.approx(0.1)
        assert solution.tie_break_applied is True

    def test_higher_total_confidence_breaks_a_remaining_tie(self):
        players = ["Steady", "Uncertain"]
        opponents = ["Opponent"]
        # Risk is equal and matchup offsets confidence, leaving confidence as
        # the deciding criterion after the objective tie.
        cells = {
            ("Steady", "Opponent"): {"matchup_score": 0.38, "confidence": 0.9},
            ("Uncertain", "Opponent"): {"matchup_score": 0.62, "confidence": 0.1},
        }
        solution = solve_lineup_assignment(matrix(players, opponents, cells=cells),
                                            players, opponents)

        assert [entry.player_name for entry in solution.assignments] == ["Steady"]
        assert solution.total_confidence == pytest.approx(0.9)
        assert solution.tie_break_applied is True

    def test_lexicographically_smallest_pairs_break_a_full_tie(self):
        # Reverse input order to prove that this is a semantic tie-break, not
        # an accident of itertools' first permutation.
        players = ["Bob", "Alice"]
        opponents = ["Yara", "Xavier"]
        solution = solve_lineup_assignment(matrix(players, opponents), players, opponents)

        pairs = {(entry.player_name, entry.opponent_name)
                 for entry in solution.assignments}
        assert pairs == {("Alice", "Xavier"), ("Bob", "Yara")}
        assert solution.tie_break_applied is True

    def test_empty_side_returns_all_slots_unassigned(self):
        solution = solve_lineup_assignment([], [], [],)
        assert solution.assignments == []
        assert solution.objective_total == 0.0
        assert solution.unassigned_players == []
        assert solution.unassigned_opponents == []
        assert solution.tie_break_applied is False

    def test_pathological_permutation_count_is_rejected_before_search(self):
        players = [f"P{i}" for i in range(10)]
        opponents = [f"O{i}" for i in range(10)]
        with pytest.raises(ValueError, match="above") as exc_info:
            solve_lineup_assignment(matrix(players, opponents), players, opponents)
        assert f"{MAX_ASSIGNMENT_PERMUTATIONS:,}" in str(exc_info.value)

    def test_matrix_shape_must_match_the_player_and_opponent_lists(self):
        cell = candidate("P1", "O1")
        with pytest.raises(ValueError, match="row"):
            solve_lineup_assignment([], ["P1"], ["O1"])
        with pytest.raises(ValueError, match="expected 2"):
            solve_lineup_assignment([[cell]], ["P1"], ["O1", "O2"])

    def test_an_unobserved_edge_is_a_null_signal_candidate_not_a_null_cell(self):
        with pytest.raises(ValueError, match="null signals"):
            solve_lineup_assignment([[None]], ["P1"], ["O1"])

    @pytest.mark.parametrize("field", [
        "matchup_score", "win_probability", "confidence", "risk_factor", "modeled_win_probability",
    ])
    def test_invalid_unit_inputs_are_rejected(self, field):
        values = {
            name: 0.5
            for name in (
                "matchup_score", "win_probability", "confidence", "risk_factor",
                "modeled_win_probability",
            )
        }
        values[field] = 1.1
        with pytest.raises(ValueError, match="between 0 and 1"):
            pairing_score(**values)


class TestLineupWeights:
    """apa_config.yaml's lineup_optimizer section makes these overridable --
    see scripts.build_lineups.load_weights_from_config -- but this module
    itself stays config-agnostic (its own docstring: "Purely derived and
    purely computational"), so DEFAULT_WEIGHTS must exactly reproduce the
    module's original, pre-config-driven behavior."""

    def test_default_weights_exactly_match_the_original_module_constants(self):
        assert DEFAULT_WEIGHTS == LineupWeights(
            matchup_score=WEIGHT_MATCHUP_SCORE,
            win_probability=WEIGHT_WIN_PROBABILITY,
            confidence=WEIGHT_CONFIDENCE,
            risk_penalty=WEIGHT_RISK_PENALTY,
        )

    def test_pairing_score_with_no_weights_argument_uses_the_defaults(self):
        assert pairing_score(0.8, 0.7, 0.6, 0.2) == pairing_score(
            0.8, 0.7, 0.6, 0.2, weights=DEFAULT_WEIGHTS
        )

    def test_custom_weights_change_the_score_predictably(self):
        """A weight moved entirely onto matchup_score alone must make the
        score depend on nothing else -- proves the override actually
        reaches the formula, not just that it's accepted."""
        only_matchup = LineupWeights(
            matchup_score=1.0, win_probability=0.0, confidence=0.0, risk_penalty=0.0
        )
        assert pairing_score(0.8, 0.1, 0.1, 0.9, weights=only_matchup) == 0.8
        assert pairing_score(0.8, 0.9, 0.9, 0.1, weights=only_matchup) == 0.8

    def test_a_pairing_candidate_uses_default_weights_when_none_given(self):
        cell = candidate("P1", "O1", matchup_score=0.8, win_probability=0.7,
                          confidence=0.6, risk_factor=0.2)
        assert cell.score == pairing_score(0.8, 0.7, 0.6, 0.2)

    def test_a_pairing_candidate_uses_its_own_custom_weights(self):
        only_matchup = LineupWeights(
            matchup_score=1.0, win_probability=0.0, confidence=0.0, risk_penalty=0.0
        )
        cell = PairingCandidate(
            player_id="P1", player_name="P1", opponent_id="O1", opponent_name="O1",
            matchup_score=0.8, win_probability=0.1, confidence=0.1, risk_factor=0.9,
            weights=only_matchup,
        )
        assert cell.score == 0.8

    def test_solve_lineup_assignment_result_reflects_whichever_weights_built_the_matrix(self):
        """The optimizer itself takes no weights argument -- it only ever
        sums each cell's already-computed .score -- so a custom weighting
        must be baked in at matrix-construction time and still change
        which assignment wins."""
        favor_matchup_only = LineupWeights(
            matchup_score=1.0, win_probability=0.0, confidence=0.0, risk_penalty=0.0
        )
        players = ["Alice", "Bob"]
        opponents = ["Xavier", "Yara"]
        cells = {
            ("Alice", "Xavier"): {"matchup_score": 0.9, "win_probability": 0.1},
            ("Alice", "Yara"): {"matchup_score": 0.1, "win_probability": 0.9},
            ("Bob", "Xavier"): {"matchup_score": 0.1, "win_probability": 0.9},
            ("Bob", "Yara"): {"matchup_score": 0.9, "win_probability": 0.1},
        }
        weighted_matrix = [
            [candidate(p, o, weights=favor_matchup_only, **cells[(p, o)])
             for o in opponents]
            for p in players
        ]
        solution = solve_lineup_assignment(weighted_matrix, players, opponents)
        pairs = {(entry.player_name, entry.opponent_name) for entry in solution.assignments}
        # Under matchup-only weighting, Alice's real strength is Xavier
        # (0.9) and Bob's is Yara (0.9) -- the win_probability-heavy
        # default weighting would have picked the opposite pairing.
        assert pairs == {("Alice", "Xavier"), ("Bob", "Yara")}


class TestModeledWinProbability:
    """analytics.win_probability's computed estimate, threaded through as
    its own field -- never conflated with the real, H2H-observed
    win_probability parameter above (see PairingCandidate.modeled_win_probability's
    own docstring)."""

    def test_defaults_to_none_and_contributes_nothing_to_the_score(self):
        with_default_weights = candidate(
            "P1", "O1", matchup_score=0.8, win_probability=0.7, confidence=0.6, risk_factor=0.2,
        )
        assert with_default_weights.modeled_win_probability is None
        # weight_modeled_win_probability defaults to 0.0, so a None here
        # must produce the exact same score as before this field existed.
        assert with_default_weights.score == pairing_score(0.8, 0.7, 0.6, 0.2)

    def test_a_real_value_is_stored_and_visible_on_the_candidate(self):
        cell = PairingCandidate(
            player_id="P1", player_name="P1", opponent_id="O1", opponent_name="O1",
            matchup_score=0.5, win_probability=0.5, confidence=0.5, risk_factor=0.5,
            modeled_win_probability=0.9,
        )
        assert cell.modeled_win_probability == 0.9

    def test_a_nonzero_weight_changes_the_score(self):
        weights = LineupWeights(modeled_win_probability=0.5)
        high = PairingCandidate(
            player_id="P1", player_name="P1", opponent_id="O1", opponent_name="O1",
            matchup_score=0.5, win_probability=0.5, confidence=0.5, risk_factor=0.5,
            modeled_win_probability=0.95, weights=weights,
        )
        low = PairingCandidate(
            player_id="P1", player_name="P1", opponent_id="O1", opponent_name="O1",
            matchup_score=0.5, win_probability=0.5, confidence=0.5, risk_factor=0.5,
            modeled_win_probability=0.05, weights=weights,
        )
        assert high.score > low.score

    def test_changing_weight_modeled_win_probability_changes_which_assignment_wins(self):
        """The same controlled two-player fixture TestSolveLineupAssignment
        already uses to prove the optimizer solves the WHOLE assignment,
        not independent best-pairs -- here proving a configured
        weight_modeled_win_probability alone can flip which pairing wins,
        even when every other real signal is held identical."""
        players = ["Alice", "Bob"]
        opponents = ["Xavier", "Yara"]
        # matchup_score/win_probability/confidence/risk_factor are IDENTICAL
        # across all four cells (so the original four-term formula is a
        # dead tie everywhere, resolved only by the lexicographic
        # tie-break -- ("Alice","Xavier")+("Bob","Yara") sorts first) --
        # only modeled_win_probability differs, and it favors the OPPOSITE
        # pairing, so weight_modeled_win_probability=0 vs >0 can only
        # possibly agree by the lexicographic tie-break's own coincidence,
        # not because the modeled signal had no effect.
        modeled = {
            ("Alice", "Xavier"): 0.1,
            ("Alice", "Yara"): 0.9,
            ("Bob", "Xavier"): 0.9,
            ("Bob", "Yara"): 0.1,
        }
        weights_off = LineupWeights(modeled_win_probability=0.0)
        weights_on = LineupWeights(modeled_win_probability=1.0)

        def build_matrix(weights):
            return [
                [
                    candidate(p, o, matchup_score=0.5, win_probability=0.5,
                             confidence=0.5, risk_factor=0.5,
                             weights=weights)
                    for o in opponents
                ]
                for p in players
            ]

        # Manually stamp modeled_win_probability onto each cell (candidate()
        # doesn't take it as a kwarg -- it's not part of the "readable
        # matrix cell" helper's contract, only PairingCandidate's).
        def with_modeled(weights):
            matrix = build_matrix(weights)
            for i, p in enumerate(players):
                for j, o in enumerate(opponents):
                    cell = matrix[i][j]
                    matrix[i][j] = PairingCandidate(
                        player_id=cell.player_id, player_name=cell.player_name,
                        opponent_id=cell.opponent_id, opponent_name=cell.opponent_name,
                        matchup_score=cell.matchup_score, win_probability=cell.win_probability,
                        confidence=cell.confidence, risk_factor=cell.risk_factor,
                        weights=weights, modeled_win_probability=modeled[(p, o)],
                    )
            return matrix

        off_solution = solve_lineup_assignment(with_modeled(weights_off), players, opponents)
        on_solution = solve_lineup_assignment(with_modeled(weights_on), players, opponents)

        off_pairs = {(e.player_name, e.opponent_name) for e in off_solution.assignments}
        on_pairs = {(e.player_name, e.opponent_name) for e in on_solution.assignments}
        assert off_pairs == {("Alice", "Xavier"), ("Bob", "Yara")}  # lexicographic default
        assert on_pairs == {("Alice", "Yara"), ("Bob", "Xavier")}  # flipped by the modeled signal
        assert off_pairs != on_pairs


class TestRationale:
    def test_no_matchup_history_is_explicit(self):
        assert build_rationale(None, None, None, None) == (
            "No matchup history - assignment based on default scoring."
        )

    def test_names_strong_signals_and_risk(self):
        assert build_rationale(0.8, 0.7, 0.9, 0.1) == (
            "High win probability, strong recent form, low risk."
        )

    def test_unknown_form_and_stability_are_not_silently_invented(self):
        assert build_rationale(0.6, 0.5, None, None) == (
            "Form unknown, stability unknown."
        )
