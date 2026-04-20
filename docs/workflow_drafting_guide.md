# Workflow Drafting Guide

This guide is informative. The normative contracts live under `specs/` (start at `specs/index.md`).
This guide is about DSL authoring choices, not runtime operations.

Companion docs:
- Concept model and terminology: `docs/orchestration_start_here.md`
- Runtime sequencing and step lifecycle: `docs/runtime_execution_lifecycle.md`

Goal: help you author workflows that are reliable when prompts, deterministic artifacts, and control flow all interact.

## 1) Mental Model: Four Authoring Surfaces

Keep these authoring surfaces separate. Confusing them is the fastest way to write a workflow that looks coherent in YAML but teaches the wrong boundary model.

| Surface | What it is | Where it lives |
| --- | --- | --- |
| Workflow boundary | Typed values crossing the workflow interface. | Top-level `inputs`, `outputs`. |
| Runtime dependencies | Files or published artifacts that must resolve before a step runs. | `depends_on`, `consumes`. |
| Provider prompt sources | The authored material used to compose provider prompt text. | `input_file`, `asset_file`, `asset_depends_on`. |
| Artifact storage / lineage | Deterministic validation and publication surfaces. | Top-level `artifacts`, step `expected_outputs`, `output_bundle`, `publishes`. |

Inside one provider step, you still have separate prompt, runtime, and flow contracts:

| Contract | What it is | Where it lives |
| --- | --- | --- |
| Prompt contract | The instructions the provider receives. | Prompt sources plus injected dependency/dataflow blocks. |
| Runtime contract | What the orchestrator validates after execution. | `expected_outputs` or `output_bundle`. |
| Flow contract | What determines routing, looping, and termination. | `on.*.goto`, gates, and cycle caps. |

The key rule: satisfying the runtime contract does not imply the prompt contract was followed, and neither implies the flow contract routes the way you intended.

## 2) Provider Prompt Composition (What The Agent Actually Sees)

Provider prompt text is composed deterministically:

| Order | Step | Notes / knobs |
| --- | --- | --- |
| 1 | Read the base prompt source (`input_file` or `asset_file`) literally. | No variable substitution inside file contents. |
| 2 | Prepend `asset_depends_on` blocks (v2.5+) if enabled. | Workflow-source-relative assets are injected in declared order before the base prompt. |
| 3 | Apply `depends_on.inject` (v1.1.1+) if enabled. | Injects resolved workspace dependencies in-memory around the already-expanded prompt. |
| 4 | Inject `## Consumed Artifacts` (v1.2+) if the step has `consumes`. | `inject_consumes`, `consumes_injection_position`, `prompt_consumes`. Uses resolved consume values from preflight. |
| 5 | Append `## Output Contract` if the step has `expected_outputs` or `output_bundle`. | `inject_output_contract` controls suffix injection. `expected_outputs.path` and `output_bundle.path` entries are rendered after runtime path substitution. This is validation, not execution. |

Practical implications: if you need dynamic prompt content, generate a file in a prior step and reference it; `consumes`/`publishes` handle lineage and preflight checks, not scope; and the `Output Contract` does not write files for the agent.

### Dependency Injection Scope

Use `depends_on.inject` for runtime-resolved file lists or content, not for substantive task instructions that belong in the prompt. Keep injected instructions as neutral labels unless the wording is only explaining how to interpret the injected block.

For provider-review steps, treat injected docs as candidates rather than a mandatory reading list unless the step truly requires every file. Avoid broad doc globs such as `docs/**/*.md` or `specs/*.md`; prefer `docs/index.md` plus a small exact set of docs that are nearly always relevant. Do not list ambient agent instruction files such as `AGENTS.md` or `CLAUDE.md` as workflow dependencies just to make agents read them; the agent runtime handles those.

If semantic enforcement matters, put the standard in the review or design prompt and back it with an output contract or gate instead of duplicating the same instruction in YAML and prompt prose.

Codex provider note: when a Codex workflow is expected to use shell tools to read or write the checkout, include `--dangerously-bypass-approvals-and-sandbox` in the provider command; `--skip-git-repo-check` is often paired with it for workflows that may run from copied or generated checkouts. The bypass flag matches the built-in `codex` provider and avoids Codex starting in its default Linux sandbox, which can fail in nested or externally sandboxed environments. Only use this for trusted workflow workspaces because it disables Codex's own approval and sandbox layer.

For v2.10 provider-session steps, treat the session handle as runtime-owned dataflow, not prompt content:
- use `provider_session.mode: fresh` to publish a typed scalar `string` handle into normal lineage
- use `provider_session.mode: resume` plus the reserved `session_id_from` consume to bind `${SESSION_ID}` at runtime
- do not ask prompts to echo, store, or restate the session id; that handle is intentionally excluded from prompt injection and `consume_bundle`

Pointer ownership note (v1.4): consume preflight for relpath artifacts is read-only and does not rewrite registry pointer files. If a command step needs deterministic consumed values, prefer `consume_bundle` JSON and read values from that bundle instead of relying on consume-time pointer mutation.

`expected_outputs` also supports optional guidance fields (`description`, `format_hint`, `example`) that are injected into the `Output Contract` block. Use them to reduce ambiguity for agent-written artifacts. They are prompt guidance only and do not change runtime validation rules.

`consumes` supports the same optional guidance fields (`description`, `format_hint`, `example`). When present, they are injected under each consumed artifact line in `## Consumed Artifacts` (subject to `prompt_consumes` filtering). They are prompt guidance only and do not change runtime consume preflight behavior.

## 3) Deterministic Handoff Patterns

### A) `expected_outputs` (v1.1+, file-per-artifact)

Use when each deterministic value naturally maps to one file path (pointers, enums, counts, relpaths).

Why it works: the orchestrator can validate presence, type, and path safety (`under`, `must_exist_target`) without parsing prose.

When a provider must write a document or report whose location is carried by a `relpath` artifact file, make the prompt say to read the recorded path from that artifact file and write the content to that current-checkout-relative target, leaving the artifact file path-only. Do not ask the provider to write rich content "to the artifact path" when that artifact path is really a pointer file.

Do not point a `relpath` expected output at a rich JSON, markdown, or log file unless that file's entire contents are the relative path value. For ledgers and reports, either publish a separate path-only pointer file or use `output_bundle` to extract typed fields from the JSON body.

### B) `output_bundle` (v1.3+, single JSON file)

Use when a step emits many scalar artifacts.

For provider steps, the prompt suffix includes the concrete JSON bundle path and field-level JSON pointer contract after runtime path substitution. Do not duplicate that path in the prompt unless the step is unusually high-risk.

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
- v1.6: use typed predicates plus structured `ref:` for booleans, generic typed comparisons, and recovered-failure routing instead of stringly `when.equals` hacks.
- v1.8: use `max_visits` and `max_transitions` instead of shell counters or ad hoc file-backed loop budgets when the goal is simply to cap a raw `goto` loop.
- v2.0: when authoring new typed predicates in nested scopes, use explicit `self.steps.*`, `parent.steps.*`, and `root.steps.*` refs and add stable step `id` values anywhere later refactors should preserve lineage or resume identity.
- v2.1: prefer typed workflow `inputs`/`outputs` over ad hoc `context` conventions when the value is part of the workflow boundary and should survive validation, resume, and later `call` reuse.
- v2.2: prefer top-level structured `if/else` when the workflow intent is branch selection rather than a reusable raw `goto` diamond.
- v2.6: prefer top-level structured `match` when a typed enum decision has three or more stable cases, or when you want the workflow shape to stay aligned with the decision artifact values instead of layering chained predicates.
- v2.7: prefer top-level `repeat_until` for bounded post-test review/fix loops when the exit condition should read the latest iteration outputs instead of shell-managed counters or raw `goto` back-edges.
- v2.8: prefer the `score` predicate helper for evaluator thresholds and score bands instead of repeating numeric `compare` / `all_of` chains around one score artifact.
- v2.9 tooling: use `orchestrate run ... --dry-run` or `orchestrate report` to surface advisory migration warnings for shell gates, stringly `when.equals`, raw `goto` diamonds, and imported/exported output-name collisions before those patterns spread.
- v2.11: use `adjudicated_provider` when a high-value artifact-producing provider step should compare multiple providers or prompt variants before downstream publication.
- Reusable-call boundary: if a workflow is intended for `call` reuse, keep bundled prompts/rubrics/schemas on the workflow-source-relative asset surface (`asset_file`, `asset_depends_on`) and keep workspace-owned or runtime-generated prompt material on `input_file`.

## 5) Prompt Authoring Guidance

Keep prompts focused on decision-quality instructions, not DSL plumbing.

| Do include | Usually avoid |
| --- | --- |
| Objective + scope boundaries. | Repeating file lists already injected via `depends_on.inject` or `consumes`. |
| Completion criteria (done vs blocked). | Repeating output contracts already injected via `expected_outputs` or `output_bundle`. |
| Forbidden shortcuts (when failure modes are predictable). | "Audit-only" language that can be mistaken for execution. |
| Evidence format (what files to write and where). | Over-specifying pointer plumbing already enforced by contracts. |

Exception: keep redundancy when the step is high-risk and you want belt-and-suspenders.

For design, design-review, and planning prompts that may affect architecture, data contracts, workflow APIs, or stable modules, explicitly instruct the agent to read `docs/index.md` first when present, then use it to select the relevant specs, architecture docs, workflow guides, and findings docs. This instruction belongs in the prompt because it is part of the review or design judgment standard. Keep the workflow `depends_on.inject` list narrow and treat it as candidate context, not a mandatory reading list.

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

### Rollback/Checkpoint Workflows Are A Special Case

Not every workflow needs checkout-level operator rules. Add them only when the workflow has DSL-level git rollback/checkpoint behavior, for example when authored runtime semantics depend on recording a base ref, creating candidate commits, and later resetting or restoring against that recorded ref.

For those workflows:
- record explicit refs such as `base_ref`, `accepted_ref`, or `candidate_commit` in workflow-owned state instead of inferring intent from ancestry shortcuts like `HEAD^`
- route keep/discard/recovery against those explicit refs, not against whatever happens to be at the branch tip later
- document repo-local live-run coexistence rules in the downstream runbook or study doc: what human edits are safe during a run, what must wait, and whether the workflow should run only in a dedicated checkout
- keep the prompt focused on the local task; operator rules about branch movement, resume/recovery, or safe concurrent edits belong in docs and workflow/runtime behavior, not prompt prose

If a workflow can be derailed by an unrelated commit landing in the same checkout, treat that as a workflow/runbook design issue to document or fix explicitly, not as a universal rule for all workflows.

### Adjudicated Provider Steps

Use `adjudicated_provider` for artifact-producing work where comparing multiple candidates is worth the extra runtime and audit state. Good fits include design drafts, report generation, structured analyses, and other deterministic-output steps where downstream workflow state should see only the selected artifact.

Start from `workflows/examples/adjudicated_provider_demo.yaml` when authoring one for the first time; it is the canonical runnable example for the v2.11 surface.

Do not use it as a generic implementation or source-edit competition mechanism in V1. The first release promotes declared deterministic outputs only; arbitrary patch selection belongs in a separate workflow design.

Keep the evaluator prompt reusable and small. Put task-specific rubric text in a concise evaluator rubric source when needed, and keep score-critical evidence bounded so packets are reviewable.

Treat the same-trust-boundary attestation as a real data disclosure decision. Baseline snapshots, candidate workspaces, composed prompts, evaluator packets, score ledgers, logs, and promotion staging can contain sensitive workspace material.

Adjudicated steps do not expose candidate or evaluator stdout through `steps.<Step>.output`, `.lines`, or `.json`. Publish deterministic artifacts and have downstream steps consume the promoted selected artifacts normally.

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

When a review step publishes a report and the immediately selected revise/fix step consumes that same report, prefer `freshness: any` for the report consume. The route decision already proves the report is the current iteration's review output, and a killed or retried provider step can otherwise mark the report version as consumed before the revise/fix step finishes. Use `freshness: since_last_consume` only when the same consumer must require a genuinely newer publication before each visit.

For raw-graph review/fix loops, add an explicit cycle cap:
- use `max_visits` when one particular gate or work step should own the retry budget
- use `max_transitions` when you want one workflow-wide ceiling across several back-edges
- keep the first tranche top-level only; do not try to guard nested `for_each` steps until the later stable-ID work lands

For v2.2 structured branching:
- keep branch-local work inside `then` / `else`; do not route downstream logic to branch-local step names
- expose any downstream values through matching branch `outputs`, then read them from the statement node
- keep the first tranche simple: top-level statements only, and do not embed raw `goto` / `_end` inside branch steps

For v2.6 enum branching:
- use `match` only with typed enum refs, and keep the cases exhaustive so the branch contract stays total for every allowed decision token
- keep case-local work inside the selected case; downstream steps should read only `root.steps.<MatchStatement>.artifacts.*`
- mirror the `if/else` block pattern: give the statement and any case that needs cross-edit identity stability an authored `id`, and expose any downstream data through matching case `outputs`
- prefer `match` over chained `if/else` only when the workflow is routing on a published decision token such as `APPROVE|REVISE|BLOCKED`; do not use it as a generic pattern-matching surface

For v2.7 structured loops:
- use `repeat_until` only for post-test loops: the body runs first, then the loop condition checks the latest loop-frame outputs
- declare the data the condition needs under `repeat_until.outputs`, then read it only through `self.outputs.<name>` inside `repeat_until.condition`
- do not point `repeat_until.condition` at `self.steps.<Inner>...`; body steps are multi-visit and that bypasses the loop-frame anti-ambiguity boundary
- give both the outer step and the repeat body an authored `id` when iteration lineage or resume stability matters across sibling insertion / body reshaping
- keep the first tranche bounded: no `goto`, nested `for_each`, or nested `repeat_until` inside the loop body
- direct nested `call`, `match`, and `if/else` bodies are allowed; the loader lowers them into loop-local executable steps that still read body-local refs through `self.steps.*` and outer lexical refs through `parent.steps.*`

Reference examples:
- Use [`workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`](../workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml) as the monolithic reference for typed workflow boundaries plus top-level `match` and `repeat_until`.
- Use [`workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml`](../workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml) as the modular reference for a small parent workflow that `call`s reusable review loops implemented in [`workflows/library/follow_on_plan_phase.yaml`](../workflows/library/follow_on_plan_phase.yaml) and [`workflows/library/follow_on_implementation_phase.yaml`](../workflows/library/follow_on_implementation_phase.yaml).

For post-v2.0 workflows, separate display names from durable identity:
- keep `name` optimized for readable reports
- use `id` when the step participates in lineage, scoped refs, or any flow you expect to survive sibling insertion / block reshaping
- do not rely on compiler-generated ids for cross-edit stability; they are only safe within the same validated workflow checksum

### Preparing A Workflow For `call`

Before drafting a new design -> plan -> implementation workflow, check `workflows/README.md` for an
existing call-based stack or phase workflow that already matches the shape. If one exists, copy or import
that stack and its imported subworkflows recursively instead of flattening it into a one-off monolith.
Use a monolith only when import portability or a debugging snapshot is the explicit goal.

For domain-specific work that still fits the generic design -> plan -> implementation prompts, prefer an
adapter over a new phase stack. The adapter should translate domain seeds into a backlog-compatible
working design seed plus per-item state/artifact roots, then call `workflows/library/backlog_item_design_plan_impl_stack.yaml`.
`workflows/library/revision_study_priority_design_plan_impl_stack.yaml` is the reference pattern for
revision-study seeds; it intentionally lets the generic design draft/revision passes rewrite the generated
working seed instead of treating the manifest source as the post-review source of truth.

If you expect a workflow to be used through `call`:

- Surface every DSL-managed write root that needs to vary per invocation as a typed workflow `input` with `type: relpath`.
- Bind those write-root inputs uniquely at each call site when repeated or concurrent calls could otherwise share the same managed `state/*`, `artifacts/*`, or other deterministic output roots.
- Keep bundled source assets on the workflow-source-relative asset surface (`asset_file`, `asset_depends_on`) instead of teaching callers to copy prompt files into the workspace.
- Keep `input_file` only for workspace-owned prompt material: caller-supplied files, runtime-generated prompts, or top-level flows that intentionally read prompt files from the active workspace.
- Keep cross-boundary data narrow: caller -> callee through typed `inputs`; callee -> caller only through declared `outputs`.
- Remember the caller-visible contract: exported callee outputs land on the outer call step (`steps.<CallStep>.artifacts.*`) only after the callee body and any callee `finally` work both succeed.
- Assume imported `command` / `provider` steps still have accepted operational risk for undeclared filesystem effects. First-tranche `call` is reuse, not sandboxing.
- Treat imported `providers`, `artifacts`, and `context` defaults as callee-private by default; do not design workflows that depend on implicit caller/callee namespace merging.

Concrete extraction pattern:
- Keep the parent workflow small and phase-oriented, then move each reusable review loop into a library workflow with typed `inputs`/`outputs`.
- [`workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml`](../workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml) shows the parent shape.
- [`workflows/library/follow_on_plan_phase.yaml`](../workflows/library/follow_on_plan_phase.yaml) and [`workflows/library/follow_on_implementation_phase.yaml`](../workflows/library/follow_on_implementation_phase.yaml) show the extracted callee shape.

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
| New DSL surface combinations | If a workflow combines structured loops, calls, or matches with deterministic output contracts or dynamic paths, copy an exact current working example or run a minimal runtime smoke for that exact contract shape. `--dry-run` validates schema and dependencies, not post-execution contract substitution. |
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
