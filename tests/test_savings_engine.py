from datetime import date
from ai.savings_engine import build_savings_plan


def test_goal_plan_calculates_remaining_and_daily_savings():
    plan = build_savings_plan({
        'id': 7,
        'goal_name': 'Movie',
        'target_amount': 755,
        'saved_amount': 250,
        'target_date': date(2026, 12, 17),
    }, today=date(2026, 11, 17))

    assert plan['remaining_amount'] == 505.0
    assert plan['days_remaining'] == 30
    assert plan['daily_saving_required'] == 16.83
    assert plan['progress_percentage'] == 33.1
    assert plan['status'] == 'on_track'


def test_completed_goal_has_zero_required_savings():
    plan = build_savings_plan({
        'goal_name': 'Headphones',
        'target_amount': 1000,
        'saved_amount': 1100,
        'target_date': date(2026, 12, 17),
    }, today=date(2026, 11, 17))

    assert plan['remaining_amount'] == 0
    assert plan['daily_saving_required'] == 0
    assert plan['progress_percentage'] == 100
    assert plan['status'] == 'completed'
