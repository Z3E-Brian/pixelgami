# Instalar

Pasos en orden. Cada uno dice qué hace, el comando y cómo comprobar que quedó bien. Si lo sigue un agente:
ejecuta un paso, verifica, y solo entonces sigue; las claves y contraseñas las pone la persona, nunca el agente
(ver [AGENTS.md](../AGENTS.md)).

Rutas: el proyecto va en `~/.local/share/pixelgami` (otra carpeta funciona, pero entonces ajusta
`ASISTENTE_DIR` para los scripts de escritorio). Las claves van en `~/.config/pixelgami/`.

## 1. Dependencias del sistema

| Para qué | Arch / CachyOS | Comprobar |
|---|---|---|
| Base | `sudo pacman -S git python uv nodejs npm ffmpeg curl` | `uv --version && node --version` |
| Cerebro local | `sudo pacman -S ollama` (o `ollama-vulkan` / `ollama-rocm` / `ollama-cuda`) | `ollama --version` |
| Oído (Whisper en GPU) | `sudo pacman -S whisper-cpp ggml-vulkan` (AUR/repos de CachyOS) | `whisper-server --help` |
| Escritorio | Hyprland, `libnotify`, `iproute2` (ss) | `hyprctl version` |

En otras distros: los mismos programas con su gestor de paquetes; whisper.cpp se puede compilar desde
[su repo](https://github.com/ggml-org/whisper.cpp) con `-DGGML_VULKAN=1` (AMD/Intel) o `-DGGML_CUDA=1` (NVIDIA).

## 2. Descargar e instalar

```bash
git clone <este repo> ~/.local/share/pixelgami
cd ~/.local/share/pixelgami
./instalar.sh
```

`instalar.sh` clona Open-LLM-VTuber y su cliente de escritorio en el commit exacto de `parches/*/BASE`, aplica
`cambios.patch`, copia `nuevos/`, crea `perfil.yaml` y `entorno.sh` desde los ejemplos y la carpeta de claves.
Se puede volver a correr: no pisa tu `perfil.yaml`, `entorno.sh` ni `conf.yaml` si ya existen.

**Comprobar**: `ls Open-LLM-VTuber/src/open_llm_vtuber/agent/asistente_contexto.py cliente-escritorio/package.json`

## 3. Dependencias de Python

```bash
./instalar.sh --python      # = cd Open-LLM-VTuber && uv sync
```

**Comprobar**: `python3 herramientas/comprobar.py` (compila todo e importa los módulos propios).

## 4. Modelos

```bash
./instalar.sh --modelos
```

Descarga en Ollama `qwen3:8b` (el cerebro, ~5 GB) y `paraphrase-multilingual` (embeddings para la memoria y para
reconocer apps, ~560 MB), y el modelo de Whisper `ggml-large-v3-turbo-q5_0.bin` (~550 MB) en
`Open-LLM-VTuber/models/whisper/`.

**Comprobar**: `ollama list` muestra los dos modelos; el archivo de Whisper existe.

Con poca VRAM (< 8 GB) o sin GPU: usa un modelo más chico en `conf.yaml` (`ollama_llm.model`, p. ej. `qwen3:4b`)
o el cerebro en la nube (Gemini, ver [CONECTAR.md](CONECTAR.md)).

## 5. App de escritorio

```bash
./instalar.sh --cliente     # = cd cliente-escritorio && npm install && npm run build:linux
```

Tarda varios minutos. **Comprobar**: existe `cliente-escritorio/release/*/linux-unpacked/open-llm-vtuber`.

## 6. Tu perfil y tu personaje

1. `perfil.yaml`: tu género y el de la asistente, dónde vives, tu navegador, tu correo (opcional), alias…
2. `Open-LLM-VTuber/conf.yaml`, sección `character_config`: `character_name` (nombre de la asistente),
   `human_name` (tu nombre), `persona_prompt` (cómo es y cómo habla) y `live2d_model_name`.
3. Voz: `conf.yaml` → `tts_config` → `edge_tts.voice` (ver [VOCES.md](VOCES.md)).

## 7. Probar sin la app

```bash
./servidor.sh
```

Abre http://localhost:12393 en el navegador: es la interfaz web de Open-LLM-VTuber. Escríbele "hola" y "¿cuánta
RAM estoy usando?". **Comprobar**: responde con voz y la cara cambia. Si falla, el log está en la terminal.

## 8. El atajo de teclado (Hyprland)

Agrega el atajo y las reglas de ventana de [escritorio/hyprland-ejemplo.txt](../escritorio/hyprland-ejemplo.txt)
a tu config (el bloque de `hyprland.conf` o el de `hyprland.lua`), y recarga Hyprland.

**Comprobar**: Super+Z muestra el personaje abajo a la derecha de la pantalla enfocada; otra vez lo oculta.
Si lleva 15 minutos oculta, se apaga sola para liberar RAM.

## 9. Conectar lo opcional

Correo, calendario, música, búsqueda web local, Claude Code: [CONECTAR.md](CONECTAR.md).

## Si algo falla

| Síntoma | Revisa |
|---|---|
| No responde / tarda mucho | `ollama ps` (¿cargó el modelo?), `servidor.log` |
| No te entiende por voz | `whisper.log`; que `whisper-server` corra en el puerto 12395; el micrófono en la app |
| Sin voz | Edge TTS necesita internet; si da 403, actualiza: `cd Open-LLM-VTuber && uv lock --upgrade-package edge-tts && uv sync` |
| La cara no cambia | que el modelo tenga expresiones y `emotionMap` (ver [MODELOS.md](MODELOS.md)) |
| El atajo no hace nada | ejecuta `escritorio/asistente_toggle.sh` en una terminal y mira el error; prueba `HYPR_SINTAXIS=clasica` o `lua` |
| La sesión se cierra cuando falta RAM | systemd-oomd: baja el modelo (qwen3:4b) o cierra cosas; la asistente se lanza en `app.slice` justo para que oomd la elija a ella |
