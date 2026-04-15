# start_merged.ps1 - SAP Masters backend with all infrastructure env vars
$ErrorActionPreference = "Stop"
$BACKEND_DIR = $PSScriptRoot
Set-Location $BACKEND_DIR

# =====================================================================
# Environment Variables
# =====================================================================
$env_vars = @{
    "MEMGRAPH_URI"           = "bolt://localhost:7687"
    "QDRANT_URL"            = "http://localhost:6333"
    "VECTOR_STORE_BACKEND"  = "qdrant"
    "CELERY_BROKER_URL"     = "amqp://sapmasters:sapmasters123@localhost:5672//"
    "CELERY_RESULT_BACKEND" = "redis://localhost:6379/0"
    "HANA_MODE"             = "mock"
    "TENANT_ID"             = "default"
    "REDIS_URL"             = "redis://localhost:6379/0"
}

# Apply env vars to current PowerShell session (they WILL propagate to child processes)
foreach ($k in $env_vars.Keys) {
    [System.Environment]::SetEnvironmentVariable($k, $env_vars[$k], "Process")
}
Write-Host "[ENV] Memgraph: bolt://localhost:7687  [PRIMARY GRAPH]" -ForegroundColor Gray
Write-Host "[ENV] Qdrant:   http://localhost:6333" -ForegroundColor Gray
Write-Host "[ENV] Backend:  VECTOR_STORE_BACKEND=qdrant" -ForegroundColor Gray
Write-Host ""

# =====================================================================
# Step 1: Seed Qdrant
# =====================================================================
Write-Host "[1/4] Seeding Qdrant vector stores..." -ForegroundColor Yellow
& python seed_all.py --stats 2>&1 | Select-Object -Last 5
Write-Host ""

# =====================================================================
# Step 2: Infrastructure health check
# =====================================================================
Write-Host "[2/4] Infrastructure..." -ForegroundColor Yellow
function Test-Service($host, $port, $label) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect($host, $port)
        $c.Close()
        Write-Host "  $label  -> REACHABLE" -ForegroundColor Green
    } catch {
        Write-Host "  $label  -> UNREACHABLE (start Docker first)" -ForegroundColor Red
    }
}
Test-Service "localhost" 7687 "Memgraph  bolt://localhost:7687"
Test-Service "localhost" 6333 "Qdrant    http://localhost:6333"
Test-Service "localhost" 5672 "RabbitMQ  amqp://localhost:5672"
Test-Service "localhost" 6379 "Redis     localhost:6379"
Write-Host ""

# =====================================================================
# Step 3: Kill any existing process on port 8000
# =====================================================================
Write-Host "[3/4] Clearing port 8000..." -ForegroundColor Yellow
$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        cmd /c "taskkill /F /PID $pid" 2>$null
        Write-Host "  Killed PID $pid" -ForegroundColor Gray
    }
    Start-Sleep -Seconds 2
}
Write-Host ""

# =====================================================================
# Step 4: Start FastAPI backend — env vars flow into Start-Process via -Environment
# =====================================================================
Write-Host "[4/4] Starting FastAPI on http://localhost:8000..." -ForegroundColor Yellow

$env_block = [System.Collections.Specialized.StringDictionary]::new()
foreach ($k in $env_vars.Keys) {
    $env_block[$k] = $env_vars[$k]
}

# Write a quick env-check script so uvicorn confirms dotenv loaded
$env_check_script = @"
import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
print('[ENV] MEMGRAPH_URI=', os.environ.get('MEMGRAPH_URI','NOT SET'))
print('[ENV] VECTOR_STORE_BACKEND=', os.environ.get('VECTOR_STORE_BACKEND','NOT SET'))
sys.exit(0)
"@

$py_exe = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"
$uvicorn_cwd = $BACKEND_DIR

Write-Host "  Starting uvicorn (env vars loaded from backend\.env)..." -ForegroundColor Gray
Write-Host ""

Start-Process $py_exe `
    -ArgumentList "-c `"import os; from dotenv import load_dotenv; load_dotenv(os.path.join(os.path.dirname('app/main.py'), '..', '.env')); import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=False)`""`
    -WorkingDirectory $uvicorn_cwd `
    -EnvironmentVariables $env_block `
    -WindowStyle Normal

Write-Host "  Waiting for startup..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# Health check
try {
    $h = Invoke-RestMethod "http://localhost:8000/health" -TimeoutSec 5
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  FASTAPI: OK  (memgraph=$($h.memgraph) redis=$($h.redis))" -ForegroundColor Green
    Write-Host "  URL:     http://localhost:8000" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Cyan
} catch {
    Write-Host "  [WARN] Backend not responding yet — retry manually" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "NOTE: To use the new start script: ." -ForegroundColor Gray
Write-Host "      For Streamlit frontend: cd ..\frontend; streamlit run app.py --server.port 8501" -ForegroundColor Gray