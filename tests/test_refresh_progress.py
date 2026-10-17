"""Operator-visible evidence at the real console/login/acquisition boundaries."""
from __future__ import annotations
import builtins
import threading
import time
import pytest
from pipeline.refresh_sources import ResponseFixtures
from tools import run_ultimate_coach_browser as runner


def test_manual_enter_receipt_browser_close_and_return_are_visible(monkeypatch,capsys):
    events=[];handlers={}
    class Page:
        def goto(self,url):events.append('goto')
    class Context:
        def on(self,event,callback):handlers[event]=callback
        def new_page(self):return Page()
    class Browser:
        def new_context(self):return Context()
        def close(self):events.append('closed')
    class Chromium:
        def launch(self,**kw):return Browser()
    class Manager:
        chromium=Chromium()
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr('playwright.sync_api.sync_playwright',lambda:Manager())
    def enter(prompt):
        events.append('enter')
        class Request:headers={'authorization':'PRIVATE-ONLY-IN-MEMORY'}
        class Response:url='https://gql.poolplayers.com/graphql';request=Request()
        handlers['response'](Response())
        return ''
    monkeypatch.setattr(builtins,'input',enter)
    assert runner.capture_access_token()=='PRIVATE-ONLY-IN-MEMORY'
    assert events==['goto','enter','closed']
    output=capsys.readouterr().out
    assert 'ENTER RECEIVED' in output
    assert output.index('ENTER RECEIVED') < output.index('Closing login browser') < output.index('Login browser closed')
    assert 'PRIVATE-ONLY-IN-MEMORY' not in output


def test_source_request_logs_start_before_blocking_and_completion_after_response(tmp_path):
    messages=[];entered=threading.Event();release=threading.Event()
    store=ResponseFixtures(tmp_path,progress=messages.append)
    def fetch():
        entered.set();release.wait(2)
        return {'viewer':{'id':1}}
    thread=threading.Thread(target=lambda:store('query dashboardTeams { viewer { id } }',{},fetch))
    thread.start()
    try:
        assert entered.wait(1)
        assert any('START' in x and 'dashboardTeams' in x for x in messages)
        assert not any('DONE' in x for x in messages)
    finally:release.set();thread.join(2)
    assert any('DONE' in x and 'dashboardTeams' in x for x in messages)
    count=len(messages)
    store('query dashboardTeams { viewer { id } }',{},lambda:pytest.fail('cached request sent again'))
    assert len(messages)==count



def test_slow_stage_reports_heartbeat_without_moving_work_to_background():
    from pipeline.refresh_progress import progress_span
    messages=[];owner=threading.get_ident()
    with progress_span(messages.append,'slow validation',interval=0.02):
        assert threading.get_ident()==owner
        time.sleep(0.09)
    assert messages[0]=='START slow validation'
    assert any('STILL RUNNING slow validation' in x for x in messages)
    assert messages[-1].startswith('DONE slow validation')
    count=len(messages);time.sleep(0.05)
    assert len(messages)==count


def test_failed_request_never_logs_done_or_secret_details(tmp_path):
    messages=[];store=ResponseFixtures(tmp_path,progress=messages.append)
    def fail():raise RuntimeError('SECRET-DETAIL-MUST-NOT-BE-LOGGED')
    with pytest.raises(RuntimeError):store('query dashboardTeams { viewer { id } }',{},fail)
    assert any('FAILED' in x and 'RuntimeError' in x for x in messages)
    assert not any('DONE' in x or 'SECRET-DETAIL' in x for x in messages)
    assert not store.entries


def test_timer_stops_after_worker_failure():
    from pipeline.refresh_progress import progress_span
    messages=[]
    with pytest.raises(ValueError):
        with progress_span(messages.append,'failing stage',interval=0.01):
            time.sleep(0.03);raise ValueError('test')
    assert messages[-1]=='FAILED failing stage: ValueError'
    count=len(messages);time.sleep(0.04);assert len(messages)==count
