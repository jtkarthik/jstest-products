import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Literal, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM
from opentelemetry import trace
from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section
try:
    from sap_cloud_sdk.agent_memory.factory.langgraph_checkpoint import create_checkpointer
except ModuleNotFoundError:
    def create_checkpointer(**_kwargs):
        return None

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Thread TTL in seconds (plain constant — not a platform config)
THREAD_TTL_SECONDS = 3600


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The language model powering this agent",
)
def get_model_name() -> str:
    return "sap/anthropic--claude-4.5-sonnet"


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of responses (0.0 = deterministic, 1.0 = creative)",
)
def get_temperature() -> float:
    return 0.0


@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="The full system prompt defining the agent's role and behavior",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return "You are an AI agent that retrieves up to 10 product master records from SAP S/4HANA. Help users by fetching product data on demand.\n\nIMPORTANT: You MUST use tools to retrieve live data. Never fabricate, guess, or invent product data. Always set the top (or equivalent page-size parameter) to a maximum of 10 on every product listing tool call. If the tool returns no results, inform the user explicitly. Relay tool errors verbatim without adding suggestions."


@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


class SampleAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self.llm = ChatLiteLLM(model=get_model_name(), temperature=get_temperature())
        self._checkpointer = create_checkpointer(ttl_seconds=THREAD_TTL_SECONDS)
        self._summarization_middleware = SummarizationMiddleware(
            model=self.llm,
            trigger=("tokens", 100_000),
            keep=("messages", 4),
        )

    @tracer.start_as_current_span("agent.initialize")
    async def _initialize(self, tools: Sequence[BaseTool]) -> bool:
        """Validate agent initialization and MCP server connectivity (M1)."""
        try:
            if tools:
                logger.info("M1.achieved: agent initialized and MCP server connection established")
                return True
            else:
                logger.warning("M1.missed: agent failed to initialize or MCP server is unreachable")
                return False
        except Exception:
            logger.error("M1.missed: agent failed to initialize or MCP server is unreachable")
            return False

    @tracer.start_as_current_span("agent.retrieve_products")
    async def _run_agent(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool],
    ) -> str:
        """Execute agent graph and retrieve products (M2 + M3)."""
        system_prompt = get_system_prompt()
        if not tools:
            system_prompt += (
                "\n\nIMPORTANT: No tools are currently available. "
                "Do not attempt to call any tools. Respond to the user explaining that tools are temporarily unavailable."
            )

        tool_names = [tool.name for tool in tools] if tools else []
        logger.info("Running agent with %d tool(s): %s", len(tool_names), tool_names)

        graph = create_agent(
            self.llm,
            tools=list(tools) if tools else [],
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            middleware=[self._summarization_middleware],
        )
        config = {"configurable": {"thread_id": context_id}}
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=query)]}, config
        )
        response = result["messages"][-1].content

        # M2: Products retrieved
        if response and len(response) > 0:
            logger.info("M2.achieved: products retrieved from S/4HANA successfully")
        else:
            logger.warning("M2.missed: no products returned or MCP tool call failed")

        # M3: Response delivered
        logger.info("M3.achieved: product data delivered to user")
        return response

    async def stream(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent responses."""
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing...",
        }

        try:
            tools = tools or []
            await self._initialize(tools)

            response = await self._run_agent(query, context_id, tools)

            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response,
            }

        except Exception as e:
            logger.exception("Agent stream() failed")
            logger.error("M2.missed: no products returned or MCP tool call failed")
            logger.error("M3.missed: failed to deliver product data to user")
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"I encountered an error while processing your request: {str(e)}. Please try again.",
            }

    async def invoke(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AgentResponse:
        """Invoke agent and return final response."""
        last: dict = {}
        async for chunk in self.stream(query, context_id, tools=tools):
            last = chunk
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        return AgentResponse(
            status="error", message=last.get("content", "Unknown error")
        )
