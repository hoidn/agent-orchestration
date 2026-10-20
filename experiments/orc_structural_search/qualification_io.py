"""Byte identities and strict JSON inputs for external qualification evidence."""

import hashlib
import json
import math
import os
import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(f"qualification: {message}")


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON identity {key!r}")
        value[key] = item
    return value


def read(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_value(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "expected bare SHA-256")
    return value


def reference(value, containing):
    require(isinstance(value, dict) and set(value) == {"file", "sha256"}, "expected {file, sha256} reference")
    require(isinstance(value['file'], str) and bool(value['file']), "empty reference path")
    path = Path(value['file'])
    path = (Path(containing).parent / path).resolve()
    require(path.is_file(), f"missing evidence {path}")
    require(digest(path) == hash_value(value['sha256']), f"hash mismatch for {path}")
    return path


def same_reference(left, left_document, right, right_document):
    """Resolve each scope and verify bytes before comparing frozen evidence identities."""
    path = reference(left, left_document)
    reference(right, right_document)
    require(left['sha256'] == right['sha256'], 'evidence references differ')
    return path


def normalized(value, containing):
    if isinstance(value, dict):
        if 'file' in value or 'sha256' in value:
            reference(value, containing)
            return {'sha256': value['sha256']}
        return {key: normalized(item, containing) for key, item in value.items()}
    if isinstance(value, list):
        return [normalized(item, containing) for item in value]
    return value


def names(value, label):
    require(isinstance(value, list) and value and all(isinstance(n, str) and n for n in value),
            f"{label} must be nonempty names")
    require(len(set(value)) == len(value), f"duplicate {label}")
    return set(value)


def calibration(value):
    require(isinstance(value, dict) and 'margin' in value, 'missing calibration margin')
    margin, error = value['margin'], value.get('error_rate', 0)
    for number in (margin, error):
        require(type(number) in (int, float) and math.isfinite(number), 'calibration must be finite numbers')
    require(margin >= 0 and 0 <= error <= 1, 'invalid calibration margin or error_rate')
    return margin, error


def package_digest(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), f"invalid task package {root}")
    lines = []
    for path in sorted(root.rglob('*'), key=lambda p: os.fsencode(p.relative_to(root).as_posix())):
        require(not path.is_symlink(), f"symlink in task package {path}")
        if not path.is_file():
            continue
        name = './' + path.relative_to(root).as_posix()
        require(not any(c in name for c in ('\\', '\n', '\r')), 'escaped sha256sum filename unsupported')
        lines.append(f"{digest(path)}  {name}\n")
    return hashlib.sha256(''.join(lines).encode()).hexdigest()
