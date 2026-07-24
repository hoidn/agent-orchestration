"""Test-only parsing for prompt contract documents emitted by the renderer.

This intentionally supports only the renderer's indented mapping/list shape and
JSON-encoded scalar values. It is not a YAML compatibility surface.
"""

from __future__ import annotations

import json
from typing import TypeAlias


ContractValue: TypeAlias = (
    dict[str, "ContractValue"] | list["ContractValue"] | str | int | float | bool | None
)


def _scalar(value: str) -> ContractValue:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _key_value(content: str) -> tuple[str, str]:
    key, separator, value = content.partition(":")
    if not separator or not key:
        raise ValueError(f"invalid prompt contract entry: {content!r}")
    return key, value.lstrip()


def _parse_block(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[ContractValue, int]:
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, ContractValue], int]:
    result: dict[str, ContractValue] = {}
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or content.startswith("- "):
            raise ValueError(f"invalid prompt contract indentation at {content!r}")

        key, scalar = _key_value(content)
        index += 1
        if scalar:
            result[key] = _scalar(scalar)
        elif index < len(lines) and lines[index][0] > indent:
            child_indent = lines[index][0]
            result[key], index = _parse_block(lines, index, child_indent)
        else:
            result[key] = None
    return result, index


def _parse_list(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[list[ContractValue], int]:
    result: list[ContractValue] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or not content.startswith("- "):
            raise ValueError(f"invalid prompt contract list entry at {content!r}")

        item = content[2:]
        index += 1
        if ":" not in item:
            result.append(_scalar(item))
            continue

        key, scalar = _key_value(item)
        mapping: dict[str, ContractValue] = {
            key: _scalar(scalar) if scalar else None
        }
        if index < len(lines) and lines[index][0] > indent:
            continuation_indent = lines[index][0]
            continuation, index = _parse_mapping(
                lines,
                index,
                continuation_indent,
            )
            mapping.update(continuation)
        result.append(mapping)
    return result, index


def parse_prompt_contract_document(prompt: str) -> dict[str, ContractValue]:
    """Return the single structured contract appended to a rendered prompt."""
    source_lines = prompt.splitlines()
    start = next(
        index for index, line in enumerate(source_lines) if line.startswith("- path:")
    )
    lines = [
        (len(line) - len(line.lstrip(" ")), line.lstrip(" "))
        for line in source_lines[start:]
        if line.strip()
    ]
    parsed, end = _parse_block(lines, 0, 0)
    if end != len(lines):
        raise ValueError("prompt contract parser did not consume the document")
    if (
        not isinstance(parsed, list)
        or len(parsed) != 1
        or not isinstance(parsed[0], dict)
    ):
        raise ValueError("prompt contract must contain exactly one document")
    return parsed[0]
