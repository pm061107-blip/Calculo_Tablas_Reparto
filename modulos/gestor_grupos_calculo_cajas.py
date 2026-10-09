"""Maestro independiente de grupos para escenarios del calculo de cajas.

El fichero tiene la misma estructura tabulada que GRUTIEP, pero su contenido
NO sustituye el maestro GRUTIEP usado para validar las exportaciones de los
clasificadores. Este modulo mantiene una copia propia y persistente para poder
simular, de forma individual, la exclusion de las tiendas de cada grupo.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modulos.gestor_grutiep import ErrorGRUTIEP, GestorGRUTIEP


class ErrorGruposCalculo(ValueError):
    """Error de estructura o contenido del fichero de grupos de calculo."""


class GestorGruposCalculoCajas:
    """Importa, consulta y limpia los grupos usados por el simulador."""

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion
        self.asegurar_tablas()

    def asegurar_tablas(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS CAJAS_GRUPOS_CALCULO (
                TRCODS INTEGER NOT NULL,
                TRDESC TEXT,
                TRTIEN INTEGER NOT NULL,
                PRIMARY KEY (TRCODS, TRTIEN)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS IX_CAJAS_GRUPOS_CALCULO_TIENDA
            ON CAJAS_GRUPOS_CALCULO (TRTIEN)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS CAJAS_GRUPOS_CALCULO_IMPORTACION (
                Id INTEGER PRIMARY KEY,
                Ruta TEXT NOT NULL,
                NombreArchivo TEXT NOT NULL,
                FechaHora TEXT NOT NULL,
                Registros INTEGER NOT NULL,
                Grupos INTEGER NOT NULL,
                Tiendas INTEGER NOT NULL
            )
            """
        )
        self.conexion.commit()

    def importar(self, ruta):
        """Valida por completo y sustituye atomically el maestro anterior."""
        try:
            analisis = GestorGRUTIEP.analizar_archivo(ruta)
        except ErrorGRUTIEP as error:
            raise ErrorGruposCalculo(str(error)) from error

        fecha_hora = datetime.now().isoformat(timespec="seconds")
        cursor = self.conexion.cursor()

        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM CAJAS_GRUPOS_CALCULO")
            cursor.executemany(
                """
                INSERT INTO CAJAS_GRUPOS_CALCULO (TRCODS, TRDESC, TRTIEN)
                VALUES (?, ?, ?)
                """,
                analisis["Datos"],
            )
            cursor.execute("DELETE FROM CAJAS_GRUPOS_CALCULO_IMPORTACION")
            cursor.execute(
                """
                INSERT INTO CAJAS_GRUPOS_CALCULO_IMPORTACION
                    (Id, Ruta, NombreArchivo, FechaHora, Registros, Grupos, Tiendas)
                VALUES
                    (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(Path(analisis["Ruta"])),
                    str(analisis["NombreArchivo"]),
                    fecha_hora,
                    int(analisis["Registros"]),
                    len(analisis["Grupos"]),
                    int(analisis["Tiendas"]),
                ),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

        return self.obtener_estado()

    def limpiar(self):
        """Elimina solo los grupos de simulacion; no toca el GRUTIEP global."""
        cursor = self.conexion.cursor()
        try:
            if self.conexion.in_transaction:
                self.conexion.commit()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM CAJAS_GRUPOS_CALCULO")
            cursor.execute("DELETE FROM CAJAS_GRUPOS_CALCULO_IMPORTACION")
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

    def obtener_grupos(self):
        """Devuelve cada grupo con sus tiendas unicas, sin mezclar grupos."""
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT TRCODS, COALESCE(TRDESC, ''), TRTIEN
            FROM CAJAS_GRUPOS_CALCULO
            ORDER BY TRCODS, TRTIEN
            """
        )

        grupos = {}
        for trcods, trdesc, trtien in cursor.fetchall():
            codigo = int(trcods)
            if codigo not in grupos:
                grupos[codigo] = {
                    "Clave": "GRUPO:" + str(codigo),
                    "Grupo": codigo,
                    "Descripcion": " ".join(str(trdesc or "").strip().split()),
                    "Tiendas": set(),
                }
            grupos[codigo]["Tiendas"].add(int(trtien))

        return [grupos[codigo] for codigo in sorted(grupos)]

    def obtener_estado(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT Ruta, NombreArchivo, FechaHora, Registros, Grupos, Tiendas
            FROM CAJAS_GRUPOS_CALCULO_IMPORTACION
            WHERE Id = 1
            """
        )
        fila = cursor.fetchone()
        if not fila:
            return None
        return {
            "Ruta": fila[0],
            "NombreArchivo": fila[1],
            "FechaHora": fila[2],
            "Registros": int(fila[3] or 0),
            "Grupos": int(fila[4] or 0),
            "Tiendas": int(fila[5] or 0),
        }

    def guardar_escenario_activo(self, escenario, resultado, umbral, modo):
        """Compatibilidad: delega en el gestor unico del pedido seleccionado.

        Desde V17.23 el escenario no es solo una cabecera: debe incluir una
        copia completa del pedido. Mantener dos escritores sobre la misma tabla
        podia dejar la seleccion sin integridad y hacerla invisible en otros
        formularios.
        """
        from modulos.gestor_pedido_escenario_activo import (
            GestorPedidoEscenarioActivo,
        )
        from modulos.gestor_tiendas_fijas_cajas import (
            GestorTiendasFijasCajas,
        )

        tiendas_fijas = GestorTiendasFijasCajas(
            self.conexion
        ).obtener_tiendas()
        return GestorPedidoEscenarioActivo(
            self.conexion
        ).guardar_desde_estarepp(
            escenario=escenario,
            resultado=resultado,
            umbral=umbral,
            modo=modo,
            tiendas_fijas=tiendas_fijas,
        )

    def limpiar_escenario_activo(self):
        """Compatibilidad: elimina cabecera y detalle desde un unico gestor."""
        try:
            from modulos.gestor_pedido_escenario_activo import (
                GestorPedidoEscenarioActivo,
            )

            GestorPedidoEscenarioActivo(self.conexion).limpiar()
        except Exception:
            try:
                self.conexion.rollback()
            except Exception:
                pass

    def tiene_grupos(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT COUNT(*) FROM CAJAS_GRUPOS_CALCULO")
        fila = cursor.fetchone()
        return bool(fila and int(fila[0] or 0) > 0)
