# Workflow Lisp Design Corpus Consolidation Plan

**Status: Plan, revised 2026-11-13 after an independent review (accept with changes: 0 blockers,
6 major, 9 minor) and the coordinator's rulings on it.** T0, T1 and the first pass of T2 are done
on branch `docs/corpus-wave1-notices`, not yet merged. This page plans the documentation half of
stage 5 ("Surface coherence") of
[Lane D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed):
the stage ends with one current language reference and the superseded designs marked historical.
It is a plan, not a contract, and not copy-safe guidance. `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md) own behavior before, during
and after it. It changes no behavior: besides documents it touches one script (the link checker),
adds two small tests, and repoints one-line docstrings that name a retired document. No provider
spend.

Approach: sort the 81 Workflow Lisp design documents by what the code and the other documents say
about them; mark as Historical everything that is no longer an owner (bodies untouched); scope the
frontend specification to the language and carry into it, as one sentence with its diagnostic
codes, each rule that lives only in a feature design; cut the authoring guide to what compiles
today. Work that touches no file another session is editing comes first and is useful alone.

What this makes harder: a rule in the reference no longer sits beside its rationale, which stays in
a Historical record one link away; the estimate is a model (about 112.5 hours) that the
first merge task recalibrates; every retirement costs a reviewer's independent sample as well as an
author's ledger; the design files that link executor retirement (39) reach `specs/` in two hops
after the cut; and the reference test fails whenever a form is registered or removed without an
entry, which is its purpose.

## What Was Measured, And How

On `main` at `ae36901d`, in the working tree, which holds another session's uncommitted edits
(listed under [Blocked files](#blocked-files)), so line counts include them. T0 measured the
committed tree instead and its ledger row differs by about 100 lines.

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
  (44 programs). A probe tested a form, not the guide's own example, unless the table says so.
- **Linked from:** maintained documents (top-level `docs/*.md`, `specs/`, the three READMEs) that
  contain the file name ("index" is `docs/index.md`, "matrix" the capability matrix, "catalog"
  `workflows/README.md`); every document is also listed in `docs/design/README.md`. Plans and
  reports are not counted. Source and test files that cite the path are counted separately.
- **Tests that read documents:** none reads a design document or the guide from the working tree.
  `tests/test_first_hour_e2e.py` runs the tutorial's blocks, and no task edits the tutorial.
  `tests/test_authoring_check_kit.py` reads the guide with `git show` from a pinned commit. So no
  existing test guards this work; the checks are the link checker and the two tests the plan adds.
- **Links and anchors:** `scripts/check_doc_links.py` reported 59 problems over 144 maintained
  files. 58 were links to an `<a id>` the checker did not read. With the fix of T0 the baseline is
  1: a link in `workflow_lisp_provider_context_values.md` to the deleted `lowering/effects.py`.

## What The Review Found

The reviewer took one normative section from each of three documents this plan had classed as
duplicates and compared every sentence with the proposed owners:

| Document, section | Normative sentences | Present | Present but weaker | Absent |
| --- | --- | --- | --- | --- |
| `numeric_surface`, rules N1 to N7 | 25 | 17 | 4 | 4 |
| `transportable_value_type`, type rules, where allowed, runtime validation | 24 | 18 | 4 | 2 |
| `pure_call_composition`, language contract, evaluation and proof invariants | 16 | 6 | 4 | 6 |
| Total | 65 | 41 | 12 | 12 |

**About a third of a "duplicate" document's rules (24 of 65) have to be written or strengthened in
the owner before the document can be retired.** Several that are present live only in a
change-log entry of `specs/versioning.md`, and the specification's operator table states its rules
by citing "numeric surface rule N2/N3/N4". The first draft's "add nothing expected" was wrong, and
its 30 hours for wave 1 were low. Other findings applied below: the link checker could not see
`<a id>` anchors; a ledger proves nothing about a rule its author did not list; only 5 of the
guide's 51 Lisp blocks are complete modules, so "every complete block compiles" missed four stale
examples; reading a variant's field after a discriminant test is a compiler defect in four shapes;
and a 4,600-line specification would be another corpus, not a reference.

## What The Conventions Allow

- A historical document that is discoverable as current guidance gets a short scope notice; its
  body is preserved, not updated.
- A lasting rule is promoted to its owner before the document that held it is archived.
- Sections may be extracted from a maintained document into a historical record if cited anchors
  are kept or their incoming references updated. The directory
  `docs/reports/documentation-history/` already holds 51 such records.
- A whole document is not duplicated to shorten its introduction.
- A contract keeps its rules, invariants, limits and rationale. So current rationale is not moved
  into a Historical record: where it leaves the reference's reading path it goes to a current
  owner or to a closing appendix (T13).
- Nothing in the conventions permits deleting a historical record, and source files and tests
  cite design documents by path. **This plan deletes and renames no document.**
- A guide keeps prerequisites, current commands, choices and troubleshooting; past incidents and
  obsolete workarounds belong in a historical record. Guide text that only repeats another
  maintained document is removed, with the owner named in the rule ledger.

## Inventory: Workflow Lisp Design Documents

Classes: **OWNER** (rules live only here), **DUPLICATES** (current; most of its rules are restated
or owned elsewhere, and by the reviewer's sample about a third are not), **SUPERSEDED** (a later
design or the code replaced it), **DELETED CODE** (describes code or forms that are gone),
**NEVER BUILT** (a proposal), **HISTORICAL** (already marked). Document names omit the
`workflow_lisp_` prefix and `.md`. Task ids refer to [Tasks](#tasks); `-` means no task touches
the file.

| Document | Lines | Stated status | Role | Code check | Linked from | Class | Fate | Task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `agent_sessions` | 445 | First slice implemented at 2.38 | contract | `agent` registered at 2.40; probe builds | matrix, guide, specs/dsl | OWNER | Keep (feature contract) | - |
| `checked_program_evaluation` | 271 | Proposed; parked 2026-11-11 | proposal | no `eval-orc` head in the registry | matrix | NEVER BUILT | Leave; listed under proposals | T2a |
| `compile_time_parametric_specialization` | 441 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `composition_first` | 489 | Generic unions and `std/improve` implemented | contract | `std/improve` imports at 2.40 (probe) | matrix, library ref, specs/versioning; cited by 6 test files | OWNER | Keep; E1 removes its section 11.1 rule | - |
| `consolidation` | 253 | Current ownership topology after extraction | record | named modules exist except `executable_ir.py` | design index only | SUPERSEDED | Rule check (module topology goes to `orchestrator/workflow_lisp/README.md`), then Historical | T3b |
| `consumer_side_rendering` | 691 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `core_calculus_middle_end` | 813 | Accepted architecture; flat route retired | contract | `workflow_lisp/wcc/` exists | README, matrix, index; cited by 2 source and 1 test files | OWNER | Keep (compiler internals, not on the author's path) | - |
| `core_stmt_taxonomy` | 168 | Historical; code removed 2026-11-12 | record | `core_ast.py` gone | design index only | HISTORICAL | Leave | - |
| `core_workflow_ast` | 94 | Historical; code removed 2026-11-12 | record | `core_ast.py` gone | design index only; cited by 1 source files | HISTORICAL | Leave | - |
| `debug_yaml_renderer` | 70 | Historical | record | n/a | matrix | HISTORICAL | Leave | - |
| `durable_host_input` | 500 | Current feature contract, target 2.40 | contract | `request-input` probe builds at 2.40 | architecture, matrix, index, specs/versioning | OWNER | Keep (feature contract) | - |
| `edit_and_continue` | 943 | Accepted as basis for a plan; Phase 3b in execution | proposal becoming contract | partly implemented (3b tasks merged) | matrix | OWNER | Historical when Phase 3b closes and evaluated execution carries it (that plan's call) | T15 |
| `edit_and_continue_spike` | 487 | Feasibility spike; 3a landed elsewhere | record | prototype deleted (its own words) | design index only | SUPERSEDED | Historical notice (done on the wave 1 branch) | T1 |
| `effect_graph` | 153 | Current-checkout component contract | contract | class `EffectGraph`: 0 hits, but `EffectSummary` (17 files) and the two effect summaries it describes are live | matrix; cited by 1 source files | DUPLICATES | Rule check; carry the few rules found only here; then Historical | T3a |
| `effect_ledger_simplification` | 426 | Accepted 2.39 contract | contract | `procedure_effect_ceiling_exceeded` in code; probe builds | matrix, guide, specs/index, specs/versioning | OWNER | Merge into the specification after the cut, then Historical | T10 |
| `evaluated_execution` | 3,308 | Current execution contract | contract | 96 of 98 named modules exist | README, architecture, matrix, index, guide, Python guide, lifecycle, 6 specs | OWNER | Keep (the runtime design) | - |
| `executable_ir` | 309 | Historical | record | `executable_ir.py` gone | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `executor_retirement` | 274 | Current cutoff and recovery contract | contract | `workflow_execution_target_retired` refuses 2.34 (probe) | matrix, index, library ref, OMP runbook, lifecycle, catalog, 4 specs | OWNER | Historical after the cut, if `specs/` carry its rules | T12 |
| `frontend_deduplication` | 102 | Incorporated; companion decision record | record | n/a | index | DUPLICATES | Historical notice (done on the wave 1 branch) | T1 |
| `frontend_mvp_specification` | 585 | Historical | record | n/a | index, MVP comparison; cited by 4 source files | HISTORICAL | Leave | - |
| `frontend_specification` | 4,800 | Accepted baseline | contract | 60 registered heads named; 3 absent (`cond`, `provider-bundle-path`, `workflow-ref`); 70 of 82 without a heading or table row; 9 removed heads still named | README, matrix, index, guide, LSP setup, MVP comparison, gap list, 3 specs; cited by 4 source and 3 test files | OWNER | Keep, scoped to the language (Parts I to VII); slim and absorb rules only | TR, T5, T5b, T4, T8-T13 |
| `generic_core_expression_surface_adapter_retirement` | 1,824 | Historical | record | n/a | matrix, index, guide | HISTORICAL | Leave | - |
| `generic_resource_context_core` | 578 | Historical | record | n/a | design index only | HISTORICAL | Leave | - |
| `judgment_views` | 986 | Scope notice plus 'retained read-only contract' | record | `report` projection removed; 18 of 26 named codes gone | matrix, index, guide; cited by 1 test files | HISTORICAL | Notice normalised (done on the wave 1 branch) | T1 |
| `key_migration_parity_architecture` | 1,684 | Historical | record | n/a | index, gap list | HISTORICAL | Leave | - |
| `language_server` | 2,556 | Current tooling contract L0-L5 | contract | `orchestrator/lsp` exists | matrix, index, guide, LSP setup; cited by 2 test files | OWNER | Keep (tooling) | - |
| `legacy_adapter` | 83 | Current adapter-quarantine policy | contract | class `LegacyAdapter`: 0 hits; lowercase name in `lints.py` | design index only | DUPLICATES | One paragraph into the command adapter contract, then Historical | T3a |
| `let_proc_local_proc_refs` | 1,264 | Implemented V1; W3 at 2.36 | contract | `let-proc` probe builds (W3 form) | matrix, index, guide; cited by 1 source files | OWNER | Merge what survives the cut into specification 7.8, then Historical | T9 |
| `lexical_checkpoint_resumability` | 859 | Historical | record | n/a | design index only | HISTORICAL | Leave | - |
| `lexical_execution_checkpoints` | 132 | Predecessor architecture; retained safety notes | record | old checkpoints not used by the memo (its own words) | matrix, index; cited by 1 test files | HISTORICAL | Notice normalised (done on the wave 1 branch) | T1 |
| `lsp_authored_reference_navigation` | 230 | Historical | record | n/a | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `lsp_diagnostic_lifecycle_and_progress` | 407 | Historical | record | n/a | matrix, index, LSP setup; cited by 1 test files | HISTORICAL | Leave | - |
| `macro_surface_contract` | 240 | Accepted current-surface contract | contract | `defmacro` registered; 7 of 9 live codes also in the specification | matrix, index, guide | OWNER | Merge into specification Part VII, then Historical | T4c |
| `native_transportable_returns` | 1,047 | Accepted; implemented at 2.15 | contract | `(result T ...)` probe builds; specification has no section for it | matrix, gap list; cited by 2 source files | OWNER | Merge surface rules into the specification, then Historical | T4e |
| `numeric_surface` | 203 | Implemented at 2.34 | contract | 5 of 5 live codes in the specification and `specs/` | matrix, guide, specs/versioning; cited by 2 source and 3 test files | DUPLICATES | Carry the rules the owners lack (sampled: about a third), then Historical | T4a |
| `parametric_type_system` | 742 | Current implemented parametric contract | contract | 23 live codes, 11 only here; 4 source files and 9 tests cite it | matrix, index, guide, specs/versioning; cited by 4 source and 9 test files | OWNER | Keep (feature contract) | - |
| `phased_contract_delivery` | 672 | Selected 2.39 migration; retained historical protocol | contract | phased probe reaches its own policy check | matrix, index, guide, tests README, 4 specs; cited by 1 test files | OWNER | Keep (feature contract) | - |
| `post_foundation_composition_stdlib_migration` | 2,855 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `private_runtime_state_and_consumer_value_flow` | 672 | Partial; C2-C6 dropped 2026-11-11 | contract in part | 1 live code, also in `specs/` | matrix, index | SUPERSEDED | Rule check, then Historical | T3b |
| `proc_refs_partial_application` | 350 | Implemented design delta | contract | 9 live codes, 8 only here | matrix, index | OWNER | Merge into specification 7.8, then Historical | T9 |
| `procedure_first_reuse_contract` | 401 | Accepted; adoption gated | contract | `:lowering` refuses at 2.40 (probe) | matrix, index, guide | DUPLICATES | Merge the boundary rule after the cut, then Historical | T10 |
| `procedure_migration_identity_compatibility` | 587 | Durable principles; historical generator | contract in part | 0 live codes; 'no generator or shim remains' | matrix, index; cited by 2 test files | DELETED CODE | Rule check, then Historical | T3b |
| `program_search_boundaries` | 134 | Adopted position statement | contract | n/a (invariants) | matrix | OWNER | Keep | - |
| `progressive_execution` | 291 | Draft target; not implemented | proposal | no code named | matrix | NEVER BUILT | Leave; listed under proposals | T2a |
| `prompt_calculus` | 859 | Accepted and implemented Q1-Q3 | contract | 32 of 35 live codes in the specification; 7 of 13 named modules gone | matrix, index, guide; cited by 1 test files | DUPLICATES | Carry the rules the specification lacks, then Historical | T4b |
| `prompt_identity_diagnostics` | 1,125 | Accepted, target 2.22 | contract | 12 live codes, 26 named codes gone | matrix, index, guide; cited by 1 test files | DUPLICATES | Carry the live rules the specification lacks, then Historical | T4b |
| `proof_graph` | 74 | Current typed proof contract | contract | class `ProofGraph`: 0 hits; its proof-neutral rule is live | matrix | DUPLICATES | Rule check; carry the few rules found only here; then Historical | T3a |
| `provider_call_policy` | 88 | Current component contract | contract | 88 lines; 1 live code only here | matrix, index | OWNER | Keep (small) | - |
| `provider_context_values` | 561 | Historical 2.31 slice; native context proposed | record | `:capture-context` still parses (probe); no evaluated port (its own words) | matrix, guide | HISTORICAL | Normalise the notice (file blocked) | T6 |
| `provider_live_binding` | 69 | Retained routing; historical protocol | record | `with-live-providers` registered; build refuses (stage 4 plan) | matrix, index, guide, specs/index; cited by 2 test files | HISTORICAL | Notice normalised (done on the wave 1 branch) | T1 |
| `provider_peer_messaging` | 59 | Retained routing; historical protocol | record | `with-live-provider-peers` registered; build refuses (stage 4 plan) | matrix, index, guide, specs/index | HISTORICAL | Notice normalised (done on the wave 1 branch) | T1 |
| `provider_prompt_dependencies` | 106 | Current component contract | contract | 106 lines; named modules exist | matrix, index | OWNER | Keep (small) | - |
| `provider_prompt_queue` | 313 | Historical | record | n/a | matrix, index | HISTORICAL | Leave | - |
| `pure_call_composition` | 435 | Implemented at 2.30; incorporated in specification 8.6 | contract | 1 live code, only here | matrix; cited by 1 test files | DUPLICATES | Carry the rules specification 8.6 lacks (sampled: 10 of 16), then Historical | T4a |
| `pure_list_traversal` | 460 | Implemented at 2.18 | contract | 15 live codes, 12 only here; specification 10.3 defers to it | matrix, index; cited by 1 test files | OWNER | Merge into specification 10.3 after I1, then Historical | T8 |
| `pure_result_replay` | 919 | Historical | record | n/a | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `refactor_architecture` | 284 | Draft architecture guidance | proposal | `lowering.py` gone; its plan ran in June | index | SUPERSEDED | Historical notice (done on the wave 1 branch) | T1 |
| `reference_catalog` | 77 | Current reference-kind contract | contract | class `ReferenceCatalog`: 0 hits | design index only | DELETED CODE | Rule check, then Historical | T3a |
| `repl` | 489 | Implemented | contract | `repl` command exists | matrix, index, guide, specs/cli | OWNER | Keep (tooling) | - |
| `repl_introspection` | 307 | Implemented | contract | 17 of 17 named modules exist | matrix, index, guide, specs/cli | OWNER | Keep (tooling) | - |
| `review_revise_stdlib_parametric_integration` | 2,972 | Historical | record | n/a | index, guide | HISTORICAL | Leave | - |
| `run_ref_expression_environments` | 652 | Partial at 2.38; provider part dropped | contract | 12 of 13 live codes also in `specs/` | matrix, index, library ref, guide, 7 specs | OWNER | Keep (feature contract) | - |
| `runtime_closures_boundary` | 669 | Deferred acceptance contract | contract (guardrail) | nothing to build by design; surface coherence cites it | matrix, index | OWNER | Keep | - |
| `runtime_migration_foundation` | 1,217 | Implemented foundation; promotion gate retired | contract in part | 10 of 12 named codes gone | matrix, index | SUPERSEDED | Rule check, then Historical | T3b |
| `runtime_native_drain_authoring` | 880 | Historical; forms removed 2026-11-12 | record | heads refuse `form_retired` | matrix, index, guide | HISTORICAL | Leave | - |
| `semantic_workflow_ir` | 187 | Historical; code removed 2026-11-12 | record | `semantic_ir.py` gone | matrix, index; cited by 1 test files | HISTORICAL | Leave | - |
| `shared_owner_lane_prerequisites` | 612 | Reference target / prerequisite ledger | record | 37 mentions of removed heads | index | DELETED CODE | Historical notice (done on the wave 1 branch) | T1 |
| `source_map` | 382 | Accepted | contract | class `SourceMap`: 0 hits; sidecar retired | matrix; cited by 1 source files | DUPLICATES | Rule check against the home T5b gives specification 74, then Historical | T3a |
| `source_site_inspection` | 302 | Implemented offline; unselected | contract | `source_sites.py` and 3 test modules exist | matrix, index; cited by 1 source and 3 test files | OWNER | Keep (search tooling) | - |
| `state_layout` | 154 | Historical; code removed 2026-11-12 | record | `state_layout.py` gone | matrix; cited by 1 test files | HISTORICAL | Leave | - |
| `stdlib_lowering` | 192 | Historical; forms removed 2026-11-12 | record | heads refuse `form_retired` | design index only; cited by 1 source files | HISTORICAL | Leave | - |
| `strict_boolean_control_flow` | 658 | Accepted; implemented at 2.26 | contract | `cond` registered; specification 12 has no `cond` | matrix | OWNER | Rewrite specification 12 from it after the variant-field fix, then Historical | T4d |
| `structural_parametric_constraints` | 321 | Historical | record | n/a | index | HISTORICAL | Leave | - |
| `surface_coherence` | 405 | Accepted 2026-11-12; not implemented | contract until retired | branches in flight | design index only | OWNER | Historical when its section 11 conditions hold | T15 |
| `transportable_value_type` | 318 | Current implemented transport contract | contract | 4 of 4 live codes in the specification and `specs/` | matrix, index; cited by 1 test files | DUPLICATES | Carry the rules the owners lack (sampled: about a third), then Historical | T4a |
| `trial_runs` | 381 | Partial; `trial` removed 2026-11-12 | contract in part | `trial` refuses `form_retired` (probe) | matrix, specs/index | DELETED CODE | Historical notice (done on the wave 1 branch) | T1 |
| `type_catalog` | 156 | Current shared typed catalog | contract | class `TypeCatalog`: 0 hits; its type families and `value_guidance_example_unsupported` are live | design index only; cited by 1 source and 1 test files | DUPLICATES | Rule check; carry the few rules found only here; then Historical | T3a |
| `typed_program_gates` | 459 | Accepted; C2 dropped, C1/C3 parked | proposal | 14 of 16 named codes absent | matrix | NEVER BUILT | Leave as a proposal; its notice says C2 is dropped | T2b |
| `unified_frontend_design` | 153 | Historical unified proposal | record | n/a | index | HISTORICAL | Leave | - |
| `value_and_continuation_composition` | 519 | Current for Increments 1-3; 4-5 retired | contract in part | 1 live code, also in `specs/` | matrix | DUPLICATES | Rule check after E1 and I2, then Historical | T11 |
| `write_once` | 574 | W3 implemented; W0/W1 unselected, W4 dropped | contract in part | W3 `let-proc` probe builds | matrix, library ref, guide, specs/index, specs/versioning | OWNER | Merge section 6.3 into specification 7.8, then Historical | T9 |

| Class | Documents | Lines |
| --- | --- | --- |
| OWNER | 28 | 23,713 |
| DUPLICATES | 13 | 4,810 |
| SUPERSEDED | 5 | 2,913 |
| DELETED CODE | 4 | 1,657 |
| NEVER BUILT | 3 | 1,021 |
| HISTORICAL | 28 | 18,693 |
| Total | 81 | 52,807 |

The review moved `effect_graph`, `proof_graph` and `type_catalog` from DELETED CODE to DUPLICATES:
the classes they name are gone, but the summaries, type families and proof rules they describe are
live. Five of the 28 HISTORICAL documents carried a notice in a non-standard form; T1 normalised
four and `provider_context_values` waits for T6.

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
| `mlevolve_workflow_lisp_system_architecture` | 951 | 'Draft design'; dropped 2026-11-11 | NEVER BUILT | Historical notice (T1, done on the wave 1 branch) |
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
[drafting guide](../lisp_workflow_drafting_guide.md) (how to write), the
[library reference](../lisp_library_reference.md) (which helper). The frontend specification is
the reference: the place to look up what a form means and which codes it refuses with, not a text
to learn from. `specs/` stay normative for runtime and DSL behavior. Evaluated execution is the
one runtime design, read for resume, identity and the memo.

| Current set after this plan | Documents | Lines now | Lines after |
| --- | --- | --- | --- |
| Language reference: `frontend_specification`, scoped to the language | 1 | 4,800 | 2,800 to 3,200 |
| Runtime design: `evaluated_execution` | 1 | 3,308 | unchanged by this plan |
| Feature contracts, read when the feature is used: `parametric_type_system`, `composition_first`, `agent_sessions`, `durable_host_input`, `phased_contract_delivery`, `run_ref_expression_environments`, `provider_call_policy`, `provider_prompt_dependencies` | 8 | 3,694 | unchanged |
| Boundaries: `program_search_boundaries`, `runtime_closures_boundary` | 2 | 803 | unchanged |
| Tooling and compiler internals: `language_server`, `repl`, `repl_introspection`, `source_site_inspection`, `core_calculus_middle_end` | 5 | 4,467 | plus the live internals T5b re-homes (at most about 400) |
| **Current Workflow Lisp design documents** | **17** | **17,072** | **about 15,472 at most** |
| Proposals, not built, listed apart: `checked_program_evaluation`, `progressive_execution`, `typed_program_gates` | 3 | 1,021 | unchanged |

### The reference, part by part

The specification is 4,800 lines today. Only Parts I to V and VII describe the language.

| Part of the specification | Lines today | Fate | Task |
| --- | --- | --- | --- |
| Before Part I: status prose, reader paths, section 0 (boundaries, a 95-line ownership list, an implementation gate), sections 1 to 3 (thesis, goals, non-goals) | 704 | At most 40 lines of status and reading path (the form index opens Part I). Target and ownership prose to the history file. Sections 1 to 3 are rationale: dropped where the design principles already say it, else a closing appendix | T13 |
| Parts I to V: surface, expressions and control, effects and authority, state and contexts, provider and command | 2,376 | The reference. Gains one sentence and the codes for each merged rule, in the entry of the form it governs; loses the body of section 24 and per-target prose | TR, T4a to T4e, T3a, T8 to T11, T13 |
| Part VI: procedural library | 368 | Section 27, `review-revise-loop` (105 lines), stays as that head's entry. The other bodies move; headings stay | T5 |
| Part VII: macros | 122 | Rewritten to the implemented contract | T4c |
| Part VIII: compiler intermediates | 146 | Live internals to `core_calculus_middle_end`; the rest to the history file | T5b |
| Part X: validation passes; Part XI: error taxonomy; Part XVI: lints | 172 + 120 + 58 | These hold language rules and live codes. Each goes to the entry of its form; dead codes and flat-route passes go to the history file | T13 |
| Part XII: source maps, observability, build artifacts, editor compatibility | 360 | Section 74 and 76.1 to `language_server` unless it already carries them; the rest to the history file | T5b |
| Parts XIII (CLI), XIV (library sketch), XVII (testing strategy), XX (open decisions) | 56 + 123 + 101 + 27 | `specs/cli.md` and the library reference own the live parts; the rest to the history file | T5b |
| Part XIX: resolved decisions (sections 106 to 108) | 67 | Sections 106 and 108 are rules with 8 inbound links: folded into 8.8 and 15 after the cut, anchors kept. Section 107 with the removed forms | T5, T10 |

Expected size: about 3,800 lines after T5 and T5b, about 4,050 at the end of wave 1 (merged rules
add about 250), 2,800 to 3,200 after T13. These are sums of section sizes, not
measurements.

### The reference test

`tests/test_workflow_lisp_reference_coverage.py`, written in TR, reads the specification between
the headings of Part I and Part VIII (the whole file once the later parts are gone) and asserts:

1. Every head of `registered_form_heads()` at the current target, and every head of
   `RETIRED_FORMS`, has an **entry**: it appears in backticks in a heading, or in the first cell
   of a row of the form index or of the removed-forms table.
2. Every backticked identifier of two or more words is a string literal in `orchestrator/`,
   unless it is in one of two lists in the test: names that are not diagnostics (field and step
   names; 13 today), and codes not found in `orchestrator/`, which T4b and T4c remove or correct (10 today, 7 of
   them `macro_*`). The test
   also asserts that each listed name still occurs in the reference, so a list can only shrink.

Measured today: by plain text search 3 registered heads do not occur in the specification at all
(`cond`, `provider-bundle-path`, `workflow-ref`); `loop-state` occurs only as an adjective and
`workflow-lisp` once in a code block; and 70 of the 82 heads have neither a heading nor a table
row of their own (the 37 operators sit in the second cell of the operator table; `call`,
`command-result`, `record`, `request-input` and `run-ref` appear only in headings without
backticks, in code blocks, or outside Parts I to VII). The form index, about 95 rows, gives every
head an entry and a link to its defining section; it is written by hand and kept true by the
test. Six retired heads have no heading (`defresource`, `deftransition`, `materialize-view`,
`produce-one-of`, `provider`, `trial`); the removed-forms table lists all eleven. Nothing is
generated.

A merged rule has one shape: a sentence, then `Diagnostics:` and the codes, inside the entry of
the form. Rationale, examples beyond one, history and review notes stay in the document that
becomes Historical.

### Every other document, by fate

- **Historical notice, no rule to move** (T1, done on the branch): `edit_and_continue_spike`,
  `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`,
  `trial_runs`, `mlevolve_workflow_lisp_system_architecture`; four non-standard notices
  normalised.
- **Carry the missing rules, then Historical** (T3a, T3b, T4a to T4e in wave 1; T8 to T11 after
  the code changes): the 13 DUPLICATES less `frontend_deduplication`, the four closed migration
  designs, `reference_catalog`, and the feature designs that own rules (`macro_surface_contract`,
  `strict_boolean_control_flow`, `native_transportable_returns`, `pure_list_traversal`,
  `proc_refs_partial_application`, `let_proc_local_proc_refs`, `write_once`,
  `effect_ledger_simplification`).
- **Historical when another plan finishes** (T12, T15): `executor_retirement` after the one-target
  cut, `surface_coherence` when its own section 11 says so, `edit_and_continue` when Phase 3b
  closes.
- **Leave:** the 23 documents already Historical with a standard notice, the proposals, and the
  current set above.

## The Authoring Guide

3,424 lines in the working tree (3,363 at `HEAD`; the difference is another session's
uncommitted REPL text). It links 27 design documents (27,734 lines) and its "current contract
reading path" names ten documents. Its anchors are linked from outside plans and reports (T0
counted 18 distinct anchors from 35 files); every one must still resolve, and with the corrected
checker an `<a id>` is enough.

It has 51 Lisp blocks, of which 5 are complete modules. The planning probes compiled forms, not
these blocks. Four examples are known stale: 5.6 (`:lowering`), 6.3 (`path/join`), 11
(`phase-target` with a string) and 18 (`:effects` on a `defworkflow`); 3.7 and 10 teach a shape
that fails with a compiler defect. T7 and T14 compile every block.

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
| 2A. Program Shapes | 72 | Shape table, admitted effects, unavailable list, public commands, closures | Table rows hold today; the unavailable paragraph lists `request-input`, which builds, and phased delivery, whose probe gets past the stated refusal | Shorten; unavailable things go to one table | 35 | 4b, E1, I1 |
| Static command arguments and shared closures | 41 | `:argv` omission and the shared closure envelope | Yes (`command-result` probes) | Keep | 35 | - |
| A complete recipe | 158 | Compile, run, resume, report, invalidate on a fixture | Yes (owned by a test); overlaps the tutorial and the lifecycle guide | Shorten to the source and six commands; keep the anchor | 40 | - |
| Print a value during a run | 9 | `print` | Yes (probe) | Keep | 9 | - |
| Inspect a run with the REPL (two sections) | 157 | REPL session, capture rules, a worked lookup | Yes; 63 of these lines are another session's uncommitted additions | Leave as written; shorten only if that session agrees | 157 | - |
| 3. Semantic Authority Rules (3.1-3.8) | 159 | Eight authority rules with bad/good pairs | Rules, not forms; 3.7 teaches reading a field after a discriminant test, which fails today with `compiler_defect` (fix in progress) | Shorten to one table and two examples; absorbs section 12; a defect note if the fix has not merged | 60 | - |
| 4. Choosing The Right Authoring Unit | 19 | Which form for which need | Yes; two rows describe removed things | Keep without those rows | 17 | - |
| 5. Types First (5.1-5.5) | 164 | `defpath`, `defenum`, `defrecord`, `defunion`, `defschema` | Forms yes (probes of `defpath`, `defschema`, `variant`, `match`); the guide's own blocks are compiled in T7 | Keep; drop the pointer to a historical design in 5.2 | 150 | - |
| 5.6 Loose Transport With `Value` | 31 | `Value` | Type yes; the example's `:lowering` refuses at 2.40 (`proc_lowering_annotation_invalid`) | Keep; fix the example | 28 | 4b |
| 6.1 `defworkflow` | 51 | Workflow boundaries and defaults | Yes (probe with `:default`) | Keep | 45 | C1 |
| 6.2 `defproc` and procedure contracts | 149 | Effects inference, restrictions, generics; an older-contract example; compiler carrier names | 2.39 contract yes (probe); older example refuses | Shorten: one contract, constraints list to a pointer, drop carrier detail | 75 | 4b, C1 |
| 6.3 `defun` | 24 | Pure helpers | Form yes; the example no: `path/join` is not a registered operator (`pure_expr_operator_unsupported`, reviewer's probe) and its return type is undefined | Keep; fix the example | 20 | - |
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
| 10. Pattern Matching And Variant Proof; 10.1 | 82 | `match`, `if`/`cond` proof, a `Blocked` variant | `match` yes; the `if`/`cond` proof example fails today with `compiler_defect` (fix in progress) | Keep; re-probe after the fix; a defect note if it has not merged | 75 | - |
| 11. Contexts And Derived State (11.1, 11.2) | 127 | Context records for phases, items and drains; boundary classes; path ownership | Mostly no: drains and resources removed; `(phase-target ctx "x.md")` refuses with a bound `PhaseCtx` too (`phase_target_name_invalid`) | Shorten to the path-ownership table | 30 | - |
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

Sum of targets: 2,075 lines, plus the table below. **Target for the guide: at most 2,100
lines**, about 39% shorter. Things that do not run (context capture,
session artifacts, prompt-identity reports, judgment views, live supervision, peer groups,
bundle-mode run references, the removed forms) take one table of about 12 rows, "Not available",
with the refusal code and the owner of each. The REPL sections (157 lines) stay as the other
session wrote them; if that session homes them in the monitoring guide instead, the target is
1,950.

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
13. Inspecting a run (REPL); debugging and lints; not available; migrating from an older target
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

### The retirement guard

Every task that marks a document Historical, T1 included: the author reads the document in full
and **refuses to mark it** if a rule in it is still true and has no current owner. The author
either carries that rule first (a ledger row) or leaves the document current and records why.

### How a task proves no rule was lost

One report, `docs/reports/2026-11-13-design-corpus-rule-ledger.md`, created by T0 and appended by
every task that retires a document or removes text from the guide or the specification. One row
per rule: the document and section; the rule as written; the owner file and anchor; the proof.

- **The author** finds rules by reading for sentences that require, forbid, bound or refuse, and
  by listing the document's live codes. A row may instead say "describes removed code" with the
  removed module or head, or "history" with the record that keeps it.
- **A diagnostic code is proved by grep**: the code is a string literal in `orchestrator/` and
  occurs in the owner. No quotation is needed.
- **A prose rule is proved by the owner's sentence, quoted.** The owner's sentence states the
  rule itself. It may not cite the document being retired ("numeric surface rule N3" is not an
  owner sentence); such citations are rewritten.
- **The reviewer**, who is not the author, picks one section of each retired document, extracts
  its normative sentences without looking at the ledger, and checks each against the rows. One
  sentence with no row, or with a row whose owner sentence is weaker, reopens the document.
- A document is marked Historical only when every row is closed and the reviewer's sample passes.
  If the owner is a blocked file, the row stays open and the document stays current.
- A source docstring that names the retired document as its contract is repointed to the new
  owner in the same task (one line, no behavior change).

Checks common to every task:

- `python scripts/check_doc_links.py` (with the fix of T0) over the 144 baseline files, the rule
  ledger and every `documentation-history/` file the task wrote: nothing beyond the one baseline
  problem.
- A Historical notice adds lines at the top and deletes none (`git diff --numstat` shows 0
  deleted). It names the current owner; where that would be executor retirement it names
  `specs/versioning.md` or `specs/cli.md` instead, since that page is itself retired by T12.
- No file is renamed or moved (`git diff --name-status` shows only `M` and intended `A`).
- The reference test, once TR has merged.
- No per-task pytest beyond that: no existing test reads these documents. T7, T14 and T15 run
  `pytest -q -n 16 --dist=worksteal --sample 10` because other sessions' code is merged between.

### The estimate

The first draft gave wave 1 30 hours. Re-estimated with the review's finding:

- rules per document: 0.65 of the sentences that carry a normative word (counted by script; the
  discount is an assumption);
- a rule that is present in the owner costs 1.5 minutes; a weaker or absent one costs 8 minutes
  (one sentence, its codes, a probe where it is behavior); a row for removed code costs 1 minute;
- 36% of live rules are weaker or absent for a DUPLICATES document, 60% for an OWNER whose section
  the specification lacks;
- 0.75 hours per document for the full read, the notice and the author's side of the review.

That gives wave 1 62 hours (53.5 for the tasks the review saw, which it
expected to take 45 to 60, and 8.5 for TR and T5b, which ruling 1 adds); 112.5 hours in
all, with a plausible range of 90 to 130. The reviewer's sampling is extra: about 25 minutes per
retired document, 13 hours over the plan.

**Checkpoint after T4a.** T4a records minutes per ledger row. If its three documents take more
than 10 hours or fewer than 5, the remaining rows of the task table are re-estimated and the
change is recorded in the ledger before T4e starts.

### Order

Wave 1 touches no blocked file. Wave 2 waits only for the other session's commit. Wave 3 waits for
code: the one-target cut and surface coherence changes E1, I1, C1, I2.

| Id | Wave | Task | Hours | Files, and the specification sections it may edit | Waits for | Proof beyond the common checks |
| --- | --- | --- | --- | --- | --- | --- |
| T0 | 1 | Baseline; rule-ledger report created; the link checker taught `<a id>` and `<a name>` anchors, with a test; corrected baseline recorded. **Done on the wave 1 branch** | 1.5 | `scripts/check_doc_links.py`; `tests/test_check_doc_links.py`; this plan's ledger; the rule-ledger report | - | Ledger row |
| T1 | 1 | Historical notice on `edit_and_continue_spike`, `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`, `trial_runs`, `mlevolve_...`; notice normalised on `judgment_views`, `lexical_execution_checkpoints`, `provider_live_binding`, `provider_peer_messaging`. Each document read in full under the retirement guard. **Done on the wave 1 branch** | 5 | those 10 design documents | T0 | Ledger rows 1.1 to 9.6 of the report; `docs/index.md` still calls two of them component contracts until T6 (blocked file) |
| T2a | 1 | Design index in five parts; capability matrix rows of T1's documents name the current owner. **Done on the wave 1 branch** | 1.5 | `docs/design/README.md`; `docs/capability_status_matrix.md` | T1 | The index lists all 104 other files once |
| TR | 1 | The reference knows every form. A test (about 25 lines) asserts that every head of `registered_form_heads()` at the current target and of `RETIRED_FORMS` has an entry in Parts I to VII, and that every backticked identifier of two or more words there is a string literal in `orchestrator/`, less two lists in the test that may only shrink (see [The reference test](#the-reference-test)). To make it pass: a "Form index" table (head, kind, defining section) and a "Removed forms" table (head, what it was, tag); entries for `cond` (a stub that T4d replaces), `loop-state`, `workflow-ref`, `provider-bundle-path` and the `workflow-lisp` header | 4.5 | Specification: a new "Form Index" section at the head of Part I; section 4; section 12 (stub); a new 13.2 after 13.1; the end of section 15; section 22 before 22.4. `tests/test_workflow_lisp_reference_coverage.py` | T0 merged | The test fails before the tables exist and passes after; `pytest --collect-only` on the new module; each new entry has a compile probe |
| T5 | 1 | Removed forms: the bodies of specification sections 24, 26, 28 to 31, 86, 87 and 107 and the Part VI diagram move to the specification's history file. Every heading stays, with one line | 3 | Specification: section 24; Part VI except section 27; sections 86, 87, 107. `documentation-history/workflow_lisp_frontend_specification-history.md` | T0 merged | Moved text identical apart from relative links, which are rewritten for the new directory and checked there; the specification drops by the moved line count |
| T5b | 1 | Off the reader's path: Parts VIII, XII, XIII, XIV, XVII and XX (813 lines). A disposition row per section: dead text to the history file; live compiler internals to `core_calculus_middle_end`; editor compatibility (76.1) and source-map rules (74) to `language_server` unless already there; CLI and library text dropped where `specs/cli.md` or the library reference already says it | 4 | Specification from Part VIII on, except Parts X, XI, XVI, XIX; the history file; `workflow_lisp_core_calculus_middle_end.md`; `workflow_lisp_language_server.md` | T5 | Ledger row per section; the one inbound anchor (76.1) resolves; links in the history file checked |
| T4c | 1 | Macros: rewrite Part VII from `macro_surface_contract`, rules and codes only; the 7 `macro_*` codes the specification names and the code lacks go; mark the document Historical | 3 | Specification Part VII, section 8.7 (`defmacro`), section 68. `macro_surface_contract` | T5b | Ledger rows; the test's pending list loses the `macro_*` names |
| T4b | 1 | Prompts: carry what `prompt_calculus` and `prompt_identity_diagnostics` hold and the specification lacks; mark both Historical | 7 | Specification 8.7.1 to 8.7.3 and 22.6 to 22.8. The two documents | T4c | Ledger rows (35 and 12 live codes; 3 and 6 missing today); the test's pending list loses the three prompt names; a row owned by `specs/providers.md` stays open until wave 2 |
| T4a | 1 | Calibration task. `numeric_surface`, `transportable_value_type`, `pure_call_composition`: carry the rules the owners lack; rewrite the operator table rows and the `specs/versioning.md` sentence that cite "numeric surface rule N2/N3/N4" so they state the rule; reconcile "2.19 or later" in 7.1.1 with the source floor; mark the three Historical | 7.5 | Specification 7.1.1, 8.6, and 10.2 up to and including its table (nothing in its last ten lines, which adjoin I1's hunk in 10.3). `specs/versioning.md`, v2.34 entry only. Docstring pointers in `reader.py`, `pure_expr.py`. The three documents | TR | Ledger rows; the reviewer's sample found 24 of 65 sentences weaker or absent, listed in the review; time spent per row recorded for the checkpoint |
| T4e | 1 | Returns: a new subsection 8.10 for plain returns and `(result T ...)` guidance from `native_transportable_returns`; mark it Historical | 4.5 | Specification: new 8.10 after 8.9. Docstring pointers in `contracts.py`, `prompt_contract.py`. The document | T4a and the checkpoint | Ledger rows; a probe per guidance key |
| T3a | 1 | Internal specification pages: `effect_graph`, `proof_graph`, `type_catalog`, `reference_catalog`, `source_map`, `legacy_adapter`. Carry the rules found only there (among them: a macro may not introduce a hidden command or provider call; proof does not cross a workflow call; whether the runtime still guards variant access, checked against the code first); mark Historical | 5 | Specification 7.1 to 7.7 and 7.9 (not 7.8), section 11; the home T5b gave section 74; `workflow_command_adapter_contract.md`. Docstring pointers in `effects.py`, `syntax.py`, `contracts.py`. The six documents | T4e; T5b | Ledger rows; a rule that needs section 16 stays open for T10 |
| T3b | 1 | Closed migration designs: `consolidation`, `runtime_migration_foundation`, `private_runtime_state_and_consumer_value_flow`, `procedure_migration_identity_compatibility`. Most rows will read "describes removed code"; the module topology of `consolidation` goes to the code map | 9 | Specification 17.1; `specs/io.md`; `specs/versioning.md` outside its 2.40 entries (a rule that belongs there waits for E1); `orchestrator/workflow_lisp/README.md`. The four documents | T3a | Ledger rows; a row owned by evaluated execution or `specs/cli.md` stays open until wave 2 |
| T4d | 1 | Conditionals: rewrite section 12 from `strict_boolean_control_flow` (`if`, `cond`, exact `Bool`, discriminant proof, codes; no text about targets below the floor, no `resource-transition` example); mark it Historical | 5 | Specification section 12. The document | The variant-field fix (`fix/variant-field-after-discriminant`) merged; TR | Ledger rows; one probe per rule, among them the four shapes that fail today |
| T2b | 1 | Second pass of the design index and the matrix for everything wave 1 retired; `specs/index.md` quick links stop calling `provider_live_binding`, `provider_peer_messaging` and `trial_runs` informative designs; the notice of `typed_program_gates` says its C2 is dropped | 1.5 | `docs/design/README.md`; `docs/capability_status_matrix.md`; `specs/index.md`; `typed_program_gates` | The wave 1 tasks above | No row calls a Historical document current |
| T6 | 2 | Normalise the notice of `provider_context_values` and fix its one broken link (the whole corrected baseline); `docs/index.md` rows and reading path for everything retired so far; close ledger rows left open on blocked owners | 2.5 | `provider_context_values`; `docs/index.md`; evaluated execution, `specs/cli.md`, `specs/providers.md` only where a row needs a sentence | Blocked files clean | No open ledger row from wave 1; link check reports nothing |
| T7 | 2 | Guide, pass 1: every section of the guide table whose last column is `-`, except the REPL sections. Removed migration text goes to the guide's history file; the "Not available" table is added; stale examples found by the compile are fixed or labelled | 9 | The guide; `documentation-history/docs-lisp_workflow_drafting_guide-history.md` | Blocked files clean; T6 | Every one of the guide's Lisp blocks (51 today) is compiled at the current target inside a stand-in module with stand-in manifests, or carries the line "not a complete program" with the reason; counts in the ledger. All inbound anchors resolve. About 2,304 lines |
| T8 | 3 | Lists: carry `pure_list_traversal` into specification 10.3 and the form index; mark it Historical | 5 | Specification 10.3. The document | I1 and E1 merged | Rows for 15 live codes (12 only there today) |
| T9 | 3 | Callables: carry `proc_refs_partial_application`, what survives of `let_proc_local_proc_refs`, and `write_once` section 6.3 into specification 7.8 and 14; mark the three Historical | 8 | Specification 7.8, 14. Docstring pointer in `procedure_typecheck.py`. The three documents | C1 and the cut merged | Rows for the 9 procedure-reference codes (8 only there today); the 13 inbound anchors of `write_once` resolve |
| T10 | 3 | Procedures and effects: carry `effect_ledger_simplification` and the boundary rule of `procedure_first_reuse_contract` into specification 8.8, 8.9 and 16; fold sections 106 and 108 into 8.8 and 15, leaving their anchors; mark both documents Historical | 5 | Specification 8.8, 8.9, 15, 16, Part XIX. The two documents | The cut and E1 merged; blocked files clean | Ledger rows; the 8 inbound links to section 106 resolve; open rows of T3a closed |
| T11 | 3 | Loop values: check `value_and_continuation_composition` Increments 1 to 3 against specification 11 and 13.1 and `specs/dsl.md`; mark it Historical | 3 | The document; the specification only where a row needs it | E1 and I2 merged | Ledger rows |
| T12 | 3 | `executor_retirement`: check its source-floor and recovery rules against `specs/versioning.md` ("Targets and identity") and `specs/cli.md`; mark it Historical; the six maintained documents that cite it as owner cite `specs/` instead | 2.5 | The document; those six documents | The cut merged; blocked files clean | Ledger rows; its 21 inbound anchors resolve |
| T13 | 3 | The reference in its final shape: preamble (704 lines) to at most 40; sections 1 to 3 (thesis, goals, non-goals) dropped where `workflow_language_design_principles.md` already says it, else kept as a closing "Rationale" appendix; Parts X, XI and XVI: live rules and codes into the entry of the form they govern, the rest to the history file; per-target sentences become rules | 7 | The specification; its history file | The cut merged; T8 to T10 | 2,800 to 3,200 lines; the reference test runs over the whole file with an empty pending list; anchors resolve |
| T14 | 3 | Guide, pass 2: the sections the cut and surface coherence rewrote, cut to their targets; sections reordered to the outline | 6 | The guide | The cut and E1, I1, C1, I2 merged; T7 | At most 2,100 lines; the block compile of T7 repeated; anchors |
| T15 | 3 | Close: mark `surface_coherence` Historical if its section 11 conditions hold and `edit_and_continue` if Phase 3b has closed; final pass over the three indexes; final numbers in the ledger | 2.5 | Those two documents; the three indexes | T8 to T14 | The numbers table, re-measured |

Hours: wave 1 62 (of which 8 done on the branch); wave 2 11.5;
wave 3 39; total 112.5.

**Smallest useful step:** T0, T1 and T2a (done on the branch) took six documents out of the current
set, made four ambiguous notices plain and gave the design index a reading path.

### What can run in parallel

In-flight branches `feat/coherence-c1`, `-e1`, `-i1`, `-i2a` edit specification 7.8, 9, 10.3,
13.1, 14 and 16.2 (the reviewer read their hunks). No wave 1 task edits those sections; E1 also
edits the 2.40 entries of `specs/versioning.md` and `specs/dsl.md`.

Two lanes edit the specification in wave 1. Each lane is serial; the lanes share no section.

| Lane | Tasks in order | Specification sections | Other files |
| --- | --- | --- | --- |
| A | T5, T5b, T4c, T4b | 24; Part VI except 27; everything from Part VIII on except Parts X, XI, XVI, XIX (section 68 for T4c); Part VII; 8.7 to 8.7.3; 22.6 to 22.8 | the specification's history file; `core_calculus_middle_end`; `language_server`; three feature documents |
| B | TR, T4a, checkpoint, T4e, T3a, T3b | the new Form Index section at the head of Part I; 4; 7.1 to 7.7, 7.9; 8.6; new 8.10; 10.2 up to its table; 11; 12 (stub only); new 13.2; end of 15; 17.1; 22 before 22.4 | the new test; `specs/versioning.md` (v2.34 entry; outside 2.40 entries); `specs/io.md`; the command adapter contract; the code map; docstrings; fourteen documents |

- **Can start now**, from `docs/corpus-wave1-notices` or from `main` once it merges: **T5** (lane
  A) and **TR** (lane B), side by side.
- T3a waits for T5b as well as for its own lane, because T5b decides where section 74 lives.
- Sections 8.6 (lane B) and 8.7 (lane A) adjoin: neither lane edits the last or first three lines
  of the other's neighbour.
- T4d is outside both lanes: section 12 only, after the variant-field fix merges.
- T2b closes the wave.
- Wave 3: T8, T9 and T10 are serial in the specification (10.3; 7.8 and 14; 8.8, 8.9, 15, 16);
  T11 and T12 run beside them; T13 follows T10; T14 touches only the guide and runs beside all of
  them.

## Numbers

| Measure | Before (measured) | After wave 1 | After wave 3 |
| --- | --- | --- | --- |
| Workflow Lisp design documents not marked Historical | 53 | 30 (31 while T4d waits) | 20 (17 current, 3 proposals) |
| Their lines | 34,114 | about 22,959 | about 16,493 at most |
| Workflow Lisp design documents marked Historical | 28 (18,693 lines) | 51 | 61 |
| Frontend specification | 4,800 lines, 2,498 of them the language | about 4,050 | 2,800 to 3,200 |
| Registered heads with an entry in the reference | 12 of 82 | 82 of 82 (TR) | 82 of 82, kept by the test |
| Authoring guide | 3,424 lines; 4 known stale examples among 51 blocks | 3,424 (blocked) | at most 2,100 (about 2,304 after T7); every block compiled |
| Documents an author reads to learn the language | 12: the tutorial, the guide and the ten on its reading path | same | 3: tutorial, guide, library reference; the specification for lookup |
| Link-check problems | 59 reported, 1 real | 1 | 0 after T6 |
| Documents deleted or renamed | - | 0 | 0 |
| Hours | - | 62 | 112.5 (range 90 to 130) |

"After" figures for the specification and the guide are targets built from section sizes, not
measurements. The directory still holds 105 files and about 63,729 lines; what changes is how
many of them a reader must treat as current.

## Rulings

### Coordinator rulings on the review, 2026-11-13

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| C1 | The one language reference is the frontend specification scoped to the language (Parts I to V and VII, 2,498 lines today), aiming at 2,800 to 3,200 lines. The preamble and Parts VIII to XX leave the reader's path. A merge carries rules only: one sentence and its codes, in the entry of the form. A test of about 25 lines keeps every registered and retired form entered and every named code real. No generated reference | Review M6: a 4,600-line specification is another corpus. A rule and its rationale have different readers. The registry's rationale strings are too thin to generate from | A reader who needs the why follows a link into a Historical record. If one-sentence rules prove too thin for a feature, its entry regrows. Relocation costs about 6 hours and the test adds a failure mode for every new form |
| C2 | The rule ledger stays, with three changes: the reviewer samples one section of every retired document independently; an owner sentence may not cite the retired document; codes are proved by grep | Review M2: a ledger covers only the rules its author listed; 24 of 65 sampled sentences were weaker or absent | About 13 reviewer hours. One sampled section can still miss a rule in another section; the Historical record keeps it and the notice links it |
| C3 | Wave 1 is re-estimated now and again after T4a | Review M3: the first estimate assumed duplicates needed no writing | The model's discount and per-row minutes are guesses; the total can be off by a third either way until the checkpoint |
| C4 | T0 teaches the link checker `<a id>` anchors, with a test, and re-baselines; the check also covers the history files a task writes | Review M1: 58 of the 59 baseline problems were false, and the plan relies on `<a id>` | The plan now changes one script. None seen: the fix is done and the baseline is 1 |
| C5 | T7 and T14 compile every Lisp block of the guide in a stand-in module at the current target | Review M4: 5 of 51 blocks are complete modules; the four stale examples are all fragments | About 3 hours of harness and labelling; an intentionally partial example needs a line saying so |
| C6 | T4d waits for the variant-field fix | Review M5: the closed-program checker ignores the branch-local proof the typechecker grants, in four shapes, so T4d could not pass its own probe | `strict_boolean_control_flow` stays current until the fix merges. If the fix is dropped, T4d writes the rule with a known-defect note instead |
| C7 | T5 keeps headings; T4e writes under section 8 only; T3a excludes 7.8; T3b stays outside the 2.40 entries of `specs/versioning.md` or waits for E1 | Review m3, m4 and the hunks of the in-flight branches | A kept heading costs one line each (about 9 lines) |
| C8 | The nine minors are applied, with two adjustments: `docs/architecture.md` (m2) does not exist, so the module topology of `consolidation` goes to `orchestrator/workflow_lisp/README.md`, the code map; m9 is settled by dropping the REPL move (planner rulings 9 and 10) | The review | See planner rulings 8, 9 and 10 |
| C9 | The retirement guard: the author reads the document in full and refuses to retire it while a still-true rule has no current owner. In T1 and every later retiring task | A notice is cheap to add and expensive to trust | Reading 25 more documents in full is in the estimate (0.75 hours each) |
| C10 | Task table, waves, lanes with their sections, and numbers recomputed | Rulings C1 to C9 change all of them | - |

### Planner rulings

| # | Decision | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | Reshaped by C1. A feature design about core syntax or typing gives its rules to the reference and is marked Historical | Surface coherence section 11 already sends its rules there and retires two feature designs on that condition | If the owner prefers focused contracts, T4c to T4e and T8 to T11 are dropped and 10 more documents stay current |
| 2 | Eight feature contracts stay separate | Their codes are mostly in `specs/` already, or source and tests cite them (parametric types: 4 source files, 9 tests); an author needs them only when using the feature | 3,694 lines stay outside the reference; the form index links each of their forms to them |
| 3 | Nothing is deleted, moved or renamed | The conventions give no permission; 16 test modules and several source files cite design paths | The directory stays at 105 files; the index does the sorting |
| 4 | A proposal that was never built is listed as a proposal, not marked Historical | Historical in the conventions describes context that once was authority; the three parked designs can reopen under the roadmap's dispositions | 1,021 lines stay "not Historical" in the count |
| 5 | Withdrawn. The first draft let T1 retire a document without a rule check when its own text named another owner; C9 replaces that with a full read | - | - |
| 6 | Changed by C2. The rule check is a ledger of normative sentences and live codes in one report, with the reviewer's independent sample | It can be reviewed row by row; a full rewrite of 30 documents cannot | A rationale that is not phrased as a rule is found only through the Historical record |
| 7 | Sections that the cut or surface coherence will rewrite are not touched until they land | The stage 4 ledger holds the same rule for test files: touch once | Ten documents and the guide's second half stay as they are until that code merges |
| 8 | After the cut, `executor_retirement` becomes Historical; existing notices that name it are left alone; new notices name `specs/` (review m8) | Editing up to 39 notices to save one hop is churn; not adding to them is free | Readers of old records take two hops to `specs/`; one `sed` fixes it later |
| 9 | Changed (review m9). The REPL how-to stays in the guide as the other session wrote it | Moving 63 freshly written lines right after they land helps nobody, and the plan cannot ask that session from here | The guide target rises by about 150 lines |
| 10 | Changed. Guide target at most 2,100 lines (was 1,950) | Sum of per-section targets that keep every form that compiles today, with the REPL sections kept | A later pass could reach about 1,650 by moving the REPL sections and the feature recipes (agent sessions, host input, phased delivery, confined children: 275 lines) to their owners |
| 11 | Line counts are taken from the working tree | The other session's edits will be committed before the tasks that touch those files | Counts move by about 100 lines against the committed tree |
| 12 | "Entry" in the reference test means a backticked head in a heading or in the first cell of the form index or removed-forms table | A plain text search passes for 79 of 82 heads today and proves nothing; a heading per head would add 70 headings | The index is about 95 hand-written rows; a wrong section link in a row is not caught by the test |
| 13 | The test's code check has two shrinking exception lists | 23 of the 98 identifiers in Parts I to V and VII are not literals in the code: 10 look like codes the code no longer has, 13 are field or step names. A blanket check without lists fails on the 13 | A new field name in the reference needs a line in the test |
| 14 | Current rationale (specification sections 1 to 3) is not sent to a Historical file | The conventions list rationale among what a contract keeps | If the design principles already carry all of it the appendix is empty; if none, the reference is about 190 lines longer |

## Not Verified While Planning

- The 53 documents not marked Historical were not read in full by the planner. Classes rest on
  headers, section outlines, the named-module and live-code checks, and inbound links. The
  reviewer's sample covered three documents. The retirement guard and the ledger of each task are
  the real check and may reclassify a document.
- "Live code" counts include identifiers that are field names rather than diagnostics, and miss
  two-word codes.
- The variant-field defect is known, not unverified: `(if (= a.variant OK) a.n 0)` fails at 2.40
  with `compiler_defect` for a `let*`-bound variant, a workflow input, a procedure or command
  result, and with the field bound by `let*` inside the branch. It builds only when every variant
  has the field with one type. The first draft said existing tests cover the `let*` shape; they
  exercise the typechecker, which grants the proof, not the closed-program checker
  (`orchestrator/contracts/closed_program/check.py`, `_field_type`), which ignores it. A fix is in
  progress on `fix/variant-field-after-discriminant`; the planner has not read it.
- The estimate's inputs (the 0.65 discount, minutes per row, the weaker-or-absent share outside
  the three sampled documents) are assumptions.
- The sentences the review quotes as found only in the internal pages were not re-read; "the
  runtime still guards variant access" may no longer be true and T3a checks the code first.
- Which sections of Parts VIII and XII are live internals was not decided; T5b decides per
  section. Whether `language_server` already carries sections 74 and 76.1 was not checked.
- Whether `workflow_language_design_principles.md` already carries the specification's thesis,
  goals and non-goals was not checked.
- Not probed by the planner: `defmacro`, `:path :out` slots, confined children,
  `review-revise-loop` beyond its import, bundle-mode run references. The `path/join` refusal is
  the reviewer's probe; the planner confirmed only that it is not a registered operator.
- The hunks of the in-flight coherence branches were read by the reviewer, not the planner.
  Whether Task 4b of the stage 4 plan edits the frontend specification is unknown; T13 assumes it
  leaves the per-target prose in place.
- The 23 design documents without the `workflow_lisp_` prefix were classified from their status
  line; the three indexed files outside `docs/design/` were not looked at.
- Whether `specs/state.md` carries the retained safety rules of `lexical_execution_checkpoints`
  was not checked; T1 checks it before normalising that notice.

## Ledger

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-13 | T0 done (branch `docs/corpus-wave1-notices` from `5e58ec41`, no uncommitted edits) | `python scripts/check_doc_links.py docs/*.md specs/*.md docs/design/*.md README.md workflows/README.md tests/README.md MIND_MAP.md docs/backlog/README.md prompts/README.md` (144 files): 59 problems with the checker as it was, 58 of them links to an existing `<a id>` the checker did not read; T0 taught `scripts/check_doc_links.py` `<a id>`/`<a name>` anchors (`tests/test_check_doc_links.py`), and the corrected count over the same tree is 1 (`workflow_lisp_provider_context_values.md`, a link to the deleted `lowering/effects.py`). The corrected list is the baseline. `wc -l` by class: OWNER 23,651, DUPLICATES 4,427, SUPERSEDED 2,913, DELETED CODE 2,040, NEVER BUILT 1,021, HISTORICAL 18,656; 81 files, 52,708 lines. `git grep` of guide anchors outside plans and reports: 18 distinct from 35 files. Lists and commands in the [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#baseline-t0), which T0 created |
| 2026-11-13 | T1 done | Historical notice (insertion after the title; body byte-identical to `5e58ec41`, checked with `cmp`) on `edit_and_continue_spike`, `frontend_deduplication`, `refactor_architecture`, `shared_owner_lane_prerequisites`, `trial_runs`, `mlevolve_workflow_lisp_system_architecture`; standard notice added above the non-standard one of `judgment_views`, `lexical_execution_checkpoints`, `provider_live_binding`, `provider_peer_messaging`. Every document read in full; rows 1.1 to 9.6 of the rule ledger; none refused. Owners in blocked files (evaluated execution, `specs/cli.md`, `specs/providers.md`, `workflows/README.md`, agent sessions) are quoted only where the sentence is also in the other session's working copy. Judgment call to review: `refactor_architecture` row 3.9 |
| 2026-11-13 | T2a done (smallest-step scope: T3 and T4 documents stay where their status puts them) | `docs/design/README.md` rewritten in the five parts (read first 5, feature contracts 35, tooling/internals/research 16, proposals not built 4 with the provider-phase isolation spec, historical 47 with two files outside the directory); all 104 other files of `docs/design/` listed once (row count checked with `grep`); no rule text kept in the preamble. Capability matrix: owner cells of the trial-runs, judgment-views, live-supervision, observation-panes, peer-messaging and pure-result-replay rows now name the current owner first and mark the design a Historical record; the other T1 documents have no matrix row. Link check (corrected checker): 1 problem, the baseline one |
| 2026-11-13 | T0 to T2a revised after their review (0 blockers, 3 majors, 10 minors) | Ledger re-swept section by section for the six retired documents, with per-document counts; no owner is a document the plan retires or a specification part leaving the reader's path; new owner sentences in `orchestrator/workflow_lisp/README.md` (two rules of `refactor_architecture`), `workflow_lisp_durable_host_input.md` (no record of an omitted `:returns`) and run-reference D2. Open rows for later tasks: 3.6 (T4c), 4.3 (T4e), 7.4 (T8), 6.6 (TR, specification section 4). `mlevolve_workflow_lisp_system_architecture` is back to current because 6.6 has no owner; its notice was removed and returns once TR adds the sentence. Link checker: single quotes, `id` not first, case, inline-code anchors, duplicate ids, fence exclusion, with tests. Design index refiled (closed migration designs and internal pages under tooling; accepted-not-landed designs beside the proposals) |
| 2026-11-13 | T5 done (lane A, branch `docs/corpus-lane-a`) | Bodies of specification §24, §26, §28 to §31 (with §29.1), §86, §87, §107 and the Part VI diagram moved to the [history file](../reports/documentation-history/workflow_lisp_frontend_specification-history.md#removed-forms-moved-2026-11-13); every heading kept with a one-line notice. Specification 4,800 to 4,512 lines. Moved lines identical apart from relative links. Rows T5.1 to T5.9 of the rule ledger: all removed code; no rule lost. Link check: the one baseline problem |
| 2026-11-13 | T5b done (lane A) | Parts VIII, XII, XIII, XIV, XVII and XX moved to the [history file](../reports/documentation-history/workflow_lisp_frontend_specification-history.md#sections-moved-off-the-reading-path-2026-11-13); each part heading kept with an `<a id>` per former section and one paragraph naming the owners. Specification 4,512 to 3,836 lines. Written: the middle-end's "Pipeline, provenance and private contexts" (§38, §74 union-field subjects, §75, §83 bootstrap roles) and the language server's "Compiler Artifact Compatibility" (§76.1). Deviation: §74's live rules went to the middle-end, not the language server, because they govern checked-program construction and runtime validation, not the editor. Rows T5b.1 to T5b.39; findings: `source_map_missing` raised nowhere; the language server's ten symbol kinds contradict the compiler's eight; its `evaluated_execution_unavailable` claim has no LSP code path; §110's ambiguous-path refusal not found. "Final Design Center" left for T13. Link check: the one baseline problem |
| 2026-11-13 | T4c done (lane A) | Specification Part VII (§32 to §37), §8.7 and §68 rewritten from `macro_surface_contract` and the code, one rule per bullet with its codes; former text to the history file. `macro_surface_contract` marked Historical (notice added, 0 lines deleted). Specification 3,836 to 3,765 lines. Rows M.1 to M.20: 18 live rules and 2 rows of removed code; of the 18, the old specification text lacked 9 (M.1 to M.3, M.6, M.9, M.12 to M.15) and stated 3 weaker (M.5, M.10, M.17), so 12 were written and 6 were present. The document itself was weaker than the code once (M.9: its emitted top-level forms omit `defprompt`). Seven dead `macro_*` codes and two dead source-map codes dropped. Probes: 12 modules at 2.40. Still naming it current, outside this lane: `docs/design/README.md` and the matrix (T2b), `docs/index.md` and the guide (blocked) |
| 2026-11-13 | T4b done (lane A) | Specification §8.7.1 to §8.7.3 and §22.6 to §22.8 rewritten from `prompt_calculus`, `prompt_identity_diagnostics` and the code (former text to the history file); both documents marked Historical (notices added, 0 lines deleted). Specification 3,765 to 3,534 lines. Rows P.1 to P.25 and Q.1 to Q.9: of 34 rows, 21 carry live rules (19 owned by the specification, 2 by evaluated execution and phased delivery; the old specification text had most of the 19 but tied to flat-route carriage, and lacked the placeholder grammar, the fill-expression rule, the refusal order, the post-attempt validation order and the `:value` union admission), 2 are rules the code does not keep (P.20 pre-launch name and destination collision, P.22 carrier mismatch), 11 are removed code or history. Compiler contradiction: unions are admitted on `:value` (P.6). Dead codes: 3 of the specification's and all 11 Q3 codes. Probes: 32 modules at 2.40. The runtime half of both documents is off the execution path (builders called only by tests). Still naming them current outside this lane: phased contract delivery line 9, `provider_result_delivery.md`, the design index and matrix rows 79 to 81 (T2b), `docs/index.md` and the guide (blocked) |
| 2026-11-13 | Lane A revised after review (0 blockers, 4 majors, 11 minors; all applied) | §34 hygiene now states that template-bound names are renamed and free template names resolve at the call site (probes; the retired contract claimed more); §8.7.3 no longer states the fragment identity or `compiled_prompt_fragment_identity_invalid` (computed and dropped); the middle-end states how the evaluated build supplies a hidden `RunCtx` (`closed/context.py`) and the import-boundary refusal `workflow_boundary_projection_collision` / `promoted_entry_hidden_phase_ctx_ambiguous` (formerly §110, wrongly recorded as absent); four owner clauses strengthened (template `command-result` refused first; failed attempts keep written files; `:must-exist false` exactly; `:text` verbatim), each by probe. Ledger rows revised in place and findings F.1 to F.5 recorded. Two source comments and two routing links repointed |
| 2026-11-13 | T0, T1, T2a and Lane A (T5, T5b, T4c, T4b) merged to `main` (`7379515c`) | Wave-1 first step: five documents Historical and four notices normalised, each body byte-identical below its notice; the rule ledger re-swept section by section after review (115 still-true sentences over nine documents); one document went back to current because the compiler enforces a rule of it that no current document carried (`module_path_mismatch`; Lane B adds the rule); the link checker reads `<a id>` anchors (59 reported problems were 1 real one); the design index is in five parts. Lane A: the language reference is 3,537 lines (from 4,800); `macro_surface_contract`, `prompt_calculus` and `prompt_identity_diagnostics` are Historical; about 35 rules written into current owners. Both reviews: approve with fixes, no blocker; the fixes removed four statements the code does not do (a prompt identity check with no effect; a run-context paragraph describing an unused path; hygiene stronger than the compiler provides; a live boundary refusal written off as nonexistent). 21 diagnostic codes named by the old documents are never raised and are not written as current. Gate: every test module that reads documents (34 modules, 948 tests) passes on the branch tip; the changes outside documents are the link checker with its test, three comments and one link; the full suite on `main` at normal load is still owed (stage 4 ledger). Code defects found and recorded on the roadmap's open list: two prompt outputs aliased to one path are not refused; an output name clashing with a result field is caught only after the provider ran; the prompt snapshot and attempt-identity machinery and `structural_bootstrap_plan` have no caller. |
| 2026-11-13 | TR done (branch `docs/corpus-lane-b`, from the wave 1 tip with `main` at `4bae0a7c` merged) | `tests/test_workflow_lisp_reference_coverage.py` (2 tests) failed first: 76 of the 93 registered (82 at 2.40) and removed (11) heads had no entry, and 24 backticked snake_case names in Parts I to VII were not string literals in `orchestrator/`. Written: a Form Index at the head of Part I (82 rows) and a Removed forms table (11 rows, with the tag and what replaces each); entries for `workflow-lisp` and `defmodule` (§4), `record` (§7.4), `cond` (new §12.1), `loop-state` (new §13.2), `workflow-ref` (end of §15), `provider-bundle-path` (§22 before 22.1). Exception lists: 14 names that are not diagnostics (field, step and function names), 10 codes not in the code (7 `macro_*` in §37, 3 prompt codes in 22.6 and 22.7; none in this lane's sections). Every new entry and each removed head was compiled at 2.40 (stand-in manifests, no-provider stubs); one finding: a `defworkflow` with a `WorkflowRef` parameter, the shape of §15's example, fails with `compiler_defect` (the entry documents the `defproc` parameter that builds). Mutation checks: dropping the `cond` entries, adding a made-up code and removing a listed name each fail the test. Link check: the baseline problem only |
| 2026-11-13 | T4a done (calibration task; branch `docs/corpus-lane-b`), revised after its review (0 blockers, 5 majors, 13 minors) | `numeric_surface`, `transportable_value_type`, `pure_call_composition` read in full and swept a second time section by section ([rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#t4a-numeric-surface-transportable-value-pure-call-composition), rows 10.1 to 12.29). After the review: 85 live rules, 42 already present in an owner, 23 strengthened (weaker, change-log only, or stated by citing the document), 18 newly written, 1 open, 1 not written (true only for one consumer). `numeric_surface` and `transportable_value_type` are Historical; `pure_call_composition` stays current: its row 12.24 (identity and checkpoint reuse) is owned only by evaluated execution, a blocked file, and `specs/state.md` and `specs/versioning.md` state it only for retargeting. Written into specification 7.1.1, 8.6, 10.2 (opening and up to its table), 7.7 and 15 (the `WorkflowRef` compiler defect: only a `defproc` formal builds); citations of the numeric document removed from the v2.34 entry of `specs/versioning.md` and one bullet of `specs/io.md`; docstring pointers in `reader.py` and `pure_expr.py` repointed. **Checkpoint (hours MODELLED, not measured):** no wall-clock time was recorded. The measured input is the share of live rules that needed work: 39 of 82 at the first count (47.6%), against the 36% the estimate assumed for DUPLICATES; about 42 of 85 with the review's rows. The estimate's per-row model gives about 8.6 hours for the three documents against 7.5 estimated, inside the 5 to 10 band only by construction. Conclusion: the remaining DUPLICATES tasks (T4b, T3a, T3b, T11) take a factor of about 1.15 on their hours; T4e, the next such task, records minutes per ledger row before T3a's estimate is revised. Open: the last bullets of 10.2 keep "(numeric surface rule N1)" (adjacent to I1's hunk); section 108 still calls formal `WorkflowRef` parameters supported; the design index and matrix still list the three as current (T2b) |
| 2026-11-13 | Lane B (TR, T4a) merged to `main` (`ee33ad54`) after its review fixes (5 majors and most minors applied; `pure_call_composition` back to current) | Gate: the reference coverage test, the link check and the authoring-kit tests on `main` after the merge (41 passed); code changes are docstring pointers only. Exception lists after the merge: 8 names that are not diagnostics, 0 codes absent from the code. Next: T4e, T3a, T3b, T2b; T4d after the variant-field fix merges. |
| 2026-11-13 | T4e done (lane B, branch `docs/corpus-lane-b2` from `main` at `3b209043`) | New specification [§8.10](../design/workflow_lisp_frontend_specification.md#810-return-types-and-result-guidance) (return positions, the transportable families, the direct root and `__result__`, required result documents, `(result T ...)`, guidance keys, examples, where guidance goes, composition; 53 lines, codes on each rule) from `native_transportable_returns` and the code; the document marked Historical (4 lines added, 0 deleted); docstrings in `contracts.py` (3) and `prompt_contract.py` (1) cite §8.10. [Rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#t4e-returns-and-result-guidance) rows 13.1 to 13.49: 29 written, 10 present, 3 removed code, 3 compiler internal, 3 history, 1 not true of the code; row 4.3 closed. Probes: 62 modules at 2.40 (compile, runs with a stand-in command, and a stand-in `codex` on a closed `PATH` for the prompt). Findings: a `Bool` result accepts the strings `"true"`/`"false"`; workflow, procedure and function return guidance is checked then dropped (`specs/io.md` says it is carried in metadata); effect-boundary guidance enters the program digest (the v2.15 row of `specs/versioning.md` says guidance changes no identity). **Measured:** 882 s wall clock from the first read to the commit, 0.30 minutes per ledger row (49 rows), against the estimate's 1.5 to 8 minutes per row and 4.5 hours for the task; the machine's load stayed near 100 throughout. Open: none |
| 2026-11-13 | T3a done (lane B, branch `docs/corpus-lane-b2`) | The six internal pages read in full ([rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#t3a-internal-specification-pages), rows 14.1 to 19.9, 74 rows: 19 written, corrected or strengthened, 31 present, 11 removed code, 5 compiler internal, 6 history, 1 not true of the code, 1 open). Written: specification §7.1 (the prelude list; `TimestampNs` does not exist), §7.3 (`defpath` keywords; path types are nominal, the catalog's refinement rules describe nothing in the compiler; an example that the compiler refused fixed), §7.5 (proof only in a `match` arm or after §12's test), §7.7 (`workflow_ref_type_invalid`), §11 (match and proof rules with codes, workflow calls carry no proof, the evaluator's run-time check, checked against `evaluated/machine.py` and `values.py`); the middle-end (root subjects; subjects are provenance and enter no digest; no source read at run time); the command adapter contract (legacy-adapter policy, and that the code enforces only the stable-command rule). `proof_graph`, `type_catalog`, `reference_catalog`, `source_map`, `legacy_adapter` marked Historical (4 lines added each, 0 deleted); docstrings in `contracts.py` and `syntax.py` repointed. **`effect_graph` stays current:** row 14.5 (at 2.35 to 2.38 declared effects equal the inferred ones, specializations exempt; `procedure_effect_mismatch`) is owned only by `effect_ledger_simplification`, a blocked file that T10 retires, and by a v2.33 change-log entry; its owner is §8.8 or §16, T10's. Compiler defect found: inside a `match` arm, a field read on the subject (not the binder) passes typecheck and is a `compiler_defect` at elaboration (reproduction in the ledger). **Measured:** 609 s wall clock, 0.14 minutes per row; probes 37 modules at 2.40 and 2.38, compile only. Open: 14.5 for T10 |
| 2026-11-13 | T3b done (lane B, branch `docs/corpus-lane-b2`) | The four closed migration designs read in full ([rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#t3b-closed-migration-designs), rows 20.1 to 23.10, 41 rows: 3 written, 22 present, 6 removed code, 2 not true of the code, 1 compiler internal, 7 history). Written: the code map's Runtime Boundary (the extracted module owners and the compiler-free runtime rule that `tests/test_workflow_closed_program_isolation.py` enforces; the design list marks the T3a and T3b documents historical) and specification §17.1 (values between steps; the flat private-lane text replaced). `consolidation`, `runtime_migration_foundation`, `private_runtime_state_and_consumer_value_flow`, `procedure_migration_identity_compatibility` marked Historical (4 lines added each, 0 deleted). Nothing written into `specs/io.md` or `specs/versioning.md`: their rules were present. Findings: prompt extern paths are checked when the call runs, not at compile; a missing prompt reports a bare errno, not the source kind. **Measured:** 325 s wall clock, 0.13 minutes per row. Open: 23.1 and 23.4 for T10 (owner today: the procedure-first reuse contract, which T10 retires) |
| 2026-11-13 | Lane B2 fix round 1 (review: 2 blockers, 5 majors, 11 minors; `consolidation` and `private_runtime_state_and_consumer_value_flow` reopened) | Every sentence added or kept re-probed with its falsifying case. **B1** §11 states the shared-field read through `has-shared-union-field` (a concrete union still refuses a field all variants declare); **B2** §7.3 states that structural constraints accept a path type with the same root and an equal or stricter existence check (arguments stay nominal). **M1** (ruling: the code is right) the v2.15 row of `specs/versioning.md`, `specs/io.md` and §7.1.1 now say that guidance on a provider or command result is part of the program's identity (probe: a guidance edit makes `resume` refuse `resume_program_changed`; a whitespace edit does not). **M2** `specs/io.md` says return guidance on a workflow, procedure or function is checked and not kept (filed for the defect list). **M3** `specs/state.md` Memo records gains the rule that a committed value is not the files the effect wrote nor a record of what a provider read (probe: replay returns a deleted file's path without rerunning or restoring it). **M4** the non-idempotent rule is present in `specs/cli.md` (blocked; quoted, not edited); §12 rows added. Both reopened documents keep their notices: every row now has an owner or is removed code. **M5** this lane's §7.5 rewrite withdrawn (row 15.13 open for T4d). Row 14.5 names `procedure_effect_missing` and the one-target-cut branch. Minors applied: m1, m2, m3, m5, m6, m7, m8, m10, m11; rejected: m4 (the sentence "Path types are refined contracts" stays true of `defpath`'s refined relpath contracts), m9 (re-exports and record flattening not probed; imports and the nested-record sentence cover them). Findings R.1 to R.9 in the [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#fix-round-1-lane-b2-review). Open: 14.5 (T10 or the cut), 15.13 (T4d), 23.1, 23.4 (T10) |
