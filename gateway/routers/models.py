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

    All models in LLM_MODELS configuration are available.
    Does not expose sensitive information (API keys, endpoints).

    Response:
    [
        {
            "name": "gpt-5-chat",
            "display_name": "GPT-5 Chat"
        }
    ]
    """
    return get_available_models()
