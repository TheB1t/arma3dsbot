import os
import re
import shutil
import asyncio

from datetime import datetime

from discord.ext import commands

from app import *
from .priv_system import *
from utils import LogLevel, to_thread, fetch_url, sessioned
from db import Mod


STEAM_CMD = "/home/arma3server/.steam/steamcmd/steamcmd.sh"

A3_SERVER_ID = "233780"
A3_SERVER_DIR = "/home/arma3server/serverfiles"
A3_WORKSHOP_ID = "107410"

A3_WORKSHOP_DIR = f"{A3_SERVER_DIR}/steamapps/workshop/content/{A3_WORKSHOP_ID}"
A3_MODS_DIR = f"{A3_SERVER_DIR}/mods"
A3_KEYS_DIR = f"{A3_SERVER_DIR}/keys"

UPDATE_PATTERN = re.compile(r"workshopAnnouncement.*?<p id=\"(\d+)\">", re.DOTALL)
WORKSHOP_CHANGELOG_URL = "https://steamcommunity.com/sharedfiles/filedetails/changelog"

RUNSCRIPT_PATH = f"{A3_SERVER_DIR}/updater_runscript.steamcmd"

class ModUpdater(commands.Cog, AppModule):

    def __init__(self, app: App):
        super(ModUpdater, self).__init__(app)

        self.mod_list = []

        for mod_folder, mod_id in self.getMods().items():
            self.addMod(mod_folder, mod_id)
    
    def __del__(self):
        self.__clean()

    @sessioned
    def getMods(self, session):
        mods = session.query(Mod).all()

        tmp = {}
        for mod in mods:
            tmp[mod.folder_name] = mod.mod_id

        return tmp
    
    @commands.hybrid_group(name="mods", fallback="update")
    @PrivSystem.withPriv(PrivSystemLevels.IVENTOLOG)
    async def mods_update(self, ctx: commands.Context, user, passwd, steam_2fa):
        msg = await self.send(ctx, "Launching a mod update")
        await self.run_update(user, passwd, steam_2fa)

        status = '\n'.join(f"[{mod['status']}] {mod['folder']} ({mod['id']})" for mod in self.mod_list)
        await msg.edit(content=f"Mod update status\n```{status}```")
        await msg.delete(delay=10)

    @mods_update.command(name="genline")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def mods_genline(self, ctx: commands.Context, folder: str):
        line = ';'.join(f"{folder}/{mod['folder']}" for mod in self.mod_list)
        await self.send(ctx, f"Modline generated:\n```{line}```")

    async def __check_one_mod(self, mod):
        link_path = "{}/{}".format(A3_MODS_DIR, mod["folder"])
        path = "{}/{}".format(A3_WORKSHOP_DIR, mod["id"])

        if os.path.isdir(path):
            if await self.__mod_needs_update(mod["id"], path):
                os.unlink(link_path)
                shutil.rmtree(path)
            else:
                mod["status"] = "UP-TO-DATE"
                self.log("No update required for \"{}\" ({})... SKIPPING".format(mod["folder"], mod["id"]))
                return [False, mod]
        
        self.log("Required update for \"{}\" ({})".format(mod["folder"], mod["id"]))
        return [True, mod]
    
    async def __check_mods_parallel(self):
        tasks = []

        for mod in self.mod_list:
            task = asyncio.ensure_future(self.__check_one_mod(mod))
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results

    async def __generate_steamcmd_runscript(self, user, passwd, steam_2fa):
        lines = [
            f"force_install_dir {A3_SERVER_DIR}",
            f"login {user} {passwd} {steam_2fa}",
        ]
        
        answers = await self.__check_mods_parallel()

        for answer in answers:
            if (not answer[0]):
                continue

            answer[1]["status"] = "UPDATED"
            lines.append(f"workshop_download_item {A3_WORKSHOP_ID} {answer[1]['id']} validate")
            lines.append(f"workshop_download_item {A3_WORKSHOP_ID} {answer[1]['id']} validate")

        lines.append("quit")

        if len(lines) <= 3:
            return False

        with open(f"{RUNSCRIPT_PATH}", 'w') as file:
            for line in lines:
                file.write(line + '\n')

        return True
    
    def __clean(self):
        if os.path.exists(RUNSCRIPT_PATH):
            os.remove(RUNSCRIPT_PATH)

    @to_thread
    def __run_steamcmd(self):
        if not os.path.exists(RUNSCRIPT_PATH):
            self.log("runscript not found")
            return ""
        
        os.system(f"{STEAM_CMD} +runscript {RUNSCRIPT_PATH}")

        for mod in self.mod_list:
            path = "{}/{}".format(A3_WORKSHOP_DIR, mod["id"])

            if not os.path.isdir(path):
                mod["status"] = "FAILED"

    async def __mod_needs_update(self, mod_id, path):
        if os.path.isdir(path):
            response = await fetch_url("{}/{}".format(WORKSHOP_CHANGELOG_URL, mod_id))
            match = UPDATE_PATTERN.search(response)

            if match:
                updated_at = datetime.fromtimestamp(int(match.group(1)))
                created_at = datetime.fromtimestamp(os.path.getctime(path))

                return updated_at >= created_at

        return False

    @to_thread
    def __lowercase_workshop_dir(self):
        for mod in self.mod_list:
            real_path = "{}/{}".format(A3_WORKSHOP_DIR, mod["id"])

            if mod["status"] == "UPDATED":
                self.log("Convert files to lower for mod {}".format(mod["folder"]))
                os.system("(cd {} && find . -depth -exec rename -v 's/(.*)\/([^\/]*)/$1\/\L$2/' {{}} \;)".format(real_path))
            else:
                self.log("Skipping folder for mod {}".format(mod["folder"]))

    @to_thread
    def __create_mod_symlinks(self):
        for mod in self.mod_list:
            if mod["status"] != "UPDATED":
                continue

            link_path = "{}/{}".format(A3_MODS_DIR, mod["folder"])
            real_path = "{}/{}".format(A3_WORKSHOP_DIR, mod["id"])

            if os.path.isdir(real_path):
                if not os.path.islink(link_path):
                    os.symlink(real_path, link_path)
                    self.log("Creating symlink '{}'...".format(link_path))
            else:
                self.log("Mod '{}' does not exist! ({})".format(mod["folder"], real_path))

    @to_thread
    def __copy_keys(self):
        key_regex = re.compile(r'(key).*', re.I)

        # Check for broken symlinks
        for key in os.listdir(A3_KEYS_DIR):
            key_path = "{}/{}".format(A3_KEYS_DIR, key)
            if os.path.islink(key_path) and not os.path.exists(key_path):
                self.log("Removing outdated server key '{}'".format(key))
                os.unlink(key_path)

        # Update/add new key symlinks
        for mod in self.mod_list:
            if mod["status"] != "UPDATED":
                continue

            real_path = "{}/{}".format(A3_WORKSHOP_DIR, mod["id"])
            if not os.path.isdir(real_path):
                self.log("Couldn't copy key for mod '{}', directory doesn't exist.".format(mod["folder"]))
            else:
                dirlist = os.listdir(real_path)
                keyDirs = [x for x in dirlist if re.search(key_regex, x)]

                if keyDirs:
                    keyDir = keyDirs[0]
                    if os.path.isfile("{}/{}".format(real_path, keyDir)):
                        # Key is placed in root directory
                        key = keyDir
                        key_path = os.path.join(A3_KEYS_DIR, key)
                        if not os.path.exists(key_path):
                            self.log("Creating symlink to key for mod '{}' ({})".format(mod["folder"], key))
                            os.symlink(os.path.join(real_path, key), key_path)
                    else:
                        # Key is in a folder
                        for key in os.listdir(os.path.join(real_path, keyDir)):
                            real_key_path = os.path.join(real_path, keyDir, key)
                            key_path = os.path.join(A3_KEYS_DIR, key)
                            if not os.path.exists(key_path):
                                self.log("Creating symlink to key for mod '{}' ({})".format(mod["folder"], key))
                                os.symlink(real_key_path, key_path)
                else:
                    self.log("!! Couldn't find key folder for mod {} !!".format(mod["folder"]))

    def addMod(self, mod_folder, mod_id):
        self.mod_list.append({ "folder": mod_folder, "id": mod_id, "status": "UNKNOWN" })

    async def run_update(self, user, passwd, steam_2fa):
        self.log("Updating mods...")
        if not await self.__generate_steamcmd_runscript(user, passwd, steam_2fa):
            self.log("No update required!")
            return False
        
        await self.__run_steamcmd()
        self.log("Converting uppercase files/folders to lowercase...")
        await self.__lowercase_workshop_dir()
        self.log("Creating symlinks...")
        await self.__create_mod_symlinks()
        self.log("Copying server keys...")
        await self.__copy_keys()
        self.log("Clean...")
        self.__clean()
        return True