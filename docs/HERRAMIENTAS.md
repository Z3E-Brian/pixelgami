# Crear una herramienta (MCP)

Una herramienta de un **servidor MCP** es algo que el modelo decide usar por su cuenta mientras responde: un
programa aparte que expone funciones con su descripción. Los de este repo (`acciones-mcp/`, `google-mcp/`,
`musica-mcp/`, `memoria-mcp/`, `claude-mcp/`) son ejemplos completos. Agregar una propia no toca el código de la
asistente.

> **¿Función o herramienta?** Para enseñarle algo nuevo, lo normal es una **función**
> ([FUNCIONES.md](FUNCIONES.md)). La entiende el router antes de responder, así que funciona bien con un modelo
> local chico, que decide mal cuándo usar una herramienta. Una herramienta MCP conviene cuando usas un modelo
> grande (Gemini) o cuando quieres compartirla con otros programas que hablan MCP.

> **Seguridad**: una herramienta corre con tus permisos (puede leer tus archivos o ejecutar comandos). Revisa el
> código de cualquier herramienta antes de instalarla, y en las tuyas limita lo que pueden hacer (lista blanca de
> acciones, confirmación para lo que no se puede deshacer).

## 1. El servidor

`clima-mcp/servidor_clima.py`:

```python
"""Herramienta MCP para la asistente: el clima de una ciudad (wttr.in)."""
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import LUGAR  # noqa: E402

mcp = FastMCP("clima")


@mcp.tool()
def clima(ciudad: str = "") -> str:
    """El clima actual y de hoy en una ciudad (vacío = donde vive el usuario). Úsala cuando pregunte por el
    clima, la temperatura o si va a llover."""
    lugar = urllib.parse.quote(ciudad or LUGAR)
    with urllib.request.urlopen(f"https://wttr.in/{lugar}?format=3&lang=es", timeout=10) as r:
        return r.read().decode().strip()


if __name__ == "__main__":
    mcp.run()
```

La **descripción** (el docstring) es lo que lee el modelo para decidir cuándo usarla: di qué hace y cuándo
usarla, en una o dos frases. Los textos que van al modelo usan los marcadores de `identidad.py` (`{usuario}`,
`{asistente}`…) y pasan por `nombres()`; nunca escribas nombres de personas a mano.

## 2. Registrarlo

En `Open-LLM-VTuber/mcp_servers.json`:

```json
"clima": {
  "command": "~/.local/share/pixelgami/Open-LLM-VTuber/.venv/bin/python",
  "args": ["~/.local/share/pixelgami/clima-mcp/servidor_clima.py"],
  "timeout": 30
}
```

Y actívalo en `conf.yaml` → `mcp_enabled_servers: [..., "clima"]`. Si necesita librerías nuevas:
`cd Open-LLM-VTuber && uv add <paquete>`.

## 3. Que el router lo entienda (si hace falta)

Un modelo grande decide solo cuándo llamar la herramienta. Uno local chico (Qwen3 8B) a veces no: por eso
`asistente_contexto.py` tiene un **router** que clasifica cada mensaje en temas (`ventanas`, `correo`, `musica`,
`web`, `pc`, `hora_mundo`, `charla`) y prepara los datos antes de responder. Para una herramienta de consulta
como el clima, lo más simple es:

1. Agregar el tema al prompt `ROUTER` (con 2-3 ejemplos de frases) y a `ESQUEMA_ROUTER`.
2. En `preparar()`, si el tema está en `r["temas"]`, llamar la función y agregar el resultado a `partes`.
3. Sumar casos a `pruebas_intencion.py` (10-15 formas distintas de pedirlo) y correrlas:
   `cd Open-LLM-VTuber && uv run python ../pruebas_intencion.py`.

Un sistema de plugins que haga esto solo (una carpeta con `plugin.yaml`: tema, ejemplos y pruebas) está en los
planes; si te interesa, abre un issue.
