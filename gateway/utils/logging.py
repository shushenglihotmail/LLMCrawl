"""
Logging configuration and utilities for the gateway service.
"""

import os
import sys
import logging
import json
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in log_entry and not key.startswith('_'):
                log_entry[key] = value
                
        return json.dumps(log_entry, default=str)

def setup_logging():
    """Configure logging for the gateway service."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(name)

def log_request(logger: logging.Logger, request_id: str, method: str, path: str, **kwargs):
    """Log an HTTP request with structured data."""
    logger.info(
        f"HTTP {method} {path}",
        extra={
            "request_id": request_id,
            "method": method,
            "path": path,
            **kwargs
        }
    )

def log_response(logger: logging.Logger, request_id: str, status_code: int, duration_ms: float, **kwargs):
    """Log an HTTP response with structured data."""
    logger.info(
        f"HTTP Response {status_code}",
        extra={
            "request_id": request_id,
            "status_code": status_code,
            "duration_ms": duration_ms,
            **kwargs
        }
    )

def log_tool_call(logger: logging.Logger, request_id: str, tool_name: str, arguments: Dict[str, Any]):
    """Log a tool function call."""
    logger.info(
        f"Tool call: {tool_name}",
        extra={
            "request_id": request_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "event_type": "tool_call"
        }
    )

def log_tool_result(logger: logging.Logger, request_id: str, tool_name: str, success: bool, duration_ms: float, result_size: int = 0):
    """Log a tool function result."""
    logger.info(
        f"Tool result: {tool_name} ({'success' if success else 'failure'})",
        extra={
            "request_id": request_id,
            "tool_name": tool_name,
            "success": success,
            "duration_ms": duration_ms,
            "result_size": result_size,
            "event_type": "tool_result"
        }
    )