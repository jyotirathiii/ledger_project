# Ledger_project: Payment Backend

A payment backend built around a double-entry ledger, safe retries and refunds.

## Features
- Double-entry ledger (every transfer writes a debit and a credit entry)
- Atomic transfers (commit / rollback)
- Idempotent payment API (Idempotency-Key header)
- Signup / login with bcrypt password hashing and JWT
- Transfer state machine with status history
- Partial and full refunds with limit checks

## Tech Stack
Python, FastAPI, MySQL

## Setup
1. `pip3 install -r requirements.txt`
2. Create a MySQL database and run `schema.sql`
3. Copy `.env.example` to `.env` and fill in your values
4. `python3 -m uvicorn main:app --reload`
5. Open `http://127.0.0.1:8000/docs`

## Design notes
- Ledger entries are never edited or deleted. A refund adds new reverse entries.
- Duplicate requests with the same Idempotency-Key return the first result.
- Money is stored as DECIMAL, never FLOAT.