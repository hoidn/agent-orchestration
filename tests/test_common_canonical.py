from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

import pytest


class _Opaque:
    def __str__(self) -> str:
        return "opaque:Ω"


def _canonical_api() -> tuple[Any, Any]:
    module = importlib.import_module("orchestrator._common.canonical")
    return module.canonical_json_dumps, module.sha256_json


def _provider_canonical_api() -> tuple[Any, Any]:
    module = importlib.import_module("orchestrator._common.canonical")
    return (
        module.compact_ascii_json_dumps,
        module.sha256_compact_ascii_json,
    )


@pytest.mark.parametrize(
    ("value", "expected_text", "expected_digest"),
    (
        (
            {"z": 1, "a": "ASCII"},
            '{"a":"ASCII","z":1}',
            "sha256:dd4091e2f992bce04533d57e9129470fb30813da6971f46d1bb5e1e64fc460a8",
        ),
        (
            {"é": "café", "emoji": "☃"},
            '{"emoji":"\\u2603","\\u00e9":"caf\\u00e9"}',
            "sha256:e1ea2eef8ef7173d7afafd09d13b544c0fa6db57781d222897886339f421060f",
        ),
        (
            {"outer": [{"z": 2, "a": [True, None, 3.5]}, "tail"]},
            '{"outer":[{"a":[true,null,3.5],"z":2},"tail"]}',
            "sha256:6245bc4bc11adce8219049f7437e757519e753325e055326363329a0afa3ac7f",
        ),
        (
            {"path": Path("α/β"), "opaque": _Opaque()},
            '{"opaque":"opaque:\\u03a9","path":"\\u03b1/\\u03b2"}',
            "sha256:92a7fc87ba2d7d01c4f8b8a0e8384454a383c99ab2bbe83fc6af97941c525d2e",
        ),
        (
            {
                "nan": float("nan"),
                "neg": float("-inf"),
                "pos": float("inf"),
            },
            '{"nan":NaN,"neg":-Infinity,"pos":Infinity}',
            "sha256:89cad63411cd4f9afd2ebd1172c9f21ac383dae702c464260b38b6075921cf3b",
        ),
    ),
)
def test_canonical_json_and_digest_golden_vectors(
    value: object,
    expected_text: str,
    expected_digest: str,
) -> None:
    canonical_json_dumps, sha256_json = _canonical_api()

    rendered = canonical_json_dumps(value)

    assert rendered == expected_text
    assert isinstance(rendered, str)
    assert rendered.encode("utf-8") == expected_text.encode("utf-8")
    assert sha256_json(value) == expected_digest
    assert expected_digest.startswith("sha256:")
    assert len(expected_digest) == 71


def test_canonical_json_keeps_text_bytes_and_newline_ownership_distinct() -> None:
    canonical_json_dumps, sha256_json = _canonical_api()
    value = {"binary": b"x\n", "text": "x\n"}
    expected_text = r"""{"binary":"b'x\\n'","text":"x\n"}"""

    rendered = canonical_json_dumps(value)

    assert rendered == expected_text
    assert not rendered.endswith("\n")
    assert not rendered.encode("utf-8").endswith(b"\n")
    assert (
        sha256_json(value)
        == "sha256:32e6389200abf98508dc261f8715f18f1772b103443f764df1a2b00c12653944"
    )
    newline_owned_digest = (
        "sha256:" + hashlib.sha256(f"{rendered}\n".encode("utf-8")).hexdigest()
    )
    assert (
        newline_owned_digest
        == "sha256:8a1936507598abf7457bb37ffdea6ce20b2220c2df01846c8761ad38cc2e89fb"
    )
    assert newline_owned_digest != sha256_json(value)


def test_compact_ascii_json_golden_vector_and_prefixed_digest() -> None:
    compact_ascii_json_dumps, sha256_compact_ascii_json = (
        _provider_canonical_api()
    )
    value = {"z": "café", "a": [1, True, None]}

    rendered = compact_ascii_json_dumps(value)

    assert rendered == '{"a":[1,true,null],"z":"caf\\u00e9"}'
    assert rendered.isascii()
    assert (
        sha256_compact_ascii_json(value)
        == "sha256:9c9604bc6439a99e638dd772ab98c11032c6612f11392d2e6398edc989ea8d1b"
    )


def test_compact_ascii_json_leaves_zero_one_and_two_newline_framing_local() -> None:
    compact_ascii_json_dumps, _ = _provider_canonical_api()
    rendered = compact_ascii_json_dumps({"frame": "value"})

    assert rendered.encode("ascii") == b'{"frame":"value"}'
    assert (rendered + "\n").encode("ascii") == b'{"frame":"value"}\n'
    assert (rendered + "\n\n").encode("ascii") == b'{"frame":"value"}\n\n'


@pytest.mark.parametrize(
    ("value", "token"),
    (
        (float("nan"), "NaN"),
        (float("inf"), "Infinity"),
        (float("-inf"), "-Infinity"),
    ),
)
def test_compact_ascii_json_preserves_permissive_nonfinite_profile(
    value: float,
    token: str,
) -> None:
    compact_ascii_json_dumps, _ = _provider_canonical_api()

    assert compact_ascii_json_dumps({"value": value}) == f'{{"value":{token}}}'


@pytest.mark.parametrize(
    ("value", "rendered"),
    (
        (float("nan"), "nan"),
        (float("inf"), "inf"),
        (float("-inf"), "-inf"),
    ),
)
def test_compact_ascii_json_preserves_rejecting_nonfinite_profile(
    value: float,
    rendered: str,
) -> None:
    compact_ascii_json_dumps, sha256_compact_ascii_json = (
        _provider_canonical_api()
    )
    expected = f"Out of range float values are not JSON compliant: {rendered}"

    with pytest.raises(ValueError) as dump_exc:
        compact_ascii_json_dumps({"value": value}, allow_nan=False)
    with pytest.raises(ValueError) as digest_exc:
        sha256_compact_ascii_json({"value": value}, allow_nan=False)

    assert str(dump_exc.value) == expected
    assert str(digest_exc.value) == expected


@pytest.mark.parametrize("value", (Path("opaque"), _Opaque()))
def test_compact_ascii_json_has_no_lexical_string_fallback(value: object) -> None:
    compact_ascii_json_dumps, sha256_compact_ascii_json = (
        _provider_canonical_api()
    )

    with pytest.raises(TypeError):
        compact_ascii_json_dumps({"value": value})
    with pytest.raises(TypeError):
        sha256_compact_ascii_json({"value": value})
