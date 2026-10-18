# ORC Structural Search Phase 2 (I2 And Adaptive Search) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare Phase 2 of the [structural search roadmap](2026-10-18-orc-structural-search-roadmap.md) offline (I2 locus-plus-fragment episodes over the implemented site manifest, the mode-2 adaptive loop with an archive, per-generation blind judging and a validation split) so that a live run can start the day Phase 1's readout selects Phase 2, and stops cleanly if it does not.

**Architecture:** Extend `experiments/orc_structural_search/` only: a `sites.py` helper builds the manifest with the runtime's own orchestrator in a subprocess, derives the I2 receipt from the final diff and feeds the existing `validate_one_site`; `driver.py` gains one `run_episode` for both interfaces; a new `adaptive.py` holds the archive, parent and site selection, generations and judging, reusing `scoring.pool_evaluations`, `join_scores` and the harness's judge scripts; `scoring.py` gains the Phase 2 readout under a frozen `criteria/phase2.json`. Nothing under `orchestrator/` changes.

**Tech Stack:** Python 3.13 standard library; `orchestrator.workflow_lisp.source_sites.build_manifest` (in-process, runtime copy); `experiments/compare` shims, `pool.py`, `summarize.py`, `score.orc`; tests with scripted providers, a scripted mutator and a scripted judge (no provider is called).

**Spec:** `docs/design/orc_structural_search_driver.md` (Proposal Interfaces I2, Edit Validation And Transactions, Search Modes mode 2, Objective/Selection, Records, Controls); `docs/design/workflow_lisp_source_site_inspection.md` §3; roadmap Phase 2 Gates and Decision Points; `docs/plans/2026-10-18-orc-structural-search-live-phase1-plan.md` (allocation, roots, scoring join).

## Selection Gate

Phase 2 is selected only when `scoring.phase1_readout` reports `phase2_selected: true` (rule `separated`) on the Phase 1 evidence root. Tasks 1–5 are offline and run regardless. If the readout does not select Phase 2: Task 6 is not started, the live runtime worktree `RT` stays pinned at the Phase 1 commit (this plan's code is never re-pinned into it), the Phase 1 report records "Phase 2 not selected: <rule>", and the branch keeps the offline apparatus for a later family. No live step runs before the owner approves the budget below.

## Decisions

1. **I2 site selection: uniform over eligible manifest sites of the parent's mutable definitions**, drawn with a `random.Random` seeded from `(run_seed, episode_index)`. Reason: the driver design starts uniform and makes feedback targeting a compared condition; a seeded draw gives the Phase 2 gate its "reproducible adaptive search" without a replay mechanism.
2. **The manifest is built by a subprocess running the runtime's copy of `sites.py` with `PYTHONPATH=<runtime>`** (`python -P -m experiments.orc_structural_search.sites ...`, the pattern of `candidates.compile_candidate`); the helper compiles in-process with `prepare_closed_program_bundle` and calls `build_manifest`. Reason: the driver must never import an orchestrator other than the runtime that evaluates the candidate, and the runtime worktree is the same branch, so the helper exists there.
3. **The receipt is derived from the final diff**, never written by the agent: the replacement is the child's subtree at the parent site's index path, supporting declarations are top-level definitions the child adds, the hypothesis is the first line of an optional `HYPOTHESIS.txt` in the workspace (excluded from patches like `EPISODE.md`) or `unavailable`. `validate_one_site` is reused unchanged; after compilation the slot check compares the child manifest's `result_type.canonical` at the replacement's start with the parent site's. A replacement that is not an indexed kind (a literal, a record constructor) gets `slot_type_unavailable` and is refused. Reason: the manifest is the only typed fact source the design admits; a REPL `:type` fallback cannot see `let*` bindings. The ceiling (literal replacements refused) is recorded in the readout's refusal table.
4. **I1 and I2 interleave within one run** (each generation: I1, I2, I1, I2), sharing the archive and the judge batches; every figure is reported per interface, never pooled. Reason: Phase 2 asks whether feedback-guided search works and whether I2 avoids collapse; the equal-budget interface comparison is Phase 3's pre-registered three-arm test. Phase 2 therefore makes no efficiency claim between interfaces.
5. **A generation is 4 episodes**; accepted children are evaluated once on each adaptive task, then judged in one blind batch per task (at most 8 clones plus both anchors: 4 children fit beside the generation-0 incumbent clone), both judges, scores joined by `scoring.join_scores`. Judge calls enter the ledger (`kind: "judge"`, planned `len(judges)` per batch). Reason: the archive needs scores before the next generation; the harness's D4 batch size and anchor rule are kept as they are.
6. **Archive = incumbent plus at most 6 frontier members**: non-dominated on (mean judged value over the adaptive tasks, higher; mean provider calls, lower); a child enters when it is non-dominated after insertion; the incumbent is the highest mean (ties: fewer calls, then earlier id). The archive starts from Phase 1's joined catalog rows as *prior* evidence (not replicates; their cost stays in Phase 1's ledger); generation 0 re-evaluates the incumbent once per adaptive task so each run measures it fresh. Parent selection is uniform over the archive. Reason: design "Search Modes" and Phase 2 gate on cached evidence.
7. **Feedback in the brief is the parent's own evidence only**: judged mean per adaptive task with n, and per evaluation the outcome, terminal `Outcome` variant, provider calls and wall clock. Never the hidden fraction, another candidate's score, or any path under the evidence root. Reason: the mutator must not learn the holdout or the archive (contamination scan patterns stay valid).
8. **Splits**: adaptive = rung 2 `resume-projection-integrity` and rung 4 `pure-result-replay` (Phase 1's tasks, so the seeds' prior scores are on them); validation = rung 1 `cf1-generic-unions`, passed to every scan as a `holdout` root and never to an episode or adaptive evaluation; finalists = the top 2 of each run's final archive by mean value (ties: fewer calls), plus the reference seed (the initial incumbent) and `direct` when distinct, each replicated twice on validation. Final choice: `records.final_choice` under `criteria/phase2.json` with `validation_success` = mean validation value, `mean_cost` = mean wall clock seconds (no metered cost exists; the criterion says so), `mean_cost_ceiling` 14,400, `equivalence_tolerance` 0.5 rubric points, `provider_calls` = mean calls. Shrinkage = screening mean minus validation mean per finalist.
9. **Sealed holdout**: none opens in Phase 2. Phase 3 needs either rung 3 `adopted-attempt-lineage` after a third calibration sample (mean 1.0 over two patches is borderline) plus its `seed/dev-check.json`, or a new package built under the ladder rule; this plan names the need and builds neither.
10. **Models**: mutator `claude -p --model claude-opus-5-5 --permission-mode bypassPermissions` behind the shims; judges `claude-opus-5-5` and `gpt-6-sol`; never Fable.

## Budget For Owner Approval

Assumptions (stated so the owner can reject them): acceptance 0.6 per episode (Phase 1 measures it; range 0.4–0.8 shown), 4 provider calls per evaluation (seed maxima 1–10; children of `direct` 1–4), resume factor 1.3 on evaluation calls, 2 judge calls per batch, evaluation wall clock 1.2–1.6 h (E-B3: 4,347–5,797 s), episode wall clock ≤ 1 h, evaluation concurrency 4.

| Variant | Episodes | Mutator | Evaluations (incl. gen-0 incumbent) | Judges | Validation (runs + judges) | **Total calls** | Codex share | Wall clock |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full: 3 runs × 6 generations × 4 episodes | 72 | 72 | 3 × (10 + 146) = 468 | 3 × 24 = 72 | 16 runs = 83 + 4 | **≈ 700** (575–855) | ≈ 180 (judge half of 76; reviewer/judge roles ≈ 25% of evaluation calls) | ≈ 33 h per run, ≈ 100 h for three sequential, + 6 h validation ≈ 4.5 days |
| Reduced: 1 run × 3 generations × 4 episodes | 12 | 12 | 10 + 73 = 83 | 12 | 8 runs = 42 + 2 | **≈ 150** (125–185) | ≈ 40 | ≈ 17 h + 4 h validation ≈ 21 h |

Proposed caps (`--call-cap`, all first-exhausted): full 900, reduced 200. The owner approves one variant in writing (`<E2>/budget-approval.md`: variant, cap, Codex window reading at approval, quota policy) before Task 6. Codex figures are account-wide bounds, never attributions.

## Global Constraints

- Work in `/home/ollie/Documents/agent-orchestration-search` on `feat/orc-structural-search`; no file under `orchestrator/` changes; no optimizer vocabulary (fitness, archive, selection) enters `orchestrator/`.
- Offline tasks call no provider: scripted `claude`/`codex` (`tests/experiments/orc_structural_search_support.py`), a scripted mutator and a scripted judge; sandboxed tests skip without bubblewrap as today.
- Every live agent call runs behind `experiments/compare/shim/` with the model guard; a Fable hit excludes the run.
- Live roots as in Phase 1: `RT` (worktree pinned at this plan's final commit only after selection), `W`, `E2` fresh, none under `/home/ollie/Documents/agent-orchestration*`, `/tmp`, `/dev/shm`, `/var/tmp`; `E2` is never shown to an agent; solution hashes via `--solution`; the validation package via `--holdout`.
- Missing receipts are `unavailable`, never 0; readouts use `summarize`'s clone-id join only; hidden acceptance is descriptive.
- Commits with pathspecs; no assistant attribution, no `Co-Authored-By` trailer; `pytest --collect-only` on new test modules; narrow selectors first, then `pytest -q -n 16 --dist=worksteal tests/experiments/`.
- Modules stay under 500 lines (`driver.py` is at 460: `episode_brief` moves out in Task 2).

## Review Focus

1. A child that replaces the site with a literal compiles but has no manifest type: it must be refused `slot_type_unavailable`, not accepted silently (Task 2 `test_i2_refuses_a_replacement_whose_type_the_manifest_cannot_report`).
2. A judge batch whose generation holds more than 8 children would exceed D4: the generation must split into two batches with anchors in each, never drop a child (Task 3 `test_generation_splits_more_than_eight_children_into_anchored_batches`).
3. The validation package path appears in no brief, episode workspace or adaptive evaluation (Task 3 `test_validation_task_never_reaches_an_episode_or_adaptive_evaluation`).
4. A generation refused at the call cap after its episodes ran leaves the log consistent: episodes recorded, no evaluation row, no archive change (Task 3 `test_judge_calls_enter_the_ledger_and_the_cap_refuses_a_generation`).
5. Two runs with the same `run_seed` and the same scripted outcomes draw the same parents and sites (Task 3 `test_mode2_is_reproducible_for_a_run_seed`).

---

### Task 1: Site manifest helper, site selection, brief text and receipt derivation

**Files:**
- Create: `experiments/orc_structural_search/sites.py`
- Test: `tests/experiments/test_orc_structural_search_sites.py`

**Interfaces (produces):**
- `site_manifest(root: Path, config: ExperimentConfig, *, runtime: Path) -> dict`: runs `[sys.executable, "-P", "-m", "experiments.orc_structural_search.sites", "--root", root, "--entry-workflow", config.entry_workflow, "--source-root", config.source_root, "--provider-externs-file", config.providers_file, ("--command-boundaries-file", ...), "--files", <mutable .orc files>]` with `cwd=runtime`, `env={**os.environ, "PYTHONPATH": str(runtime)}`; the last stdout line is the manifest JSON; a nonzero exit raises `RuntimeError` with the stderr tail. `main(argv)` compiles in-process (`prepare_closed_program_bundle(FrontendBuildRequest(source_path, source_roots=(source_root,), entry_workflow, provider_externs_path, command_boundaries_path, workspace_root=root), source_read_trace=SourceReadTrace())`) and prints `build_manifest(result, root=root, files=[...])`.
- `eligible_sites(manifest: Mapping, config: ExperimentConfig) -> list[dict]`: records with `eligibility == "eligible"`, owner name after `::` in `config.mutable_definitions`, `span.start.path` in `config.mutable_files`, sorted by `site_id`.
- `select_site(sites: Sequence[Mapping], rng: random.Random) -> dict` (`rng.choice`).
- `site_brief(site: Mapping) -> str`: site id, kind, start and end line, `result_type.rendered`, bindings as `name: type`, dependencies, the owner's restriction; the rule: replace exactly that form, fresh helpers only as new top-level definitions, nothing else changes, an optional one-line `HYPOTHESIS.txt`.
- `derive_receipt(parent: Path, child: Path, site: Mapping, config: ExperimentConfig, *, parent_candidate_id: str) -> Receipt`: `replacement_expression` = the child's LF-normalized text slice of the subform at the parent site's index path (`candidates._site_path` on the parent owner, `_subform` on the child owner), `""` when the path does not resolve; `supporting_declarations` = text of child top-level definitions whose `(head, name)` the parent lacks; `expected_file_digest` = `sha256:` of the parent file; `condition` = `config.condition`; `hypothesis` from `HYPOTHESIS.txt` or `UNAVAILABLE`.
- `slot_type(manifest: Mapping, owner: str, path: str, line: int, column: int) -> str | None`: `result_type["canonical"]` of site `<owner>@<path>:<line>:<column>` or `None`.

- [ ] **Step 1: Write the failing tests** (seeds under `experiments/orc_structural_search/seeds/`, runtime = the test worktree from `orc_structural_search_support.world`):

```python
def test_site_manifest_runs_the_runtime_helper_and_lists_the_seeds_sites(world):
    # plan_then_implement: 4 provider-call sites and 1 let* site of run, ids like
    # "workflow:plan_then_implement::run@plan_then_implement.orc:29:19"; file_digests has the one file
def test_eligible_sites_keep_only_mutable_definitions_in_mutable_files():
    # a manifest with an "excluded" record and an owner outside mutable_definitions yields neither
def test_select_site_is_reproducible_for_a_seed():
    # random.Random(7) twice -> the same site_id
def test_derive_receipt_reads_the_replacement_and_fresh_helpers_from_the_child(tmp_path):
    # canonical_form(read replacement) == canonical_form(child subtree); one helper text; digest of the parent file
def test_derived_receipt_passes_validate_one_site_for_a_single_subtree_replacement(tmp_path):
    # validate_one_site(parent, child, receipt, config).accepted is True
def test_derive_receipt_of_a_child_that_moved_the_site_yields_a_scope_exceeded_verdict(tmp_path):
    # replacement_expression == "" and validate_one_site(...).code == "scope_exceeded"
def test_site_brief_carries_the_site_record_and_no_runtime_path(world):
    # brief contains the site_id, "Plan" (rendered type), "task: String"; str(world.runtime) not in brief
def test_slot_type_reads_the_canonical_identity_at_a_position(world):
    # "plan_then_implement::Plan" at (run, plan_then_implement.orc, 29, 19); None at an unindexed position
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_sites.py` — expected: ImportError.
- [ ] **Step 3: Implement `sites.py`** with the signatures above (the `main` compile mirrors `tests/test_workflow_lisp_source_sites.py::compile_source`).
- [ ] **Step 4: Run the module's tests and `pytest --collect-only tests/experiments/test_orc_structural_search_sites.py`** — expected: all PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: structural search site manifest helper, I2 brief and receipt derivation" -- experiments/orc_structural_search/sites.py tests/experiments/test_orc_structural_search_sites.py`

### Task 2: One episode function for I1 and I2 in the driver

**Files:**
- Create: `experiments/orc_structural_search/briefs.py` (`episode_brief` moved from `driver.py`, extended)
- Modify: `experiments/orc_structural_search/driver.py` (`unguided_episode` → `run_episode`; `judge_child` gains the one-site transaction and slot check; `run_mode1` calls `run_episode(..., interface="I1", mode="unguided")`)
- Modify: `tests/experiments/orc_structural_search_support.py` (add `MUTATOR_I2`), `tests/experiments/test_orc_structural_search_driver.py`

**Interfaces:**
- Consumes: Task 1's `site_manifest`, `eligible_sites`, `site_brief`, `derive_receipt`, `slot_type`; `candidates.validate_one_site`, `Receipt`.
- Produces: `briefs.episode_brief(config: ExperimentConfig, index: int, *, site: Mapping | None = None, feedback: Mapping | None = None) -> str` (the Phase 1 text, plus `site_brief(site)` under "Site" and a "Feedback" section rendering Decision 7's fields; no runtime path, no evidence path).
- `driver.run_episode(parent_root: Path, config: ExperimentConfig, *, interface: str, mode: str, agent_cmd, work_root, evidence_root, episode_index: int, runtime, env, solutions, call_cap, holdouts=(), site: Mapping | None = None, feedback: Mapping | None = None, generation: int | None = None, run_seed: int | None = None) -> dict`: as `unguided_episode`, with `interface` taken from the argument (not the config), `EPISODE.md` from `briefs.episode_brief`, `/HYPOTHESIS.txt` added to `.git/info/exclude`, and the record extended with `generation`, `site_id`, `receipt` (dict or `None`) and `feedback`.
- `driver.judge_child(parent: Path, child: Path, config, *, runtime, site: Mapping | None = None, parent_candidate_id: str | None = None) -> dict`: with `site`, `derive_receipt` then `validate_one_site` first (its codes), then frozen-surface validation and compilation as today, then the slot check: `slot_type(site_manifest(child, ...), owner, path, line, column)` at the child's replacement start versus `site["result_type"]["canonical"]`: unequal → `slot_type_changed`; `None` → `slot_type_unavailable`; the entry-result check stays last.
- `MUTATOR_I2` (support): reads the site id from `EPISODE.md`; index 0 wraps the site's provider call in `(if true <call> (record Change :summary "skipped" :account "skipped"))` (accepted, new skeleton); 1 also renames another binding (refused `scope_exceeded`); 2 replaces the call with a second `(provider-result providers.planner ...)` of the same type under a fresh `defproc` helper (accepted, a third skeleton); 3 replaces an unused binding's call with a string literal (compiles; `slot_type_unavailable`).

- [ ] **Step 1: Write the failing tests** in `test_orc_structural_search_driver.py` (fixtures `sandboxed`, `world`; a test-only `unused_binding.orc` candidate written by the test for cases 3 and the slot-type case):

```python
def test_i2_episode_records_site_receipt_and_accepts_a_single_subtree_replacement(sandboxed, world):
    # row["interface"] == "I2", row["site_id"] == the selected site, row["receipt"]["replacement_expression"] starts with "(if true",
    # row["outcome"] == "accepted", row["skeleton"] != row["parent_skeleton"]
def test_i2_refuses_an_edit_outside_the_selected_site_with_scope_exceeded(sandboxed, world)
def test_i2_refuses_a_replacement_whose_slot_type_differs(world):
    # unused binding `(x (provider-result providers.coder :prompt (p-change ...)))` replaced by a Plan-typed call:
    # judge_child(...)["refusal_code"] == "slot_type_changed"
def test_i2_refuses_a_replacement_whose_type_the_manifest_cannot_report(world):
    # the same binding replaced by "x": refusal_code == "slot_type_unavailable"
def test_two_structurally_different_i2_replacements_both_compile_and_execute(sandboxed, world):
    # indexes 0 and 2 both accepted with distinct skeletons; both evaluate to outcome "completed" with scripted providers (Phase 2 gate)
def test_the_i2_brief_carries_the_site_and_feedback_but_no_hidden_figures_or_evidence_path(world):
    # feedback {"hidden": 0.9, ...} is rendered without "hidden"; str(evidence_root) not in brief
def test_i1_episodes_still_run_through_run_episode_with_no_site(sandboxed, world)   # mode 1 regression
```

- [ ] **Step 2: Run the selectors** — expected: FAIL (`run_episode` undefined).
- [ ] **Step 3: Implement** `briefs.py`, `run_episode`, the extended `judge_child`; update `run_mode1` and existing driver tests to `run_episode`.
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_driver.py tests/experiments/test_orc_structural_search_validation.py` — expected: PASS; `wc -l experiments/orc_structural_search/driver.py` < 500.
- [ ] **Step 5: Commit** with a pathspec over the four files: `feat: I2 episodes through the site manifest and the one-site transaction`.

### Task 3: Mode 2 adaptive loop with archive, feedback and per-generation judging

**Files:**
- Create: `experiments/orc_structural_search/adaptive.py`
- Modify: `experiments/orc_structural_search/scoring.py` (`pool_evaluations(..., include: Callable[[Mapping], bool] = lambda row: True)`; `join_scores` unchanged)
- Modify: `experiments/orc_structural_search/ledger.py` docstring only (judge entries)
- Test: `tests/experiments/test_orc_structural_search_adaptive.py`

**Interfaces:**
- Consumes: Task 2's `run_episode`, `driver.evaluate_all`, `driver.archive`, `scoring.pool_evaluations`, `join_scores`, `pooling.verify_pool`, `pooling.scan_judge`, `summarize.summarize(pool, criterion)`, `ledger.reserve`/`settle`, `readout.diversity`.
- Produces, all in `adaptive.py`:
  - An archive entry: `{"candidate_id", "candidate_root", "seed" | None, "values": {task: [float]}, "mean_value", "mean_calls", "evidence": "phase1-prior" | "adaptive", "generation"}`.
  - `initial_archive(phase1_rows: Sequence[Mapping], catalog_roots: Mapping[str, str]) -> list[dict]`: from each Phase 1 task pool's `scoring.read_pool` rows (`join_scores` rows plus the failed and incident evaluations, failure-inclusive per the 2026-10-18 criteria amendment; written by the Phase 1 readout's `--joined-out <E1>/joined.json`) with `mode == "catalog"`, keyed by seed stem to this run's archived seed roots; entries carry `evidence: "phase1-prior"`.
  - `incumbent(entries) -> dict`; `frontier(entries) -> list[dict]`; `retain(entries, child, *, size=6) -> list[dict]` (Decision 6).
  - `select_parent(entries, rng: random.Random) -> dict`.
  - `feedback(entry: Mapping, evaluations: Sequence[Mapping]) -> dict`: `{"mean_value": {task: {"mean", "n"}}, "runs": [{"task", "outcome", "terminal", "provider_calls", "wall_clock_sec"}]}` from that candidate's evaluation records only.
  - `judge_generation(evidence_root: Path, generation: int, tasks: Sequence[Path], *, criterion: Path, judges: Sequence[str], solutions, call_cap: int, pool_root: Path, scorer: Callable[[Path, str], None]) -> list[dict]`: per task `pool_evaluations(..., include=lambda r: r.get("generation") == generation)` into `<pool_root>/gen-<n>/<task>`; `ledger.reserve(kind="judge", key=f"gen {n} {task}", planned=len(judges))` before scoring; `scorer(pool, judge)` per judge (default runs `bash <pool>/records/score-<judge>.sh`), then `verify_pool`, `scan_judge(pool, judge, solution)`; `summarize.summarize(pool, criterion)`; `ledger.settle(..., records=pool / "records" / "judges" / judge)`; appends `{"kind": "judging", "generation", "task", "pool", "results"}` to the log; returns the joined rows.
  - `generation(n: int, archive: list[dict], config, *, rng, adaptive_tasks, interfaces=("I1", "I2", "I1", "I2"), launch: Mapping, judge: Mapping) -> list[dict]`: per episode a parent (`select_parent`), a site for I2 (`eligible_sites(site_manifest(parent))`, `select_site`), `feedback(parent, ...)`, `run_episode(..., generation=n)`; accepted children evaluated with `evaluate_all` on the adaptive tasks (replicate 1, `split: "adaptive"`); `judge_generation`; `retain` per child; writes `<E2>/archive/gen-<n>.json`.
  - `run_mode2(config_path: Path, *, phase1_joined: Path, seeds, adaptive_tasks, validation_task: Path, generations: int, episodes_per_generation: int, run_seed: int, work_root, evidence_root, agent_cmd, runtime, env, timeout_sec, solutions, call_cap, concurrency, criterion: Path, judges, scorer=None) -> dict`: archives the seeds (`driver.archive`), builds the initial archive, evaluates the incumbent once per adaptive task as generation 0, runs the generations, writes `<E2>/readout.json` (per interface: episode outcomes, refusals, `readout.diversity`; archive trajectory). The validation task is only passed as a `holdout` root here; validation replication is `validate_finalists` below.
  - `validate_finalists(evidence_root, archive_path: Path, *, reference_seed: str, validation_task: Path, replicates: int = 2, finalists: int = 2, launch) -> list[dict]`: evaluates the finalists, the reference and `direct` (when distinct) on the validation task (`split: "validation"`); judged with `judge_generation(..., generation=-1)` semantics via `include=lambda r: r["split"] == "validation"`.

- [ ] **Step 1: Write the failing tests** (the scripted judge: the `score` helper pattern of `tests/experiments/test_compare_pool_summarize.py`, writing a completed scoring run under the judge's state directory with ratings that favour the `if`-wrapped child):

```python
def test_initial_archive_from_phase1_rows_names_the_best_seed_incumbent()
def test_retain_keeps_incumbent_and_at_most_six_frontier_members()
def test_a_dominated_child_does_not_enter_the_archive()
def test_select_parent_is_uniform_and_reproducible_for_a_seed()
def test_feedback_carries_the_parents_scores_and_run_facts_but_no_hidden_or_other_candidates()
def test_generation_judges_each_task_once_with_both_anchors_and_updates_the_archive(sandboxed, world)
def test_generation_splits_more_than_eight_children_into_anchored_batches(sandboxed, world)
def test_judge_calls_enter_the_ledger_and_the_cap_refuses_a_generation(sandboxed, world)
    # episodes logged, no evaluation row, archive/gen-1.json absent, CallCapExceeded raised
def test_mode2_interleaves_i1_and_i2_and_reports_per_interface_figures(sandboxed, world)
def test_mode2_is_reproducible_for_a_run_seed(sandboxed, world)
def test_validation_task_never_reaches_an_episode_or_adaptive_evaluation(sandboxed, world)
    # no log row with task_id == validation task and split != "validation"; the validation path is in no EPISODE.md
def test_validate_finalists_replicates_the_reference_and_direct_beside_the_finalists(sandboxed, world)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_adaptive.py` — expected: ImportError.
- [ ] **Step 3: Implement `adaptive.py`** and the `include` parameter; the archive JSON is sorted-keys, one file per generation.
- [ ] **Step 4: Run** the module's tests, `--collect-only`, then `pytest -q -n 16 --dist=worksteal tests/experiments/` — expected: PASS.
- [ ] **Step 5: Commit** with a pathspec: `feat: structural search mode 2 adaptive loop with archive, feedback and per-generation judging`.

### Task 4: Phase 2 criterion and readout

**Files:**
- Create: `experiments/orc_structural_search/criteria/phase2.json`
- Modify: `experiments/orc_structural_search/scoring.py` (`phase2_readout`), `experiments/orc_structural_search/records.py` (`control_heads`)
- Test: `tests/experiments/test_orc_structural_search_scoring.py`

**Interfaces:**
- `criteria/phase2.json`: `experiment`, `plan`, `adaptive_tasks` (rungs 2, 4), `validation_task` (rung 1), `base_commits` (three), `judges`, `judge_bindings`, `anchors` (three packages' `-upstream`/`-stub`), `scale` (`runs`, `generations`, `episodes_per_generation` 4, `interfaces` alternate, `finalists_per_run` 2, `validation_replicates` 2), `archive` (`size` 6, frontier axes), `improvement` (`min_gain` 0.5 rubric points over the parent's adaptive mean), `collapse_threshold` 0.75 per interface, `final_choice` (`mean_cost: "wall_clock_sec"`, `mean_cost_ceiling` 14400, `equivalence_tolerance` 0.5, `provider_calls: "mean"`), `hidden_acceptance: "descriptive only"`, `model_policy`, `written_before_scoring: true`.
- `records.control_heads(source: str, *, definitions: Sequence[str]) -> dict[str, int]`: counts of `if`, `cond`, `match`, `loop/recur`, `list/map-effect` heads in the named definitions.
- `scoring.phase2_readout(logs: Sequence[Path], archives: Sequence[Path], validation_pool: Mapping | None, criterion: Mapping) -> dict`: per run and interface: completed episodes, accepted, improvements (child adaptive mean − parent adaptive mean > `min_gain`), `improvements_per_episode`, `readout.diversity` over that interface's accepted rows, `collapsed`; `control_flow_changes` (accepted children whose `control_heads` differ from the parent's); archive trajectory (incumbent mean per generation); validation rows `{candidate_id, is_reference, screening_mean, validation_mean, shrinkage, mean_cost, provider_calls}`; `final_choice` via `records.final_choice`; `anchors_ok` from the validation pool.

- [ ] **Step 1: Write the failing tests**:

```python
def test_phase2_readout_counts_improvements_per_completed_episode_per_interface()
def test_phase2_readout_reports_a_control_flow_change_when_a_child_adds_a_branch()
def test_phase2_readout_shrinkage_is_screening_minus_validation()
def test_phase2_readout_final_choice_follows_the_frozen_criterion_and_includes_the_reference()
def test_phase2_readout_never_pools_interfaces()   # a run with only I2 children leaves I1 figures unavailable
def test_phase2_criterion_is_frozen_with_three_packages_and_their_anchors()
```

- [ ] **Step 2: Run** the selectors — expected: FAIL.
- [ ] **Step 3: Implement** `control_heads`, `phase2_readout` and the `readout` subcommand option `--phase 2`; write `criteria/phase2.json`.
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_scoring.py tests/experiments/test_orc_structural_search_records.py` — expected: PASS.
- [ ] **Step 5: Commit** with a pathspec: `feat: structural search Phase 2 criterion and readout`.

### Task 5: Validation package preparation and documentation

**Files:**
- Create: `experiments/compare/tasks/cf1-generic-unions/seed/dev-check.json` (`argv`: `python -m pytest -q -x -p no:cacheprovider` over the base's existing test modules of the areas `task.txt` names; `timeout_sec` 1800; hidden tests never named)
- Modify: `experiments/orc_structural_search/README.md` (mode 2 recipe, layout additions `E/archive/`, `E/pools/`, judging records; "Not implemented" updated), `docs/capability_status_matrix.md` and `docs/index.md` (row for this plan), `docs/design/orc_structural_search_driver.md` (one sentence under "Edit Validation And Transactions": `slot_type_unavailable` refusal for unindexed replacements)

- [ ] **Step 1:** In a scratch clone at `c77e7ec0`, run the dev-check argv; expected: green. Record the command and result in the commit message body.
- [ ] **Step 2:** Write the docs; run `python scripts/check_doc_links.py` on each changed doc — expected: no broken links.
- [ ] **Step 3: Commit** with a pathspec: `docs: Phase 2 validation package check and structural search mode 2 recipe`.

### Task 6: Live Phase 2 (gated on the Phase 1 decision and the budget approval)

Preconditions, each checked and recorded in `<E2>/preconditions.md` before any call: the Phase 1 readout file shows `phase2_selected: true`; `<E2>/budget-approval.md` exists with the owner's variant and cap; Tasks 1–5 are committed and the full `tests/experiments/` suite passed on that commit; `RT` is a fresh `git worktree` at that commit; `<E1>/joined.json` exists: the Phase 1 readout writes it with `scoring.py readout --log <E1>/log.jsonl --driver-readout <E1>/readout.json --criterion <phase1.json> --joined-out <E1>/joined.json <each pool's results.json>`, every criterion task's `read_pool` rows (or `log_only_pool` rows for a task without a pool) with their outcomes (completed, failed, timeout, incident), and `adaptive.run_mode2(phase1_joined=...)` reads it as the initial archive's prior.

- [ ] **Step 1: Smoke** (counted against the cap): one I2 episode against the incumbent with the real mutator, its two adaptive evaluations, one judge batch per task with both judges; measure calls, wall clock and metering coverage; record `<E2>/smoke.md`. Stop and report if the episode's manifest or receipt step fails.
- [ ] **Step 2: Runs**: the approved number of runs with `run_seed` 1, 2, 3, each a fresh `E2/run-<k>` evidence root, `--concurrency 4`, `--call-cap` the approved figure, the validation package as `--holdout`; in tmux per the `launching-workflows` skill; resume incidents, never relaunch.
- [ ] **Step 3: Validation**: `validate_finalists` over every run's final archive; one pool, both judges; `summarize`.
- [ ] **Step 4: Readout and report**: `scoring.py readout --phase 2`; write `docs/reports/2026-10-<dd>-orc-structural-search-phase2.md` from `summarize` and the readout only (per-interface endpoints, diversity against Phase 1, control-flow changes, archive trajectory, validation table with shrinkage, final choice, calls and wall clock against the approved budget, metering coverage, scan verdicts, limitations); update the roadmap status and the capability matrix; link-check; commit.
