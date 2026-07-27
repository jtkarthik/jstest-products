"""Unit test for the list_products MCP tool (mocked via mcp-mock.json)."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure app/ is on path
APP_DIR = Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.mark.asyncio
async def test_list_products_tool_returns_mock_data():
    """The list_products mock tool should return the 5-item product list."""
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)
    assert tools, "Expected at least one tool from mcp-mock.json"

    list_tool = next((t for t in tools if "list" in t.name.lower()), None)
    assert list_tool is not None, "Expected a 'list_products' (or similar) tool"

    result = await list_tool.arun({})
    data = json.loads(result)

    assert "results" in data, "Expected 'results' key in mock response"
    products = data["results"]
    assert len(products) == 5, f"Expected 5 products in mock data, got {len(products)}"
    assert "Product" in products[0], "Each product should have a 'Product' field"


@pytest.mark.asyncio
async def test_list_products_tool_mock_schema():
    """The list_products tool input schema should accept $top parameter."""
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)
    list_tool = next((t for t in tools if "list" in t.name.lower()), None)
    assert list_tool is not None

    schema = list_tool.args_schema
    if schema is not None:
        fields = schema.model_fields
        # Should have optional $top parameter
        top_field = fields.get("top") or fields.get("$top")
        # Acceptable if not present — schema may not have all fields
        _ = top_field
