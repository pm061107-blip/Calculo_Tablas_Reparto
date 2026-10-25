from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog

from modulos.calculador_cajas_paises import CalculadorCajasPaises
from modulos.exportar_sin_volumetria import ExportadorSinVolumetria
from modulos.ventanas_tk import forzar_ventana_visible, preparar_formulario_navegable, crear_marco_scrollable
from modulos.dialogo_progreso import DialogoProgreso
from modulos.gestor_reset_calculos import GestorResetCalculos


def _pais_bloqueado(formulario, clave):
    """V2.6: pais con dos tipos de caja (no se puede elegir 300/400)."""
    item = (getattr(formulario, "paises_vars", {}) or {}).get(clave) or {}
    datos = item.get("datos") or {}
    return bool((datos.get("TiposFinales") or {}).get("Bloqueado"))


def _paises_bloqueados(formulario):
    """Nombres de pais (sin repetir) de las filas bloqueadas."""
    resultado = []
    for clave, item in (getattr(formulario, "paises_vars", {}) or {}).items():
        if not _pais_bloqueado(formulario, clave):
            continue
        pais = str((item.get("datos") or {}).get("Pais", "") or clave).split("|")[0]
        if pais not in resultado:
            resultado.append(pais)
    return resultado


def _clave_fila(gestor, fila):
    """Clave unica de una fila: pais, o pais|tipo en las lineas desglosadas."""
    if fila.get("Clave"):
        return str(fila["Clave"])
    normalizar = getattr(gestor, "normalizar_pais", None)
    pais = fila.get("Pais", "")
    return normalizar(pais) if normalizar else str(pais or "").strip().upper()


class FormularioVolumetriaReutilizacionPaises:
    """Formulario independiente para la volumetria y reutilizacion por pais.

    La ventana trabaja sobre el mismo pedido, la misma base de datos y el mismo
    resultado de cajas que ``FormularioCalculoCajasPedido``. No vuelve a importar
    datos y no duplica la logica de calculo de los modulos de negocio.
    """

    def __init__(self, formulario_cajas):
        self.formulario_cajas = formulario_cajas
        self.ventana_padre = formulario_cajas.ventana
        self.bd = formulario_cajas.bd
        self.gestor_tipo_caja_pais = formulario_cajas.gestor_tipo_caja_pais
        self.resumen_paises = formulario_cajas.resumen_paises
        self.paises_vars = {}

        self.ventana = tk.Toplevel(self.ventana_padre)
        self.ventana.withdraw()
        self.ventana.title(
            "Volumetria y optimizacion de reutilizacion de cajas por pais"
        )
        self.ventana.resizable(True, True)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.ventana.bind("<Escape>", lambda _evento: self.cerrar())

        self.crear_controles()
        self.actualizar_contexto()
        self._mostrar_en_primer_plano()

        if self.resumen_paises:
            self.ventana.after_idle(self.aplicar_seleccion_automatica_paises)

    @property
    def cajas_400_agotadas(self):
        return int(self.formulario_cajas.cajas_400_agotadas or 0)

    @property
    def resumen_cajas(self):
        return self.formulario_cajas.resumen_cajas

    def crear_controles(self):
        # V2.7: sin scroll exterior. La cabecera ocupa lo minimo y la tabla de
        # paises se estira para llenar TODO el alto disponible, sea cual sea la
        # resolucion del PC (la tabla tiene su propio scroll).
        contenedor = tk.Frame(self.ventana)
        contenedor.pack(fill="both", expand=True)
        self.contenedor_principal = contenedor

        cabecera = tk.Frame(contenedor)
        cabecera.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(
            cabecera,
            text="VOLUMETRIA Y REUTILIZACION DE CAJAS POR PAIS",
            font=("Arial", 13, "bold"),
        ).pack(side="left")
        tk.Button(
            cabecera,
            text="Cerrar y volver",
            width=16,
            command=self.cerrar,
        ).pack(side="right")
        self.crear_boton_reset(cabecera)

        self.lbl_contexto = tk.Label(
            contenedor,
            text="",
            font=("Arial", 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_contexto.pack(fill="x", padx=12, pady=(0, 2))

        self.crear_bloque_paises(contenedor)

    def crear_boton_reset(self, contenedor):
        tk.Button(
            contenedor,
            text="RESETEAR CALCULO DE PAISES",
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 9, "bold"),
            command=self.resetear_calculo_paises,
        ).pack(side="right", padx=(0, 10))

    def resetear_calculo_paises(self):
        if not messagebox.askyesno(
            "Resetear calculo de paises",
            "Se limpiara el calculo visual de paises y la seleccion actual.\n\n"
            "No se borrara la volumetria SKU ni el maestro TipoCajaPais.\n\n"
            "¿Continuar?",
            parent=self.ventana,
        ):
            return
        try:
            GestorResetCalculos(self.bd.conexion).resetear_volumetria_paises()
            self.invalidar_resultados()
            messagebox.showinfo(
                "Reset finalizado",
                "Calculo de paises reseteado correctamente. La volumetria SKU se conserva.",
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror(
                "Error reseteando calculo",
                str(error),
                parent=self.ventana,
            )

    def _centrar_sobre_padre(self):
        self.ventana.update_idletasks()
        pantalla_ancho = max(1024, int(self.ventana.winfo_screenwidth()))
        pantalla_alto = max(700, int(self.ventana.winfo_screenheight()))
        ancho = max(800, min(1320, pantalla_ancho - 40))
        alto = max(580, min(820, pantalla_alto - 80))

        try:
            padre_x = int(self.ventana_padre.winfo_rootx())
            padre_y = int(self.ventana_padre.winfo_rooty())
            padre_ancho = int(self.ventana_padre.winfo_width())
            padre_alto = int(self.ventana_padre.winfo_height())
            x = padre_x + max(0, (padre_ancho - ancho) // 2)
            y = padre_y + max(0, (padre_alto - alto) // 2)
        except Exception:
            x = (pantalla_ancho - ancho) // 2
            y = (pantalla_alto - alto) // 2

        x = max(0, min(x, pantalla_ancho - ancho))
        y = max(0, min(y, pantalla_alto - alto))
        self.ventana.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.ventana.minsize(min(1000, ancho), min(620, alto))

    def _mostrar_en_primer_plano(self):
        self._centrar_sobre_padre()
        self.ventana.deiconify()
        preparar_formulario_navegable(
            self.ventana,
            parent=self.ventana_padre,
            maximizar=True,
        )
        try:
            self.btn_calcular_paises.focus_set()
        except Exception:
            pass

    def traer_al_frente(self):
        preparar_formulario_navegable(
            self.ventana,
            parent=self.ventana_padre,
            maximizar=True,
        )
        try:
            self.btn_calcular_paises.focus_set()
        except Exception:
            pass

    def actualizar_contexto(self):
        pedido = self.contar_tabla("CAJAS_PEDIDO_LINEAS")
        volumetria = self.contar_tabla("CAJAS_VOLUMETRIA")
        contenedores = self.contar_tabla("CAJAS_CONTENEDORES")
        texto = (
            "Pedido: " + ("cargado" if pedido > 0 else "sin cargar")
            + "   |   Volumetria: " + ("cargada" if volumetria > 0 else "sin cargar")
            + "   |   Contenedores: " + ("cargados" if contenedores > 0 else "sin cargar")
            + "   |   Cajas 400 reutilizables: " + str(self.cajas_400_agotadas)
        )
        self.lbl_contexto.config(text=texto)

    def actualizar_objetivo_desde_padre(self):
        self.resumen_paises = self.formulario_cajas.resumen_paises
        self.actualizar_contexto()
        if self.resumen_paises:
            self.aplicar_seleccion_automatica_paises()
        else:
            self.lbl_objetivo_400.config(
                text=(
                    "Cajas 400 reutilizables desde carruseles: "
                    + str(self.cajas_400_agotadas)
                )
            )

    def invalidar_resultados(self):
        self.resumen_paises = None
        self.formulario_cajas.resumen_paises = None
        self.limpiar_tabla_paises()
        self.lbl_objetivo_400.config(
            text="Cajas 400 reutilizables desde carruseles: -"
        )
        self.lbl_seleccion_paises.config(text="Seleccion actual: -", fg="#000000")
        self.lbl_incidencias_paises.config(text="")
        self.actualizar_contexto()

    def cerrar(self):
        self.formulario_cajas.resumen_paises = self.resumen_paises
        if getattr(self.formulario_cajas, "ventana_volumetria", None) is self:
            self.formulario_cajas.ventana_volumetria = None

        try:
            self.ventana.grab_release()
        except Exception:
            pass
        try:
            self.ventana.attributes("-topmost", False)
        except Exception:
            pass
        try:
            self.ventana.destroy()
        except Exception:
            pass

        try:
            self.formulario_cajas.actualizar_estado_volumetria()
        except Exception:
            pass
        forzar_ventana_visible(
            self.ventana_padre,
            mantener_arriba=False,
            focus_widget=getattr(
                self.formulario_cajas,
                "btn_abrir_volumetria",
                None,
            ),
        )

    def contar_tabla(self, tabla):
        return self.formulario_cajas.contar_tabla(tabla)

    # ---------------------------------------------------------
    # BLOQUE 2 - Volumetria y optimizacion por pais
    # ---------------------------------------------------------
    def crear_bloque_paises(self, contenedor=None):
        contenedor = contenedor or self.ventana
        marco = tk.LabelFrame(
            contenedor,
            text="VOLUMETRIA Y OPTIMIZACION DE REUTILIZACION POR PAIS",
            font=("Arial", 12, "bold"),
            padx=10,
            pady=8,
        )
        marco.pack(fill="both", expand=True, padx=10, pady=(2, 8))

        fila_acciones = tk.Frame(marco)
        fila_acciones.pack(fill="x", pady=(0, 4))

        self.btn_calcular_paises = tk.Button(
            fila_acciones,
            text="CALCULAR PAISES",
            width=22,
            height=1,
            bg="#d9eaf7",
            font=("Arial", 10, "bold"),
            command=self.calcular_paises,
        )
        self.btn_calcular_paises.pack(side="left", padx=(0, 12))

        tk.Button(
            fila_acciones,
            text="EXPORTAR SIN VOLUMETRIA",
            width=24,
            height=1,
            font=("Arial", 9, "bold"),
            command=self.exportar_sin_volumetria,
        ).pack(side="left", padx=(0, 12))

        self.btn_cargar_paises_400 = tk.Button(
            fila_acciones,
            text="CARGAR PAISES 400 EN MAESTRO",
            width=31,
            height=1,
            bg="#fce5cd",
            font=("Arial", 9, "bold"),
            state="disabled",
            command=self.cargar_paises_400_en_maestro,
        )
        self.btn_cargar_paises_400.pack(side="left", padx=(0, 12))

        self.lbl_objetivo_400 = tk.Label(
            fila_acciones,
            text="Objetivo reutilizacion caja 400: -",
            font=("Arial", 10, "bold"),
            anchor="w",
        )
        self.lbl_objetivo_400.pack(side="left", padx=5)

        self.lbl_seleccion_paises = tk.Label(
            marco,
            text="Seleccion actual: -",
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_seleccion_paises.pack(fill="x", pady=(4, 1))

        self.lbl_incidencias_paises = tk.Label(
            marco,
            text="",
            font=("Arial", 8),
            anchor="w",
            justify="left",
        )
        self.lbl_incidencias_paises.pack(fill="x", pady=(0, 3))

        # Los textos largos se parten en lineas segun el ancho real de la
        # ventana en vez de quedar cortados.
        def _ajustar_textos(evento):
            ancho = max(300, int(evento.width) - 20)
            for etiqueta in (self.lbl_seleccion_paises, self.lbl_incidencias_paises):
                try:
                    etiqueta.config(wraplength=ancho)
                except Exception:
                    pass
        marco.bind("<Configure>", _ajustar_textos, add="+")

        contenedor_tabla = tk.Frame(marco, bd=1, relief="sunken")
        contenedor_tabla.pack(fill="both", expand=True, pady=(2, 0))
        contenedor_tabla.grid_rowconfigure(0, weight=1)
        contenedor_tabla.grid_columnconfigure(0, weight=1)

        self.canvas_paises = tk.Canvas(contenedor_tabla, highlightthickness=0)
        scroll_y = tk.Scrollbar(contenedor_tabla, orient="vertical", command=self.canvas_paises.yview)
        scroll_x = tk.Scrollbar(contenedor_tabla, orient="horizontal", command=self.canvas_paises.xview)
        self.frame_paises = tk.Frame(self.canvas_paises)

        def _actualizar_scroll(_evento=None):
            try:
                self.canvas_paises.configure(scrollregion=self.canvas_paises.bbox("all"))
            except Exception:
                pass

        def _ajustar_ancho(evento):
            try:
                ancho = max(int(evento.width), int(self.frame_paises.winfo_reqwidth()))
                self.canvas_paises.itemconfigure(self.ventana_paises_canvas, width=ancho)
            except Exception:
                pass

        self.frame_paises.bind("<Configure>", _actualizar_scroll, add="+")
        self.ventana_paises_canvas = self.canvas_paises.create_window((0, 0), window=self.frame_paises, anchor="nw")
        self.canvas_paises.bind("<Configure>", _ajustar_ancho, add="+")
        self.canvas_paises.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.canvas_paises.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        def _rueda(evento):
            try:
                if getattr(evento, "num", None) == 4:
                    self.canvas_paises.yview_scroll(-3, "units")
                elif getattr(evento, "num", None) == 5:
                    self.canvas_paises.yview_scroll(3, "units")
                elif int(evento.delta):
                    self.canvas_paises.yview_scroll(int(-1 * (int(evento.delta) / 120)), "units")
            except Exception:
                pass

        def _activar_rueda(_evento=None):
            try:
                self.canvas_paises.bind_all("<MouseWheel>", _rueda)
                self.canvas_paises.bind_all("<Button-4>", _rueda)
                self.canvas_paises.bind_all("<Button-5>", _rueda)
            except Exception:
                pass

        def _desactivar_rueda(_evento=None):
            try:
                self.canvas_paises.unbind_all("<MouseWheel>")
                self.canvas_paises.unbind_all("<Button-4>")
                self.canvas_paises.unbind_all("<Button-5>")
            except Exception:
                pass

        contenedor_tabla.bind("<Enter>", _activar_rueda, add="+")
        contenedor_tabla.bind("<Leave>", _desactivar_rueda, add="+")

        self._crear_cabecera_tabla_paises()

    def _crear_cabecera_tabla_paises(self):
        cabeceras = [
            "PAIS",
            "VOLUMEN m3",
            "CAJA 300",
            "CAJA 400",
            "TIPO 400 A GUARDAR",
            "MAESTRO ACTUAL",
            "AVISO (clic = detalle)",
        ]
        for col, texto in enumerate(cabeceras):
            tk.Label(
                self.frame_paises,
                text=texto,
                font=("Arial", 9, "bold"),
                bd=1,
                relief="groove",
                padx=6,
                pady=4,
            ).grid(row=0, column=col, sticky="nsew")
        self.frame_paises.grid_columnconfigure(0, weight=3)
        self.frame_paises.grid_columnconfigure(1, weight=1)
        self.frame_paises.grid_columnconfigure(2, weight=1)
        self.frame_paises.grid_columnconfigure(3, weight=1)
        self.frame_paises.grid_columnconfigure(4, weight=2)
        self.frame_paises.grid_columnconfigure(5, weight=2)
        self.frame_paises.grid_columnconfigure(6, weight=3)

    def limpiar_tabla_paises(self):
        if not hasattr(self, "frame_paises"):
            return
        for widget in self.frame_paises.winfo_children():
            widget.destroy()
        self.paises_vars = {}
        if hasattr(self, "btn_cargar_paises_400"):
            self.btn_cargar_paises_400.config(state="disabled")
        self._crear_cabecera_tabla_paises()

    def validar_calculo_paises(self):
        if self.contar_tabla("CAJAS_PEDIDO_LINEAS") <= 0:
            messagebox.showwarning("Falta pedido", "Primero debes importar el pedido.", parent=self.ventana)
            return False
        if self.contar_tabla("CAJAS_VOLUMETRIA") <= 0:
            messagebox.showwarning("Falta volumetria", "Primero debes importar la volumetria SKU.", parent=self.ventana)
            return False
        if self.contar_tabla("Tiendas_Web") <= 0:
            messagebox.showwarning(
                "Falta maestro de paises",
                "La tabla Tiendas_Web no contiene datos. No se puede agrupar el pedido por pais.",
                parent=self.ventana,
            )
            return False
        if self.resumen_cajas is None:
            messagebox.showwarning(
                "Falta calculo de cajas",
                "Primero debes ejecutar CALCULAR CAJAS.\n\n"
                "El calculo por pais descuenta obligatoriamente las unidades XDOC "
                "y utiliza solo las cajas 400 completas de carruseles como objetivo de reutilizacion.",
                parent=self.ventana,
            )
            return False
        return True

    def calcular_paises(self):
        if not self.validar_calculo_paises():
            return
        progreso = DialogoProgreso(
            self.ventana,
            titulo="Calculando paises",
            mensaje="Calculando volumetria y reutilizacion por pais...",
        )
        try:
            calculador = CalculadorCajasPaises()
            progreso.actualizar(mensaje="Calculando volumen por pais...")
            # V2.7: los paises con dos tipos de caja se calculan en una linea
            # por cada tipo de caja (cada tipo lleva sus propias cajas).
            try:
                bloqueados = self.gestor_tipo_caja_pais.paises_bloqueados_dos_tipos()
                desglose = self.gestor_tipo_caja_pais.tipo_final_por_tienda(bloqueados)
            except Exception:
                desglose = {}
            self.resumen_paises = calculador.calcular(desglose_tiendas=desglose)
            progreso.actualizar(mensaje="Aplicando seleccion automatica de paises 400...")
            self.formulario_cajas.resumen_paises = self.resumen_paises
            self.formulario_cajas.actualizar_estado_volumetria()
            self.aplicar_seleccion_automatica_paises()

            faltan = int(self.resumen_paises.get("SkusSinVolumetria", 0) or 0)
            sin_oficial = int(self.resumen_paises.get("SkusSinVolumetriaOficial", 0) or 0)
            calculados_cont = int(self.resumen_paises.get("SkusVolumetriaContenedores", 0) or 0)
            oficiales = int(self.resumen_paises.get("SkusVolumetriaOficial", 0) or 0)
            uds = int(self.resumen_paises.get("UnidadesSinVolumetria", 0) or 0)
            tiendas = int(self.resumen_paises.get("TiendasSinPais", 0) or 0)
            volumen = float(self.resumen_paises.get("VolumenTotalM3", 0.0) or 0.0)
            fallback_ok = bool(self.resumen_paises.get("FallbackContenedoresDisponible", True))
            uds_xdoc = int(self.resumen_paises.get("UnidadesDescontadasXDOC", 0) or 0)
            uds_carrusel = int(self.resumen_paises.get("UnidadesDemandaCarruseles", 0) or 0)
            aviso_fallback = "" if fallback_ok else "   |   REIMPORTAR CONTENEDORES PARA FALLBACK"
            self.lbl_incidencias_paises.config(
                text=(
                    "Demanda carruseles: " + str(uds_carrusel) + " uds"
                    + "   |   XDOC descontado: " + str(uds_xdoc) + " uds"
                    + "   |   Volumen: " + format(volumen, ".6f") + " m3"
                    + "   |   SKU oficial: " + str(oficiales)
                    + "   |   sin oficial: " + str(sin_oficial)
                    + "   |   calculados con Contenedores: " + str(calculados_cont)
                    + "   |   todavia sin volumetria: " + str(faltan)
                    + "   |   Uds sin volumetria: " + str(uds)
                    + "   |   Tiendas sin pais: " + str(tiendas)
                    + aviso_fallback
                )
            )
        except Exception as error:
            messagebox.showerror("Error calculando paises", str(error), parent=self.ventana)
        finally:
            progreso.cerrar()

    def exportar_sin_volumetria(self):
        if self.contar_tabla("CAJAS_PEDIDO_LINEAS") <= 0:
            messagebox.showwarning("Falta pedido", "Primero debes importar el pedido.", parent=self.ventana)
            return
        if self.contar_tabla("CAJAS_VOLUMETRIA") <= 0:
            messagebox.showwarning("Falta volumetria", "Primero debes importar la volumetria oficial.", parent=self.ventana)
            return
        if self.contar_tabla("CAJAS_CONTENEDORES") <= 0:
            messagebox.showwarning("Faltan contenedores", "Primero debes importar Contenedores.csv.", parent=self.ventana)
            return

        ruta = filedialog.asksaveasfilename(
            parent=self.ventana,
            title="Exportar SKU sin volumetria",
            defaultextension=".csv",
            initialfile="Sin_volumetria.csv",
            filetypes=[("CSV", "*.csv"), ("Todos los ficheros", "*.*")],
        )
        if not ruta:
            return

        try:
            resultado = ExportadorSinVolumetria().exportar(ruta)
            messagebox.showinfo(
                "Sin volumetria exportado",
                "Exportacion finalizada.\n\n"
                + "SKU sin volumetria oficial: " + str(resultado.get("SkusSinOficial", 0)) + "\n"
                + "SKU calculables desde Contenedores: " + str(resultado.get("SkusCalculables", 0)) + "\n"
                + "SKU sin datos suficientes: " + str(resultado.get("SkusSinDatos", 0)) + "\n"
                + "Filas generadas: " + str(len(resultado.get("Filas", []))) + "\n\n"
                + "Fichero de carga:\n" + str(resultado.get("Ruta", "")) + "\n\n"
                + "Diagnostico:\n" + str(resultado.get("RutaDiagnostico", "")),
                parent=self.ventana,
            )
        except Exception as error:
            messagebox.showerror("Error exportando sin volumetria", str(error), parent=self.ventana)

    # ---------------------------------------------------------
    # V2.7 - utilidades de fila (pais normal o linea por tipo de caja)
    # ---------------------------------------------------------
    def _clave_fila(self, fila):
        return _clave_fila(self.gestor_tipo_caja_pais, fila)

    @staticmethod
    def _es_tipo_400(tipo):
        return str(tipo or "").strip().upper() in {"3_USADA_40", "4_NUEVA_40"}

    def aplicar_seleccion_automatica_paises(self):
        if not self.resumen_paises:
            return

        paises = CalculadorCajasPaises.ordenar_paises(
            self.resumen_paises.get("Paises", []) or []
        )
        self.resumen_paises["Paises"] = paises
        self.enriquecer_tipos_400_paises(paises)

        maestro_400 = self.obtener_paises_400_maestro_actual()
        normalizar = self.gestor_tipo_caja_pais.normalizar_pais
        for fila in paises:
            tipo_actual = maestro_400.get(normalizar(fila.get("Pais", "")), "")
            fila["YaEnMaestro400"] = bool(tipo_actual)
            fila["TipoCajaPaisActual"] = tipo_actual

        # Paises con dos tipos de caja (TipoCajaPais + tiendas a mayores)
        tipos_finales = self.obtener_tipos_finales_paises(paises)
        bloqueadas = set()   # claves de fila que no se pueden elegir
        solo_300 = set()
        solo_400 = set()
        fijas_400 = set()    # bloqueadas cuyas cajas cuentan como 400
        for fila in paises:
            clave = self._clave_fila(fila)
            info = dict(tipos_finales.get(normalizar(fila.get("Pais", ""))) or {})
            if fila.get("TipoFijo"):
                # Linea de un pais desglosado: tipo de caja fijo.
                info["Bloqueado"] = True
                info["Permite300"] = False
                info["Permite400"] = False
                info["Motivo"] = "2 TIPOS: linea fija " + str(fila["TipoFijo"])
            fila["TiposFinales"] = info
            if info.get("Bloqueado"):
                bloqueadas.add(clave)
                tipo_fijo = fila.get("TipoFijo")
                if (tipo_fijo and self._es_tipo_400(tipo_fijo)) or (
                    not tipo_fijo and fila.get("YaEnMaestro400")
                ):
                    fijas_400.add(clave)
            elif info and not info.get("Permite400", True):
                solo_300.add(clave)
            elif info and not info.get("Permite300", True):
                solo_400.add(clave)

        no_elegibles = bloqueadas | solo_300 | solo_400
        elegibles = [f for f in paises if self._clave_fila(f) not in no_elegibles]
        cajas_fijas_400 = sum(
            int(f.get("Cajas400", 0) or 0)
            for f in paises
            if self._clave_fila(f) in (fijas_400 | solo_400)
        )
        seleccion_400, _ = CalculadorCajasPaises.seleccionar_paises_400(
            elegibles,
            max(0, self.cajas_400_agotadas - cajas_fijas_400),
        )
        seleccion_400 = {normalizar(p) for p in seleccion_400}
        # Los que ya estan en el maestro 400 se mantienen marcados.
        seleccion_400 |= {
            self._clave_fila(f) for f in elegibles if f.get("YaEnMaestro400")
        }
        seleccion_400 |= fijas_400 | solo_400
        seleccion_400 -= solo_300

        self.mostrar_tabla_paises(paises, seleccion_400)
        self.actualizar_totales_paises()

    def obtener_tipos_finales_paises(self, paises):
        try:
            return self.gestor_tipo_caja_pais.analizar_tipos_finales(
                [fila.get("Pais", "") for fila in paises]
            ) or {}
        except Exception:
            return {}

    def mostrar_detalle_tipos_pais(self, pais):
        item = self.paises_vars.get(pais) or {}
        datos = item.get("datos") or {}
        info = datos.get("TiposFinales") or {}
        pais = str(datos.get("Pais", "") or pais).split("|")[0]
        lineas = [pais, ""]
        if datos.get("TipoFijo"):
            lineas.extend([
                "Este pais tiene tiendas con distintos tipos de caja, por eso se",
                "calcula en una linea por tipo. Esta linea: " + str(datos["TipoFijo"])
                + " -> " + format(float(datos.get("VolumenM3", 0) or 0), ".6f") + " m3, "
                + str(datos.get("Cajas400" if self._es_tipo_400(datos["TipoFijo"]) else "Cajas300", 0))
                + " cajas " + ("400" if self._es_tipo_400(datos["TipoFijo"]) else "300") + ".",
                "",
            ])
        if info.get("Motivo"):
            lineas.extend([info["Motivo"], ""])
        actual = info.get("TipoCajaPaisActual") or "no esta en TipoCajaPais"
        lineas.append("TipoCajaPais actual: " + actual)
        lineas.append("")
        lineas.append("Tiendas en TipoCajaTiendaAMayores (mandan sobre el pais):")
        for tipo, tiendas in sorted((info.get("EjemplosAMayores") or {}).items()):
            total = (info.get("TiendasAMayores") or {}).get(tipo, len(tiendas))
            lineas.append(
                "- " + tipo + ": " + str(total) + " tiendas ("
                + ", ".join(str(t) for t in tiendas)
                + (" ..." if total > len(tiendas) else "") + ")"
            )
        lineas.append("")
        lineas.append("Resto de tiendas del pais (TipoCajaInicial homologado):")
        resto = info.get("TiendasResto") or {}
        if not resto:
            lineas.append("- ninguna")
        for tipo, tiendas in sorted((info.get("EjemplosResto") or {}).items()):
            total = resto.get(tipo, len(tiendas))
            lineas.append(
                "- " + tipo + ": " + str(total) + " tiendas ("
                + ", ".join(str(t) for t in tiendas)
                + (" ..." if total > len(tiendas) else "") + ")"
            )
        if info.get("Bloqueado"):
            lineas.extend([
                "",
                "El pais no se puede cambiar a 300/400 desde aqui y al cargar el",
                "maestro se conserva tal como esta. Para desbloquearlo hay que",
                "corregir TipoCajaTiendaAMayores o TipoCajaPais en Maestros.",
            ])
        messagebox.showinfo("Tipos de caja de " + pais, "\n".join(lineas), parent=self.ventana)

    def obtener_paises_400_maestro_actual(self):
        """Devuelve Pais -> TipoCajaPais para paises actualmente 400.

        Se lee desde SQLite porque es el maestro operativo que utiliza la
        aplicacion despues de cargar Configuracion.xlsx. La funcion es
        defensiva: si la tabla aun no existe o hay un error puntual, no bloquea
        el calculo de paises; simplemente no resalta ningun pais.
        """
        tipos_validos = {"4_Nueva_40", "3_Usada_40"}
        resultado = {}

        conexion = getattr(self.bd, "conexion", None)
        if conexion is None:
            conexion = getattr(self.gestor_tipo_caja_pais, "conexion", None)
        if conexion is None:
            return resultado

        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT Pais, TipoCajaPais FROM TipoCajaPais")
            for pais, tipo in cursor.fetchall():
                pais_normalizado = self.gestor_tipo_caja_pais.normalizar_pais(pais)
                tipo_normalizado = self.gestor_tipo_caja_pais.normalizar_tipo(tipo)
                if pais_normalizado and tipo_normalizado in tipos_validos:
                    resultado[pais_normalizado] = tipo_normalizado
        except Exception:
            return {}

        return resultado

    def enriquecer_tipos_400_paises(self, paises):
        diagnosticos = self.gestor_tipo_caja_pais.analizar_paises(
            [fila.get("Pais", "") for fila in paises]
        )
        por_pais = {
            self.gestor_tipo_caja_pais.normalizar_pais(fila.get("Pais", "")): fila
            for fila in diagnosticos
        }

        for fila in paises:
            clave = self.gestor_tipo_caja_pais.normalizar_pais(
                fila.get("Pais", "")
            )
            diagnostico = por_pais.get(clave, {
                "Pais": clave,
                "Estado": "SIN_INFORMACION",
                "TipoCaja400": "",
                "Descripcion": "No se ha podido determinar el tipo de caja.",
            })
            fila["DiagnosticoTipo400"] = diagnostico
            fila["TipoCaja400Maestro"] = (
                self.gestor_tipo_caja_pais.texto_tipo_para_tabla(diagnostico)
            )

    def mostrar_tabla_paises(self, paises, seleccion_400):
        self.limpiar_tabla_paises()
        seleccion = set(seleccion_400 or [])

        for indice, fila in enumerate(paises):
            fila_ui = indice + 1
            clave = self._clave_fila(fila)
            tipo_fijo = str(fila.get("TipoFijo", "") or "")
            pais_mostrado = str(fila.get("Pais", ""))
            if tipo_fijo:
                pais_mostrado += "  -  " + tipo_fijo
            seleccionada_400 = clave in seleccion
            ya_en_maestro = bool(fila.get("YaEnMaestro400"))
            tipo_actual_maestro = str(fila.get("TipoCajaPaisActual", "") or "")
            info = fila.get("TiposFinales") or {}
            bloqueado = bool(info.get("Bloqueado"))
            permite_300 = bool(info.get("Permite300", True)) and not bloqueado
            permite_400 = bool(info.get("Permite400", True)) and not bloqueado
            motivo = str(info.get("Motivo", "") or "")

            if bloqueado:
                color_fondo = "#f9cb9c"
            elif not (permite_300 and permite_400):
                color_fondo = "#fff2cc"
            elif ya_en_maestro:
                color_fondo = "#d9ead3"
            else:
                color_fondo = "#ffffff"
            color_fondo_check = color_fondo if color_fondo != "#ffffff" else self.ventana.cget("bg")
            negrita = ("Arial", 9, "bold")
            normal = ("Arial", 9)

            var300 = tk.IntVar(value=0 if seleccionada_400 else 1)
            var400 = tk.IntVar(value=1 if seleccionada_400 else 0)
            self.paises_vars[clave] = {
                "300": var300,
                "400": var400,
                "datos": fila,
                "Fijo400": 1 if seleccionada_400 else 0,
            }

            def celda(columna, texto, **opciones):
                etiqueta = tk.Label(
                    self.frame_paises,
                    text=texto,
                    padx=6,
                    pady=1,
                    bd=1,
                    relief="groove",
                    bg=color_fondo,
                    **opciones,
                )
                etiqueta.grid(row=fila_ui, column=columna, sticky="nsew")
                return etiqueta

            celda(0, pais_mostrado, anchor="w", font=negrita if (ya_en_maestro or tipo_fijo) else normal)
            celda(1, format(float(fila.get("VolumenM3", 0.0) or 0.0), ".6f"), anchor="e")

            # En una linea fija solo se ensena el numero del tipo que lleva.
            texto300 = str(int(fila.get("Cajas300", 0) or 0))
            texto400 = str(int(fila.get("Cajas400", 0) or 0))
            if tipo_fijo:
                if self._es_tipo_400(tipo_fijo):
                    texto300 = "-"
                else:
                    texto400 = "-"
            tk.Checkbutton(
                self.frame_paises,
                text=texto300,
                variable=var300,
                bg=color_fondo_check,
                activebackground=color_fondo_check,
                pady=0,
                command=lambda p=clave: self.cambiar_tipo_pais(p, "300"),
                state="normal" if permite_300 else "disabled",
            ).grid(row=fila_ui, column=2, sticky="nsew")
            tk.Checkbutton(
                self.frame_paises,
                text=texto400,
                variable=var400,
                bg=color_fondo_check,
                activebackground=color_fondo_check,
                pady=0,
                command=lambda p=clave: self.cambiar_tipo_pais(p, "400"),
                state="normal" if permite_400 else "disabled",
            ).grid(row=fila_ui, column=3, sticky="nsew")

            diagnostico = fila.get("DiagnosticoTipo400", {}) or {}
            if tipo_fijo or bloqueado:
                texto_tipo = "-"
                color_tipo = "#666666"
            else:
                texto_tipo = str(fila.get("TipoCaja400Maestro", ""))
                color_tipo = "#006100" if diagnostico.get("Estado", "") == "OK" else "#9c0006"
            celda(4, texto_tipo, anchor="center", fg=color_tipo, font=negrita)

            texto_maestro = ("400  " + tipo_actual_maestro) if ya_en_maestro else ""
            celda(
                5, texto_maestro, anchor="center",
                fg="#006100" if ya_en_maestro else "#000000",
                font=negrita if ya_en_maestro else normal,
            )

            texto_aviso = ""
            if tipo_fijo:
                texto_aviso = "PAIS CON 2 TIPOS - linea fija " + (
                    "(cuenta en 400)" if self._es_tipo_400(tipo_fijo) else "(cuenta en 300)"
                )
            elif motivo:
                texto_aviso = motivo
            aviso = celda(
                6, texto_aviso, anchor="w",
                fg="#9c0006" if bloqueado else "#7f6000",
                font=negrita if texto_aviso else normal,
                cursor="hand2" if texto_aviso else "",
            )
            if texto_aviso:
                aviso.bind(
                    "<Button-1>",
                    lambda _e, p=clave: self.mostrar_detalle_tipos_pais(p),
                )

    def cambiar_tipo_pais(self, pais, tipo):
        item = self.paises_vars.get(pais)
        if not item:
            return
        info = (item.get("datos") or {}).get("TiposFinales") or {}
        bloqueado = bool(info.get("Bloqueado"))
        if bloqueado or (tipo == "300" and not info.get("Permite300", True)) \
                or (tipo == "400" and not info.get("Permite400", True)):
            # Opcion no permitida: se vuelve al estado fijo de la fila.
            fijo_400 = int(item.get("Fijo400", 0))
            item["400"].set(fijo_400)
            item["300"].set(1 - fijo_400)
            self.actualizar_totales_paises()
            return
        if tipo == "300":
            # Siempre queda exactamente un tipo seleccionado por pais.
            item["300"].set(1)
            item["400"].set(0)
        else:
            item["400"].set(1)
            item["300"].set(0)
        self.actualizar_totales_paises()

    def actualizar_totales_paises(self):
        cajas300 = 0
        cajas400 = 0
        paises300 = 0
        paises400 = 0
        errores_tipo_400 = 0
        paises_ya_en_maestro = 0
        paises_bloqueados = set()

        for item in self.paises_vars.values():
            datos = item["datos"]
            bloqueado = bool((datos.get("TiposFinales") or {}).get("Bloqueado"))
            if bloqueado:
                paises_bloqueados.add(str(datos.get("Pais", "")))
            if datos.get("YaEnMaestro400"):
                paises_ya_en_maestro += 1
            if item["400"].get():
                cajas400 += int(datos.get("Cajas400", 0) or 0)
                paises400 += 1
                diagnostico = datos.get("DiagnosticoTipo400", {}) or {}
                if diagnostico.get("Estado") != "OK" and not bloqueado:
                    errores_tipo_400 += 1
            elif item["300"].get():
                cajas300 += int(datos.get("Cajas300", 0) or 0)
                paises300 += 1

        objetivo = int(self.cajas_400_agotadas or 0)
        diferencia = objetivo - cajas400
        if diferencia >= 0:
            situacion = "pendientes de reutilizar: " + str(diferencia)
        else:
            situacion = "exceso sobre disponibles: " + str(abs(diferencia))

        aprovechamiento = 0.0
        if objetivo > 0:
            aprovechamiento = min(cajas400, objetivo) * 100.0 / objetivo

        total = cajas300 + cajas400
        self.lbl_objetivo_400.config(
            text="Cajas 400 reutilizables desde carruseles: " + str(objetivo)
        )

        texto_errores = ""
        if errores_tipo_400 > 0:
            texto_errores = (
                "   |   ERRORES TIPO 400: " + str(errores_tipo_400)
                + " (no se podran guardar)"
            )

        self.lbl_seleccion_paises.config(
            text=(
                "Caja 300: " + str(cajas300) + " cajas / " + str(paises300) + " paises"
                + "   |   Caja 400: " + str(cajas400) + " cajas / " + str(paises400) + " paises"
                + "   |   TOTAL SELECCIONADO: " + str(total)
                + "   |   " + situacion
                + "   |   aprovechamiento 400: " + format(aprovechamiento, ".1f") + "%"
                + "   |   ya en maestro 400: " + str(paises_ya_en_maestro)
                + (
                    "   |   PAISES CON 2 TIPOS (bloqueados): " + str(len(paises_bloqueados))
                    if paises_bloqueados else ""
                )
                + texto_errores
            ),
            fg="#9c0006" if errores_tipo_400 > 0 else "#000000",
        )

        if hasattr(self, "btn_cargar_paises_400"):
            self.btn_cargar_paises_400.config(
                state="normal" if self.paises_vars else "disabled"
            )

    def obtener_paises_400_seleccionados(self):
        seleccionados = []
        if not self.resumen_paises:
            return seleccionados

        for fila in self.resumen_paises.get("Paises", []) or []:
            if fila.get("TipoFijo"):
                continue
            clave = _clave_fila(self.gestor_tipo_caja_pais, fila)
            item = self.paises_vars.get(clave)
            if item and item["400"].get() and not _pais_bloqueado(self, clave):
                seleccionados.append(clave)
        return seleccionados


    def _texto_vista_previa_maestro(self, plan, seleccionados):
        eliminar = plan.get("Eliminar", []) or []
        lineas = [
            "Se sincronizara el maestro con los paises marcados como Caja 400.",
            "Paises Caja 400 seleccionados: " + str(len(seleccionados)),
            "Paises no seleccionados que se eliminaran: " + str(len(eliminar)),
            "",
            "El maestro final contendra exclusivamente los paises Caja 400.",
            "Los paises marcados como Caja 300 y cualquier otro pais existente",
            "que no este seleccionado se eliminaran de Excel y SQLite.",
            "",
            "Conversion aplicada:",
            "- Nueva -> 4_Nueva_40",
            "- Reutilizada/Usada -> 3_Usada_40",
            "",
            "Paises nuevos: " + str(len(plan.get("Anadir", []))),
            "Ya existentes con el mismo tipo: " + str(len(plan.get("SinCambios", []))),
            "Existentes con un tipo diferente: " + str(len(plan.get("Conflictos", []))),
            "",
            "Paises que quedaran en el maestro:",
        ]

        diagnosticos = {
            fila.get("Pais", ""): fila
            for fila in plan.get("Diagnosticos", [])
        }
        if seleccionados:
            for pais in seleccionados[:40]:
                diagnostico = diagnosticos.get(pais, {})
                lineas.append(
                    "- " + pais + " -> " + str(diagnostico.get("TipoCaja400", ""))
                )
            if len(seleccionados) > 40:
                lineas.append(
                    "... y " + str(len(seleccionados) - 40) + " paises mas."
                )
        else:
            lineas.append("- Ninguno. El maestro TipoCajaPais quedara vacio.")

        if eliminar:
            lineas.extend(["", "Paises que se eliminaran:"])
            for fila in eliminar[:30]:
                lineas.append(
                    "- " + fila.get("Pais", "")
                    + " (" + fila.get("TipoActual", "") + ")"
                )
            if len(eliminar) > 30:
                lineas.append(
                    "... y " + str(len(eliminar) - 30) + " paises mas."
                )

        conservados = plan.get("Conservados") or {}
        if conservados:
            lineas.extend(["", "Paises BLOQUEADOS (2 tipos de caja) que se conservan sin cambios:"])
            for pais, tipo in sorted(conservados.items()):
                lineas.append("- " + pais + " (" + str(tipo) + ")")

        if plan.get("Conflictos"):
            lineas.extend([
                "",
                "Los paises seleccionados con un valor diferente se preguntaran uno a uno.",
                "No se sustituira su tipo sin confirmacion expresa.",
            ])

        lineas.extend([
            "",
            "Se actualizara Configuracion.xlsx y la tabla SQLite TipoCajaPais.",
            "Se creara una copia de seguridad antes de guardar.",
            "",
            "¿Continuar?",
        ])
        return "\n".join(lineas)

    def cargar_paises_400_en_maestro(self):
        seleccionados = self.obtener_paises_400_seleccionados()
        if not self.resumen_paises:
            messagebox.showwarning(
                "Falta calculo de paises",
                "Primero debes ejecutar CALCULAR PAISES.",
                parent=self.ventana,
            )
            return

        try:
            bloqueados = _paises_bloqueados(self)
            if bloqueados:
                plan = self.gestor_tipo_caja_pais.preparar_actualizacion(
                    seleccionados,
                    conservar=bloqueados,
                )
            else:
                plan = self.gestor_tipo_caja_pais.preparar_actualizacion(
                    seleccionados
                )
        except Exception as error:
            messagebox.showerror(
                "Error preparando el maestro",
                str(error),
                parent=self.ventana,
            )
            return

        errores = plan.get("Errores", [])
        if errores:
            messagebox.showerror(
                "No se puede actualizar TipoCajaPais",
                self.gestor_tipo_caja_pais.texto_errores(errores),
                parent=self.ventana,
            )
            return

        if not messagebox.askyesno(
            "Sincronizar TipoCajaPais",
            self._texto_vista_previa_maestro(plan, seleccionados),
            parent=self.ventana,
        ):
            return

        # El diccionario representa el maestro final completo. Todos los paises
        # que no aparezcan aqui se eliminaran de Excel y SQLite.
        maestro_objetivo = {
            fila["Pais"]: fila["TipoCaja400"]
            for fila in plan.get("Diagnosticos", [])
            if fila.get("Estado") == "OK"
        }
        # Paises bloqueados (dos tipos de caja): se conservan tal cual.
        for pais, tipo in (plan.get("Conservados") or {}).items():
            maestro_objetivo[pais] = tipo
        conflictos_conservados = 0

        for conflicto in plan.get("Conflictos", []):
            respuesta = messagebox.askyesnocancel(
                "TipoCajaPais ya existente",
                (
                    "Pais: " + conflicto["Pais"] + "\n\n"
                    + "Valor actual: " + conflicto["TipoActual"] + "\n"
                    + "Valor calculado: " + conflicto["TipoNuevo"] + "\n\n"
                    + "SI: sustituir por el valor calculado.\n"
                    + "NO: conservar el valor actual.\n"
                    + "CANCELAR: cancelar toda la operacion."
                ),
                parent=self.ventana,
            )
            if respuesta is None:
                return
            if respuesta:
                maestro_objetivo[conflicto["Pais"]] = conflicto["TipoNuevo"]
            else:
                maestro_objetivo[conflicto["Pais"]] = conflicto["TipoActual"]
                conflictos_conservados += 1

        try:
            resultado = self.gestor_tipo_caja_pais.guardar_maestro_seleccionado(
                maestro_objetivo
            )
        except PermissionError as error:
            messagebox.showerror(
                "Configuracion.xlsx abierto",
                str(error),
                parent=self.ventana,
            )
            return
        except Exception as error:
            messagebox.showerror(
                "Error guardando TipoCajaPais",
                "No se ha completado la actualizacion.\n\n" + str(error),
                parent=self.ventana,
            )
            return

        anadidos = resultado.get("Anadidos", {}) or {}
        modificados = resultado.get("Modificados", {}) or {}
        eliminados = resultado.get("Eliminados", {}) or {}
        sin_cambios = resultado.get("SinCambios", {}) or {}
        backup = resultado.get("Backup")

        lineas = [
            "Sincronizacion del maestro finalizada.",
            "",
            "Paises seleccionados para caja 400: " + str(len(seleccionados)),
            "Anadidos al maestro: " + str(len(anadidos)),
            "Tipos actualizados: " + str(len(modificados)),
            "Paises eliminados por no estar seleccionados: " + str(len(eliminados)),
            "Ya existentes sin cambios: " + str(len(sin_cambios)),
            "Conflictos conservados: " + str(conflictos_conservados),
            "Total final en TipoCajaPais: " + str(resultado.get("TotalMaestro", 0)),
            "",
        ]
        if backup:
            lineas.append(
                "Configuracion.xlsx y reparto.db se han sincronizado correctamente."
            )
        else:
            lineas.append("El maestro ya coincidia exactamente con la seleccion.")

        if backup:
            lineas.extend(["", "Backup:", str(backup)])

        messagebox.showinfo(
            "TipoCajaPais sincronizado",
            "\n".join(lineas),
            parent=self.ventana,
        )


    def ejecutar(self):
        self.ventana.wait_window()
