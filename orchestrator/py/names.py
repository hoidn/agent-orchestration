"""Generated `let*` binder names for one traced definition.

Effect binders follow their callee: the first use of callee `c` binds `_c`,
later uses `_c_2`, `_c_3`, ... (characters outside `[A-Za-z0-9_]` become `_`),
so inserting a step renames only later uses of the same callee. An explicit
`name=` is the binder verbatim. Region binders (match payloads, loop state)
keep per-kind counters `_<prefix><n>`. Every name is unique per definition and
never shadows a Python parameter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .diagnostics import PythonFrontendError


@dataclass
class NameAllocator:
    reserved: set[str] = field(default_factory=set)
    counters: dict[str, int] = field(default_factory=dict)

    def next(self, prefix):
        index = self.counters.get(prefix, 0)
        while f"_{prefix}{index}" in self.reserved:
            index += 1
        name = f"_{prefix}{index}"
        self.counters[prefix] = index + 1
        self.reserved.add(name)
        return name

    def callee(self, callee):
        base = "_" + re.sub(r"[^A-Za-z0-9_]", "_", callee)
        use = self.counters.get(base, 0) + 1
        while (base if use == 1 else f"{base}_{use}") in self.reserved:
            use += 1
        self.counters[base] = use
        name = base if use == 1 else f"{base}_{use}"
        self.reserved.add(name)
        return name

    def explicit(self, name, site):
        if not isinstance(name, str) or not name.isidentifier():
            raise PythonFrontendError("python_binder_name_invalid", "name= requires a Python identifier string", site=site)
        if name in self.reserved:
            raise PythonFrontendError("python_binder_name_taken", f"Binder `{name}` is already used in this definition", site=site)
        self.reserved.add(name)
        return name
