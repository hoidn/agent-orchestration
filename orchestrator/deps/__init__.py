"""Dependency resolution and injection module."""

from .resolver import DependencyResolver
from .injector import DependencyInjector

__all__ = [
    "DependencyResolver",
    "DependencyInjector",
]
