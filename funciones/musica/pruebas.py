"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "pon algo de rock", {"musica"}, ["rock"]),
    ("", "", "abre youtube y pon música", {"musica"}, []),
    ("¿Quieres que ponga música mientras trabajas?", "voy a programar", "va", {"musica"}, ["música"]),
    ("", "", "pásala", {"musica"}, []),
    ("", "", "Abre YouTube y pongo música.", {"musica"}, []),
    ("¿Puedes bajar el volumen?", "", "Bájalo a 5.", {"musica"}, ["5"]),
    ("", "", "Puedes poner cualquier canción.", {"musica"}, []),
    ("", "", "Ok, busca alguna canción de Astro Man, la que quieras.", {"musica"}, ["astro"]),
    ("", "", "¿Puedes buscar una canción de Minecraft de C418?", {"musica"}, ["c418"]),
    ("", "", "Busca Panticorale en YouTube Music.", {"musica"}, []),
    ("", "", "Ponle pausa.", {"musica"}, []),
]
