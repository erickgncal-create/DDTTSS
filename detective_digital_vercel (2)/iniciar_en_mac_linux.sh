#!/bin/bash
echo "=============================================================="
echo "  INICIANDO SERVIDOR DETECTIVE DIGITAL OSINT (LOCAL)"
echo "=============================================================="
echo "Instalando / verificando dependencias..."
pip install -r requirements.txt
echo "Abriendo navegador en http://localhost:8000..."
python3 -m webbrowser "http://localhost:8000" &
uvicorn api.index:app --host 127.0.0.1 --port 8000 --reload
