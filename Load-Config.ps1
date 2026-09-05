$configPathTask = if ($env:WARNO10V10_CONFIG) { $env:WARNO10V10_CONFIG } else { Join-Path $PSScriptRoot 'config.local.json' }
if (-not (Test-Path -LiteralPath $configPathTask)) {
    throw 'Run Setup.ps1 first to select your WARNO executable and profile.'
}
$settingsTask = Get-Content -LiteralPath $configPathTask -Raw | ConvertFrom-Json
$gameExeTask = [string]$settingsTask.game_exe
$profileTask = [string]$settingsTask.profile
$pythonExeTask = [string]$settingsTask.python_exe
foreach ($pathTask in @($gameExeTask, $profileTask, $pythonExeTask)) {
    if (-not [IO.Path]::IsPathRooted($pathTask) -or -not (Test-Path -LiteralPath $pathTask -PathType Leaf)) {
        throw 'A configured file is missing. Run Setup.ps1 again.'
    }
}
