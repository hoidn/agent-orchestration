# Workflow Lisp Frontend Deduplication

- **Status:** incorporated into the current contracts; companion decision record
- **Kind:** frontend authoring decisions and scope
- **Owner:** Workflow Lisp frontend maintainers
- **Created / last material update:** 2026-10-26
- **Delivery:** [implementation plan and ledger](../plans/2026-10-26-frontend-deduplication-plan.md)
- **Evidence:** [verification and size report](../reports/2026-10-26-frontend-deduplication-verification.md)

The current [frontend baseline](workflow_lisp_frontend_specification.md#23-command-result),
[command boundary contract](workflow_command_adapter_contract.md#static-command-argv)
and [durable host-input contract](workflow_lisp_durable_host_input.md) own the
supported syntax, validation and import rules. [DSL](../../specs/dsl.md),
[IO](../../specs/io.md) and [versioning](../../specs/versioning.md) own normative
admission and transport. This record explains the bounded choices; it is not a
replacement contract or a selector for further implementation.

## Decisions

Remove three repeated facts from authoring:

1. At targets 2.35–2.40, a command with neither `:argv` nor `:adapter` uses its
   external-tool binding's complete literal `stable_command`. Additional or
   dynamic arguments retain explicit argv. `:returns` remains required.
2. At 2.40, a direct, fully applied prompt with an explicitly declared answer
   contract supplies omitted host-input `:returns`. Raw questions and prompts
   with implicit returns still declare it. Canonical producer type ownership
   survives aliases, specialization and typed imports.
3. At targets 2.35–2.40, an opt-in discriminated manifest envelope supplies one
   shared closure plus each row's local files. Flat maps remain first-class.
   Local omission or `[]` adds no paths and cannot subtract shared paths.

These are additive source/configuration forms. They introduce no target number,
state schema, runtime protocol or interpretation change for existing explicit
forms. Definition-origin admission and the source floor remain in force.

## Normalization ownership

The graph is `source/configuration -> existing frontend owner -> concrete typed
program/bindings -> WCC -> checked closed program -> evaluated runtime`.

- `expressions.py::_elaborate_request_input` resolves the declared prompt type;
  the ordinary checker validates answer transport and explicit mismatches.
- `typecheck_effects.py::typecheck_command_result_expr` resolves literal argv
  in the existing command-boundary environment. Typed imports require concrete
  operands and retain producer argv, closure and policy. Malformed imports
  cannot acquire consumer inference. The typed match-subject path preserves
  materialized operands through nested calls.
- `build_manifest_io.py::_parse_command_boundaries_manifest` expands common
  plus local paths into ordinary bindings, while preserving raw configuration
  capture. Existing closure canonicalization, validation and runtime evidence
  owners continue to apply to every row.

Paths above are under `orchestrator/workflow_lisp/`. No omission marker, shared
reference or inference flag reaches the checked program or memo. Existing
input-document presence, structural operand order, effect identity, host
settlement and command recovery rules retain their owners.

## Why these bounds

Using the binding avoids another argv resolver or a tool schema. It cannot
prove a tool's required flags or argument count. Certified adapters retain
their explicit route; binding metadata does not guess a transport mode.

Using the declared prompt type avoids inference from text, runtime answers or
surrounding expected types. Canonical ownership prevents caller-local names
from capturing imported answer types. The ordinary host transport checker
continues to reject inadmissible types.

A string `$schema` discriminator preserves valid object-valued flat commands
named `$schema`, `shared_closure` or `commands`. One common set avoids reference,
cycle, override and exclusion policies. A broader common set can increase
runtime hashing and divergence refusals; a flat map expresses independent sets.
Closure declarations remain author claims, not dependency discovery or a sandbox.

This design makes per-command exclusions, tool-specific arity inference and
dynamic prompt dispatch harder to add. No machinery anticipates them. Typed
failure propagation, W1 constructor shorthand, command-return inference, generic
manifest inheritance, automatic rewriting and Python API changes remain outside
this scope.

## Migration and evidence limits

Migrate only selected maintained examples with demonstrably repeated facts.
Keep explicit dynamic argv and raw-question examples. Preserve historical
fixtures, frozen runs and the live DAQ workspace. Measure source and configuration
under identical formatting and include unchanged helpers; the envelope overhead
can outweigh small manifests' line savings.

Compare normalized commands, document modes, typed results, effect order and
closure sets. Whole artifacts and build keys can differ because authored
locations, source bytes and raw configuration remain captured. Equal semantic
projections do not establish cross-build or cross-package resume compatibility.
Public CLI `resume` still rebuilds from the recorded source/configuration recipe
for currentness checks before using retained authority; source deletion is not
a public resume guarantee. Producer-source-free typed import is a separate
compiler boundary.

The companion plan and report own observed tests, measurements, independent
reviews and remaining integration gates. Deterministic compile/behavior/size
evidence establishes these forms' scope; it makes no comparative quality claim
and selects no provider experiment or LangGraph rejudging.
