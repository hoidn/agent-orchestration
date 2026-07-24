"""Parse the narrow Markdown-frontmatter subset used by NeurIPS backlog tools."""

from __future__ import annotations

from pathlib import Path


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_scalar_list_frontmatter(payload: str, source_path: Path) -> dict[str, object]:
    """Parse a top-level mapping whose values are strings or string lists."""

    parsed: dict[str, object] = {}
    current_list_key: str | None = None
    lines = payload.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if not raw_line.strip():
            index += 1
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0:
            if ":" not in line:
                raise SystemExit(f"Unsupported frontmatter syntax in {source_path}: {line}")
            key, raw_value = line.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            if not key:
                raise SystemExit(f"Frontmatter key must not be empty: {source_path}")
            if value == "":
                parsed[key] = []
                current_list_key = key
            elif value == "[]":
                parsed[key] = []
                current_list_key = None
            elif value.startswith("[") and value.endswith("]"):
                parsed[key] = [
                    _strip_wrapping_quotes(item.strip())
                    for item in value[1:-1].split(",")
                    if item.strip()
                ]
                current_list_key = None
            else:
                parsed[key] = _strip_wrapping_quotes(value)
                current_list_key = None
            index += 1
            continue

        if current_list_key is None or not line.startswith("- "):
            raise SystemExit(f"Unsupported nested frontmatter syntax in {source_path}: {line}")

        item = line[2:].strip()
        values = parsed[current_list_key]
        assert isinstance(values, list)
        if item not in {"|", "|-", "|+"}:
            values.append(_strip_wrapping_quotes(item))
            index += 1
            continue

        list_indent = indent
        index += 1
        block_lines: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_indent = len(candidate) - len(candidate.lstrip(" "))
            if candidate.strip() and candidate_indent <= list_indent:
                break
            block_lines.append(candidate)
            index += 1
        content_indents = [
            len(candidate) - len(candidate.lstrip(" "))
            for candidate in block_lines
            if candidate.strip()
        ]
        if not content_indents:
            values.append("")
            continue
        content_indent = min(content_indents)
        block = "\n".join(
            candidate[content_indent:] if candidate.strip() else ""
            for candidate in block_lines
        )
        values.append(block if item == "|-" else block.rstrip("\n") + "\n")

    return parsed
