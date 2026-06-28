# cogs/admin_commands.py
import os
import shutil
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import engine
from db.models.config import Config
from decorators.helpers import is_admin

if TYPE_CHECKING:
    from bot import PyBot


class AdminCommands(commands.Cog):
    """Cog containing hidden admin-only utility commands."""

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True)
    async def test(self, ctx: commands.Context):
        """Sends a test image to verify the bot is responding correctly."""
        file = discord.File(fp="data/images/jammed.jpg")
        await ctx.reply(file=file)

    @commands.command(hidden=True)
    @is_admin()
    async def lock(self, ctx: commands.Context):
        """Toggles the bot lock state. When locked, prediction commands are disabled."""
        # Toggle lock state and notify
        if self.bot.locked:
            self.bot.locked = False
            await ctx.reply("Unlocked")
            return
        self.bot.locked = True
        await ctx.reply("Locked")

    @commands.command(hidden=True)
    @is_admin()
    async def endSeason(self, ctx: commands.Context):
        """Toggles the season over state. Persists across restarts."""
        db: Session = ctx.bot.db
        config_row = db.execute(
            select(Config).where(Config.key == "season_over")
        ).scalar_one_or_none()

        if self.bot.season_over:
            self.bot.season_over = False
            if config_row:
                config_row.value = "false"
            else:
                db.add(Config(key="season_over", value="false"))
            db.commit()
            await ctx.reply("Season reopened")
        else:
            self.bot.season_over = True
            if config_row:
                config_row.value = "true"
            else:
                db.add(Config(key="season_over", value="true"))
            db.commit()
            await ctx.reply("Season ended")

    @commands.command(hidden=True)
    @is_admin()
    async def backupDb(self, ctx: commands.Context):
        """Creates a timestamped backup copy of the database, keeping only the 3 most recent."""
        import glob

        src = "db/PybotV2.sqlite3"
        backup_dir = "db/backups"
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = f"{backup_dir}/PybotV2_{timestamp}.sqlite3"

        shutil.copy2(src, dest)

        all_backups = sorted(glob.glob(f"{backup_dir}/PybotV2_*.sqlite3"))
        while len(all_backups) > 3:
            os.remove(all_backups.pop(0))

        await ctx.message.delete()
        await ctx.author.send(f"Backup created: `{dest}`")

    @commands.command(hidden=True)
    @is_admin()
    async def restoreDb(self, ctx: commands.Context, filename: str | None = None):
        """Move current DB to db/broken and restore a backup. Usage: `.restoreDb` or `.restoreDb <filename>`"""
        import glob

        backup_dir = "db/backups"
        src = "db/PybotV2.sqlite3"

        if not os.path.exists(src):
            await ctx.reply("No database file found to replace.")
            return

        if filename is None:
            backups = sorted(glob.glob(f"{backup_dir}/PybotV2_*.sqlite3"))
            if not backups:
                await ctx.reply("No backups found.")
                return
            restore_src = backups[-1]
        else:
            restore_src = f"{backup_dir}/{filename}"
            if not os.path.exists(restore_src):
                await ctx.reply(f"Backup `{filename}` not found.")
                return

        os.makedirs("db/broken", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        broken_dest = f"db/broken/PybotV2_broken_{timestamp}.sqlite3"

        await ctx.author.send(
            f"Restoring from `{restore_src}`.\n"
            f"Current DB will be saved as `{broken_dest}`.\n"
            "Restarting to apply restored database..."
        )
        await ctx.message.delete()

        ctx.bot.auto_backup.cancel()
        if ctx.bot._db is not None:
            ctx.bot._db.close()
            ctx.bot._db = None
        engine.dispose()

        shutil.move(src, broken_dest)
        shutil.copy2(restore_src, src)

        os.execv(sys.executable, [sys.executable] + sys.argv)


async def setup(bot: "PyBot"):
    await bot.add_cog(AdminCommands(bot))
