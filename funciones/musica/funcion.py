"""Música en YouTube Music Desktop App (por su Companion Server; ver musica-mcp/servidormusica.py): poner un género,
canción o artista, sugerir canciones y elegir una ("pon la segunda"), pausar, pasar, volumen y qué está sonando.
Qué quiere lo interpreta el modelo; lo hace Python."""
import re
import time

from funciones import Frases, Pedido, Resultado, mcp
from identidad import nombres

musica = mcp("musica")
google = mcp("google")  # su _parecido, para "la de Queen"

FRASES = Frases({
    "genero": ["Buscando algo de {x}.", "Buscándote algo de {x}.", "Poniendo algo de {x}.",
               "Un momento, buscando {x}.", "Eligiendo algo de {x} para ti."],
    "cancion": ["Buscando {x}.", "Poniendo {x}.", "Un momento, buscando {x}.", "Buscando {x} en YouTube Music.",
                "Poniéndote {x}."],
    "sugerir": ["Buscando canciones{de}.", "Buscándote canciones{de}.", "Mirando qué canciones hay{de}.",
                "Un momento, buscando algunas{de}.", "Eligiendo unas buenas{de}."],
})
# el tema (respaldo sin router); qué quiere hacer lo interpreta el modelo
TEMA = re.compile(r"\b(m[uú]sica|canci[oó]n(es)?|rolas?|temas?|playlist|lista de|reproduc\w*|suena|sonando|"
                    r"pausa\w*|para la m|siguiente|anterior|s[aá]lta\w*|cambia\w*|volumen|s[uú]bel[eo]|b[aá]jal[eo]|"
                    r"g[eé]neros?|artista|[aá]lbum|youtube|reggaet\w*|rock|pop|salsa|bachata|merengue|cumbia|lofi|"
                    r"metal|jazz|rap|trap|electr[oó]nica|cl[aá]sica|baladas?|corridos|banda|anime|vocaloid|pon\w*|play|escuch\w*|o[ií]r|p[aá]sal[ao])\b", re.I)
INTERPRETAR = nombres("""{usuario} le pide a {asistente} algo sobre música (la app YouTube Music de su PC). Interpreta QUÉ quiere aunque
lo diga con otras palabras o mal transcrito. Responde solo el JSON.
accion:
- "genero": poner un género, ambiente o tipo de música ("pon reggaeton", "algo para estudiar", "música triste").
- "cancion": poner una canción concreta ("pon Bohemian Rhapsody", "ponme la de Despacito").
- "artista": poner a un cantante o banda ("pon Bad Bunny", "algo de Queen").
- "sugerir": que le diga canciones sin ponerlas todavía ("¿qué canciones de rock hay?", "recomiéndame algo de salsa").
- "elegir": poner una de las que ya se mencionaron ("pon esa", "la segunda", "la de Don Omar", "esa última").
- "pausa", "seguir" (reanudar / dale play), "siguiente", "anterior", "subir" / "bajar" (volumen), "que_suena" (qué canción es).
- "ninguna": no pide nada de música (abrir o cerrar la app, ventanas, correo, charla) o lo niega.
busqueda: lo que hay que buscar, tal como lo dijo (género, canción, artista), o "".
eleccion: para "elegir": el número ("1", "2", "última") o el nombre que dijo ("la de Don Omar" -> "Don Omar"); "" si dijo solo "esa".
Ejemplos:
"pon algo de reggaeton viejo" -> {"accion":"genero","busqueda":"reggaeton viejo","eleccion":""}
"ponme música para estudiar" -> {"accion":"genero","busqueda":"música para estudiar","eleccion":""}
"pon Bohemian Rhapsody" -> {"accion":"cancion","busqueda":"Bohemian Rhapsody","eleccion":""}
"quiero escuchar a Bad Bunny" -> {"accion":"artista","busqueda":"Bad Bunny","eleccion":""}
"¿qué canciones de rock me recomiendas?" -> {"accion":"sugerir","busqueda":"rock","eleccion":""}
"pon esa" -> {"accion":"elegir","busqueda":"","eleccion":""}
"dale con la tercera" -> {"accion":"elegir","busqueda":"","eleccion":"3"}
"la de Queen" -> {"accion":"elegir","busqueda":"","eleccion":"Queen"}
"pásala" -> {"accion":"siguiente","busqueda":"","eleccion":""}
"pon música" -> {"accion":"seguir","busqueda":"","eleccion":""}
"para la música" -> {"accion":"pausa","busqueda":"","eleccion":""}
"cierra la música" -> {"accion":"ninguna","busqueda":"","eleccion":""}
"bájale un poco" -> {"accion":"bajar","busqueda":"","eleccion":""}
"¿cómo se llama esta canción?" -> {"accion":"que_suena","busqueda":"","eleccion":""}
"abre youtube music" -> {"accion":"ninguna","busqueda":"","eleccion":""}
"abre youtube y pon música" -> {"accion":"seguir","busqueda":"","eleccion":""}
"abre youtube y ponme reggaeton" -> {"accion":"genero","busqueda":"reggaeton","eleccion":""}
"pon discord en el 3" -> {"accion":"ninguna","busqueda":"","eleccion":""}""")
ESQUEMA = {"type": "object", "properties": {
    "accion": {"type": "string", "enum": ["genero", "cancion", "artista", "sugerir", "elegir", "pausa", "seguir",
                                          "siguiente", "anterior", "subir", "bajar", "que_suena", "ninguna"]},
    "busqueda": {"type": "string"}, "eleccion": {"type": "string"}},
    "required": ["accion", "busqueda", "eleccion"]}
# lo último de música: cuándo se habló y las canciones que la asistente sugirió (para "pon esa", "la segunda")
_musica_estado = {"t": 0.0, "sugeridas": []}


def _elegir_cancion(eleccion: str) -> dict | None:
    """"esa", "la segunda", "la de Queen": entre las que sugirió la asistente o, si no, las de la cola de la app."""
    opciones = list(_musica_estado["sugeridas"])
    if not opciones:
        try:
            cola = ((musica.estado().get("player") or {}).get("queue") or {}).get("items") or []
            opciones = [{"videoId": c.get("videoId"), "titulo": c.get("title", ""), "artista": c.get("author", "")}
                        for c in cola if c.get("videoId")]
        except Exception:
            opciones = []
    if not opciones:
        return None
    e = eleccion.strip().lower()
    numeros = {"primera": 1, "segunda": 2, "tercera": 3, "cuarta": 4, "quinta": 5, "última": len(opciones),
               "ultima": len(opciones)}
    n = int(e) if e.isdigit() else numeros.get(e)
    if n:
        return opciones[min(max(n, 1), len(opciones)) - 1]
    if e:
        puntaje = lambda o: max(google._parecido(e, o["artista"], o["titulo"]),
                                google._parecido(e, o["titulo"]))
        mejor = max(opciones, key=puntaje)
        return mejor if puntaje(mejor) >= 0.6 else None
    return opciones[0]  # "pon esa": la primera que mencionó


def _gestionar(intencion: dict) -> str:
    accion, busqueda = intencion["accion"], intencion["busqueda"].strip()
    _musica_estado["t"] = time.time()
    sufijo = " Díselo en una frase, en pasado. No abras ni cierres apps o ventanas por esto."
    if accion in ("genero", "cancion", "artista") and busqueda:
        tipo = {"genero": "listas", "cancion": "canciones", "artista": "artistas"}[accion]
        encontrados = musica.buscar(busqueda, tipo, 1) or musica.buscar(busqueda, "canciones", 1)
        if not encontrados:
            return f"Buscaste \"{busqueda}\" en YouTube Music y no apareció nada; no se puso nada. Díselo."
        _musica_estado["sugeridas"] = []
        return f"Ya está hecho: {musica.poner(encontrados[0])}." + sufijo
    if accion == "sugerir":
        canciones = musica.buscar(busqueda or "éxitos", "canciones", 5)
        _musica_estado["sugeridas"] = canciones
        return ("Canciones que encontraste en YouTube Music (todavía NO suena ninguna):\n"
                + "\n".join(f"{i}. {c['titulo']} de {c['artista']}" for i, c in enumerate(canciones, 1))
                + "\nDíselas en orden (título y artista, cortito) y pregúntale cuál pone.")
    if accion == "elegir":
        elegida = _elegir_cancion(intencion["eleccion"])
        if not elegida:
            return (nombres("{usuario} quiere que pongas una canción de las mencionadas, pero no sabes cuál (no hay lista o no "
                    "coincide). Pregúntale cuál o que te diga el nombre. No se puso nada."))
        return f"Ya está hecho: {musica.poner(elegida)}." + sufijo
    if accion == "que_suena":
        return f"En YouTube Music: {musica.sonando()} Díselo en una frase."
    # "pon música" sin decir qué = seguir con lo que estaba
    nombre = {"pausa": "pause", "seguir": "play", "genero": "play", "cancion": "play", "artista": "play",
              "siguiente": "next", "anterior": "previous", "subir": "volumeUp", "bajar": "volumeDown"}[accion]
    musica.comando(nombre)
    if nombre in ("volumeUp", "volumeDown"):  # un paso es poco: tres
        musica.comando(nombre), musica.comando(nombre)
    hecho = {"pause": "pausada", "play": "sonando otra vez", "next": "pasó a la siguiente",
             "previous": "volvió a la anterior", "volumeUp": "volumen más alto", "volumeDown": "volumen más bajo"}[nombre]
    return f"Ya está hecho: música {hecho}." + sufijo


def aviso(intencion: dict) -> str:
    accion, que = intencion["accion"], intencion["busqueda"].strip()
    if accion == "genero" and que:
        return FRASES.decir("genero", x=que)
    if accion in ("cancion", "artista") and que:
        return FRASES.decir("cancion", x=que)
    if accion == "sugerir":
        return FRASES.decir("sugerir", de=f" de {que}" if que else "")
    return ""  # pausa, volumen, siguiente...: se hacen al instante


def detectar(texto: str) -> bool:
    return bool(TEMA.search(texto))


def entender(pedido: Pedido, modelo) -> dict | None:
    i = modelo(INTERPRETAR, pedido.combinado, ESQUEMA)
    return i if i and i["accion"] != "ninguna" else None


def ejecutar(intencion: dict, pedido: Pedido) -> Resultado:
    return Resultado(_gestionar(intencion), con_notas=True)
