# PyBot ⚽🤖

**PyBot** is a Discord bot for managing a fantasy football-style mini-game with match fixtures, predictions, results tracking, user profiles, and a growing list of fun extras.

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
pred top 4
Titles system - title for gameweek winner - title for first mythical fish - title for top4 winner
Rate limit fish command to prevent discord rate limits
DRY up some of the common DB calls

---

## 📜 License

MIT License © 2025
