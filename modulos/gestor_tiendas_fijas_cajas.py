"""Gestion persistente de tiendas fijas para el calculo de picos.

Las tiendas incluidas en este maestro conservan todas sus lineas de pedido
frente al filtro global de unidades por SKU. La condicion de tienda fija no
impide que la tienda sea eliminada cuando pertenece al grupo que se esta
simulando: la exclusion del grupo se aplica despues del filtro de picos.
"""

from __future__ import annotations

from datetime import datetime
import re


class ErrorTiendasFijas(ValueError):
    """Error de validacion o mantenimiento de la lista de tiendas fijas."""


class GestorTiendasFijasCajas:
    """Mantiene la lista editable de tiendas fuera del calculo de picos."""

    TIENDAS_INICIALES = (836, 2032, 5515, 11158, 13031, 19556)

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion
        self.asegurar_tablas()

    @staticmethod
    def _fecha_actual():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _normalizar_tienda(valor):
        texto = str(valor if valor is not None else "").strip()
        if texto == "":
            raise ErrorTiendasFijas("El codigo de tienda no puede estar vacio.")
        try:
            tienda = int(texto)
        except Exception as error:
            raise ErrorTiendasFijas(
                "El valor '" + texto + "' no es un codigo de tienda entero valido."
            ) from error
        if tienda <= 0:
            raise ErrorTiendasFijas(
                "El codigo de tienda debe ser un entero mayor que cero."
            )
        return tienda

    @classmethod
    def normalizar_lista(cls, tiendas):
        resultado = set()
        for valor in tiendas or []:
            resultado.add(cls._normalizar_tienda(valor))
        return sorted(resultado)

    @classmethod
    def analizar_texto(cls, texto):
        """Convierte texto pegado desde Excel en una lista de tiendas unicas."""
        contenido = str(texto or "").strip()
        if contenido == "":
            return []

        tokens = [
            token.strip()
            for token in re.split(r"[\s,;|]+", contenido)
            if token.strip()
        ]
        tiendas = []
        errores = []
        for token in tokens:
            try:
                tiendas.append(cls._normalizar_tienda(token))
            except ErrorTiendasFijas:
                errores.append(token)

        if errores:
            muestra = ", ".join(errores[:15])
            if len(errores) > 15:
                muestra += " ..."
            raise ErrorTiendasFijas(
                "Se han encontrado valores de tienda no validos:\n\n" + muestra
            )

        return sorted(set(tiendas))

    def asegurar_tablas(self):
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS CAJAS_TIENDAS_FIJAS (
                    Tienda INTEGER PRIMARY KEY,
                    FechaModificacion TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS CAJAS_TIENDAS_FIJAS_CONFIG (
                    Id INTEGER PRIMARY KEY,
                    Inicializada INTEGER NOT NULL,
                    FechaInicializacion TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "SELECT Inicializada FROM CAJAS_TIENDAS_FIJAS_CONFIG WHERE Id = 1"
            )
            inicializada = cursor.fetchone()
            if inicializada is None:
                fecha = self._fecha_actual()
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO CAJAS_TIENDAS_FIJAS
                        (Tienda, FechaModificacion)
                    VALUES (?, ?)
                    """,
                    [(tienda, fecha) for tienda in self.TIENDAS_INICIALES],
                )
                cursor.execute(
                    """
                    INSERT INTO CAJAS_TIENDAS_FIJAS_CONFIG
                        (Id, Inicializada, FechaInicializacion)
                    VALUES (1, 1, ?)
                    """,
                    (fecha,),
                )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    def obtener_tiendas(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT Tienda FROM CAJAS_TIENDAS_FIJAS ORDER BY Tienda"
        )
        return {int(fila[0]) for fila in cursor.fetchall()}

    def obtener_detalle(self):
        """Devuelve tienda, nombre actual y presencia en el pedido cargado."""
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT
                f.Tienda,
                COALESCE(
                    (
                        SELECT TRIM(IFNULL(tw.Nombre, ''))
                        FROM Tiendas_Web tw
                        WHERE CAST(tw.Tienda AS INTEGER) = f.Tienda
                        LIMIT 1
                    ),
                    ''
                ) AS Nombre,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM ESTAREPP e
                    WHERE CAST(e.Tienda AS INTEGER) = f.Tienda
                ) THEN 1 ELSE 0 END AS EnPedido
            FROM CAJAS_TIENDAS_FIJAS f
            ORDER BY f.Tienda
            """
        )
        resultado = []
        for tienda, nombre, en_pedido in cursor.fetchall():
            resultado.append(
                {
                    "Tienda": int(tienda),
                    "Nombre": str(nombre or "").strip(),
                    "EnPedido": bool(int(en_pedido or 0)),
                }
            )
        return resultado

    def anadir(self, tiendas):
        tiendas = self.normalizar_lista(tiendas)
        if not tiendas:
            return 0
        existentes = self.obtener_tiendas()
        nuevas = [tienda for tienda in tiendas if tienda not in existentes]
        if not nuevas:
            return 0

        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            fecha = self._fecha_actual()
            cursor.executemany(
                """
                INSERT INTO CAJAS_TIENDAS_FIJAS (Tienda, FechaModificacion)
                VALUES (?, ?)
                """,
                [(tienda, fecha) for tienda in nuevas],
            )
            self.conexion.commit()
            return len(nuevas)
        except Exception:
            self.conexion.rollback()
            raise

    def reemplazar(self, tiendas):
        tiendas = self.normalizar_lista(tiendas)
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM CAJAS_TIENDAS_FIJAS")
            fecha = self._fecha_actual()
            if tiendas:
                cursor.executemany(
                    """
                    INSERT INTO CAJAS_TIENDAS_FIJAS (Tienda, FechaModificacion)
                    VALUES (?, ?)
                    """,
                    [(tienda, fecha) for tienda in tiendas],
                )
            self.conexion.commit()
            return len(tiendas)
        except Exception:
            self.conexion.rollback()
            raise

    def eliminar(self, tiendas):
        tiendas = self.normalizar_lista(tiendas)
        if not tiendas:
            return 0
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            eliminadas = 0
            for tienda in tiendas:
                cursor.execute(
                    "DELETE FROM CAJAS_TIENDAS_FIJAS WHERE Tienda = ?",
                    (tienda,),
                )
                eliminadas += int(cursor.rowcount or 0)
            self.conexion.commit()
            return eliminadas
        except Exception:
            self.conexion.rollback()
            raise

    def cambiar(self, tienda_anterior, tienda_nueva):
        anterior = self._normalizar_tienda(tienda_anterior)
        nueva = self._normalizar_tienda(tienda_nueva)
        if anterior == nueva:
            return False

        existentes = self.obtener_tiendas()
        if anterior not in existentes:
            raise ErrorTiendasFijas(
                "La tienda " + str(anterior) + " ya no existe en la lista."
            )
        if nueva in existentes:
            raise ErrorTiendasFijas(
                "La tienda " + str(nueva) + " ya esta incluida en la lista."
            )

        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "DELETE FROM CAJAS_TIENDAS_FIJAS WHERE Tienda = ?",
                (anterior,),
            )
            cursor.execute(
                """
                INSERT INTO CAJAS_TIENDAS_FIJAS (Tienda, FechaModificacion)
                VALUES (?, ?)
                """,
                (nueva, self._fecha_actual()),
            )
            self.conexion.commit()
            return True
        except Exception:
            self.conexion.rollback()
            raise

    def vaciar(self):
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM CAJAS_TIENDAS_FIJAS")
            eliminadas = int(cursor.rowcount or 0)
            self.conexion.commit()
            return eliminadas
        except Exception:
            self.conexion.rollback()
            raise
