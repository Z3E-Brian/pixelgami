"""La asistente: entender cada mensaje y preparar lo que necesita para responder.

Un modelo local chico (Qwen3 8B) decide mal cuándo usar una herramienta, así que lo que se puede saber o hacer de
antemano se resuelve aquí, antes de que responda:
- el router (_router) reescribe el mensaje con la conversación ("sí" -> lo que ella ofreció) y elige sus temas;
- cada tema es una función de funciones/ (ventanas, correo, música, internet, recordatorios...): el router se arma
  con su funcion.yaml y preparar() le pasa lo suyo (ver funciones/__init__.py). Aquí no hay nada de ninguna;
- la conversación: la fecha si hace falta, las notas de memoria parecidas (embeddings, umbral calibrado: lo relevante
  puntúa ~0,55-0,70 y la charla casual ~0,15-0,35), "acuérdate de que..." (se guarda), sus hábitos para proponer,
  y lo que aprendió sola (asistente_diario.py);
- cómo habla: filtros de cada frase de la respuesta (coletillas, ofertas de relleno, un solo saludo, la cara por la
  frase, frases repetidas, datos inventados) que usa transformers.py.
"""
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

from loguru import logger

from . import asistente_diario

# la carpeta del proyecto (agent -> open_llm_vtuber -> src -> Open-LLM-VTuber -> proyecto)
BASE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BASE))
from identidad import ASISTENTE, MODELO_LOCAL, PERFIL, USUARIO, nombres  # noqa: E402
import funciones  # noqa: E402
from funciones import Frases, Pedido, Resultado  # noqa: E402

# lo que sabe hacer, cada cosa en su carpeta de funciones/ (perfil.yaml -> funciones; si no está, todas)
FUNCIONES = funciones.cargar(PERFIL.get("funciones"))

UMBRAL_MEMORIA = 0.45
MAX_NOTAS = 2
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

RECORDAR = re.compile(r"\b(acu[eé]rdate|recuerda|no (te )?olvides|anota|apunta)( de)?( que)?\s+(?P<dato>.{6,})", re.I)
PLANES = re.compile(r"\b(voy a|vamos a|quiero|abr[ea]|abramos|pon|ponme|trabajar|jugar)\b", re.I)
_memoria = funciones.mcp("memoria")
_memoria.TIMEOUT_EMB = 8  # si Ollama tarda, responder sin notas antes que quedarse callada
_habitos = funciones.mcp("acciones")  # consultar_habitos: para proponer según lo que suele hacer


# Muletillas de cierre que Qwen agrega aunque la personalidad se lo prohíba
COLETILLA = re.compile(
    r"\s*(\[[a-z_]+\]\s*)*¿\s*(necesitas|quieres|hay|deseas|puedo|te ayudo|te puedo ayudar)[^?¿]{0,60}"
    r"(algo m[aá]s|otra cosa|en algo m[aá]s|ayudarte con algo|con algo m[aá]s)[^?¿]{0,30}\?[\s.…!]*(\[[a-z_]+\]\s*)*$"
    r"|\s*(\[[a-z_]+\]\s*)*¿\s*algo m[aá]s[^?¿]{0,20}\?[\s.…!]*(\[[a-z_]+\]\s*)*$"
    r"|\s*(\[[a-z_]+\]\s*)*¿\s*(est[aá] bien|te parece( bien)?|de acuerdo|ok|vale|lo hago|procedo)[^?¿]{0,20}\?[\s.…!]*(\[[a-z_]+\]\s*)*$", re.I)


def sin_coletilla(texto: str) -> str:
    """Quita un "¿Necesitas algo más?" (y parecidos) del final del texto, y las ofertas de relleno (para que en el
    historial no aprenda a repetirlas)."""
    if not texto:
        return texto
    texto = COLETILLA.sub("", texto).rstrip()
    if not _turno["preguntar"]:
        frases = re.split(r"(?<=[.!?…])\s+", texto)
        quedan = [f for f in frases if not OFERTA.match(f)]
        texto = " ".join(quedan) if quedan else texto
    return texto


# La asistente cerraba 77 de 274 respuestas con "¿quieres que...?" aunque ya lo hubiera hecho: el usuario lo siente como que no
# lo ayuda. Esas frases no se dicen (transformers.sentence_divider las salta), salvo que el turno necesite preguntar.
OFERTA = re.compile(r"^\W*(\[[a-z_]+\]\s*)*¿\s*(y\s+)?(quieres|te gustar[ií]a|deseas|prefieres|te parece|necesitas|"
                    r"hay algo|algo m[aá]s|en qu[eé] m[aá]s|te ayudo|te cuento|te pongo|te abro|te busco|lo abro|"
                    r"lo busco|te lo|le pongo|ponemos|buscamos|seguimos)[^?]*\?[\s.…!~]*(\[[a-z_]+\]\s*)*$", re.I)
# este mensaje: preguntar = la respuesta necesita una pregunta (confirmar un borrado, proponer por hábitos); aviso = lo
# que ya dijo mientras trabajaba; revisores = los de las funciones para los datos inventados (ver revisar_frase)
_turno = {"preguntar": False, "aviso": "", "revisores": []}


SALUDO_AL_INICIO = re.compile(r"^[\s¡!]*(?:hol[ia]+s?|holis|buen[oa]s(?: d[ií]as| tardes| noches)?|hey|holaa+)\b", re.I)


def sin_saludo(frase: str) -> str:
    """La frase sin el saludo del principio ("¡Holi, el usuario! Tienes 4..." -> "Tienes 4..."); vacía si era solo eso.
    Para que la asistente salude una sola vez por respuesta: el aviso ya trae el saludo y Qwen saluda otra vez."""
    m = SALUDO_AL_INICIO.match(frase)
    if not m:
        return frase
    resto = re.sub(nombres(r"^(\s+de nuevo)?(\s*,?\s*{usuario_re}\b)?[\s!¡.,~]*"), "", frase[m.end():], flags=re.I)
    return resto[:1].upper() + resto[1:]


TIERNAS = {"shy", "embarrassed", "joy", "happy", "love", "excited", "sad", "sadness", "worried"}


def emoji_acorde(frase: str, emocion: str) -> str:
    """Qwen pone 😏 a todo (hasta a un "me alegra que te gustara"), y al usuario le suena picante. Se cambia según
    la emoción de la frase: tierna -> ☺️, jugando o tras un chiste -> 😜."""
    return frase.replace("😏", "☺️" if emocion in TIERNAS else "😜")


# Qwen 8B abre casi todo con [neutral] aunque la frase diga otra cosa: el emoji o el tono de la frase eligen la
# cara (primero lo más específico). Solo se usa cuando la etiqueta fue [neutral]; ver transformers.actions_extractor.
CARA_POR_EMOJI = [("🥰", "love"), ("☺️", "shy"), ("😳", "embarrassed"), ("😜", "playful"), ("😌", "smirk"),
                  ("😢", "sad"), ("😭", "sad"), ("😮", "surprise"), ("😲", "surprise"), ("🤔", "thinking"),
                  ("😊", "happy"), ("😄", "happy"), ("😁", "happy")]
CARA_POR_TEXTO = [
    (re.compile(r"\b(ay,? no|lo siento|qu[eé] pena|qu[eé] mal|l[aá]stima|no me sali[oó])\b", re.I), "sad"),
    (re.compile(r"\b(perd[oó]n|disculpa|me equivoqu[eé])\b", re.I), "embarrassed"),
    (re.compile(r"\b(je(je)+|ja(ja)+|ji(ji)+)\b", re.I), "joy"),
    (re.compile(r"¿en serio\?|\b(wow|guau|uy|vaya|no puedo creer)\b", re.I), "surprise"),
    (re.compile(r"\b(hmm+|mmm+|d[eé]jame ver|a ver)\b", re.I), "thinking"),
    (re.compile(r"!"), "happy"),
]


def sin_lamento(frase: str, emocion: str) -> str:
    """Sin el "¡Ay!" o "¡Ah!" con que Qwen abre a veces una respuesta normal ("¡Ay! La RTX 5060 está en..."): en la
    persona "Ay" va con pena o vergüenza ([sad] "Ay, no...", [shy] "Ay, ya..."), y con [neutral] sobra."""
    if emocion not in ("", "neutral"):
        return frase
    limpia = re.sub(r"^(\s*(?:\[[a-z_]+\]\s*)?)¡\s*(?:ay+|ah+)\s*!\s*", r"\1", frase, flags=re.I)
    return limpia if limpia.strip(" []abcdefghijklmnopqrstuvwxyz_") else frase


def cara_por_frase(frase: str, disponibles) -> str:
    """La emoción que muestra la frase ("¡Ay, no! 😢" -> "sad"), entre las que tiene el modelo; "" si no se nota."""
    for emoji, cara in CARA_POR_EMOJI:
        if emoji in frase and cara in disponibles:
            return cara
    for patron, cara in CARA_POR_TEXTO:
        if patron.search(frase) and cara in disponibles:
            return cara
    return ""


def _normal(frase: str) -> str:
    return re.sub(r"[^a-záéíóúñü ]", "", re.sub(r"\[[a-z]+\]", "", frase.lower())).strip()


def repetida(frase: str) -> bool:
    """Una frase igual a otra de su respuesta anterior (Qwen 8B a veces copia su respuesta entera cuando el
    mensaje del usuario es corto y parecido al anterior: "se pegó"). Las cortas ("¡Listo!") y los avisos sí se repiten."""
    actual = _normal(frase)
    if len(actual) < 15 or frase.strip() in _turno.get("aviso", ""):
        return False
    anteriores = re.split(r"(?<=[.!?…])\s*|(?=\[[a-z]+\])", asistente_diario._ultima_respuesta)
    return any(_normal(f) == actual for f in anteriores)


def oferta_sobrante(frase: str) -> bool:
    return not _turno["preguntar"] and bool(OFERTA.match(frase.strip()))


def _notas_parecidas(texto: str) -> list[str]:
    trozos = _memoria._trozos()
    orden = _memoria._por_significado(texto, trozos)
    if orden is None:  # Ollama apagado (modo juego): sin memoria automática
        return []
    cache = json.loads(_memoria.CACHE.read_text())
    consulta = _memoria._embeber([texto])
    if not consulta:
        return []
    notas, elegidas = _memoria._notas(), []
    for i in orden:
        nombre, t = trozos[i]
        puntaje = _memoria._coseno(consulta[0], cache[hashlib.sha1(t.encode()).hexdigest()])
        if puntaje < UMBRAL_MEMORIA or len(elegidas) >= MAX_NOTAS:
            break
        if nombre not in elegidas and nombre != "vision_usuario":  # la visión ya va siempre (asistente_diario)
            elegidas.append(nombre)
    return [f"[{n}] {notas[n][0]}\n{notas[n][1][:3000]}" for n in elegidas]


# si el usuario saluda ("holi, revisa..."), el saludo va antes del aviso; si no, Qwen saludaba después de él
SALUDO = re.compile(nombres(r"^\W*(?:{asistente_re}\W+)?(hol[ia]\w*|buen[oa]s(?: d[ií]as| tardes| noches)?|hey|qu[eé] tal|qu[eé] onda|"
                    r"pura vida|saludos)\b"), re.I)
SALUDOS = Frases({"saludo": ["¡Holi!", nombres("¡Hola, {usuario}!"), "¡Hola!", "¡Hey, hola!", "¡Buenas!"]})


def _saludo(texto: str) -> str:
    m = SALUDO.search(texto)
    if not m:
        return ""
    dijo = m.group(1).lower()
    if dijo.startswith("buen") and " " in dijo:  # "buenos días" se devuelve igual
        return f"¡{dijo[0].upper()}{dijo[1:]}!"
    return SALUDOS.decir("saludo")


def aviso_de(texto: str, avisos: list[str]) -> str:
    """Lo que la asistente dice ANTES de ponerse a hacerlo ("Revisando el spam."), para que el usuario oiga al
    momento qué entendió y no espere en silencio: los avisos de las funciones, con su saludo si él saludó."""
    aviso = " ".join(a for a in avisos if a)
    return f"{_saludo(texto)} {aviso}".strip() if aviso else ""


def revisar_frase(frase: str) -> str | None:
    """Si la frase inventa algo que las funciones de este turno saben que es falso (un precio que no salió en la
    búsqueda), lo que se dice en su lugar; None si está bien. Lo usa transformers.sentence_divider."""
    for revisar in _turno["revisores"]:
        en_lugar = revisar(frase)
        if en_lugar:
            return en_lugar
    return None


def respuesta_entregada() -> None:
    """La llama la conversación cuando la asistente empieza a responder."""
    for f in FUNCIONES:
        f.respondio()


def _qwen_json(sistema: str, texto: str, esquema: dict) -> dict | None:
    """Salida estructurada de Qwen; None si Ollama no responde."""
    import urllib.request
    try:
        cuerpo = {"model": MODELO_LOCAL, "stream": False, "think": False, "keep_alive": "30m", "format": esquema,
                  "options": {"temperature": 0}, "messages": [{"role": "system", "content": sistema},
                                                              {"role": "user", "content": texto}]}
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(cuerpo).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(json.load(r)["message"]["content"])
    except Exception as e:
        logger.warning(f"{ASISTENTE} interpretar: {e}")
        return None


# Router: UNA decisión por mensaje, con el contexto de la conversación. Reescribe lo que dijo el usuario como orden
# completa ("sí" tras "¿lo busco en Reddit?" -> "busca en Reddit opiniones de la RAM de 8 GB") y dice a qué temas
# va. Reemplaza a los detectores por palabras clave de cada tema, que fallaban con cada forma nueva de decirlo.
ROUTER_BASE = """Eres el enrutador de {asistente}, {la_asistente} de escritorio de {usuario} (su PC con Linux). Recibes el último
mensaje de {usuario} (le habla por voz; Whisper puede escribir mal alguna palabra) y el contexto de la conversación.

orden: lo que {usuario} quiere, reescrito como una petición COMPLETA que se entienda sola, en español y dirigida a
{asistente} ("busca...", "abre...", "pon...", "dime..."). Resuelve con el contexto los pronombres y referencias
("búscalo", "eso", "ahí", "el primero", "también en Reddit", "y en Japón?"). Si {usuario} acepta algo que {asistente} le
ofreció en su último mensaje ("sí", "dale", "ok", "hazlo", "va"), orden = eso que {asistente} ofreció, como orden
explícita; si ofreció varias cosas y no dice cuál, la primera. Si lo rechaza, orden = "nada, gracias". Si es
charla, orden = su mensaje tal cual. Usa el contexto SOLO si el mensaje se refiere a
él; un tema nuevo ("ponme el trailer de Silksong" después de buscar RAM) va solo, sin mezclar lo anterior. No
inventes datos que no estén en el contexto, no cambies lo que pidió y no quites ningún detalle (remitentes como "los de la U", nombres, lugares, cantidades, "tú").

necesita_contexto: true solo si el mensaje NO se entiende solo y hubo que usar el contexto para la orden ("sí",
"dale", "ábrelo", "el primero", "¿y en Japón?", "búscalo en Reddit", "ciérralo"); false si ya está completo.

Cómo habla {usuario} (sacado de cientos de mensajes suyos):
- Pide las cosas como pregunta o deseo: "¿puedes abrir Steam?", "¿puedes revisar mi correo?", "quiero...",
  "ocupo...", "quisiera...". Siempre es una ORDEN para hacer ya, no una pregunta de sí o no.
- Escribe abreviado y en tico: q = que, xq = porque, pliz, mae, "un toque/un momento/ahorita" (no cambian nada).
- Corrige sobre la marcha: "no no, mala mía, ...", "digo los correos", "no literal, pero sí", "hazlo y ya": lo que
  dice después de la corrección reemplaza a lo anterior.
- Le dice a {asistente} que se equivocó con algo que hizo o leyó ("eso no decía", "creo q el correo era otro", "no era
  ese", "te lo inventaste"), aunque se ría o {la} felicite: la orden es volver a hacerlo bien, del mismo tema.
- Deja la elección a {asistente}: "pon cualquier canción", "la que quieras", "alguna de X": es una orden, {asistente} elige.
- Whisper le cambia palabras: "Sierra"/"cierra lo" = cierra; "Guatzi"/"whatsie" = WhatsApp; "escritorio de
  archivos" = explorador de archivos; "STIM"/"stim" = Steam; "pongo música" = pon música; "pestaña N" o
  "workspace N" = escritorio N (una pestaña del navegador solo si dice {navegador} o navegador).
- Comentar o charlar sobre un tema ("la RAM depende de si es de laptop...", "el modelo está lento") es "charla":
  solo es una acción si pide HACER o SABER algo concreto.

temas (uno o varios):
{temas_funciones}
- "charla": conversación, saludos, preguntas generales, cosas de {asistente} o de {él}.

Ejemplos:
{ejemplos}"""

# lo que NO es de ninguna función
EJEMPLOS_CHARLA = """{asistente}: "¿Quieres que ponga música?" / {usuario}: "no gracias" -> orden "nada, gracias", temas ["charla"]
{usuario}: "hola asistente, cómo estás" -> temas ["charla"]
{usuario}: "pero es que la RAM depende, la de laptop es diferente" -> temas ["charla"]
{usuario}: "usa gigas" (sin contexto) / "habla más cortito" -> temas ["charla"]"""


def _uno_por_uno(ejemplos: str) -> list[str]:
    """Los ejemplos de un texto, cada uno con sus líneas de continuación (las que empiezan con espacio)."""
    lista = []
    for linea in ejemplos.splitlines():
        if linea.startswith(" ") and lista:
            lista[-1] += "\n" + linea
        elif linea.strip():
            lista.append(linea)
    return lista


def _mezclar(grupos: list[list[str]]) -> list[str]:
    """Por rondas: el primero de cada grupo, luego el segundo... Con todos los ejemplos de un tema seguidos, el modelo
    se sesgaba hacia el último bloque ("abre una pestaña con la extreme" quedó como abrir el resultado de una búsqueda)."""
    return [g[i] for i in range(max(map(len, grupos), default=0)) for g in grupos if i < len(g)]


def armar_router(lista: list) -> tuple[str, dict]:
    """El prompt del router y su esquema, con el tema, la descripción y los ejemplos de cada función de `lista`."""
    temas = "".join(f'- "{f.tema}": {f.descripcion}\n' for f in lista)
    ejemplos = _mezclar([_uno_por_uno(EJEMPLOS_CHARLA)] + [_uno_por_uno(f.ejemplos) for f in lista])
    texto = ROUTER_BASE.replace("{temas_funciones}\n", temas).replace("{ejemplos}", "\n".join(ejemplos))
    esquema = {"type": "object", "properties": {
        "orden": {"type": "string"},
        "temas": {"type": "array", "items": {"type": "string", "enum": [f.tema for f in lista] + funciones.RESERVADOS}},
        "necesita_contexto": {"type": "boolean"}},
        "required": ["orden", "temas", "necesita_contexto"]}
    return nombres(texto), esquema


ROUTER, ESQUEMA_ROUTER = armar_router(FUNCIONES)
_conversacion = {"usuario": ""}  # el mensaje anterior del usuario (el de la asistente lo guarda asistente_diario)
# mensajes que dependen de lo anterior (Qwen no siempre lo marca): cortos, "sí/dale", "ciérralo", "eso", "¿y en...?"
REFERENCIA = re.compile(r"^\W*(s[ií]|dale|va|ok|okay|claro|hazlo|de una|ya|sale|listo)\b|\b\w{3,}(lo|la|los|las|le|les)\W*$|"
                        r"\b\w+r(lo|la|los|las)\b|\b(eso|ese|esa|esos|esas|ah[ií]|all[aá]|el primero|la primera|"
                        r"el segundo|la segunda|el tercero|la tercera)\b|^\W*¿?\s*y\s", re.I)  # el mensaje anterior del usuario (el de la asistente lo guarda asistente_diario)


def _corregir_temas(temas: list[str], texto: str, orden: str) -> list[str]:
    """Las reglas fijas de cada función sobre su tema: casos que el router confunde y que no deben depender de su
    prompt ("recuérdame..." siempre es un recordatorio; "abre YouTube y pon música" no es internet)."""
    temas = list(temas)
    for f in FUNCIONES:
        fija = f.regla(texto, orden, temas)
        if fija and f.tema not in temas:
            temas = [t for t in temas if t != "charla"] + [f.tema]
        elif fija is False and f.tema in temas:
            temas = [t for t in temas if t != f.tema] or ["charla"]
    return temas


def _router(texto: str) -> dict | None:
    """{"orden", "temas", "necesita", "combinado"} para este mensaje; None si Ollama no responde (entonces,
    los detectores de cada función)."""
    contexto = []
    if asistente_diario._ultima_respuesta:
        dicho = re.sub(r"\[[a-z]+\]\s*", "", asistente_diario._ultima_respuesta)[:400]
        contexto.append(f"Último mensaje de {ASISTENTE}: «{dicho}»")
    if _conversacion["usuario"]:
        contexto.append(f"Mensaje anterior de {USUARIO}: «{_conversacion['usuario'][:200]}»")
    contexto += [t for f in FUNCIONES if (t := f.para_el_router())]  # "última búsqueda: ..."
    r = _qwen_json(ROUTER, "\n".join(contexto + [f"{USUARIO}: {texto}"]), ESQUEMA_ROUTER)
    if not r or not r.get("temas"):
        return None
    r["orden"] = (r.get("orden") or "").strip() or texto
    r["temas"] = _corregir_temas(r["temas"], texto, r["orden"])
    # reescribir solo lo que lo necesita: un mensaje completo va tal cual (al reescribir se pueden perder detalles)
    # ¿la orden trae palabras de la conversación que él no dijo ahora? Entonces usó el contexto, lo marque Qwen o no
    # (su necesita_contexto cambia con cualquier retoque del prompt: con "q dicen en reddit?" dejó de marcarlo)
    palabras = lambda t: {w for w in re.findall(r"\w+", t.lower()) if len(w) > 2}  # noqa: E731
    del_contexto = (palabras(r["orden"]) - palabras(texto)) & palabras(" ".join(contexto))
    necesita = r.get("necesita_contexto") or len(texto.split()) <= 3 or REFERENCIA.search(texto) or len(del_contexto) >= 2
    r["necesita"] = bool(necesita)
    # para los intérpretes de las funciones: la orden con el contexto Y sus palabras exactas (de ahí salen los detalles;
    # la orden trae además lo que el router corrigió de Whisper: "Sierra" -> "cierra")
    r["combinado"] = texto if r["orden"].lower().strip(" ?¿!.") == texto.lower().strip(" ?¿!.") else \
        f"{r['orden']}\n(Palabras exactas de {USUARIO}: «{texto}»; respeta sus detalles)"
    logger.info(f"{ASISTENTE} router: {r['temas']} «{r['orden']}»")
    return r


def pedido_de(texto: str, ruta: dict | None, ahora: datetime.datetime, temas=()) -> Pedido:
    """Lo que reciben las funciones: sus palabras, la orden del router y las dos juntas (sin router: sus palabras)."""
    if not ruta:
        return Pedido(texto, texto, texto, ahora, temas=frozenset(temas))
    return Pedido(texto, ruta["orden"], ruta["combinado"], ahora, ruta["necesita"], frozenset(temas))


def _temas_por_palabras(texto: str) -> set[str]:
    """Respaldo si el router no responde: los detectores de cada función."""
    return {f.tema for f in FUNCIONES if f.detectar(texto)} or {"charla"}


def entender(pedido: Pedido, temas: set[str]) -> dict:
    """{función: intención} de las funciones de estos temas que piden algo, en el orden de FUNCIONES. Las que ceden
    (cede_a) se preguntan al final y se saltan si una de esas ya pidió algo."""
    intenciones = {}
    for f in sorted((f for f in FUNCIONES if f.tema in temas), key=lambda f: bool(f.cede_a)):
        if any(g.tema in f.cede_a for g in intenciones):
            continue
        try:
            i = f.entender(pedido, _qwen_json)
        except Exception as e:  # una función con problemas no tumba a las demás
            logger.warning(f"{ASISTENTE} {f.nombre} (entender): {e}")
            continue
        if i is not None:
            intenciones[f] = i
    return {f: intenciones[f] for f in FUNCIONES if f in intenciones}


def _ejecutar(intenciones: dict, pedido: Pedido) -> list[Resultado]:
    resultados = []
    for f, intencion in intenciones.items():
        try:
            r = f.ejecutar(intencion, pedido)
        except Exception as e:
            logger.warning(f"{ASISTENTE} {f.nombre}: {e}")
            r = Resultado(f.si_falla(e))
        if r:
            resultados.append(r)
    return resultados


def preparar(texto: str, avisar=None) -> str:
    """Devuelve el bloque de contexto para este mensaje (vacío si no hay texto). avisar(frase), si se da,
    recibe lo que la asistente dice antes de ponerse a hacerlo, en cuanto se sabe qué pidió el usuario."""
    if not texto or not texto.strip():
        return ""
    ahora = datetime.datetime.now()
    partes = []
    temas = {"charla"}
    asistente_diario.actividad()
    _turno.update(preguntar=False, aviso="", revisores=[])
    # la fecha solo si la pregunta va de eso: si no, Qwen la recita en cualquier respuesta
    if re.search(r"\b(hora|fecha|d[ií]a|hoy|mañana|ayer|semana|mes|tarde|noche|temprano)\b", texto, re.I):
        partes.append(f"Ahora es {DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month - 1]} "
                      f"de {ahora.year}, {ahora:%H:%M}.")
    try:
        # la respuesta a algo que una función preguntó ("¿los borro?" -> "sí"; "¿a qué hora?" -> "a las 3"): va antes
        # que todo y no pasa por el router
        respondida = next((r for f in FUNCIONES if (r := f.pendiente(texto))), None)
        ruta = None if respondida else _router(texto)
        _conversacion["usuario"] = texto
        if not respondida:
            temas = set(ruta["temas"]) if ruta else _temas_por_palabras(texto)
        pedido = pedido_de(texto, ruta, ahora, temas)
        intenciones = {} if respondida else entender(pedido, temas)
        aviso = aviso_de(texto, [f.aviso(i) for f, i in intenciones.items()])
        if aviso and avisar:
            _turno["aviso"] = aviso
            avisar(aviso)
            partes.append(f"Mientras lo hacías ya le dijiste: «{aviso}». No lo repitas ni vuelvas a saludar: "
                          "empieza directo con el resultado.")
        resultados = ([respondida] if respondida else []) + _ejecutar(intenciones, pedido)
        partes += [r.contexto for r in resultados]
        _turno["preguntar"] = any(r.preguntar for r in resultados)
        _turno["revisores"] = [r.revisar_frase for r in resultados if r.revisar_frase]
        # lo que una función sabe para responder aunque no se le pidió hacer nada ("¿qué tengo mañana?" -> agenda)
        partes += [d for f in FUNCIONES if f not in intenciones and (d := f.datos(pedido))]
        hizo = any(r.hizo for r in resultados)
        m = RECORDAR.search(texto) if not hizo else None  # "recuérdame mañana..." ya lo hizo una función: no es nota
        if m:
            _memoria.guardar_recuerdo(m.group("dato").strip().rstrip("."))
            partes.append(nombres(f"Ya quedó guardado en tu memoria: {m.group('dato').strip()}. "
                          "Confírmaselo a {usuario} brevemente."))
        if PLANES.search(texto):
            partes.append(nombres("Hábitos de {usuario} relacionados (para proponer, no para seguir fijo):\n")
                          + _habitos.consultar_habitos(texto))
            # proponer según sus hábitos solo vale si no se hizo nada (si ya actuó, no se ofrece más)
            _turno["preguntar"] = _turno["preguntar"] or not hizo
        # con datos de una función (correos, búsquedas), sus notas solo confunden (mezcló "examen de cálculo" con un
        # correo de GitHub y se inventó un proyecto)
        notas = _notas_parecidas(texto) if all(r.con_notas for r in resultados) else []
        if notas:
            partes.append("Notas de tu memoria sobre esto:\n\n" + "\n\n---\n\n".join(notas))
    except Exception as e:  # el contexto nunca debe tumbar la respuesta
        logger.warning(f"{ASISTENTE} contexto automático: {e}")
    # lo que la asistente aprendió sola (asistente_diario.py): va siempre, para que lo aplique sin que se lo repitan
    propio = []
    preferencias = asistente_diario.preferencias()
    if preferencias:
        propio.append(nombres("Lo que aprendiste de cómo le gusta a {usuario} que hagas las cosas (síguelo siempre, sin "
                      "mencionarlo):\n") + "\n".join(f"- {p}" for p in preferencias))
    # en la charla no: son de órdenes (correo, ventanas) y alargan el contexto; con mucho texto antes de un mensaje
    # corto, Qwen 8B perdía el mensaje y repetía su respuesta anterior palabra por palabra
    lecciones = asistente_diario.lecciones(texto) if temas - {"charla"} else []
    if lecciones:
        propio.append(nombres("Lecciones de veces que te equivocaste con {usuario} (aplícalas, sin mencionarlas):\n")
                      + "\n".join(f"- {l}" for l in lecciones))
    vision = asistente_diario.vision()
    if vision:
        propio.append(nombres("Cómo ves tú a {usuario} (tu retrato de {él}, de tu diario; no lo recites):\n") + vision)
    partes = propio + partes
    if not partes:
        return ""
    return ("Contexto para responder (datos reales; úsalos y no inventes nada fuera de esto):\n\n"
            + "\n\n".join(partes)
            + nombres("\n\nResponde como {asistente} a lo que {usuario} te dice AHORA (su mensaje de abajo), con palabras nuevas: nunca "
              "repitas ni parafrasees tu respuesta anterior. Alegre, cercan{a} y con un toque juguetón, breve (una o dos frases, salvo que arriba se te pida contar más). No recites "
              "estos datos ni la fecha si no te los preguntó; usa solo lo que haga falta. No termines ofreciendo "
              "más cosas (\"¿quieres que...?\") salvo que de verdad falte algo para hacer lo que pidió."))
