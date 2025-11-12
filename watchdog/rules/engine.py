"""Rule evaluation engine."""
from __future__ import annotations

from typing import Iterable, Mapping

from watchdog.config import RuleProfile, RulesConfig
from watchdog.metrics import ClientMetrics
from watchdog.rules.policies import Policy, RuleDecision


class RuleEngine:
    """Coordinate policy evaluation for each client window."""

    def __init__(self, config: RulesConfig, policies: Mapping[str, Policy]) -> None:
        self._config = config
        self._policies = policies

    def select_profile(self, email: str) -> RuleProfile:
        """Return the rule profile associated with ``email``."""

        raise NotImplementedError

    def evaluate(self, metrics: Iterable[ClientMetrics]) -> Iterable[RuleDecision]:
        """Run all configured policies and return their decisions."""

        raise NotImplementedError
