# Workflow Lisp REPL Introspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` when implementation is authorized. Execute the checkboxes in order; the coordinator integrates changes and owns final verification. The user has authorized execution of this plan; no merge or publication is included.

**Goal:** Add `:browse`, `:info NAME`, `:source NAME` and `:type EXPR` to inspect the loaded module's names, types, prompt contracts and authored source.

**Architecture:** Reuse the loaded frontend catalogs and ordinary expression typechecking. Retain the existing compiler module graph, final entry import scope and read trace's source snapshots in memory for origins/source; keep `:bindings` as captured run-local inspection. No new reflection subsystem, evaluator or durable format.

**Tech stack:** Existing Python frontend/CLI, standard library, pytest and tmux; no new dependency.

**Status:** Bounded implementation complete, with all tasks below executed and reviewed. The full suite remains red with explicit baseline and non-reproduction dispositions; this is not a claim of globally passing acceptance. Execution was authorized by the user on 2026-10-12 ("execute the plan"); no merge or publication is included.

**Authority:** [Introspection proposal](../design/workflow_lisp_repl_introspection.md), [parent REPL design](../design/workflow_lisp_repl.md), [current CLI contract](../../specs/cli.md#workflow-lisp-repl-targets-235-and-236), [capability matrix](../capability_status_matrix.md), [language principles](../design/workflow_language_design_principles.md), [test guide](../../tests/README.md) and repository `AGENTS.md`. Current commands remain governed by the CLI contract until the proposed additions are implemented and verified.

**Approach and tradeoffs:** Add a small presentation helper over existing semantic owners, and extract the frontend-only prefix of `evaluate_repl_expression` once. Retaining the compiler graph/import scope/source text costs session memory and couples origins to current compiler structures; source-free historical inspection, hot reload, editor integration and prompt rendering would require separate work.

**Excluded:** Completion/history, multiline, definitions, interactive effects, rendered prompt audit, runtime/persistence changes and broader type/equality semantics. Source means the loaded compiler snapshot, including freshly reconstructed attachment context; matching a semantic digest does not prove original-run source text.

## Reach and ownership inventory

All paths below are relative to the branch worktree root, `/home/ollie/Documents/agent-orchestration-repl`; do not execute from its sibling checkout.

| Files / existing owners | Planned reach |
| --- | --- |
| `orchestrator/workflow_lisp/workflows.py::ExpressionCompileContext`; its single constructor in `compiler.py::_compile_stage3_graph` | Retain the existing linked module graph and final entry import scope as defaulted transient fields, excluded from comparison/repr and serialization |
| `orchestrator/workflow_lisp/repl_expr.py::LoadedModule`, `evaluate_repl_expression`, `binding_type_refs` | Retain immutable source snapshots; extract ordinary parse/elaborate/normalize/typecheck into a shared frontend-only helper; preserve the evaluation entry point |
| New `orchestrator/workflow_lisp/repl_inspect.py` | Small deterministic browse/info/source projections and origin lookup from catalogs/graph; no independent semantic catalog |
| `orchestrator/cli/commands/repl.py::_load_module`, `_module_for_attachment`, `_dispatch` | Update both `LoadedModule` creation sites to keep their compile trace; add dispatch/help/output while preserving state transitions |
| Existing `reader.py::SourceReadTrace`, `type_env.py`, `functions.py`, `procedures.py`, `prompts.py`, `modules.py` | Reuse source bytes, type resolution, signatures, prompt declarations and graph identities; avoid changing their semantics |
| Existing `closed/{artifact,frontend}.py`, `workflow/evaluated/{capture,machine,views}.py` | Regression owners only; no intended format, build API, capture, evaluator or replay change |
| New `tests/test_workflow_lisp_repl_introspection.py`, `tests/test_workflow_lisp_repl_type_query.py`, `tests/test_workflow_evaluated_repl_introspection.py`; existing `tests/test_workflow_evaluated_repl.py` | Focused catalog/source/typechecking tests; public subprocess load/run/attach coverage using existing helpers and disposable fixtures |
| `specs/cli.md`, `docs/lisp_workflow_drafting_guide.md`, `docs/capability_status_matrix.md`, `docs/index.md`, `docs/design/README.md` | Publish verified command contracts, one author session and accurate availability/routing |
| `orchestrator/cli/main.py`, `orchestrator/cli/commands/__init__.py`, `orchestrator/workflow_lisp/__init__.py`, `pyproject.toml`, manifests | Inspect callers/exports/configuration; no new public Python export, CLI flag, entry point or configuration is needed |

Current source search finds one caller of `evaluate_repl_expression`, two constructors of `LoadedModule`, and one constructor of `ExpressionCompileContext`. Repeat that search before editing; preserve positional/default compatibility. Fixture manifests remain test-local. No production prompt files need revision.

Implementation/test preparation: bounded `impl_code_*` tasks use Luna 6 xhigh; revisions return to their author. Independent code/plan reviewers use Sol 6.1 high, independent design/spec reviewers Astra 6 xhigh. State role and artifact in every delegation. Escalate unbounded code work to Sol 6.1 high and architecture gaps to Design/Astra 6 xhigh. Reviewers must differ from authors; the coordinator personally inspects the complete diff and evidence.

## Task 1 — Establish reproducible feasibility and regression boundaries

**Files:** New `tests/test_workflow_lisp_repl_introspection.py`; read the owners above and existing closed-program tests. Production edits wait until these contracts are reproducible.

- [x] Reconfirm scope against the proposal and review its origin/visibility/output rules. Inspect all callers and current worktree changes:

  ```bash
  git status --short
  rg -n 'evaluate_repl_expression|LoadedModule\(|ExpressionCompileContext\(' orchestrator tests
  ```

- [x] Create a minimal disposable two-module fixture at targets 2.35/2.36, containing a local/imported record and enum, aliases and `:only`, a pure function/procedure, a workflow, a typed `defprompt`, and provider/prompt externs. Include a namespace collision. Reuse existing fixture/build helpers; no production workflow duplication.
- [x] Add `test_existing_introspection_substrate`: prepare a real build with `SourceReadTrace`; verify callable/prompt catalog resolution, record/enum metadata, imported identity/origin paths, graph form spans and normalized source slices. Include the compiler-visible qualified names beyond `:only`'s unqualified selections. Exercise source absence for a compiled-only external artifact where the existing build route permits it; do not synthesize missing source. Exercise ordinary frontend type/effect analysis of a valid effectful expression with lowering/evaluation guarded against calls; this proof uses existing APIs before the shared REPL helper is extracted.
- [x] Collect and run the bounded proof and existing digest/source tests:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_repl_introspection.py
  pytest -q tests/test_workflow_lisp_repl_introspection.py::test_existing_introspection_substrate
  pytest -q tests/test_workflow_lisp_closed_program_compile_cli.py::test_build_key_is_portable_and_raw_source_bytes_stay_out_of_program_digest tests/test_workflow_lisp_closed_program_compile_cli.py::test_build_key_uses_the_compiler_retained_source_snapshot
  ```

  Expected: collection succeeds and substrate/source assertions pass on existing production semantics. Unsupported graph/name/source coverage is a design gap, not permission to invent a resolver. Return any gap to Design before dependent implementation.

- [x] Record bounded proof results and obtain independent plan/design review. A prior read-only probe established ordinary recipe reconstruction, matching program digest, two traced sources, a resolved `revise-plan` declaration and a correctly bounded prompt slice; it did not establish the complete new feature or imported-name coverage. Reproduce required coverage with fixtures, not a private run ID.

## Task 2 — Retain loaded provenance and implement module queries

**Files:** `workflows.py`, `compiler.py`, `repl_expr.py`, new `repl_inspect.py`; focused test module.

- [x] Add failing behavioral tests under `-k 'catalog or source_snapshot'`: enumerate supported kinds/origins deterministically; resolve every visible spelling to ordinary catalog facts; emit every namespace candidate; preserve aliases and omit generated/private implementation names according to the design.
- [x] Test record fields, union variants, enum members, path constraints, primitive identity, callable signatures/available effects and prompt slot kinds/refinements/output roles/return contracts, plus provider/prompt extern declarations. Preserve declaration order within contracts and deterministic kind/name ordering; deduplicate aliases by canonical identity. Unknown names and unavailable authored source must follow the proposal's distinct diagnostics. Extern source must never dereference a prompt asset or provider implementation.
- [x] Test exact authored form slices from fixture-owned text, including non-ASCII, CRLF/CR normalization and multiple forms on a line. Load, then edit/remove the original file; source inspection must still return the captured text. Missing graph/span/snapshot must refuse cleanly. Validate every namespace match before output; if any source is unavailable, report all unavailable matches and print no partial source. Assert lineage and fixture slices, never literal production prompt wording.
- [x] Run `pytest -q tests/test_workflow_lisp_repl_introspection.py -k 'catalog or source_snapshot'` and confirm failures are missing behavior.
- [x] Add optional transient references to the existing `LinkedModuleGraph` and final entry `ModuleImportScope` on `ExpressionCompileContext`; populate its one compiler construction site. Store `SourceReadTrace.raw_bytes_by_path` and its revision vector on `LoadedModule`; preserve existing constructor compatibility with defaulted transient metadata.
- [x] Implement only the needed catalog-to-display functions in `repl_inspect.py`. Existing catalogs/resolvers and the final entry import scope choose visible/resolvable names; the graph supplies authored owners/spans. Do not reconstruct import scope from pre-expansion graph exports, which can lose expanded visibility. Reuse `render_type_ref` and existing metadata. Do not repurpose the incomplete LSP `authored_symbols` index as semantic authority, flatten imports into a competing registry, or parse source with regexes.
- [x] Rerun the selector and source/digest regressions from Task 1. Expect all pass; serialized artifacts, manifests and semantic digests must remain unchanged. Keep each new module below the parent design's 500-line bound.

## Task 3 — Extract type-only expression analysis

**Files:** `repl_expr.py`; new `tests/test_workflow_lisp_repl_type_query.py` reusing the focused catalog fixture; existing REPL regression module.

- [x] Add failing `-k type_query` cases for module-only literals/calls, quoted strings/escapes, multiple-datum errors, imported names, attached lexical values/shadowing and ordinary type errors. Include an accepted effectful procedure expression whose type can be queried and a pure expression whose captured-dependent divisor is zero at runtime and must not run. Literal constant division by zero retains the ordinary frontend constant-fold diagnostic.
- [x] Guard the boundary in focused tests: replace lower/evaluate entry points with fail-on-call sentinels during the type query and compare builder definitions/type state before/after. Effects may be analyzed; no builder preparation, lowering, provider invocation or closed evaluation is allowed.
- [x] Run `pytest -q tests/test_workflow_lisp_repl_type_query.py -k type_query`; confirm the missing feature fails.
- [x] Extract the existing parse → elaborate → function normalization → `typecheck_expression` prefix into one helper accepting optional captured bindings. Keep target branching, catalogs/resolvers and diagnostics intact. Return the typed result and the environments the evaluation continuation already needs; do not add a second parser/typechecker or new intermediate class solely for this tuple.
- [x] Make `evaluate_repl_expression` call that helper, then retain all three existing purity/lowering/evaluation guards and its current signature. Type queries stop before the purity refusal so effectful analysis succeeds without execution. Missing lexical names retain ordinary `name_unknown`; synthesized runtime variant-case values still supply no invented frontend proof.
- [x] Rerun the type selector and `pytest -q tests/test_workflow_evaluated_repl.py`. Expect new analysis tests and existing pure-call/effect-refusal/list-emptiness behavior to pass unchanged.

## Task 4 — Wire commands and prove public behavior

**Files:** `cli/commands/repl.py`, new `tests/test_workflow_evaluated_repl_introspection.py` reusing existing public helpers; the maintained smoke stays in `tests/test_workflow_evaluated_repl.py`.

- [x] Add `test_public_repl_module_introspection` and `test_public_repl_attached_introspection` at both targets. Use real subprocess `python -B -m orchestrator repl`, ordinary build/run services and current provider executable stand-ins. Cover no-module refusals, module-only queries, successful lookup, bad arity/unknown names and recovery to later commands.
- [x] Add a public `:type` case containing spaces, escaped quotes and Lisp string syntax. Dispatch its raw remainder before `shlex.split`; the ordinary reader owns expression syntax. Parse `:info` and `:source` arguments as exactly one reader symbol; reject strings/lists or extra datums. Retain existing shell-style parsing for `:load` and `:run`. Empty/multiple expressions use the proposal's documented diagnostics.
- [x] Add public snapshot/state tests: failed load keeps previous introspection data; compatible/digest-mismatched load or attach follows old state transitions; recipe-only attachment reconstructs provenance without publishing build cache. A source-comment-only rebuild may match the program digest while presenting newly loaded text; output must label the loaded snapshot rather than historical run source.
- [x] Collect both changed modules, then run new public cases before implementation:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_repl_introspection.py tests/test_workflow_lisp_repl_type_query.py tests/test_workflow_evaluated_repl_introspection.py tests/test_workflow_evaluated_repl.py
  pytest -q tests/test_workflow_evaluated_repl_introspection.py
  ```

- [x] Retain the named compile trace at both `_load_module` and `_module_for_attachment` construction sites; publish the new module only after successful compilation/attachment checks. Add four dispatch branches, exact argument checks, stable rendering and `:help` entries. Type output is `type: <rendered type>` then `effects: <rendered effect set>`; use existing renderers. Help/browse enumerate the six supported kind families and exclusions. Source output identifies explicit-load versus recipe-reconstructed snapshots. Preserve `:bindings`, `:result`, ordinary expression output and EOF/error behavior.
- [x] Prove read-only behavior by hashing run authority/memo/views/attempts and provider request logs before/after successful/refused queries, including querying while the ordinary writer lock is held. Compare module-only workspace snapshots after the initial load to exclude legitimate existing build publication. Check no in-memory builder/captured-frame mutation.
- [x] Rerun new public cases, then both full owner modules. Expect all pass. A deterministic provider stand-in proves integration, not live provider qualification.

## Task 5 — Publish the verified contract and inspect compatibility

**Files:** `specs/cli.md`, `docs/design/workflow_lisp_repl.md`, drafting guide, matrix/hub/design index listed above; design/plan only for accepted corrections and evidence records.

- [x] Update the CLI command table, preconditions, outputs, diagnostics and read-only guarantees from the implemented proposal. Explain module queries versus run bindings, effectful type analysis versus pure execution, and loaded source versus historical source.
- [x] Add one reproducible author session using a maintained module with its actual required manifests. Use current helper names and supplied fixture values; do not promise completion, fully rendered prompts, archived source or all language namespaces.
- [x] Update availability only for behavior supported by evidence; keep design status separate. Link the design/plan without selecting unrelated roadmap phases. Validate relative links and example commands against the public tests.
- [x] Independent code review checks shared frontend analysis, name/origin fidelity, error-state preservation and no writes/effects; independent design/spec review checks scope, source qualifications and docs against behavior. Apply accepted corrections through the appropriate revision role and rerun affected checks only when changes invalidate evidence.

## Task 6 — Required integration, smoke and final verification

**Files:** Changed tests; existing regression owners; evidence appended here or a linked execution record. All commands run from the worktree root. Read `tmux` skill before long commands; place broad/slow suites in tmux with the required parallel flags.

- [x] Run focused collection/owner suites and narrow source/build parity tests first. Retain command, revision, exit code and output:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_repl_introspection.py tests/test_workflow_lisp_repl_type_query.py tests/test_workflow_evaluated_repl_introspection.py tests/test_workflow_evaluated_repl.py
  pytest -q tests/test_workflow_lisp_repl_introspection.py
  pytest -q tests/test_workflow_evaluated_repl.py
  pytest -q tests/test_workflow_lisp_build_in_memory.py::test_read_only_build_matches_persistent_prefix_without_mutating_workspace
  pytest -q tests/test_workflow_lisp_closed_program_compile_cli.py::test_build_key_is_portable_and_raw_source_bytes_stay_out_of_program_digest tests/test_workflow_lisp_closed_program_compile_cli.py::test_build_key_uses_the_compiler_retained_source_snapshot
  ```

- [x] Prepare `test_public_repl_introspection_smoke` in the existing public test module: copy maintained `workflows/examples/plan_review_execute.orc`, its imported sources and declared manifests into a disposable workspace; invoke public run with deterministic provider replies, then public REPL browse/info/source/type/old bindings/result. Assert result/type facts, fixture source lineage and unchanged evidence/provider request hashes. This is the required execution smoke and usage integration, additional to unit checks; compilation alone is insufficient.

  ```bash
  pytest --collect-only -q tests/test_workflow_evaluated_repl.py
  pytest -q tests/test_workflow_evaluated_repl.py::test_public_repl_introspection_smoke
  ```

- [x] Run affected regressions in tmux; retain exit/output. Add another owner only if implementation changes or a finding makes it relevant:

  ```bash
  pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_source_read_trace.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_prompt_calculus.py tests/test_workflow_lisp_closed_program_compile_cli.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_resume.py
  ```

- [x] Run the required broad non-E2E campaign in tmux:

  ```bash
  pytest -q -n 16 --dist=worksteal -m "not e2e"
  ```

  Expected: all selected tests pass, or every failure has an explicit evidence-backed disposition. Do not weaken checks, treat historical baseline outcomes as current evidence, or describe a red campaign as passing. Live-provider E2E remains unverified by deterministic smoke.

- [x] Coordinator inspects `git diff --check`, `git diff --stat` and the full changed-file diff plus fresh test evidence. Obtain final independent code and design/spec reviews; verify there are no added artifact/schema/header keys, dependencies, public exports or launch paths. No merge or publication is part of this bounded implementation.

## Stop or revise

Return to Design if exact visible names/origins require a competing resolver, source requires disk rereads or persisted archives, type analysis requires lowering/evaluation, or original REPL behavior cannot be preserved through the shared frontend helper. Keep missing source distinguishable from unknown names; never print fabricated authored source. Do not expand this task into LSP, completion, effect execution or runtime changes.

## Evidence record

Preparation inspected current source, callers, routing and existing tests. The original read-only reconstruction/prompt-span probe established feasibility only. Execution was subsequently authorized; the checkpoints below record fresh checks and the limits of each completed task.

Draft review, 2026-10-12: independent design and plan reviews found no material issues. The plan review's minor inventory-path correction was applied. Preparation checks passed for 24 local links/anchors, new-document whitespace, draft status and `git diff --check`. These checks do not satisfy Task 1 or implementation acceptance.

### Execution checkpoints

- Task 1: `pytest --collect-only -q tests/test_workflow_lisp_repl_introspection.py` collected 2 cases; `pytest -q tests/test_workflow_lisp_repl_introspection.py::test_existing_introspection_substrate` passed 2 cases (1.52s). Independent specification and test-quality review: PASS. The proof uses the real `frontend_only`/`legacy` compile route; production closed-build retention is still a Task 2 obligation. Source-less extern metadata is covered; compiled-only external-source absence was not demonstrated.
- Initial existing controls: the two planned build-key/source-snapshot selectors passed (5.24s); `pytest -q -n 16 --dist=worksteal tests/test_workflow_evaluated_repl.py` passed all 16 existing cases (8.87s). Logs: `/tmp/orc-repl-introspection/`.
- A clean baseline at `a761b1c62bb2e492eb30e9f03bbe416468ce31b0` runs the full non-E2E campaign in a disposable detached worktree, independently of implementation edits. It completed with exit 1: 221 failed, 23,542 passed, 7 skipped and 172 xfailed (1605.99s). Raw log/XML and extracted failure identities are retained as `baseline-full.*` and `baseline-failures.json` under `/tmp/orc-repl-introspection/`; these are comparison evidence, not a green result.

- Task 2: production closed-build catalog/source coverage collected and passed 18 cases at targets 2.35/2.36 (3.43s). The planned source/digest controls plus 16 existing REPL cases passed (18 total, 146.70s). Independent compliance and quality review: PASS. Source edge tests include shifted spans, immutable captured bytes, aliases/private names, namespace collisions and all-or-nothing refusal. Specialization filtering is tested with retained typed facts; no new macro-generated fixture was added. Logs: `/tmp/orc-repl-introspection/task2-*.log`.

- Integration refinement: type-analysis cases and public command/state cases use two small sibling test modules, reusing the original fixtures/helpers; this keeps the catalog test module focused and avoids fixture duplication. The maintained-example smoke remains in the existing public REPL owner.

- Task 3: new type-query module collected/passed 8 cases; focused catalog/query collection found 26 cases. The two focused modules plus the original public REPL suite passed 42 cases under tmux/xdist (22.26s, exit 0). Independent compliance and quality review: PASS. Constant division by zero retains the ordinary frontend diagnostic; the no-evaluation proof uses a captured-dependent zero divisor. Logs: `/tmp/orc-repl-introspection/task3-*.log`.

- Task 4: public owner collection found 26 cases; all 26 passed under tmux/xdist (13.48s, exit 0), including the maintained-example smoke with four deterministic provider replies, both targets, source lifecycle, digest state transitions, recipe-only rebuild and evidence preservation under a writer lock. Independent compliance and quality review: PASS. Logs: `/tmp/orc-repl-introspection/task4-*.log`.
- Coordinator integration controls: all four changed test modules collected 52 cases (exit 0); read-only build plus source/digest controls passed 3 cases (5.39s). A separate public CLI attachment to the motivating existing run `20261013T014512Z-5875dy` successfully browsed/inspected Plan and revise-plan, printed reconstructed source, and typed revised.steps as List[String]; 13 run files retained identical SHA-256 hashes, exit 0 and empty stderr. Receipt: `/tmp/orc-repl-introspection/user-run-inspection.json`. No providers were invoked by this attachment.

- Final affected campaign: all four REPL test owners plus source-read trace, modules, functions, prompt calculus, closed-program CLI, evaluated CLI/views/providers/resume passed 445 cases with `pytest -q -n 16 --dist=worksteal` in tmux (76.13s, exit 0). Evidence: `/tmp/orc-repl-introspection/final-affected.{log,xml,exit}`. The required final full non-E2E campaign completed with exit 1: 239 failed, 23,561 passed, 7 skipped and 171 xfailed (2278.22s). All 52 cases in the four REPL owners passed. Raw evidence: `/tmp/orc-repl-introspection/final-full.{log,xml,exit}`; final failure dispositions are below.

- Task 5 documentation checks: the maintained guide load plus five module queries passed in a disposable workspace; its attachment command sequence passed against a public shim-backed run, preserving evidence and request hashes. Both exits were 0 with empty stderr. The author validated 96 scoped links/anchors and whitespace. Logs: `/tmp/orc-repl-introspection/task5-guide-{load,attach}.{log,exit}`. Independent final code and design/spec reviews are PASS. The design reviewer validated 53 added links/anchors and the relevant receipts; its one finding was a stale proposed-status label in the design index, corrected by the coordinator. These reviews do not claim a green full suite.


### Baseline failure triage

The clean-baseline campaign's 221 failures are not a green acceptance result. While the final campaign was running, the coordinator and an independent reviewer inspected their traces and governing fixtures:

- 194 experimental ES failures: 110 enter a stale synthesis fixture without the required `evaluation_hooks` table; two fixture builders look for retired clause `F1-H09-CONSTRUCTION-REBUILD-EQUALITY` while the authority now supplies `F1-H09-CROSS-SURFACE-COHERENCE`; 72 reject the pinned bwrap identity (67 boundary-proof, three projection and two lifecycle cases); eight reject the installed Codex launcher/version; two reject an invalid feasibility worker response. These paths are unchanged by this feature.
- 27 other failures: four nanoBragg fixtures lack a sibling C source in the clone; five tracked-run checks depend on absent `.orchestrate` evidence or the original canonical workspace path; ten checkpoint/observable comparisons have pre-existing expectation mismatches; six run-ref/watcher cases exceed marker/state deadlines; one provider-isolation check detects a changing `/tmp` path-component identity; one result-freshness case never observes its marker. A timeout alone does not establish its ultimate cause.
- A preventive rerun of the two historically cached runtime-persistence selectors passed (2 passed, 3.23s; `baseline-active-runtime.{log,xml,exit}`). Cached `lastfailed` entries were explicitly excluded from the current-campaign failure inventory.

These groups describe the fresh baseline only; the final comparison below accounts separately for the current campaign.


### Final campaign comparison

The final suite is **red**, not accepted as a globally passing suite. Comparing JUnit identities gives 212 failures also seen in the clean baseline, 27 additional failures and nine baseline failures not repeated. All 36 newly added cases pass; the four changed REPL owners contain 52 passing cases in total.

The exact 27 additional selectors were rerun with `pytest -q -n 16 --dist=worksteal` in tmux: **26 passed, one xfailed**, exit 0 (55.60s). The `xfail` is the existing F50 late-refusal watchdog case; its earlier failure occurred before its expected-failure boundary, explaining 171 versus 172 xfails in the full campaigns. No assertion, timeout, marker or production code was changed. An initial narrower collection had three import errors; its log is retained separately. The successful rerun explicitly pins `PYTHONPATH` to the worktree and logs the imported package's origin.

The 27 initial failures cover watchdog/usage-limit deadlines, subprocess startup/exit deadlines, cancellation/ingress shutdown, mutable directory-identity checks and two spike-trial comparisons. Their targeted success establishes non-reproduction, not a proven environmental root cause for every case; the two spike outcomes and suppressed isolation child exception remain unexplained. Evidence is retained in `unmatched-selectors.json`, `unmatched-current-pinned.{log,xml,exit}`, `failure-comparison.json` and `failure-dispositions.json` under `/tmp/orc-repl-introspection/`.

Thirteen shared failure messages differed between worktrees. Ten differ only in runtime timestamps, temporary paths, or which tracked-evidence path is absent. Three generated-identity/snapshot cases received additional baseline-code/current-source controls; their final results are recorded below. Independent review confirmed that legacy specialization identities include source paths in type/expr representations; the full-suite message differences alone cannot establish a compiler regression.


The three generated-identity cases are now disposed by paired controls. Baseline compiler code against the current test/source paths reproduced the WCC message exactly (`same-path-baseline.*`: three expected failures, 38.09s). The two checkpoint hashes initially still differed because both `modules.resolve_module_graph` and `compiler._builtin_stdlib_source_root` choose built-in source paths. A process-local control pinned both source-directory selections to the current worktree while retaining baseline compiler code; both failures and actual hashes then matched the current-code control exactly (`same-path-pinned-baseline.*`: two expected failures, 36.15s; `same-path-current.*`: two failures, 50.39s). The intermediate partial-path controls are retained for transparency. No repository source was changed for these probes, and no failing assertion was weakened.

Final integration: the coordinator inspected the code, tests, documentation, changed-file inventory and fresh receipts; independent final code and design/spec reviews passed. The scope is the 17 planned files, including this plan and the accepted design. Tested production/test file hashes are recorded in `/tmp/orc-repl-introspection/tested-code-hashes.json`. Three generated `.tmp/omp-fake-launcher` files were removed from the feature worktree; the disposable baseline worktree and the six private verification tmux sessions were removed after the comparison; raw receipts remain under `/tmp/orc-repl-introspection/`. No artifact/schema/header keys, dependencies, public exports or launch paths were added. At bounded implementation closeout, changes were uncommitted in `feature/orc-repl`; no merge, publication or live-provider E2E had been performed. The user subsequently authorized local integration into `main`, preserving its uncommitted work; that integration is a separate verification step. The maintained deterministic smoke proves public run/attach/inspection integration; the unresolved broad-suite flakes and existing failures remain a validation limit.

Independent final evidence review: PASS. The reviewer checked all 239 failure dispositions, the 27-selector rerun, the F50 xfail accounting and all three paired identity controls; no material finding remained. This review found no evidence of an introspection regression and explicitly retained the global red-suite and unproven transient-root-cause limits.
