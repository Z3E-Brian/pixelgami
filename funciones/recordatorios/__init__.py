"""Recordatorios y calendario de la asistente (los avisos llegan aunque ella esté apagada).

  funcion.py            la parte de la conversación: entender lo que se le pide y hacerlo (ver funciones/__init__.py)
  fechas.py             entender «mañana 3pm entregar X» (sin efectos)
  avisos.py             guardar recordatorios (datos/recordatorios/) y el servicio que avisa
                        (python3 -m funciones.recordatorios.avisos vigilar)
  google_calendario.py  leer y apuntar en Google Calendar vía un Apps Script propio (calendario.gs)
  ventana.py            ventanita para crearlos con un atajo (python3 -m funciones.recordatorios.ventana)
Se usa desde la carpeta de la instalación (la de identidad.py), que debe estar en sys.path.
Pruebas sin modelo: python3 -m unittest discover -s funciones/recordatorios -t .
"""
