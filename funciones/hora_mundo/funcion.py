"""Hora en otros lugares: el modelo solo dice la zona horaria de cada lugar (eso lo sabe bien) y la cuenta la hace
Python (solo, Qwen dijo que en Barcelona eran las 14:15 cuando eran las 21:15)."""
import datetime
import re
import zoneinfo

from funciones import Pedido, Resultado
from identidad import LUGAR, ZONA, nombres

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
HORA_LUGAR = re.compile(r"\b(hora|horas|horario|huso|diferencia horaria|qu[eé] d[ií]a es)\b", re.I)
INTERPRETAR = nombres("""{usuario} vive en {lugar}. Si pregunta la hora, la fecha o la diferencia horaria de OTRO lugar (ciudad,
país o región), devuelve cada lugar con su zona horaria IANA exacta (ej. Barcelona -> Europe/Madrid, Japón -> Asia/Tokyo,
México -> America/Mexico_City, Nueva York -> America/New_York, Argentina -> America/Argentina/Buenos_Aires).
Si pregunta la hora de aquí ("¿qué hora es?") o no pregunta por la hora de un lugar, lugares vacío.""")
ESQUEMA = {"type": "object", "properties": {"lugares": {"type": "array", "items": {"type": "object", "properties": {
    "lugar": {"type": "string"}, "zona": {"type": "string"}}, "required": ["lugar", "zona"]}}}, "required": ["lugares"]}
AQUI = re.compile(nombres(r"{usuario_re}|aqu[ií]"), re.I)


# "en Japón", "con México", "para allá", "la diferencia": nombra otro lugar
OTRO_LUGAR = re.compile(r"\b(en|con|para|all[aá]|diferencia)\b", re.I)


# pedir una conversión u otra zona ("diferencia horaria con Madrid", "de GMT a EST") siempre es de aquí
CONVERSION = re.compile(r"diferencia horaria|zona horaria|huso horario|\bconvier\w*\b.*\bhora|\bhoras? entre\b|"
                        r"\bhoras? de (diferencia|distancia)\b", re.I)


def regla(texto: str, orden: str, temas: list[str]) -> bool | None:
    """Lo que no se deja al router. Es de aquí convertir la hora entre lugares. No lo es: la hora sin nombrar otro
    lugar (la de aquí: charla) ni lo que no habla de la hora; el router mandaba aquí el clima de Alicante, la tasa del
    dólar o el tráfico ("de otro lugar"), y se respondía con la hora de allá (prueba de fuego)."""
    if CONVERSION.search(texto) or CONVERSION.search(orden):
        return True
    if not (HORA_LUGAR.search(texto) or HORA_LUGAR.search(orden)):
        return False  # no habla de la hora ("¿y en Japón?" sí: el router la escribe "qué hora es en Japón")
    return None if OTRO_LUGAR.search(texto) else False


def detectar(texto: str) -> bool:
    return bool(HORA_LUGAR.search(texto) and OTRO_LUGAR.search(texto))


def entender(pedido: Pedido, modelo) -> list[dict] | None:
    """Los lugares de otra zona por los que pregunta ([{"lugar", "zona"}], hasta 4); None si ninguno."""
    r = modelo(INTERPRETAR, pedido.combinado, ESQUEMA) or {}
    lugares = [l for l in r.get("lugares", [])[:4] if l["zona"] != ZONA and not AQUI.search(l["lugar"])]
    return lugares or None


def hora_en(lugar: str, zona: str, aqui: datetime.datetime) -> str | None:
    """'Hora actual en Barcelona: 21:15 del miércoles 21 de octubre (8 h más que en San José)'; None si la zona no existe."""
    try:
        alla = aqui.astimezone(zoneinfo.ZoneInfo(zona))
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return None
    dif = (alla.utcoffset() - aqui.utcoffset()).total_seconds() / 3600
    dif_txt = f"la misma hora que en {LUGAR}" if dif == 0 else \
        f"{abs(dif):g} h {'más' if dif > 0 else 'menos'} que en {LUGAR}"
    return f"Hora actual en {lugar}: {alla:%H:%M} del {DIAS[alla.weekday()]} {alla.day} de {MESES[alla.month - 1]} ({dif_txt})"


def ejecutar(lugares: list[dict], pedido: Pedido) -> Resultado | None:
    aqui = pedido.ahora.astimezone()
    lineas = [h for l in lugares if (h := hora_en(l["lugar"], l["zona"], aqui))]
    if not lineas:
        return None
    return Resultado("\n".join(lineas) + "\nDi esa hora tal cual; no la calcules tú ni busques en internet.",
                     hizo=False)
