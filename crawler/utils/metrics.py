"""
Prometheus metrics for the Crawler service.
Tracks crawl operations, page processing, and service health.
"""

from prometheus_client import Counter, Gauge, Histogram

# Service health
SERVICE_UP = Gauge(
    "crawler_service_up",
    "Whether the crawler service is up (1) or down (0)",
)

SERVICE_ERRORS = Counter(
    "crawler_service_errors_total",
    "Total number of service-level errors",
    ["error_type"],
)

# Crawl metrics
CRAWL_REQUESTS = Counter(
    "crawler_requests_total",
    "Total number of crawl requests",
    ["source", "status"],  # source: firecrawl, playwright
)

CRAWL_DURATION = Histogram(
    "crawler_request_duration_seconds",
    "Time spent on crawl requests",
    ["source"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

PAGES_PROCESSED = Counter(
    "crawler_pages_processed_total",
    "Total number of pages processed",
    ["source"],
)

BYTES_DOWNLOADED = Counter(
    "crawler_bytes_downloaded_total",
    "Total bytes downloaded during crawling",
    ["source"],
)

# Render metrics (Playwright)
RENDER_REQUESTS = Counter(
    "crawler_render_requests_total",
    "Total number of page render requests",
    ["status"],
)

RENDER_DURATION = Histogram(
    "crawler_render_duration_seconds",
    "Time spent rendering pages with Playwright",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Extract metrics (Trafilatura)
EXTRACT_REQUESTS = Counter(
    "crawler_extract_requests_total",
    "Total number of content extraction requests",
    ["status"],
)

EXTRACT_DURATION = Histogram(
    "crawler_extract_duration_seconds",
    "Time spent extracting content with Trafilatura",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)


def set_service_up(is_up: bool = True):
    """Set service health status."""
    SERVICE_UP.set(1 if is_up else 0)


def record_service_error(error: Exception):
    """Record a service error."""
    SERVICE_ERRORS.labels(error_type=type(error).__name__).inc()


def record_crawl(
    source: str, status: str, duration: float, pages: int = 0, bytes_size: int = 0
):
    """Record crawl metrics."""
    CRAWL_REQUESTS.labels(source=source, status=status).inc()
    CRAWL_DURATION.labels(source=source).observe(duration)
    if pages > 0:
        PAGES_PROCESSED.labels(source=source).inc(pages)
    if bytes_size > 0:
        BYTES_DOWNLOADED.labels(source=source).inc(bytes_size)


def record_render(status: str, duration: float):
    """Record render metrics."""
    RENDER_REQUESTS.labels(status=status).inc()
    RENDER_DURATION.observe(duration)


def record_extract(status: str, duration: float):
    """Record extraction metrics."""
    EXTRACT_REQUESTS.labels(status=status).inc()
    EXTRACT_DURATION.observe(duration)
