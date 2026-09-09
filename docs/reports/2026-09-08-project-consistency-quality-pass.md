# Project Consistency Quality Pass — 2026-09-08

Status: pass complete; corrections integrated and reviewed, with unresolved
findings and broad-suite limits recorded below.
Purpose: record confirmed contradictions, their owners, corrections, and limits.
Authority: this report is execution evidence, not a specification, roadmap
selector, workflow promotion, or research-adoption record.
Plan: [execution plan](../plans/2026-09-08-project-consistency-quality-pass.md).

## Scope and method

The user requested the entire project, including code, specs, routing,
conventions, and human/agent guidance. The initial inventory covered 3,145
tracked and nonignored files outside `.tmp/`: 506 under `orchestrator/`, 1,019
under `tests/`, 1,063 under `docs/`, 228 under `workflows/`, 33 under `prompts/`,
18 under `specs/`, and the remaining scripts, examples, experiments, artifacts,
state, and root configuration. This was a project-wide inventory with focused
contract tracing, not a claim to have manually read every line or executed
every possible provider/state combination.

Three read-only scouts examined runtime/specs, workflow/prompt/automation
contracts, and guidance. The coordinator traced current routing and integrated
bounded fixes. Initial status was captured and 2,995 source/document/config
files were snapshotted outside the repository; code
changes were developed in a detached temporary worktree and integrated only
after checking that their destination files had not changed. Existing ES and
research work was preserved. Concurrent changes to those unrelated surfaces
are not attributed to this pass.

The authority order was runtime specs and explicit repository policy, accepted
frontend component contracts, active roadmap/task gates, durable artifact
contracts, then reports and prompt wording. Catalogs route to those owners.
Historical reports and machine-readable retirement inventories were preserved.

## Findings and corrections

| Classification | Root cause / old rule | Source of truth and correction |
| --- | --- | --- |
| `semantic_conflict` | Public run parsing, direct configuration, and the private prompt namespace defaulted summaries to 120 seconds, while fresh resume and the spec used 300. | [CLI spec](../../specs/cli.md) and `DEFAULT_SUMMARY_TIMEOUT_SEC` in `orchestrator/observability/summary.py`: all fresh entry points now use the existing 300-second constant. Explicit values and persisted 120-second settings remain unchanged. |
| `semantic_conflict` | Live Design Delta prompts described retired pointer-file handoffs or obsolete result shapes. | The `.orc` request/result types, `std/phase::ReviewDecision`, and [Step IO](../../specs/io.md): nine bound prompts now use supplied typed inputs, direct report/plan targets, and runtime-bound structured results. The architecture draft artifact remains separate from the provider's small status result. |
| `semantic_conflict` | The architecture validator required `state` paths even though both production callers supplied `artifacts/work`; it never wrote the runtime-bound command result. Its lexical path check also admitted symlink escapes. | `design_gap_architect.orc` and the structured-command transport contract: accept the two supported artifact roots, require resolved paths to remain in the workspace, retain narrower target/review/check constraints, and emit a separate two-field runtime decision for VALID, INVALID, and BLOCKED outcomes. Detailed validation artifacts remain available. |
| `semantic_conflict` / `routing_mismatch` | The selector prompt required eligibility/history evidence that its typed request omitted. | `DesignDeltaDrainCtx` already owns the manifest, progress ledger, and architecture index. Those fields now reach `SelectorPromptSubject` through ordinary typed carriage. Manifest eligibility and completed-attempt avoidance remain requirements. |
| `label_driven_policy` | Workflow age could disqualify copying despite registry-backed readiness. | The route-readiness registry and current owner evidence now govern both workflow catalog and capability matrix. Modification age alone neither grants nor removes suitability. |
| `stale_duplicate` / `discoverability_gap` | The master spec stopped at 2.26, linked a missing `arch.md`, and the strict-Boolean evidence row cited a removed 2.27 rejection test. | Existing [DSL](../../specs/dsl.md), [versioning](../../specs/versioning.md), and compiler admission: index routes include implemented target 2.27 session-artifact publication and current architecture links; the matrix cites the actual admission test. |
| `stale_duplicate` | README allowed completed YAML resume; the matrix claimed all PyYAML use was removed; one pure-expression row implied `match` remained the only proof source at every target. | Current runtime/frontend contracts: all non-`.orc` resume rejects; PyYAML is used for OMP configuration only; target 2.26 adds typed discriminant-derived proof while older targets retain their restrictions. |
| `routing_mismatch` / `stale_duplicate` | Completed Q/L, MVP, migration, ProcRef, and generic-core work appeared as active targets. `let-proc` remained designed-only in catalogs despite compiler/test support. | Completed owners and current frontend evidence: historical scope is explicit, current selection routes to the evolution follow-on roadmap, `ProcRef`/`bind-proc` and bounded V1 `let-proc` are discoverable as implemented, and review/revise companion history routes to the current baseline. Frozen inventory counts remain historical counts. |
| `stale_duplicate` / `discoverability_gap` | CLAUDE duplicated an older subset of AGENTS; testing guidance named absent files/config, omitted live opt-in, and did not support the prescribed worksteal command. | AGENTS owns shared policy. CLAUDE now routes there. Testing guidance uses existing owners, distinguishes opt-in live tests from deterministic checks, and locates markers in `pyproject.toml`; the dev extra includes `pytest-xdist`. |
| `over_specific_instruction` | Four tests froze literal prompt wording; five routing/contract checks froze obsolete phase/version/dependency claims. | Repository testing policy: touched prompt-text tests were removed in favor of behavioral adapter and compiled-carriage checks. Routing checks verify current owner links, supported version bounds, and the distinct retired-workflow/current-configuration YAML lanes. |
| `stale_duplicate` | The CLI spec advertised unused `ORCHESTRATE_*` settings without indicating availability. | The optional clarification received no answer before this correction; the stated working interpretation keeps the names as planned and documents their current lack of effect plus supported flags. Retention remains unimplemented pending an explicit deletion/precedence contract. |

## Files changed

- CLI behavior and regression coverage: `orchestrator/cli/main.py`,
  `orchestrator/cli/commands/run.py`,
  `orchestrator/cli/commands/prompt_run_service.py`,
  `tests/test_cli_observability_config.py`, and
  `tests/test_runtime_observability_cli.py`.
- Workflow dataflow: `workflows/library/lisp_frontend_design_delta/selector.orc`
  and its exact `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`
  mirror; `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`;
  all nine prompt files named by
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`;
  `tests/test_lisp_frontend_autonomous_drain_runtime.py` and
  `tests/test_workflow_lisp_design_delta_smoke.py`.
- Entry points and policy: `README.md`, `CLAUDE.md`, `pyproject.toml`,
  `tests/README.md`, `workflows/README.md`,
  `orchestrator/workflow_lisp/README.md`, `docs/documentation_conventions.md`,
  `docs/index.md`, `docs/capability_status_matrix.md`, `docs/design/README.md`,
  `docs/lisp_workflow_drafting_guide.md`, `specs/index.md`, `specs/cli.md`, and
  `tests/test_workflow_lisp_drain_roadmap_routing.py`, and
  `tests/test_workflow_lisp_e2_trial_contract.py`.
- Frontend owner/status documents under `docs/design/`:
  `workflow_lisp_frontend_specification.md`,
  `workflow_lisp_frontend_mvp_specification.md`,
  `workflow_lisp_proc_refs_partial_application.md`,
  `workflow_lisp_let_proc_local_proc_refs.md`,
  `workflow_lisp_unified_frontend_design.md`,
  `workflow_lisp_generic_resource_context_core.md`, and
  `workflow_lisp_generic_core_expression_surface_adapter_retirement.md`.
- Historical routing under `docs/plans/`:
  `2026-07-13-procedure-first-reuse-inventory.md`,
  `2026-07-13-procedure-first-migration-waves-plan.md`, and the
  `LISP-FRONTEND-AUTONOMOUS-DRAIN` / `LISP-PROC-REFS-PARTIAL-APPLICATION`
  `work_instructions.md` files; this pass's plan and report.

## Verification

Fresh verification, including failing reproductions before code correction:

- Summary defaults: the new regression failed with public/direct/private
  defaults of 120 versus required 300. After correction, the CLI observability,
  runtime observability, and prompt-run seam modules passed 43 tests in the
  main checkout.
- Adapter: eight new cases initially failed on rejected production paths or
  missing result publication. The corrected validator passed 16 relevant
  cases, including outcome and path-rejection checks. Independent quality
  review then demonstrated external symlink reads/writes; both new regression
  cases failed before the shared containment guard. All 18 adapter cases passed
  afterward in the main checkout.
- Selector: the production compile assertion failed on three missing evidence
  bindings, then passed after restoring typed input carriage.
- Both Design Delta owner modules passed 143 tests in the worktree with
  `pytest -q -n 16 --dist=worksteal` in tmux. Independent specification review
  reran 22 relevant adapter/compile/mirror cases successfully.
- Public production compile passed with fingerprint `756e1637f3306d6a`;
  production dry-run passed in the worktree and again in the final main checkout.
  Each dry-run emitted 404 advisory lint warnings
  (391 redundant relpath-kind and 13 import-output-collision warnings);
  this is not a lint-clean claim.
- `python -m orchestrator workflow-lisp-route-readiness --check` passed all
  60 surfaces with zero issues. Eleven narrow registry/version/retirement
  checks passed in the main checkout.
- The initial broader routing run passed 312 tests and failed the three stale
  assertions described above. Their corrected narrow run passed five tests,
  including existing non-`.orc` rejection controls.
- Bounded `let-proc` characterization passed 17 tests; default, explicit WCC,
  legacy, and linked-entry shared-validation probes also passed.
- The six changed/new-test owner modules collected 245 tests. Documentation
  test selectors, TOML parsing, and diff hygiene were checked. All 505 local
  Markdown link targets scanned across the current hubs, plan, and report exist.
- Final combined verification of 12 owner/dependency modules passed **523 tests**
  in the main checkout after all code and test corrections. Independent
  specification and quality reviews approved the CLI, Design Delta, guidance,
  routing, and final assertion fixes; the coordinator inspected the integrated
  diff and verification output.
- The broad non-live suite finished with **15,955 passed, 16 failed, 14 errors,
  and 7 skipped** in 321.10 seconds. Two failures were additional stale
  documentation assertions corrected above. Failure classification and focused
  rerun results are recorded below; this is not a whole-suite green claim.

Reproduce the final owner union from the repository root, in tmux:

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_cli_observability_config.py \
  tests/test_runtime_observability_cli.py \
  tests/test_cli_prompt_run_seam.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_lisp_design_delta_smoke.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_lisp_e2_trial_contract.py \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_verification_gate.py \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_yaml_orc_gap_list.py \
  tests/test_yaml_frontend_retirement.py
python -m orchestrator workflow-lisp-route-readiness --check
```

The original broad command was `pytest -q -n 16 --dist=worksteal -m 'not e2e'`.
It exhausted the `/tmp` filesystem during repository-clone fixtures. Provide
sufficient temporary storage before reproducing that run; keep socket paths
short enough for AF_UNIX. Live-provider tests were not opted in.

Production compile reproduction:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json \
  --emit-debug-yaml /tmp/consistency-design-delta-updated.yaml
```

The dry-run used `run` in place of `compile`, the same entry/manifest flags,
and `--input-file /tmp/consistency-design-delta-dry-run-inputs.json --dry-run`
instead of `--emit-debug-yaml`. Its temporary input document supplied the nine
public inputs: steering, target design, baseline design, architecture index,
and the five `architecture_targets__*` fields. It used an empty architecture
index under a temporary `artifacts/work` directory and validation-only target
paths. That temporary setup was removed after the run; the checked-in smoke
module in the owner union preserves production compile/carriage coverage.

### Broad failure classification

| Original result | Cause and follow-up evidence | Disposition |
| --- | --- | --- |
| 2 failed documentation checks | A frozen Task-5 selector claim and a literal master-spec 2.26 ceiling contradicted completed owner records and supported versions. | Corrected; both pass independently and in the final 523-test union. |
| 4 failures and 14 fixture errors during clone/calibration/artifact work | The `/tmp` filesystem ran out of space; errors included Git object/clone failures and `OSError: [Errno 28]`. All 18 affected cases passed when rerun with sufficient storage under `/home`. | Environment failure; no implementation or assertion was weakened. |
| 8 ES executable-identity failures | The installed Codex reports 0.153.4 while the frozen metering contract requires 0.145.0; seven controller tests also reject the changed launcher digest. The failures repeat in unchanged ES code/tests. | Keep the pinned identity checks. Restore the approved executable or perform a separately governed refreeze; this audit does neither. |
| 1 ES import-origin assertion | The environment reports `/home/ollie/Documents/PtychoPINN` as its forbidden editable root; the retained assertion requires `/home/ollie/Documents/tmp/PtychoPINN`. The probe itself collected 205 tests and reported no forbidden module origins. | Reproduced environment/fixture mismatch in unchanged owner code. The frozen test/evidence contract needs reconciliation before using this check as acceptance evidence. |
| 1 Q5 synthetic-provider shutdown failure | The broad run recorded `ingress_shutdown_failed` where the test expected completion. A narrow rerun with `TMPDIR=/tmp` passed and its ledger proved the listener closed with zero survivors. The relevant test/runtime files match the initial snapshot. | Transient/non-reproduced; root cause unconfirmed. No fixed claim. |

The 28-case failure/error rerun, excluding the two already-corrected doc checks,
finished with **18 passed and 10 failed** in 380.06 seconds. Nine failures were
the repeated ES environment/fixture mismatches above. The tenth was a separate
Q5 harness failure caused by the longer temporary socket path; it failed before
the original shutdown behavior was reached. The independent short-path rerun
passed:

```bash
TMPDIR=/tmp pytest -q tests/test_q5_phased_synthetic_provider_diagnosis.py::test_never_engaging_provider_bounds_wait_at_whole_attempt_deadline
```

These follow-ups classify the original broad result; they do not replace it
with an inferred full-suite pass. Existing dirty ES code/tests, AGENTS, and
frozen inventories were preserved. Concurrent research/adoption-record edits
remain outside this pass's attribution.

## Remaining distinctions and unresolved findings

1. **Inherited selector result shape:** `SelectorPublicResult` still requires a
   `work_item_bootstrap` even for DONE/BLOCKED. The corrected prompt does not
   invent an item to satisfy it. A terminal result with no existing bootstrap
   context still needs a separate result-contract design; this pass does not
   claim to repair that shape or prove a live-provider drain end to end.
2. **Inherited prerequisite recovery limit:** the typed classification contains
   route/reason/summary only. Its current transition consumes route and reason,
   not structured prerequisite identities. Details remain in the classification
   result's summary; this does not implement automatic prerequisite-edge
   recovery. The old helper scripts are not live consumers in this `.orc` graph.
3. **Legacy live test debt:** `tests/e2e/test_e2e_codex_provider.py` and
   `tests/e2e/test_e2e_claude_provider.py` still construct YAML and use a removed
   wrapper. They are explicitly excluded from recommended current live-test
   selectors and need migration before supplying acceptance evidence. They
   were not reclassified as passing or silently skipped by new code.
4. **Missing historical evidence:**
   `docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md`
   is referenced by the evolution roadmap and two historical experiment designs,
   but is absent from this checkout and the available path history. Its bytes
   were not reconstructed or substituted. Those citations are not verified
   evidence; current research claims must use available, bound records.
5. **Preserved gates and compatibility:** source-version restrictions,
   runtime closures remaining future, mandatory exact `:effects`, ES adoption,
   proposed research selection, immutable parity evidence, and historical
   state observability remain separate contracts. No study allocation,
   roadmap activation, provider call, or artifact adoption was performed.

## Evidence location

The transient audit snapshot, collection log, integration patches, and routing/
broad test logs are under `/tmp/orc-consistency-20260908-mk8jxhz3/` for this
session. Design Delta worktree logs are `/tmp/consistency-design-delta-checks.log`
and `/tmp/consistency-design-delta-dry-run.log`. These temporary paths are
session diagnostics, not durable authority or content-addressed closure proof.
The exact commands above are the durable reproduction record. Additional
temporary-only probes are supplemental observations, not retained fixtures.
