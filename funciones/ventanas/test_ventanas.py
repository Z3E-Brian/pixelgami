"""Pruebas sin modelo y sin tocar ventanas: lo que decide si hay algo que hacer y la memoria corta.
    python3 -m unittest funciones.ventanas.test_ventanas
"""
import datetime
import time
import unittest

from funciones import Pedido
from funciones.ventanas import funcion as F


def pedido(texto, orden=None):
    orden = orden or texto
    return Pedido(texto, orden, orden, datetime.datetime(2026, 1, 1, 12), orden != texto)


class Entender(unittest.TestCase):
    def setUp(self):
        F._ultima.update(t=0.0, orden="", hecho="", dicho=True)

    def test_orden_y_ventanas_abiertas(self):
        i = F.entender(pedido("abre discord en el 4"), None)
        self.assertEqual((i["orden"], i["ver"]), ("abre discord en el 4", False))
        self.assertTrue(F.entender(pedido("qué ventanas tengo abiertas"), None)["ver"])

    def test_la_parte_ya_hecha_no_se_repite(self):
        F._ultima.update(t=time.time(), orden="abre discord", hecho="Abrí: Discord", dicho=False)
        i = F.entender(pedido("abre discord y cierra steam"), None)
        self.assertEqual((i["orden"], i["previa"]), ("y cierra steam", "abre discord"))
        self.assertEqual(i["antes"], "Abrí: Discord")

    def test_lo_no_dicho_va_aunque_hable_de_otra_cosa(self):
        F._ultima.update(t=time.time(), orden="abre discord", hecho="Abrí: Discord", dicho=False)
        self.assertIn("Abrí: Discord", F.datos(pedido("pon música")))
        F.respondio()
        self.assertIsNone(F.datos(pedido("pon música")))

    def test_aviso(self):
        self.assertIn("abriendo discord en el 4", F.aviso({"orden": "abre discord en el 4"}).lower())
        self.assertEqual(F.aviso({"orden": "qué ventanas tengo abiertas"}), "")


class Regla(unittest.TestCase):
    def test_el_resultado_de_una_busqueda_no_es_una_app(self):
        self.assertFalse(F.regla("ábrelo", "abre en el navegador el primer resultado", ["web", "ventanas"]))
        self.assertIsNone(F.regla("x", "abre discord y busca ram en el navegador", ["web", "ventanas"]))
        self.assertIsNone(F.regla("x", "abre el navegador", ["ventanas"]))


class AparatosQueNoSonVentanas(unittest.TestCase):
    def test_regla(self):
        self.assertFalse(F.regla("enciende la aspiradora", "enciende la aspiradora", ["ventanas"]))
        self.assertFalse(F.regla("apaga las luces", "apaga las luces", ["ventanas"]))
        self.assertIsNone(F.regla("Sierra, el VS Code", "cierra VS Code", ["ventanas"]))
        self.assertIsNone(F.regla("qué ventanas tengo", "qué ventanas tengo abiertas", ["ventanas"]))

    def test_entender_sin_nada_que_hacer(self):
        F._ultima.update(t=0.0, orden="", hecho="", dicho=True)
        self.assertIsNone(F.entender(pedido("apaga las luces"), None))

if __name__ == "__main__":
    unittest.main()
