# Two contracts, in ORC and in Python

The useful comparison is what connects an agent's instructions to the values
and files a workflow can trust. These two conceptual showcases make that
connection visible: a typed review result, then a prompt signature that also
owns document delivery and a report postcondition.

The first example includes a complete workflow body and its Python counterpart;
provider configuration, transport, and shared application handlers are supplied
separately. The later snippets are conceptual fragments. These examples explain
the authoring model, not full runtime equivalence or benchmark results. Both
languages use a reusable provider transport, which is assumed rather than
implemented or counted here. There is no general claim that ORC needs fewer
lines or offers more reuse than Python.

## 1. One result declaration, from agent instructions to routing

A reviewer either approves a draft with notes or requests revision with a
list of findings. In ORC, the workflow declares that distinction as a union
and returns the validated result:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule review)
  (export run)

  (defunion Review
    (APPROVE (notes String))
    (REVISE (findings List[String])))

  (defprompt review-prompt
    (:fills (draft :text))
    -> Review
    "Review correctness. APPROVE if there are no blocking defects; otherwise REVISE with actionable findings. Draft: {draft}")

  (defworkflow run ((draft String)) -> Review
    (provider-result providers.reviewer
      :prompt (review-prompt :draft draft))))
```

The prompt describes **how to judge** the draft. It does not manually describe
the JSON structure: `-> Review` determines the output contract delivered to
the agent and enforced by the runtime. When the call succeeds, its consumer
receives a variant of `Review`, not a dictionary awaiting validation:

1. The runtime adds output instructions describing the allowed variants,
   their fields and field types, and where to write the structured result.
2. The structured result file is parsed and validated before it becomes a
   workflow value. Invalid output fails that boundary.
3. Consumers can branch on a typed value. Before execution, the compiler
   checks field access and requires each `match` to cover every variant.

An existing external prompt can use the same result boundary with
`(provider-result providers.review :prompt prompts.review :inputs (draft)
:returns Review)`. With a `defprompt` application, the declaration owns the
result contract: adding a separate call-site `:returns` is refused.

Here are concrete structured answers and their consequences:

| Agent answer | Result |
| --- | --- |
| `{"variant":"APPROVE","notes":"Ready to publish"}` | `accept` receives a string. |
| `{"variant":"REVISE","findings":["Define the failure policy"]}` | `revise` receives a list of strings. |
| `{"variant":"MAYBE","notes":"Unsure"}` | Undeclared variant; reject. |
| `{"variant":"APPROVE"}` | Required field missing; reject. |
| `{"variant":"APPROVE","notes":7}` | Wrong field type; reject. |
| `{"variant":"REVISE","findings":"Please improve the tests"}` | A string is not a list of strings; reject. |
| `{"variant":"REVISE","findings":["Clarify retries",7]}` | Wrong list element type; reject. |
| `{"variant":"APPROVE","notes":"Fine","findings":[]}` | Field belonging to the inactive variant; reject. |

Malformed JSON is also rejected. At the current target-2.34-and-earlier
`variant_output` boundary, unrelated unknown keys are ignored: an additional
`"debug":"x"` is not the same as including the other variant's `findings`.
This is validation of the declared union, not a promise to reject every extra
JSON key.

**Python with the standard library: declare the types, describe the format,
and write the validator.** `run_agent(prompt)` represents the reusable
transport: it returns the path of the structured result file. No journal,
subprocess launcher, or provider client belongs in this comparison:

```python
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Approved:
    notes: str


@dataclass(frozen=True)
class RevisionRequested:
    findings: list[str]


Review = Approved | RevisionRequested

OUTPUT_CONTRACT = """
Write one JSON object to the result file, using either:
{"variant": "APPROVE", "notes": "Explanation"}
or:
{"variant": "REVISE", "findings": ["First finding", "Second finding"]}
For APPROVE, notes is a required string and findings is forbidden.
For REVISE, findings is a required list of strings and notes is forbidden.
"""


def review_draft(
    draft: str, run_agent: Callable[[str], Path]
) -> Review:
    prompt = (
        "Review correctness. APPROVE if there are no blocking defects; "
        "otherwise REVISE with actionable findings. Draft: "
        + draft + "\n" + OUTPUT_CONTRACT
    )
    bundle = run_agent(prompt)
    result = json.loads(bundle.read_text(encoding="utf-8"))

    if not isinstance(result, dict):
        raise ValueError("Expected a review object")

    if result.get("variant") == "APPROVE":
        if "findings" in result:
            raise ValueError("APPROVE cannot contain findings")
        notes = result.get("notes")
        if not isinstance(notes, str):
            raise ValueError("APPROVE requires string notes")
        return Approved(notes)

    if result.get("variant") == "REVISE":
        if "notes" in result:
            raise ValueError("REVISE cannot contain notes")
        findings = result.get("findings")
        if not isinstance(findings, list):
            raise ValueError("REVISE requires a findings list")
        if not all(isinstance(item, str) for item in findings):
            raise ValueError("Every finding must be a string")
        return RevisionRequested(findings)

    raise ValueError("Unknown or missing review variant")
```

Annotations and dataclasses do not automatically validate external JSON.
The explicit checks above establish the types promised by the constructed
objects. This validator handles the cases in the table and permits unrelated
extra keys, matching the stated boundary.

**After that boundary, consuming the result is simple in both languages.**
Suppose `accept` and `revise` are application operations with the appropriate
argument types and a common result type. The conceptual ORC consumer is:

```lisp
(match result
  ((APPROVE a) (accept a.notes))
  ((REVISE r)  (revise r.findings)))
```

The Python consumer also uses typed variants, with no further JSON validation:

```python
match result:
    case Approved(notes):
        accept(notes)
    case RevisionRequested(findings):
        revise(findings)
```

The difference appears when the contract changes. Suppose a reviewer can
also return `BLOCKED(reason String)`:

| What changes? | ORC declaration | Manual Python baseline |
| --- | --- | --- |
| Tell the agent about `BLOCKED` | Add the union variant; generated output instructions follow. | Update `OUTPUT_CONTRACT`. |
| Validate the new result | The same union drives the runtime contract. | Add the dataclass to `Review` and extend `review_draft`, including the inactive-field rules. |
| Consume the new result | Add a `match` arm; incomplete coverage is a compile error. | Add a case; plain Python permits an unmatched value to fall through. A type checker can enforce exhaustive handling when configured or used with `assert_never`. |
| Change a field's type | Update the union; validation and typed consumers follow. | Update the dataclass, instructions, decoder, and affected consumers. |

### The same result with Pydantic AI

The manual Python version has several representations to keep aligned.
[Pydantic AI](https://pydantic.dev/docs/ai/core-concepts/output/) already derives
schemas and validation from output types and exposes typed results. Replace
the dataclasses and handwritten decoder above with Pydantic models:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent


class Approved(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    variant: Literal["APPROVE"]
    notes: str


class RevisionRequested(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    variant: Literal["REVISE"]
    findings: list[str]


Review = Approved | RevisionRequested

reviewer = Agent[None, Review](
    model,
    output_type=[Approved, RevisionRequested],
    tools=workspace_tools,
)


async def review_draft(draft: str) -> Review:
    result = await reviewer.run(
        "Review correctness. APPROVE if there are no blocking defects; "
        "otherwise REVISE with actionable findings. Draft: " + draft
    )
    return result.output
```

`model` and `workspace_tools` stand for shared provider and file-tool
configuration, also needed by the ORC provider; the file tools are used by
the second example. Pydantic AI handles structured output without a manual
`OUTPUT_CONTRACT` or JSON decoder. Its default output-tool transport differs
from ORC's result-file transport, so this compares authoring responsibilities,
not identical wire protocols or retry behavior. The explicit
[`extra="forbid"`](https://pydantic.dev/docs/validation/latest/concepts/models/#extra-data)
policy rejects all extra fields, including unrelated ones that the ORC
boundary above ignores.

Pydantic model consumers use keyword class patterns:

```python
match result:
    case Approved(notes=notes):
        accept(notes)
    case RevisionRequested(findings=findings):
        revise(findings)
```

For structured responses alone, this version is not meaningfully inferior
to ORC. Both derive validation from types and deliver typed values. The next
example shows the more specific difference in prompt and file contracts.

## 2. One prompt signature, from typed inputs to a required report

Now review a design document against a list of checks, write a human-readable
report, and return the same structured decision. ORC gives the three inputs
different delivery roles:

```lisp
(defpath DesignDoc
  :kind relpath :under "docs" :must-exist true)
(defpath ReportTarget
  :kind relpath :under "artifacts/review" :must-exist false)

(defprompt review-design
  (:fills
    (doc :doc DesignDoc)
    (checks :value List[String])
    (report :path :out ReportTarget))
  -> Review
  "Review the injected design against these checks: {checks}\nWrite your review report to {report}.")

(provider-result providers.review
  :prompt
    (review-design
      :doc design_path
      :checks checks
      :report report_path))
```

`design_path`, `checks`, and `report_path` are surrounding typed inputs. The
same declaration tells the compiler and runtime how to prepare the prompt,
what to validate afterward, and which structured value the caller receives:

| Signature entry | Provider context | Enforced contract |
| --- | --- | --- |
| `doc :doc DesignDoc` | Existing document content is prepended through the document-dependency lane; no `{doc}` placeholder is used. | A required workspace-relative document satisfying the path contract. |
| `checks :value List[String]` | The list is rendered as canonical JSON at `{checks}`. | The fill has the declared supported type. |
| `report :path :out ReportTarget` | `{report}` renders the destination as a POSIX path reference. | The same resolved destination must contain one UTF-8 file after a successful provider attempt. |
| `-> Review` | Generated instructions request the structured review result. | Parse and validate the union before returning it. |

The report destination is filled once. It supplies both the path shown to
the agent and the required-file postcondition, so the author cannot quietly
change one while leaving the other behind. Unknown, missing, duplicate, or
mistyped fills are compiler errors; a fragment call cannot override its
signature with parallel `:inputs`, `:prompt-dependencies`, or `:returns`.

The report and structured result are checked together: if either fails, the
step exposes neither artifact mapping. Files the provider wrote are not
rolled back. `Review` remains the decision authority; the report is for a
reader, not something the workflow parses to discover the verdict.

### Python with Pydantic AI and a required report

Reuse the Pydantic AI `reviewer` above. A small wrapper connects document
delivery, the requested destination, and the required report:

```python
import json
from pathlib import Path


async def review_design(
    doc: Path, checks: list[str], report: Path
) -> Review:
    doc = checked_path(doc, under="docs", must_exist=True)
    report = checked_path(
        report, under="artifacts/review", must_exist=False
    )

    prompt = (
        f"Review this design:\n{doc.read_text(encoding='utf-8')}\n"
        f"Against these checks: {json.dumps(checks)}\n"
        f"Write your review report to {report.as_posix()}."
    )
    decision = (await reviewer.run(prompt)).output

    # A valid Review is insufficient: the requested report must exist.
    report.read_text(encoding="utf-8")
    return decision
```

`checked_path` is an assumed reusable application helper, not a Pydantic AI
API: it enforces workspace-relative paths and the stated containment and
existence constraints. Both the wrapper and the agent's file tools use that
same workspace. Reading the report rejects a missing file, a directory, or
invalid UTF-8 before returning the decision to the wrapper's caller.
Pydantic AI still validates `Review`; no manual response parser is needed.
The file check could instead live in an
[`output_validator`](https://pydantic.dev/docs/ai/core-concepts/output/#output-validators)
using the destination from dependencies. That is another way to connect the
same obligations, not a missing framework capability.

### Where this Python version is less direct

Both correct versions provide the stated success condition. The Python
wrapper even uses the same `report` variable for the instruction and the
check. ORC's advantage is narrower: `(report :path :out ReportTarget)`
declares their relationship in the prompt signature and derives both
operations. In Python, that relationship is expressed by the function body;
the `Path` annotation does not require its use in either operation.

Consider adding a second deliverable, a UTF-8 evidence file. In ORC, add
`(evidence :path :out ReportTarget)` to `:fills`, use `{evidence}` in the
template, and supply `:evidence` at the call. The same declaration makes the
file mandatory; a caller missing that fill fails compilation. In Python,
add the parameter and path check, include it in the prompt, and add
`evidence.read_text(encoding="utf-8")` before returning:

| Requirement | ORC | Python + Pydantic AI above |
| --- | --- | --- |
| Deliver the document's content | Derived from `:doc`. | Explicit `doc.read_text(...)` in prompt construction. |
| Communicate and require an output file | Both derived from the same `:path :out` slot and fill. | Prompt interpolation plus a separate file check. |
| Add another required file | The new `:out` slot carries the postcondition. | The author must also add the postcondition to the wrapper or validator. |
| Validate the structured decision | Derived from `-> Review`. | Derived from `output_type`; no manual decoder. |

If the Python author omits the new file check, the code remains well typed
and can return a valid `Review` without the evidence file. The correctly
declared ORC `:out` slot prevents that omission. This is not proof against
an incorrect specification: an ORC author can also mistakenly write `:path`
without `:out`. The benefit starts once the output role is declared: its
consequences do not need a second implementation.

A Python `@prompt` decorator using `Annotated` delivery metadata and a typed
`Review` return could derive those same connections from the function
signature. A reusable Python abstraction could therefore narrow this gap.
ORC supplies the connection as an implemented language contract; the example
shows a local ergonomics advantage over the wrapper, not that Pydantic AI is
generally inferior or that adopting another language is justified for one
function.

The boundary is deliberately narrow. `:out` checks for a UTF-8 file at the
destination; it does not prove freshness, authorship, or equality with any
path field in `Review`. Neither `:doc` nor `:out` establishes registry
`consumes`/`publishes` lineage, a sandbox guarantee, or a context-token budget.

## Supporting examples and contract references

The earlier experiment-proposal comparison remains in
[`improve_naive.py`](improve_naive.py) and
[`improve_equivalent.py`](improve_equivalent.py). The latter is a deliberately
handwritten validator and sequential journal specimen, not the best possible
Python architecture or an implementation of all orchestrator guarantees.
[`selfcheck.py`](selfcheck.py) checks its specific committed-effect resume,
malformed-answer, and missing-answer cases. An interrupted external effect
that has not been committed can repeat; those checks do not prove exactly-once
agent execution across arbitrary crashes.

For a complete ORC consumer, see
[`improve_experiment_proposal.orc`](../../workflows/examples/improve_experiment_proposal.orc)
and the library it uses,
[`std/improve`](../../orchestrator/workflow_lisp/stdlib_modules/std/improve.orc).
[`review_revise_design_docs.orc`](../../workflows/examples/review_revise_design_docs.orc)
shows a real document-review prompt with an output position.

The conceptual contracts above are implemented surfaces, but the current
lowerer still restricts some combinations and expression positions. A valid
fragment is not evidence that every surrounding program shape executes; use
the [drafting guide's current program shapes](../../docs/lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today)
and [capability matrix](../../docs/capability_status_matrix.md) before building
a complete workflow.

For the owning definitions and behavioral evidence, start with the
[prompt-fragment and output-position guide](../../docs/lisp_workflow_drafting_guide.md#authoring-prompt-fragments---target-220),
the frontend specification
[§22.6](../../docs/design/workflow_lisp_frontend_specification.md#226-workflow-lisp-prompt-fragments-target-220)
and [§22.7](../../docs/design/workflow_lisp_frontend_specification.md#227-implemented-prompt-output-positions-target-221),
and the existing tests for
[union prompt results](../../tests/test_workflow_lisp_generic_union_defprompt_results.py),
[prompt compilation](../../tests/test_workflow_lisp_prompt_calculus.py), and
[prompt runtime behavior](../../tests/test_workflow_lisp_prompt_calculus_runtime.py).
