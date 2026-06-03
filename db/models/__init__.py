from db.models.base import Base
from db.models.config import Config
from db.models.fish import Fish
from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User
from db.models.wc_fixtures import WCFixture
from db.models.wc_predictions import WCPrediction

__all__ = ["Base", "Config", "User", "Fixture", "Prediction", "Fish", "WCFixture", "WCPrediction"]
