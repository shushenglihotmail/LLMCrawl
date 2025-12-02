param (
    [Parameter(Mandatory=$true)]
    [string]$query,
    [string]$url = "http://localhost:8005",
    [int]$TimeoutSec = 300
)

$endpoint = "$url/query"
$body = @{
    query = $query
} | ConvertTo-Json

Write-Host "Sending query to $endpoint..."
Write-Host "Query: $query"

try {
    $response = Invoke-RestMethod -Uri $endpoint -Method Post -Body $body -ContentType "application/json" -TimeoutSec $TimeoutSec
    Write-Host "Response:" -ForegroundColor Green
    
    # The result might be a JSON string inside the JSON response, or just a string
    # The bridge returns {"result": "..."}
    
    if ($response.result) {
        Write-Host $response.result
    } else {
        Write-Host ($response | ConvertTo-Json -Depth 5)
    }
}
catch {
    Write-Error "Request failed: $_"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Error "Response Body: $responseBody"
    }
}
