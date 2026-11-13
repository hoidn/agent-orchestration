# Design Corpus Rule Ledger

**Status: Captured evidence, not a contract.** This page records, for each Workflow Lisp design
document that the [design corpus consolidation plan](../plans/2026-11-13-workflow-lisp-design-corpus-consolidation-plan.md)
marks Historical or whose text it removes, every rule the document states and the current owner
that carries it. The owners named here govern; this page only shows where each rule went. Tasks of
that plan append rows; nothing here selects work.

## How To Read A Row

One row per rule. A rule is a sentence that requires, forbids, bounds or refuses, or a live
diagnostic code. Columns:

- **Document, section:** where the rule is written (document names omit `workflow_lisp_` and `.md`).
- **Rule as written:** quoted or closely shortened.
- **Owner:** the current owner, file and anchor.
- **Owner's sentence:** quoted from the owner at the commit the task worked from (whitespace
  normalised).
- **Check:** how the owner and the code were checked (identifier grep, file existence, test name).

Instead of an owner, a row may say **removed code** (the module, form or head is gone; the check
names it), **history** (a closed plan's scope, schedule or evidence; the record that keeps it), or
**not true of the code** (a target that was never adopted). A document is marked Historical only when
every row is closed. A row whose owner is a file another session is editing stays open until that
file is clean; T1's rows quote such owners only where the sentence was also found, unchanged, in the
other session's working copy.

## Baseline (T0)

Taken in the worktree of branch `docs/corpus-wave1-notices` at `5e58ec41` (no uncommitted edits;
the plan's figures were taken in the main checkout with another session's edits, so some differ).

**Link check.** `python scripts/check_doc_links.py docs/*.md specs/*.md docs/design/*.md README.md
workflows/README.md tests/README.md MIND_MAP.md docs/backlog/README.md prompts/README.md` over 144
files, two counts:

- **59 problems with the checker as it was at `5e58ec41`**, the plan's count. That checker read only
  heading anchors, so 58 of the 59 were links to an `<a id="...">` anchor that exists (for example
  `workflow_lisp_program_search_boundaries.md#proposed-amendment-2026-10-17` from
  `docs/design/README.md`).
- **1 problem with the corrected checker** (T0 taught it `<a id>` and `<a name>` anchors;
  `tests/test_check_doc_links.py`), run over the same `5e58ec41` tree:
  `docs/design/workflow_lisp_provider_context_values.md: missing target ../../orchestrator/workflow_lisp/lowering/effects.py`
  (a link to a deleted module, in a blocked file).

The corrected count is the baseline: no later task may add a problem to it.

**Line counts** (`wc -l`, classes from the plan's inventory):

| Class | Documents | Lines |
| --- | --- | --- |
| OWNER | 28 | 23,651 |
| DUPLICATES | 10 | 4,427 |
| SUPERSEDED | 5 | 2,913 |
| DELETED CODE | 7 | 2,040 |
| NEVER BUILT | 3 | 1,021 |
| HISTORICAL | 28 | 18,656 |
| Total `workflow_lisp_*.md` | 81 | 52,708 |

`docs/design/` holds 105 files and 63,630 lines; the drafting guide 3,363 lines; the frontend
specification 4,800. The differences from the plan (52,807; 63,729; 3,424) are the other
session's uncommitted edits.

**Inbound anchors of the drafting guide.** `git grep -oE 'lisp_workflow_drafting_guide\.md#[A-Za-z0-9_-]+'`
outside `docs/plans/`, `docs/reports/` and the guide itself: 18 distinct anchors from 35 files
(the plan counted 19 from 33 in the working tree). Each must still resolve after any guide task:
`confined-workflow-children-target-238-command-only` (12 links),
`a-complete-235-recipe-compile-run-resume-report-invalidate` (11; already missing at baseline),
`2a-program-shapes-what-runs-today` (11), `procedure-contracts-at-target-239` (10),
`durable-host-input` (9), `authoring-phased-contract-delivery-target-239` (9),
`agent-sessions-target-238` (9), `inspect-a-run-with-the-workflow-lisp-repl` (8),
`173-parallel-map-target-237` (5), `137-improve` (5), `portable-provider-context` (3),
`print-a-value-during-a-run`, `pinned-child-runs-and-trials`, `improve-rejections`,
`authoring-prompt-fragments---target-220`, `authoring-prompt-fragments`,
`13-standard-high-level-forms`, `101-a-step-that-may-be-unable-to-answer` (1 each).

## T1: Documents Marked Historical

### `edit_and_continue_spike`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 1.1 | Header, "What owns the behavior today" | "A run resumes only under the program it started with." | [Evaluated execution §7.3](../design/workflow_lisp_evaluated_execution.md#73-what-a-command-boundary-declares), C7 | "A semantically changed manifest or stable command changes the program identity: a fresh build is compared with the header, and resume is refused with `resume_program_changed` before any memo record is read; the plan printed with the refusal is computed afterwards, read-only." | `git grep` of the string literal in `orchestrator/`: `cli/commands/evaluated.py`, `cli/commands/human_input.py`; sentence also present in the other session's working copy |
| 1.2 | Header | "A failed command whose `failed` record says `closure: unchanged` is retried with its current script; any other unfinished command with changed files needs `resume --accept-changes`." | [Evaluated execution §8.1](../design/workflow_lisp_evaluated_execution.md#81-what-the-memo-decides); [CLI, Resume preflight precedence](../../specs/cli.md#resume-preflight-precedence), step 10 | §8.1: "Changed evidence stops it the same way unless the change is accepted: either the latest attempt has a `failed` record whose `closure` is `unchanged`, or the author passes `resume --accept-changes`." CLI: "for changed ones unless accepted: the latest attempt's `failed` row says `closure: unchanged` and the step is not a parallel-map item, or `--accept-changes` was given" | Both sentences found in the other session's working copies; `tests/test_workflow_evaluated_script_fix_retry.py` exists |
| 1.3 | §1 item 1 | C4: the closure is read-only; rehash before commit, `command_closure_written` | Evaluated execution §7.3, C4 | "Rehash before commit and fail the attempt with `command_closure_written` if its declared files changed." | String literal in `orchestrator/workflow/evaluated/effect_inputs.py` |
| 1.4 | §1 "A version of 3a", rulings 1 and 3 | Rehash on failure; record `closure: unchanged` or `changed`; an interrupted attempt needs explicit acceptance; one flag `resume --accept-changes` | Evaluated execution §7.3, C4 | "Rehash also when a started attempt fails, and record in its `failed` record `closure: unchanged` only when no process of the run is alive and then no declared file differs from its `started` evidence; otherwise `changed`, also when the rehash cannot complete or liveness cannot be checked." ... "a missing failure record never counts as acceptance." | As 1.2 |
| 1.5 | §2 "A defect that matters more than names"; ruling 4 | The provider `declaration` digest must stop including source positions; runs in flight must not be stranded | [Edit and continue §2](../design/workflow_lisp_edit_and_continue.md#2-the-declaration-prerequisite) | "`declaration` is the digest of the class's **subject** as it stands after the position stripping that defines the program digest." ... "Wherever a provider-class digest recorded in the journal is compared with a freshly resolved one, the fresh `declaration` is computed by the rule the recorded value satisfies" | Read; the design is the 3b owner (Phase 3b in execution) |
| 1.6 | §3, §4, "Proposed contract changes" (3b); ruling 2 | Prefix reuse under an edited program, the `rebased` record, C10; an edit is accepted only explicitly, and the refusal prints the plan | [Edit and continue §1](../design/workflow_lisp_edit_and_continue.md#1-summary) | "Replay the edited program against the journal, keep the commits it reproduces in journal order, and cancel everything from the first one it does not (§3). One `rebased` record names the edited program and the cut (§4). Plain `resume` refuses and prints the plan with its token; `resume --accept-changes=TOKEN` applies exactly that plan" | Read |
| 1.7a | Rulings 5, 6, 8 | `.orc` only first (Python runs); a committed human reply at or after the cut is asked again; an edited child of a run reference keeps refusing | [Edit and continue §5](../design/workflow_lisp_edit_and_continue.md#5-refusals-that-stay) | "`resume` rebuilds the generated `.orc` copy the header names. An edit to the `.py` file is not seen and nothing refuses" / "A `request_input` commit at or after the cut is cancelled like any commit, the plan lists it under \"asked again\", and the next resume issues a new request with a new ID" / "The flag, the token and the edit are never passed to a child run." | Read (sentences quoted without their bullet labels, which name the spike) |
| 1.7b | Ruling 7 | Workspace leftovers of cancelled steps are the author's risk | [Edit and continue §7](../design/workflow_lisp_edit_and_continue.md#7-soundness-and-its-limits) | Under "Workspace files of cancelled effects": "This is `invalidate`'s limit made routine." and "For agent steps it is the normal case." (the neighbouring sentences name the spike and are not quoted) | Read |
| 1.7 | §2 naming rule; §5 prototype; §6 cost; §7 H-G3 measurement | Python callee-derived names; prototype results; estimates; a measurement method | history | Kept in this record; the naming task C3 is dropped by the record's own "Consequences" paragraph | Not rules |

### `frontend_deduplication`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 2.1 | Decisions 1 | "a command with neither `:argv` nor `:adapter` uses its external-tool binding's complete literal `stable_command`. Additional or dynamic arguments retain explicit argv. `:returns` remains required." | [Command adapter contract, Static command argv](../design/workflow_command_adapter_contract.md#static-command-argv) | "At admitted targets 2.35–2.40, `command-result` may omit both `:argv` and `:adapter` when its named binding is an `external_tool`. The typechecker materializes the binding's complete literal `stable_command` before typed export and checked-program construction. `:returns` remains required." | Section read |
| 2.2 | Decisions 2 | "a direct, fully applied prompt with an explicitly declared answer contract supplies omitted host-input `:returns`. Raw questions and prompts with implicit returns still declare it. Canonical producer type ownership survives aliases, specialization and typed imports." | [Durable host input](../design/workflow_lisp_durable_host_input.md) | "`:returns` is required for raw questions and prompts without an explicitly declared return contract. A direct, fully applied typed `defprompt` with a declared answer contract supplies it when omitted." ... "Omission uses the prompt's canonical declaring-owner type, including through aliases, specialization and typed imports." | Lines read |
| 2.3 | Decisions 3; "Why these bounds" | Envelope with one shared closure plus local files; flat maps first-class; local omission or `[]` adds nothing and cannot subtract; a string `$schema` keeps flat rows named `$schema`, `shared_closure`, `commands` valid | Command adapter contract (envelope paragraphs after C1); [DSL](../../specs/dsl.md) | Contract: "Each row receives common plus local paths, including unused and certified rows. Omitted local `closure` and local `[]` add nothing; neither removes shared paths." and "Object-valued flat rows named `$schema`, `shared_closure` or `commands` remain valid command names." DSL: "Command manifests support a flat map or an envelope with exactly `$schema`, `shared_closure` and `commands`." | Lines read |
| 2.4 | Normalization ownership | "No omission marker, shared reference or inference flag reaches the checked program or memo." | Command adapter contract | "no envelope or merge reference reaches the runtime or persisted binding schema." Argv: "The typechecker materializes the binding's complete literal `stable_command` before typed export and checked-program construction." | Lines read |
| 2.5 | Normalization ownership | Typed imports require concrete operands and keep producer argv, closure and policy; malformed imports cannot infer from consumer bindings | Command adapter contract, Static command argv | "Exported/imported typed commands always carry concrete operands and their producer's closure/policy; a malformed import cannot infer from consumer bindings." | Lines read |
| 2.6 | Migration and evidence limits | Which examples to migrate; measurement method | history | The [plan](../plans/2026-10-26-frontend-deduplication-plan.md) and [verification report](2026-10-26-frontend-deduplication-verification.md) | Not rules |

### `refactor_architecture`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 3.1 | Opening paragraph | `compiler.py` coordinates; `closed/` owns checked program construction; "do not restore a lowering facade, flat executor or compatibility alias" | [Core calculus, Current Ownership And Invariants](../design/workflow_lisp_core_calculus_middle_end.md#current-ownership-and-invariants) | "`workflow_lisp/closed/` constructs the checked program and the evaluated runtime owns execution/memo persistence." ... "No migration design, representation carrier or old header selects a flat executor." | `orchestrator/workflow_lisp/lowering.py` absent |
| 3.2 | Design Principles | "macros and stdlib forms cannot hide effects" | [Design principles](../design/workflow_language_design_principles.md#compact-principles); [macro surface contract](../design/workflow_lisp_macro_surface_contract.md) | "Macros cannot hide effects." Macro contract table: "Macro-template-introduced hidden provider or command effect \| frontend effect validation \| `macro_hidden_effect`" | String literal in `orchestrator/workflow_lisp/diagnostics.py` and `lints.py` |
| 3.3 | Design Principles | "surface syntax is not authority"; "source maps are semantic infrastructure" | Design principles | "Structured bundles are authority; reports are views." and "Every generated semantic node is source-mapped." | Read |
| 3.4 | Design Principles | "Core Workflow AST, shared validation, Semantic IR, Executable IR, and runtime contracts remain the semantic path" | removed code | `core_ast.py`, `semantic_ir.py`, `executable_ir.py` absent; their designs are Historical | File existence |
| 3.5 | Macros | "Macro expansion should remain syntax-only"; malformed output keeps macro provenance and is then rejected by normal validators | Macro surface contract | "macros emit hygienic frontend AST for ordinary shared type/effect/proof checking and checked-program construction." ... "Macro provenance is additive. It does not replace the owner of the underlying failure." | Read |
| 3.6 | Build Artifacts | "Debug YAML and source-map documents are projections, not authority." | [Frontend specification §80](../design/workflow_lisp_frontend_specification.md#80-emit-debug-yaml); design principles | §80: "Its renderer/layout descriptions are historical design evidence, not an execution or persistence authority." Principles: "Structured bundles are authority; reports are views." | Read |
| 3.7 | Diagnostics And Lints | "Diagnostics and lints should fail closed. Unknown metadata should be explicit" | [Design principles §28](../design/workflow_language_design_principles.md#28-refusals-must-name-their-rule) | "Every compiler or runtime decision that denies, disables, or withholds a capability emits a coded diagnostic naming the rule it applied and the value it rejected." | Read |
| 3.8 | Expression Model And Traversal, "Required invariant" | "every `ExprNode` variant is either covered by child traversal or explicitly declared as a leaf/specialized form in a coverage test" | not true of the code | No test enumerates `ExprNode` variants (`git grep 'get_args(ExprNode'` finds one membership assertion in `tests/test_workflow_lisp_run_ref.py`); `walk_expr` in `expression_traversal.py` raises on an unknown node (`test_validate_pure_function_expr_surfaces_unknown_traversal_nodes`) | Grep |
| 3.9 | Non-Goals, Package Facade, Elaboration And Typecheck Context, Contracts, Effects, lint/artifact registries, Refactor Seams, Compatibility Strategy, Verification Strategy, Open Decisions | Scope and target module boundaries of the June 2026 behavior-preserving refactor ("should" guidance) | history | The [low-hanging refactor plan](../plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md) and the [preserved record](documentation-history/workflow_lisp_refactor_architecture-history.md#implementation-handoff). Partly adopted (`TypecheckContext` in `typecheck_context.py`, shared `expression_traversal.py`); no current document holds these as rules. Judgment call, flagged for the reviewer | Grep |

### `shared_owner_lane_prerequisites`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 4.1 | §1 and every "Until that ... works" paragraph of §2 to §3.5 | Adoption-claim rules for imported `std/drain` (`backlog-drain`, `gap-drafter`, `run-item`) and `std/resource` (`finalize-selected-item`) | removed code | `std/drain`, `std/resource`, `backlog-drain` and `finalize-selected-item` removed 2026-11-12 and refuse with `form_retired` ([frontend specification §31](../design/workflow_lisp_frontend_specification.md#31-backlog-drain): "the head refuses with `form_retired` at every target") | `stdlib_modules/std/` holds only `context`, `host`, `improve`, `phase`; `form_retired` is a string literal in `orchestrator/workflow_lisp/definitions.py` and `expressions.py` |
| 4.2 | §2.1.1 | "Pure helpers, effectful procedures, and workflow entrypoints share the same typed return-value model." | [Native transportable returns, Summary](../design/workflow_lisp_native_transportable_returns.md#summary) | "Workflow Lisp should use one typed return model across pure functions, procedures, provider and command effects, workflow calls, and public workflow boundaries." | Read |
| 4.3 | §3.3 | "inside `((BLOCKED blocked) ...)`, `blocked` has the `BLOCKED` payload type" | [Frontend specification §11](../design/workflow_lisp_frontend_specification.md#11-pattern-matching) | "The author-facing model is **refined match binders**: inside each `match` arm, the binder is the selected variant payload, so that variant's fields are in scope directly on the binder." | Read |
| 4.4 | §3.4 | No compatibility carrier (`run_state_path`, summary path) crosses a stdlib child-call boundary | removed code | The carriers named belong to the removed drain and resource route (4.1) | As 4.1 |
| 4.5 | §4 | `std/phase` exports its own review/fix types; `review-revise-loop` and `phase-scope` compile through the ordinary imported-stdlib route, with no compiler-name special case | [Frontend specification §6](../design/workflow_lisp_frontend_specification.md#6-name-resolution) | "Imported bindings are the primary route for stdlib forms such as `with-phase` / `phase-scope`" ... "A stdlib extension such as `review-revise-loop` must resolve through an imported stdlib binding or an allowed stdlib macro expansion before ordinary typechecking and WCC elaboration; promoted compilation must not silently elaborate it through a literal-name compiler branch." | `std/phase.orc` exports `ReviewDecision`, `ReviewFindings`, `ReviewLoopResult`, `phase-scope`, `review-revise-loop` |

### `trial_runs`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 5.1 | Opening paragraph | Path-mode run references keep their pure-child and typed result/delta/accounting contracts | [Evaluated execution §1.2](../design/workflow_lisp_evaluated_execution.md#12-ordinary-path-run-reference-placement-at-235) | "Path-mode run references participate directly or transitively through calls in ordinary effect-admitting control" ... "Preserve ordinary types, union/arm proofs, structural evaluation order, collection transportability and traversal bounds." | Found in the other session's working copy |
| 5.2 | Opening paragraph | Named static workflow confinement has its own owner | [Run-reference expression environments](../design/workflow_lisp_run_ref_expression_environments.md) | "**Scope:** target-2.38 confinement contract; public command-only admission and separately qualified provider transport." | Read |
| 5.3 | E0 Requirements | The direct control is canonical, makes exactly one provider call, and returns a typed result | [Workflow catalog](../../workflows/README.md); [comparison harness D3](../design/orc_effectiveness_comparison_harness.md) | Catalog: "E0 canonical direct control with typed inputs `task: String`, `model: String`, and `effort: String`, exactly one composed provider boundary, and a direct `Bool` result." Harness: "The control copy lives in the harness under `control/`; a test asserts it differs from the library file by that one line." | `workflows/library/control/direct_task.orc` exists; `test_public_direct_task_preserves_bool_policy_and_one_call_resume`; catalog sentence found in the other session's working copy |
| 5.4 | E0 Requirements | Accounting parity; workspace-native output, so an evaluator cannot unblind on artifact shape | removed code | Their consumer, E2 trial evidence and adjudication packets, was removed 2026-11-12 (`trial` refuses `form_retired`); experiments now run through the comparison harness, whose design owns its evidence rules | `orchestrator/workflow/trial/` absent |
| 5.5 | Removal notice; E1/E2 sections (already moved to the history file) | `trial` form, command, SDK; bundle-mode children; submodule/LFS refusal; trial ledgers | removed code | [Salvage record](../design/trial_and_adjudication_salvage.md); CLI owns the refusal | `trial` head refuses `form_retired` (plan probe) |
| 5.6 | Deliberately Not Selected, isolation bullet | Generated tool-using candidates excluded without positive sandbox evidence | [Program-search boundaries §6](../design/workflow_lisp_program_search_boundaries.md#6-honest-security-boundary) (amended; this document defers to it) | "Provider-in-the-loop candidate evaluation is permitted under a disclosed workspace boundary" ... "This is hygiene, not isolation, and is reported as such" | Read; the boundaries document wins by this document's own Authority paragraph |
| 5.7 | Design-Principle Compliance | Principles 28, 29, 30 | Design principles §28 to §30 | §28: "Every compiler or runtime decision that denies, disables, or withholds a capability emits a coded diagnostic naming the rule it applied and the value it rejected." | Read |
| 5.8 | Open Questions 1 | `run-ref` inputs start from the closed transportable value set | Evaluated execution §1.2 | As 5.1 ("collection transportability") | Read |
| 5.9 | Layered Structure, Feasibility Entry Proofs, Spec Amendment Inventory, Stop Rules, Verification Strategy, Open Questions 2 to 5 | E0 to E3 platform plan and program-level stop rules | history | The E-component plans linked in the record; experiment rules now in `AGENTS.md` and the harness design | Not current rules |

### `mlevolve_workflow_lisp_system_architecture`

Never built; dropped by the [roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#dispositions).
Its requirements are targets for a workflow that does not exist. Those that restate a current rule:

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 6.1 | §4, §7.3, §7.5, §14, §18 | Reports, stdout, pointer files and prompt text are views; provider and adapter results are structured values | Design principles | "Structured bundles are authority; reports are views." | Read |
| 6.2 | §11 | Adapters may not parse reports or use stdout as canonical state | [Command adapter contract](../design/workflow_command_adapter_contract.md) | "They must not establish workflow meaning by parsing markdown reports, rewriting ad hoc JSON in place, or relying on stdout as semantic authority." | Read |
| 6.3 | §10.6 | Type parameters are compile-time only and specialize before runtime-visible contracts | [Parametric type system](../design/workflow_lisp_parametric_type_system.md) | "type parameters are compile-time-only names, resolved before executable IR;" "each concrete instantiation is monomorphic;" | Read |
| 6.4 | §15 | Generated code is untrusted; no real execution without a sandbox contract | Program-search boundaries §6 | As 5.6 | Read |
| 6.5 | §2, §3, §5 to §13, §16 to §18 (rest) | Module layout, adapters, unions, phases and acceptance of the MLEvolve workflow | history | Never built; no `workflows/examples/mlevolve_approx.orc` | File existence |

## T1: Notices Normalised (Already Historical)

### `judgment_views`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 7.1 | Reader scope; Prompt-Attempt Result Locator; Read-Only Judgment Projection; Diagnostics | "locator/schema validation, content-sealed attempt provenance, result-plus-evidence joins and non-authoritative report projection remain retained contracts"; the closed locator; the ten `judgment_*` codes | removed code | [Observability, Judgment Views (Historical)](../../specs/observability.md#workflow-lisp-judgment-views-historical): "The read-only judgment views that `report` derived from the old runtime's state ... are removed" | `git grep` in `orchestrator/`: 0 hits for `prompt_attempt_result_binding`, `judgment_views`, `judgment_result_binding_missing`, `judgment_result_evidence_invalid` |
| 7.2 | Reader scope | "Historical step/iteration/result locators must not be reinterpreted as an evaluated memo schema" | [CLI](../../specs/cli.md) | "Original run data is preserved. Recovery requires the exact complete release/environment qualified for the particular family; preserved source or a package pin alone is no universal recovery guarantee" | Found in the other session's working copy |
| 7.3 | Status | Q3 identity v1 that Q4 consumed | [Prompt identity diagnostics](../design/workflow_lisp_prompt_identity_diagnostics.md) | "exact carrier value `workflow_prompt_attempt_identity.v1`;" | `PROMPT_ATTEMPT_IDENTITY_VERSION` in `orchestrator/workflow/prompt_identity.py` |
| 7.4 | Required existing-expression composition seam | A `list/map-effect` child-call argument may carry `path/join-under`; existing `path_join_under_child_invalid` / `path_join_under_escape` refusals hold | [Pure list traversal](../design/workflow_lisp_pure_list_traversal.md#bounded-effectful-binder-listmap-effect) | "Its arguments may be arbitrary already-supported pure expressions over the binder and enclosing lexical bindings." and "An invalid child fails with `path_join_under_child_invalid`; an absolute or escaping child fails with `path_join_under_escape`." | Both codes are string literals in `orchestrator/workflow/pure_expr.py`; `test_path_join_under_rejects_absolute_or_escaping_child` |

### `lexical_execution_checkpoints`

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 8.1 | Current safety owner | "Old profiles cannot resume, replay or repair in this package." | [State, State Integrity and Recovery](../../specs/state.md#state-integrity-and-recovery) | "Historical profiles refuse before locks, checksum/projection checks, repair or executor construction with `workflow_execution_profile_retired`, exit 2, without changing original data." | String literal in `orchestrator/cli/commands/resume.py` and `invalidate.py` |
| 8.2 | Current safety owner | "A demonstrated exact complete release/environment is required for historical recovery; otherwise resumability is retired." | [Executor retirement §7](../design/workflow_lisp_executor_retirement.md#7-recovery-policy-and-one-deletion-gate) | "A family without demonstrated exact-release recovery has retired resumability, rather than a general previous-release recovery promise." | Read |
| 8.3 | Current safety owner; Retained design constraints | "No coarse fallback or backward scan is promised"; "present-but-unusable, ambiguous or unsafe state fails closed without scanning older records" | State, State Integrity and Recovery (the historical checkpoint paragraphs, kept "to interpret historical evidence") | "An invalid, unsafe, absent, or non-restorable nearest point fails closed; default resume never searches an older point. Any coarse or older-boundary recovery is explicit/operator-directed or future functionality." | Read; the plan's T1 proof for this document |
| 8.4 | Retained design constraints | "typed values/proofs and identity must be revalidated before reuse" | [Evaluated execution §8.1](../design/workflow_lisp_evaluated_execution.md#81-what-the-memo-decides) | "A committed result with input digest equal to the digest of `x`, not invalidated \| Return the result." / "A committed result with another input digest \| Stop with `effect_input_diverged`" | `effect_input_diverged` is a string literal in `orchestrator/cli/commands/evaluated.py` and `cli/recovery.py`; found in the other session's working copy |
| 8.5 | Retained design constraints | "execution-position caches never become domain state, provider evidence or prompt values" | removed code | The evaluated runtime keeps no execution-position cache: "Because evaluation is a function of the program, the inputs and the committed results, it reaches the same effects in the same order up to the first effect without a commit" (evaluated execution §8.3); State: "The checksum, projection, lexical-checkpoint and backup details below describe the retired flat runtime" | Read |

### `provider_live_binding` and `provider_peer_messaging`

The two documents share their retained paragraph; rows 9.3 to 9.5 cover both.

| # | Document, section | Rule as written | Owner | Owner's sentence | Check |
| --- | --- | --- | --- | --- | --- |
| 9.1 | live binding, Status | Provider capability validation (`turn_boundary_resume`), provider execution, cleanup and native session codecs owned by Providers | [Providers](../../specs/providers.md) | "`turn_boundary_resume: true` is a structural capability declaration." ... "Provider name, input mode, TTY behavior, or session support without that declaration never implies the capability." | Found in the other session's working copy |
| 9.2 | peer messaging, Status | Structural `interactive_terminal_turn_queue.v1` validation owned by Providers; "Retaining an adapter does not admit a peer-group coordinator." | Providers | Providers: "`interactive_session_support` is an explicit structural capability." ... "Unknown capability fields, unsupported schema versions, malformed placeholders, and forcing key/action tokens reject the template." Providers, phased delivery: "Agent-valued calls, capture/session publication, isolation/confinement, supervision/peers and reachable parallel-worker phased effects remain excluded." | As 9.1 |
| 9.3 | Both, retained paragraph | "Validated provider capabilities must fail closed on absence, malformed data or unsupported operations." | Providers | As 9.1 and 9.2; for phased delivery: "absent/malformed capability never selects composed fallback." | As 9.1 |
| 9.4 | Both, retained paragraph | "Transcript/pane bytes, receipts and diagnostic views are never typed result authority." | [Observability](../../specs/observability.md); [Agent Sessions](../design/workflow_lisp_agent_sessions.md) | Observability: "Pane bytes and transcripts remain display evidence; parsers and result validation continue to consume the authoritative provider transport and declared output bundle." Agent Sessions: "Provider records and tmux/transcript observations cannot replace an adapter receipt." | Agent Sessions sentence found in the other session's working copy |
| 9.5 | Both, retained paragraph | "Partial/member attempts cannot be published as a complete result, and cleanup/recovery cannot fabricate a commit or target a different attempt." | Evaluated execution §8.3 (crash table); Providers | Evaluated: "A partial file does not parse or does not validate, so it is never a result" ... "the file is evidence, not a result. Only `committed` makes a result". Providers: "with exact prior-attempt resource/candidate ownership checked before a fresh attempt. No old state allocator, checkpoint, quarantine, phase-cursor replay or provider transcript becomes execution authority." "Member" attempts belonged to the removed group executors | Found in the other session's working copies |
| 9.6 | Both, anchors and history pointer | Group state machines, recovery amendments | removed code | Executors removed 2026-11-11 (git tag `archive/dead-executors-2026-11-11`); [salvage record](../design/live_provider_supervision_and_peers_salvage.md) | Matrix rows "Retired" |

## Findings For The Plan

- No T1 document was refused: every rule found has an owner, is removed code, or is history.
- `refactor_architecture` (row 3.9): its target module boundaries (no process-global compiler
  state, one traversal, typed registries) are partly adopted in the code and stated nowhere
  else. They were read as guidance of a closed refactor plan, not rules; a reviewer who reads them
  as rules should reopen that document.
- `refactor_architecture` row 3.8: its one "required invariant" never held (no `ExprNode` coverage
  test).
- `trial_runs` row 5.3: there are two copies of the direct control
  (`workflows/library/control/direct_task.orc` and `experiments/compare/control/direct_task.orc`);
  "canonical" now means the harness's one-line-difference test.
