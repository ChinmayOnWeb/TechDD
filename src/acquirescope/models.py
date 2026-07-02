from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Evidence:
    description: str
    path: str | None = None
    detail: str | None = None


@dataclass
class Finding:
    module: str
    title: str
    severity: Severity
    summary: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ModuleResult:
    module: str
    status: str  # "ok" | "failed"
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    metrics: dict = field(default_factory=dict)
