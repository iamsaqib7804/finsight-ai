import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'finsight_ai')

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False # Production (HTTPS) mein True karna

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf'}

    RATELIMIT_DEFAULT = "200 per minute"
    RATELIMIT_LOGIN = "5 per minute"
    RATELIMIT_REGISTER = "3 per minute"
    RATELIMIT_EXPENSE = "30 per minute"
    RATELIMIT_UPLOAD = "10 per minute"

    MAX_GROUP_MEMBERS = 50
    MAX_GROUPS_PER_USER = 50
    MAX_EXPENSE_AMOUNT = 10_000_000
    MAX_COMMENT_LENGTH = 1000
    MAX_EXPENSES_PER_USER = 10_000

    LOG_FILE = 'logs/finsight.log'
    LOG_LEVEL = 'INFO'