# Workflow Lisp Run Ref Expression Environments: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_run_ref_expression_environments.md](../../design/workflow_lisp_run_ref_expression_environments.md).

## Original delivery metadata

- Revised 2026-10-14 after independent design review: Bubblewrap sibling profile, named-workflow locus, §8.1-aligned recovery.
- Revised 2026-10-14 after F3 evidence: per-attempt delegated scope, one holder sandbox per child attempt with a host-channel spawner, the host clone as durable workspace with a tmpfs execution copy checkpointed after every leaf, hardened host reads, compile-time memory headroom, image mount points and host-side seeding (table "F3 deltas and review decisions").
- Revised 2026-10-14 (round 2) after independent review of the F3 revision: two-phase checkpoint header, holder death as `FAILED` without in-run retry, host-side time charged to the wall budget, descriptor hygiene and per-leaf relay, `setsid` leaves with deadlines, per-leaf scratch wipe, sized `/dev/shm` with read-only `/dev` and `/run`, agent-sessions authority dropped, F3b split (rows R1 to R10 in the same table).
- Revised 2026-10-14 (round 3) after the scoped re-review: durable `FAILED` terminal with its own proof and cleanup, image-only command closures, F3b-checkpoint narrowed to the copier, scope killed before the header is read, checkpoint failure as holder death, header durability, descriptor claim scoped to in-namespace processes, no checkpoint after timeouts (rows N1 to N9).
- Revised 2026-10-14 (round 4): named D5 amendment binding confined effect inputs (C2 tokens, C6 fills) to attempt snapshots so committed effects never diverge on candidate edits, closure refusal moved to dispatch before `started`, failed-terminal precedence over K4 and repair of the memo from the row, `setsid` check in the gate row, `escape_rejected` kept as the `FAILED` code (P1 to P5, in rows N2 and N4 to N9).
- Revised 2026-10-14 (round 5, final): dispatch refusals have no attempt record and their own proof variant, C4 precommit rehash limited to image pins, attempt snapshots content-addressed and allowance-checked at `started`, failed terminal row in the K4 amendment everywhere, token selection through the no-follow reader with recorded evidence maps, snapshot bytes verified before recomputation (Q1 to Q5, in the D5 row and the cited paragraphs).
- Amended 2026-10-14 after the F3b-channel gate passed (row F3b-1): spawner attribute drift (rlimits, nice, `oom_score_adj`) is a holder death, SysV IPC and mqueue carryover within one holder is accepted as candidate state, pid 1's internal eventfd and the daemon wording corrected, result broker open rules stated.
- Amended 2026-10-14 after the F3b re-review (rows F3b-1 and F3b-2): holders get a fresh session keyring and the shim's key-syscall filter, the drift comparison covers affinity, scheduling, I/O priority and `coredump_filter` and runs at post-leaf quiescence so drift fails the culprit's own attempt.
