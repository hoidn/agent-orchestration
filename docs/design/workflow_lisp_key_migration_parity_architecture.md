# Workflow Lisp Key Migration Parity Architecture

Status: draft
Kind: architecture decision / migration design
Created: 2026-06-01
Last material update: 2026-06-02
Scope:

- Workflow Lisp lowering requirements for key-workflow parity.
- Runtime/spec deltas required before `.orc` promotion.
- Migration evidence and promotion policy.

Authority:

- Normative DSL/runtime behavior remains in `specs/`.
- This document is authoritative as a migration architecture, not as a runtime
  spec, until the required spec deltas and promotion-report schema are accepted.
- A `.orc` workflow must not replace a YAML primary solely because this document
  describes a target behavior.

Related docs:

- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- Generated run evidence:
  `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Implementation target: staged changes to the Workflow Lisp frontend,
remaining effectful composition gaps, shared validation, and runtime
command/output handling needed before promoting key `.orc` workflow
replacements over YAML primaries.

Current checkout status (2026-07-13): the permanent target-loading,
report/Markdown/index, gate-evaluation, and CLI kernel remains active for
`cycle_guard_demo` and `design_plan_impl_stack`. The promoted Design Delta
family is no longer a live target; its Design-Delta-only evidence roles and G8
artifact dependency are deleted, while its immutable historical promotion
report remains the Stage-6 decision record.

## Summary

The first key-workflow migration pass proved that Workflow Lisp can compile and
dry-run meaningful `.orc` replacements, but it did not establish primary
workflow parity. The remaining gaps are not mostly syntax gaps. They are
contract gaps between high-level Lisp forms, generated Core DSL, runtime output
materialization, repeat/revise state, and migration evidence.

The first family-level parity integration pass for
`design_plan_impl_stack` also exposed two still-missing generic authoring
prerequisites that this document now treats as explicit migration blockers:

- a generic authored surface for constructing or specializing reusable
  union-returning wrapper results, so approved-only `resume-or-start`
  boundaries do not depend on compiler-generated-only union constructors; and
- a generic entrypoint context-bootstrap surface for internal `RunCtx` /
  `PhaseCtx` construction, so promoted wrappers can derive runtime-owned
  run/context values without exposing fake run ids or extra public context
  inputs.

The blocked family attempt confirmed that the second prerequisite is not just a
discoverability gap. A dedicated promoted-entry bootstrap fixture still fails
with `[workflow_signature_mismatch] call is missing required binding
\`phase-ctx\``, which means the current checkout cannot yet route runtime-owned
context into reusable wrapper calls from a promoted entry boundary. Synthetic
top-level `PhaseCtx` defaults that help compile or dry-run isolated fixtures are
implementation convenience only; they are not migration-parity evidence for
wrapper-level `resume-or-start`.

This design chooses a language-foundation-first migration architecture. The
YAML DSL already has most required runtime primitives: `output_bundle`,
`variant_output`, `repeat_until`, `on_exhausted`, workflow input defaults,
structured refs, call frames, and runtime state. Workflow Lisp also already has
important composition substrate: pure `defun`, effectful `defproc`,
`WorkflowRef`, `ProcRef`, `bind-proc`, `let-proc`, and `loop/recur`. The main
work is to complete and generalize that substrate enough that recurring
patterns such as `review-revise-loop` can be defined as ordinary `.orc` code,
not compiler-special forms. For this migration slice, ordinary `.orc` code may
include a thin macro that specializes caller-specific record shapes into
monomorphic helper definitions before ordinary lowering, because the current
language does not yet provide polymorphic imported `defproc` signatures. That
macro or helper must itself be parsed from grammar-accepted `.orc` source and
expanded through the same generic pipeline available to any user, project,
generated, or standard-library `.orc`; it must not be a Python hand-built
review-loop AST. After that, the remaining work is to specify the few runtime
behaviors that are currently implementation details and add a machine-checked
promotion gate that prevents `.orc` workflows from replacing YAML while parity
remains regressive. The main runtime/spec exceptions are command bundle-path
injection, command-produced union bundle handling, generated write-root policy,
review-loop exhaustion projection, and machine-checked promotion evidence.

No runtime closures or runtime-transported procedure values are required for
this migration tranche.

## Intention And Goal

The intention is to make `.orc` a credible primary authoring surface for key
workflow families, not merely an alternate syntax that can compile toy or
single-pass examples. A promoted `.orc` workflow must preserve the operational
behavior authors rely on in YAML: structured outputs, review/revise loops,
carried review context, resume safety, input defaults, and observable migration
evidence.

The goal of this design is to identify the smallest principled set of
DSL/compiler/runtime and `.orc` library changes needed to reach that parity without
recreating YAML-era glue. In particular, recurring orchestration patterns
should be expressible as ordinary `.orc` surfaces over generic effectful
composition, while the runtime continues to enforce validated artifacts and
state rather than learning workflow-specific concepts.

## Context And Authority

Normative DSL behavior lives in `specs/`. Existing relevant contracts include:

- `specs/dsl.md`: workflow inputs/defaults, `output_bundle`, `variant_output`,
  `repeat_until`, `on_exhausted`, structured `match`, and `materialize_artifacts`.
- `specs/state.md`: authoritative `state.json`, call frames, `repeat_until`
  bookkeeping, artifact lineage, and resume state.
- `specs/io.md`: step output capture and output contract validation.

Workflow Lisp design authority is split across:

- `docs/design/workflow_lisp_stdlib_lowering.md`, which defines the current
  standard-library lowering inventory that this design narrows away from
  compiler-special review-loop behavior;
- `docs/design/lisp_frontend_review_fix_loops.md`, which sketches review/fix
  loop behavior;
- `docs/design/workflow_lisp_state_layout.md`, which defines generated state
  path ownership;
- `docs/design/workflow_command_adapter_contract.md`, which separates
  certified command adapters from hidden semantic glue.

The migration evidence currently shows two non-primary `.orc` targets:

- `cycle_guard_demo.orc` compiles and dry-runs, but the real run failed because
  the managed output bundle was not materialized at the expected path.
- `design_plan_impl_review_stack_v2_call.orc` preserves phase order and typed
  outputs, but does not preserve full YAML review/revise loops, carried
  findings, YAML input defaults, or real smoke parity.

## Problem

Key `.orc` replacements cannot become primary while the compiler and runtime
leave important behavior implicit:

- A `command-result` can lower to `output_bundle`, but the runtime/compiler
  contract for the bundle path, environment injection, and validation authority
  is not fully documented as a promotion requirement.
- `review-revise-loop` exists as a high-level authoring concept, but it cannot
  yet be defined as ordinary `.orc` library code. The blocker is not the
  absence of procedures, references, or loops; it is that `ProcRef` review/fix
  hooks inside generic loop bodies, compiler-owned result paths, typed
  exhaustion projection, carried evidence identities, typed review findings, and
  source-map-preserving generic `.orc` expansion are not yet proven outside a
  compiler-specific branch.
- Review findings are still entangled with report/pointer extraction in legacy
  YAML patterns instead of being typed state that revise/fix steps consume.
- Generated state paths and reusable phase state are not yet stable enough for
  primary `.orc` replacements of long-running workflows.
- `.orc` entrypoints cannot yet claim parity with YAML entrypoints that expose
  defaults unless defaults are represented at the Workflow Lisp boundary.
- Migration evidence lacks a hard promotion gate that distinguishes "parses and
  dry-runs" from "can replace the YAML primary."

Without a design-level boundary, these gaps invite local patches: hidden Python
adapters, pointer-as-state compatibility, prompt-side loop instructions, or
test-only fixtures. Those would reproduce the YAML migration debt that Workflow
Lisp is intended to remove.

## Goals

- Define which changes belong to DSL/spec, Workflow Lisp compiler, runtime, and
  migration policy.
- Close the parity gaps required to promote key workflows to `.orc`.
- Preserve existing runtime primitives where they are already sufficient.
- Keep structured state and validated artifacts as authority.
- Make generated state paths, bundle paths, and source maps deterministic.
- Support real review/revise/fix loops with typed terminal outcomes.
- Make review/revise/fix loops ordinary `.orc` code rather than
  compiler-special language forms.
- Support carried review findings without markdown report parsing as semantic
  authority.
- Require compile, shared validation, dry-run, real smoke where safe, and
  parity evidence before YAML deprecation.

## Non-Goals

- Do not add runtime closures or runtime-transported procedure values.
- Do not recreate YAML pointer choreography in high-level `.orc`.
- Do not make generated/debug YAML semantic authority.
- Do not promote the low-level cycle-guard demo itself as a high-level key
  workflow replacement unless native bounded-loop parity is intentionally
  designed later.
- Do not preserve inline shell/Python findings extraction as a permanent
  semantic path.
- Do not introduce a new DSL version solely to rename existing v2.14 surfaces.
- Do not add or preserve a compiler-special `review-revise-loop` implementation
  as the migration path.
- Do not require imported-procedure polymorphism or type parameters in this
  migration slice solely to express `review-revise-loop`.

## Decision

Use a language-foundation-first architecture with narrow runtime/spec contract
deltas.

The recommended approach is:

1. Treat existing YAML DSL primitives as the executable substrate.
2. Complete the existing generic `.orc` support needed to define effectful
   library abstractions over provider calls, command calls, typed loops,
   matches, generated result paths, source maps, and compile-time
   provider/prompt/workflow/procedure references.
3. Define `review-revise-loop` as ordinary `.orc` code on top of those generic
   capabilities. For this migration slice, the exported surface from
   `std/phase.orc` may be a thin macro that specializes caller-specific record
   types into a monomorphic helper definition or generated private workflow
   before ordinary lowering, as long as effects remain explicit after expansion
   and the compiler does not recognize `review-revise-loop` by name. The
   expansion source must be grammar-accepted `.orc`, not a
   review-loop-shaped Python AST constructor.
4. Finalize Workflow Lisp contracts for `command-result`, `resume-or-start`,
   state layout, and workflow input defaults.
5. Specify and implement normative command structured-output behavior:
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the command's authoritative bundle
   target for command steps with deterministic structured bundle contracts.
6. Introduce generic structured dataflow guidance for review-result and finding
   records.
7. Add a machine-validated migration promotion gate that keeps YAML primary
   until parity evidence is non-regressive. `non_regressive` is computed by the
   promotion command from evidence; authors must not assert it by hand.

### Minimum Migration Slice

This design deliberately does not require completing every future `.orc`
composition feature before migration can continue. A key workflow may attempt
`.orc` promotion after this narrower slice is implemented and tested:

1. `command-result` lowers to authoritative generated bundle contracts with
   compiler-owned paths and runtime bundle-path injection.
2. Imported `.orc` definitions can generate provider steps, command
   steps, `match`, and one resume-safe typed loop form with stable source maps
   and stable persisted checkpoint identity.
3. Reusable library and wrapper workflows have a generic authored surface for
   building union-returning reusable-result adapters or an equivalent
   specialization route, rather than relying on compiler-generated-only
   `UnionVariantExpr` behavior.
4. Promoted entry workflows have a generic context-bootstrap route for
   internal `RunCtx` / `PhaseCtx` construction with runtime-owned run ids and
   roots hidden from the public entrypoint boundary.
5. `review-revise-loop` is an exported `.orc` surface over compile-time `ProcRef`
   review/fix hooks. It may lower through an imported monomorphic
   `defproc`/workflow or through a thin macro that specializes concrete
   caller types into an equivalent generated helper. Caller-owned review/fix
   procedures may use provider and prompt externs, but the loop does not carry
   provider or prompt refs as runtime state.
6. Generic `loop/recur` supports typed exhaustion projection through current
   `repeat_until.on_exhausted` scalar overrides plus final projection from the
   last loop-frame state.
7. Provider, prompt, workflow, and procedure refs are compile-time-only and
   fully specialized before executable runtime state is produced.
8. Parity evidence proves the generated executable shape matches the YAML
   baseline.

Generic macros, broader `.orc` packaging, and arbitrary nested effectful
composition remain follow-on work unless this review-loop implementation
requires them.

Feasibility proof status:

- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
  records the current proof. The architecture is conditionally feasible, but
  not proven by the current checkout.
- The prior viable route assumed a single imported `defproc` over
  compile-time `ProcRef` review and fix hooks, plus generic `loop/recur`
  exhaustion projection. The blocker report shows that assumption is too strong
  for the current language because imported `defproc` parameters are
  monomorphic and the retained review-loop surface passes caller-specific
  `completed` and `inputs` record types. The accepted route for this migration
  slice is therefore a thin macro or equivalent compile-time
  specialization layer that produces monomorphic helpers before ordinary
  lowering. The current compiler-special `ReviewReviseLoopExpr` path is useful
  evidence for the generated shape, but it does not satisfy this architecture.
- Promotion work must first add fixtures proving imported `.orc` usage lowers
  without recognizing the literal `review-revise-loop` name in typecheck or
  lowering.

Alternatives considered:

- **DSL-first new primitives.** Add new YAML DSL constructs for review loops,
  findings, phase state, and command results. This would make the substrate
  larger even though v2.7-v2.14 already have the needed execution primitives.
  Reject for this tranche.
- **Compiler-special stdlib lowering.** Recognize `review-revise-loop` directly
  in the compiler and lower it to generated `repeat_until`/`match`/provider
  steps. This may be expedient, but it bakes one workflow idiom into the
  compiler and delays the more important `.orc` composition model. Reject as the
  migration path.
- **Polymorphic imported `defproc`.** Add procedure type parameters or
  equivalent imported-procedure polymorphism so one imported `defproc` can accept
  arbitrary caller `completed` and `inputs` record shapes. This may still be a
  valid future language extension, but it is not the minimum change needed to
  unblock migration parity. Reject for this tranche.
- **Legacy adapter migration.** Wrap missing behavior in certified adapters and
  preserve YAML-era pointer/report conventions. Useful only for explicitly
  allowlisted compatibility. Reject as the primary architecture.
- **Language-foundation-first stdlib.** Complete generic effectful composition
  and source-map-preserving library expansion first, then implement review loops
  as ordinary `.orc` code, allowing a thin macro specialization
  layer where the current monomorphic procedure type system requires it. This
  is the selected approach.

## Required Changes By Gap

| Gap | Required extension | Primary owner | DSL/spec impact | Promotion evidence |
| --- | --- | --- | --- | --- |
| Command-result structured return materialization | Final `command-result` lowering contract and runtime bundle-path contract | Workflow Lisp lowering + runtime executor | Normative command bundle-path behavior in `specs/dsl.md` and `specs/io.md` | Real command smoke proves env injection, bundle validation, and missing-bundle failure |
| Review/revise loop parity | Complete generic effectful `.orc` library composition, then implement `review-revise-loop` as `.orc` code, allowing thin compile-time specialization for caller-specific record types | Workflow Lisp language/compiler + `.orc` libraries | No new YAML DSL construct if v2.7/v2.12 semantics plus final projection suffice | REVISE/fix/APPROVE and exhaustion tests |
| Imported review-loop resume checkpoint identity | Preserve one stable `repeat_until` checkpoint identity across imported `.orc` specialization, persisted runtime state, authored/debug projections, and resume lookup | Workflow Lisp lowering + runtime state mapping | Clarify repeat-until checkpoint identity ownership in state/runtime contracts; no new YAML DSL construct | Imported stdlib review-loop resume fixture proves the persisted checkpoint is stored and resumed under the authored/generated loop-step identity |
| Carried findings/review state | Generic structured output/dataflow support, with concrete review-result and findings schemas owned by the `.orc` review loop | `.orc` library definitions + Workflow Lisp generic validation | No new YAML DSL construct; use declared structured bundles | Findings schema validation and revise/fix consumption |
| Mixed-root review-loop report/findings path ownership | Split report-path seeding from findings-path seeding in imported `review-revise-loop` specialization so `review_report` / `last_review_report` stay on review-path contracts while `ReviewFindings.items_path` stays on `ReviewFindingsJsonPath` under `artifacts/work` | Workflow Lisp typecheck/lowering + `.orc` stdlib review-loop | No new YAML DSL construct; clarify typed path seeding and validation ownership for imported review loops | Imported review-loop fixtures and family compile proofs show `artifacts/review` reports and `artifacts/work` findings coexist without type coercion |
| Reusable-result wrapper construction | Generic authored union-construction or specialization surface for wrapper workflows that normalize approved-only reusable results | Workflow Lisp parser/typecheck/lowering + `.orc` libraries | No new YAML DSL construct; must remain an ordinary `.orc` or generic specialization surface | Compile a reusable phase wrapper that returns an authored union and drives `resume-or-start :valid-when (APPROVED)` without compiler-special family support |
| Entrypoint context bootstrap | Generic promoted-entry bootstrap split into two required sub-capabilities: runtime-owned internal `RunCtx` / `PhaseCtx` construction at the public boundary, and hidden binding of reusable internal calls whose signatures require those context values | Workflow Lisp lowering + state-layout/runtime bridge | Clarify runtime-owned context inputs, hidden binding policy, promoted-entry call binding rules, and the failure taxonomy when hidden bootstrap is unavailable | Compile and dry-run or execute a promoted wrapper that calls a reusable union-returning `resume-or-start` surface without public run-id/state-root/artifact-root inputs, without explicit or defaulted authored `phase-ctx` fallback inputs, and without a `[workflow_signature_mismatch]` missing-binding failure on the internal reusable call |
| Resume/state semantics | State layout and `resume-or-start` reusable-state validation contract | Workflow Lisp state layout + runtime/adapters | Clarify reusable state shape and failure taxonomy | Reusable, stale, missing artifact, failed, and schema-mismatch cases |
| Default input parity | `.orc` boundary syntax and lowering for workflow input defaults | Workflow Lisp parser/typecheck/lowering | Existing DSL input default support | Compile/lower/default override tests |
| Real smoke coverage | Migration promotion checklist and parity report schema | Migration policy/tests | New machine-readable migration report schema | Computed `non_regressive`, not manually asserted |

Implementation owner matrix:

| Concern | Owner / file area |
| --- | --- |
| Input defaults | `orchestrator/workflow_lisp/workflows.py`, `specs/dsl.md` |
| Record, union, and findings contracts | `orchestrator/workflow_lisp/contracts.py`, `.orc` stdlib schemas |
| Managed bundle paths | `orchestrator/workflow_lisp/lowering.py`, runtime command executor bridge |
| `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` injection | runtime command execution, `specs/io.md`, `specs/dsl.md` |
| `review-revise-loop` lowering | `.orc` stdlib/generic effectful composition and Workflow Lisp lowering |
| Reusable-result wrapper construction | Workflow Lisp expressions/typecheck/lowering and generic `.orc` specialization |
| Entrypoint context bootstrap | Workflow Lisp lowering, state-layout ownership, runtime-managed hidden inputs |
| State/reuse validation | Workflow Lisp state layout, shared validation, certified validators |
| Parity report | migration tooling, parity tests, generated report schema |

### Newly Exposed Prerequisite Gaps

The blocked `design_plan_impl_stack` family pass did not invalidate the
selected architecture, but it did show that four capabilities were still being
assumed rather than specified. Future design-gap selection should treat them as
explicit prerequisite gaps ahead of rerunning that family slice:

1. `workflow-lisp-reusable-result-wrapper-construction`
   - Scope: authored or generically specialized construction of family-local
     union-returning reusable wrapper results, including approved-only wrappers
     used to make `resume-or-start :valid-when (APPROVED)` legal without
     compiler-generated-only variant constructors.
   - Non-goal: family-specific compiler branches or hard-coded wrapper names.
2. `workflow-lisp-entrypoint-context-bootstrap`
   - Scope: runtime-owned hidden binding and lowering policy for internal
     `RunCtx` / `PhaseCtx` construction at promoted entry workflow boundaries,
     including run-id/root derivation, source maps, public-input hiding, and
     hidden binding of reusable workflow or `resume-or-start` calls whose
     internal signatures require context values not present on the authored
     public entry boundary.
   - Decomposition:
     - `entry-boundary bootstrap`: derive runtime-owned `RunCtx` /
       `PhaseCtx` values for a promoted entry workflow without exposing public
       `run-id`, `state-root`, `artifact-root`, or authored top-level
       `phase-ctx` inputs.
     - `hidden reusable-call binding`: satisfy required internal context
       parameters on reusable workflow or `resume-or-start` calls from those
       runtime-owned bindings, so the promoted wrapper does not fail with
       `[workflow_signature_mismatch] call is missing required binding
       \`phase-ctx\``.
   - Acceptance fixture: a dedicated promoted-entry bootstrap fixture that
     calls a union-returning reusable wrapper through
     `resume-or-start :valid-when (APPROVED)` and proves both that the compiled
     public boundary excludes `phase-ctx__*`, `run-id`, `state-root`,
     `artifact-root`, and managed write-root inputs, and that compile plus
     dry-run or execution succeed only because runtime-owned hidden bootstrap
     bindings satisfy the internal call contract.
   - Acceptance checkpoints:
     1. Public-boundary inspection proves the promoted entry exposes only its
        authored business inputs and excludes `phase-ctx__*`, `run-id`,
        `state-root`, `artifact-root`, and managed write-root inputs.
     2. Executable proof drives a reusable union-returning
        `resume-or-start :valid-when (APPROVED)` path and succeeds only because
        the runtime-owned bootstrap bindings satisfy the internal reusable call
        contract.
     3. A compile-only or dry-run-only proof attributable to synthetic
        top-level `PhaseCtx` defaults does not satisfy this prerequisite.
   - Non-goal: exposing `run-id`, `state-root`, or `artifact-root` as new
     required user inputs for promoted wrappers, or treating synthetic
     top-level `PhaseCtx` defaults as sufficient parity evidence.
3. `workflow-lisp-review-loop-report-findings-path-split`
   - Scope: imported `review-revise-loop` specialization must seed review-report
     fields and findings-path fields independently, so `review_report` and
     `last_review_report` may remain on review-report contracts rooted under
     `artifacts/review` while `ReviewFindings.items_path` remains on
     `ReviewFindingsJsonPath` rooted under `artifacts/work`.
   - Required behavior:
     - the initial `ReviewFindings` carrier must not be built from the same
       expression used for `review_report` or `last_review_report`;
     - the compiler/typechecker must reject or avoid lowerings that coerce both
       surfaces onto one shared path type;
     - imported stdlib and project-authored review-loop consumers must be able
       to keep human review reports and structured findings on their distinct
       authority paths without family-local adapter glue.
   - Acceptance fixture: an imported review-loop fixture and at least one
     family-style compile proof where review reports stay under
     `artifacts/review`, findings JSON stays under `artifacts/work`, and the
     resulting `ReviewDecision` / `ReviewLoopResult` contracts typecheck
     without aliasing the two path roles.
   - Non-goal: moving findings into review-report paths, weakening
     `ReviewFindingsJsonPath`, or requiring family-local coercion helpers to
     satisfy the generic stdlib route.
4. `workflow-lisp-imported-review-loop-resume-checkpoint-identity`
   - Scope: imported `review-revise-loop` lowering must preserve one stable
     `repeat_until` checkpoint identity across authored mappings, generated or
     private workflow specialization, persisted runtime state, and resume
     lookup.
   - Required behavior:
     - the persisted `state.json.repeat_until` entry for an imported stdlib
       review loop must be keyed by the same stable loop-step identity exposed
       by authored/debug projections for that run;
     - resume must find and reuse that checkpoint identity after an
       interruption in the `REVISE -> fix -> APPROVE` path rather than falling
       back to a transient allocator name or losing the frame entirely;
     - source maps and observability must still connect that persisted loop
       identity back to the imported `.orc` call site and specialized helper
       origin.
   - Acceptance fixture: the imported stdlib review-loop resume fixture in
     `tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint`
     must persist a `repeat_until` frame under the authored/generated
     `repeat_step["name"]` identity and complete successfully after resume.
   - Non-goal: family-local checkpoint aliases, weakening the proof to accept
     any repeat-until frame regardless of identity, or treating compile-only
     evidence as sufficient for resume parity.

Selection note:

- `workflow-lisp-review-loop-report-findings-path-split` should be drafted and
  selected as its own prerequisite migration gap before rerunning any family
  parity slice that keeps review reports under `artifacts/review` while
  carried findings remain under `artifacts/work`.
- `workflow-lisp-imported-review-loop-resume-checkpoint-identity` should be
  drafted and selected as its own prerequisite migration gap before rerunning
  any family parity slice that depends on imported stdlib review-loop resume
  after a persisted `REVISE` checkpoint.
- `workflow-lisp-entrypoint-context-bootstrap` should be drafted and selected
  as its own prerequisite migration gap before rerunning any family parity
  slice that depends on wrapper-level `resume-or-start` from a promoted entry
  workflow.
- The drafted gap should treat the missing-`\`phase-ctx\`` promoted-entry
  failure as its motivating negative fixture and should not allow a family
  parity slice to proceed on public-boundary inspection alone.
- The drafted imported-review-loop checkpoint gap should treat the
  `KeyError: 'rl_rl18_5_h_1__loop'` failure as its motivating negative fixture
  and should not allow a family parity slice to proceed on compile-only or
  first-run-only review-loop evidence.

## Architecture

The architecture has four layers.

```text
.orc authoring
  -> Workflow Lisp parser/typecheck/effectful library composition
  -> .orc workflows/procedures/macros
  -> Core Workflow AST / Semantic IR / Executable IR
  -> existing DSL runtime primitives
  -> migration parity evidence
```

## Normative Spec Status

Before any `.orc` candidate can replace a YAML primary, required behavior must
live in normative specs or a machine-readable schema, not only in this
architecture doc.

- `specs/dsl.md`: command steps with deterministic structured bundle contracts
  receive a runtime-resolved bundle target.
- `specs/io.md`: define `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, parent-directory
  creation, stdout-vs-bundle authority, and missing/invalid bundle behavior.
- `specs/state.md`: define the output-contract failure shape for missing or
  invalid command bundles after process exit `0`.

Remaining normative/schema work before acceptance:

- Path-safety spec surface: define workspace-relative normalization, rejection
  of absolute paths and `..` escapes, and symlink policy for generated bundle
  and state paths.
- Migration evidence schema: define the parity report fields and require
  `non_regressive` to be computed from evidence, not manually asserted.

Command-produced union results must lower to a variant-proof surface and must
not depend on an implicit `variant_output` path. Until `variant_output.path` is
normative, primary-promotion candidates may use one of two explicit strategies:

1. Add normative `variant_output.path` support and lower `command-result`
   unions directly to `variant_output`.
2. Lower the command to an `output_bundle` containing the raw discriminant and
   payload, then generate a compiler-owned validator/projection step that emits
   a variant-proof-compatible result.

The compiler must not expose output-bundle variant fields directly as if they
had selected-variant proof. Downstream variant-specific fields are available
only through `variant_output` proof or the compiler-owned projection's
equivalent discriminant proof.

## Related Doc Updates Required

Before this design is accepted rather than draft, align the dependent authoring
and lowering docs:

- `docs/lisp_workflow_drafting_guide.md`: label `review-revise-loop` as
  primary-migration-pending unless the ordinary `.orc` implementation exists.
- `docs/design/workflow_lisp_stdlib_lowering.md`: record that
  review-loop-specific compiler lowering is rejected for this tranche.
- `docs/design/lisp_frontend_review_fix_loops.md`: map YAML terminal statuses
  to `ReviewDecision` and `ReviewLoopResult`.

### 1. Workflow Lisp Authoring Layer

The authoring layer exposes primitive effectful forms and ordinary library
abstractions.

Primitive effectful forms include:

- `command-result`
- `provider-result`
- `run-provider-phase`
- `resume-or-start`
- `resource-transition`

Library abstractions include:

- `review-revise-loop`
- `finalize-selected-item`
- `backlog-drain`

Authors should express typed workflow behavior. They should not write hidden
bundle paths, pointer files, markdown extraction, or loop routing glue.

`review-revise-loop` currently lives in `std/phase.orc`, but the required
machinery is not stdlib-specific. It must compile through the same generic
machinery as project-authored `.orc` code. For this migration slice, the
imported surface may be a workflow, procedure, or thin macro that specializes
caller-specific record types into monomorphic helpers before lowering. The
compiler may know about the primitive forms that expanded `.orc` uses, but it
must not contain a review-loop-specific lowering branch or a special-case on
the literal `review-revise-loop` name.

### Generic `.orc` Expansion Contract

The expansion contract applies to all `.orc` source: user modules, project
modules, generated/private modules, and standard-library modules.
`review-revise-loop` is only the motivating migration case.

The required pipeline is:

```text
user .orc / project .orc / generated .orc / standard-library .orc
  -> grammar parser
  -> frontend AST
  -> macro/procedure expansion
  -> compile-time ref and type specialization
  -> ordinary Core AST
  -> shared validation
  -> executable workflow DSL
```

Compiler Python may implement generic language machinery: parsing,
deterministic macro expansion, effectful procedure/workflow specialization,
compile-time reference specialization, hygienic generated names and paths,
source-map propagation, typechecking, and lowering of ordinary Core AST nodes.

The compiler must maintain a formal extension boundary for recognized heads.
Each recognized head should be classified as a core language form, core effect
bridge, standard-library extension, or temporary compiler intrinsic with an
owner, rationale, and removal condition when temporary. Macro reserved-name
rules, expression elaboration dispatch, lint/denylist checks, and intrinsic
documentation should derive from that boundary rather than from parallel
hand-maintained lists. `review-revise-loop` is a standard-library extension,
not a core language form; temporary compiler intrinsics must be explicit debt,
not accidental neighbors in the expression union.

The frontend AST should represent language concepts: procedure calls, matches,
loops, records, union variants, projections, provider and command results,
materialization, and compile-time `ProcRef` specialization. It should not grow
domain nodes for product workflow idioms. A node whose fields are
`review_provider`, `fix_provider`, `review_prompt`, `fix_prompt`,
`checks_report`, or `progress_report` is evidence that review-loop semantics
have crossed the language boundary. Those fields belong in `.orc` records,
unions, procedure parameters, and imported definitions.

Compiler Python must not encode review-loop domain control flow. Large Python
blocks that directly construct a review-loop-shaped tree of `MatchExpr`,
`MatchArm`, `DoneExpr`, `UnionVariantExpr`, and field projections are acceptable
only if they are part of a generic typed-template or expansion engine used by
arbitrary `.orc` definitions. They are not acceptable as the semantic route for
`review-revise-loop` itself.

The typechecker must validate declared records, unions, procedure signatures,
variant proof, and structured refs generically. It must not contain a private
contract for `APPROVED`, `BLOCKED`, `EXHAUSTED`, or expected review-loop fields
unless `review-revise-loop` has been explicitly accepted as a language
primitive. The lowerer may dispatch on language AST constructs, but not on the
domain name `review-revise-loop`.

A generic expansion representation may record parsed expansion AST, authored
call-site source, library definition source, specialization bindings,
generated-name/path allocator identity, expansion stack, and source-map
provenance. It must not contain review-loop-specific fields such as
`review_provider`, `fix_provider`, `checks_report`, or `progress_report`; those
belong in `.orc` records, unions, procedure parameters, and library definitions.
If an internal wrapper is needed during expansion, it should be eliminated
before ordinary typechecking/lowering or have no semantic dispatch behavior of
its own.

### Required Generic `.orc` Support

The following support is required before `review-revise-loop` can be a normal
library definition. This is completion work on the current language model, not
a restart. Current support already includes pure `defun`, effectful `defproc`,
`WorkflowRef`, `ProcRef`, `bind-proc`, `let-proc`, and `loop/recur`.

1. **Effectful library procedures, workflows, or macro-specialized helpers.** A
   reusable `.orc` definition can already be represented with `defproc` and
   workflow/procedure refs. The remaining requirement is to make that path
   sufficient for reusable control combinators, including the case where a thin
   macro must specialize caller-specific record shapes into monomorphic helpers
   before lowering: imported `.orc` definitions must preserve
   sequencing, artifacts, output refs, validation, source maps, and effect
   graph entries across nested provider calls, command calls, `match`, typed
   loops, and calls to other workflows/procedures.

2. **Compile-time procedure hooks for review and fix behavior.** Workflow and
   procedure refs already have a static authoring model. The review-loop proof
   uses `ProcRef` review/fix hooks: caller-owned procedures bind or directly use
   provider and prompt externs, then the loop receives only specialized
   procedure refs or macro-specialized monomorphic helper parameters. Provider
   and prompt refs may still need better compile-time parameter support for
   broader `.orc` library ergonomics, but the migration proof must not depend on
   carrying provider or prompt refs through loop state.

3. **Composable typed loops.** `loop/recur` already provides typed iterative
   control. The remaining requirement is to prove and, where needed, complete
   its use inside imported `.orc` procedures/workflows, with typed loop
   outputs, a typed terminal result, explicit exhaustion, source maps,
   resume-safe lowering, and one stable persisted checkpoint identity that the
   resumed run can resolve back to the same loop frame.

4. **Generic result-bundle and path allocation.** Library code must request
   semantic targets such as "review decision bundle" or "phase result bundle"
   without exposing `__write_root__...` inputs or hard-coded paths. The compiler
   owns deterministic allocation, validation, source maps, and path-safety
   checks.

5. **Hygienic source-map-preserving expansion.** Existing macro hygiene must
   either be kept out of effectful macro control flow or extended with explicit
   effect introduction. If macros are used to make the library ergonomic,
   expansion must preserve authored origin, library origin, generated step
   origin, generated hidden-input origin, and generated path origin.
   Macro-introduced effects must remain visible to validation and the effect
   graph.

6. **Structured dataflow for review results.** The language does not
   need built-in findings semantics. It needs generic records, unions,
   structured provider outputs, typed procedure parameters, and loop-carried
   values sufficient for the `.orc` `review-revise-loop` definition to define
   review decisions, findings, reports, blocker classes, and exhaustion reasons.
   Until list types are available, findings may be carried as a schema-validated
   JSON artifact path, but the semantic value must be validated before
   publication and revise/fix consumption rather than extracted from markdown.
   Imported review-loop specialization must seed report fields and findings
   paths independently: `review_report` / `last_review_report` may stay on
   review-report contracts under `artifacts/review`, while
   `ReviewFindings.items_path` remains a findings JSON path under
   `artifacts/work`. Reusing the review-report expression as the findings seed
   is not an allowed lowering shortcut.

7. **Module visibility and library packaging.** Imported `.orc`
   workflows/procedures/macros must import, export, specialize, and source-map
   consistently whether they come from project modules or standard-library
   modules. A consumer should be able to inspect which `.orc` definition
   generated each executable node.

8. **Negative validation for abstraction leaks.** The compiler must reject
   library definitions that leak hidden write-root inputs, treat pointer files
   as state authority, hide effects in macros, or route on report prose.
9. **Reusable-result wrapper construction.** Authors or generic specialization
   machinery must be able to construct family-local union-returning reusable
   result wrappers in ordinary `.orc` code. Family parity must not depend on a
   surface where only compiler-generated helpers can produce union variants.
10. **Entrypoint context bootstrap.** Promoted wrapper workflows need a
   supported route to obtain internal `RunCtx` / `PhaseCtx` values with
   runtime-owned run ids and roots. Existing derived-context helpers such as
   `phase-ctx` are not sufficient when no parent context is already present at
   the authored entry boundary. This prerequisite has two separately auditable
   responsibilities: deriving those runtime-owned context values at the entry
   boundary, and using them to satisfy hidden required bindings on reusable
   internal calls. A proof that checks only the public workflow boundary is
   incomplete if the first executable reusable call still fails with
   `[workflow_signature_mismatch] call is missing required binding
   \`phase-ctx\``.

Readiness before acceptance:

| Capability | Required for review loop? | Acceptance fixture | Acceptance status |
| --- | --- | --- | --- |
| Imported `.orc` surface that lowers to effectful `defproc`/workflow behavior | Yes | Import review loop and emit DSL-visible provider, command, loop, and match nodes without compiler name recognition | Must be proven by implementation audit |
| `ProcRef` review/fix hook specialization | Yes | Pass caller-owned review/fix procedures into imported `.orc` code and emit no runtime proc value | Must be proven by implementation audit |
| Provider/prompt extern use inside selected procedures | Yes | Review/fix procedures produce provider steps after specialization without loop-carried provider or prompt refs | Must be proven by implementation audit |
| `loop/recur` to resume-safe DSL loop | Yes | `REVISE -> fix -> APPROVE` with a persisted loop checkpoint stored and resumed under the authored/generated loop-step identity | Must be proven by implementation audit |
| Generic `loop/recur` exhaustion projection | Yes | Exhaustion returns `ReviewLoopResult.EXHAUSTED` using scalar overrides plus last loop-frame outputs | Must be proven by implementation audit |
| Generated bundle/path allocation | Yes | Compile imported review loop without public hidden write-root inputs | Must be proven by implementation audit |
| Independent report and findings path seeding | Yes | Imported review loop compiles when `review_report` / `last_review_report` use review-report contracts and `ReviewFindings.items_path` uses `ReviewFindingsJsonPath` under `artifacts/work` | Must be proven by implementation audit |
| No compiler-special review-loop recognition | Yes | Imported `.orc` usage still compiles when review-loop-specific expression, typecheck, and lowering paths are absent or disabled | Must be proven by implementation audit |
| Effect graph and source maps across generic `.orc` expansion | Yes | Generated nodes record call site, imported definition, and generated-node provenance | Must be proven by implementation audit |
| Negative validation for abstraction leaks | Yes | Reject imported `.orc` definitions that route on report prose, leak hidden roots, or hide effects | Must be proven by implementation audit |
| Authored reusable-result wrapper construction | Yes | Compile a reusable phase wrapper that returns an authored union and feeds `resume-or-start :valid-when (APPROVED)` without compiler-family special casing | Must be proven by implementation audit |
| Entrypoint context bootstrap without public context inputs | Yes | Compile and dry-run or execute a promoted wrapper that internally derives `RunCtx` / `PhaseCtx`, drives a reusable union-returning `resume-or-start` wrapper, exposes no public `phase-ctx__*`, run-id, state-root, artifact-root, or managed write-root inputs, and does not require explicit/defaulted authored `phase-ctx` fallback wiring on the first reusable internal call | Must be proven by implementation audit |

New or completed authoring syntax:

The active parity tranche targets the same first-tranche review-loop carrier
and terminal protocol owned by
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`.
This section summarizes that contract only because the parity fixtures depend on
it. If wording ever diverges, the integration doc is the owner for the exact
`ReviewFindings`, `ReviewDecision`, and `ReviewLoopResult` schema.

```lisp
(defpath ReviewFindingsJsonPath
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defrecord ReviewFindings
  (schema_version String)
  (items_path ReviewFindingsJsonPath))

(defunion ReviewDecision
  (APPROVE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (REVISE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings)))

(defunion ReviewLoopResult
  (APPROVED
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings))
  (EXHAUSTED
    (last_review_report ReviewReportPath)
    (findings ReviewFindings)
    (reason String)))
```

`ReviewDecision` is the per-iteration review result. `ReviewLoopResult` is the
terminal loop result. `APPROVE` maps to terminal `APPROVED`; `REVISE` invokes
revise/fix and repeats; `BLOCKED` maps to terminal `BLOCKED`; max-iteration
exhaustion maps to terminal `EXHAUSTED`. Raw unconstrained `Json` findings do
not satisfy primary-promotion parity. Until first-class list types exist,
`items_path` must point to JSON that validates against `ReviewFindings.v1`
before publication and before revise/fix receives it.

There is no first-tranche generic `ReviewFinding` item record. The typed
carrier plus the validated minimum `ReviewFindings.v1` envelope are the whole
stdlib-owned contract for this slice.

`ReviewFindings.items_path` and `review_report` / `last_review_report` are
intentionally different contracts. Review-loop specialization must allocate or
accept them independently. A compiler or typechecker path that seeds findings
from the review-report expression, or coerces both to one shared path type,
does not satisfy this design.

`ReviewFindings.v1` is validated by a Workflow Lisp `defschema` validator if
available in this tranche, or by a certified `review-findings-v1` validation
adapter generated by the `.orc` review loop. `schema_version` must equal
`ReviewFindings.v1`; a plain string value is not sufficient without that
validation rule. Validation runs before the `ReviewFindings` record is
published to loop state and again before revise/fix receives it after resume.
Malformed findings fail as an output-contract failure, not as a review
decision.

Workflow input defaults should be expressible at the boundary:

```lisp
(defworkflow design-plan-impl-review-stack
  ((brief_path BriefPath :default "workflows/examples/inputs/design_brief.md")
   (design_target_path DesignDocTarget :default "docs/plans/example-design.md"))
  -> StackOutput
  ...)
```

Syntax status: proposed. Semantic contract: accepted target after spec and test
gates. Defaults belong to the workflow boundary, obey the same path/type
validation as explicit inputs, and are overridden by CLI/caller-provided inputs.

### 2. Compiler And Lowering Layer

The compiler owns all generated paths and hidden wiring. Generated write-root
inputs are not public workflow API.

Generated write roots may be hidden from the user-facing `.orc` API only if the
compiler lowers them to deterministic DSL-visible bindings that satisfy the
reusable-call write-root contract. Each generated root needs a stable semantic
identity derived from workflow id, call-site id, phase id, loop iteration where
applicable, and compiler/language version; source-map provenance; collision
checks across repeated calls and branch/loop expansions; resume reconstruction
rules; and a debug/explain projection.

Compiler-generated bundle and temporary paths must be run-isolated unless the
authored contract explicitly requests a stable workspace artifact. Stable
semantic identity is source-map/debug identity; the concrete write path must
include the runtime run root or another collision-proof generated namespace.
Resume must reconstruct the same concrete path for the same run.

V1 managed bundle path model:

- The compiler may emit internal managed write-root inputs for generated bundle
  paths because the current lowering path already represents managed write roots
  that way.
- Loader/runtime binding owns those values before validation/execution. CLI
  users and workflow callers must not be required to provide or override them.
- Public compiled workflow documentation and promoted entrypoint help must hide
  these inputs. Debug projections may show them only with generated-origin
  metadata and source-map provenance.
- Shared validation must distinguish public required inputs from internal
  managed inputs. A promoted entrypoint fails parity if tests or users must pass
  `__write_root__...` inputs manually.
- The runtime reconstructs the same managed value for the same run on resume and
  rejects caller-provided conflicting values for runtime-owned command bundle
  targets.

The compiler owns generic primitives and generic library expansion. It must not
own workflow-specific control idioms such as `review-revise-loop`.

`command-result` lowering must:

- map record return types to deterministic JSON-bundle contracts;
- map union return types to a variant-proof surface: either normative
  `variant_output.path`, or an authoritative `output_bundle.path` followed by a
  compiler-owned validator/projection step with equivalent discriminant proof;
- generate a deterministic result-bundle path;
- record source-map origins for the high-level form, generated step, and
  generated path;
- ensure the command receives the resolved bundle path through the runtime
  command environment;
- expose only validated bundle fields as typed refs;
- ignore stdout JSON for semantic success;
- reject command boundaries without certified command metadata when the command
  carries workflow semantics.

Generic effectful composition must:

- specialize caller-owned review/fix `ProcRef` hooks before runtime artifacts
  are produced, with provider and prompt externs resolved inside those selected
  procedures rather than carried by the loop;
- allow imported reusable library definitions to generate provider steps,
  command steps, `match`, typed loops, and materialization through ordinary
  composition;
- preserve source maps across authored call site, imported `.orc` definition, macro
  expansion if any, generated Core statements, hidden inputs, and generated
  paths;
- keep generated effects visible in Semantic IR and the effect graph;
- reject runtime transport of procedure/provider/prompt refs.

Generic authored composition for migration parity must also:

- provide a non-family-specific way to construct or specialize union-returning
  reusable wrapper surfaces in authored `.orc` code; and
- provide a runtime-owned hidden-binding route for entry workflow context
  bootstrap so wrapper-authored calls to reusable phase workflows do not invent
  fake `RunId` literals, require new public context inputs, or depend on
  explicit/defaulted authored `phase-ctx` fallback parameters at the promoted
  entry boundary.

Consumed evidence identities such as `checks_report` are loop inputs, consumed
artifacts, or workflow/materializer outputs. Review providers inspect and judge
evidence; they do not become the authority that authors consumed evidence paths
unless their declared contract actually produces those artifacts. Route and
final projection steps must carry evidence refs from input/state/materializer
authority, and validation must catch lowerings where provider output replaces
consumed evidence identity.

Reusable control forms lower by specializing imported `.orc` definitions before
Core DSL lowering. For this migration slice, the `std/phase.orc`
`review-revise-loop` export should compile as an imported workflow/procedure
boundary, or through a thin imported macro that specializes concrete caller
types into an equivalent generated private workflow or local helper boundary,
producing DSL-visible steps, call-frame state, loop state, source maps, and
outputs. It must not rely on macro-generated hidden effects, a
review-loop-specific compiler branch, or a Python implementation that
hand-builds the review-loop control tree outside the generic `.orc` expansion
pipeline.

The `review-revise-loop` `.orc` definition must compile through those generic
capabilities to the same executable families a hand-authored workflow would
use: `repeat_until`, provider steps, structured output bundles, `match`, and
materialization.

Future high-level `.orc` abstractions should normally be added by adding an
imported `.orc` definition, tests, and optionally an exported macro. They
should not require edits to expression node unions, typechecker branches,
lowerer branches, compiler visitors, or reserved-head lists unless the form is
being explicitly accepted as a core form or temporary compiler intrinsic.

Canonical generated executable shape for this migration slice:

```text
caller workflow
  call generated/private workflow stdlib__review_revise_loop__<call_site_id>
    inputs:
      draft/check artifact refs, loop budget, generated bundle roots
    compile-time specialization:
      selected review/fix behavior from ProcRef hooks
    outputs:
      ReviewLoopResult bundle, terminal status, review report, findings

generated/private workflow
  repeat_until review_loop:
    loop-frame outputs:
      review_status, latest_review_report, latest_findings,
      latest_review_decision_bundle
    steps:
      provider step writes ReviewDecision bundle
      match ReviewDecision:
        APPROVE -> materialize latest outputs and stop
        REVISE  -> run revise/fix, carry findings, recur
        BLOCKED -> materialize blocker outputs and stop
    on_exhausted.outputs:
      review_status = "EXHAUSTED"
  final projection:
    build ReviewLoopResult from review_status and loop-frame outputs
```

The caller observes a normal call-frame boundary and typed outputs. The private
workflow owns the `repeat_until` frame, generated bundle roots, and terminal
projection. This generated/private workflow is produced by generic `.orc`
specialization, whether reached from an imported procedure/workflow or a thin
macro, not by a review-loop-specific compiler primitive. If
implementation proves that inlining is required instead, this design must be
revised to spell out equivalent call-frame, source-map, and resume guarantees
before promotion.

Exhaustion lowering must respect current `repeat_until` behavior:

- The loop body materializes scalar review status and structured review result
  outputs on each completed iteration.
- `on_exhausted.outputs` overrides only scalar terminal markers, such as
  `review_status = "EXHAUSTED"`.
- The last review report and findings are loop-frame outputs from the final
  completed iteration, not values invented by exhaustion handling.
- A generated final projection step constructs `ReviewLoopResult.EXHAUSTED`
  from the scalar exhausted marker plus the last materialized review outputs.
- If the final iteration fails before those outputs exist, the loop fails as an
  ordinary execution or contract failure, not as `EXHAUSTED`.

`resume-or-start` lowering must:

- validate prior reusable state through a certified adapter or future
  runtime-native validator;
- normalize resumed and fresh branches to the same return type;
- require referenced artifacts to still exist;
- reject stale, failed, partial, or schema-incompatible state;
- never treat pointer-file existence as reusable-state authority.

Default lowering must:

- attach defaults to generated Core workflow input contracts;
- preserve caller override precedence;
- reject defaults that violate path roots, type contracts, or `must-exist`;
- keep compiler-owned hidden inputs out of public documentation unless a debug
  surface explicitly requests them.

Entrypoint context-bootstrap lowering must:

- derive internal `RunCtx` / `PhaseCtx` values from runtime-owned run metadata,
  generated state/artifact roots, and authored phase names;
- satisfy internal reusable workflow and `resume-or-start` call bindings that
  require those context values without surfacing authored fallback context
  inputs on the public workflow boundary;
- keep those context fields off the promoted public workflow boundary unless a
  debug/explain surface explicitly requests them;
- preserve deterministic source maps and managed-input provenance for generated
  context bindings; and
- reject wrapper designs that depend on user-supplied fake run ids or manual
  absolute root construction.

### 3. Runtime Layer

The runtime should not learn Lisp-specific behavior. It should execute the
generated Core DSL and enforce contracts.

Runtime/spec deltas required:

- For every command step declaring `output_bundle.path` or a future
  `variant_output.path`, the runtime resolves the workspace-relative contract
  path before command launch and exposes it as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. This environment variable is only the
  command's discoverable handle for the declared output target.
- If the command declares or receives a conflicting
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, the runtime-owned value wins.
- The runtime creates or validates the bundle parent directory according to the
  output contract before launch, then validates the bundle after exit `0`.
- The bundle file is authoritative for structured command results. Stdout may
  be captured for logs/debug, but stdout JSON is not semantic authority for
  promoted `.orc` workflows.
- If the command exits `0` and the bundle file is missing or invalid, the step
  fails as an output-contract failure.
- If the command exits non-zero, structured output validation does not mask the
  command failure.
- Resolved bundle paths must remain workspace-relative and path-safe.
- Repeat-until resume state remains the existing runtime authority for loop
  continuation; generated Lisp source maps are observability and debugging
  evidence, not runtime routing input.

These are general command-step contracts, not Lisp-specific runtime behavior.

### 4. Migration Evidence Layer

A `.orc` replacement can become primary only when a parity report says it is
non-regressive.

Intended YAML primary behavior is characterized from the current YAML primary at
the promotion baseline commit, its accepted tests, and a baseline run when one is
safe. Normative DSL specs win over accidental YAML behavior; explicit accepted
differences must be listed in the parity report.

Required evidence per promoted workflow family:

- compile always emits source `.orc`, a lowered workflow dictionary accepted by
  shared validation, source map, debug projection, compiler version, target DSL
  version, and generated-name manifest;
- optional compiler artifacts such as Core AST, Semantic IR, Executable IR,
  effect graph, proof graph, and reference catalog are emitted when implemented
  and accepted; otherwise the parity report records them as `not_implemented`;
- shared validation passes;
- dry-run passes;
- at least one real smoke or targeted integration run passes when safe;
- YAML baseline behavior is characterized;
- `.orc` output contracts, terminal states, artifacts, and resume behavior match
  the intended YAML primary behavior;
- deprecated YAML-era mechanics are explicitly listed and justified.

Real smoke is unsafe only when it would mutate external systems, spend
unbounded provider budget, require unavailable credentials, or alter user data
outside the workspace. In that case, the parity report must record
`smoke_or_integration.waived = true` with an owner, expiry, and justification,
and include targeted integration evidence for the skipped runtime behavior.

`cycle_guard_demo` should not block key high-level migration unless the project
chooses to support native `.orc` cycle-guard conformance. Its current fake
`terminal_status`/`guard_cycles` surface is useful as a command-result bridge
test, not as true parity with YAML cycle-guard semantics.

## Contracts And Interfaces

### Command Structured Output Contract

Old behavior:

- A command step with `output_bundle` validates a JSON file after successful
  command execution.
- Runtime implementation may expose a bundle path to commands, but migration
  docs did not treat this as a promotion contract.

New behavior:

- For command steps with declared structured bundle paths, the resolved bundle
  path is provided to the process as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- The command must write the structured bundle to that path.
- The runtime validates the bundle before exposing typed artifacts.
- The compiler must not require callers to pass compiler-owned hidden bundle
  inputs for promoted entrypoints.
- Command-produced union results use `variant_output.path` when that is
  normative. Until then, they use a generated `output_bundle.path` only for the
  raw discriminant and payload, followed by a compiler-owned
  validator/projection step that establishes variant proof.

Compatibility:

- Existing YAML command steps continue to work.
- Existing scripts that already honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` remain
  compatible.
- Stdout JSON may remain useful for manual debugging or legacy compatibility,
  but it is not the promoted semantic path.

### Review Loop Contract

Old behavior:

- YAML review loops use `repeat_until`, shell glue, report pointers, and
  sometimes inline findings extraction.
- Current `.orc` migrations can perform one draft/review pass without full loop
  parity.

New behavior:

- `review-revise-loop` is a standard `.orc` surface, currently exported from
  `std/phase.orc`, for bounded
  review/fix loops, not a compiler-special language form.
- It has two typed layers: `ReviewDecision` for one review iteration and
  `ReviewLoopResult` for the terminal loop result.
- `APPROVE` exits with `APPROVED`; `REVISE` deterministically invokes
  revise/fix and repeats; `BLOCKED` exits with `BLOCKED`.
- Exhaustion exits with `EXHAUSTED` only after the last completed iteration has
  produced the outputs required by the final projection.
- Reports are views; typed review decisions, terminal results, and validated
  findings are authority.
- `review_report` and `last_review_report` remain review-report contracts,
  while `ReviewFindings.items_path` remains a findings JSON contract. Imported
  review-loop lowering must not derive one from the other or force them onto a
  shared path type.
- Evidence artifact identities are carried from workflow state or consumed
  artifacts, not authored by the review provider. A reviewer may inspect and
  judge `checks_report`, but it must not redirect that evidence by returning a
  different path. If `ReviewLoopResult` includes `checks_report`, final
  projection copies it from the carried evidence input/state.

Transition table:

| Event | Loop action | `ReviewLoopResult` | YAML-compatible projection |
| --- | --- | --- | --- |
| `ReviewDecision.APPROVE` | Exit | `APPROVED` | Phase approved |
| `ReviewDecision.REVISE` with budget remaining | Run revise/fix and recur | None yet | Not completion |
| `ReviewDecision.REVISE` with budget exhausted | Exit through final projection | `EXHAUSTED` | Blocked / revise-exhausted |
| Provider-authored `ReviewDecision.BLOCKED` | Exit | `BLOCKED` | Blocked with blocker class |
| Invalid provider output | Fail contract | No semantic result | Provider output contract failure |

Compatibility:

- Existing YAML workflows remain primary until parity is proven.
- Legacy report extraction can remain behind allowlisted certified adapters only
  for migration, with replacement metadata.

### Reusable State Contract

Old behavior:

- YAML workflows frequently use file-existence gates, state-root conventions,
  and pointer files to decide whether work can be reused.

New behavior:

- `resume-or-start` validates a canonical prior state object and returns the
  same type as a fresh run.
- Reuse requires schema compatibility, approved terminal state, and existing
  referenced artifacts.
- Invalid prior state routes to fresh execution or a typed non-reusable result,
  depending on the authored form.
- `ReusablePhaseState.v1` is a derived, validated summary of canonical runtime
  state, not an alternative authority.

Minimum reusable-state shape:

```json
{
  "schema": "ReusablePhaseState.v1",
  "source_run_id": "",
  "source_step_id": "",
  "source_call_frame_id": "",
  "workflow_checksum": "",
  "phase_id": "implementation",
  "producer_workflow": "",
  "producer_compiler": "",
  "terminal": "APPROVED",
  "source_inputs_hash": "sha256:...",
  "producer_fingerprint": "sha256:...",
  "result_type": "ImplementationResult",
  "artifact_refs": {
    "plan_path": {
      "type": "relpath",
      "value": "docs/plans/example.md",
      "sha256": "..."
    }
  },
  "created_at": "",
  "compatibility": {
    "dsl_version": "2.14",
    "state_schema_version": ""
  }
}
```

Validation outcomes are `REUSABLE`, `STALE`, `MISSING_ARTIFACT`,
`FAILED_PRIOR_STATE`, `SCHEMA_MISMATCH`, and `UNSUPPORTED_VERSION`.
`STALE` means the prior state has a supported schema and terminal, but its input
hash, producer fingerprint, dependency hash, or artifact checksum no longer
matches the current reusable-state policy.

Hash and fingerprint derivation:

- `source_inputs_hash` is computed from canonical JSON for public workflow
  inputs after defaults and caller overrides are resolved. Relative paths are
  normalized workspace-relative. Inputs declared content-sensitive include the
  referenced file digest; ordinary path-valued inputs include the normalized path
  string. Generated hidden roots, run ids, timestamps, and absolute workspace
  prefixes are excluded.
- `producer_fingerprint` is computed from the `.orc` source digest, imported
  stdlib definition digests, compiler version, target DSL version, lowering
  options that affect executable shape, and specialized provider/prompt/workflow
  refs. It excludes transient runtime state.
- Artifact checksums are computed over the referenced artifact content after
  path-safety validation. A missing artifact is `MISSING_ARTIFACT`, not `STALE`.
- Schema or version incompatibility wins over staleness: unsupported schema or
  compatibility metadata returns `SCHEMA_MISMATCH` or `UNSUPPORTED_VERSION`
  before hash comparison.
- The producer records the source run id, source step id or call-frame id,
  workflow checksum, input hash basis, artifact lineage basis, and artifact
  content hashes used to validate reuse. On resume, the validator compares this
  summary against current policy and referenced artifact contents; it must not
  trust the summary alone.

Compatibility:

- Adapter-backed validators are acceptable initially.
- Pointer files remain compatibility representations only.

### Workflow Input Defaults

Old behavior:

- YAML workflow inputs support defaults.
- `.orc` promoted entrypoints may require explicit inputs even when the YAML
  primary did not.

New behavior:

- Workflow Lisp supports input defaults at the `defworkflow` boundary and
  lowers them to Core workflow input defaults.
- Literal defaults are type-checked at compile time, workspace/path constraints
  are checked during shared validation, and runtime checks are reserved for
  dynamic inputs whose existence cannot be proven earlier.

## Dependencies And Sequencing

Recommended sequencing:

1. Accept normative spec deltas for command structured-output bundle path
   injection, command-produced union bundle handling, output-contract failure
   shape, and path safety.
2. Document and test the command structured-output runtime contract.
3. Complete generic `.orc` effectful composition support for reusable library
   definitions: imported `.orc` use of `ProcRef` hooks, workflow refs and
   `loop/recur`, provider/prompt extern use inside selected procedures,
   generated path allocation, and source-map-preserving expansion.
4. Prove imported review-loop checkpoint identity so persisted `repeat_until`
   state is stored and resumed under the authored/generated loop-step identity.
   This is a standalone prerequisite gap:
   `workflow-lisp-imported-review-loop-resume-checkpoint-identity`.
5. Add the authored reusable-result wrapper construction surface needed for
   approved-only reusable adapters and wrapper-level `resume-or-start`.
6. Add entrypoint context-bootstrap support for runtime-owned internal
   `RunCtx` / `PhaseCtx` construction and hidden reusable-call binding without
   new public context inputs. The drafted prerequisite must prove both the
   promoted public boundary and the first executable reusable internal call.
   This is a standalone prerequisite gap:
   `workflow-lisp-entrypoint-context-bootstrap`.
7. Finalize `command-result` lowering so hidden bundle paths are compiler-owned
   and not public entrypoint inputs.
8. Split review-report path seeding from findings-path seeding in imported
   `review-revise-loop` specialization so review reports may remain under
   `artifacts/review` while findings JSON stays under `artifacts/work`.
9. Implement `review-revise-loop` as ordinary `.orc` code, including
   `.orc`-owned findings propagation over generic structured dataflow and any
   required thin compile-time specialization for caller-specific record types.
10. Implement or complete `.orc` input defaults.
11. Finalize `StateLayout` and `resume-or-start` reusable-state validation for
   phase outputs.
12. Define and enforce the machine-readable parity report schema.
13. Re-run the existing migrated workflow family and update parity reports.
14. Only then migrate additional key workflow families.

Independent work:

- Migration promotion checklist and parity report schema can proceed in
  parallel with compiler/runtime work.
- Certified legacy adapter inventory can proceed in parallel.

Blocked work:

- Deprecating YAML primaries is blocked until the relevant `.orc` parity report
  is non-regressive.

## Invariants And Failure Modes

Invariants:

- Structured bundles and typed artifacts are authority.
- Reports, debug YAML, stdout, pointer files, and source maps are views unless a
  specific contract says otherwise.
- Generated hidden inputs are compiler/runtime implementation details, not user
  workflow API.
- A successful command process does not imply a successful workflow step until
  output contracts validate.
- `REVISE` is not completion.
- Exhausted review loops are explicit non-completion, not failed hidden control
  flow.
- Resume/reuse cannot be based on file existence alone.
- Source maps must preserve authored-to-generated provenance for generated
  steps and paths.

Failure modes:

- Missing command bundle after exit `0`: output contract failure.
- Invalid bundle JSON: output contract failure.
- Missing required artifact target: output contract failure.
- Review provider returns invalid decision: provider output contract failure.
- Review loop exhausts: typed `EXHAUSTED` result.
- Reusable state is stale or incomplete: typed non-reusable result or fresh
  branch, according to `resume-or-start` contract.
- Default input violates path/type contract: compile or validation failure.

## Security, Operations, And Performance

Security:

- Bundle paths and generated state paths must remain workspace-relative.
- Runtime must reject absolute paths and `..` escapes before command launch or
  output validation.
- Certified adapters carrying workflow semantics must declare effects.

Operations:

- Promoted `.orc` workflows should be easier to resume and inspect because
  loop, phase, and review state are typed and source-mapped.
- Operators should not have to pass `__write_root__...` hidden inputs for
  normal runs.

Performance:

- Review/revise parity may add generated materialization and projection steps,
  but this cost is negligible next to provider execution.
- Runtime validation cost is bounded by existing JSON bundle and artifact
  validation behavior.

## Evidence And Implementation Boundaries

Implementation evidence must exercise the default path, not a fixture-only
shortcut.

For `command-result`:

- a real command process must receive `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- the command must write the bundle;
- runtime must validate the file and expose typed artifacts;
- tests must fail if stdout JSON is present but the bundle file is missing.

For `review-revise-loop`:

- tests must prove the loop is defined in `.orc` and reaches runtime
  through generic library composition, not a compiler-special lowering branch;
- tests must drive `REVISE -> fix/revise -> APPROVE`;
- tests must drive exhaustion;
- final outputs must come from the loop frame or terminal projection, not the
  first review step;
- findings must be consumed by revise/fix in structured form.

For `resume-or-start`:

- tests must cover reusable approved state, stale state, missing artifact state,
  failed state, and schema mismatch.
- tests must cover wrapper-level approved-only reuse through an authored
  union-returning reusable surface rather than record-only direct reuse.

For reusable wrapper construction and entrypoint context bootstrap:

- tests must prove an authored `.orc` wrapper can return a union-shaped reusable
  result suitable for `resume-or-start :valid-when (APPROVED)` without relying
  on compiler-family special cases; and
- tests must prove a promoted entry workflow can derive internal `RunCtx` /
  `PhaseCtx` values without exposing `phase-ctx__*`, `run-id`, `state-root`,
  or `artifact-root` as public required inputs.
- tests must also prove the promoted entry can satisfy the first reusable
  internal call without explicit/defaulted authored `phase-ctx` fallback
  wiring, so the executable proof does not stop at
  `[workflow_signature_mismatch] call is missing required binding \`phase-ctx\``.
- compile-only inspection or dry-run success attributable to synthetic
  top-level `PhaseCtx` defaults is insufficient; the proof must exercise the
  actual promoted-entry wrapper path that calls reusable union-returning
  `resume-or-start`.

For migration promotion:

- the promotion command computes `non_regressive`; authors do not set it by
  hand.
- parity reports must contain the computed `non_regressive` value and the
  evidence used to derive it.

Minimum parity-report shape:

```json
{
  "workflow_family": "design_plan_impl_stack",
  "candidate": "workflows/example.orc",
  "yaml_primary": "workflows/example.yaml",
  "compiler_version": "",
  "dsl_version": "2.14",
  "evidence": {
    "compile": {"status": "pass", "artifacts": []},
    "shared_validation": {"status": "pass"},
    "dry_run": {"status": "pass"},
    "smoke_or_integration": {
      "required": true,
      "passed": true,
      "waived": false,
      "waiver_reason": null,
      "owner": null,
      "expires": null
    },
    "baseline_characterization": {
      "inputs": "",
      "outputs": "",
      "terminal_states": "",
      "artifacts": "",
      "resume_behavior": ""
    },
    "output_contract_parity": "pass",
    "terminal_state_parity": "pass",
    "artifact_parity": "pass",
    "resume_parity": "pass"
  },
  "deprecated_yaml_mechanics": [
    {"mechanic": "pointer-file gate", "replacement": "typed state"}
  ],
  "non_regressive": false
}
```

`non_regressive` is computed as true only when:

- `compile.status`, `shared_validation.status`, and `dry_run.status` are
  `"pass"`;
- smoke or targeted integration evidence passed, or the waiver is present,
  owned, unexpired, justified, and accompanied by targeted evidence for the
  skipped runtime behavior;
- baseline characterization records inputs, outputs, terminal states, artifacts,
  and resume behavior;
- output contract parity, terminal state parity, artifact parity, and resume
  parity are all `"pass"`;
- every deprecated YAML mechanic has either a concrete replacement or an
  accepted-risk waiver owned by the promotion policy;
- optional compiler artifacts recorded as `not_implemented` are not required by
  that workflow family's promotion policy.

Any missing required field, expired waiver, manually asserted
`non_regressive=true`, or required artifact recorded as `not_implemented`
forces `non_regressive=false`.

## Compatibility And Migration

Existing YAML workflows remain valid and primary.

Migration is additive:

1. Add or update `.orc` replacement.
2. Compile and validate.
3. Run dry-run and required smoke/integration, or record an explicit waiver with
   targeted integration evidence.
4. Generate parity report.
5. Let the promotion command compute `non_regressive` from required evidence.
6. Update docs/catalog to identify `.orc` as primary.
7. Keep YAML as compatibility or fixture until an explicit deprecation decision.

Deprecated behavior:

- inline report parsing for decisions or findings;
- pointer-file existence gates;
- user-authored hidden bundle paths;
- prompts that manage workflow loops;
- treating dry-run success as replacement parity.

## Verification Strategy

Unit tests:

- `command-result` lowering emits authoritative bundle contracts, discriminant
  handling for unions, source maps, and no public hidden input requirement for
  promoted entrypoints.
- input defaults parse, type-check, lower, and reject invalid defaults.
- review-result and findings records validate through generic
  structured type checks and reject malformed findings.

Runtime integration tests:

- command structured output path is injected and validated.
- missing bundle after command success fails visibly.
- invalid bundle after command success fails visibly.
- repeat-until resume still works for `.orc`-defined review loops.

Workflow Lisp integration tests:

- `std/phase.orc` `review-revise-loop` imports and compiles through generic
  effectful composition, whether exposed as a procedure/workflow or as a thin
  macro that lowers to the same generic forms.
- imported `review-revise-loop` still compiles when review-loop-specific
  expression, typecheck, and lowering paths are absent or disabled for the
  fixture.
- regression guards reject or flag review-loop-specific compiler artifacts as
  the semantic route, including `ReviewReviseLoopExpr`,
  `_elaborate_review_revise_loop`, `__review-revise-loop__`,
  `_lower_review_revise_loop`, `_validate_review_loop_result_contract`, or
  typechecker and lowerer branches keyed directly to `review-revise-loop`.
- expansion fixtures prove at least one non-review-loop `.orc` form uses the
  same generic expansion representation and source-map path.
- generic source-map fixtures prove generated nodes identify the authored call
  site, imported `.orc` definition, macro expansion if any, allocator identity,
  and generated node provenance.
- imported `review-revise-loop` does not require procedure type
  parameters or runtime-carried type erasure to accept caller-specific
  `completed` and `inputs` record shapes.
- caller-owned review/fix procedures pass through `ProcRef` specialization and
  no runtime `ProcRef`, provider ref, or prompt ref value appears in executable
  state.
- `std/phase.orc` `review-revise-loop` approves first pass.
- `std/phase.orc` `review-revise-loop` revises once then approves.
- `std/phase.orc` `review-revise-loop` exhausts and returns `EXHAUSTED`.
- exhaustion projection fails as an ordinary contract failure if the final
  completed iteration did not materialize required review outputs.
- review provider output cannot replace carried evidence identities such as
  `checks_report`; terminal projection copies those identities from loop
  state/inputs.
- revise/fix receives findings from the previous review.
- `resume-or-start` reuses approved state and rejects stale/failed state.

Migration tests:

- existing key migration tests continue to compile and dry-run.
- promoted stack workflow has a real smoke or targeted integration run.
- parity report generation rejects `non_regressive=true` when any required
  evidence is missing.
- parity report records optional IR artifacts as `not_implemented` rather than
  silently omitting them.

## Declarative Acceptance Scenarios

### Command Result Bundle Authority

Initial state: a `.orc` workflow calls a certified command adapter returning a
typed record. The command writes JSON only to the path from
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

Entrypoint: `python -m orchestrator run workflow.orc --entry-workflow ...`

Expected result: the run completes, `state.json` exposes typed artifacts from
the bundle, and no caller-provided hidden write-root input is required.

Forbidden behavior: the run must not pass by parsing stdout if the bundle file
is absent.

### Review Revise Loop

Initial state: fake providers return `REVISE` with findings, then the fix
provider writes an updated artifact, then review returns `APPROVE`.

Entrypoint: a `.orc` phase importing `review-revise-loop` from `std/phase.orc`.

Expected result: the fix step runs exactly once, receives structured findings,
the loop exits approved, and the final phase output reflects the approved
iteration.

Forbidden behavior: the workflow must not record completion after the first
`REVISE`.

### Reusable State

Initial state: a prior phase state says `APPROVED` and references existing
artifacts.

Entrypoint: a `.orc` workflow using `resume-or-start`.

Expected result: reusable state validates and normalizes to the same return type
as a fresh phase execution.

Negative case: if the referenced artifact is missing, reuse is rejected and the
workflow follows the documented fresh or non-reusable branch.

### Migration Promotion

Initial state: a YAML primary and `.orc` candidate both exist.

Entrypoint: migration parity command or workflow.

Expected result: the promotion command computes `non_regressive=true` only when
compile, shared-validation, dry-run, required smoke/integration or explicit
waiver, and behavioral parity checks all pass.

Forbidden behavior: a candidate that only parses or dry-runs must remain
non-primary.

## Success Criteria

- Runtime command structured-output behavior is documented and tested.
- Required command bundle-path, output failure, and path-safety spec deltas are
  accepted in the relevant normative surfaces.
- `command-result` no longer requires users to pass compiler-owned hidden
  bundle inputs for promoted workflows.
- Generic effectful library composition supports provider calls, command calls,
  typed loops, matches, generated result paths, and compile-time
  provider/prompt/workflow/procedure refs without runtime-transported procedure
  values, reusing the existing `defproc`, `WorkflowRef`, `ProcRef`, `bind-proc`,
  `let-proc`, and `loop/recur` substrate where it already satisfies the
  contract.
- Authored or generically specialized reusable-result wrappers can expose
  approved-only union returns for `resume-or-start` without relying on
  compiler-generated-only union construction.
- Promoted entry workflows can bootstrap internal `RunCtx` / `PhaseCtx` values
  through runtime-owned hidden bindings rather than public run-id/root inputs,
  fake literals, or explicit/defaulted authored `PhaseCtx` fallback parameters,
  and the first reusable internal call succeeds through that same hidden
  binding route.
- `review-revise-loop` is implemented as ordinary `.orc` code, using an
  imported procedure/workflow and/or a thin macro specialization layer
  rather than a compiler-special branch, and is accepted as the canonical
  high-level replacement for YAML review/fix `repeat_until` loops.
- A follow-on parametric `.orc` specialization design may later replace the
  thin macro specialization bridge, but it is not required for this migration
  tranche.
- Review findings are validated structured state and can be consumed by
  revise/fix steps.
- Workflow Lisp input defaults lower to existing DSL input defaults.
- `resume-or-start` has a reusable-state validation contract with negative
  tests.
- Parity reports are machine-validatable and compute `non_regressive` from
  required evidence.
- The existing design/plan/impl `.orc` migration can be rerun with
  non-regressive parity, or the report explicitly names any remaining blocker.

## Stop / Revise Criteria

Revise this design if:

- implementation requires a new YAML DSL primitive rather than lowering onto
  existing v2.14 surfaces;
- implementation requires a compiler-special `review-revise-loop` path rather
  than generic `.orc` composition;
- runtime command bundle injection cannot be made reliable without exposing
  hidden inputs as public API;
- command-produced union results require implicit `variant_output` paths instead
  of an explicit generated bundle contract;
- family migration still requires fake literal run ids or new public
  run-id/state-root/artifact-root inputs, or still depends on explicit or
  defaulted authored `PhaseCtx` fallback wiring, because entrypoint context
  bootstrap is not generically specified or the hidden reusable-call binding
  half of the prerequisite is still missing;
- approved-only reusable wrappers still depend on compiler-generated-only union
  constructors with no authored or generically specialized surface;
- the review findings schema requires unsupported collection types that would
  broaden the type-system work beyond this migration tranche;
- `repeat_until` cannot express the required review/fix behavior without
  weakening resume semantics;
- parity evidence cannot distinguish real runtime behavior from fixture-only
  helper behavior.
