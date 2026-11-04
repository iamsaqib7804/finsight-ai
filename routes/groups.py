from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.group import (
    create_group, get_group, get_user_groups, is_member, is_admin,
    add_member, remove_member, delete_group, get_group_activities,
    get_group_leaderboard, get_group_heatmap, get_group_story,
    log_activity, get_group_member_ids,
)
from models.user import get_user_by_email, get_users_by_ids
from models.expense import get_group_expenses
from utils.settlement_calc import calculate_group_balances, simplify_debts
from sockets.events import emit_to_group
from db import query_one, query_all, execute
from config import Config
from models.group import get_user_groups
from db import query_all

groups_bp = Blueprint('groups', __name__)

@groups_bp.route('/', methods=['GET'])
@login_required
def list_groups():
    return jsonify({'groups': get_user_groups(current_user.id)})

@groups_bp.route('/', methods=['POST'])
@login_required
def create():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()[:100]
    if not name:
        return jsonify({'error': 'Name required'}), 400
    count = query_one("SELECT COUNT(*) AS c FROM group_members WHERE user_id = %s", (current_user.id,))
    if count and count['c'] >= Config.MAX_GROUPS_PER_USER:
        return jsonify({'error': f'Max {Config.MAX_GROUPS_PER_USER} groups allowed'}), 400
    group = create_group(name=name, description=(data.get('description') or '')[:255], creator_id=current_user.id)
    for email in (data.get('member_emails') or [])[:20]:
        u = get_user_by_email((email or '').strip().lower())
        if u and u.id != current_user.id:
            if add_member(group['id'], u.id):
                log_activity(group['id'], current_user.id, 'member_added', {'member_name': u.name, 'member_id': u.id})
    return jsonify({'group': get_group(group['id'])}), 201

@groups_bp.route('/<int:gid>', methods=['GET'])
@login_required
def detail(gid):
    if not is_member(gid, current_user.id):
        return jsonify({'error': 'Not a member'}), 403
    g = get_group(gid)
    if not g:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(g)

@groups_bp.route('/<int:gid>/dashboard', methods=['GET'])
@login_required
def dashboard(gid):
    if not is_member(gid, current_user.id):
        return jsonify({'error': 'Not a member'}), 403
    g = get_group(gid)
    balances = calculate_group_balances(gid)
    suggested = simplify_debts(balances)
    leaderboard = get_group_leaderboard(gid)
    activities = get_group_activities(gid, limit=20)
    heatmap = get_group_heatmap(gid, weeks=12)
    story = get_group_story(gid)
    expenses = get_group_expenses(gid)[:50]
    users = get_users_by_ids(list(balances.keys()))
    balance_list = [{'user': users.get(uid, {'id': uid, 'name': 'Unknown'}), 'net': amt} for uid, amt in balances.items()]
    tx_list = [{'from_user': users.get(t['from_user'], {'id': t['from_user']}), 'to_user': users.get(t['to_user'], {'id': t['to_user']}), 'amount': t['amount']} for t in suggested]
    return jsonify({
        'group': g, 'balances': balance_list,
        'suggested_settlements': tx_list, 'leaderboard': leaderboard,
        'activities': activities, 'heatmap': heatmap, 'story': story,
        'expenses': expenses,
    })

@groups_bp.route('/<int:gid>/members', methods=['POST'])
@login_required
def add(gid):
    if not is_member(gid, current_user.id):
        return jsonify({'error': 'Not a member'}), 403
    count = query_one("SELECT COUNT(*) AS c FROM group_members WHERE group_id = %s", (gid,))
    if count and count['c'] >= Config.MAX_GROUP_MEMBERS:
        return jsonify({'error': f'Max {Config.MAX_GROUP_MEMBERS} members allowed'}), 400
    data = request.get_json() or {}
    u = get_user_by_email((data.get('email') or '').strip().lower())
    if not u:
        return jsonify({'error': 'User not found'}), 404
    if not add_member(gid, u.id):
        return jsonify({'error': 'Already a member'}), 409
    log_activity(gid, current_user.id, 'member_added', {'member_name': u.name, 'member_id': u.id})
    emit_to_group(gid, 'member_added', {'group_id': gid, 'user': u.to_dict()})
    return jsonify({'message': 'Added', 'user': u.to_dict()}), 201

@groups_bp.route('/<int:gid>/members/<int:uid>', methods=['DELETE'])
@login_required
def remove(gid, uid):
    if not is_admin(gid, current_user.id) and uid != current_user.id:
        return jsonify({'error': 'Only admins can remove others'}), 403
    execute("DELETE es FROM expense_splits es JOIN expenses e ON es.expense_id = e.id WHERE e.group_id = %s AND es.user_id = %s", (gid, uid))
    remove_member(gid, uid)
    log_activity(gid, current_user.id, 'member_removed', {'member_id': uid})
    emit_to_group(gid, 'member_removed', {'group_id': gid, 'user_id': uid})
    return jsonify({'message': 'Removed'})

@groups_bp.route('/<int:gid>', methods=['DELETE'])
@login_required
def delete(gid):
    if not is_admin(gid, current_user.id):
        return jsonify({'error': 'Only admin can delete'}), 403
    delete_group(gid)
    return jsonify({'message': 'Deleted'})

@groups_bp.route('/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Fetch recent activities from all groups the user is a member of."""
    groups = get_user_groups(current_user.id)
    if not groups:
        return jsonify({'notifications': [], 'unread_count': 0})
    
    group_ids = [g['id'] for g in groups]
    placeholders = ','.join(['%s'] * len(group_ids))
    
    # ⭐ Fetch recent activities from these groups
    sql = f"""
        SELECT ga.*, u.name AS user_name, u.avatar_initials, g.name AS group_name
        FROM group_activities ga
        JOIN users u ON ga.user_id = u.id
        JOIN groups_table g ON ga.group_id = g.id
        WHERE ga.group_id IN ({placeholders})
        AND ga.user_id != %s  -- Don't show user their own actions
        ORDER BY ga.created_at DESC
        LIMIT 20
    """
    params = group_ids + [current_user.id]
    
    rows = query_all(sql, tuple(params))
    
    # Format the activities
    import json
    from datetime import datetime
    now = datetime.now()
    notifications = []
    
    for r in rows:
        delta = now - r['created_at']
        if delta.days > 0: time_ago = f"{delta.days}d ago"
        elif delta.seconds > 3600: time_ago = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60: time_ago = f"{delta.seconds // 60}m ago"
        else: time_ago = "Just now"
        
        try:
            meta = json.loads(r['meta']) if r['meta'] else {}
        except:
            meta = {}
            
        notifications.append({
            'id': r['id'],
            'user': r['user_name'],
            'avatar': r['avatar_initials'] or 'U',
            'action': r['action'],
            'meta': meta,
            'group_name': r['group_name'],
            'time_ago': time_ago
        })

    return jsonify({'notifications': notifications, 'unread_count': len(notifications)})
