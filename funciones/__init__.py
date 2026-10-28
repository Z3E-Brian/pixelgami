"""Funciones de la asistente: cada carpeta de funciones/ es una cosa que sabe hacer (ventanas, correo, música,
internet, recordatorios...). El núcleo (agent/asistente_contexto.py) solo entiende y conversa: arma el router con las
funciones activas, le pasa a cada una lo que es suyo y junta lo que devuelven para la respuesta.

Una función es una carpeta con:
  funcion.yaml   tema, descripción y ejemplos para el router; orden; a quién le cede; qué decir si falla
  funcion.py     lo que hace (ver abajo)
  pruebas.py     casos con el modelo para pruebas_intencion.py; test_*.py: pruebas sin modelo (unittest)

funcion.py (solo entender y ejecutar son obligatorias):
  entender(pedido, modelo) -> intención | None   qué pide (None: nada para esta función). modelo(sistema, texto,
                                                  esquema) -> dict | None es el modelo local con salida JSON.
  ejecutar(intención, pedido) -> Resultado | None lo hace y cuenta qué pasó, en hechos (None: nada que contar)
  aviso(intención) -> str                         lo que la asistente dice mientras lo hace ("Revisando el spam.")
  regla(texto, orden, temas) -> bool | None       regla fija sobre su tema, por encima del router: True = es mío,
                                                  False = no es mío, None = que decida el router
  detectar(texto) -> bool                         respaldo si el router no responde (Ollama apagado)
  pendiente(texto) -> Resultado | None            la respuesta a algo que la función preguntó ("¿a qué hora?",
                                                  "¿los borro?"); se revisa antes del router
  datos(pedido) -> str | None                     información para responder aunque no pida hacer nada
                                                  ("¿qué tengo mañana?" -> la agenda)
  para_el_router() -> str | None                  lo que el router debe saber de la conversación ("última búsqueda:
                                                  ...") para entender "ábrelo" o "¿y en Reddit?"
  respondio()                                     la asistente empezó a responder (para no repetir lo ya dicho)

Activas: perfil.yaml -> funciones: [ventanas, correo, ...] (si no está, todas, por su `orden`). Ver docs/FUNCIONES.md.
"""
import datetime
import importlib
import importlib.util
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

try:  # el registro del backend; fuera de él (pruebas, comprobar.py, servicios) el estándar
    from loguru import logger as log
except ImportError:
    import logging
    log = logging.getLogger("funciones")

CARPETA = Path(__file__).resolve().parent
BASE = CARPETA.parent
DATOS = BASE / "datos"  # lo que guardan las funciones; fuera del código (no va al repo público)
RESERVADOS = ["charla"]  # temas del núcleo: ninguna función puede usarlos


@dataclass
class Pedido:
    """Un mensaje del usuario, ya pasado por el router."""
    texto: str  # sus palabras exactas
    orden: str  # reescrita por el router con la conversación ("a las 5" -> "recuérdame a las 5 sacar la basura")
    combinado: str  # la orden y sus palabras exactas: lo que se le pasa al modelo (de ahí salen los detalles)
    ahora: datetime.datetime
    necesita_contexto: bool = False  # el mensaje no se entendía solo ("ábrelo", "sí", "¿y en Japón?")
    temas: frozenset = frozenset()  # los temas que eligió el router

    @property
    def resuelto(self) -> str:
        """La orden si hizo falta la conversación para entenderlo; si no, sus palabras tal cual (al reescribir un
        mensaje que ya estaba completo se pueden perder detalles)."""
        return self.orden if self.necesita_contexto else self.texto


@dataclass
class Resultado:
    """Lo que pasó, para que la asistente lo cuente."""
    contexto: str  # los hechos, con cómo decirlos ("Ya quedó agendado: ... Confírmaselo en una frase.")
    preguntar: bool = False  # falta un dato o hay que confirmar: la respuesta tiene que ser una pregunta
    hizo: bool = True  # hizo algo: la asistente no se pone a ofrecer otras cosas
    con_notas: bool = False  # las notas de memoria ayudan; por defecto no: se mezclan con los datos y confunden
    # revisa cada frase de la respuesta: devuelve lo que se dice en su lugar si inventó algo (un precio que no salió
    # en la búsqueda), o None si está bien
    revisar_frase: Callable[[str], str | None] | None = field(default=None, repr=False)


class Funcion:
    """Una función cargada: su funcion.yaml y su funcion.py, con lo opcional ya resuelto."""

    def __init__(self, nombre: str):
        import yaml
        self.nombre = nombre
        conf = yaml.safe_load((CARPETA / nombre / "funcion.yaml").read_text())
        self.tema: str = conf["tema"]
        self.descripcion: str = conf["descripcion"].rstrip("\n")
        self.ejemplos: str = (conf.get("ejemplos") or "").rstrip("\n")
        self.cede_a: list[str] = conf.get("cede_a") or []
        self._si_falla: str = conf.get("si_falla") or f"No pudiste hacerlo ({nombre}). Díselo en una frase."
        self.modulo = importlib.import_module(f"funciones.{nombre}.funcion")

    def __repr__(self) -> str:
        return f"Funcion({self.nombre!r})"

    def _opcional(self, nombre: str, *args, defecto=None):
        hacer = getattr(self.modulo, nombre, None)
        return hacer(*args) if hacer else defecto

    def entender(self, pedido: Pedido, modelo):
        return self.modulo.entender(pedido, modelo)

    def ejecutar(self, intencion, pedido: Pedido) -> Resultado | None:
        return self.modulo.ejecutar(intencion, pedido)

    def si_falla(self, error: Exception) -> str:
        """Lo que se le dice a la asistente si ejecutar() falló."""
        return self._si_falla.replace("{error}", str(error))

    def aviso(self, intencion) -> str:
        return self._opcional("aviso", intencion, defecto="")

    def regla(self, texto: str, orden: str = "", temas: list[str] = ()) -> bool | None:
        return self._opcional("regla", texto, orden or texto, list(temas))

    def detectar(self, texto: str) -> bool:
        return bool(self._opcional("detectar", texto) if hasattr(self.modulo, "detectar") else self.regla(texto))

    def pendiente(self, texto: str) -> Resultado | None:
        return self._opcional("pendiente", texto)

    def datos(self, pedido: Pedido) -> str | None:
        return self._opcional("datos", pedido)

    def para_el_router(self) -> str | None:
        return self._opcional("para_el_router")

    def respondio(self) -> None:
        self._opcional("respondio")


def disponibles() -> list[str]:
    """Las carpetas de funciones/ que tienen funcion.yaml, por su `orden` (y luego por nombre)."""
    import yaml
    rutas = list(CARPETA.glob("*/funcion.yaml"))
    orden = {p.parent.name: (yaml.safe_load(p.read_text()).get("orden", 100), p.parent.name) for p in rutas}
    return sorted(orden, key=orden.get)


def cargar(activas: list[str] | None = None) -> list[Funcion]:
    """Las funciones activas, en el orden dado (None = todas las disponibles). Falla si nombra una que no existe o si
    dos usan el mismo tema."""
    nombres = disponibles() if activas is None else list(activas)
    faltan = set(nombres) - set(disponibles())
    if faltan:
        raise ValueError(f"perfil.yaml nombra funciones que no existen en funciones/: {', '.join(sorted(faltan))}")
    cargadas = [Funcion(n) for n in nombres]
    vistos = {t: "el núcleo" for t in RESERVADOS}
    for f in cargadas:
        if f.tema in vistos:
            raise ValueError(f"funciones/{f.nombre}: el tema «{f.tema}» ya lo usa {vistos[f.tema]}")
        vistos[f.tema] = f"funciones/{f.nombre}"
    return cargadas


def carpeta_datos(nombre: str) -> Path:
    """datos/<función>/, creada si hace falta."""
    ruta = DATOS / nombre
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def mcp(nombre: str):
    """El servidor MCP <nombre>-mcp/servidor_<nombre>.py como módulo, cargado una sola vez y recién cuando se usa (así
    funcion.py importa sin sus dependencias, que están en el entorno del backend). Núcleo y funciones comparten el
    mismo: su estado, como la última pantalla donde se cerró algo, es uno solo."""
    return _Servidor(nombre)


class _Servidor:
    def __init__(self, nombre: str):
        object.__setattr__(self, "_nombre", nombre)

    def _modulo(self):
        clave = f"mcp_{self._nombre}"
        if clave not in sys.modules:
            ruta = BASE / f"{self._nombre}-mcp" / f"servidor_{self._nombre}.py"
            spec = importlib.util.spec_from_file_location(clave, ruta)
            modulo = importlib.util.module_from_spec(spec)
            sys.modules[clave] = modulo
            try:
                spec.loader.exec_module(modulo)
            except BaseException:
                del sys.modules[clave]
                raise
        return sys.modules[clave]

    def __getattr__(self, atributo: str):
        return getattr(self._modulo(), atributo)

    def __setattr__(self, atributo: str, valor) -> None:
        setattr(self._modulo(), atributo, valor)


class Frases:
    """Formas de decir lo mismo, para los avisos: nunca la misma dos veces seguidas. Cada opción es un texto con
    {campos}; "a el" y "de el" quedan "al" y "del" y la primera letra va en mayúscula."""

    def __init__(self, opciones: dict[str, list[str]]):
        self.opciones = opciones
        self._ultima: dict[str, str] = {}

    def decir(self, clave: str, **datos) -> str:
        posibles = [o for o in self.opciones[clave] if o != self._ultima.get(clave)] or self.opciones[clave]
        self._ultima[clave] = elegida = random.choice(posibles)
        frase = re.sub(r"\bde el\b", "del", re.sub(r"\ba el\b", "al", elegida.format(**datos)))
        return frase[:1].upper() + frase[1:]


def y(cosas: list[str]) -> str:
    """["a", "b", "c"] -> "a, b y c"."""
    return " y ".join([", ".join(cosas[:-1]), cosas[-1]] if len(cosas) > 1 else cosas)
