"""Selector robusto de estados para la importacion de ESTAREPP.

V17.9 elimina el encadenamiento de Toplevel modales que causaba ventanas
invisibles o bloqueos cuando el formulario principal estaba retirado y el
formulario de trabajo ya tenia un ``grab_set`` activo.

Cuando existe un formulario padre, el analisis y la seleccion se muestran en
UN UNICO panel modal embebido dentro de ese mismo formulario:

    Analizando ESTAREPP -> Selector Estado inicial / 1 / 2

No se crea ningun subformulario adicional, no se cambia de ventana entre ambas
fases y nunca se usa la raiz principal retirada como propietario visual.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Optional

from modulos.ventanas_tk import resolver_parent_tk


ORDEN_ESTADOS = ("INICIAL", "1", "2")
VERSION_SELECTOR = "V17.9"

def _log(mensaje):
    """Escribe diagnostico sin interferir con la interfaz."""
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.cwd()))
        carpeta = base / "Calculo_Tablas_Reparto" / "logs"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / "selector_estarepp.log"
        with open(ruta, "a", encoding="utf-8") as archivo:
            archivo.write(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + " | " + VERSION_SELECTOR + " | " + str(mensaje) + "\n"
            )
    except Exception:
        pass


class _FlujoEstadosESTAREPP:
    """Panel modal embebido para analizar y seleccionar estados."""

    def __init__(
        self,
        parent=None,
        ficheros: Optional[Iterable] = None,
        funcion_analisis: Optional[Callable] = None,
        resumen=None,
        mostrar_progreso: bool = True,
    ):
        self.parent = resolver_parent_tk(parent)
        self.root_creado = False

        if self.parent is None:
            # Este camino solo se usa al ejecutar el importador de forma
            # independiente. En la aplicacion siempre se recibe el formulario
            # visible como padre explicito.
            self.parent = tk.Tk()
            self.parent.title("ESTAREPP - Seleccionar estados")
            self.parent.geometry("760x520")
            self.parent.resizable(True, True)
            self.root_creado = True

        self.ficheros = [Path(x) for x in (ficheros or [])]
        self.funcion_analisis = funcion_analisis
        self.resumen = resumen
        self.mostrar_progreso = bool(mostrar_progreso and funcion_analisis is not None)

        self.resultado = None
        self.error = None
        self.vars = {}
        self.cola = queue.Queue()
        self.inicio = time.monotonic()
        self.minimo_visible = 0.45
        self.hilo = None
        self.finalizado = tk.BooleanVar(master=self.parent, value=False)
        self.grab_anterior = self._obtener_grab_actual()
        self._escape_bind_id = None

        self.overlay = tk.Frame(
            self.parent,
            background="#e9eef5",
            highlightbackground="#5b7da5",
            highlightthickness=2,
        )
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay.lift()

        self.panel = tk.Frame(
            self.overlay,
            background="#ffffff",
            relief="raised",
            borderwidth=2,
            padx=24,
            pady=20,
        )
        self.panel.place(relx=0.5, rely=0.5, anchor="center")

        self._preparar_modal()
        try:
            _log(
                "Panel embebido creado. Parent=" + str(self.parent)
                + " | titulo=" + str(self.parent.title())
                + " | progreso=" + str(self.mostrar_progreso)
            )
        except Exception:
            _log("Panel embebido creado")

        if self.mostrar_progreso:
            self._mostrar_progreso()
            # ``after_idle`` garantiza que el panel se pinte antes de iniciar
            # la lectura del fichero, incluso dentro del EXE de PyInstaller.
            self.parent.after_idle(self._iniciar_analisis)
        else:
            self._mostrar_selector(self.resumen or {})

    # ------------------------------------------------------------------
    # Modalidad embebida
    # ------------------------------------------------------------------
    def _obtener_grab_actual(self):
        try:
            grab = self.parent.grab_current()
            if grab is not None and int(grab.winfo_exists()) == 1:
                return grab
        except Exception:
            pass
        return None

    def _preparar_modal(self):
        try:
            if self.grab_anterior is not None:
                self.grab_anterior.grab_release()
        except Exception:
            pass

        try:
            self.parent.deiconify()
            self.parent.lift()
            self.parent.focus_force()
        except Exception:
            pass

        try:
            self.overlay.grab_set()
        except Exception:
            pass

        try:
            self._escape_bind_id = self.parent.bind(
                "<Escape>",
                lambda _evento: self.cancelar(),
                add="+",
            )
        except Exception:
            self._escape_bind_id = None

        try:
            self.parent.update_idletasks()
            self.overlay.update_idletasks()
        except Exception:
            pass

    def _restaurar_modal(self):
        try:
            self.overlay.grab_release()
        except Exception:
            pass

        if self._escape_bind_id is not None:
            try:
                self.parent.unbind("<Escape>", self._escape_bind_id)
            except Exception:
                pass

        try:
            self.overlay.destroy()
        except Exception:
            pass

        try:
            if (
                self.grab_anterior is not None
                and int(self.grab_anterior.winfo_exists()) == 1
            ):
                self.grab_anterior.grab_set()
                self.grab_anterior.lift()
                self.grab_anterior.focus_force()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilidades de interfaz
    # ------------------------------------------------------------------
    def _limpiar_panel(self):
        for widget in list(self.panel.winfo_children()):
            try:
                widget.destroy()
            except Exception:
                pass

    def _nombre_fichero(self):
        if len(self.ficheros) == 1:
            return self.ficheros[0].name
        if len(self.ficheros) > 1:
            return str(len(self.ficheros)) + " ficheros ESTAREPP"
        return ""

    @staticmethod
    def formatear_lotes(valor):
        valor = float(valor or 0)
        if abs(valor - round(valor)) < 0.0000001:
            return f"{int(round(valor)):,}".replace(",", ".")
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _cabecera(self, titulo):
        tk.Label(
            self.panel,
            text=titulo,
            font=("Segoe UI", 14, "bold"),
            background="#ffffff",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        tk.Label(
            self.panel,
            text="Selector ESTAREPP " + VERSION_SELECTOR,
            font=("Segoe UI", 8),
            foreground="#666666",
            background="#ffffff",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(1, 6))

        nombre = self._nombre_fichero()
        if nombre:
            tk.Label(
                self.panel,
                text="Fichero: " + nombre,
                font=("Segoe UI", 9),
                background="#ffffff",
                anchor="w",
            ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 8))

    # ------------------------------------------------------------------
    # Fase 1: analisis
    # ------------------------------------------------------------------
    def _mostrar_progreso(self):
        self._limpiar_panel()
        self._cabecera("Analizando ESTAREPP")

        tk.Label(
            self.panel,
            text=(
                "Calculando los lotes de Estado inicial, Estado 1 y Estado 2.\n"
                "La aplicacion seguira disponible cuando finalice el analisis."
            ),
            justify="left",
            background="#ffffff",
            font=("Segoe UI", 10),
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 14))

        self.barra = ttk.Progressbar(
            self.panel,
            mode="indeterminate",
            length=430,
        )
        self.barra.grid(row=4, column=0, columnspan=4, sticky="ew")
        self.barra.start(12)

        self.lbl_progreso = tk.Label(
            self.panel,
            text="Leyendo fichero...",
            font=("Segoe UI", 9),
            foreground="#444444",
            background="#ffffff",
        )
        self.lbl_progreso.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.panel.grid_columnconfigure(0, weight=1)
        try:
            self.parent.update_idletasks()
            self.overlay.lift()
        except Exception:
            pass

    def _iniciar_analisis(self):
        if self.finalizado.get():
            return

        def trabajador():
            try:
                resultado = self.funcion_analisis()
                self.cola.put(("OK", resultado))
            except BaseException as error:  # se propaga al hilo Tk
                self.cola.put(("ERROR", error))

        self.hilo = threading.Thread(
            target=trabajador,
            name="AnalisisEstadosESTAREPP",
            daemon=True,
        )
        _log("Inicio del analisis en segundo plano")
        self.hilo.start()
        self.parent.after(70, self._revisar_analisis)

    def _revisar_analisis(self):
        if self.finalizado.get():
            return

        try:
            tipo, valor = self.cola.get_nowait()
        except queue.Empty:
            try:
                self.parent.after(70, self._revisar_analisis)
            except Exception:
                self.cancelar()
            return

        restante = self.minimo_visible - (time.monotonic() - self.inicio)
        if restante > 0:
            self.parent.after(
                max(1, int(restante * 1000)),
                lambda: self._finalizar_analisis(tipo, valor),
            )
        else:
            self._finalizar_analisis(tipo, valor)

    def _finalizar_analisis(self, tipo, valor):
        try:
            self.barra.stop()
        except Exception:
            pass

        if tipo == "ERROR":
            _log("Error de analisis: " + repr(valor))
            self.error = valor
            self.finalizado.set(True)
            return

        self.resumen = valor or {}
        _log(
            "Analisis finalizado. Inicial="
            + str(self.resumen.get("INICIAL", {}).get("Lotes", 0))
            + " | E1=" + str(self.resumen.get("1", {}).get("Lotes", 0))
            + " | E2=" + str(self.resumen.get("2", {}).get("Lotes", 0))
        )
        self._mostrar_selector(self.resumen)

    # ------------------------------------------------------------------
    # Fase 2: selector en el MISMO panel
    # ------------------------------------------------------------------
    def _mostrar_selector(self, resumen):
        self._limpiar_panel()
        self.vars = {}
        self._cabecera("Seleccion de estados del ESTAREPP")

        tk.Label(
            self.panel,
            text=(
                "Marca uno o varios estados. Solo se importaran los registros "
                "de los estados seleccionados."
            ),
            justify="left",
            wraplength=610,
            background="#ffffff",
            font=("Segoe UI", 10),
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 14))

        encabezados = ("Importar", "Estado", "Registros", "Lotes")
        anclas = ("center", "w", "e", "e")
        for columna, texto in enumerate(encabezados):
            tk.Label(
                self.panel,
                text=texto,
                font=("Segoe UI", 9, "bold"),
                background="#ffffff",
                anchor=anclas[columna],
            ).grid(
                row=4,
                column=columna,
                sticky="ew" if columna != 1 else "w",
                padx=(0, 18 if columna < 3 else 0),
            )

        etiquetas = {
            "INICIAL": "Estado inicial (Estado en blanco)",
            "1": "Estado 1",
            "2": "Estado 2",
        }

        fila = 5
        for estado in ORDEN_ESTADOS:
            datos = resumen.get(estado, {})
            registros = int(datos.get("Registros", 0) or 0)
            lotes = float(datos.get("Lotes", 0) or 0)

            variable = tk.BooleanVar(master=self.parent, value=False)
            self.vars[estado] = variable

            chk = tk.Checkbutton(
                self.panel,
                variable=variable,
                command=self._actualizar_total_seleccionado,
                background="#ffffff",
                activebackground="#ffffff",
                takefocus=True,
                name="estado_" + estado.lower(),
            )
            if registros <= 0:
                chk.configure(state="disabled")

            chk.grid(row=fila, column=0, padx=(0, 18), pady=5)
            tk.Label(
                self.panel,
                text=etiquetas[estado],
                background="#ffffff",
                anchor="w",
            ).grid(row=fila, column=1, sticky="w", padx=(0, 18), pady=5)
            tk.Label(
                self.panel,
                text=str(registros),
                background="#ffffff",
                anchor="e",
            ).grid(row=fila, column=2, sticky="e", padx=(0, 18), pady=5)
            tk.Label(
                self.panel,
                text=self.formatear_lotes(lotes),
                background="#ffffff",
                anchor="e",
            ).grid(row=fila, column=3, sticky="e", pady=5)
            fila += 1

        otros = resumen.get("OTROS", {})
        otros_registros = int(otros.get("Registros", 0) or 0)
        if otros_registros > 0:
            estados = ", ".join(str(x) for x in otros.get("Estados", [])) or "desconocidos"
            tk.Label(
                self.panel,
                text=(
                    "Aviso: " + str(otros_registros)
                    + " registros tienen estados no previstos (" + estados
                    + ") y no se importaran."
                ),
                foreground="#9c5700",
                background="#ffffff",
                justify="left",
                wraplength=610,
            ).grid(row=fila, column=0, columnspan=4, sticky="w", pady=(10, 4))
            fila += 1

        total = resumen.get("TOTAL", {})
        tk.Label(
            self.panel,
            text=(
                "Total fichero: "
                + self.formatear_lotes(total.get("Lotes", 0))
                + " lotes | "
                + str(int(total.get("Registros", 0) or 0))
                + " registros"
            ),
            font=("Segoe UI", 9, "bold"),
            background="#ffffff",
        ).grid(row=fila, column=0, columnspan=4, sticky="w", pady=(12, 2))
        fila += 1

        self.lbl_total_seleccionado = tk.Label(
            self.panel,
            text="",
            font=("Segoe UI", 10, "bold"),
            background="#ffffff",
        )
        self.lbl_total_seleccionado.grid(
            row=fila,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(2, 12),
        )
        fila += 1

        acciones_rapidas = tk.Frame(self.panel, background="#ffffff")
        acciones_rapidas.grid(row=fila, column=0, columnspan=2, sticky="w")

        tk.Button(
            acciones_rapidas,
            text="Marcar todos",
            width=14,
            command=self._marcar_todos,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            acciones_rapidas,
            text="Desmarcar todos",
            width=16,
            command=self._desmarcar_todos,
        ).pack(side="left")

        botones = tk.Frame(self.panel, background="#ffffff")
        botones.grid(row=fila, column=2, columnspan=2, sticky="e")

        tk.Button(
            botones,
            text="Cancelar",
            width=14,
            command=self.cancelar,
        ).pack(side="right", padx=(8, 0))

        self.btn_importar = tk.Button(
            botones,
            text="IMPORTAR SELECCION",
            width=20,
            bg="#d9ead3",
            command=self.confirmar,
            state="disabled",
            name="importar_seleccion",
        )
        self.btn_importar.pack(side="right")

        self.panel.grid_columnconfigure(1, weight=1)
        self._actualizar_total_seleccionado()

        try:
            self.overlay.lift()
            self.parent.update_idletasks()
            primer_chk = self.panel.nametowidget("estado_inicial")
            primer_chk.focus_set()
        except Exception:
            pass

    def _marcar_todos(self):
        for estado, variable in self.vars.items():
            if int(self.resumen.get(estado, {}).get("Registros", 0) or 0) > 0:
                variable.set(True)
        self._actualizar_total_seleccionado()

    def _desmarcar_todos(self):
        for variable in self.vars.values():
            variable.set(False)
        self._actualizar_total_seleccionado()

    def _actualizar_total_seleccionado(self):
        estados = [estado for estado, variable in self.vars.items() if variable.get()]
        lotes = sum(
            float(self.resumen.get(estado, {}).get("Lotes", 0) or 0)
            for estado in estados
        )
        registros = sum(
            int(self.resumen.get(estado, {}).get("Registros", 0) or 0)
            for estado in estados
        )

        self.lbl_total_seleccionado.configure(
            text=(
                "Seleccionado: " + self.formatear_lotes(lotes)
                + " lotes | " + str(registros) + " registros"
            )
        )
        self.btn_importar.configure(state="normal" if estados else "disabled")

    # ------------------------------------------------------------------
    # Finalizacion
    # ------------------------------------------------------------------
    def confirmar(self):
        estados = {estado for estado, variable in self.vars.items() if variable.get()}
        if not estados:
            messagebox.showwarning(
                "Sin estados seleccionados",
                "Selecciona al menos un estado para importar.",
                parent=self.parent,
            )
            return
        self.resultado = estados
        _log("Seleccion confirmada: " + ",".join(sorted(estados)))
        self.finalizado.set(True)

    def cancelar(self):
        if self.finalizado.get():
            return
        self.resultado = None
        _log("Seleccion cancelada")
        self.finalizado.set(True)

    def ejecutar(self):
        try:
            self.parent.wait_variable(self.finalizado)
        except tk.TclError:
            self.resultado = None
        finally:
            self._restaurar_modal()
            _log("Panel cerrado y grab restaurado")

        if self.root_creado:
            try:
                self.parent.destroy()
            except Exception:
                pass

        if self.error is not None:
            raise self.error

        return self.resultado


class DialogoEstadosESTAREPP:
    """Compatibilidad con el API anterior: solo muestra el selector."""

    def __init__(self, resumen, ficheros=None, parent=None):
        self.flujo = _FlujoEstadosESTAREPP(
            parent=parent,
            ficheros=ficheros,
            resumen=resumen,
            funcion_analisis=None,
            mostrar_progreso=False,
        )

    def ejecutar(self):
        return self.flujo.ejecutar()


def seleccionar_estados_estarepp(resumen, ficheros=None, parent=None):
    return DialogoEstadosESTAREPP(
        resumen,
        ficheros=ficheros,
        parent=parent,
    ).ejecutar()


def analizar_y_seleccionar_estados_estarepp(funcion, ficheros=None, parent=None):
    """Analiza y selecciona estados dentro de un unico panel modal.

    Esta es la funcion que debe usar el importador real. Evita abrir dos
    ventanas consecutivas y funciona aunque la raiz principal este retirada y
    el formulario de trabajo tenga un grab previo.
    """

    return _FlujoEstadosESTAREPP(
        parent=parent,
        ficheros=ficheros,
        funcion_analisis=funcion,
        mostrar_progreso=True,
    ).ejecutar()


def ejecutar_analisis_con_progreso(funcion, ficheros=None, parent=None):
    """Compatibilidad con versiones anteriores.

    Ejecuta el mismo flujo robusto. Devuelve el resumen si el usuario confirma
    alguna seleccion; el importador V17.9 ya no usa esta funcion por separado.
    """

    flujo = _FlujoEstadosESTAREPP(
        parent=parent,
        ficheros=ficheros,
        funcion_analisis=funcion,
        mostrar_progreso=True,
    )
    seleccion = flujo.ejecutar()
    if seleccion is None:
        return None
    return flujo.resumen
