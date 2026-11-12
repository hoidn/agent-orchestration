# Lane D Stage 4: One Target

**Status: Plan, proposed 2026-11-12; not yet accepted.** This page plans stage 4 of [Lane
D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed):
one admitted `:target-dsl` for new source, one procedure regime, and the removal of the source forms
that are registered but refuse at build. It is a plan, not a contract, and not copy-safe guidance.
Behavior is owned by `specs/` and by [evaluated execution](../design/workflow_lisp_evaluated_execution.md);
until the tasks land, those documents and the code describe the checkout. No provider spend.

Approach: put every target gate in one table (no behavior change); delete the refused forms;
migrate every caller to 2.40 while the packaged library still sits at 2.35 (a newer caller may
import an older library, not the reverse); then, in one step, migrate the library, delete the older
procedure regime and narrow admission of new source to 2.40. Older headers stay readable only where
a recorded run needs them. What this makes harder is listed [below](#what-this-makes-harder).

Not planned here: the effect-placement rule, the iteration forms and the callable conventions
(stage 5, a separate design task); the two live-provider forms (owner decision 9); the 311 tracked
`.orc` files below 2.35, which already refuse.

## What Is True Today

Checked on `main` between `9bed89e5` and `5a0e3a89` (Phase 3b T2 merged while this was written) with:
`git grep` over `orchestrator/`; a dump of the form registry; a compile and closed build of every
exported workflow in all 421 tracked `.orc` files at 2.35–2.40, with externs made up from the
source, in an exported copy and again after a mechanical rewrite of the copy; 26 probe programs;
three programs run through the public command line before and after the rewrite; and the recorded
run roots of `tests/fixtures/declaration_pre_change/` resumed on a copy in which the dialect
switches answer as 2.40 does. Scripts and result files are session scratch in
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/plan-lane-d4/`
(`classify.py`, `migrate2.py`, `diff.py`, `probes.py`, `runsample.py`; the exported trees were deleted).

### Where behavior depends on the target

Six targets are admitted. 2.37 has no tracked source file; 2.36 has two.

| # | Difference | Where | Below | At and above | Kind |
| --- | --- | --- | --- | --- | --- |
| 1 | Header admitted at all | `contracts/closed_program/targets.py` (`SUPPORTED_TARGET_DSL_VERSIONS`), read by `workflow_lisp/syntax.py`, `closed/target.py`, the checker `check.py:307`; a second copy of the set in `workflow/run_ref/config.py:28` | — | 2.35–2.40 | Set membership |
| 2 | Evaluated execution floor, 2.35 | `closed/target.py`, `check.py`, `run_ref/wire.py`, `run_ref/path_contracts.py` | Refused (`workflow_execution_target_retired`) | All six | Always true above the floor |
| 3 | Local hooks (W3), 2.36 | `target_dsl_supports_local_hook_inference`, 21 uses in `modules.py`, `workflows.py`, `procedure_typecheck.py`, `procedure_specialization.py`, `compiler.py`, `expressions.py`, `repl_expr.py` | `let-proc` has one binding and explicit `:captures`; `std/improve` is `stdlib_modules/std/improve.orc`, five arguments | Several bindings, inferred captures ordered by name, one-site signature inference; `std/improve` resolves to `stdlib_modules/w3/std/improve.orc`, four arguments | **Dialect** for `std/improve` (measured: `procedure_arity_mismatch`); a superset for `let-proc` on the one file that builds |
| 4 | Parallel map, 2.37 | `parallel_map.py:53`, `check.py:3883` | Refused | Admitted | Monotone |
| 5 | Agent sessions, 2.38 | `agent_forms.py:30`, `type_env.py:150,471`, the `agent` registry row (`min_target_dsl_version`), `check_agents.py:34,172` | Refused; the names `agent` and `Agent` are free for user definitions | Admitted; the names are reserved | Monotone, except a source that defines those names |
| 6 | Confined `run-ref` children, 2.38 | `expressions.py:2067`, `run_ref/confined_config.py:205`, `check.py:4652` | Refused | Admitted; the config's target must equal the program's | Monotone |
| 7 | **Procedure regime**, 2.39 | `target_dsl_supports_effect_ceilings`, about 30 uses in `procedures.py`, `procedure_typecheck.py`, `procedure_specialization.py`, `functions.py`, `compiler.py`, `repl_expr.py`, `repl_inspect.py`, `cli/commands/repl.py`, `lsp/navigation.py`, `py/emit.py` | `:effects` is required and exact, with specialization exceptions; `:lowering inline\|private-workflow\|auto` is accepted, default `auto`; a procedure may become a private workflow callable, and an inline one called inside a loop may too | `:effects` is optional and a checked upper bound; `:lowering` is refused; always inline. Chosen by the *defining module's* target, so one build mixes both | **Dialect** |
| 8 | Finite source admission, 2.39 | `FINITE_SOURCE_ADMISSION_MIN_TARGET_DSL_VERSION` in `form_registry.py`; `expressions.py:1448`, `lsp/navigation.py:312` | Hand-written `__with-phase__` and `__generated-relpath-seed__` and the bare heads `with-phase` and `finalize-selected-item` are accepted | Refused (`private_form_not_admitted`, `stdlib_import_route_required`) unless they come from the packaged macro | **Dialect** (a restriction) |
| 9 | Import direction | `compiler.py:1335` | A module below 2.39 cannot import one at 2.39 or above; below 2.37 cannot import 2.37 or above | — | Follows from 4 and 7 |
| 10 | Phased provider delivery, 2.39 | `typecheck_effects.py:882`, `closed/effects.py:288`, `check.py:4608`, each with the literal set `{"2.39", "2.40"}` | Refused | Admitted | Monotone |
| 11 | Typed host input, 2.40 | `expressions.py:5411`, `typecheck_effects.py:81`, `py/trace.py:426`, `py/emit.py:1116` | `(request-input q)` types as `HumanReply` and refuses at build | Needs `:returns` or a prompt contract; builds | Monotone for programs that build |
| 12 | Python frontend default | `py/emit.py:270,395,1135`, `py/trace.py:426` | Default `TARGET` is 2.39; below it `proc` needs explicit effects and gets `:lowering inline` | — | Follows from 7 |
| 13 | Target as data | The closed program's `target` field (an input of the program digest); `contracts.py:897` (reusable-state fingerprint, used by `resume-or-start` only) | — | — | Label |
| 14 | Wire constants that look like targets | `closed/build.py:1648` writes `"2.35"` into every path-mode run-reference config and `check.py:4656` requires it; `provider_phased_delivery/ledger.py:940` writes `"2.23"` | — | — | Not gates; they stay |
| 15 | Gates below the floor | `providers/types.py:137` (2.23), `workflow/prompting.py:346` and `prompt_fragment_contract.py:825` (2.22), `workflow/provider_context.py:39` (2.31), `workflow/executable_ir.py:50` (2.32), `contracts.py:170,326,1080,1695` (`isinstance(target, str)`) | — | — | Always true for an admitted target |

Rows 4, 5, 6, 10 and 11 are monotone: a later target is a superset. Rows 3, 7 and 8 are a dialect
switch. Stage 3's unmerged branch `chore/lane-d3-chain` deletes `provider_context.py` and
`executable_ir.py` and trims `providers/types.py` and `prompt_fragment_contract.py`; re-run the grep
at Task 1's base and expect row 15 to be shorter.

### What the dialect switch costs, measured

The rewrite `migrate2.py` applies to every file at 2.35–2.39: the header becomes 2.40; each
`:lowering <mode>` clause goes (201 clauses; 184 `inline`, 13 `private-workflow`, 4 `auto`); below
2.39 each `:effects (...)` clause goes (231). Keeping `:effects` does not work: 12 workflows that
build today then fail `procedure_effect_ceiling_exceeded`, because the old exact declaration is not
an upper bound of what the new rule infers.

| 419 files at 2.35–2.39 | Same outcome | Same result, program structure changed | Outcome changed |
| --- | ---: | ---: | ---: |
| Tests, 380 | 352 | 7 | 21 |
| Other, 39 (6 are the packaged library) | 38 | 1 (`workflows/library/verified_iteration_drain/drain.orc`, after one hand edit) | 0 |

"Same outcome" means: every probed workflow builds to the same closed program once the `target`
label and source positions are removed, or refuses with the same diagnostic code, or typechecks as
before. Of 188 workflows that build today, 176 keep the same program, 8 change structure and 4
refuse. Of the 380 test files, 58 use a form this plan deletes; of the other 322, 302 need the
rewrite only, 7 change structure and 13 need a hand edit or exist only for the old regime:

- 10 write a private form by hand (`__generated-relpath-seed__`, or a local copy of a library
  macro that uses it): `current235/modules/**/imported_stdlib_*` (7 files),
  `modules/{valid,invalid}/generic_stdlib_composition*/**/entry.orc` (2),
  `valid/minimal_caller_review_revise_loop.orc`. The replacement is `(path/join-under T "name")`:
  the drain library builds with it, and a probe returns the same value for both, with no existence
  check at construction in either.
- 1 calls the five-argument `std/improve`: `current_examples/improve_experiment_proposal.orc`.
- 2 test the old regime only: `invalid/procedure_effect_mismatch.orc` (builds after the rewrite) and
  `invalid/procedure_private_boundary_invalid.orc`.

The 7 structure changes are procedures the old regime lowered as private workflows, by request, by
default, or by the loop rule: `generic_unions/concrete_outcome.orc`,
`guide_shapes/helper_{bound_in_loop,literal_argument}.orc`, `valid/generic_loop_union_same_module.orc`,
`modules/valid/generic_loop_union_cross_module/**/entry.orc`,
`modules/valid/imported_private_helper_local_union/**/{consumer,helper}.orc`.

Three guide shapes were run through `python -m orchestrator run` with their stand-in command, before
and after: exit code, result value and the stand-in's call log are identical in all three. The
program digest moves in all three. Effect identities are identical for the one whose structure is
unchanged and differ for the two whose structure changed (two specializations of `step` instead of
one).

Inline sources in tests are the larger part. Of 654 tracked test modules: 381 hold no source at an
older target; 138 need the header only; 69 need the header and clause removal; 22 are parametrized
over several targets; 44 name an old-regime rule or a target gate. In all: 923 headers at 2.35–2.39,
607 `:lowering` clauses (574 `inline`, 28 `private-workflow`, 5 `auto`) and 691 `:effects` clauses.
These were counted by pattern, not compiled.

### Recorded runs

`report`, the dashboard and `resume` load `closed_program.json` through the checker, which requires
an admitted `target`. Tried on a copy admitting 2.40 only, with the recorded 2.39 run root
`declaration_pre_change/provider_committed`: `report` fails `memo_inconsistent … (program_target)`
and `resume` fails `target_dsl_unsupported`. On a copy where rows 3, 7 and 8 answer as 2.40 does
for every header and the library is migrated, every workflow at 2.36–2.39 that builds today (25)
builds to the **same digest**, and so do 94 of the 163 at 2.35; 62 of the other 69 carry a
`:lowering` clause. On that copy the five recorded-run controls of
`tests/test_workflow_evaluated_edit_resume_baseline.py` that do not need the recording path pass
(2.38 and 2.39 run roots, never to be regenerated). The two recorded 2.35 run roots
(`tests/fixtures/provider_delivery_pre_change/`, `provider_delivery_file1/`) were not tried; their
sources hold no procedure.

### Forms

The registry holds 92 heads: 16 top-level definitions, 55 core special forms (37 of them pure
operators), 8 core effects, 2 library extensions and 11 with kind `TEMP_COMPILER_INTRINSIC`. That
kind means: the compiler elaborates the head itself although its design gives it to the library or
the runtime, and `remove_by` names the condition. The phrase "temporary compiler intrinsic" appears
in the rationale of 4 of the 11, which is where the count of 4 came from.

| Head | Kind | Probe at 2.40 (same at 2.35 unless noted) | Decision |
| --- | --- | --- | --- |
| `materialize-view`, `resource-transition`, `resume-or-start`, `run-provider-phase`, `produce-one-of` | Intrinsic | Build refuses, `closed_program_gap` with `form=<head>` | Delete |
| `finalize-selected-item` | Intrinsic, bare head kept for old targets | Typecheck refuses, `stdlib_import_route_required`; at 2.35 the build refuses, `closed_program_gap` | Delete, with its `std/resource` macro |
| `provider` | Intrinsic | Valid only inside `run-provider-phase` and `produce-one-of`; elsewhere `procedure_call_unknown` | Delete with them |
| `backlog-drain` | Library extension (`std/drain`) | All 4 valid fixtures refuse at build on `resource-transition` | Delete with `std/drain` |
| `defresource`, `deftransition` | Top-level | Typecheck; their only consumer is `resource-transition` | Delete |
| `with-phase` (bare head) | Intrinsic, bare head kept for old targets | Refuses, `stdlib_import_route_required`; builds at 2.35 | Delete the row in Task 4; the `std/phase` macro stays |
| `__with-phase__`, `phase-target` | Intrinsic | Build through the `std/phase` macro `with-phase`; hand-written `__with-phase__` refuses, `private_form_not_admitted` | Keep: four fixtures build with them |
| `__generated-relpath-seed__` | Intrinsic | Builds inside `review-revise-loop` and `phase-scope`; hand-written refuses | Keep; `path/join-under` could replace it (stage 5) |
| `with-live-providers`, `with-live-provider-peers` | Core effect | Build refuses, `closed_program_gap` | Keep (owner decision 9) |
| `request-input`, `run-ref`, `provider-bundle-path`, `agent`, `list/map-effect`, the 12 pure operators no shipped file builds (`cond`, `not`, `<=`, `print`, `some?`, `int/div`, `int/mod`, `float/abs`, `float/floor`, `float/round`, `string/empty?`, `symbol/name`) | — | Build | Keep |

Eleven rows go (92 to 81) and the intrinsic kind keeps three. Refused *options* of live forms are
not registry heads and stay for stage 5: bundle-mode `run-ref`, and `:session-artifact`, `:context`
and `:capture-context` on `provider-result`. The one-question `request-input` stops being reachable
in Task 4 and goes there.

Code that exists for the deleted forms: whole modules `typecheck_resume.py` (301 lines),
`typecheck_resource_view.py` (482), `resource.py` (468), `resource_stdlib.py` (40); most of
`typecheck_drain_phase.py` (240) and `phase_stdlib.py` (71); the library modules `std/drain.orc`
(398) and `std/resource.orc` (176); expression classes and their branches in `expressions.py`,
`wcc/elaborate.py`, `closed/effects.py`, `closed/preparation_check.py`, `definitions.py`,
`effects.py`; and adapters under `workflow_lisp/adapters/`, of which
`validate_review_findings_v1.py` is live (the `std/phase` review loop names it) and the others need
a reachability check. In tests, 35 modules mention a deleted form; `test_workflow_lisp_phase_stdlib.py`
(2,996 lines, 65 tests), `test_workflow_lisp_resource_stdlib.py` (891, 18),
`test_workflow_lisp_drain_stdlib.py` (316, 8) and `test_workflow_lisp_stdlib_form_migration.py`
(239, 6) hold most of it.

## Rulings

Decisions made while planning. R3 and R6 are the ones the coordinator should look at first.

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| R1 | **2.40 survives.** | It is the newest and a superset of 2.39; the tutorial, the seeds and the Python default are already one gate away | None found; 2.39 source becomes 2.40 by changing the header (26 files, all the same program) |
| R2 | **New source: 2.40 in every module of the graph, or a refusal.** `compile`, `run`, dry-run, REPL load, LSP analysis, typed imports, `run-ref` children and the Python frontend refuse any other header before anything is published. 2.35–2.39 refuse with the existing code (`workflow_execution_target_retired` for an entry, `target_dsl_unsupported` elsewhere) and a message that names the migration section of the guide and the tag of the last release that compiles it. No silent retargeting | A header that is accepted and ignored hides a change of procedure semantics. The pre-2.35 floor already works this way | An author with 2.35 source edits one line per file, plus the clauses; the message says how |
| R3 | **Recorded runs: the headers 2.35–2.39 stay readable as labels**, in two places only: the checker's table (so `report`, the dashboard and the monitor read existing run roots) and the rebuild that `resume`, `invalidate`, `input` and REPL attach do from a run's recorded sources. That rebuild uses the one remaining semantics; the existing digest comparison decides. Same digest: the run resumes. Different digest: `resume_program_changed`, as today. A recorded source the compiler no longer accepts (a `:lowering` clause, a bare `finalize-selected-item`) refuses with that diagnostic and one line naming the tag | Measured: a hard cut breaks `report` on every existing run root and strands the recorded run roots that Phase 3b forbids regenerating; with labels kept, all 25 programs at 2.36–2.39 and 94 of 163 at 2.35 keep their digest. Cost in code: a second set and one keyword on two call sites | A run in flight on 2.35 source with `:lowering` cannot resume after the upgrade; it needs the tagged release. If the rebuild admitted more than it should, the digest check still refuses, loudly |
| R4 | **The roadmap's order changes: callers first, library last.** Tests, catalog and documents go to 2.40 while the packaged library stays at 2.35; the library moves in the same task that deletes the old regime | Row 9: an older module cannot import a newer one, and the rule cannot be lifted while two regimes exist, because an old caller's exact `:effects` needs the callee's. A 2.40 caller importing the 2.35 library is today's state for every 2.39 file | If a caller is missed it stays at 2.35 and fails in Task 4, where it is easy to see |
| R5 | **The mechanical rewrite drops `:effects` below 2.39** as well as `:lowering`, except where a test is about a restriction | Measured: 12 failures if kept. Omission means inferred, so behavior is unchanged | The migrated library and catalog lose authored effect ceilings as documentation; Task 4 may write them back as checked bounds where they hold |
| R6 | **Frozen experiment kits are not edited, and the cut waits for them.** Task 4 does not merge while a kit with authorized, unspent runs declares an older target. Known: the seed-set study freezes hashes of programs at 2.39 (`experiments/orc_structural_search/seeds/`) and of `experiments/compare/score_functional.orc` at 2.35 | Editing a frozen file breaks its manifest; refusing its source stops an approved study | If the study has not frozen yet, re-freezing at 2.40 is cheaper (every experiment file is the same program after the rewrite) and Task 4 need not wait. The coordinator knows the study's state; the planner does not |
| R7 | **The 58 fixtures that use a deleted form go with it**; each deleted head keeps one `form_retired` test. The 2 old-regime fixtures and the five-argument `improve` fixture are deleted in Task 4, listed with the code they covered. The 10 hand-written private forms are rewritten with `path/join-under` where the test is about something else, and deleted where the private form is the subject | A fixture that tests a refusal the compiler can no longer produce guards nothing | A property tested only through a deleted fixture is lost; the ledger rule below makes the implementer name it |
| R8 | **Deleted heads refuse with `form_retired`**, through `RETIRED_FORMS` as `trial` does, each with its tag | One mechanism, already tested | None |
| R9 | **`:target-dsl` stays required.** | A missing header that means "current" would make the next language change silent | One line per file |
| R10 | **Package version 0.3.0 at the cut; the commit before it is tagged `v0.2.1`**, local, pushed by the coordinator. A local tag `archive/pre-one-target-2026-11-12` marks `main` before Task 1 | `specs/versioning.md`: a release that retires an executable target increments the minor version and the last release that executes it stays tagged | If the release tag is not wanted, the archive tag carries the same commit and the messages name it instead |
| R11 | **Headings and anchors that carry a target number stay** (`#agent-sessions-target-238` and the like); only body text that tells the reader to choose a target or describes the old regime changes | 45 tracked documents link to such anchors | Headings read as history; a later docs pass may rename them with alias anchors |
| R12 | **The wire constants of row 14 stay as they are**, renamed in code so they do not read as targets | Changing them changes recorded config bytes | None |

Alternatives to R2 and R3, one line each: accept every header and treat it as 2.40 (smallest code,
fails the exit test and hides the regime change); refuse older headers everywhere including resume
and `report` (simplest rule, breaks every existing run root and the Phase 3b fixtures); keep the old
regime for resume only (keeps every old run resumable, deletes nothing).

## The Versioning Rule

The roadmap asks, at this step, "whether an identity-affecting change adds a target or breaks
retained runs". Answer, written into `specs/versioning.md` by Task 4 as a section "Targets and
identity":

1. One target is admitted for new source. `:target-dsl` names the source language, nothing else.
2. A change to what existing source means, or to whether it compiles, adds a target; the same change
   migrates all tracked source and removes the previous target from new-source admission. Two source
   dialects never coexist in the compiler.
3. A change that moves an identity without changing what source means (a program digest, an effect
   identity, a memo row, the checked representation) **adds no target**. It either keeps recorded
   runs resumable, and proves it with a run root recorded before the change and never regenerated
   (the `tests/fixtures/declaration_pre_change/` pattern), or it breaks them: resume refuses through
   the digest check, the package minor version increments, the last release that resumes them is
   tagged, and the change gets a row in the spec's compatibility table.
4. A removed target stays readable as a recorded-run label until its removal condition.

| Label | Kept for | Removal condition |
| --- | --- | --- |
| 2.38, 2.39 | Recorded run roots under `tests/fixtures/declaration_pre_change/`; run roots on operators' disks | The first release after 0.3.0 that breaks resume of 0.2.x runs under rule 3; the fixtures then become refusal fixtures |
| 2.35 | `tests/fixtures/provider_delivery_pre_change/`, `provider_delivery_file1/`; run roots on operators' disks | The same |
| 2.36, 2.37 | Run roots on operators' disks only; no tracked fixture | The same, or earlier by a ledger entry |

## The Behavior Comparison

For every file a task rewrites, before against after, with `classify.py` and `diff.py`:

- **Must be identical:** for each exported workflow, built or refused; for a refusal, the first
  diagnostic code (the scripts do not compare positions: removing a clause can remove a line); for
  a build, the closed program with the `target`
  field and positions removed, unless the file is on the structure list above. For the catalog, the
  library and every file on the structure list that has a stand-in: exit code, result value and the
  stand-in's call log from a public `run` (`runsample.py`).
- **Expected to move:** the program digest of every rewritten source, because `target` is a digest
  input; run-reference configs that embed such a program; effect identities of the files on the
  structure list. Nothing else. An effect identity that moves in a file off the list is a finding.
- **Must not move at all:** anything compiled from a source the task did not edit, including every
  file already at 2.40 and every recorded run root.

Stage 3's three invariant files (corpus snapshot, compile of every tracked `.orc`, run-reference
program digests) must be byte-identical across Tasks 1 and 2, with one listed exception in Task 2.
Across Tasks 3 and 4 they are compared after the same normalization.

## Global Constraints

- Deletions, the rewrite, the table and the admission change only. No change to what a 2.40 program
  means. The two live-provider forms are not edited.
- Off limits: frozen files under `experiments/` (R6); the recorded run roots
  `tests/fixtures/declaration_pre_change/`, `provider_delivery_pre_change/` and
  `provider_delivery_file1/` (7 `.orc` files, so Task 3b rewrites 315 of the 322); `.orc` files below
  2.35; untracked files; `.worktrees/` of other sessions. `README.md`, the drafting guide,
  `specs/cli.md` and `specs/providers.md` have uncommitted edits from another session: rebase, do
  not overwrite.
- A test goes only with the code or rule it covered; the ledger lists both. No test of kill, resume,
  recovery, memo durability, checker soundness, result validation, security or the command line end
  to end is removed. Tests assert behavior, never prompt text.
- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`; no
  `git stash`. Separate worktrees; `PYTHONPATH` set to the working tree;
  `experiments/thread_m/no_provider` first on `PATH`; `mkdir -m 700` for any basetemp; long runs in
  tmux from an existing session; check `df` before a full suite.
- **Gate, for every commit:** no test outside the four worktree-artifact ids of the [test
  baseline](../reports/2026-11-11-test-baseline.md) fails. During work: the task's narrow run, then
  `pytest -q -n 16 --dist=worksteal --sample 10`; before each merge to `main`, the same without
  `--sample`. `pytest --collect-only` on each test module added or edited.

## Tasks

Task 0, then Task 1. Then Tasks 2, 3a, 3b and 3c run in four worktrees on disjoint files: Task 2
owns every tracked file that matches the deleted-form pattern (an opening parenthesis followed by
`materialize-view`, `resource-transition`, `resume-or-start`, `run-provider-phase`, `produce-one-of`,
`finalize-selected-item`, `backlog-drain`, `defresource` or `deftransition`, or an import of
`std/drain` or `std/resource`); Task 3 skips those. Task 4 needs
1 to 3 on `main` and R6 satisfied. Task 5 last.

### Task 0: Tags, baselines, scripts (0.5 day)

- [ ] Create the local annotated tag `archive/pre-one-target-2026-11-12`; record the suite result
      and the collected count. Add this plan to `docs/index.md` and the roadmap's routing list.
- [ ] Copy the planner's scripts into the task's scratch. Make stage 3's three invariant files, and
      the outcome table: `git archive HEAD orchestrator $(git ls-files '*.orc') | tar -x -C <base>`,
      then `PYTHONPATH=<base> python classify.py <base> base.json`. Expect 421 files; 188 built.
- [ ] Record `python -m orchestrator report --run-id <id>` for the three relocatable run roots of
      `declaration_pre_change/`, the two 2.35 run roots, and one fresh run killed after its first
      command (kept for Task 5).

### Task 1: One table (1.5 days; about −150, +90 lines)

`orchestrator/contracts/closed_program/targets.py` gets one mapping from target to the set of
capabilities it admits (`local_hooks`, `parallel_map`, `run_ref_confined`, `agent_sessions`,
`procedure_ceilings`, `finite_source_admission`, `phased_delivery`, `typed_host_input`) and one
lookup. Every site of rows 3 to 12 calls it: the `target_dsl_supports_*` functions, the function in
`syntax.py:751`, `FINITE_SOURCE_ADMISSION_MIN_TARGET_DSL_VERSION`, the `agent` row's
`min_target_dsl_version`, the literal sets and `== "2.40"` comparisons, the Python frontend's
checks, and the copy of the set in `run_ref/config.py`. Row 15's comparisons are removed where the
caller always passes an admitted target. Row 14's constants get names that say "wire".

- [ ] One test: each row of the table is a superset of the one before; no file under
      `orchestrator/` other than `targets.py` compares a target with a version literal or tuple. See
      it fail first.
- [ ] Checks: the three invariant files and `base.json` byte-identical; narrow run
      `tests/test_workflow_lisp_*target*.py tests/test_workflow_lisp_source_floor.py
      tests/test_workflow_lisp_agent_constructor.py tests/test_workflow_lisp_parallel_map*.py
      tests/test_workflow_run_ref_config.py tests/test_workflow_python_*.py`.
- Reviewer: does `run_ref/config.py` still import in the isolated subprocess of
  `tests/test_workflow_run_ref_config.py`; is any comparison left that the test's pattern misses
  (`getattr(..., "TARGET", "2.39")`, tuple compares built from `split(".")`).

### Task 2: Delete the refused forms (4 days; about −4,500 production and library lines, −4,100 fixture lines, −3,500 test lines)

Remove the heads marked Delete in the form table except bare `with-phase`: registry rows, parsers,
expression classes, typecheck, the WCC and closed-build branches, `defresource` and `deftransition`
with their catalog, `std/drain.orc` and `std/resource.orc`, and each adapter module that no
surviving form, library module or tracked command manifest names. Add the heads to `RETIRED_FORMS`
with this plan's tag. The 50 fixtures below 2.35 that use these heads already refuse by their
header; one goes only if the test that reads it goes.

- [ ] First re-run the reachability scan per adapter and per expression class; delete only what the
      scan clears. `validate_review_findings_v1.py` stays.
- [ ] Add one `form_retired` case per deleted head and the removed modules' rows to
      `tests/test_retired_executors_removed.py`; see them fail first. Trim
      `test_each_selected_effect_outside_the_release_is_a_located_gap` to the forms that remain.
- [ ] Documents, in this task: the guide's sections 13.1, 13.3, 13.4, 13.5 and 13.6 become one
      paragraph that names the removed forms and `form_retired`; the paragraph of section 2A that
      lists unavailable forms and the two bullets under "Runtime-Native Authoring Direction" lose
      them; sections 11 and 12 lose text that describes resource transitions as authorable. The
      capability matrix rows for `backlog-drain` and resource transitions say Removed with the tag.
      `specs/state.md` and `specs/dsl.md`: sentences that present these forms as current. The
      designs `workflow_lisp_stdlib_lowering.md` and `workflow_lisp_runtime_native_drain_authoring.md`
      become Historical with a scope notice, after a check that no current rule lives only there.
- [ ] Checks: `base.json` against the new table differs only in rows whose refusal was
      `closed_program_gap` for a deleted form or that used one (expected: 58 test files, 2 library
      modules); the corpus snapshot differs only in such rows; run-reference digests identical.
      Narrow run: `tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_closed_program_effects.py
      tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lsp_*.py
      tests/test_workflow_lisp_route_readiness.py tests/test_first_hour_e2e.py`.
- Reviewer: a live path through a "deleted" adapter (command manifests under `workflows/` name
  `apply_resource_transition`); `review-revise-loop`, `with-phase` and `phase-scope` still build
  (four fixtures); the `std/context` records still import; no test of a surviving property went with
  a fixture.

### Task 3: Migrate callers to 2.40 (8.5 days in three parts; net about −1,500 lines)

The packaged library stays at 2.35 here. The three fixtures of R7 are left for Task 4. In the 44
modules that name an old-regime rule or a target gate, 3c rewrites the tests that are not about
that rule and leaves the others at their target for Task 4.

- **3a, catalog and documents (1.5 days).** The 33 non-library files outside tests, less the frozen ones:
  `workflows/examples/`, `workflows/library/` (in `drain.orc` the seed becomes
  `(path/join-under DrainSummaryPath "drain-summary.json")`), non-frozen `experiments/`; the source
  examples in `README.md`, the tutorial, the library reference and the guide (12 headers below
  2.40), with the guide's "complete 2.35 recipe" body at 2.40 under its present anchor. Python
  examples with `TARGET = "2.38"` move to 2.40. Checks: the behavior comparison with public runs for
  every example that has stand-ins; `tests/test_first_hour_e2e.py tests/test_authoring_check_kit.py
  tests/test_workflow_lisp_closed_program_corpus.py`; one orchestrator smoke run of a catalog example.
- **3b, test `.orc` fixtures (2 days).** `migrate2.py` over the files Task 2 does not own and that
  are not recorded run roots (315); the 7 structure changes and the 10 private-form rewrites by
  hand, each with its test's expected identities or digests updated and listed. Checks: the
  behavior comparison (expected: 295 same, 7 on the structure list); `tests/test_workflow_lisp_guide_programs.py` and the modules that read
  each fixture directory.
- **3c, inline sources in tests (5 days; may be split in two worktrees by file list).** The same rewrite in
  the 207 modules of the header and clause classes; the 22 parametrized modules keep one case at
  2.40 and the ledger lists each removed parameter. Checks: each edited module run before and after
  with the same pass count, less the listed parameters; a digest or identity literal that changes
  must belong to a rewritten source.
- Reviewer: a test that still passes because it stopped testing anything (an assertion on a
  refusal that the rewrite turned into a different refusal); a `:effects` clause dropped from a test
  whose subject is the restriction; expected values edited without a matching entry in the list.

### Task 4: The cut (4 days; about −800 production lines, −1,200 test lines, −250 document lines)

One branch, merged as one, because no intermediate state is green: the library cannot move before
the old regime goes (R4) and the old regime cannot go while the library uses it.

| Edit | Change |
| --- | --- |
| `stdlib_modules/` | The rewrite on `std/{context,phase,improve}.orc`; `w3/std/improve.orc` becomes `std/improve.orc` and the five-argument module and the root selection in `modules.py:320` go |
| Rows 3, 7, 8, 9 of the difference table | The older branch of each switch: mandatory exact `:effects`, `:lowering` and `ProcedureLoweringMode` other than inline, the private-workflow lowering in `procedure_specialization.py` and its two consumers in `closed/`, the loop override, single-binding `let-proc`, hand-written private forms, the bare `with-phase` row, the import direction rule, the one-question `request-input` |
| Admission | `targets.py` names the current target and the recorded-run labels (R3). New-source entry points require the current target in every module; the two rebuild call sites (`cli/commands/evaluated.py:194`, `cli/commands/repl.py:187`) admit the labels. The refusal messages of R2 |
| `orchestrator/py/` | Default and only `TARGET` 2.40; the explicit-effects branch goes |
| Tests | Delete the E class items that test a removed rule and the three fixtures of R7; keep one test per label that a 2.3x header refuses on each public entry point and that a recorded run at that label still reports and resumes |
| `specs/versioning.md` | The section "Targets and identity" above; the gating summary's paragraphs on 2.36, 2.38 and 2.39 say what each capability is, not which target selects it; the retained-label table |
| `specs/dsl.md`, `specs/cli.md`, `specs/io.md`, `specs/state.md` | "Targets 2.35–2.40" becomes the current target where the text is about new source; the REPL and `resume` text states R3 |
| Guide | Section 2 and the opening of 2A become one paragraph; "Procedure contracts at target 2.39" is the procedure contract, without the paragraph on imported 2.35–2.38 definitions and without the 83-line older example; `let-proc` text loses the 2.35 form; "Target 2.35 explicit inputs" goes here and in the library reference; a short section "Migrating from an older target" that the refusal message links to |
| Others | `docs/index.md` clarifications, the capability matrix's target sentences, the Python guide's default, `pyproject.toml` 0.3.0 and the tag `v0.2.1` on the commit before |

- [ ] First the two tests of R2 and R3, seen to fail: every public entry point refuses a 2.39
      source graph without writing a build or run directory; the recorded run roots report and
      resume.
- [ ] Checks: the behavior comparison over the library's importers (expected: all the same program);
      the registry holds 81 heads and the table test of Task 1 holds with the three dialect
      capabilities gone; `tests/test_workflow_evaluated_edit_resume_baseline.py
      tests/test_workflow_evaluated_declaration_resume.py tests/test_workflow_evaluated_resume_*.py
      tests/test_resume_command.py tests/test_workflow_evaluated_run_ref*.py
      tests/e2e/test_e2e_workflow_evaluated_run_ref.py tests/test_workflow_lisp_lsp_*.py
      tests/test_workflow_evaluated_repl*.py tests/test_workflow_python_*.py`; one orchestrator
      smoke run; the full suite.
- Reviewer: an entry point that still accepts an older header (typed imports through
  `--imported-workflow-bundles-file`, a `run-ref` child compiled from a pinned commit, `py run`);
  a rebuild path that admits labels for a *new* run; a 2.35 run root without `:lowering` that no
  longer resumes; a program at 2.40 whose digest moved (none may).

### Task 5: Final verification (0.5 day)

- [ ] Exit test: `git grep -nE '"2\.3[5-9]"' -- orchestrator` finds the label table and the wire
      constants only; a new program at each of 2.35–2.39 refuses on `compile` and `run` with the
      migration message; the retained-label table in `specs/versioning.md` matches the code.
- [ ] End to end: `resume` completes Task 0's killed run if its digest is unchanged, or refuses with
      `resume_program_changed` and the tag; `report` on Task 0's run roots prints what it printed.
      The tutorial's pipeline is compiled, run, killed and resumed afresh.
- [ ] Full suite within the gate. Ledger: lines removed per task against the tag, collected items
      before and after, every removed test and fixture with the code or rule it covered, every
      expected value that changed.

## Size

| Task | Days | Net lines (estimate) | Parallel with |
| --- | ---: | ---: | --- |
| 0 Tags, baselines | 0.5 | 0 | — |
| 1 One table | 1.5 | −60 | — |
| 2 Refused forms | 4 | −12,000 | 3a, 3b, 3c |
| 3a Catalog and documents | 1.5 | −100 | 2, 3b, 3c |
| 3b Test fixtures | 2 | −500 | 2, 3a, 3c |
| 3c Inline test sources | 5 | −900 | 2, 3a, 3b |
| 4 The cut | 4 | −2,250 | — |
| 5 Final verification | 0.5 | 0 | — |
| **Total** | **19** | **about −15,800** | Elapsed about 11.5 days with four worktrees; 10.5 if 3c is split in two |

The whole-module figures are measured; the rest are estimates from function spans and pattern
counts. The ledger records the real figures.

## What This Makes Harder

- Compiling or starting a run from 2.35–2.39 source. Fallback: `git worktree add ../orc-0.2 v0.2.1`.
- Resuming a run recorded from 2.35 source that uses `:lowering`, a bare `finalize-selected-item` or
  the five-argument `improve`: only the tagged release resumes it.
- Pinning a `run-ref` child to a commit whose source declares an older target.
- A procedure with its own call frame. The only boundary left is `defworkflow` with `call`, whose
  inputs and result must be transportable.
- Exact effect declarations. `:effects` is an upper bound; a procedure that must do exactly one
  thing needs a test, not a clause.
- Resource transitions, reusable phase state, materialized views and the drain library as source
  forms. A later design starts from the tag and the Historical documents, on evaluated execution.
- The next language change: rule 2 makes it a migration of all tracked source in the same change,
  with no period in which two dialects compile.
- Reading the guide's history from its headings, which keep target numbers that no longer select
  anything (R11).

## Not Verified While Planning

- No task was tried. The "one semantics" measurement changed three functions in a copy; the real
  deletion touches about 55 sites. The suite was not run on any copy.
- How many tests fail when the old regime goes. The E class (44 modules) was found by pattern; which
  of its tests are about a removed rule was not read.
- Inline test sources were counted, not compiled. The 302 "rewrite only" figure is for `.orc` files.
- In 168 of the 421 files every probed entry refuses in both copies with the same code (made-up
  externs, an intended error, a form that has no closed form). For those, "same outcome" means the
  same first diagnostic code only.
- That each of the 63 registry heads not probed alone builds: the evidence is a shipped file that
  uses the head and builds, not a minimal program.
- Line estimates for Task 2 beyond whole modules, and which adapters are reachable.
- That `let-proc` with explicit `:captures` behaves the same under the newer rule: one built file.
- That effect identities never depend on the target label: one run.
- A pre-2.38 source that defines `agent` or `Agent` (row 5) was not probed.
- Whether the seed-set study has frozen its hashes or spent its tranches (R6), and whether other
  kits under `experiments/` launch new runs.
- `report --format json`, the dashboard and the monitor on old labels beyond the checker's target
  test; `invalidate` and `input` on a recorded run at an older label.
- The 311 tracked `.orc` files below 2.35 and the tests that read them.
- `orchestrator/prompt_scaffold_render.py:282` writes a 2.27 header; not analysed.
- Whether a document test pins a sentence Tasks 2 to 4 edit.

## Ledger

| Date | Entry |
| --- | --- |
