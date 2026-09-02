[CmdletBinding()]
param(
    [string]$HarPath = (Join-Path $env:USERPROFILE "Desktop\apa-network.har"),
    [string]$OutputPath = (Join-Path $env:USERPROFILE "Desktop\apa-graphql-requests.json")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $HarPath -PathType Leaf)) {
    throw "HAR file not found: $HarPath. Save it from Chrome as 'HAR with content'."
}

$har = Get-Content -LiteralPath $HarPath -Raw | ConvertFrom-Json
$wantedOperations = @("teamPage", "teamRoster", "teamSchedule")
$operations = [System.Collections.Generic.List[object]]::new()

foreach ($entry in @($har.log.entries)) {
    $request = $entry.request
    if ($request.url -notlike "*gql.poolplayers.com/graphql*") { continue }
    if ([string]::IsNullOrWhiteSpace($request.postData.text)) { continue }

    try {
        $bodies = @($request.postData.text | ConvertFrom-Json)
    }
    catch {
        continue
    }

    foreach ($body in $bodies) {
        if ($body.operationName -notin $wantedOperations) { continue }
        $operations.Add([ordered]@{
            operationName = $body.operationName
            variables = $body.variables
            query = $body.query
        })
    }
}

if ($operations.Count -eq 0) {
    throw "No teamPage, teamRoster, or teamSchedule operations found. Capture the APA team page and save HAR with content."
}

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

@($operations) | ConvertTo-Json -Depth 30 |
    Set-Content -LiteralPath $OutputPath -Encoding UTF8

Write-Host "Created: $OutputPath"
Write-Host "Operations found: $($operations.Count)"
Write-Host "Only operation names, variables, and queries were written."
Write-Host "No request headers, cookies, tokens, or response bodies were copied."
