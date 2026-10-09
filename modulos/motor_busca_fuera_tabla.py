import copy
import csv
import io
import unicodedata
from pathlib import Path
from datetime import datetime

from modulos.motor_reparto import MotorReparto


class MotorBuscaFueraTabla(MotorReparto):

    TIPOS_CAJA = [
        "4_Nueva_40",
        "3_Usada_40",
        "2_Reutilizada_30",
        "1_Nueva_30",
    ]

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, clave_pedido_trabajo=None):

        super().__init__(clave_pedido_trabajo=clave_pedido_trabajo)

        self.tablas_activas = {
            1: self.crear_estructura_tabla_activa(),
            2: self.crear_estructura_tabla_activa(),
        }

        self.fuera_tabla = []
        self.dentro_tabla = []
        self.ultimo_resultado = []

        self.mapa_pedido = {}
        self.ubicaciones_existentes = {}
        self.carga_existente_por_cla = {1: [], 2: []}
        self.carga_desconocida = []
        self.advertencias = []
        self.resumen_analisis = None
        self.libres_utilizables = {1: 0, 2: 0}
        self.libres_sin_maestro = {1: 0, 2: 0}
        self.ocupados_sin_maestro = []

        self._plantilla_destinos = []
        self._firma_inamovibles = {}

        self.crear_tablas_trabajo()

    #---------------------------------------------------------
    # Crear estructura interna de tabla activa
    #---------------------------------------------------------
    def crear_estructura_tabla_activa(self):

        return {
            "Ruta": "",
            "Destinos": {},
            "ClavesOcupadas": set(),
            "TotalDestinos": 0,
            "Ocupados": 0,
            "OcupadosConTienda": 0,
            "BloqueadosSinTienda": 0,
            "Libres": 0,
        }

    #---------------------------------------------------------
    # Crear tablas de trabajo y auditoria
    #---------------------------------------------------------
    def crear_tablas_trabajo(self):

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS FUERA_TABLA_ACTIVA (
                Clasificador INTEGER,
                Destino INTEGER,
                Tienda INTEGER,
                Aparte INTEGER,
                Estado TEXT,
                ZonaOriginal TEXT,
                Ocupado INTEGER
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS FUERA_TABLA_PEDIDO (
                Tienda INTEGER,
                Aparte INTEGER,
                Lotes REAL,
                Pais TEXT,
                TipoCaja TEXT
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS FUERA_TABLA_EXISTENTE (
                Clasificador INTEGER,
                Lado INTEGER,
                Zona TEXT,
                Bloque INTEGER,
                Destino INTEGER,
                Tienda INTEGER,
                Aparte INTEGER,
                Lotes REAL,
                Pais TEXT,
                TipoCaja TEXT,
                CargaConocida INTEGER,
                Inamovible INTEGER
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS FUERA_TABLA_RESULTADO (
                Clasificador INTEGER,
                Lado INTEGER,
                Zona TEXT,
                Tramo INTEGER,
                Bloque INTEGER,
                Destino INTEGER,
                Tienda INTEGER,
                Aparte INTEGER,
                Lotes REAL,
                Pais TEXT,
                TipoCaja TEXT,
                Prioridad INTEGER,
                PrioridadOrden INTEGER
            )
        """)

    #---------------------------------------------------------
    # Invalidar un analisis anterior
    #---------------------------------------------------------
    def invalidar_analisis(self):

        self.fuera_tabla = []
        self.dentro_tabla = []
        self.ultimo_resultado = []
        self.mapa_pedido = {}
        self.ubicaciones_existentes = {}
        self.carga_existente_por_cla = {1: [], 2: []}
        self.carga_desconocida = []
        self.advertencias = []
        self.resumen_analisis = None
        self.libres_utilizables = {1: 0, 2: 0}
        self.libres_sin_maestro = {1: 0, 2: 0}
        self.ocupados_sin_maestro = []
        self._plantilla_destinos = []
        self._firma_inamovibles = {}

    #---------------------------------------------------------
    # Normalizar cabeceras
    #---------------------------------------------------------
    def normalizar_texto(self, texto):

        if texto is None:
            return ""

        texto = str(texto).strip().lower()
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(
            caracter
            for caracter in texto
            if unicodedata.category(caracter) != "Mn"
        )

        for caracter in [" ", ".", "/", "-", "_", "(", ")"]:
            texto = texto.replace(caracter, "")

        return texto

    #---------------------------------------------------------
    # Leer entero seguro
    #---------------------------------------------------------
    def leer_entero(self, valor, defecto=None):

        if valor is None:
            return defecto

        texto = str(valor).strip()

        if texto == "":
            return defecto

        try:
            return int(float(texto.replace(",", ".")))
        except Exception:
            return defecto

    #---------------------------------------------------------
    # Leer numero seguro
    #---------------------------------------------------------
    def leer_numero(self, valor, defecto=0):

        if valor is None:
            return defecto

        texto = str(valor).strip().replace(" ", "")

        if texto == "":
            return defecto

        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except Exception:
            return defecto

    #---------------------------------------------------------
    # Obtener valor por posibles nombres
    #---------------------------------------------------------
    def obtener_valor(self, fila, mapa, nombres):

        for nombre in nombres:
            clave = self.normalizar_texto(nombre)
            if clave in mapa:
                return fila.get(mapa[clave], "")

        return ""

    #---------------------------------------------------------
    # Normalizar TipoCaja
    #---------------------------------------------------------
    def normalizar_tipo_caja(self, tipo_caja):

        texto = str(tipo_caja or "").strip()

        if texto == "":
            return "1_Nueva_30"

        return texto

    #---------------------------------------------------------
    # Importar tabla activa de un carrusel
    #---------------------------------------------------------
    def importar_tabla_activa(self, clasificador, ruta_archivo):

        if clasificador not in [1, 2]:
            raise Exception("El clasificador debe ser 1 o 2.")

        ruta = Path(ruta_archivo)

        if not ruta.exists():
            raise Exception("No existe el fichero seleccionado.")

        destinos = {}

        try:
            contenido = ruta.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            contenido = ruta.read_text(encoding="latin-1", errors="ignore")

        lector = csv.DictReader(io.StringIO(contenido), delimiter=";")

        if lector.fieldnames is None:
            raise Exception("El fichero no tiene cabecera.")

        mapa = {}
        for cabecera in lector.fieldnames:
            mapa[self.normalizar_texto(cabecera)] = cabecera

        for fila in lector:

            destino = self.leer_entero(
                self.obtener_valor(fila, mapa, ["Destino"]),
                None,
            )

            if destino is None:
                continue

            tienda = self.leer_entero(
                self.obtener_valor(
                    fila,
                    mapa,
                    ["Id Tienda", "Id Loc.", "Tienda"],
                ),
                None,
            )

            aparte = self.leer_entero(
                self.obtener_valor(fila, mapa, ["Aparte", "Apt."]),
                0,
            )

            estado = str(
                self.obtener_valor(fila, mapa, ["Estado"])
            ).strip().upper()

            lleno_bloqueado = str(
                self.obtener_valor(
                    fila,
                    mapa,
                    ["Lleno/Bloqueado", "Lleno Bloqueado"],
                )
            ).strip().upper()

            zona_original = str(
                self.obtener_valor(fila, mapa, ["Zona"])
            ).strip()

            valor_lotes_tabla = self.obtener_valor(
                fila,
                mapa,
                ["Lotes"],
            )
            lotes_informados = str(valor_lotes_tabla or "").strip() != ""
            lotes_tabla = self.leer_numero(
                valor_lotes_tabla,
                0,
            )

            pais_tabla = str(
                self.obtener_valor(fila, mapa, ["Pais", "Pais tienda"])
            ).strip()

            tipo_caja_tabla = str(
                self.obtener_valor(
                    fila,
                    mapa,
                    ["TipoCaja", "Tipo Caja", "Tipo de caja"],
                )
            ).strip()

            ocupado = False

            if tienda is not None:
                ocupado = True

            if estado not in ["", "LIBRE"]:
                ocupado = True

            if lleno_bloqueado not in ["", "NO", "0"]:
                ocupado = True

            if destino not in destinos:
                destinos[destino] = {
                    "Destino": destino,
                    "Tienda": tienda,
                    "Aparte": aparte,
                    "Estado": estado,
                    "ZonaOriginal": zona_original,
                    "Ocupado": ocupado,
                    "LotesTabla": lotes_tabla,
                    "LotesInformados": lotes_informados,
                    "PaisTabla": pais_tabla,
                    "TipoCajaTabla": tipo_caja_tabla,
                }
            else:
                actual = destinos[destino]

                if ocupado:
                    actual["Ocupado"] = True

                if actual["Tienda"] is None and tienda is not None:
                    actual["Tienda"] = tienda
                    actual["Aparte"] = aparte

                if actual["Estado"] == "" and estado != "":
                    actual["Estado"] = estado

                if actual["ZonaOriginal"] == "" and zona_original != "":
                    actual["ZonaOriginal"] = zona_original

                if (
                    not actual.get("LotesInformados", False)
                    and lotes_informados
                ):
                    actual["LotesTabla"] = lotes_tabla
                    actual["LotesInformados"] = True

                if actual["PaisTabla"] == "" and pais_tabla != "":
                    actual["PaisTabla"] = pais_tabla

                if actual["TipoCajaTabla"] == "" and tipo_caja_tabla != "":
                    actual["TipoCajaTabla"] = tipo_caja_tabla
        if len(destinos) == 0:
            raise Exception("No se han encontrado destinos validos en el fichero.")

        self.tablas_activas[clasificador] = self.crear_estructura_tabla_activa()
        self.tablas_activas[clasificador]["Ruta"] = str(ruta)
        self.tablas_activas[clasificador]["Destinos"] = destinos

        self.recalcular_estadisticas_tabla_activa(clasificador)
        self.guardar_tabla_activa_bd(clasificador)
        self.invalidar_analisis()

        return self.obtener_estadisticas_tabla_activa(clasificador)

    #---------------------------------------------------------
    # Recalcular estadisticas de tabla activa
    #---------------------------------------------------------
    def recalcular_estadisticas_tabla_activa(self, clasificador):

        tabla = self.tablas_activas[clasificador]
        claves = set()
        ocupados = 0
        ocupados_con_tienda = 0
        bloqueados_sin_tienda = 0
        libres = 0

        for datos in tabla["Destinos"].values():

            if datos["Ocupado"]:
                ocupados += 1

                tienda = datos.get("Tienda")
                aparte = datos.get("Aparte", 0)

                if tienda is not None:
                    ocupados_con_tienda += 1
                    claves.add((int(tienda), int(aparte or 0)))
                else:
                    bloqueados_sin_tienda += 1
            else:
                libres += 1

        tabla["ClavesOcupadas"] = claves
        tabla["TotalDestinos"] = len(tabla["Destinos"])
        tabla["Ocupados"] = ocupados
        tabla["OcupadosConTienda"] = ocupados_con_tienda
        tabla["BloqueadosSinTienda"] = bloqueados_sin_tienda
        tabla["Libres"] = libres

    #---------------------------------------------------------
    # Guardar tabla activa en SQLite
    #---------------------------------------------------------
    def guardar_tabla_activa_bd(self, clasificador):

        self.bd.ejecutar(
            "DELETE FROM FUERA_TABLA_ACTIVA WHERE Clasificador = ?",
            (clasificador,),
        )

        for destino, datos in sorted(
            self.tablas_activas[clasificador]["Destinos"].items()
        ):

            valores = (
                clasificador,
                destino,
                datos.get("Tienda"),
                datos.get("Aparte"),
                datos.get("Estado", ""),
                datos.get("ZonaOriginal", ""),
                1 if datos.get("Ocupado", False) else 0,
            )

            self.bd.insertar("FUERA_TABLA_ACTIVA", valores)

        self.bd.guardar()

    #---------------------------------------------------------
    # Obtener estadisticas de tabla activa
    #---------------------------------------------------------
    def obtener_estadisticas_tabla_activa(self, clasificador):

        tabla = self.tablas_activas[clasificador]

        return {
            "Ruta": tabla["Ruta"],
            "TotalDestinos": tabla["TotalDestinos"],
            "Ocupados": tabla["Ocupados"],
            "OcupadosConTienda": tabla["OcupadosConTienda"],
            "BloqueadosSinTienda": tabla["BloqueadosSinTienda"],
            "Libres": tabla["Libres"],
        }

    #---------------------------------------------------------
    # Comprobar si estan importadas las dos tablas activas
    #---------------------------------------------------------
    def tablas_activas_cargadas(self):

        return (
            self.tablas_activas[1]["TotalDestinos"] > 0
            and self.tablas_activas[2]["TotalDestinos"] > 0
        )

    #---------------------------------------------------------
    # Cargar pedido agregado
    #---------------------------------------------------------
    def cargar_mapa_pedido(self):

        if self.gestor_pedidos_trabajo is not None:
            registros = self.gestor_pedidos_trabajo.obtener_detalle(
                self.clave_pedido_trabajo
            )
        else:
            registros = self.bd.consultar("""
                SELECT
                    Tienda,
                    Aparte,
                    Lotes,
                    IFNULL(Pais, '') AS Pais,
                    IFNULL(TipoCaja, '') AS TipoCaja
                FROM TMP_ESTAREPP
            """)

        mapa = {}

        for tienda, aparte, lotes, pais, tipo_caja in registros:

            clave = (int(tienda), int(aparte or 0))

            if clave not in mapa:
                mapa[clave] = {
                    "Tienda": clave[0],
                    "Aparte": clave[1],
                    "Lotes": 0,
                    "Pais": self.normalizar_pais(pais),
                    "TipoCaja": self.normalizar_tipo_caja(tipo_caja),
                }

            mapa[clave]["Lotes"] += float(lotes or 0)

            if mapa[clave]["Pais"] == "":
                mapa[clave]["Pais"] = self.normalizar_pais(pais)

            if mapa[clave]["TipoCaja"] == "1_Nueva_30" and str(tipo_caja or "").strip() != "":
                mapa[clave]["TipoCaja"] = self.normalizar_tipo_caja(tipo_caja)

        self.mapa_pedido = mapa

    #---------------------------------------------------------
    # Obtener maestro de destinos
    #---------------------------------------------------------
    def obtener_maestro_destinos(self):

        datos = self.bd.consultar("""
            SELECT
                Clasificador,
                Lado,
                Destino,
                Descripcion,
                Prioridad,
                Prioridad_Orden
            FROM TablasDistribucionClasificador
        """)

        maestro = {}

        for clasificador, lado, destino, descripcion, prioridad, prioridad_orden in datos:
            maestro[(int(clasificador), int(destino))] = {
                "Clasificador": int(clasificador),
                "Lado": int(lado),
                "Destino": int(destino),
                "Zona": str(descripcion),
                "Prioridad": int(prioridad),
                "PrioridadOrden": int(prioridad_orden),
            }

        return maestro

    #---------------------------------------------------------
    # Analizar pedido contra tablas activas
    #---------------------------------------------------------
    def analizar_fuera_tabla(self):

        if not self.tablas_activas_cargadas():
            raise Exception(
                "Primero debes importar las tablas activas de CLA 1 y CLA 2."
            )

        self.invalidar_analisis()
        self.cargar_mapa_pedido()

        if len(self.mapa_pedido) == 0:
            raise Exception("El pedido importado no contiene tiendas/apartes.")

        maestro = self.obtener_maestro_destinos()
        ubicaciones = {}
        duplicados = []
        sin_maestro = []
        self.libres_utilizables = {1: 0, 2: 0}
        self.libres_sin_maestro = {1: 0, 2: 0}
        self.ocupados_sin_maestro = []

        for clasificador in [1, 2]:

            for numero_destino, datos in self.tablas_activas[clasificador]["Destinos"].items():
                existe_maestro = (clasificador, int(numero_destino)) in maestro

                if datos.get("Ocupado", False):
                    if not existe_maestro:
                        self.ocupados_sin_maestro.append(
                            (clasificador, int(numero_destino))
                        )
                else:
                    if existe_maestro:
                        self.libres_utilizables[clasificador] += 1
                    else:
                        self.libres_sin_maestro[clasificador] += 1

        for clasificador in [1, 2]:

            tabla = self.tablas_activas[clasificador]

            for numero_destino, datos in tabla["Destinos"].items():

                if not datos.get("Ocupado", False):
                    continue

                tienda = datos.get("Tienda")

                if tienda is None:
                    continue

                clave = (int(tienda), int(datos.get("Aparte", 0) or 0))

                if clave in ubicaciones:
                    duplicados.append(
                        (
                            clave,
                            ubicaciones[clave]["Clasificador"],
                            ubicaciones[clave]["Destino"],
                            clasificador,
                            int(numero_destino),
                        )
                    )
                    continue

                ubicacion_maestro = maestro.get((clasificador, int(numero_destino)))

                if ubicacion_maestro is None:
                    sin_maestro.append((clasificador, int(numero_destino), clave))

                ubicaciones[clave] = {
                    "Clasificador": clasificador,
                    "Destino": int(numero_destino),
                    "Lado": ubicacion_maestro["Lado"] if ubicacion_maestro else None,
                    "Zona": ubicacion_maestro["Zona"] if ubicacion_maestro else "",
                    "Prioridad": ubicacion_maestro["Prioridad"] if ubicacion_maestro else 0,
                    "PrioridadOrden": ubicacion_maestro["PrioridadOrden"] if ubicacion_maestro else 0,
                    "DatosTabla": datos,
                }

        if len(duplicados) > 0:
            detalle = []
            for clave, cla_1, destino_1, cla_2, destino_2 in duplicados[:10]:
                detalle.append(
                    "Tienda "
                    + str(clave[0])
                    + " aparte "
                    + str(clave[1])
                    + ": CLA "
                    + str(cla_1)
                    + " destino "
                    + str(destino_1)
                    + " y CLA "
                    + str(cla_2)
                    + " destino "
                    + str(destino_2)
                )

            raise Exception(
                "ERROR CRITICO: una misma Tienda+Aparte aparece mas de una vez "
                "en las tablas activas. No se puede calcular.\n\n"
                + "\n".join(detalle)
            )

        if len(sin_maestro) > 0:
            self.advertencias.append(
                str(len(sin_maestro))
                + " destinos ocupados de las tablas activas no existen en el maestro."
            )

        libres_no_utilizables = sum(self.libres_sin_maestro.values())
        if libres_no_utilizables > 0:
            self.advertencias.append(
                str(libres_no_utilizables)
                + " destinos libres no existen en el maestro y no se usaran."
            )

        self.ubicaciones_existentes = ubicaciones
        self.carga_existente_por_cla = {1: [], 2: []}
        self.carga_desconocida = []
        self.dentro_tabla = []
        self.fuera_tabla = []

        for clave, registro in self.mapa_pedido.items():

            if clave in ubicaciones:
                ubicacion = ubicaciones[clave]
                registro_dentro = dict(registro)
                registro_dentro.update(
                    {
                        "Clasificador": ubicacion["Clasificador"],
                        "Destino": ubicacion["Destino"],
                        "Lado": ubicacion["Lado"],
                        "Zona": ubicacion["Zona"],
                    }
                )
                self.dentro_tabla.append(registro_dentro)
            else:
                self.fuera_tabla.append(dict(registro))

        for clave, ubicacion in ubicaciones.items():

            datos_tabla = ubicacion["DatosTabla"]
            registro_pedido = self.mapa_pedido.get(clave)

            if registro_pedido is not None:
                lotes = float(registro_pedido["Lotes"])
                pais = registro_pedido["Pais"]
                tipo_caja = registro_pedido["TipoCaja"]
                carga_conocida = True
                origen_carga = "PEDIDO"
            else:
                lotes_tabla = float(datos_tabla.get("LotesTabla", 0) or 0)
                lotes = lotes_tabla
                pais = self.normalizar_pais(datos_tabla.get("PaisTabla", ""))
                tipo_caja = self.normalizar_tipo_caja(
                    datos_tabla.get("TipoCajaTabla", "")
                )
                # Una posicion activa puede no tener lotes informados.
                # Sigue siendo inamovible y ocupada; para el balance se
                # contabiliza con 0 lotes y NO bloquea el calculo.
                carga_conocida = bool(
                    datos_tabla.get("LotesInformados", False)
                )
                origen_carga = (
                    "TABLA_ACTIVA"
                    if carga_conocida
                    else "SIN_LOTES_INFORMADOS"
                )

            existente = {
                "Clasificador": ubicacion["Clasificador"],
                "Destino": ubicacion["Destino"],
                "Lado": ubicacion["Lado"],
                "Zona": ubicacion["Zona"],
                "Tienda": clave[0],
                "Aparte": clave[1],
                "Lotes": lotes,
                "Pais": pais,
                "TipoCaja": tipo_caja,
                "CargaConocida": carga_conocida,
                "OrigenCarga": origen_carga,
            }

            self.carga_existente_por_cla[ubicacion["Clasificador"]].append(existente)

            if not carga_conocida:
                self.carga_desconocida.append(existente)

        if len(self.carga_desconocida) > 0:
            self.advertencias.append(
                str(len(self.carga_desconocida))
                + " tiendas/apartes ocupados no tienen lotes informados; "
                + "se mantienen inamovibles y se contabilizan con 0 lotes."
            )

        self.guardar_fuera_tabla_bd()
        self.guardar_existentes_bd(maestro)

        self.resumen_analisis = self.construir_resumen_analisis()
        return dict(self.resumen_analisis)

    #---------------------------------------------------------
    # Guardar fuera de tabla en SQLite
    #---------------------------------------------------------
    def guardar_fuera_tabla_bd(self):

        self.bd.ejecutar("DELETE FROM FUERA_TABLA_PEDIDO")

        for registro in self.fuera_tabla:
            self.bd.insertar(
                "FUERA_TABLA_PEDIDO",
                (
                    registro["Tienda"],
                    registro["Aparte"],
                    registro["Lotes"],
                    registro["Pais"],
                    registro["TipoCaja"],
                ),
            )

        self.bd.guardar()

    #---------------------------------------------------------
    # Guardar posiciones existentes para auditoria
    #---------------------------------------------------------
    def guardar_existentes_bd(self, maestro):

        self.bd.ejecutar("DELETE FROM FUERA_TABLA_EXISTENTE")

        por_ubicacion = {}

        for clasificador in [1, 2]:
            for registro in self.carga_existente_por_cla[clasificador]:
                por_ubicacion[(clasificador, registro["Destino"])] = registro

        for clasificador in [1, 2]:

            for numero_destino, datos in sorted(
                self.tablas_activas[clasificador]["Destinos"].items()
            ):

                if not datos.get("Ocupado", False):
                    continue

                info_maestro = maestro.get((clasificador, int(numero_destino)), {})
                existente = por_ubicacion.get((clasificador, int(numero_destino)), {})

                valores = (
                    clasificador,
                    info_maestro.get("Lado"),
                    info_maestro.get("Zona", ""),
                    self.calcular_bloque_destino(numero_destino),
                    int(numero_destino),
                    datos.get("Tienda"),
                    int(datos.get("Aparte", 0) or 0),
                    float(existente.get("Lotes", 0) or 0),
                    existente.get("Pais", ""),
                    existente.get("TipoCaja", ""),
                    1 if existente.get("CargaConocida", False) else 0,
                    1,
                )

                self.bd.insertar("FUERA_TABLA_EXISTENTE", valores)

        self.bd.guardar()

    #---------------------------------------------------------
    # Construir resumen del analisis
    #---------------------------------------------------------
    def construir_resumen_analisis(self):

        lotes_pedido = sum(
            float(registro["Lotes"])
            for registro in self.mapa_pedido.values()
        )

        lotes_dentro = sum(
            float(registro["Lotes"])
            for registro in self.dentro_tabla
        )

        lotes_fuera = sum(
            float(registro["Lotes"])
            for registro in self.fuera_tabla
        )

        resumen_cla = {}

        for clasificador in [1, 2]:
            registros = self.carga_existente_por_cla[clasificador]
            resumen_cla[clasificador] = {
                "Tiendas": len(registros),
                "Lotes": sum(float(registro["Lotes"]) for registro in registros),
                "CargaDesconocida": sum(
                    1
                    for registro in registros
                    if not registro["CargaConocida"]
                ),
            }

        libres_1 = self.libres_utilizables[1]
        libres_2 = self.libres_utilizables[2]
        cabe = len(self.fuera_tabla) <= libres_1 + libres_2
        carga_completa = len(self.carga_desconocida) == 0
        maestro_completo = len(self.ocupados_sin_maestro) == 0

        return {
            "Pedido": len(self.mapa_pedido),
            "LotesPedido": lotes_pedido,
            "DentroTabla": len(self.dentro_tabla),
            "LotesDentroTabla": lotes_dentro,
            "FueraTabla": len(self.fuera_tabla),
            "LotesFuera": lotes_fuera,
            "CLA1TiendasAsignadas": resumen_cla[1]["Tiendas"],
            "CLA1LotesAsignados": resumen_cla[1]["Lotes"],
            "CLA2TiendasAsignadas": resumen_cla[2]["Tiendas"],
            "CLA2LotesAsignados": resumen_cla[2]["Lotes"],
            "LotesAsignadosTotal": lotes_dentro,
            "LibresCLA1": libres_1,
            "LibresCLA2": libres_2,
            "LibresTotal": libres_1 + libres_2,
            "Cabe": cabe,
            # Se conservan las claves historicas por compatibilidad.
            # CargaDesconocida ya no es bloqueante: significa solamente
            # que la posicion se contabiliza con 0 lotes.
            "CargaDesconocida": len(self.carga_desconocida),
            "CargaNoInformada": len(self.carga_desconocida),
            "CargaCompleta": carga_completa,
            "BalanceConCargaParcial": not carga_completa,
            "OcupadosSinMaestro": len(self.ocupados_sin_maestro),
            "LibresSinMaestro": sum(self.libres_sin_maestro.values()),
            "MaestroCompleto": maestro_completo,
            "CalculoPermitido": (
                cabe
                and maestro_completo
                and len(self.fuera_tabla) > 0
            ),
            "Advertencias": list(self.advertencias),
        }

    #---------------------------------------------------------
    # Obtener resumen de analisis
    #---------------------------------------------------------
    def obtener_resumen_analisis(self):

        if self.resumen_analisis is None:
            return {}

        return dict(self.resumen_analisis)

    #---------------------------------------------------------
    # Obtener resumen de paises fuera de tabla
    #---------------------------------------------------------
    def obtener_resumen_paises_fuera(self):

        resumen = {}

        for registro in self.fuera_tabla:

            pais = registro["Pais"]
            pais_mostrar = pais if pais != "" else "(SIN PAIS)"

            if pais not in resumen:
                resumen[pais] = {
                    "Pais": pais,
                    "PaisMostrar": pais_mostrar,
                    "Tiendas": 0,
                    "Lotes": 0,
                }

            resumen[pais]["Tiendas"] += 1
            resumen[pais]["Lotes"] += registro["Lotes"]

        return [resumen[pais] for pais in sorted(resumen.keys())]

    #---------------------------------------------------------
    # Obtener marca de pais obligado para exportacion
    #---------------------------------------------------------
    def obtener_marca_pais_obligado(self, registro, configuracion_paises):

        configuracion = self.normalizar_configuracion_paises(configuracion_paises)

        if not configuracion.get("Activo", False):
            return "NO", "", ""

        pais = self.normalizar_pais(registro.get("Pais", ""))
        paises_cla_1 = configuracion.get("PaisesCLA1", [])
        paises_cla_2 = configuracion.get("PaisesCLA2", [])

        if pais in paises_cla_1:
            return "SI", "CLA 1", "PAIS OBLIGADO"

        if pais in paises_cla_2:
            return "SI", "CLA 2", "PAIS OBLIGADO"

        if configuracion.get("RestoAlOtro", False):

            if len(paises_cla_1) > 0:
                return "NO", "CLA 2", "RESTO AL OTRO"

            if len(paises_cla_2) > 0:
                return "NO", "CLA 1", "RESTO AL OTRO"

        return "NO", "", "COMPENSACION"

    #---------------------------------------------------------
    # Obtener registros para exportar fuera de tabla
    #---------------------------------------------------------
    def obtener_registros_exportacion_fuera_tabla(self, configuracion_paises):

        registros = []

        if len(self.ultimo_resultado) > 0:

            for destino in self.ultimo_resultado:

                registro = {
                    "Tienda": destino.get("Tienda", ""),
                    "Aparte": destino.get("Aparte", ""),
                    "Pais": destino.get("Pais", ""),
                    "Lotes": destino.get("Lotes", 0),
                    "TipoCaja": destino.get("TipoCaja", ""),
                    "Clasificador": destino.get("Clasificador", ""),
                }

                pais_obligado, cla_obligado, motivo = self.obtener_marca_pais_obligado(
                    registro,
                    configuracion_paises,
                )

                registros.append(
                    {
                        "Tienda": registro["Tienda"],
                        "Aparte": registro["Aparte"],
                        "Pais": registro["Pais"],
                        "Clasificador": "CLA " + str(registro["Clasificador"]),
                        "PaisObligado": pais_obligado,
                        "MotivoCLA": motivo if motivo != "" else "COMPENSACION",
                        "Lotes": registro["Lotes"],
                        "TipoCaja": registro["TipoCaja"],
                    }
                )

            return registros

        for registro in self.fuera_tabla:

            pais_obligado, cla_obligado, motivo = self.obtener_marca_pais_obligado(
                registro,
                configuracion_paises,
            )

            cla = cla_obligado if cla_obligado != "" else "PENDIENTE DE CALCULO"

            registros.append(
                {
                    "Tienda": registro.get("Tienda", ""),
                    "Aparte": registro.get("Aparte", ""),
                    "Pais": registro.get("Pais", ""),
                    "Clasificador": cla,
                    "PaisObligado": pais_obligado,
                    "MotivoCLA": motivo if motivo != "" else "PENDIENTE DE CALCULO",
                    "Lotes": registro.get("Lotes", 0),
                    "TipoCaja": registro.get("TipoCaja", ""),
                }
            )

        return registros

    #---------------------------------------------------------
    # Exportar tiendas/apartes fuera de tabla
    #---------------------------------------------------------
    def exportar_fuera_tabla_csv(self, carpeta_salida, configuracion_paises=None):

        if len(self.fuera_tabla) == 0 and len(self.ultimo_resultado) == 0:
            raise Exception(
                "No hay registros fuera de tabla para exportar. "
                "Primero debes analizar fuera de tabla."
            )

        carpeta = Path(carpeta_salida)
        carpeta.mkdir(parents=True, exist_ok=True)

        fecha_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_archivo = carpeta / (
            "Fuera_Tabla_Tiendas_Aparte_" + fecha_hora + ".csv"
        )

        registros = self.obtener_registros_exportacion_fuera_tabla(
            configuracion_paises
        )

        registros = sorted(
            registros,
            key=lambda registro: (
                str(registro.get("Clasificador", "")),
                str(registro.get("Pais", "")),
                int(registro.get("Tienda", 0)),
                int(registro.get("Aparte", 0)),
            ),
        )

        with open(
            ruta_archivo,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as archivo:

            escritor = csv.writer(
                archivo,
                delimiter=";",
                lineterminator="\r\n",
            )

            escritor.writerow(
                [
                    "TIENDA",
                    "APARTE",
                    "PAIS",
                    "CLA",
                    "PAIS_OBLIGADO",
                    "MOTIVO_CLA",
                    "LOTES",
                    "TIPOCAJA",
                ]
            )

            for registro in registros:
                escritor.writerow(
                    [
                        registro.get("Tienda", ""),
                        registro.get("Aparte", ""),
                        registro.get("Pais", ""),
                        registro.get("Clasificador", ""),
                        registro.get("PaisObligado", ""),
                        registro.get("MotivoCLA", ""),
                        round(float(registro.get("Lotes", 0) or 0), 2),
                        registro.get("TipoCaja", ""),
                    ]
                )

        return ruta_archivo

    #---------------------------------------------------------
    # Contar capacidad libre de un clasificador
    # Override del motor general para estado inicial ocupado
    #---------------------------------------------------------
    def contar_capacidad_clasificador(self, clasificador):

        return sum(
            1
            for destino in self.destinos
            if destino["Clasificador"] == clasificador
            and destino["Libre"]
        )

    #---------------------------------------------------------
    # Preparar destinos con ocupacion fija e inamovible
    #---------------------------------------------------------
    def cargar_destinos_desde_tablas_activas(self):

        maestro = self.obtener_maestro_destinos()
        destinos = []
        por_ubicacion = {}

        for clasificador in [1, 2]:
            for registro in self.carga_existente_por_cla[clasificador]:
                por_ubicacion[(clasificador, registro["Destino"])] = registro

        destinos_sin_maestro = []

        for clasificador in [1, 2]:

            tabla = self.tablas_activas[clasificador]

            for numero_destino, datos in tabla["Destinos"].items():

                clave_maestro = (clasificador, int(numero_destino))

                if clave_maestro not in maestro:
                    if datos.get("Ocupado", False):
                        destinos_sin_maestro.append(clave_maestro)
                    continue

                info = maestro[clave_maestro]
                ocupado = bool(datos.get("Ocupado", False))
                existente = por_ubicacion.get(clave_maestro, {})

                destino = {
                    "Clasificador": clasificador,
                    "Lado": info["Lado"],
                    "Destino": int(numero_destino),
                    "Bloque": self.calcular_bloque_destino(numero_destino),
                    "Tramo": 0,
                    "Descripcion": info["Zona"],
                    "Prioridad": info["Prioridad"],
                    "PrioridadOrden": info["PrioridadOrden"],
                    "Libre": not ocupado,
                    "Tienda": datos.get("Tienda") if ocupado else None,
                    "Aparte": int(datos.get("Aparte", 0) or 0) if ocupado else None,
                    "Lotes": float(existente.get("Lotes", 0) or 0),
                    "TipoCaja": existente.get("TipoCaja", ""),
                    "Pais": existente.get("Pais", ""),
                    "Origen": "EXISTENTE" if ocupado else "LIBRE",
                    "Inamovible": ocupado,
                    "CargaConocida": existente.get("CargaConocida", not ocupado),
                }

                destinos.append(destino)

        if len(destinos_sin_maestro) > 0:
            detalle = ", ".join(
                "CLA " + str(cla) + " destino " + str(destino)
                for cla, destino in destinos_sin_maestro[:10]
            )
            raise Exception(
                "Hay destinos de las tablas activas que no existen en el maestro "
                "TablasDistribucionClasificador. Revisa: "
                + detalle
            )

        destinos.sort(
            key=lambda destino: (
                destino["Clasificador"],
                destino["PrioridadOrden"],
                destino["Destino"],
            )
        )

        self.destinos = destinos
        self.calcular_tramos_destinos()
        self._plantilla_destinos = copy.deepcopy(self.destinos)
        self._firma_inamovibles = self.obtener_firma_inamovibles(self.destinos)
        self.inicializar_estadisticas_desde_existentes()

    #---------------------------------------------------------
    # Crear firma de seguridad de destinos inamovibles
    #---------------------------------------------------------
    def obtener_firma_inamovibles(self, destinos):

        firma = {}

        for destino in destinos:

            if not destino.get("Inamovible", False):
                continue

            clave = (destino["Clasificador"], destino["Destino"])
            firma[clave] = (
                destino.get("Tienda"),
                destino.get("Aparte"),
                destino.get("Lotes", 0),
                destino.get("TipoCaja", ""),
                destino.get("Pais", ""),
                destino.get("Libre", False),
                destino.get("Origen", ""),
            )

        return firma

    #---------------------------------------------------------
    # Validar que ningun existente se haya movido
    #---------------------------------------------------------
    def validar_inamovibles(self):

        firma_actual = self.obtener_firma_inamovibles(self.destinos)

        if firma_actual != self._firma_inamovibles:
            raise Exception(
                "ERROR CRITICO: el calculo intento modificar una posicion "
                "existente de las tablas activas. No se ha guardado el resultado."
            )

    #---------------------------------------------------------
    # Inicializar cargas del motor con lo ya asignado
    #---------------------------------------------------------
    def inicializar_estadisticas_desde_existentes(self):

        self.clasificadores = self.crear_estadisticas_vacias()
        claves_vistas = set()

        for destino in self.destinos:

            if destino["Libre"]:
                continue

            if destino.get("Tienda") is None:
                continue

            clave_tienda = (
                int(destino["Tienda"]),
                int(destino.get("Aparte", 0) or 0),
            )

            if clave_tienda in claves_vistas:
                raise Exception(
                    "ERROR CRITICO: la Tienda "
                    + str(clave_tienda[0])
                    + " aparte "
                    + str(clave_tienda[1])
                    + " aparece repetida en el estado inicial."
                )

            claves_vistas.add(clave_tienda)

            clasificador = destino["Clasificador"]
            lado = destino["Lado"]
            descripcion = destino["Descripcion"]
            lotes = float(destino.get("Lotes", 0) or 0)

            self.clasificadores[clasificador]["Lotes"] += lotes
            self.clasificadores[clasificador]["Tiendas"] += 1
            self.clasificadores[clasificador]["Lados"][lado][descripcion] += lotes

    #---------------------------------------------------------
    # Reset seguro: conserva siempre los existentes
    #---------------------------------------------------------
    def resetear_reparto_en_memoria(self):

        if len(self._plantilla_destinos) == 0:
            super().resetear_reparto_en_memoria()
            return

        self.destinos = copy.deepcopy(self._plantilla_destinos)
        self.inicializar_estadisticas_desde_existentes()

    #---------------------------------------------------------
    # Asignar solo sobre una tolva realmente libre
    #---------------------------------------------------------
    def asignar_tienda(self, tienda, destino):

        if destino.get("Inamovible", False) or not destino.get("Libre", False):
            raise Exception(
                "ERROR CRITICO: se intento asignar una tienda sobre una "
                "posicion existente o no disponible."
            )

        super().asignar_tienda(tienda, destino)
        destino["Pais"] = self.normalizar_pais(tienda[3])
        destino["Origen"] = "FUERA_TABLA"
        destino["Inamovible"] = False
        destino["CargaConocida"] = True

    #---------------------------------------------------------
    # Lado_corto aplicable a las posiciones realmente libres
    #---------------------------------------------------------
    def calcular_tiendas_previstas_lado_corto(self):

        capacidad_largo_libre = sum(
            1
            for destino in self.destinos
            if destino.get("Libre", False)
            and destino.get("Descripcion") == "Lado_Largo"
        )
        return max(0, len(self.tmp) - capacidad_largo_libre)

    def obtener_capacidades_lados_cortos(self):

        capacidades = {}
        for destino in self.destinos:
            if not destino.get("Libre", False):
                continue
            if destino.get("Descripcion") != "Lado_corto":
                continue

            clave = (destino["Clasificador"], destino["Lado"])
            if clave not in capacidades:
                capacidades[clave] = {
                    "Capacidad": 0,
                    "PrioridadOrden": destino["PrioridadOrden"],
                }
            capacidades[clave]["Capacidad"] += 1
            capacidades[clave]["PrioridadOrden"] = min(
                capacidades[clave]["PrioridadOrden"],
                destino["PrioridadOrden"],
            )
        return capacidades

    def obtener_resumen_opcion(self):

        resumen = super().obtener_resumen_opcion()
        asignados_nuevos = sum(
            1
            for destino in self.destinos
            if destino.get("Origen") == "FUERA_TABLA"
        )
        esperados = len(self.tmp)
        pendientes = max(0, esperados - asignados_nuevos)
        resumen["RegistrosEsperados"] = esperados
        resumen["RegistrosAsignados"] = asignados_nuevos
        resumen["RegistrosPendientes"] = pendientes
        resumen["Valida"] = pendientes == 0
        return resumen

    #---------------------------------------------------------
    # Validar tipos de caja antes del reparto
    #---------------------------------------------------------
    def validar_tipos_caja(self):

        invalidos = sorted(
            {
                registro["TipoCaja"]
                for registro in self.fuera_tabla
                if registro["TipoCaja"] not in self.TIPOS_CAJA
            }
        )

        if len(invalidos) > 0:
            raise Exception(
                "Hay tipos de caja no homologados en el pedido fuera de tabla: "
                + ", ".join(invalidos)
            )

    #---------------------------------------------------------
    # Calcular reparto fuera de tabla y guardar
    #---------------------------------------------------------
    def calcular_y_guardar(self, configuracion_paises=None, tamano_bloque=10):

        if self.resumen_analisis is None:
            raise Exception("Primero debes analizar fuera de tabla.")

        if len(self.fuera_tabla) == 0:
            raise Exception("No hay registros fuera de tabla para calcular.")

        self.tamano_bloque = int(tamano_bloque or 10)

        if self.tamano_bloque <= 0:
            self.tamano_bloque = 10

        self.clasificadores_activos = [1, 2]
        self.prioridad = "NORMAL"
        self.configuracion_paises = self.normalizar_configuracion_paises(
            configuracion_paises
        )
        self.configuracion_prioridad_paises = {
            "Activo": False,
            "PaisesNormal": [],
            "PaisesInversa": [],
        }
        self.validar_tipos_caja()
        self.cargar_destinos_desde_tablas_activas()

        libres = sum(1 for destino in self.destinos if destino["Libre"])

        if len(self.fuera_tabla) > libres:
            raise Exception(
                "No hay tolvas libres suficientes. Fuera de tabla: "
                + str(len(self.fuera_tabla))
                + " | Libres utilizables: "
                + str(libres)
            )

        self.tmp = [
            (
                registro["Tienda"],
                registro["Aparte"],
                registro["Lotes"],
                registro["Pais"],
                registro["TipoCaja"],
            )
            for registro in self.fuera_tabla
        ]

        self.validar_capacidad_paises_forzados()
        self.ordenar_tiendas()
        self.calcular_numero_destinos()

        # En Busca Fuera de Tabla la seleccion solo aparece si las posiciones
        # largas libres no son suficientes para las nuevas asignaciones. Las
        # posiciones existentes permanecen siempre inamovibles.
        self.seleccionar_lado_corto_operador()
        self.resetear_reparto_en_memoria()
        self.ejecutar_reparto_core()

        resultado = [
            destino
            for destino in self.destinos
            if destino.get("Origen") == "FUERA_TABLA"
        ]

        if len(resultado) != len(self.fuera_tabla):
            raise Exception(
                "El motor no pudo colocar todas las tiendas/apartes fuera de tabla. "
                "Esperadas: "
                + str(len(self.fuera_tabla))
                + " | Asignadas: "
                + str(len(resultado))
            )

        self.validar_inamovibles()

        self.ultimo_resultado = resultado
        self.guardar_resultado_bd(resultado)
        self.guardar_reparto_clasificador(resultado)

        return self.obtener_resumen_resultado(resultado)

    #---------------------------------------------------------
    # Guardar resultado nuevo en tabla propia
    #---------------------------------------------------------
    def guardar_resultado_bd(self, resultado):

        self.bd.ejecutar("DELETE FROM FUERA_TABLA_RESULTADO")

        for destino in resultado:
            self.bd.insertar(
                "FUERA_TABLA_RESULTADO",
                (
                    destino["Clasificador"],
                    destino["Lado"],
                    destino["Descripcion"],
                    destino["Tramo"],
                    destino["Bloque"],
                    destino["Destino"],
                    destino["Tienda"],
                    destino["Aparte"],
                    destino["Lotes"],
                    destino.get("Pais", ""),
                    destino["TipoCaja"],
                    destino["Prioridad"],
                    destino["PrioridadOrden"],
                ),
            )

        self.bd.guardar()

    #---------------------------------------------------------
    # Guardar solo nuevas asignaciones para exportacion
    #---------------------------------------------------------
    def guardar_reparto_clasificador(self, resultado):

        self.bd.ejecutar("DELETE FROM REPARTO_CLASIFICADOR")

        for destino in resultado:
            self.bd.insertar(
                "REPARTO_CLASIFICADOR",
                (
                    destino["Clasificador"],
                    destino["Lado"],
                    destino["Descripcion"],
                    destino["Tramo"],
                    destino["Bloque"],
                    destino["Destino"],
                    destino["Tienda"],
                    destino["Aparte"],
                    destino["Lotes"],
                    destino["TipoCaja"],
                    destino["Prioridad"],
                    destino["PrioridadOrden"],
                ),
            )

        self.bd.guardar()

    #---------------------------------------------------------
    # Resumen de resultado con carga inicial, nueva y final
    #---------------------------------------------------------
    def obtener_resumen_resultado(self, resultado):

        nuevos = {
            1: {"Tiendas": 0, "Lotes": 0},
            2: {"Tiendas": 0, "Lotes": 0},
        }

        iniciales = {
            1: {
                "Tiendas": len(self.carga_existente_por_cla[1]),
                "Lotes": sum(
                    float(registro["Lotes"])
                    for registro in self.carga_existente_por_cla[1]
                ),
            },
            2: {
                "Tiendas": len(self.carga_existente_por_cla[2]),
                "Lotes": sum(
                    float(registro["Lotes"])
                    for registro in self.carga_existente_por_cla[2]
                ),
            },
        }

        for destino in resultado:
            clasificador = destino["Clasificador"]
            nuevos[clasificador]["Tiendas"] += 1
            nuevos[clasificador]["Lotes"] += float(destino["Lotes"])

        finales = {
            1: {
                "Tiendas": iniciales[1]["Tiendas"] + nuevos[1]["Tiendas"],
                "Lotes": iniciales[1]["Lotes"] + nuevos[1]["Lotes"],
            },
            2: {
                "Tiendas": iniciales[2]["Tiendas"] + nuevos[2]["Tiendas"],
                "Lotes": iniciales[2]["Lotes"] + nuevos[2]["Lotes"],
            },
        }

        return {
            "Registros": len(resultado),
            "Inamovibles": iniciales[1]["Tiendas"] + iniciales[2]["Tiendas"],
            "CLA1InicialTiendas": iniciales[1]["Tiendas"],
            "CLA1InicialLotes": iniciales[1]["Lotes"],
            "CLA2InicialTiendas": iniciales[2]["Tiendas"],
            "CLA2InicialLotes": iniciales[2]["Lotes"],
            "CLA1NuevasTiendas": nuevos[1]["Tiendas"],
            "CLA1NuevosLotes": nuevos[1]["Lotes"],
            "CLA2NuevasTiendas": nuevos[2]["Tiendas"],
            "CLA2NuevosLotes": nuevos[2]["Lotes"],
            "CLA1FinalTiendas": finales[1]["Tiendas"],
            "CLA1FinalLotes": finales[1]["Lotes"],
            "CLA2FinalTiendas": finales[2]["Tiendas"],
            "CLA2FinalLotes": finales[2]["Lotes"],
            "DiferenciaLotes": abs(
                finales[1]["Lotes"] - finales[2]["Lotes"]
            ),
            "DiferenciaTiendas": abs(
                finales[1]["Tiendas"] - finales[2]["Tiendas"]
            ),
        }
