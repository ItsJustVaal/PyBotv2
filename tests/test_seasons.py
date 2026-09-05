import unittest

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session

from db.models.base import Base
from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User
from db.seasons import (
    get_active_season,
    install_season_routing,
    set_active_season,
    start_new_season,
)


class SeasonRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        set_active_season(None)
        self.engine = create_engine("sqlite:///:memory:", future=True)
        install_season_routing(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        set_active_season(None)

    def test_new_season_routes_regular_fixture_and_prediction_models(self) -> None:
        start_new_season(self.db, 2026)

        self.db.add(
            Fixture(
                order_index=0,
                gameweek=1,
                home="arsenal",
                away="chelsea",
            )
        )
        self.db.add(
            Prediction(
                discord_id="123",
                gameweek_id=1,
                match_index=0,
                prediction_home=2,
                prediction_away=1,
            )
        )
        self.db.commit()

        fixtures = self.db.execute(select(Fixture)).scalars().all()
        predictions = self.db.execute(select(Prediction)).scalars().all()

        self.assertEqual(get_active_season(), 2026)
        self.assertEqual([(f.home, f.away) for f in fixtures], [("arsenal", "chelsea")])
        self.assertEqual(
            [(p.discord_id, p.prediction_home, p.prediction_away) for p in predictions],
            [("123", 2, 1)],
        )
        self.assertEqual(
            self.db.execute(
                text("SELECT COUNT(*) FROM fixtures_2026").execution_options(
                    skip_season_routing=True
                )
            ).scalar_one(),
            1,
        )
        self.assertEqual(
            self.db.execute(
                text("SELECT COUNT(*) FROM predictions_2026").execution_options(
                    skip_season_routing=True
                )
            ).scalar_one(),
            1,
        )

        fixtures[0].home_score = 3
        self.db.execute(update(Fixture).where(Fixture.id == fixtures[0].id).values(result_added=1))
        self.db.delete(predictions[0])
        self.db.commit()

        self.assertEqual(
            self.db.execute(select(Fixture.home_score, Fixture.result_added)).one(),
            (3, 1),
        )
        self.assertEqual(self.db.execute(select(Prediction)).scalars().all(), [])

    def test_new_season_archives_existing_unseasoned_data_and_resets_points(self) -> None:
        self.db.add(Fixture(order_index=0, gameweek=38, home="old", away="season"))
        self.db.add(User(discord_id="123", nickname="alice", gameweek_points=8, overall_points=42))
        self.db.commit()

        change = start_new_season(self.db, 2026)

        self.assertIn("fixtures_2025", change.archived_tables)
        self.assertEqual(
            self.db.execute(
                text("SELECT COUNT(*) FROM fixtures_2025").execution_options(
                    skip_season_routing=True
                )
            ).scalar_one(),
            1,
        )
        self.assertEqual(self.db.execute(select(Fixture)).scalars().all(), [])

        user = self.db.execute(select(User).where(User.discord_id == "123")).scalar_one()
        self.assertEqual(user.gameweek_points, 0)
        self.assertEqual(user.overall_points, 0)

    def test_switching_to_another_new_season_uses_empty_tables(self) -> None:
        start_new_season(self.db, 2026)
        self.db.add(Fixture(order_index=0, gameweek=1, home="a", away="b"))
        self.db.commit()

        start_new_season(self.db, 2027)

        self.assertEqual(self.db.execute(select(Fixture)).scalars().all(), [])
        self.assertEqual(
            self.db.execute(
                text("SELECT COUNT(*) FROM fixtures_2026").execution_options(
                    skip_season_routing=True
                )
            ).scalar_one(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
