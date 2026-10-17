from pipeline.refresh_summary import completion_counts, completion_summary
from pipeline.refresh_sources import ResponseFixtures
from tests.test_ultimate_coach_refresh import fixtures


def test_counts_are_unique_across_duplicate_division_scopes(tmp_path):
    store=ResponseFixtures(fixtures(tmp_path/'sources'),replay=True)
    counts=completion_counts(store,{'divisions':[{'division_id':'300'},{'division_id':'300'}]})
    assert counts=={'fixtures':12,'teams':2,'players':2}


def test_live_summary_formats_elapsed_time_and_partial_output_reuse():
    text=completion_summary({'fixtures':142,'teams':18,'players':217},live=True,data_reused=False,
        reused=['Ultimate_Coach.xlsx'],directory='runs/example',elapsed=252.9)
    assert 'Fixtures Captured: 142' in text
    assert 'Teams Updated: 18' in text and 'Players Updated: 217' in text
    assert 'Workbook Built: No (up to date; reused)' in text
    assert 'HTML Built: Yes' in text and '4m 12s' in text
