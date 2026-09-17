<#
.SYNOPSIS
    Registers a Windows scheduled task that keeps the Instagram session fresh.

.DESCRIPTION
    The task runs `uv run scripts/instagram_session/refresh_session.py` every
    N hours (default 6) with highest privileges (required for Chrome app-bound
    cookie decryption). Run this script once from an ELEVATED PowerShell.

.EXAMPLE
    # From an elevated PowerShell:
    .\scripts\instagram_session\register_task.ps1
    .\scripts\instagram_session\register_task.ps1 -IntervalHours 4 -NotifyChatId 123456
#>
param(
    [int]$IntervalHours = 6,
    [string]$NotifyChatId = ""
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run from an elevated (Administrator) PowerShell."
    exit 1
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptPath = Join-Path $PSScriptRoot "refresh_session.py"

$uv = Get-Command uv -ErrorAction Stop
$uvPath = $uv.Source

$scriptArgs = "run `"$scriptPath`""
if ($NotifyChatId) {
    $scriptArgs += " --notify-chat-id $NotifyChatId"
}

$action = New-ScheduledTaskAction -Execute $uvPath -Argument $scriptArgs -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -RunLevel Highest -LogonType S4U
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName "InstagramSessionRefresh" `
    -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings `
    -Description "Extracts Instagram cookies from Chrome and keeps the session alive for the Telegram bot." `
    -Force | Out-Null

Write-Host "Scheduled task 'InstagramSessionRefresh' registered (every $IntervalHours h, elevated)."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName InstagramSessionRefresh"
Write-Host "Logs:              $repoRoot\secrets\refresh.log"
