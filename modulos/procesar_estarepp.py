from bd.basedatos import BaseDatos


TIPO_CAJA_DEFECTO = "1_Nueva_30"


class ProcesarESTAREPP:

    TABLAS_ORIGEN_PERMITIDAS = {
        "ESTAREPP",
        "CAJAS_PEDIDO_ESCENARIO_ACTIVO",
        "CAJAS_PEDIDO_ESCENARIO_DESCARTADO",
    }

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, tabla_origen="ESTAREPP", bd=None):
        """Crear el procesador indicando de forma opcional la tabla origen.

        Compatibilidad admitida:
        - ProcesarESTAREPP()
        - ProcesarESTAREPP(bd=base_datos)
        - ProcesarESTAREPP(tabla_origen="CAJAS_PEDIDO_ESCENARIO_ACTIVO", bd=base_datos)
        - ProcesarESTAREPP(tabla_origen="CAJAS_PEDIDO_ESCENARIO_DESCARTADO", bd=base_datos)
        - ProcesarESTAREPP(base_datos)  # llamadas antiguas posicionales

        La deteccion del objeto BaseDatos en el primer argumento evita romper
        integraciones anteriores, mientras que ``tabla_origen`` permite procesar
        de forma segura el pedido materializado del escenario seleccionado.
        """

        # Compatibilidad con llamadas antiguas en las que el primer argumento
        # era directamente la instancia de BaseDatos.
        if tabla_origen is not None and not isinstance(tabla_origen, str):
            if bd is not None:
                raise TypeError(
                    "Se ha indicado la base de datos dos veces al crear "
                    "ProcesarESTAREPP."
                )
            bd = tabla_origen
            tabla_origen = "ESTAREPP"

        tabla_origen = str(tabla_origen or "ESTAREPP").strip().upper()
        if tabla_origen not in self.TABLAS_ORIGEN_PERMITIDAS:
            raise ValueError(
                "Tabla de origen no permitida para procesar ESTAREPP: "
                + tabla_origen
            )

        self.bd = bd if bd is not None else BaseDatos()
        self.tabla_origen = tabla_origen

        # Diccionario de trabajo del motor
        self.tmp = {}

        # Tiendas a las que se les asigna TipoCaja por defecto
        self.tiendas_tipo_caja_defecto = []

    #---------------------------------------------------------
    # Procesar
    #---------------------------------------------------------
    def procesar(self):

        if self.bd.contar_registros("Tiendas_Web") <= 0:
            raise RuntimeError(
                "Tiendas_Web no contiene ninguna tienda disponible.\n\n"
                "No se puede procesar el pedido porque la aplicacion no puede "
                "determinar el pais de las tiendas.\n\n"
                "Vuelve al menu principal, pulsa REINTENTAR TIENDAS WEB y "
                "repite la importacion cuando la conexion de red este disponible."
            )

        self.crear_tmp()

        self.actualizar_pais()

        self.actualizar_tipocaja_inicial()

        self.actualizar_tipos_caja()

        self.actualizar_tipocajapais()

        self.actualizar_tipocajatiendaamayores()

        self.aplicar_tipocaja_por_defecto()

        self.guardar_tmp()

        self.mostrar_aviso_tipocaja_por_defecto()

    #---------------------------------------------------------
    # Crear TMP en memoria
    #---------------------------------------------------------
    def crear_tmp(self):

        registros = self.bd.consultar("""

            SELECT

                Tienda,
                Aparte,
                Lotes

            FROM """ + self.tabla_origen + """

        """)

        self.tmp = {}

        for tienda, aparte, lotes in registros:

            clave = (tienda, aparte)

            if clave not in self.tmp:

                self.tmp[clave] = {

                    "Tienda": tienda,
                    "Aparte": aparte,
                    "Lotes": 0,
                    "Pais": "",
                    "TipoCaja": ""

                }

            self.tmp[clave]["Lotes"] += lotes

    #---------------------------------------------------------
    # Actualizar Pais
    #---------------------------------------------------------
    def actualizar_pais(self):

        datos = self.bd.consultar("""

            SELECT
                Tienda,
                Pais

            FROM Tiendas_Web

        """)

        dic_paises = {}

        for tienda, pais in datos:

            dic_paises[tienda] = pais

        for registro in self.tmp.values():

            tienda = registro["Tienda"]

            registro["Pais"] = dic_paises.get(tienda, "")

    #---------------------------------------------------------
    # Actualizar TipoCaja Inicial
    #---------------------------------------------------------
    def actualizar_tipocaja_inicial(self):

        datos = self.bd.consultar("""

            SELECT
                Tienda,
                TipoCajaInicial

            FROM TipoCajaInicial

        """)

        dic_tipocaja = {}

        for tienda, tipo in datos:

            dic_tipocaja[tienda] = tipo

        for registro in self.tmp.values():

            tienda = registro["Tienda"]

            registro["TipoCaja"] = dic_tipocaja.get(tienda, "")

    #---------------------------------------------------------
    # Actualizar TiposDeCaja
    #---------------------------------------------------------
    def actualizar_tipos_caja(self):

        datos = self.bd.consultar("""

            SELECT
                TipoGenerico,
                TipoCaja

            FROM TiposDeCaja

        """)

        dic_tipos = {}

        for tipo_generico, tipo_caja in datos:

            clave = str(tipo_generico).strip().upper()

            dic_tipos[clave] = tipo_caja

        for registro in self.tmp.values():

            tipo = str(registro["TipoCaja"]).strip().upper()

            if tipo in dic_tipos:

                registro["TipoCaja"] = dic_tipos[tipo]

    #---------------------------------------------------------
    # Actualizar TipoCajaPais
    #---------------------------------------------------------
    def actualizar_tipocajapais(self):

        datos = self.bd.consultar("""

            SELECT
                Pais,
                TipoCajaPais

            FROM TipoCajaPais

        """)

        dic_paises = {}

        for pais, tipo in datos:

            clave = str(pais).strip().upper()
            dic_paises[clave] = tipo

        for registro in self.tmp.values():

            pais = str(registro["Pais"]).strip().upper()

            if pais in dic_paises:

                registro["TipoCaja"] = dic_paises[pais]

    #---------------------------------------------------------
    # Actualizar TipoCajaTiendaAMayores
    #---------------------------------------------------------
    def actualizar_tipocajatiendaamayores(self):

        datos = self.bd.consultar("""

            SELECT
                Tienda,
                TipoCaja

            FROM TipoCajaTiendaAMayores

        """)

        dic_tiendas = {}

        for tienda, tipo in datos:

            dic_tiendas[tienda] = tipo

        for registro in self.tmp.values():

            tienda = registro["Tienda"]

            if tienda in dic_tiendas:

                registro["TipoCaja"] = dic_tiendas[tienda]

    #---------------------------------------------------------
    # Comprobar si TipoCaja esta vacio
    #---------------------------------------------------------
    def tipocaja_vacio(self, tipo_caja):

        if tipo_caja is None:
            return True

        texto = str(tipo_caja).strip()

        if texto == "":
            return True

        if texto.upper() in ["NONE", "NULL"]:
            return True

        return False

    #---------------------------------------------------------
    # Aplicar TipoCaja por defecto
    #---------------------------------------------------------
    def aplicar_tipocaja_por_defecto(self):

        self.tiendas_tipo_caja_defecto = []

        for registro in self.tmp.values():

            if not self.tipocaja_vacio(registro.get("TipoCaja", "")):
                continue

            registro["TipoCaja"] = TIPO_CAJA_DEFECTO

            self.tiendas_tipo_caja_defecto.append({
                "Tienda": registro.get("Tienda", ""),
                "Aparte": registro.get("Aparte", ""),
                "Pais": registro.get("Pais", ""),
                "Lotes": registro.get("Lotes", 0),
                "TipoCaja": TIPO_CAJA_DEFECTO
            })

    #---------------------------------------------------------
    # Crear texto de aviso de TipoCaja por defecto
    #---------------------------------------------------------
    def crear_texto_aviso_tipocaja_por_defecto(self):

        total = len(self.tiendas_tipo_caja_defecto)

        if total == 0:
            return ""

        lineas = []

        lineas.append(
            "Hay " + str(total) + " tiendas/apartes sin TipoCaja informado."
        )
        lineas.append("")
        lineas.append(
            "Se les ha asignado automaticamente: " + TIPO_CAJA_DEFECTO
        )
        lineas.append("")
        lineas.append("Primeros registros afectados:")
        lineas.append("")

        limite = 20

        for registro in self.tiendas_tipo_caja_defecto[:limite]:
            lineas.append(
                "Tienda " + str(registro["Tienda"]) +
                " | Aparte " + str(registro["Aparte"]) +
                " | Pais " + str(registro["Pais"]) +
                " | Lotes " + str(round(registro["Lotes"], 2))
            )

        if total > limite:
            lineas.append("")
            lineas.append(
                "Hay " + str(total - limite) + " registros mas."
            )

        lineas.append("")
        lineas.append(
            "El reparto continua, pero conviene revisar TipoCajaInicial / TipoCajaPais."
        )

        return "\n".join(lineas)

    #---------------------------------------------------------
    # Mostrar aviso de TipoCaja por defecto
    #---------------------------------------------------------
    def mostrar_aviso_tipocaja_por_defecto(self):

        if len(self.tiendas_tipo_caja_defecto) == 0:
            return

        mensaje = self.crear_texto_aviso_tipocaja_por_defecto()

        print()
        print("========================================")
        print("AVISO TIPOCAJA POR DEFECTO")
        print("========================================")
        print(mensaje)
        print("========================================")
        print()

        try:
            import tkinter as tk
            from tkinter import messagebox

            raiz = tk.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            raiz.update()

            messagebox.showwarning(
                "TipoCaja por defecto",
                mensaje,
                parent=raiz
            )

            raiz.destroy()

        except Exception:
            # Si el aviso grafico falla, el proceso no debe romper el calculo.
            pass

    #---------------------------------------------------------
    # Guardar TMP_ESTAREPP
    #---------------------------------------------------------
    def guardar_tmp(self):

        self.bd.vaciar_tabla("TMP_ESTAREPP")

        for registro in self.tmp.values():

            self.bd.insertar_diccionario(

                "TMP_ESTAREPP",
                registro

            )

        self.bd.guardar()
