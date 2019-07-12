from common.constants import GAME_PORT

class WvsGameManager(list):
    def __init__(self, world, channel_limit = 1):
        self._world = world
        self.channel_limit = channel_limit

    def get(self, channel_id):
        for channel in self:
            if channel.id == channel_id:
                return channel
        
        return None
        
    def add(self, client):
        self.append(client)

        client.port = GAME_PORT + len(self)
        client.world = self._world
        client.id = len(self) - 1
    
    @property
    def is_full(self):
        return len(self) >= self.channel_limit