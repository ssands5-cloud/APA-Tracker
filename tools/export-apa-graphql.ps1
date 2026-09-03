[CmdletBinding()]
param(
    [string]$HarPath = (Join-Path $env:USERPROFILE "Desktop\apa-network.har"),
    [string]$OutputPath = (Join-Path $env:USERPROFILE "Desktop\apa-graphql-requests.json")
)

<#
Pulls GraphQL request AND response bodies for known operations out of a
Chrome-exported HAR file, so they can be handed to Claude/Copilot without
ever sharing the HAR itself (which contains your live auth token/cookies
in the request headers).

Only these fields are ever written to $OutputPath:
  - operationName, variables, query   (from the request body)
  - response                          (the response body's JSON, decoded
                                        from base64 first if the HAR stored
                                        it that way)
No request or response HEADERS are read at all, so the auth token/cookies
never enter this script's output in the first place.

IMPORTANT: the response body itself can still contain your own name,
teammates' names, emails, or phone numbers if the portal returns them.
Skim apa-graphql-requests.json yourself before pasting it anywhere -- this
script only guarantees no *credentials* leak, not that the payload is fully
anonymous.
#>

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $HarPath -PathType Leaf)) {
    throw "HAR file not found: $HarPath. Save it from Chrome as 'HAR with content'."
}

$har = Get-Content -LiteralPath $HarPath -Raw | ConvertFrom-Json
$wantedOperations = @("teamPage", "teamRoster", "teamSchedule", "LeagueBox", "DivisionContacts")
$operations = [System.Collections.Generic.List[object]]::new()

function Get-ResponseBodies {
    param($response)

    $text = $response.content.text
    if ([string]::IsNullOrWhiteSpace($text)) {
        return @()
    }
    if ($response.content.encoding -eq "base64") {
        try {
            $text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($text))
        }
        catch {
            return @()
        }
    }
    try {
        return @($text | ConvertFrom-Json)
    }
    catch {
        # Not JSON (an error page, an empty body, etc.) -- not a GraphQL response.
        return @()
    }
}

foreach ($entry in @($har.log.entries)) {
    $request = $entry.request
    if ($request.url -notlike "*gql.poolplayers.com/graphql*") { continue }
    if ([string]::IsNullOrWhiteSpace($request.postData.text)) { continue }

    try {
        $requestBodies = @($request.postData.text | ConvertFrom-Json)
    }
    catch {
        continue
    }

    # Apollo can batch several operations into one HTTP call: the request
    # body and the response body are then both arrays, matched by position.
    $responseBodies = Get-ResponseBodies -response $entry.response

    for ($i = 0; $i -lt $requestBodies.Count; $i++) {
        $body = $requestBodies[$i]
        if ($body.operationName -notin $wantedOperations) { continue }

        $response = $null
        if ($i -lt $responseBodies.Count) {
            $response = $responseBodies[$i]
        }
        elseif ($responseBodies.Count -eq 1 -and $requestBodies.Count -eq 1) {
            $response = $responseBodies[0]
        }

        $operations.Add([ordered]@{
            operationName = $body.operationName
            variables     = $body.variables
            query         = $body.query
            response      = $response
        })
    }
}

if ($operations.Count -eq 0) {
    throw ("No {0} operations found. Capture the APA page(s) that issue them and save HAR with content." -f ($wantedOperations -join ", "))
}

$missing = $wantedOperations | Where-Object { $_ -notin $operations.operationName }

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

@($operations) | ConvertTo-Json -Depth 30 |
    Set-Content -LiteralPath $OutputPath -Encoding UTF8

Write-Host "Created: $OutputPath"
Write-Host "Operations found: $($operations.Count) ($(($operations.operationName | Select-Object -Unique) -join ', '))"
if ($missing) {
    Write-Host "Not captured this run: $($missing -join ', ') -- visit the page(s) that trigger those, then re-run."
}
Write-Host "Only operation names, variables, queries, and response bodies were written."
Write-Host "No request/response headers, cookies, or tokens were copied."
Write-Host "Review the response bodies for teammates' personal info before sharing this file."
