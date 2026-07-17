# Stack Implementation Phase Identity-Retirement Eligibility Decision

> **For agentic workers:** This plan is complete. Its retirement branch was
> not selected. Do not execute a source migration from this document.

**Status:** Complete by fail-closed eligibility stop at repository commit
`e367aeaf`. The bounded read-only scan found 24 supported old-identity
consumers across five domain-qualified identities that the proposed inline
conversion would retire. The accepted compatibility class requires zero
supported consumers, so no source, run root, run, owner attestation,
retirement record, or hold was created or changed.

**Goal:** Decide whether `design-plan-impl-implementation-phase` and its one
internal call are eligible for the accepted
`reviewed_internal_identity_retirement` class.

**Executed architecture:** Compile the retained historical source and a
deterministic in-test hypothetical inline source through the production WCC M4
build route. Derive compiler-owned production and leak identity projections,
bind a five-row domain-qualified witness subset to identities present in the
old projection and absent from the hypothetical new production/leak
projections, then scan the known completed pilot store. Any supported consumer
is a fail-closed retention result.

**Approach tradeoff:** The row remains a workflow/effect adapter even though
inline lowering compiles. This makes future cleanup depend on legitimate
retirement of the retained consumer store or a separately accepted
state-upgrade contract.

## Executed evidence

The tracked evidence root is:

```text
docs/plans/evidence/procedure-first-migration-waves/design-plan-impl-implementation-phase/
```

It contains exactly three bounded eligibility-decision artifacts:

- `eligibility_stop.json`: decision, query, counts, and routing;
- `identity_delta_witness.json`: content-addressed retained input references
  and the normalized old/proposed/leak membership projection for the five
  domain-qualified retired witnesses; and
- `known_store_scan.json`: the complete normalized scanner result, including
  all 24 match rows and all 38 scanned-file digest rows.

The retained source and provider/prompt/command manifests are reused by
repository-relative path plus SHA-256 from the completed Step 1 evidence root:

```text
docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/inputs/
```

No duplicate source or manifest snapshot was created.

The default replay is
`tests/test_workflow_lisp_procedure_first_migrations.py::test_stack_implementation_phase_identity_retirement_eligibility_stop_replays`.
It is clone-stable and depends on neither the ignored `.orchestrate` tree nor
the mutable live family source/manifests. It verifies every retained input
digest, recomputes the deterministic hypothetical source digest, checks the
content-addressed witness projection, verifies per-identity match counts
`4/8/4/4/4`, and recomputes the retained normalized scan digest.

Current-compiler reconstruction of both projections under two temporary clone
roots is opt-in via
`ORCHESTRATOR_REBUILD_STACK_IMPLEMENTATION_PROJECTIONS=1`. The live-store
rescan is separately opt-in via
`ORCHESTRATOR_RESCAN_STACK_IMPLEMENTATION_ELIGIBILITY=1`.

The observed decision facts are:

- matching terminal runs: 2;
- matching nonterminal runs: 0;
- supported consumer matches: 24;
- retained files scanned: 38; and
- normalized scan digest:
  `sha256:badca36d1166baa4c781466f8f68e7db9b10383841e56948a3fb73866a3e84f7`.

The bare callee name may remain valid procedure metadata in the hypothetical
frontend AST. Its witness is specifically the retired `workflow` identity
domain; this decision does not claim byte-string absence from every artifact.

## Decision and routing

The generic validator requires `consumer_count == 0`. Because the witness
subset already produces 24 supported matches, adding the remainder of a
complete retired-identity query cannot restore eligibility.

Therefore:

- the family source remains byte-unchanged;
- no run ID is permitted by this plan;
- the inventory row is retained and reclassified from
  `procedure-candidate` to `effect-adapter`;
- no owner action or attestation is required for this non-mutating stop; and
- Procedure-First Migration Waves Task 2 Step 3 is the next sub-selector.

## Authority and fixed scope

- Governing identity design:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`.
- Public-boundary contract:
  `docs/design/workflow_lisp_procedure_first_reuse_contract.md`.
- Parent selector:
  `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`, Task 2
  Step 2.
- This decision owns only `design-plan-impl-implementation-phase`. It does not
  reopen the completed pilot or decide the same-file record-call family.
- No YAML file changes belong here. Stage 6 YAML retirement remains the next
  major sub-roadmap after Migration Waves Tasks 2-8.

## Eligibility-decision completion contract

This decision is complete only when all of the following are true:

1. the exact historical source/manifests and hypothetical source are
   content-addressed;
2. every queried witness has an explicit identity domain, is present in the
   old production projection, and is absent from the hypothetical new
   production and leak projections;
3. the complete normalized scan and per-identity matches are retained and
   replayable without the live store;
4. the source and all run stores remain unmodified;
5. the inventory disposition and roadmap routing advance to Task 2 Step 3;
6. focused and routing tests pass; and
7. independent specification and quality reviews approve the result.

## Future retirement boundary

A future retirement attempt requires a new, separately reviewed plan after
the retained supported consumers are legitimately gone or a compatible
state-upgrade/retention design is accepted. This completed decision authorizes
no steps, roots, run IDs, owner forms, or mutations from that future path.

## Verification

```bash
pytest --collect-only -q tests/test_workflow_lisp_procedure_first_migrations.py
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k \
  'stack_implementation_phase or procedure_first_reuse_inventory'
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/design-plan-impl-implementation-phase/eligibility_stop.json >/dev/null
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/design-plan-impl-implementation-phase/identity_delta_witness.json >/dev/null
python -m json.tool docs/plans/evidence/procedure-first-migration-waves/design-plan-impl-implementation-phase/known_store_scan.json >/dev/null
git diff --cached --check
```
