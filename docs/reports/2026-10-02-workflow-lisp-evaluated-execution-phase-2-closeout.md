# Workflow Lisp Evaluated Execution — Phase 2 Closeout

**Status: Phase 2 compiler closeout complete and integrated under the agreed Critical-only gate.** Production verification candidate: `d4f0e0f438bc012182bf12ca027f2f807932ac97`; comparison base (`PHASE2_BASE`): `2e4c7a653d74c06e24c15c284662e5914abd5576`. A subsequent test-only caller repair is `17049e79051fda461f3dd20864c85fb740f96958`; its focused verification is recorded below. The completed full suite is red, not a full-suite PASS.

Named coordinator reports and receipts below are machine-local evidence under `/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan/`. Raw `/tmp` paths identify retained execution evidence; this report does not imply that these machine-local files are versioned or portable.

Phase 2 delivers the compiler for target **2.35**. Public `orchestrator compile` produces and validates `closed_program.json` and its `manifest.json`: a calculus-only table of reachable definitions, complete admitted effect nodes, canonical configuration and types, sites, provenance outside identity, and a program digest. The schema is `workflow-lisp/closed-program/1`, representation `table/1`.

**Target 2.35 is compile-only.** Public `run` and `resume` still refuse with `evaluated_execution_unavailable`. The evaluator, effect memo, runtime closure enforcement, performers, coordinator integration and runtime state/readers remain Phase 3 work. Compiler evidence does not establish runtime parity or recovery behavior. Runnable authored workflows continue to use supported targets through 2.34.

The [Phase 2 plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#status-authorities-and-scope) owns the delivery and closeout requirements; the [accepted design](../design/workflow_lisp_evaluated_execution.md) owns behavior. The [parent plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities) owns downstream selection and order. The historical spike remains separate evidence.

## Integrated Tasks And Compiler Evidence

All eleven tasks have been individually reviewed and integrated in the candidate. Their review gates do not replace the final phase-wide checks.

| Tasks | Delivered surface | Main evidence owner |
| --- | --- | --- |
| 1 | One target gate, 2.35 registration and public run/resume refusal | `tests/test_workflow_lisp_target_evaluated_execution.py` |
| 2–3 | Public typed graph admission without flat lowering; retained imported snapshots; target-specific elaboration of arguments, control values, contexts and callees | `tests/test_workflow_lisp_closed_program_frontend.py`; `tests/test_workflow_lisp_closed_program_elaboration.py` |
| 4–7 | Closed builder/table, value and capture routing, checked normal form, sites/call frames, path-free canonical identities, artifact/readback/digest, explicit command closure declarations | `tests/test_workflow_lisp_closed_program_build.py`; `tests/test_workflow_lisp_closed_program_sites.py`; `tests/test_workflow_lisp_closed_program_check.py`; `tests/test_workflow_lisp_closed_program_names.py`; `tests/test_workflow_lisp_closed_program_artifact.py`; `tests/test_workflow_lisp_command_boundary_closure.py` |
| 8–9 | Portable composed-provider subset, path run references and located release gaps; public artifact publication, build identity and imported producer configuration | `tests/test_workflow_lisp_closed_program_effects.py`; `tests/test_workflow_lisp_closed_program_compile_cli.py` |
| 10 | Exact 52-export corpus, control/admission matrix, source-free typed/restored import cases and static P3 carrier comparison | `tests/test_workflow_lisp_closed_program_corpus.py`; `tests/workflow_lisp_closed_program_p3.py`; expanded frontend/context/names/build/CLI tests |
| 11 | Availability, closure and identity documentation; current routing; correction of stale Q2 selection checks | `task-11-spec-review.md`; `task-11-quality-review.md`; `tests/test_workflow_lisp_drain_roadmap_routing.py` |

Task 10's original corpus run at `040ef78a` recorded **107 passed in 31.36 s**, exit 0 (`/tmp/task10-corpus-final-exit.log`, `.exit`); its effects module recorded **31 passed**, exit 0 (`/tmp/task10-effects-full.log`, `.exit`). Follow-up test-only repairs added the maintained old-bundle/private-enum and omitted-DrainCtx controls (54 frontend cases collected; six affected checks passed) and corrected two `repeat` assertions to the implemented `never` value (three affected checks and the true-branch public compile/readback comparison passed). Original failing reviews and RED logs remain preserved; final Task 10 formal and quality judgments passed. These are recorded historical commands, not newly executed by this report's author.

The Task 10 parent receipt records **53 independently run semantic probe groups**, all passed. Task 11's required serial modules recorded **157 passed, 2 xfailed** in total (routing 71, monitor 1, guide 85); the checker resolved **772 relative links across eleven documents**, with no broken file destinations. Five newly relevant headings/anchors and Q2/PC-1 navigation have separate evidence. This link result is scoped, not a repository-wide anchor audit. Task 11 formal and quality reviews both passed at `3d4c2514`; the prior IO compatibility wording finding was repaired in that candidate.

## Exact Shipped Export Corpus

The following table is transcribed from `EXPECTED` in [the maintained corpus test](../../tests/test_workflow_lisp_closed_program_corpus.py), without importing or executing the test module. The exact partition is **37 Built / 10 Gap / 4 Refused / 1 NotSynthesizable**, totaling **52 unique exports**. A Built row lists static `perform` sites, not dispatch count. Repeated calls/loop activations can reuse one local site. Every Built case validates, checks its perform/site correspondence, and strictly reads back the same tree, sites and digest in the maintained test.

| Export | Pinned result | Sites |
| --- | --- | ---: |
| `experiments/mlevolve_pair/probes/malformed_result.orc::run` | Built | 1 |
| `experiments/mlevolve_pair/probes/missing_bundle.orc::run` | Built | 1 |
| `experiments/mlevolve_pair/search.orc::run-search` | Built | 12 |
| `experiments/mlevolve_pair/search_compact.orc::run-search` | Built | 6 |
| `experiments/orc_vs_single_call/task/bug_report/reviewed_change.orc::reviewed-change` | Built | 4 |
| `experiments/orc_vs_single_call/workflows/best_of_n.orc::best-of-n` | Built | 2 |
| `experiments/orc_vs_single_call/workflows/best_of_n.orc::select-only` | Built | 1 |
| `experiments/orc_vs_single_call/workflows/reviewed_change.orc::reviewed-change` | Built | 4 |
| `workflows/examples/cycle_guard_demo.orc::cycle-guard-demo` | Built | 1 |
| `workflows/examples/design_plan_impl_review_stack_v2_call.orc::design-plan-impl-review-stack` | Built | 6 |
| `workflows/examples/effectful_let_star_normalization.orc::run-effectful-let-star-normalization` | Built | 4 |
| `workflows/examples/effectful_match_arm_normalization.orc::run-effectful-match-arm-normalization` | Built | 3 |
| `workflows/examples/improve_experiment_proposal.orc::run-experiment` | Built | 3 |
| `workflows/examples/kiss_backlog_item.orc::run-backlog-item` | Built | 7 |
| `workflows/examples/review_revise_design_docs.orc::review-revise-design-docs` | Refused: `workflow_signature_mismatch` | — |
| `workflows/examples/review_revise_design_docs_judgment_panel.orc::review-revise-design-docs-judgment-panel` | Built | 2 |
| `workflows/examples/review_revise_parametric_design_docs.orc::review-revise-parametric-design-docs` | Refused: `macro_arity_error` | — |
| `workflows/examples/same_file_record_call_binding.orc::run-same-file-record-call-binding` | Built | 1 |
| `workflows/examples/with_phase_composed_binding.orc::run-with-phase-composed-binding` | Built | 1 |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::design-qa` | Built | 4 |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::direct` | Built | 1 |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::product-qa` | Built | 3 |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::rich` | Built | 6 |
| `workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc::compare` | Gap: `trial` | — |
| `workflows/experiments/repository_task_pilot/task_loop.orc::run-task` | NotSynthesizable: command 'pilot_product_manifest' is parameterized by workflow input 'controller_script', whose concrete script path, source bytes, and closure are missing | — |
| `workflows/library/control/direct_task.orc::direct-task` | Built | 1 |
| `workflows/library/design_plan_impl_implementation_phase.orc::design-plan-impl-implementation-phase` | Built | 2 |
| `workflows/library/generic_run_watchdog/watchdog.orc::watchdog` | Built | 5 |
| `workflows/library/lisp_frontend_design_delta/bootstrap.orc::project-work-item-inputs` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::draft-design-gap-architecture` | Built | 1 |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::draft-design-gap-architecture-stdlib` | Built | 1 |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::project-design-gap-architecture-targets` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::project-design-gap-architecture-targets-stdlib` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::validate-design-gap-architecture` | Gap: `materialize-view` | — |
| `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::validate-design-gap-architecture-stdlib` | Gap: `materialize-view` | — |
| `workflows/library/lisp_frontend_design_delta/drain.orc::drain` | Refused: `provider_bundle_path_target_invalid` | — |
| `workflows/library/lisp_frontend_design_delta/implementation_phase.orc::implementation-phase` | Gap: `materialize-view` | — |
| `workflows/library/lisp_frontend_design_delta/plan_phase.orc::run-plan-phase` | Gap: `materialize-view` | — |
| `workflows/library/lisp_frontend_design_delta/projections.orc::classify-work-item-terminal` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/projections.orc::project-selector-action` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc::run-runtime-transition-fixture` | Gap: `resource-transition` | — |
| `workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc::run-summary-view` | Gap: `resource-transition` | — |
| `workflows/library/lisp_frontend_design_delta/selector.orc::select-next-work` | Refused: `provider_bundle_path_target_invalid` | — |
| `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc::project-selected-item-payload` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc::project-selection-result` | Built | 0 |
| `workflows/library/lisp_frontend_design_delta/transitions.orc::apply-drain-status-transition` | Gap: `resource-transition` | — |
| `workflows/library/lisp_frontend_design_delta/transitions.orc::emit-drain-status-transition-audit` | Gap: `resource-transition` | — |
| `workflows/library/lisp_frontend_design_delta/work_item.orc::classify-blocked-implementation-recovery` | Built | 1 |
| `workflows/library/lisp_frontend_design_delta/work_item.orc::run-work-item` | Gap: `materialize-view` | — |
| `workflows/library/tracked_design_phase.orc::tracked-design-phase` | Built | 2 |
| `workflows/library/tracked_plan_phase.orc::tracked-plan-phase` | Built | 2 |
| `workflows/library/verified_iteration_drain/drain.orc::drain` | Built | 9 |

The two inherited source refusals are `workflow_signature_mismatch` for `review_revise_design_docs` and `macro_arity_error` for its parametric counterpart. The selector and design-delta drain pass at their original target but refuse at 2.35 under the documented X4 provider-bundle root rule, with `provider_bundle_path_target_invalid`. These outcomes are distinct from the ten located `closed_program_gap` effect-class exclusions and from missing harness inputs. See `task-10-corpus-refusal-pairs.md` in the coordinator evidence directory for the paired checks.

## Admission And Evidence Limits

Admitted compilation includes external-tool and certified-adapter commands, portable composed providers without context capture, `asset_file`/`input_file` and the admitted prompt slots, procedure/workflow calls, value/reference bindings, `bind-proc` captures, bounded local procedures, and path-mode run references. The maintained matrix covers twelve admitted control cases through direct, same-module helper and imported-old-source helper routes. Source-owned restrictions still refuse an effectful loop exhaustion expression or an effectful `list/map` body. A defect in an admitted composition was repaired, not recategorized as a release gap.

Excluded first-release effects still refuse with source location and `closed_program_gap`: materialized views, resource transitions, trials, human-input requests, phased/supervised providers, provider context capture, and bundle-mode run references. Corpus gap counts are an inventory of encountered exports, not a complete count of excluded language forms.

The corpus preparation copies source roots into scratch, retargets the entry and preserves imported producer targets and manifests. Providers/prompts/commands can be supplied or synthesized for compile-only evidence. The real implementations and explicit closures from the nine audited manifests are preserved where available, including the materializer's neighboring import and package-owned command declarations. The absent `launch_experiment` implementation and `run_checks` receive explicitly identified executable stand-ins; missing prompts may be empty compile-only files. A coordinator script that accepts dynamic checks or script inputs does not thereby close those selected implementations. The pilot export remains NotSynthesizable because `controller_script` lacks its concrete script path, source bytes and closure. None of these preparations proves real launcher, provider, command or prompt runtime behavior.

Static P3 evidence compares the flat carriers and closed nodes for `improve_experiment_proposal` (five flat occurrences → three sites), `reviewed_change` (four → four), and `best_of_n` (two → two), plus source-kind/document/dependency/nominal fixtures. It checks contracts, guidance/refinements, renderer/slot order and kinds, typed inputs, dependencies, provider policy/configuration scope, and command argv/document/signature/closure/repeat facts. The comparator intentionally removes only R3's transport output `path` and named diagnostic/source-map provenance, and resolves nominal names through retained owners without collapsing homonyms. Full executor-free prompt assembly and public runtime/recovery agreement remain Phase 3 obligations.

C1 requires explicit closure for every supplied command binding, including unused declarations, and every used injected binding. Compilation normalizes logical closure declarations but reads or hashes no closure bytes. Runtime closure byte hashing, symlink/enforcement rules, interpreter pinning, retry checks, output disjointness and caches outside closure remain Phase 3. At older targets, valid closure is omitted from binding serialization/effect identity; editing the raw manifest can still change the build-cache key.

## Final Legacy Compatibility: Authentic Pins And Controlled Inputs

Fresh compatibility checks ran against integrated `d4f0e0f4`, with the actual Phase 0 `PHASE2_BASE`; historical `613993ad` is not this comparison base. The method uses fixed source/package paths, `PYTHONHASHSEED=0`, raw artifacts and independent rehashes, following the plan's Global Constraints.

| Comparison | Fresh recorded result | Meaning |
| --- | --- | --- |
| Four legacy public-CLI specimens: `kiss-2.14`, `panel-2.23`, `improve-2.33`, `fixture-2.34` | Eight successful compile exits; **88 raw artifact pairs equal**, with equal build keys; 176 independently rehashed rows | Byte equality for these specimens under their actual inputs |
| Compiled-import/nested run-ref capsules with authentic package pins | **55 of 67 raw pairs equal; 12 different**, 134 rehashed rows; `actual.exit=1` | Not a real-pin byte-equality pass |
| Capsule serialization control using the existing identity-provider seam (`sha256:` plus 64 `c` characters) | **All 67 raw pairs equal**, 134 rehashed rows; `fixed.exit=0` | Controlled serialization proof, not equality of authentic pins |

Authentic compiler runtime pins are base `sha256:35bae1c1335e9496e395d5bde9127516f5fdc0f03b2d8a74831286689498f83a` and candidate `sha256:56cd4cb3d02ae409ec2d6e236bab6413cd7d64e7bfd125249482f47f1e3f7270`. The twelve differences are run-ref-dependent: build `core_workflow_ast.json`, `executable_ir.json`, `lexical_checkpoint_points.json`, `lowered_workflows.json`, `run_ref_bundle_capsule.v1/bundles.pkl`, `run_ref_bundle_capsule.v1/manifest.json`, `runtime_plan.json`, `semantic_ir.json`, `source_map.json`, and exported `bundles.pkl`, `capsule-digest.txt`, `capsule-manifest.json`.

The actual graph check passed for **1,257 object pairs**, 37 state layouts and 26 scalar differences, limited to the compiler pin and derived identity fields. The layout check covered all nine renamed checkpoint state rows; remaining payload fields matched. The JSON diff showed corresponding pin/derived identity changes. Artifacts were not normalized and the authentic pin was not weakened. The wrapper's exit 0 does not override the actual comparison's exit 1.

`phase2-final-compatibility-d4f0e0f4.md` records commands, inputs and results. `phase2-final-parent-rehash-d4f0e0f4.json` records the parent's **444 independent artifact rehashes** (176 legacy + 134 actual + 134 fixed), with manifest SHA-256 values `ebc6df299187d919436ad559d7aac84b826e9ae2576cf2b31eb49d2b1ecb97e5`, `60f1e573ec000e6bb477787377654a6a9cb9cc1e20c48a70ebcf47ff3d8785b6`, and `5995186f39e64568585a6dfb91d20341b1f375827ec95817d71a9f6fae010ff5` respectively.

Raw evidence is `/tmp/p2-final-legacy-d4f0e0f4/{driver.log,driver.exit,manifest.tsv}` and `/tmp/p2-task3-parent-capsules/candidate-d4f0e0f4/{driver.log,actual.exit,fixed.exit,actual.log,fixed.log,actual/manifest.tsv,fixed/manifest.tsv,pickle-graph.log,layout-check.log,capsule-json-diff.log}`. The `040ef78a` parent/reuse receipts remain historical probe and compatibility evidence; their earlier pin and 1,263-object graph are not the fresh final result.

## Fresh Public Compile Smokes

The coordinator ran `/tmp/p2-task9-real-cli-smoke.py` against `/tmp/orc-phase2-execution` at `d4f0e0f4`, with `PYTHONDONTWRITEBYTECODE=1`, that checkout's `PYTHONPATH`, and child `PYTHONHASHSEED=0`. Both actual public `python -m orchestrator compile` invocations exited 0. Entry sources were copied into scratch and retargeted to 2.35; command manifests retained their mappings and added the explicit implementation closure. The search closure is the real `experiments/mlevolve_pair/leaves.py`. Improve retains checked-in provider/prompt manifests and uses an explicitly disclosed compile-only `scripts/launch_experiment.py` stand-in that raises if executed.

| Real source / entry | Build key | Program digest | Observed sites/effects |
| --- | --- | --- | --- |
| `experiments/mlevolve_pair/search_compact.orc::run-search` | `e7294be21da71dcd` | `sha256:8c73e408caee0aca6bbdeeea1b1650438b1028fc185649ac3b1b9c655a6b7ea5` | Six command sites; one called definition |
| `workflows/examples/improve_experiment_proposal.orc::run-experiment` | `650caf734dfe3864` | `sha256:1934809e8a7eaac6d970704ba2e65ec48525895a80da20b5d90ffd51413cdbc8` | Three sites: one command and two providers; four called definitions |

Each entry source was deleted after compilation. `ClosedProgram.from_artifact` then loaded the persisted `closed_program.json`, with digest, site/effect count and logical command closure checks passing. These are compile/readback smokes, not provider dispatch or runtime parity. Exact CLI argv/stdout/stderr are retained in `/tmp/p2-final-smoke-d4f0e0f4/{search,improve}/cli.log`; driver evidence is `/tmp/p2-final-smoke-d4f0e0f4.log` and `/tmp/p2-final-smoke-d4f0e0f4.exit` (0).

## Final Phase-Wide Verification And Review

The completed full run at `d4f0e0f4` recorded **275 failed, 20,288 passed, 36 skipped, 178 xfailed, zero errors, 230 warnings**, **607.90 s**, exit **1**. It ran alone in tmux with the required `-n 16 --dist=worksteal` flags, bytecode/cache disabled and short basetemp `/tmp/p2f.UICA91`, on Python 3.13.9, pytest 8.4.1 and pytest-xdist 3.8.0. Full command: `python -m pytest -q -n 16 --dist=worksteal -p no:cacheprovider --basetemp=/tmp/p2f.UICA91 -rfE`. The complete marker, stdout, exit, environment and exact tested head are retained under `/tmp/orc-full/phase2-final-d4f0e0f4-space/`.

The completed exact baseline run, `/tmp/orc-full/phase0-final3/`, recorded **349 failed, 19,578 passed, 36 skipped, 178 xfailed**. Failure-ID comparison found **269 common failures, six newly observed failures, and 80 baseline failure IDs absent**. “Absent” is an inventory comparison, not a claim that Phase 2 fixed eighty issues. Common IDs are retained baseline evidence; matching IDs alone do not prove every diagnostic is identical. This full run is completed red evidence and is never reported as a green suite.

`phase2-final-full-diagnosis.md` records the bounded investigation of every newly observed ID. The reviewer ran all six selectors serially at both exact heads under matching fixed permissions, with `-n 0`, no pytest cache and per-selector timeout/basetemp. Current initially produced three PASS/three FAIL; exact baseline produced six PASS. The resulting dispositions are:

| Newly observed full-run failures | Paired evidence and disposition |
| --- | --- |
| Diagnostic metadata artifact test (one) | Confirmed integration regression: an existing aliased direct `_write_build_artifacts` test caller omitted new required `workspace_root`. Test-only commit `17049e79051fda461f3dd20864c85fb740f96958` passes `workspace_root=tmp_path`; corrected caller plus wrapper/monkeypatch control recorded **2 passed in 2.05 s**, exit 0. No production change or expectation weakening. |
| ES feasibility worker tests (two) | Unchanged source/test at both heads. Bubblewrap's `--bind <sandbox_tmp_root> /tmp` hides the candidate checkout under `/tmp`; child stderr records plugin `scripts` ImportError. Exact baseline files moved under `/tmp` also fail both; exact current files under `/home` pass both. Proven checkout-location artifact; isolation/ledger validation was not relaxed. |
| Provider isolation backend tests (two) | Both pass serially at both heads; affected production/test files are unchanged. Full-run traces fail strict source/run-root ancestor currentness at shared mode-01777 `/tmp`, whose nanosecond mtime/ctime can change concurrently. The concurrency attribution is supported by the retained trace/source/serial controls, not by an induced race. Security checks were not weakened. |
| Mixed spike-trial comparison (one) | Passes serially at both heads; source/test unchanged. Recovered and normalized evaluator packets differ only at `packet.items[3].value[0].duration_ms`: flat 0 versus spike 124. Earlier result comparison permits this nonnegative duration variance; the later prompt equality does not remove it. Recorded as a pre-existing timing-sensitive assertion, without a prompt or runtime semantic change. |

Exact commands, ordering, heads, twelve paired logs/exits, cross-location ES evidence and recovered mixed prompt packets are retained under `/tmp/orc-full/phase2-full-diagnosis/`. The one-line caller repair's report is `phase2-final-path-safety-test-caller-fix.md`, with `/tmp/phase2-final-path-safety-test-caller-green.log`; it neither adds nor renames a test. The full suite was not rerun after this bounded test-only adaptation. Its two focused checks verify the actual caller change; unchanged production/workflow/fixture evidence remains reusable under the exact tree audit and evidence hashes in `phase2-final-verification-reuse-17049e79.json`. No full run at `17049e79` or invented adjusted full-run total is claimed.

Earlier runs are excluded from completed verification: the `3d4c2514` attempt was interrupted after stalled LSP tests (exit 2); a first corrected-environment d4 attempt exhausted the filesystem and lost its exit write/truncated stdout. Its observed terminal totals are not an authoritative completed run. Evidence and cleanup receipts remain `phase2-final-hang-diagnosis.md`, `phase2-diskfull-tmux-output.log`, `phase2-diskfull-cleanup.json`, and `/tmp/orc-full/phase2-final-3d4c2514/interruption-record.json`. The completed run above resolves neither history by relabeling it.

### Whole-Phase Findings And Repairs

The first independent whole-phase review at `3d4c2514` returned FAIL and is preserved in `phase2-final-code-review.md`. Every finding is recorded; the owner's Critical-only acceptance gate does not suppress other findings or excuse a demonstrated new failure.

- Five compatibility causes from the interrupted-run paired diagnosis were repaired in `583aa5ad5be76193b22320838e86fb2dba401f88`: advisory early target peek returning to authoritative legacy validation on read/parse failure; optional private `imported_programs`; canonical retained-source lookup without rereading bytes; transient typed-snapshot exclusion from equality/repr; and coverage of the two new session state maps. Independent delta review recorded **26 passed** (23 affected guard IDs and three session selectors), exit 0, in `phase2-final-compat-review.md` and `/tmp/p2-final-compat-review/`.
- Critical F1 demonstrated implicit build output following an exterior symlink at 2.35 and legacy 2.34. `f2442e8b0dbe704876884e39c696b2539b7524f3` applies workspace confinement checks at the shared publication owners, including legacy leaves/debug/capsules. The new module recorded **21 collected / 21 passed**; independent public probes reject exterior roots and a legacy leaf without altering outside data, and admit a symlink into the workspace. `phase2-final-path-safety-review.md` records PASS and F1 closure. Pathname validation does not protect against a hostile concurrent symlink swap between check and write; that limit remains explicit, with descriptor-based publication as the stated upgrade if required. No such hostile race was tested or claimed resolved.
- Both deltas were integrated at `d4f0e0f4`. `phase2-final-integration-review.md` records PASS of the merge and preservation of both disjoint changes in shared `build_artifacts.py`. That review originally missed the aliased direct test caller; the completed full run exposed it and the test-only repair above corrects it. Historical callsite claims are superseded by the actual caller audit, not silently retained as exhaustive evidence.

**Final independent code and verification review: PASS** at `17049e79051fda461f3dd20864c85fb740f96958`, under the agreed Critical-only gate. `phase2-final-verification-review.md` records no observed outstanding Critical findings or Phase 2 regressions, preserves the red suite and every newly observed failure's disposition, and audits the exact one-line follow-up, compatibility/readback and unchanged dependencies. This is an independent evidence review, not another full-suite execution.

**Final independent documentation review: PASS** for publication `a6efc7e7c307d41181680ef5d0b2fef8d414ed00`, recorded in `phase2-final-docs-review.md`. The reviewed publication and code `17049e79051fda461f3dd20864c85fb740f96958` were integrated at `a7b157d84787ff617c355c3314d0c5da9559b4e6`. That review explicitly authorized only the factual completion metadata and final Closeout checkbox after this integration. All eleven tasks and the Phase 2 compiler closeout are complete; Phases 3–7 remain pending. Final delivery SHA and bundle verification belong to the separate coordinator receipt, avoiding a self-referential commit ID here. No push or write to the owner's dirty shared checkout is part of this report.

The publication revision's fresh narrow checks recorded **2 passed in 2.16 s**, exit 0, for existing Q2 navigation and docs-index roadmap selectors (`phase2-closeout-docs-routing.log`, `.exit`). A stdlib-only static check of the six publication files resolved **622 relative file links**, found the two relevant status/delivery-order anchors, and confirmed the full table's keys/results/site counts exactly against AST `EXPECTED`: **52 rows, 37/10/4/1**. `phase2-closeout-docs-static.json` records that bounded check and `git diff --check` exit 0; it does not claim a universal repository anchor audit or execute the corpus module.

## Downstream Handoff

With the Phase 2 compiler closeout complete, the next implementation surface is **Phase 3**, including public run/resume/dry-run, committed-effect recovery and derived state/readers for the admitted classes. The preserved delivery order is **Phase 2 → Phase 3 → early Phase 6a pilot → selected Phase 4 additions (including Phase 4c/W3) and independent Phase 5 → Phase 6b consumer migration → Phase 7 retirement**.

Phase 5 may start after Phase 3 alongside the pilot and does not wait for all Phase 4 effects. Phase 6b proceeds consumer by consumer as its required capabilities land. W3 follows the Phase 6a caller assessment and resolved grammar/target/module compatibility, delivers its existing component tasks in Phase 4c, and migrates maintained callers in Phase 6b. Explicit portable context and PQ-1 remain scoped later work; this compiler closeout neither implements them nor adds them as Phase 2/3 prerequisites. Preserved obligations include useful generic/hooks/nested composition, macros/source provenance, typed prompts/results and artifact publication/consumption/freshness/lineage. Existing runs and legacy targets remain governed by the explicit Phase 7 retirement decision.
