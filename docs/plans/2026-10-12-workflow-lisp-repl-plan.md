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
| New `orchestrator/cli/commands/repl.py`, `commands/__init__.py`, `cli/main.py` | Public registration, load/run/attach commands, input loop and diagnostics |
| New `tests/test_workflow_evaluated_repl.py`; existing owner suites | Behavioral public integration, scope/purity/read-only/compatibility regressions |
| `specs/cli.md`, `docs/capability_status_matrix.md`, `docs/index.md`, `docs/lisp_workflow_drafting_guide.md` | Verified public command, routing/status and author recipe |

Delegate bounded code implementation/revision and test preparation using the
repository's prescribed roles/models. Use a reviewer distinct from the author.
The coordinator inspects the resulting diff and evidence. Read-only reviewers
may work in parallel; dependency-bearing code edits follow the ordering below.
Keep execution results, selected commits and failure dispositions in this plan
or a linked evidence record, rather than live blocker text in the durable design.

## Nine-step execution checklist

- [ ] **1. Write the design and route it before code.** Create `docs/design/workflow_lisp_repl.md` from `docs/templates/design_template.md` with status `proposed`, kind `feature`, creation date 2026-10-12 and targets 2.35/2.36. Add its Current Component Contracts row in `docs/design/README.md`; retain proposed design status even when implementation becomes available. Record this bounded execution checklist under `docs/plans/`. Independent review checks approved architecture and evidence boundaries before code integration.

- [ ] **2. Retain ordinary expression compiler context.** In `workflows.py`, add frozen `ExpressionCompileContext` (function catalog, typed functions and three name resolvers), then `Stage3CompileResult.expression_context = None` with `compare=False`, `repr=False`. Populate the entry module from existing `compiler.py` locals. In `closed/frontend.py`, add `compile_typed_program_with_result` returning typed program/entry Stage-3 result; preserve `compile_typed_program`'s existing result contract. In `closed/artifact.py`, retain `typed_program`, `stage3`, `builder` in additive defaulted transient fields. Check all callers/constructors/exports and prove artifact/manifest/digest parity with the existing closed-build suites. No new serialized context.

- [ ] **3. Inject the evaluator into existing checked replay.** In `orchestrator/workflow/evaluated/views.py`, add only `_replay(..., *, evaluate=evaluate_closed_program)`, calling that evaluator at the existing evaluation site. Keep the handler, commit order/reachability, exception handling and consumed-prefix checks unchanged. Existing report/view callers retain their default path; run the view/readers/publication selectors below.

- [ ] **4. Capture checked replay lexical positions.** Create `workflow/evaluated/capture.py` using a frozen `_CaptureMachine` and shared mutable trace that survives `replace`. Record successful `_halt` after `super`, first `_MissingCommit` in `_perform` after operand evaluation, and innermost `EvaluatedValueError` in `_body`. Stop/failure override operand halts; final entry halt wins completed evaluation. Invoke the existing injected `_replay` and `_checked_terminal`. Add `visible_bindings` to `capture.py` (inner name wins, hide `%`, outer display order). Exercise scope and `memo_inconsistent` parity before CLI integration.

- [ ] **5. Bridge ordinary pure expressions and binding types.** Create `workflow_lisp/repl_expr.py`: one `read_sexpr_text` datum into `SyntaxNode`; ordinary `elaborate_expression`, supported function normalization and `typecheck_expression`, with complete module catalogs/resolvers and the existing 2.36 inferred-hook branch. Recover frontend refs by provenance-free structural descriptors over signature/emitted/TypedExpr refs and recursive resolved components, including nested enums; exclude synthesized `variant_case` from expression scope. Lower with `frontend_value`/builder definition context and identity names. Reject transitive effects, recursively reject lowered `perform` including block/reachable callee bodies, and evaluate with ordinary machine callbacks with no effect handler/provider IO. Use an in-memory program view if pure lowering adds unreachable callee definitions; authority/artifact/digest remain unchanged. Missing context refuses module calls; ordinary unknown-name diagnostics survive.

- [ ] **6. Implement CLI load, attach and explicit public run.** Register `repl [WORKFLOW]`, `_add_frontend_flags`, `--run-id`, `--state-dir` in `cli/main.py` and the existing commands export. Startup loads then attaches. Implement `:run` with public run-option parsing and `run_workflow`; forward session state directory unless overridden and attach the returned root after locks release. Add `:bindings`, `:result`, `:help`, `:quit`, one-line `input()` and TTY-only prompt/readline. Value output is compact sorted UTF-8 JSON on the first line and exactly `: <rendered type>` on the second line; errors are `[code] detail` on stderr. EOF/quit exit 0, startup failure 2, unexpected failure 1; command errors keep the session usable. `:load` uses `FrontendBuildRequest`/`build_closed_program_bundle` and ordinary diagnostic rendering, retaining the old module on failure. Attach using retained `WorkspaceFiles`, authoritative byte loaders, memo reduction/site classes and capture. Refuse missing/flat roots with REPL codes. Compare loaded-module digest; without a module rebuild `_resume_build_request` with `prepare_closed_program_bundle` in memory, requiring recipe/digest parity. Use stored bound inputs; do not rebind current input files. No locks, append/repair, view publication or cache artifacts. Ordinary failures retain compatible state; a digest mismatch clears attachment and cannot retain an incompatible module/frame pairing.

- [ ] **7. Prepare and execute public behavioral acceptance tests.** Add `tests/test_workflow_evaluated_repl.py` using actual frontend/public run/authority/replay paths and a deterministic provider executable shim only where external provider completion/interruption needs control. Cover record field/list expressions, pure module defun/defproc including unreachable helper definitions, result, interrupted compound operand/callee scope, shadowing, direct/transitive effect refusal, byte-identical memo/state/authority/attempt files, mismatch, recipe-only/missing-recipe attachment, pure failure before/after effect, custom `:run` state directory and nested enum type recovery. Additional optional review checks are contradictory terminal/unreachable commit parity, pure unreachable helper definitions, failed-load/ordinary-error retention and detach on digest mismatch. Run `pytest --collect-only -q tests/test_workflow_evaluated_repl.py` after every test rename/addition, then `pytest -q tests/test_workflow_evaluated_repl.py`; expected collection success and all behavioral cases passing.

- [ ] **8. Update verified public documentation.** Update `specs/cli.md`, capability matrix, hub and drafting guide with the command/options, pure expression limit, attachment authority, explicit public run behavior, stable errors and a reproducible 2.35/2.36 recipe. The design index points to the proposed contract while its Current checkout availability becomes Yes once code is integrated; design status stays proposed. No new state schema contract or broad capability claim. Check every new relative Markdown link and independently review the design/plan against the implementation diff.

- [ ] **9. Complete regressions, public smoke, broad verification, review and integration.** Run the exact compile/CLI, view/readers/publication and combined final selectors below. Execute the maintained `plan_review_execute.orc` through public run in a disposable workspace with declared manifests and a deterministic provider stand-in, retaining exit/output/artifacts. Compilation alone does not satisfy this smoke; providers never run against the live checkout. Then run the full non-E2E campaign in tmux with `pytest -q -n 16 --dist=worksteal -m "not e2e"`, retaining exit/result output and every failure disposition. Review the full diff, new-module sizes, artifact/digest parity, writer-lock release before attach, no alternate evaluator and byte-preserving inspection. Obtain independent code and design/documentation review; return code corrections to the implementer and new architecture questions to Design. The coordinator verifies the final changed revision, records scope/evidence limits and commits only the intended files. Do not claim full-suite success if baseline/unrelated failures remain.

## Verification commands and evidence limits

Start from the repository root. Narrow tests use the default serial selector;
broad, slow and full runs use tmux and the required 16-worker worksteal mode.
Read the `tmux` skill before launching the long campaign.

```bash
pytest --collect-only -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_evaluated_repl.py
pytest -q tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py
pytest -q tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_view_publication.py
pytest -q tests/test_workflow_evaluated_repl.py tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py tests/test_workflow_evaluated_view_publication.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_resume.py
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

No code, acceptance tests or runtime checks are claimed by this initial plan.
The coordinator records reviewed revisions and fresh verification here or in a
linked evidence report as the checklist is executed.
