"""
Memory Client - Modular memory operations for OpenClaw-style auto-memory.

This client can be used standalone or imported into any Python project.
The logic is designed to be easily portable to Go, C#, or other languages.

Usage:
    from memory_service.client import MemoryClient

    client = MemoryClient("/path/to/memory")
    client.append_to_daily_log("user", "Hello!")
    client.append_durable_facts("User prefers Python over Go")
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class MemoryClient:
    """
    Client for OpenClaw-style memory operations.

    Handles:
    - Daily log writes (sessional memory)
    - MEMORY.md writes (durable facts)
    - Distillation prompt generation and response parsing
    """

    def __init__(self, memory_folder: str):
        """
        Initialize memory client.

        Args:
            memory_folder: Path to memory storage folder (e.g., /data/memory)
        """
        self.memory_folder = Path(memory_folder)
        self.daily_folder = self.memory_folder / "daily"
        self.memory_md = self.memory_folder / "MEMORY.md"

        # Ensure directories exist
        self.daily_folder.mkdir(parents=True, exist_ok=True)

    def append_to_daily_log(
        self, role: str, content: str, session_id: Optional[str] = None
    ) -> str:
        """
        Append a message to today's daily log.

        This is called for EVERY user/assistant message to maintain
        the full conversation transcript.

        Messages are grouped by session_id. When a new session starts,
        a session header is written to separate conversation sessions.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            session_id: Session/conversation ID for grouping messages

        Returns:
            Path to the daily log file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.daily_folder / f"{today}.md"

        entries = []
        is_new_file = not log_file.exists() or log_file.stat().st_size == 0

        # Add day header for new files
        if is_new_file:
            entries.append(f"# {today}\n")

        # Check if we need to write a session header
        if session_id:
            needs_header = True
            if not is_new_file:
                # Check if this session already has a header in today's log
                existing_content = log_file.read_text(encoding="utf-8")
                session_marker = f"[ID: {session_id}]"
                if session_marker in existing_content:
                    needs_header = False

            if needs_header:
                # Write session header
                session_time = datetime.now().strftime("%H:%M")
                # Add separator if file already has content
                if not is_new_file:
                    entries.append("\n---\n")
                entries.append(f"\n## Session {session_time} [ID: {session_id}]\n")

        # Write the message entry
        timestamp = datetime.now().strftime("%H:%M:%S")
        entries.append(f"\n### [{timestamp}] {role}\n{content}\n")

        with open(log_file, "a", encoding="utf-8") as f:
            f.writelines(entries)

        return str(log_file)

    def append_session_summary(self, summary: str) -> str:
        """
        Append a session summary to today's daily log.

        Called when 80% flush or manual distill is triggered.
        This is SESSIONAL memory - "what happened today".

        Args:
            summary: Summary text from LLM

        Returns:
            Path to the daily log file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.daily_folder / f"{today}.md"

        entry = f"\n---\n## Session Summary ({datetime.now().strftime('%H:%M')})\n{summary}\n---\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return str(log_file)

    def append_durable_facts(self, facts: str) -> str:
        """
        Append durable facts to MEMORY.md.

        Called when LLM identifies "always-true" rules or preferences.
        This is DURABLE memory - facts that will be true tomorrow too.

        Args:
            facts: Facts text from LLM

        Returns:
            Path to MEMORY.md
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## {timestamp}\n{facts}\n"

        with open(self.memory_md, "a", encoding="utf-8") as f:
            f.write(entry)

        return str(self.memory_md)

    def read_memory_md(self) -> str:
        """
        Read the contents of MEMORY.md (durable facts).

        This should be injected into the system prompt at conversation start.

        Returns:
            Contents of MEMORY.md, or empty string if doesn't exist
        """
        if not self.memory_md.exists():
            return ""
        return self.memory_md.read_text(encoding="utf-8")

    def read_daily_log(self, date: Optional[str] = None) -> str:
        """
        Read a daily log file.

        Args:
            date: Date in YYYY-MM-DD format, defaults to today

        Returns:
            Contents of the daily log, or empty string if doesn't exist
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        log_file = self.daily_folder / f"{date}.md"

        if not log_file.exists():
            return ""
        return log_file.read_text(encoding="utf-8")

    def get_distillation_prompt(self, token_usage_pct: float) -> str:
        """
        Get the hidden distillation prompt for 80% flush.

        This prompt asks the LLM to extract summary and facts,
        formatted with markers that we can parse.

        Args:
            token_usage_pct: Current token usage as percentage (0.0-1.0)

        Returns:
            Distillation prompt to inject as system message
        """
        return f"""
### MEMORY CHECKPOINT ({token_usage_pct:.0%} context used)

Before continuing with your response, please extract important information from this conversation.

**Format your extraction with these exact markers:**

[SUMMARY]
(2-3 sentence recap of what was accomplished in this session)
[/SUMMARY]

[FACTS]
- Any permanent rules, preferences, or constraints discovered
- Important decisions that should be remembered
- Technical details that will be true in future sessions
(Leave empty if no durable facts to save)
[/FACTS]

After the markers, continue with your normal response to the user.
The user will NOT see the [SUMMARY] and [FACTS] sections - they are for memory only.
"""

    def parse_distillation_response(self, response: str) -> Tuple[str, str]:
        """
        Parse LLM response for summary and facts markers.

        Args:
            response: Full LLM response text

        Returns:
            Tuple of (summary, facts) - both may be empty strings
        """
        summary = ""
        facts = ""

        # Extract [SUMMARY]...[/SUMMARY]
        summary_match = re.search(
            r"\[SUMMARY\](.*?)\[/SUMMARY\]", response, re.DOTALL | re.IGNORECASE
        )
        if summary_match:
            summary = summary_match.group(1).strip()

        # Extract [FACTS]...[/FACTS]
        facts_match = re.search(
            r"\[FACTS\](.*?)\[/FACTS\]", response, re.DOTALL | re.IGNORECASE
        )
        if facts_match:
            facts = facts_match.group(1).strip()
            # Filter out "none" or "empty" responses
            if facts.lower() in ("none", "n/a", "-", ""):
                facts = ""

        return summary, facts

    def strip_distillation_markers(self, response: str) -> str:
        """
        Remove distillation markers from response before showing to user.

        Args:
            response: Full LLM response with markers

        Returns:
            Clean response without [SUMMARY] and [FACTS] sections
        """
        # Remove [SUMMARY]...[/SUMMARY] block
        clean = re.sub(
            r"\[SUMMARY\].*?\[/SUMMARY\]\s*",
            "",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove [FACTS]...[/FACTS] block
        clean = re.sub(
            r"\[FACTS\].*?\[/FACTS\]\s*", "", clean, flags=re.DOTALL | re.IGNORECASE
        )

        return clean.strip()

    def is_enabled(self) -> bool:
        """Check if memory service is enabled (folder exists and writable)."""
        return self.memory_folder.exists() and os.access(self.memory_folder, os.W_OK)

    def get_stats(self) -> dict:
        """Get memory statistics."""
        daily_logs = list(self.daily_folder.glob("*.md"))
        memory_exists = self.memory_md.exists()
        memory_size = self.memory_md.stat().st_size if memory_exists else 0

        return {
            "enabled": self.is_enabled(),
            "daily_log_count": len(daily_logs),
            "memory_md_exists": memory_exists,
            "memory_md_size_bytes": memory_size,
            "memory_folder": str(self.memory_folder),
        }
