from pathlib import Path
import csv
import tkinter as tk
from tkinter import filedialog

from bd.basedatos import BaseDatos


class ImportarContenedoresCajas:

    def __init__(self):
        self.bd = BaseDatos()
        self.ruta = None

    def seleccionar_fichero(self):
        ventana = tk.Tk()
        ventana.withdraw()
        ventana.attributes("-topmost", True)

        ruta = filedialog.askopenfilename(
            title="Importar contenedores del silo",
            filetypes=[("CSV", "*.csv"), ("Todos los ficheros", "*.*")]
        )

        ventana.destroy()
        if ruta == "":
            return False

        self.ruta = Path(ruta)
        return True

    def crear_tabla(self):
        # Es una tabla de trabajo importada en cada ejecucion. La recreamos para
        # asegurar que la estructura sea siempre la de esta version.
        self.bd.ejecutar("DROP TABLE IF EXISTS CAJAS_CONTENEDORES")
        self.bd.ejecutar("""
            CREATE TABLE CAJAS_CONTENEDORES (
                Matricula TEXT,
                TipoContenedor TEXT,
                EstContenedor TEXT,
                DispWms TEXT,
                SkuOriginal TEXT,
                EstadoMercancia TEXT,
                TipoProducto TEXT,
                Modelo TEXT,
                Calidad TEXT,
                Color TEXT,
                Talla INTEGER,
                Campana TEXT,
                Anio TEXT,
                Cd TEXT,
                UxL INTEGER,
                Unidades INTEGER,
                Lotes INTEGER,
                ReservadoL INTEGER,
                Posicion TEXT,
                Pasillo TEXT,
                Lado TEXT,
                X TEXT,
                Y TEXT,
                Profundidad TEXT,
                Celda TEXT,
                EstPosicion TEXT,
                Zona TEXT,
                TCM TEXT,
                TipoPosAlm TEXT,
                Disponible INTEGER,
                SKUClave TEXT,
                SKUCompleto TEXT
            )
        """)

    def crear_indices(self):
        for sql in [
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_CONT_DISP_SKU ON CAJAS_CONTENEDORES (Disponible, SKUCompleto)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_CONT_MATRICULA ON CAJAS_CONTENEDORES (Matricula)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_CONT_CELDA ON CAJAS_CONTENEDORES (Celda)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_CONT_PASILLO ON CAJAS_CONTENEDORES (Pasillo)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_CONT_VOL ON CAJAS_CONTENEDORES (SKUCompleto, TCM, EstadoMercancia, Unidades)"
        ]:
            self.bd.ejecutar(sql)

    def insertar_lote(self, registros):
        if not registros:
            return

        cursor = self.bd.conexion.cursor()
        cursor.executemany("""
            INSERT INTO CAJAS_CONTENEDORES
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, registros)
        self.bd.conexion.commit()

    def texto(self, valor):
        if valor is None:
            return ""
        return str(valor).strip()

    def numero(self, valor, defecto=0.0):
        texto = self.texto(valor).replace(",", ".")
        if texto == "":
            return defecto
        try:
            return float(texto)
        except Exception:
            return defecto

    def entero(self, valor, defecto=0):
        try:
            return int(float(self.texto(valor).replace(",", ".")))
        except Exception:
            return defecto

    def entero_texto(self, valor, ancho):
        texto = self.texto(valor)
        try:
            texto = str(int(float(texto.replace(",", "."))))
        except Exception:
            pass
        return texto.zfill(ancho)

    def talla_numerica(self, valor):
        """03, 3 y 3.0 representan la misma talla numerica: 3."""
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

    def crear_sku(self, modelo, calidad, color, talla, campana, anio):
        """
        UNICA clave de cruce de cajas:
        Modelo / Calidad / Color / Talla numerica / Campana / Anio.
        """
        return "/".join([
            self.entero_texto(modelo, 4),
            self.entero_texto(calidad, 3),
            self.entero_texto(color, 3),
            str(int(talla)),
            self.texto(campana).upper(),
            self.normalizar_anio(anio)
        ])

    def parsear_sku(self, sku):
        texto = self.texto(sku).replace(" ", "")
        partes = texto.split("/")
        while len(partes) < 8:
            partes.append("")

        tipo = self.entero_texto(partes[0], 1)
        modelo = self.entero_texto(partes[1], 4)
        calidad = self.entero_texto(partes[2], 3)
        color = self.entero_texto(partes[3], 3)
        talla = self.talla_numerica(partes[4])
        campana = self.texto(partes[5]).upper()
        anio = self.normalizar_anio(partes[6])
        cd = self.texto(partes[7]).upper()

        return tipo, modelo, calidad, color, talla, campana, anio, cd

    def parsear_posicion(self, posicion):
        texto = self.texto(posicion)
        partes = texto.split("_")
        while len(partes) < 5:
            partes.append("")

        pasillo, lado, x, y, profundidad = partes[:5]
        celda = "_".join([pasillo, lado, x, y])
        return pasillo, lado, x, y, profundidad, celda

    def es_disponible(self, fila, unidades, reservado, talla_valida=True):
        if not talla_valida:
            return 0

        matricula = self.texto(fila.get("Matrícula"))
        posicion = self.texto(fila.get("Posición"))
        if matricula == "" or posicion == "":
            return 0

        if self.texto(fila.get("Est.Contenedor")).upper() != "DISPONIBLE":
            return 0
        if self.texto(fila.get("Disp.Wms")).upper() != "SI":
            return 0
        if self.texto(fila.get("Est.Posición")).upper() != "OCUPADO":
            return 0
        if unidades <= 0:
            return 0
        if reservado > 0:
            return 0

        return 1

    def importar(self):
        if not self.seleccionar_fichero():
            return 0
        return self.importar_desde_ruta(self.ruta)

    def importar_desde_ruta(self, ruta):
        self.ruta = Path(ruta)
        self.crear_tabla()

        total = 0
        disponibles = 0
        talla_no_numerica = 0
        duplicadas = 0
        registros_lote = []
        tamano_lote = 10000
        matriculas_vistas = set()

        with open(self.ruta, "r", encoding="latin-1", errors="ignore", newline="") as archivo:
            lector = csv.DictReader(archivo, delimiter=";")

            columnas_obligatorias = [
                "Matrícula", "Est.Contenedor", "Disp.Wms", "Sku", "UxL",
                "Unidades", "Lotes", "Reservado(L)", "Posición", "Est.Posición", "TCM",
                "Estado de mercancía"
            ]
            for columna in columnas_obligatorias:
                if columna not in (lector.fieldnames or []):
                    raise Exception("Falta la columna obligatoria en Contenedores.csv: " + columna)

            for fila in lector:
                matricula = self.texto(fila.get("Matrícula"))

                # Una matricula identifica una caja fisica unica. Si el fichero
                # trae la misma matricula repetida, solo se conserva la primera.
                if matricula != "" and matricula in matriculas_vistas:
                    duplicadas += 1
                    continue
                if matricula != "":
                    matriculas_vistas.add(matricula)

                sku_original = self.texto(fila.get("Sku"))
                tipo, modelo, calidad, color, talla, campana, anio, cd = self.parsear_sku(sku_original)
                uxl = self.entero(fila.get("UxL"), 0)
                unidades = self.entero(fila.get("Unidades"), 0)
                lotes = self.entero(fila.get("Lotes"), 0)
                reservado = self.entero(fila.get("Reservado(L)"), 0)
                posicion = self.texto(fila.get("Posición"))
                pasillo, lado, x, y, profundidad, celda = self.parsear_posicion(posicion)

                talla_valida = talla is not None
                if not talla_valida:
                    talla_no_numerica += 1
                    sku = ""
                else:
                    sku = self.crear_sku(modelo, calidad, color, talla, campana, anio)

                disponible = self.es_disponible(fila, unidades, reservado, talla_valida)
                if disponible:
                    disponibles += 1

                # SKUClave y SKUCompleto se mantienen por compatibilidad con la
                # estructura existente. En esta version AMBOS contienen la unica
                # clave correcta de 6 campos.
                registro = (
                    matricula,
                    self.texto(fila.get("Tipo Contenedor")),
                    self.texto(fila.get("Est.Contenedor")),
                    self.texto(fila.get("Disp.Wms")),
                    sku_original,
                    self.texto(fila.get("Estado de mercancía")),
                    tipo,
                    modelo,
                    calidad,
                    color,
                    talla,
                    campana,
                    anio,
                    cd,
                    uxl,
                    unidades,
                    lotes,
                    reservado,
                    posicion,
                    pasillo,
                    lado,
                    x,
                    y,
                    profundidad,
                    celda,
                    self.texto(fila.get("Est.Posición")),
                    self.texto(fila.get("Zona")),
                    self.texto(fila.get("TCM")),
                    self.texto(fila.get("Tipo Pos.Alm.")),
                    disponible,
                    sku,
                    sku
                )

                registros_lote.append(registro)
                total += 1

                if len(registros_lote) >= tamano_lote:
                    self.insertar_lote(registros_lote)
                    registros_lote = []

        self.insertar_lote(registros_lote)
        self.crear_indices()
        self.bd.guardar()

        print()
        print("----------------------------------------")
        print("CONTENEDORES IMPORTADOS")
        print("Archivo:", self.ruta)
        print("Registros:", total)
        print("Disponibles para calculo:", disponibles)
        print("Matriculas duplicadas omitidas:", duplicadas)
        print("SKU omitidos por talla no numerica:", talla_no_numerica)
        print("Cruce SKU: Modelo/Calidad/Color/Talla/Campana/Anio")
        print("----------------------------------------")

        return total
