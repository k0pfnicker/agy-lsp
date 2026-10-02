"""Tests for MCP Server tool registration, schemas, and live execution."""

import pytest

from agy_lsp.server import create_server


@pytest.mark.asyncio
async def test_mcp_server_tools_registration_and_schemas(test_config):
    app, manager, config = create_server(test_config)

    tools = await app.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "get_diagnostics",
        "go_to_definition",
        "find_references",
        "rename_symbol",
        "document_symbols",
        "workspace_symbols",
        "hover",
        "prepare_call_hierarchy",
        "call_hierarchy",
        "get_type_hierarchy",
        "lsp_status",
    }

    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    # Verify every tool has description and valid input_schema
    for tool in tools:
        assert tool.description is not None and len(tool.description) > 0, f"Tool {tool.name} missing description"
        assert tool.input_schema is not None, f"Tool {tool.name} missing input_schema"
        assert "properties" in tool.input_schema, f"Tool {tool.name} input_schema missing properties"


@pytest.mark.asyncio
async def test_mcp_server_lsp_status_call(test_config):
    app, manager, config = create_server(test_config)

    # Call lsp_status directly
    res = await app.call_tool("lsp_status", {})
    assert res is not None
    # Result content
    assert res.content is not None
    assert len(res.content) > 0
    text_content = res.content[0].text
    assert "workspace_root" in text_content
    assert "servers" in text_content
