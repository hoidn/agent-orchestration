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
