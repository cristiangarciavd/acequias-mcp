"""Shared fixtures.

A test module that sets ``PIN_RULES_V1 = True`` checks the engine under the
Rules v1 presets (``acequias.config.RULES_V1``: fixed varietals, the d6
bribe, floodgates in the bag, Flash for 2 to 5 players), the shipped presets
before #126. For the whole module, ``acequias.config.preset`` returns them,
so every game, board, and simulation that uses the shipped preset uses them.
Those rules are still options of the engine; the Rules v2 values are
pinned by ``test_config.py`` and ``test_shipped_rules.py``.
"""

from __future__ import annotations

import pytest

from acequias import config


@pytest.fixture(autouse=True, scope="module")
def _pin_rules_v1(request):
    if not getattr(request.module, "PIN_RULES_V1", False):
        yield
        return
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "_PRESETS", config.RULES_V1)
        yield
