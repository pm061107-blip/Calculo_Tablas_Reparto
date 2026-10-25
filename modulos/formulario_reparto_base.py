import tkinter as tk
from tkinter import messagebox

from bd.basedatos import BaseDatos
from modulos.importador_pedidos import ImportadorPedidos
from modulos.procesar_estarepp import ProcesarESTAREPP
from modulos.motor_reparto import MotorReparto
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
from modulos.repeticion_tiendas import capacidad_clasificadores, preguntar_durante_progreso
from modulos.gestor_reset_calculos import GestorResetCalculos


class FormularioRepartoBase:

    CLAVE_PEDIDO_TRABAJO = "REPARTO_BASE"

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None, titulo="Reparto", subtitulo=""):

        self.bd = BaseDatos()
        self.ventana_padre = ventana_padre
        self.clave_pedido_trabajo = str(
            getattr(self, "CLAVE_PEDIDO_TRABAJO", "REPARTO_BASE")
        ).strip().upper()
        self.gestor_pedidos_trabajo = GestorPedidosTrabajo(self.bd.conexion)

        self.tipo_fichero = None
        self.tabla_origen_pedido = "ESTAREPP"
        self.registros_estarepp = 0
        self.tiendas_aparte = 0
        self.lotes_totales = 0
        self.destinos_cla_1 = 0
        self.destinos_cla_2 = 0
        self.destinos_totales = 0

        self.tamano_bloque = tk.StringVar(value="10")

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title(titulo)
        self.ventana.geometry("920x940")
        self.ventana.minsize(860, 800)
        self.ventana.resizable(True, True)

        self.titulo = titulo
        self.subtitulo = subtitulo

        self.crear_controles()
        self.restaurar_pedido_trabajo()

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = crear_marco_scrollable(self.ventana, padx=0, pady=0)

        titulo = tk.Label(
            contenedor,
            text=self.titulo.upper(),
            font=("Arial", 18, "bold")
        )
        titulo.pack(pady=(12, 4))

        if self.subtitulo != "":
            subtitulo = tk.Label(
                contenedor,
                text=self.subtitulo,
                font=("Arial", 10)
            )
            subtitulo.pack(pady=(0, 8))

        self.crear_boton_reset(contenedor)
        self.crear_bloque_importacion(contenedor)
        self.pedido_trabajo = ComponentePedidoTrabajo(
            contenedor,
            conexion=self.bd.conexion,
            clave_formulario=self.clave_pedido_trabajo,
            ventana=self.ventana,
            padx=16,
            pady=4,
            wraplength=820,
            compacto=True,
        )
        self.pedido_escenario = ComponentePedidoEscenarioActivo(
            contenedor,
            conexion=self.bd.conexion,
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
            padx=16,
            pady=4,
            wraplength=610,
            compacto=True,
        )
        self.grutiep = ComponenteGRUTIEP(
            contenedor,
            ventana=self.ventana,
            padx=16,
            pady=4,
            wraplength=620,
        )
        self.crear_bloque_datos(contenedor)
        self.crear_bloque_opciones_base(contenedor)
        self.crear_bloque_acciones(contenedor)

    #---------------------------------------------------------
    # Boton de reseteo
    #---------------------------------------------------------
    def crear_boton_reset(self, contenedor=None):

        contenedor = contenedor or self.ventana
        tk.Button(
            contenedor,
            text="RESETEAR FORMULARIO / LIMPIAR PEDIDO Y CALCULOS",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_formulario,
        ).pack(fill="x", padx=16, pady=(6, 4))

    #---------------------------------------------------------
    # Resetear formulario
    #---------------------------------------------------------
    def resetear_formulario(self):

        if not messagebox.askyesno(
            "Resetear formulario",
            "Se limpiara el pedido de este formulario y los ultimos calculos generados.\n\n"
            "No se borraran maestros, GRUTIEP, Tiendas_Web ni volumetria de cajas.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return

        try:
            GestorResetCalculos(self.bd.conexion).resetear_reparto(
                self.clave_pedido_trabajo
            )
            self.tipo_fichero = None
            self.tabla_origen_pedido = "ESTAREPP"
            self.registros_estarepp = 0
            self.tiendas_aparte = 0
            self.lotes_totales = 0
            self.mostrar_estadisticas()
            self.lbl_tipo.config(text="Tipo: pendiente")
            self.boton_calcular.config(state="disabled")
            try:
                self.pedido_trabajo.refrescar()
            except Exception:
                pass
            self.despues_resetear()
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
    # Hook despues de resetear
    #---------------------------------------------------------
    def despues_resetear(self):

        pass

    #---------------------------------------------------------
    # Bloque importacion
    #---------------------------------------------------------
    def crear_bloque_importacion(self, contenedor=None):

        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="Importacion de pedidos",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=12
        )
        marco.pack(fill="x", padx=16, pady=8)

        tk.Button(
            marco,
            text="Importar pedidos",
            width=24,
            height=2,
            command=self.importar_pedidos
        ).grid(row=0, column=0, padx=8, pady=4)

        self.lbl_tipo = tk.Label(
            marco,
            text="Tipo: pendiente",
            font=("Arial", 10)
        )
        self.lbl_tipo.grid(row=0, column=1, sticky="w", padx=16)

    #---------------------------------------------------------
    # Bloque datos
    #---------------------------------------------------------
    def crear_bloque_datos(self, contenedor=None):

        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="Datos del fichero",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=12
        )
        marco.pack(fill="x", padx=16, pady=8)

        self.lbl_tiendas = self.crear_linea_dato(marco, 0, "Tiendas + Aparte:", "-")
        self.lbl_lotes = self.crear_linea_dato(marco, 1, "Lotes totales:", "-")
        self.lbl_destinos = self.crear_linea_dato(marco, 2, "Destinos necesarios:", "-")
        self.lbl_capacidad = self.crear_linea_dato(marco, 3, "Cabe en un carrusel:", "-")
        self.lbl_disponibles = self.crear_linea_dato(marco, 4, "Destinos disponibles:", "-")

    #---------------------------------------------------------
    # Crear linea de dato
    #---------------------------------------------------------
    def crear_linea_dato(self, marco, fila, texto, valor):

        etiqueta = tk.Label(
            marco,
            text=texto,
            width=24,
            anchor="w",
            font=("Arial", 10)
        )
        etiqueta.grid(row=fila, column=0, sticky="w", pady=3)

        dato = tk.Label(
            marco,
            text=valor,
            width=40,
            anchor="w",
            font=("Arial", 10, "bold")
        )
        dato.grid(row=fila, column=1, sticky="w", pady=3)

        return dato

    #---------------------------------------------------------
    # Bloque opciones base
    #---------------------------------------------------------
    def crear_bloque_opciones_base(self, contenedor=None):

        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="Opciones del calculo",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=12
        )
        marco.pack(fill="x", padx=16, pady=8)

        tk.Label(
            marco,
            text="Tamano de bloque:",
            font=("Arial", 10)
        ).grid(row=0, column=0, sticky="w", padx=4, pady=6)

        tk.Entry(
            marco,
            textvariable=self.tamano_bloque,
            width=8
        ).grid(row=0, column=1, sticky="w", padx=12, pady=6)

        self.crear_opciones_especificas(marco)

    #---------------------------------------------------------
    # Hook para cada formulario especifico
    #---------------------------------------------------------
    def crear_opciones_especificas(self, marco):

        pass

    #---------------------------------------------------------
    # Bloque acciones
    #---------------------------------------------------------
    def crear_bloque_acciones(self, contenedor=None):

        contenedor = contenedor or self.ventana
        marco = tk.Frame(contenedor)
        marco.pack(fill="x", padx=16, pady=10)

        self.boton_calcular = tk.Button(
            marco,
            text="CALCULAR Y EXPORTAR",
            width=24,
            height=2,
            command=self.calcular_reparto,
            state="disabled",
            bg="#d9ead3"
        )
        self.boton_calcular.pack(side="left", padx=8)

        tk.Button(
            marco,
            text="Cerrar",
            width=14,
            height=2,
            command=self.ventana.destroy
        ).pack(side="right", padx=8)

    #---------------------------------------------------------
    # Importar pedidos
    #---------------------------------------------------------
    def importar_pedidos(self):

        try:
            importador = ImportadorPedidos(parent=self.ventana)
            self.tipo_fichero = importador.importar()

            if self.tipo_fichero is None:
                messagebox.showwarning(
                    "Importacion cancelada",
                    "No se ha importado ningun fichero.",
                    parent=self.ventana
                )
                return

            procesador = ProcesarESTAREPP(bd=self.bd)
            procesador.procesar()

            self.tabla_origen_pedido = "ESTAREPP"
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

            self.cargar_estadisticas()
            self.mostrar_estadisticas()
            self.despues_importar()

            self.boton_calcular.config(state="normal")

            messagebox.showinfo(
                "Importacion finalizada",
                "Pedidos importados y preparados correctamente.",
                parent=self.ventana
            )

        except Exception as error:
            messagebox.showerror("Error importando pedidos", str(error), parent=self.ventana)

    #---------------------------------------------------------
    # Usar pedido materializado desde Calculo de cajas
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
            bd=self.bd,
        ).procesar()

        self.tabla_origen_pedido = tabla_origen
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

        self.cargar_estadisticas()
        self.mostrar_estadisticas()
        self.despues_importar()
        self.boton_calcular.config(state="normal")

        messagebox.showinfo(
            titulo_mensaje,
            texto_mensaje,
            parent=self.ventana,
        )
        return True

    #---------------------------------------------------------
    # Usar pedido materializado desde Calculo de cajas
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
                    + GestorPedidoEscenarioActivo.formatear_fecha(
                        estado.get("FechaHora")
                    )
                ),
                titulo_mensaje="Escenario activo preparado",
                texto_mensaje=(
                    nombre_origen
                    + " ya esta preparado para este reparto.\n\n"
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
    # Usar pedido descartado desde Calculo de cajas
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
                    + GestorPedidoEscenarioActivo.formatear_fecha(
                        estado.get("FechaHora")
                    )
                ),
                titulo_mensaje="Tiendas descartadas preparadas",
                texto_mensaje=(
                    nombre_origen
                    + " ya esta preparado para este reparto.\n\n"
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
            self.tabla_origen_pedido = GestorPedidosTrabajo.TABLA_DETALLE
            self.cargar_estadisticas()
            self.mostrar_estadisticas()
            self.despues_importar()
            self.boton_calcular.config(state="normal")
            return True
        except Exception:
            return False

    #---------------------------------------------------------
    # Hook despues de importar
    #---------------------------------------------------------
    def despues_importar(self):

        pass

    #---------------------------------------------------------
    # Cargar estadisticas
    #---------------------------------------------------------
    def cargar_estadisticas(self):

        estado = self.gestor_pedidos_trabajo.obtener_estado(
            self.clave_pedido_trabajo
        )
        if not estado.get("Disponible"):
            raise RuntimeError(GestorPedidosTrabajo.texto_estado(estado))

        self.registros_estarepp = int(estado.get("Registros", 0) or 0)
        self.tiendas_aparte = int(estado.get("Apartes", 0) or 0)
        self.lotes_totales = float(estado.get("Lotes", 0) or 0)

        self.destinos_cla_1 = self.contar_destinos_clasificador(1)
        self.destinos_cla_2 = self.contar_destinos_clasificador(2)
        self.destinos_totales = self.destinos_cla_1 + self.destinos_cla_2

    #---------------------------------------------------------
    # Contar destinos por clasificador
    #---------------------------------------------------------
    def contar_destinos_clasificador(self, clasificador):

        datos = self.bd.consultar(f"""
            SELECT COUNT(*)
            FROM TablasDistribucionClasificador
            WHERE Clasificador = {clasificador}
        """)

        if len(datos) == 0:
            return 0

        return datos[0][0]

    #---------------------------------------------------------
    # Mostrar estadisticas
    #---------------------------------------------------------
    def mostrar_estadisticas(self):

        cabe_un_carrusel = "SI"

        if self.tiendas_aparte > max(self.destinos_cla_1, self.destinos_cla_2):
            cabe_un_carrusel = "NO"

        self.lbl_tipo.config(text="Tipo: " + str(self.tipo_fichero))
        self.lbl_tiendas.config(text=str(self.tiendas_aparte))
        self.lbl_lotes.config(text=str(round(self.lotes_totales, 2)))
        self.lbl_destinos.config(text=str(self.tiendas_aparte))
        self.lbl_capacidad.config(text=cabe_un_carrusel)
        self.lbl_disponibles.config(
            text=(
                "CLA 1: "
                + str(self.destinos_cla_1)
                + " | CLA 2: "
                + str(self.destinos_cla_2)
                + " | Total: "
                + str(self.destinos_totales)
            )
        )

    #---------------------------------------------------------
    # Obtener tamano bloque
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
    # Validar hay pedidos
    #---------------------------------------------------------
    def validar_pedidos_importados(self):

        estado = self.gestor_pedidos_trabajo.obtener_estado(
            self.clave_pedido_trabajo
        )
        if not estado.get("Disponible"):
            messagebox.showwarning(
                "Sin pedido de trabajo",
                GestorPedidosTrabajo.texto_estado(estado),
                parent=self.ventana,
            )
            return False

        return True

    #---------------------------------------------------------
    # Validar capacidad de un carrusel
    #---------------------------------------------------------
    def validar_capacidad_un_carrusel(self, clasificador):

        capacidad = self.contar_destinos_clasificador(clasificador)

        if self.tiendas_aparte > capacidad:
            messagebox.showerror(
                "No cabe en un carrusel",
                "El reparto necesita "
                + str(self.tiendas_aparte)
                + " destinos y el carrusel "
                + str(clasificador)
                + " solo tiene "
                + str(capacidad)
                + "."
            )
            return False

        return True

    #---------------------------------------------------------
    # Ejecutar motor y exportar
    #---------------------------------------------------------
    def ejecutar_motor_y_exportar(self, clasificadores, prioridad="NORMAL", configuracion_paises=None, configuracion_prioridad_paises=None):

        if not self.pedido_trabajo.confirmar_calculo(
            "calcular y exportar las tablas"
        ):
            return None

        progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando reparto",
            mensaje="Validando GRUTIEP y preparando pedido de trabajo...",
        )
        try:
            preparacion_grutiep = preparar_pedido_con_grutiep_para_tablas(
                self.bd.conexion,
                self.clave_pedido_trabajo,
                parent=self.ventana,
            )
            clave_calculo = preparacion_grutiep["ClavePedidoTrabajo"]

            motor = MotorReparto(
                clave_pedido_trabajo=clave_calculo
            )

            # V2.5: tiendas/apartes que superan el umbral de lotes
            motor.cargar_tmp()
            repeticiones, progreso = preguntar_durante_progreso(
                progreso,
                lambda: DialogoProgreso(
                    self.ventana,
                    titulo="Calculando reparto",
                    mensaje="Calculando reparto y asignando destinos...",
                ),
                self.ventana,
                self.bd.conexion,
                motor.tmp,
                capacidad=capacidad_clasificadores(self.bd.conexion, clasificadores),
                contexto=self.titulo,
            )
            if repeticiones is None:
                return None

            progreso.actualizar(mensaje="Calculando reparto y asignando destinos...")
            resumen_motor = motor.reparto_general(
                clasificadores,
                self.obtener_tamano_bloque(),
                prioridad,
                configuracion_paises,
                configuracion_prioridad_paises,
                repeticiones=repeticiones,
            )

            progreso.actualizar(mensaje="Exportando tablas de reparto...")
            archivos = exportar_tablas_reparto_csv(
                clasificadores,
                configuracion_paises,
                parent=self.ventana,
                clave_pedido_trabajo=clave_calculo,
                validar_grutiep=False,
            )
        finally:
            progreso.cerrar()

        opcion_lado = (resumen_motor or {}).get("LadoCorto", {}) or {}
        nombre_lado = str(opcion_lado.get("Nombre", "No aplica"))
        self.gestor_pedidos_trabajo.registrar_calculo(
            self.clave_pedido_trabajo,
            tipo_calculo=self.titulo,
            lado_corto=nombre_lado,
            resumen=(
                "Clasificadores: "
                + ", ".join(str(valor) for valor in clasificadores)
                + " | Archivos: "
                + str(len(archivos or []))
                + " | "
                + str(preparacion_grutiep.get("Resumen", ""))
            ),
        )
        estado = self.pedido_trabajo.refrescar()
        return {
            "Archivos": archivos,
            "LadoCorto": nombre_lado,
            "Pedido": estado,
            "PedidoTexto": GestorPedidosTrabajo.texto_resumen_final(estado),
            "GRUTIEP": preparacion_grutiep,
            "Motor": resumen_motor,
        }

    #---------------------------------------------------------
    # Calcular reparto
    #---------------------------------------------------------
    def calcular_reparto(self):

        raise NotImplementedError

    #---------------------------------------------------------
    # Ejecutar formulario
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
