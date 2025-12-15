"""Embedded crawler service module - can run the crawler natively without Docker."""

from .runner import run_crawler_service

__all__ = ["run_crawler_service"]
