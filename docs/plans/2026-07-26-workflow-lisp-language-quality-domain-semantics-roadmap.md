# Workflow Lisp Language Quality And Domain Semantics Roadmap

- **Status:** active
- **Selected:** 2026-07-26 by the owner's post-Stage-8 prompt-calculus
  direction, the `Value` prerequisite decision at `deb95c04`, the standing
  direction to continue roadmap execution without another confirmation stop,
  and the subsequent owner direction to integrate the bounded language-server
  debugging-utility recommendations without reopening Gate S8
- **Predecessor:** completed Procedure-First Roadmap Execution Sequence
  (`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`)
- **Scope:** the Q-series `Value`/prompt-calculus direction plus a parallel
  L-series of bounded `.orc` language-server reliability, diagnostic,
  navigation, recovery, and lifecycle improvements
- **Not selected:** the parked evolution roadmap, the slimmed E0 experiment,
  the shelved type/union-parsimony candidates, and the deferred LSP frontend
  prerequisites P1–P5

## Objective

Make prompts a checked Workflow Lisp domain surface without turning types into
a mandatory taxonomy. The sequence begins with the one loose transport
contract the prompt surface needs, then lands prompt fragments in independently
reviewed tranches whose consumers already exist.

The same active roadmap now carries a bounded language-server quality track.
That track improves the trustworthiness and actionability of the implemented
Stage-8 editor surface by consuming existing compiler structure. It does not
change Workflow Lisp runtime authority, create a second analyzer, or claim that
planned L-series behavior is already implemented.

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
- Gate S8 remains complete. L-series corrections and increments are successors
  to the implemented v1 surface, not a reopening or relabeling of Stage 8.
- The language server remains a read-only consumer of production compile entry
  points. L-series work may present or index compiler-retained structure, but
  may not parse diagnostic prose, infer types independently, execute workflows,
  or create runtime/debug authority.
- Diagnostic identity, CLI/LSP compile-request parity, exact source/config
  freshness, and fail-closed navigation remain binding unless an accepted
  stage amendment explicitly changes the relevant presentation or availability
  policy without weakening compiler authority.
- P1 diagnostic accumulation, P2 reader recovery, P3 span-to-type metadata, P4
  source overlays, P5 compile caching/incrementality, and any runtime debug
  transport remain deferred. Listing their dependent features below does not
  select those prerequisites.
- A roadmap status is routing, not capability evidence. Current authoring
  guidance continues to describe v1 until the owning L stage is implemented,
  verified, reviewed, and reflected in the capability matrix.

## Selected Sequence

### Q-Series: Prompt Calculus And Domain Semantics

| Stage | Work | Entry condition | Completion gate | Status |
| --- | --- | --- | --- | --- |
| Q0 | Transportable `Value` prerequisite | Stage 8 complete; owner prerequisite decision recorded | accepted design; reviewed implementation plan; target-2.19 implementation with direct-root, loader, runtime, resume, classic/WCC, docs, and broad non-security evidence | complete — reviewed target-2.19 implementation and evidence gate closed at `020c6138` |
| Q1 | Prompt core | Q0 complete; prompt-calculus design corrected and accepted | target-gated `defprompt`, imports, closed slot kinds, fully applied named fills, exact discharge/placeholder diagnostics, prompt-carried result derivation, deterministic flattening through existing prompt composition, one migrated real consumer | complete — implementation through `af45c4f1`; exact-tree gates and ordered final reviews accepted |
| Q2 | Output-position slots | Q1 complete; existing expected-output consumer and post-attempt wiring named in the accepted design | `:out` declaration and runtime postcondition share one path contract; both-direction runtime/E2E evidence | next — accepted design; separately reviewed implementation-plan gate next |
| Q3 | Prompt identity and diagnostics | Q2 complete; E4P ownership reconciled to this stage | role-separated prompt identity and hang/context-drift/provenance diagnostics with no ambient/import noise, building on Q1's fragment-program digest | blocked by Q2 |
| Q4 | Judgment views | Q3 complete; a concrete generic-reviewer/panel consumer is bound | result-plus-provenance inspection value and deterministic views over the existing evidence authority; no new outcome union or report authority | blocked by Q3 |

### L-Series: Language-Server Debugging Utility

| Stage | Work | Entry condition | Completion gate | Status |
| --- | --- | --- | --- | --- |
| L0 | Reliability and diagnostic actionability | Gate S8 complete; current v1 behavior characterized | no-watcher `didSave` reverse invalidation, intentional structured initialization failures, visible compiler-owned notes/expansion provenance, and a content-keyed pure-projection source cache pass focused state/driver/stdio/diagnostic/cache tests plus one real stdio E2E without changing diagnostic identity | complete — reviewed implementation closes the four bounded corrections and watcher-disabled real-stdio gate |
| L1 | Authored symbols and callable signatures | L0 complete; closed navigation/completion amendment accepted | authored type/resource/transition symbols and namespace-preserving procedure/workflow signature completion use existing compiler spans/catalogs, exclude generated shapes, and retain fail-closed freshness | next — accepted design; separately reviewed implementation-plan gate next |
| L2 | Recovery-safe static completion | L1 complete; two-tier completion amendment accepted | dirty/pending/invalidated/failed open entries receive only deterministic compiler-registry form heads as an incomplete list; stale callables remain closed and stale/closed/unassociated entries remain empty | blocked by L1 |
| L3 | Per-source entry selection | L2 complete; immutable initialization-schema amendment accepted; compile-path reentrancy proven (substrate MR-4 complete, or an equivalent accepted reentrancy fixture) | one canonical workspace process can select an exported workflow for a named application source while compiling library entries with no selection, with exact CLI request parity and restart semantics | blocked by L2 |
| L4 | Diagnostic lifecycle and compile progress | L3 complete; editor evidence and a diagnostic-currentness policy are accepted | dirty/pending diagnostic visibility follows the accepted policy without losing contribution ownership, and capability-gated serialized compile progress is balanced across completion, error, cancellation, and supersession | blocked by L3 |

The Q-series stages execute in Q-table order. Q0 and Q1 are complete; Q2's
design is accepted and its separately reviewed implementation-plan gate is
next. L0 is complete; L1's design is accepted and its separately reviewed
implementation-plan gate is next.
The L-series is an owner-selected
priority queue rather than a
claim that every adjacent stage has a compiler dependency on its predecessor;
it executes in L-table order unless the owner explicitly reorders it. At most
one L stage is active at a time.

One Q stage and one L stage may proceed concurrently only after their component
plans record disjoint behavioral ownership. Shared routing files—including
this roadmap, `docs/index.md`, `docs/design/README.md`, and
`docs/capability_status_matrix.md`—must be updated serially at each stage gate.
A later stage may be narrowed by its accepted design, but may not absorb a
deferred language mechanism merely because it is adjacent.

A parallel substrate track
(`docs/plans/2026-07-26-substrate-maintenance-track.md`) runs beside this
roadmap. Its M0/M1 hygiene-and-deletion phases touch disjoint surfaces and may
interleave with Q0–Q2 and the L-series under the same explicit file-ownership
rule. Its M2 persistence-parsimony design consumes Q3's identity definition as
a second consumer (memo keys). Q3 remains authored and gated here; neither the
substrate track nor the L-series may mint a second prompt/effect identity
definition, and this roadmap absorbs no substrate work.

## Stage Q0: Transportable `Value`

**Status:** complete. The reviewed implementation and its focused,
classic/WCC, runtime, resume, normative, routing, broad non-security evidence,
failure classification, and exact staged-tree reviews are recorded in the
implementation selector below. Q1 subsequently completed through its own
reviewed implementation-plan and implementation gates.

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

**Status:** complete. The corrected design and reviewed implementation plan
landed at `53d2786b`; implementation and documentation closed through
`e9bac6fa`; the structural-test quality correction landed at `af45c4f1`.
Exact-tree collection, focused, and broad non-security evidence plus its
pre-Q1 control are recorded in the implementation plan. Ordered closing tokens
are `Q1_FINAL_SPEC_APPROVED`, `Q1_PROMPT_TEST_FIX_SPEC_APPROVED`, and
`Q1_FINAL_QUALITY_APPROVED`.

The accepted correction resolves these former review findings:

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

**Status:** accepted after ordered independent
`Q2_DESIGN_SPEC_REAPPROVED` then `Q2_DESIGN_QUALITY_APPROVED`; the separately
reviewed implementation-plan gate is next.

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

## Stage L0: Reliability And Diagnostic Actionability

**Status:** complete. The content-keyed cache, one-probe save observer,
structured initialization failure mapping, visible compiler-owned diagnostic
notes/roles, and watcher-disabled real-stdio importer gate are implemented.
The broader MR-4 session-state refactor and P1–P5 remain separate.

Authority targets:
`docs/design/workflow_lisp_language_server.md` and
`docs/design/workflow_lisp_frontend_specification.md` §76.1.

Before implementation, write a bounded component plan that preserves one
authoritative disk probe per save and accepts the small presentation amendment
needed to make ordered diagnostic notes visible. Characterization must also
determine whether the file-content cache at `lowering/pure_projection.py:485`
is content-addressed or path-keyed: path-keyed caching in a long-lived server
process can serve stale content to a recompile the freshness layer correctly
triggered. If path-keyed, a minimal content-keyed correction joins L0's
reliability scope; the broader session-state refactor remains the substrate
track's MR-4. L0 otherwise owns exactly three changes:

1. Route a clean `didSave` snapshot through the existing reverse-revision
   observer so a changed imported source invalidates and schedules every
   trustworthy importer even when the client sends no watched-file
   notification. Avoid a second generation for the saved entry: if observation
   already advances it, do not apply `save_entry` again; an unchanged-content
   save must still force the existing single local save generation.
2. Translate existing structured `LispFrontendCompileError` failures from
   production initialization loading into intentional JSON-RPC invalid-params
   responses with stable diagnostic code/path evidence and no fake
   text-document diagnostic. Do not blanket-catch `Exception`, `OSError`,
   `RuntimeError`, or permission failures as client mistakes.
3. Preserve macro/helper role, call/definition role, and nullable expansion ID
   in diagnostic related-information labels, and present the compiler's
   ordered notes in the normal diagnostic message while retaining the same raw
   contribution, structured `data`, representative selection, and parity
   identity. Tests assert structure, order, and sentinel containment rather
   than freezing complete prose.

The gate includes changed and unchanged saves, dirty/unavailable dependencies,
unknown closures, diagnostic-target ownership, active-ticket cancellation,
one-probe evidence, missing/malformed initialization manifests, a
non-structured-error negative control, diagnostic aggregation, and a no-watcher
real-stdio importer E2E. Human rendering of every `form_path`, eager
`didOpen` reverse observation, multi-diagnostic recovery, unsaved-buffer
analysis, and runtime debugging are not part of L0.

## Stage L1: Authored Symbols And Callable Signatures

Authority target: an accepted closed-matrix amendment to
`docs/design/workflow_lisp_language_server.md`, reflected in the frontend
specification before the implementation plan.

**Status:** accepted after ordered independent `L1_DESIGN_SPEC_APPROVED` then
`L1_DESIGN_QUALITY_APPROVED`; the separately reviewed implementation-plan gate
is next.

L1 may expose only compiler-retained authored structure:

- document symbols for authored enum, path, record, union, schema, resource,
  and transition definitions, in addition to the implemented module,
  procedure, and workflow symbols; and
- separate procedure, workflow, and form completion kinds with callable-root
  parameter, return, and procedure-effect details from existing signatures and
  import binding maps.

Generated, expanded, specialized, or span-ambiguous shapes remain excluded. A
procedure and workflow with the same visible label remain distinct completion
items. L1 does not add arbitrary-expression hover, type-token definition,
references, rename, signature inference, or nominal filtering.

The gate uses exact authored spans and source order, proves generated-shape
exclusion, exercises same-label procedure/workflow namespaces, and derives
details from compiler catalogs rather than LSP-owned copies.

## Stage L2: Recovery-Safe Static Completion

Authority target: an accepted two-tier completion amendment to the language
server design, frontend specification §76.1, setup guide, and drafting guide.

For an open associated `.orc` entry under live initialization, deterministic
compiler-registry form heads may remain available while the entry is dirty,
pending, dependency-invalidated, superseded, language-failed, or
server-failed. That response is explicitly incomplete and contains no local or
imported callable from a prior snapshot. Clean/current/successful entries keep
the full implemented completion union. Configuration-stale, closed,
unassociated, and unavailable entries remain empty.

Definition and document-symbol freshness do not change. L2 must not parse the
buffer, reuse a last-good callable index, schedule an unsaved compile, add
cursor/type filtering, or select P2/P4/P5.

## Stage L3: Per-Source Entry Selection

Authority target: an accepted immutable-initialization amendment to the
language server design and setup guide.

Replace the single selection applied indiscriminately to every compile entry
with a contained source-to-export selection contract, or an equivalently small
design proven against the production CLI request model. The accepted schema
must retain exactly one canonical workspace root, immutable configuration for
the process lifetime, explicit source roots, restart-on-context-drift, and
exact per-request CLI parity.

The minimum integration fixture opens one multi-export application source and
one library-only source in the same process. The application request carries
its selected workflow; the library request carries no selection; both compile
through the unchanged production Stage-3 entry point. This stage does not add
multi-root workspace support or infer an entry selection from editor focus.

Entry additionally requires proven compile-path reentrancy: the substrate
track's MR-4 (compiler session state) complete, or an equivalent accepted
fixture demonstrating sequential multi-entry compiles in one process with no
module-global state bleed. L3's minimum fixture is exactly the workload that
hazard threatens, so the precondition is structural, not scheduling
preference.

## Stage L4: Diagnostic Lifecycle And Compile Progress

Authority target: an accepted editor-lifecycle amendment to the language
server design, based on observed client behavior rather than assumed UI
capabilities.

First decide whether diagnostics owned by a dirty or pending entry should be
temporarily hidden, or whether the existing anti-flicker retention policy
remains preferable with a different visible freshness treatment. Any chosen
policy must preserve internal contribution ownership, multi-entry
deduplication, exact accepted-generation authority, and atomic replacement by
a current completion; `DiagnosticTag.Unnecessary` must not be repurposed as a
staleness marker.

Then add capability-gated LSP work-done progress around the serialized compile
pump. Emit one balanced lifecycle for coalesced work rather than one noisy
popup per generation, and terminate it correctly on success, language error,
server error, close, cancellation, configuration staleness, and supersession.
L4 adds no telemetry, compile cache, parallel compiler execution, or runtime
session reporting.

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
- LSP multi-diagnostic recovery, malformed-buffer partial ASTs, arbitrary
  expression hover, unsaved-buffer diagnostics/navigation, and incremental
  compilation remain deferred behind P1–P5 and require separate owner
  selection.
- Type-reference definition, complete references, and rename remain
  unselected until the compiler retains exact authored occurrence spans and a
  complete namespace-aware reference graph; the LSP must not guess from text.
- Runtime breakpoints, stepping, provider/state/artifact inspection, and
  failure streaming require a separately designed runtime/debug transport.
  They are not extensions of the compile-time LSP track.

## Verification And Closure

For each stage:

1. run the narrowest owning tests;
2. collect every new or renamed test module;
3. run adjacent tests for the contracts actually touched—Q stages include the
   relevant frontend/lowering/loader/runtime/resume lanes, while an L-only
   stage does not inherit runtime/resume selectors unless it changes those
   shared contracts;
4. run at least one end-to-end usage check; L stages require a real stdio or
   repository-real LSP E2E in addition to their unit/integration selectors;
5. update the owning design/normative specs, capability matrix, design router,
   docs index, drafting/setup guidance, and roadmap status from observed shipped
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

This roadmap closes when Q0–Q4 and L0–L4 satisfy their completion gates,
normative and authoring surfaces describe only shipped behavior, all ten stage
gates have ordered approval, and routing names no active successor. Closure
does not select E0, revive any parked/shelved item, select P1–P5, or create a
runtime debugging surface.
