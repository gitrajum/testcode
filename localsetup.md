# Local Setup Guide

> **Project:** Mobile Contract Agent + Wireless Analysis UI
> **Stack:** Docker, Next.js, FastAPI

---

## Prerequisites

- [Git](https://git-scm.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Access to Bayer GitHub (`bayer-int` org)

---

## Step 1 — Create Working Folder & Clone Repos

```powershell
git clone https://github.com/bayer-int/af_agentcell_004.git
cd af_agentcell_004
git checkout poc
cd ..

git clone https://github.com/bayer-int/agentic_ai_sdk.git
```

---

## Step 2 — Create Environment File

Create the file below and fill in your credentials:

```
af_agentcell_004/agents/mobile-contract-agent/.env.development
```

> Copy from `.env.example` in the same folder if one exists, then update values.

---

## Step 3 — Build & Run Agent Backend

> Run all commands from **`base MVP4 folder`**

### Build

```powershell
docker build `
  -f af_agentcell_004/agents/mobile-contract-agent/Dockerfile `
  -t mobcontr-agent:latest `
  .
```

### Run

```powershell
docker rm -f mobcontr-agent 2>$null
docker run -d `
  --name mobcontr-agent `
  -p 8000:8000 `
  --env-file "af_agentcell_004/agents/mobile-contract-agent/.env.development" `
  mobcontr-agent:latest
```

**Backend running at:** http://localhost:8000

---

## Step 4 — Build & Run UI

> Run all commands from **`MVP4/af_agentcell_004/ui`**

### Build

```powershell
docker build -f Dockerfile -t wireless-analysis:latest `
  --build-arg NEXT_PUBLIC_AZURE_CLIENT_ID="6a99f31c-bf54-4a3c-89e8-bb3e5b108a25" `
  --build-arg NEXT_PUBLIC_AZURE_TENANT_ID="fcb2b37b-5da0-466b-9b83-0014b67a7c78" `
  --build-arg NEXT_PUBLIC_AZURE_REDIRECT_URI="http://localhost:3000" `
  --build-arg NEXT_PUBLIC_AZURE_API_SCOPE="api://6a99f31c-bf54-4a3c-89e8-bb3e5b108a25/.default" `
  --build-arg NEXT_PUBLIC_API_URL="http://localhost:8000" `
  --build-arg NEXT_PUBLIC_WS_URL="ws://localhost:8000" `
  .
```

### Run

```powershell
docker rm -f wireless-ui 2>$null
docker run -d -p 3000:3000 --name wireless-ui wireless-analysis:latest
```

**UI running at:** http://localhost:3000

---

## Quick Reference

| Service        | URL                   | Container      |
|----------------|-----------------------|----------------|
| Agent Backend  | http://localhost:8000 | mobcontr-agent |
| UI             | http://localhost:3000 | wireless-ui    |

---

## Troubleshooting

**"No such container" error on `docker rm`**
This is harmless. The `2>$null` in the run commands already suppresses it. No action needed.

**Port already in use**
Run `docker ps` to see running containers, then `docker rm -f <container-name>` to stop one.
