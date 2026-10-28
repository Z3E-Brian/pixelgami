"""Pruebas de la parte de conversación (funcion.py) sin modelo, sin red y sin guardar nada: el modelo se reemplaza
por respuestas fijas y el calendario y el guardado por listas.
    python3 -m unittest funciones.recordatorios.test_conversacion
"""
import datetime
import unittest

from funciones import Pedido
from funciones.recordatorios import funcion as M


def modelo(accion, que="", cuando=""):
    """Un qwen_json falso que siempre responde lo mismo."""
    return lambda _sistema, _texto, _esquema: {"accion": accion, "que": que, "cuando": cuando}


class Conversacion(unittest.TestCase):
    def setUp(self):
        self.apuntados, self.guardados = [], []
        self._originales = (M.calendario.configurado, M.calendario.apuntar, M.avisos.guardar_uno)
        M.calendario.configurado = lambda: True
        M.calendario.apuntar = lambda *a: self.apuntados.append(a)
        M.avisos.guardar_uno = lambda texto, cuando, repetir, origen: (
            self.guardados.append((texto, cuando)) or {"texto": texto, "repetir": repetir, "cuando_texto": "luego"})
        M._pendiente["t"] = 0.0

    def tearDown(self):
        M.calendario.configurado, M.calendario.apuntar, M.avisos.guardar_uno = self._originales

    def decir(self, texto, respuesta_modelo):
        """(contexto, ¿pregunta?) de entender + ejecutar, o None si no es de recordatorios."""
        p = M.entender(Pedido(texto, texto, texto, datetime.datetime.now()), respuesta_modelo)
        r = M.ejecutar(p) if p else None
        return (r.contexto, r.preguntar) if r else None

    def test_apuntar_sin_hora_pregunta_y_luego_apunta(self):
        contexto, pregunta = self.decir("apunta una cita para el primero de noviembre", modelo("apuntar", "una cita"))
        self.assertTrue(pregunta)
        self.assertIn("TODAVÍA NO", contexto)
        self.assertEqual(self.apuntados, [])
        self.assertIn("apuntado", M.pendiente("a las 3 de la tarde").contexto)
        (texto, cuando, con_hora, _), = self.apuntados
        self.assertEqual((texto, cuando.month, cuando.day, cuando.hour, con_hora), ("Una cita", 11, 1, 15, True))

    def test_respuesta_todo_el_dia(self):
        self.decir("agenda el examen de cálculo el 12", modelo("apuntar", "examen de cálculo"))
        M.pendiente("todo el día")
        self.assertFalse(self.apuntados[0][2])

    def test_pedido_nuevo_no_responde_la_pregunta(self):
        self.decir("guarda la reunión del lunes", modelo("apuntar", "reunión"))
        self.assertIsNone(M.pendiente("apunta el dentista el viernes a las 10"))
        self.assertIsNone(M.pendiente("a las 3"))  # la pregunta ya se descartó
        self.assertEqual(self.apuntados, [])

    def test_no_cancela(self):
        self.decir("guarda la reunión del lunes", modelo("apuntar", "reunión"))
        self.assertIn("no se apuntó", M.pendiente("no, déjalo").contexto)
        self.assertEqual(self.apuntados, [])

    def test_apuntar_con_hora_o_todo_el_dia_no_pregunta(self):
        _, pregunta = self.decir("apunta el dentista el viernes a las 10", modelo("apuntar", "dentista"))
        self.assertFalse(pregunta)
        _, pregunta = self.decir("agenda la entrega el 30 de noviembre todo el día", modelo("apuntar", "la entrega"))
        self.assertFalse(pregunta)
        self.assertEqual([a[2] for a in self.apuntados], [True, False])

    def test_crear_evento_va_al_calendario(self):
        self.decir("crea un evento el sábado a las 3: partido", modelo("crear", "partido"))
        self.assertEqual(len(self.apuntados), 1)
        self.assertEqual(self.guardados, [])

    def test_recordatorio_sin_cuando_pregunta(self):
        contexto, pregunta = self.decir("recuérdame sacar la basura", modelo("crear", "sacar la basura"))
        self.assertTrue(pregunta)
        self.assertIn("no dijo cuándo", contexto)

    def test_fecha_de_sus_palabras_no_del_modelo(self):
        # el modelo corta mal ("pasado mañana" -> «pasar»): la fecha y el qué salen de lo que dijo
        p = M.entender(Pedido("puedes recordarme pasado mañana revisar el correo", "", "", datetime.datetime.now()),
                       modelo("crear", "pasar", ""))
        self.assertEqual(p["cuando"].date(), datetime.date.today() + datetime.timedelta(days=2))
        self.assertEqual(p["texto"], "Revisar el correo")

    def test_regla(self):
        self.assertTrue(M.regla("no me dejes olvidar lo del viernes"))
        self.assertFalse(M.regla("apunta que mi cumple es en marzo"))  # memoria, no calendario
        self.assertIsNone(M.regla("apunta una cita para el primero de noviembre"))
        self.assertFalse(M.regla("qué tengo mañana"))  # es la agenda (datos), no un recordatorio
        self.assertFalse(M.regla("pon música"))  # "pon" sin fecha ni calendario
        self.assertIsNone(M.regla("hola, cómo estás"))  # lo decide el router

    def test_regla_alarmas_y_quitar_de_la_agenda(self):
        self.assertTrue(M.regla("apaga la alarma"))
        self.assertTrue(M.regla("quiero ver todas mis alarmas"))
        self.assertTrue(M.regla("puedes borrar mi cita con el dentista"))
        self.assertTrue(M.regla("despeja mi calendario para el sábado"))

    def test_datos_solo_si_pregunta_la_agenda(self):
        self.assertIsNone(M.datos(Pedido("hola, cómo estás", "", "", datetime.datetime.now())))


if __name__ == "__main__":
    unittest.main()
