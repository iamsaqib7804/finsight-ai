from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.budget import upsert_budget, get_budgets, delete_budget, recalculate_spent
from db import query_one, execute

budgets_bp = Blueprint('budgets', __name__)

@budgets_bp.route('/', methods=['GET'])
@login_required
def list_budgets():
    month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    _maybe_rollover(current_user.id, month)
    budgets = get_budgets(current_user.id, month)
    for b in budgets:
        recalculate_spent(current_user.id, b['category'], month)
    budgets = get_budgets(current_user.id, month)
    return jsonify({'budgets': budgets, 'month': month})

def _maybe_rollover(user_id, month):
    existing = query_one("SELECT COUNT(*) AS c FROM budgets WHERE user_id = %s AND month = %s", (user_id, month))
    if existing and existing['c'] > 0:
        return
    y, m = map(int, month.split('-'))
    prev_m = m - 1 if m > 1 else 12
    prev_y = y if m > 1 else y - 1
    prev_month = f"{prev_y}-{prev_m:02d}"
    from db import query_all
    prev_budgets = query_all("SELECT category, limit_amount FROM budgets WHERE user_id = %s AND month = %s", (user_id, prev_month))
    for pb in prev_budgets:
        try:
            execute("INSERT IGNORE INTO budgets (user_id, category, limit_amount, month, spent_amount) VALUES (%s, %s, %s, %s, 0)", (user_id, pb['category'], pb['limit_amount'], month))
        except Exception:
            pass

@budgets_bp.route('/', methods=['POST'])
@login_required
def create():
    data = request.get_json() or {}
    month = data.get('month') or datetime.now().strftime('%Y-%m')
    category = (data.get('category') or '').strip()[:50]
    limit = float(data.get('limit') or 0)
    if not category or limit <= 0:
        return jsonify({'error': 'Category and positive limit required'}), 400
    bid = upsert_budget(user_id=current_user.id, category=category, limit_amount=limit, month=month, alert_threshold=float(data.get('alert_threshold', 0.80)))
    recalculate_spent(current_user.id, category, month)
    return jsonify({'id': bid, 'message': 'Saved'}), 201

@budgets_bp.route('/<int:bid>', methods=['DELETE'])
@login_required
def remove(bid):
    if not delete_budget(bid, current_user.id):
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'message': 'Deleted'})