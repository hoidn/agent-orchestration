"""Pure diagnostic translation and contribution aggregation for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote_to_bytes, urlsplit

from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendDiagnostic,
    capture_frontend_diagnostic_identities,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan

from .coordinates import source_span_to_lsp_range


@dataclass(frozen=True, slots=True)
class DiagnosticContribution:
    """One immutable, generation-stamped diagnostic publication contribution."""

    target_uri: str
    compile_entry_uri: str
    accepted_generation: int
    parity_identity: tuple[object, ...]
    range: Mapping[str, Mapping[str, int]]
    code: str
    severity: int
    source: str
    message: str
    data: Mapping[str, object]
    related_information: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.parity_identity, tuple):
            raise TypeError("diagnostic parity identity must be a tuple")
        if not isinstance(self.range, Mapping):
            raise TypeError("diagnostic range must be a mapping")
        if not isinstance(self.data, Mapping):
            raise TypeError("diagnostic data must be a mapping")
        if not isinstance(self.related_information, tuple) or not all(
            isinstance(item, Mapping) for item in self.related_information
        ):
            raise TypeError(
                "diagnostic related information must be a tuple of mappings"
            )
        object.__setattr__(
            self,
            "target_uri",
            _canonical_file_uri(self.target_uri),
        )
        object.__setattr__(
            self,
            "compile_entry_uri",
            _canonical_file_uri(self.compile_entry_uri),
        )
        object.__setattr__(
            self,
            "parity_identity",
            tuple(_freeze_value(item) for item in self.parity_identity),
        )
        object.__setattr__(self, "range", _freeze_mapping(self.range))
        object.__setattr__(self, "data", _freeze_mapping(self.data))
        object.__setattr__(
            self,
            "related_information",
            tuple(
                _freeze_mapping(item)
                for item in self.related_information
            ),
        )


def translate_frontend_diagnostics(
    diagnostics: Iterable[LispFrontendDiagnostic],
    *,
    compile_entry_uri: str,
    accepted_generation: int,
    accepted_text_by_path: Mapping[Path | str, str],
) -> tuple[DiagnosticContribution, ...]:
    """Translate raw compiler diagnostics against one accepted source snapshot."""

    canonical_entry_uri = _canonical_file_uri(compile_entry_uri)
    if type(accepted_generation) is not int or accepted_generation < 0:
        raise ValueError("accepted_generation must be a non-negative integer")
    accepted_text = _normalize_accepted_text(accepted_text_by_path)
    translated: list[DiagnosticContribution] = []
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, LispFrontendDiagnostic):
            raise TypeError(
                "diagnostic contributions require LispFrontendDiagnostic values"
            )
        parity_identity = capture_frontend_diagnostic_identities(
            (diagnostic,)
        )[0]
        severity_name = parity_identity[2]
        if not isinstance(severity_name, str):
            raise ValueError("diagnostic identity has no effective severity")
        severity = _severity_value(severity_name)
        source_path, retained_path = _canonical_diagnostic_path(
            diagnostic.span.start.path
        )
        source_text = (
            accepted_text.get(source_path)
            if source_path is not None
            else None
        )
        if source_path is not None and source_text is not None:
            target_uri = source_path.as_uri()
            translated_range = source_span_to_lsp_range(
                diagnostic.span,
                source_text,
            )
        else:
            target_uri = canonical_entry_uri
            translated_range = _zero_range()

        frame_data, related_information = _translate_expansion_frames(
            diagnostic.expansion_stack,
            accepted_text=accepted_text,
        )
        data = _freeze_mapping(
            {
                "diagnostic_kind": parity_identity[1],
                "phase": parity_identity[3],
                "validation_pass": parity_identity[4],
                "authority_layer": parity_identity[5],
                "raw_span": _raw_span_payload(
                    diagnostic.span,
                    retained_path=retained_path,
                ),
                "form_path": diagnostic.form_path,
                "notes": diagnostic.notes,
                "expansion_frames": frame_data,
                "compile_entry_uri": canonical_entry_uri,
                "accepted_generation": accepted_generation,
            }
        )
        translated.append(
            DiagnosticContribution(
                target_uri=target_uri,
                compile_entry_uri=canonical_entry_uri,
                accepted_generation=accepted_generation,
                parity_identity=parity_identity,
                range=_freeze_mapping(translated_range),
                code=str(parity_identity[0]),
                severity=severity,
                source="orc",
                message=diagnostic.message,
                data=data,
                related_information=tuple(related_information),
            )
        )
    return tuple(translated)


def aggregate_diagnostic_contributions(
    contributions_by_entry: Mapping[
        str,
        tuple[DiagnosticContribution, ...],
    ],
) -> Mapping[str, tuple[DiagnosticContribution, ...]]:
    """Deduplicate current contributions without erasing independent ownership."""

    representatives: dict[
        tuple[str, tuple[object, ...]],
        tuple[str, int, DiagnosticContribution],
    ] = {}
    canonical_entry_uris: set[str] = set()
    for raw_entry_uri, contributions in contributions_by_entry.items():
        entry_uri = _canonical_file_uri(raw_entry_uri)
        if entry_uri in canonical_entry_uris:
            raise ValueError(
                "entry contribution map contains duplicate canonical owners"
            )
        canonical_entry_uris.add(entry_uri)
        if not isinstance(contributions, tuple):
            raise TypeError("entry diagnostic contributions must be tuples")
        for index, contribution in enumerate(contributions):
            if not isinstance(contribution, DiagnosticContribution):
                raise TypeError(
                    "entry contribution maps require DiagnosticContribution values"
                )
            if contribution.compile_entry_uri != entry_uri:
                raise ValueError(
                    "contribution owner does not match its entry-map key"
                )
            key = (contribution.target_uri, contribution.parity_identity)
            candidate = (entry_uri, index, contribution)
            retained = representatives.get(key)
            if retained is None or candidate[:2] < retained[:2]:
                representatives[key] = candidate

    by_target: dict[str, list[DiagnosticContribution]] = {}
    ordered = sorted(
        representatives.values(),
        key=lambda item: (
            item[2].target_uri,
            repr(item[2].parity_identity),
            item[0],
            item[1],
        ),
    )
    for _entry_uri, _index, contribution in ordered:
        by_target.setdefault(contribution.target_uri, []).append(contribution)
    return MappingProxyType(
        {
            target_uri: tuple(by_target[target_uri])
            for target_uri in sorted(by_target)
        }
    )


def _normalize_accepted_text(
    accepted_text_by_path: Mapping[Path | str, str],
) -> Mapping[Path, str]:
    if not isinstance(accepted_text_by_path, Mapping):
        raise TypeError("accepted_text_by_path must be a mapping")
    normalized: dict[Path, str] = {}
    for raw_path, text in accepted_text_by_path.items():
        if not isinstance(raw_path, (Path, str)) or not isinstance(text, str):
            raise TypeError(
                "accepted source text requires path keys and string values"
            )
        path = Path(raw_path).resolve(strict=False)
        previous = normalized.setdefault(path, text)
        if previous != text:
            raise ValueError(
                f"accepted source text disagrees for canonical path `{path}`"
            )
    return MappingProxyType(normalized)


def _canonical_file_uri(uri: str) -> str:
    if not isinstance(uri, str):
        raise TypeError("compile entry URI must be a string")
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "file"
        or parsed.netloc not in {"", "localhost"}
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ValueError("compile entry URI must be a local file URI")
    try:
        decoded_path = unquote_to_bytes(parsed.path).decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as error:
        raise ValueError(
            "compile entry URI path must be valid UTF-8"
        ) from error
    path = Path(decoded_path)
    if not path.is_absolute():
        raise ValueError("compile entry URI path must be absolute")
    return path.resolve(strict=False).as_uri()


def _canonical_diagnostic_path(raw_path: object) -> tuple[Path | None, str]:
    if not isinstance(raw_path, str) or not raw_path:
        raise TypeError("diagnostic span paths must be non-empty strings")
    if raw_path.startswith("<") and raw_path.endswith(">"):
        return None, raw_path
    path = Path(raw_path).resolve(strict=False)
    return path, str(path)


def _severity_value(severity: str) -> int:
    values = {
        "error": 1,
        "warn": 2,
        "warning": 2,
        "information": 3,
        "info": 3,
        "hint": 4,
    }
    try:
        return values[severity.lower()]
    except KeyError as error:
        raise ValueError(
            f"unsupported diagnostic severity `{severity}`"
        ) from error


def _translate_expansion_frames(
    frames: tuple[object, ...],
    *,
    accepted_text: Mapping[Path, str],
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    frame_payloads: list[Mapping[str, object]] = []
    related: list[Mapping[str, object]] = []
    for frame in frames:
        kind, name, expansion_id, call_span, definition_span = (
            _structural_frame(frame)
        )
        frame_payloads.append(
            _freeze_mapping(
                {
                    "kind": kind,
                    "name": name,
                    "expansion_id": expansion_id,
                    "call_span": (
                        _raw_span_payload(call_span)
                        if call_span is not None
                        else None
                    ),
                    "definition_span": (
                        _raw_span_payload(definition_span)
                        if definition_span is not None
                        else None
                    ),
                }
            )
        )
        for location_kind, span in (
            ("call", call_span),
            ("definition", definition_span),
        ):
            location = _related_location(
                span,
                accepted_text=accepted_text,
            )
            if location is None:
                continue
            related.append(
                _freeze_mapping(
                    {
                        "kind": location_kind,
                        "name": name,
                        "location": location,
                    }
                )
            )
    return tuple(frame_payloads), tuple(related)


def _structural_frame(
    frame: object,
) -> tuple[str, str, str | None, SourceSpan | None, SourceSpan | None]:
    missing = object()
    macro_name = getattr(frame, "macro_name", missing)
    function_name = getattr(frame, "function_name", missing)
    has_macro = isinstance(macro_name, str) and bool(macro_name)
    has_helper = isinstance(function_name, str) and bool(function_name)
    if has_macro == has_helper:
        raise TypeError(
            "expansion frame requires exactly one macro or helper name"
        )
    call_span = getattr(frame, "call_span", missing)
    definition_span = getattr(frame, "definition_span", missing)
    for label, span in (
        ("call_span", call_span),
        ("definition_span", definition_span),
    ):
        if span is missing or not (
            span is None or isinstance(span, SourceSpan)
        ):
            raise TypeError(
                f"expansion frame {label} must be a SourceSpan or None"
            )
    if has_macro:
        expansion_id = getattr(frame, "expansion_id", missing)
        if expansion_id is missing or not (
            expansion_id is None or isinstance(expansion_id, str)
        ):
            raise TypeError(
                "macro expansion frame requires a nullable expansion_id"
            )
        return (
            "macro",
            macro_name,
            expansion_id,
            call_span,
            definition_span,
        )
    if getattr(frame, "expansion_id", None) is not None:
        raise TypeError("helper expansion frame cannot carry expansion_id")
    return (
        "helper",
        function_name,
        None,
        call_span,
        definition_span,
    )


def _related_location(
    span: SourceSpan | None,
    *,
    accepted_text: Mapping[Path, str],
) -> Mapping[str, object] | None:
    if span is None:
        return None
    path, _retained_path = _canonical_diagnostic_path(span.start.path)
    if path is None or path not in accepted_text:
        return None
    translated_range = source_span_to_lsp_range(span, accepted_text[path])
    return _freeze_mapping(
        {
            "uri": path.as_uri(),
            "range": translated_range,
        }
    )


def _raw_span_payload(
    span: SourceSpan,
    *,
    retained_path: str | None = None,
) -> Mapping[str, object]:
    if not isinstance(span, SourceSpan):
        raise TypeError("diagnostic span metadata requires SourceSpan values")
    if span.start.path != span.end.path:
        raise ValueError("diagnostic span endpoints must share one path")
    _path, canonical_or_synthetic = _canonical_diagnostic_path(
        span.start.path
    )
    return _freeze_mapping(
        {
            "path": retained_path or canonical_or_synthetic,
            "start": _raw_position_payload(span.start),
            "end": _raw_position_payload(span.end),
        }
    )


def _raw_position_payload(position: SourcePosition) -> Mapping[str, int]:
    if not isinstance(position, SourcePosition):
        raise TypeError("diagnostic positions must be SourcePosition values")
    return MappingProxyType(
        {
            "line": position.line,
            "column": position.column,
            "offset": position.offset,
        }
    )


def _zero_range() -> Mapping[str, Mapping[str, int]]:
    return _freeze_mapping(
        {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 0},
        }
    )


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: _freeze_value(item)
            for key, item in value.items()
        }
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


__all__ = [
    "DiagnosticContribution",
    "aggregate_diagnostic_contributions",
    "translate_frontend_diagnostics",
]
