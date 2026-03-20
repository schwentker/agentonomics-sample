"""Token and execution metrics tracking with streaming conversation logging."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from .config import TokenMetrics, AgentMetrics
from .conversation_logger import ConversationLogger


@dataclass
class SummarizationMetrics:
    """Metrics for conversation summarization."""
    summarization_count: int = 0
    messages_summarized: int = 0
    tokens_removed: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "summarization_count": self.summarization_count,
            "messages_summarized": self.messages_summarized,
            "tokens_removed": self.tokens_removed,
        }


class MetricsTracker:
    """Tracks token usage and execution metrics for agents with streaming logging."""
    
    def __init__(self, agent_name: str, output_dir: Path):
        self.agent_name = agent_name
        self.output_dir = output_dir
        self.metrics = AgentMetrics(agent_name=agent_name)
        self.summarization_metrics = SummarizationMetrics()
        self.start_time: float | None = None
        
        # Streaming conversation logger
        self.conversation_logger = ConversationLogger(output_dir)
        
        # Legacy in-memory storage (kept for backward compatibility)
        self.message_history: list[dict[str, Any]] = []
        self.tool_call_history: list[dict[str, Any]] = []
        self._last_tool_call_time: float | None = None
        self._pending_retry_tool: str | None = None
    
    def start(self):
        """Start timing the execution and open log files."""
        self.start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_logger.start()
    
    def stop(self):
        """Stop timing and close log files."""
        if self.start_time:
            self.metrics.execution_time_seconds = time.time() - self.start_time
        self.conversation_logger.stop()
    
    def record_model_call(self, input_tokens: int, output_tokens: int):
        """Record tokens from a model call."""
        self.metrics.tokens.input_tokens += input_tokens
        self.metrics.tokens.output_tokens += output_tokens
    
    def record_tool_call(self, tool_name: str, call_count: int = 1, 
                         success_count: int = 0, error_count: int = 0,
                         total_time: float = 0.0, input_chars: int = 0,
                         output_chars: int = 0):
        """Record a tool call with its metrics from the SDK."""
        self.metrics.tool_calls += call_count
        
        # Track by tool type
        for _ in range(call_count):
            self.metrics.add_tool_call(tool_name)
        
        # Track errors from tool calls
        if error_count > 0:
            for _ in range(error_count):
                self.record_tool_error(
                    tool_name=tool_name,
                    error_type="tool_execution_error",
                    error_message=f"Tool {tool_name} execution failed",
                    retry_time=total_time / call_count if call_count > 0 else 0,
                )
        
        # Estimate tokens from character counts (~4 chars per token)
        estimated_input_tokens = input_chars // 4 if input_chars else 0
        estimated_output_tokens = output_chars // 4 if output_chars else 0
        
        tool_record = {
            "tool_name": tool_name,
            "call_count": call_count,
            "success_count": success_count,
            "error_count": error_count,
            "total_time_seconds": total_time,
            "avg_time_seconds": total_time / call_count if call_count > 0 else 0,
            "input_chars": input_chars,
            "output_chars": output_chars,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "timestamp": time.time(),
        }
        self.tool_call_history.append(tool_record)
        
        # Stream to file immediately
        self._append_to_jsonl("tool_calls.jsonl", tool_record)
    
    def record_tool_use(self, tool_name: str, tool_input: dict[str, Any], tool_use_id: str):
        """Record a tool invocation to the conversation log."""
        self.conversation_logger.log_tool_use(tool_name, tool_input, tool_use_id)
    
    def record_tool_result(self, tool_use_id: str, result: Any, is_error: bool = False):
        """Record a tool result to the conversation log."""
        self.conversation_logger.log_tool_result(tool_use_id, result, is_error)
    
    def record_tool_error(self, tool_name: str, error_type: str, error_message: str,
                          retry_time: float = 0.0, is_retry: bool = False):
        """Record a tool-specific error."""
        self.metrics.error_metrics.record_error(
            error_type=error_type,
            error_message=error_message,
            tool_name=tool_name,
            retry_time=retry_time,
            is_retry=is_retry,
        )
        self.conversation_logger.log_error(error_type, error_message, {"tool_name": tool_name})
    
    def record_model_error(self, error_type: str, error_message: str,
                           retry_time: float = 0.0, is_retry: bool = False):
        """Record a model-level error."""
        self.metrics.error_metrics.record_error(
            error_type=error_type,
            error_message=error_message,
            tool_name=None,
            retry_time=retry_time,
            is_retry=is_retry,
        )
        self.conversation_logger.log_error(error_type, error_message)
    
    def record_message(self, role: str, content: str):
        """Record a message in the conversation history."""
        timestamp = time.time()
        
        # Legacy in-memory storage
        self.message_history.append({
            "role": role,
            "content": content,
            "timestamp": timestamp,
        })
        
        # Stream to conversation log
        if role == "system":
            self.conversation_logger.log_system_prompt(content)
        elif role == "user":
            self.conversation_logger.log_user_message(content)
        elif role == "assistant":
            self.conversation_logger.log_assistant_message(content)
    
    def record_summarization(self, messages_summarized: int, summary_content: str,
                             tokens_removed: int = 0, summary_tokens: int = 0):
        """Record a summarization event."""
        self.summarization_metrics.summarization_count += 1
        self.summarization_metrics.messages_summarized += messages_summarized
        self.summarization_metrics.tokens_removed += tokens_removed
        
        self.conversation_logger.log_summarization(
            messages_summarized=messages_summarized,
            summary_content=summary_content,
            tokens_removed=tokens_removed,
            summary_tokens=summary_tokens,
        )
    
    def record_raw_messages(self, messages: list[dict[str, Any]]):
        """Record raw SDK messages for complete history."""
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", [])
            self.conversation_logger.log_raw_message(role, content)
    
    def record_error(self, error: str):
        """Record an error that occurred during execution."""
        self.metrics.errors.append(error)
        self.metrics.error_metrics.record_error(
            error_type="execution_error",
            error_message=error,
        )
        self.conversation_logger.log_error("execution_error", error)
    
    def _append_to_jsonl(self, filename: str, data: dict[str, Any]):
        """Append a record to a JSONL file."""
        filepath = self.output_dir / filename
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, default=str) + "\n")
    
    def save(self):
        """Save all metrics and history to files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save metrics summary (includes summarization metrics)
        metrics_dict = self.metrics.to_dict()
        metrics_dict["summarization_metrics"] = self.summarization_metrics.to_dict()
        
        metrics_file = self.output_dir / "metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(metrics_dict, f, indent=2)
        
        # Save legacy message history (for backward compatibility)
        messages_file = self.output_dir / "messages.json"
        with open(messages_file, "w") as f:
            json.dump(self.message_history, f, indent=2)
        
        # Save tool call history (final consolidated version)
        tools_file = self.output_dir / "tool_calls.json"
        with open(tools_file, "w") as f:
            json.dump(self.tool_call_history, f, indent=2)
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the metrics."""
        summary = self.metrics.to_dict()
        summary["summarization_metrics"] = self.summarization_metrics.to_dict()
        return summary


class MultiAgentMetricsTracker:
    """Aggregates metrics from multiple agents."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.agent_trackers: dict[str, MetricsTracker] = {}
        self.orchestrator_tracker: MetricsTracker | None = None
    
    def create_tracker(self, agent_name: str) -> MetricsTracker:
        """Create a new tracker for an agent."""
        agent_dir = self.output_dir / agent_name
        tracker = MetricsTracker(agent_name, agent_dir)
        self.agent_trackers[agent_name] = tracker
        return tracker
    
    def set_orchestrator(self, tracker: MetricsTracker):
        """Set the orchestrator tracker."""
        self.orchestrator_tracker = tracker
    
    def get_total_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics from all agents."""
        total = TokenMetrics()
        total_time = 0.0
        total_tool_calls = 0
        all_errors = []
        tool_calls_by_type: dict[str, int] = {}
        
        # Aggregate summarization metrics
        total_summarizations = 0
        total_messages_summarized = 0
        total_tokens_summarized = 0
        
        # Aggregate error metrics
        total_errors = 0
        total_tool_errors = 0
        total_model_errors = 0
        total_retries = 0
        total_retry_time = 0.0
        errors_by_type: dict[str, int] = {}
        errors_by_tool: dict[str, int] = {}
        errors_by_agent: dict[str, int] = {}
        
        for name, tracker in self.agent_trackers.items():
            total.input_tokens += tracker.metrics.tokens.input_tokens
            total.output_tokens += tracker.metrics.tokens.output_tokens
            total_time += tracker.metrics.execution_time_seconds
            total_tool_calls += tracker.metrics.tool_calls
            all_errors.extend(tracker.metrics.errors)
            
            # Aggregate tool calls by type
            for tool, count in tracker.metrics.tool_calls_by_type.items():
                tool_calls_by_type[tool] = tool_calls_by_type.get(tool, 0) + count
            
            # Aggregate summarization metrics
            total_summarizations += tracker.summarization_metrics.summarization_count
            total_messages_summarized += tracker.summarization_metrics.messages_summarized
            total_tokens_summarized += tracker.summarization_metrics.tokens_removed
            
            # Aggregate error metrics
            err_metrics = tracker.metrics.error_metrics
            total_errors += err_metrics.total_errors
            total_tool_errors += err_metrics.tool_errors
            total_model_errors += err_metrics.model_errors
            total_retries += err_metrics.retry_count
            total_retry_time += err_metrics.time_spent_on_retries_seconds
            
            for err_type, count in err_metrics.errors_by_type.items():
                errors_by_type[err_type] = errors_by_type.get(err_type, 0) + count
            
            for tool, count in err_metrics.errors_by_tool.items():
                errors_by_tool[tool] = errors_by_tool.get(tool, 0) + count
            
            if err_metrics.total_errors > 0:
                errors_by_agent[name] = err_metrics.total_errors
        
        # Calculate aggregate error rate
        error_rate = (total_tool_errors / total_tool_calls * 100) if total_tool_calls > 0 else 0.0
        
        return {
            "total_tokens": total.to_dict(),
            "total_execution_time_seconds": total_time,
            "effective_execution_time_seconds": round(total_time - total_retry_time, 2),
            "total_tool_calls": total_tool_calls,
            "tool_calls_by_type": tool_calls_by_type,
            "total_errors": all_errors,
            "agent_count": len(self.agent_trackers),
            "summarization_metrics": {
                "total_summarizations": total_summarizations,
                "total_messages_summarized": total_messages_summarized,
                "total_tokens_summarized": total_tokens_summarized,
            },
            "error_metrics": {
                "total_errors": total_errors,
                "tool_errors": total_tool_errors,
                "model_errors": total_model_errors,
                "retry_count": total_retries,
                "time_spent_on_retries_seconds": round(total_retry_time, 2),
                "errors_by_type": errors_by_type,
                "errors_by_tool": errors_by_tool,
                "errors_by_agent": errors_by_agent,
                "error_rate_percent": round(error_rate, 2),
            },
        }
    
    def get_sub_agent_metrics(self) -> list[dict[str, Any]]:
        """Get metrics for each individual sub-agent."""
        metrics = []
        for name, tracker in self.agent_trackers.items():
            agent_metrics = {
                "agent_name": name,
                "tokens": tracker.metrics.tokens.to_dict(),
                "execution_time_seconds": tracker.metrics.execution_time_seconds,
                "effective_execution_time_seconds": round(tracker.metrics.effective_execution_time, 2),
                "tool_calls": tracker.metrics.tool_calls,
                "tool_calls_by_type": tracker.metrics.tool_calls_by_type,
                "errors": tracker.metrics.errors,
                "error_metrics": tracker.metrics.error_metrics.to_dict(),
                "error_rate_percent": round(tracker.metrics.error_rate, 2),
                "summarization_metrics": tracker.summarization_metrics.to_dict(),
            }
            metrics.append(agent_metrics)
        return metrics
    
    def save_all(self):
        """Save all agent metrics."""
        for tracker in self.agent_trackers.values():
            tracker.save()
        
        # Save aggregated metrics
        summary_file = self.output_dir / "aggregate_metrics.json"
        with open(summary_file, "w") as f:
            json.dump(self.get_total_metrics(), f, indent=2)
