"""Data tools exposed to the FinSight agent; every query is scoped to a user."""
from datetime import datetime
from db import query_one, query_all
from ai.savings_engine import build_savings_plan
from models.savings import get_goals
from ml import predictor


def get_financial_snapshot(user_id):
    user = query_one("SELECT monthly_income, currency FROM users WHERE id = %s", (user_id,))
    if not user:
        raise ValueError('User not found')

    now = datetime.now()
    totals = query_all(
        """SELECT category, COALESCE(SUM(es.amount), 0) AS total
           FROM expense_splits es
           JOIN expenses e ON e.id = es.expense_id
           WHERE es.user_id = %s AND YEAR(e.date) = %s AND MONTH(e.date) = %s
           GROUP BY e.category""",
        (user_id, now.year, now.month),
    )
    category_spending = {row['category']: round(float(row['total']), 2) for row in totals}
    monthly_spending = round(sum(category_spending.values()), 2)
    income = round(float(user['monthly_income'] or 0), 2)
    goals = get_goals(user_id, include_completed=False)
    reserved_for_goals = round(sum(max(float(g['target_amount']) - float(g['saved_amount']), 0) for g in goals), 2)

    history_rows = query_all(
        """SELECT DATE_FORMAT(e.date, '%Y-%m') AS month, SUM(es.amount) AS total
           FROM expense_splits es JOIN expenses e ON e.id = es.expense_id
           WHERE es.user_id = %s AND e.date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
           GROUP BY DATE_FORMAT(e.date, '%Y-%m') ORDER BY month""",
        (user_id,),
    )
    history = [float(row['total']) for row in history_rows]
    predicted = predictor.predict_next_month(history) if history else {'prediction': 0, 'confidence': 0, 'trend': 'stable'}

    return {
        'currency': user['currency'] or 'INR',
        'monthly_income': income,
        'current_month_spending': monthly_spending,
        'category_spending': category_spending,
        'estimated_unspent_income': round(max(income - monthly_spending, 0), 2),
        'active_savings_goals': len(goals),
        'remaining_goal_targets': reserved_for_goals,
        'predicted_next_month_spending': predicted,
        'data_month': now.strftime('%Y-%m'),
    }


def get_goal_plans(user_id):
    return [build_savings_plan(goal) for goal in get_goals(user_id, include_completed=False)]
