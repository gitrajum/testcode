# # syntax=docker/dockerfile:1

# # Stage 1: Builder - Install dependencies
# FROM python:3.11-slim AS builder

# WORKDIR /app

# # Install uv from official distroless image
# COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# # Copy dependency files
# COPY pyproject.toml .

# # Install dependencies to system
# RUN uv pip install --system --no-cache -e .

# # Stage 2: Runtime
# FROM python:3.11-slim

# WORKDIR /app

# # Copy Python packages from builder stage
# COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# COPY --from=builder /usr/local/bin /usr/local/bin

# # Copy application code
# COPY pyproject.toml ./
# COPY src/ ./src/
# COPY configs/ ./configs/
# COPY cli/ ./cli/

# # Create non-root user
# RUN useradd -m -u 1000 appuser && \
#     chown -R appuser:appuser /app

# # Switch to non-root user
# USER appuser

# # Expose port
# EXPOSE 8000

# # Environment variables
# ENV PYTHONUNBUFFERED=1 \
#     CONFIG_PATH=configs/config.yaml \
#     DEBUGPY_ENABLE=false \
#     DEBUGPY_WAIT=false \
#     DEBUGPY_PORT=5678

# # Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import sys; sys.exit(0)"

# # Run the agent
# CMD ["python", "-m", "src"]

# syntax=docker/dockerfile:1

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# List files at workspace root (build context) before copying SDK
RUN echo "=== Build context should contain: af_agentcell_004/ and agentic_ai_sdk/ ===" && echo "Current directory:" && pwd

# Copy SDK from workspace root (when building from workspace root)
COPY agentic_ai_sdk /sdk
RUN echo "=== Listing /sdk directory after SDK copy ===" && ls -la /sdk

# Install SDK first (non-editable for proper packaging) - exclude observability to avoid OTel conflicts
# --prerelease=allow is required because agent-framework-core depends on azure-ai-projects pre-releases
WORKDIR /sdk
RUN uv pip install --system --no-cache --prerelease=allow ".[microsoft,a2a]"

# # Install git for cloning SDK if needed (not needed - using local SDK from workspace)
# RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Switch back to /app for agent dependencies
WORKDIR /app

# List files before copying dependency files
RUN echo "=== Listing /app directory before pyproject.toml copy ===" && ls -la /app

# Copy dependency files
COPY af_agentcell_004/agents/mobile-contract-agent/pyproject.toml .
COPY af_agentcell_004/agents/mobile-contract-agent/patch_observability.py /tmp/patch_observability.py

# Accept build arguments for secrets (not needed - using local SDK)
# ARG ARTIFACTORY_USER_NAME_SDK
# ARG ARTIFACTORY_USER_TOKEN_SDK
# ARG GH_PAT_MODULES

# Install SDK first (non-editable for proper packaging) with extra dependencies
# WORKDIR /sdk

# Install SDK and agent dependencies from Artifactory
RUN set -e && \
    # \
    # #if [ -n "$ARTIFACTORY_USER_NAME_SDK" ]; then \
    # if true; then \
    #     echo "Installing SDK from Artifactory..." && \
    #     echo "DEBUG: User length: ${#ARTIFACTORY_USER_NAME_SDK}, Token length: ${#ARTIFACTORY_USER_TOKEN_SDK}" && \
    #     pip install --no-cache-dir \
    #         --index-url "https://${ARTIFACTORY_USER_NAME_SDK}:${ARTIFACTORY_USER_TOKEN_SDK}@artifactory.bayer.com/artifactory/api/pypi/agf-pypi-dev-sdk/simple" \
    #         --extra-index-url "https://pypi.org/simple" \
    #         --pre "agentic-ai-sdk[microsoft,a2a,observability]>=1.0.0rc1" && \
    #     export PIP_INDEX_URL="https://${ARTIFACTORY_USER_NAME_SDK}:${ARTIFACTORY_USER_TOKEN_SDK}@artifactory.bayer.com/artifactory/api/pypi/agf-pypi-dev-sdk/simple" && \
    #     export PIP_EXTRA_INDEX_URL="https://pypi.org/simple"; \
    # else \
    #     #echo "Cloning SDK from GitHub..." && \
    #     #if [ -n "$GH_PAT_MODULES" ]; then \
    #     #    git clone https://oauth2:${GH_PAT_MODULES}@github.com/bayer-int/agentic_ai_sdk /sdk; \
    #     #else \
    #     #    git clone https://github.com/bayer-int/agentic_ai_sdk /sdk; \
    #     #fi && \
    #     #cd /sdk && \
    #     # uv pip install --system --no-cache ".[microsoft,a2a,observability]" && \
    #     uv pip install --system --no-cache --index-url https://pypi.org/simple ".[microsoft,a2a, observability]"; \
    #     #cd /app && \
    #     #EXTRA_INDEX=""; \
    # fi && \
    # \
    # echo "=== Installed agentic-ai-sdk ===" && \
    # pip show agentic-ai-sdk && \
    # echo "=== Key dependencies (indicates extras installed) ===" && \
    # pip list | grep -E "(agent-framework-core|azure-ai-projects|fastapi|uvicorn|opentelemetry-)" || echo "No matching dependencies found" && \
    # echo "===============================" && \
    # \
    # cd /app && \
    # echo "Installing agent dependencies..." && \
    # #pip install --no-cache-dir .
    # ## Patching agent-framework-core for compatibility with opentelemetry-semantic-conventions-ai>=0.4.0 until the bug is fixed in the sdk
    echo "=== Installed agentic-ai-sdk (from local source) ===" && \
    pip show agentic-ai-sdk && \
    echo "=== Key dependencies ===" && \
    pip list | grep -E "(agent-framework-core|azure-ai-projects|fastapi|uvicorn|opentelemetry-)" || echo "No matching dependencies found" && \
    echo "===============================" && \
    echo "Installing agent dependencies..." && \
    pip install --no-cache-dir . &&\
    echo "Patching agent_framework/observability.py..." && \
    python /tmp/patch_observability.py && \
    echo "Patch applied. Verifying..." && \
    python -c "import agent_framework; print('agent_framework import OK')"

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# List files before copying application code
RUN echo "=== Listing /app directory before application code copy ===" && ls -la /app

# Copy application code
COPY af_agentcell_004/agents/mobile-contract-agent/pyproject.toml ./pyproject.toml
COPY af_agentcell_004/agents/mobile-contract-agent/src/ ./src/
COPY af_agentcell_004/agents/mobile-contract-agent/configs/ ./configs/
COPY af_agentcell_004/agents/mobile-contract-agent/cli/ ./cli/

# List files after copying all application code
RUN echo "=== Final /app directory structure ===" && ls -laR /app

# Create non-root user and required directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /mnt/agentfiles/uploads/signed_url_cache \
             /mnt/agentfiles/data \
             /mnt/agentfiles/output && \
    chown -R appuser:appuser /app /mnt/agentfiles

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=configs/config.yaml \
    DEBUGPY_ENABLE=false \
    DEBUGPY_WAIT=false \
    DEBUGPY_PORT=5678

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the agent
CMD ["python", "-m", "src"]
