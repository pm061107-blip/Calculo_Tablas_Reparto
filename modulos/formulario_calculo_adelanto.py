import tkinter as tk
from tkinter import messagebox, simpledialog
from tkinter import ttk

from bd.basedatos import BaseDatos
from modulos.importador_pedidos import ImportadorPedidos
from modulos.procesar_estarepp import ProcesarESTAREPP
from modulos.exportar_tabla_reparto_csv import exportar_tablas_reparto_csv
from modulos.exportar_grtdaswp_adelanto import exportar_grtdaswp_adelanto
from modulos.componente_grutiep import ComponenteGRUTIEP
from modulos.componente_pedido_escenario_activo import (
    ComponentePedidoEscenarioActivo,
)
from modulos.gestor_pedido_escenario_activo import (
    GestorPedidoEscenarioActivo,
)
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo
from modulos.componente_pedido_trabajo import ComponentePedidoTrabajo
from modulos.ventanas_tk import crear_marco_scrollable
from modulos.dialogo_progreso import DialogoProgreso
from modulos.repeticion_tiendas import expandir_filas, pedir_repeticiones
from modulos.gestor_reset_calculos import GestorResetCalculos


class FormularioCalculoAdelanto:

    CLAVE_SUBPEDIDO = "ADELANTO_SUBPEDIDO"
    CLAVE_PEDIDO_COMPLETO = "ADELANTO_PEDIDO_COMPLETO"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.bd = BaseDatos()
        self.ventana_padre = ventana_padre
        self.gestor_pedidos_trabajo = GestorPedidosTrabajo(self.bd.conexion)
        self.ultimo_importador_actual = None

        self.opciones_subpedido = []
        self.opciones_resto = []
        self.opcion_subpedido = None
        self.opcion_resto = None
        self.registros_subpedido = []
        self.registros_resto = []

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Calculo Adelanto")
        self.ventana.geometry("1180x980")
        self.ventana.minsize(1080, 820)
        self.ventana.resizable(True, True)

        self.crear_tablas_adelanto()
        self.crear_controles()

    #---------------------------------------------------------
    # Crear tablas temporales de adelanto
    #---------------------------------------------------------
    def crear_tablas_adelanto(self):

        tablas = [
            "ADELANTO_PEDIDO_1",
            "ADELANTO_PEDIDO_2",
            "ADELANTO_RESTO",
            "ADELANTO_SELECCION"
        ]

        for tabla in tablas:

            self.bd.ejecutar(
                "CREATE TABLE IF NOT EXISTS " + tabla + " ("
                "Tienda INTEGER, "
                "Aparte INTEGER, "
                "Lotes REAL, "
                "Pais TEXT, "
                "TipoCaja TEXT, "
                "Fase TEXT, "
                "Clasificador INTEGER"
                ")"
            )

    #---------------------------------------------------------
    # Vaciar tablas de adelanto
    #---------------------------------------------------------
    def vaciar_tablas_adelanto(self):

        for tabla in [
            "ADELANTO_PEDIDO_1",
            "ADELANTO_PEDIDO_2",
            "ADELANTO_RESTO",
            "ADELANTO_SELECCION"
        ]:
            self.bd.ejecutar("DELETE FROM " + tabla)

        self.gestor_pedidos_trabajo.limpiar(self.CLAVE_SUBPEDIDO)
        self.gestor_pedidos_trabajo.limpiar(self.CLAVE_PEDIDO_COMPLETO)
        if hasattr(self, "pedido_trabajo_subpedido"):
            self.pedido_trabajo_subpedido.refrescar()
        if hasattr(self, "pedido_trabajo_completo"):
            self.pedido_trabajo_completo.refrescar()

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = crear_marco_scrollable(self.ventana, padx=0, pady=0)
        self.contenedor_principal = contenedor

        titulo = tk.Label(
            contenedor,
            text="CALCULO ADELANTO",
            font=("Arial", 18, "bold")
        )
        titulo.pack(pady=(10, 4))

        subtitulo = tk.Label(
            contenedor,
            text="Selecciona las tiendas con mas lotes sin romper tienda. Si una tienda tiene varios apartes, entran todos o no entra ninguno.",
            font=("Arial", 10)
        )
        subtitulo.pack(pady=(0, 8))

        self.crear_boton_reset(contenedor)
        self.crear_bloque_resumen(contenedor)
        # V2.3: el bloque "Pedido seleccionado en Calculo de cajas" (escenario
        # activo / tiendas descartadas) ya no se muestra en Adelanto porque
        # aqui nunca se utiliza. Los subpedidos se importan desde fichero.
        self.grutiep = ComponenteGRUTIEP(
            contenedor,
            ventana=self.ventana,
            padx=12,
            pady=4,
            wraplength=900,
        )
        self.crear_bloque_subpedido(contenedor)
        self.crear_bloque_resto(contenedor)
        self.crear_bloque_acciones(contenedor)

    #---------------------------------------------------------
    # Boton de reset
    #---------------------------------------------------------
    def crear_boton_reset(self, contenedor=None):

        contenedor = contenedor or getattr(self, "contenedor_principal", self.ventana)
        tk.Button(
            contenedor,
            text="RESETEAR ADELANTO / LIMPIAR PEDIDOS Y CALCULOS",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_formulario,
        ).pack(fill="x", padx=12, pady=(6, 4))

    #---------------------------------------------------------
    # Resetear formulario
    #---------------------------------------------------------
    def resetear_formulario(self):

        if not messagebox.askyesno(
            "Resetear Calculo Adelanto",
            "Se limpiaran subpedido, pedido completo, opciones calculadas y exportaciones pendientes.\n\n"
            "No se borraran maestros, GRUTIEP, Tiendas_Web ni volumetria de cajas.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return

        try:
            GestorResetCalculos(self.bd.conexion).resetear_adelanto(
                [self.CLAVE_SUBPEDIDO, self.CLAVE_PEDIDO_COMPLETO]
            )
            self.opciones_subpedido = []
            self.opciones_resto = []
            self.opcion_subpedido = None
            self.opcion_resto = None
            self.registros_subpedido = []
            self.registros_resto = []
            self.limpiar_tabla(self.tabla_subpedido)
            self.limpiar_tabla(self.tabla_resto)
            self.lbl_subpedido.config(text="Subpedido: pendiente")
            self.lbl_resto.config(text="Pedido completo: pendiente")
            self.pedido_trabajo_subpedido.refrescar()
            self.pedido_trabajo_completo.refrescar()
            self.actualizar_resumen()
            messagebox.showinfo(
                "Reset finalizado",
                "Formulario reseteado correctamente.",
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error reseteando formulario",
                str(error),
                parent=self.ventana,
            )

    #---------------------------------------------------------
    # Crear bloque resumen
    #---------------------------------------------------------
    def crear_bloque_resumen(self, contenedor=None):

        contenedor = contenedor or getattr(self, "contenedor_principal", self.ventana)
        marco = tk.LabelFrame(
            contenedor,
            text="Resumen operativo",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="x", padx=12, pady=6)

        self.lbl_resumen = tk.Label(
            marco,
            text="Pendiente de importar subpedido.",
            anchor="w",
            justify="left",
            font=("Arial", 10)
        )
        self.lbl_resumen.pack(fill="x")

    #---------------------------------------------------------
    # Crear bloque subpedido
    #---------------------------------------------------------
    def crear_bloque_subpedido(self, contenedor=None):

        contenedor = contenedor or getattr(self, "contenedor_principal", self.ventana)
        marco = tk.LabelFrame(
            contenedor,
            text="1. Subpedido / adelanto - NO EVACUAR",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="both", expand=True, padx=12, pady=6)

        botones = tk.Frame(marco)
        botones.pack(fill="x", pady=(0, 6))

        tk.Button(
            botones,
            text="Importar subpedido",
            width=20,
            command=self.importar_subpedido
        ).pack(side="left", padx=4)

        tk.Button(
            botones,
            text="Usar opcion seleccionada",
            width=24,
            command=self.usar_opcion_subpedido
        ).pack(side="left", padx=4)

        self.lbl_subpedido = tk.Label(
            botones,
            text="Sin importar",
            font=("Arial", 9, "italic")
        )
        self.lbl_subpedido.pack(side="left", padx=16)

        self.pedido_trabajo_subpedido = ComponentePedidoTrabajo(
            marco,
            conexion=self.bd.conexion,
            clave_formulario=self.CLAVE_SUBPEDIDO,
            ventana=self.ventana,
            texto_marco="Pedido en uso como SUBPEDIDO / NO EVACUAR",
            padx=0,
            pady=4,
            wraplength=1080,
            compacto=True,
        )

        self.tabla_subpedido = self.crear_tabla_opciones(marco)

    #---------------------------------------------------------
    # Crear bloque resto
    #---------------------------------------------------------
    def crear_bloque_resto(self, contenedor=None):

        contenedor = contenedor or getattr(self, "contenedor_principal", self.ventana)
        marco = tk.LabelFrame(
            contenedor,
            text="2. Pedido completo menos adelanto - EVACUAR",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="both", expand=True, padx=12, pady=6)

        botones = tk.Frame(marco)
        botones.pack(fill="x", pady=(0, 6))

        tk.Button(
            botones,
            text="Importar pedido completo",
            width=24,
            command=self.importar_pedido_completo
        ).pack(side="left", padx=4)

        tk.Button(
            botones,
            text="Usar opcion seleccionada",
            width=24,
            command=self.usar_opcion_resto
        ).pack(side="left", padx=4)

        self.lbl_resto = tk.Label(
            botones,
            text="Primero selecciona el adelanto",
            font=("Arial", 9, "italic")
        )
        self.lbl_resto.pack(side="left", padx=16)

        self.pedido_trabajo_completo = ComponentePedidoTrabajo(
            marco,
            conexion=self.bd.conexion,
            clave_formulario=self.CLAVE_PEDIDO_COMPLETO,
            ventana=self.ventana,
            texto_marco="Pedido en uso como PEDIDO COMPLETO / EVACUAR",
            padx=0,
            pady=4,
            wraplength=1080,
            compacto=True,
        )

        self.tabla_resto = self.crear_tabla_opciones(marco)

    #---------------------------------------------------------
    # Crear tabla de opciones
    #---------------------------------------------------------
    def crear_tabla_opciones(self, marco):

        columnas = (
            "Id",
            "CLA",
            "Opcion",
            "Capacidad",
            "Tiendas",
            "Apartes",
            "Lotes",
            "FueraTiendas",
            "FueraApartes",
            "FueraLotes"
        )

        tabla = ttk.Treeview(
            marco,
            columns=columnas,
            show="headings",
            height=6
        )

        anchuras = {
            "Id": 45,
            "CLA": 55,
            "Opcion": 260,
            "Capacidad": 80,
            "Tiendas": 75,
            "Apartes": 75,
            "Lotes": 90,
            "FueraTiendas": 95,
            "FueraApartes": 95,
            "FueraLotes": 95
        }

        textos = {
            "Id": "Id",
            "CLA": "CLA",
            "Opcion": "Opcion",
            "Capacidad": "Cap.",
            "Tiendas": "Tiendas",
            "Apartes": "Apartes",
            "Lotes": "Lotes",
            "FueraTiendas": "T. fuera",
            "FueraApartes": "A. fuera",
            "FueraLotes": "L. fuera"
        }

        for columna in columnas:
            tabla.heading(columna, text=textos[columna])
            tabla.column(columna, width=anchuras[columna], anchor="center")

        tabla.column("Opcion", anchor="w")
        tabla.pack(fill="both", expand=True)

        return tabla

    #---------------------------------------------------------
    # Crear bloque acciones
    #---------------------------------------------------------
    def crear_bloque_acciones(self, contenedor=None):

        contenedor = contenedor or self.ventana
        marco = tk.Frame(contenedor)
        marco.pack(fill="x", padx=12, pady=10)

        tk.Button(
            marco,
            text="GENERAR TABLAS Y EXPORTAR",
            width=28,
            height=2,
            bg="#d9ead3",
            command=self.generar_tablas_exportar
        ).pack(side="left", padx=4)

        tk.Button(
            marco,
            text="Cerrar",
            width=16,
            height=2,
            command=self.ventana.destroy
        ).pack(side="right", padx=4)

    #---------------------------------------------------------
    # Importar subpedido
    #---------------------------------------------------------
    def importar_subpedido(self):

        try:
            self.vaciar_tablas_adelanto()
            self.opcion_subpedido = None
            self.opcion_resto = None
            self.registros_subpedido = []
            self.registros_resto = []
            self.limpiar_tabla(self.tabla_subpedido)
            self.limpiar_tabla(self.tabla_resto)

            tipo = self.importar_y_procesar_actual()

            if tipo is None:
                return

            self.guardar_pedido_trabajo_importado(
                self.CLAVE_SUBPEDIDO,
                tipo,
            )
            self.pedido_trabajo_subpedido.refrescar()
            if not self.copiar_tmp_a_tabla("ADELANTO_PEDIDO_1", "SUBPEDIDO", None):
                return
            self.opciones_subpedido = self.calcular_opciones("ADELANTO_PEDIDO_1", "SUBPEDIDO")
            self.mostrar_opciones(self.tabla_subpedido, self.opciones_subpedido)

            resumen = self.obtener_resumen_tabla("ADELANTO_PEDIDO_1")
            self.lbl_subpedido.config(
                text="Importado: " + str(resumen["Tiendas"]) + " tiendas | "
                + str(resumen["Apartes"]) + " apartes | "
                + str(round(resumen["Lotes"], 2)) + " lotes"
            )
            self.lbl_resto.config(text="Selecciona una opcion de adelanto y despues importa el pedido completo")
            self.actualizar_resumen()

        except Exception as error:
            messagebox.showerror("Error importando subpedido", str(error), parent=self.ventana)

    #---------------------------------------------------------
    # Importar pedido completo
    #---------------------------------------------------------
    def importar_pedido_completo(self):

        if self.opcion_subpedido is None:
            messagebox.showwarning(
                "Sin adelanto seleccionado",
                "Primero debes seleccionar una opcion del subpedido.",
                parent=self.ventana
            )
            return

        try:
            self.limpiar_tabla(self.tabla_resto)
            self.opcion_resto = None
            self.registros_resto = []

            tipo = self.importar_y_procesar_actual()

            if tipo is None:
                return

            self.guardar_pedido_trabajo_importado(
                self.CLAVE_PEDIDO_COMPLETO,
                tipo,
            )
            self.pedido_trabajo_completo.refrescar()
            self.bd.ejecutar("DELETE FROM ADELANTO_PEDIDO_2")
            self.bd.ejecutar("DELETE FROM ADELANTO_RESTO")

            if not self.copiar_tmp_a_tabla("ADELANTO_PEDIDO_2", "PEDIDO_COMPLETO", None):
                return
            self.crear_resto_sin_adelanto()

            self.opciones_resto = self.calcular_opciones("ADELANTO_RESTO", "RESTO")
            self.mostrar_opciones(self.tabla_resto, self.opciones_resto)

            resumen_total = self.obtener_resumen_tabla("ADELANTO_PEDIDO_2")
            resumen_resto = self.obtener_resumen_tabla("ADELANTO_RESTO")

            self.lbl_resto.config(
                text="Pedido completo: " + str(resumen_total["Apartes"]) + " apartes | Resto: "
                + str(resumen_resto["Apartes"]) + " apartes | "
                + str(round(resumen_resto["Lotes"], 2)) + " lotes"
            )
            self.actualizar_resumen()

        except Exception as error:
            messagebox.showerror("Error importando pedido completo", str(error), parent=self.ventana)

    #---------------------------------------------------------
    # Procesar el pedido persistente del escenario activo
    #---------------------------------------------------------
    def procesar_pedido_escenario(self, estado, tabla_origen):

        if not estado or not estado.get("Disponible"):
            raise RuntimeError(
                GestorPedidoEscenarioActivo.texto_estado(estado)
            )

        ProcesarESTAREPP(
            tabla_origen=tabla_origen,
            bd=self.bd,
        ).procesar()
        return estado

    #---------------------------------------------------------
    # Procesar el pedido persistente del escenario activo
    #---------------------------------------------------------
    def procesar_escenario_activo(self, estado=None):

        estado = estado or self.pedido_escenario.refrescar()
        return self.procesar_pedido_escenario(
            estado,
            GestorPedidoEscenarioActivo.TABLA_PEDIDO,
        )

    #---------------------------------------------------------
    # Procesar el pedido descartado del escenario activo
    #---------------------------------------------------------
    def procesar_escenario_descartado(self, estado=None):

        estado = estado or self.pedido_escenario.gestor.obtener_estado_descartado()
        if not estado or not estado.get("Disponible"):
            raise RuntimeError(
                GestorPedidoEscenarioActivo.texto_estado_descartado(estado)
            )
        return self.procesar_pedido_escenario(
            estado,
            GestorPedidoEscenarioActivo.TABLA_DESCARTADO,
        )

    #---------------------------------------------------------
    # Usar escenario activo como subpedido / NO EVACUAR
    #---------------------------------------------------------
    def usar_escenario_como_subpedido(self, estado=None):

        try:
            self.vaciar_tablas_adelanto()
            self.opcion_subpedido = None
            self.opcion_resto = None
            self.registros_subpedido = []
            self.registros_resto = []
            self.limpiar_tabla(self.tabla_subpedido)
            self.limpiar_tabla(self.tabla_resto)

            estado = self.procesar_escenario_activo(estado)
            self.guardar_pedido_trabajo_escenario(
                self.CLAVE_SUBPEDIDO,
                estado,
            )
            self.pedido_trabajo_subpedido.refrescar()
            if not self.copiar_tmp_a_tabla("ADELANTO_PEDIDO_1", "SUBPEDIDO", None):
                return
            self.opciones_subpedido = self.calcular_opciones(
                "ADELANTO_PEDIDO_1", "SUBPEDIDO"
            )
            self.mostrar_opciones(self.tabla_subpedido, self.opciones_subpedido)

            resumen = self.obtener_resumen_tabla("ADELANTO_PEDIDO_1")
            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
            self.lbl_subpedido.config(
                text=(
                    nombre_origen
                    + ": "
                    + str(resumen["Tiendas"])
                    + " tiendas | "
                    + str(resumen["Apartes"])
                    + " apartes | "
                    + str(round(resumen["Lotes"], 2))
                    + " lotes"
                )
            )
            self.lbl_resto.config(
                text="Selecciona una opcion de adelanto y despues carga el pedido completo"
            )
            self.actualizar_resumen()

            messagebox.showinfo(
                "Escenario cargado como subpedido",
                GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
                + " se ha preparado como SUBPEDIDO / NO EVACUAR.\n\n"
                + GestorPedidoEscenarioActivo.texto_estado(estado),
                parent=self.ventana,
            )
            return True

        except Exception as error:
            messagebox.showerror(
                "Error usando el escenario como subpedido",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Usar tiendas descartadas como subpedido / NO EVACUAR
    #---------------------------------------------------------
    def usar_descartadas_como_subpedido(self, _estado=None):

        try:
            self.vaciar_tablas_adelanto()
            self.opcion_subpedido = None
            self.opcion_resto = None
            self.registros_subpedido = []
            self.registros_resto = []
            self.limpiar_tabla(self.tabla_subpedido)
            self.limpiar_tabla(self.tabla_resto)

            estado = self.procesar_escenario_descartado(None)
            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_descartado(estado)
            self.guardar_pedido_trabajo_escenario(
                self.CLAVE_SUBPEDIDO,
                estado,
                tabla_origen=GestorPedidoEscenarioActivo.TABLA_DESCARTADO,
                tipo_origen="ESCENARIO_DESCARTADO",
                nombre_origen=nombre_origen,
                detalle_origen=(
                    "Pedido completo de tiendas descartadas del escenario "
                    "seleccionado en Calculo de cajas el "
                    + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
                ),
            )
            self.pedido_trabajo_subpedido.refrescar()
            if not self.copiar_tmp_a_tabla("ADELANTO_PEDIDO_1", "SUBPEDIDO", None):
                return
            self.opciones_subpedido = self.calcular_opciones(
                "ADELANTO_PEDIDO_1", "SUBPEDIDO"
            )
            self.mostrar_opciones(self.tabla_subpedido, self.opciones_subpedido)

            resumen = self.obtener_resumen_tabla("ADELANTO_PEDIDO_1")
            self.lbl_subpedido.config(
                text=(
                    nombre_origen
                    + ": "
                    + str(resumen["Tiendas"])
                    + " tiendas | "
                    + str(resumen["Apartes"])
                    + " apartes | "
                    + str(round(resumen["Lotes"], 2))
                    + " lotes"
                )
            )
            self.lbl_resto.config(
                text="Selecciona una opcion de adelanto y despues carga el pedido completo"
            )
            self.actualizar_resumen()

            messagebox.showinfo(
                "Tiendas descartadas cargadas como subpedido",
                nombre_origen
                + " se ha preparado como SUBPEDIDO / NO EVACUAR.\n\n"
                + GestorPedidoEscenarioActivo.texto_estado_descartado(estado),
                parent=self.ventana,
            )
            return True

        except Exception as error:
            messagebox.showerror(
                "Error usando tiendas descartadas como subpedido",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Usar escenario activo como pedido completo / EVACUAR
    #---------------------------------------------------------
    def usar_escenario_como_pedido_completo(self, estado=None):

        if self.opcion_subpedido is None:
            messagebox.showwarning(
                "Sin adelanto seleccionado",
                "Primero debes importar o cargar el subpedido y seleccionar una opcion.",
                parent=self.ventana,
            )
            return False

        try:
            self.limpiar_tabla(self.tabla_resto)
            self.opcion_resto = None
            self.registros_resto = []

            estado = self.procesar_escenario_activo(estado)
            self.guardar_pedido_trabajo_escenario(
                self.CLAVE_PEDIDO_COMPLETO,
                estado,
            )
            self.pedido_trabajo_completo.refrescar()
            self.bd.ejecutar("DELETE FROM ADELANTO_PEDIDO_2")
            self.bd.ejecutar("DELETE FROM ADELANTO_RESTO")
            if not self.copiar_tmp_a_tabla(
                "ADELANTO_PEDIDO_2", "PEDIDO_COMPLETO", None
            ):
                return
            self.crear_resto_sin_adelanto()

            self.opciones_resto = self.calcular_opciones(
                "ADELANTO_RESTO", "RESTO"
            )
            self.mostrar_opciones(self.tabla_resto, self.opciones_resto)

            resumen_total = self.obtener_resumen_tabla("ADELANTO_PEDIDO_2")
            resumen_resto = self.obtener_resumen_tabla("ADELANTO_RESTO")
            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
            self.lbl_resto.config(
                text=(
                    nombre_origen
                    + " como pedido completo: "
                    + str(resumen_total["Apartes"])
                    + " apartes | Resto: "
                    + str(resumen_resto["Apartes"])
                    + " apartes | "
                    + str(round(resumen_resto["Lotes"], 2))
                    + " lotes"
                )
            )
            self.actualizar_resumen()

            messagebox.showinfo(
                "Escenario cargado como pedido completo",
                GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
                + " se ha preparado como PEDIDO COMPLETO / EVACUAR.\n\n"
                + GestorPedidoEscenarioActivo.texto_estado(estado),
                parent=self.ventana,
            )
            return True

        except Exception as error:
            messagebox.showerror(
                "Error usando el escenario como pedido completo",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Usar tiendas descartadas como pedido completo / EVACUAR
    #---------------------------------------------------------
    def usar_descartadas_como_pedido_completo(self, _estado=None):

        if self.opcion_subpedido is None:
            messagebox.showwarning(
                "Sin adelanto seleccionado",
                "Primero debes importar o cargar el subpedido y seleccionar una opcion.",
                parent=self.ventana,
            )
            return False

        try:
            self.limpiar_tabla(self.tabla_resto)
            self.opcion_resto = None
            self.registros_resto = []

            estado = self.procesar_escenario_descartado(None)
            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_descartado(estado)
            self.guardar_pedido_trabajo_escenario(
                self.CLAVE_PEDIDO_COMPLETO,
                estado,
                tabla_origen=GestorPedidoEscenarioActivo.TABLA_DESCARTADO,
                tipo_origen="ESCENARIO_DESCARTADO",
                nombre_origen=nombre_origen,
                detalle_origen=(
                    "Pedido completo de tiendas descartadas del escenario "
                    "seleccionado en Calculo de cajas el "
                    + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
                ),
            )
            self.pedido_trabajo_completo.refrescar()
            self.bd.ejecutar("DELETE FROM ADELANTO_PEDIDO_2")
            self.bd.ejecutar("DELETE FROM ADELANTO_RESTO")
            if not self.copiar_tmp_a_tabla("ADELANTO_PEDIDO_2", "PEDIDO_COMPLETO", None):
                return
            self.crear_resto_sin_adelanto()

            self.opciones_resto = self.calcular_opciones("ADELANTO_RESTO", "RESTO")
            self.mostrar_opciones(self.tabla_resto, self.opciones_resto)

            resumen_total = self.obtener_resumen_tabla("ADELANTO_PEDIDO_2")
            resumen_resto = self.obtener_resumen_tabla("ADELANTO_RESTO")
            self.lbl_resto.config(
                text=(
                    nombre_origen
                    + " como pedido completo: "
                    + str(resumen_total["Apartes"])
                    + " apartes | Resto: "
                    + str(resumen_resto["Apartes"])
                    + " apartes | "
                    + str(round(resumen_resto["Lotes"], 2))
                    + " lotes"
                )
            )
            self.actualizar_resumen()

            messagebox.showinfo(
                "Tiendas descartadas cargadas como pedido completo",
                nombre_origen
                + " se ha preparado como PEDIDO COMPLETO / EVACUAR.\n\n"
                + GestorPedidoEscenarioActivo.texto_estado_descartado(estado),
                parent=self.ventana,
            )
            return True

        except Exception as error:
            messagebox.showerror(
                "Error usando tiendas descartadas como pedido completo",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Importar y procesar pedido actual
    #---------------------------------------------------------
    def importar_y_procesar_actual(self):

        importador = ImportadorPedidos(parent=self.ventana)
        tipo = importador.importar()
        self.ultimo_importador_actual = importador

        if tipo is None:
            messagebox.showwarning(
                "Importacion cancelada",
                "No se ha importado ningun fichero.",
                parent=self.ventana
            )
            return None

        procesador = ProcesarESTAREPP(bd=self.bd)
        procesador.procesar()

        return tipo

    #---------------------------------------------------------
    # Guardar pedidos independientes de las dos fases
    #---------------------------------------------------------
    def guardar_pedido_trabajo_importado(self, clave, tipo):

        importador = self.ultimo_importador_actual
        nombre_archivo = (
            importador.ruta.name
            if importador is not None and getattr(importador, "ruta", None) is not None
            else str(tipo)
        )
        return self.gestor_pedidos_trabajo.guardar_desde_tmp(
            clave,
            tipo_origen="IMPORTACION_MANUAL",
            nombre_origen=nombre_archivo,
            tabla_origen="ESTAREPP",
            detalle_origen="Tipo detectado: " + str(tipo),
        )

    def guardar_pedido_trabajo_escenario(
        self,
        clave,
        estado,
        tabla_origen=None,
        tipo_origen="ESCENARIO_ACTIVO",
        nombre_origen=None,
        detalle_origen=None,
    ):

        tabla_origen = tabla_origen or GestorPedidoEscenarioActivo.TABLA_PEDIDO
        if nombre_origen is None:
            if tabla_origen == GestorPedidoEscenarioActivo.TABLA_DESCARTADO:
                nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_descartado(estado)
            else:
                nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
        if detalle_origen is None:
            detalle_origen = (
                "Escenario seleccionado en Calculo de cajas el "
                + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
            )

        return self.gestor_pedidos_trabajo.guardar_desde_tmp(
            clave,
            tipo_origen=tipo_origen,
            nombre_origen=nombre_origen,
            tabla_origen=tabla_origen,
            detalle_origen=detalle_origen,
            estado_origen=estado,
        )

    def confirmar_pedidos_de_calculo(self):

        estado_sub = self.gestor_pedidos_trabajo.obtener_estado(
            self.CLAVE_SUBPEDIDO
        )
        estado_completo = self.gestor_pedidos_trabajo.obtener_estado(
            self.CLAVE_PEDIDO_COMPLETO
        )
        if not estado_sub.get("Disponible") or not estado_completo.get("Disponible"):
            messagebox.showwarning(
                "Pedidos de trabajo incompletos",
                "No estan disponibles los dos pedidos de trabajo.\n\nSUBPEDIDO:\n"
                + GestorPedidosTrabajo.texto_estado(estado_sub)
                + "\n\nPEDIDO COMPLETO:\n"
                + GestorPedidosTrabajo.texto_estado(estado_completo),
                parent=self.ventana,
            )
            return False

        return bool(messagebox.askyesno(
            "Confirmar pedidos de Calculo Adelanto",
            "Se van a generar las tablas con estos pedidos:\n\nSUBPEDIDO / NO EVACUAR\n"
            + GestorPedidosTrabajo.texto_estado(estado_sub)
            + "\n\nPEDIDO COMPLETO / EVACUAR\n"
            + GestorPedidosTrabajo.texto_estado(estado_completo)
            + "\n\nEn Calculo Adelanto no se solicita Lado_corto.\n\n¿Continuar?",
            parent=self.ventana,
        ))

    #---------------------------------------------------------
    # Copiar TMP_ESTAREPP a tabla de adelanto
    #---------------------------------------------------------
    def copiar_tmp_a_tabla(self, tabla, fase, clasificador):

        registros = self.bd.consultar("""
            SELECT Tienda, Aparte, Lotes, Pais, TipoCaja
            FROM TMP_ESTAREPP
        """)

        # V2.5: Tienda+Aparte que superan el umbral de lotes. Las copias son
        # filas de la misma tienda, asi que la opcion elegida las lleva todas
        # juntas al mismo CLA.
        if fase == "PEDIDO_COMPLETO":
            # Solo cuentan las tiendas que quedaran en el resto.
            tiendas_adelanto = {r[0] for r in self.registros_subpedido if r}
            candidatas = [r for r in registros if r[0] not in tiendas_adelanto]
            contexto = "Adelanto - pedido completo (solo tiendas del resto)"
        else:
            candidatas = list(registros)
            contexto = "Adelanto - subpedido"
        repeticiones = pedir_repeticiones(
            self.ventana, self.bd.conexion, candidatas, contexto=contexto
        )
        if repeticiones is None:
            messagebox.showinfo(
                "Importacion cancelada",
                "No se ha cargado el pedido. Vuelve a importarlo cuando quieras.",
                parent=self.ventana,
            )
            return False
        registros = expandir_filas(registros, repeticiones)

        self.bd.ejecutar("DELETE FROM " + tabla)

        for tienda, aparte, lotes, pais, tipo_caja in registros:
            self.bd.insertar(
                tabla,
                (tienda, aparte, lotes, pais, tipo_caja, fase, clasificador)
            )

        self.bd.guardar()
        return True

    #---------------------------------------------------------
    # Crear resto quitando COMPLETAMENTE las tiendas del adelanto
    #---------------------------------------------------------
    def crear_resto_sin_adelanto(self):

        self.bd.ejecutar("DELETE FROM ADELANTO_RESTO")

        # Regla critica del calculo Adelanto:
        # una tienda pertenece al subpedido O al pedido/resto, nunca a ambos.
        # Por eso la exclusion se hace SOLO por Tienda y no por Tienda+Aparte.
        tiendas_adelanto = {
            registro[0]
            for registro in self.registros_subpedido
            if registro is not None and len(registro) > 0
        }

        registros = self.bd.consultar("""
            SELECT Tienda, Aparte, Lotes, Pais, TipoCaja
            FROM ADELANTO_PEDIDO_2
        """)

        for tienda, aparte, lotes, pais, tipo_caja in registros:

            if tienda in tiendas_adelanto:
                continue

            self.bd.insertar(
                "ADELANTO_RESTO",
                (tienda, aparte, lotes, pais, tipo_caja, "RESTO", None)
            )

        self.bd.guardar()

        # Comprobacion obligatoria. Si alguna tienda apareciera en ambos
        # conjuntos, se detiene el proceso porque seria un error de calculo.
        self.validar_sin_solape_tiendas(
            self.registros_subpedido,
            self.bd.consultar("""
                SELECT Tienda, Aparte, Lotes, Pais, TipoCaja
                FROM ADELANTO_RESTO
            """),
            "subpedido y pedido/resto"
        )

    #---------------------------------------------------------
    # Obtener conjunto de tiendas de unos registros
    #---------------------------------------------------------
    def obtener_tiendas_registros(self, registros):

        return {
            registro[0]
            for registro in (registros or [])
            if registro is not None and len(registro) > 0 and registro[0] is not None
        }

    #---------------------------------------------------------
    # Validar que dos conjuntos de registros no compartan tienda
    #---------------------------------------------------------
    def validar_sin_solape_tiendas(self, registros_a, registros_b, contexto):

        tiendas_a = self.obtener_tiendas_registros(registros_a)
        tiendas_b = self.obtener_tiendas_registros(registros_b)
        solape = tiendas_a.intersection(tiendas_b)

        if solape:
            tiendas = ", ".join(str(tienda) for tienda in sorted(solape))
            raise Exception(
                "ERROR CRITICO: existen tiendas repetidas entre "
                + str(contexto)
                + ". Tiendas: "
                + tiendas
                + ". El calculo se ha detenido para evitar generar tablas incorrectas."
            )

        return True

    #---------------------------------------------------------
    # Recalcular el resto si cambia la opcion de adelanto
    #---------------------------------------------------------
    def recalcular_resto_por_cambio_adelanto(self):

        if self.bd.contar_registros("ADELANTO_PEDIDO_2") <= 0:
            return

        # Toda seleccion anterior del resto deja de ser valida porque el
        # conjunto de tiendas excluidas ha cambiado.
        self.opcion_resto = None
        self.registros_resto = []
        self.bd.ejecutar("DELETE FROM ADELANTO_SELECCION WHERE Fase = 'RESTO'")

        self.crear_resto_sin_adelanto()
        self.opciones_resto = self.calcular_opciones("ADELANTO_RESTO", "RESTO")
        self.mostrar_opciones(self.tabla_resto, self.opciones_resto)

        resumen_resto = self.obtener_resumen_tabla("ADELANTO_RESTO")
        self.lbl_resto.config(
            text="Adelanto cambiado: resto recalculado | "
            + str(resumen_resto["Tiendas"]) + " tiendas | "
            + str(resumen_resto["Apartes"]) + " apartes | "
            + str(round(resumen_resto["Lotes"], 2)) + " lotes | selecciona de nuevo una opcion"
        )

    #---------------------------------------------------------
    # Calcular opciones para una tabla
    #---------------------------------------------------------
    def calcular_opciones(self, tabla, fase):

        opciones = []
        numero = 1

        for clasificador in [1, 2]:

            opciones_capacidad = self.obtener_opciones_capacidad_cla(clasificador)

            for opcion_base in opciones_capacidad:

                seleccion = self.seleccionar_mejores_tiendas(tabla, opcion_base["Capacidad"])

                opcion = {
                    "Id": numero,
                    "Fase": fase,
                    "Clasificador": clasificador,
                    "Nombre": opcion_base["Nombre"],
                    "NombreBase": opcion_base["Nombre"],
                    "CapacidadMaxima": opcion_base["Capacidad"],
                    "DestinosMax": None,
                    "Tipo": opcion_base["Tipo"],
                    "LadoCorto": opcion_base.get("LadoCorto"),
                    "Capacidad": opcion_base["Capacidad"],
                    "Registros": seleccion["Registros"],
                    "Tiendas": seleccion["Tiendas"],
                    "Apartes": seleccion["Apartes"],
                    "Lotes": seleccion["Lotes"],
                    "FueraTiendas": seleccion["FueraTiendas"],
                    "FueraApartes": seleccion["FueraApartes"],
                    "FueraLotes": seleccion["FueraLotes"]
                }

                opciones.append(opcion)
                numero += 1

        return opciones

    #---------------------------------------------------------
    # Obtener opciones de capacidad de un clasificador
    #---------------------------------------------------------
    def obtener_opciones_capacidad_cla(self, clasificador):

        destinos = self.bd.consultar(f"""
            SELECT Lado, Descripcion, COUNT(*)
            FROM TablasDistribucionClasificador
            WHERE Clasificador = {clasificador}
            GROUP BY Lado, Descripcion
            ORDER BY Lado, Descripcion
        """)

        capacidad_largo = 0
        capacidad_total = 0
        lados_cortos = []

        for lado, descripcion, cantidad in destinos:

            capacidad_total += cantidad

            if descripcion == "Lado_Largo":
                capacidad_largo += cantidad

            if descripcion == "Lado_corto":
                lados_cortos.append({
                    "Lado": lado,
                    "Capacidad": cantidad
                })

        opciones = []

        if capacidad_largo > 0:
            opciones.append({
                "Tipo": "LARGOS",
                "Nombre": "2 Lado_Largo",
                "Capacidad": capacidad_largo,
                "LadoCorto": None
            })

        for lado_corto in lados_cortos:
            opciones.append({
                "Tipo": "LARGOS_MAS_CORTO",
                "Nombre": "2 Lado_Largo + Lado_corto " + str(lado_corto["Lado"]),
                "Capacidad": capacidad_largo + lado_corto["Capacidad"],
                "LadoCorto": lado_corto["Lado"]
            })

        if capacidad_total > 0:
            opciones.append({
                "Tipo": "COMPLETO",
                "Nombre": "Carrusel completo",
                "Capacidad": capacidad_total,
                "LadoCorto": None
            })

        return opciones

    #---------------------------------------------------------
    # Orden de TipoCaja obligatorio
    #---------------------------------------------------------
    def obtener_orden_tipo_caja(self):

        return {
            "4_Nueva_40": 1,
            "3_Usada_40": 2,
            "2_Reutilizada_30": 3,
            "1_Nueva_30": 4
        }

    #---------------------------------------------------------
    # Ordenar registros por TipoCaja sin romper tienda
    #---------------------------------------------------------
    def ordenar_registros_por_tipo_caja_sin_romper_tienda(self, registros):

        orden_tipo = self.obtener_orden_tipo_caja()
        tiendas = {}

        for tienda, aparte, lotes, pais, tipo_caja in registros:

            if tienda not in tiendas:
                tiendas[tienda] = {
                    "Tienda": tienda,
                    "Lotes": 0,
                    "Apartes": 0,
                    "OrdenTipo": orden_tipo.get(tipo_caja, 999),
                    "Registros": []
                }

            tiendas[tienda]["Lotes"] += lotes
            tiendas[tienda]["Apartes"] += 1
            tiendas[tienda]["Registros"].append((tienda, aparte, lotes, pais, tipo_caja))

            orden_actual = orden_tipo.get(tipo_caja, 999)

            if orden_actual < tiendas[tienda]["OrdenTipo"]:
                tiendas[tienda]["OrdenTipo"] = orden_actual

        tiendas_ordenadas = sorted(
            tiendas.values(),
            key=lambda t: (t["OrdenTipo"], -t["Lotes"], -t["Apartes"], t["Tienda"])
        )

        registros_ordenados = []

        for tienda in tiendas_ordenadas:
            tienda["Registros"].sort(
                key=lambda r: (orden_tipo.get(r[4], 999), r[1])
            )

            for registro in tienda["Registros"]:
                registros_ordenados.append(registro)

        return registros_ordenados

    #---------------------------------------------------------
    # Seleccionar mejores tiendas por lotes sin romper tienda
    #---------------------------------------------------------
    def seleccionar_mejores_tiendas(self, tabla, capacidad):

        registros = self.bd.consultar(
            "SELECT Tienda, Aparte, Lotes, Pais, TipoCaja FROM " + tabla
        )

        tiendas = {}

        for tienda, aparte, lotes, pais, tipo_caja in registros:

            if tienda not in tiendas:
                tiendas[tienda] = {
                    "Tienda": tienda,
                    "Lotes": 0,
                    "Apartes": 0,
                    "Registros": []
                }

            tiendas[tienda]["Lotes"] += lotes
            tiendas[tienda]["Apartes"] += 1
            tiendas[tienda]["Registros"].append((tienda, aparte, lotes, pais, tipo_caja))

        tiendas_ordenadas = sorted(
            tiendas.values(),
            key=lambda t: (t["Lotes"], t["Apartes"]),
            reverse=True
        )

        registros_seleccionados = []
        tiendas_seleccionadas = 0
        apartes_seleccionados = 0
        lotes_seleccionados = 0

        tiendas_fuera = 0
        apartes_fuera = 0
        lotes_fuera = 0

        for tienda in tiendas_ordenadas:

            if apartes_seleccionados + tienda["Apartes"] <= capacidad:

                tiendas_seleccionadas += 1
                apartes_seleccionados += tienda["Apartes"]
                lotes_seleccionados += tienda["Lotes"]

                for registro in tienda["Registros"]:
                    registros_seleccionados.append(registro)

            else:

                tiendas_fuera += 1
                apartes_fuera += tienda["Apartes"]
                lotes_fuera += tienda["Lotes"]

        registros_seleccionados = self.ordenar_registros_por_tipo_caja_sin_romper_tienda(
            registros_seleccionados
        )

        return {
            "Registros": registros_seleccionados,
            "Tiendas": tiendas_seleccionadas,
            "Apartes": apartes_seleccionados,
            "Lotes": lotes_seleccionados,
            "FueraTiendas": tiendas_fuera,
            "FueraApartes": apartes_fuera,
            "FueraLotes": lotes_fuera
        }

    #---------------------------------------------------------
    # Mostrar opciones en tabla
    #---------------------------------------------------------
    def mostrar_opciones(self, tabla, opciones):

        self.limpiar_tabla(tabla)

        for opcion in opciones:

            tabla.insert(
                "",
                "end",
                iid=str(opcion["Id"]),
                values=(
                    opcion["Id"],
                    "CLA " + str(opcion["Clasificador"]),
                    opcion["Nombre"],
                    opcion["Capacidad"],
                    opcion["Tiendas"],
                    opcion["Apartes"],
                    round(opcion["Lotes"], 2),
                    opcion["FueraTiendas"],
                    opcion["FueraApartes"],
                    round(opcion["FueraLotes"], 2)
                )
            )

    #---------------------------------------------------------
    # Limpiar tabla visual
    #---------------------------------------------------------
    def limpiar_tabla(self, tabla):

        for item in tabla.get_children():
            tabla.delete(item)

    #---------------------------------------------------------
    # Usar opcion subpedido
    #---------------------------------------------------------
    def usar_opcion_subpedido(self):

        opcion = self.obtener_opcion_seleccionada(
            self.tabla_subpedido,
            self.opciones_subpedido
        )

        if opcion is None:
            messagebox.showwarning(
                "Sin opcion",
                "Selecciona una opcion del subpedido."
            )
            return

        if opcion.get("Tipo") == "LARGOS":
            opcion = self.ajustar_tolvas_lados_largos(
                opcion,
                tabla_origen="ADELANTO_PEDIDO_1",
                tabla_visual=self.tabla_subpedido,
                opciones=self.opciones_subpedido,
                bloque="SUBPEDIDO / NO EVACUAR",
            )
            if opcion is None:
                return

        self.opcion_subpedido = opcion
        self.registros_subpedido = opcion["Registros"]
        self.guardar_seleccion("ADELANTO", opcion)

        # Si el pedido completo ya estaba importado, cualquier cambio en la
        # seleccion del subpedido obliga a reconstruir el resto desde cero.
        self.recalcular_resto_por_cambio_adelanto()

        self.lbl_subpedido.config(
            text="Seleccionado: CLA " + str(opcion["Clasificador"]) + " | "
            + opcion["Nombre"] + " | "
            + str(opcion["Apartes"]) + " apartes | "
            + str(round(opcion["Lotes"], 2)) + " lotes"
        )
        self.actualizar_resumen()

    #---------------------------------------------------------
    # Usar opcion resto
    #---------------------------------------------------------
    def usar_opcion_resto(self):

        opcion = self.obtener_opcion_seleccionada(
            self.tabla_resto,
            self.opciones_resto
        )

        if opcion is None:
            messagebox.showwarning(
                "Sin opcion",
                "Selecciona una opcion del pedido completo menos adelanto."
            )
            return

        if opcion.get("Tipo") == "LARGOS":
            opcion = self.ajustar_tolvas_lados_largos(
                opcion,
                tabla_origen="ADELANTO_RESTO",
                tabla_visual=self.tabla_resto,
                opciones=self.opciones_resto,
                bloque="PEDIDO COMPLETO MENOS ADELANTO / EVACUAR",
            )
            if opcion is None:
                return

        self.opcion_resto = opcion
        self.registros_resto = opcion["Registros"]
        self.guardar_seleccion("RESTO", opcion)

        self.lbl_resto.config(
            text="Seleccionado: CLA " + str(opcion["Clasificador"]) + " | "
            + opcion["Nombre"] + " | "
            + str(opcion["Apartes"]) + " apartes | "
            + str(round(opcion["Lotes"], 2)) + " lotes"
        )
        self.actualizar_resumen()

    #---------------------------------------------------------
    # V2.3 - Numero de tolvas en opciones de 2 lados largos
    #---------------------------------------------------------
    def preguntar_tolvas_lados_largos(self, opcion, bloque):

        maximo = int(opcion.get("CapacidadMaxima") or opcion["Capacidad"])

        return simpledialog.askinteger(
            "Tolvas en lados largos - " + bloque,
            bloque
            + "\nCLA " + str(opcion["Clasificador"])
            + " | " + str(opcion.get("NombreBase") or opcion["Nombre"])
            + "\n\n¿Cuantas tolvas (destinos) quieres utilizar?"
            + "\n\nMaximo disponible: " + str(maximo)
            + "\nSe usaran las primeras tolvas por prioridad del clasificador "
            "y se volvera a calcular que tiendas entran, sin romper tienda.",
            parent=self.ventana,
            initialvalue=maximo,
            minvalue=1,
            maxvalue=maximo,
        )

    def ajustar_tolvas_lados_largos(
        self,
        opcion,
        tabla_origen,
        tabla_visual,
        opciones,
        bloque,
    ):
        """Pregunta las tolvas a usar y recalcula la opcion con esa capacidad.

        Devuelve la opcion recalculada o None si el operador cancela o si no
        cabe ninguna tienda completa en ese numero de tolvas.
        """
        tolvas = self.preguntar_tolvas_lados_largos(opcion, bloque)

        if tolvas is None:
            return None

        tolvas = int(tolvas)
        maximo = int(opcion.get("CapacidadMaxima") or opcion["Capacidad"])
        seleccion = self.seleccionar_mejores_tiendas(tabla_origen, tolvas)

        if seleccion["Apartes"] <= 0:
            messagebox.showwarning(
                "No cabe ninguna tienda",
                "Con " + str(tolvas) + " tolvas no cabe ninguna tienda completa "
                "(con todos sus apartes). Elige mas tolvas.",
                parent=self.ventana,
            )
            return None

        nombre_base = str(opcion.get("NombreBase") or opcion["Nombre"])
        if tolvas < maximo:
            nombre = nombre_base + " - " + str(tolvas) + " de " + str(maximo) + " tolvas"
        else:
            nombre = nombre_base

        opcion.update({
            "Nombre": nombre,
            "NombreBase": nombre_base,
            "CapacidadMaxima": maximo,
            "Capacidad": tolvas,
            "DestinosMax": tolvas if tolvas < maximo else None,
            "Registros": seleccion["Registros"],
            "Tiendas": seleccion["Tiendas"],
            "Apartes": seleccion["Apartes"],
            "Lotes": seleccion["Lotes"],
            "FueraTiendas": seleccion["FueraTiendas"],
            "FueraApartes": seleccion["FueraApartes"],
            "FueraLotes": seleccion["FueraLotes"],
        })

        # Refrescar la tabla visual manteniendo la opcion seleccionada.
        self.mostrar_opciones(tabla_visual, opciones)
        try:
            tabla_visual.selection_set(str(opcion["Id"]))
            tabla_visual.see(str(opcion["Id"]))
        except Exception:
            pass

        return opcion

    #---------------------------------------------------------
    # Obtener opcion seleccionada de una tabla
    #---------------------------------------------------------
    def obtener_opcion_seleccionada(self, tabla, opciones):

        seleccion = tabla.selection()

        if len(seleccion) == 0:
            return None

        id_opcion = int(seleccion[0])

        for opcion in opciones:
            if opcion["Id"] == id_opcion:
                return opcion

        return None

    #---------------------------------------------------------
    # Guardar seleccion en tabla
    #---------------------------------------------------------
    def guardar_seleccion(self, fase, opcion):

        self.bd.ejecutar(
            "DELETE FROM ADELANTO_SELECCION WHERE Fase = '" + fase + "'"
        )

        for tienda, aparte, lotes, pais, tipo_caja in opcion["Registros"]:
            self.bd.insertar(
                "ADELANTO_SELECCION",
                (
                    tienda,
                    aparte,
                    lotes,
                    pais,
                    tipo_caja,
                    fase,
                    opcion["Clasificador"]
                )
            )

        self.bd.guardar()

    #---------------------------------------------------------
    # Obtener resumen de una tabla de adelanto
    #---------------------------------------------------------
    def obtener_resumen_tabla(self, tabla):

        datos = self.bd.consultar(
            "SELECT COUNT(DISTINCT Tienda), COUNT(*), IFNULL(SUM(Lotes), 0) FROM " + tabla
        )

        if len(datos) == 0:
            return {"Tiendas": 0, "Apartes": 0, "Lotes": 0}

        return {
            "Tiendas": datos[0][0],
            "Apartes": datos[0][1],
            "Lotes": datos[0][2]
        }

    #---------------------------------------------------------
    # Actualizar resumen superior
    #---------------------------------------------------------
    def actualizar_resumen(self):

        lineas = []

        if self.opcion_subpedido is None:
            lineas.append("Subpedido / No_Evacuar: pendiente de seleccionar.")
        else:
            lineas.append(
                "Subpedido / No_Evacuar: CLA " + str(self.opcion_subpedido["Clasificador"]) + " | "
                + self.opcion_subpedido["Nombre"] + " | "
                + str(self.opcion_subpedido["Tiendas"]) + " tiendas | "
                + str(self.opcion_subpedido["Apartes"]) + " apartes | "
                + str(round(self.opcion_subpedido["Lotes"], 2)) + " lotes"
            )

        if self.opcion_resto is None:
            lineas.append("Pedido completo sin subpedido / Evacuar: pendiente de seleccionar.")
        else:
            lineas.append(
                "Pedido completo sin subpedido / Evacuar: CLA " + str(self.opcion_resto["Clasificador"]) + " | "
                + self.opcion_resto["Nombre"] + " | "
                + str(self.opcion_resto["Tiendas"]) + " tiendas | "
                + str(self.opcion_resto["Apartes"]) + " apartes | "
                + str(round(self.opcion_resto["Lotes"], 2)) + " lotes"
            )

        self.lbl_resumen.config(text="\n".join(lineas))

    #---------------------------------------------------------
    # Generar tablas y exportar
    #---------------------------------------------------------
    def generar_tablas_exportar(self):

        if self.opcion_subpedido is None:
            messagebox.showwarning(
                "Falta adelanto",
                "Selecciona primero la opcion del subpedido."
            )
            return

        if self.opcion_resto is None:
            messagebox.showwarning(
                "Falta resto",
                "Selecciona la opcion del pedido completo menos adelanto."
            )
            return

        if self.opcion_subpedido["Clasificador"] == self.opcion_resto["Clasificador"]:
            messagebox.showwarning(
                "CLA repetido",
                "De momento el adelanto y el resto deben ir en carruseles distintos.",
                parent=self.ventana,
            )
            return

        # Compatibilidad con integraciones y pruebas antiguas que invocan
        # este metodo sobre un objeto minimo. En la aplicacion real el
        # confirmador siempre existe y muestra los dos pedidos en uso.
        confirmador_pedidos = getattr(self, "confirmar_pedidos_de_calculo", None)
        if callable(confirmador_pedidos) and not confirmador_pedidos():
            return

        # El orden de las preguntas reproduce el orden funcional del formulario:
        # 1) Subpedido = No_Evacuar.
        # 2) Pedido completo menos subpedido = Evacuar.
        codigo_no_evacuar = simpledialog.askstring(
            "Codigo No_Evacuar - SUBPEDIDO",
            "Las tiendas seleccionadas en el SUBPEDIDO pertenecen al grupo "
            "NO EVACUAR.\n\nIntroduce el codigo No_Evacuar para la primera "
            "columna del fichero GRTDASWP:",
            parent=self.ventana
        )

        if codigo_no_evacuar is None:
            return

        codigo_no_evacuar = codigo_no_evacuar.strip()

        if codigo_no_evacuar == "":
            messagebox.showwarning(
                "Codigo No_Evacuar obligatorio",
                "Debes introducir el codigo No_Evacuar del SUBPEDIDO.",
                parent=self.ventana
            )
            return

        codigo_evacuar = simpledialog.askstring(
            "Codigo Evacuar - PEDIDO COMPLETO",
            "Las tiendas seleccionadas en el PEDIDO COMPLETO MENOS EL "
            "SUBPEDIDO pertenecen al grupo EVACUAR.\n\nIntroduce el codigo "
            "Evacuar para la primera columna del fichero GRTDASWP:",
            parent=self.ventana
        )

        if codigo_evacuar is None:
            return

        codigo_evacuar = codigo_evacuar.strip()

        if codigo_evacuar == "":
            messagebox.showwarning(
                "Codigo Evacuar obligatorio",
                "Debes introducir el codigo Evacuar del PEDIDO COMPLETO.",
                parent=self.ventana
            )
            return

        progreso = DialogoProgreso(
            self.ventana,
            titulo="Generando Calculo Adelanto",
            mensaje="Preparando tablas de adelanto...",
        )
        try:
            # Invariante obligatorio: ninguna tienda puede estar simultaneamente
            # en la opcion seleccionada del subpedido y en la del pedido/resto.
            self.validar_sin_solape_tiendas(
                self.opcion_subpedido["Registros"],
                self.opcion_resto["Registros"],
                "las opciones finales de subpedido y pedido/resto"
            )

            progreso.actualizar(mensaje="Generando reparto del subpedido y pedido completo...")
            self.crear_reparto_clasificador_adelanto()

            clasificadores = sorted([
                self.opcion_subpedido["Clasificador"],
                self.opcion_resto["Clasificador"]
            ])

            progreso.actualizar(mensaje="Exportando tablas de reparto...")
            archivos_generados = exportar_tablas_reparto_csv(
                clasificadores,
                parent=self.ventana,
            )

            if len(archivos_generados) == 0:
                return

            carpeta_salida = archivos_generados[0].parent

            # GRTDASWP se construye EXCLUSIVAMENTE con las tiendas que han
            # quedado en las tablas finales generadas en REPARTO_CLASIFICADOR.
            # No se usa el pedido completo importado como fuente de Evacuar.
            registros_subpedido_generado = self.obtener_tiendas_reparto_generado(
                self.opcion_subpedido["Clasificador"]
            )
            registros_pedido_generado = self.obtener_tiendas_reparto_generado(
                self.opcion_resto["Clasificador"]
            )

            self.validar_tiendas_grtdaswp_generadas(
                registros_subpedido_generado,
                registros_pedido_generado
            )

            progreso.actualizar(mensaje="Generando fichero GRTDASWP de No_Evacuar/Evacuar...")
            resultado_grtdaswp = exportar_grtdaswp_adelanto(
                codigo_no_evacuar=codigo_no_evacuar,
                codigo_evacuar=codigo_evacuar,
                registros_subpedido_generado=registros_subpedido_generado,
                registros_pedido_generado=registros_pedido_generado,
                carpeta_destino=carpeta_salida
            )

            texto_pedidos = ""
            gestor_trabajo = getattr(self, "gestor_pedidos_trabajo", None)
            if gestor_trabajo is not None:
                gestor_trabajo.registrar_calculo(
                    self.CLAVE_SUBPEDIDO,
                    tipo_calculo="Calculo Adelanto - Subpedido",
                    lado_corto="No aplica en Calculo Adelanto",
                    resumen="No_Evacuar: " + str(len(resultado_grtdaswp["tiendas_no_evacuar"])),
                )
                gestor_trabajo.registrar_calculo(
                    self.CLAVE_PEDIDO_COMPLETO,
                    tipo_calculo="Calculo Adelanto - Pedido completo",
                    lado_corto="No aplica en Calculo Adelanto",
                    resumen="Evacuar: " + str(len(resultado_grtdaswp["tiendas_evacuar"])),
                )
                estado_sub = gestor_trabajo.obtener_estado(self.CLAVE_SUBPEDIDO)
                estado_completo = gestor_trabajo.obtener_estado(self.CLAVE_PEDIDO_COMPLETO)
                texto_pedidos = (
                    "SUBPEDIDO UTILIZADO\n"
                    + GestorPedidosTrabajo.texto_resumen_final(estado_sub)
                    + "\n\nPEDIDO COMPLETO UTILIZADO\n"
                    + GestorPedidosTrabajo.texto_resumen_final(estado_completo)
                    + "\n\n"
                )

            messagebox.showinfo(
                "Calculo Adelanto finalizado",
                "Tablas generadas y exportadas correctamente.\n\n"
                + texto_pedidos
                + "Lado_corto: no aplica en Calculo Adelanto\n\n"
                + "Fichero: " + str(resultado_grtdaswp["ruta"]) + "\n\n"
                + "SUBPEDIDO -> No_Evacuar: "
                + str(len(resultado_grtdaswp["tiendas_no_evacuar"])) + " tiendas"
                + " | Codigo: "
                + resultado_grtdaswp["codigo_no_evacuar"] + "\n"
                + "PEDIDO COMPLETO MENOS SUBPEDIDO -> Evacuar: "
                + str(len(resultado_grtdaswp["tiendas_evacuar"])) + " tiendas"
                + " | Codigo: "
                + resultado_grtdaswp["codigo_evacuar"] + "\n"
                + "Tiendas repetidas entre ambos bloques: 0",
                parent=self.ventana
            )

        except Exception as error:
            messagebox.showerror("Error generando tablas", str(error), parent=self.ventana)
        finally:
            progreso.cerrar()

    #---------------------------------------------------------
    # Obtener tiendas de la tabla final generada por CLA
    #---------------------------------------------------------
    def obtener_tiendas_reparto_generado(self, clasificador):

        clasificador = int(clasificador)

        return self.bd.consultar(f"""
            SELECT DISTINCT Tienda
            FROM REPARTO_CLASIFICADOR
            WHERE Clasificador = {clasificador}
              AND Tienda IS NOT NULL
            ORDER BY Tienda
        """)

    #---------------------------------------------------------
    # Validar origen profesional de GRTDASWP
    #---------------------------------------------------------
    def validar_tiendas_grtdaswp_generadas(
        self,
        registros_subpedido_generado,
        registros_pedido_generado
    ):

        if len(registros_subpedido_generado) == 0:
            raise Exception(
                "No hay tiendas en la tabla generada del subpedido. "
                "No se puede generar GRTDASWP.txt."
            )

        if len(registros_pedido_generado) == 0:
            raise Exception(
                "No hay tiendas en la tabla generada del pedido/resto. "
                "No se puede generar GRTDASWP.txt."
            )

        tiendas_subpedido = {
            str(registro[0]).strip()
            for registro in registros_subpedido_generado
        }
        tiendas_pedido = {
            str(registro[0]).strip()
            for registro in registros_pedido_generado
        }

        if len(tiendas_subpedido) == 0 or len(tiendas_pedido) == 0:
            raise Exception(
                "Las tablas generadas no contienen tiendas validas para GRTDASWP."
            )

        solape = tiendas_subpedido.intersection(tiendas_pedido)

        if solape:
            raise Exception(
                "ERROR CRITICO: la misma tienda aparece en la tabla generada del "
                "subpedido y en la tabla generada del pedido/resto. Tiendas: "
                + ", ".join(sorted(solape))
                + ". No se genera GRTDASWP.txt hasta corregir el calculo."
            )

    #---------------------------------------------------------
    # Crear REPARTO_CLASIFICADOR desde opciones elegidas
    #---------------------------------------------------------
    def crear_reparto_clasificador_adelanto(self):

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS REPARTO_CLASIFICADOR (
                Clasificador INTEGER,
                Lado INTEGER,
                Zona TEXT,
                Tramo INTEGER,
                Bloque INTEGER,
                Destino INTEGER,
                Tienda INTEGER,
                Aparte INTEGER,
                Lotes REAL,
                TipoCaja TEXT,
                Prioridad INTEGER,
                PrioridadOrden INTEGER
            )
        """)

        self.bd.ejecutar("DELETE FROM REPARTO_CLASIFICADOR")

        self.insertar_opcion_en_reparto(self.opcion_subpedido)
        self.insertar_opcion_en_reparto(self.opcion_resto)

        self.bd.guardar()

    #---------------------------------------------------------
    # Insertar una opcion elegida en reparto final
    #---------------------------------------------------------
    def insertar_opcion_en_reparto(self, opcion):

        destinos = self.preparar_destinos_memoria_adelanto(
            self.obtener_destinos_para_opcion(opcion)
        )

        registros = self.ordenar_registros_por_tipo_caja_sin_romper_tienda(
            opcion["Registros"]
        )

        if len(registros) > len(destinos):
            raise Exception(
                "La opcion " + opcion["Nombre"] + " del CLA "
                + str(opcion["Clasificador"]) + " tiene mas apartes que destinos."
            )

        for registro in registros:

            destino = self.buscar_mejor_destino_adelanto(
                destinos,
                registro
            )

            if destino is None:
                raise Exception(
                    "No se encontro destino libre para la opcion "
                    + opcion["Nombre"]
                    + " del CLA "
                    + str(opcion["Clasificador"])
                    + "."
                )

            tienda, aparte, lotes, pais, tipo_caja = registro

            destino["Libre"] = False
            destino["Tienda"] = tienda
            destino["Aparte"] = aparte
            destino["Lotes"] = lotes
            destino["TipoCaja"] = tipo_caja

            valores = (
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"],
                self.calcular_tramo_destino(destino["Destino"]),
                self.calcular_bloque_destino(destino["Destino"]),
                destino["Destino"],
                tienda,
                aparte,
                lotes,
                tipo_caja,
                destino["Prioridad"],
                destino["PrioridadOrden"]
            )

            self.bd.insertar("REPARTO_CLASIFICADOR", valores)

    #---------------------------------------------------------
    # Preparar destinos de adelanto en memoria
    #---------------------------------------------------------
    def preparar_destinos_memoria_adelanto(self, destinos):

        resultado = []

        for clasificador, lado, destino, descripcion, prioridad, prioridad_orden in destinos:

            resultado.append({
                "Clasificador": clasificador,
                "Lado": lado,
                "Destino": destino,
                "Descripcion": descripcion,
                "Prioridad": prioridad,
                "PrioridadOrden": prioridad_orden,
                "Libre": True,
                "Tienda": None,
                "Aparte": None,
                "Lotes": 0,
                "TipoCaja": ""
            })

        return resultado

    #---------------------------------------------------------
    # Buscar mejor destino para adelanto segun jerarquia
    #---------------------------------------------------------
    def buscar_mejor_destino_adelanto(self, destinos, registro):

        descripcion = self.buscar_zona_activa_adelanto(destinos)

        if descripcion is None:
            return None

        candidatos = self.obtener_primeros_destinos_libres_por_lado_adelanto(
            destinos,
            descripcion
        )

        if len(candidatos) == 0:
            return None

        mejor_destino = None
        mejor_valor = None

        for destino in candidatos:

            valor = self.valorar_destino_adelanto(
                destinos,
                destino,
                registro,
                descripcion
            )

            if mejor_valor is None or valor < mejor_valor:
                mejor_valor = valor
                mejor_destino = destino

        return mejor_destino

    #---------------------------------------------------------
    # Buscar zona activa en adelanto
    #---------------------------------------------------------
    def buscar_zona_activa_adelanto(self, destinos):

        for destino in destinos:
            if destino["Libre"] and destino["Descripcion"] == "Lado_Largo":
                return "Lado_Largo"

        for destino in destinos:
            if destino["Libre"] and destino["Descripcion"] == "Lado_corto":
                return "Lado_corto"

        return None

    #---------------------------------------------------------
    # Primer destino libre por lado en adelanto
    #---------------------------------------------------------
    def obtener_primeros_destinos_libres_por_lado_adelanto(self, destinos, descripcion):

        mejores_por_lado = {}

        for destino in destinos:

            if not destino["Libre"]:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            lado = destino["Lado"]

            if lado not in mejores_por_lado:
                mejores_por_lado[lado] = destino
                continue

            if destino["PrioridadOrden"] < mejores_por_lado[lado]["PrioridadOrden"]:
                mejores_por_lado[lado] = destino

        return list(mejores_por_lado.values())

    #---------------------------------------------------------
    # Valorar destino en adelanto
    #---------------------------------------------------------
    def valorar_destino_adelanto(self, destinos, destino, registro, descripcion):

        tienda, aparte, lotes, pais, tipo_caja = registro
        lado = destino["Lado"]

        diferencia_lotes_lado = self.calcular_diferencia_lotes_lados_adelanto(
            destinos,
            descripcion,
            lado,
            lotes
        )

        diferencia_tipo_caja_lado = self.calcular_diferencia_tipo_caja_lados_adelanto(
            destinos,
            descripcion,
            lado,
            tipo_caja
        )

        lotes_lado_resultante = self.obtener_lotes_lado_adelanto(
            destinos,
            descripcion,
            lado
        ) + lotes

        cantidad_tipo_caja_lado_resultante = self.contar_tipo_caja_lado_adelanto(
            destinos,
            descripcion,
            lado,
            tipo_caja
        ) + 1

        return (
            diferencia_lotes_lado,
            diferencia_tipo_caja_lado,
            lotes_lado_resultante,
            cantidad_tipo_caja_lado_resultante,
            destino["PrioridadOrden"]
        )

    #---------------------------------------------------------
    # Lados disponibles para equilibrio en adelanto
    #---------------------------------------------------------
    def obtener_lados_disponibles_equilibrio_adelanto(self, destinos, descripcion):

        lados = []

        for destino in destinos:

            if not destino["Libre"]:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            lado = destino["Lado"]

            if lado not in lados:
                lados.append(lado)

        return lados

    #---------------------------------------------------------
    # Obtener lotes de lado en adelanto
    #---------------------------------------------------------
    def obtener_lotes_lado_adelanto(self, destinos, descripcion, lado):

        total = 0

        for destino in destinos:

            if destino["Libre"]:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Lado"] != lado:
                continue

            total += destino["Lotes"]

        return total

    #---------------------------------------------------------
    # Diferencia de lotes por lado en adelanto con candidato
    #---------------------------------------------------------
    def calcular_diferencia_lotes_lados_adelanto(self, destinos, descripcion, lado_candidato, lotes):

        lados = self.obtener_lados_disponibles_equilibrio_adelanto(
            destinos,
            descripcion
        )

        if lado_candidato not in lados:
            lados.append(lado_candidato)

        valores = []

        for lado in lados:

            total = self.obtener_lotes_lado_adelanto(
                destinos,
                descripcion,
                lado
            )

            if lado == lado_candidato:
                total += lotes

            valores.append(total)

        if len(valores) == 0:
            return 0

        return max(valores) - min(valores)

    #---------------------------------------------------------
    # Contar TipoCaja por lado en adelanto
    #---------------------------------------------------------
    def contar_tipo_caja_lado_adelanto(self, destinos, descripcion, lado, tipo_caja):

        total = 0

        for destino in destinos:

            if destino["Libre"]:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Lado"] != lado:
                continue

            if destino["TipoCaja"] == tipo_caja:
                total += 1

        return total

    #---------------------------------------------------------
    # Diferencia de TipoCaja por lado en adelanto con candidato
    #---------------------------------------------------------
    def calcular_diferencia_tipo_caja_lados_adelanto(self, destinos, descripcion, lado_candidato, tipo_caja):

        lados = self.obtener_lados_disponibles_equilibrio_adelanto(
            destinos,
            descripcion
        )

        if lado_candidato not in lados:
            lados.append(lado_candidato)

        valores = []

        for lado in lados:

            total = self.contar_tipo_caja_lado_adelanto(
                destinos,
                descripcion,
                lado,
                tipo_caja
            )

            if lado == lado_candidato:
                total += 1

            valores.append(total)

        if len(valores) == 0:
            return 0

        return max(valores) - min(valores)

    #---------------------------------------------------------
    # Obtener destinos permitidos para una opcion
    #---------------------------------------------------------
    def obtener_destinos_para_opcion(self, opcion):

        clasificador = opcion["Clasificador"]
        tipo = opcion["Tipo"]

        condiciones = ["Clasificador = " + str(clasificador)]

        if tipo == "LARGOS":
            condiciones.append("Descripcion = 'Lado_Largo'")

        elif tipo == "LARGOS_MAS_CORTO":
            lado_corto = opcion["LadoCorto"]
            condiciones.append(
                "(Descripcion = 'Lado_Largo' OR (Descripcion = 'Lado_corto' AND Lado = " + str(lado_corto) + "))"
            )

        sql = """
            SELECT Clasificador, Lado, Destino, Descripcion, Prioridad, Prioridad_Orden
            FROM TablasDistribucionClasificador
            WHERE {condiciones}
            ORDER BY Prioridad_Orden
        """.format(condiciones=" AND ".join(condiciones))

        # V2.3: si el operador limito las tolvas de los lados largos, solo se
        # usan las primeras N tolvas por prioridad del clasificador.
        destinos_max = opcion.get("DestinosMax")
        if destinos_max:
            sql += " LIMIT " + str(int(destinos_max))

        return self.bd.consultar(sql)

    #---------------------------------------------------------
    # Calcular bloque de destino
    #---------------------------------------------------------
    def calcular_bloque_destino(self, destino):

        return ((int(destino) - 1) // 10) + 1

    #---------------------------------------------------------
    # Calcular tramo simple de destino para salida
    #---------------------------------------------------------
    def calcular_tramo_destino(self, destino):

        return self.calcular_bloque_destino(destino)

    #---------------------------------------------------------
    # Ejecutar formulario
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
