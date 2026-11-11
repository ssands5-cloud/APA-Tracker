[CmdletBinding()]
param(
    [string]$Repository = 'D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker',
    [string]$LogRoot,
    [switch]$Scheduled,
    [switch]$TestFailure,
    [switch]$SkipNotifications,
    [ValidateRange(1, 180)][int]$TimeoutMinutes = 90
)
$ErrorActionPreference = 'Stop'
$Repository = (Resolve-Path -LiteralPath $Repository).Path
if (-not $LogRoot) { $LogRoot = Join-Path $Repository 'ultimate-coach-runs\refresh' }
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$runFolder = Join-Path $LogRoot ('scheduled-' + $runId)
New-Item -ItemType Directory -Path $runFolder | Out-Null
Set-Content -LiteralPath (Join-Path $runFolder 'runner.log') -Value ("Started UTC: " + [DateTime]::UtcNow.ToString('o') + [Environment]::NewLine + 'Repository: ' + $Repository) -Encoding UTF8
Set-Content -LiteralPath (Join-Path $runFolder 'stdout.log') -Value '' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $runFolder 'stderr.log') -Value '' -Encoding UTF8
if (Test-Path -LiteralPath (Join-Path $LogRoot 'REFRESH_STATUS.txt')) { Copy-Item -LiteralPath (Join-Path $LogRoot 'REFRESH_STATUS.txt') -Destination (Join-Path $runFolder 'previous-status.txt') }
$result = [ordered]@{ run_id=$runId; started_utc=[DateTime]::UtcNow.ToString('o'); status='Running'; exit_code=1; repository=$Repository; log_folder=$runFolder; reason=$null; alerts=@() }
$exitCode = 1
try {
    if ($TestFailure) { throw 'Synthetic failure test; APA was not contacted and the refresh was not launched.' }
    $top = (& git -C $Repository rev-parse --show-toplevel).Trim().Replace('/', '\')
    if ($LASTEXITCODE -ne 0 -or $top -ne $Repository.TrimEnd('\')) { throw 'Repository boundary mismatch.' }
    $origin = (& git -C $Repository remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $origin -ne 'https://github.com/ssands5-cloud/APA-Tracker.git') { throw 'Unexpected Git origin; refresh refused.' }
    $common = & git -C $Repository rev-parse --path-format=absolute --git-common-dir
    if ($LASTEXITCODE -ne 0 -or $common.Replace('/', '\') -ne (Join-Path $Repository '.git')) { throw 'Git common directory mismatch; refresh refused.' }
    if ((Get-Content -LiteralPath (Join-Path $Repository '.repo-boundary-id') -Raw).Trim() -ne 'apa-tracker') { throw 'Repository marker mismatch; refresh refused.' }
    # The existing pipeline launches a headed APA browser and native Excel.
    # Do not silently attempt that workflow in a logged-out batch session.
    if ($Scheduled) { throw 'Unattended refresh is not validated: current APA sign-in requires a browser and Enter, and workbook validation requires desktop Excel. Task must remain disabled until both are addressed.' }
    $batch = Join-Path $Repository 'QUICK_REFRESH.bat'
    if (-not (Test-Path -LiteralPath $batch -PathType Leaf)) { throw 'QUICK_REFRESH.bat is missing.' }
    $oldPause = $env:APA_REFRESH_NO_PAUSE
    try {
        $env:APA_REFRESH_NO_PAUSE = '1'
        $command = '""{0}" --no-open"' -f $batch
        $process = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList @('/d','/s','/c',$command) -WorkingDirectory $Repository -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runFolder 'stdout.log') -RedirectStandardError (Join-Path $runFolder 'stderr.log')
        if (-not $process.WaitForExit($TimeoutMinutes * 60000)) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
            throw 'Refresh exceeded its time limit. Inspect the refresh lock before retrying; it was not removed automatically.'
        }
        $process.Refresh()
        $exitCode = $process.ExitCode
        if ($exitCode -ne 0) { throw "QUICK_REFRESH.bat returned exit code $exitCode. Inspect the local logs." }
        $result.status = 'Success'
    } finally { $env:APA_REFRESH_NO_PAUSE = $oldPause }
} catch {
    $result.status = 'Failed'
    $result.reason = $_.Exception.Message
    Add-Content -LiteralPath (Join-Path $runFolder 'runner.log') -Value ('FAILED: ' + $result.reason) -Encoding UTF8
    if ($exitCode -eq 0) { $exitCode = 1 }

} finally {
    $result.exit_code = $exitCode
    $result.finished_utc = [DateTime]::UtcNow.ToString('o')
    if ($result.status -eq 'Failed') {
        # Persist the marker before emitting the event that triggers the popup.
        $json = $result | ConvertTo-Json -Depth 5
        Set-Content -LiteralPath (Join-Path $LogRoot 'FAILED.json') -Value $json -Encoding UTF8
        $status = 'FAILED: scheduled QUICK refresh ' + $runId + [Environment]::NewLine + $result.reason + [Environment]::NewLine + 'Logs: ' + $runFolder
        Set-Content -LiteralPath (Join-Path $LogRoot 'REFRESH_STATUS.txt') -Value $status -Encoding UTF8
        if (-not $SkipNotifications) {
            $message = "Ultimate Coach QUICK refresh failed. Run: $runId. Logs: $runFolder. Open result.json for details."
            try {
                [System.Diagnostics.EventLog]::WriteEntry('UltimateCoachRefresh', $message, [System.Diagnostics.EventLogEntryType]::Error, 1001)
                $result.alerts += 'Windows Application event 1001 written'
            } catch { $result.alerts += 'Windows event failed; verify the installer registered the event source' }
        }
    }
    $json = $result | ConvertTo-Json -Depth 5
    Set-Content -LiteralPath (Join-Path $runFolder 'result.json') -Value $json -Encoding UTF8
    $temp = Join-Path $LogRoot ('latest-' + $runId + '.tmp')
    Set-Content -LiteralPath $temp -Value $json -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination (Join-Path $LogRoot 'latest.json') -Force
    if ($result.status -eq 'Failed') { Set-Content -LiteralPath (Join-Path $LogRoot 'FAILED.json') -Value $json -Encoding UTF8 }
    if (Test-Path -LiteralPath (Join-Path $LogRoot 'REFRESH_STATUS.txt')) { Copy-Item -LiteralPath (Join-Path $LogRoot 'REFRESH_STATUS.txt') -Destination (Join-Path $runFolder 'REFRESH_STATUS.txt') }
    Write-Output $json
}
exit $exitCode
