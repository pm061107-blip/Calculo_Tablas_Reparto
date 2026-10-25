import tkinter as tk
from tkinter import messagebox

from bd.basedatos import BaseDatos
from modulos.importador_pedidos import ImportadorPedidos
from modulos.procesar_estarepp import ProcesarESTAREPP
from modulos.configuracion_lados_carrusel import LADOS_CARRUSEL, obtener_lado
from modulos.motor_reparto_lados import MotorRepartoLados
from modulos.exportar_tabla_reparto_lados_csv import exportar_tablas_reparto_lados
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


class FormularioRepartoPorLados:

    CLAVE_PEDIDO_TRABAJO = "REPARTO_POR_LADOS"
    """Formulario independiente para reparto sobre los lados fisicos elegidos."""

    def __init__(self, ventana_padre=None):
        self.ventana_padre = ventana_padre
        self.bd = BaseDatos()
        self.clave_pedido_trabajo = self.CLAVE_PEDIDO_TRABAJO
        self.gestor_pedidos_trabajo = GestorPedidosTrabajo(self.bd.conexion)
        self.tipo_fichero = None
        self.tabla_origen_pedido = "ESTAREPP"
        self.registros_estarepp = 0
        self.tiendas_aparte = 0
        self.lotes_totales = 0
        self.capacidades = {}
        self.checks = {}
        self.vars_lados = {}
        self.ultimo_resumen = None

        self.tamano_bloque = tk.StringVar(value="10")

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Calculo de tabla por lados")
        self.ventana.geometry("1080x920")
        self.ventana.minsize(980, 820)
        self.ventana.resizable(True, True)

        self.crear_controles()
        self.cargar_capacidades_lados()
        self.restaurar_pedido_trabajo()
        self.actualizar_estado_seleccion()

    # ---------------------------------------------------------
    # UI principal
    # ---------------------------------------------------------
    def crear_controles(self):
        contenedor = crear_marco_scrollable(self.ventana, padx=18, pady=14)

        tk.Label(
            contenedor,
            text="CALCULO DE TABLA POR LADOS",
            font=("Arial", 18, "bold"),
        ).pack(pady=(0, 4))

        tk.Label(
            contenedor,
            text="Selecciona libremente los lados fisicos que quieras utilizar. El reparto solo usara esas tolvas.",
            font=("Arial", 10),
        ).pack(pady=(0, 10))

        self.crear_boton_reset(contenedor)
        self.crear_bloque_importacion(contenedor)
        self.pedido_trabajo = ComponentePedidoTrabajo(
            contenedor,
            conexion=self.bd.conexion,
            clave_formulario=self.clave_pedido_trabajo,
            ventana=self.ventana,
            padx=0,
            pady=4,
            wraplength=940,
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
            padx=0,
            pady=4,
            wraplength=800,
            compacto=True,
        )
        self.grutiep = ComponenteGRUTIEP(
            contenedor,
            ventana=self.ventana,
            padx=0,
            pady=4,
            wraplength=820,
        )
        self.crear_bloque_seleccion(contenedor)
        self.crear_bloque_estado(contenedor)
        self.crear_bloque_resultado(contenedor)
        self.crear_bloque_acciones(contenedor)

    def crear_boton_reset(self, padre):
        tk.Button(
            padre,
            text="RESETEAR FORMULARIO / LIMPIAR PEDIDO Y CALCULOS",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_formulario,
        ).pack(fill="x", pady=(6, 4))

    def resetear_formulario(self):
        if not messagebox.askyesno(
            "Resetear reparto por lados",
            "Se limpiara el pedido de este formulario y el ultimo calculo por lados.\n\n"
            "No se borraran maestros, GRUTIEP, Tiendas_Web ni volumetria de cajas.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            GestorResetCalculos(self.bd.conexion).resetear_reparto_por_lados(
                self.clave_pedido_trabajo
            )
            self.tipo_fichero = None
            self.tabla_origen_pedido = "ESTAREPP"
            self.registros_estarepp = 0
            self.tiendas_aparte = 0
            self.lotes_totales = 0
            self.ultimo_resumen = None
            self.lbl_tipo.config(text="Tipo: pendiente")
            self.lbl_datos.config(text="Tienda+Aparte: -   |   Lotes: -")
            for variable in self.vars_lados.values():
                variable.set(False)
            self.pedido_trabajo.refrescar()
            self.actualizar_estado_seleccion()
            self.mostrar_resultado(None)
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

    def crear_bloque_importacion(self, padre):
        marco = tk.LabelFrame(
            padre,
            text="Pedido",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=6)

        tk.Button(
            marco,
            text="IMPORTAR PEDIDOS",
            width=22,
            height=2,
            command=self.importar_pedidos,
        ).grid(row=0, column=0, rowspan=2, padx=(0, 16), pady=2)

        self.lbl_tipo = tk.Label(marco, text="Tipo: pendiente", anchor="w")
        self.lbl_tipo.grid(row=0, column=1, sticky="w")

        self.lbl_datos = tk.Label(
            marco,
            text="Tienda+Aparte: -   |   Lotes: -",
            anchor="w",
            font=("Arial", 10, "bold"),
        )
        self.lbl_datos.grid(row=1, column=1, sticky="w")

        tk.Label(marco, text="Tamano bloque:").grid(row=0, column=2, padx=(30, 6))
        tk.Entry(marco, textvariable=self.tamano_bloque, width=6).grid(row=0, column=3)

        marco.grid_columnconfigure(1, weight=1)

    def crear_bloque_seleccion(self, padre):
        marco = tk.LabelFrame(
            padre,
            text="Seleccion manual de lados fisicos",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=6)

        cla1 = tk.LabelFrame(marco, text="CARRUSEL 1", padx=10, pady=8)
        cla2 = tk.LabelFrame(marco, text="CARRUSEL 2", padx=10, pady=8)
        cla1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cla2.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_columnconfigure(1, weight=1)

        filas = {1: 0, 2: 0}
        for lado in LADOS_CARRUSEL:
            cla = int(lado["Clasificador"])
            padre_cla = cla1 if cla == 1 else cla2
            fila = filas[cla]
            filas[cla] += 1

            variable = tk.BooleanVar(value=False)
            self.vars_lados[lado["Id"]] = variable

            texto = (
                lado["Nombre"].replace("CLA " + str(cla) + " - ", "")
                + "   |   Tolvas "
                + str(lado["Desde"])
                + "-"
                + str(lado["Hasta"])
            )

            check = tk.Checkbutton(
                padre_cla,
                text=texto,
                variable=variable,
                command=lambda lado_id=lado["Id"]: self.al_cambiar_lado(lado_id),
                anchor="w",
            )
            check.grid(row=fila, column=0, sticky="w", pady=4)
            self.checks[lado["Id"]] = check

            etiqueta = tk.Label(
                padre_cla,
                text="capacidad: -",
                width=18,
                anchor="e",
                font=("Arial", 9, "bold"),
            )
            etiqueta.grid(row=fila, column=1, sticky="e", padx=(8, 0))
            self.checks[lado["Id"] + "_cap"] = etiqueta

        cla1.grid_columnconfigure(0, weight=1)
        cla2.grid_columnconfigure(0, weight=1)

    def crear_bloque_estado(self, padre):
        marco = tk.LabelFrame(
            padre,
            text="Capacidad de la seleccion",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="x", pady=6)

        self.lbl_seleccion = tk.Label(marco, text="Lados seleccionados: 0", anchor="w")
        self.lbl_seleccion.grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.lbl_necesarios = tk.Label(marco, text="Necesarios: -", anchor="w")
        self.lbl_necesarios.grid(row=0, column=1, sticky="w", padx=20)

        self.lbl_capacidad = tk.Label(marco, text="Capacidad: 0", anchor="w")
        self.lbl_capacidad.grid(row=0, column=2, sticky="w", padx=20)

        self.lbl_libres = tk.Label(marco, text="Libres/Faltan: -", anchor="w")
        self.lbl_libres.grid(row=0, column=3, sticky="w", padx=20)

        self.lbl_estado = tk.Label(
            marco,
            text="ESTADO: importa un pedido y selecciona al menos un lado",
            font=("Arial", 11, "bold"),
            fg="#7f6000",
            anchor="w",
        )
        self.lbl_estado.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def crear_bloque_resultado(self, padre):
        marco = tk.LabelFrame(
            padre,
            text="Ultimo reparto",
            font=("Arial", 11, "bold"),
            padx=12,
            pady=10,
        )
        marco.pack(fill="both", expand=True, pady=6)

        self.txt_resultado = tk.Text(marco, height=4, wrap="word", font=("Consolas", 10))
        self.txt_resultado.pack(fill="both", expand=True)
        self.txt_resultado.insert("1.0", "Todavia no se ha calculado ningun reparto.\n")
        self.txt_resultado.config(state="disabled")

    def crear_bloque_acciones(self, padre):
        marco = tk.Frame(padre)
        marco.pack(fill="x", pady=(8, 0))

        self.btn_calcular = tk.Button(
            marco,
            text="CALCULAR Y EXPORTAR",
            width=24,
            height=2,
            bg="#d9ead3",
            state="disabled",
            command=self.calcular_y_exportar,
        )
        self.btn_calcular.pack(side="left", padx=(0, 8))

        tk.Button(
            marco,
            text="Cerrar",
            width=14,
            height=2,
            command=self.ventana.destroy,
        ).pack(side="right")

    # ---------------------------------------------------------
    # Capacidades desde el maestro real
    # ---------------------------------------------------------
    def cargar_capacidades_lados(self):
        self.capacidades = {}

        for lado in LADOS_CARRUSEL:
            clasificador = int(lado["Clasificador"])
            numero_lado = int(lado["Lado"])
            descripcion = str(lado["Descripcion"]).replace("'", "''")
            desde = int(lado["Desde"])
            hasta = int(lado["Hasta"])

            datos = self.bd.consultar(f"""
                SELECT COUNT(*)
                FROM TablasDistribucionClasificador
                WHERE Clasificador = {clasificador}
                  AND Lado = {numero_lado}
                  AND Descripcion = '{descripcion}'
                  AND Destino BETWEEN {desde} AND {hasta}
            """)

            capacidad = int(datos[0][0]) if datos else 0
            self.capacidades[lado["Id"]] = capacidad

            etiqueta = self.checks.get(lado["Id"] + "_cap")
            if etiqueta is not None:
                etiqueta.config(
                    text="capacidad: " + str(capacidad)
                    + " / " + str(lado["CapacidadEsperada"])
                )

    # ---------------------------------------------------------
    # Restaurar el pedido propio al reabrir el formulario
    # ---------------------------------------------------------
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
            self.cargar_estadisticas_pedido()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------
    # Importacion
    # ---------------------------------------------------------
    def importar_pedidos(self):
        try:
            importador = ImportadorPedidos(parent=self.ventana)
            tipo = importador.importar()

            if tipo is None:
                return

            ProcesarESTAREPP(bd=self.bd).procesar()
            self.tipo_fichero = tipo
            self.tabla_origen_pedido = "ESTAREPP"
            nombre_archivo = (
                importador.ruta.name
                if getattr(importador, "ruta", None) is not None
                else str(tipo)
            )
            self.gestor_pedidos_trabajo.guardar_desde_tmp(
                self.clave_pedido_trabajo,
                tipo_origen="IMPORTACION_MANUAL",
                nombre_origen=nombre_archivo,
                tabla_origen="ESTAREPP",
                detalle_origen="Tipo detectado: " + str(tipo),
            )
            self.pedido_trabajo.refrescar()
            self.cargar_estadisticas_pedido()
            self.actualizar_estado_seleccion()

            messagebox.showinfo(
                "Importacion finalizada",
                "Pedidos importados y preparados correctamente.",
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error importando pedidos",
                str(error),
                parent=self.ventana,
            )

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
        self.tipo_fichero = nombre_origen
        self.tabla_origen_pedido = tabla_origen
        self.gestor_pedidos_trabajo.guardar_desde_tmp(
            self.clave_pedido_trabajo,
            tipo_origen=tipo_origen,
            nombre_origen=nombre_origen,
            tabla_origen=tabla_origen,
            detalle_origen=detalle_origen,
            estado_origen=estado,
        )
        self.pedido_trabajo.refrescar()
        self.cargar_estadisticas_pedido()
        self.actualizar_estado_seleccion()

        messagebox.showinfo(
            titulo_mensaje,
            texto_mensaje,
            parent=self.ventana,
        )
        return True

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
                    + " ya esta preparado para el reparto por lados.\n\n"
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
                    + " ya esta preparado para el reparto por lados.\n\n"
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

    def cargar_estadisticas_pedido(self):
        estado = self.gestor_pedidos_trabajo.obtener_estado(
            self.clave_pedido_trabajo
        )
        if not estado.get("Disponible"):
            raise RuntimeError(GestorPedidosTrabajo.texto_estado(estado))

        self.registros_estarepp = int(estado.get("Registros", 0) or 0)
        self.tiendas_aparte = int(estado.get("Apartes", 0) or 0)
        self.lotes_totales = float(estado.get("Lotes", 0) or 0)

        self.lbl_tipo.config(text="Tipo: " + str(self.tipo_fichero))
        self.lbl_datos.config(
            text=(
                "Tienda+Aparte: " + str(self.tiendas_aparte)
                + "   |   Lotes: " + str(round(self.lotes_totales, 2))
            )
        )

    # ---------------------------------------------------------
    # Seleccion y capacidad
    # ---------------------------------------------------------
    def obtener_ids_seleccionados(self):
        return [
            lado["Id"]
            for lado in LADOS_CARRUSEL
            if self.vars_lados[lado["Id"]].get()
        ]

    def al_cambiar_lado(self, _lado_id=None):
        # El operador puede seleccionar libremente los lados que quiera usar:
        # un lado, varios lados, un carrusel completo o los dos carruseles.
        # La unica validacion bloqueante es que exista capacidad suficiente
        # dentro de la seleccion realizada.
        self.actualizar_estado_seleccion()

    def actualizar_estado_seleccion(self):
        ids = self.obtener_ids_seleccionados()
        capacidad = sum(self.capacidades.get(lado_id, 0) for lado_id in ids)
        necesarios = self.tiendas_aparte if self.tipo_fichero is not None else None

        nombres = [obtener_lado(lado_id)["Nombre"] for lado_id in ids]
        texto_lados = ", ".join(nombres) if nombres else "ninguno"
        self.lbl_seleccion.config(
            text="Lados seleccionados: " + str(len(ids)) + " (" + texto_lados + ")"
        )
        self.lbl_capacidad.config(text="Capacidad: " + str(capacidad))
        self.lbl_necesarios.config(
            text="Necesarios: " + (str(necesarios) if necesarios is not None else "-")
        )

        puede_calcular = False

        if necesarios is None:
            self.lbl_libres.config(text="Libres/Faltan: -")
            self.lbl_estado.config(
                text="ESTADO: importa un pedido",
                fg="#7f6000",
            )
        elif len(ids) < 1:
            self.lbl_libres.config(text="Libres/Faltan: -")
            self.lbl_estado.config(
                text="ESTADO: selecciona al menos un lado",
                fg="#7f6000",
            )
        else:
            diferencia = capacidad - necesarios
            if diferencia >= 0:
                self.lbl_libres.config(text="Libres: " + str(diferencia))
                self.lbl_estado.config(text="ESTADO: CABE", fg="#38761d")
                puede_calcular = True
            else:
                self.lbl_libres.config(text="Faltan: " + str(abs(diferencia)))
                self.lbl_estado.config(text="ESTADO: NO CABE", fg="#990000")

        self.btn_calcular.config(state="normal" if puede_calcular else "disabled")

    def obtener_tamano_bloque(self):
        try:
            valor = int(self.tamano_bloque.get().strip() or "10")
            return valor if valor > 0 else 10
        except ValueError:
            return 10

    # ---------------------------------------------------------
    # Calculo y exportacion
    # ---------------------------------------------------------
    def calcular_y_exportar(self):
        ids = self.obtener_ids_seleccionados()

        if self.tipo_fichero is None:
            messagebox.showwarning(
                "Sin pedidos",
                "Primero debes importar el pedido.",
                parent=self.ventana,
            )
            return

        if len(ids) < 1:
            messagebox.showwarning(
                "Seleccion incompleta",
                "Selecciona al menos un lado fisico.",
                parent=self.ventana,
            )
            return

        if not self.pedido_trabajo.confirmar_calculo(
            "calcular y exportar el reparto por lados"
        ):
            return

        progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando reparto por lados",
            mensaje="Validando GRUTIEP y preparando pedido de trabajo...",
        )
        try:
            preparacion_grutiep = preparar_pedido_con_grutiep_para_tablas(
                self.bd.conexion,
                self.clave_pedido_trabajo,
                parent=self.ventana,
            )
            clave_calculo = preparacion_grutiep["ClavePedidoTrabajo"]

            motor = MotorRepartoLados(
                clave_pedido_trabajo=clave_calculo
            )

            # V2.5: tiendas/apartes que superan el umbral de lotes
            motor.cargar_tmp()
            capacidad = sum(
                int((obtener_lado(id_lado) or {}).get("CapacidadEsperada", 0) or 0)
                for id_lado in ids
            ) or None
            repeticiones, progreso = preguntar_durante_progreso(
                progreso,
                lambda: DialogoProgreso(
                    self.ventana,
                    titulo="Calculando reparto por lados",
                    mensaje="Calculando reparto por lados...",
                ),
                self.ventana,
                self.bd.conexion,
                motor.tmp,
                capacidad=capacidad,
                contexto="Reparto por lados",
            )
            if repeticiones is None:
                return

            progreso.actualizar(mensaje="Calculando reparto por lados...")
            resumen = motor.reparto_por_lados(
                ids, self.obtener_tamano_bloque(), repeticiones=repeticiones
            )
            self.ultimo_resumen = resumen
            self.mostrar_resultado(resumen)

            progreso.actualizar(mensaje="Exportando tablas de reparto por lados...")
            archivos = exportar_tablas_reparto_lados(
                resumen["Clasificadores"],
                parent=self.ventana,
                validar_grutiep=False,
            )
            lados_texto = ", ".join(
                str(lado.get("Nombre", lado.get("Id", "")))
                for lado in resumen.get("Lados", [])
            )
            self.gestor_pedidos_trabajo.registrar_calculo(
                self.clave_pedido_trabajo,
                tipo_calculo="Reparto por lados",
                lado_corto="No aplica: lados fisicos seleccionados",
                resumen="Lados: " + lados_texto + " | " + str(preparacion_grutiep.get("Resumen", "")),
            )
            pedido_texto = self.pedido_trabajo.texto_resumen_final()
            if archivos:
                messagebox.showinfo(
                    "Reparto finalizado",
                    "Reparto calculado y exportado correctamente.\n\n"
                    + pedido_texto
                    + "\nLados utilizados: " + lados_texto
                    + "\nDestinos libres: " + str(resumen["Libres"]),
                    parent=self.ventana,
                )
            else:
                messagebox.showinfo(
                    "Reparto calculado",
                    "El reparto se ha calculado correctamente. La exportacion fue cancelada.\n\n"
                    + pedido_texto
                    + "\nLados utilizados: " + lados_texto,
                    parent=self.ventana,
                )
        except Exception as error:
            messagebox.showerror(
                "Error calculando reparto por lados",
                str(error),
                parent=self.ventana,
            )
        finally:
            progreso.cerrar()

    def mostrar_resultado(self, resumen):
        self.txt_resultado.config(state="normal")
        if resumen is None:
            self.txt_resultado.delete("1.0", "end")
            self.txt_resultado.insert("1.0", "Todavia no se ha calculado ningun reparto.\n")
            self.txt_resultado.config(state="disabled")
            return

        lineas = [
            "REPARTO POR LADOS FINALIZADO",
            "",
            "Tiendas+Aparte : " + str(resumen["Necesarios"]),
            "Capacidad      : " + str(resumen["Capacidad"]),
            "Destinos libres: " + str(resumen["Libres"]),
            "",
        ]

        for lado in resumen["Lados"]:
            lineas.append(
                f"{lado['Nombre']:<18} | Tolvas {lado['Rango']:<7} | "
                f"Tiendas {lado['Tiendas']:<4} | Lotes {lado['Lotes']}"
            )

        self.txt_resultado.config(state="normal")
        self.txt_resultado.delete("1.0", "end")
        self.txt_resultado.insert("1.0", "\n".join(lineas))
        self.txt_resultado.config(state="disabled")

    def ejecutar(self):
        self.ventana.wait_window()
