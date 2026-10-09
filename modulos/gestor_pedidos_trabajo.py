"""Pedidos de trabajo independientes para los formularios de reparto.

Cada formulario conserva una copia procesada y autonoma de su pedido. De esta
forma, importar o preparar otro pedido en una ventana distinta no cambia el
pedido que utilizara el formulario actual.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4


class ErrorPedidoTrabajo(RuntimeError):
    """No se pudo crear o utilizar un pedido de trabajo."""


class GestorPedidosTrabajo:
    TABLA_META = "PEDIDOS_TRABAJO_META"
    TABLA_DETALLE = "PEDIDOS_TRABAJO_DETALLE"
    TABLA_CALCULOS = "PEDIDOS_TRABAJO_ULTIMO_CALCULO"

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion
        self.asegurar_tablas()

    @staticmethod
    def _identificador(nombre):
        return '"' + str(nombre).replace('"', '""') + '"'

    @staticmethod
    def _entero(valor, defecto=0):
        try:
            return int(float(str(valor).strip().replace(",", ".")))
        except Exception:
            return defecto

    @staticmethod
    def _real(valor, defecto=0.0):
        try:
            return float(str(valor).strip().replace(",", "."))
        except Exception:
            return defecto

    @staticmethod
    def _texto(valor):
        return str(valor or "").strip()

    def _tabla_existe(self, tabla):
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(tabla),),
        )
        return cursor.fetchone() is not None

    def _columnas_tabla(self, tabla):
        if not self._tabla_existe(tabla):
            return set()
        cursor = self.conexion.cursor()
        cursor.execute("PRAGMA table_info(" + self._identificador(tabla) + ")")
        return {str(fila[1]).strip().lower() for fila in cursor.fetchall()}

    def asegurar_tablas(self):
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS PEDIDOS_TRABAJO_META (
                ClaveFormulario TEXT PRIMARY KEY,
                IdPedido TEXT NOT NULL,
                TipoOrigen TEXT NOT NULL,
                NombreOrigen TEXT NOT NULL,
                DetalleOrigen TEXT,
                FechaHora TEXT NOT NULL,
                TablaOrigen TEXT,
                RegistrosOrigen INTEGER NOT NULL,
                TiendasOrigen INTEGER NOT NULL,
                TiendasAparte INTEGER NOT NULL,
                Lotes REAL NOT NULL,
                Unidades INTEGER NOT NULL,
                Valido INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS PEDIDOS_TRABAJO_DETALLE (
                ClaveFormulario TEXT NOT NULL,
                IdPedido TEXT NOT NULL,
                Tienda INTEGER NOT NULL,
                Aparte INTEGER NOT NULL,
                Lotes REAL NOT NULL,
                Pais TEXT,
                TipoCaja TEXT
            )
            """
        )
        self.conexion.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS UX_PEDIDOS_TRABAJO_DETALLE
            ON PEDIDOS_TRABAJO_DETALLE
            (ClaveFormulario, Tienda, Aparte)
            """
        )
        self.conexion.execute(
            """
            CREATE INDEX IF NOT EXISTS IX_PEDIDOS_TRABAJO_DETALLE_ID
            ON PEDIDOS_TRABAJO_DETALLE (IdPedido)
            """
        )
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS PEDIDOS_TRABAJO_ULTIMO_CALCULO (
                ClaveFormulario TEXT PRIMARY KEY,
                IdPedido TEXT NOT NULL,
                FechaHora TEXT NOT NULL,
                TipoCalculo TEXT NOT NULL,
                LadoCorto TEXT,
                Resumen TEXT
            )
            """
        )
        self.conexion.commit()

    def _leer_tmp_global(self):
        if not self._tabla_existe("TMP_ESTAREPP"):
            raise ErrorPedidoTrabajo(
                "TMP_ESTAREPP no existe. Importa o prepara primero un pedido."
            )
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT
                CAST(Tienda AS INTEGER),
                CAST(IFNULL(Aparte, 0) AS INTEGER),
                CAST(IFNULL(Lotes, 0) AS REAL),
                IFNULL(Pais, ''),
                IFNULL(TipoCaja, '')
            FROM TMP_ESTAREPP
            ORDER BY Tienda, Aparte
            """
        )
        filas = cursor.fetchall()
        if not filas:
            raise ErrorPedidoTrabajo(
                "El pedido procesado no contiene ninguna Tienda+Aparte."
            )
        return filas

    def _estadisticas_tabla_origen(self, tabla_origen, filas_tmp):
        columnas = self._columnas_tabla(tabla_origen)
        tiene_detalle = {"tienda", "aparte"}.issubset(columnas)
        tiene_unidades = "unidades" in columnas
        tiene_lotes = "lotes" in columnas

        if self._tabla_existe(tabla_origen) and tiene_detalle:
            identificador = self._identificador(tabla_origen)
            cursor = self.conexion.cursor()
            seleccion = [
                "COUNT(*)",
                "COUNT(DISTINCT Tienda)",
            ]
            seleccion.append("IFNULL(SUM(Unidades), 0)" if tiene_unidades else "0")
            seleccion.append("IFNULL(SUM(Lotes), 0)" if tiene_lotes else "0")
            cursor.execute("SELECT " + ", ".join(seleccion) + " FROM " + identificador)
            fila = cursor.fetchone() or (0, 0, 0, 0.0)
            cursor.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT Tienda, IFNULL(Aparte, 0) "
                "FROM " + identificador + ")"
            )
            apartes = int((cursor.fetchone() or (0,))[0] or 0)
            return {
                "Registros": int(fila[0] or 0),
                "Tiendas": int(fila[1] or 0),
                "Apartes": apartes,
                "Unidades": int(fila[2] or 0),
                "Lotes": float(fila[3] or 0.0),
            }

        tiendas = {int(fila[0]) for fila in filas_tmp}
        return {
            "Registros": len(filas_tmp),
            "Tiendas": len(tiendas),
            "Apartes": len(filas_tmp),
            "Unidades": 0,
            "Lotes": sum(float(fila[2] or 0) for fila in filas_tmp),
        }

    def guardar_desde_tmp(
        self,
        clave_formulario,
        tipo_origen,
        nombre_origen,
        tabla_origen="ESTAREPP",
        detalle_origen="",
        estado_origen=None,
    ):
        clave = self._texto(clave_formulario).upper()
        if not clave:
            raise ValueError("La clave del formulario no puede estar vacia.")

        filas = self._leer_tmp_global()
        estadisticas = self._estadisticas_tabla_origen(tabla_origen, filas)
        estado_origen = estado_origen or {}

        # Los datos del escenario materializado son mas precisos que una
        # inferencia si han sido proporcionados expresamente.
        if estado_origen:
            estadisticas["Registros"] = self._entero(
                estado_origen.get("Registros"), estadisticas["Registros"]
            )
            estadisticas["Tiendas"] = self._entero(
                estado_origen.get("Tiendas"), estadisticas["Tiendas"]
            )
            estadisticas["Apartes"] = self._entero(
                estado_origen.get("Apartes"), estadisticas["Apartes"]
            )
            estadisticas["Unidades"] = self._entero(
                estado_origen.get("Unidades"), estadisticas["Unidades"]
            )
            estadisticas["Lotes"] = self._real(
                estado_origen.get("Lotes"), estadisticas["Lotes"]
            )

        id_pedido = uuid4().hex
        fecha_hora = datetime.now().isoformat(timespec="seconds")
        cursor = self.conexion.cursor()

        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "DELETE FROM PEDIDOS_TRABAJO_DETALLE WHERE ClaveFormulario=?",
                (clave,),
            )
            cursor.executemany(
                """
                INSERT INTO PEDIDOS_TRABAJO_DETALLE (
                    ClaveFormulario, IdPedido, Tienda, Aparte, Lotes, Pais, TipoCaja
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        clave,
                        id_pedido,
                        int(fila[0]),
                        int(fila[1] or 0),
                        float(fila[2] or 0),
                        str(fila[3] or ""),
                        str(fila[4] or ""),
                    )
                    for fila in filas
                ],
            )
            cursor.execute(
                """
                INSERT INTO PEDIDOS_TRABAJO_META (
                    ClaveFormulario, IdPedido, TipoOrigen, NombreOrigen,
                    DetalleOrigen, FechaHora, TablaOrigen, RegistrosOrigen,
                    TiendasOrigen, TiendasAparte, Lotes, Unidades, Valido
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(ClaveFormulario) DO UPDATE SET
                    IdPedido=excluded.IdPedido,
                    TipoOrigen=excluded.TipoOrigen,
                    NombreOrigen=excluded.NombreOrigen,
                    DetalleOrigen=excluded.DetalleOrigen,
                    FechaHora=excluded.FechaHora,
                    TablaOrigen=excluded.TablaOrigen,
                    RegistrosOrigen=excluded.RegistrosOrigen,
                    TiendasOrigen=excluded.TiendasOrigen,
                    TiendasAparte=excluded.TiendasAparte,
                    Lotes=excluded.Lotes,
                    Unidades=excluded.Unidades,
                    Valido=1
                """,
                (
                    clave,
                    id_pedido,
                    self._texto(tipo_origen) or "DESCONOCIDO",
                    self._texto(nombre_origen) or "Pedido sin nombre",
                    self._texto(detalle_origen),
                    fecha_hora,
                    self._texto(tabla_origen),
                    int(estadisticas["Registros"]),
                    int(estadisticas["Tiendas"]),
                    int(estadisticas["Apartes"]),
                    float(estadisticas["Lotes"]),
                    int(estadisticas["Unidades"]),
                ),
            )
            cursor.execute(
                "DELETE FROM PEDIDOS_TRABAJO_ULTIMO_CALCULO WHERE ClaveFormulario=?",
                (clave,),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

        return self.obtener_estado(clave)

    def limpiar(self, clave_formulario):
        clave = self._texto(clave_formulario).upper()
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "DELETE FROM PEDIDOS_TRABAJO_DETALLE WHERE ClaveFormulario=?",
                (clave,),
            )
            cursor.execute(
                "DELETE FROM PEDIDOS_TRABAJO_META WHERE ClaveFormulario=?",
                (clave,),
            )
            cursor.execute(
                "DELETE FROM PEDIDOS_TRABAJO_ULTIMO_CALCULO WHERE ClaveFormulario=?",
                (clave,),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    def obtener_estado(self, clave_formulario):
        self.asegurar_tablas()
        clave = self._texto(clave_formulario).upper()
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT
                ClaveFormulario, IdPedido, TipoOrigen, NombreOrigen,
                DetalleOrigen, FechaHora, TablaOrigen, RegistrosOrigen,
                TiendasOrigen, TiendasAparte, Lotes, Unidades, Valido
            FROM PEDIDOS_TRABAJO_META
            WHERE ClaveFormulario=?
            """,
            (clave,),
        )
        fila = cursor.fetchone()
        if fila is None:
            return {
                "Disponible": False,
                "ClaveFormulario": clave,
                "Motivo": "Este formulario todavia no tiene un pedido de trabajo preparado.",
            }

        cursor.execute(
            """
            SELECT
                COUNT(*), COUNT(DISTINCT Tienda), IFNULL(SUM(Lotes), 0),
                COUNT(DISTINCT IdPedido), MIN(IdPedido), MAX(IdPedido)
            FROM PEDIDOS_TRABAJO_DETALLE
            WHERE ClaveFormulario=?
            """,
            (clave,),
        )
        detalle = cursor.fetchone() or (0, 0, 0.0, 0, None, None)
        integridad = (
            int(detalle[0] or 0) == int(fila[9] or 0)
            and int(detalle[3] or 0) == 1
            and str(detalle[4] or "") == str(fila[1] or "")
            and str(detalle[5] or "") == str(fila[1] or "")
            and abs(float(detalle[2] or 0.0) - float(fila[10] or 0.0)) <= 0.0001
        )
        estado = {
            "ClaveFormulario": fila[0],
            "IdPedido": fila[1],
            "TipoOrigen": fila[2],
            "NombreOrigen": fila[3],
            "DetalleOrigen": fila[4] or "",
            "FechaHora": fila[5],
            "TablaOrigen": fila[6] or "",
            "Registros": int(fila[7] or 0),
            "Tiendas": int(fila[8] or 0),
            "Apartes": int(fila[9] or 0),
            "Lotes": float(fila[10] or 0.0),
            "Unidades": int(fila[11] or 0),
            "Valido": bool(int(fila[12] or 0)),
            "Integridad": integridad,
            "DetalleRegistros": int(detalle[0] or 0),
            "DetalleTiendas": int(detalle[1] or 0),
        }
        estado["Disponible"] = bool(
            estado["Valido"] and estado["Integridad"] and estado["DetalleRegistros"] > 0
        )
        if not estado["Disponible"]:
            estado["Motivo"] = (
                "El pedido de trabajo guardado para este formulario no supera "
                "la comprobacion de integridad. Vuelve a importarlo o a cargar el escenario."
            )
        return estado

    def obtener_detalle(self, clave_formulario):
        estado = self.obtener_estado(clave_formulario)
        if not estado.get("Disponible"):
            raise ErrorPedidoTrabajo(self.texto_estado(estado))
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT Tienda, Aparte, Lotes, IFNULL(Pais, ''), IFNULL(TipoCaja, '')
            FROM PEDIDOS_TRABAJO_DETALLE
            WHERE ClaveFormulario=? AND IdPedido=?
            ORDER BY Tienda, Aparte
            """,
            (estado["ClaveFormulario"], estado["IdPedido"]),
        )
        return cursor.fetchall()

    def registrar_calculo(
        self,
        clave_formulario,
        tipo_calculo,
        lado_corto="",
        resumen="",
    ):
        estado = self.obtener_estado(clave_formulario)
        if not estado.get("Disponible"):
            raise ErrorPedidoTrabajo(self.texto_estado(estado))
        self.conexion.execute(
            """
            INSERT INTO PEDIDOS_TRABAJO_ULTIMO_CALCULO (
                ClaveFormulario, IdPedido, FechaHora, TipoCalculo, LadoCorto, Resumen
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ClaveFormulario) DO UPDATE SET
                IdPedido=excluded.IdPedido,
                FechaHora=excluded.FechaHora,
                TipoCalculo=excluded.TipoCalculo,
                LadoCorto=excluded.LadoCorto,
                Resumen=excluded.Resumen
            """,
            (
                estado["ClaveFormulario"],
                estado["IdPedido"],
                datetime.now().isoformat(timespec="seconds"),
                self._texto(tipo_calculo),
                self._texto(lado_corto),
                self._texto(resumen),
            ),
        )
        self.conexion.commit()

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
            return ("%.2f" % numero).rstrip("0").rstrip(".") or "0"
        except Exception:
            return str(valor or 0)

    @classmethod
    def nombre_tipo_origen(cls, tipo):
        tipo = str(tipo or "").strip().upper()
        return {
            "IMPORTACION_MANUAL": "Importacion manual",
            "ESCENARIO_CAJAS": "Escenario de Calculo de cajas",
            "ESCENARIO_ACTIVO": "Pedido total menos grupo",
            "ESCENARIO_DESCARTADO": "Tiendas descartadas",
            "COPIA_INTERNA": "Copia interna",
        }.get(tipo, tipo or "Origen no identificado")

    @classmethod
    def texto_estado(cls, estado):
        if not estado or not estado.get("Disponible"):
            return str((estado or {}).get("Motivo", "") or "Sin pedido de trabajo.")
        texto = (
            "PEDIDO EN USO: "
            + cls.nombre_tipo_origen(estado.get("TipoOrigen"))
            + " | "
            + str(estado.get("NombreOrigen", ""))
            + "\nPreparado: "
            + cls.formatear_fecha(estado.get("FechaHora"))
            + " | Tiendas: "
            + str(estado.get("Tiendas", 0))
            + " | Tienda+Aparte: "
            + str(estado.get("Apartes", 0))
            + " | Lotes: "
            + cls.formatear_lotes(estado.get("Lotes", 0))
        )
        if int(estado.get("Unidades", 0) or 0) > 0:
            texto += " | Unidades: " + str(estado.get("Unidades", 0))
        detalle = str(estado.get("DetalleOrigen", "") or "").strip()
        if detalle:
            texto += "\n" + detalle
        return texto

    @classmethod
    def texto_confirmacion(cls, estado, accion="calcular las tablas"):
        if not estado or not estado.get("Disponible"):
            return cls.texto_estado(estado)
        return (
            "Este formulario va a "
            + str(accion)
            + " con el siguiente pedido:\n\n"
            + cls.texto_estado(estado)
            + "\n\n¿Continuar con este pedido?"
        )

    @classmethod
    def texto_resumen_final(cls, estado):
        if not estado or not estado.get("Disponible"):
            return "Pedido utilizado: no identificado"
        return (
            "Pedido utilizado: "
            + cls.nombre_tipo_origen(estado.get("TipoOrigen"))
            + " - "
            + str(estado.get("NombreOrigen", ""))
            + "\nId pedido: "
            + str(estado.get("IdPedido", ""))[:12]
            + " | Lotes: "
            + cls.formatear_lotes(estado.get("Lotes", 0))
            + " | Tienda+Aparte: "
            + str(estado.get("Apartes", 0))
        )
