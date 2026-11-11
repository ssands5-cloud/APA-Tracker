# Ultimate Coach: daily Windows refresh setup

## Status: prepared, not unattended-ready

The daily task definition is **disabled by design**. Do not call this a working
morning refresh until logged-out authentication and workbook validation succeed.
No SMTP code or credentials are included. Future email recipient: ssands5@comcast.net.

Current blockers verified in this repository:

- `QUICK_REFRESH.bat` calls `tools/launch_apa_refresh.bat`.
- That launcher changes directory with `cd /d "%~dp0.."` and selects the
  repository venv, Python 3.12, or Python 3.13.
- `pipeline.ultimate_coach_refresh` normally opens a fresh, headed APA browser
  and waits for a person to sign in and press Enter. No unattended APA token
  was configured during setup.
- Rebuilt workbooks require desktop Excel COM recalculation. This must be
  replaced with a suitable unattended validation path, or the refresh/output
  stages must be separated, before claiming logged-out reliability.
- The scheduled wrapper currently refuses `-Scheduled` runs with an explicit
  failure. Simply enabling the task cannot solve these blockers.

Microsoft cautions that noninteractive Office automation can hang:
https://learn.microsoft.com/en-us/office/client-developer/integration/considerations-unattended-automation-office-microsoft-365-for-unattended-rpa

## Files and working directory

Canonical repository and Task Scheduler **Start in**:

`D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`

The wrapper additionally sets the child process working directory explicitly
and validates the Git root and APA-Tracker origin before launching the batch.
It calls the absolute `QUICK_REFRESH.bat` path with `--no-open`, and sets
`APA_REFRESH_NO_PAUSE=1`. This overrides the launcher's `--open` and final pause;
it does **not** remove the APA login prompt or Excel requirements.

The task scripts are tracked in the canonical checkout under `tools`.

## Automatic task creation

Open **Windows PowerShell as administrator**. Enter your Windows account
password only in its local credential prompt; a Windows Hello PIN is not the
task password. Do not put a password in command history or chat.

```powershell
$repo = 'D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker'
$setup = Join-Path $repo 'tools'
& (Join-Path $setup 'Register-UltimateCoachRefreshTask.ps1') -Repository $repo -User 'PAULS-DESKTOP\ssand'
```

This creates:

1. **Ultimate Coach - Daily QUICK Refresh** — daily 08:00, Password logon
   (whether logged in or not), limited privileges, initially disabled.
2. **Ultimate Coach - Refresh Failure Alert** — interactive popup on Application
   event 1001 from UltimateCoachRefresh, plus a logon trigger for failures that
   occurred while signed out. This task is enabled, but does nothing without an
   unacknowledged FAILED.json.

The installer also registers the Application event source and enables Task
Scheduler Operational history. It refuses to overwrite an existing task.
The daily task uses wake-to-run, missed-start catch-up, IgnoreNew (no overlap),
and a 100-minute scheduler limit. The wrapper limits its own batch child to 90
minutes. Automatic retries are deliberately not configured: interrupted refresh
locks require review rather than blindly launching another refresh.

08:00 follows the computer's local timezone. This machine was checked as
**Mountain Standard Time (US & Canada)**, which observes Denver daylight saving
changes. The computer must be powered on; a wake timer cannot power on a shut-down
computer. Catch-up can run later than 08:00 after a missed start.

## Repoint the two installed tasks

Run from **Windows PowerShell as administrator**. Enter the existing daily task account password only in the local credential prompt. This updates the installed actions and working directories while preserving their triggers and leaving the daily task disabled.

```powershell
$repo = 'D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker'
& (Join-Path $repo 'tools\Register-UltimateCoachRefreshTask.ps1') -Repository $repo -RepointExisting
```

Check that both reported working directories use the canonical checkout and both script paths use its `tools` folder. Verify the alert while signed in. The daily task remains disabled until the unattended requirements below pass.

## Exact Task Scheduler UI setup

1. Press **Win+R**, enter `taskschd.msc`, and choose **Create Task**.
2. General: name `Ultimate Coach - Daily QUICK Refresh`; user
   `PAULS-DESKTOP\ssand`; choose **Run whether user is logged on or not**.
   Do not select **Do not store password**. Leave **Run with highest privileges**
   unchecked for the refresh itself.
3. Triggers: **New → On a schedule → Daily → 8:00:00 AM → Recur every 1 day**.
   Leave the trigger disabled until readiness is proven.
4. Actions: **Start a program**.
   Program: `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`.
   Arguments (one line):

   ```text
   -NoProfile -NonInteractive -File "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\tools\Invoke-UltimateCoachScheduledRefresh.ps1" -Repository "D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker" -Scheduled
   ```

   **Start in**, without quotes:
   `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker`.
5. Conditions: enable **Wake the computer to run this task**; do not require idle.
   Do not require a specific network connection: an attempted run should log a
   network failure rather than silently skip execution.
6. Settings: enable **Allow task to be run on demand**, **Run as soon as possible
   after a scheduled start is missed**, and **Stop if running longer than
   1 hour 40 minutes**. If already running: **Do not start a new instance**.
7. Save and enter the task-account password locally. Keep the task disabled.
8. In the Actions pane choose **Enable All Tasks History** if needed.

Use the installer rather than manual setup to create the event source and
companion popup task as well.

## Logs, history and failure behavior

Everything stays under `ultimate-coach-runs\refresh`:

- `scheduled-<UTC timestamp>-<id>\runner.log`, `stdout.log`, `stderr.log`,
  `result.json`, and `REFRESH_STATUS.txt` for each scheduled attempt.
- Each attempt preserves the previous top-level status in `previous-status.txt`.
- Existing pipeline `run-*` generations and CURRENT.json are retained untouched
  on failure. There is no cleanup or history rotation in these scripts.
- `latest.json` records the latest wrapper result.
- `FAILED.json` records the latest failure; it remains as failure history even
  after a later success. Compare it with latest.json before treating it as current.
- `REFRESH_STATUS.txt` explicitly records a wrapper/preflight failure.
- Application event **1001**, provider **UltimateCoachRefresh**, triggers a
  popup while the task user is logged in. A failure while logged out is shown
  after the next login. The popup contains the local log path, not APA records.

No email is sent. Do not publish logs without checking their contents.

## Validation sequence and honest completion criteria

Safe failure-path check after installation (this intentionally fails; no APA request):

```powershell
& (Join-Path $setup 'Invoke-UltimateCoachScheduledRefresh.ps1') -Repository $repo -TestFailure
# Expect exit code 1, FAILED.json, REFRESH_STATUS.txt, event 1001 and a popup.
```

Read status and Windows task configuration:

```powershell
Get-ScheduledTask -TaskName 'Ultimate Coach - Daily QUICK Refresh' |
    Select-Object TaskName, State, Principal, Actions, Triggers
Get-ScheduledTaskInfo -TaskName 'Ultimate Coach - Daily QUICK Refresh'
Get-Content (Join-Path $repo 'ultimate-coach-runs\refresh\latest.json')
Get-WinEvent -FilterHashtable @{LogName='Application';ProviderName='UltimateCoachRefresh';Id=1001} -MaxEvents 5
```

Do not enable the daily task until all of these are proven:

1. APA authentication works without a visible browser or Enter prompt, including
   token renewal/expiry handling.
2. Changed data can produce validated outputs without an interactive Excel desktop.
3. The wrapper's scheduled-readiness refusal is removed only as part of the
   reviewed unattended implementation.
4. A task run under Password logon succeeds while logged out, returns code 0,
   advances a verified CURRENT.json bundle, and preserves run logs.
5. A controlled failure writes both markers, an event and a user notification.

Only then:

```powershell
Enable-ScheduledTask -TaskName 'Ultimate Coach - Daily QUICK Refresh'
```

Even a successful local QUICK refresh does not automatically publish a new
historical snapshot to the hosted Ultimate Coach web dashboard.
