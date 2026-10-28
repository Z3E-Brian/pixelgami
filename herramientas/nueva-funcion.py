#!/usr/bin/env python3
"""Crea una función nueva en funciones/<nombre>/ con todo lo necesario y un esqueleto que ya funciona.

    python3 herramientas/nueva-funcion.py clima                  # tema "clima"
    python3 herramientas/nueva-funcion.py hora_mundo --tema hora # otro nombre para el router

Después: cambia funcion.yaml (qué cubre, ejemplos), funcion.py (qué hace) y pruebas.py (frases reales).
Guía: docs/FUNCIONES.md.
"""
import argparse
import re
import sys
from pathlib import Path


def _instalacion() -> Path:
    """La carpeta de la instalación: la primera, subiendo desde aquí, que tiene identidad.py y funciones/. En el repo
    es la de arriba de herramientas/; en la instalación de trabajo esta herramienta está en publico/plantillas/."""
    for carpeta in Path(__file__).resolve().parents:
        if (carpeta / "identidad.py").exists() and (carpeta / "funciones/__init__.py").exists():
            return carpeta
    sys.exit("No encuentro la instalación (una carpeta con identidad.py y funciones/) más arriba de esta herramienta.")


RAIZ = _instalacion()

YAML = '''tema: {tema}
orden: 100  # dónde va en el router (las de serie: 10 a 80)
descripcion: |-
  QUÉ CUBRE: cuándo un mensaje es de "{tema}" ("una frase de ejemplo", "otra"). Si se puede confundir con otro tema,
    di también qué NO es suyo.
ejemplos: |-
  {{usuario}}: "una frase de ejemplo" -> temas ["{tema}"]
si_falla: No pudiste hacerlo ({{error}}). Díselo en una frase.
'''

FUNCION = '''"""{titulo}: QUÉ HACE (ver docs/FUNCIONES.md)."""
from funciones import Pedido, Resultado
from identidad import nombres

INTERPRETAR = nombres("""{{usuario}} le pide algo a {{asistente}} sobre {tema}. Interpreta QUÉ quiere aunque lo diga
con otras palabras o mal transcrito. Responde solo el JSON.
quiere: true si de verdad pide algo de {tema}.
que: lo que pide, corto y con sus palabras.""")
ESQUEMA = {{"type": "object", "properties": {{"quiere": {{"type": "boolean"}}, "que": {{"type": "string"}}}},
          "required": ["quiere", "que"]}}


def entender(pedido: Pedido, modelo) -> dict | None:
    """Qué pide, o None si no es de aquí (o el modelo no respondió)."""
    i = modelo(INTERPRETAR, pedido.combinado, ESQUEMA)
    return i if i and i["quiere"] else None


def ejecutar(intencion: dict, pedido: Pedido) -> Resultado:
    """Lo hace y cuenta qué pasó, en hechos."""
    return Resultado(f"Pidió «{{intencion['que']}}», pero esta función todavía no hace nada. Díselo en una frase.",
                     hizo=False)
'''

PRUEBAS = '''"""Casos con el modelo (los corre pruebas_intencion.py; solo interpretan, no ejecutan nada)."""

# (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras de la orden).
# Incluye frases que NO son de "{tema}", para que no se robe mensajes de otros temas.
ROUTER = [
    ("", "", "una frase de ejemplo", {{"{tema}"}}, []),
    ("", "", "hola, cómo estás", {{"charla"}}, []),
]
'''

TEST = '''"""Pruebas sin modelo: el modelo se reemplaza por respuestas fijas.
    python3 -m unittest funciones.{nombre}.test_{nombre}
"""
import datetime
import unittest

from funciones import Pedido
from funciones.{nombre} import funcion as F


def pedido(texto):
    return Pedido(texto, texto, texto, datetime.datetime(2026, 1, 1, 12, 0))


def modelo(respuesta):
    return lambda _sistema, _texto, _esquema: respuesta


class {clase}(unittest.TestCase):
    def test_entender(self):
        self.assertEqual(F.entender(pedido("una frase de ejemplo"), modelo({{"quiere": True, "que": "algo"}}))["que"], "algo")
        self.assertIsNone(F.entender(pedido("hola"), modelo({{"quiere": False, "que": ""}})))
        self.assertIsNone(F.entender(pedido("hola"), modelo(None)))  # el modelo no respondió

    def test_ejecutar(self):
        self.assertIn("algo", F.ejecutar({{"quiere": True, "que": "algo"}}, pedido("x")).contexto)


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nombre", help="nombre de la carpeta: minúsculas, números y _")
    ap.add_argument("--tema", help="nombre para el router (por defecto, el de la carpeta)")
    a = ap.parse_args()
    tema = a.tema or a.nombre
    for valor in (a.nombre, tema):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", valor):
            sys.exit(f"«{valor}»: usa minúsculas, números y _ (empieza con letra).")
    carpeta = RAIZ / "funciones" / a.nombre
    if carpeta.exists():
        sys.exit(f"Ya existe {carpeta.relative_to(RAIZ)}.")
    import yaml
    sys.path.insert(0, str(RAIZ))
    from funciones import RESERVADOS
    usados = {yaml.safe_load(p.read_text())["tema"]: f"funciones/{p.parent.name}"
              for p in (RAIZ / "funciones").glob("*/funcion.yaml")}
    if tema in usados or tema in RESERVADOS:
        sys.exit(f"El tema «{tema}» ya lo usa {usados.get(tema, 'el núcleo')}: elige otro con --tema.")
    datos = {"nombre": a.nombre, "tema": tema, "titulo": a.nombre.replace("_", " ").capitalize(),
             "clase": "".join(p.capitalize() for p in a.nombre.split("_"))}
    carpeta.mkdir(parents=True)
    (carpeta / "__init__.py").write_text(f'"""{datos["titulo"]} (ver funcion.py)."""\n')
    (carpeta / "funcion.yaml").write_text(YAML.format(**datos))
    (carpeta / "funcion.py").write_text(FUNCION.format(**datos))
    (carpeta / "pruebas.py").write_text(PRUEBAS.format(**datos))
    (carpeta / f"test_{a.nombre}.py").write_text(TEST.format(**datos))
    print(f"Creada funciones/{a.nombre}/ (tema «{tema}»). Siguiente:")
    print("  1. funcion.yaml: qué cubre y 2-3 ejemplos; funcion.py: qué hace; pruebas.py: frases reales")
    print(f"  2. python3 -m unittest funciones.{a.nombre}.test_{a.nombre}")
    print(f"  3. cd Open-LLM-VTuber && uv run python ../pruebas_intencion.py {a.nombre}   (y luego todas)")
    perfil = RAIZ / "perfil.yaml"
    if perfil.exists() and (yaml.safe_load(perfil.read_text()) or {}).get("funciones") is not None:
        print("  4. agrégala a `funciones:` en perfil.yaml")
    print("  Reinicia la asistente para que la cargue. Guía: docs/FUNCIONES.md")


if __name__ == "__main__":
    main()
