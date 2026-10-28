"""Recordatorios con la cara de la asistente, sin tenerla prendida: guardarlos y avisar a la hora.

La notificación sale a nombre de la asistente, pero aquí no corre nada de ella (ni el modelo, ni la voz, ni la GPU):
este proceso chico, como servicio de systemd --user, espera la hora y avisa (botones Listo / Posponer; lo que se pasó
con la PC apagada o suspendida sale al volver como "se te pasó"). Los recordatorios se crean desde la ventanita
(ventana.py), hablándole a la asistente (funcion.py) o salen solos del calendario (google_calendario.py
y/o URLs iCal), que se revisa al arrancar y al cambiar el día.

Desde la carpeta de la instalación:
  python3 -m funciones.recordatorios.avisos vigilar          el servicio
  python3 -m funciones.recordatorios.avisos agregar "mañana 3pm entregar lo de Proyectos"
  python3 -m funciones.recordatorios.avisos probar "todos los lunes 7am gym"   solo interpreta, no guarda
  python3 -m funciones.recordatorios.avisos lista | borrar <id>
Fuera del servicio usa solo la biblioteca estándar e identidad.py; gi (D-Bus) se importa dentro de vigilar().
"""
import datetime
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from funciones import carpeta_datos
from identidad import ASISTENTE, BASE, PERFIL, USUARIO

from .fechas import describir, interpretar, siguiente

CARPETA = Path(__file__).resolve().parent
DATOS = carpeta_datos("recordatorios") / "recordatorios.json"
# ícono de las notificaciones: perfil.yaml (icono_recordatorios) > recordatorios/icono.png > el del tema del sistema
_icono = Path(os.path.expanduser(PERFIL.get("icono_recordatorios") or CARPETA / "icono.png"))
ICONO = str(_icono) if _icono.exists() else "appointment-soon"
URLS_CALENDARIO = Path.home() / ".config/pixelgami/calendario.url"
PY_BACKEND = BASE / "Open-LLM-VTuber/.venv/bin/python"  # el que tiene icalendar (para las URLs iCal)
POSPONER_MIN = 10
TARDE_MIN = 10  # más tarde que esto (PC apagada o suspendida) = "se te pasó"


# ---------- guardar ----------

_lock = threading.Lock()


def cargar() -> dict:
    try:
        return json.loads(DATOS.read_text())
    except (OSError, ValueError):
        return {"siguiente_id": 1, "recordatorios": [], "avisados": []}


def guardar(datos: dict) -> None:
    tmp = DATOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    tmp.replace(DATOS)


def agregar(frase: str, origen: str = "ventana") -> dict:
    """Interpreta y guarda. Devuelve el recordatorio (con "id" y "cuando_texto") o {"error"}."""
    r = interpretar(frase)
    if "error" in r:
        return r
    return guardar_uno(r["texto"], r["cuando"], r["repetir"], origen)


def guardar_uno(texto: str, cuando: datetime.datetime, repetir: dict | None = None, origen: str = "ventana",
                **extra) -> dict:
    with _lock:
        datos = cargar()
        nuevo = {"id": datos["siguiente_id"], "texto": texto, "cuando": cuando.isoformat(timespec="minutes"),
                 "repetir": repetir, "origen": origen, **extra}
        datos["siguiente_id"] += 1
        datos["recordatorios"].append(nuevo)
        guardar(datos)
    return {**nuevo, "cuando_texto": describir(cuando, repetir)}


def pendientes() -> list[dict]:
    """Los guardados, del más próximo al más lejano, con "cuando_texto". Un evento del calendario sale una vez (aunque
    tenga dos avisos) y con su propia fecha («el domingo (todo el día)»), no la de sus avisos."""
    salida, eventos = [], set()
    for r in sorted(cargar()["recordatorios"], key=lambda r: r["cuando"]):
        ev = r.get("evento")
        if ev:
            if ev["clave"] in eventos:
                continue
            eventos.add(ev["clave"])
            cuando_texto = describir(datetime.datetime.fromisoformat(ev["inicio"]), todo_el_dia=ev["todo_el_dia"])
        else:
            cuando_texto = describir(datetime.datetime.fromisoformat(r["cuando"]), r.get("repetir"))
        salida.append({**r, "cuando_texto": cuando_texto})
    return salida


def borrar(rid: int) -> dict | None:
    """Quita el recordatorio; si es de un evento del calendario, también los otros avisos de ese evento."""
    with _lock:
        datos = cargar()
        quitado = next((r for r in datos["recordatorios"] if r["id"] == rid), None)
        if quitado:
            clave = (quitado.get("evento") or {}).get("clave")
            datos["recordatorios"] = [r for r in datos["recordatorios"] if r is not quitado
                                      and not (clave and (r.get("evento") or {}).get("clave") == clave)]
            guardar(datos)
    return quitado


# ---------- cómo lo dice la asistente ----------

FRASES = ["¡Oye! {t} 💙", "Te lo recuerdo: {t} ✨", "No se te olvide: {t}.", "Psst, {u}… {t} 🎵",
          "Recordatorio de tu {a}: {t}.", "¡{u}! {t} 💫"]
FRASES_TARDE = ["Uy, esto era para las {h} y se te pasó: {t}.", "Se me quedó en el bolsillo desde las {h}: {t}. "
                "¡Todavía estás a tiempo!", "Llegué tarde (era a las {h}): {t}."]
_ultima_frase = {"i": -1}


def a_ti(t: str) -> str:
    """Lo que escribió en primera persona, dicho por la asistente: «mi mamá» -> «tu mamá», «tengo» -> «tienes»."""
    cambios = {"mi": "tu", "mis": "tus", "me": "te", "tengo": "tienes", "debo": "debes", "necesito": "necesitas",
               "quiero": "quieres", "voy": "vas", "conmigo": "contigo", "mío": "tuyo", "mía": "tuya"}
    return re.sub(r"\b(" + "|".join(cambios) + r")\b", lambda m: cambios[m.group(1).lower()], t, flags=re.I)


def frase_asistente(texto: str, tarde_de: datetime.datetime | None = None) -> str:
    lista = FRASES_TARDE if tarde_de else FRASES
    i = random.choice([j for j in range(len(lista)) if j != _ultima_frase["i"]] or [0])
    _ultima_frase["i"] = i
    t = a_ti(texto)
    if lista[i].startswith("{t}") or ": {t}" in lista[i] or "… {t}" in lista[i] or "! {t}" in lista[i]:
        t = t[0].upper() + t[1:]
    return lista[i].format(t=t, u=USUARIO, a=ASISTENTE, h=f"{tarde_de:%H:%M}" if tarde_de else "")


def frase_evento(titulo: str, evento: dict, ahora: datetime.datetime | None = None) -> str:
    """El aviso de un evento del calendario, armado al avisar: «En 20 min: «Cita»» o «Hoy tienes «Cita» a las 15:00»
    (los minutos se cuentan en ese momento: un aviso pospuesto no dice «30 min» si faltan 20)."""
    ahora = ahora or datetime.datetime.now()
    ini = datetime.datetime.fromisoformat(evento["inicio"])
    falta = round((ini - ahora).total_seconds() / 60)
    if evento["aviso"] == "antes" and falta > 0:
        return f"En {falta} min: «{titulo}»"
    return f"Hoy tienes «{titulo}»" + ("" if evento["todo_el_dia"] else f" a las {ini:%H:%M}")


# ---------- calendario ----------

def eventos_calendario(horas: int = 48) -> list[dict]:
    """Corre en el Python del backend (tiene icalendar). [{"clave", "titulo", "inicio" iso, "todo_el_dia"}]."""
    sys.path.insert(0, str(BASE / "google-mcp"))
    import servidor_google as g
    import recurring_ical_events
    ahora = datetime.datetime.now(g.ZONA)
    salida = []
    for cal in g._calendarios():
        for ev in recurring_ical_events.of(cal).between(ahora - datetime.timedelta(hours=1),
                                                        ahora + datetime.timedelta(hours=horas)):
            ini = ev["DTSTART"].dt
            todo = not isinstance(ini, datetime.datetime)
            if todo:
                ini = datetime.datetime.combine(ini, datetime.time(), g.ZONA)
            elif ini.tzinfo is None:
                ini = ini.replace(tzinfo=g.ZONA)
            ini = ini.astimezone(g.ZONA).replace(tzinfo=None)
            salida.append({"clave": f"{ev.get('UID', '')}|{ini.isoformat()}", "titulo": str(ev.get("SUMMARY", "")),
                           "inicio": ini.isoformat(), "todo_el_dia": todo})
    return salida


def sincronizar_calendario() -> None:
    """Trae los eventos de hoy y mañana y les programa avisos. Lo llama el servicio al arrancar y cuando cambia el
    día (no hace falta más: lo que se apunta desde aquí se programa al apuntarlo, con programar_avisos).
    Fuentes: Google Calendar personal (google_calendario.py, si está autorizado) y URLs iCal (calendario.url).
    Si una fuente falla (sin internet al arrancar), lanza la excepción para que el servicio reintente."""
    eventos = []
    from . import google_calendario
    if google_calendario.configurado():
        eventos += google_calendario.eventos()
    if URLS_CALENDARIO.exists() and PY_BACKEND.exists():
        r = subprocess.run([str(PY_BACKEND), "-m", "funciones.recordatorios.avisos", "_eventos"], capture_output=True,
                           text=True, timeout=60, cwd=BASE)
        if r.returncode:
            raise RuntimeError(f"calendario iCal: {r.stderr.strip()[-300:]}")
        eventos += json.loads(r.stdout)
    programar_avisos(eventos)


def programar_avisos(eventos: list[dict]) -> None:
    """Avisos por evento: a las 8:00 del día y, si tiene hora (desde las 9), 30 min antes. Sin repetir los ya puestos."""
    ahora = datetime.datetime.now()
    with _lock:
        datos = cargar()
        avisados = set(datos.get("avisados", []))
        for ev in eventos:
            ini = datetime.datetime.fromisoformat(ev["inicio"])
            avisos = [("dia", datetime.datetime.combine(ini.date(), datetime.time(8)))]
            if not ev["todo_el_dia"] and ini.hour >= 9:
                avisos.append(("antes", ini - datetime.timedelta(minutes=30)))
            for tipo, cuando in avisos:
                clave = f"{ev['clave']}|{tipo}"
                if clave in avisados or cuando < ahora - datetime.timedelta(minutes=TARDE_MIN):
                    continue
                avisados.add(clave)
                evento = {"clave": ev["clave"], "inicio": ini.isoformat(), "todo_el_dia": ev["todo_el_dia"],
                          "aviso": tipo}
                datos["recordatorios"].append({"id": datos["siguiente_id"], "texto": ev["titulo"],
                                               "cuando": cuando.isoformat(timespec="minutes"), "repetir": None,
                                               "origen": "calendario", "evento": evento})
                datos["siguiente_id"] += 1
        datos["avisados"] = sorted(avisados)[-500:]
        guardar(datos)


# ---------- servicio ----------

def vigilar() -> None:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    respuestas = {}  # id de notificación -> recordatorio

    def senal(_c, _s, _p, _i, nombre, params):
        if nombre == "ActionInvoked":
            nid, clave = params.unpack()
        elif nombre == "NotificationClosed":
            nid, clave = params.unpack()[0], ""
        else:
            return
        r = respuestas.pop(nid, None)
        if r and clave == "posponer":
            guardar_uno(r["texto"], datetime.datetime.now().replace(second=0, microsecond=0)
                        + datetime.timedelta(minutes=POSPONER_MIN), None, "pospuesto",
                        **({"evento": r["evento"]} if r.get("evento") else {}))
        elif r and clave == "default":
            subprocess.Popen([sys.executable, "-m", "funciones.recordatorios.ventana"], cwd=BASE)

    bus.signal_subscribe("org.freedesktop.Notifications", "org.freedesktop.Notifications", None,
                         "/org/freedesktop/Notifications", None, Gio.DBusSignalFlags.NONE, senal)
    threading.Thread(target=GLib.MainLoop().run, daemon=True).start()

    def avisar(r, tarde_de):
        if r.get("evento"):
            texto = frase_evento(r["texto"], r["evento"])
            cuerpo = frase_asistente(texto, tarde_de) if tarde_de else f"{texto}."
        else:
            cuerpo = frase_asistente(r["texto"], tarde_de)
        acciones = ["listo", "Listo", "posponer", f"En {POSPONER_MIN} min"]
        hints = {"urgency": GLib.Variant("y", 1)}
        if ICONO.startswith("/"):
            hints["image-path"] = GLib.Variant("s", ICONO)
        params = GLib.Variant("(susssasa{sv}i)", (ASISTENTE, 0, ICONO, ASISTENTE, cuerpo, acciones, hints, 0))
        try:
            nid = bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                                "org.freedesktop.Notifications", "Notify", params, None, 0, 5000, None).unpack()[0]
            respuestas[nid] = r
        except Exception as e:
            print(f"no se pudo notificar: {e}", flush=True)
        try:  # el sonido de notificación del tema, si hay
            subprocess.Popen(["canberra-gtk-play", "-i", "message-new-instant"], stderr=subprocess.DEVNULL)
        except OSError:
            pass

    cal = {"dia": None, "intento": 0.0}  # día ya revisado; último intento (si falla, otra vez en 5 min)

    def revisar_calendario(hoy):
        if _seguro(sincronizar_calendario):
            cal["dia"] = hoy

    print("vigilando recordatorios", flush=True)
    while True:
        hoy = datetime.date.today()
        if cal["dia"] != hoy and time.time() - cal["intento"] > 300:  # al arrancar y al cambiar de día
            cal["intento"] = time.time()
            threading.Thread(target=revisar_calendario, args=(hoy,), daemon=True).start()
        ahora = datetime.datetime.now()
        disparar = []
        with _lock:
            datos = cargar()
            cambio = False
            for r in list(datos["recordatorios"]):
                cuando = datetime.datetime.fromisoformat(r["cuando"])
                if cuando > ahora:
                    continue
                tarde = ahora - cuando > datetime.timedelta(minutes=TARDE_MIN)
                disparar.append((r, cuando if tarde else None))
                cambio = True
                if r.get("repetir"):
                    r["cuando"] = siguiente(r["repetir"], cuando.time(), ahora).isoformat(timespec="minutes")
                else:
                    datos["recordatorios"].remove(r)
            if cambio:
                guardar(datos)
        for r, tarde_de in disparar:
            avisar(r, tarde_de)
        time.sleep(15)  # corto a propósito: tras suspender, time.sleep no cuenta el tiempo dormido


def _seguro(f) -> bool:
    try:
        f()
        return True
    except Exception as e:
        print(f"{f.__name__}: {e}", flush=True)
        return False


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "lista"
    resto = " ".join(sys.argv[2:])
    if accion == "vigilar":
        vigilar()
    elif accion == "_eventos":
        print(json.dumps(eventos_calendario()))
    elif accion in ("agregar", "probar"):
        r = agregar(resto, "comando") if accion == "agregar" else interpretar(resto)
        if "error" in r:
            sys.exit(r["error"])
        print(f"«{r['texto']}» {r.get('cuando_texto') or describir(r['cuando'], r['repetir'])}")
    elif accion == "lista":
        for r in pendientes():
            print(f"{r['id']:>4}  {r['cuando_texto']:<40} {r['texto']}")
    elif accion == "borrar":
        print("borrado" if borrar(int(resto)) else "no existe")
    else:
        sys.exit(__doc__)
