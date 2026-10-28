"""Apps, juegos, proyectos y ventanas del PC (Hyprland): abrir, cerrar y mover, en el escritorio y la pantalla que
diga, y qué ventanas hay abiertas. Lo hace acciones-mcp/servidoracciones.py, solo con su lista blanca.

Qué pide lo interpreta el modelo (entiende el orden natural de la frase: "abre WhatsApp en la otra pantalla y en el 3
VS Code"); si no responde, reglas (_ordenes_por_reglas). Las órdenes las dio el usuario: se ejecutan sin confirmar.
Un modelo chico a veces dice "voy a abrirlo" sin llamar a la herramienta: por eso se hace aquí, antes de responder.
"""
import re
import time

from funciones import Frases, Pedido, Resultado, mcp
from identidad import USUARIO, nombres

servidor = mcp("acciones")  # acciones-mcp: abrir, cerrar y mover con su lista blanca

VENTANAS = re.compile(r"\b(abiert[oa]s?|ventanas)\b", re.I)
# Órdenes directas de abrir algo ("abre steam en el 3", "ábreme discord", "abramos mh wilds"):
# se ejecutan aquí; un modelo chico a veces dice "voy a abrirlo" sin llamar a la herramienta
ABRIR = re.compile(
    nombres(r"^\W*(?:{asistente_re}\W+)?(?:pues\s+|y\s+|también\s+|tambien\s+)*"
    r"(?:[aá]br[eéi]me|[aá]br[eéií]|abramos|abrir|lanza|lánzame|inicia|pon(?:me)?)\s+(?:también\s+|tambien\s+)?"
    r"(?:el |la |los |las |un |una )?(?P<que>.+?)"
    r"(?:\s+(?:en|al)\s+(?:el\s+|la\s+)?(?:(?:workspace|escritorio|pestaña|espacio)\s*(?:de trabajo\s*)?)?(?P<ws>\d+))?\W*$"),
    re.I)
MOVER = re.compile(nombres(r"^\W*(?:{asistente_re}\W+)?(?:pues\s+|y\s+|también\s+)*(?:mueve|muéve(?:me|lo|la)?|mover|pasa|pásame|pásalo|pásala|lleva|llévame|llévalo|llévala|manda|mándame|mándalo|mándala)\s+(?:el |la |los |las |mi |mis )?(?P<que>.+?)\W*$"), re.I)
CERRAR = re.compile(nombres(r"^\W*(?:{asistente_re}\W+)?(?:pues\s+|y\s+|también\s+)*(?:cierra|ciérra(?:me|lo|la)?|cerrá|cerrar|quita|quítame)\s+(?:el |la |los |las )?(?P<que>.+?)\W*$"), re.I)
NO_ABRIR_SOLO = re.compile(r"claude|conversaci|chat|carpeta|archivo", re.I)

HAY_ACCION = re.compile(r"\b([aá]br|cierr|ciérr|cerr|muev|muév|mover|pas[aáe]|llev|lléva|mand|lanz|inici|quit)", re.I)
INTERPRETAR = nombres("""Convierte lo que pide {usuario} en acciones sobre apps y ventanas de su PC. Responde solo el JSON.
Cada acción: tipo ("abrir", "cerrar" o "mover"), que (la app, juego o proyecto, tal como lo nombró, SIN el lugar),
escritorio (número del workspace/escritorio/pestaña que dijo PARA ESA acción, o ""), pantalla ("principal",
"segunda", "misma" o ""). El lugar puede ir antes o después de la app: asígnalo a la app a la que se refiere.
"Pantalla primaria/principal/1" = "principal"; "secundaria/otra/vertical/2" = "segunda"; "la misma pantalla" = "misma".
"Mover/pasar/llevar/mandar" = mover. "La ventana actual / esta ventana / la que tengo enfrente" -> que = "ventana actual". Si nombra una app sin decir qué hacer con ella ("y ahora, WhatsApp"),
tipo = "preguntar" (no adivines si abrir o cerrar). Si niega ("no abras") o no pide ninguna acción, devuelve acciones vacías.
El escritorio oculto / área especial / scratchpad / "ventana oculta" (el que {usuario} abre con Super+S): escritorio = "oculto".
NO inventes lugares: si para una acción no dijo pantalla, pantalla = ""; si no dijo escritorio, escritorio = "".
"Pantalla 3" o "la 3" con un número mayor que 2 es el escritorio 3, no una pantalla.
Ejemplos:
"abre WhatsApp en la pantalla secundaria y en el workspace 3 abre VS Code" -> [{"tipo":"abrir","que":"WhatsApp","escritorio":"","pantalla":"segunda"},{"tipo":"abrir","que":"VS Code","escritorio":"3","pantalla":""}]
"cierra Discord y abre el explorador en la misma pantalla" -> [{"tipo":"cerrar","que":"Discord","escritorio":"","pantalla":""},{"tipo":"abrir","que":"explorador","escritorio":"","pantalla":"misma"}]
"pasa la terminal al 4 de la pantalla principal" -> [{"tipo":"mover","que":"terminal","escritorio":"4","pantalla":"principal"}]
"mueve discord al 4" -> [{"tipo":"mover","que":"discord","escritorio":"4","pantalla":""}]
"(Orden anterior, ya hecha: "abre discord"...) y ahora ciérralo" -> [{"tipo":"cerrar","que":"discord","escritorio":"","pantalla":""}]
"ok, cierra Dolphin. Y ahora, WhatsApp" -> [{"tipo":"cerrar","que":"Dolphin","escritorio":"","pantalla":""},{"tipo":"preguntar","que":"WhatsApp","escritorio":"","pantalla":""}]
"pon la música en la ventana oculta" -> [{"tipo":"abrir","que":"música","escritorio":"oculto","pantalla":""}]
"abre wsp en la pantalla secundaria y vs code en la pantalla 3" -> [{"tipo":"abrir","que":"wsp","escritorio":"","pantalla":"segunda"},{"tipo":"abrir","que":"vs code","escritorio":"3","pantalla":""}]
"¿qué hora es?" -> []""")
ESQUEMA = {"type": "object", "properties": {"acciones": {"type": "array", "items": {"type": "object", "properties": {
    "tipo": {"type": "string", "enum": ["abrir", "cerrar", "mover", "preguntar"]}, "que": {"type": "string"},
    "escritorio": {"type": "string"}, "pantalla": {"type": "string", "enum": ["principal", "segunda", "misma", ""]}},
    "required": ["tipo", "que", "escritorio", "pantalla"]}}}, "required": ["acciones"]}


# "abre Discord en el 4" -> "Va, abriendo Discord en el 4."
HACIENDO = {"abre": "abriendo", "cierra": "cerrando", "mueve": "moviendo", "pasa": "pasando", "lleva": "llevando",
            "manda": "mandando", "quita": "quitando", "lanza": "lanzando", "inicia": "iniciando", "pon": "poniendo",
            "minimiza": "minimizando"}
FRASES = Frases({
    "ventanas": ["{g} {r}.", "Va, {g} {r}.", "Dale, {g} {r}.", "Un momento, {g} {r}.", "{g} {r}, un segundo."],
})


def _aviso(orden: str) -> str:
    m = re.match(nombres(r"^\W*(?:{asistente_re}\W+)?(\w+)\s+(.+?)\W*$"), orden, re.I)
    if not m or m.group(1).lower() not in HACIENDO:
        return ""
    resto = re.sub(r"\bmis\b", "tus", re.sub(r"\bmi\b", "tu", m.group(2)))
    return FRASES.decir("ventanas", g=HACIENDO[m.group(1).lower()], r=resto)


def _legible(texto: str) -> str:
    """'Cerré: org.kde.dolphin, com.ktechpit.whatsie' -> 'Cerré: Dolphin, Whatsie'."""
    return re.sub(r"\b(?:[a-z0-9]+\.)+([a-z0-9_-]+)\b", lambda m: m.group(1).capitalize(), texto)


def _ejecutar(acciones: list[dict]) -> str | None:
    hechos = []
    for a in acciones:
        que = (a.get("que") or "").strip()
        ws = a.get("escritorio") or ""
        ws = "special:special" if re.search(r"ocult|especial|scratch", ws, re.I) else re.sub(r"\D", "", ws)
        pantalla = a.get("pantalla") or ""
        if pantalla == "misma":
            pantalla = servidor.ultima_pantalla_cerrada
        if not que:
            continue
        if a.get("tipo") == "preguntar":
            hechos.append(f"(No hiciste nada con {que}: {USUARIO} no dijo si abrirlo o cerrarlo; pregúntale.)")
        elif a.get("tipo") == "cerrar":
            hechos.append(servidor.cerrar_ventanas(que, confirmado=True))
        elif a.get("tipo") == "mover":
            hechos.append(servidor.mover_ventana(que, escritorio=ws, pantalla=pantalla))
        else:
            hechos.append(_abrir_que(que, ws, pantalla))
    # lo que falló va marcado, para que la asistente lo diga en vez de responder "¡listo!"
    marcados = [("NO SE PUDO: " + h) if re.match(r"^(No |¿)", h) else h for h in hechos if h]
    return " ".join(marcados) or None


def _abrir_que(que: str, ws: str, pantalla: str) -> str:
    """Abre un proyecto (VS Code con un repo), un juego o una app."""
    repo = re.match(r"^(?:vs ?code|visual studio code|code)\s+(?:con|en el proyecto|en el repo|del? proyecto)\s+(?:el\s+)?(.+)$", que, re.I) \
        or re.match(r"^(?:el\s+)?(?:proyecto|repo)\s+(.+)$", que, re.I)
    if repo:
        return servidor.abrir_proyecto(repo.group(1), escritorio=ws)
    juegos = servidor._juegos()
    if servidor._elegir(que, juegos) or servidor._elegir(que.lower().replace("mh", "monster hunter"), juegos):
        return servidor.abrir_juego(que) + (" (los juegos los ubica Steam)" if ws or pantalla else "")
    return servidor.abrir_app(que, escritorio=ws, pantalla=pantalla)


def _interpretar(texto: str, previa: str, modelo) -> list[dict] | None:
    """El modelo interpreta el pedido como lista de acciones; None si no responde (entonces, las reglas)."""
    antes = (f"(Orden anterior, ya hecha: \"{previa}\". Si ahora dice \"lo\", \"la\" o \"eso\", se refiere a esa "
             "app.)\n" if previa else "")
    r = modelo(INTERPRETAR, antes + texto, ESQUEMA)
    return None if r is None else r.get("acciones", [])


def _ordenes_directas(texto: str, previa: str, modelo) -> str | None:
    """Órdenes directas del usuario: las interpreta Qwen (entiende el orden natural de la
    frase); si Ollama no responde, se usan las reglas de abajo."""
    if not HAY_ACCION.search(texto) or NO_ABRIR_SOLO.search(texto) and not re.search(r"explorador|gestor|archivos", texto, re.I):
        return None
    acciones = _interpretar(texto, previa, modelo)
    if acciones is not None:
        # "X en la pantalla 4": con más de 2 pantallas no tiene sentido, es el escritorio 4
        for a in acciones:
            # solo la primera "pantalla" que viene después de esa app, sin pasar a la siguiente orden
            m = re.search(rf"{re.escape(a.get('que', ''))}(?:(?!\by\b)[^,])*?\bpantalla\s+(\w+)", texto, re.I) if a.get("que") else None
            if m and m.group(1).isdigit() and int(m.group(1)) > 2:
                a["escritorio"], a["pantalla"] = m.group(1), ""
        return _ejecutar(acciones)
    return _ordenes_por_reglas(texto)


def _ordenes_por_reglas(texto: str) -> str | None:
    """Órdenes directas del usuario ("cierra discord y abre vs code en la misma pantalla"):
    se ejecutan aquí, en orden, sin pedir confirmación (las pidió él)."""
    hechos = []
    VERBO = (r"(?:[aá]br[eéi]me|[aá]br[eéií]|abramos|abrir|lanza|inicia|pon(?:me)?|cierra|ciérra(?:me|lo|la)?|cerrar|quita"
             r"|mueve|muéve(?:me|lo|la)?|mover|pasa|pásame|pásalo|pásala|lleva|llévame|llévalo|llévala|manda|mándame|mándalo|mándala)")
    partes, verbo = [], ""
    # "abre X en el 3, Y en la segunda pantalla y cierra Z": cada parte hereda el verbo anterior
    for parte in re.split(r"\s+y\s+|,\s*|[.;!?¿¡]+", texto, flags=re.I):
        parte = parte.strip(" ,")
        # muletillas y formas educadas antes del verbo: "aquí abre...", "oye, puedes abrir..."
        if re.match(r"^\W*(?:\w+\W+){0,3}no\s+", parte, re.I):
            partes.append(parte)  # "no abras steam": nunca ejecutarlo
            continue
        parte = re.sub(nombres(r"^\W*(?:(?:{asistente_re}|aqu[ií]|ah[ií]|all[aá]|oye|bueno|ok|okay|vale|ya|ahora|entonces|porfa|eh|este|y)\W+)*"), "", parte, flags=re.I)
        parte = re.sub(nombres(r"^\W*(?:{asistente_re}\W+)?(?:por favor\s+)?(?:(?:me\s+|lo\s+)?(?:puedes|podrías|podrias|quieres|podés)\s+"
                       r"|(?:quiero|necesito|ocupo)\s+que\s+(?:me\s+)?|(?:quiero|necesito|ocupo|me\s+gustar[ií]a|voy\s+a)\s+(?!que\b))?"), "", parte, flags=re.I)
        parte = re.sub(r"^(abras|abrás)\b", "abre", parte, flags=re.I)
        parte = re.sub(r"^(cierres|cerrés)\b", "cierra", parte, flags=re.I)
        if not parte:
            continue
        if partes and re.match(r"^(en|al|a la|a el|de la|del)\s+(el\s+|la\s+|mi\s+)?(workspace|escritorio|pestaña|espacio|pantalla|monitor|primer|segund|tercer|cuart|\d)", parte, re.I):
            partes[-1] += f" {parte}"  # "..., en el workspace 3": es el lugar de lo anterior
            continue
        m = re.match(nombres(r"^\W*(?:{asistente_re}\W+)?(?:pues\s+|y\s+|luego\s+|después\s+|también\s+)*")
                     + f"({VERBO})\\b", parte, re.I)
        if m:
            verbo = m.group(1)
        elif verbo:
            parte = f"{verbo} {parte}"
        partes.append(parte)
    solo = len(partes) == 1
    for parte in partes:
        mv = MOVER.match(parte)
        if mv:
            ws, pantalla = _destino(parte)
            que = re.sub(r"\s+(a|al|en|hacia|para)\s+(el|la|mi)?\s*.*$", "", mv.group("que"), flags=re.I).strip()
            hechos.append(servidor.mover_ventana(que, escritorio=ws, pantalla=pantalla))
            continue
        c = CERRAR.match(parte)
        if c and not NO_ABRIR_SOLO.search(c.group("que")):
            que = re.sub(r"\s+(en|de)\s+(el|la)\s+.*$", "", c.group("que"), flags=re.I).strip()
            hechos.append(servidor.cerrar_ventanas(que, confirmado=True))
            continue
        h = _abrir_directo(parte, texto if solo else parte)
        if h:
            hechos.append(h)
    return " ".join(hechos) if hechos else None


def _destino(texto: str) -> tuple[str, str]:
    """(escritorio, pantalla) mencionados en el texto."""
    ws = re.search(r"(?:workspace|escritorio|pestaña|espacio)\s*(?:de trabajo\s*)?(\d+)|\b(?:al|el)\s+(\d+)\b", texto, re.I)
    ws = (ws.group(1) or ws.group(2)) if ws else ""
    pantalla = ""
    if re.search(r"(segunda|secundaria|otra|vertical|frigidaire)\s+pantalla|pantalla\s+(2|dos|secundaria|vertical)", texto, re.I):
        pantalla = "segunda"
    elif re.search(r"pantalla\s+(principal|primaria|1|uno)|(primera|principal|primaria)\s+pantalla", texto, re.I):
        pantalla = "principal"
    return ws, pantalla


def _abrir_directo(texto: str, completo: str = "") -> str | None:
    """Si es una orden directa de abrir algo conocido, la ejecuta y devuelve qué pasó."""
    completo = completo or texto
    # la orden puede venir en cualquier parte ("Steam, abre Steam."), y el escritorio en
    # otra frase ("ábrelo, en el workspace 3")
    m = None
    for frase in re.split(r"[.,;!?¿¡]+", texto):
        m = ABRIR.match(frase.strip())
        if m:
            break
    if not m:
        return None
    base = re.sub(r"\s+(en|al)\s+(el|la)\s+.*$", "", m.group("que"), flags=re.I)
    if NO_ABRIR_SOLO.search(m.group("que")) and servidor._norm(base) not in servidor.ALIAS_APPS and not re.search(r"explorador|gestor|administrador", base, re.I):
        return None  # "abre el archivo X" no es abrir una app; "el explorador de archivos" sí
    ws_aparte = re.search(r"(?:workspace|escritorio|pestaña|espacio)\s*(\d+)", completo, re.I)
    que = re.sub(r"^(vs ?code|visual studio code|el code|code)\s+(con|en\s+el\s+proyecto|en\s+el\s+repo|del?\s+proyecto)\s+(el\s+)?(proyecto\s+|repo\s+)?", "", m.group("que"), flags=re.I)
    es_proyecto = que != m.group("que") or re.search(r"\b(proyecto|repo)\b", m.group("que"), re.I)
    ws = m.group("ws") or (ws_aparte.group(1) if ws_aparte else "")
    pantalla = ""
    if re.search(r"(segunda|secundaria|otra|vertical|frigidaire)\s+pantalla|pantalla\s+(2|dos|secundaria|vertical)", completo, re.I):
        pantalla = "segunda"
    elif re.search(r"pantalla\s+(principal|primaria|1|uno)|(primera|principal|primaria)\s+pantalla", completo, re.I):
        pantalla = "principal"
    elif re.search(r"(misma|esa|la del)\s+(pantalla|pestaña|lugar|sitio)", completo, re.I) and servidor.ultima_pantalla_cerrada:
        pantalla = servidor.ultima_pantalla_cerrada
    que = re.sub(r"^(el\s+)?(proyecto|repo)\s+", "", que, flags=re.I).strip()
    juegos = servidor._juegos()
    if not es_proyecto and (servidor._elegir(que, juegos) or servidor._elegir(que.replace("mh", "monster hunter"), juegos)):
        return servidor.abrir_juego(que) + (" (los juegos los ubica Steam, no se puede elegir escritorio)" if ws else "")
    repos = {p.name: p for b in servidor.PROYECTOS if b.exists() for p in b.iterdir() if p.is_dir()}
    if es_proyecto and servidor._elegir(que, repos):
        return servidor.abrir_proyecto(que, escritorio=ws)
    que = re.sub(r"\s+(en|al)\s+(el\s+|la\s+)?(workspace|escritorio|pestaña|espacio)\b.*$", "", que, flags=re.I)
    que = re.sub(r"\s+(en|a)\s+(la\s+|el\s+|esa\s+|mi\s+)?(segunda|secundaria|otra|vertical|primera|principal|primaria|misma)?\s*(pantalla|pestaña|lugar|sitio|monitor).*$", "", que, flags=re.I).strip()
    if servidor.resolver_app(que):
        return servidor.abrir_app(que, escritorio=ws, pantalla=pantalla)
    return None


# ---------- el contrato (ver funciones/__init__.py) ----------

# Memoria corta: lo último que se ejecutó y si la asistente alcanzó a decirlo. Si el usuario da otra orden antes de que
# ella confirme la anterior, la respuesta cuenta las dos en orden, y si las dos frases llegan unidas (por una pausa) no
# se repite la primera.
_ultima = {"t": 0.0, "orden": "", "hecho": "", "dicho": True}
RECIENTE = 30  # segundos


def respondio() -> None:
    _ultima["dicho"] = True


def _reciente() -> bool:
    return time.time() - _ultima["t"] < RECIENTE


def _antes() -> str:
    """Lo que hizo por la orden anterior y no alcanzó a decir."""
    return _legible(_ultima["hecho"]) if _reciente() and not _ultima["dicho"] and _ultima["hecho"] else ""


def _contar_antes(antes: str) -> str:
    return (f"Antes, por otra orden de {USUARIO}, ya habías hecho esto y no alcanzaste a decírselo: {antes} "
            "Cuéntale las dos cosas en orden, en una o dos frases (\"Listo, te abrí X y ya lo cerré\").")


DEL_NAVEGADOR = re.compile(nombres(r"pesta|navegador|{navegador_re}|resultado|enlace|link|p[aá]gina"), re.I)
APPS = re.compile(r"discord|code|steam|whatsapp|explorador|terminal|kitty|dolphin", re.I)


def regla(texto: str, orden: str, temas: list[str]) -> bool | None:
    """Solo es de ventanas lo que se puede hacer con ellas (abrir, cerrar, mover) o preguntar cuáles hay: el router
    mandaba aquí "enciende la aspiradora", "apaga las luces" o "sube el volumen del altavoz" (prueba de fuego).
    Y tras buscar, "ábrelo en el navegador" es abrir el resultado (internet), no la app."""
    if "ventanas" not in temas:
        return None
    if not (HAY_ACCION.search(orden) or HAY_ACCION.search(texto) or VENTANAS.search(orden)):
        return False
    if "web" in temas and DEL_NAVEGADOR.search(orden) and not APPS.search(orden):
        return False
    return None


def detectar(texto: str) -> bool:
    return bool(HAY_ACCION.search(texto) or VENTANAS.search(texto))


def entender(pedido: Pedido, modelo) -> dict | None:
    """La orden (sin la parte que ya se hizo) y si pregunta qué ventanas hay. La interpreta el modelo al ejecutar, para
    que el aviso ("Va, abriendo Discord en el 4.") salga antes."""
    orden = pedido.resuelto
    previa = _ultima["orden"] if _reciente() else ""
    if previa and orden.startswith(previa):
        orden = orden[len(previa):].strip(" ,.")  # la parte ya hecha no se repite
    ver = bool(VENTANAS.search(pedido.resuelto))
    if not HAY_ACCION.search(orden):
        orden = ""  # nada que se pueda hacer con ventanas ("apaga las luces")
    if not orden and not ver:
        return None
    return {"orden": orden, "previa": previa, "ver": ver, "antes": _antes(), "modelo": modelo}


def aviso(i: dict) -> str:
    return _aviso(i["orden"]) if i["orden"] else ""


def ejecutar(i: dict, pedido: Pedido) -> Resultado | None:
    partes = []
    hecho = _ordenes_directas(i["orden"], i["previa"], i["modelo"]) if i["orden"] else None
    if hecho:
        _ultima.update(t=time.time(), orden=pedido.resuelto, hecho=hecho, dicho=False)
    if i["antes"]:
        partes.append(_contar_antes(i["antes"]))
    if hecho:
        partes.append(f"Ya está hecho, en esta orden (no llames herramientas para lo mismo): {_legible(hecho)} "
                      + ("Responde sobre esto y lo de antes, sin repetir respuestas anteriores. " if i["antes"]
                         else "Responde SOLO sobre esto, sin repetir respuestas anteriores. ")
                      + "Cuéntaselo en pasado (\"¡Listo, ya te abrí...!\"); lo marcado NO SE PUDO díselo tal cual "
                      "y por qué, nunca como hecho. Los lugares (escritorio, pantalla) dilos EXACTAMENTE como aparecen "
                      "aquí; si aquí no dice ningún lugar, no menciones ninguno (no los saques de respuestas anteriores). "
                      "Si pidió algo más que no está en esta "
                      "lista, hazlo con tus herramientas o dile que eso no lo hiciste; nunca digas que hiciste algo "
                      "que no aparece aquí.")
    if i["ver"]:
        partes.append("Ventanas abiertas ahora:\n" + servidor.ventanas_abiertas())
    if not partes:
        return None
    return Resultado("\n\n".join(partes), hizo=bool(hecho), con_notas=True)


def datos(pedido: Pedido) -> str | None:
    """Lo que hizo por la orden anterior y no alcanzó a decir, aunque ahora hable de otra cosa."""
    antes = _antes()
    return _contar_antes(antes) if antes else None
