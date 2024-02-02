import subprocess

import discord
from discord.ext import commands

from app import App, AppModule
from utils import LogLevel, BotInternalException, PBOManipulator
from .priv_system import PrivSystem, PrivSystemLevels

class MissionUploader(AppModule):
    def __init__(self, app: App):       
        super(MissionUploader, self).__init__(app,
        [
            "mission_path",
            "mission_name"
        ])
        
        self.files = [
            ("",                "mission",          "sqm"),
            ("",                "cba_settings",     "sqf"),
            ("scripts/chat",    "commands",         "sqf"),
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
            basepath, name, ext = file

            _tmp = attachment.filename.split(".")
            _ext = _tmp[-1]
            _name = ".".join(_tmp[:-1])
            
            if (ext == _ext):
                if (name == _name):
                    self.log(f"Updating file {mission_path}/{basepath}/{name}.{ext}")
                    msg = await self.send(ctx, f"Detected {name}.{ext}. Starting update...")
                    out = subprocess.run(f"wget -O {mission_path}/{mission_name}/{basepath}/{name}.{ext} {attachment.url}", check=True, text=True, capture_output=True, shell=True)
                    self.log(f"\n{out.stderr}")
                    
                    await self.edit(msg, f"{name} update finished!")

        pbo.update()
        pbo.pack()
        pbo.clean()