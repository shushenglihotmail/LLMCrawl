# Start HiChat with Entra ID Authentication
# This script loads environment variables and starts HiChat

# Load environment variables from deploy/.env
$envFile = "..\..\deploy\.env"
if (Test-Path $envFile) {
    Write-Host "Loading environment from $envFile..." -ForegroundColor Green
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Remove quotes if present
            $value = $value -replace '^["'']|["'']$', ''
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            Write-Host "  Set $name" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

# Start HiChat (auth is always enabled)
Write-Host "Starting HiChat..." -ForegroundColor Cyan
python main.py
