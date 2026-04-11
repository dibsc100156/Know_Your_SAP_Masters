# SAP Masters 5-Pillar RAG — Quick Start (Windows)
# Run from SAP_HANA_LLM_VendorChatbot\backend\

$ErrorActionPreference = "Stop"
$BACKEND_DIR = $PSScriptRoot
Set-Location $BACKEND_DIR

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  SAP Masters — 5-Pillar RAG" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Seed vector stores
Write-Host "[1/3] Seeding vector stores..." -ForegroundColor Yellow
python seed_all.py --stats
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] seed_all.py exited with code $LASTEXITCODE" -ForegroundColor Red
}
Write-Host ""

# Step 2: Start FastAPI backend
Write-Host "[2/3] Starting FastAPI on http://localhost:8000" -ForegroundColor Yellow
Write-Host "       API Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Start-Process python -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal -WorkingDirectory $BACKEND_DIR

# Step 3: Start Streamlit frontend
Write-Host "[3/3] Starting Streamlit on http://localhost:8501" -ForegroundColor Yellow
Write-Host ""
$FRONTEND_DIR = Join-Path $BACKEND_DIR "..\frontend"
if (Test-Path $FRONTEND_DIR) {
    Start-Process python -ArgumentList "-m streamlit run app.py --server.port 8501 --server.address 0.0.0.0" -WindowStyle Normal -WorkingDirectory $FRONTEND_DIR
} else {
    Write-Host "[SKIP] Frontend directory not found at $FRONTEND_DIR" -ForegroundColor Red
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Running!" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:8000 (docs: /docs)" -ForegroundColor White
Write-Host "  Frontend: http://localhost:8501" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
