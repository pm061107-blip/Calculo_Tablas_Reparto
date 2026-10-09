import csv
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from bd.basedatos import BaseDatos


COLUMNAS_REPARTO = [
    "Clasificador",
    "Lado",
    "Zona",
    "Tramo",
    "Bloque",
    "Destino",
    "Tienda",
    "Aparte",
    "Lotes",
    "TipoCaja",
    "Prioridad",
    "PrioridadOrden",
]


SQL_REPARTO = """
SELECT
    Clasificador,
    Lado,
    Zona,
    Tramo,
    Bloque,
    Destino,
    Tienda,
    Aparte,
    Lotes,
    TipoCaja,
    Prioridad,
    PrioridadOrden
FROM REPARTO_CLASIFICADOR
ORDER BY
    Clasificador,
    Destino,
    Tienda,
    Aparte
"""


# ---------------------------------------------------------
# Exportar REPARTO_CLASIFICADOR a CSV y Excel
# ---------------------------------------------------------
def exportar_reparto_clasificador(carpeta_destino=None, parent=None):
    """
    Exporta la tabla REPARTO_CLASIFICADOR de reparto.db.

    Genera dos archivos:
    - CSV separado por punto y coma.
    - Excel .xlsx.

    Uso desde un boton Tkinter:
        from modulos.exportar_reparto_clasificador import exportar_reparto_clasificador
        exportar_reparto_clasificador(parent=self.ventana)
    """

    ventana_temporal = None

    if parent is None and tk._default_root is None:
        ventana_temporal = tk.Tk()
        ventana_temporal.withdraw()
        parent = ventana_temporal

    if carpeta_destino is None:
        carpeta_destino = filedialog.askdirectory(
            title="Selecciona carpeta para exportar REPARTO_CLASIFICADOR",
            parent=parent,
        )

        if carpeta_destino is None or str(carpeta_destino).strip() == "":
            if ventana_temporal is not None:
                ventana_temporal.destroy()
            return None

    carpeta_destino = Path(carpeta_destino)
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    bd = BaseDatos()

    try:
        registros = bd.consultar(SQL_REPARTO)
    finally:
        bd.cerrar()

    if len(registros) == 0:
        messagebox.showwarning(
            "Sin datos",
            "La tabla REPARTO_CLASIFICADOR no tiene registros para exportar.",
            parent=parent,
        )

        if ventana_temporal is not None:
            ventana_temporal.destroy()

        return None

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    ruta_csv = carpeta_destino / ("REPARTO_CLASIFICADOR_" + fecha + ".csv")
    ruta_excel = carpeta_destino / ("REPARTO_CLASIFICADOR_" + fecha + ".xlsx")

    guardar_csv(ruta_csv, registros)
    guardar_excel(ruta_excel, registros)

    messagebox.showinfo(
        "Exportacion correcta",
        "Tabla REPARTO_CLASIFICADOR exportada correctamente.\n\n"
        + "CSV:\n"
        + str(ruta_csv)
        + "\n\nExcel:\n"
        + str(ruta_excel),
        parent=parent,
    )

    if ventana_temporal is not None:
        ventana_temporal.destroy()

    return {
        "csv": str(ruta_csv),
        "excel": str(ruta_excel),
        "registros": len(registros),
    }


# ---------------------------------------------------------
# Guardar CSV
# ---------------------------------------------------------
def guardar_csv(ruta_csv, registros):

    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(COLUMNAS_REPARTO)

        for registro in registros:
            escritor.writerow(list(registro))


# ---------------------------------------------------------
# Guardar Excel
# ---------------------------------------------------------
def guardar_excel(ruta_excel, registros):

    libro = Workbook()
    hoja = libro.active
    hoja.title = "REPARTO_CLASIFICADOR"

    relleno_cabecera = PatternFill("solid", fgColor="D9EAD3")
    fuente_cabecera = Font(bold=True)

    for columna, nombre in enumerate(COLUMNAS_REPARTO, start=1):
        celda = hoja.cell(row=1, column=columna)
        celda.value = nombre
        celda.font = fuente_cabecera
        celda.fill = relleno_cabecera
        celda.alignment = Alignment(horizontal="center")

    for fila_excel, registro in enumerate(registros, start=2):
        for columna, valor in enumerate(registro, start=1):
            hoja.cell(row=fila_excel, column=columna).value = valor

    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions

    for columna in range(1, len(COLUMNAS_REPARTO) + 1):
        letra = get_column_letter(columna)
        ancho = len(str(COLUMNAS_REPARTO[columna - 1])) + 2

        for fila in range(2, min(hoja.max_row, 200) + 1):
            valor = hoja.cell(row=fila, column=columna).value
            if valor is not None:
                ancho = max(ancho, len(str(valor)) + 2)

        hoja.column_dimensions[letra].width = min(max(ancho, 10), 28)

    libro.save(ruta_excel)


# ---------------------------------------------------------
# Ejecucion directa para pruebas
# ---------------------------------------------------------
if __name__ == "__main__":
    exportar_reparto_clasificador()
