param(
    [string]$GameExe,
    [string]$Profile,
    [string]$PythonExe,
    [switch]$NoShortcuts,
    [switch]$NoPause
)
$ErrorActionPreference = 'Stop'
$setupExitTask = 0
try {
    Write-Host 'WARNO solo 10v10 - local setup' -ForegroundColor Cyan
    Write-Host 'Use Windows 64-bit and Python 3.14 or later. Setup does not patch the game.'
    if (-not $PythonExe) {
        $pyTask = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pyTask) {
            $pythonOutputTask = & $pyTask.Source -3.14 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $PythonExe = ($pythonOutputTask | Out-String).Trim() }
        }
    }
    if (-not $PythonExe) { $PythonExe = (Read-Host 'Full path to your 64-bit Python 3.14 python.exe').Trim().Trim('"') }
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
    & $PythonExe -c "import sys, struct; from compression import zstd; assert sys.version_info >= (3,14) and struct.calcsize('P') == 8, '64-bit Python 3.14+ required'"
    if ($LASTEXITCODE -ne 0) { throw '64-bit Python 3.14 or later with compression.zstd is required.' }
    if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $PythonExe -Parent) 'pythonw.exe'))) {
        throw 'pythonw.exe is required beside python.exe for the background cleanup helper.'
    }
    if (-not $GameExe) {
        $runningTask = @(Get-Process -Name WARNO -ErrorAction SilentlyContinue)
        if ($runningTask.Count -eq 1) { $GameExe = $runningTask[0].Path }
    }
    if (-not $GameExe) { $GameExe = (Read-Host 'Full path to WARNO.exe (Steam -> WARNO -> Manage -> Browse local files)').Trim().Trim('"') }
    $GameExe = (Resolve-Path -LiteralPath $GameExe).Path
    if ([IO.Path]::GetFileName($GameExe) -ine 'WARNO.exe') { throw 'Select WARNO.exe.' }
    $expectedHashTask = '70F34D844EBF23EEA92D535FAD0FFFB6E0BC60DD1F64CC80C2B903D06ABAB3A8'
    if ((Get-FileHash -LiteralPath $GameExe -Algorithm SHA256).Hash -ne $expectedHashTask) {
        throw 'This WARNO build is not supported. Do not bypass the version check.'
    }
    if (-not $Profile) {
        Write-Host 'Select the profile for the Steam account you play with.'
        Write-Host 'Usually: Steam\userdata\<account-id>\1611600\remote\PROFILE.profile2'
        $Profile = (Read-Host 'Full path to PROFILE.profile2').Trim().Trim('"')
    }
    $Profile = (Resolve-Path -LiteralPath $Profile).Path
    if ([IO.Path]::GetFileName($Profile) -ine 'PROFILE.profile2') { throw 'Select PROFILE.profile2.' }
    # Validate the profile format and proposed repair without writing it.
    & $PythonExe (Join-Path $PSScriptRoot 'profile_codec.py') $Profile
    if ($LASTEXITCODE -ne 0) { throw 'This saved-profile layout is not supported.' }
    $configTask = [ordered]@{ game_exe=$GameExe; profile=$Profile; python_exe=$PythonExe }
    $configPathTask = Join-Path $PSScriptRoot 'config.local.json'
    if (Test-Path -LiteralPath $configPathTask) {
        Copy-Item -LiteralPath $configPathTask -Destination ($configPathTask + '.backup-' + (Get-Date -Format 'yyyyMMddHHmmssfff'))
    }
    $configTask | ConvertTo-Json | Set-Content -LiteralPath $configPathTask -Encoding UTF8
    if (-not $NoShortcuts) { & (Join-Path $PSScriptRoot 'Create-Desktop-Shortcuts.ps1') }
    Write-Host 'Setup complete. Your local paths are excluded from Git.' -ForegroundColor Green
    Write-Host 'Enable 10v10: run the desktop shortcut from the Solo menu.'
    Write-Host 'Restore 4v4: close WARNO, run Restore 4v4, then restart WARNO.'
} catch {
    $setupExitTask = 1
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
}
exit $setupExitTask
