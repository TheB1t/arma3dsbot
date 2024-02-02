from typing import Union
from enum import Enum

import discord
from discord import User, Member, Role
from discord.ext import commands

from app import App, AppModule, PrettyType
from utils import LogLevel, BotInternalException
from .priv_system import PrivSystem, PrivSystemLevels
from db import Player

class Permissions(Enum):
    ZEUS            = 0b1 << 0
    NOT_IVENTOLOG   = 0b1 << 1
    CAN_THROW_OUT   = 0b1 << 2
        
class PermissionsHolder:
    def __init__(self, permissions: int = 0):
        self.permissions = permissions

    def has_permission(self, permission: Permissions) -> bool:
        return (self.permissions & permission.value) > 0

    def add_permission(self, permission: Permissions):
        self.permissions |= permission.value

    def remove_permission(self, permission: Permissions):
        self.permissions &= ~permission.value

    def get_raw_permissions(self):
        return self.permissions
    
    def add_from_array(self, permissions: list[Permissions]):
        for perm in permissions:
            self.add_permission(perm)

    def add_from_array(self, permissions: list[int]):
        for perm in permissions:
            self.add_permission(Permissions(perm))

    def add_from_array(self, permissions: list[str]):
        for perm in permissions:
            self.add_permission(Permissions[perm])
            
    def __str__(self) -> str:
        result = []
        for permission in Permissions:
            if self.has_permission(permission):
                result.append(permission.name)
        return ', '.join(result) if len(result) else "NONE"

class PermissionsView(discord.ui.View):
    def __init__(self, module: AppModule, mention: Union[Member, User], perms: PermissionsHolder):
        super().__init__()
        self.module = module
        self.mention = mention
        
        self.select_callback.placeholder = "Choose permissions"
        self.select_callback.min_values = 0
        self.select_callback.max_values = len(Permissions)
        for perm in list(Permissions):
            self.select_callback.add_option(label=perm.name, default=perms.has_permission(perm))

    @discord.ui.select(cls=discord.ui.Select)
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        newperms = PermissionsHolder()
        newperms.add_from_array(select.values)
        
        with self.module.db.session as session:
            player = session.query(Player).filter_by(discordid=self.mention.id).first()
            player.permissions = newperms.get_raw_permissions()
            session.commit()
        
        await self.module.send_pretty(interaction, PrettyType.SUCCESS, 
        title = "Permissions changed",
        fields = {
            "Name": self.mention.mention,
            "Permissions": str(newperms)
        })

class PlayerManager(commands.Cog, AppModule):
    def __init__(self, app: App):
        super(PlayerManager, self).__init__(app)
    
    def addPlayer(self, session, mention: Union[Member, User], steamid):
        user = session.query(Player).filter_by(discordid=mention.id).first()

        if not user:
            user = Player(discordid=mention.id, nickname=mention.name, steamid=steamid)
            session.add(user)
            session.commit()

            return (True, user)
        return (False, user)

    def delPlayer(self, session, mention: Union[Member, User]):
        user = session.query(Player).filter_by(discordid=mention.id).first()

        if user:
            session.delete(user)
            session.commit()

            return (True, user)
        return (False, None)

    @commands.hybrid_group()
    async def player(self, ctx: commands.Context):
        pass

    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.ADMIN)
    async def get(self, ctx: commands.Context, mention: Union[Member, User]):
        with self.db.session as session:
            player = session.query(Player).filter_by(discordid=mention.id).first()
            
            if player:
                permissions = PermissionsHolder(player.permissions)
                
                await self.send_pretty(ctx, PrettyType.INFO, 
                title = "Info about player",
                fields = {
                    "Name": mention.mention,
                    "SteamID": player.steamid,
                    "Permissions": str(permissions)
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR,
                title = "Failed to find player",
                fields = {
                    "Name": mention.mention,
                    "Cause": "Does not exist"
                })

    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.ADMIN)
    async def bind_manual(self, ctx: commands.Context, mention: Union[Member, User], steamid: str):
        with self.db.session as session:
            is_added, player = self.addPlayer(session, mention, steamid)
            
            if is_added:
                await self.send_pretty(ctx, PrettyType.SUCCESS, 
                title = "Successfully binded",
                fields = {
                    "Name": mention.mention,
                    "SteamID": player.steamid
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR, 
                title = "Failed to bind",
                fields = {
                    "Name": mention.mention,
                    "SteamID": steamid,
                    "Cause": f"Already binded to {player.steamid}"
                })

    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.ADMIN)
    async def unbind_manual(self, ctx: commands.Context, mention: Union[Member, User]):
        with self.db.session as session:
            is_deleted, player = self.delPlayer(session, mention)
            
            if is_deleted:
                await self.send_pretty(ctx, PrettyType.SUCCESS, 
                title = "Successfully unbinded", 
                fields = {
                    "Name": mention.mention,
                    "SteamID": player.steamid
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR, 
                title = "Failed to unbind",
                fields = {
                    "Name": ctx.author.mention,
                    "Cause": "Not binded yet"
                })
                       
    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.USER)
    async def me(self, ctx: commands.Context):
        with self.db.session as session:
            player = session.query(Player).filter_by(discordid=ctx.author.id).first()

            if player:
                permissions = PermissionsHolder(player.permissions)

                await self.send_pretty(ctx, PrettyType.INFO, 
                title = "Info about you",
                fields = {
                    "Name": ctx.author.mention,
                    "SteamID": player.steamid,
                    "Permissions": str(permissions)
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR,
                title = "Failed to find your account",
                fields = {
                    "Name": ctx.author.mention,
                    "Cause": "Does not exist"
                })
            
    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.USER)
    async def bind(self, ctx: commands.Context, steamid: str):
        with self.db.session as session:
            is_added, player = self.addPlayer(session, ctx.author, steamid)
            
            if is_added:
                await self.send_pretty(ctx, PrettyType.SUCCESS, 
                title = "Successfully binded",
                fields = {
                    "Name": ctx.author.mention,
                    "SteamID": player.steamid
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR, 
                title = "Failed to bind",
                fields = {
                    "Name": ctx.author.mention,
                    "SteamID": steamid,
                    "Cause": f"Already binded to {player.steamid}"
                })

    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.USER)
    async def unbind(self, ctx: commands.Context):
        with self.db.session as session:
            is_deleted, player = self.delPlayer(session, ctx.author)
            
            if is_deleted:
                await self.send_pretty(ctx, PrettyType.SUCCESS, 
                title = "Successfully unbinded", 
                fields = {
                    "Name": ctx.author.mention,
                    "SteamID": player.steamid
                })
            else:
                await self.send_pretty(ctx, PrettyType.ERROR, 
                title = "Failed to unbind",
                fields = {
                    "Name": ctx.author.mention,
                    "Cause": "Not binded yet"
                })

    @player.command()
    @PrivSystem.withPriv(PrivSystemLevels.ADMIN)
    async def set_permissions(self, ctx: commands.Context, mention: Union[Member, User]):
        with self.db.session as session:
            player = session.query(Player).filter_by(discordid=mention.id).first()
            
            if player:
                permissions = PermissionsHolder(player.permissions)
                
                await self.send_pretty(ctx, PrettyType.INFO, 
                title = "Changing permissions",
                fields = {
                    "Name": mention.mention,
                    "SteamID": player.steamid
                }, view=PermissionsView(self, mention, permissions))
            else:
                await self.send_pretty(ctx, PrettyType.ERROR,
                title = "Failed to find player",
                fields = {
                    "Name": mention.mention,
                    "Cause": "Does not exist"
                })

    # @player.command()
    # @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    # async def sync(self, ctx: commands.Context):
    #     with self.db.session as session:
    #         players = session.query(Player).all()
            
    #         done = []
    #         for player in players:
    #             user = discord.utils.get(self.bot.users, name=player.nickname)
                
    #             if user:
    #                 done.append((user.name, user.id))
    #                 player.discordid = user.id
    #                 session.commit()
                    
    #         await self.send_pretty(ctx, PrettyType.INFO,
    #                                title = "Synched",
    #                                message = "\n".join([f"{name} ({id})" for name, id in done]))
                                    