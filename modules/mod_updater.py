import os
import re
import time
import shutil
import asyncio
import subprocess

from datetime import datetime
from enum import Enum
from bs4 import BeautifulSoup

from discord.ext import commands

from app import *
from .priv_system import *
from utils import LogLevel, to_thread, to_task, fetch_url, sessioned
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

MAIN_RUNSCRIPT_PATH = f"{A3_SERVER_DIR}/updater_runscript.steamcmd"
VALIDATE_RUNSCRIPT_PATH = f"{A3_SERVER_DIR}/validate_runscript.steamcmd"

class ModStatus(Enum):
    UNKNOWN                 = 0
    UP_TO_DATE              = 1
    IN_QUEUE                = 2
    IN_PROGRESS             = 3
    WAIT_VALIDATION         = 4
    VALIDATING              = 5
    UPDATED                 = 6
    FAILED                  = 7
    
class ModUpdater(commands.Cog, AppModule):

    def __init__(self, app: App):
        super(ModUpdater, self).__init__(app)

        self._check_settings_exist("steam_user")
        self._check_settings_exist("steam_password")

        self.mod_list = []

        self.__loadModList()
        self.bot.setAttachmentExtHandler("html", self.loadPreset)
    
    def __del__(self):
        self.__clean()
    
    @commands.hybrid_group(name="mods", fallback="update")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def mods_update(self, ctx: commands.Context):       
        steam_user = self.settings["steam_user"]
        steam_password = self.settings["steam_password"]
        
        await self.run_update(ctx, steam_user, steam_password)

    @mods_update.command(name="genline")
    @PrivSystem.withPriv(PrivSystemLevels.OWNER)
    async def mods_genline(self, ctx: commands.Context, folder: str):
        line = '\;'.join(f"{folder}/{mod['folder']}" for mod in self.mod_list)
        await self.send(ctx, f"Modline generated:\n```{line}```")

    @PrivSystem.withPriv(PrivSystemLevels.OWNER, False)
    async def loadPreset(self, ctx: commands.Context, attachment: discord.Attachment):
        msg = await self.send(ctx, f"Detected preset file. Starting update...")
        
        out = subprocess.run(f"wget -O /tmp/preset.html {attachment.url}", check=True, text=True, capture_output=True, shell=True)
        self.log(f"\n{out.stderr}")
        
        try:
            with open("/tmp/preset.html", 'r') as file:
                self.__cleanTable()
                
                soup = BeautifulSoup(file.read(), 'html.parser')
                
                mod_rows = soup.find_all('tr', {'data-type': 'ModContainer'})
                
                for row in mod_rows:
                    mod_name = row.find('td', {'data-type': 'DisplayName'}).text.strip()
                    mod_link = row.find('a', {'data-type': 'Link'})['href']
                    mod_id = mod_link.split('=')[-1]

                    if not mod_name.startswith('@'):
                        formatted_mod_name = re.sub(r'\W+', '_', mod_name).lower()
                        formatted_mod_name = f"@{formatted_mod_name}"
                    else:
                        formatted_mod_name = mod_name

                    self.__addMod(formatted_mod_name, mod_id)
                    
            self.__loadModList()
            await self.edit(msg, f"Preset update finished, please run 'mod update' for complete updating!\nMod list\n```{self.__generate_mod_list()}```")
        except Exception as e:
            self.log(str(e))
            await self.edit(msg, "Preset update failed!")

#--------------------------------------------------------------#
#                        MOD UPDATE                            #
#--------------------------------------------------------------#
    async def __check_one_mod(self, mod):
        mod_id = mod.get("id")
        folder = mod.get("folder")
        link_path = mod.get("link_path")
        real_path = mod.get("real_path")

        if os.path.isdir(real_path):
            if await self.__mod_needs_update(mod_id, real_path) or self.checkModStatus(mod, ModStatus.FAILED):
                if os.path.exists(link_path):
                    os.unlink(link_path)
                    
                # if os.path.exists(real_path):
                #     shutil.rmtree(real_path)
            else:
                self.setModStatus(mod, ModStatus.UP_TO_DATE)
                self.log(f"No update required for \"{folder}\" ({mod_id})... SKIPPING")
                return [False, mod]
        
        self.log(f"Required update for \"{folder}\" ({mod_id})")
        return [True, mod]
    
    async def __check_mods_parallel(self):
        tasks = []

        for mod in self.mod_list:
            task = asyncio.ensure_future(self.__check_one_mod(mod))
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results

    async def __generate_steamcmd_runscript(self, user, passwd):
        update_lines = [
            f"force_install_dir {A3_SERVER_DIR}",
            f"login {user} {passwd}",
        ]
        validate_lines = update_lines.copy()
        
        answers = await self.__check_mods_parallel()

        for answer in answers:
            if (not answer[0]):
                self.setModStatus(answer[1], ModStatus.WAIT_VALIDATION)
            else:
                self.setModStatus(answer[1], ModStatus.IN_QUEUE)
                update_lines.append(f"workshop_download_item {A3_WORKSHOP_ID} {answer[1]['id']} validate")
                
            validate_lines.append(f"workshop_download_item {A3_WORKSHOP_ID} {answer[1]['id']} validate")

        validate_lines.append("quit")
        update_lines.append("quit")

        with open(MAIN_RUNSCRIPT_PATH, 'w') as file:
            for line in update_lines:
                file.write(line + '\n')

        with open(VALIDATE_RUNSCRIPT_PATH, 'w') as file:
            for line in validate_lines:
                file.write(line + '\n')
                
        return True
    
    def __clean(self):
        if os.path.exists(MAIN_RUNSCRIPT_PATH):
            os.remove(MAIN_RUNSCRIPT_PATH)

        if os.path.exists(VALIDATE_RUNSCRIPT_PATH):
            os.remove(VALIDATE_RUNSCRIPT_PATH)
            
    def __remove_escape_sequences(self, data):
        escape_pattern = re.compile(b'\x1b[^m]*m')
        return escape_pattern.sub(b'', data)
    
    @to_task
    async def __run_steamcmd(self, runscript, fsuccess, ferror, ftimeout, fstart):
        if not os.path.exists(runscript):
            self.log("runscript not found")
            return ""

        process = await asyncio.create_subprocess_exec(STEAM_CMD, "+runscript", runscript, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        start_pattern   = re.compile(r'workshop_download_item \d+ (\d+)')
        success_pattern = re.compile(r'Success\. Downloaded item (\d+)')
        timeout_pattern = re.compile(r'ERROR! Timeout downloading item (\d+)')
        error_pattern   = re.compile(r'ERROR! Download item (\d+) failed \(([^)]+)\)')
        
        while True:
            rawline = await process.stdout.readline()

            rawline = self.__remove_escape_sequences(rawline)
            
            line = rawline.decode('ascii').replace('\n', '')

            start_match     = start_pattern.search(line)
            success_match   = success_pattern.search(line)
            timeout_match   = timeout_pattern.search(line)
            error_match     = error_pattern.search(line)

            if success_match:
                modid = success_match.group(1)
                fsuccess(modid)
                
            if error_match:
                modid = error_match.group(1)
                error = error_match.group(2)
                ferror(modid, error)

            if timeout_match:
                modid = timeout_match.group(1)
                ftimeout(modid)
                
            if start_match:
                modid = start_match.group(1)
                fstart(modid)
            
            if not rawline:
                break
        
        await process.wait()

    async def __mod_needs_update(self, mod_id, path):
        if os.path.isdir(path):
            response = await fetch_url("{}/{}".format(WORKSHOP_CHANGELOG_URL, mod_id))
            match = UPDATE_PATTERN.search(response)

            if match:
                updated_at = datetime.fromtimestamp(int(match.group(1)))
                created_at = datetime.fromtimestamp(os.path.getctime(path))

                return updated_at >= created_at

        return False

    def __rename_files_to_lowercase(self, directory_path):
        if not os.path.exists(directory_path):
            return

        parent_directory = os.path.dirname(directory_path)
        
        for root, dirs, files in os.walk(directory_path):
            for filename in files:
                old_path = os.path.join(root, filename)
                new_filename = filename.lower()
                new_path = os.path.join(root, new_filename)

                os.rename(old_path, new_path)
                
                relative_path = os.path.relpath(root, parent_directory)
                print(f"Renamed: {relative_path}/{filename} -> {new_filename}")
            
    async def __lowercase_workshop_dir(self):
        for mod in self.mod_list:
            mod_folder = mod.get("folder")
            real_path = mod.get("real_path")
            
            if self.checkModStatus(mod, ModStatus.UP_TO_DATE):
                self.log(f"Convert files to lower for mod {mod_folder}")
                self.__rename_files_to_lowercase(real_path)
            else:
                self.log(f"Skipping folder for mod {mod_folder}")

    async def __create_mod_symlinks(self):
        for mod in self.mod_list:
            if not self.checkModStatus(mod, ModStatus.UP_TO_DATE):
                continue

            mod_folder = mod.get("folder")
            real_path = mod.get("real_path")
            link_path = mod.get("link_path")

            if os.path.isdir(real_path):
                if not os.path.islink(link_path):
                    os.symlink(real_path, link_path)
                    self.log(f"Creating symlink '{link_path}'...")
            else:
                self.log(f"Mod '{mod_folder}' does not exist! ({real_path})")

    async def __copy_keys(self):
        key_regex = re.compile(r'(key).*', re.I)

        # Check for broken symlinks
        for key in os.listdir(A3_KEYS_DIR):
            key_path = "{}/{}".format(A3_KEYS_DIR, key)
            if os.path.islink(key_path) and not os.path.exists(key_path):
                self.log(f"Removing outdated server key '{key}'")
                os.unlink(key_path)

        # Update/add new key symlinks
        for mod in self.mod_list:
            if not self.checkModStatus(mod, ModStatus.UP_TO_DATE):
                continue

            mod_folder = mod.get("folder")
            real_path = mod.get("real_path")
            
            if not os.path.isdir(real_path):
                self.log(f"Couldn't copy key for mod '{mod_folder}', directory doesn't exist.")
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
                            self.log(f"Creating symlink to key for mod '{mod_folder}' ({key})")
                            os.symlink(os.path.join(real_path, key), key_path)
                    else:
                        # Key is in a folder
                        for key in os.listdir(os.path.join(real_path, keyDir)):
                            real_key_path = os.path.join(real_path, keyDir, key)
                            key_path = os.path.join(A3_KEYS_DIR, key)
                            if not os.path.exists(key_path):
                                self.log(f"Creating symlink to key for mod '{mod_folder}' ({key})")
                                os.symlink(real_key_path, key_path)
                else:
                    self.log(f"!! Couldn't find key folder for mod {mod_folder} !!")
                  

    def __update_success(self, modid):
        self.log(f"Downloaded mod {modid}")
                
        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.UPDATED)
        self.setModEndTime(mod)

    def __update_error(self, modid, err):
        self.log(f"Failed to download mod {modid}: {err}")

        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.FAILED)
        self.setModEndTime(mod)
        
    def __update_timeout(self, modid):
        self.log(f"Failed to download mod {modid}: Timeout")

        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.FAILED)
        self.setModEndTime(mod)
        
    def __update_start(self, modid):
        self.log(f"Downloading mod {modid}...")
                
        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.IN_PROGRESS)
        self.setModStartTime(mod)

    def __validate_success(self, modid):
        self.log(f"Validated mod {modid}")
                
        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.UP_TO_DATE)

    def __validate_error(self, modid, err):
        self.log(f"Failed to validate mod {modid}: {err}")

        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.FAILED)
        
    def __validate_timeout(self, modid):
        self.log(f"Failed to validate mod {modid}: Timeout")

        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.FAILED)
        
    def __validate_start(self, modid):
        self.log(f"Validating mod {modid}...")
                
        mod = self.findModByID(modid)
        self.setModStatus(mod, ModStatus.VALIDATING)
             
    async def run_update(self, ctx, user, passwd):   
        msg = await self.send(ctx, "Launching a mod update", None, False)

        self.log("Generating runscript...")
        if not await self.__generate_steamcmd_runscript(user, passwd):
            self.log("No update required!")
            return False

        self.log("Deleting symlinks...")
        for item in os.listdir(A3_MODS_DIR):
            itempath = os.path.join(A3_MODS_DIR, item)
        
            if os.path.islink(itempath):
                self.log(f"Remove link {itempath}")
                os.unlink(itempath)
        
        self.log("Updating mods...")
        main_task = self.__run_steamcmd(MAIN_RUNSCRIPT_PATH, self.__update_success, self.__update_error, self.__update_timeout, self.__update_start)
        
        while not main_task.done():
            await self.edit(msg, f"Mod update status (UPDATING)\n```{self.__generate_mod_list()}```", None)
            await asyncio.sleep(2)
            
        await main_task
        
        validate_task = self.__run_steamcmd(VALIDATE_RUNSCRIPT_PATH, self.__validate_success, self.__validate_error, self.__validate_timeout, self.__validate_start)
        
        while not validate_task.done():
            await self.edit(msg, f"Mod update status (VALIDATING)\n```{self.__generate_mod_list()}```", None)
            await asyncio.sleep(2)
        
        await validate_task
        
        await self.edit(msg, f"Mod update status (DONE)\n```{self.__generate_mod_list()}```", None)
        
        self.log("Converting uppercase files/folders to lowercase...")
        await self.__lowercase_workshop_dir()
        self.log("Creating symlinks...")
        await self.__create_mod_symlinks()
        self.log("Copying server keys...")
        await self.__copy_keys()
        self.log("Clean...")
        self.__clean()
        return True

#--------------------------------------------------------------#
#                           MISC                               #
#--------------------------------------------------------------#
    
    def __getModByID(self, session, mod_id):
        return session.query(Mod).filter_by(mod_id=mod_id).first()
    
    @sessioned
    def __setModStatus(self, session, mod_id, status):
        mod = self.__getModByID(session, mod_id)

        if mod:
            mod.status = status.value
            session.commit()
            
    @sessioned
    def __loadModList(self, session):
        mods = session.query(Mod).all()
        
        for mod in mods:
            self.addMod(mod.folder_name, mod.mod_id, ModStatus(mod.status))

    @sessioned
    def __addMod(self, session, folder_name, mod_id):    
        mod = self.__getModByID(session, mod_id)

        if not mod:
            mod = Mod(folder_name=folder_name, mod_id=mod_id)
            session.add(mod)
            session.commit()
    
    def __cleanTable(self):
        table = self.db.getTable(Mod.__tablename__)
        table.delete()
    
    def __generate_mod_list(self):
        return '\n'.join("[{}] {} ({}, took {:.2f} s)".format(mod.get("status")._name_, mod.get("folder"), mod.get("id"), self.getModTook(mod)) for mod in self.mod_list)

    def addMod(self, mod_folder, mod_id, status = ModStatus.UNKNOWN):
        self.log(f"Adding mod {mod_folder} ({mod_id})")
        self.mod_list.append({ 
            "folder": mod_folder, 
            "id": mod_id,
            "real_path": "{}/{}".format(A3_WORKSHOP_DIR, mod_id),
            "link_path": "{}/{}".format(A3_MODS_DIR, mod_folder),
            "start_time": 0,
            "end_time": 0,
            "status": status
        })
        
    def checkModStatus(self, mod, status):
        return mod.get("status") == status

    def setModStatus(self, mod, status):
        mod["status"] = status
        mod_id = mod.get("id")
        self.__setModStatus(mod_id, status)

    def setModStartTime(self, mod):
        mod["start_time"] = time.time_ns()
        
    def setModEndTime(self, mod):
        mod["end_time"] = time.time_ns()
        
    def getModTook(self, mod):
        start_time = mod["start_time"]
        end_time = mod["end_time"]
        
        if start_time == 0:
            return 0
        
        if end_time == 0:
            end_time = time.time_ns()
        
        return (end_time - start_time) / 1000000000
        
    def findModByID(self, id):
        for mod in self.mod_list:
            if mod.get("id") == id:
                return mod
        return None