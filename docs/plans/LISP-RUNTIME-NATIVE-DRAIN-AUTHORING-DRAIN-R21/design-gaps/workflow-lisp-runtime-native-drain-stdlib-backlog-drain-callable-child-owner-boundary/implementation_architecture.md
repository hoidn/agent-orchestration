# Stdlib Backlog-Drain Callable-Child Owner Boundary Architecture

Status: draft implementation architecture (2026-07-02)
Design gap id: `workflow-lisp-runtime-native-drain-stdlib-backlog-drain-callable-child-owner-boundary`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
(Sections 9.1, 12.2, 13.4)
Shared owner-lane ledger:
`docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (Sections 2.1,
2.1.1)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This architecture delivers exactly the shared owner-lane ledger Section 2.1
prerequisite (Callable-Child Value Return Over Imported `backlog-drain`) on
the promoted WCC route: the compile output must contain a lowered
`std/drain::backlog-drain` child workflow that owns the `repeat_until` loop
and its typed accumulator, the parent route must reduce to one ordinary typed
`call` step whose value return is `DrainResult`, and terminal effects must be
separated from value return per ledger Section 2.1.1. The contract covers
both authoring front doors the ledger names: the imported
`std/drain::backlog-drain` shape and the same-file promoted-callable shape.

This is the recorded prerequisite
(`recovery_route PREREQUISITE_GAP_REQUIRED`) blocking
`workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`
(its "Prerequisite P"). That sibling's architecture routed the
promoted-stdlib-route conversion class of red checks to this lane; this
document is that lane's bounded contract.

In scope:

- promoted-route (WCC M4, `DEFAULT_LOWERING_ROUTE`) emission of the lowered
  `std/drain::backlog-drain` child owner boundary for both authoring shapes,
  including the `preserve_owner_boundary` authored-spec support and WCC-route
  admission of the drain intrinsic that the pinned checks require;
- the child's shared terminal lane: loop-state accumulator, terminal carrier,
  terminal normalization, and typed `DrainResult` value return with declared
  terminal effects (transition/summary) ordered after — and never gating —
  the returned value artifacts;
- the `backlog-drain-callable-boundary` promoted-callable authored head that
  the checked-in callable-boundary proof fixtures pin;
- specialization identity for the generated child (canonical shared name
  reused for identical specializations, digest-suffixed names for distinct
  ones);
- the `std/drain.orc` terminal responsibility split
  (`finalize-drain-terminal` stays pure classification;
  `consume-drain-terminal-effects` carries the effect lane);
- source-map and provenance obligations for the parent call step, the
  projection steps over the returned union, and every generated child step;
  and
- runtime execution of the callable-child route to all four terminals
  (empty, completed, blocked, exhausted) through ordinary child-call value
  return — ledger Section 2.1's minimum behavior check.

Out of scope: the sibling regression slice's own closure (its Section-14 CLI
compile and parent smoke stay its completion-routing surfaces); ledger
Sections 2.2–2.4 beyond what the committed proofs already pin (parent
terminal reprojection and branch-local alignment fixtures are consumed as-is;
gap re-entry convergence is a separate family-owned prerequisite); preserving
or reconstructing a progressed public `DrainResult.run-state` /
`return__run-state` across the callable-child boundary; the `gap-continue
run-state carrier retirement` prerequisite and the deeper
`DrainResult`/`DrainLoopState` run-state retirement lanes; fixture-mirror sync
deferred by `workflow-lisp-design-delta-compatibility-carrier-retirement`;
`std/phase` owner-lane self-hosting; full intrinsic retirement under target
design Section 12.2 step 5 (deleting drain-aware compiler support entirely is
conversion-lane completion, not this prerequisite); and any YAML-primary
promotion claim.

## Evidence (2026-07-02, fresh output, current checkout)

`python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q` → 35 failed,
25 passed. Every failure traces to one missing mechanism family, in five
observed forms:

- **Absent lowered child.** Five structural/provenance proofs fail with
  `StopIteration` in `_child_backlog_drain_workflow`
  (`tests/test_workflow_lisp_drain_stdlib.py:469`) because
  `lowered_workflows` contains no workflow named `std/drain::backlog-drain`:
  `test_same_file_callable_boundary_preserves_generated_backlog_drain_owner_lane`
  plus the four proofs the selection names
  (`test_compile_stage3_module_preserves_parent_terminal_reprojection_over_imported_backlog_drain`,
  `test_parent_terminal_reprojection_preserves_imported_call_and_projection_provenance`,
  `test_compile_stage3_module_preserves_branch_local_terminal_contract_alignment_over_imported_backlog_drain`,
  `test_branch_local_terminal_contract_alignment_preserves_imported_call_and_projection_provenance`).
- **Missing promoted-callable head.** Compiles of
  `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary.orc`
  fail with `[procedure_call_unknown] unknown same-file procedure callee
  `backlog-drain-callable-boundary`` — the head the fixture (and
  `test_callable_boundary_fixture_uses_direct_helper_head`) pins does not
  resolve anywhere.
- **Unlanded spec field.** The same-file authored head
  (`tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc:93`)
  parses to the typed intrinsic `BacklogDrainExpr` and reaches
  `orchestrator/workflow_lisp/lowering/phase_drain.py:213`, which raises
  `AttributeError: 'BacklogDrainSpec' object has no attribute
  'preserve_owner_boundary'` — the owner-boundary gate reads a field that
  does not exist on `BacklogDrainSpec`
  (`orchestrator/workflow_lisp/drain_stdlib.py:13`).
- **Route rejection.** Other fixtures fail with
  `[wcc_lowering_route_unsupported] WCC M4 lowering supports only the bounded
  loop preview subset; ... uses unsupported `BacklogDrainExpr`` — the
  promoted route refuses the intrinsic outright.
- **Parent-inlined loop at runtime.** The imported shape
  (`drain_stdlib_backlog_drain_parent_terminal_reprojection.orc` imports
  `backlog-drain` from `std/drain`) expands the stdlib `defmacro`
  (`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc:241`) inline, so
  the parent owns the loop; every runtime execute proof
  (`test_parent_terminal_reprojection_executes_projected_parent_outputs`,
  `test_branch_local_terminal_contract_alignment_executes_parent_outputs_without_public_blocker_class`,
  `test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects`)
  fails at the macro-expanded
  `...__%macro__backlog-drain__m0001__terminal__loop` step (EMPTY-first
  parametrizations now fail with exit code 1; the sibling recorded
  loop-entering exit code 2 the same day — the runtime redness has widened on
  the shared tree since that record).

The emission mechanism largely exists but is unreachable on the promoted
route: `_ensure_callable_backlog_drain_workflow`
(`orchestrator/workflow_lisp/lowering/phase_drain.py:304`) synthesizes the
shared child (params `(ctx <DrainCtx-like>)`, return `DrainResult`-typed),
registers it in the workflow catalog, and carries specialization identity
(`_callable_backlog_drain_specialization_key`, digest-suffixed
`std/drain::backlog-drain__<sha1[:12]>` names, span/form-path-insensitive
identity). The shared terminal lane emission (terminal carrier step,
`std/drain::backlog-drain__normalize_result`, `MarkSelectorBlocked`,
`shared_drain_result` transition/summary/result ordering) also exists in
`phase_drain.py` (from line 1547/1838). The gate at `phase_drain.py:213`
additionally requires `lowering_schema_version not in (None, 1)`, so the
legacy schema-1 route is already excluded by design. The checked-in stdlib
lowering contract row
(`orchestrator/workflow_lisp/stdlib_contracts.py`,
`STDLIB_LOWERING_CONTRACTS_BY_FORM["backlog-drain"]`) already matches the
inventory the proofs assert (`resource_finalize_drain`,
backend kinds `("workflow_call", "runtime_native")`, required statement
families, source-map expectations, primary diagnostics
`backlog_drain_contract_invalid` / `workflow_call_signature_erased`).

`std/drain.orc` currently has no `consume-drain-terminal-effects` procedure;
`test_backlog_drain_target_contract_separates_terminal_value_from_effect_consumers`
pins the split (and pins `finalize-drain-terminal`'s section free of
`resource-transition`/`materialize-view`).

One negative drifted with the missing mechanism:
`test_compile_stage3_module_rejects_hidden_compatibility_bridge_public_run_item_fixture`
now reports DID NOT RAISE — the hidden-bridge contract it proves is enforced
on the intrinsic route this gap restores.

### Revision note: public run-state review expectation routed out

A later implementation review expected a `SELECTED -> CONTINUE -> EMPTY`
runtime scenario to preserve a progressed public `DrainResult.run-state`.
That expectation is not satisfiable inside this gap without changing the
approved boundary: the baseline `DrainResult` shape is carrier-free, the
shared owner-lane ledger forbids compatibility-bundle rereads and routes
remaining `run_state_path` needs to carrier-removal prerequisites, and the
callable-child boundary exposes only declared return fields. This architecture
therefore treats any requirement to preserve or reconstruct progressed public
`return__run-state` as a separate carrier-retirement prerequisite, not as a
runtime acceptance condition for callable-child owner-boundary emission.

### Classification of failing pre-existing checks

- **Live contract this gap satisfies:** every red check in
  `tests/test_workflow_lisp_drain_stdlib.py` whose fresh cause is one of the
  five forms above. They pin the partially-landed owner-boundary shape
  (child emission, promoted-callable head, spec field, WCC admission,
  terminal-effects split, specialization identity, gap-payload record-leaf
  carriage, hidden-binding metadata, negative diagnostics). The sibling
  architecture explicitly classified this class as this lane's contract.
- **Live contract owned elsewhere, consumed as constraint:** the committed
  carrier-free `expected_outputs` and carrier-rejection parametrizations
  (R40 baseline), the fixed callable-boundary field-set validation in
  `orchestrator/workflow_lisp/typecheck_calls.py` /
  `typecheck_dispatch.py`, and the sibling's landed Blocker A/B1/C baselines.
  This gap builds on them unchanged.
- **Red surfaces routed out:** the Section-14 CLI compile and family parent
  smoke (expected red on out-of-lane `std/phase`/`plan_phase` type-resolution
  drift; they are downstream verification, not this gap's gates);
  fixture-mirror desync and retired-carrier fixture construction (routes to
  `workflow-lisp-design-delta-compatibility-carrier-retirement`);
  reference-family conformance live-run evidence binding (routes per the
  sibling's residual-failure routing); gap re-entry convergence (ledger
  Section 2.4, family-owned, separate).

## Ownership

`orchestrator/workflow_lisp/drain_stdlib.py` owns `BacklogDrainSpec`. It
gains the `preserve_owner_boundary` authored-spec field. The field is
frontend-local authored data: parser and macro/head resolution set it,
lowering reads it, and nothing else may key behavior on it.

`orchestrator/workflow_lisp/lowering/phase_drain.py` owns the drain intrinsic
lowering: the owner-boundary gate, `_ensure_callable_backlog_drain_workflow`,
specialization identity, and the shared terminal-lane emission. Under target
design Section 12.2 step 4 this drain-aware lowering is sanctioned migration
scaffolding for the conversion lane; this gap makes it the working
owner-boundary mechanism on the promoted route. Retiring it in favor of pure
imported-`.orc` composition is conversion-lane completion, not this gap.

`orchestrator/workflow_lisp/wcc/route.py` and
`orchestrator/workflow_lisp/wcc/defunctionalize.py` own promoted-route
admission. They stop rejecting `BacklogDrainExpr` with
`wcc_lowering_route_unsupported` and dispatch it to the drain intrinsic
emission. Admission is keyed by expression type (`BacklogDrainExpr`), never
by workflow, family, or module name. All other unsupported expression types
keep their current rejection.

The parser/head-resolution surface that produces `BacklogDrainExpr`
(`orchestrator/workflow_lisp/parser*.py` around the existing `backlog-drain`
form parsing) owns the two authored heads. `backlog-drain-callable-boundary`
resolves to the same intrinsic with `preserve_owner_boundary` set; plain
`backlog-drain` on the promoted route defaults to the owner-boundary shape
(the pinned default-route proof requires the child with no authored opt-in).

`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` owns the imported
authoring surface: `SelectionResult`/`GapResult`/`DrainResult` declarations
(R40 carrier-free shapes — settled baseline, untouchable here),
`finalize-drain-terminal`, the new `consume-drain-terminal-effects`
procedure, and the `backlog-drain` defmacro. The imported front door must
stop inlining the loop into the parent on the promoted route; whether the
defmacro is retired in favor of intrinsic resolution or reshaped so its
expansion reaches the same owner-boundary emission is an implementation
choice, constrained by: the authored call surface in existing fixtures and
family modules does not change, and both front doors converge on the same
lowered child.

`orchestrator/workflow_lisp/stdlib_contracts.py` owns the checked contract
row; it is already aligned and is authority for the emitted statement
families, diagnostics, and source-map expectations.

`orchestrator/workflow/lowering.py`, `orchestrator/workflow/executor.py`,
and `orchestrator/exec/step_executor.py` may be touched only additively, and
only as far as fresh runtime proof shows a shared-validation-sanctioned
emitted shape lacks generic executable support (the same authorization the
sibling's Blocker B2 states; since that sibling is blocked on this lane,
landing such a generic repair here is permitted — as generic runtime
substrate with layered regression coverage, never keyed to drain, family, or
phase concepts).

Read-only authority, not repair surfaces: `orchestrator/loader.py` shared
validation (including the sanctioned `repeat_until`-body structured-control
allowance), `orchestrator/workflow_lisp/typecheck_calls.py` /
`typecheck_dispatch.py` fixed callable-boundary validation,
`orchestrator/workflow_lisp/contracts.py` workflow-boundary enforcement
(union-valued helper-workflow parameters/returns stay rejected), and the
committed proof fixtures
`tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_parent_terminal_reprojection.orc`
and
`tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_branch_local_terminal_contract_alignment.orc`
with their carrier-free `expected_outputs`.

Versioned run roots under `state/**` and `artifacts/work/**` are
runtime-owned evidence, never hand-editable.

`docs/design/workflow_command_adapter_contract.md` governs every touched
command boundary, adapter row, or runtime-native effect decision in this
slice.

## Contract

### Callable-Child Owner Boundary On The Promoted Route

On the promoted WCC route (default, no route override), a `backlog-drain`
use — imported, same-file, or through the promoted-callable head — lowers
to:

```text
parent workflow
  -> exactly one call step: call std/drain::backlog-drain (typed args from
     the authored spec; call-step id present in the parent origin map)
  -> lowered child workflow std/drain::backlog-drain:
       repeat_until loop owning the typed accumulator (DrainLoopState)
       selector / run-item / gap-drafter workflow calls inside the loop body
       terminal carrier -> normalize_result match over
         EMPTY | COMPLETED | BLOCKED | EXHAUSTED
       per-terminal: result artifacts first, then declared transition and
         summary effects (shared_drain_result lane)
  -> typed DrainResult child-call value return to the parent
```

The parent contains no `repeat_until`. The child's returned value artifacts
(`return__variant` and variant fields) are produced before, and never gated
on, the terminal transition or summary-view steps. `run_state` does not
appear in transition request bindings (R40 baseline). Downstream projection
steps in the parent (`project-parent-drain-result` and the branch-local
alignment shape) consume the child call's artifacts through the ordinary
`root.steps.<call-step>.artifacts.return__*` references the committed proofs
pin.

The value return contract is intentionally carrier-free. Internal loop state
may still contain implementation-private seeded accumulator fields while this
migration scaffold exists, but those fields are not public `DrainResult`
members, not parent-call outputs, and not a binding source for reconstructing a
progressed public run-state. If a review, fixture, or runtime parametrization
expects `return__run-state` preservation, that expectation is stale for this
gap and must be split to the carrier-retirement lane instead of widening the
callable boundary.

### Both Authoring Front Doors, One Emission

- Plain `backlog-drain` (same-file intrinsic parse) and imported
  `std/drain::backlog-drain` produce the owner-boundary lowering by default
  on the promoted route.
- `backlog-drain-callable-boundary` is the explicit promoted-callable head
  the callable-boundary proof fixtures use; it resolves to the same
  intrinsic/spec and the same emission. It is an authored head, not a new
  semantic form: no new statement families, no divergent terminal lane.
- The synthesized child's own body sets `preserve_owner_boundary` off so
  child lowering terminates (the existing `phase_drain.py:348` shape).
- Legacy schema-1 lowering behavior is unchanged (the existing schema guard
  in the gate stays).

### Specialization Identity

Identical specializations (ctx type, return type, resolved selector/run-item/
gap-drafter targets, max-iterations expression — span/form-path-insensitive)
reuse the canonical `std/drain::backlog-drain` child. Distinct
specializations in one compile get digest-suffixed names
(`std/drain::backlog-drain__<digest>`) and must not collide or cross-bind.
The committed isolation/reuse proofs are the contract.

### Fixed Callable Boundaries Stay Fixed

Selector (`DrainCtx -> SelectionResult`), run-item
(`ItemCtx + selection payload -> SelectedItemResult`), and gap-drafter
(`DrainCtx + gap record payload -> GapResult`) call shapes are unchanged.
Gap payloads cross the boundary by declared record-leaf binding (ledger
Section 2.3.1 carriage, already pinned by the rich-gap-payload proof);
non-record gap payloads keep failing with the pinned diagnostic. Hidden
private-context binding metadata for the entry ctx
(`imported_adapter_carried_context`, generated input names and roles) is
preserved exactly as the hidden-binding proof pins.

### Terminal Responsibility Split (ledger 2.1.1)

`std/drain.orc` separates lanes: `finalize-drain-terminal` performs pure
terminal classification (no `resource-transition`, no `materialize-view` in
its section); `consume-drain-terminal-effects` owns the declared effect lane.
The lowered shared terminal lane keeps `record-drain-outcome`-class
transitions and progress-summary views as declared effects ordered after the
result artifacts. No helper, publication, summary file, or run-state-file
mutation is a prerequisite for returning `DrainResult`.

### Provenance

Every generated child step id appears in the child's origin map with an
`origin_key`; the parent call step and every projection/case step appear in
the parent's origin map. Source maps must let a runtime failure in the child
diagnose back to the authored `backlog-drain` form, and selector/run-item/
gap-drafter failures diagnose the authored call boundary, not a generated
branch name.

### Runtime Value Return (ledger 2.1 minimum behavior check)

The callable-child route executes to all four terminals through ordinary
child-call value return: empty, completed, blocked (selector-blocked and
item-blocked), and exhausted — the committed
`test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects`
parametrizations and the reprojection/branch-local execute proofs. Where a
loop-body step shape that shared validation already sanctions fails to
execute, the repair is the generic lowering emission or additive generic
executor substrate (see Ownership); the sanctioned validation depth itself
must not be extended, and no repair may be keyed to drain, family, or phase
concepts.

The runtime proof checks terminal variant and declared non-carrier fields
through ordinary child-call artifacts. It must not require selector,
run-item, or gap-drafter payloads to carry undeclared run-state fields forward
as public `DrainResult` output, and it must not reread raw command bundles to
recover fields stripped by declared result validation.

## Rule For Outside Uses

The changed surfaces serve consumers beyond this gap's fixtures:

- `BacklogDrainSpec` is constructed by the parser and read by typecheck and
  lowering. The new field is authored-lowering routing data only: no
  consumer may branch on it for family-specific behavior, and no consumer
  outside parser/head-resolution may set it.
- WCC-route admission of `BacklogDrainExpr` applies to every module on the
  route. No module may depend on the former `wcc_lowering_route_unsupported`
  rejection; the admission must not open other unsupported expression types.
- The generated `std/drain::backlog-drain` child is an ordinary lowered
  workflow: shared validation, boundary projection, census, executable-IR
  validation, and the executor treat it with no name-keyed exemptions.
  Consumers enumerating `lowered_workflows` or `validated_bundles` must
  tolerate its presence (and digest-suffixed specializations) as ordinary
  entries.
- `std/drain.orc` exports serve every composing family, fixture, and test
  module: `SelectionResult`/`GapResult`/`DrainResult` value shapes do not
  change; `finalize-drain-terminal` callers keep a pure value result;
  families must not call `consume-drain-terminal-effects` as a value-return
  prerequisite — it is a declared-effect consumer only.
- Consumers must treat any generated run-state accumulator artifacts as
  private migration scaffolding. They may not assert public
  `return__run-state` preservation, use seeded run-state values as semantic
  parent results, or depend on undeclared command-result fields dropped by
  callable-boundary validation.
- Families still consuming the parent-inlined macro expansion (if any exist
  outside the fixtures) converge on the child owner boundary implicitly; they
  must not pin generated `%macro__backlog-drain__*` step names, and any such
  pin found is stale coverage to update, not a compatibility obligation.

## Command Adapter And Runtime-Native Policy

No new command adapter, inline Python/shell, stdout protocol, report
parsing, pointer authority, or ad hoc JSON rewrite may be introduced for
child emission, terminal normalization, or value return.
`record-drain-outcome`-class transitions keep their declared runtime-native
backend; test fake-command scripts remain verification vehicles bound
through declared command boundaries per
`docs/design/workflow_command_adapter_contract.md`. Any touched
command-boundary row keeps its declared contract; no `retirement_status`
changes ride this slice.

## Allowed Shapes

- Landing `preserve_owner_boundary` on `BacklogDrainSpec` with parser/head
  defaults that make the owner boundary the promoted-route default, and the
  synthesized child the only off-switch.
- Admitting `BacklogDrainExpr` on the WCC M4 route by expression-type
  dispatch into the existing `phase_drain.py` owner-boundary emission,
  reusing `_ensure_callable_backlog_drain_workflow`, the specialization
  identity, and the shared terminal lane as-is or minimally repaired to
  match the pinned step shapes.
- Resolving `backlog-drain-callable-boundary` as an authored head onto the
  same intrinsic; retiring or bypassing the `std/drain.orc` defmacro's
  parent-inline expansion on the promoted route so the imported front door
  reaches the same emission — without changing the authored call surface.
- Adding `consume-drain-terminal-effects` to `std/drain.orc` and moving
  effect forms out of `finalize-drain-terminal`'s section, keeping
  `DrainResult` value shapes identical.
- Repairing the generic loop-body lowering emission, or additively closing a
  runtime-proven generic executor support gap for a sanctioned shape, with
  layered regression coverage and no drain/family/phase keying.
- Aligning drain-stdlib negative expectations only where the restored
  intrinsic contract changes the firing diagnostic back to the intended one,
  with a contract-level rationale per changed assertion.
- Splitting or revising stale runtime/review assertions that require a
  progressed public `DrainResult.run-state`, provided the revised proof still
  checks carrier-free terminal value return and routes the carrier expectation
  to the prerequisite lane named below.

## Forbidden Shapes

- Manufacturing the lowered child through family-local wrapper workflows,
  same-file-only special cases, compiler-name allowlists, compatibility
  bundle rereads, or compatibility-only marker steps (ledger 2.1's explicit
  exclusions).
- Weakening, deleting, or re-pointing the five child-owner-boundary
  structural/provenance proofs, the committed carrier-free
  `expected_outputs`, the carrier-rejection parametrizations, or any guard
  lane to reach green.
- Making `record-drain-outcome`, publication, summary materialization, or
  any run-state-file mutation a prerequisite for returning `DrainResult`;
  reintroducing `EmitDrain*`-style caller-owned terminal normalization or
  handwritten parent fan-in.
- Re-adding `run-state` (or any state-root/checkpoint/generated-path
  carrier) to callable-result variants, transition request bindings, parent
  public unions, or fixed callable boundaries; widening
  selector/`run-item`/`gap-drafter` shapes or the imported `gap-drafter`
  arity.
- Satisfying review feedback by preserving progressed public
  `DrainResult.run-state`, rereading undeclared raw command bundles after
  callable-boundary validation, or treating the child's seeded accumulator
  run-state as a public terminal result.
- New workflow boundaries whose parameters or returns carry `GapResult`,
  `SelectedItemResult`, or nested terminal unions (the Stage 3
  workflow-boundary contract stays authority); exposing the child's private
  ctx binding as public authored input.
- Extending the sanctioned structured-control nesting depth, disabling
  `validate_shared`, admitting shapes lowering or the executor cannot run,
  or compatibility normalization that accepts unknown variant fields on
  promoted routes.
- Any compiler branch keyed to family names or Design Delta concepts beyond
  the sanctioned drain intrinsic itself; and any expansion of that intrinsic
  into new drain-aware semantics not pinned by the committed proofs.
- Reverting or re-litigating the sibling's landed Blocker A resolution,
  Blocker B1 flattening, Blocker C fixture repair, or the R40 carrier
  retirement.
- Hand-editing run-state/artifact evidence; treating rendered summaries,
  reports, pointer files, stdout, or debug YAML as semantic authority;
  claiming YAML-primary promotion from compile/smoke success.

## Source Surfaces

- `orchestrator/workflow_lisp/drain_stdlib.py` (`BacklogDrainSpec` field)
- `orchestrator/workflow_lisp/lowering/phase_drain.py` (owner-boundary gate,
  child emission, shared terminal lane; repairs only to match pinned shapes)
- `orchestrator/workflow_lisp/wcc/route.py`,
  `orchestrator/workflow_lisp/wcc/defunctionalize.py` (intrinsic admission
  and dispatch on the promoted route)
- `orchestrator/workflow_lisp/parser*.py` head resolution for
  `backlog-drain` / `backlog-drain-callable-boundary`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` (front-door
  convergence; `consume-drain-terminal-effects` split; value shapes frozen)
- `orchestrator/workflow_lisp/stdlib_contracts.py` (already-aligned contract
  row — verify, do not weaken)
- `orchestrator/workflow_lisp/lowering/control_loops.py`,
  `orchestrator/workflow_lisp/lowering/control_match.py` (only if runtime
  proof shows the emitted loop-body shape needs generic repair)
- `orchestrator/workflow/lowering.py`, `orchestrator/workflow/executor.py`,
  `orchestrator/exec/step_executor.py` (additive generic substrate only,
  runtime-proof-gated)
- `tests/test_workflow_lisp_drain_stdlib.py` and
  `tests/fixtures/workflow_lisp/valid|invalid/*backlog_drain*` (verification
  vehicles; committed proof shapes are authority)

## Acceptance Conditions

All with fresh command output on the current checkout:

- The five child-owner-boundary structural/provenance proofs pass:
  `test_same_file_callable_boundary_preserves_generated_backlog_drain_owner_lane`,
  `test_compile_stage3_module_preserves_parent_terminal_reprojection_over_imported_backlog_drain`,
  `test_parent_terminal_reprojection_preserves_imported_call_and_projection_provenance`,
  `test_compile_stage3_module_preserves_branch_local_terminal_contract_alignment_over_imported_backlog_drain`,
  `test_branch_local_terminal_contract_alignment_preserves_imported_call_and_projection_provenance`.
- The promoted-route mechanics proofs pass:
  `test_compile_stage3_module_preserves_imported_backlog_drain_as_callable_boundary`,
  `test_callable_boundary_bundle_preserves_entry_ctx_hidden_binding_metadata`,
  `test_backlog_drain_target_contract_routes_default_imported_surface_through_callable_child`,
  `test_compile_stage3_module_keeps_callable_backlog_drain_specializations_isolated`,
  `test_compile_stage3_module_reuses_canonical_callable_backlog_drain_for_identical_specializations`,
  `test_compile_stage3_module_carries_rich_gap_payload_across_callable_boundary`,
  `test_callable_backlog_drain_keeps_gap_drafter_boundary_narrow`,
  `test_compile_stage3_module_supports_record_gap_drafter_returns`,
  `test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload` (on
  its intended `workflow_call_signature_erased` diagnostic),
  `test_workflow_ref_resolution_allows_imported_family_owned_selection_result_empty_without_run_state`,
  `test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator`,
  `test_backlog_drain_contract_inventory_matches_promoted_stdlib_route`,
  `test_backlog_drain_target_contract_separates_terminal_value_from_effect_consumers`,
  `test_lowering_backlog_drain_pins_selector_blocked_compatibility_blocker_class`,
  and
  `test_compile_stage3_module_rejects_hidden_compatibility_bridge_public_run_item_fixture`
  (raising again on the hidden-bridge contract).
- The runtime value-return proofs pass on every parametrization:
  `test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects`,
  `test_parent_terminal_reprojection_executes_projected_parent_outputs`, and
  `test_branch_local_terminal_contract_alignment_executes_parent_outputs_without_public_blocker_class`,
  with no parent output including `return__run-state` (ledger 2.1 behavior
  check; ledger 2.2/2.2.1 boundary behavior). If any named proof still
  contains the stale progressed-public-run-state expectation, implementation
  must split or revise that assertion before using the proof as an acceptance
  gate; it must not repair the test by widening `DrainResult` or by recovering
  stripped bundle fields.
- `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q` passes as a
  module; any residual failure is classified fresh and routed per
  `Residual Failure Routing` only if its cause is demonstrably outside this
  contract (it must not be one of the five evidence forms above).
- Guard lanes stay green: `tests/test_workflow_lisp_wcc_m4.py -q`
  (including the imported-procedure owner-module call guard),
  `tests/test_workflow_lisp_value_flow_census.py
  tests/test_workflow_lisp_resume_plumbing_retirement.py -q`,
  `tests/test_workflow_lisp_resource_stdlib.py -q`, and
  `tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q`.
  `tests/test_workflow_lisp_reference_family_conformance.py -q` is no worse
  than the pre-existing live-run evidence-binding redness the sibling
  recorded; new failures in that lane are this slice's regression.
- No callable-result union, fixed callable boundary, shared-validation rule,
  or gate was widened, weakened, or special-cased; no compiler change names
  family concepts beyond the sanctioned drain intrinsic; every changed test
  or fixture expectation carries a contract-level rationale.
- Downstream verification (classification, not this gap's gate): the
  sibling's four child-dependent proofs are the same tests as above and go
  green with them; the Section-14 CLI compile of
  `lisp_frontend_design_delta/drain::drain` and the parent smoke either go
  green or remain red only on out-of-lane `std/phase`/`plan_phase`
  type-resolution drift, recorded and routed — a fresh failure there caused
  by a surface this slice touched is this slice's regression.

## Residual Failure Routing

- `std/phase`/plan-phase type-resolution drift on the Section-14 compile or
  family smoke:
  `workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen`.
- Fixture-mirror desync and retired-carrier fixture construction:
  `workflow-lisp-design-delta-compatibility-carrier-retirement` (its deferred
  fixture-sync task).
- Reference-family conformance live-run evidence binding: the
  conformance-gate evidence-binding class per the sibling's routing; never
  by weakening the gate or editing run state.
- Gap re-entry convergence (selector reselecting a drafted gap): ledger
  Section 2.4, family-owned, separate prerequisite.
- Deeper `DrainResult`/`DrainLoopState`/transition run-state retirement and
  the gap-continue run-state carrier: the carrier-retirement lanes; this
  slice must not touch those payload shapes.
- Any review or runtime expectation that a progressed public
  `DrainResult.run-state` / `return__run-state` survives the callable-child
  boundary: route to the carrier-retirement lanes, not to owner-boundary
  emission.
- Loop-body runtime execution failures that persist in shapes this slice did
  not emit or touch: the sibling's Blocker B2 contract governs; coordinate,
  do not double-implement.
