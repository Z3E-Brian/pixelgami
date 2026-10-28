"""Pruebas del intérprete de fechas (fechas.py). Sin modelo, sin red, sin tocar los guardados:
    python3 -m unittest funciones.recordatorios.test_fechas
Todas con el mismo "ahora": miércoles 28 de octubre de 2026, 14:20.
"""
import datetime
import unittest

from funciones.recordatorios import avisos
from funciones.recordatorios import fechas as R

AHORA = datetime.datetime(2026, 10, 28, 14, 20)
D = datetime.datetime
TODOS = list(range(7))

# (frase, texto esperado, cuándo esperado, repetir esperado)
CASOS = [
    ("mañana 3pm entregar lo de Proyectos", "Entregar lo de Proyectos", D(2026, 10, 29, 15, 0), None),
    ("recuérdame mañana a las 3 que tengo que entregar lo de Proyectos", "Entregar lo de Proyectos",
     D(2026, 10, 29, 15, 0), None),
    ("en 20 minutos sacar la ropa", "Sacar la ropa", D(2026, 10, 28, 14, 40), None),
    ("en media hora llamar a mi mamá", "Llamar a mi mamá", D(2026, 10, 28, 14, 50), None),
    ("en 1 hora y media salir", "Salir", D(2026, 10, 28, 15, 50), None),
    ("el viernes a las 10 reunión con Saray", "Reunión con Saray", D(2026, 10, 30, 10, 0), None),
    ("hoy a las 9 de la noche estudiar cálculo", "Estudiar cálculo", D(2026, 10, 28, 21, 0), None),
    ("esta noche ver el partido", "Ver el partido", D(2026, 10, 28, 20, 0), None),
    ("pasado mañana en la mañana revisar correo", "Revisar correo", D(2026, 10, 30, 8, 0), None),
    ("mañana en la mañana ir al banco", "Ir al banco", D(2026, 10, 29, 8, 0), None),
    ("a las 5 sacar la basura", "Sacar la basura", D(2026, 10, 28, 17, 0), None),
    ("a las 12 almorzar", "Almorzar", D(2026, 10, 29, 12, 0), None),  # ya pasó hoy: mañana
    ("15:30 llamar al profe", "Llamar al profe", D(2026, 10, 28, 15, 30), None),
    ("a las 3:30 llamar", "Llamar", D(2026, 10, 28, 15, 30), None),
    ("a las tres llamar", "Llamar", D(2026, 10, 28, 15, 0), None),
    ("a la una y media almorzar", "Almorzar", D(2026, 10, 29, 13, 30), None),
    ("el domingo 4 y media lavar el carro", "Lavar el carro", D(2026, 11, 1, 16, 30), None),
    ("el 5 de noviembre examen de globales", "Examen de globales", D(2026, 11, 5, 8, 0), None),
    ("el 2/11 cita médico", "Cita médico", D(2026, 11, 2, 8, 0), None),
    ("apunta una cita para el primero de noviembre", "Una cita", D(2026, 11, 1, 8, 0), None),
    ("el 1ro de diciembre pagar luz", "Pagar luz", D(2026, 12, 1, 8, 0), None),
    ("el 30 a las 2 entregar informe", "Entregar informe", D(2026, 10, 30, 14, 0), None),
    ("avísame el lunes q tengo reunión", "Tengo reunión", D(2026, 11, 2, 8, 0), None),
    ("agéndame en el calendario el dentista el viernes a las 10", "Dentista", D(2026, 10, 30, 10, 0), None),
    ("todos los lunes 7am gym", "Gym", D(2026, 11, 2, 7, 0), {"dias": [0]}),
    ("los martes a las 8 clase de PPS", "Clase de PPS", D(2026, 11, 3, 8, 0), {"dias": [1]}),
    # hoy es miércoles y las 18:00 no han pasado: la primera es hoy
    ("lunes y miércoles a las 6 de la tarde inglés", "Inglés", D(2026, 10, 28, 18, 0), {"dias": [0, 2]}),
    ("todos los días a las 10 pm tomar pastilla", "Tomar pastilla", D(2026, 10, 28, 22, 0), {"dias": TODOS}),
    ("entre semana 7:15 alarma bus", "Alarma bus", D(2026, 10, 29, 7, 15), {"dias": [0, 1, 2, 3, 4]}),
    ("cada mes el 1 pagar internet", "Pagar internet", D(2026, 11, 1, 8, 0), {"mes": 1}),
    ("el quince de cada mes pagar tarjeta", "Pagar tarjeta", D(2026, 11, 15, 8, 0), {"mes": 15}),
    # horas con palabras o pegadas al momento del día (lo ya entendido no se vuelve a leer)
    ("tres y media llamar", "Llamar", D(2026, 10, 28, 15, 30), None),
    ("mañana a las tres y media llamar", "Llamar", D(2026, 10, 29, 15, 30), None),
    ("el viernes 3 y media de la mañana correr", "Correr", D(2026, 10, 30, 3, 30), None),
    ("cuatro de la tarde reunión", "Reunión", D(2026, 10, 28, 16, 0), None),
    ("a las 3 de la tarde dentista", "Dentista", D(2026, 10, 28, 15, 0), None),
    ("tomar la pastilla a las 3 y media", "Tomar la pastilla", D(2026, 10, 28, 15, 30), None),
    ("en tres días pagar", "Pagar", D(2026, 10, 31, 8, 0), None),
    ("en 2 semanas a las 10 revisión", "Revisión", D(2026, 11, 11, 10, 0), None),
]
ERRORES = [("comprar pan", "cuándo"), ("mañana", "Qué")]


class Interpretar(unittest.TestCase):
    def test_casos(self):
        for frase, texto, cuando, repetir in CASOS:
            with self.subTest(frase=frase):
                r = R.interpretar(frase, AHORA)
                self.assertNotIn("error", r, r.get("error"))
                self.assertEqual((r["texto"], r["cuando"], r["repetir"]), (texto, cuando, repetir))

    def test_errores(self):
        for frase, pista in ERRORES:
            with self.subTest(frase=frase):
                self.assertIn(pista, R.interpretar(frase, AHORA).get("error", ""))

    def test_con_hora(self):
        self.assertTrue(R.interpretar("mañana a las 3 x", AHORA)["con_hora"])
        self.assertTrue(R.interpretar("en 10 min x", AHORA)["con_hora"])
        self.assertFalse(R.interpretar("el viernes x", AHORA)["con_hora"])
        self.assertFalse(R.interpretar("el viernes x todo el día", AHORA)["con_hora"])

    def test_siguiente_repetido(self):
        # día 31 en un mes de 30: salta al próximo mes que lo tenga
        self.assertEqual(R.siguiente({"mes": 31}, datetime.time(8), D(2026, 11, 1)), D(2026, 12, 31, 8, 0))
        self.assertEqual(R.siguiente({"dias": [4]}, datetime.time(9), D(2026, 10, 30, 9, 0)), D(2026, 11, 6, 9, 0))

    def test_describir_todo_el_dia(self):
        domingo = D(2026, 11, 1)
        self.assertEqual(R.describir(domingo, ahora=AHORA, todo_el_dia=True), "el domingo (todo el día)")
        self.assertEqual(R.describir(D(2026, 10, 28), ahora=AHORA, todo_el_dia=True), "hoy (todo el día)")
        self.assertEqual(R.describir(D(2026, 11, 1, 15), ahora=AHORA), "el domingo a las 15:00")

    def test_a_ti(self):
        self.assertEqual(avisos.a_ti("tengo que llamar a mi mamá"), "tienes que llamar a tu mamá")


if __name__ == "__main__":
    unittest.main()
