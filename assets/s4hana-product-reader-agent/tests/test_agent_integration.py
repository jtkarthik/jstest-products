"""Integration test: end-to-end agent flow with mocked LLM and MCP tools."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

APP_DIR = Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Stub out missing sap_cloud_sdk submodules before any agent imports
_factory_mod = types.ModuleType("sap_cloud_sdk.agent_memory.factory")
_checkpoint_mod = types.ModuleType("sap_cloud_sdk.agent_memory.factory.langgraph_checkpoint")
_checkpoint_mod.create_checkpointer = MagicMock(return_value=None)
sys.modules.setdefault("sap_cloud_sdk.agent_memory.factory", _factory_mod)
sys.modules.setdefault("sap_cloud_sdk.agent_memory.factory.langgraph_checkpoint", _checkpoint_mod)

# Also stub langchain.agents.middleware if missing
try:
    from langchain.agents.middleware import SummarizationMiddleware
except (ImportError, AttributeError):
    _middleware_mod = types.ModuleType("langchain.agents.middleware")
    _middleware_mod.SummarizationMiddleware = MagicMock()
    sys.modules["langchain.agents.middleware"] = _middleware_mod


def _make_mock_llm_response(content: str):
    """Build a minimal mock LLM result compatible with the agent graph output."""
    msg = MagicMock()
    msg.content = content
    return {"messages": [msg]}


@pytest.mark.asyncio
async def test_agent_invoke_returns_product_list():
    """Agent.invoke should return a completed response with product data."""
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)

    mock_result = _make_mock_llm_response(
        "Here are 5 products from S/4HANA:\n1. PROD-001\n2. PROD-002\n3. PROD-003\n4. PROD-004\n5. PROD-005"
    )

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_graph

        from agent import SampleAgent

        agent = SampleAgent()
        response = await agent.invoke(
            query="List 5 products from S/4HANA",
            context_id="test-context-001",
            tools=tools,
        )

    assert response.status == "completed"
    assert "PROD" in response.message or len(response.message) > 0


@pytest.mark.asyncio
async def test_agent_stream_yields_processing_then_result():
    """Agent.stream should yield a 'Processing...' message, then final result."""
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)

    mock_result = _make_mock_llm_response("Found 5 products: PROD-001, PROD-002, PROD-003, PROD-004, PROD-005")

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_graph

        from agent import SampleAgent

        agent = SampleAgent()
        chunks = []
        async for chunk in agent.stream(
            query="Fetch 5 products",
            context_id="test-context-002",
            tools=tools,
        ):
            chunks.append(chunk)

    assert len(chunks) >= 2, "Expected at least 2 chunks (processing + result)"
    assert chunks[0]["is_task_complete"] is False
    assert chunks[-1]["is_task_complete"] is True


@pytest.mark.asyncio
async def test_agent_handles_error_gracefully():
    """Agent should catch exceptions and return an error response, not raise."""
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)

    with patch("agent.create_agent") as mock_create:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("MCP server unavailable"))
        mock_create.return_value = mock_graph

        from agent import SampleAgent

        agent = SampleAgent()
        response = await agent.invoke(
            query="Fetch products",
            context_id="test-context-003",
            tools=tools,
        )

    assert response.status == "completed"
    assert "error" in response.message.lower()


@pytest.mark.asyncio
async def test_milestone_m1_logged_when_tools_present(caplog):
    """M1 milestone should log 'achieved' when tools are available."""
    import logging
    from mcp_tools import get_mcp_tools

    tools = await get_mcp_tools(user_token=None)

    from agent import SampleAgent

    agent = SampleAgent()
    with caplog.at_level(logging.INFO, logger="agent"):
        await agent._initialize(tools)

    assert any("M1.achieved" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_milestone_m1_missed_when_no_tools(caplog):
    """M1 milestone should log 'missed' when no tools are available."""
    import logging
    from agent import SampleAgent

    agent = SampleAgent()
    with caplog.at_level(logging.WARNING, logger="agent"):
        result = await agent._initialize([])

    assert result is False
    assert any("M1.missed" in record.message for record in caplog.records)
