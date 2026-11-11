# Engineering feasibility and risk review: Phases 0-4

Task: `review_plan_roadmap_engineering_feasibility` (reviewer, read-only).
Artifact: `docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md` at `87c9325c`.
Date: 2026-11-11. Environment: `/home/ollie/miniconda3/bin/python` 3.13.9, machine load average about 23, so wall times are noisy.

Evidence tags: **[RUN]** verified by running something in this session; **[READ]** verified by reading code or docs; **[INFERRED]** my estimate or deduction.
Probes are under `/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/roadmap-review/eng-probe/` (`p1/` Phase 1, `p3/` Phase 3) and the scan scripts under `/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/roadmap-review/scripts/`. No repository file was changed, no provider was called, no broad suite was run.

## Verdict

Phases 0 and 1 are real and small, but part of their stated work is already done and two of their exit tests are already true or not measurable. Phase 2 is under-sized by a factor of three to four: the deletion candidates are dead as executors but live as vocabulary (28-30 production importers, the dashboard, `report`, compiler signatures), 30k lines needs essentially every candidate removed in full, and "one admitted target" is a migration between two procedure-semantics regimes over about 390 `.orc` fixtures, whose own stop rule contradicts its exit test. Phase 3 is not feasible as stated without weakening guarantees: `depends_on` records value flow only, the accepted design already tried dependency-following invalidation and replaced it with the journal suffix because it mixed old and new results, and the stop rule's fallback ships exactly that half. A narrower Phase 3 is feasible and passes the stated exit test: accept an edited program, reuse the longest journal prefix whose identities and inputs still match, and cancel the suffix. Its value on the Python surface depends on stable binder names, which the roadmap schedules later, in Phase 4. Phase 4's parallel-map remainder is well defined (17 open items); its Python exit test is not defined and needs a design change the Python design currently excludes. My estimate for Phases 0-4 is 21-31 engineer-weeks with the narrow Phase 3, against a roadmap that reads as roughly a third of that.

Findings: 2 blockers, 7 major, 9 minor.

## Findings, most severe first

### B1 (blocker, Phase 3): dependency-based invalidation is unsound for workspace-coupled effects, and the stop rule falls back to it

Evidence:
- `depends_on` is the union of dependencies carried by an effect's operand values: `effect_dependencies` in `orchestrator/workflow/evaluated/effect_inputs.py:372-374`. **[READ]**
- The accepted design states its limits. `docs/design/workflow_lisp_evaluated_execution.md:1745` (C9): `depends_on` covers results read "through names, arguments, results, loop state, join parameters, `case` bindings and the conditions that chose a value; an effect inside a branch does not depend on the branch's condition", and "Evidence that one effect consumed another's output rests on C6 read digests, not on `depends_on` alone". Line 1059 (C5) puts "workspace files no boundary declares" outside the promise. **[READ]**
- The same design records why the journal suffix was chosen: "The spike followed values only and reran one of two file-dependent effects, mixing old and new results (gate report, §6); C8 is the last review's rule" (lines 1773-1776). So the roadmap's finding row "invalidation cancels the whole journal suffix although per-commit dependencies are recorded" describes a deliberate soundness decision, not an oversight. **[READ]**
- What a commit records: commands record digests of resolved argv, contract, closure and implementation files, plus optional document, input contract and launch cwd (`effect_inputs.py:559-573`, `:276`, `:417`); providers record declaration, values, policy, params, composed prompt, dependency rows, prompt source and declared dependency-file digests (`orchestrator/workflow/evaluated/providers.py:202-224`). Nothing records the workspace files an agent or command read or wrote. **[READ]**
- The pipelines the roadmap targets are agents editing a shared repository; a reviewer step that reads what an implementer step wrote has that dependency through the workspace, not through a value. **[INFERRED]**
- The audit's own probe shows the adjacent trap: `invalidate` does not restore workspace state, so a non-idempotent command ran twice on the same file and gave a wrong result (audit `authoring.md` §5b). Edit-and-continue makes that a routine operation. **[READ, audit claim not re-run]**
- Also, a committed coordinator (`run_ref`, `agent_turn`, `provider_phased`) can never be invalidated (`orchestrator/workflow/evaluated/memo.py:169-170`, `memo_reducer.py:425-430`), so any edit upstream of a committed agent turn or phased provider call must refuse. **[READ]**

Proposed change to the roadmap text:
- Replace the Phase 3 target with: "An edited program reuses the longest journal prefix of committed effects whose identity, input digest and `depends_on` still match, in journal order; the first changed, missing or unreached commit and every later commit are cancelled with the existing C8 range. Reuse out of journal order is out of scope until effects declare what they read and write."
- Replace the stop rule with: "If prefix reuse cannot be made sound, keep `resume_program_changed` and ship only a better message naming the first changed effect. Dependency-based invalidation is not a fallback."
- Add a scope line: "An edit whose suffix contains a committed coordinator effect refuses, as `invalidate` does today."

### B2 (blocker, Phase 2): "one admitted target" is a semantic migration, and its stop rule contradicts its exit test

Evidence:
- Admitted targets are 2.35-2.40 (`orchestrator/contracts/closed_program/targets.py:9-11`). Three gates are monotone capability gates (parallel map from 2.37, confined run-ref and agents from 2.38). The fourth is a regime split: `target_dsl_supports_effect_ceilings` at 2.39 (`targets.py:52-54`). **[READ]**
- Call-site count outside the definitions: 39 for `target_dsl_supports_effect_ceilings`, 20 for `target_dsl_supports_local_hook_inference`, 10 for `uses_evaluated_execution`, 9 agents, 8 parallel map, 4 confined run-ref. 59 of 90 gate real semantic differences in `procedure_typecheck.py` (15), `compiler.py` (11) and `procedure_specialization.py` (9). **[RUN: grep count]**
- The simplification record says 2.39 definitions "lose authored lowering strategy and use inference-default procedure contracts, while admitted 2.35-2.38 definition origins retain their existing semantics" (`docs/plans/2026-10-15-orc-simplification-roadmap-extension.md:19-21`) and, for the previous stdlib retarget, "Do not assume changing six headers is sufficient" (line 970). **[READ]**
- Census of 686 tracked `.orc` files: 388 at 2.35, 2 at 2.36, 1 at 2.38, 21 at 2.39, 2 at 2.40, and 261 on retired targets (164 at 2.14). Of the 391 files at 2.35-2.38, 130 use `:effects`, 113 use `:lowering`, 130 use `defproc`; five stdlib modules use both. The packaged stdlib is at 2.35 (6 modules) plus one at 2.40. Test `.py` files hold about 1,291 `"2.35"` literals in 206 files. **[RUN: scan]**
- Two `std/improve` modules with different signatures are selected by target (`stdlib_modules/std/improve.orc` at 2.35, `stdlib_modules/w3/std/improve.orc`). **[READ]**
- The exit test demands "one admitted target"; the stop rule says "a workflow that cannot move to the single target without a behavior change keeps its target". If the stop rule fires once, the exit test cannot pass. **[READ]**
- After the cut, Phases 3 and 4 make identity-affecting changes (binder naming, Python `Agent`). Under today's versioning practice each would add a target, so "one admitted target" would not hold for long. **[INFERRED]**

Proposed change to the roadmap text:
- Split the item into three stages with separate exit tests: (a) collapse the monotone capability gates into one table, no semantic change; (b) migrate the packaged stdlib and the catalog examples to the newest target and unify `std/improve`, with a behavior comparison; (c) remove the 2.35-2.38 procedure regime and migrate or delete the fixtures that exist only for it.
- Change the exit test to "one admitted target for new source; any retained older target is listed with its reason and its removal condition".
- Add a versioning rule for after the cut: whether an identity-affecting change adds a target or breaks retained runs.

### M1 (major, Phase 3): effect identities do not survive unrelated edits on the Python surface, and only partly in `.orc`

Evidence:
- Identity is the activation path (entry plus call frames) joined with the checked site string, with loop ordinals substituted for `[*]`: `orchestrator/workflow/evaluated/machine.py:33-62`, `:360-361`, `:437-455`. **[READ]**
- Python frontend names are positional: `_NameAllocator.next` returns `_{prefix}{index}` (`orchestrator/py/trace.py:139-150`), and every effect is bound through `Trace.bind` (`trace.py:270-279`). Probe `p3/pa` versus `p3/pb`: inserting one command at the top of a three-command workflow renamed every later binder (`_e0,_e1,_e2` became `_e1,_e2,_e3`), so every later identity changed. **[RUN]**
- `.orc`: authored `let*` names are stable. Probe `p3/a` versus `p3/b`: adding a named binding `pre` left the sites `x`, `#1`, `#2` and `z / body / loop:s[*] / else / #1` unchanged. Unnamed effects get a per-scope counter (`orchestrator/contracts/closed_program/sites.py:39`, `check.py:1539`); probe `p3/c`: inserting one unnamed effect before another shifted `#1,#2` to `#1,#2,#3`, so an old identity now names a different effect. A repeated binder name gets `name#2` (`sites.py:42`). Wrapping an effect in a new `let`, `if` or loop changes its path. **[RUN, READ]**
- For providers the `declaration` input part is the digest of the whole perform node minus provenance (`providers.py:203`, `strip_provenance` in `contracts/closed_program/program.py:97`), and that node contains `site` and operand references by binder name. A rename therefore changes the input digest even if identities were matched some other way. **[READ]**
- Few tests pin positional names: 7 test files mention `#N` sites and 5 mention `_e0`/`_loop0`. **[RUN: grep count]**

Proposed change: move "readable generated names" for Python out of Phase 4 and make it an entry condition of Phase 3. State it as "binder names derive from the author's variable or an explicit label, never from a counter", and give unnamed `.orc` effects the same rule or a lint that asks for a name. Note that recovering a Python variable name from a traced expression needs a design choice (frame inspection, source parsing or an explicit `name=`); it is not a rename.

### M2 (major, Phase 3): what replay must change is larger than the spike questions imply, and the exit test does not exercise the headline claim

Evidence, all **[READ]**:
- Resume refuses before reading the memo: `orchestrator/cli/commands/evaluated.py:188-191` compares the fresh program digest with `header["program_digest"]`. The run root also holds a copy of `closed_program.json`.
- The memo reducer resolves every journal row's identity, including old `started`, `failed` and invalidated rows, against the current program's site table and raises `memo_inconsistent` otherwise (`memo_reducer.py:217-225`). A removed or renamed effect therefore makes the journal unreadable under the edited program, before replay starts. `committed` rows carry `effect_class`; `started` rows do not.
- Replay requires journal order (`replay.py:111-122`), equality of `depends_on` with the reached operands (`:81-83`), and that every active commit and every pending start is reached (`:172-176`).
- A committed effect whose input digest differs stops with `effect_input_diverged` (`effect_inputs.py:490-500`; design §8.1 table row 2). The roadmap names §8.4 only; §8.1, §8.5 (C7, C8), the memo record schema, `specs/state.md` and `specs/cli.md` change too.
- The invalidation record is one range anchor, `{"record": "invalidated", "from_commit": offset}` (`memo.py:176`, `memo_reducer.py:412-423`). Invalidation by dependency needs a new record kind and new crash windows.
- The exit test (edit step three's prompt in a four-step run, re-run three and four only) is satisfied by prefix reuse plus the existing suffix range. It does not show "invalidation follows recorded dependencies, not journal order". A test of that claim would edit step two where step three does not read step two's result.
- The stop rule's invariant "a committed effect never re-runs" is contradicted by the exit test itself, where committed step three re-runs.

On the spike: the three reading questions took this review part of a day, so one week is credible for a decision memo plus a prototype of prefix reuse on a four-step fixture. It is not credible for a design of out-of-order reuse. **[INFERRED]**

Proposed change: list the five things the design revision must define (header rebase record and retained old programs; reducing old rows against the program that wrote them; automatic C8 at the first divergence, behind an explicit flag that prints what will re-run; refusal on committed coordinators and `must_not_repeat`; crash windows between rebase and invalidation). Add a second exit test for whichever reuse rule is selected, and reword the invariant as "a committed effect is reused only with identical recorded inputs, and re-runs only after a recorded invalidation".

### M3 (major, Phase 2): the deletion candidates are dead as executors but live as vocabulary; 30k lines has almost no margin

Evidence:
- Static import graph over `orchestrator/` and `tests/` (script `deps.py`, 1,178 modules). **[RUN]**

| Candidate | Lines | Production importers outside the set | Test modules importing |
| --- | ---: | ---: | ---: |
| IR stack, 12 modules (surface_ast, core_ast, semantic_ir, executable_ir, runtime_plan, state_projection, loaded_bundle, persisted_surface, elaboration, statements, linting, judgment_views) | 12,835 | 28 | 36 (26,874 lines) |
| `workflow/trial` | 8,343 | 6 (all inside the IR stack) | 8 |
| `workflow/adjudication` | 2,818 | 2 (inside trial) | 5 |
| `workflow/provider_peer_group` | 5,704 | 2 (`cli/commands/peer.py`, `executable_ir`) | 6 |
| `workflow/provider_supervision` | 3,076 | 2 (`executable_ir`, peer bindings) | 5 |
| `StateManager` methods with no production caller | 1,138 (54 of 58 methods) | 0 | 29 modules import `orchestrator.state` |
| Frontend trial type checking (`typecheck_trial.py`, `trial_result_contract.py`) | 814, plus 247 mentions in `expressions.py` | | |

- Gross total is about 34-35k lines, so the 30k exit test needs every candidate removed in full. **[INFERRED from the table]**
- Live names imported from the IR stack: `RunRefStepConfig` and `StepCommonConfig` (`workflow/evaluated/run_ref.py`, `run_ref/runtime.py`, `run_ref/child.py`, `run_ref/path_compile.py`), `ManagedJobsConfig` (`managed_jobs/runtime.py`), `ExecutableContract` (`workflow/signatures.py`, imported by `cli/commands/evaluated.py`), `SurfaceContract` (`workflow_lisp/contracts.py`), `SurfaceStepKind` (`typed_prompt_inputs.py`), `SurfaceStep` (`build_manifest_io.py`), `PrivateExecContextBinding` (`phase_family_boundary.py`), `WorkflowProvenance` (`runtime_observability.py`), the boundary projection helpers (`workflow_lisp/compiler.py`, `workflows.py`, `closed/frontend.py:34,121`), and the `statements` tokens used by `workflow/identity.py`, which `provider_attempts.py` imports. **[RUN: import scan]**
- `LoadedWorkflowBundle` is never constructed in `orchestrator/` (only in 5 test files, 19 times in `tests/fixtures/historical_observability_bundles.py`), but `compiler.py` references it about 25 times through `imported_workflow_bundles` parameters and helpers (lines 404-421, 589, 700, 1209, 1467-1594, 3380-3434, 3586, 3787), and the LSP passes `imported_workflow_bundles_path` (`lsp/state.py:23`, `lsp/compile_driver.py:827,872`). **[RUN, READ]**
- `dashboard/server.py` (3,891 lines) has no reference to evaluated runs at all; its structure views take `LoadedWorkflowBundle | PersistedWorkflowSurfaceGraph` (lines 1811, 2025, 2178-2267). `observability/report.py:322-324` requires a bundle for `build_status_snapshot`, which `dashboard/projection.py:105` calls. `cli/commands/report.py:251` calls `project_judgment_views` for non-evaluated runs. The roadmap does not say whether the dashboard is ported, cut down or deleted. **[READ]**
- Removing peer groups removes an accepted source form (`with-live-provider-peers`, about 150 mentions in the frontend, 3 test `.orc` files); removing trial type checking turns 5 tracked `.orc` files with trial forms into parse errors. These are language-surface changes with spec edits, not dead-code removal. **[RUN: grep count]**
- The audit's claims that peer groups and supervision are unreachable from `evaluated/` and the closed checker, and that the CLI refuses trials, hold (`cli/commands/trial.py:7-9`; no `peer` or `supervis` identifier in `workflow/evaluated/` or `contracts/`). **[RUN, READ]**
- Module-level reachability from the CLI, Python frontend, LSP, dashboard, demo and monitor leaves 73 modules and 29,786 lines unreachable, but that set includes subprocess entry points such as `isolation_bubblewrap`, `isolation_bundle_broker`, `run_ref/child` and the adapter scripts, so it is not a safe delete list. **[RUN]**

Proposed change: order the deletion as (1) trial, adjudication, peer groups and supervision with their CLI commands, forms and tests, about 20k lines with two production importers to cut; (2) `StateManager` dead methods and CLI vestiges; (3) the IR stack, after moving the dozen live types to a small module and after an explicit owner decision on the dashboard and on `report` for pre-evaluated runs. Change the exit test from a line count to "the named packages are gone and no module in `orchestrator/` imports them", with the line count reported, not required.

### M4 (major, Phases 0 and 2): "one number" is not a usable baseline for a deletion of this size

Evidence:
- Latest recorded full run: 15,874 passed, 71 failed, 114 skipped, 2 xfailed in 790 s over 16,061 nodes; the earlier snapshot had 70 failures, 69 shared, one fixed and two new between the two runs (`docs/plans/2026-10-15-orc-simplification-roadmap-extension.md:1136-1137`, `:1189`, `:1204-1205`). **[READ]**
- The owner's memory notes record that failures in `prompt_resume_child`, `provider_isolation` and `watchdog` depend on launch context (long `--basetemp`, a fresh tmux session), and that a full suite needs about 15 GB of basetemp; both filesystems have about 40 GB free. **[READ; `df` RUN]**
- A count hides swaps: deleting 60 test modules removes known failures while a new failure elsewhere leaves the number equal or lower. **[INFERRED]**
- 72 test modules read `docs/*.md` files and 38 reference `docs/plans/`; 6 read the route readiness registry. Phase 0's closure notes and Phase 2's guide cut will touch files that tests read. **[RUN: grep count]**

Proposed change: make the Phase 0 deliverable "the list of failing node IDs from one fixed launch recipe (command, basetemp, session), each with a mechanism and an owner", and make the Phase 2 gate "no node outside that list fails, and every removed test is listed with the code it covered". Add to Phase 0: "run the doc-reading tests after the disposition edits".

### M5 (major, Phases 3 and 4, ordering): Phase 3 rewrites the replay rules that Phase 4 still has to qualify

Evidence, all **[READ]**:
- Parallel map already changed replay's order relation inside a parallel region (`replay.py:111-158`), and the Phase 5 execution plan says the global journal-order requirement "is incompatible with valid interleaved item commits. Change only the parallel region's order relation" (`docs/plans/2026-10-07-evaluated-execution-phase-5-plan.md:100`).
- That plan's open task at line 249 reads: "Public `invalidate` keeps its whole-offset-suffix behavior with interleaved commits ... do not replace C8 with per-item invalidation." Phase 3 as written does replace it.
- 17 items are open in that plan: two for item working directories (Task 3), five for public kill and resume (Task 5), five for the best-of-N consumer including one live smoke (Task 6), five for review and closeout (Task 7). Lines 223-268.
- The roadmap says "Phase 3's spike can start during Phase 2" and "Phase 4 depends on Phase 1", with no relation between 3 and 4.

Proposed change: run the Phase 3 spike in parallel with Phase 1 (it is reading plus a prototype, and its answer decides the naming rule that the target migration should carry once). Finish the parallel-map kill and resume qualification (Phase 4's first item) before any Phase 3 implementation, so those tests are the regression baseline for the new replay rule. Require the Phase 3 design to cover interleaved parallel commits and item working-directory dependencies.

### M6 (major, Phase 4): the Python exit test is undefined and needs a design change

Evidence:
- No comparator for "same checked program shape" exists in `tests/test_workflow_python_*.py`. Program digests cannot be equal: Python binders are `_eN` and modules are `py/<name>`. The one existing twin (`durable_host_input/approval.orc` and `approval.py`) gave different provider identities in the audit's run. **[RUN: grep; audit claim READ]**
- The Python design excludes what the catalog needs: "runtime Python callbacks or arbitrary generic Python functions do not become ProcRefs" (`docs/design/python_workflow_frontend.md:422-425`); "`parallel_map` is deferred ... `Agent` is deferred because session lifetime, capability and recovery need their own faithful API" (`:634-637`). The catalog includes `std/improve` (ProcRef, `let-proc`, generic unions), best-of-N (map), the agents example and the search controller (`workflows/README.md:53-61`). **[READ]**
- Size of comparable past additions: the whole Python frontend landed on 2026-10-22 in commits of 350-900 lines; `ask` cost about 100 lines (`git log -- orchestrator/py`). **[RUN]**
- The Agent item is conditional on PQ-1c, which has not run. **[READ: delivery plan line 674]**

Estimates **[INFERRED]**: `parallel_map` 3-5 days; `Agent` 3-5 days after the PQ-1c decision; procedure references 1-2 weeks including the design revision; readable names 1 week; twins and a comparator 1-1.5 weeks.

Proposed change: define the exit test as "for each catalog example kept after PQ-1c, a Python version exists and a checked comparator finds the same number, class and order of effect sites, the same result type and the same input contract; examples that need a feature the Python design excludes are listed with the reason". Add "revise the Python frontend design for procedure references" as explicit work.

### M7 (major, Phase 1): two items are hidden projects and one is two-thirds done

Evidence:
- Let-binding: only the bare `(continue <effect>)` form still crashes. Probe `p1/grow.orc` reproduces `[compiler_defect] ... unsupported WCC elaboration node: CommandResultExpr` (raised at `wcc/elaborate.py:4072`). Probes `p1/m1.orc` (effect as `match` scrutinee) and `p1/m2.orc` (effect in a `loop-state :like` field) compile, exit 0. `_bind_effectful_loop_state_fields` (`wcc/elaborate.py:2088-2137`) and the `done` branch (`:1885-1935`) already let-bind; they landed in `91e4a538` "fix: bind effectful loop-state fields and match subject prefixes in the elaborator at 2.33". The remaining fix is about 20 lines in that helper for a state expression that is itself an effect. The comment at `stdlib_modules/std/improve.orc:7-9` is stale for direct effects. **[RUN, READ]**
- `:on-exhausted`: a loop without it compiles today (probe `p1/m3.orc`, exit 0). Forms that omit it: none under `workflows/`; 26 forms in 26 test `.orc` fixtures; 31 forms in 16 test `.py` modules; 17 forms in 12 docs; 27 forms in 3 frozen hidden-test files under `experiments/compare/tasks/`. The parse site is `workflow_lisp/expressions.py:4455-4516`. The roadmap does not say whether the rule applies to every admitted target or only the newest. **[RUN: scan]**
- More than one diagnostic per compile is in the findings table ("one error per compile") but not in the Phase 1 work list; Dispositions says "if cheap". It is not cheap: 960 raise sites against 73 accumulation sites in `workflow_lisp/`, the pipeline stops at the first blocking pass (`workflow_lisp/validation.py:80-94`), and the audit's own example spans two passes (`command_adapter_missing_contract`, then `name_unknown`). **[RUN: grep count; READ]**
- W0: its design's acceptance includes corpus cleanup, "Lines of type declarations fall by at least 200" (`docs/design/workflow_lisp_write_once.md:540`). **[READ]**

Estimates **[INFERRED]**: `continue` fix half a day; `:on-exhausted` 2-4 days; W0 3-5 days; per-definition diagnostic accumulation 1-2 weeks and still short of the audit's example.

Proposed change: reword the first item to "let-bind an effect given directly to `continue`; remove the stale stdlib comment". State the target scope of the `:on-exhausted` rule and that about 57 test forms and 17 doc snippets migrate. Move multi-diagnostic accumulation out of Phase 1 by name. Say whether W0 here means the lint only or the lint plus its corpus acceptance.

### m1 (minor, Phase 0): what created the stray directories is already gone, and the exit test is already true

- 290 `tmp*` and 130 `orc-observe-*` directories exist in the repo root. All 130 `orc-observe-*` are dated 2026-07-26; the `tmp*` ones are dated 2026-06-18 to 2026-07-29 (216 on 07-29). None is newer. **[RUN: `ls -ld`]**
- `orc-observe-*` comes from `tempfile.mkdtemp(prefix="orc-observe-", dir=_SOCKET_TEMP_ROOT)` at `orchestrator/providers/observation.py:406-411`; `_SOCKET_TEMP_ROOT = "/tmp"` since `03508127` (2026-07-27). **[READ, RUN: `git log -S`]**
- The non-empty `tmp*` samples hold `workspace/retry_workflow.yaml` and a schema-2.1 `state.json`, which are YAML-era test workspaces; no current test mentions that file name. 28 test files still call `tempfile.mkdtemp` or `TemporaryDirectory` at 127 sites without `tmp_path`. Python falls back to the current directory when `TMPDIR` points there or no temp directory is writable, which is the likely mechanism on those dates. **[RUN; mechanism INFERRED]**
- `git status --short` shows no `tmp*` or `orc-observe-*` entry today (empty directories are invisible to git; 42 are ignored through their contents). The exit test "`git status` shows no stray temp directories" passes before any work. **[RUN]**

Proposed change: "delete the 420 directories; exit test: `ls -d tmp?* orc-observe-*` is empty after one full suite run; convert the 28 test files to `tmp_path` only if that test fails".

### m2 (minor, Phase 1): the 0.5 s `--help` target is reachable with a four-file edit, but it measures the wrong command

- `python -m orchestrator --help`: 1.75-1.87 s wall. `-X importtime`: 1.43 s cumulative for `orchestrator.cli.main`, of which 1.19 s is the self time of `rfc3987_syntax.syntax_helpers`, loaded by `jsonschema._format` through `orchestrator.providers.isolation`. **[RUN]**
- With `rfc3987_syntax` blocked: 0.24-0.31 s. With `jsonschema` stubbed: 0.13-0.15 s. **[RUN]**
- `jsonschema` is imported at module level in four files only (`providers/isolation.py:16-17`, `isolation_bundle_broker.py:14`, `isolation_environment.py:33`, `isolation_network_preflight.py:28`) and used at five call sites, all inside functions. **[RUN: grep]**
- `compile` of a one-command workflow: 2.71 s normally, 1.12 s with the slow import blocked. **[RUN]**
- `rfc3987_syntax` is an optional format extra of `jsonschema`; `pyproject.toml` requires plain `jsonschema>=4.0`, so a clean install may not pay this cost at all. **[READ; clean-install behavior INFERRED]**

Proposed change: exit test "`--help` under 0.5 s and `compile` of the tutorial workflow under 1.5 s, measured in the documented environment".

### m3 (minor, Phase 1): CLI output is small but changes a spec

`run` returns `(exit_code, run_id, run_root, outputs)` and prints nothing (`cli/commands/evaluated.py:277-285`). Stdout already carries streamed provider output and the `input` JSON line (`specs/cli.md:370-376`). Printing a result line and the failing effect with its stderr tail is 1-2 days including the `specs/cli.md` change and tests that expect quiet output. **[READ; estimate INFERRED]**

### m4 (minor, Phase 1): multi-line prompt literal

The reader rejects a raw newline in a string (`workflow_lisp/reader.py:345-346`). Accepting one, or adding a block literal, is a one-site reader change plus the language spec, LSP and editor grammar; a prompt externs file route already exists (`--prompt-externs-file`). 1-2 days. **[READ; estimate INFERRED]**

### m5 (minor, Phase 1): "a new author finishes the tutorial without opening another document" has no measurement

Proposed change: "a fresh agent session given only the tutorial file and the CLI completes compile, run, fail and resume; the transcript is kept". **[INFERRED]**

### m6 (minor, Phase 2): `StateManager` deletion is confirmed and low risk

54 of 58 `StateManager` methods (1,138 lines) have no caller in `orchestrator/` outside `state.py`; each has at most three test files calling it. Live use is `load`, `close`, `_state_mutation` (from `provider_attempts.py`) and `_write_json_atomic` (from `observability/live_notes.py`). **[RUN: AST plus grep]**

### m7 (minor, Phase 0): pruning worktrees with other sessions active

127 worktrees and 220 branches exist; other sessions work in this checkout and in worktrees. Restrict the item to branches reported by `git branch --merged main` whose worktree is clean, and list what was removed. **[RUN: counts; rule INFERRED]**

### m8 (minor, Phase 3 seen from Phase 6): same-run reuse is not cross-run reuse

Phase 6 lists "children reuse the parent's committed effects where Phase 3 allows". The memo belongs to one run root and one workspace; a child program is a new run on another clone. Phase 3 as written gives nothing to a child unless a run can be forked with its workspace. Say so in Phase 3's "Makes harder" or drop the Phase 6 line. **[READ; INFERRED]**

### m9 (minor, Phase 2): the guide cut and the contract/evidence split are writing work with test coupling

The drafting guide is 3,326 lines; the target is under 1,000. Two test modules reference it and 72 read some doc. Allow 1-2 weeks and run the doc-reading tests. **[RUN: counts; estimate INFERRED]**

## Answers to the three spike questions, as far as reading and probes allow

1. **Do identities survive an unrelated edit?** Python source: no, every effect bound after the insertion point is renamed **[RUN]**. `.orc` source: yes for effects bound to an authored name whose enclosing forms are unchanged; no for unnamed effects after an inserted unnamed effect in the same scope, for repeated binder names, and for any effect whose enclosing `let`, branch or loop changes **[RUN]**.
2. **Can replay accept commits in a different order, or commits no longer reached?** Not today, at four separate points: the header digest check, the reducer's site lookup for every row, the journal-order check, and the "every active commit reached" check **[READ]**. Accepting a matching prefix in the same order needs the first two changed and an automatic suffix range. Accepting a different order needs the last two changed as well, and a new invalidation record.
3. **Which effects are safe to reuse when a command reads workspace state its inputs do not cover?** The recorded inputs cannot tell. Today's safety comes from journal order under an identical program: a reused effect was preceded by the same effects. The only reuse rule that keeps that argument is prefix reuse. Out-of-order reuse is safe only for effects that declare everything they read and write, and no such declaration exists **[READ; INFERRED]**.

Is `depends_on` complete enough to invalidate by dependency? No. It over-approximates value flow (per value, not per field; in a serial map each item depends on all earlier ones) and omits workspace coupling and the branch condition for effects inside a branch **[READ: C9]**.

Judgment: **feasible in a narrower form** (prefix reuse with automatic suffix invalidation, stable names first, refusal on coordinators). Not feasible as stated without weakening guarantees.

## Ordering and missing prerequisites

- Deleting first neither helps nor endangers Phase 3 much: Phase 3 lives in `workflow/evaluated/` (10,175 lines) and `cli/commands/evaluated.py`, which the deletion does not touch **[RUN: import graph]**. The danger is indirect: a moving baseline while a soundness-critical change is tested.
- The Phase 3 spike should precede the single-target cut, because its answer on naming changes site strings, and fixtures should migrate once.
- Missing prerequisite: a failing-node baseline with a fixed launch recipe before Phase 2 (M4).
- Missing prerequisite: stable binder names before Phase 3 (M1).
- Missing decision: the dashboard and `report` for pre-evaluated runs before the IR stack goes (M3).
- Suggested order: 0 → 1 with the Phase 3 spike alongside → 2a (trial, adjudication, peers, supervision, `StateManager`) → 4a (parallel-map qualification) and stable names → 3 (narrow) → 2b (IR stack) and 2c (target stages) → 4b (Python additions).

## Effort

| Phase | Estimate (engineer-weeks) | Confidence | Main uncertainty |
| --- | --- | --- | --- |
| 0 Clear the ground | 0.5-1 | High | classifying 71 recorded failures into an owned list |
| 1 The first hour | 2-3 (add 1-2 if multi-diagnostic stays) | Medium | `:on-exhausted` scope, W0 scope, tutorial acceptance |
| 2 Delete and unify | 7-11 (deletion 3-4, single target 3-5, docs 1-2) | Low to medium | IR vocabulary extraction, dashboard decision, 2.35-regime fixture migration |
| 3 Edit and continue, narrow form | 5-7 (spike 1, design 1-2, implementation and kill matrix 3-4) | Medium for the narrow form | new crash windows, stable-name prerequisite |
| 3 as written (dependency-based reuse) | 10-14, may not converge | Low | soundness without read/write declarations |
| 4 Python first, parallel map | 6-9 (parallel-map remainder 2-3, Python additions 4-6) | Medium to low | procedure references, PQ-1c outcome, exit-test definition |
| Total, Phases 0-4 with narrow Phase 3 | 21-31 | Low to medium | |

All estimates are **[INFERRED]** from the counts above and from the size of comparable past commits.

## Top three risks to the roadmap as a whole

1. **Phase 3 soundness.** The headline target (reuse by recorded dependency) was already tried and rejected in the accepted design, and the stop rule falls back to the unsound half. Phase 6's cost control and the "cheap to iterate" goal both rest on it.
2. **Phase 2 absorbs the calendar.** A 30k-line deletion plus a regime migration over about 390 fixtures, on a suite with 71 known failures that vary with launch context, is two to three months before any author sees a benefit, and it moves the ground under Phases 3 and 4.
3. **Exit tests that cannot fail or cannot be measured.** Phase 0's is already true, Phase 1's tutorial test has no measurement, Phase 2's contradicts its stop rule, Phase 3's passes without the claimed mechanism, Phase 4's is undefined. Phases can then close without delivering, or never close.
