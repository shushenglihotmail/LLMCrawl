"""
Simple conversation history store.
For production, consider using Redis or PostgreSQL instead of in-memory storage.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConversationStore:
    """In-memory conversation history storage."""

    def __init__(
        self, max_age_hours: int = 24, max_messages_per_conversation: int = 50
    ):
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.timestamps: Dict[str, datetime] = {}
        self.max_age = timedelta(hours=max_age_hours)
        self.max_messages = max_messages_per_conversation

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ):
        """Add a message to conversation history."""
        self._cleanup_old_conversations()

        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []

        message = {"role": role, "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        if name:
            message["name"] = name
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self.conversations[conversation_id].append(message)
        self.timestamps[conversation_id] = datetime.now()

        # Trim if too long (keep system message + recent messages)
        if len(self.conversations[conversation_id]) > self.max_messages:
            # Keep first message (usually system prompt) and recent messages
            self.conversations[conversation_id] = [
                self.conversations[conversation_id][0]
            ] + self.conversations[conversation_id][-(self.max_messages - 1) :]

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation."""
        self._cleanup_old_conversations()
        return self.conversations.get(conversation_id, [])

    def _cleanup_old_conversations(self):
        """Remove conversations older than max_age."""
        now = datetime.now()
        expired = [
            conv_id
            for conv_id, timestamp in self.timestamps.items()
            if now - timestamp > self.max_age
        ]
        for conv_id in expired:
            del self.conversations[conv_id]
            del self.timestamps[conv_id]
            logger.info(f"Cleaned up expired conversation: {conv_id}")


# Global store instance
_conversation_store = ConversationStore()


def get_conversation_store() -> ConversationStore:
    """Get the global conversation store instance."""
    return _conversation_store
