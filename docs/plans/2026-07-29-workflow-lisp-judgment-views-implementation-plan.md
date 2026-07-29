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

**Plan status:** the original plan was accepted after ordered independent
`Q4_PLAN_SPEC_APPROVED` then distinct `Q4_PLAN_QUALITY_APPROVED`. The Q5-era
plan amendment below becomes execution authority only after the
same ordered reviews approve its exact bytes. Q5 Task 14 and canonical
transplant prerequisites are complete; M1 remains outside this plan.

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

- [ ] Prove no Q5 real-provider attempt is live.
- [ ] Record Q5's final landed commit/tree in the external execution record
      and compare its changed paths with the Q4 ownership table below. Do not
      write that volatile value back into this reviewed plan.
- [ ] Confirm the current target-2.23 phased production projection, the exact
      frozen target-2.21 control, and the original plus amended Q4 design
      bindings.
- [ ] Confirm M1 is still held.
- [ ] Confirm no protected/unrelated dirty file overlaps the task about to
      start.
- [ ] Capture the fresh pre-Q4 broad non-security baseline with the exact Task
      9 command and bind its commit, tree, command, totals, failure rows, and
      excluded selectors in the external execution record before Task 1.
- [ ] Obtain `Q4_TASK_0_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_0_QUALITY_APPROVED`.

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

- [ ] Add routing/contract RED assertions for all four owners and the Q5
      exclusion.
- [ ] Run the exact routing module and confirm RED.
- [ ] Write the smallest normative deltas; do not copy the design wholesale.
- [ ] Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_drain_roadmap_routing.py
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
```

- [ ] Obtain `Q4_TASK_1_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_1_QUALITY_APPROVED`.
- [ ] Commit Task 1.

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

No other current production source byte changes in this task. Compile the
before/after target-2.23 phased entry through the same route and compare its
selected canonical workflow-entry projection byte-for-byte; the module export
catalog is deliberately excluded from that comparison because this task
changes it. The target, explicit phased delivery, materialization-attempt
count, prompt fragment identity-v2, functional-v3 evidence contract, result
contract, checkpoint/resume identity, and source mapping must remain
unchanged. Independently require the frozen target-2.21 fixture to retain its
exact pre-task SHA-256 and keep it off the sibling's import-resolution path.

### TDD and verification

- [ ] Add a RED target-2.23 same-target import fixture requiring all four newly
      exported names from current production.
- [ ] Add a byte-projection control for the current phased entry and an exact
      byte-digest control for the frozen target-2.21 fixture.
- [ ] Show the sibling fails before the export delta.
- [ ] Apply only the export delta.
- [ ] Prove sibling compile GREEN, current phased-entry projection
      byte-identical, and frozen target-2.21 bytes unchanged.
- [ ] Run the two named modules plus their `--collect-only` selectors.
- [ ] Obtain `Q4_TASK_2_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_2_QUALITY_APPROVED`.
- [ ] Commit Task 2.

**Hard stop:** do not bump or otherwise mutate current production beyond its
export line, import from or modify the frozen fixture, copy/redeclare the
fragment, accept a phased-delivery/identity/evidence/checksum/resume delta, or
weaken either comparison.

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

- [ ] RED: generic map child-call argument fails at the current
      `workflow_return_not_exportable` seam.
- [ ] RED opposite directions: invalid child and escaping child retain their
      exact diagnostics; a function-call/prompt-fill broadening remains
      refused.
- [ ] Implement the smallest projection case.
- [ ] GREEN: Classic and WCC produce the same typed child input and map result.
- [ ] Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_list_traversal.py
pytest -q tests/test_workflow_lisp_list_traversal.py
pytest -q tests/test_workflow_lisp_expressions.py
```

- [ ] Genericity scan production diff for consumer/family/module/provider
      names.
- [ ] Obtain `Q4_TASK_3_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_3_QUALITY_APPROVED`.
- [ ] Commit Task 3.

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

- [ ] RED: eligible successful ordinary call has no locator.
- [ ] RED/negative: provider, bundle, contract, Q2, and pre-commit
      interruption failures commit no locator.
- [ ] RED/negative: malformed, missing, ambiguous, or contradictory retained
      publication/scope/ordinal data makes locator construction fail before
      the existing reached-result mutation; neither the result nor locator
      commits.
- [ ] Positive coexistence: a target-2.23 `:delivery :composed` call retains
      identity-v1/functional-v2 evidence and remains eligible for the same
      locator.
- [ ] RED/negative: Q5 phased identity-v2 is excluded before construction and
      does not receive a missing-binding marker.
- [ ] Cover top-level, child call, and generated `list/map-effect` iteration.
- [ ] Cover failed-then-successful retry: only the committed ordinal binds.
- [ ] Cover completed-boundary resume: no provider/evidence access and exact
      locator reuse.
- [ ] Run new-module `--collect-only`, narrow locator tests, Q3 prompt identity,
      subworkflow, loop, and resume selectors.
- [ ] Obtain `Q4_TASK_4_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_4_QUALITY_APPROVED`.
- [ ] Commit Task 4.

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

- [ ] RED: state-only nested call cannot resolve its exact persisted contract.
- [ ] Positive: root, child-call, and loop coordinates resolve identically in
      bundle-backed and state-only paths.
- [ ] Both-direction tamper coverage: missing graph, digest mismatch, unknown
      alias, missing/extra/ambiguous contract, old-source mutation, and
      coordinate mismatch fail closed.
- [ ] Prove source compile entry points are not invoked.
- [ ] Run new-module `--collect-only`, dashboard compiled-workflow tests,
      CLI-report state-only tests, and adjacent prompt-context parity tests.
- [ ] Obtain `Q4_TASK_5_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_5_QUALITY_APPROVED`.
- [ ] Commit Task 5.

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

- [ ] RED stable empty sibling for old/ineligible runs in loaded and
      state-only reports.
- [ ] Positive/tamper rows for locator, publication, evidence, identity,
      contract, value, and coordinate validation.
- [ ] All four disagreement classifications in both directions.
- [ ] Tri-state attempt series: `bound`, `not_bound`, and
      `unknown_pre_q4`.
- [ ] Deterministic order under reversed filesystem/discovery/completion
      order.
- [ ] JSON/Markdown equivalence and content-free Markdown provenance.
- [ ] Import scans prove execution, resume, parser, and workflow code do not
      consume the projector.
- [ ] Run new-module `--collect-only`, all three report modules,
      prompt-context report regressions, and state-only CLI regressions.
- [ ] Obtain `Q4_TASK_6_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_6_QUALITY_APPROVED`.
- [ ] Commit Task 6.

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

- [ ] RED: the exact public sibling import/compile acceptance test fails on
      the Task 7 baseline because the sibling and its provider/prompt
      bindings do not yet exist. Do not cite the already-landed Task 3 seam
      as this task's RED.
- [ ] Positive compile/runtime with ordered distinct lenses and exactly one
      matrix.
- [ ] Prove the sibling imports current production at target 2.23, every
      fragment-backed review call is explicitly composed and retains
      identity-v1/functional-v2, and the frozen target-2.21 control is not an
      import owner.
- [ ] Prove the child retains the full union, Q2 output contract, identity-v1,
      and source-map owner.
- [ ] Prove synthesis has no fragment identity/locator/judgment row and its
      prompt receives no Q3/Q4 projection.
- [ ] Unsafe/escaping lenses fail before provider launch.
- [ ] Characterize duplicate destinations without claiming cross-iteration
      uniqueness enforcement.
- [ ] Retain direct `List[ReviewDecision]` and multi-boundary wrapper
      refusals.
- [ ] Run all new/renamed `--collect-only` selectors and focused example,
      calculus, list-traversal, and E2E modules.
- [ ] Obtain `Q4_TASK_7_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_7_QUALITY_APPROVED`.
- [ ] Commit Task 7.

---

## Task 8: Prove Clean/Resume Determinism And Bounded Real Use

**Files:**

- Extend `tests/test_workflow_lisp_judgment_views_e2e.py`.
- Add
  `tests/e2e/test_e2e_workflow_lisp_judgment_views.py`.
- Do not modify production behavior in this task.

### Deterministic gate

- [ ] Collect both owned modules exactly:

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_judgment_views_e2e.py \
  tests/e2e/test_e2e_workflow_lisp_judgment_views.py
```

- [ ] Run one clean panel and one interrupted-after-committed-child/resumed
      panel in isolated roots.
- [ ] Compare typed final result, artifact bytes, provider-attempt identities,
      locator bytes, judgment views, and synthesis-call count.
- [ ] Prove completed children are not replayed and no result/evidence is read
      to prepare a provider.
- [ ] Remove one evidence record after completion and prove only the affected
      view becomes unavailable while result/resume compatibility remains.
- [ ] Run the complete deterministic module exactly:

```bash
pytest -q tests/test_workflow_lisp_judgment_views_e2e.py
```

### Real-provider gate

- [ ] Run only after every deterministic selector is green and no Q5 attempt
      is live.
- [ ] Use a trusted checkout and the repo-standard dangerous-bypass provider
      launch so no directory-trust/approval prompt can stall the run.
- [ ] Use the checked pairwise-distinct default lens set and a bounded
      deadline. Each of the three review calls and the synthesis call retains
      the design's exact `:timeout-sec 3600`; the outer acceptance command has
      a numeric 15,000-second deadline.
- [ ] Do not steer panes or substitute split/synthetic proof.
- [ ] Require natural terminal completion, ordered reports, one synthesis,
      one matrix, valid state-only/loaded views, and zero replay on resume.
- [ ] Assert in the E2E preflight that every Codex provider argv contains
      `--dangerously-bypass-approvals-and-sandbox` and that every invocation
      cwd is the trusted checkout.
- [ ] From that trusted checkout, preserve the exact command output at
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

- [ ] The Task 8 external execution record binds the exact commit/tree,
      command, log SHA-256, start/finish timestamps, exit code, terminal run
      ID/root, provider call count, and the loaded/state-only view digests.

- [ ] Obtain `Q4_TASK_8_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_8_QUALITY_APPROVED`.
- [ ] Commit Task 8 evidence/test bytes.

---

## Task 9: Close Docs, Routing, And Broad Non-Security Verification

**Files:**

- `docs/design/workflow_lisp_judgment_views.md`;
- `docs/design/README.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- exact Q4 row/section in the active Q/L roadmap;
- exact Q4 expectations in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`; and
- this plan's factual implementation status.

### Closure

- [ ] Re-run all Task 1–8 focused selectors.
- [ ] Run `pytest --collect-only` for every new/renamed test module.
- [ ] Run the repository's broad non-security suite with required parallelism:

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

- [ ] Compare against Task 0's content-addressed fresh pre-Q4 baseline; do not
      repair external or excluded failures under Q4.
- [ ] Run genericity scans and prove no consumer/family/module/provider/result
      name controls mechanism behavior.
- [ ] Verify current target-2.23 phased-entry projection compatibility and the
      frozen target-2.21 byte control again.
- [ ] Verify Q5 phased identity-v2 remains excluded and unchanged.
- [ ] Update docs from designed/planned to implemented only after evidence is
      green.
- [ ] Obtain `Q4_TASK_9_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_TASK_9_QUALITY_APPROVED`.
- [ ] Obtain ordered `Q4_FINAL_SPEC_APPROVED`.
- [ ] Obtain distinct `Q4_FINAL_QUALITY_APPROVED`.
- [ ] Commit the reviewed closure bytes.
- [ ] Run a fresh postcommit focused control and record the exact commit/tree.

Stage Q4 is complete only after every task, ordered review, deterministic
gate, bounded real smoke, and broad non-security comparison above is complete.
Q4 completion does not select M1 or any parked roadmap.
