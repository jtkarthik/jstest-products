# Specification: s4hana-product-reader-agent

> **Guidelines**: Read [guidelines.md](../guidelines.md) and [guidelines-agent.md](../guidelines-agent.md) before executing ANY tasks below. Follow all constraints described there throughout execution.

## Basic Setup

- [x] Read the project input (`product-requirements-document.md`, `intent.md`)
- [x] Bootstrap agent code in `assets/s4hana-product-reader-agent/` using skill `sap-agent-bootstrap` (invoke from inside `assets/s4hana-product-reader-agent/`, use copy commands — do NOT create files manually)
- [x] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

## Project-Specific Tasks

### Agent Identity & System Prompt

- [x] Set agent name to `S/4HANA Product Reader` in `agent.py`
- [x] Set agent description: "Retrieves up to 5 product master records from SAP S/4HANA"
- [x] Write a system prompt (`@prompt_section`) that:
  - Instructs the agent to query the MCP tool to list products
  - Always sets `top` (or equivalent page-size parameter) to a maximum of 5 on every product listing tool call to limit results
  - Instructs the agent to present results clearly to the user (product ID, description, and any other key fields returned)
  - Instructs the agent NEVER to hallucinate product data — only return what the MCP tool provides
  - If no products are returned, the agent must inform the user explicitly

### MCP Tool Wiring

- [x] The agent MUST use MCP server `sap.s4:apiResource:API_PRODUCT_0002_MCP:v1` (version: v1) to read products from S/4HANA
- [x] Wire MCP tool loading in `agent.py` using `get_mcp_tools()` from `mcp_tools.py` (canonical pattern from guidelines) — NEVER create direct HTTP clients
- [x] Load tools lazily (not in `__init__`) via `_get_tools()` method

### Business Logic

- [x] The agent receives a user request to retrieve products
- [x] The agent calls the appropriate MCP tool with `top=5` (or equivalent) to limit results to 5 products
- [x] The agent formats and returns the product records to the user

### MCP Server Dependencies

- [x] Add the following entry to `assets/s4hana-product-reader-agent/asset.yaml` under `requires`:
  ```yaml
  requires:
    - name: api-product-0002-mcp
      kind: mcp-server
      ordId: sap.s4:apiResource:API_PRODUCT_0002_MCP:v1
  ```

### Business Step Instrumentation

- [x] Implement milestone M1 instrumentation in agent initialization / MCP connection:
  - On success: log `M1.achieved: agent initialized and MCP server connection established`
  - On failure: log `M1.missed: agent failed to initialize or MCP server is unreachable`
  - Add OpenTelemetry span using decorator form on the initialization helper method
- [x] Implement milestone M2 instrumentation after MCP tool call:
  - On success (at least 1 product returned): log `M2.achieved: products retrieved from S/4HANA successfully`
  - On failure (no products or error): log `M2.missed: no products returned or MCP tool call failed`
  - Add OpenTelemetry span using decorator form on the retrieval helper method
- [x] Implement milestone M3 instrumentation after formatting and returning results:
  - On success: log `M3.achieved: product data delivered to user`
  - On failure: log `M3.missed: failed to deliver product data to user`
- [x] Extract all business logic from `stream()` into `_run_agent()` plain async helper and instrument that — NEVER wrap `yield` inside `with tracer.start_as_current_span(...)`
- [x] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports

## MCP Mock Configuration

- [x] Invoke `mcp-mock-config` skill to generate `mcp-mock.json` for the MCP server `sap.s4:apiResource:API_PRODUCT_0002_MCP:v1` — required before tests can run

## Testing

- [x] `conftest.py` only sets `IBD_TESTING=true` — agent runs with mock MCP tool results during tests
- [x] Write unit tests in `assets/s4hana-product-reader-agent/tests/` — exactly one test per MCP tool used; run each immediately after writing
- [x] Write one integration test executing end-to-end agent flow with real LLM by calling the agent's `invoke` function (mock MCP tools and AI Core / LLM)
- [x] Run `pytest` from `assets/s4hana-product-reader-agent/` (no args) — if coverage < 70%, add tests until threshold met
- [x] Verify `assets/s4hana-product-reader-agent/app/agent.py` has exactly 3 decorated functions — run `grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/s4hana-product-reader-agent/app/agent.py` and confirm it returns 3
- [x] Run `pytest` again from `assets/s4hana-product-reader-agent/` (no args) to generate final `test_report.json`
- [x] Verify `test_report.json` exists in `assets/s4hana-product-reader-agent/` — if not, run pytest again until it does

## Cleanup

- [x] Delete the template runtime skill: `rm -rf assets/s4hana-product-reader-agent/app/skills/template-skill/`
