from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from db import query_one, query_all, execute

class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.name = row['name']
        self.email = row['email']
        self.password_hash = row['password_hash']
        self.avatar_initials = row['avatar_initials'] or 'U'
        self.monthly_income = float(row['monthly_income'] or 0)
        self.currency = row['currency'] or 'INR'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email, 'avatar': self.avatar_initials, 'monthly_income': self.monthly_income, 'currency': self.currency}

def get_user_by_id(user_id):
    row = query_one("SELECT * FROM users WHERE id = %s", (user_id,))
    return User(row) if row else None

def get_user_by_email(email):
    row = query_one("SELECT * FROM users WHERE email = %s", (email,))
    return User(row) if row else None

def create_user(name, email, password, monthly_income=0):
    hash_pw = generate_password_hash(password)
    parts = [p for p in name.split() if p]
    initials = ''.join(p[0].upper() for p in parts[:2]) or 'U'
    user_id = execute("INSERT INTO users (name, email, password_hash, avatar_initials, monthly_income) VALUES (%s, %s, %s, %s, %s)", (name, email, hash_pw, initials, monthly_income))
    return get_user_by_id(user_id)

def get_users_by_ids(user_ids):
    if not user_ids:
        return {}
    placeholders = ','.join(['%s'] * len(user_ids))
    rows = query_all(f"SELECT * FROM users WHERE id IN ({placeholders})", tuple(user_ids))
    return {r['id']: {'id': r['id'], 'name': r['name'], 'email': r['email'], 'avatar': r['avatar_initials'] or 'U'} for r in rows}