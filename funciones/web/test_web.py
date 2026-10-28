"""Pruebas sin modelo ni red de lo que corrige al modelo y revisa la respuesta.
    python3 -m unittest funciones.web.test_web
"""
import datetime
import unittest

from funciones import Pedido
from funciones.web import funcion as F


def pedido(texto, necesita=False):
    return Pedido(texto, texto, texto, datetime.datetime(2026, 1, 1, 12), necesita)


def intencion(**cambios):
    base = {"accion": "buscar", "consulta": "memorias RAM", "tipo": "paginas", "sitio": "", "navegador": False,
            "numero": 0}
    return {**base, **cambios}


class Revisar(unittest.TestCase):
    def setUp(self):
        F._web.update(resultados=[], consulta="")

    def test_no_abre_el_navegador_si_no_lo_pidio(self):
        i = F._revisar(intencion(navegador=True), pedido("busca memorias RAM"))
        self.assertFalse(i["navegador"])
        i = F._revisar(intencion(navegador=True), pedido("busca memorias RAM y ábrelo"))
        self.assertTrue(i["navegador"])

    def test_sitio_que_no_nombro(self):
        self.assertEqual(F._revisar(intencion(sitio="amazon.com"), pedido("busca memorias RAM"))["sitio"], "")
        self.assertEqual(F._revisar(intencion(sitio="amazon.com"), pedido("busca memorias RAM en amazon"))["sitio"],
                         "amazon.com")

    def test_nombrar_un_sitio_sin_buscar_nada_es_ir(self):
        i = F._revisar(intencion(consulta="", sitio="reddit.com"), pedido("llévame a reddit"))
        self.assertEqual(i["accion"], "ir")

    def test_dale_tras_una_busqueda_abre_el_resultado(self):
        F._web.update(resultados=[object()], consulta="RAM")
        i = F._revisar(intencion(consulta="dale"), pedido("dale", necesita=True))
        self.assertEqual((i["accion"], i["numero"]), ("abrir", 1))

    def test_para_el_router(self):
        self.assertIsNone(F.para_el_router())
        F._web.update(resultados=[type("R", (), {"title": "RAM DDR4"})()], consulta="RAM 8GB")
        self.assertIn("«RAM 8GB»", F.para_el_router())


class Precios(unittest.TestCase):
    def test_precio_inventado(self):
        revisar = F._revisor_de_precios([("RAM DDR4", "₡25.000")])
        self.assertIsNone(revisar("Está en ₡25.000 en ExtremeTech."))
        self.assertEqual(revisar("Anda por los ₡30.000."), "En lo que encontré: RAM DDR4, ₡25.000.")
        self.assertIsNone(revisar("Es una buena opción."))

    def test_sin_precios_en_los_resultados(self):
        self.assertEqual(F._revisor_de_precios([])("Cuesta unos $120."), "No veo el precio en lo que encontré.")


class Regla(unittest.TestCase):
    def test_musica_no_es_internet(self):
        self.assertFalse(F.regla("abre youtube y pon música", "abre youtube y pon música", ["musica", "web"]))
        self.assertIsNone(F.regla("x", "busca en google música para estudiar", ["musica", "web"]))
        self.assertIsNone(F.regla("x", "pon música", ["musica"]))


if __name__ == "__main__":
    unittest.main()
