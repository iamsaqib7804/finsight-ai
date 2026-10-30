import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
from app import app, socketio
from db import init_db

if __name__ == '__main__':
    print("🔧 Initializing database...")
    init_db()
    print("🚀 Starting FinSight AI on http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)