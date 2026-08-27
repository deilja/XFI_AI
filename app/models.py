from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalysisRequest:
    text: str
    source: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    summary: str
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
