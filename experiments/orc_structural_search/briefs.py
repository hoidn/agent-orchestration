"""The mutator's episode brief (EPISODE.md, read on the mutator's stdin).

Design: docs/design/orc_structural_search_driver.md ("Proposal Interfaces" I1/I2/I3, "Evaluation Hygiene"); Phase
2 plan Decision 7 (feedback). The brief names the objective, the mutable scope, the frozen surfaces and an admission-check
line that runs from the workspace (`PYTHONPATH=../py`; an I3 brief's Python module: a pyright line, whose
`orchestrator` imports resolve there too); an I2 brief adds the site (`sites.site_brief`), and a
brief with feedback adds the parent's own evidence: judged mean per task with n, and per evaluation the outcome,
terminal variant, provider calls and wall clock. Any other feedback field (a hidden fraction, another candidate's
score) is never rendered, and nothing here names a runtime or evidence path.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

from experiments.orc_structural_search import ledger, site_evidence
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.evaluation import is_python
from experiments.orc_structural_search.metrics import allocation, metric_definitions, mutable_source
from experiments.orc_structural_search.record_normalization import _named_definitions, control_heads
from experiments.orc_structural_search.records import UNAVAILABLE
from experiments.orc_structural_search.sites import site_brief
from orchestrator.workflow_lisp.sexpr import ListExpr, SymbolAtom


# The replacement heads whose sites the manifest types (orchestrator/workflow_lisp/source_sites.py _KINDS), so the
# I2 slot check can compare the replacement's type with the site's; any other replacement is slot_type_unavailable.
TYPED_HEADS = {"provider-result": "provider-call", "run-provider-phase": "provider-phased-call", "agent": "agent-turn",
               "(<procedure> ...)": "procedure-call", "call": "workflow-call", "run-ref": "run-ref", "let*": "let*",
               "if": "if", "cond": "cond", "match": "match", "loop/recur": "loop", "list/map": "list-map",
               "list/map-effect": "list-map"}
# What else refuses an I3 proposal inside `run` and added functions (acceptance.validate_python_scope and
# suppression_check), keyed by the construct; "prompt" applies under topology-only. The I3 brief renders each text.
PYTHON_RULES = {
    "import": "import statements",
    "global": "global or nonlocal statements",
    "names": "a local variable or added function named like any top-level name, and assigning to, deleting or "
             "mutating through a top-level name",
    "tuning": "a model= or effort= value that is not a literal",
    "decorator": "decorators",
    "builtin": "an added function named like a builtin",
    "prompt": "a provider_result call whose prompt argument is not <NAME>_PROMPT.format(...) written in the call "
              "itself (a variable or parameter holding one is refused), with <NAME>_PROMPT one of the top-level prompt "
              "constants (the format arguments are free, e.g. task=task + feedback)",
    "suppression": "comments that silence pyright (`# type: ignore`, `# pyright: ...`), which the check line below "
                   "does not report",
}


def episode_brief(config: ExperimentConfig, index: int, *, site: Mapping | None = None,
                  feedback: Mapping | None = None) -> str:
    """The brief of episode `index`; its first line is "# Episode <index>"."""
    text = (f"# Episode {index}\n\n"
            f"Objective: rewrite the workflow `{config.entry_workflow}` in this directory into a policy you expect "
            "to complete coding tasks in a git repository more reliably or with fewer provider calls. The "
            "evaluator and its tasks are not visible here.\n\n"
            + (python_scope(config) if is_python(config) else lisp_scope(config, site)))
    if site is not None:
        text += (f"\n## Site\n\n{site_brief(site)}\n\nThe slot check can type only a replacement headed by one of: "
                 f"{', '.join(TYPED_HEADS)}. Any other replacement (a literal, a variable, a record or variant, a pure "
                 "function call) has no type to compare and is refused.\n")
    if feedback is not None:
        text += f"\n## Feedback\n\n{feedback_text(feedback)}\n"
    return text


def python_scope(config: ExperimentConfig) -> str:
    """An I3 brief's scope, frozen surfaces and check line (acceptance.validate_python_scope, check_python)."""
    module = ledger.entry_of(Path(), config)[0].as_posix()
    rules = [text for rule, text in PYTHON_RULES.items() if rule != "prompt" or config.condition == "topology-only"]
    return (f"Mutable scope: files {', '.join(config.mutable_files)}; functions "
            f"{', '.join(config.mutable_definitions)} and fresh top-level functions; condition {config.condition}.\n\n"
            "Frozen surfaces: every other top-level definition: imports, dataclasses, prompt constants, the provider "
            f"adapter and `main`; the signature of {', '.join(f'`{name}`' for name in config.mutable_definitions)}; "
            "and what the condition does not permit (topology-only freezes prompts, the providers file and any "
            "model=/effort= value the module does not already use). Adding any other top-level statement or file, "
            "or changing a frozen surface, refuses the proposal. Inside "
            f"{', '.join(f'`{name}`' for name in config.mutable_definitions)} and added functions these also refuse "
            f"it: {'; '.join(rules)}.\n\n"
            f"Check an edit with: PYTHONPATH=../py pyright {module}\n")


def lisp_scope(config: ExperimentConfig, site: Mapping | None) -> str:
    """An I1 or I2 brief's scope, frozen surfaces and compile line."""
    boundary = (f"the command boundary file {config.command_boundaries_file}; "
                if config.command_boundaries_file else "")
    if config.condition == "module":
        return (f"Mutable scope: files {', '.join(config.mutable_files)}; the entry body and private procedures, "
                "workflows, prompts and types may be added, removed or rewritten; condition module.\n\n"
                "Frozen surfaces: imports, module and language forms, exports, exported entry parameters and result, "
                f"imported public types, provider bindings; {boundary}all other files.\n\n"
                f"Models and efforts (literal values only): {config.models}. Every provider call needs a positive "
                f"literal :timeout-sec at most {config.per_call_timeout_sec}. Agent sessions and phased providers "
                "are refused. Claude launches through PATH enforce model IDs; Codex models are checked at admission.\n\n"
                "Check an edit with: PYTHONPATH=../py python -P -m experiments.orc_structural_search.check "
                "--metadata ../admission.json\n")
    added = "Adding or removing files or definitions" + (" (other than the site's fresh helpers)" if site else "")
    return (f"Mutable scope: files {', '.join(config.mutable_files)}; definitions "
            f"{', '.join(config.mutable_definitions)}; condition {config.condition}.\n\n"
            "Frozen surfaces: imports; deftype, defrecord, defunion and defenum declarations; export, module and "
            f"language forms; exported signatures; {boundary}and what the condition does not permit (topology-only "
            "freezes prompts, the providers file and any :model/:effort value the module does not already use). "
            f"{added}, or changing a frozen surface, refuses the proposal.\n\n"
            "Check an edit with: PYTHONPATH=../py python -P -m experiments.orc_structural_search.check "
            "--metadata ../admission.json\n")


def feedback_text(feedback: Mapping) -> str:
    """Decision 7's fields of the parent's own evidence, one line each; every other field is dropped."""
    lines = ["Evidence on the workflow you are editing (judged values are rubric means):"]
    lines += [f"- task {task}: mean {value['mean']} over {value['n']} runs (failed runs count 0)"
              for task, value in feedback.get("mean_value", {}).items()]
    lines += [f"- run on task {run['task']}: outcome {run['outcome']}, terminal {run['terminal']}, "
              f"{run['provider_calls']} provider calls, {run['wall_clock_sec']} s wall clock"
              for run in feedback.get("runs", ())]
    rows = feedback.get("evaluated_structures", ())
    if not isinstance(rows, (list, tuple)):
        rows = ()
    if structures := [_structure_line(row) for row in rows if isinstance(row, Mapping)]:
        lines += ["", "Structures already tried (make the proposal differ structurally from each):", *structures]
    return "\n".join(lines)


def _structure_line(summary: Mapping) -> str:
    """Render only a bounded, typed projection of a controller-authored structural summary."""
    idea = summary.get("idea_key", "")
    idea_prefix = idea[:12] if isinstance(idea, str) and re.fullmatch(r"[0-9a-f]{64}", idea) else "unavailable"
    return (f"- heads [{_heads_text(summary)}]; control [{_control_text(summary)}]; roles [{_role_text(summary)}]; "
            f"loop {_yes_no(summary.get('loop'))}; check-gated {_yes_no(summary.get('check_gated'))}; "
            f"idea: {idea_prefix}")


def _control_text(summary: Mapping) -> str:
    controls = summary.get("control_heads", {})
    if not isinstance(controls, Mapping):
        return ""
    return ", ".join(f"{head}={controls[head]}" for head in ("if", "cond", "match", "loop/recur",
                                                                  "list/map-effect")
                      if type(controls.get(head)) is int)


def _role_text(summary: Mapping) -> str:
    roles = summary.get("provider_roles", ())
    if not isinstance(roles, (list, tuple)):
        return ""
    return ", ".join(role for role in roles
                      if isinstance(role, str) and re.fullmatch(r"providers\.[A-Za-z0-9_.-]+", role))


def _heads_text(summary: Mapping) -> str:
    outline = summary.get("heads_outline", ())
    if not isinstance(outline, (list, tuple)):
        return ""
    return "; ".join(text for row in outline if (text := _definition_text(row)))


def _definition_text(definition) -> str:
    if not isinstance(definition, Mapping) or not isinstance(definition.get("forms"), list):
        return ""
    name = definition.get("definition")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        return ""
    forms = ", ".join(f"{form['head']}/{form['arity']}" for form in definition["forms"]
                       if isinstance(form, Mapping) and isinstance(form.get("head"), str)
                       and re.fullmatch(r"[A-Za-z0-9_.*!?+:-]+(?:/[A-Za-z0-9_.*!?+:-]+)*", form["head"])
                       and type(form.get("arity")) is int and form["arity"] >= 0)
    return f"{name}: {forms}"


def _yes_no(value) -> str:
    return "yes" if value is True else "no" if value is False else "unavailable"


def structural_summary(candidate_root: Path, config: ExperimentConfig, *, runtime: Path) -> dict:
    """Summarize mutable authored ORC forms and compiled provider policy, without reading evaluation artifacts."""
    source = mutable_source(candidate_root, config)
    definitions = metric_definitions(candidate_root, config)
    selected = _named_definitions(source, definitions)
    outline = [{"definition": definition.items[1].value, "forms": _form_outline(definition)}
               for definition in selected]
    controls = control_heads(source, definitions=definitions)
    roles = [role for assigned in allocation(candidate_root, config).values() for role in assigned]
    evidence = site_evidence.candidate_evidence(candidate_root, config, runtime=runtime)
    policies = site_evidence._policy_set(evidence["allocation_signature"])
    policy_set = sorted([list(policy) for policy in policies]) if policies is not None else UNAVAILABLE
    check_gated = _check_gated(selected)
    identity = hashlib.sha256(json.dumps({"control_heads": controls, "provider_roles": roles,
                                          "check_gated": check_gated}, sort_keys=True).encode()).hexdigest()
    return {"heads_outline": outline, "control_heads": controls, "provider_roles": roles,
            "policy_set": policy_set,
            "call_sites": len(roles), "loop": controls["loop/recur"] > 0, "check_gated": check_gated,
            "private_definitions": max(0, len(definitions) - 1), "idea_key": identity}


def _form_outline(expression: ListExpr) -> list[dict]:
    forms, pending = [], [expression]
    while pending:
        current = pending.pop()
        if isinstance(current, ListExpr):
            head = current.items[0].value if current.items and isinstance(current.items[0], SymbolAtom) else "?"
            forms.append({"head": head, "arity": max(0, len(current.items) - 1)})
            pending.extend(reversed(current.items))
    return forms


def _has_head(expression, name: str) -> bool:
    pending = [expression]
    while pending:
        current = pending.pop()
        if isinstance(current, ListExpr):
            if current.items and isinstance(current.items[0], SymbolAtom) and current.items[0].value == name:
                return True
            pending.extend(current.items)
    return False


def _command_result_names(expression: ListExpr) -> set[str]:
    names, pending = set(), [expression]
    while pending:
        current = pending.pop()
        if not isinstance(current, ListExpr):
            continue
        if len(current.items) > 1 and isinstance(current.items[0], SymbolAtom) and current.items[0].value == "let*":
            bindings = current.items[1]
            if isinstance(bindings, ListExpr):
                names.update(binding.items[0].value for binding in bindings.items
                             if isinstance(binding, ListExpr) and len(binding.items) > 1
                             and isinstance(binding.items[0], SymbolAtom)
                             and _has_head(binding.items[1], "command-result"))
        pending.extend(current.items)
    return names


def _mentions_result(expression, names: set[str]) -> bool:
    pending = [expression]
    while pending:
        current = pending.pop()
        if isinstance(current, SymbolAtom) and any(current.value == name or current.value.startswith(name + ".")
                                                   for name in names):
            return True
        if isinstance(current, ListExpr):
            pending.extend(current.items)
    return False


def _check_gated(definitions: list[ListExpr]) -> bool:
    # shortcut: direct let* result to if only; extend if candidates use helper, cond or match gates.
    for definition in definitions:
        names, pending = _command_result_names(definition), [definition]
        while pending:
            current = pending.pop()
            if not isinstance(current, ListExpr):
                continue
            if (len(current.items) >= 4 and isinstance(current.items[0], SymbolAtom)
                    and current.items[0].value == "if" and _mentions_result(current.items[1], names)
                    and any(_has_head(branch, "provider-result") for branch in current.items[2:])):
                return True
            pending.extend(current.items)
    return False
