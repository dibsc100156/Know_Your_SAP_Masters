#!/usr/bin/env bash
# SAP Masters 5-Pillar RAG — Quick Start
# ======================================
# Seeds vector stores and starts both backend (FastAPI) and frontend (Streamlit).
# Run from: SAP_HANA_LLM_VendorChatbot/backend/

set -e

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BACKEND_DIR"

echo "=================================================="
echo "  SAP Masters — 5-Pillar RAG"
echo "=================================================="
echo ""

# Detect Python
PYTHON="${PYTHON:-python}"
echo "[ENV] Using: $PYTHON"
echo ""

# Step 1: Check dependencies
echo "[1/4] Checking dependencies..."
$PYTHON -c "fastapi; uvicorn; qdrant_client; chromadb; sentence_transformers; networkx; pydantic" 2>/dev/null || {
    echo "[WARN] Some dependencies missing. Install with:"
    echo "       pip install -r requirements.txt"
    echo ""
}

# Step 2: Seed vector stores
echo "[2/4] Seeding vector stores..."
$PYTHON seed_all.py --stats
echo ""

# Step 3: Start FastAPI backend
echo "[3/4] Starting FastAPI on http://localhost:8000"
echo "       Docs: http://localhost:8000/docs"
echo ""
$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Step 4: Start Streamlit frontend
echo "[4/4] Starting Streamlit on http://localhost:8501"
echo ""
cd ../frontend
$PYTHON -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
FRONTEND_PID=$!

echo ""
echo "=================================================="
echo "  Running!"
echo "  Backend: http://localhost:8000"
echo "  Frontend: http://localhost:8501"
echo "  Press Ctrl+C to stop both"
echo "=================================================="

# Wait and clean up
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
