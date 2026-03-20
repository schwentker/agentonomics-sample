"""Configuration and constants for the benchmark system."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Model specifications including context limits, max output, and pricing
# Pricing is per 1M tokens (March 2026)
# Model IDs from Anthropic API: https://api.anthropic.com/v1/models
MODEL_SPECS = {
    # Claude 4.6 (Feb 2026) - latest
    "claude-sonnet-4-6": {
        "display_name": "Claude Sonnet 4.6",
        "context": 1000000,
        "max_output": 128000,
        "input_cost_per_mtok": 3.00,
        "output_cost_per_mtok": 15.00,
    },
    "claude-opus-4-6": {
        "display_name": "Claude Opus 4.6",
        "context": 1000000,
        "max_output": 128000,
        "input_cost_per_mtok": 15.00,
        "output_cost_per_mtok": 75.00,
    },
    # Claude 4.5 (Sep-Nov 2025)
    "claude-opus-4-5-20251101": {
        "display_name": "Claude Opus 4.5",
        "context": 200000,
        "max_output": 64000,
        "input_cost_per_mtok": 15.00,
        "output_cost_per_mtok": 75.00,
    },
    "claude-sonnet-4-5-20250929": {
        "display_name": "Claude Sonnet 4.5",
        "context": 1000000,
        "max_output": 64000,
        "input_cost_per_mtok": 3.00,
        "output_cost_per_mtok": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "display_name": "Claude Haiku 4.5",
        "context": 200000,
        "max_output": 64000,
        "input_cost_per_mtok": 0.80,
        "output_cost_per_mtok": 4.00,
    },
    # Claude 4.1 (Aug 2025)
    "claude-opus-4-1-20250805": {
        "display_name": "Claude Opus 4.1",
        "context": 200000,
        "max_output": 32000,
        "input_cost_per_mtok": 15.00,
        "output_cost_per_mtok": 75.00,
    },
    # Claude 4 (May 2025)
    "claude-opus-4-20250514": {
        "display_name": "Claude Opus 4",
        "context": 200000,
        "max_output": 32000,
        "input_cost_per_mtok": 15.00,
        "output_cost_per_mtok": 75.00,
    },
    "claude-sonnet-4-20250514": {
        "display_name": "Claude Sonnet 4",
        "context": 1000000,
        "max_output": 64000,
        "input_cost_per_mtok": 3.00,
        "output_cost_per_mtok": 15.00,
    },
    # Claude 3 (Legacy)
    "claude-3-haiku-20240307": {
        "display_name": "Claude Haiku 3",
        "context": 200000,
        "max_output": 4096,
        "input_cost_per_mtok": 0.25,
        "output_cost_per_mtok": 1.25,
    },
}

# Legacy format for backward compatibility
MODEL_CONTEXT_LIMITS = {k: v["context"] for k, v in MODEL_SPECS.items()}

DEFAULT_MODEL = "claude-sonnet-4-6"
CONTEXT_THRESHOLD = 0.8  # Trigger summarization at 80% of context limit


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> dict[str, float]:
    """Calculate cost for token usage.
    
    Args:
        model_id: The model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Dict with input_cost, output_cost, and total_cost in USD
    """
    specs = MODEL_SPECS.get(model_id, {})
    input_rate = specs.get("input_cost_per_mtok", 3.00)  # Default to Sonnet pricing
    output_rate = specs.get("output_cost_per_mtok", 15.00)
    
    input_cost = (input_tokens / 1_000_000) * input_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    
    return {
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "total_cost": round(input_cost + output_cost, 4),
    }


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""
    goal_file: Path
    mcp_config_file: Path
    output_dir: Path
    model_id: str = DEFAULT_MODEL
    max_tokens: int = 16384
    temperature: float = 1.0
    top_p: float | None = None
    top_k: int | None = None
    workspace_dir: Path | None = None  # Set per-agent during execution
    
    @property
    def context_limit(self) -> int:
        return MODEL_SPECS.get(self.model_id, {}).get("context", 200000)
    
    @property
    def max_output_tokens(self) -> int:
        return MODEL_SPECS.get(self.model_id, {}).get("max_output", 16384)
    
    @property
    def summarization_threshold(self) -> int:
        return int(self.context_limit * CONTEXT_THRESHOLD)
    
    @property
    def model_params(self) -> dict:
        """Get model parameters dict for AnthropicModel."""
        params = {"temperature": self.temperature}
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.top_k is not None:
            params["top_k"] = self.top_k
        return params
    
    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for reporting."""
        specs = MODEL_SPECS.get(self.model_id, {})
        return {
            "goal_file": str(self.goal_file),
            "mcp_config_file": str(self.mcp_config_file),
            "output_dir": str(self.output_dir),
            "model_id": self.model_id,
            "model_context_limit": specs.get("context", 200000),
            "model_max_output": specs.get("max_output", 16384),
            "model_input_cost_per_mtok": specs.get("input_cost_per_mtok", 3.00),
            "model_output_cost_per_mtok": specs.get("output_cost_per_mtok", 15.00),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
        }


@dataclass
class TokenMetrics:
    """Token usage metrics for an agent run."""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class FileMetrics:
    """Metrics about files created in a workspace."""
    total_files: int = 0
    total_bytes: int = 0
    by_extension: dict[str, dict] = field(default_factory=dict)  # ext -> {count, bytes}
    
    def add_file(self, path: Path, size: int):
        """Add a file to the metrics."""
        self.total_files += 1
        self.total_bytes += size
        
        ext = path.suffix.lower() or "(no extension)"
        if ext not in self.by_extension:
            self.by_extension[ext] = {"count": 0, "bytes": 0}
        self.by_extension[ext]["count"] += 1
        self.by_extension[ext]["bytes"] += size
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "total_bytes_formatted": self._format_bytes(self.total_bytes),
            "by_extension": self.by_extension,
        }
    
    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@dataclass
class ErrorMetrics:
    """Metrics for tracking errors and retries."""
    total_errors: int = 0
    tool_errors: int = 0
    model_errors: int = 0
    retry_count: int = 0
    time_spent_on_retries_seconds: float = 0.0
    errors_by_type: dict[str, int] = field(default_factory=dict)  # error_type -> count
    errors_by_tool: dict[str, int] = field(default_factory=dict)  # tool_name -> error_count
    error_details: list[dict[str, Any]] = field(default_factory=list)  # detailed error log
    
    def record_error(self, error_type: str, error_message: str, 
                     tool_name: str | None = None, retry_time: float = 0.0,
                     is_retry: bool = False):
        """Record an error occurrence."""
        self.total_errors += 1
        
        if tool_name:
            self.tool_errors += 1
            self.errors_by_tool[tool_name] = self.errors_by_tool.get(tool_name, 0) + 1
        else:
            self.model_errors += 1
        
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1
        
        if is_retry:
            self.retry_count += 1
            self.time_spent_on_retries_seconds += retry_time
        
        self.error_details.append({
            "error_type": error_type,
            "message": error_message[:500],  # Truncate long messages
            "tool_name": tool_name,
            "retry_time_seconds": retry_time,
            "is_retry": is_retry,
        })
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage of total operations that failed."""
        return 0.0  # Will be calculated with total operations context
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total_errors": self.total_errors,
            "tool_errors": self.tool_errors,
            "model_errors": self.model_errors,
            "retry_count": self.retry_count,
            "time_spent_on_retries_seconds": round(self.time_spent_on_retries_seconds, 2),
            "errors_by_type": self.errors_by_type,
            "errors_by_tool": self.errors_by_tool,
            "error_details": self.error_details,
        }


@dataclass
class AgentMetrics:
    """Complete metrics for an agent execution."""
    agent_name: str
    tokens: TokenMetrics = field(default_factory=TokenMetrics)
    execution_time_seconds: float = 0.0
    tool_calls: int = 0
    tool_calls_by_type: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    error_metrics: ErrorMetrics = field(default_factory=ErrorMetrics)
    
    def add_tool_call(self, tool_name: str):
        """Record a tool call."""
        self.tool_calls += 1
        if tool_name not in self.tool_calls_by_type:
            self.tool_calls_by_type[tool_name] = 0
        self.tool_calls_by_type[tool_name] += 1
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage of tool calls that had errors."""
        if self.tool_calls == 0:
            return 0.0
        return (self.error_metrics.tool_errors / self.tool_calls) * 100
    
    @property
    def effective_execution_time(self) -> float:
        """Execution time minus time spent on retries."""
        return self.execution_time_seconds - self.error_metrics.time_spent_on_retries_seconds
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "tokens": self.tokens.to_dict(),
            "execution_time_seconds": self.execution_time_seconds,
            "effective_execution_time_seconds": round(self.effective_execution_time, 2),
            "tool_calls": self.tool_calls,
            "tool_calls_by_type": self.tool_calls_by_type,
            "errors": self.errors,
            "error_metrics": self.error_metrics.to_dict(),
            "error_rate_percent": round(self.error_rate, 2),
        }
