"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""
from funciones.web import funcion as F

RAM = "Encontré una RAM de 8GB DDR4 3200MHz por ₡52.000 y otra OEM por ₡25.000 en ExtremeTech."

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "holaa, puedes revisar en cuanto estan las ram de 8gb en extreme y mostrarme?", {"web"}, ["ram"]),
    ("", "", "revisa un momento en cuanto esta una ram de 8gb en extreme", {"web"}, ["ram"]),
    ("", "", "busca ventiladores para pc en extreme y abre la pestaña", {"web"}, ["ventilador"]),
    ("", "", "fíjate cuánto sale un SSD de 1 tera", {"web"}, ["ssd"]),
    ("", "", "averigua si ya salió el GTA 6", {"web"}, ["gta"]),
    ("", "", "consulta en wikipedia quién inventó el transistor", {"web"}, ["transistor"]),
    (RAM, "revisa en cuanto esta una ram de 8gb en extreme", "q dicen las opiniones en reddit?", {"web"}, ["reddit", "ram"]),
    ("No encontré nada en Reddit. ¿Quieres que lo busque en otro sitio?", "q dicen las opiniones en reddit?", "si",
     {"web"}, ["ram"]),
    ("Encontré ventiladores en ExtremeTech. ¿Quieres que abra la pestaña?", "busca ventiladores en extreme", "dale",
     {"web"}, ["abr"]),
    (RAM, "", "abre la primera para verla en opera", {"web"}, ["abr"]),
    (RAM, "", "y en amazon?", {"web"}, ["amazon", "ram"]),
    ("", "", "ponme el trailer de silksong", {"web"}, ["silksong"]),
    ("", "", "Quiero saber cómo ver mi nota de admisión a la Universidad Nacional.", {"web"}, ["admisi"]),
    ("", "", "puedes revisar si hay mods para mi mundito de minecraft", {"web"}, ["minecraft"]),
]

# cadena: router -> entender (intérprete + _revisar). (la asistente, el usuario antes, el usuario, lo esperado). Se
# prueba el intérprete aunque el router no elija "web" (como "abre el segundo" justo después de una búsqueda).
CON_CUALQUIER_TEMA = True
CADENA = [
    ("", "", "puedes buscar imagenes de 2b en opera y mostrarme?",
     {"accion": "buscar", "tipo": "imagenes", "sitio": "", "navegador": True}),
    ("", "", "ponme el trailer de silksong", {"accion": "buscar", "tipo": "videos"}),
    ("", "", "busca wallpapers de asistente", {"accion": "buscar", "tipo": "imagenes"}),
    ("", "", "revisa en cuanto esta una ram de 8gb en extreme y muéstramela",
     {"accion": "buscar", "sitio": "extremetechcr.com", "navegador": True}),
    ("", "", "busca en opera cómo instalar steam en cachyos", {"accion": "buscar", "sitio": "", "navegador": True}),
    ("", "", "búscame en google qué es un NAS", {"accion": "buscar", "sitio": "", "navegador": True}),
    ("", "", "revisa ram de 8gb en extremetech y entra en la mas barata",
     {"accion": "buscar", "sitio": "extremetechcr.com", "navegador": True}),
    ("", "", "llévame a la página de ventiladores de extreme", {"accion": "buscar", "sitio": "extremetechcr.com", "navegador": True}),
    (RAM, "revisa en cuanto esta una ram de 8gb en extreme", "ponme el trailer de silksong",
     {"accion": "buscar", "tipo": "videos"}),
    ("", "", "qué noticias hay de la RX 9070", {"accion": "buscar", "navegador": False}),
    ("", "", "checa el precio de la 4060 en amazon", {"accion": "buscar", "sitio": "amazon.com", "navegador": False}),
    (RAM, "revisa en cuanto esta una ram de 8gb en extreme", "q dicen en reddit?",
     {"accion": "buscar", "sitio": "reddit.com"}),
    ("Encontré ventiladores en ExtremeTech. ¿Quieres que abra la pestaña?", "busca ventiladores en extreme", "dale",
     {"accion": "abrir", "numero": 1}),
    (RAM, "", "abre el segundo", {"accion": "abrir", "numero": 2}),
    ("", "", "abre un pestaña de opera con la extreme", {"accion": "ir", "sitio": "extremetechcr.com"}),
    ("", "", "llévame a reddit", {"accion": "ir", "sitio": "reddit.com"}),
    ("", "", "abre la página de amazon", {"accion": "ir", "sitio": "amazon.com"}),
    (RAM, "", "qué dice el primero", {"accion": "leer", "numero": 1}),
]


def preparar() -> None:
    """Una búsqueda ya hecha, para "abre el segundo", "qué dice el primero"."""
    F._web.update(resultados=[type("R", (), {"title": "RAM 8GB DDR4", "link": "https://x", "snippet": ""})()],
                  consulta="RAM 8GB site:extremetechcr.com")


def limpiar() -> None:
    F._web.update(resultados=[], consulta="")


def revisar(caso: tuple, i: dict | None, aviso: str) -> tuple[bool, str]:
    esperado, i = caso[3], i or {}
    malos = {k: i.get(k) for k, v in esperado.items() if i.get(k) != v}
    return not malos, (f"{i.get('accion')} «{i.get('consulta', '')[:30]}» {i.get('tipo')} {i.get('sitio')!r} "
                       f"nav={i.get('navegador')} n={i.get('numero')}" + (f"  {malos}" if malos else ""))
