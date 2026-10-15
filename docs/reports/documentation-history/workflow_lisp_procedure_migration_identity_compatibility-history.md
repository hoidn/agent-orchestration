# Workflow Lisp Procedure Migration Identity Compatibility: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_procedure_migration_identity_compatibility.md](../../design/workflow_lisp_procedure_migration_identity_compatibility.md).

## Retirement Evidence Contract

A retirement record uses schema
`workflow_lisp_procedure_identity_retirement.v1` and contains at least:

- migration ID, compatibility class, repository commit, compiler/build
  versions, and retained public entry;
- internal callee identity and evidence that it is neither exported nor
  registered as a supported public entry;
- inventory/source evidence for the reviewed call site and retained public
  wrapper/contract, plus route-readiness labels as supporting routing evidence
  only. A `migration_evidence_only` label is neither mandatory nor sufficient;
- all **known** state-store roots, their owners, scan/query version and time,
  normalized query digest, matching terminal/nonterminal/call-frame counts,
  whole-store terminal/nonterminal totals, and an owner attestation that no
  supported live/nonterminal run or consumer of the queried old identities
  remains in that named store;
- the explicit statement `external_store_absence: not_asserted`;
- content-addressed old and new source snapshots and production build
  artifacts, including typed frontend AST, Semantic IR, executable IR,
  runtime plan, checkpoint points, and source map;
- an old-to-new identity delta covering workflow/call-frame IDs, executable
  node and step IDs, presentation keys, program-point/checkpoint IDs, generated
  state allocations, and source-map origin keys. Each old identity is marked
  `preserved` or `retired`; each new identity is marked `preserved` or `new`.
  Retirement records contain no runtime remap directive and are never inputs
  to resume planning or execution;
- a closed `retired_identity_query_evidence` object that content-addresses the
  frozen pre-edit scan containing `old_identity_query`. Every reviewed
  retirement record carries this binding, even when its production artifacts
  happen to enumerate every reviewed identity. This evidence is the
  authoritative source for the retired side only; it does not replace the
  production-derived preserved or new identities; it supplements the
  production table only for retired domain-qualified rows absent from those
  artifacts. The binding includes the evidence path and digest, query version,
  canonical query-list digest, identity count and exact domain membership map,
  frozen-baseline path and digest, the historical source path recorded by the
  pre-edit query, the retained old-source artifact path, and their one required
  shared digest. The historical and retained paths may differ because the live
  path can contain migrated source after capture; the validator does not reread
  current bytes there. It content-verifies the retained old-source artifact
  against the query's historical digest instead. The validator reads retained
  evidence bytes only: it neither recompiles the old source with the current
  compiler nor requires full per-workflow production bundles;
- artifact-contract comparison as a **keyed multiset**, preserving duplicate
  contracts. Keys include owning public entry, semantic step role, contract
  kind, artifact/field name, JSON pointer, type/variant, and publication role;
- execution order as a separate ordered sequence. Equal artifact multisets do
  not excuse an unreviewed execution-order change;
- persisted `SourceMapEntry.notes` proof for procedure definition and
  consuming call site;
- clean-run and interruption/resume evidence produced under the new IDs; and
- root-checksum evidence from default resume without observability or CLI
  override mutations, represented as a closed union selected by
  `evidence_mode`. `actual_tree` carries real `before_tree_digest` and
  `after_tree_digest` values and proves they are equal.
  `generic_characterization` instead carries `characterization_path`,
  `characterization_sha256`, `projection_sha256`, and the exact
  `tree_immutability: before_equals_after` result; it omits both tree-digest
  fields. The characterization file is content-addressed, uses the generic
  `workflow_lisp_root_checksum_characterization.v1` schema, and its inner
  projection digest is recomputed canonically. Both modes record that
  `WorkflowExecutor` construction and provider/command execution did not
  occur, and the closed evidence shape forbids unknown, missing, or mixed mode
  fields. Mode admissibility follows only from the immutable record fields,
  not a mutable project phase. Generic characterization never satisfies an
  actual old-state-negative or pilot-completion gate; a later actual-pilot
  negative is separate evidence and does not retroactively convert the
  retirement record; and
- callee-checksum characterization showing failure before child workflow or
  provider/command execution and no child-state identity remap, while recording
  any ordinary parent-level metadata permitted by the current runtime contract.

Repository evidence proves only repository facts. Store-owner attestation
proves only the named owner's knowledge of the named store at the recorded
time. Neither can establish the absence of unlisted external stores. If such a
store later appears, ordinary checksum rules apply without consulting the
retirement record. The record is not retroactively a remap authorization.

Historical old source and build artifacts are retained and readable for audit,
reports, and diagnosis. They are not selectable as current executable state
and are not rewritten to resemble the new build.

The validator derives the production identity table from the content-addressed
old/new artifacts and unions the frozen retired-identity query into the old
side. That union must match `identity_delta` exactly, including dispositions;
missing and extra identities both fail. Every query identity must occur in its
declared domain at most once. The sorted unique flattening of the domain lists
must equal the canonical sorted raw-identity query list, whose digest and count
are replayed independently. Because one raw identity may validly inhabit more
than one domain, the validator expands the domain map into unique
`(identity_kind, identity)` rows for the production-table and `identity_delta`
union; it does not require the domain lists to be disjoint. A query identity
that occurs anywhere in the new production identity table is a leaked retired
identity and is a hard validation failure, not a preserved identity or a
reason to trim the frozen query. Any mismatch in the
query version, canonical digest, identity count, exact domain membership map,
frozen-baseline digest, historical-source path binding, retained old-source
path binding, or their shared old-source digest fails closed.

This query evidence is evidence-only. Validation has no mutation output and
cannot authorize or perform a state-store, workflow-source, or build-artifact
write or mutation, identity alias, runtime remap, resume decision, or compiler
fallback. The mechanism and schema are migration-family-neutral and must not
select behavior from module, workflow, procedure, pilot, or repository names.

`terminal_run_count` and `nonterminal_run_count` are query-scoped counts of
distinct top-level runs containing at least one queried-identity match. Several
matches in one run count once. A match below a run directory inherits the
status of that first path component's top-level `state.json`. A nested match
without that state file fails the scan; an unreadable supported state file also
fails the scan; and a readable matching state with a missing or unknown
`status` counts as nonterminal. `store_terminal_run_count` and
`store_nonterminal_run_count` disclose all top-level runs in the named store
and remain digest- and freshness-bound, but they do not select strict
compatibility. The eligibility gate uses only the match-scoped
`nonterminal_run_count` and query-derived old call-frame/consumer counts.

## Pilot Application

The tracked-plan pilot was the first reviewed use of the retirement class. Its
completed evidence proves eligibility only for that content-addressed callee,
wrapper, store set, and run set. The route remains
`migration_evidence_only`; that label supports review but never decides
eligibility for another migration.

Before approval, the pilot owner must enumerate and attest every known store,
including the repository workspace's `.orchestrate/runs` root and any other
workspace/run roots intentionally used for this example. The scan must cover
top-level state, nested call frames, checkpoint records/indexes, retained
build manifests, and supported tooling that addresses the old call frame. A
repository-local zero match cannot support a claim about EasySpin,
PtychoPINN, paper repositories, copied workspaces, backups, CI artifacts, or
other external locations unless each is explicitly enumerated and attested.

If any known store contains a matching supported nonterminal run or a queried
old-identity consumer, the pilot returns to strict compatibility and waits for
identity preservation or the general upgrader. Unrelated active runs remain
disclosed in the whole-store totals but do not select compatibility. Terminal
historical evidence may remain, provided its old source/build artifacts are
retained and no supported resume/consumer contract is claimed.

## Dependencies And Sequencing

1. Treat acceptance of this clarification and the procedure-first contract
   amendment as a completed historical prerequisite from commit `61c79cb4`;
   do not re-amend either accepted authority during implementation.
2. Implement prerequisite A and prove normalized semantic identity stability
   on generic fixtures and both lowering routes.
3. Implement B and C; prove policy ownership and persisted two-note provenance
   on a generic inline effectful procedure fixture.
4. Implement the evidence-only retirement record validator and fresh checksum-
   rejection integration proof required by prerequisite D.
5. Retain the frozen old source/build artifacts and identity baseline without
   changing the pilot source or refreshing the old baseline.
6. Complete the known-store scans against the old identities, then obtain a
   genuine named human-owner attestation for every scanned store. An agent must
   never synthesize, guess, default, paraphrase, or sign an attestation. Any
   missing or ambiguous attestation selects strict compatibility and triggers
   the unattended stop without asking, retrying, or editing source.
7. Only after Step 6 passes, make the one pilot source migration.
8. Generate the content-addressed new artifacts, complete old-to-new identity
   delta and artifact/order comparisons, and produce clean-run plus real
   interruption/resume evidence under the new IDs.
9. Assemble and validate the completed retirement record, then obtain
   independent specification/runtime-state approval before accepting any
   reviewed retired identity.
10. Run negative old-state, focused, family parity, and broad verification,
    then update capability/status/routing docs only after implementation
    evidence passes.
11. Route the separate checksum-compatible projection-integrity hardening to a
    named plan and land it before production migration waves; it does not block
    this internal pilot.

Steps 2-4 are prerequisites, not acceptable differences to discover after the
family edit. If the current state/acceptance specs do not already state the
checksum compatibility and upgrader boundary accurately, clarify them before
the pilot source edit; do not add the separate projection audit to this plan.

The prerequisite implementation plan completed Steps 2-4 and retained the old
pilot baseline without editing the pilot source. Task 8 and its independent
reviews passed before Step 6 and the later source edit.
