"""Declarative rule policy definitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from watchdog.metrics.aggregator import ClientMetrics


class Policy(Protocol):
    """A policy analyses :class:`ClientMetrics` and yields decisions."""

    def evaluate(self, metrics: ClientMetrics) -> "RuleDecision":
        ...


@dataclass(slots=True)
class RuleDecision:
    """Outcome of running a policy on a given metric window."""

    email: str
    window: str
    score: float
    reasons: Iterable[str]
    action: str  # e.g. "allow", "warn", "block"
