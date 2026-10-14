# Provider Result Delivery — Execution Record

Status: **delivered on branch `feat/provider-result-delivery`**; this record
is the single evidence owner for the
[plan](../plans/2026-10-13-provider-result-delivery-plan.md) and the
[design](../design/provider_result_delivery.md). Receipts are in the
machine-local evidence directory
`/home/ollie/Documents/agent-orchestration-delivery-evidence/` (E), cited
by file name. Interpreter `/home/ollie/miniconda3/bin/python` 3.13.9; every
command ran from the worktree with `PYTHONPATH` set to it.

## Selection

Owner selections on 2026-10-13: execute the plan; providers bound to `omp`
templates keep the `legacy` rendering; work in a separate worktree without
touching the main checkout's uncommitted edits. Drafting baseline `3f897f33`;
the design and plan were committed at `27792626`.

## Commits

| Commit | Task | Content |
| --- | --- | --- |
| `6a70e859`, `e5116c64` | 4 | `scripts/provider_delivery_census.py` and its tests; revision after review |
| `761acc21`, `3ff77e9f` | 5 | chess example returns `MoveOutcome`/`GameOutcome`; transport prose removed from `white.md`/`black.md`; guide §10.1; tests for both `Blocked` sides and the wrong-shape failure code |
| `139ea335` | 1 | `delivery` selector on the three structured-result renderers, default `legacy`; threaded through the evaluated composer |
| `e5f73d44` | 2 | `delivery` provider input part recorded and replayed as recorded; omp templates on `legacy`; tests (a) to (e) |
| `acfc3708` | 3 | missing-result failure message carries the head of the provider's stdout |
| `341e2464` | 1 (size) | delivery opening lines and the relpath predicate moved to `orchestrator/contracts/prompt_delivery.py` (67 lines); `prompt_contract.py` back to 450 lines |
| `aba32230` | 1 to 3 (review) | non-printable characters blanked in the reply excerpt (a NUL would have made the memo unreadable); the real Task 0 interrupted run checked in at `tests/fixtures/provider_delivery_pre_change/` and resumed through the CLI as the lasting guard that the `legacy` bytes never drift; omp rationale comment and an `omp` shim in the fixture; dead `except` removed; delivery tests moved to `tests/test_workflow_evaluated_provider_delivery.py` |

Task 6's spec, matrix, routing, design and plan amendments are in the final
documentation commit on the branch.

## Accepted Deviations From The Plan

1. **The attempt path appears once in the prompt.** The evaluated design's
   R3 rule, held by 441 tests, requires a single occurrence of the result
   path. The `file` opening therefore points at the `- path:` line instead
   of repeating the path. Design §Design Details records it.
2. **The excerpt travels in the failure message.** `specs/state.md` fixes
   `exit_info` as `{}` for `provider_result_missing`; the excerpt is in the
   exception message, which reaches the failed terminal row's `message`, the
   view's `error.message` and `report`. The design's contracts table was
   corrected.
3. **Pre-change replay is proven by construction, not by a stored run.** A
   captured run root cannot be resumed from another workspace, so test (a)
   rewrites memo rows to what the pre-change package wrote (no `delivery`
   part, `legacy` block, recomputed digests, checked against the Task 0
   interrupted run's rows), and the Task 0 run itself was resumed once as
   one-time evidence (below). No permanent test pins prompt wording.

## Task 0 — Pre-Change Captures (`task-0-report.md`)

With the unmodified package at `27792626`: six composed-prompt oracles
(`legacy_{root,record,variant}.prompt.txt` at 2.35,
`flat_{root,record,variant}.prompt.txt` at 2.34; sha256 in the report), an
interrupted two-provider run kept at `/tmp/delivery-task0/interrupted/`
(run `20261013T200020Z-4ihtxh`, memo with `started`/`committed` for `first`
only; committed `input_parts` keys `declaration`, `dependency_rows`,
`params`, `policy`, `prompt`, `source:asset_file:prompt.md`, `values`, no
`delivery`), copies under `E/interrupted-run/`, the chess `zk5mh3` memo and
Black attempt copied under `E/chess-zk5mh3/` (cmp identical), and the
baseline census `census-before.txt`.

## Baseline Census (`census-before-script.txt`)

Over the main checkout, the `-smoke`, `-rerun` and `-repl` worktrees and the
chess live workspace: **69 provider attempts, 64 committed, 4
`provider_result_missing`, 1 open**, all `legacy`. The four misses are
`white-position` ×2 (`1zoj84`), `black-position` (`zk5mh3`) and `revised`
(`p016fp`), as in the design's §Problem. The design's appendix was corrected
from the earlier hand count of 67.

## Tasks 1 To 3 — Evidence (`task-1-3-report.md`)

- After Task 1 (nothing opted in): the six captures re-run and compared with
  the Task 0 oracles are byte-identical once the run id in the `- path:` line
  is normalised (`E/task1-oracles/`).
- After Task 2: the three flat-route captures are still identical to the
  Task 0 flat oracles (`E/task2-flat-oracles/`); the evaluated captures differ
  only between the block heading and the `- path:` line, as intended.
- After the module split: the six captures are identical between `acfc3708`
  and `341e2464` (`E/revision-oracles/`), 112 shape/schema/selector
  combinations produce the same output before and after the split.
- Resume of a copy of the Task 0 interrupted run with the changed package:
  `first` reused with no dispatch; `second` dispatched once, its rows carry
  `canonical_sha256("file/1")`; terminal value `{"ok": true}` equals the
  uninterrupted run's.
- Narrow owners: Task 1 modules 292 passed, Task 2 modules 289 passed, Task 3
  modules 65 passed; after the split the five renderer/replay modules pass
  (323 tests).
- `baseline` (the latest `started` row with no active commit) is used for
  providers only by the launch-cwd check; nothing compares a new attempt's
  `prompt` or `delivery` part with a prior attempt's, so a retry after a
  `legacy` attempt records `file/1`.

## Task 4 — Census (`task-4-report.md`, `task-4-review.md`)

Review: CHANGES REQUIRED (pairing by attempt untested; counts mixed
renderings; `orchestrator` import for two digests). Revision `e5116c64`:
retry fixture catches identity-only pairing (2 of 8 tests fail with it),
counts keyed by site, delivery and outcome with a per-delivery total,
stdlib digests equal to `canonical_sha256` for both names, `errors="replace"`,
non-object lines skipped with a stderr note. Re-review: **PASS**. 8 tests;
baseline unchanged at 69/64/4/1.

## Task 5 — Authoring And Chess (`task-5-report.md`, `task-5-review.md`)

Review: **PASS**, with the condition that nothing from Task 5 is merged or
smoked before Task 2 lands (met: the branch merges as one). Follow-ups in
`3ff77e9f`: Title Case heading, `Blocked` tested for Black as well, negative
tests assert `provider_result_invalid`. 7 tests pass; the example compiles
with its header command and dry-runs with its inputs.

## Smoke — One Real Chess Round (`smoke-chess.log`, `E/smoke-run/`)

Run `20261013T211100Z-tjsi1z` in the worktree, White `gpt-6.1-sol`, Black
`claude-fable-5-1`, `rounds=1`, board `artifacts/agent_chess/smoke-20261013.md`,
exit 0. Both providers wrote the result file on attempt 1 and committed
`Moved`; both `started` rows carry `delivery = canonical_sha256("file/1")`;
the composed blocks open with the write action, keep a single `- path:`
line and carry no relpath guidance (no path type in `MoveOutcome`); the game
ended `Finished` after 1. e4 e5. Memo sha256 `ad62551049ce2ee4…`.

## Full Suite (`suite-final.log`, `suite-final-failures.txt`)

`pytest -q -n 16 --dist=worksteal -m "not e2e"` on the final tree
(`341e2464` plus the uncommitted documentation of this record): **274
failed, 23,953 passed, 7 skipped, 170 xfailed, exit 1, 24 min 51 s**.
Against the branch baseline taken at `139ea335` before the evaluated route
opted in (271 failed, `task1-3-suite/baseline_139ea335_failures.txt`):

| Class | Count | Disposition |
| --- | --- | --- |
| Common with the baseline | 269 | Pre-existing RED: 240 in `tests/experiments/test_es_*` and the rest in `wcc_characterization`, `key_migrations`, `procedure_first_migrations`, `checkpoint_identity_comparison`, `shared_validation`, `procedures`, `drain_roadmap_routing` (the known 2.36/2.37 bound), `evaluated_programs`, `view_publication`, `provider_isolation_backend*`, `es_*`; none touches the changed owners |
| In the baseline, not in the final run | 2 | `test_prompt_resume_child.py` load flakes: the module passes 57 of 57 alone (`prompt-resume-child-standalone.log`) and had no failure in the final run |
| New in the final run | 5 | `test_workflow_evaluated_watchdog_watcher.py` ×4 and `test_workflow_evaluated_view_publication.py::test_real_writer_tail_liveness_and_immediate_interruption[last]`: liveness and parity timing under `-n 16`; all 5 pass when rerun serially (`suite-new-failures-rerun.log`, 5 passed in 98 s) |

No assertion was relaxed and no test was removed. The remaining RED is the
same `tests/experiments/test_es_*` family the main checkout carries.

## Reviews Of Tasks 1 To 3 (`task-1-3-review.md`)

Independent review of `139ea335`, `e5f73d44`, `acfc3708` and `341e2464`:
**CHANGES REQUIRED** with two blocking findings and seven notes. Verified by
the reviewer: `legacy` byte-identical to the Task 0 oracles for all three
renderers through the public `run`; the flat route untouched; 3,888
renderer cases equal across the old module, the default and `legacy`; the
`file` block action-first with a single path occurrence and relpath guidance
iff a relpath type is present at any depth; the real Task 0 run resumed at
HEAD with `first` reused and `second` recording `file/1`; an unknown digest
refuses before launch; a failed pre-change attempt retries with `file/1`.

Blocking: (B1) a NUL byte in provider stdout reached the terminal row's
message through the excerpt and made the memo unreadable
(`memo_inconsistent` on `report` and `resume`), a regression; (B2) the
`legacy` and `file/1` texts had become replay identity with nothing guarding
an in-place edit, because the pre-change replay test built its row with the
current renderer. Both fixed in `aba32230`: non-printable characters are
blanked before the excerpt is built (a NUL/ANSI case now asserts `report`
exits 0 and `resume` dispatches attempt 2), and the real Task 0 run is
checked in under `tests/fixtures/provider_delivery_pre_change/` and resumed
through the CLI; changing one word of the legacy text or of the relpath
guidance fails that test with `effect_input_diverged` on `prompt`. Notes N3
to N6 (omp rationale comment, `omp` shim ahead of the real binary, dead
`except`, provider test module over 500 lines) were applied in the same
commit; notes N1 and N2 (the evaluated design's parity statements, spec and
plan wording) were applied by the coordinator. Re-review: **PASS**. Two
remaining non-blocking notes are recorded in the review: no fixture pins
the `file/1` text yet (the docstring rule protects it until `file/2` is
considered), and the R3 row of the evaluated design, since amended.

Coordinator verification on `aba32230`: the owner modules
(`test_prompt_contract*`, `test_workflow_evaluated_{prompts,providers,provider_delivery,resume_replay,views,public_identity}`,
`tests/experiments/test_agent_chess.py`, `test_provider_delivery_census.py`)
collect and pass, **384 passed** (`narrow-owners-final.log`).

## Affected-Module Campaign On `aba32230` (`affected-final.log`)

`pytest -q -n 16 --dist=worksteal` over `tests/test_workflow_evaluated_*.py`,
`tests/test_prompt_contract*.py`, `tests/test_prompt_resume_child.py`, the
chess and census modules: **2 failed, 2,679 passed, 11 min 6 s**.

| Failure | Disposition |
| --- | --- |
| `test_workflow_evaluated_programs.py::test_growth_selectors_take_both_arms_and_counters_change_after_seeds` | Pre-existing: in the branch baseline list and in the final full suite; unrelated owner |
| `test_workflow_evaluated_durability_model.py::test_lost_authority_with_journal_refuses_without_reconstruction_or_launch[preexisting-roots]` | Environment-dependent, not caused by this delivery: it passes alone (`1 passed in 4.03 s`), fails together with its sibling `test_authority_survives_loss_of_unsynced_writes[preexisting-roots]` inside the module with `OSError: cannot open run root …/images/010/ws/.orchestrate/runs/<id>: cannot open directory root component: symlink or non-directory` (`durability-module-rerun.log`), and the sibling fails with the same error on the pre-change commit `27792626` in a detached worktree (`1 failed, 5 passed in 104 s`). The failure sits in the test's filesystem-image topology under `/tmp/pytest-of-ollie`, which this machine's pytest temp state is known to disturb (undeletable `garbage-*` roots); no code of this delivery touches run-root creation or authority |

## Limits

- The census after the change is the smoke round only (2 attempts, 0
  missing). The design's measurement criterion (ten attempts per site with
  the same models) is not met by this delivery and remains open; the
  rendering is adopted on the principle-30 argument and the structural
  evidence above, not on a measured reduction.
- Providers bound to `omp` templates render `legacy` and were not exercised
  live.
- The main checkout's `.orchestrate/runs` still holds the baseline chess run
  `1zoj84`; an after-census over that root must be read per delivery name.
