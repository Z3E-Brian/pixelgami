"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "revisa cuánta RAM estoy usando", {"pc"}, []),
    ("Tienes 11,6 GB de RAM usados.", "cuánta ram uso", "¿y cuánto me queda?", {"pc"}, ["ram"]),
    ("", "", "puedes decirme cuánto estás usando tú", {"pc"}, ["tú"]),
    ("", "", "qué tan caliente está la compu", {"pc"}, []),
    ("", "", "usa gigas", {"charla", "pc"}, []),
    ("", "", "puedes revisar cuanta ram estoy usando en este momento?", {"pc"}, []),
    ("", "", "¿Qué está consumiendo la RAM?", {"pc"}, []),
]
