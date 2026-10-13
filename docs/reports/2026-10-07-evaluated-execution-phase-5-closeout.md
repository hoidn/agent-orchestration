# Evaluated Execution Phase 5 Execution Record

Status: **Task 0 entry prepared; implementation pending**. This records entry to
the [Phase 5 plan](../plans/2026-10-07-evaluated-execution-phase-5-plan.md), not
parallel-map delivery or public qualification. The frontend/compiler cut and
all new Phase 5 tests remain pending; inspection predictions are not executed RED.

## Decisions And Current Baseline

The owner selected D1 **2.37** on 2026-10-12; W3 retains 2.36. D2 item cwd/path
contracts and D3 independent-prefix replay/checked representation retain their
original independent design acceptance at prepared-plan SHA-256
`9d2e02a8be309cd4339c59039fb2fb3b5ad8e1a563ca9a31f6b98a803b8873f0`.
The plan's contract delta owns the exact proposal and diagnostics; acceptance
does not establish implementation, read-back compatibility or runtime behavior.

On 2026-10-13, worktree `.worktrees/orc-consolidation-20261012` (W) is at
documentation closure `2feb6db7`, with product/test bytes qualified at
`bfd0f32411cec03241a9b2f54a6fcae118c75bd5`. The
[consolidation closeout](2026-10-12-workflow-lisp-consolidation-closeout.md) records
independent review and coordinator acceptance of bounded Tasks 0–4/Gates A–D:
268 integrated cases passed, the original 53 corpus outcomes/38 Built artifact
bytes are unchanged, one corpus case was added, and six retained families were
qualified. The full remains RED (275 failed, 23,511 passed); its cause taxonomy,
58-case canonical-interpreter PASS and separate five PASS/one XFAIL rerun retain
their limitations. None of this proves parallel execution or authorizes retirement.

Evidence directory **E** is `.worktrees/orc-consolidation-evidence-20261012`.
`E/phase5-current-entry.md` records actual owners, caller edges and source hashes,
SHA-256 `06a5a547af46a561f159b153b27d6a51030354130af2976d2532e95f2f7a801b`.
Its inventoried product hashes were rechecked unchanged at entry. Its earlier
wording that consolidation qualification blocks implementation is historical;
the final accepted consolidation report resolves that prerequisite.

Salient additional owners beyond the plan's initial table are shared
`contracts/closed_program/command_check.py` for command projection/control scope,
`workflow_lisp/lowering/command_transport_decisions.py` for continuation demands,
and the target registries in `workflow/validation.py` and
`workflow/run_ref/{config,bundle_transport}.py`. Frontend semantic identities in
`closed/names.py` and `procedure_typecheck.py` must preserve absent optional
fields, not merely JSON omission. `workflow/evaluated/capture.py` and its view
replay injection are later compatibility owners when prefix replay changes.
The inventory is a source-read record, not proof that those edits alone suffice.

## Reuse And New Proofs Still Required

**C5** and **C3** keep the physical locations and original receipt owners named
in the plan. C5 decisions/design-review records and all six named C3 Task 17
reports are present in the main checkout; this entry checked availability, not
a new review of their historical campaigns. Their original tested revisions,
hashes, scope and limitations remain unchanged. The delivered Phase 6a pilot
also remains baseline evidence. Reuse only unchanged contracts; none establishes
parallel-map feasibility, delivery or acceptance at the new target.

Current source still rewrites serial `ListMapEffectExpr`, rejects another pending
effect identity and requires global runtime/view replay order. Command/provider
launch and result paths still use the outer workspace. These are implementation
constraints, not failures newly demonstrated by this entry. Tasks 1–7 must prove
the new checked control and target/import/read-back gates; command/adapter/path
run-reference cwd behavior; independent interleaved prefixes and journal-ordered
validation; nested-map liveness and one-writer concurrent publication; and public
kill/resume/invalidate, retained-package and consumer/live qualification where
required. Existing serial REPL capture must remain source-free and read-only.

No new compiler test was collected or run, no concurrent runtime was launched,
and no new cwd/replay/concurrency proof is claimed. Phase 6b migration and
Phase 7 retirement gates remain unchanged.
