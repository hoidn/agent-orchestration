"""File system queue (FSQ) module for queue management and wait-for functionality."""

from .wait import WaitFor, WaitForResult
from .queue import (
    QueueManager,
    write_task,
    move_to_processed,
    move_to_failed
)

__all__ = [
    'WaitFor',
    'WaitForResult',
    'QueueManager',
    'write_task',
    'move_to_processed',
    'move_to_failed'
]