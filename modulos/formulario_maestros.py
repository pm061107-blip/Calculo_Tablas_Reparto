import tkinter as tk

from modulos.formulario_maestro_tipo_caja_pais import FormularioMaestroTipoCajaPais
from modulos.formulario_maestro_tipo_caja_tienda import FormularioMaestroTipoCajaTienda
from modulos.formulario_maestro_tipos_de_caja import FormularioMaestroTiposDeCaja
from modulos.formulario_maestro_distribucion_clasificador import FormularioMaestroDistribucionClasificador
from modulos.formulario_maestro_tiendas_xdoc import FormularioMaestroTiendasXDOC
from modulos.ventanas_tk import preparar_formulario_navegable


class FormularioMaestros:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.ventana_padre = ventana_padre
        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Maestros / Configuracion")
        self.ventana.geometry("760x650")
        self.ventana.resizable(True, True)
        self.ventana.protocol("WM_DELETE_WINDOW", self.ventana.destroy)
        self.formularios_abiertos = {}

        self.crear_controles()
        preparar_formulario_navegable(self.ventana, parent=self.ventana_padre, maximizar=True)

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = tk.Frame(self.ventana)
        contenedor.pack(fill="both", expand=True, padx=28, pady=24)

        titulo = tk.Label(
            contenedor,
            text="MAESTROS / CONFIGURACION",
            font=("Arial", 18, "bold")
        )
        titulo.pack(pady=(0, 6))

        subtitulo = tk.Label(
            contenedor,
            text="Selecciona el maestro que quieres mantener.",
            font=("Arial", 11)
        )
        subtitulo.pack(pady=(0, 20))

        panel = tk.Frame(contenedor)
        panel.pack(fill="both", expand=True)

        self.crear_boton_menu(
            panel,
            0,
            0,
            "TIPO CAJA POR PAIS",
            "Mantenimiento por pais",
            "#d9ead3",
            self.abrir_tipo_caja_pais
        )

        self.crear_boton_menu(
            panel,
            0,
            1,
            "TIPO CAJA TIENDA A MAYORES",
            "Excepciones por tienda",
            "#fff2cc",
            self.abrir_tipo_caja_tienda
        )

        self.crear_boton_menu(
            panel,
            1,
            0,
            "HOMOLOGACION TIPOS DE CAJA",
            "TiposDeCaja",
            "#d9eaf7",
            self.abrir_tipos_de_caja
        )

        self.crear_boton_menu(
            panel,
            1,
            1,
            "DISTRIBUCION CLASIFICADOR",
            "Destinos, lados y prioridades",
            "#eadcf8",
            self.abrir_distribucion_clasificador
        )

        self.crear_boton_menu(
            panel,
            2,
            0,
            "TIENDAS XDOC",
            "Tolerancia especial por tienda",
            "#d0e0e3",
            self.abrir_tiendas_xdoc
        )

        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        pie = tk.Frame(contenedor)
        pie.pack(fill="x", pady=(18, 0))

        tk.Button(
            pie,
            text="Cerrar",
            width=18,
            height=2,
            command=self.ventana.destroy
        ).pack(side="right")

    #---------------------------------------------------------
    # Crear boton de menu
    #---------------------------------------------------------
    def crear_boton_menu(self, panel, fila, columna, titulo, texto, color, comando):

        boton = tk.Button(
            panel,
            text=titulo + "\n" + texto,
            font=("Arial", 11, "bold"),
            bg=color,
            height=5,
            command=comando
        )

        boton.grid(
            row=fila,
            column=columna,
            sticky="nsew",
            padx=10,
            pady=10
        )

    #---------------------------------------------------------
    # Ejecutar formulario de mantenimiento navegable
    #---------------------------------------------------------
    def ejecutar_formulario_maestro(self, clase_formulario):

        clave = getattr(clase_formulario, "__name__", str(clase_formulario))
        existente = self.formularios_abiertos.get(clave)

        if existente is not None and hasattr(existente, "ventana"):
            try:
                if int(existente.ventana.winfo_exists()) == 1:
                    preparar_formulario_navegable(
                        existente.ventana,
                        parent=self.ventana,
                        maximizar=True,
                    )
                    return existente
            except Exception:
                self.formularios_abiertos.pop(clave, None)

        formulario = clase_formulario(self.ventana)
        self.formularios_abiertos[clave] = formulario

        if hasattr(formulario, "ventana"):
            preparar_formulario_navegable(
                formulario.ventana,
                parent=self.ventana,
                maximizar=True,
            )

            def _olvidar(evento, clave_formulario=clave, ventana=formulario.ventana):
                if evento.widget is ventana:
                    self.formularios_abiertos.pop(clave_formulario, None)

            try:
                formulario.ventana.bind("<Destroy>", _olvidar, add="+")
            except Exception:
                pass

        return formulario

    #---------------------------------------------------------
    # Abrir formularios de maestros
    #---------------------------------------------------------
    def abrir_tipo_caja_pais(self):

        self.ejecutar_formulario_maestro(FormularioMaestroTipoCajaPais)

    def abrir_tipo_caja_tienda(self):

        self.ejecutar_formulario_maestro(FormularioMaestroTipoCajaTienda)

    def abrir_tipos_de_caja(self):

        self.ejecutar_formulario_maestro(FormularioMaestroTiposDeCaja)

    def abrir_distribucion_clasificador(self):

        self.ejecutar_formulario_maestro(FormularioMaestroDistribucionClasificador)

    def abrir_tiendas_xdoc(self):

        self.ejecutar_formulario_maestro(FormularioMaestroTiendasXDOC)

    #---------------------------------------------------------
    # Ejecutar formulario
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
