"""
Models endpoint - expose available LLM models to clients.

This endpoint provides information about available models without exposing
sensitive information like API keys.
"""

import json
import logging
import os
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from gateway.utils.claude_bridge_manager import get_claude_bridge_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


class ModelInfo(BaseModel):
    """Public model information (no secrets)."""

    name: str
    display_name: str


def get_available_models() -> List[ModelInfo]:
    """
    Get list of available models from environment configuration.

    All models in LLM_MODELS are available (no filtering needed).
    """
    models_json = os.getenv("LLM_MODELS", "[]")

    try:
        models_config = json.loads(models_json)

        # Convert to ModelInfo (all models are available)
        available_models = []
        for model in models_config:
            available_models.append(
                ModelInfo(
                    name=model["name"],
                    display_name=model.get("display_name", model["name"]),
                )
            )

        if not available_models:
            logger.warning("No models configured in LLM_MODELS")

        return available_models

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM_MODELS: {e}")
        return []


@router.get("/available", response_model=List[ModelInfo])
async def list_available_models():
    """
    Get list of available LLM models.

    Combines models from LLM_MODELS configuration and Claude models
    cached at startup from the Claude Bridge (if it was running).
    Does not expose sensitive information (API keys, endpoints).
    """
    models = get_available_models()

    # Append Claude models cached at startup
    bridge_mgr = get_claude_bridge_manager()
    if bridge_mgr.available:
        existing_names = {m.name for m in models}
        for cm in bridge_mgr.cached_models:
            if cm["name"] not in existing_names:
                models.append(
                    ModelInfo(
                        name=cm["name"],
                        display_name=cm["display_name"],
                    )
                )

    return models
