"""Pedidos acumulados del formulario Calculo de cajas.

Calculo de cajas puede trabajar con varios pedidos importados a la vez. Cada
pedido se guarda en su propia tabla de lineas (CAJAS_PEDIDO_LINEAS) junto con
la decision del operador de calcular o no picos sobre ese pedido.

Regla de picos (V2.1):
- El umbral "< N unidades por SKU" es comun para todos los pedidos.
- Para decidir si un SKU llega al umbral se suman SOLO las unidades de los
  pedidos marcados con picos, sin contar las tiendas fijas.
- El filtro solo elimina lineas de pedidos marcados con picos.
- Las lineas de pedidos sin picos se conservan siempre.
- Las tiendas fijas conservan siempre todas sus lineas, vengan del pedido que
  vengan (salvo que pertenezcan al grupo excluido en un escenario).

ESTAREPP sigue siendo la tabla de entrada del importador comun. Calculo de
cajas copia su contenido aqui inmediatamente despues de cada importacion, de
modo que importar un pedido en otro formulario ya no cambia el pedido de cajas.
"""

from __future__ import annotations

from datetime import datetime


class ErrorPedidosCajas(RuntimeError):
    """Error de mantenimiento de los pedidos de Calculo de cajas."""


class GestorPedidosCajas:
    TABLA_LINEAS = "CAJAS_PEDIDO_LINEAS"
    TABLA_PEDIDOS = "CAJAS_PEDIDOS_IMPORTADOS"

    COLUMNAS_ESTAREPP = (
        "MarcaComercial", "Campaña", "Año", "Tienda", "Seccion", "Aparte",
        "DescTienda", "Modelo", "Calidad", "Color", "TallaNum", "TallaAlfa",
        "POC", "Familia", "Subfamilia", "Carrusel", "Estado", "Unidades",
        "UoL", "UxL", "Lotes",
    )
    TIPOS_ESTAREPP = (
        "TEXT", "TEXT", "INTEGER", "INTEGER", "INTEGER", "INTEGER",
        "TEXT", "INTEGER", "INTEGER", "INTEGER", "INTEGER", "TEXT",
        "TEXT", "INTEGER", "INTEGER", "TEXT", "INTEGER", "INTEGER",
        "TEXT", "INTEGER", "REAL",
    )

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion
        self.asegurar_tablas()

    # ---------------------------------------------------------
    # Utilidades
    # ---------------------------------------------------------
    @staticmethod
    def _id(nombre):
        return '"' + str(nombre).replace('"', '""') + '"'

    def _tabla_existe(self, tabla):
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(tabla),),
        )
        return cursor.fetchone() is not None

    @classmethod
    def columnas_select(cls, alias=""):
        prefijo = (alias + ".") if alias else ""
        return ", ".join(prefijo + cls._id(c) for c in cls.COLUMNAS_ESTAREPP)

    # ---------------------------------------------------------
    # Estructura y migracion
    # ---------------------------------------------------------
    def asegurar_tablas(self):
        existia = self._tabla_existe(self.TABLA_LINEAS)

        columnas = [
            self._id(nombre) + " " + tipo
            for nombre, tipo in zip(self.COLUMNAS_ESTAREPP, self.TIPOS_ESTAREPP)
        ]
        columnas.append('"IdPedido" INTEGER NOT NULL')
        columnas.append('"CalcularPicos" INTEGER NOT NULL DEFAULT 1')

        self.conexion.execute(
            "CREATE TABLE IF NOT EXISTS " + self._id(self.TABLA_LINEAS)
            + " (" + ", ".join(columnas) + ")"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS IX_CAJAS_PEDIDO_LINEAS_PEDIDO "
            "ON " + self._id(self.TABLA_LINEAS) + " (IdPedido)"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS IX_CAJAS_PEDIDO_LINEAS_TIENDA "
            "ON " + self._id(self.TABLA_LINEAS) + " (Tienda)"
        )
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS CAJAS_PEDIDOS_IMPORTADOS (
                IdPedido INTEGER PRIMARY KEY AUTOINCREMENT,
                NombreArchivo TEXT NOT NULL,
                Ruta TEXT,
                TipoFichero TEXT,
                FechaHora TEXT NOT NULL,
                CalcularPicos INTEGER NOT NULL DEFAULT 1,
                Registros INTEGER NOT NULL DEFAULT 0,
                Tiendas INTEGER NOT NULL DEFAULT 0,
                Unidades INTEGER NOT NULL DEFAULT 0,
                Lotes REAL NOT NULL DEFAULT 0
            )
            """
        )
        self.conexion.commit()

        if not existia:
            self._migrar_pedido_anterior()

    def _migrar_pedido_anterior(self):
        """Primera ejecucion de V2.1: conserva el pedido que ya habia.

        Antes Calculo de cajas trabajaba directamente sobre ESTAREPP con picos
        para todo el pedido. Si existe un pedido registrado de cajas, se
        traslada como pedido 1 con picos = SI para mantener el resultado
        anterior. El operador puede quitarlo o cambiarlo desde la lista.
        """
        try:
            if not self._tabla_existe("ESTAREPP"):
                return
            if not self._tabla_existe("CAJAS_IMPORTACIONES"):
                return
            cursor = self.conexion.cursor()
            cursor.execute(
                "SELECT Ruta, Detalle FROM CAJAS_IMPORTACIONES WHERE Tipo='PEDIDO'"
            )
            fila = cursor.fetchone()
            if not fila:
                return
            cursor.execute("SELECT COUNT(*) FROM ESTAREPP")
            if int((cursor.fetchone() or (0,))[0] or 0) <= 0:
                return
            ruta, detalle = fila
            nombre = self._nombre_archivo(ruta) + " (version anterior)"
            self.anadir_desde_estarepp(
                nombre_archivo=nombre,
                ruta=ruta,
                tipo_fichero=detalle or "",
                calcular_picos=True,
            )
        except Exception as error:
            print("AVISO: no se pudo migrar el pedido anterior de cajas:", error)

    @staticmethod
    def _nombre_archivo(ruta):
        if not ruta:
            return "Pedido"
        texto = str(ruta).replace("\\", "/").rstrip("/")
        return texto.split("/")[-1] or texto

    # ---------------------------------------------------------
    # Altas y bajas
    # ---------------------------------------------------------
    def estadisticas_estarepp(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT COUNT(*), COUNT(DISTINCT Tienda), "
            "IFNULL(SUM(Unidades), 0), IFNULL(SUM(Lotes), 0) FROM ESTAREPP"
        )
        fila = cursor.fetchone() or (0, 0, 0, 0.0)
        return {
            "Registros": int(fila[0] or 0),
            "Tiendas": int(fila[1] or 0),
            "Unidades": int(fila[2] or 0),
            "Lotes": float(fila[3] or 0.0),
        }

    def buscar_duplicado(self, nombre_archivo, estadisticas):
        """Devuelve el pedido ya importado con mismo fichero y mismas cifras."""
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT IdPedido, NombreArchivo, FechaHora
            FROM CAJAS_PEDIDOS_IMPORTADOS
            WHERE NombreArchivo = ? AND Registros = ? AND Unidades = ?
            ORDER BY IdPedido
            LIMIT 1
            """,
            (
                str(nombre_archivo or ""),
                int(estadisticas.get("Registros", 0) or 0),
                int(estadisticas.get("Unidades", 0) or 0),
            ),
        )
        fila = cursor.fetchone()
        if not fila:
            return None
        return {"IdPedido": int(fila[0]), "NombreArchivo": fila[1], "FechaHora": fila[2]}

    def anadir_desde_estarepp(self, nombre_archivo, ruta, tipo_fichero, calcular_picos):
        """Copia el contenido actual de ESTAREPP como un pedido nuevo."""
        estadisticas = self.estadisticas_estarepp()
        if estadisticas["Registros"] <= 0:
            raise ErrorPedidosCajas("El pedido importado no contiene lineas.")

        picos = 1 if calcular_picos else 0
        fecha = datetime.now().isoformat(timespec="seconds")
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                INSERT INTO CAJAS_PEDIDOS_IMPORTADOS
                    (NombreArchivo, Ruta, TipoFichero, FechaHora, CalcularPicos,
                     Registros, Tiendas, Unidades, Lotes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(nombre_archivo or "Pedido"),
                    str(ruta or ""),
                    str(tipo_fichero or ""),
                    fecha,
                    picos,
                    estadisticas["Registros"],
                    estadisticas["Tiendas"],
                    estadisticas["Unidades"],
                    estadisticas["Lotes"],
                ),
            )
            id_pedido = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO " + self._id(self.TABLA_LINEAS)
                + " (" + self.columnas_select() + ", IdPedido, CalcularPicos) "
                + "SELECT " + self.columnas_select() + ", ?, ? FROM ESTAREPP",
                (id_pedido, picos),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

        return self.obtener_pedido(id_pedido)

    def cambiar_picos(self, id_pedido, calcular_picos):
        picos = 1 if calcular_picos else 0
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "UPDATE CAJAS_PEDIDOS_IMPORTADOS SET CalcularPicos=? WHERE IdPedido=?",
                (picos, int(id_pedido)),
            )
            cursor.execute(
                "UPDATE " + self._id(self.TABLA_LINEAS)
                + " SET CalcularPicos=? WHERE IdPedido=?",
                (picos, int(id_pedido)),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    def eliminar(self, ids_pedido):
        ids = [int(valor) for valor in (ids_pedido or [])]
        if not ids:
            return 0
        marcas = ",".join("?" for _ in ids)
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "DELETE FROM " + self._id(self.TABLA_LINEAS)
                + " WHERE IdPedido IN (" + marcas + ")",
                ids,
            )
            cursor.execute(
                "DELETE FROM CAJAS_PEDIDOS_IMPORTADOS WHERE IdPedido IN (" + marcas + ")",
                ids,
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise
        return len(ids)

    def vaciar(self):
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM " + self._id(self.TABLA_LINEAS))
            cursor.execute("DELETE FROM CAJAS_PEDIDOS_IMPORTADOS")
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    # ---------------------------------------------------------
    # Consultas
    # ---------------------------------------------------------
    def _fila_a_pedido(self, fila):
        return {
            "IdPedido": int(fila[0]),
            "NombreArchivo": fila[1] or "",
            "Ruta": fila[2] or "",
            "TipoFichero": fila[3] or "",
            "FechaHora": fila[4] or "",
            "CalcularPicos": bool(int(fila[5] or 0)),
            "Registros": int(fila[6] or 0),
            "Tiendas": int(fila[7] or 0),
            "Unidades": int(fila[8] or 0),
            "Lotes": float(fila[9] or 0.0),
        }

    _SELECT_PEDIDOS = """
        SELECT IdPedido, NombreArchivo, Ruta, TipoFichero, FechaHora,
               CalcularPicos, Registros, Tiendas, Unidades, Lotes
        FROM CAJAS_PEDIDOS_IMPORTADOS
    """

    def obtener_pedidos(self):
        cursor = self.conexion.cursor()
        cursor.execute(self._SELECT_PEDIDOS + " ORDER BY IdPedido")
        return [self._fila_a_pedido(fila) for fila in cursor.fetchall()]

    def obtener_pedido(self, id_pedido):
        cursor = self.conexion.cursor()
        cursor.execute(self._SELECT_PEDIDOS + " WHERE IdPedido=?", (int(id_pedido),))
        fila = cursor.fetchone()
        return self._fila_a_pedido(fila) if fila else None

    def contar_lineas(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT COUNT(*) FROM " + self._id(self.TABLA_LINEAS))
        return int((cursor.fetchone() or (0,))[0] or 0)

    def resumen(self):
        pedidos = self.obtener_pedidos()
        con_picos = [p for p in pedidos if p["CalcularPicos"]]
        sin_picos = [p for p in pedidos if not p["CalcularPicos"]]
        return {
            "Pedidos": len(pedidos),
            "ConPicos": len(con_picos),
            "SinPicos": len(sin_picos),
            "Registros": sum(p["Registros"] for p in pedidos),
            "Unidades": sum(p["Unidades"] for p in pedidos),
            "Lotes": sum(p["Lotes"] for p in pedidos),
            "UnidadesConPicos": sum(p["Unidades"] for p in con_picos),
            "UnidadesSinPicos": sum(p["Unidades"] for p in sin_picos),
        }


def linea_eliminada_por_picos(sku, calcular_picos, es_tienda_fija, skus_permitidos):
    """Regla unica del filtro de picos para una linea de pedido.

    Una linea se elimina solo si pertenece a un pedido con picos, no es de una
    tienda fija y su SKU no alcanza el umbral sumando los pedidos con picos.
    """
    if skus_permitidos is None:
        return False
    if es_tienda_fija:
        return False
    if not calcular_picos:
        return False
    return sku not in skus_permitidos
