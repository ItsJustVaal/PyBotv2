from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
