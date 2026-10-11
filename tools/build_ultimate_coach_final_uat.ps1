param(
    [string]$SourceDb = "C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db",
    [string]$DestinationRoot = (Join-Path $PSScriptRoot "..\tmp\uat")
)

$ErrorActionPreference = "Stop"

function Get-Sha256WithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Attempts = 30,
        [int]$DelaySeconds = 2
    )

    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            return (Get-FileHash $Path -Algorithm SHA256 -ErrorAction Stop).Hash
        }
        catch {
            if ($i -eq $Attempts) {
                throw "Could not read SHA256 for '$Path' after $Attempts attempts. Last error: $($_.Exception.Message)"
            }
            Write-Host "Source DB temporarily busy; retrying SHA256 ($i/$Attempts)..." -ForegroundColor Yellow
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Branch = "integration/ultimate-coach-pr81-pr82-reconciliation"

Write-Host ""
Write-Host "=== ULTIMATE COACH FINAL UAT BUILD ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# Outputs stay inside the canonical APA-Tracker folder (Paul, 2026-10-08). scripts/repo_boundary.py checks
# the canonical common .git AND origin, then walks every path component from the canonical root and refuses
# any symlink/junction/reparse point, then requires final resolved containment (GPT audit #84: a string
# prefix check passes an inside-looking path routed through a junction). Run before the fetch and again
# immediately before every create, delete, move, copy and write below.
$BoundaryCheck = Join-Path $RepoRoot "scripts\repo_boundary.py"
function Assert-OutputInsideCanonical {
    param([Parameter(Mandatory = $true)][string[]]$Paths)
    $checkArgs = @($BoundaryCheck, "check-output", "--repo", $RepoRoot)
    foreach ($p in $Paths) { $checkArgs += @("--dest", $p) }
    & python @checkArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Output path refused (reason above). Nothing further was fetched, created, deleted or copied." }
}
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
Assert-OutputInsideCanonical -Paths @($DestinationRoot)
Write-Host "Destination: $DestinationRoot"

git -C $RepoRoot fetch origin $Branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

$LocalHead = (git -C $RepoRoot rev-parse HEAD).Trim()
$RemoteHead = (git -C $RepoRoot rev-parse "origin/$Branch").Trim()

Write-Host "Local head : $LocalHead"
Write-Host "Remote head: $RemoteHead"

if ($LocalHead -ne $RemoteHead) {
    throw "This worktree is not on the latest PR #83 head. Update it first, then rerun this helper."
}

$Dirty = git -C $RepoRoot status --porcelain
if ($Dirty) {
    Write-Host $Dirty
    throw "Worktree has local changes. Nothing will be built until the tree is clean."
}

if (-not (Test-Path $SourceDb -PathType Leaf)) {
    throw "Source DB not found: $SourceDb"
}

$ShortHead = $LocalHead.Substring(0,7)
$BuildRoot = Join-Path $DestinationRoot ("build-" + $ShortHead)
$TempRoot = Join-Path $DestinationRoot (".build-" + $ShortHead + "-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

Assert-OutputInsideCanonical -Paths @($DestinationRoot, $BuildRoot, $TempRoot)
New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

# The production builder intentionally refuses to write into a pre-existing
# output directory. Reserve only the parent here; let the builder create
# $TempRoot atomically. If a stale temp folder somehow exists from a prior
# interrupted attempt, remove that temp-only path before starting.
if (Test-Path $TempRoot) {
    Remove-Item $TempRoot -Recurse -Force
}

$Before = Get-Sha256WithRetry -Path $SourceDb
$DbSize = (Get-Item $SourceDb).Length

Write-Host ""
Write-Host "Source DB: $SourceDb"
Write-Host "Size     : $DbSize bytes"
Write-Host "SHA256   : $Before"

Assert-OutputInsideCanonical -Paths @($TempRoot)
Push-Location $RepoRoot
try {
    Write-Host ""
    Write-Host "=== BUILDING HTML ===" -ForegroundColor Cyan
    python scripts/build_ultimate_coach_production.py --db "$SourceDb" --out "$TempRoot"
    if ($LASTEXITCODE -ne 0) { throw "HTML production build failed with exit code $LASTEXITCODE" }

    Write-Host ""
    Write-Host "=== BUILDING EXCEL ===" -ForegroundColor Cyan
    Assert-OutputInsideCanonical -Paths @($TempRoot)   # the HTML build took minutes: re-check before writing again
    python scripts/build_ultimate_coach_excel.py --db "$SourceDb" --output "$TempRoot\Ultimate_Coach_FINAL_UAT.xlsx"
    if ($LASTEXITCODE -ne 0) { throw "Excel build failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$After = Get-Sha256WithRetry -Path $SourceDb
if ($Before -ne $After) {
    throw "Source DB hash changed during the build. Candidate NOT promoted to the UAT folder."
}

# Was the source a refreshed copy, and is it accepted current data? (GPT audit 056dae6: a partial refresh must
# never pass as current.) Recorded in UAT_MANIFEST.json; read-only, no network.
$RefreshJson = & python (Join-Path $RepoRoot "scripts\refresh_ultimate_coach_current_session.py") --describe-source $SourceDb
if ($LASTEXITCODE -ne 0) { throw "Could not describe the source DB's refresh provenance." }
$SourceRefresh = $RefreshJson | ConvertFrom-Json

$GeneratedHtml = Join-Path $TempRoot "ultimate_coach.html"
$GeneratedXlsx = Join-Path $TempRoot "Ultimate_Coach_FINAL_UAT.xlsx"

if (-not (Test-Path $GeneratedHtml -PathType Leaf)) { throw "Generated HTML is missing." }
if (-not (Test-Path $GeneratedXlsx -PathType Leaf)) { throw "Generated Excel workbook is missing." }

Assert-OutputInsideCanonical -Paths @($TempRoot, $BuildRoot)
Copy-Item $GeneratedHtml (Join-Path $TempRoot "Ultimate_Coach_FINAL_UAT.html") -Force

if (Test-Path $BuildRoot) {
    Remove-Item $BuildRoot -Recurse -Force
}
Move-Item $TempRoot $BuildRoot

$FinalHtml = Join-Path $BuildRoot "Ultimate_Coach_FINAL_UAT.html"
$FinalXlsx = Join-Path $BuildRoot "Ultimate_Coach_FINAL_UAT.xlsx"

Assert-OutputInsideCanonical -Paths @($DestinationRoot, $BuildRoot)
Copy-Item $FinalHtml (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.html") -Force
Copy-Item $FinalXlsx (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.xlsx") -Force

$HtmlHash = (Get-FileHash $FinalHtml -Algorithm SHA256).Hash
$XlsxHash = (Get-FileHash $FinalXlsx -Algorithm SHA256).Hash

# The production builder's own manifest pins the HTML it rendered; the copy
# handed to UAT must be byte-identical to it.
$ProductionManifest = Get-Content (Join-Path $BuildRoot "manifest.json") -Raw | ConvertFrom-Json
if ($ProductionManifest.html_sha256.ToUpper() -ne $HtmlHash) {
    throw "UAT HTML does not match the production manifest's html_sha256."
}

# One manifest covering BOTH UAT artifacts, so a tester can verify exactly
# what they opened. The viewer identity itself is deliberately not recorded.
$UatManifest = [ordered]@{
    schema = "ultimate-coach-final-uat-v1"
    pr_head = $LocalHead
    built_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    source_database = $SourceDb
    source_database_bytes = $DbSize
    source_database_sha256_before = $Before
    source_database_sha256_after = $After
    source_database_unchanged = ($Before -eq $After)
    source_refresh = $SourceRefresh
    match_day = $ProductionManifest.match_day
    artifacts = @(
        [ordered]@{ file = "Ultimate_Coach_FINAL_UAT.html"; bytes = (Get-Item $FinalHtml).Length; sha256 = $HtmlHash },
        [ordered]@{ file = "Ultimate_Coach_FINAL_UAT.xlsx"; bytes = (Get-Item $FinalXlsx).Length; sha256 = $XlsxHash }
    )
}
Assert-OutputInsideCanonical -Paths @($BuildRoot)
$UatManifest | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $BuildRoot "UAT_MANIFEST.json") -Encoding UTF8

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "ULTIMATE COACH FINAL UAT PACKAGE READY" -ForegroundColor Green
Write-Host "============================================"
Write-Host "PR #83 head : $LocalHead"
Write-Host "Source DB unchanged: YES"
if ($SourceRefresh.accepted_current_data) {
    Write-Host "Source data: refreshed, coverage COMPLETE for its scope ($($SourceRefresh.finished_utc))" -ForegroundColor Green
} elseif ($SourceRefresh.refreshed) {
    Write-Host "WARNING: source is a refreshed copy that is NOT accepted current data (coverage $($SourceRefresh.coverage), $($SourceRefresh.gaps) gap(s), report matches DB: $($SourceRefresh.report_matches_db)). See UAT_MANIFEST.json source_refresh." -ForegroundColor Yellow
} else {
    Write-Host "Note: source DB was not refreshed (no refresh_report.json); results end at its latest recorded result." -ForegroundColor Yellow
}
Write-Host "Manifest : $(Join-Path $BuildRoot 'UAT_MANIFEST.json')"
Write-Host ""
Write-Host "HTML : $FinalHtml"
Write-Host "SHA256: $HtmlHash"
Write-Host ""
Write-Host "Excel: $FinalXlsx"
Write-Host "SHA256: $XlsxHash"
Write-Host ""
Write-Host "Friendly copies (in the UAT folder):"
Write-Host (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.html")
Write-Host (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.xlsx")
