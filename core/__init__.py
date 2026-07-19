"""
Core package — application-wide infrastructure: logging, events,
managers, and the workflow engine.

Deliberately does NOT eagerly import every submodule here. Several core
modules (e.g. ``core.cache_manager``) depend on ``database.session``,
which in turn imports ``core.logger`` — eagerly aggregating all of
``core``'s submodules in this ``__init__.py`` would trigger a circular
import the moment any module did ``from core.logger import get_logger``
before ``database.session`` finished initialising. Import the specific
submodule you need instead, e.g. ``from core.asset_manager import
AssetManager``.
"""
