# Workflow Lisp Evaluated Execution Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task. Use `superpowers:test-driven-development` for code and `superpowers:verification-before-completion` before completion claims. Steps use checkbox (`- [ ]`) syntax for tracking. The coordinator integrates and verifies; a reviewer distinct from the author reviews each substantive task.

**Goal:** Deliver public execution, resume, invalidation and inspection of every composition admitted by the target-2.35 closed program, with durable effect authority and preserved old-target behavior.

**Architecture:** Evaluate the existing checked table program with lexical values and activation frames, reusing the pure catalog and the existing command/provider/run-reference boundaries. A synchronized append-only memo owns results; the same evaluator supplies execution, preflight and read-only position projection. Profile-aware adapters consume memo-derived views rather than fabricated flat workflows.

**Tech Stack:** Python, the existing checked Workflow Lisp representation, stdlib JSON/filesystem/locking, existing provider and command executors, pytest and public `python -m orchestrator` subprocess checks. No new dependency or general plugin/performer framework.

---

## Status, Authority And Scope

Planning baseline: `71fbbb746de947b712f55b9c149859649b29c345`, branch `feat/orc-phase3-execution`, worktree `/home/ollie/Documents/agent-orchestration/.worktrees/orc-phase3`. This document plans work; unchecked steps and expected outcomes are not verification evidence. Do not edit the owner's dirty main checkout. Commit only explicit task paths after review.

Read, in this order:

1. [Documentation index](../index.md), [capability matrix](../capability_status_matrix.md), and [design routing](../design/README.md).
2. [Accepted evaluated-execution design](../design/workflow_lisp_evaluated_execution.md), **all sections**, especially §§4.2.1–4.4, 6–10, 13, 17–18.
3. [Parent delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md), decisions, global constraints, Phase 3, delivery order and phase closeout.
4. [Phase 2 plan](2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md), shared schema and final “Verification Commands And Phase 3 Handoff”; [Phase 2 closeout](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md).
5. Normative owners [state](../../specs/state.md), [I/O](../../specs/io.md), [CLI](../../specs/cli.md), [versioning](../../specs/versioning.md); [command adapter contract](../design/workflow_command_adapter_contract.md), [core calculus](../design/workflow_lisp_core_calculus_middle_end.md), and relevant prompt/run-reference contracts reached from the index.

The whole authorized goal remains Phases **3–7**, in the parent's order: Phase 3 → early Phase 6a pilot → consumer-selected Phase 4 additions (including W3) and independent Phase 5 → Phase 6b migration → Phase 7 retirement. Phase 5 can start after Phase 3 alongside the pilot; a consumer advances independently when its capabilities land. This plan closes only Phase 3 and hands remaining work back to the whole-goal ledger. It neither retires targets nor selects a new effect class, portable context, W3 grammar or native-session semantics.

First-release classes are commands (external tools and certified adapters), portable **composed** providers, in-memory procedure/workflow calls, and path-mode run references. Preserve all admitted generic/reference/value bindings, `bind-proc`, bounded `let-proc`, compiled boundary views, macros, typed prompts/results and arbitrary admitted nesting. No new “unsupported position” refusal, wrapper requirement, size/evaluation budget or known-defect allowlist is an acceptable substitute. Existing source-language restrictions and explicit later-class `closed_program_gap` refusals remain distinct.

**Approach and cost:** Keep one evaluator and reuse existing boundary/ledger logic instead of constructing an `ExecutableWorkflow` for 2.35. This makes legacy readers require explicit profile adapters and retains two execution routes until the owner's Phase 7 decision; suffix invalidation deliberately reruns more effects than a future declared-file dependency graph would.

## Contract Decisions Before Dependent Code

The accepted design settles runtime semantics. Its bounded 2026-10-02 amendment supplies concrete wire choices in §§8.4, 8.5, 9.1.1–9.1.2 and V9; the amendment passed independent Design review at SHA256 `bc84271c11f6dc5235e283c65181133c56062750c17ba6a58d9111e68d358e1d` on 2026-10-02, with no design findings. The choices below are reviewed contracts, not implementation evidence. Tasks 1–4 are concretely ready under the settled contracts and narrow validation/compatibility corrections in this plan; R12's remaining selected-owner/traversal prerequisite does not block them.

| Decision | Existing evidence / missing detail | Blocks |
| --- | --- | --- |
| Typed external-tool `:inputs` | Amendment §9.1.1 selects target-2.35 `:argv` plus `:inputs ((field expression) ...)`, checked expression types and existing ordered closed `document` pairs. Binding `kind` selects external `inputs.json` as the final argv token versus unchanged certified inline JSON. Preserve absent versus present-empty, source operand order, attempt-independent byte/type evidence and old bytes; no second schema or configurable transport | Task 12 |
| Profile and authority wire spelling | Amendment §8.4/V9 selects `schema_version: "3.0"` and existing key `result_persistence_profile: "evaluated_execution.v1"` in header/view; closed schema `workflow-lisp/closed-program/1` and `table/1` stay unchanged. `memo_offset` is the exclusive end byte of the represented complete prefix, zero when empty. Route authority before legacy checks; reject unknown authority selectors without fallback | Tasks 5, 9–11, 16 |
| Public invalidation entry | Amendment §8.5 selects `orchestrator invalidate RUN_ID IDENTITY [--state-dir DIR]`, resume's root resolution, exact report identity, shared writer lock, stored-authority/journal checks without fresh compilation/input-equality, JSON range/exit 0 or diagnostic/exit 2. No automatic resume; old profiles refuse `invalidate_profile_unsupported`, malformed authority `memo_inconsistent` | Task 8 |
| Artifact handoff | Amendment §9.1.2 preserves typed result-path checks before commit, actual external files, C6 declared-read snapshots/path-content evidence and C9 value lineage. `must_exist` does not promise newly produced bytes/versioned freshness; C9 alone does not attest a file read. Repeat watchdog/verified-drain handoff through public evaluated entries; add no generic closed registry or flat `artifact_versions`/`artifact_consumes` view | Tasks 6–7 as affected, 14, 16 |
| R12 authored argv substitution | **Implementation prerequisite:** record the selected existing typed substitution owner and any checked closed metadata/traversal delta under the independently reviewed R12 contract for `${inputs.*}` and `${loop.index}`. Preserve callee/native input bindings and the innermost active loop, without flat state or guessing canonical generated names. Record exact paths/selectors and exclusive ownership transfer before the Task 6 substitution sub-batch | Task 6 substitution sub-batch, its Task 13/14 consumer parity evidence |

If an implementation counterexample requires changing a semantic contract, return it to Design with an executable specimen. A compiler/runtime defect within admitted forms is a repair, not a reason to ask the owner to narrow scope. Independent review of the amendment is required before dependent code, not a new permission to use SDD.

## Source Map And Ownership

These are actual baseline seams. New paths below are the planned production split, not a framework. Every new module must stay **under 500 lines**, every new function at **cyclomatic complexity <12**; split by the responsibilities below, not one module per node. Existing large owners receive narrow adapters/extractions only. Review a function's actual branches; an unavailable complexity tool is not evidence of compliance.

| Owner | Responsibility / reuse boundary |
| --- | --- |
| `orchestrator/workflow_lisp/closed/{program,check,sites,values,effects,artifact,target}.py` | Existing checked representation, identity annotations and compiler configuration. `ClosedProgram.from_artifact` validates stored authority; `build_closed_program_bundle(FrontendBuildRequest)` builds fresh authority. Its cache publication is not durable run publication |
| `orchestrator/workflow/pure_expr.py` | `evaluate_pure_operator`, `evaluate_pure_expr` and descriptor coercion remain the only operator implementation. Closed `op` contains a small catalog payload; actual closed values also include `list_map` and `path_join` |
| New `orchestrator/workflow/evaluated/{__init__,values,machine,calls}.py` | Typed immutable values with dependency evidence; structured evaluation; checked boundary transport. No persisted environment or runtime proc refs |
| New `orchestrator/workflow/evaluated/{memo,authority,attempts,runtime}.py` | Journal/reducer, durable immutable header/program, one-attempt transition and shared run/resume/preflight driver respectively |
| New `orchestrator/workflow/evaluated/{closure,commands,prompts,providers,run_ref}.py` | File evidence/interpreter pins; ordinary command performer; executor-free prompt assembly; portable provider performer; existing run-reference coordinator adapter |
| New `orchestrator/workflow/evaluated/{views,inputs}.py` | Read-only profile projection and typed-document boundary; create `inputs.py` only with Task 12's concrete consumer |
| `orchestrator/contracts/output_contract.py`, `orchestrator/workflow/type_descriptor.py` | Existing typed transport/output validation and `compiled_boundary_rows`. Reuse rather than flattening types or accepting matching labels |
| `orchestrator/exec/step_executor.py`, `orchestrator/providers/executor.py` | External dispatch seams. Adapt capture destinations/one-dispatch behavior narrowly; never call the stateful `WorkflowExecutor` wrappers as performers |
| `orchestrator/workflow/prompting.py`, `orchestrator/workflow_lisp/typed_prompt_inputs.py`, `orchestrator/deps/content_snapshot.py` | Prompt calculus, renderers and dependency bytes. Extract shared pure assembly only when existing helpers cannot be called directly |
| `orchestrator/workflow/run_ref/{runtime,ledger,path_compile,child}.py` | Existing pending/final/reconcile ledger and child launch. Path compilation and child execution currently force flat; both need evaluated dispatch |
| `orchestrator/_common/io_atomic.py`, `orchestrator/run_lock.py` | Reuse `durable_atomic_write`, `run_writer_lock`/reserved lock and workspace lock. Explicitly fsync newly created ancestor entries and empty memo |
| `orchestrator/cli/commands/{run,resume,report}.py`, `orchestrator/cli/main.py`; new `orchestrator/cli/commands/{evaluated,invalidate}.py` | Select entry target/profile before flat loading; reuse CLI inputs/manifests/root resolution. Keep adapters small |
| `orchestrator/state.py`; dashboard/monitor/watchdog owners in Tasks 10–11 | Route profile before legacy status/schema/frame checks; discover a valid evaluated root even without `state.json` |
| `orchestrator/workflow/dataflow.py` | Semantic reference for publication, consumes and freshness. Stateful `DataflowManager` is not a drop-in evaluated performer; Design owns any required extraction |

Task ownership is exclusive during a write task. A later task may edit an earlier owner's narrow seam only after its prerequisite integrates and the coordinator transfers ownership. Scouts/reviewers may run in parallel; do not give simultaneous writers the CLI, `state.py`, compiler schema or shared evaluator. Each delegation names **role + artifact type**, e.g. `impl_code_phase3_memo`; Implementation/Revision code uses Luna 6 xhigh, with bounded-work escalation to Sol 6.1 high; code/plan Review uses Sol 6.1 high, Design uses Astra 6 xhigh, per AGENTS.md. Return corrections to the author and use an independent reviewer. Coordinator inspects actual diff and evidence before integration.

## Shared Implementation Contracts

These obligations apply to every task; later tasks may not silently undo them.

1. **Values and calls:** preserve parser/ANF order, selected-arm prefixes, join-body halt semantics and loop exhaustion; strict Bool; no 256-node program limit. Evaluate arguments/captures once, then transport cached values. `call.boundary` supports direct pairs and checked caller/native input/output projections, 1:N, active unions, nominal/path constraints, generated identities and native ordering. Pure values and call transport check descriptor/path shape and refinements without filesystem reads; existence/content checks belong to initial bound inputs, new effect inputs/declared reads and newly produced effect results, with committed-input re-resolution governed by resume preflight. Committed-result replay never repeats result `must_exist` observations. Calls add activation frames but no memo entries. Definition-owned configuration and prompt asset bases survive source and compiled imports.
2. **Identity and dependency evidence:** instantiate the checked lexical sites/frames, replacing loop wildcards with iteration ordinals. Never derive identity from paths/spans, runtime visits or flattened step names. Dependency sets follow values through fields/records/lists, calls, loop/join/case bindings and conditions selecting a **value**; entering a branch does not by itself make its effect depend on the branch condition. Preserve exact escaped canonical text and identity digest.
3. **Authority:** one writer owns the memo for run/resume/invalidate. Publish checked program → header using same-directory durable atomic replacement, and sync new ancestors, empty journal and run root before any record/attempt/dispatch. Header/program never change after journal activity. Missing/invalid authority with a nonempty journal is `memo_inconsistent`; never reconstruct it from fresh source.
4. **Attempts:** reserve the next ordinal by synchronized `started` before exclusive attempt-directory creation; sync parent before dispatch. Collision preserves all evidence, records failure, launches nothing. One command/provider dispatch per memo attempt, even if executor retry configuration says otherwise. Only validated/projected committed inline value is authority; valid orphan output is never adopted. Result path, stdout/stderr and provider prompt belong to that immutable attempt.
5. **Resume:** under the existing locks, fresh compile and bound-input/header comparison **before reading any memo record**; validate stored artifact and header; execute the stored artifact. Read a complete prefix without repair; validate identities/classes/proofs/settlements; replay all active commits in journal order with freshly resolved inputs and stored values. Check the latest uncommitted command `started` evidence before stopping. Refuse unreachable later commits. No tail repair, view replacement, launch or reconciliation until preflight passes. Check again on encounter. Preflight, readers and execution use the same evaluator with different effect-boundary actions, not a second planner.
6. **Terminals:** a completed terminal requires the same halt value and all coordinator settlements; a failed terminal may contain an uncommitted failure but no unsettled committed coordinator. Clean completed resume, effectful or pure-only, leaves memo bytes unchanged and reconciles nothing. Repeated preflight/pure failure appends no duplicate terminal. `started` reopens a failed terminal; invalidation reopens a terminal. Adjacent terminals fail validation.
7. **Closure:** hash stable-command workspace-path tokens and every declared file/directory/symlink with canonical logical evidence. Missing/unreadable/unsupported/cyclic evidence fails closed. Include caches and dotfiles. Check output/input/cache disjointness before creation and rehash before command commit. For latest uncommitted `started`, changed implementation bytes/targets refuse retry until restored, including a killed writer before `failed` and `must_not_repeat`; invalidation is no bypass. Package closure uses logical `package:orchestrator`, movable identical package bytes and verified execution origin, not a user-selectable base.
8. **Interpreters:** resolve a bare first command token once at run creation and record absolute path/digest. Resume ignores PATH re-resolution; changed bytes at that path yield `interpreter_changed` and continue; missing/unusable path yields `resume_interpreter_missing`. Interpreter evidence never enters effect-input digest. Commands set `PYTHONDONTWRITEBYTECODE=1`; the evaluator and tests must avoid contaminating a package closure with caches.
9. **Invalidation:** under the writer lock validate chosen active commit and the **whole** active suffix before appending one `invalidated` row anchored by the chosen commit's immutable byte offset. Any coordinator in the suffix refuses. Replay cancels only active commits in that preceding prefix; later retries survive. No per-effect invalidations, dependency-only shortcut or batch-intent protocol.
10. **Requests/results:** R1–R12 are the complete permitted differences from old requests. `context={}`, explicit workspace cwd, preserved params/policy/timeouts; no portable session/secrets/context capture. Preserve `asset_file` versus `input_file`, all admitted document slots, dependencies and collision-free typed input labels. Output validation is the existing contract validation including paths/finite numbers/active unions, followed by projection; stdout is never a result channel.
11. **Coordinators:** only checked class `run_ref` is a first-release coordinator. Reuse pending ledger → memo commit with inline proof → final settlement → `settled`; on hit reconcile from the actual memo proof, never infer coordinator class from optional proof presence. K7 synthetic parent carries only resolved `inputs`; visit key is parent run ID, root frame, no call frame, `root.<identity digest>`, visit 1. A committed child is never superseded.
12. **Readers:** complete-line prefix plus lock liveness; no writes, tail repair, dispatch or reconcile. `state.json` carries its represented prefix offset and is disposable. A failed view publication after a durable append stops the writer before further dispatch without undoing the commit. Never present stale completed output as current authority. Legacy readers/statuses remain unchanged on legacy profiles.

## Verification Protocol

Read the `tmux` skill before launching a long command. Run commands from this worktree root. Narrow tests first, with bytecode/cache disabled; new or renamed modules must be collected first. Each task below specifies its exact test module(s). For each listed new module `tests/test_example.py`, the exact command pattern is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest --collect-only -q -p no:cacheprovider tests/test_example.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -p no:cacheprovider --basetemp=/tmp/p3-task-N tests/test_example.py
```

Substitute the literal task number and listed module, not an unrestricted directory. RED must fail on the intended missing behavior, not import/fixture/setup accidents; GREEN must pass the same selector without weakening its assertion. Use real existing pytest fixtures/helpers; no new test framework. No literal prompt-phrase assertions: request parity compares assembled requests with the independent old route under the explicit R1–R12 relation, not a frozen prose snapshot. Fresh subprocess logs contain argv, exit code, head, ordered dispatch counts and artifact/memo digests. Retain public smoke/recovery logs under coordinator evidence; do not commit generated runs or credentials.

After narrow checks, broad/slow/full suites use `python -m pytest -q -n 16 --dist=worksteal` **alone in tmux**, with no other running agents or suite. Keep short basetemp under `/tmp`; verify **at least 30 GiB free scratch** first. `/home` had only 4.7 GiB free at planning: keep the checkout there for ES/bubblewrap visibility, but place pytest/run evidence scratch on `/tmp`. A checkout under `/tmp` is hidden by the ES sandbox's private `/tmp` bind. Do not erase another task's evidence or use disk-full/truncated output as a completed run.

The reusable baseline is the completed Phase 2 `d4f0e0f4` run: **20,288 passed, 275 failed, 36 skipped, 178 xfailed, zero errors**, exit 1. The Phase 2 report diagnoses six newly observed IDs versus Phase 0, including one subsequently repaired test caller; it does not establish a green suite or a full run at `71fbbb74`. Reuse its evidence only with the exact intervening-tree audit. Compare Phase 3 failure IDs/diagnostics against the appropriate baseline, investigate every newly observed failure using narrow paired checks, and never relabel the inherited red suite as passing.

The coordinator's fresh pre-change narrow baseline at `71fbbb74` passed `tests/test_workflow_lisp_target_evaluated_execution.py` and `tests/test_workflow_lisp_closed_program_artifact.py`: **67 passed in 4.41 s**, exit 0. Head/log/exit receipts are `phase3-baseline-narrow.*` in `.superpowers/sdd/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan/`. Reuse this baseline; do not rerun the entire inherited suite merely because the worktree is new.

## Task 1: Typed Values And Catalog Agreement

**Role/artifact:** Implementation / evaluator value code and meaningful unit tests. **Prerequisite:** accepted Phase 2; no pending wire decision.

**Files:** Create `orchestrator/workflow/evaluated/__init__.py`, `orchestrator/workflow/evaluated/values.py`, `tests/test_workflow_evaluated_values.py`. Modify `orchestrator/workflow/pure_expr.py` only if a tiny shared callable extraction is necessary; extend `tests/test_workflow_pure_catalog_agreement.py`.

- [x] RED: extend catalog agreement with closed values and typed operands, including finite-number refusals and path/record/list/union/optional values. Add values with more than 256 aggregate nodes; wrong Bool/Int substitution must refuse.
- [x] Run `tests/test_workflow_evaluated_values.py` and `tests/test_workflow_pure_catalog_agreement.py`; record intended failure.
- [x] Implement the minimum typed value/dependency carrier and immutable lexical lookup. Delegate operators to the existing catalog payload evaluator; preserve closed `list_map` and `path_join` semantics. Expose a narrow existing coercion helper if needed. Keep pure shape/refinement validation separate from filesystem checks at the owning input/effect boundary; `_coerce_value` alone does not validate a new effect result.
- [x] GREEN same modules; assert errors point to the failing application and include actual operands, not only the enclosing pure region. Carry a stored committed path through pure values with its original existence validator instrumented to fail if called; Task 3 extends this proof through call projections, and Tasks 8/10 prove public replay/read-only reconstruction while new invalid path inputs/results still refuse at their owning boundary. Inspect diff/size/complexity; review and commit owned paths.

Execution receipt (2026-10-02): integrated at `da19e2bb7e5bb853fc99a35dfb56e6241e96bc96` after independent conformity and quality PASS; coordinator verification on the integration worktree: **258 passed**. This closes Task 1 only; structured control and public runtime remain later tasks.

## Task 2: Structured Evaluation And Checked Identities

**Role/artifact:** Implementation / evaluator control code. **Prerequisite:** Task 1.

**Files:** Create `orchestrator/workflow/evaluated/machine.py`, `tests/test_workflow_evaluated_control.py`, `tests/test_workflow_evaluated_loops.py`. Reuse `closed/sites.py` annotations; amend it only for a demonstrated common identity defect.

- [x] RED: evaluate built/read-back programs using a test effect callback; cover `let`, `select` arm prefixes, nested `block`, strict `if`, `case`, join body/continuation (`halt` as join result), `jump`, bounded loops, matching `continue`, `done`, exhaustion, context and committed `result_path`. Include effectful aggregate/terminal positions and parser-ordered loop seed/budget.
- [x] Run the control and loop modules before their implementation/revision.
- [x] Implement one control machine with lexical environments and explicit control transfers. Calls initially use the checked strict positional path; no evaluation budget or payload serialization. Instantiate tagged site/frame annotations with loop ordinals rather than copying the spike's identity strings.
- [x] GREEN: three arms call one procedure inside two iterations; identities differ by call/iteration and all instantiate checked sites. Verify pure-binding insertions and escaped authored names; dependency sets distinguish selected values from mere branch entry. Commit after independent review.

Execution receipt (2026-10-02): integrated at `b92deb4f34888ce3e0c48d24d8282ca553c72187` after independent conformity and quality PASS. Coordinator verification of values, control and loops: **49 passed**. The initial review failure and causal correction remain preserved; loop result dependencies include the choices selecting done/exhaustion without unused state. Task 3 retains complete call transport; Task 5 retains public runtime.

## Task 3: Calls, Captures And Boundary Transport

**Role/artifact:** Implementation / call transport code. **Prerequisite:** Tasks 1–2.

**Files:** Create `orchestrator/workflow/evaluated/calls.py`, `tests/test_workflow_evaluated_calls.py`; modify `machine.py` narrow call dispatch. Reuse `orchestrator/workflow/type_descriptor.py`, existing boundary rows and contract validation.

- [ ] RED: port Phase 2 source builders for compiled imports, nominal/path/union projections, generated boundary views, bound refs and local captures into executable value/effect-count checks. An argument containing an effect is counted once before native permutation; a 1:N caller record binds both native slots; returned value projects back.
- [ ] Run `tests/test_workflow_evaluated_calls.py`. Include a caller with conflicting command/provider/prompt names to expose accidental consuming-entry configuration lookup.
- [ ] Apply checked direct/projection partitions to cached values, preserving union activity, inactive-path relaxation, capture prefix and complete generated units; bind native body parameters in native order. Instrument pure call transport of committed paths to prove no filesystem existence/content reread. Unannotated calls stay strict. Keep no runtime ref value, persisted call frame or extra effect entry.
- [ ] GREEN: same and imported generic helpers with different types/hooks, forwarded `bind-proc` and bounded `let-proc`, explicit versus omitted X1/X2 and `phase-target` X3 values. Compare X2/X3 against old-route values, not spelling. Add public run/resume execution to these fixtures in Task 13. Review/commit.

## Task 4: Journal Reducer, Locking And Atomic Invalidation Core

**Role/artifact:** Implementation / durable memo code. **Prerequisite:** Phase 2 sites/contracts; may start independently of Tasks 1–3 after shared schema review.

**Files:** Create `orchestrator/workflow/evaluated/memo.py`, `tests/test_workflow_evaluated_memo.py`, `tests/test_workflow_evaluated_memo_writes.py`; narrow `orchestrator/run_lock.py` adapter only if needed.

- [x] RED: valid record sequence, malformed class/site/proof, duplicate/adjacent terminals, torn tail, ordinal gaps/collisions and coordinator settlement mismatch. Build offset-based ranges with future retry commits and a coordinator later in the suffix.
- [x] Run `tests/test_workflow_evaluated_memo.py` and `tests/test_workflow_evaluated_memo_writes.py`.
- [x] Implement strict complete-line read/reduction and synchronized append under existing writer-lock ownership. Track offsets, active commits, latest starts, settlements and terminal reopening. Preserve complete unsynchronized-surviving records; only the writer after preflight can discard the incomplete tail. Supply one validated suffix-range append operation; never rewrite prior records.
- [x] GREEN: two writers yield `memo_busy`; reader never locks out the writer or repairs bytes. Fault injection yields no-or-entire invalidation, preserves later commits and rejects invalid anchors/coordinator suffix before append. Review/commit.

Execution receipt (2026-10-02): integrated at `2962dd44479b09c148f21a9499e254a613697df0` after independent conformity and quality PASS. Coordinator verification of both memo modules plus the existing process-level run-lock tests: **45 passed**. Task 6 retains C2 evidence-schema/hashing integration; Task 9 retains ledger authority/reconstruction. This closes Task 4 only, without declaring the public runtime complete.

## Task 5: Durable Run Authority And Minimal Public Execution

**Role/artifact:** Implementation / header publication, runtime skeleton and public CLI routing. **Prerequisite:** Tasks 1–4 and reviewed profile/header spelling.

**Files:** Create `orchestrator/workflow/evaluated/authority.py`, `orchestrator/workflow/evaluated/runtime.py`, `orchestrator/cli/commands/evaluated.py`, `tests/test_workflow_evaluated_authority.py`, `tests/test_workflow_evaluated_cli.py`. Modify `orchestrator/cli/commands/run.py`, `orchestrator/workflow_lisp/closed/target.py`, `tests/test_workflow_lisp_target_evaluated_execution.py` narrowly.

- [ ] RED: public dry-run and pure-only run from source, input defaults/missing/unknown/wrong type/nonfinite, publication failures at every file-write/fsync/rename/directory-sync boundary; no external dispatch or journal activity before authority is durable.
- [ ] Run both new modules plus `tests/test_workflow_lisp_target_evaluated_execution.py`.
- [ ] Route by actual entry target using the existing `SourceReadTrace` and closed build request; retain malformed-target diagnostic precedence. Bind/coerce all inputs before records. Publish immutable checked program then header, sync ancestors/empty journal/root, reuse existing workspace/run locks. Dry-run validates without authority allocation or dispatch. Keep old `run_workflow` path unchanged.
- [ ] The branch may expose only the implementation present at this point for task verification; do **not** publish 2.35 as runtime-complete, weaken admission or manufacture new gaps for missing adapters. Keep release enablement/availability claims pending Task 17; no merge/release of an incomplete first-release runtime.
- [ ] GREEN: `python -m orchestrator run <fixture.orc> --dry-run` then real pure-only public run exit 0; authority corruption refuses with no mutation; ordinary compile still writes checked artifact. Review/commit.

## Task 6: Closure Evidence And One-Dispatch Command Attempts

**Role/artifact:** Implementation / closure, command boundary and attempt code. **Prerequisite:** Tasks 4–5; independently reviewed artifact amendment if it affects command result publication. The R12 substitution sub-batch additionally requires independently reviewed typed substitution ownership/closed traversal details and recorded paths/selectors/ownership transfer from the decision table; closure and attempt work need not wait on that later sub-batch.

**Files:** Create `orchestrator/workflow/evaluated/closure.py`, `orchestrator/workflow/evaluated/commands.py`, `orchestrator/workflow/evaluated/attempts.py`, `tests/test_workflow_evaluated_commands.py`, `tests/test_workflow_evaluated_closure.py`. Modify `runtime.py` dispatch and `orchestrator/exec/step_executor.py` capture seam only as needed. Add only the exact typed substitution/compiler owners selected by independently reviewed Design before that sub-batch; their selection is not delegated to implementation guesswork.

- [ ] RED in both modules: a real script receives argv and certified inline JSON bytes, writes the instructed result and logs dispatch. Valid stdout/wrong output path/extra undeclared fields test validation and projection. Retryable failure still dispatches once. Count synchronized `started` before exclusive directory creation.
- [ ] Implement C2/C3/C4 evidence, interpreter pinning and disjoint destinations. Reuse StepExecutor external launch, existing output validators and argv substitution rendering. Ensure module/PYTHONPATH launch origin equals package closure origin before dispatch. Preserve attempt logs and only commit the projected typed value after rehash.
- [ ] GREEN `tests/test_workflow_evaluated_commands.py tests/test_workflow_evaluated_closure.py`: directory/dotfile/cache evidence, symlink retarget/cycle/escape, missing/unreadable paths, package relocation, package-helper modification, output aliases under closure; collision preserves evidence and prevents launch.
- [ ] Public run smoke exercises command and injected `validate_review_findings_v1` package closure with bytecode disabled; assert no new package cache. Formatting/moving source changes no effect identity. Store R9/R10/R12 exact request parity. Review/commit; split at the existing seams if implementation exceeds one bounded review: closure/interpreter evidence → attempt/command performer → gated substitution compatibility.
- [ ] After the R12 Design gate resolves, compare old/new public requests for unchanged authored argv from `workflows/library/generic_run_watchdog/watchdog.orc` and `workflows/library/verified_iteration_drain/drain.orc`: `${inputs.*}` and `${loop.index}` currently survive in closed literal nodes, while the spike only renders their literal bytes. Preserve callee/native inputs across checked caller projections, current escaping/coercion and the innermost active loop; cover conflicting caller/callee names, imported helpers and nested-loop indices. Carry only reviewed checked references/iteration facts; no fixture source rewriting, flat state, guessed canonical names or unrestricted runtime string resolver.

## Task 7: Executor-Free Prompt Assembly And Portable Providers

**Role/artifact:** Implementation / prompt assembly and provider performer code. **Prerequisite:** Tasks 3, 5–6; reviewed artifact delta if required.

**Files:** Create `orchestrator/workflow/evaluated/prompts.py`, `orchestrator/workflow/evaluated/providers.py`, `tests/test_workflow_evaluated_prompts.py`, `tests/test_workflow_evaluated_providers.py`. Narrow shared extractions in `orchestrator/workflow/prompting.py`, `orchestrator/workflow_lisp/typed_prompt_inputs.py`, `orchestrator/providers/executor.py`, `orchestrator/workflow/executor.py` only where both routes must call the same primitive; modify `runtime.py` dispatch.

- [ ] RED: public run via deterministic provider executable captures the entire request, writes typed result, and counts dispatch. Fixtures distinguish asset and input-file paths with different bytes, document slots/dependencies, repeated preferred labels plus authored `name__2`, caller versus producer config/base, nested call policies.
- [ ] Run `tests/test_workflow_evaluated_prompts.py tests/test_workflow_evaluated_providers.py`. If work exceeds a bounded implementation, review pure prompt assembly/parity before the separate provider one-dispatch integration sub-batch.
- [ ] Assemble using existing prompt calculus/renderers/content snapshots without state resolver/audit machinery. Bind every file read in resolved input. Use `ProviderExecutor.prepare_invocation`/`execute` with context empty, workspace cwd, policy/params and stable attempt site key. Ensure one external dispatch even with retry settings, and write immutable prompt/stdout/stderr evidence under the attempt.
- [ ] GREEN compares independent flat and evaluated requests field by field with only R1–R12 differences; test result schema/refinements/paths/projection and missing run-variable placeholder failure. No sessions, context capture or phased execution become admitted. Public stand-in smoke precedes later real-provider evidence. Review/commit.

## Task 8: Resume Preflight, Retry And Public Invalidation

**Role/artifact:** Implementation / public resume and continuation code. **Prerequisite:** Tasks 3–7 plus reviewed invalidation CLI contract.

**Files:** Modify `orchestrator/workflow/evaluated/{authority,attempts,runtime,memo}.py`, `orchestrator/cli/commands/{resume,evaluated}.py`, `orchestrator/cli/main.py`; create `orchestrator/cli/commands/invalidate.py`, `tests/test_workflow_evaluated_resume.py`, `tests/test_workflow_evaluated_invalidate.py`.

- [ ] RED: public resume semantic/input changes, provenance-only edits, stored artifact tampering, later committed input divergence dependent on earlier results, unreachable later commit, latest uncommitted closure mismatch, clean pure/effect terminal twice, failed terminal retry and repeated pure failure. Instrument committed-result `must_exist` validation to fail if called on replay; initial/new invalid path inputs and new invalid results must still refuse at their boundary.
- [ ] Run both new modules. Snapshot all run evidence before every refused preflight and prove byte identity afterward, including torn tail and stale view.
- [ ] Implement the ordered shared-evaluator preflight contract above and resume persisted profile before old StateManager loading. On retry compare latest uncommitted `started` closure evidence before another start; `must_not_repeat` refuses conservatively. Restore original bytes to permit only the ordinary next ordinal. Reuse pinned interpreter path, emit changed-byte diagnostic, refuse unusable path before memo reads.
- [ ] Wire public single-range invalidation with the accepted CLI shape. A file-only A→B dependency reruns the whole suffix and equals a fresh run; commits before A remain, future retry commits survive, any coordinator suffix refuses before append.
- [ ] GREEN public run/resume/invalidate logs and one-dispatch counts. No lock/header/profile bypass through service callers. Review/commit.

## Task 9: Run-Reference Coordinator And Evaluated Children

**Role/artifact:** Implementation / path run-reference adapter and child runtime integration. **Prerequisite:** Tasks 3–8 and profile wire contract.

**Files:** Create `orchestrator/workflow/evaluated/run_ref.py`, `tests/test_workflow_evaluated_run_ref.py`; modify `orchestrator/workflow/run_ref/{path_compile,child,runtime}.py` narrowly and `evaluated/{runtime,memo}.py` class/settlement dispatch. Preserve `ledger.py` wire contract.

- [ ] RED: public path run-ref beside command/provider effects and nested calls. Legacy parent→legacy child remains permitted; legacy parent→2.35 child remains refused without child dispatch; evaluated parent→legacy/evaluated path children succeeds. Capture K7 request/visit identity and inline proof. Preserve mode1 compiled-bundle 2.35 refusal and diagnostics even though `_execute_bundle` is shared; evaluated-child fixtures must expose flat-only path compilation without widening old callers.
- [ ] Run `tests/test_workflow_evaluated_run_ref.py`; retain exact old refusal selectors `tests/test_workflow_run_ref_child.py::test_mode1_child_refuses_evaluated_target_bundle_before_dispatch` and `tests/test_workflow_run_ref_child.py::test_mode2_child_refuses_compiled_evaluated_target_before_dispatch`. After integration run existing `tests/test_workflow_run_ref_path_compile.py tests/test_workflow_run_ref_child.py tests/test_run_ref_lifecycle_driver.py` as a scheduled broad check if slow.
- [ ] Reuse lifecycle allocation, pending settlement, final parent commit and recovery functions. Parent-state adapter exposes only resolved inputs; bind actual memo authority to the proof/settlement. Gate path compile/child dispatch on request/authority-owned caller admission as well as child target before compilation/launch; a caller-controlled profile assertion cannot authorize this route. Do not fabricate flat bundles, change source provenance/ledger schema or admit mode1 through the shared executor.
- [ ] GREEN: external kill at pending→memo gap starts one replacement child on resume; kill at memo→settle gap starts none and reconciles once. Terminal-with-missing-settlement/proof/class refuses; completed resume never reconciles. Changed declared files refuse before child launch or reconcile; invalidate refuses coordinator anywhere in suffix. Review/commit.

## Task 10: Derived Profile And Public Report/Dashboard

**Role/artifact:** Implementation / read-only state view and user-facing readers. **Prerequisite:** Tasks 8–9 and accepted V9 profile schema.

**Files:** Create `orchestrator/workflow/evaluated/views.py`, `tests/test_workflow_evaluated_views.py`, `tests/test_workflow_evaluated_readers.py`. Modify `orchestrator/state.py`, `orchestrator/cli/commands/report.py`, `orchestrator/dashboard/{scanner,projection,cursor,preview}.py`; narrow `dashboard/models.py` only for actual profile fields. Wire writer projection callback in `evaluated/runtime.py`.

- [ ] RED: public report and dashboard projection/cursor on real memo roots with absent/stale `state.json`, concurrent partial tail, running/settling lock states, immediate interruption after writer death, invalidated rows, per-attempt previews and terminal settlement corruption. Spies fail if a reader writes, dispatches, reconciles, compiles a flat workflow or repeats committed-result path-existence validation during pure reconstruction.
- [ ] Run `tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py`.
- [ ] Derive all V9 keys from checked program/header, complete memo prefix and launch-free replay. Route profile before legacy checks; discover authority roots without a view. Use validated terminal output only. Writer atomically replaces the derived view after every synchronized row; failure stops before further dispatch and leaves memo authority intact.
- [ ] GREEN new modules plus `tests/test_cli_report_command.py`, `tests/test_dashboard_cursor.py`, `tests/test_dashboard_projection.py` narrow/scheduled as appropriate. Demonstrate public report and dashboard server response from the actual run root, not only an in-memory state dict. Review/commit.

## Task 11: Monitor, Watchdog And Usage-Limit Readers

**Role/artifact:** Implementation / operations readers. **Prerequisite:** Task 10.

**Files:** Modify `orchestrator/monitor/{scanner,classifier,messages}.py`, `workflows/library/scripts/probe_orchestrator_run.py`, `scripts/watch_workflow_usage_limit.sh`; extend `tests/test_workflow_evaluated_readers.py`, `tests/test_monitor_classifier.py`, `tests/test_monitor_messages_emailer.py`, `tests/test_generic_run_watchdog.py`, `tests/test_watch_workflow_usage_limit.py`. Add no notification sending or scheduled jobs.

- [ ] RED: monitor scan without state snapshot, active settling, interrupted lock release without heartbeat, invalid terminal, retry attempt error/log resolution; watchdog and watcher consume actual evaluated run roots with latest-attempt paths.
- [ ] Run affected exact modules/selectors; use dry-run monitor/no SMTP. Existing state-only or stale-heartbeat branches must fail the new behavior.
- [ ] Share the profile read-only loader; map V2 statuses explicitly, preserve legacy semantics, resolve errors/previews through attempt identity. Do not synthesize heartbeat/step_visits/call_frames to satisfy old logic or infer stalled writer from absent heartbeat.
- [ ] GREEN: public `monitor --once --dry-run` classification, probe subprocess, watcher controlled one-cycle harness, and dashboard/report parity. Preserve no-write snapshot assertion and legacy fixture checks. Review/commit.

## Task 12: Typed Command Input Documents

**Role/artifact:** Implementation / reviewed source-to-runtime command input transport. **Prerequisite:** Task 6 and independently reviewed typed-input amendment. This task is mandatory Phase 3, not deferred to Phase 4.

**Files:** Create `orchestrator/workflow/evaluated/inputs.py`, `tests/test_workflow_evaluated_input_documents.py`. Modify exact selected owners `orchestrator/workflow_lisp/expressions.py`, `orchestrator/workflow_lisp/typecheck_effects.py`, `orchestrator/workflow_lisp/wcc/elaborate.py`, `orchestrator/workflow_lisp/closed/{values,effects,check,sites}.py`, `orchestrator/workflow/evaluated/commands.py` as required by the reviewed grammar/schema. Parser owns explicit document presence and expanded argv/input operand order; WCC and closed traversal retain both through once-only lowering, site annotation and checked read-back. Update other typed traversal owners only when the new field actually participates, after grep of all `CommandResultExpr` consumers and explicit owner transfer.

- [ ] RED public source fixture: list of records of unions, nested optional/path fields and candidate/earlier-trials values reach a real command's input file and return unchanged. Wrong shape/nonfinite/path inputs refuse before this command's `started` and launch; committed-input re-resolution failures report divergence before mutation. Preserve supplied defaults/labels/list order and once-only expanded source operand order across reordered argv/input sections.
- [ ] Run `tests/test_workflow_evaluated_input_documents.py`; retain certified-adapter inline-document byte parity and old-target grammar/serialization selectors.
- [ ] After independent amendment acceptance, carry `:inputs ((field expression) ...)` through parser/typechecker/checked closed `document` pairs with inferred checked field descriptors, retaining absent versus explicit-empty. Validate/project and compute canonical finite JSON bytes in memory before `started`; after exclusive allocation/disjointness checks publish `inputs.json` through the pinned run-root file owner and append its workspace-relative POSIX path as the final argv token. Binding kind retains signature-ordered certified inline JSON. Bind exact bytes and ordered checked contracts, never attempt path, to resolved input. No second serialized type map, configurable token transport or implicit referent read/hash.
- [ ] GREEN public compile/run/resume covers absent `:inputs` (no file/token) versus `:inputs ()` (`{}` file/token), duplicate external keys and certified missing/extra signature fields, recursive contracts including transportable maps (E5) and tampered checked expressions/signatures; no second serialized descriptor map. Retries at distinct attempt paths have identical input digests for identical payloads; committed reuse launches nothing and neither reads nor regenerates an edited/deleted old generated document. Compare certified inline and legacy argv/absent-field bytes without normalization; retain old-target grammar refusals. Run collection and affected Phase 2 construction/read-back selectors; review/commit.

## Task 13: Public Totality, Capture/Context And Growth Evidence

**Role/artifact:** Implementation / public integration evidence and bounded defect repairs. **Prerequisite:** Tasks 8–9, 12.

**Files:** Create `tests/test_workflow_evaluated_totality.py`, `tests/test_workflow_evaluated_programs.py`; reuse `tests/workflow_lisp_totality_matrix_{sources,locality,extensions}.py`, `tests/test_workflow_lisp_generic_unions_runtime.py` public builders, Phase 2 closed corpus/build helpers and existing checked-in spike fixtures. Extend `tests/test_workflow_evaluated_calls.py` with public-entry variants. Modify production only for demonstrated admitted-form defects with owner transfer.

- [ ] RED add target-2.35 runtime cases to the existing generated cells without rewriting old-target expected defects. Exercise direct, same-module helper and imported older-source helper routes, including forms whose old flat lowering fails. Record rule/exclusion/admitted counts before and after; no admitted runtime xfail.
- [ ] Run new module collection then narrow failing cells; integrate bounded fixes before scheduling the full matrix with `-n 16 --dist=worksteal` in tmux.
- [ ] Public compile/run/committed-boundary resume covers every admitted construct and all call/binding forms, source-owned config, native/caller boundary views, X1–X4, source/package relocation, macro provenance and pure refactoring identity invariance. Compare X2/X3 **values** with old execution; do not rely on compiler-only probes.
- [ ] Run compact `experiments/mlevolve_pair/search_compact.orc` retargeted to 2.35 with its real `leaves.py` and explicit closure. Compare all 72 scenario/budget decisions/order/spend/final results with the existing Python reference. Double state field count **and** branch count and run; record no expression-size refusal.
- [ ] GREEN public logs and immutable invocation counts. Reuse `std/improve` and both `experiments/orc_vs_single_call/workflows/{reviewed_change,best_of_n}.orc` unchanged apart from target plus explicit runtime inputs/manifest declarations. Their stand-ins are named as stand-ins; do not execute Phase 2's raising compile-only launcher. Review/commit evidence harness.
- [ ] Preserve the first-release consumer inventory: proposal/reviewed-change/**serial** best-of-N/search/watchdog/verified-drain need no parallel-map prerequisite. A typed `Outcome.ESCALATED` value is not an effect requesting human input. Exercise the actual selected class/form rather than inferring exclusions from filenames or domain words.

## Task 14: Real Providers And Artifact Handoff

**Role/artifact:** Implementation / reproducible integration specimen; coordinator owns external run evidence. **Prerequisite:** Tasks 7–13 and reviewed artifact-handoff contract.

**Files:** Create `tests/test_workflow_evaluated_artifacts.py`; extend `tests/test_workflow_evaluated_programs.py`. Any required minimal reusable production extraction follows the reviewed artifact amendment and an explicit task owner transfer; no general flat dataflow compatibility layer. Record evidence in `docs/reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md` only during Task 16.

- [ ] RED deterministic producer→consumer handoff repeats the watchdog or verified-drain owner contract through public evaluated run/resume: real producer files, required prompt dependency path/content snapshot, producer/consumer attempt identities, typed result-field provenance and once-only final publication. Check fresh dependency bytes on retry and changed-byte refusal/invalidation as C6/C8 require; cover path run-ref envelopes and provider result/bundle paths. Validate new required artifacts before result commit/new declared reads; pure replay does not re-observe an old committed result's `must_exist`. A path string or C9 alone is not file-read evidence, and `must_exist` alone is not newly produced bytes/versioned freshness.
- [ ] Run `tests/test_workflow_evaluated_artifacts.py tests/test_workflow_evaluated_programs.py` narrow selectors; rerun existing `tests/test_dataflow.py`/`tests/test_artifact_dataflow_integration.py` if extracting their shared logic.
- [ ] Prepare concrete isolated workspaces and actual runnable implementations for `std/improve`, reviewed-change and best-of-N. Run each first with deterministic providers, then an actual configured provider; retain model/provider/request IDs, typed output, effect counts, artifacts and public resume outcome. No assertion of semantic identity between nondeterministic live outputs; assert the scenario's typed/result contract and reuse invariants. Run workflow processes in `ptycho311` if these fixtures target EasySpin/PtychoPINN/paper, including tmux.
- [ ] GREEN live public run and completed/committed-boundary resume demonstrate no committed redispatch. A missing credential/provider is a recorded unresolved evidence blocker, not substituted by stand-ins or declared complete. Hand nominated consumers and concrete authoring pain points to Phase 6a; do not require finishing that pilot to close Phase 3. Review/commit only source/evidence metadata, not secrets.

## Task 15: External Kills And Durable Recovery Qualification

**Role/artifact:** Implementation / recovery integration tests; coordinator schedules slow runs. **Prerequisite:** Tasks 8–14.

**Files:** Create `tests/test_workflow_evaluated_recovery.py`; reuse external-process synchronization patterns from `tests/experiments/test_evaluated_execution_spike_kills.py` without importing spike runtime. Extend task-owned authority/resume/invalidate/run-ref tests only for missing targeted cases. Production crash hooks, if necessary, are dependency-injected test seams, not user-facing config.

- [ ] RED externally kill real public child processes at every §8.3 window: before/after synchronized `started`, exclusive allocation, dispatch/result write, finished-valid-result-before-commit, after commit, and both coordinator gaps. Include every reached effect in the three real-program stand-in scenarios; record expected/observed case counts.
- [ ] Add durable publication fault model covering write/fsync/rename/directory fsync and disappearance of unsynchronized writes. This is distinct from SIGKILL testing: do not claim process kills simulate power loss. Assert either valid authority survives every durable record or nothing dispatched.
- [ ] Run collection and individual crash selectors before the slow suite in tmux (`-q -n 16 --dist=worksteal`). On resume compare uninterrupted final value and dispatch logs; orphan valid output never becomes a result, reserved attempts never reuse directories, must-not-repeat conservatively refuses.
- [ ] GREEN includes closure mutation then kill before failure, suffix invalidation torn/complete-before-sync/after-sync/lost-ack windows, view publication failure after commit, complete-terminal idempotence, early later-commit divergence before reconcile/tail repair, and coordinator suffix refusal. No arbitrary sleeps for race ordering; use observable boundary synchronization and real external termination. Review/commit.

## Task 16: Normative Profile, CLI And Availability Documentation

**Role/artifact:** Revision / specs and documentation, followed by independent spec/design review. **Prerequisite:** Tasks 10–15; code truth and reviewed amendments.

**Files:** Modify `specs/{state,io,cli,versioning}.md`, `docs/design/workflow_lisp_evaluated_execution.md`, `docs/design/workflow_lisp_core_calculus_middle_end.md`, `docs/design/workflow_command_adapter_contract.md`, `docs/{index,capability_status_matrix,lisp_workflow_drafting_guide,runtime_execution_lifecycle}.md`, parent Phase 3 status in `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md`. Create `docs/reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md`. Other roadmap/whole-goal ledger changes remain coordinator-owned.

- [ ] Document exact authority/header/memo/view keys, record transitions, errors, profile/representation routing, lock liveness, artifact evidence, typed `:inputs`, invalidation and read-only readers. Cross-check key-for-key against actual files produced by public fixtures; add no phase status to normative contracts beyond availability metadata conventions.
- [ ] Replace “run/resume unavailable until Phase 3” only after required executable evidence passes. Preserve later effect exclusions, C5 promise limits, genuine open later-admission questions and old-target/runtime retention. Link Phase 6a next without calling Phase 3 the end of the whole goal.
- [ ] Report exact corpus/totality counts, scenario/kill counts, live-provider versus stand-in evidence, old-byte comparisons, raw suite exits and all failure dispositions. Never turn a compile-only Phase 2 result or historical spike count into fresh runtime evidence.
- [ ] Run existing narrow docs routing selectors after inspecting their names, a relative-link check of touched docs, `git diff --check`, and code-generated-key comparison. Tests should validate contract/dataflow/navigation, not literal explanatory prose. Independent spec/design reviewer verifies amendment and final docs; review/commit.

## Task 17: Phase-Wide Compatibility, Verification And Handoff

**Role/artifact:** Coordinator / integrated code/evidence verification; independent Review / phase closeout. **Prerequisite:** Tasks 1–16 with review dispositions complete.

- [ ] Inspect the entire integrated diff, actual changed owners and every fresh check; verify new modules/functions meet limits. Confirm no runtime import uses `experiments/evaluated_execution_spike`, no hidden flat lowering for admitted 2.35 calls/children, and no profile upgrade/old-target retirement slipped in.
- [ ] Repeat raw old-target artifact comparison at fixed source/package paths with `PYTHONHASHSEED=0`, reusing Phase 2's actual specimen method (2.14 kiss, 2.23 panel, 2.33 improve, 2.34 fixture; compiled imports and nested run-ref capsules). Report truthful package-pin changes separately from fixed-identity serialization equality. Never normalize artifacts or patch the production pin. Retain independent digest manifests and old run/resume smoke.
- [ ] Schedule one full suite alone in tmux after disk preflight and narrow/slow integration checks: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -n 16 --dist=worksteal -p no:cacheprovider --basetemp=/tmp/p3-full -rfE`. Capture tested SHA, command/environment, complete output, exit and failure IDs. `/tmp/p3-full` must be a fresh task-owned path; choose a short unused suffix if occupied.
- [ ] Compare with baseline and resolve every newly observed failure with matching serial/base probes. Reuse unchanged valid checks; repeat only when relevant code changes/failures justify it. Full red baseline evidence remains red; require no unexplained new failure, no pytest error/disk exhaustion and no weakened security or expectation.
- [ ] Fresh public compile/dry-run/run/resume/invalidate/report, dashboard/monitor/watchdog and actual-provider receipt after integration; use existing fixture commands recorded by the tests, not a reconstruction from memory. Smoke at least one selected maintained consumer and one path run-reference, plus the producer→consumer handoff.
- [ ] Independent whole-phase code/evidence reviewer of a model family different from implementer checks all findings and the coverage matrix below; independent documentation/spec review confirms published claims. Coordinator reviews actual diff and output, then completes checked steps and closeout report.
- [ ] Complete the parent's authorized “Merge to `main` by fast-forward; push” through a safe integration checkout when feasible, preserving every dirty owner file. If current delivery constraints prevent it, keep that parent item **open** in the closeout/whole-goal ledger with the concrete constraint and next safe integration step; isolated-branch completion does not satisfy it. Do not force/overwrite dirty main or bypass delivery constraints. No retirement decision is inferred. Hand Phase 6a nominees, Phase 4 capability needs, independent Phase 5 and remaining Phase 6b/7 work to the whole-goal ledger and continue the user's authorized Phases 3–7 goal.

## Evidence Coverage Matrix

Every row requires fresh public execution/resume unless explicitly a compile/read-back or crash-model check; internal unit tests support, but do not replace, that evidence. The nine parent milestones are all represented, and each applicable design §17/18 obligation has an owner.

| Parent/design obligation | Task / concrete evidence |
| --- | --- |
| Values; single pure catalog | 1, 13: catalog agreement, typed finite boundaries, diagnostic operands/application location |
| All admitted constructs/nesting; totality in direct/same/imported helper | 2–3, 13: target-2.35 matrix, no admitted known defect; old-source loop-in-branch imports avoid flat lowering |
| Memo and full resume table | 4–8, 15: public stops/retries/commit authority and every allocation window |
| Typed input document | 12: recursive round-trip, validation before `started`, absent/empty distinction, source-order effects, attempt-independent digest, generated-file tampering non-authority and raw certified/legacy byte parity |
| Command/provider performers | 6–7, 13–14: std/improve and both single-call programs, stand-ins **then live** |
| Calls and path run references | 3, 9, 13: in-memory calls/captures/boundaries; legacy/evaluated parent-child admission matrix, retained mode1 refusal and two coordinator gaps |
| Derived views/readers | 10–11: actual report/dashboard/monitor/probe/watcher entries, missing/stale view and concurrent tail |
| Public compile/dry-run/run/resume | 5, 8–9, 12–15, 17: successful and refusing inputs/source/profile paths, consumer nominees |
| State specification matches code | 16–17: key-for-key real header/journal/view comparison and routed docs |
| Compact search and growth | 13: all 72 reference pairs; doubled fields and branches |
| Identity/sites/provenance | 2–3, 13: call/loop frames, escaped labels, aggregate/control traversal; formatting/source/package move; independent memo-to-site check |
| Behavioral and request parity | 6–7, 13–14: ordered identities/input/result digests/final value where old route accepts; every request field equal except named R1–R12 rules; gated typed substitution preserves native/callee inputs, escapes/coercion and innermost loop in calls/imports/nested loops |
| Existing-target bytes and runs | 17: raw artifacts, controlled serialization plus honest real-pin differences, old resume |
| File-only dependency and suffix invalidation | 8, 15: A writes/B fixed-name reads; fresh-run equality and atomic range crash windows |
| Closure with external caches; undeclared/malformed closure | 6, 8: actual Python package/cache placement, missing declaration remains build refusal, changed wrapper/helper refuses reuse/retry |
| Interpreter fixed for run | 6, 8: PATH change ignored, changed bytes diagnostic and continue, missing/nonlaunchable pin refuses before memo read |
| Valid terminal settlements; coordinator outside run-ref | 9–10: corrupt proof/class/settled terminal gives no outputs; later coordinators remain excluded, no trial admission claim |
| Durable authority and attempt reservation | 5–6, 15: write/fsync/rename/ancestor/empty-journal fault model plus public external kills; orphan output never authoritative |
| Retry after closure change | 6, 8, 15: failed and killed command, package helper, must-not-repeat, restoration and invalidation non-bypass |
| Clean terminal resume | 8, 15: effectful and pure-only resume twice, identical memo, repeated failures do not duplicate terminal |
| One-dispatch accounting | 6–8: executor retryable failure produces exactly one start/directory/dispatch/failure, next explicit resume ordinal |
| Early divergence | 8–9, 15: later commit depending on earlier values checked before launch, reconcile, tail repair or view write |
| Prompt assembly outside executor | 7: source-kind lookup distinction, document slots, dependency snapshots, typed labels and owner configuration; public parity |
| Evaluation determined by program/inputs/commits | 1–3, 8, 10: replay same trace with zero launches; instrumented pure call/replay/read-only reconstruction proves no repeated committed-result existence read; new invalid path inputs/results still refuse at their boundary |
| X1/X2/X3/X4 runtime values | 3, 7, 13: omitted/explicit/carried RunCtx/PhaseCtx, phase target equality, committed result-path resume |
| Complete specialization and source ownership | 3, 13: same-key captures once, distinct proc/workflow/value specializations; selected producer config/logical asset base wins |
| Compiled call boundary evaluator | 3, 13: 1:N, union activity, strict direct captures, generated signatures and once-only result/input projection |
| Common command config and builtin adapter | 6, 8, 13: both origins, dirs/symlinks/content, unused semantic manifest mutation, moving package, shadowing rejection and old unchanged serialization |
| Artifact production/consumption/freshness/lineage | 14: reviewed admitted producer→consumer contract, actual bytes/provenance and resume/invalidation; no substitution by memo-only values |
| P1–P7 compiler/read-back obligations already delivered | Reuse Phase 2 receipts; rerun affected modules if 12 or a defect repair changes construction/checking. Compiler evidence is never substituted for the runtime rows above |

## Completion Checklist

- [ ] All contract decisions incorporated from independently reviewed Design; no unresolved first-release semantics hidden in implementation.
- [ ] All seventeen tasks reviewed, task checks collected/run, and every applicable matrix row has linked fresh evidence.
- [ ] No known admitted-composition defect, duplicate committed dispatch, mutable authority or unvalidated terminal output.
- [ ] Actual providers and artifact handoff proven, or Phase 3 explicitly remains incomplete with concrete missing evidence.
- [ ] Old-target bytes/pins/runs audited; complete phase suite and every new failure disposition recorded honestly.
- [ ] Coordinator inspected integrated diff and evidence; independent whole-phase code and spec/docs reviews complete.
- [ ] Parent fast-forward to `main` and push completed safely, or explicitly still open with concrete constraint and next integration step while dirty owner files remain preserved; no branch-only delivery claim. Phase 6a/4/5/6b/7 remain tracked and execution continues toward the whole user goal.
