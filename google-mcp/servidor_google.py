"""Herramienta MCP para la asistente: el correo y el calendario del usuario.

Correo: Gmail por IMAP con una contraseña de aplicación (~/.config/pixelgami/gmail.key).
Se lee en modo solo lectura y con BODY.PEEK, así que nada queda marcado como leído. Los cambios
(leído/no leído, estrella, archivar, mover entre bandeja, spam y papelera; todo reversible desde
Gmail) no son herramienta MCP: solo los hace el contexto automático de la asistente cuando el usuario los pide,
y los que sacan correos de donde están, después de que confirma.
Calendario: la "dirección secreta en formato iCal" de Google Calendar
(~/.config/pixelgami/calendario.url, una por línea si son varios calendarios),
con las repeticiones expandidas.
"""
import datetime
import difflib
import email
import email.header
import email.utils
import imaplib
import re
import time
import unicodedata
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import sys
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import PERFIL, ZONA as _ZONA, nombres  # noqa: E402

CONFIG = Path.home() / ".config/pixelgami"
CLAVE_GMAIL = CONFIG / "gmail.key"
URLS_CALENDARIO = CONFIG / "calendario.url"
CUENTA = PERFIL.get("correo", "")
ZONA = ZoneInfo(_ZONA)
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# El usuario no ve lo que devuelven las herramientas: si la asistente dice "aquí tienes" sin contarlo, no le llega nada
VER_EN_VOZ = (nombres("\n\n({usuario} NO ve esta lista en pantalla: cuéntale tú lo importante —de quién y de qué tratan—, "
              "en dos o tres frases. Nunca digas \"aquí tienes\".)"))
CACHE_ICS = 300  # segundos: el calendario no se descarga en cada mensaje

mcp = FastMCP("google")
_ics = {"t": 0.0, "cals": []}


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    return "".join(t.decode(c or "utf-8", "replace") if isinstance(t, bytes) else t
                   for t, c in email.header.decode_header(valor)).strip()


def _remitente(valor: str) -> str:
    nombre, direccion = email.utils.parseaddr(_decodificar(valor))
    return nombre or direccion


def _texto(msj: email.message.Message) -> str:
    """El texto plano del correo (o el HTML sin etiquetas si no trae texto plano)."""
    partes = msj.walk() if msj.is_multipart() else [msj]
    html = ""
    for p in partes:
        if p.get_content_maintype() == "multipart" or p.get("Content-Disposition", "").startswith("attachment"):
            continue
        carga = p.get_payload(decode=True)
        if not carga:
            continue
        t = carga.decode(p.get_content_charset() or "utf-8", "replace")
        if p.get_content_type() == "text/plain":
            return re.sub(r"\s+", " ", t).strip()
        if p.get_content_type() == "text/html" and not html:
            t = re.sub(r"(?is)<(style|script).*?</\1>", " ", t)
            html = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
    return html


# carpetas que el usuario nombra -> marca especial de Gmail (los nombres reales cambian con el idioma)
CARPETAS = {"entrada": None, "spam": rb"\Junk", "papelera": rb"\Trash", "todos": rb"\All",
            "destacados": rb"\Flagged", "enviados": rb"\Sent"}
NOMBRE_CARPETA = {"entrada": "la bandeja de entrada", "spam": "la carpeta de SPAM", "papelera": "la papelera",
                  "todos": "todo el correo", "destacados": "los destacados", "enviados": "los enviados"}


def _carpeta_especial(conexion: imaplib.IMAP4_SSL, marca: bytes) -> str | None:
    """Nombre de la carpeta de Gmail con esa marca (\\Junk, \\Trash...); el nombre cambia con el idioma."""
    if marca not in _sesion["carpetas"]:
        for c in conexion.list()[1]:
            if marca in c.split(b'"')[0]:
                _sesion["carpetas"][marca] = re.search(rb'"([^"]+)"$', c).group(1).decode()
    return _sesion["carpetas"].get(marca)


# una sola conexión para todo: a ratos Gmail tarda segundos en cada comando después del login, y abrir una
# por consulta (login + list + select) hacía que la asistente tardara hasta un minuto en contestar
_sesion = {"c": None, "t": 0.0, "abierta": None, "carpetas": {}}


def _imap(carpeta: str = "entrada", escribir: bool = False) -> imaplib.IMAP4_SSL:
    """Conexión con esa carpeta abierta (en solo lectura salvo que se vaya a cambiar algo)."""
    if not CLAVE_GMAIL.exists():
        raise RuntimeError("falta la contraseña de aplicación de Gmail (~/.config/pixelgami/gmail.key)")
    if _sesion["c"] and time.time() - _sesion["t"] > 600:  # Gmail corta las conexiones quietas
        _cerrar()
    for intento in (0, 1):
        try:
            if not _sesion["c"]:
                conexion = imaplib.IMAP4_SSL("imap.gmail.com", timeout=40)
                conexion.login(CUENTA, CLAVE_GMAIL.read_text().strip().replace(" ", ""))
                _sesion.update(c=conexion, abierta=None)
            conexion = _sesion["c"]
            marca = CARPETAS.get(carpeta)
            nombre = _carpeta_especial(conexion, marca) if marca else "INBOX"
            if _sesion["abierta"] != (nombre, escribir):
                conexion.select(f'"{nombre}"', readonly=not escribir)
                _sesion["abierta"] = (nombre, escribir)
            _sesion["t"] = time.time()
            return conexion
        except (imaplib.IMAP4.abort, OSError):
            _cerrar()
            if intento:
                raise


def _cerrar() -> None:
    conexion, _sesion["c"], _sesion["abierta"] = _sesion["c"], None, None
    try:
        conexion.logout()
    except Exception:
        pass


def _listar(criterio: list[str], cuantos: int, cuerpo: int, carpeta: str = "entrada") -> str:
    try:
        conexion = _imap(carpeta)
    except Exception as e:
        return f"No pude entrar al correo: {e}"
    try:
        _, datos = conexion.search(None, *criterio)
        ids = datos[0].split()[-cuantos:][::-1]
        if not ids:
            return "No hay correos que coincidan."
        lineas = []
        # todos en un solo pedido (uno por correo eran 8 viajes a Gmail); llegan del más viejo al más nuevo
        _, d = conexion.fetch(b",".join(ids), f"(FLAGS BODY.PEEK[]<0.{max(cuerpo, 0) + 20000}>)")
        for cabecera, crudo in [p for p in d if isinstance(p, tuple)][::-1]:
            msj = email.message_from_bytes(crudo)
            fecha = email.utils.parsedate_to_datetime(msj["Date"]).astimezone(ZONA) if msj["Date"] else None
            no_leido = b"\\Seen" not in cabecera
            linea = (f"- {'(sin leer) ' if no_leido else ''}{fecha:%d/%m %H:%M} · de {_remitente(msj['From'])}: "
                     f"{_decodificar(msj['Subject']) or '(sin asunto)'}" if fecha else
                     f"- de {_remitente(msj['From'])}: {_decodificar(msj['Subject'])}")
            if cuerpo:
                linea += f"\n  {_texto(msj)[:cuerpo]}"
            lineas.append(linea)
        return "\n".join(lineas)
    except (imaplib.IMAP4.abort, OSError):
        _cerrar()
        raise


@mcp.tool()
def correos_recientes(cuantos: int = 5, solo_sin_leer: bool = False, carpeta: str = "entrada") -> str:
    """Los últimos correos del usuario (remitente, asunto, fecha y el inicio del texto).
    carpeta: "entrada", "spam", "papelera", "destacados", "enviados" o "todos"."""
    return _listar(["UNSEEN"] if solo_sin_leer else ["ALL"], min(cuantos, 15), 200, carpeta) + VER_EN_VOZ


@mcp.tool()
def buscar_correos(texto: str, cuantos: int = 3, carpeta: str = "todos", cuerpo: int = 1500) -> str:
    """Busca correos del usuario por remitente, asunto o contenido (como el buscador de Gmail) y los muestra."""
    # IMAP solo acepta ASCII aquí; el buscador de Gmail no distingue tildes
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().replace('"', "")
    return _listar(["X-GM-RAW", f'"{texto}"'], min(cuantos, 10), cuerpo, carpeta) + VER_EN_VOZ


def resumen_correo(carpeta: str = "entrada") -> str:
    """Para el contexto automático: cuántos hay (y sin leer) en la carpeta y los últimos correos."""
    try:
        conexion = _imap(carpeta)
        try:
            total = len(conexion.search(None, "ALL")[1][0].split())
            sin_leer = len(conexion.search(None, "UNSEEN")[1][0].split())
        except (imaplib.IMAP4.abort, OSError):
            _cerrar()
            raise
    except Exception as e:
        return f"No pude entrar al correo: {e}"
    donde = NOMBRE_CARPETA.get(carpeta, carpeta)
    if not total:
        return f"En {donde} no hay ningún correo."
    return (f"En {donde} hay {total} correo(s), {sin_leer} sin leer. "
            f"Los más recientes (solo los últimos 8, no son todos):\n" + correos_recientes(8, carpeta=carpeta))


def _normal(t: str) -> str:
    return re.sub(r"[^a-z0-9@.]", "", unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode())


def _parecido(buscado: str, remitente: str, asunto: str = "") -> float:
    """Qué tanto se parece lo que dijo el usuario (Whisper a veces lo deforma) al remitente o al asunto."""
    nombre, direccion = email.utils.parseaddr(remitente)
    usuario, _, dominio = direccion.lower().partition("@")
    candidatos = [c for c in (_normal(nombre), _normal(usuario), _normal(dominio.rsplit(".", 1)[0]),
                              _normal(dominio)) if c]
    b = _normal(buscado)
    if not b:
        return 0.0
    if len(b) >= 4 and b in _normal(asunto):
        return 1.0
    # palabra por palabra, sin plurales: "gaceta universitaria" = "Gacetas Universitarias UNI"
    palabras = [_normal(w) for w in re.findall(r"\w{3,}", buscado)]
    donde = _normal(nombre) + _normal(asunto)
    if palabras and all(w.rstrip("s") in donde for w in palabras):
        return 0.9
    return max((1.0 if b in c else difflib.SequenceMatcher(None, b, c).ratio() for c in candidatos), default=0.0)


def _palabras(texto: str) -> list[str]:
    return [_normal(w) for w in re.findall(r"\w{3,}", texto)]


def _raiz(w: str) -> str:
    """Sin plural: "boletines" -> "boletin", "becas" -> "beca"."""
    return w[:-2] if w.endswith("es") and len(w) > 5 else w[:-1] if w.endswith("s") else w


def _en_asunto(asuntos: list[str], asunto: str) -> bool:
    """Cada cosa que dijo el usuario aparece en el asunto, palabra por palabra y sin plurales."""
    donde = _normal(asunto)
    return all(all(_raiz(w) in donde for w in _palabras(a)) for a in asuntos)


def buscar(carpeta: str = "entrada", quienes: list[str] | None = None, solo_sin_leer: bool = False,
           revisar: int = 150, maximo: int = 50, asuntos: list[str] | None = None) -> list[tuple[bytes, str]]:
    """UID y descripción de los correos de esa carpeta (los más recientes primero); si se dan nombres,
    solo los de remitentes o asuntos parecidos; si se dan asuntos, solo los que los traen en el asunto
    (esos se buscan en toda la carpeta con el buscador de Gmail, no solo en los últimos `revisar`)."""
    asuntos = [a for a in asuntos or [] if _palabras(a)]
    conexion = _imap(carpeta)
    try:
        uids = []
        if asuntos:
            # Gmail no junta singular y plural: "beca" no encuentra "Becas"
            consulta = " ".join("subject:(" + " OR ".join(dict.fromkeys([w, _raiz(w), _raiz(w) + "s", _raiz(w) + "es"])) + ")"
                                for a in asuntos for w in _palabras(a))
            consulta += " is:unread" if solo_sin_leer else ""
            uids = conexion.uid("SEARCH", "X-GM-RAW", f'"{consulta}"')[1][0].split()[-500:]
        if not uids:  # sin asunto, o Gmail no lo halló (tildes, palabras pegadas): los últimos, revisados aquí
            uids = conexion.uid("SEARCH", None, "UNSEEN" if solo_sin_leer else "ALL")[1][0].split()[
                -(500 if asuntos else revisar):]
        if not uids:
            return []
        _, d = conexion.uid("FETCH", b",".join(uids), "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        encontrados = []
        for parte in d:
            if not isinstance(parte, tuple):
                continue
            uid = re.search(rb"UID (\d+)", parte[0]).group(1)
            msj = email.message_from_bytes(parte[1])
            de, asunto = _decodificar(msj["From"]), _decodificar(msj["Subject"])
            if (not quienes or any(_parecido(q, de, asunto) >= 0.75 for q in quienes)) and _en_asunto(asuntos, asunto):
                encontrados.append((uid, f"de {_remitente(msj['From'])}: {asunto or '(sin asunto)'}"))
        return encontrados[::-1][:maximo]
    except (imaplib.IMAP4.abort, OSError):
        _cerrar()
        raise


def leer_correo(carpeta: str, uid: bytes, largo: int = 3000) -> str:
    """El correo completo (remitente, fecha, asunto y texto limpio), sin marcarlo como leído."""
    conexion = _imap(carpeta)
    try:
        _, d = conexion.uid("FETCH", uid, "(BODY.PEEK[])")
        msj = email.message_from_bytes(next(p[1] for p in d if isinstance(p, tuple)))
    except (imaplib.IMAP4.abort, OSError):
        _cerrar()
        raise
    fecha = email.utils.parsedate_to_datetime(msj["Date"]).astimezone(ZONA) if msj["Date"] else None
    texto = re.sub(r"https?://\S+", "[enlace]", _texto(msj))
    texto = re.sub(r"(\[enlace\]\s*){2,}", "[enlaces] ", texto)
    texto = re.sub(r"[_=*~-]{4,}", " ", texto)
    return (f"De: {_remitente(msj['From'])}\n" + (f"Fecha: {DIAS[fecha.weekday()]} {fecha:%d/%m %H:%M}\n" if fecha else "")
            + f"Asunto: {_decodificar(msj['Subject']) or '(sin asunto)'}\nTexto: {texto[:largo]}"
            + (" [...sigue]" if len(texto) > largo else ""))


# acción -> (qué se hace en IMAP, cómo se cuenta). Mover a "entrada" saca de spam o recupera de la papelera;
# archivar es mover a "todos" (Gmail le quita la etiqueta de la bandeja de entrada).
ACCIONES = {
    "leido": (("STORE", "+FLAGS", r"(\Seen)"), "marcado(s) como leído(s)"),
    "no_leido": (("STORE", "-FLAGS", r"(\Seen)"), "marcado(s) como no leído(s)"),
    "destacar": (("STORE", "+FLAGS", r"(\Flagged)"), "destacado(s) con estrella"),
    "quitar_destacado": (("STORE", "-FLAGS", r"(\Flagged)"), "sin estrella"),
    "papelera": (("MOVE", "papelera"), "en la papelera (se pueden recuperar 30 días)"),
    "spam": (("MOVE", "spam"), "movido(s) a spam"),
    "entrada": (("MOVE", "entrada"), "movido(s) a la bandeja de entrada"),
    "archivar": (("MOVE", "todos"), "archivado(s) (siguen en Todos los correos)"),
}


def aplicar(accion: str, carpeta: str, uids: list[bytes]) -> str:
    """Hace el cambio en esos correos de esa carpeta. Todo se puede deshacer desde Gmail."""
    if not uids:
        return "No había correos para eso."
    if accion not in ACCIONES:
        return f"No sé hacer \"{accion}\" con el correo."
    (orden, *args), cuenta = ACCIONES[accion]
    conexion = _imap(carpeta, escribir=True)
    try:
        if orden == "MOVE":
            marca = CARPETAS[args[0]]
            destino = _carpeta_especial(conexion, marca) if marca else "INBOX"
            if not destino:
                return f"No encontré {NOMBRE_CARPETA[args[0]]} en Gmail."
            args = [f'"{destino}"']
        estado, _ = conexion.uid(orden, b",".join(uids), *args)
        return f"{len(uids)} correo(s) {cuenta}." if estado == "OK" else "Gmail no dejó hacerlo."
    except (imaplib.IMAP4.abort, OSError):
        _cerrar()
        raise


def _calendarios() -> list:
    if time.time() - _ics["t"] > CACHE_ICS:
        if not URLS_CALENDARIO.exists():
            raise RuntimeError("falta la dirección iCal del calendario (~/.config/pixelgami/calendario.url)")
        cals = []
        for url in URLS_CALENDARIO.read_text().split():
            with urllib.request.urlopen(url, timeout=15) as r:
                cals.append(icalendar.Calendar.from_ical(r.read()))
        _ics.update(t=time.time(), cals=cals)
    return _ics["cals"]


@mcp.tool()
def agenda(dias: int = 1, desde_dentro_de: int = 0) -> str:
    """Eventos del calendario del usuario. dias = cuántos días mostrar; desde_dentro_de = 0 hoy, 1 mañana, etc."""
    try:
        cals = _calendarios()
    except Exception as e:
        return f"No pude leer el calendario: {e}"
    hoy = datetime.datetime.now(ZONA).replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = hoy + datetime.timedelta(days=desde_dentro_de)
    fin = inicio + datetime.timedelta(days=max(dias, 1))
    eventos = []
    for cal in cals:
        for ev in recurring_ical_events.of(cal).between(inicio, fin):
            ini = ev["DTSTART"].dt
            todo_el_dia = not isinstance(ini, datetime.datetime)
            if todo_el_dia:
                ini = datetime.datetime.combine(ini, datetime.time(), ZONA)
            elif ini.tzinfo is None:
                ini = ini.replace(tzinfo=ZONA)
            ini = ini.astimezone(ZONA)
            lugar = str(ev.get("LOCATION", "")).strip()
            eventos.append((ini, todo_el_dia, str(ev.get("SUMMARY", "(sin título)")), lugar))
    if not eventos:
        return "No hay nada en el calendario para esos días."
    lineas = []
    for ini, todo_el_dia, titulo, lugar in sorted(eventos):
        dia = f"{DIAS[ini.weekday()]} {ini.day}/{ini.month}"
        lineas.append(f"- {dia}, {'todo el día' if todo_el_dia else f'{ini:%H:%M}'}: {titulo}"
                      + (f" ({lugar})" if lugar else ""))
    return "\n".join(lineas)


if __name__ == "__main__":
    mcp.run()
