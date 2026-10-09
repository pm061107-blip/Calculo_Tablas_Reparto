"""Ventana comun de progreso para calculos largos.

Se usa en calculos sin hilos para mantener una indicacion visual de avance.
La ventana se actualiza mediante ``update_idletasks``/``update`` en puntos
controlados del propio proceso.
"""

import tkinter as tk
from tkinter import ttk

from modulos.ventanas_tk import forzar_ventana_visible


class DialogoProgreso:
    """Dialogo modal ligero con barra determinada o indeterminada."""

    def __init__(self, parent=None, titulo="Procesando", mensaje="Procesando...", total=None):
        self.parent = parent
        self.total = total if total and int(total) > 0 else None
        self.actual = 0
        self.cerrado = False

        self.ventana = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
        self.ventana.withdraw()
        self.ventana.title(titulo)
        self.ventana.resizable(False, False)
        self.ventana.protocol("WM_DELETE_WINDOW", lambda: None)

        marco = tk.Frame(self.ventana, padx=22, pady=18)
        marco.pack(fill="both", expand=True)

        self.lbl_mensaje = tk.Label(
            marco,
            text=mensaje,
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
            width=56,
        )
        self.lbl_mensaje.pack(fill="x", pady=(0, 10))

        modo = "determinate" if self.total else "indeterminate"
        self.barra = ttk.Progressbar(marco, orient="horizontal", length=520, mode=modo)
        self.barra.pack(fill="x")

        self.lbl_detalle = tk.Label(
            marco,
            text="",
            font=("Arial", 9),
            anchor="w",
            justify="left",
        )
        self.lbl_detalle.pack(fill="x", pady=(8, 0))

        if self.total:
            self.barra.configure(maximum=self.total, value=0)
            self.lbl_detalle.config(text="0 / " + str(self.total))
        else:
            self.barra.start(12)
            self.lbl_detalle.config(text="Espere, el calculo puede tardar unos segundos...")

        self._centrar()
        self.ventana.deiconify()
        forzar_ventana_visible(self.ventana, parent=parent, mantener_arriba=True)
        self._refrescar()

    def _centrar(self):
        try:
            self.ventana.update_idletasks()
            ancho = 620
            alto = 135
            if self.parent is not None:
                px = int(self.parent.winfo_rootx())
                py = int(self.parent.winfo_rooty())
                pw = int(self.parent.winfo_width())
                ph = int(self.parent.winfo_height())
                x = px + max(0, (pw - ancho) // 2)
                y = py + max(0, (ph - alto) // 2)
            else:
                pantalla_ancho = int(self.ventana.winfo_screenwidth())
                pantalla_alto = int(self.ventana.winfo_screenheight())
                x = max(0, (pantalla_ancho - ancho) // 2)
                y = max(0, (pantalla_alto - alto) // 2)
            self.ventana.geometry(f"{ancho}x{alto}+{x}+{y}")
        except Exception:
            pass

    def _refrescar(self):
        if self.cerrado:
            return
        try:
            self.ventana.update_idletasks()
            self.ventana.update()
        except Exception:
            pass

    def actualizar(self, mensaje=None, actual=None, total=None, detalle=None):
        if self.cerrado:
            return
        try:
            if mensaje is not None:
                self.lbl_mensaje.config(text=str(mensaje))
            if total is not None and int(total) > 0:
                total = int(total)
                if self.total != total:
                    self.total = total
                    self.barra.stop()
                    self.barra.configure(mode="determinate", maximum=total)
            if actual is not None:
                self.actual = max(0, int(actual))
                if self.total:
                    self.barra.configure(value=min(self.actual, self.total))
            if detalle is not None:
                self.lbl_detalle.config(text=str(detalle))
            elif self.total:
                self.lbl_detalle.config(text=str(self.actual) + " / " + str(self.total))
            self._refrescar()
        except Exception:
            pass

    def cerrar(self):
        if self.cerrado:
            return
        self.cerrado = True
        try:
            self.barra.stop()
        except Exception:
            pass
        try:
            self.ventana.destroy()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cerrar()
        return False
