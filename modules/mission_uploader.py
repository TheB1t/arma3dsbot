import subprocess

import discord
from discord.ext import commands

from app import App, AppModule
from utils import LogLevel, BotInternalException, PBOManipulator
from .priv_system import PrivSystem, PrivSystemLevels

class MissionUploader(AppModule):
    def __init__(self, app: App):
        super(MissionUploader, self).__init__(app)

        self._check_settings_exist("mission_path")
        self._check_settings_exist("mission_name")
        
        self.files = [
            ("", "mission.sqm"),
            ("", "cba_settings.sqf"),
        ]
        self.bot.setAttachmentExtHandler("sqm", self.update)
        self.bot.setAttachmentExtHandler("sqf", self.update)

    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG, False)
    async def update(self, ctx: commands.Context, attachment: discord.Attachment):
        mission_path = self.settings["mission_path"]
        mission_name = self.settings["mission_name"]
        mission_file = f"{mission_name}.pbo"

        pbo = PBOManipulator(mission_file, mission_path)
        pbo.clean()
        pbo.unpack()

        for file in self.files:
            basepath, name = file

            if (attachment.filename == name):
                self.log(f"Updating file {mission_path}/{basepath}/{name}")
                msg = await self.send(ctx, f"Detected {name}. Starting update...")
                out = subprocess.run(f"wget -O {mission_path}/{mission_name}/{basepath}/{name} {attachment.url}", check=True, text=True, capture_output=True, shell=True)
                self.log(out.stderr)
                await msg.edit(content=f"{name} update finished!")
                await msg.delete(delay=10)

        pbo.update()
        pbo.pack()
        pbo.clean()