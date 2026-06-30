import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.wc import WorldCupCommands
from db.models.base import Base
from db.models.users import User
from db.models.wc_fixtures import WCFixture
from db.models.wc_predictions import WCPrediction


def add_fixture(
    db: Session,
    gameweek: int,
    order_index: int,
    *,
    result_added: int = 0,
    tallied: int = 0,
    home_score: int = 0,
    away_score: int = 0,
) -> None:
    db.add(
        WCFixture(
            order_index=order_index,
            gameweek=gameweek,
            group=f"group-{gameweek}",
            home=f"home-{gameweek}-{order_index}",
            away=f"away-{gameweek}-{order_index}",
            result_added=result_added,
            tallied=tallied,
            home_score=home_score,
            away_score=away_score,
        )
    )


def add_user(db: Session, discord_id: str, nickname: str) -> None:
    db.add(User(discord_id=discord_id, nickname=nickname))


def add_prediction(
    db: Session,
    discord_id: str,
    gameweek: int,
    match_index: int,
    home_score: int,
    away_score: int,
    updated_at: datetime,
) -> None:
    db.add(
        WCPrediction(
            discord_id=discord_id,
            gameweek_id=gameweek,
            match_index=match_index,
            prediction_home=home_score,
            prediction_away=away_score,
            updated_at=updated_at,
        )
    )


class WorldCupGameweekTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        bot: Any = SimpleNamespace(locked=False)
        self.cog = WorldCupCommands(bot)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_current_gameweek_starts_at_earliest_open_round(self) -> None:
        for gameweek in (1, 2, 3):
            add_fixture(self.db, gameweek, 0)
        self.db.commit()

        self.assertEqual(self.cog._get_current_gameweek(self.db), 1)

    def test_round_two_becomes_current_after_round_one_complete_with_no_round_two_results(self) -> None:
        add_fixture(self.db, 1, 0, result_added=1, tallied=1)
        add_fixture(self.db, 1, 1, result_added=1, tallied=1)
        add_fixture(self.db, 2, 0)
        add_fixture(self.db, 2, 1)
        add_fixture(self.db, 3, 0)
        self.db.commit()

        self.assertEqual(self.cog._get_current_gameweek(self.db), 2)

    def test_partially_resulted_round_stays_current_before_future_open_round(self) -> None:
        add_fixture(self.db, 1, 0, result_added=1, tallied=1)
        add_fixture(self.db, 1, 1, result_added=1, tallied=1)
        add_fixture(self.db, 2, 0, result_added=1)
        add_fixture(self.db, 2, 1)
        add_fixture(self.db, 3, 0)
        self.db.commit()

        self.assertEqual(self.cog._get_current_gameweek(self.db), 2)

    def test_current_gameweek_advances_to_round_three_after_round_two_complete(self) -> None:
        for gameweek in (1, 2):
            add_fixture(self.db, gameweek, 0, result_added=1, tallied=1)
            add_fixture(self.db, gameweek, 1, result_added=1, tallied=1)
        add_fixture(self.db, 3, 0)
        self.db.commit()

        self.assertEqual(self.cog._get_current_gameweek(self.db), 3)

    def test_current_gameweek_returns_latest_when_everything_has_results(self) -> None:
        for gameweek in (1, 2, 3):
            add_fixture(self.db, gameweek, 0, result_added=1, tallied=1)
        self.db.commit()

        self.assertEqual(self.cog._get_current_gameweek(self.db), 3)

    def test_current_result_gameweek_prefers_untallied_results(self) -> None:
        add_fixture(self.db, 1, 0, result_added=1, tallied=0)
        add_fixture(self.db, 1, 1, result_added=1, tallied=0)
        add_fixture(self.db, 2, 0)
        self.db.commit()

        self.assertEqual(self.cog._get_current_result_gameweek(self.db), 1)

    def test_prediction_week_can_select_future_group_round_two_or_three(self) -> None:
        add_fixture(self.db, 1, 0)
        self.db.commit()

        selected = self.cog._select_prediction_gameweek(self.db, ("2", "1-0"))
        self.assertEqual(selected, (2, "Gameweek: `2`", ("1-0",), None))

        selected = self.cog._select_prediction_gameweek(self.db, ("3", "0-0"))
        self.assertEqual(selected, (3, "Gameweek: `3`", ("0-0",), None))

    def test_prediction_week_rejects_other_numeric_selectors(self) -> None:
        add_fixture(self.db, 2, 0)
        self.db.commit()

        selected = self.cog._select_prediction_gameweek(self.db, ("1", "1-0"))
        self.assertIsNone(selected[0])
        self.assertIn("Only gameweeks 2 or 3", selected[3] or "")

        selected = self.cog._select_prediction_gameweek(self.db, ("4", "1-0"))
        self.assertIsNone(selected[0])
        self.assertIn("Only gameweeks 2 or 3", selected[3] or "")

    def test_prediction_week_without_selector_uses_current_gameweek(self) -> None:
        add_fixture(self.db, 1, 0, result_added=1, tallied=1)
        add_fixture(self.db, 2, 0)
        self.db.commit()

        selected = self.cog._select_prediction_gameweek(self.db, ("1-0",))
        self.assertEqual(selected, (2, "Gameweek: `2`", ("1-0",), None))

    def test_gameweek_standings_are_computed_after_stored_points_are_reset(self) -> None:
        add_user(self.db, "1", "alice")
        add_user(self.db, "2", "bob")
        add_fixture(self.db, 1, 0, result_added=1, tallied=1, home_score=2, away_score=1)
        add_fixture(self.db, 1, 1, result_added=1, tallied=1, home_score=0, away_score=0)
        add_prediction(self.db, "1", 1, 0, 2, 1, datetime(2026, 6, 1, 12, 0))
        add_prediction(self.db, "1", 1, 1, 1, 1, datetime(2026, 6, 1, 12, 1))
        add_prediction(self.db, "2", 1, 0, 1, 0, datetime(2026, 6, 1, 12, 2))
        add_prediction(self.db, "2", 1, 1, 0, 1, datetime(2026, 6, 1, 12, 3))
        self.db.commit()

        for user in self.db.query(User).all():
            user.wc_gameweek_points = 0
        self.db.commit()

        standings = self.cog._get_gameweek_standings(self.db, 1)

        self.assertEqual([(user.nickname, points) for user, points in standings], [("alice", 4), ("bob", 1)])

    def test_gameweek_standings_keep_latest_prediction_tiebreak(self) -> None:
        add_user(self.db, "1", "alice")
        add_user(self.db, "2", "bob")
        add_fixture(self.db, 1, 0, result_added=1, tallied=1, home_score=2, away_score=1)
        add_prediction(self.db, "1", 1, 0, 1, 0, datetime(2026, 6, 1, 12, 0))
        add_prediction(self.db, "2", 1, 0, 1, 0, datetime(2026, 6, 1, 12, 1))
        self.db.commit()

        standings = self.cog._get_gameweek_standings(self.db, 1)

        self.assertEqual([(user.nickname, points) for user, points in standings], [("alice", 1), ("bob", 1)])

    def test_full_time_score_prefers_regular_time_over_extra_time(self) -> None:
        match = {
            "score": {
                "fullTime": {"home": 2, "away": 1},
                "regularTime": {"home": 1, "away": 1},
                "extraTime": {"home": 2, "away": 1},
                "penalties": {"home": 4, "away": 3},
            }
        }

        self.assertEqual(self.cog._get_full_time_score(match), (1, 1))

    def test_full_time_score_falls_back_to_full_time(self) -> None:
        match = {
            "score": {
                "fullTime": {"home": 3, "away": 0},
                "regularTime": {"home": None, "away": None},
            }
        }

        self.assertEqual(self.cog._get_full_time_score(match), (3, 0))


if __name__ == "__main__":
    unittest.main()
