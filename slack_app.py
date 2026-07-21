#!/usr/bin/env python3
"""
PM Copilot — Slack bot + Web API combined.

Runs both:
  - Slack Socket Mode handler for DMs and @mentions
  - Flask HTTP server for health checks and the Vercel front-end API

Environment variables:
    SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_APP_TOKEN
    ANTHROPIC_API_KEY
    SUPABASE_URL, SUPABASE_KEY (optional)
    PORT (default 3000)
"""
import json
import os
import time
import threading
from pathlib import Path
from flask import Flask, request as flask_request, jsonify


from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from prompts import (
    researcher_task, analyst_task, writer_task,
    RESEARCHER, ANALYST, WRITER,
    RESEARCHER_EXPECTED, ANALYST_EXPECTED, WRITER_EXPECTED,
)
from validate import parse_story, validate_story, render_markdown

# Supabase is optional
try:
    from supabase_store import log_feedback, save_memory, get_recent_memory
    _has_supabase = True
except Exception:
    _has_supabase = False

def _safe_log_feedback(entry):
    if _has_supabase:
        try: log_feedback(entry); return
        except Exception as e: print(f"  [supabase] feedback log failed: {e}")
    print(f"  [feedback] {entry.get('decision','?')} — {entry.get('ask','')[:60]}")

def _safe_save_memory(user_id, channel_id, ask, story):
    if _has_supabase:
        try: save_memory(user_id, channel_id, ask, story); return
        except Exception as e: print(f"  [supabase] memory save failed: {e}")

def _safe_get_memory(user_id, channel_id, limit=3):
    if _has_supabase:
        try: return get_recent_memory(user_id, channel_id, limit)
        except Exception as e: print(f"  [supabase] memory read failed: {e}")
    return []

ROOT = Path(__file__).parent
CONTEXT_PATH = ROOT / "product_context.md"
HAIKU = "anthropic/claude-haiku-4-5"
SONNET = "anthropic/claude-sonnet-4-6"

# ── Slack app ────────────────────────────────────────────────────────────

slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# ── Flask app (health + API) ─────────────────────────────────────────────

flask_app = Flask(__name__)
@flask_app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@flask_app.route('/api/crew', methods=['OPTIONS'])
def crew_options():
    response = flask_app.make_response('')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@flask_app.route("/")
def root():
    return jsonify({"status": "ok", "service": "pm-copilot"}), 200

@flask_app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "pm-copilot"}), 200

@flask_app.route("/api/crew", methods=["POST"])
def crew_endpoint():
    data = flask_request.get_json()
    if not data or not data.get("ask") or len(data["ask"].strip()) < 5:
        return jsonify({"error": "Ask must be at least 5 characters"}), 400

    ask = data["ask"].strip()
    corpus = CONTEXT_PATH.read_text(encoding="utf-8")

    print(f"\n▸ [API] Crew starting for: {ask[:60]}...")
    t0 = time.time()

    try:
        outputs = run_crew(ask, corpus)
        duration = round(time.time() - t0, 1)
        print(f"  ✓ [API] Crew completed in {duration}s")

        story = parse_story(outputs["writer_raw"])
        errors, warnings = validate_story(story)
        print(f"  ✓ [API] Validation: {len(errors)} errors, {len(warnings)} warnings")

        if errors:
            return jsonify({"error": "Self-check failed", "errors": errors}), 422

        return jsonify({
            "ask": ask,
            "story": story,
            "researcher_brief": outputs["researcher"],
            "analyst_spec": outputs["analyst"],
            "validation": {"errors": errors, "warnings": warnings, "passed": True},
            "duration_s": duration,
            "model_routing": {"researcher": "Haiku 4.5", "analyst": "Haiku 4.5", "writer": "Sonnet 4.6"},
        })

    except Exception as e:
        print(f"  ✗ [API] Crew failed: {e}")
        return jsonify({"error": str(e)[:300]}), 500


# ── Crew runner ──────────────────────────────────────────────────────────

def run_crew(ask, corpus):
    from crewai import Agent, Task, Crew, Process, LLM

    haiku = LLM(model=HAIKU, temperature=0.2)
    sonnet = LLM(model=SONNET, temperature=0.3)

    researcher = Agent(llm=haiku, verbose=False, allow_delegation=False, **RESEARCHER)
    analyst = Agent(llm=haiku, verbose=False, allow_delegation=False, **ANALYST)
    writer = Agent(llm=sonnet, verbose=False, allow_delegation=False, **WRITER)

    t_research = Task(description=researcher_task(ask, corpus), expected_output=RESEARCHER_EXPECTED, agent=researcher)
    t_analyze = Task(description=analyst_task(ask), expected_output=ANALYST_EXPECTED, agent=analyst, context=[t_research])
    t_write = Task(description=writer_task(ask), expected_output=WRITER_EXPECTED, agent=writer, context=[t_research, t_analyze])

    crew = Crew(agents=[researcher, analyst, writer], tasks=[t_research, t_analyze, t_write], process=Process.sequential, verbose=False)
    result = crew.kickoff()
    return {"researcher": str(t_research.output), "analyst": str(t_analyze.output), "writer_raw": str(result)}


# ── Slack message formatting ─────────────────────────────────────────────

def format_story_blocks(story, warnings, duration):
    title = story.get("title", "Untitled")
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📋 {title}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Story:* {story.get('story','')}"}},
        {"type": "divider"},
    ]
    ac_lines = []
    for ac in story.get("acs", []):
        prefix = "🟢" if not ac["id"].startswith("ACE") else "🟡"
        thens = "\n".join(f"  • {t}" for t in ac.get("thens", []))
        ac_lines.append(f"{prefix} *{ac['id']}- {ac['name']}*\n  *GIVEN* {ac['given']}\n  *WHEN* {ac['when']}\n  *THEN:*\n{thens}")
    ac_text = "\n\n".join(ac_lines)
    if len(ac_text) > 2800:
        mid = len(ac_lines) // 2
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(ac_lines[:mid])}})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(ac_lines[mid:])}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": ac_text}})
    assumptions = story.get("assumptions_carried", [])
    if assumptions:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Assumptions:*\n" + "\n".join(f"• {a}" for a in assumptions)}})
    if warnings:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "⚠️ " + " | ".join(warnings)}]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"⏱ {duration}s · Haiku×2 + Sonnet×1"}]})
    blocks.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True}, "style": "primary", "action_id": "approve_story"},
        {"type": "button", "text": {"type": "plain_text", "text": "✏️ Needs edits", "emoji": True}, "action_id": "needs_edits"},
        {"type": "button", "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True}, "style": "danger", "action_id": "reject_story"},
    ]})
    return blocks


# ── Slack handlers ───────────────────────────────────────────────────────

_pending = {}

@slack_app.event("app_mention")
def handle_mention(event, say, client):
    _handle_ask(event, say, client)

@slack_app.event("message")
def handle_dm(event, say, client):
    if event.get("channel_type") == "im" and not event.get("bot_id"):
        _handle_ask(event, say, client)

def _handle_ask(event, say, client):
    raw_text = event.get("text", "").strip()
    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    ask = raw_text.split(">", 1)[-1].strip() if "<@" in raw_text else raw_text

    if not ask or len(ask) < 5:
        say("Give me a rough feature ask. Example: _\"Users keep missing when their saved jobs get reposted.\"_")
        return

    ack_result = client.chat_postMessage(channel=channel_id, text=f"🔄 Running the crew on: _{ask}_\nResearcher → Analyst → Writer — ~30-50 seconds...")
    ack_ts = ack_result.get("ts") if ack_result.get("ok") else None

    def _run():
        try:
            print(f"\n▸ [Slack] Crew starting for: {ask[:60]}...")
            corpus = CONTEXT_PATH.read_text(encoding="utf-8")
            memory = _safe_get_memory(user_id, channel_id, limit=3)
            if memory:
                corpus += "\n\n## Recent asks:\n" + "\n".join(f"- \"{m['ask']}\" → {m['story_title']}" for m in reversed(memory))

            t0 = time.time()
            outputs = run_crew(ask, corpus)
            duration = round(time.time() - t0, 1)
            print(f"  ✓ [Slack] Crew completed in {duration}s")

            story = parse_story(outputs["writer_raw"])
            errors, warnings = validate_story(story)
            print(f"  ✓ [Slack] Validation: {len(errors)} errors, {len(warnings)} warnings")

            if errors:
                msg = f"❌ Self-check failed: {'; '.join(errors)}"
                if ack_ts: client.chat_update(channel=channel_id, ts=ack_ts, text=msg)
                else: client.chat_postMessage(channel=channel_id, text=msg)
                return

            blocks = format_story_blocks(story, warnings, duration)
            if ack_ts:
                result = client.chat_update(channel=channel_id, ts=ack_ts, text=f"📋 {story.get('title','Story')}", blocks=blocks)
                msg_ts = result.get("ts", ack_ts)
            else:
                result = client.chat_postMessage(channel=channel_id, text=f"📋 {story.get('title','Story')}", blocks=blocks)
                msg_ts = result.get("ts", "")

            _pending[msg_ts] = {"ask": ask, "story": story, "warnings": warnings, "duration_s": duration, "user_id": user_id, "channel_id": channel_id}
            _safe_save_memory(user_id, channel_id, ask, story)

        except Exception as e:
            print(f"  ✗ [Slack] Crew failed: {e}")
            msg = f"❌ Crew failed: {str(e)[:200]}"
            try:
                if ack_ts: client.chat_update(channel=channel_id, ts=ack_ts, text=msg)
                else: client.chat_postMessage(channel=channel_id, text=msg)
            except Exception: pass

    threading.Thread(target=_run, daemon=True).start()


def _handle_decision(ack, body, client, decision):
    ack()
    msg_ts = body.get("message", {}).get("ts", "")
    user = body.get("user", {}).get("username", "unknown")
    channel = body.get("channel", {}).get("id", "")
    pending = _pending.pop(msg_ts, None)
    if not pending:
        client.chat_postMessage(channel=channel, text="⚠️ Story context expired.", thread_ts=msg_ts)
        return
    _safe_log_feedback({"ask": pending["ask"], "mode": "slack", "decision": decision, "self_check_warnings": pending["warnings"], "duration_s": pending["duration_s"], "story": pending["story"], "slack_user": user, "slack_channel": channel})
    emoji = {"accepted": "✅", "edited": "✏️", "rejected": "❌"}[decision]
    label = {"accepted": "Approved", "edited": "Marked for edits", "rejected": "Rejected"}[decision]
    client.chat_postMessage(channel=channel, text=f"{emoji} *{label}* by @{user} — logged.", thread_ts=msg_ts)

@slack_app.action("approve_story")
def handle_approve(ack, body, client): _handle_decision(ack, body, client, "accepted")
@slack_app.action("needs_edits")
def handle_edits(ack, body, client): _handle_decision(ack, body, client, "edited")
@slack_app.action("reject_story")
def handle_reject(ack, body, client): _handle_decision(ack, body, client, "rejected")


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))

    # Start Slack Socket Mode in background
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if app_token:
        def _run_slack():
            print("  [Slack] Starting Socket Mode...")
            SocketModeHandler(slack_app, app_token).start()
        threading.Thread(target=_run_slack, daemon=True).start()
        print("  [Slack] Bot started in background")
    else:
        print("  [Slack] No SLACK_APP_TOKEN — bot disabled")

    # Start Flask as main process (serves health check + API)
    print(f"\n▸ PM Copilot starting on port {port}...")
    flask_app.run(host="0.0.0.0", port=port)