param(
    [switch]$CheckOnly,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$exitCodeTask = 0
$launcherLogTask = Join-Path $PSScriptRoot 'launcher-enable.log'
function Write-LaunchLogTask([string]$Message) {
    [IO.File]::AppendAllText($launcherLogTask, ('{0:o} PID={1} {2}{3}' -f [DateTimeOffset]::Now, $PID, $Message, [Environment]::NewLine))
}
try {
    Write-LaunchLogTask ('Starting; CheckOnly=' + $CheckOnly)
    # A desktop child can inherit PowerShell 7's module search path while
    # running Windows PowerShell 5.1. Load this host's own Get-FileHash.
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Force
    $Host.UI.RawUI.WindowTitle = 'WARNO - Enable 10v10'
    Write-Host 'WARNO - Enable 10v10' -ForegroundColor Cyan
    Write-Host 'Use from the Solo menu. Open a fresh Skirmish lobby afterward.'
    Write-Host ''

    . (Join-Path $PSScriptRoot 'Load-Config.ps1')
    if (-not (Test-Path -LiteralPath $pythonExeTask)) {
        throw 'Python 3.14 was not found. This launcher needs the Python installation used to set it up.'
    }
    $patchScriptTask = Join-Path $PSScriptRoot 'runtime_10v10.py'
    if (-not (Test-Path -LiteralPath $patchScriptTask)) {
        throw 'The memory patch script is missing from the launcher folder.'
    }

    $gamesTask = @(Get-Process -Name WARNO -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -eq $gameExeTask
    })
    if ($gamesTask.Count -eq 0) {
        throw 'Start WARNO, go to the Solo menu, then run this shortcut again.'
    }
    if ($gamesTask.Count -ne 1) {
        throw 'More than one WARNO process was found. Close the extra instance first.'
    }
    $gamePidTask = $gamesTask[0].Id

    function Invoke-PatchTask([switch]$Apply) {
        $argsTask = @($patchScriptTask, '--pid', [string]$gamePidTask)
        if ($Apply) { $argsTask += '--apply' }
        $outputTask = & $pythonExeTask @argsTask 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw ($outputTask | Out-String)
        }
        return (($outputTask | Out-String) | ConvertFrom-Json)
    }

    # Fresh PID, process identity, module base, build hash and code bytes are
    # checked on every invocation. A status read never opens a write handle.
    $statusTask = Invoke-PatchTask
    Write-LaunchLogTask ('Validated WARNO PID=' + $gamePidTask + '; patch active=' + $statusTask.memory_patch_active)
    if (-not $CheckOnly) {
        # The watcher must be ready before this session is allowed to save an
        # expanded lobby. It survives closing this visible launcher window.
        $cleanupScriptTask = Join-Path $PSScriptRoot 'profile_cleanup.py'
        $pythonWindowlessTask = Join-Path (Split-Path $pythonExeTask -Parent) 'pythonw.exe'
        $readyFileTask = Join-Path $PSScriptRoot ('cleanup-ready-' + [guid]::NewGuid().ToString('N') + '.json')
        if (-not (Test-Path -LiteralPath $cleanupScriptTask) -or -not (Test-Path -LiteralPath $pythonWindowlessTask)) {
            throw 'Saved-lobby cleanup is missing. No new memory patch was applied.'
        }
        $watcherArgsTask = '"{0}" --watch-pid {1} --ready-file "{2}"' -f $cleanupScriptTask, $gamePidTask, $readyFileTask
        $watcherTask = Start-Process -FilePath $pythonWindowlessTask -ArgumentList $watcherArgsTask -WindowStyle Hidden -PassThru
        $deadlineTask = (Get-Date).AddSeconds(15)
        while (-not (Test-Path -LiteralPath $readyFileTask)) {
            if ($watcherTask.HasExited -or (Get-Date) -gt $deadlineTask) {
                throw 'Saved-lobby cleanup could not start. See profile-cleanup.log. No new memory patch was applied.'
            }
            Start-Sleep -Milliseconds 100
        }
        $readyTask = Get-Content -LiteralPath $readyFileTask -Raw | ConvertFrom-Json
        if (-not $readyTask.ready) { throw ('Saved-lobby cleanup refused: ' + $readyTask.error) }
        Write-Host 'Automatic saved-lobby cleanup is ready.' -ForegroundColor Green
        Write-LaunchLogTask 'Automatic saved-lobby cleanup is ready.'
    }
    if ($statusTask.memory_patch_active) {
        Write-Host '10v10 is already enabled in this WARNO session.' -ForegroundColor Green
    }
    elseif ($CheckOnly) {
        Write-Host 'The game version is supported. The memory patch is not currently enabled.'
    }
    else {
        $backupRootTask = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WARNO_Profile_Backups'
        $backupSessionTask = Join-Path $backupRootTask ('desktop_10v10_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
        New-Item -ItemType Directory -Path $backupSessionTask -Force | Out-Null
        $copyTask = Join-Path $backupSessionTask 'PROFILE.profile2'
        Copy-Item -LiteralPath $profileTask -Destination $copyTask
        if ((Get-FileHash -LiteralPath $profileTask).Hash -ne (Get-FileHash -LiteralPath $copyTask).Hash) {
            throw 'Profile backup verification failed. No memory patch was applied.'
        }
        Write-Host ('Profile backup: ' + $copyTask)
        Write-LaunchLogTask ('Profile backup verified: ' + $copyTask)
        $statusTask = Invoke-PatchTask -Apply
        if (-not $statusTask.memory_patch_active) { throw 'The patch was not enabled.' }
        # Reopen the game process with read-only access for independent read-back.
        $statusTask = Invoke-PatchTask
        if (-not $statusTask.memory_patch_active) { throw 'The independent read-back did not find the patch.' }
        Write-Host '10v10 memory patch applied and verified.' -ForegroundColor Green
    }

    Write-Host ('WARNO process: ' + $gamePidTask)
    Write-Host 'WARNO.exe on disk is unchanged.'
    Write-Host ''
    Write-Host 'Open Solo -> Skirmish. If a lobby was already open, leave and reopen it.'
    Write-Host 'Add AI to fill the ten slots per team.'
    if (-not $CheckOnly) {
        Write-Host 'After quitting WARNO, wait about 10 seconds before restarting.'
        Write-Host 'A hidden helper trims saved lobby AI to vanilla limits, preserving decks and progress.'
        Write-Host 'To return to 4v4: close WARNO, run WARNO - Restore 4v4, then start WARNO normally.'
    }
    Write-Host 'The RAM patch ends when WARNO exits. Restart WARNO before multiplayer.'
    Write-LaunchLogTask ('Finished; WARNO PID=' + $gamePidTask + '; patch active=' + $statusTask.memory_patch_active)
}
catch {
    $exitCodeTask = 1
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    try {
        Write-LaunchLogTask ('ERROR: ' + $_.Exception.Message)
        Write-Host ('Error log: ' + $launcherLogTask)
    } catch { Write-Host 'The launcher could not write its error log.' }
}
finally {
    if (-not $NoPause) {
        Write-Host ''
        [void](Read-Host 'Press Enter to close this window')
    }
}
exit $exitCodeTask
