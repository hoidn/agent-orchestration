# Workflow Lisp Q4 Judgment Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Every task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit. Track execution with
> the checkbox steps below.

**Goal:** Add a generic, read-only judgment-view projection that associates an
ordinary fragment-backed provider result with its exact Q3 prompt-attempt
evidence, then prove the surface with one bounded
`review_revise_design_docs` panel consumer.

**Architecture:** The ordinary composed-provider path co-persists one closed
attempt/result locator in `StepResult.debug` only after the result and all Q2
outputs validate. A pure projector resolves the result contract from the
run-bound, content-addressed compiled surface, validates the locator and Q3
evidence, and derives closed JSON and Markdown judgment views. One generic WCC
correction carries an already-typed `PathJoinUnderExpr` through a
`list/map-effect` child-call argument. The selected panel maps ordered lenses
to `ReviewReportPath` values and performs one ordinary extern-backed synthesis
call.

**Tech stack:** Python 3.11+, Workflow Lisp target 2.23 implementation with a
frozen target-2.21 compatibility control, Classic and WCC lowering, immutable
dataclasses/tuples, state schema 2.1, target-2.22 Q3
`workflow_prompt_attempt_identity.v1` and
`workflow_prompt_fragment_snapshot.functional.v2`, persisted compiled
surfaces, JSON/Markdown observability, pytest/pytest-xdist, and bounded
real-provider smoke evidence.

**Accepted design authority:** commit
`d7fe454902ff2f5b5784a66c37fbb19f9332e4ac`, tree
`499eec5e3461ff53086b3d066fa260b8ca8259d3`; exact reviewed design digest
`sha256:218f9e82be2848783bcf3a3c5282c47410cc66dca6e17b75fd0c81b3a9edac91`.
The design received ordered independent `Q4_DESIGN_SPEC_APPROVED` and then
distinct `Q4_DESIGN_QUALITY_APPROVED`.

**Accepted Q5-era design amendment:** commit
`3c21ceb40a53326e764cdaa7c5f4510cc3e61a2a`, tree
`1740b28f4e7c14db1cd6c49128a1f822141ba5cf`; exact amended design digest
`sha256:6c66f1890e9a19b2a70fb0ca5520a0e117baa2d092c7ff90466646adb407e8e1`.
The amendment received ordered independent
`Q4_DESIGN_AMENDMENT_SPEC_APPROVED` and then distinct
`Q4_DESIGN_AMENDMENT_QUALITY_APPROVED`. It changes the Q5-era consumer/import
binding only; the original accepted semantics and provenance remain
authoritative.

**Consumer-binding authority:** owner-adopted
`docs/reports/2026-07-27-q4-binding-decision-brief.md`, digest
`sha256:c309be8a683e12308d8250b357ac9e6999a58eece1073f8765855ae34af20165`.

**Plan status:** complete under reviewed amended plan `0f21636b` at commit
`f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
`ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record
SHA-256
`85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`.
It was accepted after ordered independent `Q4_PLAN_SPEC_APPROVED` then
distinct `Q4_PLAN_QUALITY_APPROVED`. Q5 Task 14 and canonical transplant
prerequisites are complete; M1 remains outside this plan.

**Execution status:** Task 0 closed on the lean external census record
`sha256:1bdb694da1fda43fb0ed71e842cd16e54956b86bb5106aea380a5e17f681c7`.
Tasks 1–8 landed at `9e18f884`, `4b400e7a` plus `7b96c547`, `88af8b91`,
`a3b75d76`, `4ca9e628`, `19a77547`, `6e987e23`, prompt-binding correction
`187336f7`, and Task 8 `000bfcfe`. Task 9's implicit-list ecosystem
correction landed at `0187392f`; focused verification passed 643 tests,
new-module collection found 91 tests, and the final broad replay reported
11,072 passed, 5 failed, 24 skipped, and 33 warnings. The five failures are
four inherited routing/retirement failures plus one xdist-only read-only LSP
build-digest race that passes in isolation. An earlier replay exposed a
Q4-owned missing route-registry row; the load-bearing correction now binds the
exact sibling path and surface in
`docs/workflow_lisp_route_readiness_registry.json`, and the post-correction
comparison has no Q4-owned failure. The external Task 9 and final reviews
approved the exact corrected candidate in the order
`Q4_TASK_9_SPEC_APPROVED`, `Q4_TASK_9_QUALITY_APPROVED`,
`Q4_FINAL_SPEC_APPROVED`, and `Q4_FINAL_QUALITY_APPROVED`. The reviewed bytes
landed at the commit/tree above, and the postcommit focused control passed 74
tests. No Q4 task or gate remains.

Task 2 later reached its explicit compatibility hard stop: the required
export edit necessarily changes source-lineage values and consistently
alpha-renames the parent loop's offset-bearing generated identities. The
corrected Task 2 gate below requires one ordered specification then quality
review of its exact design/plan bytes before execution resumes. It does not
re-open any completed Q5 or L-series gate.

---

## Entry Gate, Holds, And Deliberate Cost

Q3 is complete and the owner-adopted frontloaded consumer binding satisfies
Q4's entry gate. Design acceptance is complete. Planning is therefore
eligible.

The following guards remain binding:

- No Q4 mutation may overlap a live real-provider acceptance attempt whose
  byte freeze includes the same files. Task 0 proves no such attempt is live.
- Q5 Task 14 and the canonical transplant are complete. Task 0 binds the final
  landed Q5 bytes against this plan's ownership table. If a later commit
  changes prompt-attempt,
  `StepResult.debug`, persisted-surface, report, or example-family seams,
  update this plan and repeat ordered plan review before editing code.
- M1 estate shrink remains queued. Do not start, absorb, or prepare its
  deletion tranche under this plan.
- Do not edit security-, safety-, secrets-, or provider-isolation scope. The
  owner excluded that work from the active execution lane.

The deliberate cost is that workflows cannot consume, route on, or parse
judgment views. Adding a source `Judgment[T]`, a result envelope, or report
authority could make provenance-dependent workflow routing easier later, but
would violate the accepted Q4 boundary and require a new design.

---

## Governing Authorities

Read before implementation:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_lisp_judgment_views.md`;
- `docs/reports/2026-07-27-q4-binding-decision-brief.md`;
- `docs/design/workflow_lisp_prompt_calculus.md`;
- `docs/design/workflow_lisp_prompt_identity_diagnostics.md`;
- `docs/design/workflow_lisp_pure_list_traversal.md`;
- `docs/design/workflow_language_design_principles.md`, especially principles
  28, 29, and 30;
- `specs/state.md`, `specs/observability.md`, `specs/providers.md`,
  `specs/dsl.md`, and `specs/io.md`;
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- the completed Q1/Q2/Q3 plans; and
- this implementation plan, after its Q5-era amendment passes the ordered
  review gate above.

The accepted design wins over this plan. Normative specs win over
implementation. If a required implementation contradicts either authority,
stop and correct the plan/design; do not reinterpret the contract in code.

Principle 28 keeps semantic authority in validated results and existing
evidence. Principle 29 forbids a mandatory nominal result taxonomy.
Principle 30 keeps deterministic association, validation, and projection out
of provider prompts.

---

## Closed Scope And Non-Goals

This plan owns only:

- four additive exports producing the exact five-name export list on the
  current target-2.23 production module;
- one generic WCC child-call argument path for an existing typed
  `PathJoinUnderExpr`;
- a generic ordinary identity-v1 attempt/result locator;
- content-addressed persisted result-contract resolution;
- a pure closed judgment projection and JSON/Markdown integration;
- one target-2.23 ordinary-composed panel sibling and its ordinary
  extern-backed synthesis;
- deterministic clean/resume, compatibility, and bounded real-smoke evidence;
  and
- factual specs, docs, routing, and capability status.

This plan does not add or alter:

- source `Judgment`, `Judgment[T]`, evidence/prompt references, annotations, or
  a language target;
- result envelopes, new outcome unions, structural union coercion, open-record
  admissibility, implicit top values, or recursive `List[Union]` transport;
- report-derived workflow state, report parsing, result selection, majority
  routing, scoring, promotion, search, or evolution;
- prompt instructions carrying locator, identity, matrix, or disagreement
  obligations;
- Q5 `:delivery :phased`, identity-v2/evidence-v3, phase ledgers, coordinator,
  turn queue, interactive adapter, or provider registry;
- provider supervision/peer-group/live-binding behavior;
- source recompilation during report projection;
- current target-2.23 phased-entry behavior beyond the exact additive export
  list, or any byte of the frozen target-2.21 compatibility control; or
- M1 and excluded security/safety/secrets work.

Any test or implementation that appears to need one of those surfaces is a
hard stop, not permission to widen Q4.

---

## Execution And Review Contract

Run from the repository root. Do not create worktrees. Preserve unrelated
owner changes and stage only exact task files.

For every task:

1. dispatch a fresh implementation subagent with the task's exact ownership;
2. add the smallest behavioral RED test and show the intended failure;
3. implement the minimum generic correction;
4. run the narrow GREEN selectors and `pytest --collect-only` for every new or
   renamed test module;
5. run adjacent regression selectors;
6. request an independent specification review;
7. resolve findings and repeat specification review until approved;
8. only then request a distinct implementation-quality review;
9. resolve findings and repeat both reviews when bytes change materially; and
10. commit only after both ordered verdicts approve the exact task bytes.

Verdict names are task-scoped:

```text
Q4_TASK_N_SPEC_APPROVED
Q4_TASK_N_QUALITY_APPROVED
```

Final closure requires:

```text
Q4_FINAL_SPEC_APPROVED
Q4_FINAL_QUALITY_APPROVED
```

No repository document self-attests an external review of its own post-commit
bytes. Record exact reviewed commit/tree/digests factually after the verdict.

---

## Task 0: Re-open The Implementation Gate And Census Ownership

**Files:** external execution record only; no plan or production edits.

- [x] Prove no Q5 real-provider attempt is live.
- [x] Record Q5's final landed commit/tree in the external execution record
      and compare its changed paths with the Q4 ownership table below. Do not
      write that volatile value back into this reviewed plan.
- [x] Confirm the current target-2.23 phased production projection, the exact
      frozen target-2.21 control, and the original plus amended Q4 design
      bindings.
- [x] Confirm M1 is still held.
- [x] Confirm no protected/unrelated dirty file overlaps the task about to
      start.
- [x] Capture the fresh pre-Q4 broad non-security baseline with the exact Task
      9 command and bind its commit, tree, command, totals, failure rows, and
      excluded selectors in the external execution record before Task 1.
- [x] Obtain `Q4_TASK_0_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_0_QUALITY_APPROVED`.

Expected production ownership:

| Area | Expected files |
| --- | --- |
| normative contracts | `specs/state.md`, `specs/observability.md`, `specs/providers.md`, narrowly `specs/dsl.md` |
| WCC seam | `orchestrator/workflow_lisp/wcc/defunctionalize.py` and only a demonstrably necessary adjacent WCC projection helper |
| locator | `orchestrator/workflow/prompt_attempt_result_binding.py`, ordinary composed path in `orchestrator/workflow/executor.py`, existing step-result persistence helpers |
| persisted contract | `orchestrator/dashboard/compiled_workflow.py` plus the new pure projector |
| reports | new `orchestrator/workflow/judgment_views.py`, `orchestrator/observability/report.py`, `orchestrator/cli/commands/report.py` |
| consumer | current production example's export-only line, one target-2.23 composed sibling, ordinary provider/prompt bindings, and read-only frozen target-2.21 control |
| docs/routing | exact Q4 rows and routed docs only |

**Gate:** if overlap is behavioral rather than a shared import-only line,
update the component split and repeat `Q4_PLAN_SPEC_APPROVED` then
`Q4_PLAN_QUALITY_APPROVED` against every changed plan byte before Task 1.
Task 0 never edits this plan merely to record census or baseline facts.

---

## Task 1: Land Normative Contracts Before Runtime Code

**Files:**

- Modify `specs/state.md`.
- Modify `specs/observability.md`.
- Modify `specs/providers.md`.
- Modify only the WCC child-call argument clarification in `specs/dsl.md`.
- Do not modify `specs/io.md`; cite its unchanged Q2 validation boundary.
- Add or update exact routing-contract assertions in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`.

### Required normative deltas

- `state.md` owns the optional closed
  `workflow_prompt_attempt_result_binding.v1` debug locator, atomic
  co-persistence, and pre-Q4 compatibility.
- `observability.md` owns the exact stable `judgment_views` empty shape,
  available/unavailable rows, matrices, disagreements, iteration series,
  deterministic order, and state-only/bundle-backed parity.
- `providers.md` owns one successful attempt/result association, retry
  ordinal selection, and the ordinary identity-v1 eligibility predicate.
- `dsl.md` states only that the existing typed `path/join-under` expression
  may be evaluated in caller iteration scope and passed as an ordinary child
  input through the admitted WCC route.

### TDD and verification

- [x] Add routing/contract RED assertions for all four owners and the Q5
      exclusion.
- [x] Run the exact routing module and confirm RED.
- [x] Write the smallest normative deltas; do not copy the design wholesale.
- [x] Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_drain_roadmap_routing.py
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
```

- [x] Obtain `Q4_TASK_1_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_1_QUALITY_APPROVED`.
- [x] Commit Task 1.

---

## Task 2: Prove The Exact Export-Only Compatibility Gate

**Files:**

- Modify only the export declaration in
  `workflows/examples/review_revise_design_docs.orc`.
- Add a maintained target-2.23 same-target import/compile fixture under
  `tests/fixtures/workflow_lisp/judgment_views/`.
- Read but do not modify
  `tests/fixtures/workflow_lisp/prompt_calculus/review_revise_design_docs_target_2_21.orc`.
- Modify `tests/test_workflow_lisp_examples.py`.
- Modify `tests/test_workflow_lisp_prompt_calculus_e2e.py` only for compiled
  projection/identity characterization.

### Contract

The current production export list becomes exactly:

```lisp
(export
  review-revise-design-docs
  DesignDocPath
  ReviewReportTargetPath
  WorkReportPath
  review-design-doc)
```

No other current production source byte changes in this task. Keep the
declaration on its current source line so later authored line/column
coordinates do not move. Bind the source delta exactly:

```text
before sha256:89176c15dcaf29b5212441ad4776593d919880784fe0f531c9034b8a177640d7
after  sha256:8784501577c4f162f584a2ae17d1644a6bc4ea0c8bfbd18cdb0c1b7fd24a0598
```

Compile the before/after target-2.23 phased entry through the same route and
compare a selected semantic workflow-entry projection. First require the
source-position relation itself:

- old/new source sizes are exactly 8,079/8,149 bytes;
- excluding the intentionally changed export span, every
  current-production position before it is exact;
- every current-production position after it retains path, line, and column
  and has `after.offset == before.offset + 70`; and
- imported and prelude positions are exact.

Apply that check to every source position reachable from the selected
compiled projection, including type references that seed specialization
identity.

Build `q4_task2_export_compatibility.v1` with exactly these keys:

```text
schema_version
target_dsl
entry.name
entry.inputs
entry.outputs
phased_review.provider_call_policy
phased_review.compiled_prompt_fragment_identity
phased_review.prompt_attempt_identity_version
phased_review.compiler_prompt_fragment_contract
phased_review.expected_outputs
phased_review.variant_output
phased_review.runtime_plan
phased_review.source_map
parent_checkpoint_point_kinds
parent_authored_source_coordinates
```

`schema_version` is the literal contract name above.
`parent_authored_source_coordinates` contains only ordered authored form paths
and path/line/column coordinates; it omits generated subject keys and raw byte
offsets, which are checked by the separate `+70` relation. This exact
projection must be byte-identical. It deliberately makes no equality claim
for the changed source SHA, parent specialization/WCC/checkpoint/allocation
identities, or digests derived from them.

Separately serialize the phased helper bundle canonically and require its
recursive before/after diff to contain exactly six leaves. Each leaf is
`compiler_prompt_dependency_contract.source_workflow_sha256`; the locations
are `surface.steps[0]`,
`core_workflow_ast._surface_workflow.steps[0]`,
`core_workflow_ast.body[0]`,
`core_workflow_ast.body[0]._surface_step`, the helper provider node's
executable-IR `execution_config`, and the helper prompt surface in semantic
IR. All six before values equal the bound old SHA-256 and all six after values
equal the bound new SHA-256. A missing, additional, differently named, or
differently valued leaf fails. Do not add a reusable alpha normalizer,
derived-digest manifest, or new production machinery for this test.

Without normalization, require the target, public input/result contracts,
explicit phased delivery, materialization-attempt count, prompt fragment
identity-v2, functional-v3 schema, provider configuration, and phased-helper
checkpoint/runtime plan to remain exact. Require the parent checkpoint
topology and point kinds, every authored form path, and the complete
source-position relation to remain exact. Independently require the frozen
target-2.21 fixture to retain its exact pre-task SHA-256 and keep it off the
sibling's import-resolution path.

The changed workflow checksum means pre-export runs are not resumable against
the post-export source; ordinary checksum validation remains fail closed. Task
0 proved no active Q5 orchestrator/provider attempt is stranded. Task 2 makes
no cross-source-revision resume claim and changes no compiler or runtime
checksum behavior.

### TDD and verification

- [x] Add a RED target-2.23 same-target import fixture requiring all four newly
      exported names from current production.
- [x] Add a RED whole-entry comparison that exposes the raw source-lineage and
      parent generated-identity delta; do not accept a helper-only false
      green.
- [x] Add the exact named behavior projection, exact source
      before/after digests and sizes, complete `+70` source-position relation,
      exact six-leaf helper diff, exact invariants, and an exact byte-digest
      control for the frozen target-2.21 fixture.
- [x] Show the sibling fails before the export delta.
- [x] Apply only the export delta.
- [x] Prove sibling compile GREEN, current phased-entry projection
      byte-identical, the helper diff exactly six source-SHA leaves, all
      invariants exact, and frozen target-2.21 bytes unchanged.
- [x] Run the two named modules plus their `--collect-only` selectors.
- [x] Obtain `Q4_TASK_2_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_2_QUALITY_APPROVED`.
- [x] Commit Task 2.

**Hard stop:** do not bump or otherwise mutate current production beyond its
export line, import from or modify the frozen fixture, copy/redeclare the
fragment, change compiler/runtime checksum semantics, claim cross-revision
resume compatibility, accept a semantic/provider/phased-helper checkpoint or
runtime-plan delta, violate the exact source-position relation, add
normalization or digest-manifest machinery, accept a seventh helper-diff
leaf, or weaken either comparison.

---

## Task 3: Carry `PathJoinUnderExpr` Through One WCC Child Argument

**Files:**

- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`.
- Modify another WCC file only if the RED trace proves that file owns the
  missing projection.
- Modify `tests/test_workflow_lisp_list_traversal.py`.
- Add one generic Classic/WCC fixture under
  `tests/fixtures/workflow_lisp/judgment_views/`; it must contain no panel or
  family names.

### Contract

Evaluate an already-typed `PathJoinUnderExpr` in the caller's
`list/map-effect` iteration scope and bind its resulting rooted-path value as
an ordinary child-workflow input. Preserve the one-boundary map rule, source
mapping, Classic/WCC value agreement, and existing
`path_join_under_child_invalid` / `path_join_under_escape` refusals.

### TDD and verification

- [x] RED: generic map child-call argument fails at the current
      `workflow_return_not_exportable` seam.
- [x] RED opposite directions: invalid child and escaping child retain their
      exact diagnostics; a function-call/prompt-fill broadening remains
      refused.
- [x] Implement the smallest projection case.
- [x] GREEN: Classic and WCC produce the same typed child input and map result.
- [x] Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_list_traversal.py
pytest -q tests/test_workflow_lisp_list_traversal.py
pytest -q tests/test_workflow_lisp_expressions.py
```

- [x] Genericity scan production diff for consumer/family/module/provider
      names.
- [x] Obtain `Q4_TASK_3_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_3_QUALITY_APPROVED`.
- [x] Commit Task 3.

**Hard stop:** fragment-fill identity changes, new node kinds/operators,
multiple map boundaries, pure-helper support, or collection widening return
to design.

---

## Task 4: Co-persist The Generic Attempt/Result Locator

**Files:**

- Add `orchestrator/workflow/prompt_attempt_result_binding.py`.
- Modify the ordinary composed-provider success path in
  `orchestrator/workflow/executor.py`.
- Modify existing step-result conversion only if a RED proves `debug` is not
  already preserved.
- Add `tests/test_prompt_attempt_result_binding.py`.
- Extend ordinary provider, call-frame, loop, Q3, and resume tests.

### Contract

Eligibility requires the complete structural predicate from the design:
direct fragment-backed call, ordinary composed delivery, exact identity-v1,
exact functional-v2 evidence embedding identity-v1, root-owned scope, one
unique publication, and one validated committed result. Target version and
names are not selectors.

Attach the exact closed locator only after output-bundle/result-contract and
all Q2 output-position validations succeed, using the retained
`PublicationResult` and exact scope/ordinal. Result and locator enter reached
state in the same existing mutation.

### TDD and verification

- [x] RED: eligible successful ordinary call has no locator.
- [x] RED/negative: provider, bundle, contract, Q2, and pre-commit
      interruption failures commit no locator.
- [x] RED/negative: malformed, missing, ambiguous, or contradictory retained
      publication/scope/ordinal data makes locator construction fail before
      the existing reached-result mutation; neither the result nor locator
      commits.
- [x] Positive coexistence: a target-2.23 `:delivery :composed` call retains
      identity-v1/functional-v2 evidence and remains eligible for the same
      locator.
- [x] RED/negative: Q5 phased identity-v2 is excluded before construction and
      does not receive a missing-binding marker.
- [x] Cover top-level, child call, and generated `list/map-effect` iteration.
- [x] Cover failed-then-successful retry: only the committed ordinal binds.
- [x] Cover completed-boundary resume: no provider/evidence access and exact
      locator reuse.
- [x] Run new-module `--collect-only`, narrow locator tests, Q3 prompt identity,
      subworkflow, loop, and resume selectors.
- [x] Obtain `Q4_TASK_4_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_4_QUALITY_APPROVED`.
- [x] Commit Task 4.

---

## Task 5: Resolve Result Contracts From Persisted Surfaces Only

**Files:**

- Modify `orchestrator/dashboard/compiled_workflow.py` only to expose a
  reusable validated traversal over its existing persisted surface.
- Add the result-contract resolver inside
  `orchestrator/workflow/judgment_views.py`.
- Add `tests/test_workflow_judgment_result_contracts.py`.
- Extend persisted compiled-surface/dashboard tests.

### Contract

Both bundle-backed and state-only projection call the same resolver. It starts
from `state.runtime_observability.compiled_frontend.persisted_workflow_surface`,
validates the build-manifest digest, traverses call frames by persisted
`import_alias`, and resolves exactly one reached step contract and digest.
It never recompiles retained/current source, trusts an unbound live bundle,
or synthesizes a contract from the value.

### TDD and verification

- [x] RED: state-only nested call cannot resolve its exact persisted contract.
- [x] Positive: root, child-call, and loop coordinates resolve identically in
      bundle-backed and state-only paths.
- [x] Both-direction tamper coverage: missing graph, digest mismatch, unknown
      alias, missing/extra/ambiguous contract, old-source mutation, and
      coordinate mismatch fail closed.
- [x] Prove source compile entry points are not invoked.
- [x] Run new-module `--collect-only`, dashboard compiled-workflow tests,
      CLI-report state-only tests, and adjacent prompt-context parity tests.
- [x] Obtain `Q4_TASK_5_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_5_QUALITY_APPROVED`.
- [x] Commit Task 5.

---

## Task 6: Implement Closed Judgment Projection And Reports

**Files:**

- Complete `orchestrator/workflow/judgment_views.py`.
- Modify `orchestrator/observability/report.py`.
- Modify `orchestrator/cli/commands/report.py`.
- Add `tests/test_workflow_judgment_views.py`.
- Extend `tests/test_observability_report.py` and
  `tests/test_cli_report_command.py`.

### Contract

Implement the design's exact closed schemas:

- `workflow_judgment_views.v1`;
- available/unavailable `workflow_judgment_inspection.v1`;
- `workflow_judgment_matrix.v1`;
- `workflow_judgment_disagreement.v1`; and
- `workflow_judgment_iteration_series.v1`.

Use exact scope/call-frame/visit/loop/root-checksum authority and canonical
ordering. Comparison keys are only canonical primitive/enum values or exact
union variant names. Records/lists/maps/paths/top values are
`not_comparable`. Unavailable rows never vote. JSON and Markdown derive from
one validated projection. No execution/resume/parser module imports it.

### TDD and verification

- [x] RED stable empty sibling for old/ineligible runs in loaded and
      state-only reports.
- [x] Positive/tamper rows for locator, publication, evidence, identity,
      contract, value, and coordinate validation.
- [x] All four disagreement classifications in both directions.
- [x] Tri-state attempt series: `bound`, `not_bound`, and
      `unknown_pre_q4`.
- [x] Deterministic order under reversed filesystem/discovery/completion
      order.
- [x] JSON/Markdown equivalence and content-free Markdown provenance.
- [x] Import scans prove execution, resume, parser, and workflow code do not
      consume the projector.
- [x] Run new-module `--collect-only`, all three report modules,
      prompt-context report regressions, and state-only CLI regressions.
- [x] Obtain `Q4_TASK_6_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_6_QUALITY_APPROVED`.
- [x] Commit Task 6.

---

## Task 7: Land The Exact Panel Consumer

**Files:**

- Add
  `workflows/examples/review_revise_design_docs_judgment_panel.orc`.
- Add ordinary provider bindings at
  `workflows/examples/inputs/review_revise_design_docs_judgment_panel/providers.json`
  and the ordinary extern-backed synthesis prompt at
  `prompts/workflows/review_revise_design_docs/synthesize.md`.
- Add deterministic fixtures under
  `tests/fixtures/workflow_lisp/judgment_views/`.
- Extend `tests/test_workflow_lisp_examples.py` and
  `tests/test_workflow_lisp_prompt_calculus_e2e.py`.
- Add `tests/test_workflow_lisp_judgment_views_e2e.py`.

### Contract

The sibling is target 2.23, imports the exported types and
`review-design-doc` from current production, and never resolves imports
through the frozen target-2.21 control. Every fragment-backed review call
specifies exact `:delivery :composed`, retaining identity-v1/functional-v2;
the current production entry remains phased identity-v2/functional-v3 and
Q4-ineligible.

The public checked default uses pairwise-distinct safe lens strings. Each
`list/map-effect :max 8` iteration performs exactly one child call. The child
owns the existing fragment-backed `ReviewDecision`, matches every existing
variant to its common `review_report`, and returns `ReviewReportPath`. The map
returns `List[ReviewReportPath]`.

One extern-backed synthesis call consumes only the ordinary target and ordered
report paths, returns `ReviewReportPath`, remains Q4-ineligible, and produces
no second matrix. The public entry returns exact `DesignDocPanelResult`.

### TDD and verification

- [x] RED: the exact public sibling import/compile acceptance test fails on
      the Task 7 baseline because the sibling and its provider/prompt
      bindings do not yet exist. Do not cite the already-landed Task 3 seam
      as this task's RED.
- [x] Positive compile/runtime with ordered distinct lenses and exactly one
      matrix.
- [x] Prove the sibling imports current production at target 2.23, every
      fragment-backed review call is explicitly composed and retains
      identity-v1/functional-v2, and the frozen target-2.21 control is not an
      import owner.
- [x] Prove the child retains the full union, Q2 output contract, identity-v1,
      and source-map owner.
- [x] Prove synthesis has no fragment identity/locator/judgment row and its
      prompt receives no Q3/Q4 projection.
- [x] Unsafe/escaping lenses fail before provider launch.
- [x] Characterize duplicate destinations without claiming cross-iteration
      uniqueness enforcement.
- [x] Retain direct `List[ReviewDecision]` and multi-boundary wrapper
      refusals.
- [x] Run all new/renamed `--collect-only` selectors and focused example,
      calculus, list-traversal, and E2E modules.
- [x] Obtain `Q4_TASK_7_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_7_QUALITY_APPROVED`.
- [x] Commit Task 7.

---

## Task 8: Prove Clean/Resume Determinism And Bounded Real Use

**Files:**

- Extend `tests/test_workflow_lisp_judgment_views_e2e.py`.
- Add
  `tests/e2e/test_e2e_workflow_lisp_judgment_views.py`.
- Do not modify production behavior in this task.

### Deterministic gate

- [x] Collect both owned modules exactly:

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_judgment_views_e2e.py \
  tests/e2e/test_e2e_workflow_lisp_judgment_views.py
```

- [x] Run one clean panel and one interrupted-after-committed-child/resumed
      panel in isolated roots.
- [x] Compare typed final result, artifact bytes, provider-attempt identities,
      locator bytes, judgment views, and synthesis-call count.
- [x] Prove completed children are not replayed and no result/evidence is read
      to prepare a provider.
- [x] Remove one evidence record after completion and prove only the affected
      view becomes unavailable while result/resume compatibility remains.
- [x] Run the complete deterministic module exactly:

```bash
pytest -q tests/test_workflow_lisp_judgment_views_e2e.py
```

### Real-provider gate

- [x] Run only after every deterministic selector is green and no Q5 attempt
      is live.
- [x] Use a trusted checkout and the repo-standard dangerous-bypass provider
      launch so no directory-trust/approval prompt can stall the run.
- [x] Use the checked pairwise-distinct default lens set and a bounded
      deadline. Each of the three review calls and the synthesis call retains
      the design's exact `:timeout-sec 3600`; the outer acceptance command has
      a numeric 15,000-second deadline.
- [x] Do not steer panes or substitute split/synthetic proof.
- [x] Require natural terminal completion, ordered reports, one synthesis,
      one matrix, valid state-only/loaded views, and zero replay on resume.
- [x] Assert in the E2E preflight that every Codex provider argv contains
      `--dangerously-bypass-approvals-and-sandbox` and that every invocation
      cwd is the trusted checkout.
- [x] From that trusted checkout, preserve the exact command output at
      `artifacts/review/q4-task8-real-provider.log` and run:

```bash
mkdir -p artifacts/review
set -o pipefail
timeout --foreground --signal=TERM --kill-after=30s 15000s \
  env ORCHESTRATE_E2E=1 \
      ORCHESTRATE_E2E_TRUSTED_CHECKOUT="$PWD" \
      PYTHONWARNINGS=error \
  pytest -q -s \
    tests/e2e/test_e2e_workflow_lisp_judgment_views.py::test_judgment_views_real_provider_panel \
  2>&1 | tee artifacts/review/q4-task8-real-provider.log
```

- [x] The Task 8 external execution record binds the exact commit/tree,
      command, log SHA-256, start/finish timestamps, exit code, terminal run
      ID/root, provider call count, and the loaded/state-only view digests.

- [x] Obtain `Q4_TASK_8_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_8_QUALITY_APPROVED`.
- [x] Commit Task 8 evidence/test bytes.

---

## Task 9: Close Docs, Routing, And Broad Non-Security Verification

**Files:**

- `docs/design/workflow_lisp_judgment_views.md`;
- `docs/design/README.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `docs/workflow_lisp_route_readiness_registry.json`;
- exact Q4 row/section in the active Q/L roadmap;
- exact Q4 expectations in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`; and
- this plan's factual implementation status.

### Closure

- [x] Re-run all Task 1–8 focused selectors.
- [x] Run `pytest --collect-only` for every new/renamed test module.
- [x] Run the repository's broad non-security suite with required parallelism:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_execution_safety.py \
  --ignore=tests/test_provider_isolation_attestation.py \
  --ignore=tests/test_provider_isolation_backend.py \
  --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
  --ignore=tests/test_provider_isolation_bundle_broker.py \
  --ignore=tests/test_provider_isolation_candidate.py \
  --ignore=tests/test_provider_isolation_controller_lifecycle.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_isolation_execution.py \
  --ignore=tests/test_provider_isolation_network_preflight.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_runtime_authority.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_workflow_continuation.py \
  --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  --ignore=tests/test_workflow_provider_isolation_integration.py \
  -k 'not security and not secret and not isolation and not safety'
```

- [x] Compare against Task 0's content-addressed fresh pre-Q4 baseline; do not
      repair external or excluded failures under Q4.
- [x] Run genericity scans and prove no consumer/family/module/provider/result
      name controls mechanism behavior.
- [x] Verify current target-2.23 phased-entry projection compatibility and the
      frozen target-2.21 byte control again.
- [x] Verify Q5 phased identity-v2 remains excluded and unchanged.
- [x] Update docs from designed/planned to implemented only after evidence is
      green.
- [x] Obtain `Q4_TASK_9_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_TASK_9_QUALITY_APPROVED`.
- [x] Obtain ordered `Q4_FINAL_SPEC_APPROVED`.
- [x] Obtain distinct `Q4_FINAL_QUALITY_APPROVED`.
- [x] Commit the reviewed closure bytes.
- [x] Run a fresh postcommit focused control and record the exact commit/tree.

Stage Q4 completed at commit
`f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
`ccec170be8757c9e4fd5ed8ece6f93b04fc03299`. The external closure record at
SHA-256
`85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`
binds candidate-diff SHA-256
`131e6cc7cc87e52f14a47a05d581fcb5770f0cf4923643ba3d398b739034aeb9`,
Task-9 execution-record SHA-256
`d3ab15956d3c742859cba839e11a660dd4c16fa19650eece4f24dad8da8a18d3`,
the four ordered approval tokens above, and the 74-pass postcommit control.
Q4 completion does not select M1 or any parked roadmap.
