import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Repository
from app.main import create_app
from app.services.ai_gateway import ParseRequest, parse
from tests.conftest import FIXTURE


def test_api(client, preferences):
    assert client.get('/api/health').json()['data_mode']=='demo'
    assert len(client.get('/api/destinations').json())==3
    assert len(client.get('/api/destinations?interest=culture').json())==1
    assert client.get('/api/destinations/demo_1').status_code==200
    assert client.get('/api/destinations/missing').json()['error']['code']=='http_404'
    body=preferences.model_dump(mode='json')
    first=client.post('/api/trips/generate',json=body)
    assert first.status_code==200
    assert first.json()==client.post('/api/trips/recalculate',json=body).json()
    changed=client.post('/api/trips/recalculate',json=body | {'budget_kzt':100})
    assert changed.json()['status']=='no_results'
    assert client.get('/openapi.json').status_code==200


def test_error_and_cors(client):
    response=client.post('/api/trips/generate',json={})
    assert response.status_code==422
    assert response.json()['error']['details']
    headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'}
    assert client.options('/api/trips/generate',headers=headers).headers['access-control-allow-origin']=='http://localhost:3000'
    assert 'access-control-allow-origin' not in client.options('/api/trips/generate',headers=headers | {'Origin':'https://evil.invalid'}).headers


def test_ai_fallback(client, preferences):
    body=preferences.model_dump(mode='json')
    response=client.post('/api/ai/parse',json={'text':'cheaper','preferences':body}).json()
    assert response['status']=='fallback'
    assert response['preferences']==body
    trip=client.post('/api/trips/generate',json=body).json()['trips'][0]
    explanation=client.post('/api/ai/explain',json={'trip_id':trip['id'],'preferences':body}).json()
    assert explanation['status']=='fallback'
    assert '40100' in explanation['explanation']


@pytest.mark.parametrize('mode', ['raises','bad_field','bad_value','timeout','ok'])
def test_provider_contract(preferences, mode):
    class Provider:
        async def parse(self, text, preferences):
            if mode=='raises': raise RuntimeError('secret')
            if mode=='bad_field': return {'invented':'x'}
            if mode=='bad_value': return {'days':0}
            if mode=='timeout': await asyncio.sleep(1)
            return {'budget_kzt':50000}
    result=asyncio.run(parse(Provider(), ParseRequest(text='cheaper',preferences=preferences),0.01))
    assert result.status==('success' if mode=='ok' else 'fallback')
    assert result.preferences.days==preferences.days
    if mode=='ok': assert result.changes=={'budget_kzt':50000}
    else: assert result.changes=={}


def test_real_mode_is_empty():
    real=Path(__file__).parents[2]/'data'
    with TestClient(create_app(Settings(real,'sqlite:///:memory:'))) as client:
        assert client.get('/api/health').json()['dataset_ready'] is False
        assert client.get('/api/destinations').json()==[]


def test_database_roundtrip(tmp_path, data):
    repo=Repository(f'sqlite:///{(tmp_path / "test.db").as_posix()}')
    repo.initialize(data)
    assert repo.read()==data
    repo.close()


def test_bad_dataset_fails_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(Settings(tmp_path,'sqlite:///:memory:'))):
            pass
