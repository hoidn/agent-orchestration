# Workflow Lisp REPL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this bounded checklist. The coordinator assigns implementation and independent review, integrates changes and owns final verification/commits. Do not ask again for execution confirmation.

**Goal:** Add a typed, pure Workflow Lisp REPL over loaded 2.35/2.36 modules and checked evaluated-run lexical frames, with explicit ordinary public `:run` execution.

**Architecture:** Preserve one frontend, one closed evaluator and one run authority. Retain compiler context in memory, capture lexical frames during ordinary checked memo replay, and compile entered expressions through ordinary elaboration/typecheck/lowering. Inspection never writes run evidence; only explicit `:run` uses public writer authority.

**Tech stack:** Existing Python CLI/frontend/evaluated runtime, standard-library input/readline, pytest, tmux and public `python -m orchestrator` subprocesses. No dependencies added.

**Authority:** [Proposed design](../design/workflow_lisp_repl.md), [evaluated design](../design/workflow_lisp_evaluated_execution.md) §§5, 8.4, 10, 12, [CLI](../../specs/cli.md), [State](../../specs/state.md), [test guide](../../tests/README.md) and repository `AGENTS.md`.

**Scope:** Code/context/capture/expression/CLI integration, behavioral tests and the specified docs. No effects in entered expressions, session resume, flat support, editor/LSP, multiline, definitions, completion/history or launch-mechanics changes. Each new module stays below 500 lines. Existing tests are reused where they prove the contract; new tests must prove behavior/dataflow rather than literal prompt text.

**Tradeoff:** Private machine callback reuse keeps semantics shared but couples capture to that callback contract. Source-independent module calls, multiline editing and interactive effects require later design.

## File responsibilities and execution ownership

| Files | Responsibility |
| --- | --- |
| `orchestrator/workflow_lisp/workflows.py`, `compiler.py`, `closed/frontend.py`, `closed/artifact.py` | Additive transient compiler products and retained builder, preserving existing compile wrapper and artifact identity |
| `orchestrator/workflow/evaluated/views.py`, new `capture.py` | Visible bindings, injectable checked replay evaluator, frozen capture machine with shared trace |
| New `orchestrator/workflow_lisp/repl_expr.py` | Canonical descriptor/type recovery and ordinary pure-expression compilation/evaluation |
| New `orchestrator/cli/commands/repl.py`, `commands/__init__.py`, `cli/main.py`; `pyproject.toml` | Public registration, load/run/attach commands, input loop/diagnostics and installed console entry |
| New `tests/test_workflow_evaluated_repl.py`; existing owner suites | Behavioral public integration, scope/purity/read-only/compatibility regressions |
| `specs/cli.md`, `docs/capability_status_matrix.md`, `docs/index.md`, `docs/lisp_workflow_drafting_guide.md` | Verified public command, routing/status and author recipe |

Delegate bounded code implementation/revision and test preparation using the
repository's prescribed roles/models. Use a reviewer distinct from the author.
The coordinator inspects the resulting diff and evidence. Read-only reviewers
may work in parallel; dependency-bearing code edits follow the ordering below.
Keep execution results, selected commits and failure dispositions in this plan
or a linked evidence record, rather than live blocker text in the durable design.

## Nine-step execution checklist

- [x] **1. Write the design and route it before code.** Create `docs/design/workflow_lisp_repl.md` from `docs/templates/design_template.md` with status `proposed`, kind `feature`, creation date 2026-10-12 and targets 2.35/2.36. Add its Current Component Contracts row in `docs/design/README.md`; retain proposed design status even when implementation becomes available. Record this bounded execution checklist under `docs/plans/`. Independent review checks approved architecture and evidence boundaries before code integration.

- [x] **2. Retain ordinary expression compiler context.** In `workflows.py`, add frozen `ExpressionCompileContext` (function catalog, typed functions and three name resolvers), then `Stage3CompileResult.expression_context = None` with `compare=False`, `repr=False`. Populate the entry module from existing `compiler.py` locals. In `closed/frontend.py`, add `compile_typed_program_with_result` returning typed program/entry Stage-3 result; preserve `compile_typed_program`'s existing result contract. In `closed/artifact.py`, retain `typed_program`, `stage3`, `builder` in additive defaulted transient fields. Check all callers/constructors/exports and prove artifact/manifest/digest parity with the existing closed-build suites. No new serialized context.

- [x] **3. Inject the evaluator into existing checked replay.** In `orchestrator/workflow/evaluated/views.py`, add only `_replay(..., *, evaluate=evaluate_closed_program)`, calling that evaluator at the existing evaluation site. Keep the handler, commit order/reachability, exception handling and consumed-prefix checks unchanged. Existing report/view callers retain their default path; run the view/readers/publication selectors below.

- [x] **4. Capture checked replay lexical positions.** Create `workflow/evaluated/capture.py` using a frozen `_CaptureMachine` and shared mutable trace that survives `replace`. Append successful `_halt` observations after `super` to `trace.completions`; observe `_done` by calling `super`, recording the already evaluated value/environment when its existing `_ControlTransfer.kind` is `done`, and rethrowing the same exception. Record first `_MissingCommit` in `_perform` after operand evaluation, and innermost `EvaluatedValueError` in `_body`. Stop/failure override incidental halt/done events. The last completion supplies the exit frame; the actual `machine.evaluate` return supplies the final result after ordinary coercion/dependency propagation. Completed position stays `halt`, including a root loop completing through done without halt. Invoke the existing injected `_replay` and `_checked_terminal`. Add `visible_bindings` to `capture.py` (inner name wins, hide `%`, outer display order). Exercise scope and `memo_inconsistent` parity before CLI integration.

- [x] **5. Bridge ordinary pure expressions and binding types.** Create `workflow_lisp/repl_expr.py`: one `read_sexpr_text` datum into `SyntaxNode`; ordinary `elaborate_expression`, supported function normalization and `typecheck_expression`, with complete module catalogs/resolvers and the existing 2.36 inferred-hook branch. Recover frontend refs by provenance-free structural descriptors over signature/emitted/TypedExpr refs and recursive resolved components, including nested enums; exclude synthesized `variant_case` from expression scope. Lower an ephemeral `TypedWorkflowDef` with the actual `TypedExpr`, minimal captured-parameter/typed-return signature and retained source owner through builder definition context/identity names, `_prepare_command_owner`, `_install_prepared_requests`, ordinary computed-capture preparation, `builder.body` and its request verifier. Direct `frontend_value` alone lacks call coordinates for closed-opaque pure calls. Reject transitive effects, recursively reject lowered `perform` including block/reachable callee bodies, and evaluate with ordinary machine callbacks with no effect handler/provider IO. Use an ephemeral program view carrying builder definitions/nominal types for pure calls; the loaded `.program` is a separate JSON-readback snapshot, so no builder deep copy is needed. Authority/artifact/digest remain unchanged. Missing context refuses module calls; ordinary unknown-name diagnostics survive.

- [x] **6. Implement CLI load, attach and explicit public run.** Register `repl [WORKFLOW]`, `_add_frontend_flags`, `--run-id`, `--state-dir` in `cli/main.py` and the existing commands export. Register the required public `orchestrator` console entry in `pyproject.toml` using the existing `orchestrator.cli.main:main`. Startup loads then attaches. Implement `:run` with public run-option parsing and `run_workflow`; forward session state directory unless overridden and attach the returned root after locks release. Add `:bindings`, `:result`, `:help`, `:quit`, one-line `input()` and TTY-only prompt/readline. Value output is compact sorted UTF-8 JSON on the first line and exactly `: <rendered type>` on the second line; REPL/runtime errors are `[code] detail` on stderr while frontend errors retain ordinary localized `render_diagnostic` output with kind/form context. EOF/quit exit 0, startup failure 2, unexpected failure 1; command errors keep the session usable. `:load` uses `FrontendBuildRequest`/`build_closed_program_bundle` and ordinary diagnostic rendering, retaining the old module on failure. Attach using retained `WorkspaceFiles`, authoritative byte loaders, memo reduction/site classes and capture. Refuse missing/flat roots with REPL codes. Compare loaded-module digest; without a module rebuild `_resume_build_request` with `prepare_closed_program_bundle` in memory, requiring recipe/digest parity. Use stored bound inputs; do not rebind current input files. Attachment takes no writer locks and performs no append/repair, view publication or cache-artifact publication. Ordinary failures retain compatible state; a digest mismatch clears attachment and cannot retain an incompatible module/frame pairing.

- [x] **7. Prepare and execute public behavioral acceptance tests.** Add `tests/test_workflow_evaluated_repl.py` using actual frontend/public run/authority/replay paths and a deterministic provider executable shim only where external provider completion/interruption needs control. Cover record field/list expressions, pure module defun/defproc (including unused helper and nested defun-to-defproc calls), result, completed root-loop/done capture without halt and seed-block halt 3 followed by done 7, interrupted compound operand/callee scope, shadowing, direct/transitive effect refusal, byte-identical memo/state/authority/attempt files, mismatch, recipe-only/missing-recipe attachment, pure failure before/after effect, custom `:run` state directory and nested enum type recovery. Additional optional review checks are contradictory terminal/unreachable commit parity, failed-load/ordinary-error retention and detach on digest mismatch. Run `pytest --collect-only -q tests/test_workflow_evaluated_repl.py` after every test rename/addition, then `pytest -q tests/test_workflow_evaluated_repl.py`; expected collection success and all behavioral cases passing.

- [x] **8. Update verified public documentation.** Update `specs/cli.md`, capability matrix, hub and drafting guide with the command/options, pure expression limit, attachment authority, explicit public run behavior, stable errors and a reproducible 2.35/2.36 recipe. The design index points to the proposed contract while its Current checkout availability becomes Yes once code is integrated; design status stays proposed. No new state schema contract or broad capability claim. Check every new relative Markdown link and independently review the design/plan against the implementation diff.

- [x] **9. Complete regressions, public smoke, broad verification, review and integration.** Run the exact compile/CLI, view/readers/publication and combined final selectors below. Execute the maintained `plan_review_execute.orc` through public run in a disposable workspace with declared manifests and a deterministic provider stand-in, retaining exit/output/artifacts. Compilation alone does not satisfy this smoke; providers never run against the live checkout. Then run the full non-E2E campaign in tmux with `pytest -q -n 16 --dist=worksteal -m "not e2e"`, retaining exit/result output and every failure disposition. Review the full diff, new-module sizes, artifact/digest parity, writer-lock release before attach, no alternate evaluator and byte-preserving inspection. Obtain independent code and design/documentation review; return code corrections to the implementer and new architecture questions to Design. The coordinator verifies the final changed revision, records scope/evidence limits and commits only the intended files. Do not claim full-suite success if baseline/unrelated failures remain.

## Verification commands and evidence limits

Start from the repository root. Narrow tests use the default serial selector;
broad, slow and full runs use tmux and the required 16-worker worksteal mode.
Read the `tmux` skill before launching the long campaign.

```bash
pytest --collect-only -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_lisp_build_in_memory.py::test_read_only_build_matches_persistent_prefix_without_mutating_workspace
pytest -q tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py
pytest -q tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_view_publication.py
pytest -q tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_view_publication.py tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_resume.py
pytest -q -n 16 --dist=worksteal -m "not e2e"
```

If a selected owner suite becomes long, move it to tmux with the prescribed
parallel flags. The public `plan_review_execute` execution smoke supplements
the optional existing compile-only `tests/test_workflow_lisp_plan_review_execute_example.py` check; use the maintained source/header/manifests as
inputs and record the exact disposable root, invocation, stdout/stderr, exit
and evidence hashes. Public execution and production reader loaders are real;
the deterministic provider stand-in proves integration only. Live-provider E2E
is outside this bounded qualification and must be stated as unverified.

Capture evidence for malformed/inconsistent memo refusals and pure-failed
runs, not just happy-path output. Avoid literal prompt phrasing assertions.
No broad retest is necessary after documentation-only corrections unless
routing/contracts or unresolved findings make it relevant.

## Stop or return to design

Stop the implementation branch if the selected solution needs artifact/header
schema changes, memo semantics changes, a second operator evaluator, weakened
terminal/commit checks, effects in entered expressions or fixture-only public
acceptance. Report the concrete mismatch and request a design decision; do not
silently expand scope or treat a false-green helper test as qualification.

## Execution record

Evidence recorded below is the bounded verification available on 2026-10-12
(local date; smoke timestamps are 2026-10-13 UTC). Counts/probe results and
installed-console qualification are reported by the coordinator; the public
REPL, combined-selector and all smoke receipts were also inspected while
updating this record. The REPL suite and strict smoke fail the required equality
scenario; no complete implementation acceptance or full-suite pass is claimed.

Resolution by the owner, 2026-10-12: the brief's acceptance expression
`(= feedback.findings (list))` was invalid for the language, which has no list
equality at any target; the requirement was the emptiness check the language
already expresses as `(list/empty? feedback.findings)`. The three tests now use
that form with their Boolean expectations unchanged, and the public REPL module
passes 16 of 16 (`pytest -q tests/test_workflow_evaluated_repl.py`, 47.54s).
Full-suite failures outside the REPL reproduce on the baseline commit and are
not part of this acceptance.

| Check | Available result | Boundary |
| --- | --- | --- |
| Build/compile CLI regression control | 54 passed | Existing public build/compile control; coordinator-reported result |
| Checked replay view/readers/publication control | 74 passed | Existing replay consumers; coordinator-reported result |
| `tests/test_workflow_lisp_build_in_memory.py::test_read_only_build_matches_persistent_prefix_without_mutating_workspace` | 1 passed (2.27s) | Equal read-only/persistent build prefix without workspace mutation |
| Capture feasibility probe | PASS | Bounded capture probe including root-loop/done completion; supplements public tests |
| Expression feasibility probe | PASS | Bounded pure module-call prepared-owner probe; supplements public tests |
| Initial disposable public `plan_review_execute` run/REPL/report smoke | Harness exit 0, raw `SMOKE PASS`; incomplete assertions | Real public services/readers with deterministic provider stand-ins; list equality did not succeed and was not asserted |
| Installed wheel console in isolated venv with `PYTHONPATH` removed | PASS | Installed `orchestrator repl --run-id` works without source-root import injection; coordinator-reported result |
| Current REPL collection | 16 collected in 1.61s, exit 0 | Coordinator-reported collection after the two supported-operator cases were added |
| Prior 14-case public REPL module | 11 passed, 3 failed in 40.47s | `/tmp/test_workflow_evaluated_repl.log`; all three failures require Boolean list equality |
| Two added supported-operator cases | 2 passed in 16.64s | `/tmp/test_workflow_evaluated_repl_positive.log`; fresh positive list reads/emptiness at 2.35 and 2.36 |
| Current complete 16-case public REPL module | 13 passed, 3 failed in 85.32s | `/tmp/test_workflow_evaluated_repl_final.log`; required list-equality failures unchanged |
| Exact combined final regression selectors | 207 passed in 311.54s, exit 0 | `/tmp/orc-repl-verification/narrow.log`; views/readers/publication, compile/CLI, providers and resume |
| Reinforced strict public smoke | Exit 1 | `/tmp/orc-repl-verification/smoke-strict.log`; asserts required Boolean equality and fails when stdout lacks it |
| Separate supported-operator public smoke | Exit 0, `SMOKE PASS` | `/tmp/orc-repl-verification/smoke-supported.log`; actual Bool output from `list/empty?`, without replacing strict requested equality acceptance |
| Fresh ordinary-frontend probes at 2.35 and 2.36 | Required list equality refuses; `(list/empty? items)` compiles | Empty list lacks exact type context; explicitly typed list equality has incompatible operands under the ordinary scalar/enum equality contract |
| Independent code review | Bounded diff/tests and the two added positive cases approved, excluding the equality contract conflict | Distinct reviewer; coordinator-reported bounded result, no waiver of failed requested acceptance |
| Bounded documentation review | PASS | Coordinator-reported resolution of the diagnostic-format/evidence-boundary findings |
| Final local Markdown links | 44 targets exist, exit 0 | Coordinator-reported final path check |
| Three new runtime modules compile | Exit 0 | Coordinator-reported `compileall` for capture, expression bridge and CLI |
| New-module size check | Capture 146, expression bridge 262, CLI 373, test owner 395 lines | Each new module is below 500 lines |
| Full non-E2E campaign | 266 failed, 23493 passed, 7 skipped, 172 xfailed, 230 warnings in 1076.13s; exit 1 | `/tmp/orc-repl-verification/full-non-e2e.log` and `.exit`; collected the prior 14 REPL cases |
| Baseline rerun of the 263 existing failing selectors | 260 failed, 3 passed in 56.87s; exit 1 | Baseline `47e85a9c`, exact selector JSON and baseline-failing-selectors log/exit |
| Fresh current rerun of the three baseline-passing selectors | 2 failed, 1 passed in 42.12s | `unmatched-current.log`; spike mixed now passes |
| Baseline code in the same active host workspace | 2 failed in 1.19s | `baseline-same-workspace.log`; both runtime cases fail with the same workspace ownership diagnostic |


The initial smoke receipts are `/tmp/orc-repl-verification/smoke.log`,
`smoke.exit` and `smoke-evidence.json`. The harness exited 0 and printed
`SMOKE PASS`, but stdout contained no Boolean equality result and stderr
contained `list_empty_type_context_required` for
`(= feedback.findings (list))`. Its assertions did not verify that required
scenario and tolerated the frontend diagnostic. This is an initial evidence
limit, not complete smoke qualification. The reinforced rerun now asserts the
required `true` / `: Bool` output and fails with exit 1 in
`/tmp/orc-repl-verification/smoke-strict.log`. Its completed-run inspection still
shows the other typed values and result; it does not produce the requested
Boolean equality. The initial partial evidence and fresh strict failure remain
separate; no initial harness success waives the failed acceptance. No new list
capability or evaluator semantics is selected. The disposable workspace is
`/tmp/orc-repl-smoke-fk43pkir`, completed run
`20261013T022239Z-k6ot2e`. Public inspection returned visible bindings,
`feedback.findings`, `(list/length revised.steps)` and the entry result; rejected
an effectful expression; attached recipe-only; inspected a provider-failed
prefix with no entry result; and exercised explicit `:run` under custom and
overridden state roots. Report subsequently returned the ordinary completed
four-provider view. The intentionally malformed provider-result run exited 1
as a negative fixture; it is not a smoke harness failure.

The completed run's before/after SHA-256 values were identical:

| File | Before = after SHA-256 |
| --- | --- |
| `memo.jsonl` | `fd73e74aac45ee18b1dde1aaa9b4bc0c5d44a5806721a2984d41e666de9474c1` |
| `state.json` | `9778bd1964d6774ab1203fe5ca435a41eeef6c78559b0c8c89fd005411aea31d` |

These hashes prove those two inspected files were unchanged; they do not claim
all-run-file hash coverage or live-provider qualification. The broader
byte-preservation contract remains owned by the behavioral tests.

The installed-console check used the wheel installed in
`/tmp/orc-repl-verification/venv`, with
`env -u PYTHONPATH /tmp/orc-repl-verification/venv/bin/orchestrator repl --run-id <retained-run-id>`.
The launch is independent of `python -m orchestrator` from the source checkout.

### Separate supported-operator smoke

A separate receipt uses `(list/empty? feedback.findings)` and asserts its actual
`true` / `: Bool` output. `/tmp/orc-repl-verification/smoke-supported.log`
ends `SMOKE PASS`, exit 0; `smoke-supported-evidence.json` records the commands
and typed output. Its workspace is `/tmp/orc-repl-smoke-u9oywy38`, completed
run `20261013T023853Z-bpci80`. The public recipe exercises loaded and recipe-only
attachment, field/list values, entry result, refusal/session recovery, failed
capture, custom state roots and override, and ordinary completed report. A
provider-result failure is intentional negative evidence in this harness.

The supported smoke's inspected completed run preserves both hashes:

| File | Before = after SHA-256 |
| --- | --- |
| `memo.jsonl` | `e83b20f0111a59274e80b857ffdd65dda19b9aadbc9d3fb75325659384eb6e3d` |
| `state.json` | `cc38230dddcb4546bccfae6d47c7b1926d5cfffa292bf87dd0d5c0fdda1160cb` |

This is positive integration evidence for supported ordinary operators. It is
not the requested list-equality scenario, does not replace its strict red
receipt and does not waive any failed acceptance. The original strict request
and the supported alternative remain separate evidence lanes.

### Necessary packaging deviation

The original file list omitted packaging, but `[project.scripts]` had no public
`orchestrator` console entry. Add `orchestrator = "orchestrator.cli.main:main"`
to `pyproject.toml` so the approved `orchestrator repl` invocation exists after
installation. This reuses the same CLI entrypoint, adds no dependency or
alternate execution path, and is qualified by the installed-wheel check above.
The design remains `proposed` as requested; implementation availability in the
design index is independently `Yes`.

### Contract conflict and remaining verification

The current expanded public REPL suite collects 16 cases in 1.61s (exit 0)
and executes with 13 passed / 3 failed in 85.32s. Its two added positive
2.35/2.36 supported-operator cases separately pass in 16.64s; an independent
reviewer approves those cases. The failures are
`test_public_repl_attaches_to_completed_run_and_evaluates_typed_values` at
2.35 and 2.36, and
`test_effectful_expressions_refuse_without_changing_run_and_session_recovers`.
Each requires `(= feedback.findings (list))` to produce a Boolean. The strict
smoke requires the same output and now correctly fails, rather than accepting
absence of that result.

The [ordinary frontend contract §10.2](../design/workflow_lisp_frontend_specification.md#102-closed-pure-expression-surface)
limits `=` / `!=` to supported scalars and same-type enums. Fresh probes at both
2.35 and 2.36 confirm that an empty list lacks exact expected type context and
explicitly typed list equality still refuses for incompatible operands;
`(list/empty? items)` compiles. The coordinator has not changed code to broaden
the ordinary equality contract or installed a REPL-only evaluator. Clarification
of the requested list-equality priority versus preserving ordinary frontend
semantics remains pending. The supported emptiness predicate is diagnostic
context, not a silent replacement for the requested scenario.

Steps 1–6 are implemented. Step 7 remains partial because the complete public
REPL module is red, and step 9 remains partial despite the green 207-case
combined control. Step 8's bounded documentation findings are resolved with
review PASS. Independent code review approves only the bounded diff/tests
excluding the contract conflict; it does not establish complete acceptance.
The full non-E2E campaign finished red, with the dispositions below. It
collected the prior 14 REPL cases before the two new positive cases were added
and therefore does not cover those additions. Their fresh targeted and
complete-module receipts above supply separate evidence; no claim extends the
old collection.

### Full campaign and bounded baseline audit

The required `pytest -q -n 16 --dist=worksteal -m "not e2e"` campaign ran in
tmux. `/tmp/orc-repl-verification/full-non-e2e.log` and `full-non-e2e.exit`
record **266 failed / 23493 passed / 7 skipped / 172 xfailed / 230 warnings**
in 1076.13s, exit 1. This is a red full result, not acceptance or a green run
with waived failures. No tests were disabled and no new xfails were added.

The automatic audit used baseline
`47e85a9c7e452bfd367275a15d5e97b928efa5ca` in a disposable worktree and
reran the 263 existing failing selectors, excluding the three new required
REPL equality failures. `baseline-failing-selectors.json` preserves the exact
full failure set and baseline selector list; `baseline-failing-selectors.log`
and `.exit` record 260 failed / 3 passed in 56.87s, exit 1. Matching baseline
failures establish reproduction in this environment, not their absence on
other machines or a universal no-regression claim.

The three baseline-passing selectors were:

- `tests/test_runtime_failure_persistence.py::test_run_command_persists_unexpected_executor_exception`
- `tests/test_runtime_failure_persistence.py::test_run_holds_writer_lock_through_executor_exit`
- `tests/experiments/test_evaluated_execution_spike_trial.py::test_every_kill_of_the_spike_and_what_its_resume_gives[mixed]`

The fresh current rerun (`unmatched-current.log`, `.exit`) gave 2 failed /
1 passed in 42.12s. Both runtime tests failed because the outer hosting run
owns `/home/ollie/Documents/agent-orchestration-repl`, producing
`workspace_run_already_active`; the mixed spike passed. Running baseline code
for those two runtime selectors from that same active host workspace reproduced
both failures in 1.19s with the same diagnostic (`baseline-same-workspace.log`).
`unmatched-failures.json` retains the three selectors; the shared outer-run
ownership is an environment boundary, not proof that the runtime lock should
be removed or bypassed.

| Disposition of the 266 full-run failures | Count | Evidence limit |
| --- | ---: | --- |
| Existing selectors reproduced on baseline in this environment | 260 | Baseline/inherited-environment reproduction; no universal classification of every root cause |
| Runtime persistence selectors reproduced with baseline code in the same active host workspace | 2 | Both fail before executor entry with `workspace_run_already_active` |
| Mixed spike not reproduced in fresh baseline/current controls | 1 | Both fresh controls pass; original full-run failure is retained as non-reproduced, not erased |
| Required REPL list-equality contract conflict | 3 | Current requested acceptance remains red; owner clarification pending |

The mixed spike's original full-campaign failure has an unresolved root cause;
the fresh passing controls do not establish that it is fixed.

The coordinator removed the disposable baseline worktree after receipt review
and moved the full suite's generated `.tmp/omp-fake-launcher` files outside
the checkout. Logs/selector JSON remain separate local receipts. The checkout
contains only the intended committed changes and this final evidence update.

### Recorded implementation commits

| Commit | Artifact |
| --- | --- |
| `4a3d1517` | Design and bounded execution plan |
| `e142f281` | Retained expression compiler context |
| `bab0fbc1` | Injectable shared checked replay |
| `e7201328` | Read-only lexical capture |
| `9014305a` | Ordinary frontend/evaluator expression bridge |
| `dbb2a0b9` | REPL CLI and console entry point |
| `22e6bdf4` | Public scope/evidence-preservation tests |
| `807258ba` | Usage and read-only contracts documentation |

A later final evidence/documentation commit is not assigned a hash by this
record before it exists. The coordinator owns that commit and integration.

Record the owner clarification, any approved correction/retest, strict smoke
result and final acceptance review before closure. Steps 7 and 9 stay partial;
all-complete is not claimed. Temporary evidence paths are local receipts, not
portable checked-in test fixtures or persisted execution authority.
