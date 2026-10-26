# Workflow Lisp Frontend Deduplication

- **Status:** proposed; not an accepted language contract or implemented feature
- **Kind:** frontend authoring design
- **Owner:** Workflow Lisp frontend maintainers; language owner ratifies admission
- **Reviewers:** independent design reviewer and compiler/runtime owners
- **Created / last material update:** 2026-10-26
- **Implementation target:** existing evaluated frontend/core; version admission below requires an owner decision
- **Related:** [frontend baseline](workflow_lisp_frontend_specification.md), [command boundary contract](workflow_command_adapter_contract.md), [host input](workflow_lisp_durable_host_input.md), [language principles](workflow_language_design_principles.md)
- **Companion plan:** [implementation proposal and decision ledger](../plans/2026-10-26-frontend-deduplication-plan.md)

The shortened examples below are proposed syntax and are not runnable today.
Use current explicit `:argv`, `:returns` and per-row closure declarations until
this proposal is accepted, implemented and verified.

## Summary

Remove three repetitions from authoring: a command's complete static argv already
declared in its binding, a host answer type already declared by its applied
prompt, and a closure list deliberately shared by every command in a manifest.
Normalize each at its existing compile-time owner into today's explicit typed
forms and concrete command bindings. The evaluated core and runtime receive no
new protocol, inference obligation or shared-configuration reference.

Explicit argv, explicit host returns and flat manifests remain supported. This
proposal trades flexibility for one inspectable rule per omission; it makes
per-command closure exclusions, tool-specific arity inference and dynamic prompt
dispatch harder to add, and deliberately does not prepare machinery for them.

## Context And Authority

The [documentation index](../index.md), [capability matrix](../capability_status_matrix.md)
and [design index](README.md) select the authorities above and
[evaluated execution](workflow_lisp_evaluated_execution.md). Normative ownership
remains [DSL](../../specs/dsl.md), [IO](../../specs/io.md),
[state](../../specs/state.md), [CLI](../../specs/cli.md) and
[versioning](../../specs/versioning.md). This proposal does not amend them.
Admitted source/import/tooling targets are 2.35–2.40; typed host input requires
2.40. Historical flat lowering and fixed `HumanReply` are not extension points.

| Boundary | Existing owner and relevant fact |
| --- | --- |
| Command syntax | `orchestrator/workflow_lisp/expressions.py::_elaborate_command_result`, `_command_operands_from_sections`; `CommandResultExpr` distinguishes `inputs_present` and `operand_order` |
| Command resolution/checking | `typecheck_effects.py::typecheck_command_result_expr`; its context already owns `CommandBoundaryEnvironment`, unlike expression elaboration |
| Host syntax/type | `expressions.py::_elaborate_request_input`, `prompts.py::PromptCatalog`, `typecheck_effects.py::typecheck_request_input_expr`; prompts retain whether a return contract was actually declared |
| Manifest/configuration | `build_manifest_io.py::_load_command_boundaries_manifest_payload`, `_parse_command_boundaries_manifest`; `build.py` uses them for builds and immutable LSP initialization |
| Binding/closure authority | `command_boundaries.py`, `closed/program.py::_canonical_closure`, `closed/effects.py::require_command_closures`; C1 validates unused supplied rows too |
| Typed import ownership | `compiler.py` import normalization and `closed/frontend.py::TypedProgram`; definitions, prompt catalogs, command bindings and origins belong to their producer graph |
| Checked core | `expression_traversal.py`, `wcc/elaborate.py`, `closed/effects.py`, `closed/build.py`, `contracts/closed_program/check.py` |
| Build/editor/replay | `build_artifacts.py`, `closed/artifact.py`, `orchestrator/lsp/compile_driver.py`, `orchestrator/workflow/evaluated/{effect_inputs,replay,closure}.py` |

Paths without a package prefix in this table are under `orchestrator/workflow_lisp/`,
except `contracts/closed_program/`, which is under `orchestrator/`.

## Problem, Goals And Non-Goals

Repeated facts create extra editing sites and disagreement risks. This is a
language/configuration decision because removing required syntax must preserve
command mode, type ownership, effect order, import behavior and recovery identity.
The observable goal is fewer independently authored facts with the same checked
behavior, errors and evidence obligations once normalized.

Do not add tool schema inference, runtime defaults, general manifest inheritance,
new prompt values, implicit `:returns` for raw text, new command result inference,
new CLI switches or Python APIs. Typed `BLOCKED`/`EXHAUSTED` propagation and W1
constructor inference are deferred. Live/frozen DAQv4, experiment fixtures and
existing run artifacts are outside migration scope. No provider experiment is
needed to establish this deterministic frontend contract.

## Decision And Public Forms

### 1. Omit a complete static command argv

Given an external-tool binding named `inspect` with
`stable_command = ["python", "tools/inspect.py", "--json"]`:

```lisp
(command-result inspect :returns Inspection)
(command-result inspect :inputs ((target task.path)) :returns Inspection)
(command-result inspect :inputs () :returns Inspection)
```

Each expands to the corresponding explicit `:argv ("python" "tools/inspect.py"
"--json")` form. The first passes no input-document path; the second appends the
existing runtime-owned document path; the third appends the path of an empty
JSON object. No-input and empty-input modes remain different.

Omission is the author's statement that the binding supplies the **entire static
argv before the optional input-document path**. `stable_command` is otherwise
still a required prefix for explicit argv. The compiler cannot infer a tool's
required flags/arity from that prefix, and does not claim to prove it. Extra
positional or computed arguments continue to use explicit syntax:

```lisp
(command-result inspect
  :argv ("python" "tools/inspect.py" "--json" task.path)
  :returns Inspection)
(command-result normalize
  :adapter normalize_result :inputs ((report task.report)) :returns Summary)
```

Only `ExternalToolBinding` admits omission. Certified adapters still require
their existing explicit `:adapter` route or existing valid explicit argv form;
the shorthand cannot infer adapter mode from binding metadata. No implicit
renaming/alias for repeated command sites is introduced.

The syntax owner accepts the shorter arity, preserves whether `:inputs` exists,
and rejects an explicitly empty `:argv ()`. It can use the existing empty argv
tuple for an unresolved omitted argv when `adapter_name` is absent; this marker
is confined to unchecked elaboration, not a new serialized field. At the current
command typecheck owner, resolve the binding by the same name and producer
environment as explicit calls, replace the tuple with literal string operands,
then use existing argv/input/type/effect checks. Do not thread the command catalog
through all elaboration sessions. Only authored omission may enter resolution:
canonical typed/imported external calls require concrete argv, while certified
calls keep their existing mode. A malformed typed import with empty external argv
must not gain inference. If source-only provenance cannot enforce that boundary,
use a transient omission marker excluded from serialized identity; stop/revise
before changing a persisted/import schema. This is a negative proof obligation.

Generated literals have the invocation's span/form path/expansion provenance.
Their operand-order entry precedes `inputs`; all existing effectful input order
and exactly-once evaluation obligations remain. Explicit forms retain authored
order, including `:inputs` before `:argv`. A shorthand cannot append an empty
document merely because its binding exists.

### 2. Infer a host answer from a typed prompt

```lisp
(defprompt approval-question (:fills (summary :text)) -> Approval
  "Approve this recovery? {summary}")
(request-input (approval-question :summary diagnosis.summary)
  :timeout-sec 86400 :show (diagnosis.report))
(request-input "Approve this recovery?" :returns Approval)
```

At 2.40, resolve the existing direct prompt application before requiring
`:returns`. If its resolved declaration has `return_contract_declared`, use its
canonical, module-qualified answer type to populate the existing
`RequestInputExpr.answer_type_name`. This is `Approval`, not `HostReply[Approval]`.
The normal checker still determines `HostReply[Approval]`, transportability,
fill types, restrictions, timeout/evidence validity and host-input admission.

An explicit `:returns` remains available and must pass the existing prompt/type
compatibility check. A raw string/expression, unresolved prompt, or prompt without
an authored return contract cannot infer an answer; the latter's default `Value`
is not an inference license. An explicitly declared but inadmissible answer such
as `Value` fails normal host-answer checking. No inference from prompt text,
answers, surrounding expected types or runtime dispatch is allowed.

Imported prompt aliases resolve through `PromptCatalog`; copying an unqualified
type spelling into the caller is forbidden. Prompt application navigation stays
on its authored head. The inferred type adds no fictional authored type token
for LSP navigation. Prompt fills, timeout and shown paths keep current evaluation
order and provenance through procedure specialization and typed imports.

### 3. Declare one manifest-wide shared closure

Keep the existing flat command-name map. Add this opt-in envelope:

```json
{
  "$schema": "workflow-command-boundaries.v1",
  "shared_closure": ["tools/common.py", "tools/lib/"],
  "commands": {
    "inspect": {"stable_command": ["python", "tools/inspect.py"], "closure": ["tools/inspect.py"]},
    "summarize": {"stable_command": ["python", "tools/summarize.py"], "closure": ["tools/summarize.py"]}
  }
}
```

All three envelope keys are required; no other envelope keys are accepted.
The exact string discriminator selects this format. Object-valued legacy command
rows named `$schema`, `commands` or `shared_closure` remain ordinary rows; there
are no newly reserved names in a valid flat manifest. A string `$schema` with an
unknown value is an invalid manifest, never an alternate format or fallback.

`shared_closure` is validated by the existing literal-path grammar and applies
unconditionally to **every** row, including unused and certified-adapter rows.
The effective declaration is shared paths plus local `closure` paths; the
existing C2 canonicalizer supplies separator normalization, ordering and dedup.
Within the envelope, omitted local `closure` contributes no extra paths and is
valid because the shared declaration is explicit. Local `[]` also adds nothing;
it does not cancel shared paths. `shared_closure: []` is an explicit empty common
declaration. `null` and invalid paths fail even in unused rows.

There is no override, exclusion, named closure registry, file include, reference,
deep merge or inheritance chain. If a common set is inappropriate for any row,
retain the flat manifest and spell each complete closure. This is deliberately
one group per manifest. Existing programmatic binding APIs continue to accept
only concrete per-binding closures; no envelope object becomes a binding type.

Normalize the envelope once in manifest parsing before constructing bindings.
Retain the raw manifest in existing configuration-read evidence; give the compiler
ordinary bindings with complete closure tuples. Supplied paths remain relative
to the workspace, not the manifest directory. Trusted injected package origins,
manifest overrides and producer-owned imported closures retain current rules.
C1–C5 validation, hashing, mutation checks and interpreter pinning are unchanged.

## Contracts, Diagnostics And Admission

| Input/failure | Required result |
| --- | --- |
| Omitted argv, missing binding | Existing `command_adapter_missing_contract`, located at the command |
| Omitted argv, certified binding without `:adapter` | `command_result_adapter_invalid`; no protocol guessing |
| Explicit empty argv or invalid stable literal command | Existing argv/binding validation refusal; never omission fallback |
| `:adapter` combined with `:argv`, or missing required adapter inputs | Existing `command_result_adapter_invalid` |
| Missing host returns without an explicitly typed resolved prompt | `request_input_keyword_invalid`, stating how to supply a type |
| Explicit host/prompt return mismatch | Existing `request_input_prompt_return_invalid` |
| Invalid inferred host answer / earlier target | Existing host type/target refusal; no historical `HumanReply` fallback |
| Malformed envelope, unknown schema, bad shared/local closure | `command_boundary_manifest_invalid`, naming field/row and manifest |
| Missing closure in legacy flat map | Existing `command_boundary_closure_missing`, including unused rows |

Recommended admission is an additive frontend extension at already admitted
targets 2.35–2.40 for command omission and manifest sugar, with host inference
only at 2.40. **This recommendation requires explicit language-owner ratification
and a normative versioning amendment before implementation admission.** Current
version policy governs syntax/types and does not automatically grant this
exception. No new target number is assigned here. Preserve all existing explicit
forms and definition-origin gates; a newer importing caller cannot reinterpret
older definitions or reopen retired source. If the owner requires a new feature
target, revise this admission contract and its matrix before coding the gates.

## Core, Identity, Persistence And Operations

The graph stays `source/configuration -> existing owner normalization -> typed
program -> WCC -> checked closed program -> evaluated runtime`. There is one
normalizer per authored fact; no normalization in the evaluator, replay, LSP,
launcher or workflow helper. No omission marker, shared-closure reference or
inference flag survives into the checked program or memo.

Compare explicit and shortened forms by resolved command, document presence,
input/result contracts, effect ordering and concrete closure sets. Do **not**
promise byte-identical builds, program IDs, site IDs or cross-build memo reuse:
authored spans, source hashes, raw configuration evidence and compiler identity
can differ. Imported owners keep their captured concrete bindings and qualified
types. Old checked builds are not rewritten; existing pinned-build resume and
divergence rules remain authoritative. Resume must not reread a new manifest to
reconstruct a previously closed command or request.

For equivalent expanded declarations, security authority and runtime work are
unchanged. Shared closure is still an author declaration, not a sandbox or
complete dependency discovery; a broader set can legitimately cause more closure
hashing and more divergence refusals.
No filesystem traversal is added at compile time. LSP uses the same build parser
and typechecker, retains configuration-currentness/restart behavior and authored
diagnostics; this proposal does not qualify the independently open LSP F2 gate.

## Alternatives, Migration And Deletions

Keeping every form explicit avoids implementation work but preserves duplicate
facts. A clean-slate command API carrying a full signature could establish tool
arity, but would add a new contract unrelated to the requested static shorthand.
Runtime defaults would duplicate compiler ownership and make replay dependent
on mutable configuration. None is selected.

Top-level `defaults` in a flat map steals valid command names. Per-row closure
references need lookup, failure and cycle policies; choosing an arbitrary command
as shared owner couples unrelated rows. The discriminated envelope adds one
irreducible format boundary to preserve existing names; one common set avoids
these reference/override mechanisms.

After acceptance, migrate only selected maintained authoring examples whose
static argv, declared prompt return and identical common closure are demonstrable.
Delete their repeated argv/type/closure facts in the same change. Preserve useful
explicit examples and negative tests; do not delete either advanced public form.
Do not reformat manifests to manufacture a reduction. Compare equivalent source
and manifests under the same formatting and report removed facts/duplicated
tokens separately from physical LOC; count the envelope's overhead. No durable
run backfill, automatic source rewrite, compatibility shim or runtime deletion
is required. Rollback expands authoring back to explicit forms and recompiles;
it does not promise reuse of the previous build's identity.

## Evidence, Verification And Acceptance

The implementation must prove the following through public build/run paths with
real compiler, filesystem, checked artifacts and memo; commands may be local
deterministic fixtures and host settlement is local. No providers are needed.

| Obligation | Direct existing test owners / required scenario |
| --- | --- |
| Static argv and input-mode parity | `tests/test_workflow_lisp_command_input_documents.py`, `test_workflow_lisp_closed_input_documents.py`, `test_workflow_evaluated_input_documents.py`: no inputs, empty inputs, populated/effectful inputs, explicit dynamic argv and adapter rejection |
| Shared declaration and old-name compatibility | `tests/test_workflow_lisp_command_boundary_closure.py`, `test_workflow_lisp_closed_program_build.py`, `test_workflow_lisp_closed_program_compile_cli.py`: envelope versus explicitly expanded flat map, unusual legacy names, unused malformed rows, empty/shared/local sets and origins |
| Host inference and producer type ownership | `tests/test_workflow_lisp_host_input.py`: local/aliased prompt, collisions, concrete union/enum/String, untyped/raw refusal, explicit mismatch, specialization and producer-source-free typed capsule |
| Real settlement/replay | `tests/test_workflow_host_input_e2e.py`, `test_workflow_evaluated_host_input_recovery.py`: shorthand request suspends, validates settlement and resumes with the same typed reply without presenting twice |
| Command replay/closure evidence | `tests/test_workflow_evaluated_input_document_replay.py`, `test_workflow_evaluated_closure_evidence.py`: committed command is reused; declared file mutation still refuses; no-input versus empty-document evidence differs |
| Tooling and admission | `tests/test_workflow_lisp_lsp_cli_parity.py`, `test_workflow_lisp_lsp_compile_driver.py`, `test_workflow_lisp_lsp_navigation.py`: same located errors/catalog, configuration invalidation and retained authored prompt head; explicit target matrix |

A public acceptance fixture combines a shared-manifest command and a typed-prompt
host request: compile, run until suspended, settle through the public host API,
then resume. Its command executes once, input-document mode and concrete closure
are visible in checked/effect evidence, and the answer resumes as `HostReply[A]`.
An explicitly expanded sibling has equal semantic projections; identity fields
are reported separately. This crosses the real integration boundaries instead
of invoking a normalizer in isolation. Preserve fail-closed malformed/tampered
checked-program tests and existing restrictions on parallel/child host requests.

Success requires these positive/negative checks, a measured reduction under equal
formatting, updated owning docs/examples and independent review. Existing tests
are evidence of the owners to extend, **not proof that these additions work**.
Tests should assert behavior and lineage, never literal prompt phrasing.

## Handoff, Documentation And Open Decisions

The implementation plan owns task order, bounded consumer selection and fresh
verification commands. Start with admission ratification, then parser/typecheck
normalization and focused tests before selected consumer migration. Source-free
imports, effectful operand order and LSP configuration parsing are required
integration checkpoints. Source changes are expected at the syntax, typecheck
and manifest owners; core/runtime changes require revisiting this design rather
than silently introducing a second execution path.

On acceptance, amend the frontend baseline, command adapter contract, durable host
input design, `docs/lisp_workflow_drafting_guide.md`, normative DSL/IO/versioning
wording and appropriate source/import acceptance coverage. Route this proposal
and its plan through the documentation/design indices and capability matrix
without labeling them current or implemented. State/CLI changes are unnecessary
unless review finds an actual behavioral delta beyond the stated normalization.

Two prerequisites remain explicit: the language owner must decide version
admission, and implementation must demonstrate canonical qualified prompt types
and complete command operands across typed imports without caller rebinding.
The source owners above make that feasible but inspection is not an executable
proof. Stop/revise if either needs a runtime protocol, new artifact schema,
hidden argument inference, inheritance machinery, weakened closure validation,
changed effect order or unqualified cross-build resume. Broader syntax and all
deferred features require separate design selection.
