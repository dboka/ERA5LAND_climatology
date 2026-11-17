import os
from pathlib import Path
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if os.getenv('CLIMATE_DEMO', '0') == '1' and os.getenv('DATABASE_URL'):
    raise RuntimeError('CLIMATE_DEMO and DATABASE_URL cannot be combined; keep illustrative data separate')
DB_FILE = 'climate-demo.sqlite' if os.getenv('CLIMATE_DEMO', '0') == '1' else 'climate.sqlite'
DEFAULT_DB = f"sqlite:///{(ROOT / 'data' / DB_FILE).as_posix()}"
DATABASE_URL = os.getenv('DATABASE_URL', DEFAULT_DB)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS countries (
      iso3 VARCHAR(3) PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, quality TEXT NOT NULL,
      grid_cells INTEGER NOT NULL DEFAULT 0, coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
      proxy_iso3 VARCHAR(3), note TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS normals (
      iso3 VARCHAR(3) NOT NULL, mmdd VARCHAR(5) NOT NULL, temp_c DOUBLE PRECISION NOT NULL,
      PRIMARY KEY (iso3, mmdd)
    )""",
    """CREATE TABLE IF NOT EXISTS daily (
      iso3 VARCHAR(3) NOT NULL, day DATE NOT NULL, mmdd VARCHAR(5) NOT NULL,
      temp_c DOUBLE PRECISION NOT NULL, provisional BOOLEAN NOT NULL DEFAULT FALSE,
      PRIMARY KEY (iso3, day)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_daily_day ON daily(day)",
    """CREATE TABLE IF NOT EXISTS baseline_daily (
      iso3 VARCHAR(3) NOT NULL, day DATE NOT NULL, mmdd VARCHAR(5) NOT NULL,
      temp_c DOUBLE PRECISION NOT NULL,
      PRIMARY KEY (iso3, day)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_baseline_daily_day ON baseline_daily(day)",
    "CREATE INDEX IF NOT EXISTS ix_baseline_daily_calendar ON baseline_daily(iso3,mmdd)",
    "CREATE TABLE IF NOT EXISTS dataset_info (id INTEGER PRIMARY KEY, mode TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ingested_months (month VARCHAR(7) PRIMARY KEY)",
    """CREATE TABLE IF NOT EXISTS precipitation_baseline_daily (
      iso3 VARCHAR(3) NOT NULL, day DATE NOT NULL, mmdd VARCHAR(5) NOT NULL,
      precip_mm DOUBLE PRECISION NOT NULL CHECK (precip_mm >= 0),
      PRIMARY KEY (iso3, day)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_precipitation_baseline_day ON precipitation_baseline_daily(day)",
    """CREATE TABLE IF NOT EXISTS precipitation_daily (
      iso3 VARCHAR(3) NOT NULL, day DATE NOT NULL, mmdd VARCHAR(5) NOT NULL,
      precip_mm DOUBLE PRECISION NOT NULL CHECK (precip_mm >= 0),
      PRIMARY KEY (iso3, day)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_precipitation_daily_day ON precipitation_daily(day)",
    """CREATE TABLE IF NOT EXISTS precipitation_normals (
      iso3 VARCHAR(3) NOT NULL, mmdd VARCHAR(5) NOT NULL,
      precip_mm DOUBLE PRECISION NOT NULL CHECK (precip_mm >= 0),
      PRIMARY KEY (iso3, mmdd)
    )""",
]


def init_schema() -> None:
    (ROOT / 'data').mkdir(exist_ok=True)
    with engine.begin() as conn:
        for statement in SCHEMA:
            conn.execute(text(statement))
        view_query = """SELECT iso3, day, mmdd, precip_mm FROM precipitation_baseline_daily
            WHERE day < '2020-01-01' UNION ALL
            SELECT iso3, day, mmdd, precip_mm FROM precipitation_daily"""
        prefix = 'CREATE OR REPLACE VIEW' if engine.dialect.name == 'postgresql' else 'CREATE VIEW IF NOT EXISTS'
        conn.execute(text(f'{prefix} precipitation_archive AS {view_query}'))


def scalar(query: str, params: dict | None = None):
    with engine.connect() as conn:
        return conn.execute(text(query), params or {}).scalar()
