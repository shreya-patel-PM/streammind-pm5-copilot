"""
PM Copilot — Supabase store for feedback logging and conversation memory.

Replaces feedback_log.json (Phase 1) with a persistent store.
Tables must be created in Supabase before first use — see setup_sql() below.

Requires: SUPABASE_URL and SUPABASE_KEY environment variables.
"""
import json
import os
from datetime import datetime, timezone

from supabase import create_client

_client = None


def get_client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set. "
                "Get them from your Supabase project settings → API."
            )
        _client = create_client(url, key)
    return _client


# ── Feedback log ─────────────────────────────────────────────────────────

def log_feedback(entry: dict):
    """Log a crew run decision (accepted/edited/rejected) to Supabase."""
    client = get_client()
    row = {
        "ask": entry.get("ask", ""),
        "mode": entry.get("mode", "live"),
        "decision": entry.get("decision", ""),
        "warnings": json.dumps(entry.get("self_check_warnings", [])),
        "duration_s": entry.get("duration_s", 0),
        "edit_summary": entry.get("edit_summary", ""),
        "story_json": json.dumps(entry.get("story", {})),
        "slack_user": entry.get("slack_user", ""),
        "slack_channel": entry.get("slack_channel", ""),
    }
    client.table("pm_copilot_feedback").insert(row).execute()


def get_feedback_stats():
    """Return accepted/edited/rejected counts."""
    client = get_client()
    result = client.table("pm_copilot_feedback").select("decision").execute()
    rows = result.data or []
    stats = {"accepted": 0, "edited": 0, "rejected": 0}
    for r in rows:
        d = r.get("decision", "")
        if d in stats:
            stats[d] += 1
    return stats


# ── Conversation memory ──────────────────────────────────────────────────

def save_memory(user_id: str, channel_id: str, ask: str, story_json: dict):
    """Save a completed run to conversation memory for follow-up context."""
    client = get_client()
    row = {
        "user_id": user_id,
        "channel_id": channel_id,
        "ask": ask,
        "story_title": story_json.get("title", ""),
        "story_json": json.dumps(story_json),
    }
    client.table("pm_copilot_memory").insert(row).execute()


def get_recent_memory(user_id: str, channel_id: str, limit: int = 5):
    """Retrieve recent asks + stories for conversation context."""
    client = get_client()
    result = (
        client.table("pm_copilot_memory")
        .select("ask, story_title, story_json, created_at")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Setup SQL ────────────────────────────────────────────────────────────

SETUP_SQL = """
-- Run this in Supabase SQL Editor (one time)

CREATE TABLE IF NOT EXISTS pm_copilot_feedback (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    ask TEXT NOT NULL,
    mode TEXT DEFAULT 'live',
    decision TEXT NOT NULL,
    warnings JSONB DEFAULT '[]',
    duration_s REAL DEFAULT 0,
    edit_summary TEXT DEFAULT '',
    story_json JSONB DEFAULT '{}',
    slack_user TEXT DEFAULT '',
    slack_channel TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pm_copilot_memory (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    ask TEXT NOT NULL,
    story_title TEXT DEFAULT '',
    story_json JSONB DEFAULT '{}'
);

-- Index for fast memory lookups
CREATE INDEX IF NOT EXISTS idx_memory_user_channel
    ON pm_copilot_memory (user_id, channel_id, created_at DESC);
"""


def print_setup_sql():
    """Print the SQL to create tables — run once in Supabase SQL Editor."""
    print(SETUP_SQL)


if __name__ == "__main__":
    print("Run this SQL in your Supabase project's SQL Editor:\n")
    print_setup_sql()
