# Workflow Lisp Executor Retirement: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_executor_retirement.md](../../design/workflow_lisp_executor_retirement.md).

## Original delivery metadata

**Status:** selected by the owner on 2026-10-13; gate R accepted. Physical implementation is deleted and independently reviewed PASS. Retained-test migration has independent source/ledger PASS and completed second-full evidence: RED with 15 classified failures, zero errors and no new unaccounted failure. Tasks 0–5 are complete in the commit containing the execution closeout, which records independent final review PASS, main integration and preserved user changes through its delivery receipt.

## 3. Historical Baseline And Canonical Migration

The historical 2.28 baseline used serial `list/map-effect :max 8` candidate
implementation followed by the judge. The maximum bounds list size, not
concurrency. The canonical
[`best_of_n.orc`](../../../experiments/orc_vs_single_call/workflows/best_of_n.orc)
now targets 2.35 with its existing provider manifest; `best-of-n` and
`select-only` remain exported entries. The
[experiment recipe](../../../experiments/orc_vs_single_call/README.md) owns the
source/input/manifests needed to use it.

`tests/test_workflow_evaluated_consumers.py::test_public_best_of_n_runs_isolated_candidates_serially_then_the_judge`
now checks the canonical source at 2.35 without target substitution, through
CLI/provider boundaries and deterministic external transports: isolated
candidate edits, ordered requests, typed selection/report output, judge
dependencies, interruption after candidate commits and completed resume
without dispatch. The old-route comparison is migration evidence, not a
requirement to retain an executable old oracle after deletion.

The [execution closeout](../2026-10-13-best-of-n-and-executor-retirement-closeout.md)
owns exact receipts and qualification. This design does not claim arbitrary
N, live-provider behavior, parallelism or universal old-run compatibility.
Historical inputs/results and accepted comparison receipts remain preserved;
ongoing tests use canonical evaluated sources.

| Alternative | Result | Disposition |
| --- | --- | --- |
| Wait for all Phase 4/5 capabilities, then migrate everything | Preserves the largest historical surface; postpones removal indefinitely | Reject as the default dependency |
| Serial best of N now; keep only named consumers; retire exclusive infrastructure | Uses demonstrated behavior and gives deletion a finite gate | Selected |
| Add a legacy backend or compatibility adapter | Keeps the old runtime and another supported door | Reject |

## 5. Finite Consumer Dispositions

Freeze an exact path/caller list from tracked source, the route-readiness registry,
stdlib/import graphs, advertised Python exports, documentation recipes and
repository-owned runs. Registry rows alone are incomplete. Each path receives
`migrate`, `retain evaluated/shared`, `retire executable`, or `read-only history`;
an unresolved row blocks cutoff rather than creating an open-ended port project.

| Consumer / owner | Selected disposition |
| --- | --- |
| Canonical `best_of_n.orc`, sibling `.providers.json`, experiment README and consumer tests | Migrate serial source to 2.35; preserve both exported entries and current policy |
| `workflows/examples/{plan_review_execute,improve_experiment_proposal}.orc` and their input directories | Retain delivered evaluated contracts at 2.35/2.36; regression witnesses |
| Canonical `reviewed_change.orc` and `workflows/library/control/direct_task.orc` | Migrate admitted current behavior with existing consumer evidence; do not add W3 or new effects merely for uniformity |
| `workflows/library/verified_iteration_drain/drain.orc`, migration manifests and scripts | Use the bounded canonical 2.35 migration and `test_workflow_evaluated_verified_drain.py`; preserve history/phase/artifact behavior |
| `workflows/library/generic_run_watchdog/watchdog.orc` and its launch recipes | Retire as an executable consumer; the user does not require a watchdog port. Retire its primary routing and exclusive tests/assets explicitly; keep shared read-only probing where still used |
| `tracked_design_phase.orc`, `tracked_plan_phase.orc`, `design_plan_impl_implementation_phase.orc`, their importers and stdlib | Preserve useful reusable contracts; enumerate actual executable roots separately. Retire unused roots, migrate only selected used roots and required minimal dependencies; deprecation of Design Delta does not by itself retire these modules |
| Remaining `workflows/**/*.orc`, `experiments/**/*.orc`, fixtures, Python callers and advertised examples | Apply the frozen inventory's selected dispositions before cutoff. Retire unused roots as historical references; every maintained exception must name its caller, required contract, and migration evidence |
| Historical `run_best_of_n_trial.sh` / `run_single_call.sh` | Keep labeled experiment provenance or remove obsolete launch guidance; do not revive their missing machine-specific variant files as a new runner |
| Generated `prompt_scaffold_render.py::_render_run_orc`, `prompt run`/`import`, and `omp_assets/infer-output-contract.orc` | Owner selected retirement from the new package; retain exact previous release/environment recovery only where evidenced for a family; retire inference if no other caller remains. Retain native `prompt resume [--in-place]` and its historical scaffold-byte verification |
