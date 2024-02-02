from steam import game_servers as gs

class Server:

    def __init__(self, ip, base_port):
        self.ip = ip
        self.query_port = base_port + 1

    def getInfo(self):
        try:
            return gs.a2s_info((self.ip, self.query_port))
        except Exception:
            return {}

    def getPlayers(self):
        try:
            return gs.a2s_players((self.ip, self.query_port))
        except Exception:
            return []
        
    def ping(self):
        if len(self.getInfo()) == 0:
            return False
        else:
            return True
    
    def get(self):
        serverInfo = self.getInfo()
        serverPlayers = self.getPlayers()
        
        if "name" not in serverInfo:
            serverInfo["name"] = "Unknown"

        if "map" not in serverInfo:
            serverInfo["map"] = "Unknown"

        if "game" not in serverInfo:
            serverInfo["game"] = "Unknown"
            
        if "players" not in serverInfo:
            serverInfo["players"] = 0

        if "max_players" not in serverInfo:
            serverInfo["max_players"] = 0

        return (serverInfo, serverPlayers)