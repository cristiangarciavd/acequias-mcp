import tomllib
from pathlib import Path

import acequias
import server

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_acequias_version_comes_from_pyproject():
    with PYPROJECT.open("rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert acequias.__version__ == expected


def test_server_package_imports():
    assert server.__name__ == "server"
