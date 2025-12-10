"""
Prometheus metrics for LLMCrawl gateway.

Provides comprehensive metrics for:
- Crawl requests (Playwright vs Firecrawl)
- Tool calls (with parameters like file_path, url, query)
- LLM requests (tokens, duration, provider)
- Service health (up/down, errors, memory)
"""

import functools
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info

# =============================================================================
# CRAWL METRICS
# =============================================================================

CRAWL_REQUESTS_TOTAL = Counter(
    "crawl_requests_total",
    "Total number of crawl requests",
    ["status", "domain", "source"],  # source: playwright, firecrawl
)

CRAWL_DURATION_SECONDS = Histogram(
    "crawl_duration_seconds",
    "Time spent on crawl requests",
    ["domain", "source"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

CRAWL_PAGES_PROCESSED = Counter(
    "crawl_pages_processed_total",
    "Total number of pages processed",
    ["domain", "source"],
)

CRAWL_BYTES_DOWNLOADED = Counter(
    "crawl_bytes_downloaded_total",
    "Total bytes downloaded during crawling",
    ["domain", "source"],
)

# =============================================================================
# TOOL CALL METRICS
# =============================================================================

TOOL_CALLS_TOTAL = Counter(
    "tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "status"],  # status: success, error
)

TOOL_CALL_DURATION_SECONDS = Histogram(
    "tool_call_duration_seconds",
    "Time spent on tool calls",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

TOOL_CALL_ERRORS = Counter(
    "tool_call_errors_total",
    "Total number of tool call errors",
    ["tool_name", "error_type"],  # error_type: timeout, auth, validation, etc.
)

# Info metric for tool call parameters (last call details)
TOOL_CALL_INFO = Info(
    "tool_call_last",
    "Information about the last tool call",
)

# Gauge for tracking active tool calls
TOOL_CALLS_IN_PROGRESS = Gauge(
    "tool_calls_in_progress",
    "Number of tool calls currently in progress",
    ["tool_name"],
)

# =============================================================================
# LLM METRICS
# =============================================================================

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total number of LLM requests",
    ["provider", "model", "status"],  # provider: openai, anthropic, azure
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "Time spent on LLM requests",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total tokens used in LLM requests",
    ["provider", "model", "token_type"],  # token_type: input, output
)

LLM_REQUEST_SIZE_BYTES = Histogram(
    "llm_request_size_bytes",
    "Size of LLM request payloads in bytes",
    ["provider", "model"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
)

LLM_RESPONSE_SIZE_BYTES = Histogram(
    "llm_response_size_bytes",
    "Size of LLM response payloads in bytes",
    ["provider", "model"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
)

LLM_ERRORS_TOTAL = Counter(
    "llm_errors_total",
    "Total number of LLM errors",
    ["provider", "model", "error_type"],
)

# =============================================================================
# SERVICE HEALTH METRICS
# =============================================================================

SERVICE_UP = Gauge(
    "service_up",
    "Whether the service is up (1) or down (0)",
    ["service"],  # gateway, crawler, indexer
)

SERVICE_ERRORS_TOTAL = Counter(
    "service_errors_total",
    "Total number of service errors",
    ["service", "error_type"],
)

SERVICE_REQUEST_DURATION_SECONDS = Histogram(
    "service_request_duration_seconds",
    "Request duration for service endpoints",
    ["service", "endpoint", "method"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# =============================================================================
# AGENT CLIENT REQUEST METRICS
# =============================================================================

AGENT_REQUESTS_TOTAL = Counter(
    "agent_requests_total",
    "Total number of agent client requests",
    ["workflow", "status"],  # workflow: general_chat, code_analysis, etc.
)

AGENT_REQUEST_DURATION_SECONDS = Histogram(
    "agent_request_duration_seconds",
    "Total duration of agent requests",
    ["workflow"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

AGENT_REQUEST_ERRORS = Counter(
    "agent_request_errors_total",
    "Total number of agent request errors",
    ["workflow", "error_type"],  # error_type: timeout, auth, rate_limit, etc.
)

# Info metric for last request details
AGENT_REQUEST_INFO = Info(
    "agent_request_last",
    "Information about the last agent request",
)

# =============================================================================
# AGENT ACTIVITY METRICS
# =============================================================================

AGENT_ACTIVITY_TOTAL = Counter(
    "agent_activity_total",
    "Total number of agent activities",
    [
        "activity",
        "status",
    ],  # activity: prefetch_local, prefetch_azdo, crawl, index, embed
)

AGENT_ACTIVITY_DURATION_SECONDS = Histogram(
    "agent_activity_duration_seconds",
    "Duration of agent activities",
    ["activity"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

AGENT_ACTIVITY_ERRORS = Counter(
    "agent_activity_errors_total",
    "Total number of agent activity errors",
    ["activity", "error_type"],
)

AGENT_ACTIVITY_IN_PROGRESS = Gauge(
    "agent_activity_in_progress",
    "Number of agent activities currently in progress",
    ["activity"],
)

# Track items processed per activity
AGENT_ACTIVITY_ITEMS = Counter(
    "agent_activity_items_total",
    "Total items processed by agent activities",
    ["activity"],  # e.g., files fetched, urls crawled, docs indexed
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_domain_from_url(url: str) -> str:
    """Extract domain from URL for labeling."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or "unknown"
    except Exception:
        return "unknown"


def classify_error(error: Exception) -> str:
    """Classify an error into a category for metrics."""
    error_type = type(error).__name__
    error_str = str(error).lower()

    if "timeout" in error_str or "timed out" in error_str:
        return "timeout"
    elif "auth" in error_str or "401" in error_str or "403" in error_str:
        return "auth"
    elif "rate" in error_str or "429" in error_str:
        return "rate_limit"
    elif "validation" in error_str or "invalid" in error_str:
        return "validation"
    elif "connection" in error_str or "network" in error_str:
        return "connection"
    elif "not found" in error_str or "404" in error_str:
        return "not_found"
    else:
        return error_type


# =============================================================================
# RECORDING FUNCTIONS
# =============================================================================


def record_crawl_request(
    status: str,
    domain: str,
    source: str,
    duration: float,
    pages: int = 1,
    bytes_downloaded: int = 0,
):
    """Record metrics for a crawl request."""
    CRAWL_REQUESTS_TOTAL.labels(status=status, domain=domain, source=source).inc()
    CRAWL_DURATION_SECONDS.labels(domain=domain, source=source).observe(duration)
    CRAWL_PAGES_PROCESSED.labels(domain=domain, source=source).inc(pages)
    if bytes_downloaded > 0:
        CRAWL_BYTES_DOWNLOADED.labels(domain=domain, source=source).inc(
            bytes_downloaded
        )


def record_tool_call(
    tool_name: str,
    status: str,
    duration: float,
    error_type: Optional[str] = None,
    parameters: Optional[dict] = None,
):
    """
    Record metrics for a tool call.

    Args:
        tool_name: Name of the tool (e.g., "read_file", "crawl_url")
        status: "success" or "error"
        duration: Duration in seconds
        error_type: Type of error if status is "error"
        parameters: Dict of parameters for Info metric (file_path, url, query, etc.)
    """
    TOOL_CALLS_TOTAL.labels(tool_name=tool_name, status=status).inc()
    TOOL_CALL_DURATION_SECONDS.labels(tool_name=tool_name).observe(duration)

    if status == "error" and error_type:
        TOOL_CALL_ERRORS.labels(tool_name=tool_name, error_type=error_type).inc()

    # Record last call info (useful for debugging)
    if parameters:
        # Filter to only string values and limit size
        info_params = {
            "tool_name": tool_name,
            "status": status,
        }
        for key, value in parameters.items():
            if value is not None:
                str_value = str(value)[:200]  # Limit parameter length
                info_params[key] = str_value
        TOOL_CALL_INFO.info(info_params)


def record_llm_request(
    provider: str,
    model: str,
    status: str,
    duration: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    prompt_tokens: int = None,  # Alias for input_tokens
    completion_tokens: int = None,  # Alias for output_tokens
    request_size: int = 0,
    response_size: int = 0,
    error_type: Optional[str] = None,
):
    """Record metrics for an LLM request."""
    # Support both naming conventions, handle None values
    actual_input_tokens = input_tokens or prompt_tokens or 0
    actual_output_tokens = output_tokens or completion_tokens or 0
    actual_request_size = request_size or 0
    actual_response_size = response_size or 0

    LLM_REQUESTS_TOTAL.labels(provider=provider, model=model, status=status).inc()
    LLM_REQUEST_DURATION_SECONDS.labels(provider=provider, model=model).observe(
        duration
    )

    if actual_input_tokens > 0:
        LLM_TOKENS_TOTAL.labels(provider=provider, model=model, token_type="input").inc(
            actual_input_tokens
        )
    if actual_output_tokens > 0:
        LLM_TOKENS_TOTAL.labels(
            provider=provider, model=model, token_type="output"
        ).inc(actual_output_tokens)

    if actual_request_size > 0:
        LLM_REQUEST_SIZE_BYTES.labels(provider=provider, model=model).observe(
            actual_request_size
        )
    if actual_response_size > 0:
        LLM_RESPONSE_SIZE_BYTES.labels(provider=provider, model=model).observe(
            actual_response_size
        )

    if status == "error" and error_type:
        LLM_ERRORS_TOTAL.labels(
            provider=provider, model=model, error_type=error_type
        ).inc()


def record_service_error(service: str, error: Exception):
    """Record a service error."""
    error_type = classify_error(error)
    SERVICE_ERRORS_TOTAL.labels(service=service, error_type=error_type).inc()


def set_service_up(service: str, is_up: bool = True):
    """Set service health status."""
    SERVICE_UP.labels(service=service).set(1 if is_up else 0)


# =============================================================================
# AGENT RECORDING FUNCTIONS
# =============================================================================


def record_agent_request(
    workflow: str,
    status: str,
    duration: float,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    conversation_id: Optional[str] = None,
):
    """
    Record metrics for an agent client request.

    Args:
        workflow: Workflow name (general_chat, code_analysis, etc.)
        status: "success" or "error"
        duration: Duration in seconds
        error_type: Type of error if status is "error"
        error_message: Error message if status is "error"
        conversation_id: Conversation ID for tracking
    """
    AGENT_REQUESTS_TOTAL.labels(workflow=workflow, status=status).inc()
    AGENT_REQUEST_DURATION_SECONDS.labels(workflow=workflow).observe(duration)

    if status == "error" and error_type:
        AGENT_REQUEST_ERRORS.labels(workflow=workflow, error_type=error_type).inc()

    # Record last request info
    info_params = {
        "workflow": workflow,
        "status": status,
    }
    if conversation_id:
        info_params["conversation_id"] = conversation_id
    if error_message:
        info_params["error_message"] = str(error_message)[:200]
    AGENT_REQUEST_INFO.info(info_params)


def record_agent_activity(
    activity: str,
    status: str,
    duration: float,
    items: int = 0,
    error_type: Optional[str] = None,
):
    """
    Record metrics for an agent activity (prefetch, crawl, index, embed).

    Args:
        activity: Activity name:
            - "prefetch_local": Fetching local reference files
            - "prefetch_azdo": Fetching Azure DevOps target files
            - "expand_paths": Expanding path patterns to file lists
            - "crawl": Crawling seed URLs
            - "index": Indexing crawled documents
            - "embed": Embedding documents (if separate from index)
            - "llm_loop": LLM tool calling loop
        status: "success" or "error"
        duration: Duration in seconds
        items: Number of items processed (files, urls, docs)
        error_type: Type of error if status is "error"
    """
    AGENT_ACTIVITY_TOTAL.labels(activity=activity, status=status).inc()
    AGENT_ACTIVITY_DURATION_SECONDS.labels(activity=activity).observe(duration)

    # Handle None values for items
    actual_items = items or 0
    if actual_items > 0:
        AGENT_ACTIVITY_ITEMS.labels(activity=activity).inc(actual_items)

    if status == "error" and error_type:
        AGENT_ACTIVITY_ERRORS.labels(activity=activity, error_type=error_type).inc()


class AgentActivityTimer:
    """
    Context manager for timing and recording agent activities.

    Usage:
        async with AgentActivityTimer("prefetch_local") as timer:
            files = await fetch_files(...)
            timer.items = len(files)
    """

    def __init__(self, activity: str):
        self.activity = activity
        self.start_time: Optional[float] = None
        self.duration: float = 0.0
        self.status: str = "success"
        self.error_type: Optional[str] = None
        self.items: int = 0

    def __enter__(self):
        self.start_time = time.time()
        AGENT_ACTIVITY_IN_PROGRESS.labels(activity=self.activity).inc()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            self.duration = time.time() - self.start_time
        AGENT_ACTIVITY_IN_PROGRESS.labels(activity=self.activity).dec()

        if exc_type is not None:
            self.status = "error"
            self.error_type = classify_error(exc_val) if exc_val else "unknown"

        record_agent_activity(
            activity=self.activity,
            status=self.status,
            duration=self.duration,
            items=self.items,
            error_type=self.error_type,
        )

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


# =============================================================================
# DECORATORS
# =============================================================================


class MetricsTimer:
    """Context manager for timing operations."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.duration: float = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            self.duration = time.time() - self.start_time


def track_tool_call(tool_name: str, get_params: Optional[Callable] = None):
    """
    Decorator to track tool call metrics.

    Args:
        tool_name: Name of the tool
        get_params: Optional function to extract parameters from args/kwargs

    Example:
        @track_tool_call("read_file", lambda args, kwargs: {"file_path": kwargs.get("path")})
        async def read_file(path: str):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            TOOL_CALLS_IN_PROGRESS.labels(tool_name=tool_name).inc()
            start_time = time.time()
            status = "success"
            error_type = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = classify_error(e)
                raise
            finally:
                duration = time.time() - start_time
                TOOL_CALLS_IN_PROGRESS.labels(tool_name=tool_name).dec()

                params = None
                if get_params:
                    try:
                        params = get_params(args, kwargs)
                    except Exception:
                        pass

                record_tool_call(
                    tool_name=tool_name,
                    status=status,
                    duration=duration,
                    error_type=error_type,
                    parameters=params,
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            TOOL_CALLS_IN_PROGRESS.labels(tool_name=tool_name).inc()
            start_time = time.time()
            status = "success"
            error_type = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = classify_error(e)
                raise
            finally:
                duration = time.time() - start_time
                TOOL_CALLS_IN_PROGRESS.labels(tool_name=tool_name).dec()

                params = None
                if get_params:
                    try:
                        params = get_params(args, kwargs)
                    except Exception:
                        pass

                record_tool_call(
                    tool_name=tool_name,
                    status=status,
                    duration=duration,
                    error_type=error_type,
                    parameters=params,
                )

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_llm_request(provider: str):
    """
    Decorator to track LLM request metrics.

    Example:
        @track_llm_request("openai")
        async def chat_completion(messages, model="gpt-4"):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            model = kwargs.get("model", "unknown")
            start_time = time.time()
            status = "success"
            error_type = None
            input_tokens = 0
            output_tokens = 0

            try:
                result = await func(*args, **kwargs)
                # Try to extract token counts from result
                if hasattr(result, "usage"):
                    input_tokens = getattr(result.usage, "prompt_tokens", 0)
                    output_tokens = getattr(result.usage, "completion_tokens", 0)
                return result
            except Exception as e:
                status = "error"
                error_type = classify_error(e)
                raise
            finally:
                duration = time.time() - start_time
                record_llm_request(
                    provider=provider,
                    model=model,
                    status=status,
                    duration=duration,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    error_type=error_type,
                )

        return wrapper

    return decorator
