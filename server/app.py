"""The Acequias MCP server.

One module-level `MCPServer` (`app`) holds every tool. Tools are registered
with `@app.tool()` and wrapped with `@tool_errors`, so input errors from
`acequias` reach the client as tool errors with their message. Importing this
module does not start the server; `main()` does, over stdio.
"""

from __future__ import annotations

import functools
import inspect
import logging
import sys
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import acequias
from server.tools import board as board_tools
from server.tools import pieces as piece_tools
from server.tools import plate as plate_tools
from server.tools import score as score_tools
from server.tools import simulate as simulate_tools

F = TypeVar("F", bound=Callable[..., Any])

SERVER_NAME = "acequias"


def tool_errors(fn: F) -> F:
    """Turn `ValueError` and `TypeError` from a tool into an MCP tool error.

    The SDK keeps the message of a `ToolError` in the result (`isError` true),
    so the model can read what was wrong with its input. Any other exception
    is left to the SDK, which reports it as a tool error with only a generic
    message and logs the traceback to stderr.

    Put it under the `@app.tool()` decorator. It keeps the signature, so the
    tool's input schema is unchanged.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except (ValueError, TypeError) as exc:
                raise ToolError(str(exc)) from exc

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ValueError, TypeError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def create_server() -> MCPServer:
    """A server named `acequias` reporting `acequias.__version__`, with no tools."""
    return MCPServer(name=SERVER_NAME, version=acequias.__version__)


app = create_server()


@app.tool()
@tool_errors
def ping() -> str:
    """Check that the Acequias server is running; returns "pong"."""
    return "pong"


# Each tool lives in `server.tools`; registering it here keeps every tool on `app`.
generate_board = app.tool()(tool_errors(board_tools.generate_board))
calculate_score = app.tool()(tool_errors(score_tools.calculate_score))
simulate_game = app.tool()(tool_errors(simulate_tools.simulate_game))
generate_piece_stl = app.tool()(tool_errors(piece_tools.generate_piece_stl))
build_plate = app.tool()(tool_errors(plate_tools.build_plate))


def main() -> None:
    """Run the server over stdio (the `acequias-server` command)."""
    # stdout carries only MCP messages; logs go to stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    app.run("stdio")


if __name__ == "__main__":
    main()
