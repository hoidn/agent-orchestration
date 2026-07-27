"""Private exact-schema guard for calibrated live review."""

from __future__ import annotations

from collections.abc import Mapping

from jsonschema import Draft202012Validator

from ._evaluation_support import EvaluationError, _fail


_DIMENSIONS = (
    "TASK_COMPLETENESS",
    "BEHAVIORAL_CORRECTNESS",
    "MAINTAINABILITY",
    "SCOPE_CONTROL",
    "EVIDENCE_QUALITY",
)
_ASSESSMENTS = ("PASS", "CONCERN", "FAIL", "INDETERMINATE")
_TREATMENT_GUESSES = ("DIRECT", "COORDINATOR", "ORC", "UNKNOWN")
_PAIRWISE_OUTCOMES = ("A", "B", "TIE", "INDETERMINATE")
_UNPROVEN_KEYWORDS = {
    "contains",
    "minContains",
    "maxContains",
    "uniqueItems",
}


def _citation_schema() -> dict[str, object]:
    return {
        "type": "array",
        "minItems": 1,
        "items": {"type": "string", "minLength": 1},
    }


def _dimension_assessment_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dimension": {"type": "string", "enum": list(_DIMENSIONS)},
            "assessment": {"type": "string", "enum": list(_ASSESSMENTS)},
            "rationale": {"type": "string", "minLength": 1},
            "evidence_citations": _citation_schema(),
        },
        "required": [
            "dimension",
            "assessment",
            "rationale",
            "evidence_citations",
        ],
    }


def _expected_live_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "opaque_label": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "evidence_citations": _citation_schema(),
                        "dimension_assessments": {
                            "type": "array",
                            "minItems": 5,
                            "maxItems": 5,
                            "items": _dimension_assessment_schema(),
                        },
                        "sealed_treatment_guess": {
                            "type": "string",
                            "enum": list(_TREATMENT_GUESSES),
                        },
                    },
                    "required": [
                        "opaque_label",
                        "evidence_citations",
                        "dimension_assessments",
                        "sealed_treatment_guess",
                    ],
                },
            },
            "pairwise_results": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_a_label": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "candidate_b_label": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "outcome": {
                            "type": "string",
                            "enum": list(_PAIRWISE_OUTCOMES),
                        },
                        "rationale": {"type": "string", "minLength": 1},
                        "evidence_citations": _citation_schema(),
                    },
                    "required": [
                        "candidate_a_label",
                        "candidate_b_label",
                        "outcome",
                        "rationale",
                        "evidence_citations",
                    ],
                },
            },
        },
        "required": ["candidates", "pairwise_results"],
    }


def _schema_keywords(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return set(value).union(
            *(_schema_keywords(nested) for nested in value.values()),
        )
    if isinstance(value, list):
        return set().union(*(_schema_keywords(nested) for nested in value))
    return set()


def _validate_live_schema(value: object) -> None:
    """Require the exact calibration-supported live provider schema."""

    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:
        raise EvaluationError("live_reviewer_schema_invalid", str(exc)) from exc
    if _UNPROVEN_KEYWORDS.intersection(_schema_keywords(value)):
        _fail("live_reviewer_schema_invalid", "unproven schema keyword")
    if value != _expected_live_schema():
        _fail("live_reviewer_schema_invalid", "exact live output contract")
