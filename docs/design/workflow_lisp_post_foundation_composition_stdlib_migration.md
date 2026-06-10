# Workflow Lisp Post-Foundation Composition And Stdlib Migration

Status: draft design
Kind: architecture decision / migration target design
Created: 2026-06-08
Updated: 2026-06-10
Scope: post-foundation Workflow Lisp composition: nested structured control,
typed result translation, imported/std `.orc` reuse, `review-revise-loop`
first-class composition, private executable context, typed projection,
certified adapter/resource-transition ownership, entrypoint
bootstrap/defaults, canonical `resume-or-start` validation, parent-callable
workflow-family migration, and promotion evidence.

Authority:

- `docs/design/workflow_lisp_runtime_migration_foundation.md` is the hard
  prerequisite for this document.
- Normative DSL/runtime behavior remains in `specs/`.
- `docs/design/workflow_lisp_frontend_specification.md` remains the umbrella
  Workflow Lisp frontend contract.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` is the accepted
  compiler architecture for Tranche 1 nested structured-control composition.
- `docs/design/workflow_lisp_state_layout.md` owns state/path layout
  principles and context-derived path namespaces.
- `docs/design/workflow_command_adapter_contract.md` owns adapter
  certification, legacy glue classification, and lint policy.
- This document does not by itself promote any `.orc` workflow to primary
  surface.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`

## 1. Purpose

This document defines the next Workflow Lisp target after the runtime migration
foundation is complete. The foundation target hardens five lower-level
authority seams:

1. command structured-output conformance;
2. frontend-lowered typed value transport;
3. provider structured-output target binding;
4. machine-readable migration promotion gates; and
5. centralized generated state/path allocation.

This document starts after those seams are reliable. Its job is to make
higher-level `.orc` composition and stdlib reuse implementation-ready without
recreating compiler-special forms, hidden command glue, YAML-shaped public
boundaries, or parent workflows that merely wrap legacy state files.

The immediate diagnostic input is the Design Delta Drain `.orc` migration
findings report
(`docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`).
That report shows that the migration is not blocked by Lisp syntax. It is
blocked by first-class workflow composition:

- nested structured control must survive lowering and shared validation;
- stdlib workflows such as `review-revise-loop` must compose inside branches
  and reusable calls;
- union result translation must not force outer domain types to mirror inner
  control-state names;
- high-level `.orc` boundaries need private runtime context instead of public
  generated `state/` path inputs;
- deterministic publication and selector bundle helpers need typed projection
  or certified adapter contracts;
- run-state and recovery updates need declared resource-transition authority;
  and
- migration evidence must distinguish leaf compile success from
  parent-callable family parity.

YAML remains authoritative for a workflow family until strict migration parity
computes non-regressive evidence for the complete family and promotion
eligibility is proven by the gate.

## 2. Executive Decision

After `workflow_lisp_runtime_migration_foundation.md` is accepted and its
verification evidence passes, implement the next tranche as an issue-driven
composition and parent-callability hardening pass. Do not start by writing a
parent `.orc` wrapper around the existing YAML state choreography. First
complete the language/runtime surfaces that make the leaf candidates
parent-callable.

Implement the work in these ordered tranches:

- Tranche 0: current-state inventory, issue map, and readiness labels.
- Tranche 1 (P0): nested structured-control composition and generic effectful
  normalization on the accepted WCC middle-end route.
- Tranche 2 (P1): union-result normalization and variant-scoped output
  identity.
- Tranche 3 (P0): private executable context bridge, entrypoint bootstrap,
  defaults, and hidden reusable-call binding.
- Tranche 3A (P0 prerequisite within Tranche 3): parent-callable phase-family
  boundary rehabilitation for plan, implementation, and work-item surfaces.
- Tranche 4: imported/std `.orc` reuse and `review-revise-loop` first-class
  composition.
- Tranche 5 (P1): typed projection and selector/bundle materialization.
- Tranche 6 (P0 for family parity): certified adapter declarations and
  resource-transition ownership.
- Tranche 7: work-item and parent backlog-drain composition over typed
  resources.
- Tranche 8: canonical resume/reuse validation and strict parent-callable
  parity evidence.

The P0/P1 labels mirror the priority work items in the findings report. The
three P0 blockers — nested structured control, the private executable context
bridge, and run-state/resource-transition ownership — gate parent-callable
migration for the drain family. Until they land, migrations of that family
must continue as typed leaf candidates plus explicit bridge records, with YAML
remaining primary.

The 2026-06-10 WCC reconciliation changed the compiler-lane baseline. The
nested implementation-phase acceptance fixture now compiles, validates, and
smokes as one parent-callable phase under the WCC route. The remaining
work-item compile blocker has advanced past the old private-workflow and
phase-family boundary diagnostics to the next explicit compiler gap:
`work_item.orc` uses `IfExpr`, which is not yet covered by the WCC M4 route.
That `IfExpr` gap must be drafted before using the work-item or parent drain
as parent-callable parity evidence.

The target success condition is not "more leaves compile." The target success
condition is that at least one real workflow family reaches parent-callable
`.orc` evidence with:

- compile/typecheck/lowering success;
- shared validation success;
- visible provider, command, workflow, resource, state, artifact, and
  projection effects;
- source-map and Semantic IR provenance for generated statements, contexts,
  paths, variants, and adapter/resource effects;
- deterministic `StateLayout` / `PathAllocator` ownership;
- no promoted compiler branch keyed to a stdlib workflow name; and
- strict migration parity with computed `non_regressive=true` and
  `--require-promotable` before YAML-primary replacement.

## 3. Prerequisite Boundary

This document is blocked until the runtime migration foundation has completed
its success criteria:

- command structured-output tests pass for runtime env precedence, parent
  creation, and missing-bundle fail-closed behavior;
- frontend-lowered private scalar, collection, record-like, and nested relpath
  values validate, materialize as views, publish, consume, and render through
  shared runtime contracts;
- provider structured-output target binding exists for `output_bundle.path`
  and `variant_output.path`, wrong-path bundle writes fail closed, and
  provider-session/managed-job wrappers preserve the binding;
- prompt extern source semantics distinguish `asset_file` from `input_file`
  and preserve string shorthand as source-relative assets;
- `migration-parity` has strict gate behavior and schema/version validation;
- `StateLayout` / `PathAllocator` owns the blocking generated path families;
- generated path provenance is present in source maps and Semantic IR;
- compiler-owned `__write_root__...` inputs are not exposed at public workflow
  entrypoints; and
- compatibility proof paths that traverse `resume-or-start` have certified
  validator/writer bindings available through the normal compiler-owned
  command-boundary route.

If any of those remain incomplete, this document may be used for planning, but
it must not be used to justify additional `.orc` primary-promotion work.

The design-delta findings do not reopen the foundation. The private executable
context bridge in this document builds on the foundation's private value
transport and `StateLayout` / `PathAllocator` boundary; it does not redefine
them. Any identity or path-shape changes the bridge needs are routed through
`workflow_lisp_state_layout.md`, not redesigned here.

## 4. Current Evidence And Issue Map

The post-foundation target must start from durable current state, not from
older roadmap phrasing. Before selecting work, the next drain must verify
source, fixtures, tests, parity artifacts, run state, and design-index status
entries. If a row is stale, repair the inventory before implementation.

### 4.1 Durable evidence

The 2026-06-09 design-delta drain migration executed the foundation gate,
domain module, feasibility probes, plan phase, implementation phase, selector,
design-gap architect, work-item leaves, and a parent-drain readiness
assessment against this target. Durable evidence:

- findings report:
  `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`;
- parent-drain blocker record:
  `docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`;
- committed leaf candidates for plan, implementation, selector, design-gap
  architect, and work-item pieces; and
- feasibility test module
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
- blocked prerequisite evidence from the imported-child returned-variant
  recovery:
  `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/blocked-progress-report.md`
  and
  `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/blocked-recovery-decision.json`.

### 4.2 Current status snapshot

| Surface | Current state | Remaining post-foundation work |
| --- | --- | --- |
| Runtime foundation | Implemented in the completed runtime-foundation drain, subject to the prerequisite evidence above | Treat as prerequisite evidence; reopen only if a listed success criterion regresses |
| Design Delta Drain leaf candidates | Leaf candidates compile for plan, implementation pieces, selector, design-gap architect, and work-item pieces | Do not mistake leaf compile evidence for parent-callable parity |
| Parent drain | Intentionally blocked before implementation; blocker record in force | Unblock only after nested composition, private context, typed projection, resource transitions, and parent-callable evidence exist |
| Imported `PhaseCtx` recognition | Fixed frontend bug (F1) from name-local to structural/provenance-aware recognition | Preserve as invariant for future stdlib/context forms; keep regression coverage |
| Generic effectful composition | Implemented for the migrated WCC M0-M5 subset; design-delta implementation-phase parent-callable fixture compiles and smokes through WCC | Continue new compiler-lane work on WCC; do not add a second helper-hoisting route |
| Nested structured control | Implemented for the canonical implementation-phase shape through WCC; still incomplete for non-migrated surface forms such as work-item `IfExpr` (F2) | Draft the WCC `IfExpr` gap before parent-callable work-item/drain parity |
| Union-to-union result translation | Implemented on the WCC route and preserved on the legacy route where required; returned variants, not matched source cases, control target identity (F3) | Keep returned-variant normalization authoritative and finish remaining diagnostic hardening |
| Variant output field identity | Gap, mitigated by verbose variant-specific field naming (F4) | Tranche 2: variant-scoped identity, or an explicit documented restriction |
| Imported/std `.orc` reuse | Partial/implemented for stdlib modules and review-loop route | Verify import expansion, specialization identity, hygienic generated names, effect visibility, source maps, and denylist coverage |
| `review-revise-loop` stdlib route | Composes inside the canonical implementation-phase branch through WCC with compile-time `ProcRef` hooks, loop exhaustion, and typed stdlib unions (F8) | Preserve denylist/source-map/resume evidence and extend only through WCC for new nested shapes |
| Private runtime context | Gap; required lints correctly reject raw `state/` path inputs at high-level `.orc` boundaries, but no private bridge exists for runtime-owned context (F5) | Tranche 3: private executable context bridge and hidden reusable-call binding |
| Phase-family boundary rehabilitation | Partially implemented: implementation-phase parent-callable fixture now clears boundary and nested-control gates; work-item now blocks on WCC `IfExpr` before later private-context/resource gates (F12) | Draft WCC `IfExpr` first, then continue Tranche 3A boundary rehabilitation for remaining plan/work-item surfaces |
| Selector/bundle publication | Selector leaf can model provider decision; publication remains an unclassified script (F7) | Tranche 5: typed projection or certified adapter authority for selection bundle publication |
| Adapter/resource-transition authority | Adapter contract exists; family scripts still encode workflow semantics (F6, F10) | Tranche 6: classify helpers, certify retained adapters, move recurring state/resource transitions to typed runtime effects where justified |
| Migration parity gates | Strict gate hardening implemented in foundation; leaf-versus-family distinction relies on prose labels in migration records (F11) | Tranche 8: parent-callable readiness labels; leaf-only evidence insufficient for promotability |

### 4.3 Findings map

| Finding | Type | Target response | Promotion consequence |
| --- | --- | --- | --- |
| F1 imported `PhaseCtx` recognition | Fixed frontend bug | Preserve structural/capability recognition across module boundaries | Regression blocks stdlib/context promotion |
| F2 nested structured control | P0 frontend/runtime design gap, implemented for the migrated WCC subset | Tranche 1: WCC-owned nested structured-control composition and branch-scope shared validation | Parent implementation phase no longer needs split-leaf workaround; work-item still needs WCC `IfExpr` |
| F3 union-to-union result mapping | P1 lowering bug/design gap, implemented for WCC and preserved for legacy compatibility | Tranche 2: returned variant controls target union normalization; same-target imported-child pass-through is route evidence | Domain result types must not be shaped by inner control names |
| F4 variant output field uniqueness | P1 ergonomics/shared-validation issue | Tranche 2: variant-scoped output field identity; documented restriction is interim mitigation only | Variant-specific field-name workarounds remain compatibility only |
| F5 private context and StateLayout | P0 frontend/runtime design gap | Tranche 3: private executable context bridge and entrypoint bootstrap | Public state roots or fake `PhaseCtx` inputs are not parity evidence |
| F12 parent-callable phase-family boundaries | P0 frontend/runtime design gap, partially implemented | Tranche 3A: parent-callable phase-boundary rehabilitation for plan, implementation, and work-item, including private/helper boundary types and compatibility path labeling | Implementation phase has parent-callable smoke evidence; work-item remains non-parent-callable until WCC `IfExpr` and later private/resource gates land |
| F6 certified adapters and resources | P0 runtime/adapter authority gap | Tranche 6: certified adapter/resource-transition ownership | Hidden state mutation blocks family promotion |
| F7 selector/bundle publication | P1 projection/materialization gap | Tranche 5: typed projection and materialized bundle views | Selector leaves remain non-parity candidates until publication is authoritative |
| F8 review loop first-class composition | P0 stdlib composition gap | Tranches 1 and 4: stdlib review loops compose wherever effectful procedures are valid | Review-loop leaves are insufficient if nested branches fail |
| F9 work-item and parent drain | P0 workflow-family design gap | Tranche 7: typed work-item/backlog-drain model | Parent `.orc` wrapper must not hide YAML-shaped state choreography |
| F10 command adapter ergonomics | P1 authoring ergonomics issue | Tranche 6: typed adapter declaration/call surface | Raw argv plumbing is allowed only as low-level compatibility |
| F11 migration readiness evidence | P1 migration evidence gap | Tranche 8: parent-callable readiness and strict parity labels | `--require-promotable` fails on leaf-only evidence |

## 5. Authority And Dependency Direction

### 5.1 This document consumes

- `workflow_lisp_runtime_migration_foundation.md` owns command output
  authority, private value transport, provider structured-output binding,
  strict promotion gates, and the first generated path allocation boundary.
- `workflow_lisp_frontend_specification.md` owns the baseline Workflow Lisp
  compiler pipeline and the authority rule that `.orc` lowers into the
  existing validated workflow model.
- `workflow_lisp_unified_frontend_design.md` owns future/deferred frontend
  surfaces, including the rule that future features must lower into the
  existing validated model or a separately accepted future runtime contract.
- `workflow_lisp_stdlib_lowering.md` owns the stdlib lowering rule: high-level
  forms should be ordinary `.orc` stdlib code unless accepted as primitives.
- `workflow_lisp_review_revise_stdlib_parametric_integration.md` owns the
  review/revise migration rationale, shape, and historical route.
- `workflow_lisp_state_layout.md` owns context-derived path layout principles
  and the run-isolation invariant for generated private paths.
- `workflow_lisp_runtime_closures_boundary.md` owns the decision to keep
  runtime closures deferred.
- `workflow_command_adapter_contract.md` owns adapter certification, behavior
  classification, and lint policy.
- `workflow_lisp_key_migration_parity_architecture.md` owns promotion evidence
  and family-level parity policy.
- The Design Delta Drain findings report and parent-drain blocker record
  supply the current blocker evidence for nested composition, private context,
  typed projection, resource transitions, and parent-callability.

### 5.2 This document owns

- the post-foundation implementation sequence for Workflow Lisp composition;
- the issue map and current-state inventory required before new
  implementation;
- the acceptance boundary for nested structured-control composition;
- the acceptance boundary for union result normalization and variant-scoped
  output identity;
- the private executable context bridge and hidden reusable-call binding
  target;
- the acceptance boundary for ordinary imported/std `.orc` reuse under nested
  composition;
- the post-foundation target for `review-revise-loop` convergence as a
  first-class reusable workflow abstraction;
- the typed projection target for selector and bundle publication;
- the certified adapter declaration and resource-transition target for
  migration families;
- the work-item/backlog-drain composition target for parent-callable workflow
  families;
- canonical `resume-or-start` validation as used by parent-callable parity;
  and
- the readiness labels that distinguish leaf compile evidence from promotable
  family parity.

### 5.3 This document does not own

- command structured-output runtime rules;
- provider structured-output runtime target binding;
- private typed value transport runtime rules;
- the first `StateLayout` / `PathAllocator` implementation boundary;
- adapter certification policy vocabulary or lint policy details;
- runtime closures or dynamic procedure values;
- a full semantic diff engine;
- broad hard-error linting for all legacy YAML;
- public authored-YAML collection artifact widening;
- arbitrary child-process filesystem sandboxing;
- provider domain correctness; or
- operator explain tooling as a prerequisite for stdlib migration.

## 6. Target Dependency Directions

Nested composition:

```text
authored .orc
-> typed expression / effect tree
-> composition-normalized structured control graph
-> explicit scopes, proof tokens, effect summaries, source-map frames
-> Core AST / executable IR projection
-> shared validation with scope-aware refs
-> existing runtime
```

Imported/std reuse:

```text
authored .orc
-> ordinary import resolution
-> hygienic imported-body cloning
-> compile-time specialization / ProcRef substitution
-> re-typecheck
-> generic effectful normalization
-> shared validation
-> runtime artifacts with no ProcRef/provider/prompt/type leakage
```

Private executable context:

```text
public .orc entry boundary
-> runtime-owned bootstrap request
-> PrivateExecCtx from RunCtx / PhaseCtx / ItemCtx / DrainCtx / StateLayout
-> hidden internal call bindings
-> executable/runtime contract
-> source-map and Semantic IR explanation
```

Typed projection and resource transitions:

```text
validated typed provider/command/workflow state
-> typed projection or certified adapter declaration
-> declared artifact/resource effects
-> StateLayout/path-safe materialized views when needed
-> source-mapped state/artifact/resource versions
```

Migration promotion:

```text
candidate family manifest
-> compile/shared-validation/runtime evidence
-> parent-callable readiness evidence
-> output/terminal/artifact/resume/resource parity
-> schema-validated migration-parity report
-> computed non_regressive
-> --require-promotable before primary-surface replacement
```

## 7. Prohibited Dependency Directions

Nested composition anti-pattern:

```text
authored .orc
-> compiler recognizes one high-level form by literal name
-> hidden Python lowerer hand-builds branch/loop steps
-> branch-local refs appear without scope metadata
-> shared validation is patched around the generated shape
```

Private context anti-pattern:

```text
high-level .orc entrypoint
-> public inputs for state_root / manifest_path / progress_ledger_path / run_state_path / __write_root__...
-> authored code manually passes state paths
-> compile or dry-run success is claimed as parity
```

Adapter/resource anti-pattern:

```text
command-result :argv ("python" "script.py" ...)
-> script mutates run state, moves resources, parses reports, writes pointer files
-> effects are invisible to shared validation
-> parent workflow appears to compose but semantics live outside the workflow model
```

Projection anti-pattern:

```text
provider decision
-> helper script publishes bundle path by convention
-> downstream reads pointer/report path as semantic authority
-> typed selection state and materialized bundle identity diverge
```

Promotion anti-pattern:

```text
leaf .orc compile success
-> hand-written migration note says parity is close
-> non_regressive asserted or inferred
-> YAML primary is replaced before parent-callable family evidence exists
```

## 8. Goals

- Make nested `match`, nested `repeat_until`, nested stdlib calls, and
  branch-local effectful procedures lower through one generic composition
  route.
- Keep shared validation authoritative while making it scope-aware enough to
  validate generated branch-local refs and nested structured control.
- Preserve variant proof scopes across `let*`, `match`, reusable calls,
  projection, and union-return normalization.
- Normalize union-to-union returns from the actual returned variant, not from
  the matched source case.
- Allow logical field names to repeat across union variants while preserving
  distinct lowered artifact and JSON-pointer identities.
- Introduce private executable context values so public `.orc` boundaries do
  not expose generated state roots, write roots, run ids, phase roots, or YAML
  compatibility paths.
- Harden imported/std `.orc` reuse through ordinary import, specialization,
  typecheck, lowering, source maps, and effect visibility.
- Prove `review-revise-loop` is first-class enough to appear inside branch
  scopes, reusable calls, parent workflow modules, and nested phase contexts.
- Replace deterministic publication helpers with typed projections where
  possible and certified adapters where needed.
- Move recurring run-state/resource semantics toward declared
  resource-transition effects or certified adapters with explicit contracts.
- Add a typed authoring surface for certified adapters so high-level `.orc`
  code does not hand-author raw argv plumbing.
- Build a parent-callable work-item/backlog-drain model over typed resources
  and explicit terminal results.
- Require strict parity evidence that distinguishes leaf candidates,
  parent-callable candidates, non-regressive families, and promotable
  families.

## 9. Non-Goals

- Do not add runtime closures.
- Do not add runtime procedure values or dynamic dispatch.
- Do not make `orchestrate explain` a prerequisite for this tranche.
- Do not hard-error all legacy YAML inline glue before migration inventory and
  allowlist metadata exist.
- Do not use report parsing, pointer files, stdout, debug YAML, generated
  summaries, or generated markdown as semantic authority.
- Do not replace YAML primaries based on parse, compile, shared validation, or
  dry-run alone.
- Do not treat `non_regressive=true` by itself as a primary-surface decision
  when the candidate is not promotion-eligible.
- Do not weaken the required lints that reject raw generated `state/` paths at
  public high-level `.orc` boundaries; the fix is a private bridge, not lint
  relaxation.
- Do not rebuild implemented review/revise stdlib or ProcRef/specialization
  substrate from scratch; audit and harden the current route.
- Do not introduce a compiler-special `review-revise-loop` branch as the
  promoted route.
- Do not write a parent `.orc` drain wrapper that hides unresolved state
  mutation, recovery, or resource movement in adapters.
- Do not widen public authored-YAML collection artifact contracts as a
  prerequisite for private executable Workflow Lisp value transport.
- Do not expand the foundation tranches in this document; fix missing
  foundation work in the foundation design or its implementation plans.

## 10. Architecture Invariants

- Workflow Lisp remains a frontend over the existing validated workflow model.
- Shared validation remains authoritative after lowering.
- Any future frontend feature may add authoring power only by lowering into
  the existing validated workflow model or into a separately accepted future
  runtime contract.
- Composition regularity: a typed effectful form that is valid at workflow top
  level is valid in any branch scope or procedure position where its type and
  effects are valid, or it fails before lowering with an owned diagnostic that
  names the composition restriction. Silent post-lowering rejection of
  well-typed nested forms is a defect.
- Stdlib and phase forms recognize capability/shape contracts across module
  boundaries through structural validation plus source provenance, never
  through short authored-name matching (F1 lesson).
- All effects introduced by imported/std `.orc` code are visible after
  expansion.
- Every generated statement, branch scope, loop frame, path, helper, context
  value, adapter/resource effect, and selected `ProcRef` body has source-map
  provenance.
- Generated state/path allocation goes through `StateLayout` /
  `PathAllocator`.
- Branch-local refs are visible only inside scopes where their producers
  dominate the consumer.
- Union result translation derives the output variant from the returned
  variant expression; the matched source case is control flow and branch
  proof, not output identity.
- Variant proof tokens cannot be inferred from variant names alone after a
  branch returns a different union type.
- Logical field names in union variants are scoped by `(union, variant,
  field)` for lowered artifact/output identity.
- Runtime state, artifact contracts, provider results, command results,
  workflow outputs, and resource-transition results contain no `ProcRef`,
  provider ref, prompt ref, closure, unresolved type parameter, or runtime
  type object.
- Private executable context values are runtime-owned; public boundary
  projections may explain them but must not convert them into authored public
  inputs.
- Run-state mutation, recovery recording, prerequisite reconciliation, and
  terminal drain updates are typed resource transitions or certified adapters;
  hidden semantic glue in command steps is migration debt.
- Reports, pointer files, materialized views, and debug projections are views
  unless explicitly contracted otherwise.
- Migration promotion is machine-computed by strict parity evidence.
- `non_regressive` is evidence; `--require-promotable` is required before a
  primary-surface decision.
- Leaf compile evidence is necessary but never sufficient for family
  promotion; parity evidence carries explicit readiness labels.

## 11. Tranche 0: Current-State Inventory And Readiness Labels

### 11.1 Contract

Every implementation drain using this document must start by updating a
current-state inventory. The inventory is a design input, not a status boast.
It must identify which surfaces are implemented, partially implemented,
missing, blocked by foundation evidence, or intentionally deferred.

### 11.2 Required labels

Each candidate should be labeled with exactly one highest applicable migration
readiness state:

| Label | Meaning |
| --- | --- |
| `leaf_compile_candidate` | The `.orc` leaf parses, typechecks, lowers, and may pass focused tests, but it is not parent-callable parity evidence |
| `leaf_runtime_candidate` | The leaf has dry-run or smoke evidence for its own contract, but not family-level parent-callability |
| `parent_callable_candidate` | The workflow can be called by its intended parent without public generated context/state inputs and without hiding unresolved semantics |
| `family_non_regressive` | Machine evidence proves no required parity regression for the selected family target |
| `promotion_eligible` | The family is non-regressive and passes policy eligibility for primary-surface replacement |

Leaf-only evidence must never satisfy `--require-promotable`.

### 11.3 Tasks

- Verify current source routes for `std/phase.orc`, `review-revise-loop`,
  imported `.orc` expansion, `ProcRef` specialization, and structural context
  recognition.
- Verify focused test evidence for Design Delta Drain leaves, starting from
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`.
- Record every known split-leaf workaround and its missing parent-callable
  dependency.
- Mark each helper script as pure projection, certified adapter candidate,
  resource transition candidate, runtime-native candidate, or migration debt.
- Record which parity evidence is leaf-only, parent-callable, family-level,
  non-regressive, or promotable.
- Repair stale design-index/status entries before new implementation work
  starts.

### 11.4 Acceptance

- The inventory names every blocker from the Design Delta Drain findings
  report and maps it to a tranche in this document.
- No implementation ticket claims a current feature is missing without
  checking source and tests first.
- No parent-drain work item is scheduled ahead of its P0 prerequisites unless
  it is explicitly a failing fixture.
- Migration manifests and readiness reports distinguish leaf candidates from
  parent-callable candidates.

## 12. Tranche 1: Nested Structured-Control Composition

### 12.1 Contract

Nested structured control is the compiler/runtime substrate that allows
effectful `match`, effectful `repeat_until`, `loop/recur`, stdlib workflow
calls, provider-result steps, command-result steps, and typed projections to
appear inside branch scopes and reusable procedures while still passing shared
validation.

The selected target is the accepted WCC middle-end route from
`workflow_lisp_core_calculus_middle_end.md`: typed Workflow Lisp expressions
elaborate into WCC, normalize through ANF/join-point structure, and
defunctionalize into the existing validated Core/executable projection. The
route must make branch scopes, loop frames, proof tokens, source maps, and
generated path allocation explicit before shared validation. New
post-foundation compiler-lane gaps must extend WCC rather than introduce a
second composition graph.

Representative normalization:

```text
authored expression
-> typed expression/effect tree
-> structured control graph
-> scoped statements, control frames, proof tokens, effect summaries
-> Core AST / executable IR projection
-> shared validation
```

### 12.2 Required shapes

The first tranche must cover:

- effectful `let*` with provider and command results;
- effectful `match` arms that contain provider, command, workflow-call,
  stdlib-call, projection, and materialization effects;
- structured `repeat_until` or `loop/recur` nested under a `match` branch;
- stdlib `review-revise-loop` inside a branch selected by an outer domain
  result;
- same-file calls with locally constructed records;
- imported reusable procedures containing provider/command/workflow effects;
- generated write roots across reusable call boundaries;
- branch-local refs that are consumed only in valid scopes;
- proof-preserving projection from normalized branches; and
- source maps and Semantic IR layout entries for every generated branch, step,
  loop, path, and projection.

### 12.3 Branch scope and validation model

The compiler must produce a scope graph with at least:

- `scope_id`;
- parent scope;
- entering control node;
- active variant proof, if any;
- loop/call-frame identity, if any;
- values produced in the scope;
- values projected out of the scope;
- effects declared in the scope; and
- generated allocation identities requested in the scope.

Shared validation must reject a consumer ref unless the producer is in the
same scope, an ancestor scope, or an explicitly projected branch result.
Generated step IDs alone are not proof of visibility.

### 12.4 Tasks

- Define the composition-normalized structured control graph data model.
- Define pass order relative to import expansion, compile-time specialization,
  typecheck, effectful normalization, Core projection, source-map emission,
  and shared validation.
- Add effect summaries for provider, command, workflow-call, projection,
  materialization, state, artifact, resource, and adapter effects.
- Add proof-scope transfer through `let*`, `match`, calls, loops, and branch
  projections.
- Route branch-local generated paths through `StateLayout` / `PathAllocator`
  with call-frame and loop-frame identity.
- Preserve resume identity for steps generated inside branch scopes.
- Add diagnostics for unsupported nested control before ordinary lowering
  emits invalid Core.
- Add negative tests for branch-local ref leakage, missing branch projection,
  and invalid proof use.

### 12.5 Acceptance

The canonical acceptance fixture is the implementation-phase shape from the
design-delta drain:

```text
provider-result -> ImplementationAttempt
match ImplementationAttempt:
  COMPLETED -> command-result -> review-revise-loop -> ImplementationPhaseResult
  BLOCKED   -> ImplementationPhaseResult
```

Acceptance requires:

- compile/typecheck succeeds;
- lowering emits no invalid branch-local refs;
- shared validation succeeds;
- source maps identify authored forms, imported/std definitions, generated
  statements, branch scopes, loop frames, and generated paths;
- Semantic IR records matching state-layout entries;
- dry-run or fake-provider smoke succeeds;
- branch-local producers are not visible outside their branch except through
  explicit projections;
- resume identity is stable for branch-scoped generated steps;
- unsupported nested shapes fail with actionable diagnostics; and
- the implementation phase no longer has to split into
  `execute-implementation-attempt` and `review-completed-implementation`
  solely to satisfy lowering/shared validation.

### 12.6 Normative spec deltas

If existing specs describe structured `match` or `repeat_until` only as
top-level constructs, update the relevant DSL/frontend design text to clarify
one of two accepted routes:

1. Workflow Lisp may author nested effectful structured control when lowering
   normalizes it into the existing validated executable model with explicit
   branch scopes; or
2. an accepted executable IR layer may preserve nested control until
   rendering, provided shared validation receives equivalent scope, proof,
   effect, and source-map information.

## 13. Tranche 2: Union Result Normalization And Variant-Scoped Output Identity

### 13.1 Contract

Union return normalization must be based on the actual returned variant
expression and expected target type, not on the source variant that happened
to be matched. A `match` branch may intentionally translate an inner control
result into a different outer domain result.

Variant output identity must be scoped by union variant. Logical field names
may repeat across variants without colliding in lowered artifact names, JSON
pointers, validation keys, or publication identities.

### 13.2 Union-to-union normalization rule

When a branch is expected to return union type `TargetUnion`:

- if the branch expression is an explicit `TargetUnion.VARIANT(...)`, use
  `TargetUnion.VARIANT` as the output variant;
- if the branch expression has a statically known union variant proof, use
  that proof only when it belongs to `TargetUnion`;
- if the branch expression maps an inner variant to an outer variant, the
  returned outer variant controls normalization;
- the matched source case contributes branch proof for allowed field access,
  not target variant selection; and
- ambiguous or incompatible branches fail with an explicit union-normalization
  diagnostic.

Examples that must work:

```text
ReviewLoopResult.APPROVED  -> ImplementationPhaseResult.COMPLETED
ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED
ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED
```

The parent-callable work-item route adds one explicit prerequisite shape under
this tranche: a parent workflow must be able to `match` an imported child
union and return a different local domain union without inheriting the child
variant name as target identity. The canonical work-item examples are:

```text
DesignDeltaPlanPhaseResult.BLOCKED -> WorkItemResult.TERMINAL_BLOCKED
WorkItemTerminalClassification.COMPLETE -> WorkItemResult.COMPLETED
WorkItemTerminalClassification.IMPLEMENTATION_BLOCKED -> WorkItemResult.BLOCKED_RECOVERY
```

If that route still fails with `union_return_variant_ambiguous`, the blocker
belongs to this tranche as a prerequisite gap. It must not be pushed down into
Tranche 7 by renaming outer variants to child control-state names, splitting
the work-item surface back into leaves, or treating the parent route as an
authoring problem.

### 13.3 Variant-scoped field identity

The canonical lowered identity for a variant output field is:

```text
<producer_step_identity>/<union_type>/<variant_name>/<field_name>
```

or an equivalent stable tuple containing the same semantic components. The
authored field name remains simple:

```text
APPROVED.plan_path
BLOCKED.plan_path
EXHAUSTED.plan_path
```

Lowered artifact names, JSON pointers, bundle paths, source-map entries, and
Semantic IR entries must remain distinct even when the logical field name is
reused.

### 13.4 Tasks

- Replace source-case-name-based union return normalization with
  returned-variant-based normalization.
- Add a focused prerequisite fixture for imported-child parent routing: a
  parent-callable work-item-style workflow that matches imported child unions
  and returns a local domain union without `union_return_variant_ambiguous`.
- Add diagnostics for ambiguous returned union variants, missing expected
  type, and incompatible target variants.
- Introduce variant-scoped output identity in lowering and shared validation.
- Update artifact/json-pointer uniqueness checks to use `(producer, union,
  variant, field)` rather than only field or artifact name.
- Preserve backward compatibility for already-authored variant-specific field
  names.
- Add source-map and Semantic IR entries that record both authored field name
  and lowered variant-scoped identity.
- While variant-scoped identity remains unimplemented, document the
  restriction and the required variant-specific naming style in
  `docs/lisp_workflow_drafting_guide.md` with examples, add a compile-time
  diagnostic that names the restriction, and record the open gap in the
  Tranche 0 inventory. This is a required interim mitigation; it does not
  satisfy this tranche's acceptance or the target success criteria.

### 13.5 Acceptance

- Branches can translate inner review-loop variants to outer domain-specific
  result variants.
- Imported child workflow/classifier unions can be matched and translated into
  a parent work-item or drain-domain union without forcing the outer union to
  mirror child control-state names.
- Domain unions do not need to mirror inner control-state names.
- No lowering path raises `KeyError` for well-typed cross-union mappings; any
  rejected mapping has a typed diagnostic.
- The real work-item-style imported-child route no longer fails with
  `union_return_variant_ambiguous`; if it still does, Tranche 7 is blocked on
  this prerequisite.
- The same logical field name may appear in multiple variants without
  validation collisions. The documented restriction plus diagnostic is an
  interim mitigation while the gap is open; it does not satisfy this
  acceptance.
- Shared validation checks only the active variant's required fields.
- Generated bundle/artifact identities remain collision-proof.
- Existing verbose variant-specific names continue to compile as compatibility
  style.
- Diagnostics identify the union, source branch, returned expression, and
  expected target union when normalization fails.

### 13.6 Normative spec deltas

Update DSL/frontend design text for variant outputs to state that field
identity is variant-scoped in generated executable artifacts, even when the
authored logical field name repeats across variants. If public YAML currently
requires globally unique field names, preserve that public restriction only as
a public-authoring compatibility rule; do not force private frontend-lowered
`.orc` unions to inherit it when variant-scoped identities are available.

## 14. Tranche 3: Private Executable Context Bridge And Entrypoint Bootstrap

### 14.1 Contract

High-level `.orc` entrypoints must not expose runtime-owned context, generated
state roots, generated write roots, phase roots, item roots, drain roots,
selection bundle paths, recovery paths, or YAML compatibility paths as
ordinary public inputs.

The frontend/runtime must provide a private executable context bridge. The
bridge derives internal context values from runtime execution context and
`StateLayout`, binds them to reusable calls and stdlib workflows, and emits
source-map/Semantic IR evidence explaining the generated bindings without
making them public authored inputs.

This tranche needs a pre-implementation design before code changes. Parity
architecture has already exposed missing phase-context binding as a real
wrapper-promotion failure mode, and synthetic top-level `PhaseCtx` inputs are
not acceptable promotion evidence.

### 14.2 Private context values

Initial private context families:

- `RunCtx`: run id, run root, artifact root, state root, temp root, runtime
  identity, and run-scoped allocation namespace;
- `PhaseCtx`: phase namespace, phase state root, phase artifact root, phase
  bundle roots, phase checkpoint identity, and phase-specific write roots;
- `ItemCtx`: selected item identity, item state namespace, item artifact
  namespace, prerequisite/recovery linkage, and item-scoped allocation
  identity;
- `DrainCtx`: drain state namespace, selection/recovery queues, iteration
  identity, and terminal drain accumulator;
- `SelectionCtx`: typed selection state, selection bundle view identity, and
  prerequisite/gap classification state; and
- `RecoveryCtx`: blocked outcome, recovery attempt state, retry identity, and
  reconciliation resources.

These are private executable values. They may appear in executable/runtime
contracts and source maps, but they are not public authored boundary fields.

### 14.3 Hidden reusable-call binding

A promoted entry workflow may call a reusable workflow or `resume-or-start`
surface whose internal signature requires `RunCtx`, `PhaseCtx`, `ItemCtx`, or
`DrainCtx`. The compiler/runtime must satisfy those internal parameters from
private bootstrap bindings.

The public boundary must exclude:

- `run_id`;
- `state_root`;
- `artifact_root`;
- phase/item/drain state roots;
- compiler-managed write roots;
- synthetic top-level `PhaseCtx` or `RunCtx` inputs;
- `__write_root__...` inputs; and
- legacy YAML state path fields unless explicitly declared as public
  compatibility inputs.

### 14.4 YAML compatibility bridge

During migration, a YAML-compatible wrapper may bridge legacy `state/` values
into private context. That bridge must be:

- explicit in the compiled executable contract;
- source-mapped as compatibility, not authored public Workflow Lisp API;
- hidden from the promoted `.orc` public boundary when parity claims the YAML
  user did not provide those fields;
- excluded from promotion evidence if it preserves non-isolated private path
  shapes as authority; and
- retired or narrowed when typed resource/state transitions replace the legacy
  path dependency.

### 14.4A Phase-Family Boundary Rehabilitation Prerequisite

The WCC reconciliation narrowed this prerequisite. The real design-delta
implementation-phase route now has parent-callable compile and smoke evidence
through WCC. The work-item route advances past the old private-workflow and
phase-family boundary diagnostics and now stops at a WCC route gap:
`work_item.orc` uses `IfExpr`, which is outside the migrated WCC M4 subset.
This slice remains the first executable portion of the private-context bridge
for the phase-family candidates, but WCC `IfExpr` support is now the immediate
compiler prerequisite before the work-item route can expose the next boundary
or resource-transition blocker.

Required behavior:

- high-level phase-family workflows must compile as high-level `.orc`
  boundaries without exposing phase state roots, generated write roots, or
  synthetic top-level `PhaseCtx` values as ordinary authored inputs;
- compatibility bridge inputs for legacy YAML `state/` values may remain only
  as explicit private or compatibility-labeled executable bindings with
  provenance, not as promoted high-level boundary fields;
- generated private-workflow or helper-hoisted branch routes used to realize
  nested composition must receive phase-context-like values through accepted
  private or compatibility carriers rather than invalid workflow-boundary field
  types; and
- clearing this slice does not relax the lint against low-level state paths;
  it changes the boundary shape so the lint no longer fires on promoted
  phase-family routes.

Tasks:

- draft and implement WCC `IfExpr` support for the work-item route before
  interpreting work-item compile failure as a private-context or resource
  transition failure;
- define the narrow public/private boundary shape for remaining plan and
  work-item candidates before the full family-wide `RunCtx` / `DrainCtx`
  bootstrap lands;
- define which existing YAML `state/` path inputs, if any, survive only as
  compatibility bridge bindings and how build artifacts/parity reports label
  them;
- define how generated helper/private workflow boundaries carry phase context
  without `workflow_boundary_type_invalid`; and
- keep compile/build-artifact fixtures for the real design-delta phase-family
  routes so this prerequisite fails before Tranche 7 if old boundary
  diagnostics regress or the WCC `IfExpr` blocker is lost.

Acceptance:

- the real design-delta implementation-phase candidate keeps parent-callable
  compile/smoke evidence under WCC;
- the real design-delta work-item candidate no longer fails on WCC
  `IfExpr`;
- the remaining real design-delta `plan_phase.orc` and `work_item.orc`
  candidates no longer fail parent-callable compilation on
  `low_level_state_path_in_high_level_module`;
- the approved-arm helper/private-workflow route introduced by the
  imported-child returned-variant recovery no longer fails on
  `workflow_boundary_type_invalid` when it carries phase-family context;
- boundary inspection shows any retained YAML `state/` values as private or
  compatibility-bridge bindings rather than normal high-level `.orc` inputs;
  and
- if the phase-family compile route remains blocked after this slice, the
  remaining failure is owned by another documented tranche rather than by
  high-level boundary/path exposure or invalid phase-helper boundary types.

### 14.5 Tasks

- Define `PrivateExecCtx` and context-family projection into executable
  contracts.
- Define how runtime creates private context for entry workflows.
- Define how reusable calls receive hidden context bindings.
- Define how defaults are represented in Core AST, Semantic IR, and executable
  IR.
- Route context-derived generated paths through `StateLayout` /
  `PathAllocator`.
- Add public/private boundary inspection in shared validation and migration
  parity.
- Preserve structural/capability context recognition across module-qualified
  imports.
- Add diagnostics for missing hidden context bootstrap, invalid public context
  exposure, and context capability mismatch.

### 14.6 Acceptance

- A promoted `.orc` wrapper can call reusable workflows requiring
  runtime-owned context without exposing run ids, write roots, state roots,
  artifact roots, or synthetic `PhaseCtx` inputs at the public boundary.
- Public input inspection proves generated write roots, state roots, and phase
  roots are hidden for plan, selector, architect, work-item, and parent
  candidates.
- Internal reusable-call bindings succeed because runtime-owned context
  satisfies them, not because authored defaults fake them.
- `.orc` input defaults match the corresponding YAML public boundary where
  parity is claimed.
- Shared validation and migration parity inspect public and private boundary
  projections separately.
- Resume reconstructs the same private context paths for the same
  run/call/loop identity.
- A YAML-compatible migration wrapper passes legacy `state/` values privately
  without making them normal `.orc` inputs, and the bridge values are labeled
  as migration bridges in provenance.
- Source maps and Semantic IR identify generated context/default bindings.
- Module-qualified imported context types are recognized by
  structural/capability contracts, not by short local names alone.

### 14.7 Normative spec deltas

Update frontend/runtime design text to distinguish:

- public authored inputs;
- private executable context values;
- compatibility bridge values;
- generated internal input bindings; and
- source-map/Semantic IR projections over those values.

Update `docs/design/workflow_lisp_state_layout.md` to include the initial
`RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx`
derivation responsibilities needed by parent-callable migration.

## 15. Tranche 4: Imported/Std `.orc` Reuse And Review-Revise First-Class Composition

### 15.1 Contract

Imported/std `.orc` definitions must be reusable through the ordinary compiler
pipeline. A stdlib form may provide ergonomic syntax, but control flow must
belong to grammar-accepted `.orc` definitions or to generic compiler machinery
available to ordinary `.orc`.

`review-revise-loop` must remain an ordinary imported/std `.orc` abstraction
in the promoted route. It must compose anywhere effectful procedures are
valid, including inside match branches, reusable workflow calls, parent
workflow modules, and nested phase contexts.

### 15.2 Current route

The current checkout already has a first stdlib route through
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, using compile-time
`ProcRef` hooks, `loop/recur` exhaustion projection, `command-result`
validation, `match`, and typed stdlib unions. This tranche is therefore
convergence and parity hardening, not a from-zero implementation.

### 15.3 Required behavior

For `review-revise-loop`:

- `APPROVE` exits with typed completion;
- `REVISE` invokes fix and continues; it is not completion;
- `BLOCKED` exits with typed non-completion;
- `EXHAUSTED` is explicit typed non-completion;
- review findings are validated structured state, not markdown extraction;
- report paths and findings paths are independently seeded and projected;
- carried evidence identity comes from inputs/state, not provider replacement
  fields;
- branch proof, effects, generated paths, source maps, loop state, and resume
  identity survive nested calls; and
- runtime artifacts contain no `ProcRef`, provider ref, prompt ref, closure,
  or unresolved type parameter.

### 15.4 Tasks

- Load stdlib `.orc` through ordinary import resolution.
- Clone parsed imported bodies through a hygienic imported-definition
  boundary.
- Expand or specialize imported definitions without hidden runtime semantics.
- Resolve compile-time `ProcRef` substitutions and specialization identity
  before lowering.
- Re-typecheck specialized helpers before ordinary lowering.
- Preserve cache/reuse behavior without changing source-map identity.
- Preserve source maps for caller, imported definition, generated helpers,
  generated paths, review `ProcRef`, and fix `ProcRef`.
- Preserve effect summaries for imported provider/command/workflow calls.
- Keep compile-time `ProcRef` values out of runtime artifacts.
- Add architectural denylist tests for promoted name-special compiler paths.
- Check reserved names against the form registry so stdlib ownership is not
  blocked by stale compiler-special classifications.
- Add review-loop fixtures under branch scopes and parent modules, not only
  top-level leaves.

### 15.5 Acceptance

- A tiny imported `.orc` helper expands, typechecks, lowers, and validates.
- An imported `.orc` helper with provider/command effects exposes those
  effects.
- An imported `.orc` helper with `match` preserves variant proof.
- An imported `.orc` helper with loop state preserves source maps, checkpoint
  identity, and generated path provenance.
- Promoted fixtures fail if they use compiler branches keyed to stdlib form
  names rather than the generic import/expansion route.
- `review-revise-loop` compiles through imported/std `.orc` inside the
  completed branch of an implementation-attempt match.
- Generated workflow contains ordinary provider, command, match, loop,
  projection, materialization, and resource surfaces.
- APPROVE, REVISE->APPROVE, BLOCKED, EXHAUSTED, and resume fixtures pass,
  including with the loop invoked from nested contexts.
- A real workflow-family parity report can include review/revise evidence
  without relying on split-leaf workarounds.

## 16. Tranche 5: Typed Projection And Selector/Bundle Materialization

### 16.1 Contract

Deterministic projection from validated typed state to materialized
bundle/path views must be explicit. A projection is not hidden command glue.
It is a typed relationship between semantic state and a representation needed
by downstream workflow calls, prompts, compatibility paths, or legacy
consumers.

Selector and bundle publication should follow this preference order:

1. native typed projection (preferred): derive the bundle identity from
   runtime-known provider output bundle identity and `StateLayout` allocation;
2. certified adapter (migration bridge only): keep the publication script,
   certified explicitly as deterministic projection with a recorded
   native-projection replacement route; or
3. private context bridge: keep the bundle path private to
   runtime/`StateLayout` and expose typed selection values to `.orc`, when
   downstream callers need values rather than paths.

### 16.2 Projection authority rules

- The validated typed value is semantic authority.
- A structured bundle is authority only after validation against its declared
  output contract.
- A materialized bundle path may be a view, a public artifact, or a
  compatibility pointer depending on its declared contract.
- Pointer files and report paths are representations unless explicitly
  contracted otherwise.
- A projection must declare input state, output representation, path
  allocation, artifact publication behavior, and source-map provenance.
- Variant-scoped output identity must survive projection.

### 16.3 Selector/bundle publication target

For selector workflows:

```text
provider-result -> typed SelectionDecision
-> typed projection over validated decision and provider bundle identity
-> selection bundle materialized view or artifact
-> parent-callable typed selection result
```

The preferred route is a native typed projection that derives
`selection_bundle_path` from runtime-known provider output bundle identity and
`StateLayout` allocation. If retained as a script,
`publish_lisp_frontend_selection_bundle.py` must be certified as deterministic
projection, not hidden routing.

### 16.4 Tasks

- Define a projection effect class visible to shared validation and Semantic
  IR.
- Add projection contracts for selector bundle publication and other
  deterministic bundle/path materializations.
- Route projection bundle/view paths through `StateLayout` / `PathAllocator`.
- Preserve source maps from authored projection forms and imported/std
  helpers.
- Add projection negative tests for stale input, missing input bundle, schema
  mismatch, path escape, and treating a view as authority.
- Certify retained projection scripts with typed input/output contracts,
  fixtures, and source-map behavior, recording the native-projection
  replacement route.
- Update drafting guidance so authors do not hand-author publication scripts
  for deterministic projection.

### 16.5 Acceptance

- Selector candidate returns typed selection state and a declared
  bundle/materialized view identity.
- Downstream workflows can consume selection state without reading a pointer
  or report as semantic authority.
- A native projection can materialize the selection bundle path from typed
  state and provider bundle identity.
- If a certified adapter bridge is used, its behavior class is
  `typed_projection`, its effects are visible, it has positive and negative
  fixtures, and its certification record names the native replacement route.
- Source maps and Semantic IR identify projection inputs, outputs, allocation
  identity, and authority class.
- Parent workflow calls do not need to know the legacy publication script
  path.

### 16.6 Normative spec deltas

Clarify in DSL/frontend design text that typed projections may materialize
deterministic views over validated private executable state, and that such
views do not become semantic authority unless their contract explicitly says
they are public artifacts.

## 17. Tranche 6: Certified Adapter Declarations And Resource-Transition Ownership

### 17.1 Contract

Command execution remains legitimate. Hidden workflow semantics inside raw
command text are not legitimate for new high-level `.orc` workflows. Any
retained helper that decides workflow state, routing, resource movement,
artifact lineage, or resume behavior must be expressed as one of:

1. a typed Workflow Lisp procedure;
2. a typed workflow call;
3. a typed projection;
4. a certified command adapter with declared inputs, outputs, effects,
   fixtures, and source maps; or
5. a runtime-native resource/state transition effect.

Certification policy vocabulary remains owned by
`workflow_command_adapter_contract.md`; this tranche owns the sequencing for
migration families and the `.orc` call surface.

### 17.2 Adapter classification

Classify every retained helper first by behavior:

- pure typed projection;
- structured validator;
- provider-output protocol bridge;
- variant selection;
- assertion gate;
- resume-state reuse;
- resource transition;
- ledger update;
- outcome finalization;
- report parsing;
- pointer materialization; or
- external tool invocation.

Then classify the replacement route:

- native typed Workflow Lisp;
- existing DSL surface;
- certified adapter;
- runtime-native transition;
- legacy compatibility adapter; or
- migration debt to replace.

### 17.3 Certified adapter declaration surface

High-level `.orc` should call named adapters with typed fields rather than raw
argv assembly. The exact syntax may be manifest-based or `.orc`-based, but the
declaration must contain at least:

```text
name
stable command path
typed input signature
typed output signature
declared effects
artifact contracts
state/resource writes
path-safety expectations
exit-code and error taxonomy
fixture tests
negative tests
source-map behavior
owner module
replacement path, if temporary
```

Illustrative non-normative shape:

```lisp
(defadapter publish-selection-bundle
  :class typed-projection
  :command workflows/library/scripts/publish_lisp_frontend_selection_bundle.py
  :inputs  (decision SelectionDecision provider_bundle ProviderBundleRef)
  :outputs (bundle SelectionBundle)
  :effects (materializes selection_bundle_path))
```

Raw `:argv` remains available as a low-level command boundary, but new
high-level `.orc` libraries must not use raw argv to hide semantic workflow
transitions.

### 17.4 Resource-transition ownership

Run-state completion, blocked recovery recording, prerequisite edge
reconciliation, selected-item terminal classification, retry state, and drain
terminal updates are resource transitions. The target model is:

```text
resource state version + typed transition request
-> validated transition effect
-> new resource state version + typed transition result
```

A resource transition must declare:

- resource kind and identity;
- input version or snapshot identity;
- transition name;
- typed request payload;
- typed result union;
- atomicity/idempotency expectations;
- resume/retry behavior;
- conflict behavior;
- emitted artifacts or views;
- source-map provenance; and
- audit/ledger representation.

Certified adapters may implement resource transitions during migration, but
recurring transitions with atomic multi-file/resource semantics should move
toward runtime-native effects.

### 17.5 Tasks

- Inventory helper scripts used by the migration family.
- Classify each helper by behavior and replacement route.
- Add certified adapter declarations for retained helpers.
- Add typed adapter call ergonomics for `.orc` authors.
- Define `resource-transition` effect summary and Semantic IR projection.
- Define negative lint behavior for new `.orc` hidden semantic glue.
- Add fixtures for state mutation, path safety, error taxonomy, idempotency,
  and resume conflict handling.
- Promote only repeated/fundamental transitions to runtime-native effects.

### 17.6 Acceptance

- Every retained migration-family helper has a recorded classification with a
  replacement route where applicable.
- New high-level `.orc` rejects hidden semantic glue unless it is behind a
  certified adapter or accepted temporary bridge.
- Strict migration CI rejects hidden glue unless allowlisted with owner,
  replacement, and expiry.
- Adapter invocations expose typed inputs, typed outputs, effects, path-safety
  rules, and source maps.
- A declared adapter with a wrong-typed field fails at compile/typecheck, not
  at runtime argv assembly.
- Resource transitions are visible to shared validation, Semantic IR, parity
  evidence, and run-state audit views.
- Parent workflows no longer rely on unclassified scripts for completion,
  blocked recovery, prerequisite reconciliation, or terminal drain state.

### 17.7 Normative spec deltas

Update `docs/design/workflow_command_adapter_contract.md` with the typed
adapter declaration/call surface once accepted. Update state/runtime design
text for any runtime-native resource-transition effect that leaves adapter
status.

## 18. Tranche 7: Work-Item And Parent Backlog-Drain Composition

### 18.1 Contract

The parent drain is not a loop over script paths. It is a typed workflow over
resources, selections, work items, design gaps, prerequisite edges, blocked
recovery, retry, terminal block, and bounded exhaustion.

A parent-callable `.orc` family must expose typed public inputs and outputs
while carrying private runtime context, resource state, selection state,
recovery state, and generated paths internally.

The design-delta migration correctly stopped before the parent drain; the
blocker record at
`docs/plans/LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION/parent_drain_readiness_blockers.md`
remains in force until this tranche's prerequisites pass.

### 18.2 Parent-callable phase surfaces

Before a parent `.orc` drain can be promoted, each child phase must be
parent-callable. After Tranche 2 lands, the next mandatory gate is Tranche 3A
phase-family boundary rehabilitation for the real plan, implementation, and
work-item candidates:

- public inputs match the intended YAML/user boundary;
- private context is hidden and runtime-owned;
- generated write roots are hidden and allocator-owned;
- phase-family candidates clear the Tranche 3A boundary failures: no
  `low_level_state_path_in_high_level_module` on promoted high-level phase
  surfaces and no `workflow_boundary_type_invalid` on generated/private helper
  boundaries that carry phase context;
- child terminal results are typed unions;
- imported child unions can be translated into outer work-item/drain result
  unions through the Tranche 2 returned-variant route;
- artifact and state effects are declared;
- resource transitions are visible;
- retry/resume identity is stable; and
- source-map/Semantic IR provenance is complete.

### 18.3 Backlog-drain typed model

The target parent model is a typed loop with an accumulator and terminal
union, not a wrapper around YAML state files.

Representative shape:

```text
DrainState
-> select next resource or prerequisite/gap/recovery action
-> match selection:
     SELECTED_ITEM     -> run work-item phase -> resource transition -> recur
     DESIGN_GAP        -> draft/validate design gap -> resource transition -> recur
     PREREQUISITE      -> reconcile prerequisite edge -> resource transition -> recur
     BLOCKED_RECOVERY  -> run recovery route -> retry or terminal block
     EMPTY             -> completed terminal result
     EXHAUSTED         -> exhausted terminal result
```

This may become an imported/std `.orc` abstraction such as `backlog-drain`,
but it must be built from ordinary `.orc` composition, typed resource
transitions, and certified/runtime effects rather than a compiler-special
drain lowerer.

### 18.4 Tasks

- Define typed `DrainState`, `WorkItemState`, `SelectionResult`,
  `RecoveryResult`, and `DrainTerminalResult` contracts.
- Define parent-callable readiness checks for each phase candidate.
- Replace split-leaf boundaries with single parent-callable phase workflows as
  nested composition permits.
- Define resource-transition calls for selection, completion, blocked
  recovery, prerequisite reconciliation, retry, and terminal finalization.
- Define how `DrainCtx`, `ItemCtx`, `SelectionCtx`, and `RecoveryCtx` are
  derived and passed privately.
- Add fixtures for normal completion, prerequisite selection, design-gap
  drafting, blocked recovery, recovered-gap retry, terminal blocked, and
  bounded exhaustion.
- Add parity evidence roles for parent-callability and resource-transition
  parity.

### 18.5 Acceptance

- The implementation phase can be expressed as one parent-callable workflow
  rather than split leaves.
- A work-item workflow can call plan, implementation, selector/architect, and
  recovery phases without public generated context/state inputs.
- A parent drain can execute at least one normal selected item path and one
  blocked/recovery path in typed `.orc` without hiding semantics in
  unclassified adapters.
- Drain terminal results are typed and parity-comparable.
- Resource transitions and ledger updates are declared and visible.
- Strict parity evidence distinguishes parent-callable success from family
  non-regression.

## 19. Tranche 8: Canonical Resume/Reuse Validation And Migration Evidence

### 19.1 Contract

`resume-or-start` must be a typed reusable-state validation surface, not a
prettier recovery gate over ad hoc files or report text. It validates prior
reusable state, normalizes resumed and fresh branches to the same return type,
and exposes explicit recoverable outcomes when prior state is stale, missing,
incompatible, unsupported, failed, or blocked.

Migration evidence must distinguish:

- leaf compile success;
- leaf runtime evidence;
- parent-callable evidence;
- family non-regression evidence; and
- promotion eligibility.

### 19.2 Resume/reuse validation

A reusable state record must include:

- schema version;
- workflow/procedure identity;
- input digest or typed input identity;
- private context allocation identity where relevant;
- terminal variant;
- referenced artifact contracts;
- resource-transition version references where relevant;
- source-map/provenance reference;
- creation/update time as evidence, not semantic identity; and
- compatibility labels when old state layouts are bridged.

Failure taxonomy:

| Case | Required behavior |
| --- | --- |
| reusable approved prior result | resume without rerunning fresh work |
| stale input hash | typed stale-state branch or fresh rerun according to contract |
| missing artifact | typed missing-artifact branch or fresh rerun according to contract |
| schema mismatch | typed incompatible-state branch |
| unsupported version | typed unsupported-version branch |
| prior failed/blocked terminal | typed non-reusable branch unless explicitly accepted |
| private context identity mismatch | typed context-mismatch branch |
| resource version conflict | typed conflict branch or declared retry |

Resume decisions must be based on state/artifact/resource contracts, not
report parsing or pointer-file authority.

### 19.3 Migration evidence roles

A promotable family target must carry evidence for:

- compile;
- typecheck;
- lowering;
- shared validation;
- dry-run or fake-provider smoke;
- real smoke where safe and required;
- output contract parity;
- terminal state parity;
- artifact parity;
- source-map and generated-path provenance;
- public/private boundary parity;
- nested structured-control parity for parent-callable phases;
- review/revise loop parity;
- selector/projection parity;
- resource-transition parity;
- resume/reuse parity;
- deprecated-mechanic replacement or accepted waiver; and
- strict `migration-parity` computation.

### 19.4 Tasks

- Canonicalize reusable-state schema and failure taxonomy.
- Add resume fixtures for approved, stale, missing, incompatible, unsupported,
  failed/blocked, context mismatch, and resource conflict cases.
- Add parent-callable readiness fields to target manifests or parity reports.
- Ensure `--require-non-regressive` cannot pass with stale or incomplete
  parent-callable evidence for selected family targets.
- Ensure `--require-promotable` fails for leaf-only evidence even when leaves
  compile and smoke individually.
- Add report/index labels for leaf, parent-callable, family non-regressive,
  and promotion-eligible states.

### 19.5 Acceptance

- Reusable approved prior result resumes without rerunning fresh work.
- Fresh and resumed branches normalize to the same result type.
- Resume decisions do not parse reports, pointer files, or markdown as
  authority.
- Parent-callable parity evidence is required for family non-regression.
- Leaf compile evidence is displayed as useful progress but is insufficient
  for `--require-promotable`.
- A real workflow-family `.orc` parity report computes `non_regressive=true`
  only when required parent-callable evidence is complete.
- Any YAML-primary replacement passes `--require-promotable`.

## 20. Design Details

### 20.1 Nested control graph contract

A composition-normalized graph node should include:

```text
node_id
source_span
source_frame_stack
scope_id
node_kind
input_refs
output_refs
proof_requirements
proof_outputs
effect_summary
allocation_requests
runtime_projection_hints
```

Control nodes additionally include:

```text
control_kind: match | loop | repeat_until | call | projection
child_scopes
entry_proofs
exit_projection
resume_identity
```

The graph is not semantic authority after projection. It is an intermediate
representation that ensures ordinary lowering and shared validation receive
explicit scope, proof, effect, and allocation data.

### 20.2 Variant proof contract

A variant proof is valid only inside the branch or projected value that
produced it. Proof identity includes:

```text
source_union_type
source_variant
producer_ref
scope_id
proof_path
```

A target union return carries its own returned variant identity. Source proof
may justify field access, but not target variant selection unless the target
expression is itself the source value and the types match.

### 20.3 Private context contract

Private executable context authority layers:

```text
runtime execution context
-> StateLayout semantic context request
-> PrivateExecCtx value
-> hidden internal call binding
-> executable contract
-> source-map / Semantic IR projection
```

Authority rules:

- runtime execution context owns run identity;
- `StateLayout` owns context-derived path namespaces;
- executable IR owns hidden internal bindings;
- source maps and Semantic IR explain generated values;
- public boundary projection must not turn private values into authored
  inputs; and
- compatibility bridge values are migration views unless explicitly contracted
  as public inputs.

### 20.4 Projection contract

A typed projection has:

```text
projection_id
projection_class
input_contracts
output_contract
path_allocation, when materialized
authority_class: semantic_state | materialized_view | public_artifact | compatibility_view
effect_summary
source_map_entries
negative_validation_cases
```

Projection classes initially include:

- `variant_field_projection`;
- `selection_bundle_projection`;
- `materialized_value_view`;
- `compatibility_pointer_view`;
- `report_view_projection`; and
- `resource_snapshot_view`.

### 20.5 Certified adapter contract

Certified adapters must use the structured command-output authority from the
foundation. Stdout may be debug output; it is not semantic authority for
structured results. Adapter declarations must be source-mapped and must expose
effects to shared validation and Semantic IR.

Required failure behavior:

| Case | Result |
| --- | --- |
| adapter writes undeclared bundle | output-contract failure |
| adapter writes valid stdout but missing bundle | output-contract failure |
| adapter mutates undeclared state/resource | adapter contract failure |
| adapter reads pointer/report as authority without certification | lint/error in new `.orc` |
| adapter path escapes allowed root | path-safety failure before launch |
| adapter returns undeclared exit code | adapter error taxonomy failure |

### 20.6 Resource-transition contract

A resource transition is authoritative only after the runtime or certified
adapter validates:

- input resource version;
- transition preconditions;
- typed transition payload;
- conflict/idempotency policy;
- output state/version;
- declared artifacts/views;
- audit/ledger entry; and
- source-map provenance.

Reports and ledgers are views over transition state unless explicitly accepted
as transition authority.

### 20.7 Parent-callability contract

A workflow is parent-callable when:

- its public inputs are stable and parity-comparable;
- all internal context/state roots are private or explicit compatibility
  bridge values;
- its outputs are typed and terminal-state comparable;
- child effects are declared;
- resource transitions are visible;
- resume identity is stable;
- source maps and Semantic IR explain generated internals; and
- parity tooling can compare its behavior as a child of the parent, not only
  as an isolated leaf.

## 21. Contracts And Interfaces

### 21.1 Workflow Lisp frontend

- Produces composition-normalized structured control graph for nested
  effectful expressions.
- Emits scope-aware proof and effect metadata before shared validation.
- Normalizes union returns from returned variants, not matched source cases.
- Emits variant-scoped output identities.
- Expands imported/std `.orc` through ordinary
  import/specialization/typecheck/lowering.
- Recognizes imported capability/shape contracts structurally with provenance,
  never by short local names.
- Keeps `ProcRef`, provider refs, prompt refs, and type parameters
  compile-time-only.
- Emits private executable context bootstrap requests at promoted entry
  boundaries.
- Emits source maps for generated contexts, scopes, branches, loops, paths,
  projections, adapters, resources, and stdlib bodies.

### 21.2 Shared validation

- Validates scoped refs according to branch/call/loop dominance.
- Validates effect summaries for provider, command, workflow, projection,
  adapter, resource, state, and artifact effects.
- Validates variant-scoped output identities without global field-name
  collisions.
- Separates public boundary validation from executable/private binding
  validation.
- Rejects hidden semantic glue in new high-level `.orc` unless certified or
  allowlisted.

### 21.3 Runtime/executable

- Consumes `StateLayout` allocation metadata rather than synthesizing
  generated paths independently.
- Creates private executable context at entrypoints.
- Binds hidden context values to reusable calls.
- Preserves provider/command structured-output authority from the foundation.
- Executes typed projections and certified adapters according to declared
  contracts.
- Executes or delegates resource transitions with version/conflict semantics.
- Persists resume state by semantic identity, call frame, loop frame, and
  private context identity.

### 21.4 StateLayout / PathAllocator

- Owns context-derived namespaces for `RunCtx`, `PhaseCtx`, `ItemCtx`,
  `DrainCtx`, `SelectionCtx`, and `RecoveryCtx`.
- Allocates generated bundle paths, projection views, reusable call write
  roots, entrypoint managed write roots, and compatibility views.
- Provides run-isolated private generated paths by default.
- Provides resume-stable allocation identity for the same run/call-frame/loop
  identity.
- Emits metadata consumed by runtime/executable, workflow boundary projection,
  source maps, and Semantic IR.

### 21.5 Adapter registry

- Stores certified adapter declarations.
- Records behavior class, effect class, owner, replacement path, and expiry
  for temporary bridges.
- Provides typed signatures to compiler/shared validation.
- Provides fixture and negative-fixture metadata for migration evidence.
- Rejects inline heredoc/raw shell/Python semantic glue in new high-level
  `.orc`.

### 21.6 Migration parity CLI

- Keeps `migration-parity` as machine-readable promotion evidence.
- Computes `non_regressive` from evidence; manifests and hand-authored reports
  cannot assert it.
- Adds parent-callable readiness labels and evidence roles.
- Requires valid, complete, current, parent-callable family evidence for
  `--require-non-regressive` where a family target is selected.
- Requires `eligible_for_primary_surface=true` for `--require-promotable`.

## 22. Dependencies And Sequencing

Tranche 0 must land first because stale inventory can cause reimplementation
of completed stdlib/foundation routes or premature parent-wrapper work.

Tranche 1 must land before the implementation phase, work item, or parent
drain can be represented as natural single `.orc` workflows. It is the most
important composition blocker.

Tranche 2 can land in parallel with Tranche 1 once branch proof metadata is
available. Union normalization and variant-scoped field identity reduce
authoring workarounds and make domain types independent from control-state
internals.

Tranche 3A should land before parent-callable phase compilation. It is the
next draftable prerequisite surfaced by the imported-child returned-variant
recovery: until it lands, the real plan/implementation/work-item routes can
clear the cross-union blocker and still fail on
`low_level_state_path_in_high_level_module` or
`workflow_boundary_type_invalid`.

The broader Tranche 3 bootstrap should land before promoted wrapper parity,
because public generated state roots and synthetic context inputs are not
acceptable evidence.

Tranche 4 depends on Tranche 1 for rich composition. It should not rebuild
existing stdlib routes; it should harden them under nested branches and
parent-callable contexts.

Tranche 5 can begin after foundation value transport and StateLayout are
stable. Selector publication may initially use certified adapter bridges, but
the target is typed projection.

Tranche 6 can begin as an inventory immediately, but enforcement for new
high-level `.orc` should become strict only after certified declaration
mechanics are available.

Tranche 7 should wait for at least the P0 portions of Tranches 1, 3A, 5, and
6, plus the broader Tranche 3 bootstrap before family promotion. It also
depends on the Tranche 2 imported-child returned-variant prerequisite whenever
a work-item or parent route matches child phase/classifier unions and returns
a different domain union. A parent drain or parent-callable work-item written
before then would likely recreate YAML-shaped Lisp, force outer result types
to mirror child control-state names, or re-expose low-level phase-state
surfaces at high-level boundaries.

Tranche 8 can proceed in parallel for report schema/readiness labels, but
promotable family evidence must wait for parent-callable workflows.

Work that can proceed in parallel:

- source/test inventory for current stdlib and design delta leaves;
- failing nested-control fixtures;
- union normalization and variant-field negative fixtures;
- adapter/helper classification inventory;
- projection contract sketches for selector bundle publication;
- parity-report label/schema updates; and
- drafting-guide documentation for temporary limitations (nested structured
  control, variant field naming, and `state/` path boundaries) while they
  remain unfixed.

## 23. Deferred Work

### 23.1 Runtime closures

Runtime closures remain deferred. The practical composition route is
compile-time `ProcRef`, `bind-proc`, `let-proc` where accepted, and
specialization before runtime artifacts are produced.

Do not use runtime closures to work around missing effectful composition,
nested structured control, stdlib expansion, or ProcRef specialization.

### 23.2 Broad legacy YAML lint enforcement

Do not hard-error all legacy YAML inline glue as part of this target. Legacy
workflows may remain warning/allowlist surfaces until selected for migration
or strict CI. New high-level `.orc` enforcement is in scope (Tranche 6);
legacy-wide hard errors are not.

### 23.3 `orchestrate explain`

`orchestrate explain` is valuable, but it should follow stable source maps,
Semantic IR layout entries, effect summaries, proof scopes, and path
allocation records. Until then, it risks becoming a brittle report generator
over moving internals.

## 24. Work Blocked Until This Target Lands

- Parent `.orc` drain implementation as a promotion candidate.
- YAML-primary replacement for the Design Delta Drain family.
- Treating split implementation leaves as parent-callable
  implementation-phase parity.
- Treating selector decision leaves as selector parity without bundle
  publication authority.
- Treating raw argv adapter calls as acceptable high-level `.orc` workflow
  semantics.
- Treating public state roots or synthetic `PhaseCtx` defaults as promoted
  boundary parity.
- Treating leaf compile success as `--require-promotable` evidence.
- Promoted `review-revise-loop` route that depends on a compiler branch keyed
  to the literal stdlib name.

## 25. Evidence And Implementation Boundaries

### 25.1 Required evidence

Nested structured control follows this design only if nested `match`, nested
`repeat_until`/`loop`, and stdlib calls inside branches compile, lower,
validate, source-map, and smoke without split-leaf workarounds.

Union normalization follows this design only if branch return normalization
derives the target variant from the returned expression and variant-scoped
output fields can reuse logical names across variants. The documented
restriction plus diagnostic is interim mitigation, not evidence.

Private context follows this design only if promoted public boundaries hide
generated state/write-root/context inputs while executable/runtime contracts
still receive the required private bindings, and resume reconstructs the same
private paths.

Phase-family boundary rehabilitation follows this design only if the real
design-delta `plan_phase.orc`, `implementation_phase.orc`, and `work_item.orc`
routes compile without `low_level_state_path_in_high_level_module`, generated
helper/private workflow boundaries stop failing with
`workflow_boundary_type_invalid`, and any retained YAML `state/` values are
labeled as private or compatibility-bridge bindings rather than public high-
level `.orc` inputs.

Imported/std reuse follows this design only if promoted fixtures pass through
ordinary import/specialization/typecheck/lowering without compiler-name
special casing and without runtime ref leakage.

Typed projection follows this design only if materialized bundles/views are
generated from validated typed state with declared authority class, source
maps, and StateLayout allocation.

Certified adapters follow this design only if adapter declarations provide
typed input/output/effect contracts, positive and negative fixtures,
path-safety rules, and source-map behavior, and every retained family helper
has a recorded classification.

Resource transitions follow this design only if run-state/resource updates
have declared version/conflict/idempotency semantics and are visible in shared
validation, Semantic IR, and parity evidence.

Promotion follows this design only if parent-callable family evidence is
valid, complete, current, and machine-computed.

### 25.2 Prohibited evidence

The following do not prove this target:

- a parent `.orc` wrapper that calls YAML-shaped scripts for core
  state/recovery semantics;
- a split implementation phase leaf pair used as proof of complete
  implementation-phase parity;
- a stdlib review loop that only works at top level;
- a compiler-specific review-loop lowering branch used by promoted fixtures;
- a nested-control fixture that only typechecks but is rejected by shared
  validation;
- branch-local generated refs accepted only because shared validation missed
  the scope error;
- union result types renamed to match inner control variants solely to satisfy
  lowering;
- verbose variant-specific field names used as evidence that repeated logical
  field names are supported;
- a drafting-guide restriction note plus compile-time diagnostic presented as
  variant-scoped identity completion;
- a plan/implementation/work-item candidate that still fails on
  `low_level_state_path_in_high_level_module` or
  `workflow_boundary_type_invalid` presented as parent-callable phase parity;
- public `state_root`, `manifest_path`, `progress_ledger_path`, or
  `__write_root__...` inputs in a promoted `.orc` boundary;
- a synthetic top-level `PhaseCtx` input presented as context bootstrap;
- legacy `state/` paths exposed as public `.orc` inputs under a lint waiver;
- a selector bundle path written by an uncertified script and then treated as
  semantic authority;
- a resource update hidden inside inline Python, shell, or an unclassified
  helper;
- a pointer file, report, stdout payload, or debug YAML projection treated as
  semantic state;
- hand-authored `non_regressive`; or
- a migration report without parent-callable evidence used to pass
  `--require-promotable`.

## 26. Compatibility And Migration

Existing YAML and `.orc` workflows remain valid. Existing split leaves may
remain as compile candidates and diagnostic fixtures. They should be labeled
as leaf candidates, not family parity.

Existing verbose variant-specific field names remain valid. They become
compatibility style once variant-scoped field identity is implemented. While
that gap remains open, the drafting guide must document the restriction and
the required naming style; that documentation is a migration note, not target
completion.

Existing helper scripts may remain during migration if they are classified
and, when semantically meaningful, certified or allowlisted with owner,
replacement path, and expiry. New high-level `.orc` libraries must not
introduce hidden semantic glue.

Existing public YAML state paths may remain public YAML inputs where YAML
already exposes them. A promoted high-level `.orc` wrapper must not expose
them as ordinary authored inputs unless parity explicitly says the user-facing
YAML boundary exposed them.

Existing prompt/report outputs remain useful views. They must not be promoted
to semantic authority.

Existing parity reports remain historical. Strict gates may reject old reports
that lack parent-callable readiness fields, source-map evidence,
resource-transition parity, or current freshness comparators.

## 27. Verification Strategy

### 27.1 Inventory tests

- Verify `std/phase.orc` exports current review/revise stdlib entrypoints.
- Verify any claimed implemented route has focused compile/typecheck/lowering
  evidence before a new gap tries to rebuild it.
- Verify Design Delta Drain leaf candidates are labeled leaf candidates, not
  parent-callable parity.
- Verify design-index/status entries do not describe completed foundation work
  as future work.
- Verify run-state or parity evidence backs any `implemented` status claim.

### 27.2 Nested structured-control tests

- Effectful `let*` with provider and command results.
- Effectful `match` branch containing provider and command results.
- `review-revise-loop` inside the `COMPLETED` branch of
  `ImplementationAttempt`.
- Nested `loop/recur` or `repeat_until` under a `match` branch.
- Same-file call using locally constructed records.
- Imported procedure containing provider/command effects under a branch.
- Branch-scope step ID collision fixtures across repeated branches and loop
  iterations.
- Resume identity stability for branch-scoped generated steps.
- Branch-local ref leakage negative fixture.
- Missing branch projection negative fixture.
- Unsupported nested shape diagnostic fixture.
- Source-map and Semantic IR generated path fixture.

### 27.3 Union and variant-output tests

- `ReviewLoopResult.APPROVED -> ImplementationPhaseResult.COMPLETED`.
- `ReviewLoopResult.EXHAUSTED -> ImplementationPhaseResult.REVIEW_EXHAUSTED`.
- `ImplementationAttempt.BLOCKED -> ImplementationPhaseResult.BLOCKED`.
- Cross-union mapping never raises `KeyError`; rejections are typed
  diagnostics.
- Ambiguous returned union variant diagnostic.
- Incompatible target union diagnostic.
- Repeated logical field names across variants: `APPROVED.plan_path`,
  `BLOCKED.plan_path`, `EXHAUSTED.plan_path`.
- Variant-scoped artifact/json-pointer identity.
- Source-map and Semantic IR entries for variant-scoped fields.

### 27.4 Private context tests

- Runtime-owned context hidden from public boundary for plan, selector,
  architect, work-item, and parent candidates.
- Synthetic top-level `PhaseCtx` input rejected as promotion evidence.
- Hidden reusable-call binding satisfies internal context parameters.
- Public defaults match YAML candidate.
- Shared validation sees correct public/private split.
- Resume reconstructs same private paths for same run/call/loop identity.
- YAML interop wrapper passes legacy `state/` values privately with
  migration-bridge labeling.
- Module-qualified imported context recognized by structural/capability
  checks (F1 regression).

### 27.4A Phase-family boundary rehabilitation tests

- `plan_phase.orc`, `implementation_phase.orc`, and `work_item.orc` clear
  `low_level_state_path_in_high_level_module` on their promoted high-level
  boundaries.
- The approved-arm helper/private-workflow route used by the real work-item
  candidate clears `workflow_boundary_type_invalid` when it carries phase
  context.
- Build-artifact inspection shows retained YAML `state/` values, if any, as
  private or compatibility-bridge bindings rather than public authored inputs.
- The parent-callable work-item compile fixture fails with another documented
  tranche diagnostic, if any remain, rather than with boundary/path-exposure
  errors owned by Tranche 3A.

### 27.5 Imported/std and review-loop tests

- Tiny imported helper.
- Imported helper with visible provider/command effects.
- Imported helper with match proof.
- Imported helper with loop state and source-map provenance.
- Denylist test for promoted stdlib-name compiler special casing.
- APPROVE.
- REVISE->APPROVE.
- BLOCKED.
- EXHAUSTED.
- Findings validation.
- Evidence redirection negative case.
- No runtime `ProcRef`/provider/prompt/type leak.
- Review loop inside a branch.
- Review loop inside a parent-callable phase.
- Nested-invocation resume checkpoint identity.

### 27.6 Projection tests

- Selector decision to selection bundle typed projection.
- Projection path allocation through `StateLayout`.
- Projection view not treated as semantic authority.
- Missing input bundle.
- Stale input.
- Schema mismatch.
- Path escape.
- Certified projection adapter positive and negative fixtures.
- Bridge-certified publication records its native replacement route.
- Downstream consumption of typed selection state without pointer/report
  authority.

### 27.7 Adapter/resource-transition tests

- Adapter declaration schema validation.
- Adapter typed input/output validation; wrong-typed field fails at
  compile/typecheck.
- Adapter output bundle authority.
- Adapter path-safety failure before launch.
- Adapter undeclared state/resource mutation negative fixture.
- New `.orc` raw semantic argv lint failure.
- Classification record exists for every retained migration-family helper.
- Resource transition success.
- Resource transition conflict.
- Resource transition idempotent retry.
- Resource transition resume/replay.
- Resource transition audit/source-map evidence.

### 27.8 Parent/backlog-drain tests

- Complete implementation phase as one parent-callable workflow.
- Work-item workflow calls child phases with hidden private contexts.
- Parent drain normal selected item path.
- Parent drain prerequisite path.
- Parent drain design-gap path.
- Parent drain blocked recovery path.
- Parent drain recovered-gap retry path.
- Parent drain terminal blocked path.
- Parent drain bounded exhaustion path.
- Parent-callable parity report includes resource-transition evidence.

### 27.9 Resume and migration parity tests

- Reusable approved prior result.
- Stale input hash.
- Missing artifact.
- Schema mismatch.
- Unsupported version.
- Failed/blocked prior terminal.
- Private context mismatch.
- Resource version conflict.
- Fresh/resumed branch normalization.
- Leaf-only evidence fails `--require-promotable`.
- Parent-callable but regressive evidence fails `--require-non-regressive`.
- Non-regressive but ineligible evidence passes non-regressive gate and fails
  promotable gate.
- Promotable family passes both gates.

## 28. Declarative Acceptance Scenarios

### 28.1 Nested implementation phase

Initial state: an implementation phase executes a provider attempt that may
return `COMPLETED` or `BLOCKED`.

Entrypoint: compile, shared validation, and fake-provider smoke for a `.orc`
workflow whose `COMPLETED` branch runs checks and then calls
`review-revise-loop`.

Expected result: the workflow compiles as one parent-callable phase,
branch-local refs validate by scope, review-loop steps run inside the
completed branch, source maps identify nested generated steps, and terminal
`ImplementationPhaseResult` is produced.

Forbidden result: the phase must be split into execute/review leaves solely
because nested structured control fails validation.

### 28.2 Union-to-union translation

Initial state: `ReviewLoopResult.APPROVED` must become
`ImplementationPhaseResult.COMPLETED`.

Entrypoint: compile and typecheck a `match` over `ReviewLoopResult` returning
a different domain union.

Expected result: lowering chooses the returned
`ImplementationPhaseResult.COMPLETED` variant.

Forbidden result: lowering looks up `APPROVED` in `ImplementationPhaseResult`
or forces the outer domain union to reuse inner variant names.

### 28.3 Variant-scoped fields

Initial state: a plan phase has `APPROVED.plan_path`, `BLOCKED.plan_path`, and
`EXHAUSTED.plan_path`.

Entrypoint: compile, shared validation, and source-map inspection.

Expected result: authored field names remain `plan_path`, lowered identities
are variant-scoped, and active variant validation requires only the active
variant's fields.

Forbidden result: authors must write `approved_plan_path`,
`blocked_plan_path`, and `exhausted_plan_path` solely to avoid
artifact/json-pointer collisions.

### 28.4 Private promoted entry context

Initial state: a promoted `.orc` wrapper calls a reusable phase requiring
`PhaseCtx`, while the legacy YAML caller still passes `state_root` and
`run_state_path`.

Entrypoint: compile, public-boundary inspection, dry-run, and resume.

Expected result: public inputs exclude `phase-ctx`, run id, state roots,
artifact roots, and generated write roots; hidden runtime bootstrap binds the
internal call; legacy values enter through the labeled YAML interop bridge;
resume reconstructs identical private paths; source maps and Semantic IR
explain the private context.

Forbidden result: a synthetic public `PhaseCtx` default or public `state_root`
input is used as parity evidence.

### 28.5 Selector typed projection

Initial state: a selector provider returns typed selection status and
evidence.

Entrypoint: run selector candidate and inspect downstream consumption.

Expected result: typed projection materializes a selection bundle view or
artifact from validated state, downstream consumes typed selection state, and
source maps identify projection authority.

Forbidden result: an uncertified publication script writes a pointer path and
downstream treats it as semantic selection authority.

### 28.6 Certified resource transition

Initial state: a work item completes and run state must record the terminal
outcome.

Entrypoint: execute a declared resource transition or certified adapter
transition.

Expected result: transition validates input resource version, writes declared
state/artifact effects, emits typed result, records audit/source-map evidence,
and is parity-comparable.

Forbidden result: a command adapter silently rewrites run state or recovery
ledger outside declared effects.

### 28.7 Parent backlog drain

Initial state: a drain has selectable items, possible prerequisites, possible
design gaps, and bounded attempts.

Entrypoint: fake-provider or controlled smoke of parent `.orc` drain.

Expected result: parent loop selects, runs item phase, handles design
gaps/recovery, records resource transitions, and emits typed terminal result
without public generated context inputs.

Forbidden result: parent `.orc` succeeds only because it delegates
state/routing to opaque YAML-era scripts.

### 28.8 Promotion gate

Initial state: all leaves compile, but parent-callable drain evidence is
missing.

Entrypoint:

```bash
python -m orchestrator migration-parity <targets> --require-promotable
```

Expected result: gate exits nonzero and reports leaf evidence as insufficient
for promotion.

Forbidden result: YAML primary is replaced because leaf compile/dry-run
evidence exists.

## 29. Success Criteria

This post-foundation target succeeds when:

- current-state inventory is accurate and maps all Design Delta Drain findings
  to implemented, blocked, or deferred work;
- nested structured control supports the canonical implementation-phase shape
  without split-leaf workarounds;
- branch scopes, proof scopes, effect summaries, source maps, Semantic IR
  entries, and generated path allocation survive nested normalization;
- union-to-union result mapping uses returned variants rather than matched
  source cases;
- variant-scoped output identity allows repeated logical field names across
  variants;
- the real implementation-phase candidate keeps parent-callable WCC evidence,
  and the remaining plan/work-item phase-family candidates clear the Tranche
  3A/WCC `IfExpr` boundary failures while keeping low-level phase-state roots
  and synthetic phase contexts out of promoted high-level `.orc` boundaries;
- promoted `.orc` entrypoints hide private runtime context, generated write
  roots, state roots, and compatibility paths from public boundaries;
- hidden reusable-call binding supplies internal `RunCtx`, `PhaseCtx`,
  `ItemCtx`, and `DrainCtx` values where required;
- imported/std `.orc` definitions preserve effects, source maps, proof scopes,
  loop state, and generated path provenance, and stdlib shape recognition is
  structural across module boundaries;
- current review/revise stdlib implementation is inventoried and hardened
  rather than rebuilt, and it compiles in promoted mode without compiler-name
  special casing;
- `review-revise-loop` composes inside branches and parent-callable phases
  with stable resume identity;
- typed projection or certified projection adapters provide selector/bundle
  publication authority;
- certified adapter declarations expose typed inputs, outputs, effects,
  path-safety rules, fixtures, and source maps, and every retained
  migration-family helper is classified;
- recurring run-state/resource semantics are represented as declared resource
  transitions or accepted certified bridges;
- a work-item and parent backlog-drain path can be expressed as typed `.orc`
  composition rather than hidden YAML-shaped state choreography;
- `resume-or-start` has canonical typed reusable-state validation;
- migration parity distinguishes leaf candidates, parent-callable candidates,
  family non-regression, and promotion eligibility;
- at least one real workflow family reaches strict, machine-computed
  `non_regressive=true` through `.orc`; and
- any YAML-primary replacement also passes `--require-promotable`.

## 30. Summary Recommendation

Use this document as the next target only after the foundation evidence is
confirmed and a current-state inventory pass updates stale claims. The next
implementation driver should select work from the issue map, not from roadmap
wording that predates the Design Delta Drain findings.

The key post-foundation move is to stop adding one-off frontend conveniences
and instead make Workflow Lisp a first-class workflow composition frontend:
nested structured control, principled result translation, ordinary
imported/std `.orc`, private runtime context, typed projection, certified
adapters, declared resource transitions, parent-callable family workflows, and
strict migration evidence.

After the imported-child returned-variant slice, the next draftable
prerequisite is Tranche 3A phase-family boundary rehabilitation for the real
plan/implementation/work-item candidates. Until that lands, parent-callable
work-item and drain work should remain blocked even if the cross-union route
compiles.

Until the P0 tranches land, the correct migration shape remains compileable
typed leaves, explicit bridge records, and no parent `.orc` wrapper pretending
to be a principled migration.
