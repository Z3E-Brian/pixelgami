"""Pruebas sin modelo ni Gmail: el modelo se reemplaza por respuestas fijas; nada toca el correo.
    python3 -m unittest funciones.correo.test_correo
"""
import copy
import datetime
import time
import unittest

from funciones import Pedido
from funciones.correo import funcion as F


def pedido(texto, temas=("correo",)):
    return Pedido(texto, texto, texto, datetime.datetime(2026, 1, 1, 12), temas=frozenset(temas))


def intencion(**cambios):
    base = {"acciones": ["ver"], "carpeta": "", "quienes": [], "asunto": [], "todos": False, "solo_sin_leer": False}
    return {**base, **cambios}


def modelo(respuesta):
    """Un modelo falso que siempre responde lo mismo (una copia: entender() la modifica)."""
    return lambda _s, _t, _e: copy.deepcopy(respuesta)


class Entender(unittest.TestCase):
    def test_ninguna_no_es_del_correo(self):
        self.assertIsNone(F.entender(pedido("abre discord"), modelo(intencion(acciones=["ninguna"]))))

    def test_sin_modelo_el_resumen(self):
        self.assertEqual(F.entender(pedido("revisa el correo"), modelo(None)), {"acciones": ["resumen"]})
        self.assertEqual(F.aviso({"acciones": ["resumen"]}), "")

    def test_el_correo_de_alguien_es_leerlo(self):
        ver = modelo(intencion(quienes=["gaceta universitaria"]))
        self.assertEqual(F.entender(pedido("revisa el correo de la gaceta universitaria"), ver)["acciones"], ["leer"])
        self.assertEqual(F.entender(pedido("revisa los correos de la gaceta"), ver)["acciones"], ["ver"])
        self.assertEqual(F.entender(pedido("revisa el correo"), modelo(intencion()))["acciones"], ["ver"])

    def test_varios(self):
        self.assertTrue(F.entender(pedido("lee los de la U"), modelo(intencion(acciones=["leer"])))["varios"])
        self.assertFalse(F.entender(pedido("lee el de la U"), modelo(intencion(acciones=["leer"])))["varios"])


class Aviso(unittest.TestCase):
    def test_avisos(self):
        self.assertIn("spam", F.aviso(intencion(carpeta="spam")))
        self.assertIn("Zoom", F.aviso(intencion(acciones=["papelera"], quienes=["Zoom"])))
        self.assertEqual(F.aviso(intencion(acciones=["imposible"])), "")


class Pendiente(unittest.TestCase):
    def setUp(self):
        self.aplicado = []
        self._aplicar = F._aplicar
        F._aplicar = lambda acciones, carpeta, correos: self.aplicado.append(acciones) or "Listo."
        F._correo["pendiente"] = {"t": time.time(), "acciones": ["papelera"], "carpeta": "entrada", "correos": []}

    def tearDown(self):
        F._aplicar = self._aplicar
        F._correo["pendiente"] = None

    def test_si_lo_hace(self):
        self.assertIn("confirmó", F.pendiente("sí, dale").contexto)
        self.assertEqual(self.aplicado, [["papelera"]])

    def test_no_no_hace_nada(self):
        self.assertIn("no se cambió", F.pendiente("no").contexto)
        self.assertEqual(self.aplicado, [])

    def test_otra_cosa_no_es_la_respuesta(self):
        self.assertIsNone(F.pendiente("abre discord en el escritorio 3 por favor"))
        F._correo["pendiente"]["t"] -= 200  # venció
        self.assertIsNone(F.pendiente("sí"))


class Datos(unittest.TestCase):
    def test_lo_hecho_solo_si_habla_del_correo(self):
        F._correo["hecho"] = [(time.time(), "abriste y leíste 1 correo(s): GitHub")]
        self.assertIn("GitHub", F.datos(pedido("cuántos leíste?")))
        self.assertIsNone(F.datos(pedido("hola", temas=("charla",))))
        F._correo["hecho"] = []


class Regla(unittest.TestCase):
    def test_listas_no_son_correo(self):
        self.assertFalse(F.regla("lee mis listas", "lee mis listas", ["correo"]))
        self.assertFalse(F.regla("eliminar ese artículo", "elimina ese artículo", ["correo"]))
        self.assertIsNone(F.regla("manda a la papelera los correos de la lista", "", ["correo"]))

if __name__ == "__main__":
    unittest.main()
