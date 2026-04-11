@echo off
echo Starting SAP Master Data Chatbot Stack...

:: Activate the Python environment from the backend
call backend\.venv\Scripts\activate.bat

:: Install Frontend Dependencies
echo Installing UI Requirements...
pip install -r frontend\requirements.txt

:: Start Backend (Uvicorn)
echo Starting FastAPI Backend on port 8000...
start "SAP Chatbot Backend" cmd /k "cd backend && uvicorn app.main:app --reload"

:: Start Frontend (Streamlit)
echo Starting Streamlit UI...
timeout /t 3 /nobreak >nul
cd frontend
streamlit run app.py

pause