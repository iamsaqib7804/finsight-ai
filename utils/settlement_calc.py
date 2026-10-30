from collections import defaultdict
from db import query_all

def calculate_group_balances(group_id):
    paid_rows = query_all("SELECT paid_by_id AS user_id, SUM(amount) AS total_paid FROM expenses WHERE group_id = %s GROUP BY paid_by_id", (group_id,))
    paid = {r['user_id']: round(float(r['total_paid']), 2) for r in paid_rows}

    owed_rows = query_all("SELECT es.user_id, SUM(es.amount) AS total_owed FROM expense_splits es JOIN expenses e ON es.expense_id = e.id WHERE e.group_id = %s GROUP BY es.user_id", (group_id,))
    owed = {r['user_id']: round(float(r['total_owed']), 2) for r in owed_rows}

    settled_out_rows = query_all("SELECT payer_id AS user_id, SUM(amount) AS total_out FROM settlements WHERE group_id = %s AND status = 'completed' GROUP BY payer_id", (group_id,))
    settled_out = {r['user_id']: round(float(r['total_out']), 2) for r in settled_out_rows}

    settled_in_rows = query_all("SELECT receiver_id AS user_id, SUM(amount) AS total_in FROM settlements WHERE group_id = %s AND status = 'completed' GROUP BY receiver_id", (group_id,))
    settled_in = {r['user_id']: round(float(r['total_in']), 2) for r in settled_in_rows}

    members = query_all("SELECT user_id FROM group_members WHERE group_id = %s", (group_id,))
    balances = {}
    
    for m in members:
        uid = m['user_id']
        net = paid.get(uid, 0.0) - owed.get(uid, 0.0) + settled_out.get(uid, 0.0) - settled_in.get(uid, 0.0)
        if abs(net) < 0.01:
            net = 0.0
        balances[uid] = round(net, 2)

    return balances

def simplify_debts(balances):
    creditors = [[uid, amt] for uid, amt in balances.items() if amt > 0.01]
    debtors = [[uid, -amt] for uid, amt in balances.items() if amt < -0.01]
    creditors.sort(key=lambda x: -x[1])
    debtors.sort(key=lambda x: -x[1])
    
    transactions = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_id, d_amt = debtors[i]
        c_id, c_amt = creditors[j]
        pay = min(d_amt, c_amt)
        transactions.append({'from_user': d_id, 'to_user': c_id, 'amount': round(pay, 2)})
        debtors[i][1] = round(debtors[i][1] - pay, 2)
        creditors[j][1] = round(creditors[j][1] - pay, 2)
        if debtors[i][1] < 0.01: i += 1
        if creditors[j][1] < 0.01: j += 1
    return transactions

def get_pending_settlements_for_user(user_id):
    groups = query_all("SELECT group_id FROM group_members WHERE user_id = %s", (user_id,))
    owe_map = defaultdict(float)
    recv_map = defaultdict(float)

    for g in groups:
        gid = g['group_id']
        balances = calculate_group_balances(gid)
        
        pending_rows = query_all("SELECT payer_id, receiver_id, amount FROM settlements WHERE group_id = %s AND status = 'pending'", (gid,))
        pending_set = set()
        for pr in pending_rows:
            pending_set.add((pr['payer_id'], pr['receiver_id'], round(float(pr['amount']), 2)))

        txs = simplify_debts(balances)

        for t in txs:
            amt = round(t['amount'], 2)
            if (t['from_user'], t['to_user'], amt) in pending_set:
                continue
            if t['from_user'] == user_id:
                owe_map[t['to_user']] += amt
            elif t['to_user'] == user_id:
                recv_map[t['from_user']] += amt

    return {
        'to_pay': [{'user_id': k, 'amount': round(v, 2)} for k, v in owe_map.items()],
        'to_receive': [{'user_id': k, 'amount': round(v, 2)} for k, v in recv_map.items()],
    }