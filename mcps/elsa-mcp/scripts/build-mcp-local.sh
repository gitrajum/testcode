#!/bin/bash
# Build script for AI Agentic Platform MCP (LOCAL TESTING)
# This script builds the Docker image locally with proxy support
# Usage: ./build-mcp-local.sh [tag]

set -e  # Exit on error

# Default tag
TAG="${1:-latest}"

# Get the repository root (4 levels up from scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # scripts folder
ELSA_MCP_DIR="$(dirname "$SCRIPT_DIR")"  # elsa-mcp folder
MCPS_DIR="$(dirname "$ELSA_MCP_DIR")"  # mcps folder
FINOPS_DIR="$(dirname "$MCPS_DIR")"  # af_agentcell_004 folder
REPO_ROOT="$(dirname "$FINOPS_DIR")"  # repository root

# Proxy configuration (required for Bayer network)
# Comment out if not needed or if proxy auth is not configured
# PROXY="http://10.185.190.70:8080"

# Image details
IMAGE_NAME="ai-agentic-platform-mcp-elsa"
DOCKERFILE="$ELSA_MCP_DIR/Dockerfile"

# Colors for output
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Clean up existing resources first
echo -e "\n${CYAN}=== Cleaning up existing Docker resources ===${NC}"

# Stop and remove any containers using this image
ALL_CONTAINERS=$(docker ps -a -q --filter "ancestor=${IMAGE_NAME}:${TAG}" 2>/dev/null || true)
if [ -n "$ALL_CONTAINERS" ]; then
    echo -e "${YELLOW}Removing containers using ${IMAGE_NAME}:${TAG}...${NC}"
    docker rm -f $ALL_CONTAINERS 2>/dev/null || true
fi

# Remove image if exists
EXISTING_IMAGE=$(docker images -q "${IMAGE_NAME}:${TAG}" 2>/dev/null || true)
if [ -n "$EXISTING_IMAGE" ]; then
    echo -e "${YELLOW}Removing old image: ${IMAGE_NAME}:${TAG}${NC}"
    docker rmi "${IMAGE_NAME}:${TAG}" 2>/dev/null || true
fi

# Build the image
echo -e "\n${CYAN}=== Building ${IMAGE_NAME}:${TAG} ===${NC}"

if [ -n "$PROXY" ]; then
    echo -e "${YELLOW}Using proxy: $PROXY${NC}"
    docker build \
        --build-arg HTTP_PROXY="$PROXY" \
        --build-arg HTTPS_PROXY="$PROXY" \
        --build-arg http_proxy="$PROXY" \
        --build-arg https_proxy="$PROXY" \
        -f "$DOCKERFILE" \
        -t "${IMAGE_NAME}:${TAG}" \
        "$REPO_ROOT"
else
    echo -e "${YELLOW}Building without proxy${NC}"
    docker build \
        -f "$DOCKERFILE" \
        -t "${IMAGE_NAME}:${TAG}" \
        "$REPO_ROOT"
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Build successful!${NC}"
echo "Image: ${IMAGE_NAME}:${TAG}"

# Stop and remove existing container if running
echo ""
echo -e "${CYAN}Checking for existing container...${NC}"
EXISTING_CONTAINER=$(docker ps -a -q --filter "name=mcp-server-elsa" 2>/dev/null || true)
if [ -n "$EXISTING_CONTAINER" ]; then
    echo -e "${YELLOW}Stopping and removing existing container...${NC}"
    docker stop mcp-server-elsa 2>&1 >/dev/null || true
    docker rm mcp-server-elsa 2>&1 >/dev/null || true
else
    echo -e "${GRAY}No existing container found.${NC}"
fi

# Run the container
echo -e "${CYAN}Starting container...${NC}"

# Check if .env file exists
ENV_FILE="$ELSA_MCP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Loading environment variables from .env file...${NC}"
    docker run --rm -d --name mcp-server-elsa --env-file "$ENV_FILE" -p 8006:8000 "${IMAGE_NAME}:${TAG}"
else
    echo -e "${YELLOW}Warning: .env file not found at $ENV_FILE. Running without environment variables...${NC}"
    docker run --rm -d --name mcp-server-elsa -p 8006:8000 "${IMAGE_NAME}:${TAG}"
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start container!${NC}"
    exit 1
fi

# Wait for container to start
sleep 2

# Show container status
echo ""
echo -e "${GREEN}Container started successfully!${NC}"
docker ps --filter "name=mcp-server-elsa"

echo ""
echo -e "${CYAN}Useful commands:${NC}"
echo "docker logs mcp-server-elsa"
echo "docker logs -f mcp-server-elsa"
echo "docker stop mcp-server-elsa"
