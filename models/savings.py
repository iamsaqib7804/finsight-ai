"""Persistence helpers for user-owned savings goals and contributions."""
from db import execute, query_all, query_one, transaction


def create_goal(user_id, goal_name, target_amount, target_date, notes=None):
    return execute(
        """INSERT INTO savings_goals
           (user_id, goal_name, target_amount, saved_amount, target_date, notes, status)
           VALUES (%s, %s, %s, 0, %s, %s, 'active')""",
        (user_id, goal_name, target_amount, target_date, notes),
    )


def get_goal(goal_id, user_id):
    return query_one(
        """SELECT id, user_id, goal_name, target_amount, saved_amount,
                  target_date, notes, status, created_at, updated_at
           FROM savings_goals WHERE id = %s AND user_id = %s""",
        (goal_id, user_id),
    )


def get_goals(user_id, include_completed=True):
    sql = """SELECT id, user_id, goal_name, target_amount, saved_amount,
                    target_date, notes, status, created_at, updated_at
             FROM savings_goals WHERE user_id = %s"""
    params = [user_id]
    if not include_completed:
        sql += " AND status = 'active'"
    sql += " ORDER BY target_date ASC, created_at DESC"
    return query_all(sql, tuple(params))


def add_contribution(goal_id, user_id, amount, note=None):
    """Record a contribution and update its goal atomically."""
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT id, target_amount, saved_amount, status FROM savings_goals "
            "WHERE id = %s AND user_id = %s FOR UPDATE",
            (goal_id, user_id),
        )
        goal = cursor.fetchone()
        if not goal:
            return None
        if goal['status'] == 'completed':
            raise ValueError('This savings goal is already completed')

        cursor.execute(
            "INSERT INTO savings_contributions (goal_id, user_id, amount, note) VALUES (%s, %s, %s, %s)",
            (goal_id, user_id, amount, note),
        )
        new_saved = float(goal['saved_amount']) + float(amount)
        status = 'completed' if new_saved >= float(goal['target_amount']) else 'active'
        cursor.execute(
            "UPDATE savings_goals SET saved_amount = %s, status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
            (new_saved, status, goal_id, user_id),
        )
    return get_goal(goal_id, user_id)


def get_contributions(goal_id, user_id):
    # Ownership is checked before contribution history is returned.
    if not get_goal(goal_id, user_id):
        return None
    return query_all(
        """SELECT id, amount, note, created_at FROM savings_contributions
           WHERE goal_id = %s AND user_id = %s ORDER BY created_at DESC""",
        (goal_id, user_id),
    )

def update_goal(user_id, goal_id, goal_name, target_amount, target_date, notes=None):
    """Update a goal belonging to the authenticated user."""
    with transaction() as (_, cursor):
        cursor.execute(
            """SELECT id, saved_amount
               FROM savings_goals
               WHERE id = %s AND user_id = %s
               FOR UPDATE""",
            (goal_id, user_id),
        )
        goal = cursor.fetchone()

        if not goal:
            return None

        saved_amount = float(goal['saved_amount'])
        target_amount = float(target_amount)

        if target_amount <= 0:
            raise ValueError("Target amount must be greater than zero")

        status = 'completed' if saved_amount >= target_amount else 'active'

        cursor.execute(
            """UPDATE savings_goals
               SET goal_name = %s,
                   target_amount = %s,
                   target_date = %s,
                   notes = %s,
                   status = %s,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s AND user_id = %s""",
            (
                goal_name,
                target_amount,
                target_date,
                notes,
                status,
                goal_id,
                user_id,
            ),
        )

    return get_goal(goal_id, user_id)


def delete_goal(goal_id, user_id):
    """Delete a user's goal and its contribution history atomically."""
    with transaction() as (_, cursor):
        cursor.execute(
            """SELECT id FROM savings_goals
               WHERE id = %s AND user_id = %s
               FOR UPDATE""",
            (goal_id, user_id),
        )
        goal = cursor.fetchone()

        if not goal:
            return False

        cursor.execute(
            """DELETE FROM savings_contributions
               WHERE goal_id = %s AND user_id = %s""",
            (goal_id, user_id),
        )

        cursor.execute(
            """DELETE FROM savings_goals
               WHERE id = %s AND user_id = %s""",
            (goal_id, user_id),
        )

    return True
