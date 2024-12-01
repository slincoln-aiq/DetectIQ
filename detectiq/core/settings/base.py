import json
import os
from pathlib import Path
from typing import Optional

import keyring
from django.contrib.auth.models import User
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

from detectiq.core.utils.logging import get_logger
from detectiq.globals import DEFAULT_DIRS

logger = get_logger(__name__)


class IntegrationCredentials(BaseModel):
    """Base integration credentials model."""

    hostname: str = Field(default="")
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_id: Optional[str] = None
    cloud_id: Optional[str] = None
    app: Optional[str] = None
    owner: Optional[str] = None
    verify_ssl: bool = True
    enabled: bool = False

    class Config:
        extra = "allow"  # Allow extra fields


class SplunkCredentials(IntegrationCredentials):
    """Splunk-specific credentials."""

    username: Optional[str] = None
    password: Optional[SecretStr] = None
    app: Optional[str] = None
    owner: Optional[str] = None


class ElasticCredentials(IntegrationCredentials):
    """Elastic-specific credentials."""

    cloud_id: Optional[str] = None
    api_key: Optional[str] = None


class MicrosoftXDRCredentials(IntegrationCredentials):
    """Microsoft XDR-specific credentials."""

    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class Integrations(BaseModel):
    """Container for all integration settings."""

    elastic: ElasticCredentials = Field(default_factory=ElasticCredentials)
    splunk: SplunkCredentials = Field(default_factory=SplunkCredentials)
    microsoft_xdr: MicrosoftXDRCredentials = Field(default_factory=MicrosoftXDRCredentials)

    class Config:
        extra = "allow"


class DetectIQSettings(BaseModel):
    """Main settings model."""

    openai_api_key: str = Field(default="")
    rule_directories: dict = Field(
        default_factory=lambda: {
            "sigma": str(DEFAULT_DIRS.SIGMA_RULE_DIR),
            "yara": str(DEFAULT_DIRS.YARA_RULE_DIR),
            "snort": str(DEFAULT_DIRS.SNORT_RULE_DIR),
        }
    )
    vector_store_directories: dict = Field(
        default_factory=lambda: {
            "sigma": str(DEFAULT_DIRS.SIGMA_VECTOR_STORE_DIR),
            "yara": str(DEFAULT_DIRS.YARA_VECTOR_STORE_DIR),
            "snort": str(DEFAULT_DIRS.SNORT_VECTOR_STORE_DIR),
        }
    )
    log_level: str = Field(default="INFO")
    model: str = Field(default="gpt-4o")
    integrations: Integrations = Field(default_factory=Integrations)

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"


class SettingsManager:
    APP_NAME = "detectiq"
    # Get project root directory
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    SETTINGS_FILE = PROJECT_ROOT / "settings.json"

    # Define sensitive fields that should be stored in keyring
    SENSITIVE_FIELDS = {
        "splunk": ["password"],
        "elastic": ["api_key"],
        "microsoft_xdr": ["client_secret"],
        "global": ["openai_api_key"],
    }

    def __init__(self):
        load_dotenv()
        logger.debug(f"Initializing SettingsManager. Settings file: {self.SETTINGS_FILE}")

        # Create settings file if it doesn't exist
        if not self.SETTINGS_FILE.exists():
            logger.debug("Settings file does not exist. Creating with defaults...")
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.settings = self._load_settings()
            self.save_settings()
        else:
            logger.debug("Loading existing settings file...")
            self.settings = self._load_settings()

    def _load_settings(self) -> DetectIQSettings:
        # First load from env vars and set defaults
        settings_dict = {
            "openai_api_key": keyring.get_password(self.APP_NAME, "openai_api_key") or os.getenv("OPENAI_API_KEY", ""),
            "rule_directories": {
                "sigma": str(self.PROJECT_ROOT / "rules" / "sigma"),
                "yara": str(self.PROJECT_ROOT / "rules" / "yara"),
                "snort": str(self.PROJECT_ROOT / "rules" / "snort"),
            },
            "vector_store_directories": {
                "sigma": str(self.PROJECT_ROOT / "vector_stores" / "sigma"),
                "yara": str(self.PROJECT_ROOT / "vector_stores" / "yara"),
                "snort": str(self.PROJECT_ROOT / "vector_stores" / "snort"),
            },
            "log_level": os.getenv("DETECTIQ_LOG_LEVEL", "INFO"),
            "model": os.getenv("DETECTIQ_MODEL", "gpt-4"),
            "integrations": {
                "splunk": SplunkCredentials().dict(),
                "elastic": ElasticCredentials().dict(),
                "microsoft_xdr": MicrosoftXDRCredentials().dict(),
            },
        }

        # Load saved settings file if it exists
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE) as f:
                    file_settings = json.load(f)
                    logger.debug(f"Loaded settings from file: {file_settings}")

                    # Update settings with saved values
                    settings_dict.update(file_settings)

                    # Load sensitive integration settings from keyring
                    for integration_name, config in settings_dict["integrations"].items():
                        if integration_name in self.SENSITIVE_FIELDS:
                            for field in self.SENSITIVE_FIELDS[integration_name]:
                                stored_value = keyring.get_password(self.APP_NAME, f"{integration_name}_{field}")
                                if stored_value:
                                    config[field] = stored_value
            except Exception as e:
                logger.error(f"Error loading settings file: {e}")
                # Continue with defaults if file is corrupted

        logger.debug(f"Final settings dict: {settings_dict}")
        return DetectIQSettings(**settings_dict)

    def save_settings(self):
        """Save settings to file and keyring."""
        # Convert settings to dict
        settings_dict = self.settings.dict(exclude_none=True)
        file_settings = settings_dict.copy()  # Create a copy for file storage

        # Handle OpenAI API key
        if settings_dict.get("openai_api_key"):
            keyring.set_password(self.APP_NAME, "openai_api_key", settings_dict["openai_api_key"])
            file_settings["openai_api_key"] = ""

        # Handle integration credentials
        if "integrations" in settings_dict:
            for integration_name, config in settings_dict["integrations"].items():
                if isinstance(config, BaseModel):
                    config = config.dict()

                # Store sensitive fields in keyring
                if integration_name in self.SENSITIVE_FIELDS:
                    for field in self.SENSITIVE_FIELDS[integration_name]:
                        if config.get(field):
                            value = config[field]
                            if isinstance(value, SecretStr):
                                value = value.get_secret_value()
                            keyring.set_password(self.APP_NAME, f"{integration_name}_{field}", value)
                            # Remove sensitive data from file storage but keep in memory
                            file_settings["integrations"][integration_name][field] = ""

        # Save non-sensitive settings to file
        with open(self.SETTINGS_FILE, "w") as f:
            json.dump(file_settings, f, indent=2, default=str)

    def update_settings(self, **kwargs):
        """Update settings with proper type conversion."""
        settings_dict = self.settings.dict()

        for key, value in kwargs.items():
            if key == "integrations":
                integrations_data = {}
                for integration_name, integration_config in value.items():
                    # Convert any model instances to dicts first
                    if isinstance(integration_config, BaseModel):
                        integration_config = integration_config.dict()

                    # Create new instances from the dict data
                    if integration_name == "splunk":
                        integrations_data["splunk"] = SplunkCredentials(**integration_config)
                    elif integration_name == "elastic":
                        integrations_data["elastic"] = ElasticCredentials(**integration_config)
                    elif integration_name == "microsoft_xdr":
                        integrations_data["microsoft_xdr"] = MicrosoftXDRCredentials(**integration_config)

                # Create new Integrations instance with the processed data
                settings_dict["integrations"] = Integrations(**integrations_data)
            else:
                settings_dict[key] = value

        # Update settings with new values
        self.settings = DetectIQSettings(**settings_dict)
        self.save_settings()


async def get_settings(user: Optional[User] = None) -> SettingsManager:
    return SettingsManager()
