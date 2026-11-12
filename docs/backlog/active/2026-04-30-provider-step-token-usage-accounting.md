# Provider Step Token Usage Accounting

> **2026-11-12 disposition: implemented** by Lane 2 of the
> [Phase 2 plan](../../plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#lane-2-token-and-cost-metering):
> every evaluated provider, agent-turn and phased attempt writes `usage.json`
> ([providers](../../../specs/providers.md#metered-templates-and-usage); opt-in `<name>_metered`
> templates report tokens), `--max-cost-usd` caps a run's spend, and `report`
> shows tokens and cost per provider step and for the run
> ([observability](../../../specs/observability.md#report-usage)). Not taken from the proposal
> below: the stderr `tokens used` fallback, per-step statistics, matching calls to the CLIs'
> session stores, and fields in run state (usage is a view beside each attempt, not memo authority).
> The notices below are history.

> **2026-11-11 disposition:** moved to [Phase 2](../../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-2-qualification-metering-and-stable-names) of the
> [current roadmap](../../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#dispositions); the rest of the backlog is archived.

Current disposition: **implemented (2026-11-12, see the notice above).**

Current owners: [lisp workflow drafting guide](../../lisp_workflow_drafting_guide.md), [workflow lisp evaluated execution](../../design/workflow_lisp_evaluated_execution.md), [cli](../../../specs/cli.md), [workflow lisp provider prompt dependencies](../../design/workflow_lisp_provider_prompt_dependencies.md), [workflow lisp provider call policy](../../design/workflow_lisp_provider_call_policy.md).
[Backlog status inventory](../README.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


Active backlog item.

## Problem

Provider-heavy workflows can identify which steps are expensive only by scraping provider logs after the fact. Codex currently prints a human-readable `tokens used` total in stderr, and local Codex JSONL sessions contain richer `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, and `total_tokens` fields, but the orchestrator does not capture those fields as step state.

That makes it hard to answer simple operational questions such as which provider step consumed the most total tokens, whether repeated review/fix cycles dominate a run, or whether a provider/model change shifted input versus output token cost.

## Desired Outcome

Each provider step visit records structured token usage in run state when the provider exposes it. Reports can aggregate usage by step name, step visit, workflow phase, and whole run without relying on timestamp matching against provider-private session files.

## Scope

- Add provider result/state fields for structured token usage:
  - `input_tokens`
  - `cached_input_tokens`
  - `output_tokens`
  - `reasoning_output_tokens`
  - `total_tokens`
  - `source`
- Teach the Codex provider path to capture structured usage from JSONL token-count events when run in structured mode.
- Preserve a fallback parser for existing human-readable `tokens used` stderr totals, clearly marked as total-only.
- Persist usage per provider step visit, including repeated loop/retry visits.
- Add a run-level report or status projection that summarizes total, mean, max, and visit count by step name.
- Document the provider capability and how workflows opt into structured usage capture.

## Non-Goals

- Do not infer step usage from `~/.codex/sessions` timestamps as the primary mechanism.
- Do not require every provider to support token accounting before Codex support lands.
- Do not change prompt content or workflow control flow to expose token usage.
- Do not make human-readable stderr scraping the authoritative contract for input/output splits.

## Candidate Design Direction

Add a provider usage capability that can be enabled independently of prompt behavior. For Codex, prefer `codex exec --json` or the existing JSONL metadata/session path, parse the latest `token_count.total_token_usage` event for the step, normalize provider stdout so JSONL transport events are not treated as assistant text, and attach the resulting usage object to the provider execution result.

If a workflow still uses plain Codex output, record only the parsed total from `tokens used` with a source such as `codex_stderr_total_only`.

## Acceptance Criteria

- A mocked Codex JSONL provider step records input, cached input, output, reasoning output, and total tokens in `state.json`.
- A looped provider step records usage per visit rather than overwriting earlier visits without audit trail.
- A status/report command can show total, mean, max, and visit count by provider step name.
- Plain stderr `tokens used` remains supported as a total-only fallback.
- Tests cover JSONL parsing, fallback parsing, state persistence, and aggregation across repeated step visits.
- Documentation explains that provider-private session files are useful for forensic recovery but are not the workflow accounting source of truth.
