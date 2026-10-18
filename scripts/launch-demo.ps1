# One-click desktop demo: a fresh throwaway ledger, the Acme Notes story, the hosted open-weight model for speed.
# Run from the repo root:   powershell -ExecutionPolicy Bypass -File scripts\launch-demo.ps1
# Add -Local to use your own Ollama instead (slower, but it is the "runs on your laptop" proof).
param([switch]$Local)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$demoDir = Join-Path $HOME ".sthira-demo"
if (Test-Path $demoDir) { Remove-Item $demoDir -Recurse -Force }   # always start clean
New-Item -ItemType Directory -Path $demoDir | Out-Null
$env:STHIRA_DB = Join-Path $demoDir "ledger.db"

if (-not $Local -and (Test-Path ".env")) {
  # Load model settings only. The paid ANTHROPIC_API_KEY is deliberately never loaded.
  Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*(STHIRA_[A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim()) }
  }
  $env:STHIRA_PROVIDER = "openai"
  Write-Host "Using the hosted open-weight model ($env:STHIRA_MODEL)."
} else {
  Write-Host "Using local Ollama. Make sure it is running (ollama serve)."
}
Write-Host "Opening Sthira. Close the window to stop it."
uv run --no-sync sthira app --demo
