"""Internet: buscar (SearXNG local o DuckDuckGo), abrir resultados o sitios en el navegador y leer páginas.

La búsqueda la hace Python antes de responder: con la herramienta, Qwen confundía "busca memorias RAM" con buscar en
sus recuerdos y respondía con la RAM del PC. Qué quiere lo interpreta el modelo y _revisar() lo corrige con lo que de
verdad dijo (el modelo a veces abre el navegador sin que lo pida o inventa un sitio).
"""
import asyncio
import json
import re
import subprocess
import time
import types
import urllib.parse
import urllib.request


from funciones import Frases, Pedido, Resultado, log
from identidad import ASISTENTE, PERFIL, nombres

INTERPRETAR = nombres("""{usuario} le habla a {asistente} por voz. Decide si quiere algo de internet. Interpreta la intención, no la
frase literal (Whisper puede escribir mal nombres de sitios: "extreme tech" = extremetech.com).
accion:
- "buscar": quiere que busque algo en internet/la web/Google ("busca memorias RAM en ExtremeTech", "investiga qué
  laptop conviene", "noticias de Hollow Knight Silksong", "cuánto cuesta una RTX 5070"). consulta = qué buscar, en
  palabras clave claras (sin "busca", sin el sitio); sitio = dominio si nombró una página ("extremetech.com",
  "reddit.com", "youtube.com") o ""; navegador = true si además quiere verlo en el navegador ("ábrelo", "muéstramelo",
  "en {navegador}", "pónmelo en pantalla").
- "ir": quiere que le abra una página o sitio tal cual, sin buscar nada en ella ("abre una pestaña con la
  extreme", "llévame a Reddit", "abre la página de Amazon"); sitio = su dominio, consulta = "".
- "abrir": quiere abrir en el navegador uno de los resultados que {asistente} ya encontró ("abre el primero", "ábreme ese",
  "el segundo") o la búsqueda; numero = 1, 2, 3... (0 = la página de la búsqueda).
- "leer": quiere que {asistente} lea y le cuente uno de los resultados ya encontrados ("léelo", "qué dice el primero",
  "cuéntame más del segundo"); numero = cuál (1 si no dice).
tipo: "paginas" (lo normal), "imagenes" (fotos, imágenes, wallpapers, fanart), "videos" (videos, trailers,
tutoriales en video) o "noticias".
{usuario} siempre usa {navegador} y Google: "en {navegador}", "en el navegador", "en Google" es mostrárselo (navegador true),
NUNCA el sitio.
- "ninguna": no es de internet: buscar correos, buscar en sus recuerdos o lo que hablaron, buscar archivos o
  ventanas, abrir apps o juegos ("abre Discord", "abre YouTube"), poner música, charla.
Ejemplos:
"oye, puedes buscar memorias RAM en extremetech?" -> buscar, consulta "memorias RAM", sitio "extremetech.com"
"búscame reseñas de la Ryzen 7 9800X3D y ábrelas" -> buscar, consulta "Ryzen 7 9800X3D review", navegador true
"abre el segundo" (tras una búsqueda) -> abrir, numero 2
"qué dice el primero" -> leer, numero 1
"muéstramelo en {navegador}" / "ábrelo" / "enséñamelo" (tras una búsqueda) -> abrir, numero 1 (el resultado del que hablaba
  {asistente}; 0 si pide ver la búsqueda completa)
"revisa cuánto vale X en extremetech y muéstramelo" -> buscar, sitio "extremetech.com", navegador true
"busca imágenes de 2B en {navegador} y muéstramelas" -> buscar, consulta "2B", tipo "imagenes", sitio "", navegador true
"ponme el trailer de Silksong" -> buscar, consulta "Silksong trailer", tipo "videos", navegador true
"holaa, puedes revisar en cuánto están las RAM de 8GB en extreme y mostrarme?" -> buscar, consulta "RAM 8GB",
  sitio "extremetechcr.com", navegador true
"fíjate cuánto sale un SSD de 1 tera" -> buscar, consulta "precio SSD 1TB"
"consulta en Wikipedia quién inventó el transistor" -> buscar, consulta "inventor del transistor", sitio "wikipedia.org"
"revisa cuánta RAM estoy usando" / "revisa el spam" / "mira las ventanas abiertas" -> ninguna (es de su PC o su correo)
"busca el correo de la U" -> ninguna
"abre YouTube" -> ninguna
Si dice "búscalo", "eso", "lo de antes", toma el tema del mensaje anterior de {usuario} o de la búsqueda anterior.
Si recibes una orden y debajo sus palabras exactas, la acción sale de la orden; las palabras exactas solo dan
detalles (un "dale" o "sí" nunca es lo que hay que buscar).""")
ESQUEMA = {"type": "object", "properties": {
    "accion": {"type": "string", "enum": ["buscar", "ir", "abrir", "leer", "ninguna"]}, "consulta": {"type": "string"},
    "tipo": {"type": "string", "enum": ["paginas", "imagenes", "videos", "noticias"]},
    "sitio": {"type": "string"}, "navegador": {"type": "boolean"}, "numero": {"type": "integer"}},
    "required": ["accion", "consulta", "tipo", "sitio", "navegador", "numero"]}
_web = {"t": 0.0, "consulta": "", "resultados": [], "previo": ""}

FRASES = Frases({
    "web": ["Buscando {x} en {donde}.", "Un momento, buscando {x} en {donde}.", "Mirando qué sale de {x} en {donde}.",
            "Buscando {x} en {donde}, un segundo.", "Revisando {x} en {donde}."],
    "ir": ["Abriendo {x}.", "Llevándote a {x}.", "Un momento, abriendo {x}.", "Abriéndote {x}.",
           "Abriendo {x}, un segundo."],
    "abrir_resultado": ["Abriéndolo.", "Abriendo ese resultado.", "Un momento, abriéndolo.", "Abriendo la página.",
                        "Abriéndotelo."],
    "leer_pagina": ["Leyendo esa página.", "Leyéndola.", "Viendo qué dice.", "Un momento, leyéndola.",
                    "Revisando qué dice esa página."],
})
# "sí", "dale": aceptar lo que ofreció tras una búsqueda
SI = re.compile(r"^\W*(s[ií]|dale|ok|okay|hazlo|claro|va|de una|confirmo|adelante|ya)\b", re.I)
_precios: list | None = None  # los precios de los resultados de este mensaje (None: no preguntó precios)


# cuándo vale la pena preguntarle a Qwen si es de internet: por intención (revisar, mirar, fijarse, precios, tiendas,
# sitios), no por frases ("revisa en cuánto están las RAM en extreme" no decía "busca" y respondió con la RAM del PC)
DISPARA_WEB = re.compile(r"b[uú]sc|b[uú]squeda|investig|googl|internet|\bweb\b|noticia|precio|cuesta|\bvale\b|reseñ|review|"
                         r"revis|\bmir[ae]\b|m[ií]rame|ch[eé]ca|f[ií]jate|consult|averigu|tienda|compr[ae]r|"
                         r"cu[aá]nto (est[aá]n?|sale|salen|anda|andan|cobran)|en cu[aá]nto|\boferta|descuento|"
                         r"\.(com|net|org|cr)\b|amazon|reddit|wikipedia|youtube|aliexpress|newegg|intelec|walmart", re.I)


class _SinCtx:
    async def info(self, *_):
        pass

    async def error(self, mensaje):
        log.warning(f"{ASISTENTE} web: {mensaje}")


def _buscar(consulta: str, cuantos: int = 6, sitio: str = "", noticias: bool = False) -> list:
    """Resultados (title, link, snippet): SearXNG local (Google CSE, Brave, Bing, DuckDuckGo juntos; servicio
    searxng.service en 127.0.0.1:8888) y, si no responde, DuckDuckGo solo."""
    try:
        url = ("http://127.0.0.1:8888/search?format=json&q=" + urllib.parse.quote(consulta)
               + ("&categories=news" if noticias else ""))
        with urllib.request.urlopen(url, timeout=12) as r:
            datos = json.load(r)
        todos = datos.get("results", [])
        # algunos motores ignoran "site:" (salían Xataka y Ram Trucks buscando RAM en la tienda): filtrar
        if sitio:
            del_sitio = [x for x in todos if sitio in urllib.parse.urlparse(x.get("url", "")).netloc]
            todos = del_sitio or todos
        return [types.SimpleNamespace(title=x.get("title", ""), link=x.get("url", ""),
                                      snippet=(x.get("content") or "").replace("\n", " "))
                for x in todos[:cuantos]]
    except Exception as e:
        log.warning(f"{ASISTENTE} web: SearXNG no respondió ({e}), uso DuckDuckGo")
        from duckduckgo_mcp_server.server import DuckDuckGoSearcher
        return asyncio.run(DuckDuckGoSearcher().search(consulta, _SinCtx(), cuantos))


def _abrir_url(url: str) -> None:
    subprocess.Popen(["systemd-run", "--user", "--scope", "--slice=app.slice", "--collect", "-q", "xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# fijo: el usuario siempre usa el navegador predeterminado (xdg-open) y Google; nombrarlos es "muéstramelo", no un sitio
NAVEGADOR_O_BUSCADOR = re.compile(nombres(r"\b(opera( gx)?|{navegador_re}|navegador|chrome|firefox|brave|google)\b"), re.I)
# cómo nombra el usuario sus sitios (dicho a medias o mal transcrito)
SITIOS_USUARIO = [(re.compile(patron, re.I), sitio) for patron, sitio in PERFIL.get("sitios", {}).items()]
# buscador propio de cada tienda: (normal, de más barato a más caro), con {q} = lo que busca
TIENDAS = PERFIL.get("tiendas", {})
BARATO = re.compile(r"barat|econ[oó]mic|menor precio|m[aá]s bajo|precio m[aá]s bajo", re.I)
PIDE_PRECIO = re.compile(r"cu[aá]nto (cuesta|vale|sale|est[aá]n?)|en cu[aá]nto|precios?|barat|econ[oó]mic", re.I)
TRAE_PRECIO = re.compile(r"[₡$€]\s?\d[\d.,]*\d|[₡$€]\s?\d|\d[\d.,]*\s?(mil\s+)?(colones|d[oó]lares|usd|crc|eur)\b", re.I)


def _sobre_precios(texto: str, resultados: list, tienda) -> str:
    """Si pide un precio: decirlo tal cual sale o, si ningún resultado trae uno, que no lo invente (Qwen 8B
    inventaba "unos 1.200 dólares" o rangos "hasta ₡300,000" aunque la instrucción dijera que no inventara nada).
    Los precios reales quedan en _precios para revisar la respuesta (ver _revisor_de_precios)."""
    global _precios
    if not PIDE_PRECIO.search(texto):
        return ""
    _precios = [(re.split(r"\s+[-–»|]\s+", r.title)[0], p.group()) for r in resultados
                         for p in [TRAE_PRECIO.search(r.snippet) or TRAE_PRECIO.search(r.title)] if p]
    if _precios:
        return (" Di solo los precios que aparecen, tal cual y con su producto (₡ son colones); no los conviertas, "
                "no los redondees y no armes rangos con cifras que no estén.")
    return (" Ningún resultado trae el precio: dile que no lo ves en lo que encontraste, sin decir ninguna cifra"
            + (", y ofrécele abrir la tienda para verlo." if tienda else "."))


def palabras_web(t: str) -> set[str]:
    return {w for w in re.findall(r"\w{3,}", t.lower()) if w not in ("site", "extremetechcr", "com", "busca", "abre")}


def _revisar(intencion: dict | None, pedido: Pedido) -> dict | None:
    """Qwen a veces abre el navegador sin que lo pida o inventa un sitio: solo vale lo que el usuario dijo."""
    if not intencion:
        return intencion
    texto = pedido.combinado
    if not re.search(nombres(r"\b([aá]br\w*|m[uo][eé]?str\w*|ens[eé][ñn]\w*|navegador|{navegador_re}|en pantalla|quiero verl\w*|"
                     r"d[eé]jame ver\w*|entr[ae]\w*|ll[eé]v[ae]me|ve a|ir a)"), texto, re.I):
        intencion["navegador"] = False
    # "llévame a lo de ventiladores" cuando lo último buscado era RAM: es una búsqueda nueva, no un resultado viejo
    if intencion["accion"] == "abrir" and intencion["consulta"].strip() and not (
            palabras_web(intencion["consulta"]) & palabras_web(_web["consulta"])):
        intencion.update(accion="buscar", navegador=True)
    if intencion["accion"] == "abrir" and intencion["numero"] == 0 and not re.search(
            r"b[uú]squeda|resultados|todos|la lista", texto, re.I):
        intencion["numero"] = 1  # "muéstramelo" es lo que la asistente acaba de contar, no la lista
    plano = re.sub(r"[^a-z0-9]", "", texto.lower())
    nombre = re.sub(r"[^a-z0-9]", "", re.sub(r"^www\.|\.[a-z.]+$", "", intencion["sitio"].lower().strip()))
    if nombre and nombre[:6] not in plano:  # "extreme" vale por extremetech; un sitio que no nombró, no
        intencion["sitio"] = ""
    if NAVEGADOR_O_BUSCADOR.search(intencion["sitio"]):
        intencion["sitio"] = ""  # "en el navegador / en Google" es dónde mostrarlo, no dónde buscar
    if NAVEGADOR_O_BUSCADOR.search(texto) and intencion["accion"] == "buscar":
        intencion["navegador"] = True
    for patron, sitio in SITIOS_USUARIO:
        if patron.search(texto):
            intencion["sitio"] = sitio
    # un tema que no dijo ni necesitaba del contexto (el router a veces arrastra la búsqueda anterior)
    exactas = pedido.texto
    if (exactas and intencion["accion"] in ("buscar", "abrir") and not pedido.necesita_contexto
            and not (palabras_web(intencion["consulta"]) & palabras_web(exactas))):
        intencion["consulta"] = ""
    # "dale" / "abre el primer resultado" con una búsqueda hecha: abrir ese resultado, no buscar esas palabras
    num = {"primer": 1, "segund": 2, "tercer": 3}
    if intencion["accion"] == "buscar" and _web["resultados"] and (
            (SI.search(intencion["consulta"]) and len(intencion["consulta"].split()) <= 2)
            or re.search(r"resultado|b[uú]squeda", intencion["consulta"], re.I)):
        n = next((v for k, v in num.items() if k in intencion["consulta"].lower()), 1)
        intencion.update(accion="abrir", numero=n, consulta="")
    # nombrar un sitio sin nada que buscar en él es ir a ese sitio ("abre una pestaña con la extreme")
    consulta = re.sub(r"[^a-z0-9]", "", intencion["consulta"].lower())
    nombre_sitio = re.sub(r"[^a-z0-9]", "", re.sub(r"\.[a-z.]+$", "", intencion["sitio"].lower()))
    if intencion["accion"] in ("buscar", "abrir") and intencion["sitio"] and (
            not consulta or consulta in nombre_sitio or nombre_sitio[:6] in consulta and len(consulta) <= len(nombre_sitio) + 4):
        intencion["accion"] = "ir"
    return intencion


def _gestionar(intencion: dict, texto: str = "") -> str:
    from duckduckgo_mcp_server.server import WebContentFetcher
    accion = intencion["accion"]
    if accion == "ir":
        sitio = intencion["sitio"].strip()
        _abrir_url(sitio if sitio.startswith("http") else f"https://{sitio}")
        return f"YA ABRISTE {sitio} en su navegador. Díselo en una frase."
    if accion == "buscar":
        consulta = intencion["consulta"].strip() + (f" site:{intencion['sitio'].strip()}" if intencion["sitio"].strip() else "")
        tipo = intencion.get("tipo", "paginas")
        if tipo in ("imagenes", "videos"):  # la búsqueda por dentro solo trae texto: se abre la de Google/YouTube
            url = ("https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote(consulta) if tipo == "imagenes"
                   else "https://www.youtube.com/results?search_query=" + urllib.parse.quote(intencion["consulta"]))
            _abrir_url(url)
            _web.update(t=time.time(), consulta=consulta, resultados=[])
            donde = "Google Imágenes" if tipo == "imagenes" else "YouTube"
            return (f"YA ABRISTE en su navegador la búsqueda de {donde} de «{intencion['consulta']}». Díselo en una "
                    "frase; tú no ves las imágenes ni los videos, así que no los describas.")
        tienda = TIENDAS.get(intencion["sitio"].strip())
        barato = bool(BARATO.search(texto + " " + intencion["consulta"]))
        resultados = _buscar(consulta, sitio=intencion["sitio"].strip(), noticias=intencion.get("tipo") == "noticias")
        _web.update(t=time.time(), consulta=consulta, resultados=resultados)
        if tienda and (intencion["navegador"] or barato):
            # en una tienda, "muéstramelo / la más barata" = su propio buscador (ordenado por precio si lo pidió);
            # la tienda tiene Cloudflare y por dentro no se lee: los precios solo salen de los resúmenes
            url = tienda[1 if barato else 0].format(q=urllib.parse.quote_plus(intencion["consulta"].strip()))
            _abrir_url(url)
            vistos = "\n".join(f"- {r.title}: {_para_voz(r.snippet[:200])}" for r in resultados[:5])
            return (f"YA ABRISTE en su navegador la búsqueda de «{intencion['consulta']}» en la tienda "
                    f"{intencion['sitio']}" + (", ordenada de la más barata a la más cara" if barato else "")
                    + ". Díselo en una frase." + (f" Lo que dicen los resultados de Google (pueden estar algo "
                    f"desactualizados):\n{vistos}\nSi ahí aparece algún precio, puedes mencionarlo; si no, no inventes "
                    "ninguno." if vistos else " No inventes precios."))
        if not resultados:
            if intencion["navegador"]:
                _abrir_url("https://www.google.com/search?q=" + urllib.parse.quote(consulta))
                return (f"Por dentro no salió nada para «{consulta}», así que le abriste la búsqueda de Google en su "
                        "navegador. Díselo en una frase.")
            if tienda:  # por dentro no salió: que la vea en la tienda
                _abrir_url(tienda[0].format(q=urllib.parse.quote_plus(intencion["consulta"].strip())))
                return (f"Por dentro no salió nada, así que le abriste en su navegador la búsqueda de "
                        f"«{intencion['consulta']}» en {intencion['sitio']}. Díselo en una frase.")
            return f"Buscaste en internet «{consulta}» y no salió nada. Díselo en una frase, sin preguntarle nada."
        if intencion["navegador"]:  # "ábrelo / la pestaña" = el resultado, no la lista de la búsqueda
            _abrir_url(resultados[0].link)
        lista = "\n".join(f"{i}. {r.title} ({urllib.parse.urlparse(r.link).netloc}): {_para_voz(r.snippet[:220])}"
                          for i, r in enumerate(resultados, 1))
        if intencion["navegador"]:
            return (f"Buscaste en internet «{consulta}» y YA ABRISTE en su navegador el primer resultado: "
                    f"«{resultados[0].title}». Resultados reales:\n{lista}\nDile que ya se lo abriste y cuéntale en una o "
                    "dos frases lo que hay. No le preguntes si quiere abrirlo: ya está abierto."
                    + _sobre_precios(texto, resultados, None))
        return (f"Buscaste en internet «{consulta}». Resultados reales:\n{lista}\n"
                "Cuéntale en dos o tres frases lo más útil que encontraste (sin leer direcciones web ni la lista entera) "
                "No inventes nada que no esté en los resultados." + _sobre_precios(texto, resultados, tienda))
    if not _web["resultados"]:
        return nombres("{usuario} pide un resultado de búsqueda, pero no has buscado nada todavía. Pregúntale qué quiere buscar.")
    n = intencion.get("numero", 1)
    if accion == "abrir" and n == 0:
        _abrir_url("https://www.google.com/search?q=" + urllib.parse.quote(_web["consulta"]))  # El usuario usa Google
        return f"Ya abriste en su navegador la búsqueda «{_web['consulta']}». Díselo en una frase."
    r = _web["resultados"][min(max(n, 1), len(_web["resultados"])) - 1]
    _web["t"] = time.time()
    if accion == "abrir":
        _abrir_url(r.link)
        return f"Ya abriste en su navegador: «{r.title}». Díselo en una frase."
    texto = asyncio.run(WebContentFetcher().fetch_and_parse(r.link, _SinCtx()))
    return (f"Leíste la página «{r.title}». Su contenido (recortado):\n{texto[:3500]}\n"
            "Cuéntale lo importante en tres a cinco frases, con tus palabras. No inventes nada que no esté ahí.")


def _para_voz(texto: str) -> str:
    """Resumen de un resultado como se dice en voz alta ("₡269,900 I.V.A.I." -> "₡269,900 IVA incluido")."""
    return re.sub(r"\bI\.?\s?V\.?\s?A\.?\s?I\b\.?", "IVA incluido", texto)



def aviso(intencion: dict) -> str:
    accion, que = intencion["accion"], intencion["consulta"].strip()
    sitio = re.sub(r"^www\.|\.(com|net|org|co|cr|es)(\.\w\w)?$", "", intencion["sitio"].strip())  # se dice en voz
    sitio = {"extremetechcr": "ExtremeTech"}.get(sitio.lower(), sitio)
    if accion == "buscar" and que:
        tipo = {"imagenes": "imágenes de ", "videos": "videos de ", "noticias": "noticias de "}.get(intencion["tipo"], "")
        return FRASES.decir("web", x=tipo + que, donde=sitio or "internet")
    if accion == "ir" and (sitio or que):
        return FRASES.decir("ir", x=sitio or que)
    if accion == "abrir":
        return FRASES.decir("abrir_resultado")
    if accion == "leer":
        return FRASES.decir("leer_pagina")
    return ""




# ---------- el contrato (ver funciones/__init__.py) ----------

INTERNET = re.compile(r"internet|google|precio|noticia|reddit|p[aá]gina|tienda|extreme|wikipedia|amazon", re.I)


def regla(texto: str, orden: str, temas: list[str]) -> bool | None:
    """"abre YouTube y pon música" es la app de música, no una búsqueda en internet."""
    if "musica" in temas and "web" in temas and not INTERNET.search(orden):
        return False
    return None


def detectar(texto: str) -> bool:
    return bool(DISPARA_WEB.search(texto)) or any(p.search(texto) for p, _ in SITIOS_USUARIO)


def para_el_router() -> str | None:
    """Para entender "ábrelo", "¿y en Reddit?" o "dale" después de una búsqueda."""
    if not (_web["consulta"] and _web["resultados"]):
        return None
    return (f"Última búsqueda de {ASISTENTE} en internet: «{_web['consulta']}» (primer resultado: "
            f"«{_web['resultados'][0].title}»)")


def entender(pedido: Pedido, modelo) -> dict | None:
    i = _revisar(modelo(INTERPRETAR, pedido.combinado, ESQUEMA), pedido)
    return i if i and i["accion"] != "ninguna" else None


def ejecutar(intencion: dict, pedido: Pedido) -> Resultado:
    global _precios
    _precios = None
    contexto = _gestionar(intencion, pedido.combinado)
    return Resultado(contexto, revisar_frase=_revisor_de_precios(_precios) if _precios is not None else None)


def _revisor_de_precios(precios: list[tuple[str, str]]):
    """Revisa cada frase de la respuesta: si da un precio que no salió en los resultados, lo que se dice en su lugar."""
    reales = {_cifra(p) for _, p in precios}
    en_lugar = ("En lo que encontré: " + "; ".join(f"{t}, {p}" for t, p in precios[:3]) + "."
                if precios else "No veo el precio en lo que encontré.")

    def revisar(frase: str) -> str | None:
        inventado = any(_cifra(m.group()) not in reales for m in TRAE_PRECIO.finditer(frase))
        return en_lugar if inventado else None
    return revisar


def _cifra(precio: str) -> str:
    return re.sub(r"\D", "", precio)
