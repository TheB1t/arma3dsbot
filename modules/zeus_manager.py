import discord
from discord.ext import commands

from app import App, AppModule
from utils import LogLevel, BotInternalException, sessioned
from .priv_system import PrivSystem, PrivSystemLevels
from db import ZeusUser

class ZeusManager(commands.Cog, AppModule):
    def __init__(self, app: App):
        super(ZeusManager, self).__init__(app)

    def getZeusUserBySteamID(self, session, steamid):
        return session.query(ZeusUser).filter_by(steamid=steamid).first()
    
    @sessioned
    def getAllZeusUsers(self, session):
        return session.query(ZeusUser).all()
    
    @sessioned
    def addZeusUser(self, session, nickname, steamid):
        user = self.getZeusUserBySteamID(session, steamid)

        if not user:
            user = ZeusUser(nickname=nickname, steamid=steamid)
            session.add(user)
            session.commit()

            return (user.nickname, user.steamid, user.is_zeus)
        return None

    @sessioned
    def delZeusUser(self, session, steamid):
        user = self.getZeusUserBySteamID(session, steamid)

        if user:
            session.delete(user)
            session.commit()

            return (user.nickname, user.steamid, user.is_zeus)
        return None

    @sessioned
    def toggleZeusUser(self, session, steamid):
        user = self.getZeusUserBySteamID(session, steamid)

        if user:
            user.is_zeus = 0 if user.is_zeus else 1
            session.commit()

            return (user.nickname, user.steamid, user.is_zeus)
        return None
    
    @commands.hybrid_group(fallback="list")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def zeus(self, ctx: commands.Context):
        users = self.getAllZeusUsers()

        users_str = '\n'.join(f"[{user.steamid}] {user.nickname:20}: {'ZEUS' if user.is_zeus else 'NOT ZEUS'}" for user in users)
        await self.send(ctx, f"List of Zeus users ```{users_str}```")


    @zeus.command(name="add")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def zeus_add(self, ctx: commands.Context, nickname: str, steamid: str):
        user = self.addZeusUser(nickname, steamid)
        if user:
            nickname, steamid, is_zeus = user
            await self.send(ctx, f"Added new Zeus user [{steamid}] {nickname}")
        else:
            await self.send(ctx, f"Failed to add Zeus user user with steamid {steamid}, entry already exists")

    @zeus.command(name="del")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def zeus_del(self, ctx: commands.Context, steamid: str):
        user = self.delZeusUser(steamid)
        if user:
            nickname, steamid, is_zeus = user
            await self.send(ctx, f"Removed Zeus user [{steamid}] {nickname}")
        else:
            await self.send(ctx, f"Failed to delete Zeus user with steamid {steamid}, entry not found")

    @zeus.command(name="toggle")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def zeus_toggle(self, ctx: commands.Context, steamid: str):
        user = self.toggleZeusUser(steamid)
        if user:
            nickname, steamid, is_zeus = user
            await self.send(ctx, f"[{steamid}] {nickname} toggled to {'ZEUS' if is_zeus else 'NOT ZEUS'}")
        else:
            await self.send(ctx, f"Failed to toggle Zeus user user with steamid {steamid}, entry not found")