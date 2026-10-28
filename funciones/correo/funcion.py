"""El correo (Gmail o Google Workspace por IMAP, con contraseña de aplicación): revisar, leer, marcar, archivar y
mover entre bandeja, spam y papelera. Nunca borrar para siempre, vaciar, enviar ni responder.

Qué quiere hacer lo interpreta el modelo (aunque no diga "correo" o Whisper lo escriba mal); lo hace
google-mcp/servidor_google.py. Sacar correos de donde están se confirma: la papelera siempre y mover más de 3
(pendiente() recibe el "sí").
"""
import re
import time

from funciones import Frases, Pedido, Resultado, mcp, y
from identidad import PERFIL, USUARIO, nombres

google = mcp("google")

TEMA = re.compile(r"\b(correos?|e-?mails?|mails?|gmail|bandeja|spam|no deseados?|papelera|destacados?|archivad|me (escribi[oó]|escribieron|mand[oó]|mandaron)|me lleg[oó])", re.I)
SI = re.compile(r"^\W*(s[ií]|dale|ok|okay|hazlo|claro|va|de una|confirmo|adelante|ya|b[oó]rr\w*|mu[eé]v\w*|s[aá]c\w*)\b", re.I)
NO = re.compile(r"^\W*(no|mejor no|cancela|d[eé]jalo|espera)\b", re.I)
# cómo llama el usuario a remitentes que no se parecen a su nombre real
ALIAS_REMITENTE = PERFIL.get("alias_remitentes", {})
INTERPRETAR = nombres("""{usuario} le habla a {asistente} de su correo (Gmail). Interpreta QUÉ quiere hacer aunque lo diga con otras
palabras, sin decir "correo", o mal transcrito por el reconocimiento de voz. Responde solo el JSON.
acciones (lista; normalmente una sola, varias si pide varias cosas a la vez):
- "ver": revisar, contar o buscar correos (la lista); preguntar qué hay, cuántos, si le escribió alguien.
- "leer": abrir UN correo y contar lo que DICE por dentro ("léemelo", "¿qué dice el de la UNI?", "dime más de la
  rectoría", "ábrelo y dime", "revisa el último de la U", "de qué trata ese", "los detalles").
- "leido": solo marcarlos como leídos, sin leerlos ("márcalos", "ya los vi", "déjalos leídos", "ábrelos para que aparezcan leídos").
- "no_leido": marcarlos como no leídos.
- "destacar": ponerles estrella / marcarlos como importantes. "quitar_destacado": quitarles la estrella.
- "archivar": archivarlos (quitarlos de la bandeja sin borrarlos).
- "papelera": borrarlos, eliminarlos, botarlos, quitarlos, mandarlos a la papelera.
- "spam": mandarlos a spam / marcarlos como spam.
- "entrada": moverlos a la bandeja de entrada: sacarlos de spam, "no es spam", recuperarlos o restaurarlos de la
  papelera, desarchivarlos.
- "imposible": algo que no se puede: borrar para siempre, vaciar la papelera o el spam, enviar o responder correos.
- "ninguna": no habla del correo (apps, ventanas, juegos, charla, la hora) o niega ("no borres nada").
carpeta: dónde están AHORA esos correos: "entrada", "spam", "papelera", "destacados", "enviados", "todos"
(archivados o en cualquier lado), SOLO si la frase la nombra; si no la nombra, "" (no la adivines).
quienes: remitentes o temas que nombra para elegir correos, tal como los dijo ("Zoom", "la U", "el profe de
cálculo", "la beca"); [] si no nombra ninguno ("bórralos" = los de los que venían hablando). Si viene una orden
reescrita y las "Palabras exactas de {usuario}" nombran otro remitente, manda el de las palabras exactas.
asunto: palabras que {usuario} dice que trae el ASUNTO o el tema del correo, sin artículos ("el que dice matrícula",
"con asunto gira de campo", "el de la beca", "sobre el examen de cálculo", "que habla de la huelga") -> ["matrícula"];
[] si no dice ninguno. quienes es solo QUIÉN lo manda (persona, empresa, la U); si no sabe si es remitente o tema,
ponlo en quienes (ahí se busca en los dos). Si dice "el de X", "los de X" o "el correo de X", X va en quienes
o en asunto: nunca dejes los dos vacíos ("pon estrella al correo de la beca" -> asunto ["beca"]).
todos: true si dice todos / todas / toda la carpeta. solo_sin_leer: true si habla solo de los no leídos.
Ejemplos:
"revisa spam un momento" -> {"acciones":["ver"],"carpeta":"spam","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"¿cuántos no leídos tengo?" -> {"acciones":["ver"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":true}
"¿me escribió el profe de cálculo?" -> {"acciones":["ver"],"carpeta":"","quienes":["profe de cálculo"],"asunto":[],"todos":false,"solo_sin_leer":false}
"sácalos de spam y márcalos como leídos" -> {"acciones":["entrada","leido"],"carpeta":"spam","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"sácalos de spam" -> {"acciones":["entrada"],"carpeta":"spam","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"el de vida estudiantil no es spam" -> {"acciones":["entrada"],"carpeta":"spam","quienes":["vida estudiantil"],"asunto":[],"todos":false,"solo_sin_leer":false}
"recupera el de Zoom de la papelera" -> {"acciones":["entrada"],"carpeta":"papelera","quienes":["Zoom"],"asunto":[],"todos":false,"solo_sin_leer":false}
"quita el de digital ocean" -> {"acciones":["papelera"],"carpeta":"","quienes":["digital ocean"],"asunto":[],"todos":false,"solo_sin_leer":false}
"dime más de la rectoría" -> {"acciones":["leer"],"carpeta":"","quienes":["rectoría"],"asunto":[],"todos":false,"solo_sin_leer":false}
"revisa el correo de la gaceta universitaria" (UN correo, en singular: es leerlo) -> {"acciones":["leer"],"carpeta":"","quienes":["gaceta universitaria"],"asunto":[],"todos":false,"solo_sin_leer":false}
"lee los correos de comunicados uni" / "qué dicen los de la U" (leer o qué dicen, aunque sea en plural) -> {"acciones":["leer"],"carpeta":"","quienes":["comunicados uni"],"asunto":[],"todos":false,"solo_sin_leer":false}
"revisa los correos de la gaceta" (revisar varios, en plural: la lista) -> {"acciones":["ver"],"carpeta":"","quienes":["gaceta"],"asunto":[],"todos":false,"solo_sin_leer":false}
"dime si hay correos de la gaceta sin leer" -> {"acciones":["ver"],"carpeta":"","quienes":["gaceta"],"asunto":[],"todos":false,"solo_sin_leer":true}
"revisa el último correo de la Universidad Nacional" -> {"acciones":["leer"],"carpeta":"","quienes":["Universidad Nacional"],"asunto":[],"todos":false,"solo_sin_leer":false}
"¿qué dice ese?" -> {"acciones":["leer"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"ábrelos para que aparezcan leídos" -> {"acciones":["leido"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"marca todos los que no he leído como leídos" -> {"acciones":["leido"],"carpeta":"","quienes":[],"asunto":[],"todos":true,"solo_sin_leer":true}
"márcame todos los de la U como leídos" -> {"acciones":["leido"],"carpeta":"","quienes":["la U"],"asunto":[],"todos":true,"solo_sin_leer":false}
"bota todo lo de spam" -> {"acciones":["papelera"],"carpeta":"spam","quienes":[],"asunto":[],"todos":true,"solo_sin_leer":false}
"vacía la papelera" -> {"acciones":["imposible"],"carpeta":"papelera","quienes":[],"asunto":[],"todos":true,"solo_sin_leer":false}
"respóndele que sí" -> {"acciones":["imposible"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"ponle estrella al de la beca" -> {"acciones":["destacar"],"carpeta":"","quienes":[],"asunto":["beca"],"todos":false,"solo_sin_leer":false}
"archiva los de Google" -> {"acciones":["archivar"],"carpeta":"entrada","quienes":["Google"],"asunto":[],"todos":false,"solo_sin_leer":false}
"q dicen los de comunicados uni?" -> {"acciones":["leer"],"carpeta":"","quienes":["comunicados uni"],"asunto":[],"todos":false,"solo_sin_leer":false}
"¿cuántos leíste?" / "¿cuáles borraste?" / "¿qué hiciste?" (pregunta por lo que {asistente} ya hizo) -> {"acciones":["ninguna"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}
"busca el correo que dice matrícula en el asunto" -> {"acciones":["ver"],"carpeta":"","quienes":[],"asunto":["matrícula"],"todos":false,"solo_sin_leer":false}
"léeme el de la gira de campo" -> {"acciones":["leer"],"carpeta":"","quienes":[],"asunto":["gira de campo"],"todos":false,"solo_sin_leer":false}
"¿me llegó algo sobre el examen de cálculo?" -> {"acciones":["ver"],"carpeta":"","quienes":[],"asunto":["examen de cálculo"],"todos":false,"solo_sin_leer":false}
"busca los de la U que digan beca" -> {"acciones":["ver"],"carpeta":"","quienes":["la U"],"asunto":["beca"],"todos":false,"solo_sin_leer":false}
"abre discord" -> {"acciones":["ninguna"],"carpeta":"","quienes":[],"asunto":[],"todos":false,"solo_sin_leer":false}""")
ESQUEMA = {"type": "object", "properties": {
    "acciones": {"type": "array", "items": {"type": "string", "enum": ["ver", "leer", "leido", "no_leido", "destacar", "quitar_destacado", "archivar",
                                          "papelera", "spam", "entrada", "imposible", "ninguna"]}},
    "carpeta": {"type": "string", "enum": ["entrada", "spam", "papelera", "destacados", "enviados", "todos", ""]},
    "quienes": {"type": "array", "items": {"type": "string"}}, "asunto": {"type": "array", "items": {"type": "string"}},
    "todos": {"type": "boolean"}, "solo_sin_leer": {"type": "boolean"}},
    "required": ["acciones", "carpeta", "quienes", "asunto", "todos", "solo_sin_leer"]}
# lo último del correo: de qué carpeta se habló, qué correos se nombraron (uid, descripción) y la acción que
# espera el "sí" del usuario (vence a los 2 minutos)
_correo = {"t": 0.0, "carpeta": "entrada", "correos": [], "pendiente": None, "hecho": []}
# "revisa el correo de la gaceta": UN correo de alguien es leerlo (el router a veces lo pasa a "los correos" y el
# modelo, con la orden en plural, listaba en vez de leer). "revisa el correo" a secas es la bandeja.
UNO_DE = re.compile(r"\b(revis\w*|mir\w*|abr\w*|ch[eé]c\w*|ve)\s+el\s+(correo|mail|e-?mail|mensaje)\s+(de|del)\b", re.I)
# varios correos ("los de la U", "esos", "todos"): se leen hasta LEER_VARIOS, no solo el primero
PLURAL = re.compile(r"\b(los|las|esos|esas|estos|estas|todos|todas|correos|mensajes)\b", re.I)
LEER_VARIOS = 3
DONDE_CARPETA = {"entrada": "tu bandeja", "spam": "el spam", "papelera": "la papelera", "destacados": "tus destacados",
                 "enviados": "tus enviados", "todos": "todo tu correo"}
EN_CARPETA = {"spam": " en el spam", "papelera": " en la papelera", "destacados": " en destacados",
              "enviados": " en enviados", "todos": ""}
HACIENDO = {"leido": "marcando como leídos", "no_leido": "marcando como no leídos",
                "destacar": "poniéndole estrella a", "quitar_destacado": "quitándole la estrella a",
                "archivar": "archivando", "papelera": "mandando a la papelera", "spam": "mandando a spam",
                "entrada": "pasando a la bandeja de entrada"}
FRASES = Frases({
    "revisar": ["Revisando {donde}.", "Revisando {donde}, un momento.", "Echándole un ojo a {donde}.",
                "Mirando qué hay en {donde}.", "Un segundo, revisando {donde}."],
    "sin_leer": ["Buscando los que no has leído{en}.", "Revisando los que tienes sin leer{en}.",
                 "Mirando qué te falta por leer{en}.", "Un momento, buscando los no leídos{en}.",
                 "Contando los que no has abierto{en}."],
    "buscar_de": ["Buscando los de {x}{en}.", "Buscando correos de {x}{en}.", "Revisando si hay algo de {x}{en}.",
                  "Mirando si te llegó algo de {x}{en}.", "Un momento, buscando lo de {x}{en}."],
    "buscar_asunto": ["Buscando los que dicen {x} en el asunto{en}.", "Buscando correos con {x} en el asunto{en}.",
                      "Revisando qué correos hablan de {x}{en}.", "Un momento, buscando el asunto {x}{en}.",
                      "Mirando qué te llegó sobre {x}{en}."],
    "leer_uno": ["Abriendo el de {x}.", "Leyendo el de {x}.", "Un momento, abriendo el de {x}.",
                 "Viendo qué dice el de {x}.", "Leyendo el de {x}, un segundo."],
    "leer_varios": ["Leyendo los de {x}.", "Abriendo los de {x}.", "Viendo qué dicen los de {x}.",
                    "Un momento, leyendo los de {x}.", "Abriendo los de {x}, un segundo."],
    "leer_ese": ["Abriéndolo.", "Leyéndolo.", "Viendo qué dice.", "Un momento, abriéndolo.", "Leyéndolo, un segundo."],
    "leer_esos": ["Abriéndolos.", "Leyéndolos.", "Viendo qué dicen.", "Un momento, leyéndolos.",
                  "Abriéndolos, un segundo."],
    "borrar": ["Buscando {c} para mandarlos a la papelera.", "Juntando {c} para la papelera.",
               "Ubicando {c} para borrarlos.", "Un momento, buscando {c} para borrarlos.",
               "Buscando {c} para la papelera, un segundo."],
    "marcar": ["{h} {c}.", "Va, {h} {c}.", "Dale, {h} {c}.", "Un momento, {h} {c}.", "{h} {c}, un segundo."],
})


def _lista_correos(correos: list[tuple[bytes, str]], maximo: int = 10) -> str:
    lineas = [f"- {d}" for _, d in correos[:maximo]]
    if len(correos) > maximo:
        lineas.append(f"- ...y {len(correos) - maximo} más")
    return "\n".join(lineas)


MUEVEN = ("papelera", "spam", "entrada", "archivar")


def _gestionar(intencion: dict) -> str:
    """Hace (o deja pendiente de confirmar) lo que el usuario pidió con el correo y devuelve el contexto para la asistente."""
    # varias a la vez ("sácalos de spam y márcalos leídos"): primero las marcas, al final el movimiento
    acciones = sorted(dict.fromkeys(a for a in intencion["acciones"] if a != "ninguna"), key=lambda a: a in MUEVEN)
    if "imposible" in acciones:
        return (nombres("{usuario} pidió algo que no puedes hacer con el correo (solo puedes leer, marcar leído/no leído, poner "
                "estrella, archivar y mover entre bandeja, spam y papelera; no borrar para siempre, vaciar, enviar ni "
                "responder). Díselo en una frase; no se cambió nada."))
    if [a for a in acciones if a in MUEVEN][1:]:
        return nombres("{usuario} pidió mover los mismos correos a dos lugares a la vez: pregúntale a cuál. No se cambió nada.")
    quienes = [ALIAS_REMITENTE.get(q.strip().lower(), q.strip()) for q in intencion["quienes"] if q.strip()]
    asuntos = [a.strip() for a in intencion.get("asunto", []) if a.strip()]
    if "leer" in acciones:
        return _leer(intencion, quienes, asuntos)
    acciones = [a for a in acciones if a != "ver"]
    nombrados = quienes + [f"«{a}» en el asunto" for a in asuntos]  # para contárselo a la asistente
    anterior = _correo["carpeta"]
    # "pásalos", "archívalos" (sin decir cuáles): los de los que venían hablando, estén donde estén;
    # si no, la carpeta que dijo o, si no dijo ninguna, la bandeja de entrada
    pronombre = acciones and not nombrados and not intencion["todos"]
    carpeta = anterior if pronombre else intencion["carpeta"] or "entrada"
    nombre = google.NOMBRE_CARPETA.get(carpeta, carpeta)
    _correo.update(t=time.time(), carpeta=carpeta, pendiente=None)
    if not acciones:
        if nombrados:
            # buscar por nombre sin carpeta = en la bandeja (en "todos" Gmail tarda demasiado)
            donde = intencion["carpeta"] or "entrada"
            encontrados = google.buscar(donde, quienes, intencion["solo_sin_leer"], maximo=500, asuntos=asuntos)
            _correo.update(carpeta=donde, correos=encontrados[:10])
            # un dominio ("universidad.edu") es remitente; si no, Gmail busca en todo (un correo de Google
            # que menciona la dirección del usuario también contiene "universidad.edu")
            consulta = " ".join(filter(None, [
                f"({' OR '.join(f'from:{q}' if '.' in q else q for q in quienes)})" if quienes else "",
                " ".join(f"subject:({a})" for a in asuntos), "is:unread" if intencion["solo_sin_leer"] else ""]))
            datos = google.buscar_correos(consulta, 5, donde, cuerpo=300)
            # la lista trae como mucho 5: sin el número real, la asistente decía "tienes 5" siempre
            alcance = "en" if asuntos else "entre los últimos 150 de"
            datos = (f"Son {len(encontrados)}{' sin leer' if intencion['solo_sin_leer'] else ''} {alcance} {nombre} "
                     f"(abajo solo los más recientes):\n" + (datos if "No hay correos" not in datos
                                                              else _lista_correos(encontrados, 5))) \
                if encontrados else f"No hay ninguno de {y(nombrados)} en {nombre}."
        else:
            _correo["correos"] = google.buscar(carpeta, None, intencion["solo_sin_leer"], revisar=8, maximo=8)
            datos = google.resumen_correo(carpeta)
        _anotar_hecho(f"revisaste la lista de {nombre}" + (f" (los de {y(nombrados)})" if nombrados else "")
                      + ": solo viste remitentes y asuntos, no abriste ninguno")
        return (nombres(f"Correos de {USUARIO} ({nombre}):\n{datos}\nYa los revisaste: cuéntale directamente lo importante "
                "(cuántos, de quién y de qué tratan, en dos o tres frases). Son correos de {usuario}: dile \"tienes\", nunca "
                "\"tengo\". No le preguntes cuáles quiere ver."))
    # marcar como leídos "todos" = los que no lo están (los demás ya lo están)
    sin_leer = intencion["solo_sin_leer"] or acciones == ["leido"]
    if nombrados:
        correos = google.buscar(carpeta, quienes, sin_leer, asuntos=asuntos)
        if not correos and not intencion["carpeta"] and anterior != carpeta:  # el de spam del que venían hablando
            carpeta, nombre = anterior, google.NOMBRE_CARPETA.get(anterior, anterior)
            _correo["carpeta"] = carpeta
            correos = google.buscar(carpeta, quienes, sin_leer, asuntos=asuntos)
    elif intencion["todos"]:
        correos = google.buscar(carpeta, None, sin_leer, revisar=500, maximo=500)
    else:
        correos = _correo["correos"]  # "bórralos", "ábrelos": los de los que venían hablando
    que = " y ".join(google.ACCIONES[a][1] for a in acciones)
    if not correos:
        return (f"{USUARIO} pidió dejar correos {que}{' (de ' + y(nombrados) + ')' if nombrados else ''} en {nombre}, "
                "pero no encontraste ninguno" + (" sin leer" if sin_leer else "")
                + ("" if nombrados or intencion["todos"] else " (no dijo cuáles y no venían hablando de ninguno)")
                + ". Díselo; no se cambió nada. No cierres ventanas ni uses herramientas por esto.")
    _correo["correos"] = correos
    # sacar correos de donde están se confirma (la papelera siempre, mover más de 3); marcar se hace de una
    if "papelera" in acciones or (any(a in MUEVEN for a in acciones) and len(correos) > 3):
        _correo["pendiente"] = {"t": time.time(), "acciones": acciones, "carpeta": carpeta, "correos": correos}
        return (f"Encontraste {len(correos)} correo(s) en {nombre} para dejar {que} (AÚN NO se hizo nada):\n"
                + _lista_correos(correos) + "\nDile cuántos son y de quién, y pregúntale si lo haces. "
                "No digas que ya está hecho ni cierres ventanas por esto.")
    return (f"Ya está hecho: {_aplicar(acciones, carpeta, correos)}\n{_lista_correos(correos)}\n"
            "Cuéntaselo en pasado, en una frase. No abras ni cierres apps o ventanas por esto.")


def _leer(intencion: dict, quienes: list[str], asuntos: list[str]) -> str:
    """Abre el correo del que habla (el más reciente que coincida, o el primero de los que venían hablando;
    si habla de varios, hasta LEER_VARIOS), se los pasa a la asistente para que cuente lo que dicen y los marca como
    leídos, como al abrirlos en Gmail."""
    nombrados = quienes + [f"«{a}» en el asunto" for a in asuntos]
    carpeta = intencion["carpeta"] or (_correo["carpeta"] if not nombrados else "entrada")
    if nombrados:
        correos = google.buscar(carpeta, quienes, maximo=10, asuntos=asuntos)
        if not correos and not intencion["carpeta"] and _correo["carpeta"] != carpeta:
            carpeta = _correo["carpeta"]
            correos = google.buscar(carpeta, quienes, maximo=10, asuntos=asuntos)
    else:
        correos = _correo["correos"]
    _correo.update(t=time.time(), carpeta=carpeta, pendiente=None)
    if not correos:
        return (f"{USUARIO} quiere que le leas un correo{' de ' + y(nombrados) if nombrados else ''}, pero no "
                "encontraste ninguno" + ("" if nombrados else " (no dijo de quién)") + ". Díselo en una frase.")
    _correo["correos"] = correos
    abiertos = correos[:LEER_VARIOS if intencion.get("varios") else 1]
    largo = 3000 if len(abiertos) == 1 else 1400
    contenidos = [google.leer_correo(carpeta, uid, largo) for uid, _ in abiertos]
    google.aplicar("leido", carpeta, [uid for uid, _ in abiertos])
    _anotar_hecho(f"abriste y leíste {len(abiertos)} correo(s): " + "; ".join(d for _, d in abiertos))
    sin_abrir = correos[len(abiertos):]
    otros = (f"\nHay {len(sin_abrir)} más parecidos que NO abriste (solo sabes el asunto: "
             + "; ".join(d for _, d in sin_abrir[:4]) + ")") if sin_abrir else ""
    if len(abiertos) == 1:
        return (nombres(f"Abriste 1 correo (ya quedó como leído):\n{contenidos[0]}{otros}\n"
                "Cuéntale lo que DICE con los detalles importantes (qué pasa, fechas, horas, lugares, qué tiene que "
                "hacer {usuario}), en 3 a 5 frases, como se lo contarías tú. No leas enlaces ni firmas. Si dices cuántos "
                "leíste, es 1. Los hechos salen SOLO de este texto (si está en inglés, tradúcelo): nada de correos anteriores, de tus notas ni inventado; puedes comentarlo con tu estilo, pero sin agregarle cosas que no dice."))
    return (f"Abriste {len(abiertos)} correos (ya quedaron como leídos):\n\n" + "\n\n---\n\n".join(contenidos)
            + f"{otros}\nCuéntale de qué trata cada uno, una o dos frases por correo, con lo importante (fechas, "
              f"qué tiene que hacer {USUARIO}). No leas enlaces ni firmas. Leíste exactamente {len(abiertos)}. Los hechos salen SOLO de este texto (si está en inglés, tradúcelo): nada de correos anteriores, de tus notas ni inventado; puedes comentarlo con tu estilo, pero sin agregarle cosas que no dice.")


def _anotar_hecho(que: str) -> None:
    """Lo que la asistente hizo de verdad con el correo, para contestar "¿cuántos leíste?" sin inventar."""
    _correo["hecho"] = [(t, h) for t, h in _correo["hecho"] if time.time() - t < 900][-4:] + [(time.time(), que)]


def _aplicar(acciones: list[str], carpeta: str, correos: list[tuple[bytes, str]]) -> str:
    hechos = [google.aplicar(a, carpeta, [u for u, _ in correos]) for a in acciones]
    _anotar_hecho(" ".join(hechos) + " (" + "; ".join(d for _, d in correos[:6]) + ")")
    if any(a in MUEVEN for a in acciones):
        _correo["correos"] = []  # ya no están en esa carpeta
    return " ".join(hechos)


def _confirmar(si: bool) -> str:
    pend, _correo["pendiente"] = _correo["pendiente"], None
    if not si:
        return nombres("{usuario} dijo que no: no se cambió ningún correo. Confírmaselo en una frase.")
    return (f"{USUARIO} confirmó y ya está hecho: {_aplicar(pend['acciones'], pend['carpeta'], pend['correos'])} "
            "Díselo en pasado, en una frase (todo se puede deshacer en Gmail).")


def aviso(intencion: dict) -> str:
    acciones = [a for a in intencion["acciones"] if a not in ("ninguna", "imposible", "resumen")]
    if not acciones or "imposible" in intencion["acciones"]:
        return ""
    asuntos = [a.strip() for a in intencion.get("asunto", []) if a.strip()]
    solo_asunto = asuntos and not [q for q in intencion["quienes"] if q.strip()]
    quienes = y([q.strip() for q in intencion["quienes"] if q.strip()] + asuntos)
    carpeta, varios = intencion["carpeta"], intencion.get("varios")
    en = EN_CARPETA.get(carpeta, "")
    if "leer" in acciones:
        if quienes:
            return FRASES.decir("leer_varios" if varios else "leer_uno", x=quienes)
        return FRASES.decir("leer_esos" if varios else "leer_ese")
    hacer = [HACIENDO[a] for a in acciones if a in HACIENDO]
    if not hacer:  # solo "ver"
        if quienes:
            return FRASES.decir("buscar_asunto" if solo_asunto else "buscar_de", x=quienes, en=en)
        if intencion["solo_sin_leer"]:
            return FRASES.decir("sin_leer", en=en)
        return FRASES.decir("revisar", donde=DONDE_CARPETA.get(carpeta or "entrada", "tu bandeja"))
    cuales = (f"los de {quienes}" if quienes else
              "todos los" + (en or " de la bandeja") if intencion["todos"] else "esos")
    if "papelera" in acciones:
        return FRASES.decir("borrar", c=cuales)
    return FRASES.decir("marcar", h=y(hacer), c=cuales)  # "{h}" al inicio: _decir pone la mayúscula




LISTAS = re.compile(r"\blistas?\b|\bart[ií]culos?\b", re.I)


def regla(texto: str, orden: str, temas: list[str]) -> bool | None:
    """"Lee mis listas", "elimina ese artículo" no son del correo si no lo nombra: el router los mandaba aquí y
    "elimina ese artículo" quedaba en mandar correos a la papelera (prueba de fuego)."""
    if "correo" in temas and LISTAS.search(texto) and not TEMA.search(texto):
        return False
    return None


def detectar(texto: str) -> bool:
    """Respaldo sin router: nombra el correo, o se venía hablando de él (3 minutos)."""
    return bool(TEMA.search(texto)) or time.time() - _correo["t"] < 180


def entender(pedido: Pedido, modelo) -> dict | None:
    """Qué quiere hacer con el correo (ver INTERPRETAR); None si no pide nada. Si el modelo no responde, al menos
    el resumen de la bandeja."""
    i = modelo(INTERPRETAR, pedido.combinado, ESQUEMA)
    if i is None:
        return {"acciones": ["resumen"]}
    i["varios"] = bool(PLURAL.search(pedido.texto))  # "los de la U": se leen varios, no solo el primero
    if i["acciones"] == ["ver"] and (i["quienes"] or i["asunto"]) and UNO_DE.search(pedido.texto):
        i["acciones"] = ["leer"]
    return i if set(i["acciones"]) - {"ninguna"} else None


def ejecutar(intencion: dict, pedido: Pedido) -> Resultado:
    previo = _lo_hecho()  # antes de hacer lo nuevo: lo que ya había hecho
    if intencion["acciones"] == ["resumen"]:
        _correo["t"] = time.time()
        hecho = (nombres("Correos de {usuario} (bandeja de entrada):\n") + google.resumen_correo()
                 + "\nCuéntale lo importante en dos o tres frases.")
    else:
        hecho = _gestionar(intencion)
    return Resultado("\n\n".join(filter(None, [previo, hecho])), preguntar=bool(_correo["pendiente"]))


def pendiente(texto: str) -> Resultado | None:
    """La respuesta a "¿los mando a la papelera?" ("sí" / "no"), si se preguntó hace menos de 2 minutos."""
    pend = _correo["pendiente"]
    if not (pend and time.time() - pend["t"] < 120 and len(texto.split()) <= 4
            and (SI.search(texto) or NO.search(texto))):
        return None
    return Resultado(_confirmar(bool(SI.search(texto))))


def datos(pedido: Pedido) -> str | None:
    """"¿cuántos leíste?", "¿cuáles borraste?": con lo que pasó de verdad, no con lo que suena bien."""
    return _lo_hecho() if "correo" in pedido.temas else None


def _lo_hecho() -> str:
    if not _correo["hecho"]:
        return ""
    return ("Lo que de verdad hiciste con su correo antes de este mensaje (si pregunta qué hiciste o cuántos leíste, "
            "responde SOLO con esto):\n" + "\n".join(f"- {h}" for _, h in _correo["hecho"]))
