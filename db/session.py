from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import *

# SQLite URL; swap for Postgres/MySQL as needed
DATABASE_URL = "sqlite:///PybotV2.sqlite3"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    # create tables
    Base.metadata.create_all(bind=engine)
