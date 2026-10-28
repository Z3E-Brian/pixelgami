#!/usr/bin/env python3
"""Comprueba la instalación sin red ni modelos (lo usa también la prueba automática de cada PR).

    python3 herramientas/comprobar.py            # compila, valida configs y el modelo activo
    python3 herramientas/comprobar.py --importar # además importa los módulos propios (necesita `uv sync`)

Sale con código 1 si algo falla, y dice qué.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OLV = RAIZ / "Open-LLM-VTuber"
errores: list[str] = []


def error(msg: str) -> None:
    errores.append(msg)
    print("  ✗", msg)


def ok(msg: str) -> None:
    print("  ✓", msg)


def compilar() -> None:
    print("Python")
    archivos = [p for p in RAIZ.glob("*.py")] + [p for d in RAIZ.glob("*-mcp") for p in d.glob("*.py")]
    archivos += list((RAIZ / "rvc").glob("*.py")) + list((RAIZ / "herramientas").glob("*.py"))
    archivos += [p for p in (RAIZ / "funciones").rglob("*.py") if "__pycache__" not in p.parts]
    archivos += list((OLV / "src/open_llm_vtuber").rglob("*.py")) if OLV.exists() else []
    for p in archivos:
        try:
            compile(p.read_bytes(), str(p), "exec")  # solo la sintaxis: no escribe .pyc
        except SyntaxError as e:
            error(f"no compila {p.relative_to(RAIZ)}:{e.lineno}: {e.msg}")
    if not errores:
        ok(f"{len(archivos)} archivos compilan")


def configs() -> None:
    print("Configuración")
    try:
        import yaml
    except ImportError:
        print("  · sin PyYAML en este Python: me salto conf.yaml y perfil (corre con Open-LLM-VTuber/.venv/bin/python)")
        return
    perfil = RAIZ / ("perfil.yaml" if (RAIZ / "perfil.yaml").exists() else "perfil.ejemplo.yaml")
    datos = {}
    try:
        datos = yaml.safe_load(perfil.read_text()) or {}
        for clave in ("genero_usuario", "genero_asistente"):
            if str(datos.get(clave, "m")).lower()[:1] not in ("m", "f"):
                error(f"{perfil.name}: {clave} debe ser m o f")
        ok(f"{perfil.name} es YAML válido")
    except Exception as e:
        error(f"{perfil.name}: {e}")
    conf = OLV / "conf.yaml"
    if not conf.exists():
        print("  · falta Open-LLM-VTuber/conf.yaml (corre ./instalar.sh)")
        return
    try:
        personaje = yaml.safe_load(conf.read_text())["character_config"]
    except Exception as e:
        error(f"conf.yaml: {e}")
        return
    ok("conf.yaml es YAML válido")
    marcas = set(re.findall(r"\{[^{}\s]+\}", personaje.get("persona_prompt", "")))
    sys.path.insert(0, str(RAIZ))
    try:
        import identidad
        conocidas = set(identidad._MARCAS) | {"{asistente}", "{usuario}"}
        desconocidas = marcas - conocidas
        if desconocidas:
            error(f"persona_prompt usa marcadores que no existen: {', '.join(sorted(desconocidas))} (ver identidad.py)")
        else:
            ok("persona_prompt: todos los marcadores existen")
    except Exception as e:
        error(f"identidad.py no carga: {e}")
    try:  # funcion.yaml válidos, funcion.py importan y ningún tema repetido
        import funciones
        cargadas = funciones.cargar(datos.get("funciones"))
        ok("funciones: " + (", ".join(f"{f.nombre} ({f.tema})" for f in cargadas) or "ninguna"))
    except Exception as e:
        error(f"funciones: {e}")
    modelo(personaje.get("live2d_model_name", ""))


def modelo(nombre: str) -> None:
    print(f"Modelo Live2D activo: {nombre}")
    try:
        lista = json.loads((OLV / "model_dict.json").read_text())
    except Exception as e:
        error(f"model_dict.json: {e}")
        return
    entrada = next((m for m in lista if m["name"] == nombre), None)
    if not entrada:
        error(f"'{nombre}' no está en model_dict.json (agrégalo con herramientas/agregar-modelo.py)")
        return
    ruta = OLV / entrada["url"].lstrip("/")
    if not ruta.exists():
        error(f"no existe {ruta.relative_to(RAIZ)} (¿descargaste el modelo en live2d-models/?)")
        return
    datos = json.loads(ruta.read_text())
    n = len(datos.get("FileReferences", {}).get("Expressions", []))
    fuera = {k: v for k, v in entrada.get("emotionMap", {}).items() if not isinstance(v, int) or not 0 <= v < max(n, 1)}
    if fuera:
        error(f"emotionMap apunta a expresiones que no existen (el modelo tiene {n}): {fuera}")
    else:
        ok(f"{n} expresiones; emotionMap con {len(entrada.get('emotionMap', {}))} emociones, todas válidas")
    grupos = {g["Name"] for g in datos.get("Groups", [])}
    for g, para in (("LipSync", "mover la boca al hablar"), ("EyeBlink", "parpadear")):
        print(f"  {'✓' if g in grupos else '·'} grupo {g} ({para})")


def importar() -> None:
    print("Importar módulos propios")
    python = OLV / ".venv/bin/python"
    if not python.exists():
        error("falta Open-LLM-VTuber/.venv (corre ./instalar.sh --python)")
        return
    codigo = ("import sys; sys.path.insert(0, 'src'); "
              "from open_llm_vtuber.agent import asistente_contexto, asistente_diario; print('ok')")
    r = subprocess.run([str(python), "-c", codigo], cwd=OLV, capture_output=True, text=True, timeout=120)
    if r.returncode or "ok" not in r.stdout:
        error("no se pueden importar asistente_contexto / asistente_diario:\n" + r.stderr.strip()[-800:])
    else:
        ok("asistente_contexto y asistente_diario importan")


if __name__ == "__main__":
    compilar()
    configs()
    if "--importar" in sys.argv:
        importar()
    print("\nTodo bien." if not errores else f"\n{len(errores)} problema(s).")
    sys.exit(1 if errores else 0)
