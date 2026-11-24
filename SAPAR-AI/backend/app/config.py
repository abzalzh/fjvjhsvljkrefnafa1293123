import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    demo_mode: bool = False
    cors_origins: tuple[str, ...] = ('http://localhost:3000',)
    ai_timeout_seconds: float = 8.0

    @classmethod
    def from_env(cls):
        demo = os.getenv('SAPAR_DEMO_MODE', 'false').lower() == 'true'
        default_data = ROOT / 'tests' / 'fixtures' / 'demo' if demo else ROOT.parent / 'data'
        db = ROOT / 'sapar.db'
        return cls(
            data_dir=Path(os.getenv('SAPAR_DATA_DIR', str(default_data))).resolve(),
            database_url=os.getenv('DATABASE_URL', f'sqlite:///{db.as_posix()}'),
            demo_mode=demo,
            cors_origins=tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',') if x.strip()),
            ai_timeout_seconds=float(os.getenv('AI_TIMEOUT_SECONDS', '8')),
        )
