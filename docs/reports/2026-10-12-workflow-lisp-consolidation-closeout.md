# Workflow Lisp Consolidation Execution Record

Status: **bounded extraction complete**. Tasks 0–4/Gates A–D of the
[consolidation plan](../plans/2026-10-12-workflow-lisp-consolidation-plan.md) are
accepted at integrated revision `bfd0f324`, after independent Astra review and
coordinator acceptance. The full suite remains RED (275 failed), with reviewed
dispositions below. Later migration/recovery/retirement gates remain open.

## Selection And Preserved Gates

The owner requested execution of the whole plan on 2026-10-12 and limited
retained-run scope to this repository, including nested experiment/project run
roots. Current execution covers Tasks 0–4; Tasks 5–7 retain their gates.
Work uses isolated worktree
`.worktrees/orc-consolidation-20261012` (W), branch
`feat/orc-consolidation-20261012`, starting at
`fb90b036c3a92cf4506bedc42a101f378919cd95` (tree
`397dcd599be603e4a7a5b571961b99e2795935e9`). Evidence is retained separately in
`.worktrees/orc-consolidation-evidence-20261012` (E); baseline metadata is
`E/baseline.json`, with interpreter `/home/ollie/miniconda3/bin/python`.

Tasks 5–7 retain the [parent's delivery order and decision 8](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#phase-7-retirement).
The owner separately selected Phase 5 D1 target **2.37** on 2026-10-12 for
parallel map; the [Phase 5 plan](../plans/2026-10-07-evaluated-execution-phase-5-plan.md)
retains baseline, implementation/admission and public qualification gates.
Old-target retirement and retention cutoff remain unselected. Extraction
preserves currently supported behavior and APIs.

## Task 0 Inventory

The bounded qualification set is W3 proposal (2.36), README
`plan_review_execute` (2.35), canonical `reviewed_change` (2.28), canonical
`best_of_n` (2.28), generic watchdog and verified-iteration drain primaries
(2.15), and direct task (2.23). The plan names their concrete paths.
Parallel best of N remains gated on Phase 5; a qualification fixture does not
establish migration of its canonical consumer.

The route registry has 62 rows; the closed corpus has 53 entries: 38 Built,
10 Gap, 4 Refused and 1 NotSynthesizable. These describe their bounded catalogs,
not the entire maintained workflow, stdlib or public API estate. The plan selects
the extraction inventory and exact test owners for the seven consumers,
preserving all current contracts/APIs. Broader migration/retirement dispositions
belong to Tasks 5–6 and do not block extraction without behavioral retirement.

The preservation inventory includes advertised compiler/AST/lowerer exports
from `orchestrator/workflow_lisp/__init__.py` and public
`RunRefPathCompileRefusal` in `workflow/run_ref/path_compile.py`, retaining one
class implementation. `ClosedProgram` is not an advertised package-root export;
private imports migrate mechanically to the extracted owner; root exports stay
unchanged. The public `path_compile.RunRefPathCompileRefusal` import remains
a re-export of one class, with no public API deletion. Reusable
`tracked_design_phase`, `tracked_plan_phase` and
`design_plan_impl_implementation_phase` modules lack registry rows but remain
supported, as do admitted teaching examples. Design Delta's reusable procedures
survive its family deprecation. Existing capability gaps keep their Phase 4/4b
owners; unresolved historical consumer dispositions authorize no deletion.
`E/compiler-import-inventory.txt` retains the fresh direct import search over
`orchestrator` and `tests`. The plan records source-free/compiler ownership,
deferred run-reference seams and their test owners. This completes the scoped
preparation trace, not proof of runtime compiler isolation (Gate B).

`E/repository-run-inventory.json` records a read-only inventory of direct
`runs/<id>/state.json` entries under the main checkout's `.orchestrate/runs` and
`.orchestrate/archive`: 4,173 states, all schema 2.1, with recorded statuses
running 83, failed 208, completed 3,875 and suspended 7. Recorded `running`
does not prove liveness; status or schema does not prove target, supported
recovery or retained input completeness. Roots without a state file are outside
these counts. Nested experiment/project run roots inside the repository remain
in scope and are not covered by this initial inventory. Original run/archive
data stays untouched; external repositories and user storage are outside scope.

Generated pre-change fixtures are separate from those existing runs. The first
manifest retains three evaluated interrupted captures: command/provider at
2.35 and command at 2.36. Baseline public resumes exit 0 with terminal values
6, 9 and 6, respectively; stopped roots were restored from retained snapshots.
The continuation manifest retains an interrupted flat child at 2.24 inside an
evaluated 2.35 parent (public resume exit 0, terminal `true`, stopped root/control
restored), plus completed flat parents at 2.28 (reviewed change, `READY`, two
rounds) and 2.15 (watchdog, `FIXED_AND_RESUMED`, action `RESUME`). Both flat-parent
runs exit 0; they establish no interrupted-flat-parent recovery claim.

| Evidence under E | SHA-256 |
| --- | --- |
| `prechange-public-captures/capture_manifest.json` | `6d1f7e0ba223a5f2df1540f57631c571730b1f37ef6a36eaed981e2d3ce07106` |
| `prechange-public-captures-legacy-continuation/capture_manifest.json` | `7dca1d5d0247b0879f12c9825cd69fe809a751863b622d0acba2488d8173fff5` |
| `compiler-import-inventory.txt` | `8e78f4f5b815d26ec4cbcede340a2bd22cf48a0538fec2bb8ac009375408a22e` |

These manifests record absolute roots, source/assets/closures, snapshot trees,
hashes, invocation/environment and real package/interpreter pins. The original
capture process exited 1 because its old-child comparison used independently
generated `file://` locators; its failed attempt and first three successful
captures remain retained. The corrected continuation exits 0 under its embedded
receipt and reuses those three captures without rerunning them. Providers use
deterministic fixture-local transports; no live-model qualification is claimed.

The retained release is `E/baseline-release` at
`fb90b036c3a92cf4506bedc42a101f378919cd95`. Its real compiler/runtime identity
matches both capture manifests:
`sha256:7a97baa862cbf54ca3342c93b381c6ec9952e17bc1fbf77dfc6cdd56ce2630de`.
This proves the recorded pin match, not universal old-run recovery.

The fixed-identity corpus completed with exit 0: 53 cases (38 Built, 4 Refused,
10 Gap, 1 NotSynthesizable). `E/corpus-before/manifest.json` has SHA-256
`c211130522b27dfea57d528482d46fb1e0b2f94232c13161663a174a021b57c8`;
the coordinator verified all 38 built-artifact hashes. Only this canonical
comparison uses `sha256:` plus 64 `c` characters as its fixed compiler pin and
the retained `E/fixed-corpus-scratch` path before/after extraction. Real run
pins are never replaced by that comparison input.

## Baseline Receipts

Commands ran from W before product edits. The common evidence arguments are
`--basetemp E/<campaign>-tmp --junitxml E/<campaign>.xml`; E expands to the
absolute evidence directory named above. The JSON receipts retain exact argv,
cwd, exit and completion time; corresponding logs and XML retain outcomes.

| Campaign | Exact selector before evidence arguments | Fresh result | Receipt |
| --- | --- | --- | --- |
| `narrow-artifact` | `pytest -q tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_evaluated_provider_io.py` | 238 passed, exit 0 | `E/narrow-artifact.json`, `.log`, `.xml`; finished 2026-10-13 04:49:58 UTC |
| `narrow-lifecycle` | `pytest -q tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_resume_kills.py tests/test_workflow_evaluated_run_ref_kills.py` | 19 passed, exit 0 | `E/narrow-lifecycle.json`, `.log`, `.xml`; finished 2026-10-13 04:52:38 UTC |
| `full` | `pytest -q -n 16 --dist=worksteal` | 362 failed, 23,354 passed, 36 skipped, 171 xfailed, 32 errors, 230 warnings; exit 1; pytest time 1,139.12s | `E/full.json`, `.log`, `.xml`; finished 2026-10-13 05:11:39 UTC |

These narrow passes are baseline evidence. They do not establish extraction
parity, compiler isolation or complete recovery. The completed full baseline
is RED. `E/baseline-failures.json` retains the exact 394 failed/error rows for
comparison and disposition; the receipt wall time is 1,141.08s. No overall
GREEN or post-change acceptance is claimed.

The chosen long `E/full-tmp` path causes observed `AF_UNIX path too long`
failures in provider materialization tests. Watchdog-watcher tmux setup errors
may have the same path-length cause; that attribution remains unverified.
The coordinator's 394-case failed/error retest completed before product edits,
with `/tmp/oc-b0` as basetemp: 231 failed, 163 passed, zero errors, exit 1,
188.05s pytest time (188.84s receipt wall time). Exact selectors/cwd/exit and
results are retained in `E/baseline-retest.json`, `.log` and `.xml`.
`E/baseline-short-failures.json` retains the exact 231 remaining failure rows.
This is a failed-case rerun, not a second full campaign or a combined full PASS.
The original full RED receipt remains retained. Golden-divergence and experiment
failures require their own disposition; the original 394 rows are not all
classified as pre-existing product defects.

## Task 1 Feasibility And Evidence Reuse

Task 1/Gate B received independent Astra contract/evidence PASS and a separate
Sol code-quality review with no findings. Both reviews inspected code and
receipts; neither reviewer executed tests independently. This is bounded
feasibility acceptance, not final package qualification.

`E/task1-isolation-tool-receipts.md` retains tool-output excerpts, not full
redirected logs. Initial collection found one case; execution failed on an
actual transitive compiler import through `workflow/__init__.py` and the flat
executor. After extraction and the remaining caller correction it passed.
Expanded collection found nine cases. Their coverage is three reused PASS
cases from the five-case seam check, two corrected command/provider cases
(`2 passed, 7 deselected`, exit 0), and four real child/parent cases
(`4 passed, 5 deselected`, exit 0). This was the initial coverage record;
the later `after-affected` campaign ran and passed all nine together, while
remaining RED overall as recorded below.

The intermediate two performer failures came from the test harness omitting
the retained file owner during invalidation; the correction used the writer
lock and checked retained descriptor. No production guard was weakened.
Provider transport remains the deterministic external shim. The parent matrix
uses actual 2.24/2.35 children and settle/reconcile, including tampered authority,
lazy failure diagnostics and no duplicated committed child. Its complete output
and exit are `E/task1-isolation-parents.log` and `.exit` (0).

| Task 1 evidence | SHA-256 |
| --- | --- |
| `task1-isolation-tool-receipts.md` | `7c73b0503842111e9ee9da1b5b7cfda5e5fa6d517249283cc5a17cd44b2dd7ca` |
| `task1-isolation-parents.log` | `3efa70eb3a39cc1374731725792acd3ca3ee8b06eeb71b3165aeba50ef0034d6` |

Production seams are now `contracts/closed_program/`,
`workflow/evaluated/provider_io.py`, `workflow/typed_prompt_inputs.py`,
`workflow/run_ref/{wire,path_contracts}.py` and `contracts/program_identity.py`
under `orchestrator/`. Compiler preparation, public rebuild authority and child
compilation remain at their existing boundaries. Tasks 2–3 promote this patch
and reuse valid evidence; they do not extract the same owners twice.

## Post-Extraction Owner Checks

These coordinator checks ran in W; exact argv/cwd/exit are retained in each
JSON receipt, with logs/XML where applicable. They do not close Task 4.

| Campaign | Scope and fresh result | Receipt |
| --- | --- | --- |
| `after-narrow` | Artifact, semantic-check and provider-IO owners: 238 passed, exit 0, 5.68s pytest; `/tmp/oc-n1` | `E/after-narrow.json`, `.log`, `.xml` |
| `after-wire` | Child/path compile, diagnostics/source, child authority and settlement: 426 passed, exit 0, 50.69s pytest; `-n 16 --dist=worksteal`, `/tmp/oc-w1` | `E/after-wire.json`, `.log`, `.xml` |
| `corpus-after` | 53 cases with unchanged outcomes; all 38 built artifacts byte-identical to the fixed-input pre-change corpus; exit 0 | `E/corpus-after.json`, `.log`; `E/corpus-after/manifest.json` |
| `readme-smoke` | Existing `plan_review_execute` public dry-run recipe: exit 0 | `E/readme-smoke.json`, `.log` |
| `after-affected` | 126 modules: 20 failed, 4,079 passed, zero errors, exit 1; 1,768.46s pytest; `-n 16 --dist=worksteal`, `/tmp/oc-a1` | `E/after-affected.json`, `.log`, `.xml` |
| `extraction-rechecks` | Whole typed-prompt-input module, both FIFO-monitor parameters, both watchdog stream parameters and the initial public-import fixture: 53 passed, 1 failed, exit 1; 80.73s pytest; `/tmp/oc-r1` | `E/extraction-rechecks.json`, `.log`, `.xml` |
| `import-cli-sol-collect-final` | Final public-import fixture: one collected, exit 0 | `E/import-cli-sol-collect-final.json`, `.log`, `.xml` |
| `import-cli-sol-final` | Final public-import fixture: 1 passed, exit 0, 9.99s pytest | `E/import-cli-sol-final.json`, `.log`, `.xml` |

The before/after corpus manifests share SHA-256
`c211130522b27dfea57d528482d46fb1e0b2f94232c13161663a174a021b57c8`.
The coordinator's `E/extraction-checks-finished` marker records `passed` for
these checks. Canonical fixed-input equality remains separate from actual
package-pin differences and retained-run resume disposition.

The affected campaign passed all nine isolation cases together, 13 public CLI
cases, four run-reference kill cases and two resume-kill cases. Its raw RED
receipt is retained; no overall post-change PASS is claimed.
`E/after-affected-failures.json` and `E/after-affected-comparison.json` retain the
failure rows and baseline comparison. Four failures were test references to
`render_typed_prompt_inputs` at its displaced compiler owner; the test now
imports the existing runtime owner, with no production compatibility alias.
The full typed-input module passes in `extraction-rechecks`. The affected FIFO
monitor timeout and both watchdog stream parameters also pass in that narrow
recheck. Fourteen other watchdog failures overlap the short-path baseline at
the same nodes and timeout/missing stand-in-call assertions; this establishes
observed failure overlap, not a proved common root cause or a full watchdog PASS.

The recheck's one failure was the new public-import fixture's module/path
mismatch, not production behavior. The corrected final
`test_public_cli_selects_distinct_import_assets_without_redispatch` passes in its
separate receipt. It uses direct no-argument imported workflows returning `Int`,
distinct roots containing the same `prompt.md` asset path, selected asset
hashes/bytes, distinct effect identities, terminal value 3 and completed resume
without redispatch. Bound-procedure routing keeps its existing
`test_workflow_evaluated_provider_io.py` and
`test_workflow_evaluated_provider_activation.py` owners. The earlier failed
fixture receipts remain historical evidence and do not qualify that final
fixture. Independent Astra review closed the public-import finding after
inspecting the final code/receipt; this bounded verdict does not accept Gates
C–D overall. These narrow passes do not turn either RED campaign into a full PASS.

## Task 4 Retained-Run Checks

`E/task4-retained-check-20261013T054816Z/summary.json` records all six retained
families complete; `E/task4-retained-cli-20261012.log` and `.exit` retain the
full CLI-check output and exit 0. Every family has `errors: []` and its
original captured fixture restored. Each family directory contains `result.json`
with exact argv/cwd/environment, package identity, output/diagnostic hashes,
material-write comparison, report and restoration evidence.

Five changed-package public resumes exit 0: evaluated command/provider at 2.35,
command at 2.36, completed reviewed-change parent at 2.28 and completed watchdog
parent at 2.15. The 2.15 completed resume changes its compiled
`typed_frontend_ast.json`; recorded provider/script dispatch logs remain
unchanged. This is accepted resume with one recorded compile-artifact write,
not a zero-write claim.

The interrupted old child 2.24 under its evaluated parent refuses on the changed
package with exactly `resume_program_changed`, exit 2 and zero material writes.
Its stored compiler pin is
`sha256:7a97baa862cbf54ca3342c93b381c6ec9952e17bc1fbf77dfc6cdd56ce2630de`,
while the changed package is
`sha256:33f0ae6a979f25cf90e3721f95e80c5a373316e7056afeda53d2ee3d7fc97a22`.
Public resume of the original interrupted root on the retained baseline release
exits 0 with the expected terminal/result and committed-child behavior. The
receipt records expected journal/ledger/state writes during recovery, followed
by restoration of the stopped capture. Real-pin refusal remains intact.

| Retained-check evidence | SHA-256 |
| --- | --- |
| `task4-retained-check-20261013T054816Z/summary.json` | `03b6f706ab34793ac594dc1f8c3bf32f952ae476c62fddf216ccf1aa5efa3716` |
| `task4-retained-cli-20261012.log` | `7cb22ee6d6f7e2008e4519471f16ce498a260c4447e1833af8be0874da1be7ff` |

These generated representatives give bounded retained-run evidence, not
universal old-run recovery or interrupted-flat-parent qualification. Existing
repository runs/archive data remain untouched. The affected lifecycle cases
above pass; the integrated checks below add fresh evidence, while final
Task 4 acceptance is recorded below with the full RED dispositions.

## Integrated Checkpoint Receipts

Extraction checkpoint `f724b2b727c9a4cd01f85845c3fa70c80c3bb31d` merged exact main
`705e033b65fa8f7994e004aea55de68ea2c24fdd` into W at
`bfd0f32411cec03241a9b2f54a6fcae118c75bd5`. The checkpoint cleaned EOF whitespace
in `contracts/program_identity.py` and `workflow/run_ref/wire.py`; the earlier
`sha256:33f0ae…` package pin belongs to its historical retained-check receipt.
`E/integration-selection.json` records the selected revisions. Independent Sol
code review found no blockers in the overlapping extraction/REPL changes.

| Integrated campaign | Fresh result | Receipt |
| --- | --- | --- |
| `integration-capture-collect` | Nine isolation cases collected, exit 0 | `E/integration-capture-collect.json`, `.log`, `.xml` |
| `integration-capture-narrow` | Compiler-blocked real command performer/readers: 1 passed, exit 0, 5.71s pytest | `E/integration-capture-narrow.json`, `.log`, `.xml` |
| `integration-focused` | Seven modules, 268 passed, exit 0, 42.25s pytest; `-n 16 --dist=worksteal` | `E/integration-focused.json`, `.log`, `.xml` |
| `integration-retained` | Six retained families complete, exit 0, 41.11s receipt wall time | `E/integration-retained.json`, `.log`; `E/task4-retained-check-20261013T064657Z/summary.json` |

The focused module list is `test_workflow_closed_program_isolation.py`,
`test_workflow_evaluated_import_cli.py`, `test_workflow_evaluated_repl.py`,
`test_workflow_lisp_print.py`, `test_workflow_lisp_closed_program_compile_cli.py`,
`test_workflow_pure_catalog_agreement.py` and
`test_workflow_lisp_design_review_execute_example.py`, all under `tests/`.
Exact argv/cwd/exits are in the JSON receipts.

`E/corpus-integrated/manifest.json` records 54 cases: 39 Built, 4 Refused,
10 Gap and 1 NotSynthesizable. Its only added case is
`workflows/examples/design_review_execute.orc::run`.
`E/corpus-integrated/comparison-qualified.json` verifies unchanged outcomes for
all 53 original cases and byte-identical artifacts for all 38 original Built
cases; its exit is 0 and manifest SHA-256 is
`bcf4587d4952a43f123f349ccf2201d31a4d649f1301039041dd9ddeb8edd5c6`.
The original `E/integration-corpus.json`/`.log` retain exit 1: the harness compared
a Python tuple with a JSON list in `NotSynthesizable.missing_facts`. Serialized
manifest/artifact comparison passed without a product edit or corpus rerun.
The original 53-case baseline remains unchanged.

The integrated retained-check family results each have `errors: []`: five
changed-package resumes accept; old child 2.24 refuses and recovers on the
retained release, with originals restored. The current package identity is
`sha256:55211db74ae121bb76b8edcf3a8d938955e4cb3507f0656c30d781df6328dba7`.
This is bounded family evidence, not universal recovery. The integrated source
snapshot `E/integration-snapshot.json` records 1,917 paths at `bfd0f324`, SHA-256
`21729b7a9f6c91d0077dd44433838889d2f3360e01ce87f46913c74fd11c3a25`.
The coordinator accepted Tasks 2–3/Gate C at `bfd0f324` after independent Astra
final review of the 268-case PASS, all nine isolation cases, compiler-blocked
command/readers evidence and six error-free retained families with restored
originals. No other extraction contract gap remains. The full campaign is now
complete as recorded below; Gate D acceptance includes its bounded failure
qualification and does not assert overall GREEN.

## Integrated Full Campaign And Failure Qualification

At `bfd0f324`, `E/after-full.json`, `.log` and `.xml` record
`python -m pytest -q -n 16 --dist=worksteal` with `/tmp/oc-f1`: 275 failed,
23,511 passed, 36 skipped, 169 xfailed and 230 warnings; exit 1; 1,839.70s pytest
(1,842.92s receipt wall time). The receipt confirms the integrated snapshot hash
above unchanged. This full result remains RED.

`E/after-full-cause-comparison.json` retains the rows compared with the separate
short-path baseline. All 275 failures have bounded dispositions:

| Count | Observed cause/disposition |
| --- | --- |
| 207 | Same node and exact failure message as the short-path baseline |
| 4 | Same missing nanoBragg source cause; only the interpreter representation in argv differs |
| 58 | ES canonical interpreter-path validation rejects the symlinked `python` invocation; independent Sol review traced every case to the same chain |
| 5 | Timing/order failures not reproduced in the sequential bounded rerun; parallel-campaign behavior remains an evidence limit |
| 1 | Known F50 watchdog variation; bounded rerun produces its existing XFAIL, with no product correction |

The baseline `pytest` shebang used canonical
`/home/ollie/miniconda3/bin/python3.13`; the post-change wrapper used symlinked
`/home/ollie/miniconda3/bin/python`, which the ES `_canonical_absolute` trust
boundary refuses. `E/after-full-canonical-retest.json`, `.log` and `.xml` record
all 58 affected ES cases passing under `python3.13 -m pytest -q -n 16
--dist=worksteal`, exit 0, 10.61s pytest. This validates the invocation cause
without changing production code or validation.

`E/after-full-bounded-retest.json`, `.log` and `.xml` record five passed and one
XFAIL, exit 0, 64.74s pytest under canonical Python. The five passes cover both
Q5 deadline cases, both controlled-stdin cancellation parameters and the trial
sibling-failure case. Their sequential pass does not prove absence of a
concurrency defect. The watchdog XFAIL remains the known F50 condition. No
product or test bytes changed for these reruns; the original full RED is neither
replaced nor combined into an aggregate GREEN. Independent Astra accepted Gate D
for bounded extraction at `bfd0f324`, and the coordinator accepted that verdict.
No contractual blocker remains to proceed with the separately selected Phase 5
2.37 work; this report claims no Phase 5 implementation.

## Open Gates And Next Evidence

The coordinator accepted Gate A for extraction after the scoped preservation
inventory, baselines, retained captures and fixed-identity corpus. Task 1's
accepted feasibility evidence and delivered core/wire patch now supply Gate B.
Tasks 2–3 are complete and Gate C is accepted after the integrated independent
review above. The direct-import public CLI witness passes, with bound-procedure
coverage retained by its existing owners. Gate D is accepted for bounded
extraction with the completed RED failure qualification. Task 4 has the bounded
retained-artifact/real-pin results and affected lifecycle passes above; the raw
affected campaign remains RED. Exact main `705e033b` is integrated at `bfd0f324`,
with fresh focused, corpus, retained-run and full checks recorded above. The
full campaign remains RED with the bounded dispositions above. Independent
review and coordinator acceptance close Tasks 0–4/Gates A–D only. Original
baseline RED and the separate short-path rerun remain unchanged.

Tasks 5–7 additionally need consumer capabilities/qualification, explicit
old-family and archive dispositions, and owner cutover/cutoff decisions.
Repository-only inventory supplies scope; it supplies none of those policies.
