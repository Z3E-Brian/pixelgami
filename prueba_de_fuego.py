"""Prueba de fuego del entendimiento con frases ajenas: MASSIVE (Amazon, CC BY 4.0; github.com/alexa/massive), las
frases de prueba en español. Solo interpreta: NO ejecuta nada.

    cd ~/.local/share/pixelgami/Open-LLM-VTuber
    uv run python ../prueba_de_fuego.py --massive RUTA/es-ES.jsonl --n 300 --voz 100 --salida informe.md

Toma n frases repartidas entre sus 59 intenciones (las mismas con la misma semilla), las pasa por el router y por
entender() de las funciones que eligió, y las compara con ESPERADO: qué tema tiene que salir y cuáles se aceptan.
Mide sobre todo dos cosas: que cada pedido llegue a su función y que ninguna función se robe lo que no es suyo
(domótica, cocina, transporte... no son de nadie: son charla).

Con --voz m, m de esas frases (primero las de temas propios) se dicen con Edge TTS, con un poco de ruido de fondo,
se transcriben con whisper-server (el de la asistente, en 127.0.0.1:12395; tiene que estar corriendo) y se vuelven a
probar: ¿aguanta los errores de transcripción?
"""
import argparse
import asyncio
import collections
import datetime
import io
import json
import random
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "Open-LLM-VTuber/src"))
sys.path.insert(0, str(Path(__file__).parent))
from open_llm_vtuber.agent import asistente_contexto as m  # noqa: E402

m.asistente_diario.ESPERA_DIARIO = 10**9  # que no se ponga a escribir el diario durante la prueba

# intención de MASSIVE -> (temas que tienen que salir, uno basta; temas que también se aceptan). Lo que no es de
# ninguna función es charla: ahí cualquier tema de acción es un robo.
RECORDATORIO, NADA = {"recordatorio"}, set()
ESPERADO = {
    "alarm_set": (RECORDATORIO, NADA), "alarm_query": (RECORDATORIO, NADA), "alarm_remove": (RECORDATORIO, NADA),
    "calendar_set": (RECORDATORIO, NADA), "calendar_remove": (RECORDATORIO, NADA),
    "calendar_query": (NADA, RECORDATORIO),  # "¿qué tengo mañana?" es charla con la agenda; "¿qué recordatorios...?" no
    "email_query": ({"correo"}, NADA), "email_sendemail": ({"correo"}, NADA),  # enviar: el correo dice que no puede
    "email_querycontact": (NADA, {"correo"}), "email_addcontact": (NADA, {"correo"}),
    "play_music": ({"musica"}, NADA), "music_query": ({"musica"}, NADA), "music_settings": ({"musica"}, NADA),
    "music_likeness": (NADA, {"musica"}), "music_dislikeness": (NADA, {"musica"}),
    "audio_volume_up": ({"musica"}, {"pc"}), "audio_volume_down": ({"musica"}, {"pc"}),
    "audio_volume_mute": (NADA, {"musica", "pc"}), "audio_volume_other": (NADA, {"musica", "pc"}),
    "play_radio": (NADA, {"musica", "web"}), "play_podcasts": (NADA, {"musica", "web"}),
    "play_audiobook": (NADA, {"musica", "web"}), "play_game": (NADA, {"ventanas"}),
    "news_query": ({"web"}, NADA),
    "datetime_convert": ({"hora_mundo"}, NADA),
    # datetime_query: con un lugar es hora_mundo; sin lugar, la de aquí (charla). Ver esperado()
    "qa_factoid": (NADA, {"web"}), "qa_definition": (NADA, {"web"}), "qa_maths": (NADA, {"web"}),
    "qa_currency": (NADA, {"web"}), "qa_stock": (NADA, {"web"}), "weather_query": (NADA, {"web"}),
    "recommendation_events": (NADA, {"web"}), "recommendation_locations": (NADA, {"web"}),
    "recommendation_movies": (NADA, {"web"}), "cooking_recipe": (NADA, {"web"}),
    "transport_query": (NADA, {"web"}), "transport_ticket": (NADA, {"web"}), "transport_traffic": (NADA, {"web"}),
    "transport_taxi": (NADA, {"web"}), "takeaway_order": (NADA, {"web"}), "takeaway_query": (NADA, {"web"}),
    "social_post": (NADA, NADA), "social_query": (NADA, {"web"}),
    "lists_createoradd": (NADA, RECORDATORIO), "lists_query": (NADA, RECORDATORIO), "lists_remove": (NADA, RECORDATORIO),
    "general_greet": (NADA, NADA), "general_joke": (NADA, NADA), "general_quirky": (NADA, {"web"}),
    **{i: (NADA, NADA) for i in ["iot_cleaning", "iot_coffee", "iot_hue_lightchange", "iot_hue_lightdim",
                                  "iot_hue_lightoff", "iot_hue_lighton", "iot_hue_lightup", "iot_wemo_off",
                                  "iot_wemo_on"]},
}
VOZ = "es-CR-JuanNeural"
WHISPER = "http://127.0.0.1:12395/inference"


def esperado(fila: dict) -> tuple[set, set]:
    if fila["intent"] == "datetime_query":
        return ({"hora_mundo"}, NADA) if "[place_name" in fila["annot_utt"] else (NADA, NADA)
    return ESPERADO[fila["intent"]]


def elegir(filas: list[dict], n: int, semilla: int = 7) -> list[dict]:
    """n frases de prueba repartidas por igual entre las intenciones (al azar, siempre las mismas)."""
    azar = random.Random(semilla)
    por_intencion = collections.defaultdict(list)
    for f in filas:
        if f["partition"] == "test":
            por_intencion[f["intent"]].append(f)
    for lista in por_intencion.values():
        azar.shuffle(lista)
    elegidas, ronda = [], 0
    while len(elegidas) < n and any(ronda < len(v) for v in por_intencion.values()):
        elegidas += [v[ronda] for v in por_intencion.values() if ronda < len(v)][: n - len(elegidas)]
        ronda += 1
    return elegidas


def resumen(intencion) -> str:
    """La intención de una función, corta, para el informe."""
    if isinstance(intencion, dict):
        claves = [k for k in ("acciones", "accion", "consulta", "quienes", "busqueda", "texto", "orden") if intencion.get(k)]
        return " ".join(f"{k}={intencion[k]!r}"[:60] for k in claves[:3]) or "{}"
    return repr(intencion)[:60]


def probar(texto: str, fila: dict) -> dict:
    m.asistente_diario._ultima_respuesta = ""
    m._conversacion["usuario"] = ""
    r = m._router(texto)
    temas = set(r["temas"]) if r else set()
    pedido = m.pedido_de(texto, r, datetime.datetime.now(), temas)
    intenciones = m.entender(pedido, temas)
    accion = temas - {"charla"}
    requerido, permitido = esperado(fila)
    falta = bool(requerido) and not requerido & accion
    sobra = accion - requerido - permitido
    return {"texto": texto, "intent": fila["intent"], "temas": sorted(temas), "orden": r["orden"] if r else "",
            "ok": not falta and not sobra, "falta": sorted(requerido) if falta else [], "sobra": sorted(sobra),
            "entendido": {f.tema: resumen(i) for f, i in intenciones.items()},
            "sin_entender": sorted(accion - {f.tema for f in intenciones})}


async def _decir(texto: str, mp3: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(texto, VOZ).save(str(mp3))


def oir(texto: str, carpeta: Path) -> str:
    """Lo que Whisper entiende de la frase dicha por Edge TTS con un poco de ruido de fondo."""
    mp3, wav = carpeta / f"{uuid.uuid4().hex}.mp3", carpeta / "voz.wav"
    asyncio.run(_decir(texto, mp3))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-f", "lavfi", "-i",
                    "anoisesrc=color=pink:amplitude=0.02", "-filter_complex",
                    "[0:a]aresample=16000[v];[1:a]aresample=16000[r];[v][r]amix=inputs=2:duration=first",
                    "-ac", "1", "-ar", "16000", str(wav)], check=True)
    limite = "----" + uuid.uuid4().hex
    cuerpo = io.BytesIO()
    for nombre, valor in (("response_format", "json"), ("temperature", "0.0")):
        cuerpo.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"{nombre}\"\r\n\r\n{valor}\r\n".encode())
    cuerpo.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voz.wav\"\r\n"
                 "Content-Type: audio/wav\r\n\r\n".encode() + wav.read_bytes() + f"\r\n--{limite}--\r\n".encode())
    req = urllib.request.Request(WHISPER, cuerpo.getvalue(), {"Content-Type": f"multipart/form-data; boundary={limite}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("text", "").strip()


def informe(resultados: list[dict], voz: list[dict]) -> str:
    lineas = ["# Prueba de fuego (MASSIVE, español)", ""]
    bien = sum(r["ok"] for r in resultados)
    lineas += [f"**Texto: {bien}/{len(resultados)} bien.**", ""]
    robos = collections.Counter(t for r in resultados for t in r["sobra"])
    faltas = collections.Counter(t for r in resultados for t in r["falta"])
    lineas += ["## Por tema", "", "| Tema | No llegó a su función | Se lo llevó sin ser suyo |", "|---|---|---|"]
    for t in sorted(set(robos) | set(faltas)):
        lineas.append(f"| {t} | {faltas[t]} | {robos[t]} |")
    lineas += ["", "## Por intención (solo las que fallan)", "", "| Intención | Bien | Fallos: temas que salieron |",
               "|---|---|---|"]
    por = collections.defaultdict(list)
    for r in resultados:
        por[r["intent"]].append(r)
    for intent, rs in sorted(por.items()):
        malos = [r for r in rs if not r["ok"]]
        if malos:
            salidos = collections.Counter(",".join(r["temas"]) or "(ninguno)" for r in malos)
            lineas.append(f"| {intent} | {len(rs) - len(malos)}/{len(rs)} | "
                          + "; ".join(f"{t} ×{n}" for t, n in salidos.most_common()) + " |")
    vacios = [r for r in resultados if r["sin_entender"]]
    lineas += ["", f"## El router eligió una función pero entender() no sacó nada ({len(vacios)})", ""]
    lineas += [f"- [{r['intent']}] «{r['texto']}» -> {r['sin_entender']}" for r in vacios]
    lineas += ["", "## Fallos", ""]
    for r in resultados:
        if not r["ok"]:
            lineas.append(f"- [{r['intent']}] «{r['texto']}» -> {r['temas']} «{r['orden']}»"
                          + (f" falta {r['falta']}" if r["falta"] else "") + (f" sobra {r['sobra']}" if r["sobra"] else "")
                          + (f" | {r['entendido']}" if r["entendido"] else ""))
    if voz:
        bien_voz = sum(v["ok"] for v in voz)
        cambian = [v for v in voz if v["ok"] != v["ok_texto"]]
        lineas += ["", "## Voz (Edge TTS + ruido -> Whisper)", "",
                   f"**{bien_voz}/{len(voz)} bien por voz** (las mismas por texto: {sum(v['ok_texto'] for v in voz)}). "
                   f"Cambian al pasar por la voz: {len(cambian)}.", ""]
        lineas += [f"- [{v['intent']}] «{v['original']}» -> oyó «{v['texto']}» -> {v['temas']}"
                   + (" (bien por texto, MAL por voz)" if v["ok_texto"] else " (mal por texto, bien por voz)")
                   for v in cambian]
        lineas += ["", "### Transcripciones distintas del original", ""]
        lineas += [f"- «{v['original']}» -> «{v['texto']}»" for v in voz
                   if v["texto"].lower().strip(" .¿?¡!") != v["original"].lower().strip(" .¿?¡!")]
    return "\n".join(lineas) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--massive", required=True, help="es-ES.jsonl de MASSIVE")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--voz", type=int, default=0, help="cuántas probar también por voz (necesita whisper-server)")
    ap.add_argument("--salida", default="prueba_de_fuego.md")
    a = ap.parse_args()
    filas = [json.loads(linea) for linea in Path(a.massive).read_text().splitlines() if linea.strip()]
    elegidas = elegir(filas, a.n)
    resultados = []
    for i, fila in enumerate(elegidas, 1):
        r = probar(fila["utt"], fila)
        resultados.append(r)
        print(f"{i:>3} {'OK ' if r['ok'] else 'MAL'} [{fila['intent']}] {fila['utt'][:60]!r} -> {r['temas']}", flush=True)
    voz = []
    if a.voz:
        # primero las de temas propios (las que más importa que se entiendan por voz)
        propias = sorted(zip(elegidas, resultados), key=lambda x: not esperado(x[0])[0])[: a.voz]
        with tempfile.TemporaryDirectory(prefix="fuego-voz-") as carpeta:
            for i, (fila, r_texto) in enumerate(propias, 1):
                oido = oir(fila["utt"], Path(carpeta))
                r = probar(oido, fila)
                voz.append({**r, "original": fila["utt"], "ok_texto": r_texto["ok"]})
                print(f"voz {i:>3} {'OK ' if r['ok'] else 'MAL'} «{fila['utt'][:45]}» -> «{oido[:45]}» {r['temas']}",
                      flush=True)
    Path(a.salida).write_text(informe(resultados, voz))
    Path(a.salida).with_suffix(".json").write_text(json.dumps({"texto": resultados, "voz": voz}, ensure_ascii=False,
                                                              indent=1))
    print(f"\nInforme: {a.salida}")


if __name__ == "__main__":
    main()
