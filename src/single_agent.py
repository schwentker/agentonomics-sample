"""Single agent executor with context window management."""
import json
import time
from pathlib import Path
from typing import Any
from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient

from .config import BenchmarkConfig, CONTEXT_THRESHOLD
from .metrics_tracker import MetricsTracker
from .mcp_manager import MCPManager
from .requirements import extract_requirements_from_goal, create_enhanced_goal
from .sandbox_tools import create_sandbox_executor
from .prompt_loader import load_prompt
from .tracked_conversation_manager import TrackedSummarizingConversationManager


class VerboseToolCallbackHandler:
    """Callback handler that shows tool names with their key input parameters and logs to tracker."""
    
    def __init__(self, tracker: MetricsTracker | None = None):
        self.tool_count = 0
        self.tracker = tracker
        self._logged_tool_ids: set[str] = set()  # Track which tool_use_ids we've already logged
    
    def __call__(self, **kwargs):
        import sys
        
        # Handle text streaming
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)
        reasoning_text = kwargs.get("reasoningText", "")
        
        if reasoning_text:
            print(reasoning_text, end="", flush=True)
        
        if data:
            print(data, end="" if not complete else "\n", flush=True)
        
        if complete and data:
            print(flush=True)
        
        # Handle complete messages - this contains fully assembled tool use blocks
        message = kwargs.get("message")
        if message and isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content", [])
            for block in content:
                if isinstance(block, dict) and "toolUse" in block:
                    tool_use = block["toolUse"]
                    tool_name = tool_use.get("name", "")
                    tool_input = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId", "")
                    
                    if tool_name and tool_use_id and tool_use_id not in self._logged_tool_ids:
                        self._logged_tool_ids.add(tool_use_id)
                        self.tool_count += 1
                        
                        # Log to tracker
                        if self.tracker:
                            self.tracker.record_tool_use(tool_name, tool_input, tool_use_id)
                        
                        # Extract the most relevant parameter for display
                        detail = self._get_tool_detail(tool_name, tool_input)
                        if detail:
                            print(f"Tool #{self.tool_count}: {tool_name}({detail})", flush=True)
                        else:
                            print(f"Tool #{self.tool_count}: {tool_name}", flush=True)
                        
                        sys.stdout.flush()
        
        # Handle tool result
        tool_result = kwargs.get("tool_result")
        if tool_result and self.tracker:
            # Handle both dict and object-like tool_result
            if isinstance(tool_result, dict):
                tool_use_id = tool_result.get("toolUseId", "")
                content = tool_result.get("content", [])
                is_error = tool_result.get("status") == "error"
            elif hasattr(tool_result, 'toolUseId'):
                tool_use_id = getattr(tool_result, 'toolUseId', "")
                content = getattr(tool_result, 'content', [])
                is_error = getattr(tool_result, 'status', "") == "error"
            else:
                # Skip if we can't parse the tool_result
                return
            
            # Extract result text
            result_text = ""
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        result_text += item["text"]
                    elif isinstance(item, str):
                        result_text += item
            elif isinstance(content, str):
                result_text = content
            
            if tool_use_id:
                self.tracker.record_tool_result(tool_use_id, result_text, is_error)
    
    def _get_tool_detail(self, tool_name: str, tool_input: dict) -> str:
        """Extract the most relevant parameter to display for a tool."""
        if not tool_input:
            return ""
        
        # Map tool names to their key parameter
        key_params = {
            "execute_command": "command",
            "write_file": "path",
            "read_file": "path",
            "read_text_file": "path",
            "edit_file": "path",
            "create_directory": "path",
            "list_directory": "path",
            "directory_tree": "path",
            "move_file": "source",
            "search_files": "pattern",
            "read_multiple_files": "paths",
        }
        
        key = key_params.get(tool_name)
        if key and key in tool_input:
            value = tool_input[key]
            # Truncate long values
            if isinstance(value, str) and len(value) > 60:
                value = value[:57] + "..."
            elif isinstance(value, list):
                value = str(value[:3]) + ("..." if len(value) > 3 else "")
            return f"{key}={repr(value)}"
        
        # Fallback: show first string parameter
        for k, v in tool_input.items():
            if isinstance(v, str) and v:
                if len(v) > 60:
                    v = v[:57] + "..."
                return f"{k}={repr(v)}"
        
        return ""

class SingleAgentExecutor:
    """Executes a goal using a single agent with summarization strategy."""
    
    def __init__(self, config: BenchmarkConfig, api_key: str, mcp_manager: MCPManager):
        self.config = config
        self.api_key = api_key
        self.mcp_manager = mcp_manager
        self.output_dir = config.output_dir / "single_agent"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.tracker = MetricsTracker("single_agent", self.output_dir)
        
        # Create model with Anthropic
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=config.model_id,
            max_tokens=config.max_tokens,
            params=config.model_params,
        )
        
        # Create tracked conversation manager that reports summarization events
        self.conversation_manager = TrackedSummarizingConversationManager(
            on_summarization=self._on_summarization,
            summary_ratio=0.3,
            preserve_recent_messages=10,
        )
    
    def _on_summarization(self, messages_summarized: list, summary_message: dict, removed_count: int):
        """Callback when conversation is summarized."""
        # Extract summary text
        summary_text = ""
        content = summary_message.get("content", [])
        for item in content:
            if isinstance(item, dict) and "text" in item:
                summary_text += item["text"]
            elif isinstance(item, str):
                summary_text += item
        
        # Estimate tokens (rough: 4 chars per token)
        tokens_removed = sum(
            len(json.dumps(msg.get("content", ""))) // 4 
            for msg in messages_summarized
        )
        summary_tokens = len(summary_text) // 4
        
        self.tracker.record_summarization(
            messages_summarized=removed_count,
            summary_content=summary_text,
            tokens_removed=tokens_removed,
            summary_tokens=summary_tokens,
        )
    
    def _create_system_prompt(self, goal: str, tool_instructions: str) -> str:
        """Create the system prompt for the single agent."""
        # Extract structured requirements and create enhanced goal
        requirements = extract_requirements_from_goal(goal)
        enhanced_goal = create_enhanced_goal(goal, requirements)
        
        return load_prompt(
            "single_agent",
            enhanced_goal=enhanced_goal,
            tool_instructions=tool_instructions,
        )
    
    def _calculate_tool_io_sizes(self, messages: list) -> dict[str, dict[str, int]]:
        """Calculate total input/output character sizes per tool from messages.
        
        Strands SDK message format uses content blocks with 'toolUse' and 'toolResult' keys:
        - {"toolUse": {"name": "...", "toolUseId": "...", "input": {...}}}
        - {"toolResult": {"toolUseId": "...", "content": [...]}}
        """
        tool_io = {}
        tool_use_id_to_name = {}  # Map toolUseId -> tool_name for result matching
        
        for msg in messages:
            if msg.get("role") == "assistant":
                # Look for toolUse blocks in content
                for content in msg.get("content", []):
                    if isinstance(content, dict) and "toolUse" in content:
                        tool_use = content["toolUse"]
                        tool_name = tool_use.get("name", "unknown")
                        tool_use_id = tool_use.get("toolUseId", "")
                        tool_input = tool_use.get("input", {})
                        input_size = len(json.dumps(tool_input)) if tool_input else 0
                        
                        # Map toolUseId to tool_name for later result matching
                        if tool_use_id:
                            tool_use_id_to_name[tool_use_id] = tool_name
                        
                        if tool_name not in tool_io:
                            tool_io[tool_name] = {"input_chars": 0, "output_chars": 0}
                        tool_io[tool_name]["input_chars"] += input_size
            
            elif msg.get("role") == "user":
                # Look for toolResult blocks in content
                for content in msg.get("content", []):
                    if isinstance(content, dict) and "toolResult" in content:
                        tool_result = content["toolResult"]
                        tool_use_id = tool_result.get("toolUseId", "")
                        result_content = tool_result.get("content", [])
                        
                        # Calculate output size from result content
                        output_size = 0
                        for rc in result_content:
                            if isinstance(rc, dict) and "text" in rc:
                                output_size += len(rc.get("text", ""))
                            elif isinstance(rc, str):
                                output_size += len(rc)
                        
                        # Find the matching tool name
                        tool_name = tool_use_id_to_name.get(tool_use_id, "unknown")
                        if tool_name not in tool_io:
                            tool_io[tool_name] = {"input_chars": 0, "output_chars": 0}
                        tool_io[tool_name]["output_chars"] += output_size
        
        return tool_io
    
    def execute(self, goal: str) -> dict[str, Any]:
        """Execute the goal with a single agent."""
        tool_instructions = self.mcp_manager.get_tool_instructions()
        system_prompt = self._create_system_prompt(goal, tool_instructions)
        
        # Save the master prompt
        prompt_file = self.output_dir / "master_prompt.md"
        with open(prompt_file, "w") as f:
            f.write(system_prompt)
        
        # Get MCP clients for filesystem operations
        # Pass clients directly to Agent - it manages lifecycle automatically
        mcp_clients = self.mcp_manager.get_all_clients()
        
        # Create sandbox executor for code execution
        sandbox_executor = create_sandbox_executor(self.config.workspace_dir)
        
        self.tracker.start()
        self.tracker.record_message("system", system_prompt)
        
        result = {"success": False, "output": "", "error": None}
        
        # Pass MCP clients directly to Agent - lifecycle managed automatically
        # (Don't use context manager - Agent handles start/stop)
        tools = mcp_clients + [sandbox_executor]
        
        try:
            # Create callback handler with tracker for streaming logs
            callback_handler = VerboseToolCallbackHandler(tracker=self.tracker)
            
            # Create agent with all tools and verbose callback handler
            agent = Agent(
                model=self.model,
                system_prompt=system_prompt,
                tools=tools,
                conversation_manager=self.conversation_manager,
                callback_handler=callback_handler,
            )
            
            # Execute the goal
            self.tracker.record_message("user", goal)
            response = agent(goal)
            
            # Extract metrics from the agent result
            if hasattr(response, 'metrics') and response.metrics:
                metrics = response.metrics
                if hasattr(metrics, 'accumulated_usage') and metrics.accumulated_usage:
                    usage = metrics.accumulated_usage
                    # Strands SDK uses camelCase dict keys - handle both dict and object
                    if isinstance(usage, dict):
                        self.tracker.record_model_call(
                            input_tokens=usage.get('inputTokens', 0),
                            output_tokens=usage.get('outputTokens', 0),
                        )
                    elif hasattr(usage, 'inputTokens'):
                        self.tracker.record_model_call(
                            input_tokens=getattr(usage, 'inputTokens', 0),
                            output_tokens=getattr(usage, 'outputTokens', 0),
                        )
                # Record tool calls from metrics with I/O size estimation
                if hasattr(metrics, 'tool_metrics') and metrics.tool_metrics:
                    # Calculate tool I/O sizes from agent messages
                    tool_io_sizes = self._calculate_tool_io_sizes(agent.messages)
                    
                    tool_metrics = metrics.tool_metrics
                    # Handle both dict and object-like tool_metrics
                    if isinstance(tool_metrics, dict):
                        items = tool_metrics.items()
                    elif hasattr(tool_metrics, 'items'):
                        items = tool_metrics.items()
                    else:
                        items = []
                    
                    for tool_name, tm in items:
                        io_sizes = tool_io_sizes.get(tool_name, {"input_chars": 0, "output_chars": 0})
                        # Handle both object and dict-like tool metrics
                        call_count = getattr(tm, 'call_count', 0) if hasattr(tm, 'call_count') else tm.get('call_count', 0) if isinstance(tm, dict) else 0
                        success_count = getattr(tm, 'success_count', 0) if hasattr(tm, 'success_count') else tm.get('success_count', 0) if isinstance(tm, dict) else 0
                        error_count = getattr(tm, 'error_count', 0) if hasattr(tm, 'error_count') else tm.get('error_count', 0) if isinstance(tm, dict) else 0
                        total_time = getattr(tm, 'total_time', 0.0) if hasattr(tm, 'total_time') else tm.get('total_time', 0.0) if isinstance(tm, dict) else 0.0
                        
                        self.tracker.record_tool_call(
                            tool_name=tool_name,
                            call_count=call_count,
                            success_count=success_count,
                            error_count=error_count,
                            total_time=total_time,
                            input_chars=io_sizes["input_chars"],
                            output_chars=io_sizes["output_chars"],
                        )
            
            output = str(response)
            self.tracker.record_message("assistant", output)
            
            # Save raw agent messages for debugging
            raw_messages_file = self.output_dir / "raw_messages.json"
            with open(raw_messages_file, "w") as f:
                json.dump(agent.messages, f, indent=2, default=str)
            
            result["success"] = True
            result["output"] = output
            
        except Exception as e:
            error_msg = str(e)
            self.tracker.record_error(error_msg)
            result["error"] = error_msg
        
        self.tracker.stop()
        self.tracker.save()
        
        # Save result
        result_file = self.output_dir / "result.json"
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)
        
        return result
    
    def get_metrics(self) -> dict[str, Any]:
        """Get the execution metrics."""
        return self.tracker.get_summary()
