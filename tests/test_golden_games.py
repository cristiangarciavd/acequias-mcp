"""Golden games: fixed simulation runs whose every result is recorded in JSON.

``tests/data/golden_games.json`` was recorded once, from the code before the
speed-ups of issue #84, and is never re-recorded to make a change pass: any
difference in a log, a final state, the water paths, a score, or a
``SimResult`` means a rule, a tie-break, or an RNG draw moved.

To record the file (only when the game rules change on purpose)::

    uv run python tests/test_golden_games.py --record
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from acequias.flow import water
from acequias.hex import Hex
from acequias.model import Mode
from acequias.sim import SimRules, game_seed, play_one, simulate_game
from acequias.turn import Bribe, Pass, PlaceCanal, PlaceFloodgate

DATA = Path(__file__).parent / "data" / "golden_games.json"

# The shipped preset values when the file was recorded (before #20 tuned
# them). The runs pin them as overrides, so retuning the presets changes no
# golden game: these runs check the engine, not the shipped numbers.
RECORDED_NORMAL = {
    "rounds": {2: 12, 3: 12, 4: 12, 5: 12},
    "hexes_per_player": 12,
    "vineyard_distance": (4, 5),
}
RECORDED_FLASH = {
    "rounds": {2: 5, 3: 5, 4: 5, 5: 5},
    "hexes_per_player": 7,
    "vineyard_distance": (2, 3),
}

# (id, mode, players, policies seat 1 first, overrides, run seed, n)
RUNS = (
    ("G1", Mode.NORMAL, 5, ("saboteur", "greedy", "saboteur", "greedy", "saboteur"), RECORDED_NORMAL, 8401, 2),
    ("G2", Mode.NORMAL, 2, ("greedy", "greedy"), RECORDED_NORMAL, 8402, 3),
    ("G3", Mode.NORMAL, 3, ("random", "random", "random"), RECORDED_NORMAL, 8403, 3),
    ("G4", Mode.FLASH, 4, ("saboteur", "greedy", "saboteur", "greedy"), RECORDED_FLASH, 8404, 3),
    ("G5", Mode.FLASH, 5, ("random", "greedy", "saboteur", "random", "greedy"), RECORDED_FLASH, 8405, 3),
    ("G6", Mode.FLASH, 2, ("saboteur", "greedy"), {**RECORDED_FLASH, "die_faces": 4}, 8406, 4),
)
RUN_IDS = [run[0] for run in RUNS]


# --- Plain JSON of a game ------------------------------------------------------


def _hex(h: Hex) -> list[int]:
    return [h.q, h.r]


def _action(action) -> dict:
    if isinstance(action, PlaceCanal):
        return {
            "type": "PlaceCanal",
            "kind": action.kind.name,
            "hex": _hex(action.hex),
            "rotation": action.rotation,
        }
    if isinstance(action, PlaceFloodgate):
        return {"type": "PlaceFloodgate", "hex": _hex(action.hex), "direction": action.direction.name}
    if isinstance(action, Bribe):
        to = None if action.to is None else [_hex(action.to[0]), action.to[1].name]
        return {
            "type": "Bribe",
            "hex": _hex(action.hex),
            "direction": action.direction.name,
            "to": to,
        }
    if isinstance(action, Pass):
        return {"type": "Pass"}
    raise TypeError(f"unknown action {action!r}")


def _path(path) -> dict:
    return {"canals": [_hex(c.hex) for c in path.canals], "owners": sorted(path.owners)}


def _state(state) -> dict:
    board = state.board
    return {
        "round": state.round,
        "start_player": state.start_player,
        "current_player": state.current_player,
        "players": [{"id": p.id, "seat": p.seat, "debt": p.debt} for p in state.players],
        "market": [k.name for k in state.market],
        "bag": [k.name for k in state.bag],
        "canals": [
            {"hex": _hex(c.hex), "kind": c.kind.name, "rotation": c.rotation, "owner": c.owner}
            for c in board.canals
        ],
        "floodgates": [
            {"hex": _hex(g.hex), "direction": g.direction.name} for g in board.floodgates
        ],
        "claims": [[_hex(h), player] for h, player in board.claims],
    }


def _score(score) -> dict:
    return {
        "player": score.player,
        "seat": score.seat,
        "vineyards": score.vineyards,
        "bodega": score.bodega,
        "rights_paid": score.rights_paid,
        "rights_collected": score.rights_collected,
        "debt": score.debt,
        "total": score.total,
        "watered": score.watered,
        "watered_vineyards": [
            {
                "hex": _hex(v.hex),
                "varietal": v.varietal.name,
                "path": _path(v.path),
                "pays": list(v.pays),
            }
            for v in score.watered_vineyards
        ],
    }


def game_json(record) -> dict:
    """Everything recorded for one game, as plain JSON data."""
    final = record.final
    return {
        "game_seed": record.game_seed,
        "log": [
            {"round": t.round, "player": t.player, "action": _action(t.action)}
            for t in record.log
        ],
        "final": _state(final),
        "water": [
            {"vineyard": _hex(h), **_path(path)} for h, path in sorted(water(final.board).items())
        ],
        "scores": {pid: _score(s) for pid, s in record.scores.items()},
        "winners": list(record.winners),
    }


def _rules(run) -> SimRules:
    _, mode, players, policies, overrides, _, _ = run
    return SimRules(mode, players, policies, overrides)


def play_run(run) -> dict:
    """The games of ``run`` played one by one with ``play_one``."""
    rules, seed, n = _rules(run), run[5], run[6]
    return {
        "seed": seed,
        "n": n,
        "games": [game_json(play_one(rules, game_seed(seed, i))) for i in range(n)],
    }


def simulate_run(run) -> dict:
    """``simulate_game(...).to_json()`` of ``run``, through a JSON round trip."""
    rules, seed, n = _rules(run), run[5], run[6]
    return json.loads(json.dumps(simulate_game(rules, n, seed).to_json()))


def record() -> None:
    data = {}
    for run in RUNS:
        data[run[0]] = {**play_run(run), "simulate_game": simulate_run(run)}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# --- Comparison ----------------------------------------------------------------


def differences(expected, actual, where: str) -> list[str]:
    """Every field where ``actual`` differs from ``expected``, by its path."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                out.append(f"{where}.{key}: missing")
            elif key not in expected:
                out.append(f"{where}.{key}: unexpected")
            else:
                out.extend(differences(expected[key], actual[key], f"{where}.{key}"))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        out = []
        if len(expected) != len(actual):
            out.append(f"{where}: length {len(actual)}, expected {len(expected)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            out.extend(differences(e, a, f"{where}[{i}]"))
        return out
    if type(expected) is not type(actual) or expected != actual:
        return [f"{where}: {actual!r}, expected {expected!r}"]
    return []


def _assert_same(expected, actual, where: str) -> None:
    diffs = differences(expected, actual, where)
    assert not diffs, f"{len(diffs)} differences, first ones:\n" + "\n".join(diffs[:20])


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_golden_file_has_every_run(golden):
    assert sorted(golden) == sorted(RUN_IDS)
    for run in RUNS:
        assert golden[run[0]]["seed"] == run[5]
        assert golden[run[0]]["n"] == run[6]
        assert len(golden[run[0]]["games"]) == run[6]


def test_golden_data_covers_every_action_and_water_rights(golden):
    actions = [
        turn["action"]
        for run in golden.values()
        for game in run["games"]
        for turn in game["log"]
    ]
    types = {a["type"] for a in actions}
    assert {"PlaceCanal", "PlaceFloodgate", "Pass"} <= types
    assert any(a["type"] == "Bribe" and a["to"] is None for a in actions)
    assert any(a["type"] == "Bribe" and a["to"] is not None for a in actions)
    assert any(
        score["rights_paid"] > 0
        for run in golden.values()
        for game in run["games"]
        for score in game["scores"].values()
    )


@pytest.mark.parametrize("run", RUNS, ids=RUN_IDS)
def test_golden_games_replay_exactly(golden, run):
    expected = golden[run[0]]
    actual = play_run(run)
    assert actual["seed"] == expected["seed"] and actual["n"] == expected["n"]
    for i, (e, a) in enumerate(zip(expected["games"], actual["games"])):
        _assert_same(e, a, f"{run[0]} game {i}")


@pytest.mark.parametrize("run", RUNS, ids=RUN_IDS)
def test_golden_simulate_game_result(golden, run):
    _assert_same(golden[run[0]]["simulate_game"], simulate_run(run), f"{run[0]} simulate_game")


if __name__ == "__main__":
    if sys.argv[1:] != ["--record"]:
        sys.exit("usage: uv run python tests/test_golden_games.py --record")
    record()
    print(f"recorded {DATA}")
