param(
    [switch]$CheckOnly,
    [switch]$NoPause,
    [ValidateRange(10, 600)]
    [int]$StartupTimeoutSeconds = 180
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
    Write-Host 'Starts WARNO through Steam if needed, then enables solo 10v10.'
    Write-Host 'If WARNO is already running, use this from the Solo menu.'
    Write-Host ''

    . (Join-Path $PSScriptRoot 'Load-Config.ps1')
    if (-not (Test-Path -LiteralPath $pythonExeTask)) {
        throw 'Python 3.14 was not found. This launcher needs the Python installation used to set it up.'
    }
    $patchScriptTask = Join-Path $PSScriptRoot 'runtime_10v10.py'
    if (-not (Test-Path -LiteralPath $patchScriptTask)) {
        throw 'The memory patch script is missing from the launcher folder.'
    }

    function Get-WarnoProcessTask {
        $foundTask = @(Get-Process -Name WARNO -ErrorAction SilentlyContinue)
        if ($foundTask.Count -gt 1) {
            throw 'More than one WARNO process was found. Close the extra instance first.'
        }
        if ($foundTask.Count -eq 1 -and $foundTask[0].Path -ne $gameExeTask) {
            throw 'The running WARNO does not match the configured executable. Close it or run Setup.ps1 again.'
        }
        return $foundTask
    }
    $gamesTask = @(Get-WarnoProcessTask)
    if ($gamesTask.Count -eq 0) {
        if ($CheckOnly) { throw 'WARNO is not running. CheckOnly does not start the game or change its profile.' }

        # An interrupted cleanup may leave an expanded profile behind. Repair
        # it while the game is closed, before starting an unpatched process.
        Write-Host 'Checking the saved lobby before starting WARNO...'
        $cleanupOutputTask = & $pythonExeTask (Join-Path $PSScriptRoot 'profile_cleanup.py') --repair 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($cleanupOutputTask | Out-String) }
        $cleanupResultTask = ($cleanupOutputTask | Out-String) | ConvertFrom-Json
        Write-LaunchLogTask ('Pre-launch lobby cleanup; changed=' + $cleanupResultTask.changed)
        Write-Host 'Starting WARNO through Steam. Waiting for its window...'
        Write-LaunchLogTask 'Starting WARNO through Steam.'
        Start-Process -FilePath 'steam://rungameid/1611600'
        $startupDeadlineTask = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
        while ($gamesTask.Count -eq 0) {
            if ([DateTime]::UtcNow -ge $startupDeadlineTask) {
                throw 'WARNO did not start in time. Check Steam for an update or launch prompt, then run this shortcut again.'
            }
            Start-Sleep -Milliseconds 500
            $gamesTask = @(Get-WarnoProcessTask)
        }
        $startingGameTask = $gamesTask[0]
        while ($true) {
            $startingGameTask.Refresh()
            if ($startingGameTask.HasExited) { throw 'WARNO exited during startup. No memory patch was applied.' }
            if ($startingGameTask.MainWindowHandle -ne [IntPtr]::Zero) { break }
            if ([DateTime]::UtcNow -ge $startupDeadlineTask) {
                throw 'WARNO started but its window did not appear in time. Let startup finish, then run this shortcut again.'
            }
            Start-Sleep -Milliseconds 500
        }
        Write-LaunchLogTask ('WARNO window is ready; PID=' + $startingGameTask.Id)
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
