from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Fish(Base):
    __tablename__ = "fish"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    no_fish: Mapped[int] = mapped_column(Integer, default=0)
    common: Mapped[int] = mapped_column(Integer, default=0)
    uncommon: Mapped[int] = mapped_column(Integer, default=0)
    rare: Mapped[int] = mapped_column(Integer, default=0)
    legendary: Mapped[int] = mapped_column(Integer, default=0)
    mythical: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
