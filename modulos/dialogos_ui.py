"""Gestion comun de dialogos, primer plano y foco de entrada.

Este modulo corrige dos problemas recurrentes de la interfaz:

* los avisos pueden quedar detras de un formulario secundario;
* una ventana que solicita datos puede abrirse sin el cursor en el campo.

La instalacion es global: los modulos que ya usan ``tkinter.messagebox`` o
``tkinter.simpledialog`` reciben el comportamiento corregido sin tener que
reescribir cada llamada.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from modulos.ventanas_tk import (
    activar_primer_plano_sistema,
    liberar_grab_temporal,
    resolver_parent_tk,
    restaurar_grab,
)


_INSTALADO = False
_ORIGINALES_MESSAGEBOX: dict[str, Callable[..., Any]] = {}
_ORIGINALES_SIMPLEDIALOG: dict[str, Callable[..., Any]] = {}


def _existe(widget: Any) -> bool:
    if widget is None:
        return False
    try:
        return bool(int(widget.winfo_exists()))
    except Exception:
        return False


def _leer_topmost(ventana: Any) -> bool:
    try:
        valor = ventana.attributes("-topmost")
        return str(valor).lower() not in ("", "0", "false", "none")
    except Exception:
        return False


def _poner_topmost(ventana: Any, activo: bool) -> None:
    if not _existe(ventana):
        return
    try:
        ventana.attributes("-topmost", bool(activo))
    except Exception:
        pass


def _traer_al_frente(ventana: Any) -> None:
    """Eleva una ventana y la convierte temporalmente en ventana activa."""

    if not _existe(ventana):
        return

    try:
        estado = str(ventana.state()).lower()
        if estado in ("withdrawn", "iconic"):
            ventana.deiconify()
    except Exception:
        pass

    try:
        ventana.update_idletasks()
    except Exception:
        pass

    try:
        ventana.lift()
    except Exception:
        pass

    _poner_topmost(ventana, True)

    try:
        ventana.focus_force()
    except Exception:
        pass

    try:
        ventana.update()
    except Exception:
        pass

    activar_primer_plano_sistema(ventana)


class _ContextoDialogo:
    """Prepara el padre visible y restaura su estado al cerrar el dialogo."""

    def __init__(self, parent: Any = None):
        self.parent_solicitado = parent
        self.parent = None
        self.raiz_temporal = None
        self.grab_anterior = None
        self.topmost_anterior = False

    def __enter__(self):
        self.parent = resolver_parent_tk(self.parent_solicitado)

        if self.parent is None:
            self.raiz_temporal = tk.Tk()
            self.raiz_temporal.withdraw()
            try:
                self.raiz_temporal.geometry("1x1+0+0")
                self.raiz_temporal.attributes("-alpha", 0.0)
            except Exception:
                pass
            self.parent = self.raiz_temporal

        self.grab_anterior = liberar_grab_temporal(self.parent)
        self.topmost_anterior = _leer_topmost(self.parent)
        _traer_al_frente(self.parent)
        return self.parent

    def __exit__(self, exc_type, exc_value, traceback):
        if self.raiz_temporal is None and _existe(self.parent):
            _poner_topmost(self.parent, self.topmost_anterior)
            try:
                self.parent.lift()
                self.parent.focus_force()
            except Exception:
                pass

        restaurar_grab(self.grab_anterior)

        if self.raiz_temporal is not None:
            try:
                self.raiz_temporal.destroy()
            except Exception:
                pass


class _DialogoEntrada:
    """Dialogo modal de entrada con foco garantizado en el campo editable."""

    def __init__(
        self,
        parent: tk.Misc,
        titulo: str,
        mensaje: str,
        tipo: str,
        initialvalue: Any = None,
        minvalue: Any = None,
        maxvalue: Any = None,
        show: str | None = None,
    ):
        self.parent = parent
        self.tipo = tipo
        self.minvalue = minvalue
        self.maxvalue = maxvalue
        self.resultado = None

        self.ventana = tk.Toplevel(parent)
        self.ventana._mantener_topmost = True
        self.ventana.withdraw()
        self.ventana.title(str(titulo or "Introducir dato"))
        self.ventana.resizable(False, False)
        try:
            self.ventana.transient(parent)
        except Exception:
            pass

        marco = tk.Frame(self.ventana, padx=18, pady=16)
        marco.pack(fill="both", expand=True)

        tk.Label(
            marco,
            text=str(mensaje or ""),
            justify="left",
            anchor="w",
            wraplength=520,
            font=("Segoe UI", 10),
        ).pack(fill="x", pady=(0, 12))

        self.variable = tk.StringVar(
            value="" if initialvalue is None else str(initialvalue)
        )
        opciones_entrada = {
            "textvariable": self.variable,
            "width": 58,
            "font": ("Segoe UI", 11),
        }
        if show is not None:
            opciones_entrada["show"] = show

        self.entrada = tk.Entry(marco, **opciones_entrada)
        self.entrada.pack(fill="x", pady=(0, 14))

        botones = tk.Frame(marco)
        botones.pack(fill="x")

        tk.Button(
            botones,
            text="Cancelar",
            width=13,
            command=self.cancelar,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            botones,
            text="Aceptar",
            width=13,
            command=self.aceptar,
            default="active",
        ).pack(side="right")

        self.ventana.protocol("WM_DELETE_WINDOW", self.cancelar)
        self.ventana.bind("<Return>", lambda evento: self.aceptar())
        self.ventana.bind("<Escape>", lambda evento: self.cancelar())

        self._mostrar_y_enfocar()
        self.ventana.wait_window()

    def _centrar(self) -> None:
        self.ventana.update_idletasks()
        ancho = max(600, self.ventana.winfo_reqwidth())
        alto = max(190, self.ventana.winfo_reqheight())

        try:
            if _existe(self.parent) and self.parent.winfo_viewable():
                x = self.parent.winfo_rootx() + max(
                    0, (self.parent.winfo_width() - ancho) // 2
                )
                y = self.parent.winfo_rooty() + max(
                    0, (self.parent.winfo_height() - alto) // 2
                )
            else:
                x = (self.ventana.winfo_screenwidth() - ancho) // 2
                y = (self.ventana.winfo_screenheight() - alto) // 2
        except Exception:
            x = 100
            y = 100

        x = max(0, x)
        y = max(0, y)
        self.ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _mostrar_y_enfocar(self) -> None:
        self._centrar()
        self.ventana.deiconify()
        try:
            self.ventana.grab_set()
        except Exception:
            pass

        def elevar() -> None:
            if not _existe(self.ventana):
                return
            _traer_al_frente(self.ventana)

        def enfocar() -> None:
            if not _existe(self.entrada):
                return
            elevar()
            try:
                self.entrada.focus_force()
                self.entrada.selection_range(0, tk.END)
                self.entrada.icursor(tk.END)
            except Exception:
                pass

        elevar()
        self.ventana.after_idle(enfocar)
        self.ventana.after(80, enfocar)
        # Se repite solo la elevacion, no la seleccion, para no interferir
        # cuando el operador ya ha comenzado a escribir.
        self.ventana.after(350, elevar)

    def _convertir(self, texto: str):
        if self.tipo == "string":
            return texto

        if self.tipo == "integer":
            try:
                valor = int(texto.strip())
            except Exception as error:
                raise ValueError("Introduce un numero entero valido.") from error
        elif self.tipo == "float":
            try:
                valor = float(texto.strip().replace(",", "."))
            except Exception as error:
                raise ValueError("Introduce un numero valido.") from error
        else:
            return texto

        if self.minvalue is not None and valor < self.minvalue:
            raise ValueError("El valor minimo permitido es " + str(self.minvalue) + ".")
        if self.maxvalue is not None and valor > self.maxvalue:
            raise ValueError("El valor maximo permitido es " + str(self.maxvalue) + ".")
        return valor

    def aceptar(self) -> None:
        try:
            self.resultado = self._convertir(self.variable.get())
        except ValueError as error:
            messagebox.showerror(
                "Valor no valido",
                str(error),
                parent=self.ventana,
            )
            self.ventana.after_idle(self._reenfocar)
            return

        self._cerrar()

    def _reenfocar(self) -> None:
        if not _existe(self.entrada):
            return
        try:
            self.entrada.focus_force()
            self.entrada.selection_range(0, tk.END)
        except Exception:
            pass

    def cancelar(self) -> None:
        self.resultado = None
        self._cerrar()

    def _cerrar(self) -> None:
        try:
            self.ventana.grab_release()
        except Exception:
            pass
        try:
            self.ventana.destroy()
        except Exception:
            pass


def _envolver_messagebox(nombre: str) -> Callable[..., Any]:
    original = _ORIGINALES_MESSAGEBOX[nombre]

    def llamada(*args, **kwargs):
        parent = kwargs.pop("parent", None)
        with _ContextoDialogo(parent) as padre:
            kwargs["parent"] = padre
            return original(*args, **kwargs)

    llamada.__name__ = nombre
    llamada.__doc__ = getattr(original, "__doc__", None)
    return llamada


def _pedir_entrada(tipo: str, title: str, prompt: str, **kwargs):
    parent = kwargs.pop("parent", None)
    initialvalue = kwargs.pop("initialvalue", None)
    minvalue = kwargs.pop("minvalue", None)
    maxvalue = kwargs.pop("maxvalue", None)
    show = kwargs.pop("show", None)

    with _ContextoDialogo(parent) as padre:
        dialogo = _DialogoEntrada(
            parent=padre,
            titulo=title,
            mensaje=prompt,
            tipo=tipo,
            initialvalue=initialvalue,
            minvalue=minvalue,
            maxvalue=maxvalue,
            show=show,
        )
        return dialogo.resultado


def _askstring(title, prompt, **kwargs):
    return _pedir_entrada("string", title, prompt, **kwargs)


def _askinteger(title, prompt, **kwargs):
    return _pedir_entrada("integer", title, prompt, **kwargs)


def _askfloat(title, prompt, **kwargs):
    return _pedir_entrada("float", title, prompt, **kwargs)


def instalar_dialogos_globales() -> None:
    """Instala una sola vez los envoltorios de dialogos de toda la aplicacion."""

    global _INSTALADO
    if _INSTALADO:
        return

    nombres_messagebox = (
        "showinfo",
        "showwarning",
        "showerror",
        "askquestion",
        "askokcancel",
        "askretrycancel",
        "askyesno",
        "askyesnocancel",
    )

    for nombre in nombres_messagebox:
        funcion = getattr(messagebox, nombre, None)
        if callable(funcion):
            _ORIGINALES_MESSAGEBOX[nombre] = funcion

    for nombre in nombres_messagebox:
        if nombre in _ORIGINALES_MESSAGEBOX:
            setattr(messagebox, nombre, _envolver_messagebox(nombre))

    for nombre in ("askstring", "askinteger", "askfloat"):
        funcion = getattr(simpledialog, nombre, None)
        if callable(funcion):
            _ORIGINALES_SIMPLEDIALOG[nombre] = funcion

    simpledialog.askstring = _askstring
    simpledialog.askinteger = _askinteger
    simpledialog.askfloat = _askfloat

    _INSTALADO = True


def _estado_editable(widget: Any) -> bool:
    try:
        if isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Spinbox)):
            return not widget.instate(["disabled"])
    except Exception:
        pass

    try:
        estado = str(widget.cget("state")).lower()
        return estado not in ("disabled", "readonly")
    except Exception:
        return True


def _buscar_primer_campo(widget: Any):
    try:
        hijos = list(widget.winfo_children())
    except Exception:
        return None

    tipos = (tk.Entry, tk.Spinbox, ttk.Entry, ttk.Combobox, ttk.Spinbox, tk.Text)

    for hijo in hijos:
        if isinstance(hijo, tipos) and _estado_editable(hijo):
            try:
                if hijo.winfo_viewable():
                    return hijo
            except Exception:
                return hijo

        encontrado = _buscar_primer_campo(hijo)
        if encontrado is not None:
            return encontrado

    return None


def _es_descendiente(widget: Any, top: Any) -> bool:
    if not _existe(widget) or not _existe(top):
        return False
    try:
        return widget.winfo_toplevel() == top
    except Exception:
        return False


def _enfocar_primer_campo(top: Any) -> None:
    if not _existe(top):
        return

    try:
        actual = top.focus_get()
    except Exception:
        actual = None

    # No se pisa el foco si el propio dialogo ya lo ha colocado correctamente.
    if actual is not None and actual is not top and _es_descendiente(actual, top):
        return

    campo = _buscar_primer_campo(top)
    if campo is None:
        return

    try:
        campo.focus_force()
    except Exception:
        return

    try:
        if isinstance(campo, (tk.Entry, tk.Spinbox, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
            campo.selection_range(0, tk.END)
            campo.icursor(tk.END)
        elif isinstance(campo, tk.Text):
            campo.mark_set("insert", "1.0")
    except Exception:
        pass


def configurar_enfoque_automatico(raiz: tk.Misc) -> None:
    """Enfoca el primer campo editable al abrir cualquier ``Toplevel``."""

    if not _existe(raiz):
        return
    if getattr(raiz, "_enfoque_automatico_instalado", False):
        return

    def al_mapear(evento):
        top = evento.widget
        if not isinstance(top, tk.Toplevel):
            return

        def activar():
            if not _existe(top):
                return
            _traer_al_frente(top)

        def soltar_topmost():
            if not _existe(top):
                return
            if getattr(top, "_mantener_topmost", False):
                return
            _poner_topmost(top, False)

        try:
            # Toda ventana secundaria nace delante del formulario que la abre.
            # Solo los dialogos modales marcados conservan topmost hasta cerrar.
            top.after_idle(activar)
            top.after(80, activar)
            top.after(120, lambda: _enfocar_primer_campo(top))
            top.after(1100, soltar_topmost)
        except Exception:
            pass

    raiz.bind_class("Toplevel", "<Map>", al_mapear, add="+")
    raiz._enfoque_automatico_instalado = True
