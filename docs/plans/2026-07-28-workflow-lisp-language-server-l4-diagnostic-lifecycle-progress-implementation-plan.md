# Workflow Lisp Language Server L4 Diagnostic Lifecycle And Compile Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Every task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit. Use the existing
> clean implementation clone; do not create a worktree.

**Goal:** Ship the accepted L4 current-only diagnostic presentation policy and
one non-blocking capability-gated work-done lifecycle per logical serialized
compile-pump interval, without deleting contribution ownership or changing
compiler execution.

**Architecture:** Add a pure `LspState` projection that validates retained
diagnostic ownership and selects only current terminal owners for
publication. Existing state transitions republish retained target URIs when
visibility changes. Add one small transport-local progress state machine that
projects compile-pump busy/settled facts into create/begin/end/retire effects;
`WorkflowLispLanguageServer` interprets those effects without putting client
acknowledgment on the compile critical path.

**Tech stack:** Python 3.11+, frozen dataclasses/tuples, asyncio, existing
pygls/lsprotocol progress APIs, the existing immutable LSP state and
split-phase compile driver, pytest/pytest-xdist, real framed JSON-RPC over
stdio, and headless Neovim.

**Accepted design:** commit
`8260159c0759249880048979d57982b275e11f31`, tree
`0e0fd4df5d0943c0c176822a3584d6efecd22434`, after ordered
`L4_DESIGN_SPEC_APPROVED` then `L4_DESIGN_QUALITY_APPROVED`.

**Execution status:** Tasks 1–3 are implemented and committed after their
ordered specification then quality reviews. The exact Task 4 focused rerun and
broad non-security comparison are recorded below with zero new failures. The
closure-only metadata candidate now requires preparatory
`L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED`; neither label has
been issued yet. After that exact candidate is committed, the distinct
`L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED` reviews remain
required against the clean committed tree.

---

## Scope And Deliberate Cost

This plan implements only:

- a current-only diagnostic publication projection over the unchanged
  retained per-entry contribution tuples;
- exact target republishing when an owner changes between visible and hidden;
- current success/language-error visibility and dirty, unavailable, pending,
  idle, invalidated, server-error, configuration-stale, closed, and
  unassociated hiding;
- one transport-local progress interval shared by coalesced entries and
  superseded generations;
- capability gating, non-blocking token creation, late-callback isolation,
  exact token retirement, presentation-only client cancellation, and balanced
  begin/end delivery;
- real stdio evidence with supporting and non-supporting clients;
- one repository-real headless Neovim acceptance gate; and
- final documentation/status promotion after implementation evidence.

The deliberate diagnostic cost is bounded flicker: old squiggles disappear on
dirty/pending transition and only current compiler output reappears. The
deliberate progress cost is an indeterminate, non-cancellable item with no
percentage or queue count. A fast compile may finish before token creation is
acknowledged and therefore show no progress. These constraints make stale
decoration, public compile cancellation, per-generation progress, and phase or
percentage reporting harder, but keep presentation honest and mechanically
separate from compiler authority.

Do not add unsaved-buffer analysis, tolerant parsing, diagnostic pull,
message/tag/source rewriting, a second contribution store, compile
debouncing, caching, incrementality, parallel compilation, compiler callbacks,
public cancellation, telemetry, persistence, runtime reporting, editor
extensions, or editor-specific production code.

## Governing Authorities

Read before implementation:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_lisp_language_server.md`;
- `docs/design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md`;
- `docs/design/workflow_lisp_frontend_specification.md` §76.1;
- `docs/design/workflow_language_design_principles.md`, especially principles
  27–30;
- `docs/reports/2026-07-28-workflow-lisp-l4-editor-lifecycle-probe.md`;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- completed L0/L1/L2/L3/L5 plans; and
- this plan's accepted-design commit and tree above.

If this plan conflicts with the accepted design, correct the plan and repeat
ordered plan reviews. Do not reinterpret the design in code.

## Ownership And Exclusions

L4 production ownership is exactly:

- `orchestrator/lsp/state.py`;
- `orchestrator/lsp/server.py`; and
- new `orchestrator/lsp/progress.py`.

L4 behavioral test ownership is exactly:

- `tests/test_workflow_lisp_lsp_state.py`;
- `tests/test_workflow_lisp_lsp_diagnostics.py`;
- new `tests/test_workflow_lisp_lsp_progress.py`;
- `tests/test_workflow_lisp_lsp_stdio.py`;
- `tests/test_workflow_lisp_lsp_integration.py`;
- new `tests/test_workflow_lisp_lsp_neovim_e2e.py`; and
- exact L4 routing expectations in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`.

The final shared documentation paths are:

- `docs/design/workflow_lisp_language_server.md`;
- `docs/design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md`;
- exact §76.1 L4 status in
  `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/index.md`;
- exact L4/next-stage routing in the active roadmap; and
- this plan.

Do not modify the compiler, compile driver, build/CLI/runtime/workflow code, or
diagnostic identity/translation values. Do not widen L4 to Q4/Q5, P1–P5,
prompt calculus, provider coordination, or workflow execution. Do not modify
or run any security, safety, secrets, provider-isolation, or
provider-launch-shim path.

## Protected Workspace And Execution Contract

Execute from the existing clean clone:

```bash
cd /home/ollie/.tmp/mr4-plan-pCBIen/repo
```

Do not create a worktree or another clone. Before every task, refresh
`git status --short`; preserve unrelated changes and never use `git add .`,
`git add -A`, destructive checkout/reset, or broad cleanup. Stage only exact
reviewed paths.

Use one fresh implementation subagent per behavior task. For every task:

1. inventory exact owned paths and current `HEAD`;
2. write the smallest behavioral test first;
3. run it and capture the intended RED;
4. implement only that task;
5. rerun the narrow selector and adjacent LSP regressions;
6. inspect the full exact diff and `git diff --check`;
7. obtain independent specification review;
8. obtain distinct implementation-quality review only after specification
   approval;
9. apply corrections and restart both reviews in order when bytes change; and
10. stage exact reviewed paths and commit only after both approvals.

## Pre-Implementation Control

Before Task 1:

```bash
git status --short
git rev-parse HEAD HEAD^{tree}
pytest --collect-only -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  tests/test_workflow_lisp_lsp_integration.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
pytest -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  tests/test_workflow_lisp_lsp_integration.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Capture collection count, pass/fail/skip totals, elapsed time, and raw output
digest. Then run the exact broad non-security command from Task 4 Step 1,
unchanged, in tmux as the pre-L4 broad control and capture its collection
count, pass/fail/error/skip totals, elapsed time, raw output digest, and exact
failure node IDs.

Append both control records to this plan, obtain ordered
`L4_CONTROL_SPEC_APPROVED` then `L4_CONTROL_QUALITY_APPROVED` for those
metadata-only bytes, and commit only this plan before Task 1. Confirm the tree
is clean. Do not reinterpret a failure as L4 owned without a reproducing
narrow selector.

### Pre-Implementation Control Record

Captured on 2026-07-28 against commit
`f29b8999348c8f10f6469088715b8a960f95e63d`, tree
`4f70fa471a24230ab63a648a6d5dd4d6cf02daaa`, with a clean working tree.

The exact focused collection selected 282 tests in 1.13 seconds. Its raw
output SHA-256 is
`f9de5e6785dd64e73bff2ed0ff34a9cfb663faf3e23954b4472e4594ebcc5453`.
The focused execution passed 282 tests in 60.76 seconds with zero failures,
errors, or skips. Its raw output SHA-256 is
`b10822c08faf73f6b7a1480f670960e5d79cfb050556caca27ae9909558fa08a`.

The exact broad non-security command selected and executed 10,884 tests. The
authoritative complete-transcript run finished in 160.11 seconds with 10,820
passed, 42 failed, 0 errors, 22 skipped, and 33 warnings. Its raw output
SHA-256 is
`e3d493ee211b402859a11e3a2388ae093fde3fe6d1c138e0f967238df80d38f3`.
The sorted exact failure-node set SHA-256 is
`f5dccf2885bfd0f37e18573073e3904469453daff7823723560e989efac6c88c`.
The exact pre-L4 failure nodes are:

- `tests/test_workflow_lisp_post_wcc_inventory.py::test_checked_in_inventory_loads_and_validates`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_missing_explicit_tranche_3a_coverage_emits_stable_code`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_unknown_status_emits_stable_code`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_missing_evidence_path_emits_stable_code`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_completed_row_requires_completed_gap_history`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_implemented_by_wcc_row_requires_completed_gap_history`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_remaining_row_contradicted_by_repo_evidence_emits_status_conflict`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_promotion_gate_rows_cannot_block_done`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_markdown_guard_drift_emits_stable_code`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_newer_progress_ledger_event_overrides_older_status_sources`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_done_preconditions_follow_remaining_surface_state`
- `tests/test_workflow_lisp_procedures.py::test_procedure_identity_modes_match_frozen_wcc_m4_observables`
- `tests/test_provider_supervision_runtime.py::test_provider_supervision_call_frame_fails_before_runtime_activity`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_cli_inventory_check_succeeds_for_checked_in_inventory`
- `tests/test_workflow_lisp_post_wcc_inventory.py::test_cli_inventory_check_reports_drift_or_missing_evidence`
- `tests/test_provider_prompt_dependency_broad_gate.py::test_reviewed_baseline_helper_migration_changes_only_helper_and_record_digests`
- `tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates`
- `tests/test_workflow_lisp_key_migrations.py::test_tracked_plan_phase_runtime_helper_rejects_clean_run_before_writes[False]`
- `tests/test_workflow_lisp_key_migrations.py::test_tracked_plan_phase_runtime_helper_rejects_clean_run_before_writes[True]`
- `tests/test_workflow_lisp_key_migrations.py::test_tracked_plan_phase_retained_run_evidence_replays`
- `tests/test_workflow_lisp_procedure_identity_retirement.py::test_checked_retirement_artifacts_reproduce_from_production_build[old]`
- `tests/test_workflow_lisp_procedure_identity_retirement.py::test_checked_retirement_artifacts_reproduce_from_production_build[new]`
- `tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry`
- `tests/test_workflow_lisp_key_migrations.py::test_tracked_plan_phase_actual_recovery_record_matches_its_lifecycle_contract`
- `tests/test_demo_nanobragg_entrypoint_reference_harness.py::test_build_harness_produces_shared_library`
- `tests/test_demo_nanobragg_entrypoint_reference_harness.py::test_run_reference_case_returns_tensor_payload`
- `tests/test_demo_nanobragg_reference_harness.py::test_extract_accumulation_slice_reports_scoped_anchor_metadata`
- `tests/test_demo_nanobragg_reference_harness.py::test_reference_harness_supports_compile_check_mode`
- `tests/test_workflow_lisp_prompt_identity_e2e.py::test_target_222_retry_attributes_changed_roles_before_terminal_report`
- `tests/test_resume_command.py::test_direct_resume_quarantines_before_restart_or_launch_and_stays_sticky`
- `tests/test_workflow_lisp_list_traversal.py::test_unknown_target_versions_still_fail_closed`
- `tests/test_workflow_lisp_wcc_characterization.py::test_characterization_structural_cases_match_golden[stdlib_review_revise_loop]`
- `tests/test_workflow_lisp_wcc_characterization.py::test_characterization_structural_cases_match_golden[wcc_m4_implementation_phase_full_fixture]`
- `tests/test_workflow_lisp_wcc_characterization.py::test_characterization_structural_cases_match_golden[module_graph_imported_bundle_mix]`
- `tests/test_workflow_lisp_wcc_characterization.py::test_characterization_behavior_cases_match_golden[stdlib_review_revise_loop]`
- `tests/test_workflow_lisp_wcc_characterization.py::test_characterization_behavior_cases_match_golden[wcc_m4_implementation_phase_full_fixture]`
- `tests/test_workflow_lisp_lsp_e2e.py::test_real_repository_l2_recovery_to_full_is_read_only`
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_procedure_first_design_delta_public_wrapper_runtime_contract`
- `tests/test_workflow_lisp_checkpoint_identity_comparison.py::test_design_delta_drain_generic_route_matches_baseline`
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_checksum_evidence_projection_replays`
- `tests/test_workflow_lisp_checkpoint_identity_comparison.py::test_reviewed_inline_call_retirement_rejects_identity_or_lineage_drift`
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_design_delta_finalizer_hypothetical_removes_four_public_wrapper_checkpoints`

None of these nodes belongs to the L4 owned-path or focused-selector surface.
They are comparison facts only and grant no repair or weakening scope.

---

## Task 1: Current-Only Diagnostic Publication

**Files:**

- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_state.py`
- Modify: `tests/test_workflow_lisp_lsp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`

### Step 1: Write failing state and publication tests

Add tests that prove:

- current clean `success` and `language_error` owners project their exact
  retained tuples;
- empty current tuples are valid;
- dirty, unavailable, pending, clean-idle, dependency-invalidated,
  server-error, configuration-stale, closed, and unassociated owners project
  nothing;
- malformed owner URI or accepted generation raises instead of becoming a
  successful empty projection, and the production publication boundary logs
  that internal server error without emitting a partial or empty replacement;
- `didChange`, direct clean `didSave`, and dependency invalidation republish
  every old target when a currently visible owner becomes hidden;
- dirty-to-pending and pending-to-server-error do not emit redundant
  visibility republishing;
- hiding one parity-identical owner preserves the other current owner in the
  aggregate; and
- the last hidden owner publishes an exact empty diagnostic list while its
  internal contribution tuple remains byte-for-byte equal.

Run the smallest new selectors and capture RED:

```bash
pytest -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  -k 'diagnostic and (current or visible or dirty or pending or invalidated or owner)'
```

RED must be missing current-only projection/republish behavior, not fixture or
import failure.

### Step 2: Add one validated state projection

In `state.py`, add one pure public projection from `LspState` to the exact
canonical entry-URI-to-contribution mapping consumed by publication.

For every retained tuple, invoke the same structural owner/generation checks
used at state entry before applying lifecycle visibility. Do not catch and
reinterpret malformed state as empty. Include a tuple only when:

- the entry is present and clean;
- `pending_generation is None`;
- status is `success` or `language_error`; and
- every contribution matches the entry URI and current generation.

Do not modify, copy, rewrite, or delete `DiagnosticContribution` values.

### Step 3: Republish on visibility changes

Keep `StateEffects.republish_uris` as the only publication instruction. Add a
small private visibility-change helper that compares old/new entry lifecycle
and returns retained target URIs only when presentation changes.

Use it in:

- `change_entry`;
- `save_entry`; and
- `observe_file_revision`.

Keep completion replacement, close, and configuration-stale union behavior
unchanged. `record_server_failure` starts from hidden pending state and
therefore adds no redundant republish effect.

Change `server.change_document` to retain the `change_entry` transition,
apply it, and pass that exact transition to `_emit_transition_effects`, so an
unsaved edit can publish the immediate clear instead of discarding its
republish instruction.

Change `server._emit_transition_effects` to aggregate only the new validated
current projection from the already-adopted final state. Treat projection or
aggregation failure as an internal server error: call `log_internal_error` and
emit no diagnostic publication for that transition batch. Do not publish a
partial aggregate and do not reinterpret malformed retained state as a
successful empty result. Lock this behavior with a server-level test.

### Step 4: Verify and review Task 1

```bash
pytest -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_stdio.py
git diff --check
```

Obtain `L4_TASK1_SPEC_APPROVED`, then `L4_TASK1_QUALITY_APPROVED`, restarting
both in order after any byte change. Commit only:

```text
orchestrator/lsp/state.py
orchestrator/lsp/server.py
tests/test_workflow_lisp_lsp_state.py
tests/test_workflow_lisp_lsp_diagnostics.py
tests/test_workflow_lisp_lsp_stdio.py
```

Suggested subject: `Publish only current LSP diagnostics`.

---

## Task 2: Non-Blocking Compile Progress Controller

**Files:**

- Create: `orchestrator/lsp/progress.py`
- Modify: `orchestrator/lsp/server.py`
- Create: `tests/test_workflow_lisp_lsp_progress.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`

### Step 1: Write the pure state-machine RED tests

Create a table-driven suite for the exact closed states:

```text
inactive
creating(token, interval)
active(token, interval)
suppressed(interval)
```

Prove:

- absent/false capability emits no effects;
- first busy observation allocates one unique token and create effect;
- successful create while still busy emits one begin;
- late successful create after quiescence emits only retirement;
- create failure suppresses the interval with no begin/end;
- active quiescence emits one end and retirement;
- creating/suppressed quiescence emits no unmatched frame;
- cancellation-plus-replacement supersession keeps one interval/token;
- presentation cancellation ends active once, suppresses remaining work, and
  never emits compiler cancellation;
- cancellation while creating suppresses without begin/end;
- success, language error, server error, close, existing generation
  cancellation, configuration staleness, unexpected pump failure, and pump
  task cancellation all settle correctly;
- token registrations retire after end, cancellation, and unused late create;
  and
- old token/interval callbacks cannot affect a newer interval.

```bash
pytest --collect-only -q tests/test_workflow_lisp_lsp_progress.py
pytest -q tests/test_workflow_lisp_lsp_progress.py
```

The new module must collect and fail for missing production behavior.

### Step 2: Implement the pure controller

Use frozen dataclasses and literal closed state/effect values. The controller
does not import pygls, asyncio, compiler, driver, filesystem, or server state.
It accepts only:

- capability support;
- logical `busy` observations;
- exact create success/failure callbacks;
- presentation cancellation; and
- forced local settlement.

Its effects may request only create, begin, end, token retirement, or
transport-error logging. It has no compile-cancel, queue mutation, result, or
diagnostic effect.

Tokens are unique monotonic process-local strings. Match asynchronous callbacks
by both token and interval identity.

### Step 3: Interpret effects in the production server

During initialization, freeze support only when
`params.capabilities.window.work_done_progress is True`.

Define logical busy from current entry state: at least one open, clean,
current pending generation is eligible. An invalidated worker thread with no
current pending generation is not logically busy.

Interpret create with an independently scheduled `create_async` task; never
await it before scheduling or executing compilation. On success/failure,
re-enter the controller on the event-loop owner. Retire successful pygls token
registrations after end, presentation cancellation, or an unused late
acknowledgment.

Keep pygls registration ownership behind one server-local adapter:
`WorkflowLispLanguageServer._retire_progress_token(token)` performs exactly
`self.work_done_progress.tokens.pop(token, None)`. Regression tests must lock
the installed pygls `Progress.tokens` mutable-mapping contract. Do not reach
through any other private transport state. If a supported pygls version lacks
that contract, stop and revise this adapter explicitly rather than retaining a
completed token registration or allowing a retired callback to address a new
interval.

Reconcile after transition effects, after each prepared completion, on close
or configuration staleness, and in pump exception/cancellation settlement.
Bind `window/workDoneProgress/cancel` to presentation-only controller
cancellation. Unknown/retired tokens retain pygls's ignore-and-log behavior.

Emit `WorkDoneProgressBegin` with `cancellable=false` and no percentage.
Literal title/message prose is not a tested contract.

### Step 4: Add server/stdio/integration coverage

Use the existing controlled blocked-builder fixtures to prove:

- supporting capability produces create → begin → end;
- absent/false capability produces no progress traffic;
- create error produces no progress notifications and compile still settles;
- one save storm/supersession interval uses one token;
- last-work close ends presentation before the invalidated worker returns;
- another eligible entry keeps the interval open;
- language/server errors and configuration staleness end once;
- client progress cancellation ends presentation but the current compile still
  reaches its unchanged accepted or failed state; and
- no progress frame contaminates stdout outside JSON-RPC framing.

The stdio harness must answer `window/workDoneProgress/create` requests before
expecting `$/progress`; do not fake a registered token.

### Step 5: Verify and review Task 2

```bash
pytest -q \
  tests/test_workflow_lisp_lsp_progress.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  tests/test_workflow_lisp_lsp_integration.py \
  tests/test_workflow_lisp_lsp_state.py
git diff --check
```

Obtain `L4_TASK2_SPEC_APPROVED`, then `L4_TASK2_QUALITY_APPROVED`, restarting
both in order after any byte change. Commit only Task 2 paths.

Suggested subject: `Report serialized LSP compile progress`.

### Task 1–3 Execution Record

- **Task 1 commit:** `116295513b0e39463004c663920bfa73128481ca`,
  tree `d7f9d7d66142d022e5a82bb6ab72828b8ad53e0a`, after ordered
  `L4_TASK1_SPEC_APPROVED` then `L4_TASK1_QUALITY_APPROVED`.
- **Task 2 commit:** `0d5f70093fe7ee7c7abb59a29c3f555f1f3c14c9`,
  tree `94a995b55186805af25bc5d7b370829b79b7b175`, after ordered
  `L4_TASK2_SPEC_APPROVED` then `L4_TASK2_QUALITY_APPROVED`.
- **Task 3 commit:** `bdd1e8223e24c5346567710563473e2aaf5ec9ac`,
  tree `a81183182898abc3c2b40f70c3e2bb40b7342d9c`, after ordered
  `L4_TASK3_SPEC_APPROVED` then `L4_TASK3_QUALITY_APPROVED`.
- **Repository-real Neovim acceptance:** one acceptance test passed in 1.77
  seconds against installed Neovim `0.12.0-dev-703+g66f02ee1fe` and production
  `python -m orchestrator.lsp`. It observed the exact initial diagnostic
  identity, unsaved-edit clear, one save create/begin/end token lifecycle,
  exact empty current completion, empty final progress status, the exact
  intentional source-byte change only, and no `.orchestrate` tree. One
  additional helper test proves the workspace snapshot records regular-file
  bytes, directories, and symlink targets without traversing symlinked
  directories; the two-test module passes.
- **Next gate:** Task 4's closure-only metadata reviews and exact-path commit,
  followed by the distinct final exact-tree reviews.

---

## Task 3: Real Client Evidence And Shipped Documentation

**Files:**

- Create: `tests/test_workflow_lisp_lsp_neovim_e2e.py`
- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify: `docs/design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/workflow_lisp_language_server_setup.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/README.md`
- Modify: `docs/index.md`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify: this plan
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

### Step 1: Add the repository-real Neovim acceptance gate

The Python test must require the installed `nvim` executable, create a fixture
workspace under `tmp_path`, and launch headless Neovim with its generic LSP
client against production `python -m orchestrator.lsp`.

It must observe:

1. one real clean invalid-source diagnostic;
2. an unsaved edit followed by an exact empty client diagnostic view;
3. save through the real editor transport;
4. one work-done create/begin/end lifecycle for that logical compile interval;
5. one current post-save diagnostic or exact empty current result; and
6. empty final editor progress status.

Assert only event kinds, token identity/order/cardinality, diagnostic
code/range/data identity, and currentness. Do not assert literal diagnostic or
progress prose.

The test must prove the fixture has no server-created `.orchestrate` tree and
no unexpected file delta beyond the editor's intentional saved source bytes.
It must fail, not skip, when Neovim is unavailable.

```bash
pytest --collect-only -q tests/test_workflow_lisp_lsp_neovim_e2e.py
pytest -q tests/test_workflow_lisp_lsp_neovim_e2e.py
```

Because Tasks 1 and 2 already implement the behavior, this is a
post-implementation acceptance gate expected to pass on its first complete
run. A harness, fixture, or missing-executable failure is not acceptable
evidence.

### Step 2: Promote only observed shipped behavior

After the real-client gate passes:

- mark the L4 design implemented and incorporate its durable contract into the
  owning language-server baseline;
- update §76.1, setup guidance, capability/router/index surfaces, and the
  roadmap to shipped behavior;
- preserve L5 and Q4/Q5 truth;
- record Task 1/2 commit identities and exact review labels in this plan; and
- select the next eligible roadmap gate without claiming it implemented.

Routing tests must require:

- L4 `Implemented`, not `Designed`;
- current-only diagnostic presentation and capability-gated progress;
- ordered design/task review labels and real Neovim evidence;
- no stale "implementation pending" L4 wording; and
- unchanged Q4/Q5/L5 routing.

### Step 3: Run the complete focused surface

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_lsp_progress.py \
  tests/test_workflow_lisp_lsp_neovim_e2e.py
pytest -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_progress.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  tests/test_workflow_lisp_lsp_integration.py \
  tests/test_workflow_lisp_lsp_cli_parity.py \
  tests/test_workflow_lisp_lsp_navigation.py \
  tests/test_workflow_lisp_lsp_e2e.py \
  tests/test_workflow_lisp_lsp_neovim_e2e.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

### Step 4: Verify and review Task 3

Obtain `L4_TASK3_SPEC_APPROVED`, then `L4_TASK3_QUALITY_APPROVED`, restarting
both in order after any byte change. Commit only Task 3 paths.

Suggested subject: `Prove LSP lifecycle behavior in Neovim`.

---

## Task 4: Broad Comparison And Final Closure

### Step 1: Run the exact broad non-security suite in tmux

Use the `tmux` skill and the exact roadmap command:

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

Record collection count, pass/fail/error/skip totals, elapsed time, and raw
output digest. Compare every failure node against the pre-implementation
control. Do not repair or weaken an unrelated failure.

### Step 2: Commit closure metadata

Refresh:

```bash
git status --short
git rev-parse HEAD HEAD^{tree}
git diff --check
pytest -q \
  tests/test_workflow_lisp_lsp_state.py \
  tests/test_workflow_lisp_lsp_diagnostics.py \
  tests/test_workflow_lisp_lsp_progress.py \
  tests/test_workflow_lisp_lsp_stdio.py \
  tests/test_workflow_lisp_lsp_integration.py \
  tests/test_workflow_lisp_lsp_neovim_e2e.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Update only this plan and routing metadata with:

- Task commit/tree identities;
- fresh focused and broad totals/digests;
- exact review labels;
- L4 complete status; and
- the next eligible roadmap gate.

Review those closure-only bytes in order, commit them, and rerun the routing
suite. These closure-byte reviews are preparatory and are not the named final
exact-tree reviews.

Suggested subject: `Close LSP diagnostic lifecycle and progress`.

### Task 4 Evidence And Closure Record

The comparison candidate is based on clean Task 3 commit
`bdd1e8223e24c5346567710563473e2aaf5ec9ac`, tree
`a81183182898abc3c2b40f70c3e2bb40b7342d9c`.

The exact focused selector from Step 2 passed 356 tests in 70.94 seconds with
zero failures, errors, or skips. Its complete raw-output SHA-256 is
`1a19ac9339d54dd9416cbdbded1af1b8e1688b0d5ca8589a37f44ef520fee966`.

The exact broad non-security command selected and executed 10,958 tests. It
finished in 161.94 seconds with 10,895 passed, 41 failed, 0 errors, 22 skipped,
and 33 warnings. Its complete raw-output SHA-256 is
`6f071f35bf086f027ce6445f3c83114f4812f06025ec565fe32123c37ab627a4`;
the sorted exact failure-node set SHA-256 is
`97c8f87faafae8e8cfa29cbc36c9d237956d010500333247090032d14fac8c18`.
All 41 failures are unchanged members of the 42-node pre-L4 control. There are
zero new failures. The one removed control failure is
`tests/test_workflow_lisp_lsp_e2e.py::test_real_repository_l2_recovery_to_full_is_read_only`,
which now passes on the L4 tree. No unrelated failure is reclassified, repaired,
or waived by this record.

The next required outcomes for these closure-only bytes are, in order,
`L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED`. They are required
review labels, not outcomes already issued. After the reviewed closure
candidate is committed, Step 3 requires the distinct
`L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED` exact-tree outcomes;
those final labels likewise have not yet been issued.

After those final exact-tree reviews approve L4, the next eligible roadmap
gate is the stopped Q5 lineage:
`Q5_F1_F2_FIX_SPEC_APPROVED` then `Q5_F1_F2_FIX_QUALITY_APPROVED` over the
exact merged F1/F2 evidence-surfacing correction from `492b1171`. Both labels
are required and not issued. The unchanged combined invalid-then-valid
real-provider gate follows. Q5 remains partial at activation `bceb03e4`, its
Task 13 stop at `3fc3a09e` still governs, Task 14 has not started, and no
split-proof substitution is claimed. Q4 remains blocked on its concrete
consumer.

### Step 3: Final exact-tree review

Refresh the clean committed `HEAD`/tree and rerun the exact focused selector
from Step 2. Obtain final independent `L4_FINAL_SPEC_APPROVED`, then distinct
`L4_FINAL_QUALITY_APPROVED` against that exact committed tree and the recorded
broad comparison. Record the reviewed commit/tree and labels without changing
repository bytes. If either review requires a byte change, apply it, rerun
affected verification, commit the correction, and restart both named final
reviews in order against the new clean committed tree.

## Completion Gate

L4 is complete only when:

- all four tasks are committed in order;
- every task has ordered specification then quality approval;
- current-only diagnostic visibility preserves internal contribution
  ownership and multi-owner aggregation;
- progress is capability-gated, non-blocking, balanced, coalesced, and
  presentation-only on client cancellation;
- real stdio and repository-real Neovim evidence pass;
- no server/workspace mutation appears;
- the exact broad non-security comparison introduces no unadjudicated L4-owned
  failure;
- durable docs say implemented only after evidence;
- final ordered reviews approve the exact tree; and
- routing selects the next eligible roadmap gate without claiming it shipped.
