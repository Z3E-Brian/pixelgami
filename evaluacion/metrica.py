"""La métrica del router: cada caso etiquetado de pruebas_intencion.py se mide (bien o mal, qué temas eligió y
cuánto tardó) y con todos se arma un reporte: % de acierto por tema, matriz de confusión entre temas y tiempo
promedio por mensaje. El reporte se guarda en resultados/ como JSON (completo) y CSV (una fila por caso, para
comparar corridas de distintos modelos en una hoja de cálculo o en SQL).

Aquí no hay ningún modelo: medir() recibe la función que enruta, así se prueba con un router simulado.
"""
import csv
import datetime
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

CHARLA = "charla"
NINGUNO = "—"  # en la matriz: el router no eligió nada en su lugar (columna) o eligió de más (ver pares)


def accion(temas) -> set[str]:
    """Los temas que piden hacer algo (todos menos la charla)."""
    return set(temas) - {CHARLA}


def bien(esperados, temas, orden: str, palabras: Iterable[str]) -> bool:
    """¿El router acertó? Lo que importa es no perder ni inventar temas de acción: "charla" junto con otro tema
    esperado no estorba. Y la orden reescrita debe traer las palabras pedidas (en minúsculas)."""
    esperados, temas = set(esperados), set(temas)
    if accion(esperados):
        ok = accion(temas) == accion(esperados)
    else:
        ok = not accion(temas) or temas <= esperados
    return ok and all(p in orden for p in palabras)


def pares(esperados, temas) -> list[tuple[str, str]]:
    """Las casillas (tema esperado, tema elegido) que suma un caso a la matriz de confusión:
    - cada tema esperado que el router eligió va en la diagonal, y cada tema de acción que eligió de más, en su fila
      ("charla" de más junto a la acción pedida no cuenta, igual que en bien());
    - un tema esperado que perdió va con lo que eligió en su lugar (también "charla": "revisa el correo" -> charla
      es una confusión) o, si no eligió nada más, en la columna NINGUNO."""
    esperados, temas = set(esperados), set(temas)
    de_mas = accion(temas) - esperados
    casillas = []
    for e in sorted(esperados):
        if e in temas:
            casillas += [(e, e)] + [(e, s) for s in sorted(de_mas)]
        else:
            casillas += [(e, s) for s in sorted(de_mas or temas - esperados)] or [(e, NINGUNO)]
    return casillas


@dataclass(frozen=True)
class Medida:
    """Un caso ya pasado por el router."""
    texto: str
    esperados: frozenset
    temas: frozenset  # los que eligió (vacío si no respondió)
    orden: str  # la orden reescrita
    respondio: bool  # False: el modelo no respondió (Ollama apagado, cuota de Gemini...); cuenta como mal
    bien: bool
    segundos: float


def medir(casos: Iterable[tuple], enrutar: Callable[[tuple], dict | None], pausa: float = 0.0,
          reloj: Callable[[], float] = time.perf_counter) -> Iterator[Medida]:
    """Pasa cada caso (asistente, usuario antes, texto, temas esperados, palabras) por enrutar(caso), que devuelve lo
    del router ({"temas", "orden", "combinado"}) o None. Una Medida por caso, a medida que van saliendo. pausa:
    segundos de espera entre casos (para la cuota de una API), fuera del tiempo medido."""
    for n, caso in enumerate(casos):
        if n and pausa:
            time.sleep(pausa)
        texto, esperados, palabras = caso[2], caso[3], caso[4]
        inicio = reloj()
        r = enrutar(caso)
        segundos = reloj() - inicio
        temas = frozenset(r["temas"]) if r else frozenset()
        orden = (r.get("combinado") or r.get("orden") or "") if r else ""
        yield Medida(texto, frozenset(esperados), temas, r["orden"] if r else "", r is not None,
                     r is not None and bien(esperados, temas, orden.lower(), palabras), segundos)


def _orden_temas(temas: Iterable[str]) -> list[str]:
    """Por nombre, con la charla al final."""
    return sorted(set(temas), key=lambda t: (t == CHARLA, t))


def reporte(medidas: list[Medida], modelo: str, fecha: datetime.datetime) -> dict:
    """El resumen de una corrida, listo para guardar como JSON."""
    temas = _orden_temas(t for m in medidas for t in m.esperados | m.temas)
    por_tema = {}
    for t in temas:
        suyos = [m for m in medidas if t in m.esperados]
        if suyos:
            aciertos = sum(m.bien for m in suyos)
            por_tema[t] = {"casos": len(suyos), "bien": aciertos, "acierto": round(100 * aciertos / len(suyos), 1)}
    columnas = temas + [NINGUNO]
    matriz = {t: dict.fromkeys(columnas, 0) for t in por_tema}
    for m in medidas:
        for esperado, elegido in pares(m.esperados, m.temas):
            matriz[esperado][elegido] += 1
    tiempos = [m.segundos for m in medidas]
    aciertos = sum(m.bien for m in medidas)
    return {
        "modelo": modelo,
        "fecha": fecha.isoformat(timespec="seconds"),
        "casos": len(medidas),
        "bien": aciertos,
        "acierto": round(100 * aciertos / len(medidas), 1) if medidas else 0.0,
        "sin_respuesta": sum(not m.respondio for m in medidas),
        "tiempo_promedio_s": round(statistics.fmean(tiempos), 3) if tiempos else 0.0,
        "tiempo_mediana_s": round(statistics.median(tiempos), 3) if tiempos else 0.0,
        "tiempo_max_s": round(max(tiempos), 3) if tiempos else 0.0,
        "por_tema": por_tema,
        "matriz": {"filas": "tema esperado", "columnas": "tema elegido", "valores": matriz},
        "fallos": [{"texto": m.texto, "esperados": _orden_temas(m.esperados), "elegidos": _orden_temas(m.temas),
                    "orden": m.orden} for m in medidas if not m.bien],
    }


def nombre_archivo(modelo: str, fecha: datetime.datetime) -> str:
    """eval_<fecha>_<modelo> sin caracteres raros: "qwen3:8b" -> "eval_2026-10-29_2130_qwen3-8b"."""
    return f"eval_{fecha:%Y-%m-%d_%H%M}_{re.sub(r'[^A-Za-z0-9._-]+', '-', modelo).strip('-')}"


CAMPOS_CSV = ["fecha", "modelo", "texto", "esperados", "elegidos", "respondio", "bien", "segundos"]


def guardar(rep: dict, medidas: list[Medida], carpeta: Path) -> tuple[Path, Path]:
    """Escribe <carpeta>/eval_<fecha>_<modelo>.json (el reporte) y .csv (un caso por fila). Devuelve las dos rutas."""
    carpeta.mkdir(parents=True, exist_ok=True)
    fecha = datetime.datetime.fromisoformat(rep["fecha"])
    base = carpeta / nombre_archivo(rep["modelo"], fecha)
    ruta_json, ruta_csv = base.with_suffix(".json"), base.with_suffix(".csv")
    ruta_json.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
    with ruta_csv.open("w", newline="") as f:
        escritor = csv.DictWriter(f, CAMPOS_CSV)
        escritor.writeheader()
        for m in medidas:
            escritor.writerow({"fecha": rep["fecha"], "modelo": rep["modelo"], "texto": m.texto,
                               "esperados": " ".join(_orden_temas(m.esperados)),
                               "elegidos": " ".join(_orden_temas(m.temas)), "respondio": int(m.respondio),
                               "bien": int(m.bien), "segundos": round(m.segundos, 3)})
    return ruta_json, ruta_csv


def como_texto(rep: dict) -> str:
    """El reporte para la terminal: el total, el acierto por tema y la matriz de confusión."""
    lineas = [f"Router con {rep['modelo']} ({rep['fecha']}): {rep['bien']}/{rep['casos']} bien = {rep['acierto']} %"
              f", {rep['sin_respuesta']} sin respuesta; {rep['tiempo_promedio_s']} s promedio por mensaje"
              f" (mediana {rep['tiempo_mediana_s']} s, máximo {rep['tiempo_max_s']} s)", "", "Acierto por tema:"]
    ancho = max((len(t) for t in rep["por_tema"]), default=5)
    for t, d in rep["por_tema"].items():
        lineas.append(f"  {t:<{ancho}}  {d['bien']:>3}/{d['casos']:<3} {d['acierto']:>5} %")
    valores = rep["matriz"]["valores"]
    if valores:
        columnas = list(next(iter(valores.values())))
        lineas += ["", "Matriz de confusión (fila: esperado, columna: elegido; " + NINGUNO + ": ninguno):",
                   " " * (ancho + 2) + " ".join(f"{c[:7]:>7}" for c in columnas)]
        for t, fila in valores.items():
            lineas.append(f"  {t:<{ancho}}" + " ".join(f"{fila[c] or '.':>7}" for c in columnas))
    return "\n".join(lineas)
