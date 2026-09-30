# Workflow Lisp Numeric Surface

## Metadata

- **Status:** proposed target; not implemented and not current syntax
- **Kind:** pure expression surface and boundary contract
- **Owner:** Workflow Lisp frontend; pure expression catalog
- **Created:** 2026-09-29
- **Evidence:** [execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md),
  section E
- **Plan:** [evaluated execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md),
  Phase 0
- **Amends on acceptance:**
  [expression surface and adapter retirement](workflow_lisp_generic_core_expression_surface_adapter_retirement.md)
  §10.2, the drafting guide's section on pure expressions,
  `specs/io.md`, `specs/versioning.md`
- **Related:** [evaluated execution](workflow_lisp_evaluated_execution.md)

## 1. Summary

A workflow can compare two `Float` values and cannot compute with them. It
cannot divide, and it cannot write a decimal constant in an expression. A
selection policy that scores candidates therefore has to leave the language.

This design adds a closed decimal arithmetic. It has four parts.

| Part | Statement |
| --- | --- |
| Literals | A decimal literal is an expression wherever an expression is admitted |
| Arithmetic | `+`, `-`, `*`, `/`, `min`, `max` over `Float`; square root, natural logarithm, absolute value |
| Conversion | Explicit, between `Int` and `Float`. Nothing converts silently |
| Finite values | A `Float` is always finite. An operation or a boundary that would produce another value refuses |

## 2. What Exists

| Fact | Source |
| --- | --- |
| `+`, `-`, `*`, `min`, `max` accept `Int` only. Overflow of 64 bits fails closed | `orchestrator/workflow/pure_expr.py` |
| `<`, `<=`, `>`, `>=` accept `Float` on both sides. `=` and `!=` refuse `Float` | same |
| No operator converts between `Int`, `Float` and `String` | same |
| A decimal literal is accepted only as the default of a workflow parameter. No document gives a reason; the guard replaced a crash | `orchestrator/workflow_lisp/expressions.py` |
| The reader accepts no exponent | `orchestrator/workflow_lisp/reader.py` |
| `NaN` and infinity are accepted in workflow inputs and in result fields of type `float`, and are written to `state.json` as the token `NaN` | `orchestrator/contracts/output_contract.py`, `orchestrator/state.py` |
| Canonical JSON refuses `NaN` with an uncaught exception | `orchestrator/workflow/pure_expr.py` |
| The type rules of operators are written in four places | execution facts, E.1 |

## 3. Rules

### N1. Literals

```text
literal := sign? digits "." digits? exponent?
         | sign? "." digits exponent?
         | sign? digits exponent
exponent := ("e" | "E") sign? digits
```

`1.5`, `-0.25`, `2e-3` and `1.0E6` are literals. There is no literal for
infinity or for a value that is not a number. A literal whose value does not
fit a finite double is refused when the program is read.

### N2. Arithmetic

| Operator | Operands | Result | Arity |
| --- | --- | --- | --- |
| `+`, `*` | all `Int`, or all `Float` | same type | two or more |
| `-` | both `Int`, or both `Float` | same type | two |
| `/` | both `Float` | `Float` | two |
| `int/div`, `int/mod` | both `Int` | `Int` | two |
| `min`, `max` | all `Int`, or all `Float` | same type | two or more |
| `float/abs`, `float/sqrt`, `float/log` | one `Float` | `Float` | one |

`int/div` rounds toward negative infinity, and `int/mod` has the sign of the
divisor, so that `(+ (* (int/div a b) b) (int/mod a b))` equals `a`.
`float/log` is the natural logarithm.

Operands of different types are refused at compile time. No operand is
converted.

### N3. Conversion

| Operator | From | To | Refuses |
| --- | --- | --- | --- |
| `int/to-float` | `Int` | `Float` | never; the result is the nearest double |
| `float/floor` | `Float` | `Int` | a result outside 64 bits |
| `float/round` | `Float` | `Int` | a result outside 64 bits. Halves round to the even integer |

### N4. Refusals

Every refusal names the operator, prints the operands and points at the
expression.

| Code | When |
| --- | --- |
| `pure_expr_division_by_zero` | `/`, `int/div` or `int/mod` with a zero divisor |
| `pure_expr_float_domain` | `float/sqrt` of a negative value; `float/log` of zero or a negative value |
| `pure_expr_float_not_finite` | a result that is infinite or not a number |
| `pure_expr_overflow` | an `Int` result outside 64 bits, as today |

An expression made only of literals is evaluated when the program is
compiled, and its refusal is a compile error.

### N5. Equality

`=` and `!=` stay refused for `Float`. A workflow compares with an ordering.

### N6. Boundaries

A `Float` that enters a run is finite. The rule applies to workflow inputs,
to fields of command and provider results, and to expected output files.

| Input | Result |
| --- | --- |
| `NaN`, `Infinity`, `-Infinity` as JSON tokens | refused |
| `"nan"`, `"inf"` as strings where a `Float` is expected | refused |
| A number too large for a double, such as `1e400` | refused |

The code is `float_not_finite`. The diagnostic names the field.

### N7. Identity And Serialization

- A `Float` is written as the shortest decimal that reads back as the same
  double. No file of a run contains the token `NaN`.
- `+`, `-`, `*`, `/` and `float/sqrt` give the same double on every platform.
  `float/log` may differ in the last unit between mathematical libraries.
- For that reason a `Float` enters a digest rounded to 15 significant decimal
  digits. The value an effect receives is not rounded.

### N8. One Implementation

The catalog of `orchestrator/workflow/pure_expr.py` defines each operator
once: its name, the types it accepts, its result type and its evaluation. The
typechecker, the compiler and the runtime read the catalog.

## 4. Why These Operators

The accepted rule for the pure surface is that it grows when a fixture needs
an operator that the surface cannot express.

The fixture is the selection rule of an evolutionary search. It scores a
branch by its mean result and by how seldom the branch was tried:

```lisp
(defun branch-score ((total Float) (visits Int) (all-visits Int) (weight Float)) -> Float
  (+ (/ total (int/to-float visits))
     (* weight
        (float/sqrt (/ (float/log (int/to-float all-visits))
                       (int/to-float visits))))))
```

It needs division, square root, logarithm and conversion from `Int`. It needs
nothing else.

## 5. Not Included

Exponential and power functions, trigonometry, equality of `Float`, implicit
conversion, random numbers, time, and formatting of numbers as text. Each
waits for a fixture that needs it.

## 6. Targets And Compatibility

- The rules apply from one new target, the same that carries the surface
  changes of [writing each fact once](workflow_lisp_write_once.md).
- Targets that exist today keep their behaviour. They refuse a decimal
  literal in an expression and they accept non-finite values at boundaries,
  as they do now.
- The pure evaluator is shared by both execution routes, so the operators do
  not depend on evaluated execution.

## 7. Evidence Requirements

| Requirement | Measure |
| --- | --- |
| Literals | A literal compiles and runs in each position of the totality matrix |
| Operators | For each operator: a result, each refusal, and the same refusal at compile time for literal operands |
| Agreement | For every program of the tests, the type the compiler assigns equals the type the evaluator produces |
| Boundaries | Each row of N6, for a workflow input, a command result, a provider result and an expected output file |
| The fixture | The search controller, with selection by the rule of section 4, makes the decisions of its Python reference |
| Older targets | Byte-identical build artifacts; the refusals of today |

## 8. Feasibility Obligations

| Claim | Fixture |
| --- | --- |
| One catalog can serve the four places that hold type rules today | The frontend check, the static typing of payloads and the evaluator give the same answer on a generated set of well-typed and ill-typed applications |
| Rounding to 15 digits in digests does not make two different inputs equal in practice | The digests of the controller's inputs over a full search are pairwise distinct wherever the inputs differ |
| Refusing non-finite values at boundaries breaks no maintained workflow | No workflow of the repetition census corpus receives such a value in its tests |
