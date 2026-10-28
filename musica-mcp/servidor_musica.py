"""Herramienta MCP para la asistente: poner música en la app YouTube Music Desktop (ytmdesktop) del usuario.

Busca canciones, artistas y listas en YouTube Music (ytmusicapi, sin cuenta) y las reproduce en la
app con su Companion Server (http://127.0.0.1:9863, se activa en Ajustes > Integraciones). El token
de autorización se guarda en ~/.config/pixelgami/ytmd.token (se pide una vez con `autorizar`).
"""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from ytmusicapi import YTMusic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from identidad import nombres  # noqa: E402

YTMD = "http://127.0.0.1:9863/api/v1"
TOKEN = Path.home() / ".config/pixelgami/ytmd.token"
APP_ID, APP_NOMBRE, APP_VERSION = "pixelgami", nombres("{asistente} asistente"), "1.0.0"
DESKTOP = "youtube-music-desktop-app"

mcp = FastMCP("musica")
_yt = None


def _ytmusic() -> YTMusic:
    global _yt
    if _yt is None:
        _yt = YTMusic()  # con language= la búsqueda filtrada vuelve vacía
    return _yt


def _pedir(metodo: str, ruta: str, datos: dict | None = None, timeout: float = 10, con_token: bool = True):
    cabeceras = {"Content-Type": "application/json"}
    if con_token:
        if not TOKEN.exists():
            raise RuntimeError(nombres("{asistente} todavía no está autorizad{a} en YouTube Music (falta el token)"))
        cabeceras["Authorization"] = TOKEN.read_text().strip()
    req = urllib.request.Request(YTMD + ruta, json.dumps(datos).encode() if datos is not None else None,
                                 cabeceras, method=metodo)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        cuerpo = r.read()
    return json.loads(cuerpo) if cuerpo else None


def _app_lista() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 9863), timeout=1).close()
        return True
    except OSError:
        return False


def asegurar_app() -> None:
    """Abre YouTube Music si no está abierto (en su scope de app.slice, como lo que abre el usuario) y espera al servidor."""
    if _app_lista():
        return
    subprocess.Popen(["systemd-run", "--user", "--scope", "--slice=app.slice", "--collect", "-q",
                      "gtk-launch", DESKTOP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        if _app_lista():
            time.sleep(2)  # el servidor responde antes de que el reproductor esté listo
            return
    raise RuntimeError("YouTube Music no abrió o no tiene activado el Companion Server")


def autorizar() -> str:
    """Pide el token a la app: muestra un código en YouTube Music y el usuario lo acepta ahí."""
    asegurar_app()
    codigo = _pedir("POST", "/auth/requestcode", {"appId": APP_ID, "appName": APP_NOMBRE,
                                                    "appVersion": APP_VERSION}, con_token=False)["code"]
    print(f"Acepta en YouTube Music el código {codigo}", flush=True)
    token = _pedir("POST", "/auth/request", {"appId": APP_ID, "code": codigo}, timeout=60, con_token=False)["token"]
    TOKEN.write_text(token)
    TOKEN.chmod(0o600)
    return "Autorizada."


def comando(nombre: str, datos=None) -> None:
    asegurar_app()
    _pedir("POST", "/command", {"command": nombre, **({"data": datos} if datos is not None else {})})


def estado() -> dict:
    asegurar_app()
    return _pedir("GET", "/state")


def _artistas(r: dict) -> str:
    return ", ".join(a["name"] for a in r.get("artists") or [] if a.get("name"))


def buscar(texto: str, tipo: str = "canciones", cuantos: int = 5) -> list[dict]:
    """Canciones o listas de YouTube Music: [{"videoId"|"playlistId", "titulo", "artista"}]."""
    filtro = {"canciones": "songs", "listas": "playlists", "artistas": "artists"}[tipo]
    resultados = _ytmusic().search(texto, filter=filtro, limit=cuantos)[:cuantos]
    if tipo == "canciones":
        return [{"videoId": r["videoId"], "titulo": r["title"], "artista": _artistas(r)}
                for r in resultados if r.get("videoId")]
    if tipo == "listas":
        return [{"playlistId": r["browseId"].removeprefix("VL"), "titulo": r["title"], "artista": r.get("author") or ""}
                for r in resultados if r.get("browseId")]
    # artista: su radio (mezcla de sus canciones), que sí se puede reproducir como lista
    salida = []
    for r in resultados[:1]:
        info = _ytmusic().get_artist(r["browseId"])
        lista = (info.get("songs") or {}).get("browseId") or ""
        if lista:
            salida.append({"playlistId": lista.removeprefix("VL"), "titulo": f"canciones de {r['artist']}",
                           "artista": r["artist"]})
    return salida


def poner(item: dict) -> str:
    """Reproduce una canción o una lista en la app."""
    datos = {"videoId": item["videoId"]} if item.get("videoId") else {"playlistId": item["playlistId"]}
    comando("changeVideo", datos)
    return f"Sonando: {item['titulo']}" + (f" de {item['artista']}" if item.get("artista") else "")


def sonando() -> str:
    e = estado()
    video, jugador = e.get("video") or {}, e.get("player") or {}
    if not video:
        return "No está sonando nada."
    pausado = jugador.get("trackState") != 1
    return (f"{'En pausa' if pausado else 'Sonando'}: {video.get('title', '?')} de {video.get('author', '?')} "
            f"(volumen {jugador.get('volume', '?')}).")


@mcp.tool()
def poner_musica(que: str, tipo: str = "canciones") -> str:
    """Pone música en YouTube Music. que: canción, artista o género; tipo: "canciones", "listas" (géneros,
    ambientes: "rock en español", "lofi para estudiar") o "artistas"."""
    try:
        encontrados = buscar(que, tipo, 1)
        return poner(encontrados[0]) if encontrados else f"No encontré nada para \"{que}\"."
    except Exception as e:
        return f"No pude poner música: {e}"


@mcp.tool()
def controlar_musica(accion: str) -> str:
    """Controla YouTube Music. accion: "pausa", "seguir", "siguiente", "anterior", "subir", "bajar" o "que_suena"."""
    try:
        if accion == "que_suena":
            return sonando()
        nombre = {"pausa": "pause", "seguir": "play", "siguiente": "next", "anterior": "previous",
                  "subir": "volumeUp", "bajar": "volumeDown"}[accion]
        comando(nombre)
        return "Hecho."
    except Exception as e:
        return f"No pude: {e}"


if __name__ == "__main__":
    if sys.argv[1:] == ["autorizar"]:
        print(autorizar())
    else:
        mcp.run()
