"""
EmailMcp - MCP Server
An MCP Server based on Azure Emailer
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .config import get_settings

# Authentication import
try:
    from .auth import EntraIDTokenVerifier

    auth_available = True
except ImportError:
    EntraIDTokenVerifier = None
    auth_available = False

try:
    from .services.telemetry_service import setup_telemetry
except ImportError:
    setup_telemetry = None

# Import services
from .services.email_service import EmailService, register_email_tools

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format=settings.log_format,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Initialize Email Service early (before lifespan)
logger.info("Initializing EmailService...")
email_service = EmailService(
    connection_string=settings.azure_communication_connection_string,
    email_domain=settings.azure_email_domain,
)
logger.info("EmailService initialized")


@asynccontextmanager
async def lifespan(mcp: FastMCP):
    """Lifespan context manager for startup and shutdown logic."""
    logger.info(f"Starting EmailMcp MCP Server v0.1.0")

    # Setup telemetry if enabled
    if settings.otel_enabled and setup_telemetry:
        logger.info("Initializing OpenTelemetry...")
        setup_telemetry(settings)

    yield

    logger.info("Shutting down EmailMcp MCP Server")


# Initialize authentication if enabled
auth = None
if settings.mcp_auth_enabled and auth_available:
    logger.info("Initializing Azure AD authentication...")
    auth = EntraIDTokenVerifier()
    logger.info("✓ Authentication enabled for MCP server")
else:
    logger.warning("⚠️  Authentication DISABLED - not recommended for production")

# Initialize FastMCP server with authentication
mcp = FastMCP(
    name="email-mcp",
    instructions="An MCP Server based on Azure Emailer",
    version="0.1.0",
    auth=auth,  # Add authentication
    lifespan=lifespan,
)


# Register all tool services
register_email_tools(mcp, email_service)


# ==========================================
# Health and Readiness Endpoints
# ==========================================


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for monitoring and liveness probes."""
    from datetime import datetime

    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "email-mcp",
            "version": "0.1.0",
        }
    )


@mcp.custom_route("/ready", methods=["GET"])
async def readiness_check(request):
    """Readiness check endpoint - verifies service can handle requests."""
    from datetime import datetime

    from starlette.responses import JSONResponse

    try:
        # Test email service is initialized
        if email_service is None:
            return JSONResponse(
                {"status": "not_ready", "reason": "Email service not initialized"},
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ready",
                "timestamp": datetime.now().isoformat(),
                "service": "email-mcp",
            }
        )
    except Exception as e:
        return JSONResponse({"status": "not_ready", "reason": str(e)}, status_code=503)


@mcp.custom_route("/", methods=["GET"])
async def root(request):
    """Root endpoint with basic service information."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "service": "email-mcp",
            "status": "running",
            "mcp_endpoint": "/mcp",
            "health_endpoint": "/health",
            "ready_endpoint": "/ready",
            "version": "0.1.0",
            "description": "MCP Server for Azure Communication Services Email",
        }
    )


@mcp.resource("config://settings")
def get_server_config() -> str:
    """Get current server configuration (non-sensitive data only)."""
    config_info = {
        "server": {
            "host": settings.mcp_server_host,
            "port": settings.mcp_server_port,
        },
        "features": {
            "auth_enabled": settings.mcp_auth_enabled,
            "telemetry_enabled": settings.otel_enabled,
        },
        "logging": {
            "level": settings.log_level,
        },
    }

    import json

    return json.dumps(config_info, indent=2)


@mcp.prompt("welcome")
def welcome_prompt() -> str:
    """Welcome prompt for new connections."""
    return f"""
# Welcome to EmailMcp!

An MCP Server based on Azure Emailer

## Available Tools
Use the tools/list method to see all available tools.

## Server Information
- Version: 0.1.0
- Authentication: {"Enabled" if settings.mcp_auth_enabled else "Disabled"}
- Telemetry: {"Enabled" if settings.otel_enabled else "Disabled"}

## Getting Started
Try the `hello_world` tool to test the connection:
```
{{"tool": "hello_world", "arguments": {{"name": "User"}}}}
```
"""


def main():
    """Main entry point for the MCP server."""
    try:
        # Debug: Log all settings
        logger.info(f"=== EmailMcp Configuration ===")
        logger.info(f"Host: {settings.mcp_server_host}")
        logger.info(
            f"Port: {settings.mcp_server_port} (type: {type(settings.mcp_server_port)})"
        )
        logger.info(f"Auth Enabled: {settings.mcp_auth_enabled}")
        logger.info(f"Transport: streamable-http")
        logger.info(f"==============================")

        # Always run in streamable-http mode
        logger.info(
            f"Starting MCP server in streamable-http mode on {settings.mcp_server_host}:{settings.mcp_server_port}"
        )
        logger.info(f"MCP endpoint: /mcp")
        mcp.run(
            host=settings.mcp_server_host,
            port=settings.mcp_server_port,
            transport="streamable-http",
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
