#!/usr/bin/env bash
# Cierra a la asistente por completo (app de escritorio, servidor Open-LLM-VTuber, voz RVC y oído Whisper)
# para liberar la RAM. Lo lanza asistente_toggle.sh cuando lleva un rato oculta; con --si-oculta
# solo actúa si sigue oculta. Útil también antes de abrir un juego. El siguiente atajo la vuelve a arrancar.
BASE="${ASISTENTE_DIR:-$HOME/.local/share/pixelgami}"

if [ "$1" = "--si-oculta" ]; then
    ws=$(hyprctl clients -j | python3 -c '
import json, sys
print(next((c["workspace"]["name"] for c in json.load(sys.stdin) if c["class"] == "open-llm-vtuber"), ""))')
    [ "$ws" = "special:asistenteoculta" ] || exit 0
fi
rm -f "${XDG_RUNTIME_DIR:-/tmp}/asistente_apagado.pid"

# app de escritorio (ignora el cierre normal: hay que forzarla)
for p in /proc/[0-9]*; do
    exe=$(readlink "$p/exe" 2>/dev/null)
    # tras recompilar la app, el binario viejo aparece como "... (deleted)"
    case "${exe% (deleted)}" in "$BASE"/cliente-escritorio/release/*/linux-unpacked/open-llm-vtuber) kill -KILL "${p#/proc/}" ;; esac
done
# servidor (12393), voz RVC (12394) y oído Whisper (12395, ocupa la GPU)
for puerto in 12393 12394 12395; do
    pid=$(ss -ltnpH "sport = :$puerto" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    [ -n "$pid" ] && kill -TERM "$pid"
done
# el cerebro local (Ollama): sin esto el modelo se queda en la RAM/VRAM hasta que venza su keep_alive
curl -s -m 5 http://127.0.0.1:11434/api/generate -d '{"model": "qwen3:8b", "keep_alive": 0}' > /dev/null
