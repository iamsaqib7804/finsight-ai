from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_login import current_user

socketio = SocketIO(cors_allowed_origins='*', async_mode='eventlet')

def init_socketio(app):
    socketio.init_app(app)
    _register_events()
    return socketio

def _register_events():
    @socketio.on('connect')
    def on_connect():
        if current_user.is_authenticated:
            join_room(f'user_{current_user.id}')

    @socketio.on('join_group')
    def on_join_group(data):
        gid = data.get('group_id')
        if gid and current_user.is_authenticated:
            join_room(f'group_{gid}')

    @socketio.on('leave_group')
    def on_leave_group(data):
        gid = data.get('group_id')
        if gid:
            leave_room(f'group_{gid}')

def emit_to_group(group_id, event, data):
    try:
        socketio.emit(event, data, room=f'group_{group_id}')
    except Exception:
        pass

def emit_to_user(user_id, event, data):
    try:
        socketio.emit(event, data, room=f'user_{user_id}')
    except Exception:
        pass