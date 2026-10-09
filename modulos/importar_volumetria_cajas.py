from pathlib import Path
import tkinter as tk
from tkinter import filedialog

from openpyxl import load_workbook

from bd.basedatos import BaseDatos


class ImportarVolumetriaCajas:

    PERFIL_VOLUMETRIA_FIJO = "01_UNICA"

    CAMPANA_CABECERAS = ["CAMPAÑA", "CAMPANA", "CAMP.", "CAMP", "CAMPAÑA TIPO", "CAMPANA TIPO"]
    ANIO_CABECERAS = ["AÑO", "ANO", "YEAR"]

    def __init__(self):
        self.bd = BaseDatos()
        self.ruta = None

    def seleccionar_fichero(self):
        ventana = tk.Tk()
        ventana.withdraw()
        ventana.attributes("-topmost", True)

        ruta = filedialog.askopenfilename(
            title="Importar volumetria del SKU",
            filetypes=[("Excel", "*.xlsx"), ("Todos los ficheros", "*.*")]
        )
        ventana.destroy()

        if ruta == "":
            return False
        self.ruta = Path(ruta)
        return True

    def crear_tabla(self):
        self.bd.ejecutar("DROP TABLE IF EXISTS CAJAS_VOLUMETRIA")
        self.bd.ejecutar("""
            CREATE TABLE CAJAS_VOLUMETRIA (
                TipoProducto TEXT,
                Modelo TEXT,
                Calidad TEXT,
                Color TEXT,
                Talla INTEGER,
                Campana TEXT,
                Anio TEXT,
                UxL INTEGER,
                EstadoMercancia TEXT,
                Descripcion TEXT,
                UdsBulto INTEGER,
                BultosPalet INTEGER,
                UXM TEXT,
                BloqEnt TEXT,
                TCM TEXT,
                SKUCompleto TEXT,
                SKUBase TEXT
            )
        """)

    def crear_indices(self):
        self.bd.ejecutar("CREATE INDEX IF NOT EXISTS IDX_CAJAS_VOL_SKU ON CAJAS_VOLUMETRIA (SKUCompleto)")
        self.bd.ejecutar("CREATE INDEX IF NOT EXISTS IDX_CAJAS_VOL_BASE ON CAJAS_VOLUMETRIA (SKUBase)")
        self.bd.ejecutar("CREATE INDEX IF NOT EXISTS IDX_CAJAS_VOL_SKU_PERFIL ON CAJAS_VOLUMETRIA (SKUCompleto, EstadoMercancia)")
        self.bd.ejecutar("CREATE INDEX IF NOT EXISTS IDX_CAJAS_VOL_BASE_PERFIL ON CAJAS_VOLUMETRIA (SKUBase, EstadoMercancia)")

    def insertar_lote(self, registros):
        if not registros:
            return
        cursor = self.bd.conexion.cursor()
        cursor.executemany("""
            INSERT INTO CAJAS_VOLUMETRIA
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, registros)
        self.bd.conexion.commit()

    def texto(self, valor):
        if valor is None:
            return ""
        return str(valor).strip()

    def normalizar_estado_mercancia(self, valor):
        perfil = self.texto(valor).upper().replace("-", "_").replace(" ", "_")
        while "__" in perfil:
            perfil = perfil.replace("__", "_")

        compacto = perfil.replace("_", "")
        if compacto in ("UNICA", "1UNICA", "01UNICA"):
            return self.PERFIL_VOLUMETRIA_FIJO

        return perfil


    def numero(self, valor, defecto=0):
        texto = self.texto(valor).replace(",", ".")
        if texto == "":
            return defecto
        try:
            numero = float(texto)
            return int(round(numero))
        except Exception:
            return defecto

    def entero(self, valor, defecto=0):
        return self.numero(valor, defecto)

    def entero_texto(self, valor, ancho):
        texto = self.texto(valor)
        try:
            texto = str(int(float(texto.replace(",", "."))))
        except Exception:
            pass
        return texto.zfill(ancho)

    def talla_numerica(self, valor):
        texto = self.texto(valor).replace(",", ".")
        if texto == "":
            return None
        try:
            numero = float(texto)
            entero = int(numero)
            if numero != entero:
                return None
            return entero
        except Exception:
            return None

    def normalizar_anio(self, valor):
        texto = self.texto(valor)
        try:
            return str(int(float(texto)))
        except Exception:
            return texto

    def crear_sku_base(self, modelo, calidad, color, talla):
        return "/".join([
            self.entero_texto(modelo, 4),
            self.entero_texto(calidad, 3),
            self.entero_texto(color, 3),
            str(int(talla))
        ])

    def crear_sku(self, modelo, calidad, color, talla, campana, anio):
        return self.crear_sku_base(modelo, calidad, color, talla) + "/" + self.texto(campana).upper() + "/" + self.normalizar_anio(anio)

    def buscar_fila_cabeceras(self, hoja):
        for indice, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
            valores = [self.texto(v).upper() for v in fila]
            if "MOD." in valores and "CAL." in valores and "COL." in valores and "TA." in valores:
                return indice, valores
        raise Exception("No se encontraron cabeceras validas en la volumetria.")

    def buscar_indice_opcional(self, mapa, candidatos):
        for nombre in candidatos:
            if nombre in mapa:
                return mapa[nombre]
        return None

    def importar(self):
        if not self.seleccionar_fichero():
            return 0
        return self.importar_desde_ruta(self.ruta)

    def importar_desde_ruta(self, ruta):
        self.ruta = Path(ruta)
        self.crear_tabla()

        libro = load_workbook(self.ruta, read_only=True, data_only=True)
        hoja = libro[libro.sheetnames[0]]
        fila_cabecera, cabeceras = self.buscar_fila_cabeceras(hoja)
        mapa = {cabecera: indice for indice, cabecera in enumerate(cabeceras) if cabecera != ""}

        indice_campana = self.buscar_indice_opcional(mapa, self.CAMPANA_CABECERAS)
        indice_anio = self.buscar_indice_opcional(mapa, self.ANIO_CABECERAS)

        def valor(fila, cabecera):
            indice = mapa.get(cabecera)
            if indice is None or indice >= len(fila):
                return None
            return fila[indice]

        def valor_indice(fila, indice):
            if indice is None or indice >= len(fila):
                return None
            return fila[indice]

        total = 0
        omitidos_talla = 0
        omitidos_otro_perfil = 0
        registros_lote = []
        tamano_lote = 10000

        for fila in hoja.iter_rows(min_row=fila_cabecera + 1, values_only=True):
            if fila is None:
                continue

            tipo = self.entero_texto(valor(fila, "PROD."), 1)
            modelo = self.entero_texto(valor(fila, "MOD."), 4)
            calidad = self.entero_texto(valor(fila, "CAL."), 3)
            color = self.entero_texto(valor(fila, "COL."), 3)
            talla = self.talla_numerica(valor(fila, "TA."))
            uxl = int(self.numero(valor(fila, "UXL"), 0))

            if modelo == "0000" and calidad == "000" and color == "000" and uxl == 0:
                continue
            if talla is None:
                omitidos_talla += 1
                continue

            if "EST.MERC." in mapa:
                perfil = self.normalizar_estado_mercancia(valor(fila, "EST.MERC."))
            else:
                # Si el fichero no trae la columna, toda su volumetria se trata
                # como 01_UNICA conforme a la regla operativa actual.
                perfil = self.PERFIL_VOLUMETRIA_FIJO

            if perfil != self.PERFIL_VOLUMETRIA_FIJO:
                omitidos_otro_perfil += 1
                continue

            campana = self.texto(valor_indice(fila, indice_campana)).upper()
            anio = self.normalizar_anio(valor_indice(fila, indice_anio))
            sku_base = self.crear_sku_base(modelo, calidad, color, talla)
            sku = self.crear_sku(modelo, calidad, color, talla, campana, anio) if campana != "" and anio != "" else ""

            registro = (
                tipo,
                modelo,
                calidad,
                color,
                talla,
                campana,
                anio,
                uxl,
                self.PERFIL_VOLUMETRIA_FIJO,
                self.texto(valor(fila, "DESCRIPCIÓN")),
                self.entero(valor(fila, "UDS./BULTO"), 0),
                self.entero(valor(fila, "BULTOS/PALET"), 0),
                self.texto(valor(fila, "UXM")),
                self.texto(valor(fila, "BLOQ.ENT.")),
                self.texto(valor(fila, "T.CONT.MED.")),
                sku,
                sku_base
            )

            registros_lote.append(registro)
            total += 1
            if len(registros_lote) >= tamano_lote:
                self.insertar_lote(registros_lote)
                registros_lote = []

        self.insertar_lote(registros_lote)
        self.crear_indices()
        self.bd.guardar()
        libro.close()

        print()
        print("----------------------------------------")
        print("VOLUMETRIA IMPORTADA")
        print("Archivo:", self.ruta)
        print("Registros validos 01_UNICA:", total)
        print("Omitidos por otro perfil:", omitidos_otro_perfil)
        print("Omitidos por talla no numerica:", omitidos_talla)
        print("Perfil de volumetria fijo:", self.PERFIL_VOLUMETRIA_FIJO)
        print("Cruce SKU objetivo: Modelo/Calidad/Color/Talla/Campana/Anio")
        if indice_campana is None or indice_anio is None:
            print("AVISO: este fichero no trae Campana y/o Anio como columnas.")
            print("La moda podra usar coincidencia base Modelo/Calidad/Color/Talla como respaldo.")
        print("----------------------------------------")

        return total
