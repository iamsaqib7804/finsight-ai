from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.expense import (
    create_expense_with_splits, get_expense, delete_expense,
    get_user_category_history, _hydrate, add_comment, get_comments,
    delete_comment, update_expense, count_user_expenses,
)
from models.budget import update_spent
from models.group import log_activity
from ml import classifier, anomaly_detector
from sockets.events import emit_to_group
from db import query_all, query_one, execute
from app import limiter
from config import Config

expenses_bp = Blueprint('expenses', __name__)

def _get_user_group_ids(user_id):
    rows = query_all("SELECT group_id FROM group_members WHERE user_id = %s", (user_id,))
    return [r['group_id'] for r in rows]

@expenses_bp.route('/', methods=['GET'])
@login_required
def list_expenses():
    category = request.args.get('category')
    search = request.args.get('search')
    limit = min(int(request.args.get('limit', 500)), 1000)
    group_ids = _get_user_group_ids(current_user.id)
    
    if group_ids:
        placeholders = ','.join(['%s'] * len(group_ids))
        sql = f"""SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
            FROM expenses e JOIN users u ON e.paid_by_id = u.id
            WHERE ((e.group_id IS NULL AND e.paid_by_id = %s) OR (e.group_id IN ({placeholders})))"""
        params = [current_user.id] + group_ids
    else:
        sql = """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
            FROM expenses e JOIN users u ON e.paid_by_id = u.id
            WHERE e.paid_by_id = %s AND e.group_id IS NULL"""
        params = [current_user.id]
        
    if category and category not in ('All categories', 'all', ''):
        sql += " AND e.category = %s"
        params.append(category)
    if search:
        search = search[:100]
        sql += " AND (e.merchant LIKE %s OR e.description LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
        
    sql += " ORDER BY e.date DESC LIMIT %s"
    params.append(limit)
    
    rows = query_all(sql, tuple(params))
    return jsonify({'expenses': [_hydrate(r) for r in rows]})

@expenses_bp.route('/', methods=['POST'])
@login_required
@limiter.limit(Config.RATELIMIT_EXPENSE)
def create():
    data = request.get_json() or {}
    amount = float(data.get('amount') or 0)
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive'}), 400
    if amount > Config.MAX_EXPENSE_AMOUNT:
        return jsonify({'error': 'Amount exceeds max limit'}), 400
    if count_user_expenses(current_user.id) >= Config.MAX_EXPENSES_PER_USER:
        return jsonify({'error': 'Expense limit reached'}), 400
        
    description = (data.get('description') or '').strip()[:255] or 'Expense'
    merchant = (data.get('merchant') or description.split(' ')[0])[:100].strip()
    
    classification = classifier.predict(description, merchant)
    category = data.get('category')
    if not category or category in ('Auto-classify with AI', 'AI pending'):
        category = classification['category']
        
    history = get_user_category_history(current_user.id, category)
    is_anomaly = (anomaly_detector.detect(amount, history) if len(history) >= 3 else False)
    
    group_id = data.get('group_id')
    if group_id:
        group_id = int(group_id)
        member = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s", (group_id, current_user.id))
        if not member:
            return jsonify({'error': 'Not a member of this group'}), 403
            
    splits = _build_splits(amount, data, group_id)
    if splits is None:
        return jsonify({'error': 'Invalid split configuration'}), 400
        
    expense_id = create_expense_with_splits({
        'description': description, 'merchant': merchant, 'amount': amount,
        'category': category, 'source': data.get('source', 'UPI'),
        'split_type': data.get('split_type', 'equal'),
        'ai_confidence': classification['confidence'], 'is_anomaly': is_anomaly,
        'notes': (data.get('notes') or '')[:500], 'paid_by_id': current_user.id,
        'group_id': group_id,
    }, splits)
    
    month = datetime.now().strftime('%Y-%m')
    update_spent(current_user.id, category, month, amount)
    
    expense = get_expense(expense_id)
    if expense.get('group_id'):
        log_activity(expense['group_id'], current_user.id, 'expense_added', {
            'expense_id': expense['id'], 'description': description,
            'amount': amount, 'category': category,
        })
        emit_to_group(expense['group_id'], 'expense_added', expense)
        
    return jsonify({'expense': expense, 'classification': classification, 'is_anomaly': is_anomaly}), 201

def _build_splits(total_amount, data, group_id):
    split_type = data.get('split_type', 'equal')
    
    participants = list(data.get('participants') or [])
    if not participants:
        participants = [current_user.id]
    participants = list(set(participants))

    splits = []
    if split_type == 'equal':
        share = round(total_amount / len(participants), 2)
        allocated = 0
        for i, uid in enumerate(participants):
            if i == len(participants) - 1:
                amt = round(total_amount - allocated, 2)
            else:
                amt = share
                allocated += share
            splits.append({
                'user_id': uid, 
                'amount': amt, 
                'percentage': round(100 / len(participants), 2)
            })
    elif split_type == 'percentage':
        percentages = data.get('percentages') or {}
        total_pct = sum(float(p) for p in percentages.values())
        if abs(total_pct - 100) > 0.5:
            return None
        for uid_str, pct in percentages.items():
            uid = int(uid_str)
            pct = float(pct)
            splits.append({
                'user_id': uid, 
                'amount': round(total_amount * pct / 100, 2), 
                'percentage': pct
            })
    elif split_type == 'custom':
        amounts = data.get('custom_amounts') or {}
        total_custom = sum(float(a) for a in amounts.values())
        if abs(total_custom - total_amount) > 0.5:
            return None
        for uid_str, amt in amounts.items():
            uid = int(uid_str)
            amt = float(amt)
            splits.append({
                'user_id': uid, 
                'amount': amt, 
                'percentage': round(amt / total_amount * 100, 2)
            })
    else:
        return None
    return splits

@expenses_bp.route('/<int:expense_id>', methods=['DELETE'])
@login_required
def remove(expense_id):
    gid = delete_expense(expense_id, current_user.id)
    if gid is None:
        return jsonify({'error': 'Not found or unauthorized'}), 404
    if gid:
        log_activity(gid, current_user.id, 'expense_deleted', {'expense_id': expense_id})
        emit_to_group(gid, 'expense_deleted', {'id': expense_id})
    return jsonify({'message': 'Deleted'})

@expenses_bp.route('/classify', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def classify_preview():
    data = request.get_json() or {}
    desc = (data.get('description') or '')[:255]
    return jsonify(classifier.get_explanation(desc, data.get('merchant', '')))

# ============================================================
# ⭐ RECEIPT UPLOAD (ADD THIS TO THE END OF FILE)
# ============================================================

@expenses_bp.route('/<int:expense_id>/receipt', methods=['POST'])
@login_required
@limiter.limit(Config.RATELIMIT_UPLOAD)
def upload_receipt(expense_id):
    import os
    import uuid
    from PIL import Image

    row = query_one("SELECT paid_by_id, group_id FROM expenses WHERE id = %s", (expense_id,))
    if not row or row['paid_by_id'] != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if 'receipt' not in request.files:
        return jsonify({'error': 'No file'}), 400

    file = request.files['receipt']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({'error': f'Only {", ".join(Config.ALLOWED_EXTENSIONS)}'}), 400

    file_bytes = file.read()
    if len(file_bytes) > Config.MAX_CONTENT_LENGTH:
        return jsonify({'error': 'File too large (max 5 MB)'}), 400

    file.seek(0)
    mime = file.mimetype or ''
    ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/gif', 'application/pdf'}
    if mime not in ALLOWED_MIMES:
        return jsonify({'error': f'Invalid file type: {mime}'}), 400

    if mime.startswith('image/'):
        try:
            import io
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
        except Exception:
            return jsonify({'error': 'Corrupt or invalid image file'}), 400

    receipt_dir = os.path.join('static', 'receipts')
    os.makedirs(receipt_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex[:12]}_{expense_id}.{ext}"
    filepath = os.path.join(receipt_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(file_bytes)

    relative_path = f"/static/receipts/{filename}"
    execute("UPDATE expenses SET receipt_path = %s, receipt_uploaded_at = NOW() WHERE id = %s", (relative_path, expense_id))

    if row.get('group_id'):
        log_activity(row['group_id'], current_user.id, 'receipt_uploaded', {'expense_id': expense_id})
        emit_to_group(row['group_id'], 'receipt_uploaded', {
            'expense_id': expense_id, 'receipt_path': relative_path,
            'uploaded_by': current_user.name,
        })

    return jsonify({'message': 'Uploaded', 'receipt_path': relative_path, 'has_receipt': True}), 201


@expenses_bp.route('/<int:expense_id>/receipt', methods=['GET'])
@login_required
def get_receipt(expense_id):
    row = query_one(
        """SELECT e.receipt_path, e.receipt_uploaded_at, e.group_id,
                  e.paid_by_id, e.description, e.merchant
           FROM expenses e WHERE e.id = %s""",
        (expense_id,)
    )
    if not row:
        return jsonify({'error': 'Not found'}), 404

    has_access = (row['paid_by_id'] == current_user.id)
    if not has_access and row['group_id']:
        member = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s", (row['group_id'], current_user.id))
        has_access = member is not None

    if not has_access:
        return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'expense_id': expense_id,
        'receipt_path': row['receipt_path'],
        'has_receipt': bool(row['receipt_path']),
        'uploaded_at': (row['receipt_uploaded_at'].strftime('%d %b %Y %H:%M') if row['receipt_uploaded_at'] else None),
        'description': row['description'],
        'merchant': row['merchant'],
    })


@expenses_bp.route('/<int:expense_id>/receipt', methods=['DELETE'])
@login_required
def delete_receipt(expense_id):
    import os

    row = query_one("SELECT paid_by_id, receipt_path FROM expenses WHERE id = %s", (expense_id,))
    if not row or row['paid_by_id'] != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if row['receipt_path']:
        filepath = row['receipt_path'].lstrip('/')
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

    execute("UPDATE expenses SET receipt_path = NULL, receipt_uploaded_at = NULL WHERE id = %s", (expense_id,))
    return jsonify({'message': 'Deleted'})