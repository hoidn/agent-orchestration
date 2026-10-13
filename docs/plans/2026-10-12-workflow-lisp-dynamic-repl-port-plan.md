# Workflow Lisp Dynamic REPL Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. The coordinator delegates implementation and independent review, integrates the changes, and owns final verification. Execution is already authorized; do not ask for confirmation again.

**Goal:** Port the upstream REPL to this branch, preserving evaluated targets 2.35/2.36 and adding inspection and pure expressions for native target 3.0.

**Status:** Implemented and independently reviewed on `feat/orc-dynamic-core-cutover`. Bounded REPL/owner acceptance passes; the broad campaign remains RED with the baseline and timing qualification limits recorded below. This is not DC-P adoption or a default-profile change.

**Architecture:** Keep one public REPL command with profile-specific capture/expression adapters, using each profile's ordinary source compiler, evaluator and persisted authority. Effects execute only through explicit `:run` and the public run handler. Native attachment requires an explicitly loaded module with the same semantic program digest; schema 3.1 has no durable source-rebuild recipe.

**Tech stack:** Existing Python CLI/frontend/runtime, standard-library input/readline, pytest and tmux. No new dependency, parser, operator evaluator, persistence profile, effect ledger or migration.

**Authority:** [Documentation hub](../index.md), [capability matrix](../capability_status_matrix.md), [design routing](../design/README.md), [REPL design](../design/workflow_lisp_repl.md), [native design §9](../design/workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate), [CLI](../../specs/cli.md#dynamic-execution), [native version profile](../../specs/versioning.md#branch-qualified-target-30), [State](../../specs/state.md#dynamic-fresh-run-authority) and [test guide](../../tests/README.md). The REPL design owns adapter contracts; this plan owns ordering and execution evidence.

**Selection and provenance:** The user explicitly selected native 3.0 adaptation while preserving upstream typed 2.35/2.36 behavior. Destination begins at `611d9e25` in `/var/tmp/agent-orchestration-orc-dynamic-core`. The selected committed source is revision `a761b1c62bb2e492eb30e9f03bbe416468ce31b0` from `feature/orc-repl`, available in `/home/ollie/Documents/agent-orchestration-repl`. At initial inspection, `origin/main` at `ce8a41d76fe34c6ba01edbb2002a72bdaebb729a` did not supply the REPL. A later fetch reached `2372a9b7eccfcd6321aafc10fd72ac7167776149`, which includes that source and separate print/consolidation changes. Retain the selected source pin; do not merge static main wholesale or copy the shared main checkout. The later capture-constructor adjustment accompanies print's additional evaluator field, absent here; the port's existing constructor remains compatible. The final fetch still has `origin/main` at `2372a9b7`; the local source branch subsequently advanced to `2a393346` with separate module-introspection commands. That later extension is outside this selected port.

**Scope:** Preserve `:load`, `:run`, `:attach`, `:bindings`, `:result`, `:help`, `:quit`, one expression per line, pure module calls and ordinary diagnostics. No entered-expression effects, new definitions, multiline/history, interactive resume, dynamic adoption/DC-P selection, production migration or paid provider qualification. Native inspection is checked reconstruction from existing physical records, not a new historical memo or recovery guarantee. New modules stay below 500 lines.

**Tradeoff:** Reusing internal evaluator/source seams avoids semantic duplication but couples inspection to those seams. Native source-independent attachment and full historical effect-operand authenticity are unavailable without a separately designed durable contract; closures remain internal values and cannot cross external data boundaries.

## Reach and ownership

| Surface | Files and responsibility |
| --- | --- |
| Typed transient compiler context | `orchestrator/workflow_lisp/workflows.py`, `compiler.py`, `closed/frontend.py`, `closed/artifact.py`; preserve constructors, compile wrapper, emitted artifacts and digests |
| Target-2.36 dependency | Selected W3 source hunks from `8e6e06b215c86fd08fd533aec3909481a6e1ccf6`, enumerated in Task 1; preserve native admission/dispatch and older-target contracts |
| Typed inspection | `orchestrator/workflow/evaluated/views.py`; new `capture.py`; new `orchestrator/workflow_lisp/repl_expr.py`; reuse checked replay and ordinary expression semantics |
| Shared public command/config/exports | New `orchestrator/cli/commands/repl.py`, `commands/__init__.py`, `cli/main.py`, `pyproject.toml`; preserve existing profile dispatch, frontend flags and public run option validation |
| Native adapter seams | `orchestrator/workflow/dynamic/evaluator.py`, new `capture.py`, `orchestrator/workflow_lisp/dynamic/source.py`, `build.py`, new `repl_expr.py`; existing `state.py::load_dynamic_run` stays the persisted loader |
| Tests and fixtures | New `tests/test_workflow_evaluated_repl.py`, new `tests/test_workflow_dynamic_repl.py`, existing closed-build, evaluated, native and public reader suites; existing native `.orc` fixtures and deterministic command/provider probes where appropriate |
| Durable docs | New `docs/design/workflow_lisp_repl.md`; `docs/design/README.md`, `docs/index.md`, `docs/capability_status_matrix.md`, `docs/lisp_workflow_drafting_guide.md`, `specs/cli.md`, `specs/state.md`, `specs/index.md`, `specs/dsl.md` and the evaluated-execution design; preserve profile-specific authority |
| Historical reproduction | `experiments/dynamic_core_evaluation/README.md`; preserve frozen runtime/comparator/packet pins and make the historical checkout explicit if current-tree runtime changes invalidate its old command |

Before edits, inspect callers of `compile_typed_program`, `Stage3CompileResult`,
`ClosedProgramBuildResult`, evaluated `views._replay`, native `evaluate`, native
build results and the public run handler. Avoid replacing shared compiler files:
the destination already contains native patches. No user run files, source
inputs, persisted programs, headers or state formats migrate.

Use Luna 6 xhigh for bounded code implementation/revision, escalating native
integration to Sol 6.1 high when beyond a bounded task. Sol 6.1 high independently
reviews code/plans and revises docs; Astra 6 xhigh owns architectural decisions
and independent design review. Each assignment names its role and artifact.
The coordinator inspects the complete diff and verification receipts personally.

## Task 1: Import shared typed prerequisites, then port the upstream REPL

**Files:** The typed context, inspection, shared command and packaging rows above;
`tests/test_workflow_evaluated_repl.py` and
`tests/test_workflow_lisp_closed_program_compile_cli.py`.

- [x] **Task 1a, shared prerequisite checkpoint before the seven REPL commits:** The destination only admits typed targets through 2.35 plus native 3.0. REPL `repl_expr.py` calls the upstream local-hook feature predicate and changed elaboration API; four upstream public cases require 2.36. First port the four code changes and two behavioral test modules from bound-capture fix `b11e678dc4081014c8ca04cbf14e86cea5e53776`: `closed/build.py`, `closed/preparation_check.py`, `functions.py`, `typecheck_dispatch.py`, `tests/test_workflow_lisp_bound_capture_identity.py`, and `tests/test_workflow_lisp_bound_capture_integrity.py`. Then import needed implementation from committed W3 `8e6e06b215c86fd08fd533aec3909481a6e1ccf6`, using its `docs/design/workflow_lisp_write_once.md` §6 as source authority. Never substitute a version-gate-only patch, skip 2.36 tests or independently reinvent W3. This shared compiler integration exceeds a bounded mechanical port: assign Sol 6.1 high and independently review the selected dependency closure before applying it.

The candidate production dependency files are:

```text
orchestrator/workflow_lisp/{syntax,expressions,expression_traversal,functions,conditionals}.py
orchestrator/workflow_lisp/{compiler,compiler_session,workflows,modules}.py
orchestrator/workflow_lisp/{procedure_specialization,procedure_typecheck,typecheck_context,typecheck_dispatch}.py
orchestrator/workflow_lisp/closed/{build,check,command_templates,frontend,preparation_check}.py
orchestrator/workflow_lisp/lowering/{context,control_loops}.py
orchestrator/workflow_lisp/wcc/{defunctionalize,elaborate,hygiene,model}.py
orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc
orchestrator/workflow/validation.py
orchestrator/workflow/run_ref/{bundle_transport,config}.py
```

Use `git show 8e6e06b2 -- <paths>` as the patch authority, resolving hunks onto
the native branch. The scout's cumulative dry-application of bound-capture then
W3 leaves only the expected `syntax.py` catalog conflict; applying W3 without
its prerequisite also conflicts in `closed/build.py` and `typecheck_dispatch.py`.
Preserve the native 3.0 target/header/
`define` handling. Evaluated execution must select exactly 2.35/2.36, and W3
local-hook inference exactly 2.36, never accidentally 3.0 through a broad version
comparison. Inspect its associated test changes in local-hook signatures,
let-proc bindings, W3 target, compiler sessions, modules, use-site scope,
closed frontend/artifact/shared-union/command captures, older target gates,
shared validation, LSP parity and packaging. Port behavioral dependency tests/fixtures and
necessary existing-test updates; collect every added/renamed module. Start with
`tests/test_workflow_lisp_w3_target.py`,
`tests/test_workflow_lisp_local_hook_signatures.py`,
`tests/test_workflow_lisp_let_proc_bindings.py` and
`tests/test_workflow_lisp_modules.py`, then the affected existing owner suites.
Include a public target-2.36 inferred-hook compile/run smoke and preserve native
3.0 import and dispatch checks. Run both bound-capture suites plus W3 target,
local-hook, retained ProcRef capture and native source/program/CLI selectors
before independent Task 1a review; only then begin Task 1b. Existing typed artifact parity is scoped to
unchanged sources/targets; new 2.36 support deliberately adds its own artifacts.

Do not import the commit's example migration, route-readiness promotion,
historical reports/plans or broad documentation claims. `route_readiness.py`,
its test delta, registry and maintained example sources are excluded: the scout
confirmed they only promote an unrelated evaluated example and neither the
compiler nor packaging depends on them. Avoid importing source-consumer, pilot,
corpus and example migrations through their tests. Packaging's W3 assertion
uses `_write_std_improve_parity_workspace` from the LSP parity suite; include
that helper with the corresponding scoped packaging test. Task 3 must update current W3 capability and
owning normative/design contracts to reflect this selected dependency import,
without rewriting the frozen comparison history or selecting adoption.

- [x] **Task 1b, upstream REPL checkpoint:** Import the final upstream 16-case behavioral module first, including the supported `list/empty?` correction; collect both touched test modules and record the expected missing-REPL failure. Do not assert prompt wording or introduce deep list equality.
- [x] Port the selected code hunks from the exact upstream commits below, preserving destination native dispatch and interfaces. Resolve shared-file conflicts against the destination rather than replacing files wholesale.

| Order | Commit | Selected changes |
| --- | --- | --- |
| 1 | `e142f281fa06939d830979b0086a995e5a378547` | `ExpressionCompileContext`; transient Stage-3/build products; preserving `compile_typed_program` wrapper; compile CLI regression |
| 2 | `bab0fbc1385397e27a92567686259c4371ec6b5e` | Injectable evaluator in existing checked evaluated replay, with unchanged default |
| 3 | `e72013285544630ff2323ce27b4284d368fc4b7d` | New typed `capture.py` with lexical frame trace and ordinary terminal validation |
| 4 | `9014305ae2f245cec890a84bf98190d23c8d46d4` | Ordinary frontend/type/lowering/evaluator expression adapter |
| 5 | `dbb2a0b91a646b7fa4a1396e97c4bd6813e92358` | Public REPL command, exports, CLI registration and installed console entry |
| 6 | `22e6bdf42d323977cf33d482b2b5d1e956173b09` | Source public REPL behavioral module |
| 7 | `fe49c1c4ed4bb3f28b8701aa3be2767633e9d294` | Test-only `list/empty?` correction; do not import historical documentation receipts as current evidence |

- [x] Adapt the source `MemoSnapshot` import to destination `orchestrator.workflow.evaluated.memo`, where that class currently lives; do not bring in the unrelated upstream memo reducer split.
- [x] Preserve pure typed function/procedure calls, innermost capture and shadowing, actual completed entry results, checked stops/failures, recipe-only typed attachment, digest mismatch detachment and session/command state-directory forwarding. Context remains transient and cannot change serialized artifact or digest bytes. Failed loads retain compatible session state.
- [x] Execute the narrow typed checks below; review every conflict and changed caller. New modules remain below 500 lines; defer any necessary extraction of existing typed CLI helpers until actual integration requires it.

```bash
pytest --collect-only -q tests/test_workflow_evaluated_repl.py tests/test_workflow_lisp_closed_program_compile_cli.py
pytest -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_lisp_build_in_memory.py::test_read_only_build_matches_persistent_prefix_without_mutating_workspace
pytest -q tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py
pytest -q tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_view_publication.py
```

Expected: successful collection, all 16 upstream REPL cases pass, and no
artifact/digest, public CLI, replay or reader regression. Long selectors move
to tmux using `-q -n 16 --dist=worksteal`. Independent code review precedes native
integration; retain fresh logs rather than copying upstream pass counts.

## Task 2: Add the reviewed native capture and expression adapters

**Design prerequisite:** The Design agent has supplied the following architecture;
its durable native section in `docs/design/workflow_lisp_repl.md` must be finalized
and independently reviewed before implementation. Resolve any difference against
that authoritative section, not the typed memo design. Feasibility is established
by the public tests below before acceptance, not by inspection alone.

- [x] Confirm the durable native design and independent review; retain one CLI and profile-specific ordinary evaluator/source paths, no schema changes and no new effect tracking.
- [x] Add public behavioral tests before implementation, using real native compile/run/state loading and deterministic local effects. Collect the new module and record the missing-native-support failure.
- [x] In `workflow_lisp/dynamic/source.py` and `build.py`, retain the ordinary `_Lowerer` context transiently in `DynamicSourceCompilation`/`DynamicProgramBuildResult`, excluded from equality/repr/artifacts. Implement `workflow_lisp/dynamic/repl_expr.py` through the existing reader and lowering path, with one entered expression and the captured native environment. No new operator or parser implementation.
- [x] Refactor `workflow/dynamic/evaluator.py::evaluate` into its unchanged public boundary wrapper plus one shared internal reduction loop that accepts an existing node/environment/owner. Public execution retains `bind_inputs`, budget, call stack and result-boundary validation. Expression evaluation enters the internal loop directly, retaining `_Closure` values; it must not manufacture a `defworkflow` or transport closures through a declared `Value` input boundary.
- [x] Add `workflow/dynamic/capture.py`. Reuse `state.load_dynamic_run` unchanged and read completed rows' physical `result.json` through retained `WorkspaceFiles`; validate each with `validate_effect_result(native_result=True)`. Replay callbacks consume rows in ordinal order and compare definition/location/effect class; they never call runtime performers. A running/failed row or absent next row stops before dispatch and ignores partial bundles. Observe lexical environment/owner/pointer/context per continuation; restore the caller before `perform_done` and after helper return, while preserving the final root `let*` frame. The last entered operand is not reliable scope evidence.
- [x] Require all recorded rows consumed and exact halted value/step agreement for a completed state. Reproduce a pure error for a failed state without a failed effect, or stop at the next reachable effect when the saved error occurred before dispatch. Extra rows, corrupt results, source/order mismatch or terminal divergence refuse with `dynamic_state_invalid`. A pure halt with stored status `running` exposes its frame at `halt-unpublished`, but cannot publish or manufacture a `:result`. These checks do not add a historical digest guarantee for operands or result payloads absent from schema 3.1.
- [x] Route native attachment only with an explicitly loaded module (`repl_module_required` otherwise) and matching semantic digest. Digest mismatch clears the capture and uses the existing `resume_program_changed` code with neutral attachment wording. Native `:bindings` reports runtime kinds, including `Function`; JSON data prints with its kind, a function result prints opaque `<function>`, and data containers containing functions receive the design's presentation diagnostic while retaining internal expression usability. `:result` requires persisted native completion. Expressions have no dispatch callbacks: direct lowered `perform` is refused, and a reached effect through a function fails `repl_effect_refused`; do not add a global effect-analysis system.
- [x] Cover pure completion and module functions; immutable closure capture and shadowing; callee return/caller restoration and operand scope; an actual effect followed by pure failure; pure failure before any effect; real interruption before and after a completed effect; invalid persisted result; extra or misordered effect rows; completed result/step mismatch; halt before terminal publication; mismatched loaded digest; no loaded module; and custom/overridden state directories through public `:run`. Include a captured closure invoked later and passed to an ordinary module helper, opaque function display, and refused containers containing closures.
- [x] For attach, bindings, result, pure expressions, invalid expressions and effect refusal, compare before/after SHA-256 maps for every retained run file, including header/program/state/result/attempt files. Assert exact native values and diagnostics, stopped lexical scope, no effect-probe increment and no hidden publication. Hash coverage supplements rather than replaces ordinary result validation.
- [x] Re-run the typed REPL tests after shared CLI edits. Run native owner selectors and independent code/design review before integration.

```bash
pytest --collect-only -q tests/test_workflow_dynamic_repl.py
pytest -q tests/test_workflow_dynamic_repl.py
pytest -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_dynamic_evaluation.py tests/test_workflow_dynamic_source.py tests/test_workflow_dynamic_program.py
pytest -q tests/test_workflow_dynamic_cli.py tests/test_workflow_dynamic_state.py tests/test_workflow_dynamic_readers.py
```

Expected: public native acceptance passes without modifying persisted evidence
or dispatching inspection effects, typed REPL remains compatible, and native
run/refusal/readers semantics remain unchanged. Use tmux/16 workers for long
selectors. Native interruption acceptance must interrupt a real process; direct
helper fixtures alone do not satisfy this proof.

## Task 3: Integrate durable documentation and fresh verification

- [x] Reconcile the REPL design, normative CLI reference, capability matrix, design index, documentation hub and drafting guide with verified 2.35/2.36/3.0 availability. Also reconcile W3 §6 in `docs/design/workflow_lisp_write_once.md`, target-2.36 in `specs/versioning.md`, and the necessary frontend/local-procedure contract deltas from the committed source. Existing "W3 absent from this candidate" current-status statements become stale after import; historical statements remain dated history. State native loaded-source attachment, internal function display, pure-expression boundaries and existing fresh-only execution/repeat-effect risks precisely; preserve target-specific refusals. Put test outcomes and pending work here, not in durable contracts.
- [x] Preserve historical W3 evidence. Its native runtime pin `b0b05d504d4b1be7b1cbaebfadf47ffdc3e66012`, packet revision `d87334f0365f46bfeb56bf7a0f753d1490df85c5` and typed comparator `47e85a9c7e452bfd367275a15d5e97b928efa5ca` remain frozen. Update only reproduction routing to an explicit historical packet checkout if needed. Do not advance controls, rerun the known two-RED matrix for this port or claim DC-P selection.
- [x] Check new relative links, command/options and examples; independently review documentation against the actual implementation. Record all intentional profile differences.
- [x] Run a public end-to-end smoke in a disposable workspace: installed `orchestrator repl` or `python -m orchestrator repl`, real frontend/public `:run`, loaded and typed recipe-only attachment, native closure/module expression, bindings/result, effect refusal, error recovery, custom state root and ordinary report. Use existing deterministic local command/provider probes only. Assert output and stderr, exits and complete retained run-file hashes; keep exact commands and disposable paths.
- [x] After narrow acceptance, run the existing evaluated provider/resume and native command/provider/interruption/publication suites, followed by the broad non-E2E suite in tmux. Read the tmux skill before launching. Record every exit and classify failures with fresh baseline evidence where needed; never weaken assertions or report a RED campaign as PASS.

```bash
pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_resume.py tests/test_workflow_dynamic_commands.py tests/test_workflow_dynamic_providers.py tests/test_workflow_dynamic_interruptions.py tests/test_workflow_dynamic_publication_faults.py
pytest -q -n 16 --dist=worksteal -m "not e2e"
```

- [x] Coordinator inspects the final diff, changed callsites, authority boundaries, module sizes and verification logs; obtain independent code and document/design approvals. Reuse unaffected verification after doc-only fixes. Record exact final revision/tree and limits before claiming completion. Commits and final integration belong to the coordinator.

## Execution evidence

Local receipts are retained in `/tmp/orc-dynamic-repl-port-20261012/`, with
initial native test preparation receipts under
`evidence/tmp/orc-dynamic-repl-port-20261012/`. These are local execution
records, not a replacement for the committed tests or historical comparison.
All commands ran from this worktree with the existing
`/home/ollie/miniconda3/bin/python` (3.13.9), without live paid providers.

| Checkpoint | Fresh result and receipt |
| --- | --- |
| Shared prerequisite RED/collection | W3 before import: 8 failed, 2 passed; dedicated added modules: 181 collected. `task1a-red.log`, `task1a-collection.log` |
| W3/bound-capture acceptance | 241 passed; source-free capture owner: 5 passed. `task1a-narrow.log`, `task1a-captures.log` |
| Shared owner campaign | Initial 780 passed, 2 xfailed, 3 failed; two stale target-gate expectations and one incorrectly placed test hunk corrected, affected 42 passed. Final touched collection: 792. `task1a-owners.log`, `task1a-corrected.log`, `task1a-full-collection.log` |
| Shared public smoke/artifact parity | Real target-2.36 inferred/captured hooks compile/run successfully; unchanged 2.34/2.35 sources preserve artifact/source bytes against clean base. `task1a-smoke.json`, fresh `task1b-parity.json` |
| Typed REPL | Missing-command RED; 16 upstream public cases passed, transient read-only build control 1 passed, CLI/replay/readers/packaging 130 passed. `task1b-red.log`, `task1b-repl.log`, `task1b-inmemory.log`, `task1b-owners.log` |
| Typed public smoke | Loaded and recipe-only attachment at both 2.35/2.36, public `:run`, pure functions/procedures, refusal/recovery, custom state root and report; complete retained file hashes unchanged during inspection. `task1b-smoke.json` |
| Native REPL | Missing-native-support RED; final initial 26 public cases passed; subsequent nominal/null/structural descriptor subcase passed. Real process interruptions, physical result validation, closures/caller scope, fail-closed attachment and full retained-file hashes included. `native-public-final.txt`, `native-structural-result-qualified.txt` |
| Retained flat-profile refusal | Review found missing header-presence guard: real 2.34 attachment RED, corrected diagnostic GREEN with every workspace hash unchanged. Final native module collects 27; three native/typed public attachment cases pass after the correction. `native-flat-refusal-red.txt`, `native-flat-refusal-green.txt`, `native-flat-qualified-collection.txt`, `native-flat-recouple.txt` |
| Native/typed owner campaign | Initial 431 passed, 3 failed: null CLI fixture corrected to JSON input-file and included in green native acceptance; two reader watchdog deadline failures under parallel load, all four watchdog cases pass isolated. `native-regression-initial.txt`, `native-readers-recheck.txt`. The initial campaign remains RED. |
| Native public/memory smoke | Real public `:run` gives captured closure result 12 and saved workflow result 7; a later `:attach` preserves every workspace/run hash. Repeated successful/invalid queries preserve compiler maps, captured environment and base artifact. `native-public-smoke.json`, `native-memory-check-final.txt` |
| Durable document routing | 19 existing documents independently reviewed, plus accepted REPL design; 75 initial links and 9 final authority links checked. Master/Core/evaluated routing now admits typed 2.35/2.36 precisely. Affected version-routing test passed after the final correction. `docs-final-review-addendum.md`, `docs-final-routing-review.md`, `docs-version-routing-final.log` |
| Coupled effects/recovery/publication | 190 passed with `-q -n 16 --dist=worksteal`. `coupled-final.log`, exit 0 |
| Broad non-E2E campaign | Exit 1: 23,594 passed, 295 failed, 7 skipped, 172 xfailed in 1,432.28 s. `broad-final.log`, SHA-256 `f6d2d8224edd81bc534afe6fd1c20f9a89bec190319a91bc97a49b00dc711d8c` |
| Exact baseline comparison | Clean archive of `611d9e25`, all 3,687 blobs/modes checked, 649 fixture paths retained. All 295 failed node IDs collect in the base; exact rerun: 269 failed, 26 passed, no errors/skips. `baseline-failed-final-comparison.json`, `baseline-failed-junit.xml` |
| Frozen candidate follow-up | Those 26 baseline-pass cases: 18 passed, 8 failed. Source/test hash map remained identical. Q3/master routing and incoming-capture type checks pass after their corrections; two stale guide expectations and six watchdog deadline failures remain in this receipt. `baseline-failed-current26-comparison.json` |
| Final capture/REPL qualification | 422 passed, 4 existing xfailed, exit 0, including full guide, creator-scope capture/W3 suites and all 16 typed plus 27 native REPL cases. `native-bindproc-restored-owners.txt`, `native-bindproc-final-manifest.json` |
| Watchdog timing disposition | The unchanged original discovery selector fails at its 40-second deadline in both exact baseline and candidate: 44.56/44.74 seconds total, exit 1. Separate diagnostic observation reaches the same action at 67.49/68.22 seconds with identical 20-helper sequence and unchanged run tree; this is not acceptance PASS. `watchdog-sol/final-diagnostic-receipt.json`, independent `watchdog-verification-review.md` |

Independent prerequisite and typed code reviews approved conformity then
quality (`task1a-review.md`, `task1b-review.md`). Native architecture passed
independent design review (`design-review.md`), including exact incomplete-state
step accounting. Final combined code review passed conformity then quality
(`native-code-review.md`, 61 source/test hashes); final document review and its
bounded correction passed (`docs-final-review.md`,
`docs-final-review-addendum.md`, `docs-final-routing-review.md`,
`docs-capture-correction-review-addendum.md`). Post-broad code review approved
the 63 final source/test hashes in `native-code-review-addendum.md`.
The original broad campaign remains RED. Independent watchdog review accepts
the bounded timing qualification limit below; it does not turn failures into
PASS or certify zero performance regression.

The original guide fixture expected 13 and explicitly identified it as a
wrong lexical-scope value. Imported W3 intentionally fixes creator captures
at every admitted target; the same public fixture's correct value is 7.
Reconcile the maintained guide/test and versioning exception to that accepted
correction. A temporary target-only compatibility gate broke eight positive
capture contracts and was discarded; `lowering/context.py` is restored byte
for byte to the committed W3 source. No gate, xfail or assertion waiver is
delivered. The final 422-case owner campaign includes those eight positives.

Six watchdog cases exceeded their existing completion deadlines, including
serial attempts while independent suites were active. Those receipts remain
RED. Earlier focused baseline PASS/current FAIL results did not establish a
cause. A fresh representative pair under the current external load reproduces
the same unchanged 40-second assertion failure in both trees. Script, test,
fixture and generated reader guard bytes are identical; all 63 reviewed
source/test hashes remain frozen. No production fix, timeout extension,
assertion waiver or guard change is delivered.

The separate 90-second diagnostic observation preserves the same 20-reader
sequence, one simulated fresh-run action and authority bytes. Its extra
observation time is diagnostic only. Helper CPU totals are 47.32/48.38 seconds;
almost all cost is guarded interpreter/import startup. The host had another
16-worker suite running. This supports a load-sensitive qualification limit,
not performance equivalence or proof of each of the other five variants'
individual cause. Those five have not been separately paired under these
conditions. All six strict failures and the global RED result remain visible.

Long-basetemp attempts failed in tmux setup before testing; their setupERROR
receipts are preserved. The diagnostic harness initially left its two owned
watchers polling after the captured event. Qualified timing receipts use only
the original 20 recorded PIDs; those owned groups were cleaned up. Neither
setup errors nor later polling are counted as acceptance evidence.

The final diagnostic receipt hashes
`81c37cd9891530a7873eb3835c2f872a9fcf954b599281c79f34926306e07e70`.
Its independent review hashes
`f4dff29b68b0e4b253c9d167a93a3da1cd7f5e869df01b2a7e40c66363c993a8`.
The coordinator's final 84-path inventory, staged tree, commit and remote
verification are retained in local `final-scoped-paths.json` and
`final-integration.json`. Publish only the candidate branch; keep
`design/orc-dynamic-core-evaluation` at `611d9e25` for the frozen comparison.

The final native code/test freeze is recorded by
`native-bindproc-final-manifest.json`, SHA-256
`bd858e96101485b7c1c80afc10a1854944cdd5f8d3bd1ae882c1c0d4ba4e245b`.
The broad campaign began before the final flat-refusal correction; its affected
CLI paths are additionally qualified by the post-correction checks above.
All other reviewed runtime/compiler sources remain unchanged.

Evidence exception: rerunning artifact parity overwrote `task1a-parity.json`.
Its original bytes are unavailable; its original SHA-256 was retained in the
first review, and the original stdout/workspaces remain. The separately named
fresh `task1b-parity.json` is the inspected current parity proof. Do not present
the refreshed Task 1a JSON as its original receipt.

Return architectural questions to Design if implementation needs a new wire
field, persistence profile, dispatch route, parser/operator evaluator, effect
ledger, weakened result checks or closure transport across public boundaries.
No paid provider behavior or production migration is qualified by this plan.
