"""Genotype grammar and its total rendering to a target-2.39 Workflow Lisp module.

A genotype is a tuple of stages, each a tuple drawn from STAGE_KINDS:

    ("plan", model)                         planner drafts steps (a later implement reads them)
    ("implement", model)                    coder changes the workspace
    ("check_and_repair", rounds, model)     check; on failure `model` diagnoses and the coder repairs
    ("review_and_revise", rounds, model)    `model` reviews; on REQUEST_CHANGES the coder revises
    ("ill_typed_implement", model)          off-grammar: only `evolve --ill-typed-rate` makes it; renders
                                            an implement whose summary reads a field Change lacks, so the
                                            compiler rejects it (shows rejection is counted, not crashed)

A genotype holds at least one implement. Every rendered module ends with a final check and returns
`(variant Outcome DONE ...)` when it passes and `BLOCKED` otherwise. Pure; no I/O.
"""

from __future__ import annotations

MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "gpt-6-sol")
CODER_MODEL = "claude-sonnet-5-5"  # repair and revise always use the cheap coder
MAX_ROUNDS = 3
MODULE = "individual"
PROVIDERS = {"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex_unrestricted_workspace"}
COMMANDS = {"check": {"stable_command": ["python", "check.py"], "closure": ["check.py"]}}
STAGE_KINDS = ("plan", "implement", "check_and_repair", "review_and_revise")

HEADER = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule individual)
  (export run)

  (defrecord Plan (steps List[String]))
  (defrecord Change (summary String))
  (defrecord Diagnosis (findings List[String]))
  (defrecord CheckReport (passed Bool) (failing List[String]))
  (defrecord Step (note String))
  (defunion Review
    (APPROVE (notes List[String]))
    (REQUEST_CHANGES (findings List[String])))
  (defunion Outcome
    (DONE (summary String))
    (BLOCKED (reason String)))

  (defprompt plan-prompt (:fills (task :text)) -> Plan
    "STAGE:plan Plan this task as ordered steps. Change no files.\\n\\nTask: {task}")
  (defprompt implement-prompt (:fills (task :text)) -> Change
    "STAGE:implement Implement this task in the working directory.\\n\\nTask: {task}")
  (defprompt implement-plan-prompt (:fills (task :text) (steps :value List[String])) -> Change
    "STAGE:implement Implement this task in the working directory by following the plan.\\n\\nTask: {task}\\nPlan: {steps}")
  (defprompt diagnose-prompt (:fills (failing :value List[String])) -> Diagnosis
    "STAGE:diagnose The check fails. Diagnose why; change nothing.\\n\\nFailing: {failing}")
  (defprompt repair-prompt (:fills (task :text) (findings :value List[String])) -> Change
    "STAGE:repair Fix the root causes the diagnosis names.\\n\\nTask: {task}\\nDiagnosis: {findings}")
  (defprompt review-prompt (:fills (task :text)) -> Review
    "STAGE:review Review the change in the working directory for this task; change nothing.\\n\\nTask: {task}")
  (defprompt revise-prompt (:fills (task :text) (findings :value List[String])) -> Change
    "STAGE:revise Address the review findings.\\n\\nTask: {task}\\nFindings: {findings}")

  (defworkflow run ((task String)) -> Outcome
    (let* ("""

FOOTER = """           (final (command-result check :argv ("python" "check.py") :returns CheckReport)))
      (if final.passed
        (variant Outcome DONE :summary "check passed")
        (variant Outcome BLOCKED :reason "check failed"))))
)
"""


def _call(prompt: str, model: str) -> str:
    extern = "providers.codex" if model.startswith("gpt") else "providers.claude"
    return f'(provider-result {extern} :prompt {prompt} :model "{model}" :effort "medium" :timeout-sec 600)'


def _plan(name: str, model: str, plan: str | None) -> str:
    return f"({name} {_call('(plan-prompt :task task)', model)})"


def _implement(name: str, model: str, plan: str | None) -> str:
    prompt = f"(implement-plan-prompt :task task :steps {plan}.steps)" if plan else "(implement-prompt :task task)"
    return f"({name} {_call(prompt, model)})"


def _ill_typed_implement(name: str, model: str, plan: str | None) -> str:
    # Change has no `steps` field: the compiler must reject this binding.
    return (f"({name} (let* ((c {_call('(implement-prompt :task task)', model)}))\n"
            f"        (record Step :note c.steps)))")


def _check_and_repair(name: str, rounds: int, model: str) -> str:
    return f"""({name} (loop/recur :max {rounds}
        :state (loop-state (round Int 1))
        :on-exhausted (record Step :note "repair rounds exhausted")
        (fn (state)
          (let* ((report (command-result check :argv ("python" "check.py") :returns CheckReport)))
            (if report.passed
              (done (record Step :note "check passed"))
              (let* ((diagnosis {_call('(diagnose-prompt :failing report.failing)', model)})
                     (repair {_call('(repair-prompt :task task :findings diagnosis.findings)', CODER_MODEL)}))
                (continue (loop-state :like state :round (+ state.round 1)))))))))"""


def _review_and_revise(name: str, rounds: int, model: str) -> str:
    return f"""({name} (loop/recur :max {rounds}
        :state (loop-state (round Int 1))
        :on-exhausted (record Step :note "review rounds exhausted")
        (fn (state)
          (let* ((review {_call('(review-prompt :task task)', model)}))
            (match review
              ((APPROVE a) (done (record Step :note "approved")))
              ((REQUEST_CHANGES r)
               (let* ((revision {_call('(revise-prompt :task task :findings r.findings)', CODER_MODEL)}))
                 (continue (loop-state :like state :round (+ state.round 1))))))))))"""


_RENDER = {"plan": _plan, "implement": _implement, "ill_typed_implement": _ill_typed_implement}
LOOPS = {"check_and_repair": _check_and_repair, "review_and_revise": _review_and_revise}


def render(genotype: tuple[tuple, ...]) -> str:
    """Return the module source for `genotype` (total over the grammar; see the module docstring)."""

    bindings, plan = [], None
    for index, stage in enumerate(genotype):
        name, kind = f"s{index}", stage[0]
        if kind in LOOPS:
            bindings.append(LOOPS[kind](name, stage[1], stage[2]))
            continue
        bindings.append(_RENDER[kind](name, stage[1], plan))
        if kind == "plan":
            plan = name
    return HEADER + "".join(f"           {b}\n" for b in bindings) + FOOTER


def call_model(genotype: tuple[tuple, ...], identity: str) -> str:
    """The model a provider call ran with, from its memo identity
    (`workflow:individual::run / s<index>[ / ... / <binding>]`): repair and revise run CODER_MODEL, every
    other call its stage's model. Raises on an identity the renderer cannot produce."""

    parts = identity.split(" / ")
    stage = genotype[int(parts[1].removeprefix("s"))]
    return CODER_MODEL if parts[-1] in ("repair", "revise") else stage[-1]
