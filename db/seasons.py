from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from sqlalchemy import MetaData, Table, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db.models.config import Config
from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User

ACTIVE_SEASON_KEY = "active_season"
SEASON_OVER_KEY = "season_over"

_active_season: int | None = None
_routing_installed_engine_ids: set[int] = set()
_ROUTED_TABLES: dict[str, Table] = {
    "fixtures": cast(Table, Fixture.__table__),
    "predictions": cast(Table, Prediction.__table__),
}


@dataclass
class SeasonChange:
    year: int
    created_tables: list[str] = field(default_factory=list)
    existing_tables: list[str] = field(default_factory=list)
    archived_tables: list[str] = field(default_factory=list)


def validate_season_year(year: int) -> int:
    if year < 2000 or year > 2100:
        raise ValueError("Season year must be between 2000 and 2100.")
    return year


def get_active_season() -> int | None:
    return _active_season


def set_active_season(year: int | None) -> None:
    global _active_season
    _active_season = validate_season_year(year) if year is not None else None


def install_season_routing(engine: Engine) -> None:
    engine_id = id(engine)
    if engine_id in _routing_installed_engine_ids:
        return

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _route_season_tables(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        season = get_active_season()
        if season is None:
            return statement, parameters
        if context.execution_options.get("skip_season_routing"):
            return statement, parameters
        if statement.lstrip().split(" ", 1)[0].upper() not in {
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
        }:
            return statement, parameters

        routed = statement
        for base_name in _ROUTED_TABLES:
            routed = re.sub(
                rf'(?<![\w])"?{base_name}"?(?![\w])',
                f"{base_name}_{season}",
                routed,
            )
        return routed, parameters

    _routing_installed_engine_ids.add(engine_id)


def ensure_active_season_tables(db: Session, year: int) -> SeasonChange:
    change = SeasonChange(year=validate_season_year(year))
    for base_name, table in _ROUTED_TABLES.items():
        table_name = _season_table_name(base_name, change.year)
        if inspect(db.bind).has_table(table_name):  # type: ignore[arg-type]
            change.existing_tables.append(table_name)
            continue

        seasonal_table = table.to_metadata(MetaData(), name=table_name)
        seasonal_table.create(bind=db.connection(), checkfirst=True)
        change.created_tables.append(table_name)
    db.commit()
    return change


def start_new_season(db: Session, year: int) -> SeasonChange:
    year = validate_season_year(year)
    previous_season = _get_config_int(db, ACTIVE_SEASON_KEY)

    change = ensure_active_season_tables(db, year)
    if previous_season is None:
        archive_year = year - 1
        change.archived_tables.extend(_archive_unseasoned_tables(db, archive_year))

    _upsert_config(db, ACTIVE_SEASON_KEY, str(year))
    _upsert_config(db, SEASON_OVER_KEY, "false")

    for user in db.execute(select(User)).scalars().all():
        user.gameweek_points = 0
        user.overall_points = 0

    db.commit()
    set_active_season(year)
    db.expunge_all()
    return change


def _archive_unseasoned_tables(db: Session, archive_year: int) -> list[str]:
    archived = []
    for base_name, table in _ROUTED_TABLES.items():
        if not _is_physical_table(db, base_name):
            continue
        row_count = db.execute(
            text(f'SELECT COUNT(*) FROM "{base_name}"').execution_options(
                skip_season_routing=True
            )
        ).scalar_one()
        if row_count == 0:
            continue

        archive_name = _available_archive_name(db, base_name, archive_year)
        seasonal_table = table.to_metadata(MetaData(), name=archive_name)
        seasonal_table.create(bind=db.connection(), checkfirst=True)

        columns = ", ".join(f'"{column.name}"' for column in table.columns)
        db.execute(
            text(
                f'INSERT INTO "{archive_name}" ({columns}) '
                f'SELECT {columns} FROM "{base_name}"'
            ).execution_options(skip_season_routing=True)
        )
        archived.append(archive_name)
    db.commit()
    return archived


def _available_archive_name(db: Session, base_name: str, archive_year: int) -> str:
    preferred = _season_table_name(base_name, archive_year)
    if not inspect(db.bind).has_table(preferred):  # type: ignore[arg-type]
        return preferred

    existing_rows = db.execute(
        text(f'SELECT COUNT(*) FROM "{preferred}"').execution_options(
            skip_season_routing=True
        )
    ).scalar_one()
    if existing_rows == 0:
        return preferred

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_legacy_{timestamp}"


def _get_config_int(db: Session, key: str) -> int | None:
    row = db.execute(select(Config).where(Config.key == key)).scalar_one_or_none()
    if row is None:
        return None
    try:
        return int(row.value)
    except ValueError:
        return None


def _is_physical_table(db: Session, table_name: str) -> bool:
    object_type = db.execute(
        text(
            "SELECT type FROM sqlite_master "
            "WHERE name = :table_name AND type IN ('table', 'view')"
        ).execution_options(skip_season_routing=True),
        {"table_name": table_name},
    ).scalar_one_or_none()
    return object_type == "table"


def _season_table_name(base_name: str, year: int) -> str:
    return f"{base_name}_{validate_season_year(year)}"


def _upsert_config(db: Session, key: str, value: str) -> None:
    row = db.execute(select(Config).where(Config.key == key)).scalar_one_or_none()
    if row is None:
        db.add(Config(key=key, value=value))
    else:
        row.value = value
