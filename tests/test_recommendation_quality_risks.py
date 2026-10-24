"""Synthetic counterexamples for captain review, not desired-ranking specifications.

These assertions reproduce current decisions. A pass establishes behavior, not
that the selected player is more likely to win. No predictive model is used.
"""
from analytics.ultimate_coach_matchup_evidence import build_pair_index
from analytics.ultimate_coach_war_room import (
    blind_send, live_threats, meetings_index, next_send, war_room_pair,
)


def member(pid, name, sl=5, won=0, played=0):
    return {"id": pid, "external_id": str(900000 + pid), "name": name,
            "skill_level": sl, "matches_won": won, "matches_played": played}


def room(records, *, ours=None, theirs=None, dates=None, meeting_sl=None):
    ours = ours or [member(1, "Player A"), member(2, "Player B")]
    theirs = theirs or [member(10, "Opponent X")]
    players = {m['id']: m for m in [*ours, *theirs]}
    pairs, evidence = [], []
    for pid, oid, results in records:
        wins, games = results.count('W'), len(results)
        pairs.extend([{'player_id': pid, 'opponent_id': oid, 'format': 'EIGHT', 'wins': wins, 'games': games},
                      {'player_id': oid, 'opponent_id': pid, 'format': 'EIGHT', 'wins': games-wins, 'games': games}])
        for i, result in enumerate(results):
            evidence.append({'player_id': pid, 'opponent_id': oid, 'format': 'EIGHT', 'result': result,
                'match_date': (dates or {}).get((pid, oid), ['2026-10-01']*games)[i] + 'T19:00:00-06:00',
                'own_skill_level': players.get(pid, {}).get('skill_level'),
                'opponent_skill_level': (meeting_sl or {}).get((pid, oid), players.get(oid, {}).get('skill_level'))})
    return war_room_pair(ours, theirs, build_pair_index(pairs), 'EIGHT',
        meetings=meetings_index(evidence, set(players), 'America/Denver'), session_name='Synthetic session')


def first(w):
    return next_send(w, 0)['ranked'][0]['member']['id']


def test_rq01_single_win_precedes_deeper_winning_record():
    w = room([(1, 10, 'W'), (2, 10, 'WWWWWWWWLL')])
    assert [r['member']['id'] for r in next_send(w, 0)['ranked']] == [1, 2]
    assert [r['direct'] for r in w['blocks'][0]['rows']] == [(1, 1), (8, 10)]


def test_rq02_broader_records_do_not_enter_direct_order():
    ours = [member(1, 'Player A', won=3, played=7), member(2, 'Player B', won=50, played=65)]
    theirs = [member(10, 'Opponent X', won=8, played=8)]
    w = room([(1, 10, 'W')], ours=ours, theirs=theirs)
    assert first(w) == 1
    assert next_send(w, 0)['unknown'] == ['Player B']
    assert w['blocks'][0]['rows'][1]['direct'] is None


def test_rq03_recent_losing_sequence_does_not_change_aggregate_direct_order():
    records = [(1, 10, 'WWWWWWLLL'), (2, 10, 'LLWWW')]
    dates = {(1, 10): ['2020-01-01']*6 + ['2026-10-01']*3,
             (2, 10): ['2020-01-01']*2 + ['2026-10-01']*3}
    w = room(records, dates=dates)
    swapped = {key: list(reversed(value)) for key, value in dates.items()}
    assert first(w) == first(room(records, dates=swapped)) == 1
    assert w['blocks'][0]['rows'][0]['direct'] == (6, 9)
    assert 'Latest dated meeting' in w['blocks'][0]['rows'][0]['date_context']


def test_rq04_opponent_skill_change_is_context_not_a_rank_input():
    w = room([(1, 10, 'WWWW'), (2, 10, 'WWWL')],
             theirs=[member(10, 'Opponent X', sl=7)], meeting_sl={(1, 10): 3, (2, 10): 7})
    assert first(w) == 1
    assert 'Meeting opponent SL 3; roster capture SL 7' in w['blocks'][0]['rows'][0]['sl_context']


def test_rq05_blind_one_losing_pairing_overrides_two_deeper_favorable_pairings():
    w = room([(1, 10, 'W'), (2, 10, 'L'), (2, 11, 'WWWWWWWWLL'), (2, 12, 'WWWWWWWWLL')],
             theirs=[member(10, 'Opponent X'), member(11, 'Opponent Y'), member(12, 'Opponent Z')])
    result = blind_send(w)
    assert result['member']['id'] == 1
    assert (result['direct_coverage'], result['no_record']) == (1, 2)
    b = next(r for r in result['ranked'] if r['member']['id'] == 2)
    assert (b['concerning'], b['favorable'], b['direct_coverage']) == (1, 2, 3)


def test_rq06_blind_category_tie_does_not_prefer_more_meetings():
    records = [(1, 10, 'W'), (1, 11, 'W'), (2, 10, 'WWWWWWWWLL'), (2, 11, 'WWWWWWWWLL')]
    theirs = [member(10, 'Opponent X'), member(11, 'Opponent Y')]
    a = blind_send(room(records, ours=[member(1, 'Player A', sl=7), member(2, 'Player B', sl=4)], theirs=theirs))
    b = blind_send(room(records, ours=[member(1, 'Player A', sl=4), member(2, 'Player B', sl=7)], theirs=theirs))
    assert a['member']['id'] == 1 and b['member']['id'] == 2
    assert {m['id'] for m in a['ties']} == {m['id'] for m in b['ties']} == {1, 2}


def test_rq07_save_condition_is_the_same_for_one_win_and_five_wins():
    theirs = [member(10, 'Opponent X'), member(11, 'Opponent Y')]
    for future in ('W', 'WWWWW'):
        w = room([(1, 10, 'WWW'), (2, 10, 'WWL'), (1, 11, future), (2, 11, 'WL')], theirs=theirs)
        result = next_send(w, 0)
        assert result['ranked'][0]['member']['id'] == 1
        assert 'consider saving' in result['ranked'][0]['save']
        expected_sample = '1 meeting' if len(future)==1 else '5 meetings'
        assert expected_sample in result['ranked'][0]['save']
        assert not next_send(w, 0, unplayed=[True, False])['ranked'][0]['save']


def test_rq08_save_warning_does_not_balance_todays_pairing_against_future_pairing():
    w = room([(1, 10, 'WWWWW'), (2, 10, 'LLL'), (1, 11, 'W'), (2, 11, 'LLL')],
             theirs=[member(10, 'Opponent X'), member(11, 'Opponent Y')])
    result = next_send(w, 0)
    assert first(w) == 1 and 'consider saving' in result['ranked'][0]['save']
    assert [r['member']['id'] for r in result['avoid']] == [2]


def test_rq09_one_meeting_can_create_a_live_threat_with_other_players_unknown():
    result = live_threats(room([(1, 10, 'L')]))
    assert len(result) == 1 and result[0]['live']
    assert (result[0]['wins'], result[0]['games'], result[0]['players_met']) == (1, 1, 1)
    assert 'small sample' in result[0]['text'] and 'no direct record' in result[0]['text']


def test_rq10_roster_threat_can_be_concentrated_on_one_player_and_reverse_with_availability():
    w = room([(1, 10, 'LLLLLLLLLL'), (2, 10, 'WW')])
    threat = live_threats(w)[0]
    assert (threat['wins'], threat['games']) == (10, 12)
    assert first(w) == 2
    # Control: the existing implementation correctly recalculates availability.
    assert live_threats(w, remaining={2}) == []


def test_control_blind_unknown_is_not_recommended_as_safer():
    result = blind_send(room([(2, 10, 'L')]))
    assert result['member'] is None and result['unranked']
    assert 'unknown, not safer' in result['why']


def test_rq11_one_loss_excludes_a_strong_broader_record_from_ranked_answers():
    w = room([(1, 10, 'L'), (2, 10, 'LLLLLL')],
             ours=[member(1, 'Player A', won=50, played=65), member(2, 'Player B', won=3, played=7)])
    result = next_send(w, 0)
    assert result['ranked'] == []
    assert {r['member']['id'] for r in result['avoid']} == {1, 2}
    assert 'No evidence-backed option' in result['headline']


def test_rq12_strong_shared_comparison_stays_below_one_direct_win():
    # Opponent 90 is a common historical opponent, not a current roster slot.
    w = room([(1, 10, 'W'), (2, 90, 'WWWWWWWWLL'), (10, 90, 'LLLLL')])
    result = next_send(w, 0)
    assert first(w) == 1
    assert [r['member']['id'] for r in result['unordered']] == [2]
    shared = next(r for r in w['blocks'][0]['rows'] if r['member']['id'] == 2)
    assert shared['ours'] == (8, 10) and shared['theirs'] == (0, 5)
