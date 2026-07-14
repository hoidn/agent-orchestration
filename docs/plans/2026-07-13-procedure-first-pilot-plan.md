# Procedure-First Tracked Plan Phase Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Architect decision recorded 2026-07-14 (APPROVE, Path A —
conditional `reviewed_internal_identity_retirement`; see the decision request
below). Task 1A is selected. The generic match-scoped store-count correction is
implemented and reviewed at `e43461f9` and `5f382401`; the prior pre-edit scan
must now be regenerated and reviewed under that contract before the exact owner
records are presented for adoption and quiescence begins. No corrected scan,
owner attestation, or quiescence claim is complete yet. Every pilot source edit
remains prohibited until the complete pre-edit gate (corrected scans, genuine
owner attestations, isolation, quiescence, immutable evidence) commits
successfully; any matching supported live/nonterminal run or queried
old-identity consumer reverts to strict compatibility.

**Architect decision request:**
[Tracked-Plan Pilot Identity-Retirement Architect Decision Request](2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md).
It is non-authoritative routing input, not an attestation, retirement record,
or source-edit authorization.

**Goal:** Convert only the internal `tracked-plan-phase` in `design_plan_impl_review_stack_v2_call.orc` from a workflow call to an inline typed procedure while retaining `design-plan-impl-review-stack` as the public boundary and proving full executable parity.

**Architecture:** Retain the frozen pre-change contract snapshot for the public
entry, then, only after the pre-edit evidence gate passes, make the smallest
source migration: `tracked-plan-phase` becomes `defproc :lowering inline`, and
its one caller uses an ordinary positional procedure call. The public wrapper
continues to own inputs, outputs, artifacts, effects, state, effect-owned
checkpoints, source maps, and runtime execution. Public identities remain
strict; eligible old internal call-boundary identities may be retired only by
the reviewed evidence path defined below.

**Tech Stack:** Workflow Lisp `.orc`, WCC compiler, executable and Semantic IR, source maps, migration parity tooling, orchestrator CLI, pytest.

---

## Authority, prerequisites, and boundaries

- Accepted contract: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Accepted identity compatibility clarification:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Current prerequisite plan:
  `docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md`
- Reviewed inventory row: `internal-call:workflows/examples/design_plan_impl_review_stack_v2_call.orc:tracked-plan-phase:1` in `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Existing family target: `design_plan_impl_stack` in `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- The following earlier prerequisites are complete:
  1. `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md` is complete; and
  2. `docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md` is complete and reviewed.
- Identity-compatibility prerequisite Tasks 1-7 and Task 8's final
  verification/review gate are complete under the audited handoff below. The
  generic match-scoped store-count repair is also implemented and reviewed.
  The frozen pilot source and old baseline have not been refreshed. Task 1A is
  selected only through corrected scan regeneration and the owner-attestation
  boundary; Task 2 remains unselected and unauthorized.
- When resumed, this plan owns the genuine named-owner attestations for every
  known state store and either proves strict compatibility or applies the
  accepted reviewed internal identity-retirement exception. Missing,
  ambiguous, public/exported, promoted/live, or supported-consumer evidence
  stops the pilot without a source edit. A retirement record is evidence only
  and makes no old-state remap or cross-source resume claim.
- Modify no phase except `tracked-plan-phase`; `tracked-design-phase` and `design-plan-impl-implementation-phase` remain workflows for later waves.
- Retain the exported public `design-plan-impl-review-stack` workflow. Do not export the pilot procedure or register it as a workflow entry.
- Do not edit the YAML twin or archive anything in this plan. Stage 6 owns YAML retirement.
- Any public checkpoint/resume identity, public output, artifact, publication,
  effect, or source-map loss is a stop condition. An unreviewed or ineligible
  internal identity change also stops. Only an old internal identity accepted
  by the validated `reviewed_internal_identity_retirement` record may differ;
  that exception does not relax any other parity axis.

### Identity-compatibility prerequisite handoff (2026-07-14)

Task 8 audited the exact prerequisite set by responsibility rather than
treating the history as one uninterrupted range:

- Task 1 capture/observables and late normalization/correction:
  `d5eb0043`, `6076f37e`, `5c4d6bdc`, `142a1840`, `50f78791`,
  `bfabb614`, `ffd4503d`, and `d2440fe9`;
- Task 2 compiler ownership, identity preservation, schema-1 classification,
  linked specialization, and collision repairs: `7614cf9a`, `6d552c92`,
  `36071d98`, `6d8bfea7`, `90f69f12`, `27e1bd84`, and `2ba82db4`;
- Tasks 3-4 checkpoint/provenance and reviewed-observable delta:
  `e10749c3`, `a77c032f`, and `842432f9`;
- Task 5 evidence-only retirement validation: `d85d637b`, `8d317897`, and
  `57b35b1c`;
- Task 6 root/callee checksum characterization: `7e4b3428` and `e4f2ecbe`;
  and
- Task 7 contract/pilot/plan repairs and final authority binding: `8ae270ea`,
  `c7aca2c9`, `bb8ff56f`, `b7212487`, `8b2586cd`, `4237445b`, `405e918b`,
  `fd81a839`, and `71a3592b`.

The compact baseline is
`docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json`:
captured by `d5eb0043` at `2026-07-14T05:04:05Z` and accepted at `50f78791`.
Its correction authority is
`docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`:
created by `d2440fe9`, accepted at `b7212487`, and pinned into the execution
plan by `4237445b`. Final reviewed prerequisite HEAD was `71a3592b`.

Fresh gates collected 727 tests; the focused prerequisite command passed 596
with 131 deselected. The production CLI WCC compile exited 0 and its two build
artifact checks passed. The broad run reported exactly 8 failures, 4268
passes, and 11 skips in 72.64 seconds. Its nodeid set was exactly the accepted
set, and all eight isolated normalized signatures and complete-log SHA-256
digests matched the accepted baseline/correction pair. The six unchanged
unrelated failures remain in four files untouched since the pre-implementation
anchor `dfd34c76`:

- `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`;
- `tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence`;
- `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`;
- `tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`;
- `tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54`; and
- `tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch`.

The two intentional pilot REDs also retained their exact pre-edit failures:

- `tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_is_explicit_inline_procedure` — `tracked-plan-phase` remains a
  `defworkflow`; and
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_wrapper_uses_procedure_call` — the wrapper still uses
  `(call tracked-plan-phase ...)`.

The evidence-only retirement parser/validator/store scanner, production
artifact checks, root byte-immutable pre-executor checksum rejection, and
callee pre-child-execution/no-remap characterization passed. The known-store
scan API is
`orchestrator.workflow_lisp.procedure_identity_retirement.scan_known_state_store`.
Independent reviews returned `FINAL SPEC PASS` and `FINAL QUALITY PASS`, with
no cross-source resume or runtime-record coupling claim.

The literal repo-wide `git diff --check` still reports the pre-existing blank
line in protected `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`.
Scoped prerequisite/committed-path and protected-excluded diff checks are
clean; the protected paths remain unstaged and outside this handoff. The pilot
source and `tests/baselines/procedure_first/tracked_plan_phase.json` remain
unchanged. The prerequisite handoff is complete. The superseding Path A
decision selected Task 1A, but Task 2 remains locked until the corrected scan,
owner-attestation, quiescence, isolation, and immutable-evidence gates pass.

### Read-only Task 1A preflight stop (2026-07-14)

The required evidence/attestation root was absent. The canonical repository
store `/home/ollie/Documents/agent-orchestration/.orchestrate/runs` was
nonempty with 4,165 immediate run directories, 322,629 files, and approximately
6.2 GiB of content, and no genuine named-human owner attestation existed for
it. The dedicated store
`/home/ollie/Documents/agent-orchestration/.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`
and its parent chain were absent, so its required isolation proof and owner
attestation were also unmet.

The preflight retained all 355 helper-shaped
`/tmp/design-plan-impl-stack-*` scratch directories; the SHA-256 of their
sorted absolute-path list was
`b535f9a6c4debe837ba9d606420380c572c915f2e7492c46a366f37533b24b24`.
None were removed, and no matching scratch directory existed in the
repository. No human identity was inferred, no conversation response was
treated as an attestation, and no file or directory was created, removed, or
modified by the preflight. Therefore the mandatory result is
`STOP: missing known-store owner attestation`; do not create placeholder
evidence or select Task 1A's harness work or any source edit.

**Superseded 2026-07-14:** the architect decision recorded in
[the decision request](2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md)
resolves this stop for Task 1A selection (Path A; see Status above). The
preflight record above is preserved as history. The source-edit prohibition
and every fail-closed rule below remain in force until the complete pre-edit
gate commits.

## Protected working-tree guard

The following user-owned dirty paths are outside every task in this plan:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before every commit, run `git diff --cached --name-only`, then run:

```bash
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

The literal protected-path command must print nothing; the full staged list
must be a subset of the active task's `Files` list. Never stage, restore, or
rewrite a protected path. Record its initial `git status --short` output only
as a guard baseline; user changes to those paths are not plan failures.

## File responsibility map

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`: the one family source edit.
- `tests/baselines/procedure_first/tracked_plan_phase.json`: reviewed pre-migration public/runtime contract, including the internal phase route that must be preserved or explicitly proven irrelevant.
- `tests/test_workflow_lisp_procedure_first_migrations.py`: provisional
  before/after structural characterization, retained-public-boundary negative
  test, and the final production-record validator test. The existing
  structural-delta assertions never authorize retirement by themselves.
- `tests/test_workflow_lisp_key_migrations.py`: existing compile and one-pass
  runtime smoke, plus runtime-workspace lifecycle ownership. Its stack helper
  accepts an explicit workspace; normal tests use a cleanup-asserting yield
  fixture, while the evidence invocation passes the dedicated retained
  workspace.
- `tests/test_workflow_lisp_migration_parity.py`: existing family parity/report gate; change only if the report lacks procedure-first evidence fields.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`: existing commands and evidence roles; change only if a new named selector is required.
- `docs/workflow_lisp_route_readiness_registry.json`: change evidence references only after the pilot passes; do not promote the example's copy-safety.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/retirement_record.json`:
  the schema-v1 production retirement record consumed only by the evidence
  validator test, never by run/resume.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/pre_edit_known_store_scans.json`:
  immutable pre-edit scans for every named legacy root and the dedicated
  evidence root.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/final_known_store_scans.json`:
  final scans whose facts populate `retirement_record.json`.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/`:
  genuine owner-supplied pre-edit attestation records for every named store and
  the required second final attestation for the dedicated evidence root. An
  agent may copy a supplied record verbatim into this directory but may not
  author, paraphrase, or sign it.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/old/` and
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/new/`: each
  contains `source.orc`, `build_manifest.json`, `typed_frontend_ast.json`,
  `semantic_ir.json`, `executable_ir.json`, `runtime_plan.json`,
  `lexical_checkpoint_points.json`, and `source_map.json`. The retirement
  record binds every exact relative path to its SHA-256 digest.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/inputs/`:
  exact readable snapshots `provider_externs.json`, `prompt_externs.json`, and
  `command_boundaries.json` copied from the actual pilot compile inputs. Both
  old/new manifests reference these same paths when their input bytes are
  unchanged.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/`:
  stable `identity_delta.json`, `artifact_contract_multiset.json`,
  `execution_order.json`, `clean_run.json`, `interruption_resume.json`,
  `root_checksum_negative.json`, and `callee_checksum_characterization.json`
  evidence projections, plus the time-bounded
  `live_validator_pytest.txt` and `live_validator_result.json` proof.
- `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json`:
  a digest index linking pre-edit evidence, final evidence, reviews, and the
  retirement record without becoming runtime authority.
- `.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`:
  the dedicated live new-ID evidence run root. It is never a descendant of a
  legacy root and is not a tracked substitute for the stable evidence above.

## Mandatory pre-edit retirement gate

This gate runs before Task 2 and before any edit to the pilot `.orc` source.
It is not satisfied by earlier repository inspection or by a zero-match scan
of only the current workspace.

1. Confirm the identity-compatibility plan's Task 8 final handoff. Its fresh
   evidence must include the focused selectors for:
   - generic identity characterization and one-time Stage-3 resolution in
     `tests/test_workflow_lisp_procedures.py` and
     `tests/test_workflow_lisp_build_artifacts.py`;
   - inline checkpoint ownership in
     `tests/test_workflow_lisp_lexical_checkpoints.py`;
   - WCC inline provenance in `tests/test_workflow_lisp_source_map.py` and
     `tests/test_workflow_lisp_build_artifacts.py`;
   - the complete retirement validator suite in
     `tests/test_workflow_lisp_procedure_identity_retirement.py`; and
   - root/callee checksum characterization in `tests/test_resume_command.py`.
   Task 8's independent reviews must approve those prerequisite contracts;
   passing Tasks 1-7 selectors without the final reviews does not authorize a
   source edit.
2. Derive the old identity query from the unchanged
   `tests/baselines/procedure_first/tracked_plan_phase.json` and retained old
   source/build artifacts, and verify their content digests before editing.
   Enumerate the repository workspace `.orchestrate/runs` root, every other
   legacy workspace/run root intentionally used for this example, **and** the
   dedicated new-ID evidence run root
   `.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`
   as separate prospective `known_state_stores` entries. The dedicated root
   must exist but be empty, contain no old identities, and resolve outside
   every legacy root. Do not combine roots or treat a parent directory as proof
   about an unenumerated child store.
3. For every enumerated root call
   `scan_known_state_store(root, retired_identities=old_identities,
   query_version="procedure-identity-store-query.v1")`. Record the query time
   alongside the returned `normalized_scan_digest`, match-scoped
   `terminal_run_count` / `nonterminal_run_count`, query-derived
   call-frame/consumer counts, whole-store `store_terminal_run_count` /
   `store_nonterminal_run_count`,
   checkpoint-index/checkpoint-record counts, retained-manifest and
   identity-metadata counts, and scanned-file count in
   `pre_edit_known_store_scans.json`. Set
   `external_store_absence: not_asserted`. EasySpin, PtychoPINN, the paper
   repository, CI artifacts, backups, and copied workspaces remain unknown
   unless each concrete root is individually enumerated and scanned. Every
   intentionally used root, including the dedicated evidence root, must appear
   explicitly.
4. After each pre-edit scan, obtain from a genuine named human owner of that
   exact store an independently attributable timestamped attestation that no
   matching supported live/nonterminal run or consumer of the queried old
   identities remains there. The attestation must also place that named root
   under quiescence from the pre-edit scan through final validator execution
   and independent review. An agent must never synthesize, guess, default,
   paraphrase, or sign an owner name or attestation. The sole planned mutation
   is creation of the clean and interrupted/resumed **new-ID** runs in the
   dedicated evidence root after the source edit; no legacy root may mutate.
5. If any owner or attestation is missing, ambiguous, or not independently
   attributable, record exactly
   `STOP: missing known-store owner attestation`, keep
   `strict_compatibility` selected, and end without asking, retrying, editing
   source, or fabricating evidence under the standing unattended instruction.
   A matching supported live/nonterminal run, queried old consumer,
   nonempty/nonisolated dedicated root, or unexpected legacy-root mutation
   before the source edit also stops without an edit. Unrelated active runs are
   disclosed in `store_*` totals but do not select strict compatibility. Any
   unexpected legacy-root mutation after the source edit stops retirement
   acceptance; it cannot be cured by silently refreshing the evidence.

Only after all five steps and Task 1A's immutable pre-edit evidence commit pass
may Task 2 make its one `.orc` edit. After that edit, only the dedicated
evidence root may receive writes, and only for the clean and
interrupted/resumed new-ID runs. Stop all writes after those runs, rescan every
enumerated root, and write `final_known_store_scans.json`. Each quiesced legacy
root must match its pre-edit digest, matching counts, store-wide totals, and
every other scan count exactly. The dedicated root
must receive a second genuine named-owner attestation for its final snapshot.
Populate `retirement_record.json.known_state_stores` with the final scan facts
and applicable genuine attestations so the validator's fresh rescan observes
the same state. Preserve the immutable pre-edit facts separately and link them
by digest in `evidence_index.json`; neither companion evidence nor the record
is a runtime input.

Freeze all roots after the final scan until `validate_retirement_record` and
independent review complete. Any validator rescan mismatch stops acceptance.
Only the planned dedicated-root mutation permits a final rescan and second
attestation; a legacy-root mismatch requires stopping this pilot attempt, not
fabricating or backdating an attestation. Then complete the full old/new
identity delta, keyed artifact-contract multiset, separate execution-order
comparison, new-ID clean-run and interruption/resume evidence, and both
checksum negative proofs. The record makes no claim that an old run resumes
across changed source.

### Task 1: Freeze The Pre-Migration Contract And Write RED Tests

**Execution note:** Completed by commit `453ad2f9`. The checked-in old baseline
and original-source observations are retained evidence. Do not regenerate,
refresh, or reinterpret them under the new source.

**Files:**
- Create: `tests/baselines/procedure_first/tracked_plan_phase.json`
- Create: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Inspect: `tests/test_workflow_lisp_key_migrations.py`
- Inspect: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

- [x] **Step 1: Capture the baseline from the unmodified source**

Compile `design-plan-impl-review-stack` through `compile_stage3_entrypoint` with the existing provider/prompt extern JSON files and empty command boundaries. Serialize stable, semantic fields only:

- public entry/module identity and exported workflow set;
- public inputs/defaults and output contracts;
- artifacts and publication refs;
- terminal outcome and lowered step order;
- caller-visible effect kinds/subjects;
- source-map origin keys and expansion/call-site lineage;
- state-layout write roots;
- runtime-plan checkpoint IDs, presentation keys, kinds, and resume identity hints; and
- the `tracked-plan-phase` call/procedure route needed to compare the migration.

Do not snapshot whole debug YAML or unstable object reprs.

- [x] **Step 2: Write the RED source-shape test**

Assert the module has exactly one exported `defworkflow`, `design-plan-impl-review-stack`; `tracked-plan-phase` is a `defproc` with requested/resolved lowering `inline`; and the public wrapper contains a procedure call rather than a child-workflow call for that phase.

- [x] **Step 3: Write the RED contract-comparison test**

Compile the checked-in source and compare its stable
public/output/artifact/effect/source-map/state/checkpoint/resume projection to
`tracked_plan_phase.json`. The frozen test records the old route; after the
source edit, compare it through the validated retirement evidence rather than
refreshing it. Require all public identities and every old identity not
explicitly classified as an eligible reviewed retirement to remain equal.

- [x] **Step 4: Run RED tests**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'tracked_plan_phase'
```

Expected: collection succeeds; source-shape and route assertions FAIL because `tracked-plan-phase` is still a `defworkflow` called with `call`.

- [x] **Step 5: Commit baseline and RED tests**

```bash
git add tests/baselines/procedure_first/tracked_plan_phase.json tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "test: freeze tracked plan procedure pilot parity"
```

### Task 1A: Freeze Pre-Edit Retirement Evidence And Store Quiescence

**Files:**
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/pre_edit_known_store_scans.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/index.json`
- Create owner-supplied records under:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/pre-edit/<sha256-of-canonical-root>.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/old/source.orc`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/old/build_manifest.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/inputs/provider_externs.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/inputs/prompt_externs.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/inputs/command_boundaries.json`
- Create the six old production artifacts under that same `old/` directory:
  `typed_frontend_ast.json`, `semantic_ir.json`, `executable_ir.json`,
  `runtime_plan.json`, `lexical_checkpoint_points.json`, and `source_map.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json`

- [x] **Step 1: Make ordinary runtime harness workspaces explicit and ephemeral**

**Completed:** harness workspace hygiene landed separately at `7ac96c41`.
Disposal of the bound scratch set was owner-confirmed separately in
`docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/pre-edit/scratch-provenance-confirmation.json`.
This completion does not claim root enumeration, known-store scans or
attestations, or quiescence.

Change `_execute_design_plan_impl_stack_single_pass_runtime` to require an
explicit `workspace: Path`; remove its internal persistent
`tempfile.mkdtemp`. Normal tests receive a yield fixture backed by
`tempfile.TemporaryDirectory`, pass its path to the helper, and assert in the
fixture finalizer that the directory no longer exists after cleanup. Add a
cleanup-focused test assertion. The later pilot evidence invocation bypasses
that ephemeral fixture and passes the dedicated evidence workspace explicitly
so its two new-ID runs are retained.

Before any store scan, identify and remove only stale scratch directories
proven to have been created by the old
`design-plan-impl-stack-` helper. Ordinary test workspaces are ephemeral
scratch, destroyed before final scans, and are never attested durable stores.
If ownership of a leftover directory is ambiguous, stop rather than delete or
exclude it silently.

- [ ] **Step 2: Enumerate roots and prove dedicated-root isolation**

Complete Mandatory pre-edit gate Steps 1-2. Record every canonical legacy
root and the dedicated evidence root separately. Prove the dedicated root is
empty, contains no old identity, and is not equal to or below a legacy root.
Do not edit the pilot source.

- [ ] **Step 3: Scan, attest, and quiesce every root**

Complete Mandatory pre-edit gate Steps 3-5. Write the exact scanner outputs to
`pre_edit_known_store_scans.json`, including match-scoped run/consumer counts
and the non-gating `store_terminal_run_count` /
`store_nonterminal_run_count` totals. Store each genuine owner-supplied
attestation verbatim under the deterministic canonical-root digest filename
and bind those paths and content digests in `attestations/index.json`. The
attestations must cover the time-bounded quiescence window through final live
validation and independent review. Missing evidence takes the exact unattended
stop path; an agent does not create a placeholder.

- [ ] **Step 4: Snapshot build inputs and retain the old production artifact set**

Copy the actual pilot provider externs, prompt externs, and command-boundary
inputs byte-for-byte from
`workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json`,
`workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json`,
and
`workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`
to the three exact `inputs/` paths.
Review that these are the inputs supplied to the production compile command.

Copy the still-unmodified `.orc` source to `old/source.orc`, compile/build it
through the production WCC route, and retain all six required output artifacts.
Write `old/build_manifest.json` with schema
`workflow_lisp_procedure_retirement_build_manifest.v1`; it must record the
`old` side, retained entry, lowering route, compiler/build labels, and
repo-contained readable references for `source`, `provider_externs`,
`prompt_externs`, and `command_boundaries`, plus the six outputs. Every entry
binds its exact relative path and SHA-256. Record the manifest and input/output
digests in the initial `evidence_index.json`. The frozen Task 1 baseline remains
unchanged and is linked by digest; it is not regenerated.

- [ ] **Step 5: Recheck quiescence immediately before source selection**

Rescan every root. Legacy and dedicated-root digests/counts must still equal
the pre-edit facts. Any unexpected mutation records a stop and leaves the
source unedited. Confirm the protected staging guard and confirm
`workflows/examples/design_plan_impl_review_stack_v2_call.orc` has no diff.

- [ ] **Step 6: Commit immutable pre-edit evidence and harness hygiene**

```bash
git add tests/test_workflow_lisp_key_migrations.py docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/pre_edit_known_store_scans.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/index.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/pre-edit docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/inputs docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/old docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json
git diff --cached --name-only
git commit -m "evidence: freeze tracked plan retirement pre-edit state"
```

Expected: only the harness hygiene and listed pre-edit evidence are committed; genuine
attestations are byte-for-byte owner-supplied records; the pilot source and
frozen baseline are unchanged. Task 2 becomes selectable only after this
commit and the quiescence recheck pass.

### Task 2: Convert Only `tracked-plan-phase`

**Evidence status:** Every Task 2 comparison is provisional characterization.
Passing it does not authorize identity retirement; only Task 4A's complete
record, mandatory live validator, and independent approval can do so.

**Files:**
- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Change the definition to an explicit inline procedure**

Do not begin this step until the Mandatory pre-edit retirement gate has passed.

Make the definition header equivalent to:

```lisp
(defproc tracked-plan-phase
  ((design_path DesignDocPath)
   (plan_target_path PlanDocTarget)
   (plan_review_report_target_path ReviewReportTarget))
  -> PlanPhaseOutput
  :effects ((uses-provider providers.plan.draft)
            (uses-provider providers.plan.review))
  :lowering inline
  ...)
```

Preserve its body and typed `PlanPhaseOutput` return exactly.

- [ ] **Step 2: Replace only its caller**

Replace the keyword `call` form with the positional procedure application:

```lisp
(tracked-plan-phase
  design.design_path
  plan_target_path
  plan_review_report_target_path)
```

Do not change the other two `(call ...)` forms.

- [ ] **Step 3: Add the POST-EDIT actual-pilot cross-route characterization**

In `tests/test_workflow_lisp_procedure_first_migrations.py`, add
`test_post_edit_tracked_plan_phase_does_not_use_schema1_iteration_override_across_routes`.
Compile the edited pilot source through `compile_stage3_entrypoint` once with
the classic `legacy` route and once with `wcc_m4`, using the actual pilot entry
and extern/command inputs. Instrument the exact legacy predicate
`orchestrator.workflow_lisp.lowering.procedures._schema1_iteration_private_override_applies`
for both compilations and record only decisions for the actual
`tracked-plan-phase` procedure.

Require the classic compilation to observe at least one predicate decision for
`tracked-plan-phase` and require every such decision to be false: no call site
may select the schema-1 private override. Require the WCC compilation to record
zero calls to that legacy-only predicate. For each route, also require the
procedure's requested and resolved lowering modes to be `inline`,
`generated_workflow_name` to be `None`, and the lowered-workflow inventory to
contain no generated private workflow for `tracked-plan-phase`. This is a
post-edit characterization of the real pilot, not a substitute for the generic
fixture or permission to refresh the frozen pre-edit baseline.

- [ ] **Step 4: Run the source and compile parity tests**

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'tracked_plan_phase'
pytest -q tests/test_workflow_lisp_key_migrations.py -k 'design_plan_impl_stack_orc_compiles_with_phase_family_contracts'
```

Expected: the source/compile and actual-pilot cross-route characterizations
pass provisionally. Classic reports no private-override selection for
`tracked-plan-phase`; WCC never consults the schema-1 predicate; and neither
route produces a generated private workflow for the procedure. The
lowered workflow-name assertion in the existing key-migration test may need to
distinguish the one removed internal workflow from the retained public and two
untouched phase workflows; update that assertion, not the contract. Do not
treat this result as accepted retirement evidence.

- [ ] **Step 5: Commit the one-phase migration**

```bash
git add workflows/examples/design_plan_impl_review_stack_v2_call.orc tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py
git commit -m "Migrate tracked plan phase to an inline procedure"
```

### Task 3: Prove Runtime, Artifact, Checkpoint, And Resume Parity

**Evidence status:** Task 3 produces provisional runtime characterization
under the new source. It cannot classify or approve a retired identity before
Task 4A validates and reviews the complete record.

**Files:**
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify only if a missing comparison is proven: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Extend the existing single-pass runtime smoke**

Keep `_execute_design_plan_impl_stack_single_pass_runtime` as the family harness. Assert the completed public output has the same nine fields and values, the plan and review artifacts are created at the same caller-supplied paths, and no private/generated workflow entry named for `tracked-plan-phase` is externally invocable.

- [ ] **Step 2: Add a new-ID resume-after-plan-provider-boundary test**

Use the existing deterministic fake provider harness and `StateManager` to
start a run from the new source. Fail once after the plan draft/review
boundary, resume that new-source run with the same `run_id`, and assert already
completed provider work is reused and the final public output and artifacts
match a clean new-source run. Compare checkpoint IDs and presentation keys to
the provisional old/new identity delta: public and expected-preserved entries
remain exact; candidate internal differences and new effect-owned entries are
recorded for Task 4A classification. No Task 3 assertion approves an identity.

- [ ] **Step 3: Run runtime and resume tests**

```bash
pytest -q tests/test_workflow_lisp_key_migrations.py -k 'design_plan_impl_stack'
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k 'checkpoint or resume or artifact or public_boundary'
```

Expected: the runtime/resume characterization passes provisionally; no retired
identity is accepted yet.

- [ ] **Step 4: Stop on an unreviewed or ineligible identity mismatch**

If inline lowering changes a public identity, an identity classified as
preserved, or any internal identity outside the reviewed retirement class,
stop. Also stop if the new-source run cannot resume under its new identities.
Do not update the old baseline, claim cross-source old-run resume, or add an
implicit remap. Eligible internal call-boundary retirement proceeds only
through the complete validated record, substantive repository/store evidence,
root and callee checksum negatives, keyed artifact comparison, separate order
review, and independent approvals.

- [ ] **Step 5: Commit runtime evidence**

```bash
git add tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_procedure_first_migrations.py
git commit -m "Prove tracked plan procedure runtime parity"
```

### Task 4: Run Compile, Dry-Run, Semantic, And Family Parity Gates

**Files:**
- Modify only if a new evidence selector is required: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify only if the existing report cannot express the evidence: `tests/test_workflow_lisp_migration_parity.py`
- Refresh generated evidence: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`
- Modify after evidence passes: `docs/workflow_lisp_route_readiness_registry.json`

- [ ] **Step 1: Compile through the production route**

```bash
python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --emit-semantic-ir .orchestrate/tmp/procedure-first-pilot/semantic_ir.json --emit-source-map .orchestrate/tmp/procedure-first-pilot/source_map.json
```

Expected: exit 0; emitted Semantic IR includes both plan provider effects under the public entry, and the source map attributes them to `tracked-plan-phase` plus its consuming call site.

- [ ] **Step 2: Dry-run the retained public wrapper**

```bash
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --input brief_path=workflows/examples/inputs/major_project_brief.md --input design_target_path=docs/plans/parity-design.md --input design_review_report_target_path=artifacts/review/parity-design-review.md --input plan_target_path=docs/plans/parity-plan.md --input plan_review_report_target_path=artifacts/review/parity-plan-review.md --input execution_report_target_path=artifacts/work/parity-execution.md --input implementation_review_report_target_path=artifacts/review/parity-implementation-review.md --dry-run
```

Expected: exit 0.

- [ ] **Step 3: Rerun the existing family parity gate**

```bash
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity --target design_plan_impl_stack
pytest -q tests/test_workflow_lisp_migration_parity.py -k 'design_plan_impl_stack'
```

Expected: the `design_plan_impl_stack` row passes compile, dry-run, runtime, artifact, output, and resume evidence. Do not alter unrelated target rows.

- [ ] **Step 4: Update route evidence without promotion**

Add the new procedure-first comparison selector to the existing route-readiness entry. Keep `route_label: migration_candidate`, `readiness_label: leaf_runtime_candidate`, and `copy_safety: migration_evidence_only` unchanged.

- [ ] **Step 5: Commit evidence routing**

```bash
git add workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json tests/test_workflow_lisp_migration_parity.py artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json docs/workflow_lisp_route_readiness_registry.json
git commit -m "Record tracked plan procedure pilot evidence"
```

Stage only the listed files that actually changed; never stage the parity
directory wholesale.

### Task 4A: Assemble, Validate, Review, And Commit The Retirement Record

**Files:**
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/final_known_store_scans.json`
- Create owner-supplied:
  `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/final/dedicated-evidence-root.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/new/source.orc`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/new/build_manifest.json`
- Create the six new production artifacts under that same `new/` directory:
  `typed_frontend_ast.json`, `semantic_ir.json`, `executable_ir.json`,
  `runtime_plan.json`, `lexical_checkpoint_points.json`, and `source_map.json`
- Create under `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/`:
  `identity_delta.json`, `artifact_contract_multiset.json`,
  `execution_order.json`, `clean_run.json`, `interruption_resume.json`,
  `root_checksum_negative.json`, `callee_checksum_characterization.json`,
  `live_validator_pytest.txt`, and `live_validator_result.json`
- Create: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/retirement_record.json`
- Modify: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json`
- Modify: `docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/index.json`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [ ] **Step 1: Produce new-ID run/resume evidence only in the dedicated root**

Create the clean new-ID run and the distinct interrupted/resumed new-ID run in
`.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`.
No legacy root may receive a write. Retain the clean and interruption/resume
projections at the exact tracked paths above, then stop writes to the dedicated
root.

- [ ] **Step 2: Drain ephemeral harnesses, then final-scan and freeze every root**

Run the focused and broad gates that exercise the ordinary runtime harness
before taking final scan facts. Those tests must use only their
`TemporaryDirectory` yield fixtures, and every fixture finalizer must prove its
scratch workspace was removed. Assert that no `design-plan-impl-stack-*`
scratch directory or other unenumerated persistent run store remains. Normal
test scratch is never added to `known_state_stores`; any surviving directory
is a `STOP` until its ownership is established and cleanup succeeds. After the
source edit there may be no unenumerated persistent store.

Then rescan every enumerated root with the same old identities and query version.
Write the raw normalized facts to `final_known_store_scans.json`. Require every
legacy digest/count to equal its pre-edit value exactly. Obtain the genuine
named owner's second timestamped attestation for the dedicated root's final
snapshot and store it verbatim at the fixed final-attestation path. Freeze all
roots from this point through the live validator and independent review. A
legacy mismatch stops acceptance; only the dedicated root's planned new-ID
run mutations explain its pre/final delta.

- [ ] **Step 3: Build new artifacts and assemble the complete record**

Copy the one edited source to `new/source.orc`; compile/build the new side
through the same production WCC route; retain its manifest and six production
artifacts. Write `new/build_manifest.json` with schema
`workflow_lisp_procedure_retirement_build_manifest.v1`, the reviewed
compiler/build labels, and the same four input roles and six output roles as
the old manifest. When extern/command inputs are unchanged, both manifests
must reference the same three readable repo-contained `inputs/` snapshots and
their exact digests; no manifest path may be missing. Regenerate and replay
both manifests against the repository, require every referenced source/input/
output digest to match readable bytes, and require old/new compiler/build
labels and role sets to agree.

Bind every old/new exact relative artifact path and SHA-256 in
`retirement_record.json`. Populate its `known_state_stores` from the final scan
facts and applicable genuine attestations, keep
`external_store_absence: not_asserted`, and populate the full identity delta,
keyed artifact multiset, separate execution order, lineage notes, new-ID
run/resume facts, and root/callee checksum evidence. Update
`evidence_index.json` and the attestation index with content digests. Neither
the record nor either index is a run/resume input.

- [ ] **Step 4: Add a deterministic retained-evidence replay test**

Add
`test_tracked_plan_phase_retirement_record_replays_final_scan_evidence` to
`tests/test_workflow_lisp_procedure_first_migrations.py`. It must:

1. load the actual tracked `retirement_record.json` with
   `load_retirement_record`;
2. load the content-addressed `final_known_store_scans.json`;
3. use a **test-local** monkeypatch of
   `procedure_identity_retirement.scan_known_state_store` that selects a row by
   canonical root, requires the exact retired-identity query and query version,
   and returns only that retained row's normalized scan facts;
4. call `validate_retirement_record(record, repo_root=REPO_ROOT)`; and
5. assert `result.valid is True` and `result.issues == ()`.

This replay seam belongs only to the deterministic contract test. It does not
change production validation, does not claim a mutable external root is still
absent, and does not turn retained scan facts into runtime authority. The
existing hardcoded source-shape/structural-delta tests remain provisional
characterization and cannot accept a retired identity.

Run:

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_retirement_record_replays_final_scan_evidence
```

Expected: PASS from the tracked record, tracked artifacts, and exact retained
final scan facts without consulting mutable live roots.

- [ ] **Step 5: Run the one-time live validator inside the frozen window**

Add an opt-in
`test_tracked_plan_phase_retirement_record_validates_live` in the same module.
It loads the actual record, calls the unpatched public
`validate_retirement_record(..., repo_root=REPO_ROOT)`, and asserts valid. It is
skipped unless
`ORCHESTRATOR_RUN_LIVE_PROCEDURE_RETIREMENT_VALIDATION=1`, so future default
test runs do not silently depend on mutable external roots. During the
time-bounded final-scan freeze, run exactly:

```bash
bash -o pipefail -c 'ORCHESTRATOR_RUN_LIVE_PROCEDURE_RETIREMENT_VALIDATION=1 pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_plan_phase_retirement_record_validates_live 2>&1 | tee docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/live_validator_pytest.txt'
```

Record the exit status, record digest, final-scan digest, live observed store
digests/counts, and stdout digest in `live_validator_result.json`, then update
`evidence_index.json`. This is the mandatory one-time live proof; the replay
test is its durable contract check, not a replacement for it.

- [ ] **Step 6: Obtain independent specification/runtime-state approval**

The reviewer must verify the live validator ran while all roots were frozen;
its observed roots, queries, digests, counts, and result match
`final_known_store_scans.json`, `live_validator_result.json`, and the replay
facts; every owner record is genuine and properly attributed; the dedicated
root is the only mutated root; the three build-input snapshots are readable
and digest-bound; both v1 manifests replay with matching labels, roles, and
content; the old/new artifact set is complete; and the record contains no
runtime directive or cross-source resume claim. The review
must explicitly recognize that live validation is time-bound and that the
default replay test asserts retained evidence consistency, not current
external-store absence.

- [ ] **Step 7: Commit the reviewed production record and validation tests**

Run the protected staging guard, then:

```bash
git add docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/final_known_store_scans.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/final/dedicated-evidence-root.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/index.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/new docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/retirement_record.json docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json tests/test_workflow_lisp_procedure_first_migrations.py
git diff --cached --name-only
git commit -m "evidence: validate tracked plan identity retirement"
```

Expected: the commit contains only the exact record/artifact/evidence/test
paths owned above. The live proof and review occurred before the time-bounded
freeze ended; default future tests use the deterministic replay seam and do
not rescan mutable roots.

### Task 5: Complete The Pilot Gate

**Files:**
- No expected source changes.

- [ ] **Step 1: Run focused collection and integration suites**

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_route_readiness.py
```

Expected: PASS. The deterministic retained-scan replay test passes. The
time-bounded live validator test is skipped unless its explicit environment
gate is set; its mandatory frozen-window result is already retained under the
pilot evidence root and is reviewed independently.

- [ ] **Step 2: Run the broad suite in tmux**

Use the `tmux` skill:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: PASS except only established unrelated failures with fresh isolated reruns and explicit disposition.

- [ ] **Step 3: Review scope and public-negative preservation**

```bash
git diff --check HEAD~5..HEAD
git diff HEAD~5..HEAD -- workflows/examples/design_plan_impl_review_stack_v2_call.orc
rg -n '^  \(export|^  \(defworkflow|^  \(defproc tracked-plan-phase|\(call tracked-plan-phase' workflows/examples/design_plan_impl_review_stack_v2_call.orc
```

Expected: only `tracked-plan-phase` and its one call changed; `design-plan-impl-review-stack` remains the sole export/public workflow; no `(call tracked-plan-phase` remains.

- [ ] **Step 4: Obtain independent specification and quality reviews**

Specification review must check every migration-test axis in the accepted
contract and reconcile the retained live-validator result with the
deterministic replay facts. Quality review must check that the baseline is
semantic rather than textual, the runtime test is non-tautological, the
structural tests were not used to authorize retirement, mutable external roots
are not consulted by default tests, and no Stage 6 retirement leaked into the
pilot. Resolve findings and rerun both reviews whole.

## Completion gate and stop conditions

The pilot is complete only when the mandatory pre-edit scans and genuine
owner attestations passed before the source edit; the complete retirement
record passes the time-bounded live validator and the deterministic retained-
scan replay; the source-shape test, stable contract and keyed artifact
comparisons, separate execution-order review, new-ID one-pass runtime and
resume test, both checksum negatives, compile, dry-run, family parity, focused
suites, broad suite, and independent specification/runtime-state and quality
reviews pass. Retained old artifacts and the frozen baseline must still be
content-addressed and readable.

Stop without widening scope if:

- public `design-plan-impl-review-stack` inputs, outputs, artifacts, terminal behavior, or invocation identity change;
- either plan provider effect disappears from the caller-visible effect graph or Semantic IR;
- source-map lineage loses the procedure definition or consuming call site;
- any public or preserved checkpoint/resume identity changes, or an internal
  identity changes without validator-approved substantive eligibility,
  pre-edit scans and attestations, checksum negatives, artifact/order review,
  and independent approval;
- any known-store owner attestation is missing, ambiguous, unattributable, or
  agent-authored, or external-store absence is inferred rather than recorded
  as `not_asserted`;
- the root changed-source negative reaches executor construction or mutates
  the persisted run tree, or the callee negative reaches child execution or
  remaps child state;
- a legacy root changes during the quiescence window, the dedicated root
  receives an unplanned write, the final live rescan differs from the record,
  or the replay facts differ from the retained live result;
- the migration requires changing another phase, the YAML twin, the runtime result transport, or the public DSL version; or
- the parity tool cannot distinguish the reviewed structural delta from a public contract regression.
