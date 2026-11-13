# Workflow Lisp Design Corpus Consolidation Plan

**Status: Plan, drafted 2026-11-13; not reviewed, not accepted.** This page plans the documentation
half of stage 5 ("Surface coherence") of
[Lane D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed):
the stage ends with one current language reference and the superseded designs marked historical.
It is a plan, not a contract, and not copy-safe guidance. `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md) own behavior before, during
and after it. It changes no code and spends no provider call.

Approach: sort the 81 Workflow Lisp design documents by what the code and the other documents say
about them, mark as Historical everything that is no longer an owner (bodies untouched), move the
rules that still live only in a feature design into the frontend specification, and cut the
authoring guide to what compiles today. Work that touches no file another session is editing comes
first and is useful alone.

What this makes harder: the frontend specification stays long (about 4,600 lines) because it
absorbs rules instead of pointing at them; a reader who wants the rationale for a feature follows a
link into a Historical record; the 39 design files that link executor retirement, many as the
current authority of a historical notice, reach `specs/` in two hops after the cut; and each merge task needs a reviewer who reads
the rule ledger, since no test can prove a sentence was carried.

## What Was Measured, And How

On `main` at `ae36901d`, in the working tree, which holds another session's uncommitted edits
(listed under [Blocked files](#blocked-files)), so line counts include them.

- **Lines:** `wc -l`. `docs/design/` holds 105 files and 63,729 lines; the 81
  `workflow_lisp_*.md` files hold 52,807.
- **Stated status:** the document's own status line or scope notice, shortened.
- **Role:** per [documentation conventions](../documentation_conventions.md#current-guidance-and-historical-records):
  *contract* (spec or component contract), *record* (closed plan, report or decision record),
  *proposal* (status `Designed` or `Future`).
- **Code check:** for each document, the Python file names, form heads and commands it names were
  compared with `git ls-files`, with `registered_form_heads()` and `RETIRED_FORMS` in
  `orchestrator/workflow_lisp/form_registry.py` (81 heads today, 82 at target 2.40 with `agent`),
  and with `python -m orchestrator --help`. "Live codes" are backticked identifiers of three or
  more words (such as `list_map_binder_invalid`) that occur as a string literal in
  `orchestrator/`; for each feature design they were looked up in the frontend specification,
  `specs/`, evaluated execution and the guide. Class names such as `ProofGraph` were grepped in
  `orchestrator/`. "Probe" means a small program compiled at target 2.40 with
  `python -m orchestrator compile`, stand-in manifests and the no-provider stubs first on `PATH`
  (44 programs).
- **Linked from:** maintained documents (top-level `docs/*.md`, `specs/`, the three READMEs) that
  contain the file name ("index" is `docs/index.md`, "matrix" the capability matrix, "catalog"
  `workflows/README.md`); every document is also listed in `docs/design/README.md`. Plans and
  reports are not counted. Source and test files that cite the path are counted separately; none
  opens a design document. Two tests depend on a document: `tests/test_first_hour_e2e.py` runs the
  tutorial's blocks, and `tests/test_authoring_check_kit.py` asserts the guide's path.
- **Links and anchors:** `python scripts/check_doc_links.py` over 144 maintained files reports 59
  problems today (7 in the run-reference design, 6 in the guide, 5 each in `specs/cli.md` and the
  capability matrix). That is the baseline; no task may add one.

## What The Conventions Allow

- A historical document that is discoverable as current guidance gets a short scope notice; its
  body is preserved, not updated.
- A lasting rule is promoted to its owner before the document that held it is archived.
- Sections may be extracted from a maintained document into a historical record if cited anchors
  are kept or their incoming references updated. The directory
  `docs/reports/documentation-history/` already holds 51 such records.
- A whole document is not duplicated to shorten its introduction.
- Nothing in the conventions permits deleting a historical record, and source files and tests
  cite design documents by path. **This plan deletes and renames no document.**
- A guide keeps prerequisites, current commands, choices and troubleshooting; past incidents and
  obsolete workarounds belong in a historical record. Guide text that only repeats another
  maintained document is removed, with the owner named in the rule ledger.

## Inventory: Workflow Lisp Design Documents

Classes: **OWNER** (a rule lives only here), **DUPLICATES** (current, its rules are restated or
owned elsewhere), **SUPERSEDED** (a later design or the code replaced it), **DELETED CODE**
(describes code or forms that are gone), **NEVER BUILT** (a proposal), **HISTORICAL** (already
marked). Document names omit the `workflow_lisp_` prefix and `.md`. Task ids refer to
[Tasks](#tasks); `-` means no task touches the file.

| Document | Lines | Stated status | Role | Code check | Linked from | Class | Fate | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `agent_sessions` | 445 | First slice implemented at 2.38 | contract | `agent` registered at 2.40; probe builds | matrix, guide, specs/dsl | OWNER | Keep (feature contract) | - |
| `checked_program_evaluation` | 271 | Proposed; parked 2026-11-11 | proposal | no `eval-orc` head in the registry | matrix | NEVER BUILT | Leave; listed under proposals | T2 |
| `compile_time_parametric_specialization` | 441 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `composition_first` | 489 | Generic unions and `std/improve` implemented | contract | `std/improve` imports at 2.40 (probe) | matrix, library ref, specs/versioning; cited by 6 test files | OWNER | Keep; E1 removes its section 11.1 rule | - |
| `consolidation` | 253 | Current ownership topology after extraction | record | named modules exist except `executable_ir.py` | design index only | SUPERSEDED | Rule check, then Historical | T3b |
| `consumer_side_rendering` | 691 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `core_calculus_middle_end` | 813 | Accepted architecture; flat route retired | contract | `workflow_lisp/wcc/` exists | README, matrix, index; cited by 2 source and 1 test files | OWNER | Keep (compiler internals, not on the author's path) | - |
| `core_stmt_taxonomy` | 168 | Historical; code removed 2026-11-12 | record | `core_ast.py` gone | design index only | HISTORICAL | Leave | - |
| `core_workflow_ast` | 94 | Historical; code removed 2026-11-12 | record | `core_ast.py` gone | design index only; cited by 1 source files | HISTORICAL | Leave | - |
| `debug_yaml_renderer` | 70 | Historical | record | n/a | matrix | HISTORICAL | Leave | - |
| `durable_host_input` | 500 | Current feature contract, target 2.40 | contract | `request-input` probe builds at 2.40 | architecture, matrix, index, specs/versioning | OWNER | Keep (feature contract) | - |
| `edit_and_continue` | 943 | Accepted as basis for a plan; Phase 3b in execution | proposal becoming contract | partly implemented (3b tasks merged) | matrix | OWNER | Historical when Phase 3b closes and evaluated execution carries it (that plan's call) | T15 |
| `edit_and_continue_spike` | 487 | Feasibility spike; 3a landed elsewhere | record | prototype deleted (its own words) | design index only | SUPERSEDED | Historical notice now | T1 |
| `effect_graph` | 153 | Current-checkout component contract | contract | class `EffectGraph`: 0 hits; depends on the deleted Semantic IR | matrix; cited by 1 source files | DELETED CODE | Rule check, then Historical | T3a |
| `effect_ledger_simplification` | 426 | Accepted 2.39 contract | contract | `procedure_effect_ceiling_exceeded` in code; probe builds | matrix, guide, specs/index, specs/versioning | OWNER | Merge into the specification after the cut, then Historical | T10 |
| `evaluated_execution` | 3,308 | Current execution contract | contract | 96 of 98 named modules exist | README, architecture, matrix, index, guide, Python guide, lifecycle, 6 specs | OWNER | Keep (the runtime design) | - |
| `executable_ir` | 309 | Historical | record | `executable_ir.py` gone | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `executor_retirement` | 274 | Current cutoff and recovery contract | contract | `workflow_execution_target_retired` refuses 2.34 (probe) | matrix, index, library ref, OMP runbook, lifecycle, catalog, 4 specs | OWNER | Historical after the cut, if `specs/` carry its rules | T12 |
| `frontend_deduplication` | 102 | Incorporated; companion decision record | record | n/a | index | DUPLICATES | Historical notice now | T1 |
| `frontend_mvp_specification` | 585 | Historical | record | n/a | index, MVP comparison; cited by 4 source files | HISTORICAL | Leave | - |
| `frontend_specification` | 4,800 | Accepted baseline | contract | 60 registered heads named; 9 removed heads still named; 12 of 18 named modules gone; no `cond` | README, matrix, index, guide, LSP setup, MVP comparison, gap list, 3 specs; cited by 4 source and 3 test files | OWNER | Keep (the language reference); slim and absorb | T4-T5, T8-T13 |
| `generic_core_expression_surface_adapter_retirement` | 1,824 | Historical | record | n/a | matrix, index, guide | HISTORICAL | Leave | - |
| `generic_resource_context_core` | 578 | Historical | record | n/a | design index only | HISTORICAL | Leave | - |
| `judgment_views` | 986 | Scope notice plus 'retained read-only contract' | record | `report` projection removed; 18 of 26 named codes gone | matrix, index, guide; cited by 1 test files | HISTORICAL | Normalise the notice | T1 |
| `key_migration_parity_architecture` | 1,684 | Historical | record | n/a | index, gap list | HISTORICAL | Leave | - |
| `language_server` | 2,556 | Current tooling contract L0-L5 | contract | `orchestrator/lsp` exists | matrix, index, guide, LSP setup; cited by 2 test files | OWNER | Keep (tooling) | - |
| `legacy_adapter` | 83 | Current adapter-quarantine policy | contract | class `LegacyAdapter`: 0 hits; lowercase name in `lints.py` | design index only | DUPLICATES | One paragraph into the command adapter contract, then Historical | T3a |
| `let_proc_local_proc_refs` | 1,264 | Implemented V1; W3 at 2.36 | contract | `let-proc` probe builds (W3 form) | matrix, index, guide; cited by 1 source files | OWNER | Merge what survives the cut into specification 7.8, then Historical | T9 |
| `lexical_checkpoint_resumability` | 859 | Historical | record | n/a | design index only | HISTORICAL | Leave | - |
| `lexical_execution_checkpoints` | 132 | Predecessor architecture; retained safety notes | record | old checkpoints not used by the memo (its own words) | matrix, index; cited by 1 test files | HISTORICAL | Normalise the notice | T1 |
| `lsp_authored_reference_navigation` | 230 | Historical | record | n/a | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `lsp_diagnostic_lifecycle_and_progress` | 407 | Historical | record | n/a | matrix, index, LSP setup; cited by 1 test files | HISTORICAL | Leave | - |
| `macro_surface_contract` | 240 | Accepted current-surface contract | contract | `defmacro` registered; 7 of 9 live codes also in the specification | matrix, index, guide | OWNER | Merge into specification Part VII, then Historical | T4c |
| `native_transportable_returns` | 1,047 | Accepted; implemented at 2.15 | contract | `(result T ...)` probe builds; specification has no section for it | matrix, gap list; cited by 2 source files | OWNER | Merge surface rules into the specification, then Historical | T4e |
| `numeric_surface` | 203 | Implemented at 2.34 | contract | 5 of 5 live codes in the specification and `specs/` | matrix, guide, specs/versioning; cited by 2 source and 3 test files | DUPLICATES | Rule check, then Historical | T4a |
| `parametric_type_system` | 742 | Current implemented parametric contract | contract | 23 live codes, 11 only here; 4 source files and 9 tests cite it | matrix, index, guide, specs/versioning; cited by 4 source and 9 test files | OWNER | Keep (feature contract) | - |
| `phased_contract_delivery` | 672 | Selected 2.39 migration; retained historical protocol | contract | phased probe reaches its own policy check | matrix, index, guide, tests README, 4 specs; cited by 1 test files | OWNER | Keep (feature contract) | - |
| `post_foundation_composition_stdlib_migration` | 2,855 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `private_runtime_state_and_consumer_value_flow` | 672 | Partial; C2-C6 dropped 2026-11-11 | contract in part | 1 live code, also in `specs/` | matrix, index | SUPERSEDED | Rule check, then Historical | T3b |
| `proc_refs_partial_application` | 350 | Implemented design delta | contract | 9 live codes, 8 only here | matrix, index | OWNER | Merge into specification 7.8, then Historical | T9 |
| `procedure_first_reuse_contract` | 401 | Accepted; adoption gated | contract | `:lowering` refuses at 2.40 (probe) | matrix, index, guide | DUPLICATES | Merge the boundary rule after the cut, then Historical | T10 |
| `procedure_migration_identity_compatibility` | 587 | Durable principles; historical generator | contract in part | 0 live codes; 'no generator or shim remains' | matrix, index; cited by 2 test files | DELETED CODE | Rule check, then Historical | T3b |
| `program_search_boundaries` | 134 | Adopted position statement | contract | n/a (invariants) | matrix | OWNER | Keep | - |
| `progressive_execution` | 291 | Draft target; not implemented | proposal | no code named | matrix | NEVER BUILT | Leave; listed under proposals | T2 |
| `prompt_calculus` | 859 | Accepted and implemented Q1-Q3 | contract | 32 of 35 live codes in the specification; 7 of 13 named modules gone | matrix, index, guide; cited by 1 test files | DUPLICATES | Rule check, then Historical | T4b |
| `prompt_identity_diagnostics` | 1,125 | Accepted, target 2.22 | contract | 12 live codes, 26 named codes gone | matrix, index, guide; cited by 1 test files | DUPLICATES | Rule check, then Historical | T4b |
| `proof_graph` | 74 | Current typed proof contract | contract | class `ProofGraph`: 0 hits | matrix | DELETED CODE | Rule check, then Historical | T3a |
| `provider_call_policy` | 88 | Current component contract | contract | 88 lines; 1 live code only here | matrix, index | OWNER | Keep (small) | - |
| `provider_context_values` | 561 | Historical 2.31 slice; native context proposed | record | `:capture-context` still parses (probe); no evaluated port (its own words) | matrix, guide | HISTORICAL | Normalise the notice (file blocked) | T6 |
| `provider_live_binding` | 69 | Retained routing; historical protocol | record | `with-live-providers` registered; build refuses (stage 4 plan) | matrix, index, guide, specs/index; cited by 2 test files | HISTORICAL | Normalise the notice | T1 |
| `provider_peer_messaging` | 59 | Retained routing; historical protocol | record | `with-live-provider-peers` registered; build refuses (stage 4 plan) | matrix, index, guide, specs/index | HISTORICAL | Normalise the notice | T1 |
| `provider_prompt_dependencies` | 106 | Current component contract | contract | 106 lines; named modules exist | matrix, index | OWNER | Keep (small) | - |
| `provider_prompt_queue` | 313 | Historical | record | n/a | matrix, index | HISTORICAL | Leave | - |
| `pure_call_composition` | 435 | Implemented at 2.30; incorporated in specification 8.6 | contract | 1 live code, only here | matrix; cited by 1 test files | DUPLICATES | Add the code to 8.6, then Historical | T4a |
| `pure_list_traversal` | 460 | Implemented at 2.18 | contract | 15 live codes, 12 only here; specification 10.3 defers to it | matrix, index; cited by 1 test files | OWNER | Merge into specification 10.3 after I1, then Historical | T8 |
| `pure_result_replay` | 919 | Historical | record | n/a | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `refactor_architecture` | 284 | Draft architecture guidance | proposal | `lowering.py` gone; its plan ran in June | index | SUPERSEDED | Historical notice now | T1 |
| `reference_catalog` | 77 | Current reference-kind contract | contract | class `ReferenceCatalog`: 0 hits | design index only | DELETED CODE | Rule check, then Historical | T3a |
| `repl` | 489 | Implemented | contract | `repl` command exists | matrix, index, guide, specs/cli | OWNER | Keep (tooling) | - |
| `repl_introspection` | 307 | Implemented | contract | 17 of 17 named modules exist | matrix, index, guide, specs/cli | OWNER | Keep (tooling) | - |
| `review_revise_stdlib_parametric_integration` | 2,972 | Historical | record | n/a | index, guide | HISTORICAL | Leave | - |
| `run_ref_expression_environments` | 652 | Partial at 2.38; provider part dropped | contract | 12 of 13 live codes also in `specs/` | matrix, index, library ref, guide, 7 specs | OWNER | Keep (feature contract) | - |
| `runtime_closures_boundary` | 669 | Deferred acceptance contract | contract (guardrail) | nothing to build by design; surface coherence cites it | matrix, index | OWNER | Keep | - |
| `runtime_migration_foundation` | 1,217 | Implemented foundation; promotion gate retired | contract in part | 10 of 12 named codes gone | matrix, index | SUPERSEDED | Rule check, then Historical | T3b |
| `runtime_native_drain_authoring` | 880 | Historical; forms removed 2026-11-12 | record | heads refuse `form_retired` | matrix, index, guide | HISTORICAL | Leave | - |
| `semantic_workflow_ir` | 187 | Historical; code removed 2026-11-12 | record | `semantic_ir.py` gone | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `shared_owner_lane_prerequisites` | 612 | Reference target / prerequisite ledger | record | 37 mentions of removed heads | index | DELETED CODE | Historical notice now | T1 |
| `source_map` | 382 | Accepted | contract | class `SourceMap`: 0 hits; sidecar retired | matrix; cited by 1 source files | DUPLICATES | Rule check against specification 74, then Historical | T3a |
| `source_site_inspection` | 302 | Implemented offline; unselected | contract | `source_sites.py` and 3 test modules exist | matrix, index; cited by 1 source and 3 test files | OWNER | Keep (search tooling) | - |
| `state_layout` | 154 | Historical; code removed 2026-11-12 | record | `state_layout.py` gone | matrix; cited by 1 test files | HISTORICAL | Leave | - |
| `stdlib_lowering` | 192 | Historical; forms removed 2026-11-12 | record | heads refuse `form_retired` | design index only; cited by 1 source files | HISTORICAL | Leave | - |
| `strict_boolean_control_flow` | 658 | Accepted; implemented at 2.26 | contract | `cond` registered; specification 12 has no `cond` | matrix | OWNER | Rewrite specification 12 from it, then Historical | T4d |
| `structural_parametric_constraints` | 321 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `surface_coherence` | 405 | Accepted 2026-11-12; not implemented | contract until retired | branches in flight | design index only | OWNER | Historical when its section 11 conditions hold | T15 |
| `transportable_value_type` | 318 | Current implemented transport contract | contract | 4 of 4 live codes in the specification and `specs/` | matrix, index; cited by 1 test files | DUPLICATES | Rule check, then Historical | T4a |
| `trial_runs` | 381 | Partial; `trial` removed 2026-11-12 | contract in part | `trial` refuses `form_retired` (probe) | matrix, specs/index | DELETED CODE | Historical notice now | T1 |
| `type_catalog` | 156 | Current shared typed catalog | contract | class `TypeCatalog`: 0 hits | design index only; cited by 1 source and 1 test files | DELETED CODE | Rule check, then Historical | T3a |
| `typed_program_gates` | 459 | Accepted; C2 dropped, C1/C3 parked | proposal | 14 of 16 named codes absent | matrix | NEVER BUILT | Leave; listed under proposals | T2 |
| `unified_frontend_design` | 153 | Historical unified proposal | record | n/a | index | HISTORICAL | Leave | - |
| `value_and_continuation_composition` | 519 | Current for Increments 1-3; 4-5 retired | contract in part | 1 live code, also in `specs/` | matrix | DUPLICATES | Rule check after E1 and I2, then Historical | T11 |
| `write_once` | 574 | W3 implemented; W0/W1 unselected, W4 dropped | contract in part | W3 `let-proc` probe builds | matrix, library ref, guide, specs/index, specs/versioning | OWNER | Merge section 6.3 into specification 7.8, then Historical | T9 |

| Class | Documents | Lines |
| --- | --- | --- |
| OWNER | 28 | 23,713 |
| DUPLICATES | 10 | 4,427 |
| SUPERSEDED | 5 | 2,913 |
| DELETED CODE | 7 | 2,040 |
| NEVER BUILT | 3 | 1,021 |
| HISTORICAL | 28 | 18,693 |
| Total | 81 | 52,807 |

Five of the 28 HISTORICAL documents carry a notice in a non-standard form (a "retained" or
"predecessor" status line under the notice reads as current): `judgment_views`,
`lexical_execution_checkpoints`, `provider_context_values`, `provider_live_binding`,
`provider_peer_messaging`.

## Inventory: Other Design Documents In The Index

Classified from the status line and one existence check each; not the subject of this plan except
where a task is named.

| Document | Lines | Stated status | Class | Fate |
| --- | --- | --- | --- | --- |
| `workflow_language_design_principles` | 654 | Design guidance | OWNER | Keep |
| `workflow_command_adapter_contract` | 509 | Current command/adapter contract | OWNER | Keep; receives the legacy-adapter paragraph (T3a) |
| `provider_result_delivery` | 540 | Implemented 2026-10-13 | OWNER | Keep |
| `python_workflow_frontend` | 675 | Accepted; serial subset implemented | OWNER | Keep |
| `omp_provider_and_native_continuation` | 205 | Current contract for retained OMP calls | OWNER | Keep |
| `verified_iteration_drain` | 385 | Implemented; `workflows/library/verified_iteration_drain` exists | OWNER | Keep |
| `observability_step_visit_summaries` | 109 | Partial; dashboard pages removed | OWNER | Leave (observability, out of scope) |
| `orc_effectiveness_comparison_harness` | 805 | Implemented apparatus | OWNER | Leave (research) |
| `orc_reuse_introspection_search_experiment` | 793 | Draft experiment design | NEVER BUILT | Leave (research) |
| `orc_structural_search_driver` | 1,336 | Partial apparatus, offline | OWNER | Leave (research) |
| `orc_structural_search_cumulative_campaigns` | 724 | Partial, offline | OWNER | Leave (research) |
| `mlevolve_workflow_lisp_system_architecture` | 951 | 'Draft design'; dropped 2026-11-11 | NEVER BUILT | Historical notice now (T1) |
| `live_provider_supervision_and_peers_salvage` | 271 | Historical | HISTORICAL | Leave |
| `trial_and_adjudication_salvage` | 274 | Historical | HISTORICAL | Leave |
| `dashboard_observability_summary_gui` | 284 | Historical | HISTORICAL | Leave |
| `dashboard_summary_invocation_tabs` | 95 | Retired; never implemented | HISTORICAL | Leave |
| `dsl_v214_materialization_variants_draft` | 109 | Historical | HISTORICAL | Leave |
| `dsl_v214_pointer_authority` | 123 | Historical | HISTORICAL | Leave |
| `dsl_v214_variant_surface_decision` | 82 | Historical | HISTORICAL | Leave |
| `dsl_v214_yaml_ergonomics` | 197 | Historical | HISTORICAL | Leave |
| `lisp_frontend_review_fix_loops` | 318 | Historical | HISTORICAL | Leave |
| `neurips_v214_behavior_matrix` | 52 | Historical | HISTORICAL | Leave |
| `resume_projection_integrity_hardening` | 1,251 | Historical | HISTORICAL | Leave |

The index also lists three files outside `docs/design/` (two under `docs/superpowers/specs/`, one
report); they were not inventoried.

## Target Shape

What an author reads, in order: the [tutorial](../tutorial_first_pipeline.md), the
[drafting guide](../lisp_workflow_drafting_guide.md) (how to write), the frontend specification
(what every form means), the [library reference](../lisp_library_reference.md) (which helper).
`specs/` stay normative for runtime and DSL behavior. Evaluated execution is the one runtime
design, read for resume, identity and the memo.

| Current set after this plan | Documents | Lines now | Lines after |
| --- | --- | --- | --- |
| Language reference: `frontend_specification` | 1 | 4,800 | at most 4,600 (estimate) |
| Runtime design: `evaluated_execution` | 1 | 3,308 | unchanged by this plan |
| Feature contracts, read when the feature is used: `parametric_type_system`, `composition_first`, `agent_sessions`, `durable_host_input`, `phased_contract_delivery`, `run_ref_expression_environments`, `provider_call_policy`, `provider_prompt_dependencies` | 8 | 3,694 | unchanged |
| Boundaries: `program_search_boundaries`, `runtime_closures_boundary` | 2 | 803 | unchanged |
| Tooling and compiler internals: `language_server`, `repl`, `repl_introspection`, `source_site_inspection`, `core_calculus_middle_end` | 5 | 4,467 | unchanged |
| **Current Workflow Lisp design documents** | **17** | **17,072** | **about 16,872** |
| Proposals, not built, listed apart: `checked_program_evaluation`, `progressive_execution`, `typed_program_gates` | 3 | 1,021 | unchanged |

Every other document, by fate:

- **Historical notice now, no rule to move** (T1): `edit_and_continue_spike`,
  `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`,
  `trial_runs`, and `mlevolve_workflow_lisp_system_architecture`. The four free documents with a
  non-standard notice are normalised in the same task; `provider_context_values` waits (T6).
- **Rule check, then Historical** (T3a, T3b, T4a, T4b): the six "internal specification" pages
  whose classes no longer exist, four closed migration designs, and five feature designs whose
  live codes the specification already carries.
- **Merge the rules into the specification, then Historical** (T4c, T4d, T4e now; T8 to T11 after
  the code changes): `macro_surface_contract`, `strict_boolean_control_flow`,
  `native_transportable_returns`; then `pure_list_traversal`, `proc_refs_partial_application`,
  `let_proc_local_proc_refs`, `write_once`, `effect_ledger_simplification`,
  `procedure_first_reuse_contract`, `value_and_continuation_composition`.
- **Historical when another plan finishes** (T12, T15): `executor_retirement` after the one-target
  cut, `surface_coherence` when its own section 11 says so, `edit_and_continue` when Phase 3b
  closes.
- **Leave:** the 23 documents already Historical with a standard notice, the proposals, and the
  current set above.

The frontend specification changes in three ways: it gains the rules of the merged feature designs
in the sections that already name them (it has no `cond` and one line on result guidance today);
the bodies of its sections on removed forms (24, 26, 28 to 31, 86, 87, 107), its retired CLI
sections (78.1, 79, 80, 109) and its historical testing strategy (94 to 98) move to its existing
history file with anchors left in place; and after the cut its 187-line preamble and its
per-target prose become present-tense rules.

## The Authoring Guide

3,424 lines in the working tree (3,363 at `HEAD`; the difference is another session's
uncommitted REPL text). It links 27 design documents (27,734 lines) and its "current contract
reading path" names ten documents. 19 distinct anchors in it are linked from 33 files outside
plans and reports; every one must still resolve (an `<a id>` is enough).

"Edited again by" names the change that will rewrite the section anyway: **4b** is the one-target
cut (Task 4b of the [stage 4 plan](2026-11-12-lane-d-stage-4-one-target-plan.md)); **E1, I1, C1,
I2** are the changes of the [surface coherence design](../design/workflow_lisp_surface_coherence.md#11-where-the-rules-live).
Pass 1 (T7) leaves those sections alone; pass 2 (T14) finishes them after the changes land, so each
is edited once by this plan.

| Section | Lines | Teaches | Available at 2.40 today (check) | Fate | Target | Edited again by |
| --- | --- | --- | --- | --- | --- | --- |
| Front matter | 87 | Where authority lives; YAML retirement; refusals of old runs | Routing only; names three removed things per paragraph | Shorten: purpose, audience, a four-document reading path | 20 | - |
| Editor Diagnostics And Navigation | 113 | LSP internals, route-registry labels, a YAML migration promotion checklist | LSP exists; the migration gate is retired (its own words) | Move: LSP to the setup guide (pointer), checklist to the history file; keep 4 authoring bullets in section 27 | 8 | - |
| Core Rule | 14 | Narrow public workflows over typed procedures | Yes | Keep | 10 | - |
| Runtime-Native Authoring Direction | 35 | Pass typed values; hide runtime bookkeeping | Yes | Shorten; merge into Core Rule | 12 | - |
| Prompt Externs | 25 | The prompt extern manifest | Yes (used by the provider probes) | Keep; move next to section 8 | 20 | - |
| 1. Mental Model | 35 | Five layers; what the compiler and evaluator do | Yes; the 'runtime substrate' row names removed IRs | Shorten | 25 | - |
| 2. Availability Model | 55 | Which target admits what | Describes six targets | One paragraph (the cut writes it) | 10 | 4b |
| 2A. Program Shapes | 72 | Shape table, admitted effects, unavailable list, public commands, closures | Table rows hold today; the unavailable paragraph lists `request-input`, which the probe builds | Shorten; unavailable things go to one table | 35 | 4b, E1, I1 |
| Static command arguments and shared closures | 41 | `:argv` omission and the shared closure envelope | Yes (`command-result` probes) | Keep | 35 | - |
| A complete recipe | 158 | Compile, run, resume, report, invalidate on a fixture | Yes (owned by a test); overlaps the tutorial and the lifecycle guide | Shorten to the source and six commands; keep the anchor | 40 | - |
| Print a value during a run | 9 | `print` | Yes (probe) | Keep | 9 | - |
| Inspect a run with the REPL (two sections) | 157 | REPL session, capture rules, a worked lookup | Yes; 63 of these lines are another session's uncommitted additions | Move whole to the monitoring guide; leave a pointer and the two anchors | 6 | - |
| 3. Semantic Authority Rules (3.1-3.8) | 159 | Eight authority rules with bad/good pairs | Rules, not forms; 3.7's discriminant proof: see Not verified | Shorten to one table and two examples; absorbs section 12 | 60 | - |
| 4. Choosing The Right Authoring Unit | 19 | Which form for which need | Yes; two rows describe removed things | Keep without those rows | 17 | - |
| 5. Types First (5.1-5.5) | 164 | `defpath`, `defenum`, `defrecord`, `defunion`, `defschema` | Yes (probes: `defpath`, `defschema`, `variant`, `match`) | Keep; drop the pointer to a historical design in 5.2 | 150 | - |
| 5.6 Loose Transport With `Value` | 31 | `Value` | Type yes; the example's `:lowering` refuses at 2.40 (`proc_lowering_annotation_invalid`) | Keep; fix the example | 28 | 4b |
| 6.1 `defworkflow` | 51 | Workflow boundaries and defaults | Yes (probe with `:default`) | Keep | 45 | C1 |
| 6.2 `defproc` and procedure contracts | 149 | Effects inference, restrictions, generics; an older-contract example; compiler carrier names | 2.39 contract yes (probe); older example refuses | Shorten: one contract, constraints list to a pointer, drop carrier detail | 75 | 4b, C1 |
| 6.3 `defun` | 24 | Pure helpers | Yes (probe) | Keep | 20 | - |
| 6.4 `defmacro` | 27 | What a macro may do | Registered; not probed (no example in the guide) | Shorten; add one example | 20 | - |
| 7. Modules, Imports, And Exports | 46 | Module header, imports, exports | Yes (`std/phase`, `std/improve`, `std/host` import; `std/drain` refuses) | Keep | 40 | - |
| 8. Structured Provider Results | 73 | `provider-result`, inputs, call policy | Yes | Shorten | 60 | - |
| Portable Provider Context | 9 | Context capture | No: unavailable by its own text | Delete to a table row; keep the anchor | 2 | - |
| Agent sessions | 125 | `agent`, turns, a 16-row refusal table, a paid recipe | Yes (probe) | Shorten; refusal table stays with the design and `specs/dsl.md` | 70 | - |
| Durable Host Input | 92 | `request-input`, settlement, resume | Yes (probe) | Keep | 80 | - |
| Explicit OMP Session Publication | 8 | Session artifacts | No: `closed_program_gap` (probe) | Delete to a table row | 1 | - |
| Provider Prompt Dependencies | 76 | `:prompt-dependencies` | Yes | Shorten | 45 | - |
| Prompt Obligations | 23 | What a prompt should say | Yes | Keep | 20 | - |
| Authoring Prompt Fragments | 66 | `defprompt`, slot kinds | Yes (`defprompt` registered; phased probe needs one) | Keep | 60 | - |
| Authoring Prompt Output Positions | 43 | `:path :out` | Not probed; example cites a retired fixture | Shorten | 35 | - |
| Inspecting Prompt-Attempt Identity; Judgment Views | 17 | Diagnostic reports | No: unqualified for evaluated runs; judgment views removed | Delete to a table row | 1 | - |
| Authoring Phased Contract Delivery | 77 | `:delivery :phased` and a stand-in recipe | Yes within its bounds (probe reaches the fragment check) | Shorten | 45 | - |
| 8A, 8B. Live supervision; peer groups | 20 | Two forms that refuse | No: both refuse at build | Delete to table rows | 2 | - |
| Pinned Child Runs And Trials | 20 | Path-mode `run-ref`; removed `trial` | `run-ref` registered; `trial` refuses `form_retired` (probe) | Shorten to the run reference | 12 | - |
| Confined workflow children | 153 | Host preparation, image import, a lifecycle walk | Linux hosts with the listed prerequisites; not probed | Shorten; the kill-and-resume narration is the e2e test's | 80 | - |
| 9. Structured Command Results; Certified Adapters | 74 | `command-result`, adapters | Yes (probes) | Shorten the adapter half | 55 | - |
| 9A. Pure Computation And Typed Projection | 69 | The operator surface | Yes (probes: arithmetic, `list/map`, `path/join-under`) | Keep the table; the specification is the reference | 55 | - |
| 10. Pattern Matching And Variant Proof; 10.1 | 82 | `match`, `if`/`cond` proof, a `Blocked` variant | `match` yes; discriminant proof: see Not verified | Keep | 75 | - |
| 11. Contexts And Derived State (11.1, 11.2) | 127 | Context records for phases, items and drains; boundary classes; path ownership | Mostly no: drains and resources removed; `(phase-target ctx "x.md")` refuses (`phase_target_name_invalid`) | Shorten to the path-ownership table | 30 | - |
| 12. Transitions Instead Of Gates | 23 | Prefer typed outcomes to gates | A principle; resource transitions removed | Merge into section 3 | 0 | - |
| 13. Standard High-Level Forms | 81 | `review-revise-loop`, `improve`, removed forms | `std/phase` and `std/improve` import (probes); body is pointers | Shorten to three paragraphs; keep both anchors | 25 | - |
| 14. Provider Prompt Guidance; Result Guidance | 107 | Prompt content; `(result T ...)` | Yes (probe) | Shorten | 70 | - |
| 15. Operational Notes | 19 | Sessions, retries, best-of-N cautions | Yes | Shorten | 12 | - |
| 16. Reuse And Modularity | 48 | Workflows, `ProcRef`, `WorkflowRef` | Yes | Shorten; the reference paragraphs become a pointer to section 6 | 30 | C1 |
| 17. Loops; 17.1 `loop-state` | 81 | `loop/recur`, `:on-exhausted`, `loop-state` | Yes (probes), in the `fn` form the cut removes | Keep; examples move to the binder form | 75 | I2, E1 |
| 17.2 Bounded list traversal | 18 | List operators and the serial map's limits | Yes (probes) | Keep; the restriction paragraph goes | 15 | I1, E1 |
| 17.3 Parallel map | 96 | `:parallel`, `:workspace`, failure and resume | Yes (probe builds) | Shorten: the test list goes | 60 | - |
| 18. Effects | 45 | Effect kinds; an example | Kinds yes; the example puts `:effects` on a `defworkflow`, a parse error at 2.35 and 2.40 | Rewrite: the effect rule in one paragraph, the kinds, a procedure example | 30 | E1 |
| 19. Source Maps And Debugging; 20. Lints | 54 | Where to look; ten lint names | 4 of the 10 lint names are not in `orchestrator/` | Shorten: debugging order; only lints that exist | 30 | - |
| 26. Prompt Examples | 39 | A good and a bad prompt | Yes | Keep | 30 | - |
| 27. Drafting Checklist; 28. Review Checklist | 64 | Two checklists | Yes | Shorten | 50 | - |
| 29. Legacy policy; 31. Quick Translation Table | 41 | Old runs; YAML thoughts to `.orc` thoughts | History | Move to the history file; four lines stay; the cut adds 'Migrating from an older target' | 19 | 4b |
| 32. Minimal Safe Subset | 77 | One small complete module | Not probed whole | Keep; move up as the first example | 60 | - |
| 33. Final Rule | 6 | The closing rule | Yes | Keep | 5 | - |

Sum of targets: 1,924 lines, plus the table below. **Target for the guide: at most 1,950
lines**, about 43% shorter. Things that do not run (context capture, session artifacts,
prompt-identity reports, judgment views, live supervision, peer groups, bundle-mode run references,
the removed forms) take one table of about 12 rows, "Not available", with the refusal code and the
owner of each.

Outline of the shortened guide:

1. What this guide is; the four documents to read (20 lines)
2. A first module, compiled and run (from "Minimal Safe Subset" and the complete recipe)
3. Core rule and authority rules (one table)
4. Types: paths, enums, records, unions, schemas, `Value`
5. Workflows, procedures, functions, macros; how each is called; modules
6. Provider steps: results, prompt externs, prompt fragments and output positions, dependencies,
   result guidance, a step that may be unable to answer
7. Command steps and adapters; closures
8. Pure computation; pattern matching and proof
9. Loops, list traversal, parallel map
10. Effects: where one may be written, the kinds, restrictions
11. Features with their own contract: agent sessions, host input, phased delivery, run references
    and confined children
12. Library forms: `review-revise-loop`, `improve` (pointers)
13. Debugging and lints; not available; migrating from an older target
14. Checklists

## Tasks

### Blocked files

Another session has uncommitted edits to these files. No task touches them until `git status
--short` shows them clean on `main`: `README.md`, `docs/index.md`,
`docs/lisp_workflow_drafting_guide.md`, `docs/orc_workflow_design_lessons.md`,
`docs/design/workflow_lisp_agent_sessions.md`,
`docs/design/workflow_lisp_effect_ledger_simplification.md`,
`docs/design/workflow_lisp_evaluated_execution.md`,
`docs/design/workflow_lisp_provider_context_values.md`,
`docs/design/workflow_lisp_provider_prompt_queue.md`, `docs/design/workflow_lisp_repl.md`,
`docs/design/workflow_lisp_runtime_closures_boundary.md`, `specs/cli.md`, `specs/providers.md`,
`workflows/README.md`. Each task re-runs `git status --short` first. No `git stash`; a task works
on a branch in its own worktree and commits by pathspec.

### How a task proves no rule was lost

One report, `docs/reports/2026-11-13-design-corpus-rule-ledger.md`, created by T0 and appended by
every task that marks a document Historical after a check, or removes text from the guide or the
specification. One row per rule: the document and section; the rule as written; the owner file and
anchor; the owner's sentence, quoted; how it was checked (identifier grep, probe, test name). A
rule is found by reading the document for sentences that require, forbid, bound or refuse, and by
listing its live codes. A row may instead say "describes removed code" with the removed module or
head, or "history" with the record that keeps it. A document is marked Historical only when every
row is closed. If the owner is a blocked file, the row stays open and the document stays current
until that file is free.

Checks common to every task:

- `python scripts/check_doc_links.py` over the 144 baseline files: no problem that is not in the
  baseline list T0 records.
- A Historical notice adds lines at the top and deletes none: `git diff --numstat` shows 0 deleted
  for the file. The notice uses the wording of `workflow_lisp_executable_ir.md` and names the
  current owner; the old status line stays below it.
- No file is renamed or moved (`git diff --name-status` shows only `M` and the one `A`).
- `pytest -q tests/test_first_hour_e2e.py tests/test_authoring_check_kit.py` after any task that
  touches the guide. Document-only tasks run no broader suite; T7, T14 and T15 run
  `pytest -q -n 16 --dist=worksteal --sample 10` because other sessions' code is merged between.
- Reviewer distinct from the author; the reviewer reads the ledger rows, not only the diff.

### Order

Wave 1 touches no blocked file and can start now. Wave 2 waits only for the other session's
commit. Wave 3 waits for code: the one-target cut and surface coherence changes E1, I1, C1, I2.

| Id | Task | Hours | Files | Waits for | Proof beyond the common checks |
| --- | --- | --- | --- | --- | --- |
| T0 | Baseline: record line counts per class, the link-check problem list and the guide's 19 inbound anchors in this plan's ledger; create the rule-ledger report with its header | 0.5 | this plan; the new report | - | The three commands and their output are in the ledger |
| T1 | Historical notice, nothing to move: `edit_and_continue_spike`, `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`, `trial_runs`, `mlevolve_...`; normalise the notice of `judgment_views`, `lexical_execution_checkpoints`, `provider_live_binding`, `provider_peer_messaging`. Their rows in the design index and the capability matrix say Historical and name the owner | 3 | those 10 design documents; `docs/design/README.md`; `docs/capability_status_matrix.md` | T0 | One ledger row per document saying which owner replaced it; for `lexical_execution_checkpoints`, the sentence of `specs/state.md` that carries its "no backward scan" rule |
| T5 | Frontend specification, removed material: move the bodies of sections 24, 26, 28 to 31, 86, 87, 107, 78.1, 79, 80, 109 and 94 to 98 and the Part VI diagram to `documentation-history/workflow_lisp_frontend_specification-history.md`; leave each heading or an `<a id>` and one line | 3 | the specification; its history file | T0 | Every anchor of a moved section still resolves from its inbound links; the moved text is byte-identical in the history file; the specification drops by the moved line count |
| T4c | Macros: rewrite specification Part VII (sections 32 to 37, 68) from `macro_surface_contract`; then mark that document Historical | 2 | the specification; `macro_surface_contract` | T5 | Ledger rows for its 9 live codes (2 are missing from the specification today: `macro_reserved_name`, `module_alias_duplicate`) |
| T4b | Prompts: check `prompt_calculus` and `prompt_identity_diagnostics` against specification 8.7.1 to 8.7.3 and 22.6 to 22.8; add what is missing; mark both Historical | 4 | the specification; the two documents | T4c | Rows for 35 and 12 live codes (3 and 6 are missing today); a row whose owner is `specs/providers.md` stays open until wave 2 |
| T4a | Check, add nothing expected: `numeric_surface` (5 of 5 codes carried), `transportable_value_type` (4 of 4), `pure_call_composition` (add `pure_call_representation_unsupported` to 8.6); mark the three Historical | 2.5 | the specification (8.6 only); the three documents | T0 | Ledger rows; the `bind-proc` defect that surface coherence section 12 assigns to pure-call composition is recorded against specification 7.8 |
| T4d | Conditionals: rewrite specification section 12 from `strict_boolean_control_flow` (`if`, `cond`, exact `Bool`, discriminant proof, diagnostics; no text about targets below the floor, no `resource-transition` example); mark it Historical | 3 | the specification (12); the document | T4a | Ledger rows; one probe per rule kept (the planning probes are a start) |
| T4e | Returns: a specification section for plain returns and `(result T ...)` guidance from `native_transportable_returns`; mark it Historical | 3 | the specification (new subsection under 8 or 22); the document | T4d | Ledger rows; the two source files that cite the document still name an existing path |
| T3a | Internal specification pages: `effect_graph`, `proof_graph`, `type_catalog`, `reference_catalog`, `source_map`, `legacy_adapter`. For each, list the rules; carry any that no owner has into specification 7, 11, 74 or the command adapter contract; mark Historical | 3 | the six documents; the specification; `workflow_command_adapter_contract.md` | T4e | Ledger rows; a rule that needs specification 16 is left open for T10 |
| T3b | Closed migration designs: `consolidation`, `runtime_migration_foundation`, `private_runtime_state_and_consumer_value_flow`, `procedure_migration_identity_compatibility`. Same procedure; owners are the specification (17.1), `specs/io.md`, `specs/versioning.md` | 4 | the four documents; those owners | T3a | Ledger rows; a row whose owner is evaluated execution or `specs/cli.md` stays open until wave 2 |
| T2 | Design index: one page in five parts (read first; feature contracts; tooling and internals; proposals not built; historical), each row one line; capability matrix rows for every document marked in wave 1 point to the owner | 2 | `docs/design/README.md`; `docs/capability_status_matrix.md` | T1, T3b | The index lists all 105 files once; no row calls a Historical document current |
| T6 | After the other session commits: normalise the notice of `provider_context_values`; `docs/index.md` rows and its "When Working On Workflow Lisp" path for everything marked so far; close ledger rows left open on blocked owners | 2 | `provider_context_values`; `docs/index.md`; evaluated execution, `specs/cli.md`, `specs/providers.md` only where a row needs a sentence | Blocked files clean | Open ledger rows: none from wave 1 |
| T7 | Guide, pass 1: every section of the table whose last column is `-`. Removed migration text goes to `documentation-history/docs-lisp_workflow_drafting_guide-history.md`; the REPL sections move to `docs/workflow_monitoring.md` with their inbound links (five found) updated; the "Not available" table is added | 6 | the guide; its history file; `docs/workflow_monitoring.md`; files holding those links | Blocked files clean; T6 | Ledger rows per removed section; all 19 anchors resolve; every complete `(workflow-lisp ...)` block left in the guide compiles at the current target (count in the ledger); expected size about 2,200 lines |
| T8 | Lists: merge `pure_list_traversal` into specification 10.3; mark it Historical | 4 | the specification (10.3); the document | I1 and E1 merged | Rows for 15 live codes (12 only there today) |
| T9 | Callables: merge `proc_refs_partial_application`, what survives of `let_proc_local_proc_refs`, and `write_once` section 6.3 into specification 7.8 and 14; mark the three Historical | 5 | the specification (7.8, 14); the three documents | C1 merged; the cut merged | Rows for the 9 procedure-reference codes (8 only there today); the 13 inbound anchors of `write_once` still resolve |
| T10 | Procedures and effects: merge `effect_ledger_simplification` and the boundary rule of `procedure_first_reuse_contract` into specification 8.8, 8.9, 16 and 106; mark both Historical | 4 | the specification; the two documents | The cut merged; E1 merged; blocked files clean | Ledger rows, among them `procedure_effect_ceiling_exceeded`; open rows of T3a closed |
| T11 | Loop values: check `value_and_continuation_composition` Increments 1 to 3 against specification 11 and 13.1 and `specs/dsl.md`; mark it Historical | 2 | the document; the specification only if a row needs it | E1 and I2 merged | Ledger rows |
| T12 | `executor_retirement`: check its source-floor and recovery rules against `specs/versioning.md` ("Targets and identity") and `specs/cli.md`; mark it Historical; the six maintained documents that cite it as owner cite `specs/` instead | 2 | the document; those six documents | The cut merged; blocked files clean | Ledger rows; its 21 inbound anchors resolve |
| T13 | Frontend specification, present tense: preamble to at most 40 lines; the 95-line ownership list of section 0 becomes a link to the design index; sentences of the form "at target 2.xx" and "below 2.xx" become rules; flat-route remnants in Parts VIII, X, XI and XII go to the history file | 5 | the specification; its history file | The cut merged; T8 to T10 | At most 4,600 lines; anchors resolve; ledger rows for removed sentences |
| T14 | Guide, pass 2: the sections 4b and surface coherence rewrote, cut to their targets; sections reordered to the outline | 5 | the guide | The cut and E1, I1, C1, I2 merged; T7 | At most 1,950 lines; anchors; blocks compile; ledger rows |
| T15 | Close: mark `surface_coherence` Historical if its section 11 conditions hold and `edit_and_continue` if Phase 3b has closed; final pass over the design index, `docs/index.md` and the matrix; final numbers in the ledger | 2 | those two documents; the three indexes | T8 to T14 | The numbers table below, re-measured |

Hours: wave 1 (T0, T1, T5, T4c, T4b, T4a, T4d, T4e, T3a, T3b, T2) 30; wave 2 (T6, T7) 8;
wave 3 (T8 to T15) 29; total 67.

**Smallest useful step:** T0, T1 and T2 alone (5.5 hours, T2 then covering only T1's documents)
take six documents out of the current set, make four ambiguous notices plain and give the design
index a reading path.

**Parallel:** T1 runs beside everything else in wave 1 (it shares no file with them). The tasks
that edit the specification form two lanes with disjoint sections, each lane serial:
T5, T4c, T4b (Parts VI, VII, XIII, XVII; sections 8.7 and 22) and T4a, T4d, T4e, T3a, T3b
(sections 7, 8.6, 11, 12, 74). T2 closes the wave. In wave 3, T11 and T12 run beside T8 to T10,
which are serial in the specification. None of the wave 1 tasks edits specification sections 7.8,
9, 10.3, 13.1, 14 or 16, which E1, I1, C1 and I2 will rewrite.

## Numbers

| Measure | Before (measured) | After wave 1 | After wave 3 |
| --- | --- | --- | --- |
| Workflow Lisp design documents not marked Historical | 53 | 30 | 20 (17 current, 3 proposals) |
| Their lines | 34,114 | about 23,709 | about 17,893 (16,872 current) |
| Workflow Lisp design documents marked Historical | 28 (18,693 lines) | 51 | 61 |
| Frontend specification | 4,800 lines | about 4,600 (T5 removes, T4 adds) | at most 4,600 |
| Authoring guide | 3,424 lines | 3,424 (blocked) | at most 1,950 (about 2,200 after T7) |
| Documents to read to learn the language | 12: the tutorial, the guide and the ten on its reading path; the guide links 27 design documents | same | 4: tutorial, guide, frontend specification, library reference |
| Documents deleted or renamed | - | 0 | 0 |

"After" figures for the specification and the guide are targets built from section sizes, not
measurements. The directory still holds 105 files and about 63,729 lines; what changes is how
many of them a reader must treat as current.

## Rulings

| # | Decision | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | The frontend specification is the one language reference; a feature design about core syntax or typing is merged into it and marked Historical | Surface coherence section 11 already sends its rules there and retires two feature designs on that condition. Today the specification cannot serve alone: no `cond`, one line on result guidance, 12 list-traversal codes absent | 23 of the 67 hours are merges. If the owner prefers a short specification with focused contracts, T4c to T4e and T8 to T11 are dropped and 10 more documents stay current |
| 2 | Eight feature contracts stay separate | Their codes are mostly in `specs/` already, or source and tests cite them (parametric types: 4 source files, 9 tests); an author needs them only when using the feature | 3,694 lines stay outside the reference |
| 3 | Nothing is deleted, moved or renamed | The conventions give no permission; 16 test modules and several source files cite design paths | The directory stays at 105 files; the index does the sorting |
| 4 | A proposal that was never built is listed as a proposal, not marked Historical | Historical in the conventions describes context that once was authority; the three parked designs can reopen under the roadmap's dispositions | 1,021 lines stay "not Historical" in the count |
| 5 | A document whose subject is deleted code is marked Historical with a notice and no rule check (T1) only when its own text already names another owner for what survives | Five such documents say so in their first lines | A surviving rule stays only in a Historical record; the notice still links it |
| 6 | The rule check is a ledger of normative sentences and live codes, in one report | It can be reviewed row by row; a full rewrite of 20 documents cannot | A rationale that is not phrased as a rule is found only through the Historical record |
| 7 | Sections that the cut or surface coherence will rewrite are not touched until they land | The stage 4 ledger holds the same rule for test files: touch once | Ten documents and the guide's second half stay as they are until that code merges |
| 8 | After the cut, `executor_retirement` becomes Historical and the notices of the design files that link it (39) are left alone | Editing up to 39 notices to save one hop is churn | Readers of old records take two hops to `specs/`; one `sed` fixes it later |
| 9 | The REPL how-to leaves the language guide for the monitoring guide | It teaches inspecting a run, not writing a workflow; the guide's own section 15 says operational detail belongs elsewhere | Five links move twice |
| 10 | Guide target 1,950 lines, not lower | Sum of per-section targets that keep every form that compiles today | A second pass could reach about 1,500 by moving the feature recipes (agent sessions, host input, phased delivery, confined children: 275 lines) to their contracts |
| 11 | Line counts are taken from the working tree | The other session's edits will be committed before the tasks that touch those files | Counts move by a few hundred lines if those edits are dropped |

## Not Verified While Planning

- The 53 documents not marked Historical were not read in full. Classes rest on headers, section
  outlines, the named-module and live-code checks, and inbound links. DUPLICATES in particular
  rests on code coverage (for example 32 of 35 for prompt calculus), not on comparing sentences.
  The rule ledger of each task is the real check and may reclassify a document.
- "Live code" counts include identifiers that are field names rather than diagnostics, and miss
  two-word codes.
- A probe found that reading a variant field directly after a discriminant test,
  `(if (= a.variant OK) a.n 0)`, fails at 2.40 with `compiler_defect` ("union field 'n' is absent
  or has variant-dependent types") in three shapes (union from a workflow input, from a procedure,
  from a command). The guide teaches this in sections 3.7 and 10; existing tests cover the shape
  that binds the field with `let*` inside the branch. Not investigated; reported to the
  coordinator.
- Not probed: `defmacro`, `:path :out` slots, confined children, `review-revise-loop` beyond its
  import, the guide's "Minimal Safe Subset" module as a whole, bundle-mode run references.
- The branches `feat/coherence-e1` and `feat/coherence-c1` exist; they were not read. Whether they
  already edit a specification section that a wave 1 task touches is unknown.
- Task 4b of the stage 4 plan does not list the frontend specification among its files; whether it
  edits it is unknown. T13 assumes it leaves the per-target prose in place.
- The sizes "at most 4,600" and "at most 1,950" are estimates. Hours are estimates.
- The link baseline (59) was taken with another session's uncommitted edits present.
- `docs/workflow_monitoring.md` was not read; ruling 9 names it from its title and its index row.
- The 23 design documents without the `workflow_lisp_` prefix were classified from their status
  line; the three indexed files outside `docs/design/` were not looked at.
- Whether `specs/state.md` carries the retained safety rules of `lexical_execution_checkpoints`
  was not checked; T1 checks it before normalising that notice.

## Ledger

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-13 | T0 done (branch `docs/corpus-wave1-notices` from `5e58ec41`, no uncommitted edits) | `python scripts/check_doc_links.py docs/*.md specs/*.md docs/design/*.md README.md workflows/README.md tests/README.md MIND_MAP.md docs/backlog/README.md prompts/README.md` (144 files): 59 problems with the checker as it was, 58 of them links to an existing `<a id>` the checker did not read; T0 taught `scripts/check_doc_links.py` `<a id>`/`<a name>` anchors (`tests/test_check_doc_links.py`), and the corrected count over the same tree is 1 (`workflow_lisp_provider_context_values.md`, a link to the deleted `lowering/effects.py`). The corrected list is the baseline. `wc -l` by class: OWNER 23,651, DUPLICATES 4,427, SUPERSEDED 2,913, DELETED CODE 2,040, NEVER BUILT 1,021, HISTORICAL 18,656; 81 files, 52,708 lines. `git grep` of guide anchors outside plans and reports: 18 distinct from 35 files. Lists and commands in the [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#baseline-t0), which T0 created |
| 2026-11-13 | T1 done | Historical notice (insertion after the title; body byte-identical to `5e58ec41`, checked with `cmp`) on `edit_and_continue_spike`, `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`, `trial_runs`, `mlevolve_workflow_lisp_system_architecture`; standard notice added above the non-standard one of `judgment_views`, `lexical_execution_checkpoints`, `provider_live_binding`, `provider_peer_messaging`. Every document read in full; rows 1.1 to 9.6 of the rule ledger; none refused. Owners in blocked files (evaluated execution, `specs/cli.md`, `specs/providers.md`, `workflows/README.md`, agent sessions) are quoted only where the sentence is also in the other session's working copy. Judgment call to review: `refactor_architecture` row 3.9 |
