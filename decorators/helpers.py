# helpers.py

from functools import wraps
from typing import Union

from discord import Message
from discord.ext import commands
from sqlalchemy import select

from config import ADMIN
from db.models.users import User


# Admin Check — match by Discord user ID
def is_admin():
    def predicate(ctx: commands.Context):
        return str(ctx.author.id) == ADMIN

    return commands.check(predicate)


def ensure_user_exists():
    def decorator(func):
        @wraps(func)
        async def wrapper(
            self, ctx_or_msg: Union[commands.Context, Message], *args, **kwargs
        ):
            # 1) If it's a Message from a bot, ignore immediately (prevents loops)
            if isinstance(ctx_or_msg, Message) and ctx_or_msg.author.bot:
                return

            # 2) Get bot + author
            bot = getattr(ctx_or_msg, "bot", None) or getattr(self, "bot", None)
            author = getattr(ctx_or_msg, "author", None)
            if bot is None or author is None:
                return

            # 3) Check user exists
            db = bot.db
            user = db.execute(
                select(User).where(User.discord_id == str(author.id))
            ).scalar_one_or_none()

            if not user:
                # For commands, show the message; for listeners, stay silent to avoid loops
                if isinstance(ctx_or_msg, commands.Context):
                    await ctx_or_msg.reply(
                        "You must first use .join before using this."
                    )
                return

            return await func(self, ctx_or_msg, *args, **kwargs)

        return wrapper

    return decorator
