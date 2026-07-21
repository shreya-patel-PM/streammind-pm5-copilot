# PM Copilot — Multi-Agent Product-Story Generator

Sequential CrewAI crew that turns a rough one-line feature ask into a
developer-ready user story with structured acceptance criteria — grounded,
scoped, validated, and gated by a human before anything is committed.

**Flagship #4 · StreamMind portfolio · real orchestration code, not a wrapper.**

```
rough ask → Researcher (Haiku 4.5) → Analyst (Haiku 4.5) → Writer (Sonnet 4.6)
                                                              │
                                              programmatic self-check (reject > repair)
                                                              │
                                                    human gate: approve / edit
                                                              │
                                              feedback_log.json (accepted-vs-edited signal)
```

## Repository layout

```
crew.py              pipeline: crew assembly, model routing, gate, feedback log
prompts.py           agent roles + task prompts; Writer embeds the
                     create-user-story skill contract (Phase 3, skip-questions mode)
validate.py          the skill's Phase 4 self-check as code: structural rules
                     are hard failures, style rules are warnings
product_context.md   Researcher's grounding corpus (Phase 1; Notion in Phase 2)
requirements.txt     pinned live-mode deps (mock mode is stdlib-only)
```

## Quick start

```bash
# Mock mode — full pipeline mechanics, zero API calls (mirrors the
# AutoApply CI pattern: mock on PRs, live on main)
python crew.py --mock "Users keep missing when their saved jobs get reposted. We should notify them somehow."

# Live mode
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python crew.py "Let people snooze a saved job instead of deleting it."

# Non-interactive (CI): auto-approve at the gate
python crew.py --mock --yes "any ask"
```

## Design decisions

- **Model routing is the cost lever.** Haiku 4.5 handles retrieval and
  scoping; Sonnet 4.6 is reserved for the final draft where wording quality
  matters. Routing strings live at the top of `crew.py`.
- **The Writer's output contract is the `create-user-story` skill.** The
  Researcher and Analyst *are* the skill's Phase 1–2 question rounds, so the
  Writer runs in skip-questions mode with grounded inputs. The condensed
  contract in `prompts.py` must stay in sync with the skill file.
- **Self-check is code, not hope.** The skill's Phase 4 checklist is split:
  structural rules (AC/ACE prefixes, ordering, sequential numbering, THEN
  bullet lists, ≤15 happy-path) hard-fail before the human ever sees the
  draft; style rules (named personas, single-action WHEN, future tense)
  surface as warnings at the gate. Reject over repair — a failing draft is
  never silently fixed.
- **The gate is structural.** No story exists without a human decision.
  Approve / edit / reject; edits are diffed and logged.
- **Feedback log = eval signal.** Every decision appends to
  `feedback_log.json` with warnings and edit summaries — the
  accepted-vs-edited signal that feeds the LLM-as-judge rubric
  (clarity, testability, scope fidelity, completeness, grounding).

## Build phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Crew core: three agents, routing, skill contract, validation, HITL gate, feedback log (this repo) | **Built — mock-verified end to end** |
| 2 | Researcher retrieval → Notion API roadmap tool; feedback log → Supabase store | Next |
| 3 | Slack Bolt surface + Railway deploy; conversation memory | Wk 17 |
| 4 | Wire the demo front-end (prototype built) to the live crew on Vercel | Wk 17 |

## Known constraints

- Live mode is untested until run with a real `ANTHROPIC_API_KEY`; the mock
  path exercises everything downstream of the model calls.
- CrewAI's `LLM` model strings route through litellm
  (`anthropic/claude-haiku-4-5`, `anthropic/claude-sonnet-4-6`). If a CrewAI
  version bump changes the expected format, adjust the two constants in
  `crew.py`.
- Grounding is only as good as `product_context.md` until Notion is wired —
  the same honest limitation named in the case study.
