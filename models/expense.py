from db import query_one, query_all, execute, transaction

def create_expense_with_splits(expense_data, splits):
    with transaction() as (conn, cursor):
        cursor.execute(
            """INSERT INTO expenses
               (description, merchant, amount, category, source, split_type,
                ai_confidence, is_anomaly, notes, paid_by_id, group_id, date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
            (
                expense_data['description'], expense_data['merchant'],
                expense_data['amount'], expense_data['category'],
                expense_data['source'], expense_data['split_type'],
                expense_data['ai_confidence'], 1 if expense_data['is_anomaly'] else 0,
                expense_data.get('notes', ''), expense_data['paid_by_id'],
                expense_data.get('group_id'),
            )
        )
        expense_id = cursor.lastrowid
        for s in splits:
            cursor.execute(
                """INSERT INTO expense_splits (expense_id, user_id, amount, percentage)
                   VALUES (%s, %s, %s, %s)""",
                (expense_id, s['user_id'], s['amount'], s['percentage'])
            )
        return expense_id

def get_expense(expense_id):
    e = query_one(
        """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
           FROM expenses e JOIN users u ON e.paid_by_id = u.id
           WHERE e.id = %s""",
        (expense_id,)
    )
    if not e:
        return None
    return _hydrate(e)

def _hydrate(e):
    e['date'] = e['date'].strftime('%d %b %Y') if e['date'] else ''
    e['ai_confidence'] = (f"{int(float(e['ai_confidence']) * 100)}%" if e['ai_confidence'] else '—')
    e['is_anomaly'] = bool(e['is_anomaly'])
    e['amount'] = float(e['amount'])
    e['paid_by'] = {
        'id': e['paid_by_id'], 'name': e.get('paid_by_name', ''),
        'avatar': e.get('paid_by_avatar', 'U') or 'U',
    }
    receipt = e.get('receipt_path')
    e['receipt_path'] = receipt if receipt else None
    e['has_receipt'] = bool(receipt)
    e['receipt_uploaded_at'] = (e['receipt_uploaded_at'].strftime('%d %b %Y') if e.get('receipt_uploaded_at') else None)
    splits = query_all(
        """SELECT es.*, u.name AS user_name
           FROM expense_splits es JOIN users u ON es.user_id = u.id
           WHERE es.expense_id = %s""",
        (e['id'],)
    )
    for s in splits:
        s['is_settled'] = bool(s['is_settled'])
        s['amount'] = float(s['amount'])
        s['percentage'] = float(s['percentage'])
    e['splits'] = splits
    return e

def get_user_expenses(user_id, category=None, search=None, limit=500):
    sql = """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
             FROM expenses e JOIN users u ON e.paid_by_id = u.id
             WHERE e.paid_by_id = %s"""
    params = [user_id]
    if category and category not in ('All categories', 'all', ''):
        sql += " AND e.category = %s"
        params.append(category)
    if search:
        sql += " AND (e.merchant LIKE %s OR e.description LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    sql += " ORDER BY e.date DESC LIMIT %s"
    params.append(limit)
    rows = query_all(sql, tuple(params))
    return [_hydrate(r) for r in rows]

def get_group_expenses(group_id):
    rows = query_all(
        """SELECT e.*, u.name AS paid_by_name, u.avatar_initials AS paid_by_avatar
           FROM expenses e JOIN users u ON e.paid_by_id = u.id
           WHERE e.group_id = %s ORDER BY e.date DESC""",
        (group_id,)
    )
    return [_hydrate(r) for r in rows]

def delete_expense(expense_id, user_id):
    row = query_one("SELECT paid_by_id, group_id FROM expenses WHERE id = %s", (expense_id,))
    if not row or row['paid_by_id'] != user_id:
        return None
    execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
    return row['group_id']

def get_user_category_history(user_id, category, limit=30):
    rows = query_all(
        """SELECT amount FROM expenses WHERE paid_by_id = %s AND category = %s
           ORDER BY date DESC LIMIT %s""",
        (user_id, category, limit)
    )
    return [float(r['amount']) for r in rows]

def get_monthly_totals(user_id, months=6):
    from datetime import datetime
    now = datetime.now()
    totals = []
    for i in range(months - 1, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        row = query_one(
            """SELECT COALESCE(SUM(amount), 0) AS total FROM expenses
               WHERE paid_by_id = %s AND YEAR(date) = %s AND MONTH(date) = %s""",
            (user_id, y, m)
        )
        totals.append(float(row['total']))
    return totals

def get_category_totals(user_id, year, month):
    rows = query_all(
        """SELECT category, SUM(amount) AS total FROM expenses
           WHERE paid_by_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
           GROUP BY category""",
        (user_id, year, month)
    )
    return {r['category']: float(r['total']) for r in rows}

def update_expense(expense_id, user_id, description, amount, category, merchant=None, source=None, notes=None):
    row = query_one("SELECT paid_by_id FROM expenses WHERE id = %s", (expense_id,))
    if not row or row['paid_by_id'] != user_id:
        return None
    execute(
        """UPDATE expenses
           SET description = %s, amount = %s, category = %s,
               merchant = COALESCE(%s, merchant),
               source = COALESCE(%s, source),
               notes = COALESCE(%s, notes)
           WHERE id = %s""",
        (description, amount, category, merchant, source, notes, expense_id)
    )
    return get_expense(expense_id)

def count_user_expenses(user_id):
    row = query_one("SELECT COUNT(*) AS c FROM expenses WHERE paid_by_id = %s", (user_id,))
    return int(row['c']) if row else 0

# Comments
def add_comment(expense_id, user_id, comment_text):
    cid = execute(
        """INSERT INTO expense_comments (expense_id, user_id, comment)
           VALUES (%s, %s, %s)""",
        (expense_id, user_id, comment_text)
    )
    return get_comment(cid)

def get_comment(cid):
    row = query_one(
        """SELECT ec.*, u.name AS user_name, u.avatar_initials
           FROM expense_comments ec JOIN users u ON ec.user_id = u.id
           WHERE ec.id = %s""",
        (cid,)
    )
    if not row:
        return None
    return _hydrate_comment(row)

def get_comments(expense_id):
    rows = query_all(
        """SELECT ec.*, u.name AS user_name, u.avatar_initials
           FROM expense_comments ec JOIN users u ON ec.user_id = u.id
           WHERE ec.expense_id = %s ORDER BY ec.created_at ASC""",
        (expense_id,)
    )
    return [_hydrate_comment(r) for r in rows]

def _hydrate_comment(row):
    from datetime import datetime
    now = datetime.now()
    delta = now - row['created_at']
    if delta.days > 0: time_ago = f"{delta.days}d ago"
    elif delta.seconds > 3600: time_ago = f"{delta.seconds // 3600}h ago"
    elif delta.seconds > 60: time_ago = f"{delta.seconds // 60}m ago"
    else: time_ago = "Just now"
    return {
        'id': row['id'], 'expense_id': row['expense_id'],
        'user': {'id': row['user_id'], 'name': row['user_name'], 'avatar': row['avatar_initials'] or 'U'},
        'comment': row['comment'],
        'created_at': row['created_at'].strftime('%d %b %Y %H:%M'),
        'time_ago': time_ago,
    }

def delete_comment(cid, user_id):
    row = query_one("SELECT user_id FROM expense_comments WHERE id = %s", (cid,))
    if not row or row['user_id'] != user_id:
        return False
    execute("DELETE FROM expense_comments WHERE id = %s", (cid,))
    return True