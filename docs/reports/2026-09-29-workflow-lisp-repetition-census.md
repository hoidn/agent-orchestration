# Repetition In Workflow Lisp Programs: Census And Measurement

- **Status:** evidence record. It measures; it proposes nothing. The design
  that uses it is
  [Writing Each Fact Once](../design/workflow_lisp_write_once.md).
- **Date and code:** 2026-09-29. The census and the rewrite used the branch
  `feat/orc-shared-defect-repairs` at `c6fbe32a`, which is `main` at
  `5c88cd2d` plus the compiler repairs of the
  [shared defect repairs plan](../plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md).
- **Scripts and measured programs:** `experiments/orc_repetition_census/`.

## 1. Questions

1. Does the helper `std/improve`, with its generic union types, make a real
   workflow shorter or reduce its type declarations?
2. Where do `.orc` programs repeat a fact that is already stated elsewhere?

## 2. Corpus

Twenty-four files, 2,847 code lines. A code line is a non-blank line that is
not only a comment.

| Group | Files | Code lines |
| --- | ---: | ---: |
| `workflows/examples/` | 11 | 1,073 |
| `workflows/library/`, without `lisp_frontend_design_delta` | 6 | 797 |
| `experiments/orc_vs_single_call/workflows/` | 2 | 155 |
| `orchestrator/workflow_lisp/stdlib_modules/` | 5 | 822 |

Test fixtures are excluded. The Design Delta family is excluded because the
owner considers it deprecated.

## 3. Rewrite Of One Workflow With `std/improve`

`experiments/orc_vs_single_call/workflows/reviewed_change.orc` was rewritten
for target 2.33 in three variants. Each passes `--dry-run`; none was run
beyond that.

| Category | Hand-written loop, direct style (C) | With `std/improve` (B) |
| --- | ---: | ---: |
| Header and imports | 6 | 7 |
| Type declarations | 16 | 21 |
| Prompt declarations | 16 | 16 |
| Procedures and workflows | 54 | 49 |
| **Total** | **92** | **93** |

The helper does not reduce type declarations and does not shorten the
program.

| The helper removes | Lines | The helper adds | Lines |
| --- | ---: | --- | ---: |
| Two union declarations | 9 | Three records, one per type parameter (`S`, `I`, `F`) | 14 |
| Loop mechanics and five constructors | 5 | Three hook headers with `:effects` and `:lowering` | 9 |
| | | A procedure split in two, because a nested `if` in a hook is rejected | 4 |
| | | The import | 1 |

Other results:

- The compiler repairs save no line on the helper route and one line on the
  hand-written route.
- Mapping the helper's result into the workflow's own outcome union is
  rejected by the pure-result replay index, so the helper variant returns
  `Improvement[Draft Verdict String]`.
- Hook signatures restate `S`, `I` and `F` eleven times.
- The variant written in the bound style (A) has the same text as B.

The variants are in `experiments/orc_repetition_census/variants/`, stored as
`.orc.txt`.

## 4. Census

### 4.1 Lines by top-level form

| Form | Lines | Share |
| --- | ---: | ---: |
| `defworkflow` | 1,000 | 35.1 % |
| `defproc` | 683 | 24.0 % |
| `defrecord` | 308 | 10.8 % |
| `defpath` | 228 | 8.0 % |
| `defunion` | 188 | 6.6 % |
| Header and imports | 183 | 6.4 % |
| Other (`defmacro`, `defresource`, `deftransition`) | 123 | 4.3 % |
| `defenum` | 96 | 3.4 % |
| `defprompt` | 38 | 1.3 % |

Type declarations are 820 lines, 28.8 % of the corpus.

### 4.2 Declarations repeated across files

A declaration repeats when its name is also declared in another corpus file.

| Kind | Declarations | Repeats | Repeats with identical text | Lines in repeats |
| --- | ---: | ---: | ---: | ---: |
| `defpath` | 66 | 33 | 27 | 129 |
| `defrecord` | 79 | 13 | 12 | 45 |
| `defenum` | 32 | 11 | 1 | 49 |
| `defunion` | 24 | 4 | 4 | 30 |
| **Total** | **201** | **61** | **44** | **253** |

The repeats occupy 8.9 % of the corpus and 30.9 % of the type declaration
lines.

| Name | Files | Identical |
| --- | ---: | --- |
| `defpath DesignDocPath` | 7 | No |
| `defenum BlockerClass` | 7 | No |
| `defpath ReviewReportPath` | 6 | Yes |
| `defpath WorkReport` | 6 | Yes |
| `defenum ReviewDecision` | 5 | No |
| `defpath ReviewReportTarget` | 5 | Yes |
| `defpath PlanDocPath` | 4 | Yes |
| `defrecord RunCtx`, `defrecord PhaseCtx` | 3 each | Yes |

Declarations can be imported. `std/phase` exports `ReviewReportPath`, one
example imports it, and five files declare it again with the same text.

### 4.3 Constructors

| Measure | Value |
| --- | ---: |
| Constructor sites, `(record T …)` and `(variant U V …)` | 105 |
| Sites where a declaration fixes the expected type | 76 (72 %) |
| Sites that today's typechecker reaches with an expected type | 16 |
| Characters of type name written in constructors | 2,183 |
| Of those, at sites where a declaration fixes the type | 1,583 |
| Variant constructor sites whose tag is declared by more than one visible union | 13 of 33 |

The typechecker passes an expected type to procedure and workflow tails,
constructor fields, call arguments and the arms of `match`, `if` and `cond`.
It drops it at `let*` bodies, `with-phase` bodies, `done`, `continue`,
`:on-exhausted`, loop state and the arguments of generic calls. Only the
empty `(list)` uses it to decide its type.

### 4.4 Annotations

| Annotation | Count | Lines | Note |
| --- | ---: | ---: | --- |
| `:effects` | 24, on every `defproc` | 27 | 7 are empty. The compiler requires the clause and requires it to equal the inferred set |
| `:lowering` | 24 | 24 | 22 `inline`, 2 `auto`. Optional. The default `auto` may choose a private workflow when a procedure has several call sites, so `inline` records a choice |
| `:where` | 4 | | 26 constraints |
| `:forall` | 6 | | |

### 4.5 Bindings that look forced by a compiler limit

Twenty-three `let*` bindings are used once, in the next form, as a `match`
subject (19) or inside `loop-state` (4).

### 4.6 Provider call options

| Measure | Value |
| --- | ---: |
| `provider-result` calls | 49 |
| Calls that set `:model`, `:effort` or `:timeout-sec` | 20 |
| Files that repeat one option value on every call | 5 |

`reviewed_change.orc` calls `providers.coder` three times with the same three
options: nine lines.

### 4.7 Review decision unions

Thirteen declarations of ten names. Three unions are declared twice with the
same variants and fields, once in an example and once in a library file. The
approval variant is `APPROVE` in decisions and `APPROVED` in loop results. The
request for changes is `REVISE` in five unions and `REQUEST_CHANGES` in one.
The blocking variant is `BLOCK` in one union and `BLOCKED` in the others.

## 5. Facts About The Compiler

| Fact | Evidence |
| --- | --- |
| No document gives a reason for the rule that a constructor names its type | `workflow_lisp_parametric_type_system.md:368-370`, `workflow_lisp_frontend_specification.md:1188-1200` |
| `(record :k v)` and `(variant TAG :k v)` are parse errors in expression position today | `expressions.py:3009`, `:3574` |
| `(record :key value)` exists inside `trial` sections as untyped data | `expressions.py:2178` |
| A bare variant name is already resolved from context in `match` patterns and in `=` comparisons | `typecheck_proofs.py:388`, `typecheck_pure_ops.py:23-71` |
| A caller-owned union satisfies a hook result constrained with `:where (D has-union-variant …)` | compiled probe |
| A type parameter that appears only in a constraint cannot be bound | `procedure_type_param_unbindable` |
| `let-proc` defines one local procedure with explicit captures; nested and multiple bindings are excluded | `workflow_lisp_let_proc_local_proc_refs.md` §7, §9, §10 |
| `bind-proc` applies a procedure partially, by keyword | drafting guide, ProcRef tranche |
| Neither `let-proc` nor `bind-proc` is used in the corpus | search |
| `improve` compiles with `I` bound to `String` and with `F` and `B` bound to `String` | compiled probes |
| A provider externs file maps a name to a provider template and carries no options | `reviewed_change.providers.json` |

## 6. Limits

- One workflow was rewritten. Another workflow may gain or lose differently.
- The variants were compiled, not run.
- The position of each constructor site was classified by a script that knows
  only the forms in this corpus.
- "Reached by an expected type today" comes from reading the typechecker, not
  from a measurement per site.
- Line counts depend on layout. All variants keep the layout of the original.

## 7. Reproducing

From the repository root:

```bash
python experiments/orc_repetition_census/declaration_repeats.py .
PYTHONPATH=$PWD python experiments/orc_repetition_census/census.py
python experiments/orc_repetition_census/summarize.py
python experiments/orc_repetition_census/count_lines.py <file.orc>
```

`census.py` writes `census.json` beside itself; `summarize.py` prints the
tables of section 4 from it.
