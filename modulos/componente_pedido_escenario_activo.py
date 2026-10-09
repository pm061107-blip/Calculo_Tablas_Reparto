"""Bloque comun para reutilizar el pedido seleccionado en Calculo de cajas.

V17.24.2 mantiene el estado sincronizado incluso cuando el formulario de
reparto ya estaba abierto antes de seleccionar el escenario. Los botones no se
deshabilitan de forma permanente: al pulsarlos siempre se vuelve a consultar
SQLite y se informa con el estado real.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from modulos.gestor_pedido_escenario_activo import (
    GestorPedidoEscenarioActivo,
)


class ComponentePedidoEscenarioActivo:
    """Muestra el escenario disponible y ejecuta acciones sobre ese pedido."""

    INTERVALO_REFRESCO_MS = 1200

    def __init__(
        self,
        padre,
        conexion,
        ventana=None,
        acciones=None,
        padx=12,
        pady=5,
        wraplength=820,
        texto_marco="Pedido seleccionado en Calculo de cajas",
        compacto=False,
    ):
        self.padre = padre
        self.ventana = ventana or padre.winfo_toplevel()
        self.gestor = GestorPedidoEscenarioActivo(conexion)
        self.acciones = list(acciones or [])
        self.botones = []
        self.compacto = bool(compacto)
        self.estado = None
        self._after_refresco = None
        self._destruido = False

        self.marco = tk.LabelFrame(
            padre,
            text=texto_marco,
            font=("Arial", 10, "bold"),
            padx=8 if self.compacto else 10,
            pady=4 if self.compacto else 8,
        )
        self.marco.pack(fill="x", padx=padx, pady=pady)

        fila_botones = tk.Frame(self.marco)
        fila_botones.grid(row=0, column=0, sticky="nw", padx=(0, 14))

        for indice, accion in enumerate(self.acciones):
            if isinstance(accion, dict):
                texto = accion.get("texto", "USAR ESCENARIO ACTIVO")
                callback = accion.get("command")
                ancho = int(accion.get("width", 27) or 27)
            else:
                texto, callback = accion
                ancho = 27

            boton = tk.Button(
                fila_botones,
                text=str(texto),
                width=ancho,
                height=1 if self.compacto else 2,
                command=lambda cb=callback: self._ejecutar(cb),
            )
            texto_boton = str(texto).upper()
            if "DESCART" in texto_boton:
                boton.config(
                    bg="#f4cccc",
                    fg="#990000",
                    activebackground="#ea9999",
                    activeforeground="#660000",
                    font=("Arial", 9 if self.compacto else 10, "bold"),
                )
            elif "ESCENARIO ACTIVO" in texto_boton or "ACTIVO" in texto_boton:
                boton.config(
                    bg="#cfe2f3",
                    fg="#1c4587",
                    activebackground="#9fc5e8",
                    activeforeground="#073763",
                    font=("Arial", 9 if self.compacto else 10, "bold"),
                )
            if self.compacto:
                boton.grid(
                    row=0,
                    column=indice,
                    sticky="ew",
                    padx=(0, 5),
                    pady=0,
                )
            else:
                boton.grid(row=indice, column=0, sticky="ew", pady=(0, 4))
            self.botones.append(boton)

        self.marco_estado = tk.Frame(self.marco)
        self.marco_estado.grid(row=0, column=1, sticky="nsew")

        self.lbl_estado = tk.Label(
            self.marco_estado,
            text="",
            anchor="w",
            justify="left",
            wraplength=wraplength,
            font=("Arial", 9),
        )
        self.lbl_estado.grid(row=0, column=0, sticky="ew")

        self.lbl_estado_activo = tk.Label(
            self.marco_estado,
            text="",
            anchor="w",
            justify="left",
            wraplength=wraplength,
            font=("Arial", 9, "bold"),
            fg="#1c4587",
        )
        self.lbl_estado_descartado = tk.Label(
            self.marco_estado,
            text="",
            anchor="w",
            justify="left",
            wraplength=wraplength,
            font=("Arial", 9, "bold"),
            fg="#990000",
        )
        self.marco_estado.grid_columnconfigure(0, weight=1)
        self.marco.grid_columnconfigure(1, weight=1)

        # Refrescar al volver a la ventana resuelve el caso habitual en el que
        # esta ya estaba abierta cuando se selecciono el escenario en Cajas.
        try:
            self.ventana.bind("<FocusIn>", self._al_recuperar_foco, add="+")
        except Exception:
            pass
        try:
            self.marco.bind("<Destroy>", self._al_destruir, add="+")
        except Exception:
            pass

        self.refrescar()
        self._programar_refresco()

    def _ventana_disponible(self):
        if self._destruido:
            return False
        try:
            return int(self.marco.winfo_exists()) == 1
        except Exception:
            return False

    def _al_destruir(self, evento=None):
        try:
            if evento is not None and evento.widget is not self.marco:
                return
        except Exception:
            pass
        self._destruido = True
        if self._after_refresco is not None:
            try:
                self.marco.after_cancel(self._after_refresco)
            except Exception:
                pass
            self._after_refresco = None

    def _al_recuperar_foco(self, _evento=None):
        if self._ventana_disponible():
            try:
                self.refrescar()
            except Exception:
                pass

    def _programar_refresco(self):
        if not self._ventana_disponible():
            return
        if self._after_refresco is not None:
            try:
                self.marco.after_cancel(self._after_refresco)
            except Exception:
                pass
        try:
            self._after_refresco = self.marco.after(
                self.INTERVALO_REFRESCO_MS,
                self._refresco_periodico,
            )
        except Exception:
            self._after_refresco = None

    def _refresco_periodico(self):
        self._after_refresco = None
        if not self._ventana_disponible():
            return
        try:
            self.refrescar()
        finally:
            self._programar_refresco()

    def refrescar(self):
        try:
            self.estado = self.gestor.obtener_estado()
        except Exception as error:
            self.estado = {
                "Disponible": False,
                "Motivo": "No se pudo consultar el escenario activo: " + str(error),
            }

        disponible = bool(self.estado.get("Disponible"))

        # El boton permanece habilitado. Si el estado mostrado estaba
        # desactualizado, el clic vuelve a consultar la base antes de actuar.
        # Esto evita que una ventana abierta con anterioridad quede bloqueada.
        for boton in self.botones:
            try:
                boton.config(state="normal")
            except Exception:
                pass

        self._actualizar_estado_visual(disponible)
        return self.estado

    def _texto_linea_activo(self, estado):
        return (
            "PEDIDO SELECCIONADO: "
            + GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
            + " | seleccionado: "
            + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
            + "\nTiendas: "
            + str(estado.get("Tiendas", 0))
            + " | Tienda+Aparte: "
            + str(estado.get("Apartes", 0))
            + " | Lotes: "
            + GestorPedidoEscenarioActivo.formatear_lotes(estado.get("Lotes", 0))
            + " | Unidades: "
            + str(estado.get("Unidades", 0))
        )

    def _texto_linea_descartado(self, estado):
        return (
            "PEDIDO DESCARTADO: "
            + GestorPedidoEscenarioActivo.nombre_pedido_descartado(estado)
            + " | "
            + str(estado.get("TiendasDescartadas", 0))
            + " tiendas | "
            + str(estado.get("ApartesDescartados", 0))
            + " tienda/aparte | "
            + GestorPedidoEscenarioActivo.formatear_lotes(
                estado.get("LotesDescartados", 0)
            )
            + " lotes | "
            + str(estado.get("UnidadesDescartadas", 0))
            + " unidades"
        )

    def _actualizar_estado_visual(self, disponible):
        if not disponible:
            self.lbl_estado_activo.grid_remove()
            self.lbl_estado_descartado.grid_remove()
            self.lbl_estado.grid(row=0, column=0, sticky="ew")
            self.lbl_estado.config(
                text=GestorPedidoEscenarioActivo.texto_estado(self.estado),
                fg="#9a6500",
            )
            return

        self.lbl_estado.grid_remove()
        self.lbl_estado_activo.grid(row=0, column=0, sticky="ew")
        self.lbl_estado_descartado.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.lbl_estado_activo.config(
            text=self._texto_linea_activo(self.estado),
            fg="#1c4587",
        )
        self.lbl_estado_descartado.config(
            text=self._texto_linea_descartado(self.estado),
            fg="#990000",
        )

    def _ejecutar(self, callback):
        estado = self.refrescar()
        if not estado.get("Disponible"):
            messagebox.showwarning(
                "Sin escenario activo",
                GestorPedidoEscenarioActivo.texto_estado(estado),
                parent=self.ventana,
            )
            return None

        if callback is None:
            return estado

        resultado = callback(estado)
        self.refrescar()
        return resultado
