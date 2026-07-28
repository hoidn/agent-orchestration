# Workflow Lisp L5 Authored Reference Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Each task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit. Steps use checkbox
> (`- [ ]`) syntax for execution tracking.

**Goal:** Extend read-only go-to-definition from its existing exact direct-call
tokens to two and only two newly admitted authored shapes: direct prompt
application heads and final retained unexpanded `proc-ref` name tokens.

**Architecture:** Build immutable five-field authored-reference rows entirely
inside `orchestrator/lsp/navigation.py`. Join one final compiler assertion to
one original-syntax list at the exact whole span, take only the authored head
or `proc-ref` name-token span, and cross-check canonical target plus authored
definition through the prompt or procedure catalog. Preserve the existing
server preflight and protocol path unchanged; every incomplete, generated,
expanded, specialized, ambiguous, or unsupported join fails closed.

**Tech Stack:** Python 3.11+, frozen dataclasses and tuples, existing linked
Stage-3 results, `WorkflowLispSyntaxModule`, `PromptCatalog`,
`ProcedureCatalog`, pygls/lsprotocol, pytest/pytest-xdist, and real JSON-RPC
over stdio.

**Accepted design:** commit
`b8a41172bd5a1360b9d62ffa9a06512ea0ef8be4`, tree
`dad87132477a8e17635d55ee3aaf794b14bae7ea`, after ordered independent
specification review then independent quality review.

**Implementation status:** the plan passed ordered `L5_PLAN_SPEC_APPROVED`
then distinct `L5_PLAN_QUALITY_APPROVED`; Tasks 1–5 are implemented and
committed. Task 6's exact durable-baseline/routing candidate and fresh control
are assembled below, and its post-candidate broad comparison has zero failed-
node delta from that control. Ordered `L5_FINAL_SPEC_APPROVED` then distinct
`L5_FINAL_QUALITY_APPROVED`, the reviewed closure commit, and postcommit
verification remain pending.

---

## Admitted Boundary And Deliberate Cost

This plan implements only:

- a prompt-head row when one unexpanded final `PromptApplicationExpr`, one
  exact original-syntax list, and one `PromptCatalog` entry agree on whole
  span, canonical prompt target, and authored `defprompt` span;
- a `proc-ref` name-token row when one final `ProcRefLiteralExpr` remains
  directly in an authored, non-generated, non-specialized procedure or
  workflow owner, has an empty expansion stack, uniquely joins the original
  exact `(proc-ref NAME)` list, and resolves through the procedure catalog to
  an authored `defproc` span;
- collision-safe immutable rows shaped exactly as
  `(reference_kind, reference_span, canonical_target, target_kind,
  definition_span)`;
- the existing exact direct procedure-call and `(call ...)` workflow-call rows
  represented in that same collision-safe row type with no new call behavior;
- the existing current-success definition preflight and silent-null protocol;
  and
- compiler/projection, exact-token, visibility, null-matrix, real-stdio,
  repository-read-only, routing, and broad non-security evidence.

Explicitly defer every macro head shape. `ExpansionFrame` retains spelling,
call span, definition span, and expansion ID but no canonical/module-qualified
macro identity sufficient for a shape-wide local/imported join. Do not add a
partial local-only macro feature.

Explicitly exclude:

- original `proc-ref` syntax consumed or erased before the final typed result;
- macro-consumed, expanded, generated-owner, or specialized-owner proc-refs;
- WCC-reconstructed/generated calls and any call with
  `authored_callee_span=None`;
- source-text parsing, server-side name resolution, new source maps, retained
  metadata, compiler/frontend changes, completion, symbols, references,
  rename, hover, type navigation, diagnostics, and runtime behavior.

The deliberate cost is silence for useful-looking authored tokens whose final
compiler result cannot prove a unique authored-to-authored edge. Supporting
macro heads or erased/specialized proc-refs later requires a separate compiler
identity/retention design. This also makes navigation-index construction fail
as a whole when a nominally admitted join is internally inconsistent; a
best-effort partial index would hide compiler/projection drift.

## Governing Authorities

Read before implementation:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_lisp_lsp_authored_reference_navigation.md`;
- `docs/design/workflow_lisp_language_server.md`;
- `docs/design/workflow_lisp_frontend_specification.md` §76.1;
- `docs/design/workflow_lisp_prompt_calculus.md`;
- `docs/design/workflow_lisp_macro_surface_contract.md`;
- `docs/design/workflow_language_design_principles.md`, especially principles
  24, 28, 29, and 30;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- the completed L1 and L2 implementation plans; and
- this plan's accepted-design commit and exact tree above.

If this plan conflicts with the accepted L5 design, correct the plan and repeat
ordered plan reviews. Do not reinterpret the accepted contract in code.

Principle 29 means L5 adds no nominal type, mandatory type annotation, or
procedure/prompt contract taxonomy. It projects identities already accepted by
the compiler. Principle 30 means exact token ownership, identity agreement,
and refusal are deterministic tooling responsibilities; L5 must not add prompt
guidance or ask a provider to compensate for missing navigation metadata.

## Disjoint Ownership And Protected Surfaces

L5 production ownership is exactly:

- `orchestrator/lsp/navigation.py`.

L5 behavioral test ownership is exactly:

- `tests/test_workflow_lisp_lsp_navigation.py`;
- `tests/test_workflow_lisp_lsp_integration.py`;
- `tests/test_workflow_lisp_lsp_e2e.py`;
- the new L5 fixture roots named in Tasks 2 and 4.

Do not modify:

- `orchestrator/workflow_lisp/` or any compiler/frontend implementation;
- `orchestrator/lsp/server.py`, `state.py`, `compile_driver.py`,
  `coordinates.py`, or the stdio transport;
- Q3/Q5 prompt identity, runtime, evidence, workflow, or prompt assets;
- WCC, lowering, macros, specialization, source maps, catalogs, or syntax
  classes; or
- security, safety, secrets, or provider-isolation paths.

If a Task-1/2/3 RED test appears to require one of those production changes,
stop that task and return the shape to design/feasibility review. Do not widen
L5.

The final durable baseline/routing task may update only:

- `docs/design/workflow_lisp_language_server.md`;
- exact §76.1 L5 compatibility wording in
  `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_lsp_authored_reference_navigation.md`;
- `docs/workflow_lisp_language_server_setup.md`;
- the exact editor-navigation paragraph in
  `docs/lisp_workflow_drafting_guide.md`;
- the exact L5 rows/sections in `docs/capability_status_matrix.md`,
  `docs/design/README.md`, `docs/index.md`, and the active roadmap;
- exact L5 expectations in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`; and
- factual evidence/status in this plan.

Serialize those shared routing files against concurrent Q work. Preserve every
unrelated hunk.

## Protected Working Tree And Execution Contract

Run from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every pre-existing user, owner, experiment,
provider, runtime, report, and unrelated staged/unstaged change. Never use
`git add .`, `git add -A`, destructive checkout/reset, or broad cleanup.

Execute with a fresh implementation subagent per task. The choreography is
deliberately asymmetric:

- Tasks 1–3 are the only implementation owners. Each writes the smallest
  behavioral test, confirms the intended RED, implements the minimum change,
  and confirms GREEN before review.
- Tasks 4–5 are characterization/integration evidence gates over Tasks 1–3.
  Their assertions are expected to begin GREEN. Any RED identifies an owning
  Task-1/2/3 defect and routes back there for a fresh RED→GREEN cycle plus
  ordered specification then quality review; Tasks 4–5 do not patch
  production locally.
- Task 6 begins with every prior focused and evidence gate GREEN. It updates
  durable baseline/status/routing documentation and closure evidence without
  manufacturing a new behavioral RED.

For every task:

1. refresh `git status --short` and record exact task-owned paths;
2. follow that task's implementation or evidence-gate choreography above;
3. rerun the narrow selector and adjacent direct-call regressions;
4. run `pytest --collect-only -q` for every new or renamed test module;
5. inspect the complete exact task diff and run `git diff --check`;
6. obtain independent specification-compliance review;
7. correct findings in the owning task and repeat spec review;
8. obtain a distinct implementation-quality review;
9. correct findings in the owning task and repeat ordered spec then quality
   review;
10. construct an isolated exact-path staged snapshot;
11. inspect every staged byte and record commit/tree/test evidence; and
12. commit without post-review edits.

Use the `tmux` skill for commands expected to exceed one minute and for the
closing broad suite. No task may weaken an assertion to turn a failure green.

## Collision And Identity Contract

Task 1 begins with a mandatory audit before changing representation:

```bash
rg -n \
  "DefinitionLink|definition_links|_definition_spans|callee_span|canonical_target" \
  orchestrator/lsp tests/test_workflow_lisp_lsp_*.py
```

Record every producer, key, sort key, and consumer in the Task-1 review note.
The implementation must then enforce:

- `DefinitionLink` is a frozen five-field row:
  `reference_kind`, `reference_span`, `canonical_target`, `target_kind`,
  `definition_span`;
- reference-shape values are exact and closed:
  `procedure-call`, `workflow-call`, `prompt-application`, and `proc-ref`;
- target-kind values are exact and closed: `procedure`, `workflow`, `prompt`;
- `DefinitionLink.__post_init__` (or the equivalent immutable-row constructor
  validation) owns both closed domains and raises `ValueError` for an unknown
  `reference_kind` or `target_kind` before any target/occurrence map insertion;
- one target identity key is `(target_kind, canonical_target)`;
- one occurrence identity key is `(reference_kind, canonical source path,
  start offset, end offset)`;
- one span-ambiguity key is `(canonical source path, start offset, end
  offset)`, and every assertion at that span must have the same
  `reference_kind`;
- byte-for-byte-identical duplicate target facts or reference rows collapse;
- the same target key with different authored definition spans fails index
  construction;
- the same occurrence key with different target kind, canonical target, or
  definition span fails index construction;
- two different reference kinds asserted at the exact same authored source
  span fail index construction even though their kind-aware occurrence keys
  differ;
- different reference/target families may retain the same visible spelling at
  different authored spans without merging;
- ordering is deterministic by canonical path, start/end offset,
  `reference_kind`, `target_kind`, and `canonical_target`; and
- no dict assignment silently overwrites a conflicting semantic fact.

`definition_at_lsp_position` changes only from `callee_span` to
`reference_span`. Its accepted-text lookup, UTF-16 half-open membership, and
returned `definition_span` remain the single request behavior.

## Projection Contract

Add private LSP-only helpers in `orchestrator/lsp/navigation.py`:

- `_original_syntax_lists(syntax_module)` recursively walks
  `WorkflowLispSyntaxModule.forms` through `SyntaxList.items`, never source
  text, and returns retained lists deterministically;
- `_prompt_application_assertions(expr)` finds only final
  `ProviderResultExpr.prompt` values whose exact type is
  `PromptApplicationExpr`; it does not alter shared expression traversal;
- `_reference_links_for_authored_owner(...)` replaces
  `_definition_links_for_expr(...)` and emits existing direct calls plus the
  two admitted shapes;
- `_project_prompt_application_link(...)` performs the prompt join;
- `_project_proc_ref_link(...)` performs the proc-ref join;
- `_insert_unique_definition_target(...)` and
  `_insert_unique_reference_link(...)` implement both the kind-aware
  occurrence identity and kind-exclusive span-ambiguity contracts; and
- `_validate_authored_token_span(...)` verifies a non-empty same-path token
  span strictly contained in its exact whole-form span.

Equivalent private names are acceptable only if reviews can map them one for
one to these responsibilities. Do not create a general frontend projection
framework.

Prompt projection requires all of:

1. one final `PromptApplicationExpr` with empty `expansion_stack`;
2. exactly one original-syntax `SyntaxList` at the identical source and whole
   `application.span`, also unexpanded;
3. a `SyntaxIdentifier` head with an exact non-empty token span;
4. `compiled.prompt_catalog` is a `PromptCatalog`;
5. `prompt_catalog.resolve(head.resolved_name)` returns the same canonical
   `qualified_name`, declaration span, and target kind as
   `application.prompt`;
6. the canonical prompt target maps to one unexpanded authored
   `PromptDef.declaration.span`; and
7. the emitted `reference_span` is only the syntax head span.

Proc-ref projection requires all of:

1. the final traversal still contains the exact
   `ProcRefLiteralExpr`, with empty `expansion_stack`;
2. its typed owner already passed the existing non-specialized,
   non-generated, empty-owner-expansion filters;
3. exactly one unexpanded original-syntax `SyntaxList` at the identical source
   and whole `occurrence.span`;
4. exactly two list items: a `SyntaxIdentifier` head resolved as `proc-ref`
   and a `SyntaxIdentifier` name;
5. the name identifier's `resolved_name` equals
   `occurrence.authored_name`;
6. `compiled.procedure_catalog.definitions_by_name[
   occurrence.target_name]` exists, has neither
   `generated_local_procedure` nor expansion provenance, and agrees with the
   canonical procedure target; and
7. the emitted `reference_span` is only the second identifier span.

Original syntax is a cross-check and exact-token source, never independent
reference discovery. An original prompt-looking or `(proc-ref NAME)` list with
no retained final assertion emits nothing.

## Common Availability And Null Matrix

Do not add a new server branch. Every row must flow through the unchanged
`WorkflowLispLanguageServer._current_navigation`,
`definition_at_lsp_position`, and `_location_for_span` path.

For both a prompt head and a retained proc-ref name, prove null under:

- unavailable and unreadable source probes;
- dirty open buffer;
- compile pending;
- dependency invalidated;
- current language failure;
- current server failure;
- superseded generation;
- closed document;
- unassociated document URI;
- configuration stale;
- source stale;
- source and configuration stale together;
- clean-idle with no accepted current success;
- malformed/internally inconsistent entry state;
- navigation-index construction failure;
- unsupported reference kind;
- generated, expanded, specialized, erased, or ambiguous occurrence; and
- opening delimiter, closing delimiter, exact end boundary, adjacent
  whitespace, fill keyword/value, `proc-ref` form head, and every non-reference
  argument.

The server returns silent `null`; compiler diagnostics remain authoritative
for private/ambiguous source failures.

---

## Preimplementation Plan And Routing Gate

Before Task 1:

- [x] Obtain `L5_PLAN_SPEC_APPROVED` against this exact plan, accepted design,
      admitted/deferred feasibility result, and proposed routing.
- [x] Resolve every specification finding in the plan and repeat spec review.
- [x] Obtain distinct `L5_PLAN_QUALITY_APPROVED`.
- [x] Record accepted-for-execution status and both ordered tokens without
      changing scope.
- [x] Rebase the exact L5 plan/routing hunks onto the then-current shared
      baseline, preserving concurrent Q and owner changes.
- [x] Update only exact L5 plan-gate routing expectations and run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Obtain final ordered specification then quality reaffirmation against
      the exact plan/status/routing snapshot.
- [x] Commit those reviewed bytes before production changes.
- [x] Capture a fresh pre-L5 control:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Record plan-gate `HEAD`, tree, totals, and exact failures in this plan.

## Task 1: Collision-Safe Five-Field Reference Rows

**Outcome:** Existing direct-call navigation uses the accepted immutable
semantic row without behavior change, and every target/occurrence collision is
explicitly rejected rather than overwritten.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`

- [x] Run and record the mandatory collision/consumer audit command from
      "Collision And Identity Contract."
- [x] Add `test_definition_links_are_frozen_five_field_semantic_rows` and
      assert exact direct procedure/workflow values plus immutability.
- [x] Add
      `test_definition_link_rejects_unknown_reference_and_target_kinds`,
      parameterized over one unknown `reference_kind` and one unknown
      `target_kind`. Construct the frozen row directly and require `ValueError`
      from its constructor before passing the row to any index helper.
- [x] Add
      `test_reference_projection_collapses_only_identical_duplicate_facts`
      for duplicate target facts and duplicate rows.
- [x] Add
      `test_reference_projection_rejects_target_and_occurrence_collisions`
      covering different definition spans, target kinds, and canonical
      targets at one kind-aware occurrence key.
- [x] Add
      `test_reference_projection_rejects_cross_kind_assertions_at_one_span`
      proving two different `reference_kind` assertions at the same canonical
      path/start/end span fail the whole index.
- [x] Add
      `test_reference_projection_preserves_same_spelling_across_namespaces_at_distinct_spans`
      proving prompt/procedure/workflow labels and target keys do not merge
      when their authored occurrences have different spans.
- [x] Run the new nodes and confirm RED because the current row has only
      `callee_span` and `definition_span` and silently assigned definition-map
      entries are unaudited.
- [x] Replace `DefinitionLink` with the closed five-field row; update direct
      call projection, sorting, lookup, and collision-safe insertion only.
      Put closed-domain validation in `DefinitionLink.__post_init__` (or its
      exact immutable-constructor equivalent), not in
      `_insert_unique_reference_link`.
- [x] Keep direct call selection and returned definition locations byte-for-
      byte equivalent at the protocol boundary.
- [x] Run GREEN:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py::test_definition_links_are_frozen_five_field_semantic_rows \
    tests/test_workflow_lisp_lsp_navigation.py::test_definition_link_rejects_unknown_reference_and_target_kinds \
    tests/test_workflow_lisp_lsp_navigation.py::test_reference_projection_collapses_only_identical_duplicate_facts \
    tests/test_workflow_lisp_lsp_navigation.py::test_reference_projection_rejects_target_and_occurrence_collisions \
    tests/test_workflow_lisp_lsp_navigation.py::test_reference_projection_rejects_cross_kind_assertions_at_one_span \
    tests/test_workflow_lisp_lsp_navigation.py::test_reference_projection_preserves_same_spelling_across_namespaces_at_distinct_spans \
    tests/test_workflow_lisp_lsp_navigation.py::test_definition_resolves_only_exact_direct_authored_call_heads \
    tests/test_workflow_lisp_lsp_navigation.py::test_same_canonical_name_resolves_in_distinct_callable_namespaces \
    tests/test_workflow_lisp_lsp_navigation.py::test_null_or_generated_call_provenance_is_never_indexed
  ```

- [x] Obtain `L5_TASK1_SPEC_APPROVED`, then distinct
      `L5_TASK1_QUALITY_APPROVED`, and commit only the exact reviewed two-file
      snapshot.

## Task 2: Exact Direct Prompt-Application Head Projection

**Outcome:** Direct authored local and imported prompt application heads
navigate from the exact head token to the canonical authored `defprompt`.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Add:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l5_authored_refs/lsp_l5/definitions.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l5_authored_refs/lsp_l5/entry.orc`

The fixture must define prompt, procedure, and workflow members with the same
raw label and include direct prompt applications spelled:

- local `local-review`;
- unqualified imported `shared`;
- alias-qualified `defs.shared`;
- canonical-module-qualified `lsp_l5/definitions/shared`; and
- an import constrained by `:only`.

It must also retain same-label procedure/workflow direct-call controls without
requiring runtime execution.

- [x] Add `test_prompt_application_heads_project_exact_semantic_rows` and
      assert every five-field row, canonical prompt target, and exact authored
      `defprompt` span.
- [x] Add
      `test_prompt_application_navigation_supports_local_alias_canonical_and_only_spellings`
      and assert all spellings reach the one canonical target without
      cross-family substitution.
- [x] Add
      `test_prompt_application_navigation_is_exactly_head_token_bounded` with
      first and last token code units positive and opening delimiter, end
      boundary, adjacent whitespace, fill keyword/value, and closing delimiter
      null.
- [x] Add
      `test_prompt_application_projection_fails_closed_on_join_drift`,
      parameterized over missing syntax match, duplicate syntax match, wrong
      syntax kind, whole-span mismatch, canonical identity mismatch, absent
      prompt catalog target, differing definition span, expanded occurrence,
      and generated/expanded definition.
- [x] Add
      `test_original_prompt_syntax_without_final_application_is_not_discovered`
      by removing the final typed assertion while retaining original syntax.
- [x] Confirm the positive tests RED because no prompt rows exist; ensure
      pre-existing direct-call controls remain GREEN.
- [x] Implement the recursive original-syntax view and prompt projection
      exactly as specified, without changing shared traversal or frontend
      files.
- [x] Run GREEN:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py::test_prompt_application_heads_project_exact_semantic_rows \
    tests/test_workflow_lisp_lsp_navigation.py::test_prompt_application_navigation_supports_local_alias_canonical_and_only_spellings \
    tests/test_workflow_lisp_lsp_navigation.py::test_prompt_application_navigation_is_exactly_head_token_bounded \
    tests/test_workflow_lisp_lsp_navigation.py::test_prompt_application_projection_fails_closed_on_join_drift \
    tests/test_workflow_lisp_lsp_navigation.py::test_original_prompt_syntax_without_final_application_is_not_discovered \
    tests/test_workflow_lisp_lsp_navigation.py::test_definition_has_no_whole_form_or_other_identifier_fallback
  ```

- [x] Run fixture/compiler adjacency without changing it:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_modules.py
  ```

- [x] Obtain `L5_TASK2_SPEC_APPROVED`, then distinct
      `L5_TASK2_QUALITY_APPROVED`, and commit only exact reviewed navigation,
      test, and valid-fixture paths.

## Task 3: Narrow Final-Retained Proc-Ref Projection

**Outcome:** Only an unexpanded final `ProcRefLiteralExpr` in a direct authored,
non-generated, non-specialized owner navigates from its exact name token to the
canonical authored `defproc`.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Reuse the Task-2 valid L5 fixture.

- [x] Extend the fixture with retained proc-ref occurrences using the local,
      unqualified import, alias-qualified, canonical-qualified, and `:only`
      spellings listed in Task 2.
- [x] Add `test_retained_proc_ref_names_project_exact_semantic_rows` and assert
      exact row fields, canonical procedure targets, and authored `defproc`
      spans.
- [x] Add
      `test_retained_proc_ref_navigation_supports_local_alias_canonical_and_only_spellings`.
- [x] Add `test_retained_proc_ref_navigation_is_exactly_name_token_bounded`
      with first/last in-token positions positive and opening delimiter,
      `proc-ref` head, whitespace, exact name end, and closing delimiter null.
- [x] Add
      `test_proc_ref_projection_rejects_missing_multiple_kind_identity_and_span_mismatch`
      covering absent and duplicate original lists, non-`proc-ref` head,
      non-identifier/missing name, extra item, authored-name mismatch,
      canonical-target mismatch, missing procedure definition, differing
      definition span, and invalid token containment.
- [x] Add
      `test_proc_ref_projection_rejects_expanded_matching_original_syntax`.
      Give the otherwise exact matching original `(proc-ref NAME)` list a
      non-empty expansion stack and require navigation-index construction to
      raise rather than omit or accept the retained occurrence.
- [x] Add
      `test_proc_ref_projection_rejects_generated_or_expanded_catalog_definition`,
      parameterized over a matching procedure-catalog target whose definition
      has `generated_local_procedure` set and one whose definition has a
      non-empty `expansion_stack`. Each retained occurrence must fail the whole
      index rather than become null through a silently missing target.
- [x] Add
      `test_proc_ref_projection_excludes_erased_expanded_generated_and_specialized_occurrences`.
      Prove independently: original syntax with no final occurrence; non-empty
      occurrence expansion stack; generated local-procedure owner; expanded
      owner; specialized procedure owner; and specialized workflow owner.
- [x] Add
      `test_macro_consumed_proc_refs_and_macro_heads_have_no_l5_rows` using the
      real `review_revise_design_docs.orc` compile result. Assert both
      macro-consumed proc-ref tokens and the macro head remain absent while its
      direct call control remains present.
- [x] Confirm the retained positive tests RED and all excluded-shape tests
      GREEN before implementation. Confirm the two malformed-join tests above
      are RED because the current index does not yet reject those inconsistent
      retained facts, then GREEN only after fail-closed validation lands.
- [x] Implement the proc-ref projection only in the existing authored-owner
      traversal after owner filters. Do not scan syntax for occurrences and do
      not add macro support.
- [x] Run GREEN:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py::test_retained_proc_ref_names_project_exact_semantic_rows \
    tests/test_workflow_lisp_lsp_navigation.py::test_retained_proc_ref_navigation_supports_local_alias_canonical_and_only_spellings \
    tests/test_workflow_lisp_lsp_navigation.py::test_retained_proc_ref_navigation_is_exactly_name_token_bounded \
    tests/test_workflow_lisp_lsp_navigation.py::test_proc_ref_projection_rejects_missing_multiple_kind_identity_and_span_mismatch \
    tests/test_workflow_lisp_lsp_navigation.py::test_proc_ref_projection_rejects_expanded_matching_original_syntax \
    tests/test_workflow_lisp_lsp_navigation.py::test_proc_ref_projection_rejects_generated_or_expanded_catalog_definition \
    tests/test_workflow_lisp_lsp_navigation.py::test_proc_ref_projection_excludes_erased_expanded_generated_and_specialized_occurrences \
    tests/test_workflow_lisp_lsp_navigation.py::test_macro_consumed_proc_refs_and_macro_heads_have_no_l5_rows \
    tests/test_workflow_lisp_lsp_navigation.py::test_null_or_generated_call_provenance_is_never_indexed
  ```

- [x] Run unchanged compiler adjacency:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_procedures.py \
    tests/test_workflow_lisp_macros.py
  ```

- [x] Obtain `L5_TASK3_SPEC_APPROVED`, then distinct
      `L5_TASK3_QUALITY_APPROVED`, and commit only exact reviewed navigation,
      test, and valid-fixture hunks.

## Task 4: Visibility, Compiler Refusal, And Common Preflight Matrix

**Outcome:** Successful compiler visibility produces exact family-separated
edges, compiler-rejected visibility produces no snapshot, and every existing
definition availability branch applies identically to prompt/proc-ref rows.

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Add:
  `tests/fixtures/workflow_lisp/modules/invalid/lsp_l5_private/lsp_l5/private_definitions.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/invalid/lsp_l5_private/lsp_l5/entry.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/invalid/lsp_l5_ambiguous/lsp_l5/alpha.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/invalid/lsp_l5_ambiguous/lsp_l5/beta.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/invalid/lsp_l5_ambiguous/lsp_l5/entry.orc`
- Modify production only if this task exposes a Task-1/2/3 defect; route the
  fix back through that owning task's fresh TDD and ordered reviews.

- [x] Add
      `test_l5_same_visible_label_never_cross_substitutes_prompt_procedure_or_workflow`
      over the valid fixture.
- [x] Add
      `test_l5_private_and_ambiguous_imports_fail_through_compiler_authority`
      over both invalid fixture roots; assert compiler diagnostic, no accepted
      current snapshot, and definition null rather than an LSP-resolved target.
- [x] Add
      `test_l5_definition_rows_share_the_complete_current_snapshot_preflight`,
      parameterized across `prompt-application` and `proc-ref` and every state
      in "Common Availability And Null Matrix." Reuse production state
      transitions/probes; do not handwave several states into one label.
- [x] Add
      `test_l5_navigation_index_failure_is_logged_once_and_all_definition_shapes_are_null`
      by forcing a collision/join failure after current compile success. Assert
      no diagnostics mutation, no fallback index, no workspace write, and
      direct call/prompt/proc-ref all null.
- [x] Add
      `test_l5_unsupported_generated_and_outside_token_requests_are_null`
      to close the remaining non-state null categories.
- [x] These integration-shaped tests should begin GREEN after Tasks 1–3. If
      any is RED, identify the owning defect and return it to that earlier task
      instead of patching around the preflight.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py
  ```

- [x] Obtain `L5_TASK4_SPEC_APPROVED`, then distinct
      `L5_TASK4_QUALITY_APPROVED`, and commit only exact reviewed test/fixture
      paths unless an owning-task correction completed its own review cycle.

## Task 5: Real Stdio Review-Workflow Gate

**Outcome:** A real repository editor session resolves the motivating prompt
head, keeps macro/proc-ref nulls, preserves the existing direct call hit, and
writes no source, build, run, or artifact state.

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify only if a transport-specific assertion belongs there:
  `tests/test_workflow_lisp_lsp_integration.py`
- Modify production only by routing a genuine defect back to Tasks 1–3.

- [x] Define repository constants for
      `workflows/examples/review_revise_design_docs.orc` and its checked-in
      provider/prompt manifest paths.
- [x] Add
      `test_real_repository_l5_authored_reference_navigation_is_read_only`.
      Launch the real stdio server with the workflow's actual source root,
      provider externs, and prompt externs in the server's supported null-entry
      library compilation mode. Do not select the runnable workflow entry:
      that activates the independent whole-callable-closure bootstrap policy,
      which is outside L5's authored-navigation contract and rejects this
      repository example before navigation becomes observable.
- [x] Request definition inside `review-design-doc` at its fragment
      application head and assert the returned location range is the full
      authored `defprompt` declaration `definition_span`, exactly as stored in
      the five-field row. Separately assert the request succeeds only inside
      the source application head's exact `reference_span`; the target is not
      a `defprompt` name-token selection range.
- [x] Request at the `review-revise-loop` macro head and both
      macro-consumed `(proc-ref review-design-docs)` /
      `(proc-ref fix-design-doc)` name tokens; assert all three results are
      null.
- [x] Request the existing direct `(call build-review-runtime-owned)` callee
      and assert its authored `defworkflow` location remains exact.
- [x] Probe opening delimiters, exact token ends, adjacent arguments, and one
      fill keyword to ensure stdio exposes no whole-form fallback.
- [x] Snapshot source/manifests/prompt assets and `.orchestrate/build` before
      launch; after shutdown assert byte identity, unchanged build-tree digest,
      and no new run/artifact state.
- [x] This gate should begin GREEN after Tasks 1–4. Route any failure back to
      its owner and repeat TDD/reviews.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_lsp_stdio.py
  ```

- [x] Obtain `L5_TASK5_SPEC_APPROVED`, then distinct
      `L5_TASK5_QUALITY_APPROVED`, and commit only exact reviewed E2E/integration
      test paths unless an owning-task correction completed separately.

## Task 6: Durable Baseline Merge, Routing, And Closure

**Outcome:** The owning language-server baseline states the shipped durable L5
contract, the target amendment becomes an incorporated decision record, all
guidance/routing agrees on the admitted/deferred boundary, and fresh focused,
broad, and ordered review evidence closes L5.

**Files:**

- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify exact §76.1 compatibility wording:
  `docs/design/workflow_lisp_frontend_specification.md`
- Modify status/incorporation record:
  `docs/design/workflow_lisp_lsp_authored_reference_navigation.md`
- Modify exact shipped navigation text:
  `docs/workflow_lisp_language_server_setup.md`
- Modify exact editor navigation text:
  `docs/lisp_workflow_drafting_guide.md`
- Modify exact L5 row: `docs/capability_status_matrix.md`
- Modify exact L5 row: `docs/design/README.md`
- Modify exact L5 routes: `docs/index.md`
- Modify exact L5 row/section/sequence:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify exact L5 routing expectations:
  `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify factual evidence/status after all gates: this plan

- [x] Refresh and record the current baseline `HEAD`, tree, shared-file diff,
      and Q/owner routing state. Merge/reapply only exact reviewed L5 hunks;
      never replace a shared file wholesale with an older task snapshot.
- [x] Before closure edits, run the focused selector below and confirm the
      landed Tasks 1–5 plus existing routing are GREEN. A behavioral failure
      routes back to its owning Task 1–3; Task 6 does not absorb it.
- [x] Update exact routing expectations and their owning docs together for
      shipped L5 behavior, the prompt/direct-retained-proc-ref boundary,
      shape-wide macro deferment, erased/specialized proc-ref exclusion,
      preserved direct calls, accepted final review tokens, and the correct
      next L-series selector. Do not manufacture a routing RED as a Task-6
      milestone; the closure selector must remain GREEN.
- [x] Merge durable semantics, not tranche chronology, into
      `workflow_lisp_language_server.md`: five-field row, exact original-
      syntax/compiler-catalog joins, common preflight, collision refusal,
      authored-to-authored targets, and exclusions.
- [x] Update frontend §76.1 only to reflect that the read-only LSP consumes
      retained syntax/catalog facts; do not define a second compiler contract.
- [x] Mark the L5 target doc implemented/incorporated while retaining macro
      identity and erased/specialized proc-ref shapes as explicit future
      retention gaps.
- [x] Update setup/drafting docs with only user-observable exact prompt-head
      and retained-proc-ref navigation. Do not imply all macros or all proc-refs
      navigate.
- [x] Keep principles 29 and 30 intact: no type-taxonomy advice and no prompt
      prose/provider obligation.
- [x] Run collection and focused gates:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py

  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Run the active roadmap's exact broad non-security command in tmux:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

- [x] Record collection/pass/failure/error/skip totals and classify every
      retained failure against the fresh pre-L5 control. Do not repair,
      rebaseline, or waive unrelated failures under L5.
- [x] Run `git diff --check` and search exact L5 routes for stale
      proposed/review-pending/conditional-macro wording.
- [ ] Obtain `L5_FINAL_SPEC_APPROVED` against the exact implementation,
      evidence, baseline, and routing snapshot.
- [ ] Obtain distinct `L5_FINAL_QUALITY_APPROVED`.
- [ ] Commit only the exact reviewed Task-6 baseline, guidance, routing, test,
      and plan bytes without post-review edits. Tasks 1–5 production, fixture,
      and behavioral-test commits remain the implementation record.
- [ ] Verify the commit tree and rerun focused routing plus the repository-real
      L5 E2E from committed `HEAD`.

### Pre-Review Task 6 Execution Record

This record is factual through the exact pre-review Task 6 candidate. The
post-candidate broad comparison is complete. Ordered final reviews, the
reviewed closure commit, and postcommit verification remain pending.

- The Task 6 baseline is commit
  `ba7bc148db9e95ebe0b48ddc6ff23e0ec6c80610`, tree
  `1c3b24f08c511c902d379ef205eb76daa907a6ab`. Task 6 changes only the eleven
  paths named above and preserves the Q3 closure, Q5 plan, owner, and lean-pilot
  bytes already present in that tree.
- Tasks 1–5 landed as collision-safe reference rows `95e05c01`, authored
  prompt heads `042c0bc3`, direct-retained proc-ref navigation `870f7db2`,
  visibility/preflight and repository-real preflight coverage `7233138a`, the
  real-stdio compile-profile plan correction `52930d09`, and repository-real
  stdio navigation `041754e6`.
- The fresh pre-L5 control collection selected 9,944 of 9,962 nodes with 18
  deselected; its log SHA-256 is
  `3126cb7a58e589809f1f5d9fbe210cebde6c12a261d164d5e93986ee4ebceca1`.
  The bound broad control completed in 155.03 seconds with 9,885 passed, 38
  failed, 21 skipped, zero errors, and 33 warnings; its log SHA-256 is
  `88f7760414abcc18391ffbc07b87cd2c9e080bff810b462b68c99aa725c344c7`.
  The 38 failures are the same retained set as the immediately preceding Q3
  comparison, including its already-isolated xdist-only LSP race.
- Task 6 introduces no compiler/frontend, runtime, prompt, provider,
  completion, symbol, or non-navigation production change. The durable
  baseline now records immutable five-field rows, exact original-syntax/
  compiler-catalog joins, collision refusal, common-preflight ownership,
  authored-to-authored targets, and the admitted/deferred shape boundary.
- The exact four-module collection selected 212 tests in 2.13 seconds. The
  exact seven-module focused selector passed 479 tests in 47.12 seconds,
  including 60/60 active-roadmap routing tests after replacing the stale L5
  plan-gate expectations with the completed-stage and still-gated-L3 contract.
- The immutable preliminary Task 6 candidate is
  `57fb43beda71fa1661e6ff8af0ae0a7bdf2a8c4f`, tree
  `4333d42bf21a7079ebe18c0aac4cd13585481ec8`, with the bound baseline as its
  exact parent. Post-candidate collection selected 9,944 of 9,962 nodes with
  18 deselected in 14.73 seconds; its log SHA-256 is
  `7fb9ab6fee1f3baf00a00100a22188d6f7a0feb9b0c066a15f2649a5091a0b27`.
  The post-candidate broad suite completed in 154.14 seconds with 9,885 passed,
  38 failed, 21 skipped, zero errors, and 33 warnings; its log SHA-256 is
  `ec7822993d64e818531f0f289c26d64f85609e0298be43511168239268a1d210`.
  The exact sorted `FAILED` node set has zero difference from the bound pre-L5
  control, so L5 introduces zero new broad failures. This broad evidence binds
  the preliminary behavior/routing candidate. The replacement changes exactly
  two documentation paths: this factual plan/status record and
  `docs/design/workflow_lisp_lsp_authored_reference_navigation.md` for the
  final-spec prompt-only/macro-deferment correction. Neither correction changes
  a test or behavior blob; the other nine Task 6 paths remain byte-identical to
  the preliminary candidate.

## Completion Gate

L5 is complete only when:

- prompt application and retained proc-ref rows contain all five exact semantic
  fields and navigate only from exact authored token spans;
- local, alias-qualified, canonical-qualified, and `:only` successful cases
  resolve through compiler catalogs;
- private/ambiguous imports fail through compiler authority;
- collision, missing, multiple, kind, identity, and span mismatches fail the
  whole navigation index;
- every common preflight/null state remains null for both new shapes;
- erased, macro-consumed, expanded, generated-owner, and specialized-owner
  proc-refs remain null;
- macro heads remain null shape-wide;
- existing direct procedure/workflow call behavior is unchanged and WCC/
  generated calls remain excluded;
- the real review-workflow stdio session proves prompt hit, macro/proc-ref
  nulls, preserved direct call, exact boundaries, and read-only operation;
- no compiler/frontend or non-navigation production file changed;
- the owning baseline and all exact routing surfaces agree on shipped versus
  deferred behavior;
- focused and broad evidence is recorded against a fresh control; and
- ordered final specification then quality reviews approve the exact committed
  tree.
