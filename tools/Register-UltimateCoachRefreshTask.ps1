#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Repository = 'D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker',
    [string]$User = 'PAULS-DESKTOP\ssand',
    [switch]$PlanOnly,
    [string]$PlanPath
)
$ErrorActionPreference = 'Stop'
$Repository = (Resolve-Path -LiteralPath $Repository).Path
$runner = Join-Path $PSScriptRoot 'Invoke-UltimateCoachScheduledRefresh.ps1'
$notifier = Join-Path $PSScriptRoot 'Show-UltimateCoachRefreshAlert.ps1'
$logRoot = Join-Path $Repository 'ultimate-coach-runs\refresh'
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = '-NoProfile -NonInteractive -File "{0}" -Repository "{1}" -Scheduled' -f $runner, $Repository
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $Repository
$trigger = New-ScheduledTaskTrigger -Daily -At '08:00'
$trigger.StartBoundary = (Get-Date).Date.AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss')
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 100) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.Enabled = $false
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Password -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Daily QUICK refresh at 08:00 local Mountain time. DISABLED: interactive APA authentication and native Excel validation must be made unattended-safe before enabling. Logs and generations are retained.'
$alertAction = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -File "{0}" -LogRoot "{1}"' -f $notifier, $logRoot) -WorkingDirectory $Repository
$alertPrincipal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$alertSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
$eventTrigger = New-CimInstance -CimClass (Get-CimClass -Namespace 'Root/Microsoft/Windows/TaskScheduler' -ClassName 'MSFT_TaskEventTrigger') -ClientOnly -Property @{ Enabled=$true; Subscription='<QueryList><Query Id="0" Path="Application"><Select Path="Application">*[System[Provider[@Name="UltimateCoachRefresh"] and EventID=1001]]</Select></Query></QueryList>' }
$alert = New-ScheduledTask -Action $alertAction -Trigger @((New-ScheduledTaskTrigger -AtLogOn -User $User), $eventTrigger) -Settings $alertSettings -Principal $alertPrincipal -Description 'Shows any unacknowledged refresh failure when the task owner next signs in.'
if ($PlanOnly) {
    if (-not $PlanPath) { throw 'Specify an absolute -PlanPath for the exported task XML.' }
    $task | Export-ScheduledTask | Set-Content -LiteralPath $PlanPath -Encoding UTF8
    $alert | Export-ScheduledTask | Set-Content -LiteralPath ($PlanPath + ".alert.xml") -Encoding UTF8
    Write-Output "Disabled task definition exported to $PlanPath. Nothing registered."
    exit 0
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run the installer in elevated Windows PowerShell. The refresh itself uses limited privileges.' }
if (Get-ScheduledTask -TaskName 'Ultimate Coach - Daily QUICK Refresh' -ErrorAction SilentlyContinue) { throw 'Task already exists. Inspect it first; installer does not overwrite tasks.' }
if (Get-ScheduledTask -TaskName 'Ultimate Coach - Refresh Failure Alert' -ErrorAction SilentlyContinue) { throw 'Failure-alert task already exists. Inspect it first.' }
$credential = Get-Credential -UserName $User -Message 'Windows task account password (not Windows Hello PIN). Stored by Task Scheduler; never put it in a script or chat.'
if (-not $credential -or $credential.UserName -ne $User) { throw 'Credential account does not match the task account.' }
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
if (-not [System.Diagnostics.EventLog]::SourceExists('UltimateCoachRefresh')) { New-EventLog -LogName Application -Source UltimateCoachRefresh }
Register-ScheduledTask -TaskName 'Ultimate Coach - Daily QUICK Refresh' -InputObject $task -User $credential.UserName -Password $credential.GetNetworkCredential().Password | Out-Null
Register-ScheduledTask -TaskName 'Ultimate Coach - Refresh Failure Alert' -InputObject $alert | Out-Null
& "$env:SystemRoot\System32\wevtutil.exe" sl Microsoft-Windows-TaskScheduler/Operational /e:true
if ($LASTEXITCODE -ne 0) { Write-Warning 'Task history could not be enabled. Enable All Tasks History manually in Task Scheduler.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$task | Export-ScheduledTask | Set-Content -LiteralPath (Join-Path $logRoot ("task-definition-" + $stamp + ".xml")) -Encoding UTF8
Write-Output 'Daily task installed DISABLED. Windows failure notices run on failure events while signed in, or at the next sign-in. No SMTP is configured. Unattended APA/Excel blockers must be resolved before enabling.'
