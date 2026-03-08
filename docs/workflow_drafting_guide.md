# Workflow Drafting Guide

This guide is informative. The normative contracts live under `specs/` (start at `specs/index.md`).
This guide is about DSL authoring choices, not runtime operations.

Companion docs:
- Concept model and terminology: `docs/orchestration_start_here.md`
- Runtime sequencing and step lifecycle: `docs/runtime_execution_lifecycle.md`

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

Pointer ownership note (v1.4): consume preflight for relpath artifacts is read-only and does not rewrite registry pointer files. If a command step needs deterministic consumed values, prefer `consume_bundle` JSON and read values from that bundle instead of relying on consume-time pointer mutation.

`expected_outputs` also supports optional guidance fields (`description`, `format_hint`, `example`) that are injected into the `Output Contract` block. Use them to reduce ambiguity for agent-written artifacts. They are prompt guidance only and do not change runtime validation rules.

`consumes` supports the same optional guidance fields (`description`, `format_hint`, `example`). When present, they are injected under each consumed artifact line in `## Consumed Artifacts` (subject to `prompt_consumes` filtering). They are prompt guidance only and do not change runtime consume preflight behavior.

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

Two practical upgrades now exist:
- v1.5: use first-class `assert` instead of shelling out to `test`, `jq`, or tiny one-line Python gates.
- v1.6: use typed predicates plus structured `ref:` for booleans, numeric thresholds, and recovered-failure routing instead of stringly `when.equals` hacks.
- v1.8: use `max_visits` and `max_transitions` instead of shell counters or ad hoc file-backed loop budgets when the goal is simply to cap a raw `goto` loop.
- v2.0: when authoring new typed predicates in nested scopes, use explicit `self.steps.*`, `parent.steps.*`, and `root.steps.*` refs and add stable step `id` values anywhere later refactors should preserve lineage or resume identity.
- v2.1: prefer typed workflow `inputs`/`outputs` over ad hoc `context` conventions when the value is part of the workflow boundary and should survive validation, resume, and later `call` reuse.
- v2.2: prefer top-level structured `if/else` when the workflow intent is branch selection rather than a reusable raw `goto` diamond.
- Task 10 reusable-call boundary: if a workflow is intended for later `call` reuse, keep bundled prompts/rubrics/schemas on the future workflow-source-relative asset surface (`asset_file`, `asset_depends_on`) and keep runtime reads/writes on the existing WORKSPACE-relative surfaces (`input_file`, `depends_on`, `output_file`, deterministic outputs).

## 5) Prompt Authoring Guidance

Keep prompts focused on decision-quality instructions, not DSL plumbing.

| Do include | Usually avoid |
| --- | --- |
| Objective + scope boundaries. | Repeating file lists already injected via `depends_on.inject` or `consumes`. |
| Completion criteria (done vs blocked). | Repeating output contracts already injected via `expected_outputs`. |
| Forbidden shortcuts (when failure modes are predictable). | "Audit-only" language that can be mistaken for execution. |
| Evidence format (what files to write and where). | Over-specifying pointer plumbing already enforced by contracts. |

Exception: keep redundancy when the step is high-risk and you want belt-and-suspenders.

### Keep Workflow Mechanics Out Of Prompts

Prompts should describe the task, scope, and required outputs from the agent's point of view. They should not teach the agent how the orchestrator works internally.

If correctness depends on runtime mechanics such as run-root ownership, pointer-file semantics, consume preflight, artifact publication, or protected state paths, prefer to encode that in workflow contracts or runtime behavior instead of prose.

Good prompt constraints are operational from the agent's point of view:
- what checkout to work in
- whether `git worktree` is allowed
- which files are in scope or out of scope
- which exact output path to write

Avoid prompt constraints that leak workflow/runtime implementation details:
- references to `.orchestrate/` internals unless the step is explicitly about debugging them
- explanations of pointer ownership or output validation internals
- instructions framed in terms of "run workspace root" or similar runtime jargon when "current checkout" is enough

Bad:

```md
The authoritative workspace for this step is the workflow run workspace root.
Do not delete workflow-owned runtime files under `.orchestrate/` or `state/`.
Any output-contract files must be written in the run workspace paths that already exist for this run.
```

Better:

```md
Use the current checkout.
Do not use `git worktree` or another checkout.
Leave unrelated files alone.
Write the report to the exact path named by `state/execution_report_path.txt`.
```

For `expected_outputs`, prefer concise guidance annotations directly on each artifact:

```yaml
expected_outputs:
  - name: review_decision
    path: state/review_decision.txt
    type: enum
    allowed: [APPROVE, REVISE]
    description: Final implementation gate decision.
    format_hint: Uppercase token, no extra text.
    example: APPROVE
```

For `consumes`, use concise annotations when the consumed value format is easy to misread:

```yaml
consumes:
  - artifact: execution_log
    producers: [ExecutePlan]
    description: Primary execution session log path.
    format_hint: Workspace-relative path under artifacts/work.
    example: artifacts/work/latest-execution-session-log.md
```

## 6) Recommended Loop Pattern

For execute/review/fix loops, separate "doing" from "deciding":

`Execute` -> `Checks` -> `Assess` -> `Review` -> `Gate` -> (`Fix` -> back to `Checks`)

Add at least one hard closure assertion step if "looks done" is not good enough.

For raw-graph review/fix loops, add an explicit cycle cap:
- use `max_visits` when one particular gate or work step should own the retry budget
- use `max_transitions` when you want one workflow-wide ceiling across several back-edges
- keep the first tranche top-level only; do not try to guard nested `for_each` steps until the later stable-ID work lands

For v2.2 structured branching:
- keep branch-local work inside `then` / `else`; do not route downstream logic to branch-local step names
- expose any downstream values through matching branch `outputs`, then read them from the statement node
- keep the first tranche simple: top-level statements only, and do not embed raw `goto` / `_end` inside branch steps

For post-v2.0 workflows, separate display names from durable identity:
- keep `name` optimized for readable reports
- use `id` when the step participates in lineage, scoped refs, or any flow you expect to survive sibling insertion / block reshaping
- do not rely on compiler-generated ids for cross-edit stability; they are only safe within the same validated workflow checksum

### Preparing A Workflow For Future `call`

If you expect a workflow to become a reusable library workflow once `call` lands:

- Surface every DSL-managed write root that needs to vary per invocation as a typed workflow `input` with `type: relpath`.
- Bind those write-root inputs uniquely at each call site when repeated or concurrent calls could otherwise share the same managed `state/*`, `artifacts/*`, or other deterministic output roots.
- Keep bundled source assets on the workflow-source-relative asset surface (`asset_file`, `asset_depends_on`) instead of teaching callers to copy prompt files into the workspace.
- Keep cross-boundary data narrow: caller -> callee through typed `inputs`; callee -> caller only through declared `outputs`.
- Assume imported `command` / `provider` steps still have accepted operational risk for undeclared filesystem effects. First-tranche `call` is reuse, not sandboxing.
- Treat imported `providers`, `artifacts`, and `context` defaults as callee-private by default; do not design workflows that depend on implicit caller/callee namespace merging.

### Plan-Time Strategy vs Runtime Check Plan

Do not force the planning loop to publish the final runnable verification commands if execution is expected to create or modify tests.

Use this split instead:

| Artifact | Phase | Purpose |
| --- | --- | --- |
| `check_strategy` | Plan loop | Explain intended visible verification, current gaps, and what runnable checks should exist after execution. |
| `check_plan` | Implementation loop | Contain only runnable commands that `RunChecks` can execute now. |

Why this matters:
- it avoids plan steps fabricating commands for tests that do not exist yet
- it lets execution/fix steps strengthen verification without violating artifact contracts
- it keeps `RunChecks` deterministic while still allowing verification to evolve during the implementation loop

For this pattern, `RunChecks` should usually consume `check_plan` from execution/fix producers, not from plan-drafting producers. Malformed or stale check definitions should normally become structured `check_results` evidence for review/fix, rather than terminating the workflow immediately.

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
