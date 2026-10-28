# Modelos 2D (Live2D)

El personaje es un modelo **Live2D Cubism 3, 4 o 5**: una carpeta con un `.model3.json`, un `.moc3`, texturas
y, si los trae, movimientos (`.motion3.json`), física y **expresiones** (`.exp3.json`). Los de Cubism 2
(`.model.json` + `.moc`) funcionan a medias; los 3D (VRM, MMD) no.

Por defecto se usa **Mao** (`mao_pro`), que viene dentro de Open-LLM-VTuber con 8 expresiones ya asignadas.

## Dónde conseguir modelos

| Sitio | Qué hay | Ojo con |
|---|---|---|
| [Muestras oficiales de Live2D](https://www.live2d.com/en/learn/sample/) | Mao, Haru, Hiyori, Natori, Mark-kun, Epsilon, gatos… | Gratis para personas y empresas pequeñas; aceptas su *Free Material License*. Hatsune Miku y Unity-chan tienen reglas aparte. Varios traen solo movimientos, sin expresiones. |
| [BOOTH](https://booth.pm/en/search/Live2D) | Miles de modelos, gratis y de pago (busca "Live2D" + "VTS対応" o "free") | Cada uno tiene sus condiciones: casi siempre prohíben redistribuirlo y a veces piden crédito o no permiten uso comercial. |
| [nizima](https://nizima.com) | Tienda oficial de Live2D | Igual que BOOTH: lee la licencia. |
| [itch.io (tag live2d)](https://itch.io/game-assets/free/tag-live2d) | Modelos gratis, algunos CC0 | Algunos traen solo el `.cmo3` (fuente): hay que exportarlo con Cubism Editor. |
| Hacerlo tú | [Cubism Editor](https://www.live2d.com/en/cubism/download/editor/) (gratis con límites; Windows/macOS) | Dibujo por capas (PSD) + rig. |

Antes de usar un modelo: ¿permite uso personal? ¿streaming? ¿modificarlo (agregarle expresiones)? Nunca subas a
un repo público un modelo que no permita redistribución: comparte el enlace.

Que funcione bien con la asistente:
- **Fondo transparente**: sin escenario pegado al personaje (se vería un recuadro en el escritorio).
- **Expresiones**: sin ellas la cara no cambia con la emoción (solo se mueve y parpadea).
- **Boca**: grupo `LipSync` (normalmente `ParamMouthOpenY` o `ParamA`); el cliente además usa `ParamMouthForm`
  para dar forma a las vocales.
- **Parpadeo**: grupo `EyeBlink`.
- **Mirada**: los parámetros estándar `ParamAngleX/Y`, `ParamEyeBallX/Y` y `ParamBodyAngleX` (para seguir el cursor).
- **Medio cuerpo o busto** se ve mejor en una esquina que cuerpo entero.

## Agregarlo

```bash
python3 herramientas/agregar-modelo.py ~/Descargas/MiModelo --nombre robot --usar
```

1. Copia la carpeta a `Open-LLM-VTuber/live2d-models/robot/`.
2. Si hay `.exp3.json` que el `.model3.json` no declara (pasa con modelos hechos para VTube Studio), los agrega.
3. Propone el `emotionMap` mirando el nombre de cada expresión (en inglés, español o japonés) y lo que mueve
   (ojos sonrientes → alegre, sonrojo → tímida, cejas caídas y boca hacia abajo → triste, ojos muy abiertos →
   sorpresa…). Las de ropa o accesorios las ignora. Lo que no adivina lo dice.
4. Escribe la entrada en `model_dict.json` y, con `--usar`, la pone como `live2d_model_name` en `conf.yaml`.
5. Avisa si falta algo (expresiones, `LipSync`, `EyeBlink`, movimientos).

Después: `python3 herramientas/comprobar.py` y reinicia la asistente.

## La entrada de model_dict.json

```json
{
  "name": "robot",
  "url": "/live2d-models/robot/robot.model3.json",
  "kScale": 0.5,              // tamaño
  "initialXshift": 0,         // corrimiento horizontal (px)
  "initialYshift": 0,         // corrimiento vertical: súbelo/bájalo si se ve cortado
  "kXOffset": 1150,
  "idleMotionGroupName": "Idle",   // grupo de movimientos en reposo (como se llame en el .model3.json)
  "emotionMap": { "joy": 1, "sad": 4, "...": 0, "neutral": 0 },
  "tapMotions": { "HitAreaHead": { "": 1 } },          // opcional: movimiento al tocar una zona
  "partesCabeza": ["PartHead"],                        // opcional: partes de la cabeza (mirada y toques)
  "toques": { "cabeza": "exp_02", "mejilla": "exp_06", "caricia": "exp_02" }  // opcional
}
```

- **`emotionMap`**: qué expresión (su número, desde 0) pone cada emoción; `neutral` va al final.
- **`partesCabeza`** y **`toques`**: dónde está la cabeza y qué expresión (por nombre) pone cada toque.

Cómo elegirlos, saber qué cara es cada expresión y crear expresiones nuevas: [EXPRESIONES.md](EXPRESIONES.md).

## Personaje (nombre, persona, voz)

El modelo es solo el cuerpo. El nombre y la forma de ser están en `Open-LLM-VTuber/conf.yaml`
(`character_name`, `persona_prompt`), el género en `perfil.yaml` y la voz en [VOCES.md](VOCES.md).
Si cambias de personaje, revisa que las `[emociones]` de los ejemplos de la persona existan en el nuevo `emotionMap`.
