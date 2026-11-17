"""History-weighted budget allocation using the existing expense prediction model."""
from datetime import date
DEFAULT_CATEGORIES = ['Food', 'Travel', 'Shopping', 'Bills', 'Entertainment', 'Other']


def allocate_budget(spendable_budget, category_weights):
    """Allocate a spendable amount proportionally, preserving the exact total."""
    spendable_budget = round(float(spendable_budget), 2)
    weights = {str(category): max(float(weight), 0.0) for category, weight in category_weights.items()}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        weights = {category: 1.0 for category in DEFAULT_CATEGORIES}
        total_weight = float(len(DEFAULT_CATEGORIES))

    active = [category for category, weight in weights.items() if weight > 0]
    allocations = {}
    assigned = 0.0
    for category in active[:-1]:
        amount = round(spendable_budget * weights[category] / total_weight, 2)
        allocations[category] = amount
        assigned += amount
    if active:
        allocations[active[-1]] = round(spendable_budget - assigned, 2)
    return allocations, weights


def recommend_budget(user_id, monthly_budget, savings_reserve=0.0):
    from db import query_all
    from ml import predictor
    monthly_budget = round(float(monthly_budget), 2)
    savings_reserve = round(float(savings_reserve), 2)
    if monthly_budget <= 0:
        raise ValueError('Monthly budget must be greater than zero')
    if savings_reserve < 0 or savings_reserve > monthly_budget:
        raise ValueError('Savings reserve must be between zero and the monthly budget')

    today = date.today()
    month_keys = []
    for offset in range(5, -1, -1):
        year, month = today.year, today.month - offset
        while month <= 0:
            year -= 1
            month += 12
        month_keys.append(f'{year}-{month:02d}')

    rows = query_all(
        """SELECT e.category, DATE_FORMAT(e.date, '%Y-%m') AS month,
                  SUM(es.amount) AS total
           FROM expense_splits es
           JOIN expenses e ON e.id = es.expense_id
           WHERE es.user_id = %s AND e.date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
           GROUP BY e.category, DATE_FORMAT(e.date, '%Y-%m')""",
        (user_id,),
    )
    history = {}
    for row in rows:
        history.setdefault(row['category'] or 'Other', {month: 0.0 for month in month_keys})
        if row['month'] in history[row['category'] or 'Other']:
            history[row['category'] or 'Other'][row['month']] = float(row['total'] or 0)

    categories = list(dict.fromkeys(DEFAULT_CATEGORIES + list(history.keys())))
    category_history = {category: [history.get(category, {}).get(month, 0.0) for month in month_keys] for category in categories}
    predictions = predictor.predict_category_wise(category_history)
    weights = {category: max(float(predictions.get(category, {}).get('prediction', 0)), 0) for category in categories}
    spendable = round(monthly_budget - savings_reserve, 2)
    allocations, weights = allocate_budget(spendable, weights)

    return {
        'monthly_budget': monthly_budget,
        'savings_reserve': savings_reserve,
        'spendable_budget': spendable,
        'allocations': [
            {
                'category': category,
                'amount': amount,
                'percentage': round(amount / monthly_budget * 100, 1) if monthly_budget else 0,
                'predicted_historical_spend': round(weights.get(category, 0), 2),
            }
            for category, amount in sorted(allocations.items(), key=lambda item: item[1], reverse=True)
        ],
        'method': 'Proportional allocation based on the existing ML model\'s category-wise spending forecasts; savings are reserved first.',
        'history_months': month_keys,
    }
