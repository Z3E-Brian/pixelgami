"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no guardan ni apuntan nada)."""
from .fechas import describir

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "acuérdate de que me gusta el phonk", {"charla"}, []),
    ("", "", "recuérdame mañana a las 3 entregar lo de proyectos", {"recordatorio"}, ["proyectos"]),
    ("", "", "qué tengo en el calendario mañana?", {"charla"}, []),
    ("", "", "apunta que mi cumple es en marzo", {"charla"}, []),
    ("", "", "apunta en el calendario el examen el 5 a las 2", {"recordatorio"}, ["examen"]),
    # prueba de fuego (MASSIVE): las alarmas son recordatorios; quitar algo de la agenda también
    ("", "", "apaga la alarma", {"recordatorio"}, []),
    ("", "", "quiero ver todas mis alarmas programadas", {"recordatorio"}, []),
    ("", "", "puedes borrar mi cita con el dentista", {"recordatorio"}, []),
]

# cadena completa: router -> entender. (la asistente, el usuario antes, el usuario, acción esperada, palabra del qué, cuándo esperado
# como lo dice describir(), o None)
CADENA = [
    ("", "", "recuérdame mañana a las 3 que entregue lo de Proyectos", "crear", "proyectos", "mañana a las 15:00"),
    ("", "", "avísame en 20 minutos q saque la ropa", "crear", "ropa", "en 20 min"),
    ("", "", "ponme un recordatorio todos los lunes a las 7 de la mañana para ir al gym", "crear", "gym", "todos los lunes a las 07:00"),
    ("", "", "Asistente, no me dejes olvidar que el viernes a las 10 tengo reunión con Saray", "crear", "saray", "el viernes a las 10:00"),
    ("", "", "oye recuerdame en media hora llamar a mi mamá", "crear", "mamá", "en 30 min"),
    ("", "", "puedes recordarme pasado mañana revisar el correo de la U", "crear", "correo", "a las 08:00"),
    ("", "", "quiero que me avises todos los días a las 10 de la noche que tome la pastilla", "crear", "pastilla", "todos los días a las 22:00"),
    ("", "", "recuérdame el 1 de cada mes pagar el internet", "crear", "internet", "el 1 de cada mes"),
    ("", "", "ocupo que me recuerdes lunes y miércoles a las 6 de la tarde la clase de inglés", "crear", "inglés", "todos los lunes y miércoles a las 18:00"),
    ("", "", "recuérdame sacar la basura", "crear", "basura", None),
    ("¿Para cuándo te recuerdo sacar la basura?", "", "a las 5", "crear", "basura", "a las 17:00"),
    ("", "", "qué recordatorios tengo?", "listar", "", None),
    ("", "", "quita el recordatorio del gym", "borrar", "gym", None),
    ("", "", "ya no me recuerdes lo de la pastilla", "borrar", "pastilla", None),
    ("", "", "borra todos los recordatorios", "borrar", "todos", None),
    ("", "", "apunta en el calendario el examen de globales el 5 de noviembre a las 2", "apuntar", "examen", "a las 14:00"),
    ("", "", "agéndame el dentista el viernes a las 10", "apuntar", "dentista", "el viernes a las 10:00"),
    ("", "", "anota en mi agenda la reunión del lunes a las 9", "apuntar", "reunión", "el lunes a las 09:00"),
    ("", "", "mete en el calendario que el 20 de noviembre es el cumple de mi mamá", "apuntar", "cumple", "20 de noviembre"),
    ("", "", "puedes poner en mi calendario la cita del médico pasado mañana a las 4 y media", "apuntar", "médico", "a las 16:30"),
    ("", "", "Asistente, crea un evento para el sábado: partido de fútbol a las 3", "apuntar", "partido", "el sábado a las 15:00"),
    ("", "", "agenda la entrega del proyecto el 30 de noviembre", "apuntar", "entrega", "30 de noviembre"),
    ("", "", "guarda una cita con el dentista el martes a las 9", "apuntar", "dentista", "el martes a las 09:00"),
    ("", "", "agenda un examen de cálculo para el 12", "apuntar", "examen", "12 de noviembre"),
    ("", "", "tengo cita con el médico el jueves a las 3, guárdamela", "apuntar", "médico", "a las 15:00"),
    ("", "", "agéndame una reunión con Saray mañana a las 4", "apuntar", "saray", "mañana a las 16:00"),
    ("", "", "apunta una cita para el primero de noviembre", "apuntar", "cita", "domingo"),
    ("", "", "apunta que el examen de cálculo es el dos de diciembre", "apuntar", "examen", "2 de diciembre"),
    ("", "", "recuérdame a las tres llamar al profe", "crear", "profe", "a las 15:00"),
    ("", "", "dime mis alarmas", "listar", "", None),
    ("", "", "apaga mi primera alarma", "borrar", "", None),
]


def revisar(caso: tuple, intencion: dict | None, aviso: str) -> tuple[bool, str]:
    """¿entender() devolvió lo esperado? (bien, cómo se ve)"""
    _, _, _, accion, palabra, cuando = caso
    p = intencion or {"accion": "ninguna", "texto": "", "cuando": None, "error": None}
    dicho = p["error"] or (describir(p["cuando"], p["repetir"]) if p["cuando"] else "")
    ok = p["accion"] == accion and palabra in p["texto"].lower() and \
        (cuando in dicho if cuando is not None else accion not in ("crear", "apuntar") or bool(p["error"]))
    return ok, f"{p['accion']} «{p['texto']}» => {dicho}"
