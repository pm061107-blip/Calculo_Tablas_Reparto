"""Bloque visual del pedido que realmente utilizara un formulario."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo


class ComponentePedidoTrabajo:
    def __init__(
        self,
        padre,
        conexion,
        clave_formulario,
        ventana=None,
        texto_marco="Pedido en uso en este formulario",
        padx=12,
        pady=5,
        wraplength=850,
        compacto=False,
    ):
        self.padre = padre
        self.ventana = ventana or padre.winfo_toplevel()
        self.clave_formulario = str(clave_formulario).strip().upper()
        self.gestor = GestorPedidosTrabajo(conexion)
        self.compacto = bool(compacto)
        self.estado = None

        self.marco = tk.LabelFrame(
            padre,
            text=texto_marco,
            font=("Arial", 10, "bold"),
            padx=8 if self.compacto else 10,
            pady=4 if self.compacto else 7,
        )
        self.marco.pack(fill="x", padx=padx, pady=pady)

        self.lbl_estado = tk.Label(
            self.marco,
            text="",
            anchor="w",
            justify="left",
            wraplength=wraplength,
            font=("Arial", 9, "bold" if self.compacto else "normal"),
        )
        self.lbl_estado.pack(fill="x")
        self.refrescar()

    def refrescar(self):
        try:
            self.estado = self.gestor.obtener_estado(self.clave_formulario)
        except Exception as error:
            self.estado = {
                "Disponible": False,
                "Motivo": "No se pudo consultar el pedido de trabajo: " + str(error),
            }
        self.lbl_estado.config(
            text=GestorPedidosTrabajo.texto_estado(self.estado),
            fg="#176b2c" if self.estado.get("Disponible") else "#9a6500",
        )
        return self.estado

    def confirmar_calculo(self, accion="calcular las tablas"):
        estado = self.refrescar()
        if not estado.get("Disponible"):
            messagebox.showwarning(
                "Sin pedido de trabajo",
                GestorPedidosTrabajo.texto_estado(estado),
                parent=self.ventana,
            )
            return False
        return bool(
            messagebox.askyesno(
                "Confirmar pedido de calculo",
                GestorPedidosTrabajo.texto_confirmacion(estado, accion),
                parent=self.ventana,
            )
        )

    def texto_resumen_final(self):
        return GestorPedidosTrabajo.texto_resumen_final(self.refrescar())
