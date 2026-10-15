# Workflow Lisp Provider Call Policy

Status: current component contract. The [frontend](workflow_lisp_frontend_specification.md)
owns syntax/types; [provider specification](../../specs/providers.md) owns
registry validation and invocation; [evaluated execution](workflow_lisp_evaluated_execution.md)
owns checked-effect identity and recovery. The original [design and delivery
record](../plans/2026-07-17-workflow-lisp-provider-call-policy-design.md) preserves
rollout, argv comparisons and old representation contracts.

## Policy Is Data On An Explicit Provider Call

The typed `provider-result` surface accepts optional `:model`, `:effort` and
`:timeout-sec` policy. Model and effort are effect-free values of exactly
`String`; no coercion or provider effect may produce them. The frontend's
inline-lowerability rules remain applicable: accepted literal/name/reference/
projection operands do not imply arbitrary computed expressions are admitted.
Unsupported operands fail the frontend with
`provider_result_policy_operand_not_inline_lowerable`; this component introduces
no hidden materialization step.

Timeout is a positive `Int` literal. Boolean, float, string, non-positive and
dynamic timeout operands are rejected. Existing provider timeout behavior,
including exit 124, is unchanged. Empty strings do not introduce a language-level
model/effort vocabulary; provider validation still decides admissible values.
Absence of an option preserves provider defaults rather than synthesizing a new
value. Source-level syntax admitted by an older header does not admit that
header's retired executable target.

Provider identity is the compiler-known extern named by the call. Canonical
policy does not choose a provider family, change its trust lane, expand a model's
capabilities or override isolation. Unsupported canonical options fail before
provider invocation. An unrestricted provider profile is still an explicit
trusted choice, subject to [security](../../specs/security.md).

## Declarative Registry Binding

`CallPolicyBinding` maps the closed canonical keys `model` and `effort` onto
existing provider-template parameters. A target parameter uses the existing bare
identifier grammar, is not `PROMPT`, `SESSION_ID` or another reserved parameter,
and is unique across bindings. Optional argv fragments are registry data, not
provider-name dispatch in the runtime.

Every applicable base, fresh and resume command must consume its binding exactly
once. Without a fragment, the base command has exactly one target placeholder.
With a fragment, the base has none and the fragment has exactly one own target
placeholder and no other dynamic parameter. Normal placeholder escaping/counting
rules apply. Registry validation covers built-ins and custom templates; declaring
a binding is not authority to run a retired resume command.

There is one merge and substitution path:

1. Start with template defaults.
2. Overlay native provider parameters.
3. Overlay the authored canonical policy through its declared bindings.
4. Substitute once and append any present optional fragments in canonical
   `model`, then `effort` order.

Absent policy does not append an optional fragment. Existing template defaults
still apply. Codex maps canonical effort to `reasoning_effort`; Claude's optional
`--effort` fragment is present only when authored. These are declarative binding
examples, not hidden branches by provider family or name. No second substitution
pass reinterprets authored strings.

## Evaluated Execution And Delivery

`orchestrator/workflow/evaluated/providers.py::_prepare_provider_invocation`
forwards `resolved.policy` timeout/model/effort into shared `ProviderExecutor`
preparation. Checked-program policy participates in program/input-digest
consistency and memo input parts. E2 effect identity remains the checked site
and activation path; policy does not mint a new effect identity. These inputs
are not reconstructed from an old flat step or checkpoint schema. Retry/recovery and input divergence use the evaluated owners, not a
second policy-specific persistence path.

The selected provider transport and [result-delivery contract](provider_result_delivery.md)
remain independent of policy. Runtime composition supplies transport instructions
and the output contract exactly once. Authored prompts do not carry delivery
workarounds. Policy does not admit phased delivery, scaffold creation, native
continuation or old target execution by implication.

## Compatibility Boundary And Limits

Retained readers, versioned syntax/type checks and imports keep their own
qualification. Historical WCC/Core/executable-IR fields, byte-identical flat argv
controls and old checkpoint guards are retained in the source record as historical
contracts; they are not evaluated runtime schemas. The
[CLI support boundary](../../specs/cli.md#executable-support-boundary) governs
execution independently. This contract selects no new provider, option,
qualification run or stage-entry gate.
