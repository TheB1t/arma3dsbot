import re

from typing import Union
from enum import Enum
from functools import wraps

import discord
from discord.ext import commands

from app import AppModule
from utils import LogLevel, BotInternalException, sessioned
from db import Admin

class PrivSystemLevels(Enum):
    OWNER       = 0
    ADMIN       = 1
    IVENTOLOG   = 2
    USER        = 256

class PrivSystem(commands.Cog, AppModule):

    def __init__(self, app):
        super(PrivSystem, self).__init__(app)
        self.priv_levels = list(PrivSystemLevels)

    def getAdminByUID(self, session, uid):
        return session.query(Admin).filter_by(uid=uid).first()
    
    def admined(func):
        def wrapper(self, session, uid, *args, **kwargs):
            uid = str(uid)
            admin = self.getAdminByUID(session, uid)

            if not admin:
                admin = Admin(uid=uid, priv_level=PrivSystemLevels.USER.value)
                session.add(admin)
                session.commit()

            return func(self, session, uid, admin, *args, **kwargs)
        return wrapper

    @sessioned
    @admined
    def checkPriv(self, session, uid, admin, priv_level : PrivSystemLevels):
        return PrivSystemLevels(admin.priv_level).value <= priv_level.value

    @sessioned
    @admined
    def getPriv(self, session, uid, admin):
        return PrivSystemLevels(admin.priv_level)

    @sessioned
    @admined
    def setPriv(self, session, uid, admin, priv_level : PrivSystemLevels):
        admin.priv_level = priv_level.value
        session.commit()

    def withPriv(level : PrivSystemLevels, send_error=True):
        def decorator(func):
            @wraps(func)
            async def wrapper(self, ctx: commands.Context, *args, **kwargs):
                priv_system = self.bot.get_cog('PrivSystem')
                if priv_system.checkPriv(ctx.author.id, level):
                    return await func(self, ctx, *args, **kwargs)
                elif (send_error):
                    await self.send(ctx, f"This command can only be executed by users with {level.name} privileges or higher")
                
                return None                
            return wrapper
        return decorator
    
    def calcLevel(self, current_level, next_level=True):
        index = self.priv_levels.index(current_level)

        if next_level:
            tmp_index = index + 1
            if (tmp_index <= len(self.priv_levels)):
                return self.priv_levels[tmp_index]
        else:
            tmp_index = index - 1
            if (tmp_index >= 0):
                return self.priv_levels[tmp_index]
            
        return current_level

    @commands.hybrid_group(fallback="getall")
    @withPriv(PrivSystemLevels.USER)
    async def priv(self, ctx: commands.Context):
        levels = ""
        for level in self.priv_levels:
            levels += f"{level.name} ({level.value})\n"

        await self.send(ctx, f"Existing privilege levels\n```\n{levels}```")

    @priv.command(name="getmy")
    @withPriv(PrivSystemLevels.USER)
    async def getMyPrivLevel(self, ctx: commands.Context):
        user_id = ctx.author.id
        level = self.getPriv(user_id)
        await self.send(ctx, f"Your privilege level is {level.name}")

    @priv.command(name="get")
    @withPriv(PrivSystemLevels.USER)
    async def getPrivLevel(self, ctx: commands.Context, mention : Union[discord.User, discord.Member]):
        level = self.getPriv(mention.id)
        await self.send(ctx, f"{mention.display_name} privilege level is {level.name}")

    @priv.command(name="set")
    @withPriv(PrivSystemLevels.OWNER)
    async def setPrivLevel(self, ctx: commands.Context, mention : Union[discord.User, discord.Member, discord.Role], level : str):
        if not (level in PrivSystemLevels.__members__):
            raise BotInternalException(f"Privilege level {level} does not exist")
        
        await self.process(ctx, mention, 
            lambda clevel: PrivSystemLevels[level],
            lambda m, cl, rl: f"{m.display_name} is now {rl.name} (previously {cl.name})",
            lambda m, cl, rl: f"{m.display_name} already {rl.name}")  
        
    @priv.command()
    @withPriv(PrivSystemLevels.OWNER)
    async def promote(self, ctx: commands.Context, mention : Union[discord.User, discord.Member, discord.Role]):    
        await self.process(ctx, mention, 
            lambda clevel: self.calcLevel(clevel, False),
            lambda m, cl, rl: f"{m.display_name} is now {rl.name} (previously {cl.name})",
            lambda m, cl, rl: f"{m.display_name} already has the highest possible privilege level",
            allow_roles=False)  

    @priv.command()
    @withPriv(PrivSystemLevels.OWNER)
    async def demote(self, ctx: commands.Context, mention : Union[discord.User, discord.Member, discord.Role]):
        await self.process(ctx, mention, 
            lambda clevel: self.calcLevel(clevel, True),
            lambda m, cl, rl: f"{m.display_name} is now {rl.name} (previously {cl.name})",
            lambda m, cl, rl: f"{m.display_name} already has the lowest possible privilege level",
            allow_roles=False)

    async def process(self, ctx: commands.Context, mention, get_level, success_func, fail_func, allow_roles=True):
        self.log(f"Mention class: {mention.__class__.__name__}")
        if isinstance(mention, discord.User) or isinstance(mention, discord.Member):
            await self.process_user(ctx, mention, get_level, success_func, fail_func)
        elif isinstance(mention, discord.Role):
            if not allow_roles:
                raise BotInternalException("Role mentions are not available for this command, use user mentions.")
            
            for member in mention.members:
                await self.process_user(ctx, member, get_level, success_func, fail_func)

    async def process_user(self, ctx: commands.Context, mention : Union[discord.User, discord.Member], get_level, success_func, fail_func):
        self.log(f"process_user: {mention.id} {mention.display_name}")
        current_level = self.getPriv(mention.id)
        requested_level = get_level(current_level)

        if (current_level != requested_level):
            self.setPriv(mention.id, requested_level)
            text = success_func(mention, current_level, requested_level)
            await self.send(ctx, text)
        else:
            text = fail_func(mention, current_level, requested_level)
            await self.send(ctx, text)