import asyncio

from datetime import datetime

from client import WvsLoginClient
from client.entities import Account, Character
from client.entities.inventory import InventoryType
from common.constants import (
    AUTO_LOGIN, AUTO_REGISDTER, CENTER_PORT, HOST_IP, LOGIN_PORT,
    MAX_CHARACTERS, REQUEST_PIC, REQUEST_PIN, REQUIRE_STAFF_IP, WORLD_COUNT,
    get_job_from_creation)
from common.types import PendingLogin
from db import DatabaseClient
from net.packets import Packet
from net.packets.opcodes import CRecvOps, CSendOps
from net.packets.packet import packet_handler
from server.server_base import ServerBase
from utils.cpacket import CPacket


class WvsLogin(ServerBase):

    def __init__(self, parent):
        super().__init__(parent, LOGIN_PORT, 'LoginServer')
        
        self._worlds = []
        self._auto_register = AUTO_REGISDTER
        self._request_pin = REQUEST_PIN
        self._request_pic = REQUEST_PIC
        self._require_staff_ip = REQUIRE_STAFF_IP
        self._max_characters = MAX_CHARACTERS
        self._login_pool = []

    def add_world(self, world):
        self._worlds.append(world)

    @classmethod
    async def run(cls, parent):
        login = WvsLogin(parent)
        await login.start()

        return login

    async def client_connect(self, client):
        return WvsLoginClient(self, client)

    @packet_handler(CRecvOps.CP_CreateSecurityHandle)
    async def create_secuirty_heandle(self, client, packet):
        if AUTO_LOGIN:
            i_packet = Packet(op_code=CRecvOps.CP_CheckPassword)
            i_packet.encode_string("admin")
            i_packet.encode_string("admin")
            i_packet.seek(2)
            client.dispatch(i_packet)

    @packet_handler(CRecvOps.CP_CheckPassword)
    async def check_password(self, client, packet):
        password = packet.decode_string()
        username = packet.decode_string()
        response = await client.login(username, password)

        if response is 0:
            return await client.send_packet(
                CPacket.check_password_result(client, response))

        await client.send_packet(
            CPacket.check_password_result(response=response))

    async def send_world_information(self, client) -> None:
        for world in self._worlds:
            await client.send_packet(CPacket.world_information(world))

        await client.send_packet(CPacket.end_world_information())
        await client.send_packet(CPacket.last_connected_world(0))

        await client.send_packet(CPacket.send_recommended_world(self._worlds))

    @packet_handler(CRecvOps.CP_WorldRequest)
    async def world_request(self, client, packet):
        await self.send_world_information(client)

    @packet_handler(CRecvOps.CP_WorldInfoRequest)
    async def world_info_request(self, client, packet):
        await self.send_world_information(client)

    @packet_handler(CRecvOps.CP_CheckUserLimit)
    async def check_user_limit(self, client, packet):
        await client.send_packet(CPacket.check_user_limit(0))

    @packet_handler(CRecvOps.CP_SelectWorld)
    async def select_world(self, client, packet):
        packet.decode_byte()

        client.world_id = world_id = packet.decode_byte()
        client.channel_id = packet.decode_byte()

        client.account.last_connected_world = world_id

        # Load avatars for specific world in future
        await client.load_avatars(world_id=world_id)
        await client.send_packet(CPacket.world_result(client.avatars))

    @packet_handler(CRecvOps.CP_LogoutWorld)
    async def logout_world(self, client, packet):
        pass

    @packet_handler(CRecvOps.CP_CheckDuplicatedID)
    async def check_duplicated_id(self, client, packet):
        name = packet.decode_string()
        exists = await self.data.characters.get(name=name) is not None

        await client.send_packet(
            CPacket.check_duplicated_id_result(name, exists))

    @packet_handler(CRecvOps.CP_ViewAllChar)
    async def view_all_characters(self, client, packet):
        await client.load_avatars()
        packet.decode_byte()  # game_start_mode

        await asyncio.sleep(2)
        await client.send_packet(
            CPacket.start_view_all_characters(client.avatars))

        for world in self._worlds:
            await client.send_packet(
                CPacket.view_all_characters(world, client.avatars))

    @packet_handler(CRecvOps.CP_CreateNewCharacter)
    async def create_new_character(self, client, packet):
        character = Character()
        character.name = packet.decode_string()
        character.job = get_job_from_creation(packet.decode_int())
        character.sub_job = packet.decode_short()
        character.face = packet.decode_int()
        character.hair = packet.decode_int() + packet.decode_int()
        character.skin = packet.decode_int()

        invs = character.inventories

        top = await self.data.items.get(packet.decode_int())
        bottom = await self.data.items.get(packet.decode_int())
        shoes = await self.data.items.get(packet.decode_int())
        weapon = await self.data.items.get(packet.decode_int())

        invs.add(top, slot=-5)
        invs.add(bottom, slot=-6)
        invs.add(shoes, slot=-7)
        invs.add(weapon, slot=-11)
        
        character.gender = packet.decode_byte()

        character_id = await self.data.account(id=client.account.id)\
            .create_character(character)

        if character_id:
            character.id = character_id
            client.avatars.append(character)

            return await client.send_packet(
                CPacket.create_new_character(character, False))
        
        return await client.send_packet(
            CPacket.create_new_character(character, True))

    @packet_handler(CRecvOps.CP_SelectCharacter)
    async def select_character(self, client, packet):
        uid = packet.decode_int()
        character = next((c for c in client.avatars if c.id == uid), None)
        port = self.parent.worlds[client.world_id][client.channel_id].port

        self.parent.logged_in.append(
            PendingLogin(character, client.account, datetime.now()))

        await client.send_packet(
            CPacket.select_character_result(uid, port))
    
