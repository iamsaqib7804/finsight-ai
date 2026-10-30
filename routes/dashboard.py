from datetime import datetime
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from db import query_all, query_one
from ml import predictor

dashboard_bp = Blueprint('dashboard', __name__)

def _get_user_group_ids(user_id):
    rows = query_all("SELECT group_id FROM group_members WHERE user_id = %s", (user_id,))
    return [r['group_id'] for r in rows]

def _hydrate_expense(e):
    e['date'] = e['date'].strftime('%d %b %Y') if e['date'] else ''
    e['ai_confidence'] = (f"{int(float(e['ai_confidence']) * 100)}%" if e['ai_confidence'] else '—')
    e['is_anomaly'] = bool(e['is_anomaly'])
    e['amount'] = float(e['amount'])
    e['paid_by'] = {'id': e['paid_by_id'], 'name': e.get('paid_by_name', ''), 'avatar': e.get('paid_by_avatar', 'U') or 'U'}
    return e

@dashboard_bp.route('/', methods=['GET'])
@login_required
def summary():
    month = datetime.now().strftime('%Y-%m')
    year, m = map(int, month.split('-'))
    group_ids = _get_user_group_ids(current_user.id)
    if group_ids:
        placeholders = ','.join(['%s'] * len(group_ids))
        sql = f"""SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
            FROM expenses e JOIN users u ON e.paid_by_id = u.id
            WHERE YEAR(e.date) = %s AND MONTH(e.date) = %s
              AND ((e.group_id IS NULL AND e.paid_by_id = %s) OR (e.group_id IN ({placeholders})))
            ORDER BY e.date DESC"""
        params = [year, m, current_user.id] + group_ids
    else:
        sql = """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
            FROM expenses e JOIN users u ON e.paid_by_id = u.id
            WHERE YEAR(e.date) = %s AND MONTH(e.date) = %s AND e.paid_by_id = %s AND e.group_id IS NULL
            ORDER BY e.date DESC"""
        params = [year, m, current_user.id]
    expense_rows = query_all(sql, tuple(params))
    expenses = [_hydrate_expense(e) for e in expense_rows]

    total_exp = 0.0
    category_totals = {}
    for e in expenses:
        if e['group_id'] is None:
            share = e['amount']
        else:
            split_row = query_one("SELECT amount FROM expense_splits WHERE expense_id = %s AND user_id = %s", (e['id'], current_user.id))
            share = float(split_row['amount']) if split_row else 0
        total_exp += share
        cat = e['category'] or 'Other'
        category_totals[cat] = category_totals.get(cat, 0) + share

    income = current_user.monthly_income or 0
    balance = income - total_exp
    savings_rate = round((balance / income) * 100, 1) if income else 0

    grand = total_exp or 1
    breakdown = [{'category': c, 'amount': round(a, 2), 'percentage': round(a / grand * 100, 1)} for c, a in sorted(category_totals.items(), key=lambda x: -x[1])]

    from models.budget import get_budgets
    budgets = get_budgets(current_user.id, month)

    from models.expense import get_monthly_totals
    monthly_totals = get_monthly_totals(current_user.id, 6)
    if all(t == 0 for t in monthly_totals):
        monthly_totals = [total_exp] * 6
    prediction = predictor.predict_next_month(monthly_totals)

    from models.group import get_user_groups
    groups = get_user_groups(current_user.id)

    from utils.settlement_calc import get_pending_settlements_for_user
    from models.user import get_users_by_ids
    pending = get_pending_settlements_for_user(current_user.id)
    ids = {x['user_id'] for x in pending['to_pay'] + pending['to_receive']}
    users = get_users_by_ids(list(ids))
    for x in pending['to_pay']: x['user'] = users.get(x['user_id'], {'name': 'Unknown'})
    for x in pending['to_receive']: x['user'] = users.get(x['user_id'], {'name': 'Unknown'})

    alerts = []
    for b in budgets:
        if b['status'] == 'danger':
            alerts.append({'type': 'danger', 'category': b['category'], 'message': f"{b['category']} budget exceeded!"})
        elif b['status'] == 'warn':
            alerts.append({'type': 'warning', 'category': b['category'], 'message': f"{b['category']} budget is {b['percentage']}% used."})

    recent = expenses[:5]

    return jsonify({
        'month': month, 'income': income,
        'total_expenses': round(total_exp, 2),
        'balance': round(balance, 2),
        'savings_rate': savings_rate,
        'category_breakdown': breakdown,
        'budgets': budgets, 'prediction': prediction,
        'groups': groups, 'pending_settlements': pending,
        'alerts': alerts, 'recent_transactions': recent,
    })