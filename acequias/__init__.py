"""Acequias game logic, independent of the MCP server."""

from importlib.metadata import version

# The version lives only in pyproject.toml; read it from the installed metadata.
__version__ = version("acequias")
