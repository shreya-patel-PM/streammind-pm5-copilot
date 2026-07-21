#!/usr/bin/env python3
"""
PM Copilot — sequential crew: Researcher → Analyst → Writer → human gate.

Usage:
    python crew.py "Users keep missing when their saved jobs get reposted. We should notify them somehow."
    python crew.py --mock "any ask"        # pipeline test, no API calls
    python crew.py --yes --mock "..."      # non-interactive: auto-approve (CI)

Model routing (the cost lever): Haiku 4.5 on Researcher + Analyst,
Sonnet 4.6 on the Writer only.

Live mode needs: pip install -r requirements.txt  +  ANTHROPIC_API_KEY set.
Mock mode needs nothing — it exercises validation, rendering, the gate, and
the feedback log with canned crew outputs.
"""
import argparse
import difflib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from prompts import (
    RESEARCHER, ANALYST, WRITER,
    researcher_task, analyst_task, writer_task,
    RESEARCHER_EXPECTED, ANALYST_EXPECTED, WRITER_EXPECTED,
)
from validate import parse_story, validate_story, render_markdown

ROOT = Path(__file__).parent
CONTEXT_PATH = ROOT / "product_context.md"
FEEDBACK_LOG = ROOT / "feedback_log.json"
DRAFT_PATH = ROOT / "draft_story.md"

HAIKU = "anthropic/claude-haiku-4-5"
SONNET = "anthropic/claude-sonnet-4-6"


# ── live pipeline ────────────────────────────────────────────────────────

def run_live(ask: str, corpus: str):
    """Run the real CrewAI crew. Imported lazily so mock mode has no deps."""
    from crewai import Agent, Task, Crew, Process, LLM

    haiku = LLM(model=HAIKU, temperature=0.2)
    sonnet = LLM(model=SONNET, temperature=0.3)

    researcher = Agent(llm=haiku, verbose=True, allow_delegation=False, **RESEARCHER)
    analyst = Agent(llm=haiku, verbose=True, allow_delegation=False, **ANALYST)
    writer = Agent(llm=sonnet, verbose=True, allow_delegation=False, **WRITER)

    t_research = Task(
        description=researcher_task(ask, corpus),
        expected_output=RESEARCHER_EXPECTED,
        agent=researcher,
    )
    t_analyze = Task(
        description=analyst_task(ask),
        expected_output=ANALYST_EXPECTED,
        agent=analyst,
        context=[t_research],
    )
    t_write = Task(
        description=writer_task(ask),
        expected_output=WRITER_EXPECTED,
        agent=writer,
        context=[t_research, t_analyze],
    )

    crew = Crew(
        agents=[researcher, analyst, writer],
        tasks=[t_research, t_analyze, t_write],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()
    return {
        "researcher": str(t_research.output),
        "analyst": str(t_analyze.output),
        "writer_raw": str(result),
    }


# ── mock pipeline (no API calls) ─────────────────────────────────────────

MOCK_WRITER_JSON = {
    "title": "Saved Jobs – Repost Notification Email",
    "story": (
        "As a job seeker, I want to receive an email when a job I saved is "
        "reposted, so that I can decide whether it's still worth applying to."
    ),
    "acs": [
        {
            "id": "AC1",
            "name": "Repost Notification Sent",
            "given": "a job seeker has a saved job that is detected as reposted",
            "when": "the daily check runs",
            "thens": [
                "The job seeker will receive one email per repost event.",
                "The email will link back to the posting with its current ghost-score.",
            ],
        },
        {
            "id": "AC2",
            "name": "Daily Cap Reached",
            "given": "a job seeker has reached the daily notification cap",
            "when": "further repost events are detected that day",
            "thens": [
                "The additional events will be held and included in the next day's email."
            ],
        },
        {
            "id": "ACE1",
            "name": "Job Unsaved Before Check",
            "given": "a job seeker unsaved the job before the daily check runs",
            "when": "repost detection fires for that posting",
            "thens": ["No notification will be sent for that job."],
        },
        {
            "id": "ACE2",
            "name": "Posting Deleted",
            "given": "a saved job's posting is deleted after a repost is detected",
            "when": "the notification email is generated",
            "thens": [
                "The item will be omitted from the email.",
                "A skip event will be logged with user ID, posting ID, and timestamp (UTC).",
            ],
        },
    ],
    "assumptions_carried": [
        "A1 — Email is the right channel; no channel-preference data exists.",
        "A2 — Daily cadence is acceptable given batch ingest.",
        "A3 — Cap value (N emails/day) is a PM call, not derivable from data.",
    ],
}


def run_mock(ask: str, corpus: str):
    return {
        "researcher": (
            "- Saved jobs exist; stored in saved_jobs (posting_id, saved_at) (C1)\n"
            "- Repost detection exists via the features view; daily batch, "
            "up to 24h latency (C2, C3)\n"
            "- No notification infrastructure wired; Resend assumed (C4)\n"
            "- Adjacent icebox item: weekly email digest — distinct from "
            "event-driven notification (C6)"
        ),
        "analyst": (
            "IN SCOPE:\n- Email notification on repost of a saved job\n"
            "- Per-user daily cap\n- Link back to posting with ghost-score\n"
            "OUT OF SCOPE:\n- Push/in-app notifications\n- Real-time detection\n"
            "EDGE CASES:\n- Unsaved before check\n- Posting deleted before send\n"
            "DEPENDENCIES:\n- Repost signal (sql/features.sql)\n- Resend\n"
            "ASSUMPTIONS:\nA1 — Email is the right channel; no channel-preference data exists.\n"
            "A2 — Daily cadence is acceptable given batch ingest.\n"
            "A3 — Cap value (N emails/day) is a PM call, not derivable from data."
        ),
        "writer_raw": json.dumps(MOCK_WRITER_JSON),
    }


# ── human gate + feedback signal ─────────────────────────────────────────

def human_gate(markdown: str, warnings, auto_approve: bool):
    """Return (decision, final_text). Decision: accepted | edited | rejected."""
    DRAFT_PATH.write_text(markdown, encoding="utf-8")
    print("\n" + "=" * 72)
    print("DRAFT STORY (also written to draft_story.md)")
    print("=" * 72)
    print(markdown)
    if warnings:
        print("Self-check warnings (style — human judgment):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()
    if auto_approve:
        print("[--yes] auto-approving.")
        return "accepted", markdown

    while True:
        choice = input(
            "[a]pprove as-is / [e]dit draft_story.md then confirm / [r]eject: "
        ).strip().lower()
        if choice == "a":
            return "accepted", markdown
        if choice == "e":
            input("Edit draft_story.md in your editor, save, then press Enter... ")
            edited = DRAFT_PATH.read_text(encoding="utf-8")
            if edited == markdown:
                print("No changes detected — logging as accepted.")
                return "accepted", markdown
            return "edited", edited
        if choice == "r":
            return "rejected", markdown
        print("Please enter a, e, or r.")


def log_feedback(entry: dict):
    """Append to the feedback log — the accepted-vs-edited eval signal.
    Phase 2 swaps this file for the Supabase feedback store; the entry
    shape stays the same."""
    log = []
    if FEEDBACK_LOG.exists():
        try:
            log = json.loads(FEEDBACK_LOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    log.append(entry)
    FEEDBACK_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")


def edit_summary(original: str, edited: str) -> str:
    diff = list(
        difflib.unified_diff(
            original.splitlines(), edited.splitlines(), lineterm="", n=0
        )
    )
    changed = [l for l in diff if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return f"{len(changed)} changed lines"


# ── entrypoint ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="PM Copilot crew")
    ap.add_argument("ask", help="Rough one-line feature ask")
    ap.add_argument("--mock", action="store_true", help="No API calls; canned crew outputs")
    ap.add_argument("--yes", action="store_true", help="Auto-approve at the gate (CI)")
    args = ap.parse_args()

    corpus = CONTEXT_PATH.read_text(encoding="utf-8")
    t0 = time.time()

    print(f"\n▸ ask: {args.ask}")
    print(f"▸ mode: {'MOCK (no API calls)' if args.mock else 'LIVE'}")
    print(f"▸ routing: Researcher+Analyst → {HAIKU} · Writer → {SONNET}\n")

    outputs = run_mock(args.ask, corpus) if args.mock else run_live(args.ask, corpus)

    print("─" * 72)
    print("STAGE 1 · RESEARCHER — context brief\n" + outputs["researcher"])
    print("─" * 72)
    print("STAGE 2 · ANALYST — scoped spec\n" + outputs["analyst"])
    print("─" * 72)

    # Programmatic self-check (skill Phase 4) — reject over repair.
    try:
        story = parse_story(outputs["writer_raw"])
    except ValueError as e:
        print(f"✗ GATE BLOCKED — Writer output unparseable: {e}")
        sys.exit(1)

    errors, warnings = validate_story(story)
    if errors:
        print("✗ GATE BLOCKED — structural self-check failed (reject, not repair):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print("STAGE 3 · WRITER — self-check passed "
          f"({len(warnings)} warning{'s' if len(warnings) != 1 else ''})")

    markdown = render_markdown(story)
    decision, final_text = human_gate(markdown, warnings, args.yes)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ask": args.ask,
        "mode": "mock" if args.mock else "live",
        "decision": decision,
        "self_check_warnings": warnings,
        "duration_s": round(time.time() - t0, 1),
    }
    if decision == "edited":
        entry["edit_summary"] = edit_summary(markdown, final_text)
        entry["edited_text"] = final_text
    log_feedback(entry)

    print(f"\n✓ decision: {decision.upper()} — logged to {FEEDBACK_LOG.name} "
          "(the accepted-vs-edited eval signal)")


if __name__ == "__main__":
    main()
