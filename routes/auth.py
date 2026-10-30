import re
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from models.user import get_user_by_email, create_user
from app import limiter
from config import Config

auth_bp = Blueprint('auth', __name__)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

@auth_bp.route('/register', methods=['POST'])
@limiter.limit(Config.RATELIMIT_REGISTER)
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()[:100]
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    if not EMAIL_RE.match(email):
        return jsonify({'error': 'Invalid email format'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 409
    user = create_user(name=name or email.split('@')[0], email=email, password=password, monthly_income=max(0, float(data.get('monthly_income') or 0)))
    login_user(user, remember=True)
    return jsonify({'message': 'Registered', 'user': user.to_dict()}), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit(Config.RATELIMIT_LOGIN)
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    user = get_user_by_email(email)
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    login_user(user, remember=True)
    return jsonify({'message': 'Logged in', 'user': user.to_dict()})

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out'})

@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    return jsonify(current_user.to_dict())

@auth_bp.route('/me', methods=['PUT'])
@login_required
def update_me():
    from db import execute
    data = request.get_json() or {}
    name = data.get('name')
    income = data.get('monthly_income')
    if name is not None:
        name = name.strip()[:100]
        if name:
            parts = [p for p in name.split() if p]
            initials = ''.join(p[0].upper() for p in parts[:2]) or 'U'
            execute("UPDATE users SET name = %s, avatar_initials = %s WHERE id = %s", (name, initials, current_user.id))
            current_user.name = name
            current_user.avatar_initials = initials
    if income is not None:
        try:
            income = max(0, float(income))
            execute("UPDATE users SET monthly_income = %s WHERE id = %s", (income, current_user.id))
            current_user.monthly_income = income
        except (ValueError, TypeError):
            pass
    return jsonify({'message': 'Updated', 'user': current_user.to_dict()})

@auth_bp.route('/login-page')
def login_page():
    if current_user.is_authenticated:
        return redirect('/')
    return render_template('login.html')