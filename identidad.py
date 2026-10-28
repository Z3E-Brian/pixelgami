"""Quién es quién: el nombre de la asistente, el del usuario y los datos de su perfil.

Los nombres salen de character_config en conf.yaml (character_name y human_name), el mismo
lugar donde Open-LLM-VTuber los usa para la interfaz; lo demás (género, lugar, navegador, correo,
alias...) sale de perfil.yaml. La zona horaria es la del sistema salvo que el perfil diga otra.

Los textos para el modelo se escriben con marcadores y pasan por nombres():
  {asistente} {usuario} {lugar} {sistema} {dialecto} {navegador}
  regex: {asistente_re} {usuario_re} {navegador_re}
  género del usuario:    {él} {Él} (él/ella)   {lo} (lo/la)   {o} (o/a: "molest{o}")
  género de la asistente: {ella} (ella/él)   {la} (la/lo)   {a} (a/o: "sol{a}")   {la_asistente}
"""
import os
import re
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
_personaje = yaml.safe_load((BASE / "Open-LLM-VTuber/conf.yaml").read_text())["character_config"]
ASISTENTE: str = _personaje["character_name"]
USUARIO: str = _personaje["human_name"]
# el modelo local de Ollama: el mismo que responde (ollama_llm en conf.yaml) hace de router e intérprete
MODELO_LOCAL: str = ((_personaje.get("agent_config", {}).get("llm_configs", {}).get("ollama_llm") or {})
                     .get("model") or "qwen3:8b")
PERFIL: dict = yaml.safe_load((BASE / "perfil.yaml").read_text()) or {}


def _zona_del_sistema() -> str:
    """'America/Mexico_City' a partir de /etc/localtime (enlace a /usr/share/zoneinfo/...)."""
    destino = os.path.realpath("/etc/localtime")
    return destino.split("zoneinfo/", 1)[1] if "zoneinfo/" in destino else "UTC"


ZONA: str = PERFIL.get("zona_horaria") or _zona_del_sistema()
LUGAR: str = PERFIL.get("lugar", "")
NAVEGADOR: str = PERFIL.get("navegador", "el navegador")
_FEMENINO = {"f", "femenino", "mujer"}
_usuario_f = str(PERFIL.get("genero_usuario", "m")).lower() in _FEMENINO
_asistente_f = str(PERFIL.get("genero_asistente", "f")).lower() in _FEMENINO
# lo que se le da a Whisper para que acierte nombres propios (nombre de la asistente + vocabulario del perfil)
PISTA_VOZ: str = f"{ASISTENTE}, " + " ".join(str(PERFIL.get("pista_voz", "")).split())

def _nombre_re(nombre: str) -> str:
    """Regex del nombre que acepta guion, espacio o nada entre partes ("ia-chan", "ia chan", "iachan")."""
    return r"[\s-]?".join(re.escape(p) for p in re.split(r"[\s-]+", nombre.lower()))


_MARCAS = {
    "{asistente}": ASISTENTE, "{usuario}": USUARIO, "{lugar}": LUGAR, "{navegador}": NAVEGADOR,
    "{sistema}": PERFIL.get("sistema", "Linux"), "{dialecto}": PERFIL.get("dialecto", "español"),
    "{asistente_re}": _nombre_re(ASISTENTE), "{usuario_re}": _nombre_re(USUARIO),
    "{navegador_re}": re.escape(NAVEGADOR.lower()),
    "{él}": "ella" if _usuario_f else "él", "{Él}": "Ella" if _usuario_f else "Él",
    "{lo}": "la" if _usuario_f else "lo", "{o}": "a" if _usuario_f else "o",
    "{ella}": "ella" if _asistente_f else "él", "{la}": "la" if _asistente_f else "lo",
    "{a}": "a" if _asistente_f else "o", "{la_asistente}": "la asistente" if _asistente_f else "el asistente",
}


def nombres(texto: str) -> str:
    """El texto con los nombres y el género reales en lugar de los marcadores."""
    for marca, valor in _MARCAS.items():
        texto = texto.replace(marca, valor)
    return texto


if __name__ == "__main__":  # servidor.sh: identidad.py pista_voz
    import sys
    print({"pista_voz": PISTA_VOZ, "zona": ZONA}[sys.argv[1]])
