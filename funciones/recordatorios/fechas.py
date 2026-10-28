"""Fechas en español para los recordatorios: «mañana 3pm entregar X» -> qué, cuándo y si se repite.

Sin efectos: no guarda ni avisa nada (eso es avisos.py). Entiende mañana / pasado mañana / el lunes / el 5 de nov /
2/11 / el primero; a las 3 (de la tarde, salvo "de la mañana"), 15:30, "7:15" escrito así, a las tres y media;
en 20 min / media hora; todos los días / lunes y miércoles / entre semana / el 1 de cada mes.
Pruebas: python3 -m unittest funciones.recordatorios.test_fechas
"""
import datetime
import math
import re

from identidad import ASISTENTE

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_PLANO = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
_MES_RE = r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*"
_MES_NUM = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
            "oct": 10, "nov": 11, "dic": 12}
_NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
            "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
            "treinta": 30, "cuarenta": 40, "media": 0.5, "un par de": 2}
_NUM = r"(\d+|un par de|una|un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|treinta|cuarenta|media)"
_DIA_RE = r"(lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)"


# ---------- entender la frase ----------

def plano(t: str) -> str:
    """Minúsculas sin tildes, con el MISMO largo que el original (los cortes se hacen sobre el original)."""
    return t.lower().translate(str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunaeiouun"))


def _num(s: str) -> float:
    return float(s) if s.isdigit() else _NUMEROS.get(s, 1)


def _dia_num(s: str) -> int:
    return DIAS_PLANO.index(s.rstrip("s") if s.startswith(("sabado", "domingo")) else s)


_DIA_PALABRA = {"primero": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
                "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
                "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
                "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
                "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "treinta y uno": 31}


def _numeros_en_cifras(t: str) -> str:
    """Días y horas dichos con palabras, a cifras, solo donde no hay duda de que son eso:
    «el primero de noviembre» -> «el 1 de noviembre», «1ro/1°» -> «1», «el quince de cada mes» -> «el 15 de...»,
    «a las tres» / «tres y media» / «tres de la tarde» -> «3 ...». No toca «dos horas» ni «en tres días»."""
    t = re.sub(r"\b(\d{1,2})\s*(ro|ero|°|º)\b", r"\1", t, flags=re.I)
    palabras = "|".join(sorted(_DIA_PALABRA, key=len, reverse=True))
    t = re.sub(rf"\b(el|d[ií]a)\s+({palabras})\b", lambda m: f"{m.group(1)} {_DIA_PALABRA[plano(m.group(2))]}", t,
               flags=re.I)
    t = re.sub(rf"\b({palabras})(?=\s+de\s+({_MES_RE}|cada mes))",
               lambda m: str(_DIA_PALABRA[plano(m.group(1))]), t, flags=re.I)
    # horas: tras «a las…» o antes de «y media», «de la tarde», «pm»…
    horas = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
             "diez": 10, "once": 11, "doce": 12}
    nombres = "|".join(horas)
    t = re.sub(rf"\b(a las|a la|para las|como a las|tipo|sobre las)\s+({nombres})\b",
               lambda m: f"{m.group(1)} {horas[m.group(2).lower()]}", t, flags=re.I)
    return re.sub(rf"\b({nombres})(?=\s+(y media|y cuarto|menos cuarto|en punto|de la (ma[nñ]ana|tarde|noche|madrugada)"
                  r"|am\b|pm\b|a\.m|p\.m))", lambda m: str(horas[m.group(1).lower()]), t, flags=re.I)


def interpretar(frase: str, ahora: datetime.datetime | None = None) -> dict:
    """{"texto", "cuando" (datetime), "repetir" (None | {"dias": [0-6]} | {"mes": día})} o {"error": "..."}."""
    ahora = (ahora or datetime.datetime.now()).replace(second=0, microsecond=0)
    t = " " + _numeros_en_cifras(frase.strip()) + " "
    original = plano(t)
    entendido = [False] * len(t)  # letra por letra: lo que ya se usó como fecha u hora (no es parte del qué)
    tapados = {}  # match -> las posiciones que tapó (para soltarlo)
    p = original  # lo que falta entender: lo entendido va tapado con espacios

    def buscar(patron):
        """Busca en lo que todavía no se entendió y lo tapa, para que nada lo lea dos veces
        (el «mañana» de «3 de la mañana» no puede ser además la fecha)."""
        nonlocal p
        m = re.search(patron, p)
        if m:
            tapados[m] = [i for i in range(*m.span()) if not entendido[i] and not p[i].isspace()]
            for i in tapados[m]:
                entendido[i] = True
            p = "".join(" " if e else c for c, e in zip(original, entendido))
        return m

    def soltar(m):
        """Deshace un buscar() que al final no correspondía."""
        nonlocal p
        for i in tapados.pop(m):
            entendido[i] = False
        p = "".join(" " if e else c for c, e in zip(original, entendido))

    buscar(rf"^\s*(oye\s+)?({re.escape(plano(ASISTENTE))}[, ]+)?((puedes|podrias|quiero que|quisiera que|ocupo que|necesito que|porfa|"
           r"por favor)\s+)*(me\s+)?(recuerdame|recordarme|recuerdes|recordar|avisame|avisarme|avises|acuerdame|"
           r"recordatorio:?|me recuerdas|me avisas|no me dejes olvidar|(ponme|pon|crea|crear|agrega) un recordatorio"
           r"( para| de)?|ap[uú]nta(me|lo)?|an[oó]ta(me|lo)?|ag[eé]nda(me|lo)?|gu[aá]rda(me|lo)?|crea un evento"
           r"( para| de)?)( en (el|mi) (calendario|agenda))?\s+(de\s+|que\s+|para\s+)?")

    fecha = hora = None
    minuto = 0
    periodo = None  # "am" / "pm" de "de la mañana / tarde / noche"
    repetir = None
    relativo = None

    buscar(r"\b(todo el dia|el dia entero|dia entero|sin hora)\b")  # para el calendario; aquí no cambia nada

    # periodo del día (antes que "mañana" como fecha: "mañana en la mañana")
    m = buscar(r"\b((a las |a la |como a las |tipo )?(\d{1,2})(:(\d{2})|\s+y media|\s+y cuarto)?\s+)?"
               r"(de|en|por) la (manana|tarde|noche|madrugada)\b")
    if m:
        periodo = m.group(7)
        if m.group(3):  # la hora iba pegada: «4 de la tarde», «3 y media de la mañana»
            hora = int(m.group(3))
            minuto = int(m.group(5)) if m.group(5) else 30 if "media" in (m.group(4) or "") else \
                15 if "cuarto" in (m.group(4) or "") else 0
    m = buscar(r"\b(esta) (manana|tarde|noche)\b")
    if m:
        fecha, periodo = ahora.date(), m.group(2)

    # repetidos
    m = buscar(r"\b(todos los dias|todas las (mananas|tardes|noches)|cada dia|a diario|diariamente|diario)\b")
    if m:
        repetir = {"dias": list(range(7))}
        if m.group(2):  # "todas las tardes" -> la tarde
            periodo = m.group(2)[:-1] if m.group(2) != "mananas" else "manana"
    elif buscar(r"\b(entre semana|de lunes a viernes|dias de semana)\b"):
        repetir = {"dias": [0, 1, 2, 3, 4]}
    elif buscar(r"\b(cada|todos los|los) fines? de semana\b"):
        repetir = {"dias": [5, 6]}
    else:
        # "todos los lunes", "cada viernes", "los sábados", "lunes y miércoles" (varios días = se repite)
        m = buscar(rf"\b((todos los|cada|los) )?{_DIA_RE}((\s*,\s*|\s+y\s+)(los\s+)?{_DIA_RE})*\b")
        if m and (m.group(2) in ("todos los", "cada") or re.search(r"\by\b|,", m.group(0))
                  or (m.group(2) == "los" and re.search(r"(lunes|martes|miercoles|jueves|viernes|s)$", m.group(3)))):
            repetir = {"dias": sorted({_dia_num(d) for d in re.findall(_DIA_RE, m.group(0))})}
        elif m:
            soltar(m)
        m = buscar(r"\b(el (dia )?(\d{1,2}) de cada mes|cada mes(,? el (dia )?(\d{1,2}))?|todos los meses(,? el (dia )?(\d{1,2}))?|mensual(mente)?)\b")
        if m:
            repetir = {"mes": int(m.group(3) or m.group(6) or m.group(9) or ahora.day)}
        if not m:
            m = buscar(r"\b(cada semana|semanal(mente)?)\b")
            if m:
                repetir = {"dias": [ahora.weekday()]}

    # relativo: "en 20 minutos", "en media hora", "en 2 horas", "en 3 días"
    m = buscar(rf"\b(en|dentro de) {_NUM}\s*(minutos?|mins?|horas?|hrs?|h|dias?|semanas?)\b(\s+y media)?")
    if m:
        n = _num(m.group(2)) + (0.5 if m.group(4) else 0)
        u = m.group(3)
        if u.startswith(("dia", "sem")):  # «en 3 días» es una fecha: a las 8:00 o a la hora que diga, como «el sábado»
            fecha = ahora.date() + datetime.timedelta(days=int(n * (7 if u.startswith("sem") else 1)))
        else:
            relativo = datetime.timedelta(minutes=n) if u.startswith("min") else datetime.timedelta(hours=n)
    elif buscar(r"\b(en|dentro de) media hora\b"):
        relativo = datetime.timedelta(minutes=30)
    elif buscar(r"\b(en|dentro de) un rato\b"):
        relativo = datetime.timedelta(minutes=30)

    # fecha
    if fecha is None and not repetir:
        if buscar(r"\bpasado manana\b"):
            fecha = ahora.date() + datetime.timedelta(days=2)
        elif buscar(r"\bmanana\b"):
            fecha = ahora.date() + datetime.timedelta(days=1)
        elif buscar(r"\bhoy\b"):
            fecha = ahora.date()
        else:
            m = buscar(rf"\b(el |este |el proximo |el otro |proximo )?{_DIA_RE}( que viene)?\b")
            if m:
                d = _dia_num(m.group(2))
                dif = (d - ahora.weekday()) % 7
                if dif == 0 and (m.group(1) or "").strip() != "este":
                    dif = 7
                if (m.group(1) or "").strip() == "el otro":
                    dif += 7
                fecha = ahora.date() + datetime.timedelta(days=dif)
            m = buscar(rf"\b(el )?(dia )?(?P<dia>\d{{1,2}})( de (?P<mes>{_MES_RE})|/(?P<mesn>\d{{1,2}}))"
                       rf"(( de)? (?P<anio>\d{{4}}))?\b") or \
                buscar(r"\bel (dia )?(?P<dia>\d{1,2})\b(?!\s*(:|am|pm|a\.m|p\.m|h\b|de la|minutos?|horas?|y media|y cuarto))")
            if m:
                g = m.groupdict()
                dia, anio = int(g["dia"]), int(g["anio"]) if g.get("anio") else ahora.year
                con_mes = bool(g.get("mes") or g.get("mesn"))
                mes = int(g["mesn"]) if g.get("mesn") else _MES_NUM[g["mes"][:3]] if g.get("mes") else ahora.month
                try:
                    fecha = datetime.date(anio, mes, dia)
                    if fecha < ahora.date() and not g.get("anio"):  # ya pasó: el año o el mes que viene
                        fecha = datetime.date(anio + 1, mes, dia) if con_mes else \
                            datetime.date(anio + (mes == 12), mes % 12 + 1, dia)
                except ValueError:
                    return {"error": "Esa fecha no existe."}

    # hora (si no venía pegada al periodo)
    literal = False  # "7:15" escrito así es esa hora; "a las 3:30" sí puede ser de la tarde
    ampm = None
    m = None if hora is not None else \
        buscar(r"\b(a las |a la |alas |para las |tipo |como a las |sobre las )?(\d{1,2})(:|\.|h)(\d{2})\s*(am|pm|a\.m\.?|p\.m\.?)?")
    if m:
        hora, minuto, ampm = int(m.group(2)), int(m.group(4)), m.group(5)
        literal = not m.group(1)
    elif hora is None:
        m = buscar(r"\b(a las |a la |alas |para las |tipo |como a las |sobre las )(\d{1,2})(\s+y media|\s+y cuarto|\s+menos cuarto)?\s*(am|pm|a\.m\.?|p\.m\.?|hrs?)?\b") or \
            buscar(r"\b(\s?)(\d{1,2})(\s+y media|\s+y cuarto)?\s*(am|pm|a\.m\.?|p\.m\.?)") or \
            buscar(r"\b(\s?)(\d{1,2})(\s+y media|\s+y cuarto)()\b")
        if m:
            hora, ampm = int(m.group(2)), m.group(4)
            extra = (m.group(3) or "").strip()
            minuto = 30 if extra == "y media" else 15 if extra == "y cuarto" else 45 if extra == "menos cuarto" else 0
            if extra == "menos cuarto":
                hora -= 1
        else:
            if buscar(r"\b(al |a )?mediodia\b"):
                hora = 12
            elif buscar(r"\b(a )?medianoche\b"):
                hora = 0
    if hora is not None:
        if hora > 23 or minuto > 59:
            return {"error": "Esa hora no existe."}
        ampm = (ampm or "").replace(".", "")
        if ampm == "pm" and hora < 12:
            hora += 12
        elif ampm == "am" and hora == 12:
            hora = 0
        elif not ampm.startswith(("am", "pm")) and hora < 12:
            if periodo in ("tarde", "noche"):
                hora += 12
            elif periodo not in ("manana", "madrugada") and 1 <= hora <= 7 and not literal:
                hora += 12  # "a las 3" = de la tarde
    elif periodo and not relativo:
        hora = {"manana": 8, "tarde": 15, "noche": 20, "madrugada": 5}[periodo]

    # lo que queda es el qué
    texto = re.sub(r"\s+", " ", "".join(" " if e else c for c, e in zip(t, entendido))).strip(" ,.:;-")
    conectores = r"(que|q|de|a|para|el|la|las|y|tengo que|hay que|en|por favor|pliz|porfa)"
    texto = re.sub(rf"^({conectores}\b\s*)+", "", texto, flags=re.I)
    texto = re.sub(rf"(\s*\b{conectores})+$", "", texto, flags=re.I).strip(" ,.:;-")
    if not texto:
        return {"error": "¿Qué te recuerdo?"}

    if relativo:
        cuando = ahora + relativo
    elif repetir:
        h = datetime.time(hora if hora is not None else 8, minuto)
        cuando = siguiente(repetir, h, ahora - datetime.timedelta(minutes=1))
    elif fecha or hora is not None:
        cuando = datetime.datetime.combine(fecha or ahora.date(), datetime.time(hora if hora is not None else 8, minuto))
        if not fecha and cuando <= ahora:
            cuando += datetime.timedelta(days=1)
        if cuando <= ahora:
            return {"error": "Esa hora ya pasó."}
    else:
        return {"error": "¿Para cuándo? (ej. «mañana 3pm», «en 20 min», «todos los lunes 7am»)"}
    return {"texto": texto[0].upper() + texto[1:], "cuando": cuando, "repetir": repetir,
            "con_hora": hora is not None or relativo is not None}


def siguiente(repetir: dict, hora: datetime.time, despues: datetime.datetime) -> datetime.datetime:
    """La primera vez que toca después de `despues`."""
    if "dias" in repetir:
        for i in range(8):
            d = despues.date() + datetime.timedelta(days=i)
            c = datetime.datetime.combine(d, hora)
            if d.weekday() in repetir["dias"] and c > despues:
                return c
    anio, mes = despues.year, despues.month
    for _ in range(14):
        try:
            c = datetime.datetime.combine(datetime.date(anio, mes, repetir["mes"]), hora)
            if c > despues:
                return c
        except ValueError:  # día 31 en un mes de 30
            pass
        anio, mes = anio + (mes == 12), mes % 12 + 1
    raise ValueError("no encontré la siguiente fecha")


def describir(cuando: datetime.datetime, repetir: dict | None = None, ahora: datetime.datetime | None = None,
              todo_el_dia: bool = False) -> str:
    """«mañana a las 15:00», «todos los lunes a las 07:00», «el viernes 6 de noviembre a las 08:00», «el domingo
    (todo el día)»."""
    ahora = ahora or datetime.datetime.now()
    if todo_el_dia:
        hora = "(todo el día)"
    else:
        hora = f"a las {cuando:%H:%M}" if cuando.hour != 1 else f"a la {cuando:%H:%M}"
    if repetir and "mes" in repetir:
        return f"el {repetir['mes']} de cada mes {hora}"
    if repetir:
        dias = repetir["dias"]
        if len(dias) == 7:
            return f"todos los días {hora}"
        if dias == [0, 1, 2, 3, 4]:
            return f"entre semana {hora}"
        if dias == [5, 6]:
            return f"los fines de semana {hora}"
        nombres = [DIAS[d] for d in dias]
        return f"todos los {', '.join(nombres[:-1]) + ' y ' + nombres[-1] if len(nombres) > 1 else nombres[0]} {hora}"
    dif = (cuando.date() - ahora.date()).days
    if dif == 0:
        if not todo_el_dia and cuando - ahora < datetime.timedelta(hours=1):
            return f"en {max(1, math.ceil((cuando - ahora).total_seconds() / 60))} min ({cuando:%H:%M})"
        return f"hoy {hora}"
    if dif == 1:
        return f"mañana {hora}"
    if dif < 7:
        return f"el {DIAS[cuando.weekday()]} {hora}"
    return f"el {DIAS[cuando.weekday()]} {cuando.day} de {MESES[cuando.month - 1]} {hora}"
