# Phase 6 Readiness R3: Mechanical Mutants Of The Seeds: Implementation Plan

**Status: Plan, proposed 2026-11-13; not reviewed, not accepted.** It plans readiness item R3 of
[Phase 6](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-6-program-evolution)
("Mutants never crash the compiler") and the zero-spend check of H-E2's reach named in the same
section. It is a plan, not a contract and not copy-safe guidance. Behavior is owned by `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md). No task makes or authorizes
a provider or model call; every run in it uses stand-ins on a closed `PATH`. Planned against `main`
at `b399076b`.

**Goal:** a generator of a few hundred mechanical mutants of the seeds, deterministic from a seed
number; a check that each mutant compiles or is refused with a diagnostic code, with every crash
keyed as the defect backlog keys them; and, per mutation operator, the share of a completed run's
steps that `resume` would keep under the mutant.

**Approach:** operators are generators of character-range edits found by reading the source with
the package's reader and spliced into the text, so no printer is needed and comments and layout
survive. One script compiles every mutant in process, asks `plan_resume` for the plan under each
compiling mutant on a stand-in run, and writes one report. What this makes harder is listed
[below](#what-this-makes-harder).

**Not in this plan:** a search driver, selection, fitness, crossover between programs; fixing any
defect the mutants find (the defect backlog plan, branch `docs/defect-backlog-plan`, owns fixes);
a change to `resume` (the two findings in [open decision O5](#open-decisions-for-the-coordinator)
are reported, not fixed); mutants made of two or more mutations (an operator accepts any source, a
mutant included, so a search composes by applying them again).

## Probes That Shaped The Plan

All on `main` at `b399076b` unless a row says otherwise, with
`experiments/thread_m/no_provider` first on `PATH`, `PYTHONPATH` set to the tree under test, scratch
under `/tmp/r3p` (deleted). Seeds were exported with
`git archive BRANCH PATH | tar -x -C DIR`. "Compile" is
`python -m orchestrator compile P.orc --entry-workflow P::run --source-root . --provider-externs-file providers.json --command-boundaries-file commands.json`
run in the seed's directory. The stand-in run is the spike branch's
`experiments/long_horizon_seed/demo.py` with `ORC_ROOT` naming the tree (the fake `claude` of
`tests/agent_session_shims.py` on `closed_path`, scenario `clean`), the sources copied beside the
workspace so that an edit never touches a tracked file.

| # | Question | Command or method | Outcome |
| --- | --- | --- | --- |
| P1 | Do the long-horizon seeds compile on `main`? | Compile `milestones`, `staged`, `roles` and the two programs under `variants/` from `spike/long-horizon-seed` (`aa7ae4a0`) | All five build (exit 0; 8, 6 and 12 sites for the three seeds). No construct fails. The same digests on `feat/coherence-e1` (`588faf29`) |
| P2 | Do they run? | `python demo.py DIR milestones clean`, then `staged`, `roles` | All end in `DONE`: 11, 6 and 17 committed steps; 8, 5 and 8 provider calls |
| P3 | Do the seed-set programs compile on `main`? | Compile the four programs of `experiments/seed_set/programs/` from `feat/seed-set-prep` (`5449db80`) | All four build, on `main` and on E1. `plan_implement_review.orc`, the seed the seed-set plan names, does not exist on any branch |
| P4 | What fails on `main`? | Compile the seeds as rewritten in the staged-authoring idiom (`spike/authoring-revisions`, `experiments/authoring_revisions/seeds/`), then one module per construct | Refused, on `main` and on E1 alike: `Prompt[T]` (`generic_union_not_generic`), a provider as an argument (`provider_result_provider_invalid`), `(list :of String)` (`keyword_argument_invalid`), `list/take` and `list/all` (`pure_expr_operator_unsupported`), a timeout as a name (`provider_result_timeout_literal_required`). All wait for the staged-authoring revisions; none waits for E1. An input with a literal default (`(effort String :default "medium")`) builds today |
| P5 | Is there a reader and a printer that round-trip a `.orc` file? | `orchestrator.workflow_lisp.reader.read_sexpr_text`; a search of `orchestrator/` for a printer; for each of the 644 tracked and seed `.orc` files, re-read the text slice `text[span.start.offset:span.end.offset]` of every node | A reader with character-offset spans; no printer (the Python frontend writes text directly). The slice of every one of 91,844 nodes re-reads to the same form in 641 files; 3 files are unreadable on purpose. Offsets index characters, also after non-ASCII text. So a mutation is a splice of the decoded text at a node's span |
| P6 | Does the compiler check a model or an effort? | Compile a call with `:model "claude-fable-5-2" :effort "bogus"` | Builds. The compiler is no backstop: the operators' value sets must be closed and tested |
| P7 | What is the compile entry and the crash key? | `prepare_closed_program_bundle(FrontendBuildRequest(...))` in process; for a `compiler_defect`, the diagnostic's `cause`; for an escaped exception, the exception | In memory, no cache write; 0.04 to 0.4 s per mutant. Key `<exception class> <path under orchestrator/>:<innermost function>` gives `RuntimeError workflow_lisp/loop_state.py:_typecheck_loop_state_seed` for the backlog's D9 and `TypeError workflow_lisp/wcc/elaborate.py:_infer_expr_type` for D5, which are the functions its table names. The command line cannot give the function, so the check compiles in process |
| P8 | What do mechanical mutants do today? | A throwaway prototype of the operators below (without `conversation`): 427 mutants of the three long-horizon seeds and 350 of the four seed-set programs (seed number 1), then 750 `graft` mutants (number 7) | Every mutant builds or is refused with a code, except one crash key, hit four times, by `graft` mutants only, on three programs (`milestones`, `staged`, `retry_until_check`): `TypeError workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump`. Minimal form: `(loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted 0 (fn (state) (let* ((x (done 1))) x)))`. It is not in the backlog's table, and E1 does not close it. `effort`, `model` and `rounds` mutants all build, each with its own digest; `graft` builds 5 percent of the time (38 of 750), `name_unknown` being the commonest refusal |
| P9 | Does E1 change a mutant's outcome? | The same 750 `graft` mutants against an export of `feat/coherence-e1` (`588faf29`) | No outcome differs |
| P10 | What does `resume` print under a hand-made edit of each dimension? | A completed stand-in run of `milestones` (11 steps), one edit, `orchestrator resume RUN_ID` (no token, so read-only), the source restored | Table below. `plan_resume(run_root, workspace)` in `orchestrator/workflow/evaluated/rebase.py` returns the same plan in process (`kept`, `cancelled`), in 0.6 to 0.8 s |

P10, share of the 11 committed steps kept:

| Edit | `resume` | Kept | Why the cut is there |
| --- | --- | --- | --- |
| Effort or model as a literal at the planner's three calls | `resume_program_changed`, a plan | 0 of 11 | The planner runs first |
| The same at the coder's call | a plan | 3 of 11 | First coder step |
| The same at the reviewer's two calls | a plan | 5 of 11 | First reviewer step; the cut is a journal suffix, so the second milestone's coder step is cancelled too |
| Effort literal equal to the bound value (`"medium"`) | a plan | 5 of 11 | The declaration differs although the value does not |
| Effort or model through `inputs.json` | `resume_inputs_changed`, no plan | none | Changed inputs are refused |
| The literal default of an input, when the edit takes effect | `resume_program_changed`, "no plan can be accepted: `resume_inputs_changed`" | none | The same refusal, reached through the program |
| Rounds: a loop's `:max`, either loop; the map's `:max` | a plan, no cut | 11 of 11 | The bound was not reached |
| Timeout of the coder's call | a plan | 3 of 11 | Part of the call's policy |
| Prompt wording: `guides`, `work`, `review` | a plan | 0, 3, 5 of 11 | First step that uses the prompt |
| Drop the unused first binding; swap the first two | a plan | 0 of 11 | The first step is not reached next |
| Conversation: the planner's three calls continue one session | a plan | 0 of 11 | The session opens before the first step |
| Comment or layout only | exit 0, the run's result | all | Same digest |
| On `roles` (17 steps): effort at an `agent` form, a prompt, or continued to fresh | `resume_program_changed`, "no plan can be accepted: `invalidate_coordinator_committed`" | none | A plan never cancels a committed agent turn |
| On `roles`: a loop's `:max` | a plan, no cut | 17 of 17 | |

**Prior art.** The October search (`experiments/orc_structural_search/`) has no mechanical
mutator: its mutators are model sessions that rewrite a file (I1) or one site (I2). What is reused
from it is its rule for text (decode UTF-8, normalise line ends, index characters:
`sites.py:_forms_and_text`) and nothing else, because its code is closed and its tests are opt-in.
`experiments/orc_gp_example/` mutates a grammar genotype and renders a program from it; it cannot
mutate a seed's source, and its model list holds models above the ceiling. Neither is imported.

## Global Constraints

- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`; no
  `git stash`. One worktree; `PYTHONPATH` set to it; `experiments/thread_m/no_provider` first on
  `PATH`; `mkdir -m 700` for any basetemp.
- No provider or model call. A run that reaches a provider step installs the fake `claude` of
  `tests/agent_session_shims.py` and gives its subprocess `closed_path(...)`.
- Operators live under `experiments/`, never under `orchestrator/`: the
  [boundary invariants](../design/workflow_lisp_program_search_boundaries.md) (invariant 3) keep
  mutation out of the package. Every mutant goes through the ordinary compile (invariant 1).
- Tests assert outcomes, diagnostic codes, digests and parsed forms, never prompt text. Test
  sources declare `(:target-dsl "2.40")`. A new test fails first for its stated reason. Function
  complexity at most 12.
- **Closed value sets.** `MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")` and
  `EFFORTS = ("low", "medium", "high", "xhigh", "max")` are module constants with no override from
  the environment, a file or an argument. No operator writes a model or an effort outside them, so
  no mutant names a model above the Sonnet ceiling or a Fable model (`AGENTS.md`, experiment
  rules). The first space is `effort` with `low`, `medium`, `high`.
- **Frozen surfaces.** No operator changes the module name, imports, exports, the target, a type
  declaration, a prompt's `:fills` or return type, the entry workflow's parameter list or the
  manifests; `common.orc` is never a mutant
  ([driver design](../design/orc_structural_search_driver.md#edit-validation-and-transactions)).
  No operator but `graft` adds a line, so a 49-line seed stays under the 50-line limit.
- **Gate:** the narrow run, `pytest --collect-only` on the new module, then
  `pytest -q -n 16 --dist=worksteal --sample 10`. The whole suite before the merge is the
  coordinator's.

## Files

Three new files; nothing in `orchestrator/` changes.

| File | Responsible for |
| --- | --- |
| `experiments/mutants/operators.py` | The operators and the sample. Depends on `orchestrator.workflow_lisp.reader` and `sexpr` only. Holds no state, reads no file |
| `experiments/mutants/check.py` | Measuring mutants: the compile outcome and crash key, the reuse share, the report, and the one command. Depends on `prepare_closed_program_bundle`, `plan_resume`, and the stand-ins of `tests/agent_session_shims.py` and the driver of `tests/test_workflow_evaluated_agent_consumer_smoke.py` (as the seed's `demo.py` does) |
| `tests/experiments/test_mutants.py` | The default-suite sample and the operators' tests, on one fixture seed written in the module |

Interfaces:

```python
# operators.py
@dataclass(frozen=True)
class Mutation:
    operator: str                               # a key of OPERATORS
    params: str                                 # e.g. "reviewer=low", "loop1=3", "9<-18"
    edits: tuple[tuple[int, int, str], ...]     # disjoint (start, end, replacement) character ranges

OPERATORS: dict[str, Callable[[str], Iterator[Mutation]]]   # every mutation of one source, in document order
def apply(text: str, mutation: Mutation) -> str             # splice, right to left
def sample(sources: Mapping[str, str], cap: int, number: int) -> list[tuple[str, Mutation]]

# check.py
def crash_key(error: BaseException) -> str
def outcome(work: Path, program: str) -> tuple[str, str]     # ("compiles", digest) | ("refused", code)
                                                             # | ("crash", key) | ("traceback", key)
def compile_report(seed_dir: Path, programs: Sequence[str], cap: int, number: int) -> dict
def reuse_report(seed_dir: Path, program: str, standin: Mapping, mutants) -> dict
```

Text is `path.read_bytes().decode("utf-8")` with `\r\n` and `\r` turned into `\n`; spans index that
text. `sample` takes, for each program in name order and each operator in `OPERATORS` order, all
its mutations when there are at most `cap`, else `random.Random(f"{number}/{program}/{operator}")`
`.sample(...)` of them, kept in document order. A mutant's name is `program/operator/params`; it
reproduces the mutant without the seed number.

## Operators

Shared terms. A **call form** is a list headed `provider-result` or `agent`; its **role** is its
first operand when that is a symbol `providers.R` (role `R`). The **operand of** `:k` is the item
after the keyword `:k` among a form's own items. An operator yields no mutation whose replacement
equals the text it replaces. Examples are from `milestones.orc`.

| Operator | Dimension | Sites and edit | Parameters | Must not produce |
| --- | --- | --- | --- | --- |
| `effort` | Effort per role (first space for `low`, `medium`, `high`) | The operand of `:effort` in every call form of one role, all of them in one mutation, replaced by a string literal | role; level in `EFFORTS` | A level outside `EFFORTS`; an edit of some of a role's sites; an inserted `:effort`; an edit of an input or its default |
| `model` | Model per role | The same for `:model` | role; model in `MODELS` | A model outside `MODELS` |
| `rounds` | Structure: revision rounds | The operand of `:max` of one `loop/recur`, when an integer literal | loop number in document order; n in 1 to 4 | 0, a value above 4, a `list/map-effect` cap, a non-literal bound |
| `drop_step` | Structure: a step absent | One binding of one `let*` inside a `defworkflow` or `defproc`, deleted | `let*` number; binding number | Anything but one whole binding |
| `prompt` | Prompt wording | The body of one `defprompt` (its last item, a string), edited as raw source text between the quotes, so escapes are never re-encoded. `drop k` removes sentence k, sentences being the pieces between `". "`; `append` adds one fixed sentence before the closing quote | prompt name; `drop k` or `append` | An empty body; an edit of two prompts; a change to `:fills` |
| `graft` | Structure, beyond the declared values ([ruling 4](#rulings)) | One expression form replaced by the source text of another of the same module. An expression form is a list inside a `defworkflow` or `defproc` whose head is in the constant `EXPRESSION_HEADS` (`provider-result command-result call loop/recur let* if match list/map-effect list/map done continue variant record loop-state agent not and or = + list/append list/length`) | target number; donor number | A donor from another file; a donor that contains the target; a replacement equal to the target |
| `conversation` | Conversation | `continue`: in one `defworkflow`, when all `provider-result` forms of one role have the same `:model` and `:effort` text, wrap the workflow's body in `(let* ((R-session (agent providers.R :model M :effort E))) ...)` on the same line and, in each of those forms, put `R-session` for `providers.R` and delete the two keyword pairs. `fresh`: for a binding `(N (agent providers.R K...))`, delete it and put `providers.R K...` for `N` in every `provider-result` of that `let*` | workflow; role or binding; direction | A new line; a session shared across workflows; a name already used in the module |

Before and after:

- `effort`, `reviewer=low`: `(provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200 ...)`
  becomes `(provider-result providers.reviewer :model reviewer :effort "low" :timeout-sec 1200 ...)`
  at both reviewer calls. Builds; a new digest.
- `rounds`, `loop0=3`: `(loop/recur :max 2 :state ...` becomes `(loop/recur :max 3 :state ...`.
- `drop_step`, `let1.0`: the binding `(ready (provider-result providers.planner ... (guides ...)))`
  disappears; builds (nothing reads `ready`). `let1.1` (`spec`) is refused `name_unknown`.
- `prompt`, `work.drop2` removes the sentence that holds `{milestone}`: refused
  `prompt_placeholder_missing`. `work.append` builds.
- `graft` on `staged`, target the coder's call, donor the acceptance arm: the coder's
  `provider-result` becomes
  `(done (variant Outcome DONE :summary "accepted"))`: today's crash (P8).
- `conversation`, `run/planner/continue`: the three planner calls become
  `(provider-result planner-session :timeout-sec 1200 :prompt ...)` under one `agent` binding.

A "role absent" mutant is not an operator of its own: `drop_step` gives it when nothing reads the
step, and `graft` gives it when a `match` on a reviewer's verdict is replaced by one of its arms.

## Tasks

Order: T1, T2, T3, T4, T5, then T6 and T7 when what they wait for exists.

| Task | Hours | Waits for |
| --- | ---: | --- |
| T1 Six operators and the sample | 7 | Nothing |
| T2 Compile check, crash key, report, command | 4 | T1 |
| T3 Reuse share | 5 | T2 |
| T4 The `conversation` operator | 3 | T1; [decision O6](#open-decisions-for-the-coordinator) |
| T5 First readout and hand-off to the defect backlog | 2 | T3 (and T4 if kept) |
| T6 The frozen seeds in the suite and in the command's defaults | 2 | The seed's merge to `main` (roadmap Phase 5b, step 8) |
| T7 Sites of the role idiom | 3 | Staged-authoring Task P5 and [decision O4](#open-decisions-for-the-coordinator) |

Nothing waits for E1 (P1, P9). After E1 merges, T5's command is run once more, since refusal codes
and the function in a crash key can move.

### Task T1: Six operators and the sample (7 h)

Files: `experiments/mutants/operators.py`, `tests/experiments/test_mutants.py`.

- [ ] The fixture `SEED` in the test module: one module at target 2.40, under 25 lines, with
      its own record and union types, three prompts, an entry
      `run ((task String) (repo String) (planner String) (coder String) (reviewer String) (effort String))`,
      one planner call, then a `loop/recur :max 2` holding a coder call, a `command-result` and a
      `match` on a reviewer call. It is the only source the default suite mutates until T6.
- [ ] `Mutation`, `apply`, the operators `effort`, `model`, `rounds`, `drop_step`, `prompt`,
      `graft`, and `sample`, as defined above.
- Tests, each failing first because `experiments.mutants.operators` or the operator's key in
  `OPERATORS` does not exist:
  - `test_each_operator_yields_mutations_of_the_fixture`: the count per operator is the one the
    fixture fixes (3 roles times 5 levels for `effort`, and so on).
  - `test_effort_edits_every_call_of_one_role_and_nothing_else`: re-read the mutant; the operand
    of `:effort` is the string `low` at each `providers.reviewer` form and unchanged elsewhere;
    every other top-level form is equal to the seed's.
  - `test_no_mutant_names_a_model_or_effort_outside_the_closed_sets`: over every mutation of
    every operator, the string literals in `:model` and `:effort` position are in `MODELS`,
    `EFFORTS` or the seed.
  - `test_frozen_surfaces_survive`: module name, exports, target, type declarations, each
    prompt's `:fills` and the entry's parameter list are equal forms in every mutant.
  - `test_only_graft_adds_a_line`.
  - `test_prompt_edit_keeps_escapes`: the mutant re-reads, and the body's value differs from the
    seed's only by the removed or added sentence (compared as a property, not as literal text).
  - `test_sample_is_deterministic_and_capped`: equal lists for one number, different for
    another, at most `cap` per program and operator, names unique.
- Run: `pytest -q -n 8 tests/experiments/test_mutants.py` (expected: all pass; under 5 s).
- Reviewer: that sites are found by form and keyword, never by line or offset constants; that
  `apply` rejects overlapping edits.

### Task T2: Compile check, crash key, report, command (4 h)

Files: `experiments/mutants/check.py`, the test module.

- [ ] `outcome`: copy the seed directory to a work directory once, write the mutant over its
      program there, and call `prepare_closed_program_bundle` (no cache write; the seed
      directory is never written). `LispFrontendCompileError`: `("crash", crash_key(cause))`
      when the first diagnostic is `compiler_defect`, else `("refused", code)`. Any other
      `Exception` except `MemoryError`: `("traceback", crash_key(error))`. This one broad
      `except` is the check's purpose: an escaped exception is an outcome to record.
- [ ] `crash_key`: `"<type name> <file path after orchestrator/>:<function>"` of the innermost
      traceback frame inside the `orchestrator` package, or of the innermost frame when none is.
      The kind (`crash` or `traceback`) is not part of the key, so the backlog's TP1 moves no key.
- [ ] `compile_report`: per operator the counts of `compiles`, each refusal code, each crash
      key and mutants of 50 lines or more; `distinct_digests`, `equal_to_seed`; and `crashes`,
      one row per key: kind, count, operators, programs, the name of one mutant.
- [ ] `python -m experiments.mutants.check SEED_DIR --programs a,b,c [--cap 100] [--number 0] [--out report.json]`:
      prints the table, writes the report, exits 1 when any mutant ends in a crash or a
      traceback, else 0. A seed that does not build itself is a usage error (exit 2).
- [ ] `KNOWN_CRASHES` in the test module: the set of crash keys `main` is known to produce,
      today `{"TypeError workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump"}`. It may only
      shrink ([decision O1](#open-decisions-for-the-coordinator) joins it to the backlog's list).
- Tests, failing first because `check.outcome` does not exist:
  - `test_outcome_kinds`: a `rounds` mutant gives `compiles` with a digest other than the
    seed's; `drop_step` of a binding that is read gives `("refused", "name_unknown")`; a
    `prompt` drop of a sentence holding a placeholder gives
    `("refused", "prompt_placeholder_missing")`.
  - `test_crash_is_keyed_by_exception_class_and_innermost_function`: P8's minimal program gives
    kind `crash` and the key in `KNOWN_CRASHES`. When the defect is fixed this test fails; the
    fix removes the key and asserts the new outcome.
  - `test_escaped_exception_is_keyed_the_same_way`: the backlog's D9 program gives the key
    `RuntimeError workflow_lisp/loop_state.py:_typecheck_loop_state_seed` (the kind is not
    asserted; TP1 changes it).
  - `test_no_mutant_of_the_fixture_crashes_outside_the_known_list`: `compile_report` on the
    fixture at `cap` 3, number 0; every key in `crashes` is in `KNOWN_CRASHES`; the report's
    counts add up to the number of mutants.
  - `test_command_exits_1_on_a_crash_and_0_without`: the command on a one-program directory
    whose loop body is `(let* ((x (+ state.i 1))) (done state.i))` (the `graft` of the binding's
    value by the `done` form is P8's crash; probed) exits 1 and names the key; once the key
    leaves `KNOWN_CRASHES` the test keeps only its second half, the fixture, which exits 0.
- Run: the module, as in T1 (expected: under 20 s; about 20 mutants at 0.1 to 0.4 s).
- Reviewer: that the suite test cannot pass by producing no mutants; that nothing is written
  under the seed directory.

### Task T3: Reuse share (5 h)

Files: `check.py`, the test module.

- [ ] `reuse_report(seed_dir, program, standin, mutants)`. `standin` is
      `{"answers": [...], "inputs": {...}, "files": {...}}`: the fake `claude`'s answers in call
      order, the run's inputs (the check sets `repo` to the workspace), and the workspace's files.
      It builds a world (`src/` a copy of the seed directory, `repo/` the workspace, `bin/claude`
      the fake), runs the seed once to completion through the driver with `closed_path`, then for
      each mutant that compiles: writes it to `src/`, calls `plan_resume(run_root, repo)`, and
      restores the source at the end.
- [ ] Per mutant: `("plan", kept, cancelled)`; `("same_program",)` when its digest is the
      seed's (not sent to `plan_resume`); `("no_plan", code)` for a `PlanRefusal` or a resume
      refusal. The share is `kept / (kept + cancelled)`, 1 for `same_program`, 0 for `no_plan`.
- [ ] Per operator in the report: mutants measured, plans, the minimum, median and maximum
      share, and each `no_plan` code with its count. `--standin FILE.json` on the command adds
      the reuse section for the programs the file names.
- Tests, failing first because `check.reuse_report` does not exist; one stand-in run of the
  fixture is shared by the module's tests:
  - `test_a_reviewer_effort_mutant_keeps_the_steps_before_the_first_review`: `kept` equals the
    number of steps the run committed before its first reviewer step.
  - `test_a_rounds_mutant_keeps_every_step`.
  - `test_a_layout_only_edit_is_the_same_program`.
  - `test_an_edit_under_a_committed_agent_turn_has_no_plan`: a second fixture whose coder is an
    `agent`; an `effort` mutant gives `("no_plan", "invalidate_coordinator_committed")`.
  - `test_the_seed_source_is_restored`.
- Run: the module (expected: under 40 s; two stand-in runs of about 5 s).
- Reviewer: that the run's own files are never written (`plan_resume` is read-only; the test
  compares the journal's bytes before and after); that no test reaches a real provider.

### Task T4: The `conversation` operator (3 h)

Files: `operators.py`, the test module. Both directions as defined above.

- Tests, failing first with `KeyError: 'conversation'`:
  `test_continue_then_fresh_restores_the_seed_program` (the digest after both equals the seed's
  digest, or the test records why it cannot: generated names are in the digest until R2);
  `test_continue_builds_and_adds_one_session_site`; `test_conversation_adds_no_line`.
- Reviewer: that a role whose calls differ in model or effort text yields no mutation.

### Task T5: First readout and hand-off (2 h)

- [ ] Export the three long-horizon seeds and the four seed-set programs to a scratch
      directory and run the command at its defaults (`--cap 100 --number 0`), with a stand-in
      file written from the `clean` scenarios of the seed's `demo.py`. Expected from P8: about
      540 mutants of the long-horizon seeds in about three minutes; exit 1 with one crash key.
- [ ] Ledger: the mutants per operator, outcomes, distinct digests, each crash key with its
      count and example, the reuse table per operator, the commit.
- [ ] Hand to the defect backlog's owner: every key, with the backlog row it matches or
      "new", under the rule of [the next section](#what-the-crash-report-feeds).
- No new test. The readout is provisional until T6 repeats it on the frozen seeds.

### Task T6: The frozen seeds (2 h; after the seed's merge to `main`)

- [ ] The command's default seed directory and programs are the merged seed's; the stand-in
      file sits beside the seeds, written once from `demo.py`'s `clean` scenarios.
- [ ] `test_no_mutant_of_the_seeds_crashes_outside_the_known_list` at `cap` 2 (about 40
      mutants), and one reuse test on `milestones` (a reviewer `effort` mutant keeps 5 of 11).
- [ ] Repeat T5's readout; one row in `docs/index.md`; the roadmap's R3 row gets its result.

### Task T7: Sites of the role idiom (3 h; after staged-authoring Task P5)

Needed only if the frozen seed binds roles with `bind-proc` (P4, decision O4). `effort` and
`model` then also take the operand of `:effort` or `:model` of a
`(bind-proc (proc-ref ask) :who providers.R ...)` form as a site. They still write a literal
there and never edit an input's default (P10: a changed default gets no plan). Test: on the
revised seed, an `effort` mutant builds and its plan keeps the steps before the role's first call.

## What The Crash Report Feeds

The defect backlog's rule is that a dropped defect returns only when a mutant or a real workflow
hits it. For mutants, "hits" is defined on the readout of T5 or T6: the command at its defaults
(`--cap 100 --number 0`) on the seeds named there.

| Case | Rule | Who decides |
| --- | --- | --- |
| A key hit by at least one mutant of `effort`, `model`, `rounds`, `drop_step`, `prompt` or `conversation` | Its defect returns to the backlog as a kept task: a search over the declared dimensions meets it | The rule; the coordinator records it in the backlog's ledger |
| A key hit by `graft` only | It returns when mutants of at least two programs hit it, or at least three mutants of one program; below that it is entered in `KNOWN_CRASHES` and stays dropped | The coordinator, by this threshold |
| A key that matches no backlog row | A new row, with the named mutant's minimal form as its reproduction | The coordinator adds the row; the first two rules then apply |
| A dropped row no mutant hits | Stays dropped, below every row that is hit (the backlog's own wording) | — |
| Returned tasks that together exceed 10 hours | The cut was the owner's, so growth beyond that is the owner's | The owner |

Classes A and C of the backlog are not ordered by this: a mutant that spends wrongly does not
crash. Applied to P8: the one key is `graft`-only and hit on three programs, so it is a new row
that returns.

## Review Focus

- The operators' definitions against the declared dimensions of the
  [seed-set plan](2026-11-11-seed-set-calibration-plan.md) ("Search dimensions around one seed"):
  is anything declared missing, is `graft` acceptable as the structure operator.
- Whether a literal at the call site is the right reading of "model and effort per role", given
  that the seed-set plan calls each point "a binding of that program" (ruling 2, decision O5).
- The crash key: that it is what the backlog's T0 can store, and that the suite cannot stay
  green on a new crash.
- The "hits" thresholds.
- That `check.py` holding the compile check and the reuse check is one responsibility
  (measuring mutants) and not two modules' worth.

## Size

26 hours in seven tasks: 21 can start now (T1 to T5), 5 wait (T6 for the seed's merge, T7 for
the staged-authoring revisions). With reviews, about 40 agent-hours. Suite cost: about 40 s of
one worker for the new module.

## What This Makes Harder

- **A mutant is a new program, not a binding of the seed.** Writing the literal at the call
  gives each effort point its own digest and source, where the seed-set plan describes the
  first space as bindings of one program. A readout that joins by program digest sees 27
  programs.
- **Site rules follow today's spelling.** A seed rewritten in the role idiom has no `:effort`
  on its calls until T7; a new call form (phased delivery, a library wrapper) needs a new site
  rule.
- **A second list that must shrink.** A fix of a crash removes its key from `KNOWN_CRASHES`
  and changes one test, beside the backlog's own row.
- **`graft` mostly tests the typechecker.** 5 percent of its mutants build, so the stages
  after typecheck see few of them; raising that needs a donor chosen by scope, which is not
  planned.
- **The check reads two internals:** `plan_resume` and the test driver. A change to either
  breaks the reuse check, not the package.
- **Step counts, not cost.** The share treats a provider step and a command step alike and
  comes from one `clean` run; a run that takes another path has another share.

## Not Verified While Planning

- No operator was written as planned: P8 used a throwaway prototype without `conversation`,
  with `swap` (dropped here) and with a wider `prompt` operator. Its counts are indicative.
- `conversation` was probed by one hand-made edit in each direction, not as an operator; that
  `continue` followed by `fresh` gives back the seed's digest was not tried.
- The reuse share on the seed-set programs (no stand-in scenario was run for them) and on any
  scenario but `clean`.
- T7: no tree has both the role idiom and a stand-in run; that a literal in a `bind-proc`
  form cuts at the role's first call is expected, not seen.
- That `plan_resume` in process agrees with the command line beyond the six edits compared.
- Whether the frozen seed will be the spike's spelling or the role idiom (decision O4).
- The hours: read from the prototype's size (about 110 lines for six operators and the
  outcome), not from a trial.
- The sampled suite and the whole suite were not run for this change, which is one document.

## Rulings

Planner's rulings, with the cost if wrong:

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | A mutation is a character splice at a reader span, on decoded and line-normalised text | P5: no printer exists, the slices round-trip on every tracked file, comments survive. The driver design's warning is about byte offsets, which are not used | A printer is written (about a day) and the operators return forms |
| 2 | `effort` and `model` write a literal at the role's calls and never touch inputs or defaults | P10: an input change, direct or through a default, gets no plan; the entry signature is frozen in every search condition | The operators gain an input-binding mode; its reuse share is zero until `resume` accepts changed inputs |
| 3 | The check compiles in process | P7: the key needs the traceback, and it is 0.1 s a mutant against about 1 s for the command line | A crash that only the command line shows is missed; the backlog's T0 covers that side |
| 4 | `graft` is in, although it is no declared value | The declared values alone built every time in P8 and found nothing; the crashes a search would meet come from moved subtrees. Its hits return a defect only above a threshold | It is removed from `OPERATORS`; the default suite loses its only crash-finding operator |
| 5 | The default suite mutates a fixture, not the seeds, until T6 | The seeds are not on `main` | Seed-specific crashes show only in T5's manual readout until the merge |
| 6 | Nothing is reused from the October search or the toy | Prior art, above | A few helper lines are duplicated |
| 7 | No `swap` operator, no two-mutation mutants, no skeleton count in the report | Not declared, not asked; composition is free by applying operators again | Added when a search asks |

## Open Decisions For The Coordinator

| # | Decision | Planner's recommendation |
| --- | --- | --- |
| O1 | One crash list or two. The backlog's T0 (`test/defect-backlog-t0`, no commit yet) keeps `KNOWN` by row with an outcome kind; this plan keeps keys | T0 stores, for each crash row, the key string of `crash_key` (computed once in process), and `test_mutants.py` reads its set from T0's module. Until T0 lands, `KNOWN_CRASHES` stays in `test_mutants.py` |
| O2 | The "hits" rule above, with its thresholds and the 10-hour bound | Accept |
| O3 | The new crash (`done` in a `let*` binding inside a loop) | Add it to the roadmap's list and the backlog's table now, as returned; it is one more shape of the control-forms row TD1 already keeps |
| O4 | The roadmap says two things about the seed: step 8 of Phase 5b freezes it once surface coherence is merged ("the staged-authoring revisions are not required for the first search space"), and Lane D item 6 says the revisions "land before the long-horizon seed is frozen" | Freeze the spike's spelling for the first space (it builds today, P1) and do T7 only when the revised seed replaces it |
| O5 | Two findings for the owner about what a search can reuse (P10). First, model and effort changed as inputs, or as input defaults (the revised seed's spelling), get no plan: `resume_inputs_changed`. Second, on a seed with Agent Sessions no edit under a committed agent turn gets a plan: `invalidate_coordinator_committed`. So today only a literal at a call of a seed without sessions is cheap, and only for roles that run late | Report both with the reuse table. Whether `resume` should plan under changed inputs is a design question for R1, not a task here |
| O6 | Build `conversation` (T4) now, or when that dimension is searched | Now: three hours, and it is the dimension where P10 found no reuse at all |
| O7 | This plan adds no row to `docs/index.md` or to the roadmap's routing list | The coordinator adds them on acceptance; T6 adds the result |

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Plan written as proposed, against `main` at `b399076b`. Ten probes, all zero spend, stand-in providers on a closed `PATH`, no provider or model call. The long-horizon seeds (`aa7ae4a0`) and the seed-set programs (`5449db80`) build and run on `main` as written; only the staged-authoring spelling is refused. Reader with character spans, no printer. 1,527 prototype mutants: one crash key, new, `graft`-only, on three programs, not closed by E1 (`588faf29`). Reuse on `milestones`: 0, 3 and 5 of 11 steps for a planner, coder and reviewer edit; all for a loop bound; no plan for an input change or under a committed agent turn. No code change |
