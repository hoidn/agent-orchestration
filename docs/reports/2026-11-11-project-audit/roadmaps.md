# Audit slice: language/runtime roadmaps and pending designs

Task id: `review_design_language_roadmaps_audit` (reviewer, read-only).
Checkout: `/home/ollie/Documents/agent-orchestration`, branch `main`, HEAD `bb63b03b`, dirty tree (docs edits in flight; read as-is).
Excluded by brief: `experiments/`, structural-search docs, calibration reports.

Method: read status/selection/remaining-work sections of every listed roadmap and design; cross-checked against `docs/capability_status_matrix.md` (all rows), `docs/design/README.md`, `docs/index.md`; spot-checked code where a doc claim was checkable (`orchestrator/lsp/`, `orchestrator/dashboard/server.py`, test names). No tests run, no edits.

Scale context: `docs/plans/` holds 416 files (115 dated July, 62 October); `docs/design/` 100 files / ~61k lines; `docs/reports/` 78. Language targets went from ~2.19 (late July) to 2.40 (late October).

---

## 1. Roadmap table

| Roadmap | Purpose (one line) | Done | Remains | Alive? | Remaining items still make sense after evaluated execution? |
| --- | --- | --- | --- | --- | --- |
| `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` | Replace the flat executor with "evaluate the checked closed program + append-only memo" | Phases 0–3 closed (2.35); Phase 6a pilot; Phase 4c/W3 (2.36); PQ-1a/b Agent Sessions (2.38); Phase 7 retirement executed early via the 2026-10-13 amendment (§Phase 7, l.771–803) | Phase 5 Tasks 5–7 (public parallel qualification, best-of-N consumer, closeout); global Phase 6b; PQ-1c; per-phase closeout checkboxes (l.809–817) all still unchecked | **Alive** (the only roadmap with in-flight work) | Mostly yes. But §Phase 4 (l.586–638) is stale: 4a still names *portable context capture* a "priority addition" although the matrix marks it Retired (matrix l.146); 4b lists supervision/peers/adjudication/trials (retired) and human input/phased providers (since delivered at 2.40/2.39 by other plans). Status block (l.36–60) never mentions 2.38–2.40. Phase numbering is now inverted: Phase 7 is "complete" while Phases 5 and 6b are open. |
| `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md` | Research sequencing over five axes (compose, reuse, introspect, self-program, optimize) plus language workstreams EL-1/EC-1/PC-1/CF-1/W3/AA-1/CE-1 | E0–E2 complete (then retired); R0 ES parked; R1a reduced pilot; CF-1a/b (2.33); W3 (2.36); EL-1a/b/c (2.39), EL-1d cancelled; EC-1 resolved-inline subset shipped at 2.30 | R1b/R2/R3 unselected (R3 handed to the structural-search roadmap); CF-1c on hold; EC-1a/c, PC-1a–d, AA-1, CE-1 "pending, unselected" | **Partly alive**: the axis lifecycle (§Axis Lifecycle l.221–356) is the best conceptual text in the repo; the workstream ledger is stale | PC-1 section (l.453–512) is written as if 2.31 portable context is live ("implements… verified"), but the feature is Retired; it should be closed, not "pending". EC-1 is effectively done-as-subset; its remaining a/c steps have no named consumer. AA-1 and CE-1 are the only entries still pointing forward; both make *more* sense on the evaluated runtime (simulation and checked evaluation both reuse evaluator/memo). |
| `docs/plans/2026-10-15-orc-simplification-roadmap-extension.md` | Finite simplification: provider cleanup, WCC boundary, result-transport consolidation, 2.35 source floor, 2.39 EL-1, DC-P dynamic-core decision | All selected lanes complete (§Selection l.88–125; §Recommendation coverage l.1442–1473) | Nothing selected. Deferred: ordinary-provider confinement, environment/unlimited policy. Full suite left **red** (69 failure mechanisms, l.40–47) | **Closed** (execution record) | Yes — it is the one plan that reduced machinery (e.g. −64 forwarding kwargs, −50 lines in providers). The red-suite residue is the most important leftover and has no owner. |
| `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md` | Q-series prompt calculus (Q0–Q5) and L-series LSP utility (L0–L5) | All Q0–Q5, L0–L5 complete (l.3) | "Explicitly unselected" list (l.677–720): tolerant-but-loud normalization, residual prompt partial application, references/rename, runtime debug transport | **Closed** | Q4 judgment views and target-2.23 Q5 were retired at the 2026-10-13 cutoff (matrix l.79–80); Q5 was rebuilt at 2.39. The tolerant-but-loud normalization item is still a live principle-30 debt. |
| `docs/plans/2026-07-26-substrate-maintenance-track.md` | Estate shrink and persistence parsimony on the old executor | M0, M1, ML, M2(a), M3a, MR-4, MC, ME | MR-1/2/3/5, M2(b), M3b, M3c, M4 "unselected" (l.89–213) | **Effectively superseded** | **No.** M3b "effect-identity memo keys and memo-first resume" (l.172–176, 198–203) *is what evaluated execution delivered*; MR-1..3 (attempt pipeline, step loop, call-frame lifecycle) and M4 (executor/validation split) target the retired executor; M2(a)/M3a's pure-result replay profile is itself retired (matrix l.111). The track should be closed with a supersession note. |
| `docs/plans/2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md` | Compiler-frontend prerequisites P1–P5 for richer LSP | Nothing | P1 multi-diagnostic accumulation, P2 reader recovery, P3 span→type, P4 overlays, P5 incrementality | **Dormant with an unreachable gate** | Gate "after the E program" (l.47–57) can no longer fire: E/ES/trial execution is retired and parked. P1 (multiple diagnostics per compile) is the item that matters for agent authoring and belongs with AA-1 B, not behind E. |
| `docs/plans/2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md` | Hover, references, TextMate grammar over existing L1/L5 indices | Accepted design + reviewed plan (with SHA-256 receipts) | All implementation | Dormant | Low value. Design-and-plan were fully reviewed for features nobody has selected; LSP's evaluated-snapshot status is itself ambiguous (see §5 item 6). |
| `docs/plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md` | Decide whether recursion/sugar is needed | REC0 measured 77% reduction at current surface; Gate REC0 → `STOP_REC_SUGAR` (l.3–10) | Nothing (two redirects unselected) | **Closed honestly** | Yes; a good example of a stop rule actually firing. |
| `docs/plans/2026-08-14-omp-integration-design-and-roadmap.md` | OMP provider templates, JSON codec, `prompt run/import/resume`, conf presets, `:session-artifact` | OMP-I1 closed 2026-08-26 | OMP-I2 (declarative capability loading) unselected | **Historical**; most of OMP-I1 retired | `prompt run`, both `prompt import` modes, scaffolds and `:session-artifact` are retired (l.5; `omp_provider_and_native_continuation.md` l.11–17). Only templates, codec and native `prompt resume` survive. `omp_conf` has no invocation path in the evaluated performer (`omp_provider_and_native_continuation.md` l.28–33), so the multiagent conf presets are dead weight. OMP-I2 should be dropped. |
| `docs/plans/2026-10-02-agent-authoring-improvements-plan.md` | Raise the rate at which an agent writes a correct `.orc`: guide, remedy diagnostics, outcome simulation, inferred effects | Stream D's prerequisite (EL-1 at 2.39) delivered elsewhere | Baseline authoring trial, A guide, B remedies, C `simulate` | **Alive but never started** | Yes — more so than when written. Minor staleness: §2 says the guide may point to "trials… and resource transitions" (both retired). |
| `docs/backlog/README.md` + `docs/backlog/active/` (40 items) | Historical proposal inventory | 0 moved to `done/` | 40 items, 38 carrying `Status: active` in frontmatter | **Graveyard** | Almost entirely flat/YAML/Design-Delta-era (March–June). The README admits that residence in `active/` means nothing, and `roadmap_gate.json` still names `dsl-v214-phase2-neurips-stack`. Two items still have current value: provider token-usage accounting (`2026-04-30-…`), which the Pareto cost objective needs if the harness does not already meter usage, and provider-prompt surface clarity. |

**Structural observation.** No document says what comes next for the language or runtime. Selection is spread across four files (index.md l.41), and every forward-looking entry in them reads "pending, unselected". The roadmaps have become ledgers of gates rather than plans. The only work in motion is Phase 5.

---

## 2. Pending-design table

Value and cost are this reviewer's estimates. Verdicts: **now** / **later** / **fold** / **drop**.

| Design | Idea in one sentence | Status | What concretely blocks it | Value | Cost / risk | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `workflow_lisp_evaluated_execution.md` §11 + Phase 5 plan | Run `par-map` items concurrently, n at a time, with per-item identity and one memo writer | 2.37 partial: compile/read-back and bounded workers accepted | Phase 5 Tasks 5–7 only (public interruption/resume, best-of-N consumer, closeout); no design question is open | **High**: agent calls are long, and best-of-N is the canonical consumer | Medium; the core is built | **Now** |
| `workflow_lisp_checked_program_evaluation.md` (CE-1) | Let an agent emit `.orc` source that is compiled under parent-fixed types, imports and effect bound, then run on the ordinary evaluator/memo, returning Success/Rejected/Faulted/Exhausted | Proposed, unselected | Owner selection and target; import authority, effect-bound and retry/invalidation contracts | High *if* self-programming/search is the thesis; otherwise low | Medium; it reuses everything and adds one form | **Later**, gated on the research track showing one calibrated positive. It is the language feature that directly carries the thesis. Absorb typed-program-gates C1/C3 into it. |
| `workflow_lisp_typed_program_gates.md` (C1/C2/C3) | Typed `check-workflow` verdicts, generational child adapters, parked `eval-workflow` | "Accepted, no implementation" (README) vs "Designed" (matrix) | Written against target 2.23, trial runs, pure-result replay and `compile_stage3_entrypoint` (Metadata l.10–62), all retired | Low as written | — | **Fold** C1/C3 into CE-1; **drop** C2 |
| `workflow_lisp_runtime_closures_boundary.md` | Guardrail that keeps ProcRefs compile-time until a full runtime-closure contract exists | Future / deferred acceptance contract | Deliberately blocked; no consumer. The DC-P decision kept typed W3 over the dynamic branch's native function values | Low (guardrail value only) | Low | **Keep as guardrail; drop as a feature track.** Refresh the "executable IR" vocabulary. |
| `workflow_lisp_progressive_execution.md` | Agreed brief → fixed `.orc` coordinator loop: a planning agent picks the next task, workers act, checks route the result | Draft; "zero new language machinery" | Its admission note (l.3) says host input and context are retired, but 2.40 typed host input and 2.38 Agent Sessions now exist. Nothing blocks it except selection. | **High** as a product demonstration | Low–medium (a workflow, not a language feature) | **Now**, as an ordinary workflow/example. Treat it as the flagship consumer that justifies or retires Agent Sessions and host input. |
| `workflow_lisp_parametric_type_system.md` | Generics, structural constraints, specialization | Implemented (doc) vs "Partial" (README l.112) | Deferred extensions are each trigger-gated (generic records, explicit type application, trait aliases) | Low now | Low | **Later**, by trigger. Fix the README status. |
| `workflow_lisp_write_once.md` W0 | Lint: don't redeclare a type an importable module exports | Unselected | Nothing | Medium: the census shows 253 lines, 30.9% of type-declaration lines repeated | **Very low** (no language change) | **Now** |
| W1 (constructor takes expected type) | Infer `(record T …)`/`(variant U …)` names from the position | Unselected | Typechecker drops expected type at let*/loop/continue | Low–medium (1,583 chars of redundant names) | Medium (typechecker plumbing) | Later |
| W4 (provider options bound once) | Bind model/effort/timeout on the provider binding | Unselected | Nothing | Low (census: 9 lines in one file) | Low | **Drop or fold** into provider-call-policy |
| `workflow_lisp_run_ref_expression_environments.md` (confined providers) | Run named-workflow children inside a Bubblewrap sibling profile with an inference gateway | 2.38 partial; commands OK; providers **blocked** | Codex managed-config normalization silently overrides requested features and storage; no way to verify effective config (report §"Native managed-policy gate: blocked", l.1219–1253). Tasks 10–13 cannot close. | Medium (safe candidate generation for search) | **High**, and depends on third-party CLI internals | **Drop provider confinement for now**; keep the command-only recipe. Revisit only if search needs untrusted generated code with tools. |
| `docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md` | Opt-in fail-closed Bubblewrap isolation for ordinary provider calls (blind-phase information isolation) | Partial; backend and broker standalone; Tasks 4–6 (executor, resume, attestation) not done | Integration targets the old executor (schema-2.2 attempts); its motivating July ".orc vs one-shot" program is superseded. The run-ref profile explicitly "never claims to satisfy it". | Low–medium | High (2,260-line spec) | **Drop** or fold into a single confinement profile. Two parallel bwrap security profiles is sprawl. |
| `workflow_lisp_agent_sessions.md` (PQ-1c) | Run-scoped mutable agent conversations with typed per-turn commits | First slice implemented at 2.38; PQ-1c comparison not run | Owner authorization for one clean plus failed/resumed real-provider comparison (eval plan l.674) | Unknown, which is the point | Low (one comparison) | **Now**: run PQ-1c or retire. This is the fourth attempt at provider continuity (provider sessions → context values → prompt queue → agent sessions). |
| `workflow_lisp_durable_host_input.md` (2.40) | Typed durable ask / answer / expire via resume | Implemented (plan "COMPLETE") | Live/paid qualification not selected | Medium | Done | No action. Use it in progressive execution. |
| `python_workflow_frontend.md` | Typed Python that traces to ordinary `.orc` | Serial subset implemented | `parallel_map` waits on Phase 5; `Agent` waits on Agent Sessions' fate | High (adoption: agents and humans write Python better than a bespoke Lisp) | Low–medium increments | **Now** for `parallel_map` after Phase 5; Agent after PQ-1c |
| `workflow_lisp_frontend_deduplication.md` | Shared argv/closures, prompt-declared host returns | Implemented and verified (matrix l.125) | — | — | — | Done; no action |
| `workflow_lisp_private_runtime_state_and_consumer_value_flow.md` (C2–C6) | Private lexical checkpoints and consumer-side rendering cleanup | Partial; Track R historical | Most of the umbrella is flat-route plumbing the memo replaced | Low | — | **Drop the umbrella.** Fold the one live item (renderers for lists whose elements lack a default renderer, matrix l.81) into the frontend spec. |
| `mlevolve_workflow_lisp_system_architecture.md` | MCGS-style ML search architecture in `.orc` | Draft (2026-06-09), pre-evaluated, built on certified adapters and YAML parity | Rebase onto evaluated execution, per its own admission note | Low (superseded by `experiments/mlevolve_pair` compact search and the structural-search track) | — | **Drop** (archive) |
| `dashboard_observability_summary_gui.md` | Read-only `/summaries` route over the summary index | Doc says current; README says "Designed/partial" | None. The route exists (`orchestrator/dashboard/server.py` l.470–472, 656–657) | Low | Done | Fix README status |
| `workflow_lisp_language_server.md` (F2, L6) | LSP over production compile entry points | L0–L5 implemented; F2 "OPEN_NOT_WAIVED"; L6 unselected | Head note (l.1–8) says evaluated W3 compiles terminate with `evaluated_execution_unavailable`, but no LSP code or test references that code, and `tests/test_workflow_lisp_lsp_cli_parity.py` asserts successful target-2.35 typed programs in LSP | Low–medium (agents rarely use editors) | — | **Resolve F2 (verify or correct the note); drop L6.** P1 moves to AA-1. |
| `omp_provider_and_native_continuation.md` (OMP-I2) | Declarative OMP capability loading | Unselected | Needs a named consumer and OMP-owned loaded-inventory proof | Low | Medium | **Drop** OMP-I2; mark conf presets inert. |

---

## 3. Stated design principles (from `docs/design/workflow_language_design_principles.md`) and whether the roadmaps honour them

1. **A high-level construct must reduce a recurring correctness burden; punctuation savings are not enough (P26, P1).**
   *Partly honoured.* REC stopped itself (`STOP_REC_SUGAR`) and EL-1d was cancelled for lack of a consumer, so the rule can fire. Counter-examples: with-live-providers (07-13), peer messaging (07-24), Q4 judgment views (07-29), trials (07-31) and portable context (2.31, about three weeks old) were each designed, fully reviewed, shipped and then retired at the 2026-10-13 cutoff. Q4 had a bound consumer, yet "no evaluated Q4 port is selected" (matrix l.79), so the consumer did not need it enough to carry it across the runtime change.
2. **Structured state is authority; reports and views are derived (P6, P7, P22).**
   *Strongly honoured* by evaluated execution: `state.json` is a derived view of the memo (matrix l.60).
3. **Resume is state reuse; validate before commit; never re-run a committed effect (P5, P10).**
   *Honoured* by the memo design. Counter-example: Agent Sessions deliberately trade recoverability for a mutable conversation (agent_sessions.md l.15–17). That is acceptable only if PQ-1c shows the trade pays, and PQ-1c has not run.
4. **Effects are explicit; macros cannot hide them (P3, P14, P15).**
   *Honoured*, and EL-1 at 2.39 recast "explicit" as "inferred and inspectable, not hand-written" (P15 permits this).
5. **Types are opt-in constraints, not mandatory taxonomies (P29, owner-directed 2026-07-25).**
   *Honoured late.* Until 2.39 every `defproc` had to carry `:effects` equal to the inferred set (census §4.4). Repeated type declarations are 30.9% of type lines, and W0, a free lint, is still unselected. The 2.33 generic unions arrived only after the std/phase result-shape defect forced them.
6. **Provider attention is conserved: obligations the deterministic side can carry never become prompt instructions (P30).**
   *Mostly honoured.* `provider_result_delivery.md` keeps transport instructions out of prompts. Counter-example: tolerant-but-loud boundary normalization, named as debt in P30 itself, remains on the unselected list (language-quality roadmap l.689–700).
7. **Refusals name their rule; "this principle adds diagnostics, not process: no registries, audits, or review ceremonies follow from it" (P28).**
   *Diagnostics part honoured; the anti-ceremony spirit is not.* Counter-examples: ordered `*_SPEC_APPROVED`/`*_QUALITY_APPROVED` tokens with external SHA-256 closure records (language-quality roadmap Q4/L4 rows l.84, 94); MC's "terminal status externally resolved" (substrate l.94); L6 has a reviewed design and plan with receipts for unselected features. Much of that ceremony was spent on features later deleted.
8. **Frontends lower to the shared typed core, never to text (P2); the deterministic, inspectable runtime model is preserved (P27).**
   *P27 is honoured* (parallel map returns results in input order with per-item identity). *P2 is in tension* with the Python frontend, which generates `.orc` source text (`python_workflow_frontend.md` l.14–16). It is a defensible choice for inspectability, but it contradicts the principle's wording and the principle has not been amended.

---

## 4. Conceptual assessment

### Where there is a coherent thesis

- **Runtime thesis (strong).** "Every `.orc` that typechecks runs, by evaluating the checked closed program against an append-only effect memo; resume is re-evaluation; views are derived" (eval plan Goal l.11–14; design §§6–9). This is crisp and differentiating: typed, resumable, inspectable composition of agent calls with no repeated committed paid effects. The 2.35 → 2.40 sequence (W3, parallel map, sessions, inference-default effects, host input, Python) is coherent around it.
- **Research thesis (coherent on paper).** The evolution roadmap's five independent axes and the "improve or retire, then simplify" lifecycle (l.221–356) are sound epistemics. They include an explicit "abandon the custom platform" branch (l.345–348).
- **Simplification extension.** A rare instance of the roadmaps deleting machinery on evidence.

### Where it sprawls

- **Capability ahead of consumer.** The July burst (115 plan files in one month) shipped prompt calculus Q0–Q5, LSP L0–L5, peer messaging, live binding, judgment views, trials, pure-result replay, OMP scaffolding and the lean pilot. Most were retired within 2–12 weeks.
- **Two isolation projects** (provider-phase isolation and run-ref confinement) built two Bubblewrap profiles for consumers that no longer exist or are blocked.
- **Editor tooling investment** (L0–L5 with full ceremony, L6 and P1–P5 designed) for a system whose primary authors are agents.
- **Ledgers that never close.** Substrate MR/M3/M4, private-runtime C2–C6, typed program gates, MLEvolve and 40 backlog items remain "pending" after their substrate was deleted.

### Built then retired: what the retire rate says

Retired between July and October: with-live-providers, provider peer messaging, Q4 judgment views, first-class provider context values (2.31), prompt queue (designed, superseded before being built), trial runs/E2/ES execution, derived pure-result replay (M2/M3a), the lean-pilot apparatus, OMP prompt run/import/scaffolds and `:session-artifact`, managed provider jobs, provider sessions, the watchdog executor, resource-transition and materialize-view execution, the Design Delta family, the YAML DSL, executable IR and the debug YAML renderer. That is roughly 15–18 surfaces.

Three were rebuilt: phased delivery (target 2.23, then 2.39), human input (Increment 5 `HumanReply`, then 2.40 `request-input`) and continuity (provider sessions / context / queue, then Agent Sessions).

What this says:

1. **Most retirements came from a runtime switch, not from negative evidence.** Features were coupled to the flat executor and were not ported. Only REC (stop rule) and PC-1 (a small comparison showed no advantage over a result handoff) were retired on evidence. The retirement was a healthy forcing function, but it reveals that principle 26 was applied by argument at design time, not by consumer pull.
2. **The rebuilds show where demand is real.** Continuity, human-in-the-loop and phased delivery each came back. These are the capabilities to invest in and to qualify properly.
3. **Ceremony was spent indiscriminately.** Equal-weight review and closure records went to features that lived a few weeks. A cheaper "prototype tier" (no ordered approvals until a consumer has run it in anger) would have saved most of that spend.
4. **Positive signal:** the owner does delete. The DC-P decision (simplification extension l.625–664) also shows a serious alternative foundation (dynamic core 3.0) was evaluated and stopped on evidence.

### Best value-to-cost in this slice

1. **Finish Phase 5 parallel map and add Python `parallel_map`.** The core is built; parallel best-of-N is the obvious throughput win for multi-hour agent calls.
2. **Agent-authoring loop: AA-1 baseline trial + B remedies + P1 multi-diagnostic accumulation, with W0 as a free lint.** This targets the actual authors (agents) and reuses existing diagnostics. P1 must be unhooked from the dead "after E" gate.
3. **Progressive execution as an ordinary workflow, used as the flagship consumer.** It needs no language machinery and exercises 2.38 sessions plus 2.40 host input end to end. A product demo is the evidence the research track keeps lacking.
4. **PQ-1c.** One comparison closes a feature's fate: retain or retire Agent Sessions.
5. **CE-1, next after a calibrated positive.** It is the only pending language design that directly carries the self-programming/search thesis, and it reuses compiler, evaluator and memo.

### Sunk-cost continuation

1. **Run-ref confined providers.** Blocked on Codex's managed-config normalization, i.e. third-party internals (report l.1219–1253); 13-task plan; high security-review cost.
2. **Provider-phase information isolation.** Its July experiment consumer is gone, its integration targets the retired executor, and it duplicates the run-ref profile.
3. **Substrate track residuals (MR-1/2/3/5, M2(b), M3b/c, M4).** Their target was deleted, and M3b's goal is already the evaluated memo.
4. **LSP L6, and the P-series as gated.** Accepted designs and plans for hover/references/grammar with no consumer, while basic evaluated-snapshot parity (F2) is unresolved.
5. **Pre-evaluated drafts kept as "pending":** typed program gates C2/C3, private-runtime C2–C6, MLEvolve architecture, OMP-I2, and the 40-item backlog.

---

## 5. Contradictions

1. **Portable context: priority vs retired.** Eval plan §Phase 4a (l.593–603) and evolution roadmap PC-1 (l.453–512, "implements… verified") present portable context as live or prioritized; matrix l.146 says Retired; matrix l.115 says Increments 4–5 retired.
2. **Phase 4b class list is stale.** Eval plan l.604–609 lists human input and phased providers as future Phase 4b classes; both are delivered (2.40 and 2.39) by other plans and are not linked back. It also lists supervision/peers/adjudication/trials, all retired.
3. **Eval plan status omits 2.38–2.40** (l.36–60), and Phase 7 "Retirement" is complete while Phases 5 and 6b are open.
4. **Substrate track M3b vs evaluated execution.** "Effect-identity memo keys and memo-first resume… not selected" (substrate l.172–176, 198–203) contradicts the delivered evaluated memo (matrix l.60).
5. **P-series entry gate is unreachable.** "After the E program" (P-series l.47–57) vs E/ES/trial execution retired (matrix l.63; evolution roadmap §Current ES Boundary l.774–781).
6. **LSP evaluated status.** The design head note (language_server.md l.1–8) says evaluated W3 compiles end in `evaluated_execution_unavailable` and F2 is OPEN_NOT_WAIVED. Matrix l.68–73 mark L0–L5 "Implemented; Yes". `orchestrator/lsp/` never references that code, and `tests/test_workflow_lisp_lsp_cli_parity.py` (l.160–185) asserts successful target-2.35 typed programs. Either the head note is stale or the matrix overclaims. Not verified by running.
7. **Dashboard summary GUI.** design/README l.128 says "Designed/partial"; the doc says current; the route exists in `orchestrator/dashboard/server.py`.
8. **Parametric type system.** design/README l.112 says "Partial (tranche one landed)"; the doc header says "current implemented parametric contract".
9. **Typed program gates.** design/README l.108 says "Accepted"; matrix l.64 says "Designed". The doc still depends on retired trial/pure-replay substrate.
10. **Trial runs row.** Matrix l.63 is labelled "Partial" although its own text says `trial`, its SDK and ES execution are retired; only E0's direct task survives. The label misleads.
11. **OMP conf presets.** Matrix l.147 lists the `fanout/peer-team/advised-fanout` confs as the example, while `omp_provider_and_native_continuation.md` l.28–33 says `omp_conf` has no evaluated invocation path.
12. **Progressive execution admission note** (l.3) says host input is retired and gives no route; 2.40 typed host input and 2.38 sessions exist (matrix l.117, 82).
13. **Agent-authoring plan §2** routes readers to "trials… resource transitions" in the drafting guide; both are retired (matrix l.63, 132).
14. **Principle P2 vs Python frontend.** "Never lower to text" vs `.orc`-source generation; the principle has not been amended.
15. **Simplification extension "complete" vs red suite.** The selected scope is "complete" while the full suite is red with 69 failure mechanisms (l.40–47). The eval plan's Global Constraints (l.111–112) and Closeout require "no new failures" per phase. Every phase since Phase 3 has closed on a RED full suite with dispositions, so "no new failures" has quietly replaced "green".
