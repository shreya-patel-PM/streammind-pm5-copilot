# AutoApply — Product Context Corpus

This file is the Researcher's grounding source in Phase 1 of the build.
In Phase 2 the Researcher swaps to a Notion API tool over the live roadmap;
the crew code does not change — only the retrieval source does.

## [C1] Saved jobs
Users can save postings from the Browse page. Saved items are stored in the
`saved_jobs` table with `posting_id` and `saved_at`. Saving is binary today
(save / unsave); there is no status field. The History page lists saved
items sorted by `saved_at`.

## [C2] Ghost-score classification
The classifier returns GHOST or REAL plus a one-sentence rationale. Three
deterministic signals are computed in `sql/features.sql`: repost frequency
over 90 days, posting age, and cross-board spread. The Analyze page
currently shows the score only.

## [C3] Repost detection
A repost event is detectable at ingest via the repost-frequency feature
view. Ingest runs as a daily batch, so detection latency is up to 24 hours.

## [C4] Notifications and email
No notification infrastructure is wired into AutoApply yet. Resend is used
elsewhere in the portfolio (PM Agent #4 competitive-intel digest) and is
the assumed provider if email is needed.

## [C5] Guardrails and UI principles
GUARDRAILS.md calls for calm UI (no alarmist red), an evidence panel
alongside the score, and sensitivity context so users can disagree with the
model. Verdicts must never be presented as certainties.

## [C6] Backlog / icebox
An "email digest" idea is parked in the icebox (weekly summary of saved-job
activity). It is adjacent to, but distinct from, event-driven notifications.
