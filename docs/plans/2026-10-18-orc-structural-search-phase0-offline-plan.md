# ORC Structural Search Phase 0 Offline Apparatus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the experiment-local search apparatus (`experiments/orc_structural_search/`) and its seed catalog so that one authored candidate compiles, runs through public `run` in a fresh clone behind the comparison-harness shims with scripted providers, and is recorded with its identity, lineage, skeleton and consumption, without any paid provider call.

**Architecture:** A thin Python package beside `experiments/compare/`: `config.py` (experiment configuration), `candidates.py` (snapshots, `candidate_id`, frozen-surface validation, the I2 one-site transaction), `records.py` (append-only JSONL log, skeleton hash, final-choice rule), `evaluation.py` (clone, public `run` with `--state-dir`, outcome collection), `metering.py` (receipt coverage) and `driver.py` (mode 1: catalog enumeration and unguided sampling). Seeds are 2.39 copies under `experiments/orc_structural_search/seeds/` sharing one entry contract. The harness gains a candidate-root arm spec, a generic-command arm and scan patterns.

**Tech Stack:** Python 3.13 standard library; existing `orchestrator` compiler and CLI; `experiments/compare` (`prepare.py`, `repos.py`, `scan.py`, shims under bubblewrap); pytest with `tests/experiments/compare_harness_support.py` patterns.

**Spec:** `docs/design/orc_structural_search_driver.md` (apparatus contract), `docs/design/workflow_lisp_source_site_inspection.md` (manifest, consumed only by the separate feasibility plan), `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Phase 0 gates).

## Global Constraints

- Work in `/home/ollie/Documents/agent-orchestration-search` on branch `feat/orc-structural-search`; run every command from that root with `PYTHONPATH=/home/ollie/Documents/agent-orchestration-search` for subprocesses (the editable install points elsewhere).
- No paid provider call: every provider is a scripted `claude`/`codex` executable on `PATH` that reads the prompt on stdin and writes JSON to the absolute `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; the model guard stays active, and no model name containing `fable` appears anywhere.
- No optimizer vocabulary (fitness, population, crossover, archive, selection) under `orchestrator/`; the only `orchestrator/` change in this plan is the OMP `usage_complete` flag (Task 7).
- Candidates are ordinary admitted 2.39 programs; `trial`, `--emit-*`, `run-ref` provider children, `eval` and hot swap are not used.
- Missing receipts serialize as the string `"unavailable"`, never `0`.
- Commits use pathspecs (`git commit -- <paths>`), carry no assistant attribution and no `Co-Authored-By` trailer.
- Tests: narrow selectors first; new test modules get `pytest --collect-only`; sandboxed tests use `skip_without_sandbox()` from `tests/experiments/compare_harness_support.py`; work roots for sandboxed tests live under `~/.cache/compare-harness-tests`, never under `/tmp` or the checkout prefix.
- Durable docs cite paths and symbols, not line numbers.

## Review Focus

1. A child file identical to its parent except for whitespace or comments must pass frozen-surface validation and yield a different `candidate_id` but an equal `program_digest` (Task 3 test `test_whitespace_only_child_passes_validation_and_keeps_program_digest`).
2. A CRLF or multi-byte UTF-8 parent must locate its site by re-reading, never by byte offset (Task 3 test `test_transaction_locates_site_in_crlf_and_utf8_source`).
3. A proposal that edits a prompt body under `condition: topology-only` must be refused with `frozen_surface_changed` (Task 3 test `test_prompt_body_edit_refused_under_topology_only`).
4. A run whose memo never reaches a terminal row must be recorded as `incident`, not as a failure outcome, and must keep its `evaluation_id` for resume (Task 4 test `test_unfinished_memo_is_recorded_as_incident`).
5. The final-choice rule must refuse to choose without a `criterion_sha256` and must include the reference seed among the compared rows (Task 5 tests `test_final_choice_refuses_without_criterion_hash`, `test_final_choice_compares_reference_seed`).

---

### Task 1: Package, configuration and candidate snapshots

**Files:**
- Create: `experiments/orc_structural_search/__init__.py` (empty)
- Create: `experiments/orc_structural_search/config.py`
- Create: `experiments/orc_structural_search/candidates.py`
- Test: `tests/experiments/test_orc_structural_search_candidates.py`

**Interfaces:**
- Produces: `config.py`: `@dataclass(frozen=True) class ExperimentConfig(mutable_files: tuple[str, ...], mutable_definitions: tuple[str, ...], condition: str, interface: str, entry_workflow: str, source_root: str, providers_file: str, command_boundaries_file: str | None, episode_wall_clock_sec: int, criterion_sha256: str | None)` and `load_config(path: Path) -> ExperimentConfig` (JSON; `condition` is one of `topology-only`, `prompt-only`, `provider-only`, `joint`; `interface` is one of `I1`, `I2`, `I3`).
- Produces: `candidates.py`: `candidate_id(root: Path, *, orchestrator_commit: str) -> str` returning `sha256:<hex>` over, in sorted order, every file under `root` (relative path and bytes) plus the orchestrator commit; `snapshot(parent: Path, edited_files: Mapping[str, bytes], dest: Path) -> Path` copying the parent directory to `dest` and overwriting the named files, refusing when `dest` exists; `compile_candidate(root: Path, config: ExperimentConfig) -> CompileOutcome` with `CompileOutcome(status: str, build_key: str | None, program_digest: str | None, diagnostics: tuple[dict, ...])` obtained by running `python -P -m orchestrator compile <root>/<entry file> --entry-workflow ... --source-root <root> --provider-externs-file ... [--command-boundaries-file ...] --diagnostics-json` with `cwd=root`.

- [ ] **Step 1: Write the failing tests**

```python
def test_candidate_id_ignores_nothing_but_covers_every_byte(tmp_path):
    a = make_candidate(tmp_path / "a", {"m.orc": SOURCE})
    b = make_candidate(tmp_path / "b", {"m.orc": SOURCE})
    assert candidate_id(a, orchestrator_commit="abc") == candidate_id(b, orchestrator_commit="abc")
    c = make_candidate(tmp_path / "c", {"m.orc": SOURCE + "\n"})
    assert candidate_id(c, orchestrator_commit="abc") != candidate_id(a, orchestrator_commit="abc")
    assert candidate_id(a, orchestrator_commit="def") != candidate_id(a, orchestrator_commit="abc")

def test_snapshot_never_writes_parent_and_refuses_existing_dest(tmp_path): ...
def test_compile_candidate_reports_accepted_build_key_and_digest(tmp_path): ...  # SOURCE is the plan_review_execute example copied at 2.39 with its providers.json
def test_compile_candidate_reports_rejected_diagnostics(tmp_path): ...       # a type error in the body
def test_load_config_rejects_unknown_condition(tmp_path): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_candidates.py -q`
Expected: FAIL with `ModuleNotFoundError: experiments.orc_structural_search`

- [ ] **Step 3: Implement `config.py` and `candidates.py`**

`candidate_id` hashes `relative_path + b"\0" + bytes` for every regular file under the root in sorted order, then the commit string. `compile_candidate` parses the last stdout line as JSON; a nonzero exit with a JSON `{"status":"rejected",...}` line yields `status="rejected"` and the `diagnostics` list.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_candidates.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add experiments/orc_structural_search/__init__.py experiments/orc_structural_search/config.py experiments/orc_structural_search/candidates.py tests/experiments/test_orc_structural_search_candidates.py
git commit -m "feat: structural search package, configuration and candidate snapshots" -- experiments/orc_structural_search tests/experiments/test_orc_structural_search_candidates.py
```

### Task 2: Seed catalog at target 2.39 with one entry contract

**Files:**
- Create: `experiments/orc_structural_search/seeds/common.orc` (module `common`: `defrecord Change (summary String) (account String)`, `defrecord CheckReport (passed Bool) (failing List[String]) (excerpt String)`, `defunion Outcome (DONE (summary String)) (BLOCKED (reason String))`)
- Create: `experiments/orc_structural_search/seeds/direct.orc`, `plan_then_implement.orc`, `implement_review_revise.orc`, `best_of_n.orc`, `implement_check_diagnose_repair.orc`
- Create: `experiments/orc_structural_search/seeds/providers.json` (`providers.coder` → `claude_unrestricted_workspace`, `providers.planner` → `claude_unrestricted_workspace`, `providers.reviewer` → `codex_unrestricted_workspace`, `providers.judge` → `codex_unrestricted_workspace`)
- Create: `experiments/orc_structural_search/seeds/commands.json` (`{"dev-check": {"stable_command": ["python", "dev_check.py"], "closure": ["dev_check.py"]}}`)
- Create: `experiments/orc_structural_search/seeds/dev_check.py`
- Modify: `workflows/README.md` (one Workflow Catalog row per seed, status `Experiment seed (structural search); compile evidence`, DSL `2.39`)
- Test: `tests/experiments/test_orc_structural_search_seeds.py`

**Interfaces:**
- Produces: every seed exports `run ((task String) (intent String) (repo String)) -> Outcome` at `:target-dsl "2.39"`, module name equal to the file stem, importing `common`; provider externs `providers.coder`, `providers.planner`, `providers.reviewer`, `providers.judge` (a seed uses the subset it needs); `implement_check_diagnose_repair.orc` uses `(command-result dev-check :argv ("python" "dev_check.py") :returns CheckReport)` once after the first implementation and, on `passed = false`, one `providers.reviewer` diagnosis call followed by one `providers.coder` repair call.
- Produces: `dev_check.py`: reads `dev-check.json` from the workspace (`{"argv": [...], "timeout_sec": N}`), runs the argv with that timeout in the workspace, writes `{"passed": bool, "failing": [str...], "excerpt": str}` (excerpt capped at 4,000 characters) to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; a missing `dev-check.json` yields `passed=false, failing=["dev-check.json missing"]`.

- [ ] **Step 1: Write the failing tests**

```python
SEEDS = ["direct", "plan_then_implement", "implement_review_revise", "best_of_n", "implement_check_diagnose_repair"]

@pytest.mark.parametrize("seed", SEEDS)
def test_seed_compiles_at_2_39_with_the_common_entry_contract(seed):
    out = compile_seed(seed)                      # python -P -m orchestrator compile ... --diagnostics-json
    assert out["status"] == "accepted"
    assert read_header(seed)[":target-dsl"] == "2.39"
    assert entry_signature(seed) == "run ((task String) (intent String) (repo String)) -> Outcome"

def test_dev_check_writes_typed_report(tmp_path, monkeypatch): ...   # argv ["python","-c","import sys; sys.exit(1)"] -> passed False
def test_dev_check_without_config_fails_closed(tmp_path, monkeypatch): ...
def test_registry_lists_every_seed(): ...                          # workflows/README.md contains each seed path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_seeds.py -q`
Expected: FAIL (seed files missing)

- [ ] **Step 3: Author the seeds**

Port from `experiments/compare/control/direct_task.orc` (direct), `workflows/examples/plan_review_execute.orc` (plan then implement), `experiments/orc_vs_single_call/workflows/reviewed_change.orc` (implement, review, revise; map READY to DONE, ESCALATED and UNRESOLVED to BLOCKED) and `best_of_n.orc` (two candidates and a judge; `list/map-effect` over two coder calls in the single `repo`), following `docs/lisp_workflow_drafting_guide.md` for 2.39 procedure contracts and `command-result`. Compile each with the CLI until accepted. Provider calls carry explicit `:model` and `:effort` with non-Fable models (`claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6-sol`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_seeds.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: structural search seed catalog at target 2.39" -- experiments/orc_structural_search/seeds workflows/README.md tests/experiments/test_orc_structural_search_seeds.py
```

### Task 3: Frozen-surface validation and the one-site transaction

**Files:**
- Modify: `experiments/orc_structural_search/candidates.py`
- Test: `tests/experiments/test_orc_structural_search_validation.py`

**Interfaces:**
- Consumes: `read_sexpr_text(source: str, *, source_path: str) -> ListExpr` from `orchestrator/workflow_lisp/reader.py` (spanned reader tree; use `canonical_form(node)` below to compare modulo spans); `ExperimentConfig` from Task 1.
- Produces: `canonical_form(node) -> object` (nested tuples of atoms, spans dropped); `validate_frozen_surfaces(parent: Path, child: Path, config: ExperimentConfig) -> Verdict` with `Verdict(accepted: bool, code: str | None, detail: str)`; `Receipt(parent_candidate_id: str, site_id: str, expected_file_digest: str, replacement_expression: str, supporting_declarations: tuple[str, ...], condition: str, hypothesis: str)`; `validate_one_site(parent: Path, child: Path, receipt: Receipt, config: ExperimentConfig) -> Verdict`. Refusal codes: `digest_mismatch`, `site_unlocatable`, `scope_exceeded`, `declaration_collision`, `frozen_surface_changed`; `slot_type_changed` is produced later by comparing compile outputs (Task 8), not here.
- Frozen surfaces: top-level forms whose head is `import`, `deftype`, `defrecord`, `defunion`, `defenum`, `export`, `defmodule`, `:target-dsl`, `:language`; `defprompt` bodies unless `condition` is `prompt-only` or `joint`; definitions not listed in `config.mutable_definitions`.
- `site_id` format: `<owner canonical name>@<path>:<line>:<column>` where the path is the file name relative to the candidate root; the site is located by re-reading the parent with `read_sexpr_text` and finding the form whose span start is that `(line, column)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_whitespace_only_child_passes_validation_and_keeps_program_digest(tmp_path): ...
def test_unrelated_definition_edit_is_refused_with_scope_exceeded(tmp_path): ...
def test_import_change_is_refused_with_frozen_surface_changed(tmp_path): ...
def test_prompt_body_edit_refused_under_topology_only(tmp_path): ...
def test_prompt_body_edit_accepted_under_prompt_only(tmp_path): ...
def test_one_site_transaction_accepts_single_subtree_replacement(tmp_path): ...
def test_one_site_transaction_refuses_second_changed_subtree(tmp_path): ...
def test_one_site_transaction_refuses_stale_digest(tmp_path): ...
def test_helper_colliding_with_existing_name_is_refused(tmp_path): ...
def test_transaction_locates_site_in_crlf_and_utf8_source(tmp_path): ...   # parent bytes contain "\r\n" and "ñ" before the site
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_validation.py -q`
Expected: FAIL with `ImportError` for the new names

- [ ] **Step 3: Implement the validators in `candidates.py`**

Compare `canonical_form` of each top-level form of parent and child by position of the `defworkflow`/`defproc`/`defprompt` name; forms outside the mutable definitions must be equal; for the one-site transaction, within the owner form, every subtree other than the one starting at the site's `(line, column)` must be equal, and new top-level forms must be exactly the declared helpers whose names resolve to nothing in the parent (including import aliases).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_validation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: frozen-surface validation and one-site transaction for candidates" -- experiments/orc_structural_search/candidates.py tests/experiments/test_orc_structural_search_validation.py
```

### Task 4: Records, skeleton hash and the final-choice rule

**Files:**
- Create: `experiments/orc_structural_search/records.py`
- Test: `tests/experiments/test_orc_structural_search_records.py`

**Interfaces:**
- Produces: `append_record(log: Path, record: Mapping[str, object]) -> None` (one JSON line, keys sorted, `"unavailable"` preserved as a string); `read_records(log: Path) -> list[dict]`; `skeleton_hash(source: str, *, definitions: Sequence[str]) -> str` (sha256 over the canonical S-expression of the named definitions after: binders and all their references replaced by scope-ordinal placeholders `$0`, `$1`, ... assigned in order of binding within each definition, parameters included; string and numeric literals replaced by `#lit`; prompt names used as `:prompt` arguments and provider extern names replaced by `#prompt` and `#provider`; `:model` and `:effort` values replaced by `#lit`; form heads and arity kept); `final_choice(rows: Sequence[Mapping], *, criterion: Mapping) -> str` where each row has `candidate_id`, `is_reference: bool`, `validation_success: float`, `mean_cost: float | str`, `provider_calls: int`, and `criterion` has `criterion_sha256`, `mean_cost_ceiling`, `equivalence_tolerance`; rule: highest `validation_success` among rows under the ceiling, then lower cost among rows within the tolerance of the best, then fewer calls, then the lexically earlier `candidate_id`; raises `ValueError("criterion_sha256 required")` without the hash and `ValueError("reference seed missing")` when no row has `is_reference`.

- [ ] **Step 1: Write the failing tests**

```python
def test_skeleton_is_invariant_under_rename_prompt_text_and_literals(): ...
def test_skeleton_differs_for_control_flow_change(): ...   # wrapping a call in (if ...) changes it
def test_skeleton_ignores_provider_swap_and_model_change(): ...
def test_append_and_read_records_preserve_unavailable_marker(tmp_path): ...
def test_final_choice_picks_highest_validation_then_lower_cost(): ...
def test_final_choice_refuses_without_criterion_hash(): ...
def test_final_choice_compares_reference_seed(): ...        # the reference wins when it is the best under the ceiling
def test_final_choice_treats_unavailable_cost_as_over_ceiling_when_ceiling_is_in_cost_units(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_records.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `records.py`**

Use `read_sexpr_text` for the skeleton; walk `let*` bindings, `defworkflow`/`defproc` parameters and `match` arm bindings to assign ordinals; everything else is kept as its symbol text.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_records.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: structural search records, skeleton hash and final-choice rule" -- experiments/orc_structural_search/records.py tests/experiments/test_orc_structural_search_records.py
```

### Task 5: Harness extension: candidate-root arm spec, generic-command arm, scan patterns

**Files:**
- Modify: `experiments/compare/prepare.py` (`ARMS`, `arm_inputs`, `run_arm`, `scan`)
- Modify: `experiments/compare/repos.py` (`shim_commands`)
- Modify: `experiments/compare/scan.py` (`patterns`)
- Modify: `experiments/compare/README.md` (one short section "Candidate-root arms and generic-command arms")
- Test: `tests/experiments/test_compare_harness.py` (extend)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class ArmSpec(source: Path, entry: str, source_root: Path, providers: Path, inputs: tuple[str, ...], command_boundaries: Path | None = None, state_dir: Path | None = None, command: tuple[str, ...] | None = None)`; `run_arm(..., spec: ArmSpec | None = None)` where a spec replaces the `ARMS` lookup; when `spec.command` is set the arm is a generic command run behind the shims with the same `COMPARE_*` environment and `R/inputs.json` as its single argument, and `record.json` gains `"arm_kind": "generic-command"`; `shim_commands(..., state_dir=..., command_boundaries=...)` appends `--state-dir` and `--command-boundaries-file` when given; `scan.patterns(..., roots=...)` accepts extra named prefixes (`archive`, `lineage`, `holdout`) and `prepare.scan` passes `--root NAME=PATH` repeatable options through.
- Keeps: every existing `ARMS` arm and its layout unchanged; the existing refusals (checkout prefix, `/tmp`, dirty runtime, unignored `.orchestrate/`).

- [ ] **Step 1: Write the failing tests**

```python
def test_candidate_root_spec_builds_command_with_its_own_source_root_and_state_dir(world): ...
def test_generic_command_arm_runs_behind_shims_and_records_arm_kind(world): ...
def test_scan_flags_archive_lineage_and_holdout_roots(world): ...
def test_existing_arms_layout_unchanged(world): ...   # reuse the existing command.sh assertion for reviewed_change
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_compare_harness.py -q -k "candidate_root or generic_command or archive_lineage or layout_unchanged"`
Expected: FAIL (new names)

- [ ] **Step 3: Implement the extension**

Keep `ARMS` as the default lookup; build an `ArmSpec` from it so `run_arm` has one path. Resolve `spec` paths absolutely; the candidate root must satisfy the same guards as the runtime.

- [ ] **Step 4: Run the harness tests**

Run: `pytest tests/experiments/test_compare_harness.py tests/experiments/test_compare_pool_summarize.py tests/experiments/test_compare_review_once.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: candidate-root arm spec, generic-command arm and search scan patterns" -- experiments/compare/prepare.py experiments/compare/repos.py experiments/compare/scan.py experiments/compare/README.md tests/experiments/test_compare_harness.py
```

### Task 6: Evaluation launch path through public `run`

**Files:**
- Create: `experiments/orc_structural_search/evaluation.py`
- Create: `tests/experiments/orc_structural_search_support.py` (scripted `claude`/`codex` executables and a tiny task repository fixture)
- Test: `tests/experiments/test_orc_structural_search_evaluation.py`

**Interfaces:**
- Consumes: `ArmSpec` and `run_arm` from Task 5; `build_candidate` from `experiments/compare/repos.py`; `candidate_id` and `compile_candidate` from Task 1.
- Produces: `evaluation_id(candidate: str, task_id: str, evaluator_version: str, env_manifest_digest: str, replicate: int) -> str`; `evaluate(candidate_root: Path, config: ExperimentConfig, *, task_package: Path, evidence_root: Path, replicate: int, runtime: Path, env: Mapping[str, str]) -> EvaluationRecord` with `EvaluationRecord(evaluation_id, run_id, state_dir, outcome: str, value: object | None, wall_clock_sec: float | str, provider_calls: int | str, resume_count: int, incidents: tuple[str, ...])`; `outcome` is one of `completed`, `failed`, `incident`; `resume(record: EvaluationRecord, ...) -> EvaluationRecord` running `python -P -m orchestrator resume <run_id> --state-dir <state_dir>` and keeping the same `evaluation_id`.
- Scripted providers (support module): executables named `claude` and `codex` that read stdin, select a result by the first matching substring from a JSON map in `SCRIPTED_RESULTS_FILE` (env), and write it to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; placed on `PATH` after the shim directory; they must not be named anything else because the provider templates run `claude`/`codex`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.skipif(no_sandbox(), reason="bwrap required")
def test_direct_seed_runs_in_fresh_clone_and_records_run_id(world): ...   # outcome completed, value {"variant":"DONE",...}, state_dir under evidence/runs/<evaluation_id>, run_id resolves to memo.jsonl with a terminal row
def test_unfinished_memo_is_recorded_as_incident(world): ...             # scripted provider exits 1 once: outcome incident, resume_count 0, evaluation_id kept
def test_resume_keeps_evaluation_id_and_completes(world): ...
def test_evaluation_id_changes_with_replicate_and_env_manifest(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_evaluation.py -q`
Expected: FAIL

- [ ] **Step 3: Implement `evaluation.py` and the support module**

Build the clone with `build_candidate` from the task package's `base_commit` and `seed/` (seed `dev-check.json` there); copy `dev_check.py` from the seeds directory into the clone before the run; write `inputs.json` with `task`, `intent`, `repo`; launch through `run_arm(spec=ArmSpec(...))` with `state_dir=<evidence>/runs/<evaluation_id>`; classify the memo: terminal row with `completed` → `completed`; terminal row with another outcome → `failed`; no terminal row → `incident`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_evaluation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: structural search evaluation through public run in fresh clones" -- experiments/orc_structural_search/evaluation.py tests/experiments/orc_structural_search_support.py tests/experiments/test_orc_structural_search_evaluation.py
```

### Task 7: Metering coverage and the OMP usage completeness flag

**Files:**
- Create: `experiments/orc_structural_search/metering.py`
- Modify: `orchestrator/providers/omp_transport.py` (`_build_metadata`)
- Test: `tests/experiments/test_orc_structural_search_metering.py`, `tests/test_provider_omp_transport.py` (extend)

**Interfaces:**
- Produces: `claude_usage(session_jsonl: Path) -> list[dict]` (one row per assistant message with `model`, `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, missing fields `"unavailable"`); `codex_usage(rollout_dir: Path) -> list[dict] | str` returning `"unavailable"` when no token event is recognized; `coverage(records_dir: Path, *, claude_sessions: Sequence[Path], codex_rollouts: Sequence[Path]) -> dict` with per-provider `calls`, `calls_with_receipts`, `tokens` (int or `"unavailable"`), `wall_clock_sec`; `_build_metadata` gains `"usage_complete": bool`, true only when every message row carries `totalTokens` and `cost.total`.
- Consumes: shim `calls/<n>/` layout (`prompt.txt`, `stdout.txt`, `stderr.txt`) from `experiments/compare/shim/claude`; `scan.claude_sessions` for session discovery.

- [ ] **Step 1: Write the failing tests**

```python
def test_claude_usage_reads_message_usage_rows(tmp_path): ...
def test_claude_usage_marks_missing_fields_unavailable(tmp_path): ...
def test_codex_usage_is_unavailable_without_token_events(tmp_path): ...
def test_coverage_counts_calls_and_receipts_per_provider(tmp_path): ...
def test_omp_metadata_marks_usage_complete_only_when_every_row_has_totals(): ...   # in tests/test_provider_omp_transport.py
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_metering.py tests/test_provider_omp_transport.py -q -k "usage or coverage"`
Expected: FAIL

- [ ] **Step 3: Implement `metering.py` and the flag**

The flag adds one key to the metadata mapping; sums are unchanged so existing consumers keep working.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_metering.py tests/test_provider_omp_transport.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: metering coverage report and OMP usage completeness flag" -- experiments/orc_structural_search/metering.py orchestrator/providers/omp_transport.py tests/experiments/test_orc_structural_search_metering.py tests/test_provider_omp_transport.py
```

### Task 8: Mode 1 driver: catalog enumeration and unguided I1 sampling with scripted leaves

**Files:**
- Create: `experiments/orc_structural_search/driver.py`
- Create: `experiments/orc_structural_search/README.md`
- Test: `tests/experiments/test_orc_structural_search_driver.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `enumerate_catalog(seeds: Sequence[Path], config, *, tasks: Sequence[Path], evidence_root: Path, replicates: int, runtime, env) -> list[dict]` (one evaluation record per seed, task and replicate, appended to `<evidence>/log.jsonl` with `mode: "catalog"`); `unguided_episode(parent_root: Path, config, *, agent_cmd: Sequence[str], evidence_root: Path, episode_index: int, runtime, env) -> dict` launching the agent command in a copy of the parent with the objective, mutable scope and frozen surfaces written to `<copy>/EPISODE.md`, deriving the child from the final files, running `validate_frozen_surfaces`, `compile_candidate`, comparing the entry's result type between parent and child (from each `closed_program.json`'s entry result; a difference is `slot_type_changed`), snapshotting an accepted child under `<evidence>/candidates/<candidate_id>/`, and appending an episode record with `interface: "I1"`, `mode: "unguided"`, `outcome`, `refusal code or diagnostics class`, `skeleton`, `parent_candidate_id`; after every evaluation, `prepare.scan` runs over the record with `roots` naming the archive (`<evidence>/candidates`), the lineage log and the holdout root, and the hit count is stored on the evaluation record (`scan_hits`), a nonzero count marking the record `scan_pending` until adjudicated; `run_mode1(config_path: Path, *, seeds, tasks, evidence_root, episodes: int, agent_cmd, replicates, runtime, env) -> dict` producing `readout.json` with per-seed outcomes, distinct skeletons among accepted children, revisit rate and the terminal-only share.
- Scripted mutator for tests: a command that edits the parent's mutable file deterministically (one episode wraps the coder call in an `if` on a literal; another renames a binding; another edits an import) so the readout shows one structural child, one rename child with the parent's skeleton, and one refusal.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.skipif(no_sandbox(), reason="bwrap required")
def test_mode1_enumerates_catalog_and_samples_unguided_episodes(world): ...   # readout: 5 seeds evaluated once on 1 task; 3 episodes -> 2 accepted, 1 refused frozen_surface_changed; distinct_skeletons == 2 (parent and one structural child); revisit_rate == 0.5
def test_rejected_proposal_never_enters_evaluation(world): ...
def test_log_records_carry_identities_and_unavailable_markers(world): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/experiments/test_orc_structural_search_driver.py -q`
Expected: FAIL

- [ ] **Step 3: Implement `driver.py` and write the README**

README: purpose, the offline recipe (`python -m experiments.orc_structural_search.driver --config ... --seeds ... --tasks ... --evidence ... --episodes N --agent-cmd ...`), the layout under the evidence root, what is not implemented (adaptive mode, the manifest, paid runs), and the `ponytail:` deviations (dev-check runs in the working clone; no fresh-checkout patch application yet).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/experiments/test_orc_structural_search_driver.py -q`
Expected: PASS

- [ ] **Step 5: Collect-only and the experiment suite**

Run: `pytest --collect-only -q tests/experiments/test_orc_structural_search_*.py` then `pytest -q -n 16 --dist=worksteal tests/experiments`
Expected: all collected; PASS

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: mode 1 structural search driver with catalog enumeration and unguided sampling" -- experiments/orc_structural_search/driver.py experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_driver.py
```

### Task 9: Documentation and routing after implementation

**Files:**
- Modify: `docs/design/orc_structural_search_driver.md` (Metering: `scan.claude_sessions` locates session files; usage parsing lives in `experiments/orc_structural_search/metering.py`; Task family: dev-check first version runs in the working clone)
- Modify: `docs/capability_status_matrix.md` (the structural-search row: status `Partial: offline apparatus implemented with scripted providers; no study selected, manifest and adaptive mode not implemented`)
- Modify: `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Phase 0 status note naming this plan and what remains owner-gated)
- Modify: `docs/index.md` (row for this plan)

- [ ] **Step 1: Apply the documentation edits**
- [ ] **Step 2: Run the link checker**

Run: `python scripts/check_doc_links.py docs/design/orc_structural_search_driver.md docs/capability_status_matrix.md docs/plans/2026-10-18-orc-structural-search-roadmap.md docs/index.md docs/plans/2026-10-18-orc-structural-search-phase0-offline-plan.md`
Expected: only the known `<a id>` anchors reported (`proposed-amendment-2026-10-17`, `workflow-lisp-repl-targets-235-and-236`), no missing targets

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: record the structural search offline apparatus" -- docs/design/orc_structural_search_driver.md docs/capability_status_matrix.md docs/plans/2026-10-18-orc-structural-search-roadmap.md docs/index.md
```
