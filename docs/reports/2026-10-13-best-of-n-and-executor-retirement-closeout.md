# Best Of N Migration And Executor Retirement Execution

**Status:** in progress; no executable cutoff or code deletion delivered.
**Selection:** owner “proceed”, 2026-10-13, following the independently reviewed
[design](../design/workflow_lisp_executor_retirement.md) and
[plan](../plans/2026-10-13-best-of-n-and-executor-retirement-plan.md).

## Scope And Working State

The selected order migrates canonical serial best of N to 2.35 independently
of full Phase 5. Bounded existing 2.37 support stays. Watchdog needs no port;
retire its exclusive executable routing with the qualified cutoff. Keep
shared performers, useful typed imports and all original run data.
New `prompt run`/`prompt import` executions retire with the complete previous
release/environment retained; native `prompt resume [--in-place]` stays.

Execution worktree: `.worktrees/orc-consolidation-20261012` (W). Evidence:
`.worktrees/orc-consolidation-evidence-20261012` (E). Baseline is `23eb9c97`,
which adds the maintained evaluated chess experiment after the draft commit.
A detached complete baseline checkout is retained at
`.worktrees/orc-retirement-baseline-20261013`; this alone does not prove
historical package-pin compatibility or interrupted recovery.
Concurrent dirty main changes remain outside W and are preserved.

## Task Status

| Task | State | Evidence / remaining work |
| --- | --- | --- |
| 0 finite inventory | Accepted | Finite source/generated-consumer/run dispositions recorded; independent inventory review PASS; implementation qualification remains Task 3 |
| 1 canonical serial best of N | Bounded implementation accepted | Four public cases and recovery census PASS; independent contract and quality PASS; final integrated campaign remains Task 5 |
| 2 other selected consumers | Bounded migration accepted | Four canonical consumers and independent contract/quality PASS; final retained-branch and retirement checks remain before R |
| 3 cutoff / gate R | Pending | No current-package refusal or historical recovery claim yet |
| 4 physical deletion | Pending | No old executor/lowering deleted |
| 5 final verification / delivery | Pending | Fresh baseline full RED recorded; final affected/full and independent review required |

## Finite Consumer Decisions

The census found active main work beyond the initial maintained list:
`scripts/experiments/es/controller.py` calls the target-2.25 trial SDK;
`experiments/orc_research_demo/` has trial entries and direct executor/helper
imports, including untracked source and dirty callers. The owner explicitly selected “Retirar del paquete nuevo y conservar versión
anterior” on 2026-10-13. Their executable support and trial SDK retire together;
no trial port is required. Original code and data remain preserved.

The selected maintained set also migrates `experiments/mlevolve_pair/search_compact.orc`
to 2.35 using its existing evaluated public proof. Its original `search.orc`
is already an intentionally refused policy specimen and remains historical.
The repository-task-pilot study and its conventional coordinator retain source
provenance with executable retirement; they are not selected maintained pipelines. Newly tracked `experiments/agent_chess/chess.orc` and maintained
`design_review_execute.orc` / `orc_repl_feature` remain evaluated consumers.
The exact frozen census is `E/retirement-consumer-census.{json,md}`: 542
tracked `.orc` sources (45 authored, 486 fixtures, six stdlib, one installed
asset, four historical), 63 registry rows, 1,076 static Python import rows and
786 executable API-call occurrences. Fixture history is not permission to
delete tests of retained parser/type/analysis or evaluated behavior. Those
assertions must remain under their typed interface or migrate to the evaluated
entry; only exclusively retired execution assertions leave the suite.

The core `prompt --output` entry,
`orchestrator/omp_assets/infer-output-contract.orc`, retires with its sole
prompt run/import caller; its attempted migration was reverted. Migrating this asset alone would
not preserve the generated prompt CLI contract selected for retirement below.
Older module headers remain valid imported typed contracts; only executable
entry targets through 2.34 are selected for retirement after R.

### Selected Maintained Roots

| Exact source | Selected action |
| --- | --- |
| `experiments/orc_vs_single_call/workflows/best_of_n.orc` | Canonical serial 2.35 accepted under Task 1 |
| `experiments/orc_vs_single_call/workflows/reviewed_change.orc` | Migrate existing review/revise behavior to 2.35 |
| `workflows/library/control/direct_task.orc` | Migrate existing provider boundary to 2.35 |
| `workflows/library/verified_iteration_drain/drain.orc` | Migrate bounded existing drain/history behavior to 2.35 |
| `experiments/mlevolve_pair/search_compact.orc` | Migrate existing compact search to 2.35 |
| `workflows/examples/plan_review_execute.orc` | Retain evaluated 2.35 |
| `workflows/examples/design_review_execute.orc` | Retain evaluated 2.35 |
| `experiments/orc_repl_feature/repl_feature.orc` | Retain evaluated 2.35 |
| `workflows/examples/improve_experiment_proposal.orc` | Retain evaluated 2.36 |
| `experiments/agent_chess/chess.orc` | Retain evaluated 2.36 |

The census records every other tracked source's selected shared/import or
historical disposition. `E/retirement-test-dispositions.{md,json}` enumerates
389 impacted test/helper modules in thirteen owner groups. It is an impact
inventory, not blanket approval to delete mixed suites. Only assertions about
retired executable contracts disappear; retained semantics keep independent
expected values and public/typed evidence without an old executor as oracle.

### Generated Prompt Consumer — Retirement Selected

Review found an executable consumer absent from the tracked `.orc` roots:
`prompt_scaffold_render.py::_render_run_orc` generates target 2.27 with
`:session-artifact omp_session` for `prompt run` default/exact/inferred contract
modes, `--scaffold` rerun and both `prompt import` branches (including
`--reuse-run-contract`). Its scaffold compiler also consumes flat `lowered_workflows`.
`E/retirement-prompt-generated-review-probe.json` confirms that changing the
header alone produces `closed_program_gap`; no provider was launched.

The owner explicitly selected “Retirar run/import y conservar versión anterior”
on 2026-10-13. Retire these new executions from the new package and preserve them
in `E/retirement-retained-release`; no evaluated session port or sidecar metadata
is selected. Task 0's contract choice is resolved; implementation and R remain
pending. Tasks 3–4 must prove run/import refusal before scaffold/run/session
writes or effects and preserve original data.

`prompt resume [--in-place]` remains the native TTY bridge with its existing
pins, isolation, lineage and continuation publication. `verify_private_scaffold`
and `verify_captured_occupant` verify bytes/manifests/links without compilation
or `WorkflowExecutor`. Keep `_scaffold_files` and the historical 2.27 renderer
for deterministic byte verification; remove eager compiler dependencies and
`compile_check`/`derive_compiled_contract` only when unused. Native resume mutates
session journals and requires smoke/import-closure evidence in both modes;
it does not resume retired workflows or establish universal old-run recovery.

`E/retirement-inventory-review.md` records final Task 0 PASS after correcting
the omitted generated consumer and fourteen stale decision labels. The original
findings and pre-review JSON remain preserved. This accepts the finite scope,
not the still-pending refusal, native-session or recovery checks of R.

### Preserved Complete Release / Consumer Snapshot

`E/retirement-retained-release` is a complete `23eb9c97` checkout overlaid with
181 current code, test and asset files (6,456,961 bytes), including dirty and
untracked consumer work. `E/retirement-retained-consumers.json` records paths
and hashes; a second source read found no changes during capture. The
interpreter is `/home/ollie/miniconda3/bin/python3.13`; its version and
`E/retirement-retained-python-freeze.txt` record the current environment.
Original research evidence/development directories and run roots stay in place.

`E/retirement-retained-import-check.json` verifies the executor, trial SDK, ES
controller and both research adapters load from that checkout. No providers
were launched. This proves preserved import availability, not interrupted
recovery, relocation, or continued availability of remote services.

## Baseline And Verification

`E/retirement-baseline-loc.json` measures tracked Python physical lines,
including comments/blanks and excluding generated/untracked files:

| Scope | Files | Lines at 23eb9c97 |
| --- | ---: | ---: |
| Production (`orchestrator`) | 524 | 358,531 |
| Tests | 704 | 599,251 |

The fresh isolated baseline best-of-N selector passes **2 cases** (19
deselected), **30.00 s**, with exact command/exit in
`E/retirement-baseline-narrow.{json,log,xml}`. The fresh full campaign at
`23eb9c97` completed under `pytest -q -n 16 --dist=worksteal`: **217 failed,
23,862 passed, 36 skipped, 170 xfailed**, exit 1, 1,087.84 s pytest time
(1,089.91 s runner time). `E/retirement-baseline-full.{json,log,xml}` and
`E/retirement-baseline-failures.json` record the command, raw outcome, each
failed node ID and traceback. This is the comparable pre-retirement baseline;
the historical `bfd0f324` 275-failure campaign remains separate. A retained
evaluated-program growth-selector failure is included and must be accounted
for during consumer migration; no full GREEN claim is made.

`E/retirement-run-census.json` records a read-only recursive scan of repository
`state.json` and `run.json` headers, hashes and paths, including nested runs
outside the top-level `.orchestrate/`. It excludes git metadata, worktrees,
node_modules and virtualenvs, and does not follow directory symlinks. The
initial scan found 5,729 header/state files in 5,583 parent directories; these
are files/roots, not assertions of complete runs or liveness. No run was
resumed, mutated or deleted by the census. Recovery claims need separate
source/assets/pins and representative interrupted checks.

Run-file dispositions are recorded per path in the census: 5,256 schema-2.1
files become read-only history after R (4,283 without a replay profile and
973 `derived_pure_replay.v1`); 431 schema-3.0 files retain evaluated authority.
The remaining 42 files are completed synthetic spike children, not production
persistence profiles. These counts include paired headers/views and snapshots,
so must not be presented as distinct run counts. Old recovery is supported
only where exact retained source/assets/pins and evidence exist; no universal
recovery promise follows from preserving a checkout.

## Task 1 — Canonical Serial Best Of N

The canonical source now declares 2.35; its body and provider manifests are
unchanged. The exact old source and expected selection live under
`tests/fixtures/workflow_lisp/best_of_n_legacy/` as transitional historical
parity evidence. Current tests copy canonical bytes without header substitution;
recovery source preparation follows the same rule. The README supplies isolated
candidate prerequisites, manifests and public lifecycle commands.

| Receipt in E | Outcome |
| --- | --- |
| `best-of-n-canonical-final.{json,log,xml}` | 4 passed, 19 deselected, 56.13 s; compile/closed profile, dry-run, interrupted and completed resume/report, four candidates and select-only |
| `recovery-source-census.{json,log,xml}` | 1 passed, 8.43 s; public best-of-N recovery census |
| `best-of-n-final-collect.{json,log,xml}` | 35/150 collected, 115 deselected, 5.17 s; 4 consumer and 31 recovery cases |
| `best-of-n-readme-external-source-probe.json` | Public compile from a separate workspace with absolute canonical source/manifest, exit 0 |
| `best-of-n-contract-lifecycle-artifacts.json` | Six request logs and 58 checked artifact hashes from the final lifecycle evidence |
| `best-of-n-canonical-contract-review.md` | Final PASS; initial missing CLI import and stale recovery-fixture findings corrected |
| `best-of-n-canonical-quality-review.md` | PASS; caller coherence, semantic checks and artifact hashes inspected independently |

The initial target assertion RED, missing `_cli` import failures and recovery
collection RED are retained in their receipts. No test expectation was weakened
to hide those failures. Candidate lineage allows dependencies on earlier
candidates only; the judge depends on all candidate outcomes in input order.
No committed provider is dispatched again during completed resume.

This is serial deterministic public-route evidence, not live-model quality,
parallel qualification, or executor-retirement acceptance. Provider policy
and delivery code did not change, so no new live-model campaign was needed.

## Task 2 — Other Canonical Consumers

`reviewed_change`, `direct_task`, the verified drain and compact search now
declare 2.35. Their bodies are unchanged; command manifests declare the files
already used by their implementations. Current lifecycle tests use canonical
bytes, while exact older sources remain separate historical fixtures. Registry
and README routing follow the canonical sources. The incomplete inference
migration was reverted after selection of prompt run/import retirement.

| Receipt in E | Outcome |
| --- | --- |
| `retained-source-preservation.json` | Four exact historical snapshots; canonical bodies differ only in their target header |
| `retained-reviewed-green.{json,log,xml}` | 10 passed; reviewed-change outcomes and public interrupted/completed resume |
| `retained-drain-search-narrow.{json,log,xml}` | 11 passed; drain history/resume, compact-search budgets and coupled contracts |
| `retained-affected.{json,log,xml}` | 823 cases: 742 passed, 9 failed, 72 errors; initial affected campaign |
| `retained-spike-correction.{json,log,xml}` | 85 passed after historical spike callers use their exact old sources |
| `retained-manifest-correction.{json,log,xml}` | 1 passed after the manifest assertion includes the declared command closure |
| `retained-four-final-collect.{json,log,xml}` | 115 cases collected |
| `retained-affected-dispositions.json` | All 81 initial failures/errors matched by node ID: 80 corrected and verified, one pre-existing growth-observer failure retained |
| `retained-consumers-contract-review.md` | Bounded PASS for the four migrations |
| `retained-es-import-green.{json,log,xml}` / `retained-es-collect.{json,log,xml}` | 6 passed; 58 cases collected after three historical ES helpers use the exact 2.23 direct-task snapshot |
| `retained-es-affected.{json,log,xml}` / `retained-es-affected-dispositions.json` | 51 passed, 7 failed; all seven node IDs and recorded launcher hashes match the baseline mismatch |
| `retained-consumers-quality-review.md` | Final bounded PASS; original ES import-direction finding and its correction preserved |

The quality review found a new ES test dependency missed by the initial affected
selection: target-2.25 arms could no longer import canonical direct-task at 2.35.
Three historical test helpers now use its exact 2.23 snapshot. This preserves
their old assertions until selected ES retirement; it does not port ES or claim
that its current launch path remains supported after cutoff.

The existing growth-selector failure observes an extra `None` event lane and
also fails at baseline `23eb9c97`; its assertions are unchanged. The full suite
has not been rerun for this bounded cut. Drain BLOCKED, STALLED and exhaustion
still have historical-route evidence only: move those assertions to the
evaluated public path before deleting their historical test/runtime. This is
not acceptance of gate R or of physical executor retirement.

## Shared Compiler Preparation — First Batch

The WCC value reconstructors and loop-cardinality analysis, procedure private
names/local types and pure-expression classifier now live in their existing
semantic owners. Prompt descriptors use the canonical descriptor through the
existing lazy import barrier. Definitions were moved once and callers updated;
temporary flat callers still work. No executor or emitter is retired by this
batch, and the type-only lowering context remains pending final deletion.

`E/shared-compiler-helpers-implementation.md` records the exact definitions and
callers. The affected and W3 receipts contain 473 and 32 passing executions
(overlapping selectors), including the public evaluated command CLI smoke.
The follow-up spike receipt contains six passing cases. Independent contract
and quality reviews are PASS in `E/shared-compiler-helpers-{contract,quality}-review.md`.
Quality review also checked 25 imports in fresh processes.

The initial eager-descriptor import cycle was corrected by preserving the
existing lazy helper. Contract review found an overlooked historical spike
import and two unused re-export imports; all were corrected, with the spike's
same fresh-process import reproduced RED then GREEN. Full-suite verification
remains pending the retirement delivery; the recorded RED baseline is unchanged.

## Shared Command And Procedure Analysis — A3a

Binding facts, procedure selection and match analysis now belong to
`procedure_specialization.py`; `LowerableProcedureCall` belongs to
`procedures.py`. Command/control analysis belongs to `closed/command_templates.py`.
The emptied control-summary and transport-decision modules were removed.
Existing flat match boundaries still construct their terminal objects from the
shared mappings; executable emission and target admission remain unchanged.

`E/command-analysis-extraction-implementation.md` and its ownership JSON record
the moved definitions and remaining flat-only branches. Eight pre-existing
homonyms with different flat behavior remain for deletion, not unification.
The contract review's unused, locally shadowed import was removed without
changing the local implementation; fresh import and diff checks passed.

The affected campaign recorded **995 passed, 2 failed**. One failure was an
assertion of the former helper owner, corrected and verified by five focused
passing cases. Thus 996 distinct affected cases have passing evidence; the
remaining WCC identity failure is pre-existing. Full observations generated
from `cddd0ab8` and the changed code are byte-identical, SHA-256
`ce57b10b24b9ac225d1548147d44cc1aaa2bd5c79a0947c082477c406bf006d4`.
The golden assertion remains unchanged. Collection found 370 cases; twelve
fresh-process imports and public compile/read-back also passed. Exact argv,
exits and outputs are in `E/command-analysis-extraction-*` receipts.

Independent contract and quality reviews are PASS in
`E/command-analysis-extraction-{contract,quality}-review.md`. They certify this
extraction, not all retained flat behavior or gate R. The next candidate first
implements public cutoff refusals with the backend present, then separates
typed imports/LSP from flat bundle creation. Constant serializer pruning moves
with physical deletion after R; it is not an extra preparatory migration.
