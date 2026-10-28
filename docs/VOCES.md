# Voces

La voz sale en dos pasos: **Edge TTS** convierte el texto en voz (gratis, por internet, sin GPU) y, si quieres,
**RVC** cambia el timbre por el de un modelo de voz (local, opcional).

## Edge TTS (la base)

En `Open-LLM-VTuber/conf.yaml`:

```yaml
tts_config:
  tts_model: 'edge_tts'
  edge_tts:
    voice: 'es-MX-DaliaNeural'
```

Ver todas las voces y escuchar una:

```bash
cd Open-LLM-VTuber
uv run edge-tts --list-voices | grep ^es-
uv run edge-tts --voice es-MX-JorgeNeural --text "Hola, soy tu asistente." --write-media /tmp/prueba.mp3 && mpv /tmp/prueba.mp3
```

Algunas en español: `es-MX-DaliaNeural`, `es-MX-JorgeNeural` (México), `es-ES-ElviraNeural`, `es-ES-AlvaroNeural`
(España), `es-US-PalomaNeural`, `es-US-AlonsoNeural` (EE. UU.), `es-AR-ElenaNeural`, `es-CO-SalomeNeural`,
`es-CR-MariaNeural`… La velocidad se ajusta en `src/open_llm_vtuber/tts/edge_tts.py` (`rate`, por defecto +8 %).

Si un día deja de sonar (error 403), Microsoft cambió algo: actualiza el paquete con
`uv lock --upgrade-package edge-tts && uv sync`.

## RVC (voz propia, opcional)

[RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) toma la voz de Edge TTS y le pone el
timbre de un modelo entrenado (un `.pth` y, a veces, un `.index`). Corre en `rvc/servidor_rvc.py` (puerto 12394);
si no está o falla, la asistente habla con la voz de Edge TTS sin más.

1. Crea su entorno (Python 3.10; torch en CPU, o la versión ROCm/CUDA para GPU):
   ```bash
   cd rvc
   uv venv --python 3.10 .venv
   uv pip install --python .venv infer-rvc-python soundfile
   ```
2. Pon el modelo en una carpeta dentro de `rvc/` (p. ej. `rvc/voz/mi_voz.pth` y `rvc/voz/mi_voz.index`).
3. En `entorno.sh`: `export RVC_MODELO=voz` y `export RVC_TONO=0` (semitonos: +12 sube una octava; para pasar de
   una voz de hombre a una de mujer suele ir entre +5 y +12).
4. Reinicia la asistente. `servidor.sh` arranca RVC solo si existe `rvc/.venv`.

Dónde conseguir modelos RVC: [Hugging Face](https://huggingface.co/models?search=rvc) (busca "RVC") o entrena el
tuyo con tu propia voz. Revisa la licencia de cada modelo y **no uses la voz de personas reales sin su permiso**.

Cuesta unos 3–5 s por frase en CPU y ~1 s en GPU; si la GPU es la misma que usa Ollama, puede frenarlo.

## Otras opciones

Open-LLM-VTuber trae más motores en `tts_config` (Piper local, Azure, ElevenLabs, Fish Audio, CosyVoice, GPT-SoVITS…):
ver la [documentación de Open-LLM-VTuber](https://open-llm-vtuber.github.io/). Los ajustes de este repo (velocidad,
RVC) están solo en `edge_tts.py`.
