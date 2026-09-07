$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Load-Config.ps1')
$desktopTask = [Environment]::GetFolderPath('Desktop')
$shellTask = New-Object -ComObject WScript.Shell
$powerShellTask = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$iconTask = $gameExeTask + ',0'
$itemsTask = @(
    @{ Name='WARNO - Enable 10v10'; Script='Launch-10v10.ps1'; Description='Start WARNO through Steam and enable solo 10v10. If already running, use from the Solo menu.' },
    @{ Name='WARNO - Restore 4v4'; Script='Repair-Skirmish.ps1'; Description='Close WARNO, run this to repair the saved lobby, then start WARNO for vanilla 4v4.' }
)
foreach ($itemTask in $itemsTask) {
    $scriptPathTask = Join-Path $PSScriptRoot $itemTask.Script
    if (-not (Test-Path -LiteralPath $scriptPathTask)) { throw ('Missing script: ' + $scriptPathTask) }
    $linkPathTask = Join-Path $desktopTask ($itemTask.Name + '.lnk')
    $linkTask = $shellTask.CreateShortcut($linkPathTask)
    $linkTask.TargetPath = $powerShellTask
    $linkTask.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $scriptPathTask + '"'
    $linkTask.WorkingDirectory = $PSScriptRoot
    $linkTask.IconLocation = $iconTask
    $linkTask.Description = $itemTask.Description
    $linkTask.WindowStyle = 1
    $linkTask.Save()
    $savedTask = $shellTask.CreateShortcut($linkPathTask)
    if ($savedTask.TargetPath -ne $powerShellTask -or $savedTask.Arguments -ne $linkTask.Arguments) {
        throw ('Shortcut verification failed: ' + $linkPathTask)
    }
    [pscustomobject]@{ Shortcut=$linkPathTask; Target=$savedTask.TargetPath; Arguments=$savedTask.Arguments; Description=$savedTask.Description } | ConvertTo-Json
}
