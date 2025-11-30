#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Check health of all LLMCrawl services with formatted output
#>

$ErrorActionPreference = "SilentlyContinue"

function Write-ServiceHealth {
    param(
        [string]$ServiceName,
        [string]$Url,
        [int]$Port
    )

    Write-Host ""
    Write-Host "$ServiceName " -NoNewline -ForegroundColor Cyan
    Write-Host "(port $Port)" -ForegroundColor DarkGray
    Write-Host ("=" * 50) -ForegroundColor DarkGray

    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        $status = $response.status

        if ($status -eq "healthy") {
            Write-Host "  Status: " -NoNewline
            Write-Host "[OK] HEALTHY" -ForegroundColor Green
        }
        else {
            Write-Host "  Status: " -NoNewline
            Write-Host "[!] $status" -ForegroundColor Yellow
        }

        # Show service name if available
        if ($response.service) {
            Write-Host "  Service: $($response.service)" -ForegroundColor White
        }

        # Show components if available (crawler has nested components)
        if ($response.components) {
            Write-Host "  Components:" -ForegroundColor White
            foreach ($comp in $response.components.PSObject.Properties) {
                $compStatus = $comp.Value.status
                $statusColor = if ($compStatus -eq "healthy") { "Green" } else { "Yellow" }
                Write-Host "    - $($comp.Name): " -NoNewline
                Write-Host $compStatus -ForegroundColor $statusColor
            }
        }

        # Show vector store info (indexer)
        if ($response.vector_store) {
            $vsStatus = $response.vector_store.status
            $statusColor = if ($vsStatus -eq "healthy") { "Green" } else { "Yellow" }
            Write-Host "  Vector Store: " -NoNewline
            Write-Host $vsStatus -ForegroundColor $statusColor
            if ($response.vector_store.collections) {
                Write-Host "    Collections: $($response.vector_store.collections)"
            }
        }

        # Show embedding model (indexer)
        if ($response.embedding_model) {
            $emHealthy = $response.embedding_model.healthy
            $statusColor = if ($emHealthy) { "Green" } else { "Yellow" }
            $statusIcon = if ($emHealthy) { "[OK]" } else { "[X]" }
            Write-Host "  Embedding: " -NoNewline
            Write-Host $statusIcon -ForegroundColor $statusColor -NoNewline
            Write-Host " $($response.embedding_model.model)" -ForegroundColor White
        }

        return $true
    }
    catch {
        Write-Host "  Status: " -NoNewline
        Write-Host "[X] UNREACHABLE" -ForegroundColor Red
        Write-Host "  Error: Connection failed" -ForegroundColor DarkGray
        return $false
    }
}

function Write-SimpleHealth {
    param(
        [string]$ServiceName,
        [string]$Url,
        [int]$Port
    )

    Write-Host ""
    Write-Host "$ServiceName " -NoNewline -ForegroundColor Cyan
    Write-Host "(port $Port)" -ForegroundColor DarkGray
    Write-Host ("=" * 50) -ForegroundColor DarkGray

    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        Write-Host "  Status: " -NoNewline
        Write-Host "[OK] HEALTHY" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "  Status: " -NoNewline
        Write-Host "[X] UNREACHABLE" -ForegroundColor Red
        return $false
    }
}

# Header
Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "          LLMCrawl Service Health Check               " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$healthy = 0
$total = 0

# Check each service
$total++; if (Write-ServiceHealth "Gateway" "http://localhost:8000/health" 8000) { $healthy++ }
$total++; if (Write-ServiceHealth "Crawler" "http://localhost:8001/health" 8001) { $healthy++ }
$total++; if (Write-ServiceHealth "Indexer" "http://localhost:8002/health" 8002) { $healthy++ }
$total++; if (Write-SimpleHealth "MCP Server" "http://localhost:8003/health" 8003) { $healthy++ }
$total++; if (Write-SimpleHealth "Azure DevOps MCP" "http://localhost:8004/health" 8004) { $healthy++ }
$total++; if (Write-SimpleHealth "Qdrant" "http://localhost:6333/healthz" 6333) { $healthy++ }
$total++; if (Write-SimpleHealth "Playwright" "http://localhost:3000/json/version" 3000) { $healthy++ }

# Summary
Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
$summaryColor = if ($healthy -eq $total) { "Green" } elseif ($healthy -gt 0) { "Yellow" } else { "Red" }
Write-Host "  Summary: " -NoNewline
Write-Host "$healthy/$total services healthy" -ForegroundColor $summaryColor
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
