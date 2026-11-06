"""In-process tests for the MCP server: a client talks to the server object,
no subprocess."""

import inspect
import json
import subprocess
import sys

import pytest
from mcp import Client

import acequias
from server.app import app, create_server, tool_errors

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


def failing_server():
    """A separate server with deliberately failing tools, so none leak into `app`."""
    test_server = create_server()

    @test_server.tool()
    @tool_errors
    def bad_value() -> str:
        """Fails the way acequias rejects bad input."""
        raise ValueError("players must be between 2 and 5")

    @test_server.tool()
    @tool_errors
    def bad_type() -> str:
        """Fails with a TypeError."""
        raise TypeError("seed must be an int")

    @test_server.tool()
    @tool_errors
    async def bad_value_async() -> str:
        """Async tool failing with a ValueError."""
        raise ValueError("async message")

    @test_server.tool()
    @tool_errors
    def crash() -> str:
        """Fails with an unexpected error."""
        raise RuntimeError("secret internal detail")

    @test_server.tool()
    @tool_errors
    def ping() -> str:
        """Same as the real ping."""
        return "pong"

    return test_server


async def test_server_info_name_and_version():
    async with Client(app) as client:
        assert client.server_info.name == "acequias"
        assert client.server_info.version == acequias.__version__


async def test_ping_listed_and_returns_pong():
    async with Client(app) as client:
        tools = (await client.list_tools()).tools
        ping = next(tool for tool in tools if tool.name == "ping")
        assert ping.description
        assert ping.input_schema.get("properties", {}) == {}

        result = await client.call_tool("ping")
        assert not result.is_error
        assert text_of(result) == "pong"


async def test_real_server_lists_only_its_own_tools():
    failing_server()  # building a test server must not touch the real one
    async with Client(app) as client:
        tools = (await client.list_tools()).tools
        assert sorted(tool.name for tool in tools) == ["calculate_score", "generate_board", "ping"]


@pytest.mark.parametrize(
    ("tool", "message"),
    [
        ("bad_value", "players must be between 2 and 5"),
        ("bad_type", "seed must be an int"),
        ("bad_value_async", "async message"),
    ],
)
async def test_value_and_type_errors_keep_their_message(tool, message):
    async with Client(failing_server()) as client:
        result = await client.call_tool(tool)
        assert result.is_error
        assert message in text_of(result)


async def test_other_exceptions_are_tool_errors_without_traceback():
    async with Client(failing_server()) as client:
        result = await client.call_tool("crash")
        assert result.is_error
        text = text_of(result)
        assert text
        assert "Traceback" not in text
        assert "secret internal detail" not in text


async def test_session_survives_a_tool_error():
    async with Client(failing_server()) as client:
        assert (await client.call_tool("bad_value")).is_error
        assert (await client.call_tool("crash")).is_error
        result = await client.call_tool("ping")
        assert not result.is_error
        assert text_of(result) == "pong"


def test_tool_errors_keeps_the_signature():
    @tool_errors
    def tool(players: int, seed: int = 0) -> str:
        return f"{players}-{seed}"

    assert tool(3, seed=7) == "3-7"
    assert tool.__name__ == "tool"
    assert list(inspect.signature(tool).parameters) == ["players", "seed"]


def test_importing_the_app_does_not_start_the_server():
    # A server started on import would block reading stdin; this returns at once.
    completed = subprocess.run(
        [sys.executable, "-c", "import server.app; print('imported')"],
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "imported"


def test_stdout_carries_only_mcp_messages():
    # One real stdio session (initialize, then ping). Each request waits for its
    # response, so closing stdin cannot cut the ping short; then every stdout
    # line must be a JSON-RPC message and the server must exit on EOF.
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ping = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ping", "arguments": {}}}

    process = subprocess.Popen(
        [sys.executable, "-m", "server.app"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    lines = []

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def response_to(request_id):
        while True:
            line = process.stdout.readline()
            assert line, "server closed stdout before answering"
            lines.append(line)
            message = json.loads(line)
            if message.get("id") == request_id:
                return message

    try:
        send(initialize)
        assert response_to(1)["result"]["serverInfo"]["name"] == "acequias"
        send(initialized)
        send(ping)
        assert response_to(2)["result"]["content"][0]["text"] == "pong"
        # communicate() closes stdin (EOF) and waits for the server to exit.
        rest, stderr = process.communicate(timeout=60)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

    assert process.returncode == 0, stderr
    lines.extend(rest.splitlines())
    messages = [json.loads(line) for line in lines if line.strip()]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
