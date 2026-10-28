#!/usr/bin/env python3
"""Ventanita de recordatorios (python3 -m funciones.recordatorios.ventana, para un atajo de teclado): escribes «mañana 3pm entregar X», Enter y listo.

Muestra en vivo cómo lo entendió y los próximos recordatorios (con ✕ para borrar). Una sola instancia: el atajo
otra vez la cierra. Colores y fuentes del CSS de la asistente (perfil.yaml: estilo_css), versión clara u oscura
según el tema del sistema; sin ese archivo usa la paleta de abajo.
"""
import os
import re

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from identidad import ASISTENTE, BASE, PERFIL  # noqa: E402

from . import avisos  # noqa: E402
from . import google_calendario as calendario  # noqa: E402
from .fechas import describir, interpretar  # noqa: E402

APP_ID = "io.github.asistente.Recordatorios"  # = clase de la ventana (para las reglas del compositor)
# paleta por defecto (la misma estructura de variables que el CSS de la asistente: --bg, --teal, --pink-soft...)
CLARO = dict(bg="#f3f7f7", surface="#ffffff", ink="#14302e", muted="#557370", line="#cfe0de", teal="#12867e",
             teal_soft="#d6f1ee", pink="#c2306f", pink_soft="#fbe3ee", f_display="sans-serif", f_body="sans-serif",
             f_mono="monospace")
OSCURO = {**CLARO, **dict(bg="#0d1a1a", surface="#132525", ink="#dcefec", muted="#8fb0ac", line="#24403e",
                          teal="#4fd3c8", teal_soft="#173c39", pink="#f07aaa", pink_soft="#3a1b29")}
CSS = """
window, window.background {{ background: {bg}; color: {ink}; font-family: {f_body}; }}
.titulo {{ font-family: {f_display}; font-weight: 800; font-size: 17px; color: {teal}; }}
.entrada {{ background: {surface}; color: {ink}; border: 2px solid {line}; border-radius: 12px; padding: 8px 12px;
           font-size: 15px; box-shadow: none; outline: none; }}
.entrada:focus-within {{ border-color: {teal}; }}
.vista {{ color: {teal}; font-weight: 600; }}
.vista.error {{ color: {pink}; }}
.ayuda {{ color: {muted}; font-size: 12px; }}
.seccion {{ color: {muted}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
.fila {{ background: {surface}; border: 1px solid {line}; border-radius: 10px; padding: 6px 6px 6px 12px; }}
.cuando {{ font-family: {f_mono}; font-size: 11px; color: {muted}; }}
.etiqueta {{ background: {pink_soft}; color: {pink}; border-radius: 6px; padding: 0 6px; font-size: 10px;
            font-weight: 600; }}
.borrar {{ background: none; border: none; box-shadow: none; color: {muted}; min-width: 26px; min-height: 26px;
          border-radius: 8px; }}
.borrar:hover {{ background: {pink_soft}; color: {pink}; }}
.vacio {{ color: {muted}; font-style: italic; }}
"""


def paleta(oscuro: bool) -> dict:
    """Variables del CSS de la asistente: el primer bloque :root (claro) y :root[data-theme="dark"] (oscuro)."""
    base = OSCURO if oscuro else CLARO
    ruta = BASE / os.path.expanduser(PERFIL.get("estilo_css", "estilo.css"))
    try:
        css = ruta.read_text()
    except OSError:
        return base
    m = re.search(r':root\[data-theme="dark"\]\s*{([^}]*)}' if oscuro else r":root\s*{([^}]*)}", css)
    if not m:
        return base
    variables = {k.replace("-", "_"): v.strip() for k, v in re.findall(r"--([\w-]+):\s*([^;]+);", m.group(1))}
    if oscuro:  # el bloque oscuro no repite las fuentes
        variables = {**{k: v for k, v in paleta(False).items() if k.startswith("f_")}, **variables}
    return {**base, **{k: v for k, v in variables.items() if k in base}}


def oscuro() -> bool:
    try:
        return "dark" in Gio.Settings.new("org.gnome.desktop.interface").get_string("color-scheme")
    except Exception:
        return True


class Ventana(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=f"Recordatorio de {ASISTENTE}")
        self.set_default_size(470, -1)
        self.set_resizable(False)
        self.set_decorated(False)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=18,
                       margin_start=18, margin_end=18)
        self.set_child(caja)

        cabeza = Gtk.Box(spacing=10)
        icono = (Gtk.Image.new_from_file(avisos.ICONO) if avisos.ICONO.startswith("/")
                 else Gtk.Image.new_from_icon_name(avisos.ICONO))
        icono.set_pixel_size(36)
        cabeza.append(icono)
        titulo = Gtk.Label(label="¿Qué te recuerdo?", xalign=0)
        titulo.add_css_class("titulo")
        cabeza.append(titulo)
        caja.append(cabeza)

        self.entrada = Gtk.Entry(placeholder_text="mañana 3pm entregar lo de Proyectos")
        self.entrada.add_css_class("entrada")
        self.entrada.connect("changed", self.al_escribir)
        self.entrada.connect("activate", self.al_enter)
        caja.append(self.entrada)

        self.calendario = Gtk.CheckButton(label="📅 Apuntarlo también en Google Calendar",
                                          visible=calendario.configurado())
        self.calendario.add_css_class("ayuda")
        self.calendario.connect("toggled", lambda *_: self.al_escribir(self.entrada))
        caja.append(self.calendario)

        self.vista = Gtk.Label(xalign=0, wrap=True)
        self.vista.add_css_class("vista")
        caja.append(self.vista)
        ayuda = Gtk.Label(xalign=0, wrap=True, label="en 20 min sacar la ropa · todos los lunes 7am gym · "
                                                     "el 5 de nov examen · cada mes el 1 pagar internet")
        ayuda.add_css_class("ayuda")
        caja.append(ayuda)

        seccion = Gtk.Label(label="PRÓXIMOS", xalign=0, margin_top=6)
        seccion.add_css_class("seccion")
        caja.append(seccion)
        self.lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caja.append(self.lista)
        self.llenar_lista()
        self.al_escribir(self.entrada)

        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", lambda _c, k, _cod, _m: k == Gdk.KEY_Escape and (self.close() or True))
        self.add_controller(teclas)

    def al_escribir(self, entrada):
        texto = entrada.get_text().strip()
        self.vista.remove_css_class("error")
        if not texto:
            self.vista.set_label("Escribe qué y cuándo, en cualquier orden.")
            return
        r = interpretar(texto)
        if "error" in r:
            self.vista.add_css_class("error")
            self.vista.set_label(r["error"])
        else:
            extra = ("\n📅 Sin hora: en el calendario va de todo el día (escribe una hora si no)"
                     if self.calendario.get_active() and not r["con_hora"] else "")
            self.vista.set_label(f"🔔 {describir(r['cuando'], r['repetir'])} · {r['texto']}{extra}")

    def al_enter(self, entrada):
        r = avisos.agregar(entrada.get_text(), "ventana")
        if "error" in r:
            self.vista.add_css_class("error")
            self.vista.set_label(r["error"])
            return
        extra = ""
        if self.calendario.get_active():
            i = interpretar(entrada.get_text())
            try:
                calendario.apuntar(i["texto"], i["cuando"], i["con_hora"], i["repetir"])
                extra = " y quedó en tu calendario"
            except Exception as e:
                extra = f" (no se pudo apuntar en el calendario: {e})"
        self.vista.set_label(f"✓ Listo, te aviso {r['cuando_texto']}{extra}")
        entrada.set_text("")
        entrada.set_sensitive(False)
        self.llenar_lista()
        GLib.timeout_add(900, lambda: self.close() or False)

    def llenar_lista(self):
        while (hijo := self.lista.get_first_child()):
            self.lista.remove(hijo)
        pendientes = avisos.pendientes()
        if not pendientes:
            vacio = Gtk.Label(label="Nada pendiente.", xalign=0)
            vacio.add_css_class("vacio")
            self.lista.append(vacio)
        for r in pendientes[:7]:
            fila = Gtk.Box(spacing=8)
            fila.add_css_class("fila")
            textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            nombre = Gtk.Label(label=r["texto"], xalign=0, ellipsize=3)
            textos.append(nombre)
            debajo = Gtk.Box(spacing=6)
            cuando = Gtk.Label(label=r["cuando_texto"], xalign=0)
            cuando.add_css_class("cuando")
            debajo.append(cuando)
            if r.get("repetir") or r.get("origen") == "calendario":
                etiqueta = Gtk.Label(label="se repite" if r.get("repetir") else "calendario")
                etiqueta.add_css_class("etiqueta")
                debajo.append(etiqueta)
            textos.append(debajo)
            fila.append(textos)
            boton = Gtk.Button(label="✕", tooltip_text="Borrar", valign=Gtk.Align.CENTER)
            boton.add_css_class("borrar")
            boton.connect("clicked", lambda _b, rid=r["id"]: (avisos.borrar(rid), self.llenar_lista()))
            fila.append(boton)
            self.lista.append(fila)
        if len(pendientes) > 7:
            mas = Gtk.Label(label=f"y {len(pendientes) - 7} más…", xalign=0)
            mas.add_css_class("ayuda")
            self.lista.append(mas)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.ventana = None

    def do_activate(self):
        if self.ventana:  # segunda vez el atajo = cerrar
            self.ventana.close()
            return
        css = Gtk.CssProvider()
        css.load_from_string(CSS.format(**paleta(oscuro())))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.ventana = Ventana(self)
        self.ventana.connect("close-request", lambda *_: setattr(self, "ventana", None) or False)
        self.ventana.present()
        self.ventana.entrada.grab_focus()


if __name__ == "__main__":
    App().run([])
