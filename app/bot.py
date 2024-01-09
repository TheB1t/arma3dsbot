import json
import random

from functools import wraps

import discord
from discord.ext import commands, tasks

from .server import Server

from utils import Log, LogLevel, BotInternalException, get_file_extension

star_wars_statuses = [
    "May the Force be with you.",
    "In a galaxy far, far away...",
    "The dark side calls to me.",
    "Join the Rebel Alliance today!",
    "I've got a bad feeling about this.",
    "Chewie, we're home.",
    "Bounty hunting is a complicated profession.",
    "The Jedi Order is no more.",
    "Help me, Obi-Wan Kenobi, you're my only hope.",
    "The Sith are always two, a master and an apprentice.",
    "The Force is strong with this one.",
    "Do or do not, there is no try.",
    "The Death Star plans are in the data tapes.",
    "I am your father.",
    "The Millennium Falcon made the Kessel Run in less than twelve parsecs.",
    "I find your lack of faith disturbing.",
    "I've got a thermal detonator!",
    "The Senate will decide your fate.",
    "The Clone Wars have begun.",
    "It's a trap!",
    "I'm one with the Force, the Force is with me.",
    "There's always a bigger fish.",
    "We serve the First Order.",
    "The resistance will not stand.",
    "Never tell me the odds.",
    "I've got a ship, but no crew.",
    "An elegant weapon for a more civilized age.",
    "I don't like sand. It's coarse and rough and irritating.",
    "I am a Jedi, like my father before me.",
    "These aren't the droids you're looking for.",
    "It's the ship that made the Kessel Run in less than twelve parsecs.",
    "The dark side of the Force is a pathway to many abilities some consider to be unnatural.",
    "I sense a disturbance in the Force.",
    "The Force will be with you, always.",
    "There is no emotion, there is peace.",
    "The galaxy is in turmoil.",
    "I'm just a simple man trying to make my way in the universe.",
    "The Force awakens.",
    "The Jedi are extinct. Their fire has gone out of the universe.",
    "I've got a ship, and I know how to use it.",
    "You were the chosen one!",
    "The Force flows through all living things.",
    "I've got a bad feeling about this mission.",
    "Aren't you a little short for a stormtrooper?",
    "Let the past die. Kill it if you have to.",
    "It's not wise to upset a Wookiee.",
    "I've got a very bad feeling about this.",
    "It's treason, then.",
    "The Force is what gives a Jedi his power.",
    "I'm not a hero. I'm a high-functioning droid.",
    "There is another...",
]

class StatusBot(commands.Bot, Log):
    def __init__(self, command_prefix: str, srv: Server, settings):
        intents = discord.Intents.default()
        intents.guild_messages = True
        intents.dm_messages = True
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix, intents=intents)

        self.__srv_restarting_stage = 0
        self.__srv = srv
        self.__service_role_id = settings["service_role_id"]
        self.__channel_id = settings["channel_id"]
        self.__displayed_ip = settings["displayed_ip"]
        self.__port = settings["base_port"]
        self.__attachment_handlers = {}

        self.__channel = None
        self.__cache = {}
        self.__cacheLoad()

    def __cacheLoad(self):
        try:
            with open("cache.json", 'r') as file:
                self.__cache = json.load(file)
        except FileNotFoundError:
            self.__cacheSet("status_message_id", 0)
            self.__cacheSet("maintenance_mode", False)
            self.__cacheSave()  

    def __cacheSave(self):
        with open("cache.json", 'w') as file:
            json.dump(self.__cache, file, indent=4)

    def __cacheGet(self, field):
        if field in self.__cache:
            return self.__cache[field]
        
        return None
    
    def __cacheSet(self, field, value):
        self.__cache[field] = value

    def toggleMaintenanceMode(self):
        oldmode = self.__cacheGet("maintenance_mode")
        mode = not oldmode if oldmode else True
        self.__cacheSet("maintenance_mode", mode)
        self.__cacheSave()
        self.update_status.restart()
        return mode

    def setRebootState(self):
        self.__srv_restarting_stage = 2
        self.update_status.restart()

    def setAttachmentExtHandler(self, ext: str, func):
        self.log(f"Register file extension handler: {ext} -> {func.__qualname__ }")
        self.__attachment_handlers[ext] = func

    def getMessageString(self, ctx: commands.Context):
        message = ctx.message
        _server = message.guild.name if message.guild else 'DM'
        _ch = 'DM' if _server == 'DM' else message.channel
        _msg = message.content if message.content else 'empty'
        _att = [f"{a.filename} # {a.size}" for a in message.attachments]
        return f"[{_server}][{_ch}] <{message.author}> -> {_msg} ({_att})"

    async def send(self, ctx: commands.Context, message: str, delete_after=None, ephemeral=True):
        if (ctx.prefix == '/'):
            return await ctx.send(message, ephemeral=ephemeral)
        
        return await ctx.send(message, delete_after=delete_after)


    async def edit(self, msg: discord.Message, message: str, delete_after=None):
        await msg.edit(content=message)
        
        if delete_after and not msg.flags.ephemeral:
            await msg.delete(delay=delete_after)
    
    # [BOT] Events
    async def on_ready(self):
        self.log(f"[AUTH] ({self.user.id}) <{self.user.name}> logged in")

        try:
            self.__channel = self.get_channel(self.__channel_id)
        except:
            self.log(f"Can't find channel with ID {self.__channel_id}", LogLevel.FATAL)
            exit(1)

        await self.change_presence(activity=discord.Game(name=random.choice(star_wars_statuses)))

        self.update_status.start()
        self.update_activity.start()

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound) or isinstance(error, commands.MissingRequiredArgument):
            await self.send(ctx, str(error))
            return
        
        if isinstance(error, commands.HybridCommandError):
            error = error.original

        if isinstance(error, commands.CommandInvokeError) or isinstance(error, discord.app_commands.errors.CommandInvokeError):
            error = error.original

            if isinstance(error, BotInternalException):
                self.log(str(error), LogLevel.WARN)
                await self.send(ctx, str(error))
                return
            
        raise error

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        ctx = await self.get_context(message)        
        for attachment in message.attachments:
            ext = get_file_extension(attachment.filename)
            if ext in self.__attachment_handlers:
                await self.deleteSourceMessage(ctx)
    
                func = self.__attachment_handlers[ext]
                await func(ctx, attachment)

        if not len(message.content):
            return
        
        if ctx.prefix != self.command_prefix:
            return
        
        _msg = self.getMessageString(ctx)
        self.log(_msg)
            
        await self.deleteSourceMessage(ctx)
        await self.process_commands(message)

    async def deleteSourceMessage(self, ctx: commands.Context):
        try:
            if not isinstance(ctx.message.channel, discord.DMChannel):
                _msg = self.getMessageString(ctx)
                self.log(f"Deleting message {_msg}")
                await ctx.message.delete()
        except:
            pass

    # [BOT] Field former        
    def formEmbed(self, former: str):
        title = "Unknown"
        color = discord.Color.pink()
        fields = []

        maintenance_mode = self.__cacheGet("maintenance_mode")

        if (maintenance_mode):
            title = "Техническое обслуживание"
            color = discord.Color.dark_blue()
            fields = self.getMaintenanceFields()

        elif (former == "online"):
            serverInfo = self.__srv.getInfo()

            serverPlayers = []
            if (serverInfo["players"]):
                serverPlayers = self.__srv.getPlayers()

            title = serverInfo["name"]
            color = discord.Color.green()
            fields = self.getOnlineFields(serverInfo, serverPlayers)

        elif (former == "offline"):
            title = "Требуется обслуживание"
            color = discord.Color.red()
            fields = self.getOfflineFields()

        elif (former == "rebooting"):
            title = "Сервер перезагружается"
            color = discord.Color.yellow()
            fields = self.getRebootingFields()

        else:
            raise RuntimeError(f"Unknown former {former}")
        
        embed = discord.Embed(title=title, timestamp = discord.utils.utcnow(), color=color)
        for field in fields:
            embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])

        return embed


    def getOnlineFields(self, serverInfo: dict, serverPlayers: list):
        if (len(serverPlayers) > 0):
            players = '\n'.join([f"* {item['name']} ({int(item['duration'] // 3600):02d}:{int((item['duration'] % 3600) // 60):02d})" for item in serverPlayers])
        else:
            players = "Сервер пуст"

        return [
            {
                "name": "Статус",
                "value": "Online",
                "inline": True
            },
            {
                "name": "Адрес сервера",
                "value": f"{self.__displayed_ip}:{serverInfo['port']}",
                "inline": True
            },
            {
                "name": "Карта",
                "value": f"{serverInfo['map']}",
                "inline": True
            },
            {
                "name": "Миссия",
                "value": f"{serverInfo['game']}",
                "inline": True
            },
            {
                "name": "Количество игроков",
                "value": f"{serverInfo['players']}/{serverInfo['max_players']}",
                "inline": True
            },
            {
                "name": "Список игроков",
                "value": f"```py\n{players}\n```",
                "inline": False
            },
        ]

    def getOfflineFields(self):
        fields = [
            {
                "name": "Статус",
                "value": "Offline",
                "inline": True
            },
            {
                "name": "Адрес сервера",
                "value": f"{self.__displayed_ip}:{self.__port}",
                "inline": True
            }
        ]

        if (self.__service_role_id):
            fields.append({
                "name": "Оповещение",
                "value": f"<@&{self.__service_role_id}>, требуется обслуживание!",
                "inline": False
            })

        return fields
    
    def getRebootingFields(self):
        return [
            {
                "name": "Статус",
                "value": "Rebooting",
                "inline": True
            },
            {
                "name": "Адрес сервера",
                "value": f"{self.__displayed_ip}:{self.__port}",
                "inline": True
            }
        ]
    
    def getMaintenanceFields(self):
        return [
            {
                "name": "Статус",
                "value": "On Maintenance",
                "inline": True
            },
            {
                "name": "Адрес сервера",
                "value": f"{self.__displayed_ip}:{self.__port}",
                "inline": True
            }
        ]

    # [BOT] Status update
    @tasks.loop(seconds=30)
    async def update_status(self):
        status_message_id = self.__cacheGet("status_message_id")

        async with self.__channel.typing():
            embed = None

            if (self.__srv_restarting_stage >= 2):
                self.__srv_restarting_stage = 1
                embed = self.formEmbed("rebooting")
            else:
                if (self.__srv.ping()):
                    if (self.__srv_restarting_stage > 0):
                        self.__srv_restarting_stage = 0
                    embed = self.formEmbed("online")
                elif (self.__srv_restarting_stage == 0):
                    embed = self.formEmbed("offline")
                else:
                    embed = self.formEmbed("rebooting")

            try:
                if (status_message_id == 0):
                    raise RuntimeError("status_message_id == 0, send new")
                
                message = await self.__channel.fetch_message(status_message_id)
                if (message):
                    await message.edit(embed=embed)
                else:
                    raise RuntimeError("failed to fetch message, send new")
            except Exception as e:
                message = await self.__channel.send(embed=embed)
                self.__cacheSet("status_message_id", message.id)
                self.__cacheSave()

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def update_activity(self):
        await self.change_presence(activity=discord.Game(name=random.choice(star_wars_statuses)))

    @update_activity.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()