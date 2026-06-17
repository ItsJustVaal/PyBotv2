import unittest
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.wc import WorldCupCommands
from db.models.base import Base
from db.models.wc_fixtures import WCFixture


def add_fixture(
    db: Session,
    gameweek: int,
    order_index: int,
    *,
    result_added: int = 0,
    tallied: int = 0,
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


if __name__ == "__main__":
    unittest.main()
