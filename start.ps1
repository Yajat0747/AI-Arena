# ─────────────────────────────────────────────
#   AI Arena — PowerShell Launcher
# ─────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir\backend"

# Create .env if missing
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "  Created backend\.env from .env.example" -ForegroundColor Green
    Write-Host "  Add your OpenRouter key to backend\.env" -ForegroundColor Yellow
    Write-Host ""
}

# Check Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "  Python: $pyVersion" -ForegroundColor Cyan
} catch {
    Write-Host "  ERROR: Python not found!" -ForegroundColor Red
    Write-Host "  Download from: https://python.org/downloads" -ForegroundColor Yellow
    Write-Host "  Make sure to check 'Add Python to PATH'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Install dependencies
Write-Host "  Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip install failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host "   AI Arena - OpenRouter Edition" -ForegroundColor Green  
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host "   App:      http://localhost:3001" -ForegroundColor White
Write-Host "   API docs: http://localhost:3001/docs" -ForegroundColor White
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host ""

python main.py
