"""Conversation manager with summarization tracking."""
from typing import TYPE_CHECKING, Any, Callable
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.types.content import Message

if TYPE_CHECKING:
    from strands import Agent


class TrackedSummarizingConversationManager(SummarizingConversationManager):
    """SummarizingConversationManager that reports summarization events via callback.
    
    This subclass intercepts reduce_context calls to capture:
    - Messages being summarized
    - The generated summary
    - Token counts before/after
    """
    
    def __init__(
        self,
        on_summarization: Callable[[list[Message], Message, int], None] | None = None,
        summary_ratio: float = 0.3,
        preserve_recent_messages: int = 10,
        summarization_system_prompt: str | None = None,
    ):
        """Initialize the tracked conversation manager.
        
        Args:
            on_summarization: Callback called when summarization occurs.
                Receives (messages_summarized, summary_message, removed_count).
            summary_ratio: Ratio of messages to summarize (0.1-0.8).
            preserve_recent_messages: Minimum recent messages to keep.
            summarization_system_prompt: Optional custom summarization prompt.
        """
        super().__init__(
            summary_ratio=summary_ratio,
            preserve_recent_messages=preserve_recent_messages,
            summarization_system_prompt=summarization_system_prompt,
        )
        self._on_summarization = on_summarization
        self._pre_summarization_messages: list[Message] | None = None
    
    def reduce_context(self, agent: "Agent", e: Exception | None = None, **kwargs: Any) -> None:
        """Reduce context using summarization, with tracking.
        
        Captures the messages before summarization, calls the parent implementation,
        then reports the summarization event via callback.
        """
        # Capture messages before summarization
        messages_before = list(agent.messages)
        count_before = len(messages_before)
        
        # Call parent implementation
        super().reduce_context(agent, e, **kwargs)
        
        # Calculate what was summarized
        count_after = len(agent.messages)
        messages_removed = count_before - count_after
        
        # The first message after summarization should be the summary
        summary_message = agent.messages[0] if agent.messages else None
        
        # Report via callback
        if self._on_summarization and summary_message:
            # Extract the messages that were summarized (those not in the new list)
            # The summary replaces the first N messages
            summarized_messages = messages_before[:messages_removed + 1]  # +1 for the summary that replaced them
            self._on_summarization(summarized_messages, summary_message, messages_removed)
