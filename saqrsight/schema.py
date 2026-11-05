"""Common result format shared by every analysis module and evidence provider."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Module statuses. "completed" means the module ran on real input; it says nothing about the claim.
COMPLETED = "completed"
NOT_APPLICABLE = "not_applicable"   # the required input was not supplied
NOT_CONFIGURED = "not_configured"   # a model, key or provider is unavailable
FAILED = "failed"                   # the module raised an error or timed out
STATUSES = (COMPLETED, NOT_APPLICABLE, NOT_CONFIGURED, FAILED)


@dataclass
class Finding:
    """One observation produced by a module.

    code: machine-readable finding type (e.g. "urgency", "possible_synthetic", "low_agreement").
    message: plain-language explanation.
    excerpts: exact caption phrases that triggered the finding (text module).
    frames: image/frame references, e.g. {"frame": 2, "timestamp": 4.0}.
    sources: evidence references, only ever real URLs returned by a provider.
    score/confidence: raw module output; never a probability that the claim is true.
    """
    code: str
    message: str
    excerpts: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleResult:
    module: str
    status: str
    version: str
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    score: float | None = None
    confidence: str | None = None          # validated qualitative confidence, or None
    limitations: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def not_applicable(module: str, version: str, reason: str) -> ModuleResult:
    return ModuleResult(module=module, status=NOT_APPLICABLE, version=version, summary=reason)


def not_configured(module: str, version: str, reason: str, limitations: list[str] | None = None) -> ModuleResult:
    return ModuleResult(module=module, status=NOT_CONFIGURED, version=version, summary=reason,
                        limitations=limitations or [])


def failed(module: str, version: str, reason: str) -> ModuleResult:
    return ModuleResult(module=module, status=FAILED, version=version,
                        summary="This check could not be completed.", error=reason)
