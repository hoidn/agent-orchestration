# Provider Context Values — Design Drafting Plan And Simulation

Status: documentation-only work plan; does not select implementation or research expenditure.

## Scope And Approach

Clarify the consequences of explicit, rebindable provider context and draft
[the proposed design](../design/workflow_lisp_provider_context_values.md).
Reuse provider invocation, structured-value transport, generated storage, and
prompt composition. Do not introduce a memory service or another workflow
executor. Immutable context makes honest native checkpointing, conversion
fidelity, and composite result publication harder than forwarding a session ID.

1. Inspect current provider/session, prompt, value, compiler, and resume owners.
2. Record the comparative simulation below before drafting the proposal.
3. Draft semantic contracts, language/frontend consequences, architecture,
   alternatives, feasibility prerequisites, and acceptance scenarios.
4. Add clearly proposed-only documentation routing. Preserve concurrent edits;
   do not amend normative specifications, roadmap selection, or active studies.
5. Independently review the consequential design where an agent is available;
   inspect the final diff and run documentation/link checks.

Implementation requires a separately accepted design and reviewed component
plan. This task does not authorize live provider experiments, runtime edits,
workflow migration, or a commit.

## Inputs And Exclusions

Inputs are the current working-tree provider contracts, provider lowering,
prompt calculus, structured-result and resume contracts, and the user's
snapshot/transform/fork/bind proposal. Concrete source pointers are recorded in
the design's Context And Authority section.

Excluded: private model reasoning, hidden research cases, scored outcomes,
provider journals outside the task's scope, and the concurrent OMP study's
intermediate answers. No provider was asked to simulate success. The traces
below are an analytical execution of proposed rules, not recorded runtime runs.

## Compared Versions

- Baseline: current working-tree `specs/providers.md`, `specs/io.md`,
  `orchestrator/workflow_lisp/expressions.py`, and
  `orchestrator/workflow_lisp/lowering/effects.py`, inspected 2026-09-08.
  The checkout is dirty; this comparison does not equate it with committed HEAD.
- Candidate: `docs/design/workflow_lisp_provider_context_values.md`, specifically
  explicit context input and immutable captured context output on the existing
  `provider-result` boundary. The trace fixes the proposed semantics before the
  draft is written; it supplies no claim that the candidate syntax runs today.

## Scenario Setup

- Target: one completed investigation has two tool-result observations, an
  unresolved question, and an artifact reference. Two subsequent approaches
  should receive the same captured investigation without each other's answers.
- Hard: the investigation depends on a live interpreter variable and a tool
  result that the exporter cannot represent. The next provider has neither.
- Simple: a one-shot classification consumes one short supplied document;
  no subsequent call uses its conversation.

## Evidence Ledger

| Fact | Classification | Basis |
| --- | --- | --- |
| Fresh session-handle publication exists, but is separate from the typed result | observed | `:session-artifact` parsing/lowering and its direct tests |
| Existing Q3 prompt evidence is content-free, not exported conversational content | observed | `specs/providers.md` and prompt-calculus contract |
| Required capture and result must commit as one caller-visible value | specified | Candidate publication contract |
| Immutable input permits independent conversational branches | specified | Candidate input/attempt isolation contract; real adapter proof still required |
| Preserving relevant observations may reduce manual handoff work | inferred | Target scenario; requires comparison against ordinary skill/SDK handoffs |
| Context transfer cannot recreate external interpreter state | specified | Candidate state boundary, independently testable with separate workspaces/processes |

## Deterministic Workflow Delta

The candidate adds a dataflow input and an optional runtime-owned output to the
same provider boundary. It does not schedule tool calls, recreate a workspace,
add an implicit loop, choose a provider, or change result validation. Export,
storage reads, binding, and summarization are explicit effects when they do I/O;
operations on already materialized content are ordinary pure computation.

## Simulated Event Log

Each row gives consumed state, decision/output and rationale, produced state,
and next route. `D` means deterministic under the specified contract; `J`
means provider judgment, whose outcome is not assumed.

| Case/version/step | Input → decision and rationale → produced state → next route | Confidence / assumption |
| --- | --- | --- |
| Target / baseline / 1 | Investigation task → provider investigates (J) → validated answer plus optional session handle → handoff | High confidence in available mechanism; answer quality unknown |
| Target / baseline / 2 | Answer, artifacts, author-selected observations → author/agent constructs handoff → explicit packet → two fresh calls | D for delivery, J if summarization is used; omission risk is unresolved |
| Target / baseline / 3 | Same packet → two agents explore (J) → separate results → comparison | Already achievable; no claimed impossibility without ORC |
| Target / candidate / 1 | Investigation task and capture request → adapter captures settled exposed history (D) → validated result/context pair → branch | Assumes exporter covers the observations and records omissions |
| Target / candidate / 2 | Same immutable context twice → adapter binds independent destinations (D) → two child continuations → exploration | Requires adapter-level independence proof, not two uses of a mutable session ID |
| Target / candidate / 3 | Equal inherited history plus different tasks → agents explore (J) → separate results/contexts → comparison | Quality improvement unknown; each sees shared prior beliefs, not independent evidence |
| Hard / baseline / 1 | Answer referencing interpreter variable → handoff omits live state → destination lacks it → reconstruct or fail | High confidence in missing external state; reconstruction cost unknown |
| Hard / candidate / 1 | Capture request → exporter reports unsupported tool event (D) → no complete-context claim → explicit conversion or failure | Required behavior; an implementation that silently drops it falsifies the design |
| Hard / candidate / 2 | Explicit lossy projection plus live-variable reference → destination receives declared partial history (D) → state still absent → recreate from artifacts or stop | Context does not solve this case; a separate environment transfer would be needed |
| Simple / baseline / 1 | Short document → classify (J) → validated scalar → done | One ordinary provider call |
| Simple / candidate / 1 | Same call with no context/capture clauses → unchanged validation → same scalar contract → done | D compatibility requirement; no mandatory storage/export cost |
| Simple / candidate / 2 | Counterfactual opt-in capture → extra export/storage → unused context → done | Added overhead without benefit; do not migrate this consumer |

## Decision Rationale

The target benefit is removing repeated orchestration of captured evidence and
making its selection/lineage program-visible. The hard case prevents conflating
conversation with execution state. The simple case requires opt-in capture.
Two bindings are not a proof of better reasoning or statistically independent
evaluation. Those remain empirical questions.

## Comparison

Unsupported history can be diagnosed at capture/bind instead of surfacing later
as an unexplained model error. Scope is preserved only if missing material is
reported, not silently dropped. The target retains three logical stages; no
iteration reduction is claimed. Runtime assembly removes model-authored
transcript boilerplate but adds content storage, conversion records, and an
atomic publication obligation. Expected review focus is fidelity, branch
independence, compositional carriage, and total cost—not checklist completeness.

## Assumptions And Falsifiers

- If required provider content cannot be exported, portable capture is not
  proven; explicit selected-content capture may still be useful.
- If a native destination mutates its source checkpoint, native fork is not
  supported by that adapter, even when its CLI has a command called resume.
- If a small skill/SDK packet gives equivalent reuse and diagnosis with less
  total work, do not claim this design creates an ORC-specific advantage.
- If generic records, collections, or returns obstruct the dataflow, test a
  principled language/transport repair before narrowing the feature to roots.

## Regression Risks

Old prompt contracts being treated as current instructions; dangling tool-result
references after selection; sibling history leakage; capture failure publishing
only half the pair; replay mutating an old native session; serializing context
descriptors as prompt text without their content; and context capture becoming
mandatory overhead for unaffected calls.

## Recommendation

`ADOPT_NARROWLY`: adopt the direction for a proposed design and bounded
feasibility work, not implementation approval or effectiveness claims. Preserve
the full compositional contract while limiting the initial number of adapters
and operations. Resolve the explicit prerequisites before selecting a build.

## Verification Record

- Independent read-only review found one material scope issue: runtime-selected
  provider identity is not currently supported by the frontend. The draft was
  corrected to use declared provider externs initially and name dynamic dispatch
  as separate optional foundation work. The reviewer found no other material
  conceptual/architecture or overengineering issue; this is not implementation
  approval.
- Three narrow documentation-routing selectors passed (`3 passed in 1.24s`).
- Full routing module passed in tmux using `pytest -q -n 16 --dist=worksteal`
  (`71 passed in 3.94s`, exit 0). Output:
  `/tmp/orc-context-doc-check.o3Ywxa/pytest.log` (local, non-durable test evidence).
- All 25 relative Markdown links in the two new documents resolve; scoped
  whitespace checks passed, including explicit checks of the untracked files.
- No executable behavior changes are part of this plan. Runtime/provider smoke
  checks and effectiveness experiments belong to a later implementation, not
  verification of illustrative, explicitly unavailable syntax.
