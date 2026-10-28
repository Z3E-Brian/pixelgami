#!/usr/bin/env bash
# Instala pixelgami (ver docs/INSTALAR.md). Sin opciones: clona Open-LLM-VTuber y su cliente en el commit
# de parches/*/BASE, aplica los parches y crea la configuración. Se puede volver a correr: no pisa lo que existe.
#   --python   dependencias de Python (uv sync)
#   --modelos  modelos de Ollama (qwen3:8b, paraphrase-multilingual) y de Whisper
#   --cliente  compila la app de escritorio (npm)
#   --todo     todo lo anterior
set -euo pipefail
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"
paso() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
falta() { command -v "$1" > /dev/null || { echo "Falta '$1' (ver docs/INSTALAR.md, paso 1)."; exit 1; }; }

PYTHON=0 MODELOS=0 CLIENTE=0
for op in "$@"; do
    case "$op" in
        --python) PYTHON=1 ;; --modelos) MODELOS=1 ;; --cliente) CLIENTE=1 ;;
        --todo) PYTHON=1 MODELOS=1 CLIENTE=1 ;;
        *) sed -n '2,7p' "$0"; exit 1 ;;
    esac
done
falta git

paso "Open-LLM-VTuber y cliente de escritorio, con los parches"
for p in open-llm-vtuber:Open-LLM-VTuber cliente-escritorio:cliente-escritorio; do
    src="parches/${p%%:*}" dst="${p##*:}"
    if [ -d "$dst/.git" ]; then echo "$dst ya existe: no lo toco."; continue; fi
    read -r url commit < "$src/BASE"
    git clone -q "$url" "$dst"
    git -C "$dst" checkout -q "$commit"
    git -C "$dst" apply --binary "$BASE/$src/cambios.patch"
    cp -a "$src/nuevos/." "$dst/"
    echo "$dst: listo ($commit)"
done

paso "Configuración"
[ -f perfil.yaml ] || { cp perfil.ejemplo.yaml perfil.yaml; echo "perfil.yaml creado: complétalo con tus datos."; }
[ -f entorno.sh ] || { cp entorno.ejemplo.sh entorno.sh; echo "entorno.sh creado (ajustes de GPU y voz RVC)."; }
mkdir -p "$HOME/.config/pixelgami" && chmod 700 "$HOME/.config/pixelgami"
# las rutas de las herramientas MCP apuntan a la carpeta por defecto: si instalaste en otra, se corrigen
if [ "$BASE" != "$HOME/.local/share/pixelgami" ]; then
    sed -i "s|~/.local/share/pixelgami|$BASE|g" Open-LLM-VTuber/mcp_servers.json
fi
chmod +x servidor.sh escritorio/*.sh herramientas/*.py

if [ "$PYTHON" = 1 ]; then
    paso "Dependencias de Python (uv sync)"
    falta uv
    (cd Open-LLM-VTuber && uv sync)
fi

if [ "$MODELOS" = 1 ]; then
    paso "Modelos"
    if command -v ollama > /dev/null; then
        ollama pull qwen3:8b
        ollama pull paraphrase-multilingual
    else
        echo "Sin Ollama: me salto los modelos locales (usa Gemini o instala Ollama, ver docs/CONECTAR.md)."
    fi
    W=Open-LLM-VTuber/models/whisper/ggml-large-v3-turbo-q5_0.bin
    if [ ! -f "$W" ]; then
        mkdir -p "$(dirname "$W")"
        curl -L --fail -o "$W.part" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
        mv "$W.part" "$W"
    fi
fi

if [ "$CLIENTE" = 1 ]; then
    paso "App de escritorio (tarda varios minutos)"
    falta npm
    (cd cliente-escritorio && npm install && npm run build:linux)
fi

paso "Siguiente"
echo "1. Completa perfil.yaml y, en Open-LLM-VTuber/conf.yaml, character_config (tu nombre, el de la asistente, la persona)."
echo "2. Prueba: ./servidor.sh y abre http://localhost:12393"
echo "3. El atajo y lo opcional: docs/INSTALAR.md (pasos 8 y 9) y docs/CONECTAR.md"
