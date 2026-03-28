$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$nodeDir = 'C:\Program Files\nodejs'
$npmCmd = Join-Path $nodeDir 'npm.cmd'

if (-not (Test-Path $pythonExe)) {
  throw "Missing Python venv at $pythonExe. Create it first with: python -m venv .venv"
}

if (-not (Test-Path $npmCmd)) {
  throw 'npm.cmd not found. Install Node.js LTS first: winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements'
}

# Ensure node is visible in this shell session even if PATH is stale.
if ($env:Path -notlike "*$nodeDir*") {
  $env:Path = "$nodeDir;$env:Path"
}

Write-Host 'Installing backend dependencies...'
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r backend\requirements.txt

Write-Host 'Installing frontend dependencies...'
Set-Location (Join-Path $repoRoot 'frontend')
& $npmCmd install

Write-Host 'Starting backend on http://localhost:8000 ...'
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$repoRoot'; & '$pythonExe' -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host 'Starting admin dashboard on http://localhost:3000 ...'
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$repoRoot\frontend'; & '$npmCmd' run dev --workspace=admin-dashboard"

Write-Host 'Starting driver dashboard on http://localhost:3001 ...'
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$repoRoot\frontend'; & '$npmCmd' run dev --workspace=driver-dashboard"

Write-Host ''
Write-Host 'Backend docs: http://localhost:8000/docs'
Write-Host 'Admin UI:    http://localhost:3000'
Write-Host 'Driver UI:   http://localhost:3001?sim_id=RUN_ID&ev_id=AMB_01'
