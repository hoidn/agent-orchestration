"""Throwaway F1 probe: build a non-exported workflow as a private child entry."""
import sys, tempfile, json
from dataclasses import replace
from pathlib import Path
from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.contracts.closed_program.program import ClosedProgram
from tests.workflow_lisp_closed_program_helpers import install, BOUNDARIES, PROVIDERS, PROMPTS, TARGET

HELPER = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule helper) (export bump fetch Box)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch)) :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defun bump ((n Int)) -> Int (+ n 1)))'''
PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule controller) (import helper :only (bump fetch Box)) (export run)
  (defrecord Verdict (ok Bool))
  (defworkflow candidate-body ((seed Int) (task String)) -> Int
    (let* ((verdict (provider-result providers.review :prompt prompts.base
                      :inputs (task) :returns Verdict)))
      (if verdict.ok
        (loop/recur :max 5
          :state (loop-state (i Int seed))
          :on-exhausted -1
          (fn (state)
            (let* ((box (fetch (bump state.i))))
              (if (>= box.n 3) (done box.n)
                (continue (loop-state :like state :i box.n))))))
        0)))
  (defworkflow run ((seed Int)) -> Int (+ seed 1)))'''

root = Path(tempfile.mkdtemp())
install(root, {"helper.orc": HELPER, "controller.orc": PARENT})
providers = {"providers.review": "probe-provider"}
prompts = {"prompts.base": PROMPTS["prompt"]}
typed = compile_typed_program(root / "controller.orc", entry_workflow="controller::run", source_roots=(root,),
    command_boundaries=BOUNDARIES, provider_externs=providers, prompt_externs=prompts, workspace_root=root)
print(sorted(typed.workflows))
child_typed = replace(typed, entry=typed.workflows["controller::candidate-body"])
child = build_closed_program(child_typed, builder=Builder(child_typed))
print("entry", child.tree["entry"], "params", child.tree["params"])
print("sites", site_classes(child))
print("summary", child_typed.entry.effect_summary)
print("config", json.dumps(child.tree["configuration"], default=str)[:800])
print("digest", child.digest)
print({k: v.get("key") for k, v in child.tree["definitions"].items()})
print(child.tree["configuration"].get("providers"), child.tree["configuration"].get("prompts"), list(child.tree["configuration"]))
