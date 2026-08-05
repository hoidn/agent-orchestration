# ES F1 Witness Observability Correction Implementation Plan

**Status:** Implementation prerequisite. Ordered review and execution status are
recorded by the owning large-scope refreeze plan; canonical Task-0 evidence must
not precede this plan's approved closure.

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Do not create a worktree. Use strict TDD and do not publish a canonical policy,
> census, baseline, selector, A1 anchor, or feasibility capture while this plan is
> incomplete.

**Goal:** Replace line-only and post-import witness credit with deterministic,
occurrence-level evidence for the exact required F1 coverage sample while
retaining every discovered consumer and preserving the exact nineteen-module
provider-visible pytest lane.

**Architecture:** Keep `boundary_proofs.py` as the sole proof runner. Add one
explicit controller-only aggregate pytest selector and one shared CPython 3.11
source-event observer used by provider pytest, controller pytest, and residual
isolated probes. The observer starts before project imports and credits only an
exact PEP-657 opcode position, a compiler-verified import alias, or an actual
callable entry. A non-authoritative `observe-candidates` pass proposes executable
witness payloads; a reviewed policy remains the only authority.

**Tech stack:** Python 3.11 in `ptycho311`, `sys.settrace` opcode events,
`dis`, `ast`, canonical JSON, JSON Schema, pinned Git/Python identities, pytest,
and the existing Task-0 proof/census machinery.

---

## 1. Authority and observed defect

This plan is subordinate to:

- `docs/plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md`;
- `docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md`;
- `docs/design/workflow_lisp_program_search_boundaries.md`; and
- the owner-directed F1 calibration target of 5,000–10,000 physical
  implementation-delta lines, with tests and docs additional.

Fresh deterministic discovery contains 1,948 leaves, 1,959 consumers, and 236
matched paths. The non-authoritative recommendation currently proposes:

| Proof route | Consumers | Defect |
| --- | ---: | --- |
| provider pytest runtime | 834 | call-phase line hits cannot distinguish same-line occurrences and miss module/class/import scope |
| isolated runtime probe | 714 | every row lacks a concrete executable action; tracing begins after import |
| compatibility static | 342 | payloads still need exact, non-vacuous span-scoped queries |
| removal static | 69 | payloads still need exact path-absence queries |

Seventy-one routed consumers occupy thirty-three shared-line groups. At least
ninety-six proposed provider-pytest and forty-six proposed probe rows are scoped
to module, class, import, or regex-definition events. Thirty-eight proposed
runtime `Name` rows have no exact runtime position, primarily postponed
annotations. A line hit, owning-function hit, import of a module, or a strategy
placeholder is not evidence for any of those occurrences.

The discovery pair and the recommendation remain non-authoritative. This plan
does not adopt any disposition, grant any provider call, or consume an F1 arm.

## 2. Binding invariants

1. `provider_visible_pytest_selectors` remains exactly the existing nineteen
   rows in the existing order. Its aggregate argv remains exactly:

   ```text
   <pinned-python> -m pytest -q -p no:cacheprovider <exact nineteen modules>
   ```

2. Controller selector IDs, additional module paths, argv, node IDs, trace
   digests, and results never enter provider-visible selector serialization,
   task-profile visible-check bytes, or provider packets.
3. Add exactly one controller-only aggregate pytest selector,
   `CO-PYTEST-01`. Its ordered 71-module array is frozen in Section 7 with
   canonical-array SHA-256
   `sha256:3fa404d5a7b653218d77a884c0c363c8216a4b016343df2391777a9ed71bb62e`:
   the nineteen provider modules in their existing order followed by the
   fifty-two additional candidate-driver modules in UTF-8 path order. Every
   path and projection blob is an `input_bindings` row. Do not implement
   set-cover or dynamic optimization. Provider and controller selector IDs,
   witness assignments, processes, reports, and result tables are disjoint;
   private reuse of the nineteen module paths is permitted and does not merge
   the lanes.
4. Install the shared observer before any project import and keep it active
   through bootstrap, collection, setup, call, teardown, and session finish.
5. Runtime credit requires exactly one of these closed source events:

   - `opcode_exact_span`: an allowed semantic opcode has one PEP-657 position
     exactly equal to the discovered AST span. The closed AST/opcode table is:
     `Call -> CALL | CALL_FUNCTION_EX`, load `Name -> LOAD_NAME | LOAD_GLOBAL |
     LOAD_FAST | LOAD_DEREF | LOAD_CLASSDEREF`, store `Name -> STORE_NAME |
     STORE_GLOBAL | STORE_FAST | STORE_DEREF`, delete `Name -> DELETE_NAME |
     DELETE_GLOBAL | DELETE_FAST | DELETE_DEREF`, load `Attribute -> LOAD_ATTR |
     LOAD_METHOD`, store `Attribute -> STORE_ATTR`, delete `Attribute ->
     DELETE_ATTR`, and string `Constant -> LOAD_CONST`. Any other AST context or
     opcode is unsupported;
   - `import_alias_opcode`: the exact source blob has a one-to-one AST import
     alias to pinned-CPython instruction mapping, using statement span, semantic
     import argument, alias order, and instruction offset; or
   - `callable_entry`: the exact regex consumer span joins to exactly one
     `FunctionDef` or `AsyncFunctionDef` header in the bound blob, then to an
     observed `call` frame by filename, `co_qualname`, `co_name`, and
     `co_firstlineno`.

6. Span overlap, line containment, function ownership, or another occurrence on
   the same line never grants credit. Consumers may share one event only when
   their discovered spans are byte-for-byte identical.
7. Provider and controller pytest events bind a phase in `bootstrap |
   collection | setup | call | teardown`. Setup, call, and teardown bind exactly
   one full-matched collected node; bootstrap and collection bind one exact
   selector module. The observer remains installed through session finish for
   origin/tree integrity, but `session_finish` events never satisfy a consumer.
   A provider witness uses kind `pytest_runtime`; a controller witness uses the
   distinct kind `controller_pytest_runtime`.
8. Residual probes use a closed action union and trace before import:

   ```json
   {
     "action":"import_module",
     "module":"package.module",
     "expected_outcome":{"status":"returned"}
   }
   ```

   or:

   ```json
   {
     "action":"call",
     "module":"package.module",
     "callable":"qualified_name",
     "args":[],
     "kwargs":{},
     "return_value":"ignore",
     "expected_outcome":{"status":"returned"}
   }
   ```

   Arguments and keyword values use the repository's canonical transportable
   JSON subset: null, Boolean, string, integer, arrays, and string-keyed objects;
   floats and non-finite numbers are rejected. `module` and every `callable`
   segment must be identifiers, and `callable` resolves from that imported
   workspace module before invocation. Each action binds an
   `expected_outcome` of exactly `{"status":"returned"}` or
   `{"status":"raised","exception_type":"qualified.name"}`. Tracing begins
   before import and remains active through resolution and invocation. A raised
   action may qualify only when the declared raised outcome matches and the
   exact event occurred before the exception. Arbitrary return objects and
   exception messages are not serialized; `return_value` is always the literal
   `ignore`.
9. The observer is pinned to the already-bound CPython 3.11 executable. Missing
   positions, ambiguous import compilation, unsupported opcodes, incomplete
   actions, unresolved callables, forbidden origins, source-tree writes, missing
   nodes, skipped/unhit consumers, or nondeterministic results fail closed.
   For this gate, a source-identity write is any touch of a frozen Git-tree blob
   leaf or any persistent Git-visible index/worktree change, including an
   unignored addition. Repository-ignored runtime artifacts outside the frozen
   leaf set are permitted, remain non-authoritative, and are neither silently
   cleaned nor added to evidence.
10. Every consumer remains in the census and retains its exact source blob,
    tree, match, and span identity. Each consumer also carries `selector_id`,
    `witness_kind`, `coverage_status` in exactly `required | inherited | open`,
    and zero or one `coverage_witness_ids`. The selector policy carries the
    literal sampling rule
    `first_observable_per_provider_and_disposition_witness_class_in_discovery_order.v1`.
    Its exact `required` set is the ordered union, with consumer-ID
    deduplication, of the first observable consumer for every provider selector
    and the first observable consumer for every
    (`proposed_disposition`, `witness_kind`) class. A provider selector has
    exactly one witness backpointer; a controller selector has zero or one.
    The witness, desired-proof specification, executed-proof, and witness-result
    consumer domains equal that exact required set. An observable consumer not
    selected by the rule is `inherited`; an unresolved or unobserved consumer
    is `open`. Both carry zero witness backpointers and remain disclosed,
    nonblocking rows. A class with no observable representative blocks its
    required sample, but an individual open row does not. The separate
    candidate-declared fifteenth architecture and its lifecycle witness belong
    to the later refreeze/evaluator lifecycle and are not a Task-0 coverage
    consumer or an extra member of this required set.

### Closed source-event records

All source spans are closed records with `line_start`, `column_start`,
`line_end`, and `column_end`. Columns are the CPython UTF-8 byte offsets used by
the AST and PEP-657 APIs. A runtime witness specification contains
`event_kind`, `phase`, and exactly one attribution record:

- `{"attribution_kind":"pytest_node","pytest_node_pattern":"..."}` for
  setup/call/teardown;
- `{"attribution_kind":"selector_module","pytest_module_path":"..."}` for
  bootstrap/collection; or
- `{"attribution_kind":"residual_action","action_sha256":"sha256:..."}` for
  an isolated probe, whose phase is `residual` rather than a pytest phase.

The rich selector witness derives `source_event_binding` as the closed record
`event_kind`, `phase`, and the resolved exact attribution (a full node ID, module
path, or action digest). The observed `source_event` repeats that binding and
adds `consumer_path`, `caller_object_id`, the exact consumer `span`, and a
positive integer `hit_count`. Its final member is exactly one event payload:

- `opcode_exact_span`: `code_qualname`, `code_firstlineno`,
  `instruction_offset`, `opname`, and `argrepr_sha256`;
- `import_alias_opcode`: `code_qualname`, `code_firstlineno`, exact
  `statement_span`, zero-based `alias_ordinal`, nullable `module`, nullable `name`,
  nullable `asname`, nonnegative `level`, `instruction_offset`, `opname` in `IMPORT_NAME |
  IMPORT_FROM | IMPORT_STAR`, and exact string `argval`; or
- `callable_entry`: `code_qualname`, `code_name`, `code_firstlineno`, and exact
  `definition_span`.

For imports, `module` is the imported name for `Import` and the nullable
`ImportFrom.module` for `ImportFrom`; `name` is null for `Import` and the alias
name for `ImportFrom`. Compile the bound blob with its bound path, recursively locate the
single owning code object, and map aliases in source order: each `Import` alias
maps to its corresponding `IMPORT_NAME`; each named `ImportFrom` alias maps to
its `IMPORT_FROM` after the statement's one `IMPORT_NAME`; and a sole `*` maps
to `IMPORT_STAR`. A missing or multiply matching code object, instruction,
alias, offset, semantic argument, or source position fails closed. Duplicate
runtime hits are retained as `hit_count`; two independent captures must agree.

## 3. Closed contract changes

No canonical Task-0 policy or selector record exists, so amend the unaccepted
v1 schemas in place rather than introduce compatibility versions.

`preedit-policy-manifest.schema.json` must:

- require the literal `sampling_rule` above and require every consumer policy
  to carry `selector_id`, `witness_kind`, `coverage_status`, and zero-or-one
  `coverage_witness_ids`, with exactly one ID only for `required`;
- require controller selector `execution_kind` in
  `pytest_aggregate | isolated_probe | static_ast`;
- keep `pytest_runtime` provider-only and add the distinct
  `controller_pytest_runtime` witness kind;
- require pytest witness phase and the appropriate exact module/node binding;
- replace the old probe shape with the closed action union above; and
- require pytest-aggregate argv to use the pinned prefix plus explicit canonical
  selectors, with every additional driver module digest-bound in
  `input_bindings`;
- require one closed `pytest_carrier` binding in `selector_policy` with exact
  executable path, version, and raw SHA-256; and
- require `witness_observability_reviews`, binding this plan's raw digest, all
  three approved review-record raw digests, their exact verdicts, and the
  canonical implementation-candidate-set digest.

`preedit-selector-manifest.schema.json` must:

- add derived `source_event_binding` to rich runtime witnesses;
- add separate `controller_selector_results` to baseline characterization,
  including controller argv, collected nodes/digest, outcomes, origin isolation,
  trace digest, witness backpointers, and zero-or-one
  `coverage_witness_node_outcomes` rows. A row binds the selected witness ID and
  exact pytest node ID to literal `passed`; it is empty only for a
  selector-module bootstrap/collection witness or a selector with no witness;
- require every pytest origin-isolation record to repeat the verified
  `pytest_carrier` identity;
- add the validated `source_event` to runtime witness-result rows; and
- leave provider `aggregate_pytest_argv`, collected nodes, outcomes, and the
  exactly nineteen provider `selector_results` unchanged.

The source-census schema retains every consumer row and adds the same
`selector_id`, `witness_kind`, `coverage_status`, and zero-or-one
`coverage_witness_ids` contract. The mapping
`route_through_boundary -> boundary_runtime`,
`compatibility_adapter -> non_cdi_static`, and
`remove -> reference_absence` remains unchanged and is validated against the
(`proposed_disposition`, `witness_kind`) class assignment. Across the rich
selector, proof, and result schemas, consumer domains are exact only for
`coverage_status=required`; `inherited` and `open` consumers retain source
identity without acquiring witness/spec/proof/result rows.

Add `source_census.provider_visible_selector_projection(record)` as the sole
production serializer of provider-visible selector authority. It returns only
the nineteen ordered provider rows and their aggregate argv, is used by
`build_selector_manifest`, and is the API later task-profile/package builders
must consume. The controller canary tests this called production path rather
than a hand-built subset.

The three durable review records are canonical JSON at:

- `artifacts/review/es-f1-witness-observability-plan-spec-review.json` with
  verdict `ES_F1_WITNESS_PLAN_SPEC_APPROVED`;
- `artifacts/review/es-f1-witness-observability-plan-quality-review.json` with
  verdict `ES_F1_WITNESS_PLAN_QUALITY_APPROVED`; and
- `artifacts/review/es-f1-witness-observability-implementation-review.json`
  with `review_kind=implementation` and verdict
  `ES_F1_WITNESS_IMPLEMENTATION_APPROVED`.

Each is a closed `es_f1_witness_observability_review.v1` record containing
`review_kind`, `verdict`, nonempty `reviewer`, offset-bearing `reviewed_at`, an
ordered `candidate_files` array of `{path,sha256}`, its canonical
`candidate_set_sha256`, and `findings` (empty on approval). Plan reviews bind
this plan and the parent prerequisite paragraph. Their existing approvals
remain standing section/file-scoped; this owner-directed coherence correction
does not request or restart them. The records continue to name the exact bytes
they actually reviewed and are not rewritten to imply review of the corrected
lines; the owner-directed correction is the authority for those lines. The one
implementation review binds the three schemas, the census and boundary-proof
producers, the focused projection probe amended by the Task-6 concurrency
correction, and all three corresponding focused test modules. It checks both
specification conformance and implementation quality. The plan quality review
may not predate the plan specification review,
and the implementation review may not predate either plan approval or its
complete candidate; each record binds the exact bytes it reviewed; and
`reviewer` states the reviewing session and its relationship to the author —
a reviewer operated by the plan's author is recorded as a self-check.
`candidate_set_sha256` is the SHA-256 of the repository canonical-JSON encoding
of the `candidate_files` array including its final newline.
`source_census publish-policy` consumes the three paths and literal raw digests,
validates those rules, and writes their bindings into the policy's
`witness_observability_reviews`; `build-census` then verifies that closed policy
field before producing the census. For the two retained plan approvals,
publication validates each record's internal candidate-set digest and the exact
historical plan digests it truthfully records; it does not require those
historical digests to equal the owner-corrected current plan bytes. The separate
`--expected-plan-sha256` binds the current owner-corrected plan. The one
implementation review must bind the current implementation candidate exactly.

At correction closure, run the single independent implementation review once.
It is the one proportionate implementation-review pass for this nested
correction. Do not repeat it absent a material finding in its candidate.
Unchanged plan sections and their existing review standing are not reopened.

## 4. Implementation sequence

### Task 0: Retain the accepted prerequisite-plan standing

**Files:** this plan and the linked prerequisite wording in the large-scope
refreeze plan.

- [x] The recorded specification then quality plan reviews already approve the
  prerequisite. Their section/file-scoped standing is retained.
- [x] The exact canonical plan-review records named above remain the review
  authority. This owner-directed cardinality correction does not request or
  restart either plan review.
- [x] Task 1 may proceed under that retained standing. Only the one
  proportionate implementation-review pass named above remains at closure.

### Task 1: RED the schemas and executable witness joins

**Files:**

- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json`
- `scripts/experiments/es/boundary_proofs.py`
- `scripts/experiments/es/source_census.py`
- `tests/experiments/test_es_source_census.py`
- `tests/experiments/test_es_boundary_proofs.py`

- [x] Add failing tests for closed controller execution kinds, provider versus
  controller pytest witness lanes, phase/node rules, the residual action union,
  controller result rows, source-event rows, the exact required-set domains,
  provider exactly-one and controller zero-or-one backpointers, explicit
  `inherited`/`open` rows, and rejection of the old placeholder probe shape.
- [x] Add a provider-serialization canary containing controller-only IDs, paths,
  node IDs, argv, and digests; require every canary byte to be absent from the
  provider-visible projection.
- [x] Preserve the exact nineteen provider rows and prove controller rows cannot
  be substituted into them.
- [x] First run the new selectors against the unmodified implementation and
  retain the expected failures; only then change either producer or schema.
- [x] Update the boundary parser and shared fixtures in this task so the new
  closed records can be constructed. Task 2 supplies observation semantics;
  Task 1 must not leave the suite broken on an intentionally stale parser.

Run:

```bash
pytest --collect-only -q \
  tests/experiments/test_es_boundary_proofs.py \
  tests/experiments/test_es_source_census.py
pytest -q \
  tests/experiments/test_es_boundary_proofs.py \
  tests/experiments/test_es_source_census.py \
  -k 'controller or source_event or runtime_probe or provider_visible'
```

Expected before implementation: collection succeeds and the new assertions
fail for the missing contract.

### Task 2: Implement the shared exact source-event observer

**Files:** `scripts/experiments/es/boundary_proofs.py` and
`tests/experiments/test_es_boundary_proofs.py`.

- [x] Build one observer used by provider pytest, controller pytest, and residual
  probes; do not fork three tracing implementations.
- [x] Add and run every listed RED case against the Task-1 parser before adding
  observer behavior; record at least one expected failure from each event family.
- [x] Enable opcode events only for exact bound target files. Map `f_lasti` to the
  pinned code object's PEP-657 position and an allowed semantic opcode.
- [x] Parse and compile the exact bound source blob for import aliases. Reject a
  missing, multiple, reordered, or semantically mismatched instruction mapping.
- [x] Record lifecycle phase and node/module attribution without converting a
  collection event into a call event.
- [x] Start residual tracing before module import. Resolve call targets only from
  the declared workspace module and closed action payload.
- [x] Normalize only verified runtime-owned temporary paths, preserving all
  origin-isolation and source-tree identity checks.

Required RED/GREEN cases:

- two calls and two names on one line, where executing the first never credits
  the second;
- multi-alias imports, including a failure before a later alias;
- ambiguous AST-to-bytecode import mapping;
- module and class body execution during bootstrap/collection;
- exact setup/call/teardown node attribution;
- postponed annotations receiving no runtime event;
- regex definitions passing only on callable entry; and
- missing PEP-657 positions or unsupported opcodes failing closed.

Run:

```bash
pytest -q tests/experiments/test_es_boundary_proofs.py \
  -k 'source_event or exact_span or import_alias or callable_entry or phase'
pytest -q tests/experiments/test_es_boundary_proofs.py
```

### Task 3: Add the controller aggregate and residual action execution

**Files:** the same schemas, runner, census builder, and two focused test modules.

- [x] Execute the provider nineteen-module aggregate exactly as before.
- [x] Add and run controller-process, residual-action, tamper, and leak RED cases
  before implementing either execution path.
- [x] Execute `CO-PYTEST-01` in a separate fresh process from its explicit
  controller-only argv and bindings. Never append controller modules to the
  provider argv.
- [x] Collect and validate controller nodes, outcomes, origin facts, trace digest,
  and witness backpointers separately.
- [x] Treat the frozen controller aggregate as a diagnostic driver, not an
  all-green acceptance suite. Disclose and replay-bind unrelated failed and
  skipped node outcomes; any collection/runtime error or pytest exit greater
  than one still fails closed. A node-attributed selected witness is eligible
  only when that exact collected node executed and passed. A selector-module
  bootstrap/collection witness has no node-outcome row and remains eligible only
  after complete error-free collection.
- [x] Execute remaining `import_module` and `call` actions in isolated fresh
  processes under the same origin/tree checks.
- [x] Merge no raw controller identity into provider-visible output. Preserve
  controller evidence in `controller_selector_results` and source-event-bound
  witness results.

Required coverage includes one controller process proving several consumers,
selected-node skipped/failed/uncollected/unhit rejection, an unrelated
failed/skipped negative control that remains disclosed and non-gating,
controller argv/module tamper, residual action incompleteness,
import-before-trace regression, and complete provider canary exclusion.

Run:

```bash
pytest -q \
  tests/experiments/test_es_boundary_proofs.py \
  tests/experiments/test_es_source_census.py \
  -k 'controller or residual or provider_visible'
```

### Task 4: Implement non-authoritative candidate observation

**Files:** the same runner/census files and tests; `.tmp/` outputs are generated
and never committed.

- [x] Add `boundary_proofs observe-candidates`. It consumes literal fresh
  discovery bytes, the frozen extract/tree, draft dispositions, explicit
  controller argv, runner/Python identities, and forbidden roots.
- [x] Emit canonical deterministic diagnostic JSON with no `record_sha256`, no
  adoption field, and zero or more exact executable event choices per consumer.
- [x] Select recommendations in this order: provider exact event, controller
  exact event, explicit residual action, individually justified static/removal
  reclassification, otherwise unresolved.
- [x] Reject any row whose consumer/match/blob/span differs from the discovery or
  whose event cannot be replayed.
- [x] Require every observable recommendation to replace `spec_strategy` with
  a closed executable payload. Retain unresolved or unobserved rows explicitly
  as open candidates without inventing a payload, while the complete output
  remains `NON_AUTHORITATIVE`.
- [x] Add and run RED CLI, replay, unresolved-row, stale-digest, and
  nondeterminism tests before implementing the command.
- [x] Close the triggered concurrent-host-pytest fixture race before evidence
  capture. Two rejected attempts proved that independent pytest sessions can
  delete shared absolute `/tmp` fixtures while a child is running. Launch every
  pytest child through the explicit, digest-bound bubblewrap carrier with a
  private tmpfs at `/tmp`; retain the exact inner pytest argv and do not retry a
  failed child. Closure requires both-direction carrier identity/setup tests and
  a concurrent same-absolute-temp-name isolation test. This is a generic
  reproducibility prerequisite covered by the one Task-6 implementation review,
  not a new plan or review lifecycle.
- [x] Close the triggered name-only origin false positive before recapture. A
  controller diagnostic loaded a forbidden-prefix module whose complete origin
  set was inside the frozen projection. Treat a matching module name as an
  origin failure only when it has no absolute recorded origin or any recorded
  origin lies outside the bound workspace; projected-only origins remain
  admissible. Closure requires both-direction projected/missing/external-origin
  tests while retaining forbidden-root and outside-project rejection.

The command contract is exact. `--draft-dispositions` accepts only the current
`NEUTRAL_RECOMMENDATION_ONLY` record. The runner contains the literal Section-7
tuple and refuses to start unless its canonical-array digest matches Invariant
3. It also verifies the explicit bubblewrap executable, version, and raw digest,
runs every pytest child with a private tmpfs at `/tmp`, and binds that carrier
identity in the normalized origin facts and candidate input bindings.
`--report-path` receives normalized diagnostic details, while `--output`
receives the closed
`es_f1_witness_observation_candidates.v1` record with input bindings, counts,
and exactly 1,959 rows in discovery order. Run twice in `ptycho311` through
tmux (using distinct exclusive output/report paths):

Replay equality includes the exact selected source events and every stable
execution and origin-enforcement fact. Each child report retains its full raw
module-origin inventory, but replay comparison excludes that diagnostic-only
inventory because third-party runtimes generate random temporary module names.
Projected, forbidden, and outside-project origin rows remain exact replay gates.

```bash
/home/ollie/miniconda3/envs/ptycho311/bin/python \
  -m scripts.experiments.es.boundary_proofs observe-candidates \
  --discovery-input docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.json \
  --expected-discovery-input-sha256 sha256:f2a3c88c5720c08d94af4ff7eabd08a89bc50f874560b4506d7376348c217074 \
  --discovery-output .tmp/es-f1-source-census-discovery-1.json \
  --expected-discovery-output-sha256 sha256:12a603ff2d8a3370b28a74d34a828bfe716917ce7d1f4a70af6961b45aa373b4 \
  --draft-dispositions .tmp/es-f1-policy-path-decisions-candidate.json \
  --expected-draft-dispositions-sha256 sha256:332eb78805cfcd922726012a3f21f763088a2386b5626a4695a316acf6299abc \
  --python /home/ollie/miniconda3/envs/ptycho311/bin/python \
  --pytest-carrier /usr/bin/bwrap \
  --expected-pytest-carrier-sha256 sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712 \
  --workspace <ABSOLUTE_FROZEN_PREEDIT_EXTRACT> \
  --expected-tree e64f3c05f5a0894f41c047d128a9040a2cda6764 \
  --expected-runner-sha256 sha256:8c61723916447207f3f8a5819cf0fb5b70c8e7b82c400bad9e8b4667138a3872 \
  --forbidden-root /home/ollie/Documents/PtychoPINN \
  --report-path <REPO_ROOT>/.tmp/es-f1-witness-observation-report-1.json \
  --output <REPO_ROOT>/.tmp/es-f1-witness-observation-candidates-1.json
```

Repeat with suffix `2`, then run:

```bash
cmp -s .tmp/es-f1-witness-observation-candidates-1.json \
  .tmp/es-f1-witness-observation-candidates-2.json
```

The command exits 2 on any input mismatch, ambiguous replay, source-identity
write as defined above, or nondeterministic normalized row. Its successful output remains
`NON_AUTHORITATIVE`, has no `record_sha256` or adoption field, and cannot
publish a canonical policy.

### Task 5: Classify and validate all 1,959 candidate policy rows

**Files:**

- `.tmp/es-f1-witness-observation-candidates-{1,2}.json`
- `.tmp/es-f1-policy-path-decisions-candidate.json`
- `.tmp/es-f1-complete-policy-candidate-{1,2}.json`

- [x] Review every unresolved, ambiguous, postponed-annotation, detector-collision,
  compatibility, and removal row. Do not infer a disposition from path naming.
- [x] Apply the literal sampling rule from Invariant 10. Require an adopted
  payload and matching desired proof for the first observable consumer of every
  provider selector and the first observable consumer of every
  (`proposed_disposition`, `witness_kind`) class, then union and deduplicate in
  discovery order. Mark exactly that domain `required`; mark other observable
  rows `inherited` and unresolved or unobserved rows `open`.
- [x] Require every consumer to retain `selector_id`, `witness_kind`, and its
  source blob/tree identity. Require exactly one consumer and provider-selector
  witness backpointer for `required`, zero for `inherited`/`open`, and zero or
  one for each controller selector. A class with no observable representative
  blocks; an individual open row otherwise does not.
- [x] Run `source_census complete-policy-candidate` twice from the two
  byte-identical observation files and require byte-identical complete candidate
  outputs. Pass one identical, explicit offset-bearing no-consumption capture
  timestamp to both runs and the exact absolute A1 evidence root; neither value
  may be inferred from wall-clock time, filesystem metadata, or an ambient
  default. The command freshly verifies the frozen no-consumption scope and all
  thirteen closed A1 member bindings. It accepts no review or adoption fields
  and emits no `record_sha256`.
- [x] Record any unresolved or unobserved consumer with
  `coverage_status=open` and continue. Do not convert a failure into a static
  proof merely to complete the domain.

The exact candidate command is:

```bash
/home/ollie/miniconda3/envs/ptycho311/bin/python \
  -m scripts.experiments.es.source_census complete-policy-candidate \
  --discovery-input docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.json \
  --expected-discovery-input-sha256 sha256:f2a3c88c5720c08d94af4ff7eabd08a89bc50f874560b4506d7376348c217074 \
  --discovery-output .tmp/es-f1-source-census-discovery-1.json \
  --expected-discovery-output-sha256 sha256:12a603ff2d8a3370b28a74d34a828bfe716917ce7d1f4a70af6961b45aa373b4 \
  --observation-candidates .tmp/es-f1-witness-observation-candidates-1.json \
  --expected-observation-candidates-sha256 sha256:12971db8888e42b2030c113256f84116319b63ae0382bb2339a72029619b3822 \
  --reviewed-dispositions .tmp/es-f1-policy-path-decisions-candidate.json \
  --expected-reviewed-dispositions-sha256 sha256:332eb78805cfcd922726012a3f21f763088a2386b5626a4695a316acf6299abc \
  --no-consumption-captured-at 2026-08-04T17:40:24-07:00 \
  --a1-evidence-root /home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7 \
  --producer-sha256 sha256:e7f419f140ab7125dd4900ae5dc4bb9c3491c1e4157f2e1733f446c4cfd7c4f7 \
  --proof-runner-sha256 sha256:8c61723916447207f3f8a5819cf0fb5b70c8e7b82c400bad9e8b4667138a3872 \
  --output .tmp/es-f1-complete-policy-candidate-1.json
```

Repeat with suffix `2` inputs/outputs and require `cmp -s` equality. A success
requires `total=1959`, every row classified exactly once as `required`,
`inherited`, or `open`, no `spec_strategy` key on an observable row, exact
witness/spec/proof/result consumer-domain equality with the required set,
provider-selector exactly-one and controller-selector zero-or-one
backpointers, replayable source events for required rows, and no
controller-canary byte in `provider_visible_selector_projection`. The
candidate-declared fifteenth architecture is not counted in this Task-0
consumer coverage domain.

### Task 6: Close the correction and resume Task 0 evidence

- [x] Run both focused modules, then all five Task-0 modules:

  ```bash
  pytest -q \
    tests/experiments/test_es_source_census.py \
    tests/experiments/test_es_boundary_proofs.py \
    tests/experiments/test_es_feasibility_lifecycle.py \
    tests/experiments/test_es_feasibility_proofs.py \
    tests/experiments/test_es_reference_calibration.py
  ```

- [x] Run the routing test and `git diff --check`.
- [x] Run one end-to-end fixture named
  `test_occurrence_observability_end_to_end_all_lanes_and_desired_replay` that
  combines provider pytest, controller pytest, static proof, import action, call
  action, and desired-state replay in one closed contract.
- [x] Run the broad non-security suite in tmux and retain the result in the
  implementation review candidate:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_secrets.py \
    --ignore-glob='tests/test_provider_isolation*.py' \
    --ignore=tests/test_provider_launch_shim.py
  ```
- [x] Emergent concurrency correction trigger: two capacity-valid broad runs
  reproduced five failures in the exact projected baseline while the same
  205-test child passed in isolation, and a deterministic two-process fixture
  reproduced one shared-`/tmp` failure. Closure: route the projection origin
  probe through the already-verified private-`/tmp` carrier, retain the frozen
  projection inputs and report shape, and add `scripts/experiments/es/projection.py`
  plus `tests/experiments/test_es_f1_projection.py` to the one implementation
  review candidate. The focused concurrency fixture passes with both child
  probes at exit zero. The additional broad ignores implement the user's
  standing exclusion of security work; they do not waive any non-security test.
- [x] Obtain one independent implementation review that checks specification
  conformance and implementation quality together, then write the one canonical
  implementation-review record. This is the single proportionate review pass
  for the nested correction. Do not repeat it absent a material finding, and do
  not reopen unchanged plan, bootstrap, or tree-order findings. The first pass
  approved the then-current nine-file candidate. The Task-7 producer-metadata
  incident below is a material finding that invalidates that standing only for
  `source_census.py` and its test; one replacement pass over the exact current
  candidate closes the gate without reopening either ordered plan review.

### Task 7: Publish canonical authority only after implementation approval

- [x] Record the failed first publication attempt without adding a recovery
  schema. Policy raw digest
  `sha256:f32c442d8df9c9348206c7d767ec7623bae527209f12927a48fc4b83365b6ae8`
  was exclusively published, then the first census build failed before any
  census, baseline, selector, control file, run root, or evidence root existed.
  A disposable independent rescan proved that all 1,948 leaves and all
  candidate bytes were identical; only the non-authoritative discovery
  producer digest differed because `source_census.py` had received the reviewed
  candidate-set update before publication. Preserve the failed policy and its
  review/candidate inputs under `.tmp/es-f1-task7-discovery-producer-incident/`.
  Treat the failed policy as unconsumed and superseded, never as authority.
- [x] Close the incident by comparing every projection-derived discovery field
  while treating the captured producer digest as historical metadata, still
  requiring the exact producer path and a valid digest. Continue to validate
  the current census producer independently. Keep the negative control that any
  leaf/candidate/input drift fails with `discovery_recompute_mismatch`, obtain
  the one material-change review replay above, then replace only the unconsumed
  failed policy through the same exclusive publisher.

- [x] Reobserve finite no-consumption roots and current schema/lineage bindings.
- [x] Run `source_census publish-policy` from the byte-identical complete
  candidate plus all three approved review records. The command verifies the
  plan/review/candidate-set bindings and exclusively publishes
  `preedit-policy-manifest.json`; it is the only producer that adds
  `record_sha256`.
- [ ] Build `source-census.json` twice and require byte identity.
- [ ] Run `boundary_proofs bootstrap-baseline` twice in tmux and require complete
  byte identity, including separate provider/controller origin, trace, and
  result tables.
- [ ] Resume the large-scope plan at A1, feasibility capture, selector, ordered
  Task-0 reviews, purge, and machine adoption. No canonical authority file may
  predate the approved implementation-review record.

Run publication with no implicit path or review discovery:

```bash
/home/ollie/miniconda3/envs/ptycho311/bin/python \
  -m scripts.experiments.es.source_census publish-policy \
  --candidate .tmp/es-f1-complete-policy-candidate-1.json \
  --expected-candidate-sha256 <COMPLETE_CANDIDATE_RAW_SHA256> \
  --plan docs/plans/2026-08-04-es-f1-witness-observability-correction-plan.md \
  --expected-plan-sha256 <OWNER_CORRECTED_PLAN_RAW_SHA256> \
  --plan-spec-review artifacts/review/es-f1-witness-observability-plan-spec-review.json \
  --expected-plan-spec-review-sha256 <PLAN_SPEC_REVIEW_RAW_SHA256> \
  --plan-quality-review artifacts/review/es-f1-witness-observability-plan-quality-review.json \
  --expected-plan-quality-review-sha256 <PLAN_QUALITY_REVIEW_RAW_SHA256> \
  --implementation-review artifacts/review/es-f1-witness-observability-implementation-review.json \
  --expected-implementation-review-sha256 <IMPLEMENTATION_REVIEW_RAW_SHA256> \
  --policy-schema docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json \
  --output docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.json
```

`publish-policy` recaptures the three exact no-consumption roots already named
by the parent plan, requires them absent or empty, requires the four prospective
repository paths absent, validates the result against the policy schema, and
uses exclusive creation. Any existing differing output is a hard failure.

## 5. Rejected shortcuts

- Hand-authoring 714 function calls does not solve import-time or same-line
  evidence and creates brittle fixture taxonomy.
- Opcode tracing only the nineteen provider modules leaves the extra consumers
  without a driver.
- AST rewriting or injected markers executes modified source rather than the
  frozen tree.
- Treating every unobserved occurrence as compatibility/static weakens the
  reviewed disposition contract.
- Adding a selector optimizer or generic experiment framework is out of scope.

## 6. What this makes harder later

Baseline and desired-state evidence will take longer because the private
aggregate runs additional tests under opcode tracing. A Python interpreter
upgrade requires an explicit observer refreeze because import mapping is bound
to CPython 3.11 bytecode and PEP-657 positions. Source/test refactors can
invalidate exact source-event and driver bindings, requiring Task-0 digest
regeneration. A disposition/witness class without any observable representative
now blocks instead of receiving optimistic coverage. Individual unresolved or
unobserved consumers remain disclosed as nonblocking `open` rows; preserving
every such row and its source identity is the intended audit cost.

## 7. Frozen `CO-PYTEST-01` module order

The canonical compact JSON encoding of this exact array, including its final
newline, has the SHA-256 stated in Invariant 3. The first nineteen rows
deliberately repeat the provider lane as private drivers; the remaining
fifty-two are sorted by UTF-8 path bytes.

```json
[
  "tests/torch/test_generator_registry.py",
  "tests/torch/test_construction_consolidation.py",
  "tests/torch/test_generator_adapter.py",
  "tests/torch/test_config_bridge.py",
  "tests/torch/test_model_spec.py",
  "tests/torch/test_model_spec_v2.py",
  "tests/torch/test_lightning_checkpoint.py",
  "tests/torch/test_artifact_schema.py",
  "tests/torch/test_artifact_schema_v2.py",
  "tests/torch/test_workflows_components.py",
  "tests/torch/test_fno_generators.py",
  "tests/torch/test_fno_lightning_integration.py",
  "tests/torch/test_neuralop_uno_generator.py",
  "tests/torch/test_model_output_modes.py",
  "tests/torch/test_model_manager.py",
  "tests/torch/test_model_training.py",
  "tests/torch/test_train_lightning_execution_contract.py",
  "tests/torch/test_object_big_generator_contract.py",
  "tests/torch/test_structural_config_ownership.py",
  "tests/scripts/test_inference_backend_selector.py",
  "tests/scripts/test_training_backend_selector.py",
  "tests/studies/test_gain_calibration.py",
  "tests/studies/test_grid_lines_bridge_ladder.py",
  "tests/studies/test_position_reassembly_checkpoint_replay.py",
  "tests/studies/test_torch_ablation_configuration.py",
  "tests/test_acquisition_record.py",
  "tests/test_legacy_params_lifecycle.py",
  "tests/test_model_config_architecture.py",
  "tests/test_workflow_generator_integration.py",
  "tests/torch/test_absolute_scaling_contract.py",
  "tests/torch/test_absolute_scaling_dict.py",
  "tests/torch/test_absolute_scaling_entrypoints.py",
  "tests/torch/test_absolute_scaling_mmap.py",
  "tests/torch/test_amplitude_physics_gain.py",
  "tests/torch/test_ci_profile.py",
  "tests/torch/test_cli_inference_torch.py",
  "tests/torch/test_cli_train_torch.py",
  "tests/torch/test_compute_loss_c4_regression.py",
  "tests/torch/test_config_factory.py",
  "tests/torch/test_debug_fno_activations.py",
  "tests/torch/test_dict_container_physics_scale.py",
  "tests/torch/test_fno_integration.py",
  "tests/torch/test_grid_lines_c4_ci_integration.py",
  "tests/torch/test_grid_lines_ci_probe_roundtrip_integration.py",
  "tests/torch/test_grid_lines_position_reassembly_strategy.py",
  "tests/torch/test_grid_lines_torch_runner.py",
  "tests/torch/test_grid_lines_torch_runner_ci_inference.py",
  "tests/torch/test_grid_lines_torch_runner_grad_norm_flag.py",
  "tests/torch/test_hybres_extension_preconditions.py",
  "tests/torch/test_hybrid_checkpoint_cross_dataset_inference.py",
  "tests/torch/test_inference_cli_reassembly.py",
  "tests/torch/test_inference_normalization.py",
  "tests/torch/test_inference_reassembly_aggregation.py",
  "tests/torch/test_inference_reassembly_parity.py",
  "tests/torch/test_inline_dataset_amplitude_scaling_regression.py",
  "tests/torch/test_inline_dataset_rectangular_scaled_batched.py",
  "tests/torch/test_integration_workflow_torch.py",
  "tests/torch/test_lightning_dataloader_coords_guard.py",
  "tests/torch/test_loss_modes.py",
  "tests/torch/test_mlflow_recon_logging.py",
  "tests/torch/test_nphotons_resolution.py",
  "tests/torch/test_patch_stats_cli.py",
  "tests/torch/test_physics_scale_bundle.py",
  "tests/torch/test_physics_scale_container.py",
  "tests/torch/test_physics_scale_loss.py",
  "tests/torch/test_rect_probe_scale_double_div.py",
  "tests/torch/test_rect_s1s2_initialization.py",
  "tests/torch/test_rect_scaling.py",
  "tests/torch/test_rectangular_scaled_forward.py",
  "tests/torch/test_scale_parity.py",
  "tests/torch/test_varpro_probe_ablation_runner.py"
]
```
