"""Pedido persistente del escenario activo calculado en Cajas.

El formulario de calculo de cajas trabaja sobre sus pedidos acumulados
(CAJAS_PEDIDO_LINEAS, V2.1), pero los
formularios de reparto no deben depender de que esa tabla siga conteniendo el
mismo pedido. Cuando el operador activa un escenario, este modulo materializa
una copia completa y autonoma de las lineas que forman ese escenario.

La copia conserva exactamente la estructura de ESTAREPP y puede procesarse
posteriormente en cualquier formulario mediante ProcesarESTAREPP, sin volver a
importar el fichero original y sin modificar ESTAREPP.
"""

from __future__ import annotations

from datetime import datetime
import sqlite3

from modulos.motor_calculo_cajas_pedido import MotorCalculoCajasPedido
from modulos.gestor_pedidos_cajas import (
    GestorPedidosCajas,
    linea_eliminada_por_picos,
)


class ErrorPedidoEscenarioActivo(RuntimeError):
    """El escenario no pudo convertirse en un pedido global utilizable."""


class GestorPedidoEscenarioActivo:
    TABLA_PEDIDO = "CAJAS_PEDIDO_ESCENARIO_ACTIVO"
    TABLA_DESCARTADO = "CAJAS_PEDIDO_ESCENARIO_DESCARTADO"
    TABLA_META = "CAJAS_ESCENARIO_ACTIVO"

    COLUMNAS_ESTAREPP = (
        "MarcaComercial",
        "Campaña",
        "Año",
        "Tienda",
        "Seccion",
        "Aparte",
        "DescTienda",
        "Modelo",
        "Calidad",
        "Color",
        "TallaNum",
        "TallaAlfa",
        "POC",
        "Familia",
        "Subfamilia",
        "Carrusel",
        "Estado",
        "Unidades",
        "UoL",
        "UxL",
        "Lotes",
    )

    TIPOS_ESTAREPP = (
        "TEXT",
        "TEXT",
        "INTEGER",
        "INTEGER",
        "INTEGER",
        "INTEGER",
        "TEXT",
        "INTEGER",
        "INTEGER",
        "INTEGER",
        "INTEGER",
        "TEXT",
        "TEXT",
        "INTEGER",
        "INTEGER",
        "TEXT",
        "INTEGER",
        "INTEGER",
        "TEXT",
        "INTEGER",
        "REAL",
    )

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion
        self.asegurar_tablas()

    @staticmethod
    def _identificador(nombre):
        return '"' + str(nombre).replace('"', '""') + '"'

    @staticmethod
    def _numero_entero(valor, defecto=None):
        try:
            return int(float(str(valor).strip().replace(",", ".")))
        except Exception:
            return defecto

    @staticmethod
    def _numero_real(valor, defecto=0.0):
        try:
            return float(str(valor).strip().replace(",", "."))
        except Exception:
            return defecto

    @staticmethod
    def _normalizar_tiendas(valores):
        resultado = set()
        for valor in valores or set():
            tienda = GestorPedidoEscenarioActivo._numero_entero(valor, None)
            if tienda is not None and tienda > 0:
                resultado.add(tienda)
        return resultado

    def _tabla_existe(self, tabla):
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (str(tabla),),
        )
        return cursor.fetchone() is not None

    def _columnas_tabla(self, tabla):
        cursor = self.conexion.cursor()
        cursor.execute("PRAGMA table_info(" + self._identificador(tabla) + ")")
        return {str(fila[1]).strip().lower() for fila in cursor.fetchall()}

    def _asegurar_columna(self, tabla, columna, definicion):
        if str(columna).strip().lower() in self._columnas_tabla(tabla):
            return
        self.conexion.execute(
            "ALTER TABLE "
            + self._identificador(tabla)
            + " ADD COLUMN "
            + self._identificador(columna)
            + " "
            + str(definicion)
        )

    def asegurar_tablas(self):
        columnas_sql = []
        for nombre, tipo in zip(self.COLUMNAS_ESTAREPP, self.TIPOS_ESTAREPP):
            columnas_sql.append(self._identificador(nombre) + " " + tipo)

        self.conexion.execute(
            "CREATE TABLE IF NOT EXISTS "
            + self._identificador(self.TABLA_PEDIDO)
            + " ("
            + ", ".join(columnas_sql)
            + ")"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS IX_CAJAS_PEDIDO_ESCENARIO_TIENDA "
            "ON "
            + self._identificador(self.TABLA_PEDIDO)
            + " ("
            + self._identificador("Tienda")
            + ")"
        )

        columnas_descartado = list(columnas_sql) + [
            self._identificador("MotivoDescarte") + " TEXT NOT NULL",
            self._identificador("GrupoDescarte") + " TEXT",
            self._identificador("DescripcionDescarte") + " TEXT",
            self._identificador("FechaHoraDescarte") + " TEXT NOT NULL",
        ]
        self.conexion.execute(
            "CREATE TABLE IF NOT EXISTS "
            + self._identificador(self.TABLA_DESCARTADO)
            + " ("
            + ", ".join(columnas_descartado)
            + ")"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS IX_CAJAS_PEDIDO_ESCENARIO_DESC_TIENDA "
            "ON "
            + self._identificador(self.TABLA_DESCARTADO)
            + " ("
            + self._identificador("Tienda")
            + ")"
        )

        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS CAJAS_ESCENARIO_ACTIVO (
                Id INTEGER PRIMARY KEY,
                Clave TEXT NOT NULL,
                Grupo TEXT,
                Descripcion TEXT,
                UmbralUnidades INTEGER NOT NULL,
                ModoCalculo TEXT NOT NULL,
                FechaHora TEXT NOT NULL,
                TiendasGrupo INTEGER NOT NULL,
                TiendasGrupoEnPedido INTEGER NOT NULL,
                Lotes REAL NOT NULL,
                Unidades INTEGER NOT NULL,
                CajasXDC INTEGER NOT NULL,
                CajasSilo INTEGER NOT NULL
            )
            """
        )

        columnas_nuevas = {
            "RegistrosPedido": "INTEGER NOT NULL DEFAULT 0",
            "TiendasPedido": "INTEGER NOT NULL DEFAULT 0",
            "ApartesPedido": "INTEGER NOT NULL DEFAULT 0",
            "TiendasFijas": "INTEGER NOT NULL DEFAULT 0",
            "SkusPermitidos": "INTEGER NOT NULL DEFAULT 0",
            "TablaPedido": "TEXT NOT NULL DEFAULT 'CAJAS_PEDIDO_ESCENARIO_ACTIVO'",
            "RegistrosDescartados": "INTEGER NOT NULL DEFAULT 0",
            "TiendasDescartadas": "INTEGER NOT NULL DEFAULT 0",
            "ApartesDescartados": "INTEGER NOT NULL DEFAULT 0",
            "UnidadesDescartadas": "INTEGER NOT NULL DEFAULT 0",
            "LotesDescartados": "REAL NOT NULL DEFAULT 0",
            "Valido": "INTEGER NOT NULL DEFAULT 1",
        }
        for columna, definicion in columnas_nuevas.items():
            self._asegurar_columna(self.TABLA_META, columna, definicion)

        self.conexion.commit()

    def _leer_estarepp(self):
        """Lee las lineas de los pedidos de Calculo de cajas (V2.1).

        Cada fila devuelve las 21 columnas de ESTAREPP y, en la posicion 21,
        el indicador CalcularPicos de su pedido.
        """
        GestorPedidosCajas(self.conexion)
        columnas = ", ".join(
            self._identificador(columna) for columna in self.COLUMNAS_ESTAREPP
        )
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT " + columnas + ", IFNULL(\"CalcularPicos\", 1) FROM "
            + self._identificador(GestorPedidosCajas.TABLA_LINEAS)
        )
        return cursor.fetchall()

    def _construir_pedido(self, escenario, umbral, tiendas_fijas):
        filas = self._leer_estarepp()
        if not filas:
            raise ErrorPedidoEscenarioActivo(
                "Calculo de cajas no tiene ningun pedido importado para "
                "materializar el escenario."
            )

        escenario = escenario or {}
        tiendas_excluidas = self._normalizar_tiendas(
            escenario.get("Tiendas", set())
        )
        tiendas_fijas = self._normalizar_tiendas(tiendas_fijas)
        umbral = max(0, int(umbral or 0))

        motor = MotorCalculoCajasPedido()
        try:
            preparadas = []
            unidades_normales_por_sku = {}

            # El pedido descartado del escenario debe ser una fotografia
            # completa del pedido inicial de las tiendas eliminadas por el
            # grupo. No debe pasar por el filtro de picos ni por la validacion
            # de talla usada por el motor de cajas. Por eso se toma desde las
            # lineas originales de los pedidos antes de preparar la demanda activa.
            grupo = str(escenario.get("Grupo", "") or "")
            descripcion = str(escenario.get("Descripcion", "") or "")
            descartadas_por_grupo = []

            numero_columnas = len(self.COLUMNAS_ESTAREPP)
            for fila_completa in filas:
                fila = tuple(fila_completa[:numero_columnas])
                calcular_picos = bool(int(fila_completa[numero_columnas] or 0))
                tienda = self._numero_entero(fila[3], None)
                if tienda is not None and tienda in tiendas_excluidas:
                    descartadas_por_grupo.append((tuple(fila), "GRUPO", grupo, descripcion))

                talla = motor.normalizar_talla(fila[10])
                if talla is None:
                    # El motor de cajas tampoco incorpora esta linea al
                    # escenario activo, por lo que no debe aparecer en el
                    # pedido global materializado. Si la tienda pertenece al
                    # grupo descartado, la linea ya queda guardada arriba en
                    # la fotografia completa de descartadas.
                    continue

                sku = motor.crear_sku(
                    fila[7],
                    fila[8],
                    fila[9],
                    talla,
                    fila[1],
                    fila[2],
                )
                es_fija = tienda is not None and tienda in tiendas_fijas
                unidades = self._numero_entero(fila[17], 0) or 0

                preparadas.append((tuple(fila), tienda, sku, es_fija, calcular_picos))
                if not es_fija and calcular_picos:
                    unidades_normales_por_sku[sku] = (
                        int(unidades_normales_por_sku.get(sku, 0)) + unidades
                    )

            skus_permitidos = {
                sku
                for sku, unidades in unidades_normales_por_sku.items()
                if int(unidades or 0) >= umbral
            }

            resultado = []
            for fila, tienda, sku, es_fija, calcular_picos in preparadas:
                if tienda is not None and tienda in tiendas_excluidas:
                    continue
                if linea_eliminada_por_picos(
                    sku, calcular_picos, es_fija, skus_permitidos
                ):
                    # Los SKU bajo umbral afectan al pedido activo, pero no se
                    # mezclan dentro del pedido de tiendas descartadas. Si mas
                    # adelante se necesita auditoria de picos, debe ir a una
                    # tabla separada de trazabilidad, no a
                    # CAJAS_PEDIDO_ESCENARIO_DESCARTADO.
                    continue
                resultado.append(fila)

            return resultado, descartadas_por_grupo, skus_permitidos, tiendas_fijas
        finally:
            try:
                motor.bd.cerrar()
            except Exception:
                pass

    @staticmethod
    def _estadisticas_filas(filas):
        tiendas = set()
        apartes = set()
        unidades = 0
        lotes = 0.0

        for fila in filas:
            tienda = GestorPedidoEscenarioActivo._numero_entero(fila[3], None)
            aparte = GestorPedidoEscenarioActivo._numero_entero(fila[5], 0)
            if tienda is not None:
                tiendas.add(tienda)
                apartes.add((tienda, aparte))
            unidades += GestorPedidoEscenarioActivo._numero_entero(fila[17], 0) or 0
            lotes += GestorPedidoEscenarioActivo._numero_real(fila[20], 0.0)

        return {
            "Registros": len(filas),
            "Tiendas": len(tiendas),
            "Apartes": len(apartes),
            "Unidades": int(unidades),
            "Lotes": float(lotes),
        }

    @staticmethod
    def _validar_con_resultado(estadisticas, resultado):
        resultado = resultado or {}
        unidades_esperadas = int(resultado.get("Unidades", estadisticas["Unidades"]) or 0)
        lotes_esperados = float(resultado.get("Lotes", estadisticas["Lotes"]) or 0.0)

        if estadisticas["Unidades"] != unidades_esperadas:
            raise ErrorPedidoEscenarioActivo(
                "El pedido materializado no coincide con el escenario calculado. "
                "Unidades esperadas: "
                + str(unidades_esperadas)
                + " | unidades materializadas: "
                + str(estadisticas["Unidades"])
                + "."
            )

        if abs(estadisticas["Lotes"] - lotes_esperados) > 0.0001:
            raise ErrorPedidoEscenarioActivo(
                "El pedido materializado no coincide con el escenario calculado. "
                "Lotes esperados: "
                + str(round(lotes_esperados, 4))
                + " | lotes materializados: "
                + str(round(estadisticas["Lotes"], 4))
                + "."
            )

    def guardar_desde_estarepp(
        self,
        escenario,
        resultado,
        umbral,
        modo,
        tiendas_fijas=None,
    ):
        """Materializa atomically el pedido exacto del escenario activo."""
        filas, descartadas, skus_permitidos, tiendas_fijas = self._construir_pedido(
            escenario=escenario,
            umbral=umbral,
            tiendas_fijas=tiendas_fijas,
        )
        estadisticas = self._estadisticas_filas(filas)
        estadisticas_descartadas = self._estadisticas_filas([fila for fila, _motivo, _grupo, _desc in descartadas])
        if estadisticas["Registros"] <= 0:
            raise ErrorPedidoEscenarioActivo(
                "El escenario seleccionado no contiene lineas de pedido y no "
                "puede utilizarse en los formularios de reparto."
            )
        self._validar_con_resultado(estadisticas, resultado)

        escenario = escenario or {}
        resultado = resultado or {}
        fecha_hora = datetime.now().isoformat(timespec="seconds")
        columnas = ", ".join(
            self._identificador(columna) for columna in self.COLUMNAS_ESTAREPP
        )
        marcadores = ", ".join("?" for _ in self.COLUMNAS_ESTAREPP)
        columnas_descartado = columnas + ", " + ", ".join([
            self._identificador("MotivoDescarte"),
            self._identificador("GrupoDescarte"),
            self._identificador("DescripcionDescarte"),
            self._identificador("FechaHoraDescarte"),
        ])
        marcadores_descartado = ", ".join("?" for _ in range(len(self.COLUMNAS_ESTAREPP) + 4))
        cursor = self.conexion.cursor()

        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_PEDIDO))
            if filas:
                cursor.executemany(
                    "INSERT INTO "
                    + self._identificador(self.TABLA_PEDIDO)
                    + " ("
                    + columnas
                    + ") VALUES ("
                    + marcadores
                    + ")",
                    filas,
                )

            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_DESCARTADO))
            if descartadas:
                filas_descartadas = []
                for fila_descartada, motivo, grupo_desc, descripcion_desc in descartadas:
                    filas_descartadas.append(
                        tuple(fila_descartada)
                        + (str(motivo), str(grupo_desc), str(descripcion_desc), fecha_hora)
                    )
                cursor.executemany(
                    "INSERT INTO "
                    + self._identificador(self.TABLA_DESCARTADO)
                    + " ("
                    + columnas_descartado
                    + ") VALUES ("
                    + marcadores_descartado
                    + ")",
                    filas_descartadas,
                )

            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_META))
            cursor.execute(
                """
                INSERT INTO CAJAS_ESCENARIO_ACTIVO (
                    Id, Clave, Grupo, Descripcion, UmbralUnidades, ModoCalculo,
                    FechaHora, TiendasGrupo, TiendasGrupoEnPedido, Lotes,
                    Unidades, CajasXDC, CajasSilo, RegistrosPedido,
                    TiendasPedido, ApartesPedido, TiendasFijas,
                    SkusPermitidos, TablaPedido, RegistrosDescartados,
                    TiendasDescartadas, ApartesDescartados, UnidadesDescartadas,
                    LotesDescartados, Valido
                ) VALUES (
                    1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1
                )
                """,
                (
                    str(escenario.get("Clave", "TODO")),
                    str(escenario.get("Grupo", "TODO")),
                    str(escenario.get("Descripcion", "TODO")),
                    int(umbral or 0),
                    str(modo or ""),
                    fecha_hora,
                    int(resultado.get("TiendasGrupo", 0) or 0),
                    int(resultado.get("TiendasGrupoEnPedido", 0) or 0),
                    float(estadisticas["Lotes"]),
                    int(estadisticas["Unidades"]),
                    int(resultado.get("CajasXDC", 0) or 0),
                    int(resultado.get("CajasSilo", 0) or 0),
                    int(estadisticas["Registros"]),
                    int(estadisticas["Tiendas"]),
                    int(estadisticas["Apartes"]),
                    int(len(tiendas_fijas)),
                    int(len(skus_permitidos)),
                    self.TABLA_PEDIDO,
                    int(estadisticas_descartadas["Registros"]),
                    int(estadisticas_descartadas["Tiendas"]),
                    int(estadisticas_descartadas["Apartes"]),
                    int(estadisticas_descartadas["Unidades"]),
                    float(estadisticas_descartadas["Lotes"]),
                ),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

        return self.verificar_guardado_persistente(
            clave_esperada=str(escenario.get("Clave", "TODO"))
        )

    def _ruta_base_principal(self):
        try:
            cursor = self.conexion.cursor()
            cursor.execute("PRAGMA database_list")
            for _secuencia, nombre, ruta in cursor.fetchall():
                if str(nombre).lower() == "main":
                    return str(ruta or "").strip()
        except Exception:
            return ""
        return ""

    def verificar_guardado_persistente(self, clave_esperada=None):
        """Comprueba el escenario con la conexion actual y otra independiente.

        La segunda lectura detecta de inmediato errores de commit o de ruta de
        base de datos antes de informar al operador de que el escenario esta
        disponible para los demas formularios.
        """
        estado = self.obtener_estado()
        if not estado.get("Disponible"):
            raise ErrorPedidoEscenarioActivo(self.texto_estado(estado))
        if clave_esperada is not None and str(estado.get("Clave", "")) != str(
            clave_esperada
        ):
            raise ErrorPedidoEscenarioActivo(
                "El escenario leido despues de guardar no coincide con el "
                "escenario seleccionado."
            )

        ruta = self._ruta_base_principal()
        if ruta not in ("", ":memory:"):
            conexion_comprobacion = None
            try:
                conexion_comprobacion = sqlite3.connect(ruta, timeout=5)
                gestor_comprobacion = GestorPedidoEscenarioActivo(
                    conexion_comprobacion
                )
                estado_externo = gestor_comprobacion.obtener_estado()
                if not estado_externo.get("Disponible"):
                    raise ErrorPedidoEscenarioActivo(
                        "La comprobacion desde una segunda conexion no puede "
                        "leer el escenario guardado. "
                        + self.texto_estado(estado_externo)
                    )
                if str(estado_externo.get("Clave", "")) != str(
                    estado.get("Clave", "")
                ):
                    raise ErrorPedidoEscenarioActivo(
                        "La segunda conexion ha leido un escenario diferente."
                    )
                if int(estado_externo.get("Registros", 0) or 0) != int(
                    estado.get("Registros", 0) or 0
                ):
                    raise ErrorPedidoEscenarioActivo(
                        "La segunda conexion no ha leido todas las lineas del "
                        "pedido seleccionado."
                    )
            finally:
                if conexion_comprobacion is not None:
                    try:
                        conexion_comprobacion.close()
                    except Exception:
                        pass
        return estado

    def limpiar(self):
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_PEDIDO))
            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_DESCARTADO))
            cursor.execute("DELETE FROM " + self._identificador(self.TABLA_META))
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    def obtener_estado(self):
        self.asegurar_tablas()
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT
                Clave, Grupo, Descripcion, UmbralUnidades, ModoCalculo,
                FechaHora, TiendasGrupo, TiendasGrupoEnPedido, Lotes,
                Unidades, CajasXDC, CajasSilo, RegistrosPedido,
                TiendasPedido, ApartesPedido, TiendasFijas,
                SkusPermitidos, TablaPedido, RegistrosDescartados,
                TiendasDescartadas, ApartesDescartados, UnidadesDescartadas,
                LotesDescartados, Valido
            FROM CAJAS_ESCENARIO_ACTIVO
            WHERE Id = 1
            """
        )
        fila = cursor.fetchone()

        cursor.execute(
            "SELECT COUNT(*), COUNT(DISTINCT Tienda), "
            "IFNULL(SUM(Unidades), 0), IFNULL(SUM(Lotes), 0) "
            "FROM "
            + self._identificador(self.TABLA_PEDIDO)
        )
        actuales = cursor.fetchone() or (0, 0, 0, 0.0)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT Tienda, Aparte FROM "
            + self._identificador(self.TABLA_PEDIDO)
            + ")"
        )
        apartes_actuales = int((cursor.fetchone() or (0,))[0] or 0)

        if fila is None:
            return {
                "Disponible": False,
                "Motivo": "No hay ningun escenario seleccionado en Calculo de cajas.",
                "Registros": int(actuales[0] or 0),
            }

        estado = {
            "Clave": fila[0],
            "Grupo": fila[1],
            "Descripcion": fila[2],
            "UmbralUnidades": int(fila[3] or 0),
            "ModoCalculo": fila[4],
            "FechaHora": fila[5],
            "TiendasGrupo": int(fila[6] or 0),
            "TiendasGrupoEnPedido": int(fila[7] or 0),
            "Lotes": float(actuales[3] or 0.0),
            "Unidades": int(actuales[2] or 0),
            "CajasXDC": int(fila[10] or 0),
            "CajasSilo": int(fila[11] or 0),
            "Registros": int(actuales[0] or 0),
            "Tiendas": int(actuales[1] or 0),
            "Apartes": apartes_actuales,
            "TiendasFijas": int(fila[15] or 0),
            "SkusPermitidos": int(fila[16] or 0),
            "TablaPedido": str(fila[17] or self.TABLA_PEDIDO),
            "RegistrosDescartados": int(fila[18] or 0),
            "TiendasDescartadas": int(fila[19] or 0),
            "ApartesDescartados": int(fila[20] or 0),
            "UnidadesDescartadas": int(fila[21] or 0),
            "LotesDescartados": float(fila[22] or 0.0),
            "Valido": bool(int(fila[23] or 0)),
        }
        integridad = (
            int(fila[12] or 0) == estado["Registros"]
            and int(fila[13] or 0) == estado["Tiendas"]
            and int(fila[14] or 0) == estado["Apartes"]
            and int(fila[9] or 0) == estado["Unidades"]
            and abs(float(fila[8] or 0.0) - estado["Lotes"]) <= 0.0001
        )
        estado["Integridad"] = integridad
        estado["Disponible"] = bool(
            estado["Valido"]
            and estado["Integridad"]
            and estado["Registros"] > 0
            and estado["TablaPedido"] == self.TABLA_PEDIDO
        )
        if not estado["Disponible"]:
            estado["Motivo"] = (
                "El pedido materializado del escenario no esta disponible o "
                "no supera la comprobacion de integridad. Vuelve a seleccionar "
                "el escenario en Calculo de cajas."
            )
        return estado

    def _estadisticas_tabla_pedido(self, tabla):
        self.asegurar_tablas()
        cursor = self.conexion.cursor()
        identificador = self._identificador(tabla)
        cursor.execute(
            "SELECT COUNT(*), COUNT(DISTINCT Tienda), "
            "IFNULL(SUM(Unidades), 0), IFNULL(SUM(Lotes), 0) "
            "FROM " + identificador
        )
        fila = cursor.fetchone() or (0, 0, 0, 0.0)
        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT Tienda, IFNULL(Aparte, 0) "
            "FROM " + identificador + ")"
        )
        apartes = int((cursor.fetchone() or (0,))[0] or 0)
        return {
            "Registros": int(fila[0] or 0),
            "Tiendas": int(fila[1] or 0),
            "Unidades": int(fila[2] or 0),
            "Lotes": float(fila[3] or 0.0),
            "Apartes": apartes,
        }

    @classmethod
    def etiqueta_grupo(cls, estado):
        estado = estado or {}
        grupo = str(estado.get("Grupo", "") or "").strip()
        descripcion = str(estado.get("Descripcion", "") or "").strip()
        if grupo.upper() in ("", "TODO") and descripcion.upper() in ("", "TODO"):
            return "TODO"
        if grupo.upper() in ("", "TODO"):
            return descripcion or "TODO"
        if descripcion.upper() in ("", "TODO"):
            return grupo
        return (grupo + " " + descripcion).strip()

    @classmethod
    def nombre_pedido_activo(cls, estado):
        etiqueta = cls.etiqueta_grupo(estado)
        if etiqueta.upper() == "TODO":
            return "PEDIDO TOTAL"
        return "PEDIDO TOTAL - " + etiqueta

    @classmethod
    def nombre_pedido_descartado(cls, estado):
        etiqueta = cls.etiqueta_grupo(estado)
        if etiqueta.upper() == "TODO":
            return "TIENDAS DESCARTADAS - SIN GRUPO"
        return "TIENDAS DESCARTADAS - " + etiqueta

    def obtener_estado_descartado(self):
        """Devuelve la fotografia de tiendas descartadas del escenario activo."""
        estado_activo = self.obtener_estado()
        if not estado_activo.get("Disponible"):
            return {
                "Disponible": False,
                "Motivo": self.texto_estado(estado_activo),
            }

        estadisticas = self._estadisticas_tabla_pedido(self.TABLA_DESCARTADO)
        if estadisticas["Registros"] <= 0:
            return {
                "Disponible": False,
                "Grupo": estado_activo.get("Grupo", ""),
                "Descripcion": estado_activo.get("Descripcion", ""),
                "Motivo": (
                    "El escenario activo no tiene pedido descartado disponible. "
                    "Si el escenario es TODO no hay grupo descartado."
                ),
            }

        estado = dict(estado_activo)
        estado.update({
            "TipoPedidoEscenario": "DESCARTADO",
            "TablaPedido": self.TABLA_DESCARTADO,
            "Registros": estadisticas["Registros"],
            "Tiendas": estadisticas["Tiendas"],
            "Apartes": estadisticas["Apartes"],
            "Lotes": estadisticas["Lotes"],
            "Unidades": estadisticas["Unidades"],
            "Disponible": True,
            "Integridad": True,
            "NombrePedido": self.nombre_pedido_descartado(estado_activo),
        })
        return estado

    @classmethod
    def texto_estado_descartado(cls, estado):
        if not estado or not estado.get("Disponible"):
            motivo = str((estado or {}).get("Motivo", "") or "").strip()
            return motivo or "No hay pedido descartado disponible."
        return (
            cls.nombre_pedido_descartado(estado)
            + " | seleccionado: "
            + cls.formatear_fecha(estado.get("FechaHora"))
            + "\nTiendas: "
            + str(estado.get("Tiendas", 0))
            + " | Tienda+Aparte: "
            + str(estado.get("Apartes", 0))
            + " | Lotes: "
            + cls.formatear_lotes(estado.get("Lotes", 0))
            + " | Unidades: "
            + str(estado.get("Unidades", 0))
        )

    @staticmethod
    def formatear_fecha(valor):
        texto = str(valor or "").strip()
        if len(texto) >= 19 and texto[4] == "-":
            return (
                texto[8:10]
                + "/"
                + texto[5:7]
                + "/"
                + texto[0:4]
                + " "
                + texto[11:19]
            )
        return texto or "no registrada"

    @staticmethod
    def formatear_lotes(valor):
        try:
            numero = float(valor or 0)
            texto = ("%.2f" % numero).rstrip("0").rstrip(".")
            return texto or "0"
        except Exception:
            return str(valor or 0)

    @classmethod
    def texto_estado(cls, estado):
        if not estado or not estado.get("Disponible"):
            motivo = str((estado or {}).get("Motivo", "") or "").strip()
            return motivo or "No hay pedido de escenario activo disponible."

        return (
            "PEDIDO SELECCIONADO: "
            + cls.nombre_pedido_activo(estado)
            + " | seleccionado: "
            + cls.formatear_fecha(estado.get("FechaHora"))
            + "\nTiendas: "
            + str(estado.get("Tiendas", 0))
            + " | Tienda+Aparte: "
            + str(estado.get("Apartes", 0))
            + " | Lotes: "
            + cls.formatear_lotes(estado.get("Lotes", 0))
            + " | Unidades: "
            + str(estado.get("Unidades", 0))
            + "\nPedido descartado: "
            + cls.nombre_pedido_descartado(estado)
            + " | "
            + str(estado.get("TiendasDescartadas", 0))
            + " tiendas | "
            + str(estado.get("ApartesDescartados", 0))
            + " tienda/aparte | "
            + cls.formatear_lotes(estado.get("LotesDescartados", 0))
            + " lotes | "
            + str(estado.get("UnidadesDescartadas", 0))
            + " unidades"
        )
