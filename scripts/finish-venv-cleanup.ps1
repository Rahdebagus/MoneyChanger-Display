<#
    Finishes removing backend\venv.

    The 2.0 cleanup consolidated this project onto a single environment,
    .venv at the repository root. backend\venv could not be fully removed
    while VS Code's Python language server and an old uvicorn process still
    had files open inside it.

    Run this after closing VS Code (or reloading it once the interpreter is
    set to .venv) and stopping any old "uvicorn main:app" process.
#>

$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot '..\backend\venv'

if (-not (Test-Path $target)) {
    Write-Host 'backend\venv is already gone. Nothing to do.' -ForegroundColor Green
    exit 0
}

$holders = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.ExecutablePath -like '*backend\venv\*' }

if ($holders) {
    Write-Host 'These processes still have files open inside backend\venv:' -ForegroundColor Yellow
    $holders | ForEach-Object { Write-Host ("  PID {0}  {1}" -f $_.ProcessId, $_.CommandLine) }
    Write-Host ''
    Write-Host 'Close them (quit VS Code, stop the old uvicorn) and run this again.' -ForegroundColor Yellow
    exit 1
}

Remove-Item $target -Recurse -Force
Write-Host 'Removed backend\venv.' -ForegroundColor Green
Write-Host 'The active environment is .venv at the repository root.'
