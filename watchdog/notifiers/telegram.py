"""Telegram notification interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from watchdog.config import TelegramConfig
from watchdog.rules import RuleDecision


@dataclass(slots=True)
class Notification:
    """Information that should be delivered to operators."""

    decision: RuleDecision
    message: str


class TelegramNotifier:
    """Send notifications through a Telegram bot."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config

    def format(self, decision: RuleDecision) -> Notification:
        """Build the message that will be sent to Telegram."""

        raise NotImplementedError

    def send(self, notifications: Iterable[Notification]) -> None:
        """Deliver notifications to the configured chats."""

        raise NotImplementedError
