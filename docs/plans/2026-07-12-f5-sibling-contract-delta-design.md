# F5 Sibling Contract-Delta Design

## Metadata

- **Status:** accepted
- **Kind:** clarification
- **Owner:** Workflow Lisp maintainers
- **Reviewers:** drain-roadmap implementation and contract reviewers
- **Created:** 2026-07-12
- **Last material update:** 2026-07-12
- **Related docs / plans:**
  - `docs/plans/2026-07-07-drain-migration-g8-retirement.md`
  - `docs/design/workflow_language_design_principles.md`
  - `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  - `docs/design/workflow_lisp_stdlib_lowering.md`
- **Implementation target:** route-readiness data and dedicated stdlib
  runtime-proof tests only

## Summary

The `backlog-drain` authoring surface is library-provided through ordinary
imported stdlib composition. Its procedure body is specialized and lowered
inline into the owning workflow; it is not represented as a generated
`std/drain::backlog-drain` child workflow. This design aligns two stale evidence
surfaces with that generic route while preserving the proof obligations those
surfaces were created to enforce.

The implementation is intentionally limited to adding the omitted promoted-hook
fixture to the route-readiness registry and re-expressing four runtime-proof
tests against the parent-owned inline route. It does not change compiler,
validator, runtime, stdlib, workflow, fixture, or frozen migration behavior.

## Context And Authority

The governing drain plan selects this work as the F5 sibling contract-delta
sweep before Task 1.7. The accepted stdlib-lowering contract says that
`backlog-drain` lowers through ordinary imported stdlib composition and that
the dedicated executable proof remains the
`validation_profile="DEDICATED_RUNTIME_PROOF"` lane. The adapter-retirement
design requires that lane to produce a validated executable bundle without a
compiler or validator branch keyed to `std/drain`, `backlog-drain`, a workflow
family, or a proving fixture.

The workflow-language principles provide the controlling rules:

- frontends lower to shared Core AST, Semantic IR, and executable IR;
- procedures compose behavior while macros supply syntax;
- imported generic composition is preferred over form-specific compiler
  branches;
- source maps, effects, structured validation, and fail-closed negative
  behavior must remain visible; and
- promotion evidence must exercise the real default route rather than a
  fixture-only or compatibility path.

The route-readiness registry is the checked-in data authority for discovered
`.orc` surfaces. Runtime-proof behavior is owned by
`tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`. Neither surface is
authority for compiler behavior; both characterize and verify behavior defined
by the governing designs and the shared compiler/runtime pipeline.

## Problem

Two evidence surfaces still describe the pre-swap drain route.

First, discovery includes
`tests/fixtures/workflow_lisp/valid/design_delta_loop_promoted_hook_phase_ctx.orc`,
but the route-readiness registry has no row for it. Registry validation and its
CLI check therefore fail with `route_readiness_surface_missing` even though the
fixture already has independent feasibility evidence.

Second, four runtime-proof tests assume that compilation emits a child workflow
named `std/drain::backlog-drain` and a parent call to that child. The accepted
generic route instead specializes `backlog-drain-proc` inline into the entry
workflow, where the parent owns the loop, terminal projection, terminal effects,
origin-map lineage, and runtime-proof metadata. Those tests fail before they can
exercise their intended positive and negative proof obligations.

Treating these failures as production defects would reintroduce the retired
child-callable architecture or create special-case compatibility behavior.
Deleting or weakening the tests would discard evidence that the dedicated
runtime-proof lane remains executable and fail-closed. The required change is a
contract-delta re-expression of the same obligations on the generic route.

## Goals And Non-Goals

### Goals

- Give the promoted-hook phase-context fixture one unique, evidence-backed
  route-readiness identity.
- Make the checked-in registry and the route-readiness CLI validate without
  suppressing discovery or changing validation rules.
- Preserve the dedicated runtime-proof lane's positive executable-bundle,
  source-lineage, nested-structure, and command-boundary evidence.
- Preserve the negative guarantee that authored parent-scope fallback refs
  cannot be made valid merely by adding them to compiler-owned allowance
  metadata.
- Assert generic parent-owned inline composition behaviorally, without pinning
  digest-bearing specialization names, list positions, or incidental source
  wording.
- Keep all production and frozen migration surfaces byte-identical.

### Non-Goals

- No compiler, typechecker, lowering, validator, executable-IR, runtime, CLI, or
  stdlib behavior change.
- No edit to the fixture or its existing feasibility test.
- No restoration of `std/drain::backlog-drain` as a child workflow and no new
  form-, module-, workflow-, or fixture-name special case.
- No registry schema, discovery rule, label vocabulary, or migration-target
  change.
- No broad cleanup of runtime-proof helpers, generated identifiers, or metadata.
- No baseline or generated parity-artifact regeneration.
- No roadmap status or live completion claim in this document.

## Decision

Use the narrow data-and-test alignment approach:

1. Add exactly one route-readiness row for the discovered promoted-hook fixture,
   using its path-derived stable identity and its existing feasibility test as
   independent evidence.
2. Retarget the four stale runtime-proof assertions and mutations from the
   removed child workflow to the selected entry workflow's structurally located
   inline drain loop.
3. Preserve each test's semantic obligation while replacing child-call and
   child-name assertions with behavioral assertions about generic inline
   composition, parent-owned source lineage, generated nested-step validation,
   and fail-closed authored refs.

This approach is preferred because it records the route that already owns the
behavior and changes no executable semantics. Its deliberate tradeoff is that
tests must locate the generic route structurally and cannot use the former child
workflow as a convenient mutation boundary.

## Current Generic-Route Contract

For a workflow using imported `backlog-drain` composition:

- the selected entry workflow owns the specialized drain procedure body;
- the entry workflow contains the bounded `repeat_until` loop and the post-loop
  terminal projection/effect steps;
- no lowered workflow named `std/drain::backlog-drain` is required or expected;
- no top-level authored step calls `std/drain::backlog-drain`;
- specialization identities may contain digests and are not a stable public
  identity surface;
- source-map and generated-path lineage attach to the parent-owned inline
  steps;
- compiler-owned runtime-proof nested-step and ref-allowance metadata attach to
  that same lowered parent workflow;
- `DEDICATED_RUNTIME_PROOF` must validate and build an executable entry bundle;
  and
- frontend-only compilation remains non-executable and produces no validated
  entry bundle.

The test contract is therefore structural: select the entry workflow, find its
unique drain `repeat_until` route by shape and provenance, and inspect or mutate
that route. Tests must not derive authority from a digest-bearing generated
name, a fixed step index, or the historical child identity.

## Preserved Proof Obligations

The four runtime-proof test changes must preserve the following obligations.

| Existing intent | Generic-route assertion |
| --- | --- |
| Shared validation keeps generated structured branch handling active. | The selected entry workflow has no child drain call, contains the structurally identified inline drain loop, and validates through the shared route. |
| Dedicated runtime proof records boundary and source lineage. | The dedicated profile produces the executable entry bundle, retains no obsolete child-boundary proxy requirement, and records parent-owned origin/generated-path lineage for the inline loop and its terminal work. |
| Generated nested structured steps are accepted on the sanctioned route. | A generated structured step copied into the actual inline repeat body and declared in compiler-owned nested-step metadata survives `validate_lowered_workflows` under `DEDICATED_RUNTIME_PROOF`. |
| Authored parent-scope fallback refs remain rejected even when metadata lists them. | A fabricated authored fallback ref inserted into the inline repeat body still raises the established fail-closed diagnostic after the same owner/ref pair is added to both allowance collections. |

Tests must continue to cover the existing, already-green obligations for
intrinsic-lowering count zero, executable entry-bundle validation,
frontend-only bundle absence, certified placeholder command boundaries, and
serialized validation-profile values.

## Exact Permitted Scope

Implementation may modify only:

- `docs/workflow_lisp_route_readiness_registry.json`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`

The registry edit is limited to one new surface row and the registry's ordinary
document update date. The test edit is limited to structural helper/assertion
changes required to retarget the four failing tests.

The following are prohibited:

- all files under `orchestrator/`;
- all files under `workflows/`, including `std/drain.orc` and production drain
  callers;
- all files under `tests/fixtures/`;
- `tests/test_workflow_lisp_route_readiness.py`;
- checkpoint-identity baselines, migration-parity reports, family-profile
  targets, frozen manifests, and generated evidence artifacts; and
- unrelated docs or roadmap status edits.

If a failing assertion cannot be made green within the two permitted files
without weakening a proof obligation, implementation must stop and revise this
design rather than expanding scope silently.

## Data And Identity Strategy

The registry row must use:

- `path`:
  `tests/fixtures/workflow_lisp/valid/design_delta_loop_promoted_hook_phase_ctx.orc`
- `surface_id`:
  `tests.fixtures.workflow_lisp.valid.design_delta_loop_promoted_hook_phase_ctx`
- `surface_kind`: `test_fixture`
- `copy_safety`: `test_evidence_only`
- `route_label`: `wcc_default`
- `lowering_route`: `wcc_m4`
- `lowering_schema_version`: `2`
- `readiness_label`: `leaf_compile_candidate`
- `evidence`:
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs`

This mirrors adjacent proc-ref fixture rows and cites a test that compiles the
fixture through the real linked route and asserts its promoted hook behavior.
The registry's own validation test is not admissible evidence.

Runtime-proof tests must treat `ENTRY_WORKFLOW_NAME` as the stable workflow
identity. Generated specialization names are opaque. A helper may traverse the
authored mapping to find the unique `repeat_until` node and its body by
structure. It must fail clearly when zero or multiple candidate loops exist;
silently choosing a list index would convert route drift into false evidence.
Assertions over origin maps should use semantic markers and source/provenance
relationships, not full generated IDs or digest fragments.

## Invariants And Failure Modes

### Invariants

- The generic route remains name-neutral and uses no drain-specific production
  branch.
- The route-readiness registry has one row per discovered path and one unique
  `surface_id` per row.
- Evidence for the new row is independent of registry self-validation.
- Dedicated runtime proof validates the real entry bundle through shared
  validation and executable-IR validation.
- Compiler-owned metadata may authorize compiler-generated nested structure;
  it may not authorize an authored invalid ref.
- Frontend-only evidence remains non-executable.
- Test mutations operate on a deep copy and do not modify the source fixture or
  shared compiler state.
- No assertion requires the removed child workflow or an intrinsic lowering
  count greater than zero.

### Failure Modes

- **Missing or duplicate registry identity:** registry validation fails with its
  existing stable diagnostic; do not suppress discovery or relax uniqueness.
- **No or multiple inline loop candidates:** the test helper fails explicitly,
  exposing route-shape drift.
- **Source lineage missing:** the dedicated-profile test fails; do not replace
  lineage evidence with generated-name equality.
- **Generated nested mutation rejected:** stop and investigate whether the
  mutation is actually marked compiler-generated on the owning parent route;
  do not add a production exception.
- **Authored fallback mutation accepted:** treat as a proof-boundary regression;
  do not weaken the negative assertion or broaden metadata authority.
- **Production edit appears necessary:** stop and revise the design because the
  work is no longer a contract-only sibling sweep.

## Security, Operations, And Performance

There is no new authority, credential, external I/O, runtime state, or
deployment behavior. The registry gains one data row and tests traverse a small
in-memory authored mapping. Structural traversal must be bounded by that tree
and introduces no material runtime or test-performance cost.

## Evidence And Implementation Boundaries

The real evidence path is:

```text
fixture source
  -> imported stdlib macro/procedure composition
  -> parent-owned specialized Core AST / lowered mapping
  -> shared validation
  -> DEDICATED_RUNTIME_PROOF executable entry bundle
```

The registry is declarative inventory, not proof that compilation succeeds.
Its row must cite the existing feasibility test. The frontend-only profile is a
negative control, not executable evidence. Mutated lowered mappings are focused
validator probes, not alternate compiler implementations. They are valid only
when based on the real parent-owned lowered route produced by the compiler.

Review must confirm that no helper synthesizes a replacement child workflow,
no test bypasses `compile_stage3_entrypoint`, and no assertion merely checks a
fixture string. The positive and negative mutations must both pass through
`validate_lowered_workflows` with the dedicated profile.

## Compatibility And Migration

There is no user-facing or runtime compatibility change. The registry addition
records an already-discovered test fixture. The runtime-proof changes migrate
evidence from the retired child-callable representation to the accepted inline
representation while retaining the original validation boundaries.

Rollback is a revert of the two implementation-file edits. A rollback would
restore stale evidence failures but would not change production behavior.

## TDD And Verification Strategy

Implementation begins by recording the six existing failures by full test
identity:

- two route-readiness failures caused by the one missing registry row; and
- four runtime-proof failures caused by child-callable assumptions.

Then apply the changes in two small cycles:

1. Add the single registry row and require both route-readiness tests to turn
   green. Run the existing feasibility evidence test named by the row.
2. Retarget one runtime-proof obligation at a time, requiring each failing test
   to turn green without changing its semantic assertion. Run the full
   runtime-proof module after each coherent mutation-helper change.

Required fresh checks from the repository root:

```bash
pytest tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs -q
pytest tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_parent_drain_census_alignment.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py -q
pytest tests/test_workflow_lisp_checkpoint_identity.py -q
pytest tests/test_workflow_lisp_composition.py \
  tests/test_workflow_lisp_procedures.py -q
```

After narrow selectors, the broad suite must run in tmux using the repository
policy command:

```bash
pytest -q -n 16 --dist=worksteal
```

The expected contract delta is exactly six previously failing tests becoming
green, with no production diff and no new failure identity. Any unrelated
pre-existing broad-suite failures must be compared by full identity against a
fresh pre-change baseline; they must not be weakened or silently accepted.

## Declarative Acceptance / Integration Scenarios

### Registry scenario

Given the checked-in registry and repository discovery rules, invoking
`python -m orchestrator workflow-lisp-route-readiness --registry
docs/workflow_lisp_route_readiness_registry.json --check` returns success, reports
no missing required surface, and includes the promoted-hook fixture exactly
once. The fixture's cited feasibility test independently compiles the real
linked route and observes a promoted hook bundle with the required phase-context
bridge inputs.

### Positive runtime-proof scenario

Given the stdlib drain fixture and the dedicated validation profile,
`compile_stage3_entrypoint` returns a validated executable bundle for the entry
workflow. The parent mapping owns the inline repeat and terminal route, no
child drain call is present, compiler-generated nested structure is accepted,
and origin/source metadata remains attached to the inline route. The compiler
records zero intrinsic `backlog-drain` lowerings.

### Negative runtime-proof scenario

Given the compiler-produced parent mapping, a test inserts an authored
parent-scope fallback ref into the inline repeat body and also places the
owner/ref pair in both runtime-proof allowance collections. Dedicated shared
validation still rejects the mapping with the established boundary diagnostic.
No metadata-only escape hatch converts authored invalid state into valid
generated structure.

## Alternatives And Rationale

### Restore the child-callable lowering shape

Rejected. It would reverse the accepted generic-procedure migration, restore an
obsolete ownership boundary, and require production changes solely to satisfy
stale tests.

### Add compatibility aliases or drain-specific validator exceptions

Rejected. This would hide the contract delta behind name-specific machinery,
contradict the generic-route and name-neutrality requirements, and make G8
retirement evidence less trustworthy.

### Delete the four stale runtime-proof tests

Rejected. Their child identity is obsolete, but their executable-boundary,
source-lineage, generated-structure, and fail-closed-ref obligations remain
required.

### Regenerate the registry mechanically or broaden its schema

Rejected for this bounded change. Discovery identifies one omitted surface and
an adjacent-row pattern supplies its classification. Whole-file regeneration or
schema work would enlarge the review surface without improving the contract.

## Success Criteria

- Only the two permitted implementation files change.
- The new registry row exactly matches the data/identity contract above and
  cites independent evidence.
- The two route-readiness and four runtime-proof failures turn green.
- All preserved proof obligations remain explicit and behavioral.
- The fixture evidence, four-suite drain gate, checkpoint-identity canary, and
  composition/procedure canaries pass fresh.
- The broad worksteal suite introduces no new failure identity.
- Review confirms zero production, stdlib, fixture, frozen-manifest, baseline,
  or generated-artifact changes.

## Stop / Revise Criteria

Revise this design if any of the following occurs:

- a production or frozen-surface edit is required;
- the inline route cannot be selected structurally without a drain-specific
  compiler change or a digest-pinned test;
- the negative authored-ref obligation cannot be preserved;
- the dedicated profile cannot build and validate the entry bundle;
- the registry row needs a new label or schema meaning; or
- broad verification finds a new failure attributable to the contract delta.

## Documentation Impact

This design is the durable implementation handoff. No author-facing guide,
normative spec, capability-status row, or roadmap status changes are required
because the accepted generic-route behavior is unchanged. Live execution status
belongs in the governing roadmap ledger or SDD evidence record, not here.

## Implementation Handoff

1. Capture the six-test failing baseline by full identity.
2. Edit only `docs/workflow_lisp_route_readiness_registry.json`; add the exact
   row specified above and run registry plus cited-evidence checks.
3. Edit only `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`; replace
   child-workflow selection with a fail-closed structural selector for the
   parent-owned inline repeat.
4. Retarget each of the four stale tests while preserving the obligation table.
5. Run the narrow, drain integration, canary, and broad worksteal gates.
6. Review the diff for prohibited paths, digest-pinned identities, fixed list
   indexes, weakened diagnostics, or metadata treated as semantic authority.

No implementation step may infer a production change from a test failure. Such
a finding returns the work to design review.
