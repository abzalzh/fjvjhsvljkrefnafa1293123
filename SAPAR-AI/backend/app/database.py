import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, DatasetSnapshot
from app.schemas.contracts import Dataset


def load_dataset(path: Path) -> Dataset:
    payload = {name: json.loads((path / f'{name}.json').read_text(encoding='utf-8-sig'))
               for name in ('destinations', 'transport', 'costs', 'sources')}
    return Dataset.model_validate(payload)


class Repository:
    def __init__(self, url: str):
        kwargs = {}
        if url.startswith('sqlite'):
            kwargs['connect_args'] = {'check_same_thread': False}
            if ':memory:' in url:
                kwargs['poolclass'] = StaticPool
        self.engine = create_engine(url, **kwargs)

    def initialize(self, dataset: Dataset):
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session, session.begin():
            session.merge(DatasetSnapshot(id='active', payload=dataset.model_dump(mode='json')))

    def read(self) -> Dataset:
        with Session(self.engine) as session:
            row = session.get(DatasetSnapshot, 'active')
            if row is None:
                raise RuntimeError('Dataset is not initialized')
            return Dataset.model_validate(row.payload)

    def close(self):
        self.engine.dispose()
