"""The opt-in Rules v3 presets ``NORMAL_V3`` / ``FLASH_V3`` (#182)."""

from __future__ import annotations

import pytest

from acequias.config import (
    FLASH,
    FLASH_V3,
    NORMAL,
    NORMAL_V3,
    RULES_V3,
    BodegaPlacement,
    BoardShape,
    EndCondition,
    PlantingRules,
    preset,
    with_overrides,
)
from acequias.model import Mode
from acequias.sim import SimRules, _preset, play_one
from test_split_scoring import _tune

tune = _tune()

SUPPLY = {Mode.NORMAL: {2: 1, 3: 1, 4: 1.25, 5: 1.25}, Mode.FLASH: {2: 1, 3: 1}}
"""The supply multipliers the owner approved on #182."""
PIECES = {Mode.NORMAL: {2: 14, 3: 14, 4: 20, 5: 20}, Mode.FLASH: {2: 14, 3: 14}}
TARGET = {Mode.NORMAL: {2: 50, 3: 50, 4: 55, 5: 40}, Mode.FLASH: {2: 30, 3: 35}}
"""The score targets the owner approved on #182."""
GAMES = [(mode, n) for mode in Mode for n in TARGET[mode]]


def test_shipped_presets_stay_rules_v2():
    assert preset(Mode.NORMAL) is NORMAL and preset(Mode.FLASH) is FLASH
    assert RULES_V3 == {Mode.NORMAL: NORMAL_V3, Mode.FLASH: FLASH_V3}
    for p in (NORMAL, FLASH):
        assert p.planting is PlantingRules.HEXES and p.triggers == () and not p.vineyard_supply


@pytest.mark.parametrize(("mode", "n"), GAMES)
def test_v3_preset_values(mode, n):
    p = RULES_V3[mode]
    assert p.max_spins == 3
    assert p.end_conditions == (EndCondition.SUPPLY_EMPTY, EndCondition.SCORE_TARGET, EndCondition.DEAD_TURNS)
    assert p.end_condition is EndCondition.ROUNDS and p.finish_round
    assert p.bodega_placement is BodegaPlacement.NEW_SPOT and p.bodega_building
    assert p.planting is PlantingRules.VERTICES and p.board_shape is BoardShape.RIVER_STRIP
    assert p.vineyard_supply[n] == SUPPLY[mode][n]
    assert sum(p.supply_for(n).values()) == PIECES[mode][n]
    assert p.target_for(n) == TARGET[mode][n]
    assert p.round_cap(n) == 2 * p.rounds_for(n)


def test_flash_v3_rejects_4_and_5_players():
    for n in (4, 5):
        with pytest.raises(ValueError, match="flash mode is for 2 to 3 players"):
            FLASH_V3.check_players(n)
    assert NORMAL_V3.player_counts == (2, 3, 4, 5)


@pytest.mark.parametrize("mode", list(Mode))
def test_v3_presets_match_the_tuned_setup(mode):
    """One source of truth: the presets are ``tune.py``'s ``v3_best_base`` with sweep ``v3end4``'s
    combined end at the approved supply and targets, each a value the sweep tried."""
    for n, m in SUPPLY[mode].items():
        assert m in tune.V3END4_SUPPLY
        levels = tune.V3END4_TARGETS[n] if mode is Mode.NORMAL else tune.V3END4_FLASH_TARGETS
        assert TARGET[mode][n] in levels
    row = {"vineyard_supply": SUPPLY[mode], "score_target": TARGET[mode], "max_spins": tune.V3END4_SPINS}
    tuned = with_overrides(preset(mode), **{**tune.V1_OVERRIDES[mode], **tune.v3end2_base(mode), **row})
    assert tuned == RULES_V3[mode]


@pytest.mark.parametrize(("mode", "n"), GAMES)
def test_one_v3_game_ends_by_a_trigger(mode, n):
    overrides = tune.diff_from(preset(mode), RULES_V3[mode])
    rules = SimRules(mode, n, ("score_aware",) * n, overrides)
    assert _preset(rules) == RULES_V3[mode]
    final = play_one(rules, 182).final
    assert final.end_trigger in RULES_V3[mode].end_conditions
    assert final.round <= RULES_V3[mode].round_cap(n)
