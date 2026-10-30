"""Pruebas sin modelo de la métrica del router: un router simulado (respuestas fijas) y un reloj falso.
    python3 -m unittest evaluacion.test_metrica
"""
import csv
import datetime
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import funciones
from evaluacion import metrica, modelos
from evaluacion.metrica import NINGUNO

FECHA = datetime.datetime(2026, 1, 15, 21, 30)

# (la asistente, el usuario antes, lo que dice, temas esperados, palabras de la orden): el formato de pruebas.py
CASOS = [
    ("", "", "revisa el spam", {"correo"}, []),
    ("", "", "abre el navegador", {"ventanas"}, []),
    ("", "", "pon algo de música", {"musica"}, []),
    ("", "", "busca la ram y pon música", {"web", "musica"}, ["ram"]),
    ("", "", "hola, cómo estás", {"charla"}, []),
    ("", "", "qué opinas de la RAM", {"charla"}, []),
]
# lo que responde el router simulado a cada texto: (temas, orden); None = no respondió
RESPUESTAS = {
    "revisa el spam": (["correo"], "revisa el spam"),
    "abre el navegador": (["web"], "abre el navegador"),  # confunde ventanas con web
    "pon algo de música": None,  # no respondió
    "busca la ram y pon música": (["web", "musica"], "busca la RAM y pon música"),
    "hola, cómo estás": (["charla"], "hola, cómo estás"),
    "qué opinas de la RAM": (["charla", "web"], "busca la RAM"),  # inventa una búsqueda
}


def router_simulado(caso):
    r = RESPUESTAS[caso[2]]
    return None if r is None else {"temas": r[0], "orden": r[1], "combinado": r[1]}


def reloj_falso(pasos):
    """Un reloj que avanza `pasos[i]` segundos en cada caso (medir lo lee al empezar y al terminar)."""
    tiempos = iter(t for paso in pasos for t in (0.0, paso))
    return lambda: next(tiempos)


def medir_todo(pasos=(1.0,) * len(CASOS)):
    return list(metrica.medir(CASOS, router_simulado, reloj=reloj_falso(pasos)))


class Bien(unittest.TestCase):
    def test_acciones_exactas(self):
        self.assertTrue(metrica.bien({"correo"}, {"correo"}, "", []))
        self.assertFalse(metrica.bien({"correo"}, {"web"}, "", []))
        self.assertFalse(metrica.bien({"correo"}, {"correo", "web"}, "", []))  # inventó web
        self.assertFalse(metrica.bien({"web", "musica"}, {"web"}, "", []))  # perdió música

    def test_charla_junto_a_una_accion_no_estorba(self):
        self.assertTrue(metrica.bien({"correo"}, {"correo", "charla"}, "", []))
        self.assertTrue(metrica.bien({"charla"}, {"charla"}, "", []))
        self.assertFalse(metrica.bien({"charla"}, {"web"}, "", []))

    def test_palabras_de_la_orden(self):
        self.assertTrue(metrica.bien({"correo"}, {"correo"}, "marca los de la u", ["de la u"]))
        self.assertFalse(metrica.bien({"correo"}, {"correo"}, "marca todos", ["de la u"]))


class Pares(unittest.TestCase):
    def test_acierto_en_la_diagonal(self):
        self.assertEqual(metrica.pares({"correo"}, {"correo"}), [("correo", "correo")])

    def test_confusion_y_perdido(self):
        self.assertEqual(metrica.pares({"ventanas"}, {"web"}), [("ventanas", "web")])
        self.assertEqual(metrica.pares({"musica"}, set()), [("musica", NINGUNO)])
        self.assertEqual(metrica.pares({"web", "musica"}, {"web"}), [("musica", NINGUNO), ("web", "web")])

    def test_perder_una_accion_por_charla_si_es_confusion(self):
        self.assertEqual(metrica.pares({"correo"}, {"charla"}), [("correo", "charla")])

    def test_charla_de_mas_no_es_confusion(self):
        self.assertEqual(metrica.pares({"correo"}, {"correo", "charla"}), [("correo", "correo")])
        self.assertEqual(metrica.pares({"charla"}, {"charla", "web"}), [("charla", "charla"), ("charla", "web")])


class Medir(unittest.TestCase):
    def test_cada_caso(self):
        medidas = medir_todo((0.5, 1.0, 1.5, 2.0, 2.5, 3.0))
        self.assertEqual([m.bien for m in medidas], [True, False, False, True, True, False])
        self.assertEqual([m.segundos for m in medidas], [0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        self.assertEqual(medidas[1].temas, frozenset({"web"}))

    def test_sin_respuesta_es_mal(self):
        sin = medir_todo()[2]
        self.assertFalse(sin.respondio)
        self.assertFalse(sin.bien)
        self.assertEqual(sin.temas, frozenset())

    def test_charla_sin_respuesta_tambien_es_mal(self):
        """bien() da por buena una charla sin temas; si el modelo no respondió, no se midió nada."""
        medidas = list(metrica.medir([("", "", "hola", {"charla"}, [])], lambda caso: None))
        self.assertFalse(medidas[0].bien)


class Reporte(unittest.TestCase):
    def setUp(self):
        self.medidas = medir_todo((0.5, 1.0, 1.5, 2.0, 2.5, 3.0))
        self.rep = metrica.reporte(self.medidas, "ollama:qwen3:8b", FECHA)

    def test_totales(self):
        self.assertEqual((self.rep["casos"], self.rep["bien"], self.rep["sin_respuesta"]), (6, 3, 1))
        self.assertEqual(self.rep["acierto"], 50.0)
        self.assertEqual(self.rep["modelo"], "ollama:qwen3:8b")
        self.assertEqual(self.rep["fecha"], "2026-01-15T21:30:00")

    def test_tiempos(self):
        self.assertEqual(self.rep["tiempo_promedio_s"], 1.75)
        self.assertEqual(self.rep["tiempo_mediana_s"], 1.75)
        self.assertEqual(self.rep["tiempo_max_s"], 3.0)

    def test_acierto_por_tema(self):
        por_tema = self.rep["por_tema"]
        self.assertEqual(list(por_tema)[-1], "charla")  # la charla al final
        self.assertEqual(por_tema["correo"], {"casos": 1, "bien": 1, "acierto": 100.0})
        self.assertEqual(por_tema["musica"], {"casos": 2, "bien": 1, "acierto": 50.0})
        self.assertEqual(por_tema["charla"], {"casos": 2, "bien": 1, "acierto": 50.0})
        self.assertEqual(por_tema["web"]["casos"], 1)  # solo cuenta donde se esperaba web, no donde lo inventó

    def test_matriz(self):
        v = self.rep["matriz"]["valores"]
        self.assertEqual(v["ventanas"]["web"], 1)
        self.assertEqual(v["ventanas"]["ventanas"], 0)
        self.assertEqual(v["musica"][NINGUNO], 1)
        self.assertEqual(v["musica"]["musica"], 1)
        self.assertEqual((v["charla"]["charla"], v["charla"]["web"]), (2, 1))
        self.assertEqual(sum(v["correo"].values()), 1)

    def test_fallos(self):
        self.assertEqual([f["texto"] for f in self.rep["fallos"]],
                         ["abre el navegador", "pon algo de música", "qué opinas de la RAM"])
        self.assertEqual(self.rep["fallos"][2]["elegidos"], ["web", "charla"])

    def test_sin_casos(self):
        vacio = metrica.reporte([], "x", FECHA)
        self.assertEqual((vacio["casos"], vacio["acierto"], vacio["tiempo_promedio_s"]), (0, 0.0, 0.0))

    def test_como_texto(self):
        texto = metrica.como_texto(self.rep)
        self.assertIn("3/6 bien = 50.0 %", texto)
        self.assertIn("1.75 s promedio", texto)
        self.assertIn("Matriz de confusión", texto)


class Guardar(unittest.TestCase):
    def test_json_y_csv_con_fecha_y_modelo(self):
        medidas = medir_todo()
        rep = metrica.reporte(medidas, "ollama:qwen3:8b", FECHA)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_json, ruta_csv = metrica.guardar(rep, medidas, Path(carpeta) / "resultados")
            self.assertEqual(ruta_json.name, "eval_2026-01-15_2130_ollama-qwen3-8b.json")
            self.assertEqual(ruta_csv.name, "eval_2026-01-15_2130_ollama-qwen3-8b.csv")
            self.assertEqual(json.loads(ruta_json.read_text()), rep)
            with ruta_csv.open(newline="") as f:
                filas = list(csv.DictReader(f))
        self.assertEqual(len(filas), len(CASOS))
        self.assertEqual(filas[3]["esperados"], "musica web")
        self.assertEqual((filas[2]["respondio"], filas[2]["bien"]), ("0", "0"))
        self.assertTrue(all(f["modelo"] == "ollama:qwen3:8b" and f["fecha"] == rep["fecha"] for f in filas))

    def test_nombre_sin_caracteres_raros(self):
        self.assertEqual(metrica.nombre_archivo("gemini:gemini-3.5-flash", FECHA),
                         "eval_2026-01-15_2130_gemini-gemini-3.5-flash")


class Modelos(unittest.TestCase):
    def test_elegir_local(self):
        armados = []
        local = lambda nombre: armados.append(nombre) or "modelo"  # noqa: E731
        self.assertEqual(modelos.elegir("qwen3:8b", local), ("ollama:qwen3:8b", "modelo"))
        self.assertEqual(modelos.elegir("ollama:qwen3:4b", local)[0], "ollama:qwen3:4b")
        self.assertEqual(armados, ["qwen3:8b", "qwen3:4b"])

    def test_elegir_gemini_pide_el_modelo(self):
        with self.assertRaises(SystemExit):
            modelos.elegir("gemini", lambda n: None)

    def test_gemini_sin_red(self):
        """El pedido lleva el esquema y la clave; de la respuesta sale el JSON del modelo."""
        enviado = {}

        def urlopen(req, timeout):
            enviado.update(url=req.full_url, cuerpo=json.loads(req.data), clave=req.get_header("X-goog-api-key"))
            texto = json.dumps({"orden": "revisa el spam", "temas": ["correo"], "necesita_contexto": False})
            return io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"text": texto}]}}]}).encode())

        esquema = {"type": "object", "properties": {"temas": {"type": "array"}}}
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "clave-de-prueba"}), \
                mock.patch.object(modelos.urllib.request, "urlopen", urlopen):
            nombre, modelo = modelos.elegir("gemini:gemini-x", lambda n: None)
            r = modelo("eres el router", "revisa el spam", esquema)
        self.assertEqual(nombre, "gemini:gemini-x")
        self.assertEqual(r["temas"], ["correo"])
        self.assertIn("/models/gemini-x:generateContent", enviado["url"])
        self.assertEqual(enviado["clave"], "clave-de-prueba")
        self.assertEqual(enviado["cuerpo"]["generationConfig"]["responseJsonSchema"], esquema)
        self.assertEqual(enviado["cuerpo"]["systemInstruction"]["parts"][0]["text"], "eres el router")

    def test_gemini_caido_es_none(self):
        def urlopen(req, timeout):
            raise OSError("sin red")
        with mock.patch.object(modelos.urllib.request, "urlopen", urlopen), \
                mock.patch("builtins.print"):
            self.assertIsNone(modelos.gemini("gemini-x", "clave")("s", "t", {}))


class CasosReales(unittest.TestCase):
    """Los casos etiquetados de verdad (funciones/*/pruebas.py): bien formados y con temas que existen."""

    def test_temas_validos(self):
        cargadas = funciones.cargar()
        validos = {f.tema for f in cargadas} | set(funciones.RESERVADOS)
        total = 0
        for f in cargadas:
            try:
                pruebas = importlib.import_module(f"funciones.{f.nombre}.pruebas")
            except ModuleNotFoundError:
                continue
            for caso in getattr(pruebas, "ROUTER", []):
                total += 1
                with self.subTest(funcion=f.nombre, texto=caso[2]):
                    self.assertEqual(len(caso), 5)
                    self.assertTrue(caso[3], "sin temas esperados")
                    self.assertLessEqual(set(caso[3]), validos)
        self.assertGreater(total, 0)


if __name__ == "__main__":
    unittest.main()
