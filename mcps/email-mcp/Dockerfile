# syntax=docker/dockerfile:1

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy SDK from parallel checkout directory
COPY agentic_ai_sdk /sdk

# Install SDK first (non-editable for proper packaging)
WORKDIR /sdk
RUN uv pip install --system --no-cache ".[microsoft,a2a,observability]"

# Copy dependency files
WORKDIR /app
COPY af_agentcell_004/mcps/email-mcp/pyproject.toml .
COPY af_agentcell_004/mcps/email-mcp/src ./src
COPY af_agentcell_004/mcps/email-mcp/cli ./cli

# Install dependencies to system (non-editable)
RUN uv pip install --system --no-cache .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY af_agentcell_004/mcps/email-mcp/pyproject.toml ./
COPY af_agentcell_004/mcps/email-mcp/src/ ./src/
COPY af_agentcell_004/mcps/email-mcp/cli/ ./cli/
COPY af_agentcell_004/mcps/email-mcp/.env.example ./

# Create non-root user
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

# Switch to non-root user
USER mcpuser

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the MCP server
CMD ["email-mcp"]
