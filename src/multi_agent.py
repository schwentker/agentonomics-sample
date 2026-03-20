"""Multi-agent orchestration executor."""
import json
import time
from pathlib import Path
from typing import Any
from strands import Agent, tool
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient
from strands.tools.executors import SequentialToolExecutor

from .config import BenchmarkConfig
from .metrics_tracker import MetricsTracker, MultiAgentMetricsTracker
from .mcp_manager import MCPManager
from .task_decomposer import TaskDecomposer, TaskDecomposition, SubTask
from .requirements import extract_requirements_from_goal, create_enhanced_goal, StructuredRequirements
from .sandbox_tools import create_sandbox_executor
from .prompt_loader import load_prompt
from .single_agent import VerboseToolCallbackHandler


class SubAgentExecutor:
    """Executes a single sub-task with its own agent."""
    
    def __init__(self, task: SubTask, api_key: str, model_id: str, 
                 output_dir: Path, mcp_manager: MCPManager, workspace_dir: Path,
                 max_tokens: int = 16384, model_params: dict | None = None):
        self.task = task
        self.api_key = api_key
        self.model_id = model_id
        self.output_dir = output_dir / f"sub_agent_{task.id}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_manager = mcp_manager
        self.workspace_dir = workspace_dir
        self.max_tokens = max_tokens
        self.model_params = model_params or {}
        
        self.tracker = MetricsTracker(f"sub_agent_{task.id}", self.output_dir)
        
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            max_tokens=max_tokens,
            params=self.model_params,
        )
    
    def _create_prompt(self, tool_instructions: str) -> str:
        """Create the prompt for this sub-agent."""
        return load_prompt(
            "sub_agent",
            task=self.task,
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
    
    def execute(self, context: str = "") -> dict[str, Any]:
        """Execute the sub-task."""
        tool_instructions = self.mcp_manager.get_tool_instructions()
        prompt = self._create_prompt(tool_instructions)
        
        # Save the sub-agent prompt
        prompt_file = self.output_dir / "prompt.md"
        with open(prompt_file, "w") as f:
            f.write(prompt)
        
        # Get MCP clients - pass directly to Agent (lifecycle managed automatically)
        mcp_clients = self.mcp_manager.get_all_clients()
        
        # Create sandbox executor for code execution
        sandbox_executor = create_sandbox_executor(self.workspace_dir)
        
        self.tracker.start()
        self.tracker.record_message("system", prompt)
        
        result = {"task_id": self.task.id, "success": False, "output": "", "error": None}
        
        # Pass MCP clients directly to Agent - lifecycle managed automatically
        tools = mcp_clients + [sandbox_executor]
        
        try:
            # Create callback handler with tracker for streaming logs
            callback_handler = VerboseToolCallbackHandler(tracker=self.tracker)
            
            agent = Agent(
                model=self.model,
                system_prompt=prompt,
                tools=tools,
                tool_executor=SequentialToolExecutor(),  # Prevent parallel tool execution
                callback_handler=callback_handler,
            )
            
            user_message = f"Execute your task. Context from previous tasks:\n{context}" if context else "Execute your task."
            self.tracker.record_message("user", user_message)
            
            response = agent(user_message)
            
            # Extract metrics
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
        
        result_file = self.output_dir / "result.json"
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)
        
        return result


class MultiAgentExecutor:
    """Orchestrates multiple agents to complete a goal."""
    
    def __init__(self, config: BenchmarkConfig, api_key: str, mcp_manager: MCPManager):
        self.config = config
        self.api_key = api_key
        self.mcp_manager = mcp_manager
        self.output_dir = config.output_dir / "multi_agent"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.metrics_tracker = MultiAgentMetricsTracker(self.output_dir)
        self.orchestrator_tracker = self.metrics_tracker.create_tracker("orchestrator")
        self.metrics_tracker.set_orchestrator(self.orchestrator_tracker)
        
        self.model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=config.model_id,
            max_tokens=config.max_tokens,
            params=config.model_params,
        )
        
        self.decomposer = TaskDecomposer(api_key, config.model_id, config.max_output_tokens)
        self.decomposition: TaskDecomposition | None = None
        self.task_results: dict[str, dict[str, Any]] = {}
    
    def _create_orchestrator_prompt(self, goal: str, decomposition: TaskDecomposition,
                                      requirements: StructuredRequirements) -> str:
        """Create the orchestrator's system prompt."""
        return load_prompt(
            "orchestrator",
            goal=goal,
            files=requirements.files,
            decomposition=decomposition,
            verification_instructions=requirements.get_verification_instructions(),
        )
    
    def _create_sub_agent_tools(self, decomposition: TaskDecomposition) -> list:
        """Create tool functions for invoking sub-agents."""
        tools = []
        
        for task in decomposition.tasks:
            # Create a closure to capture the task
            def make_tool(t: SubTask):
                def invoke_sub_agent_impl(context: str = "") -> str:
                    """Execute the sub-agent for this task."""
                    executor = SubAgentExecutor(
                        task=t,
                        api_key=self.api_key,
                        model_id=self.config.model_id,
                        output_dir=self.output_dir,
                        mcp_manager=self.mcp_manager,
                        workspace_dir=self.config.workspace_dir,
                        max_tokens=self.config.max_tokens,
                        model_params=self.config.model_params,
                    )
                    
                    # Track this sub-agent
                    self.metrics_tracker.agent_trackers[f"sub_agent_{t.id}"] = executor.tracker
                    
                    result = executor.execute(context)
                    self.task_results[t.id] = result
                    
                    # Build the response
                    if result["success"]:
                        response_text = f"Task {t.id} completed successfully:\n{result['output']}"
                    else:
                        response_text = f"Task {t.id} failed with error:\n{result['error']}"
                    
                    # Record the tool invocation and response in orchestrator's history
                    self.orchestrator_tracker.record_message(
                        "tool_call", 
                        f"invoke_{t.id}(context={repr(context[:200] + '...' if len(context) > 200 else context)})"
                    )
                    self.orchestrator_tracker.record_message(
                        "tool_result",
                        response_text[:5000]  # Truncate very long responses
                    )
                    
                    return response_text
                
                # Create the tool with proper name and docstring
                @tool(name=f"invoke_{t.id}")
                def invoke_task(context: str = "") -> str:
                    f"""Invoke sub-agent for: {t.name}. {t.description}
                    
                    Args:
                        context: Context from previous tasks to pass to this agent
                    
                    Returns:
                        The result from the sub-agent
                    """
                    return invoke_sub_agent_impl(context)
                
                return invoke_task
            
            tools.append(make_tool(task))
        
        return tools
    
    def execute(self, goal: str) -> dict[str, Any]:
        """Execute the goal with multiple coordinated agents."""
        tool_instructions = self.mcp_manager.get_tool_instructions()
        
        # Extract requirements for verification
        requirements = extract_requirements_from_goal(goal)
        
        # Decompose the goal into tasks
        self.decomposition = self.decomposer.decompose(goal, tool_instructions)
        
        # Save decomposition
        decomp_file = self.output_dir / "task_decomposition.json"
        self.decomposer.save_decomposition(self.decomposition, str(decomp_file))
        
        # Create orchestrator prompt with verification requirements
        orchestrator_prompt = self._create_orchestrator_prompt(goal, self.decomposition, requirements)
        
        # Save master prompt
        prompt_file = self.output_dir / "master_prompt.md"
        with open(prompt_file, "w") as f:
            f.write(orchestrator_prompt)
        
        # Create sub-agent tools
        sub_agent_tools = self._create_sub_agent_tools(self.decomposition)
        
        # Give orchestrator access to MCP tools for verification + sandbox executor
        # Pass clients directly to Agent - lifecycle managed automatically
        mcp_clients = self.mcp_manager.get_all_clients()
        sandbox_executor = create_sandbox_executor(self.config.workspace_dir)
        
        self.orchestrator_tracker.start()
        self.orchestrator_tracker.record_message("system", orchestrator_prompt)
        
        result = {"success": False, "output": "", "error": None, "task_results": {}}
        
        # Pass MCP clients directly to Agent - lifecycle managed automatically
        all_tools = sub_agent_tools + mcp_clients + [sandbox_executor]
        
        try:
            # Create callback handler with tracker for streaming logs
            callback_handler = VerboseToolCallbackHandler(tracker=self.orchestrator_tracker)
            
            # Create orchestrator agent with both sub-agent tools and MCP tools for verification
            orchestrator = Agent(
                model=self.model,
                system_prompt=orchestrator_prompt,
                tools=all_tools,
                tool_executor=SequentialToolExecutor(),  # Prevent parallel sub-agent execution
                callback_handler=callback_handler,
            )
            
            user_message = "Execute all tasks in the correct order to complete the goal. Pass relevant context between dependent tasks. After all tasks complete, perform the mandatory verification steps."
            self.orchestrator_tracker.record_message("user", user_message)
            
            response = orchestrator(user_message)
            
            # Extract metrics
            if hasattr(response, 'metrics') and response.metrics:
                metrics = response.metrics
                if hasattr(metrics, 'accumulated_usage') and metrics.accumulated_usage:
                    usage = metrics.accumulated_usage
                    # Strands SDK uses camelCase dict keys - handle both dict and object
                    if isinstance(usage, dict):
                        self.orchestrator_tracker.record_model_call(
                            input_tokens=usage.get('inputTokens', 0),
                            output_tokens=usage.get('outputTokens', 0),
                        )
                    elif hasattr(usage, 'inputTokens'):
                        self.orchestrator_tracker.record_model_call(
                            input_tokens=getattr(usage, 'inputTokens', 0),
                            output_tokens=getattr(usage, 'outputTokens', 0),
                        )
                # Record tool calls from metrics (orchestrator tools are the invoke_* functions)
                if hasattr(metrics, 'tool_metrics') and metrics.tool_metrics:
                    tool_metrics = metrics.tool_metrics
                    # Handle both dict and object-like tool_metrics
                    if isinstance(tool_metrics, dict):
                        items = tool_metrics.items()
                    elif hasattr(tool_metrics, 'items'):
                        items = tool_metrics.items()
                    else:
                        items = []
                    
                    for tool_name, tm in items:
                        # Handle both object and dict-like tool metrics
                        call_count = getattr(tm, 'call_count', 0) if hasattr(tm, 'call_count') else tm.get('call_count', 0) if isinstance(tm, dict) else 0
                        success_count = getattr(tm, 'success_count', 0) if hasattr(tm, 'success_count') else tm.get('success_count', 0) if isinstance(tm, dict) else 0
                        error_count = getattr(tm, 'error_count', 0) if hasattr(tm, 'error_count') else tm.get('error_count', 0) if isinstance(tm, dict) else 0
                        total_time = getattr(tm, 'total_time', 0.0) if hasattr(tm, 'total_time') else tm.get('total_time', 0.0) if isinstance(tm, dict) else 0.0
                        
                        self.orchestrator_tracker.record_tool_call(
                            tool_name=tool_name,
                            call_count=call_count,
                            success_count=success_count,
                            error_count=error_count,
                            total_time=total_time,
                        )
            
            output = str(response)
            self.orchestrator_tracker.record_message("assistant", output)
            
            result["success"] = True
            result["output"] = output
            result["task_results"] = self.task_results
            
        except Exception as e:
            error_msg = str(e)
            self.orchestrator_tracker.record_error(error_msg)
            result["error"] = error_msg
        
        self.orchestrator_tracker.stop()
        self.metrics_tracker.save_all()
        
        result_file = self.output_dir / "result.json"
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        return result
    
    def get_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics from all agents."""
        return self.metrics_tracker.get_total_metrics()
    
    def get_sub_agent_metrics(self) -> list[dict[str, Any]]:
        """Get metrics for each individual sub-agent."""
        return self.metrics_tracker.get_sub_agent_metrics()
    
    def get_decomposition_report(self) -> str:
        """Get a report of how the task was decomposed."""
        if not self.decomposition:
            return "No decomposition performed yet."
        
        lines = [
            "# Task Decomposition Report\n",
            f"## Approach\n{self.decomposition.decomposition_approach}\n",
            f"## Separation Rationale\n{self.decomposition.separation_rationale}\n",
            "## Tasks\n",
        ]
        
        for task in self.decomposition.tasks:
            lines.append(f"### {task.id}: {task.name}")
            lines.append(f"**Description:** {task.description}")
            lines.append(f"**Tools Required:** {', '.join(task.tools_required)}")
            lines.append(f"**Dependencies:** {', '.join(task.dependencies) if task.dependencies else 'None'}")
            lines.append(f"**Rationale:** {task.rationale}\n")
        
        return "\n".join(lines)
