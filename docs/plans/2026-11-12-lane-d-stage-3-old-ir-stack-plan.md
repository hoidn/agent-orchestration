# Lane D Stage 3: Delete The Old IR Stack

**Status: Plan, accepted 2026-11-12.** This page plans stage 3 of [Lane
D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed):
delete the bundle-era intermediate representations under `orchestrator/workflow/` and move the few
names that live code still uses. It is a plan, not a contract, and not copy-safe guidance. Behavior
is owned by `specs/` and by [evaluated execution](../design/workflow_lisp_evaluated_execution.md);
until the tasks land, those documents and the code describe the checkout. No provider spend.

Approach: cut the three groups of import edges from live code first (dead leaves, the frontend's
unused bundle path, the run-reference config classes), then delete the core chain in one step.
What this makes harder is listed [below](#what-this-makes-harder).

Not planned here: the two live-provider source forms (kept by owner decision 9), targets (stage
4), `orchestrator/state.py`, the prompt-evidence modules, `prompt run` and `prompt import`.

## What Is True Today

Checked at `066aed5b` with: an AST import scan of all 1,331 tracked `.py` files; `git grep`;
`pytest --collect-only` (15,426 items); CLI probes; a compile of all 685 tracked `.orc` files; and
a function-level trace (`sys.monitoring`) of the whole suite in an exported copy of the commit
(14,248 passed; 161 failed or errored there because of the copy: long temp path, no git checkout,
tmux), plus a second traced pass over the 88 test modules that set `PYTHONPATH` themselves.

**The stack: 25 modules in `orchestrator/workflow/`, 10,600 lines, and three tails.**

| Module (lines) | Importers outside the stack | Names they use | Verdict |
| --- | --- | --- | --- |
| `executable_ir.py` (1,535) | `workflow/evaluated/run_ref.py`, `workflow/run_ref/{child,path_compile,runtime}.py`; `managed_jobs/runtime.py` (type-checking only); 5 test modules | `RunRefStepConfig`, `StepCommonConfig`; `ManagedJobsConfig` | Two live classes, 96 lines with their helpers |
| `surface_ast.py` (566) | `workflow_lisp/{contracts,build_manifest_io,phase_family_boundary,typed_prompt_inputs}.py`; 3 test modules | `SurfaceContract` (constructed in `derive_workflow_signature_contracts`); `SurfaceStep` (one `isinstance` that is never true); `PrivateExecContextBinding` (in two functions nobody calls); `SurfaceStepKind` (in a report builder only tests call) | One live name |
| `loaded_bundle.py` (354) | `workflow_lisp/{compiler,workflows,workflow_refs}.py`, `workflow_lisp/closed/frontend.py`; 1 test module | `LoadedWorkflowBundle`, `WorkflowBoundaryProjectionView`, `workflow_boundary_projection`, `workflow_input_contracts`, `workflow_output_contracts`, `workflow_public_input_contracts` | No live name: every use is on a path that never runs (next table) |
| `signatures.py` (484) | `cli/commands/evaluated.py`; 2 test modules | `bind_workflow_inputs`, `WorkflowSignatureError` (78 lines). `resolve_workflow_outputs` and nine helpers (372 lines) are called only by one test module | Stays, trimmed |
| `references.py` (290) | `workflow/run_ref/runtime.py` | `ReferenceResolver`, `ReferenceResolutionError` (178 lines reachable) | Stays, trimmed |
| `identity.py` (157) | `workflow/provider_attempts.py` | `STEP_ID_PATTERN`, one regular expression | One constant |
| `executor_runtime.py` (6) | `workflow/prompting.py` | `RuntimeStepInput`, a type alias used in annotations | Alias |
| `core_ast.py` (1,529), `semantic_ir.py` (521), `runtime_plan.py` (850), `runtime_step.py` (562), `state_projection.py` (867), `state_layout.py` (300), `transition_contract.py` (489), `provider_context.py` (144), `statements.py` (157) | None; they import each other. No test imports them | — | Dead as a whole |
| `linting.py` (305), `conditions.py` (287), `predicates.py` (277), `frontend_origins.py` (537), `runtime_context.py` (130), `runtime_types.py` (44), `step_results.py` (78) | None at all; the first three form a chain | — | Dead |
| `pointers.py` (108) | `workflow/__init__.py` re-exports `PointerResolver`; nothing uses it | — | Dead |
| Tail: `transition_executor.py` (23), `workflow_lisp/observability_summaries.py` (1,123), `workflow_lisp/consumer_rendering_census.py` (5) | None; the summaries module imports the other two | — | Dead |
| Tail: `orchestrator/managed_jobs/` (16 files, 1,342) | `tests/test_managed_job_shims.py` | — | Dead; the only user of `ManagedJobsConfig` (D2) |

So the roadmap's "dozen live types" are nine names, and only two need a new home.

**The trace agrees.** Across these modules the suite runs functions in five only:
`RunRefStepConfig.__post_init__`, `step_config_digest` and `_validate_static_config`;
`ReferenceResolver.resolve` with two parse helpers; `bind_workflow_inputs` (live) and
`resolve_workflow_outputs` (from its test module); three `loaded_bundle` helpers and
`SurfaceStep.__post_init__` (from `tests/test_workflow_surface_ast.py`); `empty_frozen_mapping`
(a default of `StepCommonConfig`). Compiling all 685 `.orc` files runs none of them. The trace sees
function calls only; constructors without `__post_init__`, enum members and constants come from
the static scan.

**Frontend code that exists only for the stack.** No code in `orchestrator/` or `tests/` builds a
`LoadedWorkflowBundle`. Production (`workflow_lisp/build.py::_compile_entry`,
`closed/artifact.py::_prepare_closed_program_bundle`, `py/_worker.py`) passes `imported_programs`
only; tests pass an empty mapping or nothing; and `_imported_workflow_bundle_fingerprint` calls
`workflow_executable_ir_to_json`, which `compiler.py` never imports, so the path would raise
`NameError` if it ran. The flag `--imported-workflow-bundles-file` is a different thing: it loads
typed programs from `.orc` sources and stays.

| File | Dead part | Lines (estimate) |
| --- | --- | ---: |
| `workflow_lisp/compiler.py` | The parameter `imported_workflow_bundles` of `compile_stage3_module`, `compile_stage3_entrypoint`, `_compile_stage3_graph`, `_derive_reusable_state_producer_context`, `_reject_duplicate_imported_program_bindings`, `_require_explicit_source_snapshots` and the functions that pass it on; `_bundle_boundary_contracts`, `_imported_workflow_bundle_fingerprint`, `_typed_program_matches_bundle`, `_bundle_boundary_facts_match`, `_bundle_span` | 150 |
| `workflow_lisp/workflows.py` | `WorkflowCatalog.imported_bundles_by_name`; the parameter and two loops in `build_workflow_catalog`; `_signature_from_imported_bundle`, `_hidden_context_requirements_from_bundle`, `_compatibility_bridge_types_from_bundle`, `_merge_signature_compatibility_bridge_types`, `_bundle_source_span` | 230 |
| `workflow_lisp/closed/frontend.py`, `workflow_lisp/workflow_refs.py`, `py/emit.py` | `TypedProgram._compiled_bundle_boundaries`, `_io_import_bundles`, `_io_workflow_bundles` and their loop in `__post_init__`; `_workflow_io_reader_from_bundle`; the parameter in `typed_program_from_graph`, `compile_typed_program_with_result`, `compile_typed_program`; `imported_bundle` in `resolve_workflow_ref_name` and `_extern_rebinding_plan_for_target`; the pass-through in `generate_graph` | 75 |
| `workflow_lisp/typed_prompt_inputs.py` | `build_typed_prompt_input_report` and 13 helpers; `select_prompt_fragment_renderer` is live and stays | 525 |
| `workflow_lisp/phase_family_boundary.py` | `apply_phase_family_boundary_classification`, `record_direct_entry_phase_context_binding`, `_phase_context_capabilities`: no caller, tests included | 141 |
| `workflow_lisp/build_manifest_io.py` | The `SurfaceStep` branch of `_json_data` | 8 |

## Where The Live Names Go

| Name | New home | Why this is the smallest move |
| --- | --- | --- |
| `RunRefStepConfig`, `StepCommonConfig`, `RUN_REF_STEP_CONFIG_IDENTITY_SCHEMA`, `_validate_static_config`, the two serializer helpers | New `orchestrator/workflow/run_ref/step_config.py`, copied verbatim (about 100 lines) | `run_ref/config.py` cannot hold them: `confined_config.py` imports `config.py`. The default `on` uses a three-line copy of `empty_frozen_mapping` |
| `SurfaceContract` | `orchestrator/workflow_lisp/contracts.py`, its only user | Eight lines; no new module |
| `bind_workflow_inputs`, `WorkflowSignatureError` | Stay in `workflow/signatures.py` | The dead half and its two stack imports go |
| `ReferenceResolver`, `ReferenceResolutionError` | Stay in `workflow/references.py` | Six unreachable names go |
| `STEP_ID_PATTERN` | One line in `workflow/provider_attempts.py` | Same pattern text |
| `RuntimeStepInput` | One line in `workflow/prompting.py`: `Mapping[str, Any]` | Annotations only |

**Identity, checked.** `orchestrator/` uses no `pickle`, `marshal` or `shelve`. `__module__` is
read in `py/emit.py` (user modules), `workflow_lisp/procedure_typecheck.py` (compares with
`NameExpr.__module__`) and `workflow_lisp/closed/preparation_check.py::record`, which skips `span`,
`form_path`, `expansion_stack` and `authored_callee_span` on dataclasses from
`orchestrator.workflow_lisp.*`. `SurfaceContract` moves into that package; its fields are `name`,
`kind`, `value_type`, `definition`, `from_ref`, so the rule does not change how it is compared.
`step_config_digest` hashes a schema string, the static config digest and the capsule record, no
module path. Three things must stay as they are:

- `_derive_reusable_state_producer_context` keeps the key `imported_workflow_fingerprints` with an
  empty mapping in its fingerprint payload.
- The strings `semantic_ir`, `executable_ir` and `runtime_step` in
  `workflow/provider_phased_delivery/diagnostics.py` and `workflow_lisp/diagnostics.py` are owner
  and pass labels in data, not imports.
- `compiler_runtime_identity_digest` hashes every file of the package
  (`run_ref/contracts.py::compute_compiler_runtime_identity`). Every task changes it, and with it
  the digest of every run-reference program, as any package change does.

## What The Refused Surfaces Need

- **The two live-provider forms.** Their parser, checker and elaboration live in 22 files under
  `orchestrator/workflow_lisp/`. None imports a stack module, so they need nothing from it. Their
  two implicit-empty reasons are in `workflow/prompt_dependency_contract.py`, which stays. Pinned
  by `test_each_selected_effect_outside_the_release_is_a_located_gap`
  (`tests/test_workflow_lisp_closed_program_effects.py`) and
  `tests/test_workflow_lisp_provider_peer_group.py`; both stay unedited.
- **`--emit-*` and `explain`.** `cli/commands/compile.py` refuses the six flags before the build
  with `workflow_lisp_cli_input_unsupported`; `explain` prints `[workflow_explain_retired]`. Neither
  imports the stack. No change (D7).
- **Retired runs.** `report`, the dashboard and the monitor use
  `workflow/evaluated/views.py::retired_run_refusal`; `resume`, `invalidate` and `input` raise
  `workflow_execution_profile_retired` from a header check. They depend on `orchestrator/state.py`
  and `workflow/human_input.py`, which this plan does not touch. Pinned by
  `tests/test_executor_retirement_cutoff.py` (42 items); all stay.
- **Route-readiness registry.** `workflow_lisp/route_readiness.py` imports the standard library
  only. `docs/workflow_lisp_route_readiness_registry.json` (65 surfaces) names no test module this
  plan deletes. No change; `tests/test_workflow_lisp_route_readiness.py` runs after Tasks 2 and 4.
- **LSP.** `orchestrator/lsp/` imports the frontend only and loads the stack today through
  `compiler.py`. After Task 2 it loads none of it. Checked by `tests/test_workflow_lisp_lsp_*.py`.

## Tests

| Module (items) | Kind | Action |
| --- | --- | --- |
| `tests/test_workflow_surface_ast.py` (2) | Stack only | Delete, Task 4 |
| `tests/test_managed_job_shims.py` (13) | Dead package; one test is named "fail closed", one covers its provider guard | Delete with D2 |
| `tests/test_workflow_output_contract_integration.py` (13) | Mixed: 12 call `resolve_workflow_outputs`; `test_bundle_guidance_is_runtime_neutral_for_value_validation` covers live `validate_output_bundle` | Remove 12, keep the file (D3); three documents link to it |
| `tests/test_workflow_lisp_typed_prompt_inputs.py` (25) | Mixed: 7 items call the report builder | Remove 7 and the `SurfaceStepKind` import |
| `tests/test_workflow_evaluated_dashboard.py` (34) | Live; `test_dashboard_and_report_do_not_load_the_bundle_stack` cannot fail once the modules are gone | Remove that one in Task 4; the removal rows replace it |
| `tests/test_workflow_lisp_build_artifacts.py` (12) | Live; an unused class `_HistoricalSurfaceGraph` imports two stack names | Drop the class and import |
| `tests/test_workflow_evaluated_{child_values,path_compile,run_ref_caller}.py`, `tests/test_workflow_run_ref_runtime.py`, `tests/workflow_evaluated_run_ref_helpers.py` | Live, never-delete (kill, resume, recovery) | Import path only |
| `tests/test_workflow_lisp_{command_control,command_scopes,run_ref}.py`, `tests/workflow_lisp_closed_program_corpus.py` | Live | Drop the empty bundle argument (seven call sites) |
| `tests/test_workflow_run_ref_config.py` (168) | Live; one subprocess blocks two stack module names before lookup | No edit; it passes with the modules gone |

Never-delete classes (kill, resume and recovery; memo durability; checker soundness; provider and
command result validation; security and confinement; CLI end to end): no item of these classes is
removed, with two cases that need a ruling because of their names: D2 and D3. Expected count:
15,426 collected today; 22 removed (35 with D2); about 75 added.

## What A User Sees Afterwards

Nothing changes in commands, flags, exit codes or diagnostics. The proof is the compile of every
tracked `.orc` file, byte for byte. Intended differences, all for Python callers:

- `RunRefStepConfig` and `StepCommonConfig` import from `orchestrator.workflow.run_ref.step_config`;
  `SurfaceContract` from `orchestrator.workflow_lisp.contracts`.
- The deleted modules raise `ModuleNotFoundError`. `from orchestrator.workflow import
  PointerResolver` stops working. The compiler functions no longer accept
  `imported_workflow_bundles`, and `WorkflowCatalog` has no `imported_bundles_by_name`.
- With D2, `orchestrator.managed_jobs` is gone; no command or flag reached it.
- `experiments/evaluated_execution_spike/run_ref.py` stops importing (its `trial.py` already
  does not). The untracked `experiments/orc_research_demo/assessment_*.py` import stack modules,
  and already import `orchestrator.workflow.pure_result_replay`, which no longer exists.

## Invariant Checks

Three files, made in Task 0 and reproduced after Tasks 1 to 4. The planner ran all three at
`066aed5b`; the scripts are session scratch in
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/plan-lane-d3/`.

| Check | Method | Result at `066aed5b` |
| --- | --- | --- |
| Corpus snapshot | `digests.py`: `program.digest` or the refusal code for every row of `tests.workflow_lisp_closed_program_corpus.corpus()` | 55 rows, 11 built, 44 refused; SHA-256 `810baec5…2a1ce0`; identical to stage 1's file |
| Compile of every tracked `.orc` file | `compile_all.py` on a `git archive` export: exit code, stdout (it carries `program_digest`) and stderr of `python -m orchestrator compile <file>`, each from an empty directory | 685 files, 37 exit 0, 648 exit 2; SHA-256 `f6083831…79586c`; the same from two different directories; about one minute |
| Run-reference programs | Serial run (`-p no:xdist`, fixed `--basetemp`) of `tests/test_workflow_lisp_run_ref*.py`, `tests/test_workflow_evaluated_run_ref*.py` and `tests/test_workflow_lisp_closed_program_effects.py`; then `program_digests.py` hashes every `closed_program.json` that holds a run-reference config, after removing `compiler_runtime_identity_digest` and `resolved_commit_sha`, also inside the base64 `config` | 400 passed; 249 files, 125 test folders, 128 distinct programs; SHA-256 `f2a28b6f…167496`; two runs gave the same file; about 3.5 minutes |

Two cautions. `compile` writes `.orchestrate/build/` under the working directory, so the second
check never runs inside the repository. The third check is not reproducible under xdist (worker
folders enter the embedded paths) or with `resolved_commit_sha` kept (the tests make a new commit
on every run).

## How The Import Edges Are Cut

Live code reaches the stack by three groups of edges, in disjoint files, so they are cut in
parallel: leaves that nothing imports (Task 1); the frontend (Task 2); the run-reference classes
and three one-line uses (Task 3). After that no module outside the chain imports it, and the chain
goes in one task in this order: `loaded_bundle` → `semantic_ir` → `core_ast`, `runtime_plan`,
`transition_contract` → `state_projection` → `runtime_step`, `executor_runtime` → `executable_ir`
→ `surface_ast`, `provider_context`, `statements`, `identity` → `state_layout`. No stub, no
re-export.

## Global Constraints

- Deletions and the moves in [Where The Live Names Go](#where-the-live-names-go) only. No refactor
  beyond cutting an edge. The two live-provider forms are not edited.
- Re-run the import scan at each task's base; the tables here are the expected result. Delete a
  definition only when a scan of `orchestrator/`, `tests/`, `scripts/` and non-frozen
  `experiments/`, `importlib` strings included, finds no reference. A missed caller means stop
  and record it; no shim.
- Tests assert behavior. A test goes only with the code it covered, and the ledger lists both.
- Off limits: `orchestrator/state.py`; `workflow/prompt_dependency_*.py`, `prompt_identity.py`;
  frozen files under `experiments/`; untracked files; `.worktrees/` of other sessions.
- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`. Separate
  worktrees; `PYTHONPATH` set to the working tree (the editable install points elsewhere);
  `experiments/thread_m/no_provider` first on `PATH`; long runs in tmux from an existing session.
- **Gate, for every commit:** no test outside the four worktree-artifact ids of the [test
  baseline](../reports/2026-11-11-test-baseline.md) fails. During work: the task's narrow run, then
  `pytest -q -n 16 --dist=worksteal --sample 10`; before each merge to `main`, the same without
  `--sample`, and the three invariant files equal to Task 0's. `pytest --collect-only` on each
  test module added or edited.

## Tasks

Sizes: S is up to one day, M two to four. Task 0 first. Tasks 1, 2 and 3 run in three worktrees
and share no file; Task 5 is drafted beside them. Task 4 starts when 1 to 3 are on `main`, and
merges together with Task 5 so that code and documents agree. Task 6 last.

### Task 0: Tag and baselines (S, 0.25 day)

- [ ] Create the local annotated tag `archive/old-ir-stack-2026-11-12` on the `main` commit the
      work starts from; do not push it (D6). Record the suite result and the collected count.
- [ ] Make the three invariant files and record their SHA-256. If the base is not `066aed5b`,
      the first and second must still equal the values above; if not, find out why before any edit.
- [ ] In a scratch workspace start the two-command pipeline of `docs/tutorial_first_pipeline.md`
      with a second command that waits for a file; kill the process group; keep it for Task 6.

### Task 1: Modules nothing imports (S, 0.5 day; 2,917 lines, 4,259 with D2)

Delete `orchestrator/workflow/{linting,conditions,predicates,frontend_origins,runtime_context,runtime_types,step_results,pointers,transition_executor}.py`
and `orchestrator/workflow_lisp/{observability_summaries,consumer_rendering_census}.py`. Reduce
`orchestrator/workflow/__init__.py` to its docstring. With D2: delete `orchestrator/managed_jobs/`
and `tests/test_managed_job_shims.py` (13 items).

- [ ] Add one row per deleted module to `REMOVED_PACKAGES` and `FORMER_PUBLIC_MODULES` in
      `tests/test_retired_executors_removed.py` and widen its docstring (D5). See the rows fail
      first. The existing tests then check: the source is absent, the module does not import, and
      nothing in `orchestrator/` or `tests/` imports it.
- [ ] Narrow run: that module, `tests/test_workflow_evaluated_cli.py`,
      `tests/test_first_hour_e2e.py`. Invariant files.

### Task 2: The frontend stops importing the stack (M, 3 days; about 1,130 lines)

| Edit | Remove or move |
| --- | --- |
| `orchestrator/workflow_lisp/{compiler,workflows,workflow_refs}.py`, `closed/frontend.py`, `orchestrator/py/emit.py` | Everything in the frontend table above that names a bundle; then what it leaves unreferenced. Keep `imported_workflow_fingerprints` as an empty mapping |
| `orchestrator/workflow_lisp/contracts.py` | Define `SurfaceContract` here, verbatim; drop the import |
| `orchestrator/workflow_lisp/typed_prompt_inputs.py`, `phase_family_boundary.py`, `build_manifest_io.py` | The report builder and its helpers; the three uncalled functions; the `SurfaceStep` branch; the three imports |
| Tests, removed with the code | The 7 report items of `tests/test_workflow_lisp_typed_prompt_inputs.py`; `_HistoricalSurfaceGraph` in `tests/test_workflow_lisp_build_artifacts.py` |
| Tests, edited | The empty bundle argument in the four files named under [Tests](#tests) |

- [ ] Add to `tests/test_retired_executors_removed.py` one test: no file under
      `orchestrator/workflow_lisp/`, `orchestrator/py/` or `orchestrator/lsp/` imports
      `surface_ast`, `loaded_bundle`, `executable_ir`, `core_ast`, `semantic_ir` or `runtime_plan`.
      See it fail first.
- [ ] Narrow run: `tests/test_workflow_lisp_*.py` (in tmux), `tests/test_workflow_python_*.py`,
      `tests/test_workflow_evaluated_repl*.py`, `tests/test_first_hour_e2e.py`. Invariant files:
      this is the task where a difference is most likely; if one appears, stop.

### Task 3: Run-reference classes and the one-line uses (S, 1 day; 372 lines)

| Edit | Remove or move |
| --- | --- |
| New `orchestrator/workflow/run_ref/step_config.py` | The names in the first row of [Where The Live Names Go](#where-the-live-names-go), verbatim |
| `orchestrator/workflow/evaluated/run_ref.py`, `orchestrator/workflow/run_ref/{child,path_compile,runtime}.py`, the five test modules | The import path |
| `orchestrator/workflow/prompting.py`, `provider_attempts.py` | A local `RuntimeStepInput`; a local `STEP_ID_PATTERN` |
| `orchestrator/workflow/signatures.py` | `resolve_workflow_outputs`, its nine helpers and two constants; the imports of `executable_ir` and `references` |
| `tests/test_workflow_output_contract_integration.py` | The 12 items that call `resolve_workflow_outputs` (D3) |

- [ ] Do not delete the classes from `executable_ir.py` here; Task 4 deletes the module.
- [ ] Narrow run: `tests/test_workflow_run_ref*.py`, `tests/test_workflow_evaluated_run_ref*.py`,
      `tests/test_workflow_evaluated_{child_values,path_compile,host_input_recovery}.py`,
      `tests/e2e/test_e2e_workflow_evaluated_run_ref.py`,
      `tests/test_workflow_evaluated_resume_kills.py`, `tests/test_resume_command.py`. Invariant
      files; the third one matters most here.

### Task 4: The chain (S, 1 day; 8,149 lines)

Delete, in the order of [How The Import Edges Are Cut](#how-the-import-edges-are-cut):
`orchestrator/workflow/{loaded_bundle,semantic_ir,core_ast,runtime_plan,transition_contract,state_projection,runtime_step,executor_runtime,executable_ir,surface_ast,provider_context,statements,identity,state_layout}.py`.
In `orchestrator/workflow/references.py` delete `parse_surface_ref`, `SurfaceRefScopeCatalog`,
`WorkflowInputReference`, `StructuredStepReference`, `SelfOutputReference` and
`MaterializeViewBindingReference`. Delete `tests/test_workflow_surface_ast.py` (2 items) and
`test_dashboard_and_report_do_not_load_the_bundle_stack`.

- [ ] First re-run the scan: no file outside these fourteen imports any of them. Add their rows to
      the removal test and one line to `experiments/evaluated_execution_spike/README.md` (one more
      of its files imports a removed module; see the tag).
- [ ] Narrow run: the removal test, `tests/test_executor_retirement_cutoff.py`,
      `tests/test_workflow_evaluated_dashboard.py`, `tests/test_cli_report_command.py`,
      `tests/test_workflow_lisp_lsp_*.py`, `tests/test_workflow_lisp_route_readiness.py`,
      `tests/test_first_hour_e2e.py`. Invariant files.

### Task 5: Specs and documents (S, 1 day)

Rule: edit only text that says the stack exists as code today. Historical records keep their
bodies. Regenerate the list with `git grep -nE "executable_ir|runtime_plan|core_ast|semantic_ir|surface_ast|loaded_bundle|Semantic IR|Executable IR|Core Workflow AST" -- specs docs/design docs/*.md orchestrator/workflow_lisp/README.md`.

| Document | Change |
| --- | --- |
| `docs/design/workflow_lisp_semantic_workflow_ir.md`, `workflow_lisp_core_workflow_ast.md`, `workflow_lisp_state_layout.md`, `workflow_lisp_core_stmt_taxonomy.md` | Status Historical, with a scope notice: code removed, the tag, the current owner. Body kept. Before that, move any rule that is still current and stated only there (D8) |
| `docs/design/README.md`, `docs/index.md` | The three rows that say "Partial: retained typed/shared-service scope"; the bullet "Semantic IR, Executable IR, Stdlib Lowering and State Layout document … retained data contracts"; a row for this plan |
| `docs/capability_status_matrix.md` | "Semantic IR": Retired, code removed, the tag. "Executable IR": drop "required shared services remain" |
| `docs/design/workflow_lisp_consolidation.md` | The paragraph that says the two run-reference classes remain in `workflow/executable_ir.py`: they are in `workflow/run_ref/step_config.py` and the module is gone |
| `docs/design/workflow_lisp_frontend_specification.md` | "Shared Component Ownership And Historical Contracts" and the list of module paths that names `orchestrator/workflow/surface_ast.py` and three siblings: say they were removed and name the tag |
| `docs/lisp_workflow_drafting_guide.md`, `orchestrator/workflow_lisp/README.md` | The sentences "Semantic/Executable IR retain their component…" and "Older Core/Semantic/Executable IR … are retained"; two links |
| `specs/state.md`, `specs/providers.md`, `specs/dsl.md` | The sentences that carry an identity "through Semantic IR, Executable IR": name the closed program, after checking the code. With D2: the `managed_jobs` blocks become a three-line removal notice |
| `specs/cli.md` | No change: the `--emit-*` line already says the flags refuse |
| The roadmap's "Routing and records" | One line for this stage |

- [ ] Make the edits; run the document tests `$(git grep -lE "docs/|specs/" -- 'tests/*.py')`.

### Task 6: Final verification (S, 0.5 day)

- [ ] The removal test passes with every row; the three invariant files equal Task 0's.
- [ ] End to end with the final code: `python -m orchestrator resume <id>` completes Task 0's
      killed run and `report` shows both effects, the first dispatched once. Then the same
      pipeline is compiled, run, killed and resumed afresh. On a retired run, `report` prints
      its one `Error:` line and `resume` its two (the logged refusal, then the same refusal after
      `Error:`), as on base; both exit 2. `specs/cli.md` fixes the one-line form only for `report`.
- [ ] Known limit, not changed here: a run that uses a run reference and is in flight when any
      package file changes cannot be resumed afterwards (`resume_program_changed`), because the
      program digest embeds a hash of every package file. This is how `main` behaves before this
      stage, not something it causes; each Lane D merge therefore strands such in-flight runs. The
      cross-version check above holds only for programs without a run reference.
- [ ] Full suite within the gate. Record in the ledger the lines removed per task
      (`git diff --shortstat` against the tag), the collected items before and after, and every
      removed test with the code it covered.

## Size

| Task | Size | Days | Production lines removed | Test items removed |
| --- | --- | ---: | ---: | ---: |
| 0 Tag and baselines | S | 0.25 | 0 | 0 |
| 1 Modules nothing imports | S | 0.5 | 2,917 (4,259 with D2) | 0 (13 with D2) |
| 2 Frontend | M | 3 | about 1,130 | 7 |
| 3 Run-reference classes | S | 1 | 372; about 100 moved | 12 |
| 4 The chain | S | 1 | 8,149 | 3 |
| 5 Documents | S | 1 | — | 0 |
| 6 Final verification | S | 0.5 | 0 | 0 |
| **Total** | | **7.25** | **about 12,570 (13,910 with D2)** | **22 (35 with D2)** |

Elapsed time with three worktrees is about four days. About 900 lines of tests go (1,000 with
D2). The frontend figure is an estimate from function spans; the ledger records the real figures.

## What This Makes Harder

- Reading or building the old bundle, Core AST, Semantic IR, Executable IR or runtime plan from
  Python. Nothing does today. Fallback: `git worktree add ../orc-old-ir archive/old-ir-stack-2026-11-12`.
- Importing a precompiled workflow as a bundle object. The only supported import is a typed
  program from `.orc` source (`imported_programs`); a second kind would be new work.
- A port of live supervision or peer groups cannot reuse the step kinds `provider_supervision`
  and `provider_peer_group` of the old enums. The
  [salvage record](../design/live_provider_supervision_and_peers_salvage.md) already says the
  port needs its own design on evaluated execution.
- The typed-prompt-input report, a migration evidence view, can no longer be produced.
- With D2, managed jobs for provider steps would be a new feature on evaluated execution.

## Decisions For The Coordinator

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | The frontend's bundle path: delete it (Task 2), or keep it and move six `loaded_bundle` names to a small module | Delete. It cannot run, and it is the only reason the frontend imports the stack |
| D2 | `orchestrator/managed_jobs/` and its 13 tests: delete with the stack, or keep and copy `ManagedJobsConfig` and `ManagedJobsRoutes` into `managed_jobs/models.py` | Delete. Nothing reaches it. It needs a ruling: its tests read as guard tests (one is named "fail closed"), and the spec text of `managed_jobs` in `specs/dsl.md` and `specs/providers.md` becomes a removal notice |
| D3 | The 12 tests of `resolve_workflow_outputs`: remove with the function, or keep both | Remove. No production caller. It needs a ruling because the class is result validation |
| D4 | `StepCommonConfig`: move it verbatim, or drop the unused `common` field of `RunRefStepConfig` | Verbatim now; no live code reads `common`, so dropping it is a later clean-up |
| D5 | The removal test: rows in `tests/test_retired_executors_removed.py`, or a new module | Rows in the existing module |
| D6 | Tag name, local only | `archive/old-ir-stack-2026-11-12` |
| D7 | `--emit-*` flags and `explain`: keep refusing, or remove them | Keep, as stage 2 ruled for the flags that do nothing; revisit in stage 4 |
| D8 | The four design documents: Historical with a scope notice | Yes, after a check that no current rule lives only there |
| D9 | Leftovers seen and not planned: the legacy halves of `RunState` in `orchestrator/state.py`; `workflow/prompt_dependency_evidence.py` and `prompt_identity.py` (3,559 lines, live through two private names used by the phased-delivery ledger); `workflow_lisp/verification_gate.py` (190 lines, no importer); `ControlFacts.signature` | A separate small plan after this stage; do not widen this one |
| D10 | The untracked `experiments/orc_research_demo/assessment_*.py` | Leave them; tell their owner. They already fail to import |

## Not Verified

- That the invariant files stay equal through any task. Only the baselines and the methods were
  run; no deletion was tried.
- The frontend line estimates, and which helpers become unreferenced after Task 2.
- That the trace saw every path: 161 tests did not pass in the exported copy, and a process
  started with a cleared environment is not traced.
- The suite result at `066aed5b` in the real checkout; the traced runs are not a baseline.
- Whether evaluated execution checks workflow outputs as strictly as `resolve_workflow_outputs`
  did (D3), and whether any design document of D8 holds a rule that is current only there.
- Whether a document test pins a sentence Task 5 edits; dynamic imports beyond a text search.
- `orchestrator/exec/retry.py` and `workflow_lisp/wcc/historical.py` look unused or historical;
  they were not analysed.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-12 | Plan accepted by the coordinator. Tasks 1 and 3 run in one worktree and Task 2 in another, in parallel; Task 4 follows all three and merges with Task 5. The local tag `archive/old-ir-stack-2026-11-12` marks `main` before the first deletion. Each task recomputes the three invariant baselines at its own base with the planner's scripts, since `main` has moved since `066aed5b`. No provider spend. |
| 2026-11-12 | Rulings D1, D4, D5, D6, D7: as recommended. The frontend's imported-bundle path is deleted (it cannot run: it calls a name its module does not import); `StepCommonConfig` moves verbatim; the removal test gains rows in `tests/test_retired_executors_removed.py`; `--emit-*` and `explain` keep refusing. |
| 2026-11-12 | Ruling D2 (`orchestrator/managed_jobs/` and its 13 tests): delete, on one condition checked first. An import scan does not see a package that is started by name. The implementer shows that no entry point, `python -m` invocation, shell script, provider template, manifest or operator guide starts it, and that `orchestrator/state.py`'s mention is a dead field or goes with it. If anything starts it, the package stays and the finding is reported. Reason for deleting: evaluated execution is the only runtime and never reaches it, so its "fail closed" tests guard nothing a user can run. If wrong: a job-management route used from outside this repository stops working; the tag holds it. |
| 2026-11-12 | Ruling D3 (the 12 tests of `resolve_workflow_outputs`): the function goes, since nothing calls it, but not its properties. Before deleting, each property those tests assert about workflow outputs is matched to a test on the evaluated path; a property with no such test gets one, or is reported as a gap in what evaluated execution validates. |
| 2026-11-12 | Rulings D8, D9, D10: the four design documents become Historical with a notice after a check that no current rule lives only there; the leftovers D9 names (legacy halves of `RunState`, `prompt_dependency_evidence.py`, `prompt_identity.py`, `workflow_lisp/verification_gate.py`, `ControlFacts.signature`) get a small separate plan after this one; the untracked `experiments/orc_research_demo/assessment_*.py` belong to another session, already fail to import, are left alone, and the owner is told. |
| 2026-11-12 | Tasks 1 and 3 done on `chore/lane-d3-leaves` (5,085 lines removed, 208 added) and reviewed: approve, five minors, nothing live changed. The reviewer's own runs from exports of base and tip give identical corpus snapshot, compile results for all 685 `.orc` files and run-reference program digests. **D2:** `orchestrator/managed_jobs/` is deleted. It was the runtime of the YAML v2.13 `managed_jobs` step option (shims for `python`, `torchrun`, `conda` and `uv` first on `PATH`, routing training jobs to a local or Slurm runner); nothing creates its wrapper class, no `.orc` form or provider template asks for it, and no live file uses its shim names, variables or file names. Its "fail closed" test was routing hygiene for that option, not part of provider isolation, whose code is byte-identical before and after. **D3:** each property the 12 deleted tests asserted about workflow outputs is matched to an evaluated-path test; two had none and got one. The reported gap (a union group's name need not prefix its discriminant's name) is not a hole and is not to be added: the group name is only a grouping key, and the live host-reply contract uses group `human_reply` with discriminant `variant`, which the old rule would reject. For Task 5: the `managed_jobs` text in `specs/dsl.md`, `specs/providers.md`, `specs/versioning.md` and `specs/state.md` is YAML-era history in the present tense and gets a removal notice. Plan corrections: `orchestrator/workflow/__init__.py` keeps `__all__ = []` because a retained test reads it; `managed_jobs` has a source-file removal row only, since another checkout's old editable install still resolves the package by name. Not merged yet: it merges with Task 2 after one full suite on both. |
| 2026-11-12 | Task 2 done on `chore/lane-d3-frontend` (about 1,330 production lines) and reviewed: approve, no finding above a nit. The reviewer repeated the reachability proof with 68 tripwires over 10,095 tests, 1,058 compiles (every tracked `.orc` file, and again with manifests made up from the source so that 125 build) and a language-server session; only the 7 removed test items tripped. Output, exit codes, digests and all 250 build artifacts are identical on base and tip. `module_import_collision` is no longer produced; no input ever produced it, since it needed a bundle. Tasks 1 to 3 merged together after one full suite on both branches with `main`: 14,520 passed, only the four worktree-artifact failures. Next: Task 4 (the chain) with Task 5 (specs and documents). |
| 2026-11-12 | Tasks 4 and 5 done on `chore/lane-d3-chain` and reviewed: approve with fixes, no blocker or major. The review's fixes are applied: six definitions the chain's removal left dead are deleted with the tests that only they had; the drafting guide no longer tells authors to allocate through `StateLayout`; the runtime-closures boundary states its rule against the checked closed program; the removal test parses each file once; Task 6 states `resume`'s two-line refusal. **Coordinator ruling (review finding m1):** a run that uses a run reference and is in flight when any package file changes cannot be resumed afterwards (`resume_program_changed`), because the program digest embeds `compiler_runtime_identity_digest`, a hash of every package file. This is behaviour of `main` before this branch, not caused by it; each Lane D merge strands such in-flight runs. Not changed in this branch. Whether the parent's resume check should ignore the compiler identity is handed to Phase 3b (edited-program resume), which owns the program-equality refusal. Skipped by ruling: the check of module names built by string concatenation, and a home for State Layout's vacuous private-input rule. |
| 2026-11-12 | Tasks 4 to 6 merged to `main` (`25d82c89`); stage 3 is done | Full suite on the branch after merging `main` (with Phase 3b T2): 14,745 passed, the four nanoBragg baseline failures, no provider called. The merge removes 8,784 lines in 45 files; production code is 212,750 lines. The three invariants are identical to their references on the merged tip (corpus snapshot, compile of all 690 `.orc` files, serial run-reference digests). Left for the leftovers plan (D9): two more definitions in `prompt_fragment_contract.py` that were already dead before this stage (`validate_compiler_prompt_attempt_binding_plan_authority`, `freeze_prompt_fragment_json`), and review nits n1 and n3. Recorded limit, not changed here: a run that uses a run reference cannot be resumed after any package file changes; the decision is assigned to Phase 3b (its ledger has the row). |
