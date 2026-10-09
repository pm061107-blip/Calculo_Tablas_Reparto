import copy
import shutil
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import openpyxl

from bd.basedatos import BaseDatos
from modulos.ventanas_tk import preparar_formulario_navegable, crear_marco_scrollable


class FormularioMaestroBase:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        self.bd = BaseDatos()
        self.ventana_padre = ventana_padre

        self.titulo = "Maestro"
        self.tabla_bd = ""
        self.hoja_excel = ""
        self.columnas = []
        self.columnas_bd = []
        self.anchuras = {}
        self.aviso_guardado = ""

        self.datos = []
        self.indices_visibles = []
        self.filtro = tk.StringVar(value="")
        self.cambios_pendientes = False

        self.archivo_configuracion = (
            Path(__file__).resolve().parent.parent
            / "datos_iniciales"
            / "Configuracion.xlsx"
        )

    #---------------------------------------------------------
    # Iniciar formulario despues de configurar propiedades
    #---------------------------------------------------------
    def iniciar_formulario(self, ancho=1100, alto=680):

        self.ventana = tk.Toplevel(self.ventana_padre)
        self.ventana.title(self.titulo)
        self.ventana.geometry(str(ancho) + "x" + str(alto))
        self.ventana.resizable(True, True)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)
        preparar_formulario_navegable(self.ventana, parent=self.ventana_padre, maximizar=True)

        if len(self.columnas_bd) == 0:
            self.columnas_bd = list(self.columnas)

        self.crear_controles()
        self.cargar_datos_bd()

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        contenedor = crear_marco_scrollable(self.ventana, padx=14, pady=12)

        tk.Label(
            contenedor,
            text=self.titulo.upper(),
            font=("Arial", 16, "bold")
        ).pack(anchor="w")

        if self.aviso_guardado != "":
            tk.Label(
                contenedor,
                text=self.aviso_guardado,
                font=("Arial", 9),
                fg="#7a4f00",
                justify="left"
            ).pack(anchor="w", pady=(2, 8))

        barra = tk.Frame(contenedor)
        barra.pack(fill="x", pady=(8, 8))

        tk.Label(barra, text="Buscar:").pack(side="left", padx=(0, 4))

        entrada = tk.Entry(barra, textvariable=self.filtro, width=34)
        entrada.pack(side="left", padx=(0, 8))
        entrada.bind("<KeyRelease>", lambda evento: self.mostrar_datos())

        tk.Button(
            barra,
            text="Limpiar filtro",
            width=14,
            command=self.limpiar_filtro
        ).pack(side="left", padx=3)

        tk.Button(
            barra,
            text="Recargar desde Excel",
            width=20,
            command=self.recargar_desde_excel
        ).pack(side="right", padx=3)

        marco_tabla = tk.Frame(contenedor)
        marco_tabla.pack(fill="both", expand=True)

        self.tabla = ttk.Treeview(
            marco_tabla,
            columns=self.columnas,
            show="headings",
            selectmode="extended"
        )

        scroll_y = tk.Scrollbar(marco_tabla, orient="vertical", command=self.tabla.yview)
        scroll_x = tk.Scrollbar(marco_tabla, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        marco_tabla.grid_rowconfigure(0, weight=1)
        marco_tabla.grid_columnconfigure(0, weight=1)

        for columna in self.columnas:
            self.tabla.heading(columna, text=columna)
            self.tabla.column(
                columna,
                width=self.anchuras.get(columna, 130),
                anchor="center"
            )

        self.tabla.bind("<Double-1>", self.editar_celda_evento)
        self.tabla.bind("<Delete>", lambda evento: self.borrar_filas())
        self.tabla.bind("<Control-c>", lambda evento: self.copiar_filas())
        self.tabla.bind("<Control-C>", lambda evento: self.copiar_filas())
        self.tabla.bind("<Control-v>", lambda evento: self.pegar_desde_excel())
        self.tabla.bind("<Control-V>", lambda evento: self.pegar_desde_excel())

        botones = tk.Frame(contenedor)
        botones.pack(fill="x", pady=(10, 0))

        tk.Button(
            botones,
            text="Añadir fila",
            width=14,
            command=self.anadir_fila
        ).pack(side="left", padx=3)

        tk.Button(
            botones,
            text="Borrar fila",
            width=14,
            command=self.borrar_filas
        ).pack(side="left", padx=3)

        tk.Button(
            botones,
            text="Copiar",
            width=12,
            command=self.copiar_filas
        ).pack(side="left", padx=3)

        tk.Button(
            botones,
            text="Pegar desde Excel",
            width=18,
            command=self.pegar_desde_excel
        ).pack(side="left", padx=3)

        tk.Button(
            botones,
            text="Guardar cambios",
            width=18,
            bg="#d9ead3",
            command=self.guardar_cambios
        ).pack(side="left", padx=12)

        tk.Button(
            botones,
            text="Cerrar",
            width=14,
            command=self.cerrar
        ).pack(side="right", padx=3)

        self.lbl_estado = tk.Label(
            contenedor,
            text="",
            font=("Arial", 9),
            anchor="w"
        )
        self.lbl_estado.pack(fill="x", pady=(8, 0))

    #---------------------------------------------------------
    # Cargar datos desde SQLite
    #---------------------------------------------------------
    def cargar_datos_bd(self):

        columnas_sql = ", ".join(self.columnas_bd)

        registros = self.bd.consultar(
            "SELECT " + columnas_sql + " FROM " + self.tabla_bd
        )

        self.datos = []

        for registro in registros:
            self.datos.append(["" if valor is None else valor for valor in registro])

        self.cambios_pendientes = False
        self.mostrar_datos()

    #---------------------------------------------------------
    # Cargar datos desde Configuracion.xlsx
    #---------------------------------------------------------
    def cargar_datos_excel(self):

        if not self.archivo_configuracion.exists():
            raise Exception("No existe Configuracion.xlsx en datos_iniciales.")

        libro = openpyxl.load_workbook(self.archivo_configuracion, data_only=True)

        if self.hoja_excel not in libro.sheetnames:
            raise Exception("No existe la hoja " + self.hoja_excel + " en Configuracion.xlsx.")

        hoja = libro[self.hoja_excel]
        cabeceras = []

        for celda in hoja[1]:
            cabeceras.append(celda.value)

        for columna in self.columnas:
            if columna not in cabeceras:
                raise Exception(
                    "La hoja " + self.hoja_excel + " no tiene la columna " + columna + "."
                )

        indices = [cabeceras.index(columna) for columna in self.columnas]
        datos = []

        for fila in hoja.iter_rows(min_row=2, values_only=True):

            if fila is None:
                continue

            registro = []
            vacia = True

            for indice in indices:
                valor = fila[indice] if indice < len(fila) else None
                if valor is not None and str(valor).strip() != "":
                    vacia = False
                registro.append("" if valor is None else valor)

            if not vacia:
                datos.append(registro)

        return datos

    #---------------------------------------------------------
    # Recargar desde Excel
    #---------------------------------------------------------
    def recargar_desde_excel(self):

        if self.cambios_pendientes:
            if not messagebox.askyesno(
                "Cambios pendientes",
                "Hay cambios sin guardar. Si recargas desde Excel se perderan. ¿Continuar?",
                parent=self.ventana
            ):
                return

        try:
            self.datos = self.cargar_datos_excel()
            self.cambios_pendientes = True
            self.mostrar_datos()
            messagebox.showinfo(
                "Recargado",
                "Datos cargados desde Configuracion.xlsx. Pulsa Guardar cambios para actualizar la base.",
                parent=self.ventana
            )
        except Exception as error:
            messagebox.showerror("Error recargando", str(error), parent=self.ventana)

    #---------------------------------------------------------
    # Mostrar datos con filtro
    #---------------------------------------------------------
    def mostrar_datos(self):

        for item in self.tabla.get_children():
            self.tabla.delete(item)

        texto = self.filtro.get().strip().upper()
        self.indices_visibles = []

        for indice, fila in enumerate(self.datos):

            mostrar = True

            if texto != "":
                mostrar = False
                for valor in fila:
                    if texto in str(valor).upper():
                        mostrar = True
                        break

            if not mostrar:
                continue

            iid = str(len(self.indices_visibles))
            self.indices_visibles.append(indice)
            self.tabla.insert("", "end", iid=iid, values=fila)

        self.actualizar_estado()

    #---------------------------------------------------------
    # Limpiar filtro
    #---------------------------------------------------------
    def limpiar_filtro(self):

        self.filtro.set("")
        self.mostrar_datos()

    #---------------------------------------------------------
    # Actualizar estado
    #---------------------------------------------------------
    def actualizar_estado(self):

        estado = "Filas: " + str(len(self.datos))

        if self.filtro.get().strip() != "":
            estado += " | visibles: " + str(len(self.indices_visibles))

        if self.cambios_pendientes:
            estado += " | cambios pendientes de guardar"

        self.lbl_estado.config(text=estado)

    #---------------------------------------------------------
    # Obtener indice real de item visible
    #---------------------------------------------------------
    def obtener_indice_real(self, item):

        indice_visible = int(item)
        return self.indices_visibles[indice_visible]

    #---------------------------------------------------------
    # Añadir fila
    #---------------------------------------------------------
    def anadir_fila(self):

        self.datos.append(["" for _ in self.columnas])
        self.cambios_pendientes = True
        self.mostrar_datos()

        ultimo_visible = None
        for item in self.tabla.get_children():
            ultimo_visible = item

        if ultimo_visible is not None:
            self.tabla.selection_set(ultimo_visible)
            self.tabla.see(ultimo_visible)

    #---------------------------------------------------------
    # Borrar filas seleccionadas
    #---------------------------------------------------------
    def borrar_filas(self):

        seleccion = self.tabla.selection()

        if len(seleccion) == 0:
            messagebox.showwarning("Sin seleccion", "Selecciona una o varias filas para borrar.", parent=self.ventana)
            return

        if not messagebox.askyesno(
            "Borrar filas",
            "Se borraran " + str(len(seleccion)) + " filas. ¿Continuar?",
            parent=self.ventana
        ):
            return

        indices = []

        for item in seleccion:
            indices.append(self.obtener_indice_real(item))

        for indice in sorted(indices, reverse=True):
            del self.datos[indice]

        self.cambios_pendientes = True
        self.mostrar_datos()

    #---------------------------------------------------------
    # Copiar filas seleccionadas
    #---------------------------------------------------------
    def copiar_filas(self):

        seleccion = self.tabla.selection()

        if len(seleccion) == 0:
            messagebox.showwarning("Sin seleccion", "Selecciona una o varias filas para copiar.", parent=self.ventana)
            return "break"

        lineas = []

        for item in seleccion:
            indice = self.obtener_indice_real(item)
            fila = self.datos[indice]
            lineas.append("\t".join([str(valor) for valor in fila]))

        texto = "\r\n".join(lineas)
        self.ventana.clipboard_clear()
        self.ventana.clipboard_append(texto)

        return "break"

    #---------------------------------------------------------
    # Pegar desde Excel
    #---------------------------------------------------------
    def pegar_desde_excel(self):

        try:
            texto = self.ventana.clipboard_get()
        except Exception:
            messagebox.showwarning("Portapapeles vacio", "No hay datos para pegar.", parent=self.ventana)
            return "break"

        filas = []

        for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):

            if linea.strip() == "":
                continue

            valores = linea.split("\t")

            if [v.strip() for v in valores] == [str(c).strip() for c in self.columnas]:
                continue

            if len(valores) > len(self.columnas):
                messagebox.showerror(
                    "Pegado incorrecto",
                    "La fila pegada tiene mas columnas de las esperadas.",
                    parent=self.ventana
                )
                return "break"

            while len(valores) < len(self.columnas):
                valores.append("")

            filas.append(valores)

        if len(filas) == 0:
            return "break"

        seleccion = self.tabla.selection()

        if len(seleccion) == 1 and len(filas) == 1:
            indice = self.obtener_indice_real(seleccion[0])
            self.datos[indice] = filas[0]
        else:
            for fila in filas:
                self.datos.append(fila)

        self.cambios_pendientes = True
        self.mostrar_datos()

        return "break"

    #---------------------------------------------------------
    # Editar celda con doble click
    #---------------------------------------------------------
    def editar_celda_evento(self, evento):

        item = self.tabla.identify_row(evento.y)
        columna_id = self.tabla.identify_column(evento.x)

        if item == "" or columna_id == "":
            return

        numero_columna = int(columna_id.replace("#", "")) - 1

        if numero_columna < 0 or numero_columna >= len(self.columnas):
            return

        indice = self.obtener_indice_real(item)
        valor_actual = self.datos[indice][numero_columna]
        nombre_columna = self.columnas[numero_columna]

        self.abrir_editor_celda(indice, numero_columna, nombre_columna, valor_actual)

    #---------------------------------------------------------
    # Abrir editor de celda
    #---------------------------------------------------------
    def abrir_editor_celda(self, indice, numero_columna, nombre_columna, valor_actual):

        ventana = tk.Toplevel(self.ventana)
        ventana.title("Editar celda")
        ventana.geometry("420x140")
        ventana.resizable(False, False)
        ventana.grab_set()
        ventana.lift()
        ventana.focus_force()

        tk.Label(
            ventana,
            text=nombre_columna,
            font=("Arial", 10, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 4))

        variable = tk.StringVar(value=str(valor_actual))
        entrada = tk.Entry(ventana, textvariable=variable, width=48)
        entrada.pack(fill="x", padx=12)
        entrada.focus_set()
        entrada.select_range(0, "end")

        botones = tk.Frame(ventana)
        botones.pack(fill="x", padx=12, pady=12)

        def aceptar():
            self.datos[indice][numero_columna] = variable.get()
            self.cambios_pendientes = True
            ventana.destroy()
            self.mostrar_datos()

        tk.Button(
            botones,
            text="Aceptar",
            width=12,
            command=aceptar
        ).pack(side="right", padx=4)

        tk.Button(
            botones,
            text="Cancelar",
            width=12,
            command=ventana.destroy
        ).pack(side="right", padx=4)

        entrada.bind("<Return>", lambda evento: aceptar())
        entrada.bind("<Escape>", lambda evento: ventana.destroy())

    #---------------------------------------------------------
    # Guardar cambios
    #---------------------------------------------------------
    def guardar_cambios(self):

        try:
            datos_limpios = self.validar_datos_completos()
        except Exception as error:
            messagebox.showerror("Validacion", str(error), parent=self.ventana)
            return

        if not messagebox.askyesno(
            "Guardar cambios",
            "Se creara una copia de seguridad de Configuracion.xlsx y se guardaran los cambios. ¿Continuar?",
            parent=self.ventana
        ):
            return

        try:
            backup = self.crear_backup_configuracion()
            self.guardar_excel(datos_limpios)
            self.guardar_bd(datos_limpios)
            self.datos = datos_limpios
            self.cambios_pendientes = False
            self.mostrar_datos()

            messagebox.showinfo(
                "Guardado correcto",
                "Cambios guardados en Configuracion.xlsx y en reparto.db.\n\nBackup:\n" + str(backup),
                parent=self.ventana
            )

        except PermissionError:
            messagebox.showerror(
                "Excel abierto",
                "No se pudo guardar Configuracion.xlsx. Cierra el archivo Excel y vuelve a guardar. No se ha actualizado la base.",
                parent=self.ventana
            )
        except Exception as error:
            messagebox.showerror("Error guardando", str(error), parent=self.ventana)

    #---------------------------------------------------------
    # Validar todos los datos
    #---------------------------------------------------------
    def validar_datos_completos(self):

        datos_limpios = []
        claves = set()

        for numero, fila in enumerate(self.datos, start=2):

            limpia = True
            for valor in fila:
                if str(valor).strip() != "":
                    limpia = False
                    break

            if limpia:
                continue

            fila_limpia = self.validar_fila(fila, numero)
            clave = self.obtener_clave_unica(fila_limpia)

            if clave is not None:
                if clave in claves:
                    raise Exception("Clave duplicada en la fila " + str(numero) + ": " + str(clave))
                claves.add(clave)

            datos_limpios.append(fila_limpia)

        return datos_limpios

    #---------------------------------------------------------
    # Validar fila - se sobreescribe en formularios hijos
    #---------------------------------------------------------
    def validar_fila(self, fila, numero_fila):

        return fila

    #---------------------------------------------------------
    # Clave unica - se sobreescribe en formularios hijos
    #---------------------------------------------------------
    def obtener_clave_unica(self, fila):

        return None

    #---------------------------------------------------------
    # Crear backup
    #---------------------------------------------------------
    def crear_backup_configuracion(self):

        if not self.archivo_configuracion.exists():
            raise Exception("No existe Configuracion.xlsx en datos_iniciales.")

        carpeta = self.archivo_configuracion.parent
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = carpeta / ("Configuracion_BACKUP_" + fecha + ".xlsx")
        shutil.copy2(self.archivo_configuracion, backup)

        return backup

    #---------------------------------------------------------
    # Guardar Excel
    #---------------------------------------------------------
    def guardar_excel(self, datos_limpios):

        libro = openpyxl.load_workbook(self.archivo_configuracion)

        if self.hoja_excel in libro.sheetnames:
            hoja = libro[self.hoja_excel]
        else:
            hoja = libro.create_sheet(self.hoja_excel)

        estilos = self.capturar_estilos_fila(hoja, 2)

        for columna, nombre in enumerate(self.columnas, start=1):
            hoja.cell(row=1, column=columna).value = nombre

        if hoja.max_row > 1:
            hoja.delete_rows(2, hoja.max_row - 1)

        for fila_excel, fila in enumerate(datos_limpios, start=2):
            for columna, valor in enumerate(fila, start=1):
                celda = hoja.cell(row=fila_excel, column=columna)
                celda.value = valor

                if columna in estilos:
                    estilo = estilos[columna]
                    celda.font = copy.copy(estilo["font"])
                    celda.fill = copy.copy(estilo["fill"])
                    celda.border = copy.copy(estilo["border"])
                    celda.alignment = copy.copy(estilo["alignment"])
                    celda.number_format = estilo["number_format"]
                    celda.protection = copy.copy(estilo["protection"])

        for columna in range(1, len(self.columnas) + 1):
            letra = openpyxl.utils.get_column_letter(columna)
            ancho_actual = hoja.column_dimensions[letra].width
            if ancho_actual is None or ancho_actual < 12:
                hoja.column_dimensions[letra].width = max(12, len(str(self.columnas[columna - 1])) + 2)

        libro.save(self.archivo_configuracion)

    #---------------------------------------------------------
    # Capturar estilos de fila existente
    #---------------------------------------------------------
    def capturar_estilos_fila(self, hoja, numero_fila):

        estilos = {}

        if hoja.max_row < numero_fila:
            return estilos

        for columna in range(1, len(self.columnas) + 1):
            celda = hoja.cell(row=numero_fila, column=columna)
            estilos[columna] = {
                "font": celda.font,
                "fill": celda.fill,
                "border": celda.border,
                "alignment": celda.alignment,
                "number_format": celda.number_format,
                "protection": celda.protection
            }

        return estilos

    #---------------------------------------------------------
    # Guardar en base de datos
    #---------------------------------------------------------
    def guardar_bd(self, datos_limpios):

        cursor = self.bd.conexion.cursor()

        try:
            cursor.execute("DELETE FROM " + self.tabla_bd)

            marcadores = ",".join(["?"] * len(self.columnas_bd))
            sql = "INSERT INTO " + self.tabla_bd + " VALUES (" + marcadores + ")"

            for fila in datos_limpios:
                cursor.execute(sql, tuple(fila))

            self.bd.conexion.commit()

        except Exception:
            self.bd.conexion.rollback()
            raise

    #---------------------------------------------------------
    # Utilidades de validacion
    #---------------------------------------------------------
    def texto_obligatorio(self, valor, campo, fila):

        texto = str(valor).strip()

        if texto == "":
            raise Exception("Fila " + str(fila) + ": " + campo + " es obligatorio.")

        return texto

    def entero_obligatorio(self, valor, campo, fila):

        texto = str(valor).strip()

        if texto == "":
            raise Exception("Fila " + str(fila) + ": " + campo + " es obligatorio.")

        try:
            return int(float(texto))
        except Exception:
            raise Exception("Fila " + str(fila) + ": " + campo + " debe ser numerico entero.")

    #---------------------------------------------------------
    # Cerrar
    #---------------------------------------------------------
    def cerrar(self):

        if self.cambios_pendientes:
            if not messagebox.askyesno(
                "Cambios pendientes",
                "Hay cambios sin guardar. ¿Cerrar igualmente?",
                parent=self.ventana
            ):
                return

        self.ventana.destroy()

    #---------------------------------------------------------
    # Ejecutar formulario
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
