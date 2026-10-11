# Workflow Lisp pure lexical capture correction plan

> Recovery, 2026-10-10: this document was restored from persistent source
> copies and recorded literal edits after the original `/tmp` product,
> qualification, raw-artifact and checkpoint directories disappeared. Results,
> checked tasks and acceptance hashes below describe the historical cut;
> they are not fresh verification of the recovered sources. Current recovery
> and required checks are governed by the [recovery plan](2026-10-10-phase4c-recovery-plan.md).
> W3 remains selected at 2.36 with one `std/improve` API per source import graph,
> after the bounded pure correction and before Phase 5; the
> [Phase 4c closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md)
> owns current qualification and delivery.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. The coordinator assigns implementation, independent review and the sole execution window; do not commit without its instruction.

**Goal:** Correct the pure `bind-proc` creation-scope error on every accepting target and the coupled generated repetition of captured effect results demonstrated at 2.30/2.33. Preserve raw artifacts and compatible retained runs of accepted-correct programs, subject only to the exact latent typed-representation exception below. The materially amended gate explicitly permits causal executable/identity/checkpoint deltas of the demonstrated incorrect duplicate-effect shape, even without authored shadow.

**Architecture:** Retain creation identity and type on free captured `NameExpr` leaves, transport it through existing bound-expression carriers, and resolve it only at an actual consuming expansion. Older flat lowering uses a separate transient identity scope and invocation-private locals; 2.30+ normalization selectively uses existing capture rows. The rejected early source-renaming prepass is not part of this correction.

**Tech stack:** Existing Python compiler, immutable expression nodes, pytest and public `python -m orchestrator` CLI.

**Historical status at interruption:** Task 1 scratch feasibility accepted and Task 2 authorized in C4 `pure-capture-task1-acceptance.json`; the eleven-owner product correction and maintained test updates are applied **uncommitted**. Bounded public compatibility and affected-check evidence is recorded in the [correction report](../reports/2026-10-07-workflow-lisp-pure-capture-correction.md). Final code/evidence and independent spec/documentation reviews passed; the coordinator accepted this bounded prerequisite in the original worktree before interruption via C4 `pure-capture-prerequisite-acceptance.json` (SHA-256 `3050538cc8da06a4e749d76a31c84c30bfcb1a6947e20f1b8dc9ae75d415950f`). Tasks 1–4 are bounded-complete except the shared future Phase 4c freeze/full campaign. Integration to `main`, commit/merge and phase closeout remain pending. The original provenance contract remains C4 `pure-capture-task1-provenance-amendment.md`, SHA-256 `87c614d20c2ebca8009a5bb6bbfd77d2c0e9f58ec493ffcbb439d12d4a78dbf5`, with the material amendments below. No new target, grammar, W3 inference, stdlib API or runtime representation is delivered.

**Recovered bounded status, 2026-10-11:** C4 `recovery-20261010/pure-prerequisite-revalidation.json` accepts fresh source-bound checks: 132 collected, 8 narrow PASS and 130 PASS / 2 XFAIL across the two complete modules; fresh public pure evidence includes the exact 2.30 latent-typed exception with both complete 15-file inventories, lexical 8, committed stop 75 → resume 0 → result 42 and unchanged effect counts 1/1. This renews only the bounded prerequisite, not universal compatibility. Its original failed preliminary progress witness remains failed. W3 Tasks 4/6/11–13 and bounded 14A/14B/F-CODE-1 now have separate acceptance. The shared final Phase 4c verification, original RED outcomes, bounded causal dispositions, compatibility and delivery are owned by the [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md). Historical task checks and lost evidence below retain their original scope.

## Authorities and evidence

Start with `docs/index.md`, `docs/capability_status_matrix.md` and `docs/design/README.md`. Governing contracts are `specs/versioning.md`, “Exceptions to target stability (every target)”; `docs/design/workflow_lisp_proc_refs_partial_application.md`, specialization/lowering; and `docs/design/workflow_lisp_core_calculus_middle_end.md` §9. Silent wrong lexical values are corrected at every accepting target. Unrelated refusals stay refused. Accepted-correct programs retain raw/resume gates; the explicit amendments below distinguish latent typed representation from the demonstrated incorrect duplicate-effect shape.

Baseline is `a4666341` in `/tmp/orc-phase4c-w3-20261007`. Physical control directory **C4** is `/home/ollie/Documents/agent-orchestration/.superpowers/sdd/2026-10-07-evaluated-execution-phase-4c-w3-plan`; **C6** is its sibling `2026-10-07-evaluated-execution-phase-6a-pilot-plan`.

- C4 `pure-capture-investigation.md` (SHA-256 `8d4f895609b56c725f6a375bf7e304d67238c246e1d734048a9a69a2263ef979`) records public baseline values 8/current and 101/shadow at 2.14, 2.29, 2.30 and 2.35. The 2.14 witness returns an equivalent record; its scalar-root refusal is a required admission control, not bug evidence.
- C6 `bound-capture-design-review.md` and `bound-capture-investigation/consumer-experiment-report.md` demonstrate why universal freezing is rejected. The integrated selective effectful correction, including its historical local-only static-row consumer, remains a compatibility control.
- `tests/test_workflow_lisp_use_site_scope.py::test_a_bound_value_keeps_its_scope_across_a_later_binder` was the original strict xfail for this defect; its removal supplied the retained RED. Reuse that maintained harness.

## Material amendment to the raw compatibility gate

The coordinator's 2026-10-07 decision, accepted by Design (`design_capture_independent`), revises the plan's stronger requirement of total raw equality for every accepted-correct entry. This is a **material gate revision**, not an editorial clarification or a retroactive PASS. The original FAIL, complete raw diff and evidence remain retained. That scratch gate was subsequently qualified and Task 2 authorized; original failures and the amended adjudication remain separate in the evidence below.

The factual source is C4 `pure-capture-typed-artifact-authority-review.md`, SHA-256 `e48644553f239c471cc80a4adbd4a8bf0fdeec78f368dd48f11b8228786c0ed3`; that review itself grants no waiver or approval. Its exact retained pair is `pure-capture-provenance-continuation/attempt6/pre-materialized-adapted/{baseline,candidate}/2_30-literal-pre-materialized-resolved-hook/`, with the complete change in `pre-materialized-adapted/typed-ast.diff`. The prior plan, SHA-256 `0d6e89458445aae9181a91165d00964ecf71fb30d3ecec2d91aa404835621e46`, is preserved as C4 `pure-capture-fix-plan-before-typed-artifact-gate-amendment-20261008T025039147857Z.md`.

`specs/versioning.md`, “Exceptions to target stability (every target)”, guarantees byte identity for programs without such a shadowed name. This fixture's literal-true entry returns 42, but an independently normalized helper specialization contains the latent 101-versus-lexical-8 defect outside that entry's executable path. The typed dump exposes real compiler decisions (frontend specification §76 and the producer/consumer trace in the factual review); hiding its correction would misrepresent the typed program. No normative contract is changed by this amendment.

Allow this exception only after demonstrating **all** of the following:

- Compare and hash every raw file recursively, including every build artifact and `typed_frontend_ast.json`; retain the complete inventory and diff. The sole permissible build-file difference is localized typed representation of this independently normalized, latently defective specialization (`%proc-ref-call.tiny.pre_materialized.d199b0ad52af` in the retained pair), including only the capture row and directly consequent generated references. Do not globally exclude the typed AST, canonicalize differences or normalize package pins.
- Trace the specialization outside the selected entry's executable path and demonstrate its live counterpart returns lexical 8, with the baseline wrong-value evidence retained. This does not authorize general liveness analysis or DCE.
- Require unchanged selected-entry outputs, admission and diagnostic outcomes, and byte equality for every other build file, executable representation, semantic/selected-entry identity and checkpoint artifact. The retained pair has 14 identical other build files; any other build delta fails this exception. Manifest or fingerprint equality alone is insufficient.
- Preserve authentic `compiler_runtime_identity` pin/digest deltas in CLI stdout and report them separately, along with all other non-build file differences. They do not establish whole-directory raw equality or license unrelated diagnostic changes.
- Demonstrate compatible public resume of a baseline accepted-correct **target-2.30 flat run** carrying this latent-specialization shape from a real committed command/provider boundary, with no redispatch. The general target-2.35 resume gate does not substitute for this target-2.30 evidence: its closed representation differs. A clean run returning 42, a zero-effect run or inspection of resume consumers does not satisfy this requirement.

No-shadow, ignored/unused/unchosen controls without the latent shadow retain total raw equality; all accepted-correct executable artifacts retain it even when this exception applies. Any unclassified delta or unmet condition fails the amended gate and returns to Design before product edits.

## Material amendment for generated duplicate effects and legacy refusal

Coordinator/Design explicitly accept the consequence coupled to the same
`capture_source` consumer, as recorded in
`/tmp/orc-pure-capture-feasibility-20261007/effect-once-design-disposition.md`
(SHA-256 `f89e7f72d38330460fd191bbde296cc60f217a69599cceed8ff6f97011ab1a62`).
This changes the former normative no-shadow gate: the demonstrated 2.30/2.33
source returns 1 on both compilers, but baseline executes its single authored
`tick` twice and product once. Each retained pair has 12 real build-file deltas
out of 15. These are causal executable, semantic identity and checkpoint
changes, not raw equality and not the latent typed-only exception. The original
FAIL and complete diffs remain retained; no retroactive PASS or normalization.
The exact shape/evidence and bounded envelope are in the correction report.

Only this demonstrated incorrect duplication and its causal artifact changes
leave the no-shadow raw gate. All accepted-correct raw/resume requirements,
all conditions of the earlier typed-only exception, truthful pins and unrelated
refusals remain intact. Remove the strict xfail only for
`test_a_captured_effect_result_runs_once` at 2.30/2.33, preserving its existing
value/count assertions. The live-provider-member xfail remains. No additional
compiler/runtime fix, effect policy or target is authorized by this amendment.

The added incorrect **legacy effect-result** run is distinct from Task 3's
incorrect **shadow 2.35** run. Its retained 2.30 checkpoint, stopped after the
first committed tick, resumes with exit 1 / `lexical_restore_invalid`,
`lexical_default_resume_invalid_checkpoint` and
`lexical_restore_semantic_digest_mismatch`, `FAIL_CLOSED`, before further effects.
Committed results/checkpoint records and tick-log bytes stay intact; only
`state.json`, `monitor_process.json`, `default_resume_report.json` and
`restore_report.json` change (failure/error/session and diagnostic observations).
This is neither compatible continuation nor a no-write `resume_program_changed`
preflight. The harness's original wrong expected exit remains a FAIL receipt.
Task 3's separate shadow-2.35 no-write guard and accepted-correct positive
resumes remain unchanged; no runtime modification is required.

## Causal proposal and exact owners

1. `typecheck_dispatch.py`, `LetStarExpr` owner: while the ordered binding and incoming environment are still present, ProcRef resolution retains the `BindProcExpr`'s source expressions. `source_binding_identity` is retained for simple-name bound arguments on the closed route; older-target ProcRef resolution uses the authored binding expression. Neither fact by itself supplies lexical lookup to all consumers.
2. `procedure_refs.resolve_proc_ref_value` copies each source expression into `BoundProcArg`. `procedure_specialization.bound_proc_ref_request` copies it, unchanged, into `specialization.value_bindings`. This mapping is a substitution recipe, not a captured environment. Adding identity to the mapping alone would not correct computed captures or old lowerers.
3. At targets below 2.30, `lowering/command_control_decisions.inline_procedure_bindings` overlays that recipe onto caller locals. WCC inline lowering (`wcc/defunctionalize.py`) protects names against the *callee's* binders, but the defining caller may already have rebound a free name. At 2.30+, `functions.normalize_resolved_inline_procedure_calls` creates static argument bindings at the later call, so the same captured expression sees that later binder. Its version gate proves it is not the common root.
4. The rejected source prepass either missed demand (first attempt) or changed an accepted-correct ignored-forwarded artifact (second attempt). It cannot satisfy the compatibility boundary. The selected replacement preserves provenance at creation and consumes it only at actual expansion.

**Selected owners and contract:** `expressions.NameExpr` gains optional compile-only `capture_origin=(BindingIdentity, TypeRef)`, excluded from equality/hash/JSON/semantic identity and generic hygiene gathering/rewriting. The `BindProcExpr` typechecker and generated-local capture construction in `procedure_typecheck` stamp only free leaves using binder-aware `map_expr`; an existing origin is immutable. Existing `BoundProcArg.value_expr` and specialization value expressions carry it. LetStar's old-target resolution must retain the typed expression metadata. Actual selected bound arguments/call-site carriers override cached specialization origins, since metadata is deliberately absent from cache identity.

`lowering/context._LoweringContext` holds separate scoped maps for original compiled value/type by identity and visible identity by spelling, without adding identity keys to `local_values`. Seed root/parameter scopes from retained typed binding environments and extend after normal WccLet lowering; lexical descent and call frames isolate activations. At the old WCC actual inline consumer (`wcc/defunctionalize._lower_wcc_procedure_call`), conflicting free reads resolve their original scope value/type through fresh invocation-private dictionary entries. No WccLet/command is emitted; explicit arguments keep caller semantics. Audit the frontend `lowering/procedures` consumer before claiming all old routes.

At `functions.normalize_resolved_inline_procedure_calls` (2.30+), track lexical binding identities and use actual selected bound arguments. Only conflicting captured reads introduce existing capture-source rows carrying original identity/type. Computed captures retain their computation and receive rows per conflicting free leaf. Preserve the historical `local_capture_names` filter and no-shadow rows/names/shape. Extend existing typecheck/WCC capture-row plumbing to the flat scope where necessary; missing origins fail rather than silently reading a shadow.

The accepted final eleven-owner cut also includes `lowering/control_loops.py`
for identity/type carriage across actual loop activations, following its dynamic-
iteration RED and independent review. Exact source hashes and the retained
feasibility/review scope are linked from the correction report.

Required guard variants remain: no collision; direct/named/alias invocation; actually applied and ignored forwarded hooks; unused/unchosen/branch-local hooks; match/loop scopes; generated local procedures; procedure-created captures; repeated activations; equal-value distinct bindings and same-expression captures sharing one specialization. No general interprocedural liveness, global registry, unconditional aliases or new runtime representation is authorized. Stop for Design if these selected owners cannot meet a guard.

**What this approach makes harder:** provenance must survive cloning/fixed points without entering semantic identity, scope values must remain available across lexical descent, and repeated calls must not reuse the wrong activation. Explicit metadata/idempotence, raw compatibility and call-site authority checks qualify these obligations.

## Task 1 — RED and bounded feasibility

**Role/artifacts:** Implementation; regression and disposable feasibility evidence. Product edits are forbidden until the coordinator reviews the feasibility result.

**Files:** existing `tests/test_workflow_lisp_use_site_scope.py`; scratch files only in the fixed disposable package, with separate C4 provenance evidence; preserve both rejected candidate seals.

- [x] Obtain the sole execution window. Preserve Luna's immutable baseline evidence; record revision, interpreter, package/source/workspace paths and `PYTHONHASHSEED=0` for every comparison.
- [x] Remove only the strict xfail on `test_a_bound_value_keeps_its_scope_across_a_later_binder`; run `pytest --collect-only -q tests/test_workflow_lisp_use_site_scope.py`, then `pytest -q tests/test_workflow_lisp_use_site_scope.py::test_a_bound_value_keeps_its_scope_across_a_later_binder`. Require genuine wrong-result failures, not import/admission errors. The initial RED retained the independent xfails; the later material amendment permits removing only the demonstrated effect-result xfail. Preserve the live-member xfail.
- [x] In a disposable package at fixed paths, prototype only the selected provenance contract above. Trace definition → BoundProcArg → specialization → actual old/new consumer, recording origin identity/type and scoped original value. No rejected prepass is retained.
- [x] First replay 2.14 record and 2.35 current/shadow pairs: require lexical 8 and current raw equality. Immediately require ignored-forwarded 42 and raw equality at both targets, subject only to the fully qualified typed-representation exception above, then qualify literal/input/computed captures (9), explicit caller argument (107), and different-type shadow. Preserve unrelated 2.14 scalar refusal. Stop at any failed early semantic/raw guard; remaining target/family variants still gate production.
- [x] Compare and hash all raw compiled outputs/manifests for current/no-shadow, unused/unchosen-hook, ignored-forwarded-hook and existing effectful/local controls against the identical-path baseline. Require total raw equality for accepted-correct controls except the exact latent-specialization exception, which preserves executable/all other build bytes. Classify the separately demonstrated incorrect duplicate-effect shape only under its material amendment; retain all twelve causal diffs. Preserve the original failed comparison and full diff alongside any new adjudication; no retroactive PASS. Actual-use consumption must leave unshadowed ignored hooks untouched without interprocedural liveness. A failed guard returns to Design before product edits. Keep all files and hashes; no normalization of semantic identity or package pins.
- [x] Before invoking the exception at Task 1, qualify public resume of a target-2.30 flat baseline run carrying this latent-specialization shape from a real committed command/provider boundary in the disposable baseline/candidate package. Retain commands, exits, terminal value and effect counts proving no redispatch; target-2.35 evidence cannot substitute. Task 3 still requires final-compiler target-2.30 compatibility for this exception; reuse scratch evidence only where unchanged and valid.
- [x] Execute an assert-based scratch check repeating typing/normalization on the same representative nested AST: require stable second-pass output and explicitly compare origin identity/type, binder identity/capture rows and the retained condition owner (those fields are excluded from ordinary dataclass equality). Trace actual invocation/pass counts through a representative nested compilation and its typechecking fixed point; record the commands, counts and AST comparison result. This is qualification of the shared invocation seam before Task 2, not a new benchmark framework. Restamped origin, repeated-pass changes or unbounded/redundant nested reapplication fail the feasibility gate. Verify origin exclusion from hygiene/serialization and call-site authority when equal expressions share a specialization.
- [x] Deliver a compact feasibility result with exact invocation and production diff proposal. Coordinator and independent reviewer either approve Task 2 or return the unresolved demand/owner choice to Design. No unreviewed downstream patches or unconditional aliases; the reviewed two existing consumers implement the one provenance contract.

## Task 2 — Implement the reviewed shared correction

**Role/artifacts:** Implementation; compiler code and minimal behavioral regressions.

**Files:** only the reviewed provenance owners above: expressions/typecheck/generated capture creation, functions normalization, lowering context and actual WCC consumer, plus demonstrated clone/hygiene/capture-row plumbing. Additional owners require concrete trace and Design review. Tests stay in `tests/test_workflow_lisp_use_site_scope.py` and the existing pure-call/public CLI modules when their harness is necessary.

- [x] Apply the approved smallest correction after RED. Keep the existing effectful retention machinery, local-only `functions.py` static capture rows, shape/independent-body guards, canonical digest and resume preflight unchanged.
- [x] Add only the guard cases not already exercised by maintained tests, parametrized through existing helpers. Assert values, dynamic command/provider inputs, effect counts and admission diagnostics; do not assert binder spelling or prompt text.
- [x] Run `pytest --collect-only -q` on every changed test module, then its new/changed selectors and the existing pure-bound-capture selector. Require GREEN and record the exact output.
- [x] Inspect the diff for duplicate capture storage, global shadow scans, per-target symptom patches and unrelated refactors. Stop and report if the qualified provenance contract no longer suffices.

## Task 3 — Public compatibility and committed resume

**Role/artifacts:** Implementation/evidence; public CLI replay and raw artifact manifest.

**Evidence:** `/tmp/orc-pure-capture-feasibility-20261007/continuation/attempt22-final-proof/`,
final committed-resume siblings and product/effect-once receipts linked from the
correction report; reuse `tests/test_workflow_evaluated_phase6a_pilot.py` and `tests/test_workflow_evaluated_public_context.py` harnesses.

- [x] At identical package/source/workspace paths and seed, compare and hash every baseline/final raw file, including all build files, for no-shadow pure current, literal capture, repeated binder, equal-value distinct binders, forwarded/local/computed capture and unused/unchosen-hook controls. Preserve full diffs and classify only the bounded typed-representation exception above; no-shadow controls and every accepted-correct executable/identity/checkpoint artifact retain byte equality. Report authentic `compiler_runtime_identity` stdout pin/digest deltas and other non-build differences separately; never strip them or claim whole-directory equality. Shadow wrong-value artifacts may change only with demonstrated corrected dataflow. The separately classified incorrect duplicate-effect shape may change only its demonstrated causal artifacts under the second amendment.
- [x] Preserve one baseline accepted-correct target-2.35 run stopped at an actual committed command/provider boundary, containing the pure bound helper. Resume that same run with the final compiler; require exit 0, correct terminal value and no redispatch of the first effect. Replay completion and compare retained run bytes. A zero-effect pure run alone cannot establish this gate.
- [x] For the typed-representation exception, also resume a baseline accepted-correct target-2.30 flat run carrying the latent-specialization shape from a real committed command/provider boundary with the final compiler. Require exit 0, the correct terminal value, no redispatch of the committed effect and unchanged retained run bytes on completion replay. The target-2.35 control, a clean 42 result, a zero-effect run or resume-source inspection cannot substitute for this target-2.30 check.
- [x] Require a baseline accepted-incorrect shadow run to refuse safely if its rebuilt identity changes, leaving retained bytes unchanged. Do not use `--force-restart` or bypass digest checks.
- [x] Record the additional incorrect 2.30 effect-result checkpoint's existing legacy FAIL_CLOSED refusal under the material amendment: no redispatch and committed/checkpoint bytes preserved, with the four diagnostic/state-file writes explicitly retained. This does not replace the preceding shadow guard or either positive compatibility check.
- [x] Run the public 2.14 record, 2.30 and 2.35 lexical-shadow/no-shadow pairs. Reuse unchanged fresh baseline results rather than rerunning them unnecessarily. Preserve the old-target scalar-root refusal.

## Task 4 — Independent review and final affected checks

**Role/artifacts:** Distinct Review / code-evidence, plus Review / specs when the status text changes. The coordinator integrates findings; return code corrections to the implementer.

- [x] Review the complete diff and raw evidence against this plan and `specs/versioning.md`. Verify every condition of the material gate amendment independently, including the localized typed specialization, live lexical-8 counterpart, full raw inventories/diffs, unchanged other build bytes and authentic committed resume with no redispatch; preserve the original FAIL and distinguish any amended adjudication. Specifically challenge unused/dead/ignored-forwarded controls, binding metadata, generated local captures, imported older modules, fixed-point idempotence and new refusal behavior. A global typed-AST exclusion or unclassified additional build delta fails; the separate demonstrated incorrect duplicate-effect deltas require their explicit material disposition and do not broaden the typed-only exception.
- [x] Run the maintained scope selectors and affected checks, covering `tests/test_workflow_lisp_pure_call_composition.py`, public context capture and Phase 6a pilot bound-review/resume through the narrow/family receipts. Reuse valid Task 2/3 evidence; exact campaign membership and exits are recorded in the correction report.
- [x] In tmux, run the final affected family using `pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_use_site_scope.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_pure_call_composition.py tests/test_workflow_lisp_command_captures.py tests/test_workflow_lisp_closed_program_elaboration.py tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_public_context.py tests/test_workflow_evaluated_phase6a_pilot.py`. Preserve exits and failure dispositions; expand only for relevant failures or gaps. Public CLI work in Task 3 supplies the mandatory orchestrator/integration smoke. The retained campaign is RED (6 failed, 454 passed, 2 xfailed); independent differential review identifies one pre-existing golden and five obsolete bug expectations. Only affected expectations were updated, then 132 collected / 8 selected PASS / two complete modules 130 PASS, 2 XFAIL. The eight-module campaign was not rerun or relabeled GREEN.
- [x] Run the complete suite once at the final Phase 4c freeze, after narrow and affected checks, using `pytest -q -n 16 --dist=worksteal` in tmux. This prerequisite correction does not launch its own separate full campaign. Link the phase-wide result and failure dispositions into this correction's closeout; repeat only for relevant subsequent changes, failures or unresolved concerns.

## Task 5 — Closeout and W3 handoff

**Role/artifacts:** Revision / documentation and coordinator integration.

- [x] Update the known-defect status in `specs/versioning.md`, `docs/capability_status_matrix.md`, `docs/index.md` and the Phase 6a pilot report only to the extent demonstrated. Keep historical 101 evidence explicitly historical; do not claim all local/effect capture defects are fixed. Remove only the corrected known-defect clause, preserving unrelated limitations.
- [x] Record final revision, exact commands/exits, raw evidence hashes, legitimate wrong-value identity changes, accepted-correct resume result, independent reviews and remaining limitations in a bounded closeout report linked from this plan.
- [x] Coordinator inspected the final diff/evidence and accepted the bounded prerequisite in the original worktree before interruption via C4 `pure-capture-prerequisite-acceptance.json`; final code review `E/pure-capture-final-code-review.md` and independent spec review `E/pure-capture-amendment-independent-review.md` are PASS (E is the correction report's evidence root). This records original-worktree acceptance only; the correction report owns recovery verification; the Phase 4c closeout owns the shared full-freeze and delivery fields. W3 qualification/delivery remain separately governed.
