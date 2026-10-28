#!/usr/bin/env bash
# Atajo (p. ej. Super+Shift+Z): reinicia a la asistente cuando se queda pegada (ventana vacía, no responde,
# sin voz). Cierra la app de escritorio y el servidor (Open-LLM-VTuber); deja la voz RVC corriendo.
# Después la vuelve a abrir con asistente_toggle.sh en la pantalla enfocada.
BASE="${ASISTENTE_DIR:-$HOME/.local/share/pixelgami}"
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

notify-send --app-name=Asistente --icon=view-refresh "Reiniciando…" "Tarda unos segundos."

# app de escritorio (ignora el cierre normal: hay que forzarla)
for p in /proc/[0-9]*; do
    exe=$(readlink "$p/exe" 2>/dev/null)
    case "${exe% (deleted)}" in "$BASE"/cliente-escritorio/release/*/linux-unpacked/open-llm-vtuber) kill -KILL "${p#/proc/}" ;; esac
done
# servidor (puerto 12393)
pid=$(ss -ltnpH 'sport = :12393' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
[ -n "$pid" ] && kill -TERM "$pid"
for _ in $(seq 20); do ss -ltnH 'sport = :12393' | grep -q . || break; sleep 0.5; done

exec "$SCRIPTS/asistente_toggle.sh"
