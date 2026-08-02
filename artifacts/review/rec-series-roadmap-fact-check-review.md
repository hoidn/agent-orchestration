# REC-Series Roadmap Fact-Check Review

- **Verdict:** `APPROVE` — zero wrong citations, zero contradictions
- **Reviewer:** independent read-only fact-check subagent (`RecFactChecker`),
  spawned 2026-08-01 in the drafting session
- **Subject:** the pre-incorporation draft of
  `docs/plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md`
- **Disposition:** all five advisories incorporated into the revision that
  entered commit `27c71084`
- **Provenance note:** delivered in-session on 2026-08-01 and persisted to
  this artifact afterward; a concurrent session, unable to observe the
  delivery, temporarily recorded the review as lost/waived.

## Findings (31 total: 25 CONFIRMED, 5 ADVISORY, 1 UNVERIFIABLE)

### Exemplar `workflows/experiments/repository_task_pilot/task_loop.orc`
1. CONFIRMED — file exists at the stated path.
2. CONFIRMED — exactly 978 lines.
3. CONFIRMED — `(:target-dsl "2.20")` at line 3; corroborated by
   `docs/reports/2026-07-27-q4-binding-decision-brief.md:67-69`.
4. CONFIRMED — exactly 7 `provider-result` callsites (lines 90, 143, 201,
   271, 335, 429, 618); "5-8 provider-call pipeline" consistent (min 5, max
   8); forensics report records the viable ORC arm used 7.
5. CONFIRMED — exactly 12 `after-*` defworkflows.
6. CONFIRMED — `fix-stage` (lines 391-407) declares exactly 16 parameters.
7. CONFIRMED — it is the frozen lean-pilot ORC treatment
   (`docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md`
   lines 780, 916-918, 1542; Task-7 readiness amendment lines 195-198).

### Drafting guide `docs/lisp_workflow_drafting_guide.md`
8. CONFIRMED — §17 documents `loop/recur` with `:max` and the verbatim rule
   "bounded iteration or explicit termination proof".
9. CONFIRMED — §17.1 `loop-state` typed local carrier.
10. CONFIRMED — §13.2 `review-revise-loop` (line 2077) and §13.6
    `backlog-drain` (line 2179).
11. CONFIRMED — §17.2 target-2.18 bounded `list/map-effect` with explicit
    `:max`; verbatim "…and unbounded traversal remain outside this
    surface"; typed exhaustion matches the draft's REC1 constraint 3.

### `specs/index.md`
12. CONFIRMED — versions extend through 2.25.
13. CONFIRMED — `repeat_until` v2.7 (`specs/dsl.md:180`) with exhaustion
    outputs v2.12.
14. CONFIRMED — out-of-scope list names while loops with the
    v2.16/v2.17/v2.25 nodes as the only bounded exceptions (lines 28-35,
    74-80); draft correctly scopes them as bounded-concurrency exceptions.
15. CONFIRMED — v2.0 "stable internal step identities".

### E-series roadmap
16. CONFIRMED (rule text) + ADVISORY (location) — the no-two-active-plans
    concurrency rule exists verbatim (lines 1885-1887) but sits in the
    historical-reference portion; suggested citing it by section name.
    [Incorporated: the revision names "the E-series roadmap's Concurrency
    And Shared-Surface Rules section".]
17. CONFIRMED — E5 no-smuggling wording and "horizon marker, not scheduled
    work" borrowed accurately.
18. CONFIRMED — accepted E2 plan owns compiler IR/lowering/persistence
    surfaces (Task 5 selected at review time).

### Superseded experiment design
19. CONFIRMED — `R1`/`R2` are PtychoPINN replay task IDs
    (`2026-07-23-orc-vs-one-shot-experiment-design.md:270-271`), grounding
    the `REC` naming-collision rationale.
20. CONFIRMED — "superseded" is accurate (lean-pilot design line 12
    records the supersession).

### Link resolution from `docs/plans/`
21. CONFIRMED — all six relative links resolve (forensics report, frontend
    specification, design principles, drafting guide, P-series roadmap,
    superseded experiment design).

### Recorded-assumption claims
22. CONFIRMED — M2 persistence (substrate maintenance track §M2; E-roadmap
    prerequisites; E2 plan "obeys M2 persistence").
23. CONFIRMED — E1 certification via the ordinary full compiler (E1 plan
    lines 556-558, 788; `specs/versioning.md` v2.24; trial-runs design
    line 594).
24. CONFIRMED (paraphrase) + ADVISORY — E2 exact cost recording and
    accounting parity are recorded properties; "cost-honesty" was the
    draft's coinage. [Incorporated: recorded vocabulary used.]

### Contradiction sweep
25. CONFIRMED — no capability-status-matrix contradiction (`loop/recur`
    Implemented-bounded, `review-revise-loop` Library, `backlog-drain`
    Library, 2.18 list traversal Implemented; no recursion row exists).
26. CONFIRMED — "closed pure-expression operator surface"
    (frontend specification line 1515).
27. CONFIRMED — "precommitted budgets and per-step accounting" grounded
    across `specs/acceptance/index.md:136-140`, `specs/dsl.md:181,897`,
    `specs/versioning.md` v2.25, `specs/state.md:32`.
28. ADVISORY — "adverse-evidence context" phrasing was the draft's own,
    not the forensics report's. [Incorporated: neutral phrasing.]
29. ADVISORY — REC2' "supervisor re-entry pattern" is a grounded
    characterization, not a named pattern; suggested citing §13.3
    `resume-or-start`, §13.6 `backlog-drain`, and the run watchdog.
    [Incorporated.]
30. UNVERIFIABLE — the session-level owner-direction status claim; not
    independently checkable in-repo; non-blocking.
31. ADVISORY (minor) — DSL-level `for_each` bookkeeping also exists;
    the authored-surface claim stands. [Incorporated: aside added.]

## Checked And Found Sound

Exemplar metrics; drafting-guide section numbers and verbatim rules; spec
version ledger and out-of-scope list; E-series concurrency and E5 wording;
E2 plan ownership; `R1`/`R2` collision rationale; all relative links; M2 /
certification / accounting invariant paraphrases; capability-matrix
consistency for every named loop form.
