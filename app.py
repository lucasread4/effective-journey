from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

# Store draft rooms and their state
draft_rooms = {}

# Sample player data (same as before)
PLAYERS_DATA = {
    "czech": {"name": "Czech Republic", "flag": "🇨🇿", "players": [...]},
    "mexico": {"name": "Mexico", "flag": "🇲🇽", "players": [...]},
    "brazil": {"name": "Brazil", "flag": "🇧🇷", "players": [...]},
    # ... add all your team data here
}

def build_player_list(team_key="all"):
    players = []
    if team_key == "all":
        for key, team in PLAYERS_DATA.items():
            for player in team["players"]:
                players.append({
                    'id': f"{key}_{player['name'].replace(' ', '_')}",
                    'name': player['name'],
                    'position': player['position'],
                    'club': player['club'],
                    'team': team['name'],
                    'teamFlag': team['flag']
                })
    return players

@app.route('/')
def index():
    return render_template('draft.html')

@socketio.on('join_room')
def handle_join_room(data):
    room = data['room']
    username = data['username']
    join_room(room)
    
    # Initialize room if it doesn't exist
    if room not in draft_rooms:
        draft_rooms[room] = {
            'players': build_player_list("all"),
            'drafted_ids': [],
            'users': {},
            'created_at': datetime.now(),
            'current_team': "all"
        }
    
    # Add user to room
    draft_rooms[room]['users'][request.sid] = username
    
    # Send current state to the new user
    emit('room_state', {
        'players': draft_rooms[room]['players'],
        'drafted_ids': draft_rooms[room]['drafted_ids'],
        'users': list(draft_rooms[room]['users'].values()),
        'current_team': draft_rooms[room]['current_team']
    }, room=request.sid)
    
    # Broadcast updated user list to everyone
    emit('users_update', {
        'users': list(draft_rooms[room]['users'].values())
    }, room=room)
    
    print(f"{username} joined room {room}")

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data['room']
    username = draft_rooms.get(room, {}).get('users', {}).pop(request.sid, None)
    leave_room(room)
    
    if room in draft_rooms and username:
        emit('users_update', {
            'users': list(draft_rooms[room]['users'].values())
        }, room=room)
        
        # Clean up empty rooms
        if len(draft_rooms[room]['users']) == 0:
            del draft_rooms[room]

@socketio.on('draft_player')
def handle_draft(data):
    room = data['room']
    player_id = data['player_id']
    username = data['username']
    
    if room in draft_rooms:
        room_data = draft_rooms[room]
        
        # Check if player is already drafted
        if player_id in room_data['drafted_ids']:
            emit('error', {'message': f'{player_id} already drafted!'}, room=request.sid)
            return
        
        # Add to drafted list
        room_data['drafted_ids'].append(player_id)
        
        # Broadcast to everyone in the room
        emit('player_drafted', {
            'player_id': player_id,
            'username': username,
            'drafted_ids': room_data['drafted_ids']
        }, room=room)

@socketio.on('remove_player')
def handle_remove(data):
    room = data['room']
    player_id = data['player_id']
    username = data['username']
    
    if room in draft_rooms:
        room_data = draft_rooms[room]
        
        if player_id in room_data['drafted_ids']:
            room_data['drafted_ids'].remove(player_id)
            
            emit('player_removed', {
                'player_id': player_id,
                'username': username,
                'drafted_ids': room_data['drafted_ids']
            }, room=room)

@socketio.on('reset_draft')
def handle_reset(data):
    room = data['room']
    username = data['username']
    
    if room in draft_rooms:
        draft_rooms[room]['drafted_ids'] = []
        
        emit('draft_reset', {
            'username': username,
            'drafted_ids': []
        }, room=room)

@socketio.on('random_pick')
def handle_random_pick(data):
    room = data['room']
    username = data['username']
    
    if room in draft_rooms:
        room_data = draft_rooms[room]
        available = [p for p in room_data['players'] if p['id'] not in room_data['drafted_ids']]
        
        if available:
            import random
            random_player = random.choice(available)
            room_data['drafted_ids'].append(random_player['id'])
            
            emit('player_drafted', {
                'player_id': random_player['id'],
                'username': f"{username} (Random)",
                'drafted_ids': room_data['drafted_ids']
            }, room=room)

@socketio.on('change_team')
def handle_team_change(data):
    room = data['room']
    team_key = data['team_key']
    
    if room in draft_rooms:
        new_players = build_player_list(team_key)
        draft_rooms[room]['players'] = new_players
        draft_rooms[room]['current_team'] = team_key
        draft_rooms[room]['drafted_ids'] = []  # Reset draft when switching teams
        
        emit('team_changed', {
            'players': new_players,
            'drafted_ids': [],
            'team_key': team_key
        }, room=room)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
