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
| 0 finite inventory | In progress | 542 tracked sources and recursive repository run census recorded; ES/research retirement selected; final row qualification pending |
| 1 canonical serial best of N | Bounded implementation accepted | Four public cases and recovery census PASS; independent contract and quality PASS; final integrated campaign remains Task 5 |
| 2 other selected consumers | Pending | Maintain evaluated examples/REPL/chess; classify advertised older roots and shared libraries |
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
`orchestrator/omp_assets/infer-output-contract.orc`, also migrates to 2.35.
Older module headers remain valid imported typed contracts; only executable
entry targets through 2.34 are selected for retirement after R.

### Preserved ES / Research Snapshot

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
