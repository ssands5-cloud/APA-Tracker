"""Export one historical league-night simulation from an existing HTML export, never a DB.

Only the allowlisted display snapshot is publishable. Original payload/identity keys remain local.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.ultimate_coach_excel_payload import build_team_rosters, build_player_vs_player_pairs
from analytics.ultimate_coach_matchup_evidence import build_pair_index, display_name, members_by_scope
from analytics.ultimate_coach_war_room import war_room_pair, meetings_index, sl_bucket_index, next_send, live_threats
from analytics.match_night_engine import plan_for_war_room, plan_text
from ui.match_night import select_fixture, slim_payload
from scripts.repo_boundary import check_no_links

LABEL = 'REALISTIC DEMO USING HISTORICAL DATA'
SCHEMA = 'ultimate-coach-dashboard-snapshot-v1'


def historical_payload(html: Path, expected_sha256: str):
    """Decode the existing compact-v2 contract exactly; only retain selected-roster evidence."""
    raw = html.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Historical export hash does not match the reviewed artifact')
    match = re.search(r'<script id="uc-data" type="application/json">(.*?)</script>', raw.decode('utf-8'), re.S)
    if not match:
        raise ValueError('Historical export has no embedded payload')
    data = json.loads(match.group(1))
    if data.get('browser_payload_schema') != 'ultimate-coach-browser-compact-v2':
        raise ValueError('Unsupported historical browser payload schema')
    if not data.get('viewer', {}).get('resolved'):
        raise ValueError('Historical viewer identity is not resolved')
    strings = data['strings']
    def deref(value):
        return strings[value] if isinstance(value, int) and not isinstance(value, bool) else value
    fields = data['team_history_fields']
    interned = set(data['team_history_interned_positions'])
    for player in data['players']:
        player['team_history'] = [
            {name: deref(row[i]) if i in interned else row[i] for i, name in enumerate(fields)}
            if isinstance(row, list) else row for row in player.get('team_history', [])]
    built = data['build']['built_at']
    pick = select_fixture(data, str(data['viewer']['external_id']), built)
    if pick['fixture'].get('format') not in ('EIGHT', 'NINE'):
        raise ValueError('Simulation requires a captured singles fixture')
    ids = {str(r['player_id']): r['player_id'] for r in pick['rosters']
           if r['team_scope_key'] in (pick['our_scope'], pick['opp_scope'])}
    evidence = []
    for key, rows in data['evidence_index'].items():
        pid, fmt = key.split('|', 1)
        if pid not in ids or fmt != pick['fixture']['format']:
            continue
        for row in rows:
            if len(row) != len(data['evidence_row_fields']):
                raise ValueError('Historical evidence row shape differs from contract')
            row = list(row)
            for position in data['evidence_interned_positions']:
                row[position] = deref(row[position])
            evidence.append(dict(zip(data['evidence_row_fields'], row), player_id=ids[pid], format=fmt))
    data['evidence'] = evidence
    slim = slim_payload(data, pick, built)
    # No source blob, credentials, tags, private identity or build paths enter the display contract.
    return slim, pick, built, data['build'].get('latest_result', 'Not captured')


def build_snapshot(payload, pick, *, built_at, latest_result, cap=23):
    if not isinstance(cap, int) or cap < 1:
        raise ValueError('Simulation cap must be a positive integer')
    players = payload['players']
    members = members_by_scope(build_team_rosters(payload), players)
    evidence = payload.get('evidence', [])
    ids = {p['id'] for p in players}
    wr = war_room_pair(members[pick['our_scope']], members[pick['opp_scope']],
        build_pair_index(build_player_vs_player_pairs(payload)), pick['fixture']['format'],
        sl_index=sl_bucket_index(evidence, ids),
        meetings=meetings_index(evidence, ids, payload['match_day']['display_timezone']),
        players_by_id={p['id']: p for p in players}, session_name=pick['fixture'].get('session_name') or '')
    plan = plan_for_war_room(wr, cap=cap)
    text = plan_text(plan)
    if not plan.get('lead'):
        raise ValueError('Historical rosters do not support a full start-plan under this simulated cap')
    def roster(rows, prefix):
        return [{'id': f'{prefix}-{i}', 'name': display_name(m, rows), 'skill': m.get('skill_level'),
                 'availability': 'Assumed available (simulation)'} for i, m in enumerate(rows, 1)]
    ours, theirs = roster(wr['ours'], 'our'), roster(wr['theirs'], 'their')
    our_ids = {m['id']: p['id'] for m, p in zip(wr['ours'], ours)}
    opponent_ids = {m['id']: p['id'] for m, p in zip(wr['theirs'], theirs)}
    matrix, responses = {}, {}
    for j, block in enumerate(wr['blocks']):
        oid = opponent_ids[block['opponent']['id']]
        matrix[oid] = {}
        for row in block['rows']:
            direct = row.get('direct')
            matrix[oid][our_ids[row['member']['id']]] = {
                'wins': direct[0] if direct else 0, 'losses': direct[1]-direct[0] if direct else 0,
                'hasDirect': bool(direct), 'note': row['reason'], 'level': row['confidence']['level'],
                'confidenceWhy': row['confidence']['why'], 'category': row['category'],
                'sharedCount': row.get('shared_count', 0)}
        opponent_name = display_name(block['opponent'], wr['theirs'])
        response = next((r for r in plan['responses'] if r['their'] == opponent_name), None)
        ns = next_send(wr, j)
        candidates = []
        for group in ('ranked', 'unordered', 'avoid'):
            for row in ns[group]:
                save = row.get('save') or ''
                if response and row['display'] == response['our']:
                    save = save.replace('consider saving —', 'Sending now spends')
                candidates.append({'name': row['display'], 'reason': row['reason'], 'save': save,
                                   'group': group, 'order': row.get('choice_number')})
        responses[oid] = {'player': response['our'] if response else 'No feasible response',
                         'why': response['why'] if response else 'Check roster and simulated cap.',
                         'level': response['level'] if response else 'Unknown',
                         'cost': (response['cost_later'] if response else '') or 'No extra continuation-cost warning from this plan. This is not a guarantee of no future cost.',
                         'candidates': candidates}
    threats = [{'name': display_name(t['opponent'], wr['theirs']), 'text': t['text'],
                'wins': t['wins'], 'meetings': t['games'], 'playersMet': t['players_met']}
               for t in live_threats(wr)]
    direct_rows = [row for block in wr['blocks'] for row in block['rows'] if row['direct']]
    plan_rows = []
    for pairing in plan['plan_if_we_lead']:
        row = next(row for block in wr['blocks'] if display_name(block['opponent'],wr['theirs']) == pairing['their']
                   for row in block['rows'] if display_name(row['member'],wr['ours']) == pairing['our'])
        plan_rows.append((row['confidence']['points'], pairing, row['confidence']['why']))
    def support(entry):
        _, pair, why = entry
        return {'our': pair['our'], 'their': pair['their'], 'level': pair['level'], 'why': why}
    lead = plan['lead']
    return {
        'schema': SCHEMA, 'mode': 'historical-simulation', 'label': LABEL,
        'provenance': {'capturedAt': built_at, 'latestResult': latest_result,
                       'fixtureWhen': (pick['fixture'].get('local_display') or 'Historical fixture').replace('\u00c2\u00b7','\u00b7'),
                       'notice': 'Historical export replay, not a current APA feed. Availability and cap are simulation assumptions; no results are predicted.'},
        'fixture': {'team': pick['labels'][pick['our_scope']].replace('\u00c2\u00b7','\u00b7'), 'opponent': pick['labels'][pick['opp_scope']].replace('\u00c2\u00b7','\u00b7'),
                    'format': '8-ball' if wr['format']=='EIGHT' else '9-ball', 'when': 'League-night simulation',
                    'venue': 'Historical fixture replay', 'scope': f'{len(ours)} vs {len(theirs)} captured players',
                    'source': 'Reviewed historical HTML export'},
        'simulation': {'cap': cap, 'games': plan['games_left'], 'availability': 'All captured roster players assumed available; none marked played.',
                       'capNote': 'Simulated reference cap for both teams; not a tournament legality check.'},
        'players': ours, 'opponents': theirs, 'evidence': matrix, 'responses': responses,
        'threats': threats, 'plan': {
            'lead': {'player': lead['our'], 'level': lead['level'], 'why': lead['why_lead'], 'alternatives': lead['equally_good']},
            'holds': plan['holds'], 'protect': [h for h in plan['holds'] if h['covers']],
            'sacrifices': plan['sacrifices'], 'responses': text['responses'], 'summary': text['summary'],
            'ifWeLead': plan['plan_if_we_lead'], 'ifTheyLead': plan['plan_if_they_lead'],
            'bestBoard': plan['best_board'], 'safestBoard': plan['safest_board'],
            'cap': plan['cap'], 'fragility': {'rating': plan['fragility']['rating'], 'player': plan['fragility']['player'], 'thinPairings': plan['fragility']['thin_pairings']},
            'strongest': support(max(plan_rows, key=lambda x:x[0])), 'weakest': support(min(plan_rows,key=lambda x:x[0]))},
        'totals': {'meetings': sum(r['direct'][1] for r in direct_rows), 'directPairs': len(direct_rows),
                   'possiblePairs': len(ours)*len(theirs), 'favorablePairs': sum(r['category']=='G' for r in direct_rows),
                   'concerningPairs': sum(r['category']=='R' for r in direct_rows)},
    }


def write_snapshot(document, out: Path):
    check_no_links(out, ROOT, 'dashboard snapshot')
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
    # Explicit projection above is the boundary; these reject accidental future whole-payload copying.
    if re.search(rb'"(?:external_id|player_id|memberNumber|card_number|cookie|access_token|password|source_db|evidence_index|strings)"\s*:', raw):
        raise ValueError('Forbidden private/internal field in dashboard snapshot')
    if b'Bearer ' in raw or b'C:\\' in raw:
        raise ValueError('Credential/path-shaped content refused')
    temp = out.with_name(out.name+'.'+uuid.uuid4().hex+'.tmp')
    check_no_links(temp, ROOT, 'dashboard snapshot temporary file')
    try:
        temp.write_bytes(raw)
        os.replace(temp, out)
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'apps/ultimate-coach-web/data/snapshot.json')
    parser.add_argument('--cap',type=int,default=23)
    args=parser.parse_args(argv)
    check_no_links(args.html,ROOT,'historical export')
    payload,pick,built,latest=historical_payload(args.html,args.expected_sha256)
    document=build_snapshot(payload,pick,built_at=built,latest_result=latest,cap=args.cap)
    write_snapshot(document,args.out)
    print(f"Historical simulation exported: {len(document['players'])} vs {len(document['opponents'])} players; {document['totals']['meetings']} direct meetings. No database opened.")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
