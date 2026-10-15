# Workflow Lisp Consolidation: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_consolidation.md](../../design/workflow_lisp_consolidation.md).

## Migration And Deletion Contract

Inventory the maintained workflows, library APIs, CLI/Python callers, fixtures,
readers and supported run families in the companion plan. The owner bounded
retained-run inventory to this repository, including nested experiment/project
run roots. The initial inventory covers `.orchestrate/runs` and
`.orchestrate/archive` only; it does not complete that repository scope.
Preserve original data. Generated pre-change compatibility fixtures are separate
evidence, not an inventory of existing runs.
Each feature needs a named maintained consumer or an explicit retirement
decision. Historical features need not all be ported to complete consolidation.

| Surface | Migration / acceptance condition | Deletion or retained boundary |
| --- | --- | --- |
| Closed loader/checker imports | Compiler, runtime, readers and tests consume one extracted owner; wire conformance passes | Remove displaced definitions and temporary import aliases |
| Provider IO and prompt utilities | Imported-source, bound-procedure and file-handoff cases preserve selection and evidence | Delete compiler dependencies from interpreter paths, retain compiler factories |
| Maintained workflows and stdlib callers | Public run/resume evidence for each selected consumer; the serial retirement amendment does not depend on full Phase 5 | Remove source forwarding and position-repair machinery made unnecessary |
| Old flat new-run route | Maintained set migrated; explicit owner selection of supported targets and cutover | Disable old new-run admission; delete lowering only after the old-run support gate also passes |
| Old executable run families | Decision 8 records a tested recovery or explicit retirement disposition per family | Remove their executor/replay/state-translation code only when support ends |
| Historical read access | Separate report/archive contract and fixtures accepted | Keep a small read-only reader if required; this does not retain execution authority |
| Tests and fixtures | Replace internal-path coupling with retained contract/behavior evidence | Delete only tests whose contracts are explicitly retired, not tests that merely import moved code |

For each supported old-run family, record target/profile, artifact and source
requirements, an exact retained release and environment, recoverability proof,
support owner and retention policy. The selected retirement contract retains
recovery only for families with exact-release evidence; other families have
explicitly retired resumability. There is no automatic 30-day expiry.
Test an interrupted representative before promising recovery,
including required command closures, source assets and coordinator state.
An unrecoverable family needs explicit disposition, not an assumed upgrade.

Archived data and read-only access have their own retention decision. Removing
an executor does not authorize deleting run directories or forensic artifacts.
Before cutover, rollback selects the old supported release and original runs;
do not convert or overwrite them. After retirement, rollback cannot be promised
without the retained release/environment and its required inputs.
