# Publish the private Match Night package to GitHub Pages (Phase 4D).
#   .\tools\publish_match_night.ps1                 # next fixture, asks for the passphrase (hidden)
#   .\tools\publish_match_night.ps1 -MatchId 51419770
#   .\tools\publish_match_night.ps1 -Demo           # synthetic demo package (no real data)
# All safety checks (canonical repo/origin, exact folders, clean allowlisted gh-pages worktree, fail-closed
# git) live in scripts/publish_match_night.py and run before anything is built, deleted or copied.
param(
    [string]$SourceDb = "C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db",
    [string]$MatchId = "",
    [switch]$Demo
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$argsList = @((Join-Path $Repo "scripts\publish_match_night.py"))
if ($Demo) { $argsList += "--demo" } else {
    $before = (Get-FileHash -LiteralPath $SourceDb -Algorithm SHA256).Hash
    $argsList += @("--db", $SourceDb)
}
if ($MatchId) { $argsList += @("--match-id", $MatchId) }
python @argsList
$code = $LASTEXITCODE
if (-not $Demo -and (Get-FileHash -LiteralPath $SourceDb -Algorithm SHA256).Hash -ne $before) { throw "Source DB changed during the build." }
if ($code -ne 0) { throw "Not published (see the reason above)." }
