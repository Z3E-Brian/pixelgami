"""Los modelos que se pueden poner a hacer de router en la evaluación, todos con la firma del núcleo
(asistente_contexto._qwen_json): modelo(sistema, texto, esquema) -> dict | None, salida JSON con ese esquema y
None si no respondió.

  --modelo qwen3:8b                  Ollama local (también "ollama:qwen3:8b"): el mismo _qwen_json del núcleo
  --modelo gemini:gemini-3.5-flash   Gemini por su API; la clave, como en servidor.sh: GEMINI_API_KEY o
                                     ~/.config/pixelgami/gemini.key
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

Modelo = Callable[[str, str, dict], dict | None]

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
CLAVE_GEMINI = Path.home() / ".config/pixelgami/gemini.key"
ESPERA = 60  # segundos: Gemini a veces se satura


def clave_gemini() -> str:
    """La clave de Gemini: GEMINI_API_KEY o el archivo de ~/.config/pixelgami (nunca en el repo)."""
    clave = os.environ.get("GEMINI_API_KEY") or (CLAVE_GEMINI.read_text().strip() if CLAVE_GEMINI.exists() else "")
    if not clave:
        raise SystemExit(f"Falta la clave de Gemini: GEMINI_API_KEY o {CLAVE_GEMINI} (ver docs/CONECTAR.md).")
    return clave


def gemini(nombre: str, clave: str, url: str = GEMINI) -> Modelo:
    """Gemini con salida JSON (responseJsonSchema) y temperatura 0, como el router local."""
    def modelo(sistema: str, texto: str, esquema: dict) -> dict | None:
        cuerpo = {"systemInstruction": {"parts": [{"text": sistema}]},
                  "contents": [{"role": "user", "parts": [{"text": texto}]}],
                  "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                       "responseJsonSchema": esquema}}
        req = urllib.request.Request(url.format(modelo=nombre), json.dumps(cuerpo).encode(),
                                     {"Content-Type": "application/json", "x-goog-api-key": clave})
        try:
            with urllib.request.urlopen(req, timeout=ESPERA) as r:
                return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:  # 429: se acabó la cuota del minuto (usa --pausa)
            print(f"  (Gemini respondió {e.code}: {e.read()[:200]!r})")
        except (OSError, ValueError, KeyError, IndexError) as e:
            print(f"  (Gemini no respondió: {e})")
        return None
    return modelo


def elegir(nombre: str, local: Callable[[str], Modelo]) -> tuple[str, Modelo]:
    """(nombre para el reporte, el modelo) a partir de lo que se pasó en --modelo. local(nombre) arma el de Ollama
    (en pruebas_intencion.py, el _qwen_json del núcleo con ese nombre)."""
    proveedor, _, resto = nombre.partition(":")
    if proveedor == "gemini":
        if not resto:
            raise SystemExit("Di cuál Gemini: --modelo gemini:<modelo> (el de conf.yaml está en gemini_llm.model).")
        return f"gemini:{resto}", gemini(resto, clave_gemini())
    nombre_local = resto if proveedor == "ollama" else nombre
    return f"ollama:{nombre_local}", local(nombre_local)
