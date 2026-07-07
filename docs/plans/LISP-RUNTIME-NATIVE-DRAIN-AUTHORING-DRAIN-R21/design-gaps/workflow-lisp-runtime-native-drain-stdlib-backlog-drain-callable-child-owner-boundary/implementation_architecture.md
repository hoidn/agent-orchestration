# Stdlib Backlog-Drain Callable-Child Owner Boundary Architecture

Status: revised implementation architecture (fourth revision, 2026-07-06)
Design gap id: `workflow-lisp-runtime-native-drain-stdlib-backlog-drain-callable-child-owner-boundary`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
(Sections 9.1, 10, 12.2, 13.4, 15)
Shared owner-lane ledger:
`docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (Sections 2.1,
2.1.1)
Baseline design: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Purpose

This gap closes the remaining terminal responsibility split for the promoted
`std/drain::backlog-drain` callable-child route. The callable owner-boundary
emission is already the accepted baseline: a parent lowers to one ordinary
typed call, and the generated child owns the `repeat_until` loop, typed
accumulator, terminal carrier, terminal normalization, source-map provenance,
and both imported and same-file promoted-callable front doors.

The remaining violation is narrower. The live child terminal lane emitted by
`orchestrator/workflow_lisp/lowering/drain_terminal.py::lower_shared_drain_terminal_result`
bundles terminal effects into the child's value-return path:

- a `record-drain-outcome` `resource_transition` against lowering-declared
  drain bookkeeping; and
- a `materialize_view` rendering of `DrainSummaryValue` to the generated
  progress-report path.

Those effects currently execute as prerequisites for returning `DrainResult`.
The shared owner-lane ledger forbids that shape. Ledger Section 2.1 requires
`backlog-drain` to return `DrainResult<TSummary>` without terminal publication,
summary materialization, run-state mutation, or drain-outcome recording as
part of value return. Ledger Section 2.1.1 requires declared terminal effects
to run only behind explicit boundary/resource contracts with named consumers.

This architecture therefore preserves the landed child-call emission contract
and changes only the terminal responsibility boundary: the child returns the
typed terminal value through pure projection, while any drain-outcome recording,
public publication, audit projection, or external mutation remains an explicit
authored effect surface.

## Governing Contract

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Section 9.1
  routes this prerequisite to the shared owner-lane ledger. Sections 10 and 15
  require terminal records, summaries, bridges, audit entries, and resource
  transitions to name a consumer and authority class; they are invalid as
  hidden prerequisites for ordinary typed value return. Section 13.4 requires
  the reference family to reach typed terminal return without interior
  summary-file materialization.
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` Sections 2.1
  and 2.1.1 define the accepted contract for callable-child value return and
  terminal responsibility split.
- `docs/design/workflow_lisp_frontend_specification.md` keeps `std/drain` as
  ordinary imported `.orc` composition over typed calls, transitions,
  projections, views, and source maps. This gap does not claim full intrinsic
  retirement under the broader conversion path.
- `docs/design/workflow_command_adapter_contract.md` classifies
  `record-drain-outcome`-class mutation as `resource_transition` behavior.
  Retiring the compiler-bundled invocation is not a transition-backend change
  and must not be replaced by inline scripts, stdout protocols, report
  parsing, pointer authority, or ad hoc JSON rewrites.

Selection provenance: this gap is the shared owner-lane prerequisite recorded
as `PREREQUISITE_GAP_REQUIRED` by the blocked compatibility-carrier retirement
sibling. It delivers only ledger Sections 2.1 and 2.1.1 for the stdlib
`backlog-drain` callable-child route.

## Baseline And Gap Classification

Accepted baseline, not reopened:

- Parent emission lowers to exactly one `call std/drain::backlog-drain`.
- The generated child owns the loop, typed accumulator, terminal carrier, and
  normalized `DrainResult` return.
- Imported `std/drain::backlog-drain` and same-file promoted-callable
  authoring converge on the same emission.
- Specialization identity, fixed selector/`run-item`/`gap-drafter`
  boundaries, gap-payload record-leaf carriage, hidden entry-context binding
  metadata, negative diagnostics, and source-map provenance remain frozen.
- The Design Delta parent already consumes the child result as a typed value,
  projects it with family projection helpers, records terminal state through
  an explicit family transition, and publishes public terminal summaries at
  the entry boundary.
- `std/drain.orc` already separates pure terminal classification
  (`finalize-drain-terminal`) from the optional effect surface
  (`consume-drain-terminal-effects`).

Live violation owned by this gap:

- The lowered child's terminal cases still contain the unconditional
  `record-drain-outcome` transition and `materialize_view` summary rendering.
  Their presence in the value-return case, not their ordering, violates the
  ledger contract.

Stale coverage and checked metadata to realign:

- Drain-stdlib guards that assert transition/view steps, hidden
  `shared_drain_result` inputs, drain run-state paths, audit-log paths, or
  audit rows as completion evidence are compatibility expectations. They must
  be replaced with assertions over typed child-call value return and explicit
  authored effect surfaces.
- Checked parent-drain manifests and focused build-artifact guards may retain
  rows only for compiled/rendered surfaces that still exist. Rows keyed solely
  to the retired `__shared_drain_result__summary` child effect are stale once
  compiled evidence shows that effect is absent. Manifest fingerprint and
  provenance checks remain fail-closed coherence requirements, not advisory
  bookkeeping.

If implementation finds a durable non-test consumer of the child-owned
run-state file, `record-drain-outcome` audit log, or child-rendered terminal
summary as semantic input, the result is a `semantic_conflict` between checked
consumers. Do not silently preserve the bundled lane or choose one consumer by
preference.

## Ownership And Bounded Scope

This slice owns:

- the child value-return lane in
  `orchestrator/workflow_lisp/lowering/drain_terminal.py` and its invocation
  from `orchestrator/workflow_lisp/lowering/phase_drain.py`;
- removal of lowering-owned transition/view machinery that exists only to make
  terminal effects prerequisites for `DrainResult` return;
- preservation of `std/drain.orc` value shapes and effect-surface split:
  `SelectionResult`, `GapResult`, `DrainResult`, `DrainLoopTerminal`, and
  `DrainLoopState` do not change; `finalize-drain-terminal` remains pure; and
  `consume-drain-terminal-effects` remains the explicit authored opt-in effect
  surface;
- test realignment for lowered structure, provenance, typed runtime outputs,
  both authoring front doors, and the pure-vs-effectful stdlib split; and
- checked-manifest and build-artifact coherence for the retired child summary
  effect, with fail-closed gates preserved.

This slice does not own:

- reworking the landed callable-child synthesis or the parent one-call shape;
- editing family `.orc` sources such as `drain.orc`, `projections.orc`,
  `transitions.orc`, or `work_item.orc`; the parent side already expresses the
  accepted split;
- changing reference-family conformance, migration-parity, census,
  retirement, shared-validation, source-map, or build-gate semantics;
- ledger Sections 2.2-2.4, ledger Section 3.5 work-item summary ownership, or
  ledger Section 4 `std/phase` owner-lane self-hosting;
- deleting the drain intrinsic in favor of complete imported-`.orc`
  expansion; or
- making any YAML-primary promotion claim.

## Contract

### Value-Return Lane (ledger 2.1)

On the promoted WCC route, every terminal case of the lowered
`std/drain::backlog-drain` child follows the value-only path:

```text
repeat_until loop (typed DrainLoopState accumulator; child-owned)
  -> terminal carrier match over acc__loop-status
       EMPTY | COMPLETED | BLOCKED | EXHAUSTED
       CONTINUE fallback -> EXHAUSTED
  -> normalize_result match over terminal__variant
       per terminal case: pure projection of return__variant and
       declared DrainResult fields from terminal carrier refs
  -> typed DrainResult child-call value return to the parent
```

Each terminal case contains no `resource_transition`, no `materialize_view`, no
generated run-state allocation, no transition audit allocation, no
effect-result bundle allocation, and no hidden input whose only purpose is the
retired effect lane. Returning `DrainResult` requires only the typed
projection.

The existing terminal semantics stay fixed: EMPTY and COMPLETED return their
corresponding variants; BLOCKED returns the carried blocker class and reason;
EXHAUSTED normalizes to the BLOCKED result variant with the carried exhaustion
blocker class; placeholder blocker values for non-blocked variants remain
unchanged. `run_state` remains absent from returned fields and remaining
bindings.

### Declared Terminal Effects (ledger 2.1.1)

Terminal effects are explicit authored surfaces with named consumers:

- parent workflow consumption uses the returned typed value directly;
- public reports or dashboards use boundary publication policy;
- durable domain/resource state uses a named transition declared by the family
  or stdlib caller; and
- resume uses runtime-owned checkpoint state, not authored drain bookkeeping.

Lowering must not auto-invoke any of these effects. In `std/drain.orc`,
`consume-drain-terminal-effects` remains a callable effect surface for families
that intentionally opt into stdlib drain-outcome recording and summary view
rendering. It is not a value-return prerequisite and is not injected by a
macro, compiler default, hidden binding, or compatibility marker step.

### Provenance And Effects

Every remaining generated child step keeps source-map and origin-map
provenance back to the authored `backlog-drain` form. Removing terminal effect
steps also removes their generated path records, hidden-input spans, and
`GeneratedSemanticEffectBinding` entries; no orphaned effect metadata remains.

Semantic IR and executable IR continue to expose surviving generated
projections and declared authored effects. The absence of a child summary view
or child transition in the value-return lane is itself part of the contract.

## Rule For Outside Uses

The split is generic for the promoted `backlog-drain` route:

- `drain_terminal.py` and `phase_drain.py` must not branch on
  `lisp_frontend_design_delta`, family names, workflow names, or checked
  manifest identities.
- No opt-in path may let lowering silently recreate the bundled terminal
  effect lane under another name.
- `std/drain.orc` exports remain stable for composing families and fixtures;
  value shapes do not widen, and callers that need `consume-drain-terminal-effects`
  call it explicitly.
- Checked manifests remain fail-closed compile inputs. They may describe only
  current compiled/rendered surfaces and explicit compatibility bridges with
  owners, consumers, schemas, and retirement conditions.
- Realigned tests assert contract behavior: effect-free lowered terminal
  cases, typed child-call outputs, explicit authored effect surfaces, and
  fail-closed manifest validation. They must not assert prompt prose or report
  wording.

## Command Adapter And Runtime-Native Policy

No new command adapter, inline Python or shell, stdout protocol, report parser,
pointer-as-state convention, or ad hoc JSON rewrite may participate in terminal
normalization or value return. `record-drain-outcome` remains a
`resource_transition`-class effect only when reached through an explicit
authored transition/effect surface. Test fakes may continue to exercise
declared command boundaries, but they do not define value-return semantics.

## Allowed Shapes

- Reduce `lower_shared_drain_terminal_result` to pure result projection, or
  inline that projection into `phase_drain.py`, provided terminal carrier,
  normalization, source maps, and fallback semantics remain valid.
- Remove `_drain_terminal_transition_config` and generated state/audit/bundle
  allocations when they serve only the retired bundled lane.
- Keep the terminal-carrier plus normalize two-stage lane if it remains
  effect-free and preserves the existing child-owner provenance.
- Realign drain-stdlib structure and runtime tests to assert value return for
  empty, completed, blocked, and exhausted terminals without requiring
  effect-lane files.
- Realign build-artifact tests and checked manifests so rows keyed only to the
  removed child summary effect are absent and surviving rows keep their
  existing classifications.
- Leave `std/drain.orc` textually unchanged unless a local comment or
  classification note is needed; value records, unions, and public signatures
  stay frozen.

## Forbidden Shapes

- Any `resource_transition`, `materialize_view`, run-state seed, transition
  audit write, summary render, or compatibility marker inside a child's
  terminal value-return case.
- Auto-invoking `consume-drain-terminal-effects` or an equivalent from
  lowering, macros, defaults, or hidden bindings.
- Re-adding `run_state`, state-root, checkpoint, generated-path, or summary
  carriers to `DrainResult` variants, parent public unions, or fixed callable
  boundaries.
- Widening selector, `run-item`, or `gap-drafter` callable boundaries.
- Reintroducing `EmitDrain*`-style caller-owned terminal fan-in or parent
  compensation workflows.
- Weakening fail-closed diagnostics such as `value_flow_census_invalid`,
  `consumer_rendering_census_invalid`,
  `resume_plumbing_retirement_invalid`,
  `workflow_boundary_authority_unclassified`, or
  `reference_family_conformance_invalid`.
- Editing runtime-owned evidence or validation gates to make the route appear
  coherent.
- Claiming YAML-primary promotion, conversion-lane completion, or adoption
  beyond ledger Sections 2.1 and 2.1.1.

## Source Surfaces

Repair surfaces:

- `orchestrator/workflow_lisp/lowering/drain_terminal.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.rendering_cleanup.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Read-only contract authority:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/value_flow_census.py`
- `orchestrator/workflow_lisp/consumer_rendering_census.py`
- `orchestrator/workflow_lisp/resume_plumbing_retirement.py`
- `orchestrator/workflow_lisp/reference_family_conformance.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- family `.orc` modules under `workflows/library/lisp_frontend_design_delta/`

## Acceptance Conditions

Fresh evidence on the current working tree must show:

- `tests/test_workflow_lisp_drain_stdlib.py` passes as a module with realigned
  guards proving each lowered terminal case is value projection only, with no
  transition/view step, effect-only hidden input, or effect-lane generated
  path in the child value-return path.
- Runtime coverage reaches empty, completed, blocked, and exhausted
  callable-child terminals and asserts the returned typed `DrainResult`
  through ordinary child-call workflow outputs.
- Both authoring front doors still converge on the same emission, and the
  frozen structural/provenance, specialization, gap-payload, and negative
  diagnostic proofs remain green.
- `finalize-drain-terminal` remains pure and
  `consume-drain-terminal-effects` remains present only as the explicit
  authored effect surface.
- Checked parent-drain manifests are coherent with compiled evidence: no row
  remains for a child summary effect that no longer exists; surviving rows
  keep their classifications; and value-flow, consumer-rendering,
  rendering-cleanup, and resume-plumbing fail-closed gates remain active.
- Preserved family lanes stay green, including selected-item stdlib coverage,
  the Design Delta parent drain smoke, autonomous drain runtime smoke, phase
  stdlib, and resource stdlib checks.
- The Design Delta Section 14 compile entrypoint exits 0 with the checked
  provider, prompt, and command-boundary inputs, and reference-family
  conformance remains based on coherent runtime-owned evidence.
- No fail-closed gate, callable-result union, fixed callable boundary,
  shared-validation rule, or command-boundary policy is widened, weakened, or
  special-cased.

Compile success alone is insufficient. The evidence must show typed terminal
value return with the terminal effect lane absent from the child value-return
path and present only behind explicit authored surfaces.

## Residual Failure Routing

- A durable semantic consumer of the retired child-owned files or audit rows
  routes to `semantic_conflict`, not silent preservation of the bundled lane.
- Compatibility-carrier and fixture-mirror residue routes to the separate
  compatibility-carrier retirement sibling after this prerequisite lands.
- Gap re-entry convergence routes to ledger Section 2.4.
- Work-item summary ownership routes to ledger Section 3.5.
- `std/phase` owner-lane self-hosting routes to ledger Section 4.
