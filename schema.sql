USE finsight_ai;
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    avatar_initials VARCHAR(3) DEFAULT 'U',
    monthly_income DECIMAL(12,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'INR',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS groups_table (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    created_by_id INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS group_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    group_id INT NOT NULL,
    user_id INT NOT NULL,
    role VARCHAR(20) DEFAULT 'member',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_group_user (group_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expenses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    merchant VARCHAR(100),
    amount DECIMAL(12,2) NOT NULL,
    category VARCHAR(50) DEFAULT 'Other',
    source VARCHAR(20) DEFAULT 'UPI',
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    split_type VARCHAR(20) DEFAULT 'equal',
    ai_confidence DECIMAL(5,4) DEFAULT 0.0,
    is_anomaly TINYINT(1) DEFAULT 0,
    notes TEXT,
    receipt_path VARCHAR(255) DEFAULT NULL,
    receipt_uploaded_at DATETIME DEFAULT NULL,
    paid_by_id INT NOT NULL,
    group_id INT NULL,
    FOREIGN KEY (paid_by_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
    INDEX idx_expenses_user_date (paid_by_id, date DESC),
    INDEX idx_expenses_group_date (group_id, date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expense_splits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    expense_id INT NOT NULL,
    user_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    percentage DECIMAL(5,2) DEFAULT 0.0,
    is_settled TINYINT(1) DEFAULT 0,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_splits_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS settlements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    payer_id INT NOT NULL,
    receiver_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    group_id INT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at DATETIME NULL,
    notes TEXT,
    FOREIGN KEY (payer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups_table(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS budgets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category VARCHAR(50) NOT NULL,
    limit_amount DECIMAL(12,2) NOT NULL,
    spent_amount DECIMAL(12,2) DEFAULT 0.00,
    month VARCHAR(7) NOT NULL,
    alert_threshold DECIMAL(3,2) DEFAULT 0.80,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_cat_month (user_id, category, month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS group_activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    group_id INT NOT NULL,
    user_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    meta JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expense_comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    expense_id INT NOT NULL,
    user_id INT NOT NULL,
    comment TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;