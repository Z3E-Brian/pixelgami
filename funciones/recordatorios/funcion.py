"""Recordatorios y calendario en la conversación: entender lo que pide y hacerlo.

Los avisos no dependen de la asistente: los da avisos.py como servicio aparte, aunque esté apagada. Aquí está la
parte de la conversación (ver funciones/__init__.py):

  regla(texto)                lo que no se deja al router: pedir que le recuerde siempre es de aquí; "apunta que me
                              gusta el phonk" (sin fecha ni calendario) y "¿qué tengo mañana?" no
  entender(pedido, modelo)    qué pide: acción, qué y cuándo. El modelo solo separa la acción y el qué; la fecha la
                              calcula fechas.py con sus palabras exactas (un modelo 8B se equivoca con "pasado
                              mañana" o mete el tiempo dentro del qué)
  ejecutar(intención, pedido) lo hace
  pendiente(texto)            la respuesta a "¿todo el día o a qué hora?", si la hubo
  datos(pedido)               su agenda (Google Calendar y URLs iCal), para "¿qué tengo mañana?"
"""
import datetime
import difflib
import re
import sys
import time

from funciones import Pedido, Resultado
from identidad import BASE, USUARIO, nombres

from . import avisos, fechas
from . import google_calendario as calendario

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# pedir que le recuerde o avise: siempre es de recordatorios
RECORDATORIO = re.compile(r"\b(recu[eé]rda(me|le)|recordatorios?|av[ií]same|acu[eé]rdame|ponme una alarma|"
                          r"no me dejes olvidar|(que )?no se me (olvide|pase|vaya a olvidar))\b", re.I)
# verbos de anotar: pueden ser el calendario ("apunta el examen el 5") o su memoria ("apunta que me gusta el phonk")
APUNTAR = re.compile(r"\b(ap[uú]nt\w*|an[oó]t\w*|ag[eé]nd\w*|programa\w*|crea\w* (un )?evento|mete\w*|pon\w*|"
                     r"gu[aá]rd\w*)\b", re.I)
# lo que hace que "apunta/guarda X" sea del calendario aunque no traiga fecha entendible
DEL_CALENDARIO = re.compile(r"calendario|agenda|ag[eé]nd|evento|citas?\b|ex[aá]men|reuni[oó]n|entrega|gu[aá]rd", re.I)
# alarmas (son recordatorios) y quitar algo de la agenda: el router los mandaba a charla (prueba de fuego)
ALARMA = re.compile(r"\balarmas?\b", re.I)
QUITAR_DE_LA_AGENDA = re.compile(r"\b(borr\w*|elimin\w*|quit\w*|cancel\w*|despej\w*)\b.*\b(citas?|eventos?|calendario|"
                                 r"agenda)\b", re.I)
TODO_EL_DIA = re.compile(r"todo el d[ií]a|d[ií]a entero|sin hora|no tiene hora|a cualquier hora", re.I)
NO = re.compile(r"^\W*(no|mejor no|cancela|d[eé]jalo|olv[ií]dalo)\b", re.I)
ESPERA_RESPUESTA = 180  # segundos que vale la pregunta "¿todo el día o a qué hora?"
# preguntar qué tiene: es la agenda (datos), no un recordatorio
AGENDA = re.compile(r"\b(calendario|agenda|eventos?|citas?|reuni[oó]n|reuniones|qu[eé] tengo|tengo algo|"
                    r"pendientes|ex[aá]men(es)?|parcial(es)?|entregas?|cumplea[ñn]os)\b", re.I)

INTERPRETAR = nombres("""{usuario} le habla a {asistente} de sus RECORDATORIOS (avisos a cierta hora que le llegan como
notificación de {asistente}) o de apuntar algo en su CALENDARIO. Interpreta qué quiere aunque lo diga con otras palabras o
mal transcrito. Las ALARMAS también son recordatorios: poner, ver o quitar una alarma es "crear", "listar" o "borrar".
Responde solo el JSON.
accion:
- "crear": que le recuerde o le avise algo a una hora o un día ("recuérdame mañana a las 3 entregar el informe",
  "avísame en 20 minutos que saque la ropa", "ponme un recordatorio los lunes a las 7 para el gym", "no me dejes olvidar
  que el viernes es la reunión").
- "apuntar": anotar algo en su calendario de Google, para tenerlo agendado: citas, exámenes, entregas, reuniones o
  cualquier cosa futura con fecha que pida apuntar, agendar o guardar ("apunta en el calendario el examen el 5 a las 2",
  "agéndame el dentista el viernes a las 10", "agenda un examen para el 12", "guarda una cita con el médico el martes
  a las 9", "anota en mi agenda la reunión del lunes", "mete en el calendario que el 20 es el cumple de mi mamá").
  "crear" es cuando pide que le RECUERDES o AVISES; "apuntar" cuando pide anotarlo, agendarlo o guardarlo.
- "listar": qué recordatorios tiene ("¿qué recordatorios tengo?", "¿qué me ibas a recordar?").
- "borrar": quitar uno o todos ("quita el del gym", "borra el recordatorio de la ropa", "ya no me recuerdes lo del
  informe", "cancela todos los recordatorios").
- "ninguna": no es sobre recordatorios ni el calendario.
que: para "crear" o "apuntar": QUÉ hay que recordarle o apuntar, corto, como lo dijo y en su persona ("entregar el
  informe", "sacar la ropa", "llamar a mi mamá"), SIN ninguna palabra de tiempo (ni hora, ni "mañana", "pasado mañana",
  "el lunes"...); para "borrar": de qué era el que quiere quitar ("gym"), o "todos"; "" si no lo dijo.
cuando: para "crear" o "apuntar": CUÁNDO, copiado TAL CUAL de sus palabras ("mañana a las 3", "en 20 minutos", "todos los
  lunes a las 7am", "el 5 de noviembre", "entre semana a las 6:30"); "" si no dijo cuándo. No conviertas ni calcules.""")
ESQUEMA = {"type": "object", "properties": {
    "accion": {"type": "string", "enum": ["crear", "apuntar", "listar", "borrar", "ninguna"]},
    "que": {"type": "string"}, "cuando": {"type": "string"}}, "required": ["accion", "que", "cuando"]}

_pendiente = {"t": 0.0}  # lo que quería apuntar sin hora, esperando "todo el día" o "a las 3"


def regla(texto: str, orden: str = "", temas: list[str] = ()) -> bool | None:
    """Lo que no se deja al router (cambia con cualquier retoque de su prompt). True = es de recordatorios,
    False = no lo es, None = que decida el router."""
    if RECORDATORIO.search(texto) or ALARMA.search(texto) or QUITAR_DE_LA_AGENDA.search(texto):
        return True
    if APUNTAR.search(texto):
        # "apunta que mi cumple es en marzo" es una nota para su memoria; al calendario si lo nombra o trae fecha
        if not DEL_CALENDARIO.search(texto) and "error" in fechas.interpretar(texto):
            return False
        return None
    return False if AGENDA.search(texto) else None


def _normal(t: str) -> str:
    return fechas.plano(re.sub(r"[^\w ]", " ", t)).strip()


def _palabras_suyas(que: str, frase: str) -> bool:
    """¿La mayoría de las palabras de `que` las dijo él? («entregar lo de Proyectos» vs «entregue lo de Proyectos»: sí)"""
    palabras, dichas = _normal(que).split(), set(_normal(frase).split())
    return bool(palabras) and sum(w in dichas for w in palabras) >= 0.6 * len(palabras)


def entender(pedido: Pedido, modelo) -> dict | None:
    """Qué pide: {"accion", "que", "texto", "cuando", "repetir", "con_hora", "todo_el_dia", "error"}, o None si no es
    de recordatorios (o el modelo no respondió). "error" (o None) es por qué no se pudo calcular el cuándo.
    La fecha sale de sus palabras exactas (pedido.texto) y, si ahí no está, de la orden del router ("a las 5" tras
    "¿para cuándo?")."""
    texto, orden = pedido.texto, pedido.orden
    i = modelo(INTERPRETAR, pedido.combinado, ESQUEMA)
    if not i or i["accion"] == "ninguna":
        return None
    que, cuando = i["que"].strip(), i["cuando"].strip()
    accion = i["accion"]
    # "crea un evento", "guárdamela", "agéndalo": al calendario aunque el modelo diga recordatorio
    if accion == "crear" and not RECORDATORIO.search(texto) and DEL_CALENDARIO.search(texto):
        accion = "apuntar"
    pedido = {"accion": accion, "que": que, "texto": que, "cuando": None, "repetir": None, "con_hora": False,
              "todo_el_dia": bool(TODO_EL_DIA.search(texto) or TODO_EL_DIA.search(orden)), "error": None}
    if accion not in ("crear", "apuntar"):
        return pedido
    # primero sus palabras exactas; la versión con contexto solo si ahí no está el cuándo
    for frase in (texto, orden):
        r = fechas.interpretar(frase)
        if "error" not in r:
            break
    else:
        frase, r = "", fechas.interpretar(f"{cuando} {que}")
    if "error" in r:
        pedido["error"] = r["error"]
        return pedido
    # el qué del modelo queda mejor («tomar la pastilla» y no «tome la pastilla»), si de verdad lo dijo y no trae tiempo
    if que and "error" in fechas.interpretar(que) and _palabras_suyas(que, frase):
        r["texto"] = que[0].upper() + que[1:]
    pedido.update(texto=r["texto"], cuando=r["cuando"], repetir=r["repetir"], con_hora=r["con_hora"])
    return pedido


def _dia(cuando: datetime.datetime, repetir: dict | None) -> str:
    """«el viernes», sin la hora (para lo que va de todo el día o aún no tiene hora)."""
    return re.sub(r" a las? \d\d:\d\d$", "", fechas.describir(cuando, repetir))


def _apuntar(texto: str, cuando: datetime.datetime, con_hora: bool, repetir: dict | None) -> str:
    if not calendario.configurado():
        return ("No puedes apuntar en su Google Calendar: todavía no está conectado (falta publicar el Apps Script y "
                "correr google_calendario.py configurar). Díselo en una frase.")
    calendario.apuntar(texto, cuando, con_hora, repetir)
    cuando_txt = fechas.describir(cuando, repetir) if con_hora else f"{_dia(cuando, repetir)} (todo el día)"
    return (f"Ya quedó apuntado en su Google Calendar: «{avisos.a_ti(texto)}», {cuando_txt}. "
            "El día del evento le vas a avisar tú. Confírmaselo en una frase.")


def ejecutar(p: dict, pedido: Pedido | None = None) -> Resultado:
    """Hace lo que entender() devolvió."""
    a_ti = avisos.a_ti
    if p["accion"] in ("listar", "borrar"):
        return Resultado(_listar_o_borrar(p))
    if not p["texto"]:
        que = "apuntar algo en su calendario" if p["accion"] == "apuntar" else "un recordatorio"
        return Resultado(f"Quiere {que} pero no dijo qué. Pregúntaselo en una frase corta.", preguntar=True)
    if p["error"]:
        if "cuándo" in p["error"]:
            return Resultado(f"Quiere que le recuerdes «{a_ti(p['texto'])}», pero no dijo cuándo. Pregúntale para "
                             "cuándo, en una frase corta (todavía no está agendado).", preguntar=True)
        return Resultado(f"No pudiste agendarlo: {p['error']} Díselo y pregúntale de nuevo cuándo, en una frase.",
                         preguntar=True)
    if p["accion"] == "apuntar":
        if p["con_hora"] or p["todo_el_dia"]:
            return Resultado(_apuntar(p["texto"], p["cuando"], p["con_hora"], p["repetir"]))
        _pendiente.update(t=time.time(), texto=p["texto"], cuando=p["cuando"], repetir=p["repetir"])
        return Resultado(f"Quiere apuntar en su calendario «{a_ti(p['texto'])}» {_dia(p['cuando'], p['repetir'])}, "
                         "pero no dijo la hora. TODAVÍA NO está apuntado: pregúntale en una frase corta si es todo el "
                         "día o a qué hora.", preguntar=True)
    g = avisos.guardar_uno(p["texto"], p["cuando"], p["repetir"], "asistente")
    return Resultado(f"Ya quedó agendado: «{a_ti(g['texto'])}», {g['cuando_texto']}"
                     + (" (se repite)" if g["repetir"] else "")
                     + ". Le llegará como notificación tuya aunque estés apagada. Confírmaselo en una frase diciendo "
                     f"cuándo exactamente así: «{g['cuando_texto']}».")


def _listar_o_borrar(p: dict) -> str:
    a_ti, que = avisos.a_ti, p["que"]
    pendientes = avisos.pendientes()
    lista = "\n".join(f"- {a_ti(r['texto'])}: {r['cuando_texto']}" for r in pendientes[:10])
    if p["accion"] == "listar":
        if not pendientes:
            return "No tiene ningún recordatorio pendiente. Díselo en una frase."
        return "Sus recordatorios pendientes, del más próximo al más lejano (si son muchos, di los 3 o 4 primeros):\n" + lista
    if not pendientes:
        return "No tiene ningún recordatorio para quitar. Díselo en una frase."
    if re.fullmatch(r"(todos|todo|todas)( (los|mis) recordatorios)?", que, re.I):
        for r in pendientes:
            avisos.borrar(r["id"])
        return f"Ya borraste sus {len(pendientes)} recordatorios. Confírmaselo en una frase."

    def parecido(r):
        a, b = _normal(que), _normal(r["texto"])
        return 1.0 if a and a in b else difflib.SequenceMatcher(None, a, b).ratio()
    mejor = max(pendientes, key=parecido)
    if parecido(mejor) < 0.5:
        return f"No encontraste ningún recordatorio de «{que}». Los que tiene son:\n{lista}\nDíselo en una frase."
    avisos.borrar(mejor["id"])
    return f"Ya quitaste el recordatorio «{a_ti(mejor['texto'])}» ({mejor['cuando_texto']}). Confírmaselo en una frase."


def pendiente(texto: str) -> Resultado | None:
    """Si la asistente preguntó "¿todo el día o a qué hora?" y esto lo responde ("todo el día", "a las 3", "no"),
    lo apunta y cuenta qué pasó; None si no hay pregunta pendiente o el mensaje es otra cosa."""
    contexto = _respuesta_pendiente(texto)
    return Resultado(contexto) if contexto else None


def _respuesta_pendiente(texto: str) -> str | None:
    p = _pendiente
    if time.time() - p["t"] > ESPERA_RESPUESTA or len(texto.split()) > 10:
        return None
    if APUNTAR.search(texto) or RECORDATORIO.search(texto):  # un pedido nuevo, no la respuesta
        p["t"] = 0.0
        return None
    if TODO_EL_DIA.search(texto):
        p["t"] = 0.0
        return _apuntar(p["texto"], p["cuando"], False, p["repetir"])
    h = fechas.interpretar(f"{texto} pendiente")  # "a las 3", "como a las 4 y media", "3pm" (le falta el qué)
    if "error" not in h and h["con_hora"] and not re.search(r"\ben (\d+|media|un|una)\b", texto, re.I):
        p["t"] = 0.0
        return _apuntar(p["texto"], datetime.datetime.combine(p["cuando"].date(), h["cuando"].time()), True,
                        p["repetir"])
    if NO.search(texto):
        p["t"] = 0.0
        return "Al final no quiso apuntarlo; no se apuntó nada. Díselo en una frase."
    return None


def _dias_agenda(texto: str) -> tuple[int, int]:
    """(días, desde dentro de cuántos) según lo que pregunta: hoy, mañana, la semana..."""
    if re.search(r"pasado mañana", texto, re.I):
        return 1, 2
    if re.search(r"\bmañana\b", texto, re.I):
        return 1, 1
    if re.search(r"\bhoy\b", texto, re.I):
        return 1, 0
    if re.search(r"\b(semana|pr[oó]ximos d[ií]as|pendientes)\b", texto, re.I):
        return 7, 0
    if re.search(r"\bmes\b", texto, re.I):
        return 31, 0
    return 3, 0


def datos(pedido: Pedido) -> str | None:
    """Su agenda, si pregunta qué tiene ("¿qué tengo mañana?"): Google Calendar y/o URLs iCal."""
    if not AGENDA.search(pedido.texto):
        return None
    dias, desde = _dias_agenda(pedido.texto)
    lineas = agenda(dias, desde, pedido.ahora)
    if avisos.URLS_CALENDARIO.exists():
        lineas.append(_agenda_ical(dias, desde))
    if not lineas and not calendario.configurado():
        return None
    return (f"Calendario de {USUARIO} ({dias} día(s) desde {'hoy' if not desde else f'dentro de {desde}'}):\n"
            + ("\n".join(lineas) or "No hay nada en el calendario para esos días."))


def _agenda_ical(dias: int, desde: int) -> str:
    """Los eventos de las URLs iCal (calendario.url), con el lector del servidor MCP de Google."""
    sys.path.insert(0, str(BASE / "google-mcp"))
    import servidor_google
    return servidor_google.agenda(dias, desde)


def agenda(dias: int, desde: int, ahora: datetime.datetime) -> list[str]:
    """Eventos de su Google Calendar: `dias` días a partir de hoy + `desde`. [] si no está conectado."""
    if not calendario.configurado():
        return []
    inicio = max(datetime.datetime.combine(ahora.date(), datetime.time()) + datetime.timedelta(days=desde),
                 ahora - datetime.timedelta(hours=1))
    lineas = []
    for e in calendario.eventos(24 * dias, inicio):
        ini = datetime.datetime.fromisoformat(e["inicio"])
        lineas.append(f"- {DIAS[ini.weekday()]} {ini.day}/{ini.month}, "
                      f"{'todo el día' if e['todo_el_dia'] else f'{ini:%H:%M}'}: {e['titulo']}"
                      + (f" ({e['lugar']})" if e["lugar"] else ""))
    return lineas
