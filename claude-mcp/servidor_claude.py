"""Herramienta MCP para la asistente: hacerle consultas a Claude Code (claude -p).

Claude corre en modo solo lectura (buscar en la web, leer archivos y configs);
no puede ejecutar comandos ni modificar nada. Gasta de la cuota de Claude.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import nombres  # noqa: E402

CLAUDE = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
INSTRUCCIONES = (
    nombres("Te consulta {asistente}, {la_asistente} de voz de escritorio de {usuario}, que leerá tu "
    "respuesta en voz alta. Responde en español, breve y al grano (máximo unas "
    "6 frases), sin markdown, tablas, listas largas ni bloques de código.")
)

mcp = FastMCP("claude")


@mcp.tool()
def preguntar_a_claude(pregunta: str) -> str:
    """Consulta a Claude (una IA más potente, con acceso de solo lectura al PC
    del usuario y a internet) y devuelve su respuesta. Úsala cuando el usuario pida
    expresamente preguntarle a Claude, o para dudas técnicas, de programación,
    de su sistema Linux/Hyprland, de sus juegos/mods o que requieran investigar.
    Pasa la pregunta completa con todo el contexto necesario. Tarda hasta ~2 min."""
    try:
        r = subprocess.run(
            [
                CLAUDE, "-p", pregunta,
                "--output-format", "text",
                "--model", "sonnet",
                "--allowedTools", "WebSearch", "WebFetch", "Read", "Grep", "Glob",
                "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit",
                "--append-system-prompt", INSTRUCCIONES,
            ],
            cwd=Path.home(),
            capture_output=True,
            text=True,
            timeout=170,
        )
    except subprocess.TimeoutExpired:
        return "Claude tardó demasiado en responder."
    if r.returncode != 0:
        return f"Claude falló: {(r.stderr or r.stdout).strip()[:300]}"
    return r.stdout.strip()


if __name__ == "__main__":
    mcp.run()
