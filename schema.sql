CREATE DATABASE IF NOT EXISTS ledger_practise;
USE ledger_practise;

CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    balance DECIMAL(12,2) NOT NULL DEFAULT 0,
    user_id INT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (balance >= 0),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS transfers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    from_account_id INT NOT NULL,
    to_account_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status ENUM('created','pending','processing','completed','failed','partially_refunded','refunded')
        NOT NULL DEFAULT 'created',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (amount > 0),
    CHECK (from_account_id <> to_account_id),
    FOREIGN KEY (from_account_id) REFERENCES accounts(id),
    FOREIGN KEY (to_account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS refunds (
    id INT PRIMARY KEY AUTO_INCREMENT,
    transfer_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    idem_key VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (amount > 0),
    FOREIGN KEY (transfer_id) REFERENCES transfers(id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INT PRIMARY KEY AUTO_INCREMENT,
    transfer_id INT NOT NULL,
    refund_id INT NULL,
    account_id INT NOT NULL,
    type ENUM('debit','credit') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (amount > 0),
    FOREIGN KEY (transfer_id) REFERENCES transfers(id),
    FOREIGN KEY (refund_id) REFERENCES refunds(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id INT PRIMARY KEY AUTO_INCREMENT,
    idem_key VARCHAR(64) NOT NULL UNIQUE,
    request_hash VARCHAR(100) NOT NULL,
    transfer_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transfer_id) REFERENCES transfers(id)
);

CREATE TABLE IF NOT EXISTS transfer_status_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    transfer_id INT NOT NULL,
    old_status VARCHAR(20) NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transfer_id) REFERENCES transfers(id)
);