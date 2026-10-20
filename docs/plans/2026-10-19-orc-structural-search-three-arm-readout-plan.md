# ORC Structural Search Three-Arm Compile-Only Readout Implementation Plan

> **Status:** executed 2026-10-19 (Tasks 1–8). The judge stage of Task 7 did not run under the calibration rule
> (controller ruling R19); results in the [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the one unmet Phase 1 gate of the [structural search roadmap](2026-10-18-orc-structural-search-roadmap.md): the compile-only three-arm readout (I3 matched Python diff, I1 Lisp whole-program, I2 Lisp locus-plus-fragment), E₀ = 6 completed episodes per arm, a collapse verdict per interface, and paid whole-run evaluation of a stratified subset `S`, built offline with scripted providers, run live once under a 65-call cap, and written into the Phase 1 report.

**Architecture:** Extend `experiments/orc_structural_search/` and `experiments/compare/` in place. I3 support lands in the modules that already own each responsibility (`records.py` skeleton hash, `acceptance.py` validation, `briefs.py` brief, `evaluation.py` launch, `prepare.py` collect, `ledger.py` planned maximum). One new module, `three_arm.py`, owns what is genuinely new: the three-arm run (episodes per arm, subset `S`, evaluations, judging through mode 2's `judging.score_pool`) and its readout. Two new candidate roots under `experiments/orc_structural_search/three_arm/` hold the rebound `direct` parent (coder on Codex `gpt-6.1-sol`) and its typed Python equivalent. Mutator isolation is one opt-in environment variable in the shared shim (`COMPARE_HIDE`: directories masked with `--tmpfs` after the `--dev-bind / /`, the episode's own tree re-bound), set by `driver.run_episode`.

**Tech Stack:** Python 3.13 standard library (`ast`, `subprocess`, `random`, `hashlib`); `orchestrator` public CLI and `orchestrator.providers.registry` / `orchestrator.contracts` as a library inside the Python workflow; `experiments/compare` shims (bubblewrap 0.9.0), `pool.py`, `summarize.py`, `score.orc`; pyright 1.1.403 at `/home/ollie/miniconda3/bin/pyright` (mypy is not installed); Codex CLI 0.163.0, Claude Code 2.1.303; tests with scripted `claude`/`codex` executables (`tests/experiments/orc_structural_search_support.py`), no provider called.

**Spec:** `docs/design/orc_structural_search_driver.md` (Proposal Interfaces I1/I2/I3; Edit Validation And Transactions; Search Modes mode 1; skeleton hashing, including "I3: a normalized Python AST"; Records; Controls, Interface Test And Ablations); roadmap Phase 1 Gates (three-arm compile-only readout bullets), Family/Cost table row 1, Decision Points (Collapse, Quota, Lost runs, Model policy), Verification Obligations; `docs/reports/2026-10-18-orc-structural-search-phase1.md` Limitations ("The three-arm compile-only readout was not run", "the episode sandbox is not isolated"); precedents `2026-10-18-orc-structural-search-live-phase1-plan.md`, `2026-10-18-orc-structural-search-phase2-plan.md`, `2026-09-29-mlevolve-orc-python-comparison.md`.

## Coordinator Decisions Applied (binding)

Owner updates of 2026-10-19 replace the earlier Claude mutator and Claude coder: every Codex call uses `gpt-6.1-sol`; the mutator for all 18 episodes is `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --model gpt-6.1-sol --config model_reasoning_effort=high` behind the shims (the registry's `codex_unrestricted_workspace` argv, effort `high` as every seed uses for the Codex role); the parent of all arms is the `direct` seed with its coder rebound to `providers.coder: codex_unrestricted_workspace`, `:model "gpt-6.1-sol" :effort "high"`, archived as a new candidate (the frozen catalog seed is untouched); the I3 workflow uses the same adapter, model, effort and prompt; judges `claude-opus-5-5` and `gpt-6.1-sol`; cap 65 charged calls; Claude share ≈ 2 calls (one judge per task).

## Feasibility (verified in the code at `bac8c50a`)

- **`run_episode` today** (`driver.py:350`): one function for I1 and I2; `interface` is an argument, `site` required iff I2; it archives the parent, builds `W/episodes/episode-<n>/{cand-1,tmp,py}`, runs the mutator with `EPISODE.md` on stdin behind `shim_prefix` (`COMPARE_ROOT/TREE/BASE`, `TMPDIR`), settles the ledger, scans (`scan_episode`), drops `.git`, calls `acceptance.judge_child`, archives an accepted child, logs the row with `skeleton`/`parent_skeleton`/`provider_allocation`. Passing `interface="I3"` with `site=None` already passes its guard; what breaks for a Python parent is `skeleton()`/`allocation()` (they join `.orc` files only and `records.skeleton_hash` raises on missing definitions), `judge_child` (`validate_frozen_surfaces` treats a `.py` as a plain mutable file, then `compile_candidate` runs the ORC compiler), `ledger.planned_calls` (reads the `.orc` entry) and the brief's compile line. Each gets an I3 branch keyed on the mutable file's `.py` suffix.
- **Codex as mutator**: `run_agent` feeds `EPISODE.md` on stdin and `codex exec` reads the prompt from stdin when no `[PROMPT]` is given (`codex exec --help`); cwd is `cand-1`, so the rollout's `cwd` lies under the tree and `scan.sources` reads it from `~/.codex/sessions` (the same path Phase 1's reviewers and the Codex judge used); the shim `codex` is a hard link of `shim/claude`, so the call is recorded under `calls/<n>/` with its patch; `quota.QUOTA_LINE` already matches Codex's `usage limit reached`, `rate limit reached` and `selected model is at capacity` lines. Workspace writes: `--dangerously-bypass-approvals-and-sandbox` turns Codex's own sandbox off; bubblewrap is the confinement, as it was for every Phase 1 Codex call. The model guard installs only as `claude`: a Codex mutator's model is fixed by its argv (`gpt-6.1-sol`), and the guard still pins any `claude` it might start. Nothing in the shims or providers makes a Codex coder or mutator infeasible.
- **Judge binding for `gpt-6.1-sol`**: `score.orc` takes `judge_model` as a typed input (`:model judge_model`, `score.orc:31-36`) and `pool.write_score_inputs` writes the judge's name into it; `experiments/compare/providers/score_codex.json` binds only `providers.judge: codex_unrestricted_workspace`. E-B3 bound `gpt-6.1-sol` with `--judge gpt-6.1-sol=$H/providers/score_codex.json` (`experiments/compare/README.md:246`). So no new binding file is needed and `score_codex.json` stays unchanged; the three-arm criterion names judge `gpt-6.1-sol` with that file. (The coordinator's note that the file "pins gpt-6-sol" is not what the code does; flagged, no action.)
- **`collect` for generic-command runs** (`prepare.py:325-345`): refuses `arm_kind == "generic-command"` because there is no memo; the orc path pairs memo starts with `calls/<n>/` and copies the committed turn's `patch-cand-1.diff`. A generic-command run has `calls/<n>/patch-cand-1.diff` from the shim and needs a terminal of its own; the Python workflow writes `terminal.json` under the run's `state_root` (`record.json` names `<cwd>/.orchestrate/runs` for a command arm, the harness's R34 placement; the task bases ignore `.orchestrate/`, so it never enters a patch). `collect` then reads outcome, failure, calls and wall clock from it and takes the last call's patch as `final`.
- **Shim mounts** (`shim/claude:51-54`): `bwrap --dev-bind / / --bind $COMPARE_TREE/tmp /tmp --tmpfs /dev/shm --tmpfs /var/tmp --unshare-pid --proc /proc --die-with-parent`. bwrap applies mount arguments in order, so `--tmpfs <dir>` after the dev-bind masks a directory and a later `--bind` re-exposes a child (probed: `--tmpfs /home/ollie/Documents --bind .../agent-orchestration-search ...` lists only that child). A pure allowlist ("bind only its own episode tree plus what the brief requires") is **infeasible** at this footprint: the Codex and Claude CLIs need `~/.codex` and `~/.claude` (auth, config, session files the scan reads), node, the conda Python, `/usr`, `/etc`, and the task family's checks import the runtime; enumerating those is a second sandbox design. The decision's stated test ("a mutator cannot read a sibling's file") is met by masking: the evidence root, `W/episodes` (own tree re-bound), `W/records`, `W/runs`, `W/agents`, `W/env-manifests` and any operator `--hide` path (the Phase 1 roots). Home stays readable and scan-detected as before (R35); recorded as the remaining boundary.
- **Prompt equivalence for I3**: a recorded Phase 1 prompt (`/home/ollie/ss-work2/records/*/run-1/calls/1/prompt.txt`) is the `defprompt` body followed by `\n\n## Output Contract` from `orchestrator.contracts.prompt_contract.render_output_bundle_contract_block` under delivery `file/2` (`prompt_delivery._FILE_2`), with a `- path:` line relative to the agent's working directory. The runtime composes it in `orchestrator/workflow/evaluated/providers.py` (`resolve_provider_input`, `launch_provider`); the Python workflow renders the same block through that library and the registry template's argv, and an offline test proves byte equality with the ORC parent's prompt except the `- path:` line.
- **Line budgets**: `candidates.py` is at 500 (nothing is added there), `scoring.py` at 476 (the three-arm readout lives in `three_arm.py`), `driver.py` at 445 (+≈12), `prepare.py` at 444 (+≈25), `acceptance.py` 73, `records.py` 336, `evaluation.py` 213, `briefs.py` 66, `ledger.py` 199.
- **Budget arithmetic** (planned-maximum reservation, `ledger.reserve`): episodes 18 × 1; evaluations ≤ 12 × the child's planned maximum (a child of the rebound `direct` that adds a check-gated repair loop plans up to 3; `ledger.max_provider_calls` refuses an unbounded child at acceptance), so ≤ 36; judges 2 tasks × 2 judges × 1 batch (≤ 6 clones + 2 anchors per task fit the D4 ten) = 4; the rebound parent's live smoke 1. Planned maximum 59 ≤ 65. The planner adds one live I3-parent smoke evaluation (1 call, total 60) because the Python route has no live exposure before the paid subset; the coordinator may strike it.

## Global Constraints

- Work in `/home/ollie/Documents/agent-orchestration-search` on `feat/orc-structural-search`; no file under `orchestrator/` changes; every module ≤ 500 lines; every function ≤ cyclomatic complexity 12.
- Offline tasks call no provider: scripted `claude`/`codex` (`tests/experiments/orc_structural_search_support.py`), a scripted Codex mutator and a scripted judge; sandboxed tests skip without bubblewrap as today. Tests assert behaviour and contracts, never prompt text.
- Models: `gpt-6.1-sol` (mutator, rebound coder, I3 coder, OpenAI judge), `claude-opus-5-5` (Claude judge; the guard's default for any `claude` an agent starts), `claude-sonnet-5-5` only where a child reuses it from the parent module (the rebound parent no longer names it); never Fable, in any call.
- Envelope, matched across arms and equal to Phase 1's I1: parent = the rebound `direct` candidate (I3: its matched Python workflow); condition `topology-only`; mutator `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --model gpt-6.1-sol --config model_reasoning_effort=high` behind the shims; per-episode wall clock 3,600 s; per-evaluation wall clock 14,400 s; tasks `resume-projection-integrity` (base `1cd60767`) and `pure-result-replay` (base `f80e551a`) with their existing `seed/dev-check.json`; E₀ = 6 completed episodes per arm (I1 rerun fresh); I2 sites from the implemented manifest (`sites.site_manifest`), uniform over `eligible_sites` with `random.Random(f"{run_seed} {episode_index}")`, `run_seed` recorded; episodes one at a time, evaluations at concurrency 4.
- Budget: `--call-cap` such that the ledger total never exceeds 65 charged calls over smoke and main run (smoke roots separate: main run cap = 65 − smoke calls); immediate zero-work refusals (exit within 2 s, no output) are uncharged under the 2026-10-18 controller ruling and are listed, not subtracted silently; quota guard and `--continue` as in Phase 1.
- `criteria/three_arm.json` frozen (sha256 recorded in `E3/criterion.sha256` and the run config's `criterion_sha256`) before any live call; `score_codex.json` and `criteria/phase1.json` unchanged.
- Live roots: a fresh runtime worktree `RT3=/home/ollie/ss3-runtime` at this plan's final commit, work root `W3=/home/ollie/ss3-work`, evidence root `E3=/home/ollie/ss3-evidence`, pools `P3=/home/ollie/ss3-pools`, smoke roots `/home/ollie/ss3-{work,evidence}-smoke`; none under `/home/ollie/Documents/agent-orchestration*`, `/tmp`, `/dev/shm`, `/var/tmp`; never touch `/home/ollie/ss-runtime`, `ss-driver`, `ss-driver2`, `ss-evidence2`, `ss-work2`, `ss-pools` (every existing earlier root, these included, is passed as `--hide` so no mutator reads them; the operator script lists them). Solution hashes via `--solution` only.
- Mutator isolation is a prerequisite of every live episode (Task 1 before Task 7); the `agent_turn_unresolved` runtime defect (`orchestrator/workflow/evaluated/agent_turns.py::_verify_completion`, a second agent turn inside `loop/recur`) is out of scope: a child that hits it is an incident under the frozen rule and is reported as such.
- Metrics per arm, never pooled across arms: acceptance per episode, edit locality, distinct skeletons, revisit rate, exact repeats by `program_digest`, terminal-only share against 0.75 → collapse verdict; `S` values descriptive (no separation decision; the Phase 2 decision stands).
- Readout through `three_arm readout` over `summarize`'s `results.json` (clone-id join via `scoring.join_scores`); no ad hoc joins; missing receipts `unavailable`, never 0.
- Commits with pathspecs; no assistant attribution, no `Co-Authored-By` trailer; `pytest --collect-only` on new test modules; narrow selectors first, then `pytest -q -n 16 --dist=worksteal --basetemp=/home/ollie/.cache/pt tests/experiments/`; one orchestrator smoke (`tests/test_cli_smoke*.py` or the repository's named smoke selector) when provisioning or prompts change (Task 2 adds a candidate root and a workflow registry row).

## Review Focus

1. A mutator that reads a sibling episode's file or the evidence root gets nothing back: the read fails inside the sandbox, while the mutator still reads its own `cand-1` and `../py` (Task 1 `test_a_mutator_cannot_read_a_siblings_file_or_the_evidence_root`).
2. The I3 parent sends the coder exactly the ORC parent's prompt bytes except the `- path:` line, through the registry's `codex_unrestricted_workspace` argv with `gpt-6.1-sol`/`high` (Task 3 `test_i3_parent_sends_the_orc_parents_prompt_except_the_result_path`).
3. An I3 child that edits a frozen top-level definition (a prompt constant, the adapter, a dataclass) or changes `run`'s signature is refused `scope_exceeded`/`frozen_surface_changed` and never evaluated; a child that only adds a helper and rewires `run` is accepted with a new skeleton (Task 4 `test_i3_refuses_edits_outside_the_mutable_functions` and `test_i3_accepts_a_helper_and_a_rewired_run_with_a_new_skeleton`).
4. The subset rule is deterministic and prefers distinct skeletons: the same log and seed choose the same two children; two accepted children with equal skeletons yield one chosen plus the seeded tie-break among the rest, and a contaminated child is never chosen (Task 6 `test_subset_prefers_distinct_skeletons_and_is_reproducible`).
5. A three-arm run whose next launch would exceed the cap refuses it before any workspace or clone exists, with every earlier row intact; judges enter the ledger (Task 6 `test_three_arm_cap_refuses_a_launch_and_judges_enter_the_ledger`).

---

### Task 1: Mutator isolation in the shim and the driver

**Files:**
- Modify: `experiments/compare/shim/claude` (`shim/codex` is its hard link; keep it so), `experiments/compare/README.md` (shim section: `COMPARE_HIDE`)
- Modify: `experiments/orc_structural_search/driver.py` (`run_episode`, `run_agent` callers: hide list), `README.md` (Layout: what the mutator cannot see)
- Test: `tests/experiments/test_compare_harness.py`, `tests/experiments/test_orc_structural_search_driver.py`

**Interfaces:**
- Shim: an optional `COMPARE_HIDE` (colon-separated absolute directories). For each existing directory `d` in it the bwrap argv gains `--tmpfs d` after `--dev-bind / /`; then `--bind "$COMPARE_TREE" "$COMPARE_TREE"` always follows (re-exposes the agents' tree when its parent was masked; a no-op otherwise). The agent's environment loses `COMPARE_HIDE` like the other `COMPARE_*` variables. Without the variable the argv is byte-identical to today's.
- `driver.hidden_roots(work_root: Path, evidence_root: Path, hide: Sequence[Path] = ()) -> list[Path]`: `[evidence_root, work_root/"episodes", work_root/"records", work_root/"runs", work_root/"agents", work_root/"env-manifests", *hide]`, each created (`mkdir(parents=True, exist_ok=True)`) so bwrap finds a mount point.
- `driver.run_episode(..., hide: Sequence[Path] = ())`: `shim_env` gains `"COMPARE_HIDE": os.pathsep.join(map(str, hidden_roots(...)))`; `driver.main` and `mode1.run_mode1` gain `--hide PATH` (repeatable) passed through; the episode row records `"hidden_roots": [...]`.

- [ ] **Step 1: Write the failing tests**

```python
# test_compare_harness.py
def test_compare_hide_masks_directories_and_keeps_the_tree(world):
    # a run whose fake claude runs `ls <masked>; cat <masked>/secret; ls $COMPARE_TREE/cand-1` with COMPARE_HIDE=<masked>:
    # stdout lacks "secret", the cat exits nonzero, cand-1 is listed; without COMPARE_HIDE the secret is read
def test_the_agent_never_sees_compare_hide(world):
    # `env` inside the call shows no COMPARE_HIDE, COMPARE_ROOT, COMPARE_TREE or COMPARE_BASE
# test_orc_structural_search_driver.py
def test_a_mutator_cannot_read_a_siblings_file_or_the_evidence_root(sandboxed, world):
    # W/episodes/episode-0/cand-1/direct.orc and E/log.jsonl exist before episode 1; the mutator's fake claude cats
    # both and its own direct.orc and ../py/orchestrator/__init__.py; the call's stdout holds the own-file content
    # and neither sibling's; row["hidden_roots"] names E and the five work-root directories; outcome is not "incident"
def test_hide_paths_from_the_command_line_reach_the_episode(world):
    # run_mode1(..., hide=[p]) -> the episode row's hidden_roots contains str(p)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_compare_harness.py -k compare_hide tests/experiments/test_orc_structural_search_driver.py -k "siblings or hide_paths"` — expected: FAIL.
- [ ] **Step 3: Implement** the shim block (a bash array built from `COMPARE_HIDE`, `[ -d ]` guarded), `hidden_roots`, the `run_episode`/`run_mode1`/`main` plumbing; README paragraphs.
- [ ] **Step 4: Run** the two test modules in full, then `pytest -q tests/experiments/test_compare_pool_summarize.py` (judges use the same shim unchanged) — expected: PASS; `wc -l experiments/orc_structural_search/driver.py` < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: mutator isolation: the shim masks COMPARE_HIDE directories under bubblewrap and the driver hides the evidence root, sibling episodes and the work root's evaluation directories from every episode" -- experiments/compare/shim/claude experiments/compare/README.md experiments/orc_structural_search/driver.py experiments/orc_structural_search/mode1.py experiments/orc_structural_search/README.md tests/experiments/test_compare_harness.py tests/experiments/test_orc_structural_search_driver.py`

### Task 2: The rebound parent candidate roots (ORC and Python) and the generic-command collect path

**Files:**
- Create: `experiments/orc_structural_search/three_arm/orc/{direct.orc, common.orc, providers.json, commands.json, dev_check.py}` (`direct.orc` = the seed with `:model "gpt-6.1-sol" :effort "high"`; `providers.json` = `{"providers.coder": "codex_unrestricted_workspace"}` plus the other three bindings as in `seeds/providers.json` so I2 helpers may name them; `common.orc`, `commands.json`, `dev_check.py` byte-identical copies of the seeds')
- Create: `experiments/orc_structural_search/three_arm/python/{direct.py, providers.json, dev_check.py}`
- Modify: `experiments/compare/prepare.py` (`collect`), `experiments/compare/README.md` (generic-command collect), `workflows/README.md` (registry row for `three_arm/orc/direct.orc`)
- Test: `tests/experiments/test_orc_structural_search_seeds.py` (compile the rebound seed), `tests/experiments/test_compare_harness.py` (collect), new `tests/experiments/test_orc_structural_search_python_workflow.py`

**Interfaces:**
- `three_arm/python/direct.py`, the matched typed workflow, one file, standard library plus the runtime library on `PYTHONPATH`:
  - frozen top level: `@dataclass(frozen=True) class Change(summary: str, account: str)`, `CheckReport(passed: bool, failing: list[str], excerpt: str)`, `Outcome` as a tagged union (`DONE(summary)` / `BLOCKED(reason)` dataclasses under a `Outcome = DONE | BLOCKED` alias); `IMPLEMENT_PROMPT: str` whose text is the `defprompt` body with `{task}`/`{repo}` fills; `PROVIDERS: dict[str, str]` read from the sibling `providers.json`; `MAX_PROVIDER_CALLS: int = 8`; `provider_result(provider: str, prompt: str, *, model: str, effort: str, timeout_sec: int, result: type[T]) -> T` (renders body + the runtime's delivery `file/2` output-contract block for `result`'s fields with a `- path:` relative to cwd under `.orchestrate/runs/<run_id>/effects/<n>/attempt-1/result.json`, runs the registry template `codex_unrestricted_workspace`'s argv with `${model}`/`${reasoning_effort}` substituted, prompt on stdin, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` set, `timeout_sec`; parses and validates the JSON into `result`; raises `ProviderFailure(code, message)` on nonzero exit, missing or invalid file, or when the run's call count would exceed `MAX_PROVIDER_CALLS`); `dev_check() -> CheckReport` (`python dev_check.py` in cwd with the bundle path set; the same command boundary as `commands.json`); `main(argv)` (reads `inputs.json`, makes `.orchestrate/runs/<run_id>/`, calls `run`, writes `terminal.json` `{"outcome": "completed"|"failed", "value": asdict|None, "failure": {"code","message"}|None, "started_at", "finished_at", "calls"}`, exit 0 on completed, 1 on failed).
  - mutable: `def run(task: str, intent: str, repo: str) -> Outcome` (the parent: one `provider_result(PROVIDERS["coder"], IMPLEMENT_PROMPT.format(...), model="gpt-6.1-sol", effort="high", timeout_sec=5400, result=Change)` then `DONE(summary=change.summary)`), plus any fresh top-level functions a child adds.
- `prepare.collect(records)` for `arm_kind == "generic-command"`: `terminal.json` under `record["state_root"]` (exactly one run directory; refuse "finish the run first" otherwise); `outcome`, `failure`, `calls = len(calls/*)`, `wall_clock_sec = finished_at − started_at`; when completed, `patches = {"final": "collected/final.diff"}` copied from the highest-numbered call's `patch-cand-1.diff` (refuse when missing: "the run is invalid (shim not first on PATH?)"); `selected`/`variant` `None`. The orc path is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# test_orc_structural_search_seeds.py
def test_the_rebound_direct_parent_compiles_with_the_codex_coder():
    # compile three_arm/orc/direct.orc: status accepted; providers.json binds coder to codex_unrestricted_workspace;
    # the only :model literal is "gpt-6.1-sol" and the only :effort "high"
# test_compare_harness.py
def test_collect_reads_a_generic_command_runs_terminal_and_last_patch(world):
    # a command that calls the fake claude twice (two call dirs with patches) and writes terminal.json completed:
    # record outcome completed, calls 2, patches final == calls/2's patch bytes, wall_clock_sec > 0
def test_collect_refuses_a_generic_command_run_without_a_terminal(world)
# test_orc_structural_search_python_workflow.py (scripted codex: writes the Change to the `- path:` file)
def test_the_python_parent_completes_and_writes_a_terminal_with_one_call(world)
def test_a_provider_failure_is_a_failed_terminal_not_an_exception(world)      # scripted codex exits 1 -> failed, code provider_exit_nonzero
def test_the_call_budget_refuses_the_ninth_provider_call(world)              # a run() stub looping 9 calls -> failed, code call_budget_exceeded
def test_pyright_passes_on_the_python_parent()                               # pyright --outputjson: 0 errors
```

- [ ] **Step 2: Run** the four selectors — expected: FAIL / file not found.
- [ ] **Step 3: Implement** the two candidate roots, `collect`'s branch, the registry row (`workflows/README.md`: "Experiment seed (structural search three-arm parent); compile evidence …; the coder is Codex gpt-6.1-sol"), README text.
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_seeds.py tests/experiments/test_compare_harness.py tests/experiments/test_orc_structural_search_python_workflow.py` and `pytest --collect-only -q tests/experiments/test_orc_structural_search_python_workflow.py`; `wc -l experiments/compare/prepare.py` < 500; the orchestrator smoke selector — expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: three-arm parents: the direct seed rebound to a Codex gpt-6.1-sol coder and its matched typed Python workflow; collect reads a generic-command run's terminal and last patch" -- experiments/orc_structural_search/three_arm experiments/compare/prepare.py experiments/compare/README.md workflows/README.md tests/experiments/test_orc_structural_search_seeds.py tests/experiments/test_compare_harness.py tests/experiments/test_orc_structural_search_python_workflow.py`

### Task 3: I3 evaluation through the generic-command arm

**Files:**
- Modify: `experiments/orc_structural_search/evaluation.py` (`evaluate`, `_classify`), `README.md` (I3 evaluation layout)
- Test: `tests/experiments/test_orc_structural_search_evaluation.py`

**Interfaces:**
- `evaluation.is_python(config: ExperimentConfig) -> bool`: the entry module file (`ledger.entry_of`) ends with `.py` (the config's `entry_workflow` is `direct::run` with `source_root "."` and the module file `direct.py`; `providers_file` `providers.json`; `command_boundaries_file` `None`).
- `evaluate(...)`: for a Python candidate, `acceptance.check_python(root, config)` (Task 4) replaces `compile_candidate` as the admission check; `ArmSpec(source=root/direct.py, entry=config.entry_workflow, source_root=root, providers=root/providers.json, inputs=INPUTS, command=(sys.executable, "-P", str(root/"direct.py")))` with no `state_dir` (the command arm's state is `<cwd>/.orchestrate/runs`, as `record.json` names); the record's `state_dir` is that path.
- `_classify(state_dir)`: a `*/terminal.json` under it (generic command) is read like a memo terminal: `completed` → value, `failed` → failed, absent → incident; the memo path is unchanged.
- The I3 parent's live prompt equality test runs offline: evaluate the ORC rebound parent and the Python parent on the fixture task with the scripted `codex`; `calls/1/prompt.txt` of both differ only in the `- path:` line (a line-wise diff whose only changed lines start with `- path:`), and the Python run's argv recorded by the scripted codex equals the registry template's command with `gpt-6.1-sol`/`high`.

- [ ] **Step 1: Write the failing tests**

```python
def test_i3_parent_sends_the_orc_parents_prompt_except_the_result_path(sandboxed, world)
def test_i3_evaluation_runs_the_generic_command_arm_and_records_a_completed_terminal(sandboxed, world)
    # record.outcome completed, value {"kind": "DONE", ...} shape as the ORC Outcome's JSON, provider_calls 1,
    # record.json arm_kind generic-command, prepare.collect(records)["patches"]["final"] exists
def test_i3_provider_failure_is_recorded_as_failed(sandboxed, world)
def test_i3_launch_killed_before_its_terminal_is_an_incident(sandboxed, world)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_evaluation.py -k i3` — expected: FAIL.
- [ ] **Step 3: Implement**; the `Outcome` JSON of `direct.py` must serialize as the ORC union does (`{"kind": "DONE", "summary": ...}`: read the ORC terminal value in the first test and match its shape, not its text).
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_evaluation.py` — expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: I3 candidates evaluate through the harness's generic-command arm; a terminal.json classifies like a memo terminal" -- experiments/orc_structural_search/evaluation.py experiments/orc_structural_search/README.md tests/experiments/test_orc_structural_search_evaluation.py`

### Task 4: I3 acceptance: AST scope validation, pyright, skeleton, allocation, planned maximum, brief

**Files:**
- Modify: `experiments/orc_structural_search/acceptance.py` (`judge_child` I3 branch, `validate_python_scope`, `check_python`), `records.py` (`python_skeleton_hash`, `python_provider_allocation`, `python_program_digest`), `ledger.py` (`planned_calls` for `.py`), `briefs.py` (I3 check line and scope text), `driver.py` (`skeleton`/`allocation` dispatch on suffix)
- Test: `tests/experiments/test_orc_structural_search_validation.py`, `test_orc_structural_search_records.py`, `test_orc_structural_search_ledger.py`, `test_orc_structural_search_briefs.py`, `test_orc_structural_search_driver.py`

**Interfaces:**
- `acceptance.validate_python_scope(parent: Path, child: Path, config: ExperimentConfig) -> Verdict` (reuses `candidates.Verdict`/`_refuse`): parse both mutable files with `ast`; `unreadable_child` on `SyntaxError`; compare top-level nodes by `ast.dump(node, include_attributes=False)`: every parent node that is not a `FunctionDef` named in `mutable_definitions` must appear unchanged (`frozen_surface_changed`, naming the node); a mutable function's `args` and `returns` must be unchanged (`frozen_surface_changed: exported signature of run changed`); a removed mutable function is `scope_exceeded`; added top-level nodes must all be `FunctionDef`s with fresh names (`scope_exceeded` otherwise; a name already bound at top level or by an import is `declaration_collision`); under `topology-only` every `model=`/`effort=` keyword constant in the mutable functions and helpers must already occur in the parent module (`frozen_surface_changed: :model/:effort values`); any file other than the mutable file differing is `scope_exceeded` (`candidates._same_file` byte rule).
- `acceptance.check_python(root: Path, config: ExperimentConfig, *, pyright: str = "pyright") -> CompileOutcome`: `[pyright, "--outputjson", <file>]` with `cwd=root`; `accepted` when `summary.errorCount == 0` with `program_digest = records.python_program_digest(source)` and `build_key = UNAVAILABLE`; else `rejected` with diagnostics `[{"code": "type_check_failed", "rule": d["rule"], "message": ...}]`; a missing pyright is a `RuntimeError` (the live run must not proceed without it).
- `judge_child` I3 branch (when `evaluation.is_python(config)`): `validate_python_scope` → `check_python` → `ledger.unbounded_refusal` → `accepted` with `program_digest`/`build_key`; no slot check, no entry-result check (the signature rule above freezes it). Verdict shape unchanged.
- `records.python_skeleton_hash(source: str, *, definitions: Sequence[str]) -> str`: over the named `FunctionDef`s (plus every top-level function the module defines that the parent lacks is the caller's concern; the hash takes `definitions` only): names bound inside a function (parameters, assignment targets, comprehension and `for` targets, `with ... as`, `except ... as`) and their references become per-function ordinals `$0, $1…` in first-binding order; names bound at module top level (functions, classes, constants) are kept except `PROVIDERS[...]`/provider identifiers, which become `#provider`, and prompt constants (names ending `_PROMPT`) which become `#prompt`; every `Constant` becomes `#lit`; attribute names, call structure, keywords, operators and statement kinds are kept; docstrings dropped; the canonical `ast.dump` text is hashed. Rename and literal changes hash equal; adding a branch, loop or call differs.
- `records.python_provider_allocation(source, *, definitions) -> dict[str, list[str]]`: per named function, the provider keys named in `PROVIDERS["..."]` subscripts in source order.
- `records.python_program_digest(source: str) -> str`: `"sha256:"` over `ast.dump` of the whole module without attributes (comments and formatting excluded; a rename changes it).
- `ledger.planned_calls` for a `.py` entry: the module's `MAX_PROVIDER_CALLS` integer literal assignment (the frozen runtime cap `provider_result` enforces), else `CallCapExceeded`.
- `briefs.episode_brief` for a `.py` mutable file: scope sentence names the mutable functions and "fresh top-level functions"; frozen surfaces "every other top-level definition: imports, dataclasses, prompt constants, the provider adapter and `main`; the signature of `run`"; the check line `pyright direct.py` (no `PYTHONPATH` copy needed: pyright reads the file); no runtime or evidence path.
- `driver.skeleton`/`allocation`: dispatch to the Python variants when the mutable file is `.py`.

- [ ] **Step 1: Write the failing tests** (child files written by the test from `three_arm/python/direct.py`):

```python
# test_orc_structural_search_validation.py
def test_i3_refuses_edits_outside_the_mutable_functions(tmp_path)          # prompt constant edit -> frozen_surface_changed; adapter edit -> frozen_surface_changed; signature change -> frozen_surface_changed; removed run -> scope_exceeded
def test_i3_accepts_a_helper_and_a_rewired_run_with_a_new_skeleton(tmp_path) # check-then-repair child: accepted, skeleton differs, provider_allocation ["coder","coder"]
def test_i3_refuses_a_new_model_literal_under_topology_only(tmp_path)
def test_i3_refuses_a_helper_colliding_with_a_frozen_name(tmp_path)
def test_i3_rejects_a_child_pyright_refuses_with_type_check_failed(tmp_path)   # run returns a str
def test_i3_rejects_an_unreadable_child(tmp_path)
# test_orc_structural_search_records.py
def test_python_skeleton_is_invariant_under_renames_and_literals_and_differs_for_a_branch()
def test_python_program_digest_ignores_comments_and_changes_with_a_rename()
# test_orc_structural_search_ledger.py
def test_a_python_entry_plans_its_frozen_call_cap_and_refuses_without_one()
# test_orc_structural_search_briefs.py
def test_the_i3_brief_names_the_python_check_and_no_runtime_path()
# test_orc_structural_search_driver.py
def test_an_i3_episode_runs_through_run_episode_with_the_codex_mutator_command(sandboxed, world)
    # fake `codex` in fakebin applies a scripted edit to direct.py; agent_cmd is the Codex argv; row interface I3,
    # provider_calls 1, calls/1/patch-cand-1.diff names direct.py, outcome accepted, program_digest startswith sha256:
```

- [ ] **Step 2: Run** the selectors — expected: FAIL.
- [ ] **Step 3: Implement** in the five modules; complexity ≤ 12 per function (split the scope walk into node-kind helpers).
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_{validation,records,ledger,briefs,driver}.py` — expected: PASS; `wc -l` of each module < 500.
- [ ] **Step 5: Commit** `git commit -m "feat: I3 matched Python diff interface: AST scope validation over the mutable functions, pyright admission, Python skeleton hash, provider allocation, planned maximum from the frozen call cap, and the I3 brief" -- experiments/orc_structural_search/{acceptance,records,ledger,briefs,driver}.py tests/experiments/test_orc_structural_search_{validation,records,ledger,briefs,driver}.py`

### Task 5: The three-arm criterion

**Files:**
- Create: `experiments/orc_structural_search/criteria/three_arm.json`
- Test: `tests/experiments/test_orc_structural_search_scoring.py` (one test)

**Interfaces (fields):** `experiment`; `plan` (this file); `tasks` and `base_commits` as Phase 1; `judges: ["claude-opus-5-5", "gpt-6.1-sol"]`; `judge_bindings: {"claude-opus-5-5": "experiments/compare/score.providers.json", "gpt-6.1-sol": "experiments/compare/providers/score_codex.json"}`; `anchors` as Phase 1; `parents: {"orc": "experiments/orc_structural_search/three_arm/orc", "python": ".../three_arm/python"}`; `envelope: {"episodes_per_arm": 6, "interfaces": ["I1","I2","I3"], "condition": "topology-only", "mutator": "<the Codex argv>", "episode_wall_clock_sec": 3600, "evaluation_wall_clock_sec": 14400, "site_selection": "uniform over eligible manifest sites, random.Random(f"{run_seed} {episode_index}")"}`; `type_checker: {"name": "pyright", "version": "1.1.403", "args": ["--outputjson"], "strictness": "pyright default (basic) rules; errorCount must be 0; warnings do not refuse"}`; `collapse_threshold: 0.75`; `locality`: "an episode is out of scope when its verdict is scope_exceeded, frozen_surface_changed, digest_mismatch, site_unlocatable or declaration_collision; locality per arm = out-of-scope episodes over completed episodes (accepted + rejected), and files touched per episode from the final diff"; `subset: {"per_arm": 2, "rule": "accepted, uncontaminated, non-revisit children by episode index; the first; then the first later child with another skeleton; else the child with the smallest sha256(f'{subset_seed}:{candidate_id}') among the rest", "replicates": 1, "tasks": "both"}`; `primary_measure`: Phase 1's text, reported descriptively per arm and per child, "no separation decision; the Phase 1/Phase 2 decision stands"; `budget: {"call_cap": 65, "planned": {"mutators": 18, "evaluations": 36, "judges": 4, "smoke": 2}, "uncharged": "immediate zero-work refusals"}`; `model_policy`; `written_before_scoring: true`; `scoring_join`: "summarize's clone-id join (scoring.join_scores); three_arm readout".

- [ ] **Step 1:** `test_three_arm_criterion_names_the_judges_type_checker_and_subset_rule` (keys present, judges as above, `judge_bindings` files exist, `written_before_scoring` true). Run — FAIL.
- [ ] **Step 2:** Write the file; run — PASS.
- [ ] **Step 3: Commit** `git commit -m "feat: frozen three-arm readout criterion (I3/I1/I2, Codex gpt-6.1-sol mutator and coder, pyright admission, subset rule)" -- experiments/orc_structural_search/criteria/three_arm.json tests/experiments/test_orc_structural_search_scoring.py`

### Task 6: `three_arm.py`: the run, the subset, judging through the ledger and the readout

**Files:**
- Create: `experiments/orc_structural_search/three_arm.py` (≤ 500 lines; command line with `run`, `judge`, `readout`)
- Modify: `experiments/orc_structural_search/README.md` (three-arm recipe, layout), `docs/design/orc_structural_search_driver.md` (status: I3 implemented offline; Mutator Sessions: isolation by masking; Execution Contract: a generic-command evaluation's terminal)
- Test: `tests/experiments/test_orc_structural_search_three_arm.py`

**Interfaces:**
- `three_arm.arm_config(base: Path, interface: str) -> ExperimentConfig`: I1/I2 → `mutable_files ("direct.orc",)`, `mutable_definitions ("run",)`, `entry_workflow "direct::run"`, `providers_file "providers.json"`, `command_boundaries_file "commands.json"`, `source_root "."`; I3 → `mutable_files ("direct.py",)`, `command_boundaries_file None`; `condition "topology-only"`, `episode_wall_clock_sec` and `criterion_sha256` from the run config JSON (`load_config` of a file holding the shared fields; `interface` set per arm).
- `run_three_arm(config_path: Path, *, parents: Mapping[str, Path] ("orc", "python"), tasks, work_root, evidence_root, episodes_per_arm: int, agent_cmd, runtime, env, timeout_sec, solutions, call_cap, concurrency, run_seed: int, subset_seed: int, hide: Sequence[Path] = (), holdouts=(), continue_run=False, guard=None) -> dict`: archives both parents (`driver.archive`), logs one `{"kind": "parents", "orc": cid, "python": cid, "run_seed", "subset_seed", "pyright": <version>}` row; for each arm in `("I1","I2","I3")` runs episodes until `episodes_per_arm` non-quota episodes of that arm exist (`quota.with_retries`; episode index global, `quota.quota_reason` as mode 1; I2 draws `sites.select_site(eligible_sites(site_manifest(parent)), random.Random(f"{run_seed} {index}"))` and passes `run_seed`); every episode row gains `"arm": interface, "mode": "three_arm"`; then `subset(rows, criterion, subset_seed)`; evaluates the chosen children with `driver.launch_units` (`fields: {"mode": "three_arm", "arm", "episode_id", "candidate_id", "parent_candidate_id", "candidate_root"}`, `continued()` from `mode1` on `--continue`), replicate 1, both tasks; writes `E/readout.json` from `compile_readout`. Refuses before any workspace when the planned maximum of the next launch would exceed the cap (`ledger.reserve`, as today).
- `subset(rows: Sequence[Mapping], criterion: Mapping, seed: int) -> dict[str, list[dict]]`: per arm the chosen episode rows under the criterion's rule; a child is eligible when `outcome == "accepted"`, its episode scan has no contaminated verdict (`scoring.contaminated_children`'s reading of `E/episodes/<id>/record.json`; an unadjudicated hit is refused loudly), and its `candidate_id` differs from the parent's and from earlier chosen ones.
- `compile_readout(rows: Sequence[Mapping], criterion: Mapping, evidence_root: Path) -> dict`: per arm: `episodes` outcome counts (`readout.outcome`, quota rows as `quota_incident`), `completed`, `accepted`, `acceptance_rate`, `refused` counts, `locality` (criterion rule; files touched per episode from `E/episodes/<id>.diff` headers), `readout.diversity(accepted)` figures, `exact_repeats` (accepted children sharing a `program_digest` with the parent or an earlier accepted child of the arm), `collapsed` against the criterion threshold or `unavailable`; `subset` (chosen candidate ids per arm); never a pooled figure.
- `judge(evidence_root, pool: Path, task: Path, *, criterion, judges, solution, call_cap, scorer=None) -> dict`: `judging.score_pool(evidence_root, pool, f"three-arm {task.name}", names=..., solution=..., call_cap=..., scorer=scorer or judging.run_judge)` (judge entries reserved in the ledger before any judge runs), then `judging.judge_scan` waits per judge, `summarize.summarize(pool, criterion)`, one `{"kind": "judging", "generation": -2, "task", "pool", "results"}` log row; the pool itself comes from `scoring pool --evidence E3 --task T --out P3/<task> --criterion C --judge ...` (unchanged).
- `readout(log: Path, driver_readout: Path, criterion: Path, results: Sequence[Path]) -> dict`: `scoring.read_pool` per task (criterion hash checked), rows grouped by `arm` (from the log's evaluation rows keyed by `evaluation_id`) and by child: `scoring.policy_stats` per child and per arm (descriptive: mean, valued_mean, failed, timeouts, incidents, hidden_mean, calls_mean, wall_clock_mean), `scoring.anchor_checks` per task (reported, not a gate), the compile-only figures from the driver readout, and `decision: "descriptive; no separation rule applied (Phase 1 decision stands)"`.
- `main(argv)`: `run` (the `driver.main` flags minus `--seeds`/`--episodes`/`--replicates`, plus `--episodes-per-arm`, `--run-seed`, `--subset-seed`, `--hide`, `--criterion`), `judge` (`--evidence --pool --task --criterion --judge … --solution --call-cap`), `readout` (`--log --driver-readout --criterion results…`).

- [ ] **Step 1: Write the failing tests** (scripted `codex` mutator with per-arm edits: I1 edit index as `MUTATOR`, I2 as `MUTATOR_I2`, I3 the Task 4 Python edit; scripted judge as in `test_orc_structural_search_judging.py`):

```python
def test_three_arm_runs_six_episodes_per_arm_against_the_two_parents_and_writes_per_arm_figures(sandboxed, world)
    # readout["arms"] has I1, I2, I3 each with completed 6 (scripted outcomes), no pooled key, I2 rows carry site_id and run_seed
def test_subset_prefers_distinct_skeletons_and_is_reproducible()           # pure function over synthetic rows
def test_a_contaminated_child_is_never_chosen_and_an_unadjudicated_hit_is_refused(tmp_path)
def test_subset_children_are_evaluated_once_per_task_and_logged_with_their_arm(sandboxed, world)
def test_three_arm_cap_refuses_a_launch_and_judges_enter_the_ledger(sandboxed, world)
    # cap just below the first evaluation: CallCapExceeded after the episodes; no W/agents tree, every episode row present;
    # judge(...) with a scripted scorer reserves kind "judge" entries and settles them
def test_three_arm_readout_reports_per_arm_and_per_child_descriptively_without_a_decision(tmp_path)
    # synthetic results.json + log: arms I1/I3 valued, I2 unvalued -> "unavailable", anchors reported, decision text present
def test_i2_site_draw_is_reproducible_for_a_run_seed(sandboxed, world)
def test_continue_resumes_after_a_quota_episode_without_repeating_an_arm(sandboxed, world)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_three_arm.py` — expected: ImportError.
- [ ] **Step 3: Implement** `three_arm.py`; README recipe (commands for run, pool, judge, summarize, readout; `--hide` for the Phase 1 roots); design doc status lines.
- [ ] **Step 4: Run** the module's tests, `pytest --collect-only -q tests/experiments/test_orc_structural_search_three_arm.py`, then `pytest -q -n 16 --dist=worksteal --basetemp=/home/ollie/.cache/pt tests/experiments/`; `python scripts/check_doc_links.py docs/design/orc_structural_search_driver.md experiments/orc_structural_search/README.md` — expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: three-arm compile-only readout driver: I1, I2 and I3 episodes against the rebound direct parents, the stratified subset, judging through the ledger and the per-arm readout" -- experiments/orc_structural_search/three_arm.py experiments/orc_structural_search/README.md docs/design/orc_structural_search_driver.md tests/experiments/test_orc_structural_search_three_arm.py`

### Task 7: Live run (one pass; gated on Tasks 1–6 committed and the full `tests/experiments/` suite green on that commit)

Preconditions recorded in `E3/preconditions.md` before any call: the commit hash; `RT3` is a fresh `git worktree` at it; `sha256sum experiments/orc_structural_search/criteria/three_arm.json` written to `E3/criterion.sha256` and into the run config's `criterion_sha256`; `pyright --version` is 1.1.403; `codex --version`, `claude --version`; the Codex account window reading; solution commits in `/home/ollie/ss-evidence-meta/solutions.txt` (reused, never copied into a package).

- [ ] **Step 1: Smoke** (separate roots `/home/ollie/ss3-{work,evidence}-smoke`, `--call-cap 9` (R12: the Python parent reserves 8; real spend about 2)): one evaluation of the rebound ORC parent on `resume-projection-integrity` through `three_arm run --episodes-per-arm 0 --smoke` (or `driver.evaluate_and_scan` from Python with `mode: "smoke"`), and one of the Python parent; collect, scan, adjudicate; record calls, wall clock, the Codex rollout path and whether the prompt bytes matched the ORC parent's except `- path:`. Stop and report if either fails. `E3/smoke.md`.
- [ ] **Step 2: Main run** in tmux per `launching-workflows`, with the README recipe's main-run command exactly (`--criterion`, the criterion's `envelope.mutator`, `--episodes-per-arm 6`, `--run-seed 1 --subset-seed 1`, `--hide` for every earlier run's existing roots: the Phase 1, incident-1, Phase 1 smoke and three-arm smoke roots and the operator directory) and `--call-cap` = 65 − smoke calls − 4 (controller ruling R15). Quota incidents relaunch under the guard; a slot or evaluation that exhausts its relaunches stops the run: `--continue` after the reset. Read every accepted episode's transcript commands before the subset is judged (the scan misses relative reads); adjudicate every hit.
- [ ] **Step 3: Pool and judge**: per task `scoring pool --evidence $E3 --task … --out $P3/<task> --criterion $RT3/…/criteria/three_arm.json --judge claude-opus-5-5=$RT3/experiments/compare/score.providers.json --judge gpt-6.1-sol=$RT3/experiments/compare/providers/score_codex.json`; then `three_arm judge --evidence $E3 --pool $P3/<task> --task … --criterion … --judge … --judge … --solution … --call-cap` = 65 − smoke calls (R15; judges in the ledger); `summarize` runs inside it.
- [ ] **Step 4: Readout**: `three_arm readout --log $E3/log.jsonl --driver-readout $E3/readout.json --criterion … $P3/*/records/results.json > $E3/three-arm-readout.json`; record sha256 of `log.jsonl`, `calls.json`, `readout.json`, `three-arm-readout.json`, both `results.json`.

### Task 8: Report section and status updates

**Files:** Modify `docs/reports/2026-10-18-orc-structural-search-phase1.md` (new section "Three-Arm Readout" after "Unguided I1: Diversity And Collapse": scope and criterion hash; envelope and the Codex mutator/coder; per-arm compile-only table: episodes, completed, accepted, acceptance rate, refusals by code, locality, distinct skeletons, revisit rate, exact repeats, terminal-only share, collapse verdict; the I2 site draws and which sites carried no type (`slot_type_unavailable`); subset `S` per arm and its descriptive judged values per child and task beside the anchors; calls and wall clock against the cap with uncharged refusals listed; scan verdicts; metering coverage; incidents including any `agent_turn_unresolved`; limitations: six episodes per arm, one mutator model, masking not an allowlist, home readable); update "Limitations" (the three-arm bullet now points to the section; isolation bullet updated) and "Next Step" (items 3 and 5 done); `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (status paragraph and Phase 1 gate: readout met, with the collapse verdict per interface, or recorded with what was measured if an arm fell short of E₀); `docs/index.md` (roadmap and report rows; a row for this plan: "Implementation plan; built offline, run live once ([report section](../reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout))"); `docs/capability_status_matrix.md` row 62 (I3 implemented offline, three-arm readout run); `docs/design/README.md` driver row.

- [ ] **Step 1:** Write from `three-arm-readout.json`, `summarize`'s `results.md` and the log only; `python scripts/check_doc_links.py` on each changed doc.
- [ ] **Step 2: Commit** `git commit -m "docs: three-arm compile-only readout (I3, I1, I2) added to the Phase 1 report; roadmap, index and matrix record the gate" -- docs/reports/2026-10-18-orc-structural-search-phase1.md docs/plans/2026-10-18-orc-structural-search-roadmap.md docs/index.md docs/capability_status_matrix.md docs/design/README.md docs/plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md`

## Flagged For The Coordinator

- Isolation: the "bind only its own episode tree plus what the brief requires" allowlist is infeasible without a second sandbox design (CLIs need home, node, conda, `/usr`, `/etc`, and the task checks need the runtime); the plan masks the named roots instead, which satisfies the stated test. Home stays readable and scan-detected.
- `score_codex.json` needs no change and no new binding file: the judge model is `score.orc`'s `judge_model` input, set by the `--judge gpt-6.1-sol=…` name (E-B3's pattern).
- One extra live smoke evaluation of the Python parent (1 call; planned total 60 ≤ 65) is added for the I3 route's first live exposure; strike it if the budget must stay at the stated 59.
- The I3 Python workflow imports `orchestrator.providers.registry` and `orchestrator.contracts` as a library to reproduce the adapter argv and the delivery contract; this is the only way to make "same adapter, same prompt" a tested property rather than a copied string.

### Critical Files for Implementation
- /home/ollie/Documents/agent-orchestration-search/experiments/orc_structural_search/driver.py
- /home/ollie/Documents/agent-orchestration-search/experiments/orc_structural_search/acceptance.py
- /home/ollie/Documents/agent-orchestration-search/experiments/compare/shim/claude
- /home/ollie/Documents/agent-orchestration-search/experiments/compare/prepare.py
- /home/ollie/Documents/agent-orchestration-search/experiments/orc_structural_search/evaluation.py

## Coordinator Rulings On The Flags (2026-10-19)

- Isolation by masking the named roots (not an allowlist) is accepted; home stays readable and scan-detected, and the report states it.
- No new judge binding: `--judge gpt-6.1-sol=experiments/compare/providers/score_codex.json` (E-B3's pattern).
- The extra live smoke of the Python parent is kept: planned total 60 of the 65-call cap.
- The I3 workflow imports `orchestrator.providers.registry` and `orchestrator.contracts` as a library, so "same adapter, same prompt" is a tested property.
