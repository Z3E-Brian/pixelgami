# Conectar

Qué hay que conectar, qué es opcional y dónde va cada clave. Las claves van **solo** en `~/.config/pixelgami/`
(carpeta con permisos 700, archivos con 600) y nunca en el repo.

| Pieza | ¿Hace falta? | Dónde se configura |
|---|---|---|
| Ollama (cerebro local + embeddings) | **Sí** | servicio de Ollama, `conf.yaml` → `ollama_llm` |
| Whisper (oído) | Sí, para hablarle por voz | `servidor.sh`, modelo en `Open-LLM-VTuber/models/whisper/` |
| Edge TTS (voz) | Sí (necesita internet) | `conf.yaml` → `edge_tts.voice` |
| Gemini | Opcional (cerebro en la nube) | `~/.config/pixelgami/gemini.key` |
| SearXNG | Opcional (si no, DuckDuckGo) | servicio local en `127.0.0.1:8888` |
| Gmail y calendario | Opcional | `perfil.yaml` → `correo`; `gmail.key`, `calendario.url` |
| Recordatorios + Google Calendar | Opcional | servicio `asistente-recordatorios`; `google-calendar-script.json` |
| YouTube Music | Opcional | YouTube Music Desktop App + `ytmd.token` |
| Claude Code | Opcional | el comando `claude` con sesión iniciada |
| Atajo de teclado | Sí, para el modo mascota | config de Hyprland (ver INSTALAR.md, paso 8) |

## Cerebro: Ollama

El modelo local hace tres trabajos: **router** (entender qué pides), **intérpretes** (correo, música, web,
ventanas) y, por defecto, también **responder**. Además `paraphrase-multilingual` calcula embeddings para la
memoria y para reconocer apps por significado. Aunque respondas con Gemini, Ollama sigue haciendo falta.

```bash
systemctl --user enable --now ollama     # o el servicio del sistema, según tu paquete
ollama pull qwen3:8b && ollama pull paraphrase-multilingual
```

Ajustes que ayudan (en el servicio, `systemctl --user edit ollama`):

```ini
[Service]
Environment=OLLAMA_CONTEXT_LENGTH=8192      # el prompt de la asistente es largo
Environment=OLLAMA_MAX_LOADED_MODELS=2      # chat + embeddings a la vez
Environment=LLAMA_ARG_CACHE_RAM=2560        # sin esto relee el prompt entero en cada mensaje (lento)
# GPU AMD: Environment=OLLAMA_VULKAN=1  (y HSA_OVERRIDE_GFX_VERSION si tu GPU lo necesita)
```

Otro modelo (más chico o más grande): cambia `ollama_llm.model` en `conf.yaml`; el router y los intérpretes usan
el mismo (`identidad.MODELO_LOCAL`). Con modelos de menos de 7B el router se equivoca más.

## Cerebro en la nube: Gemini (opcional)

1. Crea una clave gratis en [Google AI Studio](https://aistudio.google.com/apikey).
2. `printf '%s' 'TU_CLAVE' > ~/.config/pixelgami/gemini.key && chmod 600 ~/.config/pixelgami/gemini.key`
3. En `conf.yaml`: `llm_provider: 'gemini_llm'` (el modelo, en `gemini_llm.model`).

La cuota gratis es limitada y a veces la saturan; si deja de responder, vuelve a `'ollama_llm'`.

## Búsqueda web: SearXNG (opcional)

La asistente busca primero en un SearXNG local (`http://127.0.0.1:8888`, junta Google, Bing, Brave y DuckDuckGo)
y, si no responde, solo en DuckDuckGo. Para instalarlo sin Docker:
[guía de SearXNG](https://docs.searxng.org/admin/installation-searxng.html). En su `settings.yml` hace falta:

```yaml
search:
  formats: [html, json]
server:
  bind_address: "127.0.0.1"
  port: 8888
```

## Correo (Gmail / Google Workspace, opcional)

Solo hace cosas reversibles: leer, marcar leído/no leído, estrella, archivar, mover a spam o papelera
(con confirmación si son varios). Nunca borra para siempre ni envía.

1. Activa la verificación en dos pasos y crea una [contraseña de aplicación](https://myaccount.google.com/apppasswords).
2. `printf '%s' 'xxxx xxxx xxxx xxxx' > ~/.config/pixelgami/gmail.key && chmod 600 ~/.config/pixelgami/gmail.key`
3. En `perfil.yaml`: `correo: tu.cuenta@gmail.com` (y `alias_remitentes` si llamas a alguien de otra forma).

## Calendario (opcional)

En Google Calendar → Configuración del calendario → **Dirección secreta en formato iCal**. Pega la URL (una por
línea si son varios) en `~/.config/pixelgami/calendario.url` con `chmod 600`.

## Recordatorios (opcional)

Avisos a la hora como notificación de la asistente, **aunque esté apagada**: los da un servicio chico aparte
(no carga el modelo ni la voz). Se crean hablándole ("recuérdame mañana a las 3 entregar el informe", "avísame en
20 minutos", "todos los lunes a las 7 gym"), con la ventanita (`python3 -m funciones.recordatorios.ventana`, atajo en
[escritorio/hyprland-ejemplo.txt](../escritorio/hyprland-ejemplo.txt)) o desde la terminal.

1. Copia [escritorio/asistente-recordatorios.service](../escritorio/asistente-recordatorios.service) a
   `~/.config/systemd/user/` y `systemctl --user enable --now asistente-recordatorios`.
2. Opcional en `perfil.yaml`: `icono_recordatorios` y `estilo_css`.

**Comprobar** (desde la carpeta de instalación): `python3 -m funciones.recordatorios.avisos agregar "en 1 minuto probar"`
y espera la notificación. Pruebas: `python3 -m unittest discover -s funciones -t .`

### Google Calendar: leer y apuntar (opcional)

Con esto te avisa de tus eventos (a las 8:00 del día y 30 min antes) y puede apuntar: "agenda un examen para el 12",
"guarda una cita con el médico el martes a las 9" (si no dices la hora, pregunta si es todo el día). Va por un
Apps Script propio, que corre con tu cuenta y solo sabe leer y crear eventos (nunca borra):

1. `python3 -m funciones.recordatorios.google_calendario copiar` → copia el script, con una clave secreta, al portapapeles.
2. En [script.google.com](https://script.google.com): **Nuevo proyecto**, pega, guarda.
3. **Implementar → Nueva implementación → Aplicación web**: ejecutar como **Yo**, acceso **Cualquier usuario**
   (sin la clave no responde nada). Autoriza (dirá que la app no está verificada: es tuya, *Configuración
   avanzada → Ir a…*).
4. `python3 -m funciones.recordatorios.google_calendario configurar <URL que termina en /exec>`.

## Música: YouTube Music Desktop App (opcional)

1. Instala [YouTube Music Desktop App](https://github.com/ytmdesktop/ytmdesktop) 2.x.
2. En la app: Ajustes → Integraciones → activa **Companion Server** y **Enable companion authorization**.
3. `cd Open-LLM-VTuber && uv run python ../musica-mcp/servidor_musica.py autorizar` y acepta el código en la app.
4. En Hyprland (no es GNOME ni KDE) la app no encuentra dónde guardar secretos: lánzala con
   `--password-store=gnome-libsecret` (copia su `.desktop` a `~/.local/share/applications/` y agrégalo al `Exec`).

## Claude Code (opcional)

La herramienta `preguntar_a_claude` le pasa a [Claude Code](https://claude.com/claude-code) las dudas técnicas
difíciles, en modo solo lectura (busca en la web y lee archivos; no ejecuta comandos ni modifica nada). Necesita el
comando `claude` con sesión iniciada y gasta de tu cuota. Si existe la memoria de Claude Code
(`~/.claude/projects/<tu home>/memory`), la herramienta `memoria` también la lee.

## Integraciones de la PC original (opcionales, no incluidas)

- **Horas de juego**: `memoria` lee `~/.local/share/game-tracker/sessions.csv` si existe (un registrador de sesiones
  de juego aparte). Sin ese archivo, esa función dice que no hay registro.
- **Modo juego**: conviene llamar a `escritorio/asistente_apagar.sh` al abrir un juego para liberar RAM y GPU.
