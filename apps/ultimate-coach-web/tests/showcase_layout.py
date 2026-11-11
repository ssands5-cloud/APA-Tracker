"""Showcase layout checks against a RUNNING server (simulated or local real-data beta).

Same style as browser_smoke.py: point UC_WEB_BASE_URL at a running server and run
    python tests/showcase_layout.py
Simulated data comes from `next start` after a build; the local real-data beta needs `next dev` plus
UC_SHOWCASE_REAL=1. The checks are mode-agnostic and print no page content, so no real name is ever logged.
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get('UC_WEB_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
ROUTES = ['/showcase', '/showcase/matchup?pick=1', '/showcase/standings', '/showcase/rankings',
          '/showcase/players', '/showcase/results?week=7']
WIDTHS = (320, 390, 768, 1024, 1280)
BROKEN = re.compile(r'\bNaN\b|\bundefined\b|\[object|Infinity')


def check(page, width, route, errors):
    response = page.goto(BASE + route, wait_until='networkidle')
    where = f'{width}px {route}'
    assert response and response.status == 200, (where, response.status if response else None)
    assert page.locator('h1').count() == 1, (where, 'exactly one h1', page.locator('h1').count())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (where, 'horizontal page scroll')
    text = page.inner_text('body')
    assert not BROKEN.search(text), (where, 'NaN/undefined/[object] in page text')
    assert 'LOCAL BETA' in text or 'SIMULATED' in text, (where, 'data-source label missing')
    assert page.locator('nav[aria-label="Showcase navigation"] a[aria-current="page"]').count() == 1, (where, 'one active tab')
    assert page.locator('.bc-ticker').count() == 1, (where, 'ticker')
    # Tables must scroll inside their own box rather than stretching the page.
    assert page.evaluate("[...document.querySelectorAll('.bc-table-wrap')].every(w => w.getBoundingClientRect().right <= innerWidth + 1)"), (where, 'table wider than the screen')
    assert not errors, (where, errors)


def main() -> int:
    checked = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            context = browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text[:120]) if message.type == 'error' else None)
            for route in ROUTES:
                check(page, width, route, errors)
                checked += 1
            if width <= 768:
                assert page.locator('.bc-tabbar').is_visible(), (width, 'phone tab bar visible')
            context.close()
        browser.close()
    print(f'showcase layout OK: {checked} page loads across {len(WIDTHS)} widths at {BASE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
