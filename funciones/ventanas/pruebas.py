"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden)
ROUTER = [
    ("", "", "abre discord en la otra pantalla", {"ventanas"}, ["discord"]),
    ("", "", "abre discord en la otra pantalla y pon algo de phonk", {"ventanas", "musica"}, ["discord"]),
    ("Listo, te abrí VS Code en el escritorio 9.", "abre vs code en el 9", "ok, ciérralo", {"ventanas"}, ["vs code"]),
    ("", "", "qué ventanas tengo abiertas", {"ventanas"}, []),
    ("", "", "puedes abrir Steam.", {"ventanas"}, ["steam"]),
    ("", "", "Quiero que muevas la ventana actual a mi pantalla secundaria.", {"ventanas"}, []),
    ("", "", "Puedes cerrar Discord y abrir VS Code en esa misma pestaña.", {"ventanas"}, ["discord"]),
    ("Listo, te abrí VS Code en el escritorio 9.", "Abre VS Code en el workspace 9", "Sierra, el VS Code.",
     {"ventanas"}, ["cierra", "code"]),
    ("", "", "Oye, Sierra, VS Code, por favor.", {"ventanas"}, ["code"]),
    ("No encontré la aplicación WhatsApp.", "puedes abrir whatsapp", "No, abre. Guatzi, es lo mismo.",
     {"ventanas"}, ["whatsapp"]),
    ("", "", "Allá puedes abrir el WhatsApp en mi pantalla secundaria y el escritorio de archivos en el workspace 3",
     {"ventanas"}, ["whatsapp"]),
    ("", "", "Abre también Discord en la pestaña 4.", {"ventanas"}, ["discord", "4"]),
    ("", "", "Mueve la aplicación de YouTube Music a la ventana secreta.", {"ventanas"}, []),
    # prueba de fuego (MASSIVE): aparatos que no son ventanas
    ("", "", "enciende la aspiradora", {"charla"}, []),
    ("", "", "por favor apaga las luces", {"charla"}, []),
    ("", "", "aumenta el volumen del altavoz", {"charla"}, []),
]
