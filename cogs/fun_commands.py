import random
from typing import TYPE_CHECKING

import discord
from discord import Message
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.fish import Fish
from db.models.users import User
from decorators.helpers import ensure_user_exists

if TYPE_CHECKING:
    from bot import PyBot


class FunCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.Cog.listener(name="on_message")
    @ensure_user_exists()
    async def fishing(self, message: Message):
        db: Session = self.bot.db
        if message.author.bot:
            return
        discord_id = str(message.author.id)

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
            fish_user = Fish(discord_id=str(message.author.id))
            db.add(fish_user)
            db.commit()

        def roll_fish():
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
                return 5

        if message.content.startswith("<:taco:1116778997129412659>"):
            fish = roll_fish()
            match fish:
                case 0:
                    fish_user.no_fish += 1
                    await message.reply("Nothing lol loser")
                case 1:
                    fish_user.common += 1
                    await message.reply("Common Fish 🎣")
                case 2:
                    fish_user.uncommon += 1
                    await message.reply("Uncommon Fish 🐠")
                case 3:
                    fish_user.rare += 1
                    await message.reply("Rare Fish 🐟")
                case 4:
                    fish_user.legendary += 1
                    await message.reply("Legendary Fish 🐉")
                case 5:
                    fish_user.mythical += 1
                    await message.reply("YOU CAUGHT A MYTHICAL FISH! 🦑")
        else:
            return
        db.commit()

    @commands.command(name="myfish", help="Shows all of your fish")
    @ensure_user_exists()
    async def my_fish(self, ctx: commands.Context):
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        fish = db.execute(
            select(Fish).where(Fish.discord_id == user_id)
        ).scalar_one_or_none()
        if fish is None:
            await ctx.reply("User not found")
            return

        counts = {
            "Mythical": fish.mythical,
            "Legendary": fish.legendary,
            "Rare": fish.rare,
            "Uncommon": fish.uncommon,
            "Common": fish.common,
            "Nothing": fish.no_fish,
        }
        total_caught = fish.common + fish.uncommon + fish.rare + fish.legendary

        embed_desc = []
        embed_desc.append(f"Nothing 💨:  `{str(counts['Nothing'])}`")
        embed_desc.append(f"Common 🎣:  `{str(counts['Common'])}`")
        embed_desc.append(f"Uncommon 🐠:  `{str(counts['Uncommon'])}`")
        embed_desc.append(f"Rare 🐟:  `{str(counts['Rare'])}`")
        embed_desc.append(f"Legendary 🐉:  `{str(counts['Legendary'])}`")
        embed_desc.append(f"Mythical 🦑:  `{str(counts['Mythical'])}`")

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Fishing Log",
            color=discord.Color.blue(),
        )
        embed.description = "\n".join(embed_desc)
        embed.set_footer(text=f"Total fish caught: {total_caught}")

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
