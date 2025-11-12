"""WatchDog core package for independent deployments."""

from .cli import main as cli_main
from .config_loader import load_config

__all__ = [
    "cli_main",
    "load_config",
    "config",
    "collectors",
    "metrics",
    "rules",
    "notifiers",
    "services",
]
