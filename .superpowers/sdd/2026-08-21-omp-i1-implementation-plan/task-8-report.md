# Task 8 Report: Run prompts through generated Workflow Lisp

Date: 2026-08-24
Checkout: `.worktrees/omp-i1-prerequisites` @ base `3af650c5`
Commit: `Run prompts through generated Workflow Lisp`
Final hash: `d9bad712` (amended from `7ae0af76`; message unchanged)

## Scope delivered

Closed `prompt run` CLI grammar (generation: exactly one of
`--prompt`/`--prompt-file`, one public OMP provider, `--conf` iff `omp_conf`,
optional model, at most one of `--returns`/`--output`; verified rerun: exactly
`--scaffold PATH`), capture-before-mutation orchestration (prompt bytes,
registry template, concrete model, conf snapshot, contract request), closed
natural-language inference (`omp_no_tools|omp_conf -> omp_conf_inference`,
ambient providers fail before model/filesystem work), private reserved-run
snapshot materialization, compilation through the ordinary frontend, execution
through the ordinary `run_workflow`, and the minimal structured run seam
(`StateManager.new_run_id`, immutable `RunWorkflowResult`, keyword-only
internal `run_id`). No Task 9+ link/import/resume/TTY/docs work.

## RED evidence (written before production)

Step 8.1 grammar REDs (`tests/test_cli_prompt.py`, 27 tests at first write):
exactly one prompt source, public provider admission, `--conf` iff `omp_conf`,
empty values and mixed `--returns`/`--output`, duplicate singletons, positional
extras, generation flags with `--scaffold`, `--scaffold`-only rerun, and
grammar errors exiting 2 before provider calls or destination creation.

Step 8.2 orchestration REDs: default and exact modes make no inference call;
`--output` maps only through the closed provider pair (ambient providers fail
before a model call); the packaged inference workflow receives typed
task-prompt/output-request inputs and a captured model; captured-bytes-before-
mutation (prompt-file verbatim bytes, snapshot conf root reaching the task
provider); compile-before-provider-start; run id reserved before scaffold
verification with pre-existing root failure; reserved root identity
revalidated inside `run_workflow`; barrier-controlled swaps of every live
scaffold input after verification never reach the compiler or provider;
inference draft parse failure fails without repair/fallback.

Step 8.3 run-seam REDs: `StateManager.new_run_id()` public and format-checked;
`RunWorkflowResult` immutable and structured (exit/run id/run root/outputs/
session/usage); `run_workflow` accepts keyword-only `run_id`; the public `run`
parser exposes no run-id flag; CLI dispatch returns only `result.exit_code`.

Inference workflow tests added to `tests/test_prompt_contract.py`
(+54 lines): the packaged `infer-output-contract.orc` declares the two typed
`String` inputs (`task_prompt`, `output_request`) and passes them through the
existing typed provider-input surface; the inference workflow returns only the
typed `OutputContractDraft`.

### Behavioral fix RED discovered during the smoke

The fake-OMP CLI smoke failed with `contract_violation` /
`missing_bundle_file` for the task step's compiled output bundle: the OMP
confined child never receives `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` (the positive
child environment is a closed, tested contract), and the assistant text is the
authoritative structured output per the X3 design. RED
`test_task_run_materializes_output_bundle_from_transport_text` (fake child
writes no bundle, transport text is one JSON value) failed with `assert 1 == 0`
(step exit 2) before the fix and passes after.

## GREEN evidence (brief selectors)

```sh
python -m pytest -q tests/test_cli_prompt.py tests/test_prompt_contract.py
# 65 passed in ~2s

python -m pytest -q tests/test_cli_prompt.py tests/test_cli_run_ref_root.py \
  tests/test_cli_safety.py tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py
# 196 passed in ~5s

python -m pytest --collect-only -q tests/test_cli_prompt.py
# 28 tests collected
```

Narrow regressions for the shared `run.py`/`state.py`/`workflow/executor.py`
edits and the `.exit_code` cutover:

```sh
python -m pytest -q tests/test_cli_run_ref_root.py tests/test_cli_safety.py \
  tests/test_monitor_cli.py tests/test_runtime_failure_persistence.py \
  tests/test_runtime_observability_cli.py tests/test_workflow_lisp_wcc_m5.py \
  tests/test_yaml_frontend_retirement.py tests/test_workflow_lisp_cli.py \
  tests/test_workflow_lisp_lsp_cli_parity.py \
  tests/e2e/test_e2e_provider_peer_delivery.py \
  tests/e2e/test_e2e_provider_supervision.py
# 198 passed, 5 skipped

python -m pytest -q tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py \
  tests/test_workflow_lisp_pure_result_replay.py
# 179 passed
```

## Structured-result cutover

Migrated every direct `run_workflow` caller and test assertion from integer
returns to `result.exit_code` (14 test modules), using the compiled-command
references; no `__eq__`/`__int__`/dispatch shim was added. Parametrized tests
whose `command` spans compile/explain (int) and run (`RunWorkflowResult`)
assert `getattr(result, "exit_code", result) == N`.

## fake-OMP CLI smoke (actual CLI, both required modes)

Harness: compiled native launcher (`tests/fixtures/omp/fake_launcher.c`,
`-DOMP_FAKE_SCRIPT=<wrapper>`) whose wrapper imports
`tests/fixtures/omp/fake_omp.py`, replays the CLI stdin, and when no control
line is present synthesizes one whose assistant reply is the JSON document
`"OK"` (the output contract instructs the model to emit exactly one JSON
value). The smoke sitecustomize redirects every staged OMP launch to the
launcher and patches `OmpBinaryPin` to the launcher digest; the launch,
version probe, confinement helper, session journal, adapter frame, and
revalidation all run for real.

```sh
env -i HOME=… PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR=… \
  XDG_CACHE_HOME=… XDG_DATA_HOME=… XDG_STATE_HOME=… XDG_CONFIG_HOME=… \
  PYTHONPATH=$SM/shadow:<worktree> \
  python -m orchestrator prompt run --prompt "Summarize the task list." \
  --provider omp_no_tools
# EXIT=0
# stderr: scaffold: <workspace>/workflows/generated/summarize-the-task-list-<id>
# stdout: empty
# state.json: status completed; step run::run__result completed exit 0,
#   output '"OK"'; workflow_outputs {'__result__': 'OK'}
# bundle .orchestrate/workflow_lisp/entry/<run>/run_run/
#   __write_root__run_run__result__result_bundle.json -> '"OK"'

# same command with --returns '{"mode":"scalar","type":"String"}'
# EXIT=0 with identical step/bundle evidence
```

## Production changes (Task 8 owned)

- `orchestrator/cli/commands/prompt.py` (new, 499 lines): closed grammar,
  capture-before-mutation, closed inference mapping, `_new_reserved_run`
  (public `StateManager.new_run_id()` + exclusive 0700 run-root creation with
  the existing `ScaffoldSnapshotError` conversion), private 0500/0400
  `prompt-inputs` snapshot beneath the reserved root, model interpolation into
  the packaged inference snapshot, and `run_workflow(..., run_id=...)`
  adoption with reserved-root identity revalidation and exact run-id/root
  equality.
- `orchestrator/cli/main.py`, `orchestrator/cli/commands/__init__.py`: `prompt`
  subparser and dispatch.
- `orchestrator/cli/commands/run.py`, `orchestrator/state.py`: minimal
  caller-selected internal `run_id` seam and `RunWorkflowResult`; no run.py
  refactor.
- `orchestrator/omp_assets/infer-output-contract.orc` (authorized ruling): the
  two typed `String` inputs and pass-through to the typed provider-input
  surface.
- `orchestrator/workflow/executor.py` (authorized narrow seam for the smoke):
  workflow-input-bound typed prompt input values flow to provider params
  (authored `provider_params` win); OMP JSON-transport steps whose child wrote
  no output bundle materialize the compiled bundle from the normalized
  assistant text (exactly one JSON value per the output-contract guidance)
  immediately before the ordinary output-contract validation, which remains
  the single enforcement surface. No duplicate compiler/runner/verifier/root
  allocator/parser was added.
- `tests/test_cli_prompt.py` (new, 28 tests) and
  `tests/test_prompt_contract.py` (+54 lines).

## Module size cap

`orchestrator/cli/commands/prompt.py` is 499 lines (<=500). No new sibling
prompt module was needed. Grandfathered legacy modules (`main.py`, `run.py`,
`state.py`) received only the required seam edits.

## Key decisions

- Runtime param injection lives in the ordinary executor's single
  invocation-prep site: Task 7's renderer output and template assertions are
  committed authority, and the Lisp frontend has no param-targeting form.
- The model reaches inference through the rendered snapshot `run.orc`: the
  packaged asset has no `:model`; `prompt.py` inserts it into the snapshot
  copy before compile/run.
- OMP output capture: assistant text is authoritative (X3); the orchestrator
  materializes the compiled bundle from it only when the child wrote no file,
  keeping the ordinary validation as the single enforcement surface.
- Smoke pin redirection patches the staging seam (`stage_private_copy`), not
  just module globals, because `python -m orchestrator.providers.omp_launch`
  re-executes under `__main__`.

## Concerns

- `prompt.py` sits at 499 lines; any prompt-side growth will require a scoped
  sibling split.
- The inference path remains session-less by design (no link publication until
  Task 9).
- The OMP bundle materialization is a shared-executor seam; the coordinator's
  broad suite and the final quality review should confirm it stays isolated to
  OMP JSON-transport steps (non-OMP children write their own bundles and are
  untouched).
- `.tmp/` preserved untouched; no build artifacts were produced.


## Gate fix round (coordinator advisory, amended into the same commit)

The coordinator's pre-gate review found two binding-ordering violations;
both got a failing regression before production, per the TDD contract.

### RED A — rerun must reserve before verifying

`test_rerun_reserves_run_root_before_scaffold_verification`: the rerun path
called `verify_scaffold` before `_new_reserved_run`, contradicting the
binding "allocates and exclusively reserves `<runs-root>/<run-id>` before
scaffold verification". RED: the tracked `verify_scaffold` observed no
reserved run root yet (`assert False ... is_dir()`), and a pre-existing run
root reached verification instead of failing at reservation. Production:
`prompt.py` moves `_new_reserved_run` ahead of `verify_scaffold` in the
rerun branch (reservation conflict now fails closed before verification).

### RED B — reserved identity revalidated at the final pre-initialize point

`test_reserved_root_swapped_after_writer_lock_fails_before_initialize`:
`run.py` revalidated the reserved `(st_dev, st_ino)` before `StateManager`
construction, run-root `mkdir`, and writer-lock acquisition, so a root
swapped after the writer lock went undetected and `StateManager.initialize`
ran (`assert [True] == []` RED). Production: `run.py` moved the revalidation
to after `StateManager(...)`, `run_root.mkdir(...)`, and
`run_writer_lock(...)` — immediately before `StateManager.initialize`
(now keyed on `state_manager.run_root`); the early failure still unwinds the
writer lock via the existing `try/finally`.

### GREEN (fix round)

```sh
python -m pytest -q tests/test_cli_prompt.py::test_rerun_reserves_run_root_before_scaffold_verification   tests/test_cli_prompt.py::test_reserved_root_swapped_after_writer_lock_fails_before_initialize
# 2 passed

python -m pytest -q tests/test_cli_prompt.py tests/test_cli_run_ref_root.py   tests/test_cli_safety.py tests/test_prompt_contract.py tests/test_prompt_scaffold.py
# 197 passed

# migrated callers + workflow-lisp provider e2e + parity + pure replay + e2e
# 377 passed, 5 skipped
```

fake-OMP CLI smoke re-run after the fix: default and exact modes both
EXIT=0, `scaffold:` on stderr only, `workflow_outputs {'__result__': 'OK'}`,
step `run::run__result` completed exit 0.

## Gate fix round 2 (spec/security/quality review findings, same commit)

Base commit `7ae0af76`. All 19 REDs of this round were confirmed failing
before their production fix and green after (TDD).

### Test split (Step 8.1-8.3 modules each <=500 lines)

`tests/test_cli_prompt.py` (481) keeps the Step 8.1 grammar REDs and the
shared fake-runtime harness; Step 8.2 orchestration moved to
`tests/test_cli_prompt_orchestration.py` (453), Step 8.3 run-seam to
`tests/test_cli_prompt_run_seam.py` (319), and the new adversarial
filesystem REDs to `tests/test_cli_prompt_security.py` (500).

### Grammar/CLI corrections

- Long-option abbreviation disabled (`allow_abbrev=False` on the `run`,
  `prompt`, and `prompt run` parsers): `--scaf`, `--ret`, `--provide`,
  `--prompt-f`, `--backup-stat` now fail closed (REDs
  `test_abbreviated_{prompt,run}_long_options_are_rejected`).
- Slug semantics: inline `--prompt` scaffolds are always named
  `prompt-<identity>` (literal slug); `--prompt-file` scaffolds are named
  from the normalized lowercase stem (`My Meeting Notes v2.md` ->
  `my-meeting-notes-v2-<identity>`), never from the prompt's first line;
  rerun reconstructs the exact slug from the scaffold name
  (REDs `test_inline_prompt_slug_is_literal_prompt`,
  `test_prompt_file_slug_is_normalized_lowercase_stem`,
  `test_prompt_file_slug_rerun_reconstructs_identity`).
- `orchestrator/cli/commands/__init__.py` restores `run_workflow` and now
  also exports `RunWorkflowResult` in `__all__`
  (RED `test_commands_package_exports_run_workflow_and_result`).

### Run-seam corrections

- `StateManager.new_run_id()` is a public static generator
  ("generate/allocate", not "reserve"; allocation happens via
  `create_run_root`); `_generate_run_id` delegates; `prompt.py` calls it
  without constructing a `StateManager`.
- `RunWorkflowResult.workflow_outputs`/`usage` are detached and recursively
  frozen on EVERY public construction path: a dataclass `__post_init__`
  applies `_deep_freeze` (any `Mapping` -> read-only mapping proxy, lists ->
  tuples) to the defaults and to caller-supplied values alike, so direct
  construction, the dataclass defaults, and the executor's live source
  mappings all stay immutable and invisible to later mutation
  (REDs `test_run_workflow_result_outputs_and_usage_are_deeply_immutable`
  and `test_run_workflow_result_defaults_and_direct_construction_are_frozen`;
  `_run_result` no longer freezes twice).

### Adversarial filesystem REDs (all fail closed, exit 1, no provider call)

- Bundle fallback: symlink leaf, pre-existing regular leaf, FIFO leaf, and
  symlinked parent each fail the run without following the link or writing
  through it (REDs `test_bundle_fallback_rejects_{symlink_leaf,
  existing_leaf, special_leaf, symlink_parent}`). The planted node is never
  consumed, overwritten, or removed: only a leaf this process created with
  `O_EXCL` is ever unlinked, and only on a write failure
  (`test_bundle_fallback_write_failure_removes_owned_partial`, monkeypatching
  `orchestrator.workflow.executor._write_bundle_fd`).
- Prompt sources admitted through component-wise no-follow walks:
  symlinked/special `--prompt-file`; symlinked conf ancestor and leaf;
  symlinked `workflows` ancestor (no preliminary `mkdir` through the link);
  symlinked `--scaffold`; run-root ancestor swap between reservation and
  prompt-inputs creation (fstat identity check on the no-follow opened
  root) (REDs `test_prompt_file_rejects_{symlink,special_leaf}`,
  `test_conf_root_rejects_symlink_ancestor`,
  `test_generated_root_symlink_ancestor_fails_without_redirected_creation`,
  `test_rerun_rejects_symlinked_scaffold_path`,
  `test_prompt_inputs_creation_rejects_run_root_ancestor_swap`).
- Rerun reserves the run root before ANY live scaffold capture/verification
  (REDs `test_rerun_reserves_run_root_before_capture`,
  `test_rerun_reserves_run_root_before_scaffold_verification`,
  `test_run_id_reserved_before_verification_and_pre_existing_root_fails`).

### Coordinator corrections from the gate review

- **Never unlink planted bundle nodes.** The fallback tracks ownership only
  after a successful `O_EXCL|O_NOFOLLOW` creation; a provider-planted
  leaf (regular, symlink, or FIFO) is left untouched while the run fails
  closed, and only the owned partial is removed on a write failure. REDs
  above assert the planted nodes remain.
- **Early provider-template equality at capture.** `_capture_generation`
  compares the installed registry template to the code-owned
  `omp_templates()[provider]` before any inference or destination creation
  and derives the concrete model from the captured validated template
  (`--model` or template default). Tests that intentionally change the
  template patch both the installed and code-owned tables; a one-sided
  drift fails before any provider call or destination write
  (RED `test_template_drift_rejected_before_provider_execution`), and
  mutating every live template source object after capture cannot alter or
  fail the run (`test_model_derived_from_captured_template_and_late_mutation_inert`).
- `prompt.py` stayed within the 500-line cap via the authorized sibling
  `orchestrator/cli/commands/prompt_io.py`: the no-follow conf admission,
  prompt-inputs root creation with identity check (non-exclusive mkdir
  failures and identity-walk `LaunchFsError`/`OSError` in
  reservation/revalidation now exit 1 with a clean `PromptRunError`, never a
  traceback — RED `test_prompt_inputs_creation_oserror_fails_closed`),
  generated-root creation, the inference snapshot materializer (with the
  exact typed-input marker check), the frozen-payload thaw helper, and the
  `--prompt-file` reader: the parent chain is opened component-wise
  no-follow (`open_dir_no_follow` on the absolute parent) and the leaf is
  read as a regular file against that dirfd, so a symlink or special node at
  ANY position fails closed — RED `test_prompt_file_rejects_symlink_parent`
  (a leaf-only `O_NOFOLLOW` open is not sufficient).

### Rerun manifest strict parse (security re-review)

`_capture_rerun` previously converted only `SafeTreeError` for
`scaffold.json`: malformed UTF-8, malformed JSON, or a valid non-object
(JSON array) escaped as an uncaught traceback instead of a clean exit 1.
Production now decodes/parses strictly and rejects any non-`Mapping`
manifest as `PromptRunError`; the descriptor-safe no-follow read and conf
admission are unchanged. RED
`test_rerun_invalid_scaffold_manifest_fails_closed` (3 parametrized cases:
malformed UTF-8, malformed JSON, non-object) failed pre-fix with the exact
uncaught `UnicodeDecodeError`/`JSONDecodeError`/`AttributeError` and now
asserts exit 1, provider never called, no traceback, clean `prompt run:`
message. A second pass closed the nested shape hole: a valid object whose
`provider` member is a list or null broke the chained `.get` with an
uncaught `AttributeError`; `_capture_rerun` now requires `provider_doc` to
be a `Mapping` before reading `registry_name`/`concrete_model` (same RED,
two further parametrized cases).

### Inference fixture handling

`tests/fixtures/omp/fake_omp.py` is the generic Task-5 fixture and keeps
base behavior (default reply `OK`; plain text is valid outside Task-8
contracts). The Task-8 smoke harness confines the exactly-one-JSON-value
default (`"OK"`) to its `.tmp/smoke8/wrapper/fake_omp_json.py` wrapper,
which injects the quoted default through the fake's control seam before
delegating to the fixture.

### GREEN (fix round 2)

```sh
python -m pytest -q tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py
# 60 passed (incl. the two new fs REDs, the direct-construction RED, and
# the 5-case malformed-manifest/nested-shape rerun RED)

python -m pytest --collect-only -q tests/test_cli_prompt.py
# 14 tests collected

# full focused battery (split modules + brief selectors + fixture/executor/state callers)
python -m pytest -q tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py \
  tests/test_cli_run_ref_root.py tests/test_cli_safety.py tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py tests/test_provider_omp_conf.py tests/test_safe_tree.py \
  tests/test_provider_execution.py tests/test_state_manager.py \
  tests/test_provider_omp_launch.py tests/test_provider_integration.py \
  tests/test_workflow_omp_sessions.py
# 592 passed, 1 skipped

python -m pytest -q tests/test_provider_attempt_allocation.py::test_provider_attempt_site_environment_is_runtime_owned \
  tests/test_provider_integration.py tests/test_workflow_omp_sessions.py \
  tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py
# 75 passed (final round: immutability __post_init__, symlink-parent
# prompt-file, mkdir-OSError fail-closed; base fake fixture unchanged)
```

fake-OMP CLI smoke (compiled `fake_launcher` + `sitecustomize` pin/staging
shadow, clean `env -i` workspace): default and exact
(`--returns '{"mode":"scalar","type":"String"}'`) modes both EXIT=0 with
`scaffold:` on stderr only, empty stdout, `status: completed`,
`workflow_outputs {'__result__': 'OK'}` in `state.json`, and the compiled
bundle at `.orchestrate/workflow_lisp/entry/<run>/run_run/
__write_root__run_run__result__result_bundle.json` containing `"OK"`.

## Gate fix round 3 (final spec/security/quality findings, same commit)

All seven final-round findings fixed test-first: every RED was confirmed
failing against the pre-fix code (or, where the pre-fix path failed for an
unrelated harness reason, the RED targets the exact contract the review
named) and green after the fix.

1. **Capture-only contract mode/payload.** `_Captured` now freezes
   `contract_mode` ∈ {exact, inferred, default, rerun} plus the exact
   `contract_request` payload at capture time; `_resolve_contract` reads
   ONLY the captured dataclass (the `mode` parameter is gone), so any later
   mutation of the parsed CLI mode dict is inert. RED: three variants
   (`test_contract_mode_and_payload_captured_before_mode_mutation`) wrap
   `_capture_generation` and mutate `mode["returns"]`/`mode["output"]`
   after capture — default stays default, exact stays exact, `--output`
   still runs inference; each asserts `authoring.mode` and provider list.
2. **Output-contract strict decode.** `_capture_rerun`'s contract-doc
   except tuple now includes `UnicodeDecodeError` (scaffold.json already
   had it). RED: `test_rerun_invalid_output_contract_fails_closed` writes
   invalid UTF-8 into `output-contract.json` → exit 1, no provider, no
   traceback.
3. **Exact `RunWorkflowResult` carriers.** `run_workflow` initializes
   `session_id = None` / `session_status = "failed"` before the outer try;
   the reserved-root identity-mismatch return and every except handler
   return `_run_result(1|2, state_manager=..., session_id=...,
   session_status=...)`. REDs: identity mismatch (patched
   `directory_identity`) returns the caller run id/root; an exception
   after `open_executor_session` returns `session_id="sess-123"` /
   `session_status="failed"`. Both failed pre-fix (`None` carriers) and
   pass post-fix.
4. **Archive default dest never rebinds the service run id.** The empty
   `--archive-processed` default now uses a separate `archive_run_id =
   run_id or datetime.now()...`; the caller-selected `run_id` is never
   overwritten. RED: `args.archive_processed = " "` (truthy, blank after
   strip — the only path reaching the default-dest branch) keeps the
   caller id; pre-fix the result carried a fresh timestamp instead.
5. **Typed-input → provider-param bridge narrowed to the pinned lane.**
   The bridge in `_execute_composed_provider_with_context` now requires
   `resolved_provider_name == "omp_conf"` AND binding `omp_conf_root` AND
   ref `inputs.omp_conf_root` (authored `provider_params` still win). RED:
   `test_typed_inputs_cannot_bridge_to_provider_params_outside_omp_conf`
   drives the real `WorkflowExecutor` with a hostile `inputs.workspace`
   typed input on a plain provider whose command template references
   `${workspace}` — pre-fix the bridged value is substituted into the
   command; post-fix the placeholder stays unresolved and `/evil/path`
   appears nowhere in command/env.
6. **`run` parser abbreviation.** Removed `allow_abbrev=False` from the
   generic `run` parser only (the `prompt` parsers keep it); deleted
   `test_abbreviated_run_long_options_are_rejected`;
   `test_abbreviated_prompt_long_options_are_rejected` still passes.
7. **Model literal renderer reused for the inference snapshot.**
   `_wfl_string_literal` renamed `wfl_string_literal` in
   `prompt_scaffold_render.py`; `prompt_io._write_inference_snapshot`
   renders `:model "{wfl_string_literal(model)}"` (replacing the
   `json.dumps(model)[1:-1]` hack), requires exactly one code-owned
   typed-input marker, and converts the renderer's `ValueError` into a
   clean `PromptRunError`. REDs (unit, at the materialization barrier):
   control-character model raises `PromptRunError` before any file is
   written; a duplicated marker is refused. The CLI-level control-char RED
   was dropped because pre-fix already exited 1 there via unrelated fake
   harness identity plumbing — the unit RED targets the review's exact
   contract.

### Module size cap (all <=500)

`prompt.py` 470, `prompt_io.py` 192, `prompt_scaffold_render.py` 425,
`test_cli_prompt.py` 493, `test_cli_prompt_orchestration.py` 499,
`test_cli_prompt_run_seam.py` 498, `test_cli_prompt_security.py` 500.
The two orchestration rerun REDs share one `_rerun_fails_closed` helper in
`test_cli_prompt.py`; single-line test docstrings were compacted/dropped
(coordinator-sanctioned) to fit the cap. Grandfathered legacy modules
(run.py, main.py, state.py, workflow/executor.py) untouched by the cap.

### GREEN (fix round 3)

```sh
# all new REDs (9 tests, 15 parametrized cases)
python -m pytest -q \
  tests/test_cli_prompt_orchestration.py::test_contract_mode_and_payload_captured_before_mode_mutation \
  tests/test_cli_prompt_orchestration.py::test_rerun_invalid_output_contract_fails_closed \
  tests/test_cli_prompt_orchestration.py::test_rerun_invalid_scaffold_manifest_fails_closed \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_identity_mismatch_returns_known_run_id_and_root \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_post_session_exception_returns_session_id_and_failed \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_caller_run_id_kept_with_empty_archive_destination \
  tests/test_cli_prompt_run_seam.py::test_typed_inputs_cannot_bridge_to_provider_params_outside_omp_conf \
  tests/test_cli_prompt_run_seam.py::test_inference_snapshot_rejects_control_character_model \
  tests/test_cli_prompt_run_seam.py::test_inference_snapshot_requires_exactly_one_marker
# 15 passed

# split suite + coordinator-mandated extra
python -m pytest -q tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py \
  tests/test_provider_attempt_allocation.py::test_provider_attempt_site_environment_is_runtime_owned
# 70 passed

# affected neighbors (executor bridge, run callers, parser, prompt injection)
python -m pytest -q tests/test_workflow_omp_sessions.py tests/test_cli_run_ref_root.py \
  tests/test_cli_safety.py tests/test_prompt_contract_injection.py
# 151 passed
```

fake-OMP CLI smoke (compiled `fake_launcher` + `sitecustomize` pin/staging
shadow, clean `env -i` workspace, per-mode caches): default and exact
(`--returns '{"mode":"scalar","type":"String"}'`) modes both EXIT=0 with
`scaffold:` on stderr only, `status: completed`, step output `"OK"`, and
the compiled bundle at `.orchestrate/workflow_lisp/entry/<run>/run_run/
__write_root__run_run__result__result_bundle.json` containing `"OK"`.

## Gate fix round 4 (final correctness holes at `9806b1cc`, same commit)

1. **Control-character model fails closed at capture for every mode.**
   `_capture_generation` now validates the concrete model with the shared
   `wfl_string_literal` renderer and converts the renderer `ValueError` to
   `PromptRunError` before any inference or destination creation — default
   and exact modes previously reached `generate_scaffold`, where the
   Task-7 renderer's `ValueError` escaped as a traceback. RED:
   `test_control_character_model_rejected_before_destination`
   (parametrized default + exact): `--model "bad\x01model"` → exit 1, no
   provider, no traceback, no `.orchestrate` and no
   `workflows/generated` destination. Pre-fix: both cases failed with a
   raw `ValueError` traceback and a created run root.
2. **Session-carrier invariant.** `run_workflow` initializes
   `session_status` to `None` (pre-open failures now return
   `session_id=None` / `session_status=None`, never `"failed"`), sets it
   to `"failed"` immediately after `open_executor_session` succeeds, and
   the archive step marks the session failed before re-raising. The
   finally-close is wrapped: any close failure — including after a
   successful executor result — returns that `session_id` with
   `session_status="failed"`, never stale `"completed"`; every except
   handler returns `"failed" if session_id is not None else None`. The
   inner close still only runs when the id exists and always receives a
   string status. REDs: the identity-mismatch test now also asserts
   `session_id is None` / `session_status is None` (pre-fix returned
   `"failed"`); new
   `test_run_workflow_close_failure_after_success_returns_failed_session`
   (patched `close_executor_session` raising after a `completed`
   executor result → exit 1, `session_id="sess-123"`,
   `session_status="failed"`; pre-fix the close exception escaped
   `run_workflow`).

### GREEN (fix round 4)

```sh
# all RED tests incl. the two new ones (parametrized)
python -m pytest -q tests/test_cli_prompt_run_seam.py::test_run_workflow_identity_mismatch_returns_known_run_id_and_root \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_post_session_exception_returns_session_id_and_failed \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_caller_run_id_kept_with_empty_archive_destination \
  tests/test_cli_prompt_run_seam.py::test_run_workflow_close_failure_after_success_returns_failed_session \
  tests/test_cli_prompt_run_seam.py::test_control_character_model_rejected_before_destination \
  tests/test_cli_prompt_run_seam.py::test_typed_inputs_cannot_bridge_to_provider_params_outside_omp_conf \
  tests/test_cli_prompt_run_seam.py::test_inference_snapshot_rejects_control_character_model \
  tests/test_cli_prompt_run_seam.py::test_inference_snapshot_requires_exactly_one_marker \
  tests/test_cli_prompt_orchestration.py
# 33 passed

# pre-fix verification (git show HEAD run.py/prompt.py): identity status
# "failed" instead of None, close failure escaped run_workflow, control-char
# model ValueError traceback — 4 failed as expected

python -m pytest -q tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py \
  tests/test_provider_attempt_allocation.py::test_provider_attempt_site_environment_is_runtime_owned \
  tests/test_workflow_omp_sessions.py tests/test_cli_run_ref_root.py \
  tests/test_cli_safety.py tests/test_prompt_contract_injection.py
# 224 passed
```

fake-OMP CLI smoke (per-mode caches): default and exact modes both EXIT=0,
`status: completed`, step output `"OK"`, compiled bundle
`"OK"` at `.orchestrate/workflow_lisp/entry/<run>/run_run/
__write_root__run_run__result__result_bundle.json`.

Module caps re-checked: `prompt.py` 477, `prompt_io.py` 192,
`prompt_scaffold_render.py` 425, `test_cli_prompt.py` 493,
`test_cli_prompt_orchestration.py` 499, `test_cli_prompt_run_seam.py` 500,
`test_cli_prompt_security.py` 500.

## Gate fix round 5 (finally-close re-raise, same commit)

The close-failure handler no longer returns from the inner `finally` (a
`return` there suppressed an active body exception and bypassed the outer
`fail_run`, leaving the persisted run completed). On a close exception it
logs, sets `session_status = "failed"`, and re-raises so the outer handler
persists `fail_run` and returns the exact failed result — whether or not
the body itself raised. The inner close still only runs when the session
id exists and always receives a string status.

REDs (both verified failing at `854b98d0` and green after):
- `test_run_workflow_close_failure_after_success_returns_failed_session`
  extended: after a `completed` executor result plus a raising close,
  assert exit 1 / `session_id="sess-123"` / `session_status="failed"` AND
  the persisted `state.json` run status is `failed` (pre-fix the run
  remained `completed`).
- `test_run_workflow_body_and_close_exception_persists_failed_run`
  (body exception + close exception): outer handling is not bypassed —
  exit 1 / `session_id="sess-123"` / `session_status="failed"` and the
  persisted run status is `failed` (pre-fix the run stayed `running`,
  `fail_run` never ran).

```sh
python -m pytest -q <run-seam session REDs, incl. the two above>
# 4 passed (post-fix); pre-fix: 2 failed (persisted completed / running)

python -m pytest -q tests/test_cli_prompt.py tests/test_cli_prompt_orchestration.py \
  tests/test_cli_prompt_run_seam.py tests/test_cli_prompt_security.py \
  tests/test_provider_attempt_allocation.py::test_provider_attempt_site_environment_is_runtime_owned \
  tests/test_workflow_omp_sessions.py tests/test_cli_run_ref_root.py \
  tests/test_cli_safety.py tests/test_prompt_contract_injection.py
# 225 passed
```

fake-OMP CLI smoke: default and exact both EXIT=0, bundle `"OK"`.
Module caps re-checked: `test_cli_prompt_run_seam.py` 495 (was 500).

## Gate fix round 6 (trial-module-free stub cutover, same commit)

`tests/test_cli_trial.py::test_ordinary_cli_import_parse_and_dispatch_stay_trial_module_free`
monkeypatched `cli_main.run_workflow = lambda _args: 0`; the ordinary
`run` dispatch now reads `result.exit_code`, so the subprocess raised
`AttributeError`. The embedded stub now imports the ordinary run module
via `importlib` (no trial modules become eager) and returns
`run_module.RunWorkflowResult(exit_code=0)`, preserving the test's
module-loading contract.

```sh
python -m pytest -q tests/test_cli_trial.py::test_ordinary_cli_import_parse_and_dispatch_stay_trial_module_free
# green (pre-fix: AttributeError 'int' object has no attribute 'exit_code')

python -m pytest -q tests/test_cli_trial.py
# 18 passed
```
