<div align="center">
  <h1>💰 FinSight AI</h1>
  <p><b>Intelligent Expense Classification and Budget Prediction System</b></p>
  
  [![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-3.0.0-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![MySQL](https://img.shields.io/badge/MySQL-8.0-blue?logo=mysql&logoColor=white)](https://www.mysql.com/)
  [![Scikit-Learn](https://img.shields.io/badge/scikit--learn-1.4.0-orange?logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
  [![Pytest](https://img.shields.io/badge/Pytest-Passing-brightgreen?logo=pytest&logoColor=white)]()
</div>

---

## 📌 Overview

**FinSight AI** is a full-stack, AI-powered personal finance and group expense management platform. It goes beyond traditional expense trackers by using Machine Learning to automatically categorize transactions, predict future budgets, and simplify complex group settlements.

Built with a focus on **real-time synchronization**, **data security**, and **automated testing**, FinSight AI provides an intelligent, seamless financial experience.

---

## ✨ Key Features

### 🤖 AI & Machine Learning
- **Auto-Classification:** Uses a Naive Bayes classifier trained on real-world Kaggle transaction data to auto-categorize expenses (Food, Travel, Shopping, Bills, Entertainment).
- **Budget Prediction:** Forecasts next month's expenses based on historical spending trends using Weighted Moving Averages.
- **Anomaly Detection:** Flags unusual or overspending transactions.
- **Live XAI:** Explains *why* a transaction was categorized a certain way (e.g., "Keywords matched: swiggy, dinner").

### 👥 Group & Settlement Engine
- **Smart Split:** Split expenses equally, by percentage, or among specific selected group members.
- **Zero-Loop Settlements:** A mathematically strict 2-step settlement flow (Payer Pays -> Receiver Confirms) ensuring balances always hit exactly ₹0.
- **Group Dashboard:** Interactive visualizations including Leaderboards, 12-Week Spending Heatmaps, and Monthly Story Cards.

### 🔒 Security & Production Ready
- **Session Management:** Secure session cookies and CSRF protection.
- **Rate Limiting:** Prevents brute-force attacks on login and API endpoints.
- **File Validation:** Strict MIME-type and 5MB size limits on receipt uploads.
- **Automated Testing:** Includes a suite of Pytest scripts covering both functional and non-functional requirements.

---

## 📸 Screenshots

*(Add your screenshots here. Replace the placeholders below with your actual image URLs)*

| Dashboard & AI Prediction | Smart Settlements |
|:---:|:---:|
| ![Dashboard](https://via.placeholder.com/600x350?text=Dashboard+Screenshot) | ![Settlements](https://via.placeholder.com/600x350?text=Settlements+Screenshot) |

| Group Analytics & Heatmap | ML Insights & Auto-Classification |
|:---:|:---:|
| ![Group](https://via.placeholder.com/600x350?text=Group+Dashboard) | ![ML](https://via.placeholder.com/600x350?text=ML+Insights+Screenshot) |

---

## 🛠️ Tech Stack

- **Backend Framework:** Flask (Python), Flask-Login, Flask-SocketIO
- **Database:** MySQL 8.0 (raw SQL via `mysql-connector-python`)
- **Machine Learning:** Scikit-learn, Pandas, NumPy, Joblib
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (Fetch API)
- **Security:** Flask-Limiter, Pillow (Image Validation)
- **Testing:** Pytest, Requests

---

## 🏗️ System Architecture

1. **Data Ingestion:** User inputs text descriptions or uploads receipts.
2. **Preprocessing:** Text is tokenized, and bigrams are generated.
3. **ML Pipeline:** TF-IDF style scoring + Naive Bayes classifies the category.
4. **Storage:** Data is stored securely in a normalized MySQL relational database.
5. **Real-time Engine:** Flask-SocketIO pushes updates to all group members.
6. **Settlement Engine:** A greedy algorithm computes the minimum transactions required to settle all debts.

---

## 🚀 Local Installation & Setup

Follow these steps to run the project on your local machine.

### 1. Clone the Repository
```bash
git clone https://github.com/iamsaqib7804/finsight-ai.git
cd finsight-ai