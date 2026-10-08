# Publish the private Match Night package to GitHub Pages (Phase 4D).
#   .\tools\publish_match_night.ps1                 # next fixture, asks for the passphrase (hidden)
#   .\tools\publish_match_night.ps1 -MatchId 51419770
#   .\tools\publish_match_night.ps1 -Demo           # synthetic demo package (no real data)
# Builds an encrypted one-fixture site and commits it to the gh-pages branch through a worktree inside the
# repository (.worktrees/gh-pages). No force-push: each publish is a normal commit. The passphrase is never
# printed or saved. See docs/match_night_deployment.md.
param(
    [string]$SourceDb = "C:\Users\ssand\Desktop\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging.db",
    [string]$MatchId = "",
    [switch]$Demo
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Site = Join-Path $Repo "tmp\match_night_site"
$Pages = Join-Path (git -C $Repo rev-parse --path-format=absolute --git-common-dir | Split-Path -Parent) ".worktrees\gh-pages"

if (Test-Path $Site) { Remove-Item $Site -Recurse -Force }
$argsList = @("scripts\build_match_night_package.py", "--out", $Site)
if ($Demo) { $argsList += "--demo" } else { $argsList += @("--db", $SourceDb) }
if ($MatchId) { $argsList += @("--match-id", $MatchId) }
Push-Location $Repo
try {
    $before = if ($Demo) { "" } else { (Get-FileHash $SourceDb -Algorithm SHA256).Hash }
    python @argsList
    if ($LASTEXITCODE -ne 0) { throw "Match Night package was not built." }
    if (-not $Demo -and (Get-FileHash $SourceDb -Algorithm SHA256).Hash -ne $before) { throw "Source DB changed during the build." }
} finally { Pop-Location }

git -C $Repo fetch origin gh-pages 2>$null
if (-not (Test-Path $Pages)) {
    $remote = git -C $Repo ls-remote --heads origin gh-pages
    if ($remote) { git -C $Repo worktree add $Pages gh-pages }
    else {
        git -C $Repo worktree add --detach $Pages
        git -C $Pages checkout --orphan gh-pages
        git -C $Pages rm -rf --quiet .
    }
}
git -C $Pages pull --ff-only origin gh-pages 2>$null
Get-ChildItem $Pages -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force
Copy-Item (Join-Path $Site "*") $Pages -Recurse -Force
Copy-Item (Join-Path $Site ".nojekyll") $Pages -Force
git -C $Pages add -A
$label = if ($Demo) { "DEMO (synthetic players)" } else { "private encrypted package" }
git -C $Pages commit -m "Publish Match Night $label ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))"
git -C $Pages push origin gh-pages
Write-Host ""
Write-Host "Published. Open https://ssands5-cloud.github.io/APA-Tracker/ on your phone (Pages can take a minute to update)."
