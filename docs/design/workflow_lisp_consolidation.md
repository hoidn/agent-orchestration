# Workflow Lisp Consolidation

## Metadata

- **Status:** bounded extraction Tasks 0–4/Gates A–D accepted at `bfd0f324`, with reviewed RED full-suite dispositions. Migration, cutover and deletion (Tasks 5–7) remain conditional on the parent gates.
- **Kind:** architecture and migration.
- **Owner:** Workflow Lisp frontend and runtime maintainers; repository owner selects retirement policy.
- **Reviewers:** independent design and implementation reviewers.
- **Created / last material update:** 2026-10-12.
- **Implementation target:** none assigned. Existing targets 2.35 and 2.36 retain their contracts.
- **Companion plan:** [consolidation plan](../plans/2026-10-12-workflow-lisp-consolidation-plan.md).
- **Execution evidence:** [consolidation closeout](../reports/2026-10-12-workflow-lisp-consolidation-closeout.md); records bounded extraction acceptance, original RED receipts and remaining gates.

## Summary And Decision

Make evaluated execution the eventual sole route for new workflow runs, after
migrating maintained consumers and explicitly disposing of supported old runs.
Extract the existing closed-program contract from compiler ownership so the
compiler and interpreter consume one loader and one semantic checker. Delete
displaced execution machinery when its last supported use ends.

This is consolidation of the accepted [evaluated-execution design](workflow_lisp_evaluated_execution.md),
not a replacement language or runtime. Keep authored forms, typed boundaries,
performers, coordinator protocols and useful stdlib abstractions. The existing
internal `WccPerform` and closed `perform` node are sufficient; introduce no
authored `defeffect` or `perform`, effect plugin registry, or second IR.

The tradeoff is explicit: retiring old execution paths makes arbitrary old-run
recovery on the newest package harder. Recovery must use a tested retained
release or a separately accepted migration, not indefinite compatibility code.

## Authority And Scope

Normative owners remain [State](../../specs/state.md#evaluated-execution-persistence-profile-target-235),
[CLI](../../specs/cli.md#evaluated-execution-target-235),
[Step IO](../../specs/io.md#evaluated-command-and-provider-io-target-235) and
[versioning](../../specs/versioning.md). The [frontend specification](workflow_lisp_frontend_specification.md)
owns authored contracts; the [capability matrix](../capability_status_matrix.md)
distinguishes implemented surfaces from proposals. The evaluated-execution
design owns effects, identities, memo replay and coordinator settlement.

The [existing delivery plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
owns ordering: Phase 4 supplies consumer-required capabilities, Phase 5 owns
parallel map, Phase 6b migrates maintained consumers and Phase 7 retires routes
under decision 8. The owner requested execution of the plan on 2026-10-12;
bounded extraction Tasks 0–4 are accepted in an isolated worktree. Tasks 5–7 retain
that sequence and its capability, consumer and
cutoff gates. The owner separately selected Phase 5 D1 target 2.37 on
2026-10-12; parallel-map implementation and qualification remain pending. Preserve
currently supported behavior and APIs throughout extraction.

Excluded: Rust, licensing or packaging-product changes, a Python frontend,
checked-evaluation expansion, new language features, a general scheduler and
redesign of already shared provider, command, resource or run-reference services.

## Problem And Alternatives

Before extraction, the evaluated route already had the desired execution model,
but its runtime imported `workflow_lisp.closed` and compiler-owned prompt utilities. Meanwhile,
older targets retain flat lowering, replay and state translation. Renaming
directories alone removes neither dependency nor execution path; immediately
deleting old code would remove supported capabilities and recovery.

| Option | Benefit | Cost / disposition |
| --- | --- | --- |
| Leave both routes and ownership unchanged | Least immediate migration | Permanent duplicate maintenance; rejected as the end state |
| Extract the existing contract, migrate consumers, retire old routes | One checked representation and eventual execution route | Requires consumer and run-family evidence; recommended |
| Rewrite around a generic effects API or a new runtime | Freedom to redesign everything | New semantics, adapters and compatibility obligations; outside scope |

Success is fewer authoritative routes and owners with preserved behavior.
Line counts, file counts, import counts and test duration are observations to
baseline after inventory, not promised savings or calendar estimates.

## Ownership And Target Topology

```text
CLI compile / run / resume preparation -> existing Workflow Lisp compiler
                                            | closed artifact + explicit IO selections
                                            v
                         contracts/closed_program (one loader/checker)
                                            |
                                            v
                          workflow/evaluated (evaluation and memo)
                                            |
                              existing performers / coordinators
```

The CLI remains compiler-owning: public resume rebuilds and compares before
execution. Parent evaluation, read-only artifact inspection and coordinator
recovery must not import the compiler, including through deferred imports.
The explicit run-reference child compile entry remains compiler-owning at its
existing process boundary; this adds no service or protocol. Source rebuild
remains required, and serialized programs do not contain physical IO roots.

| Responsibility | Pre-extraction owner | Extracted owner / disposition |
| --- | --- | --- |
| Strict artifact loading, canonical serialization, semantic digest | `workflow_lisp/closed/program.py` | `contracts/closed_program/program.py`; move existing implementation |
| Source-free semantic checker and its wire-only helpers | `closed/check.py`, `command_check.py`, parts of `names.py` and `sites.py` | Small `contracts/closed_program/` package; compiler and runtime use the same implementation |
| Shared target admission facts | `workflow_lisp/syntax.py`, `closed/__init__.py` | `contracts/closed_program/targets.py`; syntax consumes the same facts, without a second target registry |
| Source reading, types, specialization, WCC, artifact construction | `workflow_lisp/`, including mixed helpers in `closed/program.py` and `names.py` | Stay compiler-owned; keep typed configuration projection out of the contract package |
| Provider IO carriers and checked binding | `closed/frontend.py` | `workflow/evaluated/provider_io.py`; retain owner/frame/site/digest and reference-slot validation |
| Provider IO selection from typed programs or imported bundles | `closed/frontend.py`, `closed/build.py`, `closed/artifact.py` | Compiler preparation; construct runtime carriers before crossing the boundary |
| Typed prompt rendering used by both routes | `workflow_lisp/typed_prompt_inputs.py` | `workflow/typed_prompt_inputs.py`; keep compiler report/bundle traversal in the compiler |
| Evaluation, memo, views and authority loading | `workflow/evaluated/` | Keep existing owners; replace compiler imports with the extracted contracts |
| Compile/rebuild/bind/publish | `cli/commands/{compile,run,resume,evaluated}.py` | Keep orchestration and compiler access here |
| Command/provider execution and child settlement | Existing performers, `providers/`, `workflow/run_ref/` | Reuse and preserve; consolidate caller adapters only after parity |
| Shared run-reference wire validation | Helpers/constants in `run_ref/child.py`, `closed_path.py` and `path_compile.py` used by parent runtime | `workflow/run_ref/wire.py` and `path_contracts.py`; executable child/compiler entries consume them too; public refusal class import remains a re-export |
| Normalized program identity | `workflow_lisp/diagnostics.py::build_normalized_program_identity` | `contracts/program_identity.py`; one implementation used by existing consumers. Package hashing and `compute_compiler_runtime_identity` remain in `workflow/run_ref/contracts.py` |

The extraction includes lazy paths formerly reaching child executable helpers:
`run_ref/runtime.py` now uses `wire.py` for request/result/diagnostic checks,
and `evaluated_child.py` uses source-free revision/path-fact owners. Keep these
checks shared with executable children; do not whitelist hidden compiler imports
in the parent.
`RunRefStepConfig` and `StepCommonConfig` from `workflow/executable_ir.py` remain
shared dependencies of evaluated run references. Retain them until their
contracts and callers have moved; retiring flat execution cannot delete that
whole module while maintained run references still depend on it.

Keep the package dependency-light, not necessarily stdlib-only: existing
source-free descriptor, pure-expression and run-reference contracts remain
shared. Split compiler-dependent helpers rather than copying them. Move any
checker-used type-name rule to the existing shared descriptor owner. Do not
relocate all of `closed/`, export compiler factories from the new package, or
leave forwarding modules after their supported callers have migrated.

Compiler preparation in `closed/frontend.py` uses
`_workflow_io_reader_from_program` and `_workflow_io_reader_from_bundle` to
resolve recursive imported selections and bundle provenance. It supplies
`workflow/evaluated/provider_io.py::WorkflowIOReader` with resolved source
owners and imported readers; runtime `select` needs no compiler bundle.
`ProviderIOContext.bind` still checks the complete call mapping, reference slots,
sites, entry and program digest. Missing or mismatched bindings fail closed.
Asset prompts retain their selected source owner's root; input-file prompts and
dependency snapshots retain workspace ownership. Read freshness and content
evidence stay at the existing provider boundary. No new durable IO sidecar is
introduced merely to make the dependency graph look clean.

## Contracts, Compatibility And Failure Behavior

1. **One checked artifact.** Retain `ClosedProgram.from_artifact` and its
   semantic checker, including strict JSON, descriptors, nominal identities,
   call signatures, site-table consistency and diagnostics. A schema-only JSON
   validator cannot replace it. Construction checks are not an alternate loader.
2. **Stable formats.** Initially preserve `workflow-lisp/closed-program/1`,
   `table/1`, the evaluated header/profile, memo wire and coordinator ledgers.
   Module moves must preserve canonical compiled bytes for identical identity
   inputs, semantic program digests and the documented supported resume routes.
3. **Distinct identities.** Effect identity remains definition site plus
   activation path, independent of inputs. Input digest, semantic program digest,
   artifact bytes and compiler/runtime package identity remain distinct. Equal
   inputs at two sites or loop activations do not merge effects.
4. **Honest package pins.** Installed package bytes contribute to existing
   compiler/runtime identities. Moving modules can truthfully change those pins
   and dependent artifacts. Record real-pin differences separately from
   fixed-identity byte comparisons; never normalize them away or bypass resume
   checks. Keep recovery on the recorded supported release where required.
5. **Explicit format evolution.** Any needed representation, identity or target
   change is a separate owner-selected migration with its own old-run disposition.
   Extraction does not silently upgrade runs or select a new target.
6. **Effect behavior.** Preserve command closures, interpreter pins, typed
   inputs/results, prompt assembly, output validation, artifact freshness and
   lineage. Preserve phase context and phase targets for consumers using them.
   A memo value does not replace produced files or prove what a provider read.
7. **Recovery.** Preserve writer locks, journal validation and suffix invalidation.
   An uncancelled committed effect is never redispatched. Run references and other admitted
   coordinators retain `prepare` → memo `committed` → `settle`, with `reconcile`
   after interruption; repeated activation has its own identity and ledger visit.
8. **Refusals.** Unsupported classes remain explicit build refusals, not fallback
   to the flat executor. Tampered artifacts, stale inputs, mismatched IO owners
   and incompatible resume authority refuse before effects under existing rules.

The normal user flow remains `compile`, `run`, `resume`, `report` and
`invalidate`, with existing frontend flags and diagnostics. A program needing
an unavailable capability waits for its consumer-owned port or is explicitly
retired. New-run route selection changes only at the approved cutover; no new
user-facing execution selector is introduced.

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
| Maintained workflows and stdlib callers | Phase 6b public run/resume evidence for each consumer's required Phase 4/5 capabilities | Remove source forwarding and position-repair machinery made unnecessary |
| Old flat new-run route | Maintained set migrated; explicit owner selection of supported targets and cutover | Disable old new-run admission; delete lowering only after the old-run support gate also passes |
| Old executable run families | Decision 8 records a tested recovery or explicit retirement disposition per family | Remove their executor/replay/state-translation code only when support ends |
| Historical read access | Separate report/archive contract and fixtures accepted | Keep a small read-only reader if required; this does not retain execution authority |
| Tests and fixtures | Replace internal-path coupling with retained contract/behavior evidence | Delete only tests whose contracts are explicitly retired, not tests that merely import moved code |

For each supported old-run family, record target/profile, artifact and source
requirements, an exact retained release and environment, recoverability proof,
support owner and retention policy. Proposed default: recovery through that
pinned release until the owner explicitly retires the family; no automatic
30-day expiry. Test an interrupted representative before promising recovery,
including required command closures, source assets and coordinator state.
An unrecoverable family needs explicit disposition, not an assumed upgrade.

Archived data and read-only access have their own retention decision. Removing
an executor does not authorize deleting run directories or forensic artifacts.
Before cutover, rollback selects the old supported release and original runs;
do not convert or overwrite them. After retirement, rollback cannot be promised
without the retained release/environment and its required inputs.

## Evidence, Acceptance And Stop Criteria

Task 1 now proves the bounded compiler-independent load/check/evaluation and
parent validation/settle/reconcile boundary with fresh compiler-blocked processes,
including lazy/failure paths. Real public preparation and child compilation run
outside the blocker. Independent review and coordinator acceptance closed
Tasks 0–4/Gates A–D at `bfd0f324`; the closeout records all nine isolation cases
passing together, integrated lifecycle/retained-run/corpus evidence and reviewed
RED full-suite dispositions. This bounded extraction acceptance leaves the
migration, cutover and retirement gates unchanged.

| Scenario through the public boundary | Required result and evidence |
| --- | --- |
| Compile a maintained command/provider fixture, run, externally kill after a committed effect, resume, read report, invalidate a permitted suffix, resume again | Same terminal value and declared artifacts; no committed redispatch before invalidation; required suffix reruns only; real CLI/compiler/filesystem/memo, deterministic provider substitute at the external transport |
| Imported prompt assets plus a bound procedure select distinct source owners | Exact selected bytes and dependency evidence before/after extraction; wrong owner or changed required bytes refuse before dispatch; exercise the ordinary public preparation path |
| Compile and load valid artifacts and independently tampered type/site/call/target cases | Identical canonical outputs under fixed identity inputs and equivalent refusals; verify semantic checks rather than digest mismatch alone |
| Kill a supported coordinator at each commit gap, resume from retained state | Existing discard/retry before memo commit and reconcile after it; no duplicate committed child; real child/ledger boundary |
| Recover a supported old-family interrupted fixture under its pinned release | Same documented result, artifacts and committed-effect behavior; current read-only access satisfies its separate contract |
| Attempt an unsupported old new-run target after approved cutover | Explicit retirement diagnostic and recovery guidance; no silent target conversion or legacy fallback |

Reuse the closed-artifact, evaluated CLI, provider IO, run-reference settlement,
reader and invalidation owner suites named by the governing contracts. Update
imports without discarding their assertions. Add behavioral/conformance cases
for uncovered seams; no literal prompt-text tests or giant snapshot replacement.
Each execution change requires an orchestrator/demo smoke and public integration
check; start with narrow selectors and collect changed test modules. Broader
required suites use the repository's tmux and parallel pytest policy. Real
provider qualification is retained where the consumer's gate requires it;
deterministic transports do not establish live-provider parity.

Acceptance requires the named maintained set, old-run dispositions, one checker,
compiler-free interpreter imports, public lifecycle evidence and actual deletion
of displaced paths. Record net code and dependency changes with a reproducible
scope; there is no fixed line-count or runtime-speed promise. Stop and revise if
extraction requires a second validator/IR, weakens authority checks, loses source
ownership, changes canonical semantics or leaves an unowned compatibility path.

## Operations, Documentation And Open Decisions

No new credentials or execution authority are introduced. Retained runs and
provider evidence keep existing access controls and data sensitivity. Extraction
must not expand file access; shutdown, locking and recovery remain contract
obligations. Performance changes are measured on existing public fixtures;
unexpected regressions need disposition before cutover, not assumed savings.

On acceptance and each delivered cut, update the frontend/evaluated design,
affected normative owners, drafting and lifecycle guides, capability matrix,
design index, examples and existing delivery plan. Keep historical evidence
linked with its original scope. The companion plan owns task order and receipts.

Material decisions remain explicit: the plan selects an extraction inventory
that preserves all currently supported contracts/APIs, with a bounded
qualification set. Broader migration coverage, supported old-run family
dispositions, recovery retention/cutoff and new-run target retirement remain
Tasks 5–6 gates. The
repository-only inventory selects no retirement policy. Frontend/runtime owners
qualify the dependency split and any separately needed format migration. Open
decisions block their affected migration or deletion; extraction selection grants
no waiver of existing contracts.
