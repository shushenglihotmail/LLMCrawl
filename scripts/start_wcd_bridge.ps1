<#
.SYNOPSIS
    Starts the Windows Composition Bridge service.

.DESCRIPTION
    Sets the WIN_COMP_SHARE_CMD or WIN_COMP_PS_COMMAND environment variable and
    launches the windows_composition_bridge.py tool in a new detached process.

    Supports two modes:
    1. Network share mode: Uses -WinCompShareCmd to point to a build share
    2. WCDaaS local mode: Uses -UseWcdaasLocal with -Branch and -BuildName

.PARAMETER WinCompShareCmd
    The base path to the Windows build release folder
    (e.g., \\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700).
    The script will automatically append the architecture and SDK path.

.PARAMETER Arch
    The architecture folder name. Default is "amd64fre".
    Other examples: "arm64fre", "x86fre", etc.

.PARAMETER UseWcdaasLocal
    Use existing WCDaaS local download from %LOCALAPPDATA%\Temp\wcdaas.
    Requires -Branch and -BuildName parameters.
    Run the WCDaaS URL in a browser first to download the tools.

.PARAMETER Branch
    WCD branch name (default: rs_sparc_ctr_exp). Required for -UseWcdaasLocal.

.PARAMETER BuildName
    WCD build name (e.g., 29503.1000.251209-1700). Required for -UseWcdaasLocal.

.EXAMPLE
    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700"

.EXAMPLE
    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700" -Arch "arm64fre"

.EXAMPLE
    .\start_wcd_bridge.ps1 -UseWcdaasLocal -Branch rs_sparc_ctr_exp -BuildName 29503.1000.251209-1700

.EXAMPLE
    .\start_wcd_bridge.ps1 -UseWcdaasLocal -Branch rs_sparc_ctr_exp -BuildName 29503.1000.251209-1700 -Arch arm64fre
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$WinCompShareCmd,

    [Parameter(Mandatory=$false)]
    [string]$Arch = "amd64fre",

    [Parameter(Mandatory=$false)]
    [switch]$UseWcdaasLocal,

    [Parameter(Mandatory=$false)]
    [string]$Branch = "rs_sparc_ctr_exp",

    [Parameter(Mandatory=$false)]
    [string]$BuildName
)

# Validate parameters
if (-not $UseWcdaasLocal -and -not $WinCompShareCmd) {
    Write-Error "Either -WinCompShareCmd or -UseWcdaasLocal must be specified"
    Write-Host ""
    Write-Host "Usage examples:" -ForegroundColor Yellow
    Write-Host "  Network share mode:"
    Write-Host '    .\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700"'
    Write-Host ""
    Write-Host "  WCDaaS local mode:"
    Write-Host '    .\start_wcd_bridge.ps1 -UseWcdaasLocal -Branch rs_sparc_ctr_exp -BuildName 29503.1000.251209-1700'
    exit 1
}

if ($UseWcdaasLocal -and -not $BuildName) {
    Write-Error "-BuildName is required when using -UseWcdaasLocal"
    Write-Host "Example: -BuildName 29503.1000.251209-1700"
    exit 1
}

# Get the absolute path to the bridge tool
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ToolPath = Join-Path $ScriptDir "..\tools\windows_composition_bridge.py"

if (-not (Test-Path $ToolPath)) {
    Write-Error "Bridge tool not found at: $ToolPath"
    exit 1
}

$ToolPath = (Resolve-Path $ToolPath).Path

if ($UseWcdaasLocal) {
    # WCDaaS local mode
    $WcdaasBase = Join-Path $env:LOCALAPPDATA "Temp\wcdaas"

    if (-not (Test-Path $WcdaasBase)) {
        $WcdaasUrl = "https://wcdaas-pme.azurewebsites.net/default.aspx?action=wcd&branch=$Branch&buildName=$BuildName&arch=amd64"
        Write-Error "WCDaaS temp folder not found: $WcdaasBase"
        Write-Host ""
        Write-Host "Run the WCDaaS URL in a browser first to download the tools:" -ForegroundColor Yellow
        Write-Host "  $WcdaasUrl"
        exit 1
    }

    # Find valid folders containing InteractViaPowershell.ps1
    $ValidFolders = Get-ChildItem -Path $WcdaasBase -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName "InteractViaPowershell.ps1")
    } | Sort-Object LastWriteTime -Descending

    if ($ValidFolders.Count -eq 0) {
        Write-Error "No valid WCDaaS folders found in $WcdaasBase"
        Write-Host "Valid folders must contain InteractViaPowershell.ps1"
        exit 1
    }

    $WcdaasFolder = $ValidFolders[0].FullName
    Write-Host "Using WCDaaS folder: $($ValidFolders[0].Name) (found $($ValidFolders.Count) valid)" -ForegroundColor Green

    # Construct PowerShell command
    $Ps1Path = Join-Path $WcdaasFolder "InteractViaPowershell.ps1"
    $ArchShort = $Arch -replace "fre|chk", ""
    $PsCommand = "& '$Ps1Path' -branch $Branch -buildName $BuildName -arch $ArchShort"

    # Set environment variable
    $env:WIN_COMP_PS_COMMAND = $PsCommand

    Write-Host "Configuration (WCDaaS Local):" -ForegroundColor Cyan
    Write-Host "  Branch:         $Branch"
    Write-Host "  Build Name:     $BuildName"
    Write-Host "  Architecture:   $ArchShort"
    Write-Host "  Folder:         $WcdaasFolder"
    Write-Host "  Tool Path:      $ToolPath"
}
else {
    # Network share mode
    # Construct the full path to InteractViaPowerShell.cmd
    $FullWinCompShareCmd = Join-Path $WinCompShareCmd $Arch
    $FullWinCompShareCmd = Join-Path $FullWinCompShareCmd "WindowsCompositionData\SDK\InteractViaPowerShell.cmd"

    # Set the environment variable
    $env:WIN_COMP_SHARE_CMD = $FullWinCompShareCmd

    Write-Host "Configuration:" -ForegroundColor Cyan
    Write-Host "  Base Path:          $WinCompShareCmd"
    Write-Host "  Architecture:       $Arch"
    Write-Host "  Full CMD Path:      $FullWinCompShareCmd"
    Write-Host "  Tool Path:          $ToolPath"
}

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
