"""The mutator's episode brief (EPISODE.md, read on the mutator's stdin).

Design: docs/design/orc_structural_search_driver.md ("Proposal Interfaces" I1/I2/I3, "Evaluation Hygiene"); Phase
2 plan Decision 7 (feedback). The brief names the objective, the mutable scope, the frozen surfaces and a compile
line that runs from the workspace (`PYTHONPATH=../py`; an I3 brief's Python module: a pyright line, whose
`orchestrator` imports resolve there too); an I2 brief adds the site (`sites.site_brief`), and a
brief with feedback adds the parent's own evidence: judged mean per task with n, and per evaluation the outcome,
terminal variant, provider calls and wall clock. Any other feedback field (a hidden fraction, another candidate's
score) is never rendered, and nothing here names a runtime or evidence path.
"""

import shlex
from collections.abc import Mapping
from pathlib import Path

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.evaluation import is_python
from experiments.orc_structural_search.sites import site_brief


# The replacement heads whose sites the manifest types (orchestrator/workflow_lisp/source_sites.py _KINDS), so the
# I2 slot check can compare the replacement's type with the site's; any other replacement is slot_type_unavailable.
TYPED_HEADS = {"provider-result": "provider-call", "run-provider-phase": "provider-phased-call", "agent": "agent-turn",
               "(<procedure> ...)": "procedure-call", "call": "workflow-call", "run-ref": "run-ref", "let*": "let*",
               "if": "if", "cond": "cond", "match": "match", "loop/recur": "loop", "list/map": "list-map",
               "list/map-effect": "list-map"}


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
    return (f"Mutable scope: files {', '.join(config.mutable_files)}; functions "
            f"{', '.join(config.mutable_definitions)} and fresh top-level functions; condition {config.condition}.\n\n"
            "Frozen surfaces: every other top-level definition: imports, dataclasses, prompt constants, the provider "
            f"adapter and `main`; the signature of {', '.join(f'`{name}`' for name in config.mutable_definitions)}; "
            "and what the condition does not permit (topology-only freezes prompts, the providers file and any "
            "model=/effort= value the module does not already use). Adding any other top-level statement or file, "
            "or changing a frozen surface, refuses the proposal.\n\n"
            f"Check an edit with: PYTHONPATH=../py pyright {module}\n")


def lisp_scope(config: ExperimentConfig, site: Mapping | None) -> str:
    """An I1 or I2 brief's scope, frozen surfaces and compile line."""
    module = config.entry_workflow.split("::")[0]
    compile_args = ["python", "-P", "-m", "orchestrator", "compile", f"{module}.orc", "--entry-workflow",
                    config.entry_workflow, "--source-root", config.source_root, "--provider-externs-file",
                    config.providers_file]
    boundary = ""
    if config.command_boundaries_file:
        compile_args += ["--command-boundaries-file", config.command_boundaries_file]
        boundary = f"the command boundary file {config.command_boundaries_file}; "
    added = "Adding or removing files or definitions" + (" (other than the site's fresh helpers)" if site else "")
    return (f"Mutable scope: files {', '.join(config.mutable_files)}; definitions "
            f"{', '.join(config.mutable_definitions)}; condition {config.condition}.\n\n"
            "Frozen surfaces: imports; deftype, defrecord, defunion and defenum declarations; export, module and "
            f"language forms; exported signatures; {boundary}and what the condition does not permit (topology-only "
            "freezes prompts, the providers file and any :model/:effort value the module does not already use). "
            f"{added}, or changing a frozen surface, refuses the proposal.\n\n"
            f"Check an edit with: PYTHONPATH=../py {shlex.join(compile_args)}\n")


def feedback_text(feedback: Mapping) -> str:
    """Decision 7's fields of the parent's own evidence, one line each; every other field is dropped."""
    lines = ["Evidence on the workflow you are editing (judged values are rubric means):"]
    lines += [f"- task {task}: mean {value['mean']} over {value['n']} runs (failed runs count 0)"
              for task, value in feedback.get("mean_value", {}).items()]
    lines += [f"- run on task {run['task']}: outcome {run['outcome']}, terminal {run['terminal']}, "
              f"{run['provider_calls']} provider calls, {run['wall_clock_sec']} s wall clock"
              for run in feedback.get("runs", ())]
    return "\n".join(lines)
