# Start HiChat Web Client (Development Mode)
# This script starts HiChat with the deploy directory configuration

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$deployDir = Join-Path $repoRoot "deploy"
$hichatDir = Join-Path $repoRoot "clients\hichat"

# Verify deploy directory exists
if (-not (Test-Path $deployDir)) {
    Write-Host "Error: Deploy directory not found at $deployDir" -ForegroundColor Red
    exit 1
}

# Verify HiChat directory exists
if (-not (Test-Path $hichatDir)) {
    Write-Host "Error: HiChat directory not found at $hichatDir" -ForegroundColor Red
    exit 1
}

# Change to HiChat directory
Set-Location $hichatDir

# Start HiChat with deploy directory
Write-Host "Starting HiChat Web Client..." -ForegroundColor Cyan
Write-Host "  Deploy directory: $deployDir" -ForegroundColor Gray
Write-Host "  HiChat directory: $hichatDir" -ForegroundColor Gray
Write-Host ""

python main.py --deploy-dir $deployDir
