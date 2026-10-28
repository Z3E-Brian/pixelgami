#!/usr/bin/env python3
"""Google Calendar personal: leer eventos y apuntar nuevos, a través de un Apps Script propio (calendario.gs)
publicado como aplicación web con la cuenta del usuario. Así no hay proyecto de Cloud ni permiso que venza cada 7
días. Biblioteca estándar más identidad.py (lo usan el servicio de recordatorios y el backend de la asistente, cada uno con su Python).

Desde la carpeta de la instalación:
  python3 -m funciones.recordatorios.google_calendario copiar            genera la clave y copia el script al portapapeles
  python3 -m funciones.recordatorios.google_calendario configurar <url>  guarda la URL /exec (y prueba que responda)
  python3 -m funciones.recordatorios.google_calendario eventos [días]    lo que viene
  python3 -m funciones.recordatorios.google_calendario apuntar "el 5 de noviembre a las 2 examen de globales"
Clave y URL en ~/.config/pixelgami/google-calendar-script.json (600). El script nunca borra ni edita.
"""
import datetime
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from identidad import ASISTENTE

CARPETA = Path(__file__).resolve().parent
CONFIG = Path.home() / ".config/pixelgami/google-calendar-script.json"


def _config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def _guardar_config(c: dict) -> None:
    CONFIG.touch(mode=0o600, exist_ok=True)
    os.chmod(CONFIG, 0o600)
    CONFIG.write_text(json.dumps(c, indent=1))


def configurado() -> bool:
    c = _config()
    return bool(c.get("url") and c.get("clave"))


def _llamar(datos: dict) -> dict:
    c = _config()
    datos = {**datos, "clave": c["clave"]}
    if datos["accion"] == "eventos":  # GET; Apps Script responde con una redirección que urllib sigue sola
        req = urllib.request.Request(c["url"] + "?" + urllib.parse.urlencode(datos))
    else:
        req = urllib.request.Request(c["url"], json.dumps(datos).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        respuesta = json.load(r)
    if "error" in respuesta:
        raise RuntimeError(f"Apps Script: {respuesta['error']}")
    return respuesta


def eventos(horas: int = 48, desde: datetime.datetime | None = None) -> list[dict]:
    """[{"clave", "titulo", "inicio" iso local sin zona, "todo_el_dia", "lugar"}], repetidos ya expandidos."""
    desde = (desde or datetime.datetime.now()).astimezone()
    hasta = desde + datetime.timedelta(hours=horas)
    salida = []
    for ev in _llamar({"accion": "eventos", "desde": desde.isoformat(), "hasta": hasta.isoformat()})["eventos"]:
        if ev["todo_el_dia"]:
            inicio = datetime.datetime.fromisoformat(ev["inicio"])
        else:
            inicio = datetime.datetime.fromisoformat(ev["inicio"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        titulo = ev["titulo"] or "(sin título)"
        # clave = título + inicio (la misma que pone apuntar(), para no duplicar avisos)
        salida.append({"clave": f"g:{titulo}|{inicio.isoformat()}", "titulo": titulo, "inicio": inicio.isoformat(),
                       "todo_el_dia": ev["todo_el_dia"], "lugar": ev.get("lugar", "")})
    return salida


def apuntar(titulo: str, inicio: datetime.datetime, con_hora: bool = True, repetir: dict | None = None,
            minutos: int = 60) -> dict:
    """Crea el evento en el calendario principal (sin hora = todo el día) y programa sus avisos de una vez."""
    ini = inicio.replace(second=0, microsecond=0) if con_hora else datetime.datetime.combine(inicio.date(), datetime.time())
    datos = {"accion": "apuntar", "titulo": titulo, "todo_el_dia": not con_hora, "descripcion": f"Apuntado por {ASISTENTE}",
             "inicio": ini.astimezone().isoformat(),
             "fin": (ini + datetime.timedelta(minutes=minutos)).astimezone().isoformat()}
    if repetir and "dias" in repetir:
        datos["dias"] = repetir["dias"]
    elif repetir and "mes" in repetir:
        datos["dia_mes"] = repetir["mes"]
    r = _llamar(datos)
    from . import avisos  # el servicio solo revisa el calendario al arrancar y al cambiar de día
    avisos.programar_avisos([{"clave": f"g:{titulo}|{ini.isoformat()}", "titulo": titulo,
                                     "inicio": ini.isoformat(), "todo_el_dia": not con_hora}])
    return r


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "copiar":
        c = _config()
        c.setdefault("clave", secrets.token_urlsafe(24))
        _guardar_config(c)
        script = (CARPETA / "calendario.gs").read_text().replace("__CLAVE__", c["clave"])
        subprocess.run(["wl-copy"], input=script, text=True, check=True)
        print("Script copiado al portapapeles (con tu clave).")
    elif accion == "configurar":
        c = _config()
        c["url"] = sys.argv[2].strip()
        _guardar_config(c)
        print(f"Responde: {len(eventos(24 * 7))} eventos en los próximos 7 días.")
    elif accion == "eventos":
        for e in eventos(24 * int(sys.argv[2]) if len(sys.argv) > 2 else 48):
            print(f"{e['inicio'][:16].replace('T', ' ')}  {'(todo el día) ' if e['todo_el_dia'] else ''}{e['titulo']}")
    elif accion == "apuntar":
        from .fechas import describir, interpretar
        r = interpretar(" ".join(sys.argv[2:]))
        if "error" in r:
            sys.exit(r["error"])
        apuntar(r["texto"], r["cuando"], r["con_hora"], r["repetir"])
        print(f"Apuntado: «{r['texto']}» {describir(r['cuando'], r['repetir'])}")
    else:
        sys.exit(__doc__)
