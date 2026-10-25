import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox

from modulos.importador_pedidos import ImportadorPedidos
from modulos.procesar_estarepp import ProcesarESTAREPP
from modulos.motor_busca_fuera_tabla import MotorBuscaFueraTabla
from modulos.formulario_paises_fuera_tabla import FormularioPaisesFijosFueraTabla
from modulos.exportar_tabla_reparto_csv import exportar_tablas_reparto_csv
from modulos.componente_grutiep import ComponenteGRUTIEP
from modulos.componente_pedido_escenario_activo import (
    ComponentePedidoEscenarioActivo,
)
from modulos.gestor_pedido_escenario_activo import (
    GestorPedidoEscenarioActivo,
)
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo
from modulos.componente_pedido_trabajo import ComponentePedidoTrabajo
from modulos.gestor_grutiep_calculo import preparar_pedido_con_grutiep_para_tablas
from modulos.ventanas_tk import crear_marco_scrollable
from modulos.dialogo_progreso import DialogoProgreso
from modulos.repeticion_tiendas import preguntar_durante_progreso
from modulos.gestor_reset_calculos import GestorResetCalculos
from modulos.formulario_editor_lados_cortos_domingo import EditorLadosCortosDomingo


class FormularioBuscaFueraTabla:

    CLAVE_PEDIDO_TRABAJO = "BUSCA_FUERA_TABLA"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.ventana_padre = ventana_padre
        self.clave_pedido_trabajo = self.CLAVE_PEDIDO_TRABAJO
        self.motor = MotorBuscaFueraTabla(
            clave_pedido_trabajo=self.clave_pedido_trabajo
        )
        self.gestor_pedidos_trabajo = GestorPedidosTrabajo(
            self.motor.bd.conexion
        )

        self.tipo_fichero = None
        self.pedido_importado = False
        self.analisis_realizado = False
        self.calculo_permitido = False
        self.configuracion_paises = self.configuracion_paises_vacia()

        self.tamano_bloque = tk.StringVar(value="10")
        # V2.4: modo domingo, lados cortos elegidos a mano.
        self.modo_domingo = tk.BooleanVar(value=False)

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Busca Fuera de Tabla")
        self.ventana.geometry("1080x900")
        self.ventana.minsize(980, 820)
        self.ventana.resizable(True, True)

        self.crear_controles()
        self.restaurar_pedido_trabajo()
        self.actualizar_estado_botones()

    #---------------------------------------------------------
    # Configuracion de paises vacia
    #---------------------------------------------------------
    def configuracion_paises_vacia(self):

        return {
            "Activo": False,
            "Modo": "NINGUNO",
            "PaisesCLA1": [],
            "PaisesCLA2": [],
            "RestoAlOtro": False,
        }

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = crear_marco_scrollable(self.ventana, padx=18, pady=14)

        tk.Label(
            contenedor,
            text="BUSCA FUERA DE TABLA",
            font=("Arial", 18, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            contenedor,
            text=(
                "Las tiendas ya asignadas en las tablas activas son inamovibles. "
                "El calculo coloca unicamente Tienda+Aparte pendientes en tolvas libres, "
                "teniendo en cuenta la carga real existente de ambos CLA."
            ),
            font=("Arial", 10),
            justify="left",
            wraplength=1020,
        ).pack(anchor="w", pady=(0, 10))

        self.crear_boton_reset(contenedor)
        self.crear_bloque_importacion(contenedor)
        self.pedido_trabajo = ComponentePedidoTrabajo(
            contenedor,
            conexion=self.motor.bd.conexion,
            clave_formulario=self.clave_pedido_trabajo,
            ventana=self.ventana,
            padx=0,
            pady=4,
            wraplength=940,
            compacto=True,
        )
        self.pedido_escenario = ComponentePedidoEscenarioActivo(
            contenedor,
            conexion=self.motor.bd.conexion,
            ventana=self.ventana,
            acciones=[
                {
                    "texto": "USAR ESCENARIO ACTIVO",
                    "command": self.usar_escenario_activo,
                    "width": 27,
                },
                {
                    "texto": "USAR TIENDAS DESCARTADAS",
                    "command": self.usar_tiendas_descartadas_escenario,
                    "width": 31,
                }
            ],
            padx=0,
            pady=4,
            wraplength=820,
            compacto=True,
        )
        self.grutiep = ComponenteGRUTIEP(
            contenedor,
            ventana=self.ventana,
            padx=0,
            pady=4,
            wraplength=820,
        )
        self.crear_bloque_estadisticas(contenedor)
        self.crear_bloque_opciones(contenedor)
        self.crear_bloque_acciones(contenedor)

    #---------------------------------------------------------
    # Boton de reset
    #---------------------------------------------------------
    def crear_boton_reset(self, contenedor):

        tk.Button(
            contenedor,
            text="RESETEAR FUERA DE TABLA / LIMPIAR PEDIDO Y CALCULOS",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_formulario,
        ).pack(fill="x", pady=(6, 4))

    #---------------------------------------------------------
    # Resetear formulario
    #---------------------------------------------------------
    def resetear_formulario(self):

        if not messagebox.askyesno(
            "Resetear Busca Fuera de Tabla",
            "Se limpiaran el pedido, tablas activas importadas y resultados de Fuera de Tabla.\n\n"
            "No se borraran maestros, GRUTIEP, Tiendas_Web ni volumetria de cajas.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return

        try:
            GestorResetCalculos(self.motor.bd.conexion).resetear_fuera_tabla(
                self.clave_pedido_trabajo
            )
            self.tipo_fichero = None
            self.pedido_importado = False
            self.analisis_realizado = False
            self.calculo_permitido = False
            self.configuracion_paises = self.configuracion_paises_vacia()
            self.lbl_archivo_cla1.config(text="CLA 1: pendiente")
            self.lbl_archivo_cla2.config(text="CLA 2: pendiente")
            self.lbl_pedido.config(text="Pedido: pendiente")
            self.lbl_paises.config(text="Paises obligados: NO")
            self.pedido_trabajo.refrescar()
            self.actualizar_estadisticas_basicas()
            self.actualizar_estado_botones()
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
    # Bloque importacion
    #---------------------------------------------------------
    def crear_bloque_importacion(self, contenedor):

        marco = tk.LabelFrame(
            contenedor,
            text="Importacion",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=8)

        tk.Button(
            marco,
            text="Importar tabla activa CLA 1",
            width=26,
            height=2,
            command=lambda: self.importar_tabla_activa(1),
        ).grid(row=0, column=0, padx=6, pady=4)

        tk.Button(
            marco,
            text="Importar tabla activa CLA 2",
            width=26,
            height=2,
            command=lambda: self.importar_tabla_activa(2),
        ).grid(row=0, column=1, padx=6, pady=4)

        tk.Button(
            marco,
            text="Importar pedido",
            width=24,
            height=2,
            command=self.importar_pedido,
        ).grid(row=0, column=2, padx=6, pady=4)

        self.lbl_archivo_cla1 = tk.Label(
            marco,
            text="CLA 1: pendiente",
            anchor="w",
            font=("Arial", 9),
        )
        self.lbl_archivo_cla1.grid(
            row=1,
            column=0,
            sticky="w",
            padx=6,
            pady=(8, 0),
        )

        self.lbl_archivo_cla2 = tk.Label(
            marco,
            text="CLA 2: pendiente",
            anchor="w",
            font=("Arial", 9),
        )
        self.lbl_archivo_cla2.grid(
            row=1,
            column=1,
            sticky="w",
            padx=6,
            pady=(8, 0),
        )

        self.lbl_pedido = tk.Label(
            marco,
            text="Pedido: pendiente",
            anchor="w",
            font=("Arial", 9),
        )
        self.lbl_pedido.grid(
            row=1,
            column=2,
            sticky="w",
            padx=6,
            pady=(8, 0),
        )

    #---------------------------------------------------------
    # Bloque estadisticas
    #---------------------------------------------------------
    def crear_bloque_estadisticas(self, contenedor):

        marco = tk.LabelFrame(
            contenedor,
            text="Resumen de carga real",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=8)

        self.lbl_cla1 = self.crear_linea_dato(
            marco,
            0,
            "CLA 1 ya asignado:",
            "-",
        )
        self.lbl_cla2 = self.crear_linea_dato(
            marco,
            1,
            "CLA 2 ya asignado:",
            "-",
        )
        self.lbl_pedido_total = self.crear_linea_dato(
            marco,
            2,
            "Pedido total:",
            "-",
        )
        self.lbl_dentro = self.crear_linea_dato(
            marco,
            3,
            "Ya asignado del pedido:",
            "-",
        )
        self.lbl_fuera = self.crear_linea_dato(
            marco,
            4,
            "Pendiente / fuera:",
            "-",
        )
        self.lbl_capacidad = self.crear_linea_dato(
            marco,
            5,
            "Capacidad libre:",
            "-",
        )
        self.lbl_control = self.crear_linea_dato(
            marco,
            6,
            "Control de calculo:",
            "-",
        )

    #---------------------------------------------------------
    # Crear linea dato
    #---------------------------------------------------------
    def crear_linea_dato(self, marco, fila, texto, valor):

        tk.Label(
            marco,
            text=texto,
            width=24,
            anchor="w",
            font=("Arial", 10),
        ).grid(row=fila, column=0, sticky="w", pady=3)

        etiqueta = tk.Label(
            marco,
            text=valor,
            width=92,
            anchor="w",
            font=("Arial", 10, "bold"),
            justify="left",
        )
        etiqueta.grid(row=fila, column=1, sticky="w", pady=3)

        return etiqueta

    #---------------------------------------------------------
    # Bloque opciones
    #---------------------------------------------------------
    def crear_bloque_opciones(self, contenedor):

        marco = tk.LabelFrame(
            contenedor,
            text="Opciones",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=8)

        tk.Label(
            marco,
            text="Tamano de bloque:",
            font=("Arial", 10),
        ).grid(row=0, column=0, sticky="w", padx=4, pady=4)

        tk.Entry(
            marco,
            textvariable=self.tamano_bloque,
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=4)

        self.btn_paises = tk.Button(
            marco,
            text="Configurar paises obligados",
            width=28,
            command=self.configurar_paises,
        )
        self.btn_paises.grid(row=0, column=2, sticky="w", padx=18, pady=4)

        self.lbl_paises = tk.Label(
            marco,
            text="Paises obligados: NO",
            font=("Arial", 10, "bold"),
            anchor="w",
        )
        self.lbl_paises.grid(row=0, column=3, sticky="w", padx=8, pady=4)

        tk.Checkbutton(
            marco,
            text=(
                "MODO DOMINGO: calcular como siempre y despues mover a mano las "
                "tiendas de los lados cortos (con informacion de tipo de caja)"
            ),
            variable=self.modo_domingo,
            font=("Arial", 10, "bold"),
            fg="#7f6000",
            anchor="w",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 2))

    #---------------------------------------------------------
    # Bloque acciones
    #---------------------------------------------------------
    def crear_bloque_acciones(self, contenedor):

        marco = tk.Frame(contenedor)
        marco.pack(fill="x", pady=12)

        self.btn_analizar = tk.Button(
            marco,
            text="ANALIZAR FUERA DE TABLA",
            width=26,
            height=2,
            command=self.analizar_fuera_tabla,
            bg="#d9eaf7",
        )
        self.btn_analizar.pack(side="left", padx=6)

        self.btn_calcular = tk.Button(
            marco,
            text="CALCULAR Y EXPORTAR",
            width=24,
            height=2,
            command=self.calcular_y_exportar,
            bg="#d9ead3",
        )
        self.btn_calcular.pack(side="left", padx=6)

        self.btn_exportar_fuera = tk.Button(
            marco,
            text="EXPORTAR FUERA DE TABLA",
            width=26,
            height=2,
            command=self.exportar_fuera_tabla,
            bg="#fff2cc",
        )
        self.btn_exportar_fuera.pack(side="left", padx=6)

        tk.Button(
            marco,
            text="Cerrar",
            width=14,
            height=2,
            command=self.ventana.destroy,
        ).pack(side="right", padx=6)

        self.lbl_estado = tk.Label(
            contenedor,
            text="",
            font=("Arial", 9),
            anchor="w",
            justify="left",
            wraplength=1020,
        )
        self.lbl_estado.pack(fill="x", pady=(4, 0))

    #---------------------------------------------------------
    # Restaurar pedido propio al volver a abrir el formulario
    #---------------------------------------------------------
    def restaurar_pedido_trabajo(self):

        try:
            estado = self.gestor_pedidos_trabajo.obtener_estado(
                self.clave_pedido_trabajo
            )
            self.pedido_trabajo.refrescar()
            if not estado.get("Disponible"):
                return False

            self.tipo_fichero = str(estado.get("NombreOrigen", "Pedido guardado"))
            self.pedido_importado = True
            self.lbl_pedido.config(text="Pedido: " + self.tipo_fichero)
            self.motor.invalidar_analisis()
            self.invalidar_analisis_pantalla()
            return True
        except Exception:
            return False

    #---------------------------------------------------------
    # Seleccionar fichero CSV
    #---------------------------------------------------------
    def seleccionar_csv(self, titulo):

        ruta = filedialog.askopenfilename(
            parent=self.ventana,
            title=titulo,
            filetypes=[
                ("CSV", "*.csv"),
                ("Todos los ficheros", "*.*"),
            ],
        )

        if ruta == "":
            return None

        return ruta

    #---------------------------------------------------------
    # Invalidar resultados de pantalla
    #---------------------------------------------------------
    def invalidar_analisis_pantalla(self):

        self.analisis_realizado = False
        self.calculo_permitido = False
        self.configuracion_paises = self.configuracion_paises_vacia()
        self.lbl_paises.config(text="Paises obligados: NO")
        self.lbl_pedido_total.config(text="-")
        self.lbl_dentro.config(text="-")
        self.lbl_fuera.config(text="-")
        self.lbl_capacidad.config(text="-")
        self.lbl_control.config(text="Pendiente de analizar")
        self.lbl_estado.config(text="")
        self.actualizar_estado_botones()

    #---------------------------------------------------------
    # Importar tabla activa
    #---------------------------------------------------------
    def importar_tabla_activa(self, clasificador):

        ruta = self.seleccionar_csv(
            "Selecciona tabla activa CLA " + str(clasificador)
        )

        if ruta is None:
            return

        try:
            estadisticas = self.motor.importar_tabla_activa(
                clasificador,
                ruta,
            )

            texto = (
                "CLA "
                + str(clasificador)
                + ": "
                + str(estadisticas["TotalDestinos"])
                + " destinos"
                + " | Ocupados: "
                + str(estadisticas["Ocupados"])
                + " | Con tienda: "
                + str(estadisticas["OcupadosConTienda"])
                + " | Libres: "
                + str(estadisticas["Libres"])
            )

            if clasificador == 1:
                self.lbl_archivo_cla1.config(text=texto)
            else:
                self.lbl_archivo_cla2.config(text=texto)

            self.invalidar_analisis_pantalla()
            self.actualizar_estadisticas_basicas()

            messagebox.showinfo(
                "Tabla importada",
                "Tabla activa CLA "
                + str(clasificador)
                + " importada correctamente.\n\n"
                + "Las posiciones ocupadas quedan marcadas como inamovibles.",
                parent=self.ventana,
            )

        except Exception as error:
            messagebox.showerror(
                "Error importando tabla activa",
                str(error),
                parent=self.ventana,
            )

    #---------------------------------------------------------
    # Importar pedido
    #---------------------------------------------------------
    def importar_pedido(self):

        try:
            importador = ImportadorPedidos(parent=self.ventana)
            self.tipo_fichero = importador.importar()

            if self.tipo_fichero is None:
                messagebox.showwarning(
                    "Importacion cancelada",
                    "No se ha importado ningun pedido.",
                    parent=self.ventana,
                )
                return

            procesador = ProcesarESTAREPP(bd=self.motor.bd)
            procesador.procesar()

            nombre_archivo = (
                importador.ruta.name
                if getattr(importador, "ruta", None) is not None
                else str(self.tipo_fichero)
            )
            self.gestor_pedidos_trabajo.guardar_desde_tmp(
                self.clave_pedido_trabajo,
                tipo_origen="IMPORTACION_MANUAL",
                nombre_origen=nombre_archivo,
                tabla_origen="ESTAREPP",
                detalle_origen="Tipo detectado: " + str(self.tipo_fichero),
            )
            self.pedido_trabajo.refrescar()
            self.pedido_importado = True
            self.motor.invalidar_analisis()
            self.invalidar_analisis_pantalla()
            self.lbl_pedido.config(
                text="Pedido: " + str(self.tipo_fichero) + " importado"
            )
            self.actualizar_estado_botones()

            messagebox.showinfo(
                "Pedido importado",
                "Pedido importado y preparado correctamente.\n\n"
                "Pulsa ANALIZAR FUERA DE TABLA para calcular la carga fija "
                "de cada CLA y la carga pendiente.",
                parent=self.ventana,
            )

        except Exception as error:
            messagebox.showerror(
                "Error importando pedido",
                str(error),
                parent=self.ventana,
            )

    #---------------------------------------------------------
    # Usar el pedido del escenario seleccionado en Cajas
    #---------------------------------------------------------
    def _preparar_pedido_escenario_en_formulario(
        self,
        tabla_origen,
        estado,
        tipo_origen,
        nombre_origen,
        detalle_origen,
        titulo_mensaje,
        texto_mensaje,
    ):
        ProcesarESTAREPP(
            tabla_origen=tabla_origen,
            bd=self.motor.bd,
        ).procesar()

        self.tipo_fichero = nombre_origen
        self.gestor_pedidos_trabajo.guardar_desde_tmp(
            self.clave_pedido_trabajo,
            tipo_origen=tipo_origen,
            nombre_origen=nombre_origen,
            tabla_origen=tabla_origen,
            detalle_origen=detalle_origen,
            estado_origen=estado,
        )
        self.pedido_trabajo.refrescar()
        self.pedido_importado = True
        self.motor.invalidar_analisis()
        self.invalidar_analisis_pantalla()
        self.lbl_pedido.config(text="Pedido: " + str(self.tipo_fichero))
        self.actualizar_estado_botones()

        messagebox.showinfo(
            titulo_mensaje,
            texto_mensaje,
            parent=self.ventana,
        )
        return True

    #---------------------------------------------------------
    # Usar el pedido del escenario seleccionado en Cajas
    #---------------------------------------------------------
    def usar_escenario_activo(self, estado=None):

        try:
            estado = estado or self.pedido_escenario.refrescar()
            if not estado or not estado.get("Disponible"):
                messagebox.showwarning(
                    "Sin escenario activo",
                    GestorPedidoEscenarioActivo.texto_estado(estado),
                    parent=self.ventana,
                )
                return False

            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
            return self._preparar_pedido_escenario_en_formulario(
                tabla_origen=GestorPedidoEscenarioActivo.TABLA_PEDIDO,
                estado=estado,
                tipo_origen="ESCENARIO_ACTIVO",
                nombre_origen=nombre_origen,
                detalle_origen=(
                    "Pedido activo del escenario seleccionado en Calculo de cajas el "
                    + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
                ),
                titulo_mensaje="Escenario activo preparado",
                texto_mensaje=(
                    nombre_origen
                    + " ya esta preparado para Busca Fuera de Tabla.\n\n"
                    + GestorPedidoEscenarioActivo.texto_estado(estado)
                ),
            )

        except Exception as error:
            messagebox.showerror(
                "Error usando el escenario activo",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Usar el pedido descartado del escenario seleccionado en Cajas
    #---------------------------------------------------------
    def usar_tiendas_descartadas_escenario(self, _estado=None):

        try:
            estado = self.pedido_escenario.gestor.obtener_estado_descartado()
            if not estado or not estado.get("Disponible"):
                messagebox.showwarning(
                    "Sin tiendas descartadas",
                    GestorPedidoEscenarioActivo.texto_estado_descartado(estado),
                    parent=self.ventana,
                )
                return False

            nombre_origen = GestorPedidoEscenarioActivo.nombre_pedido_descartado(estado)
            return self._preparar_pedido_escenario_en_formulario(
                tabla_origen=GestorPedidoEscenarioActivo.TABLA_DESCARTADO,
                estado=estado,
                tipo_origen="ESCENARIO_DESCARTADO",
                nombre_origen=nombre_origen,
                detalle_origen=(
                    "Pedido completo de las tiendas descartadas del escenario "
                    "seleccionado en Calculo de cajas el "
                    + GestorPedidoEscenarioActivo.formatear_fecha(estado.get("FechaHora"))
                ),
                titulo_mensaje="Tiendas descartadas preparadas",
                texto_mensaje=(
                    nombre_origen
                    + " ya esta preparado para Busca Fuera de Tabla.\n\n"
                    + GestorPedidoEscenarioActivo.texto_estado_descartado(estado)
                ),
            )

        except Exception as error:
            messagebox.showerror(
                "Error usando tiendas descartadas",
                str(error),
                parent=self.ventana,
            )
            return False

    #---------------------------------------------------------
    # Actualizar estadisticas fisicas basicas
    #---------------------------------------------------------
    def actualizar_estadisticas_basicas(self):

        e1 = self.motor.obtener_estadisticas_tabla_activa(1)
        e2 = self.motor.obtener_estadisticas_tabla_activa(2)

        self.lbl_cla1.config(
            text=(
                "Destinos: "
                + str(e1["TotalDestinos"])
                + " | Ocupados: "
                + str(e1["Ocupados"])
                + " | Libres: "
                + str(e1["Libres"])
                + " | Lotes: pendientes de cruzar con pedido"
            )
        )
        self.lbl_cla2.config(
            text=(
                "Destinos: "
                + str(e2["TotalDestinos"])
                + " | Ocupados: "
                + str(e2["Ocupados"])
                + " | Libres: "
                + str(e2["Libres"])
                + " | Lotes: pendientes de cruzar con pedido"
            )
        )

    #---------------------------------------------------------
    # Analizar fuera de tabla
    #---------------------------------------------------------
    def analizar_fuera_tabla(self):

        if not self.pedido_importado:
            messagebox.showwarning(
                "Sin pedido",
                "Primero debes importar un pedido.",
                parent=self.ventana,
            )
            return

        try:
            resumen = self.motor.analizar_fuera_tabla()
            self.analisis_realizado = True
            self.calculo_permitido = bool(resumen["CalculoPermitido"])

            self.lbl_cla1.config(
                text=(
                    str(resumen["CLA1TiendasAsignadas"])
                    + " tiendas/apartes inamovibles | "
                    + self.formatear_lotes(resumen["CLA1LotesAsignados"])
                    + " lotes | Libres: "
                    + str(resumen["LibresCLA1"])
                )
            )
            self.lbl_cla2.config(
                text=(
                    str(resumen["CLA2TiendasAsignadas"])
                    + " tiendas/apartes inamovibles | "
                    + self.formatear_lotes(resumen["CLA2LotesAsignados"])
                    + " lotes | Libres: "
                    + str(resumen["LibresCLA2"])
                )
            )
            self.lbl_pedido_total.config(
                text=(
                    str(resumen["Pedido"])
                    + " tiendas/apartes | "
                    + self.formatear_lotes(resumen["LotesPedido"])
                    + " lotes"
                )
            )
            self.lbl_dentro.config(
                text=(
                    str(resumen["DentroTabla"])
                    + " tiendas/apartes | "
                    + self.formatear_lotes(resumen["LotesDentroTabla"])
                    + " lotes"
                )
            )
            self.lbl_fuera.config(
                text=(
                    str(resumen["FueraTabla"])
                    + " tiendas/apartes | "
                    + self.formatear_lotes(resumen["LotesFuera"])
                    + " lotes"
                )
            )

            capacidad = (
                "CLA 1: "
                + str(resumen["LibresCLA1"])
                + " | CLA 2: "
                + str(resumen["LibresCLA2"])
                + " | Total: "
                + str(resumen["LibresTotal"])
                + " | Pendientes: "
                + str(resumen["FueraTabla"])
                + " | Cabe: "
                + ("SI" if resumen["Cabe"] else "NO")
            )
            self.lbl_capacidad.config(text=capacidad)

            if resumen.get("OcupadosSinMaestro", 0) > 0:
                control = (
                    "BLOQUEADO: "
                    + str(resumen["OcupadosSinMaestro"])
                    + " posiciones ocupadas no existen en el maestro de destinos."
                )
            elif resumen["FueraTabla"] == 0:
                control = "No hay tiendas/apartes fuera de tabla para calcular."
            elif not resumen["Cabe"]:
                control = "BLOQUEADO: no hay suficientes tolvas libres."
            elif resumen.get("CargaNoInformada", 0) > 0:
                control = (
                    "ADVERTENCIA NO BLOQUEANTE: "
                    + str(resumen["CargaNoInformada"])
                    + " asignaciones activas no tienen lotes informados. "
                    + "Se mantienen inamovibles y cuentan como 0 lotes para el balance."
                )
            else:
                control = (
                    "Correcto. El motor conservara todas las posiciones existentes "
                    "y balanceara carga inicial + nuevas asignaciones."
                )

            self.lbl_control.config(text=control)

            advertencias = resumen.get("Advertencias", [])
            self.lbl_estado.config(
                text=" | ".join(advertencias) if advertencias else ""
            )

            self.actualizar_estado_botones()

            mensaje = (
                "Analisis finalizado correctamente.\n\n"
                + "CLA 1 fijo: "
                + self.formatear_lotes(resumen["CLA1LotesAsignados"])
                + " lotes\n"
                + "CLA 2 fijo: "
                + self.formatear_lotes(resumen["CLA2LotesAsignados"])
                + " lotes\n"
                + "Pendiente: "
                + self.formatear_lotes(resumen["LotesFuera"])
                + " lotes"
            )

            if resumen.get("CargaNoInformada", 0) > 0:
                mensaje += (
                    "\n\nAviso: "
                    + str(resumen["CargaNoInformada"])
                    + " asignaciones activas se contabilizan con 0 lotes "
                    + "porque no tienen carga informada. No bloquean el calculo."
                )

            if not self.calculo_permitido:
                mensaje += (
                    "\n\nEl calculo no se habilita hasta resolver el control "
                    "bloqueante indicado en el resumen."
                )

            messagebox.showinfo(
                "Analisis finalizado",
                mensaje,
                parent=self.ventana,
            )

        except Exception as error:
            self.analisis_realizado = False
            self.calculo_permitido = False
            self.actualizar_estado_botones()
            messagebox.showerror(
                "Error analizando",
                str(error),
                parent=self.ventana,
            )

    #---------------------------------------------------------
    # Formatear lotes
    #---------------------------------------------------------
    def formatear_lotes(self, valor):

        numero = float(valor or 0)

        if numero.is_integer():
            return f"{int(numero):,}".replace(",", ".")

        return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    #---------------------------------------------------------
    # Configurar paises obligados
    #---------------------------------------------------------
    def configurar_paises(self):

        if not self.analisis_realizado:
            messagebox.showwarning(
                "Sin analisis",
                "Primero debes analizar fuera de tabla.",
                parent=self.ventana,
            )
            return

        datos_paises = self.motor.obtener_resumen_paises_fuera()
        formulario = FormularioPaisesFijosFueraTabla(
            self.ventana,
            datos_paises,
        )
        resultado = formulario.ejecutar()

        if resultado is None:
            return

        self.configuracion_paises = resultado
        self.actualizar_texto_paises()

    #---------------------------------------------------------
    # Actualizar texto paises
    #---------------------------------------------------------
    def actualizar_texto_paises(self):

        if not self.configuracion_paises.get("Activo", False):
            self.lbl_paises.config(text="Paises obligados: NO")
            return

        texto = "Paises obligados: "
        texto += "CLA1=" + str(
            len(self.configuracion_paises.get("PaisesCLA1", []))
        )
        texto += " | CLA2=" + str(
            len(self.configuracion_paises.get("PaisesCLA2", []))
        )

        if self.configuracion_paises.get("RestoAlOtro", False):
            texto += " | Resto al otro: SI"

        self.lbl_paises.config(text=texto)

    #---------------------------------------------------------
    # Obtener tamano de bloque
    #---------------------------------------------------------
    def obtener_tamano_bloque(self):

        texto = self.tamano_bloque.get().strip()

        if texto == "":
            return 10

        try:
            valor = int(texto)
            if valor <= 0:
                return 10
            return valor
        except ValueError:
            return 10

    #---------------------------------------------------------
    # Exportar listado fuera de tabla
    #---------------------------------------------------------
    def exportar_fuera_tabla(self):

        if not self.analisis_realizado:
            messagebox.showwarning(
                "Sin analisis",
                "Primero debes analizar fuera de tabla.",
                parent=self.ventana,
            )
            return

        carpeta = filedialog.askdirectory(
            parent=self.ventana,
            title="Selecciona carpeta para exportar fuera de tabla",
        )

        if carpeta == "":
            return

        try:
            ruta_archivo = self.motor.exportar_fuera_tabla_csv(
                carpeta,
                self.configuracion_paises,
            )

            messagebox.showinfo(
                "Exportacion finalizada",
                "Listado fuera de tabla exportado correctamente:\n\n"
                + str(ruta_archivo),
                parent=self.ventana,
            )

        except Exception as error:
            messagebox.showerror(
                "Error exportando fuera de tabla",
                str(error),
                parent=self.ventana,
            )

    #---------------------------------------------------------
    # Calcular y exportar
    #---------------------------------------------------------
    def calcular_y_exportar(self):

        if not self.analisis_realizado:
            messagebox.showwarning(
                "Sin analisis",
                "Primero debes analizar fuera de tabla.",
                parent=self.ventana,
            )
            return

        if not self.calculo_permitido:
            messagebox.showwarning(
                "Calculo bloqueado",
                "El resumen indica que el calculo no es seguro o no hay "
                "registros pendientes.",
                parent=self.ventana,
            )
            return

        if not self.pedido_trabajo.confirmar_calculo(
            "calcular y exportar Busca Fuera de Tabla"
        ):
            return

        progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando Busca Fuera de Tabla",
            mensaje="Validando GRUTIEP y preparando pedido de trabajo...",
        )
        try:
            preparacion_grutiep = preparar_pedido_con_grutiep_para_tablas(
                self.motor.bd.conexion,
                self.clave_pedido_trabajo,
                parent=self.ventana,
            )
            clave_calculo = preparacion_grutiep["ClavePedidoTrabajo"]
            self.motor.clave_pedido_trabajo = clave_calculo
            self.motor.gestor_pedidos_trabajo = GestorPedidosTrabajo(
                self.motor.bd.conexion
            )

            # V2.5: solo las tiendas NUEVAS (fuera de tabla) se pueden repetir.
            filas_nuevas = [
                (r["Tienda"], r["Aparte"], r["Lotes"], r["Pais"], r["TipoCaja"])
                for r in self.motor.fuera_tabla
            ]
            libres = getattr(self.motor, "libres_utilizables", {}) or {}
            repeticiones, progreso = preguntar_durante_progreso(
                progreso,
                lambda: DialogoProgreso(
                    self.ventana,
                    titulo="Calculando Busca Fuera de Tabla",
                    mensaje="Calculando nuevas asignaciones fuera de tabla...",
                ),
                self.ventana,
                self.motor.bd.conexion,
                filas_nuevas,
                capacidad=(int(libres.get(1, 0)) + int(libres.get(2, 0))) or None,
                contexto="Busca fuera de tabla (solo tiendas nuevas)",
            )
            if repeticiones is None:
                return

            if self.modo_domingo.get():
                # Calculo igual que siempre y despues ajuste manual de los
                # lados cortos en el editor.
                progreso.actualizar(mensaje="Modo domingo: calculando como siempre...")
                self.motor.calcular_domingo(
                    self.configuracion_paises,
                    self.obtener_tamano_bloque(),
                    repeticiones=repeticiones,
                )
                # El editor es modal: se oculta el progreso mientras se usa.
                progreso.cerrar()
                editor = EditorLadosCortosDomingo(self.ventana, self.motor)
                if not editor.ejecutar():
                    messagebox.showinfo(
                        "Modo domingo cancelado",
                        "No se ha guardado ni exportado nada. Puedes volver a calcular.",
                        parent=self.ventana,
                    )
                    return
                progreso = DialogoProgreso(
                    self.ventana,
                    titulo="Calculando Busca Fuera de Tabla",
                    mensaje="Guardando modo domingo...",
                )
                resumen = self.motor.finalizar_domingo()
            else:
                progreso.actualizar(mensaje="Calculando nuevas asignaciones fuera de tabla...")
                resumen = self.motor.calcular_y_guardar(
                    self.configuracion_paises,
                    self.obtener_tamano_bloque(),
                    repeticiones=repeticiones,
                )

            progreso.actualizar(mensaje="Exportando tablas de reparto...")
            archivos = exportar_tablas_reparto_csv(
                [1, 2],
                self.configuracion_paises,
                parent=self.ventana,
                clave_pedido_trabajo=clave_calculo,
                validar_grutiep=False,
            )

            opcion_lado = self.motor.opcion_lado_corto or {}
            nombre_lado = str(opcion_lado.get("Nombre", "No aplica"))
            self.gestor_pedidos_trabajo.registrar_calculo(
                self.clave_pedido_trabajo,
                tipo_calculo="Busca Fuera de Tabla",
                lado_corto=nombre_lado,
                resumen="Archivos: " + str(len(archivos or [])) + " | " + str(preparacion_grutiep.get("Resumen", "")),
            )
            pedido_texto = self.pedido_trabajo.texto_resumen_final()

            mensaje = (
                pedido_texto
                + "\nLado_corto: " + nombre_lado
                + "\n\n"
                "Busca fuera de tabla calculado correctamente.\n\n"
                + "POSICIONES EXISTENTES INAMOVIBLES\n"
                + "CLA 1: "
                + str(resumen["CLA1InicialTiendas"])
                + " tiendas/apartes | "
                + self.formatear_lotes(resumen["CLA1InicialLotes"])
                + " lotes\n"
                + "CLA 2: "
                + str(resumen["CLA2InicialTiendas"])
                + " tiendas/apartes | "
                + self.formatear_lotes(resumen["CLA2InicialLotes"])
                + " lotes\n\n"
                + "NUEVAS ASIGNACIONES\n"
                + "CLA 1: "
                + str(resumen["CLA1NuevasTiendas"])
                + " tiendas/apartes | "
                + self.formatear_lotes(resumen["CLA1NuevosLotes"])
                + " lotes\n"
                + "CLA 2: "
                + str(resumen["CLA2NuevasTiendas"])
                + " tiendas/apartes | "
                + self.formatear_lotes(resumen["CLA2NuevosLotes"])
                + " lotes\n\n"
                + "CARGA FINAL\n"
                + "CLA 1: "
                + self.formatear_lotes(resumen["CLA1FinalLotes"])
                + " lotes\n"
                + "CLA 2: "
                + self.formatear_lotes(resumen["CLA2FinalLotes"])
                + " lotes\n"
                + "Diferencia final: "
                + self.formatear_lotes(resumen["DiferenciaLotes"])
                + " lotes"
            )

            resumen_analisis = self.motor.obtener_resumen_analisis()
            carga_no_informada = int(
                resumen_analisis.get("CargaNoInformada", 0) or 0
            )
            if carga_no_informada > 0:
                mensaje += (
                    "\n\nNOTA DE BALANCE: "
                    + str(carga_no_informada)
                    + " posiciones existentes sin lotes informados se mantuvieron "
                    + "inamovibles y se contabilizaron con 0 lotes."
                )

            if not archivos:
                mensaje += "\n\nEl calculo se guardo, pero la exportacion fue cancelada."

            messagebox.showinfo(
                "Calculo finalizado",
                mensaje,
                parent=self.ventana,
            )

        except Exception as error:
            messagebox.showerror(
                "Error calculando",
                str(error),
                parent=self.ventana,
            )
        finally:
            progreso.cerrar()

    #---------------------------------------------------------
    # Actualizar estado de botones
    #---------------------------------------------------------
    def actualizar_estado_botones(self):

        if self.motor.tablas_activas_cargadas() and self.pedido_importado:
            self.btn_analizar.config(state="normal")
        else:
            self.btn_analizar.config(state="disabled")

        if self.analisis_realizado:
            self.btn_paises.config(state="normal")
            self.btn_exportar_fuera.config(state="normal")
        else:
            self.btn_paises.config(state="disabled")
            self.btn_exportar_fuera.config(state="disabled")

        if self.analisis_realizado and self.calculo_permitido:
            self.btn_calcular.config(state="normal")
        else:
            self.btn_calcular.config(state="disabled")

    #---------------------------------------------------------
    # Ejecutar
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
