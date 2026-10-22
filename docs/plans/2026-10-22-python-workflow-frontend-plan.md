# Python Workflow Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The owner has authorized revising the design, planning, and executing the entire worktree; do not pause for another execution choice.

**Goal:** Deliver the complete serial Python authoring API, generated ordinary `.orc`, frozen builds, and public build/check/run commands with ordinary recovery.

**Architecture:** Register declarations, trace symbolic definitions into ordered lexical regions, and emit ordinary source. A fresh child loads exact Python bytes and generates source; the parent calls the existing closed-program builder and existing run dispatcher. The compiler remains the only semantic checker and the evaluated runtime remains the only execution/recovery authority.

**Tech Stack:** Python 3.11+, standard library, existing Workflow Lisp compiler/runtime, argparse, pytest. No new dependencies or paid provider calls.

---

## Authority, Scope And Execution

- Governing design: [Python Workflow Frontend](../design/python_workflow_frontend.md), accepted by the coordinator for implementation on 2026-10-22 after independent design review and corrections. Existing compiler, [CLI](../../specs/cli.md), [state](../../specs/state.md), and [capability](../capability_status_matrix.md) contracts retain their authority.
- Worktree: `/home/ollie/Documents/agent-orchestration/.worktrees/python-api`; branch `feat/python-api`; starting base `332ebe5f`. Run commands from this root.
- The six tasks implement all four design boundaries. Dependency order is `1 -> 2 -> 3 -> 4 -> 5 -> 6`; do not have multiple authors edit shared frontend files concurrently.
- Delegate implementation and code revision to Luna 6 xhigh for bounded tasks. Task 1 establishes multi-file tracer/emitter/type-ownership interfaces, and Task 5 spans process isolation, filesystem publication and compiler integration; the coordinator may use Sol 6.1 high for these tasks because they exceed bounded mechanical changes. Keep contained follow-on tasks with Luna. Review code and this plan with a distinct Sol 6.1 high reviewer; architectural questions return to Astra 6 xhigh. State role and artifact in every delegation.
- Before each task, inspect its callers/fixtures and state the concrete approach plus what it makes harder. After each task, review contract compliance and code quality, resolve accepted findings, inspect the diff, and commit the scoped change. Reuse fresh valid evidence unless relevant changes invalidate it.
- This approach makes native Python runtime control flow and hermetic build guarantees unavailable. Python import/trace executes trusted author code. `parallel_map`, `Agent`, a Python AST compiler, runtime callbacks, automatic generic combinator support, new provider adapters, and a second runtime artifact remain out of scope.
- Existing code below the Python frontend is read/reused, not redesigned. The only production change outside `orchestrator/py/` and the new CLI command module is CLI registration/dispatch in `orchestrator/cli/main.py`. Escalate a real missing owner capability before broadening that boundary.

## File And Dependency Inventory

| Files | Responsibility / consumers |
| --- | --- |
| `orchestrator/py/__init__.py` | Public exports only; authors and CLI consume these. |
| `orchestrator/py/declarations.py` | Records, variants, paths, enums/type annotations, prompts, effect handles, callable registration and declared owner metadata. |
| `orchestrator/py/trace.py` | Symbolic expressions, ordered region bindings, registered calls, branches/match/loops, early Python-protocol refusal. |
| `orchestrator/py/emit.py` | Stable module/binding names, source emission, generated spans; delegates semantic validity to the compiler. |
| `orchestrator/py/diagnostics.py` | Author errors and composition of generated spans with existing compiler diagnostics. |
| `orchestrator/py/imports.py` | Lazy `.orc` handles backed by existing compiler export/signature/type catalogs. |
| `orchestrator/py/_worker.py` | Fresh-process exact-byte loading and trace/emission; dedicated result file, not author stdout or pickle. |
| `orchestrator/py/build.py` | Parent build/check/run API, snapshot capture/publication, pin/frozen comparison, ordinary build/run requests. |
| `orchestrator/cli/commands/python.py`; `orchestrator/cli/main.py` | `py build/check/run` parser/dispatch using existing frontend flags and run defaults. |
| `tests/test_workflow_python_{declarations,control,procedures,imports,build,cli}.py` | One behavioral test module per task; temp source trees and manifests keep fixtures local. |
| `tests/workflow_python_helpers.py` | Only shared source-tree/manifest/public-subprocess fixtures actually reused by the six modules. |
| `workflows/examples/python_command_loop.py`; `workflows/examples/python_command_loop.commands.json`; `workflows/examples/python_command_loop_tool.py` | Maintained provider-free public example and its explicit command boundary. |
| `docs/python_workflow_drafting_guide.md`; `docs/index.md`; `docs/design/README.md`; `docs/capability_status_matrix.md`; `docs/architecture_overview.md`; `docs/lisp_workflow_drafting_guide.md`; `specs/{cli,dsl}.md`; `workflows/README.md` | Public authoring guide, contract and discovery; supported scope and qualifications remain explicit. |

Read existing owners rather than copying them: `workflow_lisp/build.py:FrontendBuildRequest`, `closed/artifact.py:build_closed_program_bundle`, `compiler.py:compile_stage3_entrypoint`, `modules.py:ModuleExportSurface`, `reader.py:SourceReadTrace`, `build_manifest_io.py`, `diagnostics.py`, `cli/commands/run.py:run_workflow`, and `cli/main.py:create_parser`. Owner examples/tests: `test_workflow_evaluated_cli.py`, `test_workflow_evaluated_loops.py`, `test_workflow_evaluated_resume_kills.py`, `test_workflow_lisp_closed_program_names.py`, `test_workflow_lisp_closed_program_artifact.py`.

## Task 1: Typed Declarations, Prompts And Straight-Line Generation

**Create:** `orchestrator/py/{__init__,declarations,trace,emit,diagnostics}.py`, `tests/test_workflow_python_declarations.py`; create `tests/workflow_python_helpers.py` only for genuinely shared fixture setup.

- [x] Write red tests using source-backed temporary modules and the existing closed builder. Required named selectors: `test_forward_declarations_compile`, `test_enum_values_are_wire_tokens`, `test_prompt_kinds_and_externs_compile`, `test_provider_order_reuse_and_ignored_call`, `test_bad_annotations_and_symbolic_coercions_refuse`, `test_four_site_provider_flow_matches_existing_example`, `test_provider_stub_validates_typed_result`.
- [x] Run `pytest -q tests/test_workflow_python_declarations.py::test_forward_declarations_compile`; confirm a missing frontend/unsupported behavior failure before implementation, not a broken fixture.
- [x] Implement registration without body execution and deferred annotation resolution. Support primitives, enum string values, `RelPath` subclasses, ordered records, variant cases and module-owned closed unions, `list[T]`, and `T | None`. Reject recursive/unsupported annotations, invalid/aliased enum values, conflicting return annotations and bare case signatures (`python_variant_signature_unsupported`). Preserve same-short-name owners and constructor expected-type resolution.
- [x] Implement `Prompt(file=...|text=..., fills=..., returns=...)`, `@prompt`, `Text`, `Doc[P]`, `PathOf[P]`, `Value[T]`, `Out[P]`, and `Prompt.extern(name, returns=T)`. File prompts capture module-relative bytes; literal/decorator templates use existing prompt validation. Extern sources come only from supplied manifests; test the existing extern `:inputs`/`:returns` lane separately from fragment calls. Assert compiled contracts/types, never literal prompt wording.
- [x] Implement manifest-only `Provider(name, model=..., effort=..., timeout_sec=...)` handles and overrides. There are no default bindings or credential/executable registration. Effects outside tracing fail; reuse and discarded effects remain once-only ordered bindings. Workflow-to-workflow calls record calls without executing registered bodies recursively.
- [x] Emit ordinary source with deterministic local binding names, original module ownership and default `TARGET = "2.39"`; permit only admitted 2.35–2.39 targets through existing validation. Implement supported operators/projections and non-branching `length`/`concat`/`not_` helpers. Reject Python truthiness, iteration, length, string formatting, membership and mutation over symbolic values with useful source locations. Source maps begin here so later features do not need a second emitter.
- [x] Compile positive and negative forms through the real compiler, including invalid result types and missing externs. Check registrations do not execute bodies until tracing. Provider tests compile or use existing local stubs; never call a paid backend.
- [x] Trace a four-site draft/review/revise/execute Python fixture corresponding to `workflows/examples/design_review_execute.orc`; compare result/input contracts, provider site count and dataflow. Reuse the existing deterministic provider fixture to accept a valid structured result and refuse an invalid one. Compare behavior/contracts across differently named programs; exact digest parity belongs only to the same-name mirror in Task 3, not an invented alpha-equivalence rule.
- [x] Run `pytest --collect-only -q tests/test_workflow_python_declarations.py`, then `pytest -q tests/test_workflow_python_declarations.py`. Obtain independent review, fix accepted issues and commit `feat(py): add typed declarations and source generation`.

## Task 2: Branch Regions And Closed-Union Matching

**Modify:** `orchestrator/py/{__init__,declarations,trace,emit,diagnostics}.py`.
**Create:** `tests/test_workflow_python_control.py`.

- [ ] Add red selectors `test_when_traces_effects_in_selected_region`, `test_match_requires_exact_cases_and_scopes_binders`, `test_boolean_thunks_short_circuit`, `test_eager_branches_and_escaped_binders_refuse`. Compile fixtures to checked programs and evaluate pure branches or no-cost stub effects.
- [ ] Run `pytest -q tests/test_workflow_python_control.py::test_when_traces_effects_in_selected_region` and verify the missing control behavior fails.
- [ ] Implement `when(condition, then=lambda: ..., else_=lambda: ...)` as two independently traced regions; both author thunks run at build, but generated effects remain conditional. Reject eager values. Implement `match(value, Case=lambda payload: ...)` with exhaustive case selection, arm-local payload projection and lexical ownership checks. Preserve flat union transport; do not introduce payload records.
- [ ] Implement thunk-based `all_of`/`any_of` short circuit using the same region mechanism. Keep outer effect references reusable and ordered; branch-local binders/results may not escape or cross into sibling regions. Defer result join and nominal proof to the compiler.
- [ ] Cover effectful ignored expressions inside selected regions, unused branches, nested control and type mismatches. Assertions compare checked branches/effect execution, not emitted source substrings.
- [ ] Run `pytest --collect-only -q tests/test_workflow_python_control.py`, then `pytest -q tests/test_workflow_python_control.py tests/test_workflow_python_declarations.py`. Independent review, corrections, commit `feat(py): add lexical branches and variant matching`.

## Task 3: Procedures, Commands And Bounded Loops

**Modify:** `orchestrator/py/{__init__,declarations,trace,emit,diagnostics}.py`.
**Create:** `tests/test_workflow_python_procedures.py`.

- [ ] Add red selectors `test_proc_pure_and_target_effect_contracts`, `test_command_uses_manifest_authority_and_native_arguments`, `test_loop_done_continue_and_zero_exhaustion`, `test_nested_loop_control_ownership`, `test_generated_mirror_preserves_digest_and_sites`.
- [ ] Run `pytest -q tests/test_workflow_python_procedures.py::test_loop_done_continue_and_zero_exhaustion`; verify missing loop support fails.
- [ ] Implement `@proc`, `@pure`, `uses_command`, `uses_provider`, `calls_workflow`. At 2.39 omit inferred effects unless explicitly restricted and never emit authored lowering; at 2.35–2.38 require the existing exact effect declarations and emit `:lowering inline`. Imported definitions keep their own target/lowering contracts. Pure body effects and recursion are compiler refusals.
- [ ] Implement `Command(name, returns=T)` references with complete call argv, e.g. `emit("python", "probe.py", state.count)`. The compiler checks the supplied stable command prefix; Python supplies neither argv prefixes nor closures/repeat policy. Preserve typed numeric/path argv and `inputs={...}`. Test missing bindings, prefix disagreement and invalid result transport through existing owners.
- [ ] Implement `loop(state=..., max=..., body=..., on_exhausted=...)`, `cont`, `done`. Body/exhaustion get distinct state binders; require every body path to terminate in a loop control, explicit exhaustion at zero budget, stable state type, matching result type and correct nested-loop ownership.
- [ ] Use a local command writing JSON to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and a separate dispatch marker to verify order/reuse/ignored calls. Do not parse stdout as state. Add exact parity against hand-authored source using the same module/definition/type names, retained binding/effect labels, and configuration: compare `program.digest` and sites directly, without removing semantic names or arbitrary `@` data or adding alpha-equivalence rules.
- [ ] Run `pytest --collect-only -q tests/test_workflow_python_procedures.py`, then `pytest -q tests/test_workflow_python_procedures.py tests/test_workflow_python_control.py`. Independent review, corrections, commit `feat(py): add procedures commands and bounded loops`.

## Task 4: Module Ownership And Compiler-Owned `.orc` Imports

**Create:** `orchestrator/py/imports.py`, `tests/test_workflow_python_imports.py`.
**Modify:** `orchestrator/py/{__init__,declarations,trace,emit,diagnostics}.py`.

- [ ] Add red selectors `test_imports_concrete_proc_workflow_type_and_prompt`, `test_imported_generic_type_application_uses_compiler`, `test_modules_relocate_without_identity_change`, `test_private_missing_and_old_imports_refuse`, `test_stdlib_import_has_one_source_owner`.
- [ ] Run `pytest -q tests/test_workflow_python_imports.py::test_imports_concrete_proc_workflow_type_and_prompt`; confirm the missing bridge fails.
- [ ] Implement lazy `import_orc(name, source_root=...)` using `compile_stage3_entrypoint`, its `ModuleExportSurface`, catalogs and type environment. Pass supplied manifest configuration to the existing compiler. No second parser/type/effect checker. Handle concrete procedures, workflows, nominal types and prompts; imported type subscripting emits existing generic application and concrete callable specialization follows compiler-resolved signatures.
- [ ] Preserve defining owners across re-exports and `__all__`, reject duplicate logical modules and ambiguous union ownership, and emit `py/<qualified/module/name>.orc` with matching declared module. Test distinct modules with equal type short names and forward references. Missing/private access errors point at the Python access; imported compiler errors keep their real source.
- [ ] Compile real library and stdlib imports, relocate the fixture root, and compare stable nominal identity and effect sites. Refuse transitive pre-2.35 source normally. Keep ordered roots, reject duplicate/ambiguous roots, and never substitute incidental cwd. Expose compiler read-trace/resolved-asset evidence to Task 5.
- [ ] Run `pytest --collect-only -q tests/test_workflow_python_imports.py`, then `pytest -q tests/test_workflow_python_imports.py`. Independent review, corrections, commit `feat(py): bridge checked orc module exports`.

## Task 5: Isolated Builds, Immutable Snapshots, Frozen Pins And Diagnostics

**Create:** `orchestrator/py/{_worker,build}.py`, `tests/test_workflow_python_build.py`.
**Modify:** `orchestrator/py/{__init__,imports,emit,diagnostics}.py` and shared fixtures only as needed.

- [ ] Add red selectors `test_build_reloads_exact_bytes_despite_mtime_and_cache`, `test_worker_stdout_is_not_build_protocol`, `test_snapshot_rebuilds_project_imports_and_assets`, `test_frozen_captures_all_authoring_inputs`, `test_failed_build_preserves_pin_and_existing_snapshot`, `test_snapshot_paths_refuse_symlink_escape`, `test_diagnostics_preserve_python_and_orc_locations`.
- [ ] Run `pytest -q tests/test_workflow_python_build.py::test_build_reloads_exact_bytes_despite_mtime_and_cache`; confirm absent public build behavior fails.
- [ ] Implement file + optional `entry_workflow` build/check APIs and existing source-root/manifest keywords. No `file:member` parser or live-object build API. Spawn a fresh Python worker that compiles the exact recorded project source bytes, bypassing `.pyc` and stale modules for all local imports. Installed dependencies use normal imports. Author output must not corrupt results: return generated paths/map/capture metadata through a dedicated temporary result file, not stdout; no pickle or serialized typed program.
- [ ] Translate import, syntax and tracing failures into named authored diagnostics; retain traceback for debugging without normal incidental traceback output. The parent consumes generated ordinary files and calls `build_closed_program_bundle(FrontendBuildRequest(...))`; it owns compilation and later run dispatch. Return entry/root/map/manifest/artifact paths, `build_key`, and `program_digest`.
- [ ] Capture exact Python/prompt bytes, supplied binding manifests, compiler-read project `.orc` sources and resolved source-owned prompt assets. Preserve logical roots/layout and manifest-relative meaning. Use `SourceReadTrace.raw_bytes_by_path` and existing manifest readers; do not copy arbitrary directories. Prove preservation with a real imported local module and its relative prompt asset; a runtime `input_file` must still resolve against the workspace. Copy exact manifest JSON only where its existing relative path meaning is preserved; do not blanket-rewrite asset or runtime paths. Do not copy packaged stdlib into another root: retain consumed stdlib hashes for frozen comparison, retaining ordinary package/compiler drift checks. Runtime workspace input files and command closures keep existing runtime authority.
- [ ] Stage under the workspace, reuse path/symlink confinement and atomic IO helpers, then publish a content-addressed immutable `.orchestrate/python/` snapshot. Verify a pre-existing snapshot's bytes instead of overwriting it. Recompile against retained project roots/manifests to establish the ordinary saved recipe; a run must not depend on mutable original Python/source assets. Do not create runtime state for build/check.
- [ ] Atomically update an entry pin only after successful normal build/run. `check` never updates it. `--frozen` requires a pin and compares all captured inputs plus ordinary build identity, even if a Python edit emits identical `.orc`. Refuse changed/missing Python, prompt, imported source or configuration; failure/frozen check preserves the pin and old snapshot. Cover same-size/same-mtime edits, pre-imported module cache, unchanged rebuild, and caller mutation of globals that must not affect fresh source compilation.
- [ ] Complete versioned source maps for declarations/calls/expressions and owning function fallback spans; include source hashes/generated ranges. Compose compiler diagnostics preserving code, generated location, notes/import context. Imported `.orc` errors stay unmapped. Do not enable historical `compile --emit-source-map` or alter runtime site identity.
- [ ] Run `pytest --collect-only -q tests/test_workflow_python_build.py`, then `pytest -q tests/test_workflow_python_build.py`. Independent review with special attention to source capture, trusted-code limits, authority and failed publication; corrections; commit `feat(py): add isolated frozen source builds`.

## Task 6: Public CLI, Runtime Delegation, Recovery And Guidance

**Create:** `orchestrator/cli/commands/python.py`, `tests/test_workflow_python_cli.py`, the three example files and `docs/python_workflow_drafting_guide.md` listed above.
**Modify:** `orchestrator/cli/main.py`, `orchestrator/py/{__init__,build}.py`, `docs/{index,capability_status_matrix,architecture_overview,lisp_workflow_drafting_guide}.md`, `docs/design/README.md`, `specs/{cli,dsl}.md`, `workflows/README.md`, and this plan's evidence ledger.

- [ ] Add red selectors `test_public_py_build_check_and_entry_selection`, `test_public_py_run_branch_loop_order_and_zero_budget`, `test_public_py_resume_uses_snapshot_without_python`, `test_public_py_frozen_refuses_without_mutation`, `test_documented_python_example_runs`.
- [ ] Run `pytest -q tests/test_workflow_python_cli.py::test_public_py_build_check_and_entry_selection`; confirm missing command dispatch fails.
- [ ] Register `orchestrator py build FILE.py`, `py check FILE.py`, `py run FILE.py` with `--entry-workflow`, existing source/manifest flags, inputs and `--frozen` where applicable. Reuse parser-created ordinary run defaults instead of copying a growing `Namespace` table. Build/check authoring failures exit 2; runtime delegation retains `RunWorkflowResult` and existing 0/1/2 meanings. API `run(...)` forwards the generated retained recipe to existing `run_workflow`.
- [ ] Run the public command-only branch/loop fixture with selected/ignored/unselected calls and bound 0/3. Assert typed terminal values and command dispatch order/count; unselected arms have no attempts, reused results have one attempt, ignored selected effects run. `check` must create no effects/run state and must not move a pin.
- [ ] Interrupt just after a committed command using the existing test-only commit-gate pattern in `test_workflow_evaluated_resume_kills.py`. Invoke public `py run` dispatch; then change/remove original Python sources before ordinary `orchestrator resume RUN_ID`. Verify the committed command is never repeated, the remaining command runs once, and completed resume leaves authoritative memo/attempt files unchanged. No production test hooks, special Python resume command, or timing-only inference.
- [ ] Add a copyable command-only example with a manifest and output-bundle tool. Its guide command is `python -m orchestrator py run workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json --input limit=3`. The fixture should return integer `2` after two counted work calls; `limit=0` returns `0` with no counted work call. Test that documented command, plus build/check and frozen refusal. Guide provider examples use explicit extern manifests and clearly require configured backends; no live execution is selected.
- [ ] Document API spellings, `TARGET` effects/lowering rules, source capture/frozen semantics, trusted build execution, direct inspectable `.orc`, normal resume, and deferred Agent/parallel APIs. Route from docs/design/capability/workflow indices; correct the maintained capability and architecture-overview claims that Lisp is the only authoring frontend. Scope the ORC-only execution wording in `docs/lisp_workflow_drafting_guide.md` and `specs/dsl.md` to ordinary `run`/evaluated input, linking the Python generation route. Search equivalent maintained statements with `rg` and inspect each document's role; preserve historical records. Keep delivery chronology in this plan and evidence, not the guide. Add the CLI contract without loosening ordinary `run` suffix admission or YAML retirement.
- [ ] Run `pytest --collect-only -q tests/test_workflow_python_cli.py`, then `pytest -q tests/test_workflow_python_cli.py`. Complete the integration suite below and independent final review; coordinator inspects final diff/evidence and records limitations before committing `feat(py): expose public cli and recovery guide`.

## Integration And Final Acceptance

Use @superpowers:verification-before-completion and @tmux. After the narrow task selectors, run this broader affected suite in tmux (capture exit status and a log, poll without blocking communication):

```bash
pytest -q -n 16 --dist=worksteal tests/test_workflow_python_declarations.py tests/test_workflow_python_control.py tests/test_workflow_python_procedures.py tests/test_workflow_python_imports.py tests/test_workflow_python_build.py tests/test_workflow_python_cli.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_loops.py tests/test_workflow_evaluated_resume_kills.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_closed_program_names.py tests/test_workflow_lisp_design_review_execute_example.py
```

Expected: exit 0, every selected test passing. The existing 73-test baseline is evidence only for its original three modules, not a substitute for the new selectors. Add a broader/full suite only if failures, changes below the frontend boundary or unresolved risks justify it; any broad/full invocation uses `pytest -q -n 16 --dist=worksteal` in tmux. Do not weaken a check to hide a failure.

| Design acceptance | Required evidence |
| --- | --- |
| Complete typed serial API and refusal boundaries | Tasks 1–3 compiler-positive/negative tests and exact target checks. |
| Effects, ordering, reuse and branch locality | Tasks 2–3 checked forms plus Task 6 real command attempts/order. |
| Explicit bounded exhaustion including zero | Tasks 3/6 result and command-count assertions. |
| Forward references, exact fresh bytes and stable owners | Tasks 1/4/5 with relocation and unchanged size/mtime/cache cases. |
| Real `.orc` bridge, types, prompts and generic application | Task 4 compile through actual export catalogs; missing/private/old-target refusal. |
| Generated/handwritten compiler identity parity | Task 3 exact program digest and sites, equal declared names, retained binding/effect labels and configuration. |
| Manifest-only authority and immutable captured recipe | Tasks 1/3/5 missing bindings, full argv, no default bindings, snapshot/pin tests. |
| Frozen correctness and failed-build non-mutation | Task 5 all input classes; Task 6 public missing-pin/change refusal. |
| Public run and ordinary recovery without Python | Task 6 interrupted commit + original-source removal + read-only completed resume. |
| Python provenance with retained compiler diagnosis | Tasks 1/5 map/error assertions and imported-source attribution. |
| Copyable docs and unchanged ordinary `.orc` route | Task 6 documented command, existing evaluated CLI/example regression selectors. |
| Independent integration review | Distinct code reviewer; coordinator inspects diff and current logs before completion. |

## Decision And Evidence Ledger

| Date | Decision / evidence | Status |
| --- | --- | --- |
| 2026-10-22 | Owner authorized design correction, implementation plan and full worktree execution; no extra approval pause. | Selected |
| 2026-10-22 | Independent design approval recorded; accepted design committed as `ce75721a`. Six dependent tasks preserve all four required design boundaries; imports separated from durable build integration. | Planned |
| 2026-10-22 | Manifest-only providers/commands; command call supplies full argv; Prompt.extern source comes from prompt manifest; no defaults. | Accepted design |
| 2026-10-22 | `RelPath` subclass, fill subscripts, `else_`, file + `entry_workflow`, per-module `TARGET`; pre-2.39 procedures explicitly emit inline. | Accepted design |
| 2026-10-22 | Copy only project-local imports/assets; packaged stdlib stays in its installed root, consumed hashes retained. | Accepted design correction |
| 2026-10-22 | Dedicated worker result file, parent closed compilation, confined atomic snapshot publication and existing-snapshot byte verification. | Implementation decision |
| 2026-10-22 | Existing `test_workflow_evaluated_cli.py`, `test_workflow_lisp_closed_program_artifact.py`, `test_workflow_lisp_design_review_execute_example.py`: 73 passed in 7.17s, `/tmp/python-api-baseline.log` (coordinator evidence). | Baseline only |
| 2026-10-22 | No paid providers, judges, or quality-comparison experiments; compile/local commands/stubs only. | Spend constraint |
| 2026-10-22 | Task 1 independently approved after metadata-field/name hygiene, reachable-definition, strict boolean path option and foreign-call diagnostic fixes. Final collection: 53 tests; module: 53 passed in 4.61s, `/tmp/python-foundation-review-{collect,green}.log`. Coordinator inspected the code and logs; an earlier independent module run passed 44 tests before final regressions. | Task 1 complete |
| 2026-10-22 | Existing compiler has Optional transport but no null source constructor or generic list index operator. Explicit Python None/index refusals documented and tested; no synthesized semantics. | Verified scope clarification |
| Pending | Tasks 2–6 commits, collection/regression logs, public smoke/recovery results, final diff review. | Record as executed |

Completion requires all six tasks and the acceptance rows above. Compilation and local command evidence establish implementation and integration only; they do not qualify live providers, environmental reproducibility, parallel execution or Agent sessions.
