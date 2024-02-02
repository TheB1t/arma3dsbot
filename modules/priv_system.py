import re

from typing import Union
from enum import Enum
from functools import wraps

import discord
from discord import User, Member, Role
from discord.ext import commands
from discord.utils import get

from app import AppModule, PrettyType
from utils import LogLevel, BotInternalException
from db import BotUser

class PrivSystemLevels(Enum):
    OWNER       = 0
    ADMIN       = 1
    MODERATOR   = 2
    IVENTOLOG   = 100
    USER        = 256

class PrivView(discord.ui.View):
    def __init__(self, module: AppModule, mention: Union[User, Member, Role]):
        super().__init__()
        self.module = module
        
        self.uid = str(mention.id)
        self.is_role = isinstance(mention, Role)
        
        self.select_callback.placeholder = "Choose permissions"
        self.select_callback.min_values = 1
        self.select_callback.max_values = 1
        
        default = module.getPriv(mention)
        for perm in list(PrivSystemLevels):
            self.select_callback.add_option(label=perm.name, default=(perm == default))

    @discord.ui.select(cls=discord.ui.Select)
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        perm = PrivSystemLevels[select.values[0]]
        
        with self.module.db.session as session:
            user = session.query(BotUser).filter_by(uid=self.uid, is_role=self.is_role).first()
            user.priv_level = perm.value
            session.commit()
                    
            guild = interaction.guild
            uid = int(user.uid)
            fields = {}
            
            if guild:
                if user.is_role:
                    role = guild.get_role(uid)
                    if role:
                        fields["Name"] = role.mention
                else:
                    _user = guild.get_member(uid)
                    if _user:
                        fields["Name"] = _user.mention
            
            fields["Level"] = perm.name
            await self.module.send_pretty(interaction, PrettyType.SUCCESS, title="Permissions changed", fields=fields)
        
class PrivSystem(commands.Cog, AppModule):

    def __init__(self, app):
        super(PrivSystem, self).__init__(app)
        self.priv_levels = list(PrivSystemLevels)

    def getUsers(self, session):
        return session.query(BotUser).all()
    
    def admined(func):
        def wrapper(self, obj, *args, **kwargs):
            with self.db.session as session:
                is_role = isinstance(obj, Role)
                uid = str(obj.id)

                user = session.query(BotUser).filter_by(uid=uid, is_role=is_role).first()
                
                add_role = False
                if "add_role" in kwargs:
                    add_role = kwargs["add_role"]
                    del kwargs["add_role"]
                
                if not user:
                    if is_role and not add_role:
                        raise BotInternalException(f"Failed to find role {uid}")
                    
                    user = BotUser(uid=uid, is_role=is_role, priv_level=PrivSystemLevels.USER.value)
                    session.add(user)
                    session.commit()

                return func(self, session, uid, user, *args, **kwargs)
        return wrapper

    @admined
    def _checkPriv(self, session, uid, user, priv_level : PrivSystemLevels):
        return PrivSystemLevels(user.priv_level).value <= priv_level.value

    def checkPriv(self, user, priv_level : PrivSystemLevels):
        if self._checkPriv(user, priv_level):
            self.log(f"Access granted to {user.display_name} ({user.id})")
            return True
        
        if isinstance(user, Member):
            for role in user.roles:
                try:
                    if self._checkPriv(role, priv_level):
                        self.log(f"Access granted to {user.display_name} ({user.id}) by role {role.name} ({role.id})")
                        return True
                except:
                    pass

        self.log(f"Access denied for {user.display_name} ({user.id})")
        return False
        
    @admined
    def getPriv(self, session, uid, user):
        return PrivSystemLevels(user.priv_level)

    @admined
    def setPriv(self, session, uid, user, priv_level : PrivSystemLevels):
        user.priv_level = priv_level.value
        session.commit()

    def withPriv(level : PrivSystemLevels, send_error=True):
        def decorator(func):
            @wraps(func)
            async def wrapper(self, ctx: commands.Context, *args, **kwargs):
                priv_system = self.bot.get_cog('PrivSystem')
                if priv_system.checkPriv(ctx.author, level):
                    return await func(self, ctx, *args, **kwargs)
                elif (send_error):
                    await self.send_pretty(ctx, PrettyType.ERROR, title="Permission denied", message=f"This command can only be executed by users with {level.name} privileges or higher")
                
                return None                
            return wrapper
        return decorator

    @commands.hybrid_group()
    async def priv(self, ctx: commands.Context):
        pass

    @priv.command()
    @withPriv(PrivSystemLevels.USER)
    async def all(self, ctx: commands.Context):
        with self.db.session as session:
            userlist = ""
            users = session.query(BotUser).all()
            
            guild = ctx.guild

            for user in users:
                uid = int(user.uid)
                level = PrivSystemLevels(user.priv_level).name
                
                if guild:
                    if user.is_role:
                        role = guild.get_role(uid)
                        if role:
                            userlist += f"[ROLE] {role.mention} ({level})\n"
                    else:
                        _user = guild.get_member(uid)
                        if _user:
                            userlist += f"[USER] {_user.mention} ({level})\n"
                            
                elif (ctx.author.id == uid):
                    userlist += f"[DM USER] {ctx.author.mention} ({level})\n"
                
            if userlist == "":
                userlist = "Empty"
                    
            await self.send_pretty(ctx, PrettyType.INFO, title="User & role list", message=userlist)
        
    @priv.command()
    @withPriv(PrivSystemLevels.USER)
    async def me(self, ctx: commands.Context):
        level = self.getPriv(ctx.author)
        await self.send_pretty(ctx, PrettyType.INFO, fields={
            "Name": ctx.author.mention,
            "Level": level.name
        })

    @priv.command()
    @withPriv(PrivSystemLevels.USER)
    async def get(self, ctx: commands.Context, mention : Union[User, Member]):
        level = self.getPriv(mention)
        await self.send_pretty(ctx, PrettyType.INFO, fields={
            "Name": mention.mention,
            "Level": level.name
        })

    @priv.command()
    @withPriv(PrivSystemLevels.OWNER)
    async def set(self, ctx: commands.Context, mention : Union[User, Member, Role]):
        await self.send_pretty(ctx, PrettyType.INFO, 
        title = "Changing permissions",
        fields = {
            "UID": mention.id,
            "Name": mention.mention
        }, view=PrivView(self, mention))