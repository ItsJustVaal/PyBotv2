# cogs/fixture_commands.py
import shlex
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from decorators.helpers import ensure_user_exists, is_admin

if TYPE_CHECKING:
    from bot import PyBot


class FixtureCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True, name="setFixtures")
    @is_admin()
    async def set_fixtures(self, ctx: commands.Context):
        db: Session = ctx.bot.db

        args = shlex.split(ctx.message.content)
        gameweek = int(args[1])
        fixtures = args[2:]
        print(fixtures)
        current = (
            db.execute(select(Fixture).where(Fixture.gameweek == gameweek))
            .scalars()
            .all()
        )
        if current:
            await ctx.reply(
                f"Fixtures already exist for gameweek {gameweek}. Use update, add or delete",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Fixtures for Gameweek {gameweek}", color=discord.Color.blue()
        )
        embed_display = []

        for i, item in enumerate(fixtures):
            home, away = item.split("-")

            new_fixture = Fixture(
                order_index=i,
                gameweek=gameweek,
                home=home.strip().lower(),
                away=away.strip().lower(),
            )
            print(new_fixture)
            db.add(new_fixture)
            embed_display.append(f" {home} vs {away}")

        db.commit()

        embed.description = "\n".join(embed_display)
        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="updateFixture")
    @is_admin()
    async def update_fixture(self, ctx: commands.Context):
        db: Session = ctx.bot.db

        args = shlex.split(ctx.message.content)
        if len(args) != 4:
            await ctx.reply(
                'Usage: .updateFixture <GW> "Old Home-Old Away" "New Home-New Away"',
                ephemeral=True,
            )
            return

        gameweek = int(args[1])
        home, away = args[2].split("-")
        new_home, new_away = args[3].split("-")

        fixture_to_update = db.execute(
            select(Fixture).where(
                (Fixture.gameweek == gameweek)
                & (Fixture.home == home.lower())
                & (Fixture.away == away.lower())
            )
        ).scalar_one_or_none()
        if fixture_to_update is None:
            await ctx.reply("Fixture does not exist", ephemeral=True)
            return

        fixture_to_update.home = new_home.lower()
        fixture_to_update.away = new_away.lower()

        db.commit()

        await ctx.reply(f"Updated fixture: {home} vs {away} → {new_home} vs {new_away}")

    @commands.command(hidden=True, name="addFixture")
    @is_admin()
    async def add_fixture(self, ctx: commands.Context, gameweek: int, fixture_str: str):
        db: Session = ctx.bot.db

        home, away = fixture_str.strip('"').split("-")

        current_idx = db.execute(
            select(func.max(Fixture.order_index)).where(Fixture.gameweek == gameweek)
        ).scalar_one_or_none()
        if current_idx is None:
            await ctx.reply("No current fixtures for gameweek. Use setFixtures")
            return

        db.add(
            Fixture(
                order_index=current_idx + 1,
                gameweek=gameweek,
                home=home.lower(),
                away=away.lower(),
            )
        )
        db.commit()

        await ctx.invoke(self.bot.get_command("fixtures"), current_gameweek=gameweek)  # type: ignore

    @commands.command(hidden=True, name="deleteFixture")
    @is_admin()
    async def delete_fixture(
        self, ctx: commands.Context, gameweek: int, fixture_str: str
    ):
        db: Session = ctx.bot.db

        home, away = fixture_str.strip('"').split("-")
        fixture_to_delete = db.execute(
            select(Fixture).where(
                (Fixture.gameweek == gameweek)
                & (Fixture.home == home.lower())
                & (Fixture.away == away.lower())
            )
        ).scalar_one_or_none()

        if fixture_to_delete is None:
            await ctx.reply("Fixture not found.", ephemeral=True)
            return

        # Delete the fixture
        db.delete(fixture_to_delete)
        db.commit()

        # Re-fetch and reorder remaining fixtures
        remaining_fixtures = (
            db.execute(
                select(Fixture)
                .where(Fixture.gameweek == gameweek)
                .order_by(Fixture.order_index)
            )
            .scalars()
            .all()
        )

        for new_index, fixture in enumerate(remaining_fixtures):
            fixture.order_index = new_index

        db.commit()

        await ctx.reply(f"Deleted fixture and reordered gameweek {gameweek}.")

    @commands.command(name="fixtures")
    @ensure_user_exists()
    async def get_fixtures(
        self, ctx: commands.Context, current_gameweek: int | None = None
    ):
        message = ctx.message.content.split(" ")
        db: Session = ctx.bot.db
        if current_gameweek is None:
            current_gameweek = db.execute(
                select(func.max(Fixture.gameweek))
            ).scalar_one_or_none()

            if current_gameweek is None or current_gameweek <= 0:
                await ctx.reply("Gameweek is 0, predicting has not started yet.")
                return
        else:
            if len(message) == 2:
                gameweek_request = int(message[1])
                check = (
                    db.execute(
                        select(Fixture).where(Fixture.gameweek == gameweek_request)
                    )
                    .scalars()
                    .first()
                )
                if check is None:
                    await ctx.reply(
                        "Gameweek does not currently exist, leave blank for current GW"
                    )
                    return
                else:
                    current_gameweek = gameweek_request

        embed = discord.Embed(
            title=f"Fixtures for Gameweek {current_gameweek}",
            color=discord.Color.blue(),
        )

        fixture_list = (
            db.execute(select(Fixture).where(Fixture.gameweek == current_gameweek))
            .scalars()
            .all()
        )

        embed_desc = []
        for fixture in fixture_list:
            embed_desc.append(f" {fixture.home.title()} vs {fixture.away.title()}")

        embed.description = "\n".join(embed_desc)
        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(FixtureCommands(bot))
