import app
from modules import *

_app = app.App()

_app.addModule(PrivSystem, "PrivSystem")
_app.addModule(ModUpdater, "ModUpdater")
_app.addModule(ServerRestarter, "ServerRestarter")
_app.addModule(MissionUploader, "MissionUploader")
_app.addModule(MiscCommands, "MiscCommands")
_app.addModule(ZeusManager, "ZeusManager")

_app.run()