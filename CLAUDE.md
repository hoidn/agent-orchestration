# CLAUDE.md — How to Run Ralph in This Repo

Purpose: Quick, minimal guide for running the Ralph loops and orienting within this repository. Keep this file concise and accurate. Do not put runtime status here.

Repo map
- Specs (normative): `specs/index.md` (entry), modules in `specs/*.md`
- Acceptance list: `specs/acceptance/index.md`
- Architecture (ADRs): `arch.md`
- Prompts: `prompts/ralph_orchestrator_PROMPT.md`, `prompts/ralph_orchestrator_PLAN_PROMPT.md`
- Planning backlog: `fix_plan.md` (create/maintain)

Quick start (Amp while-loops)
- Planning loop (derive/refresh fix_plan.md):
  `while :; do cat prompts/ralph_orchestrator_PLAN_PROMPT.md | npx --yes @sourcegraph/amp; sleep 1; done`
- Build loop (implement one acceptance item):
  `while :; do cat prompts/ralph_orchestrator_PROMPT.md | npx --yes @sourcegraph/amp; sleep 1; done`

Working method (succinct)
- Always read the relevant spec module(s) in `specs/` and the acceptance item first.
- Search before changing code: `rg -n "pattern"` across the repo.
- Do exactly one important item per loop; add/update targeted tests/examples for that item.
- Keep `fix_plan.md` up to date (Top‑10 + backlog); record evidence and DoD.
- Emit artifacts and logs as per specs when applicable; do not duplicate runtime info here.

Notes
- Use `arch.md` for implementation guidance when the spec is silent; if there is a conflict, prefer the spec and propose an `arch.md` update.
- This repo tracks the modular spec; implementation code may be in progress or external — tailor test/build steps accordingly.

Don’ts
- Don’t put runtime status or long logs in this file.
- Don’t weaken DSL/spec strictness to make demos pass; align with `specs/`.

