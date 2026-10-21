"""Fail-closed production checks. Uses private expectations without printing identifiable values."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
BASE = os.environ.get('UC_WEB_BASE_URL', 'http://127.0.0.1:3013').rstrip('/')
ENGINE = os.environ.get('UC_WEB_BROWSER', 'chromium')


def main():
    private = json.loads((ROOT / 'tmp/uat/protected-historical/snapshot.json').read_text(encoding='utf-8'))
    forbidden = [p['name'] for p in private['players'] + private['opponents']]
    forbidden += [private['fixture']['team'], private['fixture']['opponent']]
    def no_private(raw):
        # Case-fold catches JSON/HTML/JS text independent of capitalization.
        assert not any(value.casefold() in raw.casefold() for value in forbidden), 'Historical identity leaked'
    cases = []
    for folder, suffixes in [(APP / '.next/static', {'.js', '.json', '.map'}), (APP / '.next/server/app', {'.html', '.rsc', '.body'})]:
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix in suffixes:
                no_private(path.read_text(encoding='utf-8', errors='replace'))
    cases.append('all generated public JS and static page payloads exclude historical identities')
    errors = []
    with sync_playwright() as p:
        browser = getattr(p, ENGINE).launch()
        context = browser.new_context(has_touch=ENGINE == 'webkit')
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        for width in (390, 768, 1024):
            page.set_viewport_size({'width': width, 'height': 1024})
            for route in ('/', '/match-night', '/recommendations', '/threats', '/team-status', '/summary'):
                response = page.goto(BASE + route)
                page.wait_for_load_state('networkidle')
                assert response.status in (200, 304)
                no_private(page.content())
                assert 'SYNTHETIC DEMO' in page.locator('.topbar').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                cases.append(f'{width} public demo {route}')
            for route in ('/dashboard', '/dashboard/match-night', '/dashboard/recommendations', '/dashboard/threats', '/dashboard/team-status', '/dashboard/summary'):
                page.goto(BASE + route)
                assert page.url.startswith(BASE + '/sign-in')
                assert page.locator('h1').inner_text() == 'Sign-in is being configured'
                no_private(page.content())
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                cases.append(f'{width} anonymous denial {route}')
        for route in ('/dashboard', '/dashboard/summary'):
            for headers in ({'RSC': '1'}, {'Cookie': '__session=forged-test-cookie'}, {'RSC': '1', 'Cookie': '__session=forged-test-cookie'}):
                url = BASE + route
                for _ in range(5):
                    response = context.request.get(url, headers=headers, max_redirects=0)
                    assert 'no-store' in response.headers.get('cache-control', '')
                    raw = response.text()
                    no_private(raw)
                    if response.status == 200 and 'RSC' in headers:
                        assert 'text/x-component' in response.headers.get('content-type', '')
                        assert re.search(r'NEXT_REDIRECT;replace;/sign-in;30[378];', raw)
                        break
                    assert response.status in (303, 307, 308)
                    url = urljoin(url, response.headers.get('location', ''))
                    assert urlparse(url).netloc == urlparse(BASE).netloc
                    if urlparse(url).path == '/sign-in':
                        break
                    # Next.js may canonicalize an RSC request with ?_rsc before rendering.
                    assert urlparse(url).path == route
                else:
                    raise AssertionError('Protected request did not reach sign-in')
                cases.append(f'{route} server request denial {sorted(headers)}')
        for route in ('/private-snapshots/historical.enc.json', '/data/snapshot.json', '/.env.local', '/sign-up', '/api/snapshot', '/dashboard/other-team'):
            response = context.request.get(BASE + route)
            assert response.status == 404, (route, response.status)
            no_private(response.text())
            cases.append(f'no direct file or unsupported route {route}')
        response = context.request.get(BASE + '/access-denied')
        assert response.status == 200 and 'Access Denied' in response.text()
        no_private(response.text())
        cases.append('unauthorized landing contains no historical data')
        page.goto(BASE + '/sign-in')
        page.screenshot(path=str(ROOT / 'tmp/uat/protected-historical' / f'sign-in-locked-{ENGINE}.png'), full_page=True)
        assert not errors, errors
        browser.close()
    result = {'browser': ENGINE, 'base': BASE, 'passes': len(cases), 'cases': cases,
              'page_errors': errors, 'provider_configured': False, 'live_login_verified': False,
              'physical_device_tested': False}
    (ROOT / 'tmp/uat/protected-historical' / f'access-{ENGINE}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
