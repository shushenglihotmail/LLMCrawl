<#
.SYNOPSIS
    LLMCrawl Build Script - Build wheel packages with various options.

.DESCRIPTION
    This script provides common build scenarios for the LLMCrawl project:
    - Normal build: Quick wheel build
    - Clean build: Remove artifacts and build fresh
    - Install build: Build and install locally
    - Release build: Clean build with version bump check

.PARAMETER Mode
    Build mode: Normal, Clean, Install, Release, Check
    - Normal:  Quick build (default)
    - Clean:   Remove artifacts, then build
    - Install: Build and install to current environment
    - Release: Clean build with version validation
    - Check:   Validate package without building

.PARAMETER NoBuild
    Skip the actual build (useful with Clean to just remove artifacts)

.PARAMETER Verbose
    Show detailed build output

.EXAMPLE
    .\scripts\build.ps1
    # Normal quick build

.EXAMPLE
    .\scripts\build.ps1 -Mode Clean
    # Clean all artifacts and rebuild

.EXAMPLE
    .\scripts\build.ps1 -Mode Install
    # Build and install locally

.EXAMPLE
    .\scripts\build.ps1 -Mode Clean -NoBuild
    # Just clean artifacts without building
#>

param(
    [ValidateSet("Normal", "Clean", "Install", "Release", "Check")]
    [string]$Mode = "Normal",
    
    [switch]$NoBuild,
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Colors for output
function Write-Header { param($msg) Write-Host "`n========================================" -ForegroundColor Cyan; Write-Host " $msg" -ForegroundColor Cyan; Write-Host "========================================`n" -ForegroundColor Cyan }
function Write-Step { param($msg) Write-Host "[*] $msg" -ForegroundColor Yellow }
function Write-Success { param($msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[!] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "    $msg" -ForegroundColor Gray }

# Change to project root
Set-Location $ProjectRoot

Write-Header "LLMCrawl Build Script"
Write-Info "Mode: $Mode"
Write-Info "Project: $ProjectRoot"

# Get current version from pyproject.toml
function Get-Version {
    $pyproject = Get-Content "pyproject.toml" -Raw
    if ($pyproject -match 'version\s*=\s*"([^"]+)"') {
        return $matches[1]
    }
    return "unknown"
}

# Clean build artifacts
function Clear-BuildArtifacts {
    Write-Step "Cleaning build artifacts..."
    
    $foldersToRemove = @(
        "build",
        "dist",
        "*.egg-info",
        ".eggs"
    )
    
    foreach ($folder in $foldersToRemove) {
        $paths = Get-ChildItem -Path $ProjectRoot -Filter $folder -Directory -ErrorAction SilentlyContinue
        foreach ($path in $paths) {
            Write-Info "Removing: $($path.FullName)"
            Remove-Item -Path $path.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    
    # Also check for egg-info in subdirectories
    $eggInfos = Get-ChildItem -Path $ProjectRoot -Filter "*.egg-info" -Directory -Recurse -ErrorAction SilentlyContinue
    foreach ($egg in $eggInfos) {
        Write-Info "Removing: $($egg.FullName)"
        Remove-Item -Path $egg.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Clean __pycache__ directories
    $pycaches = Get-ChildItem -Path $ProjectRoot -Filter "__pycache__" -Directory -Recurse -ErrorAction SilentlyContinue
    foreach ($cache in $pycaches) {
        Remove-Item -Path $cache.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    Write-Success "Build artifacts cleaned"
}

# Build wheel
function Build-Wheel {
    Write-Step "Building wheel..."
    
    $buildArgs = @("-m", "build", "--wheel")
    
    $result = & python @buildArgs 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed!"
        Write-Host $result -ForegroundColor Red
        exit 1
    }
    
    if ($VerboseOutput) {
        Write-Host $result
    }
    
    # Find the built wheel
    $wheel = Get-ChildItem -Path "dist" -Filter "*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($wheel) {
        Write-Success "Built: $($wheel.Name)"
        Write-Info "Size: $([math]::Round($wheel.Length / 1KB, 2)) KB"
        Write-Info "Path: $($wheel.FullName)"
        return $wheel.FullName
    }
    
    return $null
}

# Validate package
function Test-Package {
    Write-Step "Validating package..."
    
    # Check if twine is available
    $twineAvailable = $null -ne (Get-Command twine -ErrorAction SilentlyContinue)
    
    if ($twineAvailable) {
        $wheels = Get-ChildItem -Path "dist" -Filter "*.whl" -ErrorAction SilentlyContinue
        if ($wheels) {
            Write-Info "Running twine check..."
            & twine check dist/* 2>&1 | ForEach-Object { Write-Info $_ }
        }
    } else {
        Write-Info "Twine not available, skipping package validation"
        Write-Info "Install with: pip install twine"
    }
    
    # Check wheel contents
    $wheel = Get-ChildItem -Path "dist" -Filter "*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($wheel) {
        Write-Info "Wheel contents:"
        $tempDir = Join-Path $env:TEMP "wheel_check_$(Get-Random)"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        
        try {
            Expand-Archive -Path $wheel.FullName -DestinationPath $tempDir -Force
            $items = Get-ChildItem -Path $tempDir -Recurse -File | Group-Object { Split-Path (Split-Path $_.FullName -Parent) -Leaf }
            foreach ($group in $items | Sort-Object Name) {
                Write-Info "  $($group.Name): $($group.Count) files"
            }
        } finally {
            Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    
    Write-Success "Package validation complete"
}

# Install wheel locally
function Install-Wheel {
    param([string]$WheelPath)
    
    Write-Step "Installing wheel..."
    
    if (-not $WheelPath -or -not (Test-Path $WheelPath)) {
        $wheel = Get-ChildItem -Path "dist" -Filter "*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($wheel) {
            $WheelPath = $wheel.FullName
        } else {
            Write-Error "No wheel found to install"
            exit 1
        }
    }
    
    Write-Info "Installing: $WheelPath"
    & pip install --force-reinstall $WheelPath 2>&1 | ForEach-Object { 
        if ($VerboseOutput) { Write-Info $_ }
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Installation complete"
        
        # Verify installation
        Write-Info "Verifying installation..."
        $version = & llmcrawl --version 2>&1
        Write-Info "Installed version: $version"
    } else {
        Write-Error "Installation failed"
        exit 1
    }
}

# Check version consistency
function Test-Version {
    Write-Step "Checking version..."
    
    $version = Get-Version
    Write-Info "Version in pyproject.toml: $version"
    
    # Check if version looks like a release version
    if ($version -match '^\d+\.\d+\.\d+$') {
        Write-Success "Version format OK: $version"
    } elseif ($version -match '^\d+\.\d+\.\d+\.(dev|alpha|beta|rc)\d*$') {
        Write-Info "Pre-release version: $version"
    } else {
        Write-Info "Non-standard version format: $version"
    }
    
    return $version
}

# Main execution
$version = Get-Version
Write-Info "Version: $version"
Write-Host ""

switch ($Mode) {
    "Normal" {
        if (-not $NoBuild) {
            $wheelPath = Build-Wheel
        }
        Write-Success "Build complete!"
    }
    
    "Clean" {
        Clear-BuildArtifacts
        if (-not $NoBuild) {
            $wheelPath = Build-Wheel
        }
        Write-Success "Clean build complete!"
    }
    
    "Install" {
        Clear-BuildArtifacts
        $wheelPath = Build-Wheel
        Install-Wheel -WheelPath $wheelPath
        Write-Success "Build and install complete!"
    }
    
    "Release" {
        Write-Step "Release build..."
        $version = Test-Version
        Clear-BuildArtifacts
        $wheelPath = Build-Wheel
        Test-Package
        Write-Host ""
        Write-Success "Release build complete!"
        Write-Info "Wheel ready for distribution: $wheelPath"
        Write-Info ""
        Write-Info "Next steps:"
        Write-Info "  1. Test: pip install $wheelPath"
        Write-Info "  2. Upload: twine upload dist/*"
    }
    
    "Check" {
        Test-Version
        if (Test-Path "dist") {
            Test-Package
        } else {
            Write-Info "No dist folder - run a build first"
        }
        Write-Success "Check complete!"
    }
}

Write-Host ""
