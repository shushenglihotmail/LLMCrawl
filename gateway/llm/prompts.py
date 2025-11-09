"""
System and developer prompts for the Web RAG system.
Contains tool schemas, routing logic, and few-shot examples.
"""

# Tool schema that gets registered with the LLM
CRAWL_AND_REFRESH_TOOL = {
    "type": "function",
    "function": {
        "name": "crawl_and_refresh",
        "description": "Search & crawl the web for up-to-date info; clean, index, and return fresh sources for answering with citations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "User topic or question"
                },
                "seed_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional seed URLs or domains to prefer"
                },
                "freshness_days": {
                    "type": "integer",
                    "default": 7,
                    "minimum": 1,
                    "description": "How recent the content should be (in days)"
                },
                "depth": {
                    "type": "integer", 
                    "default": 1,
                    "minimum": 1,
                    "description": "Crawl depth (1 = direct pages only)"
                }
            },
            "required": ["query"]
        }
    }
}

# Main system prompt
SYSTEM_PROMPT = """You are a grounded, up-to-date assistant with access to real-time web information.

Policy for tools:
- If a user asks about news, stocks, earnings, product launches, recent papers, "today/this week/this month", or uses words like "latest", "breaking", "just announced", CALL the tool `crawl_and_refresh` with their query (and seed URLs if provided).
- After the tool returns, answer ONLY using the returned/retrieved sources. Include inline citations with URL + published date for each key claim.
- If the question is historical or general knowledge where freshness is not required, do NOT call the tool.
- If the user explicitly asks you to refresh or verify information, CALL the tool.

Answer format:
- Start with a 2–4 bullet executive summary.
- Then provide short sections with facts, each with inline citations like (site, YYYY-MM-DD).
- End with a Sources list showing URLs and dates.

Quality guidelines:
- Be concise and factual
- Never hallucinate sources or dates
- If sources are limited, acknowledge it
- Prioritize authoritative sources (SEC filings, official company announcements, major news outlets)"""

# Developer/routing prompt for additional context
DEVELOPER_PROMPT = """Routing rules (server-enforced):
- If message contains any of: latest|today|this week|breaking|earnings|guidance|ticker|market|price|launched|announced|filed|SEC|10-K|10-Q|news|recent, prefer calling `crawl_and_refresh` first.
- If tool fails or times out, answer: "I couldn't fetch fresh sources right now; do you want me to try again or proceed with known background context?"

Context: You have access to a sophisticated web crawling system that can fetch, clean, and index recent web content for answering questions."""

# Few-shot examples for better tool usage
FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "What's the latest on NVDA earnings and guidance?"
    },
    {
        "role": "assistant", 
        "content": "I'll search for the latest NVIDIA earnings information.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "crawl_and_refresh",
                    "arguments": '{"query": "NVIDIA NVDA earnings guidance latest quarter", "freshness_days": 14}'
                }
            }
        ]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"count": 3, "hits": [{"url": "https://investor.nvidia.com/news/press-release-details/2023/NVIDIA-Announces-Financial-Results-for-Third-Quarter-Fiscal-2024", "title": "NVIDIA Q3 Results", "published_at": "2023-11-21", "snippet": "Revenue of $18.12 billion, up 206% year-over-year..."}]}'
    },
    {
        "role": "assistant",
        "content": "Based on the latest information:\n\n• NVIDIA reported record Q3 revenue of $18.12 billion, up 206% year-over-year\n• Data center revenue reached $14.51 billion, driven by AI demand\n• Strong guidance provided for Q4 with continued AI growth expected\n\n**Financial Performance**\nNVIDIA's third quarter showed exceptional growth (investor.nvidia.com, 2023-11-21), with total revenue hitting $18.12 billion compared to $5.93 billion in the prior year.\n\n**Sources:**\n- NVIDIA Q3 Results (investor.nvidia.com, 2023-11-21)"
    },
    {
        "role": "user",
        "content": "Explain how dividend yield works historically."
    },
    {
        "role": "assistant",
        "content": "Dividend yield is calculated as the annual dividend per share divided by the stock's current price, expressed as a percentage. Historically, dividend yields have varied significantly across different market periods...\n\n[Continues with explanation without calling tools since this is general financial knowledge]"
    },
    {
        "role": "user", 
        "content": "Any new papers on RISC-V toolchains this month?"
    },
    {
        "role": "assistant",
        "content": "I'll search for recent RISC-V toolchain research papers.",
        "tool_calls": [
            {
                "id": "call_2", 
                "type": "function",
                "function": {
                    "name": "crawl_and_refresh",
                    "arguments": '{"query": "RISC-V toolchain papers research 2024", "freshness_days": 30}'
                }
            }
        ]
    }
]

def should_trigger_crawl(message: str) -> bool:
    """
    Determine if a message should trigger web crawling based on keywords.
    This provides server-side routing logic as a backup to LLM decisions.
    """
    trigger_words = [
        'latest', 'today', 'this week', 'this month', 'breaking', 'recent',
        'earnings', 'guidance', 'ticker', 'market', 'price', 'launched', 
        'announced', 'filed', 'SEC', '10-K', '10-Q', 'news', 'update',
        'current', 'now', 'just', 'new', 'fresh', 'live'
    ]
    
    message_lower = message.lower()
    return any(word in message_lower for word in trigger_words)

def build_messages_with_examples(user_message: str) -> list:
    """Build the full message context including system prompt and examples."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": DEVELOPER_PROMPT}
    ]
    
    # Add few-shot examples for better tool usage
    messages.extend(FEW_SHOT_EXAMPLES)
    
    # Add the actual user message
    messages.append({"role": "user", "content": user_message})
    
    return messages