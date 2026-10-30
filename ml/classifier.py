import os
import csv
import math
import re
from collections import defaultdict

class ExpenseClassifier:
    CATEGORIES = ['Food', 'Travel', 'Shopping', 'Bills', 'Entertainment', 'Other']

    CATEGORY_MAP = {
        'food': 'Food', 'Food': 'Food', 'Food & Dining': 'Food', 'Groceries': 'Food',
        'travel': 'Travel', 'Travel': 'Travel', 'Transportation': 'Travel',
        'shopping': 'Shopping', 'Shopping': 'Shopping',
        'bills': 'Bills', 'Bills': 'Bills', 'Bills & Utilities': 'Bills', 'EMI': 'Bills',
        'entertainment': 'Entertainment', 'Entertainment': 'Entertainment',
        'investment': 'Other', 'Investment': 'Other', 'healthcare': 'Other',
        'education': 'Other',
    }

    BOOST_KEYWORDS = {
        'Food': [
            'swiggy', 'zomato', 'restaurant', 'cafe', 'coffee', 'pizza', 'burger',
            'lunch', 'dinner', 'breakfast', 'snacks', 'food', 'meal', 'dmart',
            'grocery', 'biryani', 'dominos', 'kfc', 'mcdonalds', 'chai', 'tea',
            'hotel food', 'tiffin', 'canteen', 'bakery', 'eat', 'khana',
        ],
        'Travel': [
            'uber', 'ola', 'cab', 'taxi', 'auto', 'bus', 'train', 'flight',
            'metro', 'travel', 'trip', 'petrol', 'fuel', 'makemytrip',
            'irctc', 'airbnb', 'goa', 'airport', 'rapido', 'ride',
        ],
        'Shopping': [
            'amazon', 'flipkart', 'myntra', 'ajio', 'meesho', 'shopping',
            'mall', 'clothes', 'shoes', 'laptop', 'mobile', 'electronics',
            'tshirt', 'jeans', 'watch', 'dress', 'gadget',
        ],
        'Bills': [
            'jio', 'airtel', 'recharge', 'bill', 'electricity', 'water', 'gas',
            'broadband', 'wifi', 'dth', 'rent', 'emi', 'insurance', 'room rent',
            'hostel', 'pg', 'room', 'maintenance',
        ],
        'Entertainment': [
            'bookmyshow', 'pvr', 'movie', 'film', 'netflix', 'spotify',
            'hotstar', 'prime', 'gaming', 'concert', 'cinema', 'theatre',
            'game', 'playstation', 'xbox',
        ],
        'Other': [
            'medical', 'doctor', 'pharmacy', 'tuition', 'school', 'college',
            'fee', 'gift', 'donation', 'medicine', 'hospital',
        ],
    }

    def __init__(self):
        self.is_trained = False
        self.word_counts = {}
        self.category_doc_count = {}
        self.category_word_totals = {}
        self.vocab = set()
        self.total_docs = 0
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        self._train()

    def _tokenize(self, text):
        text = str(text).lower()
        return re.findall(r'\b[a-z][a-z0-9]+\b', text)

    def _bigrams(self, tokens):
        return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]

    def _train(self):
        print("\n🧠 Training pure-Python Naive Bayes classifier...")
        training_data = []
        csv_files = []
        if os.path.exists(self.data_dir):
            csv_files = [f for f in os.listdir(self.data_dir) if f.endswith('.csv')]
        if csv_files:
            print(f"📁 Found {len(csv_files)} CSV files")
            for csv_file in csv_files:
                training_data.extend(self._load_csv(csv_file))

        boost_count = 0
        for category, kws in self.BOOST_KEYWORDS.items():
            for kw in kws:
                tokens = self._tokenize(kw)
                if tokens:
                    for _ in range(30):
                        training_data.append((tokens, category))
                        boost_count += 1
        if boost_count:
            print(f"📊 Added {boost_count} boosted keyword examples")
        print(f"📚 Total training examples: {len(training_data)}")

        self.word_counts = {c: defaultdict(int) for c in self.CATEGORIES}
        self.category_doc_count = {c: 0 for c in self.CATEGORIES}
        self.category_word_totals = {c: 0 for c in self.CATEGORIES}

        for tokens, category in training_data:
            if category not in self.word_counts:
                continue
            self.category_doc_count[category] += 1
            self.total_docs += 1
            for token in tokens:
                self.word_counts[category][token] += 1
                self.category_word_totals[category] += 1
                self.vocab.add(token)
            for bigram in self._bigrams(tokens):
                self.word_counts[category][bigram] += 1
                self.category_word_totals[category] += 1
                self.vocab.add(bigram)

        self.is_trained = True
        dist = {c: n for c, n in self.category_doc_count.items() if n > 0}
        print(f"📊 Category distribution: {dist}")
        print(f"📖 Vocabulary: {len(self.vocab)} unique terms")
        print("✅ Classifier trained successfully\n")

    def _load_csv(self, filename):
        path = os.path.join(self.data_dir, filename)
        print(f"📖 Reading: {filename}")
        data = []
        for enc in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                with open(path, 'r', encoding=enc, newline='') as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                break
            except UnicodeDecodeError:
                continue
        else:
            return []
        if not rows:
            return []
        cols_lower = {str(c).lower().strip().replace('_', ' '): c for c in rows[0].keys()}
        text_col = None
        for candidate in ['transaction text', 'transaction', 'text', 'description', 'narrative', 'merchant', 'remark']:
            if candidate in cols_lower:
                text_col = cols_lower[candidate]
                break
        label_col = None
        for candidate in ['label', 'category', 'class', 'type']:
            if candidate in cols_lower:
                label_col = cols_lower[candidate]
                break
        if not text_col or not label_col:
            cols = list(rows[0].keys())
            non_id = [c for c in cols if not str(c).lower().startswith('unnamed')]
            if len(non_id) >= 2:
                text_col = text_col or non_id[0]
                label_col = label_col or non_id[1]
        if not text_col or not label_col:
            return []
        loaded = 0
        for row in rows:
            text = str(row.get(text_col, '')).strip()
            label = str(row.get(label_col, '')).strip()
            if not text or text.lower() in ('nan', 'none', ''):
                continue
            mapped = None
            for k, v in self.CATEGORY_MAP.items():
                if k.lower() == label.lower():
                    mapped = v
                    break
            if not mapped:
                mapped = 'Other'
            tokens = self._tokenize(text)
            if tokens:
                data.append((tokens, mapped))
                loaded += 1
        print(f"   ✅ Loaded {loaded} examples")
        return data

    def predict(self, description, merchant=''):
        if not self.is_trained:
            return {'category': 'Other', 'confidence': 0.0, 'keywords': []}

        # ⭐ FIX: Agar merchant aur description same hain, toh text double na banao
        desc_clean = str(description or '').strip()
        mer_clean = str(merchant or '').strip()
        
        if mer_clean and desc_clean:
            if mer_clean.lower() == desc_clean.lower():
                text = desc_clean
            else:
                text = f"{mer_clean} {desc_clean}"
        else:
            text = desc_clean or mer_clean

        if not text:
            return {'category': 'Other', 'confidence': 0.0, 'keywords': []}

        tokens = self._tokenize(text)
        if not tokens:
            return {'category': 'Other', 'confidence': 0.0, 'keywords': []}

        all_tokens = tokens + self._bigrams(tokens)
        vocab_size = len(self.vocab) or 1
        log_probs = {}
        
        for category in self.CATEGORIES:
            if self.category_doc_count[category] == 0:
                continue
            prior = math.log(self.category_doc_count[category] / self.total_docs)
            log_prob = prior
            total_words = self.category_word_totals[category] + vocab_size
            word_counts = self.word_counts[category]
            
            for token in all_tokens:
                count = word_counts.get(token, 0)
                log_prob += math.log((count + 1) / total_words)
            log_probs[category] = log_prob

        if not log_probs:
            return {'category': 'Other', 'confidence': 0.0, 'keywords': []}

        max_log = max(log_probs.values())
        exp_probs = {c: math.exp(lp - max_log) for c, lp in log_probs.items()}
        total = sum(exp_probs.values())
        probs = {c: p / total for c, p in exp_probs.items()}
        best_cat = max(probs.items(), key=lambda x: x[1])
        
        category = best_cat[0]
        confidence = best_cat[1]
        matched = [t for t in tokens if t in self.vocab]
        
        if len(matched) >= 2:
            confidence = min(0.98, confidence + 0.05)
            
        return {'category': category, 'confidence': round(confidence, 4), 'keywords': matched[:5]}

    def get_explanation(self, description, merchant=''):
        r = self.predict(description, merchant)
        if r['confidence'] > 0:
            r['explanation'] = f"Classified as '{r['category']}' based on: {', '.join(r['keywords']) or 'learned patterns'}"
        else:
            r['explanation'] = "Insufficient data."
        return r