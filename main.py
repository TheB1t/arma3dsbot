import re
import json
import subprocess

import discord
from discord.ext import commands

from bot import StatusBot
from server import Server
from mod_updater import ModUpdater
from db import Database

#  Read settings.json
try:
    with open("settings.json", 'r') as file:
        settings = json.load(file)

except FileNotFoundError:
    print("Can't find settings.json")
    exit(1)

#  Init
db = Database(settings["db_ip"], settings["db_port"], settings["db_user"], settings["db_pass"], settings["db_db"])
srv = Server(settings["ip"], settings["base_port"])

updater = ModUpdater()
for mod_folder, mod_id in db.getMods().items():
    updater.addMod(mod_folder, mod_id)

#  Decorators
def only_admin():
    async def predicate(ctx):
        if db.isAdmin(ctx.author.id):
            return True
        else:
            await ctx.send("Вы не имеете прав для выполнения этой команды.")
            return False
        
    return commands.check(predicate)

# [BOT] Initial
bot = StatusBot('!', srv, settings)

# [BOT] Commands
@bot.command(brief="Restarting server")
@only_admin()
async def restart(ctx):
    try:
        await ctx.send("Инициирование перезагрузки (ETA ~5 min)")
        await bot.setRebootState()
        
        out = subprocess.run("bash restart.sh", check=True, text=True, capture_output=True, shell=True)
        # await ctx.send(f"Выполнение завершено с кодом {out.returncode} (Успешно):\n```\n{out.stdout}\n```")
    except subprocess.CalledProcessError as e:
        await ctx.send("Ошибка при попытке перезагрузки, нужно перезапустить вручную!")
        # await ctx.send(f"Выполнение завершено с кодом {e.returncode} (Ошибка):\n```\n{e.stderr}\n```")

@bot.command(brief="Повышает пользователя")
@only_admin()
async def promote(ctx, 
                  mention = commands.parameter(description="Пинг пользователя")
                  ):
    user_id_match = re.match(r'<@!?(\d+)>', mention)
    if user_id_match:
        user_id = int(user_id_match.group(1))
        if (db.addAdmin(user_id)):
            await ctx.send(f"{mention} теперь админ")
        else:
            await ctx.send(f"{mention} уже админ")
    else:
        await ctx.send(f"В качестве аргумента ожидался пользователь, принято {mention}")

@bot.command(brief="Понижает пользователя")
@only_admin()
async def demote(ctx, 
                 mention = commands.parameter(description="Пинг пользователя")
                 ):
    user_id_match = re.match(r'<@!?(\d+)>', mention)
    if user_id_match:
        user_id = int(user_id_match.group(1))
        if (db.delAdmin(user_id)):
            await ctx.send(f"{mention} больше не админ")
        else:
            await ctx.send(f"{mention} и так не админ")
    else:
        await ctx.send(f"В качестве аргумента ожидался пользователь, принято {mention}")

@bot.command(brief="Обновляет моды на сервере")
@only_admin()
async def update_mods(ctx, 
                      user = commands.parameter(description="Имя пользователя Steam"), 
                      passwd = commands.parameter(description="Пароль Steam"), 
                      steam_2fa = commands.parameter(description="Код 2FA Steam")
                      ):
    await ctx.send("Запуск обновления модов")
    await updater.run_update(user, passwd, steam_2fa)

    status = ""
    for mod in updater.mods:
        status += f"[{mod['status']}] {mod['folder']} ({mod['id']})\n"

    await ctx.send(f"Статус обновления модов\n```\n{status}```")

bot.run(settings["token"])
