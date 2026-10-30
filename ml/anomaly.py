import statistics

class AnomalyDetector:
    def detect(self, amount, historical_amounts):
        if len(historical_amounts) < 3:
            return False
        mean = statistics.mean(historical_amounts)
        stdev = statistics.pstdev(historical_amounts)
        if stdev == 0:
            return amount > mean * 2
        z_score = (amount - mean) / stdev
        return abs(z_score) > 2.5

    def get_risk_level(self, spent, budget):
        if budget == 0:
            return {'level': 'unknown', 'percentage': 0}
        pct = (spent / budget) * 100
        level = 'high' if pct >= 100 else 'medium' if pct >= 80 else 'low'
        return {'level': level, 'percentage': round(pct, 1), 'remaining': max(budget - spent, 0)}