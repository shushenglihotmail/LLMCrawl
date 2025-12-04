<#
.SYNOPSIS
    Starts the Windows Composition Bridge service.

.DESCRIPTION
    Sets the WIN_COMP_SHARE_CMD environment variable and launches the
    windows_composition_bridge.py tool in a new detached process.

.PARAMETER WinCompShareCmd
    The base path to the Windows build release folder
    (e.g., \\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700).
    The script will automatically append the architecture and SDK path.

.PARAMETER Arch
    The architecture folder name. Default is "amd64fre".
    Other examples: "arm64fre", "x86fre", etc.

.EXAMPLE
    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700"

.EXAMPLE
    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700" -Arch "arm64fre"
#>

param (
    [Parameter(Mandatory=$true)]
    [string]$WinCompShareCmd,

    [Parameter(Mandatory=$false)]
    [string]$Arch = "amd64fre"
)

# Construct the full path to InteractViaPowerShell.cmd
$FullWinCompShareCmd = Join-Path $WinCompShareCmd $Arch
$FullWinCompShareCmd = Join-Path $FullWinCompShareCmd "WindowsCompositionData\SDK\InteractViaPowerShell.cmd"

# Get the absolute path to the bridge tool
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ToolPath = Join-Path $ScriptDir "..\tools\windows_composition_bridge.py"

if (-not (Test-Path $ToolPath)) {
    Write-Error "Bridge tool not found at: $ToolPath"
    exit 1
}

$ToolPath = (Resolve-Path $ToolPath).Path

Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Base Path:          $WinCompShareCmd"
Write-Host "  Architecture:       $Arch"
Write-Host "  Full CMD Path:      $FullWinCompShareCmd"
Write-Host "  Tool Path:          $ToolPath"

# Set the environment variable for the current session so Start-Process inherits it
$env:WIN_COMP_SHARE_CMD = $FullWinCompShareCmd

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
