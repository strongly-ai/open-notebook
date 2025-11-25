"""
Strongly.AI integration routes.

Provides endpoints for:
- Fetching available models from AI Gateway
- Syncing models to Open Notebook's database
- Checking Strongly.AI integration status
"""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.strongly import fetch_available_models, get_strongly_services
from open_notebook.database.repository import repo_query
from open_notebook.domain.models import Model

router = APIRouter()


class StronglyStatus(BaseModel):
    """Strongly.AI integration status."""
    enabled: bool
    ai_gateway_configured: bool
    ai_gateway_url: Optional[str] = None


class AIGatewayModel(BaseModel):
    """Model from AI Gateway."""
    id: str
    object: str = "model"
    owned_by: Optional[str] = None


class SyncResult(BaseModel):
    """Result of model sync operation."""
    synced: int
    skipped: int
    errors: int
    models: List[str]


@router.get("/strongly/status", response_model=StronglyStatus)
async def get_strongly_status():
    """
    Get Strongly.AI integration status.

    Returns whether Strongly mode is enabled and if AI Gateway is configured.
    """
    strongly_mode = os.environ.get("STRONGLY_MODE", "false").lower() == "true"
    services = get_strongly_services()

    return StronglyStatus(
        enabled=strongly_mode,
        ai_gateway_configured=services.is_configured,
        ai_gateway_url=services.ai_gateway.base_url if services.ai_gateway else None
    )


@router.get("/strongly/models", response_model=List[AIGatewayModel])
async def get_gateway_models():
    """
    Fetch available models from Strongly AI Gateway.

    Returns a list of models that can be used with Open Notebook.
    """
    services = get_strongly_services()

    if not services.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Strongly.AI AI Gateway not configured"
        )

    models = await fetch_available_models()

    return [
        AIGatewayModel(
            id=model.get("id", ""),
            object=model.get("object", "model"),
            owned_by=model.get("owned_by")
        )
        for model in models
    ]


@router.post("/strongly/sync-models", response_model=SyncResult)
async def sync_models_from_gateway():
    """
    Sync models from Strongly AI Gateway to Open Notebook's database.

    This creates model entries for each available model in the AI Gateway,
    using the 'openai_compatible' provider which points to the Gateway.
    """
    services = get_strongly_services()

    if not services.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Strongly.AI AI Gateway not configured"
        )

    gateway_models = await fetch_available_models()

    synced = 0
    skipped = 0
    errors = 0
    synced_models = []

    for gw_model in gateway_models:
        model_id = gw_model.get("id", "")
        if not model_id:
            continue

        try:
            # Check if model already exists
            existing = await repo_query(
                "SELECT * FROM model WHERE name = $name AND provider = $provider",
                {"name": model_id, "provider": "openai_compatible"}
            )

            if existing:
                skipped += 1
                continue

            # Determine model type based on ID patterns
            model_type = "language"  # Default to language model
            if "embed" in model_id.lower():
                model_type = "embedding"
            elif "tts" in model_id.lower() or "speech" in model_id.lower():
                model_type = "text_to_speech"
            elif "stt" in model_id.lower() or "whisper" in model_id.lower():
                model_type = "speech_to_text"

            # Create new model entry
            model = Model(
                name=model_id,
                provider="openai_compatible",
                type=model_type
            )
            await model.save()

            synced += 1
            synced_models.append(model_id)
            logger.info(f"Synced model: {model_id} ({model_type})")

        except Exception as e:
            errors += 1
            logger.error(f"Error syncing model {model_id}: {e}")

    return SyncResult(
        synced=synced,
        skipped=skipped,
        errors=errors,
        models=synced_models
    )


@router.delete("/strongly/models")
async def delete_strongly_models():
    """
    Delete all models with the 'openai_compatible' provider.

    Useful for re-syncing models from the AI Gateway.
    """
    try:
        result = await repo_query(
            "DELETE FROM model WHERE provider = $provider",
            {"provider": "openai_compatible"}
        )
        return {"message": "Strongly models deleted", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete models: {str(e)}"
        )
