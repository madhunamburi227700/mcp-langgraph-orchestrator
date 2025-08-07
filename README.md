# mcp-langgraph-orchestrator
madhunamburi227700/langgraph-mcp-orchestration

# 🧠 MCP LangGraph Orchestrator

This project provides a natural language interface over a custom MCP (Model Context Protocol) toolset, powered by LangGraph and OpenAI. It allows you to perform code-related operations like dependency editing, file searching, and pattern classification using simple instructions like:

```bash
edit the dependency com.google.apis:google-api-services-cloudkms:1.22.0 with 1.22.1
🚀 Features
🧠 LLM planning: Uses OpenAI GPT-4o to determine which MCP tool to invoke.

🔁 Memory: Supports multi-step edits using in-memory context (e.g., remembering patterns between user inputs).

🛠️ Tool execution: Integrates seamlessly with MCP tools like edit_dependency, find_file, classify_pattern, and more.

💬 Fallback: Acts as a chatbot if no suitable tool is found.

🗂️ Directory Structure
graphql
Copy
Edit
mcp-langgraph-orchestrator/
│
├── langgraph_flow/
│   ├── main.py                 # Entry point for LangGraph flow
│   ├── tool_executor.py        # Custom MCP tool executor
│
├── mcp_server/
│   └── server.py               # MCP server implementing tools
│
├── prompts/
│   └── tool_selector_prompt.txt # Prompt to convert natural language to tool + args
│
├── .env                        # API key and config
├── pyproject.toml              # Poetry or pip config
└── README.md                   # You're here!
🧑‍💻 Prerequisites
Python 3.10+

uv (for faster virtual envs)

OpenAI API Key (put in .env)

OPENAI_API_KEY=your-openai-api-key
📦 Installation
Clone the repo and install dependencies:

git clone https://github.com/madhunamburi227700/mcp-langgraph-orchestrator.git
cd mcp-langgraph-orchestrator

# Install dependencies (using uv or poetry)
uv init
uv venv
activate the envirolment
uv pip install --editable .

uv run langgraph_flow/main.py
Example CLI interaction:

Ask me anything (type 'exit' to quit): edit dependency com.google.apis:google-api-services-cloudkms:1.22.0 with 1.22.1
Parsed tool: edit_dependency

Found 2 matches:
 📄 ./file1.gradle
 📄 ./file2.gradle

👉 Please call edit_dependency again with the files to edit.

Ask me anything: apply it to ./file2.gradlee
✅ Dependency successfully updated!
🔧 Tools Supported
edit_dependency – Replace dependency strings across files

find_file – Locate a file by name

classify_pattern – Classify a code pattern (e.g., Gradle, Java, etc.)

ignore_path – Ignore a path from future scans

reset_ignore – Reset ignored paths

📜 Prompt Customization
Edit prompts/tool_selector_prompt.txt to control how natural language is converted into tool calls. The format should instruct the LLM to output structured JSON like:

{
  "tool_name": "edit_dependency",
  "arguments": {
    "pattern": "implementation 'com.example:lib:1.0.0'",
    "replacement": "implementation 'com.example:lib:2.0.0'"
  }
}
🧠 Memory System
If the user runs a tool like edit_dependency without providing the pattern/replacement again, the system will reuse the last known values — making multi-step edits intuitive.

🛠 Built With
LangGraph
LangChain
OpenAI GPT-4o
Custom MCP Server

📄 License
MIT License — free to use and modify.
