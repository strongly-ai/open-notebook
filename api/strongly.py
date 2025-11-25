"""
Strongly.AI Platform Integration

This module provides integration with the Strongly.AI platform:
- Service discovery from STRONGLY_SERVICES environment variable
- AI Gateway configuration for LLM access
- User authentication from platform headers
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


@dataclass
class StronglyUser:
    """User information from Strongly.AI headers."""
    user_id: str
    email: str
    name: str
    app_role: str
    platform_role: str
    authenticated: bool


@dataclass
class AIGatewayConfig:
    """AI Gateway configuration from STRONGLY_SERVICES."""
    base_url: str
    api_key: Optional[str] = None


class StronglyServices:
    """
    Parse and manage Strongly.AI platform services.

    The STRONGLY_SERVICES environment variable contains JSON with service
    configuration including AI Gateway, databases, and other platform services.
    """

    _instance: Optional["StronglyServices"] = None
    _services: Dict[str, Any] = {}
    _ai_gateway: Optional[AIGatewayConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_services()
        return cls._instance

    def _load_services(self):
        """Load and parse STRONGLY_SERVICES environment variable."""
        services_json = os.environ.get("STRONGLY_SERVICES", "")

        if not services_json:
            logger.warning("STRONGLY_SERVICES environment variable not set")
            self._services = {}
            return

        try:
            self._services = json.loads(services_json)
            logger.info("Loaded STRONGLY_SERVICES configuration")
            self._parse_ai_gateway()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse STRONGLY_SERVICES: {e}")
            self._services = {}

    def _parse_ai_gateway(self):
        """Extract AI Gateway configuration from services."""
        try:
            services = self._services.get("services", {})
            ai_gateway = services.get("ai_gateway", {})

            if ai_gateway:
                base_url = ai_gateway.get("base_url", "")
                api_key = ai_gateway.get("api_key")

                if base_url:
                    self._ai_gateway = AIGatewayConfig(
                        base_url=base_url.rstrip("/"),
                        api_key=api_key
                    )
                    logger.info(f"AI Gateway configured: {base_url}")
                else:
                    logger.warning("AI Gateway base_url not found in STRONGLY_SERVICES")
            else:
                logger.warning("ai_gateway not found in STRONGLY_SERVICES")
        except Exception as e:
            logger.error(f"Error parsing AI Gateway config: {e}")

    @property
    def ai_gateway(self) -> Optional[AIGatewayConfig]:
        """Get AI Gateway configuration."""
        return self._ai_gateway

    @property
    def is_configured(self) -> bool:
        """Check if Strongly services are properly configured."""
        return self._ai_gateway is not None

    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific service configuration."""
        return self._services.get("services", {}).get(service_name)

    def get_database(self, db_type: str, index: int = 0) -> Optional[Dict[str, Any]]:
        """Get database configuration by type (e.g., 'mongodb', 'postgresql')."""
        databases = self._services.get("services", {}).get("databases", {})
        db_list = databases.get(db_type, [])
        if db_list and len(db_list) > index:
            return db_list[index]
        return None


def get_strongly_services() -> StronglyServices:
    """Get the Strongly services singleton instance."""
    return StronglyServices()


def get_user_from_headers(headers: Dict[str, str]) -> Optional[StronglyUser]:
    """
    Extract user information from Strongly.AI platform headers.

    Headers expected:
    - X-Auth-User-Id: Unique user identifier
    - X-Auth-User-Email: User email address
    - X-Auth-User-Name: Display name
    - X-Auth-App-Role: Application-specific role
    - X-Auth-Platform-Role: Platform-wide role
    - X-Auth-Authenticated: Whether user is authenticated
    """
    user_id = headers.get("x-auth-user-id", "").strip()
    email = headers.get("x-auth-user-email", "").strip()

    if not user_id or not email:
        return None

    return StronglyUser(
        user_id=user_id,
        email=email,
        name=headers.get("x-auth-user-name", email.split("@")[0]).strip(),
        app_role=headers.get("x-auth-app-role", "user").strip(),
        platform_role=headers.get("x-auth-platform-role", "user").strip(),
        authenticated=headers.get("x-auth-authenticated", "false").lower() == "true"
    )


async def fetch_available_models() -> List[Dict[str, Any]]:
    """
    Fetch available models from Strongly AI Gateway.

    Returns a list of model configurations that can be used with Open Notebook.
    """
    services = get_strongly_services()

    if not services.ai_gateway:
        logger.warning("AI Gateway not configured, cannot fetch models")
        return []

    try:
        async with httpx.AsyncClient() as client:
            headers = {}
            if services.ai_gateway.api_key:
                headers["Authorization"] = f"Bearer {services.ai_gateway.api_key}"

            response = await client.get(
                f"{services.ai_gateway.base_url}/v1/models",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

            data = response.json()
            models = data.get("data", [])

            logger.info(f"Fetched {len(models)} models from AI Gateway")
            return models

    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch models from AI Gateway: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return []


def configure_environment():
    """
    Configure environment variables for Strongly.AI integration.

    This sets up the OpenAI-compatible endpoint to point to the AI Gateway,
    allowing Open Notebook to use Strongly's model proxy.
    """
    services = get_strongly_services()

    if not services.ai_gateway:
        logger.warning("AI Gateway not configured, skipping environment setup")
        return

    # Set OpenAI-compatible base URL to AI Gateway
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = f"{services.ai_gateway.base_url}/v1"

    if services.ai_gateway.api_key:
        os.environ["OPENAI_COMPATIBLE_API_KEY"] = services.ai_gateway.api_key

    logger.info("Configured OpenAI-compatible endpoint for Strongly AI Gateway")
