"""Run after pnpm install: python tests/captain-command-layout.py.

Checks the real rendered command with synthetic evidence in Chromium and WebKit.
No protected route, account, or production snapshot is accessed.
"""
import json
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((WEB / 'tests/fixtures/captain-command.json').read_text(encoding='utf-8'))


def render(fixture):
    result = subprocess.run(
        ['node', '--experimental-strip-types', 'tests/render-captain-command.mjs'],
        cwd=WEB, input=json.dumps(fixture), capture_output=True, text=True, encoding='utf-8', check=True,
    )
    css = (WEB / 'src/app/globals.css').read_text(encoding='utf-8')
    return result.stdout.replace('<html lang="en">', f'<html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>')


def main():
    fixture = json.loads(json.dumps(FIXTURE))
    fixture['withShell'] = True
    standard = render(fixture)
    long = json.loads(json.dumps(FIXTURE))
    long['snapshot']['fixture']['team'] = 'The Championship Contenders of Evergreen'
    long['snapshot']['fixture']['opponent'] = 'Copper Ridge League Night Challengers'
    long['snapshot']['plan']['lead']['player'] = 'Avery-Alexander Montgomery-Wellington'
    long['snapshot']['plan']['lead']['why'] *= 4
    long['withShell'] = True
    expanded = render(long)
    count = 0
    with sync_playwright() as p:
        for browser_type in [p.chromium, p.webkit]:
            browser = browser_type.launch()
            for width, height in [(390, 664), (390, 844), (1024, 768), (1180, 820), (1440, 900)]:
                page = browser.new_page(viewport={'width': width, 'height': height})
                for html in [standard, expanded]:
                    page.set_content(html)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{browser_type.name}: overflow at {width}'
                    for selector in ['.command-fixture h1', '.command-recommendation h2', '.command-why', '.command-risk', '.command-primary', '.command-dossier']:
                        for element in page.locator(selector).all():
                            box = element.bounding_box()
                            assert box and box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (selector, width, box)
                            assert element.evaluate('''(el) => {
                                const range = document.createRange(); range.selectNodeContents(el);
                                const text = range.getBoundingClientRect();
                                for (let parent = el; parent; parent = parent.parentElement) {
                                    const style = getComputedStyle(parent), box = parent.getBoundingClientRect();
                                    if (['hidden', 'clip'].includes(style.overflowY) && (text.bottom > box.bottom + 1 || text.top < box.top - 1)) return false;
                                }
                                return true;
                            }'''), f'clipped {selector} at {width}'
                    assert page.locator('.command-primary').bounding_box()['height'] >= 44
                    brand = page.locator('.brand').bounding_box()
                    command = page.locator('.captain-command').bounding_box()
                    assert brand['y'] >= command['y'] + command['height'], 'branding precedes the decision'
                    # The four immediate decisions fit on standard phone, iPad and desktop screens.
                    if html is standard:
                        box = page.locator('.command-glance').bounding_box()
                        assert box['y'] + box['height'] <= height, (browser_type.name, width, box)
                    if browser_type.name == 'webkit' and html is standard and width in [390, 1024]:
                        page.screenshot(path=str(WEB / 'node_modules' / f'captain-command-{width}.png'), full_page=True)
                    count += 1
                page.close()
            for name in ['dossiers', 'briefing']:
                for width, height in [(390, 664), (1024, 768), (1180, 820)]:
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    page.set_content(render({**fixture, 'view': name}))
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, width)
                    for element in page.locator('.threat-dossier a, .captain-minute a, .captain-minute summary').all():
                        box = element.bounding_box()
                        if box:
                            assert box['height'] >= 44, (name, width, box)
                    if browser_type.name == 'webkit' and width == 1024:
                        page.screenshot(path=str(WEB / 'node_modules' / f'captain-{name}.png'), full_page=True)
                    page.close()
                    count += 1
            browser.close()
    print(f'{count} captain layouts passed (Chromium + WebKit; phone, iPad, desktop; long text; scouting and briefing).')


if __name__ == '__main__':
    main()
