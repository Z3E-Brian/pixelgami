"""Servidor local de RVC para la voz de Asistente (localhost:12394).

Mantiene el modelo cargado y convierte cada frase que genera la TTS:
POST /convertir  {"entrada": "/ruta/frase.mp3", "salida": "/ruta/frase.wav"}
Lo usa edge_tts.py de Open-LLM-VTuber cuando ASISTENTE_RVC_URL está definido.
El modelo es la carpeta RVC_MODELO (un .pth y, si lo trae, su .index) y RVC_TONO los semitonos;
servidor.sh los toma de entorno.sh.
"""
import glob
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import soundfile as sf
from infer_rvc_python import BaseLoader

AQUI = os.path.dirname(os.path.abspath(__file__))
os.chdir(AQUI)  # rmvpe.pt se descarga/lee desde aquí
M = os.environ.get("RVC_MODELO", "voz")
PTH = sorted(glob.glob(os.path.join(M, "*.pth")))[0]
INDICE = next(iter(sorted(glob.glob(os.path.join(M, "*.index")))), "")

# Asistente: en CPU. En la GPU (torch +rocm7.2, only_cpu=False) iba a ~1 s por frase, pero el proceso
# deja la GPU al 99 % aun en reposo y Qwen (Ollama) caía de ~53 a ~7 tokens/s (2026-10-20)
conv = BaseLoader(only_cpu=False)
conv.apply_conf(
    tag="voz",
    file_model=PTH,
    pitch_algo="rmvpe+",
    pitch_lvl=int(os.environ.get("RVC_TONO", "0")),
    file_index=INDICE,
    index_influence=0.95 if INDICE else 0,
    respiration_median_filtering=3,
    envelope_ratio=1.0,
    consonant_breath_protection=0.1,
)
# precarga (HuBERT, RMVPE, modelo) para que la primera frase no tarde de más
if os.path.exists("entrada/base_dalia.mp3"):
    conv.generate_from_cache(audio_data="entrada/base_dalia.mp3", tag="voz")


class Manejador(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/convertir":
            self.send_error(404)
            return
        try:
            datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            audio, sr = conv.generate_from_cache(audio_data=datos["entrada"], tag="voz")
            sf.write(datos["salida"], audio, sr)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as e:  # la TTS cae a la voz original si esto falla
            self.send_error(500, str(e))

    def do_GET(self):  # comprobación de que está vivo
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"rvc")

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 12394), Manejador).serve_forever()
