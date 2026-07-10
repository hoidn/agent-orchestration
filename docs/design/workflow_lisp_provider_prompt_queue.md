# Workflow Lisp Provider Prompt Queue

- **Status:** proposed
- **Kind:** feature / frontend and runtime architecture decision
- **Owner:** Workflow Lisp frontend
- **Reviewers:** pending independent design review; direction and the four
  surface decisions (atomic step, static length, per-turn exit success,
  provider-form parameter) selected by the user on 2026-07-10
- **Created:** 2026-07-10
- **Last material update:** 2026-07-10
- **Related docs / plans:**
  - `docs/design/workflow_lisp_frontend_specification.md` (parent language contract)
  - `docs/design/workflow_language_design_principles.md`
  - `docs/design/workflow_lisp_native_transportable_returns.md` (accepted
    v2.15 return-contract owner; the queue's final turn renders whatever
    contract that design specifies)
  - `docs/design/workflow_lisp_runtime_migration_foundation.md` (structured-output
    authority, prompt extern semantics)
  - `docs/plans/2026-04-20-adjudicated-provider-step-design.md` (precedent:
    multi-invocation single step)
  - `specs/providers.md`, `specs/io.md`, `specs/versioning.md`
- **Implementation target:** not scheduled; requires an explicit Stage-5
  amendment to `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
  (see Dependencies And Sequencing)

## Summary

Authors need to walk a provider through several conversational turns —
context-building, staged instructions, then a final ask — inside one logical
operation, with only the final turn carrying the output contract and producing
the validated result bundle. Today the `.orc` frontend offers no way to do
this: each provider form is one prompt, one invocation, one contract, and the
YAML `provider_session` chaining mechanics (v2.10) are not reachable from
Workflow Lisp at all.

This design adds a **`prompt-queue`** parameter to the provider invocation
forms: a static, ordered list of prompt sources executed as **one runtime
step** whose internal turn loop drives N sequential provider invocations
against one persisted provider session. Turn 1 opens a fresh session and
carries the step's prompt injections; turns 2..N-1 are raw conversational
turns validated only by process exit; the final turn carries the output
contract and produces the step's single validated result bundle. The form's
type, effects, checkpoint identity, and result contract are unchanged — the
queue changes only how the invocation transport executes.

## Context And Authority

Verified implementation behavior this design builds on (2026-07-10 checkout):

- **Session transport exists and is fail-closed.** Provider templates may
  declare `session_support` with `fresh_command` / `resume_command` and
  `${SESSION_ID}` substitution (`orchestrator/providers/types.py:42-58`). The
  builtin `codex` / `codex_gpt55` templates declare it
  (`orchestrator/providers/registry.py:51-75`): fresh = `codex exec --json`,
  resume = `codex exec resume ${SESSION_ID} --json`, metadata mode
  `codex_exec_jsonl_stdout`. The session executor parses the session id from
  JSONL stdout and fails closed when the transport exposes no session id,
  more than one distinct session id, or a resume id mismatch
  (`orchestrator/providers/executor.py:886-904`). The builtin `claude` and
  `gemini` templates do **not** declare `session_support`.
- **Sessions are persisted state, not live processes.** Every turn is a
  separate process invocation that reattaches to provider-side conversation
  state by session id. There is no long-lived process held across turns, so
  "one step vs N steps" does not change what the provider actually executes.
- **Cross-step session chaining already exists in YAML v2.10.**
  `provider_session: {mode: resume, session_id_from: <artifact>}` with
  loader-time validation (`orchestrator/loader.py:4004-4043`) and a runnable
  example (`workflows/examples/dsl_review_first_fix_loop_provider_session.yaml`).
  This design deliberately does not extend that YAML surface (see Non-Goals).
- **Per-invocation contract suppression exists.**
  `PromptComposer.apply_output_contract_prompt_suffix` skips the contract
  block when `inject_output_contract` is false
  (`orchestrator/workflow/prompting.py:111-113`).
- **Multi-invocation single steps are an established runtime pattern.**
  `adjudicated_provider` (v2.11) runs candidate and evaluator invocations
  inside one logical step; `managed_jobs` (v2.13) wraps the selected
  invocation with a runtime-owned guard. The prompt-queue turn loop is a third
  member of this family.
- **`.orc` provider surfaces.** `provider-result`
  (`orchestrator/workflow_lisp/expressions.py:352`, fields `provider`,
  `prompt`, `inputs`, `returns_type_name`) and `run-provider-phase`
  (`RunProviderPhaseExpr`, `expressions.py:435`). Both carry a single `prompt`
  expression today.
- **Structured-result channel invariant.** Results travel only as validated
  bundles at runtime-bound output locations; stdout/stderr are observability
  evidence, never a result channel (`docs/index.md` clarifications;
  `specs/io.md`). Intermediate-turn output therefore cannot be a result.

Ambiguity resolved by this design: whether multi-turn provider interaction is
a workflow-graph concern (N steps) or an invocation-transport concern (one
step). This design fixes it as invocation transport.

## Problem

- A single composed prompt is the only way to deliver staged instructions to
  a provider from `.orc` today. Authors either cram context, instructions,
  and the ask into one oversized prompt, or split work across separate
  provider steps that each open a *new* session and re-establish context from
  scratch (paying repeated context assembly and losing conversational state).
- The YAML `provider_session` chaining escape hatch is unavailable to `.orc`,
  and extending YAML authoring contradicts the YAML-retirement direction.
- Chaining separate steps also forces every step to carry a typed output
  contract, even when intermediate turns exist only to build conversation
  state — producing contract noise the provider must answer and the runtime
  must validate for no semantic gain.

This needs a design-level decision because it fixes where multi-turn
interaction lives in the architecture (transport vs step graph), touches the
provider-session contract surface, and constrains checkpoint/resume
semantics.

## Goals And Non-Goals

Goals:

1. A `.orc` author can express an ordered, statically known sequence of
   prompts executed against one provider session as one provider form.
2. Only the final turn carries the output contract; only the final turn's
   bundle is the step result; the form's declared return type is unchanged.
3. Intermediate turns are observable (persisted transcripts) but produce no
   typed output and no artifacts other than observability evidence.
4. Failure anywhere in the queue fails the step with a turn-indexed
   diagnostic; retry replays the whole queue on a fresh session.
5. Queue arity 1 is exactly equivalent to today's single-prompt invocation.
6. The mechanics are structural: no branching on workflow, provider, family,
   or domain names.

Non-Goals (intentionally excluded):

- **Runtime-dynamic queue length.** The prompt list is static at compile
  time. A runtime-computed list collides with the known dynamic-step-count
  gap and is out of scope.
- **Mid-queue checkpointing or mid-queue resume.** v1 has one checkpoint —
  the step's. Resuming an interrupted run re-executes an incomplete queue
  step from turn 1 with a fresh session. Session-id-based mid-queue resume
  is deferred: it would make correctness depend on provider-side session
  persistence, which lives outside the run workspace and is not
  content-addressed.
- **Persistent-process transports.** All current session providers are
  exec-per-turn CLIs. Streaming/interactive transports would need per-turn
  protocol markers instead of exit codes and are not designed here.
- **New YAML authoring surface.** No `prompt_queue:` YAML field. The
  executable-IR and runtime mechanics are frontend-neutral, but authoring
  exposure is `.orc`-only, consistent with YAML retirement.
- **Session sharing across forms.** A queue's session is private to its step.
  Exposing session ids as first-class `.orc` values is out of scope.
- **Intermediate-turn acknowledgment protocols.** No required marker or
  validation of intermediate assistant output beyond process exit. A derail
  check can be layered later without changing this contract.

## Decision

Add a `prompt-queue` grouping form accepted by the `prompt` slot of the
provider invocation forms, lowering to **one provider step** whose runtime
executes an internal turn loop over one provider session.

- **Chosen approach:** atomic single step, static queue, parameter on the
  existing provider forms, per-turn process-exit success for intermediate
  turns, contract injection and bundle production on the final turn only,
  whole-queue fresh-session replay on retry.
- **Alternatives rejected:**
  - *N chained runtime steps* (session id flowing as an artifact between
    steps, as YAML v2.10 does). Rejected: intermediate turns have no typed
    product, so this manufactures steps whose only effect is invisible
    mutation of provider-side conversation state — against the explicit-
    dataflow and typed-transition principles — and bloats checkpoint
    identity for nothing the run can use.
  - *Standalone `(queue ...)` expression form.* Rejected: duplicates
    provider configuration, contract declaration, and typing rules onto a
    second form for no semantic gain.
  - *Macro-derived expansion to N explicit steps.* Rejected for the same
    reason as N chained steps, plus it would require exposing raw session
    plumbing as an authored `.orc` surface.
- **Tradeoffs accepted:** a long queue replays fully on failure (no partial
  credit); a single step summary covers N turns (mitigated by per-turn
  transcript artifacts); step wall-time is the sum of N provider execs under
  one step timeout budget.
- **Left open:** see Open Questions (per-turn timeout policy, `claude`
  builtin session template, which provider forms get the surface in the
  first tranche, per-turn step-summary emission).

Naming note: the form is spelled `prompt-queue`, not `queue` — "queue" is an
established filesystem-queue term in this repo (`specs/queue.md`) and must
not be overloaded.

## Design Details

### Authoring surface

The `prompt` slot of `provider-result` (and, pending the open question,
`run-provider-phase`) accepts either a single prompt source (unchanged) or a
`prompt-queue` grouping:

```lisp
(provider-result providers.migration.executor
  :prompt (prompt-queue
            prompts.migration.context      ;; turn 1: context assembly
            prompts.migration.instructions ;; turn 2: staged instructions
            prompts.migration.final-ask)   ;; turn N: contract-bearing ask
  :inputs (...)
  :returns MigrationOutcome)
```

Rules:

- Each item is an ordinary prompt source drawn from the same domain the
  `prompt` slot accepts today (prompt externs, literals). Items are
  positional; arity is fixed at compile time; arity ≥ 1.
- `(prompt-queue p)` compiles to exactly what `:prompt p` compiles to today
  (identity — verified by a lowering-equivalence test).
- The form's `:returns` type, effect classification, and step identity
  derivation are computed exactly as for a single-prompt form. The queue is
  invisible to the type system beyond arity/static-ness validation.

### Compile-time validation (fail-closed)

- Queue arity must be a compile-time constant ≥ 1; a runtime-valued list is a
  type error with a dedicated diagnostic code.
- When arity > 1, the resolved provider template must declare
  `session_support` with a `resume_command`. This is validated at
  compile/load time (mirroring the loader-time validation precedent at
  `orchestrator/loader.py:4004`), not discovered at runtime. With the builtin
  registry this admits `codex`/`codex_gpt55` and rejects `claude`/`gemini`
  until their templates gain session support.

### Executable IR

The provider step schema gains one optional field: an ordered list of prompt
sources (absent ⇒ single-prompt behavior, byte-identical IR for existing
workflows). Source maps carry one entry per queue item so diagnostics can
point at the failing turn's authored source.

### Runtime turn loop

For a queue of prompts `p_1 .. p_N`, the step runner executes:

1. **Turn 1** — `ProviderExecutor.prepare_invocation` with a FRESH-mode
   session request; the composed prompt is `p_1` plus **all step-level prompt
   injections** (typed prompt inputs, consumes injection, asset injection) —
   context is established at conversation start. No output contract block.
   The session id is captured via the template's metadata mode under the
   existing fail-closed rules.
2. **Turns 2..N-1** — RESUME-mode invocations against the captured session
   id. Composed prompt is the item's text only: no injections, no contract
   block (`inject_output_contract` false). Success = process exit 0.
3. **Turn N** — RESUME-mode invocation. Composed prompt is the item's text
   plus the output contract suffix rendered by the form's existing contract
   renderer (today's bundle/variant contract; the accepted native-returns
   contract once that lands — the queue is transport-orthogonal to it). The
   runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding is present on this
   invocation **only**, so earlier turns cannot legitimately write the
   bundle. Step success/output authority follows the existing final-turn
   rules unchanged (a valid bundle at the bound path is the result; stdout is
   evidence).

Turn-loop mechanics reuse `prepare_invocation`/`execute` per turn without
modification; the loop lives beside the adjudication runner as a sibling
step-execution mode, not inside `ProviderExecutor`.

### Failure, retry, and resume semantics

- Any intermediate turn exiting nonzero, or any session-transport error
  (missing id, plural ids, resume mismatch), fails the step immediately with
  a diagnostic carrying the turn index and the queue item's source span.
- The final turn is judged by the existing output-authority rules for the
  form (including bundle-overrides-exit behavior where it applies today).
- **Retry and resume both replay the entire queue with a fresh session.** No
  turn cursor is persisted. An interrupted queue step is simply an
  incomplete step; existing step-level resume semantics apply without
  modification.
- Turns after the first must observe the same session id captured at turn 1;
  any deviation is a step failure (inherited executor rule).

### Observability

- Each turn's normalized assistant output and invocation metadata are
  persisted as step-scoped observability artifacts (transcripts), named by
  turn index. They are evidence, never a result channel and never consumed
  by later steps.
- Prompt-audit artifacts record, per turn, whether injections and the
  contract block were applied — giving tests and reviewers a structural
  (non-phrasing) way to assert the turn-composition rules.

## Contracts And Interfaces

- **New:** `prompt-queue` grouping accepted by provider-form prompt slots;
  compile diagnostics for non-static arity and missing provider session
  support; executable-IR optional ordered prompt-source list; per-turn
  transcript artifact naming; turn-indexed failure diagnostics.
- **Changed:** none for existing workflows. A single-prompt provider form
  compiles to byte-identical IR and executes byte-identical invocations.
- **Spec deltas required at implementation time:** `specs/providers.md`
  (turn-loop composition order, session reuse, contract-suffix placement,
  bundle-path binding scope), `specs/io.md` (transcript artifacts are
  evidence-only), `specs/versioning.md` (feature gate note). The frontend
  specification gains the `prompt-queue` surface contract.

## Dependencies And Sequencing

- **Feasibility: proven for the codex family.** Session transport, resume
  commands, fail-closed id capture, and per-invocation contract suppression
  all exist and are exercised in production surfaces (evidence in Context And
  Authority). No new provider-side capability is required for codex-backed
  queues.
- **Open prerequisite (recorded, not blocking design):** `claude`/`gemini`
  builtin templates lack `session_support`; queues over those providers are
  compile-time rejected until their templates gain session commands and a
  metadata mode. Adding one is independent work.
- **Sequencing:** implementation is gated behind the semantic-migration
  freeze (drain Gate S3/P4) and belongs after the native-transportable-
  returns wave, since the final turn renders whatever return contract that
  design owns. Scheduling requires an explicit amendment to the procedure-
  first roadmap's Stage-5 wave list; this document does not by itself make
  the feature selectable.
- Work that can proceed independently: independent design review of this
  document; the `claude` session-template prerequisite; a scripted
  session-capable fixture provider for tests.

## Invariants And Failure Modes

Invariants that must hold after implementation:

1. Queue membership never affects typing, effect classification, routing,
   resume/checkpoint identity, or the declared return contract — only the
   invocation transport.
2. No name-keyed branches: the turn loop must not consult workflow, provider,
   family, or domain names.
3. Results travel only as the final turn's validated bundle at the
   runtime-bound path; intermediate stdout/transcripts are never promoted to
   results.
4. The single-source-of-truth for per-turn contract suppression is the
   composed invocation (`inject_output_contract`), not prompt-text
   inspection.
5. Session state is external, non-authoritative state: nothing in the run
   may treat provider-side conversation persistence as durable workflow
   state (hence fresh-session replay).
6. Arity-1 equivalence: `(prompt-queue p)` ≡ `:prompt p` at IR and
   invocation level.

Failure behavior:

- Non-static queue / arity 0 → compile diagnostic.
- Provider without session support, arity > 1 → compile/load diagnostic.
- Turn k nonzero exit (k < N) → step failure, diagnostic names turn k and its
  source span; no bundle is read.
- Session id missing / plural / mismatched at any turn → step failure
  (existing executor taxonomy, extended with turn index).
- Final-turn contract violation → existing contract-violation behavior,
  unchanged.
- Crash mid-queue → incomplete step; resume replays from turn 1, fresh
  session.

## Security, Operations, And Performance

- No new authority or credentials; secrets masking and path-safety rules
  apply per turn exactly as for single invocations.
- Step wall-time is the sum of N provider invocations; the step timeout
  budget therefore bounds the whole queue (per-turn budget is an open
  question). Runs with long queues should size timeouts accordingly.
- Provider-side session persistence is an external dependency with unknown
  retention; the fresh-replay policy means retention only affects in-flight
  steps, never completed ones.

## Evidence And Implementation Boundaries

- The default path is the turn loop inside the provider step runner driving
  `ProviderExecutor.prepare_invocation`/`execute` per turn. The adjudication
  runner and `managed_jobs` guard are adjacent multi-invocation mechanisms
  that must not be conflated with or reused as the queue implementation.
- A scripted session-capable fixture provider (emitting deterministic JSONL
  with a stable session id) is test infrastructure, not the implementation;
  end-to-end evidence must include at least one real session-capable
  provider smoke.
- Prompt-audit metadata is the sanctioned evidence surface for asserting
  turn-composition rules; tests must not assert literal prompt phrasing.

## Compatibility And Migration

- No existing workflow changes behavior; the surface is additive and
  `.orc`-only. Arity-1 equivalence is the compatibility contract and gets a
  dedicated test.
- No YAML surface is added or deprecated by this design.

## Verification Strategy

- **Typecheck:** arity-0 and runtime-list rejections; provider-without-
  session-support rejection; queue form typechecks to the declared return
  type; arity-1 acceptance.
- **Lowering:** golden IR for a 3-item queue (ordered prompt sources, one
  step, source-map entry per item); arity-1 IR equivalence against a plain
  prompt form.
- **Runtime (fixture provider):** turn ordering and session-id threading;
  injections on turn 1 only; contract suffix and bundle-path binding on the
  final turn only (asserted via prompt-audit metadata / invocation bindings,
  not prompt text); transcripts persisted per turn; mid-queue nonzero exit
  fails the step with the turn index; session-id mismatch fails closed;
  retry replays from turn 1 with a new session id.
- **End-to-end:** one orchestrator smoke compiling and running a small
  queue-bearing `.orc` workflow against a real session-capable provider,
  producing a validated final bundle (repo rule for DSL/frontend/runtime
  changes).
- **Negative:** a workflow attempting to consume an intermediate transcript
  as a typed artifact fails validation; a queue over a session-less provider
  fails at compile/load, not at runtime.

## Declarative Acceptance Scenario

A `.orc` workflow declares a `provider-result` over `codex` with
`(prompt-queue ctx instructions ask)` returning `ReportOutcome`. Running it:

- executes exactly three provider processes: one fresh (`codex exec --json`),
  two resumes against the turn-1 session id;
- composes typed-input/consumes/asset injections into turn 1 only; appends
  the output contract block to turn 3 only; binds
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` on turn 3 only;
- persists three turn transcripts as evidence artifacts;
- validates the turn-3 bundle as the step's sole result, typed
  `ReportOutcome`;
- on a simulated turn-2 nonzero exit: fails the step naming turn 2 and its
  source span, reads no bundle, and on retry issues a fresh session id and
  re-executes all three turns.

This proves the intended integration path because the assertions are made on
invocation records, session metadata, prompt-audit flags, and bundle
validation — not on fixture-only shortcuts or prompt phrasing.

## Success Criteria

- All Verification Strategy checks implemented and green, including the
  end-to-end smoke on a real session-capable provider.
- Arity-1 equivalence proven at IR and invocation level.
- Spec deltas (`specs/providers.md`, `specs/io.md`, `specs/versioning.md`)
  and frontend-specification delta landed with the implementation.
- Capability matrix row and doc-index routing added.
- Independent design review signoff before implementation starts.

## Stop / Revise Criteria

- The turn loop cannot be implemented without consulting provider or
  workflow names → stop; the abstraction is wrong.
- Intermediate turns turn out to need typed validation in practice (derailed
  sessions produce garbage final bundles at a material rate) → revise toward
  the deferred acknowledgment protocol rather than ad-hoc checks.
- Session-id capture proves unreliable for a needed provider → revise the
  provider-template prerequisite rather than weakening fail-closed rules.
- The step-timeout-covers-whole-queue policy proves operationally unusable →
  resolve the per-turn budget open question before proceeding.

## Documentation Impact

At implementation time: `specs/providers.md`, `specs/io.md`,
`specs/versioning.md`, `docs/design/workflow_lisp_frontend_specification.md`,
`docs/capability_status_matrix.md`, `docs/index.md` + `docs/design/README.md`
routing entries, and the Workflow Lisp drafting guide (authoring guidance and
the arity-1 equivalence note). None are edited by this proposal.

## Implementation Handoff

Suggested phases (each independently testable):

1. **Runtime turn loop behind the IR field** — executable-IR schema addition,
   step-runner turn loop, fixture provider, runtime tests. No frontend
   changes; the field is only producible by hand-built IR in tests.
2. **Frontend surface** — `prompt-queue` parsing on `provider-result`,
   typecheck validations, lowering to the IR field, source-map entries,
   arity-1 equivalence tests.
3. **End-to-end + specs/docs** — orchestrator smoke, spec deltas, capability
   matrix, drafting-guide guidance.

Likely-touched modules: `orchestrator/workflow_lisp/expressions.py`,
form parsing (`expressions.py:2395` region), the effects/calls typecheck
family, lowering core, `orchestrator/workflow/executable_ir.py`,
`orchestrator/workflow/prompting.py`, a new turn-loop runner module beside
the adjudication runner, `orchestrator/providers/` (read-only reuse).

Known tricky areas: the turn-1-vs-turn-N split of prompt composition (today
composition assumes one composed prompt per step); resume reconciliation for
a step that crashed mid-queue (must present as an ordinary incomplete step);
transcript artifact naming under the state-layout path allocator.

Safe first step: phase 1's runtime loop with the fixture provider — zero
frontend exposure, fully removable.

Out of scope for the implementation: YAML surface, dynamic arity, mid-queue
resume, session-id values in `.orc`, `claude` template session support.

## Open Questions

1. **Per-turn timeout budget** — does the existing step timeout apply to the
   whole queue (simplest) or per turn (predictable under long queues)?
   Recommendation: whole-step in v1; revisit on evidence. Blocking: no.
2. **`run-provider-phase` in tranche 1** — both forms route through shared
   lowering, but `provider-result` alone may be a smaller first tranche.
   Recommendation: `provider-result` first, `run-provider-phase` in the same
   design once the base lands. Blocking: no.
3. **Per-turn step-summary emission** — should the observability summary
   pipeline emit one summary per turn or one per step referencing the
   transcripts? Owner: dashboard/observability design. Blocking: no.
4. **`claude` builtin session template** — independent prerequisite for
   queues over Claude-family providers (needs resume command + a metadata
   mode for session-id capture). Owner: provider registry. Blocking: no for
   codex-backed use.
