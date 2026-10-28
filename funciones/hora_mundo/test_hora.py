"""Pruebas sin modelo: el modelo se reemplaza por respuestas fijas.
    python3 -m unittest funciones.hora_mundo.test_hora
"""
import datetime
import unittest
import zoneinfo

from funciones import Pedido
from funciones.hora_mundo import funcion as F

# miércoles 21 de octubre de 2026, 13:15 en Ciudad de México (UTC-6)
AQUI = datetime.datetime(2026, 10, 21, 13, 15, tzinfo=zoneinfo.ZoneInfo("America/Mexico_City"))


def pedido(texto):
    return Pedido(texto, texto, texto, AQUI)


def modelo(*lugares):
    return lambda _s, _t, _e: {"lugares": [{"lugar": l, "zona": z} for l, z in lugares]}


class Hora(unittest.TestCase):
    def test_hora_en(self):
        self.assertEqual(F.hora_en("Barcelona", "Europe/Madrid", AQUI),
                         f"Hora actual en Barcelona: 21:15 del miércoles 21 de octubre (8 h más que en {F.LUGAR})")
        self.assertIsNone(F.hora_en("Atlantis", "Mar/Atlantis", AQUI))

    def test_entender_quita_la_de_aqui(self):
        self.assertIsNone(F.entender(pedido("qué hora es"), modelo(("aquí", "America/Lima"))))
        self.assertIsNone(F.entender(pedido("qué hora es"), modelo()))
        self.assertEqual(F.entender(pedido("y en Japón?"), modelo(("Japón", "Asia/Tokyo"))),
                         [{"lugar": "Japón", "zona": "Asia/Tokyo"}])

    def test_ejecutar(self):
        r = F.ejecutar([{"lugar": "Japón", "zona": "Asia/Tokyo"}], pedido("qué hora es en Japón"))
        self.assertIn("Hora actual en Japón: 04:15 del jueves 22 de octubre", r.contexto)
        self.assertIsNone(F.ejecutar([{"lugar": "Atlantis", "zona": "Mar/Atlantis"}], pedido("x")))

    def test_regla(self):
        self.assertFalse(F.regla("qué hora es", "qué hora es", ["hora_mundo"]))
        self.assertIsNone(F.regla("qué hora es en Japón", "", ["hora_mundo"]))
        self.assertIsNone(F.regla("¿y en Japón?", "qué hora es en Japón", ["hora_mundo"]))  # sigue la conversación

    def test_regla_lo_que_no_es_la_hora(self):
        self.assertFalse(F.regla("cuál es la temperatura mínima de alicante", "dime la temperatura de Alicante", []))
        self.assertFalse(F.regla("ha aumentado la tasa del dólar", "dime la tasa del dólar", ["hora_mundo"]))
        self.assertTrue(F.regla("cuántas horas de distancia hay entre mi casa y madrid", "", []))
        self.assertTrue(F.regla("hora entre aquí y canadá", "dime la diferencia horaria entre aquí y Canadá", []))
        self.assertIsNone(F.regla("¿y en Japón?", "qué hora es en Japón", ["hora_mundo"]))

    def test_detectar(self):
        self.assertTrue(F.detectar("qué hora es en Japón"))
        self.assertFalse(F.detectar("qué hora es"))


if __name__ == "__main__":
    unittest.main()
