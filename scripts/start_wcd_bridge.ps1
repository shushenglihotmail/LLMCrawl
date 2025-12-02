<#
.SYNOPSIS
    Starts the Windows Composition Bridge service.

.DESCRIPTION
    Sets the WIN_COMP_SHARE_CMD environment variable and launches the
    windows_composition_bridge.py tool in a new detached process.

.PARAMETER WinCompShareCmd
    The path to the initialization command (e.g., \\server\share\InteractViaPowerShell.cmd).

.EXAMPLE
    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\server\share\InteractViaPowerShell.cmd"
#>

param (
    [Parameter(Mandatory=$true)]
    [string]$WinCompShareCmd
)

# Get the absolute path to the bridge tool
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ToolPath = Join-Path $ScriptDir "..\tools\windows_composition_bridge.py"

if (-not (Test-Path $ToolPath)) {
    Write-Error "Bridge tool not found at: $ToolPath"
    exit 1
}

$ToolPath = (Resolve-Path $ToolPath).Path

Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  WIN_COMP_SHARE_CMD: $WinCompShareCmd"
Write-Host "  Tool Path:          $ToolPath"

# Set the environment variable for the current session so Start-Process inherits it
$env:WIN_COMP_SHARE_CMD = $WinCompShareCmd

# Launch the bridge service in a new window
try {
    Write-Host "Launching bridge service..." -ForegroundColor Cyan
    $process = Start-Process -FilePath "python" -ArgumentList "`"$ToolPath`"" -PassThru

    if ($process) {
        Write-Host "Successfully launched Windows Composition Bridge (PID: $($process.Id))." -ForegroundColor Green
        Write-Host "The service is running in a separate window on port 8005."
    }
}
catch {
    Write-Error "Failed to start the bridge service: $_"
}
