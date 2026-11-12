# Roadmap Phase 1: The First Hour And The Long Run Plan

**Status: Plan.** Implements Phase 1 of the
[current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-1-the-first-hour-and-the-long-run).
This page owns the order of work, the tests and the gates of the phase.
Behavior is owned elsewhere: command-line behavior by the
[CLI contract](../../specs/cli.md), the language by the
[frontend specification](../design/workflow_lisp_frontend_specification.md),
resume and invalidation by
[evaluated execution](../design/workflow_lisp_evaluated_execution.md). Do not
copy examples from this page; the tutorial that Task 9 creates is the copyable
one. Until the tasks land, authors use the
[drafting guide](../lisp_workflow_drafting_guide.md) as it is.

**Goal:** a new author gets from an empty directory to a resumed run in an
hour, and someone watching a long run can see where it is, why it failed and
which command continues it.

**Headline exit test:** a failed run is diagnosed and resumed using only what
the terminal printed, in a fresh environment outside this checkout
([one automated test](#headline-exit-test)).

**Architecture:** each item reuses a channel that already exists. The language
fixes use the elaborator's own let-binding helper and the required-lint
registry, whose warnings already travel on `compile_diagnostics` (today only
`py` prints them). Terminal output is a view of the memo: every `started`,
`committed` and `failed` row passes through `append_record`, so one reporter
carried by `RunAuthority` receives each row there, and refusals reach the same
reporter through one `on_error` callback. Default manifests and hidden
commands are applied once in `main()` after parsing, so every subcommand and
the resume recipe see ordinary explicit values.

**What this makes harder later:** the terminal lines become a specified
contract; a file named `commands.json` beside a source is picked up without
being named; `RunAuthority` carries one field that is not authority.

## Global constraints

- No provider or model call in any task. The authoring check is the only
  spend, runs only after the owner approves its budget, and is launched by the
  coordinator.
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12. `elaborate.py`, `compiler.py`, `runtime.py`,
  `effect_inputs.py` and `cli/main.py` are already over 500 lines: add only the
  few lines each task names and put new logic in the new modules.
- Tests assert behavior (exit codes, printed lines, which attempts ran, the
  value returned). No test asserts literal prompt text. No mocks: drive the
  CLI in a subprocess or call the public function on real files in `tmp_path`.
- Every `pytest` and CLI invocation sets `PYTHONPATH` to the worktree under
  test (the editable install points at another checkout). Run the task's
  narrow selectors first. A broad run uses
  `pytest -q -n 16 --dist=worksteal --basetemp=/tmp/p1` in tmux, after
  `df -h`, and is compared with the Phase 0 failing-id list.
- Work in a worktree on a branch cut from `main` after
  `chore/prune-low-value-tests` has merged. Commit with a pathspec
  (`git commit -m ... -- <paths>`), one commit per checkbox group, no
  assistant attribution.
- Runtime, frontend and CLI changes each carry an end-to-end check; the tasks
  name it.
- Messages keep their first line (`[code] detail`) byte for byte. New text is
  appended as further lines, so existing assertions on codes keep passing.

## State of the code, re-verified 2026-11-11

Probes ran against `main` in a scratch directory with command-only workflows
and a local stand-in provider script.

| Item | Today |
| --- | --- |
| (a) effect given to `continue` | `(continue (command-result ...))` and `(continue (some-proc ...))` crash with `compiler_defect` (`unsupported WCC elaboration node: CommandResultExpr` / `ProcedureCallExpr`). An effect inside arithmetic, `if`, `let*`, a `loop-state :like` field, or given to `done` compiles |
| (b) missing `:on-exhausted` | Compiles silently; fails at run time with `loop_exhausted`. A warning channel exists: `REQUIRED_LINT_REGISTRY` severities `warn`/`error`, carried on `ClosedProgramBuildResult.compile_diagnostics`; `py build/check/run` print them, `compile` and `run` drop them |
| (c) output | `run` prints nothing on success and one log line on failure, with no run id, step or stderr. `resume` rejects `--quiet`, although the CLI contract says it accepts it. Help calls the program `orchestrate`; the installed script is `orchestrator` |
| (d) refusals | `resume_program_changed`, `resume_inputs_changed`, `effect_input_diverged` and `invalidate_not_committed` name no recovery; the last prints only the identity |
| (e) manifests and help | Flags are `--command-boundaries-file`, `--provider-externs-file`, `--prompt-externs-file`; no defaults. `--help` lists 20 subcommands, 10 of them maintainer or retired |
| (f) import cost | `jsonschema` is imported at module level in four `orchestrator/providers/isolation*.py` files (four validator constructions inside functions, three annotation-only uses of `ValidationError`). `--help` 2.4 s, `compile` 3.0 s; with the slow import blocked 0.4 s and 1.1 s (machine load 45) |
| (g) prompt edit and continue | Works today when prompts are files bound through the prompt manifest (`asset_file`): see Task 7 |
| (h) outside the checkout | A non-editable install into a new virtual environment ran a command pipeline in an empty directory with `PYTHONPATH` unset |

## Order and lanes

| Lane | Tasks, in order | Shared files that force the order |
| --- | --- | --- |
| Language | 1, 2 (may run in parallel) | none between them |
| CLI | 4, 5, 6, 8 | `cli/commands/evaluated.py`, `cli/main.py`, `specs/cli.md` |
| Free | 3, 7, 10, from the start | none |
| Close | 9, after 1, 2, 4, 5 and 6 | uses all of them |

One implementer per lane, one worktree per lane. Task 4's last step needs
Task 2; if Task 2 has not merged, do that step after rebasing on it. Every
existing test module named below survives the prune branch (checked against
its tip); the new tests live in new modules, so the two do not collide. Sizes:
S is up to one day, M two to three days. Total about fifteen days.

## Tasks

### Task 1: an effect given directly to `continue` (S)

**Files:** modify `orchestrator/workflow_lisp/wcc/elaborate.py`
(`_bind_effectful_loop_state_fields`) and
`orchestrator/workflow_lisp/stdlib_modules/std/improve.orc` (stale comment);
test `tests/test_workflow_lisp_prefix_scope.py`.

**Interface:** the helper keeps its signature and gains one case. When the
state expression is not a `LoopStateUpdateExpr`, contains an effect, and is
not a `LetStarExpr` or `IfExpr`, return
`(let* ((g <state>)) (continue g))`, with `g` from
`fresh_name(_generated_effect_binding_name_from_scope(naming_scope, role="state"), reserved)`.
A scratch prototype of exactly this compiled both crashing shapes and left the
program digests of the shapes that compile today unchanged. Binding every
effectful state instead moved the digests of the `if` and `let*` shapes, which
would refuse resume of retained runs, so keep the case narrow.

- [ ] Add `test_an_effect_given_directly_to_continue_runs_as_the_let_bound_form`,
      parametrized over a direct command, a direct procedure call and the
      let-bound form, in the style of `TWO_ARMS_FORMS`: all three return the
      same value and the same probe logs.
- [ ] Add `test_resume_after_a_commit_inside_direct_continue_never_repeats_it`
      with `_assert_committed_prefix_resume`.
- [ ] Run both; the direct forms fail with `compiler_defect`.
- [ ] Implement the case. Run the module and
      `tests/test_workflow_evaluated_loops.py`.
- [ ] Check by hand: compile one workflow each with `(continue (+ 1 <effect>))`,
      `(continue (if c <effect> 5))` and `(continue (let* ((x <effect>)) x))`
      before and after; the three program digests are equal.
- [ ] Delete the comment in `std/improve.orc` that says the frontend cannot
      lower these forms. If a test pins that file's bytes, leave it and note
      it in the ledger. Commit.

### Task 2: warn on a loop without `:on-exhausted` (M)

**Files:** modify `orchestrator/workflow_lisp/lints.py` (registry entry),
`orchestrator/workflow_lisp/compiler.py`
(`_collect_stage3_required_lint_diagnostics` and its one call site),
`orchestrator/cli/commands/compile.py`,
`docs/design/workflow_lisp_frontend_specification.md` (the `loop/recur`
section and the required-lint list), `docs/lisp_workflow_drafting_guide.md`;
create `tests/test_workflow_lisp_loop_exhaustion_warning.py`.

**Interface:** lint code `loop_missing_on_exhausted`, `default_severity="warn"`,
`strict_severity="error"`, emitted once per `LoopRecurExpr` whose
`on_exhausted_result_expr` is `None`, found with `walk_expr` over the typed
body of every workflow and every procedure of the module (the collector gains
a `typed_procedures` parameter; a prototype that walked workflows only missed
a loop inside a `defproc`). `compile` prints each entry of
`closed_result.compile_diagnostics` with `logger.warning(render_diagnostic(d))`
and still exits 0 with its JSON on stdout; `--diagnostics-json` output is
unchanged.

**The error half** is not built here: see
[Deviations](#deviations-from-the-roadmap), item 1.

**What it touches:** nothing has to migrate for a warning. Forms that omit
`:on-exhausted` today: 26 in 26 test `.orc` files (13 at an admitted target,
13 at retired targets), 28 in 14 test modules, 4 in 3 current documents, 9 in
8 historical plans and reports, 27 in 3 frozen experiment task files. This
task edits only the 3 forms in the frontend specification and the drafting
guide.

- [ ] Tests: `test_loop_without_on_exhausted_compiles_with_one_located_warning`
      (one diagnostic, that code, the loop's line);
      `test_loop_inside_a_procedure_is_warned_too`;
      `test_loop_with_on_exhausted_has_no_warning`;
      `test_compile_command_prints_the_warning_and_exits_zero` (subprocess).
- [ ] Run; all but the third fail.
- [ ] Implement. Run the new module, `tests/test_workflow_lisp_loop_recur.py`,
      `tests/test_workflow_lisp_diagnostics.py`,
      `tests/test_workflow_lisp_compile_diagnostics.py` and
      `tests/test_workflow_lisp_lsp_cli_parity.py`. If a test expected no
      diagnostics from a fixture that omits `:on-exhausted`, add the keyword
      to the fixture; do not relax the assertion.
- [ ] Documents: state the rule and the code in the frontend specification;
      add `:on-exhausted` to its example and to the two in the drafting guide;
      add a short author-facing paragraph to the guide (what the keyword
      returns, that the loop binder is in scope, what happens without it).
      Commit.

### Task 3: lazy `jsonschema` import (S)

**Files:** modify `orchestrator/providers/isolation.py`,
`isolation_bundle_broker.py`, `isolation_environment.py`,
`isolation_network_preflight.py`; create `tests/test_cli_import_cost.py`.

Move each `Draft202012Validator` import into the function that constructs it;
in `isolation.py` import `ValidationError` under `TYPE_CHECKING` (the module
already has postponed annotations).

- [ ] Tests, each in a subprocess: `test_cli_help_does_not_import_jsonschema`
      (import `orchestrator.cli.main`, assert the module is absent from
      `sys.modules`);
      `test_compiling_a_command_workflow_does_not_import_jsonschema`.
- [ ] Run; both fail. Implement. Run them and
      `tests/test_provider_isolation_schema_resources.py`.
- [ ] Record in the ledger the median of five runs of `--help` and of
      `compile` on a command workflow, before and after, with the load
      average. Target on an idle machine: `--help` at most 0.5 s, `compile`
      at most 1.5 s. Time is not asserted in a test. Commit.

### Task 4: the run says what it is doing (M)

**Files:** create `orchestrator/cli/progress.py`,
`tests/test_cli_run_output.py`; modify
`orchestrator/workflow/evaluated/authority.py`,
`orchestrator/workflow/evaluated/memo.py`,
`orchestrator/cli/commands/evaluated.py`, `run.py`, `resume.py`,
`orchestrator/cli/main.py`.

**Interfaces:**

```python
# orchestrator/workflow/evaluated/authority.py, on RunAuthority
observer: Callable[[Mapping[str, Any]], None] | None = field(default=None, compare=False, repr=False)

# orchestrator/workflow/evaluated/memo.py, in append_record after publish_evaluated_view
if checked_authority.observer is not None:
    checked_authority.observer(entry.data)

# orchestrator/cli/progress.py
def launcher() -> str   # "orchestrator", or "python -m orchestrator" when run as a module
class TerminalReporter:
    def __init__(self, run_id: str, run_root: Path, *, quiet: bool, state_dir: str | None,
                 err: TextIO = sys.stderr, out: TextIO = sys.stdout) -> None: ...
    def announce(self) -> None: ...                      # the run line
    def record(self, row: Mapping[str, Any]) -> None: ...  # the observer
    def run_failed(self) -> None: ...                    # the resume line
    def result(self, value: Any) -> None: ...            # compact sorted-key JSON, one line
```

`run_evaluated_workflow` and `resume_evaluated_workflow` build the reporter,
attach it with `dataclasses.replace(authority, observer=reporter.record)`, and
call `announce`, then `result` or `run_failed`. The reporter reads only
`run_root/<attempt directory>/stderr.txt`, found from the `result_path` of the
`started` row it saw for that identity. A write error on the terminal turns
the reporter off; it never fails the run.

**Lines.** Progress goes to stderr, the result to stdout.

```text
run     <run id>  <run root>
start   <identity>  attempt <n>
commit  <identity>  attempt <n>
failed  <identity>  attempt <n>  [<code>]
        stderr: <path>
        | <last ten lines of that file>
waiting <identity>  <launcher> input get <run id>
resume  <launcher> resume <run id> [--state-dir DIR]
```

- `--quiet` drops the `run`, `start` and `commit` lines. The failure block,
  the `resume` line and the result are always printed.
- The result is the terminal value itself, not the `{"__result__": ...}`
  wrapper. A suspended run prints `waiting` and no result.
- `resume` prints the same lines; effects reused from the memo print nothing.
  `resume` gains `--quiet`, which the contract already documents.
- `run --dry-run` prints one stderr line with the entry workflow and the
  number of effect sites.
- Provider output streaming is unchanged: `--quiet` still suppresses it,
  `--stream-output` stays an accepted no-op, and `--verbose` and `--log-level`
  affect logging only.
- Outside `--debug`, `run` logs with the plain format `resume` already has, so
  the existing `[code] message` line carries no timestamp prefix. Set
  `prog="orchestrator"` so usage matches the installed script.

- [ ] Tests on a three-command pipeline, each in a subprocess:
      `test_run_prints_run_id_first_then_each_effect_and_the_result` (first
      stderr line names a directory that exists under the runs root; three
      `start` and three `commit` lines in order; last stdout line parses to
      the expected value);
      `test_failed_run_prints_the_step_its_stderr_and_the_resume_command`
      (exit 1; identity of the failing step; a string the command wrote to
      stderr; a `resume` line containing the run id; empty stdout);
      `test_quiet_run_prints_only_the_result`;
      `test_resume_prints_only_the_effects_it_runs_and_the_result`;
      `test_resume_accepts_quiet`;
      `test_dry_run_reports_what_it_checked`;
      `test_suspended_run_prints_the_input_command_and_no_result` (host-input
      helpers in `tests/workflow_evaluated_host_input_helpers.py`).
- [ ] Run; all fail. Implement.
- [ ] Run `tests/test_workflow_evaluated_cli.py`,
      `tests/test_workflow_lisp_cli.py`, `tests/test_workflow_python_cli.py`,
      `tests/test_workflow_evaluated_views.py`,
      `tests/test_workflow_evaluated_repl.py` and
      `tests/test_workflow_evaluated_invalidate_smoke.py`. Tests that asserted
      empty output from `run` or `resume` now assert the new lines.
- [ ] After Task 2: `run` shows compile warnings through the existing
      `_show_run_compile_warnings`; add
      `test_run_shows_compile_warnings_unless_quiet`. Commit.

### Task 5: every refusal names what changed and what to run (M)

**Files:** create `orchestrator/cli/recovery.py`,
`tests/test_cli_recovery_messages.py`; modify
`orchestrator/cli/progress.py` (`TerminalReporter.error`),
`orchestrator/cli/commands/evaluated.py`, `invalidate.py`,
`orchestrator/workflow/evaluated/runtime.py`, `effect_inputs.py`, `memo.py`.

**Interfaces:**

```python
# runtime.py: both entry points gain
on_error: Callable[[Exception], None] | None = None
# called once, after the existing logger.error, with every exception the
# function turns into exit 1 or 2; execute_pure_resume passes it on.

# orchestrator/cli/recovery.py
REFUSAL_CODES: tuple[str, ...]
def recovery_lines(exc: Exception, *, run_id: str, launcher: str, state_dir: str | None,
                   header: Mapping[str, Any] | None = None,
                   stored_program: ClosedProgram | None = None) -> list[str]: ...
def run_command(header: Mapping[str, Any], *, launcher: str, state_dir: str | None) -> str: ...
```

Exceptions gain attributes and keep their text: `_EffectInputDiverged` gets
`identity`, `changed_parts`, `changed_files`, `retry`; the
`resume_program_changed` refusal gets `fresh_program`; `resume_inputs_changed`
gets `changed_inputs`; `invalidate_not_committed` gets `committed` (the active
committed identities) and `pending`. `run_command` rebuilds a fresh `run`
command from the header's `workflow_file` and `resume_request`.

| Code | Names | Prints |
| --- | --- | --- |
| `resume_program_changed` | effect sites added, removed or changed, by identity (`site_nodes` of stored and fresh program, provenance stripped); or that only code between effects changed | restore the source and resume; or the fresh `run` command, saying that every step runs again |
| `resume_inputs_changed` | the input names whose value differs | restore them and resume; or the fresh `run` command |
| `effect_input_diverged`, committed step | identity, changed parts, changed files | `invalidate <run> '<identity>'` then `resume <run>`; says that this step and all later ones run again and that workspace files are not rolled back |
| `effect_input_diverged`, failed step retried | identity, changed files | restore those files and resume; otherwise the fresh `run` command. Says plainly that a failed step cannot yet be retried with a changed script in the same run |
| `invalidate_not_committed` | whether the step is pending or failed; the committed identities | `resume <run>` for a pending step; otherwise the list to choose from |
| `invalidate_coordinator_committed` | the committed run reference or agent turn in the suffix | the fresh `run` command |
| `resume_result_root_changed`, `resume_run_ref_root_changed` | the recorded and the current value | the flag and value that match the run |
| `evaluated_execution_unavailable`, `resume_request_missing`, `lexical_restore_pending_effect_unsafe` | the reason in one sentence | the fresh `run` command where a recipe exists |

Codes outside the table keep today's text and get one line pointing to the
diagnostics table of the CLI contract.

- [ ] Tests, in subprocesses on the three-command pipeline:
      `test_program_edit_refusal_names_the_changed_step_and_a_run_command_that_works`;
      `test_committed_script_edit_refusal_prints_invalidate_and_resume_that_recover`
      (the test runs the two printed commands verbatim; exit 0; that step has
      a second attempt);
      `test_failed_step_script_edit_refusal_names_the_file_and_a_run_command_that_works`;
      `test_input_change_refusal_names_the_input`;
      `test_invalidate_of_an_unknown_identity_lists_the_committed_ones`;
      and in process `test_every_refusal_code_has_recovery_lines` over
      `REFUSAL_CODES`.
- [ ] Run; all fail. Implement. Run the new module,
      `tests/test_workflow_evaluated_invalidate.py`,
      `tests/test_workflow_evaluated_resume.py` and
      `tests/test_workflow_evaluated_resume_replay_boundary.py`. Commit.

### Task 6: default manifests, public help (S)

**Files:** create `orchestrator/cli/defaults.py`,
`tests/test_cli_defaults_and_help.py`; modify `orchestrator/cli/main.py`,
`orchestrator/workflow_lisp/typecheck_effects.py` (one message),
`docs/python_workflow_drafting_guide.md` (the sentence that says there are no
defaults).

**Interface:**

```python
# orchestrator/cli/defaults.py
MANIFEST_DEFAULTS = {"command_boundaries_file": "commands.json",
                     "provider_externs_file": "providers.json",
                     "prompt_externs_file": "prompts.json"}
def apply_manifest_defaults(args: argparse.Namespace) -> list[str]:
    """Fill each absent manifest flag from the file of that name beside args.workflow; return the files used."""
```

`main()` calls it once after parsing, for any command that has a `workflow`
and these attributes (`run`, `compile`, `repl`, `py build/check/run`), and
prints `using <file> beside <source>` on stderr unless `--quiet`. An explicit
flag wins. The path lands in the resume recipe like an explicit flag; `resume`
never looks for defaults.

Hidden from `--help` and still accepted: subcommands `prompt`, `trial`,
`explain`, `workflow-lisp-route-readiness`, the four `peer-*`,
`provider-materialization-submit`, `provider-isolation-environment-manifest`
(no `help=`, and a `metavar` listing the ten public commands); on `run` and
`resume` the flags the contract says evaluated execution does not read
(`--context*`, `--clean-processed`, `--archive-processed`, `--on-error`,
`--max-retries`, `--retry-delay`, `--step-summaries`, `--summary-*`,
`--live-agent-*`, `--backup-state`, `--repair`, `--force-restart`,
`--stream-output`); on `compile` the six `--emit-*` flags
(`help=argparse.SUPPRESS`).

- [ ] Tests: `test_manifests_beside_the_source_are_used_when_flags_are_absent`;
      `test_an_explicit_flag_wins_over_the_sibling_file`;
      `test_resume_uses_the_manifest_recorded_by_run`;
      `test_py_build_uses_sibling_manifests`;
      `test_missing_command_boundary_message_names_the_file_and_the_flag`;
      `test_top_level_help_lists_only_public_commands`;
      `test_hidden_commands_and_flags_still_parse`.
- [ ] Run; all fail. Implement; the `command_adapter_missing_contract` message
      gains a second sentence naming `commands.json` and the flag. Run the new
      module and `tests/test_workflow_lisp_cli.py`. Commit.

### Task 7: prompt edit and continue, documented and pinned (S)

**Finding.** With three provider steps whose prompts are files bound by the
prompt manifest (`{"prompts.two": {"asset_file": "two.md"}}`):

- editing the prompt file of a step that failed, then `resume`, runs that step
  again with the new prompt, with no refusal;
- editing the prompt file of a committed step refuses resume with
  `effect_input_diverged` naming `source:asset_file:two.md`; after
  `invalidate <run> '<identity>'`, `resume` runs that step and every later one
  and reuses the earlier ones;
- editing an inline `defprompt` string refuses with `resume_program_changed`.

So prompt edit and continue exists today for prompts kept in files, at the
cost of one `invalidate`. It does not roll back workspace files, and a
committed agent turn or run reference in the cancelled suffix refuses.

**Files:** modify `docs/runtime_execution_lifecycle.md` (new section "Edit a
prompt and continue"); create
`tests/test_workflow_evaluated_prompt_edit_continue.py`, reusing the provider
stand-in pattern of `tests/test_workflow_evaluated_providers.py`.

- [ ] Tests, asserting attempts and exit codes, never prompt text:
      `test_editing_the_prompt_file_of_a_failed_step_resumes_with_a_new_attempt`
      (earlier steps keep one attempt; the two `prompt.txt` files of the
      retried step differ);
      `test_editing_a_committed_prompt_file_refuses_then_invalidate_reruns_the_suffix`;
      `test_editing_an_inline_prompt_refuses_as_a_program_change`.
- [ ] Run. These pin existing behavior and should pass at once; if one fails,
      stop and report, because the document would be wrong.
- [ ] Write the section: the file convention, the two cases with their
      commands, the limits above. Commit.

### Task 8: CLI contract edit (S)

**Files:** modify `specs/cli.md` only, in one commit, after Tasks 4 to 6.
Another session has uncommitted edits in the REPL section of this file in the
main checkout; work from the committed file in the lane worktree and do not
touch that section.

- [ ] "Evaluated execution", `run` and `resume` entries: the line grammar of
      Task 4, which stream each line uses, what `--quiet` drops, the result
      line, the `--dry-run` line, the `waiting` line.
- [ ] Same section, frontend flags: the default-manifest rule of Task 6 and
      that `compile` and `run` print compile warnings on stderr.
- [ ] "Diagnostics": refusals keep their first line; recovery lines follow;
      the table of Task 5 by code.
- [ ] "Commands and Examples" and the global option list: the program name is
      `orchestrator`; hidden commands and flags stay accepted.
- [ ] Run the tests that read `specs/cli.md` (`grep -l "specs/cli.md" tests`).
      Commit.

### Task 9: tutorial, its smoke test and the exit test (M)

**Files:** create `docs/tutorial_first_pipeline.md` and
`tests/test_first_hour_e2e.py`; modify `README.md` ("Try it" points to the
tutorial). The coordinator adds the `docs/index.md` row.

**Tutorial.** About 150 lines, status "current guide", written for an empty
directory and an installed package, not for the repository root, and it says
so. It teaches `.orc` (see Deviations, item 7). Content, in order: install;
an existing script (`count_words.sh`); the short wrapper that runs it and
writes its output as JSON to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; `commands.json`
and what a closure is; `grow.orc` with a record result, a loop with
`:on-exhausted` and `(continue (command-result ...))`; `compile`; a `run` that
fails because the input file is missing, with the output explained; creating
the file and running the printed `resume`; editing `pad.py` and following the
printed `invalidate` and `resume`; where to go next (providers and prompts,
the Python frontend, prompt edit and continue). It states that fixing the
script of a step that failed needs a new run for now. A scratch version of
this pipeline already runs on today's CLI: 33 lines in five files.

**Machine-readable blocks.** An HTML comment before a fenced block marks it:
`<!-- file: NAME -->` writes the block to `NAME`; `<!-- run -->` runs the
block and expects exit 0; `<!-- run: exit 1 -->` expects that code;
`<!-- run: printed resume -->` runs the command the previous step printed on
its `resume` line, and the block shows it with `<run id>`.

**Environment fixture** (module scope, no network): copy `orchestrator/`,
`pyproject.toml` and `LICENSE.md` to a temporary directory (so the build
leaves nothing in the worktree); `python -m venv --system-site-packages`;
`pip install --no-index --no-deps --no-build-isolation <copy>`. Commands run
with the environment's `bin` first on `PATH`, `PYTHONPATH` removed, in a new
empty directory, with a 120 s timeout each. The fixture asserts that
`orchestrator.__file__` is inside the environment. A failure to build the
environment fails the test; it does not skip. Measured cost: about 9 s to
build, 30 to 40 s for both tests under load. Both tests stay in the default
suite.

- [ ] `test_tutorial_blocks_run_as_written`: extract the marked blocks and
      execute them in order; every step meets its declared exit code and the
      last stdout line of the final step is the value the tutorial shows.
- [ ] `test_failed_run_is_diagnosed_and_resumed_from_terminal_output`: the
      [headline exit test](#headline-exit-test).
- [ ] Run; both fail (no tutorial; no run id or resume line). Write the
      tutorial. Run `pytest --collect-only` on the module, then the module.
- [ ] Commit. Record in the ledger one manual check of
      `pip install git+<repository URL>` in a clean environment with network.

### Task 10: authoring-check kit (S, no calls)

**Files:** create `experiments/authoring_check/README.md`, `task.md`,
`line_count.sh`, `check.py`, `run_session.sh`. Contents are fixed by the
[protocol](#authoring-check-protocol). Commit the kit before any session
starts; it is not changed afterwards.

- [ ] Write the kit. Prove `check.py` on two hand-written directories: a
      correct solution passes; one that returns a constant fails the hidden
      case. No model is called.
- [ ] Commit. The coordinator puts the budget request to the owner.

## Headline exit test

`tests/test_first_hour_e2e.py::test_failed_run_is_diagnosed_and_resumed_from_terminal_output`,
in the environment fixture of Task 9:

1. Write the pipeline files from the tutorial's file blocks into the empty
   directory. Do not create `notes.txt`.
2. `orchestrator run grow.orc --input file=notes.txt --input target=5`, with
   no manifest flag. Expect exit 1.
3. From the captured stderr alone: a `failed` line names an identity; the
   stderr tail names `notes.txt`; take the command from the `resume` line.
4. Create `notes.txt` with three words.
5. Run the extracted command verbatim through the shell. Expect exit 0 and a
   last stdout line equal to `{"pads":2,"words":5}`.

The test never reads `.orchestrate/`. It fails today at step 3. It covers a
failure whose cause lies outside the command's own files; the script-bug case
is roadmap Phase 3a (Deviations, item 8).

## Authoring-check protocol

Not run by implementers. It spends provider calls, so the
[experiment rules](../../AGENTS.md) apply. It reports execution outcomes and
cost only, which those rules allow without task-family qualification; it makes
no quality claim and no claim of "better".

- **Question:** given one document and the CLI, does a fresh agent session
  produce a working provider-free workflow?
- **Task** (`task.md`, the same in both arms): in an empty directory holding
  the document as `GUIDE.md` and an existing script `line_count.sh FILE`,
  write `tally.orc` (module `tally`, workflow `run`, inputs `file` and
  `target`) and `commands.json` so that the run appends one line to the file
  per round, through a command, until the script reports at least `target`
  lines, for at most six rounds, and returns a record `{lines, rounds}`. The
  task differs from the tutorial's pipeline.
- **Arms:** *before* installs the Phase 1 base commit and gives
  `docs/lisp_workflow_drafting_guide.md`, the document the index routes a new
  author to today. *After* installs the phase tip and gives
  `docs/tutorial_first_pipeline.md`. The comparison is of the phase as a
  whole, document and CLI together.
- **Session:** one non-interactive agent CLI session per directory, model
  `claude-haiku-5-5`, no fallback model, no Fable model, tools limited to
  shell and file read, write and edit, no subagent tool, no MCP server, user
  and project settings and memory not loaded, a 20-minute wall limit and a
  per-session spend cap. `run_session.sh` fixes the exact flags after
  `claude --help` on the launch machine and saves the JSON transcript. A
  session whose transcript shows a read under the checkout path counts as a
  fail.
- **Pass, by `check.py <directory>`:** `compile` exits 0; a visible case and
  two hidden cases (already satisfied at the start; bound reached) each exit 0
  and `report --format json` shows `run.workflow_outputs` equal to the
  expected record; `line_count.sh`, which logs each call, was called during
  the hidden runs. `check.py` passes the manifest flag explicitly so it works
  on both installs.
- **Readout:** per arm, sessions passed out of sessions run, and per session
  the tokens and cost the CLI reports, wall time, and the number of
  `orchestrator` invocations that failed. The phase's authoring check is met
  when at least two of three *after* sessions pass. The *before* figure is
  recorded beside it whatever it is.
- **Budget request:** six sessions, three per arm, six provider starts in
  all, all on `claude-haiku-5-5`; no retry, no judge call. Proposed cap:
  USD 2 per session, USD 12 in total, for the owner to set. A session that
  hits a cap counts as a fail.

## Deviations from the roadmap

Left out as the roadmap says: more than one diagnostic per compile; the
write-once lint. Also outside this phase: token metering and stable generated
names (Phase 2), retry after a script fix and prefix reuse (Phase 3), deleting
retired commands (Lane D; here they are only hidden), a multi-line prompt
literal, a built-in script wrapper. The Phase 3 feasibility spike that the
roadmap runs alongside needs its own short plan and touches no file named
here.

For the coordinator to rule on:

1. **`:on-exhausted` error deferred.** Phase 1 ships the warning on every
   admitted target. Lane D has not named its single target, so the error is
   left to Lane D stage 4, where it is one severity change plus adding the
   keyword to 13 fixtures and up to 28 forms in test modules. Alternative:
   make it an error at 2.40 now; no tracked 2.40 source omits it, but 2.40
   would then differ from 2.39 on a rule unrelated to host input.
2. **Added: `resume --quiet`.** The contract documents it and the parser
   rejects it.
3. **Added: program name.** Help says `orchestrate`, the installed script is
   `orchestrator`; printed recovery commands must be runnable.
4. **Added: a `--dry-run` confirmation line**, from the audit; one line in the
   same reporter.
5. **Added: the missing-manifest diagnostic names the file and the flag.**
6. **Added: tests that pin prompt edit and continue.** The roadmap asks only
   for the check and the document.
7. **The tutorial teaches `.orc`.** Hand-written `.orc` gives readable effect
   identities, which `invalidate` and the new messages print; Python-generated
   names stay positional until Phase 2. The tutorial links to the Python guide.
8. **The exit test does not cover a bug in the failing step's own script.**
   That run cannot be resumed after the fix until Phase 3a. Phase 1 makes the
   refusal say so and print the command for a new run.
9. **"Fresh environment" means a new virtual environment that sees the base
   interpreter's packages**, so the test needs no network. A clean install
   from the repository URL is one manual check at phase close.
10. **Import-time targets are recorded, not asserted.** The tests assert that
    `jsonschema` is not imported; wall time varies with machine load.
11. **Help hides `prompt` as well**, since its `run` and `import` modes are
    retired; say if `prompt resume` should stay listed.
12. **Result on stdout even with `--quiet`.** Scripts get a clean value; tests
    that expected empty stdout change. The alternative is silence under
    `--quiet`, which keeps those tests and loses the scripted use.

## Ledger

| Date | Decision or event | Detail | Spend |
| --- | --- | --- | --- |
| 2026-11-11 | Plan accepted by the coordinator | Deviations 1–12 accepted as written. In particular: the `:on-exhausted` error waits for Lane D stage 4 (warning now); the tutorial teaches `.orc`; the exit test uses a failure outside the command's own files because a script fix cannot be resumed before roadmap Phase 3a; the result prints on stdout under `--quiet`. | none |
| 2026-11-11 | Authoring check approved by the owner | Six `claude-haiku-5-5` sessions (three before, three after the phase), cap USD 2 per session and USD 12 in total, no retries, no judge calls. Task 10 builds the kit; nothing is spent until the kit and the "before" environment exist. | 0 of USD 12 |
| 2026-11-11 | Task 3 done and merged (`c9c5dcc4`) | `jsonschema` is imported only inside the four validating functions. Median of three runs at load average about 60: `--help` 3.45 s to 0.25 s; `compile` of a one-command workflow 4.81 s to 0.90 s. 1,026 tests in the eleven modules that import the touched files pass. Brought forward because CLI start time dominates the slow tests. | none |
| 2026-11-11 | Owner ruling on the authoring check: "unconfined runs are fine" | The six sessions may run without a sandbox, with permission checks bypassed and a shell tool, as the kit's launcher starts them. Spend authorization, the six-session limit, the exact model binding and the check for other models remain required. | none |
| 2026-11-11 | Tasks 1 and 2 done, reviewed and merged (`b9207701`) | An effect given directly to `continue` (command, procedure call, `request-input`) is let-bound; the trigger is narrower than the task text (only a state that is itself an effect), so no existing program digest moves: all 62 programs that compile in isolation keep theirs. A loop without `:on-exhausted` compiles with one located `loop_missing_on_exhausted` warning; the loop that `list/map-effect` lowers to is not warned. Independent review found two defects (a false warning on `list/map-effect`, a remaining crash on `request-input`); both fixed before merge. One language-server fixture gained the keyword. | none |
| 2026-11-11 | Known gaps left by Tasks 1 and 2 | A `match` given directly to `continue` still crashes with `compiler_defect` (also before this phase); a loop produced by a macro is warned once per expansion, each pointing at the macro definition. Neither is selected in this phase. | none |
| 2026-11-11 | Tasks 7 and 10 done, reviewed and merged (`c38fe6d6`) | Task 7: editing a prompt file and continuing is documented in `docs/runtime_execution_lifecycle.md` and pinned by five tests (failed step, step not yet run, committed step then `invalidate`, restored file, inline prompt). Task 10: the authoring-check kit is at `experiments/authoring_check/`. After review it starts each session from an empty environment with every model variable pinned to `claude-haiku-5-5`, puts refusing stub CLIs ahead of the real ones for the session and the checker, keeps the six session slots and the CLI version in `~/.local/state/authoring-check`, requires real workflow steps and one randomly drawn hidden case in the check, and has the readout fail any session that used another model, started a nested session, or read the repository, charging USD 2 for a session of unknown cost. "Before" is commit `22dfb973` with the drafting guide; "after" needs the tutorial of Task 9. Read out session 1 before starting session 2. No model called. | 0 of USD 12 |
| 2026-11-11 | Tasks 4, 5, 6 and 8 done, reviewed twice and merged (`045ff7be`) | `run` and `resume` print the run id, one line per effect start, commit and failure, the result as the last stdout line and a `resume` command on failure or Ctrl-C; reporting is attached only by the CLI and the REPL, not the Python SDK. Refusals state the step's real state from the memo and print commands that work. A script fix after a failure is told plainly that it cannot be resumed in this run (restore and resume, or a fresh run) until roadmap Phase 3. Manifests beside the source are picked up without flags; help lists the public commands. `specs/cli.md` updated. The first review found one blocker (advice that re-ran a committed step to no effect) and five majors; all fixed and confirmed by a second review. | none |
| 2026-11-11 | Follow-ups from the second review, to do with Task 9 | A step that was invalidated and not yet re-run is described as unfinished, so the advice is safe but costlier than needed; the reporter turns a stream off on any write error, so a result that cannot be encoded is lost silently (redirect only on a dead descriptor and escape unencodable characters). Minors left from the first review: printed commands use a literal `python`; the `waiting` line names only `input get`; no extra line when a default-picked manifest fails validation. | none |
| 2026-11-11 | Authoring check, "before" session 1 run | `claude-haiku-5-5` only, CLI 2.1.322, 95 seconds, 11 tool calls, cost reported by the CLI USD 0.016. The session wrote a 29-line workflow that passed the check, including the randomly drawn hidden case. Sign-in worked from the empty environment; no nested session, no stub call, no read of the checkout. The readout first failed the session with `other_sessions_read`: the CLI had saved an oversized tool output (the 148 KB guide) under its own project store and named that path in the result. That is the session's own store, so the rule was corrected after seeing this one result (`readout.py`, with a test); the correction changes no other rule. | USD 0.016 of 12 |
| 2026-11-11 | Authoring check, "before" arm complete | 3 of 3 sessions passed (29, 32 and 38 lines of `.orc`; 95 to 104 seconds; 5 to 7 `orchestrator` invocations, none failed; `claude-haiku-5-5` only). The task is therefore at ceiling: the "after" arm cannot show a higher pass rate. It still runs as planned once the tutorial exists, to check that the tutorial alone is enough and to compare time, tokens and failed invocations; no claim about improvement in pass rate will be made. Cost figures are the CLI's own. | USD 0.051 of 12 |
| 2026-11-11 | Task 9 and the second-review follow-ups done and merged (`5b497fc1`) | Tutorial `docs/tutorial_first_pipeline.md` (318 lines against a target of about 150; a third is real command output). `tests/test_first_hour_e2e.py` runs the tutorial's own blocks in an empty directory with the CLI installed from the working tree, no network, and automates the headline exit test: from printed text only it finds the failing step, reads the printed stderr path, runs the printed `resume` command and gets the result. At the Phase 1 base the same run prints no run id, step or resume command. Follow-ups: an invalidated step no longer counts as unfinished; the reporter silences only a dead descriptor and escapes a result the terminal cannot encode. Full suite on the branch: 14,453 passed, 6 failed (the four worktree-artifact ids and two intermittent tests that also fail intermittently on the base). The plan's manual check of a clean network install was not done. | none |
| 2026-11-11 | Phase 1 exit test met | The headline exit test passes on `main`. Remaining: the "after" arm of the authoring check. The tutorial's worked example is a count-and-append loop of the same shape as the check's task, as Task 9 prescribed, so the "after" arm cannot show more than that the tutorial alone is enough for a task close to its own example. | none |
| 2026-11-11 | Friction found while writing the tutorial, not fixed in this phase | `resume` prints an `[effect_rerun]` log line before its `run` line; the first line of an `effect_input_diverged` refusal is long and carries digests; one recovery sentence repeats itself; `(continue <effect>)` gives the step the identity `#1`, so the tutorial let-binds it for a readable name; the ten-line stderr tail is often traceback frames; `compile` and every failure print absolute paths. | none |
| 2026-11-11 | Authoring check complete; Phase 1 closed | "After" arm: 3 of 3 passed (16 to 17 lines of `.orc`; 33 to 41 seconds; 2 to 3 `orchestrator` invocations, none failed; `claude-haiku-5-5` only). "Before" arm: 3 of 3 passed (29 to 38 lines; 95 to 104 seconds; 5 to 7 invocations). Pass rate does not differ and could not: the task was at ceiling. The "after" sessions were about 2.6 times faster and used about a third of the cost, but the tutorial's worked example has the shape of the task and the tutorial is a tenth the length of the guide, so this shows that a short worked example is cheaper to follow, not that the tool became easier to author for. No claim about authoring quality is made. Six sessions, the limit; all figures are the CLI's own. | USD 0.071 of 12; closed |

