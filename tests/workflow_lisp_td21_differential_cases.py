"""Programs around the fixes of defect backlog TD2, TD1 (D4, D19, D20) and D21, for the differential corpus
`tests/test_workflow_lisp_td21_differential.py`: each is the body of module `m` at target 2.40, entry `run`, built
beside the stand-in command `c`, the provider extern `providers.review` and the prompt `prompts.base`.

`CASES` maps an id to `(run, definitions)`. The families of the reviews of the branch (`td2-`, `td2b-`, `td1-`,
`extra-`, `r1-`, `b3-`, `left-`) are kept as written there; the `x-` families cross each fixed shape, every loop
and map operand position and the contexts of a `cond` in a `match` subject with pure and effectful parts.

The expectations file is written from an export of `main` at `e2cbc14c` (the compiler before the fixes):

    git archive e2cbc14c | tar -x -C EXPORT
    cd EXPORT && PYTHONPATH=EXPORT python -B TREE/tests/workflow_lisp_td21_differential_cases.py \
        TREE/tests/fixtures/workflow_lisp/td21_differential_main.json
"""

from __future__ import annotations

import json
from pathlib import Path



def _td2():
    U = "(defunion U (A (n Int)) (B (why String)))"
    V = "(defunion V (A (n Int)) (B (n Int)))"            # a field every variant has, one type
    W = "(defunion W (P (n Int)) (Q (n String)))"         # a field of one name, two types
    R = "(defrecord S (u U) (k Int))"
    A3 = 'u={"variant":"A","n":3}'
    B = 'u={"variant":"B","why":"no"}'
    F = "(defproc f ((x U)) -> Int (match x ((A a) a.n) ((B b) 0)))"
    INC = "(defproc inc ((x Int)) -> Int (+ x 1))"
    MAC = "(defmacro read-n (s) (match s ((A a) s.n) ((B b) 0)))"
    MAC_A = "(defmacro with-a (body) (let* ((a (variant U A :n 100))) body))"


    def E(label, result, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    CASES = [
        ("plan", "((u U)) -> Int (match u ((A a) u.n) ((B b) 0))", (U,), (A3,)),
        ("underscore-binder", "((u U)) -> Int (match u ((A _) u.n) ((B _) 0))", (U,), (A3,)),
        ("no-binder", "((u U)) -> Int (match u ((A) u.n) ((B) 0))", (U,), (A3,)),
        ("binder-is-subject", "((u U)) -> Int (match u ((A u) u.n) ((B b) 0))", (U,), (A3,)),
        ("rebound-subject-plain", "((u U)) -> Int (match u ((A a) (let* ((u (variant U A :n 9))) u.n)) ((B b) 0))", (U,), (A3,)),
        ("rebound-subject-if", "((u U)) -> Int (match u ((A a) (let* ((u (variant U A :n 9))) (if (= u.variant A) u.n 0))) ((B b) 0))", (U,), (A3,)),
        ("binder-hidden-let", "((u U)) -> Int (match u ((A a) (let* ((a 5)) (+ a u.n))) ((B b) 0))", (U,), (A3,)),
        ("binder-hidden-inner-match", "((u U) (v U)) -> Int (match u ((A a) (match v ((A a) (+ u.n (* 10 a.n))) ((B b) 0))) ((B b) 0))",
         (U,), (A3, 'v={"variant":"A","n":4}')),
        ("binder-hidden-loop", "((u U)) -> Int (match u ((A a) (loop/recur ((a 0)) :max 5 :on-exhausted a (if (> a u.n) (done a) (continue (+ a 1))))) ((B b) 0))", (U,), (A3,)),
        ("binder-hidden-map", "((u U)) -> Int (match u ((A a) (list/length (list/map ((a (list 1 2))) (+ a u.n)))) ((B b) 0))", (U,), (A3,)),
        ("binder-hidden-letproc-param", "((u U)) -> Int (match u ((A a) (let-proc ((g ((a Int)) -> Int (+ a u.n))) (g 10))) ((B b) 0))", (U,), (A3,)),
        ("nested-twice", "((u U)) -> Int (match u ((A a) (match u ((A a2) (+ u.n a2.n)) ((B b2) 0))) ((B b) 0))", (U,), (A3,)),
        ("nested-inner-other-arm", "((u U)) -> Int (match u ((A a) (match u ((A a2) u.n) ((B b2) (+ 1 0)))) ((B b) (match u ((A a3) 7) ((B b3) 8))))", (U,), (A3,)),
        ("nested-inner-wrong-variant-read", '((u U)) -> String (match u ((A a) (match u ((A a2) "x") ((B b2) u.why))) ((B b) "y"))', (U,), (A3,)),
        ("field-path-subject", "((s S)) -> Int (match s.u ((A a) s.u.n) ((B b) 0))", (U, R), ('s={"u":{"variant":"A","n":3},"k":1}',)),
        ("field-path-subject-binder", "((s S)) -> Int (match s.u ((A a) a.n) ((B b) 0))", (U, R), ('s={"u":{"variant":"A","n":3},"k":1}',)),
        ("loop-state-subject", "() -> Int (loop/recur ((s (variant U A :n 2))) :max 3 :on-exhausted 0 (match s ((A a) (done s.n)) ((B b) (done 0))))", (U,), ()),
        ("loop-state-subject-fn", "() -> Int (loop/recur :max 3 :state (variant U A :n 2) :on-exhausted 0 (fn (s) (match s ((A a) (done s.n)) ((B b) (done 0)))))", (U,), ()),
        ("in-cond", "((u U)) -> Int (match u ((A a) (cond ((> u.n 2) u.n) (else 0))) ((B b) 0))", (U,), (A3,)),
        ("in-if-condition", "((u U)) -> Int (match u ((A a) (if (> u.n 2) 1 0)) ((B b) 0))", (U,), (A3,)),
        ("in-letproc-local-body", "((u U)) -> Int (match u ((A a) (let-proc ((g () -> Int (+ u.n 1))) (g))) ((B b) 0))", (U,), (A3,)),
        ("match-inside-letproc", "((u U)) -> Int (let-proc ((g ((x U)) -> Int (match x ((A a) x.n) ((B b) 0)))) (g u))", (U,), (A3,)),
        ("in-defproc", "((u U)) -> Int (f2 u)", (U, "(defproc f2 ((x U)) -> Int (match x ((A a) x.n) ((B b) 0)))"), (A3,)),
        ("in-macro", "((u U)) -> Int (read-n u)", (U, MAC), (A3,)),
        ("macro-binder-around-read", "((u U)) -> Int (match u ((A a) (with-a u.n)) ((B b) 0))", (U, MAC_A), (A3,)),
        ("in-loop-body", "((u U)) -> Int (match u ((A a) (loop/recur ((s 0)) :max 9 :on-exhausted s (if (> s u.n) (done s) (continue (+ s 1))))) ((B b) 0))", (U,), (A3,)),
        ("in-serial-map", f"((u U)) -> Int (match u ((A a) (list/length (list/map-effect ((x (list 1 2))) :max u.n {E('m', 1)}))) ((B b) 0))", (U,), (A3,)),
        ("in-map-body", "((u U)) -> List[Int] (match u ((A a) (list/map ((x (list 1 2))) (+ x u.n))) ((B b) (list)))", (U,), (A3,)),
        ("shared-field", "((v V)) -> Int (match v ((A a) v.n) ((B b) (+ v.n 100)))", (V,), ('v={"variant":"B","n":5}',)),
        ("same-name-two-types-P", "((w W)) -> Int (match w ((P p) w.n) ((Q q) (+ 0 1)))", (W,), ('w={"variant":"P","n":4}',)),
        ("same-name-two-types-Q", '((w W)) -> String (match w ((P p) "p") ((Q q) w.n))', (W,), ('w={"variant":"Q","n":"qq"}',)),
        ("other-variant-refused", "((u U)) -> String (match u ((A a) u.why) ((B b) b.why))", (U,), (A3,)),
        ("subject-passed-whole", "((u U)) -> Int (match u ((A a) (+ (f u) u.n)) ((B b) 0))", (U, F), (A3,)),
        ("subject-returned-whole", "((u U)) -> U (match u ((A a) u) ((B b) u))", (U,), (A3,)),
        ("tag-read-in-arm", "((u U)) -> Int (match u ((A a) (if (= u.variant A) u.n 0)) ((B b) 0))", (U,), (A3,)),
        ("effect-in-arm", f'((u U)) -> Int (match u ((A a) (+ u.n {E("e", 1)})) ((B b) 0))', (U,), (A3,)),
        ("latent-if-narrowed-whole", "((u U)) -> Int (if (= u.variant A) (f u) 0)", (U, F), (A3,)),
        ("latent-if-narrowed-return", "((u U)) -> U (if (= u.variant A) u u)", (U,), (A3,)),
    ]
    return CASES


def _td2b():
    U = "(defunion U (A (n Int)) (B (why String)))"
    A3 = 'u={"variant":"A","n":3}'
    MAC = "(defmacro n-if-a (x) (if (= x.variant A) x.n 0))"
    F = "(defproc f ((x U)) -> Int (match x ((A a) (if (= x.variant A) x.n 0)) ((B b) 0)))"


    def E(label, result, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    CASES = [
        ("tag-if", "((u U)) -> Int (match u ((A a) (if (= u.variant A) u.n 0)) ((B b) 0))", (U,), (A3,)),
        ("tag-cond", "((u U)) -> Int (match u ((A a) (cond ((= u.variant A) u.n) (else 0))) ((B b) 0))", (U,), (A3,)),
        ("tag-if-both-reads", "((u U)) -> Int (match u ((A a) (if (= u.variant A) (+ u.n a.n) 0)) ((B b) 0))", (U,), (A3,)),
        ("tag-if-effect", f"((u U)) -> Int (match u ((A a) (if (= u.variant A) (+ u.n {E('e', 1)}) 0)) ((B b) 0))", (U,), (A3,)),
        ("tag-if-argv", f'((u U)) -> Int (match u ((A a) (if (= u.variant A) (command-result c :argv ("python" "c.py" "argv" u.n) :returns Int) 0)) ((B b) 0))', (U,), (A3,)),
        ("tag-if-macro", "((u U)) -> Int (match u ((A a) (n-if-a u)) ((B b) 0))", (U, MAC), (A3,)),
        ("tag-if-in-defproc", "((u U)) -> Int (f u)", (U, F), (A3,)),
        ("tag-if-other-arm", '((u U)) -> String (match u ((A a) "a") ((B b) (if (= u.variant B) u.why "z")))', (U,), ('u={"variant":"B","why":"w"}',)),
        ("tag-if-in-loop", "((u U)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (match u ((A a) (if (= u.variant A) (done u.n) (done 0))) ((B b) (done 0))))", (U,), (A3,)),
        ("binder-read-only", "((u U)) -> Int (match u ((A a) (if (= u.variant A) a.n 0)) ((B b) 0))", (U,), (A3,)),
    ]
    return CASES


def _td1():
    U = "(defunion U (A (n Int)) (B (why String)))"
    SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
    MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
    MK2 = "(defproc mk2 ((a Int) (b Int)) -> Shape (variant Shape CIRCLE :r (+ a b)))"
    PR = "(defrecord PR (k Int))"
    A3 = 'u={"variant":"A","n":3}'
    B = 'u={"variant":"B","why":"x"}'
    ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"


    def E(label, result, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    W = f"(defworkflow w ((n Int)) -> Int {E('w', 1)})"
    WP = "(defworkflow wp ((n Int)) -> Int (+ n 0))"
    PE = f"(defproc pe ((n Int)) -> Int {E('p', 1)})"
    PROV = '(provider-result providers.review :prompt prompts.base :inputs (n) :model "m" :effort "low" :returns PR)'

    CASES = []
    # ---- D4
    COUNT = ":on-exhausted s (if (> s 10) (done s) (continue (+ s 1)))"
    MM = "(match u ((A a) a.n) ((B b) 1))"
    for inputs, tag in ((A3, "A"), (B, "B")):
        CASES += [
            (f"d4-max-{tag}", f"((u U)) -> Int (loop/recur ((s 0)) :max {MM} {COUNT})", (U,), (inputs,)),
            (f"d4-max-fn-{tag}", f"((u U)) -> Int (loop/recur :max {MM} :state 0 :on-exhausted s (fn (s) (if (> s 10) (done s) (continue (+ s 1)))))", (U,), (inputs,)),
            (f"d4-state-{tag}", "((u U)) -> Int (loop/recur ((s (match u ((A a) a.n) ((B b) 7)))) :max 2 :on-exhausted 9 (done s))", (U,), (inputs,)),
            (f"d4-state-fn-{tag}", "((u U)) -> Int (loop/recur :max 2 :state (match u ((A a) a.n) ((B b) 7)) :on-exhausted 9 (fn (s) (done s)))", (U,), (inputs,)),
            (f"d4-map-{tag}", f"((u U)) -> List[Int] (list/map-effect ((x (list 1 2 3))) :max {MM} {E('m', 1)})", (U,), (inputs,)),
        ]
    CASES += [
        ("d4-max-effect-match", f"((u U)) -> Int (loop/recur ((s 0)) :max (match u ((A a) {E('k', 2)}) ((B b) 1)) {COUNT})", (U,), (A3,)),
        ("d4-state-effect-match", f"((u U)) -> Int (loop/recur ((s (match u ((A a) {E('k', 2)}) ((B b) 7)))) :max 2 :on-exhausted 9 (done s))", (U,), (A3,)),
        ("d4-map-max-effect-match", f"((u U)) -> List[Int] (list/map-effect ((x (list 1 2 3))) :max (match u ((A a) {E('k', 3)}) ((B b) 1)) {E('m', 1)})", (U,), (A3,)),
        ("d4-onexh-match", "((u U)) -> Int (loop/recur ((s 0)) :max 1 :on-exhausted (match u ((A a) a.n) ((B b) 0)) (if (> s 5) (done s) (continue (+ s 1))))", (U,), (A3,)),
        ("d4-onexh-effect-match", f"((u U)) -> Int (loop/recur ((s 0)) :max 1 :on-exhausted (match u ((A a) {E('k', 2)}) ((B b) 0)) (if (> s 5) (done s) (continue (+ s 1))))", (U,), (A3,)),
        ("d4-parallel-max-match", f"((u U)) -> List[Int] (list/map-effect ((x (list 1 2))) :max {MM} :parallel 2 {E('m', 1)})", (U,), (A3,)),
        ("d4-max-nested-if", f"((n Int)) -> Int (loop/recur ((s 0)) :max (if (> n 0) (if (> n 1) 2 3) 4) {COUNT})", (), ("n=1",)),
        ("d4-max-cond3", f"((n Int)) -> Int (loop/recur ((s 0)) :max (cond ((> n 5) 1) ((> n 0) 3) (else 4)) {COUNT})", (), ("n=1",)),
        ("d4-state-nested-if", "((n Int)) -> Int (loop/recur ((s (if (> n 0) (if (> n 1) 2 3) 4))) :max 2 :on-exhausted 9 (done s))", (), ("n=1",)),
        ("d4-state-cond3", "((n Int)) -> Int (loop/recur ((s (cond ((> n 5) 1) ((> n 0) 3) (else 4)))) :max 2 :on-exhausted 9 (done s))", (), ("n=1",)),
        ("d4-max-if-holding-match", f"((u U) (n Int)) -> Int (loop/recur ((s 0)) :max (if (> n 0) {MM} 4) {COUNT})", (U,), (A3, "n=1")),
        ("d4-max-op-match", f"((u U)) -> Int (loop/recur ((s 0)) :max (+ 1 {MM}) {COUNT})", (U,), (A3,)),
        ("d4-max-let-match", f"((u U)) -> Int (loop/recur ((s 0)) :max (let* ((k 1)) (match u ((A a) (+ k a.n)) ((B b) 1))) {COUNT})", (U,), (A3,)),
        ("d4-max-match-let-arm", f"((u U)) -> Int (loop/recur ((s 0)) :max (match u ((A a) (let* ((k 1)) (+ k a.n))) ((B b) 1)) {COUNT})", (U,), (A3,)),
        ("d4-max-match-if-arm", f"((u U)) -> Int (loop/recur ((s 0)) :max (match u ((A a) (if (> a.n 2) 2 1)) ((B b) 1)) {COUNT})", (U,), (A3,)),
        ("d4-max-match-call-subject", f"((n Int)) -> Int (loop/recur ((s 0)) :max (match (mkshape n) {ARMS}) {COUNT})", (SHAPE, MK), ("n=2",)),
        ("d4-state-record-match", "((u U)) -> Int (loop/recur ((s (loop-state (i Int (match u ((A a) a.n) ((B b) 7)))))) :max 2 :on-exhausted 9 (done s.i))", (U,), (A3,)),
        ("d4-in-defproc", "((u U)) -> Int (lp u)", (U, f"(defproc lp ((u U)) -> Int (loop/recur ((s 0)) :max {MM} {COUNT}))"), (A3,)),
        ("d4-max-if-control", f"((n Int)) -> Int (loop/recur ((s 0)) :max (if (> n 0) 3 1) {COUNT})", (), ("n=1",)),
    ]

    # ---- D19 and neighbours: each effect under one and two levels of `if`, `cond`, `match`
    LOOP = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) (EXIT VALUE)))"
    LOOP_PR = f"((n Int)) -> Int (loop/recur ((s (record PR :k 0))) :max 2 :on-exhausted 0 (if (> s.k 0) (done s.k) (EXIT VALUE)))"
    SHAPES = {
        "L1-if": "(if (> n 0) X Z)",
        "L2-if": "(if (> n 0) (if (> n 0) X Z) Z)",
        "L2-if-else": "(if (> n 0) Z (if (> n 0) X Z))",
        "L1-cond": "(cond ((> n 0) X) (else Z))",
        "L2-cond": "(cond ((> n 5) Z) ((> n 0) X) (else Z))",
        "L1-match": "(match (variant U A :n n) ((A a) X) ((B b) Z))",
        "L2-match-if": "(match (variant U A :n n) ((A a) (if (> n 0) X Z)) ((B b) Z))",
        "L2-if-match": "(if (> n 0) (match (variant U A :n n) ((A a) X) ((B b) Z)) Z)",
    }
    EFFECTS = {
        "cmd": (E("e", 1), "0", LOOP, ()),
        "wf": ("(call w :n n)", "0", LOOP, (W,)),
        "wf-pure": ("(call wp :n n)", "0", LOOP, (WP,)),
        "proc": ("(pe n)", "0", LOOP, (PE,)),
        "prov": (PROV, "(record PR :k 0)", LOOP_PR, (PR,)),
    }
    for ename, (x, z, loop, defs) in EFFECTS.items():
        for sname, shape in SHAPES.items():
            value = shape.replace("X", x).replace("Z", z)
            CASES.append((f"d19-{ename}-{sname}", loop.replace("EXIT", "continue").replace("VALUE", value), (U, *defs), ("n=1",)))
        value = SHAPES["L2-if"].replace("X", x).replace("Z", z)
        CASES.append((f"d19-{ename}-L2-if-done", loop.replace("EXIT", "done").replace("VALUE", value), (U, *defs), ("n=1",)))
        CASES.append((f"d19-{ename}-L2-if-bound", loop.replace("(EXIT VALUE)", f"(let* ((next {value})) (continue next))"), (U, *defs), ("n=1",)))

    # ---- D20
    E1_E2 = f"(if (> n 0) {E('e1', 1)} {E('e2', 2)})"
    SUBJECTS = {
        "call-if": f"(mkshape {E1_E2})",
        "let-if": f"(let* ((r {E1_E2})) (variant Shape CIRCLE :r r))",
        "call-match": f"(mkshape (match (variant U A :n n) ((A a) {E('e1', 1)}) ((B b) {E('e2', 2)})))",
        "call-plus-match": f"(mkshape (+ {E('e1', 1)} (match (variant U A :n n) ((A a) a.n) ((B b) 0))))",
        "call-cond": f"(mkshape (cond ((> n 5) {E('e1', 1)}) ((> n 0) {E('e2', 2)}) (else 0)))",
        "let-cond": f"(let* ((r (cond ((> n 0) {E('e1', 1)}) (else {E('e2', 2)})))) (variant Shape CIRCLE :r r))",
        "call-loop": f"(mkshape (loop/recur ((s 0)) :max 2 :on-exhausted 0 (done {E('e1', 1)})))",
        "let-nested-let": f"(let* ((r (let* ((q {E1_E2})) q))) (variant Shape CIRCLE :r r))",
        "call2-if": f"(mk2 {E1_E2} 1)",
        "call-pure-if": "(mkshape (if (> n 0) 1 2))",
        "if-subject": f"(if (> n 0) (mkshape {E('e1', 1)}) (mkshape {E('e2', 2)}))",
        "call-wf-if": "(mkshape (if (> n 0) (call w :n n) 0))",
        "call-let-if": f"(mkshape (let* ((q {E1_E2})) q))",
    }
    for sname, subject in SUBJECTS.items():
        for n in (1, 0):
            CASES.append((f"d20-{sname}-n{n}", f"((n Int)) -> Int (match {subject} {ARMS})", (U, SHAPE, MK, MK2, W), (f"n={n}",)))
            CASES.append((f"d20-{sname}-n{n}-bound", f"((n Int)) -> Int (let* ((shape {subject})) (match shape {ARMS}))",
                          (U, SHAPE, MK, MK2, W), (f"n={n}",)))

    # ---- D21
    BODY = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s BODY)"
    D21 = {
        "one-branch": "(let* ((x (if (> n 0) (done 1) 5))) (done x))",
        "tail": "(let* ((x 1)) (done x))",
        "inner-loop-done": "(let* ((x (loop/recur ((t 0)) :max 2 :on-exhausted 0 (done 7)))) (done x))",
        "inner-loop-cont": "(let* ((x (loop/recur ((t 0)) :max 5 :on-exhausted 0 (if (> t 2) (done t) (continue (+ t 1)))))) (done x))",
        "inner-loop-outer-exit": "(let* ((x (loop/recur ((t 0)) :max 2 :on-exhausted 0 (done 7)))) (if (> x 5) (done x) (continue (+ s 1))))",
        "inner-loop-d21": "(let* ((x (loop/recur ((t 0)) :max 2 :on-exhausted 0 (let* ((y (done 7))) y)))) (done x))",
        "unused-done": "(let* ((x (done 1))) (done 2))",
        "in-if-branch": "(if (> n 0) (let* ((x (done 1))) x) (done 2))",
        "continue-only": "(let* ((x (continue (+ s 1)))) x)",
        "operand-done": "(let* ((x (+ 1 (done 1)))) (done x))",
        "cond-all-exit-else": "(let* ((x (cond ((> n 5) (done 1)) (else (done 2))))) (done x))",
        "match-all-exit": "(let* ((x (match (variant U A :n n) ((A a) (done 1)) ((B b) (done 2))))) (done x))",
        "if-both-done": "(let* ((x (if (> n 0) (done 1) (done 2)))) x)",
        "map-body-done": "(let* ((x (list/map-effect ((i (list 1))) :max 1 (done 1)))) (done 2))",
        "letproc-done": "(let-proc ((g () -> Int (done 1))) (g))",
    }
    for name, body in D21.items():
        CASES.append((f"d21-{name}", BODY.replace("BODY", body), (U,), ("n=1",)))
        CASES.append((f"d21-{name}-fn", "((n Int)) -> Int (loop/recur :max 2 :state 0 :on-exhausted s (fn (s) BODY))".replace("BODY", body), (U,), ("n=1",)))
    CASES += [
        ("d21-outside-loop", "((n Int)) -> Int (let* ((x (done 1))) x)", (), ("n=1",)),
        ("d21-onexh", "((n Int)) -> Int (loop/recur ((s 0)) :max 1 :on-exhausted (let* ((x (done 1))) x) (continue (+ s 1)))", (), ("n=1",)),
        ("d21-in-defproc", "((n Int)) -> Int (lp n)", ("(defproc lp ((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (done 1))) x)))",), ("n=1",)),
    ]

    # ---- extra D19 neighbours: the effect in the top arm's prefix; an agent-free request is not probed
    CASES += [
        ("d19x-cmd-top-prefix", LOOP.replace("EXIT", "continue").replace("VALUE", f"(if (> n 0) (let* ((y {E('e', 1)})) (if (> n 0) y 0)) 0)"), (U,), ("n=1",)),
        ("d19x-cmd-L3-if", LOOP.replace("EXIT", "continue").replace("VALUE", f"(if (> n 0) (if (> n 0) (if (> n 0) {E('e', 1)} 0) 0) 0)"), (U,), ("n=1",)),
        ("d19x-wf-L2-if-fn", "((n Int)) -> Int (loop/recur :max 2 :state 0 :on-exhausted 0 (fn (s) (if (> s 0) (done s) (continue (if (> n 0) (if (> n 0) (call w :n n) 0) 0)))))", (U, W), ("n=1",)),
    ]
    REC = "(defrecord P2 (a Int) (b Int))"
    CASES += [
        ("e1-cont-field", f"((n Int)) -> Int (loop/recur ((s (record P2 :a 0 :b 0))) :max 2 :on-exhausted 0 (if (> s.a 0) (done s.a) (continue (record P2 :a {E('e', 1)} :b 1))))", (REC,), ("n=1",)),
        ("e1-cont-field-bound", f"((n Int)) -> Int (loop/recur ((s (record P2 :a 0 :b 0))) :max 2 :on-exhausted 0 (if (> s.a 0) (done s.a) (let* ((g (record P2 :a {E('e', 1)} :b 1))) (continue g))))", (REC,), ("n=1",)),
    ]
    CASES += [
        ("e1-subject-variant", f"((n Int)) -> Int (match (variant Shape CIRCLE :r {E('e1', 1)}) {ARMS})", (SHAPE,), ("n=1",)),
        ("e1-subject-variant-bound", f"((n Int)) -> Int (let* ((shape (variant Shape CIRCLE :r {E('e1', 1)}))) (match shape {ARMS}))", (SHAPE,), ("n=1",)),
        ("e1-subject-call", f"((n Int)) -> Int (match (mkshape {E('e1', 1)}) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("e1-subject-call-bound", f"((n Int)) -> Int (let* ((shape (mkshape {E('e1', 1)}))) (match shape {ARMS}))", (SHAPE, MK), ("n=1",)),
        ("e1-cont-if-top", f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) (continue (if (> n 0) {E('e', 1)} 0))))", (), ("n=1",)),
        ("e1-cont-if-top-bound", f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) (let* ((next (if (> n 0) {E('e', 1)} 0))) (continue next))))", (), ("n=1",)),
    ]
    return CASES


def _extra():
    U = "(defunion U (A (n Int)) (B (why String)))"
    SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
    MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
    MKU = "(defproc mku ((n Int)) -> U (variant U A :n n))"
    ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"


    def E(label, result, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    D = (U, SHAPE, MK, MKU)
    EU = E("u", '{\\"variant\\":\\"A\\",\\"n\\":4}', "U")
    CASES = [
        ("d20-if-effect-in-condition", f"((n Int)) -> Int (match (mkshape (if (> {E('c', 1)} 0) 1 2)) {ARMS})", D, ("n=1",)),
        ("d20-let-if-effect-in-condition", f"((n Int)) -> Int (match (let* ((r (if (> {E('c', 1)} 0) 1 2))) (variant Shape CIRCLE :r r)) {ARMS})", D, ("n=1",)),
        ("d20-match-effect-in-subject", f"((n Int)) -> Int (match (mkshape (match {EU} ((A a) a.n) ((B b) 0))) {ARMS})", D, ("n=1",)),
        ("d20-let-match-effect-in-subject", f"((n Int)) -> Int (match (let* ((r (match {EU} ((A a) a.n) ((B b) 0)))) (variant Shape CIRCLE :r r)) {ARMS})", D, ("n=1",)),
        ("d20-let-plain-effect", f"((n Int)) -> Int (match (let* ((r {E('e1', 1)})) (variant Shape CIRCLE :r r)) {ARMS})", D, ("n=1",)),
        ("d20-let-pure-if", "((n Int)) -> Int (match (let* ((r (if (> n 0) 1 2))) (variant Shape CIRCLE :r r)) " + ARMS + ")", D, ("n=1",)),
        ("d20-let-if-effect-unused", f"((n Int)) -> Int (match (let* ((r (if (> n 0) {E('e1', 1)} 2))) (variant Shape CIRCLE :r 7)) {ARMS})", D, ("n=1",)),
        ("d21-done-x", "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (done 1))) (done x)))", (), ("n=1",)),
        ("d21-if-both-done-x", "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (if (> n 0) (done 1) (done 2)))) (done x)))", (), ("n=1",)),
        ("d21-if-done-continue-x", "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (if (> n 0) (done 1) (continue (+ s 1))))) (done x)))", (), ("n=1",)),
        ("d21-cond-done-continue", "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (cond ((> n 5) (done 1)) (else (continue (+ s 1)))))) (done 2)))", (), ("n=1",)),
        ("d21-continue-continue-x", "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (if (> s 0) (done s) (let* ((x (continue (+ s 1)))) x)))", (), ("n=1",)),
    ]
    return CASES


U = "(defunion U (A (n Int)) (B (why String)))"
SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
RK = "(defrecord Rk (n Int))"


def E(label, result=1, type_="Int"):
    return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


PE = f"(defproc pe ((r Int)) -> Shape (variant Shape CIRCLE :r (+ r {E('pe')})))"
EU = E("u", '{\\"variant\\":\\"A\\",\\"n\\":4}', "U")


def _x_td2():
    """A read R of the subject `u` (or of the arm's binder) in arm A, inside each context."""
    contexts = {
        "plain": "R",
        "tag-if": "(if (= u.variant A) R 0)",
        "tag-if-else": "(if (= u.variant B) 0 R)",
        "tag-if-nested": "(if (> 1 0) (if (= u.variant A) R 0) 0)",
        "tag-cond": "(cond ((= u.variant B) 0) ((= u.variant A) R) (else 0))",
        "nontag-if": "(if (> 1 0) R 0)",
        "operand": "(+ 1 R)",
        "let-body": "(let* ((k 1)) (+ k R))",
        "let-binding": "(let* ((k R)) k)",
        "effect-beside": f"(+ R {E('e')})",
        "effect-before": f"(let* ((k {E('e')})) (+ k R))",
        "argv": '(command-result c :argv ("python" "c.py" "argv" R) :returns Int)',
        "nested-match": "(match u ((A a2) R) ((B b2) 1))",
        "nested-other": "(match (variant U A :n 5) ((A z) (+ z.n R)) ((B y) 0))",
        "binder-hidden": "(let* ((a (record Rk :n 9))) R)",
        "loop-done": "(loop/recur ((s 0)) :max 2 :on-exhausted 0 (done R))",
        "tag-if-effect": f"(if (= u.variant A) (+ R {E('e')}) 0)",
    }
    cases = []
    for cname, context in contexts.items():
        for rname, read in (("subject", "u.n"), ("binder", "a.n")):
            cases.append((f"x-td2-{cname}-{rname}", f"((u U)) -> Int (match u ((A a) {context.replace('R', read)}) ((B b) 0))",
                          (U, RK)))
    return cases


def _x_d4():
    """Each value V as a loop's `:max` or `:state` or a serial map's `:max`."""
    values = {
        "match": "(match u ((A a) a.n) ((B b) 1))",
        "match-subject-read": "(match u ((A a) u.n) ((B b) 1))",
        "match-effect-arm": f"(match u ((A a) {E('k', 2)}) ((B b) 1))",
        "match-effect-subject": f"(match {EU} ((A a) a.n) ((B b) 1))",
        "if": "(if (> n 0) 3 1)",
        "if-effect-cond": f"(if (> {E('k')} 0) 3 1)",
        "if-effect-branch": f"(if (> n 0) {E('k', 3)} 1)",
        "cond": "(cond ((> n 5) 1) ((> n 0) 3) (else 4))",
        "let-match": "(let* ((k 1)) (match u ((A a) (+ k a.n)) ((B b) 1)))",
        "if-match": "(if (> n 0) (match u ((A a) a.n) ((B b) 1)) 4)",
        "plus-match": "(+ 1 (match u ((A a) a.n) ((B b) 1)))",
        "cond-match": "(cond ((> n 5) 1) ((> n 0) (match u ((A a) a.n) ((B b) 1))) (else 4))",
        "let-if-match": "(let* ((k (if (> n 0) (match u ((A a) a.n) ((B b) 1)) 4))) k)",
    }
    positions = {
        "loop-max": "(loop/recur ((s 0)) :max V :on-exhausted s (if (> s 10) (done s) (continue (+ s 1))))",
        "fn-max": "(loop/recur :max V :state 0 :on-exhausted s (fn (s) (if (> s 10) (done s) (continue (+ s 1)))))",
        "loop-state": "(loop/recur ((s V)) :max 2 :on-exhausted 9 (done s))",
        "fn-state": "(loop/recur :max 2 :state V :on-exhausted 9 (fn (s) (done s)))",
        "map-max": f"(list/length (list/map-effect ((x (list 1 2))) :max V {E('m')}))",
        "map-max-bound": f"(let* ((ys (list/map-effect ((x (list 1 2))) :max V {E('m')}))) (list/length ys))",
    }
    return [(f"x-d4-{pname}-{vname}", f"((u U) (n Int)) -> Int {position.replace('V', value)}", (U,))
            for pname, position in positions.items() for vname, value in values.items()]


def _x_d20():
    """Each argument or binding value X under each spelling of the subject."""
    values = {
        "if-cond": f"(if (> {E('c')} 0) 1 2)",
        "if-then": f"(if (> n 0) {E('e1')} 2)",
        "if-both": f"(if (> n 0) {E('e1')} {E('e2', 2)})",
        "if-pure": "(if (> n 0) 1 2)",
        "match-subject": f"(match {EU} ((A a) a.n) ((B b) 0))",
        "match-arm": f"(match (variant U A :n n) ((A a) {E('e1')}) ((B b) 0))",
        "cond": f"(cond ((> n 5) {E('e1')}) ((> n 0) {E('e2', 2)}) (else 0))",
        "plus-match": f"(+ {E('e1')} (match (variant U A :n n) ((A a) a.n) ((B b) 0)))",
        "let-if": f"(let* ((q (if (> n 0) {E('e1')} 2))) q)",
        "plain": E("e1"),
        "cond-pure": "(cond ((> n 5) 1) (else 2))",
        "cond3-pure": "(cond ((> n 5) 1) ((> n 2) 3) (else 2))",
    }
    spellings = {
        "call": "(match (mkshape X) ((CIRCLE c) c.r) ((SQUARE s) 0))",
        "let": "(match (let* ((r X)) (variant Shape CIRCLE :r r)) ((CIRCLE c) c.r) ((SQUARE s) 0))",
        "effect-call": "(match (pe X) ((CIRCLE c) c.r) ((SQUARE s) 0))",
        "bound": "(let* ((shape (mkshape X))) (match shape ((CIRCLE c) c.r) ((SQUARE s) 0)))",
        "direct-cond": "(match (cond ((> n 5) (mkshape X)) (else (variant Shape SQUARE :side 2))) ((CIRCLE c) c.r) ((SQUARE s) 0))",
    }
    return [(f"x-d20-{sname}-{vname}", f"((n Int)) -> Int {spelling.replace('X', value)}", (U, SHAPE, MK, PE))
            for sname, spelling in spellings.items() for vname, value in values.items()]


def _x_d19():
    """Each effect X in each conditional shape, as a `continue` value, a `done` value and bound first."""
    wfs = (f"(defworkflow w ((n Int)) -> Int {E('w')})", "(defworkflow wp ((n Int)) -> Int (+ n 0))",
           "(defworkflow wv ((n Int)) -> Int (call w :n n))", "(defworkflow wpv ((n Int)) -> Int (call wp :n n))",
           f"(defproc pe ((n Int)) -> Int {E('p')})", "(defproc pp ((n Int)) -> Int (+ n 1))",
           "(defproc pw ((n Int)) -> Int (call w :n n))")
    effects = {"cmd": E("e"), "wf": "(call w :n n)", "wf-pure": "(call wp :n n)", "wf-via": "(call wv :n n)",
               "wf-pure-via": "(call wpv :n n)", "proc": "(pe n)", "proc-pure": "(pp n)", "proc-wf": "(pw n)"}
    shapes = {"L1-if": "(if (> n 0) X 0)", "L2-if": "(if (> n 0) (if (> n 0) X 0) 0)",
              "L2-else": "(if (> n 0) 0 (if (> n 0) X 0))", "L2-cond": "(cond ((> n 5) 0) ((> n 0) X) (else 0))",
              "L3-if": "(if (> n 0) (if (> n 1) 0 (if (> n 0) X 0)) 0)", "L2-cond-test": "(if (> n 0) (if (> X 0) 1 0) 0)"}
    exits = {"continue": "(continue V)", "done": "(done V)", "bound": "(let* ((next V)) (continue next))"}
    loop = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) EXIT))"
    return [(f"x-d19-{xname}-{ename}-{sname}", loop.replace("EXIT", exit_.replace("V", shape.replace("X", effect))), (U, *wfs))
            for xname, exit_ in exits.items() for ename, effect in effects.items() for sname, shape in shapes.items()]


def _r1():
    """Re-review probes after fix round 1: shapes one step from B1 and B2, M1's neighbours that build today, M2's
    shapes beside their `let*`-bound spelling, and m2's pure values holding a `match` as `:max` or `:state`."""
    U = "(defunion U (A (n Int)) (B (why String)))"
    SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
    MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
    PP = "(defproc pp ((n Int)) -> Int (+ n 1))"
    RK = "(defrecord Rk (n Int))"
    A3 = 'u={"variant":"A","n":3}'
    ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"


    def E(label, result=1, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    EU = E("u", '{\\"variant\\":\\"A\\",\\"n\\":4}', "U")
    CASES = []

    # ---- B1, one step away: the arm `(A a)` of `(match u ...)` holds CONTEXT
    B1 = {
        "cond-second-clause": "(cond ((> 1 2) 0) ((= u.variant A) u.n) (else 0))",
        "cond-after-other-tag": "(cond ((= u.variant B) 0) ((> u.n 1) u.n) (else 0))",
        "negated-else": "(if (not (= u.variant A)) 0 u.n)",
        "negated-then": "(if (not (= u.variant B)) u.n 0)",
        "and-first": "(if (and (= u.variant A) (> 1 0)) u.n 0)",
        "and-second": "(if (and (> 1 0) (= u.variant A)) u.n 0)",
        "or": "(if (or (= u.variant A) (> 0 1)) u.n 0)",
        "read-in-and-condition": "(if (and (= u.variant A) (> u.n 1)) 1 0)",
        "read-in-cond-test": "(cond ((= u.variant A) (if (> u.n 1) 1 0)) (else 0))",
        "let-between": "(if (= u.variant A) (let* ((k 1)) (+ k u.n)) 0)",
        "let-binding-between": "(if (= u.variant A) (let* ((k u.n)) k) 0)",
        "bound-boolean": "(let* ((t (= u.variant A))) (if t u.n 0))",
        "alias-test": "(let* ((v u)) (if (= v.variant A) u.n 0))",
        "nested-match-under-tag": "(if (= u.variant A) (match u ((A a2) u.n) ((B b2) 1)) 0)",
        "tag-under-nested-match": "(match u ((A a2) (if (= u.variant A) u.n 0)) ((B b2) 1))",
        "loop-in-arm-tag": "(loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (= u.variant A) (done u.n) (done 0)))",
        "tag-if-plus-free-read": "(+ u.n (if (= u.variant A) u.n 0))",
        "tag-if-map-body": "(if (= u.variant A) (list/length (list/map ((x (list 1 2))) (+ x u.n))) 0)",
    }
    for name, context in B1.items():
        CASES.append((f"b1-{name}", f"((u U)) -> Int (match u ((A a) {context}) ((B b) 0))", (U,), (A3,)))
    CASES += [
        ("b1-outer-if-around-match", "((u U)) -> Int (if (= u.variant A) (match u ((A a) u.n) ((B b) 0)) 0)", (U,), (A3,)),
        ("b1-outer-if-else-around-match", "((u U)) -> Int (if (= u.variant B) 0 (match u ((A a) u.n) ((B b) 0)))", (U,), (A3,)),
        ("b1-outer-cond-around-match", "((u U)) -> Int (cond ((= u.variant A) (match u ((A a) u.n) ((B b) 0))) (else 0))", (U,), (A3,)),
        ("b1-outer-if-around-match-binder", "((u U)) -> Int (if (= u.variant A) (match u ((A a) a.n) ((B b) 0)) 0)", (U,), (A3,)),
    ]

    # ---- B2, one step away: the subject `(mkshape X)`, and its `let*`-bound spelling
    B2 = {
        "inner-match-subject": f"(match {EU} ((A a) a.n) ((B b) 0))",
        "cond-condition": f"(cond ((> {E('c')} 0) 1) (else 2))",
        "cond3-second-condition": f"(cond ((> n 5) 1) ((> {E('c')} 0) 2) (else 3))",
        "loop-max": f"(loop/recur ((s 0)) :max {E('k', 2)} :on-exhausted s (if (> s 5) (done s) (continue (+ s 1))))",
        "loop-state": f"(loop/recur ((s {E('k', 2)})) :max 2 :on-exhausted s (done s))",
        "and-condition": f"(if (and (> {E('c')} 0) (> n 0)) 1 2)",
        "map-source-effect": f"(list/length (list/map-effect ((x (list 1 2))) :max 2 {E('m')}))",
        "pure-call-arg": f"(pp {E('e1')})",
        "effect-beside-pure-if": f"(+ {E('e1')} (if (> n 0) 1 2))",
        "if-condition-and-branch": f"(if (> {E('c')} 0) {E('e1')} 2)",
    }
    for name, x in B2.items():
        for n in (1, 0):
            CASES.append((f"b2-{name}-n{n}", f"((n Int)) -> Int (match (mkshape {x}) {ARMS})", (U, SHAPE, MK, PP), (f"n={n}",)))
            CASES.append((f"b2-{name}-n{n}-bound", f"((n Int)) -> Int (let* ((shape (mkshape {x}))) (match shape {ARMS}))",
                          (U, SHAPE, MK, PP), (f"n={n}",)))
    CASES += [
        ("b2-if-subject-effect-condition", f"((n Int)) -> Int (match (if (> {E('c')} 0) (mkshape 1) (mkshape 2)) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("b2-let-subject-loop-max", f"((n Int)) -> Int (match (let* ((r (loop/recur ((s 0)) :max {E('k', 2)} :on-exhausted s (if (> s 5) (done s) (continue (+ s 1)))))) (variant Shape CIRCLE :r r)) {ARMS})", (SHAPE,), ("n=1",)),
        ("b2-pure-cond-subject", f"((n Int)) -> Int (match (cond ((> n 0) (mkshape 1)) (else (mkshape 2))) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("b2-pure-cond-arg", f"((n Int)) -> Int (match (mkshape (cond ((> n 0) 1) (else 2))) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("b2-pure-cond-in-variant", f"((n Int)) -> Int (match (variant Shape CIRCLE :r (cond ((> n 0) 1) (else 2))) {ARMS})", (SHAPE,), ("n=1",)),
        ("b2-pure-cond-let", f"((n Int)) -> Int (match (let* ((r (cond ((> n 0) 1) (else 2)))) (variant Shape CIRCLE :r r)) {ARMS})", (SHAPE,), ("n=1",)),
        ("b2-effect-cond-in-variant", f"((n Int)) -> Int (match (variant Shape CIRCLE :r (cond ((> n 0) {E('e1')}) (else 2))) {ARMS})", (SHAPE,), ("n=1",)),
    ]

    # ---- M1 neighbours: these build on main and must not be refused
    W = f"(defworkflow w ((n Int)) -> Int {E('w')})"
    WP = "(defworkflow wp ((n Int)) -> Int (+ n 0))"
    WPV = "(defworkflow wpv ((n Int)) -> Int (call wp :n n))"
    PWP = "(defproc pwp ((n Int)) -> Int (call wp :n n))"
    PE = f"(defproc pe ((n Int)) -> Int {E('p')})"
    PPE = "(defproc ppe ((n Int)) -> Int (pe n))"
    LOOP = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) STEP))"
    M1 = {
        "wf-L1": "(continue (if (> n 0) (call w :n n) 0))",
        "wf-top-prefix": "(continue (if (> n 0) (let* ((y (call w :n n))) (if (> n 0) y 0)) 0))",
        "wf-match-top-if-inside": "(continue (match (variant U A :n n) ((A a) (if (> n 0) (call w :n n) 0)) ((B b) 0)))",
        "wf-inner-condition": "(continue (if (> n 0) (if (> (call w :n n) 0) 1 0) 0))",
        "wf-pure-L2": "(continue (if (> n 0) (if (> n 0) (call wp :n n) 0) 0))",
        "wf-pure-via-L2": "(continue (if (> n 0) (if (> n 0) (call wpv :n n) 0) 0))",
        "proc-pure-L2": "(continue (if (> n 0) (if (> n 0) (pp n) 0) 0))",
        "proc-pure-wf-L2": "(continue (if (> n 0) (if (> n 0) (pwp n) 0) 0))",
        "proc-L1": "(continue (if (> n 0) (pe n) 0))",
        "wf-L2-done": "(done (if (> n 0) (if (> n 0) (call w :n n) 0) 0))",
        "wf-L2-bound": "(let* ((next (if (> n 0) (if (> n 0) (call w :n n) 0) 0))) (continue next))",
        "proc-via-proc-L2": "(continue (if (> n 0) (if (> n 0) (ppe n) 0) 0))",
        "letproc-effect-L2": f"(let-proc ((g ((k Int)) -> Int {E('g')})) (continue (if (> n 0) (if (> n 0) (g n) 0) 0)))",
        "cond-else-wf": "(continue (cond ((> n 5) 0) ((> n 9) 1) (else (call w :n n))))",
    }
    for name, step in M1.items():
        CASES.append((f"m1-{name}", LOOP.replace("STEP", step), (U, W, WP, WPV, PWP, PE, PPE, PP), ("n=1",)))

    # ---- M2 shapes beside their bound spelling (n = 1 and n = 0)
    M2 = {
        "if-then": f"(if (> n 0) {E('e1')} 2)",
        "if-both": f"(if (> n 0) {E('e1')} {E('e2', 2)})",
        "cond": f"(cond ((> n 5) {E('e1')}) ((> n 0) {E('e2', 2)}) (else 0))",
        "plus-match": f"(+ {E('e1')} (match (variant U A :n n) ((A a) a.n) ((B b) 0)))",
        "match-arm": f"(match (variant U A :n n) ((A a) {E('e1')}) ((B b) 0))",
        "match-subject": f"(match {EU} ((A a) a.n) ((B b) 0))",
        "loop-continue": f"(loop/recur ((s 0)) :max 3 :on-exhausted s (if (> s 1) (done s) (continue (+ s {E('e1')}))))",
        "let-if": f"(let* ((q (if (> n 0) {E('e1')} 2))) q)",
    }
    SPELL = {
        "call": "(mkshape X)",
        "let": "(let* ((r X)) (variant Shape CIRCLE :r r))",
        "nested-let": "(let* ((r (let* ((q X)) q))) (variant Shape CIRCLE :r r))",
        "cond-subject": "(cond ((> n 5) (variant Shape SQUARE :side 2)) (else (mkshape X)))",
    }
    for xname, x in M2.items():
        for sname, spell in SPELL.items():
            subject = spell.replace("X", x)
            for n in (1, 0):
                CASES.append((f"m2-{sname}-{xname}-n{n}", f"((n Int)) -> Int (match {subject} {ARMS})", (U, SHAPE, MK), (f"n={n}",)))
                CASES.append((f"m2-{sname}-{xname}-n{n}-bound", f"((n Int)) -> Int (let* ((shape {subject})) (match shape {ARMS}))",
                              (U, SHAPE, MK), (f"n={n}",)))

    # ---- m2: pure values holding a `match` as a loop's `:max` or `:state`, or a serial map's `:max`
    MM = "(match u ((A a) a.n) ((B b) 1))"
    VALUES = {
        "plus-match": f"(+ 1 {MM})",
        "pure-call-match": f"(pp {MM})",
        "map-body-match": "(list/length (list/map ((x (list 1 2))) (match (variant U A :n x) ((A a) a.n) ((B b) 0))))",
        "list-length-match": f"(list/length (list {MM} 2))",
        "if-else-plus-match": f"(if (> n 0) 3 (+ 1 {MM}))",
        "let-match": f"(let* ((k 1)) (match u ((A a) (+ k a.n)) ((B b) 1)))",
        "cond-match": f"(cond ((> n 5) 1) ((> n 0) {MM}) (else 4))",
    }
    STATE_VALUES = {
        "loop-state-field": f"(loop-state (i Int {MM}))",
        "record-field": f"(record Rk :n {MM})",
        "variant-field": f"(variant U A :n {MM})",
    }
    for vname, v in VALUES.items():
        CASES.append((f"m2b-max-{vname}", f"((u U) (n Int)) -> Int (loop/recur ((s 0)) :max {v} :on-exhausted s (if (> s 10) (done s) (continue (+ s 1))))", (U, PP), (A3, "n=1")))
        CASES.append((f"m2b-state-{vname}", f"((u U) (n Int)) -> Int (loop/recur ((s {v})) :max 2 :on-exhausted 9 (done s))", (U, PP), (A3, "n=1")))
        CASES.append((f"m2b-mapmax-{vname}", f"((u U) (n Int)) -> Int (list/length (list/map-effect ((x (list 1 2))) :max {v} {E('m')}))", (U, PP), (A3, "n=1")))
    for vname, v in STATE_VALUES.items():
        read = {"loop-state-field": "s.i", "record-field": "s.n", "variant-field": "(match s ((A a) a.n) ((B b) 0))"}[vname]
        CASES.append((f"m2b-state-{vname}", f"((u U) (n Int)) -> Int (loop/recur ((s {v})) :max 2 :on-exhausted 9 (done {read}))", (U, RK), (A3, "n=1")))
    return CASES


def _b3():
    """B3 probes: a pure value with a `match` inside a constructor as a loop's `:state` (fix round 1's m2 route)."""
    U = "(defunion U (A (n Int)) (B (why String)))"
    RK = "(defrecord Rk (n Int))"
    R2 = "(defrecord R2 (n Int) (k Int))"
    A3 = 'u={"variant":"A","n":3}'
    MM = "(match u ((A a) a.n) ((B b) 1))"
    LOOP = "((u U) (n Int)) -> Int (loop/recur ((s STATE)) :max 2 :on-exhausted 9 (done READ))"


    def E(label, result=1, type_="Int"):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


    SHAPES = {
        "record": (f"(record Rk :n {MM})", "s.n", (U, RK)),
        "record-two": (f"(record R2 :n {MM} :k 1)", "(+ s.n s.k)", (U, R2)),
        "variant": (f"(variant U A :n {MM})", "(match s ((A a) a.n) ((B b) 0))", (U,)),
        "list": (f"(list {MM} 2)", "(list/length s)", (U,)),
        "nested-record": (f"(record Rk :n (+ 1 {MM}))", "s.n", (U, RK)),
        "if-of-records": (f"(if (> n 0) (record Rk :n {MM}) (record Rk :n 0))", "s.n", (U, RK)),
        "record-effect-body": (f"(record Rk :n {MM})", f"(+ s.n {E('f')})", (U, RK)),
    }
    CASES = [(f"b3-state-{name}", LOOP.replace("STATE", state).replace("READ", read), defs, (A3, "n=1"))
             for name, (state, read, defs) in SHAPES.items()]
    CASES += [(f"b3-fnstate-{name}", f"((u U) (n Int)) -> Int (loop/recur :max 2 :state {state} :on-exhausted 9 (fn (s) (done {read})))", defs, (A3, "n=1"))
              for name, (state, read, defs) in SHAPES.items()]
    CASES += [
        ("b3-max-record-read", f"((u U) (n Int)) -> Int (loop/recur ((s 0)) :max (let* ((r (record Rk :n {MM}))) r.n) :on-exhausted s (if (> s 10) (done s) (continue (+ s 1))))", (U, RK), (A3, "n=1")),
    ]
    return CASES


def _left():
    """Shapes left crashing on the tip: their neighbours."""
    SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
    MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
    ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"
    LOOP = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) STEP))"


    def E(label, result=1):
        return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns Int)'


    G = f"(let-proc ((g ((k Int)) -> Int {E('g')})) BODY)"
    CASES = [
        ("map-subject-pure-map", f"((n Int)) -> Int (match (mkshape (list/length (list/map ((x (list 1 2))) x))) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("map-subject-pure-serial", f"((n Int)) -> Int (match (mkshape (list/length (list/map-effect ((x (list 1 2))) :max 2 x))) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("map-subject-effect-serial", f"((n Int)) -> Int (match (mkshape (list/length (list/map-effect ((x (list 1 2))) :max 2 {E('m')}))) {ARMS})", (SHAPE, MK), ("n=1",)),
        ("map-subject-effect-serial-variant", f"((n Int)) -> Int (match (variant Shape CIRCLE :r (list/length (list/map-effect ((x (list 1 2))) :max 2 {E('m')}))) {ARMS})", (SHAPE,), ("n=1",)),
        ("letproc-L1", LOOP.replace("STEP", G.replace("BODY", "(continue (if (> n 0) (g n) 0))")), (), ("n=1",)),
        ("letproc-L2", LOOP.replace("STEP", G.replace("BODY", "(continue (if (> n 0) (if (> n 0) (g n) 0) 0))")), (), ("n=1",)),
        ("letproc-L2-cond", LOOP.replace("STEP", G.replace("BODY", "(continue (cond ((> n 5) 0) ((> n 0) (g n)) (else 0)))")), (), ("n=1",)),
        ("letproc-L2-bound", LOOP.replace("STEP", G.replace("BODY", "(let* ((next (if (> n 0) (if (> n 0) (g n) 0) 0))) (continue next))")), (), ("n=1",)),
        ("letproc-pure-L2", LOOP.replace("STEP", "(let-proc ((g ((k Int)) -> Int (+ k 1))) (continue (if (> n 0) (if (> n 0) (g n) 0) 0)))"), (), ("n=1",)),
    ]
    return CASES


def _x_operands():
    """Every loop and map operand position crossed with value shapes, pure and with a simple effect X: a literal,
    a name, a field read, an operator, `if`, `cond`, `match`, and a record, a variant and a list, each holding X,
    an `if`, a `cond` or a `match`, one and two levels down, and an `if` choosing records."""
    defs = (U, RK, "(defrecord Rk2 (k Rk))", "(defunion W (P (u U)) (Q (why String)))")
    params = "((n Int) (u U) (r Rk) (xs List[Int]))"
    holes = {"pure": "1", "effect": E("x")}
    inners = {"leaf": "X", "if": "(if (> n 0) X 2)", "cond": "(cond ((> n 5) X) ((> n 0) 2) (else 3))",
              "match": "(match u ((A a) X) ((B b) 0))"}
    ints = {"literal": "X", "name": "n", "field": "r.n", "operator": "(+ X 1)", **{k: v for k, v in inners.items() if k != "leaf"}}
    typed = {name: ("Int", "0", shape) for name, shape in ints.items()}
    for iname, inner in inners.items():
        typed[f"record-{iname}"] = ("Rk", "(record Rk :n 0)", f"(record Rk :n {inner})")
        typed[f"record2-{iname}"] = ("Rk2", "(record Rk2 :k (record Rk :n 0))", f"(record Rk2 :k (record Rk :n {inner}))")
        typed[f"variant-{iname}"] = ("U", "(variant U A :n 0)", f"(variant U A :n {inner})")
        typed[f"variant2-{iname}"] = ("W", "(variant W P :u (variant U A :n 0))", f"(variant W P :u (variant U A :n {inner}))")
        typed[f"list-{iname}"] = ("List[Int]", "(list 0)", f"(list {inner} 2)")
        typed[f"list2-{iname}"] = ("List[List[Int]]", "(list (list 0))", f"(list (list {inner}))")
        typed[f"if-records-{iname}"] = ("Rk", "(record Rk :n 0)", f"(if (> n 0) (record Rk :n {inner}) (record Rk :n 0))")
    state = {
        "state": "(loop/recur ((s V)) :max 2 :on-exhausted s (done s))",
        "fn-state": "(loop/recur :max 2 :state V :on-exhausted s (fn (s) (done s)))",
        "continue": "(loop/recur ((s V0)) :max 2 :on-exhausted s (if (> n 5) (done s) (continue V)))",
        "fn-continue": "(loop/recur :max 2 :state V0 :on-exhausted s (fn (s) (if (> n 5) (done s) (continue V))))",
        "done": "(loop/recur ((s V0)) :max 2 :on-exhausted s (done V))",
        "on-exhausted": "(loop/recur ((s V0)) :max 2 :on-exhausted V (if (> n 100) (done s) (continue s)))",
    }
    budget = {
        "max": "(loop/recur ((s 0)) :max V :on-exhausted s (if (> s 10) (done s) (continue (+ s 1))))",
        "fn-max": "(loop/recur :max V :state 0 :on-exhausted s (fn (s) (if (> s 10) (done s) (continue (+ s 1)))))",
        "map-max": f"(list/length (list/map-effect ((x (list 1 2))) :max V {E('m')}))",
    }
    source = {
        "map-source": f"(list/length (list/map-effect ((x V)) :max 5 {E('m')}))",
        "pure-map-source": "(list/length (list/map ((x V)) (+ x 1)))",
    }
    cases = []
    for hname, hole in holes.items():
        for vname, (type_, seed, shape) in typed.items():
            value = shape.replace("X", hole)
            if hname == "effect" and value == shape:
                continue
            for pname, position in state.items():
                run = position.replace("V0", seed).replace("V", value)
                cases.append((f"x-op-{pname}-{vname}-{hname}", f"{params} -> {type_} {run}", defs))
            as_int = {"Int": value, "List[Int]": f"(list/length {value})", "Rk": f"(let* ((v {value})) v.n)"}.get(type_)
            for pname, position in budget.items():
                if as_int is not None:
                    cases.append((f"x-op-{pname}-{vname}-{hname}", f"{params} -> Int {position.replace('V', as_int)}", defs))
            if type_ == "List[Int]":
                for pname, position in source.items():
                    cases.append((f"x-op-{pname}-{vname}-{hname}", f"{params} -> Int {position.replace('V', value)}", defs))
    return cases


def _x_cond_subject():
    """A `cond` at each depth and context of a `match` subject, pure and with an effect X in a clause."""
    c_int = "(cond ((> n 5) X) ((> n 0) 2) (else 3))"
    c_bool = "(cond ((> n 5) (> X 0)) (else false))"
    circle, square = "(variant Shape CIRCLE :r Q)", "(variant Shape SQUARE :side 1)"
    subjects = {
        "direct": f"(cond ((> n 5) {circle.replace('Q', 'X')}) (else {square}))",
        "call-argument": f"(mkshape {c_int})",
        "let-binding": f"(let* ((q {c_int})) {circle.replace('Q', 'q')})",
        "variant-field": circle.replace("Q", c_int),
        "if-branch": f"(if (> n 0) {circle.replace('Q', c_int)} {square})",
        "if-condition": f"(if {c_bool} {circle.replace('Q', '1')} {square})",
        "and-operand": f"(if (and (> n 0) {c_bool}) {circle.replace('Q', '1')} {square})",
        "inner-match-arm": f"(match u ((A a) {circle.replace('Q', c_int)}) ((B b) {square}))",
        "loop-done": f"(loop/recur ((s 0)) :max 2 :on-exhausted {square} (done {circle.replace('Q', c_int)}))",
        "loop-state": f"(loop/recur ((s {c_int})) :max 1 :on-exhausted {square} (done {circle.replace('Q', 's')}))",
        "let-proc-body": f"(let-proc ((f ((k Int)) -> Shape {circle.replace('Q', c_int)})) (f n))",
        "map-body": "(mkshape (list/length (list/map ((x xs)) (cond ((> x 0) 1) (else 2)))))",
    }
    defs = (U, SHAPE, MK)
    return [(f"x-cond-subject-{sname}-{hname}",
             f"((n Int) (u U) (xs List[Int])) -> Int (match {subject.replace('X', hole)} ((CIRCLE c) c.r) ((SQUARE q) 0))",
             defs)
            for sname, subject in subjects.items() for hname, hole in (("pure", "1"), ("effect", E("x")))
            if hname == "pure" or "X" in subject]


def _cases():
    cases, seen = {}, set()
    for family in (_td2, _td2b, _td1, _extra, _r1, _b3, _left):
        for case_id, run, definitions, *_inputs in family():
            key = (run, tuple(definitions))
            if key not in seen:
                seen.add(key)
                cases[f"{family.__name__[1:]}-{case_id}"] = key
    for family in (_x_td2, _x_d4, _x_d20, _x_d19, _x_operands, _x_cond_subject):
        for case_id, run, definitions in family():
            key = (run, tuple(definitions))
            if key not in seen:
                seen.add(key)
                cases[case_id] = key
    return cases


CASES: dict[str, tuple[str, tuple[str, ...]]] = _cases()


COMMAND = '''import os, sys
open("log.txt", "a").write(sys.argv[1] + "\\n")
open(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write(sys.argv[2])
'''


def source(case_id: str) -> str:
    run, definitions = CASES[case_id]
    forms = "\n  ".join((*definitions, f"(defworkflow run {run})"))
    return f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule m) (export run)\n  {forms})\n'


def observe(case_id: str, root: Path) -> list:
    """The public build of the case in `root`, which it creates: `["builds", digest]`, `["refused", codes...]`,
    `["crash", class, place]` or `["traceback", class, place]`."""
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    from tests.workflow_lisp_closed_program_helpers import build_outcome

    root.mkdir(parents=True)
    files = {"m.orc": source(case_id), "c.py": COMMAND, "prompt.md": "ASK\n",
             "commands.json": json.dumps({"c": {"stable_command": ["python", "c.py"], "closure": ["c.py"]}}),
             "providers.json": json.dumps({"providers.review": "codex"}),
             "prompts.json": json.dumps({"prompts.base": {"asset_file": "prompt.md"}})}
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    built = []
    outcome = build_outcome(lambda: built.append(build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        command_boundaries_path=root / "commands.json", workspace_root=root,
        provider_externs_path=root / "providers.json", prompt_externs_path=root / "prompts.json"))))
    return ["builds", built[0].program.digest] if built else list(outcome)


if __name__ == "__main__":
    # python tests/workflow_lisp_td21_differential_cases.py OUT.json, with PYTHONPATH the tree to observe
    # (an export of `main` for the recorded expectations).
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        observed = {case_id: observe(case_id, Path(scratch) / str(index)) for index, case_id in enumerate(CASES)}
    Path(sys.argv[1]).write_text(json.dumps(observed, indent=1, sort_keys=True) + "\n", encoding="utf-8")
