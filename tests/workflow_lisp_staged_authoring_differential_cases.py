"""Programs around Task 0b of the staged-workflow authoring plan (D1, D2, D3, D5), for the differential corpus
`tests/test_workflow_lisp_staged_authoring_differential.py`. Each is the body of module `m` at target 2.40, entry
`run`, built beside the stand-in command `c`, the provider extern `providers.review` and the prompt `prompts.base`
(the installation of `tests/workflow_lisp_td21_differential_cases.py`).

`CASES` maps an id to `(run, definitions)`; `BOUND` maps the id of a case to the id of its `let*`-bound spelling,
itself a case (`<id>~bound`), which built before the fixes. Families, each fixed shape crossed with neighbours that
built before (the same form bound with `let*` first, `if` for `match`, one more level of nesting, with an effect
and without, in a loop and outside):
- `d1-`: a `list/map` whose body is a `match`, or a `let*` reading the binder, in a condition (`if`, `cond`, an
  `and`, `or` or `not` operand, a nested `if`) in a loop body, a `fn` loop body, a match arm, a parallel map
  body, a procedure, and outside a loop;
- `d2-`: a `match` subject with a list or a `list/map` in it, in a workflow, a loop, a procedure and an uncalled
  procedure, with and without an effect in an arm, with an empty list in an arm;
- `d3-`: a generic procedure called in a serial map body, nested, in a loop, in a procedure, through a `let*`
  or an `if`, beside the parallel map, the loop body, the local procedure and the pure map that built;
- `d5-`: a `bind-proc` over a parameter of a pure procedure passed on to a `ProcRef` parameter, beside a literal,
  an effectful procedure and a reference bound in the caller;
- `<family>-r-`: the probe programs of the review of Task 0b (`staged_authoring_review_probes.json` under
  `tests/fixtures/workflow_lisp/`, each with the id it has there and the id of its bound spelling, `~b`, where it
  has one), less those the TD1 corpus (`tests/workflow_lisp_td21_differential_cases.py`) already holds: among
  them a list in a `let-proc` local's call in a `match` subject beside an `and`, an `or` or a `cond`, and a local
  that captures a name bound to a generic call.
For D1 the bound spelling binds the condition's map with `let*` (a `let*` in the map body reading the binder is
written without it, since it has the defect in that spelling too); for D3 it is the call through a `let-proc` local
written outside every map, the spelling that built (a `let*` in the map body does not); for an empty list in an
arm (a `let*` body supplies no item type) it passes the bound subject to a procedure that matches it; for D5
(a refusal), the uncalled procedures and the neighbours that built there is none.

The three expectation files under `tests/fixtures/workflow_lisp/` are written by this module's `__main__`, never by
hand: `staged_authoring_differential_main.json` (every case's build) and
`staged_authoring_differential_bound_values.json` (the bound spelling's value) on an export of `main` at
`b7e2e2b5`; `staged_authoring_differential_pins.json` (the outcome of every case whose outcome moved) on the tip
of `feat/authoring-0b`. With `F=TREE/tests/fixtures/workflow_lisp` and `M=staged_authoring_differential`:

    git archive b7e2e2b5 | tar -x -C EXPORT
    cd EXPORT && PYTHONPATH=EXPORT python -B TREE/tests/workflow_lisp_staged_authoring_differential_cases.py \\
        outcomes $F/$M_main.json
    cd TREE && PYTHONPATH=TREE python -B tests/workflow_lisp_staged_authoring_differential_cases.py \\
        pins $F/$M_main.json $F/$M_pins.json
    cd EXPORT && PYTHONPATH=EXPORT python -B TREE/tests/workflow_lisp_staged_authoring_differential_cases.py \\
        bound-values $F/$M_pins.json $F/$M_bound_values.json
"""

from __future__ import annotations

import json
from pathlib import Path

U = "(defunion U (A (n Int)) (B (why String)))"
V = "(defunion V (HAS (xs List[Int])) (NO (k Int)))"


def E(label: str, value: str = "1", type_: str = "Int") -> str:
    return f'(command-result c :argv ("python" "c.py" "{label}" "{value}") :returns {type_})'


# ---------------------------------------------------------------------------------------------
# D1

# body: (as written, in the bound spelling). A `let*` in the body reading the binder has the defect in the bound
# spelling too, so that spelling writes the body without it.
D1_BODIES = {
    "match": ("(match v ((A a) (> s a.n)) ((B b) true))",) * 2,
    "match-let": ("(let* ((k (match v ((A a) a.n) ((B b) 0)))) (> s k))", "(> s (match v ((A a) a.n) ((B b) 0)))"),
    "let-binder": ("(let* ((w v)) (match w ((A a) (> s a.n)) ((B b) true)))", "(match v ((A a) (> s a.n)) ((B b) true))"),
    "if": ("(if (= v.variant A) (> s 2) true)",) * 2,
    "let-free": ("(let* ((k 3)) (> s k))",) * 2,
}
# DONE(x) and NEXT: `(done x)` and `(continue (+ s 1))` in a loop body, `x` and `0` outside one.
D1_CONDITIONS = {
    "if": "(if HEAD DONE(s) NEXT)",
    "cond": "(cond (HEAD DONE(s)) (else NEXT))",
    "and": "(if (and (> s 0) HEAD) DONE(s) NEXT)",
    "or": "(if (or (> s 9) HEAD) DONE(s) NEXT)",
    "not": "(if (not HEAD) NEXT DONE(s))",
    "nested-if": "(if (> s 2) (if HEAD DONE(s) NEXT) NEXT)",
    "map-in-map": "(if HEAD DONE(s) NEXT)",
}
D1_HEAD = "(or-else (list/head (list/map ((v vs)) BODY)) false)"
D1_HEADS = {"map-in-map": "(or-else (list/head (list/map ((ws (list vs))) (or-else (list/head (list/map ((v ws)) BODY)) "
                          "false))) false)"}
LOOP = "(loop/recur ((s 0)) :max 6 :on-exhausted 99 FORM)"
D1_CONTEXTS = {
    # context: (run with FORM, in a loop, the conditions it takes)
    "loop": (f"((u U)) -> Int (let* ((vs (list u u))) {LOOP})", True, tuple(D1_CONDITIONS)),
    "loop-effect": ("((u U)) -> Int (let* ((vs (list u u))) " + LOOP.replace("FORM", f"(let* ((r {E('r')})) FORM)")
                    + ")", True, ("if", "cond", "and")),
    "loop-fn": ("((u U)) -> Int (let* ((vs (list u u))) (loop/recur :max 6 :state 0 :on-exhausted 99 (fn (s) FORM)))",
                True, ("if", "and")),
    "arm": ("((u U)) -> Int (let* ((vs (list u u))) " + LOOP.replace("FORM", "(match u ((A x) FORM) ((B y) (done 0)))")
            + ")", True, ("if", "cond")),
    "proc": ("((u U)) -> Int (p u)", True, ("if",)),
    "outside": ("((u U)) -> Int (let* ((vs (list u u)) (s 4)) FORM)", False, ("if", "cond", "and")),
    "parallel": ('((u U)) -> List[Int] (let* ((vs (list u u)) (s 4)) (list/map-effect ((d (list "."))) :max 1 '
                 ":parallel 1 :workspace d FORM))", False, ("if", "and")),
}


def _d1_form(condition: str, body: str, *, in_loop: bool, bound: bool) -> str:
    form = D1_CONDITIONS[condition]
    form = form.replace("DONE(s)", "(done s)" if in_loop else "s").replace("NEXT", "(continue (+ s 1))" if in_loop else "0")
    head = D1_HEADS.get(condition, D1_HEAD).replace("BODY", body)
    return f"(let* ((ok {head})) {form.replace('HEAD', 'ok')})" if bound else form.replace("HEAD", head)


def _d1_case(context: str, condition: str, body: str, *, bound: bool) -> tuple[str, tuple[str, ...]]:
    run, in_loop, _conditions = D1_CONTEXTS[context]
    form = _d1_form(condition, D1_BODIES[body][bound], in_loop=in_loop, bound=bound)
    if context == "proc":
        return run, (U, "(defproc p ((u U)) -> Int (let* ((vs (list u u))) " + LOOP.replace("FORM", form) + "))")
    return run.replace("FORM", form), (U,)


def _d1() -> list[tuple[str, tuple[str, tuple[str, ...]], tuple[str, tuple[str, ...]] | None]]:
    cases = []
    for context, (_run, _in_loop, conditions) in D1_CONTEXTS.items():
        for condition in conditions:
            for body in D1_BODIES:
                cases.append((f"d1-{context}-{condition}-{body}", _d1_case(context, condition, body, bound=False),
                              _d1_case(context, condition, body, bound=True)))
    return cases


# ---------------------------------------------------------------------------------------------
# D2

D2_DEFINITIONS = (V, "(defproc mk ((xs List[Int])) -> V (variant V HAS :xs xs))",
                  "(defproc mk2 ((k Int)) -> V (variant V NO :k k))")
D2_SUBJECTS = {
    "variant-list": "(variant V HAS :xs (list 1 2))",
    "variant-empty": "(variant V HAS :xs (list))",
    "variant-length": "(variant V NO :k (list/length (list 1 2 3)))",
    "proc-arg": "(mk (list 1 2))",
    "if-condition": "(if (list/empty? (list n)) (variant V NO :k 1) (variant V NO :k 2))",
    "if-branch": "(if (> n 0) (variant V HAS :xs (list n)) (variant V NO :k 2))",
    "let-subject": "(let* ((ys (list 1))) (variant V HAS :xs ys))",
    "let-map": "(let* ((k (list/length (list/map ((x xs)) x)))) (mk2 k))",
    "nested-match": "(match (variant V HAS :xs (list 1)) ((HAS h) (variant V NO :k (list/length h.xs))) ((NO o) (variant V NO :k o.k)))",
    "map-literal": "(mk2 (list/length (list/map ((x (list 1 2))) x)))",
    "map-name": "(mk2 (list/length (list/map ((x xs)) x)))",
    "map-field": "(variant V NO :k (list/length (list/map ((x xs)) (+ x 1))))",
    "local-argument": "(let-proc ((f ((ys List[Int])) -> V (variant V HAS :xs ys))) (f (list 1)))",
    "cond-list": "(cond ((list/empty? (list n)) (variant V NO :k 1)) (else (variant V NO :k 2)))",
    # Neighbours that built: the list only in a local's body; a `cond`; a name.
    "local-body": "(let-proc ((f ((k Int)) -> V (variant V HAS :xs (list k)))) (f 1))",
    "cond": "(cond ((> n 0) (variant V NO :k 1)) (else (variant V NO :k 2)))",
    "input-name": "(mk xs)",
    # An empty list as a procedure's argument: refused `list_empty_type_context_required` before, as written.
    "empty-argument": "(mk (list))",
}
D2_ARMS = {
    "plain": "((HAS h) (list/length h.xs)) ((NO o) o.k)",
    "effect": f"((HAS h) (+ (list/length h.xs) {E('arm')})) ((NO o) o.k)",
}
D2_PARAMS = "((n Int) (xs List[Int]))"
D2_EMPTY_ARMS = "((HAS h) h.xs) ((NO o) (list))"
D2_PM = f"(defproc pm ((w V)) -> List[Int] (match w {D2_EMPTY_ARMS}))"


# The bound spelling of a subject that is itself a `match` with a list in its subject binds that subject too.
D2_BOUND = {"nested-match": "((w0 (variant V HAS :xs (list 1))) "
                            "(w (match w0 ((HAS h) (variant V NO :k (list/length h.xs))) ((NO o) (variant V NO :k o.k)))))"}


def _d2_bindings(subject: str) -> str:
    return next((value for name, value in D2_BOUND.items() if D2_SUBJECTS[name] == subject), f"((w {subject}))")


def _d2_match(subject: str, arms: str, *, bound: bool) -> str:
    return f"(let* {_d2_bindings(subject)} (match w {arms}))" if bound else f"(match {subject} {arms})"


def _d2_case(context: str, subject: str, arms: str, *, bound: bool) -> tuple[str, tuple[str, ...]]:
    match = _d2_match(subject, arms, bound=bound)
    if context == "workflow":
        return f"{D2_PARAMS} -> Int {match}", D2_DEFINITIONS
    if context == "loop":
        return f"{D2_PARAMS} -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (done (+ s {match})))", D2_DEFINITIONS
    procedure = f"(defproc p {D2_PARAMS} -> Int {match})"
    if context == "proc":
        return f"{D2_PARAMS} -> Int (p n xs)", (*D2_DEFINITIONS, procedure)
    return "() -> Int 1", (*D2_DEFINITIONS, procedure)  # an uncalled procedure


def _d2():
    cases = []
    for name, subject in D2_SUBJECTS.items():
        for context in ("workflow", "loop", "proc"):
            for arms_name, arms in D2_ARMS.items():
                cases.append((f"d2-{context}-{arms_name}-{name}", _d2_case(context, subject, arms, bound=False),
                              _d2_case(context, subject, arms, bound=True)))
        cases.append((f"d2-uncalled-{name}", _d2_case("uncalled", subject, D2_ARMS["plain"], bound=False),
                      ("() -> Int 1", D2_DEFINITIONS)))
        # An empty list in an arm, typed by the workflow's result. A `let*` body supplies no item type, so the
        # bound spelling passes the bound subject to a procedure that matches its parameter.
        cases.append((f"d2-empty-arm-{name}", (f"{D2_PARAMS} -> List[Int] (match {subject} {D2_EMPTY_ARMS})",
                                              D2_DEFINITIONS),
                      (f"{D2_PARAMS} -> List[Int] (let* {_d2_bindings(subject)} (pm w))", (*D2_DEFINITIONS, D2_PM))))
    return cases


# ---------------------------------------------------------------------------------------------
# D3

D3_DEFINITIONS = (
    f'(defproc keep :forall (T) ((x T)) -> T (let* ((seen {E("g")})) x))',
    "(defproc keepp :forall (T) ((x T)) -> T x)",
    f'(defproc second :forall (A B) ((a A) (b B)) -> B (let* ((seen {E("p")})) b))',
    "(defproc via :forall (T) ((f ProcRef[T -> T]) (x T)) -> T (f x))",
    "(defproc inc ((v Int)) -> Int (+ v 1))",
    f'(defproc plain ((x Int)) -> Int (let* ((seen {E("q")})) x))',
)
# A body over the binder `x : Int`, of type `Int`.
D3_CALLS = {
    "direct": "(keep x)",
    "nested": "(keep (keep x))",
    "pure": "(keepp x)",
    "two-params": '(second "a" x)',
    "proc-ref": "(via (proc-ref inc) x)",
    "let": "(let* ((r (keep x))) r)",
    "if": "(if (> n 0) (keep x) x)",
    "operand": "(+ 1 (keep x))",
    "plain": "(plain x)",
    # A recursive generic procedure: `parametric_specialization_cycle`, as outside a map; it was
    # `procedure_call_unknown` in a serial map body.
    "recursive": "(rk x 1)",
}
D3_CALL_DEFINITIONS = {"recursive": (f"(defproc rk :forall (T) ((x T) (k Int)) -> T (if (> k 0) (rk x (- k 1)) "
                                     f"(let* ((seen {E('r')})) x)))",)}
D3_SERIAL = "(list/map-effect ((x SOURCE)) :max 4 CALL)"
# context: (signature, body); the body of `serial-proc` is that of procedure `p`, which `run` calls.
D3_CONTEXTS = {
    "serial": ("((n Int)) -> List[Int]", "MAP"),
    "serial-input": ("((n Int) (xs List[Int])) -> List[Int]", "MAP"),
    "serial-loop": ("((n Int)) -> Int", "(loop/recur ((s 0)) :max 1 :on-exhausted 0 (done (list/length MAP)))"),
    "serial-nested": ("((n Int)) -> Int", "(list/length (list/map-effect ((y (list 1))) :max 1 (list/length MAP)))"),
    "serial-proc": ("((n Int)) -> List[Int]", "MAP"),
    # Neighbours that built: a loop body, a pure map.
    "loop-body": ("((n Int)) -> Int", "(let* ((x 1)) (loop/recur ((s 0)) :max 1 :on-exhausted 0 (done CALL)))"),
    "pure-map": ("((n Int)) -> List[Int]", "(list/map ((x (list 1 2))) CALL)"),
}


def _d3_body(context: str, call: str, *, bound: bool) -> str:
    """The body; bound, the call goes through a local `h` written outside every map (a local written in a
    serial map body is row E7-local of the defect record)."""
    signature, body = D3_CONTEXTS[context]
    source = "xs" if context == "serial-input" else "(list 1 2)"
    body = body.replace("MAP", D3_SERIAL.replace("SOURCE", source))
    if bound:
        return f"(let-proc ((h ((x Int)) -> Int {call})) {body.replace('CALL', '(h x)')})"
    return body.replace("CALL", call)


def _d3_case(context: str, name: str, *, bound: bool) -> tuple[str, tuple[str, ...]]:
    signature, _body = D3_CONTEXTS[context]
    body = _d3_body(context, D3_CALLS[name], bound=bound)
    definitions = (*D3_DEFINITIONS, *D3_CALL_DEFINITIONS.get(name, ()))
    if context == "serial-proc":
        return f"{signature} (p n)", (*definitions, f"(defproc p {signature} {body})")
    return f"{signature} {body}", definitions


D3_NEIGHBOUR_CALLS = {"pure-map": ("pure", "proc-ref")}  # an effect in a pure map is refused before and after


def _d3():
    cases = []
    for context in D3_CONTEXTS:
        for name in D3_NEIGHBOUR_CALLS.get(context, tuple(D3_CALLS)):
            bound = _d3_case(context, name, bound=True) if context.startswith("serial") else None
            cases.append((f"d3-{context}-{name}", _d3_case(context, name, bound=False), bound))
    # The parallel map over workspaces, which built.
    for name in ("direct", "nested", "pure"):
        call = D3_CALLS[name].replace("x)", "w)")
        cases.append((f"d3-parallel-{name}", ('() -> List[String] (list/map-effect ((w (list "a" "b"))) :max 2 '
                                              f":parallel 2 :workspace w {call})", D3_DEFINITIONS), None))
    return cases


# ---------------------------------------------------------------------------------------------
# D5

D5_DEFINITIONS = ("(defproc add ((n Int) (x Int)) -> Int (+ n x))",
                  "(defproc add2 ((n Int) (m Int) (x Int)) -> Int (+ n (+ m x)))",
                  "(defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))")
D5_BODIES = {
    "direct": "(apply1 (bind-proc (proc-ref add) :n k) 1)",
    "let": "(let* ((g (bind-proc (proc-ref add) :n k))) (apply1 g 1))",
    "computed": "(apply1 (bind-proc (proc-ref add) :n (+ k 0)) 1)",
    "two-uses": "(+ (apply1 (bind-proc (proc-ref add) :n k) 1) (apply1 (bind-proc (proc-ref add) :n k) 2))",
    "two-bound": "(apply1 (bind-proc (proc-ref add2) :n k :m 1) 1)",
    # Neighbours: a literal; called where bound; an effect in the procedure.
    "literal": "(apply1 (bind-proc (proc-ref add) :n 5) k)",
    "called-where-bound": "(let* ((g (bind-proc (proc-ref add) :n k))) (g 1))",
    "effect": f"(let* ((w {E('w')})) (apply1 (bind-proc (proc-ref add) :n k) 1))",
}
D5_CALLS = {
    "call": "() -> Int (outer 2)",
    "operand": "() -> Int (+ 0 (outer 2))",
    "loop": "() -> Int (loop/recur ((s 0)) :max 1 :on-exhausted 0 (done (outer 2)))",
    "map": "() -> List[Int] (list/map-effect ((y (list 1 2))) :max 2 (outer y))",
}


def _d5():
    return [(f"d5-{call_name}-{name}", (call, (*D5_DEFINITIONS, f"(defproc outer ((k Int)) -> Int {body})")), None)
            for call_name, call in D5_CALLS.items() for name, body in D5_BODIES.items()]


# ---------------------------------------------------------------------------------------------
# The review's probes

PROBES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "staged_authoring_review_probes.json"


def _d1_reference(body: str, binder: str = "v", pre: str = "", done: str = "(done s)") -> str:
    return (f"((u U)) -> Int (let* ({pre}(vs (list u u))) (loop/recur ((s 0)) :max 6 :on-exhausted 99 (let* ((ok "
            f"(or-else (list/head (list/map (({binder} vs)) {body})) false))) (if ok {done} (continue (+ s 1))))))")


D1_MATCH = "(match v ((A a) (> s a.n)) ((B b) true))"
D1_FIELD = "(match v ((A a) a.n) ((B b) 0))"
D1_LATER = "((u U)) -> Int (+ (pre u) " + _d1_reference(D1_MATCH, done=f"(done (+ s {E('r')}))").split(" -> Int ", 1)[1] + ")"
D3_LOCAL = "(let-proc ((g ((x Int)) -> Int (keep x))) MAP)"


def _d1_pre(body: str) -> str:
    """Procedure `pre` of the probes `d1-later-*`, its map bound with `let*` (both of its bodies had D1)."""
    return "(defproc pre ((u U)) -> Int " + _d1_reference(body).split(" -> Int ", 1)[1] + ")"
# A probe whose bound spelling holds the fixed form too, so did not build before, or that has none: a spelling
# without the form, run with the probe's definitions, those named here replacing the probe's of the same name.
PROBE_REFERENCES = {
    "d1-r-d1-inner-rebind": (_d1_reference(f"(> s {D1_FIELD})"), ()),
    "d1-r-d1-pure-call-before": (_d1_reference(f"(> (pp s) {D1_FIELD})"), ()),
    "d1-r-d1b-binder-named-pp": (_d1_reference(f"(> s {D1_FIELD.replace('match v', 'match pp')})", "pp"), ()),
    "d1-r-d1b-let-outer-and-binder": (_d1_reference(f"(> s (+ o {D1_FIELD}))", pre="(o 0) "), ()),
    "d1-r-d1b-let-star-two-reads": (_d1_reference(f"(> s (+ {D1_FIELD} (match v ((A a) 1) ((B b) 2))))"), ()),
    "d1-r-d1b-local-captures-binder": (_d1_reference(D1_MATCH), ()),
    "d1-r-d1b-loop-in-body": (_d1_reference(f"(> s {D1_FIELD})"), ()),
    "d1-r-d1-later-with-plain-pre": (D1_LATER, (_d1_pre("(if (= v.variant A) (> s 3) true)"),)),
    "d1-r-d1-later-with-retry-pre": (D1_LATER, (_d1_pre(D1_MATCH),)),
    "d2-r-d2b-defun": ("((n Int) (xs List[Int]) (u U)) -> Int (dsel n)",
                       ("(defun dsel ((n Int)) -> Int (let* ((w (variant V HAS :xs (list n)))) (match w ((HAS h) "
                        "(list/length h.xs)) ((NO o) 0))))",)),
    "d2-r-d2b-local-body-match": ("((n Int) (xs List[Int]) (u U)) -> Int (let-proc ((g ((k Int)) -> Int (let* ((w "
                                  "(variant V HAS :xs (list k)))) (match w ((HAS h) (list/length h.xs)) ((NO o) 0))))) "
                                  "(g n))", ()),
    "d2-r-d2b-local-body-match-map": ("((n Int) (xs List[Int]) (u U)) -> Int (let-proc ((g ((k Int)) -> Int (let* ((w "
                                      "(mk2 (list/length (list/map ((x xs)) x))))) (match w ((HAS h) (list/length h.xs)) "
                                      "((NO o) o.k))))) (g n))", ()),
    "d3-r-d3-enclosing-request": ("((n Int)) -> List[Int] (let* ((a (keep 5))) (let-proc ((h ((x Int) (b Int)) -> Int "
                                  "(+ b (keep x)))) (list/map-effect ((x (list 1 2))) :max 2 (h x a))))", ()),
    "d3-r-d3-in-local": ("((n Int)) -> List[Int] " + D3_LOCAL.replace(
        "MAP", "(list/map-effect ((x (list 1 2))) :max 2 (g (+ x n)))"), ()),
    "d3-r-d3-in-proc-called-twice": ("((n Int)) -> Int (+ (list/length (q 1)) (list/length (q 2)))",
                                     ("(defproc q ((k Int)) -> List[Int] " + D3_LOCAL.replace(
                                         "MAP", "(list/map-effect ((x (list 1 2))) :max 2 (g (+ x k)))") + ")",)),
    "d3-r-d3-max-operand": ("((n Int)) -> List[Int] (let* ((m (keepp 2))) " + D3_LOCAL.replace(
        "MAP", "(list/map-effect ((x (list 1 2))) :max m (g x))") + ")", ()),
}


def _with_definitions(definitions: tuple[str, ...], replacing: tuple[str, ...]) -> tuple[str, ...]:
    head = lambda form: form.split(" ", 2)[:2]  # noqa: E731 - `(defproc name`
    return tuple(next((new for new in replacing if head(new) == head(old)), old) for old in definitions)


def _probes():
    """The probes, each bound spelling (`~b`) before its program, so that it keeps its id. A program and its
    `~b` with a reference both take the reference as their bound spelling."""
    rows = json.loads(PROBES.read_text(encoding="utf-8"))
    programs = {case_id: (run, tuple(definitions)) for case_id, run, definitions, _bound in rows}
    cases = []
    for case_id, _run, _definitions, bound in sorted(rows, key=lambda row: not row[0].endswith("~b")):
        base = case_id.removesuffix("~b")
        reference = PROBE_REFERENCES.get(base)
        if reference is not None:
            bound_case = (reference[0], _with_definitions(programs[case_id][1], reference[1]))
        else:
            bound_case = programs[bound] if bound else None
        cases.append((case_id, programs[case_id], bound_case))
    return cases


# ---------------------------------------------------------------------------------------------

def _cases():
    cases: dict[str, tuple[str, tuple[str, ...]]] = {}
    bound: dict[str, str] = {}
    seen: dict[tuple[str, tuple[str, ...]], str] = {}
    for family in (_d1, _d2, _d3, _d5, _probes):
        for case_id, case, bound_case in family():
            if case in seen:
                continue
            seen[case], cases[case_id] = case_id, case
            if bound_case is not None:
                bound[case_id] = seen.setdefault(bound_case, f"{case_id}~bound")
                cases.setdefault(bound[case_id], bound_case)
    return cases, bound


CASES, BOUND = _cases()


def observe(case_id: str, root: Path) -> list:
    """The public build of the case in `root`, which it creates: `["builds", digest]`, `["refused", codes...]`,
    `["crash", class, place]` or `["traceback", class, place]`."""
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    from tests.workflow_lisp_closed_program_helpers import build_outcome
    from tests.workflow_lisp_td21_differential_cases import _install

    run, definitions = CASES[case_id]
    _install(root, run, definitions)
    built = []
    outcome = build_outcome(lambda: built.append(build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        command_boundaries_path=root / "commands.json", workspace_root=root,
        provider_externs_path=root / "providers.json", prompt_externs_path=root / "prompts.json"))))
    return ["builds", built[0].program.digest] if built else list(outcome)


def run_value(case_id: str, root: Path):
    """`[value, command labels...]` of a public `run` of the case on the tree `orchestrator` is imported from, or
    None (`tests/workflow_lisp_td21_differential_cases.py:run_value`)."""
    from tests.workflow_lisp_td21_differential_cases import run_value as td21_run_value

    run, definitions = CASES[case_id]
    return td21_run_value(run, definitions, root)


if __name__ == "__main__":
    # With PYTHONPATH the tree to observe (the commands are in the module docstring):
    #   outcomes OUT.json               on an export of `main`: every case's build;
    #   pins MAIN.json OUT.json         on the tip: the build of every case whose build differs from MAIN.json;
    #   bound-values PINS.json OUT.json on an export of `main`: for each pinned case that builds and has a
    #                                   bound spelling, that spelling's value and command log (None where it
    #                                   does not run).
    import sys
    import tempfile

    mode, *paths = sys.argv[1:]
    given = json.loads(Path(paths[0]).read_text(encoding="utf-8")) if mode != "outcomes" else {}
    with tempfile.TemporaryDirectory() as scratch:
        if mode == "outcomes":
            result = {case_id: observe(case_id, Path(scratch) / str(index)) for index, case_id in enumerate(CASES)}
        elif mode == "pins":
            result = {case_id: observe(case_id, Path(scratch) / str(index)) for index, case_id in enumerate(CASES)}
            result = {case_id: outcome for case_id, outcome in result.items() if outcome != given[case_id]}
        else:
            result = {case_id: run_value(BOUND[case_id], Path(scratch) / str(index))
                      for index, case_id in enumerate(sorted(given))
                      if given[case_id][0] == "builds" and case_id in BOUND}
    Path(paths[-1]).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
