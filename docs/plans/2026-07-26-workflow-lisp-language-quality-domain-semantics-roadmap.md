# Workflow Lisp Language Quality And Domain Semantics Roadmap

- **Status:** active
- **Selected:** 2026-07-26 by the owner's post-Stage-8 prompt-calculus
  direction, the `Value` prerequisite decision at `deb95c04`, and the standing
  direction to continue roadmap execution without another confirmation stop
- **Predecessor:** completed Procedure-First Roadmap Execution Sequence
  (`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`)
- **Scope:** the `Value` prerequisite and the prompt-calculus direction only
- **Not selected:** the parked evolution roadmap, the slimmed E0 experiment,
  and the shelved type/union-parsimony candidates

## Objective

Make prompts a checked Workflow Lisp domain surface without turning types into
a mandatory taxonomy. The sequence begins with the one loose transport
contract the prompt surface needs, then lands prompt fragments in independently
reviewed tranches whose consumers already exist.

This roadmap is the separate selection act required by the predecessor's
post-Stage-8 handoff. The predecessor remains historical and complete.

## Governing Bounds

- Principle 29 is binding: types are opt-in constraints; nominal names are
  reserved for load-bearing contracts.
- Prompt completeness is structural. No compiler claim about prose quality,
  persuasion, or model compliance is permitted.
- Provider calls and procedures remain different operation kinds even when
  their parameter and result types match.
- Prompt fragments and residuals are compile-time structure, never runtime
  transport values.
- Prompt identity is role-separated and used-dependency-minimal under
  `docs/design/workflow_lisp_program_search_boundaries.md`.
- No optimization, search, evolution, fitness, or parked E-series machinery is
  part of this roadmap.
- Each behavior change uses TDD, narrow checks before broad non-security
  checks, and ordered independent specification then quality review.
- Security and provider-isolation work remain outside scope.

## Selected Sequence

| Stage | Work | Entry condition | Completion gate | Status |
| --- | --- | --- | --- | --- |
| Q0 | Transportable `Value` prerequisite | Stage 8 complete; owner prerequisite decision recorded | accepted design; reviewed implementation plan; target-2.19 implementation with direct-root, loader, runtime, resume, classic/WCC, docs, and broad non-security evidence | active — design and implementation plan accepted; implementation pending |
| Q1 | Prompt core | Q0 complete; prompt-calculus design corrected and accepted | target-gated `defprompt`, imports, closed slot kinds, fully applied named fills, exact discharge/placeholder diagnostics, prompt-carried result derivation, deterministic flattening through existing prompt composition, one migrated real consumer | blocked by Q0 |
| Q2 | Output-position slots | Q1 complete; existing expected-output consumer and post-attempt wiring named in the accepted design | `:out` declaration and runtime postcondition share one path contract; both-direction runtime/E2E evidence | blocked by Q1 |
| Q3 | Prompt identity and diagnostics | Q2 complete; E4P ownership reconciled to this stage | role-separated prompt identity and hang/context-drift/provenance diagnostics with no ambient/import noise, building on Q1's fragment-program digest | blocked by Q2 |
| Q4 | Judgment views | Q3 complete; a concrete generic-reviewer/panel consumer is bound | result-plus-provenance inspection value and deterministic views over the existing evidence authority; no new outcome union or report authority | blocked by Q3 |

Stages execute in table order. A later stage may be narrowed by its accepted
design, but may not absorb a deferred language mechanism merely because it is
adjacent.

A parallel substrate track
(`docs/plans/2026-07-26-substrate-maintenance-track.md`) runs beside this
roadmap: its M0/M1 hygiene-and-deletion phases touch disjoint surfaces and
may interleave with Q0–Q2, and its M2 persistence-parsimony design consumes
Q3's identity definition as a second consumer (memo keys). Q3 remains
authored and gated here; the substrate track must not mint a second
identity definition, and this roadmap absorbs no substrate work.

## Stage Q0: Transportable `Value`

Authority target:
`docs/design/workflow_lisp_transportable_value_type.md`.

Reviewed implementation selector:
`docs/plans/2026-07-26-workflow-lisp-transportable-value-implementation-plan.md`.

Required order:

1. independently review and accept the design;
2. draft a small implementation plan under `docs/plans/`;
3. independently review the plan;
4. implement through TDD using Subagent-Driven Development;
5. run focused contract/frontend/runtime/resume/classic-WCC checks;
6. update normative specs, capability/routing docs, and the drafting guide;
7. run the repository's broad non-security command;
8. obtain ordered final specification and quality reviews; and
9. commit exact reviewed paths plus a separate plan-only factual hash update.

Q0 must not implement `defprompt`, implicit value coercions, dynamic casts, or
field access on `Value`.

## Stage Q1: Prompt Core

Authority target:
`docs/design/workflow_lisp_prompt_calculus.md`.

Before planning, the existing proposed design must resolve these review
findings:

- remove procedure/provider signature interchangeability;
- define the closed kind/refinement/delivery/placeholder table;
- keep the first tranche to fully applied named slots rather than residual
  fragments;
- bind return ownership to one prompt declaration and the existing
  `ReturnSpec`/contract-rendering pipeline;
- define every refusal diagnostic and source owner;
- include one minimum `compiled_prompt_fragment_identity`: a canonical digest
  of exactly the referenced `defprompt` declarations plus normalized fully
  applied fill bindings, carried in semantic/executable IR and the receiving
  attempt's existing prompt snapshot before delivery; leave role separation,
  cross-attempt comparison, and diagnostic presentation to Q3;
- remove runtime prompt-reference and judgment-list examples not supported by
  the implemented list surface; and
- retain `:out`, residual partial application, judgment values, views, and
  optimization outside Q1.

Q1's required real consumer is the generic-reviewer pattern: one existing
extern prompt plus injected lens/target material is converted to importable
fragments without changing provider result authority or runtime behavior.

## Stage Q2: Output Positions

Authority target: an independently reviewed Q2 amendment to
`docs/design/workflow_lisp_prompt_calculus.md`, committed before the Q2
implementation plan.

Q2 owns only the `:path :out` delta. The declaration that instructs the
provider to write a path and the runtime postcondition checking that path must
share one authored slot. Caller-side delivery-mode overrides remain forbidden.
The design must bind one current expected-output consumer and demonstrate that
the new declaration removes duplicate path authority rather than adding
another copy.

## Stage Q3: Prompt Identity And Diagnostics

Authority target:
`docs/design/workflow_lisp_prompt_identity_diagnostics.md`, to be created and
independently accepted before the Q3 implementation plan.

Q3 is the sole roadmap owner of the E4P role-separation and diagnostic delta.
The predecessor's separate E4P list item is absorbed here and must not be
selected again. Q1's required fragment-program digest is the minimum identity
of the newly introduced compiled object; Q3 consumes it as the program-role
component rather than recomputing or replacing it.

Q3 adds role-separated identities for resolved input bindings, runtime-owned
prompt contributions, injected dependency content actually used by the
attempt, and provider policy. It excludes unused imports and ambient repository
state. Diagnostics expose those roles alongside Q1's fragment-program identity
to distinguish instruction drift, input drift, runtime-prelude drift, and
provider-policy drift in existing hang/context/provenance inspection paths.

Q3 does not introduce search or compare candidate fitness.

## Stage Q4: Judgment Views

Authority target: `docs/design/workflow_lisp_judgment_views.md`, to be created
and independently accepted before the Q4 implementation plan.

Q4 may add an inspection-layer judgment value only after Q3 provides stable
attempt identity. The semantic authority remains the provider result plus
existing attempt evidence. Matrices, disagreement tables, and iteration
series are deterministic views and are never parsed back into workflow state.

The first consumer is a generic-reviewer panel over the already implemented
bounded `list/map-effect` surface. This stage may use lists of judgment
inspection values only if their transport and view contract is accepted in
the Q4 design; it may not add runtime prompt references or higher-order
mapping.

## Explicitly Unselected Work

- The evolution follow-on roadmap remains parked and non-selectable.
- The slimmed E0 discriminating-benchmark probe remains eligible but
  unselected.
- Authored failure channels, structural union coercion, structural record
  admissibility, and named constraint bundles remain shelved until a live
  post-calculus consumer independently justifies one.
- Residual prompt partial application is deferred until repeated fully applied
  fragment use demonstrates the staging pain.
- Runtime prompt values, fragment-reference collections, type-parameterized
  fragments, semantic prompt checking, same-turn steering, and optimization
  remain outside this roadmap.

## Verification And Closure

For each stage:

1. run the narrowest owning tests;
2. collect every new or renamed test module;
3. run adjacent frontend/lowering/loader/runtime/resume tests;
4. run at least one end-to-end usage check;
5. update the owning design/normative specs, capability matrix, design router,
   docs index, drafting guide, and roadmap status from observed shipped
   behavior before final review;
6. run the exact broad non-security suite below in tmux;
7. classify any retained external failures against a fresh pre-stage control;
8. obtain specification approval before distinct quality approval; and
9. commit only the exact reviewed tree.

The reproducible broad command is:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  -k 'not security and not secret and not isolation'
```

If a later security/provider-isolation module is added, it is excluded by the
same `-k` rule; the command itself remains the comparison authority unless the
owner amends it explicitly.

This roadmap closes when Q0–Q4 are implemented, normative and authoring
surfaces describe only shipped behavior, all five stage gates have ordered
approval, and routing names no active successor. Closure does not select E0 or
revive any parked/shelved item.
