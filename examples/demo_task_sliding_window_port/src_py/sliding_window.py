"""Reference sliding-window helpers for the workflow demo task.

The implementation intentionally stays small and dependency-free so the task's
complexity comes from boundary semantics, validation, and verification rather
than setup.
"""

from __future__ import annotations

from typing import Sequence


class SlidingWindowError(ValueError):
    """Raised when sliding-window inputs are malformed."""


def _validate(values: Sequence[float], window_size: int, stride: int, drop_last: bool, pad_value: float | None) -> None:
    if not values:
        raise SlidingWindowError("values must not be empty")
    if window_size <= 0:
        raise SlidingWindowError("window_size must be positive")
    if stride <= 0:
        raise SlidingWindowError("stride must be positive")
    if drop_last and pad_value is not None:
        raise SlidingWindowError("pad_value must be None when drop_last is true")


def window_start_indices(
    values: Sequence[float],
    window_size: int,
    stride: int = 1,
    *,
    drop_last: bool = False,
    pad_value: float | None = None,
) -> list[int]:
    _validate(values, window_size, stride, drop_last, pad_value)

    starts: list[int] = []
    index = 0
    length = len(values)
    while index < length:
        end = index + window_size
        if end <= length:
            starts.append(index)
        else:
            if drop_last:
                break
            starts.append(index)
            break
        index += stride
    return starts


def sliding_windows(
    values: Sequence[float],
    window_size: int,
    stride: int = 1,
    *,
    drop_last: bool = False,
    pad_value: float | None = None,
) -> list[list[float]]:
    _validate(values, window_size, stride, drop_last, pad_value)

    windows: list[list[float]] = []
    for start in window_start_indices(
        values,
        window_size,
        stride,
        drop_last=drop_last,
        pad_value=pad_value,
    ):
        window = list(values[start : start + window_size])
        if len(window) < window_size and pad_value is not None:
            window.extend([pad_value] * (window_size - len(window)))
        windows.append(window)
    return windows
