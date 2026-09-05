import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.points_commands import PointsCommands
from db.models.base import Base
from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User


class StandingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.bot = SimpleNamespace(db=self.db)
        self.cog = PointsCommands(self.bot)
        self.ctx = SimpleNamespace(bot=self.bot, reply=AsyncMock())

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def predict(self, user, week, match, hour):
        self.db.add(Prediction(
            discord_id=user, gameweek_id=week, match_index=match,
            prediction_home=1, prediction_away=0,
            updated_at=datetime(2026, 9, 1, hour),
        ))

    async def fields(self):
        self.db.commit()
        await self.cog.standings.callback(self.cog, self.ctx)
        return [field.value for field in self.ctx.reply.call_args.kwargs["embed"].fields]

    async def test_filters_nonparticipants_and_keeps_zero_point_predictors(self):
        for name in ("inactive", "past", "current", "points"):
            self.db.add(User(discord_id=name, nickname=name,
                             gameweek_points=2 if name == "points" else 0,
                             overall_points=3 if name == "points" else 0))
        self.db.add(Fixture(gameweek=2, order_index=0, home="a", away="b"))
        self.predict("past", 1, 0, 1)
        self.predict("current", 2, 0, 2)
        self.assertEqual(await self.fields(), [
            "Points: 2\nCurrent: 0", "Points: 3\nPast: 0\nCurrent: 0",
        ])

    async def test_ties_use_latest_update_within_each_standings_period(self):
        for name in ("alice", "bob", "leader"):
            self.db.add(User(discord_id=name, nickname=name,
                             gameweek_points=3 if name == "leader" else 1,
                             overall_points=3 if name == "leader" else 1))
        self.db.add(Fixture(gameweek=2, order_index=0, home="a", away="b"))
        self.predict("alice", 2, 0, 1)
        self.predict("alice", 2, 1, 3)
        self.predict("bob", 2, 0, 2)
        self.predict("bob", 1, 0, 4)
        self.predict("leader", 2, 0, 5)
        self.assertEqual(await self.fields(), [
            "Leader: 3\nBob: 1\nAlice: 1", "Leader: 3\nAlice: 1\nBob: 1",
        ])

    async def test_empty_standings_have_readable_fields(self):
        self.db.add(User(discord_id="inactive", nickname="inactive"))
        self.assertEqual(await self.fields(), [
            "No predictions for this gameweek yet", "No predictions have been made yet",
        ])
