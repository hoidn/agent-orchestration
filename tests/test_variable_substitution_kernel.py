import json

import pytest

from orchestrator.variables import substitution


def test_template_kernel_preserves_escapes_and_inserts_once():
    template = r"$${x}|$$${x}|${x}|${x}"
    tokens = substitution.tokenize_template(template)

    assert tokens == (
        (False, "\x00{x}|\x00"),
        (True, "x"),
        (False, "|"),
        (True, "x"),
        (False, "|"),
        (True, "x"),
    )
    assert substitution.render_template(tokens, lambda _: "${nested}\x00") == (
        "${x}|$${nested}$|${nested}$|${nested}$"
    )
    assert substitution.render_template(
        substitution.tokenize_template("$${|$$${"), lambda _: "unused"
    ) == "${|$${"


def test_expression_filters_and_value_rendering_keep_legacy_bytes():
    assert substitution.parse_variable_expression("inputs.value|||json||") == (
        "inputs.value",
        ("json",),
    )
    value = {"é": [True, 2]}
    assert substitution.apply_variable_filters(value, ()) is value
    assert substitution.render_variable_value(value) == json.dumps(value)
    assert substitution.render_variable_value(
        substitution.apply_variable_filters(value, ("json",))
    ) == '{"é":[true,2]}'
    assert substitution.render_variable_value(True) == "true"
    assert substitution.render_variable_value(False) == "false"


def test_dictionary_suffix_lookup_and_filter_failures():
    root = {"payload": {"n": 7}, "none": None}
    assert substitution.resolve_dictionary_suffix(root, ("payload", "n")) == 7
    assert substitution.resolve_dictionary_suffix(root, ("payload", "missing")) is None
    assert substitution.resolve_dictionary_suffix(root, ("none",)) is None
    assert substitution.resolve_dictionary_suffix({"payload": [7]}, ("payload", "0")) is None
    with pytest.raises(ValueError, match="Unsupported variable filter: nope"):
        substitution.apply_variable_filters(1, ("nope",))
    with pytest.raises(ValueError, match="Unsupported variable filter: nope"):
        substitution.apply_variable_filters(1, ("json", "nope"))


def test_legacy_substitution_uses_shared_kernel_without_changing_failure_text():
    substitutor = substitution.VariableSubstitutor()
    assert substitutor.substitute(
        "${inputs.flag}|${inputs.value|json}",
        {"inputs": {"flag": True, "value": {"x": "é"}}},
    ) == 'true|{"x":"é"}'

    with pytest.raises(ValueError, match=r"Undefined variables: \['inputs.missing'\]"):
        substitutor.substitute("${inputs.missing}", {"inputs": {}})
    assert substitutor.substitute(
        "${inputs.missing|nope}", {"inputs": {}}, track_undefined=False
    ) == "${inputs.missing|nope}"
    with pytest.raises(ValueError, match="Unsupported variable filter: nope"):
        substitutor.substitute("${inputs.present|nope}", {"inputs": {"present": 1}})
