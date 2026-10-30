from statistics import mean

class BudgetPredictor:
    def predict_next_month(self, historical_amounts):
        if not historical_amounts or all(a == 0 for a in historical_amounts):
            return {'prediction': 0, 'confidence': 0, 'trend': 'stable', 'slope': 0}
        amounts = [float(a) for a in historical_amounts]
        n = len(amounts)
        weights = list(range(1, n + 1))
        wma = sum(a * w for a, w in zip(amounts, weights)) / sum(weights)
        slope = 0
        if n >= 2:
            x_mean = (n - 1) / 2
            y_mean = mean(amounts)
            num = sum((i - x_mean) * (amounts[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
            trend_value = slope * n + (y_mean - slope * x_mean)
            prediction = 0.6 * wma + 0.4 * trend_value
        else:
            prediction = wma
        if n >= 2:
            std = (sum((a - mean(amounts)) ** 2 for a in amounts) / n) ** 0.5
            cv = std / mean(amounts) if mean(amounts) > 0 else 1
            confidence = max(0.5, min(0.95, 1 - cv * 0.5))
        else:
            confidence = 0.5
        trend = 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'stable'
        return {'prediction': round(max(prediction, 0), 2), 'confidence': round(confidence, 2), 'trend': trend, 'slope': round(slope, 2)}

    def predict_category_wise(self, category_history):
        return {cat: self.predict_next_month(amts) for cat, amts in category_history.items() if amts}