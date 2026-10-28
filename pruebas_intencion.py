"""Pruebas del entendimiento con el modelo: el router (asistente_contexto._router) y, de cada función, router -> entender.
Solo interpreta: NO ejecuta nada.

    cd ~/.local/share/pixelgami/Open-LLM-VTuber && uv run python ../pruebas_intencion.py
    ... ../pruebas_intencion.py correo web     solo los casos de esas funciones
    ... ../pruebas_intencion.py nucleo         solo la charla

Los casos de cada función están en funciones/<función>/pruebas.py:
  ROUTER        (último mensaje de la asistente, mensaje anterior del usuario, lo que dice, temas esperados, palabras
                que deben aparecer en la orden reescrita)
  CADENA        (la asistente, el usuario antes, el usuario, lo esperado...) + revisar(caso, intención, aviso) ->
                (bien, cómo se ve). CON_CUALQUIER_TEMA = True prueba entender aunque el router no elija su tema;
                preparar() / limpiar() arman y quitan el estado que necesitan (una búsqueda ya hecha...).
Aquí solo están los de la charla, que es del núcleo: lo que NO debe ir a ninguna función.
"""
import datetime
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "Open-LLM-VTuber/src"))
sys.path.insert(0, str(Path(__file__).parent))  # funciones/
from open_llm_vtuber.agent import asistente_contexto as m  # noqa: E402

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


def probar_router(casos: list[tuple], nombre: str) -> int:
    fallos = 0
    for asistente, usuario_antes, texto, esperados, palabras in casos:
        conversacion(asistente, usuario_antes)
        r = m._router(texto) or {"temas": [], "orden": ""}
        temas, orden = set(r["temas"]), r.get("combinado", r["orden"]).lower()
        # "charla" junto con otro tema esperado no estorba; lo que importa es no perder ni inventar temas de acción
        accion = lambda t: t - {"charla"}  # noqa: E731
        ok = (accion(temas) == accion(esperados) if accion(esperados) else not accion(temas) or temas <= esperados)
        ok = ok and all(p in orden for p in palabras)
        fallos += not ok
        print(f"{'OK ' if ok else 'MAL'} {texto[:60]!r:64} -> {sorted(temas)} «{r['orden'][:70]}»")
    print(f"\n{len(casos) - fallos}/{len(casos)} bien (router: {nombre})\n")
    return fallos


def probar_cadena(f, pruebas) -> int:
    """Router -> f.entender y su aviso (las mismas funciones que preparar); entender no ejecuta nada."""
    casos = getattr(pruebas, "CADENA", [])
    if not casos:
        return 0
    getattr(pruebas, "preparar", lambda: None)()
    fallos = 0
    for caso in casos:
        asistente, usuario_antes, texto = caso[:3]
        conversacion(asistente, usuario_antes)
        r = m._router(texto)
        temas = set(r["temas"]) if r else set()
        pedido = m.pedido_de(texto, r, datetime.datetime.now(), temas)
        i = (f.entender(pedido, m._qwen_json)
             if f.tema in temas or getattr(pruebas, "CON_CUALQUIER_TEMA", False) else None)
        aviso = m.aviso_de(texto, [f.aviso(i)]) if i is not None else ""
        ok, visto = pruebas.revisar(caso, i, aviso)
        fallos += not ok
        print(f"{'MAL' if not ok else 'OK '} {texto[:55]!r:59} -> {sorted(temas)} {visto}")
    getattr(pruebas, "limpiar", lambda: None)()
    print(f"\n{len(casos) - fallos}/{len(casos)} bien (cadena: {f.nombre})\n")
    return fallos


def main() -> int:
    pedidas = set(sys.argv[1:])
    de_funciones = []
    for f in m.FUNCIONES:
        if pedidas and f.nombre not in pedidas:
            continue
        try:
            de_funciones.append((f, importlib.import_module(f"funciones.{f.nombre}.pruebas")))
        except ModuleNotFoundError:
            print(f"(funciones/{f.nombre} no trae pruebas.py)\n")
    fallos = 0
    casos = (CASOS if not pedidas or "nucleo" in pedidas else []) + [
        c for _, p in de_funciones for c in getattr(p, "ROUTER", [])]
    fallos += probar_router(casos, ", ".join(sorted(pedidas)) or "todo")
    fallos += sum(probar_cadena(f, p) for f, p in de_funciones)
    print(f"Total: {fallos} fallo(s).")
    return fallos


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
