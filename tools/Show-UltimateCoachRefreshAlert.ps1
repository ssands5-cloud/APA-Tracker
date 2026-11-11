[CmdletBinding()]
param([string]$LogRoot = 'D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\ultimate-coach-runs\refresh')
$ErrorActionPreference = 'Stop'
$pending = Join-Path $LogRoot 'FAILED.json'
if (-not (Test-Path -LiteralPath $pending)) { exit 0 }
$failure = Get-Content -LiteralPath $pending -Raw | ConvertFrom-Json
$ack = Join-Path $LogRoot 'last-notified-run.txt'
if ((Test-Path -LiteralPath $ack) -and (Get-Content -LiteralPath $ack -Raw).Trim() -eq $failure.run_id) { exit 0 }
Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show("A refresh failed at $($failure.finished_utc).`nLogs: $($failure.log_folder)`nCheck latest.json to see whether a later run succeeded.", 'Ultimate Coach refresh failure', 'OK', 'Warning') | Out-Null
Set-Content -LiteralPath $ack -Value $failure.run_id -Encoding UTF8
