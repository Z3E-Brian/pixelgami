#!/usr/bin/env python3
"""Agrega un modelo Live2D descargado (Cubism 3/4/5: carpeta con un .model3.json) a la asistente.

    python3 herramientas/agregar-modelo.py ~/Descargas/MiModelo [--nombre robot] [--usar]

- Copia la carpeta a Open-LLM-VTuber/live2d-models/<nombre>/.
- Si hay expresiones (.exp3.json) que el .model3.json no declara, las agrega (pasa seguido con modelos
  hechos para VTube Studio, que las maneja aparte).
- Propone el emotionMap mirando el nombre y lo que mueve cada expresión (ojos sonrientes -> alegre,
  sonrojo -> tímida, cejas caídas y boca hacia abajo -> triste...). Revísalo: es una propuesta.
- Escribe la entrada en model_dict.json (la reemplaza si ya existía) y, con --usar, la deja activa en conf.yaml.
Ver docs/MODELOS.md.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OLV = RAIZ / "Open-LLM-VTuber"

# Las emociones que usan la persona y el código (persona_prompt, cara_por_frase). Si el modelo no tiene una,
# se usa la primera de su lista de parecidas que sí tenga; neutral va al final del mapa a propósito: el modelo
# de lenguaje tiende a usar la primera emoción de la lista que se le muestra.
PARECIDAS = {
    "joy": ["happy"], "happy": ["joy"], "excited": ["joy", "happy", "surprise"], "love": ["shy", "joy"],
    "shy": ["embarrassed", "love", "joy"], "embarrassed": ["shy", "sad"], "sad": ["worried"],
    "worried": ["sad", "fear"], "fear": ["surprise", "worried"], "nervous": ["fear", "embarrassed"],
    "surprise": ["excited", "fear"], "curious": ["thinking", "surprise", "excited"],
    "thinking": ["curious"], "smirk": ["playful", "joy"], "playful": ["smirk", "joy"],
    "wink": ["playful", "smirk", "joy"], "angry": ["disgust"], "disgust": ["angry"],
}
SINONIMOS = {"sadness": "sad", "crying": "sad", "surprised": "surprise", "anger": "angry"}
# Accesorios y ropa que algunos modelos tienen como "expresiones": no son caras
ACCESORIO = re.compile(r"dress|cloth|outfit|hat|glass|fan|hand|weapon|item|toggle|ropa|vestido|abanico|lentes|gorro", re.I)
POR_NOMBRE = [  # palabras en el nombre del archivo de la expresión -> emoción (inglés, español, japonés)
    (r"neutral|normal|default|通常", "neutral"),
    (r"smile|happy|joy|laugh|alegr|feliz|content|sonris|warai|笑|喜|楽", "joy"),
    (r"sad|cry|tear|trist|llor|naki|泣|悲", "sad"), (r"angry|anger|mad|enoj|enfad|ikari|怒", "angry"),
    (r"surpri|shock|sorpres|asombr|odoro|驚|びっくり", "surprise"),
    (r"shy|blush|timid|sonroj|vergüen|verguen|uwu|tere|照|赤", "shy"),
    (r"love|heart|amor|enamor|coraz|ハート|好", "love"), (r"wink|guiñ|guin|ウィンク", "wink"),
    (r"think|hmm|pens|考", "thinking"), (r"fear|scare|miedo|asust|怖", "fear"),
    (r"smug|smirk|picar|burl|doya|ドヤ|にやり", "smirk"),
]


def _emocion_por_parametros(params: dict) -> str:
    """Lo que muestra una expresión según sus parámetros estándar de Cubism (ParamEyeLSmile, ParamCheek...)."""
    v = lambda *nombres: max((params.get(n, 0) for n in nombres), default=0)
    if v("ParamMouthAngry", "ParamMouthAngryLine") > 0.5 or v("ParamEyeLForm", "ParamEyeRForm") > 0.5:
        return "angry"
    if v("ParamCheek") > 0.5:
        return "shy"
    if v("ParamEyeLSmile", "ParamEyeRSmile") > 0.5:
        return "excited" if v("ParamEyeLOpen", "ParamEyeROpen") > 1 or v("ParamEyeEffect") > 0.5 else "joy"
    if v("ParamEyeLOpen", "ParamEyeROpen") > 1:
        return "surprise"
    if min(params.get("ParamBrowLAngle", 0), params.get("ParamBrowRAngle", 0)) < -0.5 or params.get("ParamMouthDown", 0) > 0.5:
        return "sad"
    if "ParamEyeLOpen" in params and v("ParamEyeLOpen", "ParamEyeROpen") < 0.2:
        return "thinking"  # ojos cerrados sin sonrisa
    if params and all(abs(x) < 0.05 for k, x in params.items() if k not in ("ParamEyeLOpen", "ParamEyeROpen")):
        return "neutral"
    return ""


def _emocion(nombre: str, archivo: Path) -> str:
    if ACCESORIO.search(nombre):
        return "accesorio"
    for patron, emocion in POR_NOMBRE:
        if re.search(patron, nombre, re.I):
            return emocion
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        return _emocion_por_parametros({p["Id"]: p.get("Value", 0) for p in datos.get("Parameters", [])})
    except (OSError, ValueError, KeyError):
        return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", type=Path, help="carpeta del modelo descargado (la que contiene el .model3.json)")
    ap.add_argument("--nombre", help="nombre corto para model_dict.json (por defecto, el de la carpeta)")
    ap.add_argument("--usar", action="store_true", help="dejarlo como modelo activo en conf.yaml")
    a = ap.parse_args()

    modelos = sorted(a.carpeta.expanduser().resolve().rglob("*.model3.json"))
    if not modelos:
        sys.exit("No encontré ningún .model3.json: ¿es un modelo de Cubism 3 o posterior? (los de Cubism 2 usan .model.json)")
    origen_json = modelos[0]
    nombre = re.sub(r"[^a-z0-9_]+", "_", (a.nombre or origen_json.parent.name).lower()).strip("_")
    destino = OLV / "live2d-models" / nombre
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origen_json.parent, destino)
    ruta_json = destino / origen_json.name
    modelo = json.loads(ruta_json.read_text(encoding="utf-8"))
    refs = modelo.setdefault("FileReferences", {})

    # expresiones sueltas que el .model3.json no declara
    declaradas = {e["File"] for e in refs.get("Expressions", [])}
    sueltas = [p.relative_to(destino).as_posix() for p in sorted(destino.rglob("*.exp3.json"))
               if p.relative_to(destino).as_posix() not in declaradas]
    if sueltas:
        refs.setdefault("Expressions", []).extend({"Name": Path(f).name.removesuffix(".exp3.json"), "File": f}
                                                  for f in sueltas)
        ruta_json.write_text(json.dumps(modelo, indent=2, ensure_ascii=False), encoding="utf-8")
    expresiones = refs.get("Expressions", [])
    grupos = {g["Name"]: g.get("Ids", []) for g in modelo.get("Groups", [])}
    movimientos = refs.get("Motions", {})

    # emotionMap propuesto
    propuesta = {}
    for i, e in enumerate(expresiones):
        emocion = _emocion(e["Name"], destino / e["File"])
        print(f"  expresión {i}: {e['Name']:<24} -> "
              + {"": "(sin adivinar: asígnala a mano)", "accesorio": "(accesorio, no es una cara)"}.get(emocion, emocion))
        if emocion and emocion != "accesorio" and emocion not in propuesta:
            propuesta[emocion] = i
    mapa = {}
    if expresiones:
        neutral = propuesta.get("neutral", 0)
        mapa = {e: i for e, i in propuesta.items() if e in PARECIDAS}
        for _ in range(3):  # las que faltan toman la de una parecida (en cadena: nervous -> fear -> surprise)
            for emocion, parecidas in PARECIDAS.items():
                primera = next((mapa[p] for p in parecidas if p in mapa), None)
                if emocion not in mapa and primera is not None:
                    mapa[emocion] = primera
        mapa = {e: mapa.get(e, neutral) for e in PARECIDAS}
        for sinonimo, emocion in SINONIMOS.items():
            mapa[sinonimo] = mapa[emocion]
        mapa["neutral"] = neutral

    reposo = next((g for g in movimientos if g.lower() == "idle"), next(iter(movimientos), ""))
    entrada = {
        "name": nombre,
        "description": f"Agregado con agregar-modelo.py desde {origen_json.parent.name}",
        "url": f"/live2d-models/{nombre}/{origen_json.name}",
        "kScale": 0.5, "initialXshift": 0, "initialYshift": 0, "kXOffset": 1150,
        "idleMotionGroupName": reposo,
        "emotionMap": mapa,
    }
    ruta_dict = OLV / "model_dict.json"
    lista = [m for m in json.loads(ruta_dict.read_text(encoding="utf-8")) if m["name"] != nombre] + [entrada]
    ruta_dict.write_text(json.dumps(lista, indent=2, ensure_ascii=False), encoding="utf-8")

    if a.usar:
        conf = OLV / "conf.yaml"
        texto = re.sub(r"(live2d_model_name:\s*)'[^']*'", rf"\g<1>'{nombre}'", conf.read_text(encoding="utf-8"), count=1)
        conf.write_text(texto, encoding="utf-8")

    print(f"\nListo: '{nombre}' en live2d-models/ y en model_dict.json" + (" (activo en conf.yaml)." if a.usar else "."))
    if sueltas:
        print(f"  Agregué {len(sueltas)} expresión(es) que el .model3.json no declaraba.")
    avisos = []
    if not expresiones:
        avisos.append("No trae expresiones: la cara no va a cambiar con la emoción (solo movimientos y parpadeo).")
    if not grupos.get("LipSync"):
        avisos.append("Sin grupo LipSync: la boca puede no moverse al hablar (en Cubism Viewer: Groups > LipSync con ParamMouthOpenY).")
    if not grupos.get("EyeBlink"):
        avisos.append("Sin grupo EyeBlink: no va a parpadear solo.")
    if not reposo:
        avisos.append("Sin movimientos: se va a quedar quieto (sin animación de reposo).")
    for aviso in avisos:
        print("  Ojo:", aviso)
    print("  Revisa el emotionMap en model_dict.json y ajusta kScale / initialYshift si se ve muy grande o cortado.")


if __name__ == "__main__":
    main()
