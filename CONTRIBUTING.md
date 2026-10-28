# Contribuir

¡Gracias! Reportes de fallos, ideas, documentación y código son bienvenidos.

## Reportar un fallo o proponer algo
- Abre un **issue** con la plantilla que corresponda. En los fallos, lo que más ayuda: qué dijiste o hiciste, qué
  esperabas, qué pasó, tu distro, escritorio y GPU, y el pedazo relevante de `servidor.log`.
- Preguntas y charla general ("¿alguien lo probó en KDE?"): en **Discussions**.

## Mandar un cambio (Pull Request)
1. Haz un fork y una rama a partir de `dev` (no de `main`: `main` es la última versión publicada).
2. Cambios chicos y de un solo tema por PR; explica el porqué en la descripción.
3. Corre `python3 herramientas/comprobar.py --importar`. Si tocaste el router o los intérpretes (lo que entiende
   la asistente), suma casos a `pruebas_intencion.py` (varias formas distintas de decir lo mismo) y córrelas.
4. Si cambias la configuración (`perfil.yaml`, `conf.yaml`, `entorno.sh`), actualiza los ejemplos y la doc, y
   anótalo en `CHANGELOG.md` bajo "Sin publicar" con cómo migrar.

Cómo está organizado el código (archivos propios y parches sobre Open-LLM-VTuber): ver [AGENTS.md](AGENTS.md),
sección "Modificar el código".

## Estilo
- Español en código, comentarios, textos y documentación (los nombres de upstream se quedan como están).
- Comentarios que expliquen el *porqué* (sobre todo lo que se aprendió probando), no el *qué*.
- Textos para el modelo con los marcadores de `identidad.py`; nunca nombres de personas, correos o rutas a mano.
- Nada de claves, datos personales ni modelos/voces que no se puedan redistribuir.

## Funciones y herramientas nuevas
Para enseñarle algo nuevo: una función en `funciones/` (`python3 herramientas/nueva-funcion.py <nombre>`; guía
en [docs/FUNCIONES.md](docs/FUNCIONES.md)), con sus `pruebas.py` y los totales de `pruebas_intencion.py` de antes y
después en el PR. Herramientas MCP: [docs/HERRAMIENTAS.md](docs/HERRAMIENTAS.md). Lo que ejecuta acciones debe
limitarse a una lista blanca y pedir confirmación para lo que no se puede deshacer. Se revisa con lupa: corre con
los permisos de quien lo instala.

## Versiones
El trabajo diario va a `dev`. Cuando hay un conjunto probado de cambios se publica una versión (`v0.x`) en
*Releases*, con su lista en `CHANGELOG.md`. Los cambios aceptados salen en la siguiente versión.

Al contribuir aceptas que tu aporte se publique bajo la licencia del repo (MIT; los parches sobre el cliente,
bajo la licencia del cliente de Open-LLM-VTuber).
