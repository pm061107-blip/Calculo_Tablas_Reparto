from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog, ttk, simpledialog

from bd.basedatos import BaseDatos
from modulos.importador_pedidos import ImportadorPedidos
from modulos.importar_volumetria_cajas import ImportarVolumetriaCajas
from modulos.importar_contenedores_cajas import ImportarContenedoresCajas
from modulos.motor_calculo_cajas_pedido import MotorCalculoCajasPedido
from modulos.registro_importaciones_cajas import RegistroImportacionesCajas
from modulos.gestor_tipo_caja_pais import GestorTipoCajaPais
from modulos.gestor_grupos_calculo_cajas import (
    ErrorGruposCalculo,
    GestorGruposCalculoCajas,
)
from modulos.calculador_escenarios_cajas import CalculadorEscenariosCajas
from modulos.gestor_tiendas_fijas_cajas import (
    ErrorTiendasFijas,
    GestorTiendasFijasCajas,
)
from modulos.gestor_pedido_escenario_activo import (
    GestorPedidoEscenarioActivo,
)
from modulos.gestor_pedidos_cajas import GestorPedidosCajas
from modulos.ventanas_tk import forzar_ventana_visible, crear_marco_scrollable
from modulos.dialogo_progreso import DialogoProgreso
from modulos.gestor_reset_calculos import GestorResetCalculos
from modulos.formulario_volumetria_reutilizacion_paises import (
    FormularioVolumetriaReutilizacionPaises,
)


class FormularioCalculoCajasPedido:
    """Formulario V17.24.2: escenario global persistente y reutilizable."""

    def __init__(self, ventana_padre=None):
        self.bd = BaseDatos()
        self.registro_importaciones = RegistroImportacionesCajas()
        self.gestor_tipo_caja_pais = GestorTipoCajaPais(
            conexion=self.bd.conexion
        )
        # V2.1: pedidos acumulados de Calculo de cajas con su marca de picos.
        self.gestor_pedidos_cajas = GestorPedidosCajas(self.bd.conexion)
        self.ventana_padre = ventana_padre

        self.tipo_pedido = None
        self.modo_calculo = tk.StringVar(value="XDOC_LIMPIEZA")
        self.resumen_cajas = None
        self.resumen_paises = None
        self.cajas_400_agotadas = 0
        self.ventana_volumetria = None

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Calculo de cajas para pedido")
        self.ventana.geometry("1320x950")
        self.ventana.minsize(1120, 790)
        self.ventana.resizable(True, True)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.umbral_sku_var = tk.StringVar(master=self.ventana, value="0")
        self.gestor_grupos_calculo = GestorGruposCalculoCajas(
            conexion=self.bd.conexion
        )
        self.gestor_tiendas_fijas = GestorTiendasFijasCajas(
            conexion=self.bd.conexion
        )
        self.gestor_pedido_escenario = GestorPedidoEscenarioActivo(
            conexion=self.bd.conexion
        )
        self.tiendas_fijas = set()
        self.grupos_calculo = []
        self.estado_grupos_calculo = None
        self.resultados_escenarios = {}
        self.escenarios_calculados = False
        self.escenario_activo = CalculadorEscenariosCajas.escenario_todo()
        self.resultado_escenario_activo = None
        self._suspendiendo_invalidacion = False

        self.crear_controles()
        self.cargar_tiendas_fijas(invalidar=False)
        self.cargar_grupos_calculo()
        self.cargar_estado_importaciones()

        self.modo_calculo.trace_add(
            "write", self._al_cambiar_parametros_calculo
        )
        self.umbral_sku_var.trace_add(
            "write", self._al_cambiar_parametros_calculo
        )

    # ---------------------------------------------------------
    # UI general
    # ---------------------------------------------------------
    def crear_controles(self):
        contenedor = crear_marco_scrollable(self.ventana, padx=0, pady=0)
        self.contenedor_principal = contenedor

        cabecera = tk.Frame(contenedor)
        cabecera.pack(fill="x", padx=16, pady=(12, 4))

        tk.Label(
            cabecera,
            text="CALCULO DE CAJAS PARA PEDIDO",
            font=("Arial", 18, "bold"),
        ).pack(side="left")

        acciones = tk.Frame(cabecera)
        acciones.pack(side="right")

        self.btn_abrir_volumetria = tk.Button(
            acciones,
            text="ABRIR VOLUMETRIA Y REUTILIZACION DE CAJAS",
            width=43,
            height=2,
            bg="#d9eaf7",
            font=("Arial", 10, "bold"),
            command=self.abrir_volumetria_reutilizacion,
        )
        self.btn_abrir_volumetria.pack(side="left", padx=(0, 12))

        tk.Button(
            acciones,
            text="Cerrar",
            width=12,
            height=2,
            command=self.cerrar,
        ).pack(side="left")

        self.btn_limpiar_datos_cajas = tk.Button(
            contenedor,
            text="RESETEAR CALCULO / LIMPIAR PEDIDO Y CONTENEDORES",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_calculo_cajas,
        )
        self.btn_limpiar_datos_cajas.pack(fill="x", padx=16, pady=(6, 4))

        tk.Label(
            contenedor,
            text=(
                "Los ficheros importados se reutilizan en sucesivos calculos hasta que importes otros. "
                "Cada calculo de reserva empieza de nuevo con todas las matriculas disponibles."
            ),
            font=("Arial", 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=18, pady=(0, 8))

        zona_superior = tk.Frame(contenedor)
        zona_superior.pack(fill="x", padx=16, pady=(4, 7))
        zona_superior.grid_columnconfigure(0, weight=5, minsize=500)
        zona_superior.grid_columnconfigure(1, weight=6, minsize=600)

        self.crear_bloque_importaciones(zona_superior)
        self.crear_bloque_reserva(zona_superior)
        self.crear_bloque_escenarios()

    # ---------------------------------------------------------
    # Importaciones persistentes
    # ---------------------------------------------------------
    def crear_bloque_importaciones(self, contenedor=None):
        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="FICHEROS CARGADOS",
            font=("Arial", 11, "bold"),
            padx=10,
            pady=8,
        )
        marco.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        marco.grid_columnconfigure(0, weight=1)

        fila_botones = tk.Frame(marco)
        fila_botones.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        for columna in range(3):
            fila_botones.grid_columnconfigure(columna, weight=1)

        tk.Button(
            fila_botones,
            text="Importar pedido",
            command=self.importar_pedido,
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        tk.Button(
            fila_botones,
            text="Importar volumetria SKU",
            command=self.importar_volumetria,
        ).grid(row=0, column=1, padx=4, sticky="ew")
        tk.Button(
            fila_botones,
            text="Importar contenedores",
            command=self.importar_contenedores,
        ).grid(row=0, column=2, padx=(4, 0), sticky="ew")

        self.lbl_pedido = tk.Label(
            marco,
            text="Pedidos: ninguno importado",
            anchor="w",
            justify="left",
            font=("Arial", 9, "bold"),
            wraplength=510,
        )
        self.lbl_pedido.grid(row=1, column=0, sticky="ew", pady=1)

        self.crear_tabla_pedidos(marco, fila=2)

        self.lbl_volumetria = tk.Label(
            marco,
            text="Volumetria: sin cargar",
            anchor="w",
            justify="left",
            font=("Arial", 9, "bold"),
            wraplength=510,
        )
        self.lbl_volumetria.grid(row=3, column=0, sticky="ew", pady=1)

        self.lbl_contenedores = tk.Label(
            marco,
            text="Contenedores: sin cargar",
            anchor="w",
            justify="left",
            font=("Arial", 9, "bold"),
            wraplength=510,
        )
        self.lbl_contenedores.grid(row=4, column=0, sticky="ew", pady=1)

    # ---------------------------------------------------------
    # V2.1 - Lista de pedidos importados con marca de picos
    # ---------------------------------------------------------
    def crear_tabla_pedidos(self, marco, fila):
        zona = tk.Frame(marco)
        zona.grid(row=fila, column=0, sticky="ew", pady=(2, 5))
        zona.grid_columnconfigure(0, weight=1)

        contenedor_tabla = tk.Frame(zona)
        contenedor_tabla.grid(row=0, column=0, sticky="ew")
        contenedor_tabla.grid_columnconfigure(0, weight=1)

        columnas = ("Num", "Fichero", "Picos", "Tiendas", "Unidades", "Lotes", "Fecha")
        self.tabla_pedidos = ttk.Treeview(
            contenedor_tabla,
            columns=columnas,
            show="headings",
            selectmode="extended",
            height=4,
        )
        cabeceras = {
            "Num": ("N.", 34, "center"),
            "Fichero": ("FICHERO", 150, "w"),
            "Picos": ("PICOS", 52, "center"),
            "Tiendas": ("TIENDAS", 60, "e"),
            "Unidades": ("UNIDADES", 72, "e"),
            "Lotes": ("LOTES", 64, "e"),
            "Fecha": ("IMPORTADO", 120, "center"),
        }
        for columna, (texto, ancho, alineacion) in cabeceras.items():
            self.tabla_pedidos.heading(columna, text=texto)
            self.tabla_pedidos.column(
                columna,
                width=ancho,
                anchor=alineacion,
                stretch=(columna == "Fichero"),
            )
        self.tabla_pedidos.tag_configure("con_picos", background="#fff2cc")
        self.tabla_pedidos.tag_configure("sin_picos", background="#d9ead3")
        self.tabla_pedidos.grid(row=0, column=0, sticky="ew")

        scroll_y = ttk.Scrollbar(
            contenedor_tabla,
            orient="vertical",
            command=self.tabla_pedidos.yview,
        )
        scroll_y.grid(row=0, column=1, sticky="ns")
        self.tabla_pedidos.configure(yscrollcommand=scroll_y.set)

        botones = tk.Frame(zona)
        botones.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        for columna in range(3):
            botones.grid_columnconfigure(columna, weight=1)

        self.btn_cambiar_picos_pedido = tk.Button(
            botones,
            text="Cambiar picos SI/NO",
            command=self.cambiar_picos_pedido,
        )
        self.btn_cambiar_picos_pedido.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self.btn_quitar_pedido = tk.Button(
            botones,
            text="Quitar pedido seleccionado",
            command=self.quitar_pedidos_seleccionados,
        )
        self.btn_quitar_pedido.grid(row=0, column=1, padx=4, sticky="ew")
        self.btn_vaciar_pedidos = tk.Button(
            botones,
            text="Vaciar todos los pedidos",
            command=self.vaciar_pedidos,
        )
        self.btn_vaciar_pedidos.grid(row=0, column=2, padx=(4, 0), sticky="ew")

        tk.Label(
            zona,
            text=(
                "PICOS SI: sus lineas entran en el filtro 'Descartar SKU con unidades < N' "
                "(sumando todos los pedidos con picos). PICOS NO: se conservan todas sus lineas. "
                "Las tiendas fijas nunca pierden lineas."
            ),
            font=("Arial", 8),
            anchor="w",
            justify="left",
            wraplength=510,
        ).grid(row=2, column=0, sticky="ew", pady=(3, 0))

    def refrescar_tabla_pedidos(self):
        if not hasattr(self, "tabla_pedidos"):
            return
        for item in self.tabla_pedidos.get_children():
            self.tabla_pedidos.delete(item)

        try:
            pedidos = self.gestor_pedidos_cajas.obtener_pedidos()
            resumen = self.gestor_pedidos_cajas.resumen()
        except Exception as error:
            self.lbl_pedido.config(text="Pedidos: no se pudo consultar (" + str(error) + ")")
            return

        for numero, pedido in enumerate(pedidos, start=1):
            self.tabla_pedidos.insert(
                "",
                "end",
                iid=str(pedido["IdPedido"]),
                values=(
                    numero,
                    pedido["NombreArchivo"],
                    "SI" if pedido["CalcularPicos"] else "NO",
                    pedido["Tiendas"],
                    pedido["Unidades"],
                    self._formatear_lotes(pedido["Lotes"]),
                    self._formatear_fecha(pedido["FechaHora"]),
                ),
                tags=("con_picos" if pedido["CalcularPicos"] else "sin_picos",),
            )

        if resumen["Pedidos"] <= 0:
            self.lbl_pedido.config(text="Pedidos: ninguno importado")
            return

        self.lbl_pedido.config(
            text=(
                "Pedidos: " + str(resumen["Pedidos"])
                + " | con picos: " + str(resumen["ConPicos"])
                + " | sin picos: " + str(resumen["SinPicos"])
                + " | unidades: " + str(resumen["Unidades"])
                + " | lotes: " + self._formatear_lotes(resumen["Lotes"])
            )
        )

    def _ids_pedidos_seleccionados(self):
        if not hasattr(self, "tabla_pedidos"):
            return []
        return [int(item) for item in self.tabla_pedidos.selection()]

    def preguntar_calcular_picos(self, nombre_archivo, estadisticas):
        """Devuelve True (picos), False (sin picos) o None (cancelar)."""
        return messagebox.askyesnocancel(
            "Calcular picos en este pedido",
            "Pedido: " + str(nombre_archivo)
            + "\nTiendas: " + str(estadisticas.get("Tiendas", 0))
            + " | Unidades: " + str(estadisticas.get("Unidades", 0))
            + " | Lotes: " + self._formatear_lotes(estadisticas.get("Lotes", 0))
            + "\n\n¿Quieres CALCULAR PICOS en este pedido?\n\n"
            "SI: sus lineas entran en el filtro 'Descartar SKU con unidades < N'. "
            "Para saber si un SKU llega a N se suman todos los pedidos con picos.\n"
            "NO: se conservan todas las lineas de este pedido.\n\n"
            "En los dos casos las tiendas fijas conservan todas sus lineas.\n\n"
            "Cancelar: no se añade este pedido.",
            parent=self.ventana,
        )

    def cambiar_picos_pedido(self):
        ids = self._ids_pedidos_seleccionados()
        if len(ids) != 1:
            messagebox.showwarning(
                "Selecciona un pedido",
                "Selecciona un unico pedido en la lista para cambiar su marca de picos.",
                parent=self.ventana,
            )
            return
        pedido = self.gestor_pedidos_cajas.obtener_pedido(ids[0])
        if pedido is None:
            self.refrescar_tabla_pedidos()
            return
        nuevo = not pedido["CalcularPicos"]
        if not messagebox.askyesno(
            "Cambiar picos",
            "Pedido: " + pedido["NombreArchivo"]
            + "\n\nPicos actual: " + ("SI" if pedido["CalcularPicos"] else "NO")
            + "\nPicos nuevo: " + ("SI" if nuevo else "NO")
            + "\n\nSe invalidara el calculo actual. ¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_pedidos_cajas.cambiar_picos(ids[0], nuevo)
            self.invalidar_resultados("ha cambiado la marca de picos de un pedido")
            self.cargar_estado_importaciones()
        except Exception as error:
            messagebox.showerror("Error cambiando picos", str(error), parent=self.ventana)

    def quitar_pedidos_seleccionados(self):
        ids = self._ids_pedidos_seleccionados()
        if not ids:
            messagebox.showwarning(
                "Selecciona un pedido",
                "Selecciona en la lista el pedido o pedidos que quieres quitar.",
                parent=self.ventana,
            )
            return
        nombres = []
        for id_pedido in ids:
            pedido = self.gestor_pedidos_cajas.obtener_pedido(id_pedido)
            if pedido is not None:
                nombres.append("- " + pedido["NombreArchivo"])
        if not messagebox.askyesno(
            "Quitar pedidos",
            "Se quitaran de Calculo de cajas:\n\n" + "\n".join(nombres)
            + "\n\nSe invalidara el calculo actual. ¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_pedidos_cajas.eliminar(ids)
            self.invalidar_resultados("se han quitado pedidos")
            self.cargar_estado_importaciones()
            self.cargar_tiendas_fijas(invalidar=False)
        except Exception as error:
            messagebox.showerror("Error quitando pedidos", str(error), parent=self.ventana)

    def vaciar_pedidos(self):
        if self.gestor_pedidos_cajas.resumen()["Pedidos"] <= 0:
            return
        if not messagebox.askyesno(
            "Vaciar pedidos",
            "Se quitaran TODOS los pedidos importados en Calculo de cajas.\n\n"
            "Contenedores, volumetria, grupos y tiendas fijas se conservan.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_pedidos_cajas.vaciar()
            self.invalidar_resultados("se han vaciado los pedidos")
            self.cargar_estado_importaciones()
            self.cargar_tiendas_fijas(invalidar=False)
        except Exception as error:
            messagebox.showerror("Error vaciando pedidos", str(error), parent=self.ventana)

    def _formatear_fecha(self, fecha):
        texto = str(fecha or "").strip()
        if len(texto) >= 19 and texto[4] == "-":
            return texto[8:10] + "/" + texto[5:7] + "/" + texto[0:4] + " " + texto[11:19]
        return texto or "no registrada"

    def _nombre_archivo(self, ruta):
        if not ruta:
            return "ruta no registrada"
        try:
            return Path(ruta).name
        except Exception:
            return str(ruta)

    def cargar_estado_importaciones(self):
        metadatos = self.registro_importaciones.todos()

        volum_count = self.contar_tabla("CAJAS_VOLUMETRIA")
        cont_count = self.contar_tabla("CAJAS_CONTENEDORES")
        disponibles = self.contar_contenedores_disponibles()

        self.refrescar_tabla_pedidos()
        self.lbl_volumetria.config(text=self._texto_estado_importacion("VOLUMETRIA", metadatos.get("VOLUMETRIA"), volum_count))
        self.lbl_contenedores.config(
            text=self._texto_estado_importacion("CONTENEDORES", metadatos.get("CONTENEDORES"), cont_count, " | disponibles: " + str(disponibles))
        )

    def _texto_estado_importacion(self, tipo, info, registros_actuales, extra=""):
        if registros_actuales <= 0:
            return tipo.title() + ": sin cargar"
        if info:
            return (
                tipo.title() + ": " + self._nombre_archivo(info.get("Ruta")) +
                " | ultima: " + self._formatear_fecha(info.get("FechaHora")) + extra
            )
        return tipo.title() + ": datos disponibles | ultima importacion no registrada" + extra

    def invalidar_resultados(self, motivo="", conservar_escenario_global=True):
        """Invalida solo el calculo local del formulario.

        El ultimo escenario que el operador ya selecciono es una fotografia
        autonoma y valida para los demas formularios. No debe desaparecer por
        cambiar un parametro, importar otro fichero o iniciar un nuevo calculo.
        Solo se sustituye cuando se guarda correctamente otra seleccion.
        """
        self.resumen_cajas = None
        self.resumen_paises = None
        self.cajas_400_agotadas = 0
        self.resultados_escenarios = {}
        self.escenarios_calculados = False
        self.escenario_activo = CalculadorEscenariosCajas.escenario_todo()
        self.resultado_escenario_activo = None
        if not conservar_escenario_global:
            try:
                self.gestor_pedido_escenario.limpiar()
            except Exception:
                pass

        if hasattr(self, "btn_exportar_resultados"):
            self.btn_exportar_resultados.config(state="disabled")
        if hasattr(self, "btn_usar_escenario"):
            self.btn_usar_escenario.config(state="disabled")

        self.lbl_reserva_total.config(text="CAJAS XDOC: -")
        self.lbl_agotadas.config(text="CAJAS PARA CARRUSELES: -")
        self.lbl_total_general.config(text="TOTAL CAJAS RESERVADAS: -")

        if hasattr(self, "lbl_filtro_sku"):
            texto = "Filtro SKU: pendiente de calcular."
            if motivo:
                texto += " Motivo: " + str(motivo)
            self.lbl_filtro_sku.config(text=texto, fg="#9c6500")
        if hasattr(self, "lbl_escenario_activo"):
            texto_estado = "Escenario local: TODO - pendiente de calcular"
            try:
                estado_guardado = self.gestor_pedido_escenario.obtener_estado()
            except Exception:
                estado_guardado = None
            if estado_guardado and estado_guardado.get("Disponible"):
                texto_estado += (
                    "\nUltimo escenario global conservado: "
                    + str(estado_guardado.get("Grupo", ""))
                    + " - "
                    + str(estado_guardado.get("Descripcion", ""))
                    + ". Sigue disponible en los formularios de reparto."
                )
            self.lbl_escenario_activo.config(
                text=texto_estado,
                fg="#9c6500",
            )
            if hasattr(self, "lbl_escenario_descartado"):
                self.lbl_escenario_descartado.config(text="")
        if hasattr(self, "lbl_progreso_escenarios"):
            self.lbl_progreso_escenarios.config(text="")
        if hasattr(self, "tabla_escenarios"):
            self.refrescar_tabla_escenarios()
        if hasattr(self, "tabla_tiendas_fijas"):
            self.refrescar_tiendas_fijas()

        self.actualizar_estado_volumetria()

        ventana = self.ventana_volumetria
        if ventana is not None:
            try:
                if int(ventana.ventana.winfo_exists()) == 1:
                    ventana.invalidar_resultados()
            except Exception:
                self.ventana_volumetria = None

    def _al_cambiar_parametros_calculo(self, *_args):
        if self._suspendiendo_invalidacion:
            return
        self.invalidar_resultados(
            "ha cambiado el modo de calculo o el umbral de unidades"
        )

    def importar_pedido(self):
        """V2.1: cada pedido importado se AÑADE a los anteriores.

        Tras leer el fichero se pregunta si ese pedido calcula picos. La
        respuesta se guarda en cada una de sus lineas.
        """
        try:
            importador = ImportadorPedidos(parent=self.ventana)
            tipo = importador.importar()
            if tipo is None:
                return

            nombre_archivo = (
                importador.ruta.name
                if getattr(importador, "ruta", None) is not None
                else str(tipo)
            )
            estadisticas = self.gestor_pedidos_cajas.estadisticas_estarepp()
            if estadisticas["Registros"] <= 0:
                messagebox.showwarning(
                    "Pedido vacio",
                    "El fichero no contiene lineas de pedido. No se ha añadido.",
                    parent=self.ventana,
                )
                return

            duplicado = self.gestor_pedidos_cajas.buscar_duplicado(
                nombre_archivo, estadisticas
            )
            if duplicado is not None and not messagebox.askyesno(
                "Pedido ya importado",
                "El fichero " + nombre_archivo
                + " ya esta en la lista con las mismas lineas y unidades "
                + "(importado " + self._formatear_fecha(duplicado["FechaHora"]) + ").\n\n"
                + "Si lo añades otra vez, sus unidades se sumaran dos veces.\n\n"
                + "¿Añadirlo de todas formas?",
                parent=self.ventana,
            ):
                return

            calcular_picos = self.preguntar_calcular_picos(nombre_archivo, estadisticas)
            if calcular_picos is None:
                messagebox.showinfo(
                    "Pedido no añadido",
                    "Importacion cancelada. La lista de pedidos no ha cambiado.",
                    parent=self.ventana,
                )
                return

            pedido = self.gestor_pedidos_cajas.anadir_desde_estarepp(
                nombre_archivo=nombre_archivo,
                ruta=importador.ruta,
                tipo_fichero=tipo,
                calcular_picos=bool(calcular_picos),
            )
            self.tipo_pedido = tipo
            self.registro_importaciones.guardar(
                "PEDIDO", importador.ruta, estadisticas["Registros"], tipo
            )
            self.invalidar_resultados("se ha añadido un pedido")
            self.cargar_estado_importaciones()
            self.cargar_tiendas_fijas(invalidar=False)

            resumen = self.gestor_pedidos_cajas.resumen()
            messagebox.showinfo(
                "Pedido añadido",
                "Pedido añadido: " + pedido["NombreArchivo"]
                + "\nPicos: " + ("SI" if pedido["CalcularPicos"] else "NO")
                + "\n\nPedidos en Calculo de cajas: " + str(resumen["Pedidos"])
                + " (con picos: " + str(resumen["ConPicos"])
                + ", sin picos: " + str(resumen["SinPicos"]) + ")"
                + "\nUnidades totales: " + str(resumen["Unidades"]),
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror("Error importando pedido", str(error), parent=self.ventana)

    def importar_volumetria(self):
        try:
            importador = ImportarVolumetriaCajas()
            registros = importador.importar()
            if registros <= 0:
                return
            self.registro_importaciones.guardar("VOLUMETRIA", importador.ruta, registros, "Volumetria SKU")
            self.invalidar_resultados()
            self.cargar_estado_importaciones()
            messagebox.showinfo("Volumetria importada", "Volumetria importada correctamente.", parent=self.ventana)
        except Exception as error:
            messagebox.showerror("Error importando volumetria", str(error), parent=self.ventana)

    def importar_contenedores(self):
        try:
            importador = ImportarContenedoresCajas()
            registros = importador.importar()
            if registros <= 0:
                return
            disponibles = self.contar_contenedores_disponibles()
            self.registro_importaciones.guardar(
                "CONTENEDORES", importador.ruta, registros, "Disponibles: " + str(disponibles)
            )
            self.invalidar_resultados()
            self.cargar_estado_importaciones()
            messagebox.showinfo("Contenedores importados", "Contenedores importados correctamente.", parent=self.ventana)
        except Exception as error:
            messagebox.showerror("Error importando contenedores", str(error), parent=self.ventana)

    def _tabla_existe(self, tabla):
        try:
            filas = self.bd.consultar(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='"
                + str(tabla).replace("'", "''")
                + "'"
            )
            return bool(filas)
        except Exception:
            return False

    def _vaciar_si_existe(self, tabla):
        if not self._tabla_existe(tabla):
            return False
        self.bd.ejecutar("DELETE FROM " + tabla)
        return True

    def resetear_calculo_cajas(self):
        """Resetea pedido, contenedores y resultados sin borrar volumetria SKU."""
        if not messagebox.askyesno(
            "Resetear calculo de cajas",
            "Se eliminaran del formulario de calculo de cajas:\n\n"
            "- Todos los pedidos importados\n"
            "- Contenedores importados\n"
            "- Resultados de cajas y escenario global derivado\n\n"
            "La volumetria SKU se conserva y solo se sustituira cuando importes otro fichero.\n\n"
            "No se borraran maestros, GRUTIEP, grupos de simulacion ni tiendas fijas.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return

        try:
            GestorResetCalculos(self.bd.conexion).resetear_calculo_cajas(
                conservar_volumetria=True
            )

            self.tipo_pedido = None
            self.resumen_cajas = None
            self.resumen_paises = None
            self.cajas_400_agotadas = 0
            self.resultados_escenarios = {}
            self.escenarios_calculados = False
            self.escenario_activo = CalculadorEscenariosCajas.escenario_todo()
            self.resultado_escenario_activo = None

            self.invalidar_resultados(
                "se han limpiado pedido, contenedores y resultados",
                conservar_escenario_global=False,
            )
            self.cargar_estado_importaciones()
            self.cargar_tiendas_fijas(invalidar=False)
            self.refrescar_tabla_escenarios()
            try:
                self.actualizar_estado_volumetria()
            except Exception:
                pass

            messagebox.showinfo(
                "Reset finalizado",
                "Pedido, contenedores y resultados dependientes se han limpiado correctamente.\n\n"
                "La volumetria SKU se conserva hasta que importes otro fichero de volumetria.\n"
                "Los maestros, GRUTIEP, grupos de calculo y tiendas fijas se conservan.",
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error reseteando calculo",
                str(error),
                parent=self.ventana,
            )

    # Compatibilidad con accesos antiguos al metodo de limpieza.
    def limpiar_pedido_contenedores_volumetria(self):
        self.resetear_calculo_cajas()

    # ---------------------------------------------------------
    # BLOQUE 2 - Escenarios por grupos de tiendas
    # ---------------------------------------------------------
    def crear_bloque_escenarios(self):
        marco = tk.LabelFrame(
            getattr(self, "contenedor_principal", self.ventana),
            text="2. ESCENARIOS POR GRUPOS DE TIENDAS",
            font=("Arial", 12, "bold"),
            padx=10,
            pady=8,
        )
        marco.pack(fill="both", expand=True, padx=16, pady=(7, 12))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(3, weight=1)

        fila_acciones = tk.Frame(marco)
        fila_acciones.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        fila_acciones.grid_columnconfigure(2, weight=1)

        self.btn_importar_grupos = tk.Button(
            fila_acciones,
            text="IMPORTAR GRUPOS",
            width=19,
            height=2,
            command=self.importar_grupos_calculo,
        )
        self.btn_importar_grupos.grid(row=0, column=0, padx=(0, 6))

        self.btn_limpiar_grupos = tk.Button(
            fila_acciones,
            text="LIMPIAR GRUPOS",
            width=18,
            height=2,
            command=self.limpiar_grupos_calculo,
        )
        self.btn_limpiar_grupos.grid(row=0, column=1, padx=(0, 10))

        self.lbl_estado_grupos = tk.Label(
            fila_acciones,
            text="Grupos de calculo: ninguno importado",
            font=("Arial", 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_estado_grupos.grid(row=0, column=2, sticky="ew", padx=(0, 12))

        tk.Label(
            fila_acciones,
            text="Descartar SKU con unidades <",
            font=("Arial", 9, "bold"),
        ).grid(row=0, column=3, padx=(0, 5))

        self.entry_umbral_sku = tk.Entry(
            fila_acciones,
            textvariable=self.umbral_sku_var,
            width=8,
            justify="center",
            font=("Arial", 11, "bold"),
        )
        self.entry_umbral_sku.grid(row=0, column=4, padx=(0, 10))

        self.btn_calcular_escenarios = tk.Button(
            fila_acciones,
            text="CALCULAR ESCENARIOS",
            width=23,
            height=2,
            bg="#d9ead3",
            font=("Arial", 10, "bold"),
            command=self.calcular_escenarios,
        )
        self.btn_calcular_escenarios.grid(row=0, column=5)

        self.crear_cuadro_tiendas_fijas(marco)

        fila_info = tk.Frame(marco)
        fila_info.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        fila_info.grid_columnconfigure(0, weight=1)

        self.lbl_filtro_sku = tk.Label(
            fila_info,
            text="Filtro SKU: pendiente de calcular.",
            font=("Arial", 9, "bold"),
            fg="#9c6500",
            anchor="w",
            justify="left",
            wraplength=1120,
        )
        self.lbl_filtro_sku.grid(row=0, column=0, sticky="ew")

        self.lbl_progreso_escenarios = tk.Label(
            fila_info,
            text="",
            font=("Arial", 9, "bold"),
            anchor="e",
        )
        self.lbl_progreso_escenarios.grid(row=0, column=1, sticky="e")

        contenedor_tabla = tk.Frame(marco, bd=1, relief="sunken")
        contenedor_tabla.grid(row=3, column=0, sticky="nsew", pady=(2, 7))
        contenedor_tabla.grid_columnconfigure(0, weight=1)
        contenedor_tabla.grid_rowconfigure(0, weight=1)

        columnas = (
            "Grupo",
            "Descripcion",
            "Lotes",
            "Unidades",
            "CajasXDC",
            "CajasSilo",
        )
        self.tabla_escenarios = ttk.Treeview(
            contenedor_tabla,
            columns=columnas,
            show="headings",
            selectmode="browse",
            height=8,
        )
        self.tabla_escenarios.heading("Grupo", text="GRUPO")
        self.tabla_escenarios.heading("Descripcion", text="DESCRIPCION")
        self.tabla_escenarios.heading("Lotes", text="LOTES")
        self.tabla_escenarios.heading("Unidades", text="UNIDADES")
        self.tabla_escenarios.heading("CajasXDC", text="CAJAS XDC")
        self.tabla_escenarios.heading("CajasSilo", text="CAJAS SILO")
        self.tabla_escenarios.column("Grupo", width=105, anchor="center", stretch=False)
        self.tabla_escenarios.column("Descripcion", width=430, anchor="w")
        self.tabla_escenarios.column("Lotes", width=115, anchor="e", stretch=False)
        self.tabla_escenarios.column("Unidades", width=125, anchor="e", stretch=False)
        self.tabla_escenarios.column("CajasXDC", width=115, anchor="e", stretch=False)
        self.tabla_escenarios.column("CajasSilo", width=115, anchor="e", stretch=False)
        self.tabla_escenarios.tag_configure("activo", background="#d9ead3")
        self.tabla_escenarios.bind(
            "<<TreeviewSelect>>", self._al_seleccionar_escenario
        )

        scroll_y = ttk.Scrollbar(
            contenedor_tabla,
            orient="vertical",
            command=self.tabla_escenarios.yview,
        )
        self.tabla_escenarios.configure(yscrollcommand=scroll_y.set)
        self.tabla_escenarios.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        fila_final = tk.Frame(marco)
        fila_final.grid(row=4, column=0, sticky="ew")
        fila_final.grid_columnconfigure(1, weight=1)

        self.btn_usar_escenario = tk.Button(
            fila_final,
            text="USAR ESCENARIO SELECCIONADO",
            width=31,
            height=2,
            bg="#fce5cd",
            font=("Arial", 10, "bold"),
            state="disabled",
            command=self.usar_escenario_seleccionado,
        )
        self.btn_usar_escenario.grid(row=0, column=0, padx=(0, 12))

        marco_estado_escenario = tk.Frame(fila_final)
        marco_estado_escenario.grid(row=0, column=1, sticky="ew")
        marco_estado_escenario.grid_columnconfigure(0, weight=1)

        self.lbl_escenario_activo = tk.Label(
            marco_estado_escenario,
            text="Escenario activo: TODO - pendiente de calcular",
            font=("Arial", 10, "bold"),
            fg="#9c6500",
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.lbl_escenario_activo.grid(row=0, column=0, sticky="ew")

        self.lbl_escenario_descartado = tk.Label(
            marco_estado_escenario,
            text="",
            font=("Arial", 10, "bold"),
            fg="#990000",
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.lbl_escenario_descartado.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.lbl_escenario_seleccionado = tk.Label(
            fila_final,
            text="Seleccionado: TODO",
            font=("Arial", 9),
            anchor="e",
        )
        self.lbl_escenario_seleccionado.grid(row=0, column=2, sticky="e")

    def crear_cuadro_tiendas_fijas(self, contenedor):
        marco = tk.LabelFrame(
            contenedor,
            text="TIENDAS FIJAS - FUERA DEL CALCULO DE PICOS",
            font=("Arial", 10, "bold"),
            padx=8,
            pady=6,
        )
        marco.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        marco.grid_columnconfigure(0, weight=3)
        marco.grid_columnconfigure(1, weight=4)

        contenedor_tabla = tk.Frame(marco, bd=1, relief="sunken")
        contenedor_tabla.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        contenedor_tabla.grid_columnconfigure(0, weight=1)
        contenedor_tabla.grid_rowconfigure(0, weight=1)

        columnas = ("Tienda", "Nombre", "Pedido")
        self.tabla_tiendas_fijas = ttk.Treeview(
            contenedor_tabla,
            columns=columnas,
            show="headings",
            selectmode="extended",
            height=4,
        )
        self.tabla_tiendas_fijas.heading("Tienda", text="TIENDA")
        self.tabla_tiendas_fijas.heading("Nombre", text="NOMBRE")
        self.tabla_tiendas_fijas.heading("Pedido", text="EN PEDIDO")
        self.tabla_tiendas_fijas.column(
            "Tienda", width=90, anchor="center", stretch=False
        )
        self.tabla_tiendas_fijas.column("Nombre", width=285, anchor="w")
        self.tabla_tiendas_fijas.column(
            "Pedido", width=90, anchor="center", stretch=False
        )
        self.tabla_tiendas_fijas.grid(row=0, column=0, sticky="nsew")
        self.tabla_tiendas_fijas.bind(
            "<Double-1>", lambda _evento: self.editar_tienda_fija()
        )
        self.tabla_tiendas_fijas.bind(
            "<Delete>", lambda _evento: self.eliminar_tiendas_fijas()
        )

        scroll_y = ttk.Scrollbar(
            contenedor_tabla,
            orient="vertical",
            command=self.tabla_tiendas_fijas.yview,
        )
        self.tabla_tiendas_fijas.configure(yscrollcommand=scroll_y.set)
        scroll_y.grid(row=0, column=1, sticky="ns")

        zona_info = tk.Frame(marco)
        zona_info.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        zona_info.grid_columnconfigure(0, weight=1)

        tk.Label(
            zona_info,
            text=(
                "Estas tiendas conservan todo su pedido frente al umbral de picos. "
                "Sus unidades no se suman para decidir los SKU normales. Si una "
                "tienda fija pertenece al grupo calculado, se elimina de ese escenario."
            ),
            font=("Arial", 9),
            anchor="w",
            justify="left",
            wraplength=500,
        ).grid(row=0, column=0, sticky="ew")

        self.lbl_estado_tiendas_fijas = tk.Label(
            zona_info,
            text="Tiendas fijas: cargando...",
            font=("Arial", 9, "bold"),
            fg="#1f4e78",
            anchor="w",
            justify="left",
        )
        self.lbl_estado_tiendas_fijas.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        zona_botones = tk.Frame(marco)
        zona_botones.grid(row=0, column=2, rowspan=2, sticky="ns")
        for columna in range(2):
            zona_botones.grid_columnconfigure(columna, weight=1)

        self.btn_anadir_tiendas_fijas = tk.Button(
            zona_botones,
            text="AÑADIR / PEGAR",
            width=18,
            command=self.anadir_tiendas_fijas,
        )
        self.btn_anadir_tiendas_fijas.grid(row=0, column=0, padx=(0, 4), pady=(0, 4))

        self.btn_editar_tienda_fija = tk.Button(
            zona_botones,
            text="EDITAR SELECCIONADA",
            width=20,
            command=self.editar_tienda_fija,
        )
        self.btn_editar_tienda_fija.grid(row=0, column=1, padx=(4, 0), pady=(0, 4))

        self.btn_eliminar_tiendas_fijas = tk.Button(
            zona_botones,
            text="ELIMINAR SELECCION",
            width=18,
            command=self.eliminar_tiendas_fijas,
        )
        self.btn_eliminar_tiendas_fijas.grid(row=1, column=0, padx=(0, 4), pady=4)

        self.btn_reemplazar_tiendas_fijas = tk.Button(
            zona_botones,
            text="REEMPLAZAR LISTA",
            width=20,
            command=self.reemplazar_tiendas_fijas,
        )
        self.btn_reemplazar_tiendas_fijas.grid(row=1, column=1, padx=(4, 0), pady=4)

        self.btn_vaciar_tiendas_fijas = tk.Button(
            zona_botones,
            text="VACIAR LISTA",
            width=18,
            command=self.vaciar_tiendas_fijas,
        )
        self.btn_vaciar_tiendas_fijas.grid(row=2, column=0, columnspan=2, pady=(4, 0))

    def cargar_tiendas_fijas(self, invalidar=False, motivo=""):
        self.tiendas_fijas = set(self.gestor_tiendas_fijas.obtener_tiendas())
        self.refrescar_tiendas_fijas()
        if invalidar:
            self.invalidar_resultados(
                motivo or "ha cambiado la lista de tiendas fijas"
            )

    def refrescar_tiendas_fijas(self):
        if not hasattr(self, "tabla_tiendas_fijas"):
            return

        seleccion_anterior = set(self.tabla_tiendas_fijas.selection())
        for item in self.tabla_tiendas_fijas.get_children():
            self.tabla_tiendas_fijas.delete(item)

        detalles = self.gestor_tiendas_fijas.obtener_detalle()
        presentes = 0
        for detalle in detalles:
            tienda = int(detalle["Tienda"])
            en_pedido = bool(detalle.get("EnPedido"))
            if en_pedido:
                presentes += 1
            nombre = str(detalle.get("Nombre", "") or "").strip()
            if nombre == "":
                nombre = "(NO ENCONTRADA EN TIENDAS_WEB)"
            self.tabla_tiendas_fijas.insert(
                "",
                "end",
                iid=str(tienda),
                values=(tienda, nombre, "SI" if en_pedido else "NO"),
            )

        for item in seleccion_anterior:
            if self.tabla_tiendas_fijas.exists(item):
                self.tabla_tiendas_fijas.selection_add(item)

        self.lbl_estado_tiendas_fijas.config(
            text=(
                "Tiendas fijas configuradas: "
                + str(len(detalles))
                + " | presentes en el pedido actual: "
                + str(presentes)
                + " | fuera del filtro de picos"
            )
        )

    def _seleccion_tiendas_fijas(self):
        resultado = []
        for item in self.tabla_tiendas_fijas.selection():
            try:
                resultado.append(int(item))
            except Exception:
                continue
        return sorted(set(resultado))

    def _cerrar_editor_tiendas_fijas(self, ventana):
        try:
            ventana.grab_release()
        except Exception:
            pass
        try:
            ventana.destroy()
        except Exception:
            pass
        try:
            self.ventana.lift()
            self.ventana.focus_force()
        except Exception:
            pass

    def _abrir_editor_lista_tiendas_fijas(self, modo):
        reemplazar = str(modo).lower() == "reemplazar"
        editor = tk.Toplevel(self.ventana)
        editor._mantener_topmost = True
        editor.withdraw()
        editor.title(
            "Reemplazar tiendas fijas" if reemplazar else "Añadir tiendas fijas"
        )
        editor.resizable(True, True)
        try:
            editor.transient(self.ventana)
        except Exception:
            pass

        marco = tk.Frame(editor, padx=16, pady=14)
        marco.pack(fill="both", expand=True)

        tk.Label(
            marco,
            text=(
                "Pega los codigos de tienda desde Excel, uno por linea o separados "
                "por espacios, tabuladores, comas o punto y coma."
                + (
                    "\n\nLa lista actual se sustituira completamente."
                    if reemplazar
                    else "\n\nLas tiendas nuevas se añadiran a la lista actual."
                )
            ),
            font=("Arial", 10),
            justify="left",
            anchor="w",
            wraplength=590,
        ).pack(fill="x", pady=(0, 10))

        texto = tk.Text(marco, width=72, height=14, font=("Consolas", 11))
        texto.pack(fill="both", expand=True, pady=(0, 12))
        if reemplazar:
            texto.insert(
                "1.0",
                "\n".join(str(tienda) for tienda in sorted(self.tiendas_fijas)),
            )
            texto.tag_add("sel", "1.0", "end-1c")

        resultado = {"guardado": False}

        def aceptar():
            try:
                tiendas = self.gestor_tiendas_fijas.analizar_texto(
                    texto.get("1.0", "end")
                )
                if not tiendas:
                    raise ErrorTiendasFijas(
                        "Debes introducir al menos un codigo de tienda. "
                        "Para dejar la lista vacia utiliza VACIAR LISTA."
                    )
                if reemplazar:
                    self.gestor_tiendas_fijas.reemplazar(tiendas)
                else:
                    self.gestor_tiendas_fijas.anadir(tiendas)
                resultado["guardado"] = True
                self._cerrar_editor_tiendas_fijas(editor)
            except ErrorTiendasFijas as error:
                messagebox.showerror(
                    "Tiendas no validas", str(error), parent=editor
                )
            except Exception as error:
                messagebox.showerror(
                    "Error guardando tiendas fijas", str(error), parent=editor
                )

        botones = tk.Frame(marco)
        botones.pack(fill="x")
        tk.Button(
            botones,
            text="Cancelar",
            width=14,
            command=lambda: self._cerrar_editor_tiendas_fijas(editor),
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            botones,
            text="Guardar",
            width=14,
            bg="#d9ead3",
            font=("Arial", 9, "bold"),
            command=aceptar,
        ).pack(side="right")

        editor.protocol(
            "WM_DELETE_WINDOW", lambda: self._cerrar_editor_tiendas_fijas(editor)
        )
        editor.bind(
            "<Escape>", lambda _evento: self._cerrar_editor_tiendas_fijas(editor)
        )

        editor.update_idletasks()
        ancho = max(680, editor.winfo_reqwidth())
        alto = max(430, editor.winfo_reqheight())
        try:
            x = self.ventana.winfo_rootx() + max(
                0, (self.ventana.winfo_width() - ancho) // 2
            )
            y = self.ventana.winfo_rooty() + max(
                0, (self.ventana.winfo_height() - alto) // 2
            )
        except Exception:
            x = 100
            y = 100
        editor.geometry(str(ancho) + "x" + str(alto) + "+" + str(x) + "+" + str(y))
        editor.deiconify()
        try:
            editor.grab_set()
        except Exception:
            pass
        forzar_ventana_visible(
            editor,
            parent=self.ventana,
            mantener_arriba=True,
            focus_widget=texto,
        )
        try:
            texto.focus_force()
            if reemplazar:
                texto.tag_add("sel", "1.0", "end-1c")
        except Exception:
            pass
        editor.wait_window()

        if resultado["guardado"]:
            self.cargar_tiendas_fijas(
                invalidar=True,
                motivo="ha cambiado la lista de tiendas fijas",
            )

    def anadir_tiendas_fijas(self):
        self._abrir_editor_lista_tiendas_fijas("anadir")

    def reemplazar_tiendas_fijas(self):
        self._abrir_editor_lista_tiendas_fijas("reemplazar")

    def editar_tienda_fija(self):
        seleccion = self._seleccion_tiendas_fijas()
        if len(seleccion) != 1:
            messagebox.showwarning(
                "Selecciona una tienda",
                "Selecciona exactamente una tienda fija para modificarla.",
                parent=self.ventana,
            )
            return
        anterior = seleccion[0]
        nueva = simpledialog.askinteger(
            "Editar tienda fija",
            "Nuevo codigo para la tienda fija " + str(anterior) + ":",
            initialvalue=anterior,
            minvalue=1,
            parent=self.ventana,
        )
        if nueva is None:
            return
        try:
            cambiado = self.gestor_tiendas_fijas.cambiar(anterior, nueva)
            if cambiado:
                self.cargar_tiendas_fijas(
                    invalidar=True,
                    motivo="se ha modificado una tienda fija",
                )
        except ErrorTiendasFijas as error:
            messagebox.showerror(
                "Tienda no valida", str(error), parent=self.ventana
            )
        except Exception as error:
            messagebox.showerror(
                "Error modificando tienda fija", str(error), parent=self.ventana
            )

    def eliminar_tiendas_fijas(self):
        seleccion = self._seleccion_tiendas_fijas()
        if not seleccion:
            messagebox.showwarning(
                "Sin seleccion",
                "Selecciona una o varias tiendas fijas para eliminarlas.",
                parent=self.ventana,
            )
            return
        if not messagebox.askyesno(
            "Eliminar tiendas fijas",
            "Se eliminaran de la lista de tiendas fuera de picos:\n\n"
            + ", ".join(str(tienda) for tienda in seleccion)
            + "\n\nDebes recalcular los escenarios despues del cambio.\n\n¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_tiendas_fijas.eliminar(seleccion)
            self.cargar_tiendas_fijas(
                invalidar=True,
                motivo="se han eliminado tiendas fijas",
            )
        except Exception as error:
            messagebox.showerror(
                "Error eliminando tiendas fijas", str(error), parent=self.ventana
            )

    def vaciar_tiendas_fijas(self):
        if not self.tiendas_fijas:
            messagebox.showinfo(
                "Lista vacia",
                "No hay tiendas fijas configuradas.",
                parent=self.ventana,
            )
            return
        if not messagebox.askyesno(
            "Vaciar tiendas fijas",
            "Se eliminara toda la lista de tiendas fuera del calculo de picos.\n\n"
            "La lista inicial no se volvera a crear automaticamente.\n"
            "Debes recalcular los escenarios despues del cambio.\n\n¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_tiendas_fijas.vaciar()
            self.cargar_tiendas_fijas(
                invalidar=True,
                motivo="se ha vaciado la lista de tiendas fijas",
            )
        except Exception as error:
            messagebox.showerror(
                "Error vaciando tiendas fijas", str(error), parent=self.ventana
            )

    def cargar_grupos_calculo(self):
        self.grupos_calculo = self.gestor_grupos_calculo.obtener_grupos()
        self.estado_grupos_calculo = self.gestor_grupos_calculo.obtener_estado()
        self._actualizar_texto_estado_grupos()
        self.refrescar_tabla_escenarios()

    def _actualizar_texto_estado_grupos(self):
        info = self.estado_grupos_calculo
        if not info or not self.grupos_calculo:
            self.lbl_estado_grupos.config(
                text="Grupos de calculo: ninguno importado. Solo se calculara TODO."
            )
            return
        self.lbl_estado_grupos.config(
            text=(
                "Fichero: "
                + str(info.get("NombreArchivo", ""))
                + " | ultima: "
                + self._formatear_fecha(info.get("FechaHora"))
                + " | grupos: "
                + str(info.get("Grupos", 0))
                + " | tiendas unicas: "
                + str(info.get("Tiendas", 0))
            )
        )

    def importar_grupos_calculo(self):
        ruta = filedialog.askopenfilename(
            parent=self.ventana,
            title="Importar grupos para el calculo de cajas",
            filetypes=[
                ("Ficheros TXT", "*.txt"),
                ("Todos los ficheros", "*.*"),
            ],
        )
        if not ruta:
            return
        try:
            info = self.gestor_grupos_calculo.importar(ruta)
            self.grupos_calculo = self.gestor_grupos_calculo.obtener_grupos()
            self.estado_grupos_calculo = info
            self.invalidar_resultados("se ha importado un nuevo fichero de grupos")
            self._actualizar_texto_estado_grupos()
            self.refrescar_tabla_escenarios()
            messagebox.showinfo(
                "Grupos importados",
                "Fichero importado correctamente.\n\n"
                + "Grupos: "
                + str(info.get("Grupos", 0))
                + "\nTiendas unicas: "
                + str(info.get("Tiendas", 0))
                + "\n\nCada grupo se calculara por separado.",
                parent=self.ventana,
            )
        except ErrorGruposCalculo as error:
            messagebox.showerror(
                "Fichero de grupos no valido", str(error), parent=self.ventana
            )
        except Exception as error:
            messagebox.showerror(
                "Error importando grupos", str(error), parent=self.ventana
            )

    def limpiar_grupos_calculo(self):
        if not self.grupos_calculo:
            messagebox.showinfo(
                "Sin grupos",
                "No hay grupos de calculo cargados. El escenario disponible es TODO.",
                parent=self.ventana,
            )
            return
        if not messagebox.askyesno(
            "Limpiar grupos",
            "Se eliminaran los grupos usados para estas simulaciones.\n\n"
            "No se modificara el GRUTIEP general de validacion.\n"
            "Permanecera solamente el escenario TODO.\n\n¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            self.gestor_grupos_calculo.limpiar()
            self.grupos_calculo = []
            self.estado_grupos_calculo = None
            self.invalidar_resultados("se han limpiado los grupos")
            self._actualizar_texto_estado_grupos()
            self.refrescar_tabla_escenarios()
        except Exception as error:
            messagebox.showerror(
                "Error limpiando grupos", str(error), parent=self.ventana
            )

    def obtener_umbral_sku(self, mostrar_error=True):
        texto = str(self.umbral_sku_var.get() or "").strip()
        try:
            valor = int(texto)
        except Exception:
            valor = -1
        if valor < 0:
            if mostrar_error:
                messagebox.showerror(
                    "Umbral no valido",
                    "El limite de unidades por SKU debe ser un entero mayor o igual que cero.\n\n"
                    "Se descartan solo los SKU cuyo total inicial sea estrictamente menor que el limite.",
                    parent=self.ventana,
                )
                try:
                    self.entry_umbral_sku.focus_force()
                    self.entry_umbral_sku.selection_range(0, "end")
                except Exception:
                    pass
            return None
        return valor

    @staticmethod
    def _formatear_lotes(valor):
        numero = float(valor or 0.0)
        texto = format(numero, ".2f")
        return texto.rstrip("0").rstrip(".") if "." in texto else texto

    def _lista_escenarios(self):
        return [CalculadorEscenariosCajas.escenario_todo()] + list(
            self.grupos_calculo or []
        )

    def _escenario_por_clave(self, clave):
        for escenario in self._lista_escenarios():
            if str(escenario.get("Clave")) == str(clave):
                return escenario
        return CalculadorEscenariosCajas.escenario_todo()

    def _clave_seleccionada(self):
        seleccion = self.tabla_escenarios.selection()
        if not seleccion:
            return CalculadorEscenariosCajas.CLAVE_TODO
        return str(seleccion[0])

    def refrescar_tabla_escenarios(self):
        if not hasattr(self, "tabla_escenarios"):
            return
        seleccion_anterior = self._clave_seleccionada()
        for item in self.tabla_escenarios.get_children():
            self.tabla_escenarios.delete(item)

        clave_activa = str(
            (self.escenario_activo or {}).get(
                "Clave", CalculadorEscenariosCajas.CLAVE_TODO
            )
        )
        claves_disponibles = []
        for escenario in self._lista_escenarios():
            clave = str(escenario.get("Clave"))
            claves_disponibles.append(clave)
            resultado = self.resultados_escenarios.get(clave)
            if resultado:
                lotes = self._formatear_lotes(resultado.get("Lotes", 0))
                unidades = str(int(resultado.get("Unidades", 0) or 0))
                cajas_xdc = str(int(resultado.get("CajasXDC", 0) or 0))
                cajas_silo = str(int(resultado.get("CajasSilo", 0) or 0))
            else:
                lotes = unidades = cajas_xdc = cajas_silo = "-"

            etiquetas = ("activo",) if clave == clave_activa and self.resumen_cajas else ()
            self.tabla_escenarios.insert(
                "",
                "end",
                iid=clave,
                values=(
                    escenario.get("Grupo", ""),
                    escenario.get("Descripcion", ""),
                    lotes,
                    unidades,
                    cajas_xdc,
                    cajas_silo,
                ),
                tags=etiquetas,
            )

        clave_seleccion = (
            seleccion_anterior
            if seleccion_anterior in claves_disponibles
            else clave_activa
            if clave_activa in claves_disponibles
            else CalculadorEscenariosCajas.CLAVE_TODO
        )
        if clave_seleccion in claves_disponibles:
            self.tabla_escenarios.selection_set(clave_seleccion)
            self.tabla_escenarios.focus(clave_seleccion)
            self.tabla_escenarios.see(clave_seleccion)
        self._al_seleccionar_escenario()

    def _al_seleccionar_escenario(self, _evento=None):
        if not hasattr(self, "lbl_escenario_seleccionado"):
            return
        escenario = self._escenario_por_clave(self._clave_seleccionada())
        self.lbl_escenario_seleccionado.config(
            text=(
                "Seleccionado: "
                + str(escenario.get("Grupo", ""))
                + " - "
                + str(escenario.get("Descripcion", ""))
            )
        )

    def _bloquear_controles_escenarios(self, bloqueado):
        estado = "disabled" if bloqueado else "normal"
        for control in [
            self.btn_importar_grupos,
            self.btn_limpiar_grupos,
            self.btn_calcular_escenarios,
            self.entry_umbral_sku,
            self.btn_anadir_tiendas_fijas,
            self.btn_editar_tienda_fija,
            self.btn_eliminar_tiendas_fijas,
            self.btn_reemplazar_tiendas_fijas,
            self.btn_vaciar_tiendas_fijas,
            getattr(self, "btn_cambiar_picos_pedido", None),
            getattr(self, "btn_quitar_pedido", None),
            getattr(self, "btn_vaciar_pedidos", None),
        ]:
            try:
                control.config(state=estado)
            except Exception:
                pass
        if bloqueado:
            self.btn_usar_escenario.config(state="disabled")
            try:
                self.ventana.config(cursor="watch")
            except Exception:
                pass
        else:
            self.btn_usar_escenario.config(
                state="normal" if self.escenarios_calculados else "disabled"
            )
            try:
                self.ventana.config(cursor="")
            except Exception:
                pass

    def _progreso_calculo_escenarios(self, indice, total, escenario):
        texto = (
            "Calculando "
            + str(indice)
            + " de "
            + str(total)
            + ": "
            + str(escenario.get("Grupo", ""))
        )
        self.lbl_progreso_escenarios.config(text=texto)
        progreso = getattr(self, "_dialogo_progreso", None)
        if progreso is not None:
            try:
                progreso.actualizar(
                    mensaje=texto,
                    actual=indice,
                    total=total,
                    detalle=str(escenario.get("Descripcion", "")),
                )
            except Exception:
                pass
        try:
            self.ventana.update_idletasks()
            self.ventana.update()
        except Exception:
            pass

    def _mostrar_resumen_filtro(self, filtro):
        umbral = int(filtro.get("Umbral", 0) or 0)
        self.lbl_filtro_sku.config(
            text=(
                "Pedidos: " + str(filtro.get("Pedidos", 0))
                + " (con picos: " + str(filtro.get("PedidosConPicos", 0))
                + ", sin picos: " + str(filtro.get("PedidosSinPicos", 0))
                + ") | unidades de pedidos sin picos conservadas: "
                + str(filtro.get("UnidadesSinPicos", 0))
                + "\nFiltro de picos sobre pedidos con picos y tiendas no fijas: descartar SKU con unidades < "
                + str(umbral)
                + " | SKU evaluados: "
                + str(filtro.get("SkusIniciales", 0))
                + " | descartados: "
                + str(filtro.get("SkusDescartados", 0))
                + " | unidades descartadas: "
                + str(filtro.get("UnidadesDescartadas", 0))
                + " | lotes descartados: "
                + self._formatear_lotes(filtro.get("LotesDescartados", 0))
                + "\nTiendas fijas configuradas: "
                + str(filtro.get("TiendasFijasConfiguradas", 0))
                + " | presentes en pedido: "
                + str(filtro.get("TiendasFijasEnPedido", 0))
                + " | unidades conservadas fuera de picos: "
                + str(filtro.get("UnidadesTiendasFijas", 0))
                + " | filas con talla no numerica: "
                + str(filtro.get("RegistrosTallaInvalida", 0))
            ),
            fg="#000000",
        )

    def _invalidar_volumetria_por_nuevo_escenario(self):
        self.resumen_paises = None
        ventana = self.ventana_volumetria
        if ventana is not None:
            try:
                if int(ventana.ventana.winfo_exists()) == 1:
                    ventana.invalidar_resultados()
            except Exception:
                self.ventana_volumetria = None

    def _guardar_escenario_global(self, escenario, resultado):
        """Guarda y verifica la fotografia global del escenario seleccionado."""
        estado = self.gestor_pedido_escenario.guardar_desde_estarepp(
            escenario=escenario,
            resultado=resultado or {},
            umbral=self.obtener_umbral_sku(mostrar_error=False) or 0,
            modo=self.modo_calculo.get(),
            tiendas_fijas=self.tiendas_fijas,
        )
        if not estado or not estado.get("Disponible"):
            raise RuntimeError(
                GestorPedidoEscenarioActivo.texto_estado(estado)
            )
        if str(estado.get("Clave", "")) != str(
            (escenario or {}).get("Clave", "")
        ):
            raise RuntimeError(
                "La comprobacion posterior al guardado devolvio un escenario "
                "diferente al seleccionado."
            )
        return estado

    def _marcar_escenario_global_guardado(self, estado):
        if not hasattr(self, "lbl_escenario_activo"):
            return
        linea = (
            "PEDIDO SELECCIONADO: "
            + GestorPedidoEscenarioActivo.nombre_pedido_activo(estado)
            + " | "
            + GestorPedidoEscenarioActivo.formatear_fecha(
                estado.get("FechaHora")
            )
        )
        linea_descartado = (
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
        self.lbl_escenario_activo.config(
            text=linea,
            fg="#1c4587",
        )
        if hasattr(self, "lbl_escenario_descartado"):
            self.lbl_escenario_descartado.config(
                text=linea_descartado,
                fg="#990000",
            )
        # Las ventanas de reparto que ya estuvieran abiertas se refrescan
        # tambien por temporizador/foco en ComponentePedidoEscenarioActivo.
        try:
            self.ventana.event_generate(
                "<<EscenarioCajasActualizado>>", when="tail"
            )
        except Exception:
            pass

    def _aplicar_calculo_activo(self, datos, actualizar_resultado=True):
        resumen = datos.get("ResumenActivo", {}) or {}
        escenario = datos.get(
            "EscenarioActivo", CalculadorEscenariosCajas.escenario_todo()
        )
        resultado = datos.get("Resultado")
        if resultado is None:
            resultado = (datos.get("PorClave", {}) or {}).get(
                str(escenario.get("Clave"))
            )

        self.resumen_cajas = resumen
        self.escenario_activo = escenario
        self.resultado_escenario_activo = resultado
        self.cajas_400_agotadas = int(
            resumen.get(
                "Cajas400CarruselReutilizables",
                resumen.get("Cajas400Agotadas", 0),
            )
            or 0
        )
        if resultado and actualizar_resultado:
            self.resultados_escenarios[str(resultado.get("Clave"))] = resultado

        self.btn_exportar_resultados.config(state="normal")
        self.mostrar_resumen_cajas()
        self._mostrar_resumen_filtro(datos.get("Filtro", {}) or {})
        tiendas_grupo = int((resultado or {}).get("TiendasGrupo", 0) or 0)
        tiendas_en_pedido = int(
            (resultado or {}).get("TiendasGrupoEnPedido", 0) or 0
        )
        fijas_eliminadas = int(
            (resultado or {}).get("TiendasFijasEliminadasGrupo", 0) or 0
        )
        self.lbl_escenario_activo.config(
            text=(
                "Escenario local seleccionado: "
                + str(escenario.get("Grupo", ""))
                + " - "
                + str(escenario.get("Descripcion", ""))
                + " | tiendas excluidas presentes en pedido: "
                + str(tiendas_en_pedido)
                + " / grupo: "
                + str(tiendas_grupo)
                + " | tiendas fijas eliminadas por el grupo: "
                + str(fijas_eliminadas)
            ),
            fg="#1c4587",
        )
        if hasattr(self, "lbl_escenario_descartado"):
            self.lbl_escenario_descartado.config(text="")
        try:
            estado_global = self._guardar_escenario_global(
                escenario=escenario,
                resultado=resultado or {},
            )
        except Exception as error:
            # El guardado es transaccional. Si falla, se conserva el ultimo
            # escenario global valido en vez de borrarlo.
            raise RuntimeError(
                "El escenario se calculo, pero no se pudo guardar como pedido "
                "global para los demas formularios. El ultimo escenario valido "
                "se ha conservado.\n\n" + str(error)
            ) from error

        self._marcar_escenario_global_guardado(estado_global)
        self._invalidar_volumetria_por_nuevo_escenario()
        self.refrescar_tabla_escenarios()
        self.actualizar_estado_volumetria()

    def calcular_escenarios(self):
        if not self.validar_calculo_cajas():
            return
        umbral = self.obtener_umbral_sku()
        if umbral is None:
            return

        self._bloquear_controles_escenarios(True)
        self._dialogo_progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando escenarios",
            mensaje="Preparando calculo de escenarios...",
            total=max(1, len(self.grupos_calculo or []) + 1),
        )
        try:
            calculador = CalculadorEscenariosCajas(bd=self.bd)
            datos = calculador.calcular_todos(
                modo=self.modo_calculo.get(),
                umbral=umbral,
                grupos=self.grupos_calculo,
                tiendas_fijas=self.tiendas_fijas,
                progreso=self._progreso_calculo_escenarios,
            )
            self.resultados_escenarios = dict(datos.get("PorClave", {}) or {})
            self.escenarios_calculados = True
            self._aplicar_calculo_activo(datos, actualizar_resultado=False)
            self.btn_usar_escenario.config(state="normal")
            self.lbl_progreso_escenarios.config(
                text="Calculo finalizado: "
                + str(len(datos.get("Resultados", []) or []))
                + " escenarios"
            )
            messagebox.showinfo(
                "Escenarios calculados",
                "Se han calculado "
                + str(len(datos.get("Resultados", []) or []))
                + " escenarios con el modo "
                + str(self.modo_calculo.get())
                + ".\n\n"
                + "TODO queda activo por defecto. Selecciona otra fila y pulsa "
                + "USAR ESCENARIO SELECCIONADO para excluir ese grupo en la "
                + "volumetria y los calculos posteriores.",
                parent=self.ventana,
            )
        except Exception as error:
            self.invalidar_resultados("el calculo de escenarios no finalizo")
            messagebox.showerror(
                "Error calculando escenarios", str(error), parent=self.ventana
            )
        finally:
            try:
                self._dialogo_progreso.cerrar()
            except Exception:
                pass
            self._dialogo_progreso = None
            self._bloquear_controles_escenarios(False)

    def usar_escenario_seleccionado(self):
        if not self.escenarios_calculados:
            messagebox.showwarning(
                "Escenarios sin calcular",
                "Primero debes pulsar CALCULAR ESCENARIOS.",
                parent=self.ventana,
            )
            return
        clave = self._clave_seleccionada()
        escenario = self._escenario_por_clave(clave)
        umbral = self.obtener_umbral_sku()
        if umbral is None:
            return

        if (
            str((self.escenario_activo or {}).get("Clave")) == clave
            and self.resumen_cajas is not None
        ):
            # Aunque ya sea el escenario local activo, vuelve a materializarlo.
            # Esto permite recuperar el guardado global si se instalo una
            # version anterior, si otra operacion lo dejo desactualizado o si
            # el operador quiere confirmar expresamente la seleccion.
            resultado_actual = self.resultado_escenario_activo or (
                self.resultados_escenarios.get(clave) or {}
            )
            try:
                estado_global = self._guardar_escenario_global(
                    escenario=escenario,
                    resultado=resultado_actual,
                )
                self._marcar_escenario_global_guardado(estado_global)
                self.refrescar_tabla_escenarios()
                messagebox.showinfo(
                    "Escenario guardado",
                    "El escenario seleccionado se ha guardado y ya esta "
                    "disponible en todos los formularios de calculo de tablas.\n\n"
                    + GestorPedidoEscenarioActivo.texto_estado(estado_global),
                    parent=self.ventana,
                )
            except Exception as error:
                messagebox.showerror(
                    "Error guardando escenario",
                    str(error),
                    parent=self.ventana,
                )
            return

        self._bloquear_controles_escenarios(True)
        self.lbl_progreso_escenarios.config(
            text="Activando escenario " + str(escenario.get("Grupo", "")) + "..."
        )
        self._dialogo_progreso = DialogoProgreso(
            self.ventana,
            titulo="Activando escenario",
            mensaje="Activando escenario " + str(escenario.get("Grupo", "")) + "...",
        )
        try:
            calculador = CalculadorEscenariosCajas(bd=self.bd)
            datos = calculador.calcular_unico(
                modo=self.modo_calculo.get(),
                umbral=umbral,
                escenario=escenario,
                tiendas_fijas=self.tiendas_fijas,
            )
            self._aplicar_calculo_activo(datos)
            self.lbl_progreso_escenarios.config(text="Escenario activo actualizado")
        except Exception as error:
            messagebox.showerror(
                "Error activando escenario", str(error), parent=self.ventana
            )
        finally:
            try:
                self._dialogo_progreso.cerrar()
            except Exception:
                pass
            self._dialogo_progreso = None
            self._bloquear_controles_escenarios(False)

    def obtener_texto_escenario_activo(self):
        escenario = self.escenario_activo or CalculadorEscenariosCajas.escenario_todo()
        resultado = self.resultado_escenario_activo or {}
        if str(escenario.get("Clave")) == CalculadorEscenariosCajas.CLAVE_TODO:
            return (
                "TODO - no se excluyen tiendas | tiendas fijas conservadas: "
                + str(resultado.get("TiendasFijasConservadas", 0))
            )
        return (
            str(escenario.get("Grupo", ""))
            + " - "
            + str(escenario.get("Descripcion", ""))
            + " | tiendas excluidas presentes en pedido: "
            + str(resultado.get("TiendasGrupoEnPedido", 0))
            + " / grupo: "
            + str(resultado.get("TiendasGrupo", len(escenario.get("Tiendas", set()) or set())))
            + " | tiendas fijas eliminadas por el grupo: "
            + str(resultado.get("TiendasFijasEliminadasGrupo", 0))
        )

    # ---------------------------------------------------------
    # BLOQUE 1 - Reserva fisica
    # ---------------------------------------------------------
    def crear_bloque_reserva(self, contenedor=None):
        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="1. RESERVA DE CAJAS DEL SILO",
            font=("Arial", 12, "bold"),
            padx=10,
            pady=8,
        )
        marco.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        marco.grid_columnconfigure(0, weight=1)

        fila_opciones = tk.Frame(marco)
        fila_opciones.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        opciones = [
            ("XDOC", "XDOC"),
            ("XDOC + LIMPIEZA", "XDOC_LIMPIEZA"),
            ("XDOC + MAS UNIDADES", "XDOC_MAS_UNIDADES"),
        ]
        for texto, valor in opciones:
            tk.Radiobutton(
                fila_opciones,
                text=texto,
                variable=self.modo_calculo,
                value=valor,
                font=("Arial", 10, "bold"),
            ).pack(side="left", padx=(0, 12))

        fila_acciones = tk.Frame(marco)
        fila_acciones.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        fila_acciones.grid_columnconfigure(0, weight=1)
        fila_acciones.grid_columnconfigure(1, weight=1)

        tk.Button(
            fila_acciones,
            text="CALCULAR CAJAS",
            height=2,
            bg="#d9ead3",
            font=("Arial", 10, "bold"),
            command=self.calcular_cajas,
        ).grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_exportar_resultados = tk.Button(
            fila_acciones,
            text="EXPORTAR RESULTADOS",
            height=2,
            font=("Arial", 9, "bold"),
            state="disabled",
            command=self.exportar_resultados_cajas,
        )
        self.btn_exportar_resultados.grid(
            row=0, column=1, padx=(5, 0), sticky="ew"
        )

        self.lbl_reserva_total = tk.Label(
            marco,
            text="CAJAS XDOC: -",
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_reserva_total.grid(row=2, column=0, sticky="ew", pady=(1, 1))

        self.lbl_agotadas = tk.Label(
            marco,
            text="CAJAS PARA CARRUSELES: -",
            font=("Arial", 10, "bold"),
            justify="left",
            anchor="w",
        )
        self.lbl_agotadas.grid(row=3, column=0, sticky="ew", pady=1)

        self.lbl_total_general = tk.Label(
            marco,
            text="TOTAL CAJAS RESERVADAS: -",
            font=("Arial", 10, "bold"),
            justify="left",
            anchor="w",
        )
        self.lbl_total_general.grid(row=4, column=0, sticky="ew", pady=(1, 0))

    def validar_calculo_cajas(self):
        if self.contar_tabla("CAJAS_PEDIDO_LINEAS") <= 0:
            messagebox.showwarning("Falta pedido", "Primero debes importar el pedido.", parent=self.ventana)
            return False
        if self.contar_tabla("CAJAS_CONTENEDORES") <= 0:
            messagebox.showwarning("Faltan contenedores", "Primero debes importar Contenedores.csv.", parent=self.ventana)
            return False
        if self.contar_tabla("CAJAS_VOLUMETRIA") <= 0:
            continuar = messagebox.askyesno(
                "Volumetria no cargada",
                "No hay volumetria cargada. XDOC usara la moda del silo cuando sea posible.\n\n¿Continuar?",
                parent=self.ventana,
            )
            return bool(continuar)
        return True

    def calcular_cajas(self):
        if not self.validar_calculo_cajas():
            return
        umbral = self.obtener_umbral_sku()
        if umbral is None:
            return

        escenario = self.escenario_activo or CalculadorEscenariosCajas.escenario_todo()
        self._bloquear_controles_escenarios(True)
        self.lbl_progreso_escenarios.config(
            text="Calculando escenario activo "
            + str(escenario.get("Grupo", ""))
            + "..."
        )
        self._dialogo_progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando cajas",
            mensaje="Calculando escenario activo " + str(escenario.get("Grupo", "")) + "...",
        )
        try:
            calculador = CalculadorEscenariosCajas(bd=self.bd)
            datos = calculador.calcular_unico(
                modo=self.modo_calculo.get(),
                umbral=umbral,
                escenario=escenario,
                tiendas_fijas=self.tiendas_fijas,
            )
            self._aplicar_calculo_activo(datos)
            self.lbl_progreso_escenarios.config(text="Calculo activo finalizado")

            # Si el formulario independiente estuviera abierto, actualiza su
            # contexto y objetivo con el escenario que acaba de calcularse.
            if self.ventana_volumetria is not None:
                try:
                    self.ventana_volumetria.actualizar_objetivo_desde_padre()
                except Exception:
                    self.ventana_volumetria = None

            messagebox.showinfo(
                "Calculo finalizado",
                "Calculo de reserva finalizado correctamente.\n\n"
                + "Escenario activo: "
                + self.obtener_texto_escenario_activo(),
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error calculando cajas", str(error), parent=self.ventana
            )
        finally:
            try:
                self._dialogo_progreso.cerrar()
            except Exception:
                pass
            self._dialogo_progreso = None
            self._bloquear_controles_escenarios(False)

    def exportar_resultados_cajas(self):
        if not self.resumen_cajas:
            messagebox.showwarning(
                "Sin calculo",
                "Primero debes calcular las cajas.",
                parent=self.ventana,
            )
            return

        motor = None
        try:
            motor = MotorCalculoCajasPedido()
            rutas = motor.exportar_resultados()
            if not rutas:
                return
            messagebox.showinfo(
                "Exportacion finalizada",
                "Se han exportado los resultados, incluido el detalle de "
                "matriculas, el perfil XDOC y las incidencias.\n\nCarpeta:\n"
                + str(Path(rutas[0]).parent),
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error exportando resultados",
                str(error),
                parent=self.ventana,
            )
        finally:
            if motor is not None:
                try:
                    motor.bd.cerrar()
                except Exception:
                    pass

    def _texto_desglose_tcm(self, filas):
        partes = []
        for tcm, cantidad in filas or []:
            partes.append(str(tcm).strip() + ": " + str(int(cantidad or 0)))
        return "   |   ".join(partes) if partes else "sin cajas"

    def mostrar_resumen_cajas(self):
        resumen = self.resumen_cajas or {}

        xdoc_total = int(resumen.get("CajasReservadasXDOC", 0) or 0)
        xdoc_tcm = resumen.get("CajasXDOCPorTCM", []) or []
        self.lbl_reserva_total.config(
            text=(
                "CAJAS XDOC: " + str(xdoc_total)
                + "   |   " + self._texto_desglose_tcm(xdoc_tcm)
                + "   |   NO REUTILIZABLES"
            )
        )

        carr_total = int(resumen.get("CajasCarruselTotal", 0) or 0)
        carr_completas = int(resumen.get("CajasCarruselCompletas", 0) or 0)
        carr_retorno = int(resumen.get("CajasCarruselRetorno", 0) or 0)
        carr_tcm = resumen.get("CajasCarruselPorTCM", []) or []
        self.lbl_agotadas.config(
            text=(
                "CAJAS PARA CARRUSELES: " + str(carr_total)
                + "   |   completas: " + str(carr_completas)
                + "   |   retorno: " + str(carr_retorno)
                + "   |   " + self._texto_desglose_tcm(carr_tcm)
            )
        )

        total = int(resumen.get("CajasReservadasTotal", 0) or 0)
        reutilizables_400 = int(resumen.get("Cajas400CarruselReutilizables", 0) or 0)
        self.lbl_total_general.config(
            text=(
                "TOTAL CAJAS RESERVADAS: " + str(total)
                + "   |   CAJAS 400 REUTILIZABLES (carrusel completas): " + str(reutilizables_400)
            )
        )

    # ---------------------------------------------------------
    # Acceso al formulario independiente de volumetria
    # ---------------------------------------------------------
    def _volumetria_abierta(self):
        formulario = self.ventana_volumetria
        if formulario is None:
            return False
        try:
            return int(formulario.ventana.winfo_exists()) == 1
        except Exception:
            self.ventana_volumetria = None
            return False

    def abrir_volumetria_reutilizacion(self):
        if self._volumetria_abierta():
            self.ventana_volumetria.traer_al_frente()
            return

        if self.contar_tabla("CAJAS_PEDIDO_LINEAS") <= 0:
            messagebox.showwarning(
                "Falta pedido",
                "Primero debes importar el pedido antes de abrir la volumetria por pais.",
                parent=self.ventana,
            )
            return

        if self.resumen_cajas is None:
            messagebox.showwarning(
                "Falta calculo de cajas",
                "Primero debes calcular las cajas del escenario que quieres usar.\n\n"
                "Puedes calcular todos los escenarios y seleccionar uno, o usar "
                "CALCULAR CAJAS para el escenario activo.",
                parent=self.ventana,
            )
            return

        try:
            self.ventana_volumetria = FormularioVolumetriaReutilizacionPaises(self)
        except Exception as error:
            self.ventana_volumetria = None
            messagebox.showerror(
                "Error abriendo volumetria",
                str(error),
                parent=self.ventana,
            )

    def actualizar_estado_volumetria(self):
        """Compatibilidad con el formulario hijo sin ocupar la zona inferior."""
        return None

    def cerrar(self):
        if self._volumetria_abierta():
            try:
                self.ventana_volumetria.cerrar()
            except Exception:
                pass
            self.ventana_volumetria = None

        try:
            self.ventana.grab_release()
        except Exception:
            pass
        try:
            self.bd.cerrar()
        except Exception:
            pass
        try:
            self.ventana.destroy()
        except Exception:
            pass

    # Compatibilidad con integraciones y pruebas de versiones anteriores.
    # La logica vive en el nuevo formulario; aqui solo se exponen delegados sin
    # volver a duplicar la implementacion.
    obtener_paises_400_seleccionados = (
        FormularioVolumetriaReutilizacionPaises.obtener_paises_400_seleccionados
    )
    _texto_vista_previa_maestro = (
        FormularioVolumetriaReutilizacionPaises._texto_vista_previa_maestro
    )
    cargar_paises_400_en_maestro = (
        FormularioVolumetriaReutilizacionPaises.cargar_paises_400_en_maestro
    )

    # ---------------------------------------------------------
    # Utilidades BD
    # ---------------------------------------------------------
    def contar_tabla(self, tabla):
        try:
            return int(self.bd.contar_registros(tabla) or 0)
        except Exception:
            return 0

    def contar_contenedores_disponibles(self):
        try:
            filas = self.bd.consultar("SELECT COUNT(*) FROM CAJAS_CONTENEDORES WHERE Disponible = 1")
            return int(filas[0][0] or 0) if filas else 0
        except Exception:
            return 0

    # ---------------------------------------------------------
    # Ejecutar
    # ---------------------------------------------------------
    def ejecutar(self):
        self.ventana.wait_window()
