# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones `0.x`: el proyecto todavía puede
cambiar de forma incompatible entre versiones; cada cambio de configuración dice cómo migrar.

## Sin publicar

## v0.1.0

Primera versión pública.

- Asistente de escritorio sobre Open-LLM-VTuber: modo mascota en Linux (una pantalla, solo el personaje recibe
  clics), aparece y se oculta con un atajo de Hyprland, se apaga sola si lleva un rato oculta.
- Cerebro local con Ollama (Qwen3 8B) o Gemini; router que entiende la intención y contexto automático (hora,
  memoria, estado del PC, ventanas, hábitos).
- Herramientas MCP: apps, juegos de Steam, proyectos, ventanas, estado del sistema, memoria y diario, correo y
  calendario de Google (solo acciones reversibles), YouTube Music, búsqueda web (SearXNG/DuckDuckGo), Claude Code.
- Recordatorios: por voz o con una ventanita, entienden fechas en español ("el primero a las 3 y media",
  "todos los lunes a las 7", "en 2 semanas"); avisan como notificación con un servicio aparte. Google Calendar
  opcional por un Apps Script propio (leer y apuntar, nunca borra).
- Voz: Whisper (whisper.cpp) para escuchar, Edge TTS para hablar, RVC opcional.
- Caras: emociones → expresiones Live2D, con la cara elegida por la frase cuando el modelo pone `[neutral]`;
  las etiquetas no se muestran en el subtítulo; toques en la cabeza y la mejilla. Guía en `docs/EXPRESIONES.md`.
- Protección contra precios inventados en búsquedas.
- Funciones: lo que sabe hacer va en carpetas de `funciones/` (tema y ejemplos para el router, entender/ejecutar,
  pruebas); el router se arma con las activas (`perfil.yaml` → `funciones`). `herramientas/nueva-funcion.py` crea
  una nueva y `docs/FUNCIONES.md` explica cómo hacerla.
- Configurable: nombres, género, lugar, navegador y alias (`perfil.yaml`); personaje de ejemplo IA-chan (modelo Mao);
  `herramientas/agregar-modelo.py` para adaptar cualquier modelo Live2D descargado.
