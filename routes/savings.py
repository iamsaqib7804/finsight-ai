from datetime import date
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from models.savings import (
    create_goal,
    get_goal,
    get_goals,
    add_contribution,
    get_contributions,
    update_goal,
    delete_goal,
)
from ai.savings_engine import build_savings_plan
from ai.financial_tools import get_financial_snapshot, get_goal_plans
from sockets.events import emit_to_user
from extensions import limiter

savings_bp = Blueprint('savings', __name__)


def _money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Amount must be a valid number')
    if not amount.is_finite() or amount <= 0 or amount > Decimal('10000000'):
        raise ValueError('Amount must be greater than 0 and no more than 10000000')
    return amount.quantize(Decimal('0.01'))


def _serialize_goal(goal):
    result = dict(goal)
    for key in ('target_amount', 'saved_amount'):
        result[key] = round(float(result[key]), 2)
    for key in ('target_date',):
        if hasattr(result[key], 'isoformat'):
            result[key] = result[key].isoformat()
    for key in ('created_at', 'updated_at'):
        if result.get(key) and hasattr(result[key], 'isoformat'):
            result[key] = result[key].isoformat(sep=' ')
    return result


@savings_bp.route('/goals', methods=['GET'])
@login_required
def list_goals():
    include_completed = request.args.get('include_completed', 'true').lower() != 'false'
    goals = get_goals(current_user.id, include_completed=include_completed)
    serialized = [_serialize_goal(g) for g in goals]
    plans = [build_savings_plan(g) for g in goals]
    return jsonify({'goals': serialized, 'plans': plans})


@savings_bp.route('/goals', methods=['POST'])
@login_required
def create_savings_goal():
    data = request.get_json(silent=True) or {}
    name = (data.get('goal_name') or '').strip()
    if not name or len(name) > 100:
        return jsonify({'error': 'Goal name is required (maximum 100 characters)'}), 400
    try:
        target_amount = _money(data.get('target_amount'))
        target_date = date.fromisoformat(str(data.get('target_date', '')))
    except ValueError as exc:
        return jsonify({'error': str(exc) if 'Amount' in str(exc) else 'Target date must use YYYY-MM-DD format'}), 400
    if target_date < date.today():
        return jsonify({'error': 'Target date cannot be in the past'}), 400

    notes = (data.get('notes') or '').strip()[:500]
    goal_id = create_goal(current_user.id, name, target_amount, target_date, notes or None)
    goal = get_goal(goal_id, current_user.id)
    plan = build_savings_plan(goal)
    emit_to_user(current_user.id, 'savings_goal_created', {'goal': _serialize_goal(goal), 'plan': plan})
    return jsonify({'goal': _serialize_goal(goal), 'plan': plan, 'message': 'Savings goal created'}), 201


@savings_bp.route('/goals/<int:goal_id>', methods=['PUT'])
@login_required
def edit_savings_goal(goal_id):
    data = request.get_json(silent=True) or {}

    name = (data.get('goal_name') or '').strip()
    if not name or len(name) > 100:
        return jsonify({
            'error': 'Goal name is required (maximum 100 characters)'
        }), 400

    try:
        target_amount = _money(data.get('target_amount'))
        target_date = date.fromisoformat(str(data.get('target_date', '')))
    except (ValueError, TypeError):
        return jsonify({
            'error': 'Provide a valid target amount and YYYY-MM-DD target date'
        }), 400

    if target_date < date.today():
        return jsonify({'error': 'Target date cannot be in the past'}), 400

    notes = (data.get('notes') or '').strip()[:500]

    try:
        goal = update_goal(
            current_user.id,
            goal_id,
            name,
            target_amount,
            target_date,
            notes or None
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not goal:
        return jsonify({'error': 'Savings goal not found'}), 404

    payload = {
        'goal': _serialize_goal(goal),
        'plan': build_savings_plan(goal)
    }

    emit_to_user(current_user.id, 'savings_goal_updated', payload)

    return jsonify({
        **payload,
        'message': 'Savings goal updated successfully'
    })


@savings_bp.route('/goals/<int:goal_id>', methods=['DELETE'])
@login_required
def remove_savings_goal(goal_id):
    deleted = delete_goal(goal_id, current_user.id)

    if not deleted:
        return jsonify({'error': 'Savings goal not found'}), 404

    emit_to_user(current_user.id, 'savings_goal_deleted', {
        'goal_id': goal_id
    })

    return jsonify({
        'message': 'Savings goal and its contribution history deleted',
        'goal_id': goal_id
    })

@savings_bp.route('/goals/<int:goal_id>/contributions', methods=['GET'])
@login_required
def contribution_history(goal_id):
    rows = get_contributions(goal_id, current_user.id)
    if rows is None:
        return jsonify({'error': 'Savings goal not found'}), 404
    contributions = []
    for row in rows:
        item = dict(row)
        item['amount'] = round(float(item['amount']), 2)
        if item.get('created_at') and hasattr(item['created_at'], 'isoformat'):
            item['created_at'] = item['created_at'].isoformat(sep=' ')
        contributions.append(item)
    return jsonify({'contributions': contributions})


@savings_bp.route('/goals/<int:goal_id>/contributions', methods=['POST'])
@login_required
def contribute(goal_id):
    data = request.get_json(silent=True) or {}
    try:
        amount = _money(data.get('amount'))
        goal = add_contribution(goal_id, current_user.id, amount, (data.get('note') or '').strip()[:255] or None)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not goal:
        return jsonify({'error': 'Savings goal not found'}), 404

    plan = build_savings_plan(goal)
    payload = {'goal': _serialize_goal(goal), 'plan': plan}
    emit_to_user(current_user.id, 'savings_goal_updated', payload)
    return jsonify({**payload, 'message': 'Savings contribution recorded'}), 201


@savings_bp.route('/goals/<int:goal_id>/plan', methods=['GET'])
@login_required
def goal_plan(goal_id):
    goal = get_goal(goal_id, current_user.id)
    if not goal:
        return jsonify({'error': 'Savings goal not found'}), 404
    return jsonify({'plan': build_savings_plan(goal)})


@savings_bp.route('/agent/snapshot', methods=['GET'])
@login_required
def agent_snapshot():
    """Read-only financial context for the agent; never exposes another user's data."""
    return jsonify({'snapshot': get_financial_snapshot(current_user.id), 'savings_plans': get_goal_plans(current_user.id)})


@savings_bp.route('/agent/ask', methods=['POST'])
@login_required
@limiter.limit('10 per minute')
def agent_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question or len(question) > 2000:
        return jsonify({'error': 'Question is required (maximum 2000 characters)'}), 400
    try:
        from ai.agent import ask_financial_agent
        answer = ask_financial_agent(current_user.id, question)
        return jsonify({'answer': answer, 'agent': 'FinSight', 'tools_available': ['get_my_financial_snapshot', 'get_my_savings_goals', 'recommend_my_monthly_budget']})
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception(
            'FinSight agent request failed: %s', type(exc).__name__
        )

        return jsonify({
            'error': 'The financial agent could not complete this request. Please try again.'
        }), 502


@savings_bp.route('/agent/budget-recommendation', methods=['POST'])
@login_required
def agent_budget_recommendation():
    data = request.get_json(silent=True) or {}
    try:
        budget = _money(data.get('monthly_budget'))
        reserve = Decimal(str(data.get('savings_reserve', 0))).quantize(Decimal('0.01'))
        if not reserve.is_finite() or reserve < 0 or reserve > budget:
            raise ValueError('Savings reserve must be between zero and the monthly budget')
        from ai.budget_optimizer import recommend_budget
        recommendation = recommend_budget(current_user.id, budget, reserve)
        return jsonify({'recommendation': recommendation})
    except (ValueError, InvalidOperation) as exc:
        return jsonify({'error': str(exc)}), 400

