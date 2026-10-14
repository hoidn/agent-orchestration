"""Tests for v2.8 score-aware predicate helpers."""


from orchestrator.workflow.predicates import TypedPredicateEvaluator


def test_score_predicate_evaluator_supports_thresholds_and_bands():
    evaluator = TypedPredicateEvaluator()
    state = {
        "steps": {
            "ScoreCandidate": {
                "artifacts": {
                    "quality_score": 0.91,
                }
            }
        }
    }

    assert evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gte": 0.9,
            }
        },
        state,
    )
    assert evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gt": 0.9,
                "lt": 0.95,
            }
        },
        state,
    )
    assert not evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gte": 0.95,
            }
        },
        state,
    )
