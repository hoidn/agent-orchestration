# Workflow Lisp Frontend Deduplication Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` to implement this plan task by task after selection. Steps use checkboxes; unchecked steps are obligations, not evidence of completion.

**Goal:** Remove repeated command argv, typed host-answer declarations and common command closures without introducing another runtime execution path.

**Architecture:** Resolve the three authoring abbreviations into existing concrete command bindings and typed expressions before closed-program construction. Preserve the current runtime, command policies, transport, evidence validation and recovery rules.

**Tech Stack:** Existing Python frontend, Workflow Lisp, JSON command manifests, pytest and the public orchestrator CLI. No new dependency or paid-provider experiment.

**Role / selection:** Completed implementation plan. The owner requested “stage and commit, then execute” on 2026-10-26, selecting the reviewed design and its recommended additive version admission. The three source forms are implemented and locally integrated; independent reviews and the closing verification gates below passed. The current contracts own admission.

**Decision record:** [Incorporated frontend deduplication design](../design/workflow_lisp_frontend_deduplication.md). Current authorities remain the [frontend](../design/workflow_lisp_frontend_specification.md), [command contract](../design/workflow_command_adapter_contract.md), [host input](../design/workflow_lisp_durable_host_input.md), [evaluated execution](../design/workflow_lisp_evaluated_execution.md) and [versioning policy](../../specs/versioning.md).

## Scope and decisions

The three changes form independently reviewable tranches:

1. At target 2.40, an applied prompt with an explicitly declared answer contract supplies omitted `request-input :returns`. Raw strings and prompts without a declared return contract still require it.
2. With neither `:argv` nor `:adapter`, `command-result` uses the named external tool's complete `stable_command`. `:returns` remains required. Presence of `:inputs`, including `:inputs ()`, retains its existing meaning.
3. An optional manifest envelope declares one `shared_closure` array and a `commands` map. Every command receives the shared files plus its local closure; local `[]` cannot subtract common files. Existing flat manifests remain valid.

The selected admission is additive on supported targets 2.35–2.40, with host inference restricted to 2.40. No target 2.41 is introduced and host-input admission is not broadened.

Typed failure propagation, expected-type constructor shorthand (W1), arbitrary command return inference, a general manifest inheritance system, automatic source rewriting, Python API changes and compiler-module restructuring are excluded. Inferring argv does not prove a tool's required argument count. Source migration does not promise equal build hashes or cross-version resume.

### Working-tree and execution boundaries

- The repository already contains unrelated edits. Record the starting status, use an isolated implementation worktree when selected, and never stage or overwrite unrelated changes.
- Preserve the DAQ v4 live workspace, its pending owner request, frozen runtime and recorded scorecards. Examples and LOC measurements use disposable copies only.
- Delegate bounded code tranches to the implementation role (Luna 6 xhigh); use a distinct Sol 6.1 high code reviewer. Return architectural deviations to Design (Astra 6 xhigh). The coordinator owns integration and final verification.
- These are development checks, not a comparative quality experiment. No authenticated provider calls, judge calls or DAQ debate relaunches are part of the plan.

## Baseline and measurement contract

Read-only census on 2026-10-26 of the existing DAQ v4 demo:

| Artifact | Observation |
| --- | --- |
| `workflows/daq_diagnosis.orc` | 132 physical lines, 11 `command-result` forms, 13 `BLOCKED` arms and six `EXHAUSTED` arms |
| `inputs/commands.json` | 115 physical lines, eight commands, 32 closure entries referring to four distinct paths |
| Same manifest data, arrays on one line | 43 physical lines; parsed JSON equality checked, no semantic simplification |

Evidence source root: `/home/ollie/Documents/daq-debate-framework-v4-live/artifacts/debate/demo` (context only; never a CI prerequisite). SHA-256 of the workflow is `b83e7ccfa7d2cf4d8f0bcc6316074d1c19cd9be7f9584c726049e1f73e4a48a1`; the manifest is `058b27810e71ff04258a7cebf88f48c39b599147cd272d63ea49bc3d21010ec9`.

Measure physical lines, nonblank/noncomment lines, source bytes, repeated argv tokens and authored closure-path occurrences separately. Apply identical formatting rules to before/after sources. Count all configuration and helper code; moving declarations to another file is not deletion. Record frontend implementation/test growth separately from authoring savings. Do not claim a numeric LOC improvement until measured; the known workflow formatting may yield character savings without removing an entire line.

## Task 1: Establish the contract and narrow proof fixtures

**Files:**
- Read the design and current authorities linked above.
- Inspect `orchestrator/workflow_lisp/expressions.py`, `typecheck_effects.py`, `compiler_session.py`, `build_manifest_io.py`, `build.py` and `closed/frontend.py`.
- Reuse existing tests named in Tasks 2–5 rather than building a second compiler harness.

- [x] Accept the version/admission choice, manifest grammar and compatibility limits in the design. If changed, revise the design before coding.
- [x] Capture starting status and identify source-only versus typed/imported entry points. Confirm typed imports cannot carry unresolved external argv or answer types into the checked program.
- [x] Record the baseline narrow test results using the current environment:

```bash
python -m pytest -q tests/test_workflow_lisp_host_input.py tests/test_workflow_lisp_command_input_documents.py tests/test_workflow_lisp_command_boundary_closure.py
```

- [x] Identify the existing representations for explicit empty argv, omitted argv and certified adapters. An omitted-source marker, if necessary, must be transient and absent from persisted typed/closed artifacts; malformed imported artifacts must never trigger inference.
- [x] Confirm the existing canonical type reference for imported prompt returns can be reused without resolving its private or aliased type name in the wrong module.

**Gate:** The three abbreviations have a concrete normalization owner and a defined refusal path. If this requires a runtime protocol, persisted omission marker or weakened import checker, return to design. Source inspection is a feasibility argument, not passing integration evidence.

## Task 2: Infer the host answer type from the declared prompt contract

**Modify:** `orchestrator/workflow_lisp/expressions.py`, `orchestrator/workflow_lisp/typecheck_effects.py` only where necessary.
**Tests:** `tests/test_workflow_lisp_host_input.py`; extend existing imported-prompt cases rather than duplicating their module harness.

- [x] Add failing cases for declared enum, `String` and transportable union prompt returns with omitted `:returns`, including imported/aliased prompts and a caller-local colliding type name.
- [x] Extend `test_typed_capsule_keeps_shared_nominal_answer_after_producer_source_removal` and `test_prompt_fills_and_shown_paths_survive_specialization` in `tests/test_workflow_lisp_host_input.py` with inferred-return forms. Export a typed capsule, remove producer sources, import it and prove the original canonical answer type, fills and shown evidence survive without caller rebinding.
- [x] Add negatives: raw question without `:returns`; prompt with only an implicit/default return; explicit mismatch; inadmissible answer type; unresolved or incompletely applied prompt; duplicate/unknown keywords; target 2.39. Keep existing pure, parallel and child-run restrictions covered.
- [x] Run the new selectors and confirm failures arise from the missing inference feature, not fixture setup.
- [x] Resolve the prompt before deciding whether `:returns` is required. Copy its declared canonical type through the current typed path; retain explicit declarations and the existing match/transport validators.
- [x] Compare expanded and abbreviated checked answer/result descriptors and effect summaries. Preserve prompt fills, shown paths, timeout semantics and source diagnostics. Do not assert whole-build digest equality across different source bytes.
- [x] Collect the changed module and run it:

```bash
python -m pytest --collect-only -q tests/test_workflow_lisp_host_input.py
python -m pytest -q tests/test_workflow_lisp_host_input.py
```

**Expected:** Both forms produce `HostReply[A]` through the same checker; every negative refuses before requesting host input. Review the tranche before proceeding to another edit of the same frontend files.

## Task 3: Resolve omitted external-tool argv at its existing binding owner

**Modify:** `orchestrator/workflow_lisp/expressions.py`, `orchestrator/workflow_lisp/typecheck_effects.py`.
**Inspect, modify only if required:** current expression traversal/typed serialization owners and `orchestrator/workflow_lisp/closed/command_interfaces.py`.
**Tests:** `tests/test_workflow_lisp_command_input_documents.py`, `tests/test_workflow_lisp_command_adapters.py`, `tests/test_workflow_lisp_closed_program_frontend.py`.

- [x] Add paired expanded/abbreviated cases for no inputs, empty input document and populated input document; test all supported source targets named by the design.
- [x] Add negative cases for missing binding, invalid/empty stable command, certified binding used as an implicit external tool, explicit empty argv and conflicting modes. Keep command result-type and inline-shell/hidden-effect checks intact.
- [x] Add an imported procedure case and an invalid imported external-command artifact case. The latter must refuse, not acquire an argv from ambient configuration.
- [x] Extend the source-free producer-scope coverage in `tests/test_workflow_lisp_closed_program_frontend.py`: compile abbreviated argv in the producer, export its typed capsule, delete producer sources and import it with a different homonymous consumer binding. The result must retain the producer's concrete argv, closure and policy, never infer them again from the consumer.
- [x] Add one effectful input producer. Verify it executes once, before the tool, with input fields in their existing order. A generated literal argv adds no effect site.
- [x] Admit the short source form, then materialize literal argv in `typecheck_command_result_expr`, where `command_boundary_environment` already exists. Do not thread command bindings through every elaboration call or add a second resolver.
- [x] Run existing binding and argument validation on the resolved expression. `:adapter` keeps its certified transport; explicit dynamic argv is preserved; `:inputs ()` appends an empty document, while absent `:inputs` appends none.
- [x] Verify concrete argv is present before typed export and WCC/closed lowering. Omission is never interpreted by the runtime.

```bash
python -m pytest --collect-only -q tests/test_workflow_lisp_command_input_documents.py tests/test_workflow_lisp_command_adapters.py tests/test_workflow_lisp_closed_program_frontend.py
python -m pytest -q tests/test_workflow_lisp_command_input_documents.py tests/test_workflow_lisp_command_adapters.py tests/test_workflow_lisp_closed_program_frontend.py
```

**Expected:** Equivalent invocation bytes/input documents and unchanged policies, with located failures for invalid forms. No command-return inference or invented shell/argument templating is introduced.

## Task 4: Expand the explicit shared-closure manifest envelope

**Modify:** `orchestrator/workflow_lisp/build_manifest_io.py`.
**Inspect:** `orchestrator/workflow_lisp/build.py`, `closed/program.py` and configuration capture; change only a real consumer that assumes all raw top-level keys are command names.
**Tests:** `tests/test_workflow_lisp_command_boundary_closure.py`, `tests/test_workflow_lisp_build_artifacts.py`, `tests/test_workflow_lisp_lsp_cli_parity.py`.

Supported optional envelope:

```json
{
  "$schema": "workflow-command-boundaries.v1",
  "shared_closure": ["scripts/daq.py", "tools/daq.py", "tools/client.py", "tools/evidence.py"],
  "commands": {
    "snapshot": {"kind": "external_tool", "stable_command": ["python3", "scripts/daq.py", "snapshot"]},
    "write": {"kind": "external_tool", "stable_command": ["python3", "scripts/daq.py", "write"], "must_not_repeat": true}
  }
}
```

- [x] Add failing envelope tests for shared-only, shared plus local files, explicit empty shared/local arrays, duplicate paths and certified-adapter rows.
- [x] Cover unknown schema, unknown envelope fields, missing required envelope fields, non-object `commands`, invalid shared/local paths and invalid unused rows. Test legitimate flat-map command names `$schema`, `commands` and `shared_closure` with object-valued entries.
- [x] Distinguish the envelope by its string schema discriminator; never reserve a formerly valid command name. Unknown schema strings refuse instead of falling back to the flat parser.
- [x] Expand each row's common plus local file list before constructing the existing binding. Use the existing literal-path validation and canonicalization. Preserve `None` versus `()` for flat-map closure declarations.
- [x] Keep raw manifest bytes/configuration evidence intact and immutable. Persist ordinary concrete binding closures; do not add group references to artifacts or a runtime merge step.
- [x] Prove equal expanded canonical command configuration for equivalent flat/enveloped inputs and byte-for-byte unchanged treatment of existing flat inputs. Preserve separate `must_not_repeat` policies and validate every supplied row.
- [x] Check CLI and editor configuration capture see the same raw revision and expanded bindings; changing the shared array must invalidate the applicable capture. Existing LSP qualification limits remain open.

```bash
python -m pytest --collect-only -q tests/test_workflow_lisp_command_boundary_closure.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lsp_cli_parity.py
python -m pytest -q tests/test_workflow_lisp_command_boundary_closure.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lsp_cli_parity.py
```

**Expected:** The normal loader handles both authoring shapes through one binding constructor. Local `[]` cannot remove shared files. No defaults framework, closure references, file includes or recursive inheritance exists.

## Task 5: Exercise the combined public path and recovery boundaries

**Create:** `tests/test_workflow_lisp_frontend_deduplication_e2e.py`, using temporary workspaces and existing public CLI/host-input test patterns.
**Reuse:** `tests/test_workflow_host_input_e2e.py`, `tests/test_workflow_evaluated_input_documents.py`, `tests/test_workflow_evaluated_command_replay.py`, `tests/test_workflow_evaluated_closure.py` and `tests/test_workflow_evaluated_resume_retry.py`.

- [x] Build a small deterministic target-2.40 workflow with a read command, a typed approval prompt and a `must_not_repeat` write command. One temporary local tool records dispatches; no real provider or DAQ device participates.
- [x] Run the expanded and abbreviated versions through public `compile`, `run`, `input get`, `input answer` and `resume`. Exercise no-input and JSON-document command modes, verify typed results and count actual dispatches.
- [x] Alter shown evidence before the answer: refusal, zero writes; restore it, answer honestly and resume successfully.
- [x] After approval, alter a declared shared implementation file: resume refuses before another dispatch; restore the file and verify the supported continuation behavior.
- [x] Interrupt after a durably observed write dispatch. Resume must refuse to repeat the uncertain `must_not_repeat` effect. In a separate completed case, resume reuses the committed result with no second dispatch.
- [x] Verify unchanged-source replay from saved artifacts without live shorthand resolution. Treat source/manifest rewrites as migrations; do not relax drift checks or claim cross-package recovery.
- [x] Collect the new module, then run the focused smoke:

```bash
python -m pytest --collect-only -q tests/test_workflow_lisp_frontend_deduplication_e2e.py
python -m pytest -q tests/test_workflow_lisp_frontend_deduplication_e2e.py
```

- [x] After narrow tests pass, run the relevant broader regression set in tmux from the repo root, using the tmux skill:

```bash
python -m pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_lisp_host_input.py \
  tests/test_workflow_lisp_command_input_documents.py \
  tests/test_workflow_lisp_command_adapters.py \
  tests/test_workflow_lisp_command_boundary_closure.py \
  tests/test_workflow_lisp_closed_program_frontend.py \
  tests/test_workflow_lisp_closed_program_compile_cli.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_lsp_cli_parity.py \
  tests/test_workflow_lisp_frontend_deduplication_e2e.py \
  tests/test_workflow_host_input_e2e.py \
  tests/test_workflow_evaluated_input_documents.py \
  tests/test_workflow_evaluated_command_replay.py \
  tests/test_workflow_evaluated_closure.py \
  tests/test_workflow_evaluated_resume_retry.py
```

**Expected:** Tests pass with zero paid-provider calls. The new public CLI test supplies the required orchestrator smoke/integration evidence. Broaden further only for a relevant unresolved concern, and do not rerun passing checks without a reason.

## Task 6: Document the supported forms and measure the subtraction

**Update after implementation:** `docs/design/workflow_lisp_frontend_specification.md`, `docs/design/workflow_command_adapter_contract.md`, `docs/design/workflow_lisp_durable_host_input.md`, `specs/dsl.md`, `specs/versioning.md`, `docs/lisp_workflow_drafting_guide.md` and relevant status/routing rows. Review `specs/io.md` for wording that describes the authored `:argv` requirement; runtime contracts do not change.
**Example:** `workflows/examples/durable_host_input/approval.orc` and its `README.md` may demonstrate host-return inference. Keep its dynamic command argv explicit. Retain an explicit-return example for raw questions.
**Report:** Create `docs/reports/2026-10-26-frontend-deduplication-verification.md` only when real implementation evidence exists.

- [x] Update contract owners and guide examples together. Explain absent versus empty inputs, exact argv inference, the shared-closure union and the limits of type inference.
- [x] Migrate only selected maintained examples; preserve explicit forms needed to demonstrate dynamic argv and raw questions. Do not rewrite historical fixtures, frozen runs or broad workflow corpora.
- [x] Run the existing host-input example smoke after its source changes. Record the exact command and result; do not merely cite an earlier run against different bytes.
- [x] Measure before/after on the portable combined fixture and, if available, a disposable copy of the hash-identified DAQ inputs. Record formatting-only savings separately and disclose missing optional external evidence.
- [x] Inspect the complete diff. Confirm there are no new runtime/schema paths, dependencies, generic configuration machinery or unrelated cleanup.
- [x] Obtain independent code review; apply accepted corrections, then rerun only affected checks. Source-free import, specialization and required replay proofs are completion gates: an unproven required boundary blocks completion and any claim of full parity. Record the gap and return to the owning task or design.
- [x] Check documentation links and whitespace, then stage only this work's reviewed files if a commit is requested or part of the selected execution handoff.

**Completion gate:** All three public forms and negative cases work through the ordinary frontend; saved commands/requests are fully concrete; the public recovery smoke passes; explicit source compatibility is covered; authoring savings and frontend growth are reported honestly. A successful compile alone is insufficient.

## Decision and evidence ledger

| Date | Decision / evidence | Scope |
| --- | --- | --- |
| 2026-10-26 | Owner requested design and plan for frontend LOC improvements | Documentation only; no implementation selected |
| 2026-10-26 | Owner requested staging/commit and execution; design committed as `1a8d5520`, implementation selected with recommended version admission | Isolated `.worktrees/frontend-deduplication`, branch `feat/frontend-deduplication`; previous unrelated changes and DAQ v4 preserved |
| 2026-10-26 | Baseline narrow suite: `python -m pytest -q tests/test_workflow_lisp_host_input.py tests/test_workflow_lisp_command_input_documents.py tests/test_workflow_lisp_command_boundary_closure.py` — 162 passed in 7.10s | Clean implementation worktree; log `.tmp/frontend-dedup/baseline.log` |
| 2026-10-26 | Three bounded abbreviations proposed; typed failure propagation and W1 deferred | Maintains exhaustive routing and existing runtime ownership |
| 2026-10-26 | Current code/contracts and the DAQ files above inspected; JSON formatting equivalence checked read-only | Baseline observation, not proof of unimplemented behavior |
| 2026-10-26 | Provider/experiment spend for implementation verification: zero | Deterministic local commands and host-input tests only |
| 2026-10-26 | Independent design review approved the proposed draft; independent plan review approved after source-free import/specialization checks became explicit completion gates | Review of documents, not acceptance of a language-version amendment or implementation evidence |
| 2026-10-26 | New design/plan links, referenced existing owner paths, JSON examples and whitespace validated; all five changed documentation files pass link checking with explicit HTML anchors recognized | The stock link checker omits HTML anchors and reports three false positives on untouched references; those target IDs were verified present. No runtime tests run for this documentation-only change |
| 2026-10-26 | Task 2 completed as `37dcb9c0`; 99 host-input tests and 321 adjacent tests passed; independent specification and code-quality reviews approved | Exported prompt copies use the existing recursive canonicalizer, including collection/path names; private types cannot capture caller names. No runtime or persisted schema change |
| 2026-10-26 | Task 3 initial implementation as `faa73587`; 199 tests passed; public CLI compile/run passed for absent, empty and populated input documents; both reviews approved | Concrete argv is resolved at typechecking, and incomplete typed imports are refused before consumer inference |
| 2026-10-26 | Disposable full DAQ before/after compile: explicit form passed with 13 sites; abbreviated form exposed a nested-command propagation defect (`prepare` stable argv changed during closing) | Task 3 completion reopened; a portable regression and compiler correction are required. Live DAQ untouched |
| 2026-10-26 | Task 4 completed as `af09779e`; 197 changed/adjacent checks passed, including CLI/editor configuration capture and build-artifact selectors; both independent reviews approved | Envelope parsing constructs ordinary concrete bindings, preserves raw capture and validates every row; no runtime/schema path |
| 2026-10-26 | Task 3 reopened defect resolved as `9d4d2489`; 40 focused regressions and 372 related checks passed; independent specification and quality reviews approved | The existing typed match-subject path now retains materialized argv. Both full disposable DAQ copies compile with 13 sites; required concrete typed-export/closing gate is proved |
| 2026-10-26 | Task 5 completed as `6cd27f16`; new combined public CLI module: 10 passed in 29.40s with `-n 16 --dist=worksteal` | Public compile/run/get/answer/resume, operand order, no/empty/populated documents, shown/shared-file drift and restore, uncertain must-not-repeat refusal, committed replay |
| 2026-10-26 | Final fourteen-module regression (the Task 5 command above): 580 passed in 93.16s, exit 0 | Fresh aggregate against frozen maintained-example bytes; integrated independent code review ready with no regression issue. Pre-existing generic host composition limit is recorded in the report without expanding scope |
| 2026-10-26 | Maintained Lisp approval example now omits only prompt-declared host `:returns`; collect-only succeeded (26 cases), then `python -m pytest -q 'tests/test_workflow_host_input_e2e.py::test_public_cli_workflows_recover_typed_outcomes_once[APPROVED-lisp]'` — 1 passed in 11.22s | Fresh smoke after the example's source change; local recording stub, zero authenticated provider calls; dynamic argv stays explicit |
| 2026-10-26 | Same-format measurements captured in the [verification report](../reports/2026-10-26-frontend-deduplication-verification.md) | DAQ eight-file authoring total 789→750 lines and 38,028→36,849 bytes; portable fixture 95→97 lines and 3,023→2,987 bytes. This is compile/behavior/size evidence, not a quality comparison |
| 2026-10-26 | Task 6 contracts, guide, routing, selected example and verification report reconciled; three new JSON envelope examples parse, whitespace check passes, and all fourteen edited Markdown files pass relative-link/anchor checking with explicit HTML IDs recognized | Stock checker reports eight pre-existing HTML-anchor false positives across the expanded file set; no genuine link error. Independent documentation review and final integration remained pending at this checkpoint |
| 2026-10-26 | Independent final documentation review approved after explicitly documenting normal-import requirements for inferred answer types; fourteen edited Markdown files pass link/anchor checking and staged whitespace passes | No code change after the 580-test regression; the coordinator inspected the complete production and documentation diff |
| 2026-10-26 | Integrated reviewed feature tree `61c1a8ee` into local `main`; fresh integration set passed 293 tests in 43.23s, exit 0 | Host inference, command input documents, command closures, combined CLI recovery and maintained approval example; exact command in the report. All 29 pre-existing tracked changes remain unstaged and their diff payloads unchanged; live DAQ source/manifest hashes unchanged |

All selected tasks and closing gates are complete. Retain the implementation worktree and local logs as verification evidence; no remote push, live DAQ migration or additional experiment is selected.
