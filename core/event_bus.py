"""
A lightweight synchronous/async-aware publish-subscribe event bus.

Decouples modules from one another: e.g. the Workflow Engine publishes
``stage.completed`` events, and the Project Manager, Backup Manager and
CLI progress display all subscribe independently without any of them
knowing about each other. This follows the Observer pattern and keeps
the codebase adherent to the Open/Closed principle — new subscribers
can be added without modifying the publisher.
"""
from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, DefaultDict

from core.logger import get_logger

logger = get_logger(__name__)

EventHandler = Callable[["Event"], Any | Awaitable[Any]]


@dataclass(slots=True)
class Event:
    """A single event dispatched through the :class:`EventBus`."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str | None = None


class EventBus:
    """
    Process-wide pub/sub event bus supporting both sync and async handlers.

    This class is intentionally a singleton (via :func:`get_event_bus`)
    so that every module publishing or subscribing shares the same
    registry of listeners.
    """

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """
        Register ``handler`` to be invoked whenever ``event_name`` is published.

        Args:
            event_name: The event name to listen for (e.g. ``"stage.completed"``).
                Use ``"*"`` to subscribe to every event.
            handler: A callable (sync or async) accepting a single :class:`Event`.
        """
        self._subscribers[event_name].append(handler)
        logger.debug("Subscribed handler {} to event '{}'", getattr(handler, "__name__", handler), event_name)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a previously registered handler for ``event_name``, if present."""
        handlers = self._subscribers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed handler from event '{}'", event_name)

    def publish(self, event_name: str, payload: dict[str, Any] | None = None, source: str | None = None) -> Event:
        """
        Synchronously publish an event, invoking every matching handler.

        Async handlers are scheduled on the running event loop if one
        exists, otherwise executed via ``asyncio.run``. Handler exceptions
        are caught and logged so one failing subscriber never breaks
        the publisher or other subscribers.
        """
        event = Event(name=event_name, payload=payload or {}, source=source)
        handlers = list(self._subscribers.get(event_name, [])) + list(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    self._run_awaitable(result)
            except Exception:
                logger.exception("Event handler for '{}' raised an exception.", event_name)

        logger.debug("Published event '{}' to {} handler(s).", event_name, len(handlers))
        return event

    async def publish_async(
        self, event_name: str, payload: dict[str, Any] | None = None, source: str | None = None
    ) -> Event:
        """Asynchronously publish an event, awaiting every async handler in turn."""
        event = Event(name=event_name, payload=payload or {}, source=source)
        handlers = list(self._subscribers.get(event_name, [])) + list(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Async event handler for '{}' raised an exception.", event_name)

        return event

    @staticmethod
    def _run_awaitable(awaitable: Awaitable[Any]) -> None:
        """Best-effort execution of an awaitable from a synchronous publish call."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(awaitable)
        except RuntimeError:
            asyncio.run(awaitable)  # type: ignore[arg-type]

    def clear(self) -> None:
        """Remove all registered subscribers (primarily useful for tests)."""
        self._subscribers.clear()


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide :class:`EventBus` singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
