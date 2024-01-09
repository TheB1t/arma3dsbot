import subprocess

from discord.ext import commands

from app import AppModule
from utils import LogLevel, BotInternalException
from .priv_system import PrivSystem, PrivSystemLevels

class ServerRestarter(commands.Cog, AppModule):
    def __init__(self, app):
        super(ServerRestarter, self).__init__(app)

    @commands.hybrid_group(name="server", fallback="restart")
    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG)
    async def restart(self, ctx: commands.Context):
        msg = await self.send(ctx, "Initiating a reboot")
        try:
            self.bot.setRebootState()
            out = subprocess.run("bash restart.sh", check=True, text=True, capture_output=True, shell=True)
            self.log(f"\n{out}")
        except subprocess.CalledProcessError as e:
            self.log(e, LogLevel.WARN)
            await msg.delete()
            raise BotInternalException("Error when trying to reboot, you need to do restart manually!")