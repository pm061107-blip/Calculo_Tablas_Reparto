import tkinter as tk
from tkinter import messagebox

from modulos.formulario_reparto_base import FormularioRepartoBase
from modulos.formulario_paises import FormularioPaisesFijos


class FormularioRepartoPaises(FormularioRepartoBase):

    CLAVE_PEDIDO_TRABAJO = "REPARTO_PAISES_FIJOS"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.configuracion_paises = None

        super().__init__(
            ventana_padre,
            "Reparto con Paises Fijos",
            "Calcula con dos carruseles forzando paises concretos a CLA 1 o CLA 2."
        )

    #---------------------------------------------------------
    # Opciones especificas
    #---------------------------------------------------------
    def crear_opciones_especificas(self, marco):

        self.boton_configurar_paises = tk.Button(
            marco,
            text="Configurar paises",
            width=20,
            command=self.configurar_paises,
            state="disabled"
        )
        self.boton_configurar_paises.grid(row=1, column=0, sticky="w", padx=4, pady=8)

        self.lbl_paises_configurados = tk.Label(
            marco,
            text="Importa pedidos antes de configurar paises.",
            font=("Arial", 9, "italic"),
            anchor="w"
        )
        self.lbl_paises_configurados.grid(row=1, column=1, columnspan=4, sticky="w", padx=12, pady=8)


    #---------------------------------------------------------
    # Hook despues de resetear
    #---------------------------------------------------------
    def despues_resetear(self):

        self.configuracion_paises = None
        try:
            self.boton_configurar_paises.config(state="disabled")
            self.lbl_paises_configurados.config(
                text="Importa pedidos antes de configurar paises."
            )
        except Exception:
            pass

    #---------------------------------------------------------
    # Despues de importar
    #---------------------------------------------------------
    def despues_importar(self):

        self.configuracion_paises = None
        self.boton_configurar_paises.config(state="normal")
        self.lbl_paises_configurados.config(text="Sin configurar")

    #---------------------------------------------------------
    # Configurar paises
    #---------------------------------------------------------
    def configurar_paises(self):

        if not self.validar_pedidos_importados():
            return

        formulario = FormularioPaisesFijos(
            self.ventana,
            clave_pedido_trabajo=self.clave_pedido_trabajo,
        )
        resultado = formulario.ejecutar()

        if resultado is None:
            self.configuracion_paises = None
            self.lbl_paises_configurados.config(text="Sin configurar")
            return

        self.configuracion_paises = resultado

        total_cla_1 = len(resultado.get("PaisesCLA1", []))
        total_cla_2 = len(resultado.get("PaisesCLA2", []))

        self.lbl_paises_configurados.config(
            text="CLA 1: " + str(total_cla_1) + " paises | CLA 2: " + str(total_cla_2) + " paises"
        )

    #---------------------------------------------------------
    # Calcular reparto
    #---------------------------------------------------------
    def calcular_reparto(self):

        if not self.validar_pedidos_importados():
            return

        if self.configuracion_paises is None:
            self.configurar_paises()

        if self.configuracion_paises is None:
            return

        try:
            resultado = self.ejecutar_motor_y_exportar(
                [1, 2],
                "NORMAL",
                self.configuracion_paises,
            )
            if resultado is None:
                return

            messagebox.showinfo(
                "Reparto finalizado",
                "Reparto con paises fijos calculado y archivos generados correctamente.\n\n"
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
