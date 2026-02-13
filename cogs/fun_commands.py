import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from bs4 import BeautifulSoup
from discord.ext import commands
# from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.fish import Fish
from db.models.users import User
from decorators.helpers import ensure_user_exists

if TYPE_CHECKING:
    from bot import PyBot
DAILY_CASTS = 5
LEAGUE_CONFIG = {
    "pl": {
        "source_cols": ["XPOS", "TEAM", "XPTS", "TITLE", "UCL", "REL"],
        "out_headers": ["POS", "TEAM", "XPTS", "TITLE", "UCL", "REL"],
        "align": ["r", "l", "r", "r", "r", "r"],
        "title": "Premier League – Predicted Table",
        "url": "https://theanalyst.com/competition/premier-league/table",
        "tab_text": "PREDICTED",
    },
    "cl": {
        "source_cols": ["TEAM", "XPOS", "FINAL", "WINNER"],
        "out_headers": ["TEAM", "XPOS", "FINAL", "WINNER"],
        "align": ["l", "r", "r", "r"],
        "title": "Champions League – Predicted Table",
        "url": "https://theanalyst.com/competition/uefa-champions-league/table",
        "tab_text": "PREDICTED",
    },
    "eul": {
        "source_cols": ["TEAM", "XPOS", "FINAL", "WINNER"],
        "out_headers": ["TEAM", "XPOS", "FINAL", "WINNER"],
        "align": ["l", "r", "r", "r"],
        "title": "Europa League – Predicted Table",
        "url": "https://theanalyst.com/competition/uefa-europa-league/table",
        "tab_text": "PREDICTED",
    },
    "buli": {
        "source_cols": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "out_headers": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "align": ["l", "r", "r", "r", "r", "r"],
        "title": "Bundesliga - Predicted Table",
        "url": "https://theanalyst.com/competition/bundesliga/table",
        "tab_text": "PREDICTED",
    },
    "lali": {
        "source_cols": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "out_headers": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "align": ["l", "r", "r", "r", "r", "r"],
        "title": "La Liga - Predicted Table",
        "url": "https://theanalyst.com/competition/la-liga/table",
        "tab_text": "PREDICTED",
    },
    "l1": {
        "source_cols": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "out_headers": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "align": ["l", "r", "r", "r", "r", "r"],
        "title": "Ligue 1 - Predicted Table",
        "url": "https://theanalyst.com/competition/ligue-1/table",
        "tab_text": "PREDICTED",
    },
    "sa": {
        "source_cols": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "out_headers": ["TEAM", "XPOS", "XPTS", "TITLE", "UCL", "REL"],
        "align": ["l", "r", "r", "r", "r", "r"],
        "title": "Serie A - Predicted Table",
        "url": "https://theanalyst.com/competition/serie-a/table",
        "tab_text": "PREDICTED",
    },
}

# alignment per column: 'l' = left, 'r' = right
PREDICTED_ALIGN = ["r", "l", "r", "r", "r", "r", "r", "r"]


class FunCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot
        self.fishing_uses: dict[str, tuple[int, str]] = {}
        self._lock = asyncio.Lock()
        self.opta_lock = asyncio.Lock()

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
            uses_left, last_date = self.fishing_uses.get(
                discord_id, (DAILY_CASTS, today)
            )
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

#     @commands.command(
#         name="opta",
#         help="Get the latest Opta pedictions. Usage: .opta pl / cl / buli etc.",
#     )
#     @commands.cooldown(1, 20, commands.BucketType.user)
#     @commands.cooldown(1, 60, commands.BucketType.default)
#     async def opta(self, ctx: commands.Context, league: str = "pl"):
#         league = league.lower()
#         if league == "help":
#             await ctx.reply("League Codes: pl, cl, buli, lali, l1, sa")
#             return

#         if league not in LEAGUE_CONFIG:
#             await ctx.reply("Unsupported league. Try .opta help for league list")
#             return

#         await ctx.reply("Loading stand by...", delete_after=5)

#         cfg = LEAGUE_CONFIG[league]

#         async def fetch_predicted_table(
#             url: str, tab_text: str
#         ) -> tuple[list[str], list[list[str]]]:
#             async with async_playwright() as p:
#                 try:
#                     browser = await asyncio.wait_for(
#                         p.chromium.launch(headless=True),
#                         timeout=5
#                     )
#                     print("Connected to Playwright server!")
#                 except Exception as e:
#                     print("Playwright connect failed:", repr(e))
#                     return [], []
                
#                 page = await browser.new_page()
#                 await page.goto(url, wait_until="networkidle")

#                 # Click Predicted tab
#                 await page.get_by_text(tab_text, exact=False).click()
#                 await page.wait_for_timeout(2000)

#                 html = await page.content()
#                 await browser.close()

#             soup = BeautifulSoup(html, "html.parser")
#             table = soup.find("table")
#             if not table:
#                 return [], []

#             # headers
#             thead = table.find("thead")
#             header_cells = thead.find_all("th") if thead else []
#             headers = [h.get_text(strip=True).upper() for h in header_cells]

#             # rows
#             tbody = table.find("tbody")
#             if not tbody:
#                 return headers, []

#             rows: list[list[str]] = []
#             for tr in tbody.find_all("tr"):
#                 cells = [td.get_text(strip=True) for td in tr.find_all("td")]
#                 if cells:
#                     rows.append(cells)

#             return headers, rows

#         def format_league_table(headers: list[str], rows: list[list[str]]) -> str:
#             source_cols = cfg["source_cols"]
#             out_headers = cfg["out_headers"]
#             align = cfg["align"]
#             num_cols = len(out_headers)

#             # map header name -> index
#             header_index: dict[str, int] = {h: i for i, h in enumerate(headers)}
#             indices: list[int] = []
#             for col in source_cols:
#                 try:
#                     indices.append(header_index[col])
#                 except KeyError:
#                     raise RuntimeError(f"Column {col!r} not found in headers {headers}")

#             # trim rows to the configured columns / order
#             trimmed_rows: list[list[str]] = []
#             for r in rows:
#                 trimmed_rows.append([r[i] if i < len(r) else "" for i in indices])

#             # column widths
#             col_widths = [len(h) for h in out_headers]
#             for row in trimmed_rows:
#                 for i in range(num_cols):
#                     col_widths[i] = max(col_widths[i], len(row[i]))

#             def fmt_cell(text: str, width: int, a: str) -> str:
#                 return text.rjust(width) if a == "r" else text.ljust(width)

#             def fmt_row(cols: list[str]) -> str:
#                 padded = []
#                 for i in range(num_cols):
#                     val = cols[i] if i < len(cols) else ""
#                     padded.append(fmt_cell(val, col_widths[i], align[i]))
#                 return " ".join(padded)

#             lines: list[str] = []
#             lines.append(fmt_row(out_headers))  # header
#             lines.append(" ".join("-" * w for w in col_widths))  # separator
#             for r in trimmed_rows:
#                 lines.append(fmt_row(r))  # data rows

#             table_str = "\n".join(lines)
#             return f"```text\n{table_str}\n```"

#         # === actual command flow ===
#         async with self.opta_lock:
#             headers, rows = await fetch_predicted_table(cfg["url"], cfg["tab_text"])
#             if not rows:
#                 await ctx.send("Could not fetch Opta data right now.")
#                 return

#             table_str = format_league_table(headers, rows)
#             title = f"**{cfg['title']}**\n"
#             await ctx.send(title + table_str)

#     @opta.error
#     async def opta_error(self, ctx, error):
#         if isinstance(error, commands.CommandOnCooldown):
#             await ctx.reply(
#                 f"Try again in **{error.retry_after:.1f}s**.",
#                 delete_after=5,
#             )


async def setup(bot: "PyBot"):
    await bot.add_cog(FunCommands(bot))
