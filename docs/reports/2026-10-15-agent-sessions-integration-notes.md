# Agent Sessions integration notes — 2026-10-15

This is a merge handoff, not another contract or qualification record. The
`feat/agent-sessions` worktree started from `0c156966`; the main checkout has
advanced independently to `23e6eed6` and carries other sessions' uncommitted
documentation amendments. Fast-forward-only integration is no longer possible.
Do not merge or overwrite that working tree from this note. The coordinator
must reconcile the committed branch and preserve the unrelated amendments at
the separately authorized integration step.

The branch updates the existing PQ-1 section, roadmap paragraph, versioning
rows and agent design. Agent-specific discovery rows exist only in main's
uncommitted amendments. They are deliberately not duplicated in the branch's
index, capability matrix or design catalog. Apply the following exact
replacement text to those main amendments during integration, with paths
relative to the indicated document.

## `docs/index.md`

Replace the fast-triage row headed `Design stable agent instances across interleaved provider calls`:

```markdown
| Use stable agent instances across interleaved provider calls | [Agent Sessions](design/workflow_lisp_agent_sessions.md), [PQ-1](plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) and [qualification evidence](reports/2026-10-14-agent-sessions-pq1a-qualification.md) | First slice implemented at 2.38: two agents on Claude and Codex in `design_review_execute_agents.orc`, with per-turn typed memo commits, recovery, C8 guards and instance views. PQ-1a deterministic proofs and bounded adapter smokes are recorded; the separately authorized clean and failed/resumed acceptance comparison (PQ-1c) has not run. The `reviewed_change` coder variant remains future. |
```

In the existing `Workflow Lisp Provider Prompt Queue` catalog entry, replace its `Use this when` line:

```markdown
**Use this when:** Reviewing retained transport/recovery analysis. [Agent Sessions](design/workflow_lisp_agent_sessions.md) supersedes the queue surface for first delivery; [PQ-1a](reports/2026-10-14-agent-sessions-pq1a-qualification.md) records deterministic and bounded real-adapter smoke evidence for the implemented 2.38 first slice. The clean and failed/resumed acceptance comparison (PQ-1c) and second consumer slice remain future; portable context, Q5 and existing phase dependencies are unchanged.
```

## `docs/capability_status_matrix.md`

Replace the row headed `Stable agent instances and interleaved session turns`:

```markdown
| Stable agent instances and interleaved session turns | Implemented at 2.38 (admission, runtime, C8 guards, views) | Opt-in bounded first slice; acceptance comparison pending | [Agent Sessions](design/workflow_lisp_agent_sessions.md); [PQ-1](plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) | [PQ-1a qualification record](reports/2026-10-14-agent-sessions-pq1a-qualification.md): deterministic mechanism/consumer proofs and bounded Claude/Codex adapter smokes; no real-provider consumer comparison | `workflows/examples/design_review_execute_agents.orc` | Run-scoped identity, exclusive sequential continuation and a typed memo commit per turn. The two-agent design/review/revise/execute first slice is implemented; PQ-1c clean and failed/resumed comparison requires separate owner authorization. The `reviewed_change` coder variant remains a future second slice with its turn shape selected then. |
```

Replace the adjacent historical queue row (rather than retaining this branch's old planned-queue row):

```markdown
| Workflow Lisp sequential native-session turns / `prompt-queue` | Superseded for first delivery | No; no queue syntax or sugar selected | [Historical queue analysis](design/workflow_lisp_provider_prompt_queue.md); [Agent Sessions](design/workflow_lisp_agent_sessions.md); [PQ-1](plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) | Native transport/recovery obligations are incorporated into the one [PQ-1a record](reports/2026-10-14-agent-sessions-pq1a-qualification.md) of agent turns | The future coder variant of `experiments/orc_vs_single_call/workflows/reviewed_change.orc` routes to Agent Sessions; turn shape selected then | Completed turns use ordinary memo commits under E3; only the pending individual turn needs scoped K4 recovery. No queue-specific progress journal or second coordinator is selected. Portable context, Q5 and existing phase dependencies remain unchanged. |
```

## `docs/design/README.md`

Replace the row for `workflow_lisp_agent_sessions.md`:

```markdown
| [workflow_lisp_agent_sessions.md](workflow_lisp_agent_sessions.md) | Stable run-scoped agent identity and interleaved native-session turns | First slice implemented at 2.38; PQ-1a evidence recorded; PQ-1c pending | Opt-in bounded first slice | Four typed design/review/revise/execute commits on two conversations in `design_review_execute_agents.orc`. [PQ-1](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) owns selection and the single [qualification record](../reports/2026-10-14-agent-sessions-pq1a-qualification.md). The real-provider acceptance comparison needs separate owner authorization; the `reviewed_change` coder variant remains future. Recovery/invalidation limits remain explicit and distinct from immutable Context. |
```

Keep main's historical queue row, which already labels the queue superseded
and routes to Agent Sessions; do not restore this branch's old `Proposed; PQ-1 pending` row.

## Overlapping maintained documents

- In `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md`, use
  this branch's complete `PQ-1: Sequential Native-Session Turns` section as
  the exact replacement of main's selected-but-pending PQ-1 amendment.
  Preserve main's unrelated authoring/checked-evaluation additions. The final
  status is first slice implemented; deterministic proofs and bounded adapter
  smokes recorded; PQ-1c not run; second slice future.
- In `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`,
  use this branch's paragraph beginning `Native sequential turns are separately
  recorded as` through `the executable core, or the early migration pilot.`
  as the exact replacement of main's selected-but-pending paragraph. Preserve
  its unrelated AA-1/CE-1/EL-1 amendments. No executable manifest or selector
  changes: no tranche count, ready/pending/completed count or active-run
  selection changes are made by this documentation update.
- In `specs/versioning.md`, retain this branch's two 2.38 rows and their
  qualification pointers while preserving main's unrelated provider-delivery
  rendering amendments.
- Main's uncommitted result-delivery rendering uses `file/2`, while this
  branch's shared `orchestrator/workflow/evaluated/providers.py::FILE_DELIVERY_NAME`
  currently selects `file/1`. Reconcile that shared constant and its
  `DELIVERY_SELECTORS` entry with main's rendering implementation together, so
  ordinary and agent turns select the same current rendering. Preserve
  historical selector/digest replay; a versioning-doc change alone does not
  perform that integration.
- In `docs/design/workflow_lisp_evaluated_execution.md`, retain this branch's
  agent-turn recovery/invalidation amendments, including the paragraph under
  the memo-record table naming `run_ref` and target-2.38 `agent_turn` as
  coordinators, and the C8 row naming both committed and attempt-history
  refusals. Preserve main's independently advanced run-reference amendments.

For that design's §9.2 performer table, set the column heading to
`First release (2.35)`. Replace main's `Later proposal` agent row with this
exact branch row:

```markdown
| Run-local agent allocation and sequential native-session turns | No; implemented at 2.38 | Ordinary non-coordinator allocation with its own checked class; existing session/turn transports behind one bounded `agent_turn` coordinator | [Agent Sessions](workflow_lisp_agent_sessions.md) commits each typed turn separately; E3 reuses the prefix and pending-turn recovery uses the scoped K4 exception (§9.3). [PQ-1a](../reports/2026-10-14-agent-sessions-pq1a-qualification.md) owns deterministic proofs and bounded real-adapter smoke evidence; `prompt-queue` is superseded for first delivery, and the separate acceptance comparison remains pending |
```

Replace the immediately following admission paragraph with:

```markdown
At first-release target 2.35, a program using a class marked later is refused
at build (§1.1). Target 2.38 additionally admits the bounded Agent allocation
and turn row above; other exclusions remain target-aware. Older executable
entries are retired; no old-route fallback is available.
```

Compare main's untracked duplicates against the integrated tracked files before
removing any duplicate. Equality must be checked at integration time; this note
does not assert current or future equality or authorize deletion based on names.

The qualification record owns smoke receipts, exact verification revisions and
coverage limits. This note neither authorizes paid comparison runs nor changes
code review findings or integration permission.
