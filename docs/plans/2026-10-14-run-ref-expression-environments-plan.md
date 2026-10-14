# Run-Ref Confined Child Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` to execute this plan task by task. Use `superpowers:test-driven-development` for behavior changes, `tmux` for long commands, and `superpowers:verification-before-completion` before acceptance claims. The coordinator integrates and verifies; reviewers must differ from authors. Do not start implementation merely because this plan exists.

**Goal:** let authors run a statically named workflow (`:program (:workflow <name>)`) as a `run-ref` child in a runtime-prepared candidate clone, with every child command and provider leaf confined by a Bubblewrap sibling profile, a typed COMPLETED/FAILED outcome at the call site, and durable recovery that never discards committed child effects. Candidate generation, evaluation and selection then compose as ordinary serial typed workflow code.

**Architecture:** the existing `run-ref` effect gains a `:program (:workflow <static-workflow-name>)` locus compiled as a private child entry through `closed/build.py::register_run_ref` and `closed/effects.py::_translate_run_ref`; no `:body`, no extraction helper, and `:bundle` stays retired. The existing rootless Bubblewrap backend (`orchestrator/providers/isolation_backend.py`, `isolation_bubblewrap.py`, cgroup v2 containment slots, result broker) becomes the substrate of a sibling profile `run_ref_confinement.v1` that adds `--unshare-net`, cgroup v2 `memory.max`/`pids.max`/`cpu.max`, a rootfs imported from the digest-pinned `:image` into a sealed content-addressed store, workflow command launches and a workspace quota (tmpfs charged to `memory.max`, or refuse admission). The profile is not registered in `_BACKENDS` (`isolation_backend.py:1568-1580`). Child evaluator, memo and authority stay on the host outside the clone; the coordinator/ledger keeps durable settlement and recovery. Provider traffic reaches upstream only through a host-owned inference gateway bound into the sandbox as a unix socket.

**Tech stack:** existing Python compiler/runtime, Workflow Lisp, pytest, rootless Bubblewrap with cgroup v2, an OCI image import step, and a narrowly scoped inference gateway. No Podman/OCI engine, no new workflow evaluator, search optimizer, package installer or sandbox backend framework.

**Status:** proposed implementation plan, not executed. Drafted 2026-10-14, revised the same day. All unchecked tasks and gates are pending; repository inspection is not runtime qualification.

**Design authority:** [Workflow Lisp Run-Ref Confined Child Environments](../design/workflow_lisp_run_ref_expression_environments.md). That document owns syntax, profile, identity, confinement, artifact transport and recovery contracts. This plan owns sequencing, tests, decisions needed before implementation, and execution evidence. If a gate invalidates a design assumption, revise and review the design before continuing; do not invent a competing contract in code or in this plan.

**Tradeoffs:** a static workflow name forces authors to forward values through declared inputs; digest-pinned images require image publication when dependencies change; the Bubblewrap profile and the gateway restrict the supported host/provider combinations to rootless user namespaces, delegated cgroup v2 and API-key provider accounts. Keeping authority outside the clone requires deliberate guest-path translation and artifact copying. These costs are accepted to make isolation and recovery enforceable.

## Scope and current evidence

Read `AGENTS.md`, `docs/index.md`, `docs/capability_status_matrix.md`, and `docs/design/README.md` first. Governing current contracts are `specs/dsl.md` (run-ref syntax), `specs/state.md`, `specs/security.md`, `specs/providers.md`, `specs/io.md`, `specs/cli.md`, and `specs/versioning.md`; the design proposes their amendment. The evaluated execution (EE) and executor-retirement designs govern compatibility. Existing `trial`/research history does not authorize restoring retired execution.

Inspection established these constraints; none is a completed feasibility experiment:

- `closed/effects.py::_translate_run_ref` admits only `PathProgram`; `run_ref/closed_path.py::_require_closed_effects` rejects effectful children. `prepare_closed_program_bundle` (`closed/artifact.py:190`) compiles a file entry via `FrontendBuildRequest`, so the child-entry seam belongs inside `register_run_ref`/`build.py`, not in a call to that function with an expression.
- `run_ref/runtime.py::_discard_incomplete_attempt` (line 1838) deletes incomplete workspaces. Applying that K4 path after a child committed an effect would lose progress and repeat external work.
- `evaluated/effect_execution.py::_dispatch_command` substitutes host interpreter pins; command launch validates package origins on the host. The confined profile needs image executable pins and translated guest paths, not inherited `shutil.which` results.
- `providers/executor.py:439` copies `os.environ` into every launch; `evaluated/providers.py::launch_provider` (line 215) uses the executor injected through `PreparedAttempt.provider_executor`, while `evaluated/commands.py::launch_command` (line 160) builds `StepExecutor` inline and has no injection point.
- `evaluated_child.py::validate_evaluated_child_terminal` and `_captured_child_authority` (lines 118-126, 22) read child authority from `<workspace>/.orchestrate/runs/<id>` inside the clone, and `_terminal_value` (line 99) assumes a sole terminal memo record with pure re-evaluation.
- `isolation_backend.py` fixes `bubblewrap.v1`; `DurableLaunchReleaseGate` (line 2942) and `CgroupV2ContainmentRoot`/`Slot` (lines 2312, 2551) carry authority assumptions that must be checked before reuse. The open provider-isolation integration Tasks 4-6 (`docs/capability_status_matrix.md:72`) own executor routing and must be coordinated with, not duplicated.
- The maintained best-of-N recipe in `experiments/orc_vs_single_call/README.md` creates clones in shell and passes paths to unrestricted providers. `harness/run_best_of_n_trial.sh` is historical provenance and must remain historical.
- The workspace was already dirty when this plan was drafted. Execution must preserve unrelated work and record its baseline; do not stage broad directories or use cleanup/reset commands against shared changes.

All paths below are repository-relative. Proposed files and selectors are explicitly identified; they do not exist merely because this plan names them.

The child program is an ordinary static workflow: pure expressions, commands, portable tool-enabled providers and static calls, with serial bounded control flow. Nested `run-ref`, parallel effect execution inside the child, dynamic evaluation, trial, human input, sessions/context, resource effects and `provider-bundle-path` are refused at compile time, transitively by effect kind. The substrate adds no exception handling: the `run-ref` site itself yields a compiler-owned union `COMPLETED (result envelope)` / `FAILED (code, detail, accounting)`, while pre-release structural and admission failures still abort under ordinary EE rules.

## File ownership and boundaries

| Responsibility | Existing owners to modify or inspect | Proposed additions |
| --- | --- | --- |
| Syntax, typing, refusals, union result | `orchestrator/workflow_lisp/expressions.py` (`_parse_run_ref_syntax_list`, line 2009), `typecheck_run_ref.py`, `expression_traversal.py`, `wcc/model.py`, `wcc/elaborate.py`, `orchestrator/contracts/closed_program/targets.py` | None |
| Child entry compilation, static config v2, request identity | `orchestrator/workflow_lisp/closed/{build,effects,artifact}.py`, `orchestrator/workflow/run_ref/{config,contracts,wire}.py` (`PathProgram.environment` exists at `config.py:313-341`) | None |
| Clone, image import, admission, authority outside the clone | `orchestrator/workflow/run_ref/{source,workspace,child,evaluated_child,launch_authority,runtime}.py` | `orchestrator/workflow/run_ref/confinement.py`: image import to a sealed rootfs, profile admission, launch through the existing backend |
| Confined leaf execution | `orchestrator/workflow/evaluated/{effect_execution,commands,providers,interpreters,authority}.py`; `orchestrator/providers/{isolation_backend,isolation_bubblewrap,executor}.py` | None beyond `confinement.py` |
| Provider transport | `orchestrator/providers/registry.py` (templates, lines 47-131), `orchestrator/providers/executor.py`, `evaluated/providers.py` | `orchestrator/providers/inference_gateway.py`: host-owned unix-socket relay for model routes only |
| Recovery, export, evidence, settlement | `orchestrator/workflow/run_ref/{runtime,ledger,delta,result_contract,evaluated_child}.py`; `orchestrator/workflow/evaluated/{run_ref,replay,run_header,views}.py` | None; no second ledger |
| Public consumers and author guidance | `orchestrator/cli/commands/{run,resume,report}.py` only where required; specs and routing docs; `experiments/orc_vs_single_call/{README.md,workflows/best_of_n.orc,workflows/best_of_n.providers.json}` | `workflows/examples/run_ref_confined/` after qualification |

Test modules: at most five new ones, `tests/test_workflow_lisp_run_ref_workflow_program.py`, `tests/test_workflow_run_ref_confinement.py`, `tests/test_workflow_run_ref_confined_recovery.py`, `tests/test_provider_inference_gateway.py` and `tests/e2e/test_e2e_run_ref_confined.py`. Export tests extend `tests/test_workflow_run_ref_delta.py`. Real-sandbox and real-provider cases live only under `tests/e2e/` with `@pytest.mark.e2e`, `skip_if_no_e2e()` and `skip_if_no_cli("bwrap")` (`tests/e2e/conftest.py:17,23`); unit modules hold argv, policy and path-translation units only, so `pytest -q -n 16 --dist=worksteal -m 'not e2e'` stays green on hosts without the sandbox. Changes must reach AST traversal, WCC payloads, closed artifact validation, request/wire codecs, runtime consumers, fixtures and docs together. No broad provider-executor or compiler refactor is authorized.

## Gates and evidence ledger

F1-F4 are proved in Task 1; F5 and F6 are the acceptance of Tasks 7 and 8. A fake executor or a successful pure child does not satisfy confinement or provider feasibility. An unavailable prerequisite or skipped live check means **BLOCKED/UNQUALIFIED**, never PASS. Increment A (Task 9) is the first shippable increment and is labelled as such; it is not the complete delivery.

| Gate | Required evidence before proceeding | Current status / evidence |
| --- | --- | --- |
| F1 (child entry closure) | `:program (:workflow name)` compiles through `register_run_ref` into a private child entry with declared inputs, imported/private procedures, owner externs and nested control flow; no parent runtime binding is visible; same identity after snapshot/rebuild | PASS 2026-10-14 (programmatic seam, Ruling P1); pending review |
| F2 (authority separation) | Child header, checked program, memo and request/receipt live outside the clone; guest processes see only the clone, bounded scratch and a result ingress; every leaf launch goes through the profile | PASS 2026-10-14 for separation facts; clone still receives the compile cache, terminal-proof relocation is Task 5; pending review |
| F3 (Bubblewrap sibling profile) | Real rootless launch with `--unshare-net`, enforced cgroup limits, imported sealed rootfs, workflow commands, workspace quota, escape negatives and descendant termination; `DurableLaunchReleaseGate` and containment slot authority assumptions checked | PASS 2026-10-14 with design deltas D-a to D-e (delegated containment root, holder/spawner launch shape, no-follow host reads, quota admission, rootfs mount points); pending review and Design |
| F4 (transport probe) | Provider CLI inside the sandbox reaches a gateway stub over a bound unix socket and the stub reaches upstream; credentials never enter the sandbox | In-sandbox leg PASS 2026-10-14; upstream leg BLOCKED (no API-key account, Ruling P2); pending review |
| F5 (recovery, Task 7) | Kill at each window resumes the same child/attempt without repeating committed effects; zero-commit attempts take the K4 discard path; legacy profile oracle unchanged | Pending / none |
| F6 (typed exports and retained evidence, Task 8) | Exact typed rebase, no-overwrite export, evidence allowance checked at each commit, cleanup with recorded obligation and resume retry, settlement without clone reads | Pending / none |
| A (language/identity) | Syntax, once-only `:commit`, compile-time refusals, union result type, static config v2, request identity and path-mode preservation tests | Pending / none |
| B (runtime/confinement) | Command and provider matrices through the profile, image executable pins, enforced limits, typed exports, recovery, old path-mode preservation | Pending / none |
| C (complete author use case) | Public compile/run/interrupted-resume/completed-resume/report for serial generation, evaluation and typed selection with a real sandbox and a real tool-enabled provider | Pending / none |
| D (release review) | Narrow and broad checks classified, final code plus security review PASS, contract review PASS, documentation accurate, explicit incremental commits | Pending / none |

At execution, append evidence rows to `docs/reports/run-ref-confinement-feasibility/README.md` with task/gate, exact command, exit, tested commit, fixture/image digests, run id and reviewer disposition, and summarize them here. That committed report is the retention location: `artifacts/` is gitignored (`.gitignore:11`) and has no retention policy. Keep secrets out of logs. The design document must not become a task checklist or a run-status log.

## Task 0: Baseline and readiness

**Files:** this plan; `docs/reports/run-ref-confinement-feasibility/README.md`. **Dependency:** none. No spec amendments in this task.

- [x] Record `git status --short`, `git rev-parse HEAD` and the dirty paths without modifying unrelated files. Use an isolated worktree if execution would collide with existing edits (`superpowers:using-git-worktrees`).
- [x] Run the existing narrow baseline: `pytest -q tests/test_workflow_lisp_closed_run_ref_placement.py tests/test_workflow_evaluated_run_ref.py tests/test_workflow_evaluated_run_ref_settlement.py tests/test_workflow_run_ref_config.py`. Record failures before interpreting later regressions.
- [x] Readiness probe, recorded with exact commands and output: `bwrap` present (it is, at `/usr/bin/bwrap`; `podman` is not installed on the reference host), unprivileged user namespaces, cgroup v2 delegation for the current user, a workspace quota mechanism, an image-import tool for a digest-pinned OCI image into a directory tree, and the provider CLI's base-URL/API-key override flags. A missing prerequisite is recorded as BLOCKED for the gate that needs it.
- [x] Reuse the existing path-mode oracles (`tests/e2e/test_e2e_workflow_evaluated_run_ref.py`, `test_closed_path_run_ref_placement_round_trip`) as the compatibility baseline; do not capture new fixtures.
- [x] Commit only the report and plan updates with explicit paths after reviewing `git diff --cached`: `docs: record run-ref confinement baseline and readiness`.

**Done:** baseline and readiness receipts exist in the report with no implementation claim.

Evidence (2026-10-14, commit `0c156966`): baseline 260 passed, path-mode oracles 19 passed; `bwrap` 0.9.0, user and network namespaces, delegated cgroup v2 (`cpu memory pids`), size-limited tmpfs quota and Python registry v2 access are ready; the controller's own cgroup scope cannot enable child controllers (F3 must use a delegated scope); no API-key provider account, so the F4 upstream leg is BLOCKED. See [the feasibility report](../reports/run-ref-confinement-feasibility/README.md).

## Task 1: Feasibility F1-F4 in bounded vertical experiments

**Files:** existing owners in the table; throwaway code under `experiments/run_ref_confinement_spike/`, removed after the gates, as in the evaluated-execution spike precedent (`docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md:69`). Retained tests go to `tests/test_workflow_lisp_run_ref_workflow_program.py`, `tests/test_workflow_run_ref_confinement.py` and `tests/e2e/test_e2e_run_ref_confined.py`.

- [x] F1: compile a `:program (:workflow name)` site whose workflow uses an imported helper, declared inputs, an owner command/provider binding and nested `let*`/branch/`loop`/`recur` through the `register_run_ref` child-entry seam. Check values, effect sites and owner bindings; prove the child cannot resolve a parent runtime binding; prove identity survives snapshot/rebuild.
- [x] F2: place child header, checked program, memo and request/receipt in an external control root; prove a guest process sees only the clone, bounded scratch and the result ingress, and that a result file alone is not authority.
- [x] F3: launch the real rootless profile from a digest-pinned image imported into a sealed content-addressed rootfs. Prove `--unshare-net`, `memory.max`/`pids.max`/`cpu.max`, workflow command execution with image executable pins, the workspace quota (tmpfs charged to `memory.max`, or admission refused), and descendant cleanup. Run escape negatives against parent and sibling clone paths, host home/secrets, `.git` alternates/hooks/config, authority paths, symlink/hardlink swaps and host sockets. Record the authority assumptions of `DurableLaunchReleaseGate` and `CgroupV2ContainmentRoot`/`Slot` and whether they hold for this profile.
- [ ] F4 (partial: in-sandbox leg only; upstream BLOCKED, Ruling P2): run the provider CLI inside the sandbox against a gateway stub over a bound unix socket that forwards to upstream; prove no direct network, no credentials inside, and model routes only.
- [x] Collect retained modules: `pytest --collect-only -q tests/test_workflow_lisp_run_ref_workflow_program.py tests/test_workflow_run_ref_confinement.py tests/e2e/test_e2e_run_ref_confined.py`; run each retained node by id, RED then GREEN; real launches in tmux with explicit timeouts. Deviation: real launches ran in the foreground with explicit `timeout` (each under 10 s), not in tmux.
- [ ] Record F1-F4 in the report with a distinct reviewer. If F3 fails, return to Design with the measurements; do not weaken the task to cwd-only isolation.
- [x] Commit the retained slice with explicit paths: `test: prove run-ref confinement seams`.

**Done:** F1-F4 have reproducible positive and negative evidence. Feasibility code is not release qualification.

Evidence (2026-10-14): F1, F2 and F3 PASS, F4 in-sandbox leg PASS and upstream leg BLOCKED; F3 returns design deltas D-a to D-e to Design before Tasks 5-6. Spike preserved at commit `fdfa8b0d` and removed. See [the feasibility report](../reports/run-ref-confinement-feasibility/README.md#task-1-feasibility-f1-f4-2026-10-14).

## Task 2: Prospective contract amendments

**Files:** `specs/{dsl,state,security,providers,io,cli,versioning}.md`, `specs/acceptance/index.md`, `docs/design/workflow_lisp_evaluated_execution.md`. `specs/dsl.md` owns run-ref syntax; the frontend specification is not touched. **Dependency:** Task 1 results.

- [ ] Allocate the next free public target and artifact/wire versions with the design owner; `2.37` is reserved for parallel map. Keep old checked artifacts, config bytes and path-mode admission unchanged.
- [ ] Write the amendments as future/unimplemented: `:program (:workflow name)` syntax, `:repo` literal and once-only `:commit`, closed policy keys, compile-time refusals, union result type, profile `run_ref_confinement.v1`, static config v2, request identity, authority outside the clone, image import, evidence allowance, typed export, recovery per the design, cleanup retry on completed resume (CLI), export removal with run deletion/invalidation.
- [ ] Write the declared EE amendments: K4 (a confined child with at least one committed effect is never discarded; zero committed effects keeps the discard/fresh path), §8.1 applied unchanged (ordinary rerun for `started`/`failed` attempts without commit unless `must_not_repeat`), §8.4 `resume_request` child-recipe variant with stored-artifact validation instead of fresh-build comparison, X4 `provider-bundle-path` refused at compile time in confined children with child `result_root` recording the external control root, R2/R3 guest spelling `/result/<attempt-relative>`, and the "internal run-ref target remains 2.35" statement.
- [ ] One contract review by a distinct reviewer; record the disposition in the report. Commit reviewed paths only: `docs: specify prospective run-ref confinement contracts`.

**Done:** amendments are written, reviewed and committed as unimplemented; Task 13 finalizes them.

## Task 3: Syntax and typing

**Modify:** `orchestrator/workflow_lisp/expressions.py` (`_parse_run_ref_syntax_list`), `typecheck_run_ref.py`, `expression_traversal.py`, `wcc/model.py`, `wcc/elaborate.py`, `orchestrator/contracts/closed_program/targets.py`. **Tests:** `tests/test_workflow_lisp_run_ref_workflow_program.py`; existing `tests/test_workflow_lisp_run_ref.py`, `tests/test_workflow_lisp_closed_run_ref_placement.py`.

- [ ] Add failing parameterized tests for `:program (:workflow name)` with a static name only, mutual exclusion with path mode, declared inputs, `:repo` literal, `:commit` as a pure String expression evaluated once in the parent, literal digest-pinned `:image`, closed policy keys and resource bounds, and target gating.
- [ ] Add compile-time refusals: `:must-exist false` result descriptors, `:network :none` plus any provider effect, and transitive refusals by effect kind (nested run-ref, parallel effects, dynamic eval, trial, human, session/context, resource, `provider-bundle-path`), including effects reached through an imported helper.
- [ ] Type the site as the union `COMPLETED (result envelope)` / `FAILED (code, detail, accounting)`; the envelope keeps value, workspace_delta and accounting from `run_ref/result_contract.py`.
- [ ] Collect the new module, run it and the existing selectors including `test_closed_path_run_ref_placement_round_trip`; verify old source still yields its previous canonical configuration.
- [ ] Review diff and commit explicit paths: `feat: type confined run-ref workflow programs`.

**Done:** ordinary static workflows are admitted or rejected for their semantic reason, with no child effect omitted from inferred analysis.

## Task 4: Child entry compilation, static config v2 and request identity

**Modify:** `orchestrator/workflow_lisp/closed/{build,effects,artifact}.py`, `orchestrator/workflow/run_ref/{config,contracts,wire}.py`. **Tests:** `tests/test_workflow_lisp_run_ref_workflow_program.py`; existing `tests/test_workflow_lisp_closed_private_run_ref.py`, `tests/test_workflow_run_ref_config.py`, `tests/test_workflow_lisp_closed_program_artifact.py`.

- [ ] Compile the named workflow into a private child entry inside `register_run_ref`/`_translate_run_ref`; store its checked identity in `run_ref_static_config.v2` with profile `run_ref_confinement.v1`, image digest, policy and environment. Preserve old decoders; never relabel an old artifact.
- [ ] Test immutable dependency snapshots: source/import/extern mutation after parent compilation uses the captured program or causes the specified identity refusal; substituted owner config and source bytes are rejected.
- [ ] Bind repo, commit, child entry identity, typed ordered inputs, image, policy and owner configuration to the durable request; test each field's digest effect and tamper rejection before launch.
- [ ] Run new selectors plus `pytest -q tests/test_workflow_lisp_closed_private_run_ref.py tests/test_workflow_run_ref_config.py tests/test_workflow_lisp_closed_program_artifact.py`; record artifact/wire round-trip evidence.
- [ ] Commit explicit paths after review: `feat: compile run-ref workflow programs into checked child entries`.

**Done:** the new locus is a front end for a checked child program with one run-ref effect identity and no alternate evaluator.

## Task 5: Clone, environment and authority outside the clone

**Modify:** `orchestrator/workflow/run_ref/{source,workspace,child,evaluated_child,launch_authority,runtime}.py`. **Create:** `orchestrator/workflow/run_ref/confinement.py` (image import, admission). **Tests:** `tests/test_workflow_run_ref_confinement.py`; existing `tests/test_workflow_run_ref_source.py`, `tests/test_workflow_evaluated_run_ref_caller.py`, `tests/test_workflow_evaluated_run_ref_root.py`. Security brief for the reviewer.

- [ ] Failing tests for one clone per activation/attempt, commit mismatch, overlapping roots, hostile git metadata and authority path aliasing; host fetch runs with a sanitized Git environment; setup component is the literal `none` with `setup_ms` 0.
- [ ] Import the digest-pinned image into the sealed content-addressed rootfs once per digest and refuse admission on digest or prerequisite mismatch.
- [ ] Relocate child authority: `validate_evaluated_child_terminal`/`_captured_child_authority` read `<workspace>/.orchestrate/runs/<id>` inside the clone; the confined profile reads the external control root recorded in the child `result_root`.
- [ ] Protected no-follow host reads for provider `:doc`/dependency, command closure hashing and typed input copying against malicious candidate symlinks and path swaps, bounded in bytes.
- [ ] Replace `_terminal_value`'s sole-terminal witness for the new profile: validate the committed memo, checked result and complete site/effect facts; keep the pure path-profile witness unchanged.
- [ ] Collect the new module, run it narrowly, then the existing source/caller/root tests. Commit explicit paths: `feat: prepare confined run-ref child environments`.

**Done:** a pure child runs and resumes in the new profile with authority inaccessible from the clone. This stage alone does not satisfy delivery.

## Task 6: Confined leaf execution

**Modify:** `orchestrator/workflow/evaluated/effect_execution.py` (`perform_external`, `_dispatch_command`), `commands.py::launch_command`, `providers.py::launch_provider`, `interpreters.py`, `authority.py`, `orchestrator/workflow/run_ref/confinement.py`, `orchestrator/providers/{isolation_backend,isolation_bubblewrap}.py`. **Tests:** `tests/test_workflow_run_ref_confinement.py` (argv/policy/path units); existing `tests/test_workflow_evaluated_commands.py`, `tests/test_workflow_evaluated_command_lifecycle.py`, `tests/test_workflow_evaluated_providers.py`; real launches in `tests/e2e/test_e2e_run_ref_confined.py`. Security brief for the reviewer.

- [ ] Failing units for profile argv (`--unshare-net`, limits, rootfs, workspace, scratch, result ingress), guest path translation, image executable pins replacing host interpreter pins, bounded stdout/stderr, timeout and process-tree termination.
- [ ] Add an executor injection point to `launch_command` and route the confined profile through `PreparedAttempt.provider_executor` for `launch_provider`; the per-attempt env/config overlay replaces the `os.environ` copy for confined launches. Coordinate the routing with the provider-isolation integration Tasks 4-6 rather than duplicating them.
- [ ] Launch through the existing backend with the sibling profile, not through `_BACKENDS`; preserve the host route for runs outside the profile; no host execution fallback.
- [ ] Enforce wall time, memory, CPU, PID, quota and output limits; clamp the provider timeout to the remaining wall budget. Until Task 10, provider effects fail with `run_ref_provider_transport_unavailable`.
- [ ] Run new units and the existing command/provider lifecycle suites, then the real confinement selectors in tmux. A mock argv assertion is not confinement evidence.
- [ ] Commit explicit paths after security review: `feat: confine run-ref leaf effects through the bubblewrap sibling profile`.

**Done:** every admitted child leaf process and descendant is confined; unsupported launch modes fail closed before dispatch.

## Task 7: Recovery (F5)

**Modify:** `orchestrator/workflow/run_ref/runtime.py` (`_discard_incomplete_attempt`, `drive_run_ref_lifecycle`, `recover_run_ref_settlement`), `ledger.py`, `child.py`, `evaluated_child.py`, `orchestrator/workflow/evaluated/run_ref.py`. **Tests:** `tests/test_workflow_run_ref_confined_recovery.py`; existing `tests/test_workflow_run_ref_runtime.py`, `tests/test_run_ref_lifecycle_driver.py`, `tests/test_workflow_evaluated_run_ref_kills.py`, `tests/test_workflow_evaluated_run_ref_settlement.py`, `tests/test_workflow_evaluated_parallel_run_ref.py`.

- [ ] One kill-window test parameterized over: before release, after release, after child command commit, after child provider commit, after child terminal, after export, after parent commit, before settlement. Assert per-site dispatch counters, child run id and workspace identity.
- [ ] K4 amendment: a confined child with at least one committed effect is never discarded; zero committed effects keeps the discard/fresh path. K8 starts from the first committed child effect; `invalidate` is allowed before it.
- [ ] `started`/`failed` attempts without commit rerun under EE §8.1 unless `must_not_repeat`; tool-enabled providers follow the agent-sessions first-turn at-least-once rule with a PQ-1a qualification record. No new outcome code.
- [ ] Keep `tests/test_workflow_run_ref_runtime.py::test_every_pre_parent_crash_discards_exact_workspace_and_reruns_fresh` valid for the legacy profile; do not change that oracle globally.
- [ ] Stop or prove termination of a still-running sandbox before retry; reuse completed child results and reconcile parent settlement without redispatch; keep one writer and the acknowledgement protocol.
- [ ] Collect the new module; run its nodes, then the existing lifecycle/kill/settlement/parallel modules in tmux, including `test_kill_at_parent_settlement_gap_recovers`, `test_public_resume_reconciles_actual_memo_commit_without_child` and `test_parallel_resume_inventory_handles_pending_head_and_historical_pair`.
- [ ] Commit explicit paths after review: `fix: resume confined run-ref children without discarding committed progress`.

**Done:** F5 accepted: committed child effects are never repeated and zero-commit attempts take the ordinary path.

## Task 8: Typed exports, retained evidence, cleanup and settlement (F6)

**Modify:** `orchestrator/workflow/run_ref/runtime.py` (`declared_artifacts_from_value`, `extract_run_ref_value`), `delta.py`, `result_contract.py`, evaluated artifact/view readers, `orchestrator/cli/commands/resume.py` for cleanup retry. **Tests:** `tests/test_workflow_run_ref_delta.py` and `tests/test_workflow_run_ref_confined_recovery.py`; existing `tests/test_workflow_evaluated_artifacts.py`, `tests/test_workflow_evaluated_path_envelopes.py`.

- [ ] Failing tests for nested record/union/list path values, aliases, conflicting descriptors, refined nominal paths, bounded directories, missing files, path escape, symlinks, hardlinks, reserved roots, oversized results and partial export interruption.
- [ ] Copy allowed outputs to `<under>/.run-ref-exports/<parent-run>/<activation>/<attempt>/<relative-to-under>`, rebase descriptor-guided paths, preserve nominal type, revalidate refinements, refuse destination conflicts. Exports are removed with run deletion or invalidation.
- [ ] Separate installation-policy evidence allowance checked at each effect commit; `:output-mib` covers exports only. Over-budget or missing/corrupt evidence blocks settlement and cleanup.
- [ ] Automatic cleanup with a recorded obligation before deletion and completion after; a deletion failure leaves cleanup pending and the next public `resume` retries it without dispatch or child allocation. Substitute roots before retry and assert fail-closed preservation of unrelated files.
- [ ] Prove the parent consumes the typed result and exports after clone removal, including report and completed resume, with terminal proof replayed against retained authority.
- [ ] Run the delta and recovery selectors and the existing artifact/path modules. Commit explicit paths: `feat: export confined run-ref results with typed parent paths`.

**Done:** F6 accepted: value, workspace delta, accounting and export proofs stay bound to one settled result and usable independently of the clone.

## Task 9: Increment A acceptance

**Tests:** `tests/e2e/test_e2e_run_ref_confined.py` (real sandbox, commands only); unit refusal case in `tests/test_workflow_run_ref_confinement.py`. **Dependency:** Tasks 3-8.

- [ ] Public compile/run/interrupted-resume/completed-resume/report of a confined child with commands and `:network :none` through the subprocess recipe below; inspect closed artifact, headers, memos, ledger, exports, result and report.
- [ ] Provider effects refuse with `run_ref_provider_transport_unavailable` before dispatch; assert no sandbox launch for the refused site.
- [ ] Run the module in tmux with `ORCHESTRATE_E2E=1`; commit explicit paths: `test: qualify confined run-ref increment A`.

**Done:** Increment A is honestly labelled as the first shippable increment, qualified for commands only; the best-of-N migration and provider transport remain pending.

## Task 10: Provider transport

**Create:** `orchestrator/providers/inference_gateway.py`. **Modify:** `orchestrator/providers/registry.py` (profile-specific template variants), `executor.py` (env overlay), `evaluated/providers.py`, `run_ref/confinement.py` (socket bind). **Tests:** `tests/test_provider_inference_gateway.py`; real provider case in `tests/e2e/test_e2e_run_ref_confined.py`; existing `tests/test_workflow_evaluated_provider_delivery.py`, `tests/test_workflow_evaluated_provider_lifecycle.py`. Security brief for the reviewer.

- [ ] Failing tests: model routes only, fixed upstream endpoint/model policy, scoped per-attempt token, expiry, body limits, streaming API support, telemetry off, API-key accounts only, unauthorized route denial, credential redaction. The result-file broker is not the gateway.
- [ ] Bind the unix socket into the sandbox; the per-attempt env/config overlay points the provider CLI at it; permanent credentials stay in the host-owned gateway. Unsupported authentication or session transports refuse with `run_ref_provider_transport_unavailable`.
- [ ] Collect the new module, run it, then the provider delivery/lifecycle suites. Run a real tool-enabled provider inside the sandbox in tmux that edits and tests the clone and returns typed data; record image, CLI, model and usage availability.
- [ ] Commit explicit paths after security review: `feat: relay confined provider inference through a host-owned gateway`.

**Done:** a real tool-enabled provider is qualified inside the sandbox with model traffic only.

## Task 11: Complete author use case

**Create:** `workflows/examples/run_ref_confined/{main.orc,commands.json,providers.json,inputs.json,README.md}`, entry `run_ref_confined::main`. **Modify:** `experiments/orc_vs_single_call/{README.md,workflows/best_of_n.orc,workflows/best_of_n.providers.json}`, `tests/workflow_evaluated_consumer_sources.py`, `tests/test_workflow_evaluated_consumers.py`, `workflows/README.md` registry row. Do not modify the historical harness.

- [ ] Example takes a repository locator, exact commit, task and candidate inputs; iterates candidates with a serial `loop`/`recur`; each child generates/edits through a provider binding using the `codex_unrestricted_workspace` template variant and evaluates with commands; the parent handles typed `FAILED` outcomes, selects with ordinary typed code, and returns `INVALID` when all assessments are invalid. Deterministic tie behavior and parent artifact consumption are tested.
- [ ] Use a real digest and documented image provenance; never publish a placeholder digest as runnable. The judge score is same-trust-domain data, not benchmark truth. Migrate the maintained best-of-N recipe to the confined form; retain old fixtures as compatibility evidence; document input/result migration for `best-of-n` and `select-only`.
- [ ] Collect changed modules; run `pytest -q tests/test_workflow_evaluated_consumers.py -k best_of_n` and the route-readiness owner. Commit explicit paths: `feat: compose confined candidate generation evaluation and selection`.

**Done:** users run the complete use case without hand-made clones or shell setup.

## Task 12: Public lifecycle, adversarial qualification and broad verification

**Tests:** the five new modules and existing owner suites. Commands run from the repository root; slow checks in tmux. Do not reuse prior logs after a relevant change.

- [ ] Collect every new or renamed module by explicit path. Real-sandbox and real-provider cases are under `tests/e2e/` with the opt-in helpers; the unit modules contain no sandbox launches.
- [ ] Security oracles must be observable: the tool step writes `readlink /proc/self/ns/{mnt,pid,user,net}`, `/proc/self/cgroup` and a nonce read from a file bound only into that sandbox into the workspace; the host asserts the namespace inodes differ from the controller's, the cgroup matches the recorded slot and the nonce matches. Forbidden-access probes run as deterministic commands in the same sandbox, each writing a positive-control record proving the attempt executed. Gateway logs show model routes only. Limit oracles are cgroup `memory.events`/`pids.events` counters and `EDQUOT`/`ENOSPC` inside the sandbox.
- [ ] In tmux: `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_run_ref_confined.py`, serially (the explicit exception to `-n 16`), then `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_workflow_evaluated_run_ref.py` for old-profile compatibility. Repeat public `resume` after completion: no dispatch, no child allocation, stable value and export proof; exercise interrupted resume on the run that passed earlier gates.
- [ ] Broad campaign in tmux: `pytest -q -n 16 --dist=worksteal -m 'not e2e'`. Classify every failure as introduced, pre-existing with fresh baseline evidence, or unresolved; unresolved related failures block release.
- [ ] Inspect the final diff personally; obtain one final code plus security review from a distinct reviewer; resolve findings through the original implementer and rerun affected checks. Commit explicit paths: `test: qualify confined run-ref public lifecycle`.

**Done:** Gates A-D have evidence, including live provider confinement and the complete public workflow.

### Public subprocess recipe required by the proposed smoke tests

The fixture creates a disposable parent workspace and runs the CLI there, following `tests/test_workflow_evaluated_invalidate.py::_cli`; it supplies absolute `SOURCE`, `SOURCE_ROOT`, `COMMANDS`, `PROVIDERS`, `INPUTS`, `RUNS_ROOT` and `RUN_REF_ROOT`. `SOURCE` is a copied qualified example with the pinned image digest recorded as fixture identity; `INPUTS` points at the test baseline repository and exact commit.

```text
python -m orchestrator compile SOURCE --entry-workflow run_ref_confined::main --source-root SOURCE_ROOT --command-boundaries-file COMMANDS --provider-externs-file PROVIDERS
python -m orchestrator run SOURCE --entry-workflow run_ref_confined::main --source-root SOURCE_ROOT --command-boundaries-file COMMANDS --provider-externs-file PROVIDERS --input-file INPUTS --state-dir RUNS_ROOT --run-ref-root RUN_REF_ROOT
python -m orchestrator resume RUN_ID --state-dir RUNS_ROOT --run-ref-root RUN_REF_ROOT
python -m orchestrator report --run-id RUN_ID --runs-root RUNS_ROOT --format json
```

The fixture obtains `RUN_ID` from the one new run header in its `RUNS_ROOT`. Uppercase names are test-supplied argv values, not CLI flags. The interrupted variant kills after a proved child commit and uses the same `resume`; the completed variant repeats `resume` and `report` and compares dispatch/allocation counts and proofs. The real smoke also proves provider tools ran in the sandbox namespace and that the exported artifact is readable after clone cleanup.

### Proposed acceptance selectors

These node ids are test-writing requirements, not existing evidence. Collect them before use; parameterization may extend each matrix without prompt-wording tests.

| Proposed selector | Required behavioral oracle |
| --- | --- |
| `tests/test_workflow_lisp_run_ref_workflow_program.py::test_workflow_program_compiles_private_child_entry_without_parent_captures` | Private child entry through `register_run_ref`; imports, helpers and owner externs keep ordinary semantics; no parent binding visible |
| `tests/test_workflow_lisp_run_ref_workflow_program.py::test_commit_policy_and_identity_refuse_before_provisioning` | Once-only `:commit`; bad commit/image/policy cannot allocate or launch; request identity tamper rejection |
| `tests/test_workflow_lisp_run_ref_workflow_program.py::test_compile_time_refusals_by_effect_kind` | `:must-exist false`, `:network :none` plus provider, transitive unsupported effects, `provider-bundle-path` |
| `tests/test_workflow_run_ref_confinement.py::test_profile_argv_limits_and_guest_path_translation` | Profile flags, limits, image executable pins and translated paths (unit, no launch) |
| `tests/test_workflow_run_ref_confinement.py::test_child_authority_lives_outside_the_clone` | Control root outside the clone; protected no-follow host reads refuse aliases |
| `tests/test_provider_inference_gateway.py::test_gateway_relays_model_routes_only` | Non-model routes denied; scoped token; credentials host-owned |
| `tests/test_workflow_run_ref_confined_recovery.py::test_kill_window_resume_preserves_committed_effects[<window>]` | Parameterized over the eight windows; stable child id/workspace; per-site dispatch counters; zero-commit attempts take K4 |
| `tests/test_workflow_run_ref_confined_recovery.py::test_public_resume_retries_cleanup_without_dispatch` | Recorded cleanup obligation; root swaps refuse without deleting unrelated files |
| `tests/test_workflow_run_ref_delta.py::test_rebased_typed_exports_survive_clone_cleanup` | Typed path validity, exact content and proofs, later consumption |
| `tests/test_workflow_run_ref_delta.py::test_evidence_allowance_checked_at_each_commit` | Separate allowance; over-budget or missing evidence blocks settlement and cleanup |
| `tests/e2e/test_e2e_run_ref_confined.py::test_increment_a_public_lifecycle_with_commands` | Public lifecycle with `:network :none`; providers refuse with `run_ref_provider_transport_unavailable` |
| `tests/e2e/test_e2e_run_ref_confined.py::test_sandbox_namespace_cgroup_and_nonce_oracles` | Namespace inodes differ, cgroup matches slot, nonce matches |
| `tests/e2e/test_e2e_run_ref_confined.py::test_forbidden_access_probes_write_positive_controls` | Each probe records that it executed and was denied |
| `tests/e2e/test_e2e_run_ref_confined.py::test_limit_oracles_memory_pids_and_quota` | `memory.events`/`pids.events` counters; `EDQUOT`/`ENOSPC` inside the sandbox |
| `tests/e2e/test_e2e_run_ref_confined.py::test_live_tool_provider_candidate_selection_lifecycle` | Real sandbox, gateway and tool-enabled provider; gateway logs show model routes only |

## Task 13: Finalize qualified example, contract status and routing

**Modify:** `specs/{dsl,state,security,providers,io,cli,versioning}.md`, `specs/acceptance/index.md`, `docs/design/workflow_lisp_evaluated_execution.md`, `docs/lisp_workflow_drafting_guide.md`, `docs/{index,capability_status_matrix}.md`, `docs/design/README.md`, `workflows/README.md`, example README and this plan.

- [ ] Audit the Task 2 amendments against the final implementation and Gates A-D; resolve discrepancies through the contract owner; update future/unimplemented status only for the qualified target/profile/provider scope, preserving old admission and recovery rules.
- [ ] Document image preparation and provider readiness once; show public compile/run/resume/report with the exact tested commands; explain declared inputs, typed `FAILED` handling, export locations and cleanup retry in author terms. Update the capability matrix and routes from designed to implemented for the tested scope only; validate local links and run `pytest -q tests/test_workflow_lisp_route_readiness.py`.
- [ ] One contract review by a distinct reviewer who also reads the example as a new author. Stage only task-owned paths, inspect `git diff --cached --check`, then commit: `docs: document qualified run-ref confined child environments`.

**Done:** source, specs, capability status, examples and evidence agree. The final report states checks omitted and remaining limits, especially provider/platform qualification scope.

## Execution and commit discipline

- Execute tasks in dependency order 0 to 13. Read-only scouting and reviews may overlap; avoid concurrent edits to shared compiler/runtime files. Task 1 may expose reusable code but cannot bypass later qualification.
- Delegate bounded implementation/revision to the prescribed implementation role/model; one distinct reviewer per task with a role brief (security brief for Tasks 5, 6 and 10), a contract review at Tasks 2 and 13, and one final code plus security review at Task 12. Route architectural failures back to Design. State role and artifact type for every delegation.
- Each behavior-changing task follows failing behavioral test, observed RED, minimum implementation, observed GREEN, review, explicit-path commit. No literal prompt wording tests. Split oversized tasks at the tested boundary without speculative abstractions.
- Commit only task-owned paths/hunks. Never use `git add .` or `git add -A` in the shared dirty checkout. Commit messages carry no attribution trailers.
- Do not claim implementation completion from this document. Current evidence is owner inspection only.

## Draft review and validation, 2026-10-14

Independent design review and independent implementation-plan review returned PASS after corrections to effectful terminal proof, partial export recovery, protected host reads, cleanup ownership/retry, score trust, prospective contract ordering and retained-evidence budgets. These decisions approve the coherence of the proposal; F1-F6 and Gates A-D remain pending.

The coordinator inspected both documents and the routing changes, checked local Markdown targets and existing referenced selector definitions, and read both illustrative Lisp blocks with the repository's S-expression reader. Both blocks parse as one form; this is not frontend compilation, typechecking or proof of the proposed syntax. Whitespace checks found no errors. Existing content in the three routing documents was preserved apart from the new entries. No runtime implementation, pytest suite, sandbox launch or provider invocation was performed for this drafting task.

## Revision 2026-10-14

Independent design and plan reviews led the coordinator to fix nine decisions that this revision applies: the Bubblewrap sibling profile replaces rootless Podman; `:program (:workflow name)` replaces `:body` and the extraction helper; recovery uses EE §8.1 ordinary rerun and a K4 amendment instead of `run_ref_child_effect_outcome_unknown`; the site returns a typed COMPLETED/FAILED union; `:repo` is a literal and `:commit` a once-evaluated String; a separate evidence allowance replaces charging evidence to `:output-mib`; gateway prerequisites and small compile-time rules are named. Tasks were reordered so contracts follow feasibility (Task 1 before Task 2), F5/F6 moved to Tasks 7 and 8, Increment A is a labelled Task 9, and real-sandbox cases live only under `tests/e2e/`. Dropped: recovery token renewal, mapping run-ref over candidates, Task 0 fixture capture, the dirty-diff digest, the double Task 0 review, the separate gate reviewer and the standalone security reviews. Evidence now lives in a committed report rather than the gitignored `artifacts/` tree.
