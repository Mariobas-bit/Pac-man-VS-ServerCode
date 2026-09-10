from gevent import monkey
monkey.patch_all()

from flask.ctx import RequestContext
def get_session(self): return getattr(self, "_session", None)
def set_session(self, value): self._session = value
RequestContext.session = property(get_session, set_session)

import os
import random
import string
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

game_rooms = {}

def generate_unique_code():
    while True:
        characters = string.ascii_uppercase + string.digits
        code = ''.join(random.choice(characters) for _ in range(4))
        if code not in game_rooms:
            return code

@app.route('/')
def home():
    return "Pac-Man Vs. Server is running on Python 3.14!"

@socketio.on('connect')
def handle_connect():
    print(f"--- Player connected! ID: {request.sid} ---")
    emit('change_menu_state', {'state': 'MAIN_MENU'})

@socketio.on('create_game_room')
def handle_create_room():
    player_id = request.sid
    room_code = generate_unique_code()

    game_rooms[room_code] = {
        "players": [player_id],
        "host_id": player_id,
        "game_started": False,
        "points_to_win": 1000,
        "pacman_id": None,
        "scores": {player_id: 0}
    }

    join_room(room_code)
    print(f"Host {player_id} created a brand new Room: {room_code}")
    
    emit('lobby_status_personal', {
        'is_host': True
    }, to=player_id)

@socketio.on('join_game_room')
def handle_join_room(data):
    room_code = data.get('room_code', '').strip().upper()
    player_id = request.sid

    if room_code not in game_rooms:
        emit('error_message', {'msg': 'ROOM NOT FOUND'})
        return

    room = game_rooms[room_code]

    if len(room["players"]) >= 4:
        emit('error_message', {'msg': 'LOBBY FULL'})
        return

    if room["game_started"]:
        emit('error_message', {'msg': 'MATCH IN PROGRESS'})
        return

    room["players"].append(player_id)
    room["scores"][player_id] = 0
    join_room(room_code)

    emit('lobby_update', {
        'room_code': room_code,
        'player_count': len(room["players"]),
        'players_list': room["players"],
    }, to=room_code)

    emit('lobby_status_personal', {
        'is_host': False
    }, to=player_id)

@socketio.on('disconnect')
def handle_disconnect():
    player_id = request.sid
    for room_code, room_data in list(game_rooms.items()):
        if player_id in room_data["players"]:
            room_data["players"].remove(player_id)
            if player_id in room_data["scores"]:
                del room_data["scores"][player_id]
            leave_room(room_code)

            if len(room_data["players"]) == 0:
                del game_rooms[room_code]
                print(f"Room {room_code} empty. Deleted.")
            else:
                if player_id == room_data["host_id"]:
                    room_data["host_id"] = room_data["players"][0]
                    emit('lobby_status_personal', {'is_host': True}, to=room_data["host_id"])

                emit('lobby_update', {
                    'room_code': room_code,
                    'player_count': len(room_data["players"]),
                    'players_list': room_data["players"]
                }, to=room_code)

@socketio.on('start_game_request')
def handle_start_game(data):
    room_code = data.get('room_code')
    player_id = request.sid
    chosen_win_limit = int(data.get('points_to_win', 1000))

    if room_code not in game_rooms: return
    room = game_rooms[room_code]

    if player_id != room["host_id"]: return

    if len(room["players"]) < 2:
        emit('error_message', {'msg': 'NEED 2+ PLAYERS'})
        return

    room["game_started"] = True
    room["points_to_win"] = chosen_win_limit
    
    for pid in room["players"]:
        room["scores"][pid] = 0

    room["pacman_id"] = random.choice(room["players"])
    emit('play_cutscene', {'type': 'MATCH_START_INTRO'}, to=room_code)
    send_role_updates(room_code)

@socketio.on('pacman_ate_pellet')
def handle_pellet(data):
    room_code = data.get('room_code')
    if room_code not in game_rooms: return
    room = game_rooms[room_code]
    pacman_id = room["pacman_id"]
    if not pacman_id: return
    room["scores"][pacman_id] += 10
    if room["scores"][pacman_id] >= room["points_to_win"]:
        emit('change_menu_state', {'state': 'GAME_OVER', 'winner': pacman_id}, to=room_code)
        room["game_started"] = False
        return
    emit('score_update', {'scores': room["scores"]}, to=room_code)

@socketio.on('ghost_caught_pacman')
def handle_catch(data):
    room_code = data.get('room_code')
    ghost_id = request.sid
    if room_code not in game_rooms: return
    room = game_rooms[room_code]
    pacman_id = room["pacman_id"]
    if not pacman_id or ghost_id == pacman_id: return
    current_pacman_score = room["scores"][pacman_id]
    points_to_steal = min(200, current_pacman_score)
    room["scores"][pacman_id] -= points_to_steal
    room["scores"][ghost_id] += points_to_steal
    if room["scores"][ghost_id] >= room["points_to_win"]:
        emit('change_menu_state', {'state': 'GAME_OVER', 'winner': ghost_id}, to=room_code)
        room["game_started"] = False
        return
    emit('play_cutscene', {'type': 'ROLE_SWAP_ALERT', 'new_pacman': ghost_id, 'old_pacman': pacman_id}, to=room_code)
    room["pacman_id"] = ghost_id
    emit('score_update', {'scores': room["scores"]}, to=room_code)
    send_role_updates(room_code)

def send_role_updates(room_code):
    room = game_rooms[room_code]
    for pid in room["players"]:
        if pid == room["pacman_id"]: emit('assigned_role', {'role': 'PAC_MAN'}, to=pid)
        else: emit('assigned_role', {'role': 'GHOST'}, to=pid)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
