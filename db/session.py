import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import *

DATABASE_URL = os.getenv("DATABASE")

engine = create_engine(DATABASE_URL, echo=False, future=True)  # type: ignore
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    # create tables
    Base.metadata.create_all(bind=engine)
