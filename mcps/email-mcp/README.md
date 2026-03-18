# EmailMcp

An MCP Server based on Azure Emailer

## Overview

This MCP (Model Context Protocol) server provides tools, resources, and prompts that can be consumed by LLM applications and agents. It is built using [FastMCP](https://github.com/jlowin/fastmcp) framework.

## Features

- 🚀 **FastMCP Framework**: Lightweight and efficient MCP server implementation
- � **Email Tools**: Send emails via Azure Communication Services with attachments and HTML support
- �🔧 **Example Tools**: Hello world, echo, math operations, string manipulation
- 📦 **Resources**: Server configuration and status
- 💬 **Prompts**: Welcome and usage guidance
- 🔐 **Authentication** (Optional): JWT-based auth with OAuth2/Azure AD
- 📊 **Telemetry** (Optional): OpenTelemetry instrumentation
- 🧪 **Testing**: Unit and integration tests with pytest
- 🐳 **Docker**: Multi-stage builds with uv, security hardening, and health checks

## Installation

### Basic Installation

```bash
pip install -e .
```

### With Optional Features

```bash
# With authentication support
pip install -e ".[auth]"

# With telemetry support
pip install -e ".[telemetry]"

# With all features
pip install -e ".[auth,telemetry]"

# With development tools
pip install -e ".[dev]"
```

## Docker Support

### Dockerfile Features

The included [Dockerfile](Dockerfile) follows enterprise best practices:

**Multi-Stage Build:**
- 🏗️ **Builder Stage**: Installs dependencies with `uv` (10-100x faster than pip)
- 🚀 **Runtime Stage**: Minimal production image with only necessary files

**Security:**
- 🔒 Non-root user (`mcpuser`, UID 1000)
- 🔐 Minimal attack surface
- ✅ Health checks built-in (30s interval, 10s timeout, 5s start period)

**Performance:**
- ⚡ Fast builds with `uv` package manager from `ghcr.io/astral-sh/uv:latest`
- 📦 Optimized layer caching
- 🎯 37% smaller images compared to previous version

**Build Optimization:**
- `.dockerignore` file excludes unnecessary files (tests, docs, .git, etc.)
- Only production code and dependencies included

### Building Docker Image

```bash
# Using agenticai CLI (recommended)
email-mcp-cli docker build

# Or using Docker directly
docker build -t email-mcp:latest .

# Build with custom tag
docker build -t email-mcp:v1.0.0 .
```

### Running in Docker

```bash
# Using agenticai CLI
email-mcp-cli docker run

# Or using Docker directly
docker run -p 8000:8000 \
  --env-file .env \
  email-mcp:latest

# With custom environment variables
docker run -p 8000:8000 \
  -e MCP_SERVER_PORT=8000 \
  -e LOG_LEVEL=INFO \
  email-mcp:latest
```

### Health Check

The container includes a health check that verifies the MCP server is responding:

```bash
# Check container health
docker ps

# View health check logs
docker inspect --format='{{json .State.Health}}' <container-id>
```

### What Gets Excluded (.dockerignore)

The following files/directories are excluded from the Docker image:
- Tests (`tests/`, `__pycache__/`, `*.pyc`)
- Documentation (`docs/`, `*.md` except README.md)
- Development files (`.venv/`, `.git/`, `.vscode/`)
- Terraform files (`terraform/`)
- Build artifacts (`dist/`, `*.egg-info/`)

See [`.dockerignore`](.dockerignore) for the complete list.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_SERVER_HOST` | Server bind address | `0.0.0.0` |
| `MCP_SERVER_PORT` | Server port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MCP_AUTH_ENABLED` | Enable authentication | `false` |
| `OTEL_ENABLED` | Enable telemetry | `false` |
| `AZURE_COMMUNICATION_CONNECTION_STRING` | Azure Communication Services connection string | - |
| `AZURE_EMAIL_DOMAIN` | Azure email domain (e.g., `example.azurecomm.net`) | - |

### Azure Communication Services Setup

To use the email features, you need to configure Azure Communication Services:

1. **Create Azure Communication Services resource** in Azure Portal
2. **Add Email Service** and connect a verified domain
3. **Get Connection String** from the Keys section
4. **Configure environment variables:**

```env
AZURE_COMMUNICATION_CONNECTION_STRING=endpoint=https://your-resource.communication.azure.com/;accesskey=your-access-key
AZURE_EMAIL_DOMAIN=your-domain.azurecomm.net
```

**Note:** The sender address will be `DoNotReply@{AZURE_EMAIL_DOMAIN}`

### Authentication (Optional)

This MCP server includes Azure AD authentication using the AgenticAI SDK:

**Features:**
- ✅ Validates Azure AD JWT tokens from Managed Identity
- ✅ Extracts user identity from token claims
- ✅ Automatic token signature verification using JWKS
- ✅ Comprehensive audit logging (Bayer 4.2.36)

**Configuration:**

```env
# Enable authentication
MCP_AUTH_ENABLED=true

# Azure AD Configuration
AZURE_TENANT_ID=fcb2b37b-5da0-466b-9b83-0014b67a7c78
MANAGED_IDENTITY_CLIENT_ID=906f830e-eeab-46e1-9e90-ad410c8649a3
```

**How It Works:**

1. Client acquires token from Azure Managed Identity
2. Client includes token in `Authorization: Bearer <token>` header
3. MCP server validates token using `EntraIDTokenVerifier`
4. User identity extracted and logged for all requests

**Disabling for Local Development:**

```env
MCP_AUTH_ENABLED=false
```

**Token Validation:**

The server validates:
- Token signature (using Azure AD JWKS)
- Issuer (`https://login.microsoftonline.com/{tenant}/v2.0`)
- Audience (managed identity client ID)
- Expiration (exp claim)
- Not-before (nbf claim)

**User Identity:**

From validated tokens, the server extracts:

```python
{
    "user_id": "oid-from-token",      # Object ID
    "email": "user@bayer.com",        # Email claim
    "name": "User Name",              # Display name
    "tenant_id": "tenant-id"          # Bayer tenant
}
```

For implementation details, see [src/auth.py](src/auth.py).

### Telemetry (Optional)

For OpenTelemetry:

```env
OTEL_ENABLED=true
OTEL_SERVICE_NAME=email-mcp
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

## Usage

### Running the Server

#### Stdio Transport (Default)

```bash
email-mcp
```

Or with Python:

```bash
python -m src.main
```

#### HTTP Transport

```bash
python -c "from src.main import mcp; mcp.run(transport='http', host='8000')"
```

### MCP Client Configuration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "email-mcp": {
      "command": "email-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

## Available Tools

### Email Tools

#### send_email

Send an email using Azure Communication Services.

**Features:**
- Plain text and HTML email content
- File attachments (PDF, images, documents)
- Base64-encoded attachment support
- Comprehensive error handling

**Parameters:**
- `recipient` (string, required): Email address of the recipient
- `subject` (string, required): Subject line of the email
- `content` (string, required): Plain text content
- `html_content` (string, optional): HTML version of the content
- `attachments` (list, optional): List of attachment dictionaries with:
  - `name`: Filename (e.g., "report.pdf")
  - `content_type`: MIME type (e.g., "application/pdf")
  - `content_base64`: Base64-encoded file content

**Example - Simple Email:**
```json
{
  "tool": "send_email",
  "arguments": {
    "recipient": "colleague@example.com",
    "subject": "Meeting Reminder",
    "content": "Don't forget our meeting tomorrow at 10 AM."
  }
}
```

**Example - Email with HTML:**
```json
{
  "tool": "send_email",
  "arguments": {
    "recipient": "team@example.com",
    "subject": "Weekly Update",
    "content": "Weekly project update attached.",
    "html_content": "<h1>Weekly Update</h1><p>See attached for details.</p>"
  }
}
```

**Example - Email with Attachment:**
```json
{
  "tool": "send_email",
  "arguments": {
    "recipient": "manager@example.com",
    "subject": "Q4 Report",
    "content": "Please find the Q4 report attached.",
    "attachments": [{
      "name": "report.pdf",
      "content_type": "application/pdf",
      "content_base64": "JVBERi0xLjQKJeLjz9M..."
    }]
  }
}
```

#### get_email_history

Get the history of emails sent through this MCP server.

**Parameters:**
- `limit` (integer, optional): Maximum number of recent emails to return (default: 10)

**Example:**
```json
{
  "tool": "get_email_history",
  "arguments": {
    "limit": 5
  }
}
```

**Response:**
```json
{
  "total_emails_sent": 42,
  "history_size": 42,
  "recent_emails": [
    {
      "recipient": "user@example.com",
      "subject": "Test Email",
      "timestamp": "2026-01-05T10:30:00",
      "status": "sent",
      "message_id": "abc-123-def"
    }
  ]
}
```

#### test_email_connection

Test the Azure Communication Services connection and configuration.

**Example:**
```json
{
  "tool": "test_email_connection",
  "arguments": {}
}
```

**Response:**
```json
{
  "success": true,
  "message": "Azure Communication Services configured successfully",
  "sender_address": "DoNotReply@yourdomain.azurecomm.net",
  "email_domain": "yourdomain.azurecomm.net",
  "client_initialized": true
}
```

### Example Tools (Hello World)

#### hello_world

Greet a user by name.

```json
{
  "tool": "hello_world",
  "arguments": {
    "name": "Alice"
  }
}
```

#### echo

Echo back a message.

```json
{
  "tool": "echo",
  "arguments": {
    "message": "Hello, MCP!"
  }
}
```

#### add_numbers

Add two numbers.

```json
{
  "tool": "add_numbers",
  "arguments": {
    "a": 5,
    "b": 3
  }
}
```

#### reverse_string

Reverse a string.

```json
{
  "tool": "reverse_string",
  "arguments": {
    "text": "hello"
  }
}
```

## Resources

### config://settings

Get current server configuration (non-sensitive data).

```json
{
  "resource": "config://settings"
}
```

## Prompts

### welcome

Get welcome message and usage instructions.

```json
{
  "prompt": "welcome"
}
```

## Deployment Configuration

### Terraform Variables

Configure `terraform/terraform.tfvars`:

```hcl
subscription_id = "your-azure-subscription-id"
resource_group_name = "rg-email-mcp-dev"
location = "eastus"
environment = "dev"

# Container configuration
mcp_container_image = "your-registry.azurecr.io/email-mcp:latest"
mcp_container_cpu = 0.25
mcp_container_memory = "0.5Gi"

# Enable external ingress if needed
# mcp_ingress_external = true
# mcp_ingress_target_port = 8000

# Environment variables for the container
mcp_env_vars = {
  MCP_NAME = "EmailMcp"
  LOG_LEVEL = "INFO"
}

# Secrets (store sensitive data in Azure Key Vault)
# mcp_secrets = {
#   API_KEY = "your-secret-value"
# }
```

See `terraform/terraform.tfvars.example` for all available options.

### CI/CD Integration

#### GitHub Actions

```yaml
name: Deploy MCP Server

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Build and Push
        run: |
          email-mcp-cli docker build --tag ${{ github.sha }}
          email-mcp-cli docker push --tag ${{ github.sha }}

      - name: Deploy Infrastructure
        run: |
          email-mcp-cli iac deploy \
            --subscription-id ${{ secrets.AZURE_SUBSCRIPTION_ID }} \
            --container-image ${{ secrets.REGISTRY }}/${{ github.sha }}
```

#### Azure DevOps

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: AzureCLI@2
    inputs:
      azureSubscription: 'your-service-connection'
      scriptType: 'bash'
      scriptLocation: 'inlineScript'
      inlineScript: |
        email-mcp-cli docker build --tag $(Build.BuildId)
        email-mcp-cli docker push --tag $(Build.BuildId)
        email-mcp-cli iac deploy \
          --subscription-id $(SUBSCRIPTION_ID) \
          --container-image $(REGISTRY)/$(Build.BuildId)
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run with coverage
pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

### Project Structure

```
email-mcp/
├── src/
│   ├── __init__.py
│   ├── main.py              # MCP server entry point
│   ├── config.py            # Configuration management
│   └── services/            # Tool services
│       ├── __init__.py
│       ├── hello_world_service.py
│       ├── auth_service.py         # Optional
│       └── telemetry_service.py    # Optional
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_hello_world_service.py
│   └── test_server.py
├── docs/                    # Additional documentation
├── .env.example
├── .gitignore
├── pyproject.toml
├── Dockerfile
└── README.md
```

## Docker

### Build Image

```bash
# Using CLI
email-mcp-cli docker build --tag latest

# Or manually
docker build -t email-mcp:latest .
```

### Push to Registry

```bash
# Login to Azure Container Registry
email-mcp-cli docker login --registry your-registry.azurecr.io

# Build and push
email-mcp-cli docker build --tag v1.0.0 --registry your-registry.azurecr.io
email-mcp-cli docker push --tag v1.0.0 --registry your-registry.azurecr.io
```

### Run Container Locally

```bash
docker run --rm -it \
  -p 8000:8000 \
  --env-file .env \
  email-mcp:latest
```

### Docker Compose

```yaml
version: '3.8'
services:
  mcp-server:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
```

## Azure Deployment

### Prerequisites

- Azure CLI installed and authenticated
- Azure subscription
- Docker (for building images)

### Quick Deployment

```bash
# 1. Configure terraform.tfvars
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars with your values

# 2. Build and push Docker image
email-mcp-cli docker build --tag latest --registry your-registry.azurecr.io
email-mcp-cli docker push --tag latest --registry your-registry.azurecr.io

# 3. Deploy infrastructure
email-mcp-cli iac deploy \
  --subscription-id <your-subscription-id> \
  --resource-group rg-email-mcp-dev \
  --state-rg rg-terraform-state \
  --state-storage stterraformstate \
  --container-image your-registry.azurecr.io/email-mcp:latest
```

### Infrastructure Components

The Terraform configuration deploys:

- **Resource Group**: Isolated resource container
- **Container App Environment**: Managed Kubernetes environment
- **Container App**: Your MCP server running in a container
- **Log Analytics Workspace**: Centralized logging
- **Container Registry** (optional): Private Docker registry

### CLI Commands

#### Infrastructure Management

```bash
# Deploy infrastructure
email-mcp-cli iac deploy \
  --subscription-id <sub-id> \
  --container-image <image> \
  --state-rg <state-rg> \
  --state-storage <state-storage>

# Show infrastructure outputs
email-mcp-cli iac output

# Destroy infrastructure
email-mcp-cli iac destroy \
  --subscription-id <sub-id> \
  --state-rg <state-rg> \
  --state-storage <state-storage>
```

#### Docker Management

```bash
# Build image
email-mcp-cli docker build --tag <tag> --registry <registry>

# Push image
email-mcp-cli docker push --tag <tag> --registry <registry>

# Login to registry
email-mcp-cli docker login --registry <registry>
```

### Manual Terraform

If you prefer using Terraform directly:

```bash
cd terraform

# Initialize
terraform init \
  -backend-config="resource_group_name=<state-rg>" \
  -backend-config="storage_account_name=<state-storage>"

# Plan
terraform plan \
  -var="subscription_id=<sub-id>" \
  -var="mcp_container_image=<image>" \
  -out=tfplan

# Apply
terraform apply tfplan

# Show outputs
terraform output
```

## Production Considerations

### Security

- **Secrets Management**: Store secrets in Azure Key Vault, not in terraform.tfvars
- **Managed Identities**: Use Azure Managed Identities for resource access
- **Network Security**: Enable private networking for sensitive workloads
- **Authentication**: Configure Container App authentication/authorization
- **Credential Rotation**: Rotate credentials regularly

### Monitoring

- **Logs**: Container App sends logs to Log Analytics workspace
- **Alerts**: Set up Azure Monitor alerts for failures and performance
- **Telemetry**: Configure Application Insights for detailed telemetry
- **Metrics**: Monitor CPU, memory, request count, and latency

### Scaling

Configure auto-scaling in terraform.tfvars:

```hcl
mcp_min_replicas = 1
mcp_max_replicas = 10
```

Scaling is based on HTTP request rate and CPU/memory usage.

### High Availability

- Deploy to multiple regions using Terraform workspaces
- Use Azure Front Door for global load balancing
- Configure health probes and readiness checks
- Set up disaster recovery procedures

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `pytest`
5. Format code: `black src/ tests/`
6. Commit changes: `git commit -am 'Add new feature'`
7. Push to branch: `git push origin feature/my-feature`
8. Open a Pull Request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: [Report a bug](https://github.com/Miroslav Kozma/email-mcp/issues)
- Documentation: See `docs/` directory

## Related Resources

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

**Author**: Miroslav Kozma (miroslav.kozma.ext@bayer.com)
**Version**: 0.1.0
