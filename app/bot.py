import json
import random

from typing import Union
from functools import wraps

import discord
from discord.ext import commands, tasks

from .server import Server

from utils import Log, LogLevel, Cache, BotInternalException, get_file_extension

from enum import Enum, auto

class PrettyType(Enum):
    SUCCESS     = auto()
    ERROR       = auto()
    WARNING     = auto()
    INFO        = auto()

class ServerStatus(Enum):
    ONLINE        = auto()
    OFFLINE       = auto()
    ERROR         = auto()
    REBOOTING     = auto()
    BOOTING       = auto()
    SHUTTING_DOWN = auto()
    MAINTENANCE   = auto()

class ServerTransition(Enum):
    START         = auto()
    END           = auto()
    PENDING       = auto()

class StatusBot(commands.Bot, Log):
    def __init__(self, command_prefix: str, srv: Server, settings):
        intents                         = discord.Intents.default()
        intents.guild_messages          = True
        intents.dm_messages             = True
        intents.members                 = True
        intents.message_content         = True
        
        super().__init__(command_prefix, intents=intents)

        self.__srv_transition           = ServerTransition.END
        self.__srv_status               = ServerStatus.OFFLINE
        self.__srv                      = srv
        self.__service_role_id          = settings["service_role_id"]
        self.__channel_id               = settings["channel_id"]
        self.__displayed_ip             = settings["displayed_ip"]
        self.__port                     = settings["base_port"]
        self.__attachment_handlers      = {}

        self.__channel                  = None
        self.__cache                    = Cache()
        
        if not self.__cache.load():
            self.__cache.status_message_id   = 0
            self.__cache.status              = self.__srv_status.value
        else:
            self.__srv_status = ServerStatus(self.__cache.status)
            
    def toggleMaintenanceMode(self):
        if (not self._checkStatus(ServerStatus.MAINTENANCE)):
            self.setStatus(ServerStatus.MAINTENANCE)
            return True
        
        self._setTransition(ServerTransition.PENDING)
        self.update_status.restart()
        return False

    def _checkTransition(self, trans : ServerTransition):
        return self.__srv_transition.value == trans.value
    
    def _setTransition(self, trans : ServerTransition):
        self.__srv_transition = trans

    def _checkStatus(self, status : ServerStatus):
        return self.__srv_status.value == status.value
    
    def _setStatus(self, status : ServerStatus):
        self._setTransition(ServerTransition.START)
        self.__srv_status       = status
        self.__cache.status     = status.value
    
    def _fsm(self):
        try:
            if not self._checkTransition(ServerTransition.START):
                if self._checkStatus(ServerStatus.MAINTENANCE) and not self._checkTransition(ServerTransition.PENDING) and not self._checkStatus(ServerStatus.OFFLINE):
                    pass
                elif self.__srv.ping():
                    self._setStatus(ServerStatus.ONLINE)
                elif self._checkStatus(ServerStatus.SHUTTING_DOWN):
                    self._setStatus(ServerStatus.OFFLINE)
                else:
                    self._setStatus(ServerStatus.ERROR)
            else:
                self._setTransition(ServerTransition.END)
                
        except Exception as e:
            self.log(str(e), LogLevel.WARN)
                
    def setStatus(self, status : ServerStatus):
        self._setStatus(status)
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

    async def send_pretty(self, entry: Union[discord.Message, discord.Interaction, commands.Context], type: PrettyType, title: str = None, message: str = None, fields: dict = None, view: discord.ui.View = None, delete_after=None, ephemeral=True):       
        color = discord.Color.light_gray()
        
        if type == PrettyType.SUCCESS:
            color = discord.Color.green()
        elif type == PrettyType.ERROR:
            color = discord.Color.red()
        elif type == PrettyType.WARNING:
            color = discord.Color.orange()
        elif type == PrettyType.INFO:
            color = discord.Color.blue()
        
        embed = discord.Embed(title=title, description=message, color=color, timestamp=discord.utils.utcnow())
        
        embed.set_footer(text=type.name)
        
        if fields:
            for key, value in fields.items():
                embed.add_field(name=key, value=value)
            
        try:
            if isinstance(entry, discord.Interaction):
                view = view if view else discord.interactions.MISSING
                return await entry.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
            else:
                ctx = entry if isinstance(entry, commands.Context) else await self.get_context(entry)
                if (ctx.prefix == '/' or isinstance(entry, discord.Interaction)):
                    return await ctx.send(embed=embed, view=view, ephemeral=ephemeral)
                
                return await ctx.send(embed=embed, view=view, delete_after=delete_after)
        
        except Exception as e:
            self.log(str(e), LogLevel.ERR)
            
    async def send(self, ctx: commands.Context, message: str, delete_after=None, ephemeral=True):
        try:
            if (ctx.prefix == '/'):
                return await ctx.send(message, ephemeral=ephemeral)
            
            return await ctx.send(message, delete_after=delete_after)
        except Exception as e:
            self.log(str(e), LogLevel.ERR)


    async def edit(self, msg: discord.Message, message: str, delete_after=None):
        try:
            await msg.edit(content=message)
            
            if delete_after and not msg.flags.ephemeral:
                await msg.delete(delay=delete_after)
        except Exception as e:
            self.log(str(e), LogLevel.ERR)
    
    # [BOT] Events
    async def on_ready(self):
        self.log(f"[AUTH] ({self.user.id}) <{self.user.name}> logged in")

        try:
            self.__channel = self.get_channel(self.__channel_id)
        except:
            self.log(f"Can't find channel with ID {self.__channel_id}", LogLevel.FATAL)
            exit(1)

        self.update_status.start()

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
                # await self.deleteSourceMessage(ctx)
    
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

    # [BOT] Embed generator        
    def generateEmbed(self):
        serverInfo, serverPlayers = self.__srv.get()
            
        statuses = {
            ServerStatus.MAINTENANCE.name : {
                "title": "Техническое обслуживание",
                "color": discord.Color.dark_blue(),
                "fields": self.getGenericFields("On Maintenance")
            },
            ServerStatus.ONLINE.name : {
                "title": serverInfo["name"],
                "color": discord.Color.green(),
                "fields": self.getOnlineFields(serverInfo, serverPlayers)
            },
            ServerStatus.OFFLINE.name : {
                "title": "Сервер выключен",
                "color": discord.Color.dark_red(),
                "fields": self.getGenericFields("Offline")
            },
            ServerStatus.ERROR.name : {
                "title": "Требуется обслуживание",
                "color": discord.Color.red(),
                "fields": self.getErrorFields()
            },
            ServerStatus.REBOOTING.name : {
                "title": "Сервер перезагружается",
                "color": discord.Color.yellow(),
                "fields": self.getGenericFields("Rebooting")
            },
            ServerStatus.BOOTING.name : {
                "title": "Сервер загружается",
                "color": discord.Color.dark_green(),
                "fields": self.getGenericFields("Booting")
            },
            ServerStatus.SHUTTING_DOWN.name : {
                "title": "Сервер выключается",
                "color": discord.Color.dark_green(),
                "fields": self.getGenericFields("Shutting down")
            }
        }

        status = statuses[self.__srv_status.name] if self.__srv_status.name in statuses else {
                "title": "!!!UNKNOWN!!!",
                "color": discord.Color.pink(),
                "fields": self.getGenericFields("Fatal error")
            }

        if (len(serverPlayers) > 0):
            if (len(serverPlayers) > 100):
                players = "Невозможно отобразить всех игроков"
            else:
                players = '\n'.join([f"* {item['name']} ({int(item['duration'] // 3600):02d}:{int((item['duration'] % 3600) // 60):02d})" for item in serverPlayers])
        else:
            players = "Сервер пуст"
        
        description = f"```py\n{players}\n```" if self._checkStatus(ServerStatus.ONLINE) else None
        
        embed = discord.Embed(timestamp = discord.utils.utcnow(), title=status["title"], color=status["color"], description=description)
        
        for field in status["fields"]:
            embed.add_field(**field)
            
        return embed


    def getOnlineFields(self, serverInfo: dict, serverPlayers: list):
        return self.getGenericFields("Online") + [
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
        ]

    def getErrorFields(self):
        fields = self.getGenericFields("Error")
        
        if (self.__service_role_id):
            fields.append({
                "name": "Оповещение",
                "value": f"<@&{self.__service_role_id}>, требуется обслуживание!",
                "inline": False
            })

        return fields

    def getGenericFields(self, status):
        return [
            {
                "name": "Статус",
                "value": status,
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
        self._fsm()
        
        embed = self.generateEmbed()
            
        try:
            if (self.__cache.status_message_id == 0):
                raise RuntimeError("status_message_id == 0, send new")
                
            message = await self.__channel.fetch_message(self.__cache.status_message_id)
            if (message):
                await message.edit(embed=embed)
            else:
                raise RuntimeError("failed to fetch message, send new")
                
        except Exception as e:
            self.log(str(e), LogLevel.WARN)
            
            message = await self.__channel.send(embed=embed)
            self.__cache.status_message_id = message.id

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()