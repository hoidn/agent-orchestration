# Shared EMPTY Run-State Retirement And Reference-Family Evidence Alignment Architecture

Status: retired/superseded implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-shared-empty-run-state-retirement-and-reference-family-evidence-alignment`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

Retirement note: superseded by `workflow-lisp-design-delta-compatibility-carrier-retirement`
and commit `e4d9aae25669839e37be485271a14285adbd6b22`, which retired the shared
run-state carrier admission and added custom-union rejection coverage.

## Scope

This slice retires the remaining shared `EMPTY.run-state` compatibility-carrier
contract and aligns Design Delta reference-family evidence with that
carrier-free route.

The bounded target is:

- `std/drain::SelectionResult.EMPTY` is a terminal selection condition with no
  `run-state` / `run_state_path` payload;
- `validate_selector_workflow_ref` and adjacent workflow-ref validation accept
  the carrier-free shared `EMPTY` variant while preserving fixed selector
  arity and typed `GAP`, `SELECTED`, and `BLOCKED` payload checks;
- imported `std/drain::backlog-drain` returns carrier-free `DrainResult`
  values from loop-owned typed state and terminal projection, not from a
  selector-carried relpath;
- Design Delta build, boundary, resume-retirement, default-resume, and
  feasibility evidence stop depending on live `run_state` bridge rows or stale
  imported-finalizer owner-route assertions; and
- runtime-native drain/resource transition evidence remains visible as typed
  effects and audit state, not as a reason to keep a run-state path carrier.

This architecture does not redesign `backlog-drain`, provider request records,
gap re-entry convergence, work-item summary ownership, public publication,
YAML-primary promotion, or the broader adapter-retirement program.

## Current Checkout Baseline

The current checkout already removed `run_state_path` from the Design Delta
high-level source route:

- `DesignDeltaDrainCtx`, selector payloads, gap payloads, selected-item
  payloads, and terminal summary values are carrier-free;
- selected-item stdlib routes keep `run_state_path` out of public inputs and
  child-call payloads;
- parent drain smoke checks assert `return__run-state` and
  `return__drain-summary__run_state_path` are absent; and
- runtime-native drain progress is represented by state-layout backed resource
  state and transition audit files.

The remaining shared carrier pressure is narrower:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` still declares
  `(EMPTY (run-state StateExisting))` on the shared `SelectionResult`;
- `orchestrator/workflow_lisp/typecheck_calls.py` still requires
  `EMPTY.run-state` for the exact shared `SelectionResult` route;
- `tests/test_workflow_lisp_drain_stdlib.py` still includes positive and
  negative fixtures built around shared `EMPTY.run-state`;
- Design Delta artifact/evidence lanes still contain stale names and checks
  that can treat `run_state` bridge rows, imported-finalizer owner-route
  claims, or retired drain-run-state compatibility rows as live prerequisites;
  and
- command-boundary or resume-retirement manifests may still mention old bridge
  rows that are valid only as retired/historical evidence.

The architecture therefore narrows the shared stdlib contract and updates
reference-family evidence to report the carrier-free route rather than proving
the old bridge is still present.

## Ownership

`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` owns the shared
`SelectionResult`, `DrainResult`, `DrainLoopState`, `DrainLoopTerminal`,
terminal projection helpers, `consume-drain-terminal-effects`, and
`backlog-drain` authoring contract.

`orchestrator/workflow_lisp/typecheck_calls.py` owns workflow-ref signature
admission for `selector`, `run-item`, and `gap-drafter`. Its selector rule must
validate the shared union shape structurally without forcing a carrier field
that the shared stdlib no longer owns.

The WCC/lowering/shared-validation/source-map layers own proof, loop-frame
carriage, child-call value return, generated paths, Semantic IR, executable
contracts, and diagnostics. Any repair needed for the carrier-free route must
be generic to Workflow Lisp and imported stdlib composition, not a branch keyed
to the Design Delta family.

The Design Delta family owns its records, projections, provider requests,
transitions, boundary authority registry, resume-retirement manifest, and
reference-family evidence under `workflows/library/lisp_frontend_design_delta/`
and `workflows/examples/inputs/workflow_lisp_migrations/`.

The runtime and transition executor own runtime-native `drain-run-state`
resource state and audit files. A runtime-native resource state path is not a
Workflow Lisp `run_state_path` compatibility carrier.

`docs/design/workflow_command_adapter_contract.md` owns any touched script,
command-boundary row, certified adapter, legacy adapter, or runtime-native
promotion decision. This slice must not replace carrier retirement with hidden
inline Python/shell, stdout JSON, report parsing, pointer files, ad hoc JSON
rewrites, or uncertified state mutation.

## Source Surfaces

Primary source surfaces for this slice are:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/resume_plumbing_retirement.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `workflows/library/lisp_frontend_design_delta/*.orc`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`

Conditional shared surfaces are in scope only if carrier-free `EMPTY` exposes a
generic defect in imported stdlib composition, loop terminal projection,
workflow-call value return, source-map lineage, or Semantic IR/executable
contract projection.

If a file outside this list uses `std/drain::SelectionResult.EMPTY` or a
`run_state_path` bridge, it follows the same rule: `EMPTY` carries no run-state
payload, and `run_state_path` is either removed from ordinary internal
composition or isolated as an explicit public/legacy compatibility bridge with
owner, consumer, schema, authority class, and retirement condition.

## Contract

The shared selector result contract is:

```lisp
(defunion SelectionResult
  (EMPTY)
  (GAP
    (gap GapPayload))
  (SELECTED
    (selection SelectionPayload))
  (BLOCKED
    (reason String)))
```

`EMPTY` means no selectable work is available. It is not a transport lane for
run state, checkpoint identity, write roots, pointer files, rendered summaries,
or compatibility bundles.

Selector validation must still require:

- one `DrainCtx` parameter for the selector workflow ref;
- a union return type with `EMPTY`, `GAP`, `SELECTED`, and `BLOCKED` variants;
- `GAP.gap` as a record payload;
- `SELECTED.selection` as a record payload; and
- `BLOCKED.reason` as `String`.

It must not require `EMPTY.run-state`, exact `EMPTY` field names containing
only `run-state`, or any substitute relpath carrier.

Imported `backlog-drain` value return remains typed Workflow Lisp dataflow.
Terminal effects are separate consumers:

- `finalize-drain-terminal` or equivalent typed projection constructs
  `DrainResult`;
- `consume-drain-terminal-effects` may explicitly run resource transition and
  materialized-view consumers;
- publication policy may render public summaries from returned typed values;
- Design Delta transition helpers may record family resource state; and
- legacy compatibility bridges may render views only when declared with owner,
  consumer, schema, authority class, and retirement metadata.

No terminal effect, report, pointer, summary, resource audit row, or
compatibility bundle is semantic transport for `SelectionResult.EMPTY` or
`DrainResult` value return.

## Reference-Family Evidence Alignment

Design Delta evidence must describe the carrier-free route directly.

Allowed evidence claims:

- `work_item.loop.run_state_path`, `drain.loop.run_state_path`, and
  `drain.output.return_run_state` are absent from promoted-route public
  boundary, loop-state, call-signature, and output evidence;
- `transitions.resource.drain_run_state` may appear as runtime-native resource
  transition evidence or as retired historical compatibility evidence, but not
  as a live `run_state_path` bridge row;
- `materialize_lisp_frontend_work_item_inputs` may remain only as retired or
  quarantined certified-adapter metadata when it is unreferenced by the
  promoted route;
- boundary-authority reports classify generated private context and bridge
  values by their actual current role, not by stale "owner route" or
  "imported finalizer" assumptions;
- default-resume and resume-retirement reports distinguish runtime-owned
  checkpoint/resource state from authored compatibility-carrier state; and
- smoke/build artifacts prove carrier-free stdlib and Design Delta value
  return without requiring summary materialization or drain-outcome recording
  as transport.

Forbidden evidence claims:

- a live `run_state_path` bridge is required for imported
  `finalize-selected-item`, imported `backlog-drain`, or selected-item stdlib
  routes;
- a runtime-native `drain-run-state` audit row justifies keeping
  `EMPTY.run-state`;
- a command-boundary manifest row with retired status counts as live workflow
  semantics;
- a materialized summary or report proves typed terminal state by being read
  back as authority; or
- a family-local wrapper, caller-name allowlist, or stale owner-route label is
  used to satisfy shared stdlib validation.

## Allowed Shapes

Allowed implementation shapes include:

- removing `run-state` from shared `std/drain::SelectionResult.EMPTY`;
- replacing selector validation's `EMPTY.run-state` check with a
  carrier-free structural check for the shared selector union;
- changing shared fixtures so positive `EMPTY` payloads are `{ "variant":
  "EMPTY" }`;
- preserving negative coverage that rejects undeclared `EMPTY` payload fields,
  public `run_state_path` inputs, loop-state carriers, call-signature carriers,
  pointer authority, and materialized-view-as-state;
- updating evidence serializers, manifests, and tests to report retired or
  absent carrier rows instead of "kept compatibility";
- retaining runtime-native resource transitions as typed effects with source
  maps, Semantic IR, executable contracts, and transition audit evidence; and
- repairing generic source-map or shared-validation behavior if the
  carrier-free route exposes a real shared WCC/schema-2 defect.

## Forbidden Shapes

This slice must not:

- rename `run-state` or `run_state_path` to another relpath carrier;
- add a one-field surrogate to `EMPTY`, `DrainResult.EMPTY`, `DrainSummaryValue`,
  `SelectionPayload`, `GapPayload`, `SelectedItemResult`, or hidden context
  records;
- widen selector, `run-item`, `gap-drafter`, `backlog-drain`, or
  `finalize-selected-item` call signatures;
- add wrapper workflows whose only purpose is to preserve or reconstruct
  run-state carrier data;
- classify a removed carrier as `runtime_derived` to satisfy evidence gates;
- reread reports, summaries, pointer files, command stdout, debug YAML, or
  compatibility bundles as state authority;
- weaken provider/command structured-output validation;
- introduce inline command glue for routing, state rewrite, or evidence
  normalization; or
- claim YAML-primary promotion from compile, validation, or smoke success.

## Command Adapter And Runtime-Native Policy

No new command adapter should be introduced for shared `EMPTY` handling or
reference-family evidence alignment. The correct replacement is typed Workflow
Lisp dataflow plus runtime-native resource transitions where durable mutation
is actually required.

Any retained command-boundary row touched by this slice must satisfy the
certified adapter contract:

- stable command path;
- typed input and output signatures;
- declared effects and artifact contracts;
- state writes and path-safety expectations;
- fixture and negative-fixture coverage;
- source-map behavior;
- owner module; and
- explicit retirement status or replacement path when temporary.

Runtime-native transition evidence must stay typed and effect-visible. It may
record drain/resource state, but it must not be treated as a compatibility
carrier for `SelectionResult.EMPTY`.

## Acceptance Conditions

The slice is acceptable when:

- shared `std/drain::SelectionResult.EMPTY` has no `run-state` field;
- selector workflow-ref validation accepts the shared carrier-free `EMPTY`
  variant and rejects stale or undeclared carrier fields;
- imported `std/drain::backlog-drain` compile/shared-validation fixtures still
  cover empty, completed, blocked, exhausted, selected-item, and gap routes;
- Design Delta parent drain compiles through WCC/schema 2 with public inputs
  free of `RunCtx`, generated roots, checkpoint paths, and `run_state_path`;
- Design Delta smoke/build outputs keep `return__run-state`,
  `return__drain-summary__run_state_path`, public `run_state_path`, loop-state
  `run_state_path`, and call-signature `run_state_path` absent;
- boundary-authority, resume-retirement, default-resume, value-flow census,
  and migration-parity evidence no longer assert live `run_state` bridge rows
  or stale imported-finalizer owner-route prerequisites;
- `transitions.resource.drain_run_state` is represented only as runtime-native
  transition evidence or retired historical compatibility evidence;
- `materialize_lisp_frontend_work_item_inputs` is unreferenced by the promoted
  route or explicitly quarantined with certified-adapter retirement metadata;
- negative evidence rejects public, private, bridge, runtime-derived,
  pointer-authority, report-authority, and materialized-view attempts to
  reintroduce the carrier; and
- all changes remain generic to the shared owner lane where they touch shared
  compiler, stdlib, validation, source-map, or runtime surfaces.

## Out Of Scope

This architecture does not cover:

- introducing new provider request-record surfaces;
- changing prompt rendering modes;
- changing gap payload record-leaf carriage;
- changing family gap re-entry convergence semantics;
- changing work-item summary ownership;
- deleting all historical run-state files or YAML-era fixtures;
- replacing every remaining certified adapter in the Design Delta migration
  inputs; or
- promoting the `.orc` candidate to YAML primary.
