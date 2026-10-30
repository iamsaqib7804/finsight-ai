from datetime import datetime
from collections import defaultdict
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.expense import get_category_totals, get_monthly_totals
from models.budget import get_budgets
from ml import classifier, predictor, anomaly_detector

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/category-breakdown', methods=['GET'])
@login_required
def category_breakdown():
    month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    year, m = map(int, month.split('-'))
    totals = get_category_totals(current_user.id, year, m)
    grand = sum(totals.values()) or 1
    breakdown = [{'category': c, 'amount': round(a, 2), 'percentage': round(a / grand * 100, 1)} for c, a in sorted(totals.items(), key=lambda x: -x[1])]
    return jsonify({'breakdown': breakdown, 'total': round(grand, 2)})

@analytics_bp.route('/trends', methods=['GET'])
@login_required
def trends():
    months = request.args.get('months', 6, type=int)
    data = []
    now = datetime.now()
    totals = get_monthly_totals(current_user.id, months)
    for i, total in enumerate(totals):
        y = now.year
        m = now.month - (months - 1 - i)
        while m <= 0:
            m += 12
            y -= 1
        data.append({'month': f'{y}-{m:02d}', 'label': datetime(y, m, 1).strftime('%b %Y'), 'total': round(total, 2)})
    return jsonify({'trends': data})

@analytics_bp.route('/predict', methods=['GET'])
@login_required
def predict():
    try:
        months = 6
        totals = get_monthly_totals(current_user.id, months)

        if all(t == 0 for t in totals):
            now = datetime.now()
            cats = get_category_totals(current_user.id, now.year, now.month)
            current_total = sum(cats.values())
            if current_total > 0:
                totals = [0, 0, 0, 0, 0, current_total]

        total_pred = predictor.predict_next_month(totals)

        now = datetime.now()
        category_history = defaultdict(list)
        categories_list = getattr(classifier, 'CATEGORIES', ['Food', 'Travel', 'Shopping', 'Bills', 'Entertainment', 'Other'])

        for i in range(months - 1, -1, -1):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            cats = get_category_totals(current_user.id, y, m)
            for c in categories_list:
                category_history[c].append(cats.get(c, 0.0))

        cat_pred = predictor.predict_category_wise(dict(category_history))

        return jsonify({
            'total_prediction': total_pred,
            'category_predictions': cat_pred,
            'history': totals,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/anomalies', methods=['GET'])
@login_required
def anomalies():
    from db import query_all
    rows = query_all(
        """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
           FROM expenses e JOIN users u ON e.paid_by_id = u.id
           WHERE e.paid_by_id = %s AND e.is_anomaly = 1
           ORDER BY e.date DESC LIMIT 20""",
        (current_user.id,)
    )
    from models.expense import _hydrate
    return jsonify({'anomalies': [_hydrate(r) for r in rows]})

@analytics_bp.route('/risk', methods=['GET'])
@login_required
def risk():
    month = datetime.now().strftime('%Y-%m')
    budgets = get_budgets(current_user.id, month)
    risk_list = []
    for b in budgets:
        r = anomaly_detector.get_risk_level(b['spent'], b['limit'])
        risk_list.append({'category': b['category'], **r})
    return jsonify({'risk': risk_list})

@analytics_bp.route('/suggestions', methods=['GET'])
@login_required
def suggestions():
    month = datetime.now().strftime('%Y-%m')
    budgets = get_budgets(current_user.id, month)
    suggestions = []
    for b in budgets:
        pct = b['percentage']
        if pct >= 100:
            suggestions.append({'type': 'danger', 'category': b['category'], 'message': f"You've exceeded your {b['category']} budget by ₹{b['spent'] - b['limit']:.0f}."})
        elif pct >= 80:
            suggestions.append({'type': 'warn', 'category': b['category'], 'message': f"Your {b['category']} budget is {pct}% used."})
    if not suggestions:
        suggestions.append({'type': 'info', 'message': 'Great job! All budgets are within healthy limits.'})
    return jsonify({'suggestions': suggestions})