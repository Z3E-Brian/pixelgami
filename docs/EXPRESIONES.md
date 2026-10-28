# Expresiones: cómo cambia la cara

Cómo pasa una respuesta a la cara del personaje, cómo asignar las expresiones de un modelo nuevo y cómo
funcionan los toques en la cabeza. Para conseguir y agregar el modelo en sí, ver [MODELOS.md](MODELOS.md).

## De la respuesta a la cara

1. **El modelo de lenguaje etiqueta cada frase** con una emoción entre corchetes: `[joy] ¡Hola! [thinking] A ver…`.
   La lista de emociones que puede usar sale de las claves del `emotionMap` del modelo, en ese orden.
2. **El backend traduce la etiqueta** (`agent/transformers.py`): busca la emoción en el `emotionMap` y manda al
   cliente el número de expresión. Después quita todas las `[etiquetas]` del texto: no salen en el subtítulo,
   ni en el historial ni en la voz.
3. **Si la etiqueta es `[neutral]` pero la frase no lo es**, la cara la elige la frase
   (`asistente_contexto.cara_por_frase`). Primero mira el emoji y después el texto:

   | En la frase | Cara | En la frase | Cara |
   |---|---|---|---|
   | 🥰 | `love` | "ay, no", "lo siento", "qué pena" | `sad` |
   | ☺️ | `shy` | "perdón", "disculpa", "me equivoqué" | `embarrassed` |
   | 😳 | `embarrassed` | "jeje", "jaja" | `joy` |
   | 😜 | `playful` | "¿en serio?", "wow", "vaya" | `surprise` |
   | 😌 | `smirk` | "hmm", "déjame ver", "a ver" | `thinking` |
   | 😢 😭 | `sad` | un `!` | `happy` |
   | 😮 😲 | `surprise` | | |
   | 🤔 | `thinking` | | |
   | 😊 😄 😁 | `happy` | | |

   Solo elige caras que existan en el `emotionMap`. Si ninguna coincide, se queda `neutral`.
4. **El cliente la aplica mientras habla.** Si una frase trae varias emociones, las reparte a lo largo de su audio
   (dos emociones: la segunda entra a la mitad). La transición la da el `FadeInTime` de cada `.exp3.json`.
5. **Vuelve a la cara normal** 4 segundos después de que dejó de sonar la última frase, para que el ánimo se note
   al terminar. La cara normal es `defaultEmotion` si el modelo lo define en `model_dict.json`; si no, la
   expresión 0.

## emotionMap: qué expresión es cada emoción

En `Open-LLM-VTuber/model_dict.json`, en la entrada del modelo:

```json
"emotionMap": {
  "joy": 1, "happy": 1, "excited": 3, "love": 3, "curious": 3, "smirk": 1, "playful": 1, "wink": 1,
  "thinking": 2, "sad": 4, "sadness": 4, "crying": 4, "worried": 4, "shy": 5, "embarrassed": 5,
  "surprise": 6, "surprised": 6, "fear": 6, "nervous": 6, "angry": 7, "anger": 7, "disgust": 7, "neutral": 0
}
```

(es el de Mao). Cada número es la **posición** de la expresión en la lista `FileReferences.Expressions` del
`.model3.json`, **empezando en 0**: en Mao `0` = `exp_01`, `1` = `exp_02`… Varias emociones pueden usar la
misma expresión, y conviene que estén todas las de esta tabla (las usan la persona y el código):

| Emoción | Cuándo | Emoción | Cuándo |
|---|---|---|---|
| `joy`, `happy` | alegre, saluda | `sad`, `worried` | pena, preocupación |
| `excited` | entusiasmo | `fear`, `nervous` | miedo, nervios |
| `love` | cariño | `surprise` | sorpresa |
| `shy`, `embarrassed` | la elogian, se equivocó | `thinking`, `curious` | pensando, dato técnico |
| `smirk`, `playful`, `wink` | cuando ella bromea | `angry`, `disgust` | enojo (rara vez) |
| `neutral` | normal | | |

Reglas que importan:
- **`neutral` va al final.** El modelo de lenguaje ve las emociones en el orden del mapa y tiende a elegir la
  primera; con `neutral` primero, casi todo salía neutral.
- **Solo números** (`comprobar.py` revisa que cada uno exista en el modelo).
- **Las `[emociones]` de los ejemplos de la persona** (`persona_prompt` en `conf.yaml`) tienen que estar en el
  mapa. Si cambias de modelo y le faltan, quita esas emociones de los ejemplos o asígnales una expresión parecida.

`herramientas/agregar-modelo.py` propone el mapa solo (ver [MODELOS.md](MODELOS.md#agregarlo)); lo que no
adivina lo dice, y esto sirve para revisarlo.

## Saber qué cara es cada expresión

- **Mirarla:** en el visor de Cubism (*Cubism Viewer*, viene con Cubism Editor) abre el `.model3.json` y haz
  clic en cada expresión.
- **Leerla:** cada `.exp3.json` es una lista de parámetros que la expresión mueve:

  ```json
  { "Type": "Live2D Expression", "FadeInTime": 0.5, "FadeOutTime": 0.5,
    "Parameters": [ { "Id": "ParamCheek", "Value": 1, "Blend": "Add" },
                    { "Id": "ParamBrowLForm", "Value": -1, "Blend": "Add" } ] }
  ```

  Los que importan son los que no quedan en 0 (o en 1 con `Multiply`). Nombres estándar (son las mismas pistas
  que usa `agregar-modelo.py`):

  | Parámetro | Qué mueve | Sugiere |
  |---|---|---|
  | `ParamEyeLSmile`, `ParamEyeRSmile` | ojos sonrientes | `joy` (con ojos muy abiertos o brillos: `excited`) |
  | `ParamEyeLOpen`, `ParamEyeROpen` > 1 | ojos muy abiertos | `surprise` |
  | `ParamEyeLOpen`, `ParamEyeROpen` cerca de 0 | ojos cerrados sin sonrisa | `thinking` |
  | `ParamCheek` | sonrojo | `shy`, `embarrassed`, `love` |
  | `ParamBrowLAngle`, `ParamBrowRAngle` < 0 | cejas caídas | `sad`, `worried` |
  | `ParamMouthDown` | boca hacia abajo | `sad` |
  | `ParamMouthAngry`, `ParamMouthAngryLine`, `ParamEyeLForm` > 0 | boca o mirada enojada | `angry`, `disgust` |
  | `ParamEyeEffect`, `ParamTear`… | brillos, lágrimas | según el modelo |

  Cada modelo puede tener parámetros propios: sus nombres legibles están en el `.cdi3.json`.
- **Probarla en vivo:** di algo que lleve esa emoción ("¡te quedó genial!" → `shy`) y mira la cara.

## Agregar o retocar una expresión

Para un modelo con pocas expresiones, se puede hacer una nueva sin Cubism Editor:

1. Copia un `.exp3.json` parecido en la carpeta de expresiones del modelo y cambia los valores
   (`Blend`: `Add` suma al valor actual, `Multiply` lo multiplica, `Overwrite` lo reemplaza).
2. Decláralo en el `.model3.json`, al **final** de `FileReferences.Expressions` para no correr los números de
   las demás: `{ "Name": "tierna", "File": "expressions/tierna.exp3.json" }`.
   (`agregar-modelo.py` declara solo los `.exp3.json` que encuentre sin declarar.)
3. Apúntale emociones en el `emotionMap` con su número nuevo, corre `python3 herramientas/comprobar.py` y
   reinicia la asistente.

Antes de modificar un modelo descargado, revisa que su licencia lo permita.

## Toques en la cabeza (opcional)

Con la asistente visible (modo mascota), sin `Ctrl`:

| Gesto | Reacción |
|---|---|
| Clic en la parte de arriba de la cabeza (frente y pelo) | expresión `cabeza` 2 segundos |
| Clic en una mejilla (a los lados, bajo los ojos) | expresión `mejilla` 2 segundos |
| Mantener apretada la cabeza (más de 0,4 s) o frotarla | expresión `caricia` mientras dure; la cabeza se recuesta hacia la mano y deja de seguir el cursor |

Ojos, nariz y boca no reaccionan, para no confundir un toque con otro. Al terminar vuelve a la cara que tenía;
si llega una respuesta durante un toque, su cara se aplica al terminar el toque, en vez de cortarlo.
Con `Ctrl` apretado, el clic arrastra al personaje.

Se configura en la entrada del modelo en `model_dict.json`:

```json
"partesCabeza": ["PartFace"],
"toques": { "cabeza": "exp_02", "mejilla": "exp_06", "caricia": "exp_02" }
```

- **`toques` usa el nombre de la expresión** (el `Name` del `.model3.json`), no su número. Si falta
  `caricia`, usa la de `cabeza`. Si el nombre no existe en el modelo, ese toque no hace nada.
- **`partesCabeza`**: partes del modelo que forman la cabeza; se usa la primera que tenga algo visible. Con
  ellas se calcula un recuadro en pantalla (ampliado un 10 % hacia arriba para incluir pelo y adornos) que
  también usa la mirada. Si no se pone, se prueban `head2`, `head`, `PartHead` y `PartFace`. Los nombres de
  las partes (`Id`) están en `Parts` del `.cdi3.json`:

  ```bash
  python3 -c "import json,sys; print([p['Id'] for p in json.load(open(sys.argv[1]))['Parts']])" Modelo.cdi3.json
  ```

  Conviene la parte que agrupa toda la cara (en Mao, `PartFace`). Si los toques caen corridos, prueba con otra.

## Si algo no anda

| Pasa | Revisa |
|---|---|
| La cara nunca cambia | Que el modelo tenga expresiones y `comprobar.py` no marque error en el `emotionMap`. |
| Casi siempre está neutral | Que `neutral` esté al final del mapa. |
| Una emoción pone una cara equivocada | El número: cuenta desde 0 en `FileReferences.Expressions`. |
| Se ve la etiqueta en el subtítulo | Que en la persona estén en minúsculas: `[Joy]` cambia la cara pero queda en el texto (solo se quitan las etiquetas en minúsculas, para no borrar cosas como `[GitHub]`). |
| La cara cambia de golpe | Sube el `FadeInTime` del `.exp3.json` (0,3–0,6 s se ve natural). |
| Los toques no reaccionan o caen corridos | `partesCabeza` (ver arriba) y que los nombres de `toques` existan. |
