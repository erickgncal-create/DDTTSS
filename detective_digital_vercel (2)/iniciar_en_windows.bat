@echo off
title Detective Digital OSINT Server
echo ==============================================================
echo   INICIANDO SERVIDOR DETECTIVE DIGITAL OSINT (LOCAL)
echo ==============================================================
echo Verificando dependencias...
python -m pip install -r requirements.txt
echo.
echo Abriendo aplicacion en tu navegador...
start http://localhost:8000
python -m uvicorn api.index:app --host 127.0.0.1 --port 8000 --reload
pause
