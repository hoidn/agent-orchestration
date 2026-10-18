# ORC Structural Search Live Phase 0 Gates And Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Phase 0 gates of the [structural search roadmap](2026-10-18-orc-structural-search-roadmap.md) and execute Phase 1 live: enumerate the authored catalog and sample unguided I1 proposals on a qualified family with real agents, score blind, and record the Phase 1 decision under the roadmap's stop rules.

**Architecture:** Reuse the offline apparatus (`experiments/orc_structural_search/`) and the comparison harness (`experiments/compare/`). Close the pre-live gaps the final review named (mutator behind the shims, model and CLI versions in evaluation identity, solution-hash case, config parsing), add bounded concurrent catalog evaluation, and add one scoring module that joins the harness's blind-judge `summarize` output to evaluation records. Live runs use a frozen runtime worktree, a work root and an evidence root outside the main checkout prefix.

**Tech Stack:** Python 3.13 standard library; `orchestrator` public CLI; `experiments/compare` shims (bubblewrap), `score.orc`, `summarize.py`; installed `claude` (Claude Code 2.1.302) and `codex` (codex-cli 0.163.0).

**Spec:** `docs/design/orc_structural_search_driver.md`; roadmap Phase 0 and Phase 1 gates and Decision Points; `docs/design/orc_effectiveness_comparison_harness.md`; `docs/orc_workflow_design_lessons.md` (evaluation rules).

## Selection, Allocation And Assumptions

The owner's 2026-10-18 directive "finish executing the roadmap" is recorded as selection of R3 Phases 0 and 1 and as acceptance of the pending boundary amendment. Allocation set by the coordinator under that directive, all first-exhausted:

| Limit | Value |
| --- | --- |
| Provider calls, all roles (arms, judges, mutators, smoke) | 160 |
| Concurrent evaluations | 4 |
| Per-evaluation wall clock | 14,400 s (the harness's executor ceiling) |
| Per-episode wall clock | 3,600 s |
| Models | `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6-sol`; never Fable |

Family: (a) review/planning improvement on the harness's calibrated packages, tasks rung 2 `resume-projection-integrity` and rung 4 `pure-result-replay` (both qualified under the frozen calibration rule, both with headroom on the descriptive hidden measure). Primary measure: the blind judge rubric (0–8) with repeated anchors and two judges (one Claude, one OpenAI), per the owner's 2026-10-15 evaluation policy; hidden acceptance descriptive only. Phase 1 scale: catalog `P` = 5 seeds × `T₀` = 2 tasks × `R` = 2 replicates; unguided I1 episodes `E₁` = 6 against the `direct` seed under `topology-only`; separation tolerance 2 within-arm standard deviations; collapse threshold 0.75.

## Global Constraints

- Work in `/home/ollie/Documents/agent-orchestration-search` on `feat/orc-structural-search`; subprocesses use `PYTHONPATH=<runtime>`.
- Every agent call (arm, judge, mutator) runs behind `experiments/compare/shim/` with the model guard; a Fable hit excludes the run.
- Live roots: runtime `RT=/home/ollie/ss-runtime` (a `git worktree` of the branch at a pinned commit), work root `W=/home/ollie/ss-work`, evidence root `E=/home/ollie/ss-evidence`; none under `/home/ollie/Documents/agent-orchestration*`, `/tmp`, `/dev/shm` or `/var/tmp`.
- Solution hashes are supplied with `--solution`, never stored in a package.
- Missing receipts are "unavailable", never 0; no ad hoc readout joins (use `summarize`'s clone-id join).
- Commits with pathspecs, no assistant attribution, no `Co-Authored-By` trailer.
- Broad or long test runs go directly in the agent shell (not a new tmux session) with a short `--basetemp`.

## Review Focus

1. A mutator command that names a Fable model is refused by the guard and its episode recorded as `incident` (Task 2 test `test_mutator_runs_behind_shims_and_guard`).
2. A catalog run where two evaluations finish out of order still writes one log line each with correct identities (Task 2 test `test_concurrent_catalog_logs_each_evaluation_once`).
3. A judge batch whose clone maps to no evaluation record fails the scoring join loudly (Task 3 test `test_scoring_refuses_unmapped_clone`).
4. The Phase 1 readout reports "not separated" when per-policy means differ by less than the tolerance (Task 3 test `test_phase1_readout_within_tolerance_is_not_separated`).
5. The provider-call ledger refuses a launch that would exceed the 160-call cap (Task 2 test `test_call_cap_refuses_launch`).

---

### Task 1: Governance and documentation of the selection

**Files:** Modify `docs/design/workflow_lisp_program_search_boundaries.md` (apply the pending amendment in place: §1 third bullet and both §6 sentences replaced with the block's text; the block reduced to a dated change note naming the 2026-10-18 directive), `docs/design/workflow_lisp_typed_program_gates.md` (one sentence in §Boundary Compliance recording the scoping reading), `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (status: Phases 0–1 selected under the directive, with the allocation table above), `docs/capability_status_matrix.md` and `docs/index.md` (row for this plan).

- [ ] Apply the edits; run `python scripts/check_doc_links.py` on each file; commit.

### Task 2: Pre-live gaps and bounded concurrency

**Files:** Modify `experiments/orc_structural_search/{driver,evaluation,config}.py`, `README.md`; tests in `tests/experiments/test_orc_structural_search_{driver,evaluation}.py`.

**Interfaces:**
- `run_agent` launches the mutator through the shim prefix (`COMPARE_ROOT=<E>/episodes/<episode_id>`, `COMPARE_TREE` = the episode workspace's parent, `COMPARE_BASE` = the parent snapshot's commit in a fresh git repository created for the episode workspace) so calls are recorded under `calls/<n>/`, run under bubblewrap and guarded; after the episode, `prepare.scan` runs over the episode records with the archive, lineage and holdout roots; hits mark the episode `scan_pending`.
- `env_manifest` adds `claude --version`, `codex --version`, `bwrap --version` and `git --version` output; `evaluation_id` therefore changes with CLI versions; model names are taken from the candidate's provider bindings and `:model` values (already in `candidate_id`).
- `check_solutions` lowercases hashes before validation and use.
- `load_config` rejects a string where a list is required, naming the field.
- `enumerate_catalog(..., concurrency: int)` evaluates with at most `concurrency` evaluations in flight (thread pool; each evaluation has its own clone and records directory); log writes are serialized.
- A call ledger `<E>/calls.json` counts provider calls per evaluation and episode from the shim records; `evaluate_and_scan` and `unguided_episode` refuse to launch when the recorded total plus the planned maximum for the next launch (seed's provider-call count; 1 for an episode) would exceed `--call-cap`.

- [ ] TDD each interface (tests named in Review Focus 1, 2, 5 plus one per remaining interface); run `pytest -q tests/experiments/test_orc_structural_search_*.py`; commit.

### Task 3: Blind scoring join and the Phase 1 readout

**Files:** Create `experiments/orc_structural_search/scoring.py`, `experiments/orc_structural_search/criteria/phase1.json` (criterion: experiment, tasks, base commits, judges `claude-opus-5-5` and `gpt-6-sol`, anchors the packages' `-upstream` and `-stub` diffs, primary measure the blind rubric mean per policy, `written_before_scoring: true`); tests `tests/experiments/test_orc_structural_search_scoring.py`.

**Interfaces:**
- `pool_evaluations(evidence_root, task_package, *, out, judges, criterion) -> Path` collects (`prepare.collect`) every completed, scanned evaluation of one task and calls the harness pool with one batch of all final patches plus anchors.
- `join_scores(results_json: Path, log: Path) -> list[dict]` maps each `summarize` run row (`run` path) to its evaluation record by `records_dir` and returns `{candidate_id, policy, task, replicate, value, hidden, calls, wall_clock_sec}`; an unmapped run raises.
- `phase1_readout(rows, *, tolerance_sd=2.0) -> dict`: per task and policy mean and within-arm SD; separation per task (two policies differ by more than `tolerance_sd` × the pooled within-arm SD); DIRECT's rank; the unguided-episode diversity and collapse figures from the driver readout; the roadmap decision (`phase2_selected: bool` with the rule that fired).

- [ ] TDD (Review Focus 3, 4 plus one per interface, on synthetic `results.json` and log fixtures); commit.

### Task 4: Family preparation

**Files:** Add `seed/dev-check.json` to `experiments/compare/tasks/resume-projection-integrity/` and `pure-result-replay/`: `argv` runs the base's existing tests in the modules the task names (`python -m pytest -q -x <paths>`), `timeout_sec` 1,800; the hidden tests are never named. Record the solution commits in `<E>/solutions.txt` (operator file outside the packages).

- [ ] Verify at each base commit that the dev-check argv runs and passes at base (green) in a scratch clone; commit the two `seed/dev-check.json` files.

### Task 5: Live setup and smoke

- [ ] Create `RT` as a `git worktree` of the branch HEAD; create `W` and `E`.
- [ ] Smoke: `direct` seed on `resume-projection-integrity`, one evaluation, through the driver with real agents; collect, scan, adjudicate; measure calls, wall clock and metering coverage. Record in `<E>/smoke.md`.

### Task 6: Phase 1 catalog and unguided sampling

- [ ] Catalog: 5 seeds × 2 tasks × 2 replicates at concurrency 4 under the call cap; collect, scan and adjudicate every run.
- [ ] Unguided: 6 I1 episodes against `direct` (`topology-only`, mutable `run`), mutator `claude -p --model claude-opus-5-5 --permission-mode bypassPermissions` behind the shims; accepted children evaluated on both tasks, one replicate, under the cap.
- [ ] Freeze the criterion (hash), pool per task, score with both judges, `summarize`, join, readout.

### Task 7: Decision and report

**Files:** Create `docs/reports/2026-10-18-orc-structural-search-phase1.md` (scope, allocation used, calls and wall clock, metering coverage, scan verdicts, per-policy table, separation, DIRECT's rank, diversity and collapse, decision under the roadmap rule, limitations); update the roadmap status and the capability matrix row; index row.

- [ ] Write from `summarize` and the readout only; link-check; commit.
