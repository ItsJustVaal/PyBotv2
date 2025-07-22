from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from db.models import *

engine = create_engine(DATABASE_URL, echo=False, future=True)  # type: ignore
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    # create tables
    Base.metadata.create_all(bind=engine)
