"""Production-server checks using synthetic data only. Evidence stays in private tmp/."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = os.environ.get('UC_WEB_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
ENGINE = os.environ.get('UC_WEB_BROWSER', 'chromium')
assert ENGINE in ('chromium', 'webkit')
OUT = Path(__file__).resolve().parents[3] / 'tmp' / 'uat' / 'ultimate-coach-web-phase1' / ENGINE
ROUTES = {'/': 'See the night clearly.', '/match-night': 'Match Night',
          '/recommendations': 'Recommendations', '/threats': 'Threats',
          '/team-status': 'Team Status', '/summary': 'Summary'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors, outside, cases = [], [], []
    with sync_playwright() as p:
        browser = getattr(p, ENGINE).launch()
        context = browser.new_context(has_touch=ENGINE == 'webkit')
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
        page = context.new_page()
        page.on('request', lambda req: outside.append(req.url) if urlparse(req.url).netloc != urlparse(BASE).netloc else None)
        for width in (320, 390, 768, 1024, 1280):
            page.set_viewport_size({'width': width, 'height': 1000})
            for route, heading in ROUTES.items():
                response = page.goto(BASE + route)
                page.wait_for_load_state('networkidle')
                # WebKit exposes the conditional 304 on repeat navigation; content below must still render.
                assert response and response.status in (200, 304), (route, response.status if response else None)
                assert page.locator('h1').inner_text() == heading
                assert 'Invented teams' in page.locator('.demo-banner').inner_text()
                assert page.get_by_role('navigation', name='Main navigation').get_by_role('link').count() == 6
                assert page.locator('a[aria-current="page"]').count() == 1
                assert page.locator('input, textarea, form, button').count() == 0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route)
                assert response.headers.get('x-frame-options') == 'DENY'
                assert 'noindex' in response.headers.get('x-robots-tag', '')
                cases.append(f'{width} {route}')
            page.goto(BASE + '/recommendations')
            page.wait_for_load_state('networkidle')
            page.get_by_label('If they put up').select_option('demo-yara')
            assert page.locator('.answer h2').inner_text() == 'Alex'
            assert 'Unknown evidence' in page.locator('.evidence-list').inner_text()
            page.reload()
            page.wait_for_load_state('networkidle')
            assert page.get_by_label('If they put up').input_value() == 'demo-xeno'
            assert page.locator('.answer h2').inner_text() == 'Jordan'
            assert page.evaluate('localStorage.length') == 0
            assert page.evaluate('sessionStorage.length') == 0
            assert not page.evaluate('navigator.serviceWorker.getRegistrations().then(r => r.length)')
            assert not page.evaluate('indexedDB.databases().then(r => r.length)')
            cases.append(f'{width} view-only selection/reset/no persistence')
        for width in (390, 768, 1280):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.goto(BASE + '/')
            page.screenshot(path=str(OUT / f'home-{width}.png'), full_page=True)
        page.set_viewport_size({'width': 1024, 'height': 1366})
        page.goto(BASE + '/match-night')
        page.screenshot(path=str(OUT / 'match-night-tablet.png'), full_page=True)
        # Verify the visible navigation links, not only direct route loads.
        for route, heading in ROUTES.items():
            page.locator('nav').get_by_role('link', name=heading if route != '/' else 'Home', exact=False).click()
            page.wait_for_url(BASE + route)
            page.wait_for_load_state('networkidle')
            assert page.locator('h1').inner_text() == heading
        cases.append('six visible navigation links')
        for route in ('/', '/match-night'):
            rejected = context.request.post(BASE + route, data='synthetic-write-probe')
            assert rejected.status in (404, 405), (route, rejected.status)
        cases.append('POST rejected on dashboard pages')
        assert not errors, errors
        assert not outside, outside
        browser.close()
    result = {'base': BASE, 'browser': ENGINE, 'passes': len(cases), 'cases': cases,
              'page_errors': errors, 'external_requests': outside, 'physical_device_tested': False}
    (OUT / 'browser-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
