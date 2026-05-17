"""Shared pytest fixtures for the Orbit Wars test suite.

Each ``smoke_test_*.py`` file installs its own kaggle stub at module
level (so it remains runnable standalone), but when pytest is the
driver we also install the stub once here as an *autouse* session
fixture. The stub is a no-op when the real ``kaggle_environments`` is
installed -- we only install our fake when no real one is importable.

This file is automatically picked up by pytest; no test needs to import
it explicitly.
"""

from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path
from types import ModuleType

import pytest

# Make the project root importable for any test that uses
# ``from orbit_wars.<sub> import ...``.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def kaggle_environments_stub():
    """If real kaggle_environments isn't installed, inject a minimal stub.

    The stub exposes ``Planet`` / ``Fleet`` namedtuples and
    ``CENTER`` / ``ROTATION_RADIUS_LIMIT`` constants -- enough for the
    legacy ``agents/sniper.py`` and ``agents/blitz.py`` to import for
    the parity tests, and enough for ``kaggle_environments.make()`` to
    be monkey-patched by individual tests if they want a fake env.
    """
    try:
        import kaggle_environments  # noqa: F401
        # Real package is present, nothing to do.
        yield
        return
    except ImportError:
        pass

    fake = ModuleType("kaggle_environments.envs.orbit_wars.orbit_wars")
    fake.Planet = namedtuple("Planet", "id owner x y radius ships production")
    fake.Fleet = namedtuple("Fleet", "id owner x y angle from_planet_id ships")
    fake.CENTER = (50.0, 50.0)
    fake.ROTATION_RADIUS_LIMIT = 50.0
    for name in (
        "kaggle_environments",
        "kaggle_environments.envs",
        "kaggle_environments.envs.orbit_wars",
    ):
        sys.modules.setdefault(name, ModuleType(name))
    sys.modules["kaggle_environments.envs.orbit_wars.orbit_wars"] = fake
    yield
