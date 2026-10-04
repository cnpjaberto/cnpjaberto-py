import sys
import threading
from pathlib import Path

import anyio
import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session
from test_endpoints import CASES

from cnpjaberto import Client
from cnpjaberto.mcp import TOOLS, build_server


async def test_tool_discovery_and_schemas(sdk):
    server = build_server(client=sdk)
    tools = {t.name: t for t in await server.list_tools()}
    assert set(tools) == set(TOOLS) | {"search_companies"}
    assert len(tools) == 44
    assert set(TOOLS.values()) | {"search"} == {case[0] for case in CASES}
    for tool in tools.values():
        assert tool.description
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert "self" not in tool.inputSchema["properties"]
        assert "kwargs" not in tool.inputSchema["properties"]
    assert tools["search_companies"].inputSchema["required"] == ["query"]
    assert "exclude" in tools["companies_by_contact"].inputSchema["properties"]
    assert "q" in tools["list_filiais"].inputSchema["properties"]
    assert tools["leads"].inputSchema["required"] == ["uf", "municipio_codigo"]
    assert (
        tools["common_owners"].inputSchema["properties"]["cnpjs"]["items"]["type"]
        == "string"
    )
    assert "PRO" in tools["compliance_dossier"].description


@pytest.mark.parametrize("method,kwargs,path,payload", CASES, ids=[c[0] for c in CASES])
async def test_every_tool_dispatches_with_valid_output(
    sdk, httpx_mock, method, kwargs, path, payload
):
    if isinstance(payload, str):
        httpx_mock.add_response(text=payload)
    else:
        httpx_mock.add_response(json=payload)
    name = next(
        (name for name, target in TOOLS.items() if target == method), "search_companies"
    )
    if method == "search":
        kwargs = {"query": kwargs["q"]}
    result = await build_server(client=sdk).call_tool(name, kwargs)
    assert result
    assert httpx_mock.get_request().url.path == path


async def test_protocol_error_result_and_guide(sdk, httpx_mock):
    httpx_mock.add_response(
        status_code=403,
        json={"detail": {"error": "Exclusivo Pro", "upgrade_url": "/planos"}},
    )
    server = build_server(client=sdk)
    async with create_connected_server_and_client_session(
        server._mcp_server
    ) as session:
        listed = await session.list_tools()
        assert len(listed.tools) == 44
        result = await session.call_tool(
            "compliance_dossier", {"cnpj": "18236120000158"}
        )
        assert result.isError
        assert "Exclusivo Pro" in result.content[0].text
        assert "/planos" in result.content[0].text
        guide = await session.read_resource("cnpjaberto://guide")
        assert "contact_gated" in guide.contents[0].text


async def test_mcp_rate_limit_and_invalid_input(sdk, httpx_mock):
    server = build_server(client=sdk)
    httpx_mock.add_response(
        status_code=429, json={"detail": "Cota mensal"}, headers={"Retry-After": "60"}
    )
    with pytest.raises(ToolError, match="Retry-After: 60"):
        await server.call_tool("lookup_cnpj", {"cnpj": "18236120000158"})
    with pytest.raises(ToolError, match="4 caracteres"):
        await server.call_tool("search_companies", {"query": "abc"})
    assert len(httpx_mock.get_requests()) == 1


async def test_client_lifecycle(monkeypatch):
    sdk = Client("key")
    monkeypatch.setattr("cnpjaberto.mcp.Client", lambda **kwargs: sdk)
    server = build_server()
    async with create_connected_server_and_client_session(
        server._mcp_server
    ) as session:
        await session.list_tools()
        assert not sdk._http.is_closed
    assert sdk._http.is_closed


async def test_borrowed_sdk_not_closed(sdk):
    server = build_server(client=sdk)
    async with create_connected_server_and_client_session(
        server._mcp_server
    ) as session:
        await session.list_tools()
    assert not sdk._http.is_closed


@pytest.mark.parametrize("console_script", [False, True])
async def test_stdio_handshake(console_script):
    # Exercises the installed module entrypoint and real JSON-RPC framing,
    # without network calls or a real credential.
    params = StdioServerParameters(
        command=str(Path(sys.executable).with_name("cnpjaberto-mcp"))
        if console_script
        else sys.executable,
        args=[] if console_script else ["-m", "cnpjaberto.mcp"],
        env={"CNPJABERTO_API_KEY": "test-key"},
    )
    with anyio.fail_after(20):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "cnpjaberto"
                assert len((await session.list_tools()).tools) == 44


async def test_http_work_does_not_block_protocol_thread():
    protocol_thread = threading.get_ident()

    def handler(request):
        assert threading.get_ident() != protocol_thread
        return httpx.Response(200, json={"results": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        sdk = Client("key", client=http)
        result = await build_server(client=sdk).call_tool(
            "search_companies", {"query": "banco"}
        )
        assert result
