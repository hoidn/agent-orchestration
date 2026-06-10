# Post-Foundation Composition Design Extension Plan

Status: plan
Created: 2026-06-09
Scope: extend `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
so it addresses the unresolved findings in
`docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
in a principled way.

## Inputs

- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
  (findings F1-F11, priority work items P0/P1, design-docs-to-update list).
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  (current target; tranches 1-6 plus deferred work).
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  (format/quality reference: authority direction, status snapshot, tranche
  contract/tasks/acceptance, evidence boundaries, prohibited evidence,
  declarative acceptance scenarios, success criteria).

## Findings-to-design mapping

| Finding | Disposition in the updated design |
| --- | --- |
| F1 (fixed) | Architecture invariant: structural/capability recognition across module boundaries; no short-name-local stdlib checks. |
| F2 | New top-priority tranche: nested structured-control composition with the implementation-phase acceptance fixture. |
| F3 | New tranche: typed result translation; output variant derives from returned variant expression. |
| F4 | Same tranche: variant-scoped field identity, with documented-restriction fallback. |
| F5 | Expand entrypoint bootstrap tranche into a private executable context bridge (incl. YAML interop bridge). |
| F6 | Expand adapter tranche: helper classification, certified adapters, run-state/resource transitions as typed effects. |
| F7 | New tranche: typed projection for selection/bundle publication with preference order. |
| F8 | Strengthen imported/std reuse + review-loop tranches: stdlib loops valid in branch scopes, reusable calls, parent modules. |
| F9 | New tranche: parent-callable workflow family and `backlog-drain` typed abstraction. |
| F10 | Adapter tranche: importable certified-adapter declaration surface with typed fields, not raw argv. |
| F11 | Parity criteria: leaf-versus-parent-callable evidence labels; `--require-promotable` fails on leaf-only evidence. |

## Edits

1. Rewrite `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
   in place: updated metadata/scope, driving evidence, revised executive
   decision and work order, updated inventory table, expanded authority and
   invariants, restructured tranches with contract/tasks/acceptance, evidence
   boundaries (required + prohibited), declarative acceptance scenarios,
   verification strategy, success criteria.
2. Refresh the one-line descriptions of the doc in `docs/design/README.md`
   and `docs/index.md` so discoverability matches the expanded scope.

## Ownership guardrails

- Do not reopen foundation tranches; the foundation doc owns command/provider
  structured-output authority, private value transport, strict gate schema,
  and the first StateLayout/PathAllocator boundary.
- StateLayout identity rules stay with `workflow_lisp_state_layout.md`;
  this design states the composition-facing requirements and routes identity
  ownership there.
- Adapter certification policy details stay with
  `workflow_command_adapter_contract.md`; this design owns sequencing and the
  `.orc` calling surface requirements.

## Verification

- `git diff --check` clean.
- Cross-references resolve to existing files.

## Revision (2026-06-09, second pass)

The doc was rewritten as a synthesis of two drafts. Base: the
alternate draft with Design Details, Contracts And Interfaces,
Dependencies And Sequencing, Work Blocked, per-tranche normative spec
deltas, readiness-label vocabulary, context families, and the
resource-transition model. Merged from the first draft:

- Related-docs and §4.1 evidence links to the parent-drain blocker
  record and the feasibility test module;
- tranche labels (Tranche 0-8) aligned between the executive decision
  and section headers, with P0/P1 markers from the findings report;
- explicit Deferred Work section (runtime closures, broad legacy lint,
  `orchestrate explain`);
- private-runtime-context inventory row corrected from "Partial" to
  "Gap";
- composition-regularity, F1 structural-recognition, and
  leaf-evidence-insufficiency invariants;
- F4 documented-restriction fallback (drafting-guide entry plus
  compile-time diagnostic) in Tranche 2;
- F7 third route (private context bridge) and bridge replacement-route
  recording in Tranche 5;
- foundation non-reopening paragraph in the prerequisite boundary; and
- snapshot rows for nested structured control, union translation, and
  variant field identity.

## Revision (2026-06-09, third pass)

Cross-review of the two drafts surfaced one remaining substantive
delta: the F4 documented-restriction fallback was demoted from an
acceptance/success alternative to a required interim mitigation.
Variant-scoped lowered identity is now the only outcome that satisfies
Tranche 2 acceptance, required evidence, and the success criteria; the
drafting-guide restriction plus compile-time diagnostic remains
mandatory while the gap is open but lives in Compatibility And
Migration and is listed under prohibited evidence as a completion
claim. The cross-review's other four recommendations (Tranche 1 owning
generic effectful normalization, Contracts And Interfaces section,
resource-transition contract, resume-or-start schema/taxonomy) were
already incorporated in the second-pass synthesis.

## Revision (2026-06-10, fourth pass)

Fold the 2026-06-10 WCC reconciliation unplanned findings
(`docs/reports/2026-06-10-wcc-post-foundation-unplanned-architecture-findings.md`,
UAF-01..12) into the target. The reconciliation execution already updated
WCC authority, the `IfExpr` blocker, Tranche 3A, and inventory rows; this
pass adds what it did not:

- UAF findings map and the 2026-06-10 report in evidence/related docs;
- route identity (WCC schema-2 vs legacy schema-1) as a semantic dimension
  of fixtures, examples, and migration evidence, with an example/fixture
  route taxonomy in Tranche 0 and prohibited-evidence entries;
- Tranche 2: terminal provenance contract (let-bound values, workflow and
  procedure calls, branch projections) and runtime active-variant output
  resolution acceptance (UAF-03, UAF-11);
- Tranche 1 acceptance: inherited activation guards reference (UAF-04,
  owned by the WCC design);
- Tranche 4: stdlib provider-effect ownership across generated callable
  workflows (UAF-06);
- Tranche 5: WCC projection/reference value classes and the pure-projection
  decision — pure input-derived outputs lower to a visible projection step
  (UAF-07, UAF-10);
- Tranche 8: reusable-state diagnostic taxonomy (fail-closed outer class,
  preserved inner cause codes) and the normalized resume bundle boundary as
  a consumed contract (UAF-08, UAF-09);
- ownership routing: guard-inheritance semantics, resume bundle shape, and
  CLI route policy stay with the WCC/runtime/authoring docs respectively.

## Revision (2026-06-10, fifth pass)

Expressivity review: the doc constrained bad shapes but never prescribed
good ones, so a drain would transliterate YAML shapes that now compile under
WCC. Added Section 10A (Post-WCC Family Idiom And Expressivity Discipline)
with six disciplines — loop-carried state over state-file choreography,
values before artifacts, context as ordinary scoped data, chosen rather than
inherited workflow boundaries, pure projections as standard glue, and
parity-constrained labeling with a mandatory post-promotion simplification
pass — plus wiring: three new invariants, a goal, Tranche 0 classification
tasks, Tranche 3 bridge-scope narrowing with an interior-context fixture,
Tranche 5 systematic pure-projection glue, Tranche 7
boundary/artifact-justification tasks and acceptance, a compatibility
paragraph making simplification part of the target, verification §27.11, and
a success criterion. Applied on top of the drain's concurrent Tranche 1A
(`workflow-lisp-wcc-ifexpr-work-item-route`) rewiring, which was preserved.

Self-audit follow-up (same day): five residuals closed — Tranche 3A carrier
language reconciled with 10A.3 (carriers are legacy-route compatibility;
WCC branch scopes need none), Tranche 5 preference order inverted under
10A.2 (typed selection values first, materialized bundle as
parity-justified shape, with the §6 diagram annotated), post-promotion
simplification given an executable home as Tranche 9 (§19A) with work-order
and sequencing entries, an effect-row-free-glue diagnostic task and
acceptance added to Tranche 5, and §10A.7 added to propagate the idiom into
the drafting guide and family review criteria with a §27.11 verification
item.

Post-pass correction from reviewing merge `ebdc635`: route identity is
multi-valued (`LoweringRoute.LEGACY`, `WCC_M1`-`WCC_M4`, plus a separate
lowering schema version), not the binary "WCC schema-2 vs legacy schema-1"
first written; the live selection authority
(`post_wcc_reconciliation_index.md`) and reconciliation inventory are now
referenced from §4.1, Related docs, and Tranche 0 tasks; and the F4
inventory row was corrected to partially-implemented (WCC M5 variant-scoped
allocation identity evidence plus UAF-11 runtime active-variant resolution),
with remaining work narrowed to authored field-name reuse acceptance and
active-variant parity.
