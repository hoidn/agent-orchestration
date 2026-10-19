# ORC Structural Search `module` Condition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement steps 1–7 of the [module condition decision](2026-10-19-orc-structural-search-module-rewrite-plan.md) offline: a fifth edit condition `module` (whole-module rewrite of private definitions) in the structural search driver, admission on the compiled child's closed program (allowlist, per-call ceiling, module graph, public contract, effect shapes), metrics over every private definition, a workspace check command in the brief, the model guard's allowlist, metering and session records on rows, a fourth arm under a successor criterion in the three-arm readout, and the design rows. No provider is called and no criterion is frozen; a live `module` arm is an owner selection after the decision's gate and is not a task here.

**Architecture:** Extend `experiments/orc_structural_search/` in place. Source-level validation stays in `candidates.py` (the I2 one-site transaction moves to `one_site.py` to free that module's line budget); checks over `closed_program.json` live in one new pure module `closed_checks.py`, called by `acceptance.judge_child` and by the new workspace check command `check.py`, which `driver.episode_workspace` stages beside the runtime copy. Records changes land in `driver.py` (mode 1's catalog helpers move to `mode1.py` for its budget), `evaluation.py` and `metering.py`; the fourth arm lands in `three_arm.py`/`three_arm_readout.py` keyed by interface and condition.

**Tech Stack:** Python 3.13 standard library (`json`, `ast`, `pathlib`, `collections`); the frozen runtime's `orchestrator compile --diagnostics-json` and its `closed_program.json`; `experiments/compare` shims (bash, bubblewrap); tests with scripted `claude`/`codex` executables (`tests/experiments/orc_structural_search_support.py`), no provider called.

**Spec:** `docs/plans/2026-10-19-orc-structural-search-module-rewrite-plan.md` at `957e963b` (sections "The `module` Condition", "Episode", "Records, Identities And Cost", "Implementation Steps", "Verification"; its "Gate For A Live `module` Arm" bounds live work: none here). Precedent: `docs/plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md`. Governing design: `docs/design/orc_structural_search_driver.md` ("Edit Validation And Transactions", "Records", "Execution Contract").

## Coordinator Decisions Applied (binding)

`module` is a fifth value of `config.CONDITIONS`, not an `edit_policy` axis; legacy conditions keep their outcomes. `module` joins `PROMPT_CONDITIONS`, `PROMPT_SIGNATURE_CONDITIONS` and `TOPOLOGY_CONDITIONS` but not `PROVIDER_CONDITIONS` (that set unfreezes `providers.json` in `_plain_file_verdict`); `:model`/`:effort` are checked on the compiled child's `perform` policies, not on source. The `import` form stays frozen (`FROZEN_HEADS`); the resolved graph is the module qualifiers of the closed program's `definitions`/`types` keys, never `configuration.imports` (verified `{}` for every probe). `acceptance.judge_child` refuses `provider_phased`, `agent` and `agent_turn` perform sites under every condition (`unsupported_effect_shape`); the closed-program planned maximum and the shim call cap are v1 (Task 2b): a `module` child's reservation is walked from its closed program, and the shim refuses the call beyond the evaluation's planned maximum. Metrics cover every non-exported definition under `module`. Retention of a child in any adaptive use is by reproduction on the validation split (at least three replicates per task); no ablation gate exists. The evaluator gate is calibration on known controls only (`anchor_trust` as in `three_arm.json` plus a predeclared tolerated error rate on those controls); nothing is required of candidate ranks. The brief exposes one check command; the controller re-runs admission. Rows gain `criterion_sha256`, metering and (episodes) native session file paths. The fourth arm runs only under a successor criterion with its own SHA-256; `three_arm.json` stays byte-identical. The last task is documentation.

## Feasibility (verified in the code at `feat/orc-structural-search` 5a85c41e, read-only probes on scratch copies)

- **Closed program shape** (`<root>/.orchestrate/build/<build_key>/closed_program.json`, written by `compile_candidate`): top-level keys `body, configuration, defaults, definitions, entry, params, representation, result, schema, sites, target, types`. A provider call is `{"k": "perform", "class": "provider", "provider": "<id>", "site": "<label>", "policy": {"model": {"k": "lit", "v": "gpt-6.1-sol", ...}, "effort": {"k": "lit", "v": "high"}, "timeout_sec": {"k": "lit", "v": 5400}}, ...}`; a `:model` naming a parameter is `{"k": "name", "n": "m"}`; a command call has `"class": "command"` and `"policy": null`. `params` is `[["task", {"kind": "primitive", "name": "String"}], ...]`; `result` the resolved type; `types` keys are qualified (`common::Change`, `common::Outcome`, and `common::CheckReport` once a child references it by qualified name past the `:only` list); `definitions` is `{}` for the seeds (their helpers inline). `configuration.imports` is `{}` for the seed, for a child adding `(import std/improve ...)` and for the qualified reference, so it carries no module graph. A qualified name into a module the file never imports is rejected by the compiler (`type_unknown`), so the frozen `import` form bounds the graph and the qualifier check is its backstop. `ledger.max_provider_calls(design_review_execute_agents.orc, "run")` is 4 (agent turns are counted), as the decision states.
- **Source validation today** (`candidates.py`, 500 lines, at the budget): `_split_forms` treats `FROZEN_HEADS` (`import`, `deftype`, `defrecord`, `defunion`, `defenum`, `export`, `defmodule`, `:target-dsl`, `:language`) as frozen; `_definition_verdict` refuses an added or removed definition (`scope_exceeded`) and a changed one outside `mutable` (`scope_exceeded`); `_condition_verdict` checks topology against `TOPOLOGY_CONDITIONS` and tuning against `PROVIDER_CONDITIONS`; `_plain_file_verdict` admits any `providers.json` change under `PROVIDER_CONDITIONS`. A type edit in `common.orc` is therefore `frozen_surface_changed` and an added `defproc` there `scope_exceeded`. The one-site transaction (`validate_one_site`, `_one_site_verdict`, `_owner_and_site`, `_scope_verdict`, `_one_form`, `_masked_form`, lines 422–437 and 468–551, ≈ 90 lines) is imported only by `acceptance.py` and `tests/experiments/test_orc_structural_search_{validation,sites}.py`; `sites.py` imports `Receipt, _owner_form, _parse_site, _site_path, _split_forms, _subform, _top_level_forms`, which stay.
- **`judge_child`** (`acceptance.py:44-79`): validation, compile, I2 slot check, `ledger.unbounded_refusal`, then `entry_result` (the closed program's `result` only). A `compiler_crash` is a `rejected` outcome with `diagnostics_class compiler_crash`. `evaluation.evaluate` compiles the archived root with `cwd=root`, so the archived candidate's closed program exists after an evaluation; `EvaluationRecord` has no `build_key`.
- **Skeleton and allocation** (`driver.skeleton`/`allocation`, `records.skeleton_hash(definitions=config.mutable_definitions)`): `_named_definitions` raises on a missing name and takes `defworkflow|defproc|defun|defprompt`; `_normalize_definition` renders the definition's own name and calls of other definitions as bare symbols (only binders become `$n`), so a private helper's name enters the hash.
- **Episode workspace** (`driver.episode_workspace`): `<tree>/cand-1` (git repo, one commit = `COMPARE_BASE`), `<tree>/tmp`, `<tree>/py/orchestrator` (the runtime copy for the brief's compile line, run with `PYTHONPATH=../py`); `experiments/` has no `__init__.py` (namespace package), so `python -m experiments.orc_structural_search.<m>` resolves under `../py` when `../py/experiments/orc_structural_search/` holds the module. `hidden_roots` masks `W/episodes` and the shim binds the episode's tree back, so `../parent`, `../check.json` and `../py` stay visible.
- **Shims**: `shim/claude` installs `shim/model-guard` as `$COMPARE_TREE/.model-guard/claude` (first on the agent's PATH, inside bubblewrap) and strips `COMPARE_*` from the agent; an evaluation's `command.sh` is `cd … && env COMPARE_ROOT=… <cmd>` run with the launcher's process environment (`evaluation._launch(argv, env)`), so a variable in the launch env reaches the shim. The guard sees only its own directory, so the allowlist must be a file beside it.
- **Metering** (`metering.coverage(records_dir, claude_sessions=, codex_rollouts=)`, not called anywhere): `scan.claude_sessions(tree, home)` lists Claude session files by the tree's slug; `scan.sources` inlines the Codex rollout glob (`~/.codex/sessions/*/*/*/rollout-*.jsonl`, `cwd` under the tree, mtime ≥ since). An evaluation's `record.json` names `candidates[0]` (the clone, `<tree>/cand-1`) and `created_at`.
- **Memo**: a provider start is `{"record": "started", "identity": "<activation> / <site label>", "attempt", "input_parts", ...}` (`agent_turns.py:212`; `prepare.paired_calls` pairs starts to `calls/<n>`), so realized sites are the `identity` values of `started` rows; an I3 run has `terminal.json` and no memo.
- **Three-arm** (`three_arm.py`, 471 lines): `ARMS = ("I1","I2","I3")`, `PARENT_OF`, `arm_config(base, interface)` with `condition="topology-only"` fixed, rows keyed by `arm` = interface; `check_run` compares the run configuration with the criterion's `envelope`; `three_arm_readout` (55 lines) imports `ARMS`. `criteria/three_arm.json` (`envelope.interfaces`, `envelope.condition`) is frozen and its SHA-256 is in the running readout's rows.
- **Line budgets**: `candidates.py` 500 (−≈90 after the one-site move, +≈20), `driver.py` 484 (−47 after the catalog-helper move, +≈18), `acceptance.py` 388 (+≈25), `three_arm.py` 471 (+≈22), `three_arm_readout.py` 55, `records.py` 464 (+≈8), `briefs.py` 107, `config.py` 51, `metering.py` 168, `evaluation.py` 233, `mode1.py` 101 (+47), `scan.py` 147, `tests/experiments/test_orc_structural_search_driver.py` 497 and `test_compare_harness.py` 652 (new tests go to new modules).

## Global Constraints

- Branch: `feat/orc-structural-search` merges into `main` first; work in a fresh worktree on a branch from that `main` (`git worktree add /home/ollie/Documents/agent-orchestration-module -b feat/orc-structural-search-module main`); never edit `/home/ollie/Documents/agent-orchestration-search` or any `/home/ollie/ss3-*` root while the three-arm readout runs; no file under `orchestrator/` changes.
- Every module ≤ 500 lines (`wc -l` in each task's run step); every function ≤ cyclomatic complexity 12; no new dependency.
- No provider is called: scripted `claude`/`codex` from `tests/experiments/orc_structural_search_support.py`; sandboxed tests (`sandboxed` fixture from `tests/experiments/test_orc_structural_search_driver.py`) skip without bubblewrap. Tests assert behaviour, contracts, codes and data, never prompt wording.
- `experiments/orc_structural_search/criteria/three_arm.json`, `phase1.json`, `phase2.json` and `experiments/compare/providers/*.json` stay byte-identical; no successor criterion is committed (tests build one in `tmp_path`); no live task.
- Refusal vocabulary: `scope_exceeded`, `frozen_surface_changed`, `declaration_collision`, `unreadable_child`, `slot_type_changed`, `unbounded_calls` as today; new post-compile codes `policy_refused` and `unsupported_effect_shape`; a `compiler_crash` is an `incident`, never `rejected`.
- Config fields for `module`: `models` (tuple of `:model` literals), `efforts` (tuple of `:effort` literals), `per_call_ceiling_sec` (int); the successor criterion carries the same three names at top level and `envelope.arms`.
- Commits with pathspecs (`git commit -m … -- <paths>`), no assistant attribution and no `Co-Authored-By` trailer; `pytest --collect-only -q` on every new test module; narrow selectors first, then `pytest -q -n 16 --dist=worksteal --basetemp=/home/ollie/.cache/pt tests/experiments/`; Tasks 4 and 5 change the brief and the shims, so they also run `pytest -q tests/experiments/test_compare_pool_summarize.py tests/test_demo_trial_smoke.py`.
- Documentation follows `docs/documentation_conventions.md`; `python scripts/check_doc_links.py <file>` on every changed doc.

## Review Focus

1. A `module` child that keeps the parent's `common` import and references `common/CheckReport` by qualified name (as all six Phase 1 children did) is accepted: the graph check compares module qualifiers, not type names (Task 2 `test_a_qualified_reference_into_an_imported_module_is_no_graph_change`).
2. A `module` child whose provider call carries no `:model` or `:effort` literal (the registry default would apply) is refused `policy_refused`, so the arm's models stay pinned (Task 2 `test_a_provider_call_without_a_model_or_effort_literal_is_refused_under_module`).
3. An unchanged child under `module` keeps the parent's skeleton and allocation under the wider coverage, so revisit and collapse figures stay comparable (Task 3 `test_an_unchanged_child_keeps_the_parents_skeleton_under_module`).
4. The check command still validates against the staged parent after the mutator commits or rewrites the workspace's git history (Task 4 `test_the_check_uses_the_staged_parent_after_the_mutator_commits`).
5. A session with no native session file (scripted CLIs) records `consumption` `unavailable` and `session_files` `[]`, never zero and never an exception (Task 6 `test_rows_carry_the_criterion_hash_and_unavailable_markers_without_receipts`).
6. An evaluation whose provider calls exceed its planned maximum is stopped by the shim, not by the ledger after the fact: the run fails as a provider failure and the refused call is on record (Task 2b `test_an_evaluation_beyond_its_planned_maximum_fails_at_the_shim`).

---

### Task 1: The `module` condition at the source level; the one-site transaction moves to `one_site.py`

**Files:**
- Modify: `experiments/orc_structural_search/config.py`, `experiments/orc_structural_search/candidates.py`, `experiments/orc_structural_search/acceptance.py` (import only)
- Create: `experiments/orc_structural_search/one_site.py`
- Test: new `tests/experiments/test_orc_structural_search_module.py`; `tests/experiments/test_orc_structural_search_{validation,sites,candidates}.py` (imports; one config test)

**Interfaces:**
- `config.CONDITIONS = ("topology-only", "prompt-only", "provider-only", "joint", "module")`; `ExperimentConfig` gains trailing defaulted fields `models: tuple[str, ...] = ()`, `efforts: tuple[str, ...] = ()`, `per_call_ceiling_sec: int | None = None`; `__post_init__` raises `ValueError("module needs models, efforts and per_call_ceiling_sec")` when `condition == "module"` and any is empty or `None`; `load_config` tuples `models`/`efforts` when present (they are optional, unlike `mutable_files`).
- `candidates`: `PROMPT_CONDITIONS`, `PROMPT_SIGNATURE_CONDITIONS`, `TOPOLOGY_CONDITIONS` gain `"module"`; new `TUNING_CONDITIONS = PROVIDER_CONDITIONS | {"module"}` used by `_condition_verdict` for the `:model/:effort values` surface (`_plain_file_verdict` keeps `PROVIDER_CONDITIONS`); `_split_forms(forms, private_types: frozenset[str] = frozenset())` keys a `defrecord`/`defunion`/`defenum` whose name is in `private_types` as a definition instead of a frozen form; `_module_verdict(..., private: bool = False)`: when `private`, computes `imported = ⋃ _import_names(import forms of the parent)`, refuses a child type declaration named in `imported` (`declaration_collision`, "<name> shadows an imported name"), frees `private_types` = type-declaration names of parent ∪ child not exported and not imported, and treats every non-exported definition as mutable; `_definition_verdict(..., private: bool)`: an added or removed non-exported definition is `ACCEPTED` when `private` (an exported one stays `scope_exceeded`); `_orc_file_verdict` passes `private = config.condition == "module" and is_mutable`, so `common.orc` keeps today's rules. `validate_frozen_surfaces`'s docstring gains the `module` sentence.
- `one_site.validate_one_site(parent, child, receipt, config) -> Verdict` (moved verbatim with `_one_site_verdict`, `_owner_and_site`, `_scope_verdict`, `_one_form`, `_masked_form`; imports what it needs from `candidates`); `acceptance.py` and the two tests import it from `one_site`.
- Fixture shared by later tasks (module-level constants in the new test module): `MODULE_CONFIG` = `direct.orc`/`("run",)`/`condition "module"`/`interface "I1"`/`entry_workflow "direct::run"`/`providers_file "providers.json"`/`command_boundaries_file "commands.json"`/`models ("gpt-6.1-sol", "claude-opus-5-5")`/`efforts ("high", "medium")`/`per_call_ceiling_sec 5400`; `module_pair(tmp_path, *edits) -> (parent, child)` copies `experiments/orc_structural_search/three_arm/orc` twice and applies `(old, new)` edits once each to the child's `direct.orc` (as `python_pair`); `MODULE_CHILD` = the parent with a private `(defunion Verdict (OK (note String)) (REDO (reason String)))`, a private `review-prompt` (`:fills (task :text) (summary :text)`, `-> Verdict`), a private `(defproc review ((task String) (summary String)) -> Verdict :effects ((uses-provider providers.reviewer)) (provider-result providers.reviewer :prompt (review-prompt …) :model "gpt-6.1-sol" :effort "high" :timeout-sec 600))` and `run` rerouted through `(match (review task change.summary) ((OK o) (variant Outcome DONE :summary change.summary)) ((REDO r) (variant Outcome BLOCKED :reason r.reason)))` (syntax as `seeds/implement_review_revise.orc` and the `MUTATOR_I2` helper); it must compile (`compile_candidate(child, MODULE_CONFIG, runtime=REPO).status == "accepted"`, asserted in the first test).

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_module.py
def test_a_module_child_with_private_type_prompt_helper_and_routing_is_accepted_and_refused_under_joint(tmp_path)
    # validate_frozen_surfaces(..., MODULE_CONFIG).accepted is True; the child compiles; under replace(MODULE_CONFIG,
    # condition="joint", mutable_definitions=("run", "implement-prompt")) the code is "scope_exceeded"
@pytest.mark.parametrize(...)  # ids: common-type, common-defproc, entry-param, export-set, import-form, own-outcome,
                               # providers-file, commands-file, added-file
def test_module_refuses_each_frozen_surface_with_its_code(tmp_path, edit, code)
    # common.orc: a field added to Change -> frozen_surface_changed; a defproc added there -> scope_exceeded;
    # run gains a parameter -> frozen_surface_changed; (export run) -> (export run review) -> frozen_surface_changed;
    # :only (Change Outcome) -> :only (Change CheckReport Outcome) -> frozen_surface_changed;
    # (defunion Outcome (DONE (summary String))) beside the import -> declaration_collision;
    # providers.json rebinding coder -> frozen_surface_changed; commands.json edited -> frozen_surface_changed;
    # notes.txt added -> scope_exceeded
def test_a_renamed_private_helper_and_a_removed_private_prompt_are_accepted_under_module(tmp_path)
def test_a_tuning_change_passes_source_validation_under_module(tmp_path)   # :effort "high" -> "medium": accepted here (Task 2 judges it)
# test_orc_structural_search_candidates.py
def test_load_config_requires_the_allowlist_and_ceiling_under_module(tmp_path)  # ValueError naming models
# test_orc_structural_search_validation.py: the CONDITION_CASES and HELPER_CASES stay as they are (legacy outcomes)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_module.py tests/experiments/test_orc_structural_search_candidates.py -k "module"` — expected: FAIL (`ValueError: condition must be one of`).
- [ ] **Step 3: Implement** `config.py`, the `candidates.py` changes, `one_site.py`, the import updates.
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_{module,validation,sites,candidates}.py` and `pytest --collect-only -q tests/experiments/test_orc_structural_search_module.py` — expected: PASS; `wc -l experiments/orc_structural_search/candidates.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: the module edit condition admits added, removed and rewritten private definitions, prompts and types of the mutable file while imports, exports, the entry signature, common.orc and the provider and command files stay frozen; the one-site transaction moves to one_site.py" -- experiments/orc_structural_search/config.py experiments/orc_structural_search/candidates.py experiments/orc_structural_search/one_site.py experiments/orc_structural_search/acceptance.py tests/experiments/test_orc_structural_search_module.py tests/experiments/test_orc_structural_search_validation.py tests/experiments/test_orc_structural_search_sites.py tests/experiments/test_orc_structural_search_candidates.py`

### Task 2: Closed-program admission: allowlist and ceiling, module graph, public contract, effect shapes; a compiler crash is an incident

**Files:**
- Create: `experiments/orc_structural_search/closed_checks.py` (pure: `json`, `pathlib`, `collections.abc`; no experiment imports but `config`)
- Modify: `experiments/orc_structural_search/acceptance.py` (`judge_child`)
- Test: new `tests/experiments/test_orc_structural_search_closed_checks.py` (pure functions over synthetic programs); `tests/experiments/test_orc_structural_search_module.py` (`judge_child` level)

**Interfaces:**
- `closed_checks.closed_program(root: Path, build_key: str) -> dict`: `json.loads` of `<root>/.orchestrate/build/<build_key>/closed_program.json`.
- `closed_checks.perform_nodes(program: Mapping) -> list[dict]`: every `{"k": "perform"}` mapping under `program["body"]` and each `program["definitions"][name]["body"]`, depth first, lists and mappings walked.
- `closed_checks.effect_shape_refusal(program) -> dict | None`: the first perform whose `class` is in `UNSUPPORTED = {"provider_phased": "phased delivery's live qualification is unselected", "agent": "...", "agent_turn": "the agent_turn_unresolved defect and the process-group kill escape"}` → `{"refusal_code": "unsupported_effect_shape", "detail": f"{site}: {class}: {reason}"}`.
- `closed_checks.policy_refusal(program, config: ExperimentConfig) -> dict | None`: `None` unless `config.condition == "module"`; for each perform with `class == "provider"`: `policy` must hold `model`, `effort` and `timeout_sec`, each `{"k": "lit"}`; `model.v in config.models`, `effort.v in config.efforts`, `timeout_sec.v <= config.per_call_ceiling_sec`; the first violation → `{"refusal_code": "policy_refused", "detail": f"{site}: {key} {'is not a literal' | 'missing' | f'{value!r} is outside the allowlist' | f'{value} exceeds the ceiling {ceiling}'}"}`.
- `closed_checks.qualifiers(program) -> set[str]`: `name.split("::")[0]` for every key of `program["types"]` and `program["definitions"]` (`set()` when a part is not a mapping).
- `closed_checks.graph_refusal(child: Mapping, parent: Mapping) -> dict | None`: `qualifiers(child) - qualifiers(parent)` non-empty → `{"refusal_code": "frozen_surface_changed", "detail": f"modules referenced beyond the parent's: {sorted(...)}"}`.
- `closed_checks.contract_refusal(child, parent, entry: str) -> dict | None`: `child["params"] != parent["params"]` or `child["result"] != parent["result"]` → `{"refusal_code": "slot_type_changed", "detail": f"the {'parameters' | 'result type'} of {entry} differ from the parent's"}`.
- `acceptance.judge_child` after a successful compile and before `slot_refusal`: `refusal = effect_shape_refusal(program) or policy_refusal(program, config)`; then (only when still `None`) the parent's program (`compile_candidate(parent, …)`, as today's `entry_result` call) feeds `graph_refusal` and, after `slot_refusal`/`unbounded_refusal`, `contract_refusal` (which replaces `entry_result`; remove `entry_result`). A compile whose first diagnostic code is `compiler_crash` returns `{**shown, "outcome": "incident", **diagnosis(compiled)}` instead of `rejected`.

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_closed_checks.py (programs built by a helper perform(cls, site, policy=None))
def test_effect_shapes_refuse_phased_and_agent_classes_and_pass_provider_and_command()
def test_policy_refuses_a_literal_outside_the_allowlist_a_name_reference_a_missing_effort_and_a_timeout_over_the_ceiling()
def test_policy_is_not_checked_under_legacy_conditions()
def test_graph_refusal_fires_for_a_new_qualifier_and_not_for_a_new_type_of_an_imported_module()
def test_contract_refusal_names_parameters_or_result()
# test_orc_structural_search_module.py (judge_child with runtime=REPO; MODULE_CHILD from Task 1)
def test_a_model_outside_the_allowlist_and_a_timeout_over_the_ceiling_are_refused_policy_refused(tmp_path)
def test_a_provider_call_without_a_model_or_effort_literal_is_refused_under_module(tmp_path)
def test_a_model_from_a_helper_parameter_is_refused_as_a_name_reference(tmp_path)   # (defproc call ((m String)) ... :model m)
def test_a_qualified_reference_into_an_imported_module_is_no_graph_change(tmp_path)  # common/CheckReport used in a private record: accepted
def test_an_agent_child_is_refused_unsupported_effect_shape(tmp_path)   # (agent providers.coder :model "gpt-6.1-sol" :effort "high") then provider-result on it; config topology-only
def test_an_unexported_entry_whose_parameter_type_changes_is_refused_slot_type_changed(tmp_path)  # as the driver test for the result type
def test_a_compiler_crash_is_an_incident_not_a_rejection(tmp_path)   # fake_runtime from test_candidates: outcome "incident", diagnostics_class "compiler_crash"
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_closed_checks.py tests/experiments/test_orc_structural_search_module.py` — expected: FAIL (ImportError / wrong codes).
- [ ] **Step 3: Implement** `closed_checks.py` and the `judge_child` wiring; `ledger.max_provider_calls` is untouched (its non-literal `:max` refusal is covered by `test_orc_structural_search_ledger.py`).
- [ ] **Step 4: Run** the two modules, `pytest --collect-only -q tests/experiments/test_orc_structural_search_closed_checks.py`, then `pytest -q tests/experiments/test_orc_structural_search_{validation,driver,i3,three_arm}.py` — expected: PASS; `wc -l experiments/orc_structural_search/acceptance.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: acceptance judges the compiled child's closed program: perform policies against the module allowlist and per-call ceiling, module qualifiers against the parent's, params beside the result type, and phased or agent effect shapes refused under every condition; a compiler crash is an incident" -- experiments/orc_structural_search/closed_checks.py experiments/orc_structural_search/acceptance.py tests/experiments/test_orc_structural_search_closed_checks.py tests/experiments/test_orc_structural_search_module.py`

### Task 2b: The planned maximum from the closed program and the shim's call cap

**Files:**
- Modify: `experiments/orc_structural_search/closed_checks.py` (from Task 2: `planned_maximum`), `experiments/orc_structural_search/ledger.py` (`planned_calls`), `experiments/orc_structural_search/driver.py` (`evaluate_and_scan`: the launch env), `experiments/compare/shim/claude` (`shim/codex` is its hard link; keep it so), `experiments/compare/README.md` (shim section), `experiments/orc_structural_search/README.md` (call cap paragraph)
- Test: new `tests/experiments/test_orc_structural_search_bound.py` (`planned_maximum` over synthetic programs; `planned_calls` on `MODULE_CHILD`-style roots with `runtime=REPO`); new `tests/experiments/test_compare_call_cap.py` (the `world` fixture of `tests/experiments/compare_harness_support.py`); the evaluation-level test in `tests/experiments/test_orc_structural_search_module.py`

**Interfaces:**
- `closed_checks.planned_maximum(program: Mapping) -> int`: walks `program["body"]` and every `program["definitions"][name]["body"]` carrying the product of the enclosing `loop` and par-map nodes' `max` values; each `perform` whose `class` is in `{"provider", "provider_phased", "agent", "agent_turn"}` adds that product; a `max` that is not an `int` raises `ledger.CallCapExceeded` (an unbounded child; `judge_child` already turns that into `unbounded_calls`). `command` and `run_ref` performs add nothing. The sum covers a provider reached through a local `proc-ref` binding, a private helper called under a loop, and (when v2 opens them) imported definitions, because the closed program carries them all.
- `ledger.planned_calls(root, config, *, runtime=None) -> int`: under `config.condition == "module"`, `compile_candidate(root, config, runtime=runtime)` (the build cache under the archived root is reused when present) and `planned_maximum(closed_program(root, build_key))`; under every other condition unchanged (`max_provider_calls(*entry_of(root, config))`), so legacy reservations and `test_orc_structural_search_ledger.py` keep their numbers. `unbounded_refusal` passes `runtime` through.
- `driver.evaluate_and_scan`: the `planned` value reserved for the launch is also passed as `COMPARE_MAX_CALLS=<planned>` in the launch `env` (the evaluation's `command.sh` runs under that env, which reaches the shim; see Feasibility, Shims); episodes set nothing (an episode's planned maximum is 1 and a mutator's nested CLI launches are part of its call).
- Shim: after the call directory `calls/<n>` is created, `if [ -n "${COMPARE_MAX_CALLS-}" ] && [ "$n" -gt "$COMPARE_MAX_CALLS" ]`, write `shim: call <n> exceeds the evaluation's planned maximum <cap>; refused before the CLI ran` to `calls/<n>/stderr.txt` and stderr and exit 75 without running the real CLI (the message must match none of `quota.QUOTA_LINE`'s patterns, so the run is a provider failure, never a quota incident); `COMPARE_MAX_CALLS` joins the variables stripped from the agent's environment (`env -u`). The runtime records the nonzero exit as `provider_exit_nonzero`, the evaluation's outcome is `failed` under the frozen rule, and `ledger.settle` counts the refused call's directory as today (one conservative call).

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_bound.py (synthetic programs from a helper; MODULE_CHILD roots from Task 1)
def test_the_planned_maximum_counts_provider_performs_times_enclosing_loop_maxima()     # provider under loop max 3 inside loop max 2 -> 6; command perform -> 0
def test_agent_and_phased_performs_count_and_commands_do_not()
def test_a_non_integer_loop_maximum_is_unbounded()                                       # CallCapExceeded
def test_a_provider_reached_through_a_local_proc_ref_binding_is_planned(tmp_path)        # module child: (proc-ref review) passed to a private helper that calls it under loop/recur :max 2 -> planned 3 (coder + 2); max_provider_calls on the same source gives 1
def test_legacy_conditions_keep_the_source_count(tmp_path)                               # topology-only root: planned_calls == max_provider_calls
# test_compare_call_cap.py
def test_the_shim_refuses_the_call_beyond_compare_max_calls(world)                      # COMPARE_MAX_CALLS=1, two calls: calls/2/stderr.txt holds the message, exit 75, the fake claude ran once
def test_without_compare_max_calls_every_call_runs_and_the_agent_never_sees_it(world)   # env inside the call lacks COMPARE_MAX_CALLS
def test_the_cap_message_is_not_a_quota_line()                                           # quota.quota_reason over the message is None
# test_orc_structural_search_module.py
def test_an_evaluation_beyond_its_planned_maximum_fails_at_the_shim(sandboxed, world, monkeypatch)
    # ledger.planned_calls patched to 1 for a module child making two provider calls: row outcome "failed", no incident,
    # the run's memo records provider_exit_nonzero at the second call, calls/2/stderr.txt names the planned maximum, ledger settles 2
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_bound.py tests/experiments/test_compare_call_cap.py tests/experiments/test_orc_structural_search_module.py -k "planned or cap or maximum"` — expected: FAIL.
- [ ] **Step 3: Implement** `planned_maximum`, the `planned_calls` branch, the `evaluate_and_scan` env line, the shim block and the two README paragraphs.
- [ ] **Step 4: Run** the three modules, `pytest --collect-only -q tests/experiments/test_orc_structural_search_bound.py tests/experiments/test_compare_call_cap.py`, then `pytest -q tests/experiments/test_compare_harness.py tests/experiments/test_compare_pool_summarize.py tests/experiments/test_orc_structural_search_ledger.py tests/experiments/test_orc_structural_search_driver.py` — expected: PASS; `wc -l` of `ledger.py`, `driver.py`, `closed_checks.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: a module child's planned maximum is walked from its closed program (perform classes times enclosing loop maxima), and the shim refuses the call beyond the evaluation's planned maximum (COMPARE_MAX_CALLS) before the CLI runs" -- experiments/orc_structural_search/closed_checks.py experiments/orc_structural_search/ledger.py experiments/orc_structural_search/driver.py experiments/compare/shim/claude experiments/compare/README.md experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_bound.py tests/experiments/test_compare_call_cap.py tests/experiments/test_orc_structural_search_module.py`

### Task 3: Skeleton and allocation over every private definition under `module`

**Files:**
- Modify: `experiments/orc_structural_search/candidates.py` (`private_definitions`), `experiments/orc_structural_search/records.py` (`skeleton_hash`, `provider_allocation`, `_normalize_definition`), `experiments/orc_structural_search/driver.py` (`skeleton`, `allocation`)
- Test: `tests/experiments/test_orc_structural_search_records.py`, `tests/experiments/test_orc_structural_search_module.py`

**Interfaces:**
- `candidates.private_definitions(path: Path) -> list[str]`: the names of the file's `defworkflow`/`defproc`/`defun`/`defprompt` forms that are not exported, in source order.
- `records.skeleton_hash(source, *, definitions, private: Sequence[str] = ())` and `records.provider_allocation(source, *, definitions)` unchanged in meaning for `private=()`; with `private`, every definition is normalized in a base scope mapping each private name to `%<index>` (its position in `private`), so a private definition's own name and every call of it render as that placeholder (`_normalize_definition(definition, scope)`; `_Normalizer.bind_params`/`_render_all` start from that scope).
- `driver.skeleton(root, config)`/`driver.allocation(root, config)`: under `module` the definitions are `[*config.mutable_definitions, *private_definitions(root / <mutable .orc file>) not already named]` (entry first, source order) and `private` is the second part; other conditions pass `config.mutable_definitions` as today (`python_skeleton_hash` takes no `private`).

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_records.py
def test_private_definition_names_hash_as_placeholders_under_private()   # renaming a helper and its call site: equal hashes; the helper's body change: different
# test_orc_structural_search_module.py
def test_module_skeleton_covers_added_helpers_and_allocation_lists_their_providers(tmp_path)
    # parent vs MODULE_CHILD: skeleton differs; allocation(child) == {"run": ["providers.coder"], "review": ["providers.reviewer"]}
def test_a_loop_moved_into_a_helper_hashes_by_the_loop_not_the_call(tmp_path)
    # child A: loop/recur :max 3 inline in run; child B: the loop in a private defproc called from run: hashes differ from the parent's and from each other, and B renamed-helper == B
def test_an_unchanged_child_keeps_the_parents_skeleton_under_module(tmp_path)
def test_legacy_conditions_hash_mutable_definitions_only(tmp_path)   # topology-only on MODULE_CHILD's file: the hash equals records.skeleton_hash(source, definitions=("run",))
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_records.py tests/experiments/test_orc_structural_search_module.py -k "private or skeleton or helper"` — expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_{records,module,driver}.py` — expected: PASS; `wc -l` of the three modules < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: under the module condition the skeleton hash and provider allocation cover every private definition of the mutable file, entry first, with private names as placeholders" -- experiments/orc_structural_search/candidates.py experiments/orc_structural_search/records.py experiments/orc_structural_search/driver.py tests/experiments/test_orc_structural_search_records.py tests/experiments/test_orc_structural_search_module.py`

### Task 4: The workspace check command and the brief

**Files:**
- Create: `experiments/orc_structural_search/check.py`
- Modify: `experiments/orc_structural_search/briefs.py` (`lisp_scope`), `experiments/orc_structural_search/driver.py` (`episode_workspace`, its callers), `experiments/orc_structural_search/README.md` (Layout: `parent/`, `check.json`, `py/experiments`; the check command)
- Test: new `tests/experiments/test_orc_structural_search_check.py`; `tests/experiments/test_orc_structural_search_briefs.py`; `tests/experiments/test_orc_structural_search_driver.py` (the brief test's call to `episode_workspace`)

**Interfaces:**
- `check.stage(tree: Path, parent_root: Path, config: ExperimentConfig, runtime: Path) -> None`: copies `runtime/experiments/orc_structural_search/{__init__,config,candidates,closed_checks,check}.py` to `tree/py/experiments/orc_structural_search/` (nothing else of the package: no criteria, seeds, README), snapshots `parent_root` to `tree/parent` (`candidates.snapshot(parent_root, {}, tree / "parent")`) and writes `tree/check.json` (`json.dumps(asdict(config))`). `driver.episode_workspace(parent_root, tree, brief, runtime, config)` calls it (the `config` parameter is new; `run_episode` and the driver test pass it).
- `check.main(argv) -> int` (`python -P -m experiments.orc_structural_search.check --parent ../parent --config ../check.json`, cwd = the workspace): `config = load_config`; `validation = validate_frozen_surfaces(parent, cwd, config)`; when accepted, `compile = compile_candidate(cwd, config, runtime=Path("../py").resolve())` and, when that is accepted, `closed = effect_shape_refusal(program) or policy_refusal(program, config) or graph_refusal(program, parent_program) or contract_refusal(program, parent_program, config.entry_workflow)` with the parent compiled the same way; prints one JSON object `{"validation": {"accepted", "code", "detail"}, "compile": asdict(CompileOutcome) | null, "closed": refusal | null, "accepted": bool}`; exit 0 iff `accepted`. The compiler's diagnostics are passed through verbatim (`workflow_lisp_compile_diagnostics.v1`). The I3 brief and `python_scope` are unchanged.
- `briefs.lisp_scope`: the check line becomes `PYTHONPATH=../py python -P -m experiments.orc_structural_search.check --parent ../parent --config ../check.json` for every `.orc` condition; under `module` the scope sentence names "every non-exported definition, prompt and type declaration of" the mutable files and the frozen surfaces sentence lists `config.models`, `config.efforts` and `config.per_call_ceiling_sec` beside imports, the export set, the entry signature, `common.orc`, the providers and command files; no runtime or evidence path.
- Scripted mutators for the tests (Python scripts run as `agent_cmd`, as `MUTATOR`), each calling the check line read from `EPISODE.md`: `REPAIRS_SCOPE` (edits the `:only` list; check exits 1 with `validation.code == "frozen_surface_changed"`; reverts and applies `MODULE_CHILD`'s edits; check exits 0; exits), `REPAIRS_TYPE` (first makes `review` return `Change` where `Verdict` is expected: check exits 1 with a non-empty `compile.diagnostics` whose first `code` is recorded in a file the test reads; repairs; exits), `FINAL_INVALID` (valid edit, check 0, then edits the import form, exits 0), `NO_REPAIR` (valid edit, check 0, exits), `COMMITS_FIRST` (`git commit -q -am x` then `git commit --amend --reset-author -q -m y`, then the check), `SLEEPS` (sleeps 30 s).

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_check.py (episode() and config_of() from test_orc_structural_search_driver; MODULE_CONFIG fields via config_of(condition="module", models=("gpt-6.1-sol", "claude-opus-5-5"), efforts=("high", "medium"), per_call_ceiling_sec=5400))
def test_a_scope_refusal_read_from_the_check_is_repaired_within_one_episode_yielding_one_accepted_child(world)
    # row outcome accepted; exactly one accepted candidate under E/candidates besides the parent; the mutator's log shows the first check's code
def test_a_type_error_gets_compiler_diagnostics_through_the_check_and_is_repaired(world)   # the recorded first code is a compiler code, not "compiler_crash"
def test_a_final_invalid_edit_is_rejected_despite_an_earlier_successful_check(world)       # outcome rejected, refusal_code frozen_surface_changed
def test_the_no_repair_path_checks_once_and_is_accepted(world)
def test_the_check_uses_the_staged_parent_after_the_mutator_commits(world)                 # COMMITS_FIRST: accepted
def test_an_exhausted_episode_settles_its_ledger_entry_and_launches_no_evaluation(world)   # episode_wall_clock_sec 2: outcome exhausted, calls.json entry calls 0, no W/records
def test_the_check_exits_nonzero_on_a_policy_refusal_and_names_the_site(world)             # a :model "gpt-7" child: closed.refusal_code == "policy_refused"
# test_orc_structural_search_briefs.py
def test_the_module_brief_carries_the_allowlist_ceiling_and_a_check_line_without_paths()   # every model, effort and the ceiling appear; no absolute path
# test_orc_structural_search_driver.py: test_the_brief_names_no_runtime_path_and_its_compile_line_runs_from_the_runtime_copy passes config to episode_workspace and still exits 0 on the unchanged parent
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_check.py tests/experiments/test_orc_structural_search_briefs.py` — expected: FAIL.
- [ ] **Step 3: Implement** `check.py`, `stage`, the brief, README.
- [ ] **Step 4: Run** the two modules, `pytest --collect-only -q tests/experiments/test_orc_structural_search_check.py`, `pytest -q tests/experiments/test_orc_structural_search_{driver,i3,three_arm}.py`, and `pytest -q tests/test_demo_trial_smoke.py` — expected: PASS; `wc -l experiments/orc_structural_search/driver.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: the episode brief gives one check command that runs frozen-surface validation, the compile and the closed-program checks from the workspace against the staged parent snapshot; the module brief states its allowlist, ceiling and frozen surfaces" -- experiments/orc_structural_search/check.py experiments/orc_structural_search/briefs.py experiments/orc_structural_search/driver.py experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_check.py tests/experiments/test_orc_structural_search_briefs.py tests/experiments/test_orc_structural_search_driver.py`

### Task 5: The model guard's allowlist (`COMPARE_MODELS`)

**Files:**
- Modify: `experiments/compare/shim/claude` (`shim/codex` is its hard link; keep it so), `experiments/compare/shim/model-guard`, `experiments/compare/README.md` (Guard bullets), `experiments/orc_structural_search/driver.py` (`run_episode` shim env; `evaluate_and_scan` launch env)
- Test: new `tests/experiments/test_compare_model_allowlist.py` (the `world` fixture of `tests/experiments/compare_harness_support.py`, as `test_compare_harness.py`'s guard tests); `tests/experiments/test_orc_structural_search_check.py`

**Interfaces:**
- Shim: when `COMPARE_MODELS` (colon-separated model names) is set, `$guard/models` holds one name per line (written through `mktemp` in `$guard` and `mv -f` only when `cmp -s` differs, as the guard itself); the agent's environment loses `COMPARE_MODELS` with the other `COMPARE_*` variables; without the variable nothing changes.
- Guard: after today's Fable check and default (`--model claude-opus-5-5` when none is given), if `$here/models` exists and the effective `--model` is not one of its lines, print `model guard: '<model>' is not in the run's model allowlist (<names>)` to stderr and exit 2 before the real CLI runs.
- Driver: `run_episode` adds `"COMPARE_MODELS": ":".join(config.models)` to `shim_env` when `config.models`; `evaluate_and_scan` adds the same to the launch `env` when `config.models` (an evaluation of a `module` child); legacy configurations set nothing.

- [ ] **Step 1: Write the failing tests**

```python
# test_compare_model_allowlist.py
def test_a_claude_model_outside_the_allowlist_is_refused_before_the_cli_runs(world, monkeypatch)   # exit 2, stderr names the allowlist, calls/1 recorded, the fake claude never ran
def test_an_allowlisted_model_and_the_default_run(world, monkeypatch)        # --model claude-sonnet-5-5 runs; no --model runs as claude-opus-5-5 (both listed)
def test_the_default_is_refused_when_it_is_not_allowlisted(world, monkeypatch)
def test_the_agent_never_sees_compare_models_and_without_it_the_guard_is_unchanged(world, monkeypatch)
# test_orc_structural_search_check.py
def test_a_module_episode_passes_the_allowlist_to_the_guard(sandboxed, world)   # MUTATOR_FABLE-style mutator asking `claude -p --model claude-sonnet-5-5` under models ("gpt-6.1-sol","claude-opus-5-5"): calls/2/stderr names the allowlist, outcome incident
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_compare_model_allowlist.py tests/experiments/test_orc_structural_search_check.py -k allowlist` — expected: FAIL.
- [ ] **Step 3: Implement** the shim block, the guard check, the driver lines, the README bullets.
- [ ] **Step 4: Run** the two modules, `pytest --collect-only -q tests/experiments/test_compare_model_allowlist.py`, `pytest -q tests/experiments/test_compare_harness.py tests/experiments/test_compare_pool_summarize.py` — expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: the model guard refuses a claude model outside the run's allowlist (COMPARE_MODELS, written beside the guard by the shim); module episodes and evaluations pass the criterion's models" -- experiments/compare/shim/claude experiments/compare/shim/model-guard experiments/compare/README.md experiments/orc_structural_search/driver.py tests/experiments/test_compare_model_allowlist.py tests/experiments/test_orc_structural_search_check.py`

### Task 6: Records: criterion hash, native session files, metering, realized and planned sites; catalog helpers move to `mode1.py`

**Files:**
- Modify: `experiments/orc_structural_search/driver.py`, `experiments/orc_structural_search/mode1.py`, `experiments/orc_structural_search/adaptive.py` (imports), `experiments/orc_structural_search/evaluation.py`, `experiments/orc_structural_search/metering.py`, `experiments/compare/scan.py`, `experiments/orc_structural_search/README.md` (row fields)
- Test: new `tests/experiments/test_orc_structural_search_rows.py`; `tests/experiments/test_orc_structural_search_metering.py`; `tests/experiments/test_compare_harness.py` (one `codex_rollouts` test); `tests/experiments/test_orc_structural_search_driver.py` (imports)

**Interfaces:**
- Move `seed_files`, `archive_seed`, `seed_config`, `catalog_jobs`, `enumerate_catalog` from `driver.py` to `mode1.py` unchanged; `adaptive.py` imports `archive_seed`, `seed_config` from `mode1`; `test_orc_structural_search_driver.py` imports `enumerate_catalog` from `mode1`.
- `scan.codex_rollouts(tree, since, home) -> Iterator[Path]`: the rollouts `sources` globs today (`home/.codex/sessions/*/*/*/rollout-*.jsonl`, mtime ≥ `since`, `codex_cwd` under `tree`); `sources` uses it.
- `metering.consumption(records_dir: Path, tree: Path, since: float, home: Path | None = None) -> dict | str`: `coverage(records_dir, claude_sessions=list(scan.claude_sessions(tree, home)), codex_rollouts=list(scan.codex_rollouts(tree, since, home)))` with `home = home or Path.home()`; returns `UNAVAILABLE` when no provider entry has `calls_with_receipts > 0`, else the report. `metering.session_files(tree, since, home=None) -> list[str]`: the same session files and rollouts as paths, sorted.
- `evaluation.EvaluationRecord.build_key: str = UNAVAILABLE` (after `attempt`), set by `evaluate` from the compile (ORC) or left `UNAVAILABLE` (I3); `evaluation.realized_sites(record) -> dict[str, int] | str`: `Counter(row["identity"] for row in read_memo(memo) if row["record"] == "started")` over `<state_dir>/<run_id>/memo.jsonl`, `UNAVAILABLE` without a memo. `closed_checks.planned_sites(program) -> list[dict]`: `[{"site": node["site"], "class": node["class"]} for node in perform_nodes(program)]`.
- `driver.run_episode(..., home: Path | None = None)`: the row gains `"criterion_sha256": config.criterion_sha256`, `"consumption": consumption(records, tree, created_at, home)` and `"session_files": session_files(tree, created_at, home)`. `driver.evaluate_and_scan(..., home: Path | None = None)`: with `arm = load(record.records_dir / "record.json")`, `tree = Path(arm["candidates"][0]).parent`, the row gains `"criterion_sha256"`, `"consumption": consumption(record.records_dir, tree, arm["created_at"], home)`, `"realized_sites": realized_sites(record)` and `"planned_sites": planned_sites(closed_program(root, record.build_key))` (`UNAVAILABLE` when `build_key` is). `three_arm.py` and `mode1.py` pass nothing new (defaults).

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_metering.py
def test_consumption_reports_tokens_from_a_session_holding_the_calls_prompt_and_is_unavailable_without_one(tmp_path)  # home=tmp_path with .claude/projects/<slug>/s.jsonl
def test_session_files_lists_the_trees_claude_sessions_and_its_codex_rollouts(tmp_path)
# test_compare_harness.py
def test_codex_rollouts_filters_by_cwd_under_the_tree_and_by_time(tmp_path)
# test_orc_structural_search_rows.py (mode1() helper of test_orc_structural_search_driver with criterion_sha256 "ab"*32 in CONFIG)
def test_rows_carry_the_criterion_hash_and_unavailable_markers_without_receipts(sandboxed, world)
    # every episode and evaluation row: criterion_sha256 == "ab"*32; consumption "unavailable"; episode session_files == []
def test_an_evaluation_row_records_realized_and_planned_sites(sandboxed, world)
    # the direct seed: realized_sites == {"change": 1}, planned_sites == [{"site": "change", "class": "provider"}]; an I3 row: both "unavailable"
def test_an_episode_with_a_readable_session_reports_tokens_and_its_file(sandboxed, world)
    # a fake claude that writes <home>/.claude/projects/<slug of its cwd>/s.jsonl holding its stdin as the user turn and usage {10,5,2,3};
    # run_episode(..., env={..., "HOME": home}, home=home): row consumption["claude"]["tokens"] == 20, session_files == [that path]
def test_a_module_episode_identity_differs_from_a_legacy_one_for_the_same_parent_and_index(world)
    # two run_episode calls, index 0, separate work and evidence roots, conditions topology-only and module: episode_id differs
# No new test for the catalog-helper move: the three driver tests that call enumerate_catalog keep passing after the
# import change. The decision's "evaluated snapshot equals the finalized candidate identity" is check_archived before
# every evaluation, covered by test_a_tampered_archived_candidate_is_refused_before_its_evaluation (unchanged).
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_rows.py tests/experiments/test_orc_structural_search_metering.py tests/experiments/test_compare_harness.py -k "codex_rollouts"` — expected: FAIL.
- [ ] **Step 3: Implement**; move the catalog helpers first (a pure move, its own commit if the diff is easier to review).
- [ ] **Step 4: Run** the modules above, `pytest --collect-only -q tests/experiments/test_orc_structural_search_rows.py`, then `pytest -q tests/experiments/test_orc_structural_search_{driver,evaluation,i3,adaptive,three_arm,scoring_phase2}.py` — expected: PASS; `wc -l` of `driver.py`, `mode1.py`, `evaluation.py`, `metering.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: episode and evaluation rows carry the criterion hash, metering coverage from the native session files, the mutator's session file paths and the evaluation's realized and planned perform sites; mode 1's catalog helpers move to mode1.py" -- experiments/orc_structural_search/driver.py experiments/orc_structural_search/mode1.py experiments/orc_structural_search/adaptive.py experiments/orc_structural_search/evaluation.py experiments/orc_structural_search/metering.py experiments/orc_structural_search/closed_checks.py experiments/compare/scan.py experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_rows.py tests/experiments/test_orc_structural_search_metering.py tests/experiments/test_compare_harness.py tests/experiments/test_orc_structural_search_driver.py`

### Task 7: A fourth arm under a successor criterion in the three-arm readout; realized sites and the frozen-surface figure per arm

**Files:**
- Modify: `experiments/orc_structural_search/three_arm.py`, `experiments/orc_structural_search/three_arm_readout.py`, `experiments/orc_structural_search/README.md` (successor criterion fields; the fourth arm's run line; the frozen-surface adjudication)
- Test: `tests/experiments/test_orc_structural_search_three_arm.py` (it is 437 lines; put the new tests in new `tests/experiments/test_orc_structural_search_fourth_arm.py` reusing its `install`, `run`, `configure`, `kind` helpers)

**Interfaces:**
- `three_arm.Arm = namedtuple("Arm", "name interface condition")`; `three_arm.arms(criterion: Mapping) -> list[Arm]`: `envelope.arms` when present (`[{"arm": "I1", "interface": "I1", "condition": "topology-only"}, …, {"arm": "I1/module", "interface": "I1", "condition": "module"}]`), else `[Arm(i, i, envelope["condition"]) for i in envelope["interfaces"]]` (so `three_arm.json` reads as today); a duplicate `arm` name is a `ValueError`.
- `three_arm.arm_config(base, interface, condition="topology-only")`; a `module` arm's config also needs `models`, `efforts`, `per_call_ceiling_sec` from the run configuration file, and `check_run` adds the pairs `("models", (config.models, tuple(frozen["models"])))`, `("efforts", …)`, `("per_call_ceiling_sec", …)` when the criterion has `models`. The successor criterion also carries `anchor_trust` (the rule of `three_arm.json`, reported by `scoring.anchor_checks`) and `anchor_error_rate` (the tolerated share of batch-and-judge anchor pairs that may fail it, predeclared); no field constrains where a candidate ranks against the upstream anchor, and the readout reports anchor outcomes beside the arms' figures.
- `run_episodes(roots, config_path, *, arms, …)`, `episode(root, config, arm: Arm, index, sites, …)` (`interface=arm.interface`, `fields={"arm": arm.name}`), `check_episodes(rows, episodes_per_arm, evidence_root, names)`, `subset(rows, criterion, seed, contaminated)` and `compile_readout(rows, criterion, evidence_root)` iterate `arms(criterion)`; the parent of an arm is `PARENT_OF[arm.interface]`; `ARMS` is removed and `three_arm_readout` takes the names from `arms(frozen)`.
- `arm_figures` adds `"frozen_surface": {"worked_around": n, "asked": n, "none": n, "unadjudicated": n}` over accepted episodes from `E/episodes/<episode_id>/record.json["frozen_surface"]` (`{"verdict": "worked_around" | "asked" | "none", "note": str}`, written by the operator after reading the transcript, beside the scan verdict; absent → unadjudicated); it is reported, never a gate.
- `three_arm_readout.child_figures` adds `realized_sites` (the evaluations' `realized_sites` summed per identity, `unavailable` when every row is), `planned_sites` (the union of site labels) and `unexercised_sites` (planned labels no realized identity ends with); `task_figures` adds per arm `sites_unexercised_mean` over its valued evaluations.

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_fourth_arm.py (successor criterion in tmp_path: three_arm.json | {"models": [...], "efforts": [...], "per_call_ceiling_sec": 5400, "envelope": {..., "arms": [the three + I1/module]}}; run config with the three fields; the scripted codex gains module.py applying MODULE_CHILD's edits when the brief names condition module)
def test_three_arm_json_still_reads_as_three_arms_and_a_successor_names_a_fourth()
def test_a_module_arm_runs_beside_the_three_under_the_successor_criterion(sandboxed, world, pyright)
    # episodes per arm 1: rows' arm in {I1, I2, I3, I1/module}; the module row has condition "module", outcome accepted,
    # skeleton != parent_skeleton, provider_allocation with "review"; readout["arms"] has the four keys and no pooled key
def test_check_run_refuses_a_run_configuration_whose_allowlist_differs_from_the_criterions(tmp_path)
def test_the_frozen_surface_figure_counts_adjudicated_verdicts_per_arm(tmp_path)   # synthetic log + record.json files
def test_the_readout_reports_realized_planned_and_unexercised_sites_per_child(tmp_path)  # synthetic rows: realized {"change": 1}, planned [change, else / repair] -> unexercised ["else / repair"]
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_fourth_arm.py` — expected: FAIL.
- [ ] **Step 3: Implement**; README recipe (the successor criterion's fields, `--config` with `models`/`efforts`/`per_call_ceiling_sec`, the adjudication field).
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_fourth_arm.py tests/experiments/test_orc_structural_search_three_arm*.py`, `pytest --collect-only -q tests/experiments/test_orc_structural_search_fourth_arm.py`, `sha256sum experiments/orc_structural_search/criteria/three_arm.json` equals the committed file's (`git diff --quiet -- experiments/orc_structural_search/criteria/`) — expected: PASS; `wc -l experiments/orc_structural_search/three_arm.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: the three-arm run takes its arms, each with an interface and a condition, from the criterion (a successor criterion may name I1/module with its allowlist and ceiling; three_arm.json reads as before); the readout reports realized, planned and unexercised perform sites per child and the adjudicated frozen-surface figure per arm" -- experiments/orc_structural_search/three_arm.py experiments/orc_structural_search/three_arm_readout.py experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_fourth_arm.py`

### Task 8: Documentation (the plan's last task; no live run)

**Files:** Modify `docs/design/orc_structural_search_driver.md` (condition table: the `module` row from the decision's table, with the closed-program checks and `unsupported_effect_shape`; "Open decisions before Phase 1 comparisons": the non-literal tuning gap is closed for `module` on the closed program and stays recorded for `provider-only`; "Records": `criterion_sha256`, `consumption`, `session_files`, `realized_sites`, `planned_sites`; status line: `module` implemented offline, unselected), `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (interface table: a row "I1 under `module` (arm, unselected)" linking the decision), `docs/index.md` (this plan's existing row: status to "executed offline (scripted providers); no live arm"), `docs/capability_status_matrix.md` row 62 (the `module` condition offline, unselected), `experiments/orc_structural_search/README.md` (consistency pass over Tasks 4–7's additions; "Not implemented": the closed-program planned maximum and the shim call cap, bundle imports, typed-site context in the `module` brief), `docs/plans/2026-10-19-orc-structural-search-module-condition-implementation-plan.md` (status: executed).

- [ ] **Step 1:** Edit; `python scripts/check_doc_links.py` on each changed doc; `pytest -q -n 16 --dist=worksteal --basetemp=/home/ollie/.cache/pt tests/experiments/` — expected: links resolve, suite green.
- [ ] **Step 2: Commit** `git commit -m "docs: the module condition's rows in the driver design, the roadmap's interface table, the index, the capability matrix and the experiment README; the open decision on non-literal tuning closed for module" -- docs/design/orc_structural_search_driver.md docs/plans/2026-10-18-orc-structural-search-roadmap.md docs/index.md docs/capability_status_matrix.md experiments/orc_structural_search/README.md docs/plans/2026-10-19-orc-structural-search-module-condition-implementation-plan.md`

## Flagged For The Coordinator

- **Graph check is a backstop.** `configuration.imports` carries no module graph; the frozen `import` form plus the compiler's `type_unknown` on a never-imported module bound the graph, and `graph_refusal` over `types`/`definitions` qualifiers can fire only if the compiler changes. The design row should say so.
- **`policy_refused`** is a new code (allowlist, ceiling, missing or non-literal policy) and a missing `:model`/`:effort` literal at a provider call is refused under `module` (fully pinned models); whether it joins the locality `OUT_OF_SCOPE` set is a successor-criterion decision.
- **Session files are recorded as paths**, not copied under `E/episodes/<id>/` (the decision allows either); copying Codex rollouts (large) is a follow-up if transcripts must survive home cleanup.
- **The guard's default** `claude-opus-5-5` is refused when a successor criterion's `models` omits it; the criterion must list every model a `claude` call may use. Codex models are stopped at acceptance only (the guard installs as `claude`).
- **Two adjacent moves** are forced by the 500-line rule: the I2 transaction to `one_site.py` (Task 1) and mode 1's catalog helpers to `mode1.py` (Task 6); both are pure moves with import updates.
- **Typed-site context in the `module` brief** ("may carry", decision step 4) is not planned; it needs the manifest at episode time and a brief shape without a receipt.
- **The frozen-surface figure** (gate 1) is an operator adjudication field counted by the readout, not detected automatically; its vocabulary (`worked_around`, `asked`, `none`) is the plan's choice.
- **Successor criterion field names** `models`, `efforts`, `per_call_ceiling_sec`, `anchor_error_rate` and `envelope.arms` (`arm`, `interface`, `condition`) are the plan's choice; no criterion file is committed before an owner selection.
