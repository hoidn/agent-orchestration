# ORC Research Demonstration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (or `superpowers:executing-plans`
> for an approved separate execution session). Use checkboxes to track tasks.

**Status:** ES remains owner-parked and PC-1 unselected. The reduced R1a pilot,
assisted C1 feasibility, and qualitative ergonomic assessment are recorded. The
follow-on documentation portion is addressed; C1 receipt-interface
implementation remains unselected. Historical charges, holds, pilot results,
configured roles, and the existing USD375 cap remain recorded below.
See the [execution record](../reports/2026-09-08-orc-research-demonstration.md).

### Proposed follow-on — explicit current-value handoff

**Owner decision required: select one local example/interface repair, at most
USD15 all-inclusive and 60 minutes elapsed implementation time.** This paragraph
authorizes no implementation. Baseline is commit `5e4e761a` and the completed
assisted C1 pair; proposal preparation alone is selected, under the owner's
separate at-most-USD10 Main reserve inside the unchanged USD375 project cap.
The documentation portion of this proposal was addressed by the 2026-10-01
consistency pass; the C1 original/terminal receipt-interface implementation
remains unselected.

**Resolved fact.** The maintained example is not generally broken. This exact
selection-free invocation compiled unchanged with exit0 and empty diagnostics:

```sh
python -m orchestrator compile workflows/examples/review_revise_design_docs.orc \
  --source-root workflows/examples \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json \
  --diagnostics-json
```

The earlier explicit `--entry-workflow
review_revise_design_docs::review-revise-design-docs` hit the name-gated bootstrap
route. `workflows.py::_entry_bootstrap_name_gate_denial` accepts only particular
entry names; `test_build_artifacts_emit_private_artifact_catalog` deliberately
uses `entry_workflow=None` for this example. This is real invocation-dependent
discoverability friction, not evidence that its omitted `run` binding always
fails. Compilation here proves no new runtime or agent-effectiveness result.

**One bounded change, if selected:**

- In `docs/lisp_workflow_drafting_guide.md`, put the working command beside the
  maintained `review_revise_design_docs.orc` example and explain its file-oriented
  subject contract. Keep the working example source and public export unchanged;
  do not rename it to satisfy the compiler name gate or add an allowlist exception.
- In `experiments/orc_research_demo/development/review_handoff.orc`, replace
  duplicate `completed-local`/`blocked-local` receipt builders with one
  `review-unit` helper taking `original Candidate`, `terminal Completion` and
  `boundary String`. Remove unused findings forwarding from delivery/cancellation
  helpers; retain actual findings inputs where review/revision/completion use them.
  Keep the public `review-completion` signature, leaf operations, Python control
  and meaningful behavior unchanged.

Expected author-facing usage (named arguments, not a new language feature):

```lisp
; Before: identical receipt builders; findings is forwarded but unused.
(call completed-local :candidate candidate :findings findings
  :completion completion :boundary boundary)
; After: original is provenance; terminal owns the final candidate/findings.
(call review-unit :original candidate :terminal completion :boundary boundary)
```

`revise-candidate` still explicitly reviews the revised candidate before creating
`completion`. Only the common receipt boundary projects the original payload and
the terminal's current candidate/findings fields. Neither a stale digest nor a
success label can substitute for approval of the actual completed candidate.

**Alternative considered:** revisit `std/phase` so a review/fix operation returns
its final subject with decision/findings, rather than only path-backed
`ReviewLoopResult` evidence. That is the substantive solution if one abstraction
must serve both file-mutating and value-returning consumers: today's procedure
updates `state.completed` but discards it from its public result. It may require
revising result polymorphism and findings ownership, not another adapter/helper
layer. The present type/language design is not sacrosanct. Do not implement that
contract change, invent C1 findings files, or copy/fork the stdlib loop in this
local repair. **Tradeoff:** the recommendation leaves this cross-domain coupling
unresolved and C1's bounded control explicit; it does not deliver one generic
review abstraction for all subjects. If that is the required outcome, reject
this local scope and select an explicit abstraction revision instead.

**Verification and ergonomic acceptance:** reuse the existing C1 normal-case
execution helpers for R1/R2/R3, including actual assemble/index handoff and blocked
cancellation, unchanged accepted content and approval of the current candidate.
Retain the existing stale-review invalid example. Compare semantic results, not
incidental formatting, callback/write counts or ordering. Recompile the documented
example through the command above; exercise its existing review/fix behavioral
fixture only if the example source unexpectedly needs changing. No live provider
study, collision comparison, new matrix or judge pipeline. Review actual
before/after callers: the invocation is discoverable at the example; a reader
can identify original versus final values locally; receipt changes have one
owner; no unused findings plumbing, new shim, forced file encoding or nonlocal
compiler change remains. These are qualitative judgments, not a numeric reuse pass.

Count authoring, Main assistance, debugging, verification and reporting inside
the implementation envelope; recheck ledger headroom before admission and retain
USD27.30 old holds. Use installed OMP defaults plus the existing cost hook,
resolved OpenAI role and ordinary task/workspace/session settings. No child is
launched for this proposal. Stop and report at the bound or if the local repair
requires compiler/stdlib contract changes; do not silently turn it into redesign.
Preserve successful runs, scored history and unrelated dirty code.

### Owner-selected assisted C1 development

**Completed record (2026-10-01):** Assisted C1 feasibility and the qualitative
ergonomic assessment are recorded in the
[execution report](../reports/2026-09-08-orc-research-demonstration.md#assisted-c1-development-and-corrected-interpretation).
The “Start now” instruction below is preserved historical text; no new C1
development is selected, and the proposed receipt-interface implementation
remains unselected.

Start now: develop correct review/revision-to-handoff ORC and reusable Python
using the existing C1 leaves and identical meaningful acceptance conditions.
Use development copies, normal tools/docs and behavioral feedback; the previous
no-tools/three-turn restriction does not apply and original scores stay unchanged.
Try `std/phase` first. Verify exact current-candidate approval, real selected
handoff, blocked cancellation and preservation. Record assistance and actual
construction/debugging/verification effort with existing metering under USD375.
Compare the working pair before redesign. The owner's subsequent reuse
clarification withdraws the prescribed two-consumer maintenance comparison as
an ergonomic-reuse test: do not allocate more work to that proxy. Preserve any
completed maintenance checks as behavioral regressions only. Assess ergonomic
reuse from actual `.orc` abstractions and callers, qualitatively, or leave it
unassessed when useful examples are absent. LLM-assisted review is acceptable;
no new judge pipeline or mandatory benchmark is selected.
No new qualification project, full pilot rerun or other workstream is selected.

### Normal-session correction — selected documentation and steering work

Practical authoring and adaptation use ordinary Codex or OMP coding sessions,
as specified by the design's [normal agent sessions](../design/orc_reuse_introspection_search_experiment.md#normal-agent-sessions-and-evaluation-boundary).
The outer driver supplies tasks/workspaces, collects costs and results, and
evaluates behavior; the agent owns its normal read/edit/compile/run/debug loop.
Use normal tools, applicable project instructions/skills, context management,
and available language tooling. Do not replace these with source-only responses,
compiler-only corrections, an arbitrary model-turn limit, or an experiment-only
tool whitelist. Disclose any necessary departure from the normal configuration.
Keep task scope and approved total cost/time limits; this is not unlimited work.

Scored sessions keep final answers and hidden cases outside the author workspace;
removing tools is not answer isolation. The exposed C1 recovery is development:
reuse its working sources and checks, disclose assistance and the actual session
profile, and do not claim fresh independent authoring or per-language inference
costs from one author constructing both versions. Do not restart a healthy child
or repeat a passing example solely to change its label. No fresh study is selected.

The brittle aggregate/ledger grading was an avoidable evaluation-design error,
not just an undisclosed contract. For any selected future check, justify exact
shape, order, callback count or intermediate-write constraints by an actual task
or consumer need; accept harmless alternatives otherwise. Use the existing valid
and invalid examples to check that distinction, not a new qualification project.
Preserve old checker outputs without interpreting invalid rejections as task
failures or evidence against the language. Correctness checks answer behavioral
questions; ergonomic reuse needs grounded judgment, or remains unassessed.

Implementation checklist for this owner-requested correction:

- [x] Replace the default author-session contract in the existing design and
  charter; distinguish task-level revision episodes from internal debugging.
- [x] Align this plan, the current roadmap, and their index entries. Keep the
  five axes independent; replace the portfolio-test proxy with grounded
  qualitative assessment of ergonomic `.orc` reuse and reject incidental grading
  constraints without a task/consumer justification.
- [x] Steer OMP to align live `inputs.json`, continuation/handoff instructions,
  and the next needed invocation. Preserve frozen pilot prompts and launch records.
- [x] Check the scoped diff, links/routing, live manifest parsing, an existing
  demo smoke, and OMP receipt/application of the steering. No new runner or ledger.

Verification (2026-09-10 UTC): independent review resolved the remaining blanket
fresh-case requirement for ergonomic improvement. All 47 added/changed local
Markdown links resolved; scoped whitespace checks and live manifest parsing
passed. The focused E-series routing test passed (1 test), and the unchanged
public-entry four-arm demo smoke passed (1 test, 33.86s) on retry in a dedicated
temporary directory. Its first attempt failed during workspace copying with
ENOSPC, before behavior ran. OMP received the corrections, updated live roles and
the current handoff, and marked both old continuation/steering files historical.
These checks validate documentation/routing and the existing scripted-provider
demo, not normal-agent efficacy or ergonomic reuse. No new default-profile
author session or fresh scored study was launched to validate these doc changes.

### Owner subtraction — preserved reduced R1a scope

The owner supersedes exhaustive source-identity, checkpoint, replay and
interrupted-run recovery admission gates. Use fresh runs for construction and
practical reuse; P1 measures changed policy reaching intended callers and
preserved outputs, not general old-run resume. Keep genuine selective reuse,
behavioral checks, fair exposure, minimal executed-source/artifact attribution
and metered effort. No new recovery framework or approval cycle is selected.

The reduced pilot's executable protocol amendment is
[`owner-scope-subtraction.json`](../../experiments/orc_research_demo/evidence/owner-scope-subtraction.json).
It governed that pilot's gates, not the selected development task above.
Retain its 24 behavior cells and six adaptations/eighteen consumer checks. Its
planned diagnostic subset was D2/D3/D4: three descriptive pairs/six assessments.
Retain D1 coercion and D5/D6 recovery/identity failures as limitations and preserve
the original six-pair/twelve-assessment record. Neither the original threshold nor
a rescaled threshold is claimable. Diagnostics do not hold other axes hostage.
Measured closeout: C1 passes2/3, C2 fails to build, C3 and Python fail strict
aggregate checks with meaningful partial behavior and contract limitations.
Four D3/D4 diagnostic assessments are complete; D2 remains unavailable.
All six adaptations/eighteen checks are retained as unavailable because no
complete measured baseline portfolio exists, not because of retired recovery gates.
See `evidence/scored-construction/axis-disposition.json`: further corrected
measurement needs explicit protocol selection; R1b/R2/R3 remain unselected.

**Goal:** measure programmability/compositionality, reuse, introspection,
self-programmability, and eventually optimization as independent hypotheses,
then turn evidence into bounded improvement or retirement and simplification
of each affected scope before investing in a general optimizer or replacement
foundation.

**Architecture:** reuse the compiler, diagnostics, immutable child runs, and
trial evidence. ORC composes agent/provider operations; those agents/providers
perform tool use. The experiment controller stays outside the runtime.

**Tech stack:** existing Python/pytest, Git, Workflow Lisp compiler and E1/E2
APIs; Rust only for the later, separately approved scientific task corpus.
No new dependency, service, language form, or registry is planned for the
initial demonstrations; evidence-led follow-ons may reconsider the foundation.

**Governing documents:** the [research charter](2026-09-08-orc-research-charter.md),
[current roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md),
[demonstration design](../design/orc_reuse_introspection_search_experiment.md),
[trial design](../design/workflow_lisp_trial_runs.md), and binding
[program-search boundaries](../design/workflow_lisp_program_search_boundaries.md).
Normative execution contracts remain in `specs/`. Per owner direction on
2026-09-08, execution safety is outside this research assessment and is not an
investment criterion or proposed workstream. This draft changes no runtime
contract; implementation-route discrepancies must be stated, not mistaken for
conceptual objections to composing tool-using agents.

## Documentation Preparation — This Request

- [x] Draft the one-page charter and durable experiment design.
- [x] Overhaul current roadmap sequencing; preserve historical evidence,
  pinned ES apparatus, and unrelated pending work.
- [x] Align documentation discovery and old prospective ES routing.
- [x] Independently review design and plan; verify the documentation diff and
  existing routing checks. Do not execute the research tasks below.

Original three-axis preparation verification (2026-09-08): independent design, plan, and routing
reviews found no remaining blockers after corrections; the existing routing
module passed all 71 tests, 64 added/new relative Markdown links resolved, and
the scoped whitespace check passed. The pinned ES refreeze plan retained its
original digest. These are documentation checks, not research results or
approval to execute the draft. They do not certify the later five-axis amendment.

## Five-Axis Amendment — Documentation Work Only

The owner requested these amendments after reviewing the expanded approach.
Approval to edit these documents is not selection of the experiments below.

- [x] Add explicit programmability/compositionality and self-programmability
  hypotheses to the charter and experiment design.
- [x] Replace R1's measurement allocation with bounded R1a construction,
  reuse, and diagnosis; define R1b authoring/revision separately.
- [x] Amend plan tasks, budgets, early ordinary-code control, and per-axis
  disposition; align the roadmap and discovery/scheduling descriptions.
- [x] Independently review the amended documents and run fresh routing,
  link, whitespace, and historical-preservation checks.

Five-axis amendment verification (2026-09-08): independent design and plan
reviews found no remaining blockers after fixing preparation/freeze order and
limiting the early ordinary-code control to its allocated construction checks.
The focused routing test and full 71-test routing module passed; all 67
added/new relative Markdown links resolved and scoped whitespace checks passed.
Historical routing/scientific records and the pinned refreeze-plan digest were
preserved. R1 became R1a/R1b; no research unit was selected or marked complete,
no executable selector changed, and no new OMP steering was sent.

## Consequent-Action Amendment — Documentation Work Only

The owner requires each axis to lead beyond a minimum viable example: pursue
principled improvement where justified; otherwise abandon the unsupported line
and simplify what remains. Foundational assumptions, including the type system
and language principles, must be reconsidered where they cause the obstruction;
local fixes are not the only alternative to giving up. This amendment selects
no research, redesign implementation, or deletion work.

- [x] Extend the roadmap with axis-specific improvement, retirement, and
  simplification branches; distinguish evidence from investment decisions.
- [x] Align the charter and design's decision rules, and make the plan's
  evidence review produce an actionable follow-on or closure, including
  assumption review and justified foundational alternatives.
- [x] Update discovery, independently review, and verify routing and preserved
  historical evidence. Leave existing experiment budgets and ES work unchanged.

Consequent-action verification (2026-09-08): independent review approved the
revised lifecycle and assumption review after correcting an overbroad platform
stop rule. The focused routing test and full 71-test routing module passed;
three added relative links and their anchors resolved, and whitespace checks
passed. Initial budgets, historical roadmap, ES boundary/refreeze digest,
independent work, and legacy routing-input digest were preserved. The five
research units remain unchanged; conditional Task 7 is unselected. No executable
selector, workflow, runtime, or research allocation changed.

Recursion-limit clarification verification (2026-09-08): independent review
approved; the focused E-series routing test, new-link checks, and whitespace
checks passed. The full routing module returned 68 passed and three failures
in surfaces untouched by this clarification: PyYAML-retirement wording, Q2
`active` wording, and the master-spec title's v2.26/v2.27 assertion. Targeted
reruns reproduced all three; they were not changed or weakened here. Research
units, selection, runtime, and current language contracts remain unchanged.

## Session-Pattern Amendment — Documentation Work Only

Incorporate the owner's approved session-mining recommendations into the
existing research track; preserve the separately recorded R0/R1a entry decision.
This amendment selects no experimental preparation, inference, or successor work.

- [x] Preserve a concise, sanitized evidence report with sampling limits;
  derive behavioral requirements rather than replaying historical instructions.
- [x] Prioritize review-to-completion composition and agent-chosen workflow
  improvement inside the existing case/episode allocations; carry recovery,
  steering, attribution, and design-reconsideration cases into scoped follow-ons.
- [x] Align the design, charter, roadmap, and Tasks 1–7 on controls, transfer,
  measurement limits, and improvement/retirement consequences without adding stages.
- [x] Review the amendments and verify routing, links, whitespace, preserved
  historical evidence, and the absence of changes to frozen study assets.

Session-pattern verification (2026-09-08): independent specification and
plan/quality reviews approved after correcting an early skill-control scope
conflict. Three focused routing checks and the full 71-test routing module
passed; 23 new/changed relative links and their anchors resolved, and whitespace
checks passed. The historical roadmap section, five research units, R1b caps,
pinned refreeze plan, and legacy review-input bytes were preserved. The separate
agent-assisted staffing amendment was retained, not accepted for spending by
this review. No workflow/runtime/prompt or executable selector changed, so no
workflow smoke was required; these are documentation checks, not research results.

## Agent-Assisted Amendment — Documentation Drafting Only (2026-09-08)

This dated checklist records a proposed R1a execution amendment, not an
experiment selection or budget approval. R0 remains owner-parked and the
separately recorded R1a Task 0 entry decision is unchanged.

- [x] Draft this plan's R1a execution boundaries, staffing, accounting,
  input-manifest, freeze, and stop rules.
- [x] Keep the fixed R1a allocation at 24 behavior cells (12 regression cells
  across four fixed arms, 9 cells across three novel requirements, 3 early
  Python/native control cells), 6 portfolio adaptations with 18 consumer
  checks, and 6 paired diagnosis cases with 12 assessments.
- [x] Keep preparation → oracle/library/case/truth freeze → measurement order,
  and keep R1b's separately selected three-episode budget unchanged.
- [x] Independently review the proposed roles, accounting, ceilings, thresholds,
  and preparation/measurement contract. Review approval is not owner allocation.
- [ ] Owner: accept the protocol, resource ceilings, exact model/configuration,
  pricing/metering method, and entry feasibility before experimental preparation.
- [x] Main: validate the amended plan against the governing design and current
  entry/routing records; no preparation, provider allocation, or measurement
  follows from drafting this checklist.

Until owner acceptance and the Task 0 entry conditions are satisfied, R1a
remains an unallocated draft. Assistance with this amendment before
selection is prior planning overhead: disclose it separately, do not count it
as a measured sample, do not assert that it was free, and do not place
experimental preparation outside the proposed caps.

Amendment verification (2026-09-08): two independent reviewers closed their
findings after separating scored diagnosing agents from truth-bearing blinded
scorers and making the confidently-wrong guard unconditional across both
diagnosis continuation branches. The focused E-series routing test passed
(1 passed); 28 added relative documentation links and their anchors resolved,
and the scoped whitespace check passed. The checkpoint JSON parses, ES remains
parked with its recorded study counters at zero, and the pinned refreeze digest
remains `5249e95a14725b9c9898553222133cf644c70bff55f98cd0b712e835e5e3e843`.
This verifies documentation, not API feasibility, runtime metering, or experimental
behavior. No experimental preparation or measurement was performed. Amendment
assistance is prior planning overhead; no reconciled cost receipt is available
here, so its cost is not reported as zero.

## PtychoPINN Transfer Amendment — Documentation Work Only

Incorporate the owner's approved mining insights into the existing research
questions, not a new study or executable workflow. This amendment changes no
allocation, accounting, entry/recovery decision, or recorded result; current
execution authority remains with Task 0 and the roadmap's hand-back.

- [x] Extend the existing sanitized session report with the PtychoPINN corpus,
  public descendant evidence, sampling limits, and counterexamples.
- [x] Specialize the existing non-orchestrator transfer requirement around an
  adaptive scientific study; distinguish routing/reuse from discovering the
  scientific cause, and native experiment machinery from ORC composition.
- [x] Align case preparation, exposure controls, five-axis claims, and
  improvement/retirement consequences across the design, Tasks 2–7, charter,
  roadmap, and discovery. Preserve all case counts, resource ceilings, current
  execution records, and frozen ES assets; run no research from this amendment.
- [x] Independently review the amended design and plan, then verify focused
  routing, the full routing module, relative links/anchors, whitespace, and
  historical/frozen-asset preservation. Keep failures and concurrent edits visible.

Verification: independent design and plan reviews approved this amendment;
the focused routing selectors passed (3 tests), followed by the full routing
module in tmux (`pytest -q -n 16 --dist=worksteal`, 71 tests). Seven added relative
links/anchors and amendment whitespace passed; the historical roadmap, five-unit
sequence, and both frozen ES asset digests are unchanged. Initial ad hoc checks
misclassified existing Markdown hard breaks and unit labels; corrected checks
passed without changing those documents. Concurrent execution-owner edits are
preserved, and that owner acknowledged the amended case-preparation guidance.
These are documentation checks, not research results. No runtime, prompt,
workflow, or executable artifact contract changed in this amendment, so no
workflow smoke was needed; study execution remains separately owned.

## Execution Boundaries And Replacement Budgets

R1a comprises Tasks 0–2 and its Task-4 report. **Owner-approved recovery,
2026-09-09:** replace the token/request stop ceilings with the existing
**USD 50 TOTAL-spend ceiling**, not an additional USD 50. Preserve and reconcile
all earlier coordinator, preparation, failed/repair, assessment, integration,
and reporting spend. Tokens (including cached input, reasoning counted once)
and requests remain reported effort metrics, not stop ceilings. The existing
**eight aggregate elapsed agent-execution hours** and **40 aggregate active human
oversight/assistance person-hours** remain limits. Scope, exposure controls,
parked ES disposition, and separately selected successor budgets are unchanged.

**Subsequent owner amendment:** “you have autonomous permission to increase
caps.” The coordinator may increase resource caps without another approval
pause, using finite, recorded amendments before further admission. The first
monetary amendment raises R1a's cumulative ceiling from USD50 to **USD75**;
it does not reset or forgive any prior charge. Later increases must preserve
the ledger and record old/new limits, reason, remaining work, and evidence.
This authority changes resource ceilings, not case allocations, role/exposure
controls, evidence gates, ES parking, or authority for new scientific execution.
Keep separately selected successor allocations explicit and finite.

**Model-routing amendment:** use configured native model roles, not hard-coded
GPT-5.4/OpenRouter selections. Current `@task` and `@smol` resolve to Luna;
`@slow` resolves to Astra. Terra may be used where the configured role selects
it. Preserve the role's thinking setting and freeze resolved model/configuration
within each paired assessment. The experiment boundary admits only direct
OpenAI/OpenAI-Codex providers; unrelated global vision/debug roles do not
authorize non-OpenAI experiment inference. Retain all historical receipts and
unknown-cost holds unchanged. Delegate bounded implementation and review work
through the same metered boundary; Main integrates and validates.

Before further research calls, use the qualified experiment-local SQLite
reservation ledger through OMP's native `before_provider_request` hook. Denial
exits before provider transport. Missing receipts retain their full reservation
and block further admission unless explicitly quarantined with a recorded
reason under the owner's approved recovery policy. Quarantine never releases
money or fabricates usage: its full hold counts against every later admission,
while only one new unquarantined request may be active. Only a valid recovered
receipt can settle and release that hold. Terminal receipts settle actual
reported cost. Reserve
the full model-bound cost of Main's single final handoff response, then end
that long-context session without polling; the fresh gated coordinator continues.
The [input manifest](../../experiments/orc_research_demo/inputs.json) owns the
frozen profile and reservation amounts; the
[execution record](../reports/2026-09-08-orc-research-demonstration.md) preserves
prior overruns and subsequent qualified evidence. No preparation/measurement
claim follows solely from monetary admission checks.

R1a uses independently scoped preparer, scored author/adaptor/diagnoser, and
scoring-assessor contexts plus an unscored coordinator. Paired conditions use
the same frozen model/configuration, tools, and context policy with fresh
contexts. A case preparer never scores its own hidden case. Scored agents never
see truth manifests or held-back answers; the separate scoring assessor receives
the frozen rubric/truth and anonymized responses without condition identity.
The initial output is controlled
agent-assisted construction/reuse/diagnosis evidence, not human performance,
live task efficacy, or autonomous closed-loop success. Where actual agent
authorship occurs, report it as agent authorship with its cost; do not
describe it as simulated human work or as free.

Those roles describe the original assessment protocol, not a qualification
prerequisite for the selected assisted development. Future scored authors and
adaptors use the normal-session contract above: the same declared ordinary
agent profile for both representations, accessible development feedback, and
final answers absent from the author environment. A fresh context does not
mean an agent without its normal tools or applicable project instructions.

This allocation **replaces**, rather than extends, the original 48-cell,
twelve-fault, optional twelve-proposal slice:

| R1a work | Replacement allocation |
| --- | --- |
| Existing four-arm regressions | Four arms × three selected scenarios = twelve cells. |
| Novel composition | Three held-back requirements × three behavioral scenarios = nine cells. |
| Early Python/native control | One matched requirement × three scenarios = three cells. |
| Behavior-cell total | Twenty-four cells, evaluated once per frozen program. |
| Reuse | Three portfolio-wide changes × two source conditions = six adaptation/verification efforts; each verifies three consumers, giving eighteen consumer checks. |
| Introspection | Six paired cases, one per fault category; two equivalent variants assigned one per evidence condition = twelve assessments. |

Oracle qualification and focused regression tests are preparation/verification,
not extra independent experimental samples; their effort still consumes every
R1a ceiling. No standalone compile-mutation study remains. If preparation or
measurement does not fit, stop with partial evidence and named gaps. Do not
repopulate the retired matrix, add a review/recovery/steering matrix, or
silently substitute easier cases. Repeated deterministic checks do not create
new independent samples.

The original reuse proxy used total metered model
input-plus-output tokens for full adaptation and verification per condition.
Cached tokens count as input, and reported reasoning/output must not be counted
twice. Report actual USD, elapsed time, request count, and human intervention
separately; never convert agent time into person-hours. Disclose setup and
payback in the same token metric. Its exploratory continuation thresholds were
at least 20% lower median token effort with no extra regressions for reuse; for
diagnosis, either one additional correct assessment out of six or at least 20%
lower median token effort without correctness loss. Neither diagnosis branch
permits more confidently wrong answers. Fix condition model/configuration/semantics,
counterbalance variants, and use fresh-context order.
These retained thresholds describe the old study; they do not define ergonomic
reuse or govern its next assessment. The design's Experiment A now owns that
qualitative question. Semantic correctness checks and effort observations may
support the account but cannot substitute for evidence about using abstractions.

R1b remains unselected Task 3 plus its Task-4 report. Before selection, set a
finite monetary/time envelope appropriate to ordinary tool-enabled sessions,
including preparation, debugging, evaluation and assistance. The original
proposal of thirty model requests, 250,000 tokens and nine source versions is
not the prospective authoring loop: requests/tokens are effort metrics, and
internal edits or compile repairs are not separately rationed source submissions.
Retain the three proposed episodes, with at most two objective-level revision
milestones per episode, distinct from the agent's internal development loop.
The earlier three aggregate execution hours and eight oversight person-hours
remain proposed time bounds to assess at selection, not a new allocation.
Leaf execution uses deterministic doubles, not live domain providers. Freeze
the actual agent/model profile and all-inclusive monetary/time limits before
entry; stop when the selected limits are exhausted. This correction raises
neither the current USD375 cap nor any approved study budget.

The R1b final-check allocation must be reserved before adaptive spending. The
three episodes are descriptive feasibility, not an ORC-versus-Python agent
comparison. Matching agent-control episodes need their own later allocation;
do not silently double this budget to obtain them.

Task 0 selects only R1a preparation/measurement after the proposed amendment,
budgets, exact model/accounting roles, and existing-mechanism feasibility have
been accepted. R1b needs its own entry review and resource allocation; it does
not require positive reuse/introspection screens. Tasks 5–7 also require
separate protocols and allocation. Task 7 is a conditional consequence of a
reviewed axis result, not work hidden in R1a/R1b or a requirement to finish all
experiments first. None of these small measurements earns `PASS_E3` or a live
effectiveness claim.


## Task 0 — Close Routing And Freeze The Small Question

**Files:** this plan and the current roadmap; eventual evidence under
`docs/reports/2026-09-08-orc-research-demonstration.md` (create only on execution).

- [x] Re-read current ES/refreeze status and coordinate with its active owner.
  Ollie explicitly selected prelaunch park and R1a entry work; the
  [roadmap hand-back](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#current-es-boundary)
  records the disposition. Frozen study bytes remain unchanged.
- [x] Record the owner-selected R1a resource envelope in the execution
  boundaries and manifest: cumulative monetary admission with finite recorded
  amendments, token/request effort metrics, agent-time and human oversight
  limits, and independently scoped preparer, author/adaptor, assessor, and
  unscored coordinator contexts. Preserve the superseded proposal and overruns
  as historical evidence rather than prospective stop rules.
- [x] Review the design against current public APIs. Classify each promised
  proof as already evidenced, to be demonstrated, or blocked; qualify
  existing-mechanism feasibility before Tasks 1–2 selection.
- [x] Define the preparation/measurement boundary: preparation qualifies the
  operation vocabulary, oracle, library, and components; then freeze cases,
  truth, acceptance, adaptation requests, comparison order, model/config,
  tools/context policy, and accounting before measurement. Preparation is not
  circularly gated on measured success.
- [x] Use one experiment-local input manifest, not a new platform schema.
  Before preparation allocation, record exact model/configuration, tools and
  context policy, pricing and metering/accounting method, role separation,
  caps, operation/input-based leaf policy, hidden/held-back access policy,
  counterbalancing policy, receipts, and intervention rules. Preparation then
  produces oracle/check digests, cases, truth, and concrete assignments; freeze
  those before measurement, not before permission to prepare them. Record no
  automatic successor selection from either utility-screen result. Manifest,
  runtime metering, and API feasibility are not completed by this amendment.

Entry checkpoint, 2026-09-09: the owner later approved replacing the
token/request stop ceilings with the existing USD 50 total-spend ceiling, and
the qualified native cost gate now enforces prospective per-request admission.
Task 0's routing/accounting/mechanism classification is therefore recorded in
the manifest and execution report under the approved dollar-cap recovery, while
preserving the earlier token-ceiling overrun as a historical failure rather
than relabeling it compliant. No research cases have been prepared or measured
yet.

**Exit:** clear authority for Tasks 1–2 and R1a's Task-4 report only after the
proposed amendment/budgets, exact roles/accounting, and existing-mechanism
feasibility are accepted; otherwise retain the plan as a draft. ES's
RICH-screen outcome is context, not a win gate.

## Task 1 — Qualify Execution And A Topology-Independent Oracle

**Read/reuse:**

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `workflows/examples/review_revise_design_docs.orc`
- `workflows/library/verified_iteration_drain/drain.orc`
- `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc`
- `orchestrator/workflow/trial/sdk.py` (`TrialRunOptions`, `run_trial_entry`)
- `tests/experiments/test_es_qa_placement_workflows.py`
- `tests/e2e/test_e2e_workflow_lisp_trial.py`
- `tests/test_workflow_run_ref_path_compile.py`

**Proposed additions, only after selection:** one experiment-local directory
`experiments/orc_research_demo/` containing `README.md`, `inputs.json`, a small
authored `trial.orc`, and local fixture assets; one owner test module
`tests/experiments/test_orc_research_demo.py`. Do not fork the frozen ES wrapper
or inherit its unrestricted provider configuration.

- [x] Add the smallest failing behavior test for a portable terminal-`trial`
  entry importing the existing four arms, with real local check execution and
  explicitly scripted providers/scorer inside the test harness. Use the
  independently scoped preparer context for setup and reserve author/adaptor
  and assessor contexts for their declared roles.
- [x] Implement only the fixture/wrapper needed for that test. Public SDK
  options have no mock/scorer injection API; keep substitutions in tests and
  label them. Do not patch correctness checks to always succeed.
- [x] Prove one genuine two-arm child-process/check-process run reaches a
  committed verdict through the public entry. Existing lower-level E2E helpers
  still prove committed verdict, sibling preservation, and resume. The owner
  smoke now reaches a committed scored verdict through the public SDK path using
  a labeled test-only packet-bound scorer substitution while preserving real
  exact-pin child runs and required-check subprocesses.
- [x] Add a known failing check control. The control must be committed before
  exact-pin child materialization; mutating the parent workspace afterward does
  not affect the child clones. If public execution cannot support the tiny proof
  without new runtime machinery, record the exact gap and stop that lane; do not
  invent a second executor.
- [x] Keep predetermined QA role sequences only for the fixed-arm regression
  subset. Add deterministic operation/input/context-based doubles for novel
  compositions; the same operation and inputs must not receive different
  answers merely because a different candidate called them.
- [x] Demonstrate on development examples that the behavioral oracle accepts
  two different correct structures and rejects a broken composition. It must
  check outputs/dependencies/control obligations, not a prescribed graph or
  literal prompt wording. Establish these proofs before assessment freezes;
  this is mechanism qualification, not a measured agent-performance claim.
  Qualification recovered through actual compiler/runtime executions of direct
  findings branching and findings → gate → branching, with separate rename,
  current-input missing-work/block, stale-input, and malformed-evidence controls.
  Main's demo/admission modules passed seven tests in40.92s; fresh independent
  review approved this development requirement in
  `experiments/orc_research_demo/evidence/oracle-final-review.txt`.
  Subsequent family integration passed28 combined tests in82.63s and received
  independent DEVELOPMENT acceptance in `evidence/family-final-acceptance.txt`.
  Separately prepared unseen requirements/truth/assignments and independent
  assessment freeze remain pending; development examples cannot be renamed
  into unseen assessment.

**Verify:** collect the new test module, then run its narrow selectors.
Existing reference selectors to characterize first:

```bash
pytest -q tests/experiments/test_es_qa_placement_workflows.py -k 'exact_four_arm_entries_compile or four_cell_trial_compiles'
pytest -q tests/test_workflow_run_ref_path_compile.py -k 'full_compile_admits_exact_effect_free or provider_diagnostic_routes or command_diagnostic_routes'
```

**Exit:** reproducible mechanism evidence, explicitly not scientific quality,
provider variability, or sandbox evidence. If the existing mechanism cannot
satisfy the proof without new runtime machinery, stop this lane and record the
gap; do not proceed by inventing a second executor.

## Task 2 — Original Construction, Reuse And Diagnosis Protocol

This section retains the original matrix and its historical incomplete cells;
the selected assisted development above is the current task. Any future
measurement follows the normal-session contract, not the old no-tools freeze.

**Files:** extend only the experiment assets and owner test module above;
write measurements to the execution report, referencing ordinary compiler and
run artifacts rather than introducing a parallel trace database.

- [x] During development preparation, the independently scoped preparer
  establishes component boundaries. First inspect public review/revise and
  drain procedures and current production compositions; QA's whole-arm
  exports are not the only reuse surface.
  Reuse existing interfaces where sufficient; permit one bounded
  experiment-local extraction only when the required boundary is absent,
  counting its setup cost. Preserve frozen ES sources and freeze the resulting
  library before assessment. The author/adaptor never receives hidden truth
  or held-back answers.
- [ ] Use the [session-pattern report](../reports/2026-09-08-orc-session-patterns.md)
  as development evidence. Identify underlying task/failure families, collapse
  fork/inherited and repeated-turn evidence, and distinguish current unmet need
  from resolved defects, visibility problems, deliberate decisions, and
  orchestrator-created friction. Record those distinctions in the existing
  input manifest/report, not a new corpus service.
- [ ] Reveal three previously unseen requirement cases. Construct and execute
  programs for review-to-selected-completion handoff, conditional judgment and
  disagreement handling, and multi-item continuation with a scoped policy
  change, using the design's qualified families. Prioritize review-to-completion
  handoffs and transfer to a non-orchestrator consumer; use the matched
  Python/native construction control where applicable. At least one case must
  concern a consumer other than maintaining this orchestrator, within these same three
  cases. Mined corrections are development data, not unseen assessments.
  Prefer the design's [adaptive scientific transfer](../design/orc_reuse_introspection_search_experiment.md#adaptive-scientific-transfer)
  for that consumer. Qualify existing native runner/scorer interfaces and
  represent their observations with operation-based leaves; do not rebuild
  scientific tools or launch a live training study for R1a. Record a fit or a
  named qualification gap, not success by substituting a simpler fixed chain.
  Choosing an existing whole arm is insufficient when it does not meet the
  case's behavioral obligations. Test three frozen scenarios per case.
- [ ] Within those scenarios, check meaningful pressure cases: a revised
  artifact reaches the selected next phase; unaffected accepted work is reused
  while materially changed dependencies invalidate the relevant review; and
  a scoped instruction is consumed at its intended decision boundary.
  Providers judge materiality/findings and ORC routes the recorded decision.
  Simulated boundary consumption is not proof of arbitrary live cross-session
  message delivery. Do not add a separate review, recovery, or steering matrix.
  For the scientific transfer case, use its existing three scenarios to test
  process success without valid scientific acceptance, pilot evidence calling
  for method reconsideration, and selective reuse after a relevant correction.
  Distinguish useful prior evidence from evidence admissible for the current
  comparison; neither identical hashes nor changed labels decide that alone.
  The scientific judgments are declared fixture observations here, not proof
  that a live provider would discover the cause or propose the remedy.
- [x] Before freezing cases, remove answer-bearing historical steering and
  later diagnosis-bearing document revisions from scored-agent context. Supply
  the same available observations and applicable pre-intervention contracts
  to both conditions. Keep all mined episode variants in development; use
  independently prepared cases for assessment. A declared requirement-change
  episode may reveal its change, but supplied causes or remedies are assistance,
  not evidence of independent discovery. No new corpus or schema is needed.
- [ ] Record correctness, construction/verification effort, glue, forks,
  interface edits, and predicted versus actual edit consequences. Classify
  library, language/runtime, authoring/documentation, and apparatus gaps.
  Do not modify the runtime/compiler to hide a failed expressibility case.
- [ ] Build one early matched Python/native construction-only control
  using ordinary idiomatic tooling and the same behavioral oracle. Its three
  scenario results are a feasibility comparison, not general superiority.
  Matched change/revision comparisons need later explicit allocation; they are
  not included in this three-scenario control.
- [ ] Retain the original matrix's unavailable three-consumer reuse result;
  do not rerun or replace that proxy as an ergonomic-reuse assessment. Review
  concrete `.orc` usage instead: discovering and understanding abstractions,
  parameterizing/adapting/composing them, and avoiding unnecessary glue, type
  conversions, forks or nonlocal edits. Use qualitative human/LLM judgment
  grounded in code and use context; leave the axis unassessed if that evidence
  is not credible. Behavioral tests establish correctness, not ergonomic value.
- [ ] Historical allocation only, not selected follow-up: three portfolio-wide adaptations independently
  from its baseline: provider-policy substitution, a typed evidence-contract
  change, and a bounded review/repair policy change. Each effort includes
  changing and verifying all three consumers; count shared edits once. Record
  six efforts and eighteen consumer checks, including all caller changes,
  verification, forks, metered input-plus-output tokens, requests, elapsed
  time, errors, USD, and human intervention. The primary adaptation metric is
  total metered tokens per condition, including cached input; do not double
  count reported reasoning/output.
- [ ] Seed six paired diagnostic cases, one per design category; retain a
  controller-owned truth manifest and event boundaries independently of
  whatever diagnostics the runtime emits. The preparer freezes truth before
  assessment. The preparer never scores its own hidden case. Scored
  author/adaptor/diagnoser contexts cannot see truth or held-back answers;
  the separate scoring assessor receives frozen rubric/truth and anonymized
  responses without condition identity.
- [ ] Compare ordinary source/log/result evidence with that same evidence plus
  structured compiler/run inspection. Assign two equivalent variants per pair,
  one per condition, with counterbalanced variant assignment and fresh-context
  order; score correct attribution and recovery decision, abstention, elapsed
  assessment time, token/request/receipt accounting, and confidently wrong
  answers, not error-message wording.
  Keep the six diagnostic categories unchanged: they assess orchestration
  attribution/recovery, not physical root-cause discovery. Both conditions
  receive the same available public hypotheses/judgments; structured views
  cannot be credited with scientific facts absent from the underlying evidence.
- [ ] Retain all twenty-four behavior-cell outcomes, eighteen reuse consumer
  checks, and twelve diagnostic assessments. Never count repeated deterministic
  checks as additional independent samples. Fixture success establishes
  scoped controlled agent-assisted behavior, not human performance, live task
  effectiveness, or autonomous closed-loop success.
- [ ] Preserve the historical exploratory thresholds: the old reuse proxy required at least
  20% lower median total adaptation/verification token effort with no extra
  regressions; diagnosis requires either one additional correct assessment of
  six or at least 20% lower median token effort without correctness loss.
  Neither diagnosis branch permits more confidently wrong answers.
  Disclose setup/payback in the same metric.

**Exit:** paired measurements, including unfavorable results and unavailable
measurements. Stop on the first exhausted ceiling or any missing independence
or metering proof; report partial evidence and named gaps. If fair diagnosis
assessment cannot be staffed inside the cap, report an untested utility claim
rather than substituting diagnostic coverage.

### Bounded prerequisite feasibility for expert-independent-3

Hold the prepared requirement/data baseline stable. Experiment P requires tasks
unseen by the assessed author against the development vocabulary; private
qualification does not create a demand for another novel case. Do not expose
private truth or qualification solutions as the scored library.

Main owns integration, runtime proof and freeze. Delegate bounded implementation
of explicit independent fixture binding and private qualification probes using
the existing compiler/runtime. Keep receiver dispatch, repeated judgment rounds,
queue progression and package review/repair control in authored ORC. Python
adapters perform one operation or evidence inspection, never a second executor.
Use one evaluator path for development and independent trusted inputs, preserving
the accepted leaf semantics and every existing caller. Private aggregate checks
must bind actual committed producers, output closure, cardinality and consumed
values; self-reported receipts and copied truth are not execution evidence.

Run bounded ordinary-route probes for receiver output, second-round count flow,
two-item execution and actual provider-policy/package-boundary handling. Check
distinct valid source structures and the concrete wrong-composition controls.
Record adapter/checker/setup cost and exact failures. A fresh independent review
then checks feasibility, exposure and library tailoring. Classify missing
prerequisites as apparatus, library, language or research-design friction and
state the warranted redesign/selection decision; do not relabel a simpler case,
abandon an entire axis or silently change runtime semantics. Existing allocation,
accepted development evidence and pending proposal selections remain unchanged.

## Task 3 — Separately Budgeted Agent Authoring And Self-Programming

**Files:** extend the same experiment assets, owner test module, and input
manifest. Invoke the installed Codex/OMP coding agent through its normal entry
point. Reuse existing task delivery, usage capture and evaluation helpers; do
not add a second agent loop in `authoring.py`. Use separate development working
copies rather than candidate commits in the user's working branch. No optimizer
or new authoring framework is selected.

- [ ] Obtain separate R1b selection and freeze all ceilings above, model,
  monetary cap, feedback exposure, intervention rules, and final-check reserve.
  Account for actual authoring calls; scripted leaf providers do not make this
  lane free. Without this allocation, Task 3 remains unselected.
- [ ] Use bounded preparation inside R1b to demonstrate one generated
  provider-workflow composition through ordinary compilation and execution
  with operation-based doubles and real checks. The current clone-path mode
  is effect-free; do not invent a mock SDK API or mislabel that route. Resolve
  any implementation/document discrepancy before measurement. A failed proof
  stops this lane, not unrelated R1a or R2 work, and selects no safety project.
- [ ] Freeze three agent episodes with fresh contexts, one per requirement
  family. Use the framework, not R1a solution source, as context. Designate a
  requirement-change episode and use the review-handoff family for the
  closed-loop objective/feedback episode; the third remains an authoring case.
  Reserve final unseen checks; do not let their answers guide revisions.
- [ ] Launch a normal coding session with applicable project instructions,
  tools and development feedback. Let it choose the composition, edit files,
  compile, execute and debug within the selected task budget. Retain meaningful
  initial/final versions and failed attempts through existing source/run records,
  not a new per-edit identity or certification process.
- [ ] Supply the selected objective or requirement change and normal
  development evidence; withhold only final assessment answers. The at-most-two
  objective-level revision milestones do not cap tool turns or debugging edits.
  In the closed-loop case, the agent chooses
  the orchestration edit from its goal and execution evidence; the controller
  does not prescribe a topology. Mere compile repair is scored separately.
- [ ] Let the agent choose a causal revision such as different review placement,
  context provision, or continuation policy without prescribing that edit.
  Score real changes in orchestration behavior. Text-only prompt edits against
  deterministic leaves cannot establish better planning/review judgments;
  live prompt-quality comparisons belong to separately allocated later work.
  A scientific-study context may exercise that same review-handoff episode,
  but the agent must choose a change to its executable orchestration, not
  merely edit a scientific configuration or paraphrase supplied steering.
  Scripted scientific decisions establish routing only; separately identify
  who supplied a diagnosis or replacement method.
- [ ] Distinguish candidate revision from a proposed objective/evaluator or
  design change. If evidence calls the premise into question, preserve the
  result and route reconsideration rather than force retries. A protocol change
  needs explicit amendment, a new comparison baseline, and fresh assessment;
  it is not an improved score under the old objective. No additional revisions
  or funding follow automatically from this branch.
- [ ] Record predicted change, complete program identity, actual behavior,
  unaffected obligations, human intervention, and all requests/tokens/time/cost
  receipts, plus first/final results. Structural distinctness is not behavioral
  improvement.
  Budget-exhausted episodes and first-version failures remain visible.
- [ ] Freeze each selected final revision before the held-back check. Do not
  repair against final-check answers. Classify authoring, feedback revision,
  and unassisted closed-loop evidence separately. An already successful program
  with no revision supplies authoring evidence only.

**Exit:** scoped evidence or a named failed prerequisite for each accomplishment,
with actual expenditure. No superiority, live domain quality, genetic-search,
or automatic R2/R3-selection claim follows. This lane is not conditional on a
positive reuse or introspection utility screen.

## Task 4 — Review Evidence And Choose Consequent Actions

**Files:** execution report and current roadmap; do not rewrite recorded
measurements after seeing the answer.

- [ ] Produce a report after R1a whether or not R1b is selected; later append
  separately identified R1b evidence. Review whole diff and evidence for
  contract compliance and simplicity. Separate mechanism, utility, and efficacy.
- [ ] Run narrow owner tests and one genuine public-entry integration smoke.
  For selected implementation changes, run the applicable broad gate in tmux
  as `pytest -q -n 16 --dist=worksteal`, after narrow checks. Report failures
  and environment limitations; do not weaken checks to obtain a green gate.
- [ ] Publish actual USD, total token effort, requests, elapsed time, human
  intervention, missing receipts, all failed/rejected cases, and maintenance
  added. Keep the original R1a thresholds with its original results, without
  using them as ergonomic-reuse criteria. Disclose setup and assistance;
  missing receipts are not zero and one shared author gives no independent
  per-language inference-cost comparison.
- [ ] Classify interventions by purpose and substantive contribution: status
  inquiry, deliberate decision, mechanical continuation, semantic correction,
  or change of objective/design. Report review churn, invalidated/reused work,
  and transfer results alongside quality and total effort. Fewer user messages,
  higher local metrics, and repairs to this orchestrator alone do not establish
  practical value or an ORC-specific advantage.
  For scientific transfer, also distinguish scientifically useful prior work
  from current-claim evidence, process completion from quality, and a provider's
  independent diagnosis from a supplied solution. Assess unnecessary reruns,
  lost useful evidence, justified method changes, and unsupported causal claims
  within existing outcomes; do not reward fewer checks at correctness's expense.
  Retained scientific artifacts demonstrate workload evidence reuse, not
  ergonomic reuse of `.orc`. Experiment A requires an assessment of actual
  abstractions and their usage; a portfolio-change test is not a substitute.
- [ ] Record supported-within-scope, adverse, inconclusive, or untested for
  each of the five axes separately from its recommended action. Use the
  [roadmap's axis lifecycle](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#axis-lifecycle--improve-or-retire-then-simplify):
  retain a useful scope, improve a named bottleneck, reconsider an implicated
  language/foundation assumption, or retire the unsupported scope and simplify.
- [ ] In the same report, identify each axis's retained use, observed limit,
  proposed causal remedy and re-evaluation, or retirement/cancellation targets.
  For inconclusive/untested work, specify the smallest uncertainty-resolving
  assessment or an explicit park with reopening evidence; do not invent a
  numerical test for an ergonomic judgment or infer impossibility.
  A positive demo alone is not a completed improvement program.
- [ ] Before declaring an axis blocked or prescribing abandonment, distinguish
  failure of today's encoding from failure of the intended capability. When a
  foundational assumption is implicated, compare credible local, type/language
  redesign, and alternative-foundation responses against the same user goal.
  Record the design principles challenged and the smallest proof that could
  distinguish the alternatives, rather than require today's checker/runtime
  to demonstrate the capability it prevents. Budget exhaustion is not disproof.
- [ ] Record encountered design-derived language limits in the same report,
  including the absence of unbounded recursion where relevant: owning rule,
  rationale, blocked use/workaround cost, and evidence for reopening the design.
  Compare iterative/delegated encodings with recursion or execution-model
  revision without assuming those encodings preserve composition/inspection.
  Keep per-run time/cost ceilings distinct from language expressiveness;
  Task 7 can investigate a justified limit without selecting its removal now.
- [ ] For any proposed follow-on, name its owner, finite resource ceiling,
  observable improvement criteria, relevant usage examples or fresh-case
  checks, stop rule, and simplification if it fails. Qualitative criteria are
  appropriate for ergonomics. Request separate Task-7
  selection; do not spend the remainder of an R1 budget on unplanned repair.
- [ ] Trace consequences for dependent work and the project foundation.
  Failure of reuse/diagnosis does not settle other axes; failure of autonomous
  revision can retain assisted authoring or non-agent search. A lost executable
  composition space does require narrowing or replacement of generated-program
  work. Recommend direct improvement, language/subsystem redesign,
  migration/reimplementation, or
  platform abandonment according to the roadmap's portfolio criteria.

**Exit:** evidence plus a concrete proposed improvement, retention, or retirement
decision for each assessed scope; untested scopes have explicit unresolved
questions and allocation/park recommendations. No outcome automatically approves
R1b, Tasks 5–7, EL-1, a general GA, or code deletion.

## Conditional Task 5 — Qualify One Live Task Family

**Starting assets:** the design's session-derived review/planning requirements,
including adaptive scientific planning using existing native runners/scorers;
alternatively `examples/demo_task_linear_classifier_port/` and
`orchestrator/demo/evaluators/linear_classifier.py` for hard-oracle repair.

- [ ] Select one family before candidate work. Prefer review/planning
  improvement if independent behavioral checks and blinded semantic assessment
  distinguish useful outputs from known defects. Freeze the assessment rubric,
  disagreement handling, and evaluators separately from candidate generation;
  approval wording and self-assessment are not ground truth. Otherwise propose
  the hard-oracle repair alternative and record why it is more evaluable.
  This replaces the mandatory scientific-first choice, not adds a second study;
  changing families after results requires a new protocol, not a hidden retry.
  Scientific planning is a context within that choice, not an additional
  mandatory family. Separately qualify scientific-judgment evaluation and
  orchestration behavior: deterministic leaf success proves only the latter.
  Use pre-intervention inputs without historical solutions; any live scientific
  execution and its resource needs must fit this separately approved protocol.
- [ ] For the repair alternative, establish a verified green Rust target
  against the independent Python reference; the unfinished seed is not a
  repair baseline. For review/planning, prepare independently assessed
  task/artifact cases outside the mined development episodes.
- [ ] Prepare twelve bounded episodes grouped by genuinely distinct task/defect
  families; prepartition adaptive/validation/sealed holdout sets. Keep a mined
  incident's forks, before/after artifacts, and near variants together. Qualify
  split sizes and evaluator sensitivity before proposing candidates. Neither
  repeated turns nor numerical reseeding count as independent tasks.
- [ ] Preregister one finite authored-arm study with fixed prompts, models,
  tools, objective, retries, and owner-approved cost/time/provider ceilings.
  Include at least three stochastic repetitions per candidate/task for initial
  noise characterization; these do not increase independent task count.
- [ ] Reserve the holdout allocation before adaptive spending. Publish a
  descriptive pilot only; twelve episodes cannot satisfy the trial design's
  powered-effectiveness requirements or its ≥30-independent-holdout floor.

**Exit:** qualified task/evaluator and affordable pilot, or stop. No live
execution until a separately reviewed bounded protocol is accepted. Further
domains, including NanoBragg, remain outside this one-family study. A fixed authored
catalog does not require successful R1b autonomous authoring. Apply Task 4's
consequent-action review to this evidence before proposing further development.

## Conditional Task 6 — Test Search And Representation Value

- [ ] Compare fixed reviewed candidates and full enumeration/random search
  before choosing an adaptive method. Four candidates normally warrant
  enumeration; do not build a GA to rediscover their maximum.
- [ ] Before expanding the candidate catalog, prove one source proposal can
  compile and run as an ordinary whole-workflow trial with the fixed provider
  configuration. Resolve the current bundle/clone-path integration and any
  governing-document discrepancy in that bounded implementation plan. Tool
  use remains delegated to agents/providers; no safety workstream is proposed.
- [ ] For an adaptive claim, freeze equal proposal/evaluation budgets, charge
  invalid proposals and diagnostic-repair calls, retain separate prompt-only
  and topology-only ablations, and select whole candidates on validation.
- [ ] Use the mined causal-improvement pattern as a candidate protocol:
  shortfall, proposed cause/change, comparable execution, evaluation, and
  retain/revise/reconsider. Start with ordinary pinned source revisions between
  runs; prove the generated-program integration rather than add runtime `eval`.
  Attribute interactions before treating a batch of plausible changes as an
  improvement; whole-program outcomes cannot be inferred by adding local scores.
  In a scientific context, candidate differences must concern orchestration
  such as diagnostic order, pilot/replication policy, or selective continuation.
  Network architecture changes, hyperparameter sweeps, and native optimizer
  iterations are workload behavior, not ORC program-space variation. Changing
  the scientific objective/evaluator starts a new comparison, not a fitness gain.
- [ ] Extend the early Python/native feasibility control for any ORC-specific
  comparative claim. Use a credible reusable Python/native
  control with the same workflow behavior, model/tools, evaluator, recovery
  obligations, and total engineering/operating accounting. This is a control,
  not a second platform product. For agent-authoring comparisons, match semantic
  requirements and budgets with idiomatic solutions; identical topology is
  required only when that is the particular representation-mechanics control.
- [ ] Include an agent using the same protocol as a skill as well as the
  reusable Python/native controller. Allocate these comparisons explicitly;
  they are not extra arms hidden in R1a's single construction control or R1b's
  three episodes. Preserve model/tool access, comparable requirements and
  budgets, and normal inspection tools; charge preparation and unsuccessful
  cycles for every condition. Assess new cases after development exposure.
- [ ] Power any confirmatory study, freeze its decision rule, and open a new
  sealed holdout once. Retain ORC for measured programming, reuse, diagnosis,
  self-programming, reliability, or search benefits; favorable topology alone cannot establish representation
  value. Stop expansion if simpler controls remain as useful at lower cost.

**Exit:** evidence-backed continue/narrow/reimplement/abandon decision. No
automatic self-modification, crossover machinery, or multi-domain claim. Apply
Task 4's review: a negative search result must also identify the simpler retained
policy and the search-only work to retire, not just stop new experiments.

## Conditional Task 7 — Improve Or Retire The Selected Scope

This task may follow any Task-4 review, including review of Tasks 5–6. It is not
a mandatory R4 stage or five parallel feature projects. Select one bounded
axis-specific change or closure at a time; investigate dependencies before
combining scopes. Reuse the execution report and roadmap for decisions, and
write a scoped implementation plan under `docs/plans/` only after the affected
contracts, consumers, remedy/removals, and verification are known. No speculative
file inventory, new framework, or permanent second implementation is prescribed.

- [ ] Obtain explicit selection and allocation for the reviewed consequence.
  Freeze its affected claim/use, baseline, causal hypothesis or retirement
  rationale, success/stop criteria, owner, and complete cost ceiling. Initial
  research budgets are unchanged and do not authorize this work.
- [ ] Inventory concrete callers, interfaces, configuration, derived evidence,
  docs, and pending features that the change affects. Mark what has independent
  consumers, what must migrate, and what becomes unnecessary. Never-built
  features are cancelled, not reported as deleted implementation.
- [ ] Choose a session-derived follow-on only for the observed need: extend
  proven review handoffs across distinct consumers; compose existing watchdog
  recovery with recurrence and verified progress; prove scoped steering is
  received/applied; or improve attribution of interacting candidate changes.
  These are alternatives, not four required subprojects. Reuse existing skills,
  stdlib, and evidence. Retire the extra controller if simpler tools cover the
  need; retain useful fixed workflows and unaffected accepted work.
  For demonstrated scientific-transfer value, test the same protocol on a
  distinct study and target observed diagnosis, pilot, or selective-reuse
  mistakes. Keep native numerical tooling; do not build a research platform
  from one episode. If the extra orchestration layer adds no repayable value
  after justified remedies and foundational alternatives have been assessed,
  retain the simpler skill/native procedure and retire only the unsupported layer.
- [ ] Treat growing glue, review churn, and local metric gains without task
  progress as reasons to reconsider the objective or decomposition before more
  retries. Let provider judgment propose the coherent alternative, including
  language/type redesign when implicated; the workflow records and routes it.
  Do not encode a fixed number of retries as a universal redesign verdict.
- [ ] For improvement, first choose the target from the reviewed alternatives.
  Add a regression when the bottleneck is behaviorally testable; assess ergonomic
  changes through actual before/after usage rather than a made-up test. Implement
  the smallest coherent remedy for that target, and remove displaced glue or
  paths. The target need not preserve today's type model or language principles.
  Introduce semantic changes only after the owning design/spec amendment and
  feasibility proof, not as hidden repairs to the old assessment.
- [ ] Compare the revised capability with the original and relevant simpler
  control using evidence appropriate to the claim: retained regressions for
  behavioral changes and independently prepared fresh cases for generalization
  or measured comparative claims.
  Account for implementation, onboarding, migration, assistance, operation,
  and maintenance; assess the chosen axis, not just compile/test counts. For
  ergonomic reuse, representative actual before/after usage and grounded
  qualitative review (including LLM-assisted review) are valid; do not require a
  numerical benchmark, fresh authored portfolio, or hidden-case exercise.
- [ ] For a type-system, language, or replacement-foundation investigation,
  explicitly challenge the implicated assumptions and test a discriminating
  case on the alternative. A credible obstruction can justify investigation;
  it does not require prior success in ORC. Before committing to the overhaul,
  demonstrate the useful capability and improved tradeoff, including unaffected
  obligations, migration, and ownership. Amend superseded design principles
  explicitly. A successful proof supports a separately scoped adoption decision,
  not automatic whole-project rewriting or two permanent implementations.
- [ ] For retirement, migrate or explicitly close affected consumers, remove
  unneeded experimental code/configuration/views, and cancel unsupported pending
  features. Keep facts/contracts used by retained capabilities and preserve
  scientific evidence. No unrelated ES, P/ME/OMP/EL-1 removal is implied.
- [ ] Run the narrow retained-behavior and routing checks; add a genuine
  integration/resume check when the selected change affects those contracts,
  followed by the applicable broad gate under the repo's tmux/pytest rules.
  Update discovery and any actual selectors; closed work must not remain
  silently pending or selectable. Review the actual diff and evidence.
- [ ] Close with measured improvement and explicit retained scope, or execute
  the approved fallback retirement/simplification. If that fallback was not
  selected, stop and request its scoped approval; do not infer deletion authority
  from failure. A useful original baseline can remain while its extension is
  retired. Further cycles require new evidence and allocation; unresolved
  uncertainty is recorded, not relabeled a success or a fatal flaw.

**Exit:** verified improvement, or verified scoped retirement/cancellation and
a simpler retained system. A replacement proof or unresolved prerequisite exits
with its explicit next decision, without claiming migration or cleanup complete.
