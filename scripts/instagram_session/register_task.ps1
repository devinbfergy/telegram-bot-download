<#
.SYNOPSIS
    Registers a scheduled task that keeps the bot's Instagram session alive.

.DESCRIPTION
    Runs `uv run scripts/instagram_session/refresh_session.py` every N hours (default 4,
    with up to 10 minutes of random jitter). It drives a headless Chrome on the bot's own
    profile, so NO elevation is needed. Do the one-time login first:
        uv run scripts/instagram_session/refresh_session.py --login

.EXAMPLE
    .\scripts\instagram_session\register_task.ps1
    .\scripts\instagram_session\register_task.ps1 -IntervalHours 3 -NotifyChatId 123456
#>
param(
    [int]$IntervalHours = 4,
    [string]$NotifyChatId = ""
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptPath = Join-Path $PSScriptRoot "refresh_session.py"
$uvPath = (Get-Command uv -ErrorAction Stop).Source

$scriptArgs = "run `"$scriptPath`""
if ($NotifyChatId) {
    $scriptArgs += " --notify-chat-id $NotifyChatId"
}

$action = New-ScheduledTaskAction -Execute $uvPath -Argument $scriptArgs -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650) -RandomDelay (New-TimeSpan -Minutes 10)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -RunLevel Limited -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName "InstagramSessionRefresh" `
    -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings `
    -Description "Keeps the Telegram bot's Instagram session alive via a headless Chrome profile." `
    -Force | Out-Null

Write-Host "Scheduled task 'InstagramSessionRefresh' registered (every $IntervalHours h)."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName InstagramSessionRefresh"
Write-Host "Logs:              $repoRoot\secrets\refresh.log"
