"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "qué hora es en barcelona", {"hora_mundo"}, ["barcelona"]),
    ("En Barcelona son las 21:15.", "qué hora es en barcelona", "¿y en Japón?", {"hora_mundo"}, ["jap", "hora"]),
    ("", "", "qué hora es", {"charla"}, []),
    # prueba de fuego (MASSIVE)
    ("", "", "cuál es la temperatura mínima de alicante", {"charla"}, []),
    ("", "", "cual es la tasa de cambio vigente en china", {"charla"}, []),
    ("", "", "cuántas horas de distancia hay entre mi ubicación y madrid", {"hora_mundo"}, []),
    ("", "", "convierte la hora actual de g. m. t. a e. s. t.", {"hora_mundo"}, []),
]
