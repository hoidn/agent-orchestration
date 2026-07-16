# Tracked Design Phase Identity-Retirement Eligibility Decision

> **For agentic workers:** This plan is complete. Its retirement branch was
> not selected. Do not execute the conditional appendix.

**Status:** Complete by fail-closed eligibility stop at repository commit
`2b12fc2b`. The bounded read-only scan found 26 supported old-identity consumers
across five domain-qualified identities that the proposed inline conversion
would retire.
The accepted compatibility class requires zero supported consumers, so no
source, run root, run, owner attestation, retirement record, or hold was
created or changed.
This bounded decision introduced no new language, compiler, runtime, or
evidence-standard design.

**Goal:** Decide whether `tracked-design-phase` and its one internal call are
eligible for the accepted `reviewed_internal_identity_retirement` class.

**Executed architecture:** Compile the unchanged source and a deterministic
in-test hypothetical inline source through the production WCC M4 build route.
Derive compiler-owned production and leak identity projections, bind a
five-row domain-qualified witness subset to identities present in the old
projection and absent from the hypothetical new leak projection, then scan the
known completed pilot store for those witnesses. Any supported consumer is a
fail-closed retention result.

**Approach tradeoff:** The row remains a workflow/effect adapter even though
inline lowering compiles and its public contract can be compared. This makes
future cleanup depend on legitimate retirement of the retained consumer store
or a separately accepted state-upgrade contract.

## Executed evidence

The tracked evidence root is:

```text
docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/
```

It contains exactly the bounded eligibility-decision artifacts:

- `inputs/`: the exact historical source plus provider, prompt, and command
  manifests;
- `eligibility_stop.json`: decision, query, counts, and routing;
- `identity_delta_witness.json`: source/input digests and the content-addressed
  normalized old/proposed/leak membership projection for the five
  domain-qualified retired witnesses; and
- `known_store_scan.json`: the complete normalized scanner result, including
  all 26 match rows and all 38 scanned-file digest rows.

The default replay is
`tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_design_phase_identity_retirement_eligibility_stop_replays`.
It is clone-stable and depends on neither the ignored `.orchestrate` tree nor
the mutable live family source/manifests. It verifies the retained input and
projection digests, proves every witness is old and absent from the retained
new leak projection, verifies per-identity match counts `4/10/4/4/4`, and
recomputes the retained normalized scan digest. Current-compiler reconstruction
of both projections under two temporary clone roots is separately opt-in via
`ORCHESTRATOR_REBUILD_TRACKED_DESIGN_PROJECTIONS=1`.

The live-store rescan is deliberately opt-in:

```bash
ORCHESTRATOR_RESCAN_TRACKED_DESIGN_ELIGIBILITY=1 \
  pytest -q tests/test_workflow_lisp_procedure_first_migrations.py::test_tracked_design_phase_eligibility_stop_live_store_rescan_is_opt_in
```

The observed decision facts are:

- matching terminal runs: 2;
- matching nonterminal runs: 0;
- supported consumer matches: 26;
- retained files scanned: 38; and
- normalized scan digest:
  `sha256:94513702975b5aea90d4a991c8a3a7cb9ca066460f15e620785dd6d203db1520`.

The bare `tracked-design-phase` spelling remains valid procedure metadata in
the hypothetical frontend AST. Its witness is specifically the retired
`workflow` identity domain; this decision does not claim byte-string absence
from every artifact.

## Decision and routing

The generic validator requires `consumer_count == 0`. Because the witness
subset already produces 26 supported matches, adding the remainder of a
complete retired-identity query cannot restore eligibility.

Therefore:

- the family source remains byte-unchanged;
- no run ID is permitted by this plan;
- the inventory row is retained and reclassified from
  `procedure-candidate` to `effect-adapter`;
- no owner action or attestation is required for this non-mutating stop; and
- Procedure-First Migration Waves Task 2 Step 2 is the next sub-selector and
  is now current.

## Authority and fixed scope

- Governing identity design:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`.
- Public-boundary contract:
  `docs/design/workflow_lisp_procedure_first_reuse_contract.md`.
- Completed generic implementation:
  `docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md`.
- Parent selector:
  `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`, Task 2
  Step 1.
- This decision owns only `tracked-design-phase`. It does not reopen the
  completed tracked-plan pilot or decide the implementation phase.
- No YAML file changes belong here. Stage 6 YAML retirement is the next major
  sub-roadmap after Migration Waves Tasks 2-8.

## Protected working-tree guard

The following user-owned paths were outside this decision and remain outside
every commit:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Never stage, restore, rewrite, or clean a protected path.

## Eligibility-decision completion contract

This decision is complete only when all of the following are true:

1. old and hypothetical new production inputs and projections are
   content-addressed;
2. every queried witness has an explicit identity domain, is present in the
   old production projection, and is absent from the hypothetical new leak
   projection;
3. the complete normalized scan and per-identity matches are retained and
   replayable without the live store;
4. the source and all run stores remain unmodified;
5. the inventory disposition and roadmap routing advance to Task 2 Step 2;
6. focused and routing tests pass; and
7. independent specification and quality reviews approve the result.

## Unselected conditional retirement appendix

A future retirement attempt would require a new, separately reviewed plan
after the retained supported consumers are legitimately gone or a compatible
state-upgrade/retention design is accepted. That future plan would need the
full pre-edit owner/quiescence gate, content-addressed old/new builds, exact
identity delta, two explicitly authorized new-ID runs, retirement-record
validation, final owner attestation, hold release, and focused/broad reviews.

None of those steps, roots, run IDs, owner forms, or mutations is authorized by
this completed eligibility decision. The completed tracked-plan pilot remains
the reference protocol; it is not an executable appendix here.

## Verification

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k \
  'tracked_design_phase_identity_retirement_eligibility_stop or procedure_first_reuse_inventory'
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/eligibility_stop.json >/dev/null
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/identity_delta_witness.json >/dev/null
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/known_store_scan.json >/dev/null
git diff --cached --check
```
