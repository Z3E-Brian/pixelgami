#!/usr/bin/env bash
# Arranca la voz RVC (localhost:12394, si está instalada), el oído Whisper (12395) y el backend
# de Open-LLM-VTuber (12393). Lo propio de esta PC (GPU, ajustes de ROCm) va en entorno.sh.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAVES="$HOME/.config/pixelgami"
[ -f "$BASE/entorno.sh" ] && . "$BASE/entorno.sh"
[ -f "$CLAVES/gemini.key" ] && export GEMINI_API_KEY="$(cat "$CLAVES/gemini.key")"

# La voz RVC carga en paralelo con el backend (no se espera): si una frase llega antes
# de que esté lista, sale con la voz normal (ver tts/edge_tts.py). Sin rvc/.venv, solo voz normal.
if [ -x "$BASE/rvc/.venv/bin/python" ]; then
    export ASISTENTE_RVC_URL="http://127.0.0.1:12394/convertir"
    if ! curl -s -o /dev/null -m 1 http://127.0.0.1:12394; then
        "$BASE/rvc/.venv/bin/python" "$BASE/rvc/servidor_rvc.py" > "$BASE/rvc.log" 2>&1 &
    fi
fi

# el oído (Whisper) en la GPU con whisper.cpp + Vulkan (paquetes whisper-cpp y ggml-vulkan)
if ! curl -s -o /dev/null -m 1 http://127.0.0.1:12395; then
    whisper-server -m "$BASE/Open-LLM-VTuber/models/whisper/ggml-large-v3-turbo-q5_0.bin" -l es -nt \
        --prompt "$("$BASE/Open-LLM-VTuber/.venv/bin/python" "$BASE/identidad.py" pista_voz)" \
        --host 127.0.0.1 --port 12395 > "$BASE/whisper.log" 2>&1 &
fi

cd "$BASE/Open-LLM-VTuber" || exit 1
exec uv run run_server.py "$@"
