# Design Delta Compatibility-Carrier Retirement Implementation Architecture

Status: revised implementation architecture (R21 drain re-entry, 2026-07-06)
Design gap id: `workflow-lisp-design-delta-compatibility-carrier-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Revision Note (R21 drain re-entry, 2026-07-06)

The 2026-07-05 revision's frontier — transition-authoring census/manifest
realignment with the landed owner-boundary route — is landed and verified
fresh on this checkout: the Section-14 parent-drain compile entrypoint exits
0 (transition-authoring status pass), and
`tests/test_workflow_lisp_drain_stdlib.py` +
`tests/test_workflow_lisp_transition_authoring.py` +
`tests/test_workflow_lisp_resume_plumbing_retirement.py` are 94/94 green in
one fresh run. The selected-item finalization lane, the family structural
repairs, the owner-boundary terminal split, and the census realignment are
all done; none of that work is redone here.

This revision covers exactly the lanes both prior revisions explicitly
deferred: run-state compatibility-carrier retirement in the remaining
`std/drain` lanes and in the Design Delta family `transitions.orc`
bridge-backed `drain-run-state` resource. Target-design authority: Section
12.1 (transitional surface retirement — delete the bridge, isolate it at a
declared public/legacy boundary, or replace the caller with typed
composition), Section 13.4 (compatibility carriers out of ordinary public
and internal call signatures; transitional compatibility surfaces retired
from ordinary internal composition), and Section 15 (internal compatibility
carriers absent from ordinary stdlib child-call composition, or isolated at
declared public/legacy boundaries while a live consumer remains).

The verified carrier surfaces on this checkout are:

- **`std/drain` carrier fields and parameters**
  (`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`):
  `DrainResult.EMPTY.run-state` and `DrainResult.COMPLETED.run-state`
  (`StateExisting`); `run_state` on all four `DrainLoopTerminal` variants;
  `DrainLoopState.run-state`; the `run-state` parameters of
  `empty-drain-result-proc`, `blocked-drain-result-proc`, and
  `completed-drain-result-proc`; and the forwarding of those values through
  `finalize-drain-terminal`. Verified: no consumer reads any of these fields
  — `lisp_frontend_design_delta/projections.orc` matches
  `EMPTY`/`COMPLETED`/`BLOCKED` without touching `.run-state`, and a
  repo-wide search finds no other field read. The values are threaded and
  dropped.
- **Compiler-side run-state threading** that exists only to fill those
  fields: `orchestrator/workflow_lisp/lowering/phase_drain.py` seeds an
  `acc__run-state` loop accumulator from the literal
  `state/drain-run-state.json`, threads it through every selection route
  (EMPTY, BLOCKED, GAP-continue, SELECTED) of the lowered `backlog-drain`
  loop, and projects it into a `terminal__run-state` carrier artifact;
  `orchestrator/workflow_lisp/lowering/drain_terminal.py` emits the
  `return__run-state` output when the result contract carries it. This is
  the run-state lane the selector record describes for
  `SelectionResult.EMPTY`/`BLOCKED` and `GapResult.CONTINUE`: those unions
  are already carrier-free in source (deny-guards pinned by
  `test_workflow_ref_resolution_rejects_custom_union_run_state_carriers`),
  and the remaining flow through those routes is this lowering accumulator.
- **Family bridge lane**
  (`workflows/library/lisp_frontend_design_delta/transitions.orc`): the
  `drain-run-state` resource with `:backing (bridge run_state_path)`; the
  five transitions declared against it (`write-drain-status-runtime-native`,
  `write-drain-status`, `record-terminal-work-item`,
  `record-blocked-recovery-outcome`,
  `record-design-gap-progress-transition`); the `run_state_path
  RunStatePath`-typed wrapper workflows `emit-drain-status-transition-audit`
  and `apply-drain-status-transition`; and the wrapper procs
  `record-drain-terminal-outcome` (takes `RunStatePath`) and
  `record-work-item-terminal-outcome` (calls the bridge-backed
  `record-terminal-work-item`). Verified: the promoted family composition
  (`drain.orc`, `work_item.orc`, `stdlib_adapters.orc`) already uses only
  the state-layout-backed `-stdlib` lanes
  (`record-drain-terminal-outcome-stdlib`, `record-design-gap-progress` →
  `record-design-gap-progress-stdlib`,
  `record-work-item-blocked-recovery-summary` →
  `record-blocked-recovery-outcome-stdlib`). The bridge lane's only
  remaining `.orc` consumers are the runtime proof fixtures
  (`runtime_transition_fixture.orc`, `runtime_view_fixture.orc`, both via
  `emit-drain-status-transition-audit`).

Part of this frontier is already red on the checkout, and the red tests
encode the intended end state: both fixture workflows call
`emit-drain-status-transition-audit` with only `:summary_path` — the
carrier-free call shape — while the wrapper still requires its
`run_state_path` parameter. Verified fresh, the compile fails with exactly
`workflow_signature_mismatch: call is missing required binding
run_state_path` (`runtime_view_fixture.orc:28`,
`runtime_transition_fixture.orc:14`), which makes
`tests/test_workflow_lisp_view_dual_run.py` 3 failed / 1 passed and the
fixture-backed feasibility selection
(`-k "runtime_transition_fixture or runtime_view_fixture"`) 5 failed.
These are live contracts to satisfy by retiring the wrapper's carrier
parameter and bridge backing, not stale fixtures to revert.

The checked resume-plumbing retirement manifest
(`workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`)
already records this exact debt as its single decision row
(`transitions.resource.drain_run_state`, decision `BLOCKED`) with the
retirement condition "remove the bridge-backed drain-run-state resource or
move any live legacy JSON write to a separate declared boundary slice".
This slice discharges that condition. The runtime-derived replacement
already exists and is green: the state-layout-backed resources
(`std/drain::drain-run-state` with the `DrainOutcome*` record family and
runtime-native `record-drain-outcome`, and the family
`drain-run-state-native`) are the survivor lane, not retirement targets.

## Scope

This architecture closes exactly the selected Design Delta
compatibility-carrier gap on its final deferred frontier: retire the
run-state compatibility carriers from ordinary internal stdlib/family
composition, so that `StateExisting` run-state values, the
`state/drain-run-state.json` seed literal, and the bridge-backed
`drain-run-state` resource no longer thread through the promoted parent
route — or, where a live consumer is proven by a focused check, are
isolated at a declared public/legacy boundary with owner, consumer, schema,
authority class, and retirement condition.

The bounded surface is:

- retirement of the `run-state`/`run_state` fields and parameters from the
  `std/drain` drain result lanes: `DrainResult`, `DrainLoopTerminal`,
  `DrainLoopState`, the three result procs, and `finalize-drain-terminal`
  forwarding, together with the then-unused `StateExisting` import;
- retirement of the compiler-side run-state threading in the shared
  `backlog-drain` lowering (`phase_drain.py` `acc__run-state` seed and
  loop/terminal carrier plumbing, `drain_terminal.py` `return__run-state`
  projection), applied as removal of dead generic plumbing, not as
  family-specific branching;
- retirement of the family `transitions.orc` bridge lane: the bridge-backed
  `drain-run-state` resource, its five bridge transitions, and the
  `run_state_path`/`RunStatePath`-typed wrapper workflows and procs listed
  in the Revision Note, collapsing the parallel bridge/native transition
  duplication to a single state-layout-backed lane per operation;
- retirement of the `RunStatePath` path type from
  `workflows/library/lisp_frontend_design_delta/types.orc` if no live
  consumer remains after the wrapper retirement;
- making the two runtime proof fixtures
  (`runtime_transition_fixture.orc`, `runtime_view_fixture.orc`) compile
  and execute again: their call sites already use the carrier-free shape,
  so the repair is retiring the wrapper's `run_state_path` parameter and
  bridge backing — or, if the wrapper is deleted, re-pointing the fixtures
  at a surviving state-layout-backed transition — so their proofs keep
  exercising the runtime-native transition and view routes;
- realignment, in the same change, of every checked contract that names a
  retired identity: the transition-authoring manifest rows, the
  resume-plumbing retirement manifest and census-module constants, the
  migration-parity targets, and the focused test modules that pin the
  current shapes; and
- direct consumers of the changed contracts, repaired only when a focused
  check fails.

The architecture does not redesign provider request records, gap re-entry
convergence, public publication, consumer-side rendering, YAML-primary
promotion, or migration evidence. It does not touch the selected-item
finalization lane, the owner-boundary terminal split, or the
transition-authoring census mechanics landed by the prior revisions except
where a checked row names a retired identity. It does not retire the
generic `bridge` backing capability from the frontend/runtime substrate —
only this family's use of it.

## Current Checkout Baseline (verified 2026-07-06)

Already landed and green (preserve; do not re-do):

- Section-14 parent-drain compile entrypoint exits 0 (fresh run,
  `lowering_route: wcc_m4`).
- `tests/test_workflow_lisp_drain_stdlib.py`,
  `tests/test_workflow_lisp_transition_authoring.py`, and
  `tests/test_workflow_lisp_resume_plumbing_retirement.py`: 94 passed in one
  fresh run.
- `tests/test_workflow_lisp_migration_parity.py`,
  `tests/test_workflow_lisp_resource_stdlib.py`,
  `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`, and
  `tests/test_workflow_lisp_resource_transition_runtime.py`: green in the
  same fresh combined run (147 passed; the only failures were the fixture
  lane below). Treat as live regression guards.

Still-broken surface this slice repairs (verified fresh):

- `tests/test_workflow_lisp_view_dual_run.py`: 3 failed / 1 passed;
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k
  "runtime_transition_fixture or runtime_view_fixture"`: 5 failed;
- single root cause: both runtime proof fixtures already call
  `emit-drain-status-transition-audit` in the carrier-free shape (only
  `:summary_path`), and the wrapper's live `run_state_path` parameter
  rejects the call (`workflow_signature_mismatch`).

Everything else on this frontier is *declared* debt rather than a red
gate: the resume-plumbing bridge row is `BLOCKED` with a retirement
condition, and the drain-stdlib tests pin the current carrier-bearing
shapes as the checked contract. That part of the work is contract-shift
work — the checked pins move together with the retirement, and those gates
must be green on both sides of the change. A checked pin of a
carrier-bearing shape is a live contract to update in the same change, not
a stale artifact to delete and not a reason to keep the carrier.

## Ownership

The `std/drain` owner lane owns the drain result/terminal type family, the
result procs, and the terminal-responsibility split. Carrier retirement
changes their *shapes* (field/parameter removal) but must not change the
terminal split semantics: result procs stay pure variant constructors with
`:effects ()`, and terminal effects stay owned by
`consume-drain-terminal-effects` behind `backlog-drain`. The
state-layout-backed `std/drain::drain-run-state` resource, the
`DrainOutcome*` record family, and runtime-native `record-drain-outcome`
are the survivor lane and keep their schemas, backend kind, conflict
policy, audit projection, and write-root identities
(`std_drain_backlog_drain__normalize_result__*`, pinned by
`tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`).

The shared lowering layer (`orchestrator/workflow_lisp/lowering/phase_drain.py`,
`orchestrator/workflow_lisp/lowering/drain_terminal.py`) owns the lowered
loop-state and terminal-carrier plumbing. It serves every `backlog-drain`
caller, so run-state threading is removed as generic dead plumbing keyed by
the retired contract fields — not by family naming or census-specific
branching. If any lowered artifact contract still demands a
`return__run-state`/`acc__run-state` binding after the type surface is
carrier-free, that contract derivation is the defect to fix, not a reason
to keep fabricating the literal seed.

The Design Delta family (`workflows/library/lisp_frontend_design_delta/`)
owns `transitions.orc`, `types.orc`, and the runtime proof fixtures. It
owns the decision of surviving transition identities when the
bridge/native duplication collapses. Renames are implementation freedom,
but every checked contract that names a transition identity must be
realigned in the same change (see Source Surfaces rules).

The resume-plumbing retirement census
(`orchestrator/workflow_lisp/resume_plumbing_retirement.py` and its checked
manifest) owns the declared-debt record for the bridge resource. This slice
changes that record from tolerated debt (`BLOCKED`) to discharged
retirement; the census module's evidence constants
(`REQUIRED_TRANSITION_IDENTITIES` = `write-drain-status`,
`RETIREMENT_EVIDENCE_REQUIREMENTS` naming `write-drain-status` and
`record-terminal-work-item`, the `DRAIN_RUN_STATE_BRIDGE_*` row contract
with allowed decisions `KEPT_COMPATIBILITY`/`BLOCKED`) must be realigned to
the surviving identities and to a retirement decision that stays
fail-closed: a retired bridge must be provably absent, never silently
unchecked.

The transition-authoring manifest
(`workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`)
keeps the standing rule from the prior revision: a row is valid only while
at least one compiled origin matches it; rows whose identities retire leave
or are re-pointed in the same change; the gate in
`orchestrator/workflow_lisp/build.py` is not weakened.

Migration parity (`orchestrator/workflow_lisp/migration_parity.py`,
`workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`)
owns parity evaluation over the public contract and declared semantic
effects. Parity rows naming `record-terminal-work-item` or other retired
identities are re-pointed at surviving identities; parity must not be
weakened, and parity must not require the `.orc` family to reproduce
YAML-era `run_state.json` merge mechanics (the parity constraint already
recorded in the resume-plumbing manifest).

`docs/design/workflow_command_adapter_contract.md` owns any retained
script, command step, legacy adapter, or runtime-native decision. If a
focused check proves a live legacy consumer still needs a YAML-era
run-state JSON write, that write is isolated per the recorded retirement
condition as a declared legacy boundary under the adapter contract's
legacy-adapter rules — labeled, fixture-tested, not imported by ordinary
family composition.

## Source Surfaces

Primary source surfaces:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` (carrier
  fields/parameters off `DrainResult`, `DrainLoopTerminal`,
  `DrainLoopState`, the three result procs, `finalize-drain-terminal`;
  drop the then-unused `StateExisting` import);
- `orchestrator/workflow_lisp/lowering/phase_drain.py` and
  `orchestrator/workflow_lisp/lowering/drain_terminal.py` (retire
  `acc__run-state` seeding/threading, `terminal__run-state`,
  `return__run-state`, and the `state/drain-run-state.json` seed literal);
- `workflows/library/lisp_frontend_design_delta/transitions.orc` (retire
  the bridge resource, bridge transitions, and `RunStatePath` wrappers;
  collapse bridge/native duplication to one state-layout lane per
  operation);
- `workflows/library/lisp_frontend_design_delta/types.orc` (`RunStatePath`
  defpath retirement if unused);
- `workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc`
  and `workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc`
  (re-point at a surviving transition);
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`,
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`,
  and `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  (checked rows track surviving identities and the discharged retirement);
- `orchestrator/workflow_lisp/resume_plumbing_retirement.py` (evidence
  constants and bridge-row decision contract realignment, fail-closed);
- `tests/test_workflow_lisp_drain_stdlib.py`,
  `tests/test_workflow_lisp_transition_authoring.py`,
  `tests/test_workflow_lisp_resume_plumbing_retirement.py` (move the pins
  to the carrier-free shapes; extend negative coverage so a reintroduced
  carrier fails).

Already-landed surfaces to preserve (verify, do not re-edit unless a
focused check fails):

- `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`
- `workflows/library/lisp_frontend_design_delta/drain.orc`,
  `work_item.orc`, `stdlib_adapters.orc` (already carrier-free; only the
  import list changes if a surviving transition identity is renamed)
- `orchestrator/workflow_lisp/source_map.py` step-kind projection (landed
  by the prior revision)

Conditional source surfaces, in scope only when a focused check fails:

- `orchestrator/workflow_lisp/typecheck_dispatch.py`,
  `orchestrator/workflow_lisp/wcc/elaborate.py`,
  `orchestrator/workflow_lisp/procedure_specialization.py`, and
  `orchestrator/workflow_lisp/lowering/core.py`, where they validate or
  project the retired fields/bindings;
- `orchestrator/workflow_lisp/adapters/normalize_drain_result.py` and the
  command-boundary manifest, if the retired terminal carrier changes the
  adapter's input contract (any change stays inside the certified-adapter
  rules of the command adapter contract);
- the mirrored fixture tree
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/…` and
  the `drain_stdlib_*` compile fixtures under
  `tests/fixtures/workflow_lisp/`, as ordinary test maintenance;
- `tests/test_workflow_lisp_migration_parity.py`,
  `tests/test_workflow_lisp_view_dual_run.py`, and
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  (including the execution smoke's `state/drain-run-state.json` seeding,
  which becomes unnecessary when the seed literal retires);
- `orchestrator/workflow_lisp/value_flow_census.py` /
  `design_delta_parent_drain.value_flow_census.json` and the boundary
  authority manifest, if a checked row still describes the bridge lane.

Rules for files used outside this gap:

- `phase_drain.py` and `drain_terminal.py` lower every `backlog-drain`
  caller, not just this family. Run-state plumbing removal must be generic
  (keyed by the retired contract fields), must not change selection/gap/
  item routing semantics or terminal fan-in shape, and must keep the
  `std_drain_backlog_drain__normalize_result__*` write-root identities
  stable. All `drain_stdlib_*` compile fixtures and the drain-stdlib test
  module revalidate it.
- `std/drain.orc` is imported by any family using `backlog-drain`. The
  carrier-free `DrainResult`/`DrainLoopTerminal` shapes are the new
  exported contract; callers that pattern-match these unions keep working
  because no caller reads the retired fields (verified), but any
  workflow-ref shape check that names the retired fields follows the
  shapes in the same change.
- `resume_plumbing_retirement.py` and its manifest are read by the build
  gate and the resume-retirement test module. The bridge row transitions
  from `BLOCKED` to a discharged state through a checked decision shape;
  removing the row silently, or leaving a decision that names an absent
  resource without proof-of-absence, are both defects.
- `parity_targets.json` and the transition-authoring manifest are read by
  the build gate and parity/census test modules. Rows describe live
  compiled identities only; retired identities leave the manifests in the
  same change that retires them.
- If any file outside these surfaces still uses `run_state_path` /
  `run-state` for ordinary Workflow Lisp composition, it follows the
  standing rule: remove the carrier or isolate it as an explicit
  public/legacy bridge with owner, consumer, schema, authority class, and
  retirement condition. Generic runtime/frontend `bridge`-backing support
  and non-family uses of `run_state_path` in the checkpoint/resume
  substrate are out of scope.

## Contract

Typed values are the semantic channel for the promoted Design Delta parent
route. After this slice, no `StateExisting` run-state value, run-state path
literal, or bridge-backed run-state resource participates in ordinary
stdlib/family composition:

- `DrainResult`, `DrainLoopTerminal`, and `DrainLoopState` carry only
  semantically consumed fields (items processed, report paths, blocker
  class); a field no consumer reads is a defect, not a reserve;
- the lowered `backlog-drain` loop threads only the typed loop state the
  contract declares; it does not fabricate path literals to satisfy
  retired carriers;
- durable drain/work-item/recovery state changes flow exclusively through
  state-layout-backed, runtime-native, fail-closed transitions
  (`record-drain-outcome`, the surviving family transitions); and
- transition-audit visibility rules from the prior revision remain in
  force: every live transition origin on the promoted route is census-
  visible and classified by exactly the checked manifest.

The carrier prohibition on the selected-item finalization lane is unchanged
and remains in force. The deny-guards
(`orchestrator/workflow_lisp/typecheck_calls.py`,
`orchestrator/workflow_lisp/lowering/workflow_calls.py`) and the
custom-union run-state rejection pinned by the drain-stdlib tests stay in
place; this slice extends the same carrier-free rule to the drain
result/terminal lanes rather than relaxing it anywhere.

Isolation fallback: if a focused check run during implementation proves a
live consumer still requires a YAML-era run-state JSON write (for example a
parity target that cannot yet be re-pointed), that single write is isolated
at a declared legacy boundary per the recorded retirement condition — with
owner, consumer, schema, authority class `compatibility_bridge` or legacy
adapter certification, and a retirement condition — and ordinary
composition must not import it. Absent such proof, the lane is removed
outright.

## Command Adapter And Runtime-Native Policy

No new inline Python, shell, heredocs, stdout JSON semantics, report
parsing, pointer-as-state behavior, ad hoc JSON rewrites, or uncertified
scripts are allowed in this slice.

The surviving transitions remain runtime-native, `fail_closed`,
state-layout-backed, with their landed carrier-free request/result/audit
schemas. Nothing in the carrier retirement may alter backend kind, conflict
policy, audit projection, idempotency fields, or fail-closed behavior of
`record-drain-outcome`, `record-selected-item-outcome`, or the surviving
family transitions.

No new runtime-native promotion is expected: the runtime-derived
replacement lane already exists. If implementation discovers a genuinely
missing native capability, that is a shared prerequisite to report, not to
patch around with a family adapter.

`materialize_lisp_frontend_work_item_inputs` remains a certified
command-boundary row with retired compatibility status; it must not be
invoked by the promoted route or counted as retirement evidence.

## Allowed Shapes

Allowed implementation shapes include:

- deleting the `run-state`/`run_state` fields and parameters from the
  `std/drain` types and result procs, and shrinking
  `finalize-drain-terminal` forwarding accordingly, because no consumer
  reads them (verified on this checkout);
- deleting the `acc__run-state` seed (including the
  `state/drain-run-state.json` literal), the loop-state threading, the
  `terminal__run-state` carrier, and the `return__run-state` projection
  from the shared lowering, as removal of plumbing that exists only to fill
  the retired fields;
- deleting the bridge-backed `drain-run-state` resource and its five bridge
  transitions from `transitions.orc`, and deleting or re-typing the
  `RunStatePath` wrapper workflows/procs
  (`emit-drain-status-transition-audit`, `apply-drain-status-transition`,
  `record-drain-terminal-outcome`, `record-work-item-terminal-outcome`) so
  no `run_state_path` parameter remains in the module;
- collapsing the bridge/native duplication by either renaming the
  surviving `-stdlib`/`-native` identities to the base names or keeping
  the suffixed names — in both cases realigning every checked contract
  (transition-authoring rows, parity targets, resume-plumbing evidence
  constants, feasibility/dual-run assertions, fixture workflows) to the
  surviving identities in the same change;
- renaming or keeping the surviving family resource name
  (`drain-run-state-native` or `drain-run-state`) as implementation
  freedom under the same realignment rule;
- recording the discharged retirement in the resume-plumbing manifest
  through a checked decision shape (for example a `RETIRED` decision whose
  validation requires proof of absence of the bridge symbol), extending the
  census module's allowed-decision contract fail-closed rather than
  deleting the row silently;
- repairing the runtime proof fixtures by retiring the wrapper's carrier
  parameter (their call sites already use the carrier-free shape) or by
  re-pointing them at a surviving state-layout transition, so the
  transition/view execution proofs stay live;
- moving the checked test pins (drain-stdlib, transition-authoring,
  resume-retirement, parity, feasibility) to the carrier-free shapes and
  extending negative coverage so a reintroduced run-state field, parameter,
  seed literal, or bridge-backed family resource fails a focused test; and
- ordinary test/fixture maintenance for inputs that still encode the
  carrier-bearing shapes, including dropping the execution smoke's
  `state/drain-run-state.json` seeding once the seed literal is gone.

If retiring the lowering plumbing surfaces a defect that cannot be repaired
as a bounded generic change with focused shared coverage inside this slice
(for example, a validated-bundle or checkpoint contract that structurally
requires a loop-state path artifact for every drain loop), stop the slice
and report the shared prerequisite instead of keeping the carrier or
patching family-specific exceptions around it.

## Forbidden Shapes

This slice must not:

- keep any `run-state`/`run_state` field, parameter, or forwarded value in
  `std/drain` drain result lanes, or fill retired fields with surrogate
  values (empty strings, dummy paths, placeholder records);
- keep the lowering seed literal `state/drain-run-state.json` or continue
  threading a run-state accumulator/terminal carrier after the fields are
  gone;
- keep the bridge-backed `drain-run-state` resource, a bridge transition,
  or a `run_state_path`-typed wrapper reachable from ordinary family
  composition, or reintroduce the bridge under a new name;
- satisfy a checked contract by weakening it: no softening the
  transition-authoring gate, the resume-plumbing validation, parity
  evaluation, or the drain-stdlib deny-guards; no deleting the
  resume-plumbing bridge row without a checked discharged-retirement
  record; no census ignore markers over live identities;
- change the terminal-responsibility split, the result procs' pure-
  constructor status, `consume-drain-terminal-effects` ownership, or the
  `std_drain_backlog_drain__normalize_result__*` write-root identities to
  make retirement easier;
- alter backend kind, conflict policy, idempotency, audit projection, or
  fail-closed behavior of any surviving transition;
- add family, drain, phase, or item naming — or carrier-specific branching
  — to shared lowering/compiler modules while removing the plumbing;
- reintroduce `run_state_path`/`run-state` in any forbidden form on the
  selected-item finalization lane or remove its deny-guards;
- route retirement evidence through rendered reports, pointer files, bundle
  rereads, provider prose, or stdout;
- retire or weaken the generic `bridge` backing capability of the
  frontend/runtime substrate, or touch non-family `run_state_path` uses in
  the checkpoint/resume substrate; or
- claim YAML-primary replacement from compile, validation, smoke, census,
  or retirement evidence alone.

## Acceptance Conditions

The slice is accepted when all of the following hold:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` contains no
  `run-state`/`run_state` field, parameter, or `StateExisting` use on the
  drain result lanes; `workflows/library/lisp_frontend_design_delta/transitions.orc`
  contains no `(bridge run_state_path)` backing, no bridge transitions, and
  no `RunStatePath`-typed parameter; and the family route to every durable
  drain/work-item/recovery state change is a state-layout-backed
  runtime-native transition. A focused negative test fails if any of these
  reappear.
- The shared `backlog-drain` lowering no longer emits `acc__run-state`,
  `terminal__run-state`, or `return__run-state` bindings and no longer
  references the `state/drain-run-state.json` seed literal, verified by a
  focused lowering/compile check that inspects the lowered bundle rather
  than rendered output.
- The Section-14 parent-drain compile entrypoint exits 0 (green today; must
  stay green across the contract shift).
- `tests/test_workflow_lisp_drain_stdlib.py`,
  `tests/test_workflow_lisp_transition_authoring.py`, and
  `tests/test_workflow_lisp_resume_plumbing_retirement.py` are fully green
  with their pins moved to the carrier-free shapes (94 passed today against
  the carrier-bearing pins; the same modules must pass against the shifted
  pins, with negative coverage for reintroduced carriers).
- The resume-plumbing retirement manifest's
  `transitions.resource.drain_run_state` row is discharged through a
  checked decision shape whose validation proves the bridge symbol is
  absent from `transitions.orc`; the census module's evidence constants
  name only surviving transition identities; validation remains
  fail-closed.
- The transition-authoring manifest and `parity_targets.json` contain only
  rows matching live compiled identities; no row names a retired bridge
  wrapper identity; the transition-authoring report passes with every row
  matched.
- The runtime proof fixtures compile and execute against a surviving
  state-layout transition: `tests/test_workflow_lisp_view_dual_run.py`
  (currently 3 failed / 1 passed) and the fixture-backed feasibility
  selection (`-k "runtime_transition_fixture or runtime_view_fixture"`,
  currently 5 failed) are fully green, so restoring them is required, not
  incidental; the promoted-route feasibility selection
  (`-k "selected_item_stdlib or parent_drain_build_and_execution_smoke"`)
  stays green.
- Regression guards stay green:
  `tests/test_workflow_lisp_resource_stdlib.py`,
  `tests/test_workflow_lisp_resource_transition_runtime.py`,
  `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`, and
  `tests/test_workflow_lisp_migration_parity.py`.
- Runtime-native transition behavior is unchanged on the survivor lane:
  `record-drain-outcome`, `record-selected-item-outcome`, and the surviving
  family transitions remain runtime-native, fail-closed,
  state-layout-backed, with audit projection and source-map provenance
  intact.
- Either no legacy run-state JSON write remains anywhere in the family, or
  exactly one is isolated at a declared legacy boundary with owner,
  consumer, schema, authority class, and retirement condition, proven
  needed by a focused check and not imported by ordinary composition.
- Direct consumers of the changed contracts are repaired only where a
  focused check fails; fixture or checked-input updates are ordinary test
  maintenance, not independent acceptance obligations.

This architecture closes only the selected compatibility-carrier retirement
gap on its run-state frontier: the `std/drain` carrier fields, the shared
lowering's run-state threading, and the family bridge-backed
`drain-run-state` lane. It does not certify full runtime-native drain
completion, provider request-record migration, gap convergence,
consumer-side rendering completion, or YAML-primary promotion.
