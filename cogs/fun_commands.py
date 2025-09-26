import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.fish import Fish
from db.models.users import User
from decorators.helpers import ensure_user_exists

if TYPE_CHECKING:
    from bot import PyBot
DAILY_CASTS = 5


class FunCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot
        self.fishing_uses: dict[str, tuple[int, str]] = {}
        self._lock = asyncio.Lock()

    def _today_key(self) -> str:
        return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()

    @commands.Cog.listener("on_message")
    async def fishing(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()
        if not content.startswith("<:taco:1116778997129412659>"):
            return

        db: Session = self.bot.db
        discord_id = str(message.author.id)
        today = self._today_key()

        user = db.execute(
            select(User).where(User.discord_id == discord_id)
        ).scalar_one_or_none()
        if user is None:
            await message.reply(".join if you want to keep track of ur fish")
            return

        fish_user = db.execute(
            select(Fish).where(Fish.discord_id == discord_id)
        ).scalar_one_or_none()
        if fish_user is None:
            fish_user = Fish(discord_id=discord_id)
            db.add(fish_user)

        async with self._lock:
            uses_left, last_date = self.fishing_uses.get(
                discord_id, (DAILY_CASTS, today)
            )
            if last_date != today:
                uses_left = DAILY_CASTS
                last_date = today

            if uses_left <= 0:
                self.fishing_uses[discord_id] = (0, today)
                return

            new_uses = uses_left - 1
            self.fishing_uses[discord_id] = (new_uses, today)

        def roll_fish() -> int:
            r = random.random()  # [0.0, 1.0)
            if r < 0.40:
                return 0  # 40.00%
            elif r < 0.85:
                return 1  # +45.00% = 85.00
            elif r < 0.97:
                return 2  # +12.00% = 97.00
            elif r < 0.9899:
                return 3  # +1.99%  = 98.99
            elif r < 0.9999:
                return 4  # +1.00%  = 99.99
            else:
                return 5  # 0.01%

        fish = roll_fish()
        if fish == 0:
            fish_user.no_fish += 1
            text = "Nothing lol loser"
        elif fish == 1:
            fish_user.common += 1
            text = "Common Fish 🎣"
        elif fish == 2:
            fish_user.uncommon += 1
            text = "Uncommon Fish 🐠"
        elif fish == 3:
            fish_user.rare += 1
            text = "Rare Fish 🐟"
        elif fish == 4:
            fish_user.legendary += 1
            text = "Legendary Fish 🐉"
        else:
            fish_user.mythical += 1
            text = "YOU CAUGHT A MYTHICAL FISH! 🦑"

        db.commit()
        await message.reply(f"{text} — casts left today: {new_uses}/{DAILY_CASTS}")
        

    @commands.command(name="myfish", help="Shows all of your fish")
    @ensure_user_exists()
    async def my_fish(self, ctx: commands.Context):
        db: Session = ctx.bot.db
        discord_id = str(ctx.author.id)
        today = self._today_key()

        fish = db.execute(
            select(Fish).where(Fish.discord_id == discord_id)
        ).scalar_one_or_none()
        if fish is None:
            await ctx.reply("User not found")
            return

        async with self._lock:
            uses_left, last_date = self.fishing_uses.get(discord_id, (DAILY_CASTS, today))
            if last_date != today:
                uses_left = DAILY_CASTS
                last_date = today
                self.fishing_uses[discord_id] = (uses_left, last_date)

        counts = {
            "Mythical": fish.mythical,
            "Legendary": fish.legendary,
            "Rare": fish.rare,
            "Uncommon": fish.uncommon,
            "Common": fish.common,
            "Nothing": fish.no_fish,
        }
        total_caught = (
            fish.common + fish.uncommon + fish.rare + fish.legendary + fish.mythical
        )

        embed_desc = [
            f"Nothing 💨:  `{counts['Nothing']}`",
            f"Common 🎣:  `{counts['Common']}`",
            f"Uncommon 🐠:  `{counts['Uncommon']}`",
            f"Rare 🐟:  `{counts['Rare']}`",
            f"Legendary 🐉:  `{counts['Legendary']}`",
            f"Mythical 🦑:  `{counts['Mythical']}`",
        ]

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Fishing Log",
            color=discord.Color.blue(),
            description="\n".join(embed_desc),
        )
        embed.set_footer(
            text=f"Total fish caught: {total_caught} — Casts left today: {uses_left}/{DAILY_CASTS}"
        )

        await ctx.reply(embed=embed)

    @commands.command(name="8ball", help="Ask the 8ball a question")
    async def eight_ball(self, ctx: commands.Context):
        choices = [
            "It is certain",
            "Without a doubt",
            "It is decidedly so",
            "As I see it, yes",
            "Most likely",
            "Fuck Yes",
            "Outlook good",
            "Signs point to yes",
            "Better not tell you now",
            "VAR has a better chance of getting a call right.",
            "Don’t count on it",
            "Outlook not so good",
            "My source (Hannah) says no",
            "My source (Majid) says Yes.",
            "Very doubtful",
            "Fuck no",
            "No.",
            "Hot damn what a good ass question. Yes.",
            "Get out.",
            "What a waste of a question smh. No.",
        ]
        num = random.randint(0, len(choices) - 1)
        choice = choices[num]

        await ctx.reply(choice)


async def setup(bot: "PyBot"):
    await bot.add_cog(FunCommands(bot))
