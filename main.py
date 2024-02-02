import app
from modules import *

_app = app.App()

_app.addModule(PrivSystem)
_app.addModule(ModUpdater)
_app.addModule(ServerManager)
_app.addModule(MissionUploader)
_app.addModule(MiscCommands)
_app.addModule(PlayerManager)

_app.run()