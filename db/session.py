from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from db.models import *

engine = create_engine(DATABASE_URL, echo=False, future=True)  # type: ignore
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def migrate_db():
    with engine.connect() as conn:
        def get_columns(table_name: str) -> set:
            result = conn.execute(text(f"PRAGMA table_info({table_name})"))
            return {row[1] for row in result}

        user_cols = get_columns("users")
        if "wc_gameweek_points" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN wc_gameweek_points INTEGER DEFAULT 0"))
        if "wc_overall_points" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN wc_overall_points INTEGER DEFAULT 0"))

        wc_fixture_cols = get_columns("wc_fixtures")
        if wc_fixture_cols and "api_match_id" not in wc_fixture_cols:
            conn.execute(text("ALTER TABLE wc_fixtures ADD COLUMN api_match_id INTEGER"))
        if wc_fixture_cols and "group" not in wc_fixture_cols:
            conn.execute(text("ALTER TABLE wc_fixtures ADD COLUMN \"group\" TEXT"))

        conn.commit()
