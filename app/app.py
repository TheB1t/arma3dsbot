import json

import discord
from discord.ext import commands

from utils import Log, LogLevel
from .bot import StatusBot
from .server import Server
from db import Database

class AppModule(Log):
    def __init__(self, app):
        super(AppModule, self).__init__()
        self.app = app

    async def send(self, ctx: commands.Context, message: str, delay=20, ephemeral=True):
        return await self.bot.send(ctx, message, delay, ephemeral)

    async def edit(self, msg: discord.Message, message: str, delay=10):
        return await self.bot.edit(msg, message, delay)
    
    @property
    def bot(self):
        return self.app.bot

    @property
    def db(self):
        return self.app.db

    @property
    def settings(self):
        return self.app.settings
    
    def _check_settings_exist(self, p):
        return self.app._check_settings_exist(p)
    
class App(Log):
    def __init__(self):
        try:
            with open("settings.json", 'r') as file:
                self.settings = json.load(file)

                self._check_settings_exist("ip")
                self._check_settings_exist("displayed_ip")
                self._check_settings_exist("base_port")

                self._check_settings_exist("db_ip")
                self._check_settings_exist("db_port")
                self._check_settings_exist("db_user")
                self._check_settings_exist("db_pass")
                self._check_settings_exist("db_db")

                self._check_settings_exist("service_role_id")
                self._check_settings_exist("channel_id")

                self._check_settings_exist("token")

        except FileNotFoundError:
            self.log("Can't find settings.json", LogLevel.FATAL)
            exit(1)
        except RuntimeError as e:
            self.log(str(e), LogLevel.FATAL)
            exit(1)

        self.db = Database(self.settings["db_ip"],
                           self.settings["db_port"], 
                           self.settings["db_user"], 
                           self.settings["db_pass"], 
                           self.settings["db_db"])
        self.srv = Server(self.settings["ip"], 
                          self.settings["base_port"])

        self.bot = StatusBot('!', self.srv, self.settings)
        self.bot.add_listener(self.on_ready)
        self.modules = {}

    def _check_settings_exist(self, p):
        if not (p in self.settings):
            raise RuntimeError(f"Missing setting {p} in settings.json")
    
    def addModule(self, c, name):
        try:
            self.log(f"Adding module {name} to app")
            inst = c(self)
            self.modules[name] = inst
        except RuntimeError as e:
            self.log(str(e), LogLevel.FATAL)
            exit(1)

    async def on_ready(self):
        for name, inst in self.modules.items():
            if isinstance(inst, commands.Cog):
                self.log(f"Adding Cog {name} to bot")
                await self.bot.add_cog(inst)

    def run(self):
        self.bot.run(self.settings["token"])