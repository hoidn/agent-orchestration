# Lane D Stage 4: One Target

**Status: Plan, revised 2026-11-12 after an independent review (accept with changes: 1 blocker, 6
major, 12 minor) and the coordinator's rulings on it; not yet accepted.** This page plans stage 4 of
[Lane D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed):
one admitted `:target-dsl`, one procedure regime, and the removal of the source forms that are
registered but refuse at build. It is a plan, not a contract, and not copy-safe guidance. Behavior
is owned by `specs/` and by [evaluated execution](../design/workflow_lisp_evaluated_execution.md);
until the tasks land, those documents and the code describe the checkout. No provider spend.

Approach: delete the refused forms; migrate every caller to 2.40 while the packaged library still
sits at 2.35 (a newer caller may import an older library, not the reverse); re-record the five
Phase 3b run roots at 2.40; migrate the library; then delete the older procedure regime and every
target gate and admit 2.40 only. Older targets remain as labels that `report`, the dashboard and the
monitor can read. **A run in flight at an older target cannot be continued after the cut except
with the tagged release.** What this makes harder is listed [below](#what-this-makes-harder).

Not planned here: the effect-placement rule, the iteration forms and the callable conventions
(stage 5, a separate design task); the two live-provider forms (owner decision 9); the 311 tracked
`.orc` files below 2.35, which already refuse.

## What Is True Today

Checked on `main` at `79f04947` (stage 3 and Phase 3b T2 and T5 are merged) with: `git grep` over
`orchestrator/`; a dump of the form registry; a compile and closed build of every exported workflow
in all 421 tracked `.orc` files at 2.35–2.40, with externs made up from the source, in an exported
copy and again after a mechanical rewrite of the copy; 26 probe programs; three programs run through
the public command line before and after the rewrite; and a recording of the five Phase 3b run
roots at 2.40 with the build `c3bdd14d`. Scripts and result files are session scratch in
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/plan-lane-d4/`
(`classify.py`, `migrate2.py`, `diff.py`, `probes.py`, `runsample.py`, `record_240.py`; the exported
trees were deleted). The reviewer re-ran the measurements on its own export and they held.

### Where behavior depends on the target

Six targets are admitted. 2.37 has no tracked source file; 2.36 has two.

| # | Difference | Where | Below | At and above | Kind |
| --- | --- | --- | --- | --- | --- |
| 1 | Header admitted at all | `contracts/closed_program/targets.py` (`SUPPORTED_TARGET_DSL_VERSIONS`), read by `workflow_lisp/syntax.py` (12 callers of `build_syntax_module`), `closed/target.py`, the checker `check.py:307` | — | 2.35–2.40 | Set membership |
| 2 | Evaluated execution floor, 2.35 | `closed/target.py`, `check.py`, `run_ref/wire.py`, `run_ref/path_contracts.py` | Refused (`workflow_execution_target_retired`) | All six | Always true above the floor |
| 3 | Local hooks (W3), 2.36 | `target_dsl_supports_local_hook_inference`, 21 lines in `modules.py`, `workflows.py`, `procedure_typecheck.py`, `procedure_specialization.py`, `compiler.py`, `expressions.py`, `repl_expr.py` | `let-proc` has one binding and explicit `:captures`; `std/improve` is `stdlib_modules/std/improve.orc`, five arguments | Several bindings, inferred captures ordered by name, one-site signature inference; `std/improve` resolves to `stdlib_modules/w3/std/improve.orc`, four arguments | **Dialect** for `std/improve` (measured: `procedure_arity_mismatch`); a superset for `let-proc` on the one file that builds |
| 4 | Parallel map, 2.37 | `parallel_map.py:53`, `check.py:3883` | Refused | Admitted | Monotone |
| 5 | Agent sessions, 2.38 | `agent_forms.py:30`, `type_env.py:150,471`, the `agent` registry row (`min_target_dsl_version`), `check_agents.py:34,172` | Refused; the names `agent` and `Agent` are free for user definitions | Admitted; the names are reserved | Monotone, except a source that defines those names (no tracked file does) |
| 6 | Confined `run-ref` children, 2.38 | `expressions.py:2067`, `run_ref/confined_config.py:205`, `check.py:1102` and `4652` (the child's and the config's target equal the program's) | Refused | Admitted | Monotone |
| 7 | **Procedure regime**, 2.39 | `target_dsl_supports_effect_ceilings`, 39 lines in `procedures.py`, `procedure_typecheck.py`, `procedure_specialization.py`, `functions.py`, `compiler.py`, `repl_expr.py`, `repl_inspect.py`, `cli/commands/repl.py`, `lsp/navigation.py`, `py/emit.py` | `:effects` is required and exact, with specialization exceptions; `:lowering inline\|private-workflow\|auto` is accepted, default `auto`; a procedure may become a private workflow callable, and an inline one called inside a loop may too | `:effects` is optional and a checked upper bound; `:lowering` is refused; always inline. Chosen by the *defining module's* target, so one build mixes both | **Dialect** |
| 8 | Finite source admission, 2.39 | `FINITE_SOURCE_ADMISSION_MIN_TARGET_DSL_VERSION` in `form_registry.py`; `expressions.py:1450`, `lsp/navigation.py:314` | Hand-written `__with-phase__` and `__generated-relpath-seed__` and the bare heads `with-phase` and `finalize-selected-item` are accepted | Refused (`private_form_not_admitted`, `stdlib_import_route_required`) unless they come from the packaged macro | **Dialect** (a restriction) |
| 9 | Import direction | `compiler.py:1335`, used at `1350`, `3545–3613` (source imports and typed-workflow calls, `evaluated_execution_target_direction_invalid`); `compiler.py:3455` (two owners of one source must declare the same target) | A module below 2.39 cannot import one at 2.39 or above; below 2.37 cannot import 2.37 or above | — | Follows from 4 and 7 |
| 10 | Phased provider delivery, 2.39 | `typecheck_effects.py:882`, `closed/effects.py:288`, `check.py:4608`, each with the literal set `{"2.39", "2.40"}` | Refused | Admitted | Monotone |
| 11 | Typed host input, 2.40 | `expressions.py:5411`, `typecheck_effects.py:81`, `py/trace.py:426`, `py/emit.py:1116` | `(request-input q)` types as `HumanReply` and refuses at build | Needs `:returns` or a prompt contract; builds | Monotone for programs that build |
| 12 | Python frontend default | `py/emit.py:270,395,1135`, `py/trace.py:426` | Default `TARGET` is 2.39; below it `proc` needs explicit effects and gets `:lowering inline` | — | Follows from 7 |
| 13 | Target as data | The closed program's `target` field (an input of the program digest); `contracts.py:897` (reusable-state fingerprint, used by `resume-or-start` only); `experiments/orc_structural_search/candidates.py:123` (`:target-dsl` is a frozen head of a candidate) | — | — | Label |
| 14 | Wire values that look like targets | `closed/build.py:1648` writes `"2.35"` into every path-mode run-reference config and `check.py:4656` requires it, both through the constant `EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION`; `run_ref/config.py:27` (the same default) and its own set at line 28, checked when a config is built (456) and decoded (596); `provider_phased_delivery/ledger.py:940` writes `"2.23"`; `prompt_scaffold_render.py:282` writes a 2.27 header into a scaffold file | — | — | Not gates; they stay (R12) |
| 15 | Gates below the floor | `workflow/prompting.py:346` (2.22); `contracts.py:172,328,1080,1695` (`isinstance(target, str)`) | — | — | Always true for an admitted target |

Rows 4, 5, 6, 10 and 11 are monotone: a later target is a superset. Rows 3, 7 and 8 are the only
dialect switches.

### What the dialect switch costs, measured

The rewrite `migrate2.py` applies to every file at 2.35–2.39: the header becomes 2.40; each
`:lowering <mode>` clause goes (201 clauses; 184 `inline`, 13 `private-workflow`, 4 `auto`); below
2.39 each `:effects (...)` clause goes (231). Keeping `:effects` does not work: 12 workflows that
build today then fail `procedure_effect_ceiling_exceeded`. All 12 are procedures that take a hook
(a procedure reference, a workflow reference or a generic function): the old clause listed the
body's own effects, and the newer ceiling is checked on each specialization, hook included.

| 419 files at 2.35–2.39 | Same outcome | Same result, program structure changed | Outcome changed |
| --- | ---: | ---: | ---: |
| Tests, 380 (7 of them sources of recorded run roots) | 352 | 7 | 21 |
| Other, 39 (6 are the packaged library) | 38 | 1 (`workflows/library/verified_iteration_drain/drain.orc`, after one hand edit) | 0 |

"Same outcome" means: every workflow builds to the same closed program once the `target` label and
the `@` provenance are removed, or refuses with the same first diagnostic code, or typechecks as
before. Of 191 workflows that build today, 179 keep the same program, 8 change structure and 4
refuse. Six rows are compiler defects and are never counted as a match: five workflows fail
`compiler_defect` today (`valid/workflow_refs_same_file.orc` twice,
`modules/valid/workflow_refs/**/imported_entry.orc`,
`valid/library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper.orc`,
`modules/valid/generic_stdlib_composition/**/entry.orc`) and the rewrite adds one
(`invalid/procedure_private_boundary_invalid.orc`, deleted in Task 4b).

Of the 380 test files, 58 use a form this plan deletes and 7 are recorded sources; of the other 315,
295 need the rewrite only, 7 change structure and 13 need a hand edit or exist only for the old
regime:

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
and after: exit code, standard output, result value, the stand-in's call log and the input parts of
every effect are identical. The program digest moves in all three. Effect identities are identical
for the one whose structure is unchanged and differ for the two whose structure changed (two
specializations of `step` instead of one). The reviewer's probes add: a 2.40 caller builds to the
same digest with the 2.35 library and with the migrated one (46 importer entries); `:effects`
clauses are not in the program digest.

### Sources whose target is a parameter

The counts above are of literal headers. These are outside them:

- 10 fixtures in `tests/fixtures/workflow_lisp/closed_program/` declare `(:target-dsl "TARGET")`;
  `tests/workflow_lisp_closed_program_helpers.py:14` substitutes
  `EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION`, which is `"2.35"`. They hold 14 `:lowering` and 14
  `:effects` clauses.
- 22 test modules build sources only through that helper, the constant or a `{TARGET}` placeholder
  and hold no literal older header; 16 modules use the constant, 39 times. Tests use it to mean "a
  target that builds", while the code uses it for the floor and for the wire value of row 14.
- Outside `tests/`: `experiments/orc_gp_example/grammar.py:29` generates 2.39 source, and
  `tests/experiments/test_orc_structural_search_seeds.py:70` asserts that each seed declares 2.39.

Of 655 tracked test modules, 25 mention a deleted form or its code (they hold 240 older headers and
554 tests; `test_workflow_lisp_procedures.py` alone has 94 headers and one mention). Of the other
630: 360 build no source at an older target; 133 need the header only; 58 the header and clause
removal; 20 are parametrized over several targets; 38 name an old-regime rule or a target gate; 21
use a parameter only. In all tests: 923 literal headers at 2.35–2.39, 607 `:lowering` clauses (574
`inline`, 28 `private-workflow`, 5 `auto`) and 691 `:effects` clauses. These are pattern counts.

### Recorded runs

- `resume`, host `input` and REPL attach rebuild the program from the **current workspace files** at
  the recorded paths (`cli/commands/evaluated.py:142,172`, `repl.py:183`); nothing is snapshotted.
  Phase 3b's `--accept-changes` compiles an edited workspace on the same path. `invalidate` does not
  rebuild; it loads the stored program and rewrites the memo (`cli/commands/invalidate.py:29`).
- `report`, the dashboard and `resume` load `closed_program.json` through the checker, which
  requires an admitted `target`. On a copy admitting 2.40 only, `report` on the recorded 2.39 run
  root `declaration_pre_change/provider_committed` fails `memo_inconsistent … (program_target)`.
- The reviewer's probe: with labels kept and one semantics, the same root resumes; with only the
  workspace header changed to 2.40 it refuses `resume_program_changed`, because `target` is a digest
  input. So keeping older headers compilable on the rebuild path helps only a workspace that was not
  migrated, and admits edited older-target source through `--accept-changes`.
- **`c3bdd14d` records all five cases at 2.40.** With the scaffold of `proof/phase-3b`
  (`scaffolds/record_fixtures.py` at `3662a26b`), its three sources changed to 2.40 and its recording
  path moved into scratch, the build `c3bdd14d` compiled and ran `provider_committed`,
  `agent_turns_committed`, `agent_turn_pending`, `phased_committed` and `phased_pending`, kill cuts
  included. Assembled as the fixture directory in a copy of `79f04947`, with the recording path of
  `tests/test_workflow_evaluated_edit_resume_baseline.py` pointed at the scratch path, all 39 tests
  of that module and of `tests/test_workflow_evaluated_declaration_resume.py` pass, unedited. Two
  things the task must do that the tests do not: release the phased transport reservations
  (`scaffolds/clean_phased_reservations.py`), and remove the two revoked `/tmp/orc-peer-*`
  directories, or the pending-phased test skips on the recording host.
- The two 2.35 run roots (`tests/fixtures/provider_delivery_pre_change/`, `provider_delivery_file1/`)
  were written by packages that predate 2.40 (2026-10-13; 2.40 was admitted on 2026-10-22), so they
  cannot be re-recorded at 2.40. Their two tests
  (`test_resume_reuses_the_checked_in_pre_change_provider_commit`,
  `test_resume_reuses_the_frozen_file1_provider_commit_and_selects_file2` in
  `tests/test_workflow_evaluated_resume_replay.py`) resume them. The `file/2` delivery rendering
  landed on 2026-10-16, before 2.40: no 2.40 run holds a commit without the `delivery` part or with
  `file/1`.

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
| `defresource`, `deftransition` | Top-level | Modules that declare them typecheck; their only consumer is `resource-transition` | Delete |
| `with-phase` (bare head) | Intrinsic, bare head kept for old targets | Refuses, `stdlib_import_route_required`; builds at 2.35 | Delete the row in Task 4b; the `std/phase` macro stays |
| `__with-phase__`, `phase-target` | Intrinsic | Build through the `std/phase` macro `with-phase`; hand-written `__with-phase__` refuses, `private_form_not_admitted` | Keep: fixtures build with them |
| `__generated-relpath-seed__` | Intrinsic | Builds inside `review-revise-loop` and `phase-scope`; hand-written refuses | Keep; `path/join-under` could replace it (stage 5) |
| `with-live-providers`, `with-live-provider-peers` | Core effect | Build refuses, `closed_program_gap` | Keep (owner decision 9) |
| `request-input`, `run-ref`, `provider-bundle-path`, `agent`, `list/map-effect`, the 12 pure operators no shipped file builds (`cond`, `not`, `<=`, `print`, `some?`, `int/div`, `int/mod`, `float/abs`, `float/floor`, `float/round`, `string/empty?`, `symbol/name`) | — | Build | Keep |

Eleven rows go (92 to 81) and the intrinsic kind keeps three. Refused *options* of live forms are
not registry heads and stay for stage 5: bundle-mode `run-ref`, and `:session-artifact`, `:context`
and `:capture-context` on `provider-result`. The one-question `request-input` stops being reachable
in Task 4b and goes there.

Code that exists for the deleted forms: whole modules `typecheck_resume.py` (301 lines),
`typecheck_resource_view.py` (482), `resource.py` (468), `resource_stdlib.py` (40); most of
`typecheck_drain_phase.py` (240) and `phase_stdlib.py` (71); the library modules `std/drain.orc`
(398) and `std/resource.orc` (176); expression classes and their branches in `expressions.py`,
`wcc/elaborate.py`, `closed/effects.py`, `closed/preparation_check.py`, `definitions.py`,
`effects.py`; and adapters under `workflow_lisp/adapters/`. `validate_review_findings_v1.py` is live
(`command_boundaries.py`, the `std/phase` review loop). The reviewer found the others named only by
`compiler.py` bindings, the two library modules, `typecheck_resume.py`, tests, and a library below
the floor.

## Rulings

(C) marks a ruling of the coordinator on the review; the others are the planner's.

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| R1 | **2.40 survives.** | It is the newest and a superset of 2.39 | None found; 2.39 source becomes 2.40 by changing the header (26 files, all the same program) |
| R2 | **Source: 2.40 in every module of the graph, or a refusal.** `compile`, `run`, dry-run, REPL load, LSP analysis, typed imports, `run-ref` children and the Python frontend refuse any other header before anything is published. 2.35–2.39 refuse with the existing code (`workflow_execution_target_retired` for an entry, `target_dsl_unsupported` elsewhere) and a message that names the migration section of the guide and the tag `v0.2.1`. No silent retargeting | A header that is accepted and ignored hides a change of procedure semantics. The pre-2.35 floor already works this way | An author with 2.35 source edits one line per file, plus the clauses; the message says how |
| R3 (C) | **Read-only labels.** The checker keeps 2.35–2.39 as readable program targets, so `report`, the dashboard and the monitor read every recorded run. Every command that continues or rewrites a run whose recorded target is not 2.40 (`resume`, with or without `--accept-changes`; `invalidate`; `input`; REPL attach) refuses before any compile and any write, with one diagnostic code that names `v0.2.1`. No label reaches the compiler and no flag is threaded through `build_syntax_module`. Replaces the first draft's R3 (labels compiled under one semantics on the rebuild path) | The rebuild compiles the current workspace, so labels on that path helped only an unmigrated workspace and let edited older-target source in through `--accept-changes`, against R2 and against Phase 3b's "a run keeps its entry and target" | Runs in flight at 2.35–2.39 stop being resumable at the cut; they finish on `v0.2.1`. If operators hold long runs at older targets, the cut strands them until they check out the tag |
| R4 (C) | **The five Phase 3b T1 run roots are re-recorded at 2.40 by `c3bdd14d`,** the build that wrote them, with the scaffold of `proof/phase-3b`, at the same recording path. Their README names that commit and says they are recorded once and never regenerated at test time. This honours "never regenerate": what must be preserved is rows written under the earlier `declaration` rule by the real earlier runtime, not the label | A fixture that cannot be resumed cannot show that old-rule rows still resume. Verified above: `c3bdd14d` records all five at 2.40 and `main`'s 39 tests pass on them unedited | A property of the 2.38 and 2.39 recordings that the 2.40 ones lack would go unseen; none was found, and the old recordings stay in history (`git show 79f04947:tests/fixtures/declaration_pre_change`) |
| R5 (C) | **The two 2.35 delivery run roots become report-plus-refusal fixtures.** Their bytes do not change; their two tests assert that `report` reads them and that `resume` refuses with the code of R3 and writes nothing | They cannot be re-recorded at 2.40 (their packages predate it) | After the cut no test resumes a really recorded commit without the `delivery` part or with `file/1`. Neither can occur in a 2.40 run (dates above), so the two acceptance branches become unreachable from `resume`; the synthetic test of the first stays while the code does. Their removal is a leftover for the delivery design's owner, not planned here |
| R6 (C) | **The rewrite drops every `:effects` clause below 2.39** (231 in `.orc` files, 14 in the placeholder fixtures, 691 in inline test sources), except in a test whose subject is the restriction, which is rewritten as an upper bound | The old clause listed only a procedure's own effects; the newer ceiling is checked per specialization and counts a hook's effects. Keeping the clause where it still passes would keep exactly one clause outside tests (`experiments/agent_chess/chess.orc`), and both library clauses fail | The library and the catalog carry no authored effect bounds after the stage |
| R7 (C) | **The cut does not wait for experiment kits.** A study runs from a frozen checkout and names the commit its hashes refer to. Task 4b has one precondition: the seed-set branch (`feat/seed-set-prep`, five programs at 2.39 in `experiments/seed_set/programs/`, header only) has merged and been migrated by Task 3a's sweep, or has migrated its programs itself, or has recorded its frozen runtime commit | No test on `main` pins the hash of an experiment `.orc`; PQ-1c, `prr_direct_orc` and eb3 read their own pinned runtime | A kit that launches from the moving checkout after the cut fails at compile with the message of R2, before any spend |
| R8 | **Fixtures that test a refusal the compiler can no longer produce go with it.** The 58 that use a deleted form go in Task 2, with one `form_retired` test per head. The five-argument `improve` fixture goes in Task 4a and the two old-regime fixtures in Task 4b. The 10 hand-written private forms are rewritten with `path/join-under` where the test is about something else and deleted where the private form is the subject | Such a fixture guards nothing | A property tested only through a deleted fixture is lost; the ledger rule makes the implementer name it |
| R9 | **Deleted heads refuse with `form_retired`**, through `RETIRED_FORMS` as `trial` does, each with its tag | One mechanism, already tested | None |
| R10 | **`:target-dsl` stays required.** | A missing header that means "current" would make the next language change silent | One line per file |
| R11 | **Package version 0.3.0 at the cut; the commit before it is tagged `v0.2.1`**, local, pushed by the coordinator. A local tag `archive/pre-one-target-2026-11-12` marks `main` before Task 2 | `specs/versioning.md`: a release that retires an executable target increments the minor version and the last release that executes it stays tagged | If the release tag is not wanted, the archive tag carries the same commit and the messages name it instead |
| R12 | **The wire values of row 14 stay.** Task 1 gives the path-mode value its own name, so `EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION` stops meaning three things. The two sets in `run_ref/config.py` validate stored and newly built config bytes and are **not** routed through source admission: narrowing them would break every path-mode run reference, new ones included. `prompt_scaffold_render.py:282` writes a file that already refuses as source; it is listed, not changed | Changing a wire value changes recorded config bytes | A reader may take `"2.35"` in a config for a target; the name and one comment say otherwise |
| R13 (C) | **No capability table.** The roadmap's first step, "collapse the monotone gates into one table", became: (a) Task 1 adds a guard test, "no comparison of a target with a version outside `targets.py`", with an explicit list of today's sites that may only shrink, and the name `CURRENT_TARGET_DSL_VERSION`; (b) Task 4b deletes the gates | Under R3 the compiler sees 2.40 only, so every gate of rows 3 to 12 is constant there. A table written in Task 1 would be deleted in Task 4b | Between Task 1 and Task 4b the gates stay scattered as today; the guard test stops new ones |
| R14 | **The checker keeps its label gates** (`check.py:3883`, `4608`, `1102`, `4652`; `check_agents.py:34,172`) and the predicates they call in `targets.py`, unchanged, until the labels go | They are the stored-program contract of the readable labels and cost no work; removing them would remove checker-soundness tests for no gain | Three predicates remain in `targets.py` with the checker as their only caller |
| R15 (C) | **One owner per file among parallel tasks** ([File ownership](#file-ownership)). A task that needs a change in a file it does not own hands the file to its owner in a list; it does not edit it | The first draft's rule left 240 older headers in files Task 2 owned and nobody migrated | A handoff waits for the other task; the lists make it visible |
| R16 (C) | **New test sources are written at 2.40 from the day Task 3 starts,** on every branch, unless they must match a recorded fixture. Task 4b lands at a Phase 3b task boundary ([Work in flight](#work-in-flight)) | Phase 3b T6 and T7 edit the same rebuild code; branches keep adding sources | A straggler at an older target fails in Task 4b's re-scan, where it is cheap |
| R17 | **Headings and anchors that carry a target number stay** (`#agent-sessions-target-238` and the like); only body text that tells the reader to choose a target or describes the old regime changes | 45 tracked documents link to such anchors | Headings read as history; a later docs pass may rename them with alias anchors |
| R18 | **All twelve minors of the review are applied; none is rejected.** Where they landed: 1 in the difference table and R12; 2 in the approach (the plan follows the roadmap's order; the first draft said it changed it, which was wrong); 3 in Tasks 4a and 4b; 4 and 5 in R7 and Task 3a; 6, 7 and 8 in the scripts and [The Behavior Comparison](#the-behavior-comparison); 9 in R6; 10 in Task 4b; 11 in R12; 12 under [Size](#size) | — | — |

Alternatives to R3, one line each: accept every header and treat it as 2.40 (smallest code, fails
the exit test and hides the regime change); admit labels on the rebuild path under one semantics
(the first draft; see R3's reason); refuse older targets in the checker too (`report` then fails on
every existing run root); keep the old regime for resume only (deletes nothing).

## The Versioning Rule

The roadmap asks, at this step, "whether an identity-affecting change adds a target or breaks
retained runs". Answer, written into `specs/versioning.md` by Task 4b as a section "Targets and
identity":

1. One target is admitted. `:target-dsl` names the source language, nothing else. Every build
   compiles source at that target, including the rebuild of an existing run and an accepted edit of
   one.
2. A change to what source that compiles means, or one that makes it stop compiling, adds a
   target; the same change migrates all tracked source and removes the previous target. Two source
   dialects never coexist in the compiler. A change that only admits source refused before, and
   moves no identity of source that compiles, adds no target; it gets an entry in the spec's
   change list. The cut of Task 4b is the one release that removes source forms without adding a
   target: it removes the older targets and, with them, the `fn` loop form
   ([surface coherence](../design/workflow_lisp_surface_coherence.md) I2b).
3. A change that moves an identity without changing what source means (a program digest, an effect
   identity, a memo row, the checked representation) **adds no target**. It either keeps recorded
   runs resumable, and proves it with a run root recorded before the change by the build that
   preceded it and never regenerated at test time, or it breaks them: resume refuses through the
   digest check, the package minor version increments, the last release that resumes them is
   tagged, and the change gets a row in the spec's compatibility table.
4. A removed target stays a **read-only label**: `report`, the dashboard and the monitor read a run
   recorded at it; nothing continues or rewrites it. **A run in flight at a removed target can be
   continued only with the tagged release that last admitted it.**

| Label | Read by | Continued by | Removal condition |
| --- | --- | --- | --- |
| 2.35–2.39 | `report`, dashboard, monitor | `v0.2.1` only | A release whose checker no longer reads the stored representation of these runs (they are unreadable then for another reason), or a ledger entry. The wire value `"2.35"` of path-mode configs is not this label and does not go with it |

## The Behavior Comparison

For every file a task rewrites, before against after, with `classify.py` and `diff.py`:

- **Must be identical:** for each exported workflow, built or refused; for a refusal, the first
  diagnostic code (the scripts do not compare positions: removing a clause can remove a line); for
  a build, the normalized hash, unless the file is on the structure list above. For the catalog, the
  library and every file on the structure list that has a stand-in, from a public `run`
  (`runsample.py`): exit code, standard output, result value, the stand-in's call log and each
  effect's input parts, with the run id normalized.
- **Expected to move:** the program digest of every rewritten source, because `target` is a digest
  input; run-reference configs that embed such a program; effect identities of the files on the
  structure list. Nothing else. An effect identity that moves in a file off the list is a finding.
- **Must not move at all:** anything compiled from a source the task did not edit, including every
  file already at 2.40 and every recorded run root.
- **Never a match:** a `compiler_defect` on either side. The six known rows are listed; a new one
  is a finding.

The normalized hash is the closed program with `target` replaced and every `@` object removed. `@`
holds `span`, `form` and `source_map_subject`: behavior does not depend on them (sites and
identities sit outside), but a source-map regression passes this comparison unseen. The LSP, REPL
and diagnostics modules in each task's narrow run are the check for that.

Stage 3's three invariant files hold raw digests, which cannot be normalized afterwards. Task 0
therefore writes, beside each raw digest of the corpus snapshot and of the compile of every `.orc`
file, the normalized hash of the same program. Tasks 1 and 2 compare the raw files byte for byte
(Task 2 with one listed exception). Tasks 3 and 4 compare raw digests for sources the task did not
edit and normalized hashes for those it did. The run-reference file is compared raw for programs
whose sources were not edited; for edited ones the run-reference test modules are the check.

Known limits of `classify.py`, to keep in view: externs are made up, so 168 files refuse the same
way on both sides and only their first code is compared; it compares entries that exist on either
side and probes every exported workflow (the first draft's cap of four is removed).

## File Ownership

Among the tasks that run in parallel, a file has one owner.

| Owner | Files |
| --- | --- |
| Task 2 | Production code and the library. Every tracked `.orc` at 2.35–2.40 that matches the deleted-form pattern (an opening parenthesis followed by `materialize-view`, `resource-transition`, `resume-or-start`, `run-provider-phase`, `produce-one-of`, `finalize-selected-item`, `backlog-drain`, `defresource` or `deftransition`, or an import of `std/drain` or `std/resource`): 58 test files. The 25 test modules that mention a deleted form, its Python modules or `current_effect_gaps`, **in full**: Task 2 deletes what tested the forms and applies the rewrite to every other source in them (240 headers). `tests/test_workflow_lisp_closed_program_effects.py` is among them; `tests/test_retired_executors_removed.py` is Task 2's too. Documents: `docs/lisp_workflow_drafting_guide.md` (removed-form text and its 5 example headers below 2.40), `docs/capability_status_matrix.md`, `specs/state.md`, `specs/dsl.md`, the two designs it marks Historical |
| Task 3a | `.orc` files outside `tests/` and outside the library, less the exclusions below; `experiments/orc_gp_example/grammar.py`; `tests/experiments/test_orc_structural_search_seeds.py`; `README.md`, `docs/tutorial_first_pipeline.md`, `docs/lisp_library_reference.md`, `docs/python_workflow_drafting_guide.md`, `workflows/README.md`; Python examples that set `TARGET` |
| Task 3b | `.orc` files under `tests/` at 2.35–2.39 that Task 2 does not own, less the recorded sources and the three fixtures of R8 left for Task 4: 312 files |
| Task 3c | Every test module not owned by Task 2 (630; 270 of them build a source at an older target); `tests/workflow_lisp_closed_program_helpers.py` and the 10 placeholder fixtures it reads; every file handed off by 3a or 3b |
| Task 3d | `tests/fixtures/declaration_pre_change/` |
| Nobody, in any task | `experiments/compare/tasks/**` and, when its branch merges, `experiments/seed_set/tasks/**` (hashed packages); frozen experiment evidence; `tests/fixtures/provider_delivery_pre_change/` and `provider_delivery_file1/`; `.orc` files below 2.35; untracked files; `.worktrees/` of other sessions |

Handoff: 3a and 3b edit no test module. If a rewritten file makes a test fail, the task reverts
that file, records the file and the failing test in its handoff list, and 3c rewrites file and test
together. The guide, `README.md`, `specs/cli.md` and `specs/providers.md` have uncommitted edits
from another session: rebase, do not overwrite.

## Work In Flight

State on 2026-11-12: Phase 3b T1, T2 and T5 are merged; T3 is in progress on `feat/p3b-t3-lineage`;
T4, T6, T7 and T8 follow. `feat/seed-set-prep` is 27 commits ahead of `main`.

- **Rule (R16).** From the day Task 3 starts, a new test source on any branch declares 2.40, unless
  it must match a recorded fixture. The coordinator adds the line to the roadmap's routing list.
- **Now, beside Phase 3b:** Tasks 0, 1, 2, 3a, 3b, 3c. None is planned to touch
  `cli/commands/evaluated.py`, `rebase.py` or the logic of the recorded-run test modules; 3c changes
  only the inline sources in them.
- **Task 3d** changes the bytes Phase 3b's tests read. It merges when no Phase 3b branch is in
  review, and each open branch runs its recorded-run tests on the new fixtures once (a test that
  pins a run id or an identity of the old recordings must be rebased; none on `main` does).
- **Task 4b** adds the refusal of R3 where Phase 3b T6 and T7 work, so it lands at a Phase 3b task
  boundary, in one of two orders:
  - *Before T6 starts* (possible only if Tasks 2 to 4a are merged by then). The refusal goes first
    in `prepare_evaluated_resume`; T6's plan printer and T7's accept path are then written above a
    function that already refuses, and Phase 3b's row "the target differs" can only mean an edit
    away from 2.40, which no longer compiles. T6 and T7 write their fixtures at 2.40. Task 4b
    re-checks nothing in Phase 3b; Phase 3b's design line on "keeps its entry and target" gets one
    sentence.
  - *After T7 merges.* The run-continuing paths are then more: the read-only plan, `accept_plan`,
    the bare flag, `input answer` and a child run. Task 4b re-checks that each reaches the one
    refusal before it compiles, prints a plan or writes; that the entry-point test enumerates the
    new handlers; and it re-scans the tests T3 to T7 added for older targets and migrates them.
- **Seed-set branch:** the precondition of R7. If it merges before Task 3a, the sweep migrates its
  five programs and its compile tests (`tests/experiments/test_seed_set_programs.py`).
- Every task re-runs its scan at its own base: `main` moves daily.

## Global Constraints

- Deletions, the rewrite, the re-recording and the admission change only. No change to what a 2.40
  program means. The two live-provider forms are not edited.
- A test goes only with the code or rule it covered; the ledger lists both. No test of kill, resume,
  recovery, memo durability, checker soundness, result validation, security or the command line end
  to end is removed, with the two exceptions ruled in R5. Tests assert behavior, never prompt text.
- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`; no
  `git stash`. Separate worktrees; `PYTHONPATH` set to the working tree;
  `experiments/thread_m/no_provider` first on `PATH`; `mkdir -m 700` for any basetemp; long runs in
  tmux from an existing session; check `df` before a full suite.
- **Gate, for every commit:** no test outside the four worktree-artifact ids of the [test
  baseline](../reports/2026-11-11-test-baseline.md) fails. During work: the task's narrow run, then
  `pytest -q -n 16 --dist=worksteal --sample 10`; before each merge to `main`, the same without
  `--sample`. `pytest --collect-only` on each test module added or edited.

## Tasks

Task 0, then Task 1. Then Tasks 2, 3a, 3b, 3c and 3d in parallel under [File
ownership](#file-ownership). Then 4a, 4b at a Phase 3b boundary, and 5.

### Task 0: Tags, baselines, scripts (0.5 day)

- [ ] Create the local annotated tag `archive/pre-one-target-2026-11-12`; record the suite result
      and the collected count. The coordinator adds R16's line to the roadmap.
- [ ] Copy the planner's scripts into the task's scratch. Make stage 3's three invariant files with
      the normalized hash beside each raw digest, and the outcome table:
      `git archive HEAD orchestrator $(git ls-files '*.orc') | tar -x -C <base>`, then
      `PYTHONPATH=<base> python classify.py <base> base.json`. Expect 421 files; 191 built.
- [ ] Record `python -m orchestrator report --run-id <id>` for the two 2.35 run roots, and keep one
      fresh run at 2.40 killed after its first command (both for Tasks 4b and 5).

### Task 1: The guard test and the current-target name (0.5 day; about +80 lines)

- [ ] `targets.py` gains `CURRENT_TARGET_DSL_VERSION = "2.40"` and a named wire value for path-mode
      configs; `closed/build.py:1648` and `check.py:4656` use the wire name (R12). No gate changes.
- [ ] One test: no file under `orchestrator/` other than `targets.py` compares a target with a
      version literal, a version tuple or a set of versions, except the sites in a list inside the
      test (rows 3 to 12 and 14 of the difference table, one entry per file with its count). The
      list may only shrink. See the test fail on a planted comparison.
- [ ] Checks: the invariant files and `base.json` byte-identical; narrow run
      `tests/test_workflow_run_ref_config.py tests/test_workflow_lisp_source_floor.py
      tests/test_workflow_evaluated_run_ref.py`.
- Reviewer: a comparison shape the test's pattern misses (`getattr(..., "TARGET", "2.39")`, a tuple
  built from `split(".")`, `min_target_dsl_version=`).

### Task 2: Delete the refused forms (5 days; about −4,500 production and library lines, −4,100 fixture lines, −3,700 test lines)

Remove the heads marked Delete in the form table except bare `with-phase`: registry rows, parsers,
expression classes, typecheck, the WCC and closed-build branches, `defresource` and `deftransition`
with their catalog, `std/drain.orc` and `std/resource.orc`, and each adapter module that no
surviving form, library module or tracked command manifest names. Add the heads to `RETIRED_FORMS`
with this plan's tag. Then apply the rewrite to every remaining source in the 25 test modules it
owns. The 50 fixtures below 2.35 that use these heads already refuse by their header; one goes only
if the test that reads it goes.

- [ ] First re-run the reachability scan per adapter and per expression class; delete only what the
      scan clears. `validate_review_findings_v1.py` stays.
- [ ] Add one `form_retired` case per deleted head and the removed modules' rows to
      `tests/test_retired_executors_removed.py`; see them fail first. Trim
      `test_each_selected_effect_outside_the_release_is_a_located_gap` to the forms that remain.
- [ ] Documents: the guide's sections 13.1, 13.3, 13.4, 13.5 and 13.6 become one paragraph that
      names the removed forms and `form_retired`; the paragraph of section 2A that lists unavailable
      forms and the two bullets under "Runtime-Native Authoring Direction" lose them; sections 11
      and 12 lose text that describes resource transitions as authorable; the guide's example
      headers go to 2.40, with the "complete 2.35 recipe" body at 2.40 under its present anchor.
      The capability matrix rows for `backlog-drain` and resource transitions say Removed with the
      tag. `specs/state.md` and `specs/dsl.md`: sentences that present these forms as current. The
      designs `workflow_lisp_stdlib_lowering.md` and `workflow_lisp_runtime_native_drain_authoring.md`
      become Historical with a scope notice, after a check that no current rule lives only there.
- [ ] Checks: `base.json` against the new table differs only in rows that used a deleted form
      (expected: 58 test files, 2 library modules); the corpus snapshot differs only in such rows;
      run-reference digests identical; the behavior comparison for the sources it rewrote. Each of
      its 25 modules run before and after with the same pass count, less the listed deletions.
      Narrow run: those modules, `tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_lsp_*.py
      tests/test_workflow_lisp_route_readiness.py tests/test_first_hour_e2e.py
      tests/test_authoring_check_kit.py`.
- Reviewer: a live path through a "deleted" adapter; `review-revise-loop`, `with-phase` and
  `phase-scope` still build; the `std/context` records still import; a surviving test in one of the
  25 modules left at an older target; no test of a surviving property went with a fixture.

### Task 3: Migrate callers to 2.40 (9 days in four parts; net about −1,300 lines)

The packaged library stays at 2.35 here.

- **3a, catalog and documents (1.5 days).** The files of its row: `workflows/examples/`,
  `workflows/library/` (in `drain.orc` the seed becomes
  `(path/join-under DrainSummaryPath "drain-summary.json")`), the experiment sources outside the
  excluded packages, the generator `grammar.py`, the seed test's assertion (2.39 becomes 2.40), the
  source examples in `README.md`, the tutorial and the library reference. Checks: the behavior
  comparison with public runs for every example that has stand-ins;
  `tests/test_first_hour_e2e.py tests/test_workflow_lisp_closed_program_corpus.py
  tests/experiments/test_orc_structural_search_seeds.py`; one orchestrator smoke run of a catalog
  example.
- **3b, test `.orc` fixtures (2 days).** `migrate2.py` over its 312 files; the 7 structure changes
  and the 10 private-form rewrites by hand. Checks: the behavior comparison (expected: 295 same, 7
  on the structure list); `tests/test_workflow_lisp_guide_programs.py` and the modules that read
  each fixture directory pass unedited, or the fixture is handed to 3c.
- **3c, inline and parameterized test sources (5 days; may be split in two worktrees by file
  list).** Its module list is computed by "builds a source at a target other than 2.40", which
  includes the constant, the helper and `{TARGET}`, not by literal header: 270 modules today. The
  helper's `TARGET` becomes `CURRENT_TARGET_DSL_VERSION` in the same commit that rewrites the 10
  placeholder fixtures (28 clauses). The 20 parametrized modules keep one case at 2.40 and the
  ledger lists each removed parameter. In the 38 modules that name an old-regime rule or a target
  gate, 3c rewrites the tests that are not about that rule and leaves the others for Task 4b, in a
  list. Checks: each edited module run before and after with the same pass count, less the listed
  parameters; a digest or identity literal that changes must belong to a rewritten source.
- **3d, re-record the five run roots (0.5 day).** Export `c3bdd14d` (`orchestrator/`, the test
  modules, `tests/fixtures/{phased_239,providers,provider_delivery_pre_change}`); take
  `scaffolds/{record_fixtures.py,assemble_fixtures.sh,clean_phased_reservations.py}` from
  `3662a26b`; change the three sources to 2.40 as `record_240.py` does (the provider source, the
  agent source, the phased `main.orc`) and nothing else; record at
  `/tmp/orc-declaration-pre-change`; assemble; release the reservations and remove the two revoked
  namespaces. The README states the build commit, the scaffold commit, the one change, and "recorded
  once; never regenerated at test time". Checks: `tests/test_workflow_evaluated_edit_resume_baseline.py
  tests/test_workflow_evaluated_declaration_resume.py`, 39 tests, no skip, unedited; a `git diff
  --stat` that touches only the fixture directory.
- Reviewer: a test that still passes because it stopped testing anything (an assertion on a
  refusal that the rewrite turned into a different refusal); a `:effects` clause dropped from a test
  whose subject is the restriction; expected values edited without a matching entry in the list;
  for 3d, any difference between the recording procedure and the original beyond the three headers.

### Task 4a: The library to 2.40 (1 day; about −150 lines)

Needs Tasks 2 and 3 on `main`. Green on its own: after Task 3 every importer is at 2.40.

- [ ] The rewrite on `stdlib_modules/std/{context,phase,improve}.orc`; `w3/std/improve.orc` becomes
      `std/improve.orc`; the five-argument module, the root selection in `modules.py:321`, the
      fixture `current_examples/improve_experiment_proposal.orc` and the tests of the five-argument
      form go, listed. The guide's and the library reference's "Target 2.35 explicit inputs" go.
- [ ] Checks: first re-run 3c's scan; no source below 2.40 imports the library. The behavior
      comparison over the library's importers (expected: every program byte-identical, since the
      importers are not edited); `tests/test_workflow_lisp_phase_stdlib.py` and the `improve` modules.
- Reviewer: an importer whose digest moved (none may).

### Task 4b: The cut (3.5 days; about −1,050 production lines, −1,700 test lines, −250 document lines, +200)

Needs 4a, the precondition of R7, and a Phase 3b boundary ([Work in flight](#work-in-flight)).

| Edit | Change |
| --- | --- |
| Admission | `targets.py`: the source set is the current target; a second set, the readable program targets, keeps 2.35–2.40 and is used by the checker only (`check.py:307`). The refusal messages of R2 |
| Rows 3, 7, 8, 9 of the difference table | The older branch of each switch: mandatory exact `:effects`, `:lowering` and every `ProcedureLoweringMode` but inline, the private-workflow lowering in `procedure_specialization.py` and its two consumers in `closed/`, the loop override, single-binding `let-proc`, hand-written private forms, the bare `with-phase` row, the import direction rule and its diagnostics, the one-question `request-input` |
| Rows 4, 5, 6, 10, 11, 12, 15 | Every frontend gate, now constant: the calls in `parallel_map.py`, `agent_forms.py`, `type_env.py`, `expressions.py`, `typecheck_effects.py`, `closed/effects.py`, `confined_config.py`, the `agent` row's minimum, the Python frontend's `TARGET` checks (default and only value 2.40). The checker's gates stay (R14). The guard test's list shrinks to rows 14 and R14 |
| Runs at a label (R3) | One function, called before any compile or write in `prepare_evaluated_resume` (`resume`, `--accept-changes`, host `input`), in `invalidate_run` and in REPL attach: if the stored program's `target` is not the current one, refuse with one new code that names `v0.2.1` and says `report` still reads the run |
| Tests | Delete the tests left by 3c that test a removed rule or gate and the two old-regime fixtures. Add: one parametrized test, older target by public entry point, that each refuses without writing a build or run directory; one test per recorded 2.35 run root that `report` prints what Task 0 recorded and that `resume` and `invalidate` refuse with the code and change no byte. The two delivery tests of R5 become those |
| `specs/versioning.md` | The section "Targets and identity"; the gating summary's paragraphs on 2.36 to 2.40 say what each capability is, not which target selects it; the label table |
| `specs/dsl.md`, `specs/cli.md`, `specs/io.md`, `specs/state.md` | "Targets 2.35–2.40" becomes the current target; `resume`, `invalidate`, `input` and the REPL state R3 in one sentence each |
| Guide | Section 2 and the opening of 2A become one paragraph; "Procedure contracts at target 2.39" is the procedure contract, without the paragraph on imported 2.35–2.38 definitions and without the 83-line older example; `let-proc` text loses the 2.35 form; a short section "Migrating from an older target" that the refusal message links to, which says in its first sentence that a run started before the migration is finished with `v0.2.1` |
| Others | `docs/index.md` clarifications, the capability matrix's target sentences, the Python guide's default, the lifecycle guide's resume section, `pyproject.toml` 0.3.0 and the tag `v0.2.1` on the commit before |

- [ ] First re-scan for sources below 2.40 at this base and migrate stragglers. Then the two new
      tests, seen to fail.
- [ ] Checks: no program at 2.40 moves (raw invariant files for unedited sources); the registry
      holds 81 heads; `tests/test_workflow_evaluated_edit_resume_baseline.py
      tests/test_workflow_evaluated_declaration_resume.py tests/test_workflow_evaluated_resume_*.py
      tests/test_resume_command.py tests/test_workflow_evaluated_run_ref*.py
      tests/e2e/test_e2e_workflow_evaluated_run_ref.py tests/test_workflow_lisp_host_input.py
      tests/test_workflow_lisp_lsp_*.py tests/test_workflow_evaluated_repl*.py
      tests/test_workflow_python_*.py tests/test_workflow_closed_program_isolation.py`; one
      orchestrator smoke run; the full suite.
- Reviewer: an entry point that still accepts an older header (typed imports through
  `--imported-workflow-bundles-file`, a `run-ref` child compiled from a pinned commit, `py run`,
  the LSP); a command that writes to a run at a label before it refuses; a stored program at a label
  that `report`, the dashboard or the monitor no longer reads; a 2.40 run recorded by `v0.2.x` that
  no longer resumes; a program at 2.40 whose digest moved (none may).

### Task 5: Final verification (0.5 day)

- [ ] Exit test: the guard test's list holds only the wire values and the checker's label gates; a
      new program at each of 2.35–2.39 refuses on `compile` and `run` with the migration message;
      the label table in `specs/versioning.md` matches `targets.py`.
- [ ] End to end: `resume` completes Task 0's killed 2.40 run; `report` on the two 2.35 run roots
      prints what Task 0 recorded; `resume` on each prints the one refusal. The
      tutorial's pipeline is compiled, run, killed and resumed afresh.
- [ ] Full suite within the gate. Ledger: lines removed per task against the tag, collected items
      before and after, every removed test and fixture with the code or rule it covered, every
      expected value that changed.

## Size

| Task | Days | Net lines (estimate) | Runs beside |
| --- | ---: | ---: | --- |
| 0 Tags, baselines | 0.5 | 0 | — |
| 1 Guard test, current-target name | 0.5 | +80 | — |
| 2 Refused forms, and its 25 test modules | 5 | −12,300 | 3a, 3b, 3c, 3d |
| 3a Catalog and documents | 1.5 | −100 | 2, 3b, 3c, 3d |
| 3b Test fixtures | 2 | −500 | 2, 3a, 3c, 3d |
| 3c Inline and parameterized test sources | 5 | −700 | 2, 3a, 3b, 3d |
| 3d Re-record five run roots | 0.5 | 0 | 2, 3a, 3b, 3c |
| 4a Library | 1 | −150 | — |
| 4b The cut | 3.5 | −2,800 | — |
| 5 Final verification | 0.5 | 0 | — |
| **Total** | **20** | **about −16,500** | Engineer-days; about 11 elapsed with four worktrees |

Against the first draft: Task 1 lost a day (no table); Task 2 gained one (it migrates the files it
owns); 3d is new; Task 4 is two steps and deletes the monotone gates as well, and no longer threads
labels into the compiler. The figures are an upper bound in engineer-days: stage 2 was estimated at
12.75 days and merged in about two calendar days, stage 3 at 7.25 and merged the day it was
accepted. The risk is in 3c's test churn and in review rounds, not in the deletions. Whole-module
line figures are measured; the rest are estimates from function spans and pattern counts, and the
ledger records the real ones.

## What This Makes Harder

- **Continuing a run started at 2.35–2.39.** After the cut `resume`, `invalidate`, `input` and REPL
  attach refuse it; only `v0.2.1` continues it (`git worktree add ../orc-0.2 v0.2.1`). `report`
  still reads it.
- Compiling or starting a run from 2.35–2.39 source: the same fallback, or the migration.
- Showing with a really recorded run that a commit without the `delivery` part, or with `file/1`,
  still replays (R5).
- Pinning a `run-ref` child to a commit whose source declares an older target.
- A procedure with its own call frame. The only boundary left is `defworkflow` with `call`, whose
  inputs and result must be transportable.
- Exact effect declarations. `:effects` is an upper bound; a procedure that must do exactly one
  thing needs a test, not a clause.
- Resource transitions, reusable phase state, materialized views and the drain library as source
  forms. A later design starts from the tag and the Historical documents, on evaluated execution.
- The next language change: rule 2 makes it a migration of all tracked source in the same change,
  with no period in which two dialects compile, and rule 4 strands the runs then in flight.
- Reading the guide's history from its headings, which keep target numbers that no longer select
  anything (R17).

## Not Verified While Planning

- No task was tried except the recording of 3d, and that one in scratch, not at the canonical path.
  The suite was not run on any copy.
- How many tests fail when the old regime and the gates go. The 38 modules that name a rule or a
  gate were found by pattern; which of their tests are about a removed rule was not read.
- Inline and parameterized test sources were counted, not compiled. The 295 "rewrite only" figure is
  for `.orc` files; the 10 placeholder fixtures were not classified.
- That no open Phase 3b branch pins a run id or identity of the present recordings (checked on
  `main` only).
- That the 2.40 recordings carry everything the 2.38 and 2.39 ones were chosen to show; the
  evidence is the 39 passing tests.
- `invalidate`, `input`, the dashboard and the monitor on a run at a label: only `report` and
  `resume` were tried, on a hard-cut copy. No tracked run root holds a host request.
- The narrowed admission beyond what R2 lists was not emulated (compile, the LSP, typed imports,
  run-ref children, `py run`).
- In 168 of the 421 files every probed entry refuses in both copies with the same code. For those,
  "same outcome" means the same first diagnostic code only.
- That each of the 63 registry heads not probed alone builds: the evidence is a shipped file that
  uses the head and builds. The deleted heads were not probed at 2.36–2.39 separately.
- Line estimates for Task 2 beyond whole modules, and the reachability of each adapter beyond the
  reviewer's grep.
- That `let-proc` with explicit `:captures` behaves the same under the newer rule: one built file.
- That effect identities never depend on the target label: one run of the planner's and one of the
  reviewer's.
- Whether the two delivery acceptance branches of R5 are dead for every caller, not only `resume`.
- The 311 tracked `.orc` files below 2.35 and the tests that read them.
- Whether a document test pins a sentence Tasks 2 to 4b edit.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-12 | First draft committed as written (`61f34f8f`). Independent review: accept with changes, 1 blocker, 6 major, 12 minor. Coordinator's rulings recorded as R3 to R7, R13, R15, R16; all minors applied (R18). The planner verified R4's condition: the build `c3bdd14d` records all five Phase 3b run roots at 2.40, and the 39 recorded-run tests of `79f04947` pass on them unedited. No provider spend. |
| 2026-11-12 | Plan accepted by the coordinator | Independent review: accept with changes, 1 blocker, 6 majors, 12 minors; all applied in the revision. The blocker (the rebuild path compiles the workspace, so labels under one semantics would not keep old runs resumable and would open an edit back door) is resolved by read-only labels: `report`, dashboard and monitor read runs of every recorded target; `resume`, `invalidate`, `input` and REPL attach refuse a run not at 2.40 with one code naming the tagged release. The planner checked the one risk of that ruling by experiment: the pre-T2 build `c3bdd14d` records the five Phase 3b fixtures at 2.40 and the current tests accept them. Coordinator rulings on the planner's notes: the checker keeps its per-label gates while old run roots are readable (R14 stands; their removal is a leftover); `invalidate` is refused for old-target runs although it does not compile; the two 2.35 delivery fixtures are a named exception. Order of execution: Tasks 0 and 1 now; Task 2 after Task 1; Tasks 3b and 3c wait for the surface-coherence design's verdict so the loop-binder rewrite and the target rewrite touch each test file once; Task 4b lands at a Phase 3b task boundary. |
| 2026-11-12 | Ruling: versioning rule 2 is about source that compiles | The surface-coherence design (accepted today) admits source that is refused now (effects in fields, any-expression map bodies, a local called by name) and moves no identity of compiling source: no target is added for those. Removing the `fn` loop form does stop compiling source from compiling: it lands inside Task 4b, the one breaking release, as a coordinator default the owner may overturn before the cut. Task 3's sweep rewrites loops to the binder form in the same pass as the headers, after the compiler accepts both forms (design change I2a). Tasks 3b and 3c are released from their hold once I2a is merged. |
| 2026-11-12 | Tasks 0 to 2 done on `chore/lane-d4-forms` (Phase A `9df49539`; Task 2 `8dbf559b`..`7edbd4cb`; review fixes after it) | Independent review: approve with fixes, 0 blockers, 3 majors, 10 minors, all applied. The ten heads, `std/drain`, `std/resource` and five adapters are removed; each head refuses with `form_retired` naming `archive/pre-one-target-2026-11-12`, and an import of either module names the tag. A module that only declared `defresource`/`deftransition`, or imported `std/drain`/`std/resource` without using a form, built before and refuses now; no tracked 2.35+ source does either. Invariants at the merged tip: run-reference digests, measured at the same path as a fresh base run (they depend on the temp path): 2 of 128 programs move, `test_confined_site_in_an_impor*` and `test_map_walk_skips_callees_re*` (`test_workflow_lisp_run_ref_workflow_program.py`), because `7edbd4cb` moved their sources `PRODUCER_238`, `PLAIN_PRODUCER` and the `_bundle_build` consumer to 2.40 (`target` is a digest input); 399 passed (400 less the removed confined-child test); `main` alone moves none. Corpus snapshot identical. Compile of every `.orc`: 634 files (690): 57 leave (55 fixtures including the orphaned `certified_adapter_semantic_bypass.orc`, and the 2 library modules), 1 arrives, the 8 rewritten imported-stdlib files change (3 now build); the 42 earlier builds are identical raw and normalized. Classify: 365 rows; only removed rows, 1 new and 1 rewritten. Import walk: 375 modules (`main`'s 384 less the 9 deleted) |
| 2026-11-12 | Kept: `resource_move_without_transition` | Still reachable: a manifest can certify an adapter with `effects` `resource_transition`/`ledger_update` or `behavior_class` `resource_transition`, and the lint is the only thing that refuses calling it. Its migration-backend exemption went (no manifest can carry `transition_binding` now), its message no longer recommends a route, and it is tested through `compile` again; the orphaned fixture `certified_adapter_semantic_bypass.orc` was deleted. `recovery_gate_without_resume_or_start` is kept for the same reason (`resume_state_reuse`), tested in `test_workflow_lisp_phase_stdlib.py` |
| 2026-11-12 | Collapsed: a manifest `transition_binding` is one refusal | `command_adapter_missing_contract` when the command boundaries are loaded: "certified adapter `X` declares `transition_binding`, which no command adapter may carry: resource transitions were removed (git tag archive/pre-one-target-2026-11-12)". The compiler's three-branch check and the reader-side role checks are deleted. No digest moves: no program with a `transition_binding` could build before either |
| 2026-11-12 | Ruling (a): the closed-program `transition_binding`/`view_binding` fields stay | They are inside the stored program digest (`closed/program.py`, `check.py`); removing them moves every digest with a certified command and breaks `report` on recorded runs. They go with a later change to the stored program format. Owner: the stage 4 leftovers list. The manifest `view_binding` field is accepted and recorded with no form that reads it; it goes with them |
| 2026-11-12 | Ruling (b): `CompilerSession.reusable_state_producer_context` and `contracts.derive_reusable_state_contract_metadata` | Dead in production; read only by `test_workflow_lisp_compiler_session_state.py` and `test_workflow_lisp_structured_results.py`. Task 3c deletes the two definitions in the same commit as the tests that read them: an explicit exception to the ownership table, which otherwise gives 3c no production file |
| 2026-11-12 | Ruling (c): 27 older-target headers left in Task 2's modules | Each was migrated alone and run. Blocked by a Task 3b fixture (3b first, then 3c migrates the test): `test_workflow_evaluated_command_templates.py::test_public_certified_document_is_delivered_and_included_in_input_digest` (2 headers; it rewrites a fixture header), `test_workflow_lisp_lowering.py::test_stage3_entrypoint_coexists_with_explicit_imported_typed_program` (`modules/valid/imported_bundle_mix` at 2.35: `evaluated_execution_target_direction_invalid`). Bare `with-phase` (Task 4b's row): lowering `test_typed_effect_inference_descends_through_phase_inside_same_file_procedure`, phase_stdlib `test_typecheck_accepts_generic_phase_ctx_for_phase_target`, `test_typecheck_accepts_generic_phase_scoped_provider_result_record`, session_artifact `test_stage3_phase_placement_rejected`, procedures `test_private_workflow_review_phase_procedure_rejects_review_loop_result_projection_boundary`, `test_private_workflow_call_rejects_review_loop_boundary_before_allocator_reuse` (6; `stdlib_import_route_required`). Old procedure regime (4b): procedures `_selected_hook_lowering_module_lines` (with its two lowering-mode tests), `test_selected_hook_recomputes_transitive_effects`, `test_private_workflow_specialization_revalidates_selected_hook_boundary`, `test_auto_lowering_stays_inline_when_private_workflow_would_only_project_inputs`, `test_compile_rejects_let_proc_name_collision_in_same_scope` (V1 `let-proc`), phase_stdlib `test_current_target_composes_review_loop_through_phase_private_workflow` (6). Older-target imports and target assertions (4b): lowering `test_build_workflow_catalog_reconstructs_imported_param_defaults_from_typed_program` (2), `..._imported_typed_rich_union_return_at_229` (2), modules `test_compile_stage3_entrypoint_keeps_native_analysis_for_old_source`, `test_imported_old_module_keeps_its_own_target_for_w3_syntax` (2), `test_w3_graph_accepts_older_helper_using_four_argument_improve` (2), intrinsic_admission `test_completion_hides_private_and_fallback_heads_only_for_target_239` (10). 2.40 `request-input` syntax (3c rewrites the probe): run_ref_workflow_program constants `CONFINED` and `SHAPE_REFUSALS` (2; the second rewrites the first's header) |
| 2026-11-12 | Leftovers handed on (4b or Task 5) | The pre-2.39 LSP completion detail (`effects (...)`) has no assertion since `lsp_l1_symbols` moved to 2.40; it goes with the old regime in 4b. Orphans with no reader: `tests/fixtures/workflow_lisp/characterization/manifest.json` rows and `straight_line_provider_phase.*` goldens, `tests/baselines/drain_checkpoint_identity/`, the never-raised `interior_publication` lint, the unused constants `MATERIALIZE_VIEW_RUNTIME_FIXTURE` (`test_workflow_lisp_entry_publication.py`) and `TYPED_PROMPT_INPUT_FIXTURE` (`test_workflow_lisp_typed_prompt_inputs.py`). LSP recovery completion offers the private and compatibility-only heads that full completion hides at 2.39+ (pre-existing) |
| 2026-11-12 | Tasks 0, 1 and 2 merged to `main` (`85a7cf88`) | The guard test (no target-version comparison outside `targets.py`; listed sites may only shrink), the archive tag `archive/pre-one-target-2026-11-12`, and the deletion of the eleven refused forms with `std/drain`, `std/resource` and five adapters: 167 files, 16,087 lines removed, 1,085 added; production code is 207,673 lines. Independent review: approve with fixes, 0 blockers, 3 majors, 10 minors, all applied (rows above). The reviewer's 151 tripwires over 9,679 tests, a compile of every `.orc` file and every CLI entry fired only in tests and fixtures the branch deletes or rewrites. Full suite on the branch after merging `main`: 14,763 passed; besides the four nanoBragg baseline failures, two timing tests failed in a run that took 19 minutes at load average 50 to 65 and pass alone (`test_observed_nonstream_timeout_is_not_blocked_by_unread_large_stdin[True]`, and the C6 retry test already on the load-sensitive list). Next: Tasks 3a to 3d wait for the migration tool (surface coherence I2a, in review fixes). |
| 2026-11-13 | Task 3d done on `chore/lane-d4-3d` (`8d78ee9b`) | The five run roots of `tests/fixtures/declaration_pre_change/` re-recorded once at 2.40 by an export of `c3bdd14d` with the scaffold of `3662a26b`, at `/tmp/orc-declaration-pre-change` under the tests' lock; the scaffold's only change is the three source headers (as `record_240.py`, with the canonical path kept). Phased reservations released (`clean_phased_reservations.py`: both `True`); the two revoked namespaces this recording created (`orc-peer-f93e6a02…`, `orc-peer-f56427c5…`, the only new `orc-peer-*` in the recording window and the two the receipts name) removed. The README names build, scaffold, command, date and the commit that last held the first recording (`ae36901d`). The stored programs differ from the first recording only in `target`; effect identities and `declaration` parts are unchanged; run ids, program digests, workflow checksums, `prompt`, `agent`, `predecessor` and `phased_cut` parts, result digests, native session ids and memo offsets (±1–3 bytes) move. Tests unedited: `edit_resume_baseline` 11, `declaration_resume` 28, `lineage_resume` 27, `lineage_readers` 25, `edit_resume_plan` 73, 164 passed, no skip (the pending-phased test runs). Sampled suite 1,478 passed. Invariants against `ae36901d`: corpus snapshot identical (`810baec5…`); run-reference digests identical (399 passed, 128 programs, `3dc6f10e…`); compile of 634 `.orc` files: exactly the five fixture sources change, exit 0 on both sides, program digest and build key only (`target` is a digest input). The two 2.35 delivery run roots are untouched (Task 4b, R5). |
| 2026-11-13 | Task 3d merged (`4143199a`) | The five Phase 3b recorded run roots are re-recorded at target 2.40 by the pre-change build `c3bdd14d` with the `proof/phase-3b` scaffold; every effect identity and every `declaration` and command input part is unchanged, each stored program differs only in `target`; all 164 tests of the five modules that use them pass unedited and none is skipped; corpus snapshot and run-reference digests identical, five fixture sources compile to new digests. Reviewed by the coordinator (fixture files, README and this ledger only). Gate, with a deviation recorded: the full suite ran at load average above 100 and took 64 minutes with 39 failures besides the four nanoBragg ones; rerun alone, 35 pass at four workers and one more serially; the last three (deadline and wall-budget tests) fail the same way on `main` at that load. A full suite on `main` at normal load is owed and is run before the next code merge. Coordinator slip, fixed: the merge script left the 68 files of the old recording on disk and staged in the main checkout, which made 22 fixture tests fail there; they were removed after checking each was an old fixture file, and the five modules then pass (163 of 164, the last one alone). |
