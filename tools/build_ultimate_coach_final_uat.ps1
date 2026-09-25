param(
    [string]$SourceDb = "C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db",
    [string]$DestinationRoot = "$env:USERPROFILE\Desktop\Ultimate Coach FINAL UAT"
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

Push-Location $RepoRoot
try {
    Write-Host ""
    Write-Host "=== BUILDING HTML ===" -ForegroundColor Cyan
    python scripts/build_ultimate_coach_production.py --db "$SourceDb" --out "$TempRoot"
    if ($LASTEXITCODE -ne 0) { throw "HTML production build failed with exit code $LASTEXITCODE" }

    Write-Host ""
    Write-Host "=== BUILDING EXCEL ===" -ForegroundColor Cyan
    python scripts/build_ultimate_coach_excel.py --db "$SourceDb" --output "$TempRoot\Ultimate_Coach_FINAL_UAT.xlsx"
    if ($LASTEXITCODE -ne 0) { throw "Excel build failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$After = Get-Sha256WithRetry -Path $SourceDb
if ($Before -ne $After) {
    throw "Source DB hash changed during the build. Candidate NOT promoted to the Desktop UAT folder."
}

$GeneratedHtml = Join-Path $TempRoot "ultimate_coach.html"
$GeneratedXlsx = Join-Path $TempRoot "Ultimate_Coach_FINAL_UAT.xlsx"

if (-not (Test-Path $GeneratedHtml -PathType Leaf)) { throw "Generated HTML is missing." }
if (-not (Test-Path $GeneratedXlsx -PathType Leaf)) { throw "Generated Excel workbook is missing." }

Copy-Item $GeneratedHtml (Join-Path $TempRoot "Ultimate_Coach_FINAL_UAT.html") -Force

if (Test-Path $BuildRoot) {
    Remove-Item $BuildRoot -Recurse -Force
}
Move-Item $TempRoot $BuildRoot

$FinalHtml = Join-Path $BuildRoot "Ultimate_Coach_FINAL_UAT.html"
$FinalXlsx = Join-Path $BuildRoot "Ultimate_Coach_FINAL_UAT.xlsx"

Copy-Item $FinalHtml (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.html") -Force
Copy-Item $FinalXlsx (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.xlsx") -Force

$HtmlHash = (Get-FileHash $FinalHtml -Algorithm SHA256).Hash
$XlsxHash = (Get-FileHash $FinalXlsx -Algorithm SHA256).Hash

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "ULTIMATE COACH FINAL UAT PACKAGE READY" -ForegroundColor Green
Write-Host "============================================"
Write-Host "PR #83 head : $LocalHead"
Write-Host "Source DB unchanged: YES"
Write-Host ""
Write-Host "HTML : $FinalHtml"
Write-Host "SHA256: $HtmlHash"
Write-Host ""
Write-Host "Excel: $FinalXlsx"
Write-Host "SHA256: $XlsxHash"
Write-Host ""
Write-Host "Friendly Desktop copies:"
Write-Host (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.html")
Write-Host (Join-Path $DestinationRoot "Ultimate_Coach_FINAL_UAT.xlsx")
