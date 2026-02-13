<#
.SYNOPSIS
    Start the Claude Bridge service on the host.

.DESCRIPTION
    Launches the Claude Bridge HTTP service (port 8006) which bridges requests
    from the Docker-based gateway to the Claude Code CLI on the host.

    Same pattern as start_wcd_bridge.ps1 (Windows Composition Bridge on port 8005).

.PARAMETER Port
    Port to run the bridge on (default: 8006).

.EXAMPLE
    .\scripts\start_claude_bridge.ps1
    .\scripts\start_claude_bridge.ps1 -Port 8007
#>
param(
    [int]$Port = 8006
)

$ErrorActionPreference = "Stop"

# Navigate to repo root
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    # Verify claude CLI is available
    $claudeCli = Join-Path $env:USERPROFILE ".claude-cli\currentVersion\claude.exe"
    if (-not (Test-Path $claudeCli)) {
        Write-Error "Claude CLI not found at $claudeCli"
        return
    }
    Write-Host "Found Claude CLI: $claudeCli" -ForegroundColor Green

    # Set port via env var
    $env:CLAUDE_BRIDGE_PORT = $Port

    # Activate venv if present
    $venvActivate = Join-Path $repoRoot "venv\Scripts\Activate.ps1"
    if (Test-Path $venvActivate) {
        Write-Host "Activating venv..."
        & $venvActivate
    }

    Write-Host ""
    Write-Host "Starting Claude Bridge on port $Port ..." -ForegroundColor Cyan
    Write-Host "Gateway container should use: http://host.docker.internal:$Port" -ForegroundColor Yellow

    # Kill any existing process on the port
    $existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if ($existing) {
        foreach ($pid in $existing) {
            Write-Host "Killing existing process on port $Port (PID $pid)..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "Press Ctrl+C to stop."
    Write-Host ""

    # Launch the bridge
    python tools/claude_bridge.py
}
finally {
    Pop-Location
}
