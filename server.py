import os
from flask import Flask
from flask_socketio import SocketIO, emit

app = Flask(__name__)

socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def home():
    return "Pac-Man Vs. Server is running on Python 3.14!"

@socketio.on('connect')
def handle_connect():
    print("--- A PLAYER HAS CONNECTED TO THE SERVER! ---")
    emit('server_message', {'msg': 'Welcome to the Pac-Man Vs. Server!'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
