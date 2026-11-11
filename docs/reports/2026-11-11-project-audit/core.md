# Core implementation audit: `orchestrator/` (branch main, 2026-11-11)

Task: review_code_core_conceptual_audit. Read-only. I judged the code and live provider-free probes, not the repo's docs or reports.
Legend: **[RUN]** = I verified it by running something. **[READ]** = I inferred it by reading code, or from static import or call-site counts.

---

## 1. Size and shape

### LOC per subpackage [RUN: `find … | wc -l`]

| Package | Modules | Lines | Notes |
|---|---:|---:|---|
| `workflow_lisp/` | 109 | 90,880 | top-level 66,586 · `closed/` 11,862 · `wcc/` 11,221 · `adapters/` 1,211 |
| `workflow/` | 163 | 87,948 | top-level 30,683 · `run_ref/` 17,743 · `evaluated/` **10,175** · `provider_phased_delivery/` 9,406 · `trial/` 8,343 · `provider_peer_group/` 5,704 · `provider_supervision/` 3,076 · `adjudication/` 2,818 |
| `providers/` | 38 | 38,155 | ~18K of it is `isolation_*` |
| `contracts/` | 16 | 10,171 | `closed_program/` checker 7,151 |
| `orchestrator/*.py` (top level) | 22 | 7,507 | `state.py` 1,664 · `prompt_*` 5,126 |
| `dashboard/` | 10 | 6,023 | |
| `lsp/` | 9 | 5,510 | |
| `cli/` | 23 | 3,980 | `main.py` 855 (`create_parser` is 485 lines) |
| `py/` (Python frontend) | 8 | 3,033 | |
| observability 1,696 · managed_jobs 1,342 · deps 1,216 · monitor 985 · _common 973 · demo 923 · exec 806 · variables 344 · fsq 222 · security 199 · omp_assets 45 | | | |
| **Total** | **458** | **261,958** | |

- Modules over 500 lines: **130**. Modules over 1,000 lines: **68**.
- Functions: 8,383 in total. An AST approximation of cyclomatic complexity puts 1,013 of them above 12. 87 are longer than 200 lines.
- Tests: 720 `.py` files, of which 665 are `test_*.py`. They hold **379,308 lines** and about 9,666 `def test_` functions, so the test-to-code ratio is about 1.45.
- The repo root holds 420 stray `tmp*` and `orc-observe-*` directories. I noted them and did not touch them.

### 25 largest modules [RUN]

| Lines | Module |
|---:|---|
| 7,432 | workflow_lisp/wcc/elaborate.py |
| 7,254 | workflow_lisp/expressions.py |
| 6,546 | providers/isolation_environment.py |
| 5,454 | workflow_lisp/compiler.py |
| 5,184 | contracts/closed_program/check.py |
| 4,602 | workflow_lisp/closed/build.py |
| 4,479 | workflow/trial/ledger.py (trial execution is retired) |
| 3,891 | dashboard/server.py |
| 3,699 | workflow/run_ref/runtime.py |
| 3,506 | providers/executor.py |
| 3,477 | providers/isolation_backend.py |
| 3,357 | workflow_lisp/workflows.py |
| 2,991 | workflow_lisp/procedure_specialization.py |
| 2,817 | workflow/provider_phased_delivery/ledger.py |
| 2,604 | workflow/pure_expr.py |
| 2,589 | providers/isolation_bundle_broker.py |
| 2,517 | workflow_lisp/procedure_typecheck.py |
| 2,360 | workflow_lisp/functions.py |
| 2,316 | workflow/executable_ir.py (YAML-era IR) |
| 2,284 | providers/isolation_network_preflight.py |
| 2,224 | workflow/prompt_identity.py |
| 2,158 | workflow_lisp/closed/names.py |
| 2,034 | workflow/persisted_surface.py |
| 2,025 | contracts/output_contract.py |
| 1,957 | workflow_lisp/contracts.py |

### Largest functions [READ: AST scan; nested functions count toward their parent]

| Lines | ~cc | Location |
|---:|---:|---|
| 995 | 110 | workflow_lisp/typecheck_dispatch.py:254 `_typecheck` |
| 929 | 97 | workflow_lisp/compiler.py:1517 `_compile_stage3_graph` |
| 831 | 91 | workflow_lisp/wcc/elaborate.py:5887 `_elaborate_effect_expr_to_binding_value` |
| 683 | 59 | workflow_lisp/typecheck_structural_values.py:121 |
| 643 | 124 | workflow_lisp/functions.py:813 `normalize_resolved_inline_procedure_calls` |
| 612 | 222 | workflow/trial/ledger.py:1432 `_validate_lifecycle` (retired feature) |
| 449 | 181 | workflow_lisp/closed/names.py:1563 `_procedure_reference_key` |

### How much code one real run touches [RUN: in-process `sys.setprofile` tracer]

I compiled and ran a two-command Lisp workflow under the tracer (script: `…/scratchpad/audit/trace_run.py`).

- It loaded **258 of 458 modules**, which is 175K of 262K lines.
- It executed **1,046 of 8,383 functions (12.5%)**. Those functions hold 17.7% of all function-body lines.
- Every module of the YAML-era IR (`surface_ast`, `core_ast`, `semantic_ir`, `executable_ir`, `runtime_plan`, `state_projection`, `loaded_bundle`) was loaded, but in each one only class bodies ran. No real function in them executed.

---

## 2. Runtime spine: is evaluation plus the memo the only mechanism?

### The spine exists, and it is clean [READ, confirmed by RUN]

- **Evaluator**: `workflow/evaluated/machine.py` is 485 lines. `_Machine._body` dispatches over ten body kinds: let, halt, if, case, join, jump, loop, continue, done and par-map (machine.py:135-146). Control flow travels as `_ControlTransfer` exceptions (70-79). Effects run only through the `effect_handler` callback (353-375).
- **Effect identity**: the identity is the activation path plus the call frames plus the checked site string. Loop `[*]` markers become actual ordinals (machine.py:33-62, 360-361, 437-455). A probe identity looks like `workflow:main::run / b` or `workflow:py/python_command_loop::run / _e1 / body / loop:_loop0[2] / else / _e0` [RUN].
- **Memo**: `evaluated/memo.py` (180 lines) and `memo_reducer.py` (456 lines). Records are fsync'd append-only JSONL with tail-tear repair (memo.py:101-157). There are 7 record kinds and 7 effect classes (memo_reducer.py:15-19).
- **Resume**: `execute_pure_resume` (runtime.py:194-255) calls `replay.discover_prefix` (replay.py:194-211). That function runs the **same evaluator** with a handler that returns committed values (replay.py:72-87). The handler checks journal order and `depends_on`, and requires that every active commit is reached (replay.py:172-176). After that, the run continues through `execute_pure_run`.
- **Resume preflight**: resume recompiles from the recorded recipe and refuses on a program-digest or input-digest change (cli/commands/evaluated.py:166-197).
- **Invalidation**: an appended `invalidated` range covers the target commit and every later commit in journal order (memo.py:160-180, suffix selected at :168). The range is chosen by journal order, not by dependency.
- **state.json**: a derived view republished from the memo (evaluated/views.py:104). `report` rebuilds it when it is missing [READ].

### Mechanisms that survive beside the spine

| Mechanism | Size | Status | Evidence |
|---|---:|---|---|
| `state.py` StateManager / RunState (state.json authority era) | 1,664 | **Mostly dead.** Live code only allocates the run id and run root (evaluated.py:250-257). About 13 mutation methods (`update_step`, `update_loop_step`, `finalize_step_with_dataflow`, `allocate_provider_attempt`, `fail_run`, `backup_state`, …) have **0 production callers**; only tests call them. Checkpoint report paths remain at state.py:666-676. | grep [READ] |
| YAML-era IR stack: surface_ast 599, core_ast 1,670, semantic_ir 540, executable_ir 2,316, runtime_plan 995, state_projection 867, loaded_bundle 354, persisted_surface 2,034, elaboration 1,182, statements 157, linting 305, judgment_views 1,816, … | ~13.8K | **Dead in production; tests keep it alive.** `LoadedWorkflowBundle(` is never constructed in `orchestrator/`; only tests and `tests/fixtures/historical_observability_bundles.py` build it. `build_core_workflow_ast` and `derive_workflow_runtime_plan` have 0 production callers. `elaboration.py` has 0 importers. The IR dataclasses survive as vocabulary: `executable_ir.RunRefStepConfig` is used by evaluated/run_ref.py:9,52, and compiler signatures still take `LoadedWorkflowBundle` (compiler.py:24, 589). | grep + trace [READ/RUN] |
| Coordinator sub-ledgers: `run-ref-attempts.jsonl` (run_ref/ledger.py 1,424, total `run_ref/` 17,743) and the phased-provider ledger (provider_phased_delivery/ledger.py 2,817, total 9,406) | ~27K | **Live, and they duplicate the memo's durability.** A second append-only journal is kept consistent with the memo through `settled` rows and "coordinator classes" (memo_reducer.py:19, 57-59; evaluated/run_ref.py:181-243; phased_providers.py:38). In effect this is a two-phase commit between two journals. | [READ] |
| `workflow/trial` 8,343 + `adjudication` 2,818 + frontend trial parse/typecheck (typecheck_trial, trial_result_contract ≈ 814 lines; 226 mentions in expressions.py) | ~12K | **Execution is dead, parsing and type checking are live.** The CLI refuses trials (cli/commands/trial.py:7-9). The closed builder emits a gap for them (closed/build.py:1718). The type checker still checks them. | [READ] |
| `provider_peer_group` 5,704 + `provider_supervision` 3,076 | 8.8K | **Unreachable from evaluated execution.** They are imported only by `cli/commands/peer.py` and `executable_ir`. The evaluated runtime, closed builder and closed checker never reference them. | [READ] |
| `prompt run/import` scaffolding (prompt_scaffold*, which renders `(:target-dsl "2.27")` at prompt_scaffold_render.py:282) | part of 5,126 | **Creation is retired** (cli/commands/prompt.py:8-9), but the code is kept because `prompt resume` imports it. | [READ]; RUN: `prompt run` still parses its full flag set |
| Small leftovers: wcc/historical.py 226 (self-described "historical"), legacy_provider_quarantine.py 45 (0 importers), transition_executor.py 23, executor_runtime.py 6 | ~300 | dead or vestigial | [READ] |
| CLI vestiges | ~300 | run.py:237-341 (clean/archive helpers) and 105-163 (`build_observability_config`) have 0 production callers. run.py:351-354 has unused parameters and :384-385, :406-411 have unused locals (`state_dir_override`, `run_ref_root`, `selected_target`). resume.py:56-75 has 15 ignored parameters (`repair`, `on_error`, `max_retries`, `summary_*`, `live_agent_note_*`). resume.py:29-30 is unreachable because `_has_authority_header` raises first. | [READ] |

**Verdict:** for command, provider and agent effects, evaluation plus the memo really is the single execution spine. No flat, semantic or executable-IR executor and no YAML loader is reachable from `run`, `resume` or `invalidate`. Two things undercut that, though:

1. About 25-35K lines of the retired architecture survive as types, test fixtures and dead helpers.
2. The run_ref and phased-provider coordinators bring their own journals, so the memo is not the only durable authority for those effect classes.

---

## 3. Compiler pipeline

Path [READ, confirmed by trace]: `cli/commands/evaluated.py:233` → `closed/artifact.py:118 _prepare_closed_program_bundle` → `closed/frontend.py:614` → `compiler.compile_stage3_entrypoint` → `_compile_stage3_graph` (compiler.py:1517).

| # | Stage / representation | Code | Lines |
|---|---|---|---:|
| 1 | Reader: span-carrying S-expressions | reader.py, spans.py | ~0.5K |
| 2 | Syntax module + form registry | syntax.py, form_registry.py | ~1.6K |
| 3 | Module graph / linking | modules.py + compiler.py | 6.5K |
| 4 | Macro expansion (`expand_module_forms`) | macros.py | 1.1K |
| 5 | Definition elaboration → `*Expr` AST | expressions.py, definitions.py, workflows.py, procedures.py, functions.py, loops/loop_state, conditionals, prompts, phase* | 21.6K |
| 6 | Type check + effect-summary inference → TypedProgram | typecheck_* (14 modules), type_env, procedure_typecheck, effects | 14.6K |
| 7 | Generic specialization / inline-procedure normalization | procedure_specialization, generic_unions, parametric_constraints, procedure_refs, functions.normalize… | 4.6K + |
| 8 | WCC (Workflow Core Calculus) elaboration + ANF | wcc/ | 11.2K |
| 9 | Closed tree (JSON) + names + command templates | closed/ | 11.9K |
| 10 | Independent closed-program checker; re-infers types (check.py:1358-1527) | contracts/closed_program/ | 7.2K |
| 11 | `ClosedProgram` digest, artifact readback self-check (artifact.py:212-218) | closed/artifact.py, program.py | 0.5K |

- The live path builds about **six representations**: sexpr, syntax module, Expr AST, typed program, WCC/ANF, and closed JSON. It also uses **three type representations**: `TypeRef` (type_env.py:174-370), JSON descriptors (type_descriptor.py, normalized_type_descriptor.py), and the checker's own inference.
- On top of that sit **six more IRs from the historical stack** inside `LoadedWorkflowBundle` (loaded_bundle.py:31-40: surface, core AST, semantic IR, executable IR, state projection, runtime plan). Evaluated execution needs none of them. They are reached only through type annotations and tests.
- Leftover vocabulary: names like "stage1" and "stage3" with no stage2, `WCC_M1/M4_ROUTE_SCHEMA_VERSION`, and `DEFAULT_LOWERING_SCHEMA = 2`.

**Target gating** [READ]

- Six targets are admitted (contracts/closed_program/targets.py:9-11).
- Seven `target_dsl_supports_*`/`uses_*` predicates exist (targets.py:14-54, syntax.py:751). They have **50 call sites in 21 files**.
- There are 13 direct `target_dsl_version` comparisons, two of them hard-coded `== "2.40"` (typecheck_effects.py:81, expressions.py:6394).
- The retired-target refusal runs **three or four times** on one run path: run.py:398, artifact.py:128, a fallback at artifact.py:168-187, and frontend.py:649.
- Pre-2.35 literals survive:
  - statements.py:9-13 (2.2-2.12), dead
  - elaboration.py:191-206, dead
  - typecheck_resume.py:150,167 (`"2.14"` hard-coded into the live `resume-or-start` fingerprints)
  - phased ledger.py:940,1651 (`"2.23"`)
  - prompt_scaffold_render.py:282 (`"2.27"`)
- Characterization: there are few feature gates, but they are scattered as predicate calls rather than one capability table. The old version numbers are mostly dead code, except where they are frozen into live identities.

---

## 4. Type system

**What an author gets.** Every item below was verified by a run.

- Records, enums, `defpath` path contracts and relpaths, Optional/List/Map, and `Value` for loose transport.
- Unions with **flow-sensitive variant proof**:
  - Reading `o.score` without a `match` fails at compile time: `[variant_ref_unproved] field score requires variant proof for Outcome`.
  - A command returning `"score": "not-an-int"` fails at runtime with `variant_field_type_invalid`, and the run exits 1.
- Applied generic unions (`Outcome[Int String]`), `:forall` type parameters, workflow and procedure references, and `defschema` field groups. These come from reading the code, not from a probe.
- Effect inference with "effect ceilings" from target 2.39 onward.

**Where the complexity is spent** [READ]

- **Provider and command result validation is the minority**, roughly 5.5K lines: contracts/output_contract.py 2,025, result_guidance.py 1,417 (prompt guidance), type_descriptor.py 1,246 (transport schemas), evaluated/values.py 492, evaluated/providers.py 364.
- **Compile-time proof and identity bookkeeping is the majority**: about 14.6K lines of type checking, 4.6K of specialization, and about 5K of re-checking in the closed checker.
- Type metadata exists mainly to keep digests stable: `json_omit_if_empty`, `semantic_identity_omit`, and `repr` that is explicitly "digested into specialization and checkpoint identities" (type_env.py:212-219, 276-299). Making `__repr__` an identity input is fragile.

---

## 5. Accidental versus essential complexity

### Most over-built relative to what the feature does

1. **The frontend is about 30 times the size of the runtime it targets.** About 98K lines of compiler and checker feed an evaluator of under 500 lines with ten body kinds. Single functions run 900-1,000 lines (typecheck_dispatch.py:254, compiler.py:1517). There are 14 `typecheck_*` modules plus a second, independent 5.2K-line re-checker.
2. **The retired architecture is kept alive by tests.** About 13.8K lines of YAML-era IR, StateManager mutation APIs and CLI vestiges remain, together with test fixtures named "historical". The tracer shows that no function in them runs on a real run.
3. **Coordinator sub-ledgers.** run_ref (17.7K) and phased delivery (9.4K) keep their own append-only journals and need `settled` reconciliation with the memo. This is where the "one memo" idea breaks.
4. **Eager imports of the isolation stack.** `cli/main.py:7` imports one constant from `observability.summary`, which imports `providers.types`. That runs `providers/__init__.py`, which imports executor and isolation, and isolation.py:16 imports `jsonschema`. In this environment jsonschema pulls in `rfc3987_syntax`, which builds 39 lark grammars. Measured: `import jsonschema` takes 2.5 s; in the profile, 5.0 s of a 10.8 s `py build` went to this import chain. Even `--help` takes 2.6 s. The isolation code itself is about 18K lines and never runs for command workflows.
5. **Residue of retired features and defensive repetition.** This covers trial (about 12K lines, still type checked), prompt scaffolding, refusals that parse the full flag set first, the repeated retired-target checks, the build readback self-check, and memo rows that store `implementation_files` twice under keys `[…,1]` and `[…,null]` with the same digest [RUN].

### Strongest, cleanest ideas

1. **The structured evaluator** (machine.py). It is small, total over a checked tree, keeps effects behind one callback, and expresses control as typed transfers. Effect identity comes from the static site plus the dynamic activation path, so it is deterministic and human-readable (`workflow:main::run / b`).
2. **Replay is evaluation.** Resume reuses the same machine with a memo-backed handler (replay.py:72-87). It also proves that every commit was reached and that dependencies match (replay.py:81-83, 172-176), so there is no second interpreter for resume.
3. **An honest durability core.** The memo is fsync'd, append-only and torn-tail aware. Invalidation is an appended range, not a rewrite (memo.py:101-180), and state.json is only a derived view.
4. **Dependency tracking at the value level.** `EvaluatedValue.dependencies` carries data and control dependencies through if, case and loop (machine.py:207-217, 251-281). Commits record them as `depends_on` and replay checks them.
5. **Content-addressed closed programs with a strict resume preflight.** Resume recompiles, then compares the program digest, the input digest and the effect input parts. In the probes, whitespace edits passed, semantic edits were refused, and closure-file edits were detected [RUN]. The Python frontend is a code generator that emits `.orc` (run in a subprocess) into the one pipeline, not a second frontend.

---

## 6. Live probes (provider-free; PYTHONPATH set to the repo; workspaces under `…/scratchpad/audit/probe-core/`)

Environment: `/home/ollie/miniconda3/bin/python`, Python 3.13.9, `PYTHONDONTWRITEBYTECODE=1`. The machine was under load, so timings vary by about ±1 s.

### A. Python example (`workflows/examples/python_command_loop*.py` copied into `probe-core/py/`)

```
python -m orchestrator py build workflows/examples/python_command_loop.py --entry-workflow run --command-boundaries-file workflows/examples/python_command_loop.commands.json   → exit 0, WALL 8.41 s
python -m orchestrator py check … (same args)                                → exit 0, WALL 8.28 s
python -m orchestrator py run   … --input limit=3                            → exit 0, WALL 8.80 s, stdout EMPTY
```

- The generated `.orc` targets **2.39** and has 2 command sites.
- The memo ends with `{"outcome":"completed","record":"terminal","value":2}`.
- Execution inside the run took about 0.2 s (state.json timestamps 19:05:05.13 → 05.34). The rest is imports plus a subprocess that generates the `.orc`: 4.06 s spent in `subprocess.run` from py/build.py:126.

### B. Lisp workflow with two commands, kill, resume and invalidate (`probe-core/lisp/`)

`main.orc` is at target 2.35. Its effect `a` computes `seed+10` and effect `b` computes `a+10`. While a `SLOW` file exists, the tool sleeps in `b`.

```
compile main.orc --entry-workflow main::run --source-root . --command-boundaries-file commands.json   → exit 0, 4.45 s, "sites": 2
run … --input seed=1   (killed with SIGKILL while b ran)
   memo: started a/1, committed a/1=11, started b/1   ; state.json status "running"
resume <run>                         → "[effect_rerun] workflow:main::run / b attempts=[1]", exit 0, 4.01 s
   dispatches: a:1:attempt-1, b:11:attempt-1, b:11:attempt-2 ; terminal {"first":11,"second":21}
resume <run>  (already complete)     → exit 0, 3.76 s, no new dispatch
invalidate <run> 'workflow:main::run / a'  → {"from_commit": 948, "record": "invalidated", …}, exit 0, 4.16 s
invalidate <run> 'main::run / a'           → "[invalidate_not_committed] main::run / a", exit 2
resume <run>                         → re-ran a (attempt-2) and b (attempt-3); new terminal appended
report --run-id <run>                → clean Markdown view (status, inputs, outputs, per-effect rows)
edit tool.py (closure), invalidate b, resume → "[effect_input_diverged] workflow:main::run / a: effect input diverged (input parts changed: ['implementation_files'] …)", exit 2
whitespace edit to main.orc, resume  → exit 0 (program digest unchanged)
semantic edit to main.orc, resume    → "[resume_program_changed] current program differs from the run header", exit 2
```

### C. Diagnostics [RUN]

- `-> String` with an `Int` body gives `bad.orc:4:5: [return_type_mismatch] … declared return type String but body returned a different type`. It is located, but it does not name the actual type.
- An unknown command gives `[command_adapter_missing_contract]`. After that is fixed, the next compile gives `[name_unknown] unknown name sed`, so the compiler reports **one error per compile**.
- `(:target-dsl "2.30")` gives `[workflow_execution_target_retired] … use a separately retained complete release/environment`.
- `--input seed=abc` gives `Validation error: Workflow input binding failed` (exit 2). It does not name the input or the reason.
- A runtime type error gives `[evaluated_execution_failed] variant_field_type_invalid: Output value is not a valid integer`. It does not name the field or the effect.

### Artifacts a run leaves [RUN]

- `.orchestrate/runs/<id>/` contains:
  - `run.json` (1.5 KB header including the rebuild recipe)
  - `closed_program.json` (10 KB, a copy of the build)
  - `memo.jsonl` (4.7 KB for two commands, because each row repeats digests)
  - `state.json` (derived view)
  - `run.lock`
  - `effects/<sha256(identity)>/attempt-N/{result.json,stdout.txt,stderr.txt}`
- `.orchestrate/build/<16-hex key>/{closed_program.json,manifest.json}`, plus `workspace.lock` and `workspace.guard`.
- The Python frontend also writes `.orchestrate/python/<sha>/{generated/*.orc, inputs/<absolute-path mirror>/…, manifest.json, source-map.json}` and `pin-*.json`.
- After all the probes, the Lisp workspace's `.orchestrate` held 24 files totalling 120 KB.

### Surprises and friction

- `run` and `py run` print **nothing** on success, not even the result value. You have to run `report` or read the memo.
- About 2.5-4 s of startup per CLI call, mostly the jsonschema/rfc3987 import chain. Every compile, resume and invalidate pays it.
- **Resume cannot absorb program edits.** Any semantic edit refuses resume, so a mid-run fix means starting a new run.
- After a closure-file edit, the run is stuck until you invalidate the earliest affected commit. The error does not suggest `invalidate`.
- Invalidation is by **journal suffix** (memo.py:168), even though per-commit `depends_on` exists.
- Good: diagnostics are coded and located, and the effect identities are readable and work directly as `invalidate` arguments.

No narrow pytest selectors were run; the probes above covered the needed evidence.
