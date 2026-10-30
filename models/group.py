from db import query_one, query_all, execute
from datetime import datetime

def create_group(name, description, creator_id):
    gid = execute(
        "INSERT INTO groups_table (name, description, created_by_id) VALUES (%s, %s, %s)",
        (name, description, creator_id)
    )
    execute(
        "INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'admin')",
        (gid, creator_id)
    )
    log_activity(gid, creator_id, 'group_created', {'name': name})
    return get_group(gid)

def get_group(group_id):
    g = query_one("SELECT * FROM groups_table WHERE id = %s", (group_id,))
    if not g:
        return None
    g['created_at'] = g['created_at'].strftime('%d %b %Y') if g['created_at'] else ''
    members = get_group_members(group_id)
    g['members'] = members
    g['member_count'] = len(members)
    return g

def get_group_members(group_id):
    rows = query_all(
        """SELECT gm.id, gm.user_id, gm.role, gm.joined_at,
                  u.name, u.email, u.avatar_initials
           FROM group_members gm
           JOIN users u ON gm.user_id = u.id
           WHERE gm.group_id = %s
           ORDER BY gm.joined_at""",
        (group_id,)
    )
    for r in rows:
        r['joined_at'] = r['joined_at'].strftime('%d %b %Y') if r['joined_at'] else ''
        r['user'] = {
            'id': r['user_id'], 'name': r['name'],
            'email': r['email'], 'avatar': r['avatar_initials'] or 'U',
        }
    return rows

def get_group_member_ids(group_id):
    rows = query_all("SELECT user_id FROM group_members WHERE group_id = %s", (group_id,))
    return [r['user_id'] for r in rows]

def get_user_groups(user_id):
    rows = query_all(
        """SELECT g.id, g.name, g.description, g.created_at,
                  (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count
           FROM groups_table g
           JOIN group_members gm ON gm.group_id = g.id
           WHERE gm.user_id = %s
           ORDER BY g.created_at DESC""",
        (user_id,)
    )
    for r in rows:
        r['created_at'] = r['created_at'].strftime('%d %b %Y') if r['created_at'] else ''
    return rows

def is_member(group_id, user_id):
    row = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s", (group_id, user_id))
    return row is not None

def is_admin(group_id, user_id):
    row = query_one("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s AND role = 'admin'", (group_id, user_id))
    return row is not None

def add_member(group_id, user_id, role='member'):
    try:
        execute("INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, %s)", (group_id, user_id, role))
        return True
    except Exception:
        return False

def remove_member(group_id, user_id):
    execute("DELETE FROM group_members WHERE group_id = %s AND user_id = %s", (group_id, user_id))

def delete_group(group_id):
    execute("DELETE FROM groups_table WHERE id = %s", (group_id,))

def log_activity(group_id, user_id, action, meta=None):
    import json
    meta_json = json.dumps(meta) if meta else None
    try:
        execute(
            """INSERT INTO group_activities (group_id, user_id, action, meta)
               VALUES (%s, %s, %s, %s)""",
            (group_id, user_id, action, meta_json)
        )
    except Exception as e:
        print(f"⚠️ Failed to log activity: {e}")

def get_group_activities(group_id, limit=30):
    import json
    rows = query_all(
        """SELECT ga.*, u.name AS user_name, u.avatar_initials
           FROM group_activities ga
           JOIN users u ON ga.user_id = u.id
           WHERE ga.group_id = %s
           ORDER BY ga.created_at DESC
           LIMIT %s""",
        (group_id, limit)
    )
    now = datetime.now()
    for r in rows:
        try:
            r['meta'] = json.loads(r['meta']) if r['meta'] else {}
        except Exception:
            r['meta'] = {}
        delta = now - r['created_at']
        if delta.days > 30: r['time_ago'] = r['created_at'].strftime('%d %b')
        elif delta.days > 0: r['time_ago'] = f"{delta.days}d ago" if delta.days > 1 else "Yesterday"
        elif delta.seconds > 3600: r['time_ago'] = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60: r['time_ago'] = f"{delta.seconds // 60}m ago"
        else: r['time_ago'] = "Just now"
        r['created_at'] = r['created_at'].strftime('%d %b %Y %H:%M')
        r['user'] = {'id': r['user_id'], 'name': r['user_name'], 'avatar': r['avatar_initials'] or 'U'}
    return rows

def get_group_leaderboard(group_id):
    rows = query_all(
        """SELECT 
              u.id AS user_id, u.name, u.avatar_initials,
              COALESCE(p.total_paid, 0) AS total_paid,
              COALESCE(p.txn_count, 0) AS txn_count,
              COALESCE(o.total_owed, 0) AS total_share
           FROM group_members gm
           JOIN users u ON gm.user_id = u.id
           LEFT JOIN (
               SELECT paid_by_id, SUM(amount) AS total_paid, COUNT(*) AS txn_count
               FROM expenses WHERE group_id = %s
               GROUP BY paid_by_id
           ) p ON p.paid_by_id = u.id
           LEFT JOIN (
               SELECT es.user_id, SUM(es.amount) AS total_owed
               FROM expense_splits es
               JOIN expenses e ON es.expense_id = e.id
               WHERE e.group_id = %s
               GROUP BY es.user_id
           ) o ON o.user_id = u.id
           WHERE gm.group_id = %s""",
        (group_id, group_id, group_id)
    )
    leaderboard = []
    for r in rows:
        paid = float(r['total_paid'])
        share = float(r['total_share'])
        leaderboard.append({
            'user': {'id': r['user_id'], 'name': r['name'], 'avatar': r['avatar_initials'] or 'U'},
            'total_paid': round(paid, 2),
            'total_share': round(share, 2),
            'net': round(paid - share, 2),
            'txn_count': int(r['txn_count']),
        })
    leaderboard.sort(key=lambda x: -x['total_paid'])
    return leaderboard

def get_group_heatmap(group_id, weeks=12):
    from datetime import timedelta
    end_date = datetime.now().date()
    start_date = end_date - timedelta(weeks=weeks)
    rows = query_all(
        """SELECT DATE(date) AS day, SUM(amount) AS total
           FROM expenses WHERE group_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
           GROUP BY DATE(date)""",
        (group_id, start_date, end_date)
    )
    daily = {r['day'].strftime('%Y-%m-%d'): float(r['total']) for r in rows}
    max_val = max(daily.values()) if daily else 0
    heatmap = []
    current = start_date
    while current <= end_date:
        key = current.strftime('%Y-%m-%d')
        amount = daily.get(key, 0)
        if max_val == 0 or amount == 0: level = 0
        else:
            ratio = amount / max_val
            level = 1 if ratio < 0.25 else 2 if ratio < 0.5 else 3 if ratio < 0.75 else 4
        heatmap.append({'date': key, 'amount': round(amount, 2), 'level': level})
        current += timedelta(days=1)
    return {'days': heatmap, 'max': round(max_val, 2)}

def get_group_story(group_id, year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    total_row = query_one(
        """SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS txn_count
           FROM expenses WHERE group_id = %s AND YEAR(date) = %s AND MONTH(date) = %s""",
        (group_id, year, month)
    )
    total = float(total_row['total'])
    txn_count = int(total_row['txn_count'])
    top_spender = query_one(
        """SELECT u.name, u.avatar_initials, SUM(e.amount) AS total
           FROM expenses e JOIN users u ON e.paid_by_id = u.id
           WHERE e.group_id = %s AND YEAR(e.date) = %s AND MONTH(e.date) = %s
           GROUP BY e.paid_by_id, u.name, u.avatar_initials
           ORDER BY total DESC LIMIT 1""",
        (group_id, year, month)
    )
    top_cat = query_one(
        """SELECT category, SUM(amount) AS total, COUNT(*) AS cnt
           FROM expenses WHERE group_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
           GROUP BY category ORDER BY total DESC LIMIT 1""",
        (group_id, year, month)
    )
    active_day = query_one(
        """SELECT DATE(date) AS day, SUM(amount) AS total, COUNT(*) AS cnt
           FROM expenses WHERE group_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
           GROUP BY DATE(date) ORDER BY cnt DESC LIMIT 1""",
        (group_id, year, month)
    )
    return {
        'month_label': f"{datetime(year, month, 1).strftime('%B %Y')}",
        'year': year, 'month': month,
        'total': round(total, 2), 'txn_count': txn_count,
        'avg_per_txn': round(total / txn_count, 2) if txn_count > 0 else 0,
        'top_spender': {'name': top_spender['name'], 'avatar': top_spender['avatar_initials'] or 'U', 'amount': round(float(top_spender['total']), 2)} if top_spender else None,
        'top_category': {'name': top_cat['category'], 'amount': round(float(top_cat['total']), 2), 'count': int(top_cat['cnt']), 'percentage': round(float(top_cat['total']) / total * 100, 1) if total > 0 else 0} if top_cat else None,
        'most_active_day': {'date': active_day['day'].strftime('%d %b (%A)') if active_day else None, 'txn_count': int(active_day['cnt']) if active_day else 0} if active_day else None,
    }