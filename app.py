import logging
import os
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

from flask import Flask, render_template, redirect, url_for, jsonify, request
from flask_login import LoginManager, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from db import init_db
from models.user import get_user_by_id
from sockets.events import init_socketio

os.makedirs('logs', exist_ok=True)
logging.basicConfig(filename=Config.LOG_FILE, level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login_page'

limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[Config.RATELIMIT_DEFAULT], storage_uri='memory://',enabled=not os.environ.get('PYTEST_CURRENT_TEST'))

socketio = init_socketio(app)

from routes import register_blueprints
register_blueprints(app)

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('auth.login_page'))

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return redirect('/')

@app.errorhandler(429)
def rate_limit(e):
    return jsonify({'error': 'Too many requests. Please slow down.'}), 429

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login_page'))
    return render_template('index.html', user=current_user.to_dict())

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'service': 'finsight-ai'})

@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def chrome_devtools():
    return jsonify({}), 200