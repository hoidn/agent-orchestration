"""Checked text edits for test sources derived from other test sources."""


def replace_exact(text: str, old: str, new: str, count: int = 1) -> str:
    """Return `text` with each `old` replaced by `new`; fail unless `old` occurs exactly `count` times.

    A derived source whose pattern stopped matching would otherwise compile its base text unchanged.
    """
    found = text.count(old)
    assert found == count, f"expected {count} occurrence(s) of {old!r}, found {found}"
    return text.replace(old, new)
