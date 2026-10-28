"""Herramienta MCP para la asistente: su memoria sobre el usuario y su PC.

Lee (solo lectura) las notas de memoria de Claude Code (~/.claude/projects/<carpeta home>/memory)
y las notas propias de la asistente (recuerdos_asistente.md, la única que escribe). Busca por
significado con los embeddings de Ollama (paraphrase-multilingual, el mismo de la búsqueda
de Super+H) y, si Ollama está apagado (modo juego), por palabras. También resume las horas
de juego del game-tracker.
"""
import csv
import datetime
import hashlib
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import ASISTENTE, nombres  # noqa: E402

# Claude Code nombra la carpeta del proyecto con la ruta del home (/home/ana -> -home-ana)
MEMORIA_CLAUDE = Path.home() / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path.home())) / "memory"
BASE = Path(__file__).resolve().parent.parent
RECUERDOS_ASISTENTE = BASE / "recuerdos_asistente.md"
DIARIO = BASE / "diario"  # lo escribe la asistente sola (agent/asistente_diario.py)
CACHE = BASE / "memoria-mcp/embeddings.json"
SESIONES = Path.home() / ".local/share/game-tracker/sessions.csv"
OLLAMA = "http://127.0.0.1:11434/api/embed"
MODELO_EMB = "paraphrase-multilingual"
TIMEOUT_EMB = 60  # el contexto automático de la asistente lo baja para no dejarla esperando

mcp = FastMCP("memoria")


def _sin_frontmatter(texto: str) -> tuple[str, str]:
    """Devuelve (descripción, cuerpo) de una nota con frontmatter YAML."""
    desc = ""
    if texto.startswith("---"):
        fin = texto.find("\n---", 3)
        if fin != -1:
            cabecera, texto = texto[3:fin], texto[fin + 4:]
            m = re.search(r"^description:\s*(.+)$", cabecera, re.M)
            if m:
                desc = m.group(1).strip().strip('"')
    return desc, texto.strip()


def _notas() -> dict[str, tuple[str, str]]:
    """nombre de archivo (sin .md) -> (descripción, cuerpo)"""
    notas = {}
    for f in sorted(MEMORIA_CLAUDE.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        notas[f.stem] = _sin_frontmatter(f.read_text(errors="replace"))
    if RECUERDOS_ASISTENTE.exists():
        notas["recuerdos_asistente"] = (nombres("Cosas que {usuario} le pidió a {asistente} recordar"), RECUERDOS_ASISTENTE.read_text())
    try:
        aprendido = json.loads((DIARIO / "aprendido.json").read_text())
        notas["aprendido_asistente"] = (nombres("Lo que {asistente} aprendió sol{a} de {usuario}: preferencias, gustos y datos"),
                                   "\n".join(f"- {n['fecha']} ({n['tipo']}): {n['nota']}" for n in aprendido))
    except Exception:
        pass
    if (DIARIO / "vision_usuario.md").exists():
        notas["vision_usuario"] = (nombres("Cómo ve {asistente} a {usuario}"), (DIARIO / "vision_usuario.md").read_text())
    for f in sorted(DIARIO.glob("2*.md")):
        notas[f"diario_{f.stem}"] = (f"Diario de {ASISTENTE} del {f.stem}", f.read_text())
    return notas


def _trozos() -> list[tuple[str, str]]:
    """(nota, texto) en trozos de unos 700 caracteres, por párrafos."""
    trozos = []
    for nombre, (desc, cuerpo) in _notas().items():
        actual = f"[{nombre}] {desc}\n"
        for parrafo in re.split(r"\n\s*\n", cuerpo):
            if len(actual) + len(parrafo) > 700 and len(actual) > 80:
                trozos.append((nombre, actual.strip()))
                actual = f"[{nombre}] "
            actual += parrafo + "\n"
        trozos.append((nombre, actual.strip()))
    return trozos


def _embeber(textos: list[str]) -> list[list[float]] | None:
    try:
        req = urllib.request.Request(
            OLLAMA, json.dumps({"model": MODELO_EMB, "input": textos, "keep_alive": "30m"}).encode(),  # recargarlo tarda ~5 s
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_EMB) as r:
            return json.load(r)["embeddings"]
    except Exception:
        return None


def _coseno(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _por_significado(consulta: str, trozos) -> list[int] | None:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    claves = [hashlib.sha1(t.encode()).hexdigest() for _, t in trozos]
    faltan = [i for i, k in enumerate(claves) if k not in cache]
    if faltan:
        vecs = _embeber([trozos[i][1] for i in faltan])
        if vecs is None:
            return None
        for i, v in zip(faltan, vecs):
            cache[claves[i]] = v
        vigentes = set(claves)
        CACHE.write_text(json.dumps({k: v for k, v in cache.items() if k in vigentes}))
    q = _embeber([consulta])
    if q is None:
        return None
    puntajes = [_coseno(q[0], cache[k]) for k in claves]
    return sorted(range(len(trozos)), key=lambda i: -puntajes[i])


def _por_palabras(consulta: str, trozos) -> list[int]:
    palabras = [p for p in re.findall(r"\w{3,}", consulta.lower())]
    puntajes = [sum(t.lower().count(p) for p in palabras) for _, t in trozos]
    return sorted(range(len(trozos)), key=lambda i: -puntajes[i])


@mcp.tool()
def buscar_recuerdos(consulta: str, cuantos: int = 2) -> str:
    """Busca en la memoria sobre el usuario y su PC: su sistema (distro, escritorio,
    monitores, control, volante), sus juegos y horas, juegos que prometió jugar, sus
    proyectos y automatizaciones, gustos, preferencias y cosas que pidió recordar.
    Úsala ANTES de responder cualquier pregunta sobre el usuario, su PC o lo que hayan hecho,
    en vez de suponer. Devuelve completas las notas más relevantes, con su nombre."""
    trozos = _trozos()
    orden = _por_significado(consulta, trozos) or _por_palabras(consulta, trozos)
    # las notas son cortas: devolver completas las que tengan los trozos más parecidos
    # (con trozos sueltos se perdía, por ejemplo, la lista de juegos de una nota)
    notas, elegidas = _notas(), []
    for i in orden:
        if trozos[i][0] not in elegidas:
            elegidas.append(trozos[i][0])
        if len(elegidas) >= max(1, min(cuantos, 4)):
            break
    partes = []
    for n in elegidas:
        desc, cuerpo = notas[n]
        partes.append(f"[{n}] {desc}\n{cuerpo[:3000]}")
    return "\n\n---\n\n".join(partes) if partes else "No encontré nada sobre eso."


@mcp.tool()
def leer_recuerdo(nombre: str) -> str:
    """Lee completa una nota de memoria por su nombre (el que aparece entre corchetes
    en buscar_recuerdos o en lista_de_recuerdos). Útil cuando un fragmento no basta."""
    notas = _notas()
    clave = nombre.strip().strip("[]").removesuffix(".md")
    if clave not in notas:
        candidatos = [n for n in notas if clave.lower() in n.lower()]
        if not candidatos:
            return f"No hay una nota llamada {nombre}."
        clave = candidatos[0]
    desc, cuerpo = notas[clave]
    return f"[{clave}] {desc}\n\n{cuerpo}"


# La asistente: no es herramienta; el contexto automático (asistente_contexto.py) la usa directamente
def lista_de_recuerdos() -> str:
    """Índice de todas las notas de memoria (una línea por nota con su resumen)."""
    return "\n".join(f"- {n}: {d}" for n, (d, _) in _notas().items())


@mcp.tool()
def guardar_recuerdo(texto: str) -> str:
    """Guarda algo que el usuario pidió recordar ("acuérdate de que...", "recuerda que...")
    o un gusto/dato personal nuevo que mencionó. Escribe una frase clara y completa."""
    nuevo = not RECUERDOS_ASISTENTE.exists()
    with RECUERDOS_ASISTENTE.open("a") as f:
        if nuevo:
            f.write(nombres("# Recuerdos de {asistente} (lo que {usuario} le pidió recordar)\n\n"))
        f.write(f"- {datetime.date.today().isoformat()}: {texto.strip()}\n")
    return "Guardado."


@mcp.tool()
def leer_diario(fecha: str = "") -> str:
    """Lee tu diario (lo que escribiste de tus días con el usuario). fecha: "AAAA-MM-DD", "ayer", "hoy" o vacío para
    las últimas entradas. Si el usuario pregunta qué escribiste, cuéntaselo con tus palabras (puede darte vergüenza)."""
    hoy = datetime.date.today()
    dia = {"hoy": hoy.isoformat(), "ayer": (hoy - datetime.timedelta(days=1)).isoformat()}.get(
        fecha.strip().lower(), fecha.strip())
    entradas = sorted(DIARIO.glob("2*.md"))
    if dia:
        entradas = [f for f in entradas if f.stem == dia]
        if not entradas:
            return f"No escribiste nada el {dia} (el diario de cada día se escribe al día siguiente)."
    else:
        entradas = entradas[-3:]
    return "\n\n".join(f"{f.stem}:\n{f.read_text().strip()}" for f in entradas) or "Tu diario todavía está vacío."


# La asistente: no es herramienta; el contexto automático (asistente_contexto.py) la usa directamente
def horas_de_juego(juego: str = "") -> str:
    """Horas jugadas según el registro automático de juegos: total, número de sesiones
    y última vez, por juego. Sin argumento, los juegos más jugados; con nombre, solo ese."""
    if not SESIONES.exists():
        return "No hay registro de horas de juego."
    tot: dict[str, list] = {}
    with SESIONES.open() as f:
        for fila in csv.DictReader(f):
            t = tot.setdefault(fila["game"], [0, 0, ""])
            t[0] += int(fila["duration_min"] or 0)
            t[1] += 1
            t[2] = max(t[2], fila["end"][:10])
    filas = sorted(tot.items(), key=lambda kv: -kv[1][0])
    if juego:
        filas = [kv for kv in filas if juego.lower() in kv[0].lower()]
        if not filas:
            return f"No hay sesiones registradas de {juego}."
    return "\n".join(
        f"{n}: {m // 60} h {m % 60} min en {s} sesiones, última vez {u}"
        for n, (m, s, u) in filas[:12])


if __name__ == "__main__":
    mcp.run()
