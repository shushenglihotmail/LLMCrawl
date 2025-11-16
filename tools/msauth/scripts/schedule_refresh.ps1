# Schedule Authentication Refresh for www.osgwiki.com
# Run this script to create a scheduled task that checks auth daily

param(
    [string]$TaskName = "LLMCrawl-RefreshOSGWikiAuth",
    [string]$Time = "02:00",  # 2 AM daily
    [string]$WorkingDir = $PSScriptRoot + "\.."
)

$Action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument `
    "-File `"$WorkingDir\tools\run_refresh_auth.ps1`"" -WorkingDirectory $WorkingDir

$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U

Write-Host "Creating scheduled task: $TaskName" -ForegroundColor Cyan
Write-Host "  Runs daily at: $Time" -ForegroundColor Yellow
Write-Host "  Working directory: $WorkingDir" -ForegroundColor Yellow

try {
    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Force

    Write-Host "`n✅ Scheduled task created successfully!" -ForegroundColor Green
    Write-Host "`nTo manage the task:" -ForegroundColor Cyan
    Write-Host "  View:   Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Run:    Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Remove: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
}
catch {
    Write-Error "Failed to create scheduled task: $_"
    exit 1
}
