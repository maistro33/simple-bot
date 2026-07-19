"""
Generic repository pattern implementation.

Provides a single, fully-typed CRUD implementation shared by every
domain repository, following the Repository pattern to keep persistence
concerns out of engines/services (Dependency Inversion / SOLID "D").
"""
from __future__ import annotations

from typing import Generic, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.logger import get_logger
from database.base import Base

logger = get_logger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic CRUD repository parametrised over a single SQLAlchemy model.

    Subclasses (e.g. ``ProjectRepository``) add domain-specific query
    methods on top of this generic foundation. Every method accepts an
    explicit :class:`Session` so callers control transaction boundaries
    via :func:`database.session.session_scope`.
    """

    def __init__(self, model: Type[ModelType]) -> None:
        """
        Args:
            model: The SQLAlchemy declarative model class this repository
                manages (e.g. ``Project``, ``Asset``).
        """
        self.model = model

    def create(self, session: Session, **fields) -> ModelType:
        """Instantiate, persist and return a new model instance."""
        instance = self.model(**fields)
        session.add(instance)
        session.flush()
        logger.debug("Created {} with id={}", self.model.__name__, getattr(instance, "id", None))
        return instance

    def get_by_id(self, session: Session, entity_id: str) -> ModelType | None:
        """Fetch a single row by its primary key, or None if not found."""
        return session.get(self.model, entity_id)

    def get_all(
        self, session: Session, limit: int = 100, offset: int = 0
    ) -> Sequence[ModelType]:
        """Return up to ``limit`` rows, starting at ``offset``, newest first."""
        stmt = select(self.model).limit(limit).offset(offset)
        if hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())
        return session.execute(stmt).scalars().all()

    def update(self, session: Session, entity_id: str, **fields) -> ModelType | None:
        """Update the given fields on the row identified by ``entity_id``."""
        instance = self.get_by_id(session, entity_id)
        if instance is None:
            logger.warning("{} with id={} not found for update.", self.model.__name__, entity_id)
            return None
        for key, value in fields.items():
            setattr(instance, key, value)
        session.flush()
        logger.debug("Updated {} id={} fields={}", self.model.__name__, entity_id, list(fields))
        return instance

    def delete(self, session: Session, entity_id: str) -> bool:
        """Delete the row identified by ``entity_id``. Returns True if deleted."""
        instance = self.get_by_id(session, entity_id)
        if instance is None:
            logger.warning("{} with id={} not found for delete.", self.model.__name__, entity_id)
            return False
        session.delete(instance)
        session.flush()
        logger.debug("Deleted {} id={}", self.model.__name__, entity_id)
        return True

    def count(self, session: Session) -> int:
        """Return the total number of rows for this model."""
        stmt = select(self.model)
        return len(session.execute(stmt).scalars().all())
