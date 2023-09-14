import json
import asyncio
from datetime import datetime

import discord
from discord.ext import commands, tasks

from server import Server

class StatusBot(commands.Bot):
    def __init__(self, command_prefix, srv, settings):
        intents = discord.Intents.default()
        intents.guild_messages = True
        intents.dm_messages = True
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix, intents=intents)

        self.__srv_restarting = False
        self.__srv = srv
        self.__service_role_id = settings["service_role_id"]
        self.__channel_id = settings["channel_id"]
        self.__displayed_ip = settings["displayed_ip"]
        self.__port = settings["base_port"]

        self.__channel = None
        self.__readCache()

    def __readCache(self):
        try:
            with open("cache.json", 'r') as file:
                self.__cache = json.load(file)
        except FileNotFoundError:
            self.__cache = {
                "status_message_id": 0
            }

            self.__saveCache()  

    def __saveCache(self):
        with open("cache.json", 'w') as file:
            json.dump(self.__cache, file, indent=4)

    async def setRebootState(self):
        self.__srv_restarting = True

        next_iteration_time = self.update_status.next_iteration
        if next_iteration_time:
            time_to_wait = discord.utils.compute_timedelta(next_iteration_time)
            print(f"Waiting {time_to_wait} seconds")
            await asyncio.sleep(time_to_wait)


    # [BOT] Events
    async def on_ready(self):
        print("{0}<{1}> logged in".format(self.user.name, self.user.id))

        try:
            self.__channel = self.get_channel(self.__channel_id)
        except:
            print("Can't find channel with ID {0}".format(self.__channel_id))
            exit(1)

        self.update_status.start()

    async def on_message(self, message: discord.Message):
        # print("{0}:{1}".format(message.id, message.content))
        await self.process_commands(message)

    # [BOT] Field former        
    def formEmbed(self, former):
        title = "Unknown"
        color = discord.Color.pink()
        fields = []

        if (former == "online"):
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


    def getOnlineFields(self, serverInfo, serverPlayers):
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

    # [BOT] Status update
    @tasks.loop(seconds=30)
    async def update_status(self):
        async with self.__channel.typing():
            embed = None

            if (self.__srv.ping()):
                if (self.__srv_restarting):
                    self.__srv_restarting = False

                embed = self.formEmbed("online")
            else:
                if (self.__srv_restarting):
                    embed = self.formEmbed("rebooting")
                else:
                    embed = self.formEmbed("offline")

            try:
                if (self.__cache["status_message_id"] == 0):
                    raise RuntimeError("status_message_id == 0, send new")
                
                message = await self.__channel.fetch_message(self.__cache["status_message_id"])
                await message.edit(embed=embed)
            except:
                message = await self.__channel.send(embed=embed)
                self.__cache["status_message_id"] = message.id
                self.__saveCache()

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()