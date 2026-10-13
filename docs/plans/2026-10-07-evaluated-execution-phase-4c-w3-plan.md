# Evaluated execution Phase 4c / W3 implementation plan

> Recovery, 2026-10-10: this document was restored from persistent source
> copies and recorded literal edits after the original `/tmp` product,
> qualification, raw-artifact and checkpoint directories disappeared. Historical
> results and acceptance hashes remain historical; recovered Task 4 qualification
> has separate fresh evidence below. Current recovery and required checks are
> governed by the [recovery plan](2026-10-10-phase4c-recovery-plan.md).
> W3 remains selected at 2.36 with one `std/improve` API per source import graph,
> after the bounded pure correction and before Phase 5; Task 4 has bounded scratch
> PASS, while product delivery remains open.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. The coordinator assigns one execution window and independent reviewers. Checkboxes record executed evidence, not design acceptance. No implementer commits without coordinator instruction.

**Goal:** Correct pure lexical capture, then deliver bounded local-hook capture/signature inference and remove context forwarding from `improve`, preserving consumers and compatible retained runs.

**Architecture:** Extend existing `let-proc`, ProcRef specialization and generated-procedure owners; use the evaluated runtime unchanged. At the selected target 2.36, select one bundled `std/improve` source API per source import graph while keeping the legacy module's bytes/path for old entries.

**Tech stack:** Existing Python frontend, Workflow Lisp stdlib, pytest, deterministic command/provider fixtures and public `python -m orchestrator` entries.

**Status:** W3 is implemented at target **2.36**. Recovered Tasks 4/6/11–13, Task14A/14B, F-CODE-1 and the capture-specialization correction have independent bounded review and coordinator acceptance. The pure prerequisite has separate fresh bounded revalidation; original acceptance and lost `/tmp` artifacts remain historical. Nine representative public consumer cases, four capture pilots and the 232 → 220 helper-plus-callers census are accepted within Task14B. The [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md) owns final package-bound compatibility, affected/full outcomes, causal dispositions, independent reviews and delivery. W3 precedes Phase 5, whose D1 target was separately selected as **2.37** on 2026-10-12; implementation remains pending; W0/W1/W2/W4 and EL/AA/CE remain unselected by this work.

**Tradeoff:** Incomplete hooks have one authored direct consumer site. Retargeting a source graph requires migrating its old five-argument `improve` calls; supporting simultaneous old/new authorities would require a separate module-identity design. Neither broader inference nor that module system is included.

## Authority and evidence boundary

Read `docs/index.md`, `docs/capability_status_matrix.md` and `docs/design/README.md` first. Durable authorities are `docs/design/workflow_lisp_write_once.md` §§6/9/11/12; the local-procedure and partial-application designs; `specs/versioning.md`; and evaluated execution §13 plus `specs/state.md`/`specs/cli.md` for resume. This plan implements only component Tasks **4 → 6 → 11 → 12 → 13 → 14** of [repetition reduction](2026-09-29-workflow-lisp-repetition-reduction-plan.md), under [parent Phase 4c](2026-09-29-workflow-lisp-evaluated-execution-plan.md#phase-4-consumer-capabilities-and-authoring). W0/W1/W2/W4, Phase 4a/4b, Phase 5 and remaining Phase 6b migration are outside scope.

Baseline: `a4666341bb7690717277711fa25409a9aa3f5c91`; worktree `/tmp/orc-phase4c-w3-20261007`. **C4** is `/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-07-evaluated-execution-phase-4c-w3-plan`; **C6** is its sibling `2026-10-07-evaluated-execution-phase-6a-pilot-plan`.

- Accepted technical candidate: C4 `w3-design-decision-brief.md`, SHA-256 `7fd1c7ac68f412a9e31e86e38d7101491d1cf22c2baa29ac4787f9a85e3905af`.
- Independent technical PASS: C4 `w3-independent-design-rereview.md`, SHA-256 `7b8fe3ab938620b9785b60cc76886390e523744f8bc17e41826776cb3fdaca56`; coordinator scope: `w3-technical-design-acceptance.json`. Acceptance supersedes the brief's historical “not yet rereviewed” heading for this exact digest only.
- C4 `w3-owner-decision.json` records the subsequent owner selection of 2.36 and graph migration; it supersedes the brief/technical acceptance's historical pending-owner wording, without waiving their feasibility or compatibility gates.
- [Write-once §§6/9/12](../design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context) and the component plan reconcile that accepted contract; independent review and C4 `w3-maintained-authority-acceptance.json` accept the reconciliation. Do not infer supported syntax from planning documents.
- C4 `pure-capture-prerequisite-acceptance.json`, SHA-256 `3050538cc8da06a4e749d76a31c84c30bfcb1a6947e20f1b8dc9ae75d415950f`, records original-worktree acceptance before interruption after historical final code/spec PASS; recovery verification is separately recorded in the correction report, with no phase closeout, commit/merge or shared full-campaign PASS.
- C4 `w3-task0-readiness.json`, SHA-256 `285267d1a67a5ad2ba5eb080d087ad4606395130c321fd5eef65d524cc732859`, accepts Task 0 for scratch Task 4 only. It binds the inventory refresh, authority/owner decisions and `/tmp/orc-w3-qualification-20261007/preparation/receipt.json`; preparation alone establishes no executable feasibility.
- [Phase 6a report](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md) and C6 `task3-w3-inventory.json` supply bounded caller evidence, not exhaustive migration or W3 feasibility. Reuse evidence only with its revision, identity inputs and limitations.
- [Pure-capture five-task plan](2026-10-07-workflow-lisp-pure-capture-fix-plan.md) remains the sole correction plan. Its separate authorization/evidence controls execution; this plan neither duplicates nor expands it.

## Execution rules and exact owners

The coordinator owns gates, integration, evidence reuse and final diff inspection. Delegate bounded code/test tasks to Implementation / Luna 6 xhigh; return corrections to that implementer; escalate only as repository policy permits. A distinct Review / Sol 6.1 high reviews code and this plan; Review / Astra 6 xhigh reviews design/spec changes. Design decisions return to Design / Astra 6 xhigh. Every delegation names role and artifact type.

All commands run from the worktree root. Before added/renamed tests, run `pytest --collect-only -q <changed modules>`. Each task first runs its smallest new failing selector, records the intended failure, makes the bounded change, then reruns for GREEN. Preserve exact commands, revision, exit and output in C4; no prompt-phrase assertions. Broad/slow commands require the `tmux` skill and `pytest -q -n 16 --dist=worksteal`. Tests/CLI/prototypes share the coordinator's sole execution window; reviewers remain read-only.

| Existing file owner (under `orchestrator/workflow_lisp/` unless explicit) | Responsibility |
| --- | --- |
| `expressions.py`, `expression_traversal.py`, `conditionals.py` | Local binding representation/parser, scoped traversal and structural users |
| `procedure_typecheck.py`, `procedure_refs.py`, `procedure_specialization.py`, `specialization_typecheck.py` | Generated locals, expected signatures, existing unifier and specialization |
| `compiler_session.py`, `typecheck_context.py`, `typecheck_dispatch.py` | Short-lived pending-local scope only if qualified; restore on exit |
| `closed/frontend.py`, `closed/names.py`, `closed/build.py` | Both local-declaration key/DId walkers and existing closed consumers |
| `syntax.py`, `orchestrator/workflow/validation.py` | Target allowlists; `syntax.py` owns predicates, including `target_dsl_uses_evaluated_execution` |
| `compiler.py`, `modules.py` | `_effective_source_roots`, stage-1 graph entry and `_compile_stage3_linked_module_graph`, `resolve_module_graph`, import-path/root checks and provenance |
| `wcc/defunctionalize.py` | `_capture_opaque_projection_scope`: declaration-boundary walker to review if the `LetProcExpr` representation changes |
| `stdlib_modules/std/improve.orc` | Legacy source: preserve bytes and path under the selected migration rule |
| `orchestrator/cli/commands/evaluated.py` | Resume rebuild/digest guard: compatibility oracle, no planned guard or recipe change |

Do not add an evaluator opcode, persisted capture schema, runtime ProcRef, generic constraint solver, per-importer module versions, overload, `improve-v2`, effect-policy change or second production scratch helper. Do not redesign internal generated names merely because they include spans; canonical identity already has its owner.

## Task 0 — Refresh ownership and record decisions

**Role/artifacts:** Coordinator plus read-only scout; inventory refresh
`/tmp/orc-pure-capture-feasibility-20261007/w3-task0-inventory-refresh.md`
(SHA-256 `e29531d30ea1ade92f8a0166f69bb9af4749efe1902e6ebc943d214ed76d4899`),
C4 `w3-owner-decision.json` and `w3-task0-readiness.json`. Task 0 is accepted;
its readiness receipt supersedes pending-status wording in the historical
read-only inventory. No W3 product writes are authorized by Task 0.

- [x] Refresh `rg -n 'LetProcExpr|LetProcBinding|resolve_module_graph\(' orchestrator` and `rg -n 'std/improve|\(improve |improve_experiment_proposal' workflows tests experiments`. Trace actual callers rather than treating match counts as a semantic census.
- [x] Include shared producers `tests/workflow_lisp_improve_stdlib_sources.py`, `tests/workflow_lisp_generic_union_runtime_sources.py`, `tests/workflow_evaluated_consumer_sources.py`, `tests/workflow_evaluated_recovery_cases.py`, closed fixtures `if_in_hook.orc`/`provider_review.orc`, proposal readers, and historical spike/census copies. Assign migrate/old control/historical/Phase 6b to each maintained owner.
- [x] Trace target registration/predicate and source-graph callsites, including CLI/LSP and source snapshots; refresh the table above with exact newly discovered owners before edits. Record baseline package/source/workspace paths, interpreter and `PYTHONHASHSEED=0`.
- [x] Record the owner decision in C4 `w3-owner-decision.json`: target 2.36, one API per source graph, old source caller migration on retargeting, sole-old-snapshot validity, unchanged overlap refusal, and existing truthful-pin/resume rules. This checkbox records selection only.
- [x] Verify the selected decision and prerequisites before target registration, stdlib resolution or consumer migration. Pure correctness work remains independently governed; a future change of compatibility policy returns to Design/review before dependent tasks.
- [x] Reconcile accepted brief into maintained write-once design/component plan through a separate Revision / documentation task and independent review, preserving proposed status. Record the resulting authority digests in C4 before new-target product work. Reconciliation is a separate documentation revision; it does not close executable qualification or delivery.

## Prerequisite — Complete the separate pure-capture correction

**Role/artifacts:** Existing assigned implementer/reviewer; reuse all five tasks and their receipts in the linked pure-capture plan. Depends on its own feasibility authorization, not W3 target selection.

- [x] Obtain accepted shared-seam feasibility, lexical 8 instead of 101, accepted-correct raw artifact controls, and actual committed-boundary compatible resume before W3 product delivery. Preserve the effectful `b11e678` controls and unrelated refusals.
- [x] Link correction Tasks 1–4 evidence and review; do not rerun valid controls or launch another full suite. Its final phase-wide full-suite checkbox and closeout reference Task F below.
- [x] The accepted bounded correction evidence satisfies the ignored/unused-hook and identity guard. A later concrete gap still returns to Design; do not hide it with W3 syntax or infer universal lexical correctness.

## Task 4 — Minimum executable qualification before broad implementation

**Role/artifacts:** Implementation / disposable compiler prototype and evidence; independent technical review. Task 0 and the bounded correction prerequisite have original-worktree acceptance before interruption; historical execution was **RUNNING** only in the now-lost `/tmp/orc-w3-qualification-20261007` with its fixed `package/` and preparation receipt. Recovery now has **PASS for bounded Task 4 only**, with sixteen reviewed source owners, subsequently promoted for delivery; subsequent Tasks 6/11–13 and bounded Task14A/14B are accepted below; bounded Task14 compatibility is subsequently accepted; the closeout owns final F status.

**Recovered acceptance:** C4 `recovery-20261010/task4-coordinator-acceptance.json`
([coordinator acceptance](/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-07-evaluated-execution-phase-4c-w3-plan/recovery-20261010/task4-coordinator-acceptance.json))
accepts the [final receipt](/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-07-evaluated-execution-phase-4c-w3-plan/recovery-20261010/qualification/revalidation/task4-final-evidence.json)
(SHA-256 `65f2f09cb4566c90d50b70295cf36cb1f45e578c84c9f747a81a620549116ab0`)
and [independent review](/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-07-evaluated-execution-phase-4c-w3-plan/recovery-20261010/qualification/revalidation/independent-code-review.md)
(SHA-256 `043d0f2a22ec74158816c7200c6def3930526243806bb146c9d937e65bd462ca`).
These supersede the receipt's earlier pending-review status and the review's
historical HOLD entries. C4 `recovery-20261010/pure-prerequisite-revalidation.json`
records the fresh prerequisite checks. `recovery-20261010/task4-product-promotion.json`
records promotion of those sixteen owners with only the historical trailing
whitespace removed; Task 6 is subsequently accepted below.
The prototype remains direct-tail only. The lexical alias `producer` control
still refuses with `procedure_call_unknown` on all four compared source states;
it is neither PASS nor a new raw/resume waiver. Missing historical fixture bytes
remain missing; reconstructed controls are labelled, not certified as originals.

Qualify only the unproven pending-local/readiness mechanism, builtin alternate-root selection seam and one public lifecycle case. Fixtures obey the one-authored-direct-consumer-site restriction; the R1 `need(h)`/`seed(1,h)` counterexample and its adversarial matrix belong to Task 13. Qualification does not complete W3, capture/site validation, snapshot compatibility or package/LSP support; Tasks 11–14 and F retain those obligations.

**Bounded prerequisite discovered during qualification:** a fully annotated
2.35 captured-command hook inside a concrete loop fails identically on delivered
`a4666341`, the post-pure compiler and W3. This is a separate pre-existing
`compiler_defect`, not a new compatibility exception. Accepted Design/review:
`/tmp/orc-w3-qualification-20261007/capture-frame-acceptance.json`
(SHA-256 `d504f4bc11fd83631ac5bc90bd18ba597fa2e82903fb44e9836605842f9a15c0`). Extend only `closed/build.py`'s existing
capture-route preparation and `closed/command_templates.py`'s frame seed to
transport slot → resolved bound argument → creator identity/type into the
existing retained rows. A demanded capture origin must resolve exactly;
literal/computed arguments may legitimately lack a whole-expression identity.
Never substitute a composite slot for a free leaf or relax the refusal.
Preserve slot/key/order and serialized/runtime structure. Follow the association
through preparation comparison and final emission; touch `preparation_check.py`
or existing `Definition.binding_aliases` only after a concrete next loss and
coordinator disposition. Require the same old RED→GREEN, full raw accepted
controls, shadow/two-environment and literal/computed controls, invalid demanded
origin/retargeted-preparation refusals, and the public Task 4 lifecycle. No
product promotion or Task 4 PASS is implied by this owner addendum.
The subsequent final-emission trace retains the ID and capture wire but lacks
`Definition.binding_aliases`. Coordination authorizes the conditional transport
through compile-only metadata on the existing `CallableRequest`, reusing those
associations for the final alias map and `preparation_check.py`'s existing
capture-index tokens. Keep demand sets and contradictory-preparation guards;
no new registry, serialized field or semantic ID. Exact disposition:
`/tmp/orc-w3-qualification-20261007/capture-frame-wire-extension.json`
(SHA-256 `9b453d82f3197f413ca364939e024d6a4b189721c091102c9d7eea6356d6d5c0`). Its implementation/guards were unqualified at that historical cut; the recovered bounded acceptance above records their fresh qualification.

The first runtime check exposed a second evaluation of a retained capture's
historical RHS. Extend `conditionals.py`'s existing closed-program operand
normalization to honor whole-binding origins, as bound-value elaboration already
does. Its `wcc/elaborate.py` argument consumer must keep the normalized ProcRef
container compile-time, rather than materializing it as a runtime value.
Preserve the producer representation; continue normalizing new operands
and nested reference bindings. The independent frame/wire transport remains
necessary. Design disposition: scratch `capture-value-once-disposition.md`,
SHA-256 `a0564ba9a772de33c953469c7b24fb7284e9cdca504b73ff2e107288b7f2c247`.
Require one dispatch for the formerly rejected loop case and full raw equality
for the accepted straight-line control before the W3 lifecycle. This adds no
compatibility waiver or new runtime mechanism.

Mixed-capture checks also found earlier pure-call expansion copying a bound
effect into the helper body, despite an existing runtime capture slot. Extend
the shared normalizer in `functions.py`, with the existing compilation route
passed from `compiler.py`: whole-origin capture rows consume the whole value
without first reifying its free leaves; on the evaluated route, preserve a
ProcRef call when expansion would repeat an effectful bound value without a
whole origin. Use existing pure normalization and resolved effect facts, not
the syntactic assumption that every procedure call is effectful. Preserve the
strict pure-function checks and raw pure computed-argument controls. Existing
Builder invocation/capture handling consumes the retained call; no second view
or carrier is introduced. Scratch Design disposition
`capture-computed-slot-disposition.md`, SHA-256
`dfd7aae091ef535a23d09aef454df62828bd6ff2db8c849b3c1696b7acc68c3d`,
governs this extension; qualification at that historical cut awaited the mixed
and distinct capture-environment cases now recorded in the recovered acceptance.

- [x] RED: one typed `initial`, two omitted-signature local hooks and a scratch no-context helper fail on the unchanged post-pure baseline with `target_dsl_unsupported` (public compile exit 2), as recorded in the final receipt. The scratch helper is evidence only, not a shipped API.
- [x] Prove the smallest pending-local seam: creator capture environment survives until the consumer call; ordinary arguments bind `S`, review's body binds `F/B`, revise becomes ready; each ready body is checked once **per readiness invocation**. Both declaration/argument orders and body-check counts are recorded. No retry-by-guessing or second registry.
- [x] Prototype only builtin-candidate substitution with an actual alternate source root, selected `stdlib_modules/w3/std/improve.orc`, retaining syntax header 2.33. Demonstrate old/new entry selection and the actual selected source path/root, including correct nested-root validation. Do not copy the whole stdlib; package/LSP, ambiguity, imports and snapshot coverage stay in Task 14.
- [x] Run one minimal public compile/run/committed stop/resume/replay through the scratch implementation with existing deterministic harnesses. The primary lifecycle stops with exit 75 after one committed effect; resume and two completed replays exit 0 without redispatch or changed retained artifacts. A separate reversed-order run passes; no second reversed stop/resume sequence is claimed.
- [x] Deliver exact bounded prototype diff, commands/exits, accepted-control full raw hashes, body-check counts, module paths and limits. Independent review + coordinator accept the mechanisms in the linked receipts. Reuse valid harnesses/evidence with their revision and identity limits, and promote qualified code where suitable after the pure-prerequisite checks before extending it in its delivery owner; do not independently rebuild a second implementation or claim undelivered matrix coverage.

## Task 6 — Register only the selected target

**Role/artifacts:** Implementation / target gate and behavioral tests. Depends on Task 4 PASS, completed correction prerequisite and recorded owner decision.

**Files:** `orchestrator/workflow_lisp/syntax.py`, `orchestrator/workflow/validation.py`, `orchestrator/workflow_lisp/closed/build.py`, `orchestrator/workflow_lisp/closed/check.py`; audit existing run-ref allowlists without duplicating their registries. Update `specs/versioning.md`, `specs/dsl.md`, State's authority/run-root section and evaluated-design §8.4 with delivered evidence; create `tests/test_workflow_lisp_w3_target.py` and reuse artifact/check tests.

**Target contract, qualified design decision:** the closed program's top-level
`target` is the entry's source target, not its representation version. Emit
`typed.target`; validate string, registered target and evaluated-route predicate.
At this cut only 2.35/2.36 qualify. Keep schema, representation, runtime profile,
readback equality and the separate internal run-ref target unchanged. The
public pure-2.36 readback failure is retained as RED. Accepted Design and
independent review are bound by
`/tmp/orc-w3-qualification-20261007/target-artifact-acceptance.json`
(SHA-256 `f3cac9cc3875f2648d5c12acc49fea655f0165d0c1730be86b0a8a1abbcf0469`).
This authorizes the minimal build/check owners in Task 4 scratch qualification;
Task 6 product promotion still requires Task 4 PASS. There is no new profile
or compatibility waiver. Compare the pure fixture's remaining structure and
result, while requiring source/manifest target equality and distinct digests.
Cover old/unknown/malformed artifact targets, retained 2.35 raw/resume and the
existing safe refusal after source retargeting. Structural equivalence does
not mean raw equality.

- [x] RED: add `test_selected_w3_target_uses_evaluated_route` and old-target controls; use `W3_TARGET = 2.36`. A program using no W3 syntax takes the existing evaluated route with equivalent semantics/canonical structure, accounting explicitly for target identity.
- [x] Add the target and one named predicate using the existing registration pattern. Preserve per-defining-module syntax admission; entry target controls graph API selection, not imported syntax permission.
- [x] Collect the new module; run `pytest -q tests/test_workflow_lisp_w3_target.py`. Expected GREEN; existing numeric/2.35 target tests remain independent owners, not renamed as W3 evidence.

**Recovery evidence:** C4 `recovery-20261010/task6-delivery/coordinator-acceptance.json`
records code/spec PASS and 187 passing affected tests (plus the renamed
unsupported-target control). This receipt records the Task 6 cut; subsequent bounded acceptances are summarized in the current status above.

## Task 11 — Several bindings, existing generated procedures

**Role/artifacts:** Implementation / parser, AST consumers and tests. Depends on Task 6.

**Files:** `expressions.py`, `expression_traversal.py`, `conditionals.py`, `procedure_typecheck.py`, `closed/frontend.py`, `closed/build.py` from the table; create `tests/test_workflow_lisp_let_proc_bindings.py`.

- [x] RED: `test_multiple_local_bindings` covers two fully annotated hooks passed to one helper; retain the original single-binding spelling. Add located refusals for empty/duplicate/malformed lists, sibling/self references, nesting and escape, plus old-target rejection of the new list spelling.
- [x] Extend the existing binding container and every structural consumer. All bodies see the creator environment; only the consumer sees locals. Update **both** closed local key and DId syntax walkers. No parallel expression family.
- [x] Preserve existing-target single-binding artifacts. New-target capture canonicalization belongs to Task 12, not an all-target identity rewrite.
- [x] Collect the new module, run `pytest -q tests/test_workflow_lisp_let_proc_bindings.py`, then `pytest -q tests/test_workflow_lisp_procedures.py -k let_proc` and relevant changed closed-name selectors. Expected GREEN for new cases and unchanged baseline dispositions for controls.

Acceptance: C4 `recovery-20261010/task11-delivery/coordinator-acceptance.json` records independent compliance/code PASS, 18 new tests, 17 legacy controls, six closed identity controls, unchanged single-binding artifacts and public result 15. Subsequent Task 12 capture inference and Task 13 bounded signature rules are accepted below; their exact composition limits remain open.

## Task 12 — Infer creator-scope captures

**Role/artifacts:** Implementation / scoped capture analysis and behavioral tests. Depends on Task 11.

**Files:** `expression_traversal.py`, `procedure_typecheck.py`, existing ProcRef/specialization owners only as necessary; tests remain in `tests/test_workflow_lisp_let_proc_bindings.py` and existing public capture harnesses.

- [x] RED: add `test_inferred_capture_equivalence` for explicit/inferred pairs, reordered/superset lists, field-root capture, parameter/local-binder shadowing, lexical ProcRef callees, later call-site shadow, two distinct local bindings and missing/unknown/duplicate authored captures. Top-level procedures/types/labels/providers are not lexical captures.
- [x] Reuse binding-aware free-name traversal plus explicit callable-position coverage. Freeze capture values and `BindingIdentity` from the creator environment. Explicit lists are checked upper bounds; validate every authored entry, then sort **used resolved names only at W3_TARGET** for either spelling. Old targets retain authored order/behavior.
- [x] Compare same-route canonical definitions/programs; distinguish source-map differences from semantic identity. Retain direct, named, forwarded and effectful bound controls from the correction.
- [x] Collect changed modules; run `pytest -q tests/test_workflow_lisp_let_proc_bindings.py -k capture` and `pytest -q tests/test_workflow_evaluated_phase6a_pilot.py::test_bound_review_captures_the_committed_account_before_shadowing_and_resume`. Require GREEN and capture/no-redispatch evidence.

Acceptance: C4 `recovery-20261010/task12-delivery/coordinator-acceptance.json` records independent HOLD→PASS after repairing import isolation and immutable-input evidence. The 40-case module, legacy controls, public values 6/28/11 and no-redispatch checks pass; corrected raw controls preserve all 2/2/15 emitted files. Two composition defects remain OPEN. The later independently reviewed `task12-delivery/original-baseline-causal/coordinator-disposition.json` confirms that both exact explicit-2.35 fixtures already reject at original a466, with identical diagnostics through pure and Task4 qualification; six compiles and no runs. This is no general compatibility waiver or proof of supported composition. Final F retains their causal disposition.

## Task 13 — Infer signatures within one authored consumer call

**Role/artifacts:** Implementation / bounded typechecking and tests. Depends on Task 12.

**Files:** `procedure_typecheck.py` (`_typecheck_let_proc_expr_impl`, `_typecheck_parametric_procedure_call`, `_infer_parametric_type_bindings`), qualified scoped-state owners from the table; create `tests/test_workflow_lisp_local_hook_signatures.py`.

- [x] RED: `test_review_result_resolves_revise_signature` covers partial/full omission and order reversal; `test_incomplete_local_requires_one_authored_site` covers refusal in both R1 `need(h)`/`seed(1,h)` orders, both branch arms, zero sites, indirect literals in alias/bound/conditional positions and disjoint same-name locals. Distinguish admission at a concrete direct relay (including a resolved lexical ProcRef consumer), unresolved readiness at a generic relay without grounding at that call, and existing scope-escape refusal when the complete consumer returns the local reference; outer-call expectations supply no evidence. Fully annotated counterparts pass in both orders; full signatures retain reuse/forwarding even with inferred captures.
- [x] Add same-site repeated arguments with compatible/conflicting expectations, repeated runtime activations, stuck readiness, incompatible body and source-location checks. Include identical-span/text occurrences; structural occurrence paths, not spans, object identities, generated copies or runtime activations, identify authored sites.
- [x] Validate cardinality across the consumer before checking it. At the eligible call, type ordinary/full arguments; group pending occurrences by local binding; unify all expected positions. Check each ready body once in its creator environment, infer/unify its return, and advance newly ready hooks until completion or located no-progress refusal.
- [x] Reuse generated definitions, existing unification/constraints, ProcRef binding and specialization; restore temporary state on exit/error. Ensure all locals are complete before closed construction; retain current effects and explicit constructor rules.
- [x] Collect the new module; run `pytest -q tests/test_workflow_lisp_local_hook_signatures.py`, then `pytest -q tests/test_workflow_lisp_procedures.py -k 'proc_ref or type_param'`. Require GREEN for new cases and unchanged baseline dispositions for legacy controls; inspect one-body-check evidence again only if the qualified mechanism changed.

Acceptance: C4 `recovery-20261010/task13-delivery/coordinator-acceptance.json` records independent HOLD→PASS, 78 signature cases, 40 retained controls and 51 legacy controls, plus located CLI escape refusals and valid result 2. Earlier lifecycle and raw evidence is reused for unchanged paths. Concrete nested and imported relay composition remains OPEN with paired full/inferred refusals; no universal ProcRef-return or imported scope-escape claim. Bounded Task14 compatibility and Task14A/14B are subsequently accepted; the closeout owns final F status.

## Task 14 — Select the graph helper and migrate representative consumers

**Role/artifacts:** Implementation / resolver, bundled source, consumers and public evidence; Revision / docs follows code review. Depends on Task 13 and unchanged owner migration decision.

**Files:** `compiler.py`, `modules.py`; create `orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc` if Task 4 validates that exact root; modify `workflows/examples/improve_experiment_proposal.orc`. Extend `tests/test_workflow_lisp_modules.py`, `tests/test_workflow_lisp_closed_program_frontend.py`, `tests/test_workflow_lisp_lsp_cli_parity.py`, `tests/workflow_evaluated_consumer_sources.py`, `tests/test_workflow_evaluated_consumers.py`, `tests/test_workflow_evaluated_phase6a_pilot.py`; reuse stdlib/recovery source owners identified in Task 0. Adjust that file list only with traced dependencies.

- [x] Preserve or reuse raw baseline artifacts and an accepted-correct interrupted 2.35 checkpoint from the unchanged baseline using existing public harnesses; record revision, fixed package/source/workspace paths, real pins and seed. Prepare old 2.33/2.34 flat imports, old 2.35 evaluated imports and type-only `Decision` controls for the delivery compatibility campaign, rather than duplicating it in Task 4.
- [x] RED first: add `test_w3_graph_selects_one_improve_api` across old/new entry and imported defining targets; test old-source five-argument migration diagnostic, valid older type-only/compatible imports, default roots, user-root ambiguity and actual selected root provenance.
- [x] Implement the qualified graph-wide builtin substitution at all public graph entries. Preserve legacy file/path, ambiguity rules and defining-module admission. Keep complete imported snapshots authoritative; extend snapshot tests for sole-old admission and differing canonical overlap refusal (`compiled_workflow_snapshot_conflict`), including deleted producer sources.
- [x] Add package-installed and real CLI/LSP parity checks for the alternate bundled file. No first-match override, stale parent root, alternate snapshot resolution or global old-snapshot rejection. Prove identical selected builtin source and source-root provenance through the real graph paths. Preserve legacy F2 checks. For evaluated targets, explicitly record the existing LSP `evaluated_execution_unavailable` after graph compilation: selected-source parity does not assert successful LSP snapshots, semantic navigation or terminal F2 parity. The pre-existing evaluated F2 discrepancy stays open and is not waived. Independent design review and coordinator disposition are recorded in C4 `recovery-20261010/task14-preparation/lsp-boundary-coordinator-disposition.json`; package/process proof remains required.
- [x] Remove only `I`, `(inputs I)` and hook forwarding from the selected helper; keep loop/results/inline/effect policy. Migrate proposal local hooks but preserve domain `ExperimentBrief`. Add a runnable reviewed-change helper specimen through the existing consumer source harness, removing context-only `ReviewContext`/constructor/forwarding while preserving `ReviewState`, reports and both final-round rejection guards. Historical census/spike files remain evidence.
- [x] Public RED/GREEN cases through existing harnesses: APPROVED/BLOCKED/EXHAUSTED, final candidate/feedback, bounded hook ordering/counts, report/artifact lineage, lexical shadow and two distinct capture environments in the same run. For two helper calls use distinct inferred locals or fully annotated reused locals, never a second site for one incomplete signature.
- [x] Exercise actual public compile/run/committed stop/resume/completed replay for proposal and reviewed-change with deterministic providers; assert requests/dataflow and no redispatch. Run `pytest -q tests/test_workflow_evaluated_consumers.py -k 'improve or reviewed_change'` plus added W3 pilot selectors; these are the orchestrator integration/smoke evidence, not a live research study.
- [x] At fixed package/source/workspace paths and seed compare raw old 2.33/2.34 flat and 2.35 evaluated artifacts; resume retained compatible old runs, including an interrupted 2.35 boundary, and verify completion replay. Separately report authentic changed-pin or migrated-source refusals with unchanged retained bytes; no pin substitution, digest rewriting or `--force-restart`. Safe refusal alone never satisfies successful old-run compatibility.
- [x] Collect all changed test modules, run the added resolver/snapshot/parity selectors and old stdlib outcome controls. Record source/module paths, pin inputs, exit codes and raw artifact hashes for independent review.
- [x] Measure callers/helper together with existing `experiments/orc_repetition_census/count_lines.py`; report actual deleted declarations/forwarding and a one-hook extra-capture edit. Counts support usefulness, not a percentage gate. Hand remaining caller inventory and explicit retargeting recipe to Phase 6b.

**Task14A bounded acceptance:** C4 `recovery-20261010/task14a-delivery/coordinator-acceptance.json` records independent PASS, 33 selected tests and 168 collected nodes. Graph, snapshot closed-build/readback and installed CLI/LSP source provenance are covered; no snapshot runtime result is claimed. Legacy F2 execution remains in F affected/full, and evaluated F2 remains OPEN_NOT_WAIVED. Subsequent bounded Task14B acceptance closes representative consumer/pilot/usefulness gates; compatibility03 has exact final-package raw/old-run acceptance, while the closeout owns final F status.

**Traced registry dependency for Task14B:** migrate the maintained proposal row to the `evaluated_execution` metadata label, with neither flat lowering field. Preserve common validation and the flat compile helper; bind the row to the maintained 2.36 source's public CLI artifact/lifecycle evidence. Add bounded registry tests and keep JSON/validator together. Design and independent PASS are accepted in C4 `recovery-20261010/evaluated-registry-migration-coordinator-disposition.json`. The reviewed Task F promotion reconciles the registry architecture, post-foundation design and `orchestrator/workflow_lisp/README.md`; no runtime/schema or F2 extension is implied.

**Task14B corrective prerequisite (F-CODE-1):** the real consumer failures trace to provider/prompt externs being included in lexical captures. C4 `recovery-20261010/w3-extern-capture-coordinator-disposition.json` accepts the independently reviewed correction to the existing W3 contract. Separate exact extern availability from effective lexical roots in `compiler_session.py`, `expressions.py`, `workflows.py` and `procedure_typecheck.py`; preserve full/pending local body typing, generated-local retyping precedence, run-ref reentry and session restoration. Keep generated signatures capture/parameter-only and leave older targets and closed capture guards unchanged. Add the design's narrow RED/GREEN structural, shadowing and restoration checks, collect changed modules, then require both real public consumers before resuming remaining Task14 gates. Unexpected product-owner expansion returns to Design. Final old-artifact/resume compatibility runs only after the corrected compiler freezes; no prior Task14A or prototype result substitutes for this proof.

**F-CODE-1 acceptance:** C4 `recovery-20261010/w3-extern-capture-delivery/coordinator-acceptance.json` accepts the four-owner extern/lexical distinction and nine real public compile/run/committed stop/resume/replay cases. Declared externs are available in hook bodies without becoming captures; real lexical Provider/Prompt aliases remain eligible under existing admission. No runtime capability transport or closed/schema expansion is implied.

**Task14B bounded acceptance:** C4 `recovery-20261010/task14b-delivery/coordinator-acceptance.json` accepts four additional capture pilots, nine reused public cases, six corrected corpus selectors, documented dry-run without launcher bytes and 223 collected nodes. The initial connected launch remains 122 PASS / 1 FAIL; corrected selectors do not relabel it GREEN. The unique helper-plus-two-callers census is 232 → 220 code lines, without a percentage/performance gate. The 30-row source inventory and explicit retargeting recipe hand off only the W3 slice to Phase 6b. Four temporary pilot workspaces were cleaned by pytest; their commands/logs/assertions remain, while nine public consumer workspaces are archived. Subsequent bounded compatibility03 acceptance and its exact final-package controls are recorded in the closeout; the closeout owns final F status.

**Task F documentation preparation:** C4 `recovery-20261010/task-f-docs-promotion.json` records the independently reviewed 22-owner promotion. The final status/routing cut and closeout are prepared for distinct Astra review; the closeout records executable verification acceptance and owns the remaining gates.

Task F's authoritative qualification and delivery state is the [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md). Earlier accepted increments remain bounded evidence; later compiler changes require the recorded package-bound refresh. Task12/13 composition OPENs and evaluated F2 **OPEN_NOT_WAIVED** remain independent of W3 qualification.

## Task F — Review, phase freeze and bounded closeout

**Role/artifacts:** Independent code/evidence and design/spec reviewers, then coordinator integration. Depends on Tasks 4/6/11–14 and correction evidence; no Phase 5 start implied.

- [x] Review full diff against accepted brief and owner decision. Require the complete Tasks 11–14 structural/refusal, capture/canonicalization, single-site/adversarial inference and module/import/snapshot/package/LSP/old-run matrices before closeout; Task 4 PASS replaces none of them. Challenge old source paths, both key/DId walkers, site cardinality, one body check, actual compatible resume versus refusal, true pins and snapshot authority. Return accepted code findings to implementer; rerun only relevant invalidated evidence.
- [x] After narrow GREEN checks, run affected suites in tmux with `pytest -q -n 16 --dist=worksteal` and the exact changed/new modules plus `tests/test_workflow_lisp_procedures.py`, `tests/test_workflow_lisp_closed_program_names.py`, `tests/test_workflow_lisp_closed_program_build.py`, `tests/test_workflow_lisp_improve_stdlib.py`, `tests/test_workflow_evaluated_recovery.py`, `tests/test_workflow_evaluated_recovery_branches.py`, and the pure-correction affected set. Record the expanded selector list; do not run these concurrently with other campaigns.
- [x] Freeze code after required corrections. Run **one full campaign**, alone in tmux: `pytest -q -n 16 --dist=worksteal`. Retain log/XML or equivalent node-level outcomes, revision and exit. Link this result to the pure correction; no separate full campaign for each component. Repeat only for relevant later changes/failures or unresolved concerns.
- [x] Preserve baseline RED facts: C6 final campaign has 425 failures with causal disposition SHA-256 `32b5d1dccb30aee4d01571749fc59ca3b440f1bed4f2fd8c7cce736380533437`; Phase 3 had 402. Reuse valid per-failure evidence, but investigate newly observed or changed outcomes against delivered baseline. Never infer causality solely from matching IDs or report adjusted GREEN.
- [x] Revision / documentation updates `docs/design/workflow_lisp_write_once.md`, `docs/design/workflow_lisp_let_proc_local_proc_refs.md`, `docs/design/workflow_lisp_composition_first.md`, `docs/lisp_workflow_drafting_guide.md`, capability/design/index routing and the component/parent plans together to reflect demonstrated support and remaining migration. Preserve the target-local capture rule and single-site limit. Publish no capability that lacks public evidence. Reconcile the observed evaluated-target LSP limitation in LSP setup/baseline/capability routing while preserving F2 as the intended contract; record its unresolved discrepancy separately from W3 selected-source parity.
- [x] Create `docs/reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md` with before/after usefulness, commands/exits, exact artifact/review hashes, authentic-pin and resume limits, full RED disposition and Phase 6b handoff. Coordinator inspects final diff/evidence itself; record integration only when actually performed.
