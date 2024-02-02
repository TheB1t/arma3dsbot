import subprocess
import asyncio
import os

from discord.ext import commands

from app import AppModule, ServerStatus
from utils import LogLevel, BotInternalException
from .priv_system import PrivSystem, PrivSystemLevels

class ServerManager(commands.Cog, AppModule):
    def __init__(self, app):        
        super(ServerManager, self).__init__(app,                           
        [
            "restart_cmd",
            "stop_cmd",
            "start_cmd"
        ])
        
        self.scripts = {
            "reboot":   self.settings["restart_cmd"],
            "stop":     self.settings["stop_cmd"],
            "start":    self.settings["start_cmd"]
        }

    async def _generic(self, ctx: commands.Context, action: str, status: ServerStatus):
        msg = await self.send(ctx, f"Initiating a {action}")
        
        try:
            self.bot.setStatus(status)
            process = await asyncio.create_subprocess_exec("bash", "handle.sh", *self.scripts[action].split(" "), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            exitcode = await process.wait()
            
            self.log(f"Done {action} with exitcode {exitcode}")
        except subprocess.CalledProcessError as e:
            self.log(str(e), LogLevel.WARN)
            await msg.delete()
            raise BotInternalException(f"Error when trying to {action}, you need to do {action} manually!")

    @commands.hybrid_group(name="server")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def server(self, ctx: commands.Context):
        pass
               
    @server.command(name="restart")
    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG)
    async def restart(self, ctx: commands.Context):
        await self._generic(ctx, "reboot", ServerStatus.REBOOTING)

    @server.command(name="stop")
    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG)
    async def stop(self, ctx: commands.Context):
        await self._generic(ctx, "stop", ServerStatus.SHUTTING_DOWN)
        
    @server.command(name="start")
    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG)
    async def start(self, ctx: commands.Context):
        await self._generic(ctx, "start", ServerStatus.BOOTING)
        
    @server.command(name="maintenance_mode")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def maintenance_toggle(self, ctx: commands.Context):
        mode = self.bot.toggleMaintenanceMode()
        await self.send(ctx, f"Maintenance mode {'enabled' if mode else 'disabled'}")