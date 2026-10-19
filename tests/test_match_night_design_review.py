"""Small exhaustive design counterexamples, not an M3 engine implementation.

Numbers below are hypothetical proposal utilities, never win estimates. These
tests expose assumptions; passing does not validate match-winning performance.
"""
from itertools import permutations
from math import comb, factorial, perm

from analytics.ultimate_coach_war_room import lineup_budget, next_send
from tests.test_recommendation_quality_risks import member, room


def two_player_boards(values):
    # Enumerate only this toy 2x2 audit table; no application solver is added.
    return [tuple(values[i][j] for i, j in enumerate(order)) for order in permutations(range(2))]


def test_m301_best_static_and_safest_static_board_can_both_be_unenforceable():
    values = ((2, -1), (-1, 2))
    boards = two_player_boards(values)
    assert max(map(sum, boards)) == 4
    safest_static = max(boards, key=lambda b: (min(b), sum(b)))
    assert safest_static == (2, 2)
    # Whichever player we lead, their responding captain can choose the cross.
    for lead in range(2):
        worst_reply = min(values[lead][j] + values[1-lead][1-j] for j in range(2))
        assert worst_reply == -2


def test_m302_local_first_send_can_consume_the_only_counter():
    w = room([(1, 10, 'WWW'), (2, 10, 'WWL'), (1, 11, 'WWWWW'), (2, 11, 'LLL')],
             theirs=[member(10, 'Opponent X'), member(11, 'Opponent Y')])
    answer = next_send(w, 0)
    assert answer['ranked'][0]['member']['id'] == 1
    assert 'consider saving' in answer['ranked'][0]['save']
    categories = { (r['member']['id'], b['opponent']['id']): r['category']
                   for b in w['blocks'] for r in b['rows'] }
    assert [categories[pair] for pair in ((1, 10), (2, 11))] == ['G', 'R']
    assert [categories[pair] for pair in ((2, 10), (1, 11))] == ['G', 'G']


def test_m303_ordered_confidence_labels_do_not_determine_additive_utility():
    # All three scales preserve Strong > Solid > Unknown, but choose differently.
    for strong, expected in ((1.5, 'two_solids'), (2, 'tie'), (3, 'strong_unknown')):
        a, b = strong + 0, 1 + 1
        selected = 'tie' if a == b else 'strong_unknown' if a > b else 'two_solids'
        assert selected == expected


def test_m304_unknown_zero_can_look_safer_than_recorded_caution():
    unknown_board, documented_board = (0, 0), (2, -1)
    assert min(unknown_board) > min(documented_board)
    assert sum(unknown_board) < sum(documented_board)
    # This reverses solely because of the chosen objective, not new evidence.


def test_m305_total_and_weakest_link_choose_different_concession_plans():
    concentrated, balanced = (2, 2, -1), (1, 1, 0.5)
    assert sum(concentrated) > sum(balanced)
    assert min(concentrated) < min(balanced)
    # "Must win" alone cannot choose the objective without match-score context.


def test_m306_full_unconstrained_board_count_is_not_single_roster_permutations():
    assert perm(8, 5) == 6720
    assert comb(8, 5) ** 2 * factorial(5) == 376320
    assert comb(8, 5) ** 2 * factorial(5) > perm(8, 5)


def test_m307_remaining_budget_can_remove_an_attractive_send():
    w = room([], ours=[member(1, 'Player A', sl=7), member(2, 'Player B', sl=6), member(3, 'Player C', sl=2)])
    a = lineup_budget(w, cap=8, slots=2, sending=1)
    b = lineup_budget(w, cap=8, slots=2, sending=2)
    assert a['feasible'] is True  # B+C fits this supplied arithmetic constraint.
    assert a['sending_keeps_legal'] is False  # A+C does not.
    assert b['sending_keeps_legal'] is True
    assert 'not a match-legality check' in a['note']


def test_m308_partial_skill_data_cannot_clear_a_board_from_feasible_field_alone():
    w = room([], ours=[member(1, 'Player A', sl=7), member(2, 'Player B', sl=6), member(3, 'Player C', sl=None)])
    result = lineup_budget(w, cap=13, slots=2)
    assert result['feasible'] is True
    assert result['complete'] is False and result['unknown_sl'] == 1
    assert 'no lineup cleared' in result['note']


def test_m309_final_pairings_do_not_identify_the_put_up_information_path():
    ours_lead = [('our lead', 'A'), ('their response', 'X'), ('their lead', 'Y'), ('our response', 'B')]
    theirs_lead = [('their lead', 'X'), ('our response', 'A'), ('our lead', 'B'), ('their response', 'Y')]
    def recorded_pairs(actions):
        return {tuple(next(player for role, player in actions[i:i+2] if role.startswith(side))
                      for side in ('our', 'their')) for i in range(0, len(actions), 2)}
    assert ours_lead != theirs_lead
    assert recorded_pairs(ours_lead) == recorded_pairs(theirs_lead) == {('A', 'X'), ('B', 'Y')}
    # Same recorded pairings admit different first-player and response decisions.


def test_m310_actual_result_does_not_supply_unplayed_alternative_outcome():
    observed = {('A', 'X'): 'W', ('B', 'Y'): 'L'}
    alternative = [('B', 'X'), ('A', 'Y')]
    assert all(pair not in observed for pair in alternative)
    # A retrospective replay cannot score this alternative as two real wins.


def test_m311_one_player_cannot_fulfil_two_simultaneous_hold_back_promises():
    w = room([(1, 10, 'WWW'), (2, 10, 'WWL'), (1, 11, 'WWW'), (1, 12, 'WWW'),
              (2, 11, 'L'), (2, 12, 'L'), (3, 11, 'L'), (3, 12, 'L')],
             ours=[member(1, 'Player A'), member(2, 'Player B'), member(3, 'Player C')],
             theirs=[member(10, 'Opponent X'), member(11, 'Opponent Y'), member(12, 'Opponent Z')])
    warning = next_send(w, 0)['ranked'][0]['save']
    assert 'Opponent Y' in warning and 'Opponent Z' in warning
    greens = {b['opponent']['id']: {r['member']['id'] for r in b['rows'] if r['category']=='G'}
              for b in w['blocks'][1:]}
    attainable = max(sum(chosen[i] in greens[opp] for i, opp in enumerate((11, 12)))
                     for chosen in permutations((1, 2, 3), 2))
    assert attainable == 1
