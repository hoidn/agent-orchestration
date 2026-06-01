# Workflow Lisp Key Migration Parity Architecture

Status: draft
Kind: architecture decision / migration design
Created: 2026-06-01
Last material update: 2026-06-01
Related docs:

- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Implementation target: staged changes to the Workflow Lisp frontend, stdlib
lowering, shared validation, and runtime command/output handling needed before
promoting key `.orc` workflow replacements over YAML primaries.

## Summary

The first key-workflow migration pass proved that Workflow Lisp can compile and
dry-run meaningful `.orc` replacements, but it did not establish primary
workflow parity. The remaining gaps are not mostly syntax gaps. They are
contract gaps between high-level Lisp forms, generated Core DSL, runtime output
materialization, repeat/revise state, and migration evidence.

This design chooses a compiler/stdlib-first migration architecture. The YAML
DSL already has most required runtime primitives: `output_bundle`,
`variant_output`, `repeat_until`, `on_exhausted`, workflow input defaults,
structured refs, call frames, and runtime state. The main work is to finalize
how Workflow Lisp lowers high-level forms onto those primitives, clarify the
few runtime behaviors that are currently implementation details, and add a
promotion checklist that prevents `.orc` workflows from replacing YAML while
still regressive.

No runtime closures or first-class runtime functions are required for this
migration tranche.

## Context And Authority

Normative DSL behavior lives in `specs/`. Existing relevant contracts include:

- `specs/dsl.md`: workflow inputs/defaults, `output_bundle`, `variant_output`,
  `repeat_until`, `on_exhausted`, structured `match`, and `materialize_artifacts`.
- `specs/state.md`: authoritative `state.json`, call frames, `repeat_until`
  bookkeeping, artifact lineage, and resume state.
- `specs/io.md`: step output capture and output contract validation.

Workflow Lisp design authority is split across:

- `docs/design/workflow_lisp_stdlib_lowering.md`, which defines the standard
  library lowering contract template;
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
- `review-revise-loop` exists as a high-level authoring concept, but its
  implementation contract is still too narrow and not yet accepted as the
  canonical replacement for YAML `repeat_until` review/fix loops.
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
- Support carried review findings without markdown report parsing as semantic
  authority.
- Require compile, shared validation, dry-run, real smoke where safe, and
  parity evidence before YAML deprecation.

## Non-Goals

- Do not add runtime closures or first-class runtime procedure values.
- Do not recreate YAML pointer choreography in high-level `.orc`.
- Do not make generated/debug YAML semantic authority.
- Do not promote the low-level cycle-guard demo itself as a high-level key
  workflow replacement unless native bounded-loop parity is intentionally
  designed later.
- Do not preserve inline shell/Python findings extraction as a permanent
  semantic path.
- Do not introduce a new DSL version solely to rename existing v2.14 surfaces.

## Decision

Use a compiler/stdlib-first architecture with narrow runtime contract
clarifications.

The recommended approach is:

1. Treat existing YAML DSL primitives as the executable substrate.
2. Finalize Workflow Lisp lowering contracts for `command-result`,
   `review-revise-loop`, `resume-or-start`, state layout, and workflow input
   defaults.
3. Clarify runtime command structured-output behavior as a contract:
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the command's authoritative bundle
   target when a command step has `output_bundle` or `variant_output`.
4. Introduce typed review-result and finding records in Workflow Lisp standard
   library guidance.
5. Add a migration promotion gate that keeps YAML primary until parity evidence
   is non-regressive.

Alternatives considered:

- **DSL-first new primitives.** Add new YAML DSL constructs for review loops,
  findings, phase state, and command results. This would make the substrate
  larger even though v2.7-v2.14 already have the needed execution primitives.
  Reject for this tranche.
- **Legacy adapter migration.** Wrap missing behavior in certified adapters and
  preserve YAML-era pointer/report conventions. Useful as a temporary bridge,
  but insufficient as the primary architecture.
- **Compiler/stdlib-first lowering.** Keep high-level `.orc` expressive, lower
  into existing validated runtime forms, and add only targeted runtime/spec
  clarifications. This is the selected approach.

## Required Changes By Gap

| Gap | Required extension | Primary owner | DSL/spec impact |
| --- | --- | --- | --- |
| Command-result structured return materialization | Final `command-result` lowering contract and runtime bundle-path contract | Workflow Lisp lowering + runtime executor | Clarify existing `output_bundle` command behavior; no new DSL construct |
| Review/revise loop parity | Accepted `review-revise-loop` lowering to `repeat_until`/`match`/provider steps | Workflow Lisp stdlib lowering | No new DSL construct if v2.7/v2.12 semantics suffice |
| Carried findings/review state | Typed review result and findings schema plus propagation rules | Workflow Lisp stdlib/type catalog | No new DSL construct; may use `output_bundle` or `variant_output` |
| Resume/state semantics | State layout and `resume-or-start` reusable-state validation contract | Workflow Lisp state layout + runtime/adapters | Likely no schema bump; clarify accepted reusable state shape |
| Default input parity | `.orc` boundary syntax and lowering for workflow input defaults | Workflow Lisp parser/typecheck/lowering | Existing DSL input default support |
| Real smoke coverage | Migration promotion checklist and parity report schema | Migration policy/tests | No DSL change |

## Architecture

The architecture has four layers.

```text
.orc authoring
  -> Workflow Lisp parser/typecheck/stdlib contracts
  -> Core Workflow AST / Semantic IR / Executable IR
  -> existing DSL runtime primitives
  -> migration parity evidence
```

### 1. Workflow Lisp Authoring Layer

The authoring layer exposes high-level forms:

- `command-result`
- `provider-result`
- `run-provider-phase`
- `review-revise-loop`
- `resume-or-start`
- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`

Authors should express typed workflow behavior. They should not write hidden
bundle paths, pointer files, markdown extraction, or loop routing glue.

New or completed authoring syntax:

```lisp
(defrecord ReviewFinding
  (id String)
  (severity FindingSeverity)
  (summary String)
  (evidence String))

(defrecord ReviewFindings
  (items Json)) ; initial portable representation; stricter list types can follow

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

Workflow input defaults should be expressible at the boundary:

```lisp
(defworkflow design-plan-impl-review-stack
  ((brief_path BriefPath :default "workflows/examples/inputs/design_brief.md")
   (design_target_path DesignDocTarget :default "docs/plans/example-design.md"))
  -> StackOutput
  ...)
```

The exact syntax can change during implementation, but the contract is fixed:
defaults belong to the workflow boundary, obey the same path/type validation as
explicit inputs, and are overridden by CLI/caller-provided inputs.

### 2. Compiler And Lowering Layer

The compiler owns all generated paths and hidden wiring. Generated write-root
inputs are not public workflow API.

`command-result` lowering must:

- derive `output_bundle` or `variant_output` from the declared return type;
- generate a deterministic result-bundle path;
- record source-map origins for the high-level form, generated step, and
  generated path;
- ensure the command receives the resolved bundle path through the runtime
  command environment;
- expose only validated bundle fields as typed refs;
- reject command boundaries without certified command metadata when the command
  carries workflow semantics.

`review-revise-loop` lowering must:

- lower to a generated `repeat_until` frame;
- emit a review provider step with a structured result contract;
- route `APPROVE`, `REVISE`, and terminal non-completion outcomes through
  structured `match`;
- invoke revise/fix only on `REVISE`;
- carry typed findings into revise/fix inputs;
- produce a typed terminal union rather than a loose decision scalar;
- use `on_exhausted` only to produce an explicit exhausted result;
- source-map generated review, route, fix, and final projection steps back to
  the high-level form.

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

### 3. Runtime Layer

The runtime should not learn Lisp-specific behavior. It should execute the
generated Core DSL and enforce contracts.

Runtime clarifications required:

- For command steps with `output_bundle` or `variant_output`, the runtime
  resolves the bundle path before command launch and exposes it as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
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

These are clarifications of existing runtime surfaces, not a new Lisp runtime.

### 4. Migration Evidence Layer

A `.orc` replacement can become primary only when a parity report says it is
non-regressive.

Required evidence per promoted workflow family:

- compile emits Core AST, Semantic IR, Executable IR when available, source map,
  and debug projection;
- shared validation passes;
- dry-run passes;
- at least one real smoke or targeted integration run passes when safe;
- YAML baseline behavior is characterized;
- `.orc` output contracts, terminal states, artifacts, and resume behavior match
  the intended YAML primary behavior;
- deprecated YAML-era mechanics are explicitly listed and justified.

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

- For command steps generated from `.orc command-result`, the resolved bundle
  path is provided to the process as `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- The command must write the structured bundle to that path.
- The runtime validates the bundle before exposing typed artifacts.
- The compiler must not require callers to pass compiler-owned hidden bundle
  inputs for promoted entrypoints.

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

- `review-revise-loop` is the standard high-level form for bounded review/fix
  loops.
- Its result is a typed union.
- `REVISE` deterministically invokes revise/fix and repeats.
- Exhaustion is explicit non-completion.
- Reports are views; typed review results and findings are authority.

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
- Defaults are type-checked and path-checked at compile/validation time where
  possible.

## Dependencies And Sequencing

Recommended sequencing:

1. Document and test the command structured-output runtime contract.
2. Finalize `command-result` lowering so hidden bundle paths are compiler-owned
   and not public entrypoint inputs.
3. Promote `review-revise-loop` from draft to accepted lowering contract,
   including typed findings propagation.
4. Implement or complete `.orc` input defaults.
5. Finalize `StateLayout` and `resume-or-start` reusable-state validation for
   phase outputs.
6. Re-run the existing migrated workflow family and update parity reports.
7. Only then migrate additional key workflow families.

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

- tests must drive `REVISE -> fix/revise -> APPROVE`;
- tests must drive exhaustion;
- final outputs must come from the loop frame or terminal projection, not the
  first review step;
- findings must be consumed by revise/fix in structured form.

For `resume-or-start`:

- tests must cover reusable approved state, stale state, missing artifact state,
  failed state, and schema mismatch.

For migration promotion:

- parity reports must record `non_regressive=true` only after compile,
  validation, dry-run, and safe smoke/integration evidence all pass.

## Compatibility And Migration

Existing YAML workflows remain valid and primary.

Migration is additive:

1. Add or update `.orc` replacement.
2. Compile and validate.
3. Run dry-run and safe smoke.
4. Generate parity report.
5. Mark non-regressive only if behavior matches the intended primary contract.
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

- `command-result` lowering emits `output_bundle`/`variant_output`, source maps,
  and no public hidden input requirement for promoted entrypoints.
- input defaults parse, type-check, lower, and reject invalid defaults.
- typed findings records validate and reject malformed findings.

Runtime integration tests:

- command structured output path is injected and validated.
- missing bundle after command success fails visibly.
- invalid bundle after command success fails visibly.
- repeat-until resume still works for generated review loops.

Workflow Lisp integration tests:

- `review-revise-loop` approves first pass.
- `review-revise-loop` revises once then approves.
- `review-revise-loop` exhausts and returns `EXHAUSTED`.
- revise/fix receives findings from the previous review.
- `resume-or-start` reuses approved state and rejects stale/failed state.

Migration tests:

- existing key migration tests continue to compile and dry-run.
- promoted stack workflow has a real smoke or targeted integration run.
- parity report generation rejects `non_regressive=true` when any required
  evidence is missing.

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

Entrypoint: a `.orc` phase using `review-revise-loop`.

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

Expected result: `non_regressive=true` is emitted only when compile,
shared-validation, dry-run, safe smoke/integration, and behavioral parity checks
all pass.

Forbidden behavior: a candidate that only parses or dry-runs must remain
non-primary.

## Success Criteria

- Runtime command structured-output behavior is documented and tested.
- `command-result` no longer requires users to pass compiler-owned hidden
  bundle inputs for promoted workflows.
- `review-revise-loop` is accepted as the canonical high-level replacement for
  YAML review/fix `repeat_until` loops.
- Review findings are typed state and can be consumed by revise/fix steps.
- Workflow Lisp input defaults lower to existing DSL input defaults.
- `resume-or-start` has a reusable-state validation contract with negative
  tests.
- The existing design/plan/impl `.orc` migration can be rerun with
  non-regressive parity, or the report explicitly names any remaining blocker.

## Stop / Revise Criteria

Revise this design if:

- implementation requires a new DSL primitive rather than lowering onto
  existing v2.14 surfaces;
- runtime command bundle injection cannot be made reliable without exposing
  hidden inputs as public API;
- typed findings require unsupported collection types that would broaden the
  type-system work beyond this migration tranche;
- `repeat_until` cannot express the required review/fix behavior without
  weakening resume semantics;
- parity evidence cannot distinguish real runtime behavior from fixture-only
  helper behavior.
