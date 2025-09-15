"""Workflow DSL type definitions using dataclasses"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Literal
from enum import Enum


class DSLVersion(Enum):
    """Supported DSL versions with feature gating"""
    V1_1 = "1.1"
    V1_1_1 = "1.1.1"
    V1_2 = "1.2"
    V1_3 = "1.3"

    @classmethod
    def from_string(cls, version: str) -> 'DSLVersion':
        """Parse version string to enum"""
        for v in cls:
            if v.value == version:
                return v
        raise ValueError(f"Unsupported DSL version: {version}")

    def supports_injection(self) -> bool:
        """Check if version supports dependency injection"""
        return self in (DSLVersion.V1_1_1, DSLVersion.V1_2, DSLVersion.V1_3)

    def supports_lifecycle(self) -> bool:
        """Check if version supports on_item_complete lifecycle"""
        return self in (DSLVersion.V1_2, DSLVersion.V1_3)

    def supports_json_validation(self) -> bool:
        """Check if version supports JSON output validation"""
        return self == DSLVersion.V1_3


class OutputCapture(Enum):
    """Output capture modes"""
    TEXT = "text"
    LINES = "lines"
    JSON = "json"


class InputMode(Enum):
    """Provider input modes"""
    ARGV = "argv"
    STDIN = "stdin"


@dataclass
class ProviderTemplate:
    """Provider template definition"""
    name: str
    command: List[str]
    defaults: Dict[str, str] = field(default_factory=dict)
    input_mode: InputMode = InputMode.ARGV


@dataclass
class DependsOnInjection:
    """Dependency injection configuration"""
    mode: Literal["list", "content", "none"] = "list"
    instruction: Optional[str] = None
    position: Literal["prepend", "append"] = "prepend"


@dataclass
class DependsOnConfig:
    """Dependencies configuration"""
    required: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    inject: Optional[Union[bool, DependsOnInjection]] = None


@dataclass
class WaitForConfig:
    """Wait-for configuration"""
    glob: str
    timeout_sec: int = 300
    poll_ms: int = 500
    min_count: int = 1


@dataclass
class ConditionEquals:
    """Equals condition"""
    left: str
    right: str


@dataclass
class Condition:
    """Step execution condition"""
    equals: Optional[ConditionEquals] = None
    exists: Optional[str] = None
    not_exists: Optional[str] = None


@dataclass
class GotoTarget:
    """Goto branching target"""
    goto: str


@dataclass
class OnHandlers:
    """Step branching handlers"""
    success: Optional[GotoTarget] = None
    failure: Optional[GotoTarget] = None
    always: Optional[GotoTarget] = None


@dataclass
class RetryConfig:
    """Retry configuration"""
    max: int
    delay_ms: int = 1000


@dataclass
class ForEachBlock:
    """For-each loop configuration"""
    items_from: Optional[str] = None
    items: Optional[List[Any]] = None
    as_var: str = "item"
    steps: List['Step'] = field(default_factory=list)

    def __post_init__(self):
        if not (self.items_from or self.items):
            raise ValueError("for_each must specify either items_from or items")
        if self.items_from and self.items:
            raise ValueError("for_each cannot specify both items_from and items")


@dataclass
class JsonOutputRequirement:
    """JSON output validation requirement (v1.3)"""
    pointer: str
    exists: bool = True
    equals: Optional[Union[str, int, bool, None]] = None
    type: Optional[Literal["string", "number", "boolean", "array", "object", "null"]] = None


@dataclass
class Step:
    """Base step definition"""
    name: str
    agent: Optional[str] = None

    # Execution types (mutually exclusive)
    provider: Optional[str] = None
    provider_params: Optional[Dict[str, str]] = None
    command: Optional[List[str]] = None
    wait_for: Optional[WaitForConfig] = None
    for_each: Optional[ForEachBlock] = None

    # I/O
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    output_capture: OutputCapture = OutputCapture.TEXT
    allow_parse_error: bool = False

    # v1.3 JSON validation
    output_schema: Optional[str] = None
    output_require: Optional[List[JsonOutputRequirement]] = None

    # Environment & secrets
    env: Dict[str, str] = field(default_factory=dict)
    secrets: List[str] = field(default_factory=list)

    # Dependencies
    depends_on: Optional[DependsOnConfig] = None

    # Control
    timeout_sec: Optional[int] = None
    retries: Optional[RetryConfig] = None
    when: Optional[Condition] = None
    on: Optional[OnHandlers] = None


@dataclass
class WorkflowSpec:
    """Top-level workflow specification"""
    version: str
    steps: List[Step]
    name: Optional[str] = None
    strict_flow: bool = True
    providers: Dict[str, ProviderTemplate] = field(default_factory=dict)
    context: Dict[str, str] = field(default_factory=dict)

    # Queue configuration
    inbox_dir: str = "inbox"
    processed_dir: str = "processed"
    failed_dir: str = "failed"
    task_extension: str = ".task"

    def __post_init__(self):
        """Post-init validation"""
        self.dsl_version = DSLVersion.from_string(self.version)