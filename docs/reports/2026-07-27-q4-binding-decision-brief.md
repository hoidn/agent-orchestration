# Q4 Panel-Consumer Binding Decision Brief

- **Status:** investigation brief with one recommended default binding, produced 2026-07-27 to frontload the Q4 entry-condition decision of the active Q/L roadmap. Owner countersign happens at the future `docs/design/workflow_lisp_judgment_views.md` design review; the default below names the evidence that reopens it. All anchors were read on this checkout on 2026-07-27; a concurrent session is editing the repo, so re-pin lines at countersign.
- **Consumes:** `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md` (Q4 row + stage section), `docs/design/workflow_lisp_prompt_calculus.md`, `docs/design/workflow_lisp_prompt_identity_diagnostics.md`, `docs/design/workflow_lisp_pure_list_traversal.md`, the `workflows/` inventory, `docs/capability_status_matrix.md`, and `docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md`.
- **Not frontloaded here:** Q5 phased delivery (its own ordered reviews are in flight and Q5 has no Q4 dependency — roadmap:99), M-track content, any spec edit, and the judgment-value/view field design itself (that is the Q4 design act, not this binding).

## 1. What The Decision Is

The Q4 stage row, verbatim (`docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md:79`):

> | Q4 | Judgment views | Q3 complete; a concrete generic-reviewer/panel consumer is bound | result-plus-provenance inspection value and deterministic views over the existing evidence authority; no new outcome union or report authority | blocked by Q3 completion |

The entry condition has two halves. "Q3 complete" is not decidable here: Q3's design is accepted (`9b2aa7ac`, review snapshot `fdf16f362f93eae89c05600e6954a118270fe7b7`) and its implementation plan is accepted at `ad5474c7`, but implementation "is next, has not started, and remains the prerequisite for Q4" (roadmap:232-233). The half that can be frontloaded is **which concrete workflow is bound as the generic-reviewer panel consumer** — the consumer the not-yet-created authority target `docs/design/workflow_lisp_judgment_views.md` (roadmap:252-253; confirmed absent by glob 2026-07-27) must design its transport and view contract against.

The roadmap pins the consumer's substrate (roadmap:260-264): "The first consumer is a generic-reviewer panel over the already implemented bounded `list/map-effect` surface. This stage may use lists of judgment inspection values only if their transport and view contract is accepted in the Q4 design; it may not add runtime prompt references or higher-order mapping."

What the stage delivers once bound (roadmap:255-258): an inspection-layer judgment value over stable Q3 attempt identity, where "the semantic authority remains the provider result plus existing attempt evidence" and matrices, disagreement tables, and iteration series "are deterministic views and are never parsed back into workflow state."

Derived consumer contract a binding must satisfy:

- **Per-lens calls must be fragment-backed.** A `defprompt` application is legal only in `provider-result :prompt` position at target ≥2.20 (`workflow_lisp_prompt_calculus.md:49-52`), and Q3 attempt identity applies "only to the direct fragment-backed `provider-result` surface" — live-supervision and peer-group forms are explicitly not Q3 consumers (`workflow_lisp_prompt_identity_diagnostics.md:37-40`). A consumer using extern prompts yields a result with **no provenance to inspect**, failing the gate's "result-plus-provenance" wording.
- **Fan-out shape.** Ordered lens list as workflow input data, bounded `list/map-effect` with a literal `:max`, body exactly one effectful call (nested loops/map-effect/live-provider forms and effectful composition are rejected with `list_map_effect_body_unsupported`; "later widening requires a demonstrated consumer" — `workflow_lisp_pure_list_traversal.md:229-243`), then a synthesis call consuming the ordered result list — the design's own motivating consumer (`workflow_lisp_pure_list_traversal.md:11-17`).
- **Provenance component.** Q3 publishes five closed identity roles plus final-prompt and composition digests as "provenance and diagnostic evidence only" on the existing report surface (`workflow_lisp_prompt_identity_diagnostics.md:14-35`); "Q4 may consume validated provenance through its separately reviewed inspection design, but Q3 does not pre-design a judgment value" (:898-900).

## 2. Options

### A — Panel variant of the generic-reviewer family (`review_revise_design_docs`)

**Description.** Bind the consumer as a panel-shaped sibling entry in `workflows/examples/review_revise_design_docs.orc`: keep the `review-design-doc` fragment with its five preserved fills and prompt-owned `-> ReviewDecision` plus `:path :out` report slot (orc:73-81; preservation table `workflow_lisp_prompt_calculus.md:196-210`), lift the single `review_focus String` (orc:47, orc:127) to an ordered lens list, fan the fragment application out via `list/map-effect`, add one synthesis call. The existing single-reviewer `review-revise-loop` entry (orc:152-159, `:max 20`) stays untouched; revise-after-panel stays outside the fan-out (map-effect body restriction).

**Evidence it is real/used.** This family *is* the roadmap's named generic-reviewer: "Q1's required real consumer is the generic-reviewer pattern" (roadmap:196-198); "Q1 and Q2 are implemented through the real `review-design-docs` consumer" (`docs/design/README.md`, prompt-calculus row); Q1 real-consumer migration commit `0ab25825` and Q2 implementation through `d0bb9a1d` (`docs/capability_status_matrix.md:41-42`); live launch evidence run `20260608T225644Z-pcxb4n` (`docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md:5-6`); catalog row naming it the "preferred fresh real-life-tested review/fix" example (`docs/capability_status_matrix.md:76`). DSL target `2.21` (orc:3) — already on the prompt-calculus surface.

**Cost/risk.** Requires the one unproven composition (fragment application inside a map-effect body — no fixture today, §5.1); a new exported workflow + prompt/extern bindings + example tests. Low blast radius: additive sibling in a file with no parity-baseline pins.

### B — Promote the maintained 2.18 panel fixture

**Description.** Bind `tests/fixtures/workflow_lisp/valid/list_map_effect_runtime_cardinality_provider.orc` (:20-33: `lens_ids` fan-out `:max 4`, per-lens `ReviewReport`, `PanelResult` reports+synthesis) — already exactly the panel shape — promoting it (or a copy under `workflows/`) to fragment applications.

**Evidence.** It is the maintained target-2.18 consumer with exactly three focused tests including two deterministic-provider E2Es (`workflow_lisp_pure_list_traversal.md:389-393`; `tests/test_workflow_lisp_list_traversal.py:83-88`).

**Cost/risk.** The capability matrix itself rules "the runtime fixture is a harness, not a standalone prompt-transport template" (`docs/capability_status_matrix.md:65`). It uses extern `prompts.review` (fixture:23), so as-is it carries no Q1 fragment identity and would produce a judgment value with result but no provenance — failing both the "generic-reviewer" half of the entry condition and the completion gate's "result-plus-provenance". Promoting it mints a new consumer with zero usage history — the weakest reading of "concrete".

### C — `review_revise_parametric_design_docs.orc`

**Description.** Adapt the historical one-off (three fixed docs, one combined review).

**Evidence.** Target `2.14` (orc:3); module-local duplicates of `RunCtx`/`PhaseCtx`/`ReviewDecision`/`BlockerClass` (orc:45-53); fixed-arity `ParametricDesignDocs` record (orc:57-60); registry-flagged `stale_needs_update` (`docs/plans/2026-07-05-post-foundation-target-completion-plan.md:443-445`); the plan that created Option A's family says "Do not mutate `review_revise_parametric_design_docs.orc`" and treats it as the superseded predecessor (`docs/plans/2026-06-08-generic-design-docs-orc-review-workflow.md:37-38,74-75`).

**Cost/risk.** Effectively a rewrite (target bump 2.14→≥2.20, de-duplication, defprompt migration, then the same panel work as A) with none of A's Q1/Q2 identity history. Dominated by A.

### D — `design_plan_impl_review_stack_v2_call.orc` stack family

**Description.** Bind Q4 to the design→plan→impl stack's review gates.

**Evidence.** Real and heavily exercised — procedure-first pilot source (`tracked-plan-phase` migrated at `e6a85cb7`, `docs/plans/2026-07-13-procedure-first-reuse-inventory.md:120-124`; public entry retained, :88-89), but target `2.14` (orc:3) with single sequential review gates, not a multi-lens panel; and it is a frozen pilot/baseline surface — the identity-compatibility plan forbids editing it outside its own gates (`docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md:18`).

**Cost/risk.** High blast radius on procedure-first parity baselines; shape mismatch with the panel gate.

### E — Production drains (`verified_iteration_drain`, `lisp_frontend_design_delta`)

**Description.** Bind Q4 into a production drain's review step.

**Evidence.** The verified drain's design is explicitly anti-panel: "P3 — Judgment is fused. One provider session per iteration owns select → plan → implement → self-verify. No judgment handoffs mid-decision" (`docs/design/verified_iteration_drain.md:32-34`). The design-delta family is target `2.14` across modules (e.g., `drain.orc:3`) with its own selector/review prompt stack.

**Cost/risk.** Contradicts the owning design's stated principles (verified drain) or drags a large 2.14 production family through a target bump mid-Q3; either couples a language-stage gate to production drain stability.

### F — `workflows/experiments/repository_task_pilot/task_loop.orc`

**Description.** The target-2.20 experiment loop with plan/impl review gates.

**Evidence.** orc:3 (`2.20`), but extern prompts (`providers.repository-task.*`) and a module-local `ReviewDecision` enum (orc:26-28); lives under `workflows/experiments/` in the exploratory lean-pilot lane (design README, Runtime And Observability Direction).

**Cost/risk.** Single-reviewer gates, no fragment applications despite 2.20; binding a roadmap stage gate to an explicitly exploratory surface inverts the experiment platform's own authority ordering.

### G — Peer-group / live-supervision panel (rejected substrate, recorded to close the branch)

**Evidence.** No workflow uses `with-live-provider-peers` (repo-wide grep of `workflows/`, zero matches, 2026-07-27); Q3 excludes live-supervision and peer-group forms from attempt identity (`workflow_lisp_prompt_identity_diagnostics.md:37-40`); the roadmap pins Q4's panel to `list/map-effect` (roadmap:260-261). Not a candidate under the gate's own wording.

## 3. Constraints From Accepted Q4 Design

The Q4 authority target does not exist yet (glob 2026-07-27: `docs/design/workflow_lisp_judgment_views.md` missing; roadmap:252-253 requires it created and independently accepted before the Q4 implementation plan). Until then the binding answers to the accepted adjacent authorities:

1. **Roadmap Q4 section** (roadmap:255-264): inspection value only after Q3 stable attempt identity; provider result + existing attempt evidence stay semantic authority; views deterministic, never parsed back into workflow state; judgment-value lists only if the Q4 design accepts their transport/view contract; no runtime prompt references; no higher-order mapping.
2. **Verbatim completion gate** (roadmap:79): "result-plus-provenance inspection value and deterministic views over the existing evidence authority; no new outcome union or report authority".
3. **Prompt calculus ownership** (`workflow_lisp_prompt_calculus.md:481-484`): "Q4 exclusively owns judgment inspection values and views"; Q3's acceptance "does not expose Q3 runtime behavior or pre-accept Q4" (:847-848); judgment values/lists/provenance views/reviewer matrices are explicitly outside Q1 (:470-471).
4. **Q3 substrate contract** (`workflow_lisp_prompt_identity_diagnostics.md:14-35, 898-900, 917`): five closed roles + digests are evidence only, on the existing report surface, "not a workflow value, result, checkpoint, resume guard, or search/fitness input"; Q4 judgment views are a named Q3 non-goal.
5. **map-effect contract** (`workflow_lisp_pure_list_traversal.md:229-243`): binder form, literal `:max`, closed body; widening only via a demonstrated consumer.
6. **Sequencing:** Q5 has no Q4 dependency (roadmap:99); the substrate track schedules M2 design beside Q4 after Q3, consuming the same Q3 identity (`docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md:224-226`) — the binding must not mint a second identity-consumer contract.
7. **Program-search boundary** (`docs/design/workflow_lisp_program_search_boundaries.md:59-62`): per-lens signals are diagnostic only, never selection or promotion authority — a Q4 disagreement table must not become a fitness function.

## 4. Recommended Default + Re-Entry Evidence

**Default: Option A.** Bind the Q4 generic-reviewer/panel consumer as a panel entry in the `review_revise_design_docs` family: the existing `review-design-doc` fragment (five preserved fills, prompt-owned `-> ReviewDecision`, `:path :out` report slot) fanned over an ordered lens list via `list/map-effect`, plus one synthesis call over the ordered report list — the pure-list-traversal motivating consumer (`workflow_lisp_pure_list_traversal.md:11-17`) realized on the roadmap's own named generic-reviewer (roadmap:196-198).

**Justification against the gate's own wording:**

- *"a concrete generic-reviewer/panel consumer"* — A is the only candidate that is simultaneously (i) the roadmap-named generic-reviewer (roadmap:196-198), (ii) fragment-backed at target 2.21 (orc:3, 73-81) so Q3 provenance will exist per attempt (`workflow_lisp_prompt_identity_diagnostics.md:37-40`), and (iii) real with live-run evidence (run `20260608T225644Z-pcxb4n`; commits `0ab25825`…`d0bb9a1d`, `docs/capability_status_matrix.md:41-42`). B has the panel substrate but is disqualified as the *bound consumer* by the capability matrix's harness ruling (:65) and extern prompts (result-only, no provenance). C is superseded by A's own creation plan; D is frozen and shape-mismatched; E contradicts its owning design; F is exploratory; G is excluded by the gate's substrate wording.
- *"result-plus-provenance … over the existing evidence authority; no new outcome union"* — A already returns `ReviewDecision` through the accepted prompt-owned `ReturnSpec` pipeline (`workflow_lisp_prompt_calculus.md:211-214`); the panel adds only list transport, exactly the item roadmap:261-263 conditions on the Q4 design's accepted view contract.

**Binding act.** Routing-only, consistent with "a roadmap status is routing, not capability evidence" (roadmap, Governing Bounds): record the `review_revise_design_docs` panel variant as the bound consumer in the Q4 entry-condition text at the Q3→Q4 gate edit, and have `workflow_lisp_judgment_views.md` name it as first consumer. No workflow edit is needed to *bind*; authoring the panel entry is Q4 implementation-plan work.

**Re-entry evidence — only the following reopens the default:**

1. **Composition seam fails.** A compile probe shows a `defprompt` application inside a `list/map-effect` body is rejected or drops fragment identity carriage (unproven today — the only map-effect fixture uses extern prompts, fixture:21-24). Then either the Q4 design carries the widening under the demonstrated-consumer rule (`workflow_lisp_pure_list_traversal.md:242-243`), or the binding falls back to a statically fanned panel over the same fragment (keeps provenance, loses runtime cardinality).
2. **Q3 lands materially amended.** If landed `functional.v2` evidence or the report surface differs from the accepted design (implementation not started as of `ad5474c7`), the provenance half of the judgment value must be re-derived before binding is meaningful.
3. **A real panel materializes elsewhere first.** Run artifacts plus a report naming ordered lenses in another family would make that family the concrete consumer under the gate's own "concrete" test.
4. **Owner selects trial-runs adjudication as first consumer.** The draft trial-runs judgment member (`docs/design/workflow_lisp_trial_runs.md:333-401`) leaving Draft via its pending review *and* an explicit owner routing act — adjacency alone is not a trigger (mirrors the M0-brief neutral-IR rule, `docs/reports/2026-07-26-m0-decision-brief.md` §3).

Net effect: the Q4 entry condition reduces to "Q3 complete"; the consumer half is a recorded default awaiting countersign at the judgment-views design review, per the M0 frontloading pattern.

## 5. Open Unknowns

1. **defprompt-in-map-effect is unproven.** Both contracts' text composes — applications live in `provider-result :prompt` (`workflow_lisp_prompt_calculus.md:49-52`) and the map-effect body *is* a `provider-result` call (`workflow_lisp_pure_list_traversal.md:229-243`) — but no fixture or test exercises the combination ([INFERENCE] compatible; repo-wide grep found exactly one map-effect fixture, extern-prompt only). Cheapest closure: one compile-only spike fixture; not run in this read-only session.
2. **What artifact "bound" requires.** The roadmap never defines the binding act (routing text vs landed workflow). The M0 pattern supports recording the default now with countersign at the Q4 design review; if the owner reads "bound" as "landed panel workflow", the binding becomes Q4-plan Task 1 rather than an entry edit.
3. **Q3's landed schema.** Every provenance field a judgment value exposes depends on Q3's actual landed evidence (design accepted, implementation not started — roadmap:227-233).
4. **Recent-commit subjects unavailable.** The newest ~12 reflog entries carry no commit messages (`.git/logs/HEAD` tail, 2026-07-27), so "no prior Q4 partial decision" rests on doc-level greps: zero Q4/panel hits in the newest report (`docs/reports/2026-07-27-q5-phased-contract-delivery-design-review.md`), no judgment-views doc anywhere, and only routing-level Q4 mentions across `docs/plans/` and `docs/reports/` (greps 2026-07-27).
5. **Target arithmetic for the panel entry.** 2.18 list forms plus 2.20/2.21 prompt forms should coexist at `:target-dsl "2.21"` (2.18 is a minimum — `workflow_lisp_pure_list_traversal.md`, version contract; [INFERENCE] no doc states an upper bound), but only the same spike compile as unknown 1 proves it.
