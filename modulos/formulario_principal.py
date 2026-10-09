import tkinter as tk
from tkinter import messagebox

from modulos.version_aplicacion import NOMBRE_VERSION
from modulos.sincronizador import Sincronizador

from modulos.formulario_reparto_normal import FormularioRepartoNormal
from modulos.formulario_reparto_un_carrusel import FormularioRepartoUnCarrusel
from modulos.formulario_reparto_paises import FormularioRepartoPaises
from modulos.formulario_calculo_adelanto import FormularioCalculoAdelanto
from modulos.formulario_maestros import FormularioMaestros
from modulos.formulario_calculo_cajas_pedido import FormularioCalculoCajasPedido
from modulos.formulario_reparto_por_lados import FormularioRepartoPorLados
from modulos.ventanas_tk import preparar_formulario_navegable

try:
    from modulos.formulario_busca_fuera_tabla import FormularioBuscaFueraTabla
except Exception:
    FormularioBuscaFueraTabla = None


class FormularioPrincipal:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, resultado_tiendas_web=None):

        self.ventana = tk.Tk()
        self.ventana.title("Calculo de Tablas de Reparto - " + NOMBRE_VERSION)
        self.ventana.geometry("980x810")
        self.ventana.resizable(True, True)

        self.resultado_tiendas_web = resultado_tiendas_web
        self.formularios_abiertos = {}

        self.crear_controles()
        preparar_formulario_navegable(self.ventana, maximizar=True)
        self.actualizar_estado_tiendas_web(resultado_tiendas_web)

        if (
            resultado_tiendas_web is not None
            and resultado_tiendas_web.get("exito") is False
        ):
            resultado_aviso = dict(resultado_tiendas_web)
            self.ventana.after(
                500,
                lambda: self.mostrar_aviso_tiendas_web(resultado_aviso),
            )

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = tk.Frame(self.ventana)
        contenedor.pack(fill="both", expand=True, padx=28, pady=24)

        titulo = tk.Label(
            contenedor,
            text="CALCULO DE TABLAS DE REPARTO",
            font=("Arial", 20, "bold")
        )
        titulo.pack(pady=(0, 6))

        subtitulo = tk.Label(
            contenedor,
            text="Selecciona el tipo de calculo que quieres realizar.",
            font=("Arial", 11)
        )
        subtitulo.pack(pady=(0, 20))

        marco_tiendas_web = tk.LabelFrame(
            contenedor,
            text="Estado Tiendas_Web",
            padx=10,
            pady=8,
        )
        marco_tiendas_web.pack(fill="x", pady=(0, 12))

        self.lbl_estado_tiendas_web = tk.Label(
            marco_tiendas_web,
            text="Comprobando Tiendas_Web...",
            font=("Arial", 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_estado_tiendas_web.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 12),
        )

        self.boton_reintentar_tiendas_web = tk.Button(
            marco_tiendas_web,
            text="REINTENTAR TIENDAS WEB",
            width=24,
            command=self.reintentar_tiendas_web,
        )
        self.boton_reintentar_tiendas_web.pack(side="right")

        panel = tk.Frame(contenedor)
        panel.pack(fill="both", expand=True)

        self.crear_boton_menu(
            panel,
            0,
            0,
            "REPARTO NORMAL",
            "Dos carruseles",
            "#d9ead3",
            self.abrir_reparto_normal
        )

        self.crear_boton_menu(
            panel,
            0,
            1,
            "REPARTO UN CARRUSEL",
            "CLA 1 o CLA 2",
            "#fff2cc",
            self.abrir_reparto_un_carrusel
        )

        self.crear_boton_menu(
            panel,
            1,
            0,
            "REPARTO CON PAISES FIJOS",
            "Forzar paises por carrusel",
            "#d9eaf7",
            self.abrir_reparto_paises
        )

        self.crear_boton_menu(
            panel,
            1,
            1,
            "CALCULO ADELANTO",
            "Subpedido + pedido completo",
            "#eadcf8",
            self.abrir_calculo_adelanto
        )

        self.crear_boton_menu(
            panel,
            2,
            0,
            "BUSCA FUERA DE TABLA",
            "Huecos libres + fuera de tabla",
            "#d9d2e9",
            self.abrir_busca_fuera_tabla
        )

        self.crear_boton_menu(
            panel,
            2,
            1,
            "CALCULO DE CAJAS PARA PEDIDO",
            "XDOC + limpieza + mas unidades",
            "#cfe2f3",
            self.abrir_calculo_cajas_pedido
        )

        self.crear_boton_menu(
            panel,
            3,
            0,
            "MAESTROS / CONFIGURACION",
            "Mantenimiento de tablas maestras",
            "#f4cccc",
            self.abrir_maestros
        )

        self.crear_boton_menu(
            panel,
            3,
            1,
            "REPARTO POR LADOS",
            "Seleccion manual de 1 o 2 lados fisicos",
            "#d0e0e3",
            self.abrir_reparto_por_lados
        )

        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)
        for fila in range(4):
            panel.grid_rowconfigure(fila, weight=1)

        pie = tk.Frame(contenedor)
        pie.pack(fill="x", pady=(18, 0))

        tk.Label(
            pie,
            text=NOMBRE_VERSION,
            font=("Arial", 8),
            fg="#666666"
        ).pack(side="left")

        tk.Button(
            pie,
            text="Salir",
            width=18,
            height=2,
            command=self.ventana.destroy
        ).pack(side="right")

    #---------------------------------------------------------
    # Estado de Tiendas_Web
    #---------------------------------------------------------
    @staticmethod
    def _formatear_numero(valor):
        try:
            return format(int(valor or 0), ",").replace(",", ".")
        except Exception:
            return str(valor or 0)

    @staticmethod
    def _formatear_fecha(valor):
        texto = str(valor or "").strip()
        if texto == "":
            return "No registrada (copia creada por una version anterior)"

        try:
            from datetime import datetime

            fecha = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")
            return fecha.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            return texto

    def _consultar_estado_tiendas_web(self):
        sincronizador = Sincronizador()
        try:
            estado = sincronizador.obtener_estado_tiendas_web()
            return {
                "exito": None,
                "ruta": estado.get("ruta_ultima", ""),
                "nombre_archivo": estado.get("nombre_ultima", ""),
                "fecha_hora": estado.get("fecha_ultima", ""),
                "registros": estado.get("registros_locales", 0),
                "tipo_error": "",
                "descripcion_error": "",
                "error_tecnico": "",
                **estado,
            }
        finally:
            sincronizador.cerrar()

    def actualizar_estado_tiendas_web(self, resultado=None):
        if resultado is None:
            try:
                resultado = self._consultar_estado_tiendas_web()
            except Exception as error:
                resultado = {
                    "exito": False,
                    "hay_copia_local": False,
                    "registros_locales": 0,
                    "fecha_ultima": "",
                    "nombre_ultima": "",
                    "descripcion_error": str(error),
                }

        self.resultado_tiendas_web = resultado

        if resultado.get("exito") is True:
            fecha = self._formatear_fecha(resultado.get("fecha_hora"))
            tiendas = self._formatear_numero(resultado.get("registros"))
            texto = (
                "TIENDAS_WEB actualizado correctamente: "
                + fecha
                + " | Tiendas: "
                + tiendas
            )
            color = "#176b2c"

        elif resultado.get("hay_copia_local"):
            fecha = self._formatear_fecha(resultado.get("fecha_ultima"))
            tiendas = self._formatear_numero(
                resultado.get("registros_locales")
            )
            texto = (
                "TIENDAS_WEB: usando copia local | Ultima carga: "
                + fecha
                + " | Tiendas: "
                + tiendas
            )
            color = "#9a6500"

        else:
            texto = (
                "TIENDAS_WEB NO DISPONIBLE: no existe una copia local valida. "
                "Reintenta cuando la red permita leer el fichero."
            )
            color = "#a61b1b"

        self.lbl_estado_tiendas_web.config(text=texto, fg=color)

    def _crear_mensaje_tiendas_web(self, resultado):
        ruta = str(resultado.get("ruta", "") or "")
        descripcion = str(resultado.get("descripcion_error", "") or "")

        lineas = [
            "No se ha podido actualizar Tiendas_Web.",
            "",
        ]

        if ruta:
            lineas.extend(["Fichero:", ruta, ""])

        if descripcion:
            lineas.extend([descripcion, ""])

        if resultado.get("hay_copia_local"):
            lineas.extend(
                [
                    "La aplicacion continuara utilizando la ultima copia local valida.",
                    "",
                    "Ultima carga correcta: "
                    + self._formatear_fecha(resultado.get("fecha_ultima")),
                    "Tiendas disponibles: "
                    + self._formatear_numero(
                        resultado.get("registros_locales")
                    ),
                    "",
                    "Los datos pueden no estar actualizados.",
                ]
            )
        else:
            lineas.extend(
                [
                    "No existe ninguna copia local disponible.",
                    "",
                    "Las operaciones que necesitan conocer el pais de las tiendas "
                    "quedaran bloqueadas hasta completar una sincronizacion valida.",
                    "",
                    "Pulsa REINTENTAR TIENDAS WEB cuando el fichero vuelva a estar accesible.",
                ]
            )

        return "\n".join(lineas)

    def mostrar_aviso_tiendas_web(self, resultado, mostrar_exito=False):
        if resultado.get("exito") is True:
            if not mostrar_exito:
                return

            messagebox.showinfo(
                "Tiendas_Web actualizado",
                (
                    "Tiendas_Web se ha actualizado correctamente.\n\n"
                    "Fecha y hora: "
                    + self._formatear_fecha(resultado.get("fecha_hora"))
                    + "\nTiendas importadas: "
                    + self._formatear_numero(resultado.get("registros"))
                ),
                parent=self.ventana,
            )
            return

        mensaje = self._crear_mensaje_tiendas_web(resultado)

        if resultado.get("hay_copia_local"):
            messagebox.showwarning(
                "Tiendas_Web: usando copia local",
                mensaje,
                parent=self.ventana,
            )
        else:
            messagebox.showerror(
                "Tiendas_Web no disponible",
                mensaje,
                parent=self.ventana,
            )

    def reintentar_tiendas_web(self):
        boton = self.boton_reintentar_tiendas_web
        texto_original = boton.cget("text")

        boton.config(state="disabled", text="REINTENTANDO...")
        try:
            self.ventana.config(cursor="watch")
            self.ventana.update_idletasks()
        except Exception:
            pass

        sincronizador = Sincronizador()
        try:
            resultado = sincronizador.sincronizar_tiendas_web()
        except Exception as error:
            try:
                estado = sincronizador.obtener_estado_tiendas_web()
            except Exception:
                estado = {
                    "hay_copia_local": False,
                    "registros_locales": 0,
                    "ruta_ultima": "",
                    "nombre_ultima": "",
                    "fecha_ultima": "",
                    "registros_ultima": 0,
                }

            resultado = {
                "exito": False,
                "ruta": "",
                "descripcion_error": str(error),
                **estado,
            }
        finally:
            sincronizador.cerrar()
            try:
                self.ventana.config(cursor="")
            except Exception:
                pass
            boton.config(state="normal", text=texto_original)

        self.actualizar_estado_tiendas_web(resultado)
        self.mostrar_aviso_tiendas_web(resultado, mostrar_exito=True)

        try:
            boton.focus_set()
        except Exception:
            pass

    #---------------------------------------------------------
    # Crear boton del menu
    #---------------------------------------------------------
    def crear_boton_menu(self, panel, fila, columna, titulo, texto, color, comando):

        boton = tk.Button(
            panel,
            text=titulo + "\n" + texto,
            font=("Arial", 12, "bold"),
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
    # Ejecutar formulario secundario navegable
    #---------------------------------------------------------
    def ejecutar_formulario_secundario(self, clase_formulario):

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
    # Abrir formularios
    #---------------------------------------------------------
    def abrir_reparto_normal(self):
        self.ejecutar_formulario_secundario(FormularioRepartoNormal)

    def abrir_reparto_un_carrusel(self):
        self.ejecutar_formulario_secundario(FormularioRepartoUnCarrusel)

    def abrir_reparto_paises(self):
        self.ejecutar_formulario_secundario(FormularioRepartoPaises)

    def abrir_calculo_adelanto(self):
        self.ejecutar_formulario_secundario(FormularioCalculoAdelanto)

    def abrir_busca_fuera_tabla(self):
        if FormularioBuscaFueraTabla is None:
            return
        self.ejecutar_formulario_secundario(FormularioBuscaFueraTabla)

    def abrir_calculo_cajas_pedido(self):
        self.ejecutar_formulario_secundario(FormularioCalculoCajasPedido)

    def abrir_reparto_por_lados(self):
        self.ejecutar_formulario_secundario(FormularioRepartoPorLados)

    def abrir_maestros(self):
        self.ejecutar_formulario_secundario(FormularioMaestros)

    #---------------------------------------------------------
    # Ejecutar formulario
    #---------------------------------------------------------
    def ejecutar(self):
        self.ventana.mainloop()
