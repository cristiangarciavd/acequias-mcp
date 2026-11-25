"""Golden games: fixed simulation runs whose every result is recorded in JSON.

``tests/data/golden_games.json`` was recorded once, from the code before the
speed-ups of issue #84, and is never re-recorded to make a change pass: any
difference in a log, a final state, the water paths, a score, or a
``SimResult`` means a rule, a tie-break, or an RNG draw moved.

To record the file (only when the game rules change on purpose)::

    uv run python tests/test_golden_games.py --record

``tests/data/golden_games_shipped.json`` (#126) holds runs of the shipped
presets as they are (Rules v2: roulette, action die, season roll, multiple
bodegas), Normal 2-5 players and Flash 2-3, with no overrides; its JSON adds
the die actions and faces, plantings, season and drought points, and the
bodega count. Re-record it only when the shipped rules or values change on
purpose::

    uv run python tests/test_golden_games.py --record-shipped
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from acequias.config import ACTION_DIE_FACES, BribeRules, VarietalRules
from acequias.flow import water
from acequias.hex import Hex
from acequias.model import Mode, PieceKind, Varietal
from acequias.sim import SimRules, game_seed, play_one, simulate_game
from acequias.turn import (
    Bribe,
    DeclineFace,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    Release,
    Resow,
    RollActionDie,
)

DATA = Path(__file__).parent / "data" / "golden_games.json"

# The shipped preset values when the file was recorded (Rules v1, before #20
# tuned them). The runs pin every one of them as overrides, so retuning the
# presets (#20) or shipping Rules v2 (#126) changes no golden game: these
# runs check the engine, not the shipped numbers.
RULES_V1 = {
    "vineyards_per_player": 2,
    "stone_share": 10,
    "market_size": 4,
    "bag_mix": {
        PieceKind.STRAIGHT: 40,
        PieceKind.GENTLE_CURVE: 20,
        PieceKind.SHARP_CURVE: 15,
        PieceKind.SYMMETRIC_Y: 5,
        PieceKind.T_BRANCH: 5,
        PieceKind.CLAW: 5,
        PieceKind.FLOODGATE: 10,
    },
    "die_faces": 6,
    "bodega_varietals": 3,
    "water_right_points": 1,
    "varietal_rules": VarietalRules.FIXED,
    "varietal_points": {Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1},
    "grape_clusters_per_player": None,
    "bribe_rules": BribeRules.D6,
    "action_die_cost": 2,
    "action_die": ACTION_DIE_FACES,
    "season_roll_every": None,
    "multiple_bodegas": False,
    "season_roll_personal_faces": True,
}
RECORDED_NORMAL = {
    **RULES_V1,
    "rounds": {2: 12, 3: 12, 4: 12, 5: 12},
    "hexes_per_player": 12,
    "vineyard_distance": (4, 5),
    "bodega_points": 2,
}
RECORDED_FLASH = {
    **RULES_V1,
    "rounds": {2: 5, 3: 5, 4: 5, 5: 5},
    "hexes_per_player": 7,
    "vineyard_distance": (2, 3),
    "bodega_points": 1,
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


# --- Shipped presets (#126) ------------------------------------------------------

SHIPPED_DATA = Path(__file__).parent / "data" / "golden_games_shipped.json"

# (id, mode, players, policies seat 1 first, overrides, run seed, n): the
# shipped presets as they are, every player count they are for. score_aware
# and random roll the action die; greedy and saboteur decline the faces.
SHIPPED_RUNS = (
    ("S1", Mode.NORMAL, 2, ("score_aware", "random"), {}, 12601, 2),
    ("S2", Mode.NORMAL, 3, ("random", "score_aware", "greedy"), {}, 12602, 2),
    ("S3", Mode.NORMAL, 4, ("score_aware", "saboteur", "random", "greedy"), {}, 12603, 1),
    ("S4", Mode.NORMAL, 5, ("random", "score_aware", "greedy", "random", "saboteur"), {}, 12604, 1),
    ("S5", Mode.FLASH, 2, ("score_aware", "score_aware"), {}, 12605, 3),
    ("S6", Mode.FLASH, 3, ("random", "greedy", "score_aware"), {}, 12606, 3),
)
SHIPPED_IDS = [run[0] for run in SHIPPED_RUNS]


def _shipped_action(action) -> dict:
    if isinstance(action, RollActionDie):
        return {"type": "RollActionDie"}
    if isinstance(action, DeclineFace):
        return {"type": "DeclineFace"}
    if isinstance(action, Release):
        return {"type": "Release", "hex": _hex(action.hex), "direction": action.direction.name}
    if isinstance(action, Resow):
        return {"type": "Resow", "hex": _hex(action.hex)}
    return _action(action)


def _enum(value):
    return None if value is None else value.name


def shipped_game_json(record) -> dict:
    """``game_json`` plus what Rules v2 adds: die actions and faces, plantings,
    season and drought points, the pending face and season roll, and bodegas."""
    data = game_json(dataclasses.replace(record, log=()))
    data["log"] = [
        {"round": t.round, "player": t.player, "action": _shipped_action(t.action), "face": _enum(t.face)}
        for t in record.log
    ]
    final = record.final
    data["final"]["players"] = [
        {"id": p.id, "seat": p.seat, "debt": p.debt, "season": p.season, "drought": p.drought}
        for p in final.players
    ]
    data["final"]["plantings"] = [[_hex(h), v.name] for h, v in final.board.plantings]
    data["final"]["pending_face"] = _enum(final.pending_face)
    data["final"]["season_roll"] = _enum(final.season_roll)
    for pid, s in record.scores.items():
        data["scores"][pid].update(
            {"bodegas": s.bodegas, "season": s.season, "drought": s.drought, "seat_bonus": s.seat_bonus}
        )
    return data


def play_shipped_run(run) -> dict:
    """The games of a shipped ``run`` played one by one with ``play_one``."""
    rules, seed, n = _rules(run), run[5], run[6]
    return {
        "seed": seed,
        "n": n,
        "games": [shipped_game_json(play_one(rules, game_seed(seed, i))) for i in range(n)],
    }


def record_shipped() -> None:
    data = {}
    for run in SHIPPED_RUNS:
        data[run[0]] = {**play_shipped_run(run), "simulate_game": simulate_run(run)}
    SHIPPED_DATA.parent.mkdir(exist_ok=True)
    SHIPPED_DATA.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


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


@pytest.fixture(scope="module")
def golden_shipped() -> dict:
    return json.loads(SHIPPED_DATA.read_text(encoding="utf-8"))


def test_shipped_golden_file_has_every_run_and_player_count(golden_shipped):
    assert sorted(golden_shipped) == sorted(SHIPPED_IDS)
    for run in SHIPPED_RUNS:
        assert run[4] == {}  # the shipped presets as they are
        assert golden_shipped[run[0]]["seed"] == run[5]
        assert len(golden_shipped[run[0]]["games"]) == run[6]
    counts = {(run[1], run[2]) for run in SHIPPED_RUNS}
    assert counts == {(Mode.NORMAL, n) for n in (2, 3, 4, 5)} | {(Mode.FLASH, 2), (Mode.FLASH, 3)}


def test_shipped_golden_data_covers_the_rules_v2_paths(golden_shipped):
    games = [game for run in golden_shipped.values() for game in run["games"]]
    turns = [turn for game in games for turn in game["log"]]
    types = {turn["action"]["type"] for turn in turns}
    assert {"PlaceCanal", "RollActionDie", "DeclineFace", "PlaceFloodgate"} <= types
    assert types & {"Release", "Resow"}
    assert "Bribe" not in types
    faces = {turn["face"] for turn in turns if turn["face"]}
    assert {"GOOD_SEASON", "DROUGHT"} <= faces
    assert any(game["final"]["plantings"] for game in games)
    scores = [s for game in games for s in game["scores"].values()]
    assert any(s["season"] > 0 for s in scores) and any(s["drought"] > 0 for s in scores)
    assert any(s["rights_paid"] > 0 for s in scores) and any(s["debt"] > 0 for s in scores)


@pytest.mark.parametrize("run", SHIPPED_RUNS, ids=SHIPPED_IDS)
def test_shipped_golden_games_replay_exactly(golden_shipped, run):
    expected = golden_shipped[run[0]]
    actual = play_shipped_run(run)
    assert actual["seed"] == expected["seed"] and actual["n"] == expected["n"]
    for i, (e, a) in enumerate(zip(expected["games"], actual["games"])):
        _assert_same(e, a, f"{run[0]} game {i}")


@pytest.mark.parametrize("run", SHIPPED_RUNS, ids=SHIPPED_IDS)
def test_shipped_golden_simulate_game_result(golden_shipped, run):
    _assert_same(golden_shipped[run[0]]["simulate_game"], simulate_run(run), f"{run[0]} simulate_game")


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        record()
        print(f"recorded {DATA}")
    elif sys.argv[1:] == ["--record-shipped"]:
        record_shipped()
        print(f"recorded {SHIPPED_DATA}")
    else:
        sys.exit("usage: uv run python tests/test_golden_games.py --record | --record-shipped")
