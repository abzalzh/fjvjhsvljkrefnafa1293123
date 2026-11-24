import json
from pathlib import Path

from app.main import create_app
from app.schemas.contracts import Dataset


ROOT=Path(__file__).parents[2]


def test_openapi_snapshot():
    assert json.loads((ROOT/'docs/openapi.json').read_text(encoding='utf-8'))==create_app().openapi()


def test_dataset_schema_snapshot():
    assert json.loads((ROOT/'docs/dataset.schema.json').read_text(encoding='utf-8'))==Dataset.model_json_schema()
