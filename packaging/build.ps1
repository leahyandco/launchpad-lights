# Builds dist\lpctl.exe.
# Uses its own environment in build\venv so it never touches the dev .venv.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:UV_PROJECT_ENVIRONMENT = "build\venv"

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

Invoke-Step "Sync build environment" { uv sync --locked --group build --no-dev }
Invoke-Step "Make icon" { uv run --no-sync python packaging\make_icon.py build\lpctl.ico }
$icon = (Resolve-Path build\lpctl.ico).Path  # absolute: PyInstaller resolves relative paths against --specpath
Invoke-Step "PyInstaller" {
    uv run --no-sync pyinstaller --noconfirm --clean --onefile --windowed `
        --name lpctl `
        --icon $icon `
        --specpath build `
        --workpath build\pyinstaller `
        --distpath dist `
        --paths src `
        --collect-submodules lpctl.modes `
        --collect-submodules winrt `
        --hidden-import pystray._win32 `
        --hidden-import mido.backends.rtmidi `
        packaging\entry.py
}

$exe = Get-Item dist\lpctl.exe
Write-Host ("==> Built {0} ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB))
