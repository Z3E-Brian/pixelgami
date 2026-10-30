"""Pruebas del entendimiento con el modelo: el router (asistente_contexto._router) y, de cada función, router -> entender.
Solo interpreta: NO ejecuta nada.

    cd ~/.local/share/pixelgami/Open-LLM-VTuber && uv run python ../pruebas_intencion.py
    ... ../pruebas_intencion.py correo web     solo los casos de esas funciones
    ... ../pruebas_intencion.py nucleo         solo la charla
    ... ../pruebas_intencion.py --modelo qwen3:8b                  el router con otro modelo de Ollama
    ... ../pruebas_intencion.py --modelo gemini:gemini-3.5-flash --pausa 7   con Gemini (pausa: su cuota por minuto)
    ... ../pruebas_intencion.py --solo-router  sin la cadena router -> entender (más rápido, para comparar modelos)

Del router sale además un reporte (evaluacion/metrica.py): % de acierto por tema, matriz de confusión y tiempo por
mensaje, guardado en resultados/eval_<fecha>_<modelo>.json y .csv.

Los casos de cada función están en funciones/<función>/pruebas.py:
  ROUTER        (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras
                que deben aparecer en la orden reescrita)
  CADENA        (la asistente, el usuario antes, el usuario, lo esperado...) + revisar(caso, intención, aviso) ->
                (bien, cómo se ve). CON_CUALQUIER_TEMA = True prueba entender aunque el router no elija su tema;
                preparar() / limpiar() arman y quitan el estado que necesitan (una búsqueda ya hecha...).
Aquí solo están los de la charla, que es del núcleo: lo que NO debe ir a ninguna función.
"""
import argparse
import datetime
import functools
import importlib
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "Open-LLM-VTuber/src"))
sys.path.insert(0, str(BASE))  # funciones/, evaluacion/
from open_llm_vtuber.agent import asistente_contexto as m  # noqa: E402
from evaluacion import metrica, modelos  # noqa: E402

m.asistente_diario.ESPERA_DIARIO = 10**9  # que no se ponga a escribir el diario durante la prueba

CASOS = [
    ("", "", "hola asistente, cómo estás", {"charla"}, []),
    ("¿Quieres que ponga música?", "", "no gracias", {"charla"}, []),
    ("", "", "me encanta el nuevo intro de texto", {"charla"}, ["me encanta"]),
    ("", "", "Pero es que la RAM depende, porque no todas las RAM son iguales, digamos, la de laptop es diferente",
     {"charla"}, []),
    ("", "", "Lo malo es que ahorita tiene un modelo muy lento, entonces mientras le llega, piensa", {"charla"}, []),
    ("", "", "di aaaaaaaaaaaaa. luego espera y di hooooolaaaaaa amigos. quiero probar tus animaciones", {"charla"}, []),
    ("", "", "muéstrame tu cara triste, luego enojada y luego hazme un guiño juguetón", {"charla"}, []),
    ("Hay 4 correos sin leer.", "revisa el correo", "¡Me aprecio tu opinión!", {"charla"}, []),
    ("", "", "solo queria apreciar lo q he estado haciendo o sea tu", {"charla"}, []),
    ("", "", "apunta es tu dia de nacimiento jeje", {"charla"}, []),
]


def conversacion(asistente: str, usuario_antes: str) -> None:
    """Deja la conversación como si la asistente hubiera dicho `asistente` y el usuario antes `usuario_antes`."""
    m.asistente_diario._ultima_respuesta = asistente
    m._conversacion["usuario"] = usuario_antes


def probar_router(casos: list[tuple], modelo, nombre_modelo: str, pausa: float = 0.0) -> list[metrica.Medida]:
    def enrutar(caso):
        conversacion(caso[0], caso[1])
        return m._router(caso[2], modelo)

    medidas = []
    for med in metrica.medir(casos, enrutar, pausa):
        medidas.append(med)
        print(f"{'OK ' if med.bien else 'MAL'} {med.texto[:60]!r:64} -> {sorted(med.temas)} «{med.orden[:70]}» "
              f"{med.segundos:.1f} s")
    print(f"\n{sum(x.bien for x in medidas)}/{len(medidas)} bien (router: {nombre_modelo})\n")
    return medidas


def probar_cadena(f, pruebas, modelo) -> int:
    """Router -> f.entender y su aviso (las mismas funciones que preparar); entender no ejecuta nada."""
    casos = getattr(pruebas, "CADENA", [])
    if not casos:
        return 0
    getattr(pruebas, "preparar", lambda: None)()
    fallos = 0
    for caso in casos:
        asistente, usuario_antes, texto = caso[:3]
        conversacion(asistente, usuario_antes)
        r = m._router(texto, modelo)
        temas = set(r["temas"]) if r else set()
        pedido = m.pedido_de(texto, r, datetime.datetime.now(), temas)
        i = (f.entender(pedido, modelo)
             if f.tema in temas or getattr(pruebas, "CON_CUALQUIER_TEMA", False) else None)
        aviso = m.aviso_de(texto, [f.aviso(i)]) if i is not None else ""
        ok, visto = pruebas.revisar(caso, i, aviso)
        fallos += not ok
        print(f"{'MAL' if not ok else 'OK '} {texto[:55]!r:59} -> {sorted(temas)} {visto}")
    getattr(pruebas, "limpiar", lambda: None)()
    print(f"\n{len(casos) - fallos}/{len(casos)} bien (cadena: {f.nombre})\n")
    return fallos


def main() -> int:
    a = argparse.ArgumentParser(description="Pruebas del router y de cada función con el modelo (no ejecuta nada).")
    a.add_argument("funciones", nargs="*", help="solo los casos de estas funciones ('nucleo': la charla)")
    a.add_argument("--modelo", help=f"quién hace de router: qwen3:8b, ollama:<modelo> o gemini:<modelo> "
                                    f"(por defecto el de conf.yaml: {m.MODELO_LOCAL})")
    a.add_argument("--pausa", type=float, default=0.0, help="segundos entre mensajes (cuota de una API)")
    a.add_argument("--solo-router", action="store_true", help="sin las cadenas router -> entender")
    a.add_argument("--resultados", type=Path, default=BASE / "resultados", help="dónde guardar el reporte")
    op = a.parse_args()
    nombre_modelo, modelo = modelos.elegir(op.modelo or m.MODELO_LOCAL,
                                           lambda nombre: functools.partial(m._qwen_json, nombre_modelo=nombre))
    pedidas = set(op.funciones)
    de_funciones = []
    for f in m.FUNCIONES:
        if pedidas and f.nombre not in pedidas:
            continue
        try:
            de_funciones.append((f, importlib.import_module(f"funciones.{f.nombre}.pruebas")))
        except ModuleNotFoundError:
            print(f"(funciones/{f.nombre} no trae pruebas.py)\n")
    casos = (CASOS if not pedidas or "nucleo" in pedidas else []) + [
        c for _, p in de_funciones for c in getattr(p, "ROUTER", [])]
    fecha = datetime.datetime.now()
    # un mensaje sin medir: que la carga del modelo (Ollama en frío tarda varios segundos) no cuente en el tiempo
    conversacion("", "")
    m._router("hola", modelo)
    medidas = probar_router(casos, modelo, nombre_modelo, op.pausa)
    fallos = sum(not x.bien for x in medidas)
    if medidas:
        rep = metrica.reporte(medidas, nombre_modelo, fecha)
        print(metrica.como_texto(rep))
        ruta_json, ruta_csv = metrica.guardar(rep, medidas, op.resultados)
        print(f"\nReporte: {ruta_json} y {ruta_csv}\n")
    if not op.solo_router:
        fallos += sum(probar_cadena(f, p, modelo) for f, p in de_funciones)
    print(f"Total: {fallos} fallo(s).")
    return fallos


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
