param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$resultCodeTask = 0
try {
    $Host.UI.RawUI.WindowTitle = 'WARNO - Restore 4v4'
    Write-Host 'WARNO - Restore 4v4' -ForegroundColor Cyan
    if (@(Get-Process -Name WARNO -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'Close WARNO completely, then run WARNO - Restore 4v4 again. It will preserve your decks and progress.'
    }
    . (Join-Path $PSScriptRoot 'Load-Config.ps1')
    $scriptTask = Join-Path $PSScriptRoot 'profile_cleanup.py'
    $outputTask = & $pythonExeTask $scriptTask --repair 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($outputTask | Out-String) }
    $resultTask = ($outputTask | Out-String) | ConvertFrom-Json
    if ($resultTask.changed) {
        Write-Host 'Saved solo lobby restored to vanilla 4v4 limits. Decks and progress were preserved.' -ForegroundColor Green
        Write-Host ('Backup: ' + $resultTask.backup)
    } else {
        Write-Host 'The saved solo lobby already fits vanilla limits.' -ForegroundColor Green
    }
    Write-Host 'Start WARNO normally, then open Solo -> Skirmish.'
    Write-Host 'Do not run Enable 10v10 for a 4v4 session.'
} catch {
    $resultCodeTask = 1
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
}
exit $resultCodeTask
