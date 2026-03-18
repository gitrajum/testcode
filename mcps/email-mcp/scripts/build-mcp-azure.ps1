# Build and Deploy script for MCP Server to Azure Container Apps
# Prerequisites:
#   - az login (authenticate to Azure)
#   - az acr login --name <your-registry> (authenticate to container registry)
# Usage: .\scripts\build-mcp-azure.ps1 [version] [-SkipPush] [-SkipDeploy]

param(
    [string]$Version = "latest",
    [switch]$SkipPush,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"

# ==========================================
# CONFIGURATION - Update these values
# ==========================================

# Azure Container Registry details
# Azure Container Registry details
$registry = "acrbayerafdev.azurecr.io"
$imageName = "email-mcp"
$workspaceRoot = "../../../"  # Path to workspace root from this script
$dockerfilePath = "agentic_ai_finops_actuals/mcps/email-mcp/Dockerfile"

# Azure Container App details
$resourceGroup = "rg-finopsai-dev-gwc"
$containerAppName = "ca-emailmcp-finopsai-dev-gwc"

# ==========================================
# Validation
# ==========================================

if ($registry -eq "YOUR_ACR_NAME.azurecr.io") {
    Write-Host "[!] WARNING: Please update the registry name in this script!" -ForegroundColor Yellow
    Write-Host "   Edit line with: `$registry = 'YOUR_ACR_NAME.azurecr.io'" -ForegroundColor Yellow
    Write-Host "`n   Example: `$registry = 'acrmcpserver.azurecr.io'" -ForegroundColor White
    $continue = Read-Host "`nContinue anyway? (y/N)"
    if ($continue -ne "y") {
        exit 0
    }
}

# ==========================================
# Build Docker Image
# ==========================================

Write-Host "`n=== Building ${registry}/${imageName}:${Version} ===" -ForegroundColor Cyan
Write-Host "Build context: Workspace root (requires agentic_ai_sdk/)" -ForegroundColor Yellow
Write-Host "Dockerfile: $dockerfilePath" -ForegroundColor White

# Change to workspace root for build context
$originalLocation = Get-Location
Set-Location $workspaceRoot

# Build arguments with proxy settings
$buildArgs = @(
    "--build-arg", "HTTP_PROXY=$env:HTTP_PROXY",
    "--build-arg", "HTTPS_PROXY=$env:HTTPS_PROXY",
    "-f", $dockerfilePath,
    "-t", "${registry}/${imageName}:${Version}",
    "."
)

# Build the image
docker build @buildArgs

$buildExitCode = $LASTEXITCODE
Set-Location $originalLocation

if ($buildExitCode -ne 0) {
    Write-Host "[X] Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Build successful!" -ForegroundColor Green

# Tag as latest if building a version tag
if ($Version -ne "latest") {
    Write-Host "`nTagging as latest..." -ForegroundColor Cyan
    docker tag "${registry}/${imageName}:${Version}" "${registry}/${imageName}:latest"
}

# ==========================================
# Push to Azure Container Registry
# ==========================================

if (-not $SkipPush) {
    Write-Host "`n=== Pushing to Azure Container Registry ===" -ForegroundColor Cyan
    Write-Host "Registry: $registry" -ForegroundColor White

    # Check if logged in to ACR
    # Write-Host "`nChecking ACR authentication..." -ForegroundColor Yellow
    # $acrName = $registry.Split('.')[0]

    # Write-Host "Attempting to login to ACR: $acrName" -ForegroundColor Yellow
    # az acr login --name $acrName 2>$null
    # if ($LASTEXITCODE -ne 0) {
    #     Write-Host "[X] ACR login failed!" -ForegroundColor Red
    #     Write-Host "   Please run: az login" -ForegroundColor Yellow
    #     Write-Host "   Then run: az acr login --name $acrName" -ForegroundColor Yellow
    #     exit 1
    # }

    # Write-Host "[OK] ACR authentication successful" -ForegroundColor Green

    # Push version tag
    Write-Host "`nPushing ${Version}..." -ForegroundColor Cyan
    docker push "${registry}/${imageName}:${Version}"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Push failed for ${Version}!" -ForegroundColor Red
        exit 1
    }

    # Push latest tag if applicable
    if ($Version -ne "latest") {
        Write-Host "Pushing latest..." -ForegroundColor Cyan
        docker push "${registry}/${imageName}:latest"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[X] Push failed for latest!" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "[OK] Pushed to registry!" -ForegroundColor Green
} else {
    Write-Host "`n[>>] Skipping push (use without -SkipPush to push)" -ForegroundColor Yellow
}

# ==========================================
# Deploy to Azure Container Apps
# ==========================================

if (-not $SkipDeploy -and -not $SkipPush) {
    Write-Host "`n=== Deploying to Azure Container Apps ===" -ForegroundColor Cyan
    Write-Host "Resource Group: $resourceGroup" -ForegroundColor White
    Write-Host "Container App: $containerAppName" -ForegroundColor White

    # Check if Azure CLI is available and logged in
    Write-Host "`nChecking Azure CLI authentication..." -ForegroundColor Yellow
    az account show --output none 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Not logged in to Azure!" -ForegroundColor Red
        Write-Host "   Please run: az login" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[OK] Azure CLI authenticated" -ForegroundColor Green

    # Load environment variables from .env file
    Write-Host "`nLoading environment variables from .env file..." -ForegroundColor Yellow
    $envFile = Join-Path (Join-Path $PSScriptRoot "..") ".env"
    $envVars = @()

    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            # Skip comments and empty lines
            if ($line -and -not $line.StartsWith("#")) {
                # Parse KEY=VALUE format
                if ($line -match "^([^=]+)=(.*)$") {
                    $key = $matches[1].Trim()
                    $value = $matches[2].Trim()
                    $envVars += "$key=$value"
                }
            }
        }
        Write-Host "[OK] Loaded $($envVars.Count) environment variables" -ForegroundColor Green
    } else {
        Write-Host "[!] Warning: .env file not found at $envFile" -ForegroundColor Yellow
    }

    # Create revision suffix from version
    $revisionSuffix = $Version.Replace(".", "").Replace("v", "v")
    if ($revisionSuffix -eq "latest") {
        $revisionSuffix = "v" + (Get-Date -Format "yyyyMMddHHmmss")
    }

    Write-Host "`nDeploying revision: $revisionSuffix" -ForegroundColor Cyan
    Write-Host "Parameters: --name $containerAppName --resource-group $resourceGroup --image ${registry}/${imageName}:${Version} --revision-suffix $revisionSuffix" -ForegroundColor White
    Write-Host "Environment variables: $($envVars.Count) variables from .env" -ForegroundColor White

    # Deploy with environment variables
    az containerapp update `
        --name $containerAppName `
        --resource-group $resourceGroup `
        --image "${registry}/${imageName}:${Version}" `
        --revision-suffix $revisionSuffix `
        --set-env-vars $envVars `
        --output none

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Deployment failed!" -ForegroundColor Red
        Write-Host "   Tip: Make sure the container app exists and you have permissions" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "[OK] Deployed successfully!" -ForegroundColor Green

    # Wait and check revision status
    Write-Host "`nWaiting for revision to become active..." -ForegroundColor Cyan
    Start-Sleep -Seconds 10

    Write-Host "`n=== Revision Status ===" -ForegroundColor Cyan
    az containerapp revision list `
        --name $containerAppName `
        --resource-group $resourceGroup `
        --output table

    # Get the FQDN
    Write-Host "`n=== Deployment Information ===" -ForegroundColor Cyan
    $fqdn = az containerapp show `
        --name $containerAppName `
        --resource-group $resourceGroup `
        --query "properties.configuration.ingress.fqdn" `
        --output tsv

    Write-Host "[OK] Deployment complete!" -ForegroundColor Green
    if ($fqdn) {
        Write-Host "FQDN: https://$fqdn" -ForegroundColor White
        Write-Host "Health: https://${fqdn}/health" -ForegroundColor White
    }

} elseif ($SkipPush) {
    Write-Host "`n[>>] Skipping deploy (image not pushed)" -ForegroundColor Yellow
} else {
    Write-Host "`n[>>] Skipping deploy (use without -SkipDeploy to deploy)" -ForegroundColor Yellow
}

Write-Host "`n[OK] Script completed successfully!" -ForegroundColor Green
