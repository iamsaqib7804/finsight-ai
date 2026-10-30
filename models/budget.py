from db import query_one, query_all, execute

def upsert_budget(user_id, category, limit_amount, month, alert_threshold=0.80):
    existing = query_one(
        "SELECT id FROM budgets WHERE user_id = %s AND category = %s AND month = %s",
        (user_id, category, month)
    )
    if existing:
        execute("UPDATE budgets SET limit_amount = %s, alert_threshold = %s WHERE id = %s",
                (limit_amount, alert_threshold, existing['id']))
        return existing['id']
    return execute(
        """INSERT INTO budgets (user_id, category, limit_amount, month, alert_threshold)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, category, limit_amount, month, alert_threshold)
    )

def get_budgets(user_id, month):
    rows = query_all(
        "SELECT * FROM budgets WHERE user_id = %s AND month = %s ORDER BY category",
        (user_id, month)
    )
    return [_hydrate(r) for r in rows]

def _hydrate(b):
    b['limit'] = float(b['limit_amount'])
    b['spent'] = float(b['spent_amount'])
    b['remaining'] = max(b['limit'] - b['spent'], 0)
    pct = round((b['spent'] / b['limit']) * 100, 1) if b['limit'] else 0
    b['percentage'] = pct
    b['status'] = 'danger' if pct >= 100 else 'warn' if pct >= 80 else 'ok'
    return b

def delete_budget(bid, user_id):
    row = query_one("SELECT user_id FROM budgets WHERE id = %s", (bid,))
    if not row or row['user_id'] != user_id:
        return False
    execute("DELETE FROM budgets WHERE id = %s", (bid,))
    return True

def update_spent(user_id, category, month, amount_delta):
    row = query_one(
        "SELECT id FROM budgets WHERE user_id = %s AND category = %s AND month = %s",
        (user_id, category, month)
    )
    if row:
        execute("UPDATE budgets SET spent_amount = spent_amount + %s WHERE id = %s", (amount_delta, row['id']))

def recalculate_spent(user_id, category, month):
    year, m = map(int, month.split('-'))
    row = query_one(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM expenses
           WHERE paid_by_id = %s AND category = %s AND YEAR(date) = %s AND MONTH(date) = %s""",
        (user_id, category, year, m)
    )
    total = float(row['total'])
    execute(
        """UPDATE budgets SET spent_amount = %s
           WHERE user_id = %s AND category = %s AND month = %s""",
        (total, user_id, category, month)
    )
    return total