import sqlite3
import os
import csv
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nerv.db"
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "accounts_overdue.csv"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # System runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        mode TEXT DEFAULT 'auto',
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        finished_at TEXT,
        summary TEXT
    )
    """)

    # Tasks broken down by Manager Agent & Jev Dispatcher
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        title TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        route_tier TEXT DEFAULT 'code',
        input_data TEXT,
        output_data TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (run_id) REFERENCES runs (id)
    )
    """)

    # Human-in-the-loop approvals
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        task_id TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        risk_level TEXT DEFAULT 'high',
        amount_inr REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decision_channel TEXT,
        FOREIGN KEY (run_id) REFERENCES runs (id)
    )
    """)

    # Audit trail: full transparency, timestamped, logging every decision & why
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        agent TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        tool_name TEXT,
        model_tier TEXT DEFAULT 'code',
        tokens_saved INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ok'
    )
    """)

    # Customer accounts database for tools
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        amount_inr REAL NOT NULL,
        due_date TEXT NOT NULL,
        days_overdue INTEGER NOT NULL,
        contact_email TEXT,
        phone TEXT,
        status TEXT DEFAULT 'overdue'
    )
    """)

    # Sent messages/emails log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sent_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        recipient_email TEXT NOT NULL,
        recipient_name TEXT,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        tone TEXT,
        timestamp TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    seed_accounts()

def seed_accounts(force=False):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM accounts")
    count = cursor.fetchone()[0]

    if count == 0 or force:
        cursor.execute("DELETE FROM accounts")
        if force:
            cursor.execute("DELETE FROM approvals")
            cursor.execute("DELETE FROM runs")
            cursor.execute("DELETE FROM sent_messages")
        if CSV_PATH.exists():
            with open(CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cursor.execute("""
                    INSERT INTO accounts (account_id, customer_name, invoice_number, amount_inr, due_date, days_overdue, contact_email, phone, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["account_id"],
                        row["customer_name"],
                        row["invoice_number"],
                        float(row["amount_inr"]),
                        row["due_date"],
                        int(row["days_overdue"]),
                        row["contact_email"] if row["contact_email"] else None,
                        row["phone"],
                        row["status"]
                    ))
        conn.commit()
    conn.close()

def log_audit(run_id: str, agent: str, action: str, details: str, tool_name: str = None, model_tier: str = "code", tokens_saved: int = 0, status: str = "ok"):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO audit_log (run_id, timestamp, agent, action, details, tool_name, model_tier, tokens_saved, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, now, agent, action, details, tool_name, model_tier, tokens_saved, status))
    conn.commit()
    conn.close()

def get_audit_trail(run_id: str = None, limit: int = 100):
    conn = get_db()
    cursor = conn.cursor()
    if run_id:
        cursor.execute("SELECT * FROM audit_log WHERE run_id = ? ORDER BY id DESC LIMIT ?", (run_id, limit))
    else:
        cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_pending_approvals():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_accounts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts ORDER BY days_overdue DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
