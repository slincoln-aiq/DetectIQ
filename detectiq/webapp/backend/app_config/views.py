from typing import Type, cast

import keyring
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from pydantic import SecretStr
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from detectiq.core.config import config_manager
from detectiq.core.integrations import get_integration
from detectiq.core.integrations.base import BaseSIEMIntegration
from detectiq.core.integrations.splunk import SplunkCredentials
from detectiq.core.utils.logging import get_logger
from detectiq.webapp.backend.utils.decorators import async_action

logger = get_logger(__name__)


# Create your views here.
@method_decorator(csrf_exempt, name="dispatch")
class AppConfigViewSet(viewsets.ViewSet):
    """ViewSet for managing DetectIQ config/settings"""

    authentication_classes = []
    permission_classes = [AllowAny]
    basename = "app_config"

    @action(detail=False, methods=["GET"], url_path="get-config")
    def get_config(self, request):
        """Get DetectIQ config."""
        try:
            current_config = config_manager.config
            # Convert Pydantic model to dict and structure response
            response_data = {
                "openai_api_key": getattr(current_config, "openai_api_key", ""),
                "rule_directories": {
                    "sigma": getattr(current_config.rule_directories, "sigma", ""),
                    "yara": getattr(current_config.rule_directories, "yara", ""),
                    "snort": getattr(current_config.rule_directories, "snort", ""),
                },
                "integrations": {
                    "splunk": (
                        current_config.integrations.splunk.model_dump()
                        if current_config.integrations and current_config.integrations.splunk
                        else {}
                    ),
                    "elastic": (
                        current_config.integrations.elastic.model_dump()
                        if current_config.integrations and current_config.integrations.elastic
                        else {}
                    ),
                    "microsoft_xdr": (
                        current_config.integrations.microsoft_xdr.model_dump()
                        if current_config.integrations and current_config.integrations.microsoft_xdr
                        else {}
                    ),
                },
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error getting config: {str(e)}")
            return Response({"error": f"Failed to get config: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @async_action(
        detail=False, methods=["POST"], url_path="update-config"
    )  # TODO: Change to update-config where we used update-settings
    async def update_config(self, request):
        try:
            config_data = request.data

            # If updating integrations, ensure proper structure
            if "integrations" in config_data:
                integrations_data = config_data["integrations"]
                if "splunk" in integrations_data:
                    # Convert to proper credential model
                    splunk_data = integrations_data["splunk"]
                    splunk_creds = SplunkCredentials(
                        hostname=splunk_data.get("hostname", ""),
                        username=splunk_data.get("username", ""),
                        password=SecretStr(splunk_data.get("password", "")),  # Convert to SecretStr
                        app=splunk_data.get("app"),
                        owner=splunk_data.get("owner"),
                        verify_ssl=splunk_data.get("verify_ssl", True),
                        enabled=splunk_data.get("enabled", False),
                    )
                    integrations_data["splunk"] = splunk_creds

            # Update config
            config_manager.update_config(**config_data)
            return Response({"status": "success"})

        except Exception as e:
            logger.error(f"Error updating config: {str(e)}")
            return Response(
                {"error": f"Failed to update config: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @async_action(detail=False, methods=["POST"], url_path="test_integration")
    async def test_integration(self, request):
        try:
            integration_name = request.data.get("integration")
            if not integration_name:
                return Response({"error": "Integration name is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Get stored config
            integrations_config = getattr(config_manager.config.integrations, integration_name, None)
            if not integrations_config:
                return Response(
                    {"error": f"No credentials found for {integration_name}"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Get integration class
            IntegrationClass = cast(Type[BaseSIEMIntegration], get_integration(integration_name))
            if not IntegrationClass:
                return Response(
                    {"error": f"Unknown integration type: {integration_name}"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Get stored password from keyring for Splunk
            if integration_name == "splunk":
                stored_password = keyring.get_password(config_manager.APP_NAME, f"{integration_name}_password")
                if stored_password:
                    integrations_config.password = SecretStr(stored_password)

            # Initialize integration
            integration = IntegrationClass()
            result = await integration.test_connection()

            return Response(result)

        except ValueError as ve:
            logger.error(f"Integration configuration error: {str(ve)}")
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error testing integration: {str(e)}")
            return Response(
                {"error": f"Failed to test integration: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
