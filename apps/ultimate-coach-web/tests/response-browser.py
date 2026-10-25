"""Real React hook/selector checks; static test server, no app routes or auth changes.
Run: node tests/build-response-browser.mjs && python tests/response-browser.py
"""
import argparse
import copy
import json
from io import BytesIO
from PIL import Image
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright, expect

WEB = Path(__file__).resolve().parents[1]
BASE = json.loads((WEB / 'tests/fixtures/captain-command.json').read_text(encoding='utf-8'))['snapshot']
# Complete the existing small synthetic fixture in memory, without protected data.
BASE['responses']['demo-xeno']['candidates'] = [
    {'name': 'Quinn', 'reason': '1–0 in one invented meeting.', 'save': 'Preserve this answer.', 'group': 'supported', 'order': 1},
    {'name': 'Jordan', 'reason': '8–2 in ten invented meetings.', 'save': '', 'group': 'supported', 'order': 2},
    {'name': 'Alex', 'reason': 'Shared support only.', 'save': '', 'group': 'shared', 'order': None},
]
BASE['evidence'] = {'demo-xeno': {player['id']: {
    'wins': 8 if player['name'] == 'Jordan' else 1, 'losses': 2 if player['name'] == 'Jordan' else 0, 'hasDirect': True,
    'note': 'Invented direct record.', 'level': 'Solid',
    'confidenceWhy': 'Synthetic recorded meetings.', 'category': 'direct', 'sharedCount': 0,
} for player in BASE['players']}}
BASE['evidence']['demo-xeno']['alex'].update({
    'wins': 0, 'losses': 0, 'hasDirect': False, 'note': 'Invented shared support.',
    'level': 'Thin', 'confidenceWhy': 'Synthetic shared meetings.', 'category': 'shared', 'sharedCount': 2,
})
BUNDLE = WEB / 'test-results/response-browser/response.js'


def fixture(case):
    data = copy.deepcopy(BASE)
    first = data['opponents'][0]
    second = {**first, 'id': 'demo-second', 'name': 'Riley'}
    data['opponents'].append(second)
    # Different existing roster names make a stale recommendation detectable.
    second_player = next(player for player in data['players'] if player['name'] != data['responses'][first['id']]['player'])
    data['responses'][second['id']] = {**data['responses'][first['id']], 'player': second_player['name'], 'why': 'Second opponent reason.', 'cost': 'Second opponent cost.'}
    if case == 'missing':
        del data['responses'][second['id']]
    if case == 'row':
        del data['evidence'][first['id']][data['players'][0]['id']]
    if case == 'map':
        del data['evidence'][first['id']]
    if case == 'cost':
        data['responses'][first['id']]['cost'] = '   '
    if case == 'missing-cost':
        del data['responses'][first['id']]['cost']
    if case == 'evidence-map':
        del data['evidence']
    if case == 'responses-map':
        del data['responses']
    if case == 'avoid':
        data['responses'][first['id']]['candidates'][-1].update({'group': 'avoid', 'reason': '1–2 in invented direct meetings.'})
        data['evidence'][first['id']]['alex'].update({
            'wins': 1, 'losses': 2, 'hasDirect': True, 'category': 'direct', 'sharedCount': 0,
            'note': 'Invented losing direct record.', 'confidenceWhy': 'Synthetic recorded meetings.',
        })
    if case == 'empty':
        data['opponents'] = []
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/response.js':
            content = BUNDLE.read_bytes()
            kind = 'text/javascript'
        else:
            case = self.path.split('/')[1].split('?')[0] or 'normal'
            css = (WEB / 'src/app/globals.css').read_text(encoding='utf-8')
            data = json.dumps(fixture(case)).replace('<', '\\u003c')
            content = f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><div id="response-root"></div><script src="/response.js"></script><script>mountResponseExplorer({data})</script></body></html>'.encode()
            kind = 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.end_headers()
        self.wfile.write(content)


def assert_answer(page, data, opponent_id):
    """All recommendation fields must follow the same selected opponent."""
    opponent = next(opponent for opponent in data['opponents'] if opponent['id'] == opponent_id)
    answer = data['responses'][opponent_id]
    expect(page.locator('select')).to_have_value(opponent_id)
    expect(page.locator('.re-answer-name')).to_have_text(answer['player'])
    expect(page.locator('.re-answer-dominant > .re-eyebrow')).to_have_text(f'Strategic Recommendation · Response to {opponent["name"]}')
    expect(page.locator('.re-answer-why')).to_have_text(f'Why: {answer["why"]}')
    expect(page.locator('.decision-cautions .command-cost.decision-cost')).to_have_text(f'Sending now costs: {answer["cost"]}')


def assert_missing_answer(page):
    expect(page.locator('select')).to_have_value('demo-second')
    expect(page.get_by_text('No response supplied', exact=True)).to_be_visible()
    expect(page.locator('.re-answer-dominant > .re-eyebrow')).to_have_text('Response to Riley')
    expect(page.get_by_text('Sending now costs: Not established.', exact=False)).to_be_visible()
    expect(page.locator('.re-answer-why')).to_have_count(0)
    # Roster evidence still lists players; only the recommendation must clear.
    expect(page.locator('.re-answer-name')).not_to_have_text(BASE['responses'][BASE['opponents'][0]['id']]['player'])


def assert_native_contrast(page, engine_name):
    # Sample native painted padding: WebKit can ignore a dark CSS background.
    control = page.locator('.re-select')
    painted = Image.open(BytesIO(control.screenshot())).convert('RGB')
    foreground = control.evaluate('el => getComputedStyle(el).color.match(/[\\d.]+/g).map(Number).slice(0,3)')
    def luminance(rgb):
        channels = [v / 255 for v in rgb]
        return sum(weight * (v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4) for weight, v in zip([.2126, .7152, .0722], channels))
    text_light = luminance(foreground)
    for fraction in [.25, .5, .75]:
        background_light = luminance(painted.getpixel((int(painted.width * fraction), painted.height - 5)))
        contrast = (max(text_light, background_light) + .05) / (min(text_light, background_light) + .05)
        assert contrast >= 4.5, f'{engine_name} native opponent selector paint contrast {contrast:.2f}:1'


def main():
    global BUNDLE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', default='test-results/response-browser', help='Test bundle directory relative to the web app; permits isolated mutation validation.')
    args = parser.parse_args()
    BUNDLE = WEB / args.bundle_dir / 'response.js'
    assert BUNDLE.is_file(), f'Build the response browser bundle first: {BUNDLE}'
    normal = fixture('normal')
    first_id = normal['opponents'][0]['id']
    second_id = normal['opponents'][1]['id']
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    count = 0
    try:
        with sync_playwright() as p:
            for engine in [p.chromium, p.webkit]:
                browser = engine.launch()
                page = browser.new_page()
                errors = []
                def record_error(error):
                    errors.append(str(error))
                    print(f'{engine.name} JavaScript error: {error}', flush=True)
                page.on('pageerror', record_error)
                # Regression first: missing response must keep selector usable.
                page.goto(origin + '/missing?opponent=demo-second')
                assert_missing_answer(page)
                page.locator('select').select_option(first_id)
                assert_answer(page, normal, first_id)
                page.locator('select').select_option(second_id)
                assert_missing_answer(page)
                count += 1
                page.goto(origin + '/normal?opponent=demo-second')
                assert_answer(page, normal, second_id)
                page.locator('select').select_option(first_id)
                assert_answer(page, normal, first_id)
                answer = BASE['responses'][BASE['opponents'][0]['id']]
                expect(page.locator('.re-answer-why')).to_contain_text(answer['why'])
                expect(page.locator('.decision-cautions')).to_contain_text(answer['cost'])
                expect(page.locator('.re-answer-dominant')).to_contain_text('Strategic Recommendation')
                expect(page.locator('.re-answer-dominant > .pill')).to_have_text('Send · Strong Evidence')
                expect(page.locator('.decision-evidence')).to_have_text('Head-to-head: 8–2 in 10 recorded meetings')
                assert page.locator('.evidence-row .pill').all_text_contents() == ['Solid Evidence', 'Solid Evidence', 'Thin Evidence']
                page.locator('.re-details-summary').click()
                expect(page.locator('.re-answer-dominant details')).to_contain_text('Recorded Evidence Order is not a send ranking.')
                expect(page.locator('.re-answer-dominant details')).to_contain_text('A 1–0 record can appear before 8–2')
                expected = [(f'Recorded Evidence Order {candidate["order"]}: ' if candidate['order'] else 'Losing direct record: ' if candidate['group'] == 'avoid' else 'Shared, not ordered: ') + candidate['name'] for candidate in answer['candidates']]
                assert page.locator('.re-answer-dominant .candidate > strong').all_text_contents() == expected
                for candidate, rendered in zip(answer['candidates'], page.locator('.candidate').all()):
                    expect(rendered.locator('p').first).to_have_text(candidate['reason'])
                    if candidate['save']:
                        expect(rendered.locator('.notice')).to_have_text(candidate['save'])
                page.locator('select').select_option(second_id)
                assert_answer(page, normal, second_id)
                page.locator('select').select_option(first_id)
                assert_answer(page, normal, first_id)
                page.locator('select').focus()
                page.keyboard.press('ArrowDown')
                page.keyboard.press('Enter')
                assert_answer(page, normal, second_id)
                page.locator('select').focus()
                page.keyboard.press('ArrowUp')
                page.keyboard.press('Enter')
                assert_answer(page, normal, first_id)
                count += 1
                assert_native_contrast(page, engine.name)
                count += 1
                page.goto(origin + '/avoid')
                page.locator('.re-details-summary').click()
                expect(page.locator('.candidate').last.locator('strong')).to_have_text('Losing direct record: Alex')
                expect(page.locator('.candidate').last.locator('p')).to_have_text('1–2 in invented direct meetings.')
                count += 1
                for case in ['row', 'map', 'evidence-map']:
                    page.goto(origin + '/' + case)
                    expect(page.locator('.evidence-row').first).to_contain_text('No direct record')
                    expect(page.locator('.evidence-row').first).to_contain_text('Unknown support')
                    count += 1
                for case in ['cost', 'missing-cost']:
                    page.goto(origin + '/' + case)
                    expect(page.locator('.decision-cautions')).to_contain_text('Sending now costs: Not established.')
                    count += 1
                page.goto(origin + '/responses-map?opponent=demo-second')
                assert_missing_answer(page)
                page.locator('select').select_option(first_id)
                expect(page.locator('.re-answer-dominant > .re-eyebrow')).to_have_text('Response to Xeno')
                expect(page.get_by_text('No response supplied', exact=True)).to_be_visible()
                count += 1
                page.goto(origin + '/empty')
                expect(page.get_by_text('No opponents are available for this fixture.')).to_be_visible()
                assert not errors, errors
                count += 1
                browser.close()
    finally:
        server.shutdown()
    print(f'{count} response scenarios passed (Chromium + WebKit; real React selector, deep-link, keyboard, missing data, native selector contrast; no JS errors).')


if __name__ == '__main__':
    main()
