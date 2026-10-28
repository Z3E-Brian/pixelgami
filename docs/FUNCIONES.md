# Funciones: enseñarle algo nuevo

Todo lo que la asistente **hace** es una **función**, es decir, una carpeta dentro de `funciones/`. Vienen estas:

| Carpeta | Tema | Qué hace |
|---|---|---|
| `ventanas` | `ventanas` | abrir, cerrar y mover apps, juegos, proyectos y ventanas |
| `correo` | `correo` | revisar, leer, marcar, archivar y mover correos (solo acciones reversibles) |
| `musica` | `musica` | YouTube Music: poner, sugerir, pausar, pasar, volumen |
| `web` | `web` | buscar en internet, abrir resultados y sitios, leer páginas |
| `pc` | `pc` | el estado del PC (RAM, disco, CPU, GPU, temperaturas) |
| `hora_mundo` | `hora_mundo` | la hora en otros lugares |
| `horas_juego` | `horas_juego` | cuánto has jugado cada juego |
| `recordatorios` | `recordatorio` | recordatorios como notificación y Google Calendar |

El **núcleo** (`asistente_contexto.py`) no sabe hacer nada de esto. Se encarga de entender cada mensaje con el
router, de la conversación, la memoria y la personalidad, y de juntar lo que devuelven las funciones. Para agregar
una función no hace falta tocarlo:

```bash
python3 herramientas/nueva-funcion.py clima
```

Crea `funciones/clima/` con todo lo necesario y un ejemplo que ya funciona. Después lo cambias por lo tuyo.

## Cómo pasa un mensaje

```
"oye, qué hora es en Japón"                  (voz o chat: Whisper pasa la voz a texto antes)
   │
   ▼  pendiente() de cada función: ¿responde algo que ella preguntó? ("¿los borro?" → "sí")  → se hace y listo
   ▼  router (modelo local): reescribe la orden con la conversación y elige temas   ← funcion.yaml de cada una
   ▼  regla() de cada función: corrige al router en lo que nunca debe fallar
   │     temas ["hora_mundo"]
   ▼  entender(pedido, modelo) de cada función de esos temas → intención (None: nada para ella)
   ▼  aviso(intención): "Dame un segundo…" mientras trabaja (opcional)
   ▼  ejecutar(intención, pedido) → Resultado: los hechos
   ▼  datos(pedido) de las demás: lo que sepan para responder ("¿qué tengo mañana?" → la agenda)
   │
   ▼  la asistente responde con esos hechos, con su voz y su personalidad
```

## La carpeta

```
funciones/clima/
  __init__.py      una línea de descripción
  funcion.yaml     lo que el router necesita saber
  funcion.py       lo que hace
  pruebas.py       frases reales con el resultado esperado (se corren con el modelo)
  test_clima.py    pruebas sin modelo (unittest)
```

### funcion.yaml

```yaml
tema: clima                     # en minúsculas, sin espacios: el nombre que usa el router
orden: 100                      # dónde va en el router y en qué orden se ejecuta (las de serie: 10 a 80)
descripcion: |-
  el clima o el pronóstico de un lugar ("¿va a llover mañana?", "¿qué temperatura hace en Lima?").
ejemplos: |-
  {usuario}: "¿llueve hoy?" -> temas ["clima"]
  {asistente}: "En Lima hay 18 °C." / {usuario}: "¿y mañana?" -> orden "dime el pronóstico de mañana en Lima", temas ["clima"]
cede_a: []                      # opcional: temas ante los que se aparta si actúan con el mismo mensaje
si_falla: No pudiste ver el clima ({error}). Díselo en una frase.
```

- **`descripcion`** va en la lista de temas del router, como `- "clima": <descripción>`. Di qué cubre y, si se
  puede confundir con otro tema, qué **no** es suyo ("preguntar la hora de aquí es charla").
- **`ejemplos`**: pocos y buenos (2 o 3), en el mismo formato que los demás. Uno con `{asistente}` le enseña a
  resolver «¿y mañana?» con la conversación. Si un ejemplo ocupa varias líneas, las siguientes empiezan con
  espacio. El router los mezcla por rondas con los de las otras funciones (el primero de cada una, luego el
  segundo…): con todos los de un tema seguidos, el modelo se sesgaba hacia ese tema.
- **`cede_a`**: las ventanas tienen `[correo, web]`. Si el correo o internet hacen algo con el mensaje, «ábrelo»
  no se toma como abrir una app.
- **`si_falla`**: lo que se le dice a la asistente si `ejecutar()` lanza un error. `{error}` es el error.
- Marcadores: `{asistente}` y `{usuario}` (los nombres de `conf.yaml`), `{lugar}`, `{navegador}`. Lista completa
  en `identidad.py`.

Cuantos más temas tiene el router, más le cuesta a un modelo chico elegir bien. Por eso conviene que los textos
sean cortos y claros, y que cada función pase sus casos de `pruebas.py` **y los de las demás**.

### funcion.py

Solo `entender` y `ejecutar` son obligatorias:

```python
from funciones import Pedido, Resultado
from identidad import nombres

INTERPRETAR = nombres("""{usuario} pregunta por el clima. Devuelve el lugar ("" = donde vive) y el día.""")
ESQUEMA = {"type": "object", "properties": {"lugar": {"type": "string"}, "dia": {"type": "string"}},
           "required": ["lugar", "dia"]}


def entender(pedido: Pedido, modelo) -> dict | None:
    return modelo(INTERPRETAR, pedido.combinado, ESQUEMA)  # None = nada para esta función


def ejecutar(intencion: dict, pedido: Pedido) -> Resultado | None:
    pronostico = consultar(intencion["lugar"], intencion["dia"])
    return Resultado(f"Pronóstico: {pronostico}. Díselo en una frase.", hizo=False)
```

| Parte | Qué recibe y devuelve |
|---|---|
| `entender(pedido, modelo)` | La intención (lo que quieras: dict, lista…) o `None` si no hay nada que hacer. `modelo(sistema, texto, esquema)` es el modelo local con salida JSON (`None` si no respondió). |
| `ejecutar(intencion, pedido)` | Lo hace y devuelve un `Resultado`, o `None` si no hay nada que contar. Si lanza una excepción, la asistente dice `si_falla`. |
| `aviso(intencion)` *(opcional)* | Lo que dice mientras trabaja, si tarda: `"Reviso el clima, un segundo."`. |
| `regla(texto, orden, temas)` *(opcional)* | Una regla fija por encima del router: `True` = es mío, `False` = no es mío, `None` = que decida el router. Para lo que **nunca** puede fallar ("recuérdame…" siempre es un recordatorio; "abre YouTube y pon música" no es internet). `temas` son los que eligió el router. |
| `detectar(texto)` *(opcional)* | Respaldo con expresiones regulares para cuando el modelo no responde (Ollama apagado). Si falta, se usa `regla`. |
| `pendiente(texto)` *(opcional)* | La respuesta a algo que la función preguntó ("¿los mando a la papelera?" → "sí"). Se revisa **antes** del router. Devuelve un `Resultado` o `None`. |
| `datos(pedido)` *(opcional)* | Información para que responda aunque no se pida hacer nada ("¿qué tengo mañana?" → la agenda). Devuelve texto o `None`. |
| `para_el_router()` *(opcional)* | Lo que el router debe saber de la conversación para entender «ábrelo» o «¿y en Reddit?» ("Última búsqueda: …"). |
| `respondio()` *(opcional)* | La asistente empezó a responder (las ventanas lo usan para no repetir lo que ya contó). |

**`Pedido`** trae el mensaje en varias versiones:
- `texto`: sus palabras exactas.
- `orden`: la reescribió el router con la conversación («¿y mañana?» → «dime el pronóstico de mañana en Lima»).
- `combinado`: la orden **y** sus palabras exactas. Es lo que conviene pasarle al modelo.
- `resuelto`: la orden si hizo falta la conversación para entenderlo; si no, sus palabras tal cual.

Además trae `necesita_contexto` (si el mensaje no se entendía solo), `temas` (los que eligió el router) y `ahora`
(la fecha y hora del mensaje). Usa `ahora` en vez de llamar a `datetime.now()`, así las pruebas pueden fijar la
hora.

**`Resultado`** son **hechos**, no frases de la asistente: la personalidad se la pone ella al responder.
- `contexto`: lo que pasó y cómo decirlo ("Ya quedó agendado: …, el viernes a las 10:00. Confírmaselo en una frase.").
- `preguntar=True` si falta un dato o hay que confirmar, y la respuesta tiene que ser una pregunta.
- `hizo=False` si solo informa. Si hizo algo, la asistente no ofrece otras cosas y "apunta que…" no se guarda
  como nota de memoria.
- `con_notas=True` si sus notas de memoria ayudan. Por defecto no se le pasan, porque se mezclan con los datos.
- `revisar_frase`: una función que revisa cada frase de la respuesta y devuelve qué decir en su lugar si inventó
  algo. Internet la usa para los precios que no salieron en la búsqueda.

**Ayudas** de `funciones`:
- `mcp("google")`: el servidor MCP `google-mcp/servidor_google.py` como módulo, compartido con el núcleo y cargado
  recién cuando se usa.
- `Frases({...})`: avisos que no repiten la misma forma dos veces seguidas.
- `carpeta_datos("clima")`: `datos/clima/`, donde guarda lo suyo.
- `log`: el registro del backend.
- `y(["a", "b"])`: "a y b".

### Reglas para que salga bien

- **El modelo interpreta, Python calcula.** Un modelo de 8B entiende bien qué quieres, pero se equivoca con fechas,
  cuentas y horas. Que el modelo devuelva la zona horaria y que Python calcule la hora; que devuelva el «cuándo»
  tal cual lo dijiste y que lo convierta código probado (`funciones/recordatorios/fechas.py`).
- **Lo que modifica algo**, como borrar, mover o enviar, debe ser reversible o pedir confirmación con
  `pendiente()` (mira cómo lo hace el correo con la papelera). Nunca ejecutes comandos de la shell armados con lo
  que dijo el modelo; usa una lista blanca, como las ventanas.
- **Lo que guardes** va en `carpeta_datos(...)`, nunca dentro de la carpeta del código.
- **Claves y configuración personal** van en `~/.config/<instalación>/` o en `perfil.yaml`, no en el código.
  Si falta algo, `ejecutar` lo dice en el `Resultado` ("Todavía no está conectado: …").
- **Si algo debe funcionar con la asistente apagada**, como los avisos de los recordatorios, ponlo en un servicio
  aparte dentro de la misma carpeta y usa la parte de la función que no necesita el modelo.

## Activarlas

Si `perfil.yaml` no tiene `funciones:`, se cargan todas las carpetas de `funciones/`, por su `orden`. Para elegir
cuáles y en qué orden:

```yaml
funciones: [ventanas, correo, musica, web, pc, hora_mundo, horas_juego, recordatorios, clima]
```

Reinicia la asistente (Super+Shift+Z o `escritorio/asistente_reiniciar.sh`).

## Probarlas

```bash
python3 -m unittest discover -s funciones -t .                            # sin modelo, todas
cd Open-LLM-VTuber && uv run python ../pruebas_intencion.py clima         # con el modelo, solo la tuya
cd Open-LLM-VTuber && uv run python ../pruebas_intencion.py               # todo (antes de un PR)
```

`pruebas.py` tiene:
- **`ROUTER`**: frases y temas esperados, `(último mensaje de la asistente, mensaje anterior, lo que dice, {temas},
  [palabras que deben quedar en la orden])`. Incluye frases que **no** son de tu función, para que no se robe
  mensajes ajenos.
- **`CADENA`** *(opcional)*: frases que pasan por el router y por tu `entender()`, `(la asistente, mensaje
  anterior, lo que dice, …lo esperado)`, y `revisar(caso, intencion, aviso) -> (bien, texto)`, que compara con lo
  esperado. No ejecuta nada.
- *(opcional)* `CON_CUALQUIER_TEMA = True` prueba `entender()` aunque el router no elija tu tema. `preparar()` y
  `limpiar()` arman y quitan el estado que necesites, como una búsqueda ya hecha.

Cuando agregues una función, corre **todas** las pruebas: un tema nuevo puede quitarle mensajes a otro. En un
PR, pega los totales de antes y después.

### Prueba de fuego (opcional, antes de una versión)

`prueba_de_fuego.py` pasa frases ajenas por el router y por `entender()`: las de prueba en español de
[MASSIVE](https://github.com/alexa/massive) (Amazon, CC BY 4.0), con 59 intenciones de asistentes de voz. Mide si
cada pedido llega a su función y, sobre todo, si alguna se roba lo que no es suyo (domótica, cocina, transporte…).
Con `--voz` también las dice con Edge TTS y las pasa por Whisper.

```bash
curl -LO https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz
tar -xzf amazon-massive-dataset-1.1.tar.gz 1.1/data/es-ES.jsonl
cd Open-LLM-VTuber && uv run python ../prueba_de_fuego.py --massive ../1.1/data/es-ES.jsonl --n 300 --voz 100
```

Si tu función cubre alguna de sus intenciones, agrégala en `ESPERADO` (por ejemplo `weather_query` para una de
clima).
