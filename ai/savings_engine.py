"""Deterministic savings calculations. Money calculations stay outside the LLM."""
from datetime import date


def build_savings_plan(goal, today=None):
    today = today or date.today()
    target = goal['target_date']
    if hasattr(target, 'date'):
        target = target.date()
    if isinstance(target, str):
        target = date.fromisoformat(target)

    target_amount = round(float(goal['target_amount']), 2)
    saved_amount = round(float(goal['saved_amount']), 2)
    remaining = round(max(target_amount - saved_amount, 0), 2)
    days_remaining = max((target - today).days, 0)
    days_for_plan = max(days_remaining, 1)
    daily = round(remaining / days_for_plan, 2)
    weekly = round(remaining / max(days_for_plan / 7, 1 / 7), 2)
    progress = round(min(saved_amount / target_amount * 100, 100), 1) if target_amount else 0

    if remaining == 0:
        status = 'completed'
    elif days_remaining == 0:
        status = 'due_today'
    else:
        status = 'on_track'  # Actual pace is assessed once contribution history is available.

    return {
        'goal_id': goal.get('id'),
        'goal_name': goal['goal_name'],
        'target_amount': target_amount,
        'saved_amount': saved_amount,
        'remaining_amount': remaining,
        'target_date': target.isoformat(),
        'days_remaining': days_remaining,
        'daily_saving_required': daily,
        'weekly_saving_required': weekly,
        'progress_percentage': progress,
        'status': status,
    }
