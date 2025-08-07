import os
import re
import json
import asyncio
from typing import List,Optional
from pydantic import BaseModel
from mcp.types import Tool, TextContent
from mcp.server import Server
from mcp.server.stdio import stdio_server
from os.path import abspath

HISTORY_FILE = "update_history.json"
IGNORE_KEYWORDS = []

# --- File Indexer ---
class FileIndexer:
    def __init__(self, root="."):
        self.root = root

    def build_index(self):
        index = {}
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if not self._is_ignored(os.path.join(root, d))]
            for file in files:
                full_path = os.path.join(root, file)
                if not self._is_ignored(full_path):
                    index[file] = full_path
        return index

    def _is_ignored(self, path):
        return any(keyword in path for keyword in IGNORE_KEYWORDS)

# --- Line Classifier ---
class LineClassifier:
    @staticmethod
    def classify(line):
        stripped = line.strip()
        if re.match(r'^@\w+', stripped): return "[Annotation]"
        if re.match(r'^import\s+[\w\.]+\s*;', stripped): return "[Import]"
        if re.match(r'^\s*(public\s+)?(final\s+)?(abstract\s+)?class\s+\w+', stripped): return "[Class]"
        if re.match(r'^\s*(public|protected|private)?\s+[A-Z]\w*\s*\(.*?\)\s*\{?', stripped): return "[Constructor]"
        if re.match(r'^\s*(public|private|protected)?\s*(static\s+)?[\w\<\>\[\]]+\s+\w+\s*\(.*?\)\s*\{?', stripped): return "[Function]"
        if re.match(r'^\s*(implementation|api|compile|runtimeOnly|testImplementation|.*Implementation)\s+(platform|enforcedPlatform)?\s*[\(\'"]', stripped): return "[Gradle]"
        if re.match(r'^\s*[\w\.\-]+\s*=\s*.+', stripped): return "[Property]"
        return "[Generic]"

# --- Logger ---
class UpdateLogger:
    def __init__(self, path=HISTORY_FILE):
        self.path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                return json.load(f)
        return {"updated": [], "skipped": []}

    def save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def record(self, status, match_info):
        if status in self.data:
            self.data[status].append(match_info)
            self.save()

    def already_handled(self, file, line):
        return any(entry['file'] == file and entry['line_content'] == line for entry in self.data['updated'] + self.data['skipped'])

# --- Dependency Manager ---
class DependencyManager:
    def __init__(self, file_index, logger):
        self.file_index = file_index
        self.logger = logger

    def search(self, pattern):
        matches = []
        for file, path in self.file_index.items():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if pattern in line:
                            matches.append({
                                "file": path,
                                "line_number": idx + 1,
                                "line_content": line.strip(),
                                "tag": LineClassifier.classify(line)
                            })
            except Exception:
                continue
        return matches

    def edit(self, pattern, replacement, only_files: Optional[List[str]] = None):
        matches = self.search(pattern)
        if not matches:
            return []

        edits = []
        for match in matches:
            path = match["file"]
            if only_files and abspath(path) not in map(abspath, only_files):
                continue
            line_number = match["line_number"]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                original_line = lines[line_number - 1]
                if self.logger.already_handled(path, original_line):
                    continue

                new_line = original_line.replace(pattern, replacement)
                lines[line_number - 1] = new_line

                with open(path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                self.logger.record("updated", {
                    "file": path,
                    "line_number": line_number,
                    "line_content": original_line.strip(),
                    "new_content": new_line.strip()
                })

                edits.append(f"✅ Replaced in {path}, line {line_number}\n🔁 '{original_line.strip()}'\n➡️  '{new_line.strip()}'")
            except Exception:
                continue

        return edits

# --- Input Models ---
class PatternInput(BaseModel):
    pattern: str

class EditInput(BaseModel):
    pattern: str
    replacement: str
    files: List[str] = []

class FileNameInput(BaseModel):
    filename: str

class IgnoreInput(BaseModel):
    path: str

# --- MCP Server Entrypoint ---
async def serve() -> None:
    server = Server("mcp-pattern-tools")
    global IGNORE_KEYWORDS
    indexer = FileIndexer()
    file_index = indexer.build_index()
    logger = UpdateLogger()
    manager = DependencyManager(file_index, logger)

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return [
            Tool(name="find_file", description="Find full file path by name", inputSchema=FileNameInput.model_json_schema()),
            Tool(name="classify_pattern", description="Find and classify any matching line", inputSchema=PatternInput.model_json_schema()),
            Tool(name="edit_dependency", description="Edit lines with a dependency pattern", inputSchema=EditInput.model_json_schema()),
            Tool(name="ignore_path", description="Ignore a specific file or folder path", inputSchema=IgnoreInput.model_json_schema()),
            Tool(name="reset_ignore", description="Reset all ignored paths", inputSchema={})
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> List[TextContent]:
        nonlocal file_index, manager

        try:
            if name == "find_file":
                filename = FileNameInput(**arguments).filename
                if filename in file_index:
                    return [TextContent(type="text", text=f"{filename} -> {file_index[filename]}")]
                return [TextContent(type="text", text=f"File '{filename}' not found.")]

            elif name == "classify_pattern":
                pattern = PatternInput(**arguments).pattern
                matches = manager.search(pattern)
                if not matches:
                    return [TextContent(type="text", text=f"No matches found for '{pattern}'")]
                results = [
                    f"{m['tag']} in {m['file']}, line {m['line_number']}: {m['line_content']}"
                    for m in matches
                ]
                return [TextContent(type="text", text=f"Found {len(results)} matches for '{pattern}':\n" + "\n".join(results))]

            elif name == "edit_dependency":
                data = EditInput(**arguments)
                matches = manager.search(data.pattern)
                
                if not matches:
                    return [TextContent(type="text", text=f"No matches found for '{data.pattern}'")]

                if not data.files:
                    match_summary = [
                        f"📄 {m['file']}, line {m['line_number']} {m['tag']}: {m['line_content']}"
                        for m in matches
                    ]
                    file_list = sorted(set(m['file'] for m in matches))
                    return [TextContent(
                        type="text",
                        text=(
                            f"Found {len(match_summary)} matches for '{data.pattern}':\n\n"
                            + "\n".join(match_summary)
                            + "\n\n👉 Please call `edit_dependency` again with the `files` field set to one or more of these files:\n"
                            + "\n".join(file_list)
                        )
                    )]

                edits = manager.edit(data.pattern, data.replacement, only_files=data.files)
                if not edits:
                    return [TextContent(type="text", text=f"No edits made. Files may already be updated or skipped.")]

                return [TextContent(type="text", text=f"🛠️ Edits Applied:\n" + "\n\n".join(edits))]


            elif name == "ignore_path":
                path = IgnoreInput(**arguments).path
                IGNORE_KEYWORDS.append(path)
                file_index = FileIndexer().build_index()
                manager = DependencyManager(file_index, logger)
                return [TextContent(type="text", text=f"Ignored path: {path}")]

            elif name == "reset_ignore":
                IGNORE_KEYWORDS.clear()
                file_index = FileIndexer().build_index()
                manager = DependencyManager(file_index, logger)
                return [TextContent(type="text", text="Ignore list has been reset.")]

            return [TextContent(type="text", text="Unknown tool")]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(serve())
