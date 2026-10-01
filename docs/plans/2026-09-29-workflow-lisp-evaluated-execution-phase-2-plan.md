# Workflow Lisp Evaluated Execution, Phase 2: The Closed Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute this plan task by
> task, with `superpowers:test-driven-development` for every behaviour change
> and `superpowers:verification-before-completion` before any completion
> claim. One worktree per task. Tasks of one group touch disjoint files and
> may run in parallel only after their listed prerequisites are merged. Use
> the repository role assignments: Implementation Luna 6 xhigh, Review Sol 6.1
> high, Design Astra 6 xhigh, Planning Astra 6 high. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The compiler produces, for a program at the evaluated execution
target, the closed program that Phase 3's evaluator will run: whole,
calculus-only, with complete effect nodes, a site table, a checked form,
provenance outside identity, and a digest that is the program's identity.

**Architecture:** An evaluated-entry compilation stops after typecheck
throughout its source graph, including older imports, and never lowers to
steps. A new package `orchestrator/workflow_lisp/closed/`
takes the typed program, elaborates every reachable definition once with the
compiler's own elaborator and normal-form pass (both changed at the new target
only), and translates the result into a table of plain JSON definitions. The
elaborator is changed where a property of the closed program cannot be
obtained after it (callee bodies, effectful arguments, `done` values,
`continue` targets, `phase-target`); everything else is translation. The
flat route retains existing admission/lowering behavior. Raw byte equality
with identical identity inputs, and separately explained truthful package-pin
changes, are the compatibility evidence (Global Constraints).

**Tech Stack:** Python, the Workflow Lisp typechecker, the WCC elaborator
(`wcc/elaborate.py`) and normal form (`wcc/anf.py`), the pure expression
catalog (`orchestrator/workflow/pure_expr.py`), canonical JSON, pytest.

**Spec:** [evaluated execution](../design/workflow_lisp_evaluated_execution.md),
sections 1.1 (`closed_program_gap`), 4 (P1 to P7, the table of definitions,
the constructs, X1 to X4), 6 (I1 to I7), 7.3 (C1 for supplied and injected command bindings), 12
(codes) and 13 (targets). Facts: the
[execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md)
(A.1 to A.5). Evidence and measured sizes: the
[gate report](../reports/2026-09-29-evaluated-execution-spike.md), sections
4 and 7. The prototype of every task is the spike under
`experiments/evaluated_execution_spike/` (`closed.py`, `closed_effects.py`,
`sites.py`, `table.py`, `repairs.py`, `frontend.py`). Read it; do not import
it. The spike is not wired in and nothing of it is deleted by this plan.

---

## Status, Authorities And Scope

- Parent plan: [evaluated execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md),
  Phase 2 (milestones P1 to P7). Entry condition: gate G1, decided
  2026-09-29. Governing revisions: design commits `181e4ed9` and
  `9fa10443`, reconciled with all twelve independent Phase 2 review findings
  and the follow-up builtin-closure/recovery contracts. The implementation baseline is the
  actual clean base recorded before Task 1; `613993ad` is historical Phase 0
  evidence, not this revision's comparison base.
- The owner selected **2.35** on 2026-09-30, closing parent-plan decision 6
  after reviewing this plan. `PHASE2_BASE` is
  `2e4c7a653d74c06e24c15c284662e5914abd5576`, the integrated Phase 0 head.
  Task 1 registers the target in one gate constant; every later task and
  every fixture reads the number from that constant, never as a literal.
- In scope: the compiler's output at the new target and the manifest field
  `closure`; both command boundary kinds; portable composed providers with
  `asset_file`, `input_file` and all admitted `defprompt` slots; procedure and
  workflow calls including value/reference bindings, `bind-proc` captures and
  bounded `let-proc`; path-mode run references. Out of scope, Phase 3 and later: the evaluator, the memo,
  performers, coordinators, views, `run` and `resume` at the new target,
  typed input documents, `par-map`.
- Phase 2 does not make the new target runnable. `orchestrator run` and
  `orchestrator resume` refuse a program at the new target with
  `evaluated_execution_unavailable` (Task 1) until Phase 3 replaces the
  refusal with the evaluator's entry. `orchestrator compile` at the new
  target writes the closed program (Task 9).
- Two experiments run beside this plan and are not tasks of it: the owner's
  coordinator experiment (parent plan, decision 5) and the equality of the
  compiler's `PhaseCtx` and `phase-target` values with the present route's
  (design §19, item 4; open item of this plan).

## Global Constraints

Every task's requirements include these lines.

- Targets that exist today (2.34 and older) accept and lower exactly what
  they do at the commit the task starts from. Evidence: build the named
  programs at the base and at the head, with the program and the orchestrator
  package each at one fixed path and `PYTHONHASHSEED=0`; compare every build
  artifact byte by byte (the method of Task 0 of Phase 0: `git archive` of
  the base into a scratch directory, `python -m orchestrator compile` with
  every `--emit-*` flag, `diff -r` on the emitted files and on
  `.orchestrate/build/<key>/`). Raw equality is required for identical identity
  inputs. `compute_compiler_runtime_identity` hashes package files: a changed
  compiler revision legitimately changes the real pin and dependent run-ref
  artifacts. Preserve that pin and report those differences explicitly;
  separately compare raw serialization with the existing identity-provider
  seam fixed to the same input. Never normalize differences or call the
  controlled result a real-pin byte-equality pass. All task-level byte-equality
  instructions below use this rule. Evidence at integration `0c82e494` versus
  `PHASE2_BASE`: 12 of 67 pairs differ with real pins (all run-ref-dependent),
  while all 67 raw pairs match with fixed identity; plain/imported-manifest
  specimens match under real pins. This does not replace the task's fresh
  compatibility run after its changes.
- No generated identity introduced by this plan contains a source-file path,
  source position or `repr` of a type. Authored semantic paths (prompt
  bindings, run-ref sources, closure declarations and type roots) remain
  program content; explicitly absolute declarations stay location-bound. `repr(TypeRef)` never enters a name or a digest of
  the closed program (execution facts A.5).
- Every refusal has a code and a source location, and prints the value it
  refused and the limit it applied.
- Tests assert through the public compile entry (`compile_typed_program`,
  `build_closed_program`, `build_closed_program_bundle`, or
  `python -m orchestrator compile`): the closed program's content, sites,
  digests, and refusals by code and location. No test asserts prose or prompt
  text.
- No broad or full-suite test run while other agents share the machine.
  Narrow selectors, one module at a time, serial, with
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -p no:cacheprovider --basetemp=<scratch>/pytest`.
  One full run at the phase closeout, alone, in tmux.
- Reuse the existing signature, effect-summary, catalog, source-read and
  descriptor owners. Add no generic signature abstraction, fake validated
  bundle or extra compatibility layer. Keep the existing small `closed/`
  file responsibilities below; split only when concrete code needs it, not
  to satisfy arbitrary line or complexity limits. An admitted form that
  cannot be closed is a compiler defect to repair, never an extra release gap.
- Reviews record every finding. Only Critical evidence of observed silent
  wrong results, data loss or writes outside the workspace blocks the owner's
  review/merge gate; other findings are handled and recorded. Failing checks
  are repaired, not relabeled acceptable. Scope changes still need an
  explicit owner/design decision.
- Commit by pathspec (`git commit -m "<message>" -- <paths>`), after staging
  the task's created/changed files. Commit messages carry no tool
  or assistant attribution.
- The spike under `experiments/evaluated_execution_spike/` is read as the
  prototype and never imported by production code or by this plan's tests.
  Test fixtures needed from `tests/experiments/fixtures/evaluated_execution_spike/`
  are copied under `tests/fixtures/workflow_lisp/closed_program/`.

## Review Focus

Five input classes most likely to bite, each pinned by a test in the task
that owns the code.

1. One procedure called from three arms of one `match` inside a loop has
   one local `perform` site in its definition and three call frames, each
   with `<binder>=<callee>` and `loop:<param>[*]`. Moving the loop into a
   called workflow preserves that separation; calls never add site rows. Task 5 tests `arms_in_loop.orc`; Task
   4 tests the table form gives one definition for the callee.
2. A program moved to another path, and the orchestrator package moved to
   another path, must give the same sites and the same program digest; the
   artifact's provenance may differ. Task 7 tests provenance and digest on
   hand-written trees; Task 9 tests both moves through public compilation,
   including package relocation in a subprocess, on a specialized imported callee
   (`if_in_hook.orc`), whose names digest `repr(TypeRef)` today.
3. A manifest without `closure` must be refused at the new target with
   `command_boundary_closure_missing` naming the boundary and the manifest
   path, before any elaboration; at 2.34 the same manifest must build the
   artifacts it builds today. Task 4 tests the refusal in process, Task 9 at
   the manifest path, Task 7 the unchanged build at 2.34.
4. A form outside the first release (`materialize-view`,
   `resource-transition`, `trial`, `request-input`, a phased or supervised
   provider, a provider with `:capture-context`, a bundle-mode `run-ref`)
   must be refused with `closed_program_gap` at the form's own location,
   with the form named, and never as `compiler_defect`. Task 8 tests each
   form; Task 10 shows it on the corpus.
5. Two builds of one source, at two paths, with different `@` provenance in
   every node, must give one digest; and a tampered operator payload in the
   artifact must be refused when the artifact is read back. Task 7 tests
   both.

---

## The Closed Program's Form

Every task from 4 on reads and writes this schema. Code excerpts below
omit repeated typed/provenance fields for readability; actual fixtures must
fill every field required here and pass `validate`. It is the contract between
tasks; a task that needs another key adds it here first.

### The program

```json
{
  "schema": "workflow-lisp/closed-program/1",
  "representation": "table/1",
  "target": "<OWNER_SELECTED_TARGET>",
  "entry": "workflow:grt/entry::run",
  "params": [["seed", {"kind": "primitive", "name": "Int"}]],
  "defaults": {"seed": 1},
  "result": {"kind": "record", "name": "grt/entry::Box", "fields": [...]},
  "body": <body>,
  "types": {"grt/entry::Box": <canonical nominal descriptor>},
  "configuration": {"commands": <all canonical command bindings>, "providers": <all resolved provider bindings>, "prompts": <all resolved prompt bindings>, "imports": {"<configuration digest>": {"commands": <producer commands>, "providers": <producer providers>, "prompts": <producer prompts>}}},
  "definitions": {"<canonical callee name>": {"key": <canonical definition tuple>, "params": [["n", <descriptor>]], "result": <descriptor>, "body": <body>}},
  "sites": [["procedure:grt/entry::fetch", "#1"]]
}
```

- `params` lists the entry's declared parameters, hidden context parameters
  excluded (they are bound in the body, X1). `defaults` holds each declared
  default as its normalized value. Type descriptors are the compiler's
  normalized descriptor shapes, recursively canonicalized by Task 6. The
  existing descriptor builder alone is insufficient: private nominals also
  require `module::Name`. `types` holds the canonical definitions of every
  reachable nominal, including private and generated result types; all uses
  must match it. No source path is included.
- `definitions` holds one entry per canonical callee name (§4.2), procedures
  and called workflows alike. A body is stored once. An imported definition
  has `configuration: <configuration digest>` selecting a row in
  `configuration.imports`; absence selects root configuration. The digest is
  Task 7's canonical digest of the producer's normalized three-map
  configuration, with no nested `imports` member in that row. Nested imported
  owners select their own rows. Equal configurations share a row; every scope
  key resolves and every effect is checked in its definition's scope. Unequal
  source/captured context for one canonical callee is
  `compiled_workflow_snapshot_conflict` before interning, not a second identity.
- `sites` is the site table (P4): one `[definition, local path]` per
  `perform`, entry first then definitions in first-call order. Call frames
  stay on call nodes. `configuration` contains every parsed manifest binding
  (including unused entries) and compiler-injected bindings used by the
  program, normalized using the same rules as in-memory bindings; provenance and raw manifest bytes are excluded. Its semantic
  content enters `program_digest`, not just the build-cache key.

### Canonical command configuration

Ratified Task 5/7 clarification, 2026-09-30. Keep
`canonical_command_configuration(bindings, *, origins)` unchanged. The raw
signature strings belong to configuration identity; source type resolution
belongs to the frontend and retained caller environment. The reader checks
closed typed consistency and the mechanical correspondence below. It does
not independently reconstruct manifest-input assignability from type-name
spelling: `document` has no per-use expected input descriptor. No basename
comparison, source alias guess, second signature service or new source
restriction is introduced. The independent review and public private/alias/
generic-type proof are recorded in the Phase 2 execution handoff.

`configuration.commands` is a JSON object keyed by the supplied binding lookup
name. Each value has **exactly** the common fields below, plus the certified
fields only for `kind: "certified_adapter"`. All fields are present, including
nulls, false, and empty arrays. No dataclass `json_omit_*` policy controls this
new projection. No arbitrary unparsed manifest keys are copied.

| Common field | Exact JSON shape / source |
| --- | --- |
| `kind` | `"external_tool"` or `"certified_adapter"`, from actual binding class |
| `name` | binding's string `name`, preserved |
| `stable_command` | ordered string array from `stable_command` |
| `must_not_repeat` | exact boolean, including `false` |
| `closure` | canonical ordered array of exact `{ "base": string, "path": string }` rows below |
| `retirement_class` | string or null |
| `retirement_label` | string or null |
| `replacement_surface` | string or null |
| `bridge_owner` | string or null |
| `expiry_condition` | string or null |
| `evidence_refs` | ordered string array |
| `retirement_status` | string or null |

The outer key is lookup authority. Preserve `binding.name` rather than silently
rewriting it from the key. The existing in-memory environment does not enforce
equality of these two strings; this clarification adds no such admission rule.

| Certified-only field | Exact JSON shape / source |
| --- | --- |
| `input_contract` | JSON object, preserving its full nested content |
| `output_type_name` | raw declared string |
| `effects` | ordered string array |
| `path_safety` | JSON object, preserving its full nested content |
| `source_map_behavior` | string |
| `fixture_ids` | ordered string array |
| `negative_fixture_ids` | ordered string array |
| `behavior_class` | string or null |
| `input_signature` | ordered array of exact `{ "name": string, "type_name": string, "required": boolean, "transport_key": string }` rows |
| `artifact_contracts` | ordered string array |
| `state_writes` | ordered string array |
| `error_codes` | ordered string array |
| `owner_module` | string or null; metadata, not type-resolution authority |
| `replacement_path` | string or null |
| `invocation_protocol` | string or null; current promoted protocol is `"json_object_positional_arg"` |
| `transition_binding` | null or exact `{ "transition_name": string, "resource_kind": string, "contract_role": string, "backend_selector": string }` |
| `view_binding` | null or exact `{ "view_name": string, "renderer_id": string, "renderer_version": integer, "contract_role": string }` |
| `declared_promoted_fields` | sorted unique string array from the existing frozenset |

String spellings are preserved, including type expressions and metadata paths.
Current value/admission validation stays with existing owners. These tables do
not turn documentary metadata into proof of fixtures, artifacts, or filesystem
existence. Do not add enum restrictions or nonempty-string rules absent from
those owners. Arrays preserve order and multiplicity except the two explicit
set projections: closure and `declared_promoted_fields`. Nested tuples/mappings
become JSON arrays/objects; object key order is serialization-only. Values must
remain ordinary finite JSON data; no `repr`, absolute inferred package prefix,
or frontend Python object enters the row.

`declared_promoted_fields` cannot be discarded: actual field presence controls
`certified_adapter_supports_promoted_calls`, even when supplied values equal
model defaults. Fields omitted by the older fingerprint (`input_contract`,
fixtures, `view_binding`, retirement metadata) cannot be omitted here.

#### Closure normalization

Both boundary kinds use the same existing C1 declaration grammar: explicit
empty array is valid; missing/`None` refuses with
`command_boundary_closure_missing`; explicit manifest `null`, scalar values,
non-string entries, empty strings and NUL refuse with
`command_boundary_manifest_invalid`. Never replace absence with `[]`.

Normalize separators to POSIX spelling and discard empty/`.` components while
retaining every `..` component. Preserve an absolute leading root; an empty
relative component sequence becomes `.`. Thus `a//./b` becomes `a/b`, `a/../b`
stays `a/../b`, `/./` becomes `/`, and `./` becomes `.`. Stable command tokens
are not normalized. Paths are literal; there is no expansion, glob traversal,
exclusion syntax, filesystem read, symlink resolution, or content hashing here.

A normalized absolute declaration uses `base: "absolute"` with its absolute
path. Relative supplied bindings use `base: "workspace"`. Only trusted
compiler-injection origin supplies `base: "package:orchestrator"` for a relative
path. Sort rows lexicographically by `(base, path)` and remove exact duplicates;
overlapping directory/file declarations remain. A retained same-named manifest
override keeps workspace origin. Origin follows the effective binding instance; an
existing injector replacement has its own trusted origin. No user row or
guessed builtin name selects the package base. The reader requires this canonical shape/order, and rejects extra row
keys, unrecognized bases, noncanonical paths, or base/path absolute mismatches.

#### Small example

```json
{"fetch":{"kind":"external_tool","name":"fetch","stable_command":["python","probe.py"],"must_not_repeat":false,"closure":[],"retirement_class":null,"retirement_label":null,"replacement_surface":null,"bridge_owner":null,"expiry_condition":null,"evidence_refs":[],"retirement_status":null}}
```

A certified row is this common shape with its kind changed and every field in
the certified table added. There is no synthetic `return_contract`, resolved
signature, binding digest, origin field, or raw manifest wrapper in either row.
`output_type_name` is the existing return declaration; the resolved result
contract is already on each perform.

#### Writer and reader obligations

**Writer (Tasks 4/6/7).** Select the actual source-program owner, retained
procedure/workflow type environment and binding before conversion. Keep the
existing source checks: return spelling matches the adapter declaration;
supplied adapter inputs resolve and typecheck in that environment; required
inputs exist, extras refuse, and protocol projectability remains enforced.
Use resolved typed result/value facts and Task 6's canonical descriptor owner,
not basename comparison or `owner_module`. Emit `result` and the derived
`contract`, plus the existing `document` rows in declaration order over supplied
inputs. The closed compiler must not resolve unused bindings or omitted
optional signature entries merely to serialize configuration.

Project all supplied bindings, including unused ones, and only the injected
bindings used by the closed program. Preserve originating configuration for
compiled producers; apply the identical projection to root and producer
three-map configurations. Producer scope digesting/deduplication stays exactly
as the plan specifies. A raw semantic configuration edit changes identity even
when its binding is unused or its type string has equivalent source meaning.

**Reader (Task 5).** Validate every row's exact variant and nested shape, every
configuration scope and its digest, and every node/value descriptor against the
closed type table. At a command perform under the selected owner scope:

- Boundary lookup must succeed. `class` is `command` for both binding kinds;
  do not invent a separate adapter effect class.
- `command` equals `stable_command`; `closure` equals normalized closure;
  `repeat` is exactly `never` for true or `rerun` for false.
- `result` and `contract` must independently agree under the existing neutral
  structured-result contract/descriptor semantics. Result literals, enclosing
  results, field uses, nominal definitions and subsequent calls continue to be
  checked; two unchecked copied type labels are never proof.
- Raw argv mode has the existing typed `argv` tail and no `document`.
  Both external tools and certified adapters can use this mode when the
  existing source validators admit it. Never infer document mode merely from
  the certified binding class.
- Document mode requires the certified binding's existing promoted metadata
  predicate and admitted invocation protocol, `argv: []`, and a `document`
  projection matching `input_signature` transport keys in declared order.
  Required supplied fields are present, optional ones may be absent, and
  undeclared/excess rows refuse. Validate each value normally and its admitted
  protocol value shape. A malformed protocol retains the owner's existing
  boundary-validation meaning, not a new release exclusion.

The signature parser currently does not reject repeated input names or
transport keys. Preserve its ordered projection rather than adding uniqueness
as an implicit new source restriction. More precisely, valid document keys are
obtained by selecting a set of declared input names containing all required
names, then projecting every signature row whose name is selected, in order.
This also states the rule for repeated rows without inventing authored names
that the closed document does not store.

Do **not** compare raw type strings to canonical descriptor names, compare
basenames, derive a module from metadata, or add a special-case primitive
string resolver in the reader. The reader establishes closed typed consistency
and the correspondence above, not source-history authenticity. A manifest type
string changed alone remains a changed program identity; this contract does
not claim its previous source meaning can be recovered from the artifact.

### Canonical definition keys

This is the exact shared wire schema for design §4.2 and Tasks 4–8.
The [design](../design/workflow_lisp_evaluated_execution.md#42-a-table-of-definitions)
owns the semantic requirements; all producers and readers use this one
representation, including hand-written Task 5 fixtures.

A definition's `key` is exactly the nine-element JSON array below. All
maps represented as binding rows use the formal ordering below and have
no duplicate formal; descriptor fields, type arguments, signatures and the
capture prefix keep their semantic order. No provenance, runtime capture
value, caller-local binder spelling, import alias, generated flat wire
prefix, legacy generated callable name, source position or body digest
appears in it. `closed/names.py:canonical_callee_name_from_key` is the sole
key-to-name algorithm, shared by the builder and artifact checker. It uses
`workflow.pure_expr.canonical_json_for_pure_value` encoded as UTF-8, without
a newline, and the full lowercase SHA-256. Task 7's canonical artifact
encoding uses the same JSON settings; its artifact newline is not hashed
into the definition name.

```text
K = [module, kind, declaration, types, procedures, workflows, values,
     captures, residual]
```

| Index | Exact JSON shape | Meaning |
| --- | --- | --- |
| 0 | nonempty string | Declaring module; the existing standalone entry namespace is `entry` (`closed/frontend.py:compile_typed_program`). |
| 1 | `"procedure"` or `"workflow"` | Source callable kind, unchanged by conversion. |
| 2 | declared-name string, or `{"owner": DId, "name": local_name, "ordinal": n}` | Top-level declaration, or stable local declaration. The local owner is the enclosing top-level declaration; `n` is the retained zero-based same-owner/same-local-name declaration ordinal. |
| 3 | `[[formal, T], ...]` | Canonical type substitutions. |
| 4 | `[[formal, PRef], ...]` | Resolved procedure-reference substitutions. |
| 5 | `[[formal, WRef], ...]` | Resolved workflow-reference substitutions, including extern rebinding. |
| 6 | `[[formal, T, ClosedValue], ...]` | Actual closed-expression substitutions, not runtime captures. |
| 7 | `[{"type": D, "routes": [Route, ...]}, ...]` | Ordered runtime capture prefix. Array position is its zero-based capture index; no parameter-name or value field. |
| 8 | `{"params": [T, ...], "result": T}` | Ordered residual parameter **types**, excluding runtime captures and erased compile-time parameters, plus result type. |

An ordinary declared `formal` is its string name. A generated local
procedure's captured formal is instead `["local", n]`, using the same
original capture-list index as its local capture route; this applies to
compile-time reference/value captures as well as runtime captures. No raw
caller capture name is copied into a binding map or `PRef.bound`. Bindings
are ordered with local selectors first by integer index, then ordinary
formal strings lexicographically. Type-variable formals in `types` remain
ordinary strings. These plain selectors also occur in reference-formal
paths; they introduce no new runtime value or identity lookup.
Extern formal names in `WRef.externs` remain ordinary nonempty strings;
the local selector belongs only to callable parameter/capture bindings.

`DId` is exactly `[module, kind, declaration]`, the first three fields of a
key. Its local `owner` must be a top-level `DId`, so this is finite. It is
declaration identity, **not** a canonical converted name, full definition
key or hash. Routes never contain a converted target key: their identity
must not recursively contain the capture row being constructed.

The residual signature intentionally has no binder names. Names remain in
`definition.params` for lexical binding, and declared formal names remain
in binding/route rows where keyword ownership matters. This avoids putting
a renamed generated binder into the key and makes the required
capture-prefix/residual-type check purely positional. Signature order and
every exact descriptor remain significant.

`D` is the key projection of an existing recursively canonical normalized
runtime descriptor: ordinary nominal definitions still agree with
`tree.types`, while generated run-reference envelopes use the structural
marker below, recursively even inside a captured or nested type. Applied
nominal identity fields use the structured projection specified below,
including phantom arguments not represented by any field. `T` additionally
allows the key-only compile-time reference signatures:

```text
{"kind": "procedure-reference", "signature": {"params": [T, ...], "result": T}}
{"kind": "workflow-reference",  "signature": {"params": [T, ...], "result": T}}
{"kind": "run-ref-result", "signature": S}
```

The first two encode static callable types when a bound argument itself is
a reference; they are not runtime values/descriptors and are forbidden in
the final runtime capture/residual signature. The exact finite structural
signature `S` below projects generated run-reference envelopes. P5 compares
the key projection of the finalized runtime signature, not the marker
directly to a runtime descriptor.

#### Run-reference structural signatures

`S` has exactly this JSON shape; `D` is the runtime descriptor projection
above, and the fixed records are complete recursive neutral descriptors:

```text
S = {"inputs": [[input_name, D], ...],
     "result": {"schema": "run_ref_result_contract.v1",
                "envelope": {"kind": "record", "fields": [
                  {"name": "value", "type": D},
                  {"name": "workspace_delta", "type": FixedWorkspaceDelta},
                  {"name": "accounting", "type": FixedRunRefAccounting}
                ]}}}
```

Objects have exactly the displayed keys. Input rows have exactly two
members; names obey the existing `RunRefInput` rule, are unique and retain
semantic input order (the array may be empty). Retain all seven fixed runtime
record identities, field orders and definitions accepted by the unchanged
neutral result validator. No compile-time reference descriptor belongs in
`S`: its inputs and child value are runtime transport types.

Validate the complete neutral result contract first, then omit **only its
own outer envelope's `name`**. Do not project that whole root through `D`,
which would request its own signature. Project each field and input type
recursively; every nested generated envelope becomes the whole marker
`{"kind":"run-ref-result","signature": S_of_its_producer}`. Its producer's
ordered inputs are part of that nested S and cannot be recovered from the
envelope alone. Preserve all other normalized-descriptor keys/scalars,
user/private nominal identities, applied types, refinements and exact fixed
records. The nameless root is a key projection, never a runtime descriptor
accepted by a weakened neutral codec. There is no forward signature ref,
self marker, generated-name escape or persisted signature/origin table.

Task 5 adds these pure helpers to `closed/names.py`; Tasks 6 and 8 reuse them:

```python
key_type_descriptor(descriptor: dict, *, run_ref_signatures: Mapping[str, dict]) -> dict
canonical_run_ref_signature(inputs: Sequence[tuple[str, dict]], result_descriptor: dict,
                            *, run_ref_signatures: Mapping[str, dict]) -> dict
run_ref_type_dependencies(descriptor: dict) -> tuple[str, ...]
```

The first two return fresh JSON values without changing their arguments, use
existing neutral descriptor/result/input validators and raise `ValueError`/`TypeError`
for invalid facts. The second may reuse `RunRefInput` with a transient
`ReferenceBinding("inputs." + name)` and nested transport enabled; that
binding never enters S. Result validation also enables target 2.35 nested
transport. The map contains completed signatures by generated
runtime identity in the caller's resolved origin scope. Callers establish
ownership and exact producer/descriptor correspondence; a supplied map alone
is not artifact authority. Construction uses compiler ownership metadata,
not spelling; read-back reserves unqualified generated envelope identities. Missing generated identities fail. No direct
frontend semantic dependency, parallel codec or duplicated fixed schema is
introduced. Existing neutral-codec/package import side effects do not imply
source re-typechecking or require an import refactor.

P5 derives an origin index from every actual `perform/run_ref` occurrence,
with its containing definition and independently checked local site. A
concrete generated identity has exactly one lexical producer; reject missing
or duplicate producers, even equal-shaped ones or a digest-prefix collision.
Dynamic calls/iterations do not add lexical producers. Decode path-mode
configs at target 2.35, check node inputs in their lexical typed environments,
and require exact ordered input name/type rows and `inputs.<name>` reference
bindings. Check node/config envelopes and all generated/fixed nominal uses
against their complete `types` entries, including nested descriptors and
config return refinements. Matching copied type labels are not inference.

Compute each producer's S with a visiting guard and memoization over generated
dependencies in its checked inputs and result fields, including generated
atoms in applied identity arguments (exclude only its own outer envelope).
Use `run_ref_type_dependencies`, which enumerates generated envelopes and
identity-argument atoms in deterministic traversal order; a whole generated
occurrence resolves through its own producer DFS. Missing/ambiguous origins
or a visiting origin fail; input dependencies can form a cycle even with
finite result descriptors or phantom-only arguments. Derive this inventory
before accepting key markers. A persisted marker must equal
a derived S in canonical JSON bytes, and runtime/key agreement must equal
`key_type_descriptor` of **that actual runtime descriptor**, selecting its
concrete producer. Canonical JSON equality keeps `false` distinct from `0`.
This reuses the derived grammar rather than adding a second S decoder.

After canonical definition names and sites have been checked, recompute the
unchanged full digest tuple specified in Task 8. Require all 64 characters,
the generated name, node/config/result-digest/type-table agreement and exact
input correspondence; neutral decoding alone does not prove lexical origin.
No source, child repository or runtime execution is consulted.

Two producers may share S but retain different concrete identities. Never
invert S to select a generated name. Before finalization, copied bodies or
specializations may share an old generated spelling: Task 6 resolves each
use through retained `RunRefSiteMetadata`/WCC producing-definition, call and
substitution context. A temporary producer handle is allowed in builder state.
A context's old-name map may collapse signature entries only after proving
complete S equality; concrete producer occurrences remain distinct for Task
8's final naming/rewrite. No program-global string substitution is valid.
Missing/ambiguous construction ownership is a compiler defect. This explicit
expansion can enlarge keys for repeated nested contracts; a compact format
would require an identity-format change.

#### Applied nominal identities and interned generated views

Runtime descriptor `name` and `union_name` remain canonical strings. For
evaluated execution their exact spelling uses this closed identity grammar:

```text
Atom     = nonempty identity atom without whitespace, '[', ']' or ','
Identity = Atom
         | List[Identity] | Optional[Identity] | Map[Identity,Identity]
         | NominalHead[Identity Identity ...]
         | AppliedUnionIdentity.variant
```

Generic arguments use one ASCII space; Map uses a comma without surrounding
spaces. List/Optional/Map have arities 1/1/2. A nominal application has at
least one argument and a module-qualified template head. Reserved unqualified
container heads differ from ordinary heads such as `pkg::List`. Non-applied
ordinary nominal/discriminant atoms keep their exact registered spelling.
The generated atom is exactly `RunRefResult$<16 lowercase hex>`, resolved
through the checked origin index. An applied discriminant has a nominal
applied union owner and the exact suffix `.variant`; no other suffix is
discarded. Existing discriminant checks still validate the owner's variants.

Only inside key descriptor `name`/`union_name` fields, project every applied
identity structurally, even when no argument is generated:

```text
I = ordinary_identity_atom_string
  | {"head": Head, "args": [I, ...]}
  | {"owner": AppliedUnionI, "member": "variant"}
  | {"kind": "run-ref-result", "signature": S}
Head = "List" | "Optional" | "Map" | qualified_nominal_template_atom
```

Objects have exactly these keys and the same arities/order as the runtime
grammar. `AppliedUnionI` has a nominal, not container, head. A generated atom
uses the same complete S marker as a generated envelope, never a digest or
site/name token. Template identity, ordinary arguments, refinements and every
other descriptor field remain exact. For example `entry::Wrapper[A]` projects
its name to `{"head":"entry::Wrapper","args":[M_A]}` when A is a checked
generated identity and M_A its full S marker. This includes phantom arguments
and nested constructors; matching payload fields alone do not prove identity.

Keep the small parser/renderer private in `closed/names.py`. Parse only these
identity fields and require canonical render-back equality; do not substitute
arbitrary serialized strings. Typed construction uses retained `type_args`,
`union_type_args`, discriminant ownership and declaring modules with the same
renderer. Register referenced nominal arguments even when phantom. At
read-back the exact runtime string indexes the full concrete `types` entry.
P5 establishes internal consistency of retained identities; absent source
template declarations/arity are not claims it can authenticate.

P5 derives an ephemeral inventory of projections of independently checked
runtime nominal descriptors. A persisted structured name in key D must match
one of those complete projections. Runtime/key agreement projects the actual
runtime descriptor, never a descriptor selected by inverting this inventory.
Different concrete entries can project equally. Missing/unknown/malformed
identity facts fail. The origin DFS includes these argument dependencies, so
A taking `Wrapper[B]` and B taking `Wrapper[A]` is a cycle even if their
Wrapper payload fields contain no generated descriptor. No descriptor/codec
field, persisted origin table or generic type service is added.

For equal converted keys, keep the first candidate in deterministic semantic
entry/call traversal as the native representative, with its native body,
capture/parameter order, result and concrete producer associations. Do not
sort by provisional names, spans, paths or object identity. Later same-key
requests keep their caller-view descriptors and use the checked generated
view of `call.boundary` below when needed. Keep source/snapshot/configuration
conflict checks; after canonical binder/type-key projection and producer
association, contradictory bodies are compiler defects, not arbitrary choices
or new body hashes. Candidate copies of an interned body are not additional
lexical producers; distinct actual entry/body effects remain distinct.

P5 first validates runtime inventories and caller-view expression typing,
derives S including phantom dependencies, then completes deferred view/key/
name/site checks. No artifact is accepted until all checks succeed. This
ordering uses checked declared signatures, not trusted opaque annotations.

#### Reference and closed-binding rows

```text
PRef = {"target": K, "residual": Signature,
        "bound": [[formal, T, Binding], ...]}
WRef = {"target": K,
        "externs": {"providers": [[formal, BindingRow], ...],
                    "prompts":   [[formal, BindingRow], ...]}}
Signature = {"params": [T, ...], "result": T}
Binding = {"value": ClosedValue}
        | {"capture": capture_index}
        | {"procedure": PRef}
        | {"workflow": WRef}
```

Each map shown has exactly its displayed keys; each `Binding` has exactly
one of its four alternatives. `PRef.target` is the recursively canonical
**converted** target; `PRef.residual` equals that target's residual
signature. `bound` records every bound formal/type/binding, using the formal
ordering above. A `capture` index refers to the capture array of the immediately
enclosing definition key whose binding facts contain the reference, not
the target key's capture array. Entering a nested `target` key starts a new
index scope. The corresponding reference-formal route identifies which
target binding receives it; nested bound references compose those formal
routes. Forwarding aliases are resolved before producing this data.

##### Mandatory `PRef.bound`/target agreement

`PRef.bound` is a second view of the target's binding facts, not independent
authority. Task 4/6 derives the converted target key, the bound rows and the
residual signature from **one** resolved reference plus its already-merged
specialization facts. It uses `ResolvedProcRefValue.signature_params`,
`bound_args`, `residual_params` and the existing specialization owner; it
does not produce the three views from separate guessed signatures.

P5 derives the target's bound-formal table from these persisted facts:

| Target fact | Bound row category and canonical type |
| --- | --- |
| `target[4]` procedure binding | `procedure`; type is `{"kind":"procedure-reference","signature": selected_PRef.residual}`. |
| `target[5]` workflow binding | `workflow`; type is `{"kind":"workflow-reference","signature": selected_WRef.target[8]}`. |
| `target[6]` closed value binding | `value`; exact persisted type and alpha-normalized closed expression. |
| A target capture route `["parameter", f]` or `["local", n]` | `capture`; terminal formal selector `f` or `["local",n]` and the capture's exact projected type. |

Type substitutions in `target[3]` are not bound value parameters. Captures
whose routes start with `reference` or `context` are carried requirements
of those bindings/bodies, not additional root bound formals. A formal must
have exactly one category across the table; overlapping value/ref/direct
capture claims are invalid. Nested reference captures are checked inside
their reference binding rather than fabricated as another bound formal.

There must be a bijection between this table and `PRef.bound`: same formal
selectors, canonical types, categories and exact binding content. Missing,
extra, duplicate or differently categorized rows fail the key check even
if the target/residual/name otherwise look plausible. In particular, a
literal bound in the target cannot be replaced by a capture row or another
literal solely because its type matches.

For capture rows, derive a target-capture-index to enclosing-capture-index
mapping from the reference's formal path and the capture routes. Prefix
the target's ordinary/local terminal route with that reference path and
require the enclosing capture to contain precisely that owner route with
the same canonical type. The bound row's `capture` index must be this
mapped index, not merely an in-range index of a compatible type. Apply the
same mapping recursively when comparing nested `procedure` bindings:
target-key capture indexes are scoped to that target key, while the bound
view's indexes are scoped to the enclosing key. The mapping is a comparison
operation over existing arrays, not a persisted second routing table.
Lifting a target route already of the form
`["reference", target_path, terminal]` concatenates the enclosing reference
path with `target_path`; it does not drop the nested owner or treat a local
capture selector as an authored parameter name.

At construction, remove the resolved bound formal selectors from the
original ordered `signature_params` **after type substitution**, erase
compile-time reference parameters through the existing specialization
owner, and require the remaining ordered parameter types and result to
equal both `PRef.residual` and `target[8]`. For a reachable target definition,
P5 also checks its actual parameter list: target capture prefix followed
by exactly that residual suffix. The construction additionally checks that
no bound formal survives in that suffix; P5 does not infer authored formal
identity from a renamed capture binder.
When only a recursive target key is retained, P5 checks its complete bound
partition plus residual equality. It does not pretend that an unavailable
authored parameter spelling/order can be authenticated from the artifact.
Changing both mutually consistent views and the body remains a different
program, subject to the durable artifact digest.

##### Exact resolved extern rows (no opaque `BindingRow`)

In `WRef.externs.providers`, each `BindingRow` is exactly:

```json
{"provider_id":"resolved-provider-id"}
```

In `WRef.externs.prompts`, each `BindingRow` is exactly one of:

```json
{"source_kind":"asset_file","path":"prompts/review.md","asset_base":"."}
{"source_kind":"input_file","path":"inputs/review.md"}
```

`provider_id` is a string with at least one non-whitespace character,
preserved exactly as `ProviderExtern.provider_id`. Prompt `path` is a
string with at least one non-whitespace character, preserved exactly as
`PromptExtern.path`; no stripping, rebasing or file read is part of this
row. `source_kind` is exactly `asset_file` or `input_file`. `asset_base`
is required only for `asset_file`, is the nonempty logical entry directory
already required by the shared provider-node schema, and comes from the
retained **producing** source owner; it is never the consumer directory or
an incidental absolute installation/source prefix. Its serialized string
and lookup semantics are exactly the same as `perform.prompt.asset_base`.
No `asset_base` key is accepted on `input_file`. Missing/extra keys, mixed
source variants, nonstring values, empty/whitespace-only ids/paths, alias
objects and provenance wrappers fail P5's row validation.

These are a direct semantic projection of existing owners, now fixed for
Task 5 fixtures: `workflows.py:ProviderExtern` (name/provider id),
`PromptExtern` (name/source kind/path), `_coerce_prompt_extern_source` and
`build_extern_environment` validate the binding values; the shared Phase 2
provider-node schema already fixes source-kind/path/asset-base carriage.
`prompt_extern_source_payload` currently serializes the same source
selection as `{asset_file: path}` or `{input_file: path}`; the closed row
uses the existing node's explicit `source_kind`/`path` spelling so the
configuration row and effect need no competing source grammar. The extern
lookup `name` is not duplicated inside a row; the binding map's formal
already identifies the use. `defprompt` is a typed prompt application,
not `PromptExtern`, and therefore is not a third extern-row alternative.
Its template/slots remain in the existing provider effect grammar.

Task 7 must emit these same rows in `configuration.providers/prompts`;
Task 8 consumes them under the definition's selected configuration scope.
Resolve workflow extern rebinding all the way to the actual row in that
source scope before building the key. Do not persist
`WorkflowExternRebindingPlan`'s unresolved tuple of names. Two formal refs
resolving to the same row have the same binding identity. Different provider
ids, prompt source kinds, paths or logical asset bases distinguish keys.
There is no new hash and no whole-scope digest in a row; unused unrelated
configuration entries still affect the program digest as already required.

`ClosedValue` uses the shared closed-value grammar, canonical type
projection and no `@`. Every lexical binder/reference **inside that key
expression** is alpha-normalized by binding traversal, including authored
local names; this is separate from the body's rule that preserves authored
names. Omit their optional [binding-label overrides](#binding-labels) from
this key projection too; runtime-body labels remain intact. Literals keep
their type tag (`Bool`, `Int`, `Float`, refinements).
An expression with a runtime free value is closure-converted first: it
cannot be serialized with a caller's free name. A runtime bind-site
computation is evaluated once into a capture, not copied into the key's
closed substitutions. No runtime procedure/workflow reference survives.

#### Capture routes

Every capture row has a nonempty `routes` array, deduplicated and sorted by
canonical JSON bytes. Capture **rows themselves are not sorted**: their
order is the actual converted native prefix. Do not merge two independently
bound captures because their values, types or schemas happen to be equal.
One row can have multiple routes when one already-bound value is forwarded
to multiple recipients. Different capture rows cannot claim the same
terminal recipient field: competing bindings are a defect, not a reason
to choose a value by array order.

The closed route grammar is:

| Route | Exact array | Owner of the terminal identity |
| --- | --- | --- |
| Direct ordinary bound parameter | `["parameter", formal]` | The current declared callable's formal. |
| Local lexical capture | `["local", n]` | Index in `GeneratedLocalProcedure.capture_names`, before erasing compile-time captures; no captured identifier spelling. |
| Bound argument of a selected procedure reference | `["reference", [reference_formal, ...], terminal]` | Nonempty path through resolved reference formals. `terminal` is `["parameter", formal]` or `["local", n]` in the selected target. |
| Caller-only context recipient | `["context", [Hop, ...], native_formal, [[source_path, native_path], ...]]` | Nonempty route through actual retained calls, ending at the original omitted native formal and its typed field paths. |

```text
Hop = [callee_DId, occurrence]
source_path = [field_segment, ...]  # relative to this capture's descriptor
native_path = [field_segment, ...]  # relative to native_formal's descriptor
```

Every integer here must be a non-Boolean, nonnegative integer. Field paths
are structural string-segment arrays, with `[]` denoting the root; they are
not flattened wire names and exclude the caller's parameter/root spelling.
Context field pairs are unique, sorted by canonical JSON bytes, and retain
all and only the captured source fields transferred at that recipient. The
existing structural boundary rule supplies union paths/activity when
applicable; there is no legacy-mode flag. Destination coverage,
type/refinement compatibility and any nominal crossing are checked through
the existing exhaustive `call.boundary` relation, not a whole-record cast.

The starting owner of a context route is the definition whose key holds the
row. Each hop selects one actual call in that owner's body. `occurrence`
is its zero-based ordinal among calls to that same `callee_DId` in the full
semantic traversal already specified for §6, ignoring calls to other
declarations and all non-call binders/nodes. Traversal enters all specified
value/body edges but does not inline or enter a callee's definition. The
next hop starts in the selected callee. Task 4 establishes the ephemeral
retained-WCC-to-closed-call association during conversion; Task 5 derives
these same ordinals from closed calls and their callee keys. No new call
field, effect site or runtime routing table is introduced.

Intermediate converted wrappers carry the suffix of the route beginning
in their own body. The terminal native callee already owns its ordinary
context formal; that formal is not a new capture unless independently
required by another conversion. Captured descriptor `D` remains the caller
nominal descriptor all the way through forwarding wrappers.

`WccSpecializationCapture.owner_kind == "callee"` supplies direct target
ownership; `"argument"` plus `argument_index` must first resolve the
original formal using the retained base signature and reference binding.
`source_name` is lookup evidence for `BoundProcArg`/local capture metadata,
never automatically the persisted formal. Generated local captures use
their ordered metadata index. Thus source aliases and caller spellings
cannot accidentally become routes.

#### Why a repeated-call ordinal is needed

This is a representational counterexample, not a claim that a new compiled
source fixture has been admitted or run:

```text
wrapper(capture A, capture B, ordinary payload):
    call leaf(payload)   # retained omission selected for A
    call leaf(payload)   # retained omission selected for B
```

Both recipients have the same declared `leaf`, native formal `phase__ctx`
and structural fields. If `A` and `B` share a nominal context type,
`(leaf, formal, fields)` alone assigns them indistinguishable routes; the
conversion in which A feeds the first call and B the second must differ
from the conversion with those recipients exchanged. The exact retained
call selection, when supplied by the already-admitted binding facts, gives
occurrences 0 and 1. It does not invent permission to supply two private
groups. Equivalently, one explicit native binding and one admitted omission
must not let a capture overwrite the explicitly bound occurrence.

Inserting a pure `let`, renaming any result binder, or inserting a call to
another declaration changes neither ordinal. Inserting an earlier call to
the **same** declaration can change it; that changes the relevant call
structure and is the stated ceiling. Swapping runtime values supplied to
the same fixed A/B slots changes call inputs only; swapping the slots'
recipient routes changes the converted definition key.

#### Name derivation and source-independent checks

For a top-level declaration, the readable base is
`kind + ":" + module + "::" + declared_name`, where `kind` is the exact
`procedure`/`workflow` key tag. For a local declaration, substitute
`local_name` for `declared_name`; its enclosing owner and ordinal are
already in the hashed key. The entry uses its `workflow:` base too.
The source admits same-name procedures and workflows; this fixed qualifier
is never selected conditionally by discovering collisions elsewhere in
the program. A top-level key with all five arrays
`K[3:8]` empty is unspecialized and uses the base alone. Every other key,
including every local key and every context-converted key, uses
`base + "[" + sha256(canonical_json_bytes(K)).hexdigest() + "]"`.
No independent specialization flag is needed. A frontend specialization
with no semantic substitutions/captures is canonicalized to its base.

P5 validates the key's shape and canonical order before deriving a name;
it then requires exact equality to its `definitions` map key. Equal names
with unequal keys remain a defect; two entries with equal keys and
different names are invalid too. JSON decoding still owns duplicate-object
key/nonfinite rejection before the dict-only checker runs.

For `c = len(K[7])`, P5 requires:

1. `definition.params` has `c + len(K[8].params)` entries, unique lexical
   binders, and the key projections of the first `c` descriptors equal the
   capture descriptors in order. The remaining descriptors and
   `definition.result`, after that same accepted generated-run-ref key
   projection, equal the residual signature.
2. Capture routes have the declared closed shape. Reference routes resolve
   through the actual reference-binding facts in the key; local indexes
   remain slot identities, not claims that an artifact reader can recover
   the original authored capture spelling. Context hops resolve to actual
   closed calls by callee `DId` and occurrence. Their source/native paths
   have valid checked descriptors.
3. At an annotated call into a converted definition, caller slots `[0:c]`
   are its capture prefix in the same order and with the same descriptors,
   or the checked generated nominal view below. A changed nominal must use
   projection rows; `direct` still requires strict compatibility.
   A direct pair for native capture slot `j` is `[j,j]`; an unrelated caller
   slot cannot masquerade as capture `j`. Call argument values are checked
   against these slots, not compared with values in the key. All remaining
   direct/projection indices retain the shared exhaustive-partition rules.
   Being in the residual suffix does not by itself authorize `direct`.
4. Context forwarding agrees with the persisted route: an intermediate
   call transfers this already-bound capture to the matching suffix capture
   in the selected converted callee; terminal transfer/projection sends
   its identified fields to the identified native formal. Track these
   existing explicit capture/name/field transfers while checking the body;
   do not accept a route string merely because a compatible callee exists
   elsewhere. The internal annotated terminal call also covers every
   ordinary residual input and both outputs.

These are internal-consistency checks. A coordinated, type-valid change
to a key, name, body and call arguments is another program, not something
source-free P5 can authenticate against unavailable historical source.
Phase 3's stored artifact/run-header digest remains the authenticity check.

#### Capture examples

For declared `sample::add(x: Int, y: Int) -> Int`, runtime-binding `x`
produces this key; calls with capture values 7 and 11 share the key/name
and differ only in their first value argument:

```json
["sample","procedure","add",[],[],[],[],
 [{"type":{"kind":"primitive","name":"Int"},"routes":[["parameter","x"]]}],
 {"params":[{"kind":"primitive","name":"Int"}],"result":{"kind":"primitive","name":"Int"}}]
```

The converted parameter types are `[Int, Int]`: capture first, residual
`y` second. The name is `procedure:sample::add[<full key hash>]`. A genuinely
substituted closed literal instead belongs in `values`, with its type tag.

For caller-only context forwarded through native declarations
`producer::entry -> producer::middle -> producer::run-phase`, the entry's
capture row retains the full canonical `consumer::PhaseCtx` descriptor and
this route (the exact full descriptor remains in `type`, not a nominal-only
label):

```json
["context",[[["producer","workflow","middle"],0],
            [["producer","workflow","run-phase"],0]],"phase__ctx",
 [[["artifact-root"],["artifact-root"]],
  [["phase-name"],["phase-name"]],
  [["run","artifact-root"],["run","artifact-root"]],
  [["run","run-id"],["run","run-id"]],
  [["run","state-root"],["run","state-root"]],
  [["state-root"],["state-root"]]]]
```

`middle` carries the suffix containing only the `run-phase` hop; that
terminal native callee retains its ordinary `producer::PhaseCtx` formal.
The outer capture is promoted once at slot 0 and uses direct pair `[0,0]`;
the terminal nominal crossing uses the complete checked projection. Two
values of one caller descriptor/routes reuse both converted wrapper keys.
A different caller nominal, recipient occurrence/formal or field mapping
changes the keys; relocation, aliases and generated wire prefixes do not.

### Body nodes

| `k` | Keys | Rule |
| --- | --- | --- |
| `let` | `name`, `value` (a bound value), `body`, optional `label` | sequencing; [binding-label rule](#binding-labels) |
| `halt` | `value` | result of the definition, or of a `block` |
| `if` | `cond` (value), `then`, `else` (bodies) | strict `Bool` |
| `case` | `subject` (value), `arms`: `[{variant, bind, body}]` | variant elimination |
| `join` | `name`, `params` (`[[name, descriptor]]`), `result` (descriptor), `body`, `cont`, optional `label` | second-class continuation with exactly one result parameter; a `halt` reached in `body` is the join's value (§4.3); [binding-label rule](#binding-labels) |
| `jump` | `join`, `args` (values) | |
| `loop` | `name`, `param`, `state_type`, `result` (descriptors), `budget` (value), `init` (value), `body`, `exhausted` (body or `null`), `code`, optional `label` | bounded iteration; `code` is the exhaustion diagnostic code; [binding-label rule](#binding-labels) |
| `continue` | `loop`, `args` (values) | names the loop it is in |
| `done` | `value` | |

### Bound values (the `value` of a `let`)

| `k` | Keys | Rule |
| --- | --- | --- |
| `perform` | `class`, `result` (descriptor), `repeat` (`"rerun"` or `"never"`), `site` (set by the site walker), and the class's keys below | one effect |
| `call` | `callee` (canonical name), `args` (values), `type` (caller result descriptor), optional `boundary` (below), `frame` (set by the site walker when the callee performs an effect) | evaluation of a definition's body (§9.2) |
| a value | | |

Effect classes of the first release (§1.1, §9.2):

| `class` | Keys |
| --- | --- |
| `command` | `boundary`, `command` (stable tokens), `closure` (canonical `[{base, path}]` rows, C1; base is `workspace`, `absolute` or `package:orchestrator`), `contract` (`{kind, payload}` without a `path`), and either `argv` (values) or `document` (`[[transport_key, value]]` in signature order, for a certified adapter) |
| `provider` | `provider` (provider id), `prompt` (`{"source_kind": "asset_file" or "input_file", "path": "<exact bound path>", "asset_base": "<logical entry directory>"}`; `asset_base` only for asset lookup, or `{"template": "<text>", "fills": <ordered typed slot rows>}`), `inputs` (`[[name, renderer_id, value]]`, with unique labels allocated from established preferred typed-input names by evaluated-execution design §9.1), `dependencies` (`{required: [values], optional: [values], position, instruction}` or `null`), `policy` (`{model, effort, delivery, materialization_attempts, timeout_sec}`, each present only when declared, as values), `contract` |
| `run_ref` | `config` (base64 of `encode_run_ref_static_config`, path mode only, inputs bound as the references `inputs.<name>`, K7), `inputs` (`[[name, value]]`) |

A workflow `call` is not a `perform`: it is a `call` node whose callee is the
workflow's canonical name (§9.2, "a call is evaluation").

### Compiled-call boundary relation

Ordinary source/procedure calls keep strict positional argument/native
parameter matching. An explicit compiled import retains the catalog's
caller-view signature and its snapshot's native signature. Closing that
boundary, or a converted internal call injecting its captured context into
a different compatible native nominal, uses this optional `call.boundary`.
Same-key interning may also require the checked generated nominal view below.
These internal annotations do not broaden source-call admission:

```text
{
  "params": [[call_slot_name, caller_descriptor], ...],
  "direct": [[argument_index, native_parameter_index], ...],
  "inputs": {"caller": [row, ...], "callee": [row, ...]},
  "outputs": {"caller": [row, ...], "callee": [row, ...]}
}
row = {"name": wire_name, "path": [structural_segment, ...], "contract": contract}
```

`call.args[i]` belongs to `boundary.params[i]`, whose unique names label
caller input roots. Callee input roots label `definition.params`; outputs
use `return`. `call.type` is the caller result, `definition.result` the native
result. Every descriptor retains exact canonical nominal facts. Serialize
existing `FlattenedContractField.generated_name/source_path` plus its
`SurfaceContract.definition`, including union `projection` metadata. Use
structural paths from retained typed descriptors/contract pointers for old
union source segments; never split flattened names to invent field paths.

Task 4 establishes bindings before renaming from `BoundProcArg.name`,
`ResolvedProcRefValue.signature_params/residual_params`,
`GeneratedLocalProcedure.capture_names`,
`WccSpecializationCapture.owner_kind/argument_index/source_name`, and the
retained workflow signature's defaults/hidden-context/compatibility facts.
The native list remains its converted capture prefix plus residual parameters.
A caller-only private context exposed by an admitted bundle becomes a typed
context/capture parameter in that converted prefix, with its original source
signature unchanged. Forward its value through the retained call graph to
the exact omitted context bindings, including transitive wrappers. Supplied
values are evaluated once and take precedence over X1/X2/default generation;
they are never discarded. Retained semantic private binding/projection facts
identify the boundary, while rewritten diagnostic provenance is not a callee
identity. Include these converted parameters in the checked relation and
canonical capture schema. Keep the caller's canonical context descriptor
in that capture. Resolve recipients from actual retained calls, native omitted
formals, typed field paths and semantic private groups/context family/phase.
An explicit native binding or authored default owns its argument. Forward to
every matching admitted omission, through only the wrappers that reach it;
never use diagnostic provenance, flattened-name splitting or an entry's direct
omission allowlist as a transitive index. Contract defaults identify omission
generation, not constraints on an explicitly supplied runtime value.

Call slots are ordered: runtime captures in native capture-prefix order;
retained caller-signature formals in declaration order, followed by otherwise
unlisted private compatibility formals sorted by name; then native-only
X1/X2/context parameters in native order. Erased compile-time parameters have
no slot. Fill each formal from its explicit binding, otherwise normalized
default (`lit`), otherwise the existing permitted hidden/context binding.
Missing/competing bindings are defects. A generated value already represented
in caller formals is not appended again; flat storage inputs are not extra
unchecked arguments. Promote a caller-only private formal to its capture
slot once and omit it from the later caller-formal section. Intermediate
forwarding calls with exact capture and residual types may remain strict
positional calls. At an annotated internal context-injection call, include
complete projection rows for all ordinary residual inputs and both native
output views, even for identical scalar types; those residuals do not become
`direct` slots merely because their types match.

`direct` is only for captures/generated/context values with ordinary strict
compatible descriptors. Its non-Boolean integer pairs are in range, sorted
by native index and unique in both columns. Capture pairs agree with the
persisted definition key's capture prefix/schema. These are the only extra
indices needed: direct slots have no wire projection and compiler binding
names may be renamed differently at each end. A context needing boundary
transport uses projection rows instead. Row roots already identify projected
slots by unique-name lookup; wire names match caller/native fields. Direct
slots and projected roots form disjoint exhaustive partitions of both caller
slots and native parameter slots, with complete field/active-variant coverage.
One caller record may supply multiple native parameters: `a: Pair(x, y)`
projects to `a__x: Int, a__y: Int`. Do not require equal caller/native arity.

Preserve authored/ANF evaluation order before permuting slots. Keep workflow
keyword prefixes from `CallExpr.bindings`/`WccPerform.keyword_args` and
`_normalize_perform`, and procedure/capture prefixes from `_normalize_call`.
Captured computations remain at their lexical bind sites. Bind any remaining
non-atomic computation once using existing `let`/name nodes before permutation;
forward resulting values, fill literal defaults and bind generated contexts
once. Phase 3 evaluates final `args` once left-to-right into a cached vector,
then transfers/projects it and binds native parameters in native order.
Projection reads that vector, never re-evaluates expressions, including 1:N.
It projects the native result back to the caller view, with no new effect/site.
Phase 2 specifies and checks this relation; the evaluator remains Phase 3.

Task 5 checks each argument against its `boundary.params` descriptor and
independently derives row meaning from canonical descriptors: valid structural
paths, exact coverage, matching wire contracts, path roots/existence, enum and
primitive constraints, union discriminants/activity and inactive-path
relaxation. Reuse the descriptor/contract owners; never compare only copied
labels or erase whole-record nominal names. Root collection schemas keep
nominal requirements they already contain. Reject missing/duplicate formals,
invalid/direct-order/capture indices, uncovered/overlapping slots, changed
paths under the same wire name, dropped rows and forged union activity with
`call_boundary`. The ordinary strict rule applies without `boundary`.
This checks internal consistency, not historical source authenticity; a
jointly type-valid alteration of arguments and relation is another program.

#### Generated loop-state carrier identities

Let `DId` be the already specified declaration-only `[module, kind, declaration]`, including the existing local-declaration object where needed. It is never a full canonical definition key/name. Define:

```text
F = [DId, carrier_introduction_ordinal]
Q = [F, [[field_name, D(canonical_field_descriptor)], ...]]
H = "workflow_lisp/private::loop-state-carrier$" + SHA256(canonical_JSON(Q))
I(carrier) = H[I(field_type_0) I(field_type_1) ...]
```

The SHA is full lowercase hex, using the existing canonical JSON bytes without an artifact newline. `D` is **exactly** `key_type_descriptor` with the actual retained producer scope; `I` is the existing canonical runtime identity grammar/renderer. Fields retain declaration order, including names. Authored seeds have at least one field, and the existing synthesized map carrier has two, so the existing nonempty applied-argument grammar suffices. Runtime descriptors keep the normal `{kind:"record", name:I(carrier), fields:[...]}` shape and their complete concrete field descriptors.

Why both Q and applied arguments are needed:

- F preserves independent same-shaped nominal families; no seed body/value digest enters it.
- Q preserves ordered field names, all canonical type content, private nominal identity and refinements, even where a type's rendered identity alone does not express a refinement.
- D removes concrete generated origins from the head's hash. Two same-S views of one family can therefore share a projected callable key, under the already accepted generated-view boundary rules.
- The applied arguments retain actual field type identities, including generated and phantom arguments. `key_type_descriptor` projects them through S, and Task 8 can rewrite them through their concrete producers. An opaque hash of a runtime descriptor would lose that capability.
- Runtime descriptors that contain different concrete producers remain distinct. Never invert S to recover a name; never discard the actual TypeRef/producing-definition/substitution association after obtaining Q.

Compute field descriptors/S dependencies before their containing carrier and memoize in the existing typed scope. A visiting dependency is the existing compiler defect, not a fallback name. F contains neither specialized K nor a loop/effect site. Q depends only on F, finite field types and the existing structural input/result signatures S, whose generated envelope root name is omitted. Thus no edge from Q to canonical callee/site, nor from those back into their own identity, is introduced. Actual cyclic generated dependencies continue to fail under the accepted visiting guard.

##### Retained family and concrete variant

At the evaluated-entry frontend's existing retained-declaration association seam, enumerate carrier **introductions** in the expanded owning declaration's semantic operand order, before specialization, inlining or normalization is allowed to change the inventory. Count an authored seed once; `:like` is not an introduction. Count the existing `list/map-effect` constructor once for its generated seed, at that constructor's lexical occurrence. Walk its child expressions normally, so independently authored seeds in its source/body still have their own introductions. This is one ordinal namespace per DId. Enter a local callable with its own existing local DId and ordinal counter; its seeds are not counted in the outer callable.

Attach F to `LoopStateCarrierMetadata` through the existing by-expression/type association, using the same bounded retained-expanded-declaration pattern as local-procedure identities. This fact is transient, excluded from legacy repr/JSON. Source spans/form paths may associate products with the retained declaration; neither their values nor their ordering enter F or Q. No source reread or lexical-owner guess from `%loop-state`/specialization prefixes is valid.

Specialization copies retain their source F; they do not recalculate it by counting a normalized specialized body. Imported/cloned producer snapshots retain the declaring module's F, independent of caller aliases. Generated list-map seeds inherit the F assigned to their actual originating constructor, not an ordinal from a post-expansion body or the currently uninformative `source_kind`. Existing metadata can be replaced with an enriched metadata value when the retained association is completed; do not add a process-global map or a parallel type registry. Every admitted seed must have exactly one association; missing/ambiguous association is a compiler defect to repair.

For the concrete variant of one F, match `LoopStateCarrierMetadata.field_types` with the current resolved typed fields in declaration order, using its existing precise signature/type matching route. The expression index alone may contain several instantiations and its last-value fallback is not closed-name authority. Carrier matching also does not collapse concrete run-reference producer associations merely because S agrees. `canonical_type_identity(type_ref, *, typed)` consumes the retained family/type facts from its existing environment search; no new site/key argument is needed.


#### Generated boundary construction and read-back

The constructor and reader have distinct obligations, ratified 2026-09-30.
The final four-member annotation does not record whether a call originated
as an ordinary generated view or an admitted compiled/context composition.
P5 proves its final relation, not that missing source history. This explicitly
replaces the earlier undifferentiated whole-signature reader requirement;
it does not change S, the nine-member key, codec or site-digest recipe.

**Constructor (Tasks 4/6).** For an ordinary converted call whose native
representative differs solely in generated nominal identities, require exact
`key_type_descriptor` equality of the whole ordered caller/native signature:
all capture-prefix slots, residual slots and result. At least one concrete
generated identity differs. Keep capture count/order/routes aligned with the
key. This case adds no permutation or 1:N cast. A changed ordinary nominal
wrapper fails this constructor predicate. Every concrete endpoint separately
passes its nominal-table and producer checks. Without a generated change,
use the ordinary strict call.

For an already-admitted import/context boundary, preserve its frontend-proven
relation and compose a generated representative change in the same annotation.
Retain caller slots, existing permutation/1:N mapping, native/projected coverage
and once-only argument evaluation; rederive final endpoint rows. Do not infer
a constructor's source admission from the fact that its final annotation would
pass P5. No boundary mode, extra effect/site or global assignability rule is
introduced; an unannotated call remains strict.

**Reader (Task 5).** Check complete generated units in the final relation
before accepting even equal flattened wire contracts. For example, caller
`[B, consumer::Payload{x:Int}]` and native
`[A, producer::Payload{x:Int}]`, with equal S for A/B, can be a valid final
composition. The reader accepts this internally consistent relation although
a purported generated-only constructor must reject the changed ordinary
Payload nominal. The final artifact cannot distinguish those histories.
Configuration scope and capture routes do not supply that absent fact.

Preserve the independent argument/type-table/producer/key/capture checks.
Derive complete input/output rows separately from each exact endpoint,
including fixed workspace/accounting fields and unchanged scalar slots.
`RunId` projects to scalar string; no unknown-primitive fallback is permitted.
`direct` remains strictly compatible, ordered and unique; a native capture
pair is `[j,j]`. Both endpoint capture slot j must project to its persisted
capture type, with routes unchanged. Changed generated captures use projection
rows. Check exact serialized endpoint rows, exhaustive disjoint partitions,
structural paths, constraints, union activity and inactive-path rules first.
Then apply this source-free predicate separately to inputs and outputs:

1. Walk each projected endpoint's actual descriptor and derived row paths.
   Protect a complete subtree at the first applicable point: a generated
   envelope; a descriptor whose own projected `name` or `union_name` contains
   a generated marker in an applied identity/discriminant; or a descriptor
   where an actual row terminates and any generated dependency occurs.
   The last case includes atomic List/Optional/Map transport. Its complete
   checked D protects descendants, so do not emit redundant nested units.
   Ordinary flattened records/unions outside a unit remain traversable.
   Use `key_type_descriptor` and existing identity/dependency helpers; a
   missing, ambiguous, cyclic or invalid origin fails, never skips a guard.
2. For every protected occurrence derive its nonempty complete **footprint**:
   sorted pairs `(actual wire name, relative structural path)` for exactly
   the rows descending through that occurrence. Relative paths start at the
   unit, excluding the enclosing caller/native root. Include a row only if
   its remaining path exists in that descriptor occurrence; another union
   arm cannot contribute a foreign leaf. Never split wire names for paths.
3. Preserve **activation** when crossing ordinary unions outside a unit:
   conjunctions of actual derived discriminator-wire/variant conditions.
   Each discriminator domain is the exact declared variant list and must
   match both endpoint enum contracts. Paired wire names identify the same
   selector, including a union flattened to a native enum formal. Shared
   paths in different branches retain conditional occurrences. A protected
   union's own complete D already protects its internal variants.
4. For each relevant discriminator assignment, compare multisets of active
   `(footprint, D)` units on both sides. They must agree exactly; multiplicity
   matters. Visit only branches affecting one footprint group rather than
   taking a global cross-product of unrelated unions. No persisted predicate
   language, identity hash or S-to-name inversion is needed. A generated
   unit may move intact from a nested ordinary field to one native formal;
   splitting away its identity into unmarked leaves fails. A shared generated
   union field may become unconditional only if every branch carries the
   same D. A correct input or unrelated unit cannot authorize a bad output,
   another root, missing branch or different S.
5. Only after those guards may paired equal wire contracts pass directly.
   Keep both exact contracts, transfer roles, structural paths, topology,
   activity and inactive-path behavior. Unequal contracts require equal
   full D at the **terminal transport descriptor of that same paired row**,
   with an actual generated dependency. Resolve conditional terminals using
   the same branch correspondence; no unrelated equal pair or unqualified
   set of descriptors grants permission. A matched ancestor unit does not
   replace this terminal proof (for example List[A]/List[B] inside an envelope).

This protects scalar S even when all flattened leaf contracts match, nested
and phantom S, applied template heads and ordered ordinary arguments. Root
collections retain their complete nominal schemas; an ordinary nominal inside
a generated-bearing applied unit cannot be erased. Outside protected units,
existing ordinary nominal and 1:N crossings remain valid. These are explicit
restrictions: generated units cannot disappear through flattening, and no
admitted source requiring that erasure has been demonstrated. If one is found,
repair the contract with that evidence rather than silently refusing admitted
source or guessing correspondence. Runtime endpoint names/configs/full site
hashes and once-only transfer remain unchanged.

Task 5 implementation evidence must cover the original changed-input-S case
before the equal-contract shortcut, scalar/List/phantom input and output views,
context-shaped 1:N around an intact generated child, captures/direct partition,
ordinary wrapper composition, nested S, template/argument/order changes,
branch swaps with the same global S multiset, shared versus conditional union
fields, missing origins and dropped/redirected rows. These go through actual
P5; a reduced boundary-only proof is not the implementation gate. Tasks 4/6
separately test the whole-signature constructor rejection, and Tasks 4/8 keep
the source-admitted scalar/List/phantom/capture/context and integration gates.
No typed fixture alone proves new source admission.

### Values

| `k` | Keys | Rule |
| --- | --- | --- |
| `lit` | `v`, `type` (descriptor) | literal; a variant tag is a literal |
| `name` | `n` | |
| `field` | `base` (value), `path` (field names) | |
| `record` | `type` (descriptor), `fields` (`[[name, value]]`) | |
| `inject` | `type` (descriptor), `variant`, `fields` | |
| `op` | `payload` (a pure catalog payload, `pure_expr_schema_version` 2, bindings `a0..an`), `args` (values) | one catalog operator; `record_update`, `list_nonempty_head` and `path_join_under` are catalog node kinds |
| `select` | `cond`, `then`, `else`, each arm `{prefix: [{name, value, label?}], value}` | conditional value; each prefix row accepts the optional [binding label](#binding-labels) |
| `list` | `items` (values), `type` (descriptor) | |
| `list_map` | `binder`, `source` (value), `body` (value), `type` (descriptor of the result list) | `list/map` with a pure body; the body reads `binder` as a name |
| `path_join` | `base` (value), `child` (`lit`), `type` (path descriptor) | X3 for a generic `PhaseCtx`: the base path joined with a literal child, under the descriptor's root |
| `block` | `body` | a body evaluated for its value (§4.3) |
| `context` | `field` (`"run-id"`) | a value the run supplies (X1) |
| `result_path` | `n` (the binder of a provider effect), `type` (path descriptor) | the committed attempt's result file (X4) |

### Type facts and prompt slot rows

Every value has one derivable type. Literal/list nodes carry `type` because
empty lists, numeric kinds, enums and refined paths cannot always be inferred
from JSON alone; `name` and `field` derive it from the typed environment.
Record/inject/path nodes already carry descriptors; `op` uses its catalog
result descriptor; `select`/`block` derive a common branch/body result;
`context.run-id` has the fixed `RunId` descriptor declared by `std/context`;
the closed checker does not coerce it to `String`. `result_path` must reference a provider result
binding and its declared path type. Definition/entry, join and loop results,
all parameter types and effect result/contract types are persisted. Case
bind types derive from the subject union's selected variant. The validator
uses these facts without a frontend environment or authored files.

A prompt slot row is `{name, kind, type, value, renderer_id, output_role,
placeholder_ordinals}` in declaration order. For `doc`, `renderer_id` is
null and the row additionally retains required document-reference/content
injection semantics (prepend, declaration order); it is not a rendered text
placeholder. Other kinds retain their selected renderer, refinements, repeated
placeholder positions and any declared output role/path/expected-output
facts. A `doc` fill owns its required content injection: it is not a rendered
placeholder and is prepended in declaration order. Keep that channel in
`prompt.fills`; the separate `dependencies` row contains only explicit
`WccPromptDependencyPayload` operands and its own ordered roles, position and
instruction. Both channels may occur on one provider without replacing one
another. Reuse the existing fragment/dependency owners' semantic projections;
keep step ids and source subjects under provenance. Do not reduce these to
counts or discard output-slot semantics.

### Provenance

Every node that came from a source form carries `"@": {"span": "<path>:<line>:<column>", "form": [...]}`.
The path is the one the reader recorded, as the source map records it today.
`strip_provenance` removes every `@` key; the digest is taken over the
stripped tree (P6, P7).

### Binding labels

Lexical names resolve values; authored labels identify sites, call frames,
and bound control segments. An optional `label` is allowed only on `let`,
`select` prefix rows, `join`, and `loop`. When present it must be a nonempty
string, never null. It labels the `let`/prefix row's `name`, the join's sole
`params[0][0]`, or the loop's `param`; it never labels a generated join/loop
target. Case-arm and `list_map` binders need no closed `label` field.

| Closed binding | Effective identity label |
| --- | --- |
| `label` present | Its authored string |
| `label` absent, lexical spelling begins `%` | Anonymous; use design §6's I4 ordinal |
| `label` absent, otherwise | The lexical spelling as an authored label |

The builder emits an override when the retained authored label differs from
the lexical spelling or itself begins `%`; otherwise the field is omitted.
Compiler-created bindings become `%n` without a label. Thus lexical `%2`
with `label: "x"` preserves a hygienically renamed authored `x`, while an
authored `%1` explicitly retains `label: "%1"`. This is the closed encoding,
not a rule for guessing frontend origin from a name.

Apply I4 and presentation escaping to the effective label, not its lexical
name. Pure bindings advance neither anonymous-effect nor repeated-label
counters. Escape authored `% / = # [ ]` before presenting identity segments;
an authored suffix is never an assigned ordinal. The `label` field is
semantic data outside `@`, retained in the program digest. Validation checks
its shape, rejects it on other node kinds, and recomputes site/frame
correspondence from it. A consistently changed label/site/digest describes
another program; read-back adds no source-authenticity claim. Pure code
edits may change the program digest without changing sites or frames.

The compiler retains the one authored-label-or-generated fact through
existing binders; [Task 4](#binding-origin-retention-and-conversion) owns
its complete frontend/WCC carriage. No hash suffix, source position,
binding registry, or new surface admission rule is involved.

### Names

- Binding origin is explicit: preserve unchanged authored lexical names;
  rename compiler-created and hygienically renamed authored binders `%<n>`
  per definition in binding order, reserving all authored lexical names and
  parameters before allocation. Resolve references in lexical scopes.
  Authored effect labels survive through the [binding-label rule](#binding-labels),
  including admitted names beginning `__` or `%`; prefixes do not establish
  origin. [Task 6](#task-6-names-that-hold-no-path) owns the Renamer.
- Callable keys and names follow [Canonical definition keys](#canonical-definition-keys):
  the base is unconditionally `procedure:module::name` or
  `workflow:module::name`, including the entry. Unspecialized top-level
  definitions use the base alone; specialized/local/capture-converted names
  append the full canonical-key SHA-256 in brackets. The same pure
  `canonical_callee_name_from_key` operation serves builder and checker.
  Persist the complete nine-component tuple and ordered residual types;
  sort formal selectors as specified there, retaining argument/field order.
  Runtime captures are explicit typed parameters/arguments, never
  runtime proc-ref values. Local keys ignore spans, generated names, body
  digests and unrelated pure bindings. Generated run-reference types use
  their canonical input/result structural signature in definition keys;
  after site assignment, Task 8 hashes the containing canonical definition,
  local site and that signature together into `site_digest`, and the existing
  neutral name rule derives the final nominal name from its first 16 hexadecimal characters.
- Nominal type identities and descriptors recursively use the declaring
  module, exported or private. Applied arguments, list/optional members,
  fields and variants recurse; generated run-ref result names never reuse
  `RunRefResult$…` from typecheck. Compiler-owned fixed run-ref runtime records
  retain the neutral codec's reserved logical identities, as specified in
  Task 8; user declarations with the same spelling remain module-qualified.
- Site segments follow the full traversal table of design §6: `select`
  prefixes under binder/arm, `block` under binder/`block`, join body under
  result binder/`body` with its continuation at the enclosing prefix, loop
  body/exhaustion separately. Pure bindings consume no effect ordinal.
  Segments are tagged internally; presentation escapes `% / = # [ ]` in
  authored names using UTF-8 percent encoding. Calls get frames only.

---

## Task Map

| Task | What | Group | Files it owns |
| --- | --- | --- | --- |
| 1 | The new target exists and refuses to run | A (alone, first) | `syntax.py`, `workflow/validation.py`, `run_ref/config.py`, `run_ref/bundle_transport.py`, `closed/__init__.py`, `closed/target.py`, `cli/commands/run.py`, `cli/commands/resume.py`, `specs/versioning.md`, `specs/dsl.md`, `specs/index.md` line 1, `tests/test_workflow_lisp_target_234.py` |
| 2 | The public compile entry that stops after typecheck | B (alone) | `closed/frontend.py`, `compiler.py` (source producers and graph), `workflows.py` (result and signatures), `workflow/loaded_bundle.py`, `build_artifacts.py` (source digests), `build.py` (export selector) |
| 3 | The elaborator at the new target | C | `wcc/model.py` (`WccIdentityFactory.closed_program`), `wcc/elaborate.py`, `expressions.py`, `conditionals.py`, `typecheck_proofs.py`, `typecheck_dispatch.py`, `typecheck_structural_values.py`, `build_manifest_io.py`, `procedure_typecheck.py` (transient loop and binding-prefix order) |
| 5 | Sites and the checked form | C | `closed/sites.py`, `closed/check.py`, `closed/names.py` (pure key-to-name and run-reference projection helpers), `workflow/type_descriptor.py` (boundary projection checking) |
| 6 | Names that hold no path | C2 (after 5) | `closed/names.py` (extend with typed construction), `type_env.py` (declaring module index) |
| 7 | The program artifact, its digest, and the manifest field `closure` | C2 (after 5) | `closed/program.py`, `command_boundaries.py`, `build_manifest_io.py`, `stdlib_contracts.py`, `compiler.py` (injected binding origins), `closed/frontend.py` (carriage) |
| 4 | The builder: bodies, values, the table, X1 to X4, command nodes; binding-origin carriage | D (alone) | `closed/build.py`, `closed/values.py`, `closed/context.py`, `closed/effects.py` (commands and the closure rule), `typecheck_effects.py` (one gated line), `expressions.py`, `typecheck_dispatch.py`, `conditionals.py`, `functions.py`, `typecheck_structural_values.py`, `procedure_typecheck.py`, `wcc/model.py`, `wcc/elaborate.py`, `wcc/anf.py` (origin retention after Task 3), `tests/workflow_lisp_closed_program_helpers.py` |
| 8 | Effect nodes: providers, run references, the gaps | E | `closed/effects.py`, `closed/build.py` (run-ref finalization call) |
| 9 | `orchestrator compile` at the new target: the build key and the artifact on disk | E | `closed/artifact.py`, `build.py` (manifest validation), `cli/commands/compile.py` |
| 10 | The corpus check | F | `tests/workflow_lisp_closed_program_corpus.py`, `tests/test_workflow_lisp_closed_program_corpus.py` |
| 11 | Documents | F | `specs/versioning.md`, `specs/io.md`, `docs/design/workflow_command_adapter_contract.md`, `docs/design/workflow_lisp_core_calculus_middle_end.md`, `docs/design/workflow_lisp_evaluated_execution.md` (status lines), `docs/lisp_workflow_drafting_guide.md`, `docs/index.md`, `docs/design/README.md`, `docs/capability_status_matrix.md` |

Order: A, then B, then C (Tasks 3 and 5 may run in parallel), then
C2 (Tasks 6 and 7 may run in parallel after Task 5's validator and pure
name helper are merged), then D (Task 4),
then E (Tasks 8 and 9 may run in parallel), then F (Tasks 10 and 11).
Task 9 initially tests the command-only route from Task 4; its provider and
run-ref integration selectors run after Task 8 is merged. Task 11's status
edits land only after Task 10's evidence. Merge prerequisites into each
isolated worktree before dispatch. File disjointness alone is insufficient.

Spike line counts are historical evidence, not implementation budgets:
revised capture conversion, recursive descriptors, full
artifact typing and total traversal were not proved by the spike. Reuse the
existing owners named in each task; no new runtime or generic framework is
part of this plan.

Every task ends with the compatibility evidence named in the task, using the
programs of this table; a task that touches no shared module states so and
skips the builds.

| Program | Target | Why |
| --- | --- | --- |
| `workflows/examples/kiss_backlog_item.orc` (inputs under `workflows/examples/inputs/kiss_backlog_item/`) | 2.14 | oldest maintained example, `with-phase` |
| `workflows/examples/review_revise_design_docs_judgment_panel.orc` | 2.23 | phased delivery, imports |
| `workflows/examples/improve_experiment_proposal.orc` | 2.33 | a parametric specialization whose step ids digest `repr(TypeRef)` |
| the `PROGRAM` of `tests/test_workflow_lisp_target_234.py`, written to a fixed path | 2.34 | the newest existing target |

---

### Task 1: The New Target Exists And Refuses To Run

**Completed 2026-09-30:** implementation `184f9b6b`; specification and quality
reviews passed after correcting both observed execution bypasses. Fresh narrow
checks passed (318 tests plus the final smoke); all 88 artifact pairs matched
`PHASE2_BASE` byte for byte. The source-consistency and child-admission
corrections below are part of this completed task.

**Files:**
- Modify: `orchestrator/workflow_lisp/syntax.py` (`SUPPORTED_TARGET_DSL_VERSIONS`, the gate constants near line 51 to 70, the predicates)
- Modify: `orchestrator/workflow/validation.py` (`DEFAULT_SUPPORTED_VERSIONS`, `DEFAULT_VERSION_ORDER`)
- Modify: `orchestrator/workflow/run_ref/config.py`, `orchestrator/workflow/run_ref/bundle_transport.py` (`_SUPPORTED_TARGET_DSL_VERSIONS`)
- Create: `orchestrator/workflow_lisp/closed/__init__.py` (empty docstring module), `orchestrator/workflow_lisp/closed/target.py`
- Modify: `orchestrator/cli/commands/run.py` (`run_workflow`, before `build_frontend_bundle` at line 629), `orchestrator/cli/commands/resume.py` (before `build_frontend_bundle` at line 233)
- Modify: `orchestrator/workflow_lisp/build.py` (shared runnable-bundle admission, using the compiled source snapshot; execution correction below)
- Modify: `orchestrator/workflow/run_ref/child.py`, `orchestrator/workflow/run_ref/runtime.py` (reject precompiled evaluated-target capsules and retain the structured diagnostic through the parent)
- Modify: `specs/versioning.md` (a `v2.35 additions` block after the `v2.34` block at line 736, a roadmap line after line 816, a table row after line 967), `specs/dsl.md` line 23 (admitted revisions extend through `"2.35"`), `specs/index.md` line 1 (the title's range)
- Modify: `tests/test_workflow_lisp_target_234.py` (the gate dictionaries)
- Test: `tests/test_workflow_lisp_target_evaluated_execution.py`, `tests/test_workflow_lisp_compiler_session_state.py`, `tests/test_workflow_run_ref_child.py`, `tests/test_workflow_run_ref_runtime.py`

**Read first:** `tests/test_workflow_lisp_target_234.py` in full; the Phase 0
Task 0 report's list of every place a version is compared (every gate is
"this target or newer", so the new target passes every 2.x gate with no
edit); design §13.

**Interfaces:**
- Produces: `syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION: str = "2.35"`
  (the owner-selected target; later tasks consume this constant) and `syntax.target_dsl_uses_evaluated_execution(target_dsl_version: str) -> bool`
  (tuple comparison `>=`, like `target_dsl_supports_numeric_surface`).
- Produces: `closed.target.entry_target_dsl_version(path: Path) -> str`
  (reads the entry header through the existing reader and syntax parser,
  without resolving imports, and returns `syntax_module.target_dsl_version`) and
  `closed.target.refuse_run_at_evaluated_execution_target(path: Path) -> None`,
  which raises `LispFrontendCompileError` with one diagnostic
  `code="evaluated_execution_unavailable"`, `phase="lowering"`, at the span
  of the module's `:target-dsl` form (the span `target_dsl_unsupported` uses
  today), when the target uses evaluated execution.
- Consumed by: every later task (the predicate); Task 9 (`entry_target_dsl_version`).

**Execution correction (2026-09-30):** the original stage-1 lookup resolves
imports without the caller's `--source-root` settings. A target-2.34 entry
whose import lives in an additional root reproduces `module_not_found` through
`compile_stage1_module(entry)` while its configured frontend build succeeds.
Both public helpers therefore share entry-only parsing, retaining the parsed
header value's span. This preserves configured import resolution for the
subsequent build and also applies to Task 9's target selection. Cover the
helper and the older-target public run with this regression case.

**Execution correction (source consistency):** quality review reproduced a
target-2.34 entry changing to 2.35 after the early guard and before the build:
the original guard then allowed both commands to execute. Availability must
also be established for the source actually compiled, before either `run`
or `resume` dispatches. Reuse the existing compiled source snapshot or source
read consistency owner; a second read of the live file is insufficient. Pin
the interleaving through the public entries with a located refusal, exit 2
and no command dispatch, including a source changed back after compilation
if the fix checks the compiled result.

The same review also executed a static 2.35 child through path-mode `run-ref`,
which bypasses the CLI guards. Enforce availability in the shared legacy
bundle-building owner so run, resume, child compilation and imported bundles
cannot obtain a runnable flat bundle for this target. Extend the regression
to the public child path, preserving its existing structured refusal contract.
Precompiled capsules also require admission at the common child execution
entry using the compiled bundle target. Carry the refused target, minimum
target and source location through the closed child diagnostic and its parent
consumer; locating a source span must not change the admission decision.
The legacy builder may refuse 2.35 in `compile`/`explain` until Task 9 supplies
the separate closed-program build route. This restriction does not belong in
the typechecking entry that Task 2 introduces.

- [x] **Step 0: Record the owner-selected target and implementation base.**

The reviewed plan was presented and the owner selected **2.35** on
2026-09-30. Use that number in the registries/docs and the gate constant in
fixtures. `PHASE2_BASE=2e4c7a653d74c06e24c15c284662e5914abd5576` records the
clean integrated source before Task 1 for compatibility comparisons.

- [x] **Step 1: Write the failing tests**

`tests/test_workflow_lisp_target_evaluated_execution.py`, importing
`_write_program`, `_public_run`, `_log`, `GATE_PREDICATES` and `GATES_FROM_234`
from `tests/test_workflow_lisp_target_234.py`:

```python
from orchestrator.workflow_lisp import syntax
TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION

@pytest.mark.parametrize("registry", [syntax.SUPPORTED_TARGET_DSL_VERSIONS, validation.DEFAULT_SUPPORTED_VERSIONS,
                                      run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS])
def test_the_evaluated_execution_target_is_registered(registry) -> None:
    assert TARGET in registry

def test_shared_validation_orders_the_new_target_last() -> None:
    assert validation.DEFAULT_VERSION_ORDER[-2:] == ("2.34", TARGET)

def test_the_gate_opens_at_the_new_target_only() -> None:
    assert (syntax.target_dsl_uses_evaluated_execution("2.34"), syntax.target_dsl_uses_evaluated_execution(TARGET)) == (False, True)

@pytest.mark.parametrize("gate", sorted({**GATE_PREDICATES, **GATES_FROM_234}))
def test_every_gate_that_234_passes_holds_at_the_new_target(gate: str) -> None:
    assert {**GATE_PREDICATES, **GATES_FROM_234}[gate](TARGET) is True

def test_run_refuses_a_program_at_the_new_target_before_any_command(tmp_path, monkeypatch) -> None:
    files = _write_program(tmp_path, TARGET)
    line = next(n for n, text in enumerate(files["source"].read_text().splitlines(), 1) if ":target-dsl" in text)
    monkeypatch.chdir(tmp_path)
    result = _public_run(files)
    assert result.exit_code == 2
    assert _log(tmp_path / "probe_revise.py") == []
    assert [(d.code, Path(d.span.start.path), d.span.start.line) for d in result.diagnostics] == \
        [("evaluated_execution_unavailable", files["source"], line)]
```

Read `run_workflow`'s result type first and adapt the last assertion to how it
carries diagnostics (it renders them through the logger today; if the result
holds none, assert on the captured log records' `code` through `caplog` with
the diagnostic's rendered location, which `render_diagnostic` prints as
`<path>:<line>:<column>: [<code>]`). Add the resume test the same way
(`orchestrator resume` on a run directory whose `workflow_file` names the
program: exit 2, same code). Add an unregistered next-version refusal derived from the selected target
(`target_dsl_unsupported`, as `test_target_235_is_refused_as_unsupported`).

- [x] **Step 2: Run them; expected failures**

`pytest -q tests/test_workflow_lisp_target_evaluated_execution.py`: the
registry tests fail with `'2.35' not in ...`, the gate test with
`AttributeError`, the run test with exit 0 and a command in the log (the
program lowers on the flat route because every gate is `>=`).

- [x] **Step 3: Implement**

Add `"2.35"` to the four registries and to the end of `DEFAULT_VERSION_ORDER`.
Add the constant and predicate to `syntax.py`. Write `closed/target.py`.
In `run_workflow` and in `resume`, inside the `try` that catches
`LispFrontendCompileError` around `build_frontend_bundle`, call
`refuse_run_at_evaluated_execution_target(workflow_path)` first. In
`tests/test_workflow_lisp_target_234.py` add
`GATES_FROM_EVALUATED = {"EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_uses_evaluated_execution}`
and include it in `test_every_min_target_gate_has_a_predicate_here`; leave
the 2.34 assertions as they are (2.34 must not pass the new gate).

- [x] **Step 4: Run the tests; expected pass**

The new module, then `tests/test_workflow_lisp_target_234.py` (its
`test_every_min_target_gate_has_a_predicate_here` fails until the dictionary
is added) and `tests/test_workflow_shared_validation.py` (its version-catalog
test expects the order to end at 2.34: update that expectation as the 2.34
commit did), `tests/test_workflow_lisp_target_233.py`.

- [x] **Step 5: Documents**

`specs/versioning.md`: a block `v2.35 additions (in progress)` stating that
the target exists, that a program at it is compiled to a closed program and
not to steps, that `run` and `resume` refuse it with
`evaluated_execution_unavailable` until the evaluator lands, and that the
tasks of this plan add the closed program; a roadmap line; a table row.
`specs/dsl.md` line 23: admitted revisions extend through `"2.35"`.
`specs/index.md` line 1: the range (two tests compare it with the highest
supported version).

- [x] **Step 6: Compatibility evidence**

Build the four programs of the table at the base and at the head. Expected:
every artifact byte-identical (the registries add a member; no gate changes).

- [x] **Step 7: Commit**

`git add -- orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow_lisp/closed orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py specs tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_shared_validation.py orchestrator/workflow_lisp/build.py orchestrator/workflow/run_ref/child.py orchestrator/workflow/run_ref/runtime.py tests/test_workflow_lisp_compiler_session_state.py tests/test_workflow_run_ref_child.py tests/test_workflow_run_ref_runtime.py`

`git commit -m "feat: register the evaluated execution target and refuse to run it before the evaluator exists" -- orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow_lisp/closed orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py specs tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_shared_validation.py orchestrator/workflow_lisp/build.py orchestrator/workflow/run_ref/child.py orchestrator/workflow/run_ref/runtime.py tests/test_workflow_lisp_compiler_session_state.py tests/test_workflow_run_ref_child.py tests/test_workflow_run_ref_runtime.py`

**What this makes harder later:** Phase 3 must remove the guard in `run` and
`resume` and route the new target to the evaluator; the test that pins the
refusal changes then. Task 9's closed build must remain separate from legacy
runnable-bundle admission. Phase 3 must route new-target children to the
evaluator before replacing their refusal; it must not enable flat bundles
at the evaluated target.

---

### Task 2: The Public Compile Entry That Stops After Typecheck

**Completed:** `ad70260b567d854708a9b30ef63a8e0b0e712d33`, with separate spec
and quality review passes. Verification: 44 frontend tests, 16 independent
admission/transport probes, nine public compile fixtures, and fresh
compatibility against `PHASE2_BASE`: 88 raw pairs equal; 67 capsule pairs
equal at fixed identity, with the 12 expected real-pin run-ref differences
reported separately.

**Files:**
- Create: `orchestrator/workflow_lisp/closed/frontend.py`
- Modify: `orchestrator/workflow_lisp/compiler.py` (`_compile_stage3_graph`, the call of `_lower_workflows_for_route` at line 3083 and the `Stage3CompileResult` construction at line 3130)
- Modify: `orchestrator/workflow_lisp/workflows.py` (`Stage3CompileResult`, signature reconstruction/catalog owners)
- Modify: `orchestrator/workflow/loaded_bundle.py` (transient `typed_program` field and pickle state)
- Modify: `orchestrator/workflow_lisp/build_artifacts.py` (reuse traced digest validation for standalone producers), `orchestrator/workflow_lisp/build.py` (shared export selector over available names; preserve legacy loader/return contract)
- Test: `tests/test_workflow_lisp_closed_program_frontend.py`

**Read first:** `experiments/evaluated_execution_spike/frontend.py` (what the
spike captured from `_lower_workflows_for_route`'s arguments); `compiler.py`
lines 2481 to 3208 (`_compile_stage3_graph`, one iteration per module in
topological order); `compile_stage3_entrypoint` (line 651); how
`_select_entry_workflow` and `validated_bundles_by_name` are used by
`build.py` (`_compile_entry`, `_select_and_reattach`).

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class TypedProgram:
    entry: TypedWorkflowDef | None  # None only during graph assembly; public return always selected
    workflows: Mapping[str, TypedWorkflowDef]          # every typed workflow of the graph, by canonical name
    procedures: Mapping[str, TypedProcedureDef]        # every typed procedure, specializations included
    type_env: FrontendTypeEnvironment                  # the entry module's
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    workflow_type_envs: Mapping[str, FrontendTypeEnvironment]
    module_type_envs: Mapping[str, FrontendTypeEnvironment]   # module name -> its environment, whole graph
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]
    command_boundary_origins: Mapping[str, str]  # trusted workspace/package origin; Task 7 adds injection carriage
    externs: Mapping[str, ProviderExtern | PromptExtern]     # entry resolved environment
    module_externs: Mapping[str, Mapping[str, ProviderExtern | PromptExtern]]  # existing environments, no alias flattening
    imported_programs: Mapping[str, TypedProgram]  # explicit binding -> selected producer snapshot
    module_workflow_signatures: Mapping[str, Mapping[str, WorkflowSignature]]  # declaring module -> caller-view catalog signatures
    configuration_bindings: Mapping[str, object]  # all caller/manifest bindings plus used injected bindings
    target: str
    entry_module: str
    entry_dir: str      # logical directory for asset lookup only, not definition identity
    source_file_digests: Mapping[str, str]  # module -> exact bytes consumed by this compile
    local_definition_keys: Mapping[str, object]  # old generated lookup name -> position-free lexical key
    _compiled_bundle_boundaries: Mapping[
        str, tuple[Mapping[str, Mapping[str, object]],
                   Mapping[str, Mapping[str, object]], WorkflowBoundaryProjectionView]
    ] = field(default_factory=dict, repr=False, compare=False)

    def workflow_type_env(self, name: str) -> FrontendTypeEnvironment: ...
    def procedure_type_env(self, procedure: TypedProcedureDef) -> FrontendTypeEnvironment: ...  # procedure_type_env_for
```

```python
def compile_typed_program(
    entry_path: Path, *, entry_workflow: str, source_roots: tuple[Path, ...],
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, PromptExternValue] | None = None,
    workspace_root: Path | None = None,
    source_read_trace: SourceReadTrace | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    imported_programs: Mapping[str, TypedProgram] | None = None,
) -> TypedProgram
```

  It calls `compile_stage3_entrypoint(...)` with `validate_shared=True`,
  `lowering_route=None`, forwarding one supplied or newly created
  `SourceReadTrace` through entry reading, imports and all compiler reads.
  Before returning the selected `TypedProgram`, call
  `_source_file_digests_from_trace(compile_result=result,
  source_read_records=trace.records, source_revision_vector=trace.revision_vector)`
  and retain its module-to-digest map. Never reread source after compile to
  form it. The existing linked result provides the module graph; no new
  signature or graph-result abstraction is needed.
  It raises `LispFrontendCompileError` with `evaluated_execution_target_required`
  at the `:target-dsl` span when the entry module's target does not use
  evaluated execution, and the typechecker's own diagnostics unchanged when
  the program does not typecheck.
- Produces: `Stage3CompileResult.typed_program: object | None = None`;
  source producers at both old and evaluated targets populate it when their
  complete typed closure is available. An old producer importing an opaque
  bundle keeps its existing compilation behavior and leaves `typed_program`
  as `None`; a later evaluated import refuses that incomplete input rather
  than inventing its missing dependency. Public selection happens after the
  complete graph; snapshot presence never selects
  the lowering route. Direct `compile_stage3_entrypoint` and
  `compile_stage3_module` create `SourceReadTrace()` if none was supplied,
  before `_effective_source_roots`/graph-attempt reads or
  `_syntax_module_uses_module_graph`, respectively. Delegation forwards the
  same trace. Freeze its records/revision vector after final producer reads,
  then derive digests before snapshot attachment, without another path read.
  Extract `_source_file_digests_for_modules(module_paths: Mapping[str, Path],
  *, source_read_records, source_revision_vector) -> dict[str, str]` from the
  existing linked helper: linked and standalone use the same revision checks,
  selecting actual compiled module paths. The evaluated standalone entry
  keeps the checkpoint's fixed `entry` namespace; old-target producers retain
  their existing identity/canonicalization (including path-stem identity where
  applicable). Snapshot creation must not rename legacy definitions. No fake
  graph/result or hash from current live files.
- Produces: `LoadedWorkflowBundle.typed_program` with default `None`,
  `compare=False`, `repr=False` (type-only import). Its `__getstate__` returns
  existing instance state minus only `typed_program`; old pickles obtain the
  default on decode. Attach selected snapshots to each final source-produced
  export after shared validation's replacements. Cover the standalone producer
  too. Preserve incoming bundle identity and existing freeze/replace paths;
  do not attach the consumer's snapshot to an imported bundle.
- Rule of `_compile_stage3_graph` (§13): compute `closed_entry` once from
  `graph.modules_by_name[graph.entry_module_name].syntax_module.target_dsl_version`.
  When true, skip `_lower_workflows_for_route` and bundle validation/production
  for **every source module**, including imports declared at older targets.
  Keep imported typed signatures (`_imported_workflow_signatures`), procedure/
  workflow effects, catalogs, environments and typed bodies published in the
  same topological order. `_workflow_name_resolver` already resolves graph
  imports through `import_scope`; do not fabricate `validated_bundles` just to
  populate `external_workflow_names`. Explicit supplied compiled imports use
  the admission and ownership rules below. No body is fabricated from flat
  steps; once admitted, a missing body is a compiler defect. Source calls
  remain admitted. Apply `closed_entry` to source-map/shared/executable
  pipeline passes that require flat artifacts too; old entries retain their
  existing validation profile even with a populated snapshot. Standalone
  routing derives the same predicate once from parsed entry syntax.
- For an older-target entry, preserve the existing lowering path. Detect an
  older-to-evaluated call/import edge before lowering the new module, and
  emit `evaluated_execution_target_direction_invalid` at its import/call
  source location, naming both modules/targets. Also check call edges inside
  an evaluated-entry graph: an imported older module cannot call back into a
  module declared at the new target. New-entry-to-old-import remains allowed.
- Compiled-import admission (design §4.2.1): forward the new
  `imported_programs` keyword through Stage 3 and graph compilation alongside
  its existing bundle map. A binding occurs in only one map. For a bundle,
  obtain its snapshot from `bundle.typed_program`; for a typed product, require
  a selected `entry`. Require the matching complete transitive producer
  snapshot before admitting the import; absent/incomplete or structurally
  mismatched pairing raises `compiled_workflow_source_required` at the
  binding/source/manifest location, naming the selected workflow. This is an
  input precondition, never `closed_program_gap`. Through 2.34, existing
  supplied-bundle admission is unchanged, including opaque decoded bundles.
  Restoration is explicit `dataclasses.replace(decoded, typed_program=original)`;
  check selected workflow/boundary contracts including private inputs, but
  claim structural consistency only, not historical body authenticity. Never
  reread `provenance.workflow_path`; recompiling changed source is replacement.
  Populate `_compiled_bundle_boundaries` from each final source-produced
  validated bundle at both existing digest/attachment points. Reuse the
  input/output/projection accessors and existing configuration freezer;
  detach nested contracts, lists and private-binding hints/provenance.
  Retain complete `WorkflowBoundaryProjectionView`/`PrivateExecContextBinding`
  facts, not just a digest or a new carrier. Pair against this original map,
  comparing contract keys/structure, default and projection presence/values,
  and semantic private classification/binding metadata. Ignore diagnostic
  source provenance and contract routing `from`/`__allow_unresolved_source`.
  Never capture expected facts from the candidate during admission or
  rederive private lowering from native signatures. A missing selected map
  entry refuses a bundle; typed-only snapshots may have an empty map. The
  entryless result and selected source exports retain the complete map;
  imported snapshots keep their own original maps. This field remains outside
  legacy bundle serialization with the rest of `typed_program`.
- The snapshot freezes retained maps and preserves each producer's source
  digests, bodies, native signatures, externs, command origins/configuration
  and logical asset base. `imported_programs` retains nested owners; do not
  merge producer trace evidence into the caller's trace. Before interning a
  canonical module/callee, equal source/context may deduplicate; unequal
  revisions, bindings or logical asset context (including source/snapshot
  overlap) raise `compiled_workflow_snapshot_conflict` naming both origins.
  No multi-version canonical-key extension or last-write-wins is introduced.
- Preserve the existing bundle caller-view signature owner. Extract
  `_signature_from_imported_contracts(alias, *, input_contract_groups,
  output_contracts, type_env, span, form_path) -> WorkflowSignature` from
  `workflows._signature_from_imported_bundle`, reusing its contract matching
  and default reconstruction. `input_contract_groups` is an ordered tuple
  of `(formal_name, contracts_by_wire_name)` pairs, not a new carrier. The
  bundle wrapper keeps current public/private classification, including
  `private_runtime_context_bindings.source_param_name`, and hidden/compatibility
  facts; never regroup those inputs by flattened-name splitting. A typed-product
  wrapper uses
  `derive_workflow_signature_contracts` and retains the native signature's
  hidden/compatibility facts without deriving them from flat fields. No fake
  bundle is needed. Keep explicit aliases as catalog/typecheck lookup names;
  retain per-module caller views in `module_workflow_signatures`. Task 4
  resolves the alias to `imported_programs[alias].entry.definition.name` for
  the closed call and uses that snapshot's native body. Do not overwrite the
  native signature with a reconstructed caller view. This task carries facts;
  Tasks 4/5/7 own boundary translation/checking and scoped configuration.
  Bundle imports always use the bundle caller-view wrapper; only
  `imported_programs` uses the native-contract typed wrapper. A populated
  snapshot does not replace the bundle's existing caller contract.
- Consumed by: Tasks 3 to 10.

- [x] **Step 1: Write the failing tests**

Fixtures: create `tests/fixtures/workflow_lisp/closed_program/` and copy
`loop_in_branch.orc`, `three_call_sites.orc`, `arms_in_loop.orc`,
`if_in_hook.orc`, `loop_in_loop.orc`, `if_over_lists.orc`,
`provider_review.orc`, `prompt_dependency.orc` and `chain.orc` from
`tests/experiments/fixtures/evaluated_execution_spike/`, replacing each
`(:target-dsl "2.33")` with `(:target-dsl "TARGET")` and each
`(defmodule spk/<name>)` with `(defmodule cp/<name>)`. Tests substitute
`TARGET` with `syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION`.

```python
def test_a_program_the_flat_route_refuses_typechecks_into_a_typed_program(tmp_path) -> None:
    entry = install(tmp_path, fixture("loop_in_branch"))      # helpers as the spike's `install`, local to this module
    typed = compile_typed_program(entry, entry_workflow="cp/loop_in_branch::run", source_roots=(tmp_path,),
                                  command_boundaries=BOUNDARIES)
    assert (typed.entry.definition.name, typed.target, sorted(typed.procedures)) == (
        "cp/loop_in_branch::run", TARGET, ["cp/loop_in_branch::fetch"])

def test_the_graph_result_at_the_new_target_holds_no_lowered_workflow(tmp_path) -> None:
    result = compile_stage3_entrypoint(entry, source_roots=(tmp_path,), command_boundaries=BOUNDARIES,
                                       validate_shared=True, workspace_root=tmp_path, lowering_route=None)
    assert (result.entry_result.lowered_workflows, result.entry_result.typed_program is not None) == ((), True)

def test_evaluated_entry_skips_flat_lowering_for_its_whole_source_graph(tmp_path, monkeypatch) -> None:
    # New entry calls an imported old-target workflow with a typecorrect loop in a branch.
    # Replace _lower_workflows_for_route with a raising sentinel: neither module calls it.
    # Every source result has lowered_workflows == () and validated_bundles == {};
    # old workflow signature/effects/body and imported procedure specializations survive.
    ...

def test_the_same_old_entry_keeps_its_existing_flat_route_refusal(tmp_path) -> None:
    # Compile the old module itself through compile_stage3_entrypoint.
    # Observed loop_in_branch refusal: workflow_signature_mismatch at line 17, column 28.
    ...

def test_an_old_to_new_edge_has_a_located_target_direction_refusal(tmp_path) -> None:
    # Test old entry -> new module and new entry -> old helper -> new callee; neither silently crosses runtimes.
    ...

def test_source_digests_describe_the_compile_reads_not_a_later_reread(tmp_path, monkeypatch) -> None:
    # Record source bytes, then mutate an imported file after its traced read but before API return.
    # Returned map hashes the consumed bytes; a fresh next compile observes the edit.
    ...

def test_a_type_error_at_the_new_target_keeps_its_code(tmp_path) -> None:
    # a signature naming an undeclared type: code `type_unknown` at the same line as at 2.34
    ...

def test_an_entry_at_2_34_is_refused_by_the_typed_entry(tmp_path) -> None:
    # code evaluated_execution_target_required at the :target-dsl line
    ...
```

Add direct producer tests for implicit and supplied traces, trace identity
through module-wrapper delegation, conflicting repeated source reads, and
source deletion/mutation after final reads but before attachment. Pin exact
consumed digests and old-profile lowering/shared-validation calls. Cover
selected exports, private/transitive bodies, missing decoded snapshots,
explicit restoration and structurally wrong pairing; preserve old bundle `is`.
An old source producer importing an opaque bundle still compiles, leaves its
complete snapshot absent, and is refused when supplied to an evaluated entry.
Change/delete producer source and change caller configuration: the accepted
snapshot must retain its original body/configuration/digests. Cover equal and
conflicting source/snapshot overlaps and nominal caller-view signatures.
Boundary artifact generation belongs to Task 4, not these frontend tests.

- [x] **Step 2: Run; expected failures**

`ImportError` on `closed.frontend`; then, once the module exists but the
graph still lowers, the observed `loop_in_branch` flat-route refusal is
`workflow_signature_mismatch` at line 17, column 28. Preserve that actual
legacy diagnostic rather than the earlier predicted boundary-type code.

- [x] **Step 3: Implement**

In `_compile_stage3_graph`, derive `closed_entry` from the entry target
**before the module loop** and check target-direction edges. When
`closed_entry`, do not lower. Build a source `TypedProgram` for both routes
from the same arguments the lowering call receives (`typed_workflows`,
`resolved_combined_procedures`, `typed_workflows_by_name`,
`combined_procedure_type_envs`, `workflow_type_envs_by_name`,
`extern_environment`, `command_boundary_environment`, `type_env`), retaining
extern bindings by declaring module and resolved workflow-reference rebinding
so identical aliases in different modules cannot overwrite one another, plus
`module_type_envs` accumulated across the loop (a dict the loop fills with
`type_env` per module name), local-definition lexical facts and `entry_dir`.
Use existing `GeneratedLocalProcedure` metadata for owner/name/capture facts;
recover same-name lexical scope order from the expanded declaration tree,
counting local declarations only. Spans may match an existing node to its
metadata during this compile, but never enter the resulting key. Retain this
small side map, rather than changing old type/definition repr or the existing
span-derived naming function. Put the construction in
`closed/frontend.py` as `typed_program_from_graph(**kwargs) -> TypedProgram`
so graph routing remains a small change in its existing owner. The graph
stays entry-agnostic:
`typed_program_from_graph` sets `entry` to `None`, and
`compile_typed_program` resolves it after the compile: the export surface
of the entry module (`result.graph.export_surfaces_by_name[entry module].workflows_by_name`)
maps `entry_workflow` to its canonical name (also preserve the existing
evaluated standalone-entry selection using fixed namespace `entry`), which must be in
`typed.workflows`; otherwise raise `entry_workflow_unknown` at the source
path, the code and location `build._select_entry_workflow` gives today.
Extract its export selection over an available-name set so old bundle and
new typed producers share the rule without requiring a bundle. Omitted
manifest selection requires one export; a requested raw export resolves to
its canonical target under the existing rule. Return
`replace(typed, entry=typed.workflows[canonical])`; each produced bundle gets
that same complete snapshot selected for its own export.

Check `compile_stage3_entrypoint`'s post-processing on a result with no
lowered workflows: `_filter_profile_checked_linked_diagnostics`,
`_collect_declared_transition_binding_diagnostics_for_linked_result` and
`_dedicated_runtime_proof_boundary_diagnostics` must accept an empty tuple;
read each and add the empty-case guard only where one is missing.

- [x] **Step 4: Run; expected pass**

The new module; `tests/test_workflow_lisp_target_234.py`;
`tests/test_workflow_lisp_generic_unions_runtime.py` (a caller of
`compile_stage3_entrypoint`); `tests/test_workflow_lisp_improve_stdlib.py`.

- [x] **Step 5: Compatibility evidence**

The four programs of the table follow Global Constraints. Also compare
plain, explicit imported-manifest and nested bundle-run-ref artifacts under
real pins and at fixed identity inputs, separately. A transient snapshot must
not alter old serialization. Exercise direct producer paths through both
Stage 3 doors; old lowering/validation still runs despite non-`None` snapshots.

- [x] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/frontend.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow/loaded_bundle.py orchestrator/workflow_lisp/build_artifacts.py orchestrator/workflow_lisp/build.py tests/fixtures/workflow_lisp/closed_program tests/test_workflow_lisp_closed_program_frontend.py`

`git commit -m "feat: a public compile entry that stops after typecheck at the evaluated execution target" -- orchestrator/workflow_lisp/closed/frontend.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow/loaded_bundle.py orchestrator/workflow_lisp/build_artifacts.py orchestrator/workflow_lisp/build.py tests/fixtures/workflow_lisp/closed_program tests/test_workflow_lisp_closed_program_frontend.py`

**What this makes harder later:** `build_frontend_bundle` still expects a
validated bundle; Task 9 gives the closed route its own build function
rather than threading `None` through `_select_and_reattach` and `_emit`.
When Phase 7 retires the flat route, the two build functions merge.

---

### Task 3: The Elaborator At The New Target

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/model.py` (`WccIdentityFactory`, line 73)
- Modify: `orchestrator/workflow_lisp/expressions.py` (`LoopRecurExpr` and its parser; `LetStarExpr`'s retained condition input), `orchestrator/workflow_lisp/typecheck_structural_values.py` (the compiler-generated loop constructor), `orchestrator/workflow_lisp/build_manifest_io.py` and `orchestrator/workflow_lisp/procedure_typecheck.py` (transient-field omission from JSON and legacy semantic identity).
- Modify: `orchestrator/workflow_lisp/conditionals.py` (closed condition selection and shared loop reconstruction), `orchestrator/workflow_lisp/typecheck_proofs.py` (if/cond wrapper transport), `orchestrator/workflow_lisp/typecheck_dispatch.py` (preserve checked inputs on reconstructed lets).
- Modify: `orchestrator/workflow_lisp/functions.py`, `orchestrator/workflow_lisp/expression_traversal.py`, `orchestrator/workflow_lisp/wcc/use_site_scope.py` (semantic transport of retained inputs in the incoming scope, including copied constructor types).
- Modify: `orchestrator/workflow_lisp/wcc/hygiene.py` (ordinary identifier collection excludes retained inputs; retained-input renaming reserves its own complete view).
- Inspect, modify only if necessary: `orchestrator/workflow_lisp/wcc/anf.py` (the gated normalization path)
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`: `elaborate_typed_workflow_body` (line 219), the `DoneExpr` branch of `_elaborate_expr_to_body` (line 1662), `_retarget_loop_continue` (line 2529) and its call at line 2465, the `PhaseTargetExpr` branch of `_elaborate_expr_to_value` (line 2736), `_prebind_effect_argument_matches` (line 4077)
- Test: `tests/test_workflow_lisp_closed_program_elaboration.py`

**Read first:** `experiments/evaluated_execution_spike/repairs.py`
(`bind_done_values`: the `done` and argument repairs, 103 lines);
`_bind_effectful_loop_state_fields` (elaborate.py line 1791: the pattern to
copy for `done`); `hygiene.fresh_name`, `generated_name_scope`,
`reserved_identifiers`; `phase.py` `PHASE_TARGET_SPECS` (line 46) and
`IMPLEMENTATION_ATTEMPT_TARGET_FIELDS` (line 42);
`lowering/phase_scope.py` lines 330 to 398 (what the flat route gives a
`phase-target`: the field for the implementation context, the join
`<artifact-root>/<phase>/<suffix>` for a generic `PhaseCtx`); the spike
report iteration 3, D1 and D2.

**Interfaces:**
- Produces: `WccIdentityFactory.closed_program: bool = False`, propagated by
  `child_scope`, excluded from `scope_id` and node ids (as
  `enclosing_variants` is). `elaborate_typed_workflow_body(..., closed_program: bool = False)`
  sets it on the root scope. Every rule below applies only when
  `scope.closed_program` is true. Below it, nothing changes: byte identity.
- Rule 1 (§4.3, "an effectful expression in an argument position is bound by
  a `let` before the call, in source order"): in `replace_arg` of
  `_prebind_effect_argument_matches`, prebind an argument when
  `scope.closed_program and _contains_effect(arg_expr)`; also prebind the
  `adapter_inputs` values of a `CommandResultExpr` (pairs) and the
  `keyword_args` of a `RunRefExpr` (already handled), in source order.
  `match_bindings` are wrapped outermost-first, which is source order.
- Rule 2 (§4.3, "a `done` value that is an effect or a `match` is bound by a
  `let` before the `done`"): in the `DoneExpr` branch, when
  `expr.result_expr` is a `MatchExpr` or `_contains_effect(expr.result_expr)`
  (same for `terminal_state_expr`), return
  `_elaborate_let_star(LetStarExpr(bindings=((g, expr.result_expr),), body=replace(expr, result_expr=NameExpr(g, ...)), span=..., form_path=..., expansion_stack=...), ...)`
  with `g = fresh_name(_generated_effect_binding_name_from_scope(generated_name_scope(scope).child_scope("loop-done", authored_binding_name="result"), role="result"), reserved_identifiers(expr, value_env=value_env, compile_time_bindings=compile_time_bindings))`.
- Rule 3 (§4.3, "a `continue` names the loop it is in; the elaborator's
  retargeting descends into joins"): `_retarget_loop_continue(body, *, loop_name, through_joins: bool)`
  gains a `WccJoin` case (`replace(body, body=..., continuation=...)`) taken
  when `through_joins`; the call at line 2465 passes `scope.closed_program`.
  A nested `WccRecJoin` is not entered (its own continues are its own).
- Rule 4 (X3): in the `PhaseTargetExpr` branch, when `scope.closed_program`:
  `active_phase_scope` must be set (else raise the `phase_translation_body_invalid`
  the flat route raises); `ctx = active_phase_scope.ctx_expr` must be a
  `NameExpr` or `FieldAccessExpr` after once-only binding at the with-phase
  site. If another admitted context expression arrives, prebind it through
  the same normalization seam; it is not a new `closed_program_gap`. Infer
  the context's type. If its record has the field `implementation_state_bundle_path`,
  return `WccFieldAccessAtom(base=<ctx as a name atom>, fields=(*ctx.fields, IMPLEMENTATION_ATTEMPT_TARGET_FIELDS[target]))`,
  typed by the record's field type (`type_env.record_field`). Otherwise return
  `WccPureOp(operator="path/join", args=(WccFieldAccessAtom(ctx, (..., "artifact-root")), WccLiteralAtom(f"{phase_name}/{suffix}", literal_kind="string")), field_names=())`
  with `suffix = PHASE_TARGET_SPECS[target][2]`, typed as
  `_build_phase_target_type(phase_name, target)`. `path/join` is an operator
  name only the closed builder reads (Task 4 maps it to the `path_join`
  value); the flat route never sees it.
- Rule 5 (case e, gate report §4): no elaborator change. The builder passes
  `procedure_return_types` without generic templates (Task 4).
- Rule 6 (design §4.3): audit every child edge, not just call operands.
  Effect-containing `select`/`block` under aggregates, operator operands,
  conditions, loop seed/budget, `halt`, `jump`, `continue` and `done` values
  are bound before use. Hoist only within the selected arm/iteration and in
  source order, preserving short-circuiting. Extend the gated elaborator
  prebinding seam first; change `wcc/anf.py` only if normalization loses a
  binding. No hidden effectful child survives outside walked bindings.
  Preserve `loop/recur`'s expanded structural `:max`/`:state` keyword order
  on every parsed loop, including older imported typed bodies. Macro operand
  spans can retain call-site order and cannot establish evaluation order.
  Use one transient `LoopRecurExpr.operand_evaluation_order` tuple, retained
  by existing replacements/traversals and excluded from repr, equality,
  hash and serialized artifacts. The existing compiler-generated list loop
  records its construction order (`:max`, then `:state`); hand-built nodes
  without retained order use that deterministic default. Only closed
  elaboration consumes this fact; legacy execution and artifact bytes stay
  unchanged. Extend the existing serializer's field metadata handling to
  omit populated transient fields, and exclude them from the existing
  `procedure_typecheck._semantic_identity` traversal; do not create a second
  serializer or hash algorithm.
  Condition normalization may already have factored these operands before
  WCC sees the loop and moved a nested loop's body prefix outside its owner.
  Retain one transient `LetStarExpr.condition_normalization_input: ExprNode | None`
  containing the already-checked full expression replaced by that generated
  condition wrapper, in its original incoming scope. Ordinary lets leave it
  `None`. Mark it `repr=False`, `compare=False`, `hash=False`, with existing
  unconditional JSON and legacy semantic-identity metadata omission.
  Populate at every already-normalizing target, including independently
  compiled older producers; never recover it by source lookup or rechecking.

  Producers are finite: `typecheck_if_expr` retains the corresponding If
  with typed condition, typed arms and existing proof contexts. Ordinary
  `cond` carries its original typed condition in `CondClauseRewrite` and
  retains the corresponding If with typed result/continuation. Exhaustive
  effectful terminal `cond` retains a semantic LetStar with exactly one fresh
  unused binding to the full typed Bool condition and the typed final
  result; first apply the existing forced-terminal-test fold using its
  terminal facts. Its retained LetStar has no alternate of its own.
  Legacy rows, folds and pure-terminal erasure remain unchanged.

  Replace the local binding-permutation/private-prefix machinery with
  ordinary tuple prefixes. Thread keyword-only `closed_program=False`
  through the existing condition normalizers. Share the existing loop
  reconstruction in a helper returning head rows and the rebuilt loop:
  normalize max/state at their original structural paths, order their row
  groups by `operand_evaluation_order` only under the closed policy, and
  wrap body/exhaustion rows inside their owners. The ordinary loop-value
  normalizer then appends its existing once-only result binding. Under the
  closed policy, `_normalize_loop_body` handles a nested LoopRecur with
  that helper before generic composite traversal, retaining its control
  spine. The default keeps original legacy behavior. No effect predicate
  decides whether an ordinary operand needs normalization: even pure loops
  under `not` require the existing operand normalizer.

  At the start of `elaborate_typed_workflow_body`, before every site, return,
  capture or hygiene scan, select the closed view on a local TypedExpr copy
  while preserving its type/effect evidence. Nodes without an alternate
  recursively select ordinary children without normalizing unrelated nodes.
  At an alternate If, restore all nested alternates inside its condition
  without normalizing them, then run the existing `_normalize_operand`
  once with `closed_program=True`. Select its branches independently,
  rebuild the If with its unchanged proof contexts and wrap the returned
  rows. For the terminal-cond alternate, restore/normalize its one condition
  value in the same way, place returned rows before its unused binding and
  independently select its result. Never revisit freshly generated rows.
  Unexpected alternate roots/row counts are compiler invariant failures.
  Selection is idempotent; generated wrappers have no alternate. Flag-off
  elaboration consumes the stored legacy view without selecting anything.

  Semantic transforms must separately visit the alternate using the
  wrapper's incoming environment, not names introduced by legacy prefixes:
  `map_expr`, function expansion, resolved-inline rewriting, cloning,
  constructor-type resolution, expanded-condition folding, forced-test
  folding, and local/bound-procedure specialization. In particular,
  `_with_resolved_constructor_types` explicitly rewrites the alternate with
  its existing resolver; resolved-inline LetStar rewriting uses incoming
  procedure/workflow reference maps. Normalizer/typechecker LetStar
  reconstructions preserve the checked input without a second check.
  `_unshadow_let_star` processes it with incoming live names, clears it on
  temporary sliced rest nodes and reattaches the independently processed
  result. Renaming the alternate must not consume the legacy fresh-name
  allocator's state. Legacy identifier inventories exclude the alternate;
  the alternate's own allocator reserves names throughout its nested view.
  Global `iter_child_exprs`/`walk_expr` remain one-view; generic
  read-only dataclass collectors skip the alternate to avoid duplicate
  legacy observations. Generic semantic rewrites still visit it. No new
  operator-specific WCC path, source admission rule or release gap is added.
  Enable the existing `_PRESERVE_BOUND_PROC_CAPTURES` mechanism when
  `closed_program=True`, so ordinary `bind-proc` calls retain lexical capture
  aliases and owner/argument capture rows for Task 4. Its existing live-provider
  activation and all behavior with the new flag off remain unchanged; do not
  add a second capture mechanism.
- Consumed by: Task 4 (`closed_program=True`), Task 8.

- [ ] **Step 1: Write the failing tests**

Tests get typed programs through `compile_typed_program` (Task 2) and call
`elaborate_typed_workflow_body(typed.entry.typed_body, owner_name=..., type_env=typed.workflow_type_env(name), value_env=dict(signature.params), workflow_return_types=..., procedure_return_types=..., resolved_procedures_by_name=typed.procedures, procedure_type_envs=typed.procedure_type_envs, route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)`
then `normalize_wcc_body_to_anf`. Assertions are on WCC node shapes.

```python
def test_an_effectful_argument_is_bound_before_the_call_in_source_order(tmp_path) -> None:
    # (defworkflow run () -> Box (fetch (inc 4)))  with inc and fetch command-backed
    body = elaborate(tmp_path, EFFECT_ARGUMENT)
    lets = let_chain(body)                      # the bound values of the outer let chain, in order
    assert [callee(v) for v in lets] == ["cp/effect_argument::inc", "cp/effect_argument::fetch"]
    assert isinstance(lets[1].args[0], WccNameAtom) and lets[1].args[0].name == outer_let_names(body)[0]

def test_a_done_value_that_is_an_effect_is_bound_before_the_done(tmp_path) -> None:
    body = elaborate(tmp_path, DONE_CALL)       # (done (fetch state.n)) in a loop body
    loop = find(body, WccRecJoin)
    tail = last(loop.body)                      # the loop body's tail after its lets
    assert isinstance(tail, WccLoopDone) and isinstance(tail.result, WccNameAtom)
    assert callee(bound_value_of(loop.body, tail.result.name)) == "cp/done_call::fetch"

def test_every_continue_under_a_join_names_its_loop(tmp_path) -> None:
    body = elaborate(tmp_path, fixture("arms_in_loop"))
    loop = find(body, WccRecJoin)
    assert {node.target_name for node in walk(loop.body) if isinstance(node, WccLoopContinue)} == {loop.loop_name}

def test_a_phase_target_on_the_implementation_context_is_its_field(tmp_path) -> None:
    # the with_phase_composed_binding shape, retargeted, provider inputs (phase-target execution-report)
    perform = find(body, WccPerform)
    assert [(a.base.name, a.fields) for a in perform.positional_args if isinstance(a, WccFieldAccessAtom)][-2:] == \
        [("phase-ctx", ("execution_report_target",)), ("phase-ctx", ("progress_report_target",))]

def test_a_phase_target_on_a_generic_context_is_a_path_join(tmp_path) -> None:
    # (with-phase ctx work (phase-target execution-report)) with ctx : PhaseCtx as in phase_stdlib_run_provider_phase.orc
    value = find(body, WccPureOp)
    assert (value.operator, value.args[0].fields, value.args[1].value) == ("path/join", ("artifact-root",), "work/execution-report.md")

def test_below_the_new_target_the_rules_are_off(tmp_path) -> None:
    # closed_program=False on EFFECT_ARGUMENT raises TypeError("unsupported WCC elaboration node: ProcedureCallExpr")
```

Add parameterized WCC-shape cases for select prefixes, nested blocks, join
body/continuation, record/list fields, operator operands, conditions and each
terminal/loop operand. Assert order and branch-local binding, with an unchosen
arm still under that arm. Also a `continue` whose state field holds an effect still binds it (the
2.33 rule is unchanged); the `#`-ordinal-relevant shape of Review Focus 1 is
not this task's. Add an ordinary command-backed `bind-proc` case with a
captured name shadowed between binding and call: the alias is bound before
the shadow, and the call's capture row reads that alias. Compare the flag-off
WCC with the existing behavior. Task 4 still owns conversion to closed capture
parameters/keys and full artifact verification.

Cover both authored loop keyword orders and a macro whose expanded keyword
order disagrees with the operands' source spans. Check that loop operand
effects occur once in that order, and that the transient field changes
neither legacy AST repr/JSON nor the flag-off route. Include an older
imported loop and the compiler-generated loop's retained order.
Cover both orders in `if` and `cond`, repeated nested retained conditions,
exhaustive effectful terminal-cond folding, and runtime/literal-zero nested
loops. Assert that inner body effects remain under both loop joins, head
calls occur once in keyword order, and an unchosen arm remains lazy. Cover
pure/effectful `not(loop)`, an ordinary equality operand and an admitted pure
aggregate operand. Verify actual delayed selection restores nested inputs
before one normalization, all names resolve, and selection is idempotent.
Check helper/resolved-inline/local-procedure transport, shadowed captures,
provenance and a copied cross-module constructor's resolved type after
producer source deletion. Import an independently compiled, reachable 2.34
snapshot through its original validated bundle. Its old-admitted effectful
seed/literal-max case proves reachability and seed locality; the legacy
route refuses a procedure-call max, so use 2.35 cases for two-effect order.
Populated metadata must leave legacy repr/JSON/semantic identity unchanged
and must not duplicate ordinary collector observations. Compare legacy
shadowing/renaming with and without the alternate; retaining it must not
change ordinary output names. Reconstructed lets retain their original
checked input across repeated normalization.

- [ ] **Step 2: Run; expected failures**

`TypeError: unsupported WCC elaboration node: ProcedureCallExpr` for the
argument and `done` cases; `{"__wcc_current_loop__"}` for the `continue`
case; `WccPhaseTargetAtom` where a field access is expected.

- [ ] **Step 3: Implement the six rules**

Each rule under `if scope.closed_program`. Keep every existing branch byte
for byte on the other path.

- [ ] **Step 4: Run; expected pass**

The new module; then `tests/test_workflow_lisp_wcc_m4.py`,
`tests/test_workflow_lisp_wcc_m3.py`, `tests/test_workflow_lisp_wcc_m2.py`,
`tests/test_workflow_lisp_wcc_m1.py` (the ANF invariant tests),
`tests/test_workflow_lisp_improve_stdlib.py`,
`tests/test_workflow_lisp_guide_programs.py` (row 16 of the drafting guide
still meets `compiler_defect` at 2.33 and 2.34), plus
`tests/test_workflow_lisp_strict_boolean_control_flow.py` and
`tests/test_workflow_lisp_loop_recur.py` for the shared normalizer, plus
`tests/test_workflow_lisp_use_site_scope.py` for shared hygiene.

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical. `improve_experiment_proposal`
is the one with a `continue` under a join and a specialized callee: its step
ids must not move.

Because the loop-order fact touches a shared expression carrier, also run
the existing 67-artifact capsule comparison against the fixed Phase 2
baseline. Preserve truthful package pins in the real comparison and report
expected pin-only differences separately from the controlled fixed-identity
comparison; the latter does not establish raw equality of real packages.

- [ ] **Step 6: Commit**

Stage and commit only the changed paths listed above (including `wcc/anf.py`
only if a demonstrated normalization defect requires it), plus any fixtures
actually added under `tests/fixtures/workflow_lisp/closed_program`.

Commit message: `feat: elaborate effectful arguments, done values, continue targets and phase-target for the closed program`.

**What this makes harder later:** `path/join` is an operator the catalog does
not know; if Phase 3 wants to evaluate it through the catalog, the catalog
gains a node kind then. Two elaboration behaviours now live behind one flag;
Phase 7 removes the flag with the flat route. Until that retirement,
semantic expression rewrites must transport the retained condition input
in its incoming scope while ordinary legacy traversal stays one-view.

---

### Task 5: Sites And The Checked Form

**Files:**
- Create: `orchestrator/workflow_lisp/closed/sites.py`, `orchestrator/workflow_lisp/closed/check.py`, `orchestrator/workflow_lisp/closed/names.py` (pure key-to-name and run-reference descriptor/signature helpers; Task 6 adds typed construction)
- Modify: `orchestrator/workflow/type_descriptor.py` (source-independent compiled-boundary projection validation)
- Test: `tests/test_workflow_lisp_closed_program_sites.py`, `tests/test_workflow_lisp_closed_program_check.py`

**Read first:** `experiments/evaluated_execution_spike/sites.py` (`_Scope`,
`_SiteWalker`, `_Validator`) and `table.py` (`to_table`, `_local_sites`);
design §6 (I1 to I4), P4, P5, and the complete
[canonical key schema](#canonical-definition-keys) and
[binding-label schema](#binding-labels). These modules/helper
are pure functions over the shared schema; no compiler/frontend import.

**Interfaces:**
- Produces: `names.canonical_callee_name_from_key(key: list) -> str`, the
  sole [key-to-name operation](#name-derivation-and-source-independent-checks).
  Use `workflow.pure_expr.canonical_json_for_pure_value` encoded as UTF-8
  without a newline and `hashlib.sha256`; do not depend on future
  `closed/program.py`. `check.py` validates the key's exact shape, formal
  ordering, reference-binding bijection, resolved extern rows and capture/
  residual agreement before calling it. Hand-written fixtures use this
  actual helper, with no placeholder naming algorithm or deferred check.
- Produces: `names.key_type_descriptor`, `names.canonical_run_ref_signature`
  and `names.run_ref_type_dependencies` with the exact
  [shared signature contract](#run-reference-structural-signatures).
  `check.py` owns the derived origin inventory and complete S/key/runtime checks
  now; neither opaque S acceptance nor deferred Task 8 correspondence is valid.
- Produces: `sites.SEPARATOR = " / "`;
  `sites.assign_sites(tree: dict) -> list[tuple[str, str]]`: writes
  `site` (the local path) on every `perform` and `frame` (the local prefix
  plus `<binder>=<callee>`) on every `call` whose callee performs an effect,
  walking the entry body then each definition body on its own; returns the
  site table in program order, appending **only `perform`** rows. A `call`'s effectfulness is read from
  `tree["definitions"][callee]` (memoized with a visiting guard that reports
  `call_cycle` rather than recursing forever on malformed input). Use the
  shared effective binding label, including optional overrides; a lexical
  `%` prefix alone does not make a labelled binding anonymous.
- Produces: `check.CheckedFormError(ValueError)` with attributes `rule: str`
  and `location: str | None` (the `@.span` of the offending node when it has
  one); `check.validate(tree: dict) -> None` checking, over the entry and
  every definition: every `name` is bound (params, lets, join params, loop
  params, case binds, select prefixes, `list_map` binders); every `jump`
  names an enclosing `join`; every `continue` names the innermost enclosing
  `loop` (not a join's, not an outer loop's); every `perform` has a `site`
  unique within its definition; every `call` names a definition, and the
  call graph is acyclic (no recursive call, P5); every `loop` has a `budget`
  value; every `op` payload passes `validate_pure_expr_payload`; every
  `record` and `inject` has field names equal to its descriptor's; every
  `path_join` has a path descriptor with a root; the `k` of every node is
  one of the schema's. Walk every edge listed in design §6, including
  select prefixes/values, block body, separate join body/continuation and
  exhaustion. Independently enumerate all performs/calls rather than
  trusting the site walk: enforce a site-table bijection, exactly one frame
  per effectful call and no call row in `sites`.
- Validate the exact [binding-label schema](#binding-labels), including
  select prefix rows, before using its labels to recompute persisted
  sites/frames. Reject null, empty or non-string labels and labels on other
  node kinds. Require exactly one `join.params` entry, whether or not a
  label exists; reject other cardinalities as `join_arity` before indexing
  `params[0]`. Join labels belong to that result parameter, not the control
  target; jump argument arity/types remain independently checked. Lexical
  lookup always uses names, never labels. Key `ClosedValue` projections
  must omit label overrides as well as alpha-normalize lexical names.
- `validate` also infers/checks every value against the persisted `types`
  table and typed environments. Require exact nominal definitions, primitive
  literal kinds (Bool is not Int), list elements, field projections,
  record/variant field types, catalog argument/result types, strict Bool
  conditions, select arm agreement and block result types. Check entry and
  callee defaults/params/results, capture/call arity and argument/result
  types, join jump/result types, loop seed/state/budget/continue/done/
  exhaustion results, provider result-path origins and every perform's
  result against its command/provider contract or decoded run-ref result.
  Effects must also match their canonical configuration entry in the
  definition's resolved scope (`configuration.imports` or root), under the
  exact [command configuration correspondence](#writer-and-reader-obligations).
  Raw manifest type strings are semantic configuration, not source-free
  expected input descriptors; the reader does not re-run alias resolution or
  compare them to canonical nominal names. Reuse pure
  catalog descriptor validation/coercion and assignability semantics; do not
  invoke frontend typecheck or accept equality of two unvalidated copied
  labels as proof. Unknown/missing type facts and mismatches fail read-back
  with a stable rule (e.g. `type_mismatch`, `nominal_definition`,
  `call_signature`, `effect_result`, `entry_result`). This proves internal
  type/contract consistency, including definition-name/key agreement and
  capture/residual signature agreement, not artifact authenticity: Phase 3 separately
  compares the stored artifact's digest with its durable run header. Reject
  malformed/duplicate JSON keys and nonfinite numbers before typed checking,
  and reject duplicate definition/type/parameter identities rather than
  silently overwriting them.
- Check every [reference binding](#mandatory-prefboundtarget-agreement)
  against its converted target facts, including category/type/value and
  route-based capture-index remapping in nested reference scopes. Validate
  the exact [resolved extern rows](#exact-resolved-extern-rows-no-opaque-bindingrow)
  now, before Task 7 produces them. Derive capture prefix indexes and static
  context-call occurrences from the persisted key and closed bodies; check
  forwarding suffixes and terminal transfers rather than trusting route
  labels. The pure name helper gives same-named procedure/workflow keys
  distinct names without a program-wide collision inventory.
- Validate the shared `call.boundary` schema independently. Each argument is
  checked once against its aligned caller slot; `direct` pairs and projected
  roots partition both caller and native parameters exactly. Check capture
  prefix/key agreement, indices/order, structural paths, wire contracts and
  complete active-variant coverage from canonical descriptors, not copied
  contract labels. Use the existing neutral transport-descriptor owner and
  boundary-contract normalization semantics without importing the frontend.
  Path roots/existence, enums and primitive kinds stay exact; root collection
  schemas preserve their existing nominal facts. Independently derive legacy
  union structural paths and inactive-variant path relaxation. Reject forged
  activity, dropped/redirected rows and altered direct pairs as `call_boundary`.
  Apply the same checks to converted internal context-injection calls,
  including their capture schema, ordinary residual rows and both output
  views. Also implement the shared generated nominal view and structured
  applied-identity inventory, including phantom dependencies and staged S/view
  checking. Follow [generated boundary read-back](#generated-boundary-construction-and-read-back):
  complete protected D/footprint/branch guards precede wire equality; the reader
  checks the final relation, while the constructor owns generated-only whole-D.
  Ordinary unannotated calls retain strict nominal/positional matching.
  Resolve every definition configuration scope and verify its digest and
  effect bindings;
  missing or mismatched scopes fail `configuration_scope`.
- Run-reference read-back checks use Task 8's exact configuration/type digest
  recipe and fixed runtime record identities. The neutral decoder establishes
  the static config's internal consistency; this checker also establishes
  correspondence with the containing definition/site, node and `types` table,
  using the exact shared origin/dependency/signature algorithm above.
- Consumed by: Task 4 (`assign_sites` then `validate` at build), Task 6
  (the shared pure name/signature helpers), Task 7 (`validate` on artifact read-back).

- [ ] **Step 1: Write the failing tests on hand-written trees**

Write a helper `tree(entry_body, definitions={})` in the test module that
returns a minimal program dict (`params: []`, `defaults: {}`). Perform nodes
in these trees need only `{"k": "perform", "class": "command", "result": {...}, "repeat": "rerun", "boundary": "fetch", "command": ["python", "probe.py"], "closure": [], "contract": {...}, "argv": []}`.

```python
def test_three_arms_in_a_loop_give_three_frames_over_one_site() -> None:
    # loop(param "state") has a join with result param `got` and a three-arm case body.
    # Each arm binds `%1` to a call of "procedure:cp/arms_in_loop::fetch", then jumps
    # to the join with that value; its continuation is done(got). The callee performs one unnamed effect.
    table = assign_sites(t)
    assert table == [("procedure:cp/arms_in_loop::fetch", "#1")]
    assert [n["frame"] for n in calls(t)] == [f"loop:state[*] / got / body / {arm} / #1=procedure:cp/arms_in_loop::fetch" for arm in (...)]

def test_a_pure_binding_takes_no_ordinal_and_a_repeated_name_takes_a_counter() -> None:
    # lets: %1 = op, %2 = perform, x = perform, x = perform  ->  sites ["#1", "x", "x#2"]

def test_hygienic_names_keep_authored_labels_and_pure_names_take_no_counter() -> None:
    # x = lit, %1(label="x") = perform, %2(label="x") = perform -> ["x", "x#2"]
    # Renaming/inserting the pure binding leaves sites unchanged; refs use %1/%2.

def test_an_authored_percent_name_is_not_an_anonymous_ordinal() -> None:
    # %1(label="%1") = perform, %2 = perform -> ["%251", "#1"]
    # Include __authored and / = # [ ] punctuation; escape labels, not lexical names.

def test_a_join_whose_body_performs_an_effect_is_a_segment_and_a_pure_join_is_not() -> None:

def test_a_call_of_a_pure_definition_gets_no_frame_and_no_site() -> None:

def test_the_exhaustion_body_is_its_own_segment() -> None:   # "loop:state / exhausted / e"
```

Add hand-written valid trees with effects in each select arm prefix, a
nested block, join body and continuation with the same authored binder, and
loop exhaustion. Assert independent node/site bijection and call-frame
counts. Tamper an unvisited effect, insert a call into `sites`, remove a
frame, and use authored punctuation to test collision-free presentation.
Include label overrides in select prefixes, join result `params[0]`, and
loop state `param`; the generated control target must not enter those
segments. Tamper a label without updating its persisted site/frame and
require rejection. Reject empty/non-string/null labels and labels on
case/list-map nodes. Reject zero/two join parameters with `join_arity`,
separately from wrong jump arguments. A consistent label/site/digest edit is
another program, not evidence of source authenticity.

For `check.validate`, one test per rule, each tampering one node of a valid
tree and asserting `CheckedFormError.rule`: `unbound_name`, `jump_target`, `join_arity`,
`continue_target` (a `continue` naming an outer loop from an inner loop),
`site_missing`, `site_duplicate`, `callee_unknown`, `call_cycle`,
`budget_missing`, `payload_invalid`, `record_fields`, `node_kind` plus the
type rules above. Change non-operator descriptors independently: perform
result, entry result, list-map result item, nested record field, call result/
argument, loop state and private nominal name. Each must fail even after the
attacker recomputes the outer digest. Add valid typed trees covering all
value forms so the validator does not reject supported forms indiscriminately.

Add hand-written annotated-call trees for distinct nominal records, dynamic
paths and 1:N arguments (`Pair(x,y)` to native `a__x,a__y`), including a direct
capture, omitted default and X1/X2 context slots. Round-trip each through
Task 7 when available. Tamper both direct indices/partition and projection
roots; reject Boolean/out-of-range/duplicate indices, changed paths under the
same wire name, dropped rows, incorrect capture prefix, mismatched path
constraints, and an unannotated nominal mismatch. A union fixture must derive
activity and relaxed inactive paths from its nominal descriptor, then refuse
forged activity after the artifact digest is recomputed. These are read-back
proofs, not assertions on compiler-generated text. Include a caller-only
context capture forwarded through one and two wrappers, projected into a
native nominal context, with complete ordinary residual/output rows. Refuse
dropped capture slots, redirected recipient paths, altered capture types,
wrong direct pairs and missing residual/output coverage. Test missing/incorrect
configuration scope and effects matched against the wrong owner's binding.

Add valid nine-component keys and tamper their name/hash, formal ordering,
bound rows (missing/extra/duplicate/category/type/value), nested capture
indexes of the same type, and capture prefix count/order/types. Exercise
both callable kinds under one module/name, local capture selectors, every
exact provider/prompt row variant, and a repeated-same-callee context route
whose other occurrence has an explicit binding. Pure-binding insertion,
binder renaming and a call to another declaration leave its occurrence
unchanged. These key and row checks are complete in Task 5; only their
production source/descriptor construction waits for the later tasks.

Add valid one-level and nested run-reference fixtures using the unchanged
neutral codec and the shared S helpers. Reject wrong input order/type/reference,
missing/duplicate producers, finite-descriptor input-origin cycles, malformed
key S, generated-name leakage, conflicting fixed `types` records and changes
to the digest suffix after its first 16 characters. Test equal-S distinct
sites and refuse an expression/config nominal substitution between them.
Changing a nested producer's S must change the outer signature/key/site
correspondence. These tests prove complete Task 5 read-back; later producer
integration does not replace them. Cover scalar, List and phantom-applied
generated views, both endpoint rows, captures/residual/output coverage, strict
no-boundary rejection, changed nested/phantom S, ordinary template/argument
order differences, missing origins and phantom-only dependency cycles.
Capture/context combinations without demonstrated source admission use typed
fixtures here; do not report them as public source integration evidence.

- [ ] **Step 2: Run; expected failure** `ImportError`.

- [ ] **Step 3: Implement** `sites.py`, `check.py` and the pure helpers in
`names.py` over the shared schema, including both run-reference projections.
Use small node dispatchers as in the spike, with an independent validation
walk. The spike's small validator is not a full type checker; do not preserve
its omitted type checks to meet its historical line estimate.

- [ ] **Step 4: Run; expected pass.** Collect-only on both modules. Run the
existing descriptor and pure-expression tests that exercise the shared
`workflow/type_descriptor.py` owner, using narrow selectors first.

- [ ] **Step 5: Compatibility evidence:** the descriptor owner is shared.
Run the four-program comparison under Global Constraints and preserve its
existing nominal and transport validation behavior.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/sites.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow/type_descriptor.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_check.py`

`git commit -m "feat: effect sites and the checked form of the closed program" -- orchestrator/workflow_lisp/closed/sites.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow/type_descriptor.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_check.py`

**What this makes harder later:** `par-map` (Phase 5) adds an item segment
`[<index>]` (I2) to the walker and a node kind to the validator; both are
one case each.

---

### Task 6: Names That Hold No Path

**Files:**
- Modify: `orchestrator/workflow_lisp/closed/names.py` (Task 5 created the pure key-to-name and run-reference projection helpers; extend them with typed construction)
- Modify: `orchestrator/workflow_lisp/type_env.py` (`FrontendTypeEnvironment.from_module`, line 604: the map of nominal descriptor names; a sibling map and a method)
- Modify: `orchestrator/workflow_lisp/loop_state.py` (transient family fact on existing carrier metadata)
- Modify: `orchestrator/workflow_lisp/closed/frontend.py` (retained expanded-declaration association, including snapshots)
- Modify when required: `orchestrator/workflow_lisp/typecheck_structural_values.py` (propagate the originating list-map constructor family without changing legacy type/name/repr output)
- Test: `tests/test_workflow_lisp_closed_program_names.py`

**Read first:** the spike's `closed.py` lines 122 to 170 (`_Def.bind`,
`_type_id`) and 335 to 350 (`definition_id`); `procedures.py` lines 322 to
391 (`parametric_specialization_name` digests `repr(TypeRef)`;
`proc_ref_specialization_name`); `normalized_type_descriptor.py` lines 102
to 175 (`_nominal_descriptor_name`: exported types get `module::Name`, a
non-exported type its bare name, found through the span's file path);
execution facts A.5; design §4.2 and P6; the
[canonical key schema](#canonical-definition-keys). Merge Task 5 first.

**Interfaces:**
- Consumes: Task 5's `canonical_callee_name_from_key`, `key_type_descriptor`,
  `canonical_run_ref_signature` and `run_ref_type_dependencies`. Keep frontend
  imports under `TYPE_CHECKING` or inside typed constructors so the pure helpers have no
  frontend semantic dependency. Existing neutral import side effects are
  outside this claim. Do not import `closed.check` or `closed.program` into
  `names.py`. Derive origin scopes from retained typed producer metadata,
  using the shared signature contract; do not duplicate its projection.
- Produces: `FrontendTypeEnvironment.declaring_module(type_ref: TypeRef) -> str | None`:
  the `defmodule` name of the module that declares the nominal type behind
  `type_ref` (`RecordDef`, `UnionDef`, `EnumDef`, `PathDef`, `SchemaDef`),
  exported or not. Implemented as a second map in `from_module`, keyed like
  `_nominal_descriptor_names_by_definition_id` (by `id(definition)`), for
  every definition kind. No dataclass of `definitions.py` gains a field:
  `repr(TypeRef)` includes the definition's repr and is digested into
  specialization names at every existing target.
- Produces, in `closed/names.py`:
  - `canonical_type_identity(type_ref: TypeRef, *, typed: TypedProgram) -> str`:
    a primitive by its name; a nominal type by `<declaring module>::<Name>`,
    the module found through `declaring_module` on the entry environment,
    then each `typed.module_type_envs` value, then the procedure and workflow
    environments; a `DiscriminantTypeRef` as `<union identity>.variant`;
    `ListTypeRef`/`OptionalTypeRef` as `List[<item>]`/`Optional[<item>]`; an
    applied union as `<template identity>[<arg identity> ...]` (one ASCII
    space between arguments), and Map as `Map[<key>,<value>]`. Use the exact
    shared identity grammar/renderer, retaining phantom type arguments. It never
    reads a span, a path or `repr`. A type whose module cannot be found
    raises `CanonicalNameError(type name)`; the builder reports it as a
    located compiler defect and repairs the declaring-module facts. Builtin
    and standalone types use their stable logical namespaces. Failure to
    name an admitted type is not a release exclusion.
  - Generated loop-state records use the shared [F/Q/H/I rule](#generated-loop-state-carrier-identities). Retain the family before specialization/normalization, preserve it across imports and synthetic list-map expansion, and resolve the concrete variant from its actual typed field facts. Keep the public identity signature and environment search unchanged. Expression-only last-variant lookup and legacy generated names are not authority.
  - `canonical_type_descriptor(type_ref, *, typed) -> dict`: reuse the
    normalized descriptor shape and recursively replace all nominal names
    from the declaring-module index, including nested fields, variants,
    applied arguments, list/optional members and private imported types.
    Register/check each nominal definition in the program `types` table,
    including nominal applied arguments with no corresponding payload field.
    Preserve refinements/path roots. Do not change the old descriptor route.
  - `canonical_definition_key(definition, *, typed, binding_facts,
    capture_parameters, residual_signature) -> list`: construct the complete
    [shared nine-component tuple](#canonical-definition-keys). Task 4 supplies
    checked closed value expressions and explicit capture parameters before
    calling this function. Procedure-reference
    facts include recursive target keys, residual signatures and every bound
    argument's formal/type/closed binding; workflow-reference facts include
    canonical workflow keys and the exact resolved provider/prompt rows.
    Derive `PRef.target`, its bound rows and residual signature from one
    resolved binding plus merged specialization facts; enforce the shared
    category/type/value/capture-route bijection and ordered residual partition.
    Alpha-normalize bound value expressions, retaining tagged primitive kinds. Runtime capture
    facts identify owning formal/argument routes and types, not caller names
    or runtime values. Caller-only private context captures use this same schema:
    declaration-only recipient/formal routes, per-callee static call
    occurrences, typed field paths and the caller's canonical captured type,
    excluding import aliases, generated wire prefixes, paths and spans. Two
    values of that type/routes share a body; distinct nominal capture types
    may require distinct converted keys. Generated-only nominal differences
    use the shared structured S projection and may share a key; retain the
    first semantic candidate as native representative and preserve later
    caller views through the shared checked boundary. Before an ordinary
    generated-only annotation, prove whole-ordered-signature D equality as
    specified by the [constructor rule](#generated-boundary-construction-and-read-back);
    reader acceptance of another valid composition does not replace it.
    Memoize by the complete
    converted key; context conversion uses the existing specialized-name rule.
    Sort formal selectors as the shared schema specifies; preserve ordered
    fields. The historical `typed.local_definition_keys` six-tuple supplies
    owner/name/ordinal metadata, not the wire key: resolve types from typed
    facts and local captures by index, never copy `(name, type_name)` rows.
  - `canonical_callee_name(definition, *, key) -> str`: delegate to Task 5's
    pure `canonical_callee_name_from_key`. Bases are unconditionally
    `procedure:module::name` or `workflow:module::name`; the shared rule
    appends the key hash for local/specialized/capture-converted definitions.
    Store `key` beside the body and refuse equal names with unequal keys as
    a compiler defect. A local definition
    uses `typed.local_definition_keys` and existing generated-local metadata,
    never `definition.name`'s span hash. No value/workflow/ref/capture form
    is turned into a release gap.
  - Generated run-reference types use their canonical input/result structural
    signature in definition keys; after site assignment, Task 8 hashes the
    containing canonical definition, local site and that signature together
    into `site_digest`, and the existing neutral name rule derives the final
    nominal name from its first 16 hexadecimal characters. This is a two-pass
    finalization in Task 8, not a self-referential hash. Test distinct producer
    contexts sharing S (and any shared provisional spelling), keeping their
    concrete origin links through calls/substitutions; no inversion of S or
    global old-name rewrite may select an origin.
  - `Renamer(reserved_names=...)`: reserve all authored lexical names and
    parameters in the definition before allocating the first `%<n>`.
    `bind(name, *, authored_label: str | None, env: MutableMapping[str, str]) -> str`
    preserves an unchanged authored name; a generated name or a hygienically
    renamed authored name gets the next available `%<n>` in binding order,
    counting from 1 per definition and skipping reserved names. Record the
    lexical result in `env[name]`; the authored label remains a separate
    fact for the builder's [wire projection](#binding-labels).
    `ref(name, *, env: Mapping[str, str]) -> str` resolves that lexical map.
    The builder copies the map at binding/scope edges: an initializer uses
    the parent environment, and the introduced binder scopes only over its
    continuation/body. Sibling arms restore the parent environment. The
    allocator is per definition; the reference map is not a global
    last-writer table. Every binder supplies explicit origin, including
    case/list-map binders; no prefix, suffix, span or scope hash decides it.
- Consumed by: Task 4.

- [ ] **Step 1: Write the failing tests**

Through `compile_typed_program` on `if_in_hook.orc` (it specializes
`std/improve::improve` with types of the entry module and two proc refs):

```python
def test_a_specialized_callee_is_named_by_its_base_and_canonical_arguments(tmp_path) -> None:
    typed = compile(tmp_path, fixture("if_in_hook"))
    (spec,) = [p for p in typed.procedures.values() if p.specialization is not None and p.specialization.base_name == "std/improve::improve"]
    key = canonical_definition_key(spec, typed=typed, **closed_binding_facts(spec))
    assert canonical_callee_name(spec, key=key) == "procedure:std/improve::improve[" + sha256(canonical_json(key)).hexdigest() + "]"
    # Inspect the tuple too: all four type bindings and both reference targets are retained.

def test_private_type_identities_and_descriptors_are_recursively_qualified(tmp_path) -> None:
    # Two imported modules each declare private Note, nested in exported records/unions/lists.
    # Their identities and descriptors differ by declared module, including entry/effect result fields.


def test_no_identity_holds_a_path_a_position_or_a_type_repr(tmp_path) -> None:
    for name in every_canonical_name(typed):
        assert str(tmp_path) not in name and "TypeRef" not in name and re.search(r"\.orc:\d+", name) is None

def test_moving_the_program_keeps_every_canonical_name(tmp_path) -> None:
    assert names(tmp_path / "here") == names(tmp_path / "elsewhere" / "deeper")

def test_binding_origin_and_scope_control_lexical_names() -> None:
    r = Renamer(reserved_names={"x", "%1", "__authored"})
    outer = {}
    assert r.bind("x", authored_label="x", env=outer) == "x"
    inner = dict(outer)
    assert r.bind("x_hygiene_digest", authored_label="x", env=inner) == "%2"
    assert r.ref("x_hygiene_digest", env=inner) == "%2"
    assert r.ref("x", env=outer) == "x"
    assert r.bind("__authored", authored_label="__authored", env=outer) == "__authored"
    assert r.bind("temporary", authored_label=None, env=inner) == "%3"
```

Add key tests for same base/types with different value substitutions,
workflow references, extern rebindings and bound proc-ref arguments: distinct
keys/names. Two runtime captures of one converted body share a key and have
different call values. Add let-proc same-name nested/sibling scope cases;
blank lines, relocation, pure-binding insertion/renaming change no local key.
Use existing bound-reference forwarding and let-proc fixtures; Task 4 adds
public-builder checks once conversion exists. No placeholder capture helper
is a production dependency of this task: key unit cases use explicit plain
binding facts; public integration follows in Task 4.
Test shadowed initializer lookup, restored sibling scopes, sequential select
prefixes, and reserved names encountered later in a definition. Give case,
list-map, loop and generated control binders explicit origin facts; use the
same Renamer, without a frontend service in these unit cases. In key-value
tests, changing local authored names and their label overrides leaves the
alpha-normalized key unchanged. Task 4 verifies parser-to-WCC carriage and
public builds.
Include one source-admitted same-name procedure/workflow pair, both reached
by the entry, and require distinct kind-qualified names. Exercise local
compile-time and runtime capture selectors, nested bound-reference index
scopes and each fixed resolved extern row. Different runtime capture values
reuse keys; changes in caller nominal descriptors or recipient routes do not.

Add carrier identity checks for distinct nested shapes and independent same-shaped seeds, ordered fields/refinements, relocation and pure binding edits, imported aliases/local callables, synthetic list-map and specialization lineage. Generated field dependencies include phantom arguments; preserve each concrete producer even when S agrees. Tasks 4/8 add full public build/read-back and finalization checks.

- [ ] **Step 2: Run; expected failures** `ImportError`; then missing binding
facts or bare private nominal names until implemented.

- [ ] **Step 3: Implement.** `declaring_module` first (a map beside the existing one), then recursive
descriptors and complete key constructors in `names.py`, preserving the
single pure key-to-name helper. Do not reuse
`repr`, generated local names or raw typechecker run-ref result names.

- [ ] **Step 4: Run; expected pass.**

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical. `improve_experiment_proposal`
(2.33) and `review_revise_design_docs_judgment_panel` (2.23) are the ones
whose step ids and binding schema digests hold `repr(TypeRef)`: if
`type_env.py` changed a repr, they would differ.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/type_env.py tests/test_workflow_lisp_closed_program_names.py`

`git commit -m "feat: canonical callee and type identities for the closed program" -- orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/type_env.py tests/test_workflow_lisp_closed_program_names.py`

**What this makes harder later:** two naming schemes coexist (digested
`%parametric-call.*` names for steps, canonical names for the closed
program) until Phase 7.

---

### Task 7: The Program Artifact, Its Digest, And The Manifest Field `closure`

**Files:**
- Create: `orchestrator/workflow_lisp/closed/program.py`
- Modify: `orchestrator/workflow_lisp/command_boundaries.py` (`ExternalToolBinding` line 80, `CertifiedAdapterBinding` line 129), `orchestrator/workflow_lisp/build_manifest_io.py` (`_parse_command_boundaries_manifest`, both `kind` branches; `_require_optional_string_array` exists)
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py` (checked-in builtin declarations), `orchestrator/workflow_lisp/compiler.py` (existing injection factories and `_augment_builtin_command_boundaries` origin carriage), `orchestrator/workflow_lisp/closed/frontend.py` (retain effective origins/configuration)
- Test: `tests/test_workflow_lisp_closed_program_artifact.py`, `tests/test_workflow_lisp_command_boundary_closure.py`

**Read first:** the spike's `sites.py` lines 35 to 78 (`ClosedProgram`,
`canonical_digest`, `strip_provenance`, `from_artifact`); design P6, P7,
§8.4 (the representation is part of the identity), C1, §13 (the field is
accepted and ignored at older targets); `build_manifest_io._json_data`
(line 921: honours `json_omit_if_none`); `compiler._command_boundary_fingerprint_payload`
(line 2380: explicit fields, so a new field does not enter the fingerprint
unless added there; do not add it).

**Interfaces:**
- Produces, in `closed/program.py`:
  - `SCHEMA = "workflow-lisp/closed-program/1"`, `REPRESENTATION = "table/1"`.
  - `@dataclass(frozen=True) class ClosedProgram: tree: dict; sites: tuple[tuple[str, str], ...]; digest: str`
    with `artifact() -> str` (canonical JSON of `tree`: `sort_keys=True`,
    `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, one
    trailing newline; provenance included) and
    `@classmethod from_artifact(text: str) -> ClosedProgram` (parses, checks
    `schema` and `representation`, runs `check.validate`, rebuilds `sites`
    from the nodes' `site` keys and compares with `tree["sites"]`, computes
    the digest). A mismatch or a validation failure raises
    `ClosedProgramInvalid(code="closed_program_invalid", rule, location)`.
  - `canonical_digest(value) -> str` (`"sha256:" + hex` over the same
    canonical JSON) and `strip_provenance(node)`.
  - `program_digest(tree) -> str` = `canonical_digest(strip_provenance(tree))`
    (P7: `sites` are in the tree and enter the digest; `@` does not).
- Produces: `ExternalToolBinding.closure: tuple[str, ...] | None = field(default=None, repr=False, metadata={"json_omit_if_none": True})`,
  the same on `CertifiedAdapterBinding`. Both parser branches preserve
  absence (`None`) versus `[]` (`()`); explicit `null` is invalid, not absence.
  Validate each path as a nonempty literal string without NUL; no globs,
  environment expansion or exclusions. Use the existing array validator only
  where its null/empty rules match, otherwise add the direct presence check.
  Add `canonical_command_configuration(bindings, *, origins)` in `program.py`: project
  the exact [canonical command rows](#canonical-command-configuration),
  including all adapter metadata, raw input/output type declarations,
  stable argv, repeat rule and closure. Do not resolve unused bindings or
  omitted optional inputs during serialization; resolved result/contract
  facts remain on each perform. Normalize
  closure separators and `.` components, retaining `..`, sort/deduplicate;
  relative paths use the command workspace, absolute declarations stay
  absolute. Do not use `posixpath.normpath` (it collapses `..` across symlinks).
  A simple component filter suffices; retain root `.` for an empty relative
  component sequence. No filesystem reads during compile. Emit sorted
  `{base, path}` rows: ordinary relative paths use `workspace`; absolute
  declarations use `absolute`; trusted injected relative paths use
  `package:orchestrator`. Apply the grammar to in-memory bindings too.
- Compiler-owned declarations are required, never exempt. Add the explicit
  checked-in `closure=(".",)` to `validate_review_findings_v1` beside its
  binding in `stdlib_contracts.py`; inventory other admitted injected command
  bindings in the existing compiler factories and give each an authoritative
  declaration there. The initial package-root declaration binds transitive
  compiler/contracts/I/O imports as well as the adapter; no import-discovery
  system or unknown empty declaration is introduced. Its accepted cost is
  divergence for unrelated package-file changes until a smaller closure is
  audited. Later excluded effect classes remain excluded as classes, but a
  reachable admitted command may not lack C1.
- Preserve trusted origin in `CommandBoundaryEnvironment` alongside
  `bindings_by_name` (a small origin map, default workspace for supplied
  bindings). Existing injection functions set package origin only for the
  binding instances they actually inject; preserve the map while rebuilding
  environments and carry it into `TypedProgram`. Never infer builtin origin
  from a matching name: a retained manifest override remains workspace-based.
  `configuration.commands` includes all supplied entries and every injected
  binding used by the closed program. No user field selects package origin,
  and no absolute installation prefix enters program identity.
- Use the same semantic configuration projection for root and retained
  producer snapshots. `configuration.imports[canonical_digest(producer_config)]`
  stores each producer's normalized `{commands, providers, prompts}`, including
  unused supplied entries and used injected bindings. Nested owners contribute
  separate rows; equal configurations deduplicate. Imported definitions select
  their row by `configuration`, while an absent selector means root. Neither
  source digests, provenance/install prefixes nor old bundle fingerprints
  enter these rows. Artifact validation checks scope digests/references and
  effects under their owning scope. All rows and `call.boundary` participate
  in semantic identity and read-back; no special unvalidated side file.
- Emit the exact [resolved extern rows](#exact-resolved-extern-rows-no-opaque-bindingrow)
  already checked by Task 5: providers use `{provider_id}`; prompts use
  `{source_kind, path, asset_base}` for `asset_file`, or `{source_kind, path}`
  for `input_file`. Reuse `ProviderExtern`, `PromptExtern` and the existing
  normalization owners; retain the producer's logical asset base and exact
  bound path. No alias/provenance wrapper, policy/template payload or new
  binding hash is introduced. The same rows serve `WRef.externs` and the
  selected root/imported configuration; Task 8 consumes them.
- Keep `closure` out of binding dataclass repr with `repr=False`; old
  identity owners can digest these objects. Keep `closure` out of
  old-target binding serialization/fingerprints even
  when explicitly supplied: inspect `_json_data` and every boundary payload
  producer, and omit it in the old route's projection, not globally in the
  model. The existing raw-manifest-byte cache hashing algorithm remains
  untouched. `json_omit_if_none` alone does not handle explicit closure.
- Runtime-only closure work belongs to Phase 3: workspace/symlink resolution,
  sorted file/directory content evidence (including dotfiles/caches),
  missing/unreadable/cyclic-path refusal and disjoint input/result/cache
  destinations. Phase 2 persists declarations sufficient for those rules;
  it neither hashes unavailable workspace contents nor adds exclusions.
  Phase 3 resolves `package:orchestrator` through the existing loaded-package/
  PYTHONPATH seam, binds package-relative evidence (external symlink targets
  remain absolute), and checks dispatch origin against that declared tree
  to prevent workspace/PYTHONPATH shadowing. Caches in evaluator and children
  must be disabled or outside the declared package; none are ignored.
- The refusal C1 itself (`command_boundary_closure_missing`) is Task 4's
  (`require_command_closures`), because it is a rule of the new target and
  Task 4 owns the command node; this task only carries the field.
- Consumed by: Task 4 (`ClosedProgram`, `program_digest`, `binding.closure`),
  Task 9 (`artifact()`, `from_artifact`).

- [ ] **Step 1: Write the failing tests**

On hand-written trees (reuse the tree helper of Task 5's test module by
importing it):

```python
def test_the_digest_leaves_provenance_out_and_the_artifact_keeps_it() -> None:
    a = tree_with_provenance("/here/x.orc"); b = tree_with_provenance("/elsewhere/deeper/x.orc")
    assert program_digest(a) == program_digest(b)
    assert ClosedProgram(a, sites, program_digest(a)).artifact() != ClosedProgram(b, sites, program_digest(b)).artifact()
    assert "/here/x.orc" in ClosedProgram(a, ...).artifact()

def test_the_artifact_reads_back_to_the_same_tree_sites_and_digest() -> None:

def test_a_tampered_operator_payload_is_refused_when_the_artifact_is_read() -> None:
    tree = json.loads(program.artifact())
    selected_op(tree)["payload"]["result_type"] = STRING_DESCRIPTOR
    text = json.dumps(tree)
    with pytest.raises(ClosedProgramInvalid) as e: ClosedProgram.from_artifact(text)
    assert (e.value.code, e.value.rule) == ("closed_program_invalid", "payload_invalid")

def test_another_representation_or_schema_is_refused_when_read() -> None:   # rule "representation"

def test_a_site_table_that_disagrees_with_the_nodes_is_refused() -> None:   # rule "sites"

def test_readback_refuses_non_operator_type_tampering() -> None:
    # Parameterize explicit JSON paths for perform.result, entry.result, list_map.type,
    # nested record field and call result/argument; recompute digest before readback.
    # Assert the corresponding checked-form rule, not just digest inequality.
```

`tests/test_workflow_lisp_command_boundary_closure.py`:

```python
def test_closure_is_parsed_into_the_binding_and_absent_is_none(tmp_path) -> None:
    payload = {"a": {"kind": "external_tool", "stable_command": ["python", "a.py"], "closure": ["lib/", "b.py"]},
               "b": {"kind": "external_tool", "stable_command": ["python", "b.py"]},
               "c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": []}}
    bindings = _parse_command_boundaries_manifest(payload, manifest_path=tmp_path / "commands.json")
    assert [bindings[n].closure for n in "abc"] == [("lib/", "b.py"), None, ()]

@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
def test_closure_grammar_and_canonicalization_for_both_kinds(kind) -> None:
    # Reject null, scalar, non-string, empty path and NUL; absence differs from [].
    # a//./b and a/b deduplicate; a/../b is retained; absolute and overlapping entries survive.
    # In-memory bindings obey the same rules; nonexistent paths need no compile-time reads.

def test_injected_adapters_keep_package_closure_and_manifest_overrides_keep_workspace_origin(tmp_path) -> None:
    # Use compile_typed_program (Task 2) plus canonical configuration projection here.
    # Task 4 adds full build/read-back for a std/phase path using validate_review_findings_v1:
    # closure == [{"base": "package:orchestrator", "path": "."}], no installed absolute prefix.
    # Grammar/origin tests run here; Task 4 adds removal of the authoritative declaration
    # and its located command_boundary_closure_missing refusal after injection.
    # A retained manifest override with the same name has workspace rows, not package rows.
    # Task 9 proves package relocation preserves the full artifact digest; declaration edits change it.

def test_at_2_34_a_manifest_with_closure_builds_the_artifacts_of_one_without(tmp_path) -> None:
    # the PROGRAM of test_workflow_lisp_target_234 at 2.34, built twice with the two manifests through `_build`;
    # Compare all semantic/binding artifacts byte-for-byte; only map the changed build key
    # and declared raw-manifest fingerprint/provenance fields. Assert closure is absent
    # even when supplied. Never broadly scrub a new semantic difference.
```

- [ ] **Step 2: Run; expected failures** `ImportError`; `AttributeError: closure`.

Add artifact round-trips of the Task 5 boundary fixtures and two producer
scopes with same-named, unequal command/provider/prompt bindings. Changing an
unused producer binding changes program identity; scope/key changes that
mismatch the selected effect fail checked read-back. Equal configurations
share one row, and relocation/provenance changes add no incidental paths.
These checks exercise the semantic projection, not raw bundle fingerprints.
Round-trip both prompt source variants and resolved provider ids, asserting
the same rows in workflow-reference keys and their selected configuration.
Reject mixed/extra/missing keys and an asset base on `input_file`; preserve
the producing owner's logical base for `asset_file` after relocation.

- [ ] **Step 3: Implement** the artifact, canonical configuration and
closure carriage/old-route omission in their existing owners.

- [ ] **Step 4: Run; expected pass.** Then `tests/test_workflow_lisp_build_manifest_io.py`
if it exists (find the manifest parser's owner tests with `rg -l _parse_command_boundaries_manifest tests`),
and `tests/test_workflow_lisp_target_234.py`.

- [ ] **Step 5: Compatibility evidence**

The four programs of the table, whose manifests lack the field:
byte-identical (old-target payload producers omit closure/origin even for
injected declarations; `json_omit_if_none` is sufficient only for absent
manifest declarations, and fingerprint payloads retain their old field set).

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/program.py orchestrator/workflow_lisp/command_boundaries.py orchestrator/workflow_lisp/build_manifest_io.py orchestrator/workflow_lisp/stdlib_contracts.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/closed/frontend.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_command_boundary_closure.py`

`git commit -m "feat: the closed program artifact with its digest, and the command boundary closure field" -- orchestrator/workflow_lisp/closed/program.py orchestrator/workflow_lisp/command_boundaries.py orchestrator/workflow_lisp/build_manifest_io.py orchestrator/workflow_lisp/stdlib_contracts.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/closed/frontend.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_command_boundary_closure.py`

**What this makes harder later:** a second representation (Phase 5 or later)
must keep `from_artifact` refusing the other one, and the run header must
carry `representation` (§8.4): Phase 3 reads it from the artifact.

---

### Task 4: The Builder: Bodies, Values, The Table, X1 To X4, Command Nodes

**Completed 2026-10-01:** implementation `c0b34b66`, corrected by `59e2a81b`
and `0760be2b`; formal and quality re-reviews passed on the final commit.
Fresh verification: 35 owned tests, 268 closed consumers, 70 selected legacy
checks and 229 WCC/elaboration checks; 23 independent public probe groups
include 20 computed/reference capture cases. All 88 legacy CLI artifact/build-key
pairs and all 67 capsule pairs with a fixed identity input are byte-identical.
With the real package pins, 55 capsule pairs match and 12 run-reference
artifacts change only in the compiler pin and derived identities, inspected
through JSON, state layouts and loaded pickle graphs. Provider/run-reference
effect translation remains Task 8; this completion does not claim runtime
execution or resume support.


Consume the retained [loop-carrier families](#generated-loop-state-carrier-identities) and actual producer links. Register every concrete carrier and field nominal, including phantom applied arguments; existing first-native-representative and checked generated-view rules apply recursively.

**Files:**
- Create: `orchestrator/workflow_lisp/closed/build.py` (bodies, bound values, calls, the table), `orchestrator/workflow_lisp/closed/values.py` (values, operators, surface objects), `orchestrator/workflow_lisp/closed/context.py` (X1, X2, X4), `orchestrator/workflow_lisp/closed/effects.py` (`require_command_closures`, `translate_perform` for `command_result`; every other kind raises `ClosedProgramGap` naming its form until Task 8 translates providers and run references)
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py` (`typecheck_provider_bundle_path_expr`, line 1188: one gated condition, X4)
- Modify: `orchestrator/workflow_lisp/expressions.py` (transient binding-origin fields and parser capture), `orchestrator/workflow_lisp/typecheck_dispatch.py`, `orchestrator/workflow_lisp/conditionals.py`, `orchestrator/workflow_lisp/functions.py` (preserve origin through reconstructed bindings/arms and cloning), `orchestrator/workflow_lisp/typecheck_structural_values.py` (authored list item versus synthetic loop binders), `orchestrator/workflow_lisp/workflows.py` (`WorkflowParam.binding_label` from the declaration identifier), `orchestrator/workflow_lisp/procedures.py` (`ProcedureParam.binding_label` from defproc declaration identifiers), `orchestrator/workflow_lisp/procedure_specialization.py` (preserve the parameter origin while projecting residual parameters), `orchestrator/workflow_lisp/procedure_refs.py` (retain the source binding identity for closed local capture routing), `orchestrator/workflow_lisp/procedure_typecheck.py` (generated capture parameters remain anonymous; `_semantic_identity` omits transient fields), `orchestrator/workflow_lisp/typecheck_context.py` (retain the actual entry binding environment transiently), `orchestrator/workflow_lisp/typecheck_loop_recur.py` and `typecheck_proofs.py` (retain exact loop and arm binder identities), `orchestrator/workflow_lisp/expression_traversal.py` (preserve checked TypeRefs when rebuilding expressions), and `orchestrator/workflow_lisp/closed/names.py` (canonical discriminant descriptor).
- Modify after Task 3: `orchestrator/workflow_lisp/wcc/model.py` (binding origin on existing metadata/case arms and the transient originating `BindProcExpr` on existing specialization-capture rows), `orchestrator/workflow_lisp/wcc/elaborate.py` (origin carriage for captures, including inherited bound values), `orchestrator/workflow_lisp/wcc/anf.py` (preserve case-arm origin; generated lets remain anonymous), and `orchestrator/workflow_lisp/wcc/hygiene.py` (keep the transient source handle opaque while renaming WCC values). Reuse Task 3's `build_manifest_io.py` transient omission support; do not change its normalization contract or hygiene spelling algorithm.
- Modify shared Task 5 checker: `orchestrator/workflow_lisp/closed/check.py` validates local capture routes using exact non-Boolean indices and projects result-contract provenance only from schema-owned field rows.
- Create: `tests/workflow_lisp_closed_program_helpers.py` (shared by Tasks 4, 8, 9, 10: `install`, `fixture`, `build`, `with_blank_lines`, `BOUNDARIES` with `closure=("probe.py",)` on every binding, `PROVIDERS`, `PROMPTS`, modelled on the spike's test helpers, importing none of the spike)
- Test: `tests/test_workflow_lisp_closed_program_build.py`, `tests/test_workflow_lisp_closed_program_context.py`, `tests/test_workflow_lisp_closed_program_check.py`

**Read first:** the spike's `closed.py` in full (its docstring says what it
supplied for each property), `table.py`; design §4.1 to §4.4, §9.2 (a call
is evaluation); `defunctionalize._lower_wcc_procedure_call` (line 6656:
how the flat route elaborates a callee body, with `_procedure_signature_local_type_bindings`
as the value env and `procedure_type_env_for`); `context_classification._is_run_context_shape`;
`WorkflowSignature.hidden_context_requirements` and
`PromotedEntryHiddenContextRequirement` (`phase.py` line 83: `param_name`,
`context_kind`, `phase_name`); `lowering/workflow_calls._runtime_context_default_value`
(line 181: the present route's constants `state/run`, `artifacts/run`,
`state/<phase>`, `artifacts/<phase>`); `typecheck_effects.typecheck_provider_bundle_path_expr`
(line 1188); `SyntaxIdentifier`'s origin fields and the
[binding-origin carriage below](#binding-origin-retention-and-conversion).

**Interfaces:**
- Consumes: `TypedProgram` (Task 2); `elaborate_typed_workflow_body(..., closed_program=True)`
  (Task 3); `sites.assign_sites`, `check.validate` (Task 5);
  `names.canonical_callee_name`, `canonical_type_identity`, `Renamer`
  and `canonical_type_descriptor`, `canonical_definition_key` (Task 6); `program.ClosedProgram`, `program_digest`, `SCHEMA`,
  `REPRESENTATION`, the bindings' `closure` field (Task 7).
- Produces: `build.build_closed_program(typed: TypedProgram) -> ClosedProgram`.
  Steps inside: `require_command_closures` for the root and every retained
  producer's command bindings (C1, before elaboration), build the owner index
  with Task 2's snapshot-conflict check, then the entry definition using its
  `source_program`, type environment, externs and renamer. Bind hidden context
  parameters of the entry as leading `let`s (X1), translate the body, attach
  each callee once by canonical name into `definitions` (memoized; a callee
  reached twice with contradictory internal bodies after input admission is
  a defect: raise `ValueError`, reported as `compiler_defect`; incompatible
  supplied snapshots were already refused as `compiled_workflow_snapshot_conflict`).
  Add canonical `types` and complete
  `configuration`, then `assign_sites`, `validate`, and `program_digest`.
  Task 8 later inserts generated run-ref finalization between site assignment
  and validation when it adds run-ref translation. The whole build runs under
  `compiler_defect_boundary(entry path)` so that an internal error is a
  `compiler_defect` located at the innermost node
  (`records_defect_provenance("closed-program")` on the body and value
  dispatchers).
- Produces, in `closed/effects.py`:
  - `require_command_closures(bindings: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding], *, manifest_path: Path | None) -> None`:
    raises `LispFrontendCompileError` with one diagnostic per boundary whose
    `closure is None`, `code="command_boundary_closure_missing"`, at the
    manifest path (`_cli_request_diagnostic`) when given, else at
    `command_boundaries._environment_span()`, message naming the boundary,
    `notes=(f"boundary={name}",)`. Check all supplied entries and used
    compiler-injected command boundaries; preserve the originating manifest
    or command-form location. Validate builtin declarations after injection
    and again before translating any generated admitted command. A builtin
    name is not an exemption. Require Task 7's origin-aware canonical rows;
    never substitute `[]` when declaration data is missing.
  - `translate_perform(builder: Builder, perform: WccPerform, d: Definition, env) -> dict`,
    for `perform_kind == "command_result"`: `boundary` = `payload["adapter_name"] or perform.target_name`;
    `command` = the binding's `stable_command`; `closure` = its canonical
    normalized declaration from the owning definition's configuration scope;
    `contract` = `derive_prompt_guided_structured_result_contract(result type, workflow_name=d.canonical, step_id="effect", type_env=d.type_env, guidance=return_spec.guidance)`
    as `{kind, payload without "path" or source_map_subject}`; move the
    latter diagnostic subject under `@` rather than into program identity; `repeat` = `"never"` when
    `binding.must_not_repeat` else `"rerun"`; `argv` = the values after the
    stable tokens, or for a certified adapter `document` = `[[field.transport_key, value]]`
    in `input_signature` order over the declared inputs. Preserve currently
    admitted invocation protocols; malformed protocols keep their boundary
    validation diagnostic, and a missing admitted translation is a defect,
    not a new release exclusion. Every
    other `perform_kind`, and the binding values `WccProviderSupervision`
    and `WccProviderPeerGroup`, raise `ClosedProgramGap` with the surface
    form's name (`provider-result`, `run-ref`, `request-input`, `trial`,
    `run-provider-phase`, `produce-one-of`, `resume-or-start`,
    `finalize-selected-item`, `resource-transition`, `materialize-view`,
    `with-live-providers`, `with-live-provider-peers`); Task 8 replaces the
    first two with translations.
- Produces: `build.ClosedProgramGap(Exception)` with `form: str`, `message`,
  `span`, `form_path`; `build.gap_diagnostic(gap) -> LispFrontendDiagnostic`
  with `code="closed_program_gap"`, `message=f"`{form}` has no closed form in this release: {message}"`,
  `notes=(f"form={form}",)`, `phase="lowering"`, at the node's span.
  `build_closed_program` converts a gap into `LispFrontendCompileError` before
  the defect boundary sees it. Every refusal names the form in `notes`, so a
  test asserts `notes`, not the message.
- Produces the translation context Task 8 uses:

```python
@dataclass
class Definition:
    canonical: str            # the canonical callee name, or the entry's name
    owner: str                # the elaborator's owner name (definition.name)
    source_program: TypedProgram  # body/environment/configuration/asset owner
    type_env: FrontendTypeEnvironment
    externs: Mapping[str, ProviderExtern | PromptExtern]  # declaring module plus resolved specialization rebinding
    renamer: Renamer          # one lexical-name allocator per definition
    names: dict[str, str]     # scoped source/WCC spelling -> closed spelling
    loops: list[str]          # innermost last

class Builder:
    typed: TypedProgram
    def value(self, value: WccValue, d: Definition, env: Mapping[str, TypeRef]) -> dict: ...
    def desc(self, type_ref: TypeRef, d: Definition) -> dict: ...     # Task 6 recursive canonical descriptor; register nominal facts
    def body(self, node: WccBody, d: Definition, env) -> dict: ...
    def binding(self, value: WccBindingValue, d: Definition, env) -> dict: ...   # perform -> effects.translate_perform(self, ...), call -> self.call, workflow_call -> self.workflow_call
```

- Build the definition-owner index by visiting `typed.imported_programs`
  recursively and local graph definitions. `Builder.typed` remains the root;
  body/type/extern/command/prompt/asset lookups use `d.source_program`. Preserve
  native callee signatures and the declaring module's separate caller-view
  signatures. Resolve an explicit alias through that owner's selected import
  entry before emitting its canonical callee. Register Task 7's canonical
  configuration row for each imported owner and select it on its definitions.
  Keep workflow and procedure declaration kinds distinct in this index;
  same source `module::name` does not imply one closed callable identity.
- Copy the `names` mapping in the translation context at lexical binding
  edges while sharing the definition's Renamer allocator. Call `bind`/`ref`
  with that map; keep the type environment separate. Translate initializers,
  map sources, loop seeds and budgets before entering their binder's scope;
  restore parent mappings for sibling arms. Emit only the optional overrides
  specified by the [binding-label schema](#binding-labels).
- Rules this task implements, each cited:
  - P1: `call` → `{"k": "call", "callee": canonical, "args": [...]}`; the
    callee's body elaborated once with `elaborate_typed_workflow_body(procedure.typed_body, owner_name=procedure.definition.name, type_env=d.source_program.procedure_type_env(procedure), value_env=_procedure_signature_local_type_bindings(procedure), workflow_return_types=<every workflow's return type>, procedure_return_types=<every procedure's, generic templates excluded (case e)>, route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)`,
    normalized with `normalize_wcc_body_to_anf`, stored under
    `definitions[canonical] = {"key": key, "params": [[renamed param, descriptor]], "result": descriptor, "body": ...}`. A
    recursive call (the callee is on the active stack) is a `ClosedProgramGap`
    with form `call` ("recursive call"). `workflow_call` likewise, by the
    workflow's canonical name, with keyword arguments matched to parameters,
    a parameter the call leaves out taking its declared default (`lit`) or,
    when the signature has a hidden context requirement for it, the X1/X2
    value; a parameter with neither is a defect of the typechecker
    (`ValueError`). For an explicit compiled import, match against its
    retained caller view, then emit the shared `boundary` relation to the
    native body. Use existing `derive_workflow_signature_contracts` projections
    and private classification; do not replace native types with caller types.
    Follow the shared slot/default/capture/context order and 1:N rules,
    preserving evaluation in ANF prefixes before permutation. `direct` handles
    strict generated/capture transfers; projections handle the boundary view.
    Neither case adds a site or reconstructs a body from flat steps.
    For ordinary same-key generated-only views, enforce the shared complete
    ordered-signature D predicate before annotating. Retain the independently
    frontend-proven relation for admitted compiled/context composition; P5
    checks the final relation and cannot authenticate that construction history.
  - Before P1 names are computed, convert existing `BoundProcArg`, value/
    workflow/reference specialization facts and generated local capture facts
    into closed bindings. Substituted compile-time expressions enter the full
    key; runtime captures become a leading typed capture prefix before
    the residual parameters, with call arguments evaluated once at their
    lexical binding before forwarding.
    Preserve the existing `_procedure_signature_local_type_bindings` and
    forwarding rules; never retain surface expressions or runtime refs in
    the artifact. Two captures of the same body share a definition; differing
    substitutions/reference targets/rebindings do not. The plain converted
    facts feed Task 6; no extra closure framework/module is needed.
    Use the exact [key grammar](#canonical-definition-keys), derive each
    `PRef.target`/bound/residual view from one resolved binding, and preserve
    the shared bound-formal bijection. Generated-local metadata supplies
    owner/name/ordinal and capture indexes; its historical raw capture/type
    names are not the wire schema. Resolve workflow externs to Task 7's
    exact rows, never an unresolved rebinding alias tuple.
  - For an admitted bundle exposing a private formal absent from its native
    entry, perform the shared context-capture conversion before computing
    keys. Match exact omitted recipients through the owner's resolved typed/
    WCC calls, native requirements and retained semantic wire/typed-path groups;
    resolve aliases and specializations in that owner. Preserve explicit
    bindings/defaults. Append only required captures to each affected wrapper's
    capture prefix, with the caller's descriptor, and forward the already
    evaluated names. The source-native signatures/bodies remain unchanged.
    At the terminal nominal crossing emit the shared checked internal boundary
    relation, including all ordinary residual and output rows. Use every
    matching recipient originally fed by the group, not the first compatible
    type; unrelated edges gain no capture. An unaccounted admitted group is a
    translation defect to repair, not a new release exclusion.
    Associate actual retained calls with their closed nodes and use the
    shared declaration-only/per-callee-occurrence routes; forwarding wrappers
    carry suffixes. No converted-key/hash cycle, runtime routing table or
    source-position/binder-derived discriminator is needed.
  - P2: every `WccOpaqueFrontendValue` is translated in `values.py`:
    `UnionVariantTagExpr` → `lit`; `LoopStateSeedExpr` → `record` (type: the
    carrier descriptor); `LoopStateUpdateExpr` → `op` with a `record_update`
    payload; `ListExpr` → `list`; `CompilerListNonemptyHeadExpr` → `op` with
    the catalog's `list_nonempty_head` payload (`compiler_owned: true`,
    `invariant_diagnostic: "list_nonempty_invariant_broken"`);
    `ListMapExpr` → `list_map` (the body elaborated with
    `_elaborate_expr_to_body` under an env extended with the binder, as the
    spike's `frontend()` does, then translated; a body with `let`s becomes a
    `block`); `PathJoinUnderExpr` → `op` with a `path_join_under` payload
    (`path_type` = the descriptor of `path_type_ref`, `child` = `a0`);
    `IfExpr` (a module below 2.26 elaborated under the new target's rules)
    → `select`; `LetStarExpr` (an inlined pure call) → `block` or its value;
    `GeneratedRelpathSeedExpr` → `lit` of `literal_path`;
    `ProviderBundlePathExpr` with a `NameExpr` source → `result_path` (X4);
    `ResourceTransitionExpr` → `ClosedProgramGap` (form `resource-transition`).
    A `WccPhaseTargetAtom` reaching the builder is a defect (Task 3 elaborated
    it away): `ValueError`. A `WccPureOp` with operator `path/join` →
    `path_join`. Any other operator → `op` with a one-operator payload
    validated by `validate_pure_expr_payload` (P5).
  - X1: `context.run_context_value() -> dict` = the record
    `{run-id: {"k": "context", "field": "run-id"}, state-root: lit "state/run", artifact-root: lit "artifacts/run"}`
    with the `RunCtx` descriptor. Bound at the entry for each hidden context
    parameter of kind `RunCtx` as a leading `let <param> = <record>`; supplied
    at a workflow call that leaves such a parameter out.
  - X2: `context.phase_context_value(run: dict, phase_name: str) -> dict` =
    the record `{run: <run>, phase-name: lit phase_name, state-root: lit f"state/{phase_name}", artifact-root: lit f"artifacts/{phase_name}"}`.
    `run` is the caller's context value: the caller's parameter typed
    `RunCtx` as a `name`, or the `run` field of its parameter typed
    `PhaseCtx` (`field`). For an admitted derived-child omission, reuse
    `phase.derived_private_child_context_eligibility(...).carried_input_sources`:
    project the exact `ItemCtx.run` paths and use
    `_runtime_context_default_value` for the child phase constants. Do not
    replace that carried run with X1. Resolve the source once; an explicit
    native context wins. Only an omission with no carried caller context uses
    `run_context_value()`. This preserves the existing compiled caller refusal
    `workflow_call_signature_erased` for the derived-prefix specimen; it does
    not broaden admission. Runtime equality with the present route remains
    the open item of this plan (design §19, 4).
  - X4: `result_path` carries the declared path descriptor. At the new
    target `typecheck_provider_bundle_path_expr` additionally requires the
    `:as` type's `under` to be `.orchestrate/runs` (the parent of every run
    root, `specs/state.md`), else `provider_bundle_path_target_invalid`;
    this one-line rule in `typecheck_effects.py`, gated by
    `target_dsl_uses_evaluated_execution(context.type_env.target_dsl_version)`,
    belongs to this task.
  - §4.3: a `halt` in a join's body is the join's value: `body()` translates
    it as `halt` and the evaluator (Phase 3) treats it so; nothing to do here
    beyond keeping `halt` in that position. `continue` → `{"k": "continue", "loop": d.loops[-1], ...}`
    only when the WCC node's `target_name` names that loop (Task 3
    guarantees it; a mismatch is a `ValueError`).
- Consumed by: Tasks 8, 9, 10.

#### Binding-origin retention and conversion

Task 4 retains one transient fact through existing binder records:
`binding_label: str | None`, the authored label or no authored label for a
compiler-created binding. A source `SyntaxIdentifier` with no
`introduced_by_expansion_id` contributes its `display_name`; an introduced
compiler identifier contributes `None`. Caller-authored macro arguments
keep their origin. Never reconstruct this fact from a resolved spelling,
hash suffix, span, or `form_path`; cloning may give many nodes the same
source location. Existing admission rules are unchanged.

| Binder | Exact retained route into the builder |
| --- | --- |
| `let*` | Binding identifier → parallel immutable `LetStarExpr.binding_labels` entries → `WccLet.metadata.binding_label`; a control binding instead carries that entry on `WccJoin.metadata.binding_label` for its sole result parameter. Slice/reorder labels together with their bindings. |
| `match` arm | Pattern identifier → `MatchArm.binding_label` → `WccCaseArm.binding_label` via `_elaborate_case_arm`. The builder supplies that origin to the arm's scoped `Renamer.bind`; no closed case-arm `label` is emitted. |
| Pure `list/map` | Binder identifier → `ListMapExpr.binding_label`, retained with the expression inside `WccOpaqueFrontendValue` → `values.py`'s `list_map` conversion. Rename with explicit origin under the body scope; no closed `list_map.label` is emitted. |
| Source loop state | State identifier → `LoopBodyFnExpr.binding_label` in `_elaborate_loop_body_fn` → `LoopRecurExpr.binding_label` in `_elaborate_loop_recur` → `WccRecJoin.metadata.binding_label` for `params[0]`. |
| Effectful list item (`list/map-effect`) | Binder identifier → `ListMapEffectExpr.binding_label` → its item-binding entry in `typecheck_structural_values`' synthetic `LetStarExpr` → `WccLet.metadata.binding_label`. Preserve the authored item; synthetic result/tail/state bindings and the generated `LoopRecurExpr` state have no authored label. Retain Task 3's terminal-state and operand-order behavior. |
| Generated ANF/capture/context/temporary/control target | Its existing constructor or conversion owner supplies `None`; generated join/loop targets are separate from result/state labels. Native definition parameters use their retained declaration facts. |
| Native workflow/procedure parameters | Declaration `SyntaxIdentifier` → transient `WorkflowParam.binding_label` / `ProcedureParam.binding_label`; caller-authored macro arguments retain their label, while introduced and unused template parameters remain `None`. The builder uses the declaration records directly; typed signature tuples do not carry this fact. Generic procedure specialization preserves the origin on each residual parameter. |

Runtime closure captures also retain the existing `BindingIdentity` for the
actual lexical binder through transient typed and existing WCC binder/call
metadata. Existing specialization-capture rows additionally retain their
originating `BindProcExpr` transiently, so a bound formal (or nested formal
path) selects aliases from its own creation region even when inherited
captures reuse one source spelling across a shadow. Closed elaboration freezes a demanded runtime value at its lexical
owner with an anonymous binding, then forwards that binding through local
procedures, joins, loops, and imported wrappers. The alias map is copied at
lexical edges; identities are never reconstructed from a spelling or used as
a global registry. These facts are omitted from repr, equality, semantic
identity and legacy serialization. A source-deleted imported build uses the
retained typed producer snapshot; any decoded bundle must reattach that
in-memory snapshot before closed construction. No new field is added to the
legacy bundle or artifact formats.

Use default absent origin on compiler-generated constructors, and require
every `Renamer.bind` call to pass the appropriate fact, including case and
list-map binders. Preserve unchanged authored lexical names. This is data
carriage, not another registry or binder framework.

Use `repr=False`, `compare=False`, `hash=False`, and Task 3's existing
`json_omit_always` field metadata for these transient fields. Exclude them
also from `procedure_typecheck._semantic_identity`, which walks dataclass
fields independently of repr/equality flags; legacy callable names and
serialized outputs must remain unchanged. Do not add these facts to type
definition dataclasses. `WorkflowParam` and `ProcedureParam` are retained
declaration records; their new facts stay transient and are read only by the
closed builder. Only the explicit closed-schema projection is semantic
artifact data.

Audit manual reconstruction and binding-list slicing/concatenation in the
listed files. In particular, `typecheck_dispatch` and `conditionals` rebuild
authored lets, `functions._clone_function_expr` rebuilds match arms, and
`wcc/anf.py:_normalize_body` rebuilds `WccCaseArm`; preserve their origin,
using `replace` where sufficient. Hygiene's `replace` of lexical names must
keep the original metadata label across repeated renames. Fresh ANF lets
must not inherit a source binding's label merely because they copy its
diagnostic metadata. The existing capture-safe spelling algorithm and
flag-off behavior stay intact.

- [x] **Step 1: Write the failing tests**

Through `build(root, sources)` of the helpers module (`install`,
`compile_typed_program`, `build_closed_program`):

```python
def test_three_call_sites_of_one_procedure_are_one_definition_and_three_frames(tmp_path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))
    callee = "procedure:cp/three_call_sites::fetch"
    assert sorted(closed.tree["definitions"]) == [callee]
    assert closed.sites == ((callee, "#1"),)
    assert [c["frame"] for c in calls(closed.tree["body"])] == [f"{n}={callee}" for n in ("a", "b", "c")]

def test_one_procedure_in_three_arms_of_a_match_in_a_loop(tmp_path) -> None:      # Review focus 1
    assert closed.sites == ((callee, "#1"),)
    assert len(calls(closed.tree["body"])) == 3   # check each arm's loop/frame prefix separately

def test_the_program_holds_no_surface_object(tmp_path) -> None:
    for name in ("arms_in_loop", "loop_in_loop", "if_over_lists"):
        closed = build(tmp_path / name, fixture(name))
        validate(closed.tree)  # every node kind/child is in the closed schema
        assert_all_leaves_are_json_values(closed.tree)  # no frontend Expr/TypeRef objects

def test_an_effectful_argument_gives_two_frames_in_source_order(tmp_path) -> None:
    # (fetch (inc 4)): ordered frames #1=procedure:...::inc then #2=procedure:...::fetch;
    # sites are only the performs in the two callee definitions.

def test_all_reference_bindings_and_runtime_captures_close(tmp_path) -> None:
    # Public builds: same-base value/workflow specializations differ; bound proc refs forward;
    # one captured computation is bound once before two calls, both passing that same value;
    # nested let-proc captures work and no runtime ProcRef or surface Expr survives.

def test_same_named_procedure_and_workflow_are_distinct_closed_definitions(tmp_path) -> None:
    # One entry reaches both admitted callable kinds; retain both bodies under
    # procedure:collision::same and workflow:collision::same, then read back.

def test_imported_old_target_loop_in_branch_builds_without_flat_lowering(tmp_path) -> None:
    # Task 2's imported fixture now reaches ClosedProgram and passes from_artifact.

def test_compiled_imports_keep_native_bodies_and_caller_boundary_views(tmp_path) -> None:
    # Public old-bundle and typed-product imports: distinct nominal records,
    # dynamic paths, and one Pair argument feeding native a__x/a__y params.
    # Add defaults/capture/context slots; assert complete aligned relation and
    # once-only authored/lexical ANF prefixes, then artifact read-back.
    # Producer source deletion and conflicting caller configuration preserve
    # producer body/bindings/asset base; no live-source reread or flat lowering.

def test_private_nominals_remain_distinct_in_entry_effect_and_nested_descriptors(tmp_path) -> None:
    # Two imported private Note types are recursively module-qualified everywhere.

def test_used_injected_adapter_requires_its_declared_package_closure(tmp_path) -> None:
    # Full build/read-back of Task 7's injected adapter; remove declaration to assert
    # located command_boundary_closure_missing. A real manifest override keeps workspace base.

def test_a_loop_in_a_branch_and_a_loop_in_a_loop_build(tmp_path) -> None:
    assert build(tmp_path / "a", fixture("loop_in_branch")).sites and build(tmp_path / "b", fixture("loop_in_loop")).sites

def test_a_list_map_body_is_a_value_over_its_binder(tmp_path) -> None:
    # (list/map ((x xs)) (+ x 1)) -> {"k": "list_map", "binder": "x", "source": {...}, "body": {"k": "op", ...}}

def test_hygienic_effect_labels_survive_unrelated_pure_refactoring(tmp_path) -> None:
    # Outer x=false; (and (let* ((x (check 1))) x) x): inner/outer refs remain distinct.
    # Insert a pure binding, then rename outer x so hoisting needs no rename:
    # same authored inner label, sites, frames and callee keys; once-only call prefix.
    # A changed pure body may change the program digest.

def test_origin_survives_case_maps_and_loop_conversion(tmp_path) -> None:
    # Authored and introduced macro case/list-map binders retain explicit origin;
    # authored names stay, generated names become %n, no closed label on these nodes.
    # LoopBodyFn -> LoopRecur -> WccRecJoin carries source state origin.
    # ListMapEffect item -> synthetic let keeps its label; synthetic state is anonymous.
    # Include admitted let names __authored, %1 and a hex-suffix name.

def test_relocation_preserves_closed_binding_names_labels_and_identity(tmp_path) -> None:
    # Blank lines, source/package relocation and different PYTHONHASHSEED:
    # equal stripped digests, lexical names, labels, sites/frames and callee keys.
    # Cover a specialized callee and introduced case/list-map binders.

def test_a_recursive_call_is_a_gap_at_the_call(tmp_path) -> None:
    # closed_program_gap, notes ("form=call",), at the recursive call's line;
    # if the typechecker already refuses the program, pin its code instead and say so in the report

def test_a_command_node_carries_its_boundary_closure_contract_and_repeat_rule(tmp_path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"),
                   boundaries={"fetch": ExternalToolBinding("fetch", ("python", "probe.py"), closure=("probe.py",), must_not_repeat=True)})
    (node,) = performs(closed, "procedure:cp/three_call_sites::fetch")
    assert (node["class"], node["boundary"], node["command"], node["closure"], node["repeat"], node["contract"]["kind"]) == \
        ("command", "fetch", ["python", "probe.py"], [{"base": "workspace", "path": "probe.py"}], "never", "output_bundle")
    assert "path" not in node["contract"]["payload"]
    assert node["argv"] == [{"k": "lit", "v": "fetch"}, {"k": "name", "n": "n"}]

def test_a_boundary_without_closure_is_refused_before_elaboration(tmp_path) -> None:     # Review focus 3, C1
    with pytest.raises(LispFrontendCompileError) as e:
        build(tmp_path, fixture("three_call_sites"), boundaries={"fetch": ExternalToolBinding("fetch", ("python", "probe.py"))})
    (d,) = e.value.diagnostics
    assert (d.code, d.notes) == ("command_boundary_closure_missing", ("boundary=fetch",))

def test_a_certified_adapter_receives_one_document_in_signature_order(tmp_path) -> None:
    # a CertifiedAdapterBinding with input_signature (b, a) and invocation_protocol json_object_positional_arg,
    # called with :a and :b -> node["document"] == [["b", value_b], ["a", value_a]], node["argv"] == []

def test_a_form_outside_the_release_is_a_gap_naming_it(tmp_path) -> None:
    # one program with (materialize-view ...): code closed_program_gap, notes ("form=materialize-view",), at its line
```

Build and read back real direct and transitive compiled-import private-context
specimens through the public API. Supply nondefault contexts; verify one
capture slot, exact native recipients, complete outer/internal boundary rows,
unchanged original signatures and reuse for two values of the same type/routes.
Build/read back the admitted scalar, List and phantom same-S generic-call
fixtures with representative reuse and preserved distinct producer links;
pure-name insertion/relocation must preserve identities. Cover an admitted
capture/context combination when available, distinguishing typed-fixture
proof from unproven source admission. Verify ordinary distinct canonical
capture types produce consistent distinct keys,
explicit bindings win, every matching omission receives the capture, and
unrelated calls stay unchanged. Phase 3 adds an execution assertion with a
once-counted source expression; a Phase 2 structural proof is not that test.

`tests/test_workflow_lisp_closed_program_context.py`:

```python
def test_a_call_that_leaves_out_run_receives_the_run_context_record(tmp_path) -> None:
    # entry `entry` calls a workflow with a hidden `run : RunCtx`; the call's args hold the X1 record
    assert call["args"][i] == {"k": "record", "type": ANY_RUNCTX_DESC, "fields": [
        ["run-id", {"k": "context", "field": "run-id"}], ["state-root", {"k": "lit", "v": "state/run"}], ["artifact-root", {"k": "lit", "v": "artifacts/run"}]]}

def test_a_call_that_leaves_out_a_phase_context_receives_the_phase_record(tmp_path) -> None:
    # fields run (the caller's `run` name), phase-name "work", state-root "state/work", artifact-root "artifacts/work"

def test_the_entry_binds_its_own_hidden_run_context_first(tmp_path) -> None:
    assert closed.tree["body"]["k"] == "let" and closed.tree["body"]["name"] == "run" and "run" not in dict(closed.tree["params"])

def test_a_provider_bundle_path_is_a_result_path_typed_under_the_run_root(tmp_path) -> None:
    # (provider-bundle-path r :as ResultBundle) with (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
    # Test typechecking and value translation with a typed provider-result binding;
    # Task 4 does not yet translate the provider effect that produces it.
    # -> {"k": "result_path", "n": "r", "type": {...}}; with :under "state" -> provider_bundle_path_target_invalid at the form
    # Task 8 owns the complete provider-producing program build.
```

- [x] **Step 2: Run; expected failures** `ImportError`, then gaps and
`ValueError`s as each translation is missing.

- [x] **Step 3: Implement** in this order: the
[origin carriage](#binding-origin-retention-and-conversion) above, then `Definition` and `Builder.body`
for `let`/`halt`/`if`/`case`/`join`/`jump`/`loop`/`continue`/`done`;
`values.py` for atoms, ops, select, then each opaque kind; `effects.py`
(`require_command_closures`, the command node, the gaps); `call` and
`workflow_call` with the memoized table; `context.py`; the X4 typecheck
line; canonical type/config facts, sites, validation and digest at the end. Keep the existing responsibilities small;
add no modules solely to meet a line estimate.

- [x] **Step 4: Run; expected pass.** Then Tasks 5, 6, 7 modules (they are
unchanged but their consumers are new).

- [x] **Step 5: Compatibility evidence**

Build the four programs of the table; require byte-identical output after
both the gated `typecheck_effects.py` change and transient origin retention.
Run the relevant existing hygiene/normalization selectors and verify old
local/specialization identities and repr/serialization exclude the new
fields. The new public builds must pass artifact read-back, lexical scope
checks and perform/site bijection. These compile checks do not establish
Phase 3 runtime execution/resume behavior.

- [x] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/conditionals.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/typecheck_structural_values.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/procedures.py orchestrator/workflow_lisp/procedure_specialization.py orchestrator/workflow_lisp/procedure_refs.py orchestrator/workflow_lisp/procedure_typecheck.py orchestrator/workflow_lisp/typecheck_context.py orchestrator/workflow_lisp/typecheck_loop_recur.py orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/expression_traversal.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/wcc/anf.py tests/workflow_lisp_closed_program_helpers.py tests/test_workflow_lisp_closed_program_build.py tests/test_workflow_lisp_closed_program_context.py tests/test_workflow_lisp_closed_program_check.py docs/plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md`

`git commit -m "feat: build the closed program as a table of definitions with the run's context values" -- orchestrator/workflow_lisp/closed orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/conditionals.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/typecheck_structural_values.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/procedures.py orchestrator/workflow_lisp/procedure_specialization.py orchestrator/workflow_lisp/procedure_refs.py orchestrator/workflow_lisp/procedure_typecheck.py orchestrator/workflow_lisp/typecheck_context.py orchestrator/workflow_lisp/typecheck_loop_recur.py orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/expression_traversal.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/wcc/anf.py tests/workflow_lisp_closed_program_helpers.py tests/test_workflow_lisp_closed_program_build.py tests/test_workflow_lisp_closed_program_context.py tests/test_workflow_lisp_closed_program_check.py docs/plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md`

**What this makes harder later:** both target routes retain their own
elaboration consumers until flat-route retirement. Imported source modules
are never flat-lowered during an evaluated-entry build. Context-value runtime
parity remains Phase 3 evidence; any discrepancy must be repaired in the
small context translation, not hidden as a new exclusion. Reconstructed
binders must preserve one origin fact, and artifact readers must distinguish
lexical names from authored identity labels.

---

### Task 8: Effect Nodes: Providers, Run References, And The Gaps

Finalize [loop-carrier](#generated-loop-state-carrier-identities) applied arguments together with fields and type-table uses through their retained actual producers. Their head stays stable because it hashes D rather than concrete generated names. Add public build/read-back checks with same-S distinct producers, including phantom arguments, without a new registry or serialized origin field.

**Files:**
- Modify: `orchestrator/workflow_lisp/closed/effects.py` (created by Task 4 with the command node, the closure rule and the gaps), `orchestrator/workflow_lisp/closed/build.py` (producer associations and call run-ref finalization after site assignment and before validation), `orchestrator/workflow_lisp/closed/values.py` (preserve exact producer context across selected value-prefix bindings)
- Modify: `orchestrator/workflow_lisp/closed/names.py` (generated RunRef results are structural, not ordinary nominal owners, during local ProcRef type unification)
- Modify: `orchestrator/workflow_lisp/contracts.py` (allow the closed caller to project nested nominal descriptors from retained TypeRefs before shared-versus-variant contract placement; callers that omit the projector keep the legacy projection)
- Modify: `orchestrator/workflow_lisp/closed/build.py` and `closed/effects.py` (retain and rederive generated-type-bearing command/provider result contracts after actual run-ref producer names finalize)
- Modify: `orchestrator/workflow_lisp/expressions.py` and `functions.py` (retain the exact captured binder and checked type on generated pure-call static-argument rows), `typecheck_dispatch.py` (carry those transient rows through the typed `LetStarExpr` reconstruction), `wcc/elaborate.py` and `wcc/model.py` (consume them only on the closed route as identity-bearing name reads), `wcc/hygiene.py` (preserve that identity and type through spelling renames), and `closed/build.py` (pre-scan opaque retained rows, freeze their lexical owners and resolve values and producer context through the same scoped alias)
- Modify if needed: `orchestrator/workflow_lisp/closed/check.py` (verify Task 5's complete read-back checks against finalized run-reference nodes)
- Test: `tests/test_workflow_lisp_closed_program_effects.py`

**Read first:** the spike's `closed_effects.py` in full; design P3, §1.1
(the classes and the portable subset), §9.1 (inputs), §9.2 (bundle mode is
later), K7; lowering's `_lower_provider_result_operation`
(`lowering/effects.py` line 444: policy, prompt source, typed prompt inputs,
dependencies), `derive_prompt_guided_structured_result_contract`
(`contracts.py`), `typed_prompt_inputs.py` (how a typed prompt input is named
and which renderer it gets), `resolve_default_view_renderer`
(`orchestrator/workflow/view_renderer.py`), `run_ref/config.py`
(`build_run_ref_static_config`, `encode_run_ref_static_config`,
`ReferenceBinding`, `RunRefInput`), `run_ref/contracts.compute_compiler_runtime_identity`,
execution facts A.2 and A.4.

**Interfaces:**
- Consumes: Task 4's `translate_perform`, `Builder.value`, `Builder.desc`,
  `ClosedProgramGap`; Task 7's exact resolved provider/prompt configuration
  rows and the shared structural key projection for generated run-ref types.
- Consumes: normalized pure local-procedure capture rows retained on typed
  `LetStarExpr`s at every source target that admits this normalization
  (2.30+). They name the actual captured `BindingIdentity` and checked
  `TypeRef`; an imported native snapshot is consumed as retained and is not
  retyped or normalized again. Only closed WCC elaboration reads these rows;
  the legacy route ignores them.
- Produces: two more branches of `translate_perform`, each a `perform` node
  of the schema:
  - `provider_result`: `provider` = `d.externs[target].provider_id`;
    it agrees with the selected configuration's `{provider_id}` row.
    `prompt` preserves `PromptExtern.source_kind` and exact bound `path`.
    `asset_file` carries the logical entry asset base used by the current
    lookup; `input_file` retains workspace/input lookup semantics. Never
    prepend an asset root or reinterpret an input file. Resolve imported
    extern rebindings through the typed module environment, not only the
    entry's alias map, and use the same exact prompt row as `WRef.externs`
    and the selected configuration. For `defprompt`, emit template and the
    ordered typed slot rows defined above. Preserve `doc` references as required content
    injections (prepend, declaration order), with no renderer; other slots
    retain renderer, repeated placeholder positions, refinements and output
    roles/expected-output facts. Reuse semantic projections from
    `_build_compiler_prompt_fragment_contract` in `lowering/phase_scope.py`
    and `_lower_prompt_fragment_dependencies` without constructing flat steps
    or copying their step-id-based identity. `inputs` retains the established
    typed names as preferred labels, renderer selection and value expressions.
    Before translation, reserve the entire preferred-name list. In input
    order, the first occurrence keeps its preferred label; later occurrences
    of the same label receive the smallest unreserved `preferred__N`, with a
    per-label counter starting at 2. Reserve every assigned label. Preserve
    all rows and their original order, renderer and value, including repeated
    expressions; do not deduplicate inputs. This closed-only collision rule
    follows evaluated-execution design §9.1 and leaves the legacy lowering
    route unchanged. A colliding closed input's label can therefore differ
    from its legacy label, while its value, renderer, and ordered row remain
    unchanged. Compiler-generated ANF input labels use the retained
    `Renamer` binding for that exact input occurrence, while authored labels
    (including lookalike spellings) remain authored; do not classify by a
    generated-name prefix;
    `dependencies` from `WccPromptDependencyPayload` rows by role, with
    `position` and `instruction`; `policy` = each of `model`, `effort`,
    `delivery`, `materialization_attempts`, `timeout_sec` present in the
    payload, as values; `contract` derived as the command node derives it,
    from the declared result type; `repeat` = `"rerun"`. Payload parts `context_expr`,
    `session_artifact`, `capture_context` are gaps (form `provider-result`,
    naming the part: outside the portable subset, §1.1).
  - `run_ref`: path mode only. Translate inputs to closed typed values;
    retain source/program selection and supported static policy. First obtain
    the exact [shared structural signature `S`](#run-reference-structural-signatures)
    through Task 6's typed adaptation of Task 5's pure helpers: ordered input
    names/descriptors and the complete neutral result contract with only its
    own envelope name omitted. Retain
    user/private nominal identities, refinements, field order and the exact
    fixed runtime result schemas. References to another generated run-reference
    type use its structural signature, never its provisional or finalized
    generated name. Use this same structural projection in containing
    definition keys and on artifact read-back.

    After site assignment, compute the 64-character lowercase hexadecimal
    `site_digest = sha256(canonical_json(["workflow-lisp/run-ref-site/1", containing_canonical_definition, assigned_local_site, S])).hexdigest()`.
    `containing_canonical_definition` is always the canonical name string
    used in the first component of `sites`: `tree.entry` or the key string
    in `tree.definitions` verified against its retained K, never K itself.
    Here `canonical_json` uses the closed program's canonical UTF-8 JSON
    encoding. Set `generated_result_type = "RunRefResult$" + site_digest[:16]`,
    exactly as `build_run_ref_static_config` requires; do not derive a second
    independent generated name. This configuration/type digest does not alter
    the lexical site table or §6's runtime effect identity.

    Rewrite generated type occurrences in entry/definition/node descriptors,
    both endpoints of call boundaries and `types`, preserving structural
    definition keys. Rewrite atoms in applied identities through their actual
    producer associations, then re-render and register the concrete identity.
    Preserve the scoped producer map when sequential captures or selected-value
    prefixes extend a definition's names; a copied binder origin may associate
    with different actual producers in different emitted bodies.
    Command and provider result contracts can contain a transport-schema copy
    of the same nested nominal descriptors. Retain the contract's exact effect
    TypeRef and containing definition until producer names finalize, then run
    the shared contract derivation again through the finalized canonical
    descriptor projection before validation. This also recomputes
    shared-versus-variant placement from actual producer names. Preserve the
    existing guidance and source-subject projection; never patch transported
    names by provisional spelling or weaken the checker.
    Recompute result descriptor digests, then call the unchanged
    `build_run_ref_static_config`/`encode_run_ref_static_config` with these
    canonical facts and `RunRefInput(..., ReferenceBinding(f"inputs.{name}"))`.
    Never copy `payload.site_digest`, `payload.result_digest` or span-based
    generated names. Finalization does not recompute a definition key from
    finalized nominal names. Preserve the neutral schemas, fixed runtime
    descriptors, naming rule and codecs; existing targets retain their
    existing identity recipe.

    Register the neutral result's fixed runtime records in `types` under their
    reserved logical identities (`WorkspaceDelta`, `RunRefAccounting` and
    their nested fixed records), with exactly the descriptors accepted by
    `validate_run_ref_result_descriptor`; they are compiler-owned builtins,
    not module-declared user nominals. At build, use compiler ownership
    metadata, not spelling alone, to select this builtin treatment. A
    user/private nominal still uses `module::Name`. Register the generated
    envelope separately under its newly finalized `RunRefResult$<digest-prefix>`
    name; never register its old span-derived name. Rewrite each concrete use
    through its retained producer context; copied bodies/specializations may
    share an old spelling, and different sites may share S. Neither a global
    name substitution nor inversion of S resolves those origins.

    On artifact read-back, decode the config, reconstruct `S` from independently
    checked descriptor/producer facts, and recompute the full digest using the
    actual containing definition and assigned site. Require equality of all
    64 digest characters, the generated name, result descriptor/digest and
    ordered input names/types/reference bindings with the checked node and
    `types`. The neutral decoder validates the exact fixed runtime records;
    recursively compare each such record and the generated envelope with its
    `types` entry and all uses. Reject conflicting descriptors under one
    reserved identity. Successful neutral decoding alone does not establish
    this lexical correspondence. Source/program/policy remain in the encoded
    config and program digest; their changes must change semantic program
    identity but need not change a generated type when its site and signature
    are unchanged.

    Reuse `compute_compiler_runtime_identity` after verifying package-location
    independence. Bundle mode stays a located gap under §9.2. The Phase 3
    caller adapter reuses the existing run-ref ledger/runtime; this does not
    claim its step-oriented caller integration works unchanged.
  - the gaps of Task 4 stay for every other kind, each named by its surface
    form; this task adds a test per form.
- Consumed by: Task 4's `binding()` (unchanged), Task 9, Task 10.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_provider_node_carries_prompt_inputs_policy_dependencies_and_contract(tmp_path) -> None:
    # provider_review.orc and prompt_dependency.orc: prompt source_kind/path/base; inputs [["draft", "<renderer>", {...}]];
    # policy {"model": lit, ...}; dependencies {"required": [...], "optional": [], "position": ..., "instruction": ...}

def test_provider_input_label_collisions_keep_ordered_values_and_reject_duplicate_rows(tmp_path) -> None:
    # Field/field, field/name, repeated-expression and reserved-suffix cases;
    # source-deleted read-back preserves every value/renderer row and relocation
    # identity, while the checker still rejects a tampered duplicate label.

@pytest.mark.parametrize("source_kind", ["asset_file", "input_file"])
def test_prompt_source_selection_matches_the_existing_lookup(tmp_path, source_kind) -> None:
    # Put distinct sentinel bytes at the asset and workspace/input locations;
    # public compile preserves source_kind/path and the matching existing resolver
    # selects the same bytes as the old route. Assert source selection/content
    # digest, not authored prompt phrasing; neither source is silently coerced.

def test_a_defprompt_application_carries_its_template_and_fills(tmp_path) -> None:
    # Include doc, text, value, path and output-role slots; compare semantic
    # document dependencies/renderers/ordering/refinements/output facts with old lowering.

def test_path_run_ref_and_let_proc_ignore_formatting_and_location(tmp_path) -> None:
    # Public build after blank lines/comments and source/package relocation:
    # keys, generated names, decoded config/site_digest, sites and program digest equal.
    # Changing the actual input/result signature or bound source changes semantic identity.

def test_a_provider_bundle_path_builds_with_its_producing_provider(tmp_path) -> None:
    # Public build of the complete X4 program: provider effect plus result_path
    # with its declared .orchestrate/runs path descriptor, extending Task 4's value-only case.

def test_a_path_mode_run_ref_carries_the_static_config_with_reference_bindings(tmp_path) -> None:
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert [(i.name, i.binding.reference) for i in config.inputs] == [("seed", "inputs.seed")]
    # Fixed runtime records and the generated envelope agree with `types`;
    # private user nominals remain qualified, including nested producer results.
    # Include a generated type forwarded through a call, distinct same-S sites,
    # and any admitted repeated specialization with shared provisional names.

def test_same_signature_run_ref_producers_keep_occurrence_specific_types(tmp_path) -> None:
    # Public build/read-back with distinct producers sharing S, including a
    # captured local ProcRef, a copied/specialized body, a generated loop
    # carrier, and a phantom applied argument. Every concrete name points to
    # its own containing definition/site while structural keys stay unchanged.

@pytest.mark.parametrize("effect_kind", ["command", "provider"])
def test_nested_run_ref_contract_uses_actual_producers_after_finalization(
    tmp_path, effect_kind
) -> None:
    # A public Choice[A, B] result with LEFT.payload: List[A] and
    # RIGHT.payload: List[B], instantiated from two distinct same-S run refs.
    # For both effect kinds, source-deleted build/read-back keeps each variant's
    # nested record name paired with its actual producer, retains guidance and
    # provenance, and does not hoist provisional-equal fields as shared.

def test_selected_workflow_reference_body_uses_its_retained_provider_rows(tmp_path) -> None:
    # Extend the admitted Task 4 WorkflowRef specimen through public build and
    # read-back. Give caller and imported producer conflicting provider/prompt
    # aliases, including asset_file and input_file, and assert the selected
    # body, its WRef key and configuration use the producer's exact rows.

def test_local_proc_ref_can_capture_and_forward_a_generated_run_ref(tmp_path) -> None:
    # Public compile the Task 4 local-forward specimen. The selected local
    # procedure's PRef key must compare retained structural signatures and
    # retain the captured producer route; it must not resolve a generated
    # result as an ordinary nominal owner or add a release gap.

def test_run_ref_readback_checks_the_full_site_digest_and_reserved_types(tmp_path) -> None:
    # Public-build a finalized run-ref artifact, delete source, then change only
    # the digest suffix after its first 16 characters and tamper a reserved
    # runtime type. Strict artifact read-back refuses both.

def test_pure_inline_local_capture_reuses_its_actual_effectful_binder(tmp_path) -> None:
    # One authored effect captured through a local ProcRef remains one
    # definition/site after WCC elaboration. Cover command/provider/run-ref,
    # source-deleted native 2.35 and imported native 2.34 typed snapshots,
    # captured aliases and copied lexical owners; transient rows remain a
    # closed-route fact, with legacy byte compatibility checked separately.

@pytest.mark.parametrize("form", ["materialize-view", "resource-transition", "trial", "request-input", "with-live-providers", "run-provider-phase"])
def test_a_form_outside_the_release_is_a_gap_at_its_own_location(tmp_path, form) -> None:   # Review focus 4
    # one small program per form (write them inline; each typechecks at the new target)
    d = gap(tmp_path, PROGRAMS[form])
    assert (d.code, d.notes, d.span.start.line) == ("closed_program_gap", (f"form={form}",), LINES[form])

def test_a_provider_with_context_capture_and_a_bundle_run_ref_are_gaps(tmp_path) -> None:
```

- [ ] **Step 2: Run; expected failures** `closed_program_gap` with
`form=provider-result` and `form=run-ref` where nodes are expected; the
gap tests pass already (Task 4 raised them) and stay as the record.

- [ ] **Step 3: Implement** the existing effect dispatch, with helpers
`_provider`, `_prompt`, `_inputs`, `_dependencies`, `_run_ref` as needed.
Task 8 owns producer-scoped run-ref config/descriptors finalization after Task 5 assigns
sites; keep this helper in `effects.py` and insert its call in
`build_closed_program` after `assign_sites` and before `validate` and
`program_digest`. Retain actual pure-call capture owners in transient typed
rows for all admitted source targets, consume those rows only in closed WCC
before copied initializers can emit effects, and resolve their exact aliases
for both value translation and generated-type producer context. Add the
complete provider-producing X4 build check here. Re-derive generated-type-
bearing command/provider result contracts at this same finalization boundary
from their retained TypeRef and producer context, before validation.

- [ ] **Step 4: Run; expected pass.** Also Task 4's module (unchanged
behaviour for commands).

- [ ] **Step 5: Compatibility evidence:** Task 8 also changes the shared
`closed/names.py` type-unification consumer and the optional nested descriptor
projection in `contracts.py`. Run the focused canonical-name,
PRef/let-proc, hygiene/normalizer, and old-target compatibility selectors;
report any byte changes against the same compiler/runtime pin inputs. New
capture-source rows remain absent from equality, generic hygiene name
collection, serialized artifacts and the legacy WCC/flat route; only the closed
consumer resolves them. The native 2.34 import test must use its retained
typed snapshot after source deletion, with no source replay. The generated-type
branch must affect only the new structural comparison and must not alter the
legacy identity recipe. Shared command/provider contract rederivation must
preserve guidance, source-subject provenance and legacy default projection
behavior while recomputing generated nominal placement. Closed prompt rows
retain document fills in `prompt.fills` and any explicit dependency rows in
the separate `dependencies` channel. The source frontend continues to reject
fragment prompts that redeclare explicit prompt dependencies; this task does
not widen source syntax.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/effects.py orchestrator/workflow_lisp/closed/build.py orchestrator/workflow_lisp/closed/values.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/wcc/hygiene.py orchestrator/workflow_lisp/wcc/model.py tests/test_workflow_lisp_closed_program_effects.py docs/plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md`

`git commit -m "feat: provider and run reference nodes in the closed program" -- orchestrator/workflow_lisp/closed/effects.py orchestrator/workflow_lisp/closed/build.py orchestrator/workflow_lisp/closed/values.py orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/closed/check.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/wcc/hygiene.py orchestrator/workflow_lisp/wcc/model.py tests/test_workflow_lisp_closed_program_effects.py docs/plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md`

**What this makes harder later:** each later class replaces a gap branch.
Phase 3 still proves assembled prompt parity and run-ref caller integration;
Phase 2 must already preserve all assembly/contract facts, so that remaining
runtime evidence does not authorize dropping document slots or dependencies.
Pure-call normalizers and typed-tree rewrites must now keep one additional
parallel transient fact aligned when they splice, slice or rename generated
`let*` rows; generic name collectors must continue to ignore its owner facts.
That row stays out of the wire schema, and the legacy consumer remains until
its route retires.
The closed builder also retains generated-type-bearing effect contract
requests until producer names are final, so finalization must rederive their
shared/variant placement before checked-tree validation.

---

### Task 9: `orchestrator compile` At The New Target: The Build Key And The Artifact On Disk

**Files:**
- Create: `orchestrator/workflow_lisp/closed/artifact.py`
- Modify: `orchestrator/workflow_lisp/build.py` (share compiled-import manifest entry validation; keep legacy loader/initializer behavior)
- Modify: `orchestrator/workflow_lisp/closed/target.py` (optional source-read trace forwarding through the existing target reader)
- Modify: `orchestrator/cli/commands/compile.py` (`compile_workflow`, before `normalize_frontend_artifact_exports` at line 63)
- Test: `tests/test_workflow_lisp_closed_program_compile_cli.py`

**Read first:** `build.py` lines 845 to 980 (`_build_frontend_bundle_in_memory`:
how the manifests are loaded and the request resolved), `build_manifest_io.py`
(`_resolve_request`, `_load_string_mapping`, `_load_prompt_extern_mapping`,
`_load_command_boundaries_manifest_payload`, `_parse_command_boundaries_manifest`),
`build_artifacts._fingerprint_build` (line 61: what the flat build key
digests), design P7, §8.4, C7.

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ClosedProgramBuildResult:
    build_root: Path            # <workspace>/.orchestrate/build/<build key>
    build_key: str
    program: ClosedProgram
    artifact_path: Path         # build_root / "closed_program.json"
    manifest_path: Path         # build_root / "manifest.json"
    entry_workflow: str

def build_closed_program_bundle(request: FrontendBuildRequest) -> ClosedProgramBuildResult
def closed_build_key(*, target: str, entry_workflow: str, source_file_digests: Mapping[str, str],
                     provider_externs: Mapping[str, str], prompt_externs: Mapping[str, object],
                     command_boundary_manifest: Mapping[str, object],
                     imported_programs: Mapping[str, object]) -> str
```

  `build_closed_program_bundle` resolves the request as `build.py` does,
  loads provider, prompt, command and imported-workflow manifests using the
  existing validation/configuration owners. Select the evaluated route before
  `load_frontend_initialization_configuration`, whose old initializer eagerly
  compiles imports into runnable bundles. Keep that initializer unchanged for
  old targets. Call `require_command_closures` on each captured producer/root
  configuration at its manifest location. Load compiled imports as described
  below, then call `compile_typed_program` with both import maps and one fresh
  consumer `SourceReadTrace`, then `build_closed_program`. Write
  `closed_program.json` (`program.artifact()`) and `manifest.json`
  (`{"schema_version": "closed-program-build/1", "build_key", "program_digest", "representation", "target", "entry_workflow", "source_path", "source_roots", "sites": <count>, "artifact_paths": {"closed_program": "build/<key>/closed_program.json"}}`,
  written with `indent=2, sort_keys=True`). `closed_build_key` is
  `sha256(canonical JSON of its arguments)[:16]`; it holds no incidental
  source/install location (authored semantic paths remain). Source files are
  keyed by module name with content digests, taken from the
  exact compile via `typed.source_file_digests` from Task 2's traced API, so
  equivalent builds in relocated workspaces use the same key under each
  workspace's build root. Within one workspace, atomically replace cache
  artifacts only after a successful validated build; provenance can differ.
  A build cache is not the durable run authority of Phase 3.
- Extract the old compiled-import entry validation into a shared iterator of
  `(binding_name, resolved_source_path, requested_entry)` tuples. The closed
  loader returns the plain pair `(bundles_by_binding, programs_by_binding)`.
  `kind=compiled` remains `.orc`-only and each producer still disables recursive
  imported manifests. Create its trace before target inspection and preserve
  it through the selected producer path. Add optional `source_read_trace`
  forwarding to the existing target-reader helpers; the target read and the
  selected compile share that exact trace so a changed source revision is
  detected. Existing callers without a trace keep their behavior. An
  old-target producer uses the
  existing in-memory compilation, retaining its selected bundle/snapshot; an
  evaluated producer calls the typed Stage 3 path and selects its export
  without `_require_runnable_in_memory_build` or a fake bundle. Task 2's shared
  export selector handles raw/canonical requested names and unique exports
  when omitted. The legacy loader's return type remains unchanged.
- `closed_build_key.imported_programs` contains canonical JSON contributions
  by supplied binding: selected canonical entry, producer target, original
  `source_file_digests`, canonical three-map configuration, and recursively
  retained import contributions. Reuse Task 7's projection; no old bundle
  fingerprint, incidental source/install path or raw manifest formatting enters this
  semantic contribution. Independently compiled producer bytes remain in
  producer trace evidence; never inject hashes into the consumer's trace or
  reread source to compute the key. Raw source digests affect build identity,
  not semantic `program_digest`.
- `compile_workflow`: after the `.orc` check, `target = entry_target_dsl_version(workflow_path)`;
  preserve the existing missing-source diagnostic
  `workflow_lisp_cli_input_missing` and old-target validation precedence:
  the routing pre-read must not turn a missing source into a generic I/O error.
  When `target_dsl_uses_evaluated_execution(target)`: any `--emit-*` flag
  is refused with `workflow_lisp_cli_input_unsupported` naming the flag
  (the flat artifacts do not exist at this target); otherwise call
  `build_closed_program_bundle` and print the summary
  `{"build_key", "build_root", "entry_workflow", "program_digest", "sites", "artifact_paths"}`;
  in machine mode print `{"status": "accepted", "program_digest": ..., "build_key": ...}`
  through `_print_machine_document`. Errors are handled by the same
  `except` clauses as today.
- Consumed by: Task 10 (the corpus builds through this function), Phase 3
  (`run` reads the checked artifact; resume freshly compiles current source/
  config and compares semantic program identity before memo access, then
  validates and executes the stored artifact).

- [ ] **Step 1: Write the failing tests**

Through `python -m orchestrator compile` in a subprocess with
`PYTHONHASHSEED=0` (the `_build` helper of `tests/test_workflow_lisp_target_234.py`
adapted: no `--emit-*` flags; the program is `PROGRAM` of that module at the
new target, with its actual task-owned probe scripts explicitly declared
in each manifest closure):

```python
def test_compile_writes_the_closed_program_and_its_manifest(tmp_path) -> None:
    summary, build_dir = compile_cli(files)
    program = ClosedProgram.from_artifact((build_dir / "closed_program.json").read_text())
    manifest = json.loads((build_dir / "manifest.json").read_text())
    assert (summary["program_digest"], manifest["program_digest"], manifest["build_key"]) == (program.digest, program.digest, build_dir.name)
    assert program.tree["entry"] == "workflow:grt/entry::run" and program.sites

def test_two_builds_of_one_source_at_two_paths_give_one_digest_and_one_build_key(tmp_path) -> None:   # Review focus 5, P7
    a = compile_cli(write(tmp_path / "here")); b = compile_cli(write(tmp_path / "elsewhere" / "deeper"))
    assert (a.digest, a.key) == (b.digest, b.key) and a.artifact != b.artifact     # provenance differs

def test_moving_the_orchestrator_package_changes_no_digest(tmp_path) -> None:
    # copy `orchestrator/` to tmp_path/package, run the CLI with PYTHONPATH there, as the spike's test did

@pytest.mark.parametrize("shape", ["specialized_import", "path_run_ref", "let_proc", "bound_capture"])
def test_blank_lines_and_comments_change_no_digest_and_no_site(tmp_path, shape) -> None:
    # Raw source digests/build key change; semantic program digest, generated names and sites do not.

def test_a_changed_stable_command_or_closure_changes_the_digest(tmp_path) -> None:    # C7

def test_an_unused_manifest_entry_changes_program_digest(tmp_path) -> None:
    # Both command kinds; also provider/prompt resolved configuration changes.
    # JSON whitespace/key order and normalized closure duplicates change no semantic digest.

def test_build_key_uses_the_same_compile_source_snapshot(tmp_path) -> None:
    # Mutate an import after its traced read; key uses consumed bytes, next build uses new bytes.

def test_compiled_import_manifest_selects_old_and_evaluated_producers(tmp_path) -> None:
    # CLI fourth manifest with one old runnable producer and one typed 2.35
    # producer; requested/unique export selection, no eager old initializer
    # for the new producer, both native bodies in the checked artifact.
    # A producer edit between target inspection and compilation is refused
    # by the shared trace's existing revision-consistency check.

def test_imported_snapshot_configuration_and_source_contribute_to_build_identity(tmp_path) -> None:
    # Original producer digests, transitive bodies and scopes survive; unused
    # producer binding changes semantic identity, relocation does not.
    # Selected entry/source-byte changes alter key; caller trace is separate.

def test_an_emit_flag_is_refused_at_the_new_target(tmp_path) -> None:    # exit 2, workflow_lisp_cli_input_unsupported

def test_a_manifest_without_closure_is_refused_at_the_manifest_path(tmp_path) -> None:   # Review focus 3
    # exit 2; the diagnostic's span path is the manifest; code command_boundary_closure_missing

def test_the_same_manifest_builds_at_2_34_as_today(tmp_path) -> None:   # the other half of Review focus 3: `_build` of the 2.34 module passes
```

- [ ] **Step 2: Run; expected failures** the CLI builds the flat artifacts
at the new target (Task 2 made lowering skip, so `build_frontend_bundle`
fails on the missing bundle: a `RuntimeError` or `KeyError`, exit 2 with no
code); record it.

- [ ] **Step 3: Implement** `artifact.py`, the CLI branch and shared manifest
entry validation, following the existing configuration and selection owners.
Do not duplicate the old initializer or route a typed producer through a
runnable-bundle requirement.

- [ ] **Step 4: Run; expected pass.** Then `tests/test_workflow_lisp_target_234.py`
and the compile command's existing tests (`rg -l compile_workflow tests`).

- [ ] **Step 5: Compatibility evidence**

`compile.py` changed: the four programs of the table through the CLI;
byte-identical, and the printed summaries equal apart from the output
directory.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/artifact.py orchestrator/workflow_lisp/closed/target.py orchestrator/workflow_lisp/build.py orchestrator/cli/commands/compile.py tests/test_workflow_lisp_closed_program_compile_cli.py`

`git commit -m "feat: compile a program at the evaluated execution target to its closed program artifact" -- orchestrator/workflow_lisp/closed/artifact.py orchestrator/workflow_lisp/closed/target.py orchestrator/workflow_lisp/build.py orchestrator/cli/commands/compile.py tests/test_workflow_lisp_closed_program_compile_cli.py`

**What this makes harder later:** two build functions and two manifest
schemas until Phase 7; Phase 3's `run` reads `closed_program.json` from the
build root by `build_key` and copies it beside `run.json` (§8.4).

---

### Task 10: The Corpus Check

**Files:**
- Create: `tests/workflow_lisp_closed_program_corpus.py` (helper, not collected), `tests/test_workflow_lisp_closed_program_corpus.py`

**Read first:** the spike's `census.py` (the corpus roots, how externs were
synthesized from checked-in manifests or the source: read it, do not import
it); the spike report iteration 3, D3 (38 of 52 built and the seven reasons);
design §18 first row; Phase 2 milestones P1, P2, P3.

**Interfaces:**
- Consumes: `build_closed_program_bundle` (Task 9) or `compile_typed_program`
  + `build_closed_program` in process (faster; choose in process).
- Produces: `corpus() -> list[Workflow]` over
  `workflows/examples`, `workflows/library`, `workflows/experiments`,
  `experiments/orc_vs_single_call`, `experiments/mlevolve_pair`: every
  exported workflow of every `.orc` file (52 today);
  `prepare(workflow, scratch) -> Prepared`: copies the file's source root to
  scratch, rewrites the entry's `(:target-dsl "...")` to the new target
  (imported modules keep theirs, §13), synthesizes the externs: providers
  from a checked-in manifest beside the workflow (`*providers*.json`) else
  `codex` for every provider name found in every module under the source
  root; preserve any checked-in imported-workflow manifest and compile its
  `.orc` producers through Task 9's shared routing with their own snapshots;
  prompts from a manifest else an empty file per prompt name; commands
  from a manifest else `["python", "<the leading literal words of :argv>"]`,
  and an explicit audited closure declaration for every fixture command.
  Do not synthesize an unknown `closure: []`: use checked-in known manifest
  declarations, compiler-owned declarations, or a task-owned stand-in script
  whose implementation is explicitly declared. Empty closure is only for a
  boundary whose empty promise is consciously authored. Record synthetic
  commands/prompts as compile-only evidence, never runtime parity. A boundary
  lacking enough signature/implementation facts to prepare is recorded as
  `not_synthesizable`, with the exact missing facts; it is not a new language
  gap, and the admission matrix must separately cover that supported form.
- Produces: `EXPECTED: dict[str, Outcome]` pinned per workflow: `built`
  (with its site count), `gap(form)`, `refused(code)` (a typecheck refusal
  the flat route gives too), `not_synthesizable`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("workflow", corpus(), ids=str)
def test_every_shipped_workflow_builds_a_closed_program_or_is_refused_by_a_gap_naming_the_form(tmp_path, workflow) -> None:
    prepared = prepare(workflow, tmp_path)
    outcome = try_build(prepared)          # Built(program) | Gap(form, line) | Refused(code) | NotSynthesizable
    assert outcome == EXPECTED[str(workflow)]
    if isinstance(outcome, Built):
        validate(outcome.program.tree)      # P1, P2; pure programs may have zero sites
        assert_perform_site_bijection(outcome.program)
        assert ClosedProgram.from_artifact(outcome.program.artifact()).digest == outcome.program.digest   # P5, P7

def test_the_partition_is_stated() -> None:
    counts = Counter(type(o).__name__ for o in EXPECTED.values())
    assert counts["Built"] >= 38                      # the spike built 38; X2 and X3 now build two more
    assert counts["Gap"] + counts["Refused"] + counts["NotSynthesizable"] + counts["Built"] == len(EXPECTED)
```

Write `EXPECTED` first from the spike's D3 table: `materialize-view` for
the five `validate-design-gap-architecture`, `-stdlib`,
`implementation-phase`, `run-plan-phase`, `run-work-item`;
`resource-transition` for `run-runtime-transition-fixture`,
`run-summary-view`, `apply-drain-status-transition`,
`emit-drain-status-transition-audit`; `trial` for
`qa_placement_trial::compare`; `refused(provider_phased_interactive_capability_missing)`
for `review-revise-design-docs-judgment-panel`; `refused(macro_arity_error)`
for `review-revise-parametric-design-docs`; `built` for the rest, including
`run-with-phase-composed-binding` and `lisp_frontend_design_delta::drain`
(X3 and X2 are built now). Where the run disagrees, the run wins: record the
actual outcome, and if a workflow that the spike built now fails, that is a
finding for the report, not an expectation to lower.

- [ ] **Step 2: Run; expected failures** the pinned outcomes that differ from
the actual ones; each is inspected before `EXPECTED` is corrected.

- [ ] **Step 3: Write the helper** (about 180 lines) and correct `EXPECTED`
from the run, with one line of justification per correction in the report.

- [ ] **Step 4: Run; expected pass.** Time the module; it should stay under
three minutes serial (38 builds at 0.1 to 0.3 s each plus typecheck).

- [ ] **Step 5: P3 evidence** (contracts and complete prompt assembly facts).

For `workflows/examples/improve_experiment_proposal.orc`, the two single-call
workflows, and dedicated input-file/document-slot fixtures, compile both
routes and compare each matched effect's runtime semantics. Remove only the
intentional transport output `path` (R3) and diagnostic `source_map_subject`/
source-map provenance, explicitly naming each ignored field. Keep all output
validation fields, renderer ids, slot kinds/types/order/output roles,
placeholder positions, policy and dependencies' ordered values, roles,
position and instruction. Normalize canonical private type names through the
known module mapping, never by deleting nominal distinctions. For synthetic
input labels, use the retained binding owner to normalize only the compiler-
generated occurrence; preserve authored labels even when they resemble
generated spellings. Compare prompt
source kind and lookup selection using distinct file contents. Counts alone
are not dependency parity. Reuse existing pure prompt/dependency projection
helpers where available; full executor-free prompt assembly and request
comparison through `run`/`resume` remain Phase 3 evidence. Test name:
`test_contracts_and_prompt_inputs_equal_the_flat_routes_for_the_real_programs`.

Add an explicit admission matrix alongside the shipped corpus: external-tool
and certified-adapter commands; both prompt source kinds; document/rendered/
output slots; plain/generic/value/workflow/ref-bound/captured/local calls;
path run-ref; all nested control edges in design §6. Include direct,
same-module-helper and imported-old-helper shapes for the formerly failing
positions. Add complete source-produced old bundles and typed 2.35 products,
explicit restoration, nominal record/path boundary views, 1:N arguments,
defaults/capture/context alignment and distinct producer configuration scopes.
Exercise both direct APIs and the fourth-manifest CLI route. Missing snapshots
and conflicting canonical contexts are explicit invalid-input tests under
Task 2's admission rules, not new `gap(form)` outcomes. Every admitted matrix
entry builds and round-trips; an internal compiler failure is repaired,
never added to `EXPECTED` as a new gap.

- [ ] **Step 6: Commit**

`git add -- tests/workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_corpus.py`

`git commit -m "test: every shipped workflow builds a closed program or is refused by a gap naming the form" -- tests/workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_corpus.py`

**What this makes harder later:** the pinned partition changes with every
Phase 4 class; the expectation table is the record of what the first release
covers.

---

### Task 11: Documents

**Files:**
- Modify: `specs/versioning.md` (the `v2.35 additions` block of Task 1: add what Phase 2 added), `specs/io.md` (a bullet under the deterministic artifact contracts: the command boundary manifest field `closure`, C1, C2's meaning at build, accepted and ignored below the new target), `docs/design/workflow_command_adapter_contract.md` (a section "Command closure declaration" beside "Command rerun behavior"), `docs/design/workflow_lisp_core_calculus_middle_end.md` (§10.1: the closed program's constructs and values at the new target, with a pointer to the schema of this plan; §11.4: identity at the new target is site and activation path, no lowering schema; §15: the deferred "authority inversion" is selected at gate G1; §16: remove the corresponding line), `docs/design/workflow_lisp_evaluated_execution.md` (Metadata status: Phase 2 implemented at the new target, the evaluator not; §4.1 table: the "Today" column becomes "Before Phase 2"), `docs/lisp_workflow_drafting_guide.md` (§2A: a paragraph after the table stating what a program at the new target gets today: `compile` builds the closed program, `run` refuses with `evaluated_execution_unavailable`, the forms refused by `closed_program_gap`, the `closure` field required), `docs/index.md` (the evaluated execution row: Phase 2 implemented; the Phase 2 plan row), `docs/design/README.md` (the design's status cell), `docs/capability_status_matrix.md` (one row: evaluated execution target, compile implemented, run future)
- Test: the existing document tests `tests/test_workflow_lisp_drain_roadmap_routing.py` (one known failure, `test_historical_q2_index_routes_current_selection_to_evolution_entry_gates`), `tests/test_monitor_docs.py`, and `tests/test_workflow_lisp_guide_programs.py` (the guide's quoted programs are unchanged)

- [ ] **Step 1:** Read each document's section named above and the
`documentation_conventions.md` checklist.
- [ ] **Step 2:** Write the changes. Every statement names the code or the
test that makes it true. No status word beyond "implemented", "refused",
"open".
- [ ] **Step 3:** Run the three test modules one at a time. Record the historical
known failure as baseline evidence, then repair any remaining failure in the
appropriate owner before closeout; never claim a failing selector passed.
- [ ] **Step 4:** Check every relative link of the touched documents resolves
(a ten-line script over `\[[^\]]*\]\(([^)#]+)` per file).
- [ ] **Step 5: Commit**

`git add -- specs docs`

`git commit -m "docs: record the closed program at the evaluated execution target" -- specs docs`

---

## Milestone Evidence

| Milestone | Evidence | Task |
| --- | --- | --- |
| P1. Callee bodies are part of the program | Every corpus workflow whose classes are in the release builds with one definition per canonical callee and no elaboration after `build_closed_program` returns; `three_call_sites` gives one definition and three frames | 4, 10 |
| P2. No surface object in a node | `check.validate` refuses an unknown `k`; every corpus tree is schema-valid JSON with no frontend objects (authored string contents are unrestricted) | 4, 5, 10 |
| P3. Effects carry contract, prompt assembly, policy and repeat rule | Command, provider and run-ref node tests; the contract and typed prompt inputs of the real programs equal the flat route's | 8, 10 |
| P4. The site table | Review focus 1 on `arms_in_loop`; one local perform site, call frames separate; total traversal and bijection | 4, 5 |
| P5. The normal form is checked when built | Every value/call/control/effect/entry type checked; operator and non-operator tampering refused on read | 5, 7 |
| P6. Provenance outside identity | Blank lines, a moved program and a moved package change no site and no digest; no name holds a path, a position or a type repr | 6, 9 |
| P7. The program is an artifact with a digest | Two builds at two paths share identity; unused semantic config edits change program digest; same-compile source bytes key the cache | 7, 9 |

## What Stays Open

- Whether the compiler's `PhaseCtx` (X2) and `phase-target` (X3) values
  equal the present route's (design §19, 4): one program per form, run on
  both routes, once Phase 3 runs programs. Until then `context.py` follows
  the flat route's constants (`_runtime_context_default_value`).
- The rendering of prompt dependency snapshots (design §19, 5): Phase 3,
  when prompt assembly runs outside the executor; the provider's ordered
  `prompt.fills` and separate explicit `dependencies` row together carry slot
  kinds, values, policy and ordering needed to prove parity; Phase 3 verifies
  their actual rendering.
- Which forms outside the release the corpus uses, by count: Task 10's
  expectation table is the answer and the input to Phase 4's order.
- Whether a `list_map` value should instead be a catalog payload: decided
  here as a closed value over its binder (the evaluator extends the
  environment per item); Phase 3 may revisit if the catalog's own `list_map`
  is cheaper to evaluate.

## Verification Commands And Phase 3 Handoff

Run from the implementation worktree root. For each new/renamed test module,
collect it before the narrow test. Substitute a task-owned scratch path:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest --collect-only -q -p no:cacheprovider tests/test_workflow_lisp_closed_program_frontend.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -p no:cacheprovider --basetemp=/tmp/phase2-task2/pytest tests/test_workflow_lisp_closed_program_frontend.py
```

Apply the same commands to each exact test module named in Tasks 1–10;
run existing owner selectors named in each task serially. Run Task 9's
provider/run-ref selectors after Task 8, then the corpus after both. Before
commit inspect `git diff --check` and the actual diff; stage/commit only the
listed paths (include an inspected adjacent owner only when necessary).

Compile smoke, from the worktree root after Task 9's helper installs its
selected-target source/manifests at `/tmp/phase2-smoke` (no flat emit flags):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=$PWD python -m orchestrator compile /tmp/phase2-smoke/grt/entry.orc --entry-workflow grt/entry::run --source-root /tmp/phase2-smoke --provider-externs-file /tmp/phase2-smoke/providers.json --prompt-externs-file /tmp/phase2-smoke/prompts.json --command-boundaries-file /tmp/phase2-smoke/commands.json
```

Task 9's subprocess fixtures must also compile a provider/run-ref specimen
using the same flags and task-owned manifests. Retain fresh exit 0, summary,
artifact read-back and perform/site bijection results. This public CLI
integration plus corpus round-trip is the Phase 2 orchestrator smoke; `run`
and `resume` intentionally remain unavailable and their no-launch refusal is
tested in Task 1. No external provider dispatch or Phase 3 evaluator is
needed for compile-only scope. The plan revision itself runs document checks,
not these future tests against nonexistent implementation modules.

Phase 3 consumes the checked `effect_class`, result contracts, full call/
capture/type facts, source-kind-preserving prompts, canonical configuration,
site/frame separation and position-free run-ref config. It must implement
checked `call.boundary` direct/projection transport over once-evaluated cached
arguments, native-order binding and result projection, preserving 1:N,
nominal path/record/union constraints and the definition's configuration scope.
Required runtime evidence includes argument/capture once-only behavior and
matching boundary values; Phase 2's old-route probes are not evaluator proof.
Its plan must retain
fresh compile versus header comparison before memo reads, stored-artifact
validation, preflight in journal order, durable `started` before allocation,
durable atomic header/program publication before `started`, closure evidence
checks before retrying uncommitted attempts, one atomic anchored suffix-
invalidation record, one external dispatch per memo attempt, run-ref settlement classification,
clean-terminal idempotence and profile-aware reader adapters. Closure content
hashes/symlink rules, interpreter pinning (no PATH re-resolution), caches
outside closure and output disjointness remain runtime work. No journal,
retry, terminal, trial-SDK or reader implementation enters this plan.

## Closeout

- [ ] Raw compatibility comparison for the four programs and compiled-import/
  nested run-ref specimens against `PHASE2_BASE`: equal bytes at identical
  identity inputs, separate fixed-identity serialization proof, and explicit
  explanation of real compiler-pin-dependent differences without weakening
  the pin or normalizing artifacts (Global Constraints).
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`,
  after narrow selectors pass. Record and resolve failures; do not weaken
  verification or accept a new failure by updating expectations.
- [ ] Fresh output: `python -m orchestrator compile` of
  `experiments/mlevolve_pair/search_compact.orc` retargeted, and of the
  `std/improve` example, at the new target; the summaries and the site
  counts in the report.
- [ ] The corpus table of Task 10 in the report, with the count built.
- [ ] Review by the repository Review role (Sol 6.1 high), with the owner's
  Critical-only gate above and every finding/evidence disposition recorded.
- [ ] Integrate according to the coordinator's authorized branch workflow;
  this document revision itself neither implements Phase 2 nor authorizes a
  target number, merge or push.
