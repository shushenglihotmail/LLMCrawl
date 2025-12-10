"""
Prometheus metrics for the Indexer service.
Tracks indexing operations, retrieval, and service health.
"""

from prometheus_client import Counter, Histogram, Gauge

# Service health
SERVICE_UP = Gauge(
    "indexer_service_up",
    "Whether the indexer service is up (1) or down (0)",
)

SERVICE_ERRORS = Counter(
    "indexer_service_errors_total",
    "Total number of service-level errors",
    ["error_type"],
)

# Index metrics
INDEX_REQUESTS = Counter(
    "indexer_index_requests_total",
    "Total number of index requests",
    ["status"],
)

INDEX_DURATION = Histogram(
    "indexer_index_duration_seconds",
    "Time spent on indexing requests",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

DOCUMENTS_INDEXED = Counter(
    "indexer_documents_indexed_total",
    "Total number of documents indexed",
)

CHUNKS_CREATED = Counter(
    "indexer_chunks_created_total",
    "Total number of chunks created during indexing",
)

# Retrieve metrics
RETRIEVE_REQUESTS = Counter(
    "indexer_retrieve_requests_total",
    "Total number of retrieve requests",
    ["status"],
)

RETRIEVE_DURATION = Histogram(
    "indexer_retrieve_duration_seconds",
    "Time spent on retrieval requests",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

RETRIEVE_RESULTS = Histogram(
    "indexer_retrieve_results_count",
    "Number of results returned per retrieval",
    buckets=[0, 1, 2, 5, 10, 20, 50],
)


def set_service_up(is_up: bool = True):
    """Set service health status."""
    SERVICE_UP.set(1 if is_up else 0)


def record_service_error(error: Exception):
    """Record a service error."""
    SERVICE_ERRORS.labels(error_type=type(error).__name__).inc()


def record_index(status: str, duration: float, documents: int = 0, chunks: int = 0):
    """Record indexing metrics."""
    INDEX_REQUESTS.labels(status=status).inc()
    INDEX_DURATION.observe(duration)
    if documents > 0:
        DOCUMENTS_INDEXED.inc(documents)
    if chunks > 0:
        CHUNKS_CREATED.inc(chunks)


def record_retrieve(status: str, duration: float, results: int = 0):
    """Record retrieval metrics."""
    RETRIEVE_REQUESTS.labels(status=status).inc()
    RETRIEVE_DURATION.observe(duration)
    RETRIEVE_RESULTS.observe(results)
