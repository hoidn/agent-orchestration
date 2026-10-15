# Workflow Lisp Judgment Views: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_judgment_views.md](../../design/workflow_lisp_judgment_views.md).

## Original delivery metadata

- **First consumer:** the implemented target-2.23 ordinary-composed panel
  sibling in the `review_revise_design_docs` family
- **Implementation evidence:** Tasks 1–8 landed through `000bfcfe`, with the
  separate prompt-asset correction at `187336f7` and implicit-list ecosystem
  correction at `0187392f`; focused verification passed 643 tests, the new
  module collected 91 tests, and the broad closure comparison reported
  11,072 passed, 5 failed, 24 skipped, and 33 warnings
- **Closure-comparison disposition:** the five failures are four inherited
  route/retirement rows plus one xdist-only LSP read-only build-digest race;
  the LSP row passes in isolated replay
- **Review provenance:** ordered external `Q4_TASK_9_SPEC_APPROVED`,
  `Q4_TASK_9_QUALITY_APPROVED`, `Q4_FINAL_SPEC_APPROVED`, then
  `Q4_FINAL_QUALITY_APPROVED` are bound by closure-record SHA-256
  `85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`;
  this document records rather than self-attests them
- **Design review order:** independent `Q4_DESIGN_SPEC_APPROVED`, then
  independent `Q4_DESIGN_QUALITY_APPROVED` (both approved against commit
  `d7fe454902ff2f5b5784a66c37fbb19f9332e4ac`)

## Selected Generic-Reviewer Panel

### Module and target

The implementation preserves the current target-2.23
`review-revise-design-docs` entry's phased prompt, result, identity-v2,
functional-v3, and runtime behavior. The required layout is a target-2.23
sibling module in the same example family that imports the existing
`review-design-doc` declaration and uses it only from an explicit ordinary
`:delivery :composed` call. The current production module may add only the
four names required by the maintained compile proof to its export surface:

```lisp
(export
  review-revise-design-docs
  DesignDocPath
  ReviewReportTargetPath
  WorkReportPath
  review-design-doc)
```

`DesignDocPath`, `ReviewReportTargetPath`, and `WorkReportPath` are referenced
by the fragment's closed fill contract; exporting the fragment without those
types is not a viable import surface. The production module's target, existing
entry body, and phased behavior remain unchanged.

The export line necessarily changes the production source bytes. Task 2
characterization found that the current compiler carries that source change
through two distinct kinds of lineage:

- the exact source SHA-256 appears in the workflow checksum, the prompt
  dependency contract, and digests derived from those values; and
- the additional export bytes shift later source offsets. The current
  parametric-specialization identity includes those offsets, so the parent
  loop's generated specialization, WCC, step, checkpoint, allocation, and
  source-map subject identifiers are consistently alpha-renamed.

Q4 does not migrate that compiler-wide identity scheme and does not normalize
the changed parent identities into a compatibility claim. They are a
disclosed cross-source-revision incompatibility. The implementation gate owns
the closed test projection `q4_task2_export_compatibility.v1`, containing
exactly:

- `schema_version = "q4_task2_export_compatibility.v1"`;
- the target DSL;
- the production entry name, public inputs, and public result contract;
- the phased helper's provider-call policy, compiled fragment identity,
  prompt-attempt identity version, canonical fragment contract, expected
  outputs, and variant result contract;
- the phased helper's complete runtime plan and complete source-map row; and
- the parent entry's ordered checkpoint point kinds and authored form
  paths/line/column coordinates, with generated subject keys excluded.

That projection must be byte-identical before and after the export edit. It
does not contain the module export catalog, raw source digests, generated
parent identities, or digests derived from those identities, and therefore
makes no claim about them.

The helper bundle has one separately closed source-lineage exception. A
recursive canonical diff must contain exactly six changed leaves, all named
`compiler_prompt_dependency_contract.source_workflow_sha256`, at these
authoritative locations:

1. `surface.steps[0]`;
2. `core_workflow_ast._surface_workflow.steps[0]`;
3. `core_workflow_ast.body[0]`;
4. `core_workflow_ast.body[0]._surface_step`;
5. the helper provider node's executable-IR `execution_config`; and
6. the helper prompt surface in semantic IR.

Every before value is the bound old source SHA-256 and every after value is
the bound new source SHA-256. Any seventh leaf, different field name,
different value, or missing row fails the gate. This exact diff is the
source-lineage characterization; Q4 adds no reusable normalizer or digest
manifest.

The source-position relation is exact. The old and new production sources are
8,079 and 8,149 bytes respectively. Apart from the intentionally changed
export span, every current-production position before that span remains
exact; every position after it retains the same path, line, and column and
has `after.offset == before.offset + 70`. Imported and prelude positions
remain exact. The gate checks this relation over every source position
reachable from the selected compiled projection, including the type
references that seed specialization identity.

The gate additionally requires, without normalization:

- the target, public inputs and result contract, phased delivery,
  materialization-attempt count, prompt fragment identity-v2, functional-v3
  schema, provider configuration, and phased-helper checkpoint/runtime plan
  to remain exact;
- the complete named projection, the exact six-leaf helper diff, parent
  checkpoint topology and point kinds, every authored form path, and the
  complete source-position relation above, to remain exact; and
- the frozen target-2.21 fixture to remain byte-identical to the pre-Q5 source
  retained by `bb67f680` and remain absent from the sibling's import graph.

This is not a claim that a run compiled from the pre-export source can resume
against the post-export source. Ordinary workflow-checksum validation rejects
that cross-source-revision resume before lexical restoration, and Q4 does not
weaken it. The Task 0 census established that no active Q5 orchestrator or
provider attempt is stranded by landing the source revision. Any semantic
delta in the named projection, any helper diff outside the exact six leaves,
any phased-helper checkpoint/runtime-plan delta, any
source-position-relation delta, or any frozen-control delta stops
implementation and returns to Q4 design. Copying the fragment under a new
identity or changing compiler/runtime checksum semantics is not a fallback.

### Lens contract

The panel input is an ordered `List[String]` of lens identifiers. Each
identifier is:

- non-empty;
- a safe relative child accepted by `path/join-under`;
- meaningful as the `review_focus` text shown to the reviewer; and
- pairwise distinct within one panel invocation.

The outer iteration derives its typed Q2 report target and passes it to the
child with:

```lisp
(path/join-under ReviewReportTargetPath lens)
```

Unsafe or escaping identifiers fail through the existing
`path_join_under_child_invalid` or `path_join_under_escape` rule before that
child provider launches.

Pairwise uniqueness is an explicit caller precondition, not a runtime claim.
The current language has no distinctness/set operator, and existing Q2
destination collision validation compares positions within one provider
invocation, not destinations across separate list iterations. Q4 does not
weaken or misdescribe that boundary. The public example ships a checked,
pairwise-distinct default lens set, documents that overriding callers must
preserve uniqueness, and tests the observed duplicate-destination behavior as
a contract limitation. Adding runtime distinctness or a paired
`List[Record]` input is a separately reviewed language change, not a hidden
Q4 prerequisite.

### Per-lens and synthesis behavior

For each ordered lens:

1. the outer `list/map-effect :max 8` makes exactly one child workflow call;
2. the child executes the existing fragment-backed review provider;
3. the provider returns the existing `ReviewDecision` and writes its Q2-bound
   report;
4. the child matches every existing variant to `review_report`; and
5. the child returns `ReviewReportPath`.

The ordered map result is exact `List[ReviewReportPath]`. One synthesis
provider consumes only that report-path list and the ordinary review subject.
The sibling declares the load-bearing final record:

```lisp
(defrecord DesignDocPanelResult
  (reports List[ReviewReportPath])
  (synthesis ReviewReportPath))
```

The synthesis boundary is exact and deliberately not Q4-eligible:

```lisp
(provider-result providers.design-docs.synthesize
  :prompt prompts.design-docs.synthesize
  :inputs (target_doc reports)
  :model synthesis_model
  :effort synthesis_effort
  :timeout-sec 3600
  :returns ReviewReportPath)
```

`prompts.design-docs.synthesize` is an extern prompt, not a `defprompt`
fragment application. It therefore has no compiled fragment contract or
identity-v1 Q3 carrier and fails the Q4 eligibility predicate before locator
construction. It writes and returns the ordinary domain synthesis report but
does not create a second judgment row or matrix. The panel returns
`DesignDocPanelResult` containing the ordered per-lens paths and synthesis
path.

Q3/Q4 digests, locator fields, matrix layout, and disagreement statuses never
enter the synthesis prompt under principle 30. Making synthesis
fragment-backed or judgment-inspectable would be a separate Q4 design
extension, not an implementation choice.

The panel does not revise the target document. Existing
`review-revise-loop` semantics remain in the original entry. A panel-driven
revision policy would require a separate design.

## Original status and provenance

- **Status:** implemented and complete for the bounded target-2.23
  explicit-composed sibling and read-only inspection surface at commit
  `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
  `ccec170be8757c9e4fd5ed8ece6f93b04fc03299`; the production target-2.23
  phased call remains Q4-ineligible
