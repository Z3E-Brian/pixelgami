"""Herramienta MCP para la asistente: acciones concretas en el PC del usuario.

Solo acciones de esta lista (no hay comandos libres): abrir juegos, apps y proyectos,
retomar conversaciones de Claude en una terminal, cerrar ventanas (con confirmación) y
ver el estado del sistema. Todo lo que se abre va en su propio scope de systemd en
app.slice, como lo que abre el usuario (si no, systemd-oomd podría llevarse el escritorio).
Cada acción y cada sugerencia aceptada o rechazada queda en habitos.jsonl, para que
La asistente aprenda qué suele querer el usuario según el día y la hora.
"""
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import ASISTENTE, PERFIL, USUARIO, nombres  # noqa: E402

HOME = Path.home()
BASE = Path(__file__).resolve().parent.parent
HABITOS = BASE / "habitos.jsonl"
STEAMAPPS = HOME / ".local/share/Steam/steamapps"
PROYECTOS = [HOME / c for c in PERFIL.get("carpetas_proyectos", ["Documentos/GitHub", "Proyectos"])]
DIRS_DESKTOP = [
    HOME / ".local/share/applications", Path("/usr/share/applications"),
    HOME / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
]
CLAUDE = HOME / ".local/bin/claude"
SESIONES_CLAUDE = HOME / ".claude/projects"
NO_SON_JUEGOS = re.compile(r"Proton|Steam Linux Runtime|Steamworks|Wallpaper Engine|Redistributable", re.I)
SCOPE = ["systemd-run", "--user", "--scope", "--slice=app.slice", "--collect", "--quiet"]
# nombres comunes -> la app que usa el usuario (ganan a la búsqueda aproximada); ver perfil.yaml
ALIAS_APPS = PERFIL.get("alias_apps", {})
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

mcp = FastMCP("acciones")


def _entorno_de_la_sesion() -> None:
    """El cliente MCP lanza este servidor solo con PATH, HOME y poco más: sin el bus de
    systemd ni Wayland/Hyprland, systemd-run y gtk-launch fallan en silencio. Se toma el
    entorno de la sesión gráfica del systemd del usuario (Hyprland lo exporta ahí)."""
    uid = os.getuid()
    os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    r = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True)
    for linea in r.stdout.splitlines():
        clave, _, valor = linea.partition("=")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


_entorno_de_la_sesion()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _elegir(nombre: str, opciones: dict[str, object]):
    """La opción cuyo nombre normalizado contiene al buscado (o al revés), la más corta."""
    n = _norm(nombre)
    hits = [k for k in opciones if n and (n in _norm(k) or _norm(k) in n)]
    return opciones[min(hits, key=len)] if hits else None


def _lanzar(cmd: list[str], cwd: Path | None = None, escritorio: str = "") -> None:
    """Lanza en su scope; con escritorio, por Hyprland con la regla de ese workspace
    (sin cambiar de escritorio al usuario)."""
    if escritorio.strip():
        linea = shlex.join(SCOPE + cmd)
        if cwd:
            linea = f"cd {shlex.quote(str(cwd))} && {linea}"
        orden = (f"hl.dsp.exec_cmd({json.dumps(linea, ensure_ascii=False)}, "
                 f"{{ workspace = {json.dumps(escritorio.strip() + ' silent')} }})")
        subprocess.run(["hyprctl", "dispatch", orden], capture_output=True)
        return
    subprocess.Popen(SCOPE + cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _anotar(tipo: str, detalle: str, **extra) -> None:
    ahora = datetime.datetime.now()
    fila = {"fecha": ahora.isoformat(timespec="minutes"), "dia": DIAS[ahora.weekday()],
            "hora": ahora.hour, "tipo": tipo, "detalle": detalle, **extra}
    with HABITOS.open("a") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _juegos() -> dict[str, str]:
    """nombre -> appid de los juegos instalados en Steam"""
    juegos = {}
    for f in STEAMAPPS.glob("appmanifest_*.acf"):
        t = f.read_text(errors="replace")
        nombre = re.search(r'"name"\s+"([^"]+)"', t)
        appid = re.search(r'"appid"\s+"(\d+)"', t)
        if nombre and appid and not NO_SON_JUEGOS.search(nombre.group(1)):
            juegos[nombre.group(1)] = appid.group(1)
    return juegos


def _monitor(pantalla: str) -> dict | None:
    """'principal' (la de 0,0) o 'segunda'/'secundaria'/'vertical'/'2' -> monitor de Hyprland."""
    r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True)
    try:
        mons = json.loads(r.stdout or "[]")
    except ValueError:
        return None
    if not pantalla.strip() or not mons:
        return None
    principal = min(mons, key=lambda m: (m["x"] != 0 or m["y"] != 0, m["id"]))
    otras = [m for m in mons if m is not principal]
    p = _norm(pantalla)
    por_nombre = next((m for m in mons if _norm(m["name"]) == p), None)
    if por_nombre:
        return por_nombre
    if p in ("principal", "1", "primera", "main") or not otras:
        return principal
    return otras[0]


def _mover_cuando_aparezca(clase: str, antes: set[str], escritorio: str, segundos: int = 25,
                           monitor: str = "") -> None:
    """Respaldo de la regla de escritorio: apps como Discord o Steam abren la ventana real
    desde otro proceso (su lanzador), así que la regla de exec_cmd no les llega. Espera
    la ventana nueva de esa app y la lleva al escritorio pedido."""
    def vigilar():
        n = _norm(clase)
        fin = time.time() + segundos
        while time.time() < fin:
            time.sleep(0.5)
            for c in _clientes():
                if c["address"] in antes or not n or n not in _norm(c.get("class", "")):
                    continue
                if str(c["workspace"]["name"]) != escritorio:
                    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ workspace = "{escritorio}", '
                                    f'follow = false, window = "address:{c["address"]}" }})'], capture_output=True)
                if monitor:  # el escritorio se crea en la pantalla enfocada: llevarlo a la pedida
                    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.workspace.move({{ workspace = "{escritorio}", '
                                    f'monitor = "{monitor}" }})'], capture_output=True)
                return
    threading.Thread(target=vigilar, daemon=True).start()


def _clase_de(entrada: str) -> str:
    """StartupWMClass del .desktop (o su nombre) para reconocer la ventana de la app."""
    for d in DIRS_DESKTOP:
        f = d / f"{entrada}.desktop"
        if f.exists():
            m = re.search(r"^StartupWMClass=(.+)$", f.read_text(errors="replace"), re.M)
            return m.group(1).strip() if m else entrada
    return entrada


def _apps() -> dict[str, str]:
    """nombre visible -> id del .desktop (los primeros directorios tienen prioridad)"""
    apps: dict[str, str] = {}
    for d in DIRS_DESKTOP:
        for f in d.glob("*.desktop"):
            t = f.read_text(errors="replace")
            principal = t.split("\n[Desktop Action")[0]
            if re.search(r"^(NoDisplay|Hidden)=true", principal, re.M):
                continue
            m = re.search(r"^Name=(.+)$", principal, re.M)
            if m and m.group(1) not in apps:
                apps[m.group(1).strip()] = f.stem
            # también por su descripción genérica y palabras clave ("terminal" -> kitty)
            for campo in ("GenericName",):  # Keywords no: la de Claude incluye "code"
                g = re.search(rf"^{campo}=(.+)$", principal, re.M)
                for alias in (g.group(1).split(";") if g else []):
                    if alias.strip() and alias.strip() not in apps:
                        apps[alias.strip()] = f.stem
    return apps


EMB_URL = "http://127.0.0.1:11434/api/embed"
EMB_CACHE = BASE / "acciones-mcp/apps_embeddings.json"
UMBRAL_APP = 0.47  # aciertos 0,49-0,85; lo dudoso ~0,44 (y casi siempre rofi)
VENTAJA_APP = 0.05  # el primero tiene que despegarse del segundo


def _apps_descritas() -> dict[str, str]:
    """id del .desktop -> lo que la app dice de sí misma (en español si lo trae): nombre,
    tipo, descripción y categorías. Sirve para buscar por significado."""
    vistas: dict[str, str] = {}
    for d in DIRS_DESKTOP:
        for f in d.glob("*.desktop"):
            if f.stem in vistas:
                continue
            t = f.read_text(errors="replace").split("\n[Desktop Action")[0]
            if re.search(r"^(NoDisplay|Hidden)=true", t, re.M) or not re.search(r"^Name=", t, re.M):
                continue
            partes = []
            for campo in ("Name", "GenericName", "Comment", "Keywords"):
                for clave in (f"{campo}[es]", campo):
                    m = re.search(rf"^{re.escape(clave)}=(.+)$", t, re.M)
                    if m:
                        partes.append(m.group(1).replace(";", ", "))
                        break
            cat = re.search(r"^Categories=(.+)$", t, re.M)
            if cat and re.search(r"\bGame\b", cat.group(1)) or f.stem in ("rofi", "rofi-theme-selector"):
                continue  # los juegos se abren por nombre; rofi (el lanzador) se parece a todo
            if re.search(r"^Exec=.*\b(pkexec|sudo|kdesu|gksu)\b", t, re.M) or re.search(r"^X-KDE-SubstituteUID=true", t, re.M) or "btrfs" in f.stem.lower():
                continue  # herramientas de administrador (piden contraseña): solo por su nombre
            if cat:
                partes.append(cat.group(1).replace(";", " "))
            vistas[f.stem] = ". ".join(partes)
    return vistas


def _embeber(textos: list[str]) -> list[list[float]] | None:
    try:
        import urllib.request
        req = urllib.request.Request(EMB_URL, json.dumps({"model": "paraphrase-multilingual", "input": textos,
                                                          "keep_alive": "30m"}).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)["embeddings"]
    except Exception:
        return None


def _por_significado(pedido: str) -> str | None:
    """La app cuya descripción más se parece a lo pedido ("explorador", "algo para ver
    fotos"), si supera el umbral. Las descripciones se guardan ya convertidas en caché."""
    import hashlib, math
    apps = _apps_descritas()
    cache = json.loads(EMB_CACHE.read_text()) if EMB_CACHE.exists() else {}
    claves = {i: hashlib.sha1(t.encode()).hexdigest() for i, t in apps.items()}
    faltan = [i for i, k in claves.items() if k not in cache]
    if faltan:
        vecs = _embeber([apps[i] for i in faltan])
        if vecs is None:
            return None
        cache.update({claves[i]: v for i, v in zip(faltan, vecs)})
        EMB_CACHE.write_text(json.dumps({k: cache[k] for k in claves.values()}))
    q = _embeber([pedido])
    if not q:
        return None
    norma = lambda v: math.sqrt(sum(x * x for x in v)) or 1.0
    nq = norma(q[0])
    puntajes = sorted(((sum(a * b for a, b in zip(q[0], cache[claves[i]])) / (nq * norma(cache[claves[i]])), i)
                       for i in apps), reverse=True)
    (p1, mejor), p2 = puntajes[0], (puntajes[1][0] if len(puntajes) > 1 else 0)
    return mejor if p1 >= UMBRAL_APP and p1 - p2 >= VENTAJA_APP else None


def _alias(nombre: str) -> str:
    """Alias aunque venga con artículo o en singular ("el explorador de archivo")."""
    n = re.sub(r"^(el|la|los|las|un|una|mi|mis)", "", _norm(nombre))
    if n in ALIAS_APPS:
        return ALIAS_APPS[n]
    for clave in sorted(ALIAS_APPS, key=len, reverse=True):
        if len(clave) >= 6 and (clave in n or (len(n) >= 6 and n in clave)):
            return ALIAS_APPS[clave]
    return nombre


def resolver_app(nombre: str) -> str | None:
    """id del .desktop para lo que pidió el usuario: alias, nombre exacto, nombre parecido y,
    si nada de eso, por significado (no hace falta decir el nombre literal)."""
    apps = _apps()
    nombre = _alias(nombre)
    return apps.get(nombre) or _elegir(nombre, apps) or _por_significado(nombre)


def _clientes() -> list[dict]:
    r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "[]")
    except ValueError:  # sin Hyprland en el entorno (servidor lanzado fuera de la sesión)
        return []


ACTUAL = re.compile(r"(ventana\s+)?(actual|esta|esa|enfrente|de enfrente|que tengo|abierta ahora|enfocada|activa)|^(ventana|esto|eso)$", re.I)


def _ventana_actual() -> list[dict]:
    """La última ventana que usó el usuario (sin contar a la asistente), por historial de foco."""
    vistas = [c for c in _clientes() if c.get("class") != "open-llm-vtuber" and c.get("focusHistoryID", 99) >= 0
              and not str(c.get("workspace", {}).get("name", "")).startswith("special:asistenteoculta")]
    return sorted(vistas, key=lambda c: c.get("focusHistoryID", 99))[:1]


def _ventanas_de(nombre: str) -> list[dict]:
    """Ventanas abiertas de la app pedida (por su .desktop/clase, o por nombre o título).
    "La ventana actual" / "esta ventana" = la última que usó el usuario."""
    if ACTUAL.search(nombre.strip()):
        return _ventana_actual()
    entrada = resolver_app(nombre)
    clase = _norm(_clase_de(entrada)) if entrada else ""
    n = _norm(nombre)
    vistas = []
    for c in _clientes():
        k = _norm(c.get("class", ""))
        if c.get("class") == "open-llm-vtuber" or c.get("workspace", {}).get("name") == "special:asistenteoculta":
            continue  # las del escritorio oculto (Super+S) sí cuentan: se pueden sacar de ahí
        if (clase and (clase in k or k in clase)) or (entrada and _norm(entrada).endswith(k) and k) \
                or (n and (n in k or n in _norm(c.get("title", "")))):
            vistas.append(c)
    return vistas


def _mover(ventanas: list[dict], escritorio: str, pantalla: str) -> str:
    mon = _monitor(pantalla)
    if mon and not escritorio.strip():
        escritorio = str(mon["activeWorkspace"]["name"])
    if not escritorio.strip():
        return ""
    for c in ventanas:
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ workspace = "{escritorio}", follow = false, '
                        f'window = "address:{c["address"]}" }})'], capture_output=True)
    if mon:  # el escritorio puede existir en otra pantalla: llevarlo a la pedida
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.workspace.move({{ workspace = "{escritorio}", '
                        f'monitor = "{mon["name"]}" }})'], capture_output=True)
    return escritorio


@mcp.tool()
def mover_ventana(nombre: str, escritorio: str = "", pantalla: str = "") -> str:
    """Mueve una ventana YA ABIERTA (no abre otra) a un escritorio (workspace; "special:special"
    es el oculto de Super+S) y/o a una pantalla ("principal" o "segunda"). nombre: la app
    ("discord", "el explorador", "vs code") o "ventana actual" para la última que usó el usuario."""
    ventanas = _ventanas_de(nombre)
    if not ventanas:
        return f"No hay ninguna ventana de {nombre} abierta."
    ws = _mover(ventanas, escritorio, pantalla)
    if not ws:
        return "¿A qué escritorio o pantalla la muevo?"
    clase = ventanas[0]["class"]
    _anotar("accion", f"mover {clase} al escritorio {ws}")
    return f"Moví {clase} al escritorio {ws}" + (f" de la pantalla {pantalla}" if pantalla else "") + "."


@mcp.tool()
def abrir_juego(nombre: str) -> str:
    """Abre un juego de Steam por su nombre (aproximado: "mh wilds", "war thunder").
    Se abre donde lo ponga Steam (no se puede elegir escritorio)."""
    juegos = _juegos()
    appid = _elegir(nombre, juegos) or _elegir(nombre.replace("mh", "monster hunter"), juegos)
    if not appid:
        return f"No encontré {nombre} en Steam. Instalados: {', '.join(sorted(juegos))}."
    titulo = next(k for k, v in juegos.items() if v == appid)
    _lanzar(["steam", f"steam://rungameid/{appid}"])
    _anotar("accion", f"abrir juego {titulo}")
    return f"Abriendo {titulo}."


@mcp.tool()
def abrir_app(nombre: str, escritorio: str = "", pantalla: str = "") -> str:
    """Abre una aplicación instalada por su nombre (Discord, Opera, WhatsApp, YouTube
    Music, Steam, terminal...). escritorio: número del workspace, solo si el usuario lo pide
    ("en el 3"). pantalla: "principal" o "segunda", solo si la pide. Si ya estaba
    abierta, normalmente solo la trae."""
    apps = _apps()
    entrada = resolver_app(nombre)
    if not entrada:
        return f"No encontré la app {nombre}."
    titulo = next((k for k, v in apps.items() if v == entrada), entrada)
    if escritorio.strip() or pantalla.strip():
        abiertas = _ventanas_de(nombre)
        if abiertas:  # ya estaba abierta: llevarla al lugar pedido, no abrir otra
            ws = _mover(abiertas, escritorio, pantalla)
            _anotar("accion", f"mover {titulo} al escritorio {ws}")
            return f"{titulo} ya estaba abierta: la moví al escritorio {ws}."
    mon = _monitor(pantalla)
    if mon and not escritorio.strip():
        escritorio = str(mon["activeWorkspace"]["name"])
    if escritorio.strip():
        _mover_cuando_aparezca(_clase_de(entrada), {c["address"] for c in _clientes()}, escritorio.strip(),
                               monitor=mon["name"] if mon else "")
    _lanzar(["gtk-launch", entrada], escritorio=escritorio)
    donde = (f" en el escritorio {escritorio}" if escritorio else "") + (" de la segunda pantalla" if mon and pantalla and _norm(pantalla) not in ("principal", "1", "primera") else "")
    _anotar("accion", f"abrir app {titulo}{donde}")
    return f"Abriendo {titulo}{donde}."


@mcp.tool()
def abrir_proyecto(nombre: str, escritorio: str = "") -> str:
    """Abre VS Code en un repositorio/proyecto del usuario (nombre aproximado: dicho a
    medias o mal transcrito, p. ej. "tienda" = mi-tienda-web). Se abre en la pantalla donde esté el ratón, o en
    el workspace escritorio si el usuario lo pide."""
    repos = {p.name: p for base in PROYECTOS if base.exists() for p in base.iterdir() if p.is_dir()}
    ruta = _elegir(nombre, repos)
    if not ruta:
        return f"No encontré el proyecto {nombre}. Hay: {', '.join(sorted(repos))}."
    _lanzar(["code", "--new-window", str(ruta)], cwd=ruta, escritorio=escritorio)
    _anotar("accion", f"abrir proyecto {ruta.name}")
    return f"Abriendo VS Code en {ruta.name}."


def _resumen_sesion(f: Path) -> dict | None:
    cwd, primera = None, None
    try:
        with f.open(errors="replace") as fh:
            for i, linea in enumerate(fh):
                if i > 400:
                    break
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                cwd = cwd or d.get("cwd")
                if primera is None and d.get("type") == "user":
                    c = d.get("message", {}).get("content")
                    texto = c if isinstance(c, str) else " ".join(
                        x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text")
                    if texto and not texto.startswith("<"):
                        primera = re.sub(r"\s+", " ", texto)[:160]
    except OSError:
        return None
    if not cwd:
        return None
    return {"id": f.stem, "carpeta": cwd, "inicio": primera or "(sin texto)",
            "ultima": datetime.datetime.fromtimestamp(f.stat().st_mtime)}


@mcp.tool()
def buscar_conversaciones_claude(texto: str = "", dias: int = 7) -> str:
    """Lista las conversaciones recientes del usuario con Claude Code (terminal), con su
    carpeta/proyecto, cuándo fue la última actividad y cómo empezó. Filtra por texto
    (tema o proyecto) si se da. Úsala para "seguir la conversación de anoche" y luego
    abre la elegida con abrir_conversacion_claude."""
    limite = datetime.datetime.now() - datetime.timedelta(days=dias)
    archivos = sorted(SESIONES_CLAUDE.glob("*/*.jsonl"), key=lambda p: -p.stat().st_mtime)
    filas = []
    for f in archivos:
        if datetime.datetime.fromtimestamp(f.stat().st_mtime) < limite:
            break
        s = _resumen_sesion(f)
        if not s or "scratch" in s["carpeta"]:
            continue
        if texto and _norm(texto) not in _norm(s["inicio"] + s["carpeta"]):
            continue
        cuando = s["ultima"].strftime(f"{DIAS[s['ultima'].weekday()]} %d %H:%M")
        filas.append(f"id {s['id']} | {Path(s['carpeta']).name or '~'} | {cuando} | {s['inicio']}")
        if len(filas) >= 8:
            break
    return "\n".join(filas) if filas else "No encontré conversaciones así."


@mcp.tool()
def abrir_conversacion_claude(id: str, escritorio: str = "") -> str:
    """Abre una terminal (kitty) en la carpeta de esa conversación con Claude Code
    retomándola (claude --resume). El id sale de buscar_conversaciones_claude.
    escritorio: workspace donde abrirla, solo si el usuario lo pide."""
    f = next(SESIONES_CLAUDE.glob(f"*/{id}.jsonl"), None)
    s = _resumen_sesion(f) if f else None
    if not s:
        return "No encontré esa conversación."
    _lanzar(["kitty", "--directory", s["carpeta"], str(CLAUDE), "--resume", id], escritorio=escritorio)
    _anotar("accion", f"retomar claude en {Path(s['carpeta']).name or '~'}")
    return f"Abriendo la conversación en {s['carpeta']}."


# La asistente: no es herramienta; el contexto automático (asistente_contexto.py) la usa directamente
def ventanas_abiertas() -> str:
    """Lista las ventanas abiertas (app y título), para saber qué está corriendo."""
    return "\n".join(f"{c['class']}: {c['title'][:70]}" for c in _clientes()
                     if c.get("class") and c["class"] != "open-llm-vtuber") or "No hay ventanas."


@mcp.tool()
def cerrar_ventanas(nombre: str, confirmado: bool = False) -> str:
    """Cierra (como con la X, sin forzar) las ventanas cuya app o título coincide con
    nombre (por ejemplo un juego, "steam", "discord"). Si el usuario lo pidió él mismo, usa
    confirmado=True directamente. Si es una propuesta tuya, primero pregunta; sin confirmar,
    solo devuelve qué cerraría."""
    n = _norm(nombre)
    elegidas = [c for c in _clientes() if c.get("class") != "open-llm-vtuber"
                and (n in _norm(c.get("class", "")) or n in _norm(c.get("title", "")))]
    if not elegidas:
        return f"No hay ventanas de {nombre} abiertas."
    lista = ", ".join(sorted({c["class"] for c in elegidas}))
    if not confirmado:
        return f"Cerraría: {lista}. Pídele confirmación a {USUARIO}."
    global ultima_pantalla_cerrada
    ultima_pantalla_cerrada = _monitor_de(elegidas[0])
    for c in elegidas:
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{c["address"]}" }})'],
                       capture_output=True)
    _anotar("accion", f"cerrar {lista}")
    return f"Cerré: {lista}."


ultima_pantalla_cerrada = ""  # para "ábrelo en la misma pantalla" justo después de cerrar algo


def _monitor_de(cliente: dict) -> str:
    r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True)
    try:
        return next((m["name"] for m in json.loads(r.stdout) if m["id"] == cliente.get("monitor")), "")
    except ValueError:
        return ""


def _leer(p: str) -> str:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return ""


# La asistente: no es herramienta; el contexto automático (asistente_contexto.py) la usa directamente
def estado_sistema() -> str:
    """Estado del PC: RAM y zram, disco, temperaturas y uso de CPU y GPU,
    tiempo encendido y las apps que más memoria usan."""
    mem = {k: int(v.split()[0]) // 1024 for k, v in
           (l.split(":", 1) for l in _leer("/proc/meminfo").splitlines())}
    gb = lambda mb: f"{mb / 1024:.1f}".replace(".", ",")  # El usuario prefiere gigas
    partes = [f"RAM: {gb(mem['MemTotal'] - mem['MemAvailable'])} de {gb(mem['MemTotal'])} GB usados "
              f"({gb(mem['MemAvailable'])} GB libres)",
              f"zram/swap: {gb(mem['SwapTotal'] - mem['SwapFree'])} de {gb(mem['SwapTotal'])} GB"]
    for nombre, ruta in (("disco /", "/"), ("disco /home", str(HOME))):
        u = shutil.disk_usage(ruta)
        partes.append(f"{nombre}: {u.free // 2**30} GB libres de {u.total // 2**30} GB")
    for h in Path("/sys/class/hwmon").glob("hwmon*"):
        n = _leer(h / "name")
        t = _leer(h / "temp1_input")
        if n in ("k10temp", "amdgpu") and t:
            partes.append(f"temperatura {'CPU' if n == 'k10temp' else 'GPU'}: {int(t) // 1000} °C")
    for card in Path("/sys/class/drm").glob("card[0-9]/device"):
        usada, total = _leer(card / "mem_info_vram_used"), _leer(card / "mem_info_vram_total")
        if usada and total and int(total) > 2**31:
            partes.append(f"VRAM: {gb(int(usada) // 2**20)} de {gb(int(total) // 2**20)} GB, GPU al {_leer(card / 'gpu_busy_percent')} %")
    horas = float(_leer("/proc/uptime").split()[0]) / 3600
    partes.append(f"encendido hace {int(horas)} h {int(horas % 1 * 60)} min")
    top = subprocess.run(["ps", "-eo", "rss,comm", "--sort=-rss", "--no-headers"], capture_output=True, text=True)
    procesos: dict[str, int] = {}
    for l in top.stdout.splitlines():
        rss, comm = l.split(None, 1)
        procesos[comm] = procesos.get(comm, 0) + int(rss) // 1024
    partes.append("más memoria (aprox.): " + ", ".join(f"{c} {gb(m)} GB" for c, m in sorted(procesos.items(), key=lambda kv: -kv[1])[:5]))
    # lo que ocupa la asistente misma: su ventana, el servidor, la voz (RVC), el oído (whisper) y el cerebro (Ollama)
    ram_asistente = 0
    for l in subprocess.run(["ps", "-eo", "rss,args", "--no-headers"], capture_output=True, text=True).stdout.splitlines():
        rss, args = l.split(None, 1)
        if any(k in args for k in ("pixelgami", "llama-server", "whisper-server", "ollama serve")):
            ram_asistente += int(rss) // 1024
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=2) as r:
            vram_asistente = sum(m.get("size_vram", 0) for m in json.load(r)["models"]) // 2**20
        vram = f", VRAM {gb(vram_asistente)} GB (el modelo Qwen)"
    except Exception:
        vram = ""
    partes.append(nombres(f"{ASISTENTE} (tú mism{{a}}: tu ventana, tu voz, tu oído y tu cerebro Qwen): RAM {gb(ram_asistente)} GB{vram}; "
                  "en disco ocupas unos 25 GB con tus modelos"))
    return "\n".join(partes)


@mcp.tool()
def registrar_sugerencia(situacion: str, sugerencia: str, acepto: bool) -> str:
    """Anota si el usuario aceptó o rechazó algo que le propusiste (por ejemplo situacion="abrir
    proyecto mi-tienda-web", sugerencia="poner música calmada", acepto=False). Llámala siempre
    que responda a una propuesta tuya: así aprendes qué suele querer."""
    _anotar("sugerencia", sugerencia, situacion=situacion, acepto=acepto)
    return "Anotado."


# La asistente: no es herramienta; el contexto automático (asistente_contexto.py) la usa directamente
def consultar_habitos(situacion: str) -> str:
    """Qué suele hacer o querer el usuario en una situación ("abrir proyecto mi-tienda-web",
    "jugar monster hunter", "trabajar"): cuántas veces aceptó o rechazó cada sugerencia,
    lo último que dijo y cuándo suele hacer esas acciones (días y horas). Úsala antes de
    proponer algo, para no seguir siempre los mismos pasos."""
    if not HABITOS.exists():
        return "Todavía no hay hábitos registrados: pregunta y aprende."
    palabras = [p for p in re.findall(r"\w{3,}", _norm_sp(situacion))]
    sug: dict[str, list] = {}
    acciones = []
    for linea in HABITOS.read_text().splitlines():
        d = json.loads(linea)
        texto = _norm_sp(d.get("situacion", "") + " " + d["detalle"])
        if palabras and not any(p in texto for p in palabras):
            continue
        if d["tipo"] == "sugerencia":
            s = sug.setdefault(d["detalle"], [0, 0, ""])
            s[0 if d["acepto"] else 1] += 1
            s[2] = f"{d['dia']} {d['fecha'][11:]}: {'sí' if d['acepto'] else 'no'}"
        else:
            acciones.append(d)
    partes = [f"'{k}': aceptó {a}, rechazó {r} (última: {u})" for k, (a, r, u) in sug.items()]
    if acciones:
        ult = acciones[-5:]
        partes.append("acciones recientes: " + "; ".join(f"{d['detalle']} ({d['dia']} {d['hora']} h)" for d in ult))
    ahora = datetime.datetime.now()
    partes.append(f"ahora es {DIAS[ahora.weekday()]} {ahora:%H:%M}")
    return "\n".join(partes) if len(partes) > 1 else f"Nada registrado sobre {situacion}. " + partes[-1]


def _norm_sp(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower()


if __name__ == "__main__":
    mcp.run()
