#!/usr/bin/env bash
# Atajo (p. ej. Super+Z): muestra/oculta a la asistente en modo mascota (solo el cuerpo, fondo
# transparente) en la pantalla enfocada, pegada a la esquina inferior derecha.
# Visible = ventana fijada (pin) y con el cursor listo en el cuadro de texto; oculta = escritorio
# especial "asistenteoculta", sin micrófono. Si sigue oculta APAGAR_TRAS segundos se cierra todo
# (asistente_apagar.sh) para liberar RAM; el siguiente atajo la vuelve a arrancar.
# La app corre por XWayland: así solo el personaje y el cuadro de texto reciben clics.
# Hecho para Hyprland. Sintaxis de hyprctl: la del config en Lua (hyprland.lua) o la clásica
# (hyprland.conf); se detecta sola o se fuerza con HYPR_SINTAXIS=lua|clasica. Ver docs/INSTALAR.md.
BASE="${ASISTENTE_DIR:-$HOME/.local/share/pixelgami}"
CLIENTE="$(ls -d "$BASE"/cliente-escritorio/release/*/linux-unpacked/open-llm-vtuber 2>/dev/null | tail -1)"
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APAGAR_TRAS=900
PID_APAGADO="${XDG_RUNTIME_DIR:-/tmp}/asistente_apagado.pid"
# servidor y app en su propio scope (app.slice): si systemd-oomd tiene que matar algo,
# se lleva a la asistente y no a la sesión gráfica entera
SCOPE="systemd-run --user --scope --slice=app.slice --collect --quiet"
if [ -z "$HYPR_SINTAXIS" ]; then
    [ -f "$HOME/.config/hypr/hyprland.lua" ] && HYPR_SINTAXIS=lua || HYPR_SINTAXIS=clasica
fi
# Una sola ejecución a la vez: si está arrancando, otro atajo no abre otra copia.
# (los procesos lanzados abajo cierran el fd 9 para no quedarse con el candado)
exec 9> "${XDG_RUNTIME_DIR:-/tmp}/asistente_toggle.lock"
flock -n 9 || exit 0

# --- acciones de Hyprland en las dos sintaxis ---
h_mover() {      # h_mover <direccion> <x> <y>
    if [ "$HYPR_SINTAXIS" = lua ]; then
        hyprctl dispatch "hl.dsp.window.move({ x = $2, y = $3, window = \"address:$1\" })"
    else
        hyprctl dispatch movewindowpixel "exact $2 $3,address:$1"
    fi
}
h_escritorio() { # h_escritorio <direccion> <escritorio>  (sin seguirla)
    if [ "$HYPR_SINTAXIS" = lua ]; then
        hyprctl dispatch "hl.dsp.window.move({ workspace = \"$2\", follow = false, window = \"address:$1\" })"
    else
        hyprctl dispatch movetoworkspacesilent "$2,address:$1"
    fi
}
h_fijar() {      # alterna el pin de la ventana
    if [ "$HYPR_SINTAXIS" = lua ]; then
        hyprctl dispatch "hl.dsp.window.pin({ window = \"address:$1\" })"
    else
        hyprctl dispatch pin "address:$1"
    fi
}
h_enfocar() {    # h_enfocar ventana <direccion> | h_enfocar monitor <nombre>
    if [ "$HYPR_SINTAXIS" = lua ]; then
        [ "$1" = ventana ] && hyprctl dispatch "hl.dsp.focus({ window = \"address:$2\" })" \
                           || hyprctl dispatch "hl.dsp.focus({ monitor = \"$2\" })"
    else
        [ "$1" = ventana ] && hyprctl dispatch focuswindow "address:$2" || hyprctl dispatch focusmonitor "$2"
    fi
}

monitor() {
    # imprime "x y ancho alto escritorio nombre" (lógicos) del área donde van las ventanas
    # normales de la pantalla enfocada: sin la barra (reserved) y con el mismo margen
    # (gaps_out + borde), para que quede alineada con ellas abajo a la derecha
    local gap borde
    gap=$(hyprctl getoption general:gaps_out | awk 'NR==1 {print $(NF-1)}')
    borde=$(hyprctl getoption general:border_size | awk 'NR==1 {print $2}')
    hyprctl monitors -j | python3 -c "
import json, sys
m = next(m for m in json.load(sys.stdin) if m['focused'])
w, h = (m['height'], m['width']) if m['transform'] % 2 else (m['width'], m['height'])
w, h = round(w / m['scale']), round(h / m['scale'])
izq, arr, der, aba = m['reserved']
margen = ${gap:-0} + ${borde:-0}
print(m['x'], m['y'], w - der - margen, h - aba - margen, m['activeWorkspace']['name'], m['name'])"
}

ventana() {
    # imprime "direccion escritorio fijada ancho alto" de la ventana de la asistente, si existe
    hyprctl clients -j | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    if c["class"] == "open-llm-vtuber":
        print(c["address"], c["workspace"]["name"], c["pinned"], *c["size"])
        break'
}

avisar() {
    # la app vigila este archivo (mostrar: foco al cuadro de texto; ocultar: apaga el micrófono)
    echo "${1#--asistente-} $(date +%s%N)" > "${XDG_RUNTIME_DIR:-/tmp}/asistente_aviso"
}

cancelar_apagado() {
    [ -f "$PID_APAGADO" ] && kill "$(cat "$PID_APAGADO")" 2> /dev/null
    rm -f "$PID_APAGADO"
}

colocar() {
    # esquina inferior derecha de la pantalla enfocada, según el tamaño real de la ventana
    h_mover "$1" $((MX + MW - $2)) $((MY + MH - $3))
}

mostrar() {
    local addr=$1
    cancelar_apagado
    h_escritorio "$addr" "$MWS"
    colocar "$@"
    h_fijar "$addr"
    h_enfocar ventana "$addr"
    avisar --asistente-mostrar
}

ocultar() {
    local addr=$1
    [ "$pinned" = "True" ] && h_fijar "$addr"
    h_escritorio "$addr" "special:asistenteoculta"
    avisar --asistente-ocultar
    cancelar_apagado
    setsid bash -c "sleep $APAGAR_TRAS; exec '$SCRIPTS/asistente_apagar.sh' --si-oculta" > /dev/null 2>&1 < /dev/null 9>&- &
    echo $! > "$PID_APAGADO"
}

[ -x "$CLIENTE" ] || { notify-send "Asistente" "No encuentro la app de escritorio en $BASE/cliente-escritorio/release (¿la compilaste?)"; exit 1; }
read -r MX MY MW MH MWS MMON <<< "$(monitor)"   # pantalla enfocada al presionar el atajo
read -r addr ws pinned w h <<< "$(ventana)"

if [ -z "$addr" ]; then
    notify-send --app-name=Asistente --icon=dialog-information "Despertando…" "Unos segundos."
    if ! ss -ltn 'sport = :12393' | grep -q LISTEN; then
        setsid $SCOPE "$BASE/servidor.sh" > "$BASE/servidor.log" 2>&1 < /dev/null 9>&- &
    fi
    for _ in $(seq 60); do
        curl -s -o /dev/null -m 1 http://localhost:12393 && break
        sleep 1
    done
    h_enfocar monitor "$MMON"
    ASISTENTE_MODE=pet setsid $SCOPE "$CLIENTE" --ozone-platform=x11 > "$BASE/cliente.log" 2>&1 < /dev/null 9>&- &
    for _ in $(seq 30); do
        read -r addr ws pinned w h <<< "$(ventana)"
        [ -n "$addr" ] && break
        sleep 0.5
    done
    [ -z "$addr" ] && exit 1
    mostrar "$addr" "$w" "$h"
    # al terminar de cargar la app se centra sola y luego pasa a modo mascota (tarda más
    # si el equipo está ocupado): recolocarla hasta que lleve 3 s quieta en su sitio
    quieta=0
    for _ in $(seq 40); do
        sleep 0.5
        read -r x y <<< "$(hyprctl clients -j | python3 -c "
import json, sys
c = next((c for c in json.load(sys.stdin) if c['address'] == '$addr'), None)
print(*c['at']) if c else print('- -')")"
        [ "$x" = "-" ] && break
        if [ "$x" = $((MX + MW - w)) ] && [ "$y" = $((MY + MH - h)) ]; then
            quieta=$((quieta + 1))
            [ "$quieta" -ge 6 ] && break
        else
            quieta=0
            colocar "$addr" "$w" "$h"
        fi
    done
    avisar --asistente-mostrar
elif [ "$ws" = "special:asistenteoculta" ]; then
    mostrar "$addr" "$w" "$h"
else
    ocultar "$addr"
fi
