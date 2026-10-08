import os
import sys
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))

from detective_core import (
    DetectiveDigitalEngine,
    TipoMaterial,
    TipoViolacion,
    QueryBuilderAnexoV,
    AutomatedSourceMonitor,
    GazetteScraperProcessor
)

app = FastAPI(
    title="Detective Digital OSINT API",
    description="Motor de Agregación de Prensa, Wikipedia y Cadena de Custodia Forense",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = DetectiveDigitalEngine(workspace_path="/tmp/detective_workspace")
monitor_manager = AutomatedSourceMonitor(engine)
gazette_processor = GazetteScraperProcessor(engine)

# ==========================================
# UTILIDADES DE CONSULTA EXTERNA EN VIVO
# ==========================================
def fetch_url(url: str, timeout: int = 8) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DetectiveDigital/2.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")

def consultar_wikipedia(termino: str) -> Optional[Dict[str, Any]]:
    """Consulta la API de Wikipedia para obtener datos biográficos y foto oficial verificada."""
    try:
        # 1. Búsqueda de página coincidente
        search_url = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(termino)}&format=json&origin=*"
        search_data = json.loads(fetch_url(search_url))
        
        if not search_data.get("query", {}).get("search"):
            return None

        titulo_pagina = search_data["query"]["search"][0]["title"]
        
        # 2. Resumen oficial
        summary_url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(titulo_pagina)}"
        summary_data = json.loads(fetch_url(summary_url))

        return {
            "titulo": summary_data.get("title", titulo_pagina),
            "descripcion": summary_data.get("description", "Figura Pública"),
            "extracto": summary_data.get("extract", ""),
            "foto_url": summary_data.get("thumbnail", {}).get("source", ""),
            "url_oficial": summary_data.get("content_urls", {}).get("desktop", {}).get("page", f"https://es.wikipedia.org/wiki/{urllib.parse.quote(titulo_pagina)}"),
            "fecha_edicion": summary_data.get("timestamp", "")
        }
    except Exception as e:
        print(f"Error consultando Wikipedia para '{termino}': {e}")
        return None

def consultar_prensa_en_vivo(termino: str, max_articulos: int = 10) -> List[Dict[str, Any]]:
    """Consulta el feed de Google News para Venezuela y extrae artículos de prensa reales."""
    articulos = []
    try:
        encoded_q = urllib.parse.quote(termino)
        # Feed RSS de Google News Venezuela
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=es-419&gl=VE&ceid=VE:es-419"
        xml_data = fetch_url(rss_url)

        root = ET.fromstring(xml_data)
        for item in root.findall(".//item")[:max_articulos]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            source_el = item.find("source")
            medio = source_el.text if source_el is not None else "Prensa"

            # Limpiar nombre del medio en el título si viene duplicado
            if " - " in title:
                titulo_limpio = title.rsplit(" - ", 1)[0]
            else:
                titulo_limpio = title

            articulos.append({
                "titulo": titulo_limpio,
                "medio": medio,
                "url": link,
                "fecha": pub_date
            })
    except Exception as e:
        print(f"Error consultando prensa para '{termino}': {e}")

    return articulos

# ==========================================
# ENDPOINTS REST DE LA APLICACIÓN
# ==========================================
@app.get("/api/health")
def health_check():
    return {"status": "online", "mode": "Live OSINT Connector", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/investigar")
def investigar_entidad(q: str = Query(..., description="Nombre o término a investigar")):
    """
    Endpoint principal: Agrega datos de Wikipedia + Prensa en Vivo de Venezuela.
    Alimenta los perfiles con cobertura periodística real y fuentes oficiales.
    """
    termino = q.strip()
    if not termino:
        raise HTTPException(status_code=400, detail="Debe proporcionar un término de búsqueda.")

    # 1. Datos biográficos y foto oficial
    datos_wiki = consultar_wikipedia(termino)

    # 2. Artículos de prensa en vivo relacionados
    articulos_prensa = consultar_prensa_en_vivo(termino, max_articulos=12)

    # Si no se encontró ni en Wikipedia ni en noticias
    if not datos_wiki and not articulos_prensa:
        return {
            "encontrado": False,
            "termino": termino,
            "mensaje": f"No se encontraron registros verificados en fuentes abiertas para '{termino}'. Por rigor metodológico, no se generan datos ficticios."
        }

    # 3. Compilar el perfil periodístico enriquecido
    perfil_consolidado = {
        "encontrado": True,
        "termino_busqueda": termino,
        "nombre_oficial": datos_wiki["titulo"] if datos_wiki else termino,
        "cargo_descripcion": datos_wiki["descripcion"] if datos_wiki else "Tema en cobertura de prensa reciente",
        "resumen_biografico": datos_wiki["extracto"] if datos_wiki else "",
        "fotografia_url": datos_wiki["foto_url"] if datos_wiki else "",
        "fuente_primaria_url": datos_wiki["url_oficial"] if datos_wiki else (articulos_prensa[0]["url"] if articulos_prensa else ""),
        "total_articulos_prensa": len(articulos_prensa),
        "cobertura_prensa": articulos_prensa,
        "medios_que_reportan": list({a["medio"] for a in articulos_prensa if a["medio"]})
    }

    return perfil_consolidado

@app.get("/api/feeds")
def obtener_feeds_en_vivo(filtro: Optional[str] = None):
    """Devuelve despachos de prensa en vivo para las tres columnas de contraste."""
    q = filtro.strip() if filtro else "Venezuela"
    articulos = consultar_prensa_en_vivo(q, max_articulos=25)

    # Clasificar según tipo de medio
    medios_oficiales_keywords = ["avn", "vtv", "últimas noticias", "ultimas noticias", "correo del orinoco", "vea", "mpprijp"]
    medios_internacionales_keywords = ["reuters", "associated press", "ap", "afp", "bbc", "el país", "el pais", "dw", "infobae", "cnn"]

    independientes = []
    oficiales = []
    internacionales = []

    for a in articulos:
        m_lower = a["medio"].lower()
        if any(k in m_lower for k in medios_oficiales_keywords):
            oficiales.append(a)
        elif any(k in m_lower for k in medios_internacionales_keywords):
            internacionales.append(a)
        else:
            independientes.append(a)

    return {
        "filtro_aplicado": q,
        "independientes": independientes,
        "oficiales": oficiales,
        "internacionales": internacionales
    }
