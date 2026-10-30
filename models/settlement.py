from db import query_one, query_all, execute

def create_settlement(payer_id, receiver_id, amount, group_id=None, notes=''):
    sid = execute("INSERT INTO settlements (payer_id, receiver_id, amount, group_id, notes) VALUES (%s, %s, %s, %s, %s)", (payer_id, receiver_id, amount, group_id, notes))
    return get_settlement(sid)

def get_settlement(sid):
    row = query_one("""SELECT s.*, p.name AS payer_name, p.avatar_initials AS payer_avatar, r.name AS receiver_name, r.avatar_initials AS receiver_avatar FROM settlements s JOIN users p ON s.payer_id = p.id JOIN users r ON s.receiver_id = r.id WHERE s.id = %s""", (sid,))
    if not row: return None
    return _hydrate(row)

def _hydrate(row):
    row['amount'] = float(row['amount'])
    row['created_at'] = row['created_at'].strftime('%d %b %Y') if row['created_at'] else ''
    row['settled_at'] = row['settled_at'].strftime('%d %b %Y') if row['settled_at'] else None
    row['payer'] = {'id': row['payer_id'], 'name': row['payer_name'], 'avatar': row['payer_avatar'] or 'U'}
    row['receiver'] = {'id': row['receiver_id'], 'name': row['receiver_name'], 'avatar': row['receiver_avatar'] or 'U'}
    row['group_id'] = row.get('group_id')
    row['status'] = row.get('status', 'pending')
    return row

def mark_complete(sid, user_id):
    row = query_one("SELECT payer_id, receiver_id FROM settlements WHERE id = %s", (sid,))
    if not row or user_id not in (row['payer_id'], row['receiver_id']):
        return None
    execute("UPDATE settlements SET status = 'completed', settled_at = NOW() WHERE id = %s", (sid,))
    return get_settlement(sid)

def list_settlements(user_id):
    rows = query_all("""SELECT s.*, p.name AS payer_name, p.avatar_initials AS payer_avatar, r.name AS receiver_name, r.avatar_initials AS receiver_avatar FROM settlements s JOIN users p ON s.payer_id = p.id JOIN users r ON s.receiver_id = r.id WHERE s.payer_id = %s OR s.receiver_id = %s ORDER BY s.created_at DESC""", (user_id, user_id))
    return [_hydrate(r) for r in rows]