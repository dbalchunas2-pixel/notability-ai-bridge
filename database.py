"""
SQLite database layer for Notability MCP SaaS.
Stores users, OAuth tokens, and usage logs.
Uses WAL mode for concurrent read/write on Railway volume.
"""

import os
import sqlite3
import secrets
import time
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

logger = logging.getLogger("notability-mcp-db")

DB_PATH = os.environ.get("DB_PATH", os.environ.get("DATA_DIR", "/data") + "/notability_saas.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    plan TEXT DEFAULT 'free',
    created_at TEXT DEFAULT (datetime('now')),
    stripe_customer_id TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expiry TEXT,
    drive_folder_id TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    tool_name TEXT NOT NULL,
    called_at TEXT DEFAULT (datetime('now')),
    params_summary TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    email TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_log(user_id, called_at);
CREATE INDEX IF NOT EXISTS idx_usage_tool ON usage_log(tool_name);
"""

# Plan limits: tool calls per day
PLAN_LIMITS = {
    "free": 50,
    "pro": 1000,
    "unlimited": -1,  # no limit
}


def init_db():
    """Initialize database with schema. Called on startup."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Enable WAL for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    logger.info(f"Database initialized at {DB_PATH}")


@contextmanager
def get_conn():
    """Get a SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_api_key() -> str:
    """Generate a secure API key."""
    return "nb_" + secrets.token_urlsafe(32)


def create_user(email: str) -> dict:
    """Create a new user with an API key."""
    api_key = generate_api_key()
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, api_key, plan) VALUES (?, ?, 'free')",
            (email, api_key)
        )
        user_id = cursor.lastrowid
        return {"id": user_id, "email": email, "api_key": api_key, "plan": "free"}


def get_user_by_api_key(api_key: str) -> dict | None:
    """Look up a user by their API key."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE api_key = ? AND status = 'active'",
            (api_key,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    """Look up a user by ID."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def store_oauth_token(user_id: int, access_token: str, refresh_token: str,
                      expires_in: int, drive_folder_id: str = ""):
    """Store or update OAuth tokens for a user."""
    expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO oauth_tokens (user_id, access_token, refresh_token, token_expiry, drive_folder_id, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                token_expiry = excluded.token_expiry,
                drive_folder_id = excluded.drive_folder_id,
                updated_at = datetime('now')
        """, (user_id, access_token, refresh_token, expiry, drive_folder_id))


def get_oauth_token(user_id: int) -> dict | None:
    """Get stored OAuth tokens for a user."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def update_access_token(user_id: int, access_token: str, expires_in: int):
    """Update just the access token after refresh."""
    expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE oauth_tokens SET access_token = ?, token_expiry = ?, updated_at = datetime('now') WHERE user_id = ?",
            (access_token, expiry, user_id)
        )


def log_usage(user_id: int, tool_name: str, params_summary: str = "", duration_ms: int = 0):
    """Log a tool call for usage tracking."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO usage_log (user_id, tool_name, params_summary, duration_ms) VALUES (?, ?, ?, ?)",
            (user_id, tool_name, params_summary, duration_ms)
        )


def get_usage_today(user_id: int) -> int:
    """Get count of tool calls today for a user."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND called_at >= date('now')",
            (user_id,)
        ).fetchone()
        return row["cnt"] if row else 0


def get_usage_stats(user_id: int, days: int = 30) -> dict:
    """Get usage statistics for a user."""
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]
        by_tool = conn.execute(
            "SELECT tool_name, COUNT(*) as cnt FROM usage_log WHERE user_id = ? GROUP BY tool_name ORDER BY cnt DESC",
            (user_id,)
        ).fetchall()
        last_30 = conn.execute(
            "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND called_at >= date('now', '-30 days')",
            (user_id,)
        ).fetchone()["cnt"]
        return {
            "total_calls": total,
            "last_30_days": last_30,
            "by_tool": {r["tool_name"]: r["cnt"] for r in by_tool},
        }


def check_rate_limit(user_id: int, plan: str) -> tuple[bool, str]:
    """Check if user has hit their daily rate limit.
    Returns (allowed, message).
    """
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    if limit == -1:
        return True, "unlimited"
    used = get_usage_today(user_id)
    if used >= limit:
        return False, f"Daily limit reached ({used}/{limit}). Upgrade to Pro for 1000 calls/day."
    return True, f"{used}/{limit} calls today"


def create_oauth_state(email: str) -> str:
    """Create a unique OAuth state parameter for CSRF protection."""
    state = secrets.token_urlsafe(24)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, email) VALUES (?, ?)",
            (state, email)
        )
    return state


def validate_oauth_state(state: str) -> str | None:
    """Validate an OAuth state and return the associated email. Deletes used states."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM oauth_states WHERE state = ?", (state,)
        ).fetchone()
        if not row:
            return None
        # Delete used state (single-use)
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        email = row["email"]
        # Clean up old states (>1 hour old)
        conn.execute("DELETE FROM oauth_states WHERE created_at < datetime('now', '-1 hour')")
        return email


def update_user_plan(user_id: int, plan: str, stripe_customer_id: str = ""):
    """Update a user's plan (e.g., after Stripe payment)."""
    with get_conn() as conn:
        if stripe_customer_id:
            conn.execute(
                "UPDATE users SET plan = ?, stripe_customer_id = ? WHERE id = ?",
                (plan, stripe_customer_id, user_id)
            )
        else:
            conn.execute(
                "UPDATE users SET plan = ? WHERE id = ?",
                (plan, user_id)
            )


def regenerate_api_key(user_id: int) -> str:
    """Generate a new API key for a user."""
    new_key = generate_api_key()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET api_key = ? WHERE id = ?",
            (new_key, user_id)
        )
    return new_key
