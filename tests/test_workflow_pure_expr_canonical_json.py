"""The direct canonical JSON encoding agrees with the reference encoding on generated values."""

from __future__ import annotations

from decimal import Decimal
import json
import random
from types import MappingProxyType

from orchestrator.workflow import pure_expr

_TEXT = "aZ09 _-./\\\"'\n\téß中☃\U0001f600\ud800\x00\x7f"


def _reference(value):
    return json.dumps(pure_expr._jsonable(value), **pure_expr._CANONICAL_JSON)


def _outcome(encode, value):
    try:
        return encode(value)
    except Exception as exc:  # the refusal itself must agree
        return type(exc), str(exc)


def _scalar(rng):
    return rng.choice([
        lambda: "".join(rng.choice(_TEXT) for _ in range(rng.randrange(6))),
        lambda: rng.randrange(-10**20, 10**20), lambda: rng.choice([0, 1, -1, True, False, None]),
        lambda: rng.uniform(-1e6, 1e6), lambda: rng.choice([0.0, -0.0, 1e308, 5e-324, 0.1, 1e16]),
        lambda: rng.choice([float("nan"), float("inf"), Decimal("1.5")]) if rng.random() < 0.05 else 2.5,
    ])()


def _key(rng, plain):
    if plain or rng.random() < 0.8:
        return "".join(rng.choice(_TEXT) for _ in range(rng.randrange(1, 4)))
    return rng.choice([1, 0, True, False, None, 2.5, ("t",), -3])


def _value(rng, depth, plain):
    if depth == 0 or rng.random() < 0.3:
        return _scalar(rng)
    items = [_value(rng, depth - 1, plain) for _ in range(rng.randrange(4))]
    kind = rng.choice(["dict", "dict", "list", "tuple"] + ([] if plain else ["proxy"]))
    if kind in {"dict", "proxy"}:
        mapping = {_key(rng, plain): item for item in items}
        return MappingProxyType(mapping) if kind == "proxy" else mapping
    return items if kind == "list" else tuple(items)


def _has_non_plain_mapping(value):
    if isinstance(value, dict) and type(value) is dict:
        return any(type(key) is not str or _has_non_plain_mapping(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(map(_has_non_plain_mapping, value))
    return isinstance(value, MappingProxyType)


def test_direct_encoding_agrees_with_reference_on_generated_values():
    rng = random.Random(20261111)
    fallbacks = 0
    for index in range(4000):
        value = _value(rng, 4, plain=index % 2 == 0)
        assert _outcome(pure_expr.canonical_json_for_pure_value, value) == _outcome(_reference, value), value
        if _has_non_plain_mapping(value):
            fallbacks += 1
            assert not pure_expr._encodes_unchanged(value), value
    assert fallbacks > 300


def test_non_string_keys_take_the_reference_encoding():
    for value in ({1: "a", "1": "b"}, {True: 1}, {None: 1}, {2.5: 1}, [{"a": {3: 4}}], MappingProxyType({"a": 1})):
        assert not pure_expr._encodes_unchanged(value)
        assert _outcome(pure_expr.canonical_json_for_pure_value, value) == _outcome(_reference, value)
