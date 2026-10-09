import tkinter as tk
from tkinter import messagebox

from modulos.formulario_reparto_base import FormularioRepartoBase
from modulos.formulario_prioridad_paises_un_carrusel import FormularioPrioridadPaisesUnCarrusel


class FormularioRepartoUnCarrusel(FormularioRepartoBase):

    CLAVE_PEDIDO_TRABAJO = "REPARTO_UN_CARRUSEL"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.carrusel_unico = tk.IntVar(value=1)
        self.prioridad = tk.StringVar(value="NORMAL")
        self.configuracion_prioridad_paises = None
        self.lbl_prioridad_paises = None

        super().__init__(
            ventana_padre,
            "Reparto Un Carrusel",
            "Calcula el reparto usando solo CLA 1 o solo CLA 2."
        )

    #---------------------------------------------------------
    # Opciones especificas
    #---------------------------------------------------------
    def crear_opciones_especificas(self, marco):

        tk.Label(
            marco,
            text="Carrusel:",
            font=("Arial", 10)
        ).grid(row=1, column=0, sticky="w", padx=4, pady=6)

        tk.Radiobutton(
            marco,
            text="CLA 1",
            variable=self.carrusel_unico,
            value=1
        ).grid(row=1, column=1, sticky="w", padx=12, pady=6)

        tk.Radiobutton(
            marco,
            text="CLA 2",
            variable=self.carrusel_unico,
            value=2
        ).grid(row=1, column=2, sticky="w", padx=12, pady=6)

        tk.Label(
            marco,
            text="Prioridad general:",
            font=("Arial", 10)
        ).grid(row=2, column=0, sticky="w", padx=4, pady=6)

        tk.Radiobutton(
            marco,
            text="Normal",
            variable=self.prioridad,
            value="NORMAL",
            command=self.actualizar_resumen_prioridad_paises
        ).grid(row=2, column=1, sticky="w", padx=12, pady=6)

        tk.Radiobutton(
            marco,
            text="Inversa",
            variable=self.prioridad,
            value="INVERSA",
            command=self.actualizar_resumen_prioridad_paises
        ).grid(row=2, column=2, sticky="w", padx=12, pady=6)

        tk.Button(
            marco,
            text="Configurar paises Normal / Inversa",
            width=34,
            command=self.configurar_prioridad_paises
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(12, 4))

        self.lbl_prioridad_paises = tk.Label(
            marco,
            text="Paises: todos usan la prioridad general.",
            font=("Arial", 9),
            fg="#1f4e79",
            anchor="w",
            justify="left"
        )
        self.lbl_prioridad_paises.grid(row=4, column=0, columnspan=4, sticky="w", padx=4, pady=(0, 4))


    #---------------------------------------------------------
    # Hook despues de resetear
    #---------------------------------------------------------
    def despues_resetear(self):

        self.configuracion_prioridad_paises = None
        self.actualizar_resumen_prioridad_paises()

    #---------------------------------------------------------
    # Hook despues de importar pedidos
    #---------------------------------------------------------
    def despues_importar(self):

        self.configuracion_prioridad_paises = None
        self.actualizar_resumen_prioridad_paises()

    #---------------------------------------------------------
    # Configurar prioridad de paises
    #---------------------------------------------------------
    def configurar_prioridad_paises(self):

        if not self.validar_pedidos_importados():
            return

        formulario = FormularioPrioridadPaisesUnCarrusel(
            self.ventana,
            self.configuracion_prioridad_paises,
            self.prioridad.get(),
            clave_pedido_trabajo=self.clave_pedido_trabajo,
        )

        resultado = formulario.ejecutar()

        if resultado is None:
            return

        self.configuracion_prioridad_paises = resultado
        self.actualizar_resumen_prioridad_paises()

    #---------------------------------------------------------
    # Actualizar texto de resumen de paises
    #---------------------------------------------------------
    def actualizar_resumen_prioridad_paises(self):

        if self.lbl_prioridad_paises is None:
            return

        if self.configuracion_prioridad_paises is None:
            self.lbl_prioridad_paises.config(
                text="Paises: todos usan la prioridad general " + self.prioridad.get() + "."
            )
            return

        if not self.configuracion_prioridad_paises.get("Activo", False):
            self.lbl_prioridad_paises.config(
                text="Paises: todos en AUTO. Se usara la prioridad general " + self.prioridad.get() + "."
            )
            return

        normales = self.configuracion_prioridad_paises.get("PaisesNormal", [])
        inversos = self.configuracion_prioridad_paises.get("PaisesInversa", [])

        texto = (
            "Paises Normal: " + str(len(normales))
            + " | Paises Inversa: " + str(len(inversos))
            + " | Resto: prioridad general " + self.prioridad.get()
        )

        self.lbl_prioridad_paises.config(text=texto)

    #---------------------------------------------------------
    # Calcular reparto
    #---------------------------------------------------------
    def calcular_reparto(self):

        if not self.validar_pedidos_importados():
            return

        clasificador = self.carrusel_unico.get()

        if not self.validar_capacidad_un_carrusel(clasificador):
            return

        try:
            resultado = self.ejecutar_motor_y_exportar(
                [clasificador],
                self.prioridad.get(),
                None,
                self.configuracion_prioridad_paises,
            )
            if resultado is None:
                return

            messagebox.showinfo(
                "Reparto finalizado",
                "Reparto de un carrusel calculado y archivos generados correctamente.\n\n"
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
