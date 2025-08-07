import os
import json
import re
import asyncio
from typing import TypedDict, cast
from dotenv import load_dotenv
from langgraph.graph import StateGraph
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langgraph_flow.tool_executor import MCPToolExecutor

# Load environment variables
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# 🧠 Global memory for edit_dependency context
edit_memory = {
    "pattern": "",
    "replacement": "",
    "files": []
}

# Shared state for LangGraph
class FlowState(TypedDict):
    input: str
    tool_name: str
    arguments: dict
    output: str

# Load prompt
with open("prompts/tool_selector_prompt.txt") as f:
    raw_prompt = f.read()

prompt = PromptTemplate.from_template(raw_prompt)
llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

# MCP Tool Executor
executor = MCPToolExecutor("code-search", command="python", args=["mcp_server/server.py"])

# Input passthrough node
def input_node(state: FlowState) -> FlowState:
    return state

# LLM planner node
async def plan_tool_call(state: FlowState) -> FlowState:
    input_text = state["input"]
    formatted_prompt = prompt.format(input=input_text)
    response = await llm.ainvoke([HumanMessage(content=formatted_prompt)])

    try:
        content = response.content
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        content = re.sub(r"```(?:json)?\n([\s\S]*?)```", r"\1", content).strip()
        parsed = json.loads(content)

        tool_name = parsed["tool_name"]
        args = parsed["arguments"]

        print("Parsed tool:", tool_name)

        # Update memory if edit_dependency is called with pattern and replacement
        if tool_name == "edit_dependency":
            if "pattern" in args and "replacement" in args:
                edit_memory["pattern"] = args["pattern"]
                edit_memory["replacement"] = args["replacement"]
                edit_memory["files"] = args.get("files", [])

        return cast(FlowState, {
            **state,
            "tool_name": tool_name,
            "arguments": args
        })

    except Exception as e:
        return cast(FlowState, {
            **state,
            "tool_name": "none",
            "output": f"Failed to parse tool call: {e}\nRaw response: {response.content}"
        })

# MCP tool executor node
async def call_mcp_tool(state: FlowState) -> FlowState:
    tool_name = state.get("tool_name", "")
    arguments = state.get("arguments", {})

    available_tools = [t.name for t in await executor.list_tools()]
    if tool_name not in available_tools:
        return cast(FlowState, {
            **state,
            "output": f"Unknown tool selected: '{tool_name}'. Available tools: {available_tools}"
        })

    # 🧠 Use memory if missing args
    if tool_name == "edit_dependency":
        if arguments.get("files") and not arguments.get("pattern"):
            arguments["pattern"] = edit_memory["pattern"]
            arguments["replacement"] = edit_memory["replacement"]

            print("🧠 Using memory:")
            print("  Pattern:", arguments["pattern"])
            print("  Replacement:", arguments["replacement"])
            print("  Files:", arguments["files"])

    try:
        result = await executor.execute_tool(tool_name, arguments)
        output = "\n".join(c.text for c in result.content if c.type == "text")

        # Optionally update memory after actual edit
        if tool_name == "edit_dependency" and "Edited" in output:
            edit_memory["files"] = arguments.get("files", edit_memory["files"])

        return cast(FlowState, {**state, "output": output})
    except Exception as e:
        return cast(FlowState, {**state, "output": f"MCP call failed: {e}"})

# General chatbot fallback
async def normal_chat_response(state: FlowState) -> FlowState:
    print("Responding as general chatbot...")
    response = await llm.ainvoke(state["input"])
    return cast(FlowState, {**state, "output": response.content})

# Router node
def router(state: FlowState) -> str:
    tool_name = state.get("tool_name", "none")
    return "call" if tool_name and tool_name != "none" else "chat"

# Build the LangGraph flow
def build_flow() -> Runnable:
    builder = StateGraph(FlowState)

    builder.add_node("input", input_node)
    builder.add_node("plan", plan_tool_call)
    builder.add_node("call", call_mcp_tool)
    builder.add_node("chat", normal_chat_response)

    builder.set_entry_point("input")
    builder.add_edge("input", "plan")

    builder.add_conditional_edges("plan", router, {
        "call": "call",
        "chat": "chat"
    })

    builder.set_finish_point("call")
    builder.set_finish_point("chat")

    return builder.compile()

# Main CLI
async def main():
    await executor.initialize()
    tools = await executor.list_tools()
    print("Available tools in MCP:", [t.name for t in tools])

    flow = build_flow()

    while True:
        user_input = input("Ask me anything (type 'exit' to quit): ")
        if user_input.strip().lower() in ["exit", "quit"]:
            break

        state: FlowState = {
            "input": user_input,
            "tool_name": "",
            "arguments": {},
            "output": ""
        }

        result = await flow.ainvoke(state)
        print("Result:", result["output"])

    await executor.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
