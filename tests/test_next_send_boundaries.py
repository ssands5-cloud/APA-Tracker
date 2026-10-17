"""Presentation boundaries; ranked evidence remains identical to Python."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from openpyxl import load_workbook
from ui.export_excel_ultimate_coach import write_workbook
from tests.excel_formula_eval import Workbook
from tests.test_excel_war_room_formulas import _payload
from tests.test_ultimate_coach_war_room_browser import _page, _python_war_room, OURS, THEIRS, CAM


@pytest.mark.parametrize('width',[390,1280])
def test_next_send_boundaries_before_list_and_scoped_context(tmp_path,width):
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            page,errors=_page(tmp_path,browser);page.set_viewport_size({'width':width,'height':900})
            assert 'options against' in page.locator('#next-send h3').inner_text().lower()
            method=page.locator('#next-send .ns-method')
            assert 'Not an overall player ranking' in method.inner_text()
            assert method.evaluate('(e)=>!!(e.compareDocumentPosition(document.querySelector("#next-send .ns-list")) & Node.DOCUMENT_POSITION_FOLLOWING)')
            assert 'Direct-record order 1' in page.locator('#next-send .ns-m').first.inner_text()
            assert '2 meetings' in page.locator('#next-send .ns-sample').first.inner_text()
            assert 'small sample' in page.locator('#next-send .ns-sample').first.inner_text()
            context=page.locator('#next-send .ns-broader')
            assert 'Not used in this ordering' in context.inner_text()
            assert 'Fall 2026' in context.inner_text() and '8-Ball' in context.inner_text()
            assert 'Captured team/session record' in context.inner_text()
            assert 'not a lifetime record' in context.inner_text()
            assert 'No verified direct/shared comparison' in page.locator('#next-send .ns-method').inner_text()
            py=_python_war_room();js=page.evaluate(f"window.__ucWarRoomPair({OURS!r},{THEIRS!r},'EIGHT')")
            assert js['best']==[[r['player'] for r in b['rows'] if r['category'] in ('G','E','I')] for b in py['blocks']]
            assert js['matrix']==[[[c['category'],c['cell'],c['explanation'],c['reason'],c['captain']] for c in row['cells']] for row in py['matrix']]
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert errors==[]
        finally:browser.close()


def test_workbook_neutral_order_and_broader_context(tmp_path):
    path=write_workbook(_payload(),tmp_path/'uc.xlsx',built_at='2026-10-07 18:00 UTC',viewer_member_external_id='1001')
    wb=load_workbook(path);book=Workbook(wb);book.set('Command Center','C6',CAM)
    assert book.display('Command Center','B7')=='NEXT SEND - RECORDED MATCHUP OPTIONS'
    text=book.display('Command Center','B8')
    assert 'Not an overall player ranking' in text
    assert 'Direct-record order 1' in text
    assert 'MEETINGS' in text and 'SMALL SAMPLE' in text
    broader=book.value('Engine',book.name('wr_NsBroader').ref)
    assert 'Not used in this ordering' in broader
    assert 'Fall 2026' in broader and '8-Ball' in broader
    assert 'not a lifetime record' in broader
    assert 'Ann Archer' in broader and 'Bea Baker' in broader and CAM in broader
    wb.close()


def test_broader_zero_missing_and_strong_records_never_reorder(tmp_path):
    from ui.ultimate_coach import render
    payload=_payload()
    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            for label,won,played in [('zero',0,0),('strong',50,65)]:
                payload['players'][0]['team_history'][0]['matches_won']=won
                payload['players'][0]['team_history'][0]['matches_played']=played
                path=tmp_path/(label+'.html')
                path.write_text(render(payload,built_at='2026-10-07 18:00 UTC',viewer_member_external_id='1001'),encoding='utf-8')
                page=browser.new_page(viewport={'width':390,'height':900});page.goto(path.as_uri())
                results.append(page.evaluate(f"window.__ucWarRoomPair({OURS!r},{THEIRS!r},'EIGHT')"))
                text=page.locator('.ns-broader').inner_text()
                assert ('0-0' if label=='zero' else '50-15') in text
                assert 'Not captured' in text
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                page.close()
        finally:browser.close()
    # Only scouting broader-record display changes; all matrix and sends are identical.
    assert results[0]['matrix']==results[1]['matrix']
    assert results[0]['best']==results[1]['best']


def test_one_direct_win_stays_first_while_unranked_broader_record_is_visible(tmp_path):
    from ui.ultimate_coach import render
    from tests.test_excel_war_room_formulas import _games
    payload=_payload()
    payload['evidence']=[r for r in payload['evidence'] if {r['player_id'],r['opponent_id']} not in ({1,10},{2,10})]
    old=_games(1,10,'W',date='2025-09-20T19:00:00-06:00')
    for r in old:r['session_name']='Fall 2025'
    payload['evidence']+=old
    for p in payload['players']:
        for h in p['team_history']:
            if p['id']==1:h.update(matches_won=3,matches_played=7)
            if p['id']==2:h.update(matches_won=50,matches_played=65)
            if p['id']==10:h.update(matches_won=8,matches_played=8)
    path=tmp_path/'early-direct.html';path.write_text(render(payload,built_at='2026-10-07 18:00 UTC',viewer_member_external_id='1001'),encoding='utf-8')
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            page=browser.new_page(viewport={'width':390,'height':900});page.goto(path.as_uri())
            assert page.locator('#next-send [data-send-our]').first.get_attribute('data-send-our')=='1'
            assert page.locator('.ns-sample').first.inner_text()=='1 meeting · small sample'
            broader=page.locator('.ns-broader')
            assert '3-4' in broader.inner_text() and '8-0' in broader.inner_text()
            b=broader.locator('li').filter(has_text='Bea Baker')
            assert '50-15' in b.inner_text() and 'no verified direct meetings' in b.inner_text()
            assert b.is_visible() and 'Not used in this ordering' in broader.inner_text()
        finally:browser.close()
