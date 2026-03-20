"""Streaming conversation logger with JSONL format for crash-safe logging."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConversationEvent:
    """A single event in the conversation history."""
    seq: int
    timestamp: float
    event_type: str  # user, assistant, tool_use, tool_result, summarization, error
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "content": self.content,
            "metadata": self.metadata,
        }


class ConversationLogger:
    """Append-only JSONL logger for conversation history.
    
    Writes each event immediately to disk for crash safety.
    Tracks summarization events and preserves summaries.
    """
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.conversation_file = output_dir / "conversation.jsonl"
        self.summarizations_dir = output_dir / "summarizations"
        
        self._seq = 0
        self._summarization_count = 0
        self._messages_before_summarization = 0
        self._tokens_summarized = 0
        self._file_handle = None
    
    def start(self):
        """Open the conversation file for appending."""
        self._file_handle = open(self.conversation_file, "a", encoding="utf-8")
    
    def stop(self):
        """Close the conversation file and write metadata."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        
        # Write conversation metadata
        meta_file = self.output_dir / "conversation_meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "total_events": self._seq,
                "summarization_count": self._summarization_count,
                "messages_before_summarization": self._messages_before_summarization,
                "tokens_summarized": self._tokens_summarized,
            }, f, indent=2)
    
    def _write_event(self, event: ConversationEvent):
        """Write a single event to the JSONL file."""
        if self._file_handle:
            self._file_handle.write(json.dumps(event.to_dict(), default=str) + "\n")
            self._file_handle.flush()  # Ensure immediate write to disk
    
    def log_system_prompt(self, content: str):
        """Log the system prompt."""
        self._seq += 1
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="system",
            content=content,
        )
        self._write_event(event)
    
    def log_user_message(self, content: str):
        """Log a user message."""
        self._seq += 1
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="user",
            content=content,
        )
        self._write_event(event)
    
    def log_assistant_message(self, content: str, tokens: dict[str, int] | None = None):
        """Log an assistant message."""
        self._seq += 1
        metadata = {}
        if tokens:
            metadata["tokens"] = tokens
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="assistant",
            content=content,
            metadata=metadata,
        )
        self._write_event(event)
    
    def log_tool_use(self, tool_name: str, tool_input: dict[str, Any], tool_use_id: str):
        """Log a tool invocation."""
        self._seq += 1
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="tool_use",
            content={
                "tool_name": tool_name,
                "input": tool_input,
            },
            metadata={"tool_use_id": tool_use_id},
        )
        self._write_event(event)
    
    def log_tool_result(self, tool_use_id: str, result: Any, is_error: bool = False):
        """Log a tool result."""
        self._seq += 1
        # Truncate very long results for the log
        result_str = str(result)
        if len(result_str) > 10000:
            result_str = result_str[:10000] + f"... [truncated, total {len(str(result))} chars]"
        
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="tool_result",
            content=result_str,
            metadata={
                "tool_use_id": tool_use_id,
                "is_error": is_error,
            },
        )
        self._write_event(event)
    
    def log_summarization(self, messages_summarized: int, summary_content: str,
                          tokens_removed: int = 0, summary_tokens: int = 0):
        """Log a summarization event and save the summary."""
        self._seq += 1
        self._summarization_count += 1
        self._messages_before_summarization += messages_summarized
        self._tokens_summarized += tokens_removed
        
        # Save the full summary to a separate file
        self.summarizations_dir.mkdir(parents=True, exist_ok=True)
        summary_file = self.summarizations_dir / f"{self._summarization_count:03d}_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "summarization_number": self._summarization_count,
                "timestamp": time.time(),
                "messages_summarized": messages_summarized,
                "tokens_removed": tokens_removed,
                "summary_tokens": summary_tokens,
                "summary": summary_content,
            }, f, indent=2)
        
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="summarization",
            content=f"[Summarization #{self._summarization_count}: {messages_summarized} messages compressed]",
            metadata={
                "summarization_number": self._summarization_count,
                "messages_summarized": messages_summarized,
                "tokens_removed": tokens_removed,
                "summary_tokens": summary_tokens,
                "summary_file": str(summary_file.name),
            },
        )
        self._write_event(event)
    
    def log_error(self, error_type: str, error_message: str, context: dict[str, Any] | None = None):
        """Log an error event."""
        self._seq += 1
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type="error",
            content=error_message,
            metadata={
                "error_type": error_type,
                **(context or {}),
            },
        )
        self._write_event(event)
    
    def log_raw_message(self, role: str, content: Any):
        """Log a raw SDK message for complete history."""
        self._seq += 1
        event = ConversationEvent(
            seq=self._seq,
            timestamp=time.time(),
            event_type=f"raw_{role}",
            content=content,
        )
        self._write_event(event)
    
    def get_summarization_metrics(self) -> dict[str, Any]:
        """Get summarization-related metrics."""
        return {
            "summarization_count": self._summarization_count,
            "messages_before_summarization": self._messages_before_summarization,
            "tokens_summarized": self._tokens_summarized,
        }
