"""Public-run reproducers for forms missing from the original matrix."""

from __future__ import annotations

_HEADER = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule grt/entry)
  (export run)
'''

_IF_RECORDS = '''  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "{probe}" "fetch" n) :returns Box))
  (defproc pick ((pair Pair) (branch String)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((current (if (= branch "A") pair.a pair.b))
           (got (fetch current.n)))
      (record Box :n (+ got.n current.n))))
  (defworkflow run ((branch String :default "B")) -> Box
    (loop/recur :max 2
      :state (loop-state (pair Pair
        (record Pair :a (record Box :n 1) :b (record Box :n 2))))
      :on-exhausted (record Box :n 0)
      (fn (state)
        (let* ((got (pick state.pair branch)))
          (done got)))))'''

_IF_LISTS = '''  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defrecord Out (n Int) (parents List[Box]))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "{probe}" "fetch" n) :returns Box))
  (defproc pick ((pair Pair) (branch String)) -> Out
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((current (if (= branch "A") pair.a pair.b))
           (parents (if (= branch "C") (list pair.b) (list current)))
           (got (fetch current.n)))
      (record Out :n got.n :parents parents)))
  (defworkflow run ((branch String :default "B")) -> Out
    (loop/recur :max 2
      :state (loop-state (pair Pair
        (record Pair :a (record Box :n 1) :b (record Box :n 2))))
      :on-exhausted (record Out :n 0 :parents (list))
      (fn (state)
        (let* ((got (pick state.pair branch)))
          (done got)))))'''

_NESTED_EFFECTFUL_ARGUMENT = '''  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Int
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "{probe}" "bump" n) :returns Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "{probe}" "fetch" n) :returns Box))
  (defworkflow run () -> Box (fetch (bump 26)))'''

_PURE_HELPER_DECLS = '''  (defrecord State (turn Int))
  (defrecord Result (turn Int) (status String))
  (defun result ((state State) (status String)) -> Result
    (record Result :turn state.turn :status status))
  (defworkflow run () -> Result
'''

_PURE_HELPER_LOOP = '''(loop/recur :max 1
      :state (record State :turn 0)
      :on-exhausted (result state "loop_bound_exhausted")
      (fn (state)
        (if (= state.turn 0)
          (continue (record State :turn (+ state.turn 1)))
          (done (result state "done")))))'''

_PURE_HELPER_EXHAUSTION = _PURE_HELPER_DECLS + '''    (if true
      ''' + _PURE_HELPER_LOOP + '''
      (record Result :turn 0 :status "else")))'''

_PURE_HELPER_EXHAUSTION_TOP_LEVEL = _PURE_HELPER_DECLS + "    " + _PURE_HELPER_LOOP + ")"

_CALL_RESULT_IN_IF = '''  (defrecord Note (flag Bool) (note String))
  (defproc step ((name String)) -> Note
    :effects ((uses-command step))
    (command-result step :argv ("python" "{probe}" "step" name) :returns Note))
  (defworkflow inner () -> Note (step "yes"))
  (defworkflow run () -> Note
    (let* ((first (step "yes")))
      (if first.flag
        (let* ((r (call inner))
               (same (= r.note "yes")))
          (step (if same "same" "different")))
        (step "else"))))'''

_SCALAR_CALL_LOOP_STATE = '''  (defproc tick ((n Int)) -> Int
    :effects ((uses-command tick))
    :lowering inline
    (command-result tick :argv ("python" "{probe}" "tick" n) :returns Int))
  (defworkflow run () -> Int
    (loop/recur :max 2
      :state (loop-state (n Int 0) (turn Int 0))
      :on-exhausted 0
      (fn (state)
        (if (= state.turn 0)
          (continue (loop-state :like state :n (tick 1) :turn 1))
          (done state.n)))))'''

_SOURCE = {
    "if-record-loop": _IF_RECORDS,
    "if-list-loop": _IF_LISTS,
    "nested-effectful-argument": _NESTED_EFFECTFUL_ARGUMENT,
    "pure-helper-exhaustion": _PURE_HELPER_EXHAUSTION,
    "pure-helper-exhaustion-top-level": _PURE_HELPER_EXHAUSTION_TOP_LEVEL,
    "call-result-in-if": _CALL_RESULT_IN_IF,
    "scalar-call-loop-state": _SCALAR_CALL_LOOP_STATE,
}


REGRESSION_CELLS = (
    ("repro:if-record-loop", "procedure-in-loop"),
    ("repro:if-list-loop", "procedure-in-loop"),
    ("repro:nested-effectful-argument", "effectful-argument"),
    ("repro:pure-helper-exhaustion", "on-exhausted-value"),
    ("repro:call-result-in-if", "call-result-in-if"),
    ("repro:scalar-call-loop-state", "loop-state-field"),
    ("repro:pure-helper-exhaustion-top-level", "on-exhausted-value"),
)


def reproducer_sources(name: str, probe: str, target: str = "2.33") -> dict[str, str]:
    """Return one minimal `.orc` source tree, preserving the reported position."""

    source = _HEADER.format(target=target) + _SOURCE[name].format(probe=probe) + ")\n"
    return {"grt/entry.orc": source}


def cells() -> list[tuple[str, str]]:
    return list(REGRESSION_CELLS)


def program(form: str, probe: str) -> dict[str, str]:
    target_form = form.removeprefix("t234:")
    name = target_form.removeprefix("repro:")
    target = "2.34" if form.startswith("t234:") else "2.33"
    return reproducer_sources(name, probe, target)


def expected(form: str) -> tuple[dict[str, object], list[str]]:
    name = form.removeprefix("t234:").removeprefix("repro:")
    return {
        "if-record-loop": ({"return__n": 4}, ["fetch 2"]),
        "if-list-loop": ({"return__n": 2, "return__parents": [{"n": 2}]}, ["fetch 2"]),
        "nested-effectful-argument": ({"return__n": 27}, ["bump 26", "fetch 27"]),
        "pure-helper-exhaustion": (
            {"return__turn": 1, "return__status": "loop_bound_exhausted"}, []
        ),
        "call-result-in-if": (
            {"return__flag": True, "return__note": "same"},
            ["step yes", "step yes", "step same"],
        ),
        "scalar-call-loop-state": ({"__result__": 1}, ["tick 1"]),
        "pure-helper-exhaustion-top-level": (
            {"return__turn": 1, "return__status": "loop_bound_exhausted"}, []
        ),
    }[name]
