import tkinter as tk
from tkinter import messagebox

from modulos.formulario_reparto_base import FormularioRepartoBase


class FormularioRepartoNormal(FormularioRepartoBase):

    CLAVE_PEDIDO_TRABAJO = "REPARTO_NORMAL"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        super().__init__(
            ventana_padre,
            "Reparto Normal",
            "Calcula el reparto normal usando los dos carruseles."
        )

    #---------------------------------------------------------
    # Opciones especificas
    #---------------------------------------------------------
    def crear_opciones_especificas(self, marco):

        texto = (
            "Modelo fijo: dos carruseles | Prioridad normal | "
            "sin paises forzados."
        )

        self.lbl_modelo = tk.Label(
            marco,
            text=texto,
            font=("Arial", 10, "italic"),
            anchor="w"
        )
        self.lbl_modelo.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="w",
            padx=4,
            pady=8,
        )

    #---------------------------------------------------------
    # Calcular reparto
    #---------------------------------------------------------
    def calcular_reparto(self):

        if not self.validar_pedidos_importados():
            return

        try:
            resultado = self.ejecutar_motor_y_exportar(
                [1, 2],
                "NORMAL",
                None,
            )
            if resultado is None:
                return

            messagebox.showinfo(
                "Reparto finalizado",
                "Reparto normal calculado y archivos generados correctamente.\n\n"
                + resultado["PedidoTexto"]
                + "\nLado_corto: "
                + resultado["LadoCorto"],
                parent=self.ventana,
            )

        except Exception as error:
            messagebox.showerror(
                "Error calculando reparto",
                str(error),
                parent=self.ventana,
            )
