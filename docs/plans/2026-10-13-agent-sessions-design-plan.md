# Agent Sessions Design Drafting

Scope: draft a principled design on upstream `main` for two stable runtime
agent instances, interleaved native-session turns, and a typed result per
turn in `design_review_execute.orc`. This selects no implementation or DSL
version and authorizes no live-provider experiment.

Approach: extend the existing provider/session and evaluated-execution owners;
keep mutable session identity distinct from immutable provider Context values.
The main tradeoff is stricter recovery and invalidation for conversations that
cannot rewind or fork.

- [x] Draft identity, authoring, lifecycle, persistence, failure and
  compatibility contracts, with explicit feasibility prerequisites.
- [x] Obtain independent architecture review and resolve findings.
- [x] Add narrowly scoped discovery links; verify links and inspect the diff.

Deliverable: [Agent Sessions](../design/workflow_lisp_agent_sessions.md).

Independent architecture review passed after tightening C8 invalidation to
cover dispatched, advanced or uncertain agent attempts started after the cut,
including uncommitted attempts with undeclared file dependencies. The public
workflow boundary and opaque-reference rules were also clarified.

Coordinator verification: 14 local links resolve, all named existing module
paths exist, and scoped whitespace checks pass. Each discovery index received
one proposed-capability row; pre-existing edits were preserved. Local review
and verification receipts: `/tmp/agent-sessions-design-20261013-aidl07k4/`.
This is documentation review, not runtime qualification. No runtime code,
workflow, paid-provider invocation or implementation target was changed;
native continuation and recovery still require the design's feasibility proof.

## Review-Driven Revision

The preceding review covers the first draft only. The subsequent user review
requires explicit K8/C8 classification, the frontend runtime-reference
exception, one native-turn substrate shared with the prompt-queue proposal,
and clearer recovery, replay and operability boundaries. The user's tmux
observation requirement is included in this revision.

- [x] Resolve the architectural feedback in the proposal, recording any
  deliberately unadopted recommendation and remaining selection questions.
- [x] Reconcile discovery and related proposed-design routes without changing
  normative behavior or assigning a roadmap owner/version.
- [x] Independently review the revision and verify its scoped diff and links.

Revision decisions: committed agent turns use existing K8/C8 coordinator
protection; only uncommitted advances need the agent-specific invalidation
guard. The proposal explicitly requires a versioned exception to frontend
§8.8. Agents and queues share one native-turn coordinator and adapter
qualification. Queue syntax remains a pre-selection decision: agent calls
with intermediate typed results are not exact sugar for the queue contract.

An explicit resume may replace an uncommitted first-turn candidate after
quiescence, reconciliation and durable abandonment, accepting repeated tool
effects without repeating another agent's committed work. Later conversation
turns cannot reset native history. The document now includes recovery costs,
inline committed continuation proof, worker-local admission prerequisites,
open selection questions and two derived read-only tmux views.

Independent rereview found one additional memo-state conflict. The correction
keeps reconciliable attempts pending, permits recovered proof to commit the
original ordinal and orders abandonment before failure closure and retry.
The reviewer then returned PASS with no remaining actionable findings.

Final coordinator checks: 24 local links and 19 existing module paths resolve;
scoped whitespace checks pass. The related queue design received one
reciprocal paragraph and each discovery row states that no roadmap selection
owner is assigned. Pre-existing unrelated edits remain outside this revision.
Review and verification receipts:
`/tmp/agent-sessions-review-revision-20261013-0a0su49g/`.
No runtime tests or provider calls were run for these documentation changes;
native adapter feasibility and implementation selection remain pending.

## First-Delivery Surface Consolidation

The owner's subsequent decision supersedes the preceding open queue-syntax
choice: cover sequential native turns through `agent`, retire `prompt-queue`
as a first-delivery surface, and add no sugar now. Each turn commits to the
ordinary memo under E3; only a pending individual turn needs the scoped K4
refinement. PQ-1a remains the single qualification record for that mechanism.
This gives up one effect identity for the whole sequence; it selects no
implementation target or live-provider experiment.

- [x] Revise agent/queue designs, ordinary allocation versus coordinator-turn
  classification, evaluated C8/native-turn routing, PQ-1 and context cross-links.
- [x] Update discovery/status rows and retain the queue document as historical
  transport/recovery analysis, without introducing another selection owner.
- [x] Obtain independent review and check scoped links, references and diffs.

The accepted revision makes allocation an ordinary effect with its own checked
class and reserves coordinator/K8 treatment for turns. C8's explanation now
covers coordinators generally while retaining the first release's `run_ref`
admission. The frontend exception still cites the runtime-closures boundary.
PQ-1 now owns Agent qualification and pending implementation selection for
the designer/reviewer and coder consumers. Existing procedures may compose
statically resolved prompts; no runtime prompt-reference list is admitted.

Independent review returned PASS after clarifying that a typed prompt can
supply the result contract when the literal `:returns` clause is omitted.
Only a turn without any typed result contract remains outside this proposal.
Coordinator verification checked 48 local links, scoped whitespace, unchanged
K4 text, and preserved queue/PQ-1 headings and anchors. Ten documentation
files changed relative to this revision's baseline; unrelated edits remain.
Evidence: `/tmp/agent-queue-retirement-20261013-71uojqkz/`.

Routing stays at one pending, consumer-conditioned PQ-1 entry with the same
three steps and no additional phase or prerequisite. No executable PQ-1
manifest/selector was found in the scoped state/workflows/scripts search.
No workflow source, runtime, active run state, implementation target or provider
was changed; no runtime tests or provider calls were run. Adapter feasibility
remains an open prerequisite, recorded once under PQ-1a.

## Owner Selection (2026-10-14)

The owner's explicit PQ-1 selection, taken on 2026-10-14 after the native CLI
probe, closes the drafting work above without reopening any completed step. It
is recorded in the design, the
[PQ-1 entry](2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns)
and the discovery rows.

| Decision | Selection |
| --- | --- |
| D1 exclusivity | Runtime-owned: the writer lock and one active turn per agent prevent internal appends; a pre-append native-head check against the recorded predecessor position refuses `agent_session_diverged`. Native active-writer exclusion is defense in depth; the external check-then-append window is a documented operator limit |
| D2 adapters | Both in the first slice: Claude session transport from scratch (fresh/resume commands, `session_support`, native-store accumulator with position/completion evidence) and the existing Codex accumulator/fresh-resume template extended with native position/completion evidence. Ordinary fresh calls on either provider unchanged |
| D3 consumer | First slice: the opt-in two-agent `design_review_execute` variant, designer `Agent` on Claude (A1 draft, A2 revise) and reviewer `Agent` on Codex (B1 review, B2 execute), four typed results, current models/effort/timeouts kept. Second slice: the `reviewed_change` coder variant (coder `Agent` on Claude, independent fresh Codex reviewer, final `Change` preserved), coder turn shape selected then. Mechanism proofs use deterministic adapters regardless of consumer |
| D4 target | New additive evaluated target 2.38; 2.35/2.36/2.37 unchanged, Phase 5 gates independent |
| D5 amendments | Frontend §8.8 exception, evaluated §8/§9.3 K4 agent-turn exception and C8 checked coordinator classification, as written in the design; each an admission obligation with its own spec change, fixture and recovery proof |
| D6 tmux | One read-only view per agent instance across all its turns; the same agent twice shows in the same view. The observability amendment is in the first slice |
| D7 native store | Provider default home (`~/.codex`, `~/.claude`); no per-run home or credential provisioning; locators are provider UUIDs |
| D8 real providers | One bounded, receipt-backed smoke per admitted adapter (Claude and Codex in the first slice) is in plan scope; the acceptance comparison is authorized separately by the owner |

PQ-1a stays the single qualification record and becomes a gate inside the
implementation plan, intended at
`docs/plans/2026-10-14-agent-sessions-implementation-plan.md` (not yet
written). Nothing is implemented, qualified or tested by this selection; no
runtime, workflow source, spec or provider configuration changed.
