"""MCP server connection and tool management."""
import json
import os
from pathlib import Path
from typing import Any
from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient


class MCPManager:
    """Manages MCP server connections and tool discovery."""
    
    def __init__(self, config_path: Path, workspace_dir: Path | None = None):
        self.config_path = config_path
        self.workspace_dir = workspace_dir
        self.config = self._load_config()
        self.clients: dict[str, MCPClient] = {}
        self.tool_descriptions: dict[str, str] = {}
    
    def _load_config(self) -> dict[str, Any]:
        """Load MCP configuration from JSON file."""
        if not self.config_path.exists():
            return {"mcpServers": {}}
        with open(self.config_path) as f:
            return json.load(f)
    
    def _resolve_workspace_path(self, args: list[str]) -> list[str]:
        """Replace workspace placeholders in args with actual path."""
        if not self.workspace_dir:
            return args
        
        resolved = []
        for arg in args:
            if arg in ("./workspace", "./workspace/", "workspace"):
                resolved.append(str(self.workspace_dir.absolute()))
            elif "{workspace}" in arg:
                resolved.append(arg.replace("{workspace}", str(self.workspace_dir.absolute())))
            else:
                resolved.append(arg)
        return resolved
    
    def create_client(self, server_name: str) -> MCPClient:
        """Create an MCP client for a specific server."""
        server_config = self.config.get("mcpServers", {}).get(server_name)
        if not server_config:
            raise ValueError(f"Server '{server_name}' not found in MCP config")
        
        command = server_config.get("command", "uvx")
        args = self._resolve_workspace_path(server_config.get("args", []))
        env = server_config.get("env", {})
        
        # Suppress MCP server info messages by setting log level to ERROR
        merged_env = {**os.environ, **(env or {})}
        merged_env["FASTMCP_LOG_LEVEL"] = "ERROR"
        merged_env["MCP_LOG_LEVEL"] = "ERROR"
        
        return MCPClient(lambda cmd=command, a=args, e=merged_env: stdio_client(
            StdioServerParameters(command=cmd, args=a, env=e)
        ))
    
    def get_all_clients(self) -> list[MCPClient]:
        """Create clients for all configured MCP servers."""
        clients = []
        for server_name in self.config.get("mcpServers", {}):
            clients.append(self.create_client(server_name))
        return clients
    
    def verify_tools(self, client: MCPClient) -> list[dict[str, Any]]:
        """Verify MCP tools are accessible and return their descriptions."""
        tools = []
        with client:
            tool_list = client.list_tools_sync()
            for mcp_tool in tool_list:
                spec = mcp_tool.tool_spec
                tool_info = {
                    "name": spec.get("name", mcp_tool.tool_name),
                    "description": spec.get("description", ""),
                    "input_schema": spec.get("inputSchema", {}),
                }
                tools.append(tool_info)
                self.tool_descriptions[tool_info["name"]] = tool_info["description"]
        return tools
    
    def get_tool_instructions(self) -> str:
        """Generate tool instructions for prompts."""
        lines = ["## Available Tools\n"]
        
        # Add MCP tool descriptions
        if self.tool_descriptions:
            lines.append("### Filesystem Tools (MCP)")
            for name, desc in self.tool_descriptions.items():
                lines.append(f"- **{name}**: {desc}")
            lines.append("")
        
        # Add sandbox executor instructions
        lines.append("### Code Execution")
        lines.append("- **execute_command**: Execute shell commands in the workspace sandbox.")
        lines.append("  Use this to run tests, execute Python scripts, or perform other shell operations.")
        lines.append("  Example: `execute_command(command=\"python -m pytest test_calculator.py -v\")`")
        lines.append("")
        
        return "\n".join(lines)
