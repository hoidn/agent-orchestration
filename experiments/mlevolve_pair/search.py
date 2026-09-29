"""Python-owned controller for the bounded two-branch comparison."""

from __future__ import annotations

from collections.abc import Callable

from .leaves import evaluate, propose, validate_candidate, validate_evaluation

Candidate = dict[str, int]
Evaluation = dict[str, object]
Trial = dict[str, object]
Proposal = Callable[[str, str, int, int, int, int, int], Candidate]
Evaluator = Callable[[int, int], Evaluation]


def run_search(
    max_evaluations: int = 12,
    target_score: float = 0.0,
    *,
    proposal: Proposal = propose,
    evaluator: Evaluator = evaluate,
) -> dict[str, object]:
    if type(max_evaluations) is not int or not 2 <= max_evaluations <= 16:
        return {
            "candidate": {"a": 1, "b": 0},
            "evaluation": {"valid": False, "score": target_score, "error": "invalid_budget"},
            "evaluations": 0,
            "status": "invalid_budget",
            "trace": [],
        }

    a, b = {"a": 1, "b": 0}, {"a": 0, "b": 1}
    ae, be = validate_evaluation(evaluator(a["a"], a["b"])), validate_evaluation(
        evaluator(b["a"], b["b"])
    )
    trace: list[Trial] = []
    best, best_eval = a, ae
    if be["valid"] and (not ae["valid"] or be["score"] < ae["score"]):
        best, best_eval = b, be

    def record(action: str, branch: str, candidate: Candidate, evaluation: Evaluation,
               parents: list[Candidate], accepted: bool) -> None:
        trace.append({
            "action": action, "branch": branch, "parents": parents,
            "candidate": candidate, "evaluation": evaluation, "accepted": accepted,
        })

    def request(operation: str, branch: str, current: Candidate,
                other: Candidate) -> Candidate:
        return validate_candidate(proposal(
            operation, branch, current["a"], current["b"],
            other["a"], other["b"], len(trace),
        ))

    record("seed", "A", a, ae, [], True)
    record("seed", "B", b, be, [], True)
    evaluations, next_branch = 2, "A"
    stalls = {"A": 0, "B": 0}
    pending: tuple[str, Candidate] | None = None
    fused = False

    while evaluations < max_evaluations and (
        not best_eval["valid"] or best_eval["score"] > target_score
    ):
        if pending is not None:
            branch, failed = pending
            current, other = (a, b) if branch == "A" else (b, a)
            candidate = request("repair", branch, failed, other)
            evaluation = validate_evaluation(evaluator(candidate["a"], candidate["b"]))
            accepted = bool(evaluation["valid"] and evaluation["score"] < (
                ae if branch == "A" else be
            )["score"])
            record("repair", branch, candidate, evaluation, [failed], accepted)
            evaluations += 1
            if accepted:
                if branch == "A":
                    a, ae = candidate, evaluation
                else:
                    b, be = candidate, evaluation
                stalls[branch] = 0
                if evaluation["score"] < best_eval["score"]:
                    best, best_eval = candidate, evaluation
            else:
                stalls[branch] += 1
            pending = None
            next_branch = "B" if branch == "A" else "A"
            continue

        if not fused and stalls["A"] >= 2 and stalls["B"] >= 2:
            candidate = request("fuse", "both", a, b)
            evaluation = validate_evaluation(evaluator(candidate["a"], candidate["b"]))
            accepted = bool(evaluation["valid"] and evaluation["score"] < best_eval["score"])
            record("fuse", "both", candidate, evaluation, [a, b], accepted)
            evaluations += 1
            if accepted:
                best, best_eval = candidate, evaluation
            stalls = {"A": 0, "B": 0}
            fused = True
            continue

        branch = next_branch
        current, other = (a, b) if branch == "A" else (b, a)
        candidate = request("improve", branch, current, other)
        evaluation = validate_evaluation(evaluator(candidate["a"], candidate["b"]))
        current_eval = ae if branch == "A" else be
        accepted = bool(evaluation["valid"] and evaluation["score"] < current_eval["score"])
        record("improve", branch, candidate, evaluation, [current], accepted)
        evaluations += 1
        if accepted:
            if branch == "A":
                a, ae = candidate, evaluation
            else:
                b, be = candidate, evaluation
            stalls[branch] = 0
            if evaluation["score"] < best_eval["score"]:
                best, best_eval = candidate, evaluation
        else:
            stalls[branch] += 1
            if not evaluation["valid"]:
                pending = branch, candidate
        next_branch = "B" if branch == "A" else "A"

    return {
        "candidate": best, "evaluation": best_eval, "evaluations": evaluations,
        "status": "solved" if best_eval["valid"] and best_eval["score"] <= target_score
        else "budget_exhausted",
        "trace": trace,
    }
