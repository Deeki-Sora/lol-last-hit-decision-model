param([switch]$InstallFFmpeg)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $RepoRoot
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.11 or newer, then run this script again.'
    }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        if ($InstallFFmpeg) {
            winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'FFmpeg installation failed.' }
            Write-Host 'Open a new terminal to refresh PATH.'
        } else {
            Write-Host 'Install FFmpeg manually, or rerun with -InstallFFmpeg.'
        }
    }
    Write-Host 'Scoring uses only the Python standard library. FFmpeg/ffprobe are needed for video operations.'
} finally { Pop-Location }
