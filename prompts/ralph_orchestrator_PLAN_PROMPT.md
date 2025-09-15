# Ralph Planning Prompt: Derive and Prioritize fix_plan.md (Orchestrator DSL v1.1 / state 1.1.1)

You are Ralph in planning mode. This loop does NOT write code. It studies, inventories, and produces/updates `fix_plan.md` so that subsequent build loops can execute one item at a time.

Allocate the same stack every loop (do not skip):
- @SPEC: `MULTI_AGENT_ORCHESTRATION_V1.1_SPEC.md`
- @ACCEPTANCE: the “Acceptance Tests” section inside the spec
- @CODE: `src/` (implementation), `workflows/` (examples), `prompts/` (prompt files), `tests/` (if present)
- @PLAN: `fix_plan.md` (create if missing; keep prioritized)
- @AGENTS: `AGENTS.md` (how to run/build/test; keep concise and accurate)

Goal of this loop:
- Produce or refresh a prioritized, actionable `fix_plan.md` that maps spec requirements and acceptance tests to current implementation and coverage, with evidence and Definition of Done for each item.

Subagents policy:
- You may use up to 300 subagents for repository search and summarization (ripgrep, file scanning, summarizing spec sections, mapping tests to features).
- Use at most 1 subagent for any command that executes the application (e.g., smoke run of CLI) and avoid long builds. Preference is to infer from code/tests rather than executing.

Method (follow in order):
1) Extract acceptance items: Parse the “Acceptance Tests” list from the spec into a numbered set. Normalize each item to a single declarative statement.
2) Map to code/tests/examples: For each acceptance item, search the codebase for relevant modules, validators, CLI handlers, and example workflows. Capture file pointers (paths + line anchors) as evidence.
3) Categorize status: done (clear implementation + tests/examples), partial (some logic exists or tests incomplete), missing (no clear implementation or tests).
4) Define DoD per item: Link back to spec line(s) and describe how to verify (test or example workflow to run, expected state/log fields, exit codes). Keep it minimal and objective.
5) Identify dependencies: Note prerequisites among items (e.g., DSL validation before injection; path safety before depends_on).
6) Prioritize: Score items by impact, risk, and enabling power. Output a Top‑10 list first, then the full backlog.
7) Update artifacts: Overwrite `fix_plan.md` with the structured content below. Do not place runtime status in docs.

fix_plan.md structure (use this exact format):

```
# Orchestrator Fix Plan (v1.1 / state 1.1.1)

Legend: [ ] missing  [~] partial  [x] done  (status reflects implementation + tests)

## Top 10 Priorities
1. <title> — status: [ ], spec: <section/ref>, acceptance: <ids>, DoD: <one sentence>
   - Rationale: <impact/enabler>
   - Evidence: <paths or “none”>
   - Tasks:
     - <short actionable>
     - <short actionable>

## Backlog (by acceptance item)

### A<N>: <acceptance item short name>
- Status: [ ]|[~]|[x]
- Spec refs: <section ids or anchors>
- Acceptance IDs: <list>
- Evidence (code/tests/examples):
  - <path:line> — <note>
- Definition of Done:
  - <objective verification steps>
- Tasks:
  - <single-loop sized task>
  - <single-loop sized task>
- Risks/Notes: <any ambiguities to resolve>

### A<N+1>: ...

## Cross-cutting items
- Limits centralization (caps for stdout, json, injection) — status: [ ]
- Goto scoping in loops (define behavior + tests) — status: [ ]
- State schema consolidation (`error`, injection truncation fields) — status: [ ]

## Removed/Completed (history)
- <date> — <item> — reason
```

Evidence guidelines:
- Prefer concise references over pasted content (e.g., `src/validator/dsl.rs:120-170`).
- If a feature appears implemented but untested, mark status [~] and add a DoD task to add/verify tests/examples.

Don’ts:
- Don’t write code changes in this loop.
- Don’t remove items without evidence or replacement rationale.
- Don’t add runtime state to `AGENTS.md` or `fix_plan.md`.

Outputs of this loop (must produce all):
- Updated `fix_plan.md` per template (Top‑10 + Backlog + Cross‑cutting).
- A short summary (max 10 lines) of the highest‑impact next 3 items and why.

Next loop handoff:
- The next build loop should pick item #1 from Top‑10, quote its DoD, and implement only that one.

