# ORC Simplification Roadmap Extension

> **For agentic workers:** The selected bounded engineering scope and finite
> dispositions are complete. Preserve the captured verification and residual
> defect limits below; completion does not mean the full suite is green or close
> any main delivery-phase gate. New work requires its own selection.

**Goal:** simplify high-level composition while preserving useful type-derived
prompt, input and output contracts, and remove duplicated semantic ownership
from the compiler and runtime that remain supported.

**Architecture:** prioritize provider cleanup, close the retained static
executable WCC boundary through finite deletions, and consolidate result
decoding and validation. Main's specs, accepted designs and delivery plan
govern these lanes; the separate branch evaluation in Task 4 uses its existing
[dynamic-core production-adoption/migration gate (DC-P)](#dynamic-adoption-authority)
only for its bounded candidate migration.

**Tradeoff:** new target-2.39 definitions lose authored lowering strategy and
use inference-default procedure contracts, while admitted 2.35–2.38 definition
origins retain their existing semantics. The 2.35 source floor removes old-source
analysis/import support; historical data readers remain separate. Task 4 retains
typed W3 for the fixed consumers and stops this 3.0 adoption/migration lane.

**Tech stack:** existing Python, Workflow Lisp WCC/closed program/evaluator,
shared provider control and transport owners, pytest/pytest-xdist; no dependency,
second typed IR, process framework or replacement contract language is proposed.

## Status, evidence and authority

This is the selected simplification extension to the
[evaluated-execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md)
and [evolution roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md).
The owner instructed execution on 2026-10-15. This manual selection neither
reopens completed phases nor changes existing entry/acceptance gates. The delegated completion decision selects target 2.39 and the finite remaining
manual steps below. No new manifest, selector, research allocation or workflow
run is introduced.

**Integration status, 2026-10-16:** the selected implementation, 2.35 source floor,
2.39 C/D/E consumer delivery and reviewed durable documentation/routing changes
are complete for this selected scope. The captured full suite remains red:
69 failure mechanisms match the F campaign, one stale target assertion was
corrected and independently reviewed after the full snapshot, and a controlled
before/current probe demonstrates the remaining isolation timestamp-race
mechanism. The [final integration evidence](#final-integration-evidence--2026-10-16)
separates that frozen campaign from later focused corrections and records the
unresolved limits. No main Phase 5, Phase 6b or Phase 7 closeout follows.

The original review was supplied in the conversation; the
[review record](../reports/2026-10-15-orc-simplification-review.md) captures its
recommendations, source checks and rejected interpretations.
`70f5529` is its code-evidence pin, not a revision containing that review. This
planning revision inspected a broadly dirty checkout with HEAD at
`6005b5c1f105057a41a5a57882e5df90abf44118`; that commit alone does not
represent the historical working files. Execution uses the isolated worktree
`.worktrees/orc-simplification-20261015` based on that committed source, with
only this extension, its preserved report and its three routing changes copied
from the dirty checkout. Concurrent unrelated changes are not imported. Fresh
baseline results belong to the execution record below. The report's isolated process probe found a
terminated leader with a SIGTERM-ignoring descendant alive and its pipe open;
that is a concrete cleanup defect, not proof about every provider profile.
Historical full-suite failures are not a current baseline. The old E-B2 zero
gain/4.9× observation was subsequently classified as uncalibrated (`ddb1f3ae`);
it supplies neither a performance target nor an architecture verdict.
Do not infer a nested-loop defect from another form's refusal: current nesting
claims require the exact case in the totality/guide owners named below.

Semantic owners remain `specs/` and the relevant designs. Before implementing
changed behavior, update and review the corresponding owner below; roadmap
prose does not settle an unresolved language, compatibility or security contract.
Main's current contracts and delivery authority govern this entire plan.
Task 4's pinned branch documents are reference authority for that branch's
evaluation and bounded migration, not a replacement main contract.

| Work | Contract/design owners | Implementation and primary test owners |
| --- | --- | --- |
| Provider cleanup | `specs/providers.md`, `specs/io.md`; `specs/security.md` for boundary claims | `orchestrator/providers/executor.py`, `orchestrator/providers/control.py`; `tests/test_provider_execution_control.py` |
| Structured executable WCC | `docs/design/workflow_lisp_core_calculus_middle_end.md`, `docs/design/workflow_lisp_frontend_specification.md`, `docs/design/workflow_lisp_evaluated_execution.md`; `specs/state.md`, `specs/versioning.md` if identities/artifacts change | `orchestrator/workflow_lisp/wcc/{model,elaborate}.py`, `orchestrator/workflow_lisp/closed/{values,build}.py`; `tests/test_workflow_lisp_closed_program_{elaboration,check,sites,artifact}.py` |
| Result transport | `specs/io.md`, `specs/state.md`, `specs/versioning.md`, `docs/design/provider_result_delivery.md`, [numeric surface](../design/workflow_lisp_numeric_surface.md) and [transportable values](../design/workflow_lisp_transportable_value_type.md) | `orchestrator/contracts/output_contract.py`, `orchestrator/workflow/{type_descriptor,pure_expr}.py`, `orchestrator/workflow/evaluated/{machine,values}.py`, `orchestrator/workflow_lisp/contracts.py`; `tests/test_output_contract{,_nested_transport}.py` |
| Inferred effects | `docs/design/workflow_lisp_effect_ledger_simplification.md`, existing roadmap EL-1; frontend and versioning owners | `orchestrator/workflow_lisp/{effects,typecheck_effects}.py`; `tests/test_workflow_lisp_{effects,imported_effects}.py` |
| Shared pure preparation | evaluated/REPL designs and current Phase 5 plan | `orchestrator/workflow/pure_expr.py`, `orchestrator/workflow/evaluated/{parallel,replay}.py`; `tests/test_workflow_pure_catalog_agreement.py`, `tests/test_workflow_evaluated_parallel*.py` |
| Consumer retirement | `docs/design/workflow_lisp_executor_retirement.md`, existing Phase 6b/7 and any selected DC-P amendment | exact callers selected below, their public lifecycle tests and retained import/LSP owners |

Brace/glob notation identifies existing owner families, not blanket permission
to edit every member. Each selected slice must name its exact files, callers,
fixtures, configuration, exports and verification scope before implementation.

## Selection and execution record — 2026-10-15

The owner selected execution of the plan. The dispositions below bound that
instruction and distinguish completed work from remaining implementation.

| Lane | Current disposition |
| --- | --- |
| Task 0 | Bounded baseline/caller census and immediate guarantee correction complete; evidence and remaining Task 5 documentation scope below. No full-suite claim. |
| Task 1 | Complete for the selected owned-group cleanup defect: affected-profile verification and independent compliance/quality reviews passed. D2 preserves the inherited-session ordinary default; no default launch-policy change is selected. |
| Task 2 | Complete for D1’s selected retained executable boundary. All six cuts passed independent compliance and quality review; final v2 closure/inventory corrections and identity/runtime probes passed. The known computed-list capture defect is preserved for separate repair. No full-suite or phase-closeout claim. |
| Task 3 | The selected compatibility-preserving scalar consolidation is complete: equivalent rules are shared, affected checks and both reviews passed. Non-equivalent profile behavior is retained; no uniform semantics or further validator replacement is selected. |
| Task 4 | Decision: retain typed W3 for the demonstrated fixed improve/search consumers and stop this 3.0 adoption/migration lane. Reuse the pinned qualified evidence; keep dynamic research and its native function-value benefit. No new comparison or paid calls. |
| Task 5 engineering lanes | The selected executable specialization, authored-lowering removal, primitive rules, parallel preparation, finite retirement/source admission and documentation/routing changes are integrated. Slice reviews, final failure/population accounting, the post-full corpus correction and the isolation race disposition are recorded below. The selected scope is complete; suite health and main phase qualification are not claimed. |
| Task 5 executable specialization | Complete for the selected bounded command, dead inference forwarding and single-mode WCC body cuts. Both independent reviews passed, including eight supplemental public diagnostic cases. Combined production verification: 2,928 affected tests and 22 exact public outcomes. F subsequently removes the obsolete source-compilation mode; the condition-normalization stage distinction remains. Other Task 5 lanes keep their gates. |
| Task 5 parallel preparation | Complete for the selected source/bounds and one-item preparation slice. Live preflight and lazy read-only replay retain their timing; 96 affected tests and independent compliance/quality reviews passed. |
| Task 5 primitive rules | The five-operation catalog slice and equivalent concat/optional/list descriptor slice are complete. Original diagnostics, coercion and lazy behavior remain; respective affected suites (522 and 662), exact artifacts and independent compliance/quality reviews passed. Frontend dependent-type and transport checks retain their existing owner. |
| Task 5 EL-1 / source floor / lowering / intrinsic admission | B/F/C/D/E are integrated with reviewed contracts and finite owner/consumer dispositions. The 2.35 floor retires pre-floor source/import/REPL/LSP compatibility; 2.39 delivers inferred omission, checked restrictions, caller-owned inline composition and finite private-form admission. The proposal and compact search are the two migrated consumers; imported 2.35–2.38 definitions keep their semantics. Final C/D/E failure accounting preserves the red snapshot, separately accepted corpus correction and controlled isolation-race evidence; no green-suite or main-phase claim follows. |
| Task 5 optional lanes | Cancel EL-1d for this selection because no consumer-backed simplification justifies replacing the live summary. Defer ordinary-provider confinement and environment/unlimited policy; retain D2 inherited ordinary defaults and the existing child-confinement gate. |

**Routing effect:** the selected finite lanes are integrated under the
dispositions above, with final comparison/correction evidence and explicit
residual-defect dispositions recorded below. Machine manifest/queue rows remain
**0 → 0**; no workflow selector is activated.
Existing research allocations, frozen evidence and the bounded DC-P retain/stop
decision are preserved. These manual delivery records do not select new work.

**Execution baseline:** worktree HEAD, `main` and freshly observed `origin/main`
all resolve to `6005b5c1f105057a41a5a57882e5df90abf44118`; the coordinator's
upstream fetch succeeded with no incoming source changes. The dynamic candidate
remains `1ecde6e4566cf38a9d9f642e4e5c74e45d71b368`, separate from main.

Fresh baseline evidence at that source revision, before implementation:

| Command / population | Result |
| --- | --- |
| Task 0's three named provider-control selectors | Exit 0; 3 passed in 2.44s |
| `pytest -q -n 16 --dist=worksteal tests/test_provider_execution_control.py tests/test_provider_execution.py tests/test_workflow_evaluated_providers.py tests/test_workflow_lisp_guide_programs.py` (tmux) | Exit 0; 240 passed in 22.59s |
| WCC narrow list/check and captured-shadowing selectors in `wcc-baseline.json` | Exit 0; 2 passed in 2.38s |
| `pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_closed_program_elaboration.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_evaluated_consumers.py tests/test_workflow_evaluated_resume_replay_boundary.py` (tmux) | Exit 0; 306 passed in 60.81s |

The three narrow cases are included in the 240-case population; these are not
243 distinct tests. Exact commands, exit records and captured output are in
`/tmp/orc-simplification-exec-20261015-psuk0c4o/{baseline.json,provider-narrow.log,affected-baseline.log}`;
these local temporary files are execution evidence, not portable fixtures.
The coordinator corrected README's undeclared-execution guarantee to describe
declared dependency byte identity and its limits. The coordinator also checked
`docs/architecture_overview.md` against current security/CLI owners: its checked
artifact/memo and 2.35–2.38 account already reflects the completed documentation
cleanup, so no duplicate repair is selected. Task 5's remaining README count
correction now names committed snapshot `6005b5c1` and its counting methods:
`scc` 4.1.0 reports 443 Python files, 226,951 code lines and 257,091 total lines
under `orchestrator/`, including the demo package. The tracked test tree has
572 `test_*.py` modules and 8,328 `test_*` function definitions; these replace
the unsupported collected-case approximation without claiming coverage.
Receipts are `/tmp/orc-simplification-counts-nq7_e_ak/{counts.json,test-source-counts.json}`.
This baseline does not establish full-suite health or close
Tasks 1/2/3.

The two WCC narrow cases are included in the 306-case population. Their exact
commands and logs are in the same temporary evidence directory's
`wcc-baseline.json`, `wcc-narrow.log` and `wcc-affected-baseline.log`.
The ordinary public-path regression
`TestProviderExecutor::test_managed_timeout_waits_for_owned_group_after_leader_exits`
in `tests/test_provider_execution.py` failed before production changes: the
timeout remained blocked by a descendant holding capture pipes after leader
exit. This records the before-change regression failure; the completed repair
is verified below.

**Task 1 execution result:** ordinary invocations with an owned group and
session invocations now reuse the existing controlled lifecycle. Cleanup
preserves the caller's cancellation grace, checks residual group membership,
escalates and bounds reap/capture/stdin settlement. Persistent `wait`/`poll`
errors still trigger bounded signalling and retain an explicit failure;
successful fallback reap does not turn the original error into success.
Inherited-session ordinary launches keep their existing default. Session
spooling/display and protocol normalization retain their profile behavior.

The final affected population passed **647 tests, with 4 skipped**, in 21.68s
(exit 0). It contains the original four baseline modules plus observation,
OMP launch/transport, evaluated session requests, supervision and run-ref
provider control. Both changed test modules collected **194 tests**. The
population includes the deterministic public evaluated-provider CLI smoke
`test_public_provider_dispatches_once_and_commits_its_typed_result`.
Independent compliance and quality reviews approved the final changes;
the coordinator inspected the diff and fresh outputs. Production code is
50 lines smaller across `providers/control.py` and `providers/executor.py`.

Exact commands, source hashes, RED/GREEN probes and limits are retained in
`/tmp/provider-cleanup-execution-record.json`; the final suite log is
`/tmp/provider-cleanup-expanded-v7.log`. Earlier failures remain recorded:
review found and corrected grace, session-spool and persistent-wait regressions.
Two test completion races were reproduced against baseline and patch, then
fixed by joining the executor within the original total deadline; assertions
and time budgets were preserved. A PID fixture now publishes atomically.
The expanded clean-source archive run is diagnostic evidence only: its absent
`.git` caused an unrelated OMP version-probe failure. These checks establish
the selected cleanup scope, not full-suite health or OS confinement; no live
or paid provider was used.

Task 4's read-only checkpoint confirmed the pinned packet's recommendation to
retain typed W3 for the demonstrated fixed consumers. It also preserves the
native function-value benefit, RW-I10 zero-limit and RW-S05 Boolean transport
differences, and the measured repeated calls after fresh restart. No comparison
was rerun, adoption decision taken, or production owner retired by this check.
EL-1's ES prelaunch-park hand-back is recorded in the evolution roadmap.
The later delegated completion decision below selects 2.39 and resolves the
remaining owner/adoption choices; it does not rewrite this earlier checkpoint.

### Task 0 bounded caller and WCC inventory

At source `6005b5c1`, cleanup callers in `providers/executor.py` are ordinary
streaming/timeout/exception paths in `_execute`, observed nonstream execution
in `_execute_observed_nonstream_invocation`, and session execution in
`_execute_session_invocation`. `_start_process`/`_run_process` select transport
launch behavior. Controlled execution separately owns
`_run_bound_controlled_invocation`, `_fail_bound_controlled_invocation`, group
quiescence and `_join_controlled_io_workers`; shared `providers/control.py`
owns controlled cancellation. Only invocation-owned groups enter Task 1's
repair; inherited-session launches keep their default. The public regression
and baseline above distinguish existing controlled coverage from that defect.

The frozen [source census](../reports/2026-10-15-orc-simplification-review.md#wcc-boundary)
records the initial opaque producers, backend re-entry and reverse consumers
at `6005b5c1`; it is evidence, not the current inventory. The completed contract
is [middle-end §13.2](../design/workflow_lisp_core_calculus_middle_end.md#132-retained-executable-wcc-closure).

### Task 2 completion and verification record

| Completed cut | Result and retained evidence |
| --- | --- |
| 1. Lists/blocks | Structured typed items and local blocks; matching opaque producer/re-entry deleted. 639 affected tests passed; twelve exact artifacts. `/tmp/orc-wcc-list-final-20261015.{sh,log,exit}`, `/tmp/orc-wcc-list-identity-20261015/after-compare.log`. |
| 2. Direct carriers/prepared prompts | Expansion blocks, discriminants, relpaths, bundle paths and prompt rows use prepared values; displaced raw branches deleted. 1,148 affected tests passed. `/tmp/orc-wcc-cut2-review-20261015`, `/tmp/orc-wcc-cut2-revision-affected-20261015.{log,exit,sha256}`. |
| 3. Structured children | Loop-state seed/update, nonempty head and rooted path operands are typed WCC; ordinary record-update keeps its ANF behavior. 733 affected tests passed, with nine exact structured artifacts and the ordinary-update control. `/tmp/orc-wcc-cut3-review-20261015`, `/tmp/orc-wcc-cut3-revision-final-20261015.sha256`. |
| 4. Pure maps | Source, binder body and static wrapper metadata are structured; map source/body re-entry deleted. Generated RunRef local comparison corrected without weakening descriptor/owner/field checks. 1,242 affected tests passed; eight exact map artifacts. `/tmp/orc-wcc-cut4-v3-verify-20261015.sh`, `/tmp/orc-wcc-cut4-v3-affected-20261015.{log,exit}`. |
| 5. Capture preparation | Existing requests retain WCC capture recipes and bound operands; missing preparations refuse. 1,395 affected tests passed, then 199 narrow tests after dead-class deletion. Eight exact capture artifacts/traces cover 23 request instantiations. `/tmp/orc-wcc-cut5-review-v3-20261015/manifest.json`; the 16-test bound-module supplement is `/tmp/orc-wcc-cut5-bound-coverage-supplement-20261015/manifest.json`. |
| 6. Boundary deletion | Entry/request semantic closure, instantiated capture wire validation and exact call inventory precede emission. Executable frontend/reverse bridges are removed; historical consumers are isolated. Final production v2 is `/tmp/orc-wcc-cut6-review-v2-20261015/manifest.json`; final probes and scope are in its sibling `verification-receipts.json`. |

Each cut received independent compliance and quality approval; the coordinator
inspected the diff and verification. Counts overlap and are not additive.
The final cut's broader affected run passed **2,413 tests** in 239.76s on v1.
Its subsequent capture-wire/inventory correction passed **137 affected tests**
in 17.94s on final v2; the changed boundary module collected **40 tests**.
Exact selectors, exits and source hashes are in the v2 manifest. The broader
2,413 result does not describe the corrected snapshot, and no full suite was
run. The later Task 5 command-mode completion record below supplies combined
verification for those cuts and the final Task 2 implementation.

Final v2 identity probes compare **44 complete artifact pairs** exactly:
12 list, seven direct-carrier, nine structured-child, eight map and eight
capture cases. Receipts are
`/tmp/orc-wcc-probe-adaptations-20261015/receipts/final-run.json`.
Three additional admitted old-header conditional artifacts and nine complete
runtime timelines match their pre-cut baseline. Halt and ordinary-update
controls remain byte-identical and evaluate from source-free artifacts to 13
and 1 respectively. Public compile/run/stop-resume and committed-effect reuse
checks are included in the affected owners; no real-provider qualification is
implied. Missing deleted instrumentation hooks are explicitly unavailable in
the copied probe receipts, not dynamic evidence of zero calls. Installed
callback tests instead disable actual frontend elaboration/ANF/reverse entries
after completed preparation.

The six authentic RunRef artifacts retain **30 mismatches**, all embedded
`compiler_runtime_identity_digest` differences caused by changed package bytes.
The raw results are preserved without normalization. A separate control
physically computes one retained cut-2 package identity and supplies it through
the existing internal builder seam: all six complete artifacts match exactly.
The original/control evidence is under
`/tmp/orc-wcc-cut4-runref-classification-20261015/`; final directories are
`after-cut6-v2-authentic` and `after-cut6-v2-control`. Fixed-input byte equality
establishes neither authentic-package equality nor cross-package resume
compatibility; production identity computation and refusals are unchanged.

**Remaining non-executable inventory:** `wcc/historical.py` retains reverse
reconstruction/substitution for provider-region resource-transition refusal
preparation. The later single-mode body cut removes the non-executable WCC
condition-classification projection; shared source condition normalization
retains its separate consumers.
The shared `WccAtom`/`WccValue` union still admits historical opaque values;
retained executable semantic-edge checks reject them before emission.
Diagnostic source/spans, nominal declarations, original callable identities
and frozen child capsules remain metadata. Old-header pure conditionals are
structured when prepared for admitted execution. Resource transitions retain
their refusal; no unsupported effect was admitted to close the boundary.
This is not a global grep-zero or removal claim.

**Known preserved defect:** a computed list bound in a stored `bind-proc` and
called twice returns `((8, 9), (8, 9))` while evaluating its additions twice:
`[(7, 1), (7, 2), (7, 1), (7, 2)]`. Explicit materialization evaluates them once.
This violates the unchanged
[evaluated capture contract](../design/workflow_lisp_evaluated_execution.md#4-the-closed-program);
it is not desired semantics or a once-only guarantee established by Task 2.
The baseline/after multiplicity and materialization boundaries are preserved.
Repair needs a separate behavior/identity disposition. Evidence:
`/tmp/orc-wcc-list-capture-probe-20261015.py`, archived compiler
`/tmp/orc-wcc-list-capture-baseline-20261015`, regression
`test_prepared_list_captures_preserve_materialization_order`.

## Dependencies and decisions at selection

Priority is scheduling guidance; dependencies are the edges below. Shared-file
edits are serialized or their combined result is requalified.

| Lane | Entry dependency | Exit owner |
| --- | --- | --- |
| Task 0 baseline | None | Fresh bounded baseline and selected-slice inventory |
| Task 1 process repair | 0 → 1; D2 before a default-policy change | Task 1 cleanup evidence |
| Task 2a WCC slice | 0 → 2a; D1 selects full Task 2 scope | Migrated family's structural and public evidence |
| Task 2b WCC completion | 2a → 2b | Retained executable boundary has no opaque payload or backend re-entry |
| Task 3 result contract | Task 0 and completed investigation; D3 selects compatibility-preserving consolidation | One acceptance contract per existing profile; equivalent duplication removed |
| Task 4 branch disposition | Reuse qualified pinned evidence and delegated owner decision | Retain typed fixed consumers; stop this 3.0 migration lane |
| Task 5 lanes | Each lane's existing entry/selection conditions | Each lane's stated exit |

Task 1 has priority but is not a technical prerequisite for Task 2a. EL-1d,
ordinary environment/unlimited-execution policy and confinement are separate
lanes; their own acceptance remains intact and they do not gate other repairs.

| Decision | Required disposition before the affected change |
| --- | --- |
| D1 — Task 2 scope | Selected in full on 2026-10-15: 2a is the first cut and 2b is completion. Conforming slices need no repeated approval; existing phase gates are unchanged. |
| D2 — ordinary session/PGID default | Preserve the current inherited-session default. Repair selected already-owned-group cleanup paths; any future default change requires a separate terminal/stdin/signal compatibility decision. |
| D3 — decoder and structured acceptance | Owner selected “Conservar compatibilidad; consolidar ahora las reglas equivalentes” on 2026-10-15. Preserve all existing target/profile numeric, JSON, path, optional and union behavior, including committed replay acceptance; consolidate only proved-equivalent rules. No uniform new semantics or target is selected. |

Versioning, retirement, EL-1 and confinement decisions retain their existing
owners; D1–D3 do not replace them. Implementation selection is bounded by the
explicit owner dispositions recorded here.

## Task 0 — Refresh the bounded baseline

- [x] Record main and candidate committed heads, dirty/concurrent ownership and
  applicable upstream deliveries. Read `docs/index.md`, the capability matrix
  and design routing; reconcile claims against owners and executable tests.
- [x] Trace every caller of the cleanup and output-validation seams. For WCC,
  list remaining opaque producers, closed-construction elaborator/ANF re-entry,
  reverse translation and retained child-type facts, classified by admitted
  executable form versus historical import/LSP-only consumer.
- [x] Pick the first WCC family from that inventory: an admitted construct
  with a real bridge deletion and a maintained consumer. Record its paths and
  expected removals here; do not turn a repository-wide census into a gate.
  Task 2's selected first family is `ListExpr`: its child translation
  genuinely calls the backend re-entry helper. Refresh that choice if producers
  or consumers change; tags and record updates do not supply that bridge cut.
- [x] Run the narrow current owners, saving revision, command, exit and result.
  Reuse prior evidence only for unchanged code/contracts and identified scope.
- [x] Refresh the completed
  [documentation cleanup](2026-10-15-current-documentation-cleanup-plan.md)
  before scheduling duplicate repairs. Correct any remaining guarantee
  overstatements in `README.md` and
  `docs/architecture_overview.md` against `specs/security.md`,
  `specs/providers.md`, `specs/io.md` and `specs/state.md`. If the README still
  claims nothing undeclared runs, replace that claim: checked manifests/result contracts do
  not constrain arbitrary subprocess behavior. Distinguish validation, owned
  process cleanup and OS confinement; committed-effect reuse does not guarantee
  exactly-once external effects across an interrupted precommit attempt.
  This correction accompanies baseline/cleanup and does not wait for WCC.

Initial commands, from the repo root:

```bash
git rev-parse HEAD
git status --short
rg -n 'WccOpaqueFrontendValue|frontend_value|frontend_body|_elaborate_expr_to_body|normalize_wcc_body_to_anf' orchestrator/workflow_lisp/wcc orchestrator/workflow_lisp/closed
rg -n '_terminate_process_tree|_join_controlled_io_workers' orchestrator tests
pytest -q tests/test_provider_execution_control.py::test_natural_leader_exit_with_lingering_child_is_cleaned_but_rejected tests/test_provider_execution_control.py::test_group_signal_failure_with_inherited_pipes_has_bounded_workers tests/test_provider_execution_control.py::test_cancellation_escalates_from_term_to_kill
pytest -q tests/test_workflow_lisp_guide_programs.py
```

**Exit:** a finite first slice and fresh baseline, including failures. No claim
of current suite health or complete compiler inventory follows from this check.

## Task 1 — Repair ordinary provider process cleanup first

**Files:** `orchestrator/providers/executor.py`, reuse
`orchestrator/providers/control.py`; extend
`tests/test_provider_execution.py` for the ordinary-path regression and
`tests/test_provider_execution_control.py` for controlled-path compatibility.
Clarify providers/IO specs if needed.

`ProviderInvocation.terminate_process_tree` currently defaults to `False` in
`orchestrator/providers/types.py`. Ordinary streaming/observed launches use it
for `start_new_session`; ordinary nonstreaming uses a grouped `Popen` path only
when true. Controlled and session execution have their own launch profiles.
Reusing cleanup code therefore does not by itself extend group ownership.

- [x] Verify the selected D2 compatibility scope in providers/IO and the
  actual launch callers: preserve the inherited-session ordinary default and
  repair residual children only for invocation-owned groups. Check terminal,
  stdin and signal behavior where affected. The public-path regression must
  demonstrate bounded teardown and truthful outcome without requiring a
  particular helper. A new ordinary default is outside this selection.
- [x] Add a regression that exercises ordinary public provider execution:
  the leader exits on SIGTERM, a descendant ignores it and retains stdout or
  stderr. Assert finite cleanup, owned-group termination and a truthful failure
  result; always clean up the test process group on assertion failure.
- [x] Make the test fail on the current implementation. Cover timeout and
  applicable exceptional/early-exit paths, including stdin/capture workers.
- [x] Reuse existing residual-group signalling and bounded worker-join logic;
  leader exit must not be mistaken for group quiescence. Preserve diagnostics,
  failure handling and supported platform behavior without a new supervisor.
  Apply it only where the invocation owns the group; test the independently
  selected ordinary-path policy rather than claiming every profile is grouped.
- [x] Trace every applicable launch profile/caller, including ordinary,
  controlled, session and transport variants, and cover each affected path.
  Verify a deterministic public evaluated-provider smoke, owned-group
  quiescence and joined capture/stdin workers. A failed signal or unfinished
  teardown must produce an explicit cleanup failure, not successful cleanup.
  Shared cleanup must not alter profile isolation.

```bash
pytest -q tests/test_provider_execution_control.py::test_natural_leader_exit_with_lingering_child_is_cleaned_but_rejected tests/test_provider_execution_control.py::test_group_signal_failure_with_inherited_pipes_has_bounded_workers tests/test_provider_execution_control.py::test_cancellation_escalates_from_term_to_kill
pytest -q tests/test_provider_execution.py
pytest -q tests/test_workflow_evaluated_providers.py
```

**Exit:** regression passes through the affected public path, bounded cleanup
reaches owned-group quiescence and joined workers or reports its residual
failure explicitly, and affected-profile compatibility is demonstrated under
the selected launch policy. PGIDs cannot contain descendants that escape the
owned group; this is no universal descendant or OS-confinement guarantee.

## Task 2 — Close the retained executable WCC boundary

**Disposition:** complete for the full D1 retained admitted executable scope.
The durable contract is
[middle-end §13.2](../design/workflow_lisp_core_calculus_middle_end.md#132-retained-executable-wcc-closure),
with frontend fact ownership in
[frontend §44.1](../design/workflow_lisp_frontend_specification.md#441-workflow-core-calculus)
and construction properties in
[evaluated execution §4.1](../design/workflow_lisp_evaluated_execution.md#41-properties).
The six-cut [completion record](#task-2-completion-and-verification-record)
above owns implementation evidence and its limits.

### Task 2a — One construct-family vertical slice

- [x] Settle structured list/block representation and resolved child facts in
  the owning designs; preserve generated types, specialization and provenance.
- [x] Delete the list raw-payload producer and matching translation/re-entry
  branches; extend binder-aware scope, substitution and capture traversal.
- [x] Verify lazy/nested/imported/generic/captured lists, independent artifact
  rejection, exact same-target artifacts and public run/resume behavior.
- [x] Obtain independent reviews and inspect the final implementation/evidence.

### Task 2b — Finish the retained boundary, family by family

- [x] Complete every retained admitted family without reducing supported scope
  or introducing a second IR or executable compatibility fallback.
- [x] Retain exact post-specialization source facts and synthesize generated
  types at their producers; preserve independent artifact type checking.
- [x] Complete capture recipes and bound operands before translation. Preserve
  observed evaluation counts and materialization, including the separately
  gated computed-list defect recorded above.
- [x] Remove shared executable `frontend_value`/`frontend_body`, backend
  elaboration/ANF and reverse-conversion calls/imports. Preserve named
  refusal consumers in `wcc/historical.py`; the later body cut removes WCC
  condition classification while preserving shared source normalization. Retain
  the shared opaque union explicitly for resource-transition refusal.
- [x] Enforce semantic closure for entry/request graphs, effect payloads,
  prepared operands and instantiated capture wires before emission. Check
  exact child inventory and once-only inventory consumption; reject malformed
  raw/opaque/unknown/missing/extraneous edges without reaching the emitter.
- [x] Verify source-free readback and runtime controls, equal-input canonical
  artifacts/sites/digests, retained diagnostic/target guards and public
  lifecycle. Preserve authentic RunRef package-pin mismatches separately.
- [x] Obtain independent compliance/quality approval for final v2 and promote
  the durable construction contract into maintained designs.

**Exit reached:** the retained executable boundary is structured and prepared,
with no executable source re-entry or reverse bridge. Historical consumers,
source metadata and excluded-effect refusals retain their explicit scope.
The later Task 5 record closes the bounded WCC specialization cuts; further
shared-mode retirement retains its own design and verification gates. Task 2
completion adds no gate to Phases 5, 6b or 7 and does not close those phases;
their existing closeout obligations remain intact.

## Task 3 — Choose one result-transport contract, then consolidate it

**Entry:** Task 0 and the bounded investigation are complete. The owner has
resolved D3 in favor of preserving compatibility and consolidating equivalent
rules now; the selected scalar parser cut below is complete. This lane does
not wait for complete WCC or dynamic adoption.

- [x] Trace the real validation owners and record finite observed truth
  table for **text decoding** and a separate table for **structured-value
  acceptance**, before choosing canonical semantics: `output_contract.py`'s
  `validate_contract_value`, `_parse_output_value`, `_parse_output_bundle_value`
  and `_validate_direct_transport_value`; `type_descriptor.py`'s
  `validate_transport_value`, `_validate_primitive_value`, `_validate_json_value`
  and `_validate_transport_path`; and evaluated `machine.py::_coerce_result` →
  `values.py::coerce_evaluated_value` → `pure_expr.py::coerce_pure_value` /
  `_coerce_value`. Include `workflow_lisp/contracts.py`'s schema derivation and
  captured-byte publication callers, not only the two structural validators.
  D3 preserves the observed decoding and acceptance profiles. Reuse an existing
  rule owner only where equivalence is proved; `validate_transport_value` does
  not replace callers with different semantics. The goal remains one acceptance
  contract per existing profile and removal of equivalent duplicated rules.
- [x] Cover numeric/Bool strings, recursive lists, Bool-versus-Int, Float from
  Int, integer range, finite numbers, record missing/extra fields, union
  active/inactive fields and whole-root values. Leaf and recursive bundle
  parsing can coerce strings; structural transport and pure coercion differ.
  Include `Value`'s strict JSON checks, the internal `Value`→`Json` projection,
  JSON depth/size/cycle checks and `_jsonable` behavior. Preserve the observed
  strictness/conversion differences under D3; broader reuse needs equivalence
  evidence for each affected caller.
- [x] Preserve and verify finite-number refusal at the exact caller targets/profiles:
  output validation has `finite_floats=False` by default and uses
  `non_finite_number`; transport Float is finite; pure coercion also scans for
  non-finite values. There is no current `refuse_non_finite_floats` helper to
  reuse. Preserve the numeric contract's target boundary (2.34) unless a
  versioned change is selected. Include typed-path traversal/absolute-path
  refusals and symlink escape checks through `_validate_relpath_value`,
  `_validate_relpath_value_by_path` and the workspace-file owner.
- [x] Settle before/after rules and target/profile compatibility in IO, numeric,
  transportable-value, versioning and provider-delivery owners. Reuse the
  existing owner that implements those chosen rules and delete equivalent
  duplicates. Do not assume strict structural transport wins or introduce a
  compatibility wrapper before proving an old caller needs one; preserve any
  required conversion at the existing boundary. No additional validator is proposed.
- [x] Test actual command/provider publication and failures before commit.
  Keep schema validation distinct from artifact freshness/lineage checks.
  Preserve historical committed results and replay: do not rewrite or revalidate
  them using newly selected rules.

### Task 3 investigation evidence and selected D3 disposition

The source inspection and two bounded probes at `6005b5c1` distinguish the
existing profiles below. These are observed **before** behaviors; D3 requires
the same **after** behavior for selected consolidation cuts.

| Text / captured-byte case | Existing decoding behavior |
| --- | --- |
| Int/Float/Bool strings; recursive List strings | Leaf/bundle parsers coerce, including nested numeric strings; structural transport and pure coercion reject those strings as numeric/Bool operands. |
| Whole-root Value JSON string or null | Preserved as string/null; a JSON-looking string is not decoded again. |
| Flattened record numeric string and unknown extra | Declared pointer projects/coerces the field and drops the unknown extra; direct nested record validation rejects numeric strings and extra fields. |
| Missing record fields | Missing required pointer refuses; omitted flattened optional becomes None; direct record still requires the optional field key. |
| Flattened union | Known inactive fields refuse; unknown extra fields are projected away; active numeric strings coerce. |
| Float NaN/overflow JSON | Output default accepts Float nonfinite; `finite_floats=True` refuses. Value JSON has its own strict rejection. All evaluated command/provider publication callers request `True`. |

| Already-structured case | Output / structural transport | Pure coercion |
| --- | --- | --- |
| Bool supplied as Int | Refuse | Refuse |
| Int `2**63`; Int `1` supplied as Float | Accept; normalize Float to `1.0` | Refuse signed-64 overflow; refuse Int as Float |
| Tuple supplied as List | Refuse | Convert to list |
| Union known inactive field | Direct output/transport refuse | Drop known inactive field; unknown extra still refuses |
| Value tuple, non-string map key or key collision | Strict JSON domain refuses | `_jsonable` converts tuples and stringifies keys; `{1: a, "1": b}` collapses to one key |
| Value depth 65 / canonical size over 16 MiB | Transport refuses at depth 64 / 16,777,216 bytes; opaque output accepts tested cases | Accept tested cases; no corresponding transport budget |
| Value container cycle | Explicit output/transport refusal | Direct pure probe raises RecursionError; evaluated wrapper converts it to EvaluatedValueError |
| Absolute/traversing Path | Output rejects using workspace/path owner; transport without callback accepts tested strings | Lexical normalized-root refusal; no fresh disk checks |
| Basename Path under declared root | Output normalizes `x` to `artifacts/x`; callback-free transport keeps `x` | Refuse outside declared root; normalized `artifacts/x` passes |

Finite caller census: `contracts/output_contract.py::{validate_contract_value,
validate_expected_outputs,validate_output_bundle,validate_variant_output_bundle,
_parse_output_value,_parse_output_bundle_value,_validate_direct_transport_value,
_validate_relpath_value,_validate_relpath_value_by_path}` owns leaf/byte parsing
and workspace-file validation. `workflow/type_descriptor.py::{
validate_transport_value,_validate_primitive_value,_validate_json_value,
_validate_transport_path}` owns direct descriptor acceptance. Schema producers
are `workflow_lisp/contracts.py::{derive_structured_result_contract,
derive_prompt_guided_structured_result_contract,derive_workflow_signature_contracts,
derive_union_workflow_output_metadata}`. Public captured-byte consumers are
`workflow/evaluated/commands.py::_validate_result_bytes` and provider
publication in `workflow/evaluated/providers.py`; they request finite floats.
Other existing contract consumers are signatures, judgment views, supervision
contracts, adjudication promotion, result guidance and reusable phase-result
adapters; changing the default reaches these independently retained profiles.

Runtime results pass `evaluated/machine.py::_coerce_result` →
`evaluated/values.py::coerce_evaluated_value` →
`workflow/pure_expr.py::{coerce_pure_value,_coerce_value,_jsonable}`. Inputs,
calls, authority, sessions, run-ref, parallel and replay also use the evaluated
coercion owner. Crucially, `evaluated/replay.py::committed_value` already coerces
committed memo values. Changing pure acceptance can therefore invalidate old
history even without rewriting stored bytes; replay compatibility must be
proved before a broader shared-owner change.

Evidence: `PYTHONPATH=. python /tmp/orc_result_transport_probe.py` and
`PYTHONPATH=. python /tmp/orc_result_transport_bytes_probe.py`, both exit 0;
captured tables are the corresponding `.log` files. The narrow owner selection
in `/tmp/orc_result_transport_narrow.log` passed 27 tests in 12.97s. These local
probes cover named API inputs, not provider quality, every descriptor or public
lifecycle equivalence; the byte probe directly calls captured-byte validators.

The owner resolved D3: preserve compatibility and consolidate equivalent rules
now. The selected first cut delegates String/enum/Int/Bool/relpath leaf parsing
from `_parse_output_value` to the existing `_parse_output_bundle_value` for its
string-input domain, with behavioral and diagnostic equivalence checks. Float
keeps its existing path because diagnostic `value_path` differs; it is excluded
from this cut. Broader consolidation requires separate proved-equivalent
slices. Existing targets/profiles retain numeric, JSON, path, optional and union
behavior; committed replay acceptance remains unchanged.

Uniform incompatible semantics at a new version remain a future proposal
requiring separate selection, design and migration; D3 does not silently replace
that possibility with a claim that all validators are unified. The useful
current goal is one documented acceptance contract per existing profile and
removal of equivalent duplication. The selected scalar consolidation has
completed its publication/replay/compatibility checks; non-equivalent validators
remain under their existing owners rather than being forced into one contract.

**Task 3 execution result:** `_parse_output_value` now delegates String, enum,
Int, Bool and relpath parsing to the existing bundle parser for its string-input
domain, deleting 29 net production lines. Both callers retain their existing
text normalization and error decoration. Float remains separate because its
leaf error context omits the bundle's `value_path`; no wrapper or additional
validator was introduced. The admitted scalar producers emit no conflicting
record/union item descriptor. `specs/io.md` now precisely distinguishes direct
structural Float validation from scalar and container-of-leaf parsing; its
independent design review passed. No target, numeric rule or replay acceptance
changed.

Both captured-byte and structured-value probes are byte-identical before and
after, saved as `/tmp/orc_result_transport_{probe,bytes_probe}.{before,after}.log`.
The independent compliance reviewer additionally compared 832 value/diagnostic
cases against HEAD, including whitespace, enum, numeric/Bool, finite flags,
workspace-file validation, symlinks and NUL paths. Compliance and quality
reviews approved the change. The coordinator inspected the diff, compared the
persisted probes and ran the final seven-module gate: **244 passed in 23.32s**,
exit 0. Command, output and exit are
`/tmp/orc-result-scalars-final-20261015.{sh,log,exit}`. The modules cover output
contracts, nested transport, Value, workflow output integration, evaluated
providers/resume and Float boundaries. No tests were changed, so no new
collection-only run was needed. This is the selected consolidation's evidence,
not full-suite health or a claim that the different acceptance profiles have
become interchangeable.

```bash
pytest -q tests/test_output_contract.py tests/test_output_contract_nested_transport.py
pytest -q tests/test_workflow_output_contract_integration.py
pytest -q tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_resume.py
```

**Exit:** both decoding and structured acceptance have one documented contract
at each selected target/profile, duplicate equivalent rules are removed, and
textual/already-structured publication and old/new boundary checks pass without
new failures. Historical committed results are not decoded or validated anew.
Any unproved equivalence stops the affected consolidation slice without
blocking Tasks 1 or 2a. D3 permits no acceptance-policy change to make a shared
implementation fit.

## Dynamic adoption authority

**Task 4 — Decision under the existing production-adoption/migration gate.**

The delegated owner decision is **retain typed W3 for the demonstrated fixed
improve/search consumers; stop this 3.0 adoption/migration lane**. This settles
the existing DC-P choice without merging a new evaluator or deleting the
qualified dynamic research branch. The user's willingness to trade static
checks/resume for demonstrated benefits remains valid; the available fixed
consumer evidence does not justify that trade here.

The candidate is `feat/orc-dynamic-core-cutover` at
`1ecde6e4566cf38a9d9f642e4e5c74e45d71b368`. A fresh upstream fetch reconfirmed
that pin and main `6005b5c1f105057a41a5a57882e5df90abf44118`, with no incoming
changes or competing target allocation. Reuse its
[proposal](https://github.com/hoidn/agent-orchestration/blob/1ecde6e4566cf38a9d9f642e4e5c74e45d71b368/docs/design/workflow_lisp_dynamic_core_proposal.md),
[readiness plan](https://github.com/hoidn/agent-orchestration/blob/1ecde6e4566cf38a9d9f642e4e5c74e45d71b368/docs/plans/2026-10-02-workflow-lisp-dynamic-core-readiness-plan.md),
[DC-3 / DC-P authority](https://github.com/hoidn/agent-orchestration/blob/1ecde6e4566cf38a9d9f642e4e5c74e45d71b368/docs/plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#dc-3-production-readiness-and-gate-dc-p)
and [implemented-W3 evidence](https://github.com/hoidn/agent-orchestration/blob/1ecde6e4566cf38a9d9f642e4e5c74e45d71b368/docs/reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#implemented-w3-reevaluation--2026-10-12).

- [x] Preserve the native ordinary function-value composition benefit and typed
  W3 parity for the demonstrated fixed consumers.
- [x] Base this bounded decision on the packet's zero removable production
  owners, weaker early diagnostics and fresh-restart repeated work (eight
  successful calls versus six after the real interruption comparison).
- [x] Preserve RW-I10 zero-limit and RW-S05 Boolean-transport differences as
  findings. D3 explicitly preserves current compatibility; this decision does
  not fix them by changing main transport semantics.
- [x] Close this adoption choice without a new study or paid-provider call.
  Provider quality, human productivity and broader production performance
  remain unassessed. A future different consumer requires its own evidence.

No `run-search` 2.35→3.0 migration is selected. The selected 2.39 typed authoring
migration below is different and preserves the ordinary evaluated runtime.
Main Phase 6b/Phase 5/Phase 7 keep their own exits. No historical branch report,
frozen source, retained run or prior result is rewritten, and no dynamic
production owner is claimed retired by this decision.

**Exit:** the bounded DC-P retain/stop decision is recorded above; this is not a
main delivery-phase closeout or rejection of dynamic-language research.

## Task 5 — Complete the other bounded simplifications

These recommendations retain concrete deliverables. The delegated completion
decision selects the target-2.39 remainder below; accepted contracts and an
independently reviewed design still precede its code. Completed cuts and all
other retained compatibility/qualification gates remain unchanged.

- [x] **EL-1:** implement the selected 2.39 EL-1a/b/c contract and finite
  [implementation sequence](#target-239-selected-implementation). Infer effects
  by default, check optional restrictions after specialization, expose inferred
  facts through existing inspection, and qualify two maintained consumers.
  Preserve old definition origins and the completed ES hand-back. Shared
  compiler owners are edited sequentially; no further WCC prerequisite is added.
- [x] **Specialize the executable elaborator:** complete for the selected
  bounded command-preparation, dead inference-forwarding and WCC body cuts
  below. The existing executable entry is specific to one mode; historical
  body/convenience callers have explicit dispositions. F also removes
  `CompilerSession.closed_program`, the old source-compilation branches and
  `wcc/route.py`; retained artifact route/schema fields are data. Shared source
  typing, current target selection and the typing/preparation stages of
  condition normalization retain their real consumers.

  **Completed command-family cut:**
  [middle-end §13.4](../design/workflow_lisp_core_calculus_middle_end.md#134-executable-only-command-preparation)
  owns the executable-only contract. Removed `ControlFacts.closed_program`,
  its false binding/private-output/procedure branches, the specialized-loop
  `closed_context` fallback and the builder's redundant scan flag. Real typed
  owners replace direct-test mode selection; unknown-operation rejection,
  callee-local types and original imported catalogs remain checked.

  **Completed dead type-inference forwarding cut:**
  [middle-end §13.4.1](../design/workflow_lisp_core_calculus_middle_end.md#1341-mode-independent-type-fact-inference)
  owns the mode-independent helper pair. Removed two formals and **64 production
  keyword arguments** (63 in `wcc/elaborate.py`, one in the command owner).
  The command-capture test retains its capture-origin/shadow assertion without
  the deleted keyword. No source policy, runtime policy, target, default or
  shared typechecker semantics changed; `result_guidance._infer_expr_type`
  remains outside the cut.

  **Combined acceptance:** independent compliance and quality reviews passed.
  The narrow population passed **393 tests** in 4.28s. The combined broader
  population passed **2,478 tests** in 174.98s, exit 0, using
  `pytest -q -n 16 --dist=worksteal` in tmux. Commands, log/exit hashes and
  the accepted package freeze are in
  `/tmp/orc-command-mode-20261015/broad-receipt.json`,
  `broad-verify-20261015.sh`, `broad.log`, `broad.exit` and `broad.sha256`.
  `final-freeze-manifest.json` records 444 package files;
  `owner-hash-manifest.json` records the seven changed owners. The coordinator
  checked the frozen source and evidence hashes. This verifies the command
  and inference cuts together with final Task 2 and the primitive cuts; parallel
  preparation retains its separately recorded 96-test evidence. This affected
  population is not a full-suite or whole-lane closeout.

  Final external probes preserve **44 complete artifact pairs**, 23 actual
  prepared-request instantiations, three old-header conditional artifacts and
  nine complete timelines. All six RunRef controlled artifacts remain exact;
  the six authentic artifacts retain 30 package-pin mismatches only, without
  normalization or a cross-package resume claim. The public diagnostic probe
  preserves all **14 ordered records**, including source/provenance, phase,
  code, data and precedence. Per-probe receipts live under
  `/tmp/orc-wcc-probe-adaptations-20261015/receipts/commandmode-final-*`,
  `/tmp/orc-command-mode-20261015/artifact-pairs-report.json` and
  `/tmp/orc-wcc-mode-diagnostics-20261015/commandmode-final-diagnostics-comparison.json`.
  Deleted hooks marked unavailable are not dynamic zero-call evidence.

  The read-only diagnostic baseline includes both provider-group families,
  direct/inline and auto/private members, nested/specialized captures and
  competing errors. It preserves three pre-existing compiler-defect cases;
  none is a desired diagnostic or silently repaired by these cuts. A separate
  process-local blanket closure-bypass experiment on six invalid-member cases
  replaced their member-specific diagnostic pairs with compiler defects
  (`/tmp/orc-wcc-mode-diagnostics-20261015/closure-bypass-results.json`). This
  rejects that blanket bypass, not all possible compatible body-specialization
  approaches. No repository change or live provider call was made by the
  diagnostic/bypass probes.

  The compatible continuation retains provider-member closure and validation
  while making `_inline_provider_procedure_call` recurse in closed mode. A
  separate process-local experiment changed only that recursive call in the
  frozen v2 package and preserved all 14 original cases' complete ordered
  diagnostics, status, stage and source identity. Instrumentation observed
  eight actual recursive calls in closed mode. Eight further cases extracted
  from frozen provider-supervision tests also matched exactly: effectful
  `if`, `match` and loop, pure and nested pure `if`, unresolved conditional
  capture, and direct/aliased WorkflowRef boundaries. This is finite
  feasibility evidence, not full specialization acceptance. Sources and
  baselines remain unchanged; no product edit or live call occurred.
  `/tmp/orc-wcc-mode-diagnostics-20261015/provider-recursion-closed-design-receipt.json`
  records the patch, limits and evidence hashes; the exact comparisons are
  `provider-recursion-closed-comparison.json` and
  `provider-recursion-control-comparison.json` in that directory.

  **Completed single-mode WCC body cut:**
  [middle-end §13.4.2](../design/workflow_lisp_core_calculus_middle_end.md#1342-wcc-body-specialization-and-historical-consumer-boundary)
  owns the implemented preparation boundary. The existing body entry,
  call-type preparation and `WccIdentityFactory` no longer carry the mode.
  Their production callers use one entry; the convenience function/export and
  displaced false branches are removed without a wrapper or second pass.
  Shared typechecking/admission and both source condition-normalization paths
  retain their semantic consumers. No source syntax, target, runtime policy,
  artifact schema or effect admission changes.

  | Consumer/family | Implemented disposition |
  | --- | --- |
  | Builder, both command passes, specialized-loop scan and provider-member recursion | Use the existing executable body entry without a mode argument; preserve defining/imported owners, captures, cardinality and both command passes. |
  | Convenience function and `wcc/__init__.py` export | Removed after repository caller migration; no compatibility alias or historical body door. |
  | WCC/control/provenance and old-header import tests | Retained semantic assertions through executable preparation and independent model/scope checks; no fixture-header upgrade to avoid a failure. |
  | Flag-off phase atom and flat-only effectful-loop assertions | Two obsolete representation/limitation assertions retired individually; current phase/loop ordering and typed imports retained. |
  | Provider-region closure and diagnostics | Closure/validation preserved, including recursive executable preparation, eligibility, capture substitutions and ordered refusals. Neither group kind becomes executable. |
  | Opaque resource transitions and reverse substitution | `WccOpaqueFrontendValue` and `wcc/historical.py` retain the resource-transition refusal path. The obsolete WCC condition-classification producer is gone. |

  The authoritative incremental diff and frozen owners are
  `/tmp/orc-wcc-single-mode-impl-1792120860143253536/incremental-authoritative.patch`,
  `final-freeze-authoritative-manifest.json` and
  `owner-hash-authoritative-manifest.json`. The affected broader run passed
  **2,928 tests** in 182.46s, exit 0, with `-n 16 --dist=worksteal` in tmux
  (`broad.log`, `broad.exit`). The changed modules collected **479 tests**
  before the public-coverage supplement (`collect-all-changed.log`). This
  affected result is not a full-suite or whole-Task-5 closeout.

  The external acceptance receipt
  `/tmp/orc-wcc-single-mode-probes-20261015/final-acceptance-receipt.json`
  records 44 exact artifact pairs, 23 actual capture-request instantiations,
  three exact old-header conditional artifacts and nine complete timelines.
  All six physically controlled RunRef artifacts match; the six authentic
  artifacts retain only 30 package-pin differences. No pins or authored
  locations are normalized, and no cross-package resume compatibility is
  established. Unavailable deleted instrumentation hooks remain unavailable,
  rather than dynamic zero-call evidence. The receipt's original package freeze
  and the authoritative manifest retain the same production bytes.

  `final-diagnostic-receipt.json` in the implementation directory records all
  **22** baseline public outcomes and complete ordered authored diagnostics
  with equal cause type/messages. Raw tracebacks remain archived; changed
  physical package paths, source lines and formatting are explicitly outside
  that equality claim. No live provider calls occurred. The known computed-list
  capture defect and pre-existing diagnostic defects are preserved.

  Both independent code reviews passed and the coordinator accepted the cut.
  Eight supplemental checked public cases cover auto/private member refusals
  and competing-member/sibling precedence for both group kinds, comparing
  complete ordered baseline records and stages in
  `tests/test_workflow_lisp_closed_program_effects.py`, using
  `tests/fixtures/workflow_lisp/closed_program/provider_member_diagnostics.json`.
  The eight cases passed in 1.20s; the effects module collected 40 tests and
  all 16 changed modules collected **519 tests**. The test-only overlay is
  `test-overlay-1-manifest.json`, with collection in
  `collect-all-changed-with-overlay.log` in the implementation directory.
  It seals the two test files and unchanged 444-file production package, so
  the passing 2,928-test production run and exact artifact probes are reused.
  This closes the selected bounded executable-specialization lane. Further
  authored-lowering/source-intrinsic work follows the separately selected 2.39
  design, version and migration gates below. This WCC completion itself adds
  no public capability, automated manifest row or workflow run.
- [x] **Remove authored compiler-strategy lowering:** target-2.39 definitions
  reject `:lowering` and always compose inline into the caller. An intentional
  runtime boundary uses existing `defworkflow`/`call`; unexported workflows
  restrict imports, not local entry selection. Retain old-origin AUTO/private
  behavior, provider closure checks, command preparation and checkpoint identity.
  Migrate the finite consumers and verify boundaries/recovery as specified below;
  do not promise old private-procedure fingerprint or resume after migration.
- [x] **Fixed primitive catalog and equivalent descriptor rules (selected cuts):** consolidate duplicated rules for operators
  without shared signatures (Boolean/string/option/list operations, including
  `_LIST_OPERATOR_NAMES`) in
  `orchestrator/workflow/pure_expr.py` and its
  `orchestrator/workflow_lisp/typecheck_pure_ops.py` consumer. Retain finite
  built-in registration, target admission and independent checker rules;
  delete replaced tables/branches and verify type/evaluation/refusal agreement
  with `tests/test_workflow_pure_catalog_agreement.py` and
  `tests/test_workflow_pure_expr.py`. Keep expected valid/invalid operands and
  results independent of the catalog under test; exercise those vectors through
  source compilation, direct artifact/payload validation and runtime evaluation.
  Agreement between consumers of one incorrect table is insufficient. Preserve
  source-specific diagnostics, the typed-Path concatenation prohibition and
  lazy short-circuit evaluation. No plugin registry is needed.
  Completed first slice: `and`/`or`/`not`, `string/empty?` and `symbol/name`
  now use the existing `PureOperatorSpec` signatures/evaluation, with displaced
  source/payload/runtime and inference fallback branches removed. Existing
  primitive rejection preserves the original first-invalid-operand metadata
  used by durable pure-fault fingerprints. The changed catalog module collects
  220 tests and passes all 220; the affected suite passed 522 tests in 15.19
  seconds (exit 0). Separate checks cover public lazy run/resume (15), saved
  pure faults (4) and source-free loading (2); these overlapping selections
  are not additive. Two full canonical artifact pairs, covering all five
  operations and short-circuit faults, are byte-identical and evaluate to
  independently specified results after source removal. Evidence:
  `/tmp/orc-primitives-broad.{log,exit}` and
  `/tmp/orc-primitives-artifact-pair-manifest.json`; both independent reviews
  and coordinator inspection passed. Leave concat, optional and list
  dependent-type rules for separate cuts; do not assign them false fixed
  primitive signatures merely to fit the catalog.
  The completed second cut uses the existing catalog's `group="list"`
  instead of `_LIST_OPERATOR_NAMES` and the frontend's repeated name set.
  In `pure_expr.py`, reuse `_derive_static_operator_type` for the equivalent
  concat/optional/list descriptor judgments in `evaluate_pure_operator`,
  retaining value coercion, error order/metadata, fresh-list construction and
  length overflow checks. Frontend dependent-type/transport checks and concat's
  source-specific Path diagnostic remain with their existing owner. This
  requires no new rule framework or public contract. Production scope is
  `pure_expr.py` and `typecheck_pure_ops.py`; independent descriptor/result
  vectors, before/after rejection evidence, list mutation controls and public
  list/optional composition checks establish compatibility. The command-mode
  combined verification above covers this cut with final Task 2. This cut
  removes duplicate equivalent judgments; it does not claim
  all frontend dependent rules have become catalog signatures.
  Its isolated package overlays only the two production owners and the catalog
  test on the approved pre-cut-6 snapshot. Collection passed (224 tests), narrow
  checks passed (428), and the 11-module affected suite passed 662 tests in 7.59
  seconds, exit 0. All 48 independent before/after descriptor/value cases are
  byte-identical. The complete list/optional/concat artifact is byte-identical
  (10,023 bytes); source-free evaluation in both packages returns the specified
  results for empty and nonempty inputs. Evidence and commands live in
  `/tmp/orc-primitives-second-evidence/`, with the exact three-file overlay in
  `/tmp/orc-primitives-second-overlay-manifest.json`. Both independent reviews
  and coordinator inspection passed. The later command-mode combined checks
  above also cover this cut with final Task 2; the isolated evidence retains
  its original scope.
- [x] **Parallel pure preparation:** trace `orchestrator/workflow/evaluated/parallel.py`
  and `orchestrator/workflow/evaluated/replay.py`; extract only their duplicated
  item/index/workspace/dependency preparation and bounds checks whose
  outputs and refusal timing can agree. Delete the replaced branches, test
  empty/max-sized/nested inputs, repeated-workspace refusal, partial commits,
  out-of-order completion and read-only replay. Preserve result order, error
  timing and committed recovery using `tests/test_workflow_evaluated_parallel.py`,
  `tests/test_workflow_evaluated_parallel_failures.py`,
  `tests/test_workflow_evaluated_parallel_resume.py` and affected replay owners.
  Live scheduling, filesystem freshness and dispatch remain owned by their
  respective callers. Workspace resolution/collision preflight remains live
  only; do not introduce disk checks into read-only replay. Acceptance needs
  actual deletion and unchanged public
  behavior, not just an extracted helper.
  The first candidate shares source/bounds checking and one-item lexical/
  workspace/dependency preparation, with final-result assembly only if equivalent.
  Live `_items` must still eagerly prepare all items and check filesystem
  collisions before dispatch. Replay must still prepare lazily per item inside
  its existing try/fault/frontier ordering, without filesystem checks. Sharing
  pure preparation must not move those caller-owned timing boundaries.
  Implemented in `_Machine._parallel_source` and `_parallel_item`, with the
  displaced rules removed from both callers. Result assembly remains with its
  callers because their diagnostic contexts differ. The production diff is
  +24/−20 lines across the three existing modules; the reduction is in duplicate
  rule ownership, not net lines. The public index regression in
  `test_workflow_evaluated_parallel_cwd_cli.py` passes with both the original
  runtime and this change: per-workspace append-only records prove index/cwd
  delivery and no redispatch after completed resume. The changed module collects
  7 tests; the affected suite passed 96 tests in 33.75 seconds (exit 0), after
  narrow baseline/after checks. Commands, hashes and isolated-baseline evidence:
  `/tmp/orc-task5-index-integration-evidence-20261015.log`; broad command/output:
  `/tmp/orc-task5-parallel-broad-20261015.{sh,log,exit}`. Both independent reviews
  and coordinator inspection passed. These checks do not close the main
  delivery plan's Phase 5 qualification gates.
- [x] **Effect metadata:** cancel EL-1d for this selection. `EffectSummary`
  still serves placement, cycles, lowering, inspection and path-admission
  serialization; no measured performance or concrete maintenance problem
  justifies a replacement. EL-1b removes authored ceremony over that owner.
- [x] **Retirement and source/intrinsics:** complete the finite 2.39 admission
  cut below: retire authored private heads and bare compatibility fallbacks
  from the new source regime, while retaining real stdlib expansions and
  admitted 2.35–2.38 import/editor semantics. Existing Gate R retired flat
  execution; F additionally removes pre-2.35 source/import/tooling support.
  Native prompt-resume scaffold verification, retained data readers,
  `phase-target`, typing/preparation stages and 2.35–2.38 lowering remain real
  consumers. Do not create a new port queue or delete their owners by file count.
- [x] **Confinement:** defer ordinary public-provider confinement. No selected
  consumer here needs that additional policy or qualification; process cleanup
  provides no confinement proof. Preserve the existing
  [child environment/qualification gate](2026-10-14-run-ref-expression-environments-plan.md),
  including refusal without host fallback. Public confined providers stay
  unqualified until that separate gate supplies evidence; no live allocation.
- [x] **Ordinary environment and unlimited execution policy:** retain the D2
  inherited ordinary default, authored timeouts and existing environment
  behavior. Defer an allowlist/unlimited-policy change because this work has no
  selected caller requirement or credential-compatibility evidence for it.
  This explicit disposition does not weaken owned-group cleanup or child policy.
- [x] **Architecture and test guidance:** refresh the completed
  [documentation cleanup](2026-10-15-current-documentation-cleanup-plan.md)
  before selecting remaining repairs to `docs/architecture_overview.md`,
  design routing and historical frontend sketches against current semantic owners.
  Repair remaining stale test guidance in `tests/README.md`; any source/test count
  states its revision, inclusion/exclusion method and limits. Historical sketches
  remain labelled history rather than a competing current pipeline.

<a id="source-floor-retirement-sequence"></a>

### F — Pre-2.35 source compatibility retirement

**Owner decision.** The user explicitly instructed “eliminate pre 2.35
compatibility support.” This supersedes earlier plan allowances for old typed
imports, REPL/LSP analysis and exclusive old-source modes. Preserve current
2.35–2.38 semantics and B's accepted 2.39 contract. This is a package support
cut, not a new language target; no 2.40 allocation, compatibility flag, test
shim, old-source emitter or legacy diagnostic compiler is selected.

**Ordering and ownership.** B finishes its core inference files first. F1
maintained-source/test migration precedes F2 floor enforcement; F3 deletes
exclusive compatibility and F4 verifies the reconciled population. F precedes
C/D finalization and E consumer migration. Read-only inventories and disjoint
test preparation can proceed during B; effects/import tests and the
`compiler.py`/`procedures.py`/`procedure_typecheck.py` owners stay with B until
handoff. Each F batch has one implementation owner, a distinct reviewer and
coordinator verification. The floor is not complete after header rejection.

| Population | Finite disposition |
| --- | --- |
| Packaged maintained libraries | Migrate exactly `orchestrator/workflow_lisp/stdlib_modules/std/{context,drain,phase,resource,improve}.orc` and `orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc` to 2.35. Preserve existing bodies/contracts and the two entry-selected improve variants; repair only behavior differences exposed by the current-target comparison. Do not assume changing six headers is sufficient. Keep declared effects/lowering under the 2.35 regime, not new 2.39 semantics. |
| Old workflow programs | The 20 pre-floor `.orc` files under `workflows/` have no authored ≥2.35 `.orc` importer in the bounded source census. Retain their original bytes as historical corpus, withdraw their live typed/import/readiness claims, and remove current compiler test dependence. This population is the 14 `workflows/library/lisp_frontend_design_delta/*.orc`, `design_plan_impl_implementation_phase.orc`, `tracked_design_phase.orc`, `tracked_plan_phase.orc`, `generic_run_watchdog/watchdog.orc`, and the two `workflows/experiments/qa_placement_effectiveness/*.orc`. Do not port Design Delta parents, watchdog or trials by changing their headers. Current reusable behavior is tested with explicit admitted-source fixtures; their historical executable sources remain frozen. |
| Old experiment sources | Preserve the 19 pre-floor `.orc` files under `experiments/` as historical/frozen comparison input. They comprise the 13 generic-union hidden fixture modules under `compare/tasks/cf1-generic-unions/hidden/tests/fixtures/workflow_lisp/generic_unions`, the `ea-loop-result-paths` and `pure-result-replay` frozen task fixtures, `mlevolve_pair/{search.orc,probes/malformed_result.orc,probes/missing_bundle.orc}`, and `orc_vs_single_call/task/bug_report/reviewed_change.orc`. Current `search_compact.orc` and the maintained reviewed-change workflow remain separate supported consumers. Historical compare/repetition scripts may read data but cannot make the current compiler execute old source. |
| Current tests using old headers | Preserve every semantic assertion still relevant to admitted compilation/runtime: create explicit 2.35 fixtures or edit maintained nonfrozen fixtures with named intent and before/after evidence. Retire only tests whose sole promise is pre-floor admission/behavior. Delete redundant old-target labels after mapping their semantic cases to retained nodes. No dynamic header rewrite, old-target acceptance monkeypatch, hidden reduced suite or compatibility parser in test helpers. |
| Historical bytes used as evidence | Keep reports, golden old artifacts, archived studies and run evidence byte-identical. Tests may read/hash them as data or assert clear refusal. If a current semantic test depends on frozen old source, make a narrowly scoped current-target fixture rather than modifying the evidence or silently executing it. |
| Historical detailed trial projection | Retire `workflow/trial/observability.py`, its sole caller and dedicated Markdown renderer in `observability/report.py`, the five detailed-projection tests in `test_workflow_trial_observability.py`, and their exclusive `_captured_trial_config` helper in `test_workflow_trial_ledger.py`. There is no admitted evaluated trial producer; the public CLI already reads raw state, and the dashboard loader never supplies the flat bundle required by this projector. Preserve trial-output suppression, public read-only state inspection, independent config/ledger/settlement validation and both frozen JSON captures. Add public state-only regression coverage for redaction, no scan/repair and unchanged bytes. Do not synthesize a 2.35 trial bundle to retain an unreachable compatibility path. The dashboard's generic state/debug reader remains; no dashboard redaction guarantee is inferred. |

**F1 — Migrate dependencies and tests before closing admission.** The six stdlib
files are the production change. Compare them from an immutable before package
against a separate 2.35 candidate copy. Existing owners are
`tests/test_workflow_lisp_{phase_stdlib,drain_stdlib,resource_stdlib,improve_stdlib,generic_stdlib_composition,w3_target}.py`,
`tests/test_workflow_evaluated_consumers.py` and
`tests/test_workflow_lisp_guide_programs.py`. Cover imported phase/drain macros,
resource type/declared refusal, ordinary improve at 2.35 and W3 at 2.36, selected
hooks and strict Boolean/closed typing. This migrates source contracts, not
excluded resource/view/context effects into execution. Run a public scripted
compile/run/resume consumer after migration.

The bounded design probe uses immutable
`/tmp/orc-remainder-baseline-20261015` and a separate six-file stdlib copy:
`/tmp/orc-sourcefloor-stdlib-design-j88htqpr/receipt-v2.json`. Ten import/typecheck
cases (context/phase/drain/resource/improve at 2.35 and 2.36) accept before and
after header migration. It does not prove macro execution, runtime behavior or
identity equivalence; those remain F1 acceptance above. The first probe had an
invalid ancestor source-root layout; its outputs remain preserved and v2 uses
separate sibling app/library roots. No baseline or product source was modified.

Test migration is a finite population, not a global replacement. Freeze a
file/hash and collected-node inventory before editing; the preliminary literal
census (about 1,274 occurrences in 619 `.py/.orc/.json` files) is only a search
bound, not a count of supported cases. Partition every affected node as:
retained unchanged, migrated with its new node(s), exclusively old-contract
retired, historical data-only, or known failure still represented. Shared
fixtures belong to one batch owner. Use these bounded ownership batches:

| Batch | Existing test/fixture owners | Required treatment |
| --- | --- | --- |
| F1a syntax/import/editor | `test_workflow_lisp_{reader,syntax,modules,macros,diagnostics,source_read_trace,target_234,target_evaluated_execution,lsp_*}.py` and their referenced module fixtures; REPL load/type/inspection tests | Retarget current language, provenance and diagnostic cases to 2.35; preserve 2.35–2.38 feature gates. Replace pre-floor feature-admission matrices with a compact entry/import/REPL/LSP refusal matrix. Do not erase current diagnostic cases because their old header now refuses earlier. |
| F1b typed semantics | `test_workflow_lisp_{effects,imported_effects,procedures,functions,proc_refs,workflow_refs,generic_*,parametric_*,loop_*,strict_boolean_*,prompt_*,provider_*,structured_results,resource_stdlib,phase_stdlib,drain_stdlib,improve_stdlib}.py`, shared source helpers and their referenced fixtures | Preserve actual type/effect/capture/control/stdlib assertions at 2.35; migrate bodies deliberately where the new source regime exposes a substantive difference. B owns overlapping effect/import tests until handoff. Old-only version rejections disappear, not their current positive/negative semantic coverage. |
| F1c WCC/closed/runtime | `test_workflow_lisp_{wcc_*,closed_*,use_site_scope,elaborated_prefixes,hoisted_scope,prefix_scope,procedure_first_migrations,design_delta_smoke}.py`, `tests/workflow_lisp_closed_program_corpus.py`, affected evaluated/runtime owners | Delete `_analyze_and_select_evaluated_entry`'s historical-analysis phase and corpus `_replace_entry_target` promotion. Use explicit current source throughout. Retain each distinct scope/value/effect/lineage assertion and public runtime check. Historical corpus entries get data/refusal dispositions rather than synthetic promotion. |
| F1d manifests/readers/experiments | `test_workflow_lisp_{route_readiness,drain_roadmap_routing,build_artifacts,key_migrations}.py`, `tests/experiments/test_mlevolve_pair.py`, current artifact/report/native-resume readers, `docs/workflow_lisp_route_readiness_registry.json` and its CLI validator | Narrow current readiness to admitted source; preserve historical labels/evidence as nonexecuting data. Migrate current artifact-reader fixtures by artifact contract, not blanket target edits. Retire old execution/harness assertions and keep read-only evidence checks where a current consumer requires them. |

These filename families delimit the collected inventory, not permission to
rewrite all their tests mechanically. Record exact changed/retired node IDs
and replacement coverage in the execution receipt before accepting each batch.
For example, the use-site-scope failures reached the 2.35 runtime after old
analysis: collapse their historical header labels but keep every distinct
capture/evaluation-order shape and its failing/passing assertion at 2.35. A
pre-existing failure cannot be retired merely because its old test name had an
old version label.

**F2 — Enforce the floor at every public and internal import door.** Own
`orchestrator/contracts/closed_program/targets.py`,
`orchestrator/workflow/run_ref/config.py`,
`orchestrator/workflow_lisp/{syntax,modules,compiler,build}.py`,
`orchestrator/workflow_lisp/closed/{target,frontend}.py` and the existing bundle
admission boundary in `orchestrator/workflow/loaded_bundle.py` if needed.
Both target registries become 2.35–2.39; source and transitive imported headers
reject with `target_dsl_unsupported`. Keep public old-entry refusal precedence
(`workflow_execution_target_retired`) and no writes/locks. Before catalog
publication, validate an imported typed program or bundle's own target and
every represented module in `module_type_envs` and the transitive
`imported_programs` closure. A 2.35 outer target must not admit an embedded
pre-2.35 module through the Python API; reuse the existing graph and identity
checks without a new schema. The LSP compile driver and REPL use the same
frontend and invalidate stale old-target snapshots; no alternate analysis.
No payload/state conversion or new format is introduced.

**F3 — Remove the exclusive implementation.** Trace remaining calls after F2,
then delete the old branches and their argument/export plumbing in the same
slice. The finite owners are:

- `workflow_lisp/syntax.py` pre-floor feature gates and their branches in
  `expressions.py`, `macros.py`, `type_env.py`, `functions.py`, `result_guidance.py`,
  `typecheck_dispatch.py`, `typecheck_structural_values.py`, `typecheck_proofs.py`,
  prompt owners and `compiler.py`. Numeric/union/import/effect behavior already
  selected at 2.35 becomes the sole admitted source behavior. Preserve targetless
  shared utilities where they have a real non-source consumer; they are not a
  door admitting an old module. Retain real 2.36/2.37/2.38/2.39 distinctions.
- `workflow_lisp/compiler_session.py::CompilerSession.closed_program`, its
  compiler/typecheck/`procedure_specialization.py` false-source branches and
  forwarding arguments once all direct typed entrypoints are current-target.
  Preserve the current closed behavior and its diagnostic/placement checks.
  `conditionals.py` typing-time normalization versus later
  `prepare_closed_condition_expr` remains a real stage distinction; do not
  merge their behavior merely because the source floor moved.
- `workflow_lisp/wcc/route.py`, `workflow_lisp/{compiler,build,__init__}.py`,
  `wcc/__init__.py`, `orchestrator/lsp/{state,compile_driver}.py`: remove
  source-selectable LEGACY/WCC_M1/M2/M3 routes and exclusive old-route
  classification/emission. Delete obsolete selector arguments/exports when no
  current caller remains. Current artifact wire fields, if needed by a named
  2.35+ reader, are validated constants/data rather than a route dispatcher.
  `route_readiness.py` may read historical rows but cannot reactivate a route.
- Preserve `wcc/historical.py` or relocate its live provider closure helpers
  under their existing owner only if useful: its name does not make the
  provider-member diagnostics dead. Current provider-group closure, command
  preparation, private-workflow behavior for 2.35–2.38 and D3 scalar/transport
  distinctions remain. Remove only the paths made exclusive and unreachable
  by the source cutoff; record every retained branch's concrete current caller.

No second elaborator, reader compatibility engine, permanent route alias or
new target-policy registry replaces these deletions. The baseline §13.4
single-mode invariants and the frozen 22 provider diagnostic controls remain;
source-floor fixtures migrate the semantic cases without rewriting that evidence.

**F4 — Acceptance and failure accounting.** Collect every changed/added test
module and preserve the full-suite population correspondence. Run narrow source
entry/direct/transitive import/bundle/REPL/LSP refusals for 2.14/2.34 plus admitted
2.35–2.39 controls, migrated library tests and current provider/command/condition
consumers; then affected suites and full pytest in tmux with
`pytest -q -n 16 --dist=worksteal`. Compare against the accepted frozen baseline:
25 candidate failures: 20 also fail at clean HEAD; two full-run-only failures
(provider-isolation revalidation and overlap timeout) pass their focused checks;
three reproducible prior-cut regressions are now fixed and independently
compliance/quality reviewed. The three-file accepted overlay passed 261 tests
in 13.54 seconds, with coordinator owner-hash verification:
`/tmp/orc-baseline-regression-fix-20261015/receipt.json`. The repairs cover helper
ownership inventory and two corpus precedence cases; the final guard traverses
the complete callsite graph and preserves the third runtime-view precedence.
The receipt records the narrowly changed internal cause for an explicitly
unsupported capture. F4 must still track the 20 semantic failures and two
load-sensitive cases, rather than assuming that focused success makes the full
population green. Fix new regressions in their owners; do not convert failures
to intentional retirements or weaken expected values/diagnostics. Report before/after counts, each removed/replaced node and
known-failure mapping, so fewer collected tests cannot masquerade as success.

For unchanged source/target cases, preserve exact artifacts/identity and
ordered diagnostics. Migrated library bytes may intentionally change source
and program identity; compare values, shapes, operations, lineage and fresh
same-source resume, not fabricated identity equivalence. Never normalize a
`compiler_runtime_identity_digest` to claim an authentic RunRef match. Keep
physical-fixture controls and no paid-provider allocation. Frozen sources,
results and reports remain byte-identical; no cross-package resume claim.

**Exit:** maintained current sources and tests are migrated, all pre-floor
source/import/tooling doors refuse, exclusive implementation/selectors/shims
are deleted, retained readers have actual current consumers, and full
before/after population/failure accounting and independent reviews pass.
Only then is the floor complete; marking a header unsupported is insufficient.

**Integration checkpoint — F4 verified; C/D/E released.** F2's admission boundary and F3's
exclusive-code retirement are integrated. Independent code review approved the
final F3 v3 correction: 53 production owners, 2,481 net lines removed, all 52
remaining changed Python files compiling with Python 3.11. Twenty-five complete
artifacts for unchanged sources at 2.35–2.39 match exactly, including their
digests; no identity field was normalized. The coordinator's fresh integrated
source-floor and REPL checks passed 38 cases at that checkpoint. The F4
campaign and disposition below now complete the floor's integration gate.

Review caught and repaired the context-free REPL literal regression and removed
the remaining always-enabled macro flags and unused arguments. Explicit
structural policies used by current low-level constructors remain; source-floor
retirement does not erase those transport contracts. The frozen production
manifest is `/tmp/orc-f3-retirement-results-20261015/product-v3-manifest.json`
(SHA-256 `dea0846ba8d5a90dc47b3d0706d1d2bb5cee21b5e462f9575cd725410ab5dc2f`).

Test migration also removes variable-driven header promotion in the recovery
and effect-gap helpers. Explicit admitted fixtures preserve all four recovery
source hashes, 420 recovery case records and seven installed consumer snapshots;
586 test node IDs remain represented. Twelve focused public recovery, artifact,
invalidation and effect-gap checks pass. The fifth migration receipt is
`/tmp/orc-f1d-fifth-results-20261015/receipt.json`. Frozen historical inputs stay
unchanged.

**F4 campaign, 2026-10-16.** After correcting the migrated callers/fixtures,
collect-only passed 6,273 cases in changed modules. Full pytest with the recorded
16-worker command produced **15,832 passed, 70 failed, 114 skipped, 2 xfailed**
in 960.32 seconds; all 1,869 hashed product/test files stayed unchanged.
The suite is red. Its 68 previously evidenced failures recur; the delayed-marker
timeout is additionally reproduced in the immutable baseline and current tree.
The remaining `unquiescent-recovery` failure belongs to the unchanged independent
native-session experiment harness: its five local code/test owners are identical
to baseline, and invocation 5 ended before the test's injected failure at 6.
Repeated before/current checks pass, but the original quiescence cause was not
captured; this is an unresolved harness finding, not a proven baseline failure.
It remains visible and does not select a repair to that independent harness or
block integration of C/D/E. No assertion, timeout or exclusion was changed.

The nested subprocess failure has matching inner stderr before/current: it
imports the separately installed `omp-i1-prerequisites` checkout, which rejects
2.35. A supplemental invocation with this worktree explicitly on `PYTHONPATH`
passes; the global installation and the full-run failure record remain intact.
Four other failures require the external nanoBragg checkout. These environment
prerequisites are distinct from retained compiler/LSP defects.

The population reconciles exactly:
`16276 - 821 replaced - 126 retired + 603 replacements + 86 additions = 16018`.
All 947 absent baseline nodes have a disposition, with no unresolved references.
The five trial-detail retirements remove an unreachable responsibility; six new
public state-only cases retain redaction/no-read/no-write coverage. All 39 frozen
historical workflow/experiment sources remain byte-identical. The coordinator
verified all 72 changed production Python files with Python 3.11.13.

Evidence: `/tmp/orc-source-floor-integration-results-20261015/full-final-f.{xml,log}`
and its receipt; `/tmp/orc-f4-population-accounting-final-f-20261016/summary.json`;
`/tmp/orc-f4-expected-failure-ledger-20261016/`; the additional native-harness
receipt `/tmp/orc-f4-native-new-failures-20261016/receipt.json`; and
`/tmp/orc-f4-nested-cause-20261016/receipt.json`. Independent review checked the
population/cause accounting and the finite trial retirement. The subsequent
joint C/D/E campaign must still identify any changed cause or new regression;
these counts are not a blanket allowance for later failures.

### Final integration evidence — 2026-10-16

**The selected engineering scope is complete; the captured full suite is red.**
Reviewed C/D/E code, the two maintained consumer migrations, the 24-file durable
documentation patch
and two-plan routing patch are integrated. Final discovery corrections also
align the architecture overview, lifecycle target table and REPL design-index
row with admitted 2.35–2.39 source/runs and 2.39 authoring on the same runtime;
these add no contract or qualification claim. The source floor's completed F4
campaign above remains an earlier snapshot; its 70 failures are not a blanket
allowance for this later campaign.

| Captured check | Result |
| --- | --- |
| Narrow 2.39 integration selectors | 117 passed in 10.29s; exit 0 |
| Affected C/D/E owners | 546 passed, 1 failed in 74.91s; exit 1. The failure is the known `growth_selector_event_lane` case with the same cause/message. |
| Changed-module collection | 6,338 collected in 10.24s; exit 0. This is a selected-module count, not the full test population. |
| Full `pytest -q -n 16 --dist=worksteal` in tmux | **15,874 passed, 71 failed, 114 skipped, 2 xfailed** in 790.25s; exit 1. The actual complete XML population is **16,061 unique nodes**. |
| Campaign source integrity | All 1,879 hashed product/test files are unchanged across each captured command. No full-suite source drift. |

Compared with F-final's actual 16,018 nodes, C/D/E removes three parameter labels
and adds 46: the three E target-bearing ID replacements plus 12 C and 31 D cases.
The changed-module collection increase of 65 includes 22 pre-existing command-
template cases newly selected; it is not 65 new full-suite tests.

The original complete population reconciles exactly:
`16276 - 824 replaced - 126 retired + 606 replacements + 129 independent additions = 16061`.
All **950** absent baseline nodes have recorded replacement/retirement lineage;
there are no unresolved nodes or replacement references. Every F70 failed node
is still present, including those that now pass. No smaller population is used
to make the red campaign appear successful.

The F70 → final71 failure comparison has **69 shared failures**, one now-passing
node and two newly observed failures. The shared failure mechanisms match the
preceding F campaign after specific temporary-path, address and timer-text
normalization; target numbers are not normalized. All 68 previously evidenced
failures recur; the additional shared `delayed-marker-hang` timeout was reproduced in the
immutable baseline. `unquiescent-recovery` passes in this campaign, but its
uncaptured intermittent quiescence history remains unresolved and is not
relabelled a proven baseline cause or repaired harness.

The two newly observed failures have separate dispositions; the 71-failure
snapshot is preserved rather than reclassified wholesale as known failures:

- `test_corpus_materializes_declared_workspace_launcher_without_changing_closure`
  had a stale expected target 2.36 for the maintained proposal migrated to 2.39.
  The one-line test-only correction passes its focused checks and complete owner
  module; independent Sol review approved the correction.
- `test_execute_enrolls_and_releases_before_status_wait` failed pinned invocation
  authority revalidation. The exact uninstrumented test passes 3/3 times in the
  immutable baseline and 3/3 in the current tree; the compared owners are
  identical. A controlled create/unlink of only the task's own `/tmp` file
  between `lstat` and `fstat`, only during pinned revalidation, produces the same
  full outer exception and `$.run_root.components[0].identity` inner failure in
  both trees. Only `mtime_ns`/`ctime_ns` change. This demonstrates a pre-existing
  shared-ancestor timestamp-race mechanism; it does not reproduce a natural
  baseline full-load failure or identify the original concurrent writer. No
  production, security check, fixture or test is changed for this disposition.

**Post-full corpus correction evidence:** the expectation alone changes
2.36 → 2.39; all 469 product/config hashes and the test-node population remain
unchanged. The narrow checks pass 2 cases in 1.77s, collection finds 109 cases,
and the complete owner module passes 109 in 7.60s under the tmux/16-worker
command. Exact diff, AST-only-change check, logs and hashes are in
`/tmp/orc-final-corpus-correction-20261016/`. Independent Sol review approved it.
These results follow the frozen 71-failure snapshot; they do not imply a full
rerun or a green full-suite result. The final coordinator snapshot check over
all 1,879 full-campaign source/test hashes finds this assertion as the sole
post-full change, with no production drift; all 39 historical sources and the
original review hash match. The isolation receipt, exact repeated commands,
controlled JSON/tracebacks and owner-hash manifest are in
`/tmp/orc-239-isolation-failure-20261016/`. The coordinator inspected both
controlled outputs and verified the same causal chain and timestamp-only
change. No natural baseline full-load reproduction or global green result is
claimed. The shared-ancestor race and unresolved native-harness history remain
explicit residual defects rather than new repair work selected by this plan.

Retained compiler/navigation defects and evaluated LSP **F2 OPEN_NOT_WAIVED**
remain visible. Native experiment-harness findings, the separately installed
`omp-i1-prerequisites` subprocess issue and the external nanoBragg prerequisites
retain their earlier dispositions; none supplies permission to weaken assertions,
hide tests or claim universal correctness. Ordinary public-provider confinement
remains deferred and its independent child qualification gate is unchanged.

Exact commands, receipts, hashes, JUnit and integration owner manifests are in
`/tmp/orc-239-final-integration-20261016/`; node lineage, actual population deltas
and the exact failure-ID comparison are in
`/tmp/orc-239-final-population-accounting-20261016/`, including `summary.json` and
`F70-to-final71-failure-comparison.json`. Shared cause verification is
`/tmp/orc-239-final-integration-20261016/shared-failure-cause-comparison.json`;
post-full source inspection is `final-inspection.json` in the same directory.
The frozen review report and 39 historical workflow/experiment sources remain
unchanged. Independent slice, documentation,
plan and corpus-correction reviews plus coordinator inspection complete this
selected engineering scope with the residual limits above. No main phase, broad
dynamic-language research gate or paid-provider allocation is closed or selected.

### Target-2.39 selected implementation

**Selection and tradeoff.** The user delegated the remaining decisions; target
2.39 is the next unallocated target at the freshly fetched pins above. Select
EL-1a/b/c, removal of authored strategy on new definitions, and finite source
admission narrowing. This removes mandatory effect mirrors and a compiler-choice
knob from new source. Retaining admitted old definitions requires their existing
versioned semantics; it does not justify duplicate new analysis/runtime paths.
An explicit workflow boundary requires concrete transportable arguments and
creates a new identity when replacing an old private procedure. It cannot hide
a local entry or transport compile-time hooks.

The governing contracts are the
[effect-ledger design](../design/workflow_lisp_effect_ledger_simplification.md),
[frontend §6 / §8.8 / §106](../design/workflow_lisp_frontend_specification.md),
[effect graph](../design/workflow_lisp_effect_graph.md),
[middle-end](../design/workflow_lisp_core_calculus_middle_end.md),
[REPL](../design/workflow_lisp_repl.md),
[LSP](../design/workflow_lisp_language_server.md), and
[versioning](../../specs/versioning.md). Independent review of the contract and
bounded slice precedes its code. A scoped B approval can release B while C/D
review continues; do not advertise target-2.39 support until its selected source
rules and public acceptance are complete.

**DAG:** A (contract/plan review) → B (EL-1 authoring/inspection) → F (source-floor
migration/admission/exclusive deletion) → C (lowering) → D (private-form source
admission) → E (consumer migration and EL-1c). Code owners shared
between B/F/C/D are serialized and each stage hands its reviewed diff and fresh
checks to the next. Read-only review/fixture preparation may run alongside the
author. F2 may prepare an isolated candidate while F1 migrates its consumers;
integrating floor enforcement still follows the migration and its population
accounting. No new workflow manifest or research allocation is created.

| Slice | Exact production/consumer owners | Required change and deletion |
| --- | --- | --- |
| B — EL-1a/b | `orchestrator/contracts/closed_program/targets.py`; `orchestrator/workflow/run_ref/config.py`; `orchestrator/workflow_lisp/{syntax,procedures,compiler,effects,procedure_typecheck,specialization_typecheck,procedure_specialization,functions,repl_expr,repl_inspect}.py`; `orchestrator/lsp/navigation.py` | Add 2.39 during B; F then raises both existing target ranges to the selected 2.35 floor. Carry optional declaration and compiler-only definition origin through current copies. Resolve named workflow/provider subjects with existing catalogs and formal WorkflowRef bindings; command adapter labels keep their domain. Check ceilings at the settled inference boundary, including materializations returned by final workflow typing. Replace new-origin specialization/generated-name exemptions with actual restriction checks. Preserve old-origin checks/exemptions. Use inferred/incomplete facts for pure-function and run-ref/trial placement and existing REPL/LSP projections; remove declaration-as-inference assumptions. No new atom, persisted origin, analysis graph or request API. |
| C — authored lowering | `orchestrator/workflow_lisp/{procedures,procedure_typecheck,procedure_specialization,compiler}.py`; `orchestrator/workflow_lisp/closed/{command_templates,build}.py`, `orchestrator/workflow_lisp/wcc/elaborate.py` only if their existing resolved-policy consumers need adjustment | Reject new-origin authored lowering; select internal INLINE before legacy AUTO/private analysis. All temporary/final new-origin let-proc helpers omit synthetic ceilings/strategy. Preserve old-origin strategy/identity and provider closure validation; do not copy or replace those owners. New explicit boundary uses ordinary workflow/call. |
| D — finite source admission | `orchestrator/workflow_lisp/{expressions,form_registry}.py`; existing `syntax.py`/`macros.py` provenance is reused, not replaced; `orchestrator/lsp/navigation.py` only for the existing form projection | At post-expansion elaboration, remove new-target bare `with-phase`/`finalize-selected-item` fallback. Admit private wrapper/seed only when the head's introducing frame belongs to the actual packaged phase/drain template defined by §6. Hide private/fallback forms from new-target completion. Preserve admitted 2.35–2.38 source and actual builtin expansion, `phase-target` and other live intrinsic owners. |
| E — EL-1c and maintained migrations | `experiments/mlevolve_pair/search_compact.orc`; `workflows/examples/improve_experiment_proposal.orc`; `docs/lisp_workflow_drafting_guide.md`; relevant current discovery/version status rows | Retarget these two maintained consumers to 2.39, remove lowering, omit `branch-step`'s mirrored command ledger, retain `propose`'s intentional empty restriction and `execute`'s intentional launch-command ceiling. Imported `std/improve` definitions retain their 2.35 migrated contract and semantics. Preserve exact command configuration, policy, schemas and returned values. Publish new copy-safe examples only after acceptance. |

B starts with current parser/definition/signature and final validation owners;
intermediate `validate_declared=False` stays. `ProcedureDef` origin is compiler
metadata omitted from semantic identity/JSON; existing `dataclasses.replace`
specialization and qualification preserve it. A macro-emitted definition uses
the receiving module target, while an imported definition keeps its own.
F separately migrates the six maintained stdlib modules to 2.35; they do not
adopt 2.39 ceilings/lowering. An optional metadata rewrite and a new module
identity registry remain outside these slices.

**First B acceptance (release of the next implementation slice).** Add bounded
cases to `tests/test_workflow_lisp_effects.py`,
`tests/test_workflow_lisp_imported_effects.py` (create this focused owner if absent),
`tests/test_workflow_lisp_workflow_refs.py`,
`tests/test_workflow_lisp_repl_type_query.py` and the existing LSP navigation
owner `tests/test_workflow_lisp_lsp_e2e.py`; use existing specialization/ProcRef
fixtures rather than a new harness. The matrix must cover:

- omitted effectful wrapper; explicit-empty pure success/effectful failure;
  named strict subset success and uncovered/unknown/wrong-kind refusal;
- a defining-scope workflow alias, canonical transitive workflow, caller
  shadowing, unused provider symbol, and an adapter label different from its
  boundary binding name;
- pure/effectful ProcRef selection, formal WorkflowRef substitution, nested
  generated helper and a specialization materialized by final workflow typing;
  unresolved hooks are visibly incomplete, not empty;
- 2.39→2.35–2.38 import preserving exact/empty/exemption behavior; reverse refusal,
  including 2.37/2.38; macro-generated receiving origin and pre-floor refusal controls;
- REPL definition/selected-call inspection and LSP completion distinguish
  restriction from inference; absent clauses cannot bypass run-ref/trial or
  pure-context refusal. Existing completion/REPL no-execution rules stay.

The implementer can use narrower existing modules when they own the exact
behavior; record that disposition rather than duplicate a test. Collect each
changed/added test module, run narrow cases, then the affected suite with
`pytest -q -n 16 --dist=worksteal` in tmux. One public compile/run/resume wrapper
with scripted local leaves must preserve value, concrete effect lineage and
completed-result reuse. An imported workflow-capsule configuration-conflict
control uses `tests/test_workflow_evaluated_call_lineage.py`; no cross-capsule
provider-key model is inferred from that fixture. The read-only executable
capsule probe `/tmp/orc-el1-capsule-summary-cixk_0i2/receipt.json` wraps an
imported workflow with different producer/consumer provider and command
configuration; its exact inferred set is `(calls-workflow dep)`, with no
producer provider/command atom crossing that boundary. This supports the
existing boundary rather than adding an owner/configuration effect schema.

**B completed; F released.** The final B candidate has independent compliance
and code-quality approval. Its new contract tests pass 44 cases; the affected
16-module suite passes 825 cases in 16.56 seconds, including public scripted
run/completed-resume checks. All changed test modules collect (401 cases across
the eight selected modules). The final package and owner hashes match before
and after the broad run:
`/tmp/orc-el1-b-1792124410615878442/review-freeze-7-manifest.json`
(SHA-256 `c377a437abd5aa309dc9b7b803f25e89d9f76c472ecf92486061dc86eab0339e`)
and `broad-v7-receipt.json`. The three imported-call lineage tests also pass.
An imported 2.35 macro's emitted definition follows the receiving 2.39 regime,
while the same omitted-clause emission is refused under 2.35; the checked-build
probe is recorded in `/tmp/orc-el1-macro-origin-m49b2e3f/receipt.json`.
Resolved calls use the existing lexical discovery and materialized rows;
inspection reuses that traversal without materializing work. Unused callable
parameters do not invent effects or incompleteness. These checks release F,
not public 2.39 support before C/D/E or the source-floor acceptance below.

**C/D acceptance.** Use `tests/test_workflow_lisp_procedure_first_migrations.py`,
`tests/test_workflow_lisp_closed_program_frontend.py`,
`tests/test_workflow_lisp_provider_supervision.py`,
`tests/test_workflow_lisp_command_control.py`,
`tests/test_workflow_lisp_stdlib_form_migration.py`,
`tests/test_workflow_lisp_phase_stdlib.py`,
`tests/test_workflow_lisp_drain_stdlib.py` and
`tests/test_workflow_lisp_closed_phase_target.py` as applicable. Prove new-target
lowering refusal and inline policy, 2.35–2.38 imported AUTO/private identities,
generated let-proc behavior, explicit workflow frame/call and same-source resume.
Direct private heads, a same-named user macro synthesizing a private head,
other user synthesis, a caller-spliced private head and a shadowing fake std
module producing a private head must refuse. Genuine packaged 2.35
phase/drain expansion in a new target, including nested user→builtin expansion,
must retain its old success or downstream diagnostic. Bare compatibility heads
refuse while imported routes remain. Do not claim complete build support for a
stdlib form whose existing later stage is already unsupported. Preserve authored
source spans and expansion attribution. Existing `phase-target` typed/read-back
controls remain.

The ordinary-boundary feasibility proof is
`/tmp/orc-el1-boundary-proof-xdpoxb6h/receipt.json`: existing 2.38 unexported local
workflow plus ordinary call evaluates to 5 with one closed call and definition
key `[el1/boundary, workflow, internal]`. It proves reuse of the existing
mechanism, not old private identity or cross-version recovery. Existing macro
syntax already supplies the head introduction id, frame definition span and
builtin source path; no new provenance schema is needed.

**E acceptance and finite utility decision.** Save the two exact before-source
snapshots and configurations outside mutable fixtures, then compare the new
sources under identical scripted leaves. Run their owning public integration
in `tests/test_workflow_evaluated_consumers.py` and
`tests/test_workflow_lisp_guide_programs.py`, plus their existing narrower owners.
Demonstrate four local revisions: dependency addition, dependency removal,
provider substitution under an intentional ceiling, and imported hook adaptation.
Record required annotation edits, coupled files, expected compile failures and
whether source-mapped diagnosis identifies the responsible restriction/call.
Demonstrate that an omitted effectful wrapper needs no ledger repair and that
intentional ceilings still detect a disallowed change. This is bounded
mechanical authoring evidence; human/agent productivity, search quality and
paid-provider cost remain unmeasured. Fix a concrete recurring issue exposed by
these cases before closure, or explicitly narrow that unsupported case in the
governing contract and review it; do not close EL-1c merely by running a smoke.

Verify fresh public compile/run/resume with scripted leaves for the migrated
source, retaining intentional schema/policy/result semantics and reuse within
that new identity. Admitted 2.35–2.38 source controls and frozen evidence remain unchanged;
no old artifact backfill or cross-target resume claim. Reuse the frozen full
baseline and completed WCC/D2/D3 verification unless these edits affect their
owners. Independent code/plan review, the coordinator's final diff inspection
and existing phase-closeout obligations remain controlling.

Each selected Task 5 lane has its own exit; none requires completing all of
Task 5. Optional policy, confinement and EL-1d cannot hold other lanes open.

| Lane | Exit |
| --- | --- |
| EL-1 | Existing EL-1 step acceptance, ES hand-back, target and owner conditions met for the selected step |
| Executable specialization | Dedicated executable entry, displaced branches/flags removed for disposed callers, retained analysis/import/editor and public checks pass |
| Authored lowering | Selected versioned callers migrated; semantic boundaries and identities preserved or explicitly versioned; displaced syntax/strategy removed |
| Primitive catalog | Duplicate selected rules deleted; independent source/artifact/runtime vectors pass, including path and short-circuit controls |
| Parallel preparation | Replaced preparation deleted; bounds/order/failure/recovery checks pass; collision preflight stays live-only |
| Effect metadata | Named EL-1d maintenance need and equivalent consumer behavior established, or cleanup explicitly cancelled |
| Retirement | Every selected caller/run has a disposition and its displaced owners are deleted under existing retirement authority |
| Source/intrinsics | Versioned admission and migration complete for selected forms, with public refusal controls |
| Confinement | Existing child qualification preserved; ordinary-provider policy either explicitly deferred or passes its selected denial/no-fallback/resume checks |
| Environment/unlimited policy | Explicit deferral or selected versioned policy passes real caller compatibility and leakage checks |
| Architecture/test guidance | Remaining selected inconsistencies corrected against owners, with valid routes and reproducible checks/count method |

<a id="proposed-recommendation-coverage-and-completion"></a>

## Recommendation coverage and completion

These rows are this plan's recommendations, grounded in the code and
design owners above. They do not claim to reproduce a committed review report.
Rejected interpretations/non-goals are: “39% dead code” from import counts;
using `count_nodes` to refute ten semantic constructs; uniform provider
launch/sandbox behavior; a deleted README pipeline; E-B2 as calibrated performance
guidance; and complete WCC as an EL-1 prerequisite. These are unsupported
premises, not useful recommendations dropped from the review's coverage.

| Proposed recommendation | Source / disposition | Deliverable / acceptance owner |
| --- | --- | --- |
| Structured WCC, not raw frontend escapes | [WCC source checks](../reports/2026-10-15-orc-simplification-review.md#wcc-boundary) | Tasks 2a/2b; zero retained executable producers/re-entry/reverse bridges |
| Retain child facts; type generated values | [WCC source checks](../reports/2026-10-15-orc-simplification-review.md#wcc-boundary) | Task 2a; specialization/capture/type evidence |
| Delete reverse capture/substitution route | [WCC source checks](../reports/2026-10-15-orc-simplification-review.md#wcc-boundary) | Completed Task 2 removes executable reverse bridges; `wcc/historical.py` retains non-executable consumers. Materialization/site evidence and the known computed-list defect are recorded above. |
| Specialize executable elaboration | [Mode source checks](../reports/2026-10-15-orc-simplification-review.md#executable-mode) | Task 5; deleted dual-mode flags/branches, isolated historical analysis, actual plumbing removal |
| Remove authored compiler-strategy lowering | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5; versioned `:lowering` removal, semantic boundaries and identity migration |
| Fixed primitive catalog | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5; deleted duplicate rules, independent source/artifact/runtime vectors and preserved path/short-circuit semantics |
| Shared pure parallel preparation | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5; deletion, refusal timing, live/replay separation |
| Inference-default effect restrictions | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5 / EL-1; real identity/import/specialization prerequisites |
| Reduce effect-analysis metadata | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5 / EL-1d cancelled for this selection after consumer inventory; retain the live summary owner |
| Process cleanup under each owned profile | [Process source checks](../reports/2026-10-15-orc-simplification-review.md#process-cleanup) | Task 1; prior session/PGID decision, bounded teardown, quiescence/join or explicit residual failure |
| Authored timeouts and environment policy | [Process source checks](../reports/2026-10-15-orc-simplification-review.md#process-cleanup) | Task 5 optional policy lane; compatibility decision before policy change |
| Canonical typed results | [Transport source checks](../reports/2026-10-15-orc-simplification-review.md#result-transport) | Task 3; observed truth tables, preserved per-profile semantics, one owner for equivalent rules, compatibility evidence |
| Preserve memo history and freshness | [Transport source checks](../reports/2026-10-15-orc-simplification-review.md#result-transport) | Task 3; old committed results untouched, lineage separate |
| Genuine confinement | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5; explicit ordinary-provider qualification/defer decision, existing child gate, policy-bound resume and denial/no-fallback checks |
| Consumer-based retirement | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5 and DC-P; finite dispositions including import/editor/readers |
| Narrow source and retire temporary intrinsics | [Shared-owner checks](../reports/2026-10-15-orc-simplification-review.md#shared-rules-and-retirement) | Task 5; explicit admission contract and caller migration |
| Honest guarantees and architecture/test documentation | [Authority / evidence limits](../reports/2026-10-15-orc-simplification-review.md#authority-and-acceptance) | Tasks 0/5; immediate guarantee correction, authoritative routing and reproducible count method |
| Fresh regression evidence and public integration | [Authority / evidence limits](../reports/2026-10-15-orc-simplification-review.md#authority-and-acceptance) | Verification below; same-population baseline, no new failures, defects and external prerequisites visible |
| Dynamic composition with useful boundary types | [Authority / evidence limits](../reports/2026-10-15-orc-simplification-review.md#authority-and-acceptance) | Task 4; existing DC-P and finite migration/deletion |
| Real consumer utility, quality and total cost | [Authority / evidence limits](../reports/2026-10-15-orc-simplification-review.md#authority-and-acceptance) | Task 4; bounded named task, qualified evidence and full cost |

## Verification and handoff for each selected slice

- [x] State its approach/tradeoff and exact ownership, update semantic owners
  before behavior changes, then add behavior/contract tests. Use no tests that
  assert literal prompt phrasing. Run `pytest --collect-only -q` on each module
  with new/renamed tests, followed by its narrow selectors.
- [x] Run affected owner suites and at least one public orchestrator integration
  or smoke check; static slices require source-free artifacts and run/recovery.
  Command examples above are initial selectors, not sufficient final coverage.
  New/renamed tests require collection of the changed modules; unchanged
  test modules need no redundant collection-only run.
- [x] Compare fresh before/after results on the same selected test population
  and account for every changed outcome. Fix and recheck each new regression;
  do not absorb one into a known-failure allowance. The frozen final full result stays red;
  its two newly observed failures have the separate post-full assertion
  correction and controlled pre-existing race disposition above. The corrected
  owner module passes; no source-floor/2.39 production regression is demonstrated
  by the isolation comparison. Keep existing real defects visible with named
  owners/dispositions; classify external prerequisites separately with
  reproducible requirements. Do not narrow supported scope or
  relabel historical campaigns as a fresh baseline to make the result green.
  Refresh changed cells of the evaluated design's
  [§17 public behavior matrix](../design/workflow_lisp_evaluated_execution.md#17-evidence-requirements),
  using `tests/test_workflow_evaluated_totality.py` and
  `tests/test_workflow_lisp_guide_programs.py`, plus same-target identity evidence.
  The [capability matrix](../capability_status_matrix.md) owns implemented,
  admitted and qualified scope; refresh affected entries without promotion
  beyond their evidence.
- [x] Run relevant broad/slow suites in tmux using
  `pytest -q -n 16 --dist=worksteal` plus the exact modules chosen for that task.
  A slice runs the relevant broader affected checks; it does not automatically
  close a delivery phase or require the full suite. An actual phase closeout
  follows the parent [Closeout, Per Phase](2026-09-29-workflow-lisp-evaluated-execution-plan.md#closeout-per-phase):
  full suite in tmux with those flags, before/after failure accounting and
  fresh public compile/run/resume for each new form. This extension adds no new
  main phase gates and weakens none of those existing closeout obligations.
- [x] Independently review the diff, deletion claims, identity/compatibility
  results and unresolved limitations. The coordinator inspects final evidence.
- [x] Update this document and existing routing/owner records with actual
  outcomes; no per-tranche report framework is required. If later activation
  uses a manifest, update its source of truth and validate selection then.

**Current routing effect:** executable tranche/manifest rows remain **0 → 0**.
The selected bounded implementation and documentation lanes are integrated,
including the source floor and 2.39 EL-1/lowering/source-admission/consumer work.
Final population/cause accounting, the separately reviewed post-full corpus
correction and coordinator inspection complete this selected scope with the red
suite and residual race/native/LSP defects explicitly retained. Task 4 retains
typed W3 and stops only this 3.0 adoption/migration lane; EL-1d is cancelled for this selection. Ordinary-provider
confinement and environment/unlimited-policy changes remain explicitly deferred,
with D2 behavior and existing child gates retained. No automated workflow handoff,
main Phase 5/6b/7 closeout, new research allocation or green-suite claim follows.
