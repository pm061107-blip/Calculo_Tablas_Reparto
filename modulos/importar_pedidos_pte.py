from pathlib import Path
import csv

from bd.basedatos import BaseDatos


class ImportarPedidosPTE:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, fichero):

        self.fichero = Path(fichero)
        self.bd = BaseDatos()

    #---------------------------------------------------------
    # Obtener campo de una fila
    #---------------------------------------------------------
    def obtener_campo(self, fila, nombre):

        nombre_buscado = nombre.strip().upper()

        for clave, valor in fila.items():

            if clave is None:
                continue

            if clave.strip().upper() == nombre_buscado:

                if valor is None:
                    return ""

                return str(valor).strip()

        return ""

    #---------------------------------------------------------
    # Convertir a entero
    #---------------------------------------------------------
    def a_entero(self, valor, defecto=0):

        valor = str(valor).strip()

        if valor == "":
            return defecto

        valor = valor.replace(",", ".")

        try:
            return int(float(valor))
        except ValueError:
            return defecto

    #---------------------------------------------------------
    # Convertir a decimal
    #---------------------------------------------------------
    def a_decimal(self, valor, defecto=0):

        valor = str(valor).strip()

        if valor == "":
            return defecto

        valor = valor.replace(",", ".")

        try:
            return float(valor)
        except ValueError:
            return defecto

    #---------------------------------------------------------
    # Interpretar SKU
    # Ejemplo:
    # 0/7558/305/800/02/I/2026/W
    #---------------------------------------------------------
    def interpretar_sku(self, sku):

        partes = str(sku).strip().split("/")

        datos = {
            "Modelo": 0,
            "Calidad": 0,
            "Color": 0,
            "TallaAlfa": "",
            "Campaña": "",
            "Año": 0
        }

        if len(partes) >= 7:

            datos["Modelo"] = self.a_entero(partes[1])
            datos["Calidad"] = self.a_entero(partes[2])
            datos["Color"] = self.a_entero(partes[3])
            datos["TallaAlfa"] = partes[4].strip()
            datos["Campaña"] = partes[5].strip()
            datos["Año"] = self.a_entero(partes[6])

        return datos

    #---------------------------------------------------------
    # Interpretar fila de Pedidos PTE
    #---------------------------------------------------------
    def interpretar_fila(self, fila):

        sku = self.obtener_campo(fila, "Sku")
        datos_sku = self.interpretar_sku(sku)

        tienda = self.a_entero(
            self.obtener_campo(fila, "Id Loc.")
        )

        aparte = self.a_entero(
            self.obtener_campo(fila, "Apt.")
        )

        unidades = self.a_entero(
            self.obtener_campo(fila, "Dem.U")
        )

        lotes = self.a_decimal(
            self.obtener_campo(fila, "Dem.L")
        )

        if lotes > 0 and unidades > 0:
            uxl = int(round(unidades / lotes))
        else:
            uxl = 0

        talla_alfa = datos_sku["TallaAlfa"]

        talla_num = self.a_entero(talla_alfa)

        tipo_articulo = self.obtener_campo(fila, "T. Art.")

        if tipo_articulo != "":
            marca = tipo_articulo[0:1].upper()
        else:
            marca = "P"

        registro = {
            "MarcaComercial": marca,
            "Campaña": datos_sku["Campaña"],
            "Año": datos_sku["Año"],
            "Tienda": tienda,
            "Seccion": 1,
            "Aparte": aparte,
            "DescTienda": self.obtener_campo(fila, "Loc. Destino"),
            "Modelo": datos_sku["Modelo"],
            "Calidad": datos_sku["Calidad"],
            "Color": datos_sku["Color"],
            "TallaNum": talla_num,
            "TallaAlfa": talla_alfa,
            "POC": "",
            "Familia": 0,
            "Subfamilia": 0,
            "Carrusel": self.obtener_campo(fila, "Tabla Reparto"),
            "Estado": 0,
            "Unidades": unidades,
            "UoL": "U",
            "UxL": uxl,
            "Lotes": lotes
        }

        return registro

    #---------------------------------------------------------
    # Importar Pedidos PTE
    #---------------------------------------------------------
    def importar(self):

        print()
        print("----------------------------------------")
        print("IMPORTANDO PEDIDOS PTE")
        print("----------------------------------------")
        print("Archivo:", self.fichero)

        self.bd.vaciar_tabla("ESTAREPP")

        registros = 0
        errores = 0

        with open(
            self.fichero,
            "r",
            encoding="utf-8-sig",
            errors="ignore",
            newline=""
        ) as archivo:

            lector = csv.DictReader(
                archivo,
                delimiter=";"
            )

            for fila in lector:

                registro = self.interpretar_fila(fila)

                if registro["Tienda"] == 0:
                    errores += 1
                    continue

                self.bd.insertar_diccionario(
                    "ESTAREPP",
                    registro
                )

                registros += 1

        self.bd.guardar()

        total = self.bd.contar_registros("ESTAREPP")

        print("Registros importados :", registros)
        print("Registros descartados :", errores)
        print("Registros en SQLite  :", total)
        print("----------------------------------------")

        return True
        