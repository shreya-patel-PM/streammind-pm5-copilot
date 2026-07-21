# PM Copilot

**Multi-Agent Product-Story Generator | Flagship #4 | StreamMind portfolio | Shreya Patel**

A Slack bot that turns a rough one-line feature ask into a developer-ready user story — grounded, scoped, validated, and gated by a human before anything is committed.

Not a single prompt in a wrapper. A real CrewAI crew: Researcher → Analyst → Writer, with visible hand-offs, a programmatic self-check, and an approve/edit/reject gate.

🎯 **[Live demo](https://streammind-pm5-copilot-demo.vercel.app)** — try any feature ask, watch the crew work

---

## How it works

PM types in Slack: *"Users keep missing when their saved jobs get reposted."*

- **RESEARCHER** (Haiku 4.5) → gathers context, constraints, dependencies
- **ANALYST** (Haiku 4.5) → scopes: in/out, edge cases, assumptions (A1, A2...)
- **WRITER** (Sonnet 4.6) → drafts story + AC/ACE in create-user-story format
- **SELF-CHECK** (code) → structural hard fail / style warnings — reject over repair
- **HUMAN GATE** → Approve ✅ / Edit ✏️ / Reject ❌ — nothing ships without you

**30-50 seconds. ~$0.02 per run. Works for any domain.**

---

## Live surfaces

| Surface | What it does |
|---------|-------------|
| **Slack bot** (@PM Copilot) | PMs type asks, get story cards with approve/edit/reject buttons |
| **[Vercel demo](https://streammind-pm5-copilot-demo.vercel.app)** | Interactive front-end with visible hand-offs and icons |
| **[Railway API](https://pm-copilot.up.railway.app/api/health)** | Flask API serving both Slack and Vercel |
| **Supabase** | Persists feedback decisions + conversation memory |

---

## Evaluation — real numbers

Scored with an LLM-as-judge rubric across **15 asks in 5 categories** (grounded, partially grounded, ungrounded, scope-trap, adversarial):

| Dimension | Score |
|-----------|-------|
| Testability | **4.27** / 5 |
| Completeness | **4.13** / 5 |
| Grounding | **3.73** / 5 |
| Clarity | **3.66** / 5 |
| Scope fidelity | **2.66** / 5 |
| **Overall** | **3.69 / 5** |

Scope fidelity (2.66) is the identified tuning target — documented, not hidden.

### Ablation: crew vs single call

| Metric | Crew (3 calls) | Single (1 call) |
|--------|---------------|------------------|
| Overall avg | 3.69 | 4.20 |
| Latency | 49.4s | 22.4s |
| Structural pass rate | **93%** | 67% |
| Adversarial "Make it better" | **4.4** | 2.2 |

The single call wins on average. The crew wins where it matters: adversarial asks (+2.2 delta) and structural validity (93% vs 67%).

---

## Repository layout

| File | Purpose |
|------|--------|
| `slack_app.py` | Slack bot + Flask API (combined server) |
| `crew.py` | CLI pipeline — mock + live modes |
| `prompts.py` | Agent roles + task prompts (Writer embeds skill contract) |
| `validate.py` | create-user-story self-check as code |
| `eval_rubric.py` | LLM-as-judge rubric scorer (5 dimensions) |
| `run_golden_set.py` | Batch runner — crew + single-call + ablation |
| `supabase_store.py` | Feedback log + conversation memory |
| `product_context.md` | Researcher grounding corpus |
| `ARCHITECTURE.md` | Runtime topology, model routing, cost table |
| `GUARDRAILS.md` | HITL gate, grounding chain, red-team log |
| `evals/golden_asks.json` | 15 asks × 5 categories with reference stories |
| `evals/results/` | Crew run outputs + rubric scores |
| `evals/results_single/` | Single-call outputs for ablation |
| `evals/eval_summary.csv` | Full benchmark results |
| `evals/ablation_summary.csv` | Crew vs single-call comparison |

---

## Quick start

**Mock mode** (no API key needed):
```bash
python crew.py --mock "Users keep missing when their saved jobs get reposted."
```

**Live mode**:
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python crew.py "Let people snooze a saved job instead of deleting it."
```

**Golden set benchmark**:
```bash
python run_golden_set.py              # full crew run + scoring
python run_golden_set.py --ablation   # crew vs single-call comparison
```

**Slack bot locally** (set env vars for Slack, Supabase, and Anthropic first):
```bash
python slack_app.py
```

---

## Design decisions

| Decision | Chose | Over | Why |
|----------|-------|------|-----|
| Pipeline | Fixed sequential | Manager-delegated | Task order is known; delegation adds risk |
| Routing | Haiku ×2 + Sonnet ×1 | Sonnet ×3 | 60% cost reduction |
| Output | create-user-story skill | Ad hoc prompt | Programmatic validation |
| Validation | Reject over repair | Auto-correct | Failing loud is safer |
| Gate | After Writer | After each agent | One checkpoint is enough |

---

## Key documents

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Runtime topology, model routing, cost table, eval plan
- **[GUARDRAILS.md](GUARDRAILS.md)** — HITL gate, grounding chain, red-team log, failure modes

---

*Built Weeks 16–17 · StreamMind 2026 · [Portfolio](https://github.com/shreya-patel-PM)*
