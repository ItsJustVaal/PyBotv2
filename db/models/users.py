from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String, nullable=False)

    money: Mapped[int] = mapped_column(Integer, default=0)
    gameweek_points: Mapped[int] = mapped_column(Integer, default=0)
    overall_points: Mapped[int] = mapped_column(Integer, default=0)
    free_packs: Mapped[int] = mapped_column(Integer, default=0)
    scrabble_wins: Mapped[int] = mapped_column(Integer, default=0)
    fish_caught: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
