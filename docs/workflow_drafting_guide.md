# Workflow Drafting Guide

This guide is informative. The normative contracts live under `specs/` (start at `specs/index.md`).

Goal: help you author workflows that are reliable when prompts, deterministic artifacts, and control flow all interact.

## 1) Mental Model: Three Contracts

Treat a provider step as three separate contracts. Confusing them is the fastest way to write a workflow that "looks right" but fails in review.

| Contract | What it is | Where it lives |
| --- | --- | --- |
| Prompt contract | The instructions the provider receives. | `input_file` plus injected blocks (see below). |
| Runtime contract | What the orchestrator validates after execution. | `expected_outputs` or `output_bundle`. |
| Flow contract | What determines routing, looping, and termination. | `on.*.goto`, gates, and cycle caps. |

The key rule: satisfying the runtime contract does not imply the prompt contract was followed, and neither implies the flow contract routes the way you intended.

## 2) Provider Prompt Composition (What The Agent Actually Sees)

Provider prompt text is composed deterministically:

| Order | Step | Notes / knobs |
| --- | --- | --- |
| 1 | Read `input_file` literally. | No variable substitution inside file contents. |
| 2 | Apply `depends_on.inject` (v1.1.1+) if enabled. | Injects resolved dependencies in-memory; the workflow file does not change. |
| 3 | Inject `## Consumed Artifacts` (v1.2+) if the step has `consumes`. | `inject_consumes`, `consumes_injection_position`, `prompt_consumes`. Uses resolved consume values from preflight. |
| 4 | Append `## Output Contract` if the step has `expected_outputs`. | `inject_output_contract` controls suffix injection. This is validation, not execution. |

Practical implications: if you need dynamic prompt content, generate a file in a prior step and reference it; `consumes`/`publishes` handle lineage and preflight checks, not scope; and the `Output Contract` does not write files for the agent.

## 3) Deterministic Handoff Patterns

### A) `expected_outputs` (v1.1+, file-per-artifact)

Use when each deterministic value naturally maps to one file path (pointers, enums, counts, relpaths).

Why it works: the orchestrator can validate presence, type, and path safety (`under`, `must_exist_target`) without parsing prose.

### B) `output_bundle` (v1.3+, single JSON file)

Use when a step emits many scalar artifacts.

Summary:

| Pattern | Best for | Tradeoffs |
| --- | --- | --- |
| `expected_outputs` | A few values that naturally map to files (relpaths, enums, counts). | Simple and human-auditable; can create many small pointer files if overused. |
| `output_bundle` | Many scalar values at once. | Fewer files; stricter JSON discipline. |

## 4) Avoid Weak Gates

Common anti-pattern: a step "succeeds" because it wrote the required output files, even though the underlying work is incomplete.

This is not a bug; it's how the contracts are designed. The orchestrator can validate that files exist, but it cannot infer semantic completeness unless you encode it.

If your intent is root-cause closure, add an explicit gate that checks closure criteria before moving forward.

Example closure checks: a required command was executed (with machine-checkable evidence), fallbacks were not used for canonical requirements, required artifacts exist with expected profile/tag, and a review decision artifact says `APPROVE`.

Do not rely on review prose as the only enforcement mechanism. Route control flow using strict, published artifacts.

## 5) Prompt Authoring Guidance

Keep prompts focused on decision-quality instructions, not DSL plumbing.

| Do include | Usually avoid |
| --- | --- |
| Objective + scope boundaries. | Repeating file lists already injected via `depends_on.inject` or `consumes`. |
| Completion criteria (done vs blocked). | Repeating output contracts already injected via `expected_outputs`. |
| Forbidden shortcuts (when failure modes are predictable). | "Audit-only" language that can be mistaken for execution. |
| Evidence format (what files to write and where). | Over-specifying pointer plumbing already enforced by contracts. |

Exception: keep redundancy when the step is high-risk and you want belt-and-suspenders.

## 6) Recommended Loop Pattern

For execute/review/fix loops, separate "doing" from "deciding":

`Execute` -> `Checks` -> `Assess` -> `Review` -> `Gate` -> (`Fix` -> back to `Checks`)

Add at least one hard closure assertion step if "looks done" is not good enough.

## 7) Drafting Checklist

Before running a new workflow, confirm the basics:

| Area | Sanity check |
| --- | --- |
| Versioning | `version` gates the features you use (injection, dataflow, bundles). |
| Determinism | Use `expected_outputs` or `output_bundle` where deterministic handoff is needed. |
| Dataflow | `publishes.from` references a real produced artifact name; `consumes` matches real runtime dependencies. |
| Prompts | Prompt text does not conflict with injected blocks. |
| Control flow | Gates encode completion, not just "a file exists"; loops have bounded retries/cycles. |
| First run | Use `--debug` so you can inspect composed prompts. |

## 8) Debugging Where Things Go Wrong

Use run artifacts under `.orchestrate/runs/<run_id>/`:

| File | Why you care |
| --- | --- |
| `logs/<Step>.prompt.txt` | The fully composed provider prompt after injections. |
| `state.json` | Step results, errors, and parsed deterministic artifacts. |
| `logs/<Step>.stdout` / `logs/<Step>.stderr` | Provider/command traces (including truncation spillover). |

If behavior differs from prompt file content, inspect the composed `.prompt.txt` first.

## 9) Runtime Observability (No DSL Clutter)

Observability controls are intentionally runtime flags, not workflow syntax.

`--step-summaries` enables advisory per-step summaries. `--summary-mode async|sync` selects behavior (`async` is default and non-blocking; `sync` blocks step completion until summary output/error is written). `--summary-provider <provider>` selects the summarizer template.

Summary artifacts live under `.orchestrate/runs/<run_id>/summaries/`. They are not part of artifact contracts and must never gate workflow control flow.
