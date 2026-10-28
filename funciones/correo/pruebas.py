"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "revisa el spam", {"correo"}, []),
    ("", "", "marca como leídos los de la U", {"correo"}, ["de la u"]),
    ("Tienes 3 correos de la UNI sin leer.", "revisa mis correos", "ábrelos", {"correo"}, ["uni"]),
    ("", "", "Puedes revisar el último correo que tengo de la Universidad Nacional.", {"correo"}, ["universidad"]),
    ("", "", "quiero q envies a papelera el de digitl ocean", {"correo"}, ["ocean"]),
    ("", "", "Borra los de VictualOcean y los de Zoom.", {"correo"}, ["zoom"]),
    ("No hay ventanas de DigitalOcean ni de Zoom abiertas.", "Borra los de DigitalOcean y los de Zoom.",
     "Digo los correos.", {"correo"}, ["zoom"]),
    ("Tienes 3 correos sin leer: Google, Zoom y la UNI.", "revisa mis correos", "abrelos, para q aparezcan leidos",
     {"correo"}, []),
    ("Tienes 500 correos en la bandeja.", "marca los correos q tengo como leidos",
     "no no, mala mia, marca los q no estan leidos como leidos", {"correo"}, ["leído"]),
    ("Ya marqué como leídos los del spam.", "solo marcalos como leidos",
     "graciaaas, ahora marca los de la bandeja de recibidos pliz", {"correo"}, []),
    ("El último correo es de la Rectoría UNI, sobre la matrícula.", "revisa el último correo de la U",
     "Dime más de la rectoría.", {"correo"}, ["rector"]),
    # prueba de fuego (MASSIVE): listas no son correo
    ("", "", "olly me lee mis listas", {"charla"}, []),
    ("", "", "eliminar ese artículo", {"charla"}, []),
]

# cadena: router -> entender + el aviso que diría. (la asistente, el usuario antes, el usuario, lo esperado; "aviso" =
# palabra que debe salir en el aviso, "" = que no haya aviso). Nada se ejecuta.
CADENA = [
    ("", "", "revisa el correo de la gaceta universitaria", {"acciones": ["leer"], "varios": False, "aviso": "gaceta"}),
    ("", "", "revisa los correos de la gaceta universitaria", {"acciones": ["ver"], "aviso": "gaceta"}),
    ("Tienes 7 correos de la Gaceta Universitaria UNI.", "revisa los correos de la gaceta universitaria", "sin leer?",
     {"acciones": ["ver"], "solo_sin_leer": True}),
    ("", "", "q dicen los de comunicados uni?", {"acciones": ["leer"], "varios": True, "aviso": "comunicados"}),
    ("", "", "lee los correos de comunicados uni", {"acciones": ["leer"], "varios": True}),
    ("", "", "léeme el de la rectoría", {"acciones": ["leer"], "varios": False, "aviso": "rector"}),
    ("Leí 3 correos de Comunicados UNI: normativas, una comisión y la biblioteca.", "lee los correos de comunicados uni",
     "cuantos leiste?", {"acciones": ["ninguna"], "aviso": ""}),
    ("", "", "holi, puedes revisar q correos sin abrir tengo?", {"acciones": ["ver"], "solo_sin_leer": True, "aviso": "¡"}),
    ("", "", "revisa el spam", {"acciones": ["ver"], "carpeta": "spam", "aviso": "spam"}),
    ("", "", "borra los de unsplash, railway y render", {"acciones": ["papelera"], "aviso": "unsplash"}),
    ("", "", "¿me escribió el profe de cálculo?", {"acciones": ["ver"], "asunto": [], "aviso": "cálculo"}),
    ("", "", "busca el correo que dice matrícula en el asunto", {"acciones": ["ver"], "quienes": [], "aviso": "matrícula"}),
    ("", "", "léeme el de la gira de campo", {"acciones": ["leer"], "quienes": [], "aviso": "gira"}),
    ("", "", "¿me llegó algo sobre el examen de cálculo?", {"acciones": ["ver"], "quienes": [], "aviso": "examen"}),
    ("", "", "busca los correos con asunto alcance", {"acciones": ["ver"], "asunto": ["alcance"]}),
    ("", "", "revisa los de la U que digan beca", {"acciones": ["ver"], "asunto": ["beca"], "aviso": "beca"}),
    ("", "", "ponle estrella al de la beca", {"acciones": ["destacar"], "aviso": "beca"}),
    ("El de GitHub es sobre un proyecto de cálculo que tienes que entregar antes del 16 de noviembre.", "q dice el de github?", "jajajaja, esta bien, me gustó esa respuesta oye, pero creo q el correo era otro jsjsj",
     {"acciones": ["leer"]}),
    ("El de GitHub es sobre un proyecto de cálculo que tienes que entregar antes del 16 de noviembre.", "q dice el de github?", "eso no decía el correo, te lo inventaste", {"acciones": ["leer"]}),
    ("El de GitHub es sobre un proyecto de cálculo que tienes que entregar antes del 16 de noviembre.", "q dice el de github?", "mmm no creo q sea ese, revisalo bien", {"acciones": ["leer"]}),
    ("El de GitHub es sobre un proyecto de cálculo que tienes que entregar antes del 16 de noviembre.", "q dice el de github?", "jajaja me encantó esa respuesta", {"acciones": ["ninguna"]}),
]


def revisar(caso: tuple, i: dict | None, aviso: str) -> tuple[bool, str]:
    esperado, i = caso[3], i or {"acciones": ["ninguna"]}
    malos = {k: i.get(k) for k, v in esperado.items() if k != "aviso" and i.get(k) != v}
    if "aviso" in esperado and (esperado["aviso"] not in aviso.lower() if esperado["aviso"] else aviso):
        malos["aviso"] = aviso
    return not malos, (f"{i['acciones']} {i.get('quienes', [])} {i.get('asunto', [])} «{aviso}»"
                       + (f"  {malos}" if malos else ""))
