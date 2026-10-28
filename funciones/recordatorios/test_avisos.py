"""Pruebas de los avisos del calendario (avisos.py). Sin red ni notificaciones; los guardados van a un
archivo temporal:
    python3 -m unittest funciones.recordatorios.test_avisos
"""
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from funciones.recordatorios import avisos

D = datetime.datetime
CITA = {"clave": "g:Cita|2099-11-01T00:00:00", "titulo": "Cita", "inicio": "2099-11-01T00:00:00", "todo_el_dia": True}
CLASE = {"clave": "g:Clase|2099-11-02T15:00:00", "titulo": "Clase", "inicio": "2099-11-02T15:00:00",
         "todo_el_dia": False}


class AvisosCalendario(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        parche = mock.patch.object(avisos, "DATOS", Path(carpeta.name) / "recordatorios.json")
        parche.start()
        self.addCleanup(parche.stop)

    def test_guarda_el_evento_no_la_frase(self):
        avisos.programar_avisos([CITA])
        (r,) = avisos.cargar()["recordatorios"]
        self.assertEqual(r["texto"], "Cita")
        self.assertEqual(r["cuando"], "2099-11-01T08:00")  # el aviso, a las 8 del día
        self.assertEqual(r["evento"]["aviso"], "dia")

    def test_lista_con_la_fecha_del_evento(self):
        avisos.programar_avisos([CITA])
        (r,) = avisos.pendientes()
        self.assertEqual(r["texto"], "Cita")
        self.assertIn("(todo el día)", r["cuando_texto"])
        self.assertNotIn("08:00", r["cuando_texto"])

    def test_un_evento_una_fila_y_se_borra_entero(self):
        avisos.programar_avisos([CLASE])
        self.assertEqual(len(avisos.cargar()["recordatorios"]), 2)  # a las 8 y 30 min antes
        (r,) = avisos.pendientes()
        self.assertTrue(r["cuando_texto"].endswith("a las 15:00"))
        avisos.borrar(r["id"])
        self.assertEqual(avisos.cargar()["recordatorios"], [])

    def test_no_repite_avisos(self):
        avisos.programar_avisos([CITA])
        avisos.programar_avisos([CITA])
        self.assertEqual(len(avisos.cargar()["recordatorios"]), 1)


class FraseEvento(unittest.TestCase):
    EV = {"inicio": "2026-11-02T15:00:00", "todo_el_dia": False}

    def test_dia(self):
        self.assertEqual(avisos.frase_evento("Clase", {**self.EV, "aviso": "dia"}, D(2026, 11, 2, 8)),
                         "Hoy tienes «Clase» a las 15:00")
        self.assertEqual(avisos.frase_evento("Cita", {"inicio": "2026-11-01T00:00:00", "todo_el_dia": True,
                                                      "aviso": "dia"}, D(2026, 11, 1, 8)), "Hoy tienes «Cita»")

    def test_antes_cuenta_lo_que_falta(self):
        antes = {**self.EV, "aviso": "antes"}
        self.assertEqual(avisos.frase_evento("Clase", antes, D(2026, 11, 2, 14, 30)), "En 30 min: «Clase»")
        self.assertEqual(avisos.frase_evento("Clase", antes, D(2026, 11, 2, 14, 40)), "En 20 min: «Clase»")
        self.assertEqual(avisos.frase_evento("Clase", antes, D(2026, 11, 2, 15, 5)), "Hoy tienes «Clase» a las 15:00")


if __name__ == "__main__":
    unittest.main()
