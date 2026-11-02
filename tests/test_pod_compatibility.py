"""Protocol regressions for the proposed contract 2.4.0."""
import asyncio
import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from doctracker.main import app
from doctracker.system import app as system
from doctracker.tester import app as tester
from doctracker.tester.suite import GOLDEN, Fail, check_schema
from doctracker.tester.suite import TestCase as Case

client = TestClient(app)


def setup(sid: str) -> httpx.Response:
    return client.post('/system/test/setup', json={'session_id': sid, 'setup': {}})


def test_session_conflict_release_and_frozen_old_report():
    assert setup('first').status_code == 201
    r = setup('second')
    assert r.status_code == 409 and r.json() == {'message': 'another test session is active', 'source': 'system'}
    assert setup('first').status_code == 409
    assert client.get('/system/test/report?session_id=first').status_code == 200
    assert setup('second').status_code == 201
    old = client.get('/system/test/report?session_id=first').json()
    assert client.get('/system/test/report?session_id=second').status_code == 200
    assert setup('third').status_code == 201
    assert client.get('/system/test/report?session_id=first').json() == old


def test_session_timeout(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(system.time, 'monotonic', lambda: clock[0])
    assert setup('first').status_code == 201
    clock[0] += 719
    assert setup('second').status_code == 409
    clock[0] += 1
    assert setup('second').status_code == 201


def test_preparing_and_coverage_failure(monkeypatch):
    assert setup('first').status_code == 201
    system.sessions['first']['state'] = 'preparing'
    assert client.get('/system/test/report?session_id=first').status_code == 409
    system.sessions['first']['state'] = 'ready'
    def fail(_):
        raise RuntimeError('coverage unavailable')
    monkeypatch.setattr(system.coverage_tracker.start(), 'report', fail)
    assert client.get('/system/test/report?session_id=first').status_code == 500
    assert not system.sessions['first']['report_read']


def sample_result():
    r = copy.deepcopy(GOLDEN['c1-impl-only']['expected'])
    r.update(analysis_id='an-'+'1'*32, repository='pod/fixtures', tool_version='test', created_at='2026-11-01T00:00:00Z')
    return r


def test_optional_drift_fields_accepted_but_unknown_fields_rejected():
    r = sample_result()
    r.update(drift=None, drift_error={'code': 'MODELS_NOT_FOUND', 'message': 'no /models'})
    r['issues'] = []
    check_schema(r)
    r['unrecognized'] = True
    with pytest.raises(Fail):
        check_schema(r)


def mock_transport(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(tester.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def run_mock(monkeypatch, handler):
    mock_transport(monkeypatch, handler)
    tester.sessions['test'] = {'target_url': 'https://target/system', 'state': 'ready', 'report': None}
    response = client.post('/tester/test/run', json={'session_id': 'test'})
    return response, tester.sessions['test']['report']


def base_reply(request):
    if request.url.path.endswith('/test/report'):
        return httpx.Response(200, json={'coverage': {'code': {'covered': 1, 'total': 2, 'basis': 'test'}}})
    return httpx.Response(200, json={})


@pytest.mark.parametrize('features', [[], ['model_drift']])
def test_missing_feature_skips_and_pending_stays_pending(monkeypatch, features):
    health_calls = []
    def handler(req):
        if req.url.path.endswith('/health'):
            health_calls.append(req)
            return httpx.Response(200, json={'status': 'ok', 'tool_version': 'x', 'config_version': 'mapping-v1.1',
                                            'features': features})
        return base_reply(req)
    _, report = run_mock(monkeypatch, handler)
    assert len(health_calls) == 1 and len(report['results']) == 33
    results = {r['test_id']: r for r in report['results']}
    for i in range(18, 22):
        assert results[f'T-{i}']['outcome'] == 'skip'
        assert results[f'T-{i}']['message'] == 'target does not implement prose_detector'
    for i in range(24, 34):
        assert results[f'T-{i}']['message'] == 'expected answers not yet published'
    assert results['T-22']['message'] == 'Phase 5'
    assert results['T-23']['message'] == 'checked by inspection'


@pytest.mark.parametrize('health_mode,source', [('timeout','communication'), ('invalid','system')])
def test_health_failure_isolated_from_shared_tests(monkeypatch, health_mode, source):
    async def handler(req):
        if req.url.path.endswith('/health'):
            if health_mode == 'timeout':
                raise httpx.ReadTimeout('no health', request=req)
            return httpx.Response(200, json={})
        return base_reply(req)
    _, report = run_mock(monkeypatch, handler)
    results = {r['test_id']: r for r in report['results']}
    assert results['T-01']['outcome'] == 'fail'  # ran and received the deliberately invalid body
    for i in range(18,22):
        assert results[f'T-{i}']['source'] == source
        assert results[f'T-{i}']['outcome'] == 'error'
    assert report['coverage']['component']['covered'] == 5  # C4 excluded


@pytest.mark.parametrize('mode,expected', [('timeout',0), ('server_error',1), ('bad_reply',1)])
def test_only_answered_project_tests_count_coverage(monkeypatch, mode, expected):
    async def probe(ctx):
        response = await ctx.get('/analyze-probe')
        if response.json() != {'ok': True}:
            raise Fail('bad reply')
        return 'ok'
    monkeypatch.setattr(tester, 'TESTS', [Case('T-probe','probe',('AC-01',),('C1',),probe)])
    def handler(req):
        if req.url.path.endswith('/health'):
            return httpx.Response(200,json={'status':'ok','tool_version':'x','config_version':'mapping-v1.1'})
        if req.url.path.endswith('/analyze-probe'):
            if mode == 'timeout':
                raise httpx.ReadTimeout('no answer',request=req)
            return httpx.Response(503 if mode == 'server_error' else 200,json={})
        return base_reply(req)
    _, report = run_mock(monkeypatch, handler)
    assert report['coverage']['component']['covered'] == expected


def test_deadline_aborts_stores_report_and_releases_target(monkeypatch):
    calls=[]
    async def slow(ctx):
        await ctx.get('/slow')
        return 'unexpected'
    monkeypatch.setattr(tester,'RUN_LIMIT',0.03)
    monkeypatch.setattr(tester,'TESTS',[Case('T-a','slow',('AC-01',),('C1',),slow),
                                       Case('T-b','unstarted',('AC-01',),('C1',),slow)])
    async def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith('/health'):
            return httpx.Response(200,json={'status':'ok','tool_version':'x','config_version':'mapping-v1.1'})
        if req.url.path.endswith('/slow'):
            await asyncio.sleep(10)
        return base_reply(req)
    response, report = run_mock(monkeypatch,handler)
    assert response.status_code == 500 and response.json()['message'] == 'tester run limit reached'
    assert report['results'] == [
        {'test_id':'T-a','outcome':'error','source':'tester','message':'tester run limit reached'},
        {'test_id':'T-b','outcome':'skip','message':'tester run limit reached'}]
    assert calls == ['/system/health','/system/slow','/system/test/report']
    assert report['coverage']['component']['covered'] == 0
    assert client.get('/tester/test/report?session_id=test').json() == report
    assert client.post('/tester/test/run',json={'session_id':'test'}).status_code == 409


def test_old_request_cannot_add_coverage_to_new_session(monkeypatch):
    import threading

    from tests.test_api import COMMITS, REPO
    entered, release = threading.Event(), threading.Event()
    original = system.run_analysis
    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(system,'run_analysis',slow)
    assert setup('old').status_code == 201
    responses=[]
    thread=threading.Thread(target=lambda: responses.append(client.post('/system/analyze',json={
        'repository':REPO,'commit_id':COMMITS['c1-impl-only']})))
    thread.start()
    try:
        assert entered.wait(5)
        assert client.get('/system/test/report?session_id=old').status_code == 200
        assert setup('new').status_code == 201
    finally:
        release.set()
        thread.join(5)
    assert responses and responses[0].status_code == 200
    code=client.get('/system/test/report?session_id=new').json()['coverage']['code']
    assert code['covered'] in (0,None)  # null only when an outer CI collector owns tracing
