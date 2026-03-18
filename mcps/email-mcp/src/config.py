"""
Configuration management for EmailMcp MCP Server.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    mcp_server_host: str = Field(default="0.0.0.0", description="Server host address")
    mcp_server_port: int = Field(default=8000, description="Server port")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string",
    )

    # Authentication (Optional)
    mcp_auth_enabled: bool = Field(default=False, description="Enable authentication")
    mcp_auth_debug: bool = Field(default=True, description="Auth debug mode")
    auth_resource_server_url: Optional[str] = Field(
        default=None, description="OAuth2 resource server URL"
    )
    auth_client_id: Optional[str] = Field(default=None, description="OAuth2 client ID")
    auth_audience: Optional[str] = Field(default=None, description="OAuth2 audience")

    # Telemetry (Optional)
    otel_enabled: bool = Field(default=False, description="Enable OpenTelemetry")
    otel_service_name: str = Field(
        default="email-mcp", description="Service name for telemetry"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318", description="OTLP endpoint"
    )

    # Azure Communication Services (Email)
    azure_communication_connection_string: Optional[str] = Field(
        default=None, description="Azure Communication Services connection string"
    )
    azure_email_domain: Optional[str] = Field(
        default=None,
        description="Azure email domain for sender address (e.g., example.azurecomm.net)",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
