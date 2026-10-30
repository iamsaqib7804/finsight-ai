from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.settlement import create_settlement, mark_complete, list_settlements, get_settlement
from models.group import is_member, log_activity
from models.user import get_users_by_ids
from utils.settlement_calc import calculate_group_balances, simplify_debts, get_pending_settlements_for_user
from sockets.events import emit_to_user, emit_to_group
from db import query_one, query_all, execute
from app import limiter
from config import Config

settlements_bp = Blueprint('settlements', __name__)

@settlements_bp.route('/group/<int:gid>/balances', methods=['GET'])
@login_required
def group_balances(gid):
    if not is_member(gid, current_user.id):
        return jsonify({'error': 'Not a member'}), 403
    balances = calculate_group_balances(gid)
    suggested = simplify_debts(balances)
    users = get_users_by_ids(list(balances.keys()))
    balance_list = [{'user': users.get(uid, {'id': uid, 'name': 'Unknown'}), 'net': amt} for uid, amt in balances.items()]
    tx_list = [{'from_user': users.get(t['from_user'], {'id': t['from_user']}), 'to_user': users.get(t['to_user'], {'id': t['to_user']}), 'amount': t['amount']} for t in suggested]
    return jsonify({'balances': balance_list, 'suggested_settlements': tx_list})

@settlements_bp.route('/pending', methods=['GET'])
@login_required
def pending():
    p = get_pending_settlements_for_user(current_user.id)
    ids = {x['user_id'] for x in p['to_pay'] + p['to_receive']}
    users = get_users_by_ids(list(ids))
    for x in p['to_pay']: x['user'] = users.get(x['user_id'], {'name': 'Unknown'})
    for x in p['to_receive']: x['user'] = users.get(x['user_id'], {'name': 'Unknown'})
    return jsonify(p)

@settlements_bp.route('/incoming', methods=['GET'])
@login_required
def incoming():
    rows = query_all(
        """SELECT s.*, p.name AS payer_name, p.avatar_initials AS payer_avatar,
                  r.name AS receiver_name, r.avatar_initials AS receiver_avatar
           FROM settlements s
           JOIN users p ON s.payer_id = p.id
           JOIN users r ON s.receiver_id = r.id
           WHERE s.receiver_id = %s AND s.status = 'pending'
           ORDER BY s.created_at DESC""",
        (current_user.id,)
    )
    from models.settlement import _hydrate
    return jsonify({'incoming': [_hydrate(r) for r in rows]})

@settlements_bp.route('/outgoing', methods=['GET'])
@login_required
def outgoing():
    rows = query_all(
        """SELECT s.*, p.name AS payer_name, p.avatar_initials AS payer_avatar,
                  r.name AS receiver_name, r.avatar_initials AS receiver_avatar
           FROM settlements s
           JOIN users p ON s.payer_id = p.id
           JOIN users r ON s.receiver_id = r.id
           WHERE s.payer_id = %s AND s.status = 'pending'
           ORDER BY s.created_at DESC""",
        (current_user.id,)
    )
    from models.settlement import _hydrate
    return jsonify({'outgoing': [_hydrate(r) for r in rows]})

@settlements_bp.route('/', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def create():
    data = request.get_json() or {}
    receiver_id = int(data.get('receiver_id') or 0)
    amount = float(data.get('amount') or 0)
    group_id = data.get('group_id')
    
    if not receiver_id or amount <= 0:
        return jsonify({'error': 'Invalid data'}), 400
    if amount > Config.MAX_EXPENSE_AMOUNT:
        return jsonify({'error': f'Amount exceeds max'}), 400
    if receiver_id == current_user.id:
        return jsonify({'error': 'Cannot settle with yourself'}), 400

    receiver = query_one("SELECT id FROM users WHERE id = %s", (receiver_id,))
    if not receiver:
        return jsonify({'error': 'Receiver not found'}), 404

    if not group_id:
        common = query_all(
            """SELECT gm1.group_id FROM group_members gm1
               JOIN group_members gm2 ON gm1.group_id = gm2.group_id
               WHERE gm1.user_id = %s AND gm2.user_id = %s LIMIT 1""",
            (current_user.id, receiver_id)
        )
        if common:
            group_id = common[0]['group_id']

    if not group_id:
        return jsonify({'error': 'No common group found'}), 400

    m1 = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s", (group_id, current_user.id))
    m2 = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s", (group_id, receiver_id))
    if not m1 or not m2:
        return jsonify({'error': 'One or both users not in group'}), 403

    s = create_settlement(payer_id=current_user.id, receiver_id=receiver_id, amount=amount, group_id=group_id, notes=(data.get('notes') or '')[:255])
    log_activity(group_id, current_user.id, 'settlement_initiated', {'settlement_id': s['id'], 'amount': amount, 'receiver_id': receiver_id})
    
    emit_to_user(receiver_id, 'settlement_requested', s)
    return jsonify(s), 201

@settlements_bp.route('/<int:sid>/complete', methods=['POST'])
@login_required
def complete(sid):
    s = get_settlement(sid)
    if not s:
        return jsonify({'error': 'Not found'}), 404
        
    if s['status'] != 'pending':
        return jsonify({'error': 'Already processed'}), 400
        
    # SIRF RECEIVER HI CONFIRM KAR SAKTA HAI
    if s['receiver']['id'] != current_user.id:
        return jsonify({'error': 'Only the receiver can confirm this payment'}), 403

    updated = mark_complete(sid, current_user.id)
    if not updated:
        return jsonify({'error': 'Failed'}), 500
        
    group_id = updated.get('group_id')
    if group_id:
        log_activity(group_id, current_user.id, 'settlement_completed', {
            'settlement_id': updated['id'], 
            'amount': updated['amount'], 
            'payer_name': updated['payer']['name']
        })
        balances = calculate_group_balances(group_id)
        suggested = simplify_debts(balances)
        emit_to_group(group_id, 'settlement_completed', {
            'settlement': updated, 
            'balances': balances, 
            'suggested_settlements': suggested
        })
        
    emit_to_user(updated['payer']['id'], 'settlement_completed', updated)
    emit_to_user(updated['receiver']['id'], 'settlement_completed', updated)
    return jsonify(updated)

@settlements_bp.route('/<int:sid>/reject', methods=['POST'])
@login_required
def reject(sid):
    s = get_settlement(sid)
    if not s:
        return jsonify({'error': 'Not found'}), 404
    if s['status'] != 'pending':
        return jsonify({'error': 'Already processed'}), 400
    if s['receiver']['id'] != current_user.id:
        return jsonify({'error': 'Only the receiver can reject'}), 403
        
    execute("UPDATE settlements SET status = 'rejected' WHERE id = %s", (sid,))
    updated = get_settlement(sid)
    if updated.get('group_id'):
        log_activity(updated['group_id'], current_user.id, 'settlement_rejected', {'settlement_id': updated['id']})
    emit_to_user(updated['payer']['id'], 'settlement_rejected', updated)
    return jsonify(updated)

@settlements_bp.route('/', methods=['GET'])
@login_required
def list_all():
    return jsonify({'settlements': list_settlements(current_user.id)})

@settlements_bp.route('/remind/<int:target_user_id>', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def remind(target_user_id):
    target = query_one("SELECT id FROM users WHERE id = %s", (target_user_id,))
    if not target:
        return jsonify({'error': 'User not found'}), 404
    if target_user_id == current_user.id:
        return jsonify({'error': 'Cannot remind yourself'}), 400
    emit_to_user(target_user_id, 'payment_reminder', {'from': current_user.to_dict(), 'message': f'{current_user.name} is reminding you about a pending settlement.'})
    return jsonify({'message': 'Reminder sent'})