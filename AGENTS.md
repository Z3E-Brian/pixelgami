# Para agentes (Claude Code, Codex, etc.)

Si te pidieron instalar, adaptar o modificar este proyecto:

## Instalar
- Sigue [docs/INSTALAR.md](docs/INSTALAR.md) **paso a paso**: ejecuta un paso, corre su comprobación y solo
  entonces sigue. Si una comprobación falla, para y cuéntale a la persona qué pasó; no improvises atajos.
- El sistema operativo es de la persona: pide permiso antes de instalar paquetes con `sudo`, habilitar servicios o
  editar la config de Hyprland, y di exactamente qué vas a cambiar.
- **Claves y contraseñas** (Gemini, Gmail, calendario, YouTube Music) las pone la persona. Dale el comando para
  guardarlas en `~/.config/pixelgami/` (chmod 600); no las leas, no las pidas en el chat, no las escribas en el repo.
- Al terminar: `python3 herramientas/comprobar.py --importar` y la prueba del paso 7.

## Adaptar (modelo, voz, personaje)
- Modelo Live2D: `herramientas/agregar-modelo.py <carpeta>` y revisa el `emotionMap` propuesto con
  [docs/MODELOS.md](docs/MODELOS.md). No subas modelos a ningún repo salvo que su licencia lo permita.
- Datos de la persona: `perfil.yaml`. Nombres y persona: `Open-LLM-VTuber/conf.yaml` → `character_config`.
- Ajustes de la máquina (GPU, RVC): `entorno.sh`.

## Modificar el código
- El código de la asistente está en dos lugares: los archivos propios de este repo (`*-mcp/`, `identidad.py`,
  `rvc/`, `escritorio/`, `herramientas/`) y los **parches** sobre Open-LLM-VTuber y su cliente (`parches/*/`).
  Tras `./instalar.sh` los parches están aplicados en `Open-LLM-VTuber/` y `cliente-escritorio/`; para proponer un
  cambio ahí, edita esos árboles y regenera el parche: `git -C Open-LLM-VTuber diff HEAD --binary > parches/open-llm-vtuber/cambios.patch`
  (los archivos nuevos van copiados en `parches/<clon>/nuevos/`).
- Textos para el modelo: con marcadores de `identidad.py` (`{usuario}`, `{asistente}`, `{él}`, `sol{a}`…) y
  `nombres()`; nunca nombres de personas a mano.
- Antes de un PR: `python3 herramientas/comprobar.py --importar`; si tocaste el router o los intérpretes, agrega
  casos a `pruebas_intencion.py` y córrelas (necesita Ollama).
- Ver [CONTRIBUTING.md](CONTRIBUTING.md).
