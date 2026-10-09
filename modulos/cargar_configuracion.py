from datetime import datetime
from pathlib import Path
import shutil

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from bd.basedatos import BaseDatos


class CargarConfiguracion:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self):
        self.bd = BaseDatos()
        self.archivo = Path(__file__).parent.parent / "datos_iniciales" / "Configuracion.xlsx"

    #---------------------------------------------------------
    # Asegurar hoja TiendasXDOC sin sobrescribir maestros
    #---------------------------------------------------------
    def asegurar_hoja_tiendas_xdoc(self):
        """
        Crea la hoja TiendasXDOC si no existe y migra sin perdida la version
        anterior de dos columnas. PerfilVolumetria se conserva por compatibilidad,
        pero su valor se fuerza siempre a 01_UNICA.
        """
        if not self.archivo.exists():
            raise Exception("No existe datos_iniciales/Configuracion.xlsx")

        libro = openpyxl.load_workbook(self.archivo)
        cambios = False

        if "TiendasXDOC" not in libro.sheetnames:
            hoja = libro.create_sheet("TiendasXDOC")
            hoja["A1"] = "Tienda"
            hoja["B1"] = "ToleranciaXDOC"
            hoja["C1"] = "PerfilVolumetria"
            cambios = True
        else:
            hoja = libro["TiendasXDOC"]
            cabeceras = {
                str(celda.value or "").strip().lower(): celda.column
                for celda in hoja[1]
            }
            if "perfilvolumetria" not in cabeceras:
                columna = max(3, hoja.max_column + 1)
                hoja.cell(row=1, column=columna, value="PerfilVolumetria")
                cambios = True
            else:
                columna = cabeceras["perfilvolumetria"]

            for fila in range(2, hoja.max_row + 1):
                tienda = hoja.cell(row=fila, column=1).value
                if tienda is None or str(tienda).strip() == "":
                    continue
                valor_actual = str(hoja.cell(row=fila, column=columna).value or "").strip().upper()
                if valor_actual != "01_UNICA":
                    hoja.cell(row=fila, column=columna, value="01_UNICA")
                    cambios = True

        if not cambios:
            libro.close()
            return False

        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = self.archivo.parent / ("Configuracion_BACKUP_PRE_XDOC_V17_1_" + fecha + ".xlsx")
        shutil.copy2(self.archivo, backup)

        for celda in hoja[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="1F4E78")
            celda.alignment = Alignment(horizontal="center")

        hoja.column_dimensions["A"].width = 16
        hoja.column_dimensions["B"].width = 22
        hoja.column_dimensions["C"].width = 24
        hoja.freeze_panes = "A2"

        libro.save(self.archivo)
        libro.close()

        print("Hoja TiendasXDOC creada/actualizada en Configuracion.xlsx")
        print("Backup creado:", backup)
        return True

    #---------------------------------------------------------
    # Cargar una hoja
    #---------------------------------------------------------
    def cargar_hoja(self, nombre_hoja, obligatoria=True):
        libro = openpyxl.load_workbook(self.archivo, data_only=True)

        if nombre_hoja not in libro.sheetnames:
            libro.close()
            if obligatoria:
                raise Exception("No existe la hoja " + nombre_hoja + " en Configuracion.xlsx")
            return 0

        hoja = libro[nombre_hoja]
        columnas = [celda.value for celda in hoja[1]]

        self.bd.vaciar_tabla(nombre_hoja)
        total = 0

        for fila in hoja.iter_rows(min_row=2, values_only=True):
            if all(valor is None or str(valor).strip() == "" for valor in fila):
                continue

            registro = {}
            for i, valor in enumerate(fila):
                if i >= len(columnas):
                    break
                columna = columnas[i]
                if columna is None or str(columna).strip() == "":
                    continue
                registro[str(columna).strip()] = valor

            if registro:
                self.bd.insertar_diccionario(nombre_hoja, registro)
                total += 1

        self.bd.guardar()
        libro.close()
        return total

    #---------------------------------------------------------
    # Cargar configuracion
    #---------------------------------------------------------
    def cargar_configuracion(self):
        self.asegurar_hoja_tiendas_xdoc()

        self.cargar_hoja("TiposDeCaja")
        self.cargar_hoja("TipoCajaPais")
        self.cargar_hoja("TipoCajaTiendaAMayores")
        self.cargar_hoja("TablasDistribucionClasificador")
        self.cargar_hoja("TiendasXDOC", obligatoria=False)
