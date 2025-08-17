# PyBot ⚽🤖

**PyBot** is a Discord bot for managing a fantasy football-style mini-game with match fixtures, predictions, results tracking, user profiles, and a growing list of fun extras.

---

## Features

### ✅ User Management

- `.join`: Register yourself in the game.
- `.me`: View your user card and stats.

### 📆 Fixtures

- `.setFixtures <gameweek> <"TeamA-TeamB" ...>`: Admin-only. Set fixtures for a specific gameweek.
- `.updateFixture <gameweek> <"OldHome-OldAway"> <"NewHome-NewAway">`: Admin-only. Update a fixture.
- `.addFixture <gameweek> <"TeamA-TeamB">`: Admin-only. Add a fixture.
- `.deleteFixture <gameweek> <"TeamA-TeamB">`: Admin-only. Delete a fixture and reorder indices.
- `.fixtures [gameweek]`: View fixtures for the current or given gameweek.

### 🔮 Predictions

- `.predict <gameweek> <score1-score2 ...>`: Submit predictions for each fixture.
- `.updatePrediction <gameweek> <"TeamA-TeamB"> <score>`: Update prediction.
- `.deletePrediction <gameweek> <"TeamA-TeamB">`: Delete a prediction.
- `.myPredictions [gameweek]`: View personal predictions.
- `.userPredictions <user>`: Admin-only. View another user's predictions.

### 📊 Results

- `.setResults <gameweek> <score1-score2 ...>`: Admin-only. Enter actual match results.
- `.updateResult <gameweek> <"TeamA-TeamB"> <score>`: Admin-only. Update a result.
- `.deleteResult <gameweek> <"TeamA-TeamB">`: Admin-only. Delete a result.

### 🏆 Points

- Auto-calculated when results are added.
- `.points`: View top users by total points.
- `.gameweekPoints`: View current week scores.

🎮 **Fun Commands** (`fun_commands.py`)

- `.8ball`: Ask the magic 8-ball a question.
- `.fish`: Catch fish using 🎣 — compete with other users!
- `.scrabble`: Play scrabble-style minigames for bragging rights.

---

## 🛠️ Developer Notes

### Architecture

- Built using `discord.py` with a custom `PyBot` subclass.
- Uses SQLAlchemy 2.0 with a PostgreSQL/SQLite backend.
- Modular command files (`cogs/`).
- All commands log usage, support ephemeral replies, and run async.

### Database Tables

- **Users**: ID, Discord ID, Nickname, Points, Stats
- **Fixtures**: Gameweek, Home, Away, Order Index, Scores
- **Predictions**: By user/gameweek/team
- **Results**: Fixture scores, updated dynamically
- **Fish**: Users table of fish

### Decorators

- `@ensure_user_exists`: Checks DB registration.
- `@is_admin`: Limits access by Discord ID.

---

## 🚧 TODO

Scrabble
Set User Points to specific number
Set all users to 0 points (helper command at season restart)
Backup db

---

## 📜 License

MIT License © 2025
