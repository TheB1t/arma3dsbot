import socket
from steam import game_servers as gs

class Server:

    def __init__(self, ip, base_port):
        self.ip = ip
        self.query_port = base_port + 1

    def getInfo(self):
        try:
            return gs.a2s_info((self.ip, self.query_port))
        except (RuntimeError, socket.timeout):
            raise RuntimeError("Failed to get server info")

    def getPlayers(self):
        try:
            return gs.a2s_players((self.ip, self.query_port))
        except (RuntimeError, socket.timeout):
            raise RuntimeError("Failed to get server players")
        
    def ping(self):
        try:
            self.getInfo()
            return True
        except:
            return False