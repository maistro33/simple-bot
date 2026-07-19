"""
Engines package — one class per pipeline capability. Every engine
inherits from :class:`BaseEngine`, which injects the shared
:class:`AIManager` and standardises the ``execute`` contract so the
Workflow Engine can invoke any engine polymorphically.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.logger import get_logger
from services.ai_manager import AIManager, get_ai_manager


class BaseEngine(ABC):
    """
    Abstract base class for every pipeline engine.

    Subclasses implement :meth:`execute`, receiving the project ID and a
    mutable ``context`` dict accumulated from prior stages (e.g. the
    Script Engine's output is available to the Storyboard Engine via
    ``context["script"]``). This keeps engines decoupled from the
    database where possible — most read what they need from ``context``
    and return new data to be merged back in by the Workflow Engine.
    """

    def __init__(self, ai_manager: AIManager | None = None) -> None:
        self.ai = ai_manager or get_ai_manager()
        self.logger = get_logger(self.__class__.__module__)

    @abstractmethod
    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute this engine's pipeline stage.

        Args:
            project_id: The project this execution belongs to.
            context: Accumulated data from previously executed stages.

        Returns:
            A dict of new/updated context data to merge into the
            workflow's running context (and typically also persisted to
            the database by this method before returning).
        """
        raise NotImplementedError

    @staticmethod
    def _safe_get(context: dict[str, Any], key: str, default: Any = None) -> Any:
        """Fetch a key from context with a friendly default, avoiding KeyError noise."""
        return context.get(key, default)
