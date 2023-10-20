import discord
from discord.ext import commands

from app import App, AppModule
from utils import LogLevel, BotInternalException
from .priv_system import PrivSystem, PrivSystemLevels

class MiscCommands(commands.Cog, AppModule):
    def __init__(self, app: App):
        super(MiscCommands, self).__init__(app)

    @commands.hybrid_group(name="cleanmessages", fallback="onlybot")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def clean(self, ctx: commands.Context):
        channel = ctx.message.channel
        
        messages = []

        async for message in channel.history(limit=None):
            if message.author == self.bot.user:
                messages.append(message)
                self.log(f"Removing message [{ctx.guild.name}][{message.channel}][{message.created_at}] <{message.author}> -> {message.content}")

        await channel.delete_messages(messages)
        await self.send(ctx, f"Removed {len(messages)}")

    @clean.command(name="all")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def cleanAll(self, ctx: commands.Context):
        channel = ctx.message.channel
        
        messages = []

        async for message in channel.history(limit=None):
            messages.append(message)
            self.log(f"Removing message [{ctx.guild.name}][{message.channel}][{message.created_at}] <{message.author}> -> {message.content}")

        await channel.delete_messages(messages)
        await self.send(ctx, f"Removed {len(messages)}")

    @commands.hybrid_command()
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def sync(self, ctx: commands.Context):
        synced = await self.bot.tree.sync()
        await self.send(ctx, f"Synced {len(synced)} global commands")

    @commands.hybrid_command()
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def maintenance_toggle(self, ctx: commands.Context):
        mode = self.bot.toggleMaintenanceMode()
        await self.send(ctx, f"Maintenance mode {'enabled' if mode else 'disabled'}")