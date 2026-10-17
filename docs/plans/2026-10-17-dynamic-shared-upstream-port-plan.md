# Dynamic Branch Shared-Upstream Port Plan (hunk granularity)

> **For agentic workers:** execute with `superpowers:subagent-driven-development`,
> one task per implementer, a distinct reviewer per task, and
> `superpowers:verification-before-completion` before any completion claim.
> Checkboxes track delivery. This plan authorizes the port below and nothing else.

**Goal:** bring the dynamic branch's *shared* substrate up to main where main's
change is genuinely shareable or adaptable, so both runtimes run on the same
corrected performers and contracts. Select at hunk granularity, never by whole
commit, and never port main wholesale.

**Approach:** port three behavior packages and one deduplication hunk, each with
its main tests and spec wording, onto `feat/orc-dynamic-core-cutover`. What this
makes harder: the branch's typed route stays pre-retirement, so later retirement
or typed-feature ports still need their own coordinated change.

**Status and authority:** implementation plan, independently reviewed on
2026-10-17 (one blocker and seven majors resolved in this revision). The owner
selected the direction (main → dynamic, shareable hunks only, hunk granularity).
Normative owners remain `specs/{cli,providers,io,state,versioning}.md`; the
branch's native contract is `docs/design/workflow_lisp_dynamic_core_proposal.md`.
Nothing here selects DC-P adoption, runtime-profile defaults, target changes,
main merge or push.

**Recorded decisions (unattended; owner may reverse at review):**
- D-A: port the whole `3693acbd` executor/control patch, including the
  managed-jobs call sites (E2–E4), because it is one clean, main-verified unit.
- D-B: adopt main's streaming rule on both routes: provider output streams by
  default, `--quiet` silences it, `--stream-output` is accepted and inert. This
  is a deliberate stdout behavior change for the branch's typed 2.35/2.36 route
  and for native 3.0, which today never reads its `--stream-output` flag.
- D-C: with the teardown port, a zero exit while the owned process group still
  has members is a failure (main's `specs/providers.md` rule). Intended.
- D-D: pure refactors are deferred unless they are prerequisites.

## Pins, preservation and evidence

- Integration worktree: `/var/tmp/agent-orchestration-dynamic-shared-port-20261017`,
  branch `integrate/dynamic-shared-port-20261017`, base `74fae634` (branch tip).
- Control worktree (read-only product code): `/var/tmp/agent-orchestration-dynamic-control-74fae634`
  at `74fae634`, for paired runs of any selector that is not in the baseline.
- Upstream inspection pin: main `90ae778c`; merge-base `93a33ae2`.
- Environment pin for every campaign and control run: `/home/ollie/miniconda3/bin/python`
  (3.13.9) with `PYTHONPATH` set to the worktree being tested and `-p no:cacheprovider`.
- Evidence root (absolute): `/var/tmp/orc-dynamic-evidence/shared-port-20261017/`
  (`baseline/`, `main-control/`, `patches/`, `inventory-*.md`, per-task receipts).
  Backups: `/var/tmp/orc-dynamic-evidence/feat-orc-dynamic-core-cutover-74fae634.bundle`
  (verified) and `target-overlay-20261017.patch` (sha256 `ad2bdfc6…`) plus the
  target's untracked `docs/plans/2026-10-13-repl-w3-documentation-consistency-plan.md`.
- Target worktree `/var/tmp/agent-orchestration-orc-dynamic-core` (21 dirty docs
  including `specs/providers.md`, `specs/io.md` and
  `docs/design/workflow_lisp_dynamic_core_proposal.md`; one untracked plan) and
  original main are observed only until Task 6.
- Baseline, pre-change, 54 affected modules at `74fae634`: 2205 passed, 0 failed,
  129.9 s (`baseline/affected.log`, `baseline/selectors.txt`). Main control at
  `90ae778c`: `tests/test_provider_execution.py tests/test_provider_execution_control.py`
  194 passed (`main-control/teardown-tests.log`).
- Commit per task with explicit pathspecs; no attribution trailers.

## Selected scope

| Package | Upstream source (hunk-restricted) | Adaptation on the branch |
| --- | --- | --- |
| 1. Provider process-group teardown repair | `3693acbd` restricted to `orchestrator/providers/{executor,control}.py` (`patches/teardown-code.patch`, applies cleanly, excludes `3e07b8cd`) and its hunks in `tests/test_provider_execution{,_control}.py` (`patches/teardown-tests.patch`, applies cleanly; carries no `launch_cwd`/`logical_workspace_root` tests); `specs/providers.md` owned-group teardown wording (Timeouts section) | None expected in code; expected result is exactly 194 passed in the two modules. The native OMP path runs `_execute_session_invocation`, which on the branch still calls the defective `_terminate_process_tree`. |
| 2. Streaming rule (D-B) | `ce8a41d7`: `orchestrator/workflow/evaluated/{providers,runtime}.py`, `orchestrator/cli/commands/{evaluated,resume}.py`, `tests/test_workflow_evaluated_providers.py`; `specs/cli.md` wording | The runtime/evaluated/resume hunks apply cleanly; the `providers.py` hunk is adapted by hand (`perform_provider` hard-codes `stream_output=False` at ~302). Native: `orchestrator/cli/commands/dynamic.py` (add `--quiet`; keep `--stream-output` inert), `orchestrator/workflow/dynamic/runtime.py` (~289) and the `execute_dynamic_run → _perform_dynamic_provider` path in `orchestrator/workflow/dynamic/evaluator.py`. The branch spec lacks the paragraph `ce8a41d7` edits, so write the rule at the dynamic run paragraph (~`specs/cli.md:271`) and the 2.35/2.36 resume bullet (~299); update `workflow_lisp_dynamic_core_proposal.md` ~1063 (overlay overlap in Task 6). Skip the `test_workflow_lisp_closed_program_corpus.py` hunk unless it fails without it. |
| 3. Reply-excerpt blanking | `acfc3708` and the `providers.py` excerpt hunk of `aba32230`; test `test_public_missing_result_names_the_reply_head_and_resume_retries` (main `tests/test_workflow_evaluated_provider_delivery.py:357`) and the shim modes `silent`/`nul` (main `tests/test_workflow_evaluated_providers.py:42-43`) | `_provider_result` names the reply head with non-printables blanked. The branch's `test_omp_missing_normalized_stdout_uses_missing_result_diagnostic` (`test_workflow_evaluated_provider_delivery.py:164`) asserts `raw not in message` only because the branch never added the excerpt; replace it with main's `"reply began:"`/`raw in message` assertions. That is adoption of the new behavior, not weakening. Fixture and docstring parts of `aba32230` are already present; confirm, do not duplicate. |
| 4. `_parse_output_value` delegation | `3693acbd` hunk at `orchestrator/contracts/output_contract.py` (main `_parse_output_value`, ~1245) | Deduplication only; behavior-neutral because the branch's `strict_transport_values` defaults to False. Existing `tests/test_output_contract*.py` stay green. |

## Excluded, with reasons (from the inventories)

- **Typed-only features** (2.37 parallel map, 2.38 agent sessions/`agent_turn`,
  confined run-ref, 2.39 phased providers and inferred effects, `Agent` type,
  Claude session codec, `effect_execution.py`, launch-cwd/logical-workspace
  parts of `3e07b8cd`): no separable shareable core.
- **Retirement deletions**: the branch frontend still uses the removed names
  (`workflow_lisp/syntax.py`, `typecheck_pure_ops.py`, `form_registry.py`,
  `LOWERING_SCHEMA_*`, pure-result replay profile, `build.py` paths used by
  compile/run/resume/lsp); native imports `build.normalize_frontend_artifact_exports`
  and `prompt_scaffold_fs.open_root_creating`, both deleted on main. Retirement
  is a separate coordinated change.
- **Closed-program contracts**: no S hunks; the three A hunks (`s1/s2/n1`,
  walker move into `node_walk.py`) only matter if typed agent checks are ever
  ported; `t4/t6/c7/c4/c12/c20` would change 3.0 admission or 2.35/2.36
  artifact behavior.
- **Deferred shareable refactors** (no behavior, not prerequisites): pure
  operator catalog consolidation (needs a `typecheck_pure_ops` change), program
  identity extraction, REPL canonical source path, `_union_field_descriptor`,
  `repl_expr` import tidy, launch/result split, `WorkspaceFiles.read(max_bytes)`,
  failure-helper extractions, lazy `run_workflow` import, resume `exc.code` log,
  the `ce8a41d7` corpus-test hunk.
- **`print` operator**: a feature; native evaluator consequences unverified.
- **`_has_authority_header` and image-pin acceptance**: would alter native
  header/pin admission; need a dynamic exemption first.

## Execution rules

Coordinator owns scope, integration and final verification. Implementation role
`impl_code_` on Opus 5.5 high; distinct `review_code_` reviewer on Opus 5.5 high.
Run from the integration worktree with the environment pin. Long runs in tmux on a
private socket (`-q -n 16 --dist=worksteal`). Collect new/renamed test modules
first, run narrow selectors, then the affected campaign. No test is weakened,
skipped or deleted to hide a failure; any proposed test removal is escalated to
the coordinator instead of applied.

### Task 0: Baseline and inputs
- [x] Worktree, control worktree, bundle, overlay backup, inventories, patches,
  baseline and main control recorded as above; plan committed on the integration branch.

### Task 1: Port the teardown repair (package 1)
**Files:** `orchestrator/providers/{executor,control}.py`,
`tests/test_provider_execution.py`, `tests/test_provider_execution_control.py`,
`specs/providers.md`.
- [x] `git apply` both saved patches; run
  `python -m pytest -q -p no:cacheprovider tests/test_provider_execution.py tests/test_provider_execution_control.py`;
  expect exactly 194 passed. Anything else is an adaptation gap: fix or escalate.
- [x] Run the executor consumers on HEAD and on the control worktree, in tmux:
  `tests/test_managed_provider_execution.py tests/test_managed_provider_runtime.py tests/test_provider_session_transport.py tests/test_provider_observation_execution.py tests/test_provider_interactive_terminal.py tests/test_provider_peer_group_runtime.py tests/test_workflow_evaluated_provider_lifecycle.py tests/test_provider_supervision_ir.py tests/test_provider_supervision_resume.py tests/test_provider_supervision_runtime.py`.
  Attribute every HEAD-only failure; a failure that is the D-C rule taking effect
  is updated to the new contract with that reason in the commit.
- [x] Port the `specs/providers.md` owned-group teardown wording (reaped leader,
  observed-empty group, finite deadlines, settlement, D-C) into the branch's
  Timeouts section at hunk level; native/3.0 sections untouched.
- [x] Distinct review, then commit: `fix: port bounded owned-group provider teardown`.

### Task 2: Port the streaming rule (package 2)
**Files:** as listed in the scope table, plus `tests/test_workflow_dynamic_cli.py`.
Runs in parallel with Task 1 (disjoint files).
- [x] Add the `tests/test_workflow_evaluated_providers.py` hunk and a native
  subprocess regression (`python -m orchestrator … run` at 3.0 with a local
  provider shim) asserting provider output appears on stdout by default and not
  with `--quiet`, with `--stream-output` accepted; collect, show the failures,
  implement, rerun. Record at least one real CLI process per route in the receipt.
- [x] Run `python -m pytest -q -p no:cacheprovider tests/test_workflow_evaluated_providers.py tests/test_workflow_dynamic_providers.py tests/test_workflow_dynamic_cli.py tests/test_workflow_evaluated_resume.py tests/test_workflow_lisp_closed_program_corpus.py`.
- [x] Write the `specs/cli.md` wording and the proposal-doc line. Distinct
  review, commit: `feat: stream provider output through both runtimes`.

### Task 3: Port reply-excerpt blanking and the parser delegation (packages 3, 4)
**Files:** `orchestrator/workflow/evaluated/providers.py`,
`orchestrator/contracts/output_contract.py`,
`tests/test_workflow_evaluated_providers.py`, `tests/test_workflow_evaluated_provider_delivery.py`.
Starts only after Task 2 has committed (shared files).
- [x] Add the shim modes and the excerpt test; replace the branch assertion as
  described; show failure; port the two `providers.py` hunks.
- [x] Port the `_parse_output_value` delegation; run
  `python -m pytest -q -p no:cacheprovider tests/test_output_contract.py tests/test_output_contract_collections.py tests/test_output_contract_nested_transport.py tests/test_output_contract_value.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_provider_delivery.py`.
- [x] Distinct review, commit: `fix: name the reply head in missing-result failures and deduplicate output parsing`.

### Task 4: Affected campaign and public smoke
- [x] In tmux: the 54 baseline modules plus the Task 1 consumer modules and any
  new modules; compare with the baseline (2205 passed, 0 failed) and, for modules
  outside the baseline, with the same selectors on the control worktree. Every
  HEAD-only failure is attributed by node and fixed or shown pre-existing.
- [x] Public smoke, real processes: the Task 2 native subprocess regression,
  `tests/test_workflow_dynamic_cli.py::test_actual_public_subprocess_fresh_run`,
  `tests/test_workflow_dynamic_repl.py::test_public_native_repl_reconstructs_completed_local_provider_result_read_only`,
  `tests/test_workflow_evaluated_invalidate_smoke.py`,
  `tests/test_workflow_evaluated_consumers.py -k 'best_of_n or public or smoke'`.

### Task 5: Full non-e2e campaign and integrated review
- [x] In tmux: `python -m pytest -q -n 16 --dist=worksteal -p no:cacheprovider -m 'not e2e' --ignore=tests/e2e`.
  Rerun every failing node on HEAD and on the control worktree with identical
  environment; compare normalized diagnostics (checkout/temp roots stripped). Use
  `/var/tmp/orc-dynamic-evidence/orc-dynamic-main-sync-20261015-yenoqng0/task7/failure-review/`
  only to group known causes. HEAD-only failures, or changed diagnostics, are
  fixed or demonstrated unrelated with evidence.
- [x] Distinct review of the whole integrated diff against `74fae634`;
  coordinator inspects `git diff --check`, `git diff --stat 74fae634..HEAD` and receipts.

### Task 6: Report, rehearse, then fast-forward the target
- [ ] Write `docs/reports/2026-10-17-dynamic-shared-upstream-port.md` (pins,
  final hash, receipts, attributed failures, deferred scope) and tick this plan;
  commit both before integration.
- [ ] Refresh the target snapshot (status, overlay patch, untracked bytes, modes)
  and compare with `target-overlay-20261017.patch`; if the owner changed files,
  use the newer state. Verify main's HEAD/index/worktree inventory for later comparison.
- [ ] Disposable rehearsal worktree at target HEAD `74fae634`; restore the overlay
  and untracked plan; verify byte equality with the target. Rehearse
  `git stash push --include-untracked -m dynamic-shared-port-rehearsal` (record
  the OID), `git merge --ff-only integrate/dynamic-shared-port-20261017`,
  `git stash apply --index <OID>`. Resolve only overlay overlaps
  (`specs/providers.md`, `docs/design/workflow_lisp_dynamic_core_proposal.md`)
  by a reviewed patch; verify the result against both inputs; run
  `git diff --check`, the doc link check (`python scripts/check_doc_links.py`
  on changed docs if present) and the Task 4 public smoke on the rehearsed tree.
- [ ] Recheck the target is unchanged since the refreshed snapshot, then perform
  the rehearsed sequence there with a named stash (`dynamic-shared-port-original-preserved-20261017`,
  OID recorded). Verify target HEAD equals the integration tip and the
  content/status manifest equals the rehearsal; verify main unchanged. If index
  restoration cannot be shown correct, leave the target untouched and report.
  Never `reset --hard`, `clean` or force refs. Keep the stash and backups. No push.

## Dependencies, rollback and completion

Tasks 1 and 2 are independent and edit disjoint files; Task 3 starts after
Task 2's commit; Task 4 follows 1–3; Task 5 follows 4; Task 6 follows 5. A failed
task is repaired or reverted with `git revert` on the integration branch with its
receipt kept. Completion requires the four packages committed, distinct reviews,
affected campaign at or above baseline with attributed failures, paired
full-campaign attribution, the committed report, and verified target integration
with the overlay preserved.
