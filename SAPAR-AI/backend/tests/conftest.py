from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import load_dataset
from app.main import create_app
from app.schemas.contracts import TripPreferences


FIXTURE = Path(__file__).parent / 'fixtures' / 'demo'


@pytest.fixture
def data():
    return load_dataset(FIXTURE)


@pytest.fixture
def preferences():
    return TripPreferences(origin='Almaty', budget_kzt=70000, days=3, travelers=1,
                           transport='public', interests=['nature'], start_date='2026-11-26')


@pytest.fixture
def client():
    with TestClient(create_app(Settings(FIXTURE, 'sqlite:///:memory:', demo_mode=True))) as client:
        yield client
