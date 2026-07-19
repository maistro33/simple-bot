"""
Application-wide exception hierarchy.

Using dedicated exception types (instead of bare ``Exception``) lets the
Workflow Engine, CLI and Recovery Manager react appropriately to
different failure classes (e.g. retry on ``TransientServiceError`` but
abort immediately on ``ConfigurationError``).
"""
from __future__ import annotations


class FactDropError(Exception):
    """Base class for every exception raised by FACT DROP AI STUDIO."""


class ConfigurationError(FactDropError):
    """Raised when required configuration (e.g. an API key) is missing or invalid."""


class ValidationError(FactDropError):
    """Raised when input data fails domain validation rules."""


class ProjectNotFoundError(FactDropError):
    """Raised when a referenced project ID does not exist in the database."""


class StageExecutionError(FactDropError):
    """Raised when a workflow stage fails to execute successfully."""

    def __init__(self, stage: str, message: str, *, recoverable: bool = True) -> None:
        """
        Args:
            stage: The :class:`config.constants.WorkflowStage` value (as string)
                that failed.
            message: A human-readable description of the failure.
            recoverable: Whether the Recovery Manager should attempt a retry.
        """
        self.stage = stage
        self.recoverable = recoverable
        super().__init__(f"Stage '{stage}' failed: {message}")


class AIServiceError(FactDropError):
    """Raised when an external AI provider (OpenAI, ElevenLabs, ...) call fails."""


class TransientServiceError(AIServiceError):
    """Raised for retryable failures such as network timeouts or rate limits."""


class PluginError(FactDropError):
    """Raised when an affiliate/platform plugin fails to fetch or parse data."""


class PluginNotFoundError(PluginError):
    """Raised when no registered plugin can handle a given URL or platform."""


class AssetError(FactDropError):
    """Raised for filesystem/asset persistence failures."""


class ExportError(FactDropError):
    """Raised when bundling/exporting a completed project fails."""


class QueueFullError(FactDropError):
    """Raised when the Queue Manager rejects a new job because capacity is exceeded."""
