from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog

from modulos.calculador_cajas_paises import CalculadorCajasPaises
from modulos.exportar_sin_volumetria import ExportadorSinVolumetria
from modulos.ventanas_tk import forzar_ventana_visible, preparar_formulario_navegable, crear_marco_scrollable
from modulos.dialogo_progreso import DialogoProgreso
from modulos.gestor_reset_calculos import GestorResetCalculos


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
        contenedor = crear_marco_scrollable(self.ventana, padx=0, pady=0)
        self.contenedor_principal = contenedor
        cabecera = tk.Frame(contenedor)
        cabecera.pack(fill="x", padx=16, pady=(12, 4))

        tk.Label(
            cabecera,
            text="VOLUMETRIA Y REUTILIZACION DE CAJAS POR PAIS",
            font=("Arial", 17, "bold"),
        ).pack(side="left")

        tk.Button(
            cabecera,
            text="Cerrar y volver",
            width=18,
            command=self.cerrar,
        ).pack(side="right")

        self.lbl_contexto = tk.Label(
            contenedor,
            text="",
            font=("Arial", 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_contexto.pack(fill="x", padx=18, pady=(0, 4))

        self.crear_boton_reset(contenedor)

        tk.Label(
            self.ventana,
            text=(
                "Este formulario utiliza el pedido, la volumetria, los contenedores "
                "y el ultimo calculo de cajas ya cargados en el formulario anterior."
            ),
            font=("Arial", 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=18, pady=(0, 8))

        self.crear_bloque_paises(contenedor)

    def crear_boton_reset(self, contenedor):
        tk.Button(
            contenedor,
            text="RESETEAR CALCULO DE PAISES",
            height=1,
            bg="#cc0000",
            fg="white",
            activebackground="#990000",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            command=self.resetear_calculo_paises,
        ).pack(fill="x", padx=18, pady=(0, 6))

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
        pedido = self.contar_tabla("ESTAREPP")
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
        marco.pack(fill="both", expand=True, padx=16, pady=(7, 12))

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
        self.lbl_seleccion_paises.pack(fill="x", pady=(8, 2))

        self.lbl_incidencias_paises = tk.Label(
            marco,
            text="",
            font=("Arial", 9),
            anchor="w",
            justify="left",
        )
        self.lbl_incidencias_paises.pack(fill="x", pady=(0, 5))

        alto_tabla = max(430, int(self.ventana.winfo_screenheight() or 760) - 285)
        contenedor_tabla = tk.Frame(marco, bd=1, relief="sunken", height=alto_tabla)
        contenedor_tabla.pack(fill="both", expand=True, pady=(2, 0))
        contenedor_tabla.pack_propagate(False)
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

        self._crear_cabecera_tabla_paises()

    def _crear_cabecera_tabla_paises(self):
        cabeceras = [
            "PAIS",
            "VOLUMEN m3",
            "CAJA 300",
            "CAJA 400",
            "TIPO 400 A GUARDAR",
            "MAESTRO ACTUAL",
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
        if self.contar_tabla("ESTAREPP") <= 0:
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
            self.resumen_paises = calculador.calcular()
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
        if self.contar_tabla("ESTAREPP") <= 0:
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

    def aplicar_seleccion_automatica_paises(self):
        if not self.resumen_paises:
            return

        paises = CalculadorCajasPaises.ordenar_paises(
            self.resumen_paises.get("Paises", []) or []
        )
        self.resumen_paises["Paises"] = paises
        self.enriquecer_tipos_400_paises(paises)

        maestro_400 = self.obtener_paises_400_maestro_actual()
        claves_calculadas = {
            self.gestor_tipo_caja_pais.normalizar_pais(fila.get("Pais", ""))
            for fila in paises
        }
        paises_maestro_en_calculo = set()
        for fila in paises:
            clave = self.gestor_tipo_caja_pais.normalizar_pais(
                fila.get("Pais", "")
            )
            tipo_actual = maestro_400.get(clave, "")
            fila["YaEnMaestro400"] = bool(tipo_actual)
            fila["TipoCajaPaisActual"] = tipo_actual
            if tipo_actual:
                paises_maestro_en_calculo.add(clave)

        seleccion_400, _ = CalculadorCajasPaises.seleccionar_paises_400(
            paises,
            self.cajas_400_agotadas,
        )
        seleccion_400 = set(seleccion_400) | paises_maestro_en_calculo

        # Si el maestro contiene paises 400 que no aparecen en el calculo actual,
        # no se muestran en la tabla porque no tienen demanda en este pedido.
        # La sincronizacion posterior sigue siendo exclusiva sobre los paises
        # marcados en la tabla visible.
        _ = claves_calculadas

        self.mostrar_tabla_paises(paises, seleccion_400)
        self.actualizar_totales_paises()

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

        seleccion_normalizada = {
            self.gestor_tipo_caja_pais.normalizar_pais(pais)
            for pais in seleccion_400
        }

        for indice, fila in enumerate(paises):
            fila_ui = indice + 1
            pais_mostrado = str(fila.get("Pais", ""))
            clave_pais = self.gestor_tipo_caja_pais.normalizar_pais(pais_mostrado)
            seleccionada_400 = clave_pais in seleccion_normalizada
            ya_en_maestro = bool(fila.get("YaEnMaestro400"))
            tipo_actual_maestro = str(fila.get("TipoCajaPaisActual", "") or "")
            color_fondo = "#d9ead3" if ya_en_maestro else "#ffffff"
            color_fondo_check = "#d9ead3" if ya_en_maestro else self.ventana.cget("bg")

            var300 = tk.IntVar(value=0 if seleccionada_400 else 1)
            var400 = tk.IntVar(value=1 if seleccionada_400 else 0)
            self.paises_vars[clave_pais] = {
                "300": var300,
                "400": var400,
                "datos": fila,
            }

            tk.Label(
                self.frame_paises,
                text=pais_mostrado,
                anchor="w",
                padx=6,
                pady=3,
                bd=1,
                relief="groove",
                bg=color_fondo,
                font=("Arial", 9, "bold") if ya_en_maestro else ("Arial", 9),
            ).grid(row=fila_ui, column=0, sticky="nsew")
            tk.Label(
                self.frame_paises,
                text=format(float(fila.get("VolumenM3", 0.0) or 0.0), ".6f"),
                anchor="e",
                padx=6,
                pady=3,
                bd=1,
                relief="groove",
                bg=color_fondo,
            ).grid(row=fila_ui, column=1, sticky="nsew")

            tk.Checkbutton(
                self.frame_paises,
                text=str(int(fila.get("Cajas300", 0) or 0)),
                variable=var300,
                bg=color_fondo_check,
                activebackground=color_fondo_check,
                command=lambda p=clave_pais: self.cambiar_tipo_pais(p, "300"),
            ).grid(row=fila_ui, column=2, sticky="nsew")

            tk.Checkbutton(
                self.frame_paises,
                text=str(int(fila.get("Cajas400", 0) or 0)),
                variable=var400,
                bg=color_fondo_check,
                activebackground=color_fondo_check,
                command=lambda p=clave_pais: self.cambiar_tipo_pais(p, "400"),
            ).grid(row=fila_ui, column=3, sticky="nsew")

            diagnostico = fila.get("DiagnosticoTipo400", {}) or {}
            estado = diagnostico.get("Estado", "")
            color_texto = "#006100" if estado == "OK" else "#9c0006"
            tk.Label(
                self.frame_paises,
                text=str(fila.get("TipoCaja400Maestro", "")),
                anchor="center",
                padx=6,
                pady=3,
                bd=1,
                relief="groove",
                fg=color_texto,
                bg=color_fondo,
                font=("Arial", 9, "bold"),
            ).grid(row=fila_ui, column=4, sticky="nsew")

            texto_maestro = ""
            if ya_en_maestro:
                texto_maestro = "YA EN MAESTRO 400"
                if tipo_actual_maestro:
                    texto_maestro += "\n" + tipo_actual_maestro
            tk.Label(
                self.frame_paises,
                text=texto_maestro,
                anchor="center",
                padx=6,
                pady=3,
                bd=1,
                relief="groove",
                fg="#006100" if ya_en_maestro else "#000000",
                bg=color_fondo,
                font=("Arial", 9, "bold") if ya_en_maestro else ("Arial", 9),
            ).grid(row=fila_ui, column=5, sticky="nsew")

    def cambiar_tipo_pais(self, pais, tipo):
        item = self.paises_vars.get(pais)
        if not item:
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

        for item in self.paises_vars.values():
            datos = item["datos"]
            if datos.get("YaEnMaestro400"):
                paises_ya_en_maestro += 1
            if item["400"].get():
                cajas400 += int(datos.get("Cajas400", 0) or 0)
                paises400 += 1
                diagnostico = datos.get("DiagnosticoTipo400", {}) or {}
                if diagnostico.get("Estado") != "OK":
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
            clave = self.gestor_tipo_caja_pais.normalizar_pais(
                fila.get("Pais", "")
            )
            item = self.paises_vars.get(clave)
            if item and item["400"].get():
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
