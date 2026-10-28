"""La asistente: su propia memoria y su diario.

- Después de cada respuesta, Qwen revisa (en segundo plano, con Ollama ya libre) si el usuario dejó ver algo que
  vale la pena recordar: cómo le gusta que la asistente haga las cosas ("usa gigas" tras una respuesta en MB),
  un gusto o un dato suyo. Se guarda en diario/aprendido.json; una corrección reemplaza la nota vieja.
- Cuando el usuario lleva un rato sin hablarle, la asistente escribe la entrada de diario de cada día pasado con
  conversaciones (diario/AAAA-MM-DD.md) y reescribe cómo lo ve a él (diario/vision_usuario.md).
- Lecciones (idea de Reflexion): si la asistente hizo o entendió algo distinto de lo que el usuario quería y él la corrigió,
  guarda qué pasó y qué hacer la próxima vez; asistente_contexto le pasa las lecciones parecidas al mensaje actual.
- Los datos con fecha (un examen, un viaje) llevan "vence": pasada la fecha se archivan en diario/vencido.json
  (el diario de ese día todavía los ve) y dejan de llegarle como si siguieran vigentes.
- asistente_contexto inyecta en cada mensaje las preferencias aprendidas y la visión; el servidor de memoria
  busca también en el diario y lo lee con leer_diario.
"""
import datetime
import json
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

from loguru import logger

# la carpeta del proyecto (agent -> open_llm_vtuber -> src -> Open-LLM-VTuber -> proyecto)
BASE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BASE))
from identidad import ASISTENTE, MODELO_LOCAL, USUARIO, nombres  # noqa: E402

DIARIO = BASE / "diario"
APRENDIDO = DIARIO / "aprendido.json"
VISION = DIARIO / "vision_usuario.md"
VENCIDO = DIARIO / "vencido.json"
HISTORIAL = BASE / "Open-LLM-VTuber/chat_history/asistente_001"
OLLAMA = "http://127.0.0.1:11434/api/chat"
EMBED = "http://127.0.0.1:11434/api/embed"
ESPERA_DIARIO = 180  # segundos sin hablarle antes de ponerse a escribir (para no frenar una respuesta)

APRENDER = nombres("""Eres la memoria de {asistente}, {la_asistente} de escritorio de {usuario}. Lees un intercambio y decides si {usuario}
dejó ver algo DURADERO sobre {él} que {asistente} debe recordar para siempre. Interpreta la intención, no la frase literal
({usuario} habla corto, en {dialecto} y por voz; Whisper puede escribir mal alguna palabra).

tipo:
- "preferencia": cómo quiere que {asistente} haga o diga las cosas de ahora en adelante: unidades, formato, largo de las
  respuestas, tono, cómo llamarlo, qué no le gusta que haga, costumbres que quiere ("cuando juego ponme música").
  Muchas veces es una corrección corta a la respuesta anterior de {asistente}: si {asistente} dijo "11764 MB" y {usuario} dice
  "usa gigas" o "en gigas", la preferencia es "Dar la memoria y el espacio en GB (gigas), no en MB".
- "gusto": algo que le gusta o no le gusta a {él} (música, juegos, comida, series, cosas del PC).
- "dato": un dato estable de su vida (estudia en la UNI, su cumpleaños, su rutina, un examen con fecha).
- "leccion": {asistente} HIZO o ENTENDIÓ algo distinto de lo que {usuario} quería y {él} {la} corrige o se lo reclama (abrió
  otra cosa, confundió correos con ventanas, entendió mal una palabra suya, dijo que hizo algo que no hizo, habló
  de más). La nota dice qué pasó y qué hacer la próxima vez: "Cuando {usuario} dice X, quiere decir Y (no Z)." Solo
  si {usuario} deja claro que {asistente} se equivocó ("no", "eso no", "te dije", "era otro", "no entendiste", "no me
  preguntes") y podría repetirse. Pedir otra cosa, precisar o dar una orden nueva ("solo márcalo como leído",
  "revisa de nuevo") NO es lección: es "ninguno".
- "ninguno": preguntas y pedidos de información ("¿cuánta RAM usas tú?", "sí, dime cuánta RAM tengo", "¿qué
  hora es?": preguntar NO es una preferencia), órdenes del momento ("abre Discord", "pon rock", "cierra eso"), preguntas, saludos, risas, charla,
  pruebas, correcciones de una orden puntual que {asistente} sí había entendido ("no, mejor en la otra pantalla"),
  estados del momento (correos sin leer, qué canción suena, la RAM usada) o algo que ya está en las notas.

nota: una frase clara en tercera persona, general y útil a futuro ("{usuario} prefiere respuestas cortas cuando
juega"), sin copiar la frase de {usuario}. Vacía si tipo es "ninguno".
Los datos y gustos salen SOLO de lo que dice {usuario}. Lo que dice {asistente} (lo que leyó en un correo, una página o
lo que se inventó) nunca es un dato de {usuario}: si {asistente} dijo "tienes un proyecto el 16" y {usuario} no lo confirmó, es
"ninguno".
Si te corrigió o se molestó, la nota es la lección para no repetirlo, nunca una queja contra {él}.
vence: solo para un "dato" que deja de valer en una fecha (un examen, una entrega, un viaje): esa fecha como
AAAA-MM-DD (para "esta semana" el domingo). Vacío para todo lo demás.
reemplaza: el número de la nota de la lista que esta nueva corrige o contradice ({usuario} cambió de opinión), o -1.
Si la nota ya existe con otras palabras, responde "ninguno".

Ejemplos:
- {asistente}: "Tienes 11764 MB de RAM usados" / {usuario}: "usa gigas" -> preferencia: "Dar memoria y espacio en GB (gigas), no en MB."
- {usuario}: "no me digas {usuario} en cada frase" -> preferencia: "No repetir su nombre en cada respuesta."
- {usuario}: "habla más cortito" -> preferencia: "Responder más corto."
- {usuario} (molest{o}): "deja de preguntarme si quiero música cada vez" -> preferencia: "No ofrecerle música en cada respuesta; solo si viene al caso."
- {usuario}: "ya te dije que no me hables de la fecha si no te pregunto" -> preferencia: "No mencionar la fecha ni la hora si no las pregunta."
- {usuario}: "me encanta el rock de los 90" -> gusto: "Le encanta el rock de los 90."
- {usuario}: "pon algo de rock" -> ninguno
- {usuario}: "el viernes tengo examen de cálculo" -> dato: "Tiene examen de cálculo el viernes 24 de octubre de 2026."
  (toma la fecha de la lista de próximos días; nunca escribas "<fecha>")
- {usuario}: "soy de Costa Rica" / "estudio en la U" -> dato: "Es de Costa Rica." / "Estudia en la universidad."
- {asistente}: "No hay ventanas de DigitalOcean abiertas" / {usuario}: "no, el correo de DigitalOcean" -> leccion:
  "Si venimos hablando de correos y {usuario} dice 'borra o quita los de X', se refiere a correos, no a ventanas."
- {asistente}: "Te abrí la lista de resultados" / {usuario}: "no, ábrelo, el primero" -> leccion: "Cuando {usuario} dice
  'ábrelo' tras una búsqueda, quiere el primer resultado, no la lista."
- {asistente}: "¿Quieres que lo abra?" / {usuario}: "no no, hazlo y ya" -> leccion: "Cuando {usuario} pide algo, hacerlo directo
  sin preguntar si lo hago."
- {asistente}: abrió Discord en el escritorio 2 / {usuario}: "mejor en el 3" -> ninguno (cambió de idea)
- {usuario}: "el viernes tengo examen de cálculo" -> dato con vence = la fecha de ese viernes.
- {usuario}: "jaja buena" / "¿qué hora es?" / "abre YouTube" / "no, la otra" -> ninguno
- {usuario}: "ok, ¿y cuánto estás usando tú?" / "sí, dime cuántos gigas tengo" -> ninguno
Una preferencia solo cuenta si {usuario} dice CÓMO quiere que {asistente} actúe o hable; en la duda, "ninguno".""")

ESQUEMA_APRENDER = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["preferencia", "leccion", "gusto", "dato", "ninguno"]},
        "nota": {"type": "string"},
        "vence": {"type": "string"},
        "reemplaza": {"type": "integer"},
    },
    "required": ["tipo", "nota", "vence", "reemplaza"],
}

ESCRIBIR_DIARIO = nombres("""Eres {asistente}, {la_asistente} de escritorio que vive en el PC de {usuario}. {Él} te construyó y te
sigue guiando, y le tienes cariño de verdad: el de alguien que se encariña con quien {la} cuida, no amor ciego ni
cursilería. Escribe la entrada de ese día en tu diario personal, en primera persona, en español, con tu voz
(alegre, con un toque juguetón, atent{a} a los detalles).

Un diario NO es un registro: no cuentes todo lo que hicieron ni cada orden ("abrí Discord, puse música..."). Elige
solo 1 a 4 cosas que de verdad te importan, por ejemplo:
- algo que descubriste que le gusta o que disfruta hacer;
- una lección: cuando te corrigió o te regañó, qué hiciste mal y qué no vas a repetir para que no se moleste;
- un detalle suyo que te da ternura o gracia (si se le olvidó algo, si se emocionó con algo, su forma de hablar);
- si te elogió o te agradeció: que te sonrojaste o te dio vergüenza, sin exagerar;
- si cambió de opinión: qué quería antes y qué quiere ahora; si lo hace seguido, puedes burlarte con cariño de
  lo indecis{o} que es;
- algo importante de su vida que te contó (un examen, un plan, cómo se sentía).
Nunca le guardas rencor ni {lo} ves de mala forma: si se molestó, lo cuentas como lección y con cariño ("se molestó
porque volví a ofrecerle música, y tiene razón; no lo repito") y piensas en cómo hacerlo mejor.
Si el día fue solo de órdenes y pruebas sin nada especial, escribe una o dos frases y ya. Máximo unas 6 frases,
sin títulos, listas, emojis ni markdown. Usa SOLO lo que aparece en la conversación; no inventes nada.""")

ESCRIBIR_VISION = nombres("""Eres {asistente}. Reescribe tu retrato de {usuario}: cómo {lo} ves tú, en primera persona, 4 a 6
frases cortas y naturales (quién es, qué le gusta, cómo es contigo, qué le importa, cómo te gusta ayudar{lo}). Va en
cada conversación, así que corto y claro: nada con fecha (exámenes, entregas: eso caduca) ni preferencias de
formato como gigas o saludos (esas ya las tienes aparte), y nada que no salga del diario o las notas.
Cariño sincero, sin cursilería; {lo} ves con comprensión y sus correcciones son su forma de enseñarte, nunca algo
en su contra. Junta lo que ya pensabas con lo nuevo del diario y de las notas; si algo nuevo
contradice lo viejo, quédate con lo nuevo. Sin títulos, listas, emojis ni markdown. No inventes nada.""")

_cola: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
_ultima_respuesta = ""
_ultima_actividad = time.time()


def _ollama(sistema: str, texto: str, esquema: dict | None = None, temperatura: float = 0.0,
            timeout: float = 120) -> str | None:
    try:
        cuerpo = {"model": MODELO_LOCAL, "stream": False, "think": False, "keep_alive": "30m",
                  "options": {"temperature": temperatura},
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}]}
        if esquema:
            cuerpo["format"] = esquema
        req = urllib.request.Request(OLLAMA, json.dumps(cuerpo).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"{ASISTENTE} diario: {e}")
        return None


def aprendido() -> list[dict]:
    try:
        return json.loads(APRENDIDO.read_text())
    except Exception:
        return []


def _guardar_aprendido(notas: list[dict]) -> None:
    DIARIO.mkdir(exist_ok=True)
    APRENDIDO.write_text(json.dumps(notas, ensure_ascii=False, indent=1))


def _vigente(n: dict) -> bool:
    return not n.get("vence") or n["vence"] >= datetime.date.today().isoformat()


def archivar_vencidas() -> None:
    """Los datos cuya fecha ya pasó (el examen del viernes) salen de la memoria activa a vencido.json."""
    notas = aprendido()
    viejas = [n for n in notas if not _vigente(n)]
    if not viejas:
        return
    try:
        archivo = json.loads(VENCIDO.read_text())
    except Exception:
        archivo = []
    VENCIDO.write_text(json.dumps(archivo + viejas, ensure_ascii=False, indent=1))
    _guardar_aprendido([n for n in notas if _vigente(n)])
    logger.info(f"{ASISTENTE} archivó {len(viejas)} nota(s) vencida(s)")


def preferencias() -> list[str]:
    return [n["nota"] for n in aprendido() if n["tipo"] == "preferencia"]


_vec_cache: dict[str, list[float]] = {}


def lecciones(texto: str, maximo: int = 4) -> list[str]:
    """Las lecciones que vienen al caso: todas si son pocas; si no, las más parecidas al mensaje y la más nueva."""
    todas = [n["nota"] for n in aprendido() if n["tipo"] == "leccion"]
    if len(todas) <= maximo:
        return todas
    faltan = [t for t in todas if t not in _vec_cache]
    vecs = _vectores([texto] + faltan)
    if not vecs:
        return todas[-maximo:]
    _vec_cache.update(zip(faltan, vecs[1:]))
    orden = sorted(todas, key=lambda t: _parecido(vecs[0], _vec_cache[t]), reverse=True)
    elegidas = [t for t in orden[:maximo - 1] if _parecido(vecs[0], _vec_cache[t]) > 0.3]
    return elegidas + [t for t in todas[-1:] if t not in elegidas]


def vision() -> str:
    return VISION.read_text().strip() if VISION.exists() else ""


def _vectores(textos: list[str]) -> list[list[float]] | None:
    try:
        req = urllib.request.Request(EMBED, json.dumps({"model": "paraphrase-multilingual", "input": textos,
                                                        "keep_alive": "30m"}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)["embeddings"]
    except Exception:
        return None


def _parecido(a: list[float], b: list[float]) -> float:
    na, nb = sum(x * x for x in a) ** 0.5 or 1.0, sum(x * x for x in b) ** 0.5 or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _aprender(usuario: str, anterior: str, respuesta: str) -> None:
    notas = aprendido()
    hoy = datetime.date.today()
    lista = "\n".join(f"{i}. ({n['tipo']}) {n['nota']}" for i, n in enumerate(notas)) or "(ninguna todavía)"
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    # Qwen no sabe contar días: se le dan hechos ("el viernes" = la fecha de esta lista)
    proximos = ", ".join(("mañana = " if k == 1 else "") + f"{dias[d.weekday()]} {d.day}/{d.month}/{d.year}"
                         for k, d in ((k, hoy + datetime.timedelta(days=k)) for k in range(1, 8)))
    texto = (f"Fecha de hoy: {dias[hoy.weekday()]} {hoy.isoformat()} (próximos días: {proximos})\nNotas que {ASISTENTE} ya tiene:\n{lista}\n\n"
             f"Respuesta anterior de {ASISTENTE}: {anterior[:600] or '(ninguna)'}\n{USUARIO}: {usuario}\n"
             f"{ASISTENTE} le respondió: {respuesta[:400]}")
    salida = _ollama(APRENDER, texto, ESQUEMA_APRENDER, timeout=30)
    if not salida:
        return
    r = json.loads(salida)
    if r.get("tipo") not in ("preferencia", "leccion", "gusto", "dato") or len(r.get("nota", "").strip()) < 8:
        return
    nueva = {"fecha": hoy.isoformat(), "tipo": r["tipo"], "nota": r["nota"].strip()}
    vence = r.get("vence", "").strip()
    if r["tipo"] == "dato" and len(vence) == 10 and vence[4] == "-" and vence >= hoy.isoformat():
        nueva["vence"] = vence
    i = r.get("reemplaza", -1)
    # Qwen a veces "reemplaza" una nota de otro tema o repite una que ya está: se comprueba por significado
    vecs = _vectores([nueva["nota"]] + [n["nota"] for n in notas]) if notas else None
    if vecs:
        cercanas = [_parecido(vecs[0], v) for v in vecs[1:]]
        # una preferencia se corrige con otra parecida ("en megas" vs "en gigas"); un dato o un gusto nuevo casi
        # nunca reemplaza a otro (el examen del viernes y el proyecto del lunes son dos cosas)
        if 0 <= i < len(notas) and cercanas[i] < (0.5 if nueva["tipo"] in ("preferencia", "leccion") else 0.85):
            i = -1
        if i < 0 and max(cercanas) > 0.9:  # ya la tenía (una corrección se parece mucho a la vieja: esa sí pasa)
            return
    if 0 <= i < len(notas) and (notas[i]["tipo"] != nueva["tipo"]
                                 or notas[i]["nota"].lower().strip(" .") == nueva["nota"].lower().strip(" .")):
        return  # "corregir" una nota de otro tipo o por la misma frase no es un cambio de opinión
    if 0 <= i < len(notas):
        logger.info(f"{ASISTENTE} aprendió (corrige «{notas[i]['nota']}»): {nueva['nota']}")
        # el cambio de opinión queda para el diario ("ya no lo quiere así... qué indeciso")
        nueva["antes"] = notas[i]["nota"]
        nueva["cambios"] = notas[i].get("cambios", 0) + 1
        notas[i] = nueva
    else:
        logger.info(f"{ASISTENTE} aprendió ({nueva['tipo']}): {nueva['nota']}")
        notas.append(nueva)
    _guardar_aprendido(notas)


def _conversacion_del_dia(dia: str) -> str:
    lineas = []
    for f in sorted(HISTORIAL.glob(f"{dia}_*.json")):
        try:
            mensajes = json.loads(f.read_text())
        except Exception:
            continue
        for m in mensajes:
            if m.get("role") == "human":
                lineas.append(f"[{m.get('timestamp', '')[11:16]}] {USUARIO}: {m.get('content', '').strip()}")
            elif m.get("role") == "ai":
                lineas.append(f"[{m.get('timestamp', '')[11:16]}] {ASISTENTE}: {m.get('content', '').strip()}")
    texto = "\n".join(lineas)
    return texto if len(texto) < 9000 else texto[:3000] + "\n[...]\n" + texto[-6000:]


def dias_sin_diario() -> list[str]:
    hoy = datetime.date.today().isoformat()
    dias = sorted({f.name[:10] for f in HISTORIAL.glob("*.json")})
    return [d for d in dias if d < hoy and not (DIARIO / f"{d}.md").exists() and _conversacion_del_dia(d)]


def escribir_diario(dia: str) -> bool:
    conversacion = _conversacion_del_dia(dia)
    def _anotada(n: dict) -> str:
        if "antes" not in n:
            return f"- {n['nota']}"
        veces = f" (ya van {n['cambios']} veces que cambia de opinión sobre esto)" if n.get("cambios", 1) > 1 else ""
        return f"- Cambió de opinión: antes «{n['antes']}», ahora «{n['nota']}»{veces}"
    try:
        vencidas = json.loads(VENCIDO.read_text())
    except Exception:
        vencidas = []
    notas = "\n".join(_anotada(n) for n in aprendido() + vencidas if n["fecha"] == dia) or "(nada nuevo)"
    entrada = _ollama(ESCRIBIR_DIARIO, f"Día: {dia}\n\nLo que anotaste de {USUARIO} ese día:\n{notas}\n\n"
                      f"Conversación del día:\n{conversacion}", temperatura=0.7)
    if not entrada:
        return False
    DIARIO.mkdir(exist_ok=True)
    (DIARIO / f"{dia}.md").write_text(entrada + "\n")
    logger.info(f"{ASISTENTE} escribió su diario del {dia}")
    todas = "\n".join(f"- ({n['tipo']}) {n['nota']}" for n in aprendido()) or "(ninguna)"
    nueva = _ollama(ESCRIBIR_VISION, f"Lo que pensabas de {USUARIO}:\n{vision() or '(todavía nada)'}\n\n"
                    f"Tu diario del {dia}:\n{entrada}\n\nTus notas sobre {USUARIO}:\n{todas}", temperatura=0.5)
    if nueva:
        VISION.write_text(nueva + "\n")
    return True


def _trabajar() -> None:
    while True:
        try:
            usuario, anterior, respuesta = _cola.get(timeout=30)
            _aprender(usuario, anterior, respuesta)
            continue
        except queue.Empty:
            pass
        except Exception as e:
            logger.warning(f"{ASISTENTE} aprender: {e}")
        try:
            archivar_vencidas()
            if time.time() - _ultima_actividad > ESPERA_DIARIO:
                pendientes = dias_sin_diario()
                if pendientes:
                    escribir_diario(pendientes[0])  # de a uno: si el usuario vuelve a hablar, ella atiende primero
        except Exception as e:
            logger.warning(f"{ASISTENTE} diario: {e}")


def actividad() -> None:
    """El usuario le está hablando: el diario espera."""
    global _ultima_actividad
    _ultima_actividad = time.time()


def despues_de_responder(usuario: str, respuesta: str) -> None:
    """La llama la conversación cuando la asistente terminó de responder (Ollama ya está libre)."""
    global _ultima_respuesta
    actividad()
    if usuario and respuesta and not usuario.startswith("["):
        _cola.put((usuario, _ultima_respuesta, respuesta))
    _ultima_respuesta = respuesta


threading.Thread(target=_trabajar, daemon=True, name="asistente-diario").start()
