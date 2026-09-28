# CF-1 Runtime Prerequisite Repair Plan

> **For agentic workers:** use `superpowers:subagent-driven-development`;
> implement with TDD, then obtain independent contract and quality reviews.

**Goal:** exhausted Workflow Lisp loops return the last committed `continue`
state, including through nested match bodies and committed-boundary resume.

**Architecture:** use the loop's already-resolved declared outputs as the
state authority. Remove the redundant overwrite in
`LoopExecutor._exhaustion_frame_artifacts`; consumer and older-target checks
confirm that no second selector is needed. Preserve validation of actual output sources
and resume identities; add no new state schema, source syntax or evaluator.

**Tech stack:** Python, pytest, existing Workflow Lisp compiler/executor/CLI.

## Authority and scope

- Contract: `specs/dsl.md`, rich loop values; the
  [composition design](../design/workflow_lisp_composition_first.md) §§4, 9–10.
- Selection: [CF-1](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected),
  prerequisite selector repair before CF-1b.
- Reproduction: [exhaustion check](../reports/2026-09-28-cf1a-exhaustion-projection-check.md).
- Worktree: `.worktrees/cf1-exhaustion-selector`, starting at `da7989c0`,
  with the other session's partial selector repair preserved for completion.

The existing selector recognizes `*__continue__state` updates but misses the
failing route's `*__body__<arm>__state` under a dotted match-body key. The WIP
name-refinement fix raises a false ambiguity between entry and terminal state.
More importantly, a fresh diagnostic shows the resolved `frame_artifacts`
already contain the correct final score 3; bypassing the selector preserves it.
`_loop_repeat_outputs_from_terminal` declares the terminal references, and
`execute_repeat_until` resolves them before exhaustion. Prefer that existing
dataflow over discovering snapshots by name. Retain any genuinely necessary
compatibility behavior only with a failing executable consumer proving it.
Do not recursively scan arbitrary artifacts or nested iteration history, or
choose by map order. Entry state and a terminal value are not ambiguous peers.

Out of scope: generic unions, `std/improve`, type-version decisions, removal of
`ctx`, the pure-inline-hook frontend defect, and unrelated worktree changes.
Command-backed deterministic review hooks avoid the known frontend limitation.
Retaining current persistence/compilation contracts means new execution-node
shapes will still need their own evidence; no general state-discovery framework
is introduced.

## Task 1 — Repair selection and verify its real consumers

**Files:**

- Modify `orchestrator/workflow/loops.py` at the exhaustion selector and its
  call site; deleting the helper is preferred if existing output resolution
  covers all consumers.
- Extend `tests/test_workflow_loops_exhaustion_state.py`.
- Extend `tests/test_workflow_lisp_generic_state_exhaustion.py`; reuse nearby
  public run/resume patterns from `test_workflow_lisp_rich_loop_values_e2e.py`.
- Add `tests/test_workflow_lisp_generic_exhaustion_resume.py` for the public
  checkpoint-boundary regression without duplicating the generic source.
- Correct the stale final-count expectation in
  `tests/test_workflow_lisp_loop_recur.py` only if contract review establishes
  it encoded the same off-by-one bug rather than a versioned behavior.
- Update the internal context double in `tests/test_workflow_lisp_run_ref.py`
  when adding the enclosing output-target field; keep its assertions unchanged.
- Put the ordinary `std/phase` regression in that existing exhaustion module
  unless a clearly reusable fixture already owns it. Do not alter stdlib APIs.

- [x] Reproduce the multi-iteration failure with the marker removed or
  `--runxfail`; record actual expected/observed final values.
- [x] Trace the only selector call, lowered terminal output contracts, and
  nested execution results. Add a failing control with correct resolved outputs,
  stale entry state and a nested update. Cover multiple iterations, skipped
  arms, single iteration, unrelated nested state and normal `done`. Zero is
  not an admitted loop bound; the retired helper's `current_iteration == 0`
  control actually represented the first iteration.
- [x] Implement the smallest shared-owner correction, preferring removal of
  redundant snapshot selection. Check prior targets and real stdlib consumers.
  Replace tests of obsolete name-selection mechanics with behavioral dataflow
  assertions, not weaker expectations. Preserve existing errors for invalid or
  ambiguous declared sources/identities; do not invent ambiguity among unrelated
  snapshots or silently fall back from a missing required output.
- [x] Remove the strict `xfail` after the original scenario passes. Exercise
  at least two and three iterations, checking the actual returned value.
- [x] Compile and execute the ordinary imported `std/phase` review helper with
  distinct per-iteration report/findings paths and at least two revisions.
  Assert exhaustion returns the final review metadata, not the prior iteration.
  Keep the real findings validator, with valid local artifacts and fake command
  or provider hooks; no live provider is needed.
- [x] Correct the mixed-target projection defect exposed by that consumer:
  imported target-2.14 `std/phase` discards explicit output source paths while
  the enclosing target-2.32 runtime interprets the resulting `/result` pointers
  literally. Thread the enclosing emitted target through the existing lowering
  context and use it for generated projection layout. Keep the definition's
  type environment authoritative for source admission and expression semantics.
  Check all context constructors, old-target emitted mappings, and execution
  of the ordinary imported helper. No library-name exception or target bump.
  Future context constructors must preserve both distinct target roles.
- [x] Add a public run/resume integration check for the generic-record path,
  interrupting after committed updates, preferably after the last update but
  before exhaustion publication. Assert final values agree with a fresh run and
  already committed hook calls are not replayed. Reuse existing checkpoint
  hooks and fixtures; no admission overrides or state repair in the test.
- [x] Run collect-only on changed test modules, then narrow tests:

```bash
python -m pytest --collect-only -q tests/test_workflow_loops_exhaustion_state.py tests/test_workflow_lisp_generic_state_exhaustion.py
python -m pytest -q tests/test_workflow_loops_exhaustion_state.py tests/test_workflow_lisp_generic_state_exhaustion.py
```

Expected: all pass, no remaining regression `xfail`. Review the actual diff
for contract compliance, then separately for correctness and minimality.

## Task 2 — Integration, wider verification and status

- [x] Run adjacent loop, rich-value/resume and imported-stdlib suites, then the
  full suite, in tmux using `python -m pytest -q -n 16 --dist=worksteal`.
  On this storage-constrained host, add `-o tmp_path_retention_policy=failed`
  so passing tests release their temporary trees; this changes retention only,
  not collection or assertions.
  Record unrelated baseline failures; reproduce them against the clean base
  before attributing them. Do not weaken assertions to obtain green results.
- [x] Inspect the final diff and integrate only the scoped files into the
  shared checkout, preserving concurrent changes. The owner subsequently
  requested staging and committing only this scoped patch.
- [x] Append fresh evidence to the existing exhaustion report and this plan.
  Update only the relevant CF-1 roadmap/status/catalog wording after tests
  establish the correction. Preserve the original defect report as history and
  coordinate documentation edits with the other session's CF-1b planning.
- [x] Keep the remaining CF-1a decisions and future generic-union acceptance
  separate. This fix does not implement CF-1b or prove its whole contract.
- [ ] Close the master plan's full-suite **no-new-failures** gate. The final
  comparison has one additional provider-cancellation failure; its unchanged
  module passes isolated in both temporary-storage layouts. Cause is not
  established. Do not waive this gate or expand this bounded runtime repair
  into provider-control work without an owner decision.

## Task 3 — Remove ambiguous selection in the affected runtime paths

Owner follow-up: eliminate smells such as brittle selectors. Keep this bounded
to the exhaustion/output-resolution and immediate checkpoint-restoration paths,
not a repository-wide rewrite. The owner explicitly confirmed this scope:
"Cerrar el trabajo actual y sus rutas afectadas." Inspect each consumer before
changing it.

- [x] Separate resolved artifacts from resolver failure explicitly. The shared
  output resolver currently returns either as a plain dictionary, and its three
  consumers (`repeat_until`, structured `if`, structured `match`) mistake a
  failure for data. Use an ordinary `(artifacts, failure)` return at this private
  boundary and update its runtime protocol and all consumers together. Do not
  classify user data by keys such as `status` or `error`. Test a missing required
  output and valid outputs with envelope-like field names.
- [x] Preserve the existing committed-frame resume authority when the validated
  checkpoint replaces the iteration body. Do not resolve outputs again from
  the retired body. Keep ordinary output resolution and failure propagation for
  every non-restored iteration. Legacy declared result aliases remain bindings
  resolved and validated by their downstream normalizer, not an exhaustion-time
  evaluator or a new checkpoint validation scheme.
- [x] Preserve the already-emitted exact source identity when activating a
  lexical restore overlay; stop searching binding-name substrings or accepting
  arbitrary proof-source suffixes. Resolve through the existing projection and
  validated descriptors. Do not introduce a checkpoint schema, longest-name
  preference, ordering rule, or compatibility guessing path. Test colliding
  names, reordered candidates and normal public restoration.
- [x] Examine the same overlay's example-specific `return__count` /
  `return__label` handling against its declared loop/result mappings. Remove
  any redundant publication path or use the existing output contracts if a
  real consumer needs it; do not generalize by scanning field names.
  Reconstruct captured producer artifacts by following the existing compiled
  `value_document` reference leaves back from the captured binding value.
  Traverse document/value pairs under the existing checkpoint grammar; the
  replay walker has a different grammar and rejects valid record fields named
  `ref`. Do not execute a second evaluator or infer a completed result from
  loop state. Match reads retain selector validation.
- [x] Obtain contract and quality review after these changes, rerun collection,
  focused negatives/public resume and adjacent runtime suites, then compare the
  broader core suite with the same baseline selectors. Record full-suite
  infrastructure limitations separately, never as passing evidence.

These changes make malformed or source-less restoration metadata ineligible
for guessed overlay values; supporting such a shape later requires an explicit
identity contract. No authored syntax, target version or persisted schema is
added. Evidence of a required schema/API expansion must stop this bounded task
for a design decision rather than justify another name-based fallback.

## Execution evidence

The reviewed scoped patch is integrated into `main`. All **725
adjacent tests pass**. Full verification ran, but the master plan's strict
no-new-failures gate remains open: one additional provider-cancellation failure
appears under the full workload despite its unchanged module passing isolated.
Astra reviewed the owner-level approach; Luna and the coordinator implemented
the runtime/tests; separate Sol reviews checked contract and quality.

- Original baseline `da7989c0`: `python -m pytest -q --runxfail
  tests/test_workflow_lisp_generic_state_exhaustion.py` gives **1 passed,
  1 failed**; three revisions return score 2 instead of 3.
- Handed-off WIP `b48f1fe3`: both narrow modules give **10 passed, 1 failed**;
  the name-refinement selector reports false ambiguity between entry and nested
  terminal state. That partial fix is not accepted implementation.
- A temporary diagnostic bypass of the overwrite returns score 3 and the
  three-times revised title. Before the overwrite, both resolved frame outputs
  and the executed match body's outputs already carry score 3. No source change
  was made for that diagnostic.
- After deleting the redundant selector, the coordinator reran the original
  regression module: **2 passed in 1.45s**. Adjacent checks gave **98 passed,
  1 failed**: the target-2.14 scalar fixture expected count 1 after two
  increments, whereas the corrected result is count 2 with the final reason.
  Astra independently confirmed that the expectation encodes the same bug:
  `specs/dsl.md` requires completed-iteration outputs, and the frontend requires
  the last materialized loop-frame outputs. Pre-2.29 compatibility preserves
  admission and emitted mappings, not returning the penultimate value. Keep
  the generated-reference checks and correct only the final count/reason.
- Adjacent baseline tests in `.worktrees/cf1-runtime-baseline` at `da7989c0`:
  **99 passed in 6.57s**, exit 0, with `python -m pytest -q -n 16
  --dist=worksteal` over `test_workflow_lisp_loop_recur.py`,
  `test_workflow_lisp_loop_state.py`, `test_workflow_lisp_rich_loop_values_e2e.py`,
  `test_workflow_lisp_generic_stdlib_composition.py`, and
  `test_workflow_lisp_imported_stdlib_loop_exhaustion_post_loop_terminal.py`.
- The first full baseline run was interrupted after exhausting `/tmp` while
  cloning test repositories. Its failures are not usable baseline evidence.
  Only its owned `/tmp/pytest-of-ollie/pytest-22` tree was removed (8.3 GB);
  `/tmp/cf1-runtime-baseline-full.log` was retained. Subsequent full checks use
  pytest's built-in failed-only temporary retention to bound storage use.
- The two full-suite retries also exhausted temporary storage; failed-only
  retention does not bound session fixtures or failed test clones. The final
  retry was stopped and its owned temporary tree removed; all logs remain in
  `/tmp/cf1-runtime-baseline-{full,retry,clean}.log`. None is a usable full-suite
  baseline. The owner's ImageNet archive was explicitly excluded from cleanup
  and remains untouched. No complete-suite passing claim is made.
- The complete non-experiment baseline (`tests --ignore=tests/experiments`,
  excluding the newly copied resume probe) finished without storage failure:
  **13,533 passed, 21 failed, 35 skipped, 1 xfailed, 3 errors**, 100.90s.
  Log: `/tmp/cf1-runtime-baseline-core.log`. This is a core-suite baseline, not
  a substitute claim that the experiments passed.
- The new public run/resume check interrupts after all three review calls and
  the final committed false condition. The old runtime already resumes to
  score 3 without replay, but a fresh run returns 2; the test fails on that
  mismatch. With the selector removed, both return score 3, **1 passed**.
- Output-boundary red/green: missing outputs in `if`, `match` and `repeat_until`
  previously completed as error-shaped data (**3 failed, 1 passed** including
  the valid envelope-like-fields control). Separating artifacts/failure makes
  all four pass. A fifth control feeds corrupted producer data through an
  otherwise valid compiled output contract and preserves `invalid_output_value`.
- After output separation, nine adjacent modules including public resume and
  structured control flow pass: **176 passed in 5.48s**; log
  `/tmp/cf1-runtime-adjacent-v2.log`. Collection of the five changed/new test
  modules at that point: **76 tests collected**. This predates overlay cleanup.
- The ordinary imported `std/phase` test exposed a separate mixed-target
  projection defect: a target-2.14 inline definition emitted `/result` for
  each field, while its target-2.32 enclosing executable requires explicit
  source paths. Keeping the emitted target separate from the definition's
  type environment corrects the layout without changing source admission.
  The exhaustion module now passes all **4 cases**, including three genuine
  revisions with the real findings validator and distinct review artifacts.
- After that emitter correction, the expanded adjacent/replay checks give
  **324 passed in 9.47s**; projection/cache/pure-call checks give **75 passed
  in 4.83s**. Logs: `/tmp/cf1-runtime-emitter-check.log` and
  `/tmp/cf1-runtime-projection-check.log`. These precede overlay cleanup.
- Full baseline using executable `/dev/shm` temporary storage completed:
  **15,985 passed, 455 failed, 36 skipped, 1 xfailed, 5 errors**, 459.74s;
  log `/tmp/cf1-runtime-baseline-ram.log`. No disk-full errors occurred.
  This environment has additional failures: provider-isolation admission
  deliberately rejects roots under `/dev`, and longer temporary paths exceed
  some Unix-socket limits. These are not asserted to be project defects.
  Compare the candidate under the same temporary layout, and separately
  compare the full non-experiment suite in ordinary disk-backed temporary
  storage. Neither comparison is an all-green full-suite claim. The earlier
  disk-full attempts remain invalid verification evidence.
- Independent pre-overlay contract review: **23 passed in 10.85s**, covering
  exhaustion, ordinary `std/phase`, public resume, structured output failures,
  rich unions, nested match execution, `done`, and older-target admission.
  Independent quality review found no outstanding issue in the selector
  deletion, resolver boundary or emitted-target correction. Both reviews must
  still cover the final overlay diff.
- The tuple correction exposed a previously masked sidecar-resume error:
  `restored_iteration_complete` skipped the retired body, then resolved its
  absent outputs. The existing positive resume test reproduced the failure.
  Reusing the committed frame in that guarded path matches the existing
  successful-condition resume authority; **11 focused controls pass**.
  A proposed extra revalidation against the loop-frame contracts was rejected:
  target-2.14 `result__*` slots can contain declared reference bindings, which
  the ordinary downstream normalizer resolves and validates. Treating those
  slots as already-normalized scalar values would reinterpret old mappings.
  The checkpoint validates progress and carried state, not every result slot;
  no exhaustive-frame-validation claim is made.
- Final overlay correction uses exact compiled producers and declared artifact
  members. It removes binding substrings, proof suffixes, synthetic loop-result
  aliases and example-specific fields. A public record-field `ref` regression
  exposed an incompatible replay walker; the final local document/value-pair
  traversal respects the existing checkpoint grammar without an evaluator.
- Final independent contract review: **33 passed in 11.75s**, **207 collected**,
  no outstanding finding. Final quality review: **9 passed in 3.11s**, no
  outstanding finding. Both include `ref`, renamed `done` values, exact source
  and selector guards. The implementer's full lexical-restore module has
  **128 passed in 11.07s**.
- Coordinator final adjacent check: **263 passed in 14.32s**, using `-n 16
  --dist=worksteal`; log `/tmp/cf1-runtime-final-adjacent.log`. Selective
  integration preserved all unrelated dirty files. Fresh `main` integration
  checks: **8 passed in 24.54s**, including real imported `std/phase`, public
  generic run/resume, and source identity/record `ref`.
- A fresh pre-integration `main` core baseline completed with **13,551 passed,
  7 failed, 35 skipped, 1 xfailed, 3 errors**, 137.57s; log
  `/tmp/cf1-main-baseline-core.log`. This differs from the isolated worktree
  baseline because the checkout, external fixtures and concurrent unrelated
  work differ. Compare final `main` core against this baseline, not raw counts
  across different environments. Full `/dev/shm` comparison remains separate.
- The first integrated core run had **13,558 passed, 11 failed, 3 errors**;
  log `/tmp/cf1-main-core.log`. It exposed two missing-field errors in the
  `run-ref` test double and one real flattened-union resume regression.
  Updating the double preserves every assertion. Binding validation now uses
  the exact declared member for singleton references and retains the existing
  compiled descriptor checks for composite values, rather than applying a
  single-slot contract to the whole union. The existing public design-delta
  wrapper resume test reproduced **1 failed** against **1 passed** on the
  clean baseline, then passed after correction without replay.
- Exact-source validation now corroborates the local ID through the IR's
  declared lexical scope, without assuming a root-level prefix. Nested-scope
  controls failed before that change and pass afterward. Final independent
  contract review gives **16 passed in 16.90s**; quality review gives
  **6 passed in 17.59s**. No source syntax, persisted schema or replay evaluator
  was introduced.
- Expanded final adjacent check on `main`: **725 passed in 26.89s**, over
  thirteen modules including the entire `run-ref` and procedure-first suites;
  log `/tmp/cf1-main-final-adjacent.log`. Final collection across all eight
  changed/new test modules: **497 collected in 4.11s**.
- Four additional non-DSL failures in the first core run passed when rerun
  separately (**4 passed in 3.31s**, `/tmp/cf1-nondsl-main-narrow.log`);
  their provider code and tests are unchanged from the clean baseline.
  The first full `main` comparison had **16,156 passed, 332 failed, 5 errors**,
  613.68s, in `/tmp/cf1-main-full.log`. Beyond the three corrected DSL/test-double
  failures, its additional IDs were the previously recorded Q5 failure and
  four non-DSL cases that passed separately (**4 passed in 4.47s**,
  `/tmp/cf1-nondsl-full-narrow.log`). Do not attribute those cases causally to
  concurrency without further evidence. Neither earlier comparison is an
  all-green claim.
- Final full run on `main`, after all scoped corrections: **16,165 passed,
  325 failed, 36 skipped, 5 errors**, 350.28s; log
  `/tmp/cf1-main-full-final.log`. Command: `TMPDIR=/dev/shm/cf1-candbase-Xq5oBt
  python -m pytest -q -n 16 --dist=worksteal
  -o tmp_path_retention_policy=failed tests`. The temporary-root prefix has
  the same length as the full baseline's. Of its 330 failure/error IDs, 329
  also occur in `/tmp/cf1-runtime-baseline-ram.log`. The one additional ID is
  `tests/test_provider_execution_control.py::test_large_unread_controlled_stdin_cannot_block_cancellation[bound]`.
  It also failed in the first integrated full run, so it is not dismissed as
  a one-off. Its production code and test are unchanged from `da7989c0`.
  The entire module passes isolated: **75 passed in 4.66s** with ordinary
  disk-backed temporary storage, and **75 passed in 5.10s** with the final
  full run's RAM-backed `TMPDIR`; logs `/tmp/cf1-final-provider-control.log`
  and `/tmp/cf1-provider-ram-control.log`. These controls do not prove the
  cause or close the strict full-suite gate.
- Final documentation routing checks: **70 passed, 1 failed in 5.90s**;
  log `/tmp/cf1-docs-final.log`. The failure is the pre-existing
  `test_historical_q2_index_routes_current_selection_to_evolution_entry_gates`,
  outside the edited CF-1 section. No assertion was weakened.
- Owned temporary test trees were removed after their runs finished; logs
  were retained. They are regenerable test data, not project assets. The
  owner's `/tmp/ILSVRC2012_img_train.tar` remains untouched (147897477120 bytes,
  modification time `2026-09-01 12:07:51.734352649 -0700`).
