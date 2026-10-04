# Workflow Lisp Dynamic Core Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task. Steps use checkbox syntax. The coordinator retains integration and verification; a different reviewer checks each implementation first for conformity, then for code quality.

**Goal:** Qualify the reviewed fresh-only, sequential dynamic candidate through the existing public CLI and shared boundary owners, ending with evidence for DC-P rather than adopting or migrating it.

**Architecture:** Follow [proposal §9](../design/workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate): ordinary runtime functions with explicit boundary schemas, direct shared command/provider performers, one independently checked program and one minimal fresh-run state profile. First prove exact routing, root contracts and selective module admission; move the experimental core and its active consumers together only when the imported shared seams can support the replacement path. Retain typed runtime owners for their existing targets.

**Tech Stack:** Existing Python frontend/runtime, S-expression reader, normalized type descriptors, output-contract validators, `StepExecutor`, `ProviderExecutor`, `WorkspaceFiles`, pytest and the existing CLI. No dependency or general backend interface is required.

**Tradeoff:** This removes dynamic callers' source assembly, leaf workflows and wire reconstruction. It makes latent type mistakes and recovery after interruption harder: checks occur at executed operations/boundaries, a fresh invocation repeats work, and old-target compatibility remains a maintenance cost.

## Authority, Scope And Current Evidence

The [evaluation plan](2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#dc-3-production-readiness-and-gate-dc-p) owns DC-U/DC-P dispositions. Its explicit owner continue selects this bounded readiness work. [Proposal §9](../design/workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate) owns the candidate contract; this plan does not make new language decisions. The design file inspected for this handoff has SHA256 `53f865b345ccc38fa7f0402fb158d39e8d5e0f116f04dfcf7eb1c5b1a09edf11`; independent Design review and the final argv-contract recheck both passed on that exact hash. Read `docs/index.md`, `docs/capability_status_matrix.md` and the governing design before each owner transfer.

This plan registers target `3.0` on the development branch only when its checked route can be exercised. Its program schema is `workflow-lisp/dynamic-program/1`; its state pair is `3.1` / `dynamic_execution.v1`. No default target changes, release claim, maintained application migration, paid provider work, child runs, parallel effects, resume, invalidation or effect-tracking implementation is selected. Resume/invalidation **refusal** is required. After DC-P only, the proposed single application destination is `experiments/mlevolve_pair/search_compact.orc`, entry `run-search`; its maintained file and command manifest remain unchanged during this plan. Qualification uses a fixture with the same complete policy. `std/dynamic/improve` is the required library integration, not a second application migration.

Design and plan reviews passed; **Tasks 1–4 are complete**; reviewed typed command/provider/document delivery and the plain native shared seam are qualified at `866dcd99`. Independent Sol conformity/quality review passed and combined verification recorded 2554 collected, 2553 passed and one expected failure in 223.11s with unchanged source hashes. Task 5 is selected next, not implemented; Tasks 6–9 remain pending. Q2 has declaration-only source selection; public/source-free linking remains unqualified. Q1 is partial: the strict native-root kernel is proved, with direct publication still pending Task 8. Existing DC-2's 110 utility cases, reviewed `4728b14e` candidate and frozen `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` comparison remain historical evidence; they do not pass Q1–Q5. Runtime import `163f286d` integrated at `cc896d41` supplies interpreter pins. Later reviewed command performer `d6d9469c`/receipt `fc9c57d3` integrated at `ddec5698`: 27 new and 157 affected cases passed. At that import, its native strict dynamic seam was not yet qualified; see the [shared import receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-command-performer-import) for the inherited empty-record limitation and exact evidence. Coordinator evidence at that integration: 9 narrow tests passed, 38 affected tests passed, 38 collected; logs are in `/tmp/orc-dc3-integration-z6_e0z2j`. Link durable receipts through the existing evaluation report before temporary logs disappear. Earlier `0f1bbc46` is represented by equivalent patch `a780639c`, not literal ancestry. Keep moving runtime pins separate from frozen comparison inputs.

Earlier synchronization, 2026-10-03: reviewed `b5b07ceb` integrated at `a672985d`; provider handoff `7e2282a4` / receipt `21b78d16` integrated at `103dc8cd`. Command and portable provider public runs, pure prompt assembly and captured C6 reads are available. The [current import receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-commandprovider-runtime-import) records APIs, verification and the remaining Task 4 gaps. Public-resume/full typed release acceptance remains separate; DC-P and Q1–Q5 are unchanged.

Earlier synchronization, 2026-10-04: reviewed Task 8 and retained-descriptor writer delivery through `e17bd61f` integrated at `d3b68c0a`; the [current import receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-typed-resumeinvalidation-import) records ordinary typed public resume/suffix invalidation and exact affected-suite limitations. This does not add dynamic recovery. The native strict result/provider-preparation and certified inline serialization sub-slice is qualified at `ee4ae46b` under Task 4 ownership; its [current receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-native-performer-sub-slice) records that bounded evidence separately from external Task 12 document transport and its integrated qualification, which were missing at that cutoff. The later import and combined qualification below supersede that missing dependency.

The earlier shared cutoff `4ca7a0fb` is integrated at `eb9c9e30`, including the reviewed durable-locator alias correction; the [native/shared receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-native-performer-sub-slice) records 878 affected checks and the Task 12 dependency at that cutoff. That import did not complete Phase 3 Task 9 or advance dynamic gates.

Current synchronization, 2026-10-04: shared Tasks 9–11 have reviewed completion receipts for path children/coordinators, derived report/dashboard views and monitor/probe/watchdog readers. Task 12 external documents through `4bcf5424`, `5bdb2497` and `a024397b`, plus the native document seam, are integrated at `866dcd99`. The [current import receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-childrenreadersinput-document-import) preserves the initial frozen merge review/280 typed checks and records final Sol conformity/quality PASS plus 2553 passed/one expected failure across 2554 collected cases with unchanged source hashes. **Task 4 PASS** releases the atomic Tasks 5–8 cutover; Task 5 is selected next, not implemented. Task 8 owns the actual dynamic caller/publication. Upstream Task 12 public replay delivery `ebaf78ed` and closeout `98b3f3d9` are integrated at `970ac933`, with 29 new cases collected and passed in 118.92s; full Phase 3 and live-provider qualification remain open. Public `3.0`, Q1–Q5 completion and DC-P remain unqualified.

### Sequencing And Unavailable Owners

| Work | Dependency and permitted progress |
| --- | --- |
| Tasks 1–3: exact routing, Q1 root-contract preparation, selective source linking | Independent of missing shared performers. Do not call these a runnable dynamic public target. Task 3 proves selection before executable elaboration, not complete Q2 source-free execution. |
| Task 4: shared import/seam qualification | Import reviewed Phase 3 Tasks 6–7/12; inspect actual APIs and their state dependencies. Typed delivery and native document preparation/attempt-path sharing passed combined qualification at `866dcd99`; the cutover is released. |
| Tasks 5–8: production cutover, in bounded reviewed sub-batches | Task 4 has passed; Task 5 is selected next, not implemented. Prepare in an isolated integration checkout and land the core move, frontend, state, direct path, stdlib and replacement active tests together. No intermediate release, copied core or production spike decoder. |
| Task 9: retained controls, interruption/readers and readiness closeout | Requires the integrated candidate. Complete Q1–Q5 and document remaining live-provider allocation gaps; DC-P disposition remains an owner decision. |

At every task/sub-batch boundary, the coordinator follows the evaluation plan's [upstream synchronization procedure](2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#upstream-phase-3-synchronization): inspect committed shared heads and receipts, import applicable reviewed changes, resolve owner overlap, run affected checks and record source/integration hashes. Do not cherry-pick another worker's uncommitted state. If a required shared API is still memo-coupled, return that extraction to its owner or obtain an explicit ownership transfer; do not create a parallel performer, fabricate a memo, or wrap `WorkflowExecutor` to avoid the dependency.

## File And Ownership Map

Paths below are proposed destinations unless explicitly described as existing. A path in this table is not evidence an API exists.

| Owner | Files and responsibility |
| --- | --- |
| Existing target selection | `orchestrator/workflow_lisp/syntax.py`; callers in `compiler.py`, `closed/{target,frontend,artifact}.py`, `typecheck_effects.py`, `orchestrator/cli/commands/{compile,run,resume}.py` and `orchestrator/workflow/run_ref/child.py`. Preserve old target routing; keep dynamic imports/children explicitly refused where inadmissible. |
| Shared schema/boundary owners | `orchestrator/workflow_lisp/{contracts,normalized_type_descriptor,typed_prompt_inputs}.py`, `orchestrator/contracts/output_contract.py`, `orchestrator/workflow/type_descriptor.py`. One strict captured-byte/root-value pipeline, original typed defaults retained. |
| Existing source/module owners | `orchestrator/workflow_lisp/{reader,syntax,modules,definitions,type_env,source_map}.py` and manifest/configuration loaders in `build_manifest_io.py`. Reuse roots, names, visibility, declaration dependencies and source tracing. Change only the owners actually traversed by the selected declaration path. |
| Dynamic program/frontend | New `orchestrator/workflow_lisp/dynamic/{__init__,program,source,build}.py`. Move/revise experimental `program.py` and `source.py`; independent admission, checked source maps and closed build publication. No typed body synthesis. |
| Dynamic evaluator/run | New `orchestrator/workflow/dynamic/{__init__,evaluator,runtime,state}.py`. Move/revise experimental `evaluator.py`; `state.py` owns fresh authority validation/publication and read-only projection, `runtime.py` owns invocation transitions and direct performer calls. Do not create a generic dispatcher hierarchy. |
| Imported shared performer owners | Planned `orchestrator/workflow/evaluated/{commands,prompts,providers,inputs}.py` and existing closure/interpreter/filesystem owners. Consume actual delivered request APIs; no interface signature is invented here. Typed attempts/memo remain typed. |
| Public routes/readers | New `orchestrator/cli/commands/dynamic.py`; narrow changes in existing CLI compile/run/resume/report, `cli/main.py`, `state.py`, dashboard and monitor readers, probe and usage-limit watcher. A public result carrier must preserve scalar dynamic terminal values while retaining legacy mappings. |
| Library and qualification consumers | New `orchestrator/workflow_lisp/stdlib_modules/std/dynamic/improve.orc`; new `tests/fixtures/workflow_lisp/dynamic/` fixtures; new `tests/test_workflow_dynamic_*.py` modules named below. Retain original `std/improve.orc` schema identities and typed helper. |
| Historical experiment removal | `experiments/dynamic_core_evaluation/{program,source,evaluator,leaf_bridge}.py`, its source fragments and active test drivers. Move reusable code/policy; remove maintained duplicates and obsolete callers only in the complete cutover. Preserve original receipts and reproduction revision in its README/report. |

Owner transfer means coordinator-managed exclusive file assignment after checking upstream overlap; it is not a new user-approval gate. The coordinator may assign the reviewed dynamic-specific strict opt-in to the existing shared owner and return its delta/evidence for reuse. Shared performer delivery remains upstream.

No live workflow/selector drains this plan. The evaluation plan and its parent roadmap prose select work; there is no new manifest to fabricate or historical run state to rewrite. The coordinator updates linked routing surfaces when task status or availability changes.

## Common Execution And Review Protocol

Implementation / code uses Luna 6 xhigh for bounded batches; escalate an oversized or repeatedly failing batch to Sol 6.1 high. Revision / code returns to the implementer when possible. Review / code uses a distinct Sol 6.1 high reviewer, first conformity against the exact task/design, then quality after conformity passes. New architecture questions return to Design / design with Astra 6 xhigh; ordinary implementation decisions stay with the existing owner. Final specification/readiness review is independent of its author. Every delegation names role, artifact, exclusive files and dependencies.

For each task: inspect all callers; write the smallest failing behavioral/contract check; run its narrow selector and record the actual failure; implement; collect new/renamed modules; run narrow checks; inspect diff; complete both reviews; rerun only checks affected by corrections. No tests of literal prompt prose, no skipped assertions to conceal missing delivery, and no missing-module fixture standing in for a real public path. The coordinator inspects integrated diffs/results itself.

Run commands from this worktree root with the intended interpreter and local imports (`PYTHONPATH=.` if needed to defeat a stale editable install). Use the tmux skill for long commands. Broad/slow suites run in tmux with `pytest -q -n 16 --dist=worksteal`; selectors shown without xdist are the narrow first checks. Commit reviewed complete units when authorized; Tasks 5–8 form one atomic cutover and must not leave the active DC-2 route broken in an integrated commit.

## Task 1: Make Typed Target Routing Exact

**Role/artifact:** Implementation / target selection and refusal tests. **Dependency:** none beyond the reviewed design. This is the first bounded executable task, suitable for one Luna implementer.

**Exclusive files:** Modify `orchestrator/workflow_lisp/syntax.py`; extend `tests/test_workflow_lisp_target_evaluated_execution.py`. Inspect, but change other callers only if a failing causal test demonstrates the shared predicate is insufficient. No target registration or dynamic source forms in this task.

- [x] Re-run `rg -n 'target_dsl_uses_evaluated_execution' orchestrator tests` and inspect every caller, including compile/import, typecheck, run/resume and run-ref refusal paths.
- [x] Add `test_evaluated_route_excludes_unknown_and_dynamic_targets`: assert the existing predicate accepts `2.35`, rejects every earlier supported target and rejects `2.36`, `3.0`, `3.1` and malformed input. This must fail on the current numeric comparison. Keep the existing minimum-version constant for its compatibility audit; do not rename prior tests needlessly.
- [x] Add `test_unknown_target_public_compile_and_run_refuse_before_creation`, parameterized for unregistered `2.36` and `3.0`. Use actual public compile/run source entry with spies that fail on typed/legacy execution, and assert nonzero diagnostic exit, no build/run creation and no process launch. Assert a diagnostic code/location, not wording. The `3.0` case moves to the positive dynamic route test only when Task 6 explicitly registers it; `2.36` stays refused.
- [x] RED: `pytest -q tests/test_workflow_lisp_target_evaluated_execution.py -k 'excludes_unknown or unknown_target_public'`.
- [x] Replace the open-ended numeric route with the exact currently supported typed target selection in the same owner. For the inspected registry the complete body can be `return target_dsl_version == EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION`. Do not add a registry/plugin abstraction or broaden run-ref supported versions.
- [x] Collect the changed module, then GREEN: `pytest -q tests/test_workflow_lisp_target_evaluated_execution.py`. Run the public pure smoke `pytest -q tests/test_workflow_evaluated_cli.py::test_public_pure_run_persists_checked_terminal` and old artifact check `pytest -q tests/test_workflow_lisp_target_234.py`; put the latter in the broad tmux command if its collected workload is slow.
- [x] Check the shared predicate's caller diff and retained `2.35` behavior in independent conformity/quality review. Record this as a routing prerequisite only; no Q proof or dynamic capability is complete.

## Task 2: Prove One Strict Native-Root Boundary

**Role/artifact:** Implementation / shared output-contract delta and Q1 preparation. **Dependency:** none on performers; transfer these shared files from their upstream owners before editing.

**Files:** Extend `tests/test_output_contract.py` and `tests/test_output_contract_nested_transport.py`; create `tests/test_workflow_dynamic_boundaries.py`. Modify only needed shared owners `orchestrator/contracts/output_contract.py`, `orchestrator/workflow/type_descriptor.py` and `orchestrator/workflow_lisp/contracts.py`. The existing `derive_prompt_guided_structured_result_contract(..., whole_value=True)` is the API; use it, do not recreate it.

- [x] Write a real record/applied-union contract fixture, derive a whole-value output contract, and feed captured bytes through the existing output owner. Expect native `__result__` data, strict Bool/Int/finite values, Int-to-Float normalization and original active-union shape.
- [x] Add negative cases for duplicate JSON keys, extra/missing/inactive fields, wrong Bool, nested invalid values and output-path escapes. A valid result plus missing required report must publish no successful result. Prove all validators see the same captured bytes even if the pathname changes after acquisition.
- [x] RED: `pytest -q tests/test_workflow_dynamic_boundaries.py`. Inspect the existing decoder before moving/reusing the experiment's strict decoder; one shared owner must implement strict policy. Add a selected-profile opt-in at that owner if required, retaining old default behavior. No evaluator-local parser or schema implementation.
- [x] GREEN: collect the new module, run it, then relevant selectors in `tests/test_output_contract.py`, `tests/test_output_contract_nested_transport.py` and `tests/test_workflow_lisp_build_artifacts.py`. Compare retained typed generated/read-back contracts unchanged for identical identity inputs.
- [x] Record Q1 as **partial: root kernel proved, direct performer publication pending Task 8**. Record the reusable shared delta and evidence for the upstream owner before the next import; keep the shared-file ownership allocation explicit.

## Task 3: Qualify Declaration-Only Source Selection

**Role/artifact:** Implementation / module selection, ownership and source-location delta. **Dependency:** Task 1 for route assumptions; no performer dependency. Scope ends before new program-format lowering.

**Files:** Extend `tests/test_workflow_lisp_modules.py`; create `tests/test_workflow_dynamic_modules.py` and module fixtures under `tests/fixtures/workflow_lisp/dynamic/modules/`. Modify `modules.py` and the narrow declaration-selection seam in `compiler.py`; extend `syntax.py`, `definitions.py`, `type_env.py` or source-map vocabulary only if their real declaration path requires it. Do not add a parallel module resolver.

- [x] RED fixture: select `Decision`/`Improvement` from existing `std/improve` with their declaration dependencies while an executable typed-helper elaborator spy raises if called. Test roots, exports, alias/`:only`, transitive declaration dependencies, duplicate canonical member snapshots, cycles and ambiguity. A declaration requiring an inadmissible executable dependency must fail with the import chain.
- [x] Add refusal checks for selected old `defproc`, workflow, macro and `ProcRef`, and supplied compiled bundles of **every** profile. Existing target entries must refuse dynamic executable source. Keep unknown-version checks ahead of loading any foreign profile. Supplied-bundle and dynamic-source refusals are verified in Task 6 if the Task 3 seam does not accept those inputs; do not simulate an unavailable loader.
- [x] Run `pytest -q tests/test_workflow_dynamic_modules.py`; implement selection before executable elaboration through the existing discovery/export/scope owners. Select before macro expansion and declaration elaboration, reusing `resolve_module_graph`, `derive_export_surface`, `build_import_scope` and the compiler's imported/exported type-reference helpers. A selected-declaration test must exclude an invalid unselected declaration; the existing stage-1 path already skips procedure bodies, so a procedure spy alone proves no new behavior. Preserve defining module identity, configuration/asset base and exact `SourceReadTrace` bytes/spans. Do not concatenate source or synthesize a provisional dynamic artifact.
- [x] Collect and GREEN the new module, then `tests/test_workflow_lisp_modules.py`. Source-free execution, ordinary helper captures and persisted maps stay pending Task 6; mark this limited result honestly in Q2 evidence.
- [x] Review boundaries of any shared loader amendment with retained old-target module fixtures. If source header/export support cannot be separated from dynamic lowering, keep that part in Task 6; do not register a runnable target to make this preliminary proof pass.

Task 3 integrated at `17a69df0`: 23 new cases collected and passed, 336 affected
cases passed, and coordinator verification passed 24 cases including a retained
public CLI run. Independent conformity and quality passed. Compiled-bundle,
target-3.0, source-free and persisted-map checks remain Task 6, as scoped above.
See the [receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#task-3--selective-source-declarations).

## Task 4: Import And Qualify The Direct Shared Seam

**Role/artifact:** Coordinator / upstream integration and interface evidence. **Dependency:** actual reviewed Phase 3 Task 6 command performer, Task 7 prompt/provider performer and Task 12 input-document delivery. Existing helper receipts do not satisfy this dependency.

**Imported baseline (2026-10-04):** reviewed shared delivery through `e17bd61f`
is imported at `d3b68c0a`, retaining command runtime/R12 rendering, pure prompt
assembly, captured provider IO and the portable provider performer/lifecycle,
and adding ordinary typed public resume/invalidation.
Provider required output-file checks are delivered. The native sub-slice adds
`native_result=True` to the existing command/provider performers and captured-byte
validator: it requires one strictly transportable whole-root result contract
before dispatch, preserves one captured result read, and validates required
provider files and overlap before return. Typed defaults retain projection.
Private plain validated-value provider preparation avoids `EvaluatedValue`
construction and uses the existing path-only `WorkflowIOReader`; Task 8 owns
strict input validation, imported-asset module ownership, the actual dynamic
caller and publication. Argv rendering reuses `render_variable_value` after
strict validation; no second template extraction or reader is required.
Command document serialization is qualified through the plain ordered-field
`_serialize_command_document` kernel, preserving both canonical external bytes
and signature-ordered certified inline JSON; its typed wrapper preserves
absent-document, slot-offset and operand-count rules. The [current native receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-native-performer-sub-slice)
records that qualified sub-slice. The later reviewed Task 12 import supplies
external document operand/bytes/path-token transport, including absent/empty
semantics. Shared `_prepare_command_document_fields` consumes plain field values
and descriptors through the existing validators; `_command_document_argv`
accepts caller-owned attempt files and appends the external document token.
Their typed wrappers retain once-only operand order, absence/empty distinction
and attempt publication. No typed node/value or fabricated memo is needed for
the native request. The [current document import receipt](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#shared-childrenreadersinput-document-import)
records `866dcd99`, independent Sol conformity/quality PASS and final combined
verification. **Task 4 PASS** selects Task 5 next and releases the atomic
Tasks 5–8 cutover; Task 8 still owns the actual dynamic caller/publication.

**Owned changes:** Integration receipts in the existing evaluation report/Phase 3 evidence matrix; shared source remains with its owner unless explicitly transferred. No new performer implementation is assigned by this task.

Upstream observation during drafting: `d6d9469c10718ca993f32df15bf9ce8102944ac3` introduces `commands.py::perform_command(node, argv, *, attempt_files, workspace_files, input_document=None, timeout_sec=None)`, returning `(EvaluatedValue, result_digest)`. Its projection/coercion still assumes checked typed nodes. This is concrete shared delivery, not proof that the dynamic native-root/strict-policy seam or full Task 6/7/12/Q3 is ready. The coordinator owns its current integration receipt; refresh that receipt at this task rather than treating this draft observation as an import pin.

- [x] Inspect the delivered `evaluated/{commands,prompts,providers}.py` and actual call sites; record delivered `evaluated/inputs.py` and its typed preparation dependencies. Record concrete callable names/signatures and request/result ownership from code in the receipt; this plan deliberately supplies no fictional APIs.
- [x] Verify requests take resolved values, declaration-owned contracts and caller-owned attempt files without reading typed memo, `EvaluatedValue` internals or dynamic state. If not, route one shared extraction to its owner. Task 4 qualifies the delivered shared contract with real dispatch and its existing consumer; Task 8 adds the real dynamic caller and verifies both before integrating the atomic cutover. Requiring that second caller before starting its implementation would be circular. No fake typed `ClosedProgram`, `MemoSnapshot`, attempt journal or per-effect `WorkflowExecutor`.
- [x] Import reviewed delivery and run its exact selectors in `tests/test_workflow_evaluated_commands.py`, `tests/test_workflow_evaluated_prompts.py`, `tests/test_workflow_evaluated_providers.py`, `tests/test_workflow_lisp_command_input_documents.py`, `tests/test_workflow_lisp_closed_input_documents.py`, `tests/test_workflow_evaluated_input_document_contracts.py`, `tests/test_workflow_evaluated_input_document_attempts.py`, plus changed closure/interpreter/attempt and native-seam checks. These are delivered module names; retain their real typed consumers when qualifying the shared extraction.
- [x] Confirm whole-value contracts, captured-byte strict policy, provider document roles/required files, explicit cwd/permissions, one dispatch, certified signature ordering and external document transport can pass through that seam. Task 8 owns dynamic public source evidence; these are interface prerequisites.
- [x] Record PASS or the exact missing owner/slice (current receipt records qualified native/inline/external document kernels and combined verification at `866dcd99`; **PASS**). PASS releases Tasks 5–8; Task 5 is selected next, not implemented. The shared qualification alone does not complete the overall goal.

## Tasks 5–8: Atomic Production Cutover

These are sequential, separately delegated/reviewed sub-batches of one integration unit. Task 4 has passed; Task 5 is selected next, not implemented. Freeze a reproducible DC-2 revision and receipts first. The coordinator lands the unit only when new active behavior tests replace the removed active drivers and all required cutover checks pass. No persistent production copy of the experiment, no forwarding experimental package and no spike-format compatibility decoder is allowed.

### Task 5: Move And Admit The Core

**Role/artifact:** Implementation / program and iterative evaluator. **Files:** Move `experiments/dynamic_core_evaluation/program.py` to `orchestrator/workflow_lisp/dynamic/program.py`; move its evaluator to `orchestrator/workflow/dynamic/evaluator.py`; create package initializers and `tests/test_workflow_dynamic_program.py`, `tests/test_workflow_dynamic_evaluation.py`. Archive spike-format-only tests with their exact historical revision; port reusable behavior from `tests/experiments/test_dynamic_core_evaluation.py`.

- [ ] RED read-back/tamper checks for the **exact** §9.4 envelope, lexical definition fields/owner/boundary, public defaults, schema references, authorized static effect payloads, source references and semantic/provenance digests. All bodies are checked, including unreachable ones. Reject old spike schemas, unknown fields/versions, host callables and forged code/configuration references.
- [ ] Move the core and revise it for only the production representation. Reuse canonical digest, descriptor and immutable value owners. Persist source provenance separately from semantic identity; location-only edits must preserve semantic digest. Independent read-back re-derives root contracts rather than trusting copied schema/contract data.
- [ ] Port strict scalar/numeric/budget checks and ordinary create/return/store/pass/select closures, recursion/self-application, shadowing, functional updates and lazy strict conditions. Declared workflow calls validate arguments/defaults/result; helpers remain untyped. Reject closures recursively at every data boundary. No call/effect resets the invocation budget.
- [ ] Run `pytest -q tests/test_workflow_dynamic_program.py tests/test_workflow_dynamic_evaluation.py`, collecting both modules. Pure checks can pass before source/public integration; missing direct execution is not represented by a trusted host callback or old `LeafBridge`.
- [ ] Review this sub-batch before assigning the frontend. Do not land it alone while active experiment consumers still depend on the removed owners.

### Task 6: Finish Source Lowering, Closed Builds And The Pure Public Route

**Role/artifact:** Implementation / frontend, imports, maps and build/CLI routing. **Dependency:** Tasks 3, 5. **Files:** Move experimental `source.py` to `workflow_lisp/dynamic/source.py`; create `dynamic/build.py`, `orchestrator/cli/commands/dynamic.py`; modify existing syntax/module/source-map and compile/run route owners narrowly. Create `tests/test_workflow_dynamic_source.py`, `tests/test_workflow_dynamic_cli.py`; extend `tests/test_workflow_dynamic_modules.py` and the target test from Task 1.

- [ ] RED ordinary `workflow-lisp`/`defmodule`/`defworkflow` source with entry-only budget, untyped `define`/`fn`, explicit boundary declarations, defaults and imported helpers. Test malformed syntax, unbound names, duplicates, missing budget/result schema and every prohibited class in unreachable bodies.
- [ ] Lower directly to the admitted dynamic representation. Resolve imports once by canonical owner; preserve defining-module prompt/configuration/asset ownership. Add per-expression/boundary maps with spans/form paths. Source-free execution must succeed after source deletion; invalid required maps refuse before evaluation. Runtime arity/field/type errors identify imported definition and caller without values/captures leaking into diagnostics.
- [ ] Reuse `FrontendBuildRequest`, source/configuration traces, binding manifests and atomic artifact publication. Refuse all compiled import bundles. Persist/read back program plus source provenance; do not route through typed specialization/WCC/`ClosedProgram` construction.
- [ ] Register `3.0` **only in the candidate source/build route on this branch**, with exact selection before typed/legacy loaders. Update every relevant target predicate caller from Task 1's inventory; retain old run-ref/trial/bundle rejection, do not copy the new target into unrelated supported-version sets. Unknown targets still refuse.
- [ ] Public compile and dry-run must enforce option/input/binding rules before run creation. Track explicit CLI options separately from legacy parser defaults: omitted retries mean zero here; explicit nonzero retries/continue and other §9.2 exclusions refuse. A dry-run does not execute latent branches or promise dynamic type safety. Scalar public results must survive the existing result carrier without breaking old mapping consumers; implement that narrow carrier change with actual callers/tests.
- [ ] Collect/run `pytest -q tests/test_workflow_dynamic_source.py tests/test_workflow_dynamic_modules.py tests/test_workflow_dynamic_cli.py`; run retained typed CLI/target tests after shared routing changes. Pure public run tests become GREEN after Task 7 supplies fresh authority. Do not call a compile-only artifact a runnable candidate.

### Task 7: Fresh Authority And Profile-Aware Readers

**Role/artifact:** Implementation / fresh state, CLI and inspection. **Dependency:** Task 5 program and Task 6 routing; transfer public reader files before editing.

**Files:** Create `orchestrator/workflow/dynamic/{state,runtime}.py`, `tests/test_workflow_dynamic_state.py`, `tests/test_workflow_dynamic_readers.py`; extend dynamic CLI tests. Modify `cli/commands/{run,resume,report,dynamic}.py`, `cli/main.py`, `orchestrator/state.py`, `dashboard/{scanner,projection,cursor,preview}.py`, `monitor/{scanner,classifier,messages}.py`, `workflows/library/scripts/probe_orchestrator_run.py`, `scripts/watch_workflow_usage_limit.sh` only for actual profile routing. Modify an upstream invalidate command if it exists; otherwise refuse this profile at the existing public invalidation entry, without creating a new general invalidation feature.

- [ ] RED exact §9.7 run/state/effect-row schema and cross-field invariants, scalar terminal values, immutable pins, missing/corrupt state, noncontiguous ordinals, invalid paths, multiple running rows and unknown/mixed profiles. Snapshot bytes around every refused resume/invalidation/reader operation.
- [ ] Under existing writer/workspace locks, use pinned `WorkspaceFiles`/durable write owners to publish program/header/initial state before execution. Persist only fresh state; no memo or captured environment. Do not call typed `allocate_attempt`/`attempt_paths`, which require memo authority. Reuse lower filesystem operations; any shared extraction needs actual typed and dynamic callers and upstream ownership.
- [ ] Add run transitions and exclusive ordinal attempt paths, with no adoption on collision. Atomic publication/allocation failure stops before another dispatch. Schema-valid terminal output requires completed effects and no active failure. Earlier successful files remain evidence after later failure.
- [ ] Readers validate pins and state through the profile owner, use lock liveness to distinguish running/interrupted, and never compile, replay, dispatch, repair or write. Missing state is invalid, not reconstructible. Dashboard/report expose reached invocations and `resumable: false`; monitor/probe/watcher stop/escalate interrupted runs instead of automatically resuming/restarting. No notifications or scheduled jobs are sent.
- [ ] Collect/run `pytest -q tests/test_workflow_dynamic_state.py tests/test_workflow_dynamic_readers.py tests/test_workflow_dynamic_cli.py`. Exercise actual public report, dashboard response, `monitor --once --dry-run`, probe subprocess and controlled one-cycle watcher. Reuse existing legacy reader suites listed in Task 9.
- [ ] Pure public compile/run/report smoke must now pass. Effect interruption cases remain pending the direct integration in Task 8; record this distinction in Q4.

### Task 8: Direct Effects, Imported Improve And Replacement Consumers

**Role/artifact:** Implementation / dynamic-specific boundary adaptation, stdlib and integration tests. **Dependencies:** Tasks 4–7. Keep individual revisions bounded: command path, provider path, then library/consumer port; review each before combining.

**Files:** Extend `workflow_lisp/dynamic/{source,program,build}.py`, `workflow/dynamic/{evaluator,runtime}.py`; change shared static payload checks only by owner-approved extraction in `closed/{effects,check}.py`. Create `tests/test_workflow_dynamic_commands.py`, `tests/test_workflow_dynamic_providers.py`, `tests/test_workflow_dynamic_improve.py`, `tests/test_workflow_dynamic_search.py`, `tests/test_workflow_dynamic_edits.py` and fixtures under `tests/fixtures/workflow_lisp/dynamic/`. Move the helper policy into `stdlib_modules/std/dynamic/improve.orc`.

- [ ] RED public command fixtures: a real certified adapter, real external argv tool, and typed external document tool. Derive boundaries from existing bindings and explicit `:returns`; require `:input-type` exactly when external `:inputs` is present, including empty records, and forbid it for certified adapters. Validate exact fields/paths/strict values before dispatch; preserve written operand order and evaluate once.
- [ ] Implement only dynamic child evaluation/descriptor checks and the caller's state transitions around the imported shared request/performer. Preserve shared argv rendering of scalars/aggregates, Bool spellings and literal/runtime distinctions. Do not reinterpret a runtime string as a template/reference. Reuse certified inline ordering and Task 12 file/token transport. Check closure/disjointness/interpreter evidence through the delivered owners.
- [ ] RED public provider fixture: deterministic executable provider captures the real request, documents, options and output paths, returns a declared record/union, selects a closure from that data and performs a later actual command. Owner-relative documents and required reports must survive imports. Set a spy to fail on any dynamic-path `WorkflowExecutor` construction. No host callback or per-leaf run can satisfy this check.
- [ ] Complete Q1 using one captured result snapshot through strict root and required-output validation to actual publication. Wrong/missing bundle, wrong Bool/extra/inactive fields, nonfinite data, forbidden paths, permissions and required-report failure expose no successful dynamic result. Preserve registered `omp_json_stdout`; ordinary stdout remains insufficient.
- [ ] Move improve policy to the real library import, using existing `std/improve` `Decision`/`Improvement` declarations. Port approval, blocked, exhaustion, final-revision failure, invalid hooks, nonpositive limits and imported/inline order. Ordinary captures carry separate goal/rubric values; no internal type arguments, `ProcRef`, carrier records or authored `return__` normalization.
- [ ] Port the complete search protocol to the qualification fixture: seed rank, strict improvement/ties, invalid evaluation versus invalid schema, one same-branch repair, stalls, one fusion, complete history, budget/score stops and loop exhaustion. Keep the maintained `search_compact.orc` unchanged until DC-P. Port the four edits (state field, review payload, capture context, helper extraction) and late-error/cost observations to the direct route.
- [ ] Collect all new modules; run narrow command/provider checks and public smokes first. Run the slower improve/search/edit corpus in tmux with `pytest -q -n 16 --dist=worksteal tests/test_workflow_dynamic_improve.py tests/test_workflow_dynamic_search.py tests/test_workflow_dynamic_edits.py`.
- [ ] Remove `LeafBridge`, `_GuardedWorkflowExecutor`, hand-linked registries, wrapper leaf workflows and source assembly from the maintained candidate. Remove active experiment imports only after each reusable behavioral case has a named production replacement or an explicit historical-only rationale. Do not delete a difficult utility case as though it were merely spike-format admission. Preserve frozen controls and report original/new counts separately.
- [ ] Inspect the complete Tasks 5–8 diff and replacement test map; verify both real callers of every shared extraction, then complete conformity and quality review before integrating this atomic cutover.

## Task 9: Q1–Q5 Evidence, Compatibility And DC-P Handoff

**Role/artifact:** Coordinator / final integration; Revision / documentation and reports; independent Review / readiness. **Dependency:** integrated Tasks 1–8. No paid calls or application migration are part of this task.

**Files:** Existing evaluation report and its plan; Phase 3 [evidence matrix](2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#evidence-coverage-matrix). Update `docs/index.md`, `docs/design/README.md`, `docs/capability_status_matrix.md`, parent evaluated-execution plan, repetition plan and follow-on roadmap together. On behavior landing, amend applicable `specs/{versioning,cli,state,io,providers}.md`, `docs/design/workflow_lisp_frontend_specification.md`, `docs/lisp_workflow_drafting_guide.md`, and the experiment README to distinguish branch-qualified profile from adopted/default availability. Do not globally rewrite typed contracts.

- [ ] Create the Q1–Q5 receipt rows below in the existing evidence matrix/report, with source/runtime hashes, exact selectors, expected versus observed behavior, counts, review hashes and missing evidence. No duplicate release checklist with competing status.
- [ ] External-kill Q4 checks use real subprocesses at pre-dispatch, in-flight and output-before-publication barriers. Repeated fresh run consumes additional calls/budget; old run files remain unchanged, orphan results are not adopted, resume/invalidation refuse. Also inject failed state writes/allocation and reader races. Exercise source-free errors and wrong-profile routes with no writes/launches.
- [ ] Run retained target/artifact/run/resume selectors and actual old profile roots. Preserve original runtime/environment pins; source recompile is not old-run conversion. Compare old artifact/request observations on identical identity inputs; record legitimate package-pin changes instead of normalizing them away.
- [ ] Run final collection and the affected broad suite below in tmux. Reuse valid prior full results unless code changes or unresolved failures justify a rerun. Diagnose baseline failures against pinned source; never weaken assertions or mark unavailable live-provider tests passed.
- [ ] Inspect removal/compatibility ledger against actual files/callers. Publish removed versus retained owners and new authority cost, not just LOC. Do not claim whole typed compiler retirement.
- [ ] Verify Markdown links/anchors, source examples with the actual parser/compiler, stale status routes and `git diff --check`. Independent code review and independent readiness/document review must both pass on the integrated candidate.
- [ ] Present DC-P with Q evidence and explicit paid/live qualification gaps. Only an explicit owner continue authorizing adoption/migration activates Phase 6b for the one named destination. Phase 7 retirement remains separate. Stop retains typed fallback; unfinished shared work is reported as unfinished readiness, not a completed candidate.

### Proof Ownership

| Proof | Completion evidence; no inherited automatic PASS |
| --- | --- |
| Q1 | Task 2 kernel plus Task 8 actual command/provider publication: one captured snapshot, native record/applied-union roots, strict refusals, required-output failure and retained typed contracts. |
| Q2 | Task 3 selection plus Tasks 5–6 source-free closed artifacts, real imports/captures, owner-relative documents, valid maps, version/conflict/cycle refusals. |
| Q3 | Task 8 real public source/CLI with both command transports and deterministic provider, closure selected after result, exact request comparisons, and no legacy executor construction. |
| Q4 | Tasks 7/9 real readers, locks, subprocess kills, failed publications, immutable prior files and explicit no-resume/no-invalidate behavior; fresh calls repeat work. |
| Q5 | Tasks 8/9 full improve/search controls and four edits, retained old targets/runs, actual removal inventory and honest late-error/restart costs. |

Final dynamic suite (after the named modules exist):

```bash
pytest --collect-only -q tests/test_workflow_dynamic_*.py
pytest -q -n 16 --dist=worksteal tests/test_workflow_dynamic_*.py
```

Affected compatibility suite, selecting extra imported performer modules from Task 4's actual receipt:

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_lisp_target_evaluated_execution.py \
  tests/test_workflow_lisp_target_234.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_build_path_safety.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_improve_stdlib.py \
  tests/test_workflow_evaluated_cli.py \
  tests/test_workflow_evaluated_authority.py \
  tests/test_workflow_evaluated_attempts.py \
  tests/test_workflow_evaluated_interpreters.py \
  tests/test_workflow_state_compatibility.py \
  tests/test_output_contract.py \
  tests/test_output_contract_nested_transport.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_cursor.py \
  tests/test_dashboard_projection.py \
  tests/test_monitor_classifier.py \
  tests/test_monitor_messages_emailer.py \
  tests/test_generic_run_watchdog.py \
  tests/test_watch_workflow_usage_limit.py
```

## Removal And Compatibility Ledger

| Surface | Disposition in this plan | Later obligation |
| --- | --- | --- |
| Experiment program/evaluator/source implementations | Move/revise, do not copy. Remove old package imports in the atomic cutover; retain receipts and historical revision. | None requiring a second maintained implementation. |
| Spike schema read-back tests | Archive as historical proof, without production decoders. Port value/budget/security behavior to the new format. | Preserve reproducibility from the frozen source. |
| Leaf bridge, guard executor, registry, wrapper leaf sources and dynamic caller normalizers | Delete from maintained dynamic execution after direct replacements pass; account for every active test caller. | Typed legacy leaf runs remain under their original owner. |
| Assembled improve/helper fragments | Replace with real `std/dynamic/improve` import and production fixtures. | Retain canonical domain schemas in `std/improve`. |
| `search_compact.orc` / `commands_compact.json` | Unchanged maintained consumer; direct candidate is a test fixture until DC-P. | One migration after authorization, preserving entry/config/policy and external schemas. |
| Typed compiler specialization/ProcRef/proofs, legacy lowering, typed evaluator/memo and resume | Retain. Dynamic bypass is not deletion. | Phase 7 requires actual remaining-caller and existing-run retirement decisions. |
| New program/frontend/fresh-state/readers | Count as new production responsibilities and compatibility cost. | Adoption must weigh these against removed call paths and authoring benefits. |

## Completion Record

Planning or a successful independent prerequisite does not complete readiness. Check each item only with integrated evidence:

- [x] Tasks 1–3 passed and exact limited proof scope recorded.
- [x] Task 4 imported real shared delivery and qualified its memo-free seam.
- [ ] Tasks 5–8 atomically replaced the experiment route with active behavioral tests.
- [ ] Q1–Q5 passed with public integration, retained-profile and kill evidence.
- [ ] Source/spec/routing docs match delivered availability; independent reviews passed.
- [ ] Paid/live evidence needs are explicitly recorded as satisfied by authorized work or missing; deterministic stand-ins are not claimed as live-provider qualification.
- [ ] DC-P evidence packet handed off with adoption, migration and retirement still unselected. The subsequent owner disposition is external to this readiness plan and is recorded separately; it is not required to finish DC-3 qualification.
