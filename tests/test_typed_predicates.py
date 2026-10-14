"""Tests for v1.6 typed predicates, structured refs, and assert routing."""


import pytest

from orchestrator.workflow.predicates import PredicateEvaluationError, TypedPredicateEvaluator


def test_typed_predicate_evaluator_rejects_multi_operator_nodes():
    evaluator = TypedPredicateEvaluator()
    state = {
        "steps": {
            "WriteReady": {
                "artifacts": {"ready": True},
            }
        }
    }

    predicates = [
        {
            "artifact_bool": {"ref": "root.steps.WriteReady.artifacts.ready"},
            "compare": {"left": 1, "op": "eq", "right": 1},
        },
        {
            "all_of": [
                {
                    "artifact_bool": {"ref": "root.steps.WriteReady.artifacts.ready"},
                    "compare": {"left": 1, "op": "eq", "right": 2},
                }
            ]
        },
    ]

    for predicate in predicates:
        with pytest.raises(PredicateEvaluationError):
            evaluator.evaluate(predicate, state)


def test_typed_predicate_compare_supports_string_eq_and_ne():
    evaluator = TypedPredicateEvaluator()
    state = {
        "steps": {
            "WriteSession": {
                "artifacts": {"session_id": "sess-123"},
            }
        }
    }

    assert evaluator.evaluate(
        {
            "compare": {
                "left": {"ref": "root.steps.WriteSession.artifacts.session_id"},
                "op": "eq",
                "right": "sess-123",
            }
        },
        state,
    ) is True
    assert evaluator.evaluate(
        {
            "compare": {
                "left": {"ref": "root.steps.WriteSession.artifacts.session_id"},
                "op": "ne",
                "right": "sess-999",
            }
        },
        state,
    ) is True
